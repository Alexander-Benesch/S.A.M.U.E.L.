from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from samuel.adapters.llm.metering import MeteringLLMAdapter
from samuel.adapters.llm.openai_compat import OpenAICompatAdapter
from samuel.adapters.llm.retry import RetryLLMAdapter
from samuel.core.bus import Bus
from samuel.core.commands import PlanIssueCommand
from samuel.core.ports import IVersionControl
from samuel.core.types import Issue
from samuel.slices.planning.handler import PlanningHandler


def test_missing_choices_reaches_correlated_terminal_planning_boundary() -> None:
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    scm = MagicMock(spec=IVersionControl)
    scm.get_issue.return_value = Issue(
        number=4,
        title="Golden path",
        body="- [ ] Produce a valid plan",
        state="open",
    )
    provider = OpenAICompatAdapter(
        api_key="configured",
        base_url="https://provider.invalid/v1",
        model="fixture-model",
    )
    metered = MeteringLLMAdapter(provider, bus=bus, provider_name="fixture-provider")
    llm = RetryLLMAdapter(metered, max_attempts=3, base_delay_s=0, sleep_fn=lambda _: None)
    handler = PlanningHandler(bus, scm=scm, llm=llm)

    with patch("samuel.adapters.llm.openai_compat.http_post", return_value={}) as http_post:
        result = handler.handle(
            PlanIssueCommand(issue_number=4, correlation_id="d0-golden-fixture-4")
        )

    assert result is None
    assert http_post.call_count == 1
    names = [event.name for event in events]
    assert "LLMCallCompleted" not in names
    assert "PlanCreated" not in names
    assert "LLMUnavailable" in names
    assert "PlanBlocked" in names
    unavailable = next(event for event in events if event.name == "LLMUnavailable")
    assert unavailable.correlation_id == "d0-golden-fixture-4"
    assert unavailable.payload["issue"] == 4
    assert unavailable.payload["task"] == "planning"
    assert unavailable.payload["error_category"] == "malformed_response"
    assert unavailable.payload["error_code"] == "missing_choices"
    assert unavailable.payload["retryable"] is False


def test_empty_truncated_response_reaches_planning_token_limit_boundary() -> None:
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    scm = MagicMock(spec=IVersionControl)
    scm.get_issue.return_value = Issue(
        number=32,
        title="Reasoning budget",
        body="- [ ] Produce a valid plan",
        state="open",
    )
    provider = OpenAICompatAdapter(
        api_key="configured",
        base_url="https://provider.invalid/v1",
        model="reasoning-model",
    )
    metered = MeteringLLMAdapter(provider, bus=bus, provider_name="fixture-provider")
    llm = RetryLLMAdapter(metered, max_attempts=3, base_delay_s=0, sleep_fn=lambda _: None)
    handler = PlanningHandler(bus, scm=scm, llm=llm)
    response = {
        "choices": [
            {
                "message": {"content": None, "reasoning_content": "must stay private"},
                "finish_reason": "length",
            }
        ],
        "usage": {
            "prompt_tokens": 2400,
            "completion_tokens": 4096,
            "completion_tokens_details": {"reasoning_tokens": 4096},
        },
        "model": "reasoning-model",
    }

    with patch("samuel.adapters.llm.openai_compat.http_post", return_value=response) as http_post:
        result = handler.handle(
            PlanIssueCommand(issue_number=32, correlation_id="d0-truncated-fixture-32")
        )

    assert result is None
    assert http_post.call_count == 1
    names = [event.name for event in events]
    assert "LLMCallCompleted" in names
    assert "TokenLimitHit" in names
    assert "PlanBlocked" in names
    assert "LLMUnavailable" not in names
    assert "PlanCreated" not in names
    completed = next(event for event in events if event.name == "LLMCallCompleted")
    assert completed.correlation_id == "d0-truncated-fixture-32"
    assert completed.payload["stop_reason"] == "length"
    assert completed.payload["output_tokens"] == 4096
    assert completed.payload["reasoning_tokens"] == 4096
    assert "must stay private" not in repr(events)
    assert any("llm_response_truncated" in call.args[1] for call in scm.post_comment.call_args_list)
