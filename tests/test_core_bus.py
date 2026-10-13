from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from samuel.core.bus import (
    AuditMiddleware,
    Bus,
    ErrorMiddleware,
    HandledCommandFailure,
    IdempotencyMiddleware,
    IdempotencyStore,
    MetricsMiddleware,
)
from samuel.core.commands import Command
from samuel.core.events import Event


def test_bus_publish_subscribe():
    bus = Bus()
    received: list[Event] = []
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


def test_idempotency_middleware_deduplicates_events_by_payload_key():
    bus = Bus()
    bus.add_middleware(IdempotencyMiddleware(IdempotencyStore()))
    received: list[Event] = []
    bus.subscribe("Observed", received.append)

    bus.publish(Event(name="Observed", payload={"idempotency_key": "activity:1"}))
    bus.publish(Event(name="Observed", payload={"idempotency_key": "activity:1"}))

    assert len(received) == 1


def test_parallel_same_key_waits_for_one_dispatch_and_replays_once():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event as ThreadEvent

    bus = Bus()
    bus.add_middleware(IdempotencyMiddleware(IdempotencyStore()))
    entered = ThreadEvent()
    release = ThreadEvent()
    effects = []

    def handle(_event):
        effects.append("started")
        entered.set()
        assert release.wait(2)

    bus.subscribe("Observed", handle)

    def publish():
        bus.publish(Event(name="Observed", payload={"idempotency_key": "delivery:1"}))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(publish)
        assert entered.wait(2)
        second = pool.submit(publish)
        release.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert effects == ["started"]


def test_failed_claim_is_released_for_retry_without_marking_key():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event as ThreadEvent

    store = IdempotencyStore()
    middleware = IdempotencyMiddleware(store)
    entered = ThreadEvent()
    release = ThreadEvent()
    calls = []

    def dispatch(_message):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
            raise RuntimeError("transient dispatch failure")
        return "recovered"

    message = Command(name="Do", idempotency_key="retry:1")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(middleware, message, dispatch)
        assert entered.wait(2)
        second = pool.submit(middleware, message, dispatch)
        release.set()
        with pytest.raises(RuntimeError, match="transient"):
            first.result(timeout=2)
        assert second.result(timeout=2) == "recovered"

    assert calls == [1, 1]
    assert store.has_key("retry:1")


def test_error_middleware_catches_exceptions():
    bus = Bus()
    bus.add_middleware(ErrorMiddleware())

    def bad_handler(c):
        raise RuntimeError("boom")

    bus.register_command("Fail", bad_handler)
    result = bus.send(Command(name="Fail"))
    assert isinstance(result, HandledCommandFailure)
    assert result == HandledCommandFailure(
        error_class="internal",
        reason_code="internal_command_error",
        correlation_id=result.correlation_id,
        command_name="Fail",
    )
    assert not result


def test_error_middleware_distinguishes_legitimate_none_from_failure():
    bus = Bus()
    bus.add_middleware(ErrorMiddleware())
    bus.register_command("NoResult", lambda _command: None)

    assert bus.send(Command(name="NoResult")) is None


def test_error_middleware_publishes_bounded_abort_for_normal_command_exception():
    bus = Bus()
    bus.add_middleware(ErrorMiddleware(bus=bus))
    events: list[Event] = []
    bus.subscribe("WorkflowAborted", events.append)

    def fail(_command):
        raise RuntimeError("credential-like detail must not become event data")

    bus.register_command("PlanIssue", fail)
    bus.send(
        Command(
            name="PlanIssue",
            payload={"issue": 41},
            correlation_id="corr-normal-failure",
        )
    )

    assert len(events) == 1
    assert events[0].payload == {
        "reason": "internal_command_error",
        "error_class": "internal",
        "source_command": "PlanIssue",
        "issue": 41,
    }
    assert events[0].correlation_id == "corr-normal-failure"


def test_error_middleware_publishes_bounded_correlated_diagnostic():
    bus = Bus()
    bus.add_middleware(ErrorMiddleware(bus=bus))
    diagnostics: list[Event] = []
    bus.subscribe("DiagnosticRaised", diagnostics.append)

    def fail(_command):
        raise RuntimeError("credential-like detail must not become event data")

    bus.register_command("PlanIssue", fail)
    bus.send(
        Command(
            name="PlanIssue",
            payload={"issue": 41},
            correlation_id="corr-normal-failure",
        )
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].correlation_id == "corr-normal-failure"
    assert diagnostics[0].payload["issue"] == 41
    assert diagnostics[0].payload["source_command"] == "PlanIssue"
    assert diagnostics[0].payload["reason"] == "internal_command_error"
    assert diagnostics[0].payload["error_class"] == "internal"
    assert "credential-like detail" not in str(diagnostics[0].payload)


def test_handled_command_exception_is_not_a_successful_command_audit():
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))
    bus.add_middleware(ErrorMiddleware(bus=bus))

    def fail(_command):
        raise ValueError("private detail")

    bus.register_command("PlanIssue", fail)
    bus.send(Command(name="PlanIssue", payload={"issue": 52}, correlation_id="run-52"))

    command_audits = [
        event.payload for event in written if event.payload.get("message_name") == "PlanIssue"
    ]
    assert len(command_audits) == 1
    assert command_audits[0]["error"] == "internal_command_error"
    assert "private detail" not in str(command_audits[0])


