from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from samuel.core.errors import SCMRevisionError
from samuel.core.evaluation_subject import (
    EvaluationSubject,
    PullRequestRevision,
    RevisionComparison,
)
from samuel.core.external_evidence import SCMCheckObservation, SCMCheckReference
from samuel.core.identity import (
    AutomationTokenRecord,
    IdentityStatus,
    PrincipalRecord,
    Role,
    SessionRecord,
)
from samuel.core.state import (
    AuthorityLeaseRecord,
    AuthorityRecord,
    AuthorityWriteResult,
    EvaluationTerminalRecord,
    HealingClaimRecord,
    LLMBudgetAttemptRecord,
    ManagedBackupRecord,
    ObservationRecord,
    OperationIntentRecord,
    PlanningClarificationRecord,
    ReconcileEntryRecord,
    RestoreOperationRecord,
    RetentionCategoryStateRecord,
    RetentionExecutionRecord,
    RetentionTableSnapshot,
    RunProjectionRecord,
    ScoreDerivationRecord,
    StateStoreStatus,
    WorkflowBudgetAdmissionRecord,
    WorkflowCheckpointRecord,
)
from samuel.core.types import (
    PR,
    AuditQuery,
    Comment,
    GateContext,
    GateResult,
    Issue,
    LLMResponse,
    ProviderDispatchResult,
    ProviderEvidence,
    ProviderRunReference,
    SCMActivity,
    SCMLabelEvent,
    SkeletonEntry,
    VerificationAuthority,
    VerificationCriterion,
    VerificationProgress,
    VerificationRequest,
)
from samuel.core.workspaces import WorkspaceHandle, WorkspaceRecord


class IVersionControl(ABC):
    @abstractmethod
    def get_issue(self, number: int) -> Issue: ...

    @abstractmethod
    def get_comments(self, number: int) -> list[Comment]: ...

    @abstractmethod
    def post_comment(self, number: int, body: str) -> Comment: ...

    @abstractmethod
    def create_pr(self, head: str, base: str, title: str, body: str) -> PR: ...

    @abstractmethod
    def swap_label(self, number: int, remove: str, add: str) -> None: ...

    @abstractmethod
    def list_labels(self) -> list[dict]: ...

    @abstractmethod
    def create_label(self, name: str, color: str, description: str = "") -> dict: ...

    @abstractmethod
    def list_issues(self, labels: list[str]) -> list[Issue]: ...

    @abstractmethod
    def close_issue(self, number: int) -> None: ...

    @abstractmethod
    def merge_pr(self, pr_id: int) -> bool: ...

    def merge_pr_expected(self, pr_id: int, *, expected_head_sha: str) -> bool:
        """Merge only if the provider enforces the exact expected head."""

        raise SCMRevisionError(
            "expected_head_merge_unsupported",
            "SCM adapter has no qualified expected-head merge capability",
        )

    @abstractmethod
    def issue_url(self, number: int) -> str: ...

    @abstractmethod
    def pr_url(self, pr_id: int) -> str: ...

    @abstractmethod
    def branch_url(self, branch: str) -> str: ...

    def get_branch_protection(self, branch: str) -> dict | None:
        """Return protection metadata for ``branch`` or ``None``.

        Concrete-default-None so existing test mocks keep working — only
        adapters that actually expose the SCM endpoint override (#209).
        Implementations should return:
        - ``None`` when the branch is unprotected or the SCM has no such
          concept.
        - ``{"branch": <name>, "rules": <raw-dict-from-SCM>}`` when
          protected. ``rules`` is intentionally unstructured so different
          backends can surface their full rule shape.
        """
        return None

    @property
    def repository_identity(self) -> str:
        raise SCMRevisionError(
            "immutable_revisions_unsupported",
            "SCM adapter does not expose an immutable repository identity",
        )

    def resolve_ref(self, ref: str) -> str:
        raise SCMRevisionError(
            "immutable_revisions_unsupported",
            "SCM adapter cannot resolve references to immutable commits",
        )

    def compare_commits(
        self,
        base_sha: str,
        head_sha: str,
        *,
        max_diff_bytes: int,
    ) -> RevisionComparison:
        raise SCMRevisionError(
            "immutable_revisions_unsupported",
            "SCM adapter cannot compare immutable commits",
        )

    def read_file_at_revision(
        self,
        head_sha: str,
        path: str,
        *,
        max_file_bytes: int,
    ) -> str | None:
        raise SCMRevisionError(
            "immutable_file_read_unsupported",
            "SCM adapter cannot read files from immutable commits",
        )

    def get_pr_revision(self, pr_id: int) -> PullRequestRevision:
        raise SCMRevisionError(
            "immutable_revisions_unsupported",
            "SCM adapter cannot verify pull-request revisions",
        )

    def get_pr(self, pr_id: int) -> PR:
        """Return one provider-neutral pull request identity.

        Resume callers use this together with ``get_pr_revision``; adapters
        which cannot expose a stable PR identity must fail closed.
        """

        raise SCMRevisionError(
            "pull_request_lookup_unsupported",
            "SCM adapter cannot retrieve a pull request by number",
        )

    def find_pr_by_marker(self, marker: str, *, head: str, base: str) -> PR | None:
        """Find the uniquely marked PR created by a pending operation intent."""

        raise SCMRevisionError(
            "pull_request_lookup_unsupported",
            "SCM adapter cannot reconcile pull requests by intent marker",
        )

    def resolve_ref_optional(self, ref: str) -> str | None:
        """Resolve a ref, returning ``None`` only when it is confirmed absent."""

        return self.resolve_ref(ref)

    @property
    def capabilities(self) -> set[str]:
        return set()

    def list_scm_activity(self, since: str, limit: int = 250) -> list[SCMActivity]:
        """Return normalized repository activity newer than RFC3339 ``since``.

        Optional capability: adapters implementing it advertise
        ``activity_polling``.  The concrete empty default preserves portability
        for SCM backends which only support webhooks.
        """
        return []

    def get_label_events(self, number: int, label: str) -> list[SCMLabelEvent]:
        """Return attributable label evidence, oldest first.

        A non-empty label retains the portable label-addition contract. Providers
        that advertise native label-event correlation may accept an empty label
        to return every add/remove transition for ambiguity checks.
        """

        return []


