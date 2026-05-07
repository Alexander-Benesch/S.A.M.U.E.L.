from __future__ import annotations

from typing import Any

from samuel.adapters.llm.metering import MeteringLLMAdapter
from samuel.core.bus import Bus
from samuel.core.events import LLMCallCompleted
from samuel.core.issue_context import issue_scope
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class FakeInner(ILLMProvider):
    def __init__(self, response: LLMResponse | None = None) -> None:
        self._response = response or LLMResponse(
            text="hello",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
            model_used="test-model",
            latency_ms=42,
        )
        self.calls: list[tuple[list[dict], dict]] = []

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls.append((messages, kwargs))
        return self._response

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class FakeBrokenInner(ILLMProvider):
    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        raise RuntimeError("inner failed")

    def estimate_tokens(self, text: str) -> int:
        return 0

    @property
    def context_window(self) -> int:
        return 1


def _capture_events(bus: Bus) -> list:
    captured: list = []
    bus.subscribe("LLMCallCompleted", lambda e: captured.append(e))
    return captured


class TestMeteringAdapter:
    def test_publishes_event_on_complete(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        adapter.complete([{"role": "user", "content": "hi"}], task="planning")

        assert len(events) == 1
        e = events[0]
        assert isinstance(e, LLMCallCompleted)
        assert e.payload["task"] == "planning"
        assert e.payload["provider"] == "test"
        assert e.payload["model"] == "test-model"
        assert e.payload["input_tokens"] == 100
        assert e.payload["output_tokens"] == 50
        assert e.payload["tokens"] == 150
        assert e.payload["latency_ms"] == 42

    def test_returns_inner_response(self):
        bus = Bus()
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")
        result = adapter.complete([{"role": "user", "content": "x"}])
        assert result.text == "hello"

    def test_default_task_is_default(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="claude")

        adapter.complete([{"role": "user", "content": "x"}])

        assert events[0].payload["task"] == "default"

    def test_publish_failure_does_not_break_complete(self):
        class BrokenBus:
            def publish(self, event: Any) -> None:
                raise RuntimeError("bus broke")

        adapter = MeteringLLMAdapter(FakeInner(), bus=BrokenBus(), provider_name="x")
        result = adapter.complete([{"role": "user", "content": "x"}])
        assert result.text == "hello"

    def test_inner_failure_propagates(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeBrokenInner(), bus=bus, provider_name="x")

        try:
            adapter.complete([{"role": "user", "content": "x"}])
        except RuntimeError as e:
            assert "inner failed" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
        assert events == []  # no event published when inner fails

    def test_context_window_delegates(self):
        bus = Bus()
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="x")
        assert adapter.context_window == 200_000

    def test_estimate_tokens_delegates(self):
        bus = Bus()
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="x")
        assert adapter.estimate_tokens("a" * 40) == 10

    def test_zero_cost_for_local_provider(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="ollama")

        adapter.complete([{"role": "user", "content": "x"}])

        assert events[0].payload["cost"] == 0.0

    def test_event_carries_issue_when_context_active(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        with issue_scope(176):
            adapter.complete([{"role": "user", "content": "x"}], task="planning")

        assert events[0].payload.get("issue") == 176

    def test_event_omits_issue_when_no_context(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        adapter.complete([{"role": "user", "content": "x"}])

        assert "issue" not in events[0].payload

    def test_nested_scope_uses_innermost_issue(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        with issue_scope(100):
            with issue_scope(200):
                adapter.complete([{"role": "user", "content": "x"}])
            adapter.complete([{"role": "user", "content": "y"}])

        assert events[0].payload["issue"] == 200
        assert events[1].payload["issue"] == 100

    def test_scope_resets_after_exit(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        with issue_scope(42):
            adapter.complete([{"role": "user", "content": "x"}])
        adapter.complete([{"role": "user", "content": "y"}])

        assert events[0].payload["issue"] == 42
        assert "issue" not in events[1].payload

    def test_metadata_kwargs_propagate_to_payload(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        adapter.complete(
            [{"role": "user", "content": "x"}],
            task="implementation",
            tools_loaded=["PythonASTBuilder", "TreeSitterTSBuilder"],
            context_sections=["skeleton", "grep", "constraints"],
            guards=["prompt_guards", "context_validator"],
            prompt_tokens_est=9950,
        )

        p = events[0].payload
        assert p["task"] == "implementation"
        assert p["tools_loaded"] == ["PythonASTBuilder", "TreeSitterTSBuilder"]
        assert p["context_sections"] == ["skeleton", "grep", "constraints"]
        assert p["guards"] == ["prompt_guards", "context_validator"]
        assert p["prompt_tokens_est"] == 9950

    def test_metadata_omitted_when_not_provided(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        adapter.complete([{"role": "user", "content": "x"}])

        p = events[0].payload
        assert "tools_loaded" not in p
        assert "context_sections" not in p
        assert "guards" not in p
        assert "prompt_tokens_est" not in p

    def test_empty_metadata_omitted(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        adapter.complete(
            [{"role": "user", "content": "x"}],
            tools_loaded=[],
            context_sections=[],
            guards=[],
            prompt_tokens_est=0,
        )

        p = events[0].payload
        assert "tools_loaded" not in p
        assert "context_sections" not in p
        assert "guards" not in p
        assert "prompt_tokens_est" not in p


class TestFactoryIntegrationWithBus:
    def test_bus_in_factory_wraps_with_metering(self):
        from unittest.mock import MagicMock

        from samuel.adapters.llm.factory import create_llm_adapter

        bus = Bus()

        config = MagicMock()
        # Isolated config_dir so the repo's defaults.json (which now has
        # per-task system_prompt overrides since #338-audit-fix-2) doesn't
        # force TaskRouting and break this default-chain assertion.
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "ollama",
            "agent.config_dir":     "/tmp/samuel-metering-tests-no-defaults",
        }.get(key, default)

        secrets = MagicMock()
        secrets.get.return_value = None

        adapter = create_llm_adapter(config, secrets, bus=bus)

        # Check the adapter chain: CircuitBreaker → Sanitizer → Metering → Ollama
        from samuel.adapters.llm.circuit_breaker import CircuitBreakerAdapter
        from samuel.adapters.llm.sanitizer import SanitizingLLMAdapter

        assert isinstance(adapter, CircuitBreakerAdapter)
        assert isinstance(adapter._inner, SanitizingLLMAdapter)
        # Metering should sit inside the sanitizer
        assert isinstance(adapter._inner._inner, MeteringLLMAdapter)

    def test_no_bus_skips_metering(self):
        from unittest.mock import MagicMock

        from samuel.adapters.llm.factory import create_llm_adapter

        config = MagicMock()
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "ollama",
            "agent.config_dir":     "/tmp/samuel-metering-tests-no-defaults",
        }.get(key, default)
        secrets = MagicMock()
        secrets.get.return_value = None

        adapter = create_llm_adapter(config, secrets)  # no bus
        # No MeteringLLMAdapter in the chain when bus is None
        from samuel.adapters.llm.ollama import OllamaAdapter

        assert isinstance(adapter._inner._inner, OllamaAdapter)
