from __future__ import annotations

import pytest

from samuel.core.errors import AgentAbort, GateFailed, ProviderUnavailable, SecurityViolation


def test_secret_gate_and_ineligible_healing_have_distinct_actionable_guidance():
    from samuel.core.errors import describe_diagnostic

    gate = describe_diagnostic(
        logger="",
        reason="assigned-secret@8",
        category="gates",
        event_name="GateFailed",
        gate="diff_secret_scan",
    )
    blocked = describe_diagnostic(
        logger="",
        reason="bound_healing:gate_11_not_failed",
        category="workflow",
        event_name="WorkflowBlocked",
    )
    assert "Secret" in gate["title"]
    assert "Secret-Referenz" in " ".join(gate["next_steps"])
    assert "Healing" in blocked["title"]
    assert "fehlgeschlagenes Gate 11 voraus" in blocked["cause"]
    assert "GateFailed" in " ".join(blocked["next_steps"])
    assert "abgelehnt" not in blocked["cause"]
    assert "Versuch beenden" in " ".join(blocked["next_steps"])


@pytest.mark.parametrize(
    "event_name",
    [
        "WorkflowBlocked",
        "WorkflowAborted",
        "PlanBlocked",
        "ReviewBlocked",
        "PRCreationFailed",
        "MergeOutcomeUnknown",
        "EvaluationSubjectInvalidated",
    ],
)
def test_unknown_workflow_stop_does_not_invent_gate_failure(event_name):
    from samuel.core.errors import describe_diagnostic

    result = describe_diagnostic(
        logger="", reason="unknown_reason", category="workflow", event_name=event_name
    )
    assert "nicht belegt" in result["cause"]
    assert "Logs" in " ".join(result["next_steps"])
    assert "neu planen" in " ".join(result["next_steps"])


def test_agent_abort():
    with pytest.raises(AgentAbort):
        raise AgentAbort("stopped")


def test_agent_abort_fields():
    exc = AgentAbort("halt", gate=5, issue=42)
    assert exc.gate == 5
    assert exc.issue == 42
    assert "halt" in str(exc)


def test_agent_abort_defaults():
    exc = AgentAbort("simple")
    assert exc.gate is None
    assert exc.issue is None


def test_security_violation():
    with pytest.raises(SecurityViolation):
        raise SecurityViolation("forbidden")


def test_gate_failed_fields():
    # #290: ASI08 cascading_failures statt A06 — Gate-Failure ist semantisch
    # ein Cascading-Failure-Signal (initialer Fehler propagiert weiter).
    exc = GateFailed(gate=3, reason="lint failed", owasp_risk="ASI08")
    assert exc.gate == 3
    assert exc.reason == "lint failed"
    assert exc.owasp_risk == "ASI08"
    assert "Gate 3 failed" in str(exc)


def test_gate_failed_string_gate():
    exc = GateFailed(gate="external:sonar", reason="quality")
    assert exc.gate == "external:sonar"
    assert exc.owasp_risk is None


def test_provider_unavailable_fields():
    exc = ProviderUnavailable(provider="anthropic", reason="rate limit")
    assert exc.provider == "anthropic"
    assert exc.reason == "rate limit"
    assert "anthropic" in str(exc)


def test_provider_unavailable_carries_bounded_classification_separate_from_reason():
    raw_reason = "raw provider payload with sk-test-secret"
    exc = ProviderUnavailable(
        provider="openai_compatible",
        reason=raw_reason,
        category="provider_error",
        code="429",
        status=429,
        retryable=True,
    )

    assert exc.category == "provider_error"
    assert exc.code == "429"
    assert exc.status == 429
    assert exc.retryable is True
    assert raw_reason not in exc.safe_message


def test_run_projection_diagnostic_identifies_operation_without_inventing_cause() -> None:
    from samuel.core.errors import describe_diagnostic

    result = describe_diagnostic(
        logger="samuel.core.bootstrap",
        reason="Runtime run-projection backfill failed",
        category="system",
        event_name="DiagnosticRaised",
    )
    assert "Run-Projektion" in result["title"]
    assert "Dashboard" in result["impact"]
    assert "Exceptionklasse" in result["cause"]
    assert "KeyError" not in result["cause"]


def test_complexity_warning_is_advisory_without_changing_gate_failure_guidance() -> None:
    from samuel.core.errors import describe_diagnostic

    warning = describe_diagnostic(
        logger="", reason="PlanComplexityWarn", category="plan", event_name="PlanComplexityWarn"
    )
    assert warning["title"] == "Hinweis zur Plan-Komplexität"
    assert "blockiert den Workflow nicht" in warning["impact"]
    assert "Required-Gates" in warning["impact"]
    failure = describe_diagnostic(
        logger="", reason="syntax rejected", category="gates", event_name="GateFailed"
    )
    assert failure["title"] == "Workflow-Prüfung nicht erfolgreich"
    assert "abgelehnt" in failure["cause"]


@pytest.mark.parametrize(
    "reason",
    [
        "system_prompt unreadable at config/llm/prompts/planner.md (PermissionError)",
        "system_prompt not found: planner.md",
        "system_prompt_by_provider value rejected for provider=test",
    ],
)
def test_prompt_configuration_diagnostic_does_not_claim_provider_call_failed(reason):
    from samuel.core.errors import describe_diagnostic

    result = describe_diagnostic(
        logger="samuel.adapters.llm.prompts", reason=reason, category="llm"
    )
    assert result["title"] == "Promptkonfiguration prüfen"
    assert result["problem_type"] == "configuration"
    assert "effektive Promptquelle" in " ".join(result["next_steps"])
    assert "Zugangsdaten testen" not in " ".join(result["next_steps"])
    provider = describe_diagnostic(
        logger="samuel.adapters.llm.openai_compat", reason="request failed", category="llm"
    )
    assert provider["title"] == "LLM-Aufruf fehlgeschlagen"
