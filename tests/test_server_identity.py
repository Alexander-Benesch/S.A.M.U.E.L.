from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from samuel.adapters.auth.local import LocalIdentityService
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.bus import Bus
from samuel.core.configuration_session import ConfigurationSession
from samuel.server import create_server


@contextmanager
def _serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _url(server, path: str) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}{path}"


def _runtime(
    tmp_path: Path, *, access_mode: str = "local_identity", bootstrap_identity: bool = True
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    auth = json.loads((Path(__file__).parents[1] / "config" / "auth.json").read_text())
    auth["access_mode"] = access_mode
    (config_dir / "auth.json").write_text(json.dumps(auth), encoding="utf-8")
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: (
        str(config_dir) if key == "agent.config_dir" else default
    )
    store = SQLiteStateStore(tmp_path / "runtime")
    identity = LocalIdentityService(
        store.identity,
        instance_uuid=lambda: store.status().authority_instance,
    )
    if bootstrap_identity:
        identity.bootstrap("admin", "administrator-password")
        admin_session = identity.login("admin", "administrator-password", client_key="fixture")
        identity.create_user(
            admin_session.actor,
            "viewer",
            "viewer-password-long",
            ("viewer",),
        )
    bus = Bus()
    bus.state_store = store
    bus.register_command("HealthCheck", lambda _command: {"healthy": True, "checks": {}})
    return bus, config


def _login(opener, server, username: str, password: str) -> dict[str, Any]:
    request = urllib.request.Request(
        _url(server, "/api/v1/auth/login"),
        data=json.dumps({"username": username, "password": password}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    # Login verifies the real password hash and persists the session. This test
    # checks authorization and CSRF, with a bounded wait for the HTTP response.
    with opener.open(request, timeout=10) as response:
        return cast(dict[str, Any], json.load(response))


def _csrf(jar: CookieJar) -> str:
    return cast(str, next(cookie.value for cookie in jar if cookie.name == "samuel_csrf"))


def test_identity_state_contention_rejects_http_mutation_and_recovers_after_unlock(tmp_path):
    bus, config = _runtime(tmp_path)
    server = create_server(bus, host="127.0.0.1", port=0, config=config, configuration_mode="setup")
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    path = tmp_path / "config/features.json"
    with _serve(server):
        _login(opener, server, "admin", "administrator-password")
        request = urllib.request.Request(
            _url(server, "/api/v1/settings/flag"),
            data=b'{"name":"eval","enabled":true}',
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": _csrf(jar)},
        )
        with sqlite3.connect(bus.state_store.path) as writer:
            writer.execute("BEGIN IMMEDIATE")
            with pytest.raises(urllib.error.HTTPError) as blocked:
                opener.open(request, timeout=5)
            assert blocked.value.code == 503
            assert json.load(blocked.value)["code"] == "state_locked"
            assert not path.exists()
            writer.rollback()
        assert opener.open(request, timeout=5).status == 200
        assert json.loads(path.read_text())["eval"] is True


def test_dashboard_identity_uses_its_runtime_audit_writer(tmp_path, monkeypatch):
    from samuel.adapters.audit.jsonl import JSONLAuditSink, verify_chain
    from samuel.core.bus import AuditMiddleware
    from samuel.slices.audit_trail import bridge

    fallback = tmp_path / "unsigned-fallback.jsonl"
    monkeypatch.setattr(bridge, "_bus", None)
    monkeypatch.setattr(bridge, "_jsonl_path", fallback)
    bus, config = _runtime(tmp_path)
    log = tmp_path / "signed-runtime.jsonl"
    key = "synthetic-runtime-audit-key"
    sink = JSONLAuditSink(log, rotation="none", hmac_key=key)
    bus.add_middleware(AuditMiddleware(sink))
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with _serve(server):
        _login(opener, server, "admin", "administrator-password")
    assert not fallback.exists(), "Dashboard identity bypassed its runtime audit writer"
    assert verify_chain(log, key)["ok"]
    records = [json.loads(line) for line in log.read_text().splitlines()]
    event = next(r["payload"] for r in records if r["payload"].get("evt") == "login_succeeded")
    assert event["source"] == "dashboard" and event["meta"]["actor"].startswith("user:")
    assert "administrator-password" not in log.read_text()


def test_authenticated_setup_write_observes_runtime_admission_fence(tmp_path: Path) -> None:
    bus, config = _runtime(tmp_path)
    session = ConfigurationSession(bus.state_store.authority)
    bus.configuration_session = session
    server = create_server(bus, host="127.0.0.1", port=0, config=config, configuration_mode="setup")
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    path = tmp_path / "config/features.json"

    def request():
        return urllib.request.Request(
            _url(server, "/api/v1/settings/flag"),
            data=json.dumps({"name": "eval", "enabled": True}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": _csrf(jar)},
        )

    with _serve(server):
        _login(opener, server, "admin", "administrator-password")
        with session.admission(), pytest.raises(urllib.error.HTTPError) as blocked:
            opener.open(request(), timeout=2)
        assert blocked.value.code == 409
        assert not path.exists()
        with opener.open(request(), timeout=2) as response:
            assert response.status == 200
            result = json.load(response)
        assert result["updated"] is True and result["restart_required"] is True
        assert json.loads(path.read_text())["eval"] is True
        assert session.state()["active"] == {}


def test_local_session_uses_cookies_csrf_and_explicit_role_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAMUEL_API_KEY", "must-not-be-a-fallback")
    bus, config = _runtime(tmp_path)
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    with _serve(server):
        mode = json.loads(opener.open(_url(server, "/api/v1/auth/mode"), timeout=2).read())
        assert mode["access_mode"] == "local_identity"
        assert mode["legacy_fallback"] is False

        legacy = urllib.request.Request(
            _url(server, "/api/v1/dashboard/status"),
            headers={"X-API-Key": "must-not-be-a-fallback"},
        )
        with pytest.raises(urllib.error.HTTPError) as legacy_error:
            opener.open(legacy, timeout=2)
        assert legacy_error.value.code == 401

        login = _login(opener, server, "viewer", "viewer-password-long")
        assert login["actor"]["roles"] == ["viewer"]
        session_cookie = next(cookie for cookie in jar if cookie.name == "samuel_session")
        assert session_cookie.has_nonstandard_attr("HttpOnly")
        assert session_cookie.get_nonstandard_attr("SameSite") == "Strict"

        status = json.loads(opener.open(_url(server, "/api/v1/dashboard/status"), timeout=2).read())
        assert set(status) == {
            "service",
            "available",
            "product_version",
            "access",
            "technical_health",
            "operational_readiness",
            "qualification",
            "audit_writer",
        }
        assert status["audit_writer"] == "unknown"

        with pytest.raises(urllib.error.HTTPError) as users_error:
            opener.open(_url(server, "/api/v1/admin/users"), timeout=2)
        assert users_error.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as diagnostic_error:
            opener.open(_url(server, "/api/v1/dashboard/health"), timeout=2)
        assert diagnostic_error.value.code == 403

        logout_without_csrf = urllib.request.Request(
            _url(server, "/api/v1/auth/logout"), data=b"{}", method="POST"
        )
        with pytest.raises(urllib.error.HTTPError) as csrf_error:
            opener.open(logout_without_csrf, timeout=2)
        assert csrf_error.value.code == 403

        logout = urllib.request.Request(
            _url(server, "/api/v1/auth/logout"),
            data=b"{}",
            method="POST",
            headers={"X-CSRF-Token": _csrf(jar)},
        )
        assert opener.open(logout, timeout=2).status == 200


def test_administrator_api_requires_session_and_returns_token_only_on_creation(
    tmp_path: Path,
) -> None:
    bus, config = _runtime(tmp_path)
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    with _serve(server):
        _login(opener, server, "admin", "administrator-password")
        users = json.loads(opener.open(_url(server, "/api/v1/admin/users"), timeout=2).read())
        assert {row["username"] for row in users["users"]} == {"admin", "viewer"}

        create = urllib.request.Request(
            _url(server, "/api/v1/admin/tokens"),
            data=json.dumps(
                {
                    "name": "diagnostic-client",
                    "permissions": ["diagnostics:read"],
                    "lifetime_seconds": 3600,
                }
            ).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": _csrf(jar)},
        )
        token = json.loads(opener.open(create, timeout=2).read())
        assert token["token"].startswith("samuel_")
        assert token["permissions"] == ["diagnostics:read"]

        token_list = json.loads(opener.open(_url(server, "/api/v1/admin/tokens"), timeout=2).read())
        assert token_list["tokens"][0]["token_id"] == token["token_id"]
        assert token["token"] not in json.dumps(token_list)
        assert "token_hash" not in json.dumps(token_list)

        automation = urllib.request.Request(
            _url(server, "/api/v1/dashboard/health"),
            headers={"Authorization": f"Bearer {token['token']}"},
        )
        assert urllib.request.urlopen(automation, timeout=2).status == 200
        forbidden = urllib.request.Request(
            _url(server, "/api/v1/admin/users"),
            headers={"Authorization": f"Bearer {token['token']}"},
        )
        with pytest.raises(urllib.error.HTTPError) as permission_error:
            urllib.request.urlopen(forbidden, timeout=2)
        assert permission_error.value.code == 403

        revoke = urllib.request.Request(
            _url(server, f"/api/v1/admin/tokens/{token['token_id']}"),
            data=b"{}",
            method="DELETE",
            headers={"X-CSRF-Token": _csrf(jar)},
        )
        assert json.loads(opener.open(revoke, timeout=2).read())["revoked"] is True
        with pytest.raises(urllib.error.HTTPError) as revoked_error:
            urllib.request.urlopen(automation, timeout=2)
        assert revoked_error.value.code == 401

        session_list = json.loads(
            opener.open(_url(server, "/api/v1/admin/sessions"), timeout=2).read()
        )
        serialized = json.dumps(session_list)
        assert "session_hash" not in serialized
        assert "csrf" not in serialized
        assert "administrator-password" not in serialized


@pytest.mark.parametrize("bootstrap_identity", [False, True])
def test_legacy_configuration_with_identity_store_uses_key_and_keeps_session_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bootstrap_identity: bool
) -> None:
    from samuel.core.configuration_session import ConfigurationSession
    from samuel.llm_configuration import LLMRuntime

    monkeypatch.setenv("SAMUEL_API_KEY", "legacy-configuration-test-key")
    bus, config = _runtime(
        tmp_path, access_mode="legacy_api_key", bootstrap_identity=bootstrap_identity
    )
    root = tmp_path / "config"
    (root / "llm").mkdir()
    (root / "llm.json").write_text(json.dumps({"default": {"provider": "manual", "fallbacks": []}}))
    defaults = root / "llm/defaults.json"
    defaults.write_text(
        json.dumps({"tasks": {"planning": {"provider": "manual", "model": "before"}}})
    )
    bus.configuration_session = ConfigurationSession(bus.state_store.authority)
    bus.authority_state_store = bus.state_store.authority
    bus.quality_registry = bus.state_store.quality_metrics
    bus.llm_runtime = LLMRuntime(None, config, bus)
    server = create_server(bus, host="127.0.0.1", port=0, config=config)

    def post(path: str, body: dict, *, key: str = "legacy-configuration-test-key"):
        request = urllib.request.Request(
            _url(server, path),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-API-Key": key},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    path = "/api/v1/settings/configuration"
    with _serve(server):
        assert post(path, {"action": "enter"}, key="wrong-key")[0] == 401
        code, data = post(path, {"action": "enter"})
        assert code == 200, data
        state = data["session"]
        assert state["owner"] == "legacy-api-key"
        assert post("/api/v1/settings/flag", {"name": "eval", "enabled": True})[0] == 409
        code, data = post(
            path,
            {
                "action": "stage",
                "version": state["version"],
                "task": "planning",
                "config": {"model": "after"},
            },
        )
        assert code == 200, data
        assert json.loads(defaults.read_text())["tasks"]["planning"]["model"] == "before"
        assert post(path, {"action": "apply", "version": state["version"]})[0] == 409
        state = data["session"]
        code, data = post(path, {"action": "apply", "version": state["version"]})
        assert code == 200 and data["session"]["phase"] == "idle", data
        assert json.loads(defaults.read_text())["tasks"]["planning"]["model"] == "after"
    bus.close()


@pytest.mark.parametrize("access_mode", ["legacy_api_key", "local_identity"])
def test_recovery_reauth_follows_active_access_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, access_mode: str
) -> None:
    monkeypatch.setenv("SAMUEL_API_KEY", "legacy-recovery-test-key")
    bus, config = _runtime(tmp_path, access_mode=access_mode)
    identity = LocalIdentityService(
        bus.state_store.identity, instance_uuid=lambda: bus.state_store.status().authority_instance
    )
    admin = identity.login("admin", "administrator-password", client_key="fixture")
    identity.create_user(admin.actor, "operator", "operator-password-long", ("operator",))
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    downstream = MagicMock(return_value={"updated": False, "code": "fixture_downstream_guard"})
    monkeypatch.setattr(
        cast(Any, server.RequestHandlerClass).dashboard, "recovery_action", downstream
    )
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def post(*, csrf: bool = True):
        headers = {"Content-Type": "application/json", "X-API-Key": "legacy-recovery-test-key"}
        if access_mode == "local_identity" and csrf:
            headers["X-CSRF-Token"] = _csrf(jar)
        request = urllib.request.Request(
            _url(server, "/api/v1/issues/42/recovery"),
            data=json.dumps({"action": "abandon", "reason": "test"}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    with _serve(server):
        if access_mode == "local_identity":
            _login(opener, server, "viewer", "viewer-password-long")
            assert post()[0] == 403
            _login(opener, server, "operator", "operator-password-long")
            assert post(csrf=False)[0] == 403
            with monkeypatch.context() as patch:
                patch.setattr(LocalIdentityService, "is_fresh", lambda self, actor: False)
                code, payload = post()
                assert code == 403 and payload["code"] == "fresh_reauthentication_required"
            downstream.assert_not_called()
        code, payload = post()
        assert code == 409 and payload["code"] == "fixture_downstream_guard", payload
        downstream.assert_called_once()
        assert downstream.call_args.args[0] == 42
        if access_mode == "legacy_api_key":
            assert downstream.call_args.args[2] == "legacy-api-key"
    bus.close()


@pytest.mark.parametrize("maintenance", [False, True])
def test_configuration_mode_http_uses_identity_csrf_and_preserves_other_write_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    maintenance: bool,
) -> None:
    from samuel.core.configuration_session import ConfigurationSession
    from samuel.llm_configuration import LLMRuntime

    bus, config = _runtime(tmp_path)
    root = tmp_path / "config"
    (root / "llm").mkdir()
    (root / "llm.json").write_text(json.dumps({"default": {"provider": "manual", "fallbacks": []}}))
    (root / "llm/defaults.json").write_text(
        json.dumps({"tasks": {"planning": {"provider": "manual", "model": "manual-id"}}})
    )
    bus.configuration_session = ConfigurationSession(bus.state_store.authority)
    bus.authority_state_store = bus.state_store.authority
    bus.quality_registry = bus.state_store.quality_metrics
    bus.llm_runtime = LLMRuntime(None, config, bus)
    if maintenance:
        with bus.configuration_session.host_transition(
            "setup", "operator", "explicit setup", "a" * 64
        ) as complete:
            complete()
    expected_phase = "maintenance" if maintenance else "idle"
    server = create_server(
        bus,
        host="127.0.0.1",
        port=0,
        config=config,
        configuration_mode="setup" if maintenance else "production",
    )
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def post(path: str, body: dict, *, csrf: bool = True) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = _csrf(jar)
        request = urllib.request.Request(
            _url(server, path), data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    path = "/api/v1/settings/configuration"
    with _serve(server):
        _login(opener, server, "viewer", "viewer-password-long")
        assert post(path, {"action": "enter"})[0] == 403
        _login(opener, server, "admin", "administrator-password")
        assert post(path, {"action": "enter"}, csrf=False)[0] == 403
        with monkeypatch.context() as patch:
            patch.setattr(LocalIdentityService, "is_fresh", lambda self, actor: False)
            code, data = post(path, {"action": "enter"})
            assert code == 403 and data["code"] == "fresh_reauthentication_required"
        code, data = post(path, {"action": "enter"})
        assert code == 200, data
        state = data["session"]
        assert state["phase"] == "editing"
        assert post("/api/v1/settings/flag", {"name": "eval", "enabled": True})[0] == 409
        assert post("/api/v1/dashboard/llm/prompts/planner.md", {"content": "no"})[0] == 409
        # Probe permission is separate from administrator configuration permission.
        assert post(path + "/probe", {"task": "planning", "version": state["version"]})[0] == 403
        code, data = post(
            path,
            {
                "action": "stage",
                "version": state["version"],
                "task": "planning",
                "config": {"model": "new-free-id"},
            },
        )
        assert code == 200, data
        assert post(path, {"action": "apply", "version": state["version"]})[0] == 409
        state = data["session"]
        code, data = post(path, {"action": "apply", "version": state["version"]})
        assert code == 200, data
        assert data["session"]["phase"] == expected_phase
        assert (
            json.loads((root / "llm/defaults.json").read_text())["tasks"]["planning"]["model"]
            == "new-free-id"
        )
        code, data = post(path, {"action": "enter"})
        assert code == 200
        code, data = post(path, {"action": "cancel", "version": data["session"]["version"]})
        assert code == 200 and data["session"]["phase"] == expected_phase
        if maintenance:
            from samuel.core.configuration_session import ConfigurationConflict

            assert post("/api/v1/settings/flag", {"name": "eval", "enabled": True})[0] == 200
            assert json.loads((root / "features.json").read_text())["eval"] is True
            assert bus.configuration_session.state()["phase"] == "maintenance"

            with pytest.raises(ConfigurationConflict), bus.configuration_session.admission():
                pytest.fail("Dashboard released host maintenance")
            html = opener.open(_url(server, "/"), timeout=5).read().decode()
            assert "das Dashboard kann die Sperre nicht aufheben" in html
            with bus.configuration_session.host_transition(
                "stopped", "operator", "register source", "a" * 64
            ) as complete:
                complete()
            assert post("/api/v1/settings/flag", {"name": "eval", "enabled": False})[0] == 409
            assert json.loads((root / "features.json").read_text())["eval"] is True
            assert bus.configuration_session.state()["maintenance"]["step"] == "stopped"
            assert "Runtime bleibt gestoppt" in html


@pytest.mark.parametrize(
    "role,allowed",
    [("viewer", False), ("administrator", False), ("auditor", True), ("operator", True)],
)
def test_system_diagnostics_requires_diagnostic_permission_not_admin_role(tmp_path, role, allowed):
    bus, config = _runtime(tmp_path)
    identity = LocalIdentityService(
        bus.state_store.identity, instance_uuid=lambda: bus.state_store.status().authority_instance
    )
    admin = identity.login("admin", "administrator-password", client_key="fixture")
    identity.create_user(admin.actor, "diagnostic-user", "diagnostic-password-long", (role,))
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    with _serve(server):
        _login(opener, server, "diagnostic-user", "diagnostic-password-long")
        target = _url(server, "/api/v1/dashboard/diagnostics")
        if allowed:
            with opener.open(target, timeout=3) as response:
                assert json.load(response)["informational_only"] is True
        else:
            with pytest.raises(urllib.error.HTTPError) as error:
                opener.open(target, timeout=3)
            assert error.value.code == 403
    bus.close()


@pytest.mark.parametrize("kind", ["user", "token"])
@pytest.mark.parametrize("duplicate_name", ["diagnostic-client", "DIAGNOSTIC-CLIENT"])
def test_duplicate_identity_name_returns_bound_error_without_state_change(
    tmp_path, kind, duplicate_name
):
    bus, config = _runtime(tmp_path)
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    path = "/api/v1/admin/users" if kind == "user" else "/api/v1/admin/tokens"
    key = "username" if kind == "user" else "name"
    body = (
        {"password": "diagnostic-user-password", "roles": ["viewer"]}
        if kind == "user"
        else {"permissions": ["diagnostics:read"], "lifetime_seconds": 3600}
    )
    with _serve(server):
        _login(opener, server, "admin", "administrator-password")

        def create(name):
            request = urllib.request.Request(
                _url(server, path),
                data=json.dumps({key: name, **body}).encode(),
                method="POST",
                headers={"Content-Type": "application/json", "X-CSRF-Token": _csrf(jar)},
            )
            return opener.open(request, timeout=5)

        with create("diagnostic-client") as response:
            assert response.status == 201
        identity = bus.state_store.identity
        principals = identity.list_principals()
        tokens = identity.list_automation_tokens()
        authority = bus.state_store.authority.authority_status()
        with pytest.raises(urllib.error.HTTPError) as conflict:
            create(duplicate_name)
        assert conflict.value.code == (409 if kind == "user" else 400)
        assert json.load(conflict.value)["code"] == (
            "identity_username_conflict" if kind == "user" else "identity_automation_conflict"
        )
        assert identity.list_principals() == principals
        assert identity.list_automation_tokens() == tokens
        assert bus.state_store.authority.authority_status() == authority
        with opener.open(_url(server, "/api/v1/admin/users"), timeout=5) as response:
            assert response.status == 200
