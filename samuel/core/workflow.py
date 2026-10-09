from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from samuel.core.commands import create_command
from samuel.core.config import WORKFLOW_BUILTIN_CONDITION_NAMES
from samuel.core.events import Event, UnhandledCommand

log = logging.getLogger(__name__)


def _has_clarification(event: Event, _config: Any) -> bool:
    contract = event.payload.get("acceptance_contract")
    return isinstance(contract, dict) and isinstance(contract.get("clarification_basis"), dict)


_BUILTIN_CONDITIONS: dict[str, Callable[[Event, Any], bool]] = {
    "plan_without_clarification": lambda event, config: not _has_clarification(event, config),
    "plan_with_clarification": _has_clarification,
}

assert set(_BUILTIN_CONDITIONS) == WORKFLOW_BUILTIN_CONDITION_NAMES


def plan_approval_required(definition: dict[str, Any]) -> bool | None:
    """Derive plan approval from the active implementation transition."""

    triggers = {
        str(step.get("on"))
        for step in definition.get("steps", [])
        if isinstance(step, dict)
        and step.get("send") == "Implement"
        and step.get("on") in {"PlanApproved", "PlanValidated"}
    }
    if triggers == {"PlanApproved"}:
        return True
    if triggers == {"PlanValidated"} or triggers == {"PlanApproved", "PlanValidated"}:
        return False
    return None


class WorkflowEngine:
    def __init__(
        self,
        bus: Any,
        definition: dict | None = None,
        config: Any | None = None,
    ) -> None:
        self._bus = bus
        self._config = config
        self._steps: list[dict] = []
        if definition:
            self.load(definition)

    def load(self, definition: dict) -> None:
        self._steps = definition.get("steps", [])
        for step in self._steps:
            event_name = step["on"]
            self._bus.subscribe(event_name, self._make_handler(step))

    def _make_handler(self, step: dict) -> Callable[[Event], None]:
        def handler(event: Event) -> None:
            command_name = step["send"]
            condition = step.get("condition")
            if condition and not self._evaluate_condition(condition, event):
                log.debug("Condition not met for %s -> %s", event.name, command_name)
                return
            if not self._bus.has_handler(command_name):
                self._bus.publish(
                    UnhandledCommand(
                        payload={
                            "command": command_name,
                            "trigger": event.name,
                            "reason": f"No handler registered for '{command_name}'",
                        }
                    )
                )
                return
            cmd = create_command(
                command_name,
                payload=event.payload,
                correlation_id=event.correlation_id,
            )
            self._bus.send(cmd)

        return handler

    def _evaluate_condition(self, condition: str, event: Event) -> bool:
        if condition in _BUILTIN_CONDITIONS:
            return _BUILTIN_CONDITIONS[condition](event, self._config)
        try:
            return bool(
                eval(  # noqa: S307 - expression was schema-validated at profile load
                    condition,
                    {"__builtins__": {}},
                    {"event": event, "payload": event.payload},
                )
            )
        except Exception:
            log.warning("Condition eval failed: %s", condition)
            return False
