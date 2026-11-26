"""Git operations for S.A.M.U.E.L. v2 — branch, commit, push."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from samuel.core.command_safety import validate_command_args
from samuel.core.errors import GitTransportAuthError
from samuel.core.ports import IGitTransportAuth

log = logging.getLogger(__name__)

_TIMEOUT = 30
_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
DEFAULT_GIT_AUTHOR_NAME = "S.A.M.U.E.L. Reference Agent"
DEFAULT_GIT_AUTHOR_EMAIL = "samuel-reference@localhost.invalid"
GIT_PATH_OVERRIDE_KEYS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
    }
)
_GIT_AUTH_CONTROL_KEYS = frozenset(
    {
        "GIT_ASKPASS",
        "GIT_ASKPASS_REQUIRE",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_KEY_1",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_VALUE_0",
        "GIT_CONFIG_VALUE_1",
        "GIT_EXEC_PATH",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_TERMINAL_PROMPT",
        "PYTHONHOME",
        "PYTHONPATH",
        "SSH_ASKPASS",
        "SSH_AUTH_SOCK",
    }
)
_GIT_CREDENTIAL_ENVIRONMENT_KEYS = frozenset(
    {
        "GITEA_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "SCM_TOKEN",
        "SAMUEL_GIT_ASKPASS_SECRET",
        "SAMUEL_GIT_ASKPASS_USERNAME",
    }
)
_GIT_STRIPPED_KEYS = _GIT_AUTH_CONTROL_KEYS | _GIT_CREDENTIAL_ENVIRONMENT_KEYS
_GIT_EXECUTION_POLICY = {
    "core.hooksPath": os.devnull,
    "core.fsmonitor": "false",
    "core.attributesFile": os.devnull,
    "credential.helper": "",
    "protocol.allow": "never",
    "protocol.http.allow": "always",
    "protocol.https.allow": "always",
    "protocol.file.allow": "always",
    "protocol.ext.allow": "never",
    "gc.auto": "0",
    "maintenance.auto": "false",
}
_CREDENTIAL_FREE_NETWORK_ENV = {
    "GIT_ASKPASS_REQUIRE": "never",
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_KEY_0": "credential.helper",
    "GIT_CONFIG_KEY_1": "credential.interactive",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_VALUE_0": "",
    "GIT_CONFIG_VALUE_1": "false",
    "GIT_TERMINAL_PROMPT": "0",
}


def git_process_environment(
    overrides: Mapping[str, str] | None = None,
    *,
    strip_path_overrides: bool = False,
) -> dict[str, str]:
    """Build a Git environment without inherited transport credentials."""

    stripped = _GIT_STRIPPED_KEYS | (
        GIT_PATH_OVERRIDE_KEYS if strip_path_overrides else frozenset()
    )
    environment = {key: value for key, value in os.environ.items() if key not in stripped}
    if overrides:
        environment.update(overrides)
    environment.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_PARAMETERS="",
        GIT_TERMINAL_PROMPT="0",
        GIT_PAGER="cat",
    )
    for key in ("GIT_EXTERNAL_DIFF", "GIT_DIFF_OPTS"):
        environment.pop(key, None)
    count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    for key, value in _GIT_EXECUTION_POLICY.items():
        environment[f"GIT_CONFIG_KEY_{count}"] = key
        environment[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    environment["GIT_CONFIG_COUNT"] = str(count)
    return environment


def git_configuration_safe(cwd: Path | None, environment: Mapping[str, str]) -> bool:
    """Reject executable repository configuration before existing Git operations.

    Config inspection never expands includes. Hooks/fsmonitor and inherited
    config are disabled on every invocation, including this passive inspection.
    This is not isolation from a concurrent process with the same OS identity.
    """
    cwd = cwd or Path.cwd()
    inspection_environment = {
        key: value
        for key, value in environment.items()
        if key not in _GIT_CREDENTIAL_ENVIRONMENT_KEYS and key != "GIT_ASKPASS"
    }
    scopes = ["--local"]
    for scope in scopes:
        has_worktree_config = False
        result = subprocess.run(
            ["git", "config", scope, "--no-includes", "--null", "--list"],
            cwd=str(cwd),
            env=inspection_environment,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            shell=False,
        )
        if result.returncode != 0:
            return False
        for entry in result.stdout.split("\0"):
            key = entry.partition("\n")[0].lower()
            if scope == "--local" and key == "extensions.worktreeconfig":
                has_worktree_config = True
            if (
                key.startswith(("include.", "includeif.", "filter."))
                or (
                    key.startswith("protocol.")
                    and key
                    not in {"protocol.file.allow", "protocol.http.allow", "protocol.https.allow"}
                )
                or key
                in {
                    "core.sshcommand",
                    "core.gitproxy",
                    "core.alternaterefscommand",
                    "diff.external",
                    "gpg.program",
                    "core.askpass",
                }
                or re.fullmatch(r"diff\..*\.(command|textconv)", key)
                or re.fullmatch(r"gpg\..*\.program", key)
                or re.fullmatch(r"remote\..*\.(vcs|uploadpack|receivepack|proxy)", key)
            ):
                return False
        if has_worktree_config:
            enabled = subprocess.run(
                [
                    "git",
                    "config",
                    "--local",
                    "--no-includes",
                    "--type=bool",
                    "--get",
                    "extensions.worktreeConfig",
                ],
                cwd=str(cwd),
                env=inspection_environment,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                shell=False,
            )
            if enabled.returncode != 0:
                return False
            if enabled.stdout.strip() == "true":
                scopes.append("--worktree")
    return True


def _run(
    args: list[str],
    cwd: Path | None = None,
    *,
    log_failure: bool = True,
    environment: Mapping[str, str] | None = None,
    strip_path_overrides: bool = False,
) -> tuple[bool, str]:
    """Run a git command, return (success, output)."""
    safety = validate_command_args(["git", *args])
    if not safety["safe"]:
        log.error("Blocked unsafe git operation: %s", ", ".join(safety["blocked_patterns"]))
        return False, "blocked by command safety policy"
    try:
        effective_environment = git_process_environment(
            environment, strip_path_overrides=strip_path_overrides
        )
        if not git_configuration_safe(cwd, effective_environment):
            return False, "git_repository_configuration_unsafe"
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=str(cwd) if cwd else None,
            env=effective_environment,
            shell=False,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            if log_failure:
                log.warning("git %s failed: %s", " ".join(args[:2]), result.stderr.strip())
            return False, result.stderr.strip()
        return True, output
    except subprocess.TimeoutExpired:
        log.error("git %s timed out", " ".join(args[:2]))
        return False, "timeout"
    except FileNotFoundError:
        log.error("git not found")
        return False, "git not found"


def _remote_run(
    args: list[str],
    cwd: Path | None,
    transport_auth: IGitTransportAuth | None,
    operation: Literal["fetch", "push"],
) -> tuple[bool, str]:
    remote_ok, remote_url = _run(["remote", "get-url", "origin"], cwd, log_failure=False)
    if not remote_ok:
        log.error("git %s blocked: origin remote is unavailable", operation)
        return False, "origin remote unavailable"
    try:
        if transport_auth is None:
            completed = _run(
                args,
                cwd,
                log_failure=False,
                environment=_CREDENTIAL_FREE_NETWORK_ENV,
                strip_path_overrides=True,
            )
        else:
            with transport_auth.environment(remote_url, operation) as environment:
                completed = _run(
                    args,
                    cwd,
                    log_failure=False,
                    environment=environment,
                    strip_path_overrides=True,
                )
        if not completed[0]:
            log.error("git %s failed: git_transport_failed", operation)
            return False, "git_transport_failed"
        return completed
    except GitTransportAuthError as exc:
        log.error("git %s blocked: %s", operation, exc.code)
        return False, exc.code


def current_branch(cwd: Path | None = None) -> str:
    """Return the name of the current branch."""
    ok, out = _run(["branch", "--show-current"], cwd)
    return out if ok else ""


def head_sha(cwd: Path | None = None) -> str:
    """Return the full object ID currently checked out."""

    ok, out = _run(["rev-parse", "HEAD"], cwd)
    return out if ok else ""


def index_tree(cwd: Path | None = None) -> str:
    """Materialize and return the staged tree identity without creating a commit."""

    ok, out = _run(["write-tree"], cwd)
    return out if ok and _SHA_RE.fullmatch(out) else ""


def revision_tree(revision: str = "HEAD", cwd: Path | None = None) -> str:
    ok, out = _run(["rev-parse", f"{revision}^{{tree}}"], cwd)
    return out if ok and _SHA_RE.fullmatch(out) else ""


def revision_parent(revision: str = "HEAD", cwd: Path | None = None) -> str:
    ok, out = _run(["rev-parse", f"{revision}^"], cwd)
    return out if ok and _SHA_RE.fullmatch(out) else ""


def worktree_clean(cwd: Path | None = None) -> bool:
    ok, out = _run(["status", "--porcelain"], cwd)
    return ok and not out


def status_porcelain(cwd: Path | None = None) -> str | None:
    """Return stable porcelain-v1 status, or ``None`` when Git cannot inspect it."""

    ok, out = _run(["status", "--porcelain=v1", "--untracked-files=all"], cwd)
    return out if ok else None


def staged_candidate_clean(cwd: Path | None = None) -> bool:
    """Accept only staged candidate changes with no unstaged/untracked state.

    ``write-tree`` binds the index, but by itself does not reveal an untracked
    file or an unstaged edit made after staging.  Resume may enter commit-tree
    only when every porcelain row represents an ordinary staged change and
    the working-tree column is empty.
    """

    status = status_porcelain(cwd)
    if status is None or not status:
        return False
    allowed_index_states = frozenset({"A", "C", "D", "M", "R", "T"})
    return all(
        len(row) >= 3 and row[0] in allowed_index_states and row[1] == " "
        for row in status.splitlines()
    )


def git_control_plane_paths(cwd: Path) -> tuple[Path, ...]:
    """Return canonical paths that Git treats as local repository metadata.

    The reserved ``.git`` marker is always returned.  For an active worktree,
    one read-only ``rev-parse`` call also resolves linked/separate git dirs,
    the common dir, index and object storage, including effective ``GIT_*``
    overrides understood by Git itself.
    """

    root = cwd.resolve(strict=True)
    paths = {(root / ".git").resolve(strict=False)}
    ok, output = _run(
        [
            "rev-parse",
            "--absolute-git-dir",
            "--git-common-dir",
            "--git-path",
            "index",
            "--git-path",
            "objects",
        ],
        root,
        log_failure=False,
    )
    if ok:
        resolved_outputs: list[Path] = []
        for raw_path in output.splitlines():
            if not raw_path:
                continue
            path = Path(raw_path)
            if not path.is_absolute():
                path = root / path
            resolved = path.resolve(strict=False)
            resolved_outputs.append(resolved)
            paths.add(resolved)
        if len(resolved_outputs) >= 3:
            index_path = resolved_outputs[2]
            paths.add(index_path.with_name(f"{index_path.name}.lock"))
    return tuple(sorted(paths, key=lambda path: str(path)))


def prepare_branch_at_head(
    name: str,
    expected_head: str,
    cwd: Path | None = None,
    *,
    transport_auth: IGitTransportAuth | None = None,
) -> bool:
    """Checkout a pushed candidate branch only when it proves ``expected_head``.

    This is the bound-healing continuation path. It never recreates the branch
    from ``origin/main`` and refuses dirty worktrees or moved remote refs.
    """

    if not _SHA_RE.fullmatch(expected_head):
        log.error("prepare_branch_at_head: invalid expected head")
        return False
    if not worktree_clean(cwd):
        log.error("prepare_branch_at_head: worktree is not clean")
        return False
    fetched, error = _remote_run(["fetch", "origin", name], cwd, transport_auth, "fetch")
    if not fetched:
        log.error("prepare_branch_at_head: failed to fetch origin/%s: %s", name, error)
        return False
    ok, remote_head = _run(["rev-parse", f"origin/{name}"], cwd)
    if not ok or remote_head != expected_head:
        log.error("prepare_branch_at_head: origin/%s no longer matches expected head", name)
        return False
    ok, error = _run(["checkout", "-B", name, f"origin/{name}"], cwd)
    if not ok:
        log.error("prepare_branch_at_head: checkout failed for %s: %s", name, error)
        return False
    return current_branch(cwd) == name and head_sha(cwd) == expected_head


def create_branch(
    name: str,
    base: str = "main",
    cwd: Path | None = None,
    *,
    transport_auth: IGitTransportAuth | None = None,
) -> bool:
    """Create and checkout a fresh branch from origin/<base>.

    If the branch already exists locally (e.g. from a previous failed run),
    it is deleted and recreated so the worktree starts clean from origin/<base>.
    Returns False if the worktree cannot be switched to the branch (e.g. dirty
    state blocks checkout); the caller MUST treat this as a hard failure and
    not assume operations like commit/push will land on the intended branch.
    """
    fetched, fetch_error = _remote_run(["fetch", "origin", base], cwd, transport_auth, "fetch")
    if not fetched:
        log.error("create_branch: failed to refresh origin/%s: %s", base, fetch_error)
        return False

    # A missing local branch is the expected happy path, not a warning.
    branch_exists, _ = _run(["rev-parse", "--verify", f"refs/heads/{name}"], cwd, log_failure=False)
    if branch_exists:
        ok, err = _run(["checkout", base], cwd)
        if not ok:
            log.error(
                "create_branch: cannot switch to %s before recreating %s: %s", base, name, err
            )
            return False
        ok, err = _run(["branch", "-D", name], cwd)
        if not ok:
            log.error("create_branch: failed to delete stale branch %s: %s", name, err)
            return False

    ok, err = _run(["checkout", "-b", name, f"origin/{base}"], cwd)
    if not ok:
        log.error("create_branch: failed to create %s from origin/%s: %s", name, base, err)
        return False

    actual = current_branch(cwd)
    if actual != name:
        log.error("create_branch: post-condition failed — on %r instead of %r", actual, name)
        return False
    return True


def stage_files(files: list[str], cwd: Path | None = None) -> bool:
    """Stage files for commit. Empty list stages all changes."""
    if not files:
        ok, _ = _run(["add", "-A"], cwd)
        return ok
    ok, _ = _run(["add", "--", *files], cwd)
    return ok


def commit(
    message: str,
    cwd: Path | None = None,
    author_name: str | None = None,
    author_email: str | None = None,
) -> bool:
    """Create a commit with an explicit, non-authoritative service identity."""
    identity = _resolve_commit_identity(author_name, author_email)
    if identity is None:
        return False
    name, email = identity
    args = ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    args.extend(["commit", "-m", message])
    ok, _ = _run(args, cwd)
    return ok


def _resolve_commit_identity(
    author_name: str | None = None,
    author_email: str | None = None,
) -> tuple[str, str] | None:
    """Resolve one complete attribution pair without mixing configuration sources."""

    if author_name is not None or author_email is not None:
        name = (author_name or "").strip()
        email = (author_email or "").strip()
        source = "parameters"
    elif "SAMUEL_GIT_AUTHOR_NAME" in os.environ or "SAMUEL_GIT_AUTHOR_EMAIL" in os.environ:
        name = os.environ.get("SAMUEL_GIT_AUTHOR_NAME", "").strip()
        email = os.environ.get("SAMUEL_GIT_AUTHOR_EMAIL", "").strip()
        source = "environment"
    else:
        return DEFAULT_GIT_AUTHOR_NAME, DEFAULT_GIT_AUTHOR_EMAIL

    if not name or not email:
        log.error("Incomplete Git commit identity from %s", source)
        return None
    return name, email


def commit_tree_transaction(
    message: str,
    *,
    expected_parent: str,
    expected_tree: str,
    cwd: Path,
    author_name: str | None = None,
    author_email: str | None = None,
    signing_required: bool = False,
    signing_key: str | None = None,
) -> str:
    """Create a hook-free content-bound commit and atomically move HEAD.

    The caller persists the intent before entering this function.  Returning
    an empty string is fail-closed: no success may be inferred without the
    exact parent/tree postcondition and an atomic ref move.
    """

    if not _SHA_RE.fullmatch(expected_parent) or not _SHA_RE.fullmatch(expected_tree):
        log.error("commit_tree_transaction: invalid parent/tree identity")
        return ""
    if signing_required and not signing_key:
        log.error("commit_tree_transaction: signing required but no key configured")
        return ""
    if head_sha(cwd) != expected_parent or index_tree(cwd) != expected_tree:
        log.error("commit_tree_transaction: precondition changed before commit creation")
        return ""
    ok, ref = _run(["symbolic-ref", "-q", "HEAD"], cwd)
    if not ok or not ref.startswith("refs/heads/"):
        log.error("commit_tree_transaction: HEAD is not a local branch ref")
        return ""

    environment = git_process_environment()
    identity = _resolve_commit_identity(author_name, author_email)
    if identity is None:
        return ""
    name, email = identity
    environment.update(
        {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
    )
    args = ["git", "commit-tree", expected_tree, "-p", expected_parent]
    if signing_required:
        args.append(f"-S{signing_key}")
    try:
        created = subprocess.run(
            args,
            cwd=str(cwd),
            env=environment,
            input=message,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        log.error("commit_tree_transaction: commit-tree failed")
        return ""
    commit_sha = created.stdout.strip()
    if created.returncode != 0 or not _SHA_RE.fullmatch(commit_sha):
        log.error("commit_tree_transaction: commit-tree did not return a commit")
        return ""

    # Nothing may stage between write-tree and the ref move.  A content change
    # here leaves the newly created object unreachable and preserves the ref.
    if index_tree(cwd) != expected_tree or head_sha(cwd) != expected_parent:
        log.error("commit_tree_transaction: index or HEAD changed before ref move")
        return ""
    ref_exists, _ = _run(["show-ref", "--verify", "--quiet", ref], cwd, log_failure=False)
    transaction = (
        f"start\nupdate {ref} {commit_sha} {expected_parent}\nprepare\ncommit\n"
        if ref_exists
        else f"start\ncreate {ref} {commit_sha}\nprepare\ncommit\n"
    )
    try:
        moved = subprocess.run(
            ["git", "update-ref", "-m", "samuel: content-bound commit", "--stdin"],
            cwd=str(cwd),
            env=environment,
            input=transaction,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        log.error("commit_tree_transaction: update-ref failed")
        return ""
    if moved.returncode != 0:
        log.error("commit_tree_transaction: atomic ref move rejected")
        return ""
    if (
        head_sha(cwd) != commit_sha
        or revision_parent(cwd=cwd) != expected_parent
        or revision_tree(cwd=cwd) != expected_tree
        or not worktree_clean(cwd)
    ):
        log.error("commit_tree_transaction: postcondition mismatch")
        return ""
    return commit_sha


def push(
    branch: str,
    cwd: Path | None = None,
    *,
    transport_auth: IGitTransportAuth | None = None,
) -> bool:
    """Push branch to origin."""
    ok, _ = _remote_run(["push", "-u", "origin", branch], cwd, transport_auth, "push")
    return ok


def checkout(branch: str, cwd: Path | None = None) -> bool:
    """Checkout an existing branch."""
    ok, _ = _run(["checkout", branch], cwd)
    return ok


def changed_files(base: str = "main", cwd: Path | None = None) -> list[str]:
    """List files changed between origin/<base> and HEAD."""
    ok, out = _run(["diff", "--name-only", f"origin/{base}...HEAD"], cwd)
    if ok and out:
        return [f for f in out.split("\n") if f]
    return []


def diff_text(base: str = "main", cwd: Path | None = None) -> str:
    """Return the diff text between origin/<base> and HEAD."""
    ok, out = _run(["diff", f"origin/{base}...HEAD"], cwd)
    return out if ok else ""
