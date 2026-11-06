from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowContext:
    """Issue/run identity inherited by nested, synchronous workflow work."""

    issue_number: int
    correlation_id: str | None = None
    budget_admission_key: str | None = None


_workflow_context: ContextVar[WorkflowContext | None] = ContextVar(
    "samuel_workflow_context",
    default=None,
)


@contextmanager
def issue_scope(
    issue_number: int,
    correlation_id: str | None = None,
    budget_admission_key: str | None = None,
) -> Iterator[None]:
    """Bind issue and optional workflow correlation to the current context.

    Read by ``MeteringLLMAdapter`` to attach an ``issue`` field to
    ``LLMCallCompleted`` events.  A supplied correlation binds that telemetry
    to the existing workflow run; omitting it deliberately creates no such
    binding.
    """
    normalized_correlation = str(correlation_id).strip() if correlation_id else None
    normalized_budget_key = str(budget_admission_key).strip() if budget_admission_key else None
    token = _workflow_context.set(
        WorkflowContext(
            issue_number=issue_number,
            correlation_id=normalized_correlation or None,
            budget_admission_key=normalized_budget_key or None,
        )
    )
    try:
        yield
    finally:
        _workflow_context.reset(token)


def current_issue() -> int | None:
    context = _workflow_context.get()
    return context.issue_number if context is not None else None


def current_workflow_correlation() -> str | None:
    context = _workflow_context.get()
    return context.correlation_id if context is not None else None


def current_budget_admission() -> str | None:
    context = _workflow_context.get()
    return context.budget_admission_key if context is not None else None
