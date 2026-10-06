from __future__ import annotations

import pytest

from samuel.core.workflow_outcome import (
    TERMINAL_WORKFLOW_EVENTS,
    reduce_workflow_outcome,
)


@pytest.mark.parametrize(
    ("event_name", "expected_status"),
    [
        ("PlanBlocked", "blocked"),
        ("PlanReplanRejected", "blocked"),
        ("LLMUnavailable", "blocked"),
        ("WorkflowBlocked", "blocked"),
        ("PRCreationFailed", "blocked"),
        ("WorkflowAborted", "aborted"),
        ("EvaluationSubjectInvalidated", "blocked"),
        ("CandidateEvaluationFailed", "blocked"),
        ("CandidateSubmissionRejected", "blocked"),
        ("ProviderVerificationBlocked", "blocked"),
        ("ReviewBlocked", "blocked"),
        ("MergeOutcomeUnknown", "blocked"),
        ("PRCreated", "pr_created"),
        ("ReviewCompleted", "reviewed"),
        ("PRMerged", "merged"),
        ("CandidateEvaluationCompleted", "evaluated"),
    ],
)
def test_declared_terminal_events_have_their_workflow_semantics(
    event_name: str,
    expected_status: str,
) -> None:
    outcome = reduce_workflow_outcome([(event_name, {})])

    assert event_name in TERMINAL_WORKFLOW_EVENTS
    assert outcome.status == expected_status
    assert outcome.terminal_event == event_name


def test_stage_failure_is_not_a_workflow_terminal() -> None:
    outcome = reduce_workflow_outcome(
        [
            ("GateFailed", {"gate": 11}),
            ("HealingAttemptStarted", {}),
        ]
    )

    assert outcome.status == "running"
    assert outcome.terminal_event is None


def test_pr_created_stays_running_until_required_review_finishes() -> None:
    pending = reduce_workflow_outcome([("PRCreated", {"review_required": True})])
    reviewed = reduce_workflow_outcome(
        [("PRCreated", {"review_required": True}), ("ReviewCompleted", {"decision": "pass"})]
    )

    assert pending.status == "running"
    assert pending.terminal_event is None
    assert reviewed.status == "reviewed"


def test_candidate_provider_wait_is_nonterminal() -> None:
    outcome = reduce_workflow_outcome(
        [("CandidateVerificationPending", {}), ("ProviderVerificationPending", {})]
    )

    assert "CandidateVerificationPending" not in TERMINAL_WORKFLOW_EVENTS
    assert "ProviderVerificationPending" not in TERMINAL_WORKFLOW_EVENTS
    assert outcome.status == "running"


def test_manual_acceptance_wait_is_nonterminal_and_true_block_remains_terminal() -> None:
    waiting = reduce_workflow_outcome(
        [("GateEvaluationCompleted", {"blocked": True, "manual_pending": True})]
    )
    blocked = reduce_workflow_outcome(
        [
            ("GateEvaluationCompleted", {"blocked": True, "manual_pending": True}),
            ("WorkflowBlocked", {"reason": "real_gate_failure"}),
        ]
    )

    assert waiting.status == "manual_pending"
    assert waiting.terminal_event is None
    assert blocked.status == "blocked"


def test_plan_revocation_is_nonterminal_until_replacement_plan_continues() -> None:
    outcome = reduce_workflow_outcome([("PlanRevoked", {})])

    assert "PlanRevoked" not in TERMINAL_WORKFLOW_EVENTS
    assert outcome.status == "running"
    assert outcome.terminal_event is None


def test_pr_success_supersedes_recoverable_block_but_invalidation_revokes_it() -> None:
    recovered = reduce_workflow_outcome(
        [("PlanBlocked", {}), ("PRCreated", {}), ("WorkflowBlocked", {})]
    )
    invalidated = reduce_workflow_outcome([("PRCreated", {}), ("EvaluationSubjectInvalidated", {})])

    assert recovered.status == "pr_created"
    assert invalidated == reduce_workflow_outcome(
        [("EvaluationSubjectInvalidated", {}), ("PRCreated", {})]
    )
    assert invalidated.status == "blocked"


def test_merge_supersedes_abort_but_not_subject_invalidation() -> None:
    assert reduce_workflow_outcome([("WorkflowAborted", {}), ("PRMerged", {})]).status == "merged"
    assert (
        reduce_workflow_outcome([("PRMerged", {}), ("EvaluationSubjectInvalidated", {})]).status
        == "blocked"
    )


@pytest.mark.parametrize("bound", [None, False])
def test_llm_only_legacy_or_explicitly_unbound_projection_is_not_a_run(
    bound: bool | None,
) -> None:
    payload = {} if bound is None else {"workflow_correlation_bound": bound}

    assert reduce_workflow_outcome([("LLMCallCompleted", payload)]).status == "unbound"


def test_bound_llm_only_projection_remains_running() -> None:
    outcome = reduce_workflow_outcome([("LLMCallCompleted", {"workflow_correlation_bound": True})])

    assert outcome.status == "running"
