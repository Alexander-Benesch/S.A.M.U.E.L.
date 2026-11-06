from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from samuel.core.config import EvalSchema, GatesConfigSchema
from samuel.core.evaluation_subject import (
    EvaluationSubject,
    canonical_contract_text,
    contract_hash,
    gate_policy_binding,
    policy_digest,
)


def _subject() -> EvaluationSubject:
    return EvaluationSubject(
        repository="https://scm.example/owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="2026-08-24.v1",
        policy_digest="sha256:" + "d" * 64,
    )


def test_subject_is_immutable_and_round_trips() -> None:
    subject = _subject()

    assert EvaluationSubject.from_dict(subject.as_dict()) == subject
    with pytest.raises(FrozenInstanceError):
        subject.head_sha = "e" * 40  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", ""),
        ("base_sha", "main"),
        ("head_sha", "ABCDEF" * 7),
        ("contract_hash", "c" * 64),
        ("policy_version", " "),
        ("policy_digest", "sha256:invalid"),
    ],
)
def test_subject_rejects_ambiguous_identity(field: str, value: str) -> None:
    values = _subject().as_dict()
    values[field] = value

    with pytest.raises(ValueError):
        EvaluationSubject.from_dict(values)


def test_contract_hash_canonicalizes_newlines_unicode_and_trailing_space() -> None:
    decomposed = "## Plan\r\n- [ ] Cafe\u0301  \r\n"
    composed = "\n## Plan\n- [ ] Café\n\n"

    assert canonical_contract_text(decomposed) == "## Plan\n- [ ] Café\n"
    assert contract_hash(decomposed) == contract_hash(composed)


def test_policy_digest_is_stable_across_mapping_order() -> None:
    assert policy_digest({"required": [1, 2], "version": "v1"}) == policy_digest(
        {"version": "v1", "required": [1, 2]}
    )


def test_gate_policy_digest_binds_effective_scm_required_context() -> None:
    product = gate_policy_binding(
        GatesConfigSchema(),
        EvalSchema(),
        None,
        scm_policy={
            "provider": "gitea",
            "required_status_context": "CI / lint-and-test (pull_request)",
        },
    )
    demo = gate_policy_binding(
        GatesConfigSchema(),
        EvalSchema(),
        None,
        scm_policy={
            "required_status_context": "CI / demo-tests (pull_request)",
            "provider": "gitea",
        },
    )

    assert product["policy_version"] == demo["policy_version"]
    assert product["policy_digest"] != demo["policy_digest"]
