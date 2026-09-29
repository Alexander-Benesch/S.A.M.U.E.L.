from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from samuel.cli import _cmd_resume
from samuel.core.bus import Bus
from samuel.core.state import StateStoreError


class _Coordinator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "pending": 1, "blocked": 0, "last_outcome": {}}

    def list(self) -> list[dict[str, Any]]:
        return [{"checkpoint_key": "checkpoint-1", "resume_eligible": True}]

    def inspect(self, checkpoint_key: str) -> dict[str, Any]:
        if checkpoint_key != "checkpoint-1":
            raise StateStoreError("resume_checkpoint_missing", "missing")
        return {"checkpoint_key": checkpoint_key, "boundary": "push_pending"}

    def abandon(self, checkpoint_key: str, *, reason: str) -> dict[str, Any]:
        self.calls.append(("abandon", checkpoint_key, reason))
        return {"checkpoint_key": checkpoint_key, "status": "abandoned"}

    def cleanup(self, checkpoint_key: str, *, reason: str) -> dict[str, Any]:
        self.calls.append(("cleanup", checkpoint_key, reason))
        return {"checkpoint_key": checkpoint_key, "status": "cleaned"}


def _args(action: str, checkpoint_key: str = "", reason: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        action=action,
        checkpoint_key=checkpoint_key,
        reason=reason,
        json=True,
    )


def test_resume_list_and_inspect_are_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    bus = Bus()
    bus.resume_coordinator = _Coordinator()

    assert _cmd_resume(bus, _args("list")) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["resume"]["status"]["pending"] == 1
    assert listed["resume"]["checkpoints"][0]["checkpoint_key"] == "checkpoint-1"

    assert _cmd_resume(bus, _args("inspect", "checkpoint-1")) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["resume"] == {
        "boundary": "push_pending",
        "checkpoint_key": "checkpoint-1",
    }


@pytest.mark.parametrize("action", ["abandon", "cleanup"])
def test_destructive_resume_operator_actions_require_reason(
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    bus = Bus()
    bus.resume_coordinator = _Coordinator()

    assert _cmd_resume(bus, _args(action, "checkpoint-1")) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == f"resume_{action}_arguments_required"


@pytest.mark.parametrize("action", ["attempt", "resume"])
def test_targeted_attempt_and_resume_alias_report_pending_as_nonzero(
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    bus = Bus()
    bus.resume_coordinator = _Coordinator()
    bus.register_command(
        "ResumePending",
        lambda command: {
            "attempted": 1,
            "resumed": 0,
            "blocked": 1,
            "details": [
                {
                    "checkpoint_key": command.payload["checkpoint_key"],
                    "pending": True,
                    "reason": "resume_lease_live",
                }
            ],
        },
    )

    assert _cmd_resume(bus, _args(action, "checkpoint-1")) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["resume"]["details"][0]["reason"] == "resume_lease_live"
