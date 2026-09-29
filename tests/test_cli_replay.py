from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from samuel.cli import _cmd_replay
from samuel.core.bus import Bus


class _Cfg:
    def __init__(self, data_dir):
        self._d = data_dir

    def get(self, key, default=None):
        return self._d if key == "agent.data_dir" else default


def _bus(data_dir):
    bus = Bus()
    bus.config = _Cfg(str(data_dir))
    return bus


def _log(tmp_path: Path, records):
    d = tmp_path / "logs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )


def test_replay_no_events(tmp_path, capsys):
    rc = _cmd_replay(_bus(tmp_path), Namespace(issue=42, run=None, publish=False))
    assert rc == 0
    assert "no audit events" in capsys.readouterr().out


def test_replay_prints_snapshot(tmp_path, capsys):
    _log(
        tmp_path,
        [
            {"ts": "2026-05-29T10:00:00", "payload": {"message_name": "IssueReady", "issue": 42}},
            {"ts": "2026-05-29T10:05:00", "payload": {"message_name": "PRMerged", "issue": 42}},
        ],
    )
    rc = _cmd_replay(_bus(tmp_path), Namespace(issue=42, run=None, publish=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "status=completed" in out
    assert "IssueReady" in out and "PRMerged" in out


def test_replay_publish_side_effect_free(tmp_path, capsys):
    _log(
        tmp_path,
        [
            {"ts": "1", "payload": {"message_name": "IssueReady", "issue": 42}},
        ],
    )
    rc = _cmd_replay(_bus(tmp_path), Namespace(issue=42, run=None, publish=True))
    assert rc == 0
    assert "replayed 1 events to a no-op bus" in capsys.readouterr().out
