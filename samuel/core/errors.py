from __future__ import annotations

from typing import Any

from samuel.core.evaluation_subject import EvaluationSubject


class AgentAbort(Exception):
    def __init__(self, message: str, gate: int | str | None = None, issue: int | None = None):
        self.gate = gate
        self.issue = issue
        super().__init__(message)


class SecurityViolation(Exception):
    pass


class GitTransportAuthError(Exception):
    """Bounded failure at the network-Git credential delegation boundary."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.safe_message = message
        super().__init__(message)


class GateFailed(Exception):
    def __init__(self, gate: int | str, reason: str, owasp_risk: str | None = None):
        self.gate = gate
        self.reason = reason
        self.owasp_risk = owasp_risk
        super().__init__(f"Gate {gate} failed: {reason}")


class SCMRevisionError(Exception):
    """Bounded, credential-free failure while establishing an evaluation subject."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        subject: EvaluationSubject | None = None,
    ):
        self.code = code
        self.safe_message = message
        self.subject = subject
        super().__init__(message)


class SubjectTooLargeError(SCMRevisionError):
    def __init__(self, limit_bytes: int):
        self.limit_bytes = limit_bytes
        super().__init__(
            "subject_too_large",
            f"Evaluation subject exceeds the configured {limit_bytes}-byte diff limit",
        )


class CandidateFileTooLargeError(SCMRevisionError):
    def __init__(self, limit_bytes: int):
        self.limit_bytes = limit_bytes
        super().__init__(
            "candidate_file_too_large",
            f"Candidate file exceeds the configured {limit_bytes}-byte quality limit",
        )


class ProviderUnavailable(Exception):
    def __init__(
        self,
        provider: str,
        reason: str = "",
        *,
        category: str = "provider_unavailable",
        code: str = "provider_unavailable",
        status: int | None = None,
        retryable: bool = False,
    ):
        self.provider = provider
        self.reason = reason
        self.category = category
        self.code = code
        self.status = status
        self.retryable = retryable
        details = [f"category={category}", f"code={code}"]
        if status is not None:
            details.append(f"status={status}")
        details.append(f"retryable={str(retryable).lower()}")
        self.safe_message = f"Provider {provider} unavailable (" + ", ".join(details) + ")"
        super().__init__(f"Provider {provider} unavailable: {reason}")


