from __future__ import annotations

import copy
from typing import Any

import pytest

from samuel.core.evaluation_observation import (
    EvaluationObservationIdentity,
    ScoreDerivationIdentity,
    validate_completed_observation,
)
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.slices.evaluation.observation_store import (
    EvaluationObservationStore,
    ObservationConflictError,
)


def _subject() -> EvaluationSubject:
    return EvaluationSubject(
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="gates.v1",
        policy_digest="sha256:" + "d" * 64,
    )


def test_observation_key_binds_subject_policy_and_evidence() -> None:
    identity = EvaluationObservationIdentity.build(
        subject=_subject(),
        gate_results=[{"gate": 11, "status": "passed"}],
        acceptance_evidence={"results": [{"criterion_id": "AC-1", "status": "passed"}]},
    )
    changed = EvaluationObservationIdentity.build(
        subject=_subject(),
        gate_results=[{"gate": 11, "status": "failed"}],
        acceptance_evidence={"results": [{"criterion_id": "AC-1", "status": "failed"}]},
    )

    assert identity.observation_key != changed.observation_key
    assert identity.as_dict()["evaluation_subject"] == _subject().as_dict()


def test_formula_replay_uses_distinct_score_key_for_same_observation() -> None:
    common = {
        "observation_key": "sha256:" + "e" * 64,
        "scoring_policy_version": "eval.v1",
        "scoring_policy_digest": "sha256:" + "f" * 64,
    }
    old = ScoreDerivationIdentity.build(**common, formula_version="legacy.v1")
    new = ScoreDerivationIdentity.build(**common, formula_version="bound.v2")

    assert old.observation_key == new.observation_key
    assert old.score_key != new.score_key


def test_completed_observation_validation_rejects_tampered_authority_or_identity() -> None:
    subject = _subject()
    gate_results = [
        {
            "gate": 11,
            "passed": True,
            "executed": True,
            "status": "passed",
            "reason_code": "gate_11_passed",
            "authority": "required",
            "evaluation_subject": subject.as_dict(),
        }
    ]
    acceptance = {
        "evaluation_subject": subject.as_dict(),
        "contract": {"contract_hash": subject.contract_hash},
        "results": [],
    }
    identity = EvaluationObservationIdentity.build(
        subject=subject,
        gate_results=gate_results,
        acceptance_evidence=acceptance,
    )
    payload: dict[str, Any] = {
        "evaluation_subject": subject.as_dict(),
        "gate_results": gate_results,
        "acceptance_evidence": acceptance,
        "gate_result_schema_version": 2,
        "observation_schema_version": identity.schema_version,
        "observation_key": identity.observation_key,
        "evidence_digest": identity.evidence_digest,
    }

    assert validate_completed_observation(payload) == (subject, identity)

    missing_gate_schema = dict(payload)
    missing_gate_schema.pop("gate_result_schema_version")
    with pytest.raises(ValueError, match="gate-result schema"):
        validate_completed_observation(missing_gate_schema)

    tampered_gate_results = copy.deepcopy(gate_results)
    tampered_gate_results[0]["authority"] = "unknown"
    tampered = dict(payload, gate_results=tampered_gate_results)
    with pytest.raises(ValueError, match="invalid authority"):
        validate_completed_observation(tampered)

    tampered = copy.deepcopy(payload)
    tampered["observation_key"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="observation_key"):
        validate_completed_observation(tampered)


def test_observation_store_is_idempotent_and_rejects_conflicts(tmp_path) -> None:
    store = EvaluationObservationStore(tmp_path)
    observation = {
        "observation_key": "sha256:" + "1" * 64,
        "evidence_digest": "sha256:" + "2" * 64,
        "evaluation_subject": _subject().as_dict(),
    }

    assert store.record_observation(observation) == "created"
    reloaded = EvaluationObservationStore(tmp_path)
    assert reloaded.record_observation(copy.deepcopy(observation)) == "duplicate"

    conflicting = dict(observation, evidence_digest="sha256:" + "3" * 64)
    with pytest.raises(ObservationConflictError, match="conflicting"):
        reloaded.record_observation(conflicting)


def test_score_requires_its_bound_raw_observation(tmp_path) -> None:
    store = EvaluationObservationStore(tmp_path)
    score = {
        "score_key": "sha256:" + "4" * 64,
        "observation_key": "sha256:" + "5" * 64,
        "score": 1.0,
    }

    with pytest.raises(ObservationConflictError, match="no stored raw observation"):
        store.record_score(score)

    store.record_observation(
        {
            "observation_key": score["observation_key"],
            "evidence_digest": "sha256:" + "6" * 64,
        }
    )
    assert store.record_score(score) == "created"
    assert store.record_score(score) == "duplicate"
