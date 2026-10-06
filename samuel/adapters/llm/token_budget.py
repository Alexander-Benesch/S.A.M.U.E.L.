from __future__ import annotations

from typing import Any

from samuel.adapters.llm.costs import get_model_reasoning_info
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class TokenBudgetLLMAdapter(ILLMProvider):
    """Apply the configured content and optional reasoning budget at runtime.

    ``content_max_tokens`` is the amount reserved for the visible answer.
    Reasoning-capable OpenRouter models may additionally receive an opt-in
    ``reasoning_reserve``.  OpenRouter counts both against ``max_tokens``, so
    the effective total is their sum.
    """

    def __init__(
        self,
        inner: ILLMProvider,
        *,
        provider: str,
        model: str | None,
        content_max_tokens: int | None,
        temperature: float | None,
        reasoning_reserve: int = 0,
    ) -> None:
        self._inner = inner
        self._provider = provider
        self._model = model or ""
        self._content_max_tokens = content_max_tokens
        self._temperature = temperature
        self._reasoning_reserve = max(0, int(reasoning_reserve or 0))

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        forwarded = dict(kwargs)
        explicit_max_tokens = forwarded.get("max_tokens")
        content_budget = (
            int(explicit_max_tokens)
            if explicit_max_tokens is not None
            else int(self._content_max_tokens)
            if self._content_max_tokens is not None
            else None
        )
        reasoning = get_model_reasoning_info(self._model)
        # A numeric reserve is an explicit OpenRouter control.  Other
        # providers do not share that request contract; merely increasing
        # max_tokens there would pretend to reserve reasoning while actually
        # only widening the generic output budget.
        reserve = (
            self._reasoning_reserve
            if reasoning["is_reasoning"] and self._provider == "openrouter"
            else 0
        )

        if content_budget is not None:
            forwarded["max_tokens"] = content_budget + reserve
            forwarded["content_max_tokens"] = content_budget
            forwarded["effective_max_tokens"] = content_budget + reserve
        if self._temperature is not None and "temperature" not in forwarded:
            forwarded["temperature"] = self._temperature
        forwarded["reasoning_model"] = reasoning["is_reasoning"]
        forwarded["reasoning_detection"] = reasoning["source"]
        forwarded["reasoning_reserve"] = reserve

        # OpenRouter's reasoning object is provider-specific.  Other adapters
        # still receive the correct total output budget without an unknown
        # request field.
        if reserve:
            forwarded["reasoning"] = {"max_tokens": reserve}

        return self._inner.complete(messages, **forwarded)

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)