def test_audit_omits_source_diff_but_keeps_live_event_payload() -> None:
    written = []

    class FakeSink:
        def write(self, event):
            written.append(event)

    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=FakeSink()))
    received: list[Event] = []
    bus.subscribe("PRCreated", received.append)
    event = Event(name="PRCreated", payload={"issue": 42, "diff": "+private source"})

    bus.publish(event)

    assert received[0].payload["diff"] == "+private source"
    audit = next(row for row in written if row.payload["message_name"] == "PRCreated")
    assert audit.payload["diff"] == "***SOURCE_DIFF_OMITTED***"


def test_diagnostic_publish_failure_does_not_hide_terminal_abort():
    from samuel.core.events import DiagnosticRaised

    class DiagnosticFailingBus(Bus):
        def publish(self, event):
            if isinstance(event, DiagnosticRaised):
                raise RuntimeError("diagnostic sink unavailable")
            return super().publish(event)

    bus = DiagnosticFailingBus()
    bus.add_middleware(ErrorMiddleware(bus=bus))
    aborted: list[Event] = []
    bus.subscribe("WorkflowAborted", aborted.append)

    def fail(_command):
        raise RuntimeError("original private detail")

    bus.register_command("PlanIssue", fail)
    bus.send(Command(name="PlanIssue", payload={"issue": 53}, correlation_id="run-53"))

    assert len(aborted) == 1
    assert aborted[0].correlation_id == "run-53"
    assert aborted[0].payload["reason"] == "internal_command_error"


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


def test_metrics_middleware_counts_failure_consumed_by_inner_error_middleware():
    bus = Bus()
    metrics = MetricsMiddleware()
    bus.add_middleware(metrics)
    bus.add_middleware(ErrorMiddleware(bus=bus))
    bus.register_command("Fail", lambda _command: (_ for _ in ()).throw(RuntimeError("raw")))

    result = bus.send(Command(name="Fail"))

    assert isinstance(result, HandledCommandFailure)
    assert metrics.counts["Fail"] == 0
    assert metrics.errors["Fail"] == 1


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
    bus.send(
        Command(
            name="Real",
            payload={"message_name": "Fake", "issue": 7},
        )
    )
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


# --- #334: Dead-Letter-Queue ---------------------------------------------


def test_dlq_records_failed_event_handler():
    from samuel.core.bus import DeadLetterQueue

    with tempfile.TemporaryDirectory() as tmp:
        dlq = DeadLetterQueue(path=Path(tmp) / "dlq.jsonl")
        bus = Bus()
        bus.dlq = dlq

        def boom(_e):
            raise ValueError("kaboom")

        ok = []
        bus.subscribe("Ping", boom)
        bus.subscribe("Ping", lambda e: ok.append(e))  # bleibt isoliert
        bus.publish(Event(name="Ping", payload={"x": 1}))

        assert len(ok) == 1, "other subscriber must still run"
        rows = dlq.list()
        assert len(rows) == 1
        assert rows[0]["event_name"] == "Ping"
        assert "kaboom" in rows[0]["error"]
        assert rows[0]["payload"] == {"x": 1}
        assert "boom" in rows[0]["handler"]


def test_dlq_no_record_on_success():
    from samuel.core.bus import DeadLetterQueue

    with tempfile.TemporaryDirectory() as tmp:
        dlq = DeadLetterQueue(path=Path(tmp) / "dlq.jsonl")
        bus = Bus()
        bus.dlq = dlq
        bus.subscribe("Ping", lambda e: None)
        bus.publish(Event(name="Ping"))
        assert dlq.list() == []


def test_dlq_list_newest_first_and_get():
    from samuel.core.bus import DeadLetterQueue

    with tempfile.TemporaryDirectory() as tmp:
        dlq = DeadLetterQueue(path=Path(tmp) / "dlq.jsonl")
        id1 = dlq.record(event_name="A", payload={}, error="e1")
        id2 = dlq.record(event_name="B", payload={}, error="e2")
        rows = dlq.list()
        assert [r["event_name"] for r in rows] == ["B", "A"]
        first = dlq.get(id1)
        second = dlq.get(id2)
        assert first is not None
        assert second is not None
        assert first["event_name"] == "A"
        assert second["event_name"] == "B"
        assert dlq.get("nope") is None


def test_dlq_replay_republishes_event():
    from samuel.core.bus import DeadLetterQueue
    from samuel.core.events import Event as _Ev

    with tempfile.TemporaryDirectory() as tmp:
        dlq = DeadLetterQueue(path=Path(tmp) / "dlq.jsonl")
        eid = dlq.record(event_name="Ping", payload={"k": "v"}, error="x")
        bus = Bus()
        got = []
        bus.subscribe("Ping", lambda e: got.append(e))
        entry = dlq.get(eid)
        assert entry is not None
        bus.publish(_Ev(name=entry["event_name"], payload=entry["payload"]))
        assert got and got[0].payload == {"k": "v"}


def test_dlq_disabled_is_noop():
    bus = Bus()  # bus.dlq is None

    def boom(_e):
        raise RuntimeError("x")

    bus.subscribe("Ping", boom)
    bus.publish(Event(name="Ping"))  # darf nicht crashen
