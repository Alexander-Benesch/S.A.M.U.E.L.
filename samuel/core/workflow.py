from __future__ import annotations

import logging
from typing import Any, Callable

from samuel.core.commands import create_command
from samuel.core.events import Event, UnhandledCommand

log = logging.getLogger(__name__)


def _cond_self_parity_ok(event: Event, config: Any) -> bool:
    # #271: liest payload.score (was EvalCompleted publisht), nicht eval_score.
    # #285: Hartstop wenn ac_total > 0 und ac_verified == 0 — sonst feuert
    # CreatePR auf criteria_scores die bei Verifier-Crash zu 1.0-Defaults
    # werden (siehe map_ac_results_to_criteria fuer leeren results-List).
    score = event.payload.get("score") or 0
    ac_total = event.payload.get("ac_total") or 0
    ac_verified = event.payload.get("ac_verified") or 0
    if ac_total > 0 and ac_verified == 0:
        return False
    return score >= 0.6


def _cond_healing_enabled_and_under_budget(event: Event, config: Any) -> bool:
    """#239: Workflow-Gate fuer EvalFailed -> Heal.

    Bedingungen:
    - Feature-Flag `healing` aktiv
    - `event.payload.attempt <= healing.max_attempts` (default 3)

    Score-Verbesserungs-Check macht der HealingHandler intern (siehe
    no-improvement-Pfad). Der Engine-Gate prueft nur Budget+Flag, weil
    score-history slice-internal ist.
    """
    if config is None or not config.feature_flag("healing"):
        return False
    attempt = event.payload.get("attempt") or 1
    max_attempts = 3
    if config:
        try:
            val = config.get("healing.max_attempts", 3)
            max_attempts = int(val) if val else 3
        except (TypeError, ValueError):
            max_attempts = 3
    return attempt <= max_attempts


_BUILTIN_CONDITIONS: dict[str, Callable[[Event, Any], bool]] = {
    "self_parity_ok": _cond_self_parity_ok,
    # #239: Heal-Loop-Gate (config-aware)
    "healing_enabled_and_under_budget": _cond_healing_enabled_and_under_budget,
}


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

    def _make_handler(self, step: dict):
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
            return bool(eval(condition, {"event": event, "payload": event.payload}))  # noqa: S307
        except Exception:
            log.warning("Condition eval failed: %s", condition)
            return False