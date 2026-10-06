from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from samuel.core.bus import Bus
from samuel.core.config import load_workflow_config
from samuel.core.events import CodeGenerated, Event, IssueReady
from samuel.core.workflow import WorkflowEngine, plan_approval_required

APPROVAL_MODES = {"chat", "self", "standard", "watch"}
UNATTENDED_MODES = {"autonomous", "night", "patch"}


def test_shipped_workflows_distinguish_interactive_and_unattended_approval() -> None:
    workflows = Path("config/workflows")
    seen: set[str] = set()
    for path in workflows.glob("*.json"):
        definition = load_workflow_config(workflows.parent, path.stem)
        seen.add(path.stem)
        implement_triggers = {
            step["on"] for step in definition["steps"] if step.get("send") == "Implement"
        }
        if path.stem in APPROVAL_MODES:
            assert plan_approval_required(definition) is True
            assert "PlanApproved" in implement_triggers, path
            assert "PlanValidated" not in implement_triggers, path
        elif path.stem in UNATTENDED_MODES:
            assert plan_approval_required(definition) is False
            assert "PlanValidated" in implement_triggers, path
            assert "PlanApproved" in implement_triggers, path
            conditions = {
                (step["on"], step.get("condition"))
                for step in definition["steps"]
                if step.get("send") == "Implement"
            }
            assert ("PlanValidated", "plan_without_clarification") in conditions
            assert ("PlanApproved", "plan_with_clarification") in conditions
        else:
            raise AssertionError(f"Undocumented shipped workflow profile: {path.stem}")

    assert seen == APPROVAL_MODES | UNATTENDED_MODES


def test_every_shipped_workflow_dispatches_first_real_command() -> None:
    """Regression #466: workflow steps subscribe to events, never commands."""

    for name in sorted(APPROVAL_MODES | UNATTENDED_MODES):
        bus = Bus()
        planned: list[dict] = []

        def capture_plan(command: Any, target: list[dict] = planned) -> None:
            target.append(command.payload)

        bus.register_command("PlanIssue", capture_plan)
        WorkflowEngine(bus, load_workflow_config("config", name))

        bus.publish(IssueReady(payload={"issue": 466, "workflow": name}))

        assert planned == [{"issue": 466, "workflow": name}], name


def test_shipped_workflow_approval_gates_dispatch_as_documented() -> None:
    for name in sorted(APPROVAL_MODES | UNATTENDED_MODES):
        bus = Bus()
        implemented: list[dict] = []

        def capture_implementation(command: Any, target: list[dict] = implemented) -> None:
            target.append(command.payload)

        bus.register_command("Implement", capture_implementation)
        WorkflowEngine(bus, load_workflow_config("config", name))

        bus.publish(Event(name="PlanValidated", payload={"issue": 466}))
        if name in APPROVAL_MODES:
            assert implemented == [], name
            bus.publish(Event(name="PlanApproved", payload={"issue": 466}))
        else:
            assert implemented == [{"issue": 466}], name
            bus.publish(Event(name="PlanApproved", payload={"issue": 466}))

        assert implemented == [{"issue": 466}], name


def test_unattended_workflows_require_approval_only_for_clarified_plans() -> None:
    clarified_contract = {"clarification_basis": {"schema_version": 1}}
    for name in sorted(UNATTENDED_MODES):
        bus = Bus()
        implemented: list[dict] = []

        def capture_implementation(command: Any, target: list[dict] = implemented) -> None:
            target.append(command.payload)

        bus.register_command("Implement", capture_implementation)
        WorkflowEngine(bus, load_workflow_config("config", name))

        bus.publish(
            Event(
                name="PlanValidated",
                payload={"issue": 575, "acceptance_contract": clarified_contract},
            )
        )
        assert implemented == [], name

        bus.publish(
            Event(
                name="PlanApproved",
                payload={"issue": 575, "acceptance_contract": clarified_contract},
            )
        )
        assert implemented == [{"issue": 575, "acceptance_contract": clarified_contract}], name


def test_chat_workflow_reaches_create_pr_from_generated_candidate() -> None:
    bus = Bus()
    create_pr_payloads: list[dict] = []
    bus.register_command("CreatePR", lambda command: create_pr_payloads.append(command.payload))
    WorkflowEngine(bus, load_workflow_config("config", "chat"))

    bus.publish(CodeGenerated(payload={"issue": 467, "branch": "feat/467"}))

    assert create_pr_payloads == [{"issue": 467, "branch": "feat/467"}]


