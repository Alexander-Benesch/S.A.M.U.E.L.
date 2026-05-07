from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, EvaluateCommand
from samuel.core.config import EvalSchema, load_eval_config
from samuel.core.events import EvalCompleted, EvalFailed
from samuel.core.ports import IConfig, IVersionControl
from samuel.slices.evaluation.baseline_store import get_baseline, promote_baseline
from samuel.slices.evaluation.scoring import EvalResult, append_history, compute_score

log = logging.getLogger(__name__)


class EvaluationHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config_dir: str | Path = "config",
        data_dir: str | Path = "data",
        config: IConfig | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._data_dir = Path(data_dir)
        self._agent_config = config
        self._history_max: int = int(
            config.get("agent.eval.history_max", 90) if config else 90
        )
        try:
            self._config = load_eval_config(config_dir)
        except ValueError:
            self._config = EvalSchema()

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

        # #285: ac_total/ac_verified durchreichen, damit _cond_self_parity_ok
        # in workflow.py einen Hartstop bei 0-Verifikationen machen kann.
        carry_keys = ("branch", "base", "patches_applied", "rounds", "ac_total", "ac_verified")
        carried = {k: cmd.payload[k] for k in carry_keys if k in cmd.payload}

        effective_baseline = self._effective_baseline(issue_number)

        if not criteria_scores:
            log.warning(
                "Eval #%d: no criteria_scores provided — blocking workflow "
                "(siehe #232 fuer AC-basierten Score-Producer)",
                issue_number,
            )
            self._bus.publish(EvalFailed(
                payload={
                    **carried,
                    "issue": issue_number,
                    "reason": "no_scores_provided",
                    "score": 0.0,
                    "baseline": effective_baseline,
                    "criteria": {},
                },
                correlation_id=correlation_id,
            ))
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
            self._bus.publish(EvalCompleted(
                payload={
                    **carried,
                    "issue": issue_number,
                    "score": result.score,
                    "baseline": promoted,
                    "criteria": {r.name: r.score for r in result.criteria},
                },
                correlation_id=correlation_id,
            ))
        else:
            reason = (
                f"regression: score {result.score} < baseline {effective_baseline}"
                if regression
                else "fail_fast_blocked" if result.fail_fast_blocked else ""
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