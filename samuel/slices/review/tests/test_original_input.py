from __future__ import annotations

from dataclasses import replace

import pytest

from samuel.core.bus import Bus, scrub_secrets
from samuel.core.commands import ReviewCommand
from samuel.core.errors import SCMRevisionError
from samuel.core.events import Event
from samuel.core.review import text_digest
from samuel.core.types import canonical_digest
from samuel.slices.review.handler import ReviewHandler
from samuel.slices.review.tests.test_handler import MockLLM, MockSCM, _payload


def reference(payload: dict, correlation: str = "attempt-a") -> dict:
    return {
        "kind": "original_diff",
        "subject_sha256": canonical_digest(payload["evaluation_subject"]),
        "sha256": text_digest(payload["diff"]),
        "correlation_id": correlation,
    }


@pytest.mark.parametrize("value", ["***REDACTED***", "+changed", "old attempt report"])
def test_replacement_cannot_be_reviewed_or_forwarded(value: str) -> None:
    bus = Bus()
    events: list[Event] = []
    bus.subscribe("ReviewBlocked", events.append)
    scm = MockSCM()
    llm = MockLLM()
    payload = _payload(scm)
    payload["diff"] = value
    result = ReviewHandler(bus, scm=scm, llm=llm).handle(ReviewCommand(payload=payload))
    assert result["reason_code"] == "artifact_digest_mismatch"
    assert llm.prompts == []
    assert scm.posted == []
    assert result["input_identity"]["supplied_sha256"] == text_digest(value)
    assert result["input_identity"]["original_sha256"] == text_digest(scm.original_diff)
    assert value not in str(events[0].payload)


def test_missing_original_does_not_fall_back_to_supplied_report() -> None:
    class Missing(MockSCM):
        def compare_commits(self, *args, **kwargs):
            raise SCMRevisionError("unknown_commit", "private token must not be copied")

    scm = Missing()
    llm = MockLLM()
    result = ReviewHandler(Bus(), scm=scm, llm=llm).handle(ReviewCommand(payload=_payload(scm)))
    assert result["reason_code"] == "original_input_missing"
    assert llm.prompts == []
    assert "private token" not in str(result)


def test_review_without_original_source_never_calls_provider() -> None:
    payload = _payload(MockSCM())
    llm = MockLLM()
    result = ReviewHandler(Bus(), llm=llm).handle(ReviewCommand(payload=payload))
    assert result["reason_code"] == "original_input_missing"
    assert llm.prompts == []


def test_review_comparison_uses_configured_gate_limit() -> None:
    class Limited(MockSCM):
        def compare_commits(self, base_sha, head_sha, *, max_diff_bytes):
            assert max_diff_bytes == 12_345
            return super().compare_commits(base_sha, head_sha, max_diff_bytes=max_diff_bytes)

    scm = Limited()
    result = ReviewHandler(Bus(), scm=scm, llm=MockLLM(), max_diff_bytes=12_345).handle(
        ReviewCommand(payload=_payload(scm))
    )
    assert result["reviewed"] is True


def test_scrubbed_projection_has_separate_identity_and_is_rejected() -> None:
    scm = MockSCM()
    scm.original_diff = '+key = "sk-' + "z" * 24 + '"'
    payload = _payload(scm)
    payload["diff"] = scrub_secrets(scm.original_diff)
    assert payload["diff"] != scm.original_diff
    llm = MockLLM()
    result = ReviewHandler(Bus(), scm=scm, llm=llm).handle(ReviewCommand(payload=payload))
    assert result["reason_code"] == "redacted_projection_not_allowed"
    assert (
        result["input_identity"]["original_sha256"] != result["input_identity"]["supplied_sha256"]
    )
    assert scm.original_diff not in str(result)
    assert llm.prompts == []


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("kind", "redacted_evidence", "redacted_projection_not_allowed"),
        ("kind", "digest_reference", "redacted_projection_not_allowed"),
        ("subject_sha256", "sha256:" + "c" * 64, "wrong_subject"),
        ("correlation_id", "other-attempt", "wrong_subject"),
        ("sha256", "sha256:" + "e" * 64, "artifact_digest_mismatch"),
    ],
)
def test_reference_cannot_change_role_subject_attempt_or_digest(field, value, reason) -> None:
    scm = MockSCM()
    payload = _payload(scm)
    payload["diff_reference"] = {**reference(payload), field: value}
    llm = MockLLM()
    result = ReviewHandler(Bus(), scm=scm, llm=llm).handle(
        ReviewCommand(payload=payload, correlation_id="attempt-a")
    )
    assert result["reason_code"] == reason
    assert llm.prompts == []


@pytest.mark.parametrize("field", ["repository", "base_sha", "head_sha"])
def test_comparison_must_belong_to_the_exact_subject(field) -> None:
    class Wrong(MockSCM):
        def compare_commits(self, *args, **kwargs):
            comparison = super().compare_commits(*args, **kwargs)
            return replace(
                comparison,
                **{field: "https://other.example/repo" if field == "repository" else "f" * 40},
            )

    scm = Wrong()
    llm = MockLLM()
    result = ReviewHandler(Bus(), scm=scm, llm=llm).handle(ReviewCommand(payload=_payload(scm)))
    assert result["reason_code"] == "wrong_subject"
    assert llm.prompts == []


def test_actual_original_with_redaction_words_is_not_a_projection() -> None:
    scm = MockSCM()
    scm.original_diff = '+placeholder = "***REDACTED***"'
    payload = _payload(scm)
    payload["diff_reference"] = reference(payload)
    llm = MockLLM()
    result = ReviewHandler(Bus(), scm=scm, llm=llm).handle(
        ReviewCommand(payload=payload, correlation_id="attempt-a")
    )
    assert result["reviewed"] is True
    assert scm.original_diff in llm.prompts[0]
