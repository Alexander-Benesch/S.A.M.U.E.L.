"""Stable identities for bound gate observations and score derivations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.gate_metadata import (
    EVALUATION_OBSERVATION_SCHEMA_VERSION,
    GATE_RESULT_SCHEMA_VERSION,
    GATE_STATUSES,
)

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REASON_CODE_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
CURRENT_OBSERVATION_SCHEMA_VERSION = EVALUATION_OBSERVATION_SCHEMA_VERSION
_SUPPORTED_OBSERVATION_SCHEMA_VERSIONS = frozenset({1, CURRENT_OBSERVATION_SCHEMA_VERSION})


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _require_digest(value: str, field_name: str) -> None:
    if not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_text(value: str, field_name: str) -> None:
    if not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field_name} must be a canonical non-empty string")


@dataclass(frozen=True)
class EvaluationObservationIdentity:
    """Identity of one complete evidence set for one immutable subject."""

    schema_version: int
    subject: EvaluationSubject
    evidence_digest: str
    observation_key: str

    def __post_init__(self) -> None:
        if self.schema_version not in _SUPPORTED_OBSERVATION_SCHEMA_VERSIONS:
            raise ValueError("unsupported evaluation observation schema")
        _require_digest(self.evidence_digest, "evidence_digest")
        _require_digest(self.observation_key, "observation_key")
        expected = canonical_digest(
            {
                "schema_version": self.schema_version,
                "evaluation_subject": self.subject.as_dict(),
                "gate_policy_version": self.subject.policy_version,
                "gate_policy_digest": self.subject.policy_digest,
                "evidence_digest": self.evidence_digest,
            }
        )
        if self.observation_key != expected:
            raise ValueError("observation_key is not bound to subject, policy and evidence")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_subject": self.subject.as_dict(),
            "evidence_digest": self.evidence_digest,
            "observation_key": self.observation_key,
        }

    @classmethod
    def build(
        cls,
        *,
        subject: EvaluationSubject,
        gate_results: list[dict[str, Any]],
        acceptance_evidence: dict[str, Any] | None,
        schema_version: int = CURRENT_OBSERVATION_SCHEMA_VERSION,
        gate_result_schema_version: int | None = None,
    ) -> EvaluationObservationIdentity:
        evidence_payload: dict[str, Any] = {
            "gate_results": gate_results,
            "acceptance_evidence": acceptance_evidence,
        }
        if schema_version >= 2:
            effective_gate_schema = gate_result_schema_version or GATE_RESULT_SCHEMA_VERSION
            evidence_payload["gate_result_schema_version"] = effective_gate_schema
        evidence_digest = canonical_digest(evidence_payload)
        observation_key = canonical_digest(
            {
                "schema_version": schema_version,
                "evaluation_subject": subject.as_dict(),
                "gate_policy_version": subject.policy_version,
                "gate_policy_digest": subject.policy_digest,
                "evidence_digest": evidence_digest,
            }
        )
        return cls(
            schema_version=schema_version,
            subject=subject,
            evidence_digest=evidence_digest,
            observation_key=observation_key,
        )


@dataclass(frozen=True)
class ScoreDerivationIdentity:
    """Identity of one formula applied to one bound raw observation."""

    schema_version: int
    observation_key: str
    scoring_policy_version: str
    scoring_policy_digest: str
    formula_version: str
    score_key: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported score derivation schema")
        _require_digest(self.observation_key, "observation_key")
        _require_text(self.scoring_policy_version, "scoring_policy_version")
        _require_digest(self.scoring_policy_digest, "scoring_policy_digest")
        _require_text(self.formula_version, "formula_version")
        expected = canonical_digest(
            {
                "schema_version": self.schema_version,
                "observation_key": self.observation_key,
                "scoring_policy_version": self.scoring_policy_version,
                "scoring_policy_digest": self.scoring_policy_digest,
                "formula_version": self.formula_version,
            }
        )
        if self.score_key != expected:
            raise ValueError("score_key is not bound to its observation and formula")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def build(
        cls,
        *,
        observation_key: str,
        scoring_policy_version: str,
        scoring_policy_digest: str,
        formula_version: str,
    ) -> ScoreDerivationIdentity:
        score_key = canonical_digest(
            {
                "schema_version": 1,
                "observation_key": observation_key,
                "scoring_policy_version": scoring_policy_version,
                "scoring_policy_digest": scoring_policy_digest,
                "formula_version": formula_version,
            }
        )
        return cls(
            schema_version=1,
            observation_key=observation_key,
            scoring_policy_version=scoring_policy_version,
            scoring_policy_digest=scoring_policy_digest,
            formula_version=formula_version,
            score_key=score_key,
        )


def validate_completed_observation(
    payload: dict[str, Any],
) -> tuple[EvaluationSubject, EvaluationObservationIdentity]:
    """Validate a complete event before passive or active consumers use it."""

    raw_subject = payload.get("evaluation_subject")
    gate_results = payload.get("gate_results")
    acceptance_evidence = payload.get("acceptance_evidence")
    if not isinstance(raw_subject, dict) or not isinstance(gate_results, list):
        raise ValueError("gate observation lacks subject or gate results")
    if any(not isinstance(item, dict) for item in gate_results):
        raise ValueError("gate observation contains invalid gate evidence")
    subject = EvaluationSubject.from_dict(raw_subject)
    subject_dict = subject.as_dict()
    schema_version = payload.get("observation_schema_version")
    if schema_version not in _SUPPORTED_OBSERVATION_SCHEMA_VERSIONS:
        raise ValueError("gate observation has an unsupported schema")
    for result in gate_results:
        if result.get("evaluation_subject") != subject_dict:
            raise ValueError("gate evidence belongs to a different evaluation subject")
        if result.get("authority") not in {"required", "optional"}:
            raise ValueError("gate evidence has invalid authority")
        if schema_version >= 2:
            _validate_gate_result_v2(result)
    gate_result_schema_version = payload.get(
        "gate_result_schema_version", 1 if schema_version == 1 else None
    )
    if schema_version >= 2 and gate_result_schema_version != GATE_RESULT_SCHEMA_VERSION:
        raise ValueError("gate observation has an unsupported gate-result schema")
    if acceptance_evidence is not None:
        if not isinstance(acceptance_evidence, dict):
            raise ValueError("acceptance evidence has invalid shape")
        if acceptance_evidence.get("evaluation_subject") != subject_dict:
            raise ValueError("acceptance evidence belongs to a different evaluation subject")
        contract = acceptance_evidence.get("contract")
        if not isinstance(contract, dict) or contract.get("contract_hash") != subject.contract_hash:
            raise ValueError("acceptance evidence belongs to a different contract")

    identity = EvaluationObservationIdentity.build(
        subject=subject,
        gate_results=gate_results,
        acceptance_evidence=acceptance_evidence,
        schema_version=schema_version,
        gate_result_schema_version=gate_result_schema_version,
    )
    if payload.get("observation_schema_version") != identity.schema_version:
        raise ValueError("published observation schema does not match its evidence")
    if payload.get("observation_key") != identity.observation_key:
        raise ValueError("published observation_key does not match its evidence")
    if payload.get("evidence_digest") != identity.evidence_digest:
        raise ValueError("published evidence_digest does not match its evidence")
    return subject, identity


def _validate_gate_result_v2(result: dict[str, Any]) -> None:
    """Reject ambiguous PASS/FAIL evidence in the tri-state observation series."""

    executed = result.get("executed")
    passed = result.get("passed")
    status = result.get("status")
    reason_code = result.get("reason_code")
    if type(executed) is not bool:
        raise ValueError("gate evidence lacks an explicit execution state")
    if status not in GATE_STATUSES:
        raise ValueError("gate evidence has invalid status")
    if not isinstance(reason_code, str) or _REASON_CODE_RE.fullmatch(reason_code) is None:
        raise ValueError("gate evidence lacks a canonical reason code")
    if executed:
        if type(passed) is not bool or status == "skipped_precondition":
            raise ValueError("executed gate evidence has an invalid result state")
        if status in {"passed", "not_applicable"} and passed is not True:
            raise ValueError("passing gate evidence cannot carry a negative result")
        if status in {"failed", "error", "missing_evidence", "manual_pending", "not_evaluated"}:
            if passed is not False:
                raise ValueError("non-passing gate evidence cannot carry a positive result")
    elif passed is not None or status != "skipped_precondition":
        raise ValueError("non-executed gate evidence is not an explicit precondition skip")


def unavailable_evaluation_key(
    *,
    issue_number: int,
    branch: str,
    correlation_id: str,
    error_code: str,
    subject: EvaluationSubject | None,
) -> str:
    """Idempotent run-local identity when no complete observation can exist."""

    return canonical_digest(
        {
            "schema_version": 1,
            "issue": int(issue_number),
            "branch": branch,
            "correlation_id": correlation_id,
            "error_code": error_code,
            "evaluation_subject": subject.as_dict() if subject is not None else None,
        }
    )
