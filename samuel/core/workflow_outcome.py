"""Authoritative reduction of workflow events to one run outcome.

The event classes and workflow profiles define which transitions can occur;
this module owns only the query-side reduction of their observable outcomes.
It deliberately excludes stage-local failures such as ``GateFailed`` and
``EvalFailed`` because the same correlated run may still heal and create a PR.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

WorkflowOutcomeStatus = Literal[
    "running",
    "manual_pending",
    "unbound",
    "blocked",
    "aborted",
    "pr_created",
    "reviewed",
    "merged",
    "evaluated",
]

BLOCKING_WORKFLOW_EVENTS = frozenset(
    {
        "PlanBlocked",
        "PlanReplanRejected",
        "LLMUnavailable",
        "WorkflowBlocked",
        "PRCreationFailed",
        "CandidateEvaluationFailed",
        "CandidateSubmissionRejected",
        "ProviderVerificationBlocked",
        "ReviewBlocked",
        "MergeOutcomeUnknown",
    }
)
ABORTING_WORKFLOW_EVENTS = frozenset({"WorkflowAborted"})
SUCCESSFUL_WORKFLOW_EVENTS = frozenset(
    {"PRCreated", "ReviewCompleted", "PRMerged", "CandidateEvaluationCompleted"}
)
REVOKING_WORKFLOW_EVENTS = frozenset({"EvaluationSubjectInvalidated"})
TERMINAL_WORKFLOW_EVENTS = frozenset(
    BLOCKING_WORKFLOW_EVENTS
    | ABORTING_WORKFLOW_EVENTS
    | SUCCESSFUL_WORKFLOW_EVENTS
    | REVOKING_WORKFLOW_EVENTS
)


@dataclass(frozen=True)
class WorkflowOutcome:
    status: WorkflowOutcomeStatus
    terminal_event: str | None = None

    @property
    def projection_status(self) -> str:
        if self.status in {"pr_created", "reviewed", "merged", "evaluated"}:
            return "complete"
        if self.status in {"blocked", "aborted"}:
            return "blocked"
        return self.status


def reduce_workflow_outcome(
    events: Iterable[tuple[str, Mapping[str, Any]]],
) -> WorkflowOutcome:
    """Reduce chronologically ordered event facts without delivery-order bias.

    Priority is semantic rather than last-delivery-wins:

    * subject invalidation revokes a previously successful subject;
    * a confirmed merge is the strongest non-revoked success;
    * an explicit workflow abort remains terminal;
    * a confirmed PR supersedes earlier recoverable/blocking observations;
    * otherwise the latest true blocking workflow event wins.

    A projection containing only legacy or explicitly unbound LLM telemetry is
    classified ``unbound``.  It remains inspectable state but is not a run.
    """

    facts = [(str(name), payload) for name, payload in events if str(name)]
    names = [name for name, _ in facts]
    if "EvaluationSubjectInvalidated" in names:
        return WorkflowOutcome("blocked", "EvaluationSubjectInvalidated")
    if "PRMerged" in names:
        return WorkflowOutcome("merged", "PRMerged")
    if "WorkflowAborted" in names:
        return WorkflowOutcome("aborted", "WorkflowAborted")
    for name, _payload in reversed(facts):
        if name in {"ReviewBlocked", "MergeOutcomeUnknown"}:
            return WorkflowOutcome("blocked", name)
    if "ReviewCompleted" in names:
        return WorkflowOutcome("reviewed", "ReviewCompleted")
    for name, payload in reversed(facts):
        if name == "PRCreated":
            if payload.get("review_required") is True:
                return WorkflowOutcome("running")
            return WorkflowOutcome("pr_created", "PRCreated")
    if "CandidateEvaluationCompleted" in names:
        return WorkflowOutcome("evaluated", "CandidateEvaluationCompleted")
    for name, _payload in reversed(facts):
        if name in BLOCKING_WORKFLOW_EVENTS:
            return WorkflowOutcome("blocked", name)
    if any(
        name == "GateEvaluationCompleted" and payload.get("manual_pending") is True
        for name, payload in facts
    ):
        return WorkflowOutcome("manual_pending")
    if facts and all(
        name == "LLMCallCompleted" and payload.get("workflow_correlation_bound") is not True
        for name, payload in facts
    ):
        return WorkflowOutcome("unbound")
    return WorkflowOutcome("running")
