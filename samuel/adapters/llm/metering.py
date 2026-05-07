from __future__ import annotations

import logging
from typing import Any

from samuel.adapters.llm.costs import estimate_cost
from samuel.core.events import LLMCallCompleted
from samuel.core.issue_context import current_issue
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)


class MeteringLLMAdapter(ILLMProvider):
    """Wraps an ILLMProvider to publish LLMCallCompleted events on every
    complete() call. Provides the data the dashboard / cost-tracking expects."""

    def __init__(
        self,
        inner: ILLMProvider,
        bus: Any,
        provider_name: str,
    ) -> None:
        self._inner = inner
        self._bus = bus
        self._provider = provider_name

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        response = self._inner.complete(messages, **kwargs)
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
            "tokens": response.input_tokens + response.output_tokens,
            "cost": cost,
            "latency_ms": response.latency_ms,
            "stop_reason": response.stop_reason,
        }
        issue = current_issue()
        if issue is not None:
            payload["issue"] = issue
        for field in ("tools_loaded", "context_sections", "guards", "prompt_tokens_est"):
            val = kwargs.get(field)
            if val:
                payload[field] = val
        try:
            self._bus.publish(LLMCallCompleted(payload=payload))
        except Exception:
            log.exception("Failed to publish LLMCallCompleted")
        return response

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)
