"""Port-bound reconciliation of restored runtime authority.

The coordinator classifies persisted authority and external SCM effects.  It
does not know SQLite, Gitea, GitHub or Git worktree implementation details.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from samuel.core.ports import IAuthorityStateStore, IVersionControl, IWorkspaceManager
from samuel.core.state import ReconcileEntryRecord, StateStoreError

log = logging.getLogger(__name__)


class StateReconcileCoordinator:
    """Produce one complete, replace-all reconcile inventory."""

    def __init__(
        self,
        *,
        authority_store: IAuthorityStateStore,
        workspace_manager: IWorkspaceManager | None,
        scm: IVersionControl | None,
    ) -> None:
        self._authority = authority_store
        self._workspaces = workspace_manager
        self._scm = scm

    def _workspaces_required(self) -> IWorkspaceManager:
        if self._workspaces is None:
            raise StateStoreError(
                "state_reconcile_workspace_unavailable",
                "Workspace registry is required to reconcile persisted effects",
            )
        return self._workspaces

    @staticmethod
    def _entry(
        operation_id: str,
        object_type: str,
        object_key: str,
        classification: str,
        reason: str,
        evidence: dict[str, Any] | None = None,
    ) -> ReconcileEntryRecord:
        return ReconcileEntryRecord(
            operation_id=operation_id,
            object_type=object_type,
            object_key=object_key,
            classification=classification,  # type: ignore[arg-type]
            reason=reason,
            evidence=evidence or {},
        )

    def _scm_required(self) -> IVersionControl:
        if self._scm is None:
            raise StateStoreError(
                "state_reconcile_scm_unavailable",
                "SCM is required to reconcile persisted external effects",
            )
        return self._scm

    def _classify_intent(self, operation_id: str, intent: Any) -> ReconcileEntryRecord:
        payload = dict(intent.payload)
        postcondition = dict(intent.postcondition)
        evidence = {
            "operation": intent.operation,
            "persisted_status": intent.status,
            "issue": intent.issue_number,
        }
        if intent.operation == "provider_dispatch.v1":
            request_key = str(payload.get("request_key") or "")
            checkpoint = self._authority.get_checkpoint(f"provider:{request_key}")
            if checkpoint is None:
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "unresolved",
                    "provider_dispatch_checkpoint_missing",
                    evidence,
                )
            evidence["provider_boundary"] = checkpoint.boundary
            evidence["resume_eligible"] = checkpoint.resume_eligible
            if (
                intent.status == "applied"
                and checkpoint.boundary in {"provider_completed", "provider_failed"}
                and not checkpoint.resume_eligible
            ):
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "verified_effect",
                    "provider_dispatch_and_consumption_recorded",
                    evidence,
                )
            return self._entry(
                operation_id,
                "intent",
                intent.intent_key,
                "unresolved",
                (
                    "provider_dispatch_requires_reconcile"
                    if intent.status == "pending"
                    else "provider_verification_incomplete"
                ),
                evidence,
            )
        if intent.operation == "push":
            scm = self._scm_required()
            branch = str(payload.get("branch") or "")
            expected = str(
                postcondition.get("remote_head")
                or postcondition.get("expected_head")
                or payload.get("expected_head")
                or ""
            )
            if not branch or not expected:
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "unresolved",
                    "push_identity_incomplete",
                    evidence,
                )
            observed = scm.resolve_ref_optional(branch)
            evidence["remote_revision_matched"] = observed == expected
            if observed == expected:
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "verified_effect",
                    "push_revision_verified",
                    evidence,
                )
            if observed is None and intent.status in {"pending", "failed"}:
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "verified_absent",
                    "push_revision_absent",
                    evidence,
                )
            return self._entry(
                operation_id,
                "intent",
                intent.intent_key,
                "unresolved",
                "push_revision_mismatch",
                evidence,
            )

        if intent.operation == "create_pr":
            scm = self._scm_required()
            number = postcondition.get("pr_number")
            if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                marker = str(payload.get("intent_marker") or "")
                head = str(payload.get("head") or "")
                base = str(payload.get("base") or "")
                if not marker or not head or not base or intent.status != "pending":
                    return self._entry(
                        operation_id,
                        "intent",
                        intent.intent_key,
                        "unresolved",
                        "pull_request_identity_incomplete",
                        evidence,
                    )
                matched_pr = scm.find_pr_by_marker(marker, head=head, base=base)
                evidence["marker_lookup_performed"] = True
                if matched_pr is None:
                    return self._entry(
                        operation_id,
                        "intent",
                        intent.intent_key,
                        "unresolved",
                        "pull_request_effect_not_confirmed",
                        evidence,
                    )
                number = matched_pr.number
            revision = scm.get_pr_revision(number)
            expected_head = str(postcondition.get("head_sha") or payload.get("head_sha") or "")
            expected_base = str(postcondition.get("base_sha") or payload.get("base_sha") or "")
            matched = bool(expected_head and expected_base) and (
                revision.head_sha == expected_head and revision.base_sha == expected_base
            )
            evidence["pull_request_revision_matched"] = matched
            evidence["pr_number"] = number
            return self._entry(
                operation_id,
                "intent",
                intent.intent_key,
                "verified_effect" if matched else "unresolved",
                "pull_request_revision_verified" if matched else "pull_request_revision_mismatch",
                evidence,
            )

        if intent.operation == "merge_pr":
            scm = self._scm_required()
            number = payload.get("pr_number")
            expected_head = str(
                postcondition.get("head_sha") or payload.get("expected_head_sha") or ""
            )
            expected_base = str(postcondition.get("base_sha") or payload.get("base_sha") or "")
            if (
                not isinstance(number, int)
                or isinstance(number, bool)
                or number <= 0
                or not expected_head
                or not expected_base
            ):
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "unresolved",
                    "merge_identity_incomplete",
                    evidence,
                )
            pr = scm.get_pr(number)
            revision = scm.get_pr_revision(number)
            revision_matched = (
                revision.head_sha == expected_head and revision.base_sha == expected_base
            )
            evidence.update(
                {
                    "pr_number": number,
                    "pull_request_revision_matched": revision_matched,
                    "merged": pr.merged,
                }
            )
            if pr.merged and revision_matched:
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "verified_effect",
                    "merge_postcondition_verified",
                    evidence,
                )
            if not pr.merged and revision_matched and intent.status == "failed":
                return self._entry(
                    operation_id,
                    "intent",
                    intent.intent_key,
                    "verified_absent",
                    "merge_effect_absent",
                    evidence,
                )
            return self._entry(
                operation_id,
                "intent",
                intent.intent_key,
                "unresolved",
                (
                    "merge_revision_mismatch"
                    if not revision_matched
                    else "merge_effect_not_confirmed"
                ),
                evidence,
            )

        if intent.operation == "commit":
            # Commit identity is content-bound, but the current workspace port
            # deliberately exposes registry state rather than arbitrary Git
            # execution.  A restored commit therefore remains operator-visible
            # until a public workspace verification capability can prove it.
            return self._entry(
                operation_id,
                "intent",
                intent.intent_key,
                "unresolved",
                "commit_requires_workspace_verification",
                evidence,
            )

        if intent.status == "applied":
            return self._entry(
                operation_id,
                "intent",
                intent.intent_key,
                "verified_effect",
                "persisted_internal_effect_applied",
                evidence,
            )
        return self._entry(
            operation_id,
            "intent",
            intent.intent_key,
            "unresolved",
            "unknown_intent_effect",
            evidence,
        )

    def scan(self, operation_id: str) -> dict[str, Any]:
        entries: list[ReconcileEntryRecord] = []
        try:
            records = self._authority.list_authority_records()
            claims = self._authority.list_healing_claims()
            checkpoints = self._authority.list_checkpoints()
            intents = self._authority.list_intents()
            budget_admissions = self._authority.list_budget_admissions()
            budget_attempts = self._authority.list_budget_attempts()
            try:
                clarifications = self._authority.list_planning_clarifications()
            except NotImplementedError:
                clarifications = []
            leases = self._authority.list_leases()
            workspaces = self._workspaces_required().list_workspaces()

            entries.append(
                self._entry(
                    operation_id,
                    "inventory",
                    "complete",
                    "verified_effect",
                    "inventory_completed",
                    {
                        "authority_records": len(records),
                        "claims": len(claims),
                        "checkpoints": len(checkpoints),
                        "intents": len(intents),
                        "budget_admissions": len(budget_admissions),
                        "budget_attempts": len(budget_attempts),
                        "planning_clarifications": len(clarifications),
                        "leases": len(leases),
                        "workspaces": len(workspaces),
                    },
                )
            )
            checkpoints_by_key = {row.checkpoint_key: row for row in checkpoints}
            for record in records:
                if record.kind == "verification_request.v1":
                    checkpoint = checkpoints_by_key.get(f"provider:{record.record_key}")
                    consumed = bool(
                        checkpoint is not None
                        and checkpoint.boundary in {"provider_completed", "provider_failed"}
                        and not checkpoint.resume_eligible
                    )
                    entries.append(
                        self._entry(
                            operation_id,
                            "authority_record",
                            record.record_key,
                            "verified_effect" if consumed else "unresolved",
                            (
                                "verification_request_consumed"
                                if consumed
                                else "verification_request_requires_provider_reconcile"
                            ),
                            {"kind": record.kind},
                        )
                    )
                    continue
                entries.append(
                    self._entry(
                        operation_id,
                        "authority_record",
                        record.record_key,
                        "verified_effect",
                        "persisted_authority_tombstone",
                        {"kind": record.kind},
                    )
                )
            for claim in claims:
                classification = (
                    "verified_effect"
                    if claim.status == "attempted"
                    else "abandoned"
                    if claim.status == "abandoned"
                    else "unresolved"
                )
                entries.append(
                    self._entry(
                        operation_id,
                        "healing_claim",
                        claim.observation_key,
                        classification,
                        f"healing_claim_{claim.status}",
                        {"issue": claim.issue_number, "status": claim.status},
                    )
                )
            for checkpoint in checkpoints:
                entries.append(
                    self._entry(
                        operation_id,
                        "checkpoint",
                        checkpoint.checkpoint_key,
                        "unresolved" if checkpoint.resume_eligible else "verified_absent",
                        (
                            "resumable_checkpoint_requires_operator_review"
                            if checkpoint.resume_eligible
                            else "checkpoint_has_no_resume_authority"
                        ),
                        {"boundary": checkpoint.boundary, "workspace_id": checkpoint.workspace_id},
                    )
                )
            for intent in intents:
                entries.append(self._classify_intent(operation_id, intent))
            for admission in budget_admissions:
                entries.append(
                    self._entry(
                        operation_id,
                        "workflow_budget_admission",
                        admission.admission_key,
                        "verified_effect",
                        "persisted_token_authority_preserved",
                        {
                            "issue": admission.issue_number,
                            "plan_bound": bool(admission.plan_contract_hash),
                            "token_limit": admission.token_limit,
                        },
                    )
                )
            for attempt in budget_attempts:
                entries.append(
                    self._entry(
                        operation_id,
                        "llm_budget_attempt",
                        attempt.attempt_key,
                        "verified_effect",
                        (
                            "known_usage_settled"
                            if attempt.status == "settled"
                            else "reservation_preserved_fail_closed"
                        ),
                        {
                            "status": attempt.status,
                            "reserved_tokens": attempt.reserved_tokens,
                        },
                    )
                )
            for clarification in clarifications:
                if clarification.status in {"waiting", "answered"}:
                    classification = "unresolved"
                    reason = "planning_clarification_requires_operator_review"
                elif clarification.status == "planned":
                    classification = "verified_effect"
                    reason = "planning_clarification_bound_to_plan"
                else:
                    classification = "abandoned"
                    reason = f"planning_clarification_{clarification.status}"
                entries.append(
                    self._entry(
                        operation_id,
                        "planning_clarification",
                        clarification.series_key,
                        classification,
                        reason,
                        {
                            "issue": clarification.issue_number,
                            "round": clarification.round_number,
                            "status": clarification.status,
                        },
                    )
                )
            now = datetime.now(timezone.utc)
            for lease in leases:
                expired = lease.expires_at <= now
                entries.append(
                    self._entry(
                        operation_id,
                        "lease",
                        lease.resource_key,
                        "verified_absent" if expired else "unresolved",
                        "lease_expired" if expired else "live_lease_requires_operator_review",
                        {"version": lease.version, "expired": expired},
                    )
                )
            for workspace in workspaces:
                classification = (
                    "verified_effect"
                    if workspace.status == "terminal"
                    else "abandoned"
                    if workspace.status == "quarantined"
                    else "unresolved"
                )
                entries.append(
                    self._entry(
                        operation_id,
                        "workspace",
                        workspace.workspace_id,
                        classification,
                        f"workspace_{workspace.status}",
                        {"profile": workspace.profile, "status": workspace.status},
                    )
                )
            write = self._authority.replace_reconcile_scan(operation_id, entries)
        except StateStoreError as exc:
            self._authority.replace_reconcile_scan(
                operation_id,
                [],
                scan_error_code=exc.code,
            )
            return {
                "operation_id": operation_id,
                "scan_status": "scan_failed",
                "error_code": exc.code,
                "entries": 0,
            }
        except Exception as exc:  # noqa: BLE001 - external adapters fail closed
            log.error("Restore reconcile scan failed in external adapter (%s)", type(exc).__name__)
            self._authority.replace_reconcile_scan(
                operation_id,
                [],
                scan_error_code="state_reconcile_scan_failed",
            )
            return {
                "operation_id": operation_id,
                "scan_status": "scan_failed",
                "error_code": "state_reconcile_scan_failed",
                "entries": 0,
            }
        unresolved = sum(1 for entry in entries if entry.classification == "unresolved")
        return {
            "operation_id": operation_id,
            "scan_status": "completed",
            "entries": len(entries),
            "unresolved": unresolved,
            "authority_epoch": write.authority_epoch,
        }

    def status(self, operation_id: str) -> dict[str, Any]:
        entries = self._authority.list_reconcile_entries(operation_id)
        counts: dict[str, int] = {}
        for entry in entries:
            counts[entry.classification] = counts.get(entry.classification, 0) + 1
        authority = self._authority.authority_status()
        return {
            "operation_id": operation_id,
            "active": authority.get("active_restore_operation") == operation_id,
            "scan_status": authority.get("restore_scan_status"),
            "counts": counts,
            "entries": [
                {
                    "object_type": entry.object_type,
                    "object_key": entry.object_key,
                    "classification": entry.classification,
                    "reason": entry.reason,
                }
                for entry in entries
            ],
        }

    def classify(
        self,
        operation_id: str,
        object_type: str,
        object_key: str,
        *,
        classification: str,
        reason: str,
    ) -> dict[str, Any]:
        transition = self._authority.classify_reconcile_entry(
            operation_id,
            object_type,
            object_key,
            classification=classification,
            reason=reason,
        )
        return {
            "operation_id": operation_id,
            "object_type": object_type,
            "object_key": object_key,
            "classification": classification,
            "authority_epoch": transition.authority_epoch,
        }

    def complete(self, operation_id: str, *, audit_epoch: int = 0) -> dict[str, Any]:
        transition = self._authority.complete_reconcile(
            operation_id,
            audit_epoch=audit_epoch,
        )
        return {
            "operation_id": operation_id,
            "status": "completed",
            "authority_epoch": transition.authority_epoch,
        }
