from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from typing import Any

import pytest

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


def test_activity_lifetime_is_bound_to_real_call_and_response() -> None:
    entered, release = Event(), Event()

    class BlockingInner(FakeInner):
        def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
            entered.set()
            assert release.wait(5)
            return super().complete(messages, **kwargs)

    adapter = MeteringLLMAdapter(BlockingInner(), Bus(), "deepseek", model_name="requested-model")

    def call() -> LLMResponse:
        with issue_scope(42, correlation_id="run-42"):
            return adapter.complete([{"role": "user", "content": "private prompt"}], task="review")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(call)
        try:
            assert entered.wait(5)
            row = adapter.call_activity_status()["calls"][0]
            assert (row["task"], row["provider"], row["model"]) == (
                "review",
                "deepseek",
                "requested-model",
            )
            assert (row["issue"], row["correlation_id"]) == (42, "run-42")
            assert row["model_source"] == "request"
            assert row["started_at"]
            row["task"] = "tampered"
            assert adapter.call_activity_status()["calls"][0]["task"] == "review"
        finally:
            release.set()
        assert future.result().text == "hello"
    result = adapter.call_activity_status()
    assert result["calls"] == []
    assert result["last_call"]["model"] == "test-model"
    assert result["last_call"]["model_source"] == "response"
    assert result["last_call"]["outcome"] == "response_received"
    assert "private prompt" not in str(result) and "hello" not in str(result)


def test_activity_failure_is_redacted_and_does_not_leave_running_call() -> None:
    class PrivateFailure(FakeBrokenInner):
        def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
            raise ValueError("private response and credential")

    adapter = MeteringLLMAdapter(PrivateFailure(), Bus(), "deepseek", model_name="requested")
    with pytest.raises(ValueError, match="private response"):
        adapter.complete([], task="planning")
    result = adapter.call_activity_status()
    assert result["calls"] == []
    assert result["last_call"]["outcome"] == "failed"
    assert result["last_call"]["error_class"] == "ValueError"
    assert result["last_call"]["model_source"] == "request"
    assert "private response" not in str(result) and "credential" not in str(result)


def test_parallel_call_lifetimes_do_not_clear_each_other() -> None:
    entered, release = Barrier(3), Event()

    class ParallelInner(FakeInner):
        def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
            entered.wait(timeout=5)
            assert release.wait(5)
            return super().complete(messages, **kwargs)

    adapter = MeteringLLMAdapter(ParallelInner(), Bus(), "deepseek", model_name="model")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(adapter.complete, [], task=task) for task in ("planning", "review")]
        try:
            entered.wait(timeout=5)
            calls = adapter.call_activity_status()["calls"]
            assert {c["task"] for c in calls} == {"planning", "review"}
            assert len({c["call_id"] for c in calls}) == 2
        finally:
            release.set()
        for future in futures:
            future.result()
    assert adapter.call_activity_status()["calls"] == []


def test_new_metering_instance_never_reuses_prior_activity() -> None:
    old = MeteringLLMAdapter(FakeInner(), Bus(), "deepseek")
    old.complete([], task="implementation")
    fresh = MeteringLLMAdapter(FakeInner(), Bus(), "deepseek")
    assert old.call_activity_status()["last_call"] is not None
    assert fresh.call_activity_status() == {"calls": [], "last_call": None}


