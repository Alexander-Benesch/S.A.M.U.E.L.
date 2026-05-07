from __future__ import annotations

import json
from pathlib import Path

from samuel.core.bus import Bus
from samuel.core.events import EvalCompleted, IssueReady
from samuel.core.workflow import WorkflowEngine


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
        "steps": [{"on": "IssueReady", "send": "PlanIssue", "condition": "payload.get('priority') == 'high'"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"priority": "low"}))
    assert len(results) == 0


def test_workflow_condition_passes():
    bus = Bus()
    results = []
    bus.register_command("PlanIssue", lambda c: results.append(1))

    definition = {
        "steps": [{"on": "IssueReady", "send": "PlanIssue", "condition": "payload.get('priority') == 'high'"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(IssueReady(payload={"priority": "high"}))
    assert len(results) == 1


def test_builtin_condition_self_parity_ok_passes():
    """#271: Condition liest payload.score (matcht EvalCompleted-Schema)."""
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(c.payload))

    definition = {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(EvalCompleted(payload={"issue": 42, "score": 0.8, "branch": "samuel/issue-42"}))
    assert len(results) == 1
    assert results[0]["branch"] == "samuel/issue-42"


def test_builtin_condition_self_parity_ok_blocks():
    """#271: Score unter 0.6 → CreatePR wird NICHT getriggert."""
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))

    definition = {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(EvalCompleted(payload={"issue": 42, "score": 0.3}))
    assert len(results) == 0


def test_builtin_condition_self_parity_ok_missing_score():
    """#271: Fehlendes score-Feld → graceful False, kein Crash."""
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))

    definition = {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    }
    WorkflowEngine(bus, definition)
    bus.publish(EvalCompleted(payload={"issue": 42}))
    assert len(results) == 0


def test_self_parity_ok_with_real_eval_completed_payload():
    """#271: End-to-end mit Payload-Struktur wie sie EvalCompleted in Production
    publisht (siehe samuel/slices/evaluation/handler.py). Vorher schlug die
    Condition mit `payload.get('eval_score')` fehl — `eval_score` existiert
    nicht im echten Payload, nur `score`."""
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(c.payload))

    definition = {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    }
    WorkflowEngine(bus, definition)
    # Payload-Struktur exakt wie in #236-Self-Mode-Run-Log gesehen
    bus.publish(EvalCompleted(payload={
        "issue": 236,
        "score": 0.8875,
        "baseline": 0.8875,
        "criteria": {"syntax_valid": 0.875, "test_pass_rate": 0.833},
        "branch": "samuel/issue-236",
        "patches_applied": 20,
        "rounds": 3,
    }))
    assert len(results) == 1, "CreatePR sollte mit score=0.8875 getriggert werden"
    assert results[0]["score"] == 0.8875


def test_self_parity_ok_threshold_boundary():
    """#271: Genau 0.6 → True (>= 0.6)."""
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))
    WorkflowEngine(bus, {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    })
    bus.publish(EvalCompleted(payload={"issue": 1, "score": 0.6}))
    assert len(results) == 1


def test_self_parity_ok_just_below_threshold():
    """#271: 0.59 → False."""
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))
    WorkflowEngine(bus, {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    })
    bus.publish(EvalCompleted(payload={"issue": 1, "score": 0.59}))
    assert len(results) == 0


def test_self_parity_ok_blocks_when_zero_acs_verified():
    """#285: AC-Verifier-Crash darf nicht still als 'parity_ok' durchgehen.

    Reproduktion #280-Run: Verifier crashte, results=[], criteria_scores wurden
    zu 1.0-Defaults, score landete >= 0.6, CreatePR feuerte trotzdem.
    """
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))
    WorkflowEngine(bus, {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    })
    bus.publish(EvalCompleted(payload={
        "issue": 280, "score": 1.0,
        "ac_total": 5, "ac_verified": 0,
    }))
    assert len(results) == 0, "Hartstop bei 0 ACs verified erwartet"


def test_self_parity_ok_passes_when_majority_verified():
    """#285: einzelne fehlgeschlagene ACs blocken nicht — Score-Schwelle bleibt zustaendig."""
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))
    WorkflowEngine(bus, {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    })
    bus.publish(EvalCompleted(payload={
        "issue": 1, "score": 0.9,
        "ac_total": 5, "ac_verified": 4,
    }))
    assert len(results) == 1


def test_self_parity_ok_passes_when_no_acs():
    """#285: Backward-Compat — Plan ohne ACs (ac_total=0) bleibt unbeeindruckt.

    Auch fuer Events ohne ac_total/ac_verified-Felder (alte Module): Default 0
    haelt graceful, score-Schwelle entscheidet.
    """
    bus = Bus()
    results = []
    bus.register_command("CreatePR", lambda c: results.append(1))
    WorkflowEngine(bus, {
        "steps": [{"on": "EvalCompleted", "send": "CreatePR", "condition": "self_parity_ok"}],
    })
    bus.publish(EvalCompleted(payload={"issue": 1, "score": 1.0}))
    assert len(results) == 1, "Ohne ac_total bleibt Backward-Compat"


def _load_workflow(name: str) -> dict:
    p = Path(__file__).parent.parent / "config" / "workflows" / f"{name}.json"
    return json.loads(p.read_text())


def test_standard_workflow_has_review_step():
    wf = _load_workflow("standard")
    triggers = {step["send"]: step["on"] for step in wf["steps"]}
    assert "Review" in triggers, "standard.json muss Review-Step enthalten (Issue #159)"
    assert triggers["Review"] == "PRCreated"


def test_autonomous_workflow_keeps_review_and_merge():
    wf = _load_workflow("autonomous")
    sends = [step["send"] for step in wf["steps"]]
    assert "Review" in sends
    assert "MergePR" in sends