def test_shipped_workflows_have_no_legacy_authority_routes() -> None:
    for name in sorted(APPROVAL_MODES | UNATTENDED_MODES):
        document = _load_workflow(name)
        assert "legacy_steps" not in document
        routes = {(step["on"], step["send"]) for step in document["steps"]}
        assert ("CodeGenerated", "CreatePR") in routes
        assert not any(send in {"Score", "Evaluate", "Heal"} for _, send in routes)


def test_every_workflow_routes_one_evidence_healing_suggestion() -> None:
    for name in sorted(APPROVAL_MODES | UNATTENDED_MODES):
        definition = load_workflow_config("config", name)
        routes = [(step["on"], step["send"]) for step in definition["steps"]]
        assert routes.count(("HealingSuggested", "Implement")) == 1, name


def test_self_has_no_unbound_quality_or_score_authority() -> None:
    definition = load_workflow_config("config", "self")
    routes = {(step["on"], step["send"]) for step in definition["steps"]}
    assert ("CodeGenerated", "CreatePR") in routes
    assert not any(
        send in {"RunQuality", "Score", "Evaluate"} or condition == "self_parity_ok"
        for step in definition["steps"]
        for send, condition in [(step["send"], step.get("condition"))]
    )


def test_review_workflows_forward_pr_diff_to_review_command() -> None:
    for name in ("standard", "autonomous"):
        bus = Bus()
        review_payloads: list[dict] = []

        def capture_review(command: Any, target: list[dict] = review_payloads) -> None:
            target.append(command.payload)

        bus.register_command("Review", capture_review)
        WorkflowEngine(bus, load_workflow_config("config", name))

        bus.publish(
            Event(
                name="PRCreated",
                payload={"issue": 467, "pr_number": 12, "diff": "+safe change"},
            )
        )

        assert review_payloads == [{"issue": 467, "pr_number": 12, "diff": "+safe change"}], name


def test_workflow_dispatches_command():
    bus = Bus()
    results = []
    bus.register_command("PlanIssue", lambda c: results.append(c.payload))

    definition = {
        "steps": [{"on": "IssueReady", "send": "PlanIssue"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"number": 42}))
    assert len(results) == 1
    assert results[0]["number"] == 42


def test_workflow_unhandled_command():
    bus = Bus()
    unhandled = []
    bus.subscribe("UnhandledCommand", lambda e: unhandled.append(e))

    definition = {
        "steps": [{"on": "IssueReady", "send": "NonExistent"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={}))
    assert len(unhandled) == 1
    assert unhandled[0].payload["command"] == "NonExistent"


def test_workflow_condition_blocks():
    bus = Bus()
    results = []
    bus.register_command("PlanIssue", lambda c: results.append(1))

    definition = {
        "steps": [
            {
                "on": "IssueReady",
                "send": "PlanIssue",
                "condition": "payload.get('priority') == 'high'",
            }
        ],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"priority": "low"}))
    assert len(results) == 0


def test_workflow_condition_passes():
    bus = Bus()
    results = []
    bus.register_command("PlanIssue", lambda c: results.append(1))

    definition = {
        "steps": [
            {
                "on": "IssueReady",
                "send": "PlanIssue",
                "condition": "payload.get('priority') == 'high'",
            }
        ],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"priority": "high"}))
    assert len(results) == 1


def _load_workflow(name: str) -> dict[str, Any]:
    p = Path(__file__).parent.parent / "config" / "workflows" / f"{name}.json"
    return cast(dict[str, Any], json.loads(p.read_text()))


def test_standard_workflow_has_review_step():
    wf = _load_workflow("standard")
    triggers = {step["send"]: step["on"] for step in wf["steps"]}
    assert "Review" in triggers, "standard.json muss Review-Step enthalten (Issue #159)"
    assert triggers["Review"] == "PRCreated"


def test_autonomous_workflow_keeps_review_without_phantom_merge_contract():
    wf = _load_workflow("autonomous")
    sends = [step["send"] for step in wf["steps"]]
    assert "Review" in sends
    assert "MergePR" not in sends
    assert not any(step["on"] == "ReviewCompleted" for step in wf["steps"])
