"""Durable, exclusive configuration sessions and workflow admission.

The authority store's compare-and-swap is the shared linearization point. No
lease timeout grants permission to resume work or discard an interrupted edit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Protocol
from uuid import uuid4

from samuel.core.commands import Command
from samuel.core.events import Event
from samuel.core.ports import IAuthorityStateStore
from samuel.core.state import StateStoreConflict

log = logging.getLogger(__name__)


class ConfigurationConflict(RuntimeError):
    """Retryable admission/CAS conflict; must not be deduplicated as success."""


class ConfigurationArea(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def validate(self, draft: dict[str, Any]) -> dict[str, Any]: ...
    def prepare(self, draft: dict[str, Any]) -> Any: ...
    def persist(self, draft: dict[str, Any]) -> None: ...
    def activate(self, prepared: Any) -> None: ...


# These messages can enter a workflow outside an existing synchronous dispatch.
WORK_COMMANDS = frozenset(
    {
        "ScanIssues",
        "PlanIssue",
        "ReplanIssue",
        "Implement",
        "CreatePR",
        "SubmitCandidate",
        "RequestCandidateVerification",
        "Score",
        "Evaluate",
        "Heal",
        "Review",
        "ResumePending",
        "RunQuality",
        "VerifyAC",
        "BuildContext",
        "Changelog",
    }
)
WORK_EVENTS = frozenset(
    {
        "IssueReady",
        "IssueCommented",
        "PlanApproved",
        "PlanValidated",
        "PullRequestOpened",
        "PullRequestUpdated",
        "PullRequestMerged",
        "CheckRunCompleted",
        "WorkflowRunCompleted",
    }
)
WAIT_EVENTS = frozenset(
    {
        "PlanPosted",
        "ClarificationRequested",
        "ClarificationWaiting",
        "WorkflowBlocked",
        "ReviewBlocked",
        "MergeOutcomeUnknown",
        "PRCreationFailed",
        "ManualInputRequired",
        "ACManualPending",
        "GateEvaluationCompleted",
        "EvaluationSubjectInvalidated",
        "ProviderVerificationBlocked",
    }
)
FINISH_EVENTS = frozenset(
    {"ReviewCompleted", "PRMerged", "CandidateEvaluationCompleted", "WorkflowAborted"}
)


def exclusive(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def locked(self: ConfigurationSession, *args: Any, **kwargs: Any) -> Any:
        try:
            with self.store.configuration_lock():
                return method(self, *args, **kwargs)
        except StateStoreConflict as exc:
            raise ConfigurationConflict("Konfigurationsaktion läuft; erneut versuchen.") from exc

    return locked


class ConfigurationSession:
    def __init__(self, store: IAuthorityStateStore) -> None:
        self.store = store
        self.areas: dict[str, ConfigurationArea] = {}
        self.work_events = set(WORK_EVENTS) | {"GateEvaluationCompleted"}
        self.refresh: Callable[[int], None] = lambda revision: None
        self.external_blockers: Callable[[], list[str]] = lambda: []
        self.audit: Callable[[dict[str, Any]], None] = lambda payload: None
        self._inside: ContextVar[bool] = ContextVar(
            f"configuration_dispatch_{id(self)}", default=False
        )

    def state(self) -> dict[str, Any]:
        return self.store.configuration_state() or {
            "version": 0,
            "revision": 0,
            "phase": "idle",
            "active": {},
            "issues": {},
        }

    def _save(self, state: dict[str, Any]) -> dict[str, Any]:
        version = state["version"]
        state["version"] += 1
        try:
            self.store.compare_configuration_state(state, version=version)
        except StateStoreConflict as exc:
            raise ConfigurationConflict("Zustand geändert; Ansicht neu laden.") from exc
        return state

    def _update(self, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        for _ in range(100):
            state = self.state()
            mutate(state)
            try:
                return self._save(state)
            except ConfigurationConflict:
                continue
        raise ConfigurationConflict("Zustandsdienst ist belegt; erneut versuchen.")

    def _audit(self, action: str, state: dict[str, Any], actor: str) -> None:
        self.audit(
            {
                "action": action,
                "actor": actor,
                "change_id": state.get("change_id"),
                "area": state.get("area"),
                "version": state["version"],
                "revision": state["revision"],
                "phase": state["phase"],
                "probes": [
                    {key: probe[key] for key in ("task", "valid", "scope", "at", "draft_version")}
                    for probe in state.get("probes", [])
                ],
                "changed_tasks": sorted(
                    task
                    for task, cfg in state.get("draft", {})
                    .get("llm/defaults.json", {})
                    .get("tasks", {})
                    .items()
                    if cfg
                    != state.get("before", {})
                    .get("llm/defaults.json", {})
                    .get("tasks", {})
                    .get(task)
                ),
            }
        )

    def blockers(self, state: dict[str, Any]) -> list[str]:
        reasons = [f"Ausführung {key}" for key in state["active"]]
        reasons += [f"Issue #{key}: {value}" for key, value in state["issues"].items()]
        if self.store.authority_status().get("reconcile_required"):
            reasons.append("Autoritätszustand muss abgeglichen werden")
        reasons += [
            f"Fortsetzbarer Workflow #{row.issue_number}"
            for row in self.store.list_checkpoints(resume_eligible=True)
        ]
        reasons += [
            f"Ungeklärter Vorgang: {row.operation}"
            for row in self.store.list_intents()
            if row.status not in {"applied", "failed"}
        ]
        reasons += [
            f"Klärung #{row.issue_number}"
            for row in self.store.list_planning_clarifications()
            if row.status in {"waiting", "answered", "exhausted", "timed_out"}
        ]
        reasons += [
            "Ungeklärter LLM-Budgetversuch"
            for row in self.store.list_budget_attempts()
            if row.status == "reserved"
        ]
        reasons += [
            f"Healing #{row.issue_number}"
            for row in self.store.list_healing_claims()
            if row.status == "claimed"
        ]
        return reasons + self.external_blockers()

    @exclusive
    def enter(self, area: str, actor: str) -> dict[str, Any]:
        if area not in self.areas:
            raise ValueError("Unbekannter Konfigurationsbereich")
        state = self.state()
        if state["phase"] != "idle":
            raise ConfigurationConflict("Konfigurationsmodus ist bereits aktiv.")
        reasons = self.blockers(state)
        if reasons:
            raise ConfigurationConflict("; ".join(reasons))
        # Snapshot is only accepted if admission state has not changed while reading.
        before = self.areas[area].snapshot()
        state.update(
            phase="editing",
            area=area,
            owner=actor,
            change_id=str(uuid4()),
            before=before,
            draft=deepcopy(before),
            probes=[],
            preview=None,
        )
        state["preview"] = self.areas[area].validate(before)
        self._save(state)
        self._audit("enter", state, actor)
        return state

    def owned(self, actor: str, version: int, *, recovery: bool = False) -> dict[str, Any]:
        state = self.state()
        if state["phase"] == "idle" or state["version"] != version:
            raise ConfigurationConflict("Konfiguration geändert; Ansicht neu laden.")
        if not recovery and state.get("owner") != actor:
            raise ConfigurationConflict(
                "Konfiguration wird von einem anderen Administrator bearbeitet."
            )
        if state["phase"] not in {"editing", "failed"} and not recovery:
            raise ConfigurationConflict("Unterbrochener Vorgang muss wiederhergestellt werden.")
        return state

    @exclusive
    def stage(self, actor: str, version: int, draft: dict[str, Any]) -> dict[str, Any]:
        state = self.owned(actor, version)
        if state["phase"] != "editing":
            raise ConfigurationConflict("Zuerst den vorherigen Stand wiederherstellen.")
        preview = self.areas[state["area"]].validate(draft)
        probes = state["probes"] if draft == state["draft"] else []
        state.update(draft=deepcopy(draft), preview=preview, probes=probes)
        self._save(state)
        self._audit("stage", state, actor)
        return state

    @exclusive
    def probe(
        self, actor: str, version: int, task: str, test: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        state = self.owned(actor, version)
        # Claim prevents apply/recovery from racing a provider probe.
        state["phase"] = "probing"
        self._save(state)
        try:
            result = test(state["draft"])
            valid = result.get("valid") is True
        except Exception:
            log.warning("Configuration provider probe failed; result recorded as failed")
            valid = False
        evidence = {
            "task": task,
            "valid": valid,
            "scope": "provider.validate; kein Nachweis einer Modellantwort",
            "at": datetime.now(timezone.utc).isoformat(),
            "draft_version": version,
        }
        state["probes"] = [row for row in state["probes"] if row["task"] != task] + [evidence]
        state["phase"] = "editing"
        self._save(state)
        self._audit("probe_pass" if valid else "probe_fail", state, actor)
        return state

    @exclusive
    def apply(
        self, actor: str, version: int, *, override_failed_probe: bool = False
    ) -> dict[str, Any]:
        state = self.owned(actor, version)
        if state["phase"] != "editing":
            raise ConfigurationConflict("Zuerst den vorherigen Stand wiederherstellen.")
        if any(not row["valid"] for row in state["probes"]) and not override_failed_probe:
            raise ValueError("Fehlgeschlagenen Verbindungstest ausdrücklich bestätigen.")
        area = self.areas[state["area"]]
        if area.snapshot() != state["before"]:
            raise ConfigurationConflict("Dateien wurden außerhalb des Dashboards geändert.")
        preview = area.validate(state["draft"])
        previous = state.get("preview") or {}
        if preview.get("binding", preview) != previous.get("binding", previous):
            state["preview"] = preview
            self._save(state)
            raise ConfigurationConflict("Vorschau aktualisiert; prüfen und erneut übernehmen.")
        state["phase"] = "applying"
        self._save(state)  # Write-ahead journal, including original and intended documents.
        self._audit("apply_override" if override_failed_probe else "apply", state, actor)
        try:
            prepared = area.prepare(state["draft"])
            area.persist(state["draft"])
            area.activate(prepared)
            state["revision"] += 1
            return self._finish(state, actor, "applied")
        except Exception:
            state["phase"] = "failed"
            self._save(state)
            self._audit("apply_failed", state, actor)
            raise

    @exclusive
    def cancel(self, actor: str, version: int, *, recovery: bool = False) -> dict[str, Any]:
        state = self.owned(actor, version, recovery=recovery)
        # Explicit recovery is allowed after process/browser loss, never on a timer.
        area = self.areas[state["area"]]
        state["phase"] = "restoring"
        self._save(state)
        try:
            prepared = area.prepare(state["before"])
            try:
                unchanged = area.snapshot() == state["before"]
            except (OSError, ValueError):
                unchanged = False
            if not unchanged:
                area.persist(state["before"])
            area.activate(prepared)
            state["revision"] += 1
            return self._finish(state, actor, "restored" if recovery else "cancelled")
        except Exception:
            state["phase"] = "failed"
            self._save(state)
            self._audit("restore_failed", state, actor)
            raise

    def _finish(self, state: dict[str, Any], actor: str, action: str) -> dict[str, Any]:
        state["phase"] = "idle"
        self._audit(action, state, actor)
        for key in ("before", "draft", "preview", "probes", "owner", "area", "change_id"):
            state.pop(key, None)
        return self._save(state)

    @exclusive
    def reconcile_dispatch(self, actor: str) -> dict[str, Any]:
        # OS lock proves no live process is dispatching. Durable waiting issues
        # and uncertain external intents are deliberately not cleared here.
        with self.store.configuration_lock(work=True):

            def reconcile(state: dict[str, Any]) -> None:
                if state["phase"] != "idle":
                    raise ConfigurationConflict("Zuerst Konfiguration wiederherstellen.")
                state["active"] = {}

            state = self._update(reconcile)
            self._audit("dispatch_reconciled", state, actor)
            return state

    @contextmanager
    def operator_action(self) -> Iterator[None]:
        """Serialize explicit lifecycle actions against dispatch and config edits."""
        try:
            with self.store.configuration_lock(), self.store.configuration_lock(work=True):
                state = self.state()
                if state["phase"] != "idle" or state["active"]:
                    raise ConfigurationConflict("Betrieb ist aktiv oder muss abgeglichen werden.")
                if self.store.authority_status().get("reconcile_required"):
                    raise ConfigurationConflict("Autoritätszustand muss abgeglichen werden.")
                token = self._inside.set(True)
                try:
                    yield
                finally:
                    self._inside.reset(token)
        except StateStoreConflict as exc:
            raise ConfigurationConflict("Betrieb oder Konfigurationsaktion läuft.") from exc

    def complete_issue(self, issue: int) -> None:
        if not self._inside.get():
            raise ConfigurationConflict("Exklusive Lifecycleaktion erforderlich.")
        self._update(lambda state: state["issues"].pop(str(issue), None))

    @contextmanager
    def admission(self, name: str = "work") -> Iterator[None]:
        if self._inside.get():
            yield
            return
        try:
            with self.store.configuration_lock(work=True, shared=True), self._admission(name):
                yield
        except StateStoreConflict as exc:
            raise ConfigurationConflict("Ausführungsstatus wird abgeglichen.") from exc

    @contextmanager
    def _admission(self, name: str = "work") -> Iterator[None]:
        if self._inside.get():
            yield
            return
        if self.store.authority_status().get("reconcile_required"):
            raise ConfigurationConflict(
                "Autoritätszustand muss vor neuer Arbeit abgeglichen werden."
            )
        key = str(uuid4())

        def start(state: dict[str, Any]) -> None:
            if state["phase"] != "idle":
                raise ConfigurationConflict("Konfigurationsmodus aktiv; Arbeit bleibt ausstehend.")
            state["active"][key] = name

        state = self._update(start)
        token = self._inside.set(True)
        try:
            self.refresh(state["revision"])
            yield
        finally:
            self._inside.reset(token)
            self._update(lambda current: current["active"].pop(key, None))

    def dispatch(self, msg: Event | Command, next_: Callable[[], Any]) -> Any:
        guarded = (
            isinstance(msg, Command) and msg.name in WORK_COMMANDS
        ) or msg.name in self.work_events
        if guarded and not self._inside.get():
            with self.admission(msg.name):
                return self.dispatch(msg, next_)
        issue = (
            getattr(msg, "issue_number", 0)
            or msg.payload.get("issue")
            or msg.payload.get("issue_number")
        )
        persistent_commands = {
            "PlanIssue",
            "ReplanIssue",
            "Implement",
            "CreatePR",
            "SubmitCandidate",
            "RequestCandidateVerification",
            "Review",
            "Heal",
            "Evaluate",
        }
        tracked = (
            isinstance(msg, Command) and msg.name in persistent_commands
        ) or msg.name in WAIT_EVENTS | FINISH_EVENTS | {"PRCreated"}
        if self._inside.get() and isinstance(issue, int) and issue > 0 and tracked:

            def record(state: dict[str, Any]) -> None:
                key = str(issue)
                if (
                    isinstance(msg, Command)
                    and msg.name in WORK_COMMANDS
                    or msg.name in WAIT_EVENTS
                ):
                    state["issues"][key] = msg.name
                elif msg.name in FINISH_EVENTS or (
                    msg.name == "PRCreated" and msg.payload.get("review_required") is not True
                ):
                    state["issues"].pop(key, None)

            self._update(record)
        return next_()
