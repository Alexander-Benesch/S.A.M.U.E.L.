from __future__ import annotations

import errno
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from samuel.adapters.audit.async_sink import AsyncAuditSink
from samuel.adapters.audit.fanout import FanOutAuditSink
from samuel.adapters.audit.jsonl import JSONLAuditSink, verify_chain
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.cli import _cmd_health
from samuel.core.bus import Bus
from samuel.core.health_projection import record_audit_writer, record_projection, snapshot
from samuel.core.logging import attach_audit_diagnostics, detach_audit_diagnostics
from samuel.core.ports import IAuditSink
from samuel.slices.dashboard.handler import DashboardHandler


class FaultSink(IAuditSink):
    def __init__(self, error=None):
        self.error = error
        self.written: list = []

    def write(self, event):
        if self.error:
            raise self.error
        self.written.append(event)

    def query(self, query):
        return self.written


def diagnostics(state, process="process-a"):
    instance = state.status().authority_instance

    def report(write, primary="", fallback=""):
        return record_audit_writer(
            state.projections,
            instance_uuid=instance,
            writer_id="sha256:destination",
            process_uuid=process,
            state=write,
            primary_error=primary,
            fallback_error=fallback,
        )

    return report


def view(state):
    return snapshot(state.projections, instance_uuid=state.status().authority_instance)[
        "audit_writer"
    ]


@pytest.mark.parametrize(
    "error,code",
    [
        (PermissionError(errno.EACCES, "private/path"), "permission_denied"),
        (OSError(errno.ENOSPC, "private token"), "no_space"),
        (OSError(errno.EIO, "raw secret"), "io_error"),
        (RuntimeError("sensitive provider payload"), "write_error"),
    ],
)
@pytest.mark.parametrize("fallback_fails", [False, True])
def test_primary_fault_and_fallback_are_distinct_and_secret_free(
    tmp_path, error, code, fallback_fails
):
    state = SQLiteStateStore(tmp_path)
    fallback = FaultSink(RuntimeError("private fallback secret") if fallback_fails else None)
    sink = AsyncAuditSink(FaultSink(error), fallback, diagnostic=diagnostics(state))
    sink.write({"secret": "event payload is not a diagnostic"})
    sink.stop()
    result = view(SQLiteStateStore(tmp_path))
    facts = result["writers"][0]["summary"]
    assert result["status"] == ("loss_detected" if fallback_fails else "degraded")
    assert facts["lost_events"] == int(fallback_fails)
    assert facts["fallback_events"] == int(not fallback_fails)
    assert facts["last_failure"]["primary_error"] == code
    serialized = json.dumps(result)
    for raw in ("private", "sensitive", "raw secret", "event payload"):
        assert raw not in serialized
    assert result["integrity_verified"] is False
    assert result["completeness_proven"] is False


def test_wrong_key_preserves_primary_bytes_and_exposes_real_fallback(tmp_path):
    state = SQLiteStateStore(tmp_path / "state")
    path = tmp_path / "agent.jsonl"
    JSONLAuditSink(path, rotation="none", hmac_key="original-key").write({"evt": "baseline"})
    before = path.read_bytes()
    fallback = tmp_path / "agent.jsonl.fallback"
    sink = AsyncAuditSink(
        JSONLAuditSink(path, rotation="none", hmac_key="wrong-key"),
        JSONLAuditSink(fallback, rotation="none", hmac_key="wrong-key"),
        diagnostic=diagnostics(state),
    )
    sink.write({"evt": "negative"})
    sink.stop()
    result = view(state)
    assert path.read_bytes() == before
    assert verify_chain(path, "original-key")["ok"]
    assert verify_chain(fallback, "wrong-key")["ok"]
    assert result["status"] == "degraded"
    assert result["writers"][0]["summary"]["last_failure"]["primary_error"] == "append_refused"
    assert "wrong-key" not in json.dumps(result)


def test_restart_preserves_failure_and_success_resolves_only_writer_degradation(tmp_path):
    state = SQLiteStateStore(tmp_path)
    report = diagnostics(state)
    report("write_failed", "append_refused", "permission_denied")
    diagnostics(state, "restarted")("started")
    assert view(state)["status"] == "loss_detected"
    diagnostics(state, "restarted")("primary_written")
    facts = view(state)["writers"][0]["summary"]
    assert facts["last_write"] == "primary_written"
    assert facts["primary_degraded"] is False
    assert facts["lost_events"] == 1
    assert facts["resolved_finding"]
    assert view(state)["status"] == "loss_detected"
    assert (
        snapshot(state.projections, instance_uuid=state.status().authority_instance)[
            "qualification"
        ]["status"]
        == "not_checked"
    )


