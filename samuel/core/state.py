"""Shared runtime-state value objects and stable failure taxonomy.

SQLite is deliberately absent from this module.  Slices and core consumers
depend on these records and on the ports in :mod:`samuel.core.ports`; storage
details remain adapter concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from samuel.core.gate_metadata import EVALUATION_OBSERVATION_SCHEMA_VERSION

StateFailureSemantics = Literal["observable", "non_blocking", "fail_closed"]
HealingClaimStatus = Literal["claimed", "attempted", "abandoned"]
IntentStatus = Literal["pending", "applied", "failed", "mismatch", "unresolved"]
RestoreOperationStatus = Literal["reconcile_required", "completed", "superseded"]
ReconcileScanStatus = Literal["pending", "completed", "scan_failed"]
ReconcileClassification = Literal[
    "verified_effect",
    "verified_absent",
    "abandoned",
    "unresolved",
]
RetentionCategoryState = Literal["report_only", "enforce", "suspended"]
RetentionExecutionStatus = Literal["completed"]
BudgetAttemptStatus = Literal["reserved", "settled", "unknown"]
ClarificationStatus = Literal[
    "waiting",
    "answered",
    "planned",
    "superseded",
    "timed_out",
    "exhausted",
]

AUTHORITY_EVENT_SERIES = "authority.v2"


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for persisted state."""

    return datetime.now(timezone.utc)


def authority_event_binding(
    authority_status: dict[str, Any],
    *,
    authority_epoch: int | None = None,
) -> dict[str, Any]:
    """Return the mandatory v2 binding for authority-bearing audit events.

    The status lookup deliberately happens after the authoritative write.  A
    later concurrent write may advance the store epoch, but it cannot change
    the instance UUID without an exclusive restore.  The event remains bound
    to the exact epoch returned by its own transition.
    """

    instance_uuid = authority_status.get("instance")
    epoch = authority_status.get("epoch") if authority_epoch is None else authority_epoch
    if not isinstance(instance_uuid, str) or not instance_uuid:
        raise StateStoreError(
            "state_authority_binding_invalid",
            "Authority state does not expose a valid instance UUID",
        )
    try:
        UUID(instance_uuid)
    except ValueError as exc:
        raise StateStoreError(
            "state_authority_binding_invalid",
            "Authority state does not expose a valid instance UUID",
        ) from exc
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise StateStoreError(
            "state_authority_binding_invalid",
            "Authority state does not expose a valid epoch",
        )
    return {
        "authority_series": AUTHORITY_EVENT_SERIES,
        "instance_uuid": instance_uuid,
        "authority_epoch": epoch,
    }


@dataclass(frozen=True)
class StateStoreStatus:
    healthy: bool
    path: Path
    schema_version: int
    supported_schema_version: int
    journal_mode: str
    auto_vacuum: str
    foreign_keys: bool
    filesystem_type: str
    filesystem_mount: Path
    tables: tuple[str, ...]
    projection_healthy: bool = True
    projection_error_code: str | None = None
    authority_epoch: int = 0
    authority_instance: str = ""
    witness_epoch: int = 0
    reconcile_required: bool = False
    reconcile_reason: str | None = None
    active_restore_operation: str | None = None
    restore_scan_status: str | None = None
    restore_sentinel_present: bool = False
    retention_emergency_stop: bool = True
    retention_category_states: tuple[dict[str, Any], ...] = ()
    retention_last_execution: dict[str, Any] | None = None
    identity_status: str = "unavailable"
    identity_principals: int = 0
    identity_active_sessions: int = 0
    identity_active_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "path": str(self.path),
            "schema_version": self.schema_version,
            "supported_schema_version": self.supported_schema_version,
            "journal_mode": self.journal_mode,
            "auto_vacuum": self.auto_vacuum,
            "foreign_keys": self.foreign_keys,
            "filesystem": {
                "type": self.filesystem_type,
                "mount": str(self.filesystem_mount),
                "classification": "local",
            },
            "tables": list(self.tables),
            "projections": {
                "healthy": self.projection_healthy,
                "error_code": self.projection_error_code,
                "failure_semantics": "non_blocking",
            },
            "identity": {
                "status": self.identity_status,
                "principals": self.identity_principals,
                "active_sessions": self.identity_active_sessions,
                "active_tokens": self.identity_active_tokens,
                "secrets_included": False,
            },
            "authority": {
                "epoch": self.authority_epoch,
                "instance": self.authority_instance,
                "witness_epoch": self.witness_epoch,
                "reconcile_required": self.reconcile_required,
                "reconcile_reason": self.reconcile_reason,
                "active_restore_operation": self.active_restore_operation,
                "restore_scan_status": self.restore_scan_status,
                "restore_sentinel_present": self.restore_sentinel_present,
                "retention_emergency_stop": self.retention_emergency_stop,
                "retention_category_states": list(self.retention_category_states),
                "retention_last_execution": self.retention_last_execution,
                "failure_semantics": "fail_closed",
            },
        }


