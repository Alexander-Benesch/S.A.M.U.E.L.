from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_issue_context: ContextVar[int | None] = ContextVar(
    "samuel_issue_context", default=None
)


@contextmanager
def issue_scope(issue_number: int) -> Iterator[None]:
    """Bind an issue number to the current execution context.

    Read by ``MeteringLLMAdapter`` to attach an ``issue`` field to
    ``LLMCallCompleted`` events so the dashboard can correlate token/cost
    usage to a specific workflow issue.
    """
    token = _issue_context.set(issue_number)
    try:
        yield
    finally:
        _issue_context.reset(token)


def current_issue() -> int | None:
    return _issue_context.get()
