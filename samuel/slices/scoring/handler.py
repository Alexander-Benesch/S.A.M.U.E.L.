"""ScoringHandler — produziert criteria_scores aus AC-Verifikation (#232).

Liegt zwischen CodeGenerated und Evaluate im Workflow:
    CodeGenerated -> Score -> Scored -> Evaluate

Holt den Plan-Kommentar des Issues, ruft die AC-Verifikation per Bus auf
(VerifyACCommand → ACVerificationHandler), mappt die Tag-Pass-Rates auf
die 4 eval-Kriterien und publisht Scored mit criteria_scores im Payload.
Die Workflow-Engine reicht das Payload weiter an EvaluateCommand.
"""
from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, ScoreCommand, VerifyACCommand
from samuel.core.events import Scored
from samuel.core.ports import IVersionControl

log = logging.getLogger(__name__)


_TAG_FAMILIES: dict[str, set[str]] = {
    "syntax_valid":     {"DIFF", "EXISTS", "IMPORT"},
    "test_pass_rate":   {"TEST"},
    "scope_compliant":  {"GREP", "GREP:NOT"},
}

_HALLUCINATION_TAGS = {"DIFF", "EXISTS"}


def map_ac_results_to_criteria(results: list[dict[str, Any]]) -> dict[str, float]:
    """Map per-AC verification results into the 4 eval criteria.

    Score per criterion = passed / total within its tag family.
    Empty family → 1.0 (no claim, no failure to fault the LLM for).
    hallucination_free is the DIFF/EXISTS pass-rate: when the LLM claims a
    file exists and it doesn't, that's the textbook hallucination signal.
    """
    scores: dict[str, float] = {}
    for criterion, tags in _TAG_FAMILIES.items():
        relevant = [r for r in results if r.get("tag") in tags]
        if not relevant:
            scores[criterion] = 1.0
        else:
            passed = sum(1 for r in relevant if r.get("passed"))
            scores[criterion] = passed / len(relevant)

    halluc_relevant = [r for r in results if r.get("tag") in _HALLUCINATION_TAGS]
    if not halluc_relevant:
        scores["hallucination_free"] = 1.0
    else:
        passed = sum(1 for r in halluc_relevant if r.get("passed"))
        scores["hallucination_free"] = passed / len(halluc_relevant)

    return scores


def _extract_plan_comment(scm: IVersionControl, issue_number: int) -> str:
    comments = scm.get_comments(issue_number)
    for c in reversed(comments):
        if "## Plan" in c.body or "### Akzeptanzkriterien" in c.body:
            return c.body
    return ""


class ScoringHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, ScoreCommand)
        issue_number = cmd.issue_number or cmd.payload.get("issue", 0)
        correlation_id = cmd.correlation_id or ""

        carry_keys = ("branch", "base", "patches_applied", "rounds")
        carried = {k: cmd.payload[k] for k in carry_keys if k in cmd.payload}

        if not self._scm:
            log.warning("Score #%d: no scm — cannot fetch plan", issue_number)
            self._publish(carried, issue_number, {}, "no_scm", correlation_id)
            return {"criteria_scores": {}, "reason": "no_scm"}

        plan_text = _extract_plan_comment(self._scm, issue_number)
        if not plan_text:
            log.warning("Score #%d: no plan comment found", issue_number)
            self._publish(carried, issue_number, {}, "no_plan_found", correlation_id)
            return {"criteria_scores": {}, "reason": "no_plan_found"}

        # #253: issue im payload mitführen, sonst publisht der AC-Verifier
        # TestRunCompleted-Events ohne issue-Field und das Dashboard kann
        # die Test-Runs keinem Issue zuordnen.
        ac_result = self._bus.send(VerifyACCommand(payload={
            "plan_text": plan_text,
            "issue": issue_number,
        })) or {}
        results = ac_result.get("results", [])

        # #285: ac_total/ac_verified explizit publishen, damit
        # _cond_self_parity_ok einen Hartstop bei 0-Verifikationen machen kann
        # (sonst durchwinkt criteria_scores=1.0-Defaults bei Verifier-Crash).
        ac_total = len(results)
        ac_verified = sum(1 for r in results if r.get("passed"))

        criteria_scores = map_ac_results_to_criteria(results)
        log.info(
            "Score #%d: %d/%d ACs verified — criteria_scores=%s",
            issue_number, ac_verified, ac_total, criteria_scores,
        )
        self._publish(
            carried, issue_number, criteria_scores, None, correlation_id,
            ac_total=ac_total, ac_verified=ac_verified,
        )
        return {
            "criteria_scores": criteria_scores,
            "ac_results": results,
            "ac_total": ac_total,
            "ac_verified": ac_verified,
        }

    def _publish(
        self,
        carried: dict[str, Any],
        issue_number: int,
        criteria_scores: dict[str, float],
        reason: str | None,
        correlation_id: str,
        *,
        ac_total: int = 0,
        ac_verified: int = 0,
    ) -> None:
        payload: dict[str, Any] = {
            **carried,
            "issue": issue_number,
            "criteria_scores": criteria_scores,
            "ac_total": ac_total,
            "ac_verified": ac_verified,
        }
        if reason:
            payload["reason"] = reason
        self._bus.publish(Scored(payload=payload, correlation_id=correlation_id))