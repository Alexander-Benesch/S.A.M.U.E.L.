from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from tools.preflight_rollout_evidence import (
    PreflightRolloutEvidenceError,
    load_and_validate_preflight_rollout_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "rollout" / "issue-620.json"
SCHEMA = ROOT / "docs" / "rollout" / "issue-620.schema.json"


def _document() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(EVIDENCE.read_text(encoding="utf-8")))


def _case(document: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in document["cases"] if case["id"] == case_id)


def _write(tmp_path: Path, document: dict[str, Any]) -> tuple[Path, Path]:
    evidence = tmp_path / EVIDENCE.name
    schema = tmp_path / SCHEMA.name
    evidence.write_text(json.dumps(document), encoding="utf-8")
    schema.write_bytes(SCHEMA.read_bytes())
    return evidence, schema


def test_checked_in_preflight_rollout_evidence_is_valid() -> None:
    load_and_validate_preflight_rollout_evidence(EVIDENCE, SCHEMA)


def test_each_required_case_is_mandatory(tmp_path: Path) -> None:
    document = _document()
    document["cases"].pop()
    evidence, schema = _write(tmp_path, document)

    with pytest.raises(PreflightRolloutEvidenceError, match="exactly six cases"):
        load_and_validate_preflight_rollout_evidence(evidence, schema)


def test_observation_digest_is_recomputed_from_exact_evidence(tmp_path: Path) -> None:
    document = _document()
    _case(document, "scope_fail")["gate_results"][0]["reason"] = "tampered"
    evidence, schema = _write(tmp_path, document)

    with pytest.raises(PreflightRolloutEvidenceError, match="observation is invalid"):
        load_and_validate_preflight_rollout_evidence(evidence, schema)


def test_scope_block_cannot_claim_gate_11_execution(tmp_path: Path) -> None:
    document = _document()
    gate_11 = next(
        gate for gate in _case(document, "scope_fail")["gate_results"] if gate["gate"] == 11
    )
    gate_11.update(passed=True, executed=True, status="passed", reason_code="gate_11_passed")
    evidence, schema = _write(tmp_path, document)

    with pytest.raises(PreflightRolloutEvidenceError, match=r"observation is invalid|gate\[11\]"):
        load_and_validate_preflight_rollout_evidence(evidence, schema)


@pytest.mark.parametrize("case_id", ["scope_fail", "syntax_fail", "freshness_unknown"])
def test_preflight_blocks_require_zero_verifier_dispatches(
    tmp_path: Path,
    case_id: str,
) -> None:
    document = _document()
    _case(document, case_id)["verifier_dispatches"] = 1
    evidence, schema = _write(tmp_path, document)

    with pytest.raises(PreflightRolloutEvidenceError, match="verifier_dispatches"):
        load_and_validate_preflight_rollout_evidence(evidence, schema)


def test_subject_unavailable_cannot_carry_fabricated_subject(tmp_path: Path) -> None:
    document = _document()
    unavailable = _case(document, "subject_unavailable")
    unavailable["subject"] = deepcopy(_case(document, "success")["subject"])
    evidence, schema = _write(tmp_path, document)

    with pytest.raises(PreflightRolloutEvidenceError, match="subject must be None"):
        load_and_validate_preflight_rollout_evidence(evidence, schema)


def test_gate_11_only_failure_must_remain_healable(tmp_path: Path) -> None:
    document = _document()
    _case(document, "gate11_healable")["healing"]["classification"] = "not_healable"
    evidence, schema = _write(tmp_path, document)

    with pytest.raises(PreflightRolloutEvidenceError, match="healing.classification"):
        load_and_validate_preflight_rollout_evidence(evidence, schema)


def test_evidence_binds_exact_schema_bytes(tmp_path: Path) -> None:
    document = _document()
    document["schema_digest"] = "sha256:" + "0" * 64
    evidence, schema = _write(tmp_path, document)

    with pytest.raises(PreflightRolloutEvidenceError, match="schema_digest"):
        load_and_validate_preflight_rollout_evidence(evidence, schema)
