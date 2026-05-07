"""Tests for SystemPromptInjectorAdapter (#338 Schicht B Wiring)."""
from __future__ import annotations

from typing import Any

from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class MockInner(ILLMProvider):
    """Records the messages it received in ``complete``."""

    def __init__(self) -> None:
        self.last_messages: list[dict] | None = None
        self.last_kwargs: dict[str, Any] = {}

    @property
    def context_window(self) -> int:
        return 1024

    @property
    def capabilities(self) -> set[str]:
        return {"chat"}

    def estimate_tokens(self, text: str) -> int:
        return len(text)

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.last_messages = list(messages)
        self.last_kwargs = kwargs
        return LLMResponse(text="ok", input_tokens=0, output_tokens=0)


class TestSystemPromptInjector:
    def test_prepends_system_message_when_caller_has_none(self) -> None:
        inner = MockInner()
        adapter = SystemPromptInjectorAdapter(inner, system_prompt="ROLE: planner")

        adapter.complete([{"role": "user", "content": "Hello"}])

        assert inner.last_messages == [
            {"role": "system", "content": "ROLE: planner"},
            {"role": "user", "content": "Hello"},
        ]

    def test_does_not_override_caller_system_message(self) -> None:
        """If the caller already prepended a system role, we trust them."""
        inner = MockInner()
        adapter = SystemPromptInjectorAdapter(inner, system_prompt="ROLE: planner")

        adapter.complete([
            {"role": "system", "content": "PLAN-CONTEXT"},
            {"role": "user", "content": "Hello"},
        ])

        # Caller's system message is preserved, ours is dropped.
        assert inner.last_messages == [
            {"role": "system", "content": "PLAN-CONTEXT"},
            {"role": "user", "content": "Hello"},
        ]

    def test_empty_prompt_is_passthrough(self) -> None:
        """Empty / whitespace-only system prompt -> no injection."""
        inner = MockInner()
        adapter = SystemPromptInjectorAdapter(inner, system_prompt="   ")
        msgs = [{"role": "user", "content": "Hello"}]

        adapter.complete(msgs)

        assert inner.last_messages == msgs

    def test_kwargs_propagate(self) -> None:
        inner = MockInner()
        adapter = SystemPromptInjectorAdapter(inner, system_prompt="X")

        adapter.complete(
            [{"role": "user", "content": "Hi"}],
            temperature=0.7, max_tokens=128,
        )

        assert inner.last_kwargs == {"temperature": 0.7, "max_tokens": 128}

    def test_context_window_and_capabilities_delegate(self) -> None:
        inner = MockInner()
        adapter = SystemPromptInjectorAdapter(inner, system_prompt="X")

        assert adapter.context_window == 1024
        assert adapter.capabilities == {"chat"}

    def test_estimate_tokens_delegates(self) -> None:
        inner = MockInner()
        adapter = SystemPromptInjectorAdapter(inner, system_prompt="X")

        assert adapter.estimate_tokens("hello") == 5

    def test_empty_messages_still_get_system_prepended(self) -> None:
        """Edge case: messages=[] — wrapper still injects."""
        inner = MockInner()
        adapter = SystemPromptInjectorAdapter(inner, system_prompt="ROLE: x")

        adapter.complete([])

        assert inner.last_messages == [{"role": "system", "content": "ROLE: x"}]
