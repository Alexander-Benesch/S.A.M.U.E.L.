"""Durable, exclusive configuration sessions and workflow admission.

The authority store's compare-and-swap is the shared linearization point. No
lease timeout grants permission to resume work or discard an interrupted edit.
"""

from __future__ import annotations

import logging
import re
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
from samuel.core.state import ManagedBackupRecord, StateStoreConflict

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
        self.prompt_start_allowed: Callable[[int, str], bool] = lambda issue, correlation: (
            not (
                any(row.issue_number == issue for row in self.store.list_checkpoints())
                or any(
                    row.payload.get("issue_number", row.payload.get("issue")) == issue
                    for row in self.store.list_authority_records()
                )
            )
        )
        self.prompt_manifest: Callable[[], dict[str, Any]] = lambda: {}
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
                "prompt_bindings": state.get("prompt_bindings", {}),
                "version": state["version"],
                "revision": state["revision"],
                "phase": state["phase"],
                **(
                    {"maintenance": deepcopy(state["maintenance"])}
                    if "maintenance" in state
                    else {}
                ),
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

    def blockers(self, state: dict[str, Any], *, include_external: bool = True) -> list[str]:
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
        return reasons + (self.external_blockers() if include_external else [])

    @exclusive
    def enter(self, area: str, actor: str) -> dict[str, Any]:
        if area not in self.areas:
            raise ValueError("Unbekannter Konfigurationsbereich")
        state = self.state()
        if state["phase"] != "idle" and not self._maintenance_setup(state):
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
        if state["phase"] in {"idle", "maintenance"} or state["version"] != version:
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
        state["phase"] = "maintenance" if state.get("maintenance") else "idle"
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
                if state["phase"] != "idle" or state.get("maintenance"):
                    raise ConfigurationConflict("Zuerst Konfiguration wiederherstellen.")
                state["active"] = {}

            state = self._update(reconcile)
            self._audit("dispatch_reconciled", state, actor)
            return state

    @contextmanager
    def configuration_write(self, *, setup: bool = False) -> Iterator[None]:
        """Fence setup writes without granting nested workflow admission."""
        try:
            with self.store.configuration_lock(), self.store.configuration_lock(work=True):
                state = self.state()
                allowed = (state["phase"] == "idle" and not state.get("maintenance")) or (
                    setup and self._maintenance_setup(state)
                )
                if not allowed or state["active"]:
                    raise ConfigurationConflict("Betrieb ist aktiv oder muss abgeglichen werden.")
                if self.store.authority_status().get("reconcile_required"):
                    raise ConfigurationConflict("Autoritätszustand muss abgeglichen werden.")
                yield
        except StateStoreConflict as exc:
            raise ConfigurationConflict("Betrieb oder Konfigurationsaktion läuft.") from exc

    @staticmethod
    def _maintenance_setup(state: dict[str, Any]) -> bool:
        return bool(
            state["phase"] == "maintenance" and state.get("maintenance", {}).get("step") == "setup"
        )

    def setup_writes_allowed(self) -> bool:
        state = self.state()
        return (
            state["phase"] == "idle" and not state.get("maintenance")
        ) or self._maintenance_setup(state)

    @contextmanager
    def host_transition(
        self,
        target: str,
        actor: str,
        reason: str,
        binding: str,
        *,
        before_transition: Callable[[], ManagedBackupRecord | None] | None = None,
        require_pending: bool = False,
    ) -> Iterator[Callable[[], dict[str, Any]]]:
        """Hold existing OS fences across an operator's stop/start sequence.

        Only explicit completion releases production admission. Process loss
        releases the OS locks but leaves the durable transition pending. The
        same bound operator path can retry without discarding workflow state.
        A fixed internal preparation may capture the idle state under both
        fences before persisting maintenance; it is never repeated on a retry.
        Its managed backup reference is persisted with the pending transition,
        before audit/output, and retained on the same bound retry. The reference
        does not verify an archive or authorize restoration.
        """
        if (
            target not in {"setup", "production", "stopped"}
            or not actor.strip()
            or not reason.strip()
        ):
            raise ValueError("Zielmodus, Operator und Begründung erforderlich.")
        if re.fullmatch(r"[0-9a-f]{64}", binding) is None:
            raise ValueError("Geprüfte Installationsbindung erforderlich.")
        try:
            with self.store.configuration_lock(), self.store.configuration_lock(work=True):
                state = self.state()
                previous = state.get("maintenance", {})
                if require_pending and (
                    state["phase"] != "maintenance"
                    or previous.get("step") != "pending"
                    or previous.get("target") != target
                    or previous.get("binding") != binding
                ):
                    raise ConfigurationConflict(
                        "Genau dieser offene Wartungsvorgang ist erforderlich."
                    )
                if state["phase"] not in {"idle", "maintenance"}:
                    raise ConfigurationConflict("Zuerst die Konfigurationssitzung abschließen.")
                if (previous or state["phase"] == "maintenance") and previous.get(
                    "binding"
                ) != binding:
                    raise ConfigurationConflict("Wartung gehört zu einer anderen Installation.")
                recorded = "commit_version" in previous and previous.get("step") == "pending"
                if recorded and previous.get("target") != target:
                    raise ConfigurationConflict(
                        "Bestätigter Wartungsvorgang verlangt dasselbe Ziel."
                    )
                # Setup is also the existing SCM repair path. It never releases
                # work: local blockers apply before entry, and production must
                # additionally recheck SCM state before admission can reopen.
                reasons = self.blockers(state, include_external=target == "production")
                if reasons:
                    raise ConfigurationConflict("; ".join(reasons))
                backup: ManagedBackupRecord | None = None
                if before_transition is not None:
                    if state["phase"] != "idle" or previous:
                        raise ConfigurationConflict(
                            "Sicherung vor Wartungsbeginn erfordert abgeschlossenen Ruhezustand."
                        )
                    backup = before_transition()
                    if backup is not None and not isinstance(backup, ManagedBackupRecord):
                        raise ValueError("Wartungsvorbereitung muss ein Managed Backup liefern.")
                    if self.state() != state:
                        raise ConfigurationConflict(
                            "Zustand während Wartungsvorbereitung geändert."
                        )
                    reasons = self.blockers(state, include_external=target == "production")
                    if reasons:
                        raise ConfigurationConflict("; ".join(reasons))
                backup_receipt = deepcopy(previous.get("backup"))
                if before_transition is not None and backup is not None:
                    backup_receipt = {
                        "backup_id": backup.backup_id,
                        "path": str(backup.path),
                        "digest": backup.digest,
                        "instance_uuid": backup.instance_uuid,
                        "authority_epoch": backup.authority_epoch,
                        "created_at": backup.created_at.isoformat(),
                    }
                if not recorded:
                    state["phase"] = "maintenance"
                    state["maintenance"] = {
                        "operation_id": str(uuid4()),
                        "binding": binding,
                        "target": target,
                        "step": "pending",
                        "actor": actor,
                        "reason": reason,
                        **({"backup": backup_receipt} if backup_receipt is not None else {}),
                    }
                    self._save(state)
                    self._audit("host_transition_started", state, actor)
                version = state["version"]
                completed = False
                open_transition = True

                def complete() -> dict[str, Any]:
                    nonlocal completed
                    current = self.state()
                    if not open_transition or completed or current["version"] != version:
                        raise ConfigurationConflict("Wartung geändert oder bereits abgeschlossen.")
                    reasons = self.blockers(current, include_external=target == "production")
                    if reasons:
                        raise ConfigurationConflict("; ".join(reasons))
                    maintenance = current["maintenance"]
                    if not recorded:
                        self._audit("host_transition_commit_requested", current, actor)
                        maintenance["commit_version"] = current["version"] + 1
                        self._save(current)
                    # A retry may append this observation again. The operation ID
                    # and commit version identify the same still-fenced decision.
                    self._audit("host_transition_commit_recorded", current, actor)
                    current["last_host_transition"] = {
                        key: maintenance[key]
                        for key in ("operation_id", "binding", "target", "commit_version")
                    }
                    maintenance["step"] = target
                    if target == "production":
                        current["phase"] = "idle"
                        current.pop("maintenance")
                    self._save(current)
                    completed = True
                    return current

                try:
                    yield complete
                finally:
                    open_transition = False
        except StateStoreConflict as exc:
            raise ConfigurationConflict("Betrieb oder andere Wartungsaktion läuft.") from exc

    @contextmanager
    def operator_action(self) -> Iterator[None]:
        """Serialize explicit lifecycle actions against dispatch and config edits."""
        with self.configuration_write():
            token = self._inside.set(True)
            try:
                yield
            finally:
                self._inside.reset(token)

    def complete_issue(self, issue: int) -> None:
        if not self._inside.get():
            raise ConfigurationConflict("Exklusive Lifecycleaktion erforderlich.")

        def finish(state: dict[str, Any]) -> None:
            state["issues"].pop(str(issue), None)
            state.get("prompt_bindings", {}).pop(str(issue), None)

        self._update(finish)

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
            if state["phase"] != "idle" or state.get("maintenance"):
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
                if msg.name in {"PlanIssue", "ReplanIssue"} and key not in state["issues"]:
                    manifest = (
                        self.prompt_manifest()
                        if self.prompt_start_allowed(issue, msg.correlation_id or "")
                        else {}
                    )
                    if manifest:
                        state.setdefault("prompt_bindings", {})[key] = {
                            "manifest": manifest,
                            "bound_at": datetime.now(timezone.utc).isoformat(),
                            "correlation_id": msg.correlation_id,
                        }
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

            previous = self.state().get("prompt_bindings", {}).get(str(issue))
            updated = self._update(record)
            if updated.get("prompt_bindings", {}).get(str(issue)) != previous:
                self._audit("prompt_bound", updated, "runtime")
        return next_()
