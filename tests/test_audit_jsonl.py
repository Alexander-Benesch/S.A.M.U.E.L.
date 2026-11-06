from __future__ import annotations

import json
import multiprocessing
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

import samuel.adapters.audit.jsonl as jsonl_module
from samuel.adapters.audit.jsonl import AuditWriteError, JSONLAuditSink, verify_chain
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
        # #290: ASI04 agentic_supply_chain + ASI01 agent_goal_hijack
        sink.write({"event_name": "A", "owasp_risk": "agentic_supply_chain", "payload": {}})
        sink.write({"event_name": "B", "owasp_risk": "agent_goal_hijack", "payload": {}})

        results = sink.query(AuditQuery(owasp_risk="agentic_supply_chain"))
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


# --- #333: HMAC-Chain (Tamper-Evidenz) -----------------------------------


def test_no_chain_fields_without_key():
    with tempfile.TemporaryDirectory() as d:
        fp = Path(d) / "audit.jsonl"
        sink = JSONLAuditSink(fp, rotation="none")
        sink.write({"event_name": "X", "payload": {}})
        rec = json.loads(fp.read_text().splitlines()[0])
        assert "hmac" not in rec and "prev_hash" not in rec


def test_keyless_writer_refuses_existing_signed_chain_without_mutation(tmp_path: Path):
    fp = tmp_path / "audit.jsonl"
    signed = JSONLAuditSink(fp, rotation="none", hmac_key="k")
    signed.write({"event_name": "A", "payload": {"order": 1}})
    before = fp.read_bytes()

    with pytest.raises(AuditWriteError, match="existing chain is signed"):
        JSONLAuditSink(fp, rotation="none").write(
            {"event_name": "UNSIGNED", "payload": {"order": 2}}
        )

    assert fp.read_bytes() == before
    signed.write({"event_name": "B", "payload": {"order": 3}})
    assert verify_chain(fp, "k") == {
        "ok": True,
        "file": str(fp),
        "records": 2,
        "error": "",
        "line": 0,
    }


def test_chain_written_and_verifies():
    from samuel.adapters.audit.jsonl import verify_chain

    with tempfile.TemporaryDirectory() as d:
        fp = Path(d) / "audit.jsonl"
        sink = JSONLAuditSink(fp, rotation="none", hmac_key="secret-key")
        for i in range(5):
            sink.write({"event_name": "E", "payload": {"i": i}})
        lines = [json.loads(x) for x in fp.read_text().splitlines()]
        assert lines[0]["prev_hash"] == ""
        # jede Zeile verkettet mit der vorherigen
        for a, b in zip(lines, lines[1:], strict=False):
            assert b["prev_hash"] == a["hmac"]
        res = verify_chain(fp, "secret-key")
        assert res["ok"] is True
        assert res["records"] == 5


def test_verify_detects_tampered_payload():
    from samuel.adapters.audit.jsonl import verify_chain

    with tempfile.TemporaryDirectory() as d:
        fp = Path(d) / "audit.jsonl"
        sink = JSONLAuditSink(fp, rotation="none", hmac_key="k")
        sink.write({"event_name": "E", "payload": {"amount": 1}})
        sink.write({"event_name": "E", "payload": {"amount": 2}})
        # Zeile 1 nachtraeglich faelschen, hmac aber belassen
        lines = fp.read_text().splitlines()
        rec = json.loads(lines[0])
        rec["payload"]["amount"] = 999
        lines[0] = json.dumps(rec)
        fp.write_text("\n".join(lines) + "\n")
        res = verify_chain(fp, "k")
        assert res["ok"] is False
        assert "hmac mismatch" in res["error"]
        assert res["line"] == 1


def test_verify_detects_deleted_record():
    from samuel.adapters.audit.jsonl import verify_chain

    with tempfile.TemporaryDirectory() as d:
        fp = Path(d) / "audit.jsonl"
        sink = JSONLAuditSink(fp, rotation="none", hmac_key="k")
        for i in range(3):
            sink.write({"event_name": "E", "payload": {"i": i}})
        lines = fp.read_text().splitlines()
        del lines[1]  # mittleren Record entfernen -> Chain bricht
        fp.write_text("\n".join(lines) + "\n")
        res = verify_chain(fp, "k")
        assert res["ok"] is False
        assert "broken chain" in res["error"]