class ILLMProvider(ABC):
    @abstractmethod
    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse: ...

    @abstractmethod
    def estimate_tokens(self, text: str) -> int: ...

    @property
    @abstractmethod
    def context_window(self) -> int: ...

    @property
    def capabilities(self) -> set[str]:
        return set()


class IAuthProvider(ABC):
    @abstractmethod
    def get_token(self) -> str: ...

    @abstractmethod
    def is_valid(self) -> bool: ...

    @abstractmethod
    def refresh(self) -> None: ...


class IIdentityStateStore(ABC):
    """Typed local identity state within the existing runtime-state database."""

    @abstractmethod
    def status(self) -> IdentityStatus: ...

    @abstractmethod
    def bootstrap_administrator(self, username: str, password_hash: str) -> PrincipalRecord: ...

    @abstractmethod
    def recover_administrator(
        self, username: str, password_hash: str, *, reason: str
    ) -> PrincipalRecord: ...

    @abstractmethod
    def get_principal_by_username(self, username: str) -> PrincipalRecord | None: ...

    @abstractmethod
    def get_principal(self, principal_id: str) -> PrincipalRecord | None: ...

    @abstractmethod
    def list_principals(self) -> list[PrincipalRecord]: ...

    @abstractmethod
    def create_user(
        self, username: str, password_hash: str, roles: tuple[Role, ...]
    ) -> PrincipalRecord: ...

    @abstractmethod
    def update_user(
        self,
        principal_id: str,
        *,
        roles: tuple[Role, ...] | None = None,
        disabled: bool | None = None,
        password_hash: str | None = None,
    ) -> PrincipalRecord: ...

    @abstractmethod
    def create_session(self, record: SessionRecord) -> None: ...

    @abstractmethod
    def get_session(self, session_hash: str) -> SessionRecord | None: ...

    @abstractmethod
    def touch_session(self, session_hash: str, seen_at: datetime) -> None: ...

    @abstractmethod
    def list_sessions(self, principal_id: str | None = None) -> list[SessionRecord]: ...

    @abstractmethod
    def revoke_session(self, session_hash: str, *, actor: str, revoked_at: datetime) -> bool: ...

    @abstractmethod
    def revoke_session_id(self, session_id: str, *, actor: str, revoked_at: datetime) -> bool: ...

    @abstractmethod
    def revoke_sessions(
        self, *, principal_id: str | None, actor: str, revoked_at: datetime
    ) -> int: ...

    @abstractmethod
    def create_automation_token(
        self, principal: PrincipalRecord, token: AutomationTokenRecord
    ) -> None: ...

    @abstractmethod
    def get_automation_token(self, token_hash: str) -> AutomationTokenRecord | None: ...

    @abstractmethod
    def list_automation_tokens(self) -> list[AutomationTokenRecord]: ...

    @abstractmethod
    def revoke_automation_token(
        self, token_id: str, *, actor: str, revoked_at: datetime
    ) -> bool: ...


