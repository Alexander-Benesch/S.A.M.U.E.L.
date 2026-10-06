"""Side-effect-free score replay from immutable bound observations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from samuel.core.config import EvalSchema
from samuel.core.evaluation_observation import ScoreDerivationIdentity, canonical_digest
from samuel.core.ports import IObservationStore
from samuel.core.state import ObservationRecord, ScoreDerivationRecord
from samuel.slices.evaluation.bound_scoring import derive_bound_score


class ScoreReplay:
    """Rebuild derivations without publishing workflow events or touching EWMA."""

    def __init__(self, store: IObservationStore, policies: Iterable[EvalSchema]) -> None:
        self._store = store
        self._policies = tuple(policies)
        identities = {(policy.policy_version, policy.formula_version) for policy in self._policies}
        if len(identities) != len(self._policies):
            raise ValueError("score replay policies must have unique policy/formula identities")

    def replay(self, *, issue_number: int | None = None) -> dict[str, Any]:
        created = 0
        duplicates = 0
        not_scoreable = 0
        results: list[dict[str, Any]] = []
        observations = self._store.list_observations(issue_number)
        for observation in observations:
            for policy in self._policies:
                record = build_score_derivation(observation, policy)
                was_created = self._store.put_derivation(record)
                created += int(was_created)
                duplicates += int(not was_created)
                not_scoreable += int(record.score is None)
                results.append(
                    {
                        "observation_key": observation.observation_key,
                        "score_key": record.score_key,
                        "scoring_policy_version": record.scoring_policy_version,
                        "formula_version": record.formula_version,
                        "status": "created" if was_created else "duplicate",
                        "scoreability": record.payload["scoreability"],
                    }
                )
        return {
            "schema": "samuel-score-replay.v1",
            "observations": len(observations),
            "policy_formula_pairs": len(self._policies),
            "created": created,
            "duplicates": duplicates,
            "not_scoreable": not_scoreable,
            "workflow_events_published": 0,
            "quality_metrics_updated": 0,
            "results": results,
        }


def build_score_derivation(
    observation: ObservationRecord,
    config: EvalSchema,
) -> ScoreDerivationRecord:
    """Apply one formula to one immutable observation using the live payload shape."""

    scoring_policy = {
        "policy_version": config.policy_version,
        "formula_version": config.formula_version,
        "weights": config.weights,
    }
    scoring_policy_digest = canonical_digest(scoring_policy)
    identity = ScoreDerivationIdentity.build(
        observation_key=observation.observation_key,
        scoring_policy_version=config.policy_version,
        scoring_policy_digest=scoring_policy_digest,
        formula_version=config.formula_version,
    )
    payload = observation.payload
    acceptance_evidence = payload.get("acceptance_evidence")
    derived = derive_bound_score(
        acceptance_evidence if isinstance(acceptance_evidence, dict) else None,
        config,
    )
    score_payload = {
        "issue": observation.issue_number,
        "cat": "eval",
        "evt": "score_observed",
        "label": "Nicht bindende Qualitätsbeobachtung",
        "observation_key": observation.observation_key,
        "evidence_digest": observation.evidence_digest,
        "score_key": identity.score_key,
        "scoring_policy_version": config.policy_version,
        "scoring_policy_digest": scoring_policy_digest,
        "formula_version": config.formula_version,
        "evidence_origin": observation.evidence_origin,
        "observation_schema": observation.observation_schema,
        "gate_blocked": _gate_blocked(payload.get("gate_results")),
        "evaluation_subject": payload.get("evaluation_subject"),
        **derived,
    }
    return ScoreDerivationRecord(
        score_key=identity.score_key,
        observation_key=observation.observation_key,
        scoring_policy_version=config.policy_version,
        scoring_policy_digest=scoring_policy_digest,
        formula_version=config.formula_version,
        score=float(score_payload["score"]) if score_payload["score"] is not None else None,
        issue_number=observation.issue_number,
        evidence_origin=observation.evidence_origin,
        observation_schema=observation.observation_schema,
        payload=score_payload,
        derived_at=observation.observed_at,
    )


def _gate_blocked(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return any(
        isinstance(result, dict)
        and result.get("authority") == "required"
        and result.get("passed") is False
        for result in value
    )
