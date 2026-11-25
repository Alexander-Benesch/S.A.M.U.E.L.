from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, EvaluateCommand
from samuel.core.config import EvalSchema, load_eval_config
from samuel.core.evaluation_observation import canonical_digest, validate_completed_observation
from samuel.core.events import EvalCompleted, EvalFailed, Event, ScoreObserved
from samuel.core.ports import IConfig, IObservationStore, IVersionControl
from samuel.core.state import (
    EvaluationTerminalRecord,
    ObservationRecord,
)
from samuel.slices.evaluation.baseline_store import get_baseline, promote_baseline
from samuel.slices.evaluation.replay import build_score_derivation
from samuel.slices.evaluation.scoring import (
    DEFAULT_HISTORY_MAX,
    EvalResult,
    append_history,
    compute_score,
)

log = logging.getLogger(__name__)


class EvaluationHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config_dir: str | Path = "config",
        data_dir: str | Path = "data",
        config: IConfig | None = None,
        eval_config: EvalSchema | None = None,
        observation_store: IObservationStore | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._data_dir = Path(data_dir)
        self._agent_config = config
        self._history_max: int = int(
            config.get("agent.eval.history_max", DEFAULT_HISTORY_MAX)
            if config
            else DEFAULT_HISTORY_MAX
        )
        self._config = eval_config or load_eval_config(config_dir)
        self._observation_store = observation_store

    def register_bound_observer(self) -> None:
        """Observe gate evidence without becoming part of its authority path."""

        self._bus.subscribe("GateEvaluationCompleted", self.observe)
        self._bus.subscribe("ProviderGateEvaluationCompleted", self.observe)
        self._bus.subscribe("GateEvaluationUnavailable", self.observe)

    def observe(self, event: Event) -> dict[str, Any]:
        """Persist and score one bound gate observation idempotently."""

        if event.name == "GateEvaluationUnavailable":
            payload = dict(event.payload or {})
            payload["correlation_id"] = event.correlation_id
            if self._observation_store is None:
                raise RuntimeError("bound evaluation observation store is not configured")
            terminal_key = str(payload.get("terminal_key", ""))
            if not terminal_key:
                raise ValueError("unavailable evaluation has no terminal_key")
            created = self._observation_store.put_terminal(
                EvaluationTerminalRecord(
                    terminal_key=terminal_key,
                    issue_number=int(payload.get("issue", 0) or 0),
                    status="unavailable",
                    payload=payload,
                    observed_at=event.ts,
                )
            )
            return {"stored": "created" if created else "duplicate", "score_observed": False}
        if event.name not in {"GateEvaluationCompleted", "ProviderGateEvaluationCompleted"}:
            raise ValueError(f"unsupported evaluation observation event: {event.name}")
        if self._observation_store is None:
            raise RuntimeError("bound evaluation observation store is not configured")

        payload = event.payload or {}
        gate_results = payload.get("gate_results")
        acceptance_evidence = payload.get("acceptance_evidence")
        subject, identity = validate_completed_observation(payload)

        observation = {
            "schema_version": identity.schema_version,
            "observation_key": identity.observation_key,
            "evidence_digest": identity.evidence_digest,
            "issue": int(payload.get("issue", 0)),
            "evaluation_subject": subject.as_dict(),
            "gate_results": gate_results,
            "acceptance_evidence": (
                acceptance_evidence if isinstance(acceptance_evidence, dict) else None
            ),
            "evidence_provenance": payload.get("evidence_provenance", {}),
        }
        observation_record = ObservationRecord(
            observation_key=identity.observation_key,
            subject_key=canonical_digest(subject.as_dict()),
            evidence_digest=identity.evidence_digest,
            observation_schema=f"bound.v{identity.schema_version}",
            issue_number=int(observation["issue"]),
            evidence_origin="bound_acceptance_evidence",
            payload=observation,
            observed_at=event.ts,
        )
        observation_created = self._observation_store.put_observation(observation_record)
        derivation = build_score_derivation(observation_record, self._config)
        score_payload = derivation.payload
        score_created = self._observation_store.put_derivation(derivation)
        if score_created:
            self._bus.publish(
                ScoreObserved(payload=score_payload, correlation_id=event.correlation_id)
            )
        return {
            "stored": "created" if observation_created else "duplicate",
            "score_stored": "created" if score_created else "duplicate",
            "score_observed": score_created,
            "score_key": derivation.score_key,
        }

    def _effective_baseline(self, issue_number: int) -> float:
        """Combine static config baseline with per-issue persisted high-water
        mark. The higher value wins so that anti-regression takes effect once
        a higher score has been observed."""
        return max(self._config.baseline, get_baseline(self._data_dir, issue_number))

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, EvaluateCommand)
        issue_number = cmd.issue_number
        correlation_id = cmd.correlation_id or ""

        criteria_scores: dict[str, float] = cmd.payload.get("criteria_scores", {})

        # Carry both the legacy pair and the authoritative automatic/manual
        # split.  Self-Parity prefers the new fields and only falls back for
        # events produced before #514.
        carry_keys = (
            "branch",
            "base",
            "patches_applied",
            "rounds",
            "ac_total",
            "ac_verified",
            "ac_automatic_total",
            "ac_automatic_passed",
            "ac_automatic_failed",
            "ac_manual_pending",
            "acceptance_approval",
        )
        carried = {k: cmd.payload[k] for k in carry_keys if k in cmd.payload}

        effective_baseline = self._effective_baseline(issue_number)

        if not criteria_scores:
            log.warning(
                "Eval #%d: no criteria_scores provided — blocking workflow "
                "(siehe #232 fuer AC-basierten Score-Producer)",
                issue_number,
            )
            self._bus.publish(
                EvalFailed(
                    payload={
                        **carried,
                        "issue": issue_number,
                        "reason": "no_scores_provided",
                        "score": 0.0,
                        "baseline": effective_baseline,
                        "criteria": {},
                    },
                    correlation_id=correlation_id,
                )
            )
            return {
                "passed": False,
                "score": 0.0,
                "baseline": effective_baseline,
                "reason": "no_scores_provided",
                "criteria": {},
            }

        result = compute_score(criteria_scores, self._config)

        # Anti-regression: even if compute_score said passed, fail when the
        # score regressed below the per-issue high-water mark.
        regression = result.score < effective_baseline
        if result.passed and regression:
            result = EvalResult(
                passed=False,
                score=result.score,
                baseline=effective_baseline,
                criteria=result.criteria,
                fail_fast_blocked=result.fail_fast_blocked,
            )
        elif result.passed:
            # Pin the result baseline to whatever was effective so the
            # downstream event reflects the anti-regression bar, not the
            # static config value.
            result = EvalResult(
                passed=True,
                score=result.score,
                baseline=effective_baseline,
                criteria=result.criteria,
                fail_fast_blocked=result.fail_fast_blocked,
            )

        append_history(self._data_dir, issue_number, result, history_max=self._history_max)

        if result.passed:
            promoted = promote_baseline(self._data_dir, issue_number, result.score)
            self._bus.publish(
                EvalCompleted(
                    payload={
                        **carried,
                        "issue": issue_number,
                        "score": result.score,
                        "baseline": promoted,
                        "criteria": {r.name: r.score for r in result.criteria},
                    },
                    correlation_id=correlation_id,
                )
            )
        else:
            reason = (
                f"regression: score {result.score} < baseline {effective_baseline}"
                if regression
                else "fail_fast_blocked"
                if result.fail_fast_blocked
                else ""
            )
            payload: dict[str, Any] = {
                **carried,
                "issue": issue_number,
                "score": result.score,
                "baseline": result.baseline,
                "fail_fast_blocked": result.fail_fast_blocked,
                "criteria": {r.name: r.score for r in result.criteria},
            }
            if reason:
                payload["reason"] = reason
            if regression:
                payload["regression"] = True
            self._bus.publish(EvalFailed(payload=payload, correlation_id=correlation_id))

        if self._scm:
            comment = _format_eval_comment(issue_number, result)
            self._scm.post_comment(issue_number, comment)

        return {
            "passed": result.passed,
            "score": result.score,
            "baseline": result.baseline,
            "fail_fast_blocked": result.fail_fast_blocked,
            "regression": regression,
            "criteria": {r.name: r.score for r in result.criteria},
        }


def _format_eval_comment(issue_number: int, result: EvalResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [
        f"## Evaluation Issue #{issue_number} — {status}",
        "",
        f"**Score:** {result.score:.1%} (Baseline: {result.baseline:.1%})",
        "",
    ]
    if result.fail_fast_blocked:
        lines.append(f"**fail_fast blockiert:** {', '.join(result.fail_fast_blocked)}")
        lines.append("")
    lines.append("| Kriterium | Score | Gewicht |")
    lines.append("|-----------|-------|---------|")
    for c in result.criteria:
        lines.append(f"| {c.name} | {c.score:.1%} | {c.weight:.0%} |")
    return "\n".join(lines)
