"""#302: Tests for time-window routing."""
from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock

from samuel.adapters.llm.scheduled_routing import (
    ScheduledTaskRoutingAdapter,
    _schedule_active,
)
from samuel.core.types import LLMResponse


def _mock_adapter(label: str):
    m = MagicMock()
    m.complete.return_value = LLMResponse(
        text=f"from-{label}", input_tokens=1, output_tokens=1,
        cached_tokens=0, stop_reason="end_turn",
        model_used=label, latency_ms=1,
    )
    m.estimate_tokens.return_value = len(label)
    return m


# _schedule_active() tests
def test_schedule_active_within_window():
    sched = {"active": True, "from": "09:00", "to": "17:00", "provider": "x", "model": "y"}
    assert _schedule_active(sched, now=time(12, 0)) is True
    assert _schedule_active(sched, now=time(9, 0)) is True
    assert _schedule_active(sched, now=time(17, 0)) is True
    assert _schedule_active(sched, now=time(8, 59)) is False
    assert _schedule_active(sched, now=time(17, 1)) is False


def test_schedule_active_midnight_crossing():
    sched = {"active": True, "from": "22:00", "to": "06:00"}
    assert _schedule_active(sched, now=time(23, 30)) is True
    assert _schedule_active(sched, now=time(2, 0)) is True
    assert _schedule_active(sched, now=time(6, 0)) is True
    assert _schedule_active(sched, now=time(22, 0)) is True
    assert _schedule_active(sched, now=time(8, 0)) is False
    assert _schedule_active(sched, now=time(21, 59)) is False


def test_schedule_inactive_flag_false():
    sched = {"active": False, "from": "00:00", "to": "23:59"}
    assert _schedule_active(sched, now=time(12, 0)) is False


def test_schedule_invalid_time_format():
    assert _schedule_active({"active": True, "from": "abc", "to": "06:00"}) is False
    assert _schedule_active({"active": True, "from": "22:00"}) is False  # missing 'to'
    assert _schedule_active({}) is False
    assert _schedule_active(None) is False


def test_schedule_default_active_flag_is_true():
    """active defaults to True when omitted."""
    sched = {"from": "00:00", "to": "23:59"}
    assert _schedule_active(sched, now=time(12, 0)) is True


# ScheduledTaskRoutingAdapter tests
def test_scheduled_routing_uses_day_when_inactive(monkeypatch):
    day = _mock_adapter("day")
    night = _mock_adapter("night")
    default = _mock_adapter("default")

    # Force schedule-inactive by patching _schedule_active
    monkeypatch.setattr(
        "samuel.adapters.llm.scheduled_routing._schedule_active",
        lambda sched, now=None: False,
    )

    router = ScheduledTaskRoutingAdapter(
        default=default,
        by_task_day={"planning": day},
        by_task_night={"planning": night},
        schedules={"planning": {"from": "22:00", "to": "06:00", "provider": "claude", "model": "x"}},
    )
    res = router.complete("p", task="planning")
    assert res.text == "from-day"
    night.complete.assert_not_called()


def test_scheduled_routing_dispatches_to_night_when_active(monkeypatch):
    day = _mock_adapter("day")
    night = _mock_adapter("night")
    default = _mock_adapter("default")

    monkeypatch.setattr(
        "samuel.adapters.llm.scheduled_routing._schedule_active",
        lambda sched, now=None: True,
    )

    router = ScheduledTaskRoutingAdapter(
        default=default,
        by_task_day={"planning": day},
        by_task_night={"planning": night},
        schedules={"planning": {"from": "22:00", "to": "06:00", "provider": "claude", "model": "x"}},
    )
    res = router.complete("p", task="planning")
    assert res.text == "from-night"
    day.complete.assert_not_called()


def test_scheduled_routing_falls_back_to_default_for_unknown_task():
    default = _mock_adapter("default")
    router = ScheduledTaskRoutingAdapter(
        default=default,
        by_task_day={},
        by_task_night={},
        schedules={},
    )
    res = router.complete("p", task="unknown")
    assert res.text == "from-default"


def test_scheduled_routing_estimate_tokens_uses_default():
    default = _mock_adapter("default")
    router = ScheduledTaskRoutingAdapter(
        default=default, by_task_day={}, by_task_night={}, schedules={},
    )
    assert router.estimate_tokens("hello") == len("default")
