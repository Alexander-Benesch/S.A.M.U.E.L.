"""Shared Git worktree manager for mutable runs and bound verification."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Literal, cast

from samuel.core.command_safety import validate_command_args
from samuel.core.errors import GitTransportAuthError
from samuel.core.git import (
    GIT_PATH_OVERRIDE_KEYS,
    git_process_environment,
)
from samuel.core.ports import IGitTransportAuth, IWorkspaceManager
from samuel.core.workspaces import WorkspaceError, WorkspaceHandle, WorkspaceRecord

try:
    import fcntl
except ImportError:  # pragma: no cover - the supported manager requires POSIX locks
    fcntl = None  # type: ignore[assignment]


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
_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_NETWORK_FILESYSTEMS = frozenset({"9p", "cifs", "fuse.sshfs", "nfs", "nfs4", "smb3"})


def resolve_work_dir(raw: str | Path, *, config_dir: str | Path | None = None) -> Path:
    """Resolve a dedicated workspace root next to, but not inside, runtime state."""

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute() and config_dir is not None:
        candidate = Path(config_dir).expanduser().resolve(strict=False).parent / candidate
    return candidate.resolve(strict=False)


def read_workspace_registry(work_dir: str | Path) -> list[WorkspaceRecord]:
    """Read an existing workspace registry without creating files or directories."""

    database = Path(work_dir).expanduser().resolve(strict=False) / "workspaces.sqlite3"
    if not database.is_file() or database.is_symlink():
        return []
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM workspaces ORDER BY created_at, workspace_id"
        ).fetchall()
    except sqlite3.Error as exc:
        raise WorkspaceError(
            "workspace_registry_unreadable",
            "Workspace registry could not be read without mutation",
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    try:
        return [WorkspaceRecord(**dict(row)) for row in rows]
    except (TypeError, ValueError) as exc:
        raise WorkspaceError(
            "workspace_registry_invalid",
            "Workspace registry contains an unsupported record shape",
        ) from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _slug(value: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")[:40] or "workspace"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{readable}-{digest}"


def _mount_type(path: Path) -> str:
    """Return the Linux filesystem type covering ``path`` or fail closed."""

    try:
        rows = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise WorkspaceError(
            "workspace_filesystem_unknown",
            "Workspace filesystem could not be classified",
        ) from exc
    target = path.resolve(strict=False)
    matches: list[tuple[int, str]] = []
    for row in rows:
        left, marker, right = row.partition(" - ")
        left_fields = left.split()
        right_fields = right.split()
        if not marker or len(left_fields) < 5 or not right_fields:
            continue
        mount = Path(
            re.sub(
                r"\\([0-7]{3})",
                lambda item: chr(int(item.group(1), 8)),
                left_fields[4],
            )
        ).resolve(strict=False)
        if target == mount or mount in target.parents:
            matches.append((len(mount.parts), right_fields[0].lower()))
    if not matches:
        raise WorkspaceError(
            "workspace_filesystem_unknown",
            "Workspace filesystem could not be classified",
        )
    return max(matches)[1]


class GitWorktreeManager(IWorkspaceManager):
    """Own linked worktrees and their process-independent registry.

    The manager provides checkout containment and ownership only.  Candidate
    processes keep the caller's OS privileges unless a separate sandbox is
    configured.
    """

    def __init__(
        self,
        work_dir: str | Path,
        *,
        data_dir: str | Path | None = None,
        reserve_bytes: int = 128 * 1024 * 1024,
        minimum_free_bytes: int = 512 * 1024 * 1024,
        quarantine_max_count: int = 8,
        quarantine_max_bytes: int = 2 * 1024 * 1024 * 1024,
        quarantine_retention_hours: int = 168,
        git_timeout: int = 60,
        transport_auth: IGitTransportAuth | None = None,
    ) -> None:
        if fcntl is None:
            raise WorkspaceError(
                "workspace_lock_unsupported",
                "The worktree manager requires POSIX flock support",
            )
        if any(os.environ.get(name) for name in GIT_PATH_OVERRIDE_KEYS):
            raise WorkspaceError(
                "workspace_git_environment_unsafe",
                "Dangerous Git path overrides must be removed before startup",
            )
        self.work_dir = Path(work_dir).expanduser().resolve(strict=False)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.chmod(0o700)
        if data_dir is not None:
            resolved_data_dir = Path(data_dir).expanduser().resolve(strict=False)
            if (
                self.work_dir == resolved_data_dir
                or self.work_dir in resolved_data_dir.parents
                or resolved_data_dir in self.work_dir.parents
            ):
                raise WorkspaceError(
                    "workspace_state_overlap",
                    "Workspace and runtime-state directories must be separate",
                )
        filesystem = _mount_type(self.work_dir)
        if filesystem in _NETWORK_FILESYSTEMS:
            raise WorkspaceError(
                "workspace_filesystem_remote",
                f"Workspace filesystem {filesystem!r} is not supported",
            )
        if (
            isinstance(reserve_bytes, bool)
            or int(reserve_bytes) <= 0
            or isinstance(minimum_free_bytes, bool)
            or int(minimum_free_bytes) < 0
            or isinstance(quarantine_max_count, bool)
            or int(quarantine_max_count) <= 0
            or isinstance(quarantine_max_bytes, bool)
            or int(quarantine_max_bytes) <= 0
            or isinstance(quarantine_retention_hours, bool)
            or int(quarantine_retention_hours) <= 0
            or isinstance(git_timeout, bool)
            or int(git_timeout) <= 0
        ):
            raise WorkspaceError(
                "workspace_configuration_invalid",
                "Workspace limits must be positive integers; minimum free space may be zero",
            )
        self._reserve_bytes = int(reserve_bytes)
        self._minimum_free_bytes = int(minimum_free_bytes)
        self._quarantine_max_count = int(quarantine_max_count)
        self._quarantine_max_bytes = int(quarantine_max_bytes)
        self._quarantine_retention_hours = int(quarantine_retention_hours)
        self._git_timeout = int(git_timeout)
        self._transport_auth = transport_auth
        self._db_path = self.work_dir / "workspaces.sqlite3"
        self._manager_lock_path = self.work_dir / ".manager.lock"
        self._lock_dir = self.work_dir / "locks"
        self._tree_dir = self.work_dir / "trees"
        self._lock_dir.mkdir(mode=0o700, exist_ok=True)
        self._tree_dir.mkdir(mode=0o700, exist_ok=True)
        self._held_locks: dict[str, IO[bytes]] = {}
        self._lease_counts: dict[str, int] = {}
        self._initialize_registry()

    @staticmethod
    def _environment(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        return git_process_environment(overrides, strip_path_overrides=True)

    def _git(
        self,
        args: list[str],
        cwd: Path,
        *,
        timeout: int | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> str:
        safety = validate_command_args(["git", *args])
        if not safety["safe"]:
            raise WorkspaceError(
                "workspace_git_command_blocked",
                "Workspace Git operation was blocked by command policy",
            )
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(cwd),
                env=self._environment(environment),
                capture_output=True,
                text=True,
                timeout=timeout or self._git_timeout,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkspaceError(
                "workspace_git_failed",
                "Workspace Git operation could not complete",
            ) from exc
        if result.returncode != 0:
            raise WorkspaceError(
                "workspace_git_failed",
                "Workspace Git operation could not complete",
            )
        return result.stdout.strip()

    def _remote_git(
        self,
        args: list[str],
        cwd: Path,
        *,
        operation: Literal["fetch", "push"],
    ) -> str:
        remote_url = self._git(["remote", "get-url", "origin"], cwd)
        try:
            if self._transport_auth is None:
                return self._git(args, cwd, environment=_CREDENTIAL_FREE_NETWORK_ENV)
            with self._transport_auth.environment(remote_url, operation) as environment:
                return self._git(args, cwd, environment=environment)
        except GitTransportAuthError as exc:
            raise WorkspaceError(exc.code, exc.safe_message) from exc

    def _create_branch_ref(self, repository_root: Path, branch: str, head_sha: str) -> None:
        if not _SHA_RE.fullmatch(head_sha):
            raise WorkspaceError(
                "workspace_head_invalid",
                "Run-worktree branch base is not an immutable revision",
            )
        normalized = self._git(["check-ref-format", "--branch", branch], repository_root)
        if normalized != branch or any(char in branch for char in "\r\n\0"):
            raise WorkspaceError(
                "workspace_branch_invalid",
                "Run-worktree branch name is not canonical",
            )
        ref = f"refs/heads/{branch}"
        transaction = f"start\ncreate {ref} {head_sha}\nprepare\ncommit\n"
        try:
            created = subprocess.run(
                [
                    "git",
                    "update-ref",
                    "-m",
                    "samuel: create run-worktree branch",
                    "--stdin",
                ],
                cwd=str(repository_root),
                env=self._environment(),
                input=transaction,
                capture_output=True,
                text=True,
                timeout=self._git_timeout,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkspaceError(
                "workspace_git_failed",
                "Workspace branch creation could not complete",
            ) from exc
        if created.returncode != 0 or self._git(["rev-parse", ref], repository_root) != head_sha:
            raise WorkspaceError(
                "workspace_git_failed",
                "Workspace branch creation could not complete",
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize_registry(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    profile TEXT NOT NULL CHECK(profile IN ('run', 'verification')),
                    repository_root TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    branch TEXT NOT NULL,
                    head_sha TEXT NOT NULL,
                    base_ref TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('creating', 'active', 'terminal', 'quarantined')),
                    reserved_bytes INTEGER NOT NULL,
                    owner_pid INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    quarantine_until TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(workspaces)")}
            if "quarantine_until" not in columns:
                connection.execute(
                    "ALTER TABLE workspaces ADD COLUMN quarantine_until TEXT NOT NULL DEFAULT ''"
                )

    @contextmanager
    def _manager_lock(self) -> Iterator[None]:
        lock = self._manager_lock_path.open("a+b")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def _resource_lock(self, key: str, workspace_id: str) -> None:
        path = self._lock_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.lock"
        lock = path.open("a+b")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock.close()
            raise WorkspaceError(
                "workspace_owned",
                "The requested branch or workspace is owned by another process",
            ) from exc
        self._held_locks[workspace_id] = lock
        self._lease_counts[workspace_id] = 1

    def _unlock(self, workspace_id: str) -> None:
        self._lease_counts.pop(workspace_id, None)
        lock = self._held_locks.pop(workspace_id, None)
        if lock is None:
            return
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()

    def _row(self, workspace_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM workspaces WHERE workspace_id = ?",
                    (workspace_id,),
                ).fetchone(),
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(**dict(row))

    def _capacity_preflight(self, connection: sqlite3.Connection) -> None:
        quarantined = connection.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(reserved_bytes), 0) AS bytes "
            "FROM workspaces WHERE status = 'quarantined'"
        ).fetchone()
        if (
            int(quarantined["count"]) >= self._quarantine_max_count
            or int(quarantined["bytes"]) + self._reserve_bytes > self._quarantine_max_bytes
        ):
            raise WorkspaceError(
                "workspace_quarantine_capacity",
                "Workspace quarantine capacity is exhausted; no new run may start",
            )
        active_reserved = int(
            connection.execute(
                "SELECT COALESCE(SUM(reserved_bytes), 0) FROM workspaces "
                "WHERE status IN ('creating', 'active')"
            ).fetchone()[0]
        )
        free = shutil.disk_usage(self.work_dir).free
        if free - active_reserved - self._reserve_bytes < self._minimum_free_bytes:
            raise WorkspaceError(
                "workspace_capacity_insufficient",
                "Workspace capacity preflight failed before candidate mutation",
            )

    def _prepare_row(
        self,
        *,
        workspace_id: str,
        profile: str,
        repository_root: Path,
        path: Path,
        branch: str,
        head_sha: str,
        base_ref: str,
    ) -> str:
        now = _utc_now()
        with self._manager_lock(), self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT status FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
            if existing is not None:
                if existing["status"] == "terminal":
                    connection.execute(
                        "DELETE FROM workspaces WHERE workspace_id = ?",
                        (workspace_id,),
                    )
                else:
                    connection.execute("ROLLBACK")
                    raise WorkspaceError(
                        "workspace_exists",
                        "Workspace identity already exists and requires operator inspection",
                    )
            self._capacity_preflight(connection)
            connection.execute(
                "INSERT INTO workspaces (workspace_id, profile, repository_root, path, branch, "
                "head_sha, base_ref, status, reserved_bytes, owner_pid, created_at, updated_at, "
                "quarantine_until, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'creating', ?, ?, ?, ?, '', '')",
                (
                    workspace_id,
                    profile,
                    str(repository_root),
                    str(path),
                    branch,
                    head_sha,
                    base_ref,
                    self._reserve_bytes,
                    os.getpid(),
                    now,
                    now,
                ),
            )
            connection.execute("COMMIT")
        return now

    def _activate(self, workspace_id: str, head_sha: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE workspaces SET status='active', head_sha=?, updated_at=? "
                "WHERE workspace_id=? AND status='creating'",
                (head_sha, _utc_now(), workspace_id),
            )

    def _drop_failed(self, workspace_id: str, repository_root: Path, path: Path) -> None:
        try:
            if path.exists():
                self._git(["worktree", "remove", "--force", str(path)], repository_root)
        except WorkspaceError:
            pass
        with self._connect() as connection:
            connection.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        self._unlock(workspace_id)

    def _validate_repository_boundary(self, repository_root: Path) -> Path:
        root = repository_root.expanduser().resolve(strict=True)
        if not (root / ".git").exists():
            raise WorkspaceError("workspace_repository_invalid", "Target is not a Git worktree")
        if self.work_dir == root or root in self.work_dir.parents or self.work_dir in root.parents:
            raise WorkspaceError(
                "workspace_path_overlap",
                "Workspace storage must be outside the target repository",
            )
        return root

    def acquire_run(
        self,
        *,
        repository_root: Path,
        workspace_id: str,
        branch: str,
        base_ref: str,
        expected_head: str = "",
        expected_base_sha: str = "",
    ) -> WorkspaceHandle:
        root = self._validate_repository_boundary(repository_root)
        if workspace_id in self._held_locks:
            row = self._row(workspace_id)
            if (
                row is None
                or row["status"] != "active"
                or row["profile"] != "run"
                or Path(row["repository_root"]) != root
                or row["branch"] != branch
            ):
                raise WorkspaceError(
                    "workspace_reentry_mismatch",
                    "Active workspace does not match the requested healing continuation",
                )
            path = Path(row["path"])
            observed_head = self._git(["rev-parse", "HEAD"], path)
            observed_branch = self._git(["branch", "--show-current"], path)
            dirty = self._git(["status", "--porcelain"], path)
            if (
                observed_branch != branch
                or dirty
                or (expected_head and observed_head != expected_head)
            ):
                raise WorkspaceError(
                    "workspace_reentry_precondition_failed",
                    "Run-worktree cannot be reused for the bound healing continuation",
                )
            self._lease_counts[workspace_id] += 1
            with self._connect() as connection:
                connection.execute(
                    "UPDATE workspaces SET head_sha=?, updated_at=? WHERE workspace_id=?",
                    (observed_head, _utc_now(), workspace_id),
                )
            return WorkspaceHandle(
                workspace_id=workspace_id,
                profile="run",
                repository_root=root,
                path=path,
                branch=branch,
                head_sha=observed_head,
                base_ref=str(row["base_ref"]),
                created_at=str(row["created_at"]),
            )
        resource_key = f"run\0{root}\0{branch}"
        self._resource_lock(resource_key, workspace_id)
        path = self._tree_dir / "run" / _slug(workspace_id)
        try:
            created_at = self._prepare_row(
                workspace_id=workspace_id,
                profile="run",
                repository_root=root,
                path=path,
                branch=branch,
                head_sha=expected_head,
                base_ref=base_ref,
            )
            path.parent.mkdir(mode=0o700, exist_ok=True)
            if expected_base_sha and not _SHA_RE.fullmatch(expected_base_sha):
                raise WorkspaceError(
                    "workspace_base_invalid",
                    "Expected base is not an immutable revision",
                )
            if expected_head:
                if not _SHA_RE.fullmatch(expected_head):
                    raise WorkspaceError(
                        "workspace_head_invalid",
                        "Expected healing head is not an immutable revision",
                    )
                self._remote_git(["fetch", "origin", branch], root, operation="fetch")
                observed = self._git(["rev-parse", f"origin/{branch}"], root)
                if observed != expected_head:
                    raise WorkspaceError(
                        "workspace_head_changed",
                        "Remote candidate no longer matches the expected healing head",
                    )
                local_exists = (
                    subprocess.run(
                        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                        cwd=str(root),
                        env=self._environment(),
                        timeout=self._git_timeout,
                        check=False,
                    ).returncode
                    == 0
                )
                if local_exists:
                    self._git(["branch", "-f", branch, expected_head], root)
                    self._git(["worktree", "add", str(path), branch], root)
                else:
                    self._create_branch_ref(root, branch, expected_head)
                    self._git(["worktree", "add", str(path), branch], root)
            else:
                self._remote_git(["fetch", "origin", base_ref], root, operation="fetch")
                local_exists = (
                    subprocess.run(
                        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                        cwd=str(root),
                        env=self._environment(),
                        timeout=self._git_timeout,
                        check=False,
                    ).returncode
                    == 0
                )
                if local_exists:
                    self._git(["branch", "-D", branch], root)
                base_head = self._git(["rev-parse", f"origin/{base_ref}"], root)
                if expected_base_sha and base_head != expected_base_sha:
                    raise WorkspaceError(
                        "workspace_base_changed",
                        "Remote base no longer matches the approved planning snapshot",
                    )
                self._create_branch_ref(root, branch, base_head)
                self._git(["worktree", "add", str(path), branch], root)
            observed_head = self._git(["rev-parse", "HEAD"], path)
            observed_branch = self._git(["branch", "--show-current"], path)
            if observed_branch != branch or (expected_head and observed_head != expected_head):
                raise WorkspaceError(
                    "workspace_postcondition_failed",
                    "Run-worktree does not match the requested branch and revision",
                )
            self._activate(workspace_id, observed_head)
            return WorkspaceHandle(
                workspace_id=workspace_id,
                profile="run",
                repository_root=root,
                path=path,
                branch=branch,
                head_sha=observed_head,
                base_ref=base_ref,
                created_at=created_at,
            )
        except BaseException:
            self._drop_failed(workspace_id, root, path)
            raise

    def acquire_verification(
        self,
        *,
        repository_root: Path,
        workspace_id: str,
        head_sha: str,
        base_ref: str = "",
    ) -> WorkspaceHandle:
        root = self._validate_repository_boundary(repository_root)
        if not _SHA_RE.fullmatch(head_sha):
            raise WorkspaceError(
                "workspace_head_invalid",
                "Verification head is not an immutable revision",
            )
        self._resource_lock(f"verification\0{root}\0{workspace_id}", workspace_id)
        path = self._tree_dir / "verification" / _slug(workspace_id)
        try:
            if base_ref:
                self._remote_git(["fetch", "origin", base_ref], root, operation="fetch")
                observed_base = self._git(["rev-parse", f"origin/{base_ref}"], root)
                if observed_base != head_sha:
                    raise WorkspaceError(
                        "workspace_base_changed",
                        "Remote base does not match the requested planning snapshot",
                    )
            created_at = self._prepare_row(
                workspace_id=workspace_id,
                profile="verification",
                repository_root=root,
                path=path,
                branch="",
                head_sha=head_sha,
                base_ref="",
            )
            path.parent.mkdir(mode=0o700, exist_ok=True)
            self._git(["worktree", "add", "--detach", str(path), head_sha], root)
            observed = self._git(["rev-parse", "HEAD"], path)
            if observed != head_sha:
                raise WorkspaceError(
                    "workspace_postcondition_failed",
                    "Verification worktree does not match the requested revision",
                )
            self._activate(workspace_id, observed)
            return WorkspaceHandle(
                workspace_id=workspace_id,
                profile="verification",
                repository_root=root,
                path=path,
                branch="",
                head_sha=observed,
                base_ref="",
                created_at=created_at,
            )
        except BaseException:
            self._drop_failed(workspace_id, root, path)
            raise

    def acquire_existing_run(
        self,
        *,
        repository_root: Path,
        workspace_id: str,
        branch: str,
    ) -> WorkspaceHandle:
        root = self._validate_repository_boundary(repository_root)
        row = self._row(workspace_id)
        if (
            row is None
            or row["profile"] != "run"
            or row["status"] not in {"active", "creating"}
            or Path(row["repository_root"]) != root
            or str(row["branch"]) != branch
        ):
            raise WorkspaceError(
                "workspace_resume_identity_mismatch",
                "Existing run-worktree does not match the bound resume identity",
            )
        self._resource_lock(f"run\0{root}\0{branch}", workspace_id)
        try:
            path = Path(row["path"])
            if not path.is_dir():
                raise WorkspaceError(
                    "workspace_resume_missing",
                    "Bound run-worktree is no longer present",
                )
            observed_branch = self._git(["branch", "--show-current"], path)
            observed_head = self._git(["rev-parse", "HEAD"], path)
            if observed_branch != branch:
                raise WorkspaceError(
                    "workspace_resume_branch_mismatch",
                    "Run-worktree branch no longer matches its registry binding",
                )
            return WorkspaceHandle(
                workspace_id=workspace_id,
                profile="run",
                repository_root=root,
                path=path,
                branch=branch,
                head_sha=observed_head,
                base_ref=str(row["base_ref"]),
                created_at=str(row["created_at"]),
            )
        except BaseException:
            self._unlock(workspace_id)
            raise

    def detach(self, workspace_id: str) -> None:
        """Release only this process' ownership; preserve resumable evidence."""

        self._unlock(workspace_id)

    def release(self, workspace_id: str) -> None:
        leases = self._lease_counts.get(workspace_id, 0)
        if leases > 1:
            self._lease_counts[workspace_id] = leases - 1
            return
        row = self._row(workspace_id)
        if row is None:
            self._unlock(workspace_id)
            return
        record = self._record(row)
        if record.status == "quarantined":
            self._unlock(workspace_id)
            return
        root = Path(record.repository_root)
        path = Path(record.path)
        try:
            if path.exists():
                self._git(["worktree", "remove", "--force", str(path)], root)
            with self._connect() as connection:
                connection.execute(
                    "UPDATE workspaces SET status='terminal', updated_at=? WHERE workspace_id=?",
                    (_utc_now(), workspace_id),
                )
        finally:
            self._unlock(workspace_id)

    def quarantine(self, workspace_id: str, *, reason: str) -> None:
        if workspace_id not in self._held_locks:
            row = self._row(workspace_id)
            if row is None:
                raise WorkspaceError("workspace_missing", "Workspace identity was not found")
            key = (
                f"run\0{row['repository_root']}\0{row['branch']}"
                if row["profile"] == "run"
                else f"verification\0{row['repository_root']}\0{row['workspace_id']}"
            )
            self._resource_lock(key, workspace_id)
        now = datetime.now(timezone.utc)
        quarantine_until = now + timedelta(hours=self._quarantine_retention_hours)
        with self._connect() as connection:
            connection.execute(
                "UPDATE workspaces SET status='quarantined', reason=?, updated_at=?, "
                "quarantine_until=? "
                "WHERE workspace_id=? AND status IN ('creating', 'active')",
                (
                    reason[:120],
                    now.isoformat(timespec="microseconds"),
                    quarantine_until.isoformat(timespec="microseconds"),
                    workspace_id,
                ),
            )
        self._unlock(workspace_id)

    def discard_quarantine(self, workspace_id: str, *, reason: str) -> None:
        if not reason.strip():
            raise WorkspaceError(
                "workspace_discard_reason_required",
                "Discarding quarantined evidence requires an operator reason",
            )
        row = self._row(workspace_id)
        if row is None or row["status"] != "quarantined":
            raise WorkspaceError(
                "workspace_not_quarantined",
                "Only a quarantined workspace may be explicitly discarded",
            )
        key = (
            f"run\0{row['repository_root']}\0{row['branch']}"
            if row["profile"] == "run"
            else f"verification\0{row['repository_root']}\0{row['workspace_id']}"
        )
        self._resource_lock(key, workspace_id)
        try:
            path = Path(row["path"])
            if path.exists():
                self._git(
                    ["worktree", "remove", "--force", str(path)],
                    Path(row["repository_root"]),
                )
            with self._connect() as connection:
                connection.execute(
                    "UPDATE workspaces SET status='terminal', reason=?, updated_at=? "
                    "WHERE workspace_id=? AND status='quarantined'",
                    (f"operator_discard:{reason.strip()[:100]}", _utc_now(), workspace_id),
                )
        finally:
            self._unlock(workspace_id)

    def list_workspaces(self) -> list[WorkspaceRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workspaces ORDER BY created_at, workspace_id"
            ).fetchall()
        return [self._record(row) for row in rows]

    def inspect(self, workspace_id: str) -> WorkspaceRecord | None:
        row = self._row(workspace_id)
        return self._record(row) if row is not None else None

    def prune(self) -> dict[str, int]:
        removed_trees = 0
        removed_records = 0
        repositories: set[Path] = set()
        with self._manager_lock():
            for record in self.list_workspaces():
                repositories.add(Path(record.repository_root))
                if record.status != "terminal":
                    continue
                path = Path(record.path)
                if path.exists():
                    self._git(
                        ["worktree", "remove", "--force", str(path)],
                        Path(record.repository_root),
                    )
                    removed_trees += 1
                with self._connect() as connection:
                    connection.execute(
                        "DELETE FROM workspaces WHERE workspace_id=? AND status='terminal'",
                        (record.workspace_id,),
                    )
                    removed_records += 1
            records = self.list_workspaces()
            protected_missing = any(
                record.status in {"active", "quarantined"} and not Path(record.path).exists()
                for record in records
            )
            if not protected_missing:
                for repository in repositories:
                    self._git(["worktree", "prune"], repository)
        return {"trees_removed": removed_trees, "records_removed": removed_records}
