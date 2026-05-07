"""#302: Time-window routing fuer LLM-Tasks.

v1-Pendant: ``gitea-agent/plugins/llm.py:_schedule_active`` (commit 97c816d).

Premium-Feature ``llm_routing_advanced``. Free mode ignoriert ``schedule``-Bloecke
in der Task-Config (statisches Routing aus #301 bleibt aktiv).
"""
from __future__ import annotations

import logging
from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.schedule import schedule_active as _schedule_active
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)

# Re-exported for tests + adapters that imported from this module pre-#302-fix.
__all__ = ["ScheduledTaskRoutingAdapter", "_schedule_active"]


class ScheduledTaskRoutingAdapter:
    """#302: Picks per-task day or night provider depending on current time.

    Wraps an existing default + day-task-map + night-task-map. On ``complete``,
    looks up the schedule for ``task=`` and routes to the night-adapter when
    active, else day-adapter, else default. Premium-only — Factory only builds
    this when ``is_premium_active()`` and ``has_feature("llm_routing_advanced")``.
    """

    def __init__(
        self,
        default: ILLMProvider,
        by_task_day: dict[str, ILLMProvider],
        by_task_night: dict[str, ILLMProvider],
        schedules: dict[str, dict],
    ) -> None:
        self._default = default
        self._day = dict(by_task_day)
        self._night = dict(by_task_night)
        self._schedules = dict(schedules)

    def complete(
        self,
        prompt: Any,
        *,
        task: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        adapter: ILLMProvider
        if task and task in self._schedules and _schedule_active(self._schedules[task]):
            adapter = self._night.get(task) or self._day.get(task) or self._default
            log.debug("Schedule: task=%s on night-route", task)
        else:
            adapter = self._day.get(task or "", self._default)
        return adapter.complete(prompt, task=task, **kwargs)

    def estimate_tokens(self, text: str) -> int:
        return self._default.estimate_tokens(text)
