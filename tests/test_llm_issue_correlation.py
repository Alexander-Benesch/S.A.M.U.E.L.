"""Regression #206: end-to-end check that LLMCallCompleted events
carry an ``issue`` field when published from within a workflow handler.

Lives in tests/ rather than slices/planning/tests/ to keep the slice
boundary clean (slices may not import from samuel.adapters)."""
from __future__ import annotations

from typing import Any

from samuel.adapters.llm.metering import MeteringLLMAdapter
from samuel.core.bus import Bus
from samuel.core.commands import HealCommand, PlanIssueCommand, ReviewCommand
from samuel.core.ports import IConfig, ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse
from samuel.slices.healing.handler import HealingHandler
from samuel.slices.planning.handler import PlanningHandler
from samuel.slices.review.handler import ReviewHandler

GOOD_PLAN = """\
## Analyse
Änderung in `handler.py` Zeile 42.

### Akzeptanzkriterien
- [ ] [DIFF] handler.py — Handler geändert
- [ ] [TEST] test_handler — Tests grün
"""


class _MockSCM(IVersionControl):
    def __init__(self) -> None:
        self._issue = Issue(
            number=176, title="t", body="- [ ] AC1\n- [ ] AC2", state="open"
        )
        self.posted: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return self._issue

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted.append((number, body))
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class _FakeLLM(ILLMProvider):
    def __init__(self, text: str = GOOD_PLAN) -> None:
        self._text = text

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text=self._text,
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
            model_used="test",
            latency_ms=10,
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class _AlwaysOnConfig(IConfig):
    def get(self, key: str, default: Any = None) -> Any:
        return default

    def feature_flag(self, name: str) -> bool:
        return True

    def reload(self) -> None:
        pass


def _capture(bus: Bus) -> list:
    out: list = []
    bus.subscribe("LLMCallCompleted", lambda e: out.append(e))
    return out


def test_planning_handler_propagates_issue_to_llm_event():
    bus = Bus()
    metered = MeteringLLMAdapter(_FakeLLM(), bus=bus, provider_name="deepseek")
    handler = PlanningHandler(bus, scm=_MockSCM(), llm=metered)
    events = _capture(bus)

    handler.handle(PlanIssueCommand(issue_number=176))

    assert events, "expected LLMCallCompleted event(s)"
    for evt in events:
        assert evt.payload.get("issue") == 176


def test_review_handler_propagates_issue_to_llm_event():
    bus = Bus()
    metered = MeteringLLMAdapter(_FakeLLM("review"), bus=bus, provider_name="deepseek")
    handler = ReviewHandler(bus, scm=_MockSCM(), llm=metered)
    events = _capture(bus)

    handler.handle(ReviewCommand(payload={"issue": 99, "diff": "diff --git a b"}))

    assert events
    assert events[0].payload.get("issue") == 99


def test_healing_handler_propagates_issue_to_llm_event():
    bus = Bus()
    metered = MeteringLLMAdapter(_FakeLLM("heal"), bus=bus, provider_name="deepseek")
    handler = HealingHandler(bus, llm=metered, config=_AlwaysOnConfig())
    events = _capture(bus)

    handler.handle(HealCommand(payload={
        "issue": 55, "failure_type": "GateFailed", "attempt": 1, "context": {}
    }))

    assert events
    assert events[0].payload.get("issue") == 55


def test_event_outside_handler_has_no_issue():
    bus = Bus()
    metered = MeteringLLMAdapter(_FakeLLM(), bus=bus, provider_name="deepseek")
    events = _capture(bus)

    metered.complete([{"role": "user", "content": "hi"}])

    assert events
    assert "issue" not in events[0].payload


def test_planning_handler_sets_task_and_guards():
    bus = Bus()
    metered = MeteringLLMAdapter(_FakeLLM(), bus=bus, provider_name="deepseek")
    handler = PlanningHandler(bus, scm=_MockSCM(), llm=metered)
    events = _capture(bus)

    handler.handle(PlanIssueCommand(issue_number=176))

    assert events
    p = events[0].payload
    assert p["task"] == "planning"
    assert "prompt_guards" in p["guards"]
    assert "plan_validator" in p["guards"]


def test_review_handler_sets_task_and_guards():
    bus = Bus()
    metered = MeteringLLMAdapter(_FakeLLM("review"), bus=bus, provider_name="deepseek")
    handler = ReviewHandler(bus, scm=_MockSCM(), llm=metered)
    events = _capture(bus)

    handler.handle(ReviewCommand(payload={"issue": 99, "diff": "diff --git a b"}))

    assert events
    p = events[0].payload
    assert p["task"] == "review"
    assert p["guards"] == ["prompt_guards"]


def test_healing_handler_sets_task_and_guards():
    bus = Bus()
    metered = MeteringLLMAdapter(_FakeLLM("heal"), bus=bus, provider_name="deepseek")
    handler = HealingHandler(bus, llm=metered, config=_AlwaysOnConfig())
    events = _capture(bus)

    handler.handle(HealCommand(payload={
        "issue": 55, "failure_type": "GateFailed", "attempt": 1, "context": {}
    }))

    assert events
    p = events[0].payload
    assert p["task"] == "healing"
    assert "prompt_guards" in p["guards"]
    assert "healing_budget" in p["guards"]
