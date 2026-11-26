from __future__ import annotations

import argparse
import io
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.adapter import GiteaAdapter
from samuel.adapters.github.adapter import GitHubAdapter
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.cli import _cmd_health
from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.config import FileConfig
from samuel.core.events import Event
from samuel.core.types import Issue
from samuel.server import create_server
from samuel.slices.health.handler import HealthHandler


@pytest.mark.parametrize("provider", ["gitea", "github"])
@pytest.mark.parametrize("configured", [False, True])
def test_remote_scm_error_body_stays_out_of_health_consumers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    provider: str,
    configured: bool,
) -> None:
    canary = "fixture-sensitive-scm-token"
    auth = StaticTokenAuth(canary)
    scm = (
        GiteaAdapter("https://scm.invalid", "owner/repo", auth)
        if provider == "gitea"
        else GitHubAdapter("owner/repo", auth, base_url="https://scm.invalid")
    )
    original = urllib.request.urlopen
    observed: list[str] = []

    def deny(request: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(request, urllib.request.Request) and request.full_url.startswith(
            "https://scm.invalid/"
        ):
            authorization = request.get_header("Authorization")
            assert authorization and canary in authorization
            observed.append(request.get_method())
            body = json.dumps({"message": "reflected " + authorization}).encode()
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(body))
        return original(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", deny)
    state = SQLiteStateStore(tmp_path / "state")
    config = FileConfig(tmp_path / "config") if configured else None
    bus = Bus()
    events: list[Event] = []
    bus.subscribe("*", lambda event: events.append(event))
    handler = HealthHandler(
        bus, scm=scm, config=config, state=state, projection_store=state.projections
    )
    bus.register_command("HealthCheck", handler.handle)

    result = handler.handle(HealthCheckCommand())
    assert result["healthy"] is False
    assert result["critical"] is configured
    assert result["checks"]["scm"]["passed"] is False
    assert result["checks"]["scm"]["reachable"] is False
    assert canary not in json.dumps(result)
    assert (
        type(scm).__name__.removesuffix("Adapter") + "APIError" in result["checks"]["scm"]["error"]
    )
    assert "HTTP 403" in result["checks"]["scm"]["error"]
    assert "Admin" not in result["checks"]["scm"]["error"]

    server = create_server(bus, host="127.0.0.1", port=0, authentication=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/api/v1/dashboard/self_check", timeout=3
        ) as response:
            assert response.status == 200
            payload = json.load(response)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert canary not in json.dumps(payload)
    assert _cmd_health(bus, argparse.Namespace()) == 1
    assert canary not in capsys.readouterr().out
    assert canary not in caplog.text
    assert canary not in json.dumps([event.payload for event in events])
    assert any(event.name == "StartupBlocked" for event in events) is (not configured)
    assert canary not in json.dumps([row.payload for row in state.projections.list_projections()])
    assert observed == ["GET", "GET", "GET"]


@pytest.mark.parametrize("status", [None, True, 99, 600, "fixture-sensitive-status"])
def test_untrusted_scm_status_is_not_rendered_as_http_or_private_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: object,
) -> None:
    class RemoteFailure(Exception):
        status: object

    failure = RemoteFailure("fixture-sensitive-body")
    failure.status = status
    scm = GiteaAdapter("https://scm.invalid", "owner/repo", StaticTokenAuth("fixture-only"))

    def fail(labels: list[str]) -> list[Issue]:
        raise failure

    monkeypatch.setattr(scm, "list_issues", fail)
    result = HealthHandler(Bus(), scm=scm, config=FileConfig(tmp_path)).handle(HealthCheckCommand())
    assert "fixture-sensitive" not in json.dumps(result)
    assert "RemoteFailure" in result["checks"]["scm"]["error"]
    assert "HTTP" not in result["checks"]["scm"]["error"]
    assert "fixture-sensitive" not in caplog.text
