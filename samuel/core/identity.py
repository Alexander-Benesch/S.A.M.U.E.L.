"""Provider-neutral dashboard identity, role, permission, and session contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

IdentityStatus = Literal["uninitialized", "active", "recovery_pending"]
PrincipalKind = Literal["user", "automation"]
Role = Literal["viewer", "auditor", "operator", "administrator"]

VIEW_STATUS = "status:view"
READ_AUDIT = "audit:read"
READ_DIAGNOSTICS = "diagnostics:read"
RUN_OPERATIONS = "operations:execute"
RUN_PROVIDER_PROBES = "provider:probe"
READ_CONFIGURATION = "configuration:read"
WRITE_CONFIGURATION = "configuration:write"
MANAGE_IDENTITIES = "identity:manage"
MANAGE_SESSIONS = "session:manage"

ALL_PERMISSIONS = frozenset(
    {
        VIEW_STATUS,
        READ_AUDIT,
        READ_DIAGNOSTICS,
        RUN_OPERATIONS,
        RUN_PROVIDER_PROBES,
        READ_CONFIGURATION,
        WRITE_CONFIGURATION,
        MANAGE_IDENTITIES,
        MANAGE_SESSIONS,
    }
)

# These are independent bundles.  Sharing an individual permission does not
# create role inheritance and adding a role never adds another role.
ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    "viewer": frozenset({VIEW_STATUS}),
    "auditor": frozenset({READ_AUDIT, READ_DIAGNOSTICS}),
    "operator": frozenset({VIEW_STATUS, READ_DIAGNOSTICS, RUN_OPERATIONS, RUN_PROVIDER_PROBES}),
    "administrator": frozenset(
        {READ_CONFIGURATION, WRITE_CONFIGURATION, MANAGE_IDENTITIES, MANAGE_SESSIONS}
    ),
}


def permissions_for_roles(roles: tuple[Role, ...]) -> frozenset[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS[role])
    return frozenset(permissions)


@dataclass(frozen=True)
class PrincipalRecord:
    principal_id: str
    username: str
    kind: PrincipalKind
    password_hash: str | None
    disabled: bool
    credential_version: int
    roles: tuple[Role, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    session_hash: str
    principal_id: str
    instance_uuid: str
    csrf_hash: str
    credential_version: int
    created_at: datetime
    authenticated_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoked_by: str | None


@dataclass(frozen=True)
class AutomationTokenRecord:
    token_id: str
    token_hash: str
    principal_id: str
    permissions: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoked_by: str | None


@dataclass(frozen=True)
class AuthenticatedActor:
    principal_id: str
    username: str
    kind: PrincipalKind | Literal["legacy"]
    roles: tuple[Role, ...]
    permissions: frozenset[str]
    authentication: Literal["session", "automation_token", "legacy_api_key"]
    session_hash: str | None = None
    csrf_hash: str | None = None
    authenticated_at: datetime | None = None

    def permits(self, permission: str) -> bool:
        return permission in self.permissions


class IdentityError(RuntimeError):
    """Stable, payload-free identity failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
