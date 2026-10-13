"""Dashboard authentication and deny-by-default endpoint authorization."""

from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from samuel.adapters.auth.local import LocalIdentityService
from samuel.core.identity import (
    ALL_PERMISSIONS,
    MANAGE_IDENTITIES,
    MANAGE_SESSIONS,
    READ_AUDIT,
    READ_CONFIGURATION,
    READ_DIAGNOSTICS,
    RUN_OPERATIONS,
    RUN_PROVIDER_PROBES,
    VIEW_STATUS,
    WRITE_CONFIGURATION,
    AuthenticatedActor,
)

log = logging.getLogger(__name__)

AccessMode = Literal["legacy_api_key", "local_identity"]
AUTHENTICATED = "authenticated"


@dataclass(frozen=True)
class AuthRuntimeConfig:
    access_mode: AccessMode
    secure_cookies: bool
    session_absolute_seconds: int
    session_idle_seconds: int
    fresh_auth_seconds: int
    login_attempts: int
    login_window_seconds: int

    @classmethod
    def load(cls, config_dir: Path | str) -> AuthRuntimeConfig:
        path = Path(config_dir) / "auth.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"dashboard auth configuration is unreadable: {path}") from exc
        if not isinstance(raw, dict) or set(raw) != {
            "schema_version",
            "access_mode",
            "secure_cookies",
            "session_absolute_seconds",
            "session_idle_seconds",
            "fresh_auth_seconds",
            "login_attempts",
            "login_window_seconds",
        }:
            raise ValueError("dashboard auth configuration has unknown or missing fields")
        if raw.get("schema_version") != 1:
            raise ValueError("dashboard auth schema_version must be 1")
        mode = str(raw.get("access_mode", ""))
        if mode not in {"legacy_api_key", "local_identity"}:
            raise ValueError("dashboard auth access_mode is invalid")
        integer_fields = (
            "session_absolute_seconds",
            "session_idle_seconds",
            "fresh_auth_seconds",
            "login_attempts",
            "login_window_seconds",
        )
        if any(
            not isinstance(raw[field], int) or isinstance(raw[field], bool) or int(raw[field]) <= 0
            for field in integer_fields
        ):
            raise ValueError("dashboard auth duration and limiter values must be positive integers")
        if not isinstance(raw["secure_cookies"], bool):
            raise ValueError("dashboard auth secure_cookies must be a boolean")
        return cls(
            access_mode=cast(AccessMode, mode),
            secure_cookies=bool(raw["secure_cookies"]),
            session_absolute_seconds=int(raw["session_absolute_seconds"]),
            session_idle_seconds=int(raw["session_idle_seconds"]),
            fresh_auth_seconds=int(raw["fresh_auth_seconds"]),
            login_attempts=int(raw["login_attempts"]),
            login_window_seconds=int(raw["login_window_seconds"]),
        )


@dataclass(frozen=True)
class AuthDecision:
    actor: AuthenticatedActor | None
    status: int
    code: str

    @property
    def allowed(self) -> bool:
        return self.actor is not None and self.status == 200


