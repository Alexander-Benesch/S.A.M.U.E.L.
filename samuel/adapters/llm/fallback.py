"""Ordered provider failover for LLM calls.

The adapter is deliberately provider-agnostic: each inner provider keeps its
own metering, model and prompt wrapper. A call only reaches the next provider
after the previous provider raised, so successful primary calls add no extra
network traffic or token cost.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from samuel.core.errors import ProviderUnavailable
from samuel.core.events import ProviderFallbackUsed
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)


class FallbackLLMAdapter(ILLMProvider):
    def __init__(
        self,
        providers: list[tuple[str, ILLMProvider]],
        *,
        on_fallback: Callable[[ProviderFallbackUsed], None] | None = None,
    ) -> None:
        if not providers:
            raise ValueError("at least one LLM provider is required")
        self._providers = list(providers)
        self._on_fallback = on_fallback

    @property
    def context_window(self) -> int:
        # A request eligible for fallback must fit every configured provider.
        return min(provider.context_window for _, provider in self._providers)

    @property
    def capabilities(self) -> set[str]:
        capabilities = [set(provider.capabilities) for _, provider in self._providers]
        return set.intersection(*capabilities) if capabilities else set()

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        last_error: Exception | None = None
        for index, (name, provider) in enumerate(self._providers):
            try:
                return provider.complete(messages, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if isinstance(exc, ProviderUnavailable) and exc.category == "workflow_budget":
                    raise
                if index == len(self._providers) - 1:
                    raise
                next_name = self._providers[index + 1][0]
                log.warning(
                    "LLM provider %s failed (%s); falling back to %s",
                    name,
                    type(exc).__name__,
                    next_name,
                )
                if self._on_fallback:
                    self._on_fallback(
                        ProviderFallbackUsed(
                            payload={
                                "from_provider": name,
                                "to_provider": next_name,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                                "task": kwargs.get("task", ""),
                            },
                            source="llm_fallback",
                        )
                    )
        assert last_error is not None
        raise last_error

    def estimate_tokens(self, text: str) -> int:
        return self._providers[0][1].estimate_tokens(text)
