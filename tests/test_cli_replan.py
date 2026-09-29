from __future__ import annotations

import argparse

from samuel.cli import _cmd_replan, _cmd_run
from samuel.core.bus import Bus
from samuel.core.events import PlanBlocked, PlanPosted, PlanReplanRejected


def test_run_returns_nonzero_when_active_plan_blocks_replanning(capsys) -> None:
    bus = Bus()
    bus.subscribe(
        "IssueReady",
        lambda event: bus.publish(
            PlanReplanRejected(
                payload={"issue": 42, "reason": "active_plan_requires_explicit_replan"},
                correlation_id=event.correlation_id,
            )
        ),
    )

    result = _cmd_run(bus, argparse.Namespace(issue=42))

    assert result == 1
    assert "samuel replan" in capsys.readouterr().err


def test_run_returns_nonzero_for_own_plan_block_and_redacts_reason(capsys) -> None:
    bus = Bus()
    bus.subscribe(
        "IssueReady",
        lambda event: bus.publish(
            PlanBlocked(
                payload={
                    "issue": 42,
                    "reason": "provider blocked sk-abcdefghijklmnopqrstuvwxyz123456",
                },
                correlation_id=event.correlation_id,
            )
        ),
    )

    result = _cmd_run(bus, argparse.Namespace(issue=42))

    assert result == 1
    stderr = capsys.readouterr().err
    assert "Planung für Issue #42 blockiert" in stderr
    assert "***REDACTED***" in stderr
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in stderr


def test_run_ignores_foreign_terminal_events_and_returns_zero(capsys) -> None:
    bus = Bus()

    def publish_foreign_events(event) -> None:
        bus.publish(
            PlanBlocked(
                payload={"issue": 7, "reason": "other_issue"},
                correlation_id=event.correlation_id,
            )
        )
        bus.publish(
            PlanBlocked(
                payload={"issue": 42, "reason": "other_invocation"},
                correlation_id="foreign-invocation",
            )
        )
        bus.publish(
            PlanReplanRejected(
                payload={"issue": 42, "reason": "other_invocation"},
                correlation_id="foreign-invocation",
            )
        )
        bus.publish(
            PlanPosted(
                payload={"issue": 42, "plan_comment_id": 17},
                correlation_id=event.correlation_id,
            )
        )

    bus.subscribe("IssueReady", publish_foreign_events)

    result = _cmd_run(bus, argparse.Namespace(issue=42))

    assert result == 0
    assert capsys.readouterr().err == ""


def test_replan_dispatches_required_reason() -> None:
    bus = Bus()
    captured = []

    def handle_replan(command):
        captured.append(command)
        return {"score": 100}

    bus.register_command("ReplanIssue", handle_replan)

    result = _cmd_replan(
        bus,
        argparse.Namespace(issue=42, reason="Plan ist unvollständig"),
    )

    assert result == 0
    assert captured[0].issue_number == 42
    assert captured[0].reason == "Plan ist unvollständig"
