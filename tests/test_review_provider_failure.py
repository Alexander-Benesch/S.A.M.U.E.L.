from __future__ import annotations

from typing import Any

from samuel.adapters.llm.retry import RetryLLMAdapter
from samuel.core.bus import Bus, ErrorMiddleware
from samuel.core.config import load_workflow_config
from samuel.core.errors import ProviderUnavailable
from samuel.core.events import PRCreated
from samuel.core.types import LLMResponse
from samuel.core.workflow import WorkflowEngine
from samuel.slices.review.handler import ReviewHandler
from samuel.slices.review.tests.test_handler import MockLLM, MockSCM, _payload


class TransientReviewLLM(MockLLM):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        raise ProviderUnavailable(
            "openai_compatible",
            reason="raw provider detail sk-should-not-appear",
            category="provider_error",
            code="rate_limit",
            status=429,
            retryable=True,
        )


def test_exhausted_review_provider_blocks_bound_pr_without_aborting_workflow() -> None:
    bus = Bus()
    bus.add_middleware(ErrorMiddleware(bus))
    events: list[Any] = []
    bus.subscribe("*", events.append)
    scm = MockSCM()
    provider = TransientReviewLLM()
    review = ReviewHandler(
        bus,
        scm=scm,
        llm=RetryLLMAdapter(provider, max_attempts=3, base_delay_s=0, sleep_fn=lambda _: None),
    )
    bus.register_command("Review", review.handle)
    WorkflowEngine(bus, load_workflow_config("config", "standard"))
    payload = _payload(scm)

    bus.publish(PRCreated(payload=payload, correlation_id="review-run-42"))

    assert provider.calls == 3
    blocked = [event for event in events if event.name == "ReviewBlocked"]
    assert len(blocked) == 1
    assert blocked[0].correlation_id == "review-run-42"
    assert blocked[0].payload["issue"] == 42
    assert blocked[0].payload["pr_number"] == 12
    assert blocked[0].payload["evaluation_subject"] == payload["evaluation_subject"]
    assert blocked[0].payload["reason_code"] == "provider_unavailable"
    assert blocked[0].payload["provider_error"] == {
        "code": "rate_limit",
        "status": 429,
        "retryable": True,
    }
    assert not {"WorkflowAborted", "ReviewCompleted"} & {event.name for event in events}
    assert "sk-should-not-appear" not in str(blocked[0].payload)
    assert scm.posted == []
