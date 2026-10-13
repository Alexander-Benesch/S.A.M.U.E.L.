from __future__ import annotations

import json
from argparse import Namespace

from samuel.adapters.audit.jsonl import JSONLAuditSink
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.cli import _cmd_audit
from samuel.core.bus import Bus
from samuel.core.events import IntegrityViolation


class _Cfg:
    def __init__(self, data_dir):
        self._d = data_dir

    def get(self, key, default=None):
        return self._d if key == "agent.data_dir" else default


def _bus(data_dir, *, with_state=False):
    bus = Bus()
    bus.config = _Cfg(str(data_dir))
    if with_state:
        state = SQLiteStateStore(data_dir)
        bus.state_store = state
        bus.run_projection_store = state.projections
    return bus


def test_audit_verify_no_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SAMUEL_AUDIT_HMAC_KEY", raising=False)
    rc = _cmd_audit(_bus(tmp_path), Namespace(action="verify"))
    assert rc == 1
    assert "not set" in capsys.readouterr().out


def test_audit_verify_clean(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SAMUEL_AUDIT_HMAC_KEY", "k")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    sink = JSONLAuditSink(log_dir / "agent.jsonl", rotation="none", hmac_key="k")
    for i in range(3):
        sink.write({"event_name": "E", "payload": {"i": i}})
    rc = _cmd_audit(_bus(tmp_path), Namespace(action="verify"))
    assert rc == 0
    assert "VERIFIED" in capsys.readouterr().out


def test_audit_verify_persists_instance_bound_projection(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SAMUEL_AUDIT_HMAC_KEY", "k")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    sink = JSONLAuditSink(log_dir / "agent.jsonl", rotation="none", hmac_key="k")
    sink.write({"event_name": "E", "payload": {"bounded": True}})
    bus = _bus(tmp_path, with_state=True)

    assert _cmd_audit(bus, Namespace(action="verify")) == 0

    projection = bus.run_projection_store.get_projection("health-readiness:audit_integrity")
    assert projection is not None
    assert projection.status == "passed"
    assert projection.payload["instance_uuid"] == bus.state_store.status().authority_instance
    assert projection.payload["summary"] == {
        "files_checked": 1,
        "records_checked": 1,
        "failed_files": 0,
    }
    capsys.readouterr()


def test_audit_verify_tampered_publishes_integrity_violation(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SAMUEL_AUDIT_HMAC_KEY", "k")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fp = log_dir / "agent.jsonl"
    sink = JSONLAuditSink(fp, rotation="none", hmac_key="k")
    sink.write({"event_name": "E", "payload": {"amount": 1}})
    sink.write({"event_name": "E", "payload": {"amount": 2}})
    # ersten Record faelschen
    lines = fp.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["payload"]["amount"] = 999
    lines[0] = json.dumps(rec)
    fp.write_text("\n".join(lines) + "\n")

    bus = _bus(tmp_path)
    got: list = []
    bus.subscribe("IntegrityViolation", lambda e: got.append(e))
    rc = _cmd_audit(bus, Namespace(action="verify"))
    assert rc == 1
    assert "TAMPERING DETECTED" in capsys.readouterr().out
    assert len(got) == 1 and isinstance(got[0], IntegrityViolation)
    assert got[0].payload["owasp_risk"] == "agentic_supply_chain"
