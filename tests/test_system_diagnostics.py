"""#921 composes observations; it neither probes nor grants workflow authority."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from samuel.adapters.api.auth import permission_for_request
from samuel.adapters.gitea.api import GiteaAPI
from samuel.adapters.github.api import GitHubAPI
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.bus import Bus
from samuel.core.health_projection import record_projection, snapshot
from samuel.core.identity import READ_DIAGNOSTICS, ROLE_PERMISSIONS, RUN_PROVIDER_PROBES
from samuel.server import create_server
from samuel.slices.dashboard.data import get_system_diagnostics

CONFIG = {"digest_status": "available", "restart_required": False}
HEALTH_KEYS = ("python", "git", "config", "state", "authority", "scm", "llm", "execution_provider")


def row(report, code):
    return next(item for item in report["checks"] if item["code"] == code)


def seed(state, *, failed=None, at=None):
    instance = state.status().authority_instance
    for kind in ("technical_health", "operational_readiness", "doctor", "audit_integrity"):
        record_projection(
            state.projections,
            kind=kind,
            status="ready" if kind == "operational_readiness" else "passed",
            instance_uuid=instance,
            summary={"checks": {name: name != failed for name in HEALTH_KEYS}},
            observed_at=at,
        )
    return instance


@pytest.mark.parametrize("failed", [None, "state", "authority", "scm", "llm", "execution_provider"])
def test_existing_health_facts_keep_their_scope_and_never_become_a_global_pass(tmp_path, failed):
    state = SQLiteStateStore(tmp_path)
    instance = seed(state, failed=failed)
    report = get_system_diagnostics(snapshot(state.projections, instance_uuid=instance), CONFIG)
    assert report["informational_only"] is True and report["passive"] is True
    assert "status" not in report and "ready" not in report
    for name in HEALTH_KEYS:
        check = row(report, name)
        assert check["status"] == ("failed" if name == failed else "passed")
        assert check["checked_at"] and check["evidence_digest"].startswith("sha256:")
        assert check["freshness"] == "current" and check["fix"]
    assert "keine Aussage über Schreibrechte" in row(report, "scm")["expected"]
    assert "Kein TEST-Runner-Nachweis" in row(report, "execution_provider")["expected"]
    assert row(report, "readiness")["status"] == "passed"
    assert row(report, "project")["status"] == "unknown"


@pytest.mark.parametrize("age,foreign", [(3601, False), (-5, False), (0, True)])
def test_stale_or_restored_projection_never_passes_and_does_not_erase_past_failure(
    tmp_path, age, foreign
):
    state = SQLiteStateStore(tmp_path)
    instance = seed(state, failed="state", at=datetime.now(timezone.utc) - timedelta(seconds=age))
    projected = snapshot(state.projections, instance_uuid="restored" if foreign else instance)
    report = get_system_diagnostics(projected, CONFIG)
    for name in (*HEALTH_KEYS, "readiness", "doctor", "audit_integrity"):
        assert row(report, name)["status"] == "unknown"
        assert row(report, name)["freshness"] == "stale"
    assert row(report, "state")["previous_failure"] is True
    assert row(report, "scm")["previous_failure"] is False


def test_missing_projections_and_unrecognised_values_do_not_pass_or_leak_details():
    report = get_system_diagnostics({}, {})
    assert all(check["status"] == "unknown" for check in report["checks"])
    poisoned = {
        "technical_health": {
            "current": True,
            "status": "passed",
            "checked_at": "fixture-sensitive-value",
            "evidence_digest": "fixture-sensitive-value",
            "summary": {
                "checks": {"scm": "fixture-sensitive-value"},
                "token": "fixture-sensitive-value",
            },
        },
        "operational_readiness": {"project": {"passed": False, "path": "fixture-sensitive-value"}},
    }
    report = get_system_diagnostics(
        poisoned, {**CONFIG, "stored_config_digest": "fixture-sensitive-value"}
    )
    assert "fixture-sensitive-value" not in json.dumps(report)
    assert row(report, "scm")["status"] == "unknown"
    assert row(report, "project")["status"] == "failed"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("written", "passed"),
        ("degraded", "degraded"),
        ("loss_detected", "failed"),
        ("unknown", "unknown"),
    ],
)
def test_audit_writer_and_integrity_are_independent(tmp_path, status, expected):
    state = SQLiteStateStore(tmp_path)
    instance = seed(state)
    record_projection(
        state.projections,
        kind="audit_integrity",
        status="failed",
        instance_uuid=instance,
        summary={"failed_files": 1},
    )
    projected = snapshot(state.projections, instance_uuid=instance)
    projected["audit_writer"] = {"status": status, "writers": []}
    report = get_system_diagnostics(projected, CONFIG)
    assert row(report, "audit_writer")["status"] == expected
    assert row(report, "audit_integrity")["status"] == "failed"
    assert row(report, "doctor")["status"] == "passed"


@pytest.mark.parametrize(
    "digest,restart,expected",
    [
        ("available", False, "passed"),
        ("available", True, "degraded"),
        ("unavailable", True, "unknown"),
    ],
)
def test_config_drift_is_visible_without_reinterpreting_old_projections(digest, restart, expected):
    report = get_system_diagnostics({}, {"digest_status": digest, "restart_required": restart})
    assert row(report, "configuration_consistency")["status"] == expected
    assert row(report, "state")["status"] == "unknown"
    assert "nicht an jede spätere Konfigurationsänderung" in report["coverage"]


def test_permission_contract_keeps_active_actions_separate():
    assert permission_for_request("GET", "/api/v1/dashboard/diagnostics") == READ_DIAGNOSTICS
    assert permission_for_request("POST", "/api/v1/dashboard/diagnostics") is None
    assert permission_for_request("GET", "/api/v1/dashboard/self_check") == RUN_PROVIDER_PROBES
    assert permission_for_request("POST", "/api/v1/dashboard/webhook/read") == RUN_PROVIDER_PROBES
    assert READ_DIAGNOSTICS in ROLE_PERMISSIONS["auditor"]
    assert RUN_PROVIDER_PROBES not in ROLE_PERMISSIONS["auditor"]
    assert READ_DIAGNOSTICS not in ROLE_PERMISSIONS["viewer"]


@pytest.mark.parametrize("provider", ["gitea", "github"])
def test_real_http_overview_is_passive_redacted_and_does_not_renew_evidence(
    tmp_path, monkeypatch, provider
):
    (tmp_path / "auth.json").write_bytes(Path("config/auth.json").read_bytes())
    for key, value in {
        "SCM_PROVIDER": provider,
        "SCM_URL": "https://scm.invalid",
        "SCM_REPO": "o/r",
        "SCM_TOKEN": "fixture-sensitive-token",
        "SLICE_HMAC_KEY": "fixture-sensitive-key",
        "SAMUEL_API_KEY": "dashboard-fixture",
    }.items():
        monkeypatch.setenv(key, value)
    state = SQLiteStateStore(tmp_path / "state")
    seed(state, failed="scm")
    bus = Bus()
    bus.state_store = state
    bus.run_projection_store = state.projections
    send = Mock(side_effect=AssertionError("No workflow or Health command"))
    monkeypatch.setattr(bus, "send", send)
    network = Mock(side_effect=AssertionError("No SCM request"))
    monkeypatch.setattr(GiteaAPI, "request", network)
    monkeypatch.setattr(GitHubAPI, "request", network)
    server = create_server(
        bus, host="127.0.0.1", port=0, config={"agent.config_dir": str(tmp_path)}
    )
    probe = Mock(side_effect=AssertionError("No LLM probe"))
    monkeypatch.setattr(server.RequestHandlerClass.dashboard, "_connection_tester", probe)
    projections_before = state.projections.list_projections()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        url = base + "/api/v1/dashboard/diagnostics"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=3)
        assert exc.value.code == 401
        reports = []
        for _ in range(2):
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"X-API-Key": "dashboard-fixture"}), timeout=3
            ) as response:
                reports.append(json.load(response))
        assert reports[0] == reports[1]
        report = reports[0]
        assert report["schema"] == "samuel-system-diagnostics.v1"
        assert row(report, "scm")["status"] == "failed"
        assert row(report["webhook"], "native_delivery")["state"] == "not_proven"
        assert row(report["webhook"], "signing_key")["state"] == "configured"
        assert "fixture-sensitive" not in json.dumps(report)
        with urllib.request.urlopen(base, timeout=3) as response:
            assert 'id="set-diagnostics"' in response.read().decode()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        bus.close()
    assert state.projections.list_projections() == projections_before
    send.assert_not_called()
    network.assert_not_called()
    probe.assert_not_called()


def test_multiple_writers_do_not_hide_a_previous_loss_or_invent_common_timestamp():
    report = get_system_diagnostics(
        {
            "audit_writer": {
                "status": "unknown",
                "writers": [
                    {"status": "stale", "current": False, "result": "loss_detected"},
                    {"status": "written", "current": True, "result": "written"},
                ],
            }
        },
        CONFIG,
    )
    writer = row(report, "audit_writer")
    assert writer["status"] == "unknown" and writer["previous_failure"] is True
    assert writer["checked_at"] is None and writer["evidence_digest"] is None