def test_received_truncated_response_is_not_a_task_pass() -> None:
    adapter = MeteringLLMAdapter(
        FakeInner(
            LLMResponse(
                text="partial",
                input_tokens=1,
                output_tokens=2,
                stop_reason="length",
                model_used="m",
            )
        ),
        Bus(),
        "deepseek",
    )
    adapter.complete([], task="review")
    assert adapter.call_activity_status()["last_call"]["outcome"] == "truncated"


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
        assert events[0].payload["workflow_correlation_bound"] is False

    def test_event_inherits_bound_workflow_correlation(self):
        bus = Bus()
        events = _capture_events(bus)
        inner = FakeInner()
        adapter = MeteringLLMAdapter(inner, bus=bus, provider_name="test")

        with issue_scope(176, "workflow-run-176"):
            adapter.complete([{"role": "user", "content": "x"}], task="planning")

        assert events[0].correlation_id == "workflow-run-176"
        assert events[0].payload["issue"] == 176
        assert events[0].payload["workflow_correlation_bound"] is True
        assert "correlation_id" not in inner.calls[0][1]

    def test_event_omits_issue_when_no_context(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        adapter.complete([{"role": "user", "content": "x"}])

        assert "issue" not in events[0].payload
        assert events[0].payload["workflow_correlation_bound"] is False
        assert events[0].correlation_id

    def test_nested_scope_uses_innermost_issue(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        with issue_scope(100, "run-100"):
            with issue_scope(200, "run-200"):
                adapter.complete([{"role": "user", "content": "x"}])
            adapter.complete([{"role": "user", "content": "y"}])

        assert events[0].payload["issue"] == 200
        assert events[0].correlation_id == "run-200"
        assert events[1].payload["issue"] == 100
        assert events[1].correlation_id == "run-100"

    def test_scope_resets_after_exit(self):
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="test")

        with issue_scope(42, "run-42"):
            adapter.complete([{"role": "user", "content": "x"}])
        adapter.complete([{"role": "user", "content": "y"}])

        assert events[0].payload["issue"] == 42
        assert events[0].correlation_id == "run-42"
        assert "issue" not in events[1].payload
        assert events[1].payload["workflow_correlation_bound"] is False
        assert events[1].correlation_id != "run-42"

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

    def test_truncation_is_logged_with_budget_and_issue(self, caplog):
        response = LLMResponse(
            text="partial",
            input_tokens=10,
            output_tokens=4096,
            stop_reason="length",
            model_used="reasoner",
            reasoning_tokens=900,
        )
        bus = Bus()
        events = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(response), bus=bus, provider_name="openrouter")

        with caplog.at_level("WARNING"), issue_scope(427):
            adapter.complete(
                [],
                task="planning",
                content_max_tokens=4096,
                effective_max_tokens=5120,
                reasoning_model=True,
                reasoning_detection="openrouter_metadata",
                reasoning_reserve=1024,
            )

        assert "LLM response truncated" in caplog.text
        assert "issue=427" in caplog.text
        payload = events[0].payload
        assert payload["content_max_tokens"] == 4096
        assert payload["effective_max_tokens"] == 5120
        assert payload["reasoning_reserve"] == 1024
        assert payload["reasoning_tokens"] == 900

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
            "agent.config_dir": "/tmp/samuel-metering-tests-no-defaults",
        }.get(key, default)

        secrets = MagicMock()
        secrets.get.return_value = None

        adapter = create_llm_adapter(config, secrets, bus=bus)

        # Check the adapter chain: CircuitBreaker → Sanitizer → Metering → Ollama
        from samuel.adapters.llm.circuit_breaker import CircuitBreakerAdapter
        from samuel.adapters.llm.sanitizer import SanitizingLLMAdapter
        from samuel.adapters.llm.token_budget import TokenBudgetLLMAdapter

        assert isinstance(adapter, CircuitBreakerAdapter)
        assert isinstance(adapter._inner, SanitizingLLMAdapter)
        # Metering should sit inside the sanitizer
        assert isinstance(adapter._inner._inner, TokenBudgetLLMAdapter)
        assert isinstance(adapter._inner._inner._inner, MeteringLLMAdapter)

    def test_no_bus_skips_metering(self):
        from unittest.mock import MagicMock

        from samuel.adapters.llm.factory import create_llm_adapter

        config = MagicMock()
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "ollama",
            "agent.config_dir": "/tmp/samuel-metering-tests-no-defaults",
        }.get(key, default)
        secrets = MagicMock()
        secrets.get.return_value = None

        adapter = create_llm_adapter(config, secrets)  # no bus
        # No MeteringLLMAdapter in the chain when bus is None
        from samuel.adapters.llm.ollama import OllamaAdapter
        from samuel.adapters.llm.token_budget import TokenBudgetLLMAdapter

        assert isinstance(adapter._inner._inner, TokenBudgetLLMAdapter)
        assert isinstance(adapter._inner._inner._inner, OllamaAdapter)


class TestQualityLookup:
    """#153: quality_lookup haengt den historischen Score an LLMCallCompleted."""

    def test_quality_score_attached_when_lookup_returns_value(self):
        bus = Bus()
        captured = _capture_events(bus)
        adapter = MeteringLLMAdapter(
            FakeInner(),
            bus=bus,
            provider_name="deepseek",
            quality_lookup=lambda p, m, t: 0.873,
        )
        adapter.complete([{"role": "user", "content": "x"}], task="implementation")
        assert captured[0].payload["quality_score"] == 0.873

    def test_no_field_when_lookup_returns_none(self):
        bus = Bus()
        captured = _capture_events(bus)
        adapter = MeteringLLMAdapter(
            FakeInner(),
            bus=bus,
            provider_name="deepseek",
            quality_lookup=lambda p, m, t: None,
        )
        adapter.complete([{"role": "user", "content": "x"}], task="planning")
        assert "quality_score" not in captured[0].payload

    def test_no_field_without_lookup(self):
        bus = Bus()
        captured = _capture_events(bus)
        adapter = MeteringLLMAdapter(FakeInner(), bus=bus, provider_name="deepseek")
        adapter.complete([{"role": "user", "content": "x"}])
        assert "quality_score" not in captured[0].payload

    def test_lookup_exception_does_not_break_call(self):
        bus = Bus()
        captured = _capture_events(bus)

        def _boom(p, m, t):
            raise RuntimeError("lookup broke")

        adapter = MeteringLLMAdapter(
            FakeInner(),
            bus=bus,
            provider_name="deepseek",
            quality_lookup=_boom,
        )
        resp = adapter.complete([{"role": "user", "content": "x"}], task="impl")
        assert resp.text == "hello"
        assert "quality_score" not in captured[0].payload