def _headers(headers: dict[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _cookie_value(headers: dict[str, str], name: str) -> str:
    raw = _headers(headers).get("cookie", "")
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except CookieError:
        return ""
    morsel = cookie.get(name)
    return morsel.value if morsel is not None else ""


def permission_for_request(method: str, raw_path: str) -> str | None:
    """Return one explicit permission for every authenticated API entrypoint."""

    method = method.upper()
    if method == "HEAD":
        method = "GET"
    path = urlsplit(raw_path).path
    route = f"{method} {path}"
    if route in {
        "GET /api/v1/auth/check",
        "GET /api/v1/auth/session",
        "POST /api/v1/auth/logout",
        "POST /api/v1/auth/reauth",
    }:
        return AUTHENTICATED
    if path.startswith("/api/v1/admin/users"):
        return MANAGE_IDENTITIES
    if path.startswith("/api/v1/admin/sessions"):
        return MANAGE_SESSIONS
    if path.startswith("/api/v1/admin/tokens"):
        return MANAGE_IDENTITIES
    if route == "GET /api/v1/dashboard/status":
        return VIEW_STATUS
    if route in {
        "GET /api/v1/dashboard/metrics",
        "GET /api/v1/dashboard/health",
        "GET /api/v1/dashboard/problems",
        "GET /api/v1/dashboard/workflow",
        "GET /api/v1/dashboard/llm",
        "GET /api/v1/dashboard/llm/pricing-info",
        "GET /api/metrics",
    } or (method == "GET" and path.startswith("/api/v1/dashboard/workflow/")):
        return READ_DIAGNOSTICS
    if route in {
        "GET /api/v1/dashboard/logs",
        "GET /api/v1/dashboard/security",
        "GET /api/v1/dashboard/compliance/legend",
        "GET /api/v1/dashboard/dlq",
        "GET /api/v1/dashboard/quality",
        "GET /api/v1/dashboard/activity",
        "GET /api/v1/dashboard/transfer_warnings",
    }:
        return READ_AUDIT
    if route in {
        "GET /api/v1/setup/status",
        "GET /api/v1/dashboard/settings",
        "GET /api/v1/dashboard/llm/schedule",
    } or (method == "GET" and path.startswith("/api/v1/dashboard/llm/prompts")):
        return READ_CONFIGURATION
    if method == "GET" and path.startswith("/api/v1/dashboard/llm/models"):
        return RUN_PROVIDER_PROBES
    if route in {
        "POST /api/v1/dashboard/llm/test-connection",
        "GET /api/v1/dashboard/self_check",
    }:
        return RUN_PROVIDER_PROBES
    if route in {
        "POST /api/v1/setup/labels",
        "POST /api/v1/dashboard/llm/models/refresh",
        "POST /api/v1/scan",
        "GET /api/v1/health",
        "GET /api/v1/dashboard/self-mode/health",
    } or (
        method == "POST"
        and path.startswith("/api/v1/issues/")
        and (path.endswith("/plan") or path.endswith("/implement"))
    ):
        return RUN_OPERATIONS
    if route in {
        "POST /api/v1/setup/configure",
        "POST /api/v1/settings/flag",
        "POST /api/v1/settings/extensions/documentation",
        "POST /api/v1/settings/risk-class",
        "POST /api/v1/settings/attribution",
        "POST /api/v1/settings/llm/global",
        "POST /api/v1/settings/llm/task",
    } or (method in {"POST", "DELETE"} and path.startswith("/api/v1/dashboard/llm/prompts/")):
        return WRITE_CONFIGURATION
    return None


class APIKeyAuth:
    """Explicit legacy adapter retained only until local-identity cutover."""

    def __init__(self, valid_keys: list[str] | None = None) -> None:
        self._valid_keys = set(valid_keys or [])

    def authenticate(self, headers: dict[str, str]) -> bool:
        return self.actor(headers) is not None

    def actor(self, headers: dict[str, str]) -> AuthenticatedActor | None:
        if not self._valid_keys:
            return None
        lc = _headers(headers)
        auth = lc.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else lc.get("x-api-key", "")
        if not token or not any(hmac.compare_digest(token, key) for key in self._valid_keys):
            return None
        return AuthenticatedActor(
            principal_id="legacy-api-key",
            username="legacy-api-key",
            kind="legacy",
            roles=("viewer", "auditor", "operator", "administrator"),
            permissions=ALL_PERMISSIONS,
            authentication="legacy_api_key",
        )


class DashboardAuth:
    """One access mode; local identity never falls back to the legacy key."""

    cookie_name = "samuel_session"

    def __init__(
        self,
        config: AuthRuntimeConfig,
        *,
        legacy: APIKeyAuth | None = None,
        local: LocalIdentityService | None = None,
    ) -> None:
        self.config = config
        self.legacy = legacy
        self.local = local
        if config.access_mode == "legacy_api_key" and legacy is None:
            raise ValueError("legacy_api_key mode requires SAMUEL_API_KEY")
        if config.access_mode == "local_identity" and local is None:
            raise ValueError("local_identity mode requires the runtime identity state")

    def authenticate(self, headers: dict[str, str]) -> bool:
        return self.authenticate_actor(headers) is not None

    def authenticate_actor(self, headers: dict[str, str]) -> AuthenticatedActor | None:
        if self.config.access_mode == "legacy_api_key":
            return self.legacy.actor(headers) if self.legacy is not None else None
        if self.local is None:
            return None
        lc = _headers(headers)
        authorization = lc.get("authorization", "")
        if authorization.startswith("Bearer "):
            return self.local.authenticate_token(authorization[7:])
        return self.local.authenticate_session(_cookie_value(headers, self.cookie_name))

    def authorize(self, method: str, path: str, headers: dict[str, str]) -> AuthDecision:
        actor = self.authenticate_actor(headers)
        if actor is None:
            return AuthDecision(None, 401, "authentication_required")
        permission = permission_for_request(method, path)
        if permission is None:
            return AuthDecision(actor, 403, "endpoint_not_authorized")
        if permission != AUTHENTICATED and not actor.permits(permission):
            return AuthDecision(actor, 403, "permission_denied")
        if (
            actor.authentication == "session"
            and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            and self.local is not None
            and not self.local.csrf_valid(actor, _headers(headers).get("x-csrf-token", ""))
        ):
            return AuthDecision(actor, 403, "csrf_validation_failed")
        return AuthDecision(actor, 200, "authorized")

    def status(self) -> dict[str, Any]:
        identity_status: str = "legacy"
        if self.local is not None:
            identity_status = self.local.status()
        return {
            "access_mode": self.config.access_mode,
            "secure_cookies": self.config.secure_cookies,
            "transport": "https" if self.config.secure_cookies else "http_or_untrusted_proxy",
            "identity_status": identity_status,
            "legacy_fallback": False,
        }
