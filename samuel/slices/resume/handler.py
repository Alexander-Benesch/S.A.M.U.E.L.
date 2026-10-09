from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, CreatePRCommand, ImplementCommand, ResumePendingCommand
from samuel.core.events import Event, ResumeAttempted, ResumeBlocked, ResumeCompleted
from samuel.core.ports import (
    IAuthorityStateStore,
    IConfig,
    IProviderVerificationCoordinator,
    IRunProjectionStore,
    IWorkspaceManager,
)
from samuel.core.state import (
    AuthorityRecord,
    RunProjectionRecord,
    StateStoreError,
    WorkflowCheckpointRecord,
)
from samuel.core.workflow_outcome import TERMINAL_WORKFLOW_EVENTS
from samuel.core.workspaces import WorkspaceError

log = logging.getLogger(__name__)


def _authority_key(kind: str, *parts: str) -> str:
    value = "\x00".join((kind, *parts)).encode("utf-8")
    return f"{kind}:sha256:{hashlib.sha256(value).hexdigest()}"


class ResumeCoordinator:
    """Dispatch persisted finalization checkpoints through existing commands.

    The coordinator owns no Git or SCM implementation.  The Implementation
    handler performs OS-lock, lease and state predicates through ports before
    it continues an effect.
    """

    def __init__(
        self,
        bus: Bus,
        *,
        authority_store: IAuthorityStateStore,
        workspace_manager: IWorkspaceManager,
        config: IConfig,
        owner_id: str,
        projection_store: IRunProjectionStore | None = None,
        provider_verification: IProviderVerificationCoordinator | None = None,
    ) -> None:
        self._bus = bus
        self._authority = authority_store
        self._workspaces = workspace_manager
        self._config = config
        self._owner_id = owner_id
        self._projections = projection_store
        self._provider_verification = provider_verification
        self._last_outcome: dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("agent.resume.enabled", False)) and not bool(
            self._authority.authority_status().get("reconcile_required")
        )

    def status(self) -> dict[str, Any]:
        checkpoints = self._authority.list_checkpoints()
        pending = [row for row in checkpoints if row.resume_eligible]
        blocked = [
            row
            for row in checkpoints
            if row.boundary in {"blocked", "abandoned"}
            or str(row.payload.get("resume_status", "")) in {"blocked", "abandoned"}
        ]
        latest = self._last_outcome
        if not latest and self._projections is not None:
            projections = self._projections.list_projections(series="resume")
            if projections:
                latest = dict(projections[-1].payload)
        authority = self._authority.authority_status()
        return {
            "enabled": self.enabled,
            "configured": bool(self._config.get("agent.resume.enabled", False)),
            "reconcile_required": bool(authority.get("reconcile_required")),
            "pending": len(pending),
            "blocked": len(blocked),
            "last_outcome": dict(latest),
        }

    def list(self) -> list[dict[str, Any]]:
        return [self._checkpoint_summary(row) for row in self._authority.list_checkpoints()]

    def inspect(self, checkpoint_key: str) -> dict[str, Any]:
        checkpoint = self._authority.get_checkpoint(checkpoint_key)
        if checkpoint is None:
            raise StateStoreError(
                "resume_checkpoint_missing",
                "Resume checkpoint does not exist",
            )
        workspace = (
            self._workspaces.inspect(checkpoint.workspace_id) if checkpoint.workspace_id else None
        )
        intents = self._authority.list_intents(correlation_id=checkpoint.correlation_id)
        return {
            **self._checkpoint_summary(checkpoint),
            "workspace": workspace.as_dict() if workspace is not None else None,
            "intents": [
                {
                    "intent_key": row.intent_key,
                    "operation": row.operation,
                    "status": row.status,
                    "subject_key": row.subject_key,
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in intents
            ],
        }

    @staticmethod
    def _checkpoint_summary(checkpoint: WorkflowCheckpointRecord) -> dict[str, Any]:
        return {
            "checkpoint_key": checkpoint.checkpoint_key,
            "issue": checkpoint.issue_number,
            "correlation_id": checkpoint.correlation_id,
            "workflow": checkpoint.workflow,
            "boundary": checkpoint.boundary,
            "repository": checkpoint.repository,
            "branch": checkpoint.branch,
            "base_ref": checkpoint.base_ref,
            "head_sha": checkpoint.head_sha,
            "workspace_id": checkpoint.workspace_id,
            "resume_eligible": checkpoint.resume_eligible,
            "resume_status": str(checkpoint.payload.get("resume_status", "")),
            "resume_reason": str(checkpoint.payload.get("resume_reason", "")),
            "updated_at": checkpoint.updated_at.isoformat(),
        }

    def _record_outcome(self, outcome: dict[str, Any]) -> None:
        self._last_outcome = dict(outcome)
        if self._projections is None:
            return
        try:
            self._projections.upsert_projection(
                RunProjectionRecord(
                    projection_key="resume:last-outcome",
                    issue_number=0,
                    correlation_id="",
                    series="resume",
                    status=str(outcome.get("reason") or "completed"),
                    payload=dict(outcome),
                )
            )
        except Exception:  # noqa: BLE001 - a projection cannot gain resume authority
            log.exception("Resume outcome projection failed without blocking authority")

    def handle(self, command: Command) -> dict[str, Any]:
        assert isinstance(command, ResumePendingCommand)
        requested = str(command.payload.get("checkpoint_key") or "")
        if not self.enabled:
            outcome: dict[str, Any] = {
                "enabled": False,
                "attempted": 0,
                "resumed": 0,
                "blocked": 0,
                "reason": (
                    "authority_reconcile_required"
                    if self._authority.authority_status().get("reconcile_required")
                    else "resume_disabled"
                ),
            }
            self._record_outcome(outcome)
            return outcome
        authority_status = self._authority.authority_status()
        if authority_status.get("reconcile_required"):
            outcome = {
                "enabled": True,
                "attempted": 0,
                "resumed": 0,
                "blocked": 1,
                "reason": "authority_reconcile_required",
            }
            self._record_outcome(outcome)
            return outcome

        checkpoints = self._authority.list_checkpoints(resume_eligible=True)
        if requested:
            checkpoints = [row for row in checkpoints if row.checkpoint_key == requested]
            if not checkpoints:
                outcome = {
                    "enabled": True,
                    "attempted": 0,
                    "resumed": 0,
                    "blocked": 1,
                    "reason": "resume_checkpoint_missing",
                }
                self._record_outcome(outcome)
                return outcome
        eligible_ids = {row.workspace_id for row in checkpoints if row.workspace_id}
        self._quarantine_unbound_orphans(eligible_ids)

        attempted = 0
        resumed = 0
        blocked = 0
        details: list[dict[str, Any]] = []
        for checkpoint in checkpoints:
            if checkpoint.boundary == "manual_pending":
                details.append(
                    {
                        "checkpoint_key": checkpoint.checkpoint_key,
                        "workspace_id": checkpoint.workspace_id,
                        "resumed": False,
                        "pending": True,
                        "reason": "waiting_human_acceptance",
                    }
                )
                continue
            attempted += 1
            terminal_key = _authority_key("resume-terminal", checkpoint.checkpoint_key)
            if self._authority.get_authority_record(terminal_key) is not None:
                try:
                    self._complete_terminal_cleanup(checkpoint, acquire_lock=True)
                except (StateStoreError, WorkspaceError) as exc:
                    blocked += 1
                    details.append(
                        {
                            "checkpoint_key": checkpoint.checkpoint_key,
                            "workspace_id": checkpoint.workspace_id,
                            "resumed": False,
                            "pending": True,
                            "reason": getattr(exc, "code", "resume_terminal_cleanup_failed"),
                        }
                    )
                else:
                    resumed += 1
                    details.append(
                        {
                            "checkpoint_key": checkpoint.checkpoint_key,
                            "workspace_id": checkpoint.workspace_id,
                            "resumed": True,
                            "pending": False,
                            "reason": "terminal_cleanup_reconciled",
                        }
                    )
                continue
            self._bus.publish(
                ResumeAttempted(
                    payload={
                        "issue": checkpoint.issue_number,
                        "checkpoint_key": checkpoint.checkpoint_key,
                        "workspace_id": checkpoint.workspace_id,
                        "boundary": checkpoint.boundary,
                    },
                    correlation_id=checkpoint.correlation_id,
                )
            )
            if checkpoint.workflow == "provider_verification":
                result = self._resume_provider(checkpoint)
                if result.get("resumed"):
                    resumed += 1
                    self._bus.publish(
                        ResumeCompleted(
                            payload={
                                "issue": checkpoint.issue_number,
                                "checkpoint_key": checkpoint.checkpoint_key,
                                "workspace_id": "",
                                "boundary": result.get("boundary", checkpoint.boundary),
                                "pending": bool(result.get("pending")),
                            },
                            correlation_id=checkpoint.correlation_id,
                        )
                    )
                else:
                    blocked += 1
                    self._bus.publish(
                        ResumeBlocked(
                            payload={
                                "issue": checkpoint.issue_number,
                                "checkpoint_key": checkpoint.checkpoint_key,
                                "workspace_id": "",
                                "reason": result.get("reason", "provider_resume_failed"),
                                "pending": bool(result.get("pending")),
                            },
                            correlation_id=checkpoint.correlation_id,
                        )
                    )
                details.append(
                    {
                        "checkpoint_key": checkpoint.checkpoint_key,
                        "workspace_id": "",
                        "resumed": bool(result.get("resumed")),
                        "pending": bool(result.get("pending")),
                        "reason": result.get("reason", ""),
                    }
                )
                continue
            result = self._bus.send(
                ImplementCommand(
                    issue_number=checkpoint.issue_number,
                    payload={
                        "issue": checkpoint.issue_number,
                        "branch": checkpoint.branch,
                        "workspace_id": checkpoint.workspace_id,
                        "checkpoint_key": checkpoint.checkpoint_key,
                        "resume_finalization": True,
                        **(
                            {"budget_admission_key": checkpoint.payload["budget_admission_key"]}
                            if checkpoint.payload.get("budget_admission_key")
                            else {}
                        ),
                    },
                    correlation_id=checkpoint.correlation_id,
                )
            )
            result = result if isinstance(result, dict) else {"success": False}
            if result.get("resumed"):
                resumed += 1
                self._bus.publish(
                    ResumeCompleted(
                        payload={
                            "issue": checkpoint.issue_number,
                            "checkpoint_key": checkpoint.checkpoint_key,
                            "workspace_id": checkpoint.workspace_id,
                            "boundary": result.get("boundary", checkpoint.boundary),
                        },
                        correlation_id=checkpoint.correlation_id,
                    )
                )
            else:
                blocked += 1
                self._bus.publish(
                    ResumeBlocked(
                        payload={
                            "issue": checkpoint.issue_number,
                            "checkpoint_key": checkpoint.checkpoint_key,
                            "workspace_id": checkpoint.workspace_id,
                            "reason": result.get("reason", "resume_failed"),
                            "pending": bool(result.get("pending")),
                        },
                        correlation_id=checkpoint.correlation_id,
                    )
                )
            details.append(
                {
                    "checkpoint_key": checkpoint.checkpoint_key,
                    "workspace_id": checkpoint.workspace_id,
                    "resumed": bool(result.get("resumed")),
                    "pending": bool(result.get("pending")),
                    "reason": result.get("reason", ""),
                }
            )
        outcome = {
            "enabled": True,
            "attempted": attempted,
            "resumed": resumed,
            "blocked": blocked,
            "details": details,
        }
        self._record_outcome(outcome)
        return outcome

    def _resume_provider(self, checkpoint: WorkflowCheckpointRecord) -> dict[str, Any]:
        provider = self._provider_verification
        request_key = str(checkpoint.payload.get("request_key") or "")
        if provider is None or not request_key:
            return {
                "resumed": False,
                "pending": True,
                "reason": "provider_recovery_unavailable",
            }
        try:
            progress = provider.advance(request_key)
        except Exception as exc:  # noqa: BLE001 - provider recovery remains fail-closed
            log.warning(
                "Provider recovery failed for %s (%s)",
                request_key,
                type(exc).__name__,
            )
            return {
                "resumed": False,
                "pending": True,
                "reason": "provider_recovery_failed",
            }
        status = str(getattr(progress, "status", ""))
        reason = str(getattr(progress, "reason_code", "provider_recovery_unknown"))
        if status == "blocked":
            return {"resumed": False, "pending": False, "reason": reason}
        request = getattr(progress, "request", None)
        if status == "evidence_ready" and getattr(request, "consumer_mode", "") == (
            "reference_worker"
        ):
            assert request is not None
            context = checkpoint.payload.get("consumer_context")
            if not isinstance(context, dict):
                provider.acknowledge(request_key, outcome="failed")
                return {
                    "resumed": False,
                    "pending": False,
                    "reason": "provider_consumer_context_missing",
                }
            branch = context.get("branch")
            base = context.get("base")
            if (
                not isinstance(branch, str)
                or not branch
                or branch != branch.strip()
                or not isinstance(base, str)
                or not base
                or base != base.strip()
            ):
                provider.acknowledge(request_key, outcome="failed")
                return {
                    "resumed": False,
                    "pending": False,
                    "reason": "provider_consumer_context_invalid",
                }
            command_payload: dict[str, Any] = {
                "issue": checkpoint.issue_number,
                "branch": branch,
                "base": base,
                "provider_resume": True,
            }
            for key in (
                "workspace_id",
                "healing_origin_observation_key",
                "acceptance_approval",
            ):
                value = context.get(key)
                if value is not None:
                    command_payload[key] = value
            try:
                result = self._bus.send(
                    CreatePRCommand(
                        issue_number=checkpoint.issue_number,
                        branch=branch,
                        base=base,
                        subject=request.subject,
                        payload=command_payload,
                        correlation_id=checkpoint.correlation_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - leave evidence for deterministic retry
                log.warning(
                    "Provider consumer failed for %s (%s)",
                    request_key,
                    type(exc).__name__,
                )
                return {
                    "resumed": False,
                    "pending": True,
                    "reason": "provider_consumer_failed",
                }
            if not isinstance(result, dict):
                return {
                    "resumed": False,
                    "pending": True,
                    "reason": "provider_consumer_result_invalid",
                }
            if result.get("provider_pending"):
                return {
                    "resumed": True,
                    "pending": True,
                    "reason": str(result.get("reason_code") or "provider_run_pending"),
                    "boundary": "provider_running",
                }
            if result.get("provider_blocked"):
                return {
                    "resumed": False,
                    "pending": False,
                    "reason": str(result.get("reason_code") or "provider_consumer_blocked"),
                }
            return {
                "resumed": True,
                "pending": False,
                "reason": "provider_evidence_consumed",
                "boundary": "provider_consumed",
            }
        return {
            "resumed": True,
            "pending": True,
            "reason": reason,
            "boundary": f"provider_{status}" if status else checkpoint.boundary,
        }

    def observe_terminal(self, event: Event) -> None:
        if event.name not in TERMINAL_WORKFLOW_EVENTS:
            return
        issue = int(event.payload.get("issue") or 0)
        correlation_id = event.correlation_id or ""
        if not issue or not correlation_id:
            return
        for checkpoint in self._authority.list_checkpoints(resume_eligible=True):
            if checkpoint.issue_number != issue or checkpoint.correlation_id != correlation_id:
                continue
            tombstone_key = _authority_key("resume-terminal", checkpoint.checkpoint_key)
            try:
                self._authority.put_authority_record(
                    AuthorityRecord(
                        record_key=tombstone_key,
                        kind="resume_terminal",
                        payload={
                            "checkpoint_key": checkpoint.checkpoint_key,
                            "workspace_id": checkpoint.workspace_id,
                            "terminal_event": event.name,
                            "reason": str(event.payload.get("reason") or "")[:120],
                        },
                    )
                )
                self._complete_terminal_cleanup(checkpoint, acquire_lock=False)
            except (StateStoreError, WorkspaceError):
                log.exception("Terminal resume-state cleanup failed closed")

    def _complete_terminal_cleanup(
        self,
        checkpoint: WorkflowCheckpointRecord,
        *,
        acquire_lock: bool,
    ) -> None:
        if acquire_lock and checkpoint.workspace_id:
            record = self._workspaces.inspect(checkpoint.workspace_id)
            if record is not None and record.status in {"active", "creating"}:
                self._workspaces.acquire_existing_run(
                    repository_root=Path(record.repository_root),
                    workspace_id=checkpoint.workspace_id,
                    branch=checkpoint.branch,
                )
        if checkpoint.workspace_id:
            self._workspaces.release(checkpoint.workspace_id)
        self._authority.clear_checkpoint(checkpoint.checkpoint_key)
        lease = (
            self._authority.get_lease(checkpoint.workspace_id) if checkpoint.workspace_id else None
        )
        if lease is not None:
            self._authority.release_lease(
                checkpoint.workspace_id,
                owner_id=lease.owner_id,
                expected_version=lease.version,
            )

    def abandon(self, checkpoint_key: str, *, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise StateStoreError(
                "resume_abandon_reason_required",
                "Abandoning a resume checkpoint requires an operator reason",
            )
        checkpoint = self._authority.get_checkpoint(checkpoint_key)
        if checkpoint is None or (
            not checkpoint.resume_eligible and checkpoint.boundary != "blocked"
        ):
            raise StateStoreError(
                "resume_checkpoint_missing",
                "A resumable checkpoint with this identity does not exist",
            )
        if checkpoint.workspace_id:
            self._workspaces.quarantine(
                checkpoint.workspace_id,
                reason=f"operator_abandon:{reason.strip()[:90]}",
            )
        self._authority.put_authority_record(
            AuthorityRecord(
                record_key=_authority_key("resume-abandoned", checkpoint_key),
                kind="resume_abandoned",
                payload={
                    "checkpoint_key": checkpoint_key,
                    "workspace_id": checkpoint.workspace_id,
                    "reason": reason.strip()[:120],
                },
            )
        )
        self._authority.put_checkpoint(
            replace(
                checkpoint,
                boundary="abandoned",
                resume_eligible=False,
                payload={
                    **checkpoint.payload,
                    "resume_status": "abandoned",
                    "abandon_reason": reason.strip()[:120],
                },
            )
        )
        return {
            "checkpoint_key": checkpoint_key,
            "workspace_id": checkpoint.workspace_id,
            "status": "abandoned",
        }

    def cleanup(self, checkpoint_key: str, *, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise StateStoreError(
                "resume_cleanup_reason_required",
                "Cleaning resume evidence requires an operator reason",
            )
        checkpoint = self._authority.get_checkpoint(checkpoint_key)
        if checkpoint is None or checkpoint.boundary != "abandoned":
            raise StateStoreError(
                "resume_checkpoint_not_abandoned",
                "Only an operator-abandoned resume checkpoint may be cleaned up",
            )
        self._authority.put_authority_record(
            AuthorityRecord(
                record_key=_authority_key("resume-cleanup", checkpoint_key),
                kind="resume_cleanup",
                payload={
                    "checkpoint_key": checkpoint_key,
                    "workspace_id": checkpoint.workspace_id,
                    "reason": reason.strip()[:120],
                },
            )
        )
        if checkpoint.workspace_id:
            self._workspaces.discard_quarantine(
                checkpoint.workspace_id,
                reason=reason.strip(),
            )
        self._authority.clear_checkpoint(checkpoint_key)
        lease = (
            self._authority.get_lease(checkpoint.workspace_id) if checkpoint.workspace_id else None
        )
        if lease is not None:
            self._authority.release_lease(
                checkpoint.workspace_id,
                owner_id=lease.owner_id,
                expected_version=lease.version,
            )
        return {
            "checkpoint_key": checkpoint_key,
            "workspace_id": checkpoint.workspace_id,
            "status": "cleaned",
        }

    def _quarantine_unbound_orphans(self, eligible_ids: set[str]) -> None:
        for workspace in self._workspaces.list_workspaces():
            if workspace.profile != "run" or workspace.status not in {"creating", "active"}:
                continue
            if workspace.workspace_id in eligible_ids:
                continue
            try:
                self._workspaces.quarantine(
                    workspace.workspace_id,
                    reason="owner_process_missing_without_resume_authority",
                )
            except WorkspaceError as exc:
                if exc.code != "workspace_owned":
                    log.warning("Cannot classify orphan workspace: %s", exc.code)
