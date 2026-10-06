"""Versioned local SQLite adapter for passive runtime-state foundations."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from samuel.core.ports import (
    IAuthorityStateStore,
    IIdentityStateStore,
    IObservationStore,
    IQualityMetricsRegistry,
    IRetentionExecutionStore,
    IRetentionStateStore,
    IRunProjectionStore,
    IStateDiagnostics,
)
from samuel.core.retention import RetentionError, retention_plan_digest
from samuel.core.state import (
    AuthorityLeaseRecord,
    AuthorityRecord,
    AuthorityWriteResult,
    EvaluationTerminalRecord,
    HealingClaimRecord,
    LLMBudgetAttemptRecord,
    ManagedBackupRecord,
    ObservationRecord,
    OperationIntentRecord,
    PlanningClarificationRecord,
    ReconcileEntryRecord,
    RestoreOperationRecord,
    RetentionCategoryStateRecord,
    RetentionExecutionRecord,
    RetentionTableSnapshot,
    RunProjectionRecord,
    ScoreDerivationRecord,
    StateStoreConflict,
    StateStoreError,
    StateStoreStatus,
    WorkflowBudgetAdmissionRecord,
    WorkflowCheckpointRecord,
)

SCHEMA_VERSION = 10
DATABASE_FILENAME = "samuel-state.sqlite3"
AUTHORITY_WITNESS_FILENAME = "samuel-state-authority.json"
AUTHORITY_WITNESS_LOCK_FILENAME = ".samuel-state-authority.lock"
STATE_LIFECYCLE_LOCK_FILENAME = ".samuel-state-lifecycle.lock"
RESTORE_SENTINEL_FILENAME = "samuel-state-restore.json"
_MOUNTINFO_PATH = Path("/proc/self/mountinfo")
_LOCAL_FILESYSTEMS = frozenset(
    {
        "aufs",
        "btrfs",
        "exfat",
        "ext2",
        "ext3",
        "ext4",
        "f2fs",
        "fuseblk",
        "overlay",
        "ramfs",
        "rootfs",
        "tmpfs",
        "vfat",
        "xfs",
        "zfs",
    }
)
_NETWORK_FILESYSTEMS = frozenset(
    {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "fuse.sshfs",
        "glusterfs",
        "nfs",
        "nfs4",
        "smb3",
    }
)
_EXPECTED_TABLES = (
    "authority_leases",
    "authority_metadata",
    "authority_records",
    "evaluation_terminals",
    "healing_claims",
    "identity_metadata",
    "identity_principal_roles",
    "identity_principals",
    "identity_sessions",
    "identity_tokens",
    "legacy_imports",
    "llm_budget_attempts",
    "managed_backups",
    "observations",
    "operation_intents",
    "planning_clarifications",
    "quality_metrics",
    "reconcile_entries",
    "restore_operations",
    "retention_category_states",
    "retention_executions",
    "run_projections",
    "schema_migrations",
    "score_derivations",
    "workflow_budget_admissions",
    "workflow_checkpoints",
)
_MOUNT_ESCAPE = re.compile(r"\\([0-7]{3})")
_SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _unescape_mountinfo(value: str) -> str:
    return _MOUNT_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)


def _filesystem_for(path: Path, *, mountinfo_path: Path = _MOUNTINFO_PATH) -> tuple[str, Path]:
    """Resolve one path to an allowlisted local mount.

    Linux mountinfo is the authoritative source for the reference adapter.  A
    missing, unparsable or unknown filesystem is rejected rather than guessed.
    """

    target = path.expanduser().resolve(strict=False)
    try:
        lines = mountinfo_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise StateStoreError(
            "state_filesystem_unknown",
            "Runtime-state filesystem could not be classified as local",
        ) from exc

    candidates: list[tuple[Path, str]] = []
    for line in lines:
        left, separator, right = line.partition(" - ")
        left_fields = left.split()
        right_fields = right.split()
        if not separator or len(left_fields) < 5 or not right_fields:
            continue
        mount = Path(_unescape_mountinfo(left_fields[4])).resolve(strict=False)
        if target == mount or mount in target.parents:
            candidates.append((mount, right_fields[0].lower()))
    if not candidates:
        raise StateStoreError(
            "state_filesystem_unknown",
            "Runtime-state filesystem could not be classified as local",
        )

    mount, filesystem_type = max(candidates, key=lambda item: len(item[0].parts))
    if filesystem_type in _NETWORK_FILESYSTEMS:
        raise StateStoreError(
            "state_filesystem_remote",
            f"Runtime-state filesystem {filesystem_type!r} is not supported",
        )
    if filesystem_type not in _LOCAL_FILESYSTEMS:
        raise StateStoreError(
            "state_filesystem_unknown",
            f"Runtime-state filesystem {filesystem_type!r} is not classified as local",
        )
    return filesystem_type, mount


def resolve_data_dir(raw: str | Path, *, config_dir: str | Path | None = None) -> Path:
    """Normalize ``agent.data_dir`` without introducing a second config source.

    Absolute operator paths remain unchanged.  Relative values are rooted next
    to the selected config directory, matching the shipped ``config/`` +
    ``data/`` layout even when the installed CLI is started elsewhere.
    """

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute() and config_dir is not None:
        candidate = Path(config_dir).expanduser().resolve(strict=False).parent / candidate
    return candidate.resolve(strict=False)


def _json(value: dict[str, Any] | list[Any]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise StateStoreError(
            "state_payload_invalid",
            "Runtime-state payload is not canonical JSON",
        ) from exc


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise StateStoreError(
            "state_timestamp_invalid",
            "Runtime-state timestamps must be timezone-aware UTC values",
        )
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _from_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def audit_authority_high_watermark(paths: list[Path]) -> int:
    """Best-effort supplemental epoch from JSONL audit files and rotations."""

    maximum = 0

    def visit(value: Any) -> None:
        nonlocal maximum
        if isinstance(value, dict):
            epoch = value.get("authority_epoch")
            if isinstance(epoch, int) and not isinstance(epoch, bool) and epoch >= 0:
                maximum = max(maximum, epoch)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    for configured in paths:
        candidates = [configured, *sorted(configured.parent.glob(f"{configured.name}.*"))]
        for candidate in candidates:
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                with candidate.open(encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            visit(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue
    return maximum


def _translate_sqlite_error(exc: BaseException) -> StateStoreError:
    message = str(exc).lower()
    if "locked" in message or "busy" in message:
        return StateStoreError("state_locked", "Runtime-state database is locked or busy")
    if "readonly" in message or "read-only" in message:
        return StateStoreError("state_readonly", "Runtime-state database is read-only")
    if "malformed" in message or "not a database" in message or "file is encrypted" in message:
        return StateStoreError("state_corrupt", "Runtime-state database is corrupt or unreadable")
    return StateStoreError("state_io_error", "Runtime-state database operation failed")


class SQLiteStateStore(IStateDiagnostics):
    """Own one SQLite schema and expose semantics-specific port views."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        config_dir: str | Path | None = None,
        mountinfo_path: Path = _MOUNTINFO_PATH,
        timeout: float = 1.0,
    ) -> None:
        self.data_dir = resolve_data_dir(data_dir, config_dir=config_dir)
        self.path = self.data_dir / DATABASE_FILENAME
        self.authority_witness_path = self.data_dir / AUTHORITY_WITNESS_FILENAME
        self.lifecycle_lock_path = self.data_dir / STATE_LIFECYCLE_LOCK_FILENAME
        self.restore_sentinel_path = self.data_dir / RESTORE_SENTINEL_FILENAME
        self._timeout = timeout
        self._projection_error_code: str | None = None
        self._filesystem_type, self._filesystem_mount = _filesystem_for(
            self.data_dir,
            mountinfo_path=mountinfo_path,
        )
        self._initialize()
        self.observations: IObservationStore = SQLiteObservationStore(self)
        self.projections: IRunProjectionStore = SQLiteRunProjectionStore(self)
        self.quality_metrics: IQualityMetricsRegistry = SQLiteQualityMetricsRegistry(self)
        self.authority: IAuthorityStateStore = SQLiteAuthorityStateStore(self)
        from samuel.adapters.state.identity import SQLiteIdentityStateStore

        self.identity: IIdentityStateStore = SQLiteIdentityStateStore(self)
        self.retention: IRetentionStateStore = SQLiteRetentionStateStore(self)
        self.retention_execution: IRetentionExecutionStore = SQLiteRetentionExecutionStore(self)

    @contextmanager
    def _lifecycle_lock(self, *, exclusive: bool = False) -> Iterator[None]:
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.lifecycle_lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        except OSError as exc:
            raise StateStoreError(
                "state_lifecycle_lock_failed",
                "Runtime-state lifecycle lock could not be acquired",
            ) from exc
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                with suppress(OSError):
                    os.close(descriptor)

    @contextmanager
    def lifecycle_lock(self, *, exclusive: bool = False) -> Iterator[None]:
        """Coordinate bounded local lifecycle tools with backup and restore."""

        with self._lifecycle_lock(exclusive=exclusive):
            yield

    @contextmanager
    def _connection(self, *, lifecycle: bool = True) -> Iterator[sqlite3.Connection]:
        lock = self._lifecycle_lock() if lifecycle else nullcontext()
        with lock:
            try:
                connection = sqlite3.connect(self.path, timeout=self._timeout)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                yield connection
            except StateStoreError:
                raise
            except (OSError, sqlite3.Error) as exc:
                raise _translate_sqlite_error(exc) from exc
            finally:
                connection_value = locals().get("connection")
                if isinstance(connection_value, sqlite3.Connection):
                    connection_value.close()

    def _initialize(self) -> None:
        try:
            created_directory = not self.data_dir.exists()
            self.data_dir.mkdir(parents=True, exist_ok=True)
            if created_directory:
                self.data_dir.chmod(0o700)
        except OSError as exc:
            raise StateStoreError(
                "state_readonly",
                "Runtime-state directory cannot be created or written",
            ) from exc

        if self.path.is_symlink():
            raise StateStoreError(
                "state_path_unsafe",
                "Runtime-state database path must not be a symbolic link",
            )
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            pass
        except OSError as exc:
            raise StateStoreError(
                "state_readonly",
                "Runtime-state database cannot be created or opened",
            ) from exc
        else:
            os.close(descriptor)
        with self._connection() as connection:
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > SCHEMA_VERSION:
                    raise StateStoreError(
                        "state_schema_too_new",
                        f"Runtime-state schema {version} is newer than supported schema "
                        f"{SCHEMA_VERSION}",
                    )
                tables = self._table_names(connection)
                if version == 0 and tables:
                    raise StateStoreError(
                        "state_schema_unversioned",
                        "Runtime-state database contains an unversioned schema",
                    )
                controlled_authority_init = version in {0, 1, 2}
                if version == 0:
                    connection.execute("PRAGMA auto_vacuum = INCREMENTAL")
                    journal_mode = str(
                        connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                    ).lower()
                    if journal_mode != "wal":
                        raise StateStoreError(
                            "state_wal_unavailable",
                            "Runtime-state database could not enable WAL mode",
                        )
                    self._create_schema(connection)
                elif version == 1:
                    self._migrate_v1_to_v2(connection)
                    self._migrate_v2_to_v3(connection)
                    self._migrate_v3_to_v4(connection)
                    self._migrate_v4_to_v5(connection)
                    self._migrate_v5_to_v6(connection)
                    self._migrate_v6_to_v7(connection)
                    self._migrate_v7_to_v8(connection)
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 2:
                    self._migrate_v2_to_v3(connection)
                    self._migrate_v3_to_v4(connection)
                    self._migrate_v4_to_v5(connection)
                    self._migrate_v5_to_v6(connection)
                    self._migrate_v6_to_v7(connection)
                    self._migrate_v7_to_v8(connection)
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 3:
                    self._migrate_v3_to_v4(connection)
                    self._migrate_v4_to_v5(connection)
                    self._migrate_v5_to_v6(connection)
                    self._migrate_v6_to_v7(connection)
                    self._migrate_v7_to_v8(connection)
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 4:
                    self._migrate_v4_to_v5(connection)
                    self._migrate_v5_to_v6(connection)
                    self._migrate_v6_to_v7(connection)
                    self._migrate_v7_to_v8(connection)
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 5:
                    self._migrate_v5_to_v6(connection)
                    self._migrate_v6_to_v7(connection)
                    self._migrate_v7_to_v8(connection)
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 6:
                    self._migrate_v6_to_v7(connection)
                    self._migrate_v7_to_v8(connection)
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 7:
                    self._migrate_v7_to_v8(connection)
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 8:
                    self._migrate_v8_to_v9(connection)
                    self._migrate_v9_to_v10(connection)
                elif version == 9:
                    self._migrate_v9_to_v10(connection)
                self._verify_schema(connection)
            except StateStoreError:
                raise
            except (OSError, sqlite3.Error) as exc:
                raise _translate_sqlite_error(exc) from exc

        try:
            self.path.chmod(0o600)
        except OSError as exc:
            raise StateStoreError(
                "state_permissions_failed",
                "Runtime-state database permissions could not be secured",
            ) from exc
        self._initialize_authority_witness(controlled=controlled_authority_init)
        if self.restore_sentinel_path.exists() or self.restore_sentinel_path.is_symlink():
            self._mark_reconcile("state_restore_interrupted")

    def _authority_metadata(self, *, lifecycle: bool = True) -> sqlite3.Row:
        with self._connection(lifecycle=lifecycle) as connection:
            row = connection.execute(
                "SELECT * FROM authority_metadata WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise StateStoreError(
                "state_authority_metadata_missing",
                "Runtime-state authority metadata is missing",
            )
        return cast(sqlite3.Row, row)

    def _read_authority_witness(self) -> dict[str, Any]:
        path = self.authority_witness_path
        if path.is_symlink() or not path.is_file():
            raise StateStoreError(
                "state_authority_witness_missing",
                "Runtime-state authority witness is missing or unsafe",
            )
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateStoreError(
                "state_authority_witness_invalid",
                "Runtime-state authority witness is unreadable",
            ) from exc
        if (
            not isinstance(document, dict)
            or document.get("schema") != "samuel-authority-witness.v1"
            or not isinstance(document.get("instance_uuid"), str)
            or not isinstance(document.get("authority_epoch"), int)
            or int(document["authority_epoch"]) < 0
        ):
            raise StateStoreError(
                "state_authority_witness_invalid",
                "Runtime-state authority witness has an invalid schema",
            )
        return document

    def _write_authority_witness(self, instance_uuid: str, authority_epoch: int) -> None:
        path = self.authority_witness_path
        if path.is_symlink():
            raise StateStoreError(
                "state_authority_witness_unsafe",
                "Runtime-state authority witness path must not be a symbolic link",
            )
        payload = (
            json.dumps(
                {
                    "authority_epoch": authority_epoch,
                    "instance_uuid": instance_uuid,
                    "schema": "samuel-authority-witness.v1",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            written = 0
            while written < len(payload):
                count = os.write(descriptor, payload[written:])
                if count <= 0:
                    raise OSError("authority witness write made no progress")
                written += count
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, path)
            path.chmod(0o600)
            directory_fd = os.open(self.data_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise StateStoreError(
                "state_authority_witness_write_failed",
                "Runtime-state authority witness could not be persisted",
            ) from exc
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def _sync_authority_witness(self, *, lifecycle: bool = True) -> None:
        """Serialize cross-process witness writes and publish the newest DB epoch."""

        lock_path = self.data_dir / AUTHORITY_WITNESS_LOCK_FILENAME
        descriptor: int | None = None
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            metadata = self._authority_metadata(lifecycle=lifecycle)
            self._write_authority_witness(
                str(metadata["instance_uuid"]), int(metadata["authority_epoch"])
            )
        except StateStoreError:
            raise
        except OSError as exc:
            raise StateStoreError(
                "state_authority_witness_write_failed",
                "Runtime-state authority witness could not be synchronized",
            ) from exc
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                with suppress(OSError):
                    os.close(descriptor)

    def _mark_reconcile(self, reason: str) -> None:
        now = _timestamp(datetime.now(timezone.utc))
        with self._connection() as connection, connection:
            current = connection.execute(
                "SELECT reconcile_required, reconcile_reason FROM authority_metadata "
                "WHERE singleton = 1"
            ).fetchone()
            if current is None:
                raise StateStoreError(
                    "state_authority_metadata_missing",
                    "Runtime-state authority metadata is missing",
                )
            if bool(current["reconcile_required"]):
                return
            connection.execute(
                "UPDATE authority_metadata SET reconcile_required = 1, reconcile_reason = ?, "
                "authority_epoch = authority_epoch + 1, updated_at = ? WHERE singleton = 1",
                (reason, now),
            )

    def _initialize_authority_witness(self, *, controlled: bool) -> None:
        metadata = self._authority_metadata()
        instance_uuid = str(metadata["instance_uuid"])
        epoch = int(metadata["authority_epoch"])
        if controlled:
            self._sync_authority_witness()
            return
        try:
            witness = self._read_authority_witness()
        except StateStoreError as exc:
            self._mark_reconcile(exc.code)
            return
        if str(witness["instance_uuid"]) != instance_uuid:
            self._mark_reconcile("state_authority_instance_mismatch")
        elif int(witness["authority_epoch"]) > epoch:
            self._mark_reconcile("state_authority_epoch_rollback")
        elif int(witness["authority_epoch"]) < epoch:
            self._mark_reconcile("state_authority_witness_lag")

    def compare_audit_authority_epoch(self, audit_epoch: int) -> None:
        """Let lossy audit evidence tighten, but never authorize, state."""

        metadata = self._authority_metadata()
        if audit_epoch > int(metadata["authority_epoch"]):
            self._mark_reconcile("state_authority_audit_ahead")

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

            CREATE TABLE observations (
                observation_key TEXT PRIMARY KEY,
                subject_key TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                observation_schema TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                evidence_origin TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
            CREATE INDEX observations_issue_series
            ON observations(issue_number, evidence_origin, observation_schema, observed_at);

            CREATE TABLE score_derivations (
                score_key TEXT PRIMARY KEY,
                observation_key TEXT NOT NULL REFERENCES observations(observation_key),
                scoring_policy_version TEXT NOT NULL,
                scoring_policy_digest TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                evidence_origin TEXT NOT NULL,
                observation_schema TEXT NOT NULL,
                score REAL,
                payload_json TEXT NOT NULL,
                derived_at TEXT NOT NULL
            );
            CREATE INDEX score_derivations_issue_series
            ON score_derivations(
                issue_number,
                evidence_origin,
                observation_schema,
                scoring_policy_version,
                formula_version,
                derived_at
            );

            CREATE TABLE evaluation_terminals (
                terminal_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
            CREATE INDEX evaluation_terminals_issue
            ON evaluation_terminals(issue_number, observed_at);

            CREATE TABLE run_projections (
                projection_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                series TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX run_projections_issue_series
            ON run_projections(issue_number, series, updated_at);

            CREATE TABLE authority_records (
                record_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE authority_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                instance_uuid TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 0),
                reconcile_required INTEGER NOT NULL CHECK(reconcile_required IN (0, 1)),
                reconcile_reason TEXT,
                active_restore_operation TEXT,
                pre_restore_epoch_highwater INTEGER NOT NULL DEFAULT 0
                    CHECK(pre_restore_epoch_highwater >= 0),
                restored_from_uuid TEXT,
                retention_emergency_stop INTEGER NOT NULL DEFAULT 1
                    CHECK(retention_emergency_stop IN (0, 1)),
                updated_at TEXT NOT NULL
            );
            INSERT INTO authority_metadata VALUES (
                1,
                lower(hex(randomblob(16))),
                0,
                0,
                NULL,
                NULL,
                0,
                NULL,
                1,
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            );

            CREATE TABLE healing_claims (
                observation_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('claimed', 'attempted', 'abandoned')),
                outcome TEXT,
                reason TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE workflow_checkpoints (
                checkpoint_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                workflow TEXT NOT NULL,
                boundary TEXT NOT NULL,
                repository TEXT NOT NULL,
                branch TEXT NOT NULL,
                base_ref TEXT NOT NULL,
                head_sha TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                evaluation_subject_json TEXT NOT NULL,
                resume_eligible INTEGER NOT NULL CHECK(resume_eligible IN (0, 1)),
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE operation_intents (
                intent_key TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('pending', 'applied', 'failed', 'mismatch', 'unresolved')
                ),
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                postcondition_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE workflow_budget_admissions (
                admission_key TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                issue_number INTEGER NOT NULL CHECK(issue_number > 0),
                invocation_digest TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                policy_digest TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                token_limit INTEGER NOT NULL CHECK(token_limit > 0),
                plan_contract_hash TEXT NOT NULL DEFAULT '',
                plan_comment_id INTEGER NOT NULL DEFAULT 0 CHECK(plan_comment_id >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX workflow_budget_plan_binding
            ON workflow_budget_admissions(
                repository, issue_number, plan_contract_hash, plan_comment_id
            )
            WHERE plan_contract_hash != '';

            CREATE TABLE llm_budget_attempts (
                attempt_key TEXT PRIMARY KEY,
                admission_key TEXT NOT NULL
                    REFERENCES workflow_budget_admissions(admission_key),
                logical_call_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task TEXT NOT NULL,
                input_upper_bound INTEGER NOT NULL CHECK(input_upper_bound > 0),
                output_upper_bound INTEGER NOT NULL CHECK(output_upper_bound > 0),
                reserved_tokens INTEGER NOT NULL CHECK(
                    reserved_tokens = input_upper_bound + output_upper_bound
                ),
                status TEXT NOT NULL CHECK(status IN ('reserved', 'settled', 'unknown')),
                actual_input_tokens INTEGER CHECK(actual_input_tokens >= 0),
                actual_output_tokens INTEGER CHECK(actual_output_tokens >= 0),
                outcome_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status = 'settled' AND actual_input_tokens IS NOT NULL
                        AND actual_output_tokens IS NOT NULL)
                    OR (status IN ('reserved', 'unknown') AND actual_input_tokens IS NULL
                        AND actual_output_tokens IS NULL)
                ),
                CHECK(
                    (status = 'reserved' AND outcome_code = '')
                    OR (status IN ('settled', 'unknown') AND outcome_code != '')
                )
            );
            CREATE INDEX llm_budget_attempts_admission
            ON llm_budget_attempts(admission_key, created_at, attempt_key);

            CREATE TABLE planning_clarifications (
                series_key TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                issue_number INTEGER NOT NULL CHECK(issue_number > 0),
                source_digest TEXT NOT NULL,
                admission_key TEXT NOT NULL REFERENCES workflow_budget_admissions(admission_key),
                correlation_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'waiting', 'answered', 'planned', 'superseded', 'timed_out', 'exhausted'
                )),
                round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 2),
                deadline_at TEXT NOT NULL,
                rounds_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX planning_clarifications_issue
            ON planning_clarifications(repository, issue_number, updated_at, series_key);

            CREATE TABLE authority_leases (
                resource_key TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE identity_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                status TEXT NOT NULL CHECK(
                    status IN ('uninitialized', 'active', 'recovery_pending')
                ),
                recovery_reason TEXT,
                activated_at TEXT,
                updated_at TEXT NOT NULL
            );
            INSERT INTO identity_metadata VALUES (
                1,
                'uninitialized',
                NULL,
                NULL,
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            );

            CREATE TABLE identity_principals (
                principal_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                kind TEXT NOT NULL CHECK(kind IN ('user', 'automation')),
                password_hash TEXT,
                disabled INTEGER NOT NULL CHECK(disabled IN (0, 1)),
                credential_version INTEGER NOT NULL CHECK(credential_version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (kind = 'user' AND password_hash IS NOT NULL)
                    OR (kind = 'automation' AND password_hash IS NULL)
                )
            );

            CREATE TABLE identity_principal_roles (
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(
                    role IN ('viewer', 'auditor', 'operator', 'administrator')
                ),
                PRIMARY KEY(principal_id, role)
            );

            CREATE TABLE identity_sessions (
                session_id TEXT NOT NULL UNIQUE,
                session_hash TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                instance_uuid TEXT NOT NULL,
                csrf_hash TEXT NOT NULL,
                credential_version INTEGER NOT NULL CHECK(credential_version >= 1),
                created_at TEXT NOT NULL,
                authenticated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                revoked_by TEXT
            );
            CREATE INDEX identity_sessions_principal
            ON identity_sessions(principal_id, expires_at);

            CREATE TABLE identity_tokens (
                token_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                permissions_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                revoked_by TEXT
            );
            CREATE INDEX identity_tokens_principal
            ON identity_tokens(principal_id, expires_at);

            CREATE TABLE quality_metrics (
                metric_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task TEXT NOT NULL,
                evidence_origin TEXT NOT NULL,
                observation_schema TEXT NOT NULL,
                scoring_policy_version TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX quality_metrics_series
            ON quality_metrics(
                provider,
                model,
                task,
                evidence_origin,
                observation_schema,
                scoring_policy_version,
                formula_version,
                updated_at
            );

            CREATE TABLE legacy_imports (
                source_path TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                format_version TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                record_counts_json TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );

            CREATE TABLE managed_backups (
                backup_id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                digest TEXT NOT NULL,
                instance_uuid TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 0),
                created_at TEXT NOT NULL
            );

            CREATE TABLE restore_operations (
                operation_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(
                    status IN ('reconcile_required', 'completed', 'superseded')
                ),
                source_digest TEXT NOT NULL,
                restored_from_uuid TEXT NOT NULL,
                instance_uuid TEXT NOT NULL,
                pre_restore_epoch_highwater INTEGER NOT NULL
                    CHECK(pre_restore_epoch_highwater >= 0),
                supersedes_operation_id TEXT,
                reason TEXT,
                scan_status TEXT NOT NULL CHECK(
                    scan_status IN ('pending', 'completed', 'scan_failed')
                ),
                scan_error_code TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE reconcile_entries (
                operation_id TEXT NOT NULL REFERENCES restore_operations(operation_id),
                object_type TEXT NOT NULL,
                object_key TEXT NOT NULL,
                classification TEXT NOT NULL CHECK(
                    classification IN (
                        'verified_effect', 'verified_absent', 'abandoned', 'unresolved'
                    )
                ),
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(operation_id, object_type, object_key)
            );

            CREATE TABLE retention_category_states (
                category_id TEXT PRIMARY KEY,
                category_digest TEXT NOT NULL,
                profile_role_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('report_only', 'enforce', 'suspended')),
                version INTEGER NOT NULL CHECK(version >= 1),
                evidence_digest TEXT,
                grant_cutoff_utc TEXT,
                activated_at TEXT,
                reason TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE retention_executions (
                execution_id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                plan_digest TEXT NOT NULL UNIQUE,
                category_digest TEXT NOT NULL,
                profile_role_digest TEXT NOT NULL,
                cutoff_utc TEXT NOT NULL,
                anchor TEXT NOT NULL,
                object_ids_json TEXT NOT NULL,
                candidate_count INTEGER NOT NULL CHECK(candidate_count >= 0),
                deleted_count INTEGER NOT NULL CHECK(deleted_count >= 0),
                status TEXT NOT NULL CHECK(status = 'completed'),
                reason TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 1),
                executed_at TEXT NOT NULL
            );

            INSERT INTO schema_migrations(version, applied_at)
            VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (3, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (4, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (5, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (6, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (7, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (8, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (9, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (10, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 10;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        """Upgrade the passive foundation without discarding v1 shadow data."""

        connection.executescript(
            """
            BEGIN IMMEDIATE;
            ALTER TABLE observations ADD COLUMN issue_number INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE observations ADD COLUMN evidence_origin TEXT NOT NULL
                DEFAULT 'bound_acceptance_evidence';
            CREATE INDEX observations_issue_series
            ON observations(issue_number, evidence_origin, observation_schema, observed_at);

            ALTER TABLE score_derivations ADD COLUMN scoring_policy_digest TEXT NOT NULL
                DEFAULT '';
            ALTER TABLE score_derivations ADD COLUMN issue_number INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE score_derivations ADD COLUMN evidence_origin TEXT NOT NULL
                DEFAULT 'bound_acceptance_evidence';
            ALTER TABLE score_derivations ADD COLUMN observation_schema TEXT NOT NULL
                DEFAULT 'bound.v1';
            CREATE INDEX score_derivations_issue_series
            ON score_derivations(
                issue_number,
                evidence_origin,
                observation_schema,
                scoring_policy_version,
                formula_version,
                derived_at
            );

            CREATE TABLE evaluation_terminals (
                terminal_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );
            CREATE INDEX evaluation_terminals_issue
            ON evaluation_terminals(issue_number, observed_at);

            CREATE TABLE quality_metrics (
                metric_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task TEXT NOT NULL,
                evidence_origin TEXT NOT NULL,
                observation_schema TEXT NOT NULL,
                scoring_policy_version TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX quality_metrics_series
            ON quality_metrics(
                provider,
                model,
                task,
                evidence_origin,
                observation_schema,
                scoring_policy_version,
                formula_version,
                updated_at
            );

            CREATE TABLE legacy_imports (
                source_path TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                format_version TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                record_counts_json TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 2;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE authority_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                instance_uuid TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 0),
                reconcile_required INTEGER NOT NULL CHECK(reconcile_required IN (0, 1)),
                reconcile_reason TEXT,
                updated_at TEXT NOT NULL
            );
            INSERT INTO authority_metadata VALUES (
                1,
                lower(hex(randomblob(16))),
                0,
                0,
                NULL,
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            );
            CREATE TABLE healing_claims (
                observation_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('claimed', 'attempted', 'abandoned')),
                outcome TEXT,
                reason TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE workflow_checkpoints (
                checkpoint_key TEXT PRIMARY KEY,
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                workflow TEXT NOT NULL,
                boundary TEXT NOT NULL,
                repository TEXT NOT NULL,
                branch TEXT NOT NULL,
                base_ref TEXT NOT NULL,
                head_sha TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                evaluation_subject_json TEXT NOT NULL,
                resume_eligible INTEGER NOT NULL CHECK(resume_eligible IN (0, 1)),
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE operation_intents (
                intent_key TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('pending', 'applied', 'failed', 'mismatch', 'unresolved')
                ),
                issue_number INTEGER NOT NULL,
                correlation_id TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                postcondition_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE authority_leases (
                resource_key TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                updated_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (3, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 3;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            ALTER TABLE authority_metadata ADD COLUMN active_restore_operation TEXT;
            ALTER TABLE authority_metadata ADD COLUMN pre_restore_epoch_highwater INTEGER
                NOT NULL DEFAULT 0 CHECK(pre_restore_epoch_highwater >= 0);
            ALTER TABLE authority_metadata ADD COLUMN restored_from_uuid TEXT;

            CREATE TABLE restore_operations (
                operation_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(
                    status IN ('reconcile_required', 'completed', 'superseded')
                ),
                source_digest TEXT NOT NULL,
                restored_from_uuid TEXT NOT NULL,
                instance_uuid TEXT NOT NULL,
                pre_restore_epoch_highwater INTEGER NOT NULL
                    CHECK(pre_restore_epoch_highwater >= 0),
                supersedes_operation_id TEXT,
                reason TEXT,
                scan_status TEXT NOT NULL CHECK(
                    scan_status IN ('pending', 'completed', 'scan_failed')
                ),
                scan_error_code TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE reconcile_entries (
                operation_id TEXT NOT NULL REFERENCES restore_operations(operation_id),
                object_type TEXT NOT NULL,
                object_key TEXT NOT NULL,
                classification TEXT NOT NULL CHECK(
                    classification IN (
                        'verified_effect', 'verified_absent', 'abandoned', 'unresolved'
                    )
                ),
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(operation_id, object_type, object_key)
            );
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (4, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 4;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v4_to_v5(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            ALTER TABLE authority_metadata ADD COLUMN retention_emergency_stop INTEGER
                NOT NULL DEFAULT 1 CHECK(retention_emergency_stop IN (0, 1));
            CREATE TABLE managed_backups (
                backup_id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                digest TEXT NOT NULL,
                instance_uuid TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 0),
                created_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (5, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 5;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v5_to_v6(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE retention_category_states (
                category_id TEXT PRIMARY KEY,
                category_digest TEXT NOT NULL,
                profile_role_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('report_only', 'enforce', 'suspended')),
                version INTEGER NOT NULL CHECK(version >= 1),
                evidence_digest TEXT,
                reason TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE retention_executions (
                execution_id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                plan_digest TEXT NOT NULL UNIQUE,
                category_digest TEXT NOT NULL,
                profile_role_digest TEXT NOT NULL,
                cutoff_utc TEXT NOT NULL,
                anchor TEXT NOT NULL,
                object_ids_json TEXT NOT NULL,
                candidate_count INTEGER NOT NULL CHECK(candidate_count >= 0),
                deleted_count INTEGER NOT NULL CHECK(deleted_count >= 0),
                status TEXT NOT NULL CHECK(status = 'completed'),
                reason TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL CHECK(authority_epoch >= 1),
                executed_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (6, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 6;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v6_to_v7(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE identity_metadata (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                status TEXT NOT NULL CHECK(
                    status IN ('uninitialized', 'active', 'recovery_pending')
                ),
                recovery_reason TEXT,
                activated_at TEXT,
                updated_at TEXT NOT NULL
            );
            INSERT INTO identity_metadata VALUES (
                1,
                'uninitialized',
                NULL,
                NULL,
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            );
            CREATE TABLE identity_principals (
                principal_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                kind TEXT NOT NULL CHECK(kind IN ('user', 'automation')),
                password_hash TEXT,
                disabled INTEGER NOT NULL CHECK(disabled IN (0, 1)),
                credential_version INTEGER NOT NULL CHECK(credential_version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (kind = 'user' AND password_hash IS NOT NULL)
                    OR (kind = 'automation' AND password_hash IS NULL)
                )
            );
            CREATE TABLE identity_principal_roles (
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(
                    role IN ('viewer', 'auditor', 'operator', 'administrator')
                ),
                PRIMARY KEY(principal_id, role)
            );
            CREATE TABLE identity_sessions (
                session_id TEXT NOT NULL UNIQUE,
                session_hash TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                instance_uuid TEXT NOT NULL,
                csrf_hash TEXT NOT NULL,
                credential_version INTEGER NOT NULL CHECK(credential_version >= 1),
                created_at TEXT NOT NULL,
                authenticated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                revoked_by TEXT
            );
            CREATE INDEX identity_sessions_principal
            ON identity_sessions(principal_id, expires_at);
            CREATE TABLE identity_tokens (
                token_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                principal_id TEXT NOT NULL REFERENCES identity_principals(principal_id)
                    ON DELETE CASCADE,
                permissions_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                revoked_by TEXT
            );
            CREATE INDEX identity_tokens_principal
            ON identity_tokens(principal_id, expires_at);
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (7, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 7;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v7_to_v8(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            ALTER TABLE retention_category_states ADD COLUMN grant_cutoff_utc TEXT;
            ALTER TABLE retention_category_states ADD COLUMN activated_at TEXT;
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (8, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 8;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v8_to_v9(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE workflow_budget_admissions (
                admission_key TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                issue_number INTEGER NOT NULL CHECK(issue_number > 0),
                invocation_digest TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                policy_digest TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                token_limit INTEGER NOT NULL CHECK(token_limit > 0),
                plan_contract_hash TEXT NOT NULL DEFAULT '',
                plan_comment_id INTEGER NOT NULL DEFAULT 0 CHECK(plan_comment_id >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX workflow_budget_plan_binding
            ON workflow_budget_admissions(
                repository, issue_number, plan_contract_hash, plan_comment_id
            )
            WHERE plan_contract_hash != '';
            CREATE TABLE llm_budget_attempts (
                attempt_key TEXT PRIMARY KEY,
                admission_key TEXT NOT NULL
                    REFERENCES workflow_budget_admissions(admission_key),
                logical_call_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                task TEXT NOT NULL,
                input_upper_bound INTEGER NOT NULL CHECK(input_upper_bound > 0),
                output_upper_bound INTEGER NOT NULL CHECK(output_upper_bound > 0),
                reserved_tokens INTEGER NOT NULL CHECK(
                    reserved_tokens = input_upper_bound + output_upper_bound
                ),
                status TEXT NOT NULL CHECK(status IN ('reserved', 'settled', 'unknown')),
                actual_input_tokens INTEGER CHECK(actual_input_tokens >= 0),
                actual_output_tokens INTEGER CHECK(actual_output_tokens >= 0),
                outcome_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK(
                    (status = 'settled' AND actual_input_tokens IS NOT NULL
                        AND actual_output_tokens IS NOT NULL)
                    OR (status IN ('reserved', 'unknown') AND actual_input_tokens IS NULL
                        AND actual_output_tokens IS NULL)
                ),
                CHECK(
                    (status = 'reserved' AND outcome_code = '')
                    OR (status IN ('settled', 'unknown') AND outcome_code != '')
                )
            );
            CREATE INDEX llm_budget_attempts_admission
            ON llm_budget_attempts(admission_key, created_at, attempt_key);
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (9, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 9;
            COMMIT;
            """
        )

    @staticmethod
    def _migrate_v9_to_v10(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE planning_clarifications (
                series_key TEXT PRIMARY KEY,
                repository TEXT NOT NULL,
                issue_number INTEGER NOT NULL CHECK(issue_number > 0),
                source_digest TEXT NOT NULL,
                admission_key TEXT NOT NULL REFERENCES workflow_budget_admissions(admission_key),
                correlation_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'waiting', 'answered', 'planned', 'superseded', 'timed_out', 'exhausted'
                )),
                round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 2),
                deadline_at TEXT NOT NULL,
                rounds_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX planning_clarifications_issue
            ON planning_clarifications(repository, issue_number, updated_at, series_key);
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (10, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
            PRAGMA user_version = 10;
            COMMIT;
            """
        )

    @staticmethod
    def _table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
        rows = connection.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def _verify_schema(self, connection: sqlite3.Connection) -> None:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise StateStoreError(
                "state_schema_unsupported",
                f"Runtime-state schema {version} is not supported",
            )
        tables = self._table_names(connection)
        if tables != _EXPECTED_TABLES:
            raise StateStoreError(
                "state_schema_invalid",
                "Runtime-state schema does not match the supported table contract",
            )
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        auto_vacuum = int(connection.execute("PRAGMA auto_vacuum").fetchone()[0])
        foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
        integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0]).lower()
        if journal_mode != "wal" or auto_vacuum != 2 or foreign_keys != 1 or integrity != "ok":
            raise StateStoreError(
                "state_schema_invalid",
                "Runtime-state database settings or integrity check are invalid",
            )

    def _status(self, *, lifecycle: bool) -> StateStoreStatus:
        lock = self._lifecycle_lock() if lifecycle else nullcontext()
        with lock:
            with self._connection(lifecycle=False) as connection:
                self._verify_schema(connection)
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
                auto_vacuum_value = int(connection.execute("PRAGMA auto_vacuum").fetchone()[0])
                foreign_keys = bool(connection.execute("PRAGMA foreign_keys").fetchone()[0])
                tables = self._table_names(connection)
                authority = connection.execute(
                    "SELECT * FROM authority_metadata WHERE singleton = 1"
                ).fetchone()
                restore = None
                if authority is not None and authority["active_restore_operation"] is not None:
                    restore = connection.execute(
                        "SELECT scan_status FROM restore_operations WHERE operation_id = ?",
                        (str(authority["active_restore_operation"]),),
                    ).fetchone()
                retention_states = tuple(
                    {
                        "category": str(row["category_id"]),
                        "category_digest": str(row["category_digest"]),
                        "profile_role_digest": str(row["profile_role_digest"]),
                        "state": str(row["state"]),
                        "version": int(row["version"]),
                        "evidence_digest": (
                            str(row["evidence_digest"])
                            if row["evidence_digest"] is not None
                            else None
                        ),
                        "grant_cutoff_utc": (
                            str(row["grant_cutoff_utc"])
                            if row["grant_cutoff_utc"] is not None
                            else None
                        ),
                        "activated_at": (
                            str(row["activated_at"]) if row["activated_at"] is not None else None
                        ),
                        "updated_at": str(row["updated_at"]),
                    }
                    for row in connection.execute(
                        "SELECT * FROM retention_category_states ORDER BY category_id"
                    ).fetchall()
                )
                last_execution_row = connection.execute(
                    "SELECT category_id, execution_id, plan_digest, deleted_count, "
                    "authority_epoch, executed_at FROM retention_executions "
                    "ORDER BY executed_at DESC, execution_id DESC LIMIT 1"
                ).fetchone()
                identity_metadata = connection.execute(
                    "SELECT status FROM identity_metadata WHERE singleton = 1"
                ).fetchone()
                identity_principals = int(
                    connection.execute("SELECT COUNT(*) FROM identity_principals").fetchone()[0]
                )
                identity_active_sessions = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM identity_sessions WHERE revoked_at IS NULL "
                        "AND expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
                    ).fetchone()[0]
                )
                identity_active_tokens = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM identity_tokens WHERE revoked_at IS NULL "
                        "AND expires_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
                    ).fetchone()[0]
                )
            if authority is None:
                raise StateStoreError(
                    "state_authority_metadata_missing",
                    "Runtime-state authority metadata is missing",
                )
            witness_epoch = -1
            try:
                witness = self._read_authority_witness()
                if str(witness["instance_uuid"]) == str(authority["instance_uuid"]):
                    witness_epoch = int(witness["authority_epoch"])
            except StateStoreError:
                pass
        auto_vacuum = {0: "none", 1: "full", 2: "incremental"}.get(auto_vacuum_value, "unknown")
        return StateStoreStatus(
            healthy=True,
            path=self.path,
            schema_version=version,
            supported_schema_version=SCHEMA_VERSION,
            journal_mode=journal_mode,
            auto_vacuum=auto_vacuum,
            foreign_keys=foreign_keys,
            filesystem_type=self._filesystem_type,
            filesystem_mount=self._filesystem_mount,
            tables=tables,
            projection_healthy=self._projection_error_code is None,
            projection_error_code=self._projection_error_code,
            authority_epoch=int(authority["authority_epoch"]),
            authority_instance=str(authority["instance_uuid"]),
            witness_epoch=witness_epoch,
            reconcile_required=bool(authority["reconcile_required"]),
            reconcile_reason=(
                str(authority["reconcile_reason"])
                if authority["reconcile_reason"] is not None
                else None
            ),
            active_restore_operation=(
                str(authority["active_restore_operation"])
                if authority["active_restore_operation"] is not None
                else None
            ),
            restore_scan_status=(str(restore["scan_status"]) if restore is not None else None),
            restore_sentinel_present=(
                self.restore_sentinel_path.exists() or self.restore_sentinel_path.is_symlink()
            ),
            retention_emergency_stop=bool(authority["retention_emergency_stop"]),
            retention_category_states=retention_states,
            retention_last_execution=(
                {
                    "category": str(last_execution_row["category_id"]),
                    "execution_id": str(last_execution_row["execution_id"]),
                    "plan_digest": str(last_execution_row["plan_digest"]),
                    "deleted_count": int(last_execution_row["deleted_count"]),
                    "authority_epoch": int(last_execution_row["authority_epoch"]),
                    "executed_at": str(last_execution_row["executed_at"]),
                }
                if last_execution_row is not None
                else None
            ),
            identity_status=(
                str(identity_metadata["status"]) if identity_metadata is not None else "unavailable"
            ),
            identity_principals=identity_principals,
            identity_active_sessions=identity_active_sessions,
            identity_active_tokens=identity_active_tokens,
        )

    def status(self) -> StateStoreStatus:
        return self._status(lifecycle=True)

    def dump(self) -> dict[str, Any]:
        with self._lifecycle_lock():
            status = self._status(lifecycle=False).as_dict()
            with self._connection(lifecycle=False) as connection:
                counts = {
                    table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    for table in _EXPECTED_TABLES
                }
                migrations = [
                    {"version": int(row[0]), "applied_at": str(row[1])}
                    for row in connection.execute(
                        "SELECT version, applied_at FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]
                authority_counts = {
                    "claims": {
                        status_name: int(
                            connection.execute(
                                "SELECT COUNT(*) FROM healing_claims WHERE status = ?",
                                (status_name,),
                            ).fetchone()[0]
                        )
                        for status_name in ("claimed", "attempted", "abandoned")
                    },
                    "checkpoints": int(
                        connection.execute("SELECT COUNT(*) FROM workflow_checkpoints").fetchone()[
                            0
                        ]
                    ),
                    "intents": {
                        status_name: int(
                            connection.execute(
                                "SELECT COUNT(*) FROM operation_intents WHERE status = ?",
                                (status_name,),
                            ).fetchone()[0]
                        )
                        for status_name in (
                            "pending",
                            "applied",
                            "failed",
                            "mismatch",
                            "unresolved",
                        )
                    },
                    "workflow_budgets": {
                        "admissions": int(
                            connection.execute(
                                "SELECT COUNT(*) FROM workflow_budget_admissions"
                            ).fetchone()[0]
                        ),
                        "attempts": {
                            status_name: int(
                                connection.execute(
                                    "SELECT COUNT(*) FROM llm_budget_attempts WHERE status = ?",
                                    (status_name,),
                                ).fetchone()[0]
                            )
                            for status_name in ("reserved", "settled", "unknown")
                        },
                        "committed_tokens": int(
                            connection.execute(
                                "SELECT COALESCE(SUM(CASE WHEN status = 'settled' "
                                "THEN actual_input_tokens + actual_output_tokens "
                                "ELSE reserved_tokens END), 0) FROM llm_budget_attempts"
                            ).fetchone()[0]
                        ),
                    },
                    "planning_clarifications": {
                        status_name: int(
                            connection.execute(
                                "SELECT COUNT(*) FROM planning_clarifications WHERE status = ?",
                                (status_name,),
                            ).fetchone()[0]
                        )
                        for status_name in (
                            "waiting",
                            "answered",
                            "planned",
                            "superseded",
                            "timed_out",
                            "exhausted",
                        )
                    },
                    "leases": int(
                        connection.execute("SELECT COUNT(*) FROM authority_leases").fetchone()[0]
                    ),
                    "restore_operations": {
                        status_name: int(
                            connection.execute(
                                "SELECT COUNT(*) FROM restore_operations WHERE status = ?",
                                (status_name,),
                            ).fetchone()[0]
                        )
                        for status_name in ("reconcile_required", "completed", "superseded")
                    },
                    "reconcile_entries": {
                        status_name: int(
                            connection.execute(
                                "SELECT COUNT(*) FROM reconcile_entries WHERE classification = ?",
                                (status_name,),
                            ).fetchone()[0]
                        )
                        for status_name in (
                            "verified_effect",
                            "verified_absent",
                            "abandoned",
                            "unresolved",
                        )
                    },
                }
        return {
            "format": "samuel-state-dump.v1",
            "status": status,
            "row_counts": counts,
            "migrations": migrations,
            "authority_counts": authority_counts,
            "payloads_included": False,
        }

    def backup(self, destination: Path) -> Path:
        destination = destination.expanduser().resolve(strict=False)
        if destination == self.path:
            raise StateStoreError(
                "state_backup_target_invalid",
                "Runtime-state backup target must differ from the live database",
            )
        if destination.exists():
            raise StateStoreError(
                "state_backup_exists",
                "Runtime-state backup target already exists",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
        try:
            with self._connection() as source:
                target = sqlite3.connect(temporary)
                try:
                    source.backup(target)
                    integrity = str(target.execute("PRAGMA integrity_check").fetchone()[0]).lower()
                    if integrity != "ok":
                        raise StateStoreError(
                            "state_backup_invalid",
                            "Runtime-state backup failed its integrity check",
                        )
                finally:
                    target.close()
            temporary.chmod(0o600)
            os.link(temporary, destination)
        except StateStoreError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise _translate_sqlite_error(exc) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        return destination

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise StateStoreError(
                "state_restore_source_unreadable",
                "Runtime-state restore source could not be read",
            ) from exc
        return f"sha256:{digest.hexdigest()}"

    def _write_restore_sentinel(self, payload: dict[str, Any]) -> None:
        if self.restore_sentinel_path.is_symlink():
            raise StateStoreError(
                "state_restore_sentinel_unsafe",
                "Runtime-state restore sentinel path must not be a symbolic link",
            )
        temporary = self.restore_sentinel_path.with_name(
            f".{self.restore_sentinel_path.name}.tmp-{uuid.uuid4().hex}"
        )
        encoded = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode(
            "utf-8"
        )
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.write(descriptor, encoded)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary, self.restore_sentinel_path)
            directory_fd = os.open(self.data_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise StateStoreError(
                "state_restore_sentinel_write_failed",
                "Runtime-state restore sentinel could not be persisted",
            ) from exc
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)
            with suppress(OSError):
                temporary.unlink(missing_ok=True)

    def _assert_restore_complete(self) -> None:
        if self.restore_sentinel_path.exists() or self.restore_sentinel_path.is_symlink():
            raise StateStoreError(
                "state_restore_interrupted",
                "Interrupted restore must be explicitly superseded before authority changes",
            )

    @staticmethod
    def _restore_operation_from_row(row: sqlite3.Row) -> RestoreOperationRecord:
        return RestoreOperationRecord(
            operation_id=str(row["operation_id"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            source_digest=str(row["source_digest"]),
            restored_from_uuid=str(row["restored_from_uuid"]),
            instance_uuid=str(row["instance_uuid"]),
            pre_restore_epoch_highwater=int(row["pre_restore_epoch_highwater"]),
            supersedes_operation_id=(
                str(row["supersedes_operation_id"])
                if row["supersedes_operation_id"] is not None
                else None
            ),
            reason=str(row["reason"]) if row["reason"] is not None else None,
            scan_status=str(row["scan_status"]),  # type: ignore[arg-type]
            scan_error_code=(
                str(row["scan_error_code"]) if row["scan_error_code"] is not None else None
            ),
            created_at=_from_timestamp(str(row["created_at"])),
            completed_at=(
                _from_timestamp(str(row["completed_at"]))
                if row["completed_at"] is not None
                else None
            ),
        )

    def list_restore_operations(self) -> list[RestoreOperationRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM restore_operations ORDER BY created_at, operation_id"
            ).fetchall()
        return [self._restore_operation_from_row(row) for row in rows]

    def restore(
        self,
        source: Path,
        *,
        audit_epoch: int = 0,
        supersede_operation_id: str | None = None,
        reason: str | None = None,
    ) -> RestoreOperationRecord:
        source_candidate = source.expanduser()
        if source_candidate.is_symlink():
            raise StateStoreError(
                "state_restore_source_invalid",
                "Runtime-state restore source must be a separate regular backup file",
            )
        source = source_candidate.resolve(strict=False)
        if source == self.path or not source.is_file():
            raise StateStoreError(
                "state_restore_source_invalid",
                "Runtime-state restore source must be a separate regular backup file",
            )
        if audit_epoch < 0:
            raise StateStoreError(
                "state_restore_audit_epoch_invalid",
                "Runtime-state restore audit epoch must be non-negative",
            )
        if supersede_operation_id and not str(reason or "").strip():
            raise StateStoreError(
                "state_restore_supersession_reason_required",
                "Superseding a restore requires an operator reason",
            )

        operation_id = str(uuid.uuid4())
        staging = self.data_dir / f".{DATABASE_FILENAME}.restore-{operation_id}"
        source_digest = self._file_digest(source)
        with self._lifecycle_lock(exclusive=True):
            sentinel_operation: str | None = None
            sentinel_document: dict[str, Any] = {}
            if self.restore_sentinel_path.exists() or self.restore_sentinel_path.is_symlink():
                if self.restore_sentinel_path.is_symlink():
                    raise StateStoreError(
                        "state_restore_sentinel_unsafe",
                        "Runtime-state restore sentinel path must not be a symbolic link",
                    )
                try:
                    sentinel = json.loads(self.restore_sentinel_path.read_text(encoding="utf-8"))
                    if isinstance(sentinel, dict):
                        sentinel_document = sentinel
                        sentinel_operation = str(sentinel.get("operation_id") or "") or None
                except (OSError, json.JSONDecodeError) as exc:
                    raise StateStoreError(
                        "state_restore_sentinel_invalid",
                        "Interrupted restore sentinel is unreadable or invalid",
                    ) from exc
                if sentinel_operation is None:
                    raise StateStoreError(
                        "state_restore_sentinel_invalid",
                        "Interrupted restore sentinel is unreadable or invalid",
                    )
                if supersede_operation_id != sentinel_operation:
                    raise StateStoreError(
                        "state_restore_interrupted",
                        "An interrupted restore must be explicitly superseded",
                    )

            with self._connection(lifecycle=False) as live:
                live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                live_metadata = live.execute(
                    "SELECT * FROM authority_metadata WHERE singleton = 1"
                ).fetchone()
                if live_metadata is None:
                    raise StateStoreError(
                        "state_authority_metadata_missing",
                        "Runtime-state authority metadata is missing",
                    )
                active_operation = (
                    str(live_metadata["active_restore_operation"])
                    if live_metadata["active_restore_operation"] is not None
                    else None
                )
                active_row = None
                if active_operation:
                    active_row = live.execute(
                        "SELECT * FROM restore_operations WHERE operation_id = ?",
                        (active_operation,),
                    ).fetchone()

            open_operation = sentinel_operation or active_operation
            if open_operation and supersede_operation_id != open_operation:
                raise StateStoreError(
                    "state_restore_reconcile_open",
                    "An open restore reconcile must be completed or explicitly superseded",
                )
            if supersede_operation_id and supersede_operation_id != open_operation:
                raise StateStoreError(
                    "state_restore_supersession_mismatch",
                    "Restore supersession does not match the open operation",
                )

            try:
                witness = self._read_authority_witness()
                witness_epoch = int(witness["authority_epoch"])
            except StateStoreError:
                witness_epoch = 0
            pre_highwater = max(
                int(live_metadata["authority_epoch"]),
                int(live_metadata["pre_restore_epoch_highwater"]),
                witness_epoch,
                audit_epoch,
            )
            self._write_restore_sentinel(
                {
                    "operation_id": operation_id,
                    "previous_operation_id": sentinel_operation or active_operation,
                    "pre_restore_epoch_highwater": pre_highwater,
                    "schema": "samuel-state-restore.v1",
                    "source_digest": source_digest,
                    "created_at": _timestamp(datetime.now(timezone.utc)),
                }
            )

            try:
                source_connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
                target = sqlite3.connect(staging)
                target.row_factory = sqlite3.Row
                try:
                    source_connection.backup(target)
                    target.execute("PRAGMA foreign_keys = ON")
                    version = int(target.execute("PRAGMA user_version").fetchone()[0])
                    tables = self._table_names(target)
                    if version == 0 and tables:
                        raise StateStoreError(
                            "state_schema_unversioned",
                            "Runtime-state restore source contains an unversioned schema",
                        )
                    if version > SCHEMA_VERSION:
                        raise StateStoreError(
                            "state_schema_too_new",
                            "Runtime-state restore source is newer than this installation",
                        )
                    if version == 1:
                        self._migrate_v1_to_v2(target)
                        self._migrate_v2_to_v3(target)
                        self._migrate_v3_to_v4(target)
                        self._migrate_v4_to_v5(target)
                        self._migrate_v5_to_v6(target)
                        self._migrate_v6_to_v7(target)
                        self._migrate_v7_to_v8(target)
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 2:
                        self._migrate_v2_to_v3(target)
                        self._migrate_v3_to_v4(target)
                        self._migrate_v4_to_v5(target)
                        self._migrate_v5_to_v6(target)
                        self._migrate_v6_to_v7(target)
                        self._migrate_v7_to_v8(target)
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 3:
                        self._migrate_v3_to_v4(target)
                        self._migrate_v4_to_v5(target)
                        self._migrate_v5_to_v6(target)
                        self._migrate_v6_to_v7(target)
                        self._migrate_v7_to_v8(target)
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 4:
                        self._migrate_v4_to_v5(target)
                        self._migrate_v5_to_v6(target)
                        self._migrate_v6_to_v7(target)
                        self._migrate_v7_to_v8(target)
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 5:
                        self._migrate_v5_to_v6(target)
                        self._migrate_v6_to_v7(target)
                        self._migrate_v7_to_v8(target)
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 6:
                        self._migrate_v6_to_v7(target)
                        self._migrate_v7_to_v8(target)
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 7:
                        self._migrate_v7_to_v8(target)
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 8:
                        self._migrate_v8_to_v9(target)
                        self._migrate_v9_to_v10(target)
                    elif version == 9:
                        self._migrate_v9_to_v10(target)
                    target.execute("PRAGMA journal_mode = WAL")
                    target.execute("PRAGMA foreign_keys = ON")
                    self._verify_schema(target)
                    integrity = str(target.execute("PRAGMA integrity_check").fetchone()[0]).lower()
                    if integrity != "ok":
                        raise StateStoreError(
                            "state_restore_integrity_failed",
                            "Runtime-state restore source failed its integrity check",
                        )
                    backup_metadata = target.execute(
                        "SELECT * FROM authority_metadata WHERE singleton = 1"
                    ).fetchone()
                    if backup_metadata is None:
                        raise StateStoreError(
                            "state_authority_metadata_missing",
                            "Runtime-state restore source lacks authority metadata",
                        )
                    restored_from_uuid = str(backup_metadata["instance_uuid"])
                    pre_highwater = max(
                        pre_highwater,
                        int(backup_metadata["authority_epoch"]),
                        int(backup_metadata["pre_restore_epoch_highwater"]),
                    )
                    new_instance_uuid = str(uuid.uuid4())
                    now = _timestamp(datetime.now(timezone.utc))
                    target.execute("BEGIN IMMEDIATE")
                    if active_row is not None:
                        target.execute(
                            "INSERT OR REPLACE INTO restore_operations VALUES "
                            "(?, 'superseded', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                str(active_row["operation_id"]),
                                str(active_row["source_digest"]),
                                str(active_row["restored_from_uuid"]),
                                str(active_row["instance_uuid"]),
                                int(active_row["pre_restore_epoch_highwater"]),
                                active_row["supersedes_operation_id"],
                                str(reason or active_row["reason"] or "superseded restore"),
                                str(active_row["scan_status"]),
                                active_row["scan_error_code"],
                                str(active_row["created_at"]),
                                now,
                            ),
                        )
                    if sentinel_operation and sentinel_operation != active_operation:
                        target.execute(
                            "INSERT OR IGNORE INTO restore_operations VALUES "
                            "(?, 'superseded', ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?)",
                            (
                                sentinel_operation,
                                str(sentinel_document.get("source_digest") or "unknown"),
                                str(live_metadata["instance_uuid"]),
                                str(live_metadata["instance_uuid"]),
                                max(
                                    pre_highwater,
                                    int(sentinel_document.get("pre_restore_epoch_highwater") or 0),
                                ),
                                sentinel_document.get("previous_operation_id"),
                                str(reason or "superseded interrupted restore"),
                                str(sentinel_document.get("created_at") or now),
                                now,
                            ),
                        )
                    target.execute(
                        "UPDATE restore_operations SET status = 'superseded', completed_at = ? "
                        "WHERE status = 'reconcile_required'",
                        (now,),
                    )
                    target.execute(
                        "INSERT INTO restore_operations VALUES "
                        "(?, 'reconcile_required', ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, NULL)",
                        (
                            operation_id,
                            source_digest,
                            restored_from_uuid,
                            new_instance_uuid,
                            pre_highwater,
                            sentinel_operation or active_operation,
                            str(reason).strip() if reason else None,
                            now,
                        ),
                    )
                    target.execute(
                        "UPDATE authority_metadata SET instance_uuid = ?, authority_epoch = ?, "
                        "reconcile_required = 1, reconcile_reason = ?, "
                        "active_restore_operation = ?, pre_restore_epoch_highwater = ?, "
                        "restored_from_uuid = ?, retention_emergency_stop = 1, "
                        "updated_at = ? WHERE singleton = 1",
                        (
                            new_instance_uuid,
                            pre_highwater + 1,
                            "state_restore_reconcile_required",
                            operation_id,
                            pre_highwater,
                            restored_from_uuid,
                            now,
                        ),
                    )
                    target.execute(
                        "UPDATE retention_category_states SET state = 'suspended', "
                        "version = version + 1, evidence_digest = NULL, "
                        "reason = 'restore requires retention reauthorization', updated_at = ?",
                        (now,),
                    )
                    target.execute(
                        "UPDATE identity_metadata SET status = 'recovery_pending', "
                        "recovery_reason = 'state restore requires local identity recovery', "
                        "updated_at = ? WHERE singleton = 1 AND status = 'active'",
                        (now,),
                    )
                    target.execute(
                        "UPDATE identity_sessions SET revoked_at = ?, revoked_by = 'system:restore' "
                        "WHERE revoked_at IS NULL",
                        (now,),
                    )
                    target.execute(
                        "UPDATE identity_tokens SET revoked_at = ?, revoked_by = 'system:restore' "
                        "WHERE revoked_at IS NULL",
                        (now,),
                    )
                    target.execute("COMMIT")
                    target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except BaseException:
                    if target.in_transaction:
                        target.execute("ROLLBACK")
                    raise
                finally:
                    target.close()
                    source_connection.close()

                if self._file_digest(source) != source_digest:
                    raise StateStoreError(
                        "state_restore_source_changed",
                        "Runtime-state restore source changed while it was being verified",
                    )
                for suffix in ("-wal", "-shm"):
                    with suppress(FileNotFoundError):
                        self.path.with_name(f"{self.path.name}{suffix}").unlink()
                os.replace(staging, self.path)
                self.path.chmod(0o600)
                directory_fd = os.open(self.data_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                self._sync_authority_witness(lifecycle=False)
                self.restore_sentinel_path.unlink()
                directory_fd = os.open(self.data_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except StateStoreError:
                raise
            except (OSError, sqlite3.Error) as exc:
                raise _translate_sqlite_error(exc) from exc
            finally:
                for candidate in (
                    staging,
                    staging.with_name(f"{staging.name}-wal"),
                    staging.with_name(f"{staging.name}-shm"),
                ):
                    with suppress(OSError):
                        candidate.unlink(missing_ok=True)

        operations = self.list_restore_operations()
        for operation in operations:
            if operation.operation_id == operation_id:
                return operation
        raise StateStoreError(
            "state_restore_operation_missing",
            "Runtime-state restore operation was not persisted",
        )


class SQLiteRetentionStateStore(IRetentionStateStore):
    """Read-only retention inventory plus append-only managed-backup registry."""

    def __init__(self, database: SQLiteStateStore) -> None:
        self._database = database

    def catalog(self) -> dict[str, tuple[str, ...]]:
        with self._database._connection() as connection:
            return {
                table: tuple(
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                )
                for table in self._database._table_names(connection)
            }

    def snapshot(self, table: str) -> RetentionTableSnapshot:
        if table not in _EXPECTED_TABLES:
            raise StateStoreError(
                "state_retention_table_unknown",
                "Retention inventory requested an unknown runtime-state table",
            )
        with self._database._connection() as connection:
            columns = tuple(
                str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
            rows = tuple(dict(row) for row in connection.execute(f"SELECT * FROM {table}"))
        return RetentionTableSnapshot(table=table, columns=columns, rows=rows)

    def register_managed_backup(self, record: ManagedBackupRecord) -> bool:
        identity = (
            record.backup_id,
            str(record.path),
            record.digest,
            record.instance_uuid,
            record.authority_epoch,
        )
        values = (*identity, _timestamp(record.created_at))
        with self._database._connection() as connection:
            existing = connection.execute(
                "SELECT backup_id, path, digest, instance_uuid, authority_epoch "
                "FROM managed_backups WHERE backup_id = ?",
                (record.backup_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == identity:
                    return False
                raise StateStoreConflict("managed backup", record.backup_id)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO managed_backups VALUES (?, ?, ?, ?, ?, ?)", values
                    )
            except sqlite3.IntegrityError as exc:
                raise StateStoreError(
                    "state_managed_backup_conflict",
                    "Managed backup path is already registered with different identity",
                ) from exc
        return True

    def list_managed_backups(self) -> list[ManagedBackupRecord]:
        with self._database._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM managed_backups ORDER BY created_at, backup_id"
            ).fetchall()
        return [
            ManagedBackupRecord(
                backup_id=str(row["backup_id"]),
                path=Path(str(row["path"])),
                digest=str(row["digest"]),
                instance_uuid=str(row["instance_uuid"]),
                authority_epoch=int(row["authority_epoch"]),
                created_at=_from_timestamp(str(row["created_at"])),
            )
            for row in rows
        ]

    def emergency_stop(self) -> bool:
        return bool(self._database._authority_metadata()["retention_emergency_stop"])


class SQLiteRetentionExecutionStore(IRetentionExecutionStore):
    """Transactional authority plus the single stage-5c deletion strategy."""

    _STATES = frozenset({"report_only", "enforce", "suspended"})

    def __init__(self, database: SQLiteStateStore) -> None:
        self._database = database
        self._authority = SQLiteAuthorityStateStore(database)

    @staticmethod
    def _category_state_from_row(row: sqlite3.Row) -> RetentionCategoryStateRecord:
        return RetentionCategoryStateRecord(
            category_id=str(row["category_id"]),
            category_digest=str(row["category_digest"]),
            profile_role_digest=str(row["profile_role_digest"]),
            state=cast(Any, str(row["state"])),
            version=int(row["version"]),
            evidence_digest=(
                str(row["evidence_digest"]) if row["evidence_digest"] is not None else None
            ),
            grant_cutoff_utc=(
                _from_timestamp(str(row["grant_cutoff_utc"]))
                if row["grant_cutoff_utc"] is not None
                else None
            ),
            activated_at=(
                _from_timestamp(str(row["activated_at"]))
                if row["activated_at"] is not None
                else None
            ),
            reason=str(row["reason"]),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    @staticmethod
    def _execution_from_row(row: sqlite3.Row) -> RetentionExecutionRecord:
        object_ids = json.loads(str(row["object_ids_json"]))
        if not isinstance(object_ids, list) or any(
            not isinstance(value, str) for value in object_ids
        ):
            raise StateStoreError(
                "state_retention_execution_invalid",
                "Retention execution receipt contains invalid object identities",
            )
        return RetentionExecutionRecord(
            execution_id=str(row["execution_id"]),
            category_id=str(row["category_id"]),
            plan_digest=str(row["plan_digest"]),
            category_digest=str(row["category_digest"]),
            profile_role_digest=str(row["profile_role_digest"]),
            cutoff_utc=_from_timestamp(str(row["cutoff_utc"])),
            anchor=str(row["anchor"]),
            object_ids=tuple(object_ids),
            candidate_count=int(row["candidate_count"]),
            deleted_count=int(row["deleted_count"]),
            status=cast(Any, str(row["status"])),
            reason=str(row["reason"]),
            authority_epoch=int(row["authority_epoch"]),
            executed_at=_from_timestamp(str(row["executed_at"])),
        )

    def get_category_state(self, category_id: str) -> RetentionCategoryStateRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM retention_category_states WHERE category_id = ?",
                (category_id,),
            ).fetchone()
        return self._category_state_from_row(row) if row is not None else None

    def list_category_states(self) -> list[RetentionCategoryStateRecord]:
        with self._database._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM retention_category_states ORDER BY category_id"
            ).fetchall()
        return [self._category_state_from_row(row) for row in rows]

    def transition_category(
        self,
        *,
        category_id: str,
        category_digest: str,
        profile_role_digest: str,
        state: str,
        reason: str,
        evidence_digest: str | None = None,
        grant_cutoff_utc: datetime | None = None,
        activated_at: datetime | None = None,
    ) -> AuthorityWriteResult:
        normalized_reason = reason.strip()
        if not category_id or state not in self._STATES or not normalized_reason:
            raise StateStoreError(
                "state_retention_transition_invalid",
                "Retention category transition is incomplete or invalid",
            )
        if not _SHA256_DIGEST.fullmatch(category_digest) or not _SHA256_DIGEST.fullmatch(
            profile_role_digest
        ):
            raise StateStoreError(
                "state_retention_digest_invalid",
                "Retention category transitions require SHA-256 policy digests",
            )
        if evidence_digest is not None and not _SHA256_DIGEST.fullmatch(evidence_digest):
            raise StateStoreError(
                "state_retention_digest_invalid",
                "Retention category evidence must be a SHA-256 digest",
            )
        if state == "enforce" and category_id != "score_derivations":
            raise StateStoreError(
                "state_retention_category_not_allowlisted",
                "Retention category has no registered deletion strategy",
            )
        if state == "enforce" and not evidence_digest:
            raise StateStoreError(
                "state_retention_evidence_required",
                "Retention enforcement requires a bound plan digest",
            )
        if state == "enforce" and (
            not isinstance(grant_cutoff_utc, datetime)
            or grant_cutoff_utc.tzinfo is None
            or grant_cutoff_utc.utcoffset() is None
        ):
            raise StateStoreError(
                "state_retention_grant_invalid",
                "Retention enforcement requires a timezone-aware grant cutoff",
            )
        if state == "enforce" and (
            not isinstance(activated_at, datetime)
            or activated_at.tzinfo is None
            or activated_at.utcoffset() is None
        ):
            raise StateStoreError(
                "state_retention_grant_invalid",
                "Retention enforcement requires a timezone-aware activation time",
            )
        if state != "enforce" and (grant_cutoff_utc is not None or activated_at is not None):
            raise StateStoreError(
                "state_retention_grant_invalid",
                "Only retention enforcement may bind a grant cutoff",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT * FROM retention_category_states WHERE category_id = ?",
                (category_id,),
            ).fetchone()
            now = _timestamp(datetime.now(timezone.utc))
            normalized_cutoff = (
                _timestamp(grant_cutoff_utc.astimezone(timezone.utc))
                if grant_cutoff_utc is not None
                else None
            )
            normalized_activation = (
                _timestamp(activated_at.astimezone(timezone.utc))
                if activated_at is not None
                else None
            )
            target = (
                category_digest,
                profile_role_digest,
                state,
                evidence_digest,
                normalized_cutoff,
                normalized_activation,
                normalized_reason,
            )
            if (
                existing is not None
                and (
                    str(existing["category_digest"]),
                    str(existing["profile_role_digest"]),
                    str(existing["state"]),
                    existing["evidence_digest"],
                    existing["grant_cutoff_utc"],
                    existing["activated_at"],
                    str(existing["reason"]),
                )
                == target
            ):
                return False
            version = int(existing["version"]) + 1 if existing is not None else 1
            connection.execute(
                "INSERT INTO retention_category_states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(category_id) DO UPDATE SET category_digest=excluded.category_digest, "
                "profile_role_digest=excluded.profile_role_digest, state=excluded.state, "
                "version=excluded.version, evidence_digest=excluded.evidence_digest, "
                "grant_cutoff_utc=excluded.grant_cutoff_utc, "
                "activated_at=excluded.activated_at, "
                "reason=excluded.reason, updated_at=excluded.updated_at",
                (
                    category_id,
                    category_digest,
                    profile_role_digest,
                    state,
                    version,
                    evidence_digest,
                    normalized_cutoff,
                    normalized_activation,
                    normalized_reason,
                    now,
                ),
            )
            metadata = connection.execute(
                "SELECT authority_epoch FROM authority_metadata WHERE singleton = 1"
            ).fetchone()
            if metadata is None:
                raise StateStoreError(
                    "state_authority_metadata_missing",
                    "Runtime-state authority metadata is missing",
                )
            payload = {
                "category": category_id,
                "category_digest": category_digest,
                "profile_role_digest": profile_role_digest,
                "state": state,
                "version": version,
                "evidence_digest": evidence_digest,
                "grant_cutoff_utc": normalized_cutoff,
                "activated_at": normalized_activation,
                "reason": normalized_reason,
                "authority_epoch": int(metadata["authority_epoch"]) + 1,
            }
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            record_key = (
                "sha256:"
                + hashlib.sha256(
                    ("retention-category-transition.v1:" + encoded).encode("utf-8")
                ).hexdigest()
            )
            connection.execute(
                "INSERT INTO authority_records VALUES (?, 'retention_category_transition.v1', ?, ?)",
                (record_key, encoded, now),
            )
            return True

        return self._authority._transition(mutate)

    def set_emergency_stop(self, enabled: bool, *, reason: str) -> AuthorityWriteResult:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise StateStoreError(
                "state_retention_reason_required",
                "Retention emergency-stop transition requires an operator reason",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            metadata = connection.execute(
                "SELECT retention_emergency_stop, authority_epoch FROM authority_metadata "
                "WHERE singleton = 1"
            ).fetchone()
            if metadata is None:
                raise StateStoreError(
                    "state_authority_metadata_missing",
                    "Runtime-state authority metadata is missing",
                )
            if bool(metadata["retention_emergency_stop"]) == enabled:
                return False
            now = _timestamp(datetime.now(timezone.utc))
            connection.execute(
                "UPDATE authority_metadata SET retention_emergency_stop = ?, updated_at = ? "
                "WHERE singleton = 1",
                (int(enabled), now),
            )
            payload = {
                "enabled": enabled,
                "reason": normalized_reason,
                "authority_epoch": int(metadata["authority_epoch"]) + 1,
            }
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            record_key = (
                "sha256:"
                + hashlib.sha256(
                    ("retention-emergency-stop.v1:" + encoded).encode("utf-8")
                ).hexdigest()
            )
            connection.execute(
                "INSERT INTO authority_records VALUES (?, 'retention_emergency_stop.v1', ?, ?)",
                (record_key, encoded, now),
            )
            return True

        return self._authority._transition(mutate)

    def execute_score_derivations(
        self,
        *,
        plan_digest: str,
        category_digest: str,
        profile_role_digest: str,
        cutoff_utc: datetime,
        anchor: str,
        object_ids: tuple[str, ...],
        field_classification: Mapping[str, str],
        payload_classification: Mapping[str, str],
        reason: str,
    ) -> RetentionExecutionRecord:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise StateStoreError(
                "state_retention_reason_required",
                "Retention execution requires an operator reason",
            )
        if not isinstance(cutoff_utc, datetime) or cutoff_utc.tzinfo is None:
            raise StateStoreError(
                "state_retention_cutoff_invalid",
                "Retention execution requires a timezone-aware cutoff",
            )
        if cutoff_utc.utcoffset() is None:
            raise StateStoreError(
                "state_retention_cutoff_invalid",
                "Retention execution requires a timezone-aware cutoff",
            )
        if anchor != "derived_at":
            raise StateStoreError(
                "state_retention_anchor_invalid",
                "Score-derivation retention requires the derived_at anchor",
            )
        if any(
            not _SHA256_DIGEST.fullmatch(value)
            for value in (plan_digest, category_digest, profile_role_digest)
        ):
            raise StateStoreError(
                "state_retention_digest_invalid",
                "Retention execution requires SHA-256 plan and policy digests",
            )
        cutoff = cutoff_utc.astimezone(timezone.utc)
        with self._database._lifecycle_lock():
            self._database._assert_restore_complete()
            with self._database._connection(lifecycle=False) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT * FROM retention_executions WHERE plan_digest = ?",
                        (plan_digest,),
                    ).fetchone()
                    if existing is not None:
                        existing_receipt = self._execution_from_row(existing)
                        bound_digest = retention_plan_digest(
                            category_id=existing_receipt.category_id,
                            category_digest=existing_receipt.category_digest,
                            profile_role_digest=existing_receipt.profile_role_digest,
                            cutoff_utc=existing_receipt.cutoff_utc,
                            anchor=existing_receipt.anchor,
                            object_ids=existing_receipt.object_ids,
                        )
                        if (
                            str(existing["category_id"]) != "score_derivations"
                            or str(existing["category_digest"]) != category_digest
                            or str(existing["profile_role_digest"]) != profile_role_digest
                            or str(existing["cutoff_utc"]) != _timestamp(cutoff)
                            or str(existing["anchor"]) != anchor
                            or bound_digest != plan_digest
                        ):
                            raise StateStoreConflict("retention execution", plan_digest)
                        connection.execute("COMMIT")
                        self._database._sync_authority_witness(lifecycle=False)
                        return existing_receipt
                    metadata = connection.execute(
                        "SELECT authority_epoch, reconcile_required, retention_emergency_stop "
                        "FROM authority_metadata WHERE singleton = 1"
                    ).fetchone()
                    if metadata is None:
                        raise StateStoreError(
                            "state_authority_metadata_missing",
                            "Runtime-state authority metadata is missing",
                        )
                    if bool(metadata["reconcile_required"]):
                        raise StateStoreError(
                            "state_reconcile_required",
                            "Runtime-state reconcile blocks retention execution",
                        )
                    if bool(metadata["retention_emergency_stop"]):
                        raise StateStoreError(
                            "state_retention_emergency_stop",
                            "Retention emergency stop blocks execution",
                        )
                    state = connection.execute(
                        "SELECT * FROM retention_category_states WHERE category_id = 'score_derivations'"
                    ).fetchone()
                    if (
                        state is None
                        or str(state["state"]) != "enforce"
                        or str(state["category_digest"]) != category_digest
                        or str(state["profile_role_digest"]) != profile_role_digest
                        or str(state["evidence_digest"] or "") != plan_digest
                        or state["grant_cutoff_utc"] is None
                        or str(state["grant_cutoff_utc"]) != _timestamp(cutoff)
                        or state["activated_at"] is None
                    ):
                        raise StateStoreError(
                            "state_retention_authority_invalid",
                            "Retention category is not authorized for this exact plan",
                        )
                    actual_columns = {
                        str(row[1])
                        for row in connection.execute(
                            "PRAGMA table_info(score_derivations)"
                        ).fetchall()
                    }
                    if (
                        actual_columns != set(field_classification)
                        or field_classification.get("payload_json")
                        != "not_automatically_verifiable"
                        or dict(payload_classification) != {"$": "not_automatically_verifiable"}
                    ):
                        raise StateStoreError(
                            "state_retention_classification_invalid",
                            "Retention classification does not match the current storage contract",
                        )
                    actual_ids = tuple(
                        str(row[0])
                        for row in connection.execute(
                            "SELECT score_key FROM score_derivations WHERE derived_at < ? "
                            "ORDER BY score_key",
                            (_timestamp(cutoff),),
                        ).fetchall()
                    )
                    expected_digest = retention_plan_digest(
                        category_id="score_derivations",
                        category_digest=category_digest,
                        profile_role_digest=profile_role_digest,
                        cutoff_utc=cutoff,
                        anchor=anchor,
                        object_ids=actual_ids,
                    )
                    if not actual_ids:
                        raise StateStoreError(
                            "state_retention_plan_empty",
                            "Retention execution plan contains no current candidates",
                        )
                    if actual_ids != tuple(sorted(object_ids)) or expected_digest != plan_digest:
                        raise StateStoreError(
                            "state_retention_plan_drift",
                            "Retention candidates changed after the approved dry run",
                        )
                    deleted = connection.execute(
                        "DELETE FROM score_derivations WHERE derived_at < ?",
                        (_timestamp(cutoff),),
                    ).rowcount
                    if deleted != len(actual_ids):
                        raise StateStoreError(
                            "state_retention_delete_mismatch",
                            "Retention deletion did not match the bound candidate set",
                        )
                    epoch = int(metadata["authority_epoch"]) + 1
                    now = _timestamp(datetime.now(timezone.utc))
                    connection.execute(
                        "INSERT INTO retention_executions VALUES (?, 'score_derivations', ?, ?, ?, "
                        "?, ?, ?, ?, ?, 'completed', ?, ?, ?)",
                        (
                            plan_digest,
                            plan_digest,
                            category_digest,
                            profile_role_digest,
                            _timestamp(cutoff),
                            anchor,
                            json.dumps(actual_ids, separators=(",", ":")),
                            len(actual_ids),
                            deleted,
                            normalized_reason,
                            epoch,
                            now,
                        ),
                    )
                    connection.execute(
                        "UPDATE authority_metadata SET authority_epoch = ?, updated_at = ? "
                        "WHERE singleton = 1",
                        (epoch, now),
                    )
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
            self._database._sync_authority_witness(lifecycle=False)
        result = self.list_executions("score_derivations")
        for record in result:
            if record.plan_digest == plan_digest:
                return record
        raise StateStoreError(
            "state_retention_execution_missing",
            "Completed retention execution receipt is missing",
        )

    def get_execution(self, plan_digest: str) -> RetentionExecutionRecord | None:
        if not _SHA256_DIGEST.fullmatch(plan_digest):
            raise StateStoreError(
                "state_retention_digest_invalid",
                "Retention receipt lookup requires a SHA-256 plan digest",
            )
        with self._database._lifecycle_lock():
            self._database._assert_restore_complete()
            with self._database._connection(lifecycle=False) as connection:
                row = connection.execute(
                    "SELECT * FROM retention_executions WHERE plan_digest = ?",
                    (plan_digest,),
                ).fetchone()
        if row is None:
            return None
        record = self._execution_from_row(row)
        try:
            bound_digest = retention_plan_digest(
                category_id=record.category_id,
                category_digest=record.category_digest,
                profile_role_digest=record.profile_role_digest,
                cutoff_utc=record.cutoff_utc,
                anchor=record.anchor,
                object_ids=record.object_ids,
            )
        except RetentionError as exc:
            raise StateStoreError(
                "state_retention_execution_invalid",
                "Retention execution receipt does not match its bound identity",
            ) from exc
        if (
            bound_digest != plan_digest
            or record.execution_id != plan_digest
            or not _SHA256_DIGEST.fullmatch(record.category_digest)
            or not _SHA256_DIGEST.fullmatch(record.profile_role_digest)
            or record.candidate_count != len(record.object_ids)
            or record.deleted_count != record.candidate_count
        ):
            raise StateStoreError(
                "state_retention_execution_invalid",
                "Retention execution receipt does not match its bound identity",
            )
        return record

    def list_executions(self, category_id: str | None = None) -> list[RetentionExecutionRecord]:
        query = "SELECT * FROM retention_executions"
        parameters: tuple[Any, ...] = ()
        if category_id is not None:
            query += " WHERE category_id = ?"
            parameters = (category_id,)
        query += " ORDER BY executed_at, execution_id"
        with self._database._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._execution_from_row(row) for row in rows]


class SQLiteObservationStore(IObservationStore):
    def __init__(self, database: SQLiteStateStore) -> None:
        self._database = database

    def put_observation(self, record: ObservationRecord) -> bool:
        identity_values = (
            record.observation_key,
            record.subject_key,
            record.evidence_digest,
            record.observation_schema,
            record.issue_number,
            record.evidence_origin,
            _json(record.payload),
        )
        values = (
            *identity_values,
            _timestamp(record.observed_at),
        )
        with self._database._connection() as connection:
            existing = connection.execute(
                "SELECT observation_key, subject_key, evidence_digest, observation_schema, "
                "issue_number, evidence_origin, payload_json "
                "FROM observations WHERE observation_key = ?",
                (record.observation_key,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == identity_values:
                    return False
                raise StateStoreConflict("observation", record.observation_key)
            with connection:
                connection.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values
                )
        return True

    def get_observation(self, observation_key: str) -> ObservationRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM observations WHERE observation_key = ?", (observation_key,)
            ).fetchone()
        if row is None:
            return None
        return ObservationRecord(
            observation_key=str(row["observation_key"]),
            subject_key=str(row["subject_key"]),
            evidence_digest=str(row["evidence_digest"]),
            observation_schema=str(row["observation_schema"]),
            payload=json.loads(str(row["payload_json"])),
            issue_number=int(row["issue_number"]),
            evidence_origin=str(row["evidence_origin"]),
            observed_at=_from_timestamp(str(row["observed_at"])),
        )

    def list_observations(self, issue_number: int | None = None) -> list[ObservationRecord]:
        query = "SELECT * FROM observations"
        parameters: tuple[object, ...] = ()
        if issue_number is not None:
            query += " WHERE issue_number = ?"
            parameters = (int(issue_number),)
        query += " ORDER BY observed_at, observation_key"
        with self._database._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._observation_from_row(row) for row in rows]

    @staticmethod
    def _observation_from_row(row: sqlite3.Row) -> ObservationRecord:
        return ObservationRecord(
            observation_key=str(row["observation_key"]),
            subject_key=str(row["subject_key"]),
            evidence_digest=str(row["evidence_digest"]),
            observation_schema=str(row["observation_schema"]),
            payload=json.loads(str(row["payload_json"])),
            issue_number=int(row["issue_number"]),
            evidence_origin=str(row["evidence_origin"]),
            observed_at=_from_timestamp(str(row["observed_at"])),
        )

    def put_derivation(self, record: ScoreDerivationRecord) -> bool:
        identity_values = (
            record.score_key,
            record.observation_key,
            record.scoring_policy_version,
            record.scoring_policy_digest,
            record.formula_version,
            record.issue_number,
            record.evidence_origin,
            record.observation_schema,
            record.score,
            _json(record.payload),
        )
        values = (
            *identity_values,
            _timestamp(record.derived_at),
        )
        with self._database._connection() as connection:
            existing = connection.execute(
                "SELECT score_key, observation_key, scoring_policy_version, "
                "scoring_policy_digest, formula_version, issue_number, evidence_origin, "
                "observation_schema, score, payload_json "
                "FROM score_derivations WHERE score_key = ?",
                (record.score_key,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == identity_values:
                    return False
                raise StateStoreConflict("score derivation", record.score_key)
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO score_derivations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        values,
                    )
            except sqlite3.IntegrityError as exc:
                raise StateStoreError(
                    "state_observation_missing",
                    "Score derivation requires its bound observation",
                ) from exc
        return True

    def get_derivation(self, score_key: str) -> ScoreDerivationRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM score_derivations WHERE score_key = ?", (score_key,)
            ).fetchone()
        if row is None:
            return None
        return ScoreDerivationRecord(
            score_key=str(row["score_key"]),
            observation_key=str(row["observation_key"]),
            scoring_policy_version=str(row["scoring_policy_version"]),
            scoring_policy_digest=str(row["scoring_policy_digest"]),
            formula_version=str(row["formula_version"]),
            score=float(row["score"]) if row["score"] is not None else None,
            payload=json.loads(str(row["payload_json"])),
            issue_number=int(row["issue_number"]),
            evidence_origin=str(row["evidence_origin"]),
            observation_schema=str(row["observation_schema"]),
            derived_at=_from_timestamp(str(row["derived_at"])),
        )

    def list_derivations(
        self,
        issue_number: int | None = None,
    ) -> list[ScoreDerivationRecord]:
        query = "SELECT * FROM score_derivations"
        parameters: tuple[object, ...] = ()
        if issue_number is not None:
            query += " WHERE issue_number = ?"
            parameters = (int(issue_number),)
        query += " ORDER BY derived_at, score_key"
        with self._database._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._derivation_from_row(row) for row in rows]

    @staticmethod
    def _derivation_from_row(row: sqlite3.Row) -> ScoreDerivationRecord:
        return ScoreDerivationRecord(
            score_key=str(row["score_key"]),
            observation_key=str(row["observation_key"]),
            scoring_policy_version=str(row["scoring_policy_version"]),
            scoring_policy_digest=str(row["scoring_policy_digest"]),
            formula_version=str(row["formula_version"]),
            score=float(row["score"]) if row["score"] is not None else None,
            payload=json.loads(str(row["payload_json"])),
            issue_number=int(row["issue_number"]),
            evidence_origin=str(row["evidence_origin"]),
            observation_schema=str(row["observation_schema"]),
            derived_at=_from_timestamp(str(row["derived_at"])),
        )

    def put_terminal(self, record: EvaluationTerminalRecord) -> bool:
        identity_values = (
            record.terminal_key,
            record.issue_number,
            record.status,
            _json(record.payload),
        )
        values = (*identity_values, _timestamp(record.observed_at))
        with self._database._connection() as connection:
            existing = connection.execute(
                "SELECT terminal_key, issue_number, status, payload_json "
                "FROM evaluation_terminals WHERE terminal_key = ?",
                (record.terminal_key,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == identity_values:
                    return False
                raise StateStoreConflict("evaluation terminal", record.terminal_key)
            with connection:
                connection.execute(
                    "INSERT INTO evaluation_terminals VALUES (?, ?, ?, ?, ?)", values
                )
        return True

    def get_terminal(self, terminal_key: str) -> EvaluationTerminalRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM evaluation_terminals WHERE terminal_key = ?",
                (terminal_key,),
            ).fetchone()
        return self._terminal_from_row(row) if row is not None else None

    def list_terminals(
        self,
        issue_number: int | None = None,
    ) -> list[EvaluationTerminalRecord]:
        query = "SELECT * FROM evaluation_terminals"
        parameters: tuple[object, ...] = ()
        if issue_number is not None:
            query += " WHERE issue_number = ?"
            parameters = (int(issue_number),)
        query += " ORDER BY observed_at, terminal_key"
        with self._database._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._terminal_from_row(row) for row in rows]

    @staticmethod
    def _terminal_from_row(row: sqlite3.Row) -> EvaluationTerminalRecord:
        return EvaluationTerminalRecord(
            terminal_key=str(row["terminal_key"]),
            issue_number=int(row["issue_number"]),
            status=str(row["status"]),
            payload=json.loads(str(row["payload_json"])),
            observed_at=_from_timestamp(str(row["observed_at"])),
        )


class SQLiteRunProjectionStore(IRunProjectionStore):
    def __init__(self, database: SQLiteStateStore) -> None:
        self._database = database

    def upsert_projection(self, record: RunProjectionRecord) -> None:
        values = (
            record.projection_key,
            record.issue_number,
            record.correlation_id,
            record.series,
            record.status,
            _json(record.payload),
            _timestamp(record.updated_at),
        )
        try:
            with self._database._connection() as connection, connection:
                connection.execute(
                    """
                    INSERT INTO run_projections VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(projection_key) DO UPDATE SET
                        issue_number = excluded.issue_number,
                        correlation_id = excluded.correlation_id,
                        series = excluded.series,
                        status = excluded.status,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    values,
                )
        except StateStoreError as exc:
            self._database._projection_error_code = exc.code
            raise
        self._database._projection_error_code = None

    def get_projection(self, projection_key: str) -> RunProjectionRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM run_projections WHERE projection_key = ?", (projection_key,)
            ).fetchone()
        if row is None:
            return None
        return RunProjectionRecord(
            projection_key=str(row["projection_key"]),
            issue_number=int(row["issue_number"]),
            correlation_id=str(row["correlation_id"]),
            series=str(row["series"]),
            status=str(row["status"]),
            payload=json.loads(str(row["payload_json"])),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_projections(
        self,
        issue_number: int | None = None,
        *,
        series: str | None = None,
    ) -> list[RunProjectionRecord]:
        clauses: list[str] = []
        parameters: list[object] = []
        if issue_number is not None:
            clauses.append("issue_number = ?")
            parameters.append(int(issue_number))
        if series is not None:
            clauses.append("series = ?")
            parameters.append(series)
        query = "SELECT * FROM run_projections"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at, projection_key"
        with self._database._connection() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [
            RunProjectionRecord(
                projection_key=str(row["projection_key"]),
                issue_number=int(row["issue_number"]),
                correlation_id=str(row["correlation_id"]),
                series=str(row["series"]),
                status=str(row["status"]),
                payload=json.loads(str(row["payload_json"])),
                updated_at=_from_timestamp(str(row["updated_at"])),
            )
            for row in rows
        ]


class SQLiteQualityMetricsRegistry(IQualityMetricsRegistry):
    """Recency-weighted quality projection separated by exact score series."""

    def __init__(self, database: SQLiteStateStore, alpha: float = 0.3) -> None:
        self._database = database
        self._alpha = alpha

    @staticmethod
    def _series(metadata: dict[str, Any] | None) -> tuple[str, str, str, str]:
        if metadata and metadata.get("evidence_origin") == "bound_acceptance_evidence":
            return (
                "bound_acceptance_evidence",
                str(metadata.get("observation_schema", "bound.v1")),
                str(metadata.get("scoring_policy_version", "unknown")),
                str(metadata.get("formula_version", "unknown")),
            )
        return ("unbound_worktree", "legacy.v1", "legacy", "legacy")

    @staticmethod
    def _key(
        provider: str,
        model: str,
        task: str,
        series: tuple[str, str, str, str],
    ) -> str:
        import hashlib

        raw = _json(
            {
                "provider": provider,
                "model": model,
                "task": task,
                "evidence_origin": series[0],
                "observation_schema": series[1],
                "scoring_policy_version": series[2],
                "formula_version": series[3],
            }
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(raw).hexdigest()}"

    def record(
        self,
        provider: str,
        model: str,
        task: str,
        score: float,
        passed: bool | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        series = self._series(metadata)
        key = self._key(provider, model, task, series)
        now = datetime.now(timezone.utc)
        with self._database._connection() as connection, connection:
            row = connection.execute(
                "SELECT payload_json FROM quality_metrics WHERE metric_key = ?", (key,)
            ).fetchone()
            if row is None:
                entry: dict[str, Any] = {
                    "provider": provider,
                    "model": model,
                    "task": task,
                    "evidence_origin": series[0],
                    "observation_schema": series[1],
                    "scoring_policy_version": series[2],
                    "formula_version": series[3],
                    "ewma_score": float(score),
                    "count": 0,
                    "passed": 0,
                    "failed": 0,
                    "observed": 0,
                    "last_score": float(score),
                    "last_ts": "",
                }
            else:
                entry = json.loads(str(row["payload_json"]))
                previous = float(entry.get("ewma_score", score))
                entry["ewma_score"] = round(
                    self._alpha * float(score) + (1 - self._alpha) * previous,
                    4,
                )
            entry["count"] = int(entry.get("count", 0)) + 1
            bucket = "passed" if passed is True else "failed" if passed is False else "observed"
            entry[bucket] = int(entry.get(bucket, 0)) + 1
            entry["last_score"] = float(score)
            entry["last_ts"] = _timestamp(now)
            if metadata:
                entry["last_observation"] = dict(metadata)
            values = (
                key,
                provider,
                model,
                task,
                *series,
                _json(entry),
                _timestamp(now),
            )
            connection.execute(
                """
                INSERT INTO quality_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(metric_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                values,
            )

    def import_aggregate(self, entry: dict[str, Any]) -> bool:
        """Import one already-aggregated legacy row without replaying EWMA."""

        provider = str(entry.get("provider", ""))
        model = str(entry.get("model", ""))
        task = str(entry.get("task", ""))
        if not provider or not model or not task:
            raise StateStoreError(
                "state_legacy_invalid",
                "Legacy quality metric has no provider, model or task identity",
            )
        origin = str(entry.get("evidence_origin", "unbound_worktree"))
        series = (
            origin,
            str(
                entry.get("observation_schema")
                or ("bound.v1" if origin == "bound_acceptance_evidence" else "legacy.v1")
            ),
            str(entry.get("scoring_policy_version", "legacy")),
            str(entry.get("formula_version", "legacy")),
        )
        normalized = {
            **entry,
            "evidence_origin": series[0],
            "observation_schema": series[1],
            "scoring_policy_version": series[2],
            "formula_version": series[3],
        }
        key = self._key(provider, model, task, series)
        timestamp = str(entry.get("last_ts", "")) or _timestamp(datetime.now(timezone.utc))
        try:
            updated_at = _from_timestamp(timestamp)
        except ValueError:
            updated_at = datetime.now(timezone.utc)
        values = (
            key,
            provider,
            model,
            task,
            *series,
            _json(normalized),
            _timestamp(updated_at),
        )
        with self._database._connection() as connection:
            existing = connection.execute(
                "SELECT provider, model, task, evidence_origin, observation_schema, "
                "scoring_policy_version, formula_version, payload_json "
                "FROM quality_metrics WHERE metric_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == values[1:9]:
                    return False
                raise StateStoreConflict("quality metric", key)
            with connection:
                connection.execute(
                    "INSERT INTO quality_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
        return True

    def score_for(self, provider: str, model: str, task: str) -> float | None:
        with self._database._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM quality_metrics "
                "WHERE provider = ? AND model = ? AND task = ? ORDER BY updated_at DESC",
                (provider, model, task),
            ).fetchall()
        for row in rows:
            entry = json.loads(str(row["payload_json"]))
            value = entry.get("ewma_score")
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def aggregates(self) -> list[dict]:
        with self._database._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM quality_metrics ORDER BY updated_at DESC"
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            entry = json.loads(str(row["payload_json"]))
            graded = int(entry.get("passed", 0)) + int(entry.get("failed", 0))
            result.append(
                {
                    **entry,
                    "count": int(entry.get("count", 0)),
                    "passed": int(entry.get("passed", 0)),
                    "failed": int(entry.get("failed", 0)),
                    "observed": int(entry.get("observed", 0)),
                    "success_rate_pct": (
                        round(int(entry.get("passed", 0)) / graded * 100) if graded else None
                    ),
                }
            )
        return result


class SQLiteAuthorityStateStore(IAuthorityStateStore):
    def __init__(self, database: SQLiteStateStore) -> None:
        self._database = database

    def _transition(self, mutate: Any) -> AuthorityWriteResult:
        with self._database._lifecycle_lock():
            self._database._assert_restore_complete()
            with self._database._connection(lifecycle=False) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    changed = bool(mutate(connection))
                    metadata = connection.execute(
                        "SELECT instance_uuid, authority_epoch FROM authority_metadata "
                        "WHERE singleton = 1"
                    ).fetchone()
                    if metadata is None:
                        raise StateStoreError(
                            "state_authority_metadata_missing",
                            "Runtime-state authority metadata is missing",
                        )
                    if changed:
                        now = _timestamp(datetime.now(timezone.utc))
                        connection.execute(
                            "UPDATE authority_metadata SET authority_epoch = authority_epoch + 1, "
                            "updated_at = ? WHERE singleton = 1",
                            (now,),
                        )
                        metadata = connection.execute(
                            "SELECT instance_uuid, authority_epoch FROM authority_metadata "
                            "WHERE singleton = 1"
                        ).fetchone()
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
                assert metadata is not None
                epoch = int(metadata["authority_epoch"])
            if changed:
                self._database._sync_authority_witness(lifecycle=False)
        return AuthorityWriteResult(changed=changed, authority_epoch=epoch)

    def put_authority_record(self, record: AuthorityRecord) -> bool:
        values = (
            record.record_key,
            record.kind,
            _json(record.payload),
            _timestamp(record.updated_at),
        )

        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT record_key, kind, payload_json, updated_at "
                "FROM authority_records WHERE record_key = ?",
                (record.record_key,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["record_key"]) == record.record_key
                    and str(existing["kind"]) == record.kind
                    and str(existing["payload_json"]) == _json(record.payload)
                ):
                    return False
                raise StateStoreConflict("authority", record.record_key)
            connection.execute("INSERT INTO authority_records VALUES (?, ?, ?, ?)", values)
            return True

        return self._transition(mutate).changed

    def get_authority_record(self, record_key: str) -> AuthorityRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM authority_records WHERE record_key = ?", (record_key,)
            ).fetchone()
        if row is None:
            return None
        return AuthorityRecord(
            record_key=str(row["record_key"]),
            kind=str(row["kind"]),
            payload=json.loads(str(row["payload_json"])),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_authority_records(self) -> list[AuthorityRecord]:
        with self._database._connection() as connection:
            keys = [
                str(row[0])
                for row in connection.execute(
                    "SELECT record_key FROM authority_records ORDER BY updated_at, record_key"
                ).fetchall()
            ]
        return [record for key in keys if (record := self.get_authority_record(key)) is not None]

    def claim_healing(self, record: HealingClaimRecord) -> AuthorityWriteResult:
        if record.status != "claimed":
            raise StateStoreError(
                "state_claim_transition_invalid",
                "A new healing claim must start in claimed state",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            inserted = connection.execute(
                "INSERT OR IGNORE INTO healing_claims VALUES (?, ?, ?, 'claimed', NULL, NULL, ?)",
                (
                    record.observation_key,
                    record.issue_number,
                    record.correlation_id,
                    _timestamp(record.updated_at),
                ),
            )
            if inserted.rowcount == 1:
                return True
            existing = connection.execute(
                "SELECT issue_number FROM healing_claims WHERE observation_key = ?",
                (record.observation_key,),
            ).fetchone()
            if existing is None or int(existing["issue_number"]) != record.issue_number:
                raise StateStoreConflict("healing claim", record.observation_key)
            return False

        return self._transition(mutate)

    def finish_healing(
        self,
        observation_key: str,
        *,
        status: str,
        outcome: str | None = None,
        reason: str | None = None,
    ) -> AuthorityWriteResult:
        if status not in {"attempted", "abandoned"}:
            raise StateStoreError(
                "state_claim_transition_invalid",
                "Healing claim can only finish as attempted or abandoned",
            )
        if status == "abandoned" and not str(reason or "").strip():
            raise StateStoreError(
                "state_claim_reason_required",
                "Abandoning a healing claim requires an operator reason",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT status, outcome, reason FROM healing_claims WHERE observation_key = ?",
                (observation_key,),
            ).fetchone()
            if row is None:
                raise StateStoreError(
                    "state_claim_missing",
                    "Healing claim does not exist",
                )
            current = (str(row["status"]), row["outcome"], row["reason"])
            target = (status, outcome, reason)
            if current == target:
                return False
            if current[0] != "claimed":
                raise StateStoreConflict("healing claim", observation_key)
            connection.execute(
                "UPDATE healing_claims SET status = ?, outcome = ?, reason = ?, updated_at = ? "
                "WHERE observation_key = ? AND status = 'claimed'",
                (
                    status,
                    outcome,
                    reason,
                    _timestamp(datetime.now(timezone.utc)),
                    observation_key,
                ),
            )
            return True

        return self._transition(mutate)

    def get_healing_claim(self, observation_key: str) -> HealingClaimRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM healing_claims WHERE observation_key = ?", (observation_key,)
            ).fetchone()
        if row is None:
            return None
        return HealingClaimRecord(
            observation_key=str(row["observation_key"]),
            issue_number=int(row["issue_number"]),
            correlation_id=str(row["correlation_id"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            outcome=str(row["outcome"]) if row["outcome"] is not None else None,
            reason=str(row["reason"]) if row["reason"] is not None else None,
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_healing_claims(self) -> list[HealingClaimRecord]:
        with self._database._connection() as connection:
            keys = [
                str(row[0])
                for row in connection.execute(
                    "SELECT observation_key FROM healing_claims "
                    "ORDER BY updated_at, observation_key"
                ).fetchall()
            ]
        return [claim for key in keys if (claim := self.get_healing_claim(key)) is not None]

    def put_checkpoint(self, record: WorkflowCheckpointRecord) -> AuthorityWriteResult:
        values = (
            record.checkpoint_key,
            record.issue_number,
            record.correlation_id,
            record.workflow,
            record.boundary,
            record.repository,
            record.branch,
            record.base_ref,
            record.head_sha,
            record.workspace_id,
            _json(record.evaluation_subject),
            int(record.resume_eligible),
            _json(record.payload),
            _timestamp(record.updated_at),
        )

        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT * FROM workflow_checkpoints WHERE checkpoint_key = ?",
                (record.checkpoint_key,),
            ).fetchone()
            if existing is not None and tuple(existing) == values:
                return False
            if existing is not None and (
                int(existing["issue_number"]) != record.issue_number
                or str(existing["correlation_id"]) != record.correlation_id
            ):
                raise StateStoreConflict("checkpoint", record.checkpoint_key)
            connection.execute(
                "INSERT INTO workflow_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(checkpoint_key) DO UPDATE SET workflow=excluded.workflow, "
                "boundary=excluded.boundary, repository=excluded.repository, branch=excluded.branch, "
                "base_ref=excluded.base_ref, head_sha=excluded.head_sha, "
                "workspace_id=excluded.workspace_id, "
                "evaluation_subject_json=excluded.evaluation_subject_json, "
                "resume_eligible=excluded.resume_eligible, payload_json=excluded.payload_json, "
                "updated_at=excluded.updated_at",
                values,
            )
            return True

        return self._transition(mutate)

    def get_checkpoint(self, checkpoint_key: str) -> WorkflowCheckpointRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_checkpoints WHERE checkpoint_key = ?", (checkpoint_key,)
            ).fetchone()
        if row is None:
            return None
        return WorkflowCheckpointRecord(
            checkpoint_key=str(row["checkpoint_key"]),
            issue_number=int(row["issue_number"]),
            correlation_id=str(row["correlation_id"]),
            workflow=str(row["workflow"]),
            boundary=str(row["boundary"]),
            repository=str(row["repository"]),
            branch=str(row["branch"]),
            base_ref=str(row["base_ref"]),
            head_sha=str(row["head_sha"]),
            workspace_id=str(row["workspace_id"]),
            evaluation_subject=json.loads(str(row["evaluation_subject_json"])),
            resume_eligible=bool(row["resume_eligible"]),
            payload=json.loads(str(row["payload_json"])),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_checkpoints(
        self, *, resume_eligible: bool | None = None
    ) -> list[WorkflowCheckpointRecord]:
        query = "SELECT checkpoint_key FROM workflow_checkpoints"
        params: tuple[object, ...] = ()
        if resume_eligible is not None:
            query += " WHERE resume_eligible = ?"
            params = (int(resume_eligible),)
        query += " ORDER BY updated_at, checkpoint_key"
        with self._database._connection() as connection:
            keys = [str(row[0]) for row in connection.execute(query, params).fetchall()]
        return [record for key in keys if (record := self.get_checkpoint(key)) is not None]

    def clear_checkpoint(self, checkpoint_key: str) -> AuthorityWriteResult:
        def mutate(connection: sqlite3.Connection) -> bool:
            cursor = connection.execute(
                "DELETE FROM workflow_checkpoints WHERE checkpoint_key = ?", (checkpoint_key,)
            )
            return cursor.rowcount > 0

        return self._transition(mutate)

    def put_intent(self, record: OperationIntentRecord) -> AuthorityWriteResult:
        if record.status != "pending":
            raise StateStoreError(
                "state_intent_transition_invalid",
                "A new operation intent must start in pending state",
            )
        values = (
            record.intent_key,
            record.operation,
            record.status,
            record.issue_number,
            record.correlation_id,
            record.subject_key,
            _json(record.payload),
            _json(record.postcondition),
            _timestamp(record.updated_at),
        )

        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT * FROM operation_intents WHERE intent_key = ?", (record.intent_key,)
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["operation"]) == record.operation
                    and int(existing["issue_number"]) == record.issue_number
                    and str(existing["correlation_id"]) == record.correlation_id
                    and str(existing["subject_key"]) == record.subject_key
                    and str(existing["payload_json"]) == _json(record.payload)
                ):
                    # A retry observes the same immutable effect identity.  Its
                    # persisted status/postcondition is intentionally retained.
                    return False
                raise StateStoreConflict("operation intent", record.intent_key)
            connection.execute(
                "INSERT INTO operation_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", values
            )
            return True

        return self._transition(mutate)

    def finish_intent(
        self,
        intent_key: str,
        *,
        status: str,
        postcondition: dict[str, Any],
    ) -> AuthorityWriteResult:
        if status not in {"applied", "failed", "mismatch", "unresolved"}:
            raise StateStoreError(
                "state_intent_transition_invalid",
                "Operation intent has an invalid terminal status",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT status, postcondition_json FROM operation_intents WHERE intent_key = ?",
                (intent_key,),
            ).fetchone()
            if row is None:
                raise StateStoreError("state_intent_missing", "Operation intent does not exist")
            encoded = _json(postcondition)
            if str(row["status"]) == status and str(row["postcondition_json"]) == encoded:
                return False
            if str(row["status"]) != "pending":
                raise StateStoreConflict("operation intent", intent_key)
            connection.execute(
                "UPDATE operation_intents SET status = ?, postcondition_json = ?, updated_at = ? "
                "WHERE intent_key = ? AND status = 'pending'",
                (
                    status,
                    encoded,
                    _timestamp(datetime.now(timezone.utc)),
                    intent_key,
                ),
            )
            return True

        return self._transition(mutate)

    def get_intent(self, intent_key: str) -> OperationIntentRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM operation_intents WHERE intent_key = ?", (intent_key,)
            ).fetchone()
        if row is None:
            return None
        return OperationIntentRecord(
            intent_key=str(row["intent_key"]),
            operation=str(row["operation"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            issue_number=int(row["issue_number"]),
            correlation_id=str(row["correlation_id"]),
            subject_key=str(row["subject_key"]),
            payload=json.loads(str(row["payload_json"])),
            postcondition=json.loads(str(row["postcondition_json"])),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_intents(
        self,
        *,
        correlation_id: str | None = None,
        status: str | None = None,
    ) -> list[OperationIntentRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT intent_key FROM operation_intents"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at, intent_key"
        with self._database._connection() as connection:
            keys = [str(row[0]) for row in connection.execute(query, tuple(params)).fetchall()]
        return [record for key in keys if (record := self.get_intent(key)) is not None]

    def put_budget_admission(self, record: WorkflowBudgetAdmissionRecord) -> AuthorityWriteResult:
        if (
            record.issue_number <= 0
            or isinstance(record.token_limit, bool)
            or record.token_limit <= 0
            or not record.admission_key.strip()
            or not record.repository.strip()
            or not record.invocation_digest.strip()
            or not record.source_digest.strip()
            or not record.policy_digest.strip()
            or record.plan_contract_hash
            or record.plan_comment_id != 0
        ):
            raise StateStoreError(
                "workflow_budget_admission_invalid",
                "Workflow budget admission has invalid bounds",
            )
        values = (
            record.admission_key,
            record.repository,
            record.issue_number,
            record.invocation_digest,
            record.source_digest,
            record.policy_digest,
            record.correlation_id,
            record.token_limit,
            record.plan_contract_hash,
            record.plan_comment_id,
            _timestamp(record.created_at),
            _timestamp(record.updated_at),
        )

        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT * FROM workflow_budget_admissions WHERE admission_key = ?",
                (record.admission_key,),
            ).fetchone()
            if existing is not None:
                immutable = (
                    str(existing["repository"]),
                    int(existing["issue_number"]),
                    str(existing["invocation_digest"]),
                    str(existing["source_digest"]),
                    str(existing["policy_digest"]),
                    str(existing["correlation_id"]),
                    int(existing["token_limit"]),
                )
                expected = (
                    record.repository,
                    record.issue_number,
                    record.invocation_digest,
                    record.source_digest,
                    record.policy_digest,
                    record.correlation_id,
                    record.token_limit,
                )
                if immutable == expected:
                    return False
                raise StateStoreConflict("workflow budget admission", record.admission_key)
            connection.execute(
                "INSERT INTO workflow_budget_admissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            return True

        return self._transition(mutate)

    def bind_budget_plan(
        self, admission_key: str, *, plan_contract_hash: str, plan_comment_id: int
    ) -> AuthorityWriteResult:
        if not plan_contract_hash.strip() or plan_comment_id <= 0:
            raise StateStoreError(
                "workflow_budget_plan_binding_invalid",
                "Workflow budget plan binding is empty",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT plan_contract_hash, plan_comment_id FROM workflow_budget_admissions "
                "WHERE admission_key = ?",
                (admission_key,),
            ).fetchone()
            if row is None:
                raise StateStoreError(
                    "workflow_budget_admission_missing",
                    "Workflow budget admission does not exist",
                )
            current = str(row["plan_contract_hash"])
            current_comment = int(row["plan_comment_id"])
            if current == plan_contract_hash and current_comment == plan_comment_id:
                return False
            if current or current_comment:
                raise StateStoreConflict("workflow budget plan", admission_key)
            try:
                connection.execute(
                    "UPDATE workflow_budget_admissions SET plan_contract_hash = ?, "
                    "plan_comment_id = ?, updated_at = ? WHERE admission_key = ? "
                    "AND plan_contract_hash = '' AND plan_comment_id = 0",
                    (
                        plan_contract_hash,
                        plan_comment_id,
                        _timestamp(datetime.now(timezone.utc)),
                        admission_key,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise StateStoreConflict("workflow budget plan", plan_contract_hash) from exc
            return True

        return self._transition(mutate)

    def get_budget_admission(self, admission_key: str) -> WorkflowBudgetAdmissionRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_budget_admissions WHERE admission_key = ?",
                (admission_key,),
            ).fetchone()
        return self._budget_admission_from_row(row) if row is not None else None

    def find_budget_admission(
        self,
        *,
        repository: str,
        issue_number: int,
        plan_contract_hash: str,
        plan_comment_id: int,
    ) -> WorkflowBudgetAdmissionRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_budget_admissions "
                "WHERE repository = ? AND issue_number = ? AND plan_contract_hash = ? "
                "AND plan_comment_id = ?",
                (repository, issue_number, plan_contract_hash, plan_comment_id),
            ).fetchone()
        return self._budget_admission_from_row(row) if row is not None else None

    @staticmethod
    def _budget_admission_from_row(row: sqlite3.Row) -> WorkflowBudgetAdmissionRecord:
        return WorkflowBudgetAdmissionRecord(
            admission_key=str(row["admission_key"]),
            repository=str(row["repository"]),
            issue_number=int(row["issue_number"]),
            invocation_digest=str(row["invocation_digest"]),
            source_digest=str(row["source_digest"]),
            policy_digest=str(row["policy_digest"]),
            correlation_id=str(row["correlation_id"]),
            token_limit=int(row["token_limit"]),
            plan_contract_hash=str(row["plan_contract_hash"]),
            plan_comment_id=int(row["plan_comment_id"]),
            created_at=_from_timestamp(str(row["created_at"])),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_budget_admissions(self) -> list[WorkflowBudgetAdmissionRecord]:
        with self._database._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_budget_admissions ORDER BY created_at, admission_key"
            ).fetchall()
        return [self._budget_admission_from_row(row) for row in rows]

    def reserve_budget_attempt(self, record: LLMBudgetAttemptRecord) -> AuthorityWriteResult:
        if (
            record.status != "reserved"
            or not record.attempt_key.strip()
            or not record.admission_key.strip()
            or not record.logical_call_id.strip()
            or isinstance(record.input_upper_bound, bool)
            or record.input_upper_bound <= 0
            or isinstance(record.output_upper_bound, bool)
            or record.output_upper_bound <= 0
            or record.reserved_tokens != record.input_upper_bound + record.output_upper_bound
        ):
            raise StateStoreError(
                "workflow_budget_attempt_invalid",
                "LLM budget attempt has invalid reservation bounds",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT * FROM llm_budget_attempts WHERE attempt_key = ?",
                (record.attempt_key,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["admission_key"]) == record.admission_key
                    and int(existing["reserved_tokens"]) == record.reserved_tokens
                    and str(existing["status"]) == record.status
                ):
                    return False
                raise StateStoreConflict("LLM budget attempt", record.attempt_key)
            admission = connection.execute(
                "SELECT token_limit FROM workflow_budget_admissions WHERE admission_key = ?",
                (record.admission_key,),
            ).fetchone()
            if admission is None:
                raise StateStoreError(
                    "workflow_budget_admission_missing",
                    "Workflow budget admission does not exist",
                )
            committed = connection.execute(
                "SELECT COALESCE(SUM(CASE WHEN status = 'settled' "
                "THEN actual_input_tokens + actual_output_tokens ELSE reserved_tokens END), 0) "
                "FROM llm_budget_attempts WHERE admission_key = ?",
                (record.admission_key,),
            ).fetchone()
            used = int(committed[0]) if committed is not None else 0
            if used + record.reserved_tokens > int(admission["token_limit"]):
                raise StateStoreError(
                    "workflow_token_budget_exhausted",
                    "Workflow token budget cannot cover the next provider attempt",
                )
            connection.execute(
                "INSERT INTO llm_budget_attempts VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', NULL, NULL, '', ?, ?)",
                (
                    record.attempt_key,
                    record.admission_key,
                    record.logical_call_id,
                    record.provider,
                    record.model,
                    record.task,
                    record.input_upper_bound,
                    record.output_upper_bound,
                    record.reserved_tokens,
                    _timestamp(record.created_at),
                    _timestamp(record.updated_at),
                ),
            )
            return True

        return self._transition(mutate)

    def settle_budget_attempt(
        self,
        attempt_key: str,
        *,
        status: str,
        actual_input_tokens: int | None,
        actual_output_tokens: int | None,
        outcome_code: str,
    ) -> AuthorityWriteResult:
        if status not in {"settled", "unknown"} or not outcome_code.strip():
            raise StateStoreError(
                "workflow_budget_attempt_transition_invalid",
                "LLM budget attempt can only settle or remain unknown",
            )
        if status == "settled" and (
            actual_input_tokens is None
            or actual_output_tokens is None
            or actual_input_tokens < 0
            or actual_output_tokens < 0
        ):
            raise StateStoreError(
                "workflow_budget_usage_invalid",
                "Known LLM usage must contain non-negative token counts",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT * FROM llm_budget_attempts WHERE attempt_key = ?",
                (attempt_key,),
            ).fetchone()
            if row is None:
                raise StateStoreError(
                    "workflow_budget_attempt_missing",
                    "LLM budget attempt does not exist",
                )
            current = str(row["status"])
            expected = (
                status,
                actual_input_tokens,
                actual_output_tokens,
                outcome_code,
            )
            observed = (
                current,
                row["actual_input_tokens"],
                row["actual_output_tokens"],
                str(row["outcome_code"]),
            )
            if observed == expected:
                return False
            if current != "reserved":
                raise StateStoreConflict("LLM budget attempt", attempt_key)
            if status == "settled" and (
                int(actual_input_tokens or 0) + int(actual_output_tokens or 0)
                > int(row["reserved_tokens"])
            ):
                raise StateStoreError(
                    "workflow_budget_bound_exceeded",
                    "Provider usage exceeded the reserved token upper bound",
                )
            connection.execute(
                "UPDATE llm_budget_attempts SET status = ?, actual_input_tokens = ?, "
                "actual_output_tokens = ?, outcome_code = ?, updated_at = ? "
                "WHERE attempt_key = ? AND status = 'reserved'",
                (
                    status,
                    actual_input_tokens,
                    actual_output_tokens,
                    outcome_code,
                    _timestamp(datetime.now(timezone.utc)),
                    attempt_key,
                ),
            )
            return True

        return self._transition(mutate)

    def get_budget_attempt(self, attempt_key: str) -> LLMBudgetAttemptRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM llm_budget_attempts WHERE attempt_key = ?", (attempt_key,)
            ).fetchone()
        return self._budget_attempt_from_row(row) if row is not None else None

    @staticmethod
    def _budget_attempt_from_row(row: sqlite3.Row) -> LLMBudgetAttemptRecord:
        return LLMBudgetAttemptRecord(
            attempt_key=str(row["attempt_key"]),
            admission_key=str(row["admission_key"]),
            logical_call_id=str(row["logical_call_id"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            task=str(row["task"]),
            input_upper_bound=int(row["input_upper_bound"]),
            output_upper_bound=int(row["output_upper_bound"]),
            reserved_tokens=int(row["reserved_tokens"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            actual_input_tokens=(
                int(row["actual_input_tokens"]) if row["actual_input_tokens"] is not None else None
            ),
            actual_output_tokens=(
                int(row["actual_output_tokens"])
                if row["actual_output_tokens"] is not None
                else None
            ),
            outcome_code=str(row["outcome_code"]),
            created_at=_from_timestamp(str(row["created_at"])),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_budget_attempts(
        self, *, admission_key: str | None = None
    ) -> list[LLMBudgetAttemptRecord]:
        query = "SELECT * FROM llm_budget_attempts"
        params: tuple[object, ...] = ()
        if admission_key is not None:
            query += " WHERE admission_key = ?"
            params = (admission_key,)
        query += " ORDER BY created_at, attempt_key"
        with self._database._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._budget_attempt_from_row(row) for row in rows]

    def put_planning_clarification(
        self,
        record: PlanningClarificationRecord,
        *,
        expected_version: int | None = None,
    ) -> AuthorityWriteResult:
        if (
            not record.series_key
            or not record.repository
            or record.issue_number <= 0
            or not record.source_digest.startswith("sha256:")
            or not record.admission_key
            or record.round_number not in {1, 2}
            or record.version <= 0
            or record.status
            not in {"waiting", "answered", "planned", "superseded", "timed_out", "exhausted"}
            or len(record.rounds) != record.round_number
        ):
            raise StateStoreError(
                "planning_clarification_invalid",
                "Planning clarification state is incomplete or outside its bounded contract",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            existing = connection.execute(
                "SELECT version FROM planning_clarifications WHERE series_key = ?",
                (record.series_key,),
            ).fetchone()
            values = (
                record.repository,
                record.issue_number,
                record.source_digest,
                record.admission_key,
                record.correlation_id,
                record.status,
                record.round_number,
                _timestamp(record.deadline_at),
                _json(list(record.rounds)),
                record.version,
                _timestamp(record.created_at),
                _timestamp(record.updated_at),
                record.series_key,
            )
            if existing is None:
                if expected_version is not None or record.version != 1:
                    raise StateStoreConflict("planning clarification", record.series_key)
                connection.execute(
                    "INSERT INTO planning_clarifications "
                    "(repository, issue_number, source_digest, admission_key, correlation_id, "
                    "status, round_number, deadline_at, rounds_json, version, created_at, "
                    "updated_at, series_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
                return True
            if expected_version is None or int(existing["version"]) != expected_version:
                raise StateStoreConflict("planning clarification", record.series_key)
            if record.version != expected_version + 1:
                raise StateStoreConflict("planning clarification", record.series_key)
            cursor = connection.execute(
                "UPDATE planning_clarifications SET repository = ?, issue_number = ?, "
                "source_digest = ?, admission_key = ?, correlation_id = ?, status = ?, "
                "round_number = ?, deadline_at = ?, rounds_json = ?, version = ?, "
                "created_at = ?, updated_at = ? WHERE series_key = ? AND version = ?",
                (*values, expected_version),
            )
            if cursor.rowcount != 1:
                raise StateStoreConflict("planning clarification", record.series_key)
            return True

        return self._transition(mutate)

    @staticmethod
    def _planning_clarification_from_row(
        row: sqlite3.Row,
    ) -> PlanningClarificationRecord:
        rounds = json.loads(str(row["rounds_json"]))
        if not isinstance(rounds, list) or not all(isinstance(item, dict) for item in rounds):
            raise StateStoreError(
                "planning_clarification_invalid",
                "Planning clarification round evidence is invalid",
            )
        return PlanningClarificationRecord(
            series_key=str(row["series_key"]),
            repository=str(row["repository"]),
            issue_number=int(row["issue_number"]),
            source_digest=str(row["source_digest"]),
            admission_key=str(row["admission_key"]),
            correlation_id=str(row["correlation_id"]),
            status=cast(Any, str(row["status"])),
            round_number=int(row["round_number"]),
            deadline_at=_from_timestamp(str(row["deadline_at"])),
            rounds=tuple(rounds),
            version=int(row["version"]),
            created_at=_from_timestamp(str(row["created_at"])),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def get_planning_clarification(self, series_key: str) -> PlanningClarificationRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM planning_clarifications WHERE series_key = ?", (series_key,)
            ).fetchone()
        return self._planning_clarification_from_row(row) if row is not None else None

    def find_active_planning_clarification(
        self, *, repository: str, issue_number: int
    ) -> PlanningClarificationRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM planning_clarifications WHERE repository = ? "
                "AND issue_number = ? AND status IN ('waiting', 'answered') "
                "ORDER BY updated_at DESC, series_key DESC LIMIT 1",
                (repository, issue_number),
            ).fetchone()
        return self._planning_clarification_from_row(row) if row is not None else None

    def find_latest_planning_clarification(
        self, *, repository: str, issue_number: int
    ) -> PlanningClarificationRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM planning_clarifications WHERE repository = ? "
                "AND issue_number = ? ORDER BY updated_at DESC, series_key DESC LIMIT 1",
                (repository, issue_number),
            ).fetchone()
        return self._planning_clarification_from_row(row) if row is not None else None

    def list_planning_clarifications(self) -> list[PlanningClarificationRecord]:
        with self._database._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM planning_clarifications ORDER BY created_at, series_key"
            ).fetchall()
        return [self._planning_clarification_from_row(row) for row in rows]

    def acquire_lease(
        self,
        record: AuthorityLeaseRecord,
        *,
        expected_version: int | None = None,
    ) -> AuthorityWriteResult:
        def mutate(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT version FROM authority_leases WHERE resource_key = ?",
                (record.resource_key,),
            ).fetchone()
            if row is None:
                if expected_version is not None or record.version != 1:
                    raise StateStoreConflict("authority lease", record.resource_key)
                connection.execute(
                    "INSERT INTO authority_leases VALUES (?, ?, ?, ?, ?)",
                    (
                        record.resource_key,
                        record.owner_id,
                        _timestamp(record.expires_at),
                        record.version,
                        _timestamp(record.updated_at),
                    ),
                )
                return True
            if expected_version is None or int(row["version"]) != expected_version:
                raise StateStoreConflict("authority lease", record.resource_key)
            if record.version != expected_version + 1:
                raise StateStoreConflict("authority lease", record.resource_key)
            cursor = connection.execute(
                "UPDATE authority_leases SET owner_id = ?, expires_at = ?, version = ?, "
                "updated_at = ? WHERE resource_key = ? AND version = ?",
                (
                    record.owner_id,
                    _timestamp(record.expires_at),
                    record.version,
                    _timestamp(record.updated_at),
                    record.resource_key,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise StateStoreConflict("authority lease", record.resource_key)
            return True

        return self._transition(mutate)

    def get_lease(self, resource_key: str) -> AuthorityLeaseRecord | None:
        with self._database._connection() as connection:
            row = connection.execute(
                "SELECT * FROM authority_leases WHERE resource_key = ?", (resource_key,)
            ).fetchone()
        if row is None:
            return None
        return AuthorityLeaseRecord(
            resource_key=str(row["resource_key"]),
            owner_id=str(row["owner_id"]),
            expires_at=_from_timestamp(str(row["expires_at"])),
            version=int(row["version"]),
            updated_at=_from_timestamp(str(row["updated_at"])),
        )

    def list_leases(self) -> list[AuthorityLeaseRecord]:
        with self._database._connection() as connection:
            keys = [
                str(row[0])
                for row in connection.execute(
                    "SELECT resource_key FROM authority_leases ORDER BY updated_at, resource_key"
                ).fetchall()
            ]
        return [lease for key in keys if (lease := self.get_lease(key)) is not None]

    def release_lease(
        self,
        resource_key: str,
        *,
        owner_id: str,
        expected_version: int,
    ) -> AuthorityWriteResult:
        def mutate(connection: sqlite3.Connection) -> bool:
            cursor = connection.execute(
                "DELETE FROM authority_leases WHERE resource_key = ? AND owner_id = ? "
                "AND version = ?",
                (resource_key, owner_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise StateStoreConflict("authority lease", resource_key)
            return True

        return self._transition(mutate)

    def authority_status(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._database.status().as_dict()["authority"])

    def replace_reconcile_scan(
        self,
        operation_id: str,
        entries: list[ReconcileEntryRecord],
        *,
        scan_error_code: str | None = None,
    ) -> AuthorityWriteResult:
        if any(entry.operation_id != operation_id for entry in entries):
            raise StateStoreError(
                "state_reconcile_entry_invalid",
                "Reconcile entries must belong to the active restore operation",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            metadata = connection.execute(
                "SELECT active_restore_operation, reconcile_required FROM authority_metadata "
                "WHERE singleton = 1"
            ).fetchone()
            operation = connection.execute(
                "SELECT status FROM restore_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if (
                metadata is None
                or not bool(metadata["reconcile_required"])
                or str(metadata["active_restore_operation"] or "") != operation_id
                or operation is None
                or str(operation["status"]) != "reconcile_required"
            ):
                raise StateStoreError(
                    "state_reconcile_operation_inactive",
                    "Reconcile scan does not target the active restore operation",
                )
            now = _timestamp(datetime.now(timezone.utc))
            if scan_error_code:
                connection.execute(
                    "UPDATE restore_operations SET scan_status = 'scan_failed', "
                    "scan_error_code = ? WHERE operation_id = ?",
                    (scan_error_code, operation_id),
                )
                return True
            identities: set[tuple[str, str]] = set()
            for entry in entries:
                identity = (entry.object_type, entry.object_key)
                if identity in identities:
                    raise StateStoreError(
                        "state_reconcile_entry_duplicate",
                        "Reconcile scan produced duplicate object identities",
                    )
                identities.add(identity)
            connection.execute(
                "DELETE FROM reconcile_entries WHERE operation_id = ?", (operation_id,)
            )
            for entry in entries:
                connection.execute(
                    "INSERT INTO reconcile_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        operation_id,
                        entry.object_type,
                        entry.object_key,
                        entry.classification,
                        entry.reason,
                        _json(entry.evidence),
                        _timestamp(entry.updated_at),
                    ),
                )
            connection.execute(
                "UPDATE restore_operations SET scan_status = 'completed', "
                "scan_error_code = NULL WHERE operation_id = ?",
                (operation_id,),
            )
            connection.execute(
                "UPDATE authority_metadata SET updated_at = ? WHERE singleton = 1",
                (now,),
            )
            return True

        return self._transition(mutate)

    def list_reconcile_entries(self, operation_id: str) -> list[ReconcileEntryRecord]:
        with self._database._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM reconcile_entries WHERE operation_id = ? "
                "ORDER BY object_type, object_key",
                (operation_id,),
            ).fetchall()
        return [
            ReconcileEntryRecord(
                operation_id=str(row["operation_id"]),
                object_type=str(row["object_type"]),
                object_key=str(row["object_key"]),
                classification=str(row["classification"]),  # type: ignore[arg-type]
                reason=str(row["reason"]),
                evidence=json.loads(str(row["evidence_json"])),
                updated_at=_from_timestamp(str(row["updated_at"])),
            )
            for row in rows
        ]

    def classify_reconcile_entry(
        self,
        operation_id: str,
        object_type: str,
        object_key: str,
        *,
        classification: str,
        reason: str,
    ) -> AuthorityWriteResult:
        if classification not in {"verified_effect", "verified_absent", "abandoned"}:
            raise StateStoreError(
                "state_reconcile_classification_invalid",
                "Operator classification must be verified_effect, verified_absent or abandoned",
            )
        if not reason.strip():
            raise StateStoreError(
                "state_reconcile_reason_required",
                "Operator reconcile classification requires a reason",
            )

        def mutate(connection: sqlite3.Connection) -> bool:
            operation = connection.execute(
                "SELECT status, scan_status FROM restore_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if operation is None or str(operation["status"]) != "reconcile_required":
                raise StateStoreError(
                    "state_reconcile_operation_inactive",
                    "Reconcile classification requires an active restore operation",
                )
            if str(operation["scan_status"]) != "completed":
                raise StateStoreError(
                    "state_reconcile_scan_incomplete",
                    "Reconcile classification requires a successful scan",
                )
            current = connection.execute(
                "SELECT classification, reason FROM reconcile_entries "
                "WHERE operation_id = ? AND object_type = ? AND object_key = ?",
                (operation_id, object_type, object_key),
            ).fetchone()
            if current is None:
                raise StateStoreError(
                    "state_reconcile_entry_missing",
                    "Reconcile entry does not exist",
                )
            if (
                str(current["classification"]) == classification
                and str(current["reason"]) == reason
            ):
                return False
            connection.execute(
                "UPDATE reconcile_entries SET classification = ?, reason = ?, updated_at = ? "
                "WHERE operation_id = ? AND object_type = ? AND object_key = ?",
                (
                    classification,
                    reason.strip(),
                    _timestamp(datetime.now(timezone.utc)),
                    operation_id,
                    object_type,
                    object_key,
                ),
            )
            return True

        return self._transition(mutate)

    def complete_reconcile(
        self,
        operation_id: str,
        *,
        audit_epoch: int = 0,
    ) -> AuthorityWriteResult:
        if audit_epoch < 0:
            raise StateStoreError(
                "state_reconcile_audit_epoch_invalid",
                "Reconcile audit epoch must be non-negative",
            )
        with self._database._lifecycle_lock():
            self._database._assert_restore_complete()
            try:
                witness = self._database._read_authority_witness()
                witness_epoch = int(witness["authority_epoch"])
            except StateStoreError:
                witness_epoch = 0
            with self._database._connection(lifecycle=False) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    metadata = connection.execute(
                        "SELECT * FROM authority_metadata WHERE singleton = 1"
                    ).fetchone()
                    operation = connection.execute(
                        "SELECT * FROM restore_operations WHERE operation_id = ?",
                        (operation_id,),
                    ).fetchone()
                    if (
                        metadata is None
                        or not bool(metadata["reconcile_required"])
                        or str(metadata["active_restore_operation"] or "") != operation_id
                        or operation is None
                        or str(operation["status"]) != "reconcile_required"
                    ):
                        raise StateStoreError(
                            "state_reconcile_operation_inactive",
                            "Reconcile completion requires the active restore operation",
                        )
                    if str(operation["scan_status"]) != "completed":
                        raise StateStoreError(
                            "state_reconcile_scan_incomplete",
                            "Reconcile completion requires a successful scan",
                        )
                    inventory = connection.execute(
                        "SELECT classification FROM reconcile_entries "
                        "WHERE operation_id = ? AND object_type = 'inventory' "
                        "AND object_key = 'complete'",
                        (operation_id,),
                    ).fetchone()
                    if inventory is None or str(inventory["classification"]) != "verified_effect":
                        raise StateStoreError(
                            "state_reconcile_inventory_incomplete",
                            "Reconcile completion requires one complete persisted inventory",
                        )
                    unresolved = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM reconcile_entries "
                            "WHERE operation_id = ? AND classification = 'unresolved'",
                            (operation_id,),
                        ).fetchone()[0]
                    )
                    if unresolved:
                        raise StateStoreError(
                            "state_reconcile_unresolved",
                            "Reconcile completion is blocked by unresolved objects",
                        )
                    new_epoch = (
                        max(
                            int(metadata["authority_epoch"]),
                            int(metadata["pre_restore_epoch_highwater"]),
                            int(operation["pre_restore_epoch_highwater"]),
                            witness_epoch,
                            audit_epoch,
                        )
                        + 1
                    )
                    now = _timestamp(datetime.now(timezone.utc))
                    connection.execute(
                        "UPDATE restore_operations SET status = 'completed', "
                        "completed_at = ? WHERE operation_id = ?",
                        (now, operation_id),
                    )
                    connection.execute(
                        "UPDATE authority_metadata SET authority_epoch = ?, "
                        "reconcile_required = 0, reconcile_reason = NULL, "
                        "active_restore_operation = NULL, pre_restore_epoch_highwater = 0, "
                        "updated_at = ? WHERE singleton = 1",
                        (new_epoch, now),
                    )
                    connection.execute("COMMIT")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
            self._database._sync_authority_witness(lifecycle=False)
        return AuthorityWriteResult(changed=True, authority_epoch=new_epoch)
