from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from samuel.core.bus import Bus
from samuel.core.ports import IVersionControl
from samuel.core.types import SCMActivity
from samuel.slices.watch.activity import SCMActivityPoller


def _scm(rows: list[SCMActivity]):
    scm = MagicMock(spec=IVersionControl)
    scm.list_scm_activity.return_value = rows
    return scm


def test_initial_sync_uses_bounded_window_and_persists_cursor(tmp_path: Path) -> None:
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    row = SCMActivity(
        event="IssueOpened",
        number=390,
        timestamp="2026-08-20T12:00:00Z",
        title="Polling",
        actor="alice",
    )
    scm = _scm([row])
    bus = Bus()
    received: list[Any] = []
    bus.subscribe("IssueOpened", received.append)
    state_path = tmp_path / "activity.json"
    poller = SCMActivityPoller(bus, scm, state_path, initial_days=3, now_fn=lambda: now)

    result = poller.poll("corr-390")

    scm.list_scm_activity.assert_called_once_with("2026-08-18T12:00:00Z", limit=250)
    assert result["activity_observed"] == 1
    assert result["activity_forwarded"] == 1
    assert result["activity_cursor_saved"] is True
    assert received[0].payload["source"] == "polling"
    assert received[0].payload["timestamp"] == row.timestamp
    assert received[0].correlation_id == "corr-390"
    assert '"cursor": "2026-08-21T12:00:00Z"' in state_path.read_text()


def test_cursor_overlap_and_interval_skip(tmp_path: Path) -> None:
    moments = iter(
        [
            datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 12, 0, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 12, 2, tzinfo=timezone.utc),
        ]
    )
    scm = _scm([])
    poller = SCMActivityPoller(
        Bus(),
        scm,
        tmp_path / "activity.json",
        overlap_seconds=60,
        interval_seconds=60,
        now_fn=lambda: next(moments),
    )

    poller.poll()
    skipped = poller.poll()
    poller.poll()

    assert skipped["activity_poll"] == "interval_skip"
    assert scm.list_scm_activity.call_count == 2
    assert scm.list_scm_activity.call_args_list[-1].args[0] == "2026-08-21T11:59:00Z"


def test_poll_failure_does_not_advance_cursor(tmp_path: Path) -> None:
    scm = MagicMock(spec=IVersionControl)
    scm.list_scm_activity.side_effect = RuntimeError("offline")
    state_path = tmp_path / "activity.json"
    poller = SCMActivityPoller(
        Bus(),
        scm,
        state_path,
        now_fn=lambda: datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(RuntimeError, match="offline"):
        poller.poll()

    assert not state_path.exists()


def test_future_cursor_is_reset_to_initial_window(tmp_path: Path) -> None:
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    state_path = tmp_path / "activity.json"
    state_path.write_text('{"cursor":"2026-08-22T12:00:00Z"}')
    scm = _scm([])
    poller = SCMActivityPoller(Bus(), scm, state_path, initial_days=2, now_fn=lambda: now)

    poller.poll()

    assert scm.list_scm_activity.call_args.args[0] == "2026-08-19T12:00:00Z"


def test_initial_sync_skips_matching_legacy_webhook_audit_row(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "agent.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-08-21T10:00:01Z",
                "name": "AuditEvent",
                "payload": {
                    "message_name": "IssueOpened",
                    "number": 390,
                    "source": "webhook",
                },
            }
        )
        + "\n"
    )
    scm = _scm(
        [
            SCMActivity(
                event="IssueOpened",
                number=390,
                timestamp="2026-08-21T10:00:00Z",
            )
        ]
    )
    received: list[Any] = []
    bus = Bus()
    bus.subscribe("IssueOpened", received.append)
    poller = SCMActivityPoller(
        bus,
        scm,
        tmp_path / "scm_activity_poll.json",
        now_fn=lambda: datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc),
    )

    result = poller.poll()

    assert result["activity_observed"] == 1
    assert result["activity_forwarded"] == 0
    assert result["activity_deduplicated"] == 1
    assert received == []


def test_unknown_adapter_event_is_not_published(tmp_path: Path) -> None:
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    scm = _scm(
        [
            SCMActivity(
                event="RepositoryStarred",
                number=1,
                timestamp=(now - timedelta(minutes=1)).isoformat(),
            )
        ]
    )
    received: list[Any] = []
    bus = Bus()
    bus.subscribe("*", received.append)

    result = SCMActivityPoller(bus, scm, tmp_path / "activity.json", now_fn=lambda: now).poll()

    assert result["activity_observed"] == 1
    assert result["activity_forwarded"] == 0
    assert received == []
