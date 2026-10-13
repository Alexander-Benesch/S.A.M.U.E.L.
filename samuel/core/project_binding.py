"""Read-only local project prerequisites; no clone, repair, bootstrap or authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from samuel.core import git
from samuel.core.errors import GitTransportAuthError
from samuel.core.git_remote import canonical_repository_url

PROJECT_BINDING_FILE = "project-binding.json"
PROJECT_BINDING_SCHEMA = "project-binding.v2"


def configured_project_root(config_dir: Path, raw: str | None = None) -> Path | None:
    value = (os.environ.get("PROJECT_ROOT", "") if raw is None else raw).strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else config_dir.resolve().parent / path


def regular_path(path: Path) -> bool:
    return not any(part.is_symlink() for part in (path, *path.parents))


def paths_overlap(left: Path, right: Path) -> bool:
    a, b = left.resolve(), right.resolve()
    return a == b or a in b.parents or b in a.parents


def project_overlay(source: str, target: str) -> str:
    # JSON quoted scalars are YAML scalars; accepted paths cannot expand Compose variables.
    return (
        "services:\n  samuel:\n    volumes:\n      - type: bind\n"
        f"        source: {json.dumps(source)}\n        target: {json.dumps(target)}\n"
        "        read_only: false\n        bind:\n          create_host_path: false\n"
    )


def validate_binding(value: Any) -> dict[str, Any]:
    fields = {
        "schema",
        "profile",
        "host_source",
        "container_target",
        "repository",
        "initial_revision",
        "uid",
        "gid",
        "installation_sha256",
        "compose_sha256",
        "source_identity",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("project registration schema is invalid")
    if value["schema"] != PROJECT_BINDING_SCHEMA or value["profile"] != "local-reference":
        raise ValueError("project registration profile is unsupported")
    for key in ("host_source", "container_target"):
        path = value[key]
        if (
            not isinstance(path, str)
            or re.fullmatch(r"/[A-Za-z0-9/._-]+", path) is None
            or str(Path(path)) != path
            or ".." in Path(path).parts
        ):
            raise ValueError("project registration requires canonical absolute paths")
    target = Path(value["container_target"])
    if any(
        paths_overlap(target, Path(p))
        for p in (
            "/app",
            "/samuel-workspaces",
            "/opt",
            "/run",
            "/proc",
            "/sys",
            "/dev",
            "/etc",
            "/usr",
            "/tmp",
            "/home",
            "/root",
            "/var",
            "/bin",
            "/sbin",
            "/lib",
            "/lib64",
        )
    ):
        raise ValueError("project mount overlaps a reserved runtime path")
    for key in ("uid", "gid"):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError("project runtime ownership is invalid")
    identity = value["source_identity"]
    if (
        not isinstance(identity, dict)
        or set(identity) != {"device", "inode"}
        or any(type(v) is not int or v < 0 for v in identity.values())
    ):
        raise ValueError("project filesystem identity is invalid")
    for key in ("installation_sha256", "compose_sha256"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise ValueError("project registration digest is invalid")
    if not isinstance(value["initial_revision"], str) or not re.fullmatch(
        r"[0-9a-f]{40}(?:[0-9a-f]{24})?", value["initial_revision"]
    ):
        raise ValueError("project registration needs a full initial commit")
    if (
        not isinstance(value["repository"], str)
        or canonical_repository_url(value["repository"]) != value["repository"]
    ):
        raise ValueError("project repository identity is not canonical")
    expected = hashlib.sha256(
        project_overlay(value["host_source"], value["container_target"]).encode()
    ).hexdigest()
    if value["compose_sha256"] != expected:
        raise ValueError("project registration mount digest differs")
    return value


def read_project_binding(config_dir: Path) -> dict[str, Any] | None:
    path = config_dir / PROJECT_BINDING_FILE
    if not path.exists() and not path.is_symlink():
        return None
    if not regular_path(path) or not path.is_file():
        raise ValueError("project registration is not a regular file")
    return validate_binding(json.loads(path.read_text(encoding="utf-8")))


def inspect_project(
    root: Path | None,
    *,
    repository: str | None = None,
    protected_roots: tuple[Path, ...] = (),
    binding: dict[str, Any] | None = None,
    expected_revision: str | None = None,
    required_binding: bool = False,
    check_runtime_identity: bool = True,
    check_mount_target: bool = True,
) -> dict[str, Any]:
    """Inspect metadata only. Permission observations do not attest locks or a sandbox."""
    result: dict[str, Any] = {
        "passed": False,
        "status": "blocked",
        "profile": "local-reference",
        "reason_code": "project_root_missing",
        "root": str(root) if root else "",
        "scope": "local_source_prerequisites",
        "active_io_qualified": False,
        "candidate_isolation_qualified": False,
        "registered": binding is not None,
    }

    def fail(code: str) -> dict[str, Any]:
        return {**result, "reason_code": code}

    try:
        if required_binding and binding is None:
            return fail("project_binding_missing")
        if root is None:
            return result
        if not regular_path(root) or not root.is_dir():
            return fail("project_path_unsafe_or_missing")
        if (binding is not None or required_binding) and any(
            paths_overlap(root, other) for other in protected_roots
        ):
            return fail("project_path_overlap")
        if binding is not None:
            validate_binding(binding)
            observed = root.stat()
            if {"device": observed.st_dev, "inode": observed.st_ino} != binding["source_identity"]:
                return fail("project_source_identity_changed")
            if check_mount_target and str(root) != binding["container_target"]:
                return fail("project_binding_root_mismatch")
            if check_mount_target and required_binding:
                mounted = False
                for line in Path("/proc/self/mountinfo").read_text().splitlines():
                    fields = line.split()
                    if len(fields) > 4 and fields[4] == str(root):
                        mounted = True
                        break
                if not mounted:
                    return fail("project_bind_mount_missing")
            if check_runtime_identity and (os.getuid(), os.getgid()) != (
                binding["uid"],
                binding["gid"],
            ):
                return fail("project_runtime_owner_mismatch")
            if repository is None or canonical_repository_url(repository) != binding["repository"]:
                return fail("project_binding_scm_mismatch")
        admin = root / ".git"
        if not admin.exists() or admin.is_symlink():
            return fail("project_git_missing_or_unsafe")
        if binding is not None:
            if not admin.is_dir() or (admin / "objects/info/alternates").exists():
                return fail("project_git_layout_unsupported")
            if any(
                not regular_path(admin / name) for name in ("objects", "refs", "config", "HEAD")
            ):
                return fail("project_git_layout_unsafe")
            if any(
                (p.stat().st_uid, p.stat().st_gid) != (binding["uid"], binding["gid"])
                for p in (root, admin)
            ):
                return fail("project_source_owner_mismatch")
            if any(p.stat().st_mode & 0o022 for p in (root, admin)):
                return fail("project_source_permissions_unsafe")
            if not all(
                os.access(p, os.R_OK | os.W_OK | os.X_OK, effective_ids=True) for p in (root, admin)
            ):
                return fail("project_git_not_writable")
            if os.statvfs(root).f_flag & getattr(os, "ST_RDONLY", 1):
                return fail("project_mount_read_only")
        environment = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_PARAMETERS": "",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "core.hooksPath",
            "GIT_CONFIG_VALUE_1": os.devnull,
        }

        def read(args: list[str]) -> tuple[bool, str]:
            return git._run(
                args, root, log_failure=False, environment=environment, strip_path_overrides=True
            )

        if binding is not None:
            ok, top = read(["rev-parse", "--show-toplevel"])
            common_ok, common = read(["rev-parse", "--git-common-dir"])
            if (
                not ok
                or Path(top).resolve() != root.resolve()
                or not common_ok
                or (root / common).resolve() != admin.resolve()
            ):
                return fail("project_git_layout_unsupported")
        ok, head = read(["rev-parse", "--verify", "HEAD^{commit}"])
        if not ok or not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", head):
            return fail("project_revision_unavailable")
        result["observed_revision"] = head
        if expected_revision is not None and head != expected_revision:
            return fail("project_initial_revision_mismatch")
        if expected_revision is not None:
            clean, paths = read(["ls-files", "--modified", "--deleted", "--others"])
            staged, _ = read(["diff-index", "--cached", "--quiet", "--no-ext-diff", "HEAD", "--"])
            if not clean or paths or not staged:
                return fail("project_initial_checkout_dirty")
        if repository is not None:
            ok, origin = read(["remote", "get-url", "--all", "origin"])
            if not ok or canonical_repository_url(origin) != canonical_repository_url(repository):
                return fail("project_origin_mismatch")
            ok, push_origin = read(["remote", "get-url", "--push", "--all", "origin"])
            if not ok or canonical_repository_url(push_origin) != canonical_repository_url(
                repository
            ):
                return fail("project_push_origin_mismatch")
            result["repository"] = canonical_repository_url(repository)
        result.update(passed=True, status="ready", reason_code="project_source_observed")
        return result
    except (ValueError, OSError, GitTransportAuthError):
        return fail("project_inspection_unavailable")


def project_readiness(
    config_dir: Path,
    *,
    root: Path | None,
    repository: str | None,
    protected_roots: tuple[Path, ...] = (),
) -> dict[str, Any]:
    try:
        binding = read_project_binding(config_dir)
    except (OSError, ValueError, GitTransportAuthError):
        return {"passed": False, "status": "blocked", "reason_code": "project_binding_invalid"}
    return inspect_project(
        root,
        repository=repository,
        protected_roots=protected_roots,
        binding=binding,
        required_binding=os.environ.get("SAMUEL_PROJECT_BINDING_REQUIRED") == "1",
    )
