from __future__ import annotations

import logging
import threading
from typing import Any

from samuel.core.acceptance import latest_active_plan
from samuel.core.bus import Bus
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import Event
from samuel.core.ports import IVersionControl
from samuel.core.workflow_outcome import (
    ABORTING_WORKFLOW_EVENTS,
    BLOCKING_WORKFLOW_EVENTS,
    REVOKING_WORKFLOW_EVENTS,
)

log = logging.getLogger(__name__)

TRANSITIONS: dict[str, tuple[str, str]] = {
    "IssueReady": ("", "ready-for-agent"),
    "PlanPosted": ("ready-for-agent", "status:plan"),
    # Keep the human approval label until candidate gates have consumed it.
    # The PR-gate authority reconstruction deliberately checks current SCM
    # state, so removing it synchronously here invalidates the approval before
    # CodeGenerated can be evaluated (#862).
    "PlanApproved": ("", "status:wip"),
    "CodeGenerated": ("ready-for-agent", "in-progress"),
    "PRCreated": ("in-progress", "needs-review"),
}

LABEL_BLOCKING_WORKFLOW_EVENTS = BLOCKING_WORKFLOW_EVENTS - {
    "PlanReplanRejected",
    "CandidateEvaluationFailed",
    "CandidateSubmissionRejected",
}

BLOCKED_EVENTS = frozenset(
    LABEL_BLOCKING_WORKFLOW_EVENTS
    | ABORTING_WORKFLOW_EVENTS
    | REVOKING_WORKFLOW_EVENTS
    | {"GateFailed"}  # visible stage failure; may still heal within the run
)
BLOCKED_LABELS_TO_REMOVE = (
    "ready-for-agent",
    "in-progress",
    "help wanted",
    "status:plan",
    "status:approved",
    "status:wip",
    "needs-review",
    "status:done",
)

STATUS_TRANSITIONS: dict[str, str] = {
    "CodeGenerated": "status:wip",
    "PRCreated": "status:wip",
}

EVENT_NAMES = set(TRANSITIONS) | set(STATUS_TRANSITIONS) | set(BLOCKED_EVENTS)
EVENT_NAMES.add("HealingAttemptStarted")
EVENT_NAMES.add("PRMerged")


class LabelsHandler:
    def __init__(self, bus: Bus, scm: IVersionControl | None = None) -> None:
        self._bus = bus
        self._scm = scm
        self._state_lock = threading.Lock()
        self._healing_attempts: dict[tuple[int, str], str] = {}

    def register(self) -> None:
        for event_name in EVENT_NAMES:
            self._bus.subscribe(event_name, self._on_event)

    def _on_event(self, event: Event) -> None:
        if self._scm is None:
            return
        issue = self._extract_issue(event)
        if issue is None:
            return

        if event.name == "IssueReady":
            try:
                if latest_active_plan(self._scm.get_comments(issue)) is not None:
                    return
            except Exception as exc:
                log.warning("Start label projection deferred (#%d, %s)", issue, type(exc).__name__)
                return

        if event.name in TRANSITIONS:
            remove, add = TRANSITIONS[event.name]
            self._safe_swap(issue, remove, add)

        if event.name in STATUS_TRANSITIONS:
            self._safe_swap(issue, "", STATUS_TRANSITIONS[event.name])

        if event.name == "PlanApproved":
            self._safe_swap(issue, "status:plan", "")
            self._safe_swap(issue, "status:failed", "")

        if event.name == "PlanPosted":
            self._safe_swap(issue, "status:failed", "")
            self._safe_swap(issue, "status:done", "")

        if event.name == "PRMerged":
            try:
                subject = EvaluationSubject.from_dict((event.payload or {})["evaluation_subject"])
                active = latest_active_plan(self._scm.get_comments(issue))
                if (
                    subject.repository == self._scm.repository_identity
                    and active is not None
                    and active[1].contract_hash == subject.contract_hash
                ):
                    for label in ("needs-review", "in-progress", "status:wip", "status:approved"):
                        self._safe_swap(issue, label, "")
                    self._safe_swap(issue, "", "status:done")
            except Exception as exc:
                log.warning("Merge label projection deferred (#%d, %s)", issue, type(exc).__name__)

        if event.name == "HealingAttemptStarted":
            self._remember_healing_attempt(issue, event)

        if event.name == "PRCreated":
            self._safe_swap(issue, "status:approved", "")
            self._complete_healing_attempt(issue, event)

        if event.name in BLOCKED_EVENTS:
            self._forget_healing_attempt(issue, event)
            for label in BLOCKED_LABELS_TO_REMOVE:
                self._safe_swap(issue, label, "")
            self._safe_swap(issue, "", "status:failed")

    def _remember_healing_attempt(self, issue: int, event: Event) -> None:
        key = self._run_key(issue, event)
        observation_key = str((event.payload or {}).get("observation_key", ""))
        if key is not None and observation_key:
            with self._state_lock:
                self._healing_attempts[key] = observation_key

    def _complete_healing_attempt(self, issue: int, event: Event) -> None:
        key = self._run_key(issue, event)
        if key is None:
            return
        observed_origin = str((event.payload or {}).get("healing_origin_observation_key", ""))
        with self._state_lock:
            expected_origin = self._healing_attempts.get(key)
            matched = bool(expected_origin) and observed_origin == expected_origin
            if matched:
                self._healing_attempts.pop(key, None)
        if matched:
            self._safe_swap(issue, "status:failed", "")

    def _forget_healing_attempt(self, issue: int, event: Event) -> None:
        key = self._run_key(issue, event)
        if key is not None:
            with self._state_lock:
                self._healing_attempts.pop(key, None)

    @staticmethod
    def _run_key(issue: int, event: Event) -> tuple[int, str] | None:
        correlation_id = str(event.correlation_id or "")
        return (issue, correlation_id) if correlation_id else None

    def _extract_issue(self, event: Event) -> int | None:
        payload: dict[str, Any] = event.payload or {}
        for key in ("issue", "issue_number"):
            val = payload.get(key)
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val.isdigit():
                return int(val)
        return None

    def _safe_swap(self, issue: int, remove: str, add: str) -> None:
        scm = self._scm
        if scm is None:
            return
        try:
            scm.swap_label(issue, remove, add)
        except Exception as exc:
            log.warning(
                "Label transition failed (#%d, remove=%r, add=%r): %s", issue, remove, add, exc
            )
