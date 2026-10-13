from __future__ import annotations

import json

import pytest

from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.review import (
    classify_review_contract_error,
    parse_review_decision,
    text_digest,
)
from samuel.core.types import canonical_digest


def _subject() -> EvaluationSubject:
    return EvaluationSubject(
        repository="https://scm.example/owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="preflight.v2",
        policy_digest="sha256:" + "d" * 64,
    )


def _document(*, decision: str = "pass", findings: list[dict] | None = None) -> dict:
    subject = _subject()
    return {
        "schema_version": 2,
        "decision": decision,
        "subject_sha256": canonical_digest(subject.as_dict()),
        "diff_sha256": text_digest("diff"),
        "policy": {"version": subject.policy_version, "digest": subject.policy_digest},
        "tool": {"kind": "llm", "name": "review"},
        "prompt_sha256": text_digest("prompt"),
        "findings": findings or [],
    }


def _parse(document: dict):
    return parse_review_decision(
        json.dumps(document),
        expected_subject=_subject(),
        expected_diff_sha256=text_digest("diff"),
        expected_prompt_sha256=text_digest("prompt"),
        expected_tool_kind="llm",
        expected_tool_name="review",
        producer_model="model-1",
    )


def test_parses_exact_bound_pass() -> None:
    result = _parse(
        _document(
            findings=[{"severity": "suggestion", "code": "naming", "summary": "Use a clearer name"}]
        )
    )

    assert result.decision == "pass"
    assert result.producer_model == "model-1"
    assert result.subject == _subject()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(extra=True),
        lambda row: row.update(diff_sha256=text_digest("other")),
        lambda row: row.update(subject_sha256=canonical_digest({"other": "subject"})),
        lambda row: row["policy"].update(digest="sha256:" + "e" * 64),
        lambda row: row["tool"].update(name="other"),
        lambda row: row.update(prompt_sha256=text_digest("other")),
    ],
)
def test_rejects_unknown_or_drifted_bindings(mutation) -> None:
    document = _document()
    mutation(document)

    with pytest.raises(ValueError):
        _parse(document)


def test_rejects_prose_transport_success() -> None:
    with pytest.raises(ValueError, match="not one JSON document"):
        parse_review_decision(
            "LGTM",
            expected_subject=_subject(),
            expected_diff_sha256=text_digest("diff"),
            expected_prompt_sha256=text_digest("prompt"),
            expected_tool_kind="llm",
            expected_tool_name="review",
        )


def test_rejects_pass_with_blocker_and_block_without_blocker() -> None:
    blocker = [{"severity": "blocker", "code": "unsafe", "summary": "Unsafe change"}]
    with pytest.raises(ValueError, match="pass review"):
        _parse(_document(findings=blocker))
    with pytest.raises(ValueError, match="needs at least one"):
        _parse(_document(decision="block"))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(schema_version="1"),
        lambda row: row.update(decision=1),
        lambda row: row.update(subject_sha256=1),
        lambda row: row["policy"].update(version=1),
        lambda row: row["tool"].update(name=1),
        lambda row: row.update(
            findings=[{"severity": "suggestion", "code": 1, "summary": "typed"}]
        ),
        lambda row: row.update(
            findings=[{"severity": "suggestion", "code": "typed", "summary": 1}]
        ),
    ],
)
def test_rejects_type_coercion(mutation) -> None:
    document = _document()
    mutation(document)

    with pytest.raises(ValueError):
        _parse(document)


def test_rejects_duplicate_json_fields() -> None:
    raw = json.dumps(_document()).replace(
        '"schema_version": 2', '"schema_version": 2, "schema_version": 2'
    )

    with pytest.raises(ValueError, match="duplicate field"):
        parse_review_decision(
            raw,
            expected_subject=_subject(),
            expected_diff_sha256=text_digest("diff"),
            expected_prompt_sha256=text_digest("prompt"),
            expected_tool_kind="llm",
            expected_tool_name="review",
        )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("review response is not one JSON document", "not_json_document"),
        ("review response contains duplicate field 'x'", "duplicate_field"),
        ("review decision must contain exactly []", "closed_schema_mismatch"),
        ("review decision belongs to another prompt", "binding_mismatch"),
        ("pass review cannot contain blocker findings", "decision_findings_mismatch"),
        ("review schema version is invalid", "field_value_invalid"),
    ],
)
def test_contract_error_class_is_bounded(message: str, expected: str) -> None:
    assert classify_review_contract_error(ValueError(message)) == expected