def test_verify_detects_unsigned_record():
    from samuel.adapters.audit.jsonl import verify_chain

    with tempfile.TemporaryDirectory() as d:
        fp = Path(d) / "audit.jsonl"
        fp.write_text(json.dumps({"event_name": "E", "payload": {}}) + "\n")
        res = verify_chain(fp, "k")
        assert res["ok"] is False
        assert "missing hmac" in res["error"]


def test_chain_continues_across_process_restart():
    """Neuer Sink (Prozessneustart) liest den letzten HMAC und setzt fort."""
    from samuel.adapters.audit.jsonl import verify_chain

    with tempfile.TemporaryDirectory() as d:
        fp = Path(d) / "audit.jsonl"
        JSONLAuditSink(fp, rotation="none", hmac_key="k").write({"event_name": "A", "payload": {}})
        # zweiter Sink-Instanz (frischer Prozess)
        JSONLAuditSink(fp, rotation="none", hmac_key="k").write({"event_name": "B", "payload": {}})
        lines = [json.loads(x) for x in fp.read_text().splitlines()]
        assert lines[1]["prev_hash"] == lines[0]["hmac"]
        assert verify_chain(fp, "k")["ok"] is True


def _write_first_and_third(
    path: str,
    first_written: multiprocessing.synchronize.Event,
    second_written: multiprocessing.synchronize.Event,
) -> None:
    sink = JSONLAuditSink(path, rotation="none", hmac_key="k")
    sink.write({"event_name": "A", "payload": {"order": 1}})
    first_written.set()
    if not second_written.wait(timeout=10):
        raise RuntimeError("second writer did not finish")
    sink.write({"event_name": "C", "payload": {"order": 3}})


def _write_second(
    path: str,
    first_written: multiprocessing.synchronize.Event,
    second_written: multiprocessing.synchronize.Event,
) -> None:
    if not first_written.wait(timeout=10):
        raise RuntimeError("first writer did not finish")
    JSONLAuditSink(path, rotation="none", hmac_key="k").write(
        {"event_name": "B", "payload": {"order": 2}}
    )
    second_written.set()


@pytest.mark.skipif(jsonl_module.fcntl is None, reason="requires POSIX flock")
def test_chain_serializes_interleaved_processes_against_disk_head(tmp_path: Path):
    """Regression #689: writer A must not reuse its stale process-local head."""
    fp = tmp_path / "audit.jsonl"
    context = multiprocessing.get_context("spawn")
    first_written = context.Event()
    second_written = context.Event()
    first = context.Process(
        target=_write_first_and_third,
        args=(str(fp), first_written, second_written),
    )
    second = context.Process(
        target=_write_second,
        args=(str(fp), first_written, second_written),
    )

    first.start()
    second.start()
    first.join(timeout=20)
    second.join(timeout=20)

    assert first.exitcode == 0
    assert second.exitcode == 0
    records = [json.loads(line) for line in fp.read_text().splitlines()]
    assert [record["payload"]["order"] for record in records] == [1, 2, 3]
    assert verify_chain(fp, "k") == {
        "ok": True,
        "file": str(fp),
        "records": 3,
        "error": "",
        "line": 0,
    }


def test_signed_write_fails_closed_without_posix_lock(tmp_path: Path, monkeypatch):
    fp = tmp_path / "audit.jsonl"
    monkeypatch.setattr(jsonl_module, "fcntl", None)

    with pytest.raises(AuditWriteError, match="requires POSIX flock"):
        JSONLAuditSink(fp, rotation="none", hmac_key="k").write({"event_name": "A", "payload": {}})

    assert not fp.exists()


def test_signed_write_refuses_invalid_existing_tail(tmp_path: Path):
    fp = tmp_path / "audit.jsonl"
    fp.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(AuditWriteError, match="tail is not valid JSON"):
        JSONLAuditSink(fp, rotation="none", hmac_key="k").write({"event_name": "A", "payload": {}})

    assert fp.read_text(encoding="utf-8") == "not-json\n"


def test_signed_write_refuses_tampered_existing_tail(tmp_path: Path):
    fp = tmp_path / "audit.jsonl"
    sink = JSONLAuditSink(fp, rotation="none", hmac_key="k")
    sink.write({"event_name": "A", "payload": {"value": 1}})
    original = json.loads(fp.read_text(encoding="utf-8"))
    original["payload"]["value"] = 2
    fp.write_text(json.dumps(original) + "\n", encoding="utf-8")

    with pytest.raises(AuditWriteError, match="tail HMAC does not verify"):
        sink.write({"event_name": "B", "payload": {}})

    assert len(fp.read_text(encoding="utf-8").splitlines()) == 1
