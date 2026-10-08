from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from samuel.core.acceptance import (
    AcceptanceApproval,
    AcceptanceContract,
    AcceptanceEvidence,
    AcceptanceResult,
    PlanApprovalAuthorityError,
    issue_revision_digest,
    latest_active_plan,
    manual_receipts_for_subject,
    only_manual_acceptance_pending,
    parse_acceptance_contract,
    plan_approval_authority_key,
    resolve_plan_approval,
)
from samuel.core.bus import Bus, scrub_secrets
from samuel.core.commands import (
    Command,
    CreatePRCommand,
    RequestCandidateVerificationCommand,
    SubmitCandidateCommand,
    VerifyACCommand,
)
from samuel.core.config import EvalSchema, GatesConfigSchema, load_eval_config, load_gates_config
from samuel.core.errors import SCMRevisionError
from samuel.core.evaluation_observation import (
    EvaluationObservationIdentity,
    canonical_digest,
    unavailable_evaluation_key,
    validate_completed_observation,
)
from samuel.core.evaluation_subject import (
    EvaluationSubject,
    PullRequestRevision,
    RevisionComparison,
    gate_policy_binding,
)
from samuel.core.events import (
    CandidateEvaluationCompleted,
    CandidateEvaluationFailed,
    CandidateSubmissionRejected,
    CandidateVerificationPending,
    EvaluationSubjectInvalidated,
    Event,
    GateEvaluationCompleted,
    GateEvaluationUnavailable,
    GateFailedEvent,
    GatesPassed,
    OutOfScopeDiff,
    PRCreated,
    PRCreationFailed,
    ProviderGateEvaluationCompleted,
    ProviderVerificationBlocked,
    ProviderVerificationPending,
    ProviderVerificationRequested,
    WorkflowBlocked,
)
from samuel.core.gate_metadata import (
    GATE_NAMES,
    GATE_RESULT_SCHEMA_VERSION,
    PRE_FLIGHT_GATE_IDS,
    PRE_FLIGHT_GATE_ORDER,
)
from samuel.core.ports import (
    IAuthorityStateStore,
    IExternalGate,
    IObservationStore,
    IProviderVerificationCoordinator,
    IVersionControl,
)
from samuel.core.process_environment import VERIFIER_ENVIRONMENT_PROFILE
from samuel.core.review import render_change_context
from samuel.core.state import (
    OperationIntentRecord,
    StateStoreError,
    WorkflowCheckpointRecord,
    authority_event_binding,
)
from samuel.core.types import (
    PR,
    Comment,
    GateContext,
    GateResult,
    ProviderEvidence,
    VerificationAuthority,
    VerificationCriterion,
)
from samuel.slices.pr_gates.gates import GATE_REGISTRY

log = logging.getLogger(__name__)


class PRGatesHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config_dir: str | Path = "config",
        project_root: Path | None = None,
        external_gates: list[IExternalGate] | None = None,
        ai_attribution_fn: Callable[[], str] | None = None,
        gates_profile: str | None = None,
        gates_config: GatesConfigSchema | None = None,
        eval_config: EvalSchema | None = None,
        authority_store: IAuthorityStateStore | None = None,
        observation_store: IObservationStore | None = None,
        scm_policy: Mapping[str, str] | None = None,
        provider_verification: IProviderVerificationCoordinator | None = None,
        review_required: bool = False,
    ) -> None:
        self._bus = bus
        self._authority = authority_store
        self._observations = observation_store
        self._scm = scm
        self._project_root = project_root or Path(".")
        self._config_dir = Path(config_dir)
        self._external_gates = external_gates or []
        self._path_risk_configured = any(gate.name == "path_risk" for gate in self._external_gates)
        self._ai_attribution_fn = ai_attribution_fn
        self._gates_config = (
            gates_config
            if gates_config is not None
            else load_gates_config(config_dir, profile=gates_profile)
        )
        resolved_eval_config = eval_config or load_eval_config(config_dir)
        self._eval_config = resolved_eval_config
        self._test_runner_policy = {
            "policy_version": resolved_eval_config.test_policy_version,
            "test_cmd": resolved_eval_config.test_cmd,
            "test_timeout": resolved_eval_config.test_timeout,
        }
        self._candidate_process_policy = {"environment_profile": VERIFIER_ENVIRONMENT_PROFILE}
        self._scm_policy = dict(scm_policy) if scm_policy is not None else None
        self._provider_verification = provider_verification
        self._review_required = review_required
        # #368 Task 1: aktives Gate-Profil (fuer das Reviewer-Briefing).
        self._gates_profile = (
            gates_profile or os.environ.get("SAMUEL_GATES_PROFILE", "").strip().lower() or "default"
        )
        self._architecture_policy: dict[str, Any] | None = None
        architecture_path = self._config_dir / "architecture.json"
        try:
            loaded_architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
            if isinstance(loaded_architecture, dict):
                self._architecture_policy = loaded_architecture
        except (OSError, ValueError):
            pass
        self._policy_binding = gate_policy_binding(
            self._gates_config,
            resolved_eval_config,
            self._architecture_policy,
            candidate_process=self._candidate_process_policy,
            scm_policy=self._scm_policy,
        )

    @staticmethod
    def _pr_intent_key(correlation_id: str, subject: EvaluationSubject) -> str:
        raw = "\x00".join(
            ("create_pr", correlation_id, subject.repository, subject.base_sha, subject.head_sha)
        ).encode("utf-8")
        return f"create_pr:sha256:{hashlib.sha256(raw).hexdigest()}"

    @staticmethod
    def _checkpoint_key(correlation_id: str, issue_number: int) -> str:
        raw = "\x00".join(
            ("checkpoint", correlation_id or str(issue_number), str(issue_number))
        ).encode("utf-8")
        return f"checkpoint:sha256:{hashlib.sha256(raw).hexdigest()}"

    def _authority_event_binding(self, authority_epoch: int | None) -> dict[str, Any]:
        if authority_epoch is None:
            return {}
        if self._authority is None:
            raise StateStoreError(
                "state_authority_binding_invalid",
                "Authority event cannot be bound without an authority store",
            )
        return authority_event_binding(
            self._authority.authority_status(),
            authority_epoch=authority_epoch,
        )

    @staticmethod
    def _valid_pr_result(pr_result: Any) -> bool:
        """Accept only a concrete, safely auditable PR identity."""
        number = getattr(pr_result, "number", None)
        html_url = getattr(pr_result, "html_url", None)
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            return False
        if not isinstance(html_url, str) or not html_url or html_url != html_url.strip():
            return False
        normalized_url = html_url
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in normalized_url):
            return False
        try:
            parsed = urlsplit(normalized_url)
            _ = parsed.port
        except ValueError:
            return False
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.path.strip("/")
            and not parsed.query
            and not parsed.fragment
        )

    def _pr_creation_failed(
        self,
        *,
        issue_number: int,
        branch: str,
        correlation_id: str,
        results: list[GateResult],
        error_code: str,
        error_type: str,
        subject: EvaluationSubject,
    ) -> dict[str, Any]:
        """Publish bounded failure evidence and stop the success workflow."""
        provider = type(self._scm).__name__ if self._scm is not None else "none"
        error = {
            "code": error_code,
            "type": error_type,
            "provider": provider,
            "message": "SCM did not confirm creation of a valid pull request",
            "remediation": "Verify SCM configuration and repository connectivity before retrying",
        }
        self._bus.publish(
            PRCreationFailed(
                payload={
                    "issue": issue_number,
                    "branch": branch,
                    "cat": "scm",
                    "evt": "pr_create_failed",
                    "source_command": "CreatePR",
                    "gates_passed": True,
                    "pr_created": False,
                    "error": error,
                    "reason": error["message"],
                    "evaluation_subject": subject.as_dict(),
                },
                correlation_id=correlation_id,
            )
        )
        return {
            "passed": False,
            "gates_passed": True,
            "pr_created": False,
            "results": results,
            "gate_results": self._gate_evidence(results, subject),
            "blocked_gates": [],
            "pr_error": error,
            "evaluation_subject": subject.as_dict(),
        }

    def _subject_failure(
        self,
        *,
        issue_number: int,
        branch: str,
        correlation_id: str,
        error: SCMRevisionError,
        subject: EvaluationSubject | None = None,
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "issue": issue_number,
            "branch": branch,
            "cat": "gates",
            "evt": "gate_failed",
            "gate": "evaluation_subject",
            "status": "not_evaluated",
            "reason": error.safe_message,
            "error": {
                "code": error.code,
                "type": type(error).__name__,
                "message": error.safe_message,
            },
        }
        if subject is not None:
            evidence["evaluation_subject"] = subject.as_dict()
        self._bus.publish(GateFailedEvent(payload=evidence, correlation_id=correlation_id))
        unavailable_payload: dict[str, Any] = {
            "issue": issue_number,
            "branch": branch,
            "cat": "gates",
            "evt": "gate_evaluation_unavailable",
            "status": "not_evaluated",
            "reason": error.safe_message,
            "error": evidence["error"],
            "terminal_key": unavailable_evaluation_key(
                issue_number=issue_number,
                branch=branch,
                correlation_id=correlation_id,
                error_code=error.code,
                subject=subject,
            ),
        }
        if subject is not None:
            unavailable_payload["evaluation_subject"] = subject.as_dict()
        self._bus.publish(
            GateEvaluationUnavailable(
                payload=unavailable_payload,
                correlation_id=correlation_id,
            )
        )
        return {
            "passed": False,
            "gates_passed": False,
            "pr_created": False,
            "results": [],
            "blocked_gates": [],
            "subject_error": evidence["error"],
            **({"evaluation_subject": subject.as_dict()} if subject is not None else {}),
        }

    def _resolve_subject(
        self,
        cmd: CreatePRCommand,
        contract: AcceptanceContract | None,
    ) -> tuple[EvaluationSubject, RevisionComparison]:
        if self._scm is None:
            raise SCMRevisionError(
                "scm_adapter_missing",
                "An SCM adapter is required to establish an evaluation subject",
            )
        if contract is None:
            raise SCMRevisionError(
                "acceptance_contract_missing",
                "No approved acceptance contract is available for evaluation",
            )
        repository = self._scm.repository_identity
        self._policy_binding = gate_policy_binding(
            self._gates_config,
            self._eval_config,
            self._architecture_policy,
            candidate_process=self._candidate_process_policy,
            scm_policy=self._scm_policy,
        )
        try:
            base_sha = self._scm.resolve_ref(cmd.base or "main")
            head_sha = self._scm.resolve_ref(cmd.branch)
            computed = EvaluationSubject(
                repository=repository,
                base_sha=base_sha,
                head_sha=head_sha,
                contract_hash=contract.contract_hash,
                policy_version=str(self._policy_binding["policy_version"]),
                policy_digest=str(self._policy_binding["policy_digest"]),
            )
        except ValueError as exc:
            raise SCMRevisionError(
                "invalid_evaluation_subject",
                "SCM or policy data cannot form a valid evaluation subject",
            ) from exc
        if cmd.subject is not None and cmd.subject != computed:
            raise SCMRevisionError(
                "evaluation_subject_changed",
                "The repository, contract, or policy changed after the subject was established",
                subject=cmd.subject,
            )
        subject = cmd.subject or computed
        try:
            comparison = self._scm.compare_commits(
                subject.base_sha,
                subject.head_sha,
                max_diff_bytes=self._gates_config.parameters.max_diff_bytes,
            )
        except SCMRevisionError as exc:
            exc.subject = subject
            raise
        except Exception as exc:
            raise SCMRevisionError(
                "comparison_failed",
                "SCM failed while comparing the immutable commits",
                subject=subject,
            ) from exc
        if (
            comparison.repository != subject.repository
            or comparison.base_sha != subject.base_sha
            or comparison.head_sha != subject.head_sha
        ):
            raise SCMRevisionError(
                "comparison_subject_mismatch",
                "SCM comparison does not match the evaluation subject",
                subject=subject,
            )
        return subject, comparison

    def _bind_review_budget_admission(
        self,
        cmd: CreatePRCommand,
        *,
        contract: AcceptanceContract,
        plan_comment: Comment,
        subject: EvaluationSubject,
    ) -> None:
        """Restore the exact plan-bound budget authority for review.

        The synchronous workflow normally carries this identity from
        Planning through ``CodeGenerated``.  A persisted same-candidate
        continuation, such as reevaluating MANUAL acceptance, enters the PR
        gate in a new process and therefore has to recover the same authority
        from state.  Recovery never creates or resets an admission.
        """

        if not self._review_required or self._authority is None:
            return
        try:
            admission = self._authority.find_budget_admission(
                repository=subject.repository,
                issue_number=cmd.issue_number,
                plan_contract_hash=contract.contract_hash,
                plan_comment_id=plan_comment.id,
            )
        except StateStoreError as exc:
            raise SCMRevisionError(
                "workflow_budget_admission_lookup_failed",
                "Workflow budget admission could not be read",
                subject=subject,
            ) from exc
        if admission is None:
            raise SCMRevisionError(
                "workflow_budget_admission_missing",
                "No workflow budget admission is bound to the active plan",
                subject=subject,
            )
        supplied = cmd.payload.get("budget_admission_key")
        if supplied is not None and supplied != admission.admission_key:
            raise SCMRevisionError(
                "workflow_budget_admission_mismatch",
                "Supplied workflow budget admission belongs to another plan",
                subject=subject,
            )
        cmd.payload["budget_admission_key"] = admission.admission_key

    def _contract_approval(
        self,
        cmd: CreatePRCommand,
        contract: AcceptanceContract,
        plan_comment: Comment,
        comments: list[Comment],
        subject: EvaluationSubject | None = None,
    ) -> AcceptanceApproval:
        supplied = cmd.payload.get("acceptance_approval")
        if isinstance(supplied, dict):
            try:
                approval = AcceptanceApproval.from_dict(supplied)
                if (
                    approval.actor == "samuel:planning-policy"
                    and approval.method == "plan_validated"
                    and approval.contract_hash == contract.contract_hash
                    and approval.plan_comment_id == plan_comment.id
                ):
                    return approval
            except ValueError:
                pass
        if (
            self._authority is None
            or self._scm is None
            or not callable(getattr(self._authority, "get_authority_record", None))
        ):
            return AcceptanceApproval(state="unapproved")
        key = plan_approval_authority_key(
            repository=self._scm.repository_identity,
            issue_number=cmd.issue_number,
            plan_comment_id=plan_comment.id,
            contract_hash=contract.contract_hash,
        )
        if self._authority.get_authority_record(key) is None:
            return AcceptanceApproval(state="unapproved")
        try:
            return resolve_plan_approval(
                self._authority,
                scm=self._scm,
                repository=self._scm.repository_identity,
                issue_number=cmd.issue_number,
                plan_comment=plan_comment,
                contract=contract,
                comments=comments,
                supplied=supplied if isinstance(supplied, dict) else None,
                expected_base_sha=subject.base_sha if subject is not None else None,
            )
        except PlanApprovalAuthorityError:
            return AcceptanceApproval(state="unapproved")

    def _provider_acceptance_evidence(
        self,
        *,
        contract: AcceptanceContract,
        comments: list[Comment],
        plan_comment: Comment,
        subject: EvaluationSubject,
        evidence: ProviderEvidence,
    ) -> dict[str, Any]:
        """Translate exact provider output into the existing Gate 11 contract."""

        provider_results = {item.criterion_id: item for item in evidence.criteria}
        manual_receipts = manual_receipts_for_subject(comments, plan_comment, contract, subject)
        results: list[AcceptanceResult] = []
        for criterion in contract.criteria:
            if criterion.mode == "manual":
                receipt = manual_receipts.get(criterion.criterion_id)
                results.append(
                    AcceptanceResult(
                        criterion_id=criterion.criterion_id,
                        status="passed" if isinstance(receipt, dict) else "manual_pending",
                        reason=(
                            f"human-approved by {receipt.get('actor')}"
                            if isinstance(receipt, dict)
                            else "manual receipt is missing or belongs to another subject"
                        ),
                        tag=criterion.tag,
                        evidence=(
                            {"human_receipt": dict(receipt)} if isinstance(receipt, dict) else None
                        ),
                    )
                )
                continue
            observed = provider_results.get(criterion.criterion_id)
            if observed is None or observed.tag != criterion.tag:
                results.append(
                    AcceptanceResult(
                        criterion_id=criterion.criterion_id,
                        status="missing_evidence",
                        reason="provider evidence does not contain this exact criterion",
                        tag=criterion.tag,
                    )
                )
                continue
            results.append(
                AcceptanceResult(
                    criterion_id=criterion.criterion_id,
                    status=observed.status,
                    reason=observed.reason,
                    tag=criterion.tag,
                    evidence={
                        "origin": "bound_execution_provider",
                        "request_key": evidence.request_key,
                        "provider": evidence.reference.provider,
                        "run_id": evidence.reference.run_id,
                        "attempt": evidence.reference.attempt,
                        "evidence_digest": observed.evidence_digest,
                    },
                )
            )
        return AcceptanceEvidence(
            schema_version=1,
            subject=subject,
            contract=contract,
            results=tuple(results),
        ).as_dict()

    @staticmethod
    def _pr_matches_subject(revision: PullRequestRevision, subject: EvaluationSubject) -> bool:
        return (
            revision.repository == subject.repository
            and revision.base_sha == subject.base_sha
            and revision.head_sha == subject.head_sha
        )

    def _find_intended_pr(
        self,
        intent: OperationIntentRecord | None,
        *,
        marker: str,
        head: str,
        base: str,
        subject: EvaluationSubject,
    ) -> PR | None:
        if self._scm is None or intent is None:
            return None
        pr: PR | None = None
        try:
            number = intent.postcondition.get("pr_number")
            if isinstance(number, int) and not isinstance(number, bool) and number > 0:
                pr = self._scm.get_pr(number)
            elif intent.status == "pending":
                pr = self._scm.find_pr_by_marker(marker, head=head, base=base)
        except SCMRevisionError:
            raise
        except Exception as exc:
            raise SCMRevisionError(
                "pr_reconciliation_failed",
                "SCM could not reconcile the persisted pull-request intent",
                subject=subject,
            ) from exc
        if pr is None:
            return None
        if not self._valid_pr_result(pr):
            raise SCMRevisionError(
                "invalid_scm_response",
                "SCM returned an invalid pull-request identity during reconciliation",
            )
        try:
            revision = self._scm.get_pr_revision(pr.number)
        except SCMRevisionError:
            raise
        except Exception as exc:
            raise SCMRevisionError(
                "pr_reconciliation_failed",
                "SCM could not verify the reconciled pull-request revision",
                subject=subject,
            ) from exc
        if not self._pr_matches_subject(revision, subject):
            raise SCMRevisionError(
                "pr_revision_changed",
                "Intended pull request no longer matches the evaluation subject",
                subject=subject,
            )
        return pr

    def _subject_invalidated(
        self,
        *,
        issue_number: int,
        branch: str,
        correlation_id: str,
        subject: EvaluationSubject,
        pr_number: int,
        pr_url: str,
        results: list[GateResult],
        observed: PullRequestRevision | None,
        reason_code: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "issue": issue_number,
            "branch": branch,
            "pr_number": pr_number,
            "cat": "gates",
            "evt": "subject_invalidated",
            "reason": "Pull request no longer proves the evaluated repository revision",
            "reason_code": reason_code,
            "status": "invalidated",
            "gates_passed": False,
            "pr_created": True,
            "evaluation_subject": subject.as_dict(),
            "gate_results": self._gate_evidence(results, subject),
        }
        if observed is not None:
            payload["observed_revision"] = {
                "repository": observed.repository,
                "base_sha": observed.base_sha,
                "head_sha": observed.head_sha,
            }
        self._bus.publish(
            EvaluationSubjectInvalidated(payload=payload, correlation_id=correlation_id)
        )
        return {
            "passed": False,
            "gates_passed": False,
            "pr_created": True,
            "pr_number": pr_number,
            "pr_url": pr_url,
            "results": results,
            "gate_results": self._gate_evidence(results, subject),
            "blocked_gates": [],
            "subject_error": {
                "code": reason_code,
                "type": "EvaluationSubjectInvalidated",
                "message": payload["reason"],
            },
            "evaluation_subject": subject.as_dict(),
        }

    def _render_reviewer_briefing(
        self,
        results: list[GateResult],
        correlation_id: str,
        subject: EvaluationSubject,
        *,
        contract: AcceptanceContract | None = None,
        acceptance_evidence: dict[str, Any] | None = None,
    ) -> str:
        """Render the authoritative gate decision without a score signal."""
        lines = [
            "## S.A.M.U.E.L. Gate-Entscheidung",
            "- **Freigabeautorität:** Required-Gates des aktiven Profils",
            f"- **Gate-Profil:** `{self._gates_profile}`",
            f"- **Audit-Correlation-ID:** `{correlation_id or 'n/a'}`",
            f"- **Repository:** `{subject.repository}`",
            f"- **Base-Commit:** `{subject.base_sha}`",
            f"- **Head-Commit:** `{subject.head_sha}`",
            f"- **Acceptance-Contract:** `{subject.contract_hash}`",
            f"- **Policy:** `{subject.policy_version}` / `{subject.policy_digest}`",
            "",
            "| Gate | Status | Hinweis |",
            "|---|---|---|",
        ]
        for r in results:
            labels = {
                "passed": "✅ PASS",
                "failed": "❌ FAIL",
                "error": "❌ ERROR",
                "missing_evidence": "❌ MISSING EVIDENCE",
                "not_applicable": "➖ N/A",
                "skipped_precondition": "⏭️ SKIP",
                "manual_pending": "⏸️ MANUAL PENDING",
                "not_evaluated": "❌ NOT EVALUATED",
            }
            status = labels[r.status or ("passed" if r.passed is True else "failed")]
            reason = (r.reason or "").replace("|", "\\|")[:120]
            gate_name = GATE_NAMES.get(r.gate, str(r.gate))
            lines.append(f"| {r.gate} {gate_name} | {status} | {reason} |")
        findings = [r for r in results if r.executed and r.owasp_risk]
        if findings:
            lines.append("")
            lines.append("**Security-Findings (OWASP):**")
            for r in findings:
                reason = (r.reason or "").strip()
                lines.append(f"- Gate `{r.gate}` — {r.owasp_risk}: {reason}")
        if contract is not None:
            verified = (
                acceptance_evidence
                if acceptance_evidence is not None
                and acceptance_evidence.get("evaluation_subject") == subject.as_dict()
                else {}
            )
            statuses = {
                row.get("criterion_id"): row.get("status", "unverified")
                for row in verified.get("results", [])
                if isinstance(row, dict)
            }
            lines.extend(["", "### Auftragsumfang und Acceptance am Candidate"])
            for criterion in contract.criteria:
                text = scrub_secrets(" ".join(criterion.text.split()))
                status = str(statuses.get(criterion.criterion_id, "unverified")).upper()
                lines.append(f"- `{criterion.criterion_id}` [{criterion.tag}] {text}: **{status}**")
        return "\n".join(lines)

    def _post_manual_instructions(
        self,
        issue_number: int,
        subject: EvaluationSubject,
        contract: AcceptanceContract,
        acceptance_evidence: dict[str, Any] | None,
    ) -> None:
        scm = self._scm
        if scm is None or acceptance_evidence is None:
            return
        pending = {
            row.get("criterion_id")
            for row in acceptance_evidence.get("results", [])
            if isinstance(row, dict) and row.get("status") == "manual_pending"
        }
        criteria = [
            c for c in contract.criteria if c.mode == "manual" and c.criterion_id in pending
        ]
        if not criteria:
            return
        marker = (
            f"<!-- samuel-manual:{canonical_digest(subject.as_dict())}:"
            + ":".join(c.criterion_id for c in criteria)
            + " -->"
        )
        lines = [
            f"## MANUAL-Acceptance für Issue #{issue_number}",
            "",
            "Die Planfreigabe ist erfolgt. Jetzt die folgenden Kriterien am genannten "
            "Candidate fachlich prüfen und jeweils den fertigen Befehl kommentieren.",
            "`status:approved`, `ok` und `/approve` bestätigen diese Kriterien nicht.",
            f"Candidate: `{subject.head_sha}`",
            f"Contract: `{subject.contract_hash}`",
            "",
        ]
        for criterion in criteria:
            description = scrub_secrets(" ".join(criterion.text.split()))
            lines.extend(
                [
                    f"- `{criterion.criterion_id}`: {description}",
                    "```text",
                    f"/samuel accept {criterion.criterion_id} "
                    f"--contract {subject.contract_hash} --head {subject.head_sha}",
                    "```",
                ]
            )
        lines.extend(
            [
                "Bei einem neuen Plan oder Candidate gelten diese Befehle nicht für dessen Freigabe.",
                marker,
            ]
        )
        try:
            if any(marker in comment.body for comment in scm.get_comments(issue_number)):
                return
            scm.post_comment(issue_number, "\n".join(lines))
        except Exception as exc:
            log.warning(
                "MANUAL instructions unavailable for issue #%d (%s)",
                issue_number,
                type(exc).__name__,
            )

    def _gate_evidence(self, results: list[GateResult], subject: EvaluationSubject) -> list[dict]:
        evidence: list[dict] = []
        for result in results:
            item = {
                "gate": result.gate,
                "passed": result.passed,
                "executed": result.executed,
                "status": result.status,
                "reason_code": result.reason_code,
                "reason": result.reason,
                "owasp_risk": result.owasp_risk,
                "phase": ("preflight" if result.gate in PRE_FLIGHT_GATE_IDS else "post_candidate"),
                "authority": result.authority,
                "evaluation_subject": subject.as_dict(),
            }
            if result.tool is not None:
                item["tool"] = result.tool
            evidence.append(item)
        return evidence

    def _authoritative_candidate_approval(
        self,
        *,
        issue_number: int,
        issue_labels: set[str],
        contract: AcceptanceContract,
        plan_comment: Comment,
        comments: list[Comment],
    ) -> AcceptanceApproval:
        """Resolve only durable approval; current SCM status is projection."""

        del issue_labels
        sanitized = CreatePRCommand(issue_number=issue_number)
        return self._contract_approval(sanitized, contract, plan_comment, comments)

    @staticmethod
    def _candidate_submission_key(
        issue_number: int,
        plan_comment_id: int,
        subject: EvaluationSubject,
    ) -> str:
        return canonical_digest(
            {
                "schema_version": 1,
                "operation": "passive_candidate_submission",
                "issue": issue_number,
                "plan_comment_id": plan_comment_id,
                "evaluation_subject": subject.as_dict(),
            }
        )

    def _candidate_terminal(
        self,
        event_type: Callable[..., Event],
        *,
        issue_number: int,
        correlation_id: str,
        status: str,
        reason_code: str,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "issue": issue_number,
            "cat": "gates",
            "evt": status,
            "status": status,
            "reason_code": reason_code,
            "reason": reason,
            "evaluation_authority": "approved_plan",
            "mutation_authority": "none",
            **(extra or {}),
        }
        self._bus.publish(event_type(payload=payload, correlation_id=correlation_id))
        return {"ok": status == "candidate_evaluation_completed", **payload}

    def handle_candidate(
        self,
        cmd: Command,
        *,
        use_existing_observation: bool = True,
    ) -> dict[str, Any]:
        """Evaluate an existing SCM candidate without PR or mutation effects."""

        assert isinstance(cmd, SubmitCandidateCommand)
        issue_number = cmd.issue_number
        correlation_id = cmd.correlation_id or ""
        if cmd.payload:
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code="producer_authority_fields_rejected",
                reason="Candidate submission accepts no producer-supplied authority fields",
            )
        if issue_number <= 0:
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code="candidate_mapping_missing",
                reason="Candidate submission needs a positive issue mapping",
            )
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", cmd.head_sha):
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code="candidate_head_invalid",
                reason="Candidate head must be a full lowercase Git object ID",
            )
        if self._scm is None:
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code="scm_adapter_missing",
                reason="Configured SCM is unavailable",
            )

        try:
            issue = self._scm.get_issue(issue_number)
            if issue.state != "open":
                raise SCMRevisionError(
                    "candidate_mapping_inactive",
                    "Candidate issue mapping is not open",
                )
            comments = self._scm.get_comments(issue_number)
            active = latest_active_plan(comments)
            if active is None:
                raise SCMRevisionError(
                    "active_plan_missing", "No active acceptance plan exists for this issue"
                )
            plan_comment, contract = active
            source = contract.source_snapshot
            if contract.schema_version != 2 or source is None:
                raise SCMRevisionError(
                    "planning_source_missing",
                    "Active plan has no authoritative planning-source snapshot",
                )
            if source.repository != self._scm.repository_identity:
                raise SCMRevisionError(
                    "candidate_repository_mismatch",
                    "Active plan belongs to a different configured repository",
                )
            observed_issue_digest = issue_revision_digest(
                number=issue.number,
                title=issue.title,
                body=issue.body,
            )
            if observed_issue_digest != source.issue_digest:
                raise SCMRevisionError(
                    "candidate_issue_drift",
                    "Issue requirements changed after the active plan was created",
                )
            base_sha = self._scm.resolve_ref(source.base_ref)
            if base_sha != source.base_sha:
                raise SCMRevisionError(
                    "candidate_base_drift",
                    "Configured base changed after the active plan was created",
                )
            resolved_head = self._scm.resolve_ref(cmd.head_sha)
            if resolved_head != cmd.head_sha:
                raise SCMRevisionError(
                    "candidate_head_mismatch",
                    "SCM did not resolve the exact submitted candidate head",
                )
            approval = self._authoritative_candidate_approval(
                issue_number=issue_number,
                issue_labels={label.name for label in issue.labels},
                contract=contract,
                plan_comment=plan_comment,
                comments=comments,
            )
            if approval.state != "approved":
                raise SCMRevisionError(
                    "candidate_approval_missing",
                    "Active plan has no attributable approval from an authoritative SCM source",
                )
            contract = contract.with_approval(approval)
            self._policy_binding = gate_policy_binding(
                self._gates_config,
                self._eval_config,
                self._architecture_policy,
                candidate_process=self._candidate_process_policy,
                scm_policy=self._scm_policy,
            )
            subject = EvaluationSubject(
                repository=self._scm.repository_identity,
                base_sha=base_sha,
                head_sha=resolved_head,
                contract_hash=contract.contract_hash,
                policy_version=str(self._policy_binding["policy_version"]),
                policy_digest=str(self._policy_binding["policy_digest"]),
            )
            comparison = self._scm.compare_commits(
                base_sha,
                resolved_head,
                max_diff_bytes=self._gates_config.parameters.max_diff_bytes,
            )
            if (
                comparison.repository != subject.repository
                or comparison.base_sha != subject.base_sha
                or comparison.head_sha != subject.head_sha
            ):
                raise SCMRevisionError(
                    "comparison_subject_mismatch",
                    "SCM comparison does not match the submitted candidate",
                    subject=subject,
                )
        except SCMRevisionError as exc:
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code=exc.code,
                reason=exc.safe_message,
            )
        except Exception as exc:  # noqa: BLE001 - provider errors fail closed
            log.error(
                "Candidate binding failed for issue #%d (%s)", issue_number, type(exc).__name__
            )
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code="candidate_binding_failed",
                reason="SCM failed while binding the submitted candidate",
            )

        submission_key = self._candidate_submission_key(issue_number, plan_comment.id, subject)
        scm = self._scm
        assert scm is not None
        common = {
            "submission_key": submission_key,
            "plan_comment_id": plan_comment.id,
            "approval_source_id": approval.source_id,
            "evaluation_subject": subject.as_dict(),
        }
        ctx = GateContext(
            issue_number=issue_number,
            branch=cmd.head_sha,
            changed_files=list(comparison.changed_files),
            diff=comparison.diff,
            plan_comment=plan_comment.body,
            project_root=self._project_root,
            path_risk_configured=self._path_risk_configured,
            subject=subject,
            correlation_id=correlation_id,
            max_quality_file_bytes=self._gates_config.parameters.max_quality_file_bytes,
            read_candidate_file=lambda path: scm.read_file_at_revision(
                subject.head_sha,
                path,
                max_file_bytes=self._gates_config.parameters.max_quality_file_bytes,
            ),
            acceptance_contract=contract.as_dict(),
            architecture_policy=self._architecture_policy,
        )
        active_gates = (set(self._gates_config.required) | set(self._gates_config.optional)) - set(
            self._gates_config.disabled
        )
        preflight_results: list[GateResult] = []
        for gate_id in PRE_FLIGHT_GATE_ORDER:
            if gate_id not in active_gates or gate_id not in GATE_REGISTRY:
                continue
            result = replace(
                GATE_REGISTRY[gate_id](ctx),
                subject=subject,
                authority=("required" if gate_id in self._gates_config.required else "optional"),
            )
            preflight_results.append(result)
            if result.gate == "7b" and isinstance(result.tool, dict):
                out_of_scope = result.tool.get("out_of_scope")
                if isinstance(out_of_scope, list) and out_of_scope:
                    self._bus.publish(
                        OutOfScopeDiff(
                            payload={
                                "issue": issue_number,
                                "evt": "out_of_scope_diff",
                                "files": out_of_scope,
                                "count": len(out_of_scope),
                                "reason": result.reason,
                                "control_id": "PRG-07B",
                                "evaluation_subject": subject.as_dict(),
                                "scope_evidence": result.tool,
                                "mutation_authority": "none",
                            },
                            correlation_id=correlation_id,
                        )
                    )
        for ext_gate in self._external_gates:
            try:
                preflight_results.append(
                    replace(ext_gate.run(ctx), subject=subject, authority="required")
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Candidate preflight gate %s failed (%s)",
                    ext_gate.name,
                    type(exc).__name__,
                )
                preflight_results.append(
                    GateResult(
                        gate=ext_gate.name,
                        passed=False,
                        status="error",
                        reason=f"External preflight error ({type(exc).__name__})",
                        subject=subject,
                        authority="required",
                    )
                )
        preflight_evidence = self._gate_evidence(preflight_results, subject)
        failed_preflight = next(
            (
                result
                for result in preflight_results
                if result.authority == "required" and result.passed is False
            ),
            None,
        )
        if failed_preflight is not None:
            return self._candidate_terminal(
                CandidateEvaluationFailed,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_evaluation_failed",
                reason_code=str(failed_preflight.reason_code or "required_preflight_failed"),
                reason=failed_preflight.reason,
                extra={**common, "preflight_gate_results": preflight_evidence},
            )

        matching_payload: dict[str, Any] | None = None
        matching_key = ""
        if use_existing_observation and self._observations is not None:
            for record in reversed(self._observations.list_observations(issue_number)):
                if record.evidence_origin != "bound_acceptance_evidence":
                    continue
                payload = record.payload
                if payload.get("evaluation_subject") != subject.as_dict():
                    continue
                try:
                    validate_completed_observation(payload)
                except (TypeError, ValueError):
                    return self._candidate_terminal(
                        CandidateEvaluationFailed,
                        issue_number=issue_number,
                        correlation_id=correlation_id,
                        status="candidate_evaluation_failed",
                        reason_code="candidate_evidence_invalid",
                        reason="Stored candidate evidence failed integrity validation",
                        extra=common,
                    )
                evidence_approval = (
                    payload.get("acceptance_evidence", {}).get("contract", {}).get("approval")
                    if isinstance(payload.get("acceptance_evidence"), dict)
                    else None
                )
                if evidence_approval != approval.as_dict():
                    continue
                matching_payload = payload
                matching_key = record.observation_key
                break

        if matching_payload is None:
            payload = {
                "issue": issue_number,
                "cat": "gates",
                "evt": "candidate_verification_pending",
                "status": "candidate_verification_pending",
                "reason_code": "bound_provider_evidence_pending",
                "reason": "No exact bound provider observation is available",
                "evaluation_authority": "approved_plan",
                "mutation_authority": "none",
                "preflight_gate_results": preflight_evidence,
                **common,
            }
            self._bus.publish(
                CandidateVerificationPending(payload=payload, correlation_id=correlation_id)
            )
            return {"ok": False, **payload}

        gate_results = matching_payload.get("gate_results", [])
        configured_required = set(self._gates_config.required)
        required_by_id = {
            item.get("gate"): item
            for item in gate_results
            if isinstance(item, dict) and item.get("authority") == "required"
        }
        missing_required = sorted(
            configured_required - set(required_by_id),
            key=lambda value: (str(type(value)), str(value)),
        )
        failed_required = [
            item for item in required_by_id.values() if item.get("passed") is not True
        ]
        terminal_extra = {
            **common,
            "observation_key": matching_key,
            "preflight_gate_results": preflight_evidence,
            "gate_results": gate_results,
        }
        if missing_required or failed_required:
            return self._candidate_terminal(
                CandidateEvaluationFailed,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_evaluation_failed",
                reason_code=(
                    "required_evidence_missing" if missing_required else "required_gate_failed"
                ),
                reason=(
                    f"Stored observation lacks required gates: {missing_required}"
                    if missing_required
                    else "Stored observation contains a non-passing required gate"
                ),
                extra=terminal_extra,
            )
        return self._candidate_terminal(
            CandidateEvaluationCompleted,
            issue_number=issue_number,
            correlation_id=correlation_id,
            status="candidate_evaluation_completed",
            reason_code="bound_evidence_accepted",
            reason="Exact bound provider observation satisfies all required gates",
            extra=terminal_extra,
        )

    def handle_provider_candidate(self, cmd: Command) -> dict[str, Any]:
        """Authorize/recover provider execution and consume exact bound evidence."""

        assert isinstance(cmd, RequestCandidateVerificationCommand)
        correlation_id = cmd.correlation_id or ""
        passive = self.handle_candidate(
            SubmitCandidateCommand(
                issue_number=cmd.issue_number,
                head_sha=cmd.head_sha,
                payload=dict(cmd.payload),
                correlation_id=correlation_id,
            ),
            use_existing_observation=False,
        )
        if passive.get("status") != "candidate_verification_pending":
            return passive
        provider_verification = self._provider_verification
        if provider_verification is None:
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=cmd.issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code="execution_provider_disabled",
                reason="No qualified execution provider is enabled",
                extra={
                    key: passive[key]
                    for key in ("submission_key", "evaluation_subject")
                    if key in passive
                },
            )
        assert self._scm is not None
        try:
            issue = self._scm.get_issue(cmd.issue_number)
            comments = self._scm.get_comments(cmd.issue_number)
            active = latest_active_plan(comments)
            if active is None:
                raise SCMRevisionError("active_plan_missing", "Active plan disappeared")
            plan_comment, contract = active
            approval = self._authoritative_candidate_approval(
                issue_number=cmd.issue_number,
                issue_labels={label.name for label in issue.labels},
                contract=contract,
                plan_comment=plan_comment,
                comments=comments,
            )
            if approval.state != "approved":
                raise SCMRevisionError(
                    "candidate_approval_missing", "Active plan approval is no longer current"
                )
            contract = contract.with_approval(approval)
            raw_subject = passive.get("evaluation_subject")
            if not isinstance(raw_subject, dict):
                raise SCMRevisionError(
                    "candidate_subject_missing", "Candidate subject is unavailable"
                )
            subject = EvaluationSubject.from_dict(raw_subject)
            if (
                plan_comment.id != passive.get("plan_comment_id")
                or approval.source_id != passive.get("approval_source_id")
                or contract.contract_hash != subject.contract_hash
            ):
                raise SCMRevisionError(
                    "candidate_authority_drift",
                    "Candidate authority changed before provider request",
                )
            automatic_criteria = tuple(
                VerificationCriterion(
                    criterion_id=criterion.criterion_id,
                    tag=criterion.tag,
                    text=criterion.text,
                )
                for criterion in contract.criteria
                if criterion.mode != "manual"
            )
            if not automatic_criteria:
                raise SCMRevisionError(
                    "provider_criteria_missing",
                    "Active plan has no automatic criteria for an execution provider",
                )
            authority = VerificationAuthority(
                issue_number=cmd.issue_number,
                plan_comment_id=plan_comment.id,
                contract_hash=contract.contract_hash,
                approval_source_id=approval.source_id,
                approval_actor=approval.actor,
                approval_method=approval.method,
            )
            progress = provider_verification.request(
                subject=subject,
                authority=authority,
                criteria=automatic_criteria,
                policy_binding=dict(self._policy_binding),
                correlation_id=correlation_id,
                new_request=cmd.new_request,
                consumer_mode="passive_candidate",
                consumer_context={"head_sha": subject.head_sha},
            )
        except SCMRevisionError as exc:
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=cmd.issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code=exc.code,
                reason=exc.safe_message,
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                "Provider request binding failed for issue #%d (%s)",
                cmd.issue_number,
                type(exc).__name__,
            )
            return self._candidate_terminal(
                CandidateSubmissionRejected,
                issue_number=cmd.issue_number,
                correlation_id=correlation_id,
                status="candidate_submission_rejected",
                reason_code="provider_request_binding_failed",
                reason="Provider request could not be bound to authoritative state",
            )

        provider_common = {
            "request_key": progress.request.request_key,
            "provider_profile": progress.request.provider_profile,
            "provider_profile_digest": progress.request.provider_profile_digest,
            "evaluation_subject": subject.as_dict(),
            "plan_comment_id": plan_comment.id,
            "approval_source_id": approval.source_id,
            "mutation_authority": "none",
            **(
                {"provider_run": progress.reference.as_dict()}
                if progress.reference is not None
                else {}
            ),
        }
        self._bus.publish(
            ProviderVerificationRequested(
                payload={
                    "issue": cmd.issue_number,
                    "cat": "gates",
                    "evt": "provider_verification_requested",
                    **provider_common,
                },
                correlation_id=correlation_id,
            )
        )
        if progress.pending:
            payload = {
                "issue": cmd.issue_number,
                "cat": "gates",
                "evt": "provider_verification_pending",
                "status": "candidate_verification_pending",
                "reason_code": progress.reason_code,
                "reason": "Bound provider verification is not terminal",
                "evaluation_authority": "approved_plan",
                **provider_common,
            }
            self._bus.publish(
                ProviderVerificationPending(payload=payload, correlation_id=correlation_id)
            )
            return {"ok": False, **payload}
        if progress.status == "blocked" or progress.evidence is None:
            self._bus.publish(
                ProviderVerificationBlocked(
                    payload={
                        "issue": cmd.issue_number,
                        "cat": "gates",
                        "evt": "provider_verification_blocked",
                        "reason_code": progress.reason_code,
                        **provider_common,
                    },
                    correlation_id=correlation_id,
                )
            )
            return self._candidate_terminal(
                CandidateEvaluationFailed,
                issue_number=cmd.issue_number,
                correlation_id=correlation_id,
                status="candidate_evaluation_failed",
                reason_code=progress.reason_code,
                reason="Bound provider verification failed closed",
                extra=provider_common,
            )

        return self._evaluate_provider_evidence(
            issue_number=cmd.issue_number,
            correlation_id=correlation_id,
            plan_comment=plan_comment,
            contract=contract,
            comments=comments,
            subject=subject,
            evidence=progress.evidence,
            provider_common=provider_common,
        )

    def _evaluate_provider_evidence(
        self,
        *,
        issue_number: int,
        correlation_id: str,
        plan_comment: Comment,
        contract: AcceptanceContract,
        comments: list[Comment],
        subject: EvaluationSubject,
        evidence: ProviderEvidence,
        provider_common: dict[str, Any],
    ) -> dict[str, Any]:
        assert self._scm is not None
        scm = self._scm

        def block_provider(reason_code: str, reason: str) -> dict[str, Any]:
            provider_verification = self._provider_verification
            if provider_verification is None:
                raise RuntimeError("provider verification disappeared during evidence evaluation")
            provider_verification.acknowledge(evidence.request_key, outcome="failed")
            self._bus.publish(
                ProviderVerificationBlocked(
                    payload={
                        "issue": issue_number,
                        "cat": "gates",
                        "evt": "provider_verification_blocked",
                        "reason_code": reason_code,
                        "evaluation_subject": subject.as_dict(),
                        "consumer_mode": "passive_candidate",
                        **provider_common,
                    },
                    correlation_id=correlation_id,
                )
            )
            return self._candidate_terminal(
                CandidateEvaluationFailed,
                issue_number=issue_number,
                correlation_id=correlation_id,
                status="candidate_evaluation_failed",
                reason_code=reason_code,
                reason=reason,
                extra=provider_common,
            )

        try:
            fresh_issue = scm.get_issue(issue_number)
            if fresh_issue.state != "open":
                raise SCMRevisionError(
                    "provider_authority_revoked",
                    "Candidate issue mapping is no longer open",
                )
            fresh_comments = scm.get_comments(issue_number)
            fresh_active = latest_active_plan(fresh_comments)
            if fresh_active is None:
                raise SCMRevisionError(
                    "provider_authority_revoked",
                    "Active plan disappeared before provider evidence use",
                )
            fresh_plan, fresh_contract = fresh_active
            fresh_source = fresh_contract.source_snapshot
            if fresh_source is None or fresh_contract.schema_version != 2:
                raise SCMRevisionError(
                    "provider_authority_drift",
                    "Active plan lost its authoritative source binding",
                )
            fresh_approval = self._authoritative_candidate_approval(
                issue_number=issue_number,
                issue_labels={label.name for label in fresh_issue.labels},
                contract=fresh_contract,
                plan_comment=fresh_plan,
                comments=fresh_comments,
            )
            if fresh_approval.state != "approved":
                raise SCMRevisionError(
                    "provider_authority_revoked",
                    "Active plan approval is no longer current",
                )
            fresh_contract = fresh_contract.with_approval(fresh_approval)
            fresh_policy = gate_policy_binding(
                self._gates_config,
                self._eval_config,
                self._architecture_policy,
                candidate_process=self._candidate_process_policy,
                scm_policy=self._scm_policy,
            )
            fresh_subject = EvaluationSubject(
                repository=scm.repository_identity,
                base_sha=scm.resolve_ref(fresh_source.base_ref),
                head_sha=scm.resolve_ref(subject.head_sha),
                contract_hash=fresh_contract.contract_hash,
                policy_version=str(fresh_policy["policy_version"]),
                policy_digest=str(fresh_policy["policy_digest"]),
            )
            if (
                fresh_plan.id != plan_comment.id
                or fresh_contract.contract_hash != contract.contract_hash
                or fresh_contract.approval != contract.approval
                or fresh_source.repository != scm.repository_identity
                or issue_revision_digest(
                    number=fresh_issue.number,
                    title=fresh_issue.title,
                    body=fresh_issue.body,
                )
                != fresh_source.issue_digest
                or fresh_subject != subject
            ):
                raise SCMRevisionError(
                    "provider_authority_drift",
                    "Plan, approval, subject, or policy changed before evidence use",
                )
            comments = fresh_comments
            plan_comment = fresh_plan
            contract = fresh_contract
        except SCMRevisionError as exc:
            return block_provider(exc.code, exc.safe_message)
        except Exception as exc:  # noqa: BLE001 - SCM failure cannot authorize evidence use
            log.warning(
                "Passive provider authority recheck failed for issue #%d (%s)",
                issue_number,
                type(exc).__name__,
            )
            return block_provider(
                "provider_authority_recheck_failed",
                "Provider authority could not be rechecked",
            )

        comparison = scm.compare_commits(
            subject.base_sha,
            subject.head_sha,
            max_diff_bytes=self._gates_config.parameters.max_diff_bytes,
        )
        if (
            comparison.repository != subject.repository
            or comparison.base_sha != subject.base_sha
            or comparison.head_sha != subject.head_sha
        ):
            return block_provider(
                "provider_subject_drift",
                "Candidate changed before provider evidence consumption",
            )
        acceptance_evidence = self._provider_acceptance_evidence(
            contract=contract,
            comments=comments,
            plan_comment=plan_comment,
            subject=subject,
            evidence=evidence,
        )
        ctx = GateContext(
            issue_number=issue_number,
            branch=subject.head_sha,
            changed_files=list(comparison.changed_files),
            diff=comparison.diff,
            plan_comment=plan_comment.body,
            project_root=self._project_root,
            path_risk_configured=self._path_risk_configured,
            subject=subject,
            correlation_id=correlation_id,
            max_quality_file_bytes=self._gates_config.parameters.max_quality_file_bytes,
            read_candidate_file=lambda path: scm.read_file_at_revision(
                subject.head_sha,
                path,
                max_file_bytes=self._gates_config.parameters.max_quality_file_bytes,
            ),
            acceptance_evidence=acceptance_evidence,
            acceptance_contract=contract.as_dict(),
            architecture_policy=self._architecture_policy,
        )
        active = (set(self._gates_config.required) | set(self._gates_config.optional)) - set(
            self._gates_config.disabled
        )
        gate_results: list[GateResult] = []
        for gate_id in [
            *[item for item in PRE_FLIGHT_GATE_ORDER if item in active],
            *sorted(
                (item for item in active if item not in PRE_FLIGHT_GATE_IDS),
                key=lambda value: (isinstance(value, str), str(value)),
            ),
        ]:
            gate_fn = GATE_REGISTRY.get(gate_id)
            if gate_fn is None:
                continue
            gate_results.append(
                replace(
                    gate_fn(ctx),
                    subject=subject,
                    authority=(
                        "required" if gate_id in self._gates_config.required else "optional"
                    ),
                )
            )
        for ext_gate in self._external_gates:
            try:
                gate_results.append(
                    replace(ext_gate.run(ctx), subject=subject, authority="required")
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Passive provider gate %s failed (%s)",
                    ext_gate.name,
                    type(exc).__name__,
                )
                gate_results.append(
                    GateResult(
                        gate=ext_gate.name,
                        passed=False,
                        status="error",
                        reason=f"External provider gate error ({type(exc).__name__})",
                        subject=subject,
                        authority="required",
                    )
                )
        gate_evidence = self._gate_evidence(gate_results, subject)
        identity = EvaluationObservationIdentity.build(
            subject=subject,
            gate_results=gate_evidence,
            acceptance_evidence=acceptance_evidence,
        )
        event_payload = {
            "issue": issue_number,
            "cat": "gates",
            "evt": "provider_gate_evaluation_completed",
            "blocked": any(
                result.authority == "required" and result.passed is not True
                for result in gate_results
            ),
            "gate_results": gate_evidence,
            "acceptance_evidence": acceptance_evidence,
            "evaluation_subject": subject.as_dict(),
            "gate_result_schema_version": GATE_RESULT_SCHEMA_VERSION,
            "observation_schema_version": identity.schema_version,
            "observation_key": identity.observation_key,
            "evidence_digest": identity.evidence_digest,
            "evaluation_mode": "execution_provider",
            "mutation_authority": "none",
            "evidence_provenance": {
                "gate_results": "bound_evaluation_subject",
                "acceptance_evidence": "bound_execution_provider",
                "provider_evidence_digest": evidence.evidence_digest,
                "request_key": evidence.request_key,
            },
            **provider_common,
        }
        self._bus.publish(
            ProviderGateEvaluationCompleted(
                payload=event_payload,
                correlation_id=correlation_id,
            )
        )
        blocked = bool(event_payload["blocked"])
        provider_verification = self._provider_verification
        if provider_verification is None:
            raise RuntimeError("provider verification disappeared during evidence evaluation")
        provider_verification.acknowledge(
            evidence.request_key,
            outcome="failed" if blocked else "completed",
        )
        return self._candidate_terminal(
            CandidateEvaluationFailed if blocked else CandidateEvaluationCompleted,
            issue_number=issue_number,
            correlation_id=correlation_id,
            status=("candidate_evaluation_failed" if blocked else "candidate_evaluation_completed"),
            reason_code=("required_gate_failed" if blocked else "bound_provider_evidence_accepted"),
            reason=(
                "Bound provider evidence contains a non-passing required gate"
                if blocked
                else "Exact bound provider evidence satisfies all required gates"
            ),
            extra={
                **provider_common,
                "observation_key": identity.observation_key,
                "gate_results": gate_evidence,
            },
        )

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, CreatePRCommand)
        issue_number = cmd.issue_number
        correlation_id = cmd.correlation_id or ""

        plan_comment: str | None = None
        plan_comment_record: Comment | None = None
        comments: list[Comment] = []
        contract: AcceptanceContract | None = None
        try:
            if self._scm is not None:
                comments = self._scm.get_comments(issue_number)
                active = latest_active_plan(comments)
                if active is not None:
                    plan_comment_record, contract = active
                    plan_comment = plan_comment_record.body
            if plan_comment:
                contract = contract or parse_acceptance_contract(plan_comment)
            subject, comparison = self._resolve_subject(cmd, contract)
            assert contract is not None
            assert plan_comment_record is not None
            self._bind_review_budget_admission(
                cmd,
                contract=contract,
                plan_comment=plan_comment_record,
                subject=subject,
            )
        except SCMRevisionError as exc:
            log.error(
                "Cannot establish evaluation subject for issue #%d (%s)",
                issue_number,
                exc.code,
            )
            return self._subject_failure(
                issue_number=issue_number,
                branch=cmd.branch,
                correlation_id=correlation_id,
                error=exc,
                subject=exc.subject or cmd.subject,
            )
        except Exception as exc:
            log.error(
                "Cannot establish evaluation subject for issue #%d (%s)",
                issue_number,
                type(exc).__name__,
            )
            return self._subject_failure(
                issue_number=issue_number,
                branch=cmd.branch,
                correlation_id=correlation_id,
                error=SCMRevisionError(
                    "subject_resolution_failed",
                    "SCM failed while establishing the evaluation subject",
                ),
                subject=cmd.subject,
            )

        cmd.subject = subject
        cmd.payload["evaluation_subject"] = subject.as_dict()
        changed_files = list(comparison.changed_files)
        diff = comparison.diff
        assert self._scm is not None  # established by _resolve_subject above
        scm = self._scm
        assert contract is not None
        assert plan_comment_record is not None
        approval = self._contract_approval(
            cmd,
            contract,
            plan_comment_record,
            comments,
            subject,
        )
        contract = contract.with_approval(approval)
        manual_receipts = manual_receipts_for_subject(
            comments,
            plan_comment_record,
            contract,
            subject,
        )
        acceptance_evidence: dict[str, Any] | None = None
        ctx = GateContext(
            issue_number=issue_number,
            branch=cmd.branch,
            changed_files=changed_files,
            diff=diff,
            plan_comment=plan_comment,
            project_root=self._project_root,
            path_risk_configured=self._path_risk_configured,
            subject=subject,
            correlation_id=correlation_id,
            max_quality_file_bytes=self._gates_config.parameters.max_quality_file_bytes,
            read_candidate_file=lambda path: scm.read_file_at_revision(
                subject.head_sha,
                path,
                max_file_bytes=self._gates_config.parameters.max_quality_file_bytes,
            ),
            acceptance_evidence=acceptance_evidence,
            acceptance_contract=contract.as_dict(),
            architecture_policy=self._architecture_policy,
        )

        results: list[GateResult] = []
        blocked = False
        provider_common: dict[str, Any] = {}
        provider_request_key = ""

        all_gate_ids = set(self._gates_config.required) | set(self._gates_config.optional)
        disabled = set(self._gates_config.disabled)
        active_gates = all_gate_ids - disabled

        def run_internal_gate(gate_id: int | str) -> None:
            nonlocal blocked
            gate_fn = GATE_REGISTRY.get(gate_id)
            if not gate_fn:
                return

            result = replace(
                gate_fn(ctx),
                subject=subject,
                authority=("required" if gate_id in self._gates_config.required else "optional"),
            )
            results.append(result)

            if result.gate == "7b" and result.tool:
                out_of_scope = result.tool.get("out_of_scope")
                if isinstance(out_of_scope, list) and out_of_scope:
                    self._bus.publish(
                        OutOfScopeDiff(
                            payload={
                                "issue": issue_number,
                                "evt": "out_of_scope_diff",
                                "files": out_of_scope,
                                "count": len(out_of_scope),
                                "reason": result.reason,
                                "control_id": "PRG-07B",
                                "evaluation_subject": subject.as_dict(),
                                "scope_evidence": result.tool,
                            },
                            correlation_id=correlation_id,
                        )
                    )

            if result.passed is False:
                is_required = gate_id in self._gates_config.required
                if is_required:
                    blocked = True
                    if result.status == "manual_pending" and gate_id in (11, 12):
                        return
                    self._bus.publish(
                        GateFailedEvent(
                            payload={
                                "issue": issue_number,
                                "gate": gate_id,
                                "reason": result.reason,
                                "status": result.status or "failed",
                                "owasp_risk": result.owasp_risk,
                                "cat": "gates",
                                "evt": "gate_failed",
                                "evaluation_subject": subject.as_dict(),
                            },
                            correlation_id=correlation_id,
                        )
                    )

        def run_external_gates() -> None:
            nonlocal blocked
            for ext_gate in self._external_gates:
                try:
                    ext_result = replace(
                        ext_gate.run(ctx),
                        subject=subject,
                        authority="required",
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "External gate %s failed (%s)",
                        ext_gate.name,
                        type(exc).__name__,
                    )
                    ext_result = GateResult(
                        gate=ext_gate.name,
                        passed=False,
                        status="error",
                        reason=f"External gate error ({type(exc).__name__})",
                        subject=subject,
                        authority="required",
                    )
                results.append(ext_result)
                if ext_result.passed is False:
                    blocked = True
                    self._bus.publish(
                        GateFailedEvent(
                            payload={
                                "issue": issue_number,
                                "gate": ext_gate.name,
                                "reason": ext_result.reason,
                                "status": ext_result.status,
                                "owasp_risk": ext_result.owasp_risk,
                                "external": True,
                                "cat": "gates",
                                "evt": "gate_failed",
                                "evaluation_subject": subject.as_dict(),
                            },
                            correlation_id=correlation_id,
                        )
                    )

        sorted_active = sorted(active_gates, key=lambda x: (isinstance(x, str), str(x)))
        preflight_ids = [gate_id for gate_id in PRE_FLIGHT_GATE_ORDER if gate_id in active_gates]
        post_candidate_ids = [
            gate_id for gate_id in sorted_active if gate_id not in PRE_FLIGHT_GATE_IDS
        ]

        for gate_id in preflight_ids:
            run_internal_gate(gate_id)

        if blocked:
            for gate_id in post_candidate_ids:
                results.append(
                    GateResult(
                        gate=gate_id,
                        passed=None,
                        executed=False,
                        status="skipped_precondition",
                        reason="Nicht ausgeführt: erforderliches Preflight-Gate fehlgeschlagen",
                        subject=subject,
                        authority=(
                            "required" if gate_id in self._gates_config.required else "optional"
                        ),
                    )
                )
            for ext_gate in self._external_gates:
                results.append(
                    GateResult(
                        gate=ext_gate.name,
                        passed=None,
                        executed=False,
                        status="skipped_precondition",
                        reason="Nicht ausgeführt: erforderliches Preflight-Gate fehlgeschlagen",
                        subject=subject,
                        authority="required",
                    )
                )
        else:
            provider_verification = self._provider_verification
            if provider_verification is not None:
                # All process-free local gates run before an external execution effect.
                run_external_gates()
                if not blocked:
                    automatic_criteria = tuple(
                        VerificationCriterion(
                            criterion_id=criterion.criterion_id,
                            tag=criterion.tag,
                            text=criterion.text,
                        )
                        for criterion in contract.criteria
                        if criterion.mode != "manual"
                    )
                    if approval.state != "approved" or not automatic_criteria:
                        reason_code = (
                            "provider_approval_missing"
                            if approval.state != "approved"
                            else "provider_criteria_missing"
                        )
                        self._bus.publish(
                            ProviderVerificationBlocked(
                                payload={
                                    "issue": issue_number,
                                    "cat": "gates",
                                    "evt": "provider_verification_blocked",
                                    "reason_code": reason_code,
                                    "evaluation_subject": subject.as_dict(),
                                },
                                correlation_id=correlation_id,
                            )
                        )
                        return {
                            "passed": False,
                            "gates_passed": False,
                            "pr_created": False,
                            "provider_blocked": True,
                            "reason_code": reason_code,
                            "results": results,
                            "evaluation_subject": subject.as_dict(),
                        }
                    authority = VerificationAuthority(
                        issue_number=issue_number,
                        plan_comment_id=plan_comment_record.id,
                        contract_hash=contract.contract_hash,
                        approval_source_id=approval.source_id,
                        approval_actor=approval.actor,
                        approval_method=approval.method,
                    )
                    consumer_context = {
                        "branch": cmd.branch,
                        "base": cmd.base or "main",
                        "acceptance_approval": approval.as_dict(),
                        **(
                            {"workspace_id": cmd.payload["workspace_id"]}
                            if isinstance(cmd.payload.get("workspace_id"), str)
                            and cmd.payload["workspace_id"]
                            else {}
                        ),
                        **(
                            {
                                "healing_origin_observation_key": cmd.payload[
                                    "healing_origin_observation_key"
                                ]
                            }
                            if isinstance(cmd.payload.get("healing_origin_observation_key"), str)
                            and cmd.payload["healing_origin_observation_key"]
                            else {}
                        ),
                    }
                    try:
                        progress = provider_verification.request(
                            subject=subject,
                            authority=authority,
                            criteria=automatic_criteria,
                            policy_binding=dict(self._policy_binding),
                            correlation_id=correlation_id,
                            consumer_mode="reference_worker",
                            consumer_context=consumer_context,
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.error(
                            "Provider request failed for issue #%d (%s)",
                            issue_number,
                            type(exc).__name__,
                        )
                        self._bus.publish(
                            ProviderVerificationBlocked(
                                payload={
                                    "issue": issue_number,
                                    "cat": "gates",
                                    "evt": "provider_verification_blocked",
                                    "reason_code": "provider_request_failed",
                                    "evaluation_subject": subject.as_dict(),
                                },
                                correlation_id=correlation_id,
                            )
                        )
                        return {
                            "passed": False,
                            "gates_passed": False,
                            "pr_created": False,
                            "provider_blocked": True,
                            "reason_code": "provider_request_failed",
                            "results": results,
                            "evaluation_subject": subject.as_dict(),
                        }
                    provider_request_key = progress.request.request_key
                    provider_common = {
                        "request_key": provider_request_key,
                        "provider_profile": progress.request.provider_profile,
                        "provider_profile_digest": progress.request.provider_profile_digest,
                        **(
                            {"provider_run": progress.reference.as_dict()}
                            if progress.reference is not None
                            else {}
                        ),
                    }
                    self._bus.publish(
                        ProviderVerificationRequested(
                            payload={
                                "issue": issue_number,
                                "cat": "gates",
                                "evt": "provider_verification_requested",
                                "evaluation_subject": subject.as_dict(),
                                "consumer_mode": "reference_worker",
                                **provider_common,
                            },
                            correlation_id=correlation_id,
                        )
                    )
                    if progress.pending:
                        provider_event_payload = {
                            "issue": issue_number,
                            "cat": "gates",
                            "evt": "provider_verification_pending",
                            "reason_code": progress.reason_code,
                            "evaluation_subject": subject.as_dict(),
                            "consumer_mode": "reference_worker",
                            **provider_common,
                        }
                        self._bus.publish(
                            ProviderVerificationPending(
                                payload=provider_event_payload,
                                correlation_id=correlation_id,
                            )
                        )
                        return {
                            "passed": False,
                            "gates_passed": False,
                            "pr_created": False,
                            "provider_pending": True,
                            "results": results,
                            **provider_event_payload,
                        }
                    if progress.status == "blocked" or progress.evidence is None:
                        provider_event_payload = {
                            "issue": issue_number,
                            "cat": "gates",
                            "evt": "provider_verification_blocked",
                            "reason_code": progress.reason_code,
                            "evaluation_subject": subject.as_dict(),
                            "consumer_mode": "reference_worker",
                            **provider_common,
                        }
                        self._bus.publish(
                            ProviderVerificationBlocked(
                                payload=provider_event_payload,
                                correlation_id=correlation_id,
                            )
                        )
                        return {
                            "passed": False,
                            "gates_passed": False,
                            "pr_created": False,
                            "provider_blocked": True,
                            "results": results,
                            **provider_event_payload,
                        }
                    try:
                        fresh_comments = scm.get_comments(issue_number)
                        fresh_active = latest_active_plan(fresh_comments)
                        if fresh_active is None:
                            raise SCMRevisionError(
                                "provider_authority_revoked",
                                "Active plan disappeared before provider evidence use",
                            )
                        fresh_plan, fresh_contract = fresh_active
                        fresh_subject, _fresh_comparison = self._resolve_subject(
                            cmd,
                            fresh_contract,
                        )
                        fresh_approval = self._contract_approval(
                            cmd,
                            fresh_contract,
                            fresh_plan,
                            fresh_comments,
                            fresh_subject,
                        )
                        if (
                            fresh_plan.id != plan_comment_record.id
                            or fresh_contract.contract_hash != contract.contract_hash
                            or fresh_approval != approval
                            or fresh_subject != subject
                        ):
                            raise SCMRevisionError(
                                "provider_authority_drift",
                                "Plan, approval, subject, or policy changed before evidence use",
                            )
                    except Exception as exc:  # noqa: BLE001
                        reason_code = (
                            exc.code
                            if isinstance(exc, SCMRevisionError)
                            else "provider_authority_recheck_failed"
                        )
                        provider_verification.acknowledge(
                            progress.request.request_key,
                            outcome="failed",
                        )
                        self._bus.publish(
                            ProviderVerificationBlocked(
                                payload={
                                    "issue": issue_number,
                                    "cat": "gates",
                                    "evt": "provider_verification_blocked",
                                    "reason_code": reason_code,
                                    "evaluation_subject": subject.as_dict(),
                                    "consumer_mode": "reference_worker",
                                    **provider_common,
                                },
                                correlation_id=correlation_id,
                            )
                        )
                        return {
                            "passed": False,
                            "gates_passed": False,
                            "pr_created": False,
                            "provider_blocked": True,
                            "reason_code": reason_code,
                            "results": results,
                            "evaluation_subject": subject.as_dict(),
                            **provider_common,
                        }
                    acceptance_evidence = self._provider_acceptance_evidence(
                        contract=contract,
                        comments=comments,
                        plan_comment=plan_comment_record,
                        subject=subject,
                        evidence=progress.evidence,
                    )
                    provider_common["provider_evidence_digest"] = progress.evidence.evidence_digest
                    ctx.acceptance_evidence = acceptance_evidence
                    for gate_id in post_candidate_ids:
                        run_internal_gate(gate_id)
            else:
                try:
                    verification = None
                    if self._bus.has_handler("VerifyAC"):
                        verification = self._bus.send(
                            VerifyACCommand(
                                subject=subject,
                                payload={
                                    "issue": issue_number,
                                    "phase": "post_implementation",
                                    "plan_text": plan_comment,
                                    "acceptance_contract": contract.as_dict(),
                                    "changed_files": changed_files,
                                    "manual_receipts": manual_receipts,
                                    "evaluation_subject": subject.as_dict(),
                                },
                                correlation_id=correlation_id,
                            )
                        )
                    if isinstance(verification, dict) and isinstance(
                        verification.get("acceptance_evidence"), dict
                    ):
                        acceptance_evidence = verification["acceptance_evidence"]
                except Exception as exc:  # noqa: BLE001
                    log.error(
                        "Acceptance verifier failed for issue #%d (%s)",
                        issue_number,
                        type(exc).__name__,
                    )
                ctx.acceptance_evidence = acceptance_evidence

                for gate_id in post_candidate_ids:
                    run_internal_gate(gate_id)
                run_external_gates()

        gate_evidence = self._gate_evidence(results, subject)
        manual_wait = blocked and only_manual_acceptance_pending(gate_evidence, acceptance_evidence)
        if manual_wait:
            try:
                checkpoint_store = self._authority
                checkpoint = (
                    checkpoint_store.get_checkpoint(
                        self._checkpoint_key(correlation_id, issue_number)
                    )
                    if checkpoint_store is not None
                    else None
                )
                event_payload = checkpoint.payload.get("event_payload") if checkpoint else None
                if (
                    checkpoint is None
                    or checkpoint_store is None
                    or not checkpoint.resume_eligible
                    or checkpoint.issue_number != issue_number
                    or checkpoint.repository != subject.repository
                    or checkpoint.head_sha != subject.head_sha
                    or checkpoint.workspace_id != cmd.payload.get("workspace_id")
                    or not isinstance(event_payload, dict)
                    or event_payload.get("evaluation_subject") != subject.as_dict()
                ):
                    raise StateStoreError(
                        "manual_pending_checkpoint_missing",
                        "The candidate has no matching resumable finalization checkpoint",
                    )
                checkpoint_store.put_checkpoint(
                    replace(
                        checkpoint,
                        boundary="manual_pending",
                        payload={
                            **checkpoint.payload,
                            "resume_status": "waiting_human_acceptance",
                        },
                    )
                )
            except StateStoreError:
                manual_wait = False
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue_number,
                            "reason": "manual_pending_checkpoint_missing",
                        },
                        correlation_id=correlation_id,
                    )
                )
        observation_identity = EvaluationObservationIdentity.build(
            subject=subject,
            gate_results=gate_evidence,
            acceptance_evidence=acceptance_evidence,
        )
        workspace_id = cmd.payload.get("workspace_id")
        mutation_authority: dict[str, Any] | None = None
        if (
            approval.state == "approved"
            and isinstance(workspace_id, str)
            and workspace_id
            and workspace_id == workspace_id.strip()
            and correlation_id
        ):
            mutation_authority = {
                "schema_version": 1,
                "authority": "mutate_candidate",
                "source": "approved_plan_workflow",
                "issue": issue_number,
                "plan_comment_id": plan_comment_record.id,
                "contract_hash": contract.contract_hash,
                "approval_source_id": approval.source_id,
                "workspace_id": workspace_id,
                "correlation_id": correlation_id,
            }
        self._bus.publish(
            GateEvaluationCompleted(
                payload={
                    "issue": issue_number,
                    "branch": cmd.branch,
                    "base": cmd.base or "main",
                    "cat": "gates",
                    "evt": "gate_evaluation_completed",
                    "blocked": blocked,
                    "manual_pending": manual_wait,
                    "gate_results": gate_evidence,
                    "acceptance_evidence": acceptance_evidence,
                    "evaluation_subject": subject.as_dict(),
                    "gate_result_schema_version": GATE_RESULT_SCHEMA_VERSION,
                    "observation_schema_version": observation_identity.schema_version,
                    "observation_key": observation_identity.observation_key,
                    "evidence_digest": observation_identity.evidence_digest,
                    "evaluation_mode": "reference_worker",
                    **provider_common,
                    **(
                        {"mutation_authority": mutation_authority}
                        if mutation_authority is not None
                        else {}
                    ),
                    **(
                        {"workspace_id": cmd.payload["workspace_id"]}
                        if "workspace_id" in cmd.payload
                        else {}
                    ),
                    "evidence_provenance": {
                        "gate_results": "bound_evaluation_subject",
                        "acceptance_evidence": (
                            "bound_acceptance_evidence"
                            if acceptance_evidence is not None
                            else "missing_evidence"
                        ),
                    },
                    **(
                        {
                            "healing_origin_observation_key": cmd.payload[
                                "healing_origin_observation_key"
                            ]
                        }
                        if "healing_origin_observation_key" in cmd.payload
                        else {}
                    ),
                },
                correlation_id=correlation_id,
            )
        )
        if provider_request_key and blocked:
            provider_verification = self._provider_verification
            if provider_verification is None:
                raise RuntimeError("provider verification disappeared before acknowledgement")
            provider_verification.acknowledge(
                provider_request_key,
                outcome="failed",
            )

        if blocked:
            if manual_wait:
                self._post_manual_instructions(issue_number, subject, contract, acceptance_evidence)
            return {
                "passed": False,
                "gates_passed": False,
                "pr_created": False,
                "manual_pending": manual_wait,
                "results": results,
                "blocked_gates": [r for r in results if r.passed is False],
                "evaluation_subject": subject.as_dict(),
                "gate_results": gate_evidence,
                "acceptance_evidence": acceptance_evidence,
                **provider_common,
            }

        # #258: Explicit success-Event so the dashboard `gates`-stage can show
        # "done" instead of "pending" (which was the case when only failure
        # events fired).
        self._bus.publish(
            GatesPassed(
                payload={
                    "issue": issue_number,
                    "gates_run": len(results),
                    "cat": "gates",
                    "evt": "gates_passed",
                    "evaluation_subject": subject.as_dict(),
                    "gate_results": gate_evidence,
                    "acceptance_evidence": acceptance_evidence,
                    **provider_common,
                },
                correlation_id=correlation_id,
            )
        )

        attribution = self._ai_attribution_fn() if self._ai_attribution_fn else None

        # _resolve_subject already established that the adapter is present.
        assert self._scm is not None

        title = f"feat: Issue #{issue_number}"
        body_parts = [f"## Issue #{issue_number}"]
        try:
            issue = self._scm.get_issue(issue_number)
            issue_title, issue_body = issue.title, issue.body
        except Exception as exc:
            log.warning("PR change context unavailable (%s)", type(exc).__name__)
            issue_title, issue_body = f"Issue #{issue_number}", "Auftragskontext nicht verfügbar."
        body_parts.append(
            "\n## Fachliche Änderung\n\n"
            + render_change_context(
                title=issue_title, context=issue_body, comparison=comparison, subject=subject
            )
        )
        if attribution:
            body_parts.append(f"\n{attribution}")
        # The reviewer briefing contains only the authoritative gate outcome.
        # Passive score observations are presented separately after PRCreated.
        body_parts.append(
            "\n"
            + self._render_reviewer_briefing(
                results,
                correlation_id,
                subject,
                contract=contract,
                acceptance_evidence=acceptance_evidence,
            )
        )
        pr_intent_key = self._pr_intent_key(correlation_id, subject)
        pr_intent_marker = f"samuel-intent:{pr_intent_key}"
        body_parts.append(f"\n<!-- {pr_intent_marker} -->")
        existing_intent: OperationIntentRecord | None = None
        if self._authority is not None:
            try:
                existing_intent = self._authority.get_intent(pr_intent_key)
                self._authority.put_intent(
                    OperationIntentRecord(
                        intent_key=pr_intent_key,
                        operation="create_pr",
                        status="pending",
                        issue_number=issue_number,
                        correlation_id=correlation_id,
                        subject_key=subject.head_sha,
                        payload={
                            "repository": subject.repository,
                            "head": cmd.branch,
                            "base": cmd.base or "main",
                            "base_sha": subject.base_sha,
                            "head_sha": subject.head_sha,
                            "intent_marker": pr_intent_marker,
                            "recovery_authority": "number_then_marker",
                            "evaluation_subject": subject.as_dict(),
                        },
                    )
                )
                checkpoint_key = self._checkpoint_key(correlation_id, issue_number)
                checkpoint = self._authority.get_checkpoint(checkpoint_key)
                if checkpoint is not None and checkpoint.resume_eligible:
                    self._authority.put_checkpoint(
                        WorkflowCheckpointRecord(
                            **{
                                **checkpoint.__dict__,
                                "boundary": "pr_pending",
                                "head_sha": subject.head_sha,
                                "payload": {
                                    **checkpoint.payload,
                                    "pr_intent_key": pr_intent_key,
                                    "pr_intent_marker": pr_intent_marker,
                                    "resume_status": "pending",
                                },
                            }
                        )
                    )
            except StateStoreError:
                return self._pr_creation_failed(
                    issue_number=issue_number,
                    branch=cmd.branch,
                    correlation_id=correlation_id,
                    results=results,
                    error_code="authority_intent_write_failed",
                    error_type="StateStoreError",
                    subject=subject,
                )
            if existing_intent is not None:
                existing_intent = self._authority.get_intent(pr_intent_key)
        try:
            pr_result = self._find_intended_pr(
                existing_intent,
                marker=pr_intent_marker,
                head=cmd.branch,
                base=cmd.base or "main",
                subject=subject,
            )
        except SCMRevisionError as exc:
            return self._subject_failure(
                issue_number=issue_number,
                branch=cmd.branch,
                correlation_id=correlation_id,
                error=exc,
                subject=subject,
            )
        try:
            if pr_result is None:
                pr_result = self._scm.create_pr(
                    head=cmd.branch,
                    base=cmd.base or "main",
                    title=title,
                    body="\n".join(body_parts),
                )
        except Exception as exc:
            error_type = type(exc).__name__
            # Deliberately do not log the exception message: provider errors
            # may contain response bodies, headers or credentials.
            log.error(
                "Failed to create PR for issue #%d via %s (%s)",
                issue_number,
                type(self._scm).__name__,
                error_type,
            )
            if self._authority is not None:
                with suppress(StateStoreError):
                    self._authority.finish_intent(
                        pr_intent_key,
                        status="failed",
                        postcondition={"pr_created": False},
                    )
            return self._pr_creation_failed(
                issue_number=issue_number,
                branch=cmd.branch,
                correlation_id=correlation_id,
                results=results,
                error_code="scm_create_pr_failed",
                error_type=error_type,
                subject=subject,
            )

        if not self._valid_pr_result(pr_result):
            log.error(
                "SCM adapter %s returned an invalid PR result for issue #%d",
                type(self._scm).__name__,
                issue_number,
            )
            if self._authority is not None:
                with suppress(StateStoreError):
                    self._authority.finish_intent(
                        pr_intent_key,
                        status="mismatch",
                        postcondition={"pr_created": True, "valid_result": False},
                    )
            return self._pr_creation_failed(
                issue_number=issue_number,
                branch=cmd.branch,
                correlation_id=correlation_id,
                results=results,
                error_code="invalid_scm_response",
                error_type="InvalidPRResponse",
                subject=subject,
            )
        assert pr_result is not None

        log.info("PR #%d created or reconciled: %s", pr_result.number, pr_result.html_url)

        try:
            pr_revision = self._scm.get_pr_revision(pr_result.number)
        except Exception as exc:
            log.error(
                "Cannot verify PR #%d evaluation subject (%s)",
                pr_result.number,
                type(exc).__name__,
            )
            if self._authority is not None:
                with suppress(StateStoreError):
                    self._authority.finish_intent(
                        pr_intent_key,
                        status="unresolved",
                        postcondition={
                            "pr_created": True,
                            "pr_number": pr_result.number,
                            "revision_verified": False,
                        },
                    )
            return self._subject_invalidated(
                issue_number=issue_number,
                branch=cmd.branch,
                correlation_id=correlation_id,
                subject=subject,
                pr_number=pr_result.number,
                pr_url=pr_result.html_url,
                results=results,
                observed=None,
                reason_code="pr_revision_unverifiable",
            )
        if not self._pr_matches_subject(pr_revision, subject):
            if self._authority is not None:
                with suppress(StateStoreError):
                    self._authority.finish_intent(
                        pr_intent_key,
                        status="mismatch",
                        postcondition={
                            "pr_created": True,
                            "pr_number": pr_result.number,
                            "revision_verified": True,
                        },
                    )
            return self._subject_invalidated(
                issue_number=issue_number,
                branch=cmd.branch,
                correlation_id=correlation_id,
                subject=subject,
                pr_number=pr_result.number,
                pr_url=pr_result.html_url,
                results=results,
                observed=pr_revision,
                reason_code="pr_revision_changed",
            )

        authority_epoch: int | None = None
        if self._authority is not None:
            try:
                current_intent = self._authority.get_intent(pr_intent_key)
                if current_intent is not None and current_intent.status == "pending":
                    authority_epoch = self._authority.finish_intent(
                        pr_intent_key,
                        status="applied",
                        postcondition={
                            "pr_created": True,
                            "pr_number": pr_result.number,
                            "head_sha": pr_revision.head_sha,
                            "base_sha": pr_revision.base_sha,
                        },
                    ).authority_epoch
                elif current_intent is not None and current_intent.status == "applied":
                    authority_epoch = self._authority.authority_status().get("epoch")
                else:
                    raise StateStoreError(
                        "state_intent_transition_invalid",
                        "PR intent is not pending or applied during reconciliation",
                    )
            except StateStoreError:
                return self._subject_invalidated(
                    issue_number=issue_number,
                    branch=cmd.branch,
                    correlation_id=correlation_id,
                    subject=subject,
                    pr_number=pr_result.number,
                    pr_url=pr_result.html_url,
                    results=results,
                    observed=pr_revision,
                    reason_code="authority_intent_write_failed",
                )

        payload: dict[str, Any] = {
            "issue": issue_number,
            "branch": cmd.branch,
            # The Review workflow step consumes the same complete diff that the
            # gate handler already inspected.  Recomputing it after PR creation
            # could review a different working-tree state.
            "diff": diff,
            "changed_files": changed_files,
            "evaluation_subject": subject.as_dict(),
            "gate_results": gate_evidence,
            "acceptance_evidence": acceptance_evidence,
            "acceptance_contract": contract.as_dict(),
            "review_required": self._review_required,
            **provider_common,
            **self._authority_event_binding(authority_epoch),
        }
        payload["pr_number"] = pr_result.number
        payload["pr_url"] = pr_result.html_url
        if "healing_origin_observation_key" in cmd.payload:
            payload["healing_origin_observation_key"] = cmd.payload[
                "healing_origin_observation_key"
            ]
        if "budget_admission_key" in cmd.payload:
            payload["budget_admission_key"] = cmd.payload["budget_admission_key"]
        if attribution:
            payload["ai_attribution"] = attribution

        if provider_request_key:
            provider_verification = self._provider_verification
            if provider_verification is None:
                raise RuntimeError("provider verification disappeared before acknowledgement")
            provider_verification.acknowledge(provider_request_key, outcome="completed")

        self._bus.publish(
            PRCreated(
                payload=payload,
                correlation_id=correlation_id,
            )
        )

        response: dict[str, Any] = {
            "passed": True,
            "gates_passed": True,
            "pr_created": True,
            "results": results,
            "blocked_gates": [],
            "pr_number": pr_result.number,
            "pr_url": pr_result.html_url,
            "evaluation_subject": subject.as_dict(),
            "gate_results": gate_evidence,
            "acceptance_evidence": acceptance_evidence,
            **provider_common,
        }
        if attribution:
            response["ai_attribution"] = attribution
        return response
