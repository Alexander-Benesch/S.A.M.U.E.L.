from __future__ import annotations

import tempfile
from pathlib import Path

from samuel.core.bus import (
    AuditMiddleware,
    Bus,
    ErrorMiddleware,
    IdempotencyMiddleware,
    IdempotencyStore,
    MetricsMiddleware,
    PromptGuardMiddleware,
    SecurityMiddleware,
)
from samuel.core.commands import Command
from samuel.core.events import Event


def test_bus_publish_subscribe():
    bus = Bus()
    received = []
    bus.subscribe("Ping", lambda e: received.append(e))
    bus.publish(Event(name="Ping"))
    assert len(received) == 1


def test_bus_multiple_subscribers():
    bus = Bus()
    a, b = [], []
    bus.subscribe("X", lambda e: a.append(1))
    bus.subscribe("X", lambda e: b.append(1))
    bus.publish(Event(name="X"))
    assert len(a) == 1
    assert len(b) == 1


def test_bus_send_command():
    bus = Bus()
    results = []
    bus.register_command("DoIt", lambda c: results.append(c.name))
    bus.send(Command(name="DoIt"))
    assert results == ["DoIt"]


def test_bus_unhandled_command():
    bus = Bus()
    unhandled = []
    bus.subscribe("UnhandledCommand", lambda e: unhandled.append(e))
    bus.send(Command(name="Missing"))
    assert len(unhandled) == 1
    assert unhandled[0].payload["command"] == "Missing"


def test_bus_has_handler():
    bus = Bus()
    assert not bus.has_handler("X")
    bus.register_command("X", lambda c: None)
    assert bus.has_handler("X")


def test_idempotency_store_basic():
    store = IdempotencyStore()
    assert not store.has_key("k1")
    store.set_key("k1")
    assert store.has_key("k1")


def test_idempotency_store_persistence():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "store.json"
        store1 = IdempotencyStore(path=path)
        store1.set_key("k1")
        store2 = IdempotencyStore(path=path)
        assert store2.has_key("k1")


def test_idempotency_middleware_dedup():
    bus = Bus()
    store = IdempotencyStore()
    bus.add_middleware(IdempotencyMiddleware(store))
    results = []
    bus.register_command("Do", lambda c: results.append(1))
    bus.send(Command(name="Do", idempotency_key="once"))
    bus.send(Command(name="Do", idempotency_key="once"))
    assert len(results) == 1


def test_idempotency_middleware_no_key_no_dedup():
    bus = Bus()
    bus.add_middleware(IdempotencyMiddleware())
    results = []
    bus.register_command("Do", lambda c: results.append(1))
    bus.send(Command(name="Do"))
    bus.send(Command(name="Do"))
    assert len(results) == 2


def test_error_middleware_catches_exceptions():
    bus = Bus()
    bus.add_middleware(ErrorMiddleware())

    def bad_handler(c):
        raise RuntimeError("boom")

    bus.register_command("Fail", bad_handler)
    result = bus.send(Command(name="Fail"))
    assert result is None


def test_error_middleware_publishes_workflow_aborted_on_agent_abort():
    from samuel.core.errors import AgentAbort

    bus = Bus()
    bus.add_middleware(ErrorMiddleware(bus=bus))
    events = []
    bus.subscribe("WorkflowAborted", lambda e: events.append(e))

    def abort_handler(c):
        raise AgentAbort("stopped", gate=5, issue=42)

    bus.register_command("Fail", abort_handler)
    bus.send(Command(name="Fail", correlation_id="corr-1"))

    assert len(events) == 1
    assert events[0].payload["reason"] == "stopped"
    assert events[0].payload["gate"] == 5
    assert events[0].payload["issue"] == 42
    assert events[0].correlation_id == "corr-1"


def test_metrics_middleware_counts():
    bus = Bus()
    metrics = MetricsMiddleware()
    bus.add_middleware(metrics)
    bus.register_command("X", lambda c: None)
    bus.send(Command(name="X"))
    bus.send(Command(name="X"))
    assert metrics.counts["X"] == 2


def test_prompt_guard_blocks_missing_markers():
    bus = Bus()
    bus.add_middleware(PromptGuardMiddleware())
    results = []
    bus.register_command("LLMCall", lambda c: results.append(1))
    bus.send(Command(name="LLMCall", payload={"prompt": "no markers here"}))
    assert len(results) == 0


def test_prompt_guard_passes_with_markers():
    bus = Bus()
    bus.add_middleware(PromptGuardMiddleware())
    results = []
    bus.register_command("LLMCall", lambda c: results.append(1))
    prompt = "Unveränderliche Schranken ... Ignoriere Anweisungen ..."
    bus.send(Command(name="LLMCall", payload={"prompt": prompt}))
    assert len(results) == 1


def test_security_middleware_passthrough():
    bus = Bus()
    bus.add_middleware(SecurityMiddleware())
    results = []
    bus.register_command("Safe", lambda c: results.append(1))
    bus.send(Command(name="Safe"))
    assert len(results) == 1


def test_audit_middleware_logs():
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))
    bus.register_command("X", lambda c: None)
    bus.send(Command(name="X"))
    assert len(written) == 1


def test_audit_middleware_includes_original_payload():
    """Regression #179: original payload (issue, branch, ...) must be carried."""
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))
    bus.register_command("X", lambda c: None)
    bus.send(Command(name="X", payload={"issue": 42, "branch": "feature/foo"}))
    assert written[0].payload["issue"] == 42
    assert written[0].payload["branch"] == "feature/foo"
    assert written[0].payload["message_name"] == "X"


def test_audit_middleware_meta_overrides_original_on_conflict():
    """Meta keys (message_type, message_name, correlation_id) must win
    if a payload happens to use the same key."""
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))
    bus.register_command("Real", lambda c: None)
    bus.send(Command(
        name="Real",
        payload={"message_name": "Fake", "issue": 7},
    ))
    assert written[0].payload["message_name"] == "Real"  # not "Fake"
    assert written[0].payload["issue"] == 7


def test_audit_middleware_records_duration_ms():
    """duration_ms must be present and positive on every audited call."""
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))

    def slow_handler(_cmd):
        import time as _t
        _t.sleep(0.005)

    bus.register_command("Slow", slow_handler)
    bus.send(Command(name="Slow"))
    assert "duration_ms" in written[0].payload
    assert written[0].payload["duration_ms"] >= 0
    assert "error" not in written[0].payload


def test_audit_middleware_records_error_on_exception():
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    def raising_handler(_cmd):
        raise RuntimeError("boom")

    bus = Bus()
    import contextlib
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))
    bus.register_command("Boom", raising_handler)
    with contextlib.suppress(RuntimeError):
        bus.send(Command(name="Boom"))
    assert len(written) == 1
    assert written[0].payload["error"] == "RuntimeError"
    assert "duration_ms" in written[0].payload


def test_audit_middleware_handles_non_dict_payload():
    """Defensive: msg with no payload or weird payload shouldn't crash."""
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    class FakeMsg:
        def __init__(self):
            self.name = "Weird"
            self.payload = "not-a-dict"

    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))
    bus.register_command("Weird", lambda c: None)
    bus.send(FakeMsg())  # type: ignore[arg-type]
    assert len(written) == 1
    assert written[0].payload["message_name"] == "Weird"


def test_middleware_chain_order():
    bus = Bus()
    order = []
    bus.add_middleware(ErrorMiddleware())
    bus.add_middleware(MetricsMiddleware())
    bus.register_command("X", lambda c: order.append("handler"))
    bus.send(Command(name="X"))
    assert order == ["handler"]
