from __future__ import annotations

from datetime import datetime, timezone

from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.external_evidence import (
    SCMCheckExpectations,
    SCMCheckJob,
    SCMCheckObservation,
    SCMCheckReference,
    SCMCommitStatus,
    assess_scm_check_evidence,
)


def _subject(*, head: str = "b" * 40) -> EvaluationSubject:
    return EvaluationSubject(
        repository="https://gitea.example/owner/repo",
        base_sha="a" * 40,
        head_sha=head,
        contract_hash="sha256:" + "c" * 64,
        policy_version="gates.v1",
        policy_digest="sha256:" + "d" * 64,
    )


def _reference() -> SCMCheckReference:
    return SCMCheckReference(provider="gitea", repository="owner/repo", run_id=704)


def _observation(**overrides) -> SCMCheckObservation:
    values = {
        "provider": "gitea",
        "provider_instance": "https://gitea.example",
        "repository": "owner/repo",
        "run_id": 704,
        "requested_attempt": 1,
        "reported_attempt": 1,
        "event": "pull_request",
        "head_sha": "b" * 40,
        "pull_request_number": 7,
        "pull_request_base_sha": "a" * 40,
        "pull_request_head_sha": "b" * 40,
        "head_branch": "feature/evidence",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-09-18T09:59:00Z",
        "completed_at": "2026-09-18T10:00:00Z",
        "workflow_path": ".gitea/workflows/ci.yml",
        "workflow_ref": "refs/pull/7/head",
        "workflow_blob_sha": "e" * 40,
        "run_url": "https://gitea.example/owner/repo/actions/runs/704",
        "jobs": (
            SCMCheckJob(
                job_id=9,
                name="tests",
                status="completed",
                conclusion="success",
                runner_id=2,
                runner_name="runner",
                runner_labels=("linux",),
                started_at="2026-09-18T09:59:00Z",
                completed_at="2026-09-18T10:00:00Z",
                url="https://gitea.example/owner/repo/actions/runs/704/jobs/9",
            ),
        ),
        "commit_statuses": (
            SCMCommitStatus(
                status_id=11,
                context="CI / tests (pull_request)",
                state="success",
                target_url="/owner/repo/actions/runs/704/jobs/9",
                creator="ci-bot",
                created_at="2026-09-18T10:00:00Z",
                updated_at="2026-09-18T10:00:00Z",
            ),
        ),
    }
    values.update(overrides)
    return SCMCheckObservation(**values)


def _expectations(*, max_age_seconds: int = 3600) -> SCMCheckExpectations:
    return SCMCheckExpectations(
        status_context="CI / tests (pull_request)",
        workflow_path=".gitea/workflows/ci.yml",
        event="pull_request",
        max_age_seconds=max_age_seconds,
    )


def test_matching_provider_facts_are_qualified_but_never_authoritative() -> None:
    assessment = assess_scm_check_evidence(
        _observation(),
        reference=_reference(),
        subject=_subject(),
        expectations=_expectations(),
        now=datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc),
    )

    assert assessment.verdict == "advisory_qualified"
    assert assessment.required_effect is False
    assert assessment.dispatch_effect is False
    assert assessment.mutation_effect is False
    assert {finding.code for finding in assessment.findings} >= {
        "verification_request_binding_unproven",
        "runner_environment_unproven",
        "toolchain_unproven",
        "provider_response_unsigned",
    }
    statement = assessment.as_in_toto_statement()
    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["subject"][0]["digest"]["gitCommit"] == "b" * 40
    assert statement["predicate"]["requiredEffect"] is False
    assert statement["predicate"]["authority"] == "none"
    assert statement["predicate"]["evaluationSubject"] == _subject().as_dict()
    assert statement["predicate"]["providerObservation"] == _observation().as_dict()


def test_pull_request_base_and_head_bindings_are_checked_independently() -> None:
    assessment = assess_scm_check_evidence(
        _observation(
            pull_request_base_sha="f" * 40,
            pull_request_head_sha="e" * 40,
        ),
        reference=_reference(),
        subject=_subject(),
        expectations=_expectations(),
        now=datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc),
    )

    assert assessment.verdict == "advisory_rejected"
    assert {finding.code for finding in assessment.findings} >= {
        "base_sha_mismatch",
        "contradictory_sources",
    }


def test_wrong_subject_status_and_workflow_are_rejected_without_mutation_effect() -> None:
    observation = _observation(
        head_sha="f" * 40,
        workflow_path=".gitea/workflows/other.yml",
        commit_statuses=(
            SCMCommitStatus(
                status_id=11,
                context="CI / other (pull_request)",
                state="failure",
                target_url="/owner/repo/actions/runs/999/jobs/9",
                creator=None,
                created_at="2026-09-18T10:00:00Z",
                updated_at="2026-09-18T10:00:00Z",
            ),
        ),
    )
    assessment = assess_scm_check_evidence(
        observation,
        reference=_reference(),
        subject=_subject(),
        expectations=_expectations(),
        now=datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc),
    )

    codes = {finding.code for finding in assessment.findings}
    assert assessment.verdict == "advisory_rejected"
    assert {"head_sha_mismatch", "workflow_path_mismatch", "status_context_missing"} <= codes
    assert (
        assessment.required_effect
        is assessment.dispatch_effect
        is assessment.mutation_effect
        is False
    )


def test_stale_missing_unknown_and_contradictory_facts_remain_distinct() -> None:
    observation = _observation(
        reported_attempt=None,
        conclusion="success",
        jobs=(
            SCMCheckJob(
                job_id=9,
                name="tests",
                status="completed",
                conclusion="failure",
                runner_id=None,
                runner_name=None,
                runner_labels=(),
                started_at=None,
                completed_at="2026-09-17T10:00:00Z",
                url=None,
            ),
        ),
        missing_facts=("run_attempt", "runner_labels"),
        unknown_fields=("future_field",),
    )
    assessment = assess_scm_check_evidence(
        observation,
        reference=_reference(),
        subject=_subject(),
        expectations=_expectations(max_age_seconds=60),
        now=datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc),
    )

    findings = [finding.as_dict() for finding in assessment.findings]
    assert {finding["code"] for finding in findings} >= {
        "run_attempt_unproven",
        "missing_run_attempt",
        "missing_runner_labels",
        "unknown_provider_fields",
        "contradictory_sources",
        "stale_evidence",
    }
    assert len(findings) == len(
        {(finding["code"], finding["severity"], finding["origin"]) for finding in findings}
    )


def test_observation_and_assessment_digests_are_deterministic() -> None:
    first = _observation()
    second = _observation()
    first_assessment = assess_scm_check_evidence(
        first,
        reference=_reference(),
        subject=_subject(),
        expectations=_expectations(),
        now=datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc),
    )
    second_assessment = assess_scm_check_evidence(
        second,
        reference=_reference(),
        subject=_subject(),
        expectations=_expectations(),
        now=datetime(2026, 9, 18, 10, 6, tzinfo=timezone.utc),
    )

    assert first.evidence_digest == second.evidence_digest
    assert first_assessment.assessment_key == second_assessment.assessment_key
