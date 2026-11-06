"""Operation-bound SCM diagnostics; observations never grant authority (#897)."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class PermissionActor(StrEnum):
    RUNTIME = "runtime_bot"
    OPERATOR = "operator"


class PermissionOperation(StrEnum):
    REPOSITORY_READ = "repository_read"
    REPOSITORY_WRITE = "repository_write"
    IDENTITY_READ = "identity_read"
    LABEL_READ = "label_read"
    BRANCH_READ = "branch_protection_read"
    BRANCH_WRITE = "branch_protection_write"
    HOOK_READ = "webhook_read"
    HOOK_WRITE = "webhook_provision"
    REF_WRITE = "git_reference_write"
    OTHER = "scm_request"


class PermissionOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"
    GUARD_BLOCKED = "guard_blocked"
    UNKNOWN = "unknown"


_OPERATIONS = {
    PermissionOperation.REPOSITORY_READ: "Repository lesen",
    PermissionOperation.REPOSITORY_WRITE: "Repository schreiben (Issue/Kommentar/Label/PR/Datei)",
    PermissionOperation.IDENTITY_READ: "SCM-Identität lesen",
    PermissionOperation.LABEL_READ: "Repository-Labels lesen",
    PermissionOperation.BRANCH_READ: "Branchschutz lesen",
    PermissionOperation.BRANCH_WRITE: "Branchschutz ändern",
    PermissionOperation.HOOK_READ: "Webhooks lesen",
    PermissionOperation.HOOK_WRITE: "Webhooks einrichten/ändern",
    PermissionOperation.REF_WRITE: "Git-Referenzen ändern",
    PermissionOperation.OTHER: "SCM-Anfrage",
}
_STATES = {
    PermissionOutcome.SUCCEEDED: "ACCESS_CONFIRMED",
    PermissionOutcome.DENIED: "OPERATOR_ACTION_REQUIRED",
    PermissionOutcome.GUARD_BLOCKED: "UNEXPECTED_PRIVILEGE_ESCALATION_REQUEST",
    PermissionOutcome.UNKNOWN: "UNKNOWN",
}


# Provider-relative route templates only. Repository names, IDs, query values
# and arbitrary path text never enter permission diagnostics.
_ENDPOINTS = (
    "/user",
    "/repos/{owner}/{repo}",
    "/repos/{owner}/{repo}/branch_protections/{branch}",
    "/repos/{owner}/{repo}/branch_protections",
    "/repos/{owner}/{repo}/branches/{branch}/protection",
    "/repos/{owner}/{repo}/hooks",
    "/repos/{owner}/{repo}/hooks/{id}",
    "/repos/{owner}/{repo}/git/refs",
    "/repos/{owner}/{repo}/git/refs/{ref}",
    "/repos/{owner}/{repo}/issues",
    "/repos/{owner}/{repo}/issues/{id}",
    "/repos/{owner}/{repo}/issues/{id}/comments",
    "/repos/{owner}/{repo}/issues/comments/{id}",
    "/repos/{owner}/{repo}/issues/{id}/labels",
    "/repos/{owner}/{repo}/issues/{id}/labels/{label}",
    "/repos/{owner}/{repo}/labels",
    "/repos/{owner}/{repo}/labels/{label}",
    "/repos/{owner}/{repo}/pulls",
    "/repos/{owner}/{repo}/pulls/{id}",
    "/repos/{owner}/{repo}/pulls/{id}/merge",
    "/repos/{owner}/{repo}/contents/{path}",
)
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "unknown"}


def scm_endpoint(path: str) -> str:
    for template in _ENDPOINTS:
        pattern = re.sub(r"\{[^}]+\}", "[^/]+", template)
        if re.fullmatch(pattern, path.split("?", 1)[0]):
            return template
    return "unknown"


@dataclass(frozen=True)
class PermissionDiagnostic:
    actor: PermissionActor
    operation: PermissionOperation
    outcome: PermissionOutcome
    http_status: int | None = None
    method: str = "unknown"
    endpoint: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            **self.describe(),
            "schema": "scm-permission.v1",
            "state": _STATES[self.outcome],
            "scope": "operation",
            "required_permission": "unknown",
            "overall_permissions": "not_checked",
            "action_actor": "none" if self.outcome == PermissionOutcome.SUCCEEDED else "operator",
        }

    def describe(self) -> dict[str, Any]:
        role = "Runtime-Bot" if self.actor == PermissionActor.RUNTIME else "Operator-Credential"
        operation = _OPERATIONS[self.operation]
        context = f"{operation} · verwendete Rolle: {role}."
        if self.endpoint != "unknown":
            context += f" {self.method} {self.endpoint}."
        if self.http_status is not None:
            context += f" HTTP {self.http_status}."
        if self.outcome == PermissionOutcome.SUCCEEDED:
            title = "Zugriff für diese Operation bestätigt"
            impact = "Andere Operationen und wirksame Mindestrechte sind damit nicht geprüft."
            steps = ["Weitere benötigte Fähigkeiten getrennt prüfen; keine Rechte ausweiten."]
        elif self.outcome == PermissionOutcome.DENIED:
            title = "Gezielte Operatorprüfung erforderlich"
            impact = (
                "Dieser Zugriff wurde abgewiesen; das erforderliche Mindestrecht ist unbekannt."
            )
            steps = [
                "Operator: Zielrepository, Endpoint und das hier verwendete Credential prüfen. "
                "Authentisierung und tatsächlich erforderliche Einzelrechte getrennt klären."
            ]
            if self.operation in {PermissionOperation.BRANCH_READ, PermissionOperation.HOOK_WRITE}:
                steps.append(
                    "Die getrennte Operatorprüfung bzw. Einrichtung verwenden; "
                    "dem Runtime-Bot keine pauschalen Adminrechte geben."
                )
        elif self.outcome == PermissionOutcome.GUARD_BLOCKED:
            title = "Verbotene SCM-Verwaltungsoperation blockiert"
            impact = "Der vorhandene API-Guard hat diese Anfrage vor dem Netzwerkzugriff gesperrt."
            steps = [
                "Aufrufenden Pfad und zugehörigen Lauf prüfen und korrigieren. "
                "Die Sperre beibehalten; keine erweiterten Botrechte vergeben.",
                "Erforderliche Verwaltungsaufgaben über den getrennten Operatorweg erledigen. "
                "Die Sperre beweist keine Absicht eines LLMs.",
            ]
        else:
            title = "Berechtigung für diese Operation nicht prüfbar"
            impact = "Fehlende oder mehrdeutige Antworten belegen weder ausreichende Rechte noch eine Rechteausweitung."
            steps = [
                "Operator: Verbindung, Zielrepository, Endpoint und verwendetes Credential prüfen. "
                "Bei unklarem Schreibresultat zuerst die tatsächliche Wirkung prüfen; nicht blind wiederholen."
            ]
        return {
            "problem_type": "security"
            if self.outcome == PermissionOutcome.GUARD_BLOCKED
            else "scm_git",
            "title": title,
            "cause": context,
            "impact": impact,
            "next_steps": steps,
        }

    def summary(self) -> str:
        description = self.describe()
        return f"{_STATES[self.outcome]}: {description['cause']} {description['impact']}"


def read_permission_diagnostic(value: object) -> PermissionDiagnostic | None:
    """Reconstruct only bounded facts, never stored/provider-supplied advice."""
    if not isinstance(value, dict) or value.get("schema") != "scm-permission.v1":
        return None
    try:
        status = value.get("http_status")
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            return None
        method, endpoint = value.get("method", "unknown"), value.get("endpoint", "unknown")
        if method not in _METHODS or endpoint not in (*_ENDPOINTS, "unknown"):
            return None
        return PermissionDiagnostic(
            PermissionActor(value["actor"]),
            PermissionOperation(value["operation"]),
            PermissionOutcome(value["outcome"]),
            status,
            method,
            endpoint,
        )
    except (KeyError, ValueError, TypeError):
        return None


def scm_operation(method: str, path: str) -> PermissionOperation:
    """Map known routes to bounded capability names, without copying URLs or IDs."""
    parts = path.split("?", 1)[0].strip("/").split("/")
    read = method == "GET"
    if parts == ["user"] and read:
        return PermissionOperation.IDENTITY_READ
    if len(parts) < 3 or parts[0] != "repos":
        return PermissionOperation.OTHER
    tail = parts[3:]
    if not tail and read:
        return PermissionOperation.REPOSITORY_READ
    if tail and (
        tail[0] == "branch_protections" or (tail[0] == "branches" and "protection" in tail)
    ):
        return PermissionOperation.BRANCH_READ if read else PermissionOperation.BRANCH_WRITE
    if tail and tail[0] == "hooks":
        return PermissionOperation.HOOK_READ if read else PermissionOperation.HOOK_WRITE
    if tail[:2] == ["git", "refs"] and not read:
        return PermissionOperation.REF_WRITE
    if tail == ["labels"] and read:
        return PermissionOperation.LABEL_READ
    if tail and tail[0] in {"issues", "pulls", "labels", "contents"} and not read:
        return PermissionOperation.REPOSITORY_WRITE
    return PermissionOperation.OTHER


def log_scm_permission(
    logger: logging.Logger,
    actor: PermissionActor,
    method: str,
    path: str,
    outcome: PermissionOutcome,
    http_status: int | None = None,
) -> PermissionDiagnostic:
    diagnostic = PermissionDiagnostic(
        actor,
        scm_operation(method, path),
        outcome,
        http_status,
        method if method in _METHODS else "unknown",
        scm_endpoint(path),
    )
    # Only failures enter the existing WARNING+ audit bridge. Successful calls
    # remain operation-local INFO logs, never a persisted readiness verdict.
    level = logging.INFO if outcome == PermissionOutcome.SUCCEEDED else logging.WARNING
    if outcome == PermissionOutcome.GUARD_BLOCKED:
        level = logging.CRITICAL
    logger.log(level, diagnostic.summary(), extra={"permission_diagnostic": diagnostic})
    return diagnostic