def describe_diagnostic(
    *, logger: str, reason: str, category: str, event_name: str = ""
) -> dict[str, Any]:
    """Translate one technical record into cautious operator guidance."""

    text = reason.lower()
    if logger == "samuel.core.git" or "git " in text or "create_branch" in text:
        if "git not found" in text:
            return _diagnostic_description(
                "environment",
                "Git ist nicht verfügbar",
                "Der Prozess findet das Programm `git` nicht im PATH.",
                "Branch-, Diff-, Commit- und Push-Schritte können nicht ausgeführt werden.",
                [
                    "Auf dem Zielsystem `git --version` ausführen.",
                    "Git installieren oder den PATH des Samuel-Prozesses korrigieren.",
                    "Samuel neu starten und den fehlgeschlagenen Schritt wiederholen.",
                ],
            )
        if "timed out" in text:
            return _diagnostic_description(
                "environment",
                "Git-Befehl hat das Zeitlimit überschritten",
                "Datenträger, Git-Hook oder Remote-Verbindung können langsam oder blockiert sein.",
                "Der betroffene Git-Schritt wurde abgebrochen; Ergebnisse können fehlen.",
                [
                    "Den genannten Git-Befehl im Zielprojekt manuell ausführen.",
                    "Netzwerk, Remote und blockierende Git-Hooks prüfen.",
                    "Erst nach erfolgreichem Lauf den Samuel-Schritt wiederholen.",
                ],
            )
        if "dirty worktree" in text:
            return _diagnostic_description(
                "scm_git",
                "Branchwechsel durch lokale Änderungen blockiert",
                "Im Zielprojekt liegen nicht eingecheckte oder nicht gesicherte Änderungen.",
                "Samuel stoppt, damit vorhandene Arbeit nicht überschrieben wird.",
                [
                    "Im Zielprojekt `git status --short` und `git diff` prüfen.",
                    "Gewollte Änderungen committen oder sicher stashen; nichts ungeprüft löschen.",
                    "Danach den fehlgeschlagenen Workflow erneut starten.",
                ],
            )
        if "not a valid ref" in text:
            return _diagnostic_description(
                "scm_git",
                "Git-Referenz fehlt",
                "Der geprüfte Branch oder Commit ist lokal nicht vorhanden.",
                "Der Branch- oder Diff-Schritt kann damit nicht fortfahren.",
                [
                    "Remote und Basisbranch mit `git remote -v` und `git branch -a` prüfen.",
                    "`git fetch --prune origin` ausführen und die Basis kontrollieren.",
                ],
            )
        if "create_branch" in text or "checkout -b" in text:
            return _diagnostic_description(
                "scm_git",
                "Arbeitsbranch konnte nicht sicher erstellt werden",
                "Git lehnte das Erstellen oder den abschließenden Branch-Nachweis ab.",
                "Samuel bricht ab, damit Änderungen nicht auf dem falschen Branch landen.",
                [
                    "Vorhergehende Git-Meldung und `git status --short --branch` prüfen.",
                    "Remote, Basisbranch, Rechte und gleichnamige Branches kontrollieren.",
                    "Ursache beheben und den Workflow neu starten.",
                ],
            )
        return _diagnostic_description(
            "scm_git",
            "Git-Operation fehlgeschlagen",
            "Git hat den in den technischen Details genannten Befehl abgelehnt.",
            "Der davon abhängige Workflow-Schritt ist unvollständig.",
            [
                "`git status --short --branch` im Zielprojekt prüfen.",
                "Befehl und Fehlermeldung in den technischen Details nachvollziehen.",
                "Nach Behebung den fehlgeschlagenen Schritt wiederholen.",
            ],
        )

    category_descriptions = {
        "llm": (
            "llm_provider",
            "LLM-Aufruf fehlgeschlagen",
            "Provider, Modell, Zugangsdaten, Rate-Limit oder Netzwerk kommen infrage.",
            "Die aktuelle KI-Aufgabe kann unvollständig oder abgebrochen sein.",
            [
                "Provider, Modell und Zeitpunkt in den technischen Details prüfen.",
                "Verbindung, Guthaben/Limit und Zugangsdaten testen.",
                "Erst danach die betroffene Aufgabe erneut ausführen.",
            ],
        ),
        "config": (
            "configuration",
            "Konfiguration konnte nicht angewendet werden",
            "Ein Wert fehlt, ist ungültig oder passt nicht zur Umgebung.",
            "Die Funktion nutzt gegebenenfalls keinen oder einen älteren gültigen Stand.",
            [
                "Datei und Feld aus den technischen Details prüfen.",
                "Konfiguration validieren und den Dienst neu laden.",
            ],
        ),
        "security": (
            "security",
            "Sicherheitsprüfung hat angeschlagen",
            "Eine Schutzregel hat einen potenziell unsicheren Zustand erkannt.",
            "Der betroffene Vorgang kann bewusst blockiert worden sein.",
            [
                "Ereignis, betroffene Dateien und OWASP-Hinweis prüfen.",
                "Nicht umgehen; Ursache bewerten und gezielt beheben.",
            ],
        ),
    }
    selected = category_descriptions.get(category)
    if selected:
        return _diagnostic_description(*selected)
    if category in {"workflow", "gates", "quality", "eval", "guard", "plan"}:
        return _diagnostic_description(
            "workflow",
            "Workflow-Prüfung nicht erfolgreich",
            "Eine fachliche Prüfung oder ein Gate hat den Stand abgelehnt.",
            "Der Workflow wird nicht als erfolgreich abgeschlossen behandelt.",
            [
                "Grund, Issue und betroffene Dateien prüfen.",
                "Das auslösende Kriterium beheben und erneut prüfen.",
            ],
        )
    return _diagnostic_description(
        "product",
        event_name or "Samuel-Laufzeitproblem",
        "Die Meldung allein beweist keine Root Cause; Komponente und Rohmeldung grenzen sie ein.",
        "Die in der Meldung genannte Funktion kann beeinträchtigt sein.",
        [
            "Komponente, Zeitpunkt und technische Details prüfen.",
            "Bei Wiederholung Korrelation und unmittelbar vorhergehende Logs heranziehen.",
        ],
    )


def _diagnostic_description(
    problem_type: str, title: str, cause: str, impact: str, next_steps: list[str]
) -> dict[str, Any]:
    return {
        "problem_type": problem_type,
        "title": title,
        "cause": cause,
        "impact": impact,
        "next_steps": next_steps,
    }
