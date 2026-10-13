"""Local standalone identity provider using Argon2 and opaque server sessions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from samuel.core.identity import (
    ALL_PERMISSIONS,
    AuthenticatedActor,
    AutomationTokenRecord,
    IdentityError,
    PrincipalRecord,
    Role,
    SessionRecord,
    permissions_for_roles,
)
from samuel.core.ports import IIdentityStateStore

AuditCallback = Callable[[str, str, dict[str, Any]], None]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_username(username: str) -> str:
    normalized = username.strip()
    if not (3 <= len(normalized) <= 64):
        raise IdentityError(
            "identity_username_invalid", "Username must contain between 3 and 64 characters"
        )
    if not all(character.isalnum() or character in {"-", "_", "."} for character in normalized):
        raise IdentityError("identity_username_invalid", "Username contains unsupported characters")
    return normalized


def _validate_password(password: str) -> None:
    if len(password) < 12 or len(password) > 1024:
        raise IdentityError(
            "identity_password_invalid", "Password must contain between 12 and 1024 characters"
        )


def _validate_roles(roles: tuple[str, ...]) -> tuple[Role, ...]:
    valid = {"viewer", "auditor", "operator", "administrator"}
    if not roles or any(role not in valid for role in roles):
        raise IdentityError("identity_roles_invalid", "At least one known role is required")
    return cast(tuple[Role, ...], tuple(sorted(set(roles))))


@dataclass(frozen=True)
class IssuedSession:
    session_token: str
    csrf_token: str
    record: SessionRecord
    actor: AuthenticatedActor


@dataclass(frozen=True)
class IssuedAutomationToken:
    token: str
    token_id: str
    principal_id: str
    username: str
    permissions: tuple[str, ...]
    expires_at: datetime


class LoginRateLimiter:
    """Small process-local limiter; persisted auth state never grants a bypass."""

    def __init__(self, attempts: int = 5, window_seconds: int = 300, *, clock: Clock = _utc_now):
        self._attempts = attempts
        self._window = timedelta(seconds=window_seconds)
        self._clock = clock
        self._failures: dict[str, deque[datetime]] = defaultdict(deque)

    def _active(self, key: str) -> deque[datetime]:
        now = self._clock()
        failures = self._failures[key]
        while failures and now - failures[0] >= self._window:
            failures.popleft()
        return failures

    def allowed(self, key: str) -> bool:
        return len(self._active(key)) < self._attempts

    def failed(self, key: str) -> None:
        self._active(key).append(self._clock())

    def succeeded(self, key: str) -> None:
        self._failures.pop(key, None)


class LocalIdentityService:
    """Reference provider; all durable authority remains in ``IIdentityStateStore``."""

    def __init__(
        self,
        state: IIdentityStateStore,
        *,
        instance_uuid: Callable[[], str],
        absolute_seconds: int = 8 * 60 * 60,
        idle_seconds: int = 30 * 60,
        fresh_seconds: int = 5 * 60,
        login_attempts: int = 5,
        login_window_seconds: int = 5 * 60,
        clock: Clock = _utc_now,
        audit: AuditCallback | None = None,
    ) -> None:
        if absolute_seconds <= 0 or idle_seconds <= 0 or fresh_seconds <= 0:
            raise ValueError("identity session durations must be positive")
        self._state = state
        self._instance_uuid = instance_uuid
        self._absolute = timedelta(seconds=absolute_seconds)
        self._idle = timedelta(seconds=idle_seconds)
        self._fresh = timedelta(seconds=fresh_seconds)
        self._clock = clock
        self._audit = audit or (lambda _event, _actor, _meta: None)
        self._passwords = PasswordHasher()
        self._rate_limit = LoginRateLimiter(
            attempts=login_attempts, window_seconds=login_window_seconds, clock=clock
        )

    def status(self) -> str:
        return self._state.status()

    def list_principals(self) -> list[PrincipalRecord]:
        return self._state.list_principals()

    def list_sessions(self, principal_id: str | None = None) -> list[SessionRecord]:
        return self._state.list_sessions(principal_id)

    def list_automation_tokens(self) -> list[AutomationTokenRecord]:
        return self._state.list_automation_tokens()

    @staticmethod
    def password_is_argon2(value: str) -> bool:
        return value.startswith("$argon2")

    def hash_password(self, password: str) -> str:
        _validate_password(password)
        return self._passwords.hash(password)

    def _verify_password(self, principal: PrincipalRecord, password: str) -> bool:
        if principal.password_hash is None:
            return False
        try:
            return bool(self._passwords.verify(principal.password_hash, password))
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def bootstrap(self, username: str, password: str) -> PrincipalRecord:
        username = _validate_username(username)
        principal = self._state.bootstrap_administrator(username, self.hash_password(password))
        self._audit(
            "identity_bootstrapped", f"user:{principal.principal_id}", {"username": username}
        )
        return principal

    def recover(self, username: str, password: str, *, reason: str) -> PrincipalRecord:
        username = _validate_username(username)
        principal = self._state.recover_administrator(
            username, self.hash_password(password), reason=reason
        )
        self._audit(
            "identity_recovered",
            f"user:{principal.principal_id}",
            {"username": username, "reason": reason.strip()},
        )
        return principal

    def _issue_session(self, principal: PrincipalRecord) -> IssuedSession:
        now = self._clock()
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        record = SessionRecord(
            session_id=str(uuid4()),
            session_hash=_digest(session_token),
            principal_id=principal.principal_id,
            instance_uuid=self._instance_uuid(),
            csrf_hash=_digest(csrf_token),
            credential_version=principal.credential_version,
            created_at=now,
            authenticated_at=now,
            last_seen_at=now,
            expires_at=now + self._absolute,
            revoked_at=None,
            revoked_by=None,
        )
        self._state.create_session(record)
        actor = AuthenticatedActor(
            principal_id=principal.principal_id,
            username=principal.username,
            kind=principal.kind,
            roles=principal.roles,
            permissions=permissions_for_roles(principal.roles),
            authentication="session",
            session_hash=record.session_hash,
            csrf_hash=record.csrf_hash,
            authenticated_at=record.authenticated_at,
        )
        return IssuedSession(session_token, csrf_token, record, actor)

    def login(self, username: str, password: str, *, client_key: str) -> IssuedSession:
        username = username.strip()
        limiter_key = f"{client_key}:{username.casefold()}"
        if not self._rate_limit.allowed(limiter_key):
            self._audit("login_rate_limited", "anonymous", {"username": username})
            raise IdentityError("authentication_rate_limited", "Too many login attempts")
        if self._state.status() != "active":
            self._rate_limit.failed(limiter_key)
            raise IdentityError("identity_not_active", "Local identity is not active")
        principal = self._state.get_principal_by_username(username)
        if (
            principal is None
            or principal.kind != "user"
            or principal.disabled
            or not self._verify_password(principal, password)
        ):
            self._rate_limit.failed(limiter_key)
            self._audit("login_failed", "anonymous", {"username": username})
            raise IdentityError("authentication_failed", "Invalid username or password")
        self._rate_limit.succeeded(limiter_key)
        issued = self._issue_session(principal)
        self._audit(
            "login_succeeded",
            f"user:{principal.principal_id}",
            {"username": principal.username, "session_id": issued.record.session_id},
        )
        return issued

    def authenticate_session(self, session_token: str) -> AuthenticatedActor | None:
        if not session_token or self._state.status() != "active":
            return None
        session = self._state.get_session(_digest(session_token))
        now = self._clock()
        if (
            session is None
            or session.revoked_at is not None
            or session.instance_uuid != self._instance_uuid()
            or now >= session.expires_at
            or now - session.last_seen_at >= self._idle
        ):
            return None
        principal = self._state.get_principal(session.principal_id)
        if (
            principal is None
            or principal.kind != "user"
            or principal.disabled
            or principal.credential_version != session.credential_version
        ):
            return None
        self._state.touch_session(session.session_hash, now)
        return AuthenticatedActor(
            principal_id=principal.principal_id,
            username=principal.username,
            kind=principal.kind,
            roles=principal.roles,
            permissions=permissions_for_roles(principal.roles),
            authentication="session",
            session_hash=session.session_hash,
            csrf_hash=session.csrf_hash,
            authenticated_at=session.authenticated_at,
        )

    def authenticate_token(self, raw_token: str) -> AuthenticatedActor | None:
        if not raw_token or self._state.status() != "active":
            return None
        token = self._state.get_automation_token(_digest(raw_token))
        now = self._clock()
        if token is None or token.revoked_at is not None or now >= token.expires_at:
            return None
        principal = self._state.get_principal(token.principal_id)
        if principal is None or principal.kind != "automation" or principal.disabled:
            return None
        return AuthenticatedActor(
            principal_id=principal.principal_id,
            username=principal.username,
            kind=principal.kind,
            roles=(),
            permissions=frozenset(token.permissions),
            authentication="automation_token",
        )

    def csrf_valid(self, actor: AuthenticatedActor, token: str) -> bool:
        csrf_hash = actor.csrf_hash
        return bool(csrf_hash and token) and hmac.compare_digest(csrf_hash or "", _digest(token))

    def is_fresh(self, actor: AuthenticatedActor) -> bool:
        return bool(
            actor.authentication == "session"
            and actor.authenticated_at is not None
            and self._clock() - actor.authenticated_at < self._fresh
        )

    def reauthenticate(self, actor: AuthenticatedActor, password: str) -> IssuedSession:
        if actor.authentication != "session" or actor.session_hash is None:
            raise IdentityError("reauthentication_required", "A user session is required")
        principal = self._state.get_principal(actor.principal_id)
        if (
            principal is None
            or principal.disabled
            or not self._verify_password(principal, password)
        ):
            self._audit("reauthentication_failed", f"user:{actor.principal_id}", {})
            raise IdentityError("reauthentication_failed", "Password verification failed")
        now = self._clock()
        self._state.revoke_session(actor.session_hash, actor=actor.principal_id, revoked_at=now)
        issued = self._issue_session(principal)
        self._audit(
            "session_rotated",
            f"user:{actor.principal_id}",
            {"session_id": issued.record.session_id},
        )
        return issued

    def logout(self, actor: AuthenticatedActor) -> bool:
        if actor.authentication != "session" or actor.session_hash is None:
            return False
        revoked = self._state.revoke_session(
            actor.session_hash, actor=actor.principal_id, revoked_at=self._clock()
        )
        if revoked:
            self._audit("logout", f"user:{actor.principal_id}", {})
        return revoked

    def create_user(
        self, actor: AuthenticatedActor, username: str, password: str, roles: tuple[str, ...]
    ) -> PrincipalRecord:
        username = _validate_username(username)
        validated_roles = _validate_roles(roles)
        principal = self._state.create_user(username, self.hash_password(password), validated_roles)
        self._audit(
            "user_created",
            f"user:{actor.principal_id}",
            {
                "subject": principal.principal_id,
                "username": username,
                "roles": list(validated_roles),
            },
        )
        return principal

    def update_user(
        self,
        actor: AuthenticatedActor,
        principal_id: str,
        *,
        roles: tuple[str, ...] | None = None,
        disabled: bool | None = None,
        password: str | None = None,
    ) -> PrincipalRecord:
        validated_roles = _validate_roles(roles) if roles is not None else None
        existing = self._state.get_principal(principal_id)
        if existing is None or existing.kind != "user":
            raise IdentityError("identity_principal_missing", "User does not exist")
        removes_admin = "administrator" in existing.roles and (
            disabled is True
            or (validated_roles is not None and "administrator" not in validated_roles)
        )
        if removes_admin and not any(
            candidate.principal_id != principal_id
            and not candidate.disabled
            and "administrator" in candidate.roles
            for candidate in self._state.list_principals()
        ):
            raise IdentityError(
                "identity_last_administrator",
                "The final active administrator cannot be removed or disabled",
            )
        password_hash = self.hash_password(password) if password is not None else None
        principal = self._state.update_user(
            principal_id,
            roles=validated_roles,
            disabled=disabled,
            password_hash=password_hash,
        )
        self._audit(
            "user_updated",
            f"user:{actor.principal_id}",
            {
                "subject": principal_id,
                "roles": list(validated_roles) if validated_roles is not None else None,
                "disabled": disabled,
                "password_changed": password_hash is not None,
            },
        )
        return principal

    def revoke_session(self, actor: AuthenticatedActor, session_id: str) -> bool:
        revoked = self._state.revoke_session_id(
            session_id, actor=actor.principal_id, revoked_at=self._clock()
        )
        if revoked:
            self._audit(
                "session_revoked",
                f"user:{actor.principal_id}",
                {"session_id": session_id},
            )
        return revoked

    def revoke_all_sessions(self, actor: AuthenticatedActor) -> int:
        count = self._state.revoke_sessions(
            principal_id=None, actor=actor.principal_id, revoked_at=self._clock()
        )
        self._audit(
            "sessions_revoked_globally",
            f"user:{actor.principal_id}",
            {"count": count},
        )
        return count

    def create_automation_token(
        self,
        actor: AuthenticatedActor,
        name: str,
        permissions: tuple[str, ...],
        *,
        lifetime_seconds: int,
    ) -> IssuedAutomationToken:
        username = _validate_username(name)
        normalized = tuple(sorted(set(permissions)))
        if not normalized or any(permission not in ALL_PERMISSIONS for permission in normalized):
            raise IdentityError(
                "identity_token_permissions_invalid",
                "Automation token permissions must be an explicit known non-empty set",
            )
        if lifetime_seconds <= 0 or lifetime_seconds > 365 * 24 * 60 * 60:
            raise IdentityError(
                "identity_token_lifetime_invalid", "Automation token lifetime is invalid"
            )
        now = self._clock()
        principal_id = str(uuid4())
        token_id = str(uuid4())
        raw = "samuel_" + secrets.token_urlsafe(32)
        principal = PrincipalRecord(
            principal_id=principal_id,
            username=username,
            kind="automation",
            password_hash=None,
            disabled=False,
            credential_version=1,
            roles=(),
            created_at=now,
            updated_at=now,
        )
        token = AutomationTokenRecord(
            token_id=token_id,
            token_hash=_digest(raw),
            principal_id=principal_id,
            permissions=normalized,
            created_at=now,
            expires_at=now + timedelta(seconds=lifetime_seconds),
            revoked_at=None,
            revoked_by=None,
        )
        self._state.create_automation_token(principal, token)
        self._audit(
            "automation_token_created",
            f"user:{actor.principal_id}",
            {
                "subject": principal_id,
                "token_id": token_id,
                "permissions": list(normalized),
                "expires_at": token.expires_at.isoformat(),
            },
        )
        return IssuedAutomationToken(
            token=raw,
            token_id=token_id,
            principal_id=principal_id,
            username=username,
            permissions=normalized,
            expires_at=token.expires_at,
        )

    def revoke_automation_token(self, actor: AuthenticatedActor, token_id: str) -> bool:
        revoked = self._state.revoke_automation_token(
            token_id, actor=actor.principal_id, revoked_at=self._clock()
        )
        if revoked:
            self._audit(
                "automation_token_revoked",
                f"user:{actor.principal_id}",
                {"token_id": token_id},
            )
        return revoked
