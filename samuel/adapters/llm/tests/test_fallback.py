from __future__ import annotations

import pytest

from samuel.adapters.llm.fallback import FallbackLLMAdapter
from samuel.core.events import ProviderFallbackUsed
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class FakeProvider(ILLMProvider):
    def __init__(
        self,
        name: str,
        *,
        error: Exception | None = None,
        context_window: int = 100_000,
        capabilities: set[str] | None = None,
    ) -> None:
        self.name = name
        self.error = error
        self._context_window = context_window
        self._capabilities = capabilities or set()
        self.calls = 0

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        self.calls += 1
        if self.error:
            raise self.error
        return LLMResponse(text=self.name, input_tokens=1, output_tokens=1, model_used=self.name)

    def estimate_tokens(self, text: str) -> int:
        return len(text)

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def capabilities(self) -> set[str]:
        return set(self._capabilities)


def test_primary_success_does_not_call_fallback() -> None:
    primary = FakeProvider("primary")
    fallback = FakeProvider("fallback")
    adapter = FallbackLLMAdapter([("primary", primary), ("fallback", fallback)])

    response = adapter.complete([{"role": "user", "content": "hi"}])

    assert response.text == "primary"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_provider_error_uses_next_provider() -> None:
    primary = FakeProvider("primary", error=TimeoutError("down"))
    fallback = FakeProvider("fallback")
    adapter = FallbackLLMAdapter([("primary", primary), ("fallback", fallback)])

    response = adapter.complete([])

    assert response.text == "fallback"
    assert fallback.calls == 1


def test_fallback_publishes_existing_audit_event() -> None:
    events: list[ProviderFallbackUsed] = []
    adapter = FallbackLLMAdapter(
        [
            ("primary", FakeProvider("primary", error=TimeoutError("down"))),
            ("fallback", FakeProvider("fallback")),
        ],
        on_fallback=events.append,
    )

    adapter.complete([], task="planning")

    assert len(events) == 1
    assert events[0].name == "ProviderFallbackUsed"
    assert events[0].payload["from_provider"] == "primary"
    assert events[0].payload["to_provider"] == "fallback"
    assert events[0].payload["task"] == "planning"


def test_last_error_is_preserved_when_all_providers_fail() -> None:
    adapter = FallbackLLMAdapter(
        [
            ("one", FakeProvider("one", error=TimeoutError("one"))),
            ("two", FakeProvider("two", error=RuntimeError("two"))),
        ]
    )

    with pytest.raises(RuntimeError, match="two"):
        adapter.complete([])


def test_contract_uses_safe_shared_capabilities_and_context() -> None:
    adapter = FallbackLLMAdapter(
        [
            (
                "one",
                FakeProvider(
                    "one",
                    context_window=200_000,
                    capabilities={"structured_output", "tools"},
                ),
            ),
            (
                "two",
                FakeProvider("two", context_window=32_000, capabilities={"structured_output"}),
            ),
        ]
    )

    assert adapter.context_window == 32_000
    assert adapter.capabilities == {"structured_output"}
