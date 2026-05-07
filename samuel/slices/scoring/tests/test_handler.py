"""Tests for ScoringHandler (#232)."""
from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, ScoreCommand
from samuel.core.events import Event
from samuel.core.ports import IVersionControl
from samuel.core.types import Comment, Issue
from samuel.slices.scoring.handler import (
    ScoringHandler,
    map_ac_results_to_criteria,
)


class MockSCM(IVersionControl):
    def __init__(self, plan_comment: str = "") -> None:
        self._plan = plan_comment

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="t", body="b", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        if self._plan:
            return [Comment(id=1, body=self._plan, user="bot")]
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=2, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


def _stub_ac_verifier(bus: Bus, results: list[dict[str, Any]]) -> None:
    """Stub the VerifyAC contract on the bus with a fixed AC-result list.
    Avoids importing the ac_verification slice (architecture rule)."""

    def _handle(_cmd: Command) -> dict[str, Any]:
        return {
            "verified": all(r.get("passed") for r in results) and bool(results),
            "total": len(results),
            "passed": sum(1 for r in results if r.get("passed")),
            "manual": 0,
            "results": results,
        }

    bus.register_command("VerifyAC", _handle)


class TestMapACResultsToCriteria:
    def test_all_passed_diff_only(self):
        results = [
            {"tag": "DIFF", "arg": "a.py", "passed": True},
            {"tag": "DIFF", "arg": "b.py", "passed": True},
        ]
        scores = map_ac_results_to_criteria(results)
        assert scores["syntax_valid"] == 1.0
        assert scores["hallucination_free"] == 1.0
        # No TEST/GREP claims → no failure → 1.0
        assert scores["test_pass_rate"] == 1.0
        assert scores["scope_compliant"] == 1.0

    def test_partial_diff_failures(self):
        results = [
            {"tag": "DIFF", "arg": "a.py", "passed": True},
            {"tag": "DIFF", "arg": "missing.py", "passed": False},
        ]
        scores = map_ac_results_to_criteria(results)
        assert scores["syntax_valid"] == 0.5
        assert scores["hallucination_free"] == 0.5

    def test_grep_maps_to_scope_compliant(self):
        results = [
            {"tag": "GREP", "arg": "foo", "passed": True},
            {"tag": "GREP:NOT", "arg": "bar", "passed": False},
        ]
        scores = map_ac_results_to_criteria(results)
        assert scores["scope_compliant"] == 0.5
        # GREP isn't a hallucination signal — only DIFF/EXISTS are
        assert scores["hallucination_free"] == 1.0

    def test_test_tag_maps_to_test_pass_rate(self):
        results = [
            {"tag": "TEST", "arg": "x", "passed": True},
            {"tag": "TEST", "arg": "y", "passed": True},
            {"tag": "TEST", "arg": "z", "passed": False},
        ]
        scores = map_ac_results_to_criteria(results)
        assert abs(scores["test_pass_rate"] - 2 / 3) < 1e-6

    def test_empty_results_all_one(self):
        scores = map_ac_results_to_criteria([])
        assert scores == {
            "syntax_valid": 1.0,
            "test_pass_rate": 1.0,
            "scope_compliant": 1.0,
            "hallucination_free": 1.0,
        }

    def test_unknown_tag_does_not_fault_any_family(self):
        """A tag we don't have a family for must not lower any score."""
        results = [{"tag": "WEIRD", "arg": "x", "passed": False}]
        scores = map_ac_results_to_criteria(results)
        assert all(v == 1.0 for v in scores.values())


