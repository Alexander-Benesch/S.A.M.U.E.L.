from __future__ import annotations

import json
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


def _runtime(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    auth = json.loads((Path(__file__).parents[1] / "config" / "auth.json").read_text())
    auth["access_mode"] = "local_identity"
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
    return cast(dict[str, Any], json.loads(opener.open(request, timeout=2).read()))


def _csrf(jar: CookieJar) -> str:
    return cast(str, next(cookie.value for cookie in jar if cookie.name == "samuel_csrf"))


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


def test_configuration_mode_http_uses_identity_csrf_and_preserves_other_write_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
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
        assert data["session"]["phase"] == "idle"
        assert (
            json.loads((root / "llm/defaults.json").read_text())["tasks"]["planning"]["model"]
            == "new-free-id"
        )
        code, data = post(path, {"action": "enter"})
        assert code == 200
        code, data = post(path, {"action": "cancel", "version": data["session"]["version"]})
        assert code == 200 and data["session"]["phase"] == "idle"


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
