"""Provider-neutral, advisory-only projection of external SCM check evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from samuel.core.evaluation_observation import canonical_digest
from samuel.core.evaluation_subject import EvaluationSubject

SCM_CHECK_OBSERVATION_SCHEMA = "scm-check-observation.v1"
SCM_CHECK_ASSESSMENT_SCHEMA = "scm-check-assessment.v1"
SCM_CHECK_PREDICATE_TYPE = "https://samuel.dev/attestations/scm-check-assessment/v1"


def _canonical_text(value: str, field: str) -> str:
    normalized = str(value).strip()
    if not normalized or any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError(f"{field} must be a canonical non-empty string")
    if len(normalized) > 4096:
        raise ValueError(f"{field} exceeds the projection limit")
    return normalized


def _optional_text(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    return _canonical_text(value, field)


def _full_sha(value: str, field: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) not in {40, 64} or any(
        char not in "0123456789abcdef" for char in normalized
    ):
        raise ValueError(f"{field} must be a full lowercase Git object ID")
    return normalized


@dataclass(frozen=True)
class SCMCheckReference:
    provider: str
    repository: str
    run_id: int
    attempt: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _canonical_text(self.provider, "provider").lower())
        object.__setattr__(self, "repository", _canonical_text(self.repository, "repository"))
        if isinstance(self.run_id, bool) or self.run_id <= 0:
            raise ValueError("run_id must be a positive integer")
        if isinstance(self.attempt, bool) or self.attempt <= 0:
            raise ValueError("attempt must be a positive integer")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SCMCheckJob:
    job_id: int
    name: str
    status: str
    conclusion: str | None
    runner_id: int | None
    runner_name: str | None
    runner_labels: tuple[str, ...]
    started_at: str | None
    completed_at: str | None
    url: str | None

    def __post_init__(self) -> None:
        if isinstance(self.job_id, bool) or self.job_id <= 0:
            raise ValueError("job_id must be a positive integer")
        if self.runner_id is not None and (isinstance(self.runner_id, bool) or self.runner_id <= 0):
            raise ValueError("runner_id must be a positive integer")
        object.__setattr__(self, "name", _canonical_text(self.name, "job.name"))
        object.__setattr__(self, "status", _canonical_text(self.status, "job.status").lower())
        object.__setattr__(self, "conclusion", _optional_text(self.conclusion, "job.conclusion"))
        object.__setattr__(self, "runner_name", _optional_text(self.runner_name, "job.runner_name"))
        object.__setattr__(
            self,
            "runner_labels",
            tuple(
                sorted({_canonical_text(label, "job.runner_label") for label in self.runner_labels})
            ),
        )
        object.__setattr__(self, "started_at", _optional_text(self.started_at, "job.started_at"))
        object.__setattr__(
            self, "completed_at", _optional_text(self.completed_at, "job.completed_at")
        )
        object.__setattr__(self, "url", _optional_text(self.url, "job.url"))

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["runner_labels"] = list(self.runner_labels)
        return value


@dataclass(frozen=True)
class SCMCommitStatus:
    status_id: int
    context: str
    state: str
    target_url: str | None
    creator: str | None
    created_at: str | None
    updated_at: str | None

    def __post_init__(self) -> None:
        if isinstance(self.status_id, bool) or self.status_id <= 0:
            raise ValueError("status_id must be a positive integer")
        object.__setattr__(self, "context", _canonical_text(self.context, "status.context"))
        object.__setattr__(self, "state", _canonical_text(self.state, "status.state").lower())
        object.__setattr__(self, "target_url", _optional_text(self.target_url, "status.target_url"))
        object.__setattr__(self, "creator", _optional_text(self.creator, "status.creator"))
        object.__setattr__(self, "created_at", _optional_text(self.created_at, "status.created_at"))
        object.__setattr__(self, "updated_at", _optional_text(self.updated_at, "status.updated_at"))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SCMCheckObservation:
    provider: str
    provider_instance: str
    repository: str
    run_id: int
    requested_attempt: int
    reported_attempt: int | None
    event: str
    head_sha: str
    pull_request_number: int | None
    pull_request_base_sha: str | None
    pull_request_head_sha: str | None
    head_branch: str | None
    status: str
    conclusion: str | None
    started_at: str | None
    completed_at: str | None
    workflow_path: str | None
    workflow_ref: str | None
    workflow_blob_sha: str | None
    run_url: str | None
    jobs: tuple[SCMCheckJob, ...]
    commit_statuses: tuple[SCMCommitStatus, ...]
    missing_facts: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    schema: str = SCM_CHECK_OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCM_CHECK_OBSERVATION_SCHEMA:
            raise ValueError("unsupported SCM check observation schema")
        object.__setattr__(self, "provider", _canonical_text(self.provider, "provider").lower())
        object.__setattr__(
            self, "provider_instance", _canonical_text(self.provider_instance, "provider_instance")
        )
        object.__setattr__(self, "repository", _canonical_text(self.repository, "repository"))
        if isinstance(self.run_id, bool) or self.run_id <= 0:
            raise ValueError("run_id must be a positive integer")
        if isinstance(self.requested_attempt, bool) or self.requested_attempt <= 0:
            raise ValueError("requested_attempt must be a positive integer")
        if self.reported_attempt is not None and (
            isinstance(self.reported_attempt, bool) or self.reported_attempt <= 0
        ):
            raise ValueError("reported_attempt must be a positive integer")
        object.__setattr__(self, "event", _canonical_text(self.event, "event").lower())
        object.__setattr__(self, "head_sha", _full_sha(self.head_sha, "head_sha"))
        if self.pull_request_number is not None and (
            isinstance(self.pull_request_number, bool) or self.pull_request_number <= 0
        ):
            raise ValueError("pull_request_number must be a positive integer")
        if self.pull_request_base_sha is not None:
            object.__setattr__(
                self,
                "pull_request_base_sha",
                _full_sha(self.pull_request_base_sha, "pull_request_base_sha"),
            )
        if self.pull_request_head_sha is not None:
            object.__setattr__(
                self,
                "pull_request_head_sha",
                _full_sha(self.pull_request_head_sha, "pull_request_head_sha"),
            )
        object.__setattr__(self, "head_branch", _optional_text(self.head_branch, "head_branch"))
        object.__setattr__(self, "status", _canonical_text(self.status, "status").lower())
        object.__setattr__(self, "conclusion", _optional_text(self.conclusion, "conclusion"))
        object.__setattr__(self, "started_at", _optional_text(self.started_at, "started_at"))
        object.__setattr__(self, "completed_at", _optional_text(self.completed_at, "completed_at"))
        object.__setattr__(
            self, "workflow_path", _optional_text(self.workflow_path, "workflow_path")
        )
        object.__setattr__(self, "workflow_ref", _optional_text(self.workflow_ref, "workflow_ref"))
        if self.workflow_blob_sha is not None:
            object.__setattr__(
                self, "workflow_blob_sha", _full_sha(self.workflow_blob_sha, "workflow_blob_sha")
            )
        object.__setattr__(self, "run_url", _optional_text(self.run_url, "run_url"))
        if any(not isinstance(job, SCMCheckJob) for job in self.jobs):
            raise ValueError("jobs must contain SCMCheckJob values")
        if any(not isinstance(status, SCMCommitStatus) for status in self.commit_statuses):
            raise ValueError("commit_statuses must contain SCMCommitStatus values")
        object.__setattr__(
            self,
            "missing_facts",
            tuple(sorted({_canonical_text(value, "missing_fact") for value in self.missing_facts})),
        )
        object.__setattr__(
            self,
            "unknown_fields",
            tuple(
                sorted({_canonical_text(value, "unknown_field") for value in self.unknown_fields})
            ),
        )

    @property
    def repository_identity(self) -> str:
        return f"{self.provider_instance.rstrip('/')}/{self.repository}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "provider": self.provider,
            "provider_instance": self.provider_instance,
            "repository": self.repository,
            "run_id": self.run_id,
            "requested_attempt": self.requested_attempt,
            "reported_attempt": self.reported_attempt,
            "event": self.event,
            "head_sha": self.head_sha,
            "pull_request_number": self.pull_request_number,
            "pull_request_base_sha": self.pull_request_base_sha,
            "pull_request_head_sha": self.pull_request_head_sha,
            "head_branch": self.head_branch,
            "status": self.status,
            "conclusion": self.conclusion,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "workflow_path": self.workflow_path,
            "workflow_ref": self.workflow_ref,
            "workflow_blob_sha": self.workflow_blob_sha,
            "run_url": self.run_url,
            "jobs": [job.as_dict() for job in self.jobs],
            "commit_statuses": [status.as_dict() for status in self.commit_statuses],
            "missing_facts": list(self.missing_facts),
            "unknown_fields": list(self.unknown_fields),
        }

    @property
    def evidence_digest(self) -> str:
        return canonical_digest(self.as_dict())


@dataclass(frozen=True)
class SCMCheckExpectations:
    status_context: str
    workflow_path: str | None = None
    event: str | None = None
    max_age_seconds: int = 86400

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "status_context", _canonical_text(self.status_context, "status_context")
        )
        object.__setattr__(
            self, "workflow_path", _optional_text(self.workflow_path, "workflow_path")
        )
        event = _optional_text(self.event, "event")
        object.__setattr__(self, "event", event.lower() if event else None)
        if isinstance(self.max_age_seconds, bool) or self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be a positive integer")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceFinding:
    code: str
    severity: Literal["info", "warning", "error"]
    origin: Literal["provider", "assessment"]

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceAssessment:
    subject: EvaluationSubject
    reference: SCMCheckReference
    provider_observation: SCMCheckObservation
    expectations: SCMCheckExpectations
    verdict: Literal["advisory_qualified", "advisory_rejected"]
    findings: tuple[EvidenceFinding, ...]
    schema: str = SCM_CHECK_ASSESSMENT_SCHEMA
    role: Literal["advisory"] = "advisory"
    required_effect: Literal[False] = False
    dispatch_effect: Literal[False] = False
    mutation_effect: Literal[False] = False

    def __post_init__(self) -> None:
        if self.schema != SCM_CHECK_ASSESSMENT_SCHEMA:
            raise ValueError("unsupported SCM check assessment schema")
        if self.reference.provider != self.provider_observation.provider:
            raise ValueError("reference provider differs from observation provider")
        if self.reference.repository != self.provider_observation.repository:
            raise ValueError("reference repository differs from observation repository")
        if self.reference.run_id != self.provider_observation.run_id:
            raise ValueError("reference run differs from observation run")

    @property
    def assessment_key(self) -> str:
        return canonical_digest(
            {
                "schema": self.schema,
                "role": self.role,
                "subject": self.subject.as_dict(),
                "reference": self.reference.as_dict(),
                "expectations": self.expectations.as_dict(),
                "provider_evidence_digest": self.provider_observation.evidence_digest,
                "findings": [finding.as_dict() for finding in self.findings],
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "role": self.role,
            "authority": "none",
            "required_effect": self.required_effect,
            "dispatch_effect": self.dispatch_effect,
            "mutation_effect": self.mutation_effect,
            "verdict": self.verdict,
            "assessment_key": self.assessment_key,
            "subject": self.subject.as_dict(),
            "reference": self.reference.as_dict(),
            "expectations": self.expectations.as_dict(),
            "provider_observation": self.provider_observation.as_dict(),
            "provider_evidence_digest": self.provider_observation.evidence_digest,
            "findings": [finding.as_dict() for finding in self.findings],
        }

    def as_in_toto_statement(self) -> dict[str, Any]:
        return {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "name": self.subject.repository,
                    "digest": {"gitCommit": self.subject.head_sha},
                }
            ],
            "predicateType": SCM_CHECK_PREDICATE_TYPE,
            "predicate": {
                "assessmentKey": self.assessment_key,
                "role": self.role,
                "authority": "none",
                "requiredEffect": self.required_effect,
                "dispatchEffect": self.dispatch_effect,
                "mutationEffect": self.mutation_effect,
                "provider": self.provider_observation.provider,
                "providerInstance": self.provider_observation.provider_instance,
                "repository": self.provider_observation.repository,
                "runId": self.provider_observation.run_id,
                "providerEvidenceDigest": self.provider_observation.evidence_digest,
                "evaluationSubject": self.subject.as_dict(),
                "checkReference": self.reference.as_dict(),
                "expectations": self.expectations.as_dict(),
                "providerObservation": self.provider_observation.as_dict(),
                "verdict": self.verdict,
                "findings": [finding.as_dict() for finding in self.findings],
            },
        }


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def assess_scm_check_evidence(
    observation: SCMCheckObservation,
    *,
    reference: SCMCheckReference,
    subject: EvaluationSubject,
    expectations: SCMCheckExpectations,
    now: datetime | None = None,
) -> EvidenceAssessment:
    findings: list[EvidenceFinding] = []

    def add(
        code: str,
        severity: Literal["info", "warning", "error"],
        origin: Literal["provider", "assessment"] = "assessment",
    ) -> None:
        finding = EvidenceFinding(code=code, severity=severity, origin=origin)
        if finding not in findings:
            findings.append(finding)

    if observation.repository_identity.rstrip("/") != subject.repository.rstrip("/"):
        add("repository_mismatch", "error")
    if observation.head_sha != subject.head_sha:
        add("head_sha_mismatch", "error")
    if (
        observation.pull_request_head_sha
        and observation.pull_request_head_sha != observation.head_sha
    ):
        add("contradictory_sources", "error")
    if observation.pull_request_base_sha is None:
        add("base_sha_unproven", "warning", "provider")
    elif observation.pull_request_base_sha != subject.base_sha:
        add("base_sha_mismatch", "error")
    if observation.reported_attempt is None:
        add("run_attempt_unproven", "warning", "provider")
    elif observation.reported_attempt != reference.attempt:
        add("attempt_mismatch", "error")
    if expectations.event and observation.event != expectations.event:
        add("event_mismatch", "error")
    if expectations.workflow_path and observation.workflow_path != expectations.workflow_path:
        add("workflow_path_mismatch", "error")
    if observation.status != "completed":
        add("run_not_terminal", "error", "provider")
    if observation.conclusion != "success":
        add("run_not_successful", "error", "provider")

    by_context = [
        status
        for status in observation.commit_statuses
        if status.context == expectations.status_context
    ]
    if not by_context:
        add("status_context_missing", "error", "provider")
    else:
        latest_status = max(
            by_context,
            key=lambda item: (
                _timestamp(item.updated_at)
                or _timestamp(item.created_at)
                or datetime.min.replace(tzinfo=timezone.utc)
            ),
        )
        if latest_status.state != "success":
            add("status_not_successful", "error", "provider")
        if (
            latest_status.target_url
            and f"/actions/runs/{reference.run_id}/" not in latest_status.target_url
        ):
            add("status_run_reference_mismatch", "error")
        if latest_status.creator is None:
            add("status_creator_unproven", "warning", "provider")

    job_conclusions = {job.conclusion for job in observation.jobs if job.status == "completed"}
    if observation.conclusion == "success" and any(
        value not in {None, "success", "skipped"} for value in job_conclusions
    ):
        add("contradictory_sources", "error")
    if not observation.jobs:
        add("jobs_missing", "warning", "provider")

    time_values = [
        parsed
        for parsed in [
            *(_timestamp(job.completed_at) for job in observation.jobs),
            _timestamp(observation.completed_at),
            _timestamp(observation.started_at),
            *(
                _timestamp(status.updated_at) or _timestamp(status.created_at)
                for status in observation.commit_statuses
            ),
        ]
        if parsed is not None
    ]
    effective_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not time_values:
        add("freshness_unproven", "warning", "provider")
    else:
        newest = max(time_values)
        age_seconds = (effective_now - newest).total_seconds()
        if age_seconds < -300:
            add("future_timestamp", "error", "provider")
        elif age_seconds > expectations.max_age_seconds:
            add("stale_evidence", "error", "provider")

    for fact in observation.missing_facts:
        add(f"missing_{fact}", "warning", "provider")
    if observation.unknown_fields:
        add("unknown_provider_fields", "info", "provider")
    if observation.workflow_blob_sha is None:
        add("workflow_blob_unproven", "warning", "provider")
    add("verification_request_binding_unproven", "warning")
    add("runner_environment_unproven", "warning", "provider")
    add("toolchain_unproven", "warning", "provider")
    if not observation.provider_instance.lower().startswith("https://"):
        add("provider_transport_unauthenticated", "warning")
    add("provider_response_unsigned", "warning", "provider")

    verdict: Literal["advisory_qualified", "advisory_rejected"] = (
        "advisory_rejected"
        if any(finding.severity == "error" for finding in findings)
        else "advisory_qualified"
    )
    return EvidenceAssessment(
        subject=subject,
        reference=reference,
        provider_observation=observation,
        expectations=expectations,
        verdict=verdict,
        findings=tuple(findings),
    )
