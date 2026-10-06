"""Fail-closed cumulative token reservations for workflow LLM attempts."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from samuel.core.errors import ProviderUnavailable
from samuel.core.events import (
    LLMBudgetAttemptReserved,
    LLMBudgetAttemptSettled,
    LLMBudgetBlocked,
)
from samuel.core.issue_context import (
    current_budget_admission,
    current_issue,
    current_workflow_correlation,
)
from samuel.core.ports import IAuthorityStateStore, ILLMProvider
from samuel.core.state import (
    LLMBudgetAttemptRecord,
    StateStoreError,
    authority_event_binding,
)
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)

_logical_call_id: ContextVar[str | None] = ContextVar(
    "samuel_workflow_budget_logical_call",
    default=None,
)


@contextmanager
def logical_call_scope() -> Iterator[str]:
    existing = _logical_call_id.get()
    if existing:
        yield existing
        return
    value = str(uuid4())
    token = _logical_call_id.set(value)
    try:
        yield value
    finally:
        _logical_call_id.reset(token)


class LogicalCallLLMAdapter(ILLMProvider):
    """Keep one logical identity across all nested retry/fallback attempts."""

    def __init__(self, inner: ILLMProvider) -> None:
        self._inner = inner

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        with logical_call_scope():
            return self._inner.complete(messages, **kwargs)

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)


def _input_token_upper_bound(messages: list[dict]) -> int:
    """Conservative tokenizer-independent request bound.

    UTF-8 byte length bounds byte/subword tokenization of the exact final
    messages.  Per-message and request framing are added explicitly because
    providers tokenize role and separator markers that are not user text.
    """

    encoded = json.dumps(
        messages,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return max(1, len(encoded) + 32 * len(messages) + 64)


class WorkflowTokenBudgetLLMAdapter(ILLMProvider):
    """Reserve and settle one physical provider attempt in authority state."""

    def __init__(
        self,
        inner: ILLMProvider,
        *,
        authority_store: IAuthorityStateStore,
        provider: str,
        model: str,
        bus: Any | None = None,
    ) -> None:
        self._inner = inner
        self._authority = authority_store
        self._provider = provider
        self._model = model
        self._bus = bus

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def _publish(self, event: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event)

    def _binding(self, authority_epoch: int) -> dict[str, Any]:
        return authority_event_binding(
            self._authority.authority_status(),
            authority_epoch=authority_epoch,
        )

    def _blocked(self, issue: int, code: str, task: str) -> ProviderUnavailable:
        self._publish(
            LLMBudgetBlocked(
                correlation_id=current_workflow_correlation() or str(uuid4()),
                payload={
                    "issue": issue,
                    "provider": self._provider,
                    "model": self._model,
                    "task": task,
                    "reason": code,
                    "owasp_risk": "tool_misuse",
                },
            )
        )
        return ProviderUnavailable(
            self._provider,
            category="workflow_budget",
            code=code,
            retryable=False,
        )

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        issue = current_issue()
        admission_key = current_budget_admission()
        # Calls outside an issue workflow are diagnostic/operator probes and
        # do not claim a workflow budget.  Any issue-bound call must carry the
        # admission created before Planning.
        if issue is None:
            return self._inner.complete(messages, **kwargs)
        task = str(kwargs.get("task") or "default")
        if not admission_key:
            raise self._blocked(issue, "workflow_budget_admission_missing", task)
        try:
            admission = self._authority.get_budget_admission(admission_key)
        except StateStoreError as exc:
            raise self._blocked(issue, exc.code, task) from exc
        if admission is None or admission.issue_number != issue:
            raise self._blocked(issue, "workflow_budget_admission_mismatch", task)
        raw_output_bound = kwargs.get("max_tokens")
        if (
            isinstance(raw_output_bound, bool)
            or not isinstance(raw_output_bound, int)
            or raw_output_bound <= 0
        ):
            raise self._blocked(issue, "workflow_budget_output_bound_missing", task)
        logical_call_id = _logical_call_id.get()
        if not logical_call_id:
            raise self._blocked(issue, "workflow_budget_logical_call_missing", task)

        input_bound = _input_token_upper_bound(messages)
        output_bound = int(raw_output_bound)
        attempt = LLMBudgetAttemptRecord(
            attempt_key=f"llm-attempt:{uuid4()}",
            admission_key=admission_key,
            logical_call_id=logical_call_id,
            provider=self._provider,
            model=self._model,
            task=task,
            input_upper_bound=input_bound,
            output_upper_bound=output_bound,
            reserved_tokens=input_bound + output_bound,
        )
        try:
            reserved = self._authority.reserve_budget_attempt(attempt)
        except StateStoreError as exc:
            raise self._blocked(issue, exc.code, task) from exc
        self._publish(
            LLMBudgetAttemptReserved(
                correlation_id=current_workflow_correlation() or str(uuid4()),
                payload={
                    "issue": issue,
                    "attempt_key": attempt.attempt_key,
                    "logical_call_id": logical_call_id,
                    "provider": self._provider,
                    "model": self._model,
                    "task": task,
                    "input_upper_bound": input_bound,
                    "output_upper_bound": output_bound,
                    "reserved_tokens": attempt.reserved_tokens,
                    **self._binding(reserved.authority_epoch),
                },
            )
        )

        try:
            response = self._inner.complete(messages, **kwargs)
        except Exception as exc:
            # The transport boundary cannot prove that a failed call consumed
            # no tokens.  Preserve the complete reservation before any retry
            # or provider fallback is allowed to reserve again.
            try:
                unknown = self._authority.settle_budget_attempt(
                    attempt.attempt_key,
                    status="unknown",
                    actual_input_tokens=None,
                    actual_output_tokens=None,
                    outcome_code=f"exception:{type(exc).__name__}",
                )
                self._publish(
                    LLMBudgetAttemptSettled(
                        correlation_id=current_workflow_correlation() or str(uuid4()),
                        payload={
                            "issue": issue,
                            "attempt_key": attempt.attempt_key,
                            "provider": self._provider,
                            "task": task,
                            "status": "unknown",
                            "reserved_tokens": attempt.reserved_tokens,
                            **self._binding(unknown.authority_epoch),
                        },
                    )
                )
            except Exception:
                log.exception("Failed to persist unknown LLM budget outcome")
            raise

        known_usage = (
            response.usage_reported
            and isinstance(response.input_tokens, int)
            and not isinstance(response.input_tokens, bool)
            and response.input_tokens >= 0
            and isinstance(response.output_tokens, int)
            and not isinstance(response.output_tokens, bool)
            and response.output_tokens >= 0
            and response.input_tokens + response.output_tokens <= attempt.reserved_tokens
        )
        settlement_status = "settled" if known_usage else "unknown"
        outcome_code = (
            "usage_reported"
            if known_usage
            else "usage_bound_exceeded"
            if response.usage_reported
            else "usage_unreported"
        )
        try:
            settled = self._authority.settle_budget_attempt(
                attempt.attempt_key,
                status=settlement_status,
                actual_input_tokens=response.input_tokens if known_usage else None,
                actual_output_tokens=response.output_tokens if known_usage else None,
                outcome_code=outcome_code,
            )
        except StateStoreError as exc:
            raise self._blocked(issue, exc.code, task) from exc
        self._publish(
            LLMBudgetAttemptSettled(
                correlation_id=current_workflow_correlation() or str(uuid4()),
                payload={
                    "issue": issue,
                    "attempt_key": attempt.attempt_key,
                    "provider": self._provider,
                    "task": task,
                    "status": settlement_status,
                    "reserved_tokens": attempt.reserved_tokens,
                    "actual_tokens": (
                        response.input_tokens + response.output_tokens if known_usage else None
                    ),
                    "outcome_code": outcome_code,
                    **self._binding(settled.authority_epoch),
                },
            )
        )
        return response

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)