@dataclass(frozen=True)
class ObservationRecord:
    observation_key: str
    subject_key: str
    evidence_digest: str
    observation_schema: str
    payload: dict[str, Any]
    issue_number: int = 0
    evidence_origin: str = "bound_acceptance_evidence"
    observed_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ScoreDerivationRecord:
    score_key: str
    observation_key: str
    scoring_policy_version: str
    formula_version: str
    score: float | None
    payload: dict[str, Any]
    issue_number: int = 0
    scoring_policy_digest: str = ""
    evidence_origin: str = "bound_acceptance_evidence"
    observation_schema: str = f"bound.v{EVALUATION_OBSERVATION_SCHEMA_VERSION}"
    derived_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class EvaluationTerminalRecord:
    terminal_key: str
    issue_number: int
    status: str
    payload: dict[str, Any]
    observed_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RunProjectionRecord:
    projection_key: str
    issue_number: int
    correlation_id: str
    series: str
    status: str
    payload: dict[str, Any]
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AuthorityRecord:
    record_key: str
    kind: str
    payload: dict[str, Any]
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AuthorityWriteResult:
    changed: bool
    authority_epoch: int


@dataclass(frozen=True)
class HealingClaimRecord:
    observation_key: str
    issue_number: int
    correlation_id: str
    status: HealingClaimStatus = "claimed"
    outcome: str | None = None
    reason: str | None = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class WorkflowCheckpointRecord:
    checkpoint_key: str
    issue_number: int
    correlation_id: str
    workflow: str
    boundary: str
    repository: str
    branch: str
    base_ref: str
    head_sha: str
    workspace_id: str
    evaluation_subject: dict[str, Any]
    resume_eligible: bool
    payload: dict[str, Any]
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class OperationIntentRecord:
    intent_key: str
    operation: str
    status: IntentStatus
    issue_number: int
    correlation_id: str
    subject_key: str
    payload: dict[str, Any]
    postcondition: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class WorkflowBudgetAdmissionRecord:
    """One immutable, operator-authorized workflow token allowance."""

    admission_key: str
    repository: str
    issue_number: int
    invocation_digest: str
    source_digest: str
    policy_digest: str
    correlation_id: str
    token_limit: int
    plan_contract_hash: str = ""
    plan_comment_id: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PlanningClarificationRecord:
    """One source-bound clarification series and its append-only round evidence.

    ``rounds`` contains bounded question, answer and revision metadata. The SCM
    comment remains the input source and is re-read and digest-checked before
    planning or approval; raw text is never copied to audit or dashboard events.
    """

    series_key: str
    repository: str
    issue_number: int
    source_digest: str
    admission_key: str
    correlation_id: str
    status: ClarificationStatus
    round_number: int
    deadline_at: datetime
    rounds: tuple[dict[str, Any], ...]
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class LLMBudgetAttemptRecord:
    """Persisted reservation for exactly one physical provider attempt."""

    attempt_key: str
    admission_key: str
    logical_call_id: str
    provider: str
    model: str
    task: str
    input_upper_bound: int
    output_upper_bound: int
    reserved_tokens: int
    status: BudgetAttemptStatus = "reserved"
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None
    outcome_code: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AuthorityLeaseRecord:
    resource_key: str
    owner_id: str
    expires_at: datetime
    version: int
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RestoreOperationRecord:
    operation_id: str
    status: RestoreOperationStatus
    source_digest: str
    restored_from_uuid: str
    instance_uuid: str
    pre_restore_epoch_highwater: int
    supersedes_operation_id: str | None = None
    reason: str | None = None
    scan_status: ReconcileScanStatus = "pending"
    scan_error_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ReconcileEntryRecord:
    operation_id: str
    object_type: str
    object_key: str
    classification: ReconcileClassification
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ManagedBackupRecord:
    """One backup inside the operator-selected managed retention boundary."""

    backup_id: str
    path: Path
    digest: str
    instance_uuid: str
    authority_epoch: int
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RetentionCategoryStateRecord:
    """Persisted operator authority for exactly one retention category policy."""

    category_id: str
    category_digest: str
    profile_role_digest: str
    state: RetentionCategoryState
    version: int
    reason: str
    evidence_digest: str | None = None
    grant_cutoff_utc: datetime | None = None
    activated_at: datetime | None = None
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RetentionExecutionRecord:
    """Append-only receipt for one exact, category-bound deletion plan."""

    execution_id: str
    category_id: str
    plan_digest: str
    category_digest: str
    profile_role_digest: str
    cutoff_utc: datetime
    anchor: str
    object_ids: tuple[str, ...]
    candidate_count: int
    deleted_count: int
    status: RetentionExecutionStatus
    reason: str
    authority_epoch: int
    executed_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RetentionTableSnapshot:
    """Schema and row metadata used by a non-deleting retention report.

    Row values are an internal policy input.  Callers must not include them in
    operator output; only aggregate counts and protection reasons are safe.
    """

    table: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]


class StateStoreError(Exception):
    """Credential- and payload-free runtime-state failure."""

    def __init__(self, code: str, safe_message: str):
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class StateStoreConflict(StateStoreError):
    def __init__(self, kind: str, key: str):
        super().__init__(
            "state_record_conflict",
            f"{kind} record {key!r} already exists with different bound content",
        )
