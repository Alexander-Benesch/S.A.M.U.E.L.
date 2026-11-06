"""Explicit attempt retirement and fresh planning over existing authority records.

The journal fences dispatch; it is not a second workflow engine. Checkpoints,
plan revocations and their consumers keep their existing authority contracts.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
from collections.abc import Callable
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from samuel.core.acceptance import (
    PlanApprovalAuthorityError,
    PlanRevocation,
    latest_active_plan,
    render_plan_revocation,
    resolve_plan_approval,
    text_digest,
)
from samuel.core.commands import Command, ReplanIssueCommand, ResumePendingCommand
from samuel.core.configuration_session import ConfigurationConflict
from samuel.core.events import AuditEvent, Event
from samuel.core.ports import IVersionControl
from samuel.core.security_policy import redact_secrets
from samuel.core.state import AuthorityRecord, StateStoreConflict, WorkflowCheckpointRecord
from samuel.core.workflow_outcome import reduce_workflow_outcome

log = logging.getLogger(__name__)

ENTRIES = frozenset(
    {
        "PlanIssue",
        "ReplanIssue",
        "Implement",
        "CreatePR",
        "Review",
        "Heal",
        "SubmitCandidate",
        "RequestCandidateVerification",
        "Evaluate",
    }
)
TRIGGERS = frozenset({"IssueReady", "PlanApproved", "PullRequestOpened", "PullRequestUpdated"})


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class WorkflowRecovery:
    def __init__(self, bus: Any, scm: IVersionControl) -> None:
        self.bus, self.scm = bus, scm
        self.session = bus.configuration_session
        self.store = bus.authority_state_store
        self.repository = scm.repository_identity
        self.finished_observers: list[
            Callable[[AuthorityRecord, list[Event], list[str]], None]
        ] = []
        self._scope: ContextVar[Any] = ContextVar("recovery_scope", default=None)
        self._operator: ContextVar[tuple[int, str] | None] = ContextVar(
            "recovery_operator", default=None
        )

    def _records(self, issue: int) -> list[AuthorityRecord]:
        return [
            r
            for r in self.store.list_authority_records()
            if r.kind.startswith("workflow_recovery.")
            and r.payload.get("repository") == self.repository
            and r.payload.get("issue") == issue
        ]

    def _write(self, kind: str, issue: int, key: str, **payload: Any) -> AuthorityRecord:
        record = AuthorityRecord(
            record_key="workflow-recovery:" + digest([self.repository, issue, kind, key]),
            kind="workflow_recovery." + kind,
            payload={"repository": self.repository, "issue": issue, **payload},
        )
        self.store.put_authority_record(record)
        return record

    def _current(self, records: list[AuthorityRecord]) -> list[AuthorityRecord]:
        retired = {
            key for r in records if r.kind.endswith(".retired") for key in r.payload["executions"]
        }
        return [r for r in records if r.kind.endswith(".execution") and r.record_key not in retired]

    def _ends(self, records: list[AuthorityRecord]) -> dict[str, dict[str, Any]]:
        return {r.payload["execution"]: r.payload for r in records if r.kind.endswith(".end")}

    def _fenced(self, records: list[AuthorityRecord]) -> bool:
        ends = self._ends(records)
        completed = {
            key
            for r in records
            if r.kind.endswith(".retired")
            for key in r.payload.get("retirements", [])
        }
        if any(r.kind.endswith(".retiring") and r.record_key not in completed for r in records):
            return True
        return any(
            r.record_key not in ends or ends[r.record_key]["status"] in {"blocked", "aborted"}
            for r in self._current(records)
        )

    def requires_human(self, issue: int, correlation: str) -> bool:
        return any(
            r.kind.endswith(".restart") and r.payload["correlation"] == correlation
            for r in self._records(issue)
        )

    def plan_binding(self, issue: int) -> dict[str, Any] | None:
        records = self._records(issue)
        restarts = [r for r in records if r.kind.endswith(".restart")]
        if not restarts:
            return None
        active = latest_active_plan(self.scm.get_comments(issue))
        if active is None:
            return None
        return next(
            (
                r.payload
                for r in reversed(records)
                if r.kind.endswith(".plan")
                and r.payload["plan_comment_id"] == active[0].id
                and r.payload["contract_hash"] == active[1].contract_hash
            ),
            None,
        )

    def active_issue(self, issue: int) -> bool:
        scope = self._scope.get()
        return bool(scope and scope["issue"] == issue)

    def projection_is_current(self, ended: AuthorityRecord) -> bool:
        current = self._current(self._records(ended.payload["issue"]))
        return bool(
            current
            and current[-1].record_key == ended.payload["execution"]
            and self.store.get_authority_record(ended.record_key) == ended
        )

    def defer_terminal_detail(self, issue: int, detail: str, *, draft: str | None = None) -> bool:
        scope = self._scope.get()
        if not scope or scope["issue"] != issue or not self.finished_observers:
            return False
        scope.setdefault("terminal_details", []).append(redact_secrets(detail)[:300])
        if draft is not None:
            safe = redact_secrets(draft)
            scope.setdefault("terminal_drafts", []).append(
                safe[:16000] + ("\n[gekürzt]" if len(safe) > 16000 else "")
            )
        return True

    def automatic_entry_reason(self, issue: int, phase: str) -> str | None:
        """Deny stale scan inputs without granting authority from labels."""
        records = self._records(issue)
        if self._fenced(records):
            return "attempt_finished_or_unresolved"
        labels = {label.name for label in self.scm.get_issue(issue).labels}
        if labels & {"status:failed", "status:done", "status:wip", "in-progress", "needs-review"}:
            return "issue_not_at_automatic_entry"
        active = latest_active_plan(self.scm.get_comments(issue))
        if phase == "planning" and active is not None:
            return "active_plan_requires_explicit_replan"
        if phase == "approval" and active is None:
            return "planning_contract_missing"
        ends = self._ends(records)
        if any(
            r.payload["stage"] in {"PlanApproved", "Implement", "CreatePR", "Review"}
            and ends.get(r.record_key, {}).get("status") not in {"rejected", "waiting"}
            for r in self._current(records)
        ):
            return "attempt_already_dispatched"
        if phase == "planning" and any(r.kind.endswith((".retired", ".restart")) for r in records):
            clarification = self.store.find_active_planning_clarification(
                repository=self.repository, issue_number=issue
            )
            if clarification is None:
                return "explicit_new_planning_required"
        return None

    def _plan_identity(self, issue: int) -> dict[str, Any]:
        try:
            active = latest_active_plan(self.scm.get_comments(issue))
            return {"id": active[0].id, "contract_hash": active[1].contract_hash} if active else {}
        except Exception as exc:
            log.warning("Plan binding unavailable (#%d, %s)", issue, type(exc).__name__)
            return {"unknown": True}

    @staticmethod
    def _projection_event(event: Event) -> Event:
        # Projection consumers never receive raw model content or provider errors.
        keys = {
            "issue",
            "issue_number",
            "repository",
            "evaluation_subject",
            "plan_comment_id",
            "acceptance_contract",
            "branch",
            "pr",
            "pr_number",
            "review_required",
            "manual_pending",
            "healing_origin_observation_key",
            "observation_key",
            "mutation_authority",
            "reason_code",
            "gate",
            "attempt",
            "max_attempts",
        }
        payload = deepcopy({k: v for k, v in event.payload.items() if k in keys})
        if isinstance(payload.get("acceptance_contract"), dict):
            payload["acceptance_contract"] = {
                "contract_hash": payload["acceptance_contract"].get("contract_hash")
            }
        return Event(name=event.name, correlation_id=event.correlation_id, payload=payload)

    def dispatch(self, msg: Event | Command, next_: Callable[[], Any]) -> Any:
        issue = (
            getattr(msg, "issue_number", 0)
            or msg.payload.get("issue")
            or msg.payload.get("issue_number")
        )
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            return next_()
        correlation = str(msg.correlation_id or "")
        scope = self._scope.get()
        if scope is None and correlation:
            records = self._records(issue)
            current_keys = {r.record_key for r in self._current(records)}
            if any(
                r.kind.endswith(".execution")
                and r.record_key not in current_keys
                and r.payload["correlation"] == correlation
                for r in records
            ):
                return {
                    "success": False,
                    "code": "workflow_recovery_required",
                    "reason": "retired_attempt",
                }
        if (
            isinstance(msg, Event)
            and scope
            and scope["issue"] == issue
            and scope["correlation"] == correlation
        ):
            scope["events"].append(self._projection_event(msg))
            scope["facts"].append(
                (
                    msg.name,
                    {
                        k: v
                        for k, v in msg.payload.items()
                        if k in {"reason", "reason_code", "manual_pending", "review_required"}
                    },
                )
            )
            if msg.name == "PlanPosted" and self.requires_human(issue, correlation):
                contract = msg.payload.get("acceptance_contract", {})
                self._write(
                    "plan",
                    issue,
                    correlation,
                    correlation=correlation,
                    plan_comment_id=msg.payload["plan_comment_id"],
                    contract_hash=contract.get("contract_hash", ""),
                    branch=f"samuel/issue-{issue}-attempt-{digest(correlation)[:12]}",
                )
        if scope and scope["issue"] == issue and scope["correlation"] == correlation:
            return self._invoke(msg, issue, next_)
        entry = isinstance(msg, Command) and msg.name in ENTRIES or msg.name in TRIGGERS
        if not entry:
            return next_()
        try:
            with (
                self.session.admission(msg.name),
                self.store.workflow_lock(digest([self.repository, issue])),
            ):
                return self._dispatch_entry(msg, issue, correlation, next_)
        except StateStoreConflict as exc:
            raise ConfigurationConflict("Issue wird bereits bearbeitet.") from exc

    def resume_provider(
        self, checkpoint: WorkflowCheckpointRecord, next_: Callable[[], Any]
    ) -> dict[str, Any]:
        """Guard the existing provider coordinator before polling or consuming evidence."""
        with (
            self.session.admission("ResumePending"),
            self.store.workflow_lock(digest([self.repository, checkpoint.issue_number])),
        ):
            persisted = self.store.get_checkpoint(checkpoint.checkpoint_key)
            if (
                persisted != checkpoint
                or not checkpoint.resume_eligible
                or checkpoint.repository != self.repository
                or checkpoint.workflow != "provider_verification"
            ):
                return {"resumed": False, "pending": False, "reason": "resume_checkpoint_changed"}
            msg = ResumePendingCommand(
                payload={
                    "issue": checkpoint.issue_number,
                    "checkpoint_key": checkpoint.checkpoint_key,
                },
                correlation_id=checkpoint.correlation_id,
            )
            result = self._dispatch_entry(
                msg, checkpoint.issue_number, checkpoint.correlation_id, next_, provider_resume=True
            )
            assert isinstance(result, dict)
            return result

    def _dispatch_entry(
        self,
        msg: Event | Command,
        issue: int,
        correlation: str,
        next_: Callable[[], Any],
        *,
        provider_resume: bool = False,
    ) -> Any:
        records = self._records(issue)
        operator = self._operator.get() == (issue, correlation)
        continuation = False
        if not operator and msg.name in {"PlanIssue", "IssueReady"} and not self._fenced(records):
            clarification = self.store.find_active_planning_clarification(
                repository=self.repository, issue_number=issue
            )
            if (
                clarification
                and self.requires_human(issue, clarification.correlation_id)
                and any(
                    r.payload["correlation"] == clarification.correlation_id
                    for r in self._current(records)
                )
            ):
                # Poll only this unfinished, source-bound series. Source drift
                # must block rather than authorize another series via `run`.
                continuation = True
                correlation = clarification.correlation_id
                msg.correlation_id = correlation
                msg.payload["clarification_continuation_authorized"] = False
                if hasattr(msg, "clarification_continuation_authorized"):
                    msg.clarification_continuation_authorized = False
        checkpoint_key = str(msg.payload.get("checkpoint_key") or "")
        checkpoint = self.store.get_checkpoint(checkpoint_key) if checkpoint_key else None
        technical_resume = provider_resume or (
            msg.name == "Implement"
            and msg.payload.get("resume_finalization") is True
            and checkpoint is not None
            and checkpoint.resume_eligible
            and checkpoint.issue_number == issue
            and checkpoint.repository == self.repository
            and checkpoint.boundary
            in {"commit_pending", "push_pending", "gates_pending", "pr_pending"}
            and checkpoint.correlation_id == correlation
        )
        if (
            not records
            and not operator
            and not technical_resume
            and any(label.name == "status:failed" for label in self.scm.get_issue(issue).labels)
        ):
            # Legacy labels may deny automatic entry, never grant authority.
            return {
                "success": False,
                "code": "workflow_recovery_required",
                "reason": "legacy_failure_requires_new_planning",
            }
        ends = self._ends(records)
        terminal = any(
            ends.get(r.record_key, {}).get("status") in {"blocked", "aborted"}
            for r in self._current(records)
        )
        retired_correlations = {
            r.payload["correlation"]
            for r in records
            if r.kind.endswith(".execution") and r not in self._current(records)
        }
        if correlation in retired_correlations or (
            not operator and self._fenced(records) and not (technical_resume and not terminal)
        ):
            return {
                "success": False,
                "code": "workflow_recovery_required",
                "reason": "attempt_finished_or_unresolved",
                "issue": issue,
                "next_action": "recovery inspect",
            }
        if (
            not operator
            and not continuation
            and msg.name in {"PlanIssue", "IssueReady", "ReplanIssue"}
            and any(r.kind.endswith((".retired", ".restart")) for r in records)
        ):
            return {
                "success": False,
                "code": "workflow_recovery_required",
                "reason": "explicit_new_planning_required",
                "issue": issue,
            }
        if (
            not operator
            and not continuation
            and any(r.kind.endswith(".retired") for r in records)
            and self.plan_binding(issue) is None
        ):
            return {
                "success": False,
                "code": "workflow_recovery_required",
                "reason": "explicit_new_planning_required",
            }
        if not operator and not technical_resume and msg.name == "PlanApproved":
            reason = self.automatic_entry_reason(issue, "approval")
            if reason:
                return {"success": False, "code": "workflow_recovery_required", "reason": reason}
        execution = self._write(
            "execution",
            issue,
            str(uuid4()),
            correlation=correlation,
            stage=msg.name,
            plan_binding=self._plan_identity(issue),
        )
        scope: dict[str, Any] = {
            "issue": issue,
            "correlation": correlation,
            "facts": [],
            "events": [self._projection_event(msg)] if isinstance(msg, Event) else [],
        }
        token = self._scope.set(scope)
        try:
            result = self._invoke(msg, issue, next_)
            outcome = reduce_workflow_outcome(scope["facts"])
            # A rejected implicit run is not failure of the still-valid plan.
            status: str = (
                "rejected" if outcome.terminal_event == "PlanReplanRejected" else outcome.status
            )
            reason = next(
                (
                    str(p.get("reason_code") or p.get("reason") or "")
                    for n, p in reversed(scope["facts"])
                    if n == outcome.terminal_event
                ),
                "",
            )
            if (
                isinstance(result, dict)
                and (
                    result.get("success") is False
                    or (provider_resume and result.get("resumed") is False)
                )
                and not result.get("pending")
            ):
                result_reason = str(result.get("reason") or "operation_failed")
                if result_reason == "waiting_human_approval" or result_reason.startswith(
                    "plan_approval_"
                ):
                    status = "waiting"
                elif outcome.terminal_event != "PlanReplanRejected":
                    status = "blocked"
                    reason = result_reason
            ended = self._write(
                "end",
                issue,
                execution.record_key,
                execution=execution.record_key,
                correlation=correlation,
                status=status,
                event=outcome.terminal_event,
                stage=msg.name,
                reason=redact_secrets(reason)[:160],
                plan_binding=execution.payload["plan_binding"],
                terminal_details=list(dict.fromkeys(scope.get("terminal_details", [])))[:5],
            )
            if (
                technical_resume
                and isinstance(result, dict)
                and result.get("resumed")
                and not result.get("pending")
            ):
                for original in self._current(records):
                    if (
                        original.record_key not in ends
                        and original.payload["correlation"] == correlation
                    ):
                        self._write(
                            "end",
                            issue,
                            original.record_key,
                            execution=original.record_key,
                            correlation=correlation,
                            status=status,
                            event=outcome.terminal_event,
                            stage=original.payload["stage"],
                            reason="technical_finalization_completed",
                        )
            for observer in self.finished_observers:
                try:
                    observer(ended, scope["events"], scope.get("terminal_drafts", []))
                except Exception as exc:
                    # A projection failure cannot change the durable outcome.
                    log.warning("Workflow projection deferred (#%d, %s)", issue, type(exc).__name__)
            return result
        finally:
            self._scope.reset(token)

    def _invoke(self, msg: Event | Command, issue: int, next_: Callable[[], Any]) -> Any:
        if msg.name in {"Implement", "PlanApproved"} and not msg.payload.get("resume_finalization"):
            binding = self.plan_binding(issue)
            if binding:
                approval = msg.payload.get("acceptance_approval", {})
                if (
                    approval.get("method") == "plan_validated"
                    or approval.get("state") != "approved"
                ):
                    return {
                        "success": False,
                        "code": "workflow_recovery_required",
                        "reason": "waiting_human_approval",
                    }
                comments = self.scm.get_comments(issue)
                active = latest_active_plan(comments)
                if active is None:
                    return {
                        "success": False,
                        "code": "workflow_recovery_required",
                        "reason": "planning_contract_missing",
                    }
                try:
                    verified = resolve_plan_approval(
                        self.store,
                        scm=self.scm,
                        repository=self.repository,
                        issue_number=issue,
                        plan_comment=active[0],
                        contract=active[1],
                        comments=comments,
                        supplied=approval,
                    )
                except PlanApprovalAuthorityError as exc:
                    return {
                        "success": False,
                        "code": "workflow_recovery_required",
                        "reason": exc.code,
                    }
                if verified.method == "plan_validated":
                    return {
                        "success": False,
                        "code": "workflow_recovery_required",
                        "reason": "waiting_human_approval",
                    }
                msg.payload["acceptance_approval"] = verified.as_dict()
                msg.payload["branch"] = binding["branch"]
        try:
            return next_()
        except Exception:
            scope = self._scope.get()
            if scope is not None:
                scope["facts"].append(("WorkflowBlocked", {"reason": "dispatch_exception"}))
            raise

    def inspect(self, issue: int) -> dict[str, Any]:
        if isinstance(issue, bool) or issue <= 0:
            raise ValueError("invalid_issue")
        records = self._records(issue)
        current = self._current(records)
        ends = self._ends(records)
        scm_issue = self.scm.get_issue(issue)
        comments = self.scm.get_comments(issue)
        active = latest_active_plan(comments)
        clarification = self.store.find_active_planning_clarification(
            repository=self.repository, issue_number=issue
        )
        labels = sorted(label.name for label in scm_issue.labels)
        checkpoints = [
            r
            for r in self.store.list_checkpoints()
            if r.issue_number == issue and r.resume_eligible
        ]
        intents = [
            r
            for r in self.store.list_intents()
            if r.issue_number == issue and r.status not in {"applied", "failed"}
        ]
        claims = [
            r
            for r in self.store.list_healing_claims()
            if r.issue_number == issue and r.status == "claimed"
        ]
        admissions = {
            r.admission_key
            for r in self.store.list_budget_admissions()
            if r.repository == self.repository and r.issue_number == issue
        }
        reservations = [
            r
            for r in self.store.list_budget_attempts()
            if r.admission_key in admissions and r.status == "reserved"
        ]
        problems = []
        if any(r.repository != self.repository for r in checkpoints):
            problems.append("foreign_checkpoint_binding")
        if self.store.authority_status().get("reconcile_required"):
            problems.append("authority_reconcile_required")
        if self.session.state()["phase"] != "idle":
            problems.append("configuration_mode_active")
        if self.session.state()["active"]:
            problems.append("execution_active_or_unreconciled")
        if intents:
            problems.append("external_effect_unresolved")
        if claims or reservations:
            problems.append("healing_or_budget_unresolved")
        if "status:done" in labels:
            problems.append("issue_already_completed")
        if scm_issue.state != "open":
            problems.append("issue_not_open")
        # The existing SCM port does not list arbitrary PRs. Use the bound
        # observed PR identities and fail closed on an unexplained review label.
        pr_numbers = set()
        projections = self.bus.run_projection_store
        if projections is not None:
            for row in projections.list_projections(issue_number=issue, series="workflow-run.v1"):
                for envelope in row.payload.get("events", []):
                    p = envelope.get("payload", {})
                    if p.get("message_name") == "PRCreated":
                        number = p.get("pr_number") or p.get("pr")
                        if isinstance(number, int):
                            pr_numbers.add(number)
                        else:
                            problems.append("pr_identity_unresolved")
        for intent in self.store.list_intents():
            if (
                intent.issue_number == issue
                and intent.operation == "create_pr"
                and intent.status == "applied"
            ):
                number = intent.postcondition.get("pr_number")
                if isinstance(number, int):
                    pr_numbers.add(number)
                else:
                    problems.append("pr_identity_unresolved")
        for number in sorted(pr_numbers):
            pr = self.scm.get_pr(number)
            if pr.state == "open" or pr.merged:
                problems.append("existing_pr_requires_resolution")
        if "needs-review" in labels and not pr_numbers:
            problems.append("pr_identity_unresolved")
        if {"status:wip", "in-progress"} & set(labels) and not current:
            problems.append("execution_history_unavailable")
        latest = next((ends[r.record_key] for r in reversed(current) if r.record_key in ends), {})
        interrupted = any(r.record_key not in ends for r in current)
        phase = (
            "interrupted"
            if interrupted
            else "finished"
            if self._fenced(records)
            else "waiting"
            if active or clarification
            else "idle"
        )
        reason = (
            latest.get("reason")
            or latest.get("event")
            or (
                "dispatch_interrupted"
                if interrupted
                else "active_plan"
                if active
                else "clarification_waiting"
                if clarification
                else "no_attempt"
            )
        )
        actions = []
        technical = [
            r
            for r in checkpoints
            if r.boundary in {"commit_pending", "push_pending", "gates_pending", "pr_pending"}
            or r.workflow == "provider_verification"
        ]
        if (
            technical
            and not (set(problems) - {"external_effect_unresolved"})
            and not any(
                ends.get(r.record_key, {}).get("status") in {"blocked", "aborted"} for r in current
            )
        ):
            actions.append("resume")
        if not problems:
            # Explicit, versioned operator intent can also start fresh planning
            # for legacy failures without this journal. It grants no old stage,
            # approval or candidate authority.
            if current or active or self._fenced(records):
                actions.append("end")
            actions.append("replan")
        fingerprint = {
            "records": [(r.record_key, r.payload) for r in records],
            "plan": active[0].id if active else None,
            "contract": active[1].contract_hash if active else None,
            "clarification": (clarification.series_key, clarification.version)
            if clarification
            else None,
            "labels": labels,
            "issue_state": scm_issue.state,
            "issue_digest": digest([scm_issue.title, scm_issue.body]),
            "checkpoints": [
                (r.checkpoint_key, r.boundary, r.updated_at.isoformat()) for r in checkpoints
            ],
            "problems": problems,
        }
        reason = redact_secrets(str(reason))[:160]
        return {
            "issue": issue,
            "attempt": current[-1].payload["correlation"] if current else None,
            "stage": {
                "PlanIssue": "planning",
                "ReplanIssue": "planning",
                "IssueReady": "planning",
                "Implement": "implementation",
                "PlanApproved": "implementation",
                "CreatePR": "delivery",
                "Review": "review",
                "Heal": "healing",
                "SubmitCandidate": "evaluation",
                "Evaluate": "evaluation",
                "RequestCandidateVerification": "verification",
            }.get(
                str(current[-1].payload["stage"] if interrupted else latest.get("stage")),
                "planning" if active or clarification else "unknown",
            ),
            "status": phase,
            "reason": reason,
            "recoverability": "technical_only"
            if "resume" in actions
            else "human_action_required"
            if problems
            else "new_planning_only",
            "automatic_retry": False,
            "safe_entry": "technical_finalization"
            if "resume" in actions
            else "planning"
            if "replan" in actions
            else "none",
            "actions": actions,
            "blockers": problems,
            "version": digest(fingerprint),
            "checkpoints": [r.checkpoint_key for r in technical],
            "next_action": "Zuerst offene Vorgänge klären."
            if problems
            else "Technischen Abschluss fortsetzen oder Versuch ausdrücklich beenden."
            if "resume" in actions
            else "Versuch beenden; Ursache beheben und ausdrücklich neu planen. Neue Freigabe erforderlich.",
        }

    def action(
        self, issue: int, action: str, version: str, reason: str, actor: str
    ) -> dict[str, Any]:
        if action not in {"end", "replan", "resume"}:
            raise ValueError("unsupported_recovery_action")
        if action != "resume" and (not reason.strip() or len(reason) > 1000):
            raise ValueError("operator_reason_required")
        with self.session.operator_action():
            status = self.inspect(issue)
            if status["version"] != version:
                raise ConfigurationConflict("Zustand geändert; Ansicht neu laden.")
            if action not in status["actions"]:
                raise ConfigurationConflict(
                    "; ".join(status["blockers"]) or "Aktion nicht verfügbar."
                )
            if action == "resume":
                return {
                    "updated": True,
                    "result": [
                        self.bus.send(ResumePendingCommand(payload={"checkpoint_key": key}))
                        for key in status["checkpoints"]
                    ],
                }
            self._retire(issue, version, reason, actor)
            if action == "end":
                return {"updated": True, "recovery": self.inspect(issue)}
            self.session.refresh(self.session.state()["revision"])
            correlation = str(uuid4())
            self._write(
                "restart",
                issue,
                version,
                correlation=correlation,
                actor=actor,
                previous_version=version,
                reason_digest=text_digest(reason),
            )
            self.bus.publish(
                AuditEvent(
                    payload={
                        "action": "workflow_restart_requested",
                        "issue": issue,
                        "actor": actor,
                        "new_attempt": correlation,
                        "previous_version": version,
                    }
                )
            )
            token = self._operator.set((issue, correlation))
            try:
                result = self.bus.send(
                    ReplanIssueCommand(
                        issue_number=issue,
                        reason=reason,
                        correlation_id=correlation,
                        payload={"recovery_restart": True, "actor": actor},
                    )
                )
            finally:
                self._operator.reset(token)
            return {
                "updated": True,
                "attempt": correlation,
                "planning_returned": result is not None,
                "recovery": self.inspect(issue),
            }

    def authorized_restart(self, issue: int, correlation: str) -> bool:
        return self._operator.get() == (issue, correlation) and self.requires_human(
            issue, correlation
        )

    def _retire(self, issue: int, version: str, reason: str, actor: str) -> None:
        records = self._records(issue)
        current = self._current(records)
        # Journal the intent before SCM writes. An interrupted retirement stays
        # fenced; repeat explicitly after reading the current operator status.
        retiring = self._write(
            "retiring", issue, version, actor=actor, reason_digest=text_digest(reason)
        )
        active = latest_active_plan(self.scm.get_comments(issue))
        if active:
            comment, contract = active
            revocation = PlanRevocation(
                schema_version=1,
                plan_comment_id=comment.id,
                contract_hash=contract.contract_hash,
                actor=actor,
                reason_digest=text_digest(reason),
                revoked_at=datetime.now(timezone.utc).isoformat(),
            )
            self.scm.post_comment(
                issue,
                "## Versuch ausdrücklich beendet\n\n"
                + html.escape(redact_secrets(reason))
                + "\n\n"
                + render_plan_revocation(revocation),
            )
            if latest_active_plan(self.scm.get_comments(issue)) is not None:
                raise ConfigurationConflict("Planwiderruf noch nicht bestätigt.")
        for checkpoint in self.store.list_checkpoints():
            if checkpoint.issue_number == issue and checkpoint.resume_eligible:
                self.bus.resume_coordinator.abandon(checkpoint.checkpoint_key, reason=reason)
        for clarification in self.store.list_planning_clarifications():
            if (
                clarification.issue_number == issue
                and clarification.repository == self.repository
                and clarification.status in {"waiting", "answered", "exhausted", "timed_out"}
            ):
                self.store.put_planning_clarification(
                    replace(
                        clarification,
                        status="superseded",
                        version=clarification.version + 1,
                        updated_at=datetime.now(timezone.utc),
                    ),
                    expected_version=clarification.version,
                )
        for label in (
            "ready-for-agent",
            "status:approved",
            "status:plan",
            "status:wip",
            "in-progress",
            "needs-review",
        ):
            self.scm.swap_label(issue, label, "")
        if {l.name for l in self.scm.get_issue(issue).labels} & {
            "ready-for-agent",
            "status:approved",
            "status:plan",
            "status:wip",
            "in-progress",
            "needs-review",
        }:
            raise ConfigurationConflict("Labelbereinigung noch nicht bestätigt.")
        self._write(
            "retired",
            issue,
            version,
            actor=actor,
            reason_digest=text_digest(reason),
            executions=[r.record_key for r in current],
            retirements=[r.record_key for r in records if r.kind.endswith(".retiring")]
            + [retiring.record_key],
        )
        self.session.complete_issue(issue)
        self.bus.publish(
            AuditEvent(
                payload={
                    "action": "workflow_attempt_retired",
                    "issue": issue,
                    "actor": actor,
                    "version": version,
                    "reason_digest": text_digest(reason),
                }
            )
        )