def test_restart_invalidates_success_and_restore_ttl_never_pass(tmp_path):
    state = SQLiteStateStore(tmp_path)
    report = diagnostics(state)
    report("primary_written")
    assert view(state)["status"] == "written"
    diagnostics(state, "restart")("started")
    assert view(state)["status"] == "unknown"
    failed = report("write_failed", "append_refused", "no_space")
    expired = snapshot(
        state.projections,
        instance_uuid=state.status().authority_instance,
        now=failed.updated_at + timedelta(hours=2),
    )["audit_writer"]
    restored = snapshot(state.projections, instance_uuid="restored-instance")["audit_writer"]
    assert expired["status"] == restored["status"] == "unknown"
    assert expired["writers"][0]["summary"]["lost_events"] == 1
    assert restored["writers"][0]["result"] == "loss_detected"


def test_concurrent_process_readbacks_do_not_lose_loss_counts(tmp_path):
    states = [SQLiteStateStore(tmp_path) for _ in range(4)]

    def fail(index):
        diagnostics(states[index % 4], str(index))("write_failed", "io_error", "no_space")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fail, range(24)))
    assert view(SQLiteStateStore(tmp_path))["writers"][0]["summary"]["lost_events"] == 24


def test_queue_overflow_and_stopped_writes_remain_visible_after_drain(tmp_path):
    started = threading.Event()
    release = threading.Event()

    class Blocking(FaultSink):
        def write(self, event):
            started.set()
            assert release.wait(5)
            super().write(event)

    state = SQLiteStateStore(tmp_path)
    sink = AsyncAuditSink(
        Blocking(), FaultSink(RuntimeError("secret")), buffer_size=1, diagnostic=diagnostics(state)
    )
    try:
        sink.write({"evt": "inflight"})
        assert started.wait(2)
        sink.write({"evt": "queued"})
        sink.write({"evt": "ordinary overflow"})
        sink.write({"lvl": "error", "evt": "security overflow"})
        assert view(state)["writers"][0]["summary"]["lost_events"] == 2
    finally:
        release.set()
        sink.stop()
    sink.write({"evt": "after stop"})
    assert view(state)["writers"][0]["summary"]["lost_events"] == 3


def test_fanout_success_cannot_mask_jsonl_failure_or_recurse(tmp_path):
    state = SQLiteStateStore(tmp_path)
    bus = Bus()
    diagnostics_seen: list = []
    bus.subscribe("DiagnosticRaised", diagnostics_seen.append)
    bridge = attach_audit_diagnostics(bus)
    jsonl = AsyncAuditSink(
        FaultSink(RuntimeError("secret")), FaultSink(), diagnostic=diagnostics(state)
    )
    sarif = FaultSink()
    try:
        fanout = FanOutAuditSink([jsonl, sarif])
        fanout.write({"evt": "finding", "owasp_risk": "test"})
        fanout.stop()
        assert len(sarif.written) == 1
        assert view(state)["status"] == "degraded"
        assert diagnostics_seen == []
    finally:
        jsonl.stop()
        detach_audit_diagnostics(bridge)


@pytest.mark.parametrize("healthy", [True, False])
def test_cli_and_passive_dashboard_share_fact_without_changing_exit(tmp_path, capsys, healthy):
    state = SQLiteStateStore(tmp_path)
    diagnostics(state)("fallback_written", "append_refused")
    instance = state.status().authority_instance
    record_projection(
        state.projections,
        kind="technical_health",
        status="passed" if healthy else "failed",
        instance_uuid=instance,
        summary={"checks": {"git": healthy}},
    )
    bus = Bus()
    bus.state_store = state
    dashboard = DashboardHandler(bus, run_projection_store=state.projections)
    fact = dashboard.get_health()
    bus.register_command("HealthCheck", lambda command: fact)
    before = state.projections.list_projections()
    assert _cmd_health(bus, None) == (0 if healthy else 1)
    assert "Audit writer: degraded" in capsys.readouterr().out
    assert dashboard.get_viewer_status()["audit_writer"] == "degraded"
    assert state.projections.list_projections() == before


def test_projection_failure_is_unknown_locally_without_recursive_audit(tmp_path):
    bus = Bus()
    bus.audit_writer_projection_available = lambda: False
    state = SQLiteStateStore(tmp_path)
    diagnostics(state)("primary_written")
    bus.state_store = state
    dashboard = DashboardHandler(bus, run_projection_store=state.projections)
    assert dashboard.get_health()["audit_writer"]["status"] == "unknown"
    assert dashboard.get_health()["audit_writer"]["projection_available"] is False
