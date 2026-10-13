"""Non-authoritative presentation of bound score observations."""

from __future__ import annotations

import logging
import threading
from typing import Any

from samuel.core.events import Event
from samuel.core.ports import IVersionControl

log = logging.getLogger(__name__)


def render_score_observation(payload: dict[str, Any]) -> str:
    """Render telemetry without PASS/FAIL, baseline or merge language."""

    raw_score = payload.get("score")
    score = f"{float(raw_score):.1%}" if isinstance(raw_score, (int, float)) else "n/a"
    raw_coverage = payload.get("coverage")
    if isinstance(raw_coverage, dict):
        ratio = raw_coverage.get("ratio")
        coverage = f"{float(ratio):.1%}" if isinstance(ratio, (int, float)) else "n/a"
    elif isinstance(raw_coverage, (int, float)):
        coverage = f"{float(raw_coverage):.1%}"
    else:
        coverage = "n/a"
    lines = [
        "## Nicht bindende Qualitätsbeobachtung",
        "",
        "Diese Messung ist kein PASS/FAIL- oder Merge-Signal. "
        "Die Freigabeentscheidung stammt ausschließlich aus dem Required-Gate-Profil.",
        "",
        f"- **Beobachteter Score:** {score}",
        f"- **Berechenbarkeit:** `{payload.get('scoreability', 'unknown')}`",
        f"- **Rohabdeckung:** {coverage}",
        f"- **Scoring-Policy:** `{payload.get('scoring_policy_version', 'n/a')}`",
        f"- **Formel:** `{payload.get('formula_version', 'n/a')}`",
        f"- **Evidence-Herkunft:** `{payload.get('evidence_origin', 'n/a')}`",
        f"- **Observation:** `{payload.get('observation_key', 'n/a')}`",
        "",
        "| Kategorie | Anwendbar | Vorhanden | Bestanden | Beobachtung |",
        "|---|---:|---:|---:|---:|",
    ]
    categories = payload.get("categories")
    if isinstance(categories, dict):
        for name, category in categories.items():
            if not isinstance(category, dict):
                continue
            category_score = category.get("score")
            rendered_score = (
                f"{float(category_score):.1%}"
                if isinstance(category_score, (int, float))
                else "n/a"
            )
            lines.append(
                f"| {name} | {'ja' if category.get('applicable') else 'nein'} | "
                f"{category.get('criteria_total', category.get('total', 0))} | "
                f"{category.get('criteria_passed', category.get('passed', 0))} | "
                f"{rendered_score} |"
            )
    return "\n".join(lines)


class ScorePresentationHandler:
    """Join ScoreObserved with PRCreated and post outside the gate call stack.

    The subscriber only caches and queues work.  SCM I/O runs in a bounded
    daemon thread, so a slow provider cannot delay or change the PR result.
    Adapter-level request timeouts remain the hard network bound.
    """

    def __init__(
        self,
        bus: Any,
        *,
        scm: IVersionControl | None,
        request_timeout: float = 10.0,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._request_timeout = max(0.1, float(request_timeout))
        self._scores: dict[tuple[int, str], dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._slot = threading.BoundedSemaphore(1)

    def register(self) -> None:
        self._bus.subscribe("ScoreObserved", self.on_score_observed)
        self._bus.subscribe("PRCreated", self.on_pr_created)

    @staticmethod
    def _key(payload: dict[str, Any]) -> tuple[int, str]:
        subject = payload.get("evaluation_subject")
        head = subject.get("head_sha", "") if isinstance(subject, dict) else ""
        return int(payload.get("issue", 0)), str(head)

    def on_score_observed(self, event: Event) -> dict[str, Any]:
        payload = dict(event.payload or {})
        if payload.get("gate_blocked") is True:
            return {"cached": False, "reason": "no_pr_for_blocked_gate_run"}
        with self._lock:
            self._scores[self._key(payload)] = payload
        return {"cached": True, "external_io": False}

    def on_pr_created(self, event: Event) -> dict[str, Any]:
        payload = event.payload or {}
        with self._lock:
            score = self._scores.pop(self._key(payload), None)
        if score is None or self._scm is None:
            return {"queued": False, "reason": "score_or_scm_unavailable"}
        if not self._slot.acquire(blocking=False):
            log.warning("Score presentation queue busy; observation remains in audit data")
            return {"queued": False, "reason": "presentation_busy"}
        pr_number = int(payload.get("pr_number", 0))
        thread = threading.Thread(
            target=self._post,
            args=(pr_number, score),
            name=f"score-presentation-{pr_number}",
            daemon=True,
        )
        thread.start()
        timer = threading.Timer(
            self._request_timeout,
            self._report_timeout,
            args=(thread, pr_number),
        )
        timer.daemon = True
        timer.start()
        return {"queued": True, "external_io": "background"}

    def _post(self, pr_number: int, score: dict[str, Any]) -> None:
        try:
            assert self._scm is not None
            self._scm.post_comment(pr_number, render_score_observation(score))
        except Exception as exc:
            log.warning("Score presentation failed for PR #%d (%s)", pr_number, type(exc).__name__)
        finally:
            self._slot.release()

    @staticmethod
    def _report_timeout(thread: threading.Thread, pr_number: int) -> None:
        if thread.is_alive():
            log.warning("Score presentation exceeded request timeout for PR #%d", pr_number)
