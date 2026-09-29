from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from samuel.core.acceptance import (
    AcceptanceApproval,
    clarification_evidence_failure,
    latest_active_plan,
    manual_receipts_for_subject,
    persist_plan_approval,
)
from samuel.core.bus import Bus
from samuel.core.commands import (
    Command,
    CreatePRCommand,
    ResumePendingCommand,
    ScanIssuesCommand,
)
from samuel.core.config import SUPPORTED_WATCH_MAX_PARALLEL
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import IssueReady, PlanApproved, WorkflowBlocked
from samuel.core.ports import IAuthorityStateStore, IConfig, IVersionControl
from samuel.core.state import StateStoreError
from samuel.core.types import Issue, canonical_scm_timestamp, scm_timestamp_at_or_after
from samuel.core.workflow_outcome import (
    TERMINAL_WORKFLOW_EVENTS,
    reduce_workflow_outcome,
)
from samuel.slices.watch.activity import SCMActivityPoller

log = logging.getLogger(__name__)

LABEL_PLAN = "status:plan"
LABEL_APPROVED = "status:approved"
LABEL_WIP = "status:wip"
LABEL_DONE = "status:done"
LABEL_FAILED = "status:failed"

VALID_TRANSITIONS: dict[str, set[str]] = {
    LABEL_PLAN: {LABEL_APPROVED, LABEL_DONE},
    LABEL_APPROVED: {LABEL_WIP, LABEL_DONE},
    LABEL_WIP: {LABEL_DONE},
    LABEL_FAILED: {LABEL_PLAN, LABEL_APPROVED},
}

STATUS_LABELS = (LABEL_FAILED, LABEL_PLAN, LABEL_APPROVED, LABEL_WIP, LABEL_DONE)
RISK_LABEL_LEVELS = {
    "risk:low": 1,
    "risk:medium": 2,
    "risk:high": 3,
    "risk:critical": 4,
}

_WATCH_OUTCOME_EVENTS = TERMINAL_WORKFLOW_EVENTS | {
    "PlanPosted",
    "ClarificationRequested",
    "ClarificationWaiting",
}


def _status_labels(issue: Issue) -> list[str]:
    return [l.name for l in issue.labels if l.name in STATUS_LABELS]


def _issue_risk(issue: Issue) -> tuple[int, str]:
    """Return the most conservative risk label; unlabeled issues default high."""

    levels = [
        (RISK_LABEL_LEVELS[label.name], label.name)
        for label in issue.labels
        if label.name in RISK_LABEL_LEVELS
    ]
    if not levels:
        return 3, "unlabeled_default_high"
    return max(levels)


class WatchHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config: IConfig | None = None,
        max_parallel: int = 1,
        max_risk: int = 3,
        workflow_name: str = "standard",
        authority_store: IAuthorityStateStore | None = None,
    ) -> None:
        if (
            isinstance(max_parallel, bool)
            or not isinstance(max_parallel, int)
            or max_parallel != SUPPORTED_WATCH_MAX_PARALLEL
        ):
            raise ValueError(
                f"WatchHandler max_parallel must be exactly {SUPPORTED_WATCH_MAX_PARALLEL}; "
                "the synchronous bus has no in-process parallel dispatcher"
            )
        self._bus = bus
        self._scm = scm
        self._config = config
        self._semaphore = threading.Semaphore(max_parallel)
        self._max_parallel = max_parallel
        self._max_risk = max(1, min(int(max_risk), 4))
        self._workflow_name = workflow_name
        self._authority = authority_store
        self._active: set[int] = set()
        self._lock = threading.Lock()
        self._dispatch_events: dict[tuple[str, int], list[tuple[str, dict[str, Any]]]] = {}
        for event_name in sorted(_WATCH_OUTCOME_EVENTS):
            self._bus.subscribe(event_name, self._record_dispatch_event)

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, ScanIssuesCommand)
        correlation_id = cmd.correlation_id or ""

        if self._config:
            try:
                self._config.reload()
                log.debug("Config hot-reloaded at cycle start")
            except Exception as exc:  # noqa: BLE001
                log.warning("Config reload failed, using cached config: %s", exc)

        resume_result: dict[str, Any] = {}
        if self._bus.has_handler("ResumePending"):
            result = self._bus.send(
                ResumePendingCommand(
                    payload={"source": "watch_cycle"},
                    correlation_id=correlation_id,
                )
            )
            if isinstance(result, dict):
                resume_result = result

        if not self._scm:
            log.warning("No SCM configured, watch cycle skipped")
            return {
                "dispatched": 0,
                "dispatched_failed": 0,
                "planned": 0,
                "approved": 0,
                "dispatch_outcomes": [],
                "label_fixes": 0,
                "activity_observed": 0,
                "activity_forwarded": 0,
                "activity_deduplicated": 0,
                "activity_poll": "no_scm",
                "risk_filtered": 0,
                "max_risk": self._max_risk,
                "workflow": self._workflow_name,
                "resume": resume_result,
            }

        activity_result = self._poll_scm_activity(correlation_id)

        ready_issues = self._scm.list_issues(labels=["ready-for-agent"])
        issues_with_risk = [(issue, *_issue_risk(issue)) for issue in ready_issues]
        issues_to_plan = [
            (issue, risk, source)
            for issue, risk, source in issues_with_risk
            if risk <= self._max_risk
        ]
        risk_filtered = len(ready_issues) - len(issues_to_plan)
        if risk_filtered:
            log.warning(
                "Workflow '%s' skipped %d ready issue(s) above max_risk=%d",
                self._workflow_name,
                risk_filtered,
                self._max_risk,
            )
        approval_candidates = self._scm.list_issues(labels=[LABEL_APPROVED])
        # A bare approved label is not evidence that the generated plan was
        # ever visible.  Capture valid plan -> approved transitions before the
        # consistency pass removes the older status label.
        issues_to_approve = [
            issue for issue in approval_candidates if LABEL_PLAN in _status_labels(issue)
        ]
        ignored_approvals = len(approval_candidates) - len(issues_to_approve)
        label_fixes = self._check_label_consistency()

        dispatched = 0
        dispatched_failed = 0
        planned = 0
        approved = 0
        dispatch_outcomes: list[dict[str, Any]] = []
        for issue, risk, risk_source in issues_to_plan:
            if not self._try_acquire(issue.number):
                log.debug("Semaphore full, skipping issue #%d", issue.number)
                continue

            try:
                dispatch_key = self._begin_dispatch(correlation_id, issue.number)
                self._bus.publish(
                    IssueReady(
                        payload={
                            "issue": issue.number,
                            "title": issue.title,
                            "risk": risk,
                            "risk_source": risk_source,
                            "workflow": self._workflow_name,
                        },
                        correlation_id=correlation_id,
                    )
                )
                # WorkflowEngine reagiert auf IssueReady und dispatcht PlanIssue.
                # Kein direkter PlanIssueCommand-Send — verhindert Doppel-Dispatch.
                dispatched += 1
                outcome = self._finish_dispatch(dispatch_key, phase="planning")
                dispatch_outcomes.append(outcome)
                if outcome["status"] == "planned":
                    planned += 1
                elif outcome["status"] != "waiting":
                    dispatched_failed += 1
            finally:
                self._discard_dispatch(correlation_id, issue.number)
                self._release(issue.number)

        for issue in issues_to_approve:
            if not self._try_acquire(issue.number):
                continue
            try:
                approval: dict[str, Any] | None = None
                acceptance_contract: dict[str, object] | None = None
                try:
                    comments = self._scm.get_comments(issue.number)
                    active = latest_active_plan(comments)
                    if active is None:
                        raise ValueError("no active plan")
                    plan, contract = active
                    clarification_failure = clarification_evidence_failure(
                        contract, issue, comments
                    )
                    if clarification_failure is not None:
                        raise ValueError(clarification_failure)
                    if contract.clarification_basis is not None:
                        source = contract.source_snapshot
                        if (
                            source is None
                            or source.repository != self._scm.repository_identity
                            or self._scm.resolve_ref(source.base_ref) != source.base_sha
                        ):
                            raise ValueError("clarification_source_changed")
                    plan_created_at = canonical_scm_timestamp(plan.created_at)
                    approval_event = next(
                        event
                        for event in reversed(
                            self._scm.get_label_events(issue.number, LABEL_APPROVED)
                        )
                        if event.actor
                        and event.actor_type == "human"
                        and event.timestamp
                        and plan_created_at
                        and scm_timestamp_at_or_after(event.timestamp, plan_created_at)
                    )
                    acceptance_contract = contract.as_dict()
                    approval = AcceptanceApproval(
                        state="approved",
                        actor=approval_event.actor,
                        method="status:approved/polling",
                        source_id=f"plan:{plan.id};{approval_event.source_id}",
                        approved_at=approval_event.timestamp,
                        contract_hash=contract.contract_hash,
                        plan_comment_id=plan.id,
                    ).as_dict()
                except (OSError, StopIteration, ValueError) as exc:
                    if str(exc).startswith("clarification_"):
                        self._bus.publish(
                            WorkflowBlocked(
                                payload={
                                    "issue": issue.number,
                                    "stage": "approval",
                                    "reason": str(exc),
                                },
                                correlation_id=correlation_id,
                            )
                        )
                    ignored_approvals += 1
                    continue
                budget_admission_key = ""
                approval_authority_key = ""
                if (
                    self._authority is None
                    or not callable(getattr(self._authority, "put_authority_record", None))
                    or not callable(getattr(self._authority, "get_authority_record", None))
                ):
                    dispatch_key = self._begin_dispatch(correlation_id, issue.number)
                    self._bus.publish(
                        WorkflowBlocked(
                            payload={
                                "issue": issue.number,
                                "reason": "plan_approval_authority_store_missing",
                            },
                            correlation_id=correlation_id,
                        )
                    )
                    dispatched += 1
                    dispatched_failed += 1
                    dispatch_outcomes.append(self._finish_dispatch(dispatch_key, phase="approval"))
                    continue
                if self._authority is not None:
                    assert acceptance_contract is not None
                    contract_hash = str(acceptance_contract.get("contract_hash") or "")
                    try:
                        repository = self._scm.repository_identity
                        admission = self._authority.find_budget_admission(
                            repository=repository,
                            issue_number=issue.number,
                            plan_contract_hash=contract_hash,
                            plan_comment_id=plan.id,
                        )
                    except Exception as exc:  # approval remains fail-closed and observable
                        self._bus.publish(
                            WorkflowBlocked(
                                payload={
                                    "issue": issue.number,
                                    "reason": "workflow_budget_admission_lookup_failed",
                                    "error_type": type(exc).__name__,
                                },
                                correlation_id=correlation_id,
                            )
                        )
                        admission = None
                    if admission is None:
                        dispatch_key = self._begin_dispatch(correlation_id, issue.number)
                        self._bus.publish(
                            WorkflowBlocked(
                                payload={
                                    "issue": issue.number,
                                    "reason": "workflow_budget_admission_missing",
                                },
                                correlation_id=correlation_id,
                            )
                        )
                        dispatched += 1
                        dispatched_failed += 1
                        dispatch_outcomes.append(
                            self._finish_dispatch(dispatch_key, phase="approval")
                        )
                        continue
                    budget_admission_key = admission.admission_key
                    if callable(getattr(self._authority, "put_authority_record", None)):
                        assert approval is not None
                        try:
                            approval_record = persist_plan_approval(
                                self._authority,
                                repository=repository,
                                issue_number=issue.number,
                                contract=contract,
                                approval=AcceptanceApproval.from_dict(approval),
                                transport="authenticated_scm_polling",
                            )
                            approval_authority_key = approval_record.record_key
                            approval = AcceptanceApproval.from_dict(
                                approval_record.payload["approval"]
                            ).as_dict()
                        except (StateStoreError, ValueError) as exc:
                            dispatch_key = self._begin_dispatch(correlation_id, issue.number)
                            self._bus.publish(
                                WorkflowBlocked(
                                    payload={
                                        "issue": issue.number,
                                        "reason": getattr(
                                            exc,
                                            "code",
                                            "plan_approval_authority_persist_failed",
                                        ),
                                    },
                                    correlation_id=correlation_id,
                                )
                            )
                            dispatched += 1
                            dispatched_failed += 1
                            dispatch_outcomes.append(
                                self._finish_dispatch(dispatch_key, phase="approval")
                            )
                            continue
                dispatch_key = self._begin_dispatch(correlation_id, issue.number)
                self._bus.publish(
                    PlanApproved(
                        payload={
                            "issue": issue.number,
                            "title": issue.title,
                            "source": "polling",
                            "approval_method": "status:approved",
                            **({"acceptance_approval": approval} if approval else {}),
                            **(
                                {"acceptance_contract": acceptance_contract}
                                if acceptance_contract
                                else {}
                            ),
                            **(
                                {"budget_admission_key": budget_admission_key}
                                if budget_admission_key
                                else {}
                            ),
                            **(
                                {"plan_approval_authority_key": approval_authority_key}
                                if approval_authority_key
                                else {}
                            ),
                        },
                        correlation_id=correlation_id,
                    )
                )
                dispatched += 1
                outcome = self._finish_dispatch(dispatch_key, phase="approval")
                dispatch_outcomes.append(outcome)
                if outcome["status"] == "approved":
                    approved += 1
                else:
                    dispatched_failed += 1
            finally:
                self._discard_dispatch(correlation_id, issue.number)
                self._release(issue.number)

        manual_outcomes = self._reevaluate_manual_pending()
        dispatched += len(manual_outcomes)
        dispatched_failed += sum(1 for outcome in manual_outcomes if outcome["status"] == "blocked")
        dispatch_outcomes.extend(manual_outcomes)

        return {
            "dispatched": dispatched,
            "dispatched_failed": dispatched_failed,
            "planned": planned,
            "approved": approved,
            "manual_reevaluated": sum(
                1 for outcome in manual_outcomes if outcome["status"] == "approved"
            ),
            "dispatch_outcomes": dispatch_outcomes,
            "ignored_approvals": ignored_approvals,
            "risk_filtered": risk_filtered,
            "max_risk": self._max_risk,
            "workflow": self._workflow_name,
            "label_fixes": label_fixes,
            "resume": resume_result,
            **activity_result,
        }

    def _reevaluate_manual_pending(self) -> list[dict[str, Any]]:
        """Continue exact waiting candidates only after native SCM human receipts exist."""

        if (
            self._authority is None
            or self._scm is None
            or not callable(getattr(self._authority, "list_checkpoints", None))
        ):
            return []
        outcomes: list[dict[str, Any]] = []
        for checkpoint in self._authority.list_checkpoints(resume_eligible=True):
            if checkpoint.boundary != "manual_pending":
                continue
            issue_number = checkpoint.issue_number
            if not self._try_acquire(issue_number):
                continue
            try:
                comments = self._scm.get_comments(issue_number)
                active = latest_active_plan(comments)
                if active is None:
                    continue
                plan_comment, contract = active
                event_payload = checkpoint.payload.get("event_payload")
                raw_subject = (
                    event_payload.get("evaluation_subject")
                    if isinstance(event_payload, dict)
                    else None
                )
                if not isinstance(raw_subject, dict):
                    continue
                subject = EvaluationSubject.from_dict(raw_subject)
                if (
                    checkpoint.repository != subject.repository
                    or checkpoint.repository != self._scm.repository_identity
                    or checkpoint.head_sha != subject.head_sha
                    or contract.contract_hash != subject.contract_hash
                ):
                    continue
                required_manual = {
                    criterion.criterion_id
                    for criterion in contract.criteria
                    if criterion.required and criterion.mode == "manual"
                }
                if not required_manual:
                    continue
                receipts = manual_receipts_for_subject(
                    comments,
                    plan_comment,
                    contract,
                    subject,
                    after=checkpoint.updated_at.isoformat(),
                )
                if not required_manual <= receipts.keys():
                    continue
                dispatch_key = self._begin_dispatch(checkpoint.correlation_id, issue_number)
                result = self._bus.send(
                    CreatePRCommand(
                        issue_number=issue_number,
                        branch=checkpoint.branch,
                        base=checkpoint.base_ref,
                        subject=subject,
                        payload={
                            "workspace_id": checkpoint.workspace_id,
                            "manual_reevaluation": True,
                        },
                        correlation_id=checkpoint.correlation_id,
                    )
                )
                outcome = self._finish_dispatch(dispatch_key, phase="manual_acceptance")
                if isinstance(result, dict) and result.get("manual_pending"):
                    outcome["status"] = "waiting"
                outcomes.append(outcome)
            except (OSError, ValueError, StateStoreError) as exc:
                log.warning("MANUAL reevaluation deferred for #%d: %s", issue_number, exc)
            finally:
                self._discard_dispatch(checkpoint.correlation_id, issue_number)
                self._release(issue_number)
        return outcomes

    def _begin_dispatch(self, correlation_id: str, issue_number: int) -> tuple[str, int]:
        key = (correlation_id, issue_number)
        with self._lock:
            self._dispatch_events[key] = []
        return key

    def _discard_dispatch(self, correlation_id: str, issue_number: int) -> None:
        with self._lock:
            self._dispatch_events.pop((correlation_id, issue_number), None)

    def _record_dispatch_event(self, event: Any) -> None:
        correlation_id = str(getattr(event, "correlation_id", "") or "")
        payload = getattr(event, "payload", {})
        if not isinstance(payload, dict):
            payload = {}
        event_issue = payload.get("issue")
        with self._lock:
            for (active_correlation, active_issue), facts in self._dispatch_events.items():
                if active_correlation != correlation_id:
                    continue
                if event_issue is not None and str(event_issue) != str(active_issue):
                    continue
                facts.append((str(event.name), dict(payload)))

    def _finish_dispatch(self, key: tuple[str, int], *, phase: str) -> dict[str, Any]:
        with self._lock:
            facts = list(self._dispatch_events.pop(key, []))

        outcome = reduce_workflow_outcome(facts)
        terminal_event = outcome.terminal_event
        status: str
        if outcome.status in {"blocked", "aborted"}:
            status = outcome.status
        elif phase == "planning" and any(name == "PlanPosted" for name, _ in facts):
            status = "planned"
        elif phase == "planning" and any(
            name in {"ClarificationRequested", "ClarificationWaiting"} for name, _ in facts
        ):
            status = "waiting"
        elif phase in {"approval", "manual_acceptance"} and outcome.status in {
            "pr_created",
            "reviewed",
            "merged",
        }:
            status = "approved"
        else:
            status = "failed"

        result: dict[str, Any] = {
            "issue": key[1],
            "correlation_id": key[0],
            "phase": phase,
            "status": status,
            "terminal_event": terminal_event,
        }
        if status == "failed":
            result["reason"] = "no_terminal_outcome"
        return result

    def _poll_scm_activity(self, correlation_id: str) -> dict[str, Any]:
        if not self._config or not self._config.feature_flag("scm_activity_polling"):
            return {
                "activity_observed": 0,
                "activity_forwarded": 0,
                "activity_deduplicated": 0,
                "activity_poll": "disabled",
            }
        scm = self._scm
        if scm is None:
            return {
                "activity_observed": 0,
                "activity_forwarded": 0,
                "activity_deduplicated": 0,
                "activity_poll": "no_scm",
            }
        if "activity_polling" not in scm.capabilities:
            log.warning("SCM activity polling enabled but adapter does not support it")
            return {
                "activity_observed": 0,
                "activity_forwarded": 0,
                "activity_deduplicated": 0,
                "activity_poll": "unsupported",
            }

        data_dir = Path(str(self._config.get("agent.data_dir", "data")))
        poller = SCMActivityPoller(
            self._bus,
            scm,
            data_dir / "scm_activity_poll.json",
            initial_days=int(self._config.get("agent.auto.activity_initial_days", 7)),
            overlap_seconds=int(self._config.get("agent.auto.activity_overlap_seconds", 60)),
            interval_seconds=int(self._config.get("agent.auto.activity_poll_interval", 60)),
            limit=int(self._config.get("agent.auto.activity_limit", 250)),
        )
        try:
            return poller.poll(correlation_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("SCM activity polling failed: %s", exc)
            return {
                "activity_observed": 0,
                "activity_forwarded": 0,
                "activity_deduplicated": 0,
                "activity_poll": "failed",
                "activity_error": str(exc),
            }

    def _try_acquire(self, issue_number: int) -> bool:
        with self._lock:
            if issue_number in self._active:
                return False
        acquired = self._semaphore.acquire(blocking=False)
        if acquired:
            with self._lock:
                self._active.add(issue_number)
        return acquired

    def _release(self, issue_number: int) -> None:
        with self._lock:
            self._active.discard(issue_number)
        self._semaphore.release()

    def _check_label_consistency(self) -> int:
        scm = self._scm
        if scm is None:
            return 0
        fixes = 0
        for label in [LABEL_PLAN, LABEL_APPROVED, LABEL_WIP, LABEL_FAILED]:
            try:
                issues = scm.list_issues(labels=[label])
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to list issues for label %s: %s", label, exc)
                continue

            for issue in issues:
                status_list = _status_labels(issue)
                if len(status_list) > 1:
                    keep = max(status_list, key=STATUS_LABELS.index)
                    for extra in status_list:
                        if extra != keep:
                            try:
                                scm.swap_label(issue.number, extra, keep)
                                fixes += 1
                                log.info(
                                    "Label fix: issue #%d removed %s (kept %s)",
                                    issue.number,
                                    extra,
                                    keep,
                                )
                            except Exception as exc:  # noqa: BLE001
                                log.warning(
                                    "Failed to fix label on issue #%d: %s",
                                    issue.number,
                                    exc,
                                )
        return fixes
