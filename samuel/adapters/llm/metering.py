from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from samuel.adapters.llm.costs import estimate_cost
from samuel.core.events import LLMCallCompleted
from samuel.core.issue_context import current_issue, current_workflow_correlation
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse, is_truncated_stop_reason

log = logging.getLogger(__name__)


class MeteringLLMAdapter(ILLMProvider):
    """Wraps an ILLMProvider to publish LLMCallCompleted events on every
    complete() call. Provides the data the dashboard / cost-tracking expects."""

    def __init__(
        self,
        inner: ILLMProvider,
        bus: Any,
        provider_name: str,
        quality_lookup: Any = None,
        *,
        model_name: str = "",
    ) -> None:
        self._inner = inner
        self._bus = bus
        self._provider = provider_name
        self._model = model_name
        self._activity_lock = Lock()
        self._active_calls: dict[str, dict[str, Any]] = {}
        self._last_call: dict[str, Any] | None = None
        # #153: optionaler Callable (provider, model, task) -> float|None. Liefert
        # den historischen Rolling-Quality-Score und reichert LLMCallCompleted
        # damit an (Hook nach complete). None -> Feld wird weggelassen.
        self._quality_lookup = quality_lookup

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def call_activity_status(self) -> dict[str, Any]:
        """Process-local physical calls, independent of persistent budget state."""
        with self._activity_lock:
            return {
                "calls": [dict(call) for call in self._active_calls.values()],
                "last_call": dict(self._last_call) if self._last_call else None,
            }

    def _finish_call(
        self, call_id: str, *, outcome: str, model: str = "", error_class: str = ""
    ) -> None:
        with self._activity_lock:
            call = self._active_calls.pop(call_id)
            self._last_call = {
                **call,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "outcome": outcome,
                "model": model or call["model"],
                "model_source": "response" if model else "request",
                "error_class": error_class,
            }

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        call_id = uuid4().hex
        with self._activity_lock:
            self._active_calls[call_id] = {
                "call_id": call_id,
                "task": kwargs.get("task") or "default",
                "provider": self._provider,
                "model": self._model,
                "model_source": "request",
                "issue": current_issue(),
                "correlation_id": current_workflow_correlation(),
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        try:
            response = self._inner.complete(messages, **kwargs)
        except BaseException as exc:
            self._finish_call(call_id, outcome="failed", error_class=type(exc).__name__)
            raise
        self._finish_call(
            call_id,
            outcome="truncated"
            if is_truncated_stop_reason(response.stop_reason)
            else "response_received",
            model=response.model_used,
        )
        try:
            cost = estimate_cost(
                self._provider,
                response.model_used or kwargs.get("model", ""),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cached_tokens=response.cached_tokens,
            )
        except Exception:
            log.exception("estimate_cost failed")
            cost = 0.0
        payload: dict[str, Any] = {
            "task": kwargs.get("task", "default"),
            "provider": self._provider,
            "model": response.model_used,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cached_tokens": response.cached_tokens,
            "reasoning_tokens": response.reasoning_tokens,
            "tokens": response.input_tokens + response.output_tokens,
            "usage_reported": response.usage_reported,
            "cost": cost,
            "latency_ms": response.latency_ms,
            "stop_reason": response.stop_reason,
        }
        for field in (
            "content_max_tokens",
            "effective_max_tokens",
            "reasoning_model",
            "reasoning_detection",
            "reasoning_reserve",
        ):
            if field in kwargs:
                payload[field] = kwargs[field]
        issue = current_issue()
        workflow_correlation = current_workflow_correlation()
        if issue is not None:
            payload["issue"] = issue
        payload["workflow_correlation_bound"] = workflow_correlation is not None
        for field in ("tools_loaded", "context_sections", "guards", "prompt_tokens_est"):
            val = kwargs.get(field)
            if val:
                payload[field] = val
        # #153: historischen Quality-Score des (provider, model, task) anhaengen.
        if self._quality_lookup is not None:
            try:
                qs = self._quality_lookup(
                    self._provider,
                    response.model_used,
                    payload["task"],
                )
                if isinstance(qs, (int, float)):
                    payload["quality_score"] = round(float(qs), 4)
            except Exception:
                log.exception("quality_lookup failed")
        try:
            event = (
                LLMCallCompleted(payload=payload, correlation_id=workflow_correlation)
                if workflow_correlation is not None
                else LLMCallCompleted(payload=payload)
            )
            self._bus.publish(event)
        except Exception:
            log.exception("Failed to publish LLMCallCompleted")
        if is_truncated_stop_reason(response.stop_reason):
            log.warning(
                "LLM response truncated: task=%s provider=%s model=%s issue=%s "
                "stop_reason=%s content_max_tokens=%s reasoning_reserve=%s",
                payload["task"],
                self._provider,
                response.model_used,
                issue if issue is not None else "-",
                response.stop_reason,
                payload.get("content_max_tokens", "-"),
                payload.get("reasoning_reserve", 0),
            )
        return response

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)
