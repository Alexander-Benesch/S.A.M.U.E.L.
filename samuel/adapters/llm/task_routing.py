"""#225: TaskRoutingLLMAdapter — dispatches LLM calls to per-task providers.

Wraps multiple inner adapters (one per task family) plus a default. Reads the
``task=`` kwarg from ``complete()``, routes to the matching provider, and falls
back to default for unknown or missing tasks. It is configured through the
general LLM defaults path.
"""

from __future__ import annotations

import logging
from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)


class TaskRoutingLLMAdapter(ILLMProvider):
    """Dispatcher: looks at ``task=`` kwarg, picks the right inner adapter."""

    def __init__(
        self,
        default: ILLMProvider,
        by_task: dict[str, ILLMProvider],
    ) -> None:
        self._default = default
        self._by_task = dict(by_task)

    def complete(
        self,
        messages: list[dict],
        *,
        task: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        adapter = self._by_task.get(task or "", self._default)
        if adapter is self._default and task and task not in self._by_task:
            log.debug("TaskRouting: no override for task=%s, using default", task)
        return adapter.complete(messages, task=task, **kwargs)

    def estimate_tokens(self, text: str) -> int:
        return self._default.estimate_tokens(text)

    @property
    def context_window(self) -> int:
        return self._default.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._default.capabilities
