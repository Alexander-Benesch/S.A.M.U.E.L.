"""SQLite identity projection sharing the versioned runtime-state database."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from samuel.core.identity import (
    ALL_PERMISSIONS,
    AutomationTokenRecord,
    IdentityError,
    IdentityStatus,
    PrincipalKind,
    PrincipalRecord,
    Role,
    SessionRecord,
)
from samuel.core.ports import IIdentityStateStore

if TYPE_CHECKING:
    from samuel.adapters.state.sqlite import SQLiteStateStore

_ROLES = frozenset({"viewer", "auditor", "operator", "administrator"})


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IdentityError("identity_timestamp_invalid", "Identity timestamps must be UTC-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SQLiteIdentityStateStore(IIdentityStateStore):
    """Typed identity operations with the runtime-state lifecycle lock and witness."""

    def __init__(self, store: SQLiteStateStore) -> None:
        self._store = store

    @staticmethod
    def _roles(connection: sqlite3.Connection, principal_id: str) -> tuple[Role, ...]:
        rows = connection.execute(
            "SELECT role FROM identity_principal_roles WHERE principal_id = ? ORDER BY role",
            (principal_id,),
        ).fetchall()
        return tuple(cast(Role, str(row["role"])) for row in rows)

    @classmethod
    def _principal(cls, connection: sqlite3.Connection, row: sqlite3.Row) -> PrincipalRecord:
        return PrincipalRecord(
            principal_id=str(row["principal_id"]),
            username=str(row["username"]),
            kind=cast(PrincipalKind, str(row["kind"])),
            password_hash=str(row["password_hash"]) if row["password_hash"] is not None else None,
            disabled=bool(row["disabled"]),
            credential_version=int(row["credential_version"]),
            roles=cls._roles(connection, str(row["principal_id"])),
            created_at=_datetime(str(row["created_at"])),
            updated_at=_datetime(str(row["updated_at"])),
        )

    @staticmethod
    def _session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            session_id=str(row["session_id"]),
            session_hash=str(row["session_hash"]),
            principal_id=str(row["principal_id"]),
            instance_uuid=str(row["instance_uuid"]),
            csrf_hash=str(row["csrf_hash"]),
            credential_version=int(row["credential_version"]),
            created_at=_datetime(str(row["created_at"])),
            authenticated_at=_datetime(str(row["authenticated_at"])),
            last_seen_at=_datetime(str(row["last_seen_at"])),
            expires_at=_datetime(str(row["expires_at"])),
            revoked_at=_datetime(str(row["revoked_at"])) if row["revoked_at"] else None,
            revoked_by=str(row["revoked_by"]) if row["revoked_by"] else None,
        )

    @staticmethod
    def _token(row: sqlite3.Row) -> AutomationTokenRecord:
        raw_permissions = json.loads(str(row["permissions_json"]))
        if not isinstance(raw_permissions, list) or any(
            not isinstance(value, str) or value not in ALL_PERMISSIONS for value in raw_permissions
        ):
            raise IdentityError(
                "identity_token_permissions_invalid",
                "Automation token permissions are invalid",
            )
        return AutomationTokenRecord(
            token_id=str(row["token_id"]),
            token_hash=str(row["token_hash"]),
            principal_id=str(row["principal_id"]),
            permissions=tuple(sorted(raw_permissions)),
            created_at=_datetime(str(row["created_at"])),
            expires_at=_datetime(str(row["expires_at"])),
            revoked_at=_datetime(str(row["revoked_at"])) if row["revoked_at"] else None,
            revoked_by=str(row["revoked_by"]) if row["revoked_by"] else None,
        )

    @staticmethod
    def _advance_authority(connection: sqlite3.Connection, now: datetime) -> None:
        connection.execute(
            "UPDATE authority_metadata SET authority_epoch = authority_epoch + 1, "
            "updated_at = ? WHERE singleton = 1",
            (_timestamp(now),),
        )

    def _sync_witness(self) -> None:
        self._store._sync_authority_witness()  # noqa: SLF001 - same adapter boundary

    def status(self) -> IdentityStatus:
        with self._store._connection() as connection:  # noqa: SLF001
            row = connection.execute(
                "SELECT status FROM identity_metadata WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise IdentityError("identity_metadata_missing", "Identity metadata is missing")
        return cast(IdentityStatus, str(row["status"]))

    def bootstrap_administrator(self, username: str, password_hash: str) -> PrincipalRecord:
        now = datetime.now(timezone.utc)
        principal_id = str(uuid4())
        try:
            with self._store._connection() as connection, connection:  # noqa: SLF001
                metadata = connection.execute(
                    "SELECT status FROM identity_metadata WHERE singleton = 1"
                ).fetchone()
                if metadata is None or str(metadata["status"]) != "uninitialized":
                    raise IdentityError(
                        "identity_already_initialized",
                        "Identity bootstrap is only available before initialization",
                    )
                connection.execute(
                    "INSERT INTO identity_principals VALUES (?, ?, 'user', ?, 0, 1, ?, ?)",
                    (principal_id, username, password_hash, _timestamp(now), _timestamp(now)),
                )
                connection.execute(
                    "INSERT INTO identity_principal_roles VALUES (?, 'administrator')",
                    (principal_id,),
                )
                connection.execute(
                    "UPDATE identity_metadata SET status = 'active', recovery_reason = NULL, "
                    "activated_at = ?, updated_at = ? WHERE singleton = 1",
                    (_timestamp(now), _timestamp(now)),
                )
                self._advance_authority(connection, now)
                row = connection.execute(
                    "SELECT * FROM identity_principals WHERE principal_id = ?", (principal_id,)
                ).fetchone()
                if row is None:
                    raise IdentityError("identity_write_failed", "Administrator was not persisted")
                result = self._principal(connection, row)
        except sqlite3.IntegrityError as exc:
            raise IdentityError("identity_username_conflict", "Username already exists") from exc
        self._sync_witness()
        return result

    def recover_administrator(
        self, username: str, password_hash: str, *, reason: str
    ) -> PrincipalRecord:
        if not reason.strip():
            raise IdentityError("identity_recovery_reason_required", "Recovery reason is required")
        now = datetime.now(timezone.utc)
        with self._store._connection() as connection, connection:  # noqa: SLF001
            metadata = connection.execute(
                "SELECT status FROM identity_metadata WHERE singleton = 1"
            ).fetchone()
            if metadata is None or str(metadata["status"]) != "recovery_pending":
                raise IdentityError(
                    "identity_recovery_not_pending",
                    "Identity recovery is not pending for this installation",
                )
            row = connection.execute(
                "SELECT * FROM identity_principals WHERE username = ? COLLATE NOCASE AND kind = 'user'",
                (username,),
            ).fetchone()
            if row is None:
                raise IdentityError(
                    "identity_recovery_principal_missing",
                    "Recovery principal does not exist in the restored installation",
                )
            principal_id = str(row["principal_id"])
            connection.execute(
                "UPDATE identity_principals SET password_hash = ?, disabled = 0, "
                "credential_version = credential_version + 1, updated_at = ? "
                "WHERE principal_id = ?",
                (password_hash, _timestamp(now), principal_id),
            )
            connection.execute(
                "DELETE FROM identity_principal_roles WHERE principal_id = ?", (principal_id,)
            )
            connection.execute(
                "INSERT INTO identity_principal_roles VALUES (?, 'administrator')", (principal_id,)
            )
            connection.execute(
                "UPDATE identity_sessions SET revoked_at = ?, revoked_by = 'system:recovery' "
                "WHERE revoked_at IS NULL",
                (_timestamp(now),),
            )
            connection.execute(
                "UPDATE identity_tokens SET revoked_at = ?, revoked_by = 'system:recovery' "
                "WHERE revoked_at IS NULL",
                (_timestamp(now),),
            )
            connection.execute(
                "UPDATE identity_metadata SET status = 'active', recovery_reason = NULL, "
                "activated_at = ?, updated_at = ? WHERE singleton = 1",
                (_timestamp(now), _timestamp(now)),
            )
            self._advance_authority(connection, now)
            updated = connection.execute(
                "SELECT * FROM identity_principals WHERE principal_id = ?", (principal_id,)
            ).fetchone()
            if updated is None:
                raise IdentityError(
                    "identity_write_failed", "Recovered principal was not persisted"
                )
            result = self._principal(connection, updated)
        self._sync_witness()
        return result

    def get_principal_by_username(self, username: str) -> PrincipalRecord | None:
        with self._store._connection() as connection:  # noqa: SLF001
            row = connection.execute(
                "SELECT * FROM identity_principals WHERE username = ? COLLATE NOCASE", (username,)
            ).fetchone()
            return self._principal(connection, row) if row is not None else None

    def get_principal(self, principal_id: str) -> PrincipalRecord | None:
        with self._store._connection() as connection:  # noqa: SLF001
            row = connection.execute(
                "SELECT * FROM identity_principals WHERE principal_id = ?", (principal_id,)
            ).fetchone()
            return self._principal(connection, row) if row is not None else None

    def list_principals(self) -> list[PrincipalRecord]:
        with self._store._connection() as connection:  # noqa: SLF001
            rows = connection.execute(
                "SELECT * FROM identity_principals ORDER BY username COLLATE NOCASE, principal_id"
            ).fetchall()
            return [self._principal(connection, row) for row in rows]

    def create_user(
        self, username: str, password_hash: str, roles: tuple[Role, ...]
    ) -> PrincipalRecord:
        now = datetime.now(timezone.utc)
        principal_id = str(uuid4())
        try:
            with self._store._connection() as connection, connection:  # noqa: SLF001
                connection.execute(
                    "INSERT INTO identity_principals VALUES (?, ?, 'user', ?, 0, 1, ?, ?)",
                    (principal_id, username, password_hash, _timestamp(now), _timestamp(now)),
                )
                connection.executemany(
                    "INSERT INTO identity_principal_roles VALUES (?, ?)",
                    [(principal_id, role) for role in roles],
                )
                self._advance_authority(connection, now)
                row = connection.execute(
                    "SELECT * FROM identity_principals WHERE principal_id = ?", (principal_id,)
                ).fetchone()
                if row is None:
                    raise IdentityError("identity_write_failed", "User was not persisted")
                result = self._principal(connection, row)
        except sqlite3.IntegrityError as exc:
            raise IdentityError("identity_username_conflict", "Username already exists") from exc
        self._sync_witness()
        return result

    def update_user(
        self,
        principal_id: str,
        *,
        roles: tuple[Role, ...] | None = None,
        disabled: bool | None = None,
        password_hash: str | None = None,
    ) -> PrincipalRecord:
        now = datetime.now(timezone.utc)
        with self._store._connection() as connection, connection:  # noqa: SLF001
            row = connection.execute(
                "SELECT * FROM identity_principals WHERE principal_id = ? AND kind = 'user'",
                (principal_id,),
            ).fetchone()
            if row is None:
                raise IdentityError("identity_principal_missing", "User does not exist")
            assignments = ["updated_at = ?", "credential_version = credential_version + 1"]
            values: list[Any] = [_timestamp(now)]
            if disabled is not None:
                assignments.append("disabled = ?")
                values.append(int(disabled))
            if password_hash is not None:
                assignments.append("password_hash = ?")
                values.append(password_hash)
            values.append(principal_id)
            connection.execute(
                f"UPDATE identity_principals SET {', '.join(assignments)} WHERE principal_id = ?",
                values,
            )
            if roles is not None:
                connection.execute(
                    "DELETE FROM identity_principal_roles WHERE principal_id = ?", (principal_id,)
                )
                connection.executemany(
                    "INSERT INTO identity_principal_roles VALUES (?, ?)",
                    [(principal_id, role) for role in roles],
                )
            connection.execute(
                "UPDATE identity_sessions SET revoked_at = ?, revoked_by = 'system:principal-change' "
                "WHERE principal_id = ? AND revoked_at IS NULL",
                (_timestamp(now), principal_id),
            )
            self._advance_authority(connection, now)
            updated = connection.execute(
                "SELECT * FROM identity_principals WHERE principal_id = ?", (principal_id,)
            ).fetchone()
            if updated is None:
                raise IdentityError("identity_write_failed", "User update was not persisted")
            result = self._principal(connection, updated)
        self._sync_witness()
        return result

    def create_session(self, record: SessionRecord) -> None:
        with self._store._connection() as connection, connection:  # noqa: SLF001
            connection.execute(
                "INSERT INTO identity_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                (
                    record.session_id,
                    record.session_hash,
                    record.principal_id,
                    record.instance_uuid,
                    record.csrf_hash,
                    record.credential_version,
                    _timestamp(record.created_at),
                    _timestamp(record.authenticated_at),
                    _timestamp(record.last_seen_at),
                    _timestamp(record.expires_at),
                ),
            )
            self._advance_authority(connection, record.created_at)
        self._sync_witness()

    def get_session(self, session_hash: str) -> SessionRecord | None:
        with self._store._connection() as connection:  # noqa: SLF001
            row = connection.execute(
                "SELECT * FROM identity_sessions WHERE session_hash = ?", (session_hash,)
            ).fetchone()
        return self._session(row) if row is not None else None

    def touch_session(self, session_hash: str, seen_at: datetime) -> None:
        with self._store._connection() as connection, connection:  # noqa: SLF001
            connection.execute(
                "UPDATE identity_sessions SET last_seen_at = ? WHERE session_hash = ? "
                "AND revoked_at IS NULL",
                (_timestamp(seen_at), session_hash),
            )

    def list_sessions(self, principal_id: str | None = None) -> list[SessionRecord]:
        with self._store._connection() as connection:  # noqa: SLF001
            if principal_id is None:
                rows = connection.execute(
                    "SELECT * FROM identity_sessions ORDER BY created_at, session_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM identity_sessions WHERE principal_id = ? "
                    "ORDER BY created_at, session_id",
                    (principal_id,),
                ).fetchall()
        return [self._session(row) for row in rows]

    def revoke_session(self, session_hash: str, *, actor: str, revoked_at: datetime) -> bool:
        with self._store._connection() as connection, connection:  # noqa: SLF001
            result = connection.execute(
                "UPDATE identity_sessions SET revoked_at = ?, revoked_by = ? "
                "WHERE session_hash = ? AND revoked_at IS NULL",
                (_timestamp(revoked_at), actor, session_hash),
            )
            if result.rowcount:
                self._advance_authority(connection, revoked_at)
        if result.rowcount:
            self._sync_witness()
        return bool(result.rowcount)

    def revoke_session_id(self, session_id: str, *, actor: str, revoked_at: datetime) -> bool:
        with self._store._connection() as connection, connection:  # noqa: SLF001
            result = connection.execute(
                "UPDATE identity_sessions SET revoked_at = ?, revoked_by = ? "
                "WHERE session_id = ? AND revoked_at IS NULL",
                (_timestamp(revoked_at), actor, session_id),
            )
            if result.rowcount:
                self._advance_authority(connection, revoked_at)
        if result.rowcount:
            self._sync_witness()
        return bool(result.rowcount)

    def revoke_sessions(self, *, principal_id: str | None, actor: str, revoked_at: datetime) -> int:
        query = (
            "UPDATE identity_sessions SET revoked_at = ?, revoked_by = ? WHERE revoked_at IS NULL"
        )
        values: list[Any] = [_timestamp(revoked_at), actor]
        if principal_id is not None:
            query += " AND principal_id = ?"
            values.append(principal_id)
        with self._store._connection() as connection, connection:  # noqa: SLF001
            result = connection.execute(query, values)
            if result.rowcount:
                self._advance_authority(connection, revoked_at)
        if result.rowcount:
            self._sync_witness()
        return int(result.rowcount)

    def create_automation_token(
        self, principal: PrincipalRecord, token: AutomationTokenRecord
    ) -> None:
        if principal.kind != "automation" or principal.password_hash is not None:
            raise IdentityError(
                "identity_automation_principal_invalid",
                "Automation token requires an automation principal",
            )
        now = datetime.now(timezone.utc)
        try:
            with self._store._connection() as connection, connection:  # noqa: SLF001
                connection.execute(
                    "INSERT INTO identity_principals VALUES (?, ?, 'automation', NULL, 0, 1, ?, ?)",
                    (
                        principal.principal_id,
                        principal.username,
                        _timestamp(principal.created_at),
                        _timestamp(principal.updated_at),
                    ),
                )
                connection.execute(
                    "INSERT INTO identity_tokens VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
                    (
                        token.token_id,
                        token.token_hash,
                        token.principal_id,
                        json.dumps(sorted(token.permissions), separators=(",", ":")),
                        _timestamp(token.created_at),
                        _timestamp(token.expires_at),
                    ),
                )
                self._advance_authority(connection, now)
        except sqlite3.IntegrityError as exc:
            raise IdentityError(
                "identity_automation_conflict", "Automation principal or token already exists"
            ) from exc
        self._sync_witness()

    def get_automation_token(self, token_hash: str) -> AutomationTokenRecord | None:
        with self._store._connection() as connection:  # noqa: SLF001
            row = connection.execute(
                "SELECT * FROM identity_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return self._token(row) if row is not None else None

    def list_automation_tokens(self) -> list[AutomationTokenRecord]:
        with self._store._connection() as connection:  # noqa: SLF001
            rows = connection.execute(
                "SELECT * FROM identity_tokens ORDER BY created_at, token_id"
            ).fetchall()
        return [self._token(row) for row in rows]

    def revoke_automation_token(self, token_id: str, *, actor: str, revoked_at: datetime) -> bool:
        with self._store._connection() as connection, connection:  # noqa: SLF001
            result = connection.execute(
                "UPDATE identity_tokens SET revoked_at = ?, revoked_by = ? "
                "WHERE token_id = ? AND revoked_at IS NULL",
                (_timestamp(revoked_at), actor, token_id),
            )
            if result.rowcount:
                self._advance_authority(connection, revoked_at)
        if result.rowcount:
            self._sync_witness()
        return bool(result.rowcount)
