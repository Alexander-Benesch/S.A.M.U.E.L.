from __future__ import annotations

import pytest

from samuel.core.types import (
    AuditQuery,
    GateContext,
    GateResult,
    HealCommand,
    LLMResponse,
    SCMActivity,
    SkeletonEntry,
    WorkflowCheckpoint,
    safe_float,
    safe_int,
    strip_html,
    validate_comment,
)


def test_llm_response_defaults():
    r = LLMResponse(text="hi", input_tokens=10, output_tokens=5)
    assert r.cached_tokens == 0
    assert r.stop_reason == "end_turn"
    assert r.model_used == ""
    assert r.latency_ms == 0


def test_scm_activity_timestamp_and_id_are_canonical():
    activity = SCMActivity(
        event="IssueClosed",
        number=42,
        timestamp="2026-08-21T12:00:00+02:00",
    )

    assert activity.timestamp == "2026-08-21T10:00:00Z"
    assert activity.activity_id == "IssueClosed:42:2026-08-21T10:00:00Z"


def test_gate_context():
    gc = GateContext(issue_number=1, branch="main", changed_files=["a.py"], diff="")
    assert gc.plan_comment is None
    assert gc.subject is None


def test_gate_result():
    gr = GateResult(gate=1, passed=True, reason="ok")
    assert gr.owasp_risk is None
    assert gr.executed is True
    assert gr.status == "passed"
    assert gr.reason_code == "gate_1_passed"


def test_gate_result_models_precondition_skip_without_pass_or_fail():
    gr = GateResult(
        gate=11,
        passed=None,
        executed=False,
        status="skipped_precondition",
        reason="preflight blocked",
    )

    assert gr.passed is None
    assert gr.executed is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"passed": None, "executed": True, "status": "skipped_precondition"},
        {"passed": False, "executed": False, "status": "skipped_precondition"},
        {"passed": None, "executed": False, "status": "failed"},
        {"passed": True, "executed": True, "status": "unknown"},
        {"passed": False, "executed": True, "status": "passed"},
        {"passed": True, "executed": True, "status": "failed"},
        {"passed": False, "executed": True, "status": "not_applicable"},
        {"passed": True, "executed": True, "status": "passed", "authority": "unknown"},
    ],
)
def test_gate_result_rejects_ambiguous_states(kwargs):
    with pytest.raises(ValueError):
        GateResult(gate=11, reason="invalid", **kwargs)


def test_audit_query_defaults():
    aq = AuditQuery()
    assert aq.limit == 100
    assert aq.issue is None


def test_skeleton_entry_defaults():
    se = SkeletonEntry(name="foo", kind="function", file="a.py", line_start=1, line_end=5)
    assert se.calls == []
    assert se.called_by == []
    assert se.language == ""


def test_heal_command():
    hc = HealCommand(issue=1, failure_type="test")
    assert hc.attempt == 1
    assert hc.context == {}


def test_workflow_checkpoint():
    wc = WorkflowCheckpoint(issue=1, phase="planning", step="llm_call_1")
    assert wc.state == {}


def test_safe_int():
    assert safe_int("42") == 42
    assert safe_int("nope") == 0
    assert safe_int(None, default=-1) == -1
    assert safe_int(3.9) == 3


def test_safe_float():
    assert safe_float("3.14") == 3.14
    assert safe_float("nope") == 0.0
    assert safe_float(None, default=-1.0) == -1.0


def test_strip_html_basic():
    assert strip_html("<b>bold</b>") == "bold"
    assert strip_html("no tags") == "no tags"
    assert strip_html("") == ""


def test_strip_html_entities():
    assert strip_html("&amp; &lt;") == "& <"


def test_strip_html_non_string():
    assert strip_html(None) == ""
    assert strip_html(42) == "42"


def test_validate_comment_pass():
    body = "## Analyse\ntext\n## Plan\ntext\n## Risiko\nlow"
    assert validate_comment(body, "plan") == []


def test_validate_comment_missing():
    body = "## Analyse\ntext"
    missing = validate_comment(body, "plan")
    assert "## Plan" in missing
    assert "## Risiko" in missing


def test_validate_comment_unknown_type():
    assert validate_comment("anything", "unknown_type") == []


def test_validate_comment_custom_fields():
    fields = {"custom": ["## Foo", "## Bar"]}
    assert validate_comment("## Foo\n## Bar", "custom", required_fields=fields) == []
    assert len(validate_comment("nope", "custom", required_fields=fields)) == 2
