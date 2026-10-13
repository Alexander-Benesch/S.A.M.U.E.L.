from __future__ import annotations

import tempfile
from argparse import Namespace
from pathlib import Path

from samuel.cli import _cmd_dlq
from samuel.core.bus import Bus, DeadLetterQueue


def _bus_with_dlq(tmp):
    bus = Bus()
    bus.dlq = DeadLetterQueue(path=Path(tmp) / "dlq.jsonl")
    return bus


def test_dlq_list_empty(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        bus = _bus_with_dlq(tmp)
        rc = _cmd_dlq(bus, Namespace(action="list", id=None, limit=50))
        assert rc == 0
        assert "DLQ empty" in capsys.readouterr().out


def test_dlq_list_shows_entries(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        bus = _bus_with_dlq(tmp)
        bus.dlq.record(event_name="Ping", payload={}, error="ValueError: x")
        rc = _cmd_dlq(bus, Namespace(action="list", id=None, limit=50))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Ping" in out and "ValueError" in out


def test_dlq_replay_republishes(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        bus = _bus_with_dlq(tmp)
        eid = bus.dlq.record(event_name="Ping", payload={"k": "v"}, error="x")
        got = []
        bus.subscribe("Ping", lambda e: got.append(e))
        rc = _cmd_dlq(bus, Namespace(action="replay", id=eid, limit=50))
        assert rc == 0
        assert got and got[0].payload == {"k": "v"}
        assert "replayed" in capsys.readouterr().out


def test_dlq_replay_unknown_id(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        bus = _bus_with_dlq(tmp)
        rc = _cmd_dlq(bus, Namespace(action="replay", id="nope", limit=50))
        assert rc == 1


def test_dlq_replay_missing_id(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        bus = _bus_with_dlq(tmp)
        rc = _cmd_dlq(bus, Namespace(action="replay", id=None, limit=50))
        assert rc == 1
