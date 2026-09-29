from __future__ import annotations

import pytest

from samuel.core.errors import AgentAbort, GateFailed, ProviderUnavailable, SecurityViolation


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
