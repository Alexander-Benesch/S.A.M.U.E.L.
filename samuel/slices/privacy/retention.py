"""Retention inventory and operator-controlled stage-5c execution boundary."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from samuel.core.ports import (
    IAuthorityStateStore,
    IRetentionExecutionStore,
    IRetentionStateStore,
    IStateDiagnostics,
)
from samuel.core.retention import (
    EXECUTABLE_RETENTION_CATEGORIES,
    EXTERNAL_RETENTION_CATEGORIES,
    RetentionCategoryPolicy,
    RetentionError,
    RetentionPolicyConfig,
    retention_plan_digest,
)
from samuel.core.state import ManagedBackupRecord, RetentionExecutionRecord, StateStoreError
from samuel.core.workspaces import WorkspaceRecord

_EXTERNAL_CONTRACTS = {
    "audit_logs": ("audit_jsonl", "configured_jsonl_sinks"),
    "workspaces": ("workspace_registry", "workspaces"),
    "quarantine_worktrees": ("quarantine_worktree", "workspaces"),
}


class RetentionCoordinator:
    """Validate policy and coordinate explicitly authorized retention actions."""

    def __init__(
        self,
        *,
        policy: RetentionPolicyConfig,
        state: IRetentionStateStore,
        authority: IAuthorityStateStore,
        execution: IRetentionExecutionStore,
        audit_files: Iterable[Path] = (),
        workspaces: Iterable[WorkspaceRecord] = (),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy
        self._state = state
        self._authority = authority
        self._execution = execution
        self._audit_files = tuple(sorted({path.resolve(strict=False) for path in audit_files}))
        self._workspaces = tuple(workspaces)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def validate_catalog(self) -> list[dict[str, str]]:
        """Check schema/config completeness in both directions."""

        catalog = self._state.catalog()
        for category_id, category in self._policy.categories.items():
            if (
                category.storage in {"sqlite_table", "managed_backup"}
                and category_id != category.source
            ):
                raise RetentionError(
                    "retention_category_unknown",
                    "Runtime-state retention category identity must match its source",
                )
        configured_sources = {
            category.source
            for category in self._policy.categories.values()
            if category.storage in {"sqlite_table", "managed_backup"}
        }
        findings: list[dict[str, str]] = []
        for table in sorted(set(catalog) - configured_sources):
            findings.append(
                {
                    "code": "retention_catalog_source_unconfigured",
                    "category": table,
                    "detail": "runtime-state table has no retention category",
                }
            )
        for source in sorted(configured_sources - set(catalog)):
            raise RetentionError(
                "retention_catalog_source_unknown",
                f"Retention category references unknown runtime-state source {source!r}",
            )

        configured_external = {
            category_id
            for category_id, category in self._policy.categories.items()
            if category.storage in {"workspace_registry", "audit_jsonl", "quarantine_worktree"}
        }
        unknown_external = configured_external - EXTERNAL_RETENTION_CATEGORIES
        if unknown_external:
            raise RetentionError(
                "retention_external_category_unknown",
                "Retention configuration contains an unknown external category",
            )
        for category_id in sorted(configured_external):
            category = self._policy.categories[category_id]
            if (category.storage, category.source) != _EXTERNAL_CONTRACTS[category_id]:
                raise RetentionError(
                    "retention_external_contract_invalid",
                    "Retention external category has an invalid storage/source binding",
                )
        for category_id in sorted(EXTERNAL_RETENTION_CATEGORIES - configured_external):
            findings.append(
                {
                    "code": "retention_external_category_unconfigured",
                    "category": category_id,
                    "detail": "registered external artifact class has no retention category",
                }
            )

        for category_id, category in sorted(self._policy.categories.items()):
            if category.storage not in {"sqlite_table", "managed_backup"}:
                continue
            actual = set(catalog[category.source])
            configured = set(category.fields)
            missing = sorted(actual - configured)
            extra = sorted(configured - actual)
            if missing:
                findings.append(
                    {
                        "code": "retention_field_unclassified",
                        "category": category_id,
                        "detail": ",".join(missing),
                    }
                )
            if extra:
                raise RetentionError(
                    "retention_field_unknown",
                    f"Retention category {category_id!r} classifies unknown fields",
                )
        return findings

    def approve(self, category_id: str, *, reason: str) -> dict[str, Any]:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise RetentionError(
                "retention_approval_reason_required",
                "Retention approval requires an operator reason",
            )
        try:
            category = self._policy.categories[category_id]
        except KeyError as exc:
            raise RetentionError(
                "retention_category_unknown", "Retention approval category is unknown"
            ) from exc
        category_digest = category.policy_digest()
        result = self._execution.transition_category(
            category_id=category_id,
            category_digest=category_digest,
            profile_role_digest=self._policy.profile_role_digest,
            state="report_only",
            reason=normalized_reason,
        )
        return {
            "category": category_id,
            "category_digest": category_digest,
            "profile_role_digest": self._policy.profile_role_digest,
            "created": result.changed,
            "authority_epoch": result.authority_epoch,
        }

    def suspend(self, category_id: str, *, reason: str) -> dict[str, Any]:
        category = self._category(category_id)
        result = self._execution.transition_category(
            category_id=category_id,
            category_digest=category.policy_digest(),
            profile_role_digest=self._policy.profile_role_digest,
            state="suspended",
            reason=reason,
        )
        return {
            "category": category_id,
            "state": "suspended",
            "changed": result.changed,
            "authority_epoch": result.authority_epoch,
        }

    def set_emergency_stop(self, enabled: bool, *, reason: str) -> dict[str, Any]:
        result = self._execution.set_emergency_stop(enabled, reason=reason)
        return {
            "retention_emergency_stop": enabled,
            "changed": result.changed,
            "authority_epoch": result.authority_epoch,
        }

    def activate(
        self,
        category_id: str,
        *,
        plan_digest: str,
        cutoff_utc: datetime,
        reason: str,
    ) -> dict[str, Any]:
        category = self._category(category_id)
        if category.mode != "enforce" or category_id not in EXECUTABLE_RETENTION_CATEGORIES:
            raise RetentionError(
                "retention_enforce_not_configured",
                "Retention category is not configured for enforcement",
            )
        activated_at = self._clock().astimezone(timezone.utc)
        _, effective_period = category.effective_period(activated_at)
        if effective_period is None or cutoff_utc > effective_period.subtract_from(activated_at):
            raise RetentionError(
                "retention_cutoff_not_yet_eligible",
                "Retention cutoff includes records that are not old enough at activation",
            )
        plan = self._execution_plan(category, cutoff_utc)
        if plan["plan_digest"] != plan_digest:
            raise RetentionError(
                "retention_plan_drift",
                "Retention activation does not match the current candidate plan",
            )
        current = self._execution.get_category_state(category_id)
        if current is None or current.state not in {"report_only", "enforce"}:
            raise RetentionError(
                "retention_category_not_reviewed",
                "Retention category must be reviewed before enforcement is activated",
            )
        if (
            current.category_digest != category.policy_digest()
            or current.profile_role_digest != self._policy.profile_role_digest
        ):
            raise RetentionError(
                "retention_policy_review_stale",
                "Retention category review is stale for the active policy",
            )
        findings = self.validate_catalog()
        if findings:
            raise RetentionError(
                "retention_classification_incomplete",
                "Retention activation requires a complete current storage classification",
            )
        result = self._execution.transition_category(
            category_id=category_id,
            category_digest=category.policy_digest(),
            profile_role_digest=self._policy.profile_role_digest,
            state="enforce",
            reason=reason,
            evidence_digest=plan_digest,
            grant_cutoff_utc=cutoff_utc,
            activated_at=activated_at,
        )
        return {
            "category": category_id,
            "state": "enforce",
            "plan_digest": plan_digest,
            "changed": result.changed,
            "authority_epoch": result.authority_epoch,
        }

    def execute(
        self,
        category_id: str,
        *,
        plan_digest: str,
        cutoff_utc: datetime,
        reason: str,
    ) -> dict[str, Any]:
        if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
            raise RetentionError(
                "retention_timestamp_invalid",
                "Retention cutoff timestamps must be timezone-aware",
            )
        previous = self._execution.get_execution(plan_digest)
        if previous is not None:
            if previous.category_id != category_id or previous.cutoff_utc != cutoff_utc.astimezone(
                timezone.utc
            ):
                raise RetentionError(
                    "retention_receipt_identity_mismatch",
                    "Retention receipt does not match the requested category and cutoff",
                )
            return self._receipt_payload(previous)

        category = self._category(category_id)
        if category.mode != "enforce" or category_id != "score_derivations":
            raise RetentionError(
                "retention_execution_category_not_allowlisted",
                "Retention category has no active deletion strategy",
            )
        state = self._execution.get_category_state(category_id)
        if state is not None and state.state == "enforce":
            if (
                state.category_digest != category.policy_digest()
                or state.profile_role_digest != self._policy.profile_role_digest
                or state.evidence_digest != plan_digest
                or state.grant_cutoff_utc != cutoff_utc.astimezone(timezone.utc)
                or state.activated_at is None
            ):
                raise RetentionError(
                    "retention_grant_invalid",
                    "Retention execution requires the current exact activation grant",
                )
            _, effective_period = category.effective_period(state.activated_at)
            if effective_period is None or cutoff_utc > effective_period.subtract_from(
                state.activated_at
            ):
                raise RetentionError(
                    "retention_grant_cutoff_invalid",
                    "Retention activation grant contains an ineligible cutoff",
                )
        if self.validate_catalog():
            with suppress(StateStoreError):
                self._execution.transition_category(
                    category_id=category_id,
                    category_digest=category.policy_digest(),
                    profile_role_digest=self._policy.profile_role_digest,
                    state="suspended",
                    reason="automatic suspension after retention classification drift",
                )
            raise RetentionError(
                "retention_classification_incomplete",
                "Retention execution requires a complete current storage classification",
            )
        plan = self._execution_plan(category, cutoff_utc)
        try:
            receipt = self._execution.execute_score_derivations(
                plan_digest=plan_digest,
                category_digest=category.policy_digest(),
                profile_role_digest=self._policy.profile_role_digest,
                cutoff_utc=cutoff_utc,
                anchor=category.anchor,
                object_ids=tuple(plan["candidate_object_ids"]),
                field_classification=category.fields,
                payload_classification=category.payload_paths,
                reason=reason,
            )
        except (RetentionError, StateStoreError) as exc:
            if getattr(exc, "code", "") in {
                "state_corrupt",
                "state_io_error",
                "state_locked",
                "state_readonly",
                "state_retention_delete_mismatch",
                "state_retention_plan_drift",
                "state_retention_execution_missing",
                "state_retention_classification_invalid",
                "state_authority_witness_write_failed",
            }:
                with suppress(StateStoreError):
                    self._execution.transition_category(
                        category_id=category_id,
                        category_digest=category.policy_digest(),
                        profile_role_digest=self._policy.profile_role_digest,
                        state="suspended",
                        reason="automatic suspension after failed retention execution",
                        evidence_digest=plan_digest,
                    )
            raise
        return self._receipt_payload(receipt)

    @staticmethod
    def _receipt_payload(receipt: RetentionExecutionRecord) -> dict[str, Any]:
        return {
            "category": receipt.category_id,
            "execution_id": receipt.execution_id,
            "plan_digest": receipt.plan_digest,
            "candidate_count": receipt.candidate_count,
            "deleted_count": receipt.deleted_count,
            "status": receipt.status,
            "authority_epoch": receipt.authority_epoch,
            "executed_at": receipt.executed_at.isoformat(),
        }

    def dry_run(self, *, at: datetime | None = None) -> dict[str, Any]:
        now = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        findings = self.validate_catalog()
        categories: list[dict[str, Any]] = []
        for category_id, category in sorted(self._policy.categories.items()):
            categories.append(self._category_report(category_id, category, now, findings))

        authority_status = self._authority.authority_status()
        emergency_stop = self._state.emergency_stop()
        future_blocked = bool(
            emergency_stop or authority_status.get("reconcile_required", True) or findings
        )
        authorized = [row["category"] for row in categories if row["effective_mode"] == "enforce"]
        return {
            "schema": "samuel-retention-dry-run.v1",
            "generated_at": now.isoformat(),
            "profile": self._policy.active_profile,
            "operator_role": self._policy.operator_role,
            "profile_role_digest": self._policy.profile_role_digest,
            "managed_backup_dir": str(self._policy.managed_backup_dir),
            "retention_emergency_stop": emergency_stop,
            "reconcile_required": bool(authority_status.get("reconcile_required", True)),
            "future_enforcement_blocked": future_blocked,
            "delete_capability_present": True,
            "authorized_enforcement_categories": authorized,
            "active_enforcement_categories": [] if future_blocked else authorized,
            "categories": categories,
            "findings": sorted(
                findings,
                key=lambda item: (item["code"], item.get("category", ""), item["detail"]),
            ),
        }

    def status(self) -> dict[str, Any]:
        """Return bounded authority state for passive health and dashboard views."""

        findings = self.validate_catalog()
        authority_status = self._authority.authority_status()
        emergency_stop = self._state.emergency_stop()
        categories: list[dict[str, Any]] = []
        for category_id, category in sorted(self._policy.categories.items()):
            category_digest = category.policy_digest()
            state = self._execution.get_category_state(category_id)
            current = bool(
                state is not None
                and state.category_digest == category_digest
                and state.profile_role_digest == self._policy.profile_role_digest
            )
            if not current:
                effective_mode = "report_only_pending_review"
            elif state is not None and state.state == "suspended":
                effective_mode = "suspended"
            elif state is not None and state.state == "enforce" and category.mode == "enforce":
                effective_mode = "enforce"
            else:
                effective_mode = "report_only"
            categories.append(
                {
                    "category": category_id,
                    "effective_mode": effective_mode,
                    "category_digest": category_digest,
                    "profile_role_digest": self._policy.profile_role_digest,
                    "authority_version": state.version if current and state is not None else None,
                    "evidence_digest": (
                        state.evidence_digest if current and state is not None else None
                    ),
                    "grant_cutoff_utc": (
                        state.grant_cutoff_utc.isoformat()
                        if current and state is not None and state.grant_cutoff_utc is not None
                        else None
                    ),
                    "activated_at": (
                        state.activated_at.isoformat()
                        if current and state is not None and state.activated_at is not None
                        else None
                    ),
                }
            )
        executions = self._execution.list_executions()
        last_execution = self._receipt_payload(executions[-1]) if executions else None
        reconcile_required = bool(authority_status.get("reconcile_required", True))
        return {
            "schema": "samuel-retention-status.v1",
            "profile": self._policy.active_profile,
            "operator_role": self._policy.operator_role,
            "retention_emergency_stop": emergency_stop,
            "reconcile_required": reconcile_required,
            "future_enforcement_blocked": bool(emergency_stop or reconcile_required or findings),
            "pending_review_count": sum(
                row["effective_mode"] == "report_only_pending_review" for row in categories
            ),
            "categories": categories,
            "last_execution": last_execution,
            "findings": sorted(
                findings,
                key=lambda item: (item["code"], item.get("category", ""), item["detail"]),
            ),
        }

    def _category_report(
        self,
        category_id: str,
        category: RetentionCategoryPolicy,
        now: datetime,
        findings: list[dict[str, str]],
    ) -> dict[str, Any]:
        effective_name, period = category.effective_period(now)
        cutoff = period.subtract_from(now) if period is not None else None
        category_digest = category.policy_digest()
        state = self._execution.get_category_state(category_id)
        current = bool(
            state is not None
            and state.category_digest == category_digest
            and state.profile_role_digest == self._policy.profile_role_digest
        )
        approved = current and state is not None and state.state != "suspended"
        if not current:
            effective_mode = "report_only_pending_review"
        elif state is not None and state.state == "suspended":
            effective_mode = "suspended"
        elif state is not None and state.state == "enforce" and category.mode == "enforce":
            effective_mode = "enforce"
        else:
            effective_mode = "report_only"

        if category.storage in {"sqlite_table", "managed_backup"}:
            rows = list(self._state.snapshot(category.source).rows)
            counts = self._row_counts(category, rows, cutoff)
            if category.storage == "managed_backup":
                counts.update(self._managed_backup_files(category_id, rows, findings))
        elif category.storage == "audit_jsonl":
            counts = self._audit_counts(category_id, cutoff, findings)
        else:
            selected = [
                row
                for row in self._workspaces
                if category.storage == "workspace_registry" or row.status == "quarantined"
            ]
            counts = self._workspace_counts(category, selected, cutoff)

        plan = (
            self._execution_plan(category, cutoff, rows=rows)
            if category_id in EXECUTABLE_RETENTION_CATEGORIES and cutoff is not None
            else {"plan_digest": None, "candidate_object_ids": []}
        )
        executions = self._execution.list_executions(category_id)
        return {
            "category": category_id,
            "storage": category.storage,
            "source": category.source,
            "profile": self._policy.active_profile,
            "configured_period": category.period,
            "effective_period": effective_name,
            "cutoff_utc": cutoff.isoformat() if cutoff is not None else None,
            "anchor": category.anchor,
            "requested_mode": category.mode,
            "effective_mode": effective_mode,
            "approved": approved,
            "authority_state": state.state if current and state is not None else None,
            "authority_version": state.version if current and state is not None else None,
            "evidence_digest": state.evidence_digest if current and state is not None else None,
            "category_digest": category_digest,
            "profile_role_digest": self._policy.profile_role_digest,
            "field_classification": dict(sorted(category.fields.items())),
            "payload_classification": dict(sorted(category.payload_paths.items())),
            "protections": list(category.protections),
            "execution_strategy_available": category_id in EXECUTABLE_RETENTION_CATEGORIES,
            "plan_digest": plan["plan_digest"],
            "candidate_object_ids": plan["candidate_object_ids"],
            "last_execution": (
                {
                    "execution_id": executions[-1].execution_id,
                    "plan_digest": executions[-1].plan_digest,
                    "deleted_count": executions[-1].deleted_count,
                    "authority_epoch": executions[-1].authority_epoch,
                    "executed_at": executions[-1].executed_at.isoformat(),
                }
                if executions
                else None
            ),
            **counts,
        }

    def _category(self, category_id: str) -> RetentionCategoryPolicy:
        try:
            return self._policy.categories[category_id]
        except KeyError as exc:
            raise RetentionError(
                "retention_category_unknown", "Retention category is unknown"
            ) from exc

    def _execution_plan(
        self,
        category: RetentionCategoryPolicy,
        cutoff: datetime,
        *,
        rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if category.category_id != "score_derivations":
            raise RetentionError(
                "retention_execution_category_not_allowlisted",
                "Retention category has no registered deletion strategy",
            )
        candidates = rows if rows is not None else list(self._state.snapshot(category.source).rows)
        object_ids = tuple(
            sorted(
                str(row["score_key"])
                for row in candidates
                if (timestamp := _parse_timestamp(row.get(category.anchor))) is not None
                and timestamp < cutoff
                and _row_protection(category.category_id, row) is None
            )
        )
        return {
            "candidate_object_ids": list(object_ids),
            "plan_digest": retention_plan_digest(
                category_id=category.category_id,
                category_digest=category.policy_digest(),
                profile_role_digest=self._policy.profile_role_digest,
                cutoff_utc=cutoff,
                anchor=category.anchor,
                object_ids=object_ids,
            ),
        }

    def _managed_backup_files(
        self,
        category_id: str,
        rows: list[dict[str, Any]],
        findings: list[dict[str, str]],
    ) -> dict[str, int]:
        directory = self._policy.managed_backup_dir
        registered = {str(Path(str(row["path"])).resolve(strict=False)) for row in rows}
        try:
            artifacts = {
                str(path.resolve(strict=False))
                for path in directory.glob("*.sqlite3")
                if path.is_file() and not path.is_symlink()
            }
        except OSError:
            artifacts = set()
            findings.append(
                {
                    "code": "retention_managed_backup_directory_unreadable",
                    "category": category_id,
                    "detail": directory.name,
                }
            )
        unregistered = sorted(artifacts - registered)
        missing = sorted(registered - artifacts)
        for path in unregistered:
            findings.append(
                {
                    "code": "retention_managed_backup_unregistered",
                    "category": category_id,
                    "detail": Path(path).name,
                }
            )
        for path in missing:
            findings.append(
                {
                    "code": "retention_managed_backup_missing",
                    "category": category_id,
                    "detail": Path(path).name,
                }
            )
        return {
            "artifact_count": len(artifacts),
            "unregistered_count": len(unregistered),
            "missing_registered_count": len(missing),
        }

    def _row_counts(
        self,
        category: RetentionCategoryPolicy,
        rows: list[dict[str, Any]],
        cutoff: datetime | None,
    ) -> dict[str, Any]:
        candidates = 0
        protected = Counter[str]()
        open_restore_digests = (
            {
                str(row.get("source_digest"))
                for row in self._state.snapshot("restore_operations").rows
                if row.get("status") != "completed"
            }
            if category.category_id == "managed_backups"
            else set()
        )
        open_restore_operations = (
            {
                str(row.get("operation_id"))
                for row in self._state.snapshot("restore_operations").rows
                if row.get("status") != "completed"
            }
            if category.category_id == "reconcile_entries"
            else set()
        )
        for row in rows:
            if cutoff is None:
                protected["no_time_based_deletion"] += 1
                continue
            anchor_value = row.get(category.anchor)
            timestamp = _parse_timestamp(anchor_value)
            if timestamp is None:
                protected["missing_or_invalid_anchor"] += 1
                continue
            if timestamp >= cutoff:
                continue
            reason: str | None
            if row.get("digest") in open_restore_digests:
                reason = "open_restore_digest_pin"
            elif row.get("operation_id") in open_restore_operations:
                reason = "open_restore_never"
            else:
                reason = _row_protection(category.category_id, row)
            if reason is None:
                candidates += 1
            else:
                protected[reason] += 1
        return {
            "records": len(rows),
            "candidate_count": candidates,
            "protected_count": sum(protected.values()),
            "protection_counts": dict(sorted(protected.items())),
        }

    def _audit_counts(
        self,
        category_id: str,
        cutoff: datetime | None,
        findings: list[dict[str, str]],
    ) -> dict[str, Any]:
        candidates = 0
        protected = Counter[str]()
        for path in self._audit_files:
            status, timestamp = _last_audit_timestamp(path)
            if status != "ok":
                protected[status] += 1
                findings.append(
                    {
                        "code": f"retention_audit_{status}",
                        "category": category_id,
                        "detail": path.name,
                    }
                )
            elif cutoff is not None and timestamp is not None and timestamp < cutoff:
                candidates += 1
        return {
            "records": len(self._audit_files),
            "candidate_count": candidates,
            "protected_count": sum(protected.values()),
            "protection_counts": dict(sorted(protected.items())),
        }

    @staticmethod
    def _workspace_counts(
        category: RetentionCategoryPolicy,
        rows: list[WorkspaceRecord],
        cutoff: datetime | None,
    ) -> dict[str, Any]:
        candidates = 0
        protected = Counter[str]()
        for row in rows:
            timestamp = _parse_timestamp(getattr(row, category.anchor, None))
            if cutoff is None or timestamp is None:
                protected["workspace_lifecycle_only"] += 1
            elif timestamp < cutoff:
                protected["operator_discard_only"] += 1
        return {
            "records": len(rows),
            "candidate_count": candidates,
            "protected_count": sum(protected.values()),
            "protection_counts": dict(sorted(protected.items())),
        }


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _row_protection(category_id: str, row: dict[str, Any]) -> str | None:
    if category_id in {
        "authority_metadata",
        "authority_records",
        "legacy_imports",
        "llm_budget_attempts",
        "planning_clarifications",
        "quality_metrics",
        "schema_migrations",
        "workflow_budget_admissions",
    }:
        return "no_time_based_deletion"
    if category_id == "healing_claims":
        return "permanent_at_most_once_tombstone"
    if category_id == "workflow_checkpoints" and bool(row.get("resume_eligible")):
        return "active_or_reconcile_relevant"
    if category_id == "operation_intents" and row.get("status") in {
        "pending",
        "unresolved",
        "mismatch",
    }:
        return "active_or_reconcile_relevant"
    if (
        category_id == "operation_intents"
        and row.get("operation") == "provider_dispatch.v1"
        and row.get("status") == "applied"
    ):
        return "provider_verification_or_reconcile_relevant"
    if category_id == "restore_operations" and row.get("status") != "completed":
        return "open_restore"
    if category_id == "run_projections" and row.get("status") not in {
        "blocked",
        "complete",
        "unbound",
    }:
        return "non_terminal_never"
    return None


def _last_audit_timestamp(path: Path) -> tuple[str, datetime | None]:
    if path.is_symlink() or not path.is_file():
        return "unreadable", None
    last: datetime | None = None
    invalid = False
    saw_content = False
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                saw_content = True
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    invalid = True
                    continue
                timestamp = _parse_timestamp(event.get("ts") if isinstance(event, dict) else None)
                if timestamp is None:
                    invalid = True
                    continue
                last = timestamp
    except (OSError, UnicodeError):
        return "unreadable", None
    if not saw_content:
        return "empty", None
    if invalid:
        return "corrupt_or_partial", last
    if last is None:
        return "empty", None
    return "ok", last


def create_managed_backup(
    *,
    policy: RetentionPolicyConfig,
    diagnostics: IStateDiagnostics,
    state: IRetentionStateStore,
    at: datetime | None = None,
) -> ManagedBackupRecord:
    """Create and register one SQLite-consistent backup in the managed boundary."""

    now = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    directory = policy.managed_backup_dir
    if directory.is_symlink():
        raise StateStoreError(
            "state_managed_backup_path_unsafe",
            "Managed backup directory must not be a symbolic link",
        )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    except OSError as exc:
        raise StateStoreError(
            "state_managed_backup_path_unavailable",
            "Managed backup directory cannot be prepared",
        ) from exc
    backup_id = uuid.uuid4().hex
    filename = f"samuel-state-{now.strftime('%Y%m%dT%H%M%SZ')}-{backup_id}.sqlite3"
    destination = (directory / filename).resolve(strict=False)
    if destination.parent != directory.resolve(strict=False):
        raise StateStoreError(
            "state_managed_backup_path_unsafe",
            "Managed backup target escaped its configured directory",
        )
    diagnostics.backup(destination)
    hasher = hashlib.sha256()
    try:
        with destination.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
    except OSError as exc:
        raise StateStoreError(
            "state_managed_backup_unreadable",
            "Managed backup could not be hashed after creation",
        ) from exc
    digest = f"sha256:{hasher.hexdigest()}"
    status = diagnostics.status()
    record = ManagedBackupRecord(
        backup_id=backup_id,
        path=destination,
        digest=digest,
        instance_uuid=status.authority_instance,
        authority_epoch=status.authority_epoch,
        created_at=now,
    )
    state.register_managed_backup(record)
    return record
