"""#153: Attribute passive quality observations to the preceding LLM call.

Die ``correlation_id`` der Events propagiert in v2 nicht zuverlaessig vom
LLM-Call bis zum Eval (#206-Luecke), wohl aber die ``issue``-Nummer. Dieser
Handler korreliert daher ueber ``issue``: er merkt sich pro Issue den zuletzt
gesehenen (provider, model, task) eines LLM-Calls. Ein vollständig
gekennzeichnetes, nicht bindendes ``ScoreObserved`` wird diesem Tupel
gutgeschrieben. Der *letzte* LLM-Call vor der Beobachtung
(typisch die Implementierung) erhält die Attribution. Reine Planungs-Calls
bleiben unbeobachtet.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict

from samuel.core.bus import Bus
from samuel.core.events import Event, QualityCheckCompleted
from samuel.core.ports import IQualityMetricsRegistry

log = logging.getLogger(__name__)

SUBSCRIBES_TO = ["LLMCallCompleted", "ScoreObserved"]
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class QualityMetricsHandler:
    def __init__(
        self,
        bus: Bus,
        registry: IQualityMetricsRegistry,
        max_tracked: int = 512,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._max = max_tracked
        # issue -> (provider, model, task) des zuletzt gesehenen LLM-Calls.
        self._by_issue: OrderedDict[int, tuple[str, str, str]] = OrderedDict()

    def register(self, bus: Bus | None = None) -> None:
        b = bus or self._bus
        b.subscribe("LLMCallCompleted", self.on_llm_call)
        b.subscribe("ScoreObserved", self.on_eval)

    def on_llm_call(self, event: Event) -> None:
        payload = event.payload or {}
        issue = payload.get("issue")
        if issue is None:
            return
        try:
            issue_i = int(issue)
        except (TypeError, ValueError):
            return
        self._by_issue[issue_i] = (
            str(payload.get("provider", "")),
            str(payload.get("model", "")),
            str(payload.get("task", "")),
        )
        self._by_issue.move_to_end(issue_i)
        while len(self._by_issue) > self._max:
            self._by_issue.popitem(last=False)

    def on_eval(self, event: Event) -> None:
        payload = event.payload or {}
        issue = payload.get("issue")
        score = payload.get("score")
        if issue is None or not isinstance(score, (int, float)):
            return
        try:
            issue_i = int(issue)
        except (TypeError, ValueError):
            return
        key = self._by_issue.get(issue_i)
        if key is None:
            return  # kein bekannter LLM-Call fuer dieses Issue -> nichts zu graden
        provider, model, task = key
        if event.name != "ScoreObserved":
            return
        required = (
            payload.get("non_binding") is True,
            payload.get("evidence_origin") == "bound_acceptance_evidence",
            bool(_DIGEST_RE.fullmatch(str(payload.get("observation_key", "")))),
            bool(_DIGEST_RE.fullmatch(str(payload.get("score_key", "")))),
            bool(_DIGEST_RE.fullmatch(str(payload.get("scoring_policy_digest", "")))),
            bool(str(payload.get("scoring_policy_version", ""))),
            bool(str(payload.get("formula_version", ""))),
        )
        if not all(required) or payload.get("scoreability") != "scoreable":
            return
        passed: bool | None = None
        criteria = payload.get("categories") if isinstance(payload.get("categories"), dict) else {}
        metadata = {
            "observation_key": payload["observation_key"],
            "scoring_policy_version": payload["scoring_policy_version"],
            "scoring_policy_digest": payload.get("scoring_policy_digest"),
            "formula_version": payload["formula_version"],
            "observation_schema": str(payload.get("observation_schema") or "bound.v1"),
            "evidence_origin": payload["evidence_origin"],
            "non_binding": True,
        }

        try:
            self._registry.record(
                provider,
                model,
                task,
                float(score),
                passed,
                metadata=metadata,
            )
        except Exception:
            log.exception("quality registry record failed")

        try:
            self._bus.publish(
                QualityCheckCompleted(
                    payload={
                        "provider": provider,
                        "model": model,
                        "task": task,
                        "score": float(score),
                        "passed": passed,
                        "non_binding": True,
                        "observation": metadata,
                        "criteria": criteria,
                        "issue": issue_i,
                    },
                    correlation_id=event.correlation_id,
                )
            )
        except Exception:
            log.exception("publish QualityCheckCompleted failed")