class IGitTransportAuth(ABC):
    """Delegate one credential to one validated network-Git operation."""

    failure_semantics = "fail_closed"

    @abstractmethod
    def environment(
        self,
        remote_url: str,
        operation: Literal["fetch", "push"],
    ) -> AbstractContextManager[Mapping[str, str]]:
        """Return an ephemeral subprocess overlay for the bound remote."""


class IAuditLog(ABC):
    @abstractmethod
    def log(self, event: Any) -> str: ...

    @abstractmethod
    def read(self, **filters: Any) -> list[Any]: ...

    @abstractmethod
    def start_run(self, mode: str) -> str: ...


class IConfig(ABC):
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    def feature_flag(self, name: str) -> bool: ...

    def reload(self) -> None:
        """Reload mutable backends; immutable/mock configs may keep this no-op."""
        return None


class IAuditSink(ABC):
    @abstractmethod
    def write(self, event: Any) -> None: ...

    @abstractmethod
    def query(self, query: AuditQuery) -> list[Any]: ...


class IQualityMetricsRegistry(ABC):
    """#153: persistierte, recency-gewichtete LLM-Qualitaet pro
    (provider, model, task). ``record`` verrechnet einen neuen Eval-Score in den
    Gleitdurchschnitt (EWMA); ``score_for`` liefert den aktuellen Durchschnitt
    (z.B. zum Anreichern von LLMCallCompleted / fuer Quality-aware Routing);
    ``aggregates`` liefert alle Zeilen fuer das Dashboard."""

    @abstractmethod
    def record(
        self,
        provider: str,
        model: str,
        task: str,
        score: float,
        passed: bool | None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    @abstractmethod
    def score_for(
        self,
        provider: str,
        model: str,
        task: str,
    ) -> float | None: ...

    @abstractmethod
    def aggregates(self) -> list[dict]: ...


class ISecretsProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> str: ...


class ISkeletonBuilder(ABC):
    supported_extensions: set[str]

    @abstractmethod
    def extract(self, file: Path) -> list[SkeletonEntry]: ...


class IPatchApplier(ABC):
    supported_extensions: set[str]

    @abstractmethod
    def apply(self, file: Path, patches: list[Any]) -> Any: ...

    @abstractmethod
    def validate(self, file: Path, content: str) -> bool: ...


class INotificationSink(ABC):
    @abstractmethod
    def notify(self, event: Any) -> None: ...


class IQualityCheck(ABC):
    supported_extensions: set[str]

    @abstractmethod
    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> Any: ...


class IExternalGate(ABC):
    name: str

    @abstractmethod
    def run(self, context: GateContext) -> GateResult: ...


class ISCMCheckEvidenceReader(ABC):
    """Read existing provider evidence without granting gate authority."""

    failure_semantics = "observable"

    @abstractmethod
    def read_check_evidence(self, reference: SCMCheckReference) -> SCMCheckObservation: ...


class IExecutionProvider(ABC):
    """Dispatch and reconcile one explicitly authorized verification request."""

    failure_semantics = "fail_closed"

    @abstractmethod
    def dispatch(self, request: VerificationRequest) -> ProviderDispatchResult:
        """Submit once. Implementations must not retry an ambiguous external POST."""

    @abstractmethod
    def reconcile(
        self,
        request: VerificationRequest,
        reference: ProviderRunReference | None,
    ) -> ProviderDispatchResult:
        """Find the run for the same request without creating another run."""

    @abstractmethod
    def read_evidence(
        self,
        request: VerificationRequest,
        reference: ProviderRunReference,
    ) -> ProviderEvidence | None:
        """Return terminal bound evidence, or ``None`` while the run is pending."""


class IProviderVerificationRecovery(Protocol):
    """Narrow restart hook that can only advance an existing request."""

    def advance(self, request_key: str) -> Any: ...


class IProviderVerificationCoordinator(IProviderVerificationRecovery, Protocol):
    """Application-facing provider coordinator without a cross-slice dependency."""

    def request(
        self,
        *,
        subject: EvaluationSubject,
        authority: VerificationAuthority,
        criteria: tuple[VerificationCriterion, ...],
        policy_binding: dict[str, Any],
        correlation_id: str,
        new_request: bool = False,
        consumer_mode: Literal["passive_candidate", "reference_worker"] = "passive_candidate",
        consumer_context: dict[str, Any] | None = None,
    ) -> VerificationProgress: ...

    def acknowledge(self, request_key: str, *, outcome: str) -> None: ...


class IWorkspaceManager(ABC):
    """Own Git worktrees without making a workspace a sandbox claim."""

    failure_semantics = "fail_closed"

    @abstractmethod
    def acquire_run(
        self,
        *,
        repository_root: Path,
        workspace_id: str,
        branch: str,
        base_ref: str,
        expected_head: str = "",
        expected_base_sha: str = "",
    ) -> WorkspaceHandle: ...

    @abstractmethod
    def acquire_verification(
        self,
        *,
        repository_root: Path,
        workspace_id: str,
        head_sha: str,
        base_ref: str = "",
    ) -> WorkspaceHandle: ...

    @abstractmethod
    def acquire_existing_run(
        self,
        *,
        repository_root: Path,
        workspace_id: str,
        branch: str,
    ) -> WorkspaceHandle:
        """Take the OS lock for an existing run without mutating its tree."""

    @abstractmethod
    def detach(self, workspace_id: str) -> None:
        """Release process ownership without deleting or terminalizing the tree."""

    @abstractmethod
    def release(self, workspace_id: str) -> None: ...

    @abstractmethod
    def quarantine(self, workspace_id: str, *, reason: str) -> None: ...

    @abstractmethod
    def discard_quarantine(self, workspace_id: str, *, reason: str) -> None: ...

    @abstractmethod
    def list_workspaces(self) -> list[WorkspaceRecord]: ...

    @abstractmethod
    def inspect(self, workspace_id: str) -> WorkspaceRecord | None: ...

    @abstractmethod
    def prune(self) -> dict[str, int]: ...


class IObservationStore(ABC):
    """Immutable observations and their replayable derivations.

    Failures are observable telemetry failures; consumers must surface them
    but must not silently turn the score into release authority.
    """

    failure_semantics = "observable"

    @abstractmethod
    def put_observation(self, record: ObservationRecord) -> bool: ...

    @abstractmethod
    def get_observation(self, observation_key: str) -> ObservationRecord | None: ...

    @abstractmethod
    def list_observations(self, issue_number: int | None = None) -> list[ObservationRecord]: ...

    @abstractmethod
    def put_derivation(self, record: ScoreDerivationRecord) -> bool: ...

    @abstractmethod
    def get_derivation(self, score_key: str) -> ScoreDerivationRecord | None: ...

    @abstractmethod
    def list_derivations(
        self,
        issue_number: int | None = None,
    ) -> list[ScoreDerivationRecord]: ...

    @abstractmethod
    def put_terminal(self, record: EvaluationTerminalRecord) -> bool: ...

    @abstractmethod
    def get_terminal(self, terminal_key: str) -> EvaluationTerminalRecord | None: ...

    @abstractmethod
    def list_terminals(
        self,
        issue_number: int | None = None,
    ) -> list[EvaluationTerminalRecord]: ...


class IRunProjectionStore(ABC):
    """Replaceable query projection for dashboard/runtime history.

    Projection failures are non-blocking for release workflows and must be
    made visible so a later rebuild can catch up.
    """

    failure_semantics = "non_blocking"

    @abstractmethod
    def upsert_projection(self, record: RunProjectionRecord) -> None: ...

    @abstractmethod
    def get_projection(self, projection_key: str) -> RunProjectionRecord | None: ...

    @abstractmethod
    def list_projections(
        self,
        issue_number: int | None = None,
        *,
        series: str | None = None,
    ) -> list[RunProjectionRecord]: ...


class IAuthorityStateStore(ABC):
    """Transactional authority state for claims, checkpoints and effects.

    Callers must treat every write failure as fail-closed before entering the
    next unsafe section.
    """

    failure_semantics = "fail_closed"

    @abstractmethod
    def put_authority_record(self, record: AuthorityRecord) -> bool: ...

    @abstractmethod
    def get_authority_record(self, record_key: str) -> AuthorityRecord | None: ...

    @abstractmethod
    def list_authority_records(self) -> list[AuthorityRecord]: ...

    @abstractmethod
    def claim_healing(self, record: HealingClaimRecord) -> AuthorityWriteResult: ...

    @abstractmethod
    def finish_healing(
        self,
        observation_key: str,
        *,
        status: str,
        outcome: str | None = None,
        reason: str | None = None,
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def get_healing_claim(self, observation_key: str) -> HealingClaimRecord | None: ...

    @abstractmethod
    def list_healing_claims(self) -> list[HealingClaimRecord]: ...

    @abstractmethod
    def put_checkpoint(self, record: WorkflowCheckpointRecord) -> AuthorityWriteResult: ...

    @abstractmethod
    def get_checkpoint(self, checkpoint_key: str) -> WorkflowCheckpointRecord | None: ...

    @abstractmethod
    def list_checkpoints(
        self, *, resume_eligible: bool | None = None
    ) -> list[WorkflowCheckpointRecord]: ...

    @abstractmethod
    def clear_checkpoint(self, checkpoint_key: str) -> AuthorityWriteResult: ...

    @abstractmethod
    def put_intent(self, record: OperationIntentRecord) -> AuthorityWriteResult: ...

    @abstractmethod
    def finish_intent(
        self,
        intent_key: str,
        *,
        status: str,
        postcondition: dict[str, Any],
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def get_intent(self, intent_key: str) -> OperationIntentRecord | None: ...

    @abstractmethod
    def list_intents(
        self,
        *,
        correlation_id: str | None = None,
        status: str | None = None,
    ) -> list[OperationIntentRecord]: ...

    @abstractmethod
    def put_budget_admission(
        self, record: WorkflowBudgetAdmissionRecord
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def bind_budget_plan(
        self, admission_key: str, *, plan_contract_hash: str, plan_comment_id: int
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def get_budget_admission(self, admission_key: str) -> WorkflowBudgetAdmissionRecord | None: ...

    @abstractmethod
    def find_budget_admission(
        self,
        *,
        repository: str,
        issue_number: int,
        plan_contract_hash: str,
        plan_comment_id: int,
    ) -> WorkflowBudgetAdmissionRecord | None: ...

    @abstractmethod
    def list_budget_admissions(self) -> list[WorkflowBudgetAdmissionRecord]: ...

    @abstractmethod
    def reserve_budget_attempt(self, record: LLMBudgetAttemptRecord) -> AuthorityWriteResult: ...

    @abstractmethod
    def settle_budget_attempt(
        self,
        attempt_key: str,
        *,
        status: str,
        actual_input_tokens: int | None,
        actual_output_tokens: int | None,
        outcome_code: str,
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def get_budget_attempt(self, attempt_key: str) -> LLMBudgetAttemptRecord | None: ...

    @abstractmethod
    def list_budget_attempts(
        self, *, admission_key: str | None = None
    ) -> list[LLMBudgetAttemptRecord]: ...

    def put_planning_clarification(
        self,
        record: PlanningClarificationRecord,
        *,
        expected_version: int | None = None,
    ) -> AuthorityWriteResult:
        raise NotImplementedError

    def get_planning_clarification(self, series_key: str) -> PlanningClarificationRecord | None:
        raise NotImplementedError

    def find_active_planning_clarification(
        self, *, repository: str, issue_number: int
    ) -> PlanningClarificationRecord | None:
        raise NotImplementedError

    def find_latest_planning_clarification(
        self, *, repository: str, issue_number: int
    ) -> PlanningClarificationRecord | None:
        raise NotImplementedError

    def list_planning_clarifications(self) -> list[PlanningClarificationRecord]:
        raise NotImplementedError

    @abstractmethod
    def acquire_lease(
        self,
        record: AuthorityLeaseRecord,
        *,
        expected_version: int | None = None,
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def get_lease(self, resource_key: str) -> AuthorityLeaseRecord | None: ...

    @abstractmethod
    def list_leases(self) -> list[AuthorityLeaseRecord]: ...

    @abstractmethod
    def release_lease(
        self,
        resource_key: str,
        *,
        owner_id: str,
        expected_version: int,
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def authority_status(self) -> dict[str, Any]: ...

    @abstractmethod
    def replace_reconcile_scan(
        self,
        operation_id: str,
        entries: list[ReconcileEntryRecord],
        *,
        scan_error_code: str | None = None,
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def list_reconcile_entries(self, operation_id: str) -> list[ReconcileEntryRecord]: ...

    @abstractmethod
    def classify_reconcile_entry(
        self,
        operation_id: str,
        object_type: str,
        object_key: str,
        *,
        classification: str,
        reason: str,
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def complete_reconcile(
        self,
        operation_id: str,
        *,
        audit_epoch: int = 0,
    ) -> AuthorityWriteResult: ...


class IStateDiagnostics(ABC):
    """Operator-safe lifecycle and backup boundary for runtime state."""

    @abstractmethod
    def status(self) -> StateStoreStatus: ...

    @abstractmethod
    def dump(self) -> dict[str, Any]: ...

    @abstractmethod
    def backup(self, destination: Path) -> Path: ...

    @abstractmethod
    def restore(
        self,
        source: Path,
        *,
        audit_epoch: int = 0,
        supersede_operation_id: str | None = None,
        reason: str | None = None,
    ) -> RestoreOperationRecord: ...

    @abstractmethod
    def list_restore_operations(self) -> list[RestoreOperationRecord]: ...


class IRetentionStateStore(ABC):
    """State-near inventory for report-only retention and managed backups.

    Stage 5b deliberately exposes no deletion method.  A failed inventory or
    registration is fail-closed for future enforcement but cannot block the
    existing workflow, because no enforcement path exists yet.
    """

    failure_semantics = "observable"

    @abstractmethod
    def catalog(self) -> dict[str, tuple[str, ...]]: ...

    @abstractmethod
    def snapshot(self, table: str) -> RetentionTableSnapshot: ...

    @abstractmethod
    def register_managed_backup(self, record: ManagedBackupRecord) -> bool: ...

    @abstractmethod
    def list_managed_backups(self) -> list[ManagedBackupRecord]: ...

    @abstractmethod
    def emergency_stop(self) -> bool: ...


class IRetentionExecutionStore(ABC):
    """Fail-closed authority and allowlisted execution boundary for retention.

    The port deliberately exposes no table name, SQL text or generic deletion
    primitive.  Every executable category requires a named adapter strategy.
    """

    failure_semantics = "fail_closed"

    @abstractmethod
    def get_category_state(self, category_id: str) -> RetentionCategoryStateRecord | None: ...

    @abstractmethod
    def list_category_states(self) -> list[RetentionCategoryStateRecord]: ...

    @abstractmethod
    def transition_category(
        self,
        *,
        category_id: str,
        category_digest: str,
        profile_role_digest: str,
        state: str,
        reason: str,
        evidence_digest: str | None = None,
        grant_cutoff_utc: datetime | None = None,
        activated_at: datetime | None = None,
    ) -> AuthorityWriteResult: ...

    @abstractmethod
    def set_emergency_stop(self, enabled: bool, *, reason: str) -> AuthorityWriteResult: ...

    @abstractmethod
    def execute_score_derivations(
        self,
        *,
        plan_digest: str,
        category_digest: str,
        profile_role_digest: str,
        cutoff_utc: datetime,
        anchor: str,
        object_ids: tuple[str, ...],
        field_classification: Mapping[str, str],
        payload_classification: Mapping[str, str],
        reason: str,
    ) -> RetentionExecutionRecord: ...

    @abstractmethod
    def get_execution(self, plan_digest: str) -> RetentionExecutionRecord | None: ...

    @abstractmethod
    def list_executions(self, category_id: str | None = None) -> list[RetentionExecutionRecord]: ...


class IPromptRiskAnalyzer(ABC):
    """Advisory analysis of untrusted content before an LLM call."""

    @abstractmethod
    def inspect_issue_text(
        self,
        *,
        issue_number: int,
        title: str,
        body: str,
        correlation_id: str,
    ) -> dict[str, Any]: ...

    def inspect_text(
        self,
        *,
        issue_number: int,
        source: str,
        text: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Compatibility path for analyzers that only implement issue input."""

        return self.inspect_issue_text(
            issue_number=issue_number,
            title=source,
            body=text,
            correlation_id=correlation_id,
        )


class IExternalEventSink(ABC):
    @abstractmethod
    def on_event(self, event: Any) -> None: ...


class IExternalTrigger(ABC):
    @abstractmethod
    def register(self, bus: Any) -> None: ...


class IDashboardRenderer(ABC):
    @abstractmethod
    def render_page(self, page: str, data: dict[str, Any]) -> str: ...

    @abstractmethod
    def get_api_data(self, endpoint: str, **params: Any) -> dict[str, Any]: ...


class IProjectRegistry(ABC):
    @abstractmethod
    def list_projects(self) -> list[Any]: ...

    @abstractmethod
    def get_config(self, project_id: str) -> Any: ...
