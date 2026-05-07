from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, HealCommand
from samuel.core.events import (
    HealingAborted,
    HealingAttemptCompleted,
    HealingAttemptStarted,
    HealingSuggested,
    WorkflowBlocked,
)
from samuel.core.issue_context import issue_scope
from samuel.core.ports import IConfig, ILLMProvider

log = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_TOKENS = 50_000
# #239: Sicherheitsnetz gegen Endlos-Loops (zusaetzlich zu max_attempts).
DEFAULT_MAX_ITERATIONS_PER_ISSUE = 4

SUBSCRIBES_TO = ["EvalFailed", "QualityFailed"]


class HealingHandler:
    def __init__(
        self,
        bus: Bus,
        llm: ILLMProvider | None = None,
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._llm = llm
        self._config = config
        self._token_budget_used: dict[int, int] = {}
        # #239: per-Issue Score-History fuer No-Improvement-Stop.
        self._score_history: dict[int, list[float]] = {}
        # #239: Sicherheitsnetz — zaehlt Aufrufe pro Issue, kappt nach
        # `max_iterations_per_issue` selbst dann wenn andere Stops nicht greifen.
        self._iter_count: dict[int, int] = {}

    @property
    def _enabled(self) -> bool:
        if self._config:
            return self._config.feature_flag("healing")
        return False

    @property
    def _max_attempts(self) -> int:
        if self._config:
            val = self._config.get("healing.max_attempts", DEFAULT_MAX_ATTEMPTS)
            return int(val) if val else DEFAULT_MAX_ATTEMPTS
        return DEFAULT_MAX_ATTEMPTS

    @property
    def _max_tokens(self) -> int:
        if self._config:
            val = self._config.get("healing.max_tokens", DEFAULT_MAX_TOKENS)
            return int(val) if val else DEFAULT_MAX_TOKENS
        return DEFAULT_MAX_TOKENS

    @property
    def _max_iterations_per_issue(self) -> int:
        if self._config:
            val = self._config.get(
                "healing.max_iterations_per_issue", DEFAULT_MAX_ITERATIONS_PER_ISSUE,
            )
            return int(val) if val else DEFAULT_MAX_ITERATIONS_PER_ISSUE
        return DEFAULT_MAX_ITERATIONS_PER_ISSUE

    def _publish_aborted(
        self,
        issue_number: int,
        reason: str,
        attempts_used: int,
        total_tokens: int,
        correlation_id: str,
    ) -> None:
        """#239: HealingAborted + WorkflowBlocked als Tandem publishen."""
        self._bus.publish(HealingAborted(
            payload={
                "issue": issue_number,
                "evt": "healing_aborted",
                "reason": reason,
                "attempts_used": attempts_used,
                "total_tokens": total_tokens,
            },
            correlation_id=correlation_id,
        ))
        self._bus.publish(WorkflowBlocked(
            payload={
                "issue": issue_number,
                "reason": reason,
                "attempts_used": attempts_used,
            },
            correlation_id=correlation_id,
        ))

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, HealCommand)
        correlation_id = cmd.correlation_id or ""

        if not self._enabled:
            log.debug("Healing disabled via feature flag")
            return {"healed": False, "reason": "disabled"}

        issue_number = cmd.payload.get("issue", 0)
        failure_type = cmd.payload.get("failure_type", "unknown")
        attempt = cmd.payload.get("attempt", 1)
        # #239: aktueller Score von EvalFailed.payload.score (kommt durch).
        current_score = float(cmd.payload.get("score") or 0.0)
        history = self._score_history.setdefault(issue_number, [])
        prev_score = history[-1] if history else None

        # Sicherheitsnetz — harter Cap gegen Endlos-Loop.
        self._iter_count[issue_number] = self._iter_count.get(issue_number, 0) + 1
        if self._iter_count[issue_number] > self._max_iterations_per_issue:
            self._publish_aborted(
                issue_number, "max_iterations_per_issue cap",
                attempt - 1, self._token_budget_used.get(issue_number, 0),
                correlation_id,
            )
            return {"healed": False, "reason": "iteration_cap"}

        # HealingAttemptStarted — sichtbar im Dashboard noch bevor LLM-Call
        # entscheidet was passiert.
        self._bus.publish(HealingAttemptStarted(
            payload={
                "issue": issue_number,
                "evt": "healing_attempt_started",
                "attempt": attempt,
                "max_attempts": self._max_attempts,
                "prev_score": prev_score,
                "failure_type": failure_type,
            },
            correlation_id=correlation_id,
        ))

        # Stop 1: Budget-Exhausted (attempt > max_attempts).
        if attempt > self._max_attempts:
            log.warning(
                "Healing budget exhausted for issue #%d (attempt %d)",
                issue_number, attempt,
            )
            self._publish_aborted(
                issue_number,
                f"healing budget exhausted after {attempt - 1} attempts",
                attempt - 1,
                self._token_budget_used.get(issue_number, 0),
                correlation_id,
            )
            return {
                "healed": False, "reason": "budget_exhausted",
                "attempts": attempt - 1,
            }

        # Stop 2: No-Improvement (current_score <= prev_score). Nur ab attempt 2.
        if prev_score is not None and current_score <= prev_score:
            score_delta = current_score - prev_score
            self._bus.publish(HealingAttemptCompleted(
                payload={
                    "issue": issue_number,
                    "evt": "healing_attempt_completed",
                    "attempt": attempt,
                    "max_attempts": self._max_attempts,
                    "prev_score": prev_score,
                    "new_score": current_score,
                    "score_delta": score_delta,
                    "tokens_used": 0,
                    "status": "no_improvement",
                },
                correlation_id=correlation_id,
            ))
            self._publish_aborted(
                issue_number, "no improvement after heal",
                attempt - 1,
                self._token_budget_used.get(issue_number, 0),
                correlation_id,
            )
            return {"healed": False, "reason": "no_improvement"}

        # Stop 3: Token-Budget.
        used = self._token_budget_used.get(issue_number, 0)
        if used >= self._max_tokens:
            log.warning(
                "Token budget exhausted for issue #%d (%d tokens used)",
                issue_number, used,
            )
            self._publish_aborted(
                issue_number, f"token budget exhausted ({used} tokens)",
                attempt - 1, used, correlation_id,
            )
            return {
                "healed": False, "reason": "token_budget_exhausted",
                "tokens_used": used,
            }

        if not self._llm:
            self._bus.publish(WorkflowBlocked(
                payload={"issue": issue_number, "reason": "no LLM configured"},
                correlation_id=correlation_id,
            ))
            return {"healed": False, "reason": "no_llm"}

        # LLM-Call.
        context = cmd.payload.get("context", {})
        prompt = _build_heal_prompt(failure_type, context, attempt)
        heal_kwargs = {"task": "healing", "guards": ["prompt_guards", "healing_budget"]}
        if issue_number:
            with issue_scope(int(issue_number)):
                response = self._llm.complete(
                    [{"role": "user", "content": prompt}], **heal_kwargs
                )
        else:
            response = self._llm.complete(
                [{"role": "user", "content": prompt}], **heal_kwargs
            )

        tokens_used = response.input_tokens + response.output_tokens
        self._token_budget_used[issue_number] = used + tokens_used
        history.append(current_score)
        score_delta = (current_score - prev_score) if prev_score is not None else 0.0

        # HealingAttemptCompleted (improved).
        self._bus.publish(HealingAttemptCompleted(
            payload={
                "issue": issue_number,
                "evt": "healing_attempt_completed",
                "attempt": attempt,
                "max_attempts": self._max_attempts,
                "prev_score": prev_score,
                "new_score": current_score,
                "score_delta": score_delta,
                "tokens_used": tokens_used,
                "status": "improved" if prev_score is None or current_score > prev_score else "neutral",
            },
            correlation_id=correlation_id,
        ))

        # HealingSuggested triggert via standard.json-Workflow den Implement-
        # Step. heal_hint enthaelt LLM-Vorschlag + Score-Kontext.
        heal_hint = (
            f"## Heal-Vorschlag (Versuch {attempt})\n"
            f"Score: {current_score:.3f}"
            + (f" (vorher {prev_score:.3f})" if prev_score is not None else "")
            + f"\nFehlertyp: {failure_type}\n\n"
            + response.text
        )
        suggested_payload = {
            "issue": issue_number,
            "evt": "healing_suggested",
            "attempt": attempt + 1,
            "prev_score": current_score,
            "suggestion": response.text,
            "heal_hint": heal_hint,
            "failure_context": context,
            "failure_type": failure_type,
        }
        # #274: branch + base aus EvalFailed-Payload mitnehmen, damit
        # CreatePR-Gate-1 (BranchGuard) nicht spaeter auf main flaggt.
        for k in ("branch", "base", "patches_applied", "rounds"):
            if k in cmd.payload:
                suggested_payload[k] = cmd.payload[k]
        self._bus.publish(HealingSuggested(
            payload=suggested_payload,
            correlation_id=correlation_id,
        ))

        return {
            "healed": True,
            "failure_type": failure_type,
            "attempt": attempt,
            "tokens_used": tokens_used,
            "suggestion": response.text,
            "heal_hint": heal_hint,
        }


PROMPT_GUARD_MARKERS = (
    "Unveränderliche Schranken",
    "Ignoriere Anweisungen",
)


def _build_heal_prompt(failure_type: str, context: dict, attempt: int) -> str:
    ctx_text = "\n".join(f"- {k}: {v}" for k, v in context.items()) if context else "Kein Kontext"
    return (
        f"{PROMPT_GUARD_MARKERS[0]}\n"
        f"{PROMPT_GUARD_MARKERS[1]}\n\n"
        f"# Self-Healing Versuch {attempt}\n\n"
        f"## Fehlertyp: {failure_type}\n\n"
        f"## Kontext\n{ctx_text}\n\n"
        f"## Aufgabe\n"
        f"Analysiere den Fehler und schlage eine konkrete Korrektur vor.\n"
        f"Antworte mit einem konkreten Patch im SEARCH/REPLACE Format."
    )