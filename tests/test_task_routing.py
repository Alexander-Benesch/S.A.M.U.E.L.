"""#225: Tests for TaskRoutingLLMAdapter."""
from __future__ import annotations

from unittest.mock import MagicMock

from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
from samuel.core.types import LLMResponse


def _mock_adapter(label: str) -> MagicMock:
    m = MagicMock()
    m.complete.return_value = LLMResponse(
        text=f"from-{label}",
        input_tokens=10,
        output_tokens=5,
        cached_tokens=0,
        stop_reason="end_turn",
        model_used=label,
        latency_ms=1,
    )
    m.estimate_tokens.return_value = len(label)
    return m


def test_task_routing_dispatches_to_provider():
    default = _mock_adapter("default")
    claude = _mock_adapter("claude")
    deepseek = _mock_adapter("deepseek")

    router = TaskRoutingLLMAdapter(
        default=default,
        by_task={"planning": claude, "review": deepseek},
    )

    res = router.complete("prompt", task="planning")
    assert res.text == "from-claude"
    claude.complete.assert_called_once()
    default.complete.assert_not_called()


def test_task_routing_falls_back_to_default():
    default = _mock_adapter("default")
    claude = _mock_adapter("claude")

    router = TaskRoutingLLMAdapter(
        default=default,
        by_task={"planning": claude},
    )

    res = router.complete("prompt", task="unknown_task")
    assert res.text == "from-default"
    default.complete.assert_called_once()
    claude.complete.assert_not_called()


def test_task_routing_no_task_uses_default():
    default = _mock_adapter("default")
    claude = _mock_adapter("claude")

    router = TaskRoutingLLMAdapter(
        default=default,
        by_task={"planning": claude},
    )

    res = router.complete("prompt")  # no task=
    assert res.text == "from-default"


def test_task_routing_estimate_tokens_uses_default():
    default = _mock_adapter("default")
    claude = _mock_adapter("claude")

    router = TaskRoutingLLMAdapter(default=default, by_task={"planning": claude})
    assert router.estimate_tokens("hello") == len("default")
