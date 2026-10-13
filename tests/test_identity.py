from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from samuel.adapters.api.auth import AuthRuntimeConfig, DashboardAuth
from samuel.adapters.auth.local import LocalIdentityService
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.identity import (
    MANAGE_IDENTITIES,
    RUN_OPERATIONS,
    VIEW_STATUS,
    IdentityError,
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


def _service(tmp_path: Path, *, clock: Clock | None = None):
    store = SQLiteStateStore(tmp_path)
    active_clock = clock or Clock()
    service = LocalIdentityService(
        store.identity,
        instance_uuid=lambda: str(store.authority.authority_status()["instance"]),
        clock=active_clock,
    )
    return store, service, active_clock


def _auth(service: LocalIdentityService) -> DashboardAuth:
    return DashboardAuth(
        AuthRuntimeConfig(
            access_mode="local_identity",
            secure_cookies=False,
            session_absolute_seconds=28_800,
            session_idle_seconds=1_800,
            fresh_auth_seconds=300,
            login_attempts=5,
            login_window_seconds=300,
        ),
        local=service,
    )


def test_bootstrap_uses_argon2_and_roles_are_not_hierarchical(tmp_path: Path) -> None:
    store, service, _clock = _service(tmp_path)

    principal = service.bootstrap("admin", "correct horse battery staple")
    issued = service.login("admin", "correct horse battery staple", client_key="127.0.0.1")

    assert store.identity.status() == "active"
    assert principal.password_hash is not None
    assert service.password_is_argon2(principal.password_hash)
    assert issued.actor.roles == ("administrator",)
    assert issued.actor.permits(MANAGE_IDENTITIES)
    assert not issued.actor.permits(VIEW_STATUS)
    assert not issued.actor.permits(RUN_OPERATIONS)


def test_session_survives_restart_but_idle_and_role_change_revoke(tmp_path: Path) -> None:
    store, service, clock = _service(tmp_path)
    principal = service.bootstrap("operator", "correct horse battery staple")
    store.identity.update_user(principal.principal_id, roles=("operator",))
    issued = service.login("operator", "correct horse battery staple", client_key="127.0.0.1")

    reopened = SQLiteStateStore(tmp_path)
    after_restart = LocalIdentityService(
        reopened.identity,
        instance_uuid=lambda: str(reopened.authority.authority_status()["instance"]),
        clock=clock,
    )
    actor = after_restart.authenticate_session(issued.session_token)
    assert actor is not None and actor.permits(RUN_OPERATIONS)

    reopened.identity.update_user(principal.principal_id, roles=("viewer",))
    assert after_restart.authenticate_session(issued.session_token) is None

    second = after_restart.login("operator", "correct horse battery staple", client_key="127.0.0.1")
    clock.advance(minutes=30)
    assert after_restart.authenticate_session(second.session_token) is None


def test_cookie_session_requires_csrf_for_mutation(tmp_path: Path) -> None:
    _store, service, _clock = _service(tmp_path)
    service.bootstrap("admin", "correct horse battery staple")
    issued = service.login("admin", "correct horse battery staple", client_key="127.0.0.1")
    auth = _auth(service)
    cookie = {"Cookie": f"samuel_session={issued.session_token}"}

    missing = auth.authorize("POST", "/api/v1/settings/flag", cookie)
    allowed = auth.authorize(
        "POST",
        "/api/v1/settings/flag",
        {**cookie, "X-CSRF-Token": issued.csrf_token},
    )

    assert missing.status == 403 and missing.code == "csrf_validation_failed"
    assert allowed.allowed is True


def test_unknown_or_method_mismatched_endpoint_is_denied(tmp_path: Path) -> None:
    store, service, _clock = _service(tmp_path)
    principal = service.bootstrap("viewer", "correct horse battery staple")
    store.identity.update_user(principal.principal_id, roles=("viewer",))
    issued = service.login("viewer", "correct horse battery staple", client_key="client")
    auth = _auth(service)
    cookie = {"Cookie": f"samuel_session={issued.session_token}"}

    assert auth.authorize("HEAD", "/api/v1/dashboard/status", cookie).allowed is True
    unknown = auth.authorize("GET", "/api/v1/unknown", cookie)
    wrong_method = auth.authorize("POST", "/api/v1/dashboard/status", cookie)

    assert (unknown.status, unknown.code) == (403, "endpoint_not_authorized")
    assert (wrong_method.status, wrong_method.code) == (403, "endpoint_not_authorized")


def test_auth_config_requires_boolean_secure_cookie_setting(tmp_path: Path) -> None:
    document = json.loads((Path(__file__).parents[1] / "config" / "auth.json").read_text())
    document["secure_cookies"] = "false"
    config = tmp_path / "config"
    config.mkdir()
    (config / "auth.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="secure_cookies must be a boolean"):
        AuthRuntimeConfig.load(config)


def test_restore_requires_local_recovery_and_never_reactivates_old_session(
    tmp_path: Path,
) -> None:
    store, service, clock = _service(tmp_path / "live")
    service.bootstrap("admin", "correct horse battery staple")
    issued = service.login("admin", "correct horse battery staple", client_key="127.0.0.1")
    backup = store.backup(tmp_path / "identity-backup.sqlite3")

    operation = store.restore(backup)

    assert operation.status == "reconcile_required"
    assert store.identity.status() == "recovery_pending"
    assert service.authenticate_session(issued.session_token) is None
    with pytest.raises(IdentityError, match="not active"):
        service.login("admin", "correct horse battery staple", client_key="127.0.0.1")

    service.recover("admin", "new correct horse battery staple", reason="verified restore")
    assert store.identity.status() == "active"
    assert service.authenticate_session(issued.session_token) is None
    assert (
        service.login(
            "admin", "new correct horse battery staple", client_key="127.0.0.1"
        ).actor.username
        == "admin"
    )
    assert clock.value.tzinfo is not None


def test_restore_before_identity_bootstrap_remains_bootstrappable(tmp_path: Path) -> None:
    store, service, _clock = _service(tmp_path / "live")
    backup = store.backup(tmp_path / "legacy-backup.sqlite3")

    operation = store.restore(backup)

    assert operation.status == "reconcile_required"
    assert store.identity.status() == "uninitialized"
    assert service.bootstrap("admin", "correct horse battery staple").roles == ("administrator",)


def test_login_rate_limit_is_fail_closed_without_secret_audit_payload(tmp_path: Path) -> None:
    events: list[tuple[str, str, dict]] = []
    store = SQLiteStateStore(tmp_path)
    service = LocalIdentityService(
        store.identity,
        instance_uuid=lambda: str(store.authority.authority_status()["instance"]),
        login_attempts=2,
        audit=lambda event, actor, meta: events.append((event, actor, meta)),
    )
    service.bootstrap("admin", "correct horse battery staple")

    for _ in range(2):
        with pytest.raises(IdentityError, match="Invalid username or password"):
            service.login("admin", "wrong password", client_key="client")
    with pytest.raises(IdentityError, match="Too many login attempts"):
        service.login("admin", "correct horse battery staple", client_key="client")

    assert all("password" not in str(meta).lower() for _event, _actor, meta in events)
