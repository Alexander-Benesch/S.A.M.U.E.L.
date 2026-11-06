from __future__ import annotations

from typing import Any

from samuel.adapters.llm import costs
from samuel.adapters.llm.token_budget import TokenBudgetLLMAdapter
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse, is_truncated_stop_reason


class RecordingLLM(ILLMProvider):
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.kwargs = kwargs
        return LLMResponse(text="ok", input_tokens=1, output_tokens=1)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 128_000


def _fresh_cache(entries: dict | None = None) -> None:
    import time

    costs._or_cache = entries or {}
    costs._or_cache_ts = time.time()


def test_applies_content_budget_and_temperature() -> None:
    _fresh_cache()
    inner = RecordingLLM()
    adapter = TokenBudgetLLMAdapter(
        inner,
        provider="ollama",
        model="llama3",
        content_max_tokens=8192,
        temperature=0.1,
    )

    adapter.complete([], task="implementation")

    assert inner.kwargs["max_tokens"] == 8192
    assert inner.kwargs["content_max_tokens"] == 8192
    assert inner.kwargs["temperature"] == 0.1
    assert inner.kwargs["reasoning_reserve"] == 0


def test_openrouter_reasoning_reserve_is_added_to_content_budget() -> None:
    _fresh_cache()
    inner = RecordingLLM()
    adapter = TokenBudgetLLMAdapter(
        inner,
        provider="openrouter",
        model="nvidia/nemotron-3-super",
        content_max_tokens=4096,
        temperature=0.3,
        reasoning_reserve=2048,
    )

    adapter.complete([], task="planning")

    assert inner.kwargs["max_tokens"] == 6144
    assert inner.kwargs["content_max_tokens"] == 4096
    assert inner.kwargs["reasoning"] == {"max_tokens": 2048}
    assert inner.kwargs["reasoning_model"] is True


def test_metadata_is_authoritative_over_name_heuristic() -> None:
    _fresh_cache(
        {
            "nvidia/nemotron-plain": {
                "reasoning": {},
                "prompt": 0,
                "completion": 0,
            }
        }
    )
    inner = RecordingLLM()
    adapter = TokenBudgetLLMAdapter(
        inner,
        provider="openrouter",
        model="nvidia/nemotron-plain",
        content_max_tokens=1000,
        temperature=None,
        reasoning_reserve=500,
    )

    adapter.complete([])

    assert inner.kwargs["max_tokens"] == 1000
    assert inner.kwargs["reasoning_reserve"] == 0
    assert "reasoning" not in inner.kwargs
    assert inner.kwargs["reasoning_detection"] == "openrouter_metadata"


def test_explicit_content_budget_still_keeps_reasoning_reserve_separate() -> None:
    _fresh_cache()
    inner = RecordingLLM()
    adapter = TokenBudgetLLMAdapter(
        inner,
        provider="openrouter",
        model="deepseek/deepseek-r1",
        content_max_tokens=4096,
        temperature=0.2,
        reasoning_reserve=1000,
    )

    adapter.complete([], max_tokens=2000)

    assert inner.kwargs["content_max_tokens"] == 2000
    assert inner.kwargs["max_tokens"] == 3000


def test_non_openrouter_provider_does_not_pretend_to_reserve_reasoning() -> None:
    _fresh_cache()
    inner = RecordingLLM()
    adapter = TokenBudgetLLMAdapter(
        inner,
        provider="openai",
        model="o3",
        content_max_tokens=2000,
        temperature=None,
        reasoning_reserve=1000,
    )

    adapter.complete([])

    assert inner.kwargs["max_tokens"] == 2000
    assert inner.kwargs["reasoning_reserve"] == 0
    assert "reasoning" not in inner.kwargs


def test_truncation_stop_reasons_are_provider_independent() -> None:
    assert is_truncated_stop_reason("length")
    assert is_truncated_stop_reason("max_tokens")
    assert is_truncated_stop_reason("token_limit")
    assert not is_truncated_stop_reason("stop")
