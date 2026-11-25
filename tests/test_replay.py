from __future__ import annotations

import json
from pathlib import Path

from samuel.core.bus import Bus
from samuel.core.replay import build_snapshot, load_run_events, replay_to_bus


def _write_log(tmp_path: Path, records: list[dict]) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "agent.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )


def test_load_filters_by_issue_and_sorts(tmp_path):
    _write_log(
        tmp_path,
        [
            {
                "ts": "2026-05-29T10:02",
                "name": "AuditEvent",
                "correlation_id": "r1",
                "payload": {"message_name": "PlanCreated", "issue": 42},
            },
            {
                "ts": "2026-05-29T10:01",
                "name": "AuditEvent",
                "correlation_id": "r1",
                "payload": {"message_name": "IssueReady", "issue": 42},
            },
            {
                "ts": "2026-05-29T10:03",
                "name": "AuditEvent",
                "correlation_id": "r2",
                "payload": {"message_name": "IssueReady", "issue": 99},
            },
        ],
    )
    rows = load_run_events(str(tmp_path), issue=42)
    assert [r["payload"]["message_name"] for r in rows] == ["IssueReady", "PlanCreated"]


def test_load_filters_by_run_id(tmp_path):
    _write_log(
        tmp_path,
        [
            {"ts": "1", "correlation_id": "r1", "payload": {"message_name": "A", "issue": 7}},
            {"ts": "2", "correlation_id": "r2", "payload": {"message_name": "B", "issue": 7}},
        ],
    )
    rows = load_run_events(str(tmp_path), issue=7, run_id="r2")
    assert len(rows) == 1 and rows[0]["payload"]["message_name"] == "B"


def test_load_empty_when_no_logs(tmp_path):
    assert load_run_events(str(tmp_path), issue=1) == []


def test_snapshot_status_completed():
    events = [
        {"ts": "1", "payload": {"message_name": "IssueReady", "issue": 5}},
        {"ts": "2", "payload": {"message_name": "PRMerged", "issue": 5}},
    ]
    snap = build_snapshot(events, issue=5)
    assert snap["status"] == "completed"
    assert snap["terminal_event"] == "PRMerged"
    assert snap["event_count"] == 2
    assert snap["stages"]["IssueReady"] == 1
    assert snap["first_ts"] == "1" and snap["last_ts"] == "2"


def test_snapshot_status_failed():
    events = [
        {"ts": "1", "payload": {"message_name": "PlanCreated", "issue": 5}},
        {"ts": "2", "payload": {"message_name": "PlanBlocked", "issue": 5, "reason": "boom"}},
    ]
    snap = build_snapshot(events, issue=5)
    assert snap["status"] == "failed"
    assert snap["terminal_event"] == "PlanBlocked"
    assert snap["timeline"][-1]["message"] == "boom"


def test_gate_failure_without_terminal_workflow_outcome_remains_in_progress():
    events = [
        {"ts": "1", "payload": {"message_name": "GateFailed", "issue": 5}},
        {"ts": "2", "payload": {"message_name": "HealingAttemptStarted", "issue": 5}},
    ]

    snap = build_snapshot(events, issue=5)

    assert snap["status"] == "in_progress"
    assert snap["terminal_event"] == ""


def test_pr_creation_failed_is_a_failure_terminal():
    events = [
        {"ts": "1", "payload": {"message_name": "GatesPassed", "issue": 5}},
        {
            "ts": "2",
            "payload": {
                "message_name": "PRCreationFailed",
                "issue": 5,
                "reason": "SCM did not confirm creation of a valid pull request",
            },
        },
    ]

    snap = build_snapshot(events, issue=5)

    assert snap["status"] == "failed"
    assert snap["terminal_event"] == "PRCreationFailed"


def test_snapshot_empty():
    snap = build_snapshot([], issue=5)
    assert snap["status"] == "unknown"
    assert snap["event_count"] == 0


def test_replay_to_bus_is_side_effect_free():
    """Replay publisht Events; an einem frischen Bus ohne Handler passiert
    nichts Reales. Command-Handler werden nie getriggert."""
    events = [
        {"payload": {"message_name": "IssueReady", "issue": 5}},
        {"payload": {"message_name": "PlanCreated", "issue": 5}},
    ]
    bus = Bus()
    triggered = []
    bus.register_command("PlanIssue", lambda c: triggered.append(c))
    seen = []
    bus.subscribe("*", lambda e: seen.append(e.name))
    n = replay_to_bus(events, bus)
    assert n == 2
    assert seen == ["IssueReady", "PlanCreated"]
    assert triggered == []  # keine Command-Side-Effects