class TestScoringHandler:
    def test_no_scm_blocks_with_reason(self):
        bus = Bus()
        events = _collect_events(bus)
        handler = ScoringHandler(bus, scm=None)

        result = handler.handle(ScoreCommand(payload={"issue": 42}))

        assert result["reason"] == "no_scm"
        assert result["criteria_scores"] == {}
        scored = next(e for e in events if e.name == "Scored")
        assert scored.payload["reason"] == "no_scm"
        assert scored.payload["criteria_scores"] == {}

    def test_no_plan_blocks_with_reason(self):
        bus = Bus()
        events = _collect_events(bus)
        handler = ScoringHandler(bus, scm=MockSCM(plan_comment=""))

        result = handler.handle(ScoreCommand(payload={"issue": 42}))

        assert result["reason"] == "no_plan_found"
        scored = next(e for e in events if e.name == "Scored")
        assert scored.payload["reason"] == "no_plan_found"

    def test_happy_path_produces_criteria_scores(self):
        plan = (
            "## Plan\n"
            "### Akzeptanzkriterien\n"
            "- [ ] [DIFF] real.py\n"
            "- [ ] [DIFF] missing.py\n"
        )
        bus = Bus()
        events = _collect_events(bus)
        _stub_ac_verifier(bus, [
            {"tag": "DIFF", "arg": "real.py", "passed": True},
            {"tag": "DIFF", "arg": "missing.py", "passed": False},
        ])
        handler = ScoringHandler(bus, scm=MockSCM(plan_comment=plan))

        result = handler.handle(ScoreCommand(payload={"issue": 42}))

        assert "criteria_scores" in result
        # 1 of 2 DIFF tags resolves → syntax_valid = hallucination_free = 0.5
        assert result["criteria_scores"]["syntax_valid"] == 0.5
        assert result["criteria_scores"]["hallucination_free"] == 0.5

        scored = next(e for e in events if e.name == "Scored")
        assert scored.payload["criteria_scores"]["syntax_valid"] == 0.5

    def test_carries_branch_and_base_through(self):
        plan = "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] real.py\n"
        bus = Bus()
        events = _collect_events(bus)
        _stub_ac_verifier(bus, [{"tag": "DIFF", "arg": "real.py", "passed": True}])
        handler = ScoringHandler(bus, scm=MockSCM(plan_comment=plan))

        handler.handle(ScoreCommand(payload={
            "issue": 42,
            "branch": "samuel/issue-42",
            "base": "main",
            "patches_applied": 3,
            "rounds": 2,
        }))

        scored = next(e for e in events if e.name == "Scored")
        assert scored.payload["branch"] == "samuel/issue-42"
        assert scored.payload["base"] == "main"
        assert scored.payload["patches_applied"] == 3
        assert scored.payload["rounds"] == 2

    def test_correlation_id_flows(self):
        plan = "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] real.py\n"
        bus = Bus()
        events = _collect_events(bus)
        _stub_ac_verifier(bus, [{"tag": "DIFF", "arg": "real.py", "passed": True}])
        handler = ScoringHandler(bus, scm=MockSCM(plan_comment=plan))

        handler.handle(ScoreCommand(
            payload={"issue": 42},
            correlation_id="score-corr-1",
        ))

        scored = next(e for e in events if e.name == "Scored")
        assert scored.correlation_id == "score-corr-1"

    def test_verify_ac_command_carries_issue_field(self):
        """#253: ScoringHandler muss issue im VerifyACCommand-Payload mitsenden,
        sonst publisht der AC-Verifier TestRunCompleted-Events ohne issue-Feld
        und das Dashboard kann sie nicht zuordnen."""
        plan = "## Plan\n### Akzeptanzkriterien\n- [ ] [TEST] some_test\n"
        bus = Bus()

        captured: dict[str, Any] = {}

        def _capture_handle(cmd: Command) -> dict[str, Any]:
            captured["payload"] = dict(cmd.payload)
            return {
                "verified": True, "total": 1, "passed": 1, "manual": 0,
                "results": [{"tag": "TEST", "arg": "some_test", "passed": True}],
            }

        bus.register_command("VerifyAC", _capture_handle)
        handler = ScoringHandler(bus, scm=MockSCM(plan_comment=plan))

        handler.handle(ScoreCommand(payload={"issue": 253}))

        assert "issue" in captured["payload"], (
            f"VerifyAC payload missing 'issue': {captured['payload']}"
        )
        assert captured["payload"]["issue"] == 253
        assert "plan_text" in captured["payload"]
