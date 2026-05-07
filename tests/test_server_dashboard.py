"""Integration tests for the Phase 14.6 dashboard server wiring.

Covers:
- HTML + /api/* routes require API key when SAMUEL_API_KEY is set
- No auth in dev-mode (SAMUEL_API_KEY not set)
- /api/v1/dashboard/self_check returns checks list
- /api/v1/setup/labels reachable via RestAPI (delegates to SetupHandler)
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import HTTPServer

import pytest

from samuel.core.bus import Bus
from samuel.server import create_server


@contextmanager
def _serve(srv: HTTPServer):
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _url(srv: HTTPServer, path: str) -> str:
    host, port = srv.server_address
    # host may be bytes/0.0.0.0 — normalise
    host_str = "127.0.0.1" if str(host) in ("0.0.0.0", "", "b''") else str(host)
    return f"http://{host_str}:{port}{path}"


class TestServerAuthEnabled:
    def test_dashboard_html_requires_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "secret-xyz")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            # Without key: 401
            req = urllib.request.Request(_url(srv, "/"))
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            assert exc_info.value.code == 401

            # With key (X-API-Key, urllib normalises casing — must still work): 200 HTML
            req2 = urllib.request.Request(_url(srv, "/"), headers={"X-API-Key": "secret-xyz"})
            resp = urllib.request.urlopen(req2, timeout=2)
            assert resp.status == 200
            assert b"S.A.M.U.E.L." in resp.read()

    def test_api_dashboard_endpoints_require_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SAMUEL_API_KEY", "abc-123")
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            req = urllib.request.Request(_url(srv, "/api/v1/dashboard/status"))
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=2)
            assert exc_info.value.code == 401

            req2 = urllib.request.Request(
                _url(srv, "/api/v1/dashboard/status"),
                headers={"Authorization": "Bearer abc-123"},
            )
            resp = urllib.request.urlopen(req2, timeout=2)
            assert resp.status == 200


class TestServerDevMode:
    def test_no_auth_required_when_key_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            resp = urllib.request.urlopen(_url(srv, "/"), timeout=2)
            assert resp.status == 200
            resp2 = urllib.request.urlopen(_url(srv, "/api/v1/dashboard/status"), timeout=2)
            assert resp2.status == 200


class TestSelfCheckRoute:
    def test_self_check_endpoint_returns_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        bus = Bus()
        bus.register_command(
            "HealthCheck",
            lambda cmd: {"healthy": True, "checks": {"python": {"passed": True, "version": "3.12"}}},
        )
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            import json as _json
            resp = urllib.request.urlopen(_url(srv, "/api/v1/dashboard/self_check"), timeout=2)
            body = _json.loads(resp.read())
            assert body["healthy"] is True
            assert any(c["name"] == "python" for c in body["checks"])


class TestSettingsFlagRoute:
    def test_settings_flag_updates_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
        from samuel.core.config import FileConfig

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        cfg = FileConfig(tmp_path)
        srv = create_server(bus, host="127.0.0.1", port=0, config=cfg)
        with _serve(srv):
            import json as _json
            data = _json.dumps({"name": "eval", "enabled": False}).encode()
            req = urllib.request.Request(
                _url(srv, "/api/v1/settings/flag"),
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            body = _json.loads(resp.read())
            assert body.get("updated") is True
            assert cfg.feature_flag("eval") is False


class TestLLMModelsRoute:
    """#328: /api/v1/dashboard/llm/models must use base_url query param so the
    LLM-Editor can show models for a remote LMStudio/Ollama instance."""

    def _make_config(self):
        from unittest.mock import MagicMock
        cfg = MagicMock()
        cfg.get.side_effect = lambda k, d=None: d
        return cfg

    def test_llm_models_endpoint_uses_query_base_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path,
    ) -> None:
        """#328-AC: name matches issue-body anchor."""
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        captured: dict = {}

        class _FakeAdapter:
            def list_models(self):
                return [{"id": "remote-model-1", "model": "remote-model-1"}]

        def _fake_build_inner(provider, config, secrets, **kwargs):
            captured["provider"] = provider
            captured["base_url_override"] = kwargs.get("base_url_override")
            return _FakeAdapter()

        # server.py uses `from samuel.adapters.llm.factory import _build_inner`
        # lazily inside the GET handler — patching the module-level symbol
        # works because the import happens at request time.
        import samuel.adapters.llm.factory as _factory
        monkeypatch.setattr(_factory, "_build_inner", _fake_build_inner)

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0, config=self._make_config())
        with _serve(srv):
            from urllib.parse import quote
            url = _url(
                srv,
                "/api/v1/dashboard/llm/models?provider=lmstudio&base_url="
                + quote("http://192.168.1.158:1234"),
            )
            resp = urllib.request.urlopen(url, timeout=2)
            import json as _json
            body = _json.loads(resp.read())
            assert body["provider"] == "lmstudio"
            assert body["models"] == [{"id": "remote-model-1", "model": "remote-model-1"}]
            # Backend must have forwarded the base_url to _build_inner
            assert captured["base_url_override"] == "http://192.168.1.158:1234"

    def test_llm_models_endpoint_without_base_url_uses_config_default(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If base_url query is omitted, the override is None — adapter falls back to config."""
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        captured: dict = {}

        class _FakeAdapter:
            def list_models(self):
                return []

        def _fake_build_inner(provider, config, secrets, **kwargs):
            captured["base_url_override"] = kwargs.get("base_url_override")
            return _FakeAdapter()

        import samuel.adapters.llm.factory as _factory
        monkeypatch.setattr(_factory, "_build_inner", _fake_build_inner)

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0, config=self._make_config())
        with _serve(srv):
            url = _url(srv, "/api/v1/dashboard/llm/models?provider=ollama")
            resp = urllib.request.urlopen(url, timeout=2)
            assert resp.status == 200
            assert captured["base_url_override"] is None


class TestSetupLabelsRoute:
    def test_setup_labels_route_reachable(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)

        class _FakeSCM:
            def list_labels(self):
                return []

            def create_label(self, name, color, description=""):
                return {"id": 1, "name": name, "color": color, "description": description}

        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})

        # Stage labels.json inside tmp_path/config, and chdir into tmp_path so
        # SetupHandler (project_root=.) picks it up.
        (tmp_path / "config").mkdir()
        import json as _json
        (tmp_path / "config" / "labels.json").write_text(
            _json.dumps({"labels": [{"name": "ready-for-agent", "color": "0e8a16"}]})
        )
        monkeypatch.chdir(tmp_path)

        srv = create_server(bus, host="127.0.0.1", port=0, scm=_FakeSCM())
        with _serve(srv):
            req = urllib.request.Request(
                _url(srv, "/api/v1/setup/labels"),
                data=b"",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            body = _json.loads(resp.read())
            assert body.get("synced") is True
            assert "ready-for-agent" in body.get("created", [])


# #359: Click-Expand fuer OWASP/AI-Act-Codes im Audit-Trail + Schranken-Protokoll
class TestClickExpandMarkers:
    def test_audit_trail_has_click_expand_markers(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTML enthaelt die Klassen + data-attributes fuer das
        Click-Expand-Pattern im Workflow-Issue-Detail Audit-Trail."""
        import samuel.server as _srv
        html = _srv.DASHBOARD_HTML
        # Audit-Trail-Renderer
        assert "trail-info-cell" in html
        assert "trail-info-row" in html
        assert "data-trail-idx" in html
        assert "data-trail-info-for" in html
        # ⓘ-Symbol als visueller Hint (HTML-Entity)
        assert "&#9432;" in html

    def test_security_barrier_has_click_expand_markers(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTML enthaelt die Klassen + data-attributes fuer das
        Click-Expand-Pattern im Security-Tab Schranken-Protokoll."""
        import samuel.server as _srv
        html = _srv.DASHBOARD_HTML
        assert "barrier-info-cell" in html
        assert "barrier-info-row" in html
        assert "data-barrier-idx" in html
        assert "data-barrier-info-for" in html

    def test_compliance_legend_helpers_defined(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """JS-Helpers fuer den lazy Legend-Lookup sind im HTML."""
        import samuel.server as _srv
        html = _srv.DASHBOARD_HTML
        assert "ensureLegend" in html
        assert "owaspDesc" in html
        assert "aiActDesc" in html
        assert "complianceCache" in html

    def test_compliance_legend_endpoint_serves_owasp_and_ai_act(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End-to-end: Endpoint liefert die Daten die das JS erwartet —
        mind. ein OWASP- und ein AI-Act-Eintrag mit Beschreibung."""
        import json as _json
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        srv = create_server(bus, host="127.0.0.1", port=0)
        with _serve(srv):
            resp = urllib.request.urlopen(
                _url(srv, "/api/v1/dashboard/compliance/legend"), timeout=2,
            )
            body = _json.loads(resp.read())
        # Legende kommt direkt aus core.owasp / core.ai_act — Spotcheck.
        owasp = body.get("owasp") or []
        ai_act = body.get("ai_act") or []
        assert owasp, "owasp legend must not be empty"
        assert ai_act, "ai_act legend must not be empty"
        # Mindestens ein OWASP-Eintrag mit Description
        assert any(r.get("description") for r in owasp), "owasp entries need descriptions"
        assert any(r.get("description") or r.get("title") for r in ai_act), \
            "ai_act entries need descriptions"
