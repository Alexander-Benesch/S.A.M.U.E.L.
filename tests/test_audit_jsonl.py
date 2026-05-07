from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from samuel.adapters.audit.jsonl import JSONLAuditSink
from samuel.adapters.audit.upcasters import upcast
from samuel.core.types import AuditQuery


def test_write_and_read():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "IssueReady", "correlation_id": "c1", "payload": {"issue": 42}})
        sink.write({"event_name": "PlanCreated", "correlation_id": "c1", "payload": {"issue": 42}})

        results = sink.query(AuditQuery(issue=42))
        assert len(results) == 2


def test_query_by_correlation_id():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "A", "correlation_id": "c1", "payload": {}})
        sink.write({"event_name": "B", "correlation_id": "c2", "payload": {}})

        results = sink.query(AuditQuery(correlation_id="c1"))
        assert len(results) == 1
        assert results[0]["correlation_id"] == "c1"


def test_query_by_event_name():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "IssueReady", "correlation_id": "c1", "payload": {}})
        sink.write({"event_name": "PlanCreated", "correlation_id": "c1", "payload": {}})

        results = sink.query(AuditQuery(event_name="IssueReady"))
        assert len(results) == 1


def test_query_by_owasp_risk():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        sink.write({"event_name": "A", "owasp_risk": "broken_trust_boundaries", "payload": {}})
        sink.write({"event_name": "B", "owasp_risk": "excessive_autonomy", "payload": {}})

        results = sink.query(AuditQuery(owasp_risk="broken_trust_boundaries"))
        assert len(results) == 1


def test_query_limit():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl")
        for i in range(10):
            sink.write({"event_name": "E", "correlation_id": "c", "payload": {}})

        results = sink.query(AuditQuery(limit=3))
        assert len(results) == 3


def test_daily_rotation():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="daily")
        sink.write({"event_name": "Test", "payload": {}})

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        expected = Path(d) / f"audit_{date_str}.jsonl"
        assert expected.exists()


def test_no_rotation():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write({"event_name": "Test", "payload": {}})
        assert (Path(d) / "audit.jsonl").exists()


def test_upcast_gate_failed():
    event = {"name": "GateFailed", "event_version": 1, "gate": 3}
    result = upcast(event)
    assert result["owasp_risk"] == "unknown"
    assert result["event_version"] == 2


def test_upcast_llm_call_completed():
    event = {"name": "LLMCallCompleted", "event_version": 1, "text": "hi"}
    result = upcast(event)
    assert result["latency_ms"] == 0
    assert result["event_version"] == 2


def test_upcast_no_match():
    event = {"name": "IssueReady", "event_version": 1}
    result = upcast(event)
    assert result == event


def test_write_adds_timestamp():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write({"event_name": "Test", "payload": {}})
        line = json.loads((Path(d) / "audit.jsonl").read_text().strip())
        assert "ts" in line


def test_write_dataclass_event_serialized_structurally():
    """Regression #177: AuditEvent (dataclass) was being stringified into a
    'data' field instead of written structurally with payload/name top-level."""
    from samuel.core.events import AuditEvent

    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write(AuditEvent(payload={"message_name": "Foo", "issue": 99}))
        line = json.loads((Path(d) / "audit.jsonl").read_text().strip())
        assert "data" not in line
        assert line["name"] == "AuditEvent"
        assert line["payload"]["message_name"] == "Foo"
        assert line["payload"]["issue"] == 99


def test_write_dict_event_unchanged():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write({"name": "Hand", "payload": {"k": "v"}})
        line = json.loads((Path(d) / "audit.jsonl").read_text().strip())
        assert line["name"] == "Hand"
        assert line["payload"] == {"k": "v"}


def test_write_unknown_object_falls_back_to_str():
    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write("just a string")
        line = json.loads((Path(d) / "audit.jsonl").read_text().strip())
        assert line["data"] == "just a string"


def test_write_dataclass_query_finds_by_issue():
    """End-to-end: dataclass write → query by payload.issue must succeed."""
    from samuel.core.events import AuditEvent

    with tempfile.TemporaryDirectory() as d:
        sink = JSONLAuditSink(Path(d) / "audit.jsonl", rotation="none")
        sink.write(AuditEvent(payload={"issue": 42, "message_name": "X"}))
        sink.write(AuditEvent(payload={"issue": 99, "message_name": "Y"}))

        results = sink.query(AuditQuery(issue=42))
        assert len(results) == 1
        assert results[0]["payload"]["message_name"] == "X"
