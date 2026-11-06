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
    *,
    logger: str,
    reason: str,
    category: str,
    event_name: str = "",
    gate: str = "",
    permission: object = None,
) -> dict[str, Any]:
    """Translate one technical record into cautious operator guidance."""

    from samuel.core.permission_diagnostics import read_permission_diagnostic

    diagnostic = read_permission_diagnostic(permission)
    if diagnostic is not None:
        return {**diagnostic.describe(), "permission_diagnostic": diagnostic.to_dict()}
    text = reason.lower()
    continuation_guidance = (
        "Im Dashboard den Runstatus und offene Vorgänge prüfen. Bei gescheitertem Versuch: "
        "offene Vorgänge klären, ausdrücklich Versuch beenden, Ursache beheben und neu planen; "
        "den neuen Plan menschlich freigeben. Für wartende Runs nur die angebotene gebundene "
        "Aktion nutzen. Keine freie Wiederholung einzelner Workflow-Stages."
    )
    if event_name == "GateFailed" and gate == "diff_secret_scan":
        return _diagnostic_description(
            "security",
            "Secret-Prüfung hat den Kandidaten blockiert",
            "Das Gate diff_secret_scan meldet ein Secret-Muster in hinzugefügten Diff-Zeilen; "
            "ob es ein echtes Geheimnis ist, muss geprüft werden.",
            "Dieser Kandidat hat die Sicherheitsprüfung nicht bestanden.",
            [
                "Finding-Typ und gemeldete Datei/Zeile im Kandidaten prüfen; "
                "Secret-Werte nicht in Logs, Kommentare oder Meldungen kopieren.",
                "Echte Zugangsdaten aus dem Kandidaten entfernen und durch eine konfigurierte "
                "Secret-Referenz ersetzen; offengelegte Zugangsdaten beim Anbieter widerrufen. "
                "Bei Fehlalarm den Befund prüfen, das Gate nicht umgehen.",
                continuation_guidance,
            ],
        )
    if event_name == "WorkflowBlocked" and text == "bound_healing:gate_11_not_failed":
        return _diagnostic_description(
            "workflow",
            "Automatisches Healing für diesen Befund nicht zulässig",
            "Healing setzt ein fehlgeschlagenes Gate 11 voraus; diese Voraussetzung ist hier nicht erfüllt. "
            "Die Meldung benennt keine Ursache eines anderen Gatefehlers.",
            "Aus diesem Befund wird keine automatische Reparatur gestartet; der Versuch bleibt gestoppt.",
            [
                "Im selben Lauf die GateFailed-Meldung öffnen und deren konkreten Befund beheben. "
                "Ein bestandenes Gate 11 nicht als weiteren Fehler behandeln.",
                continuation_guidance,
            ],
        )
    if event_name == "PlanComplexityWarn":
        return _diagnostic_description(
            "workflow",
            "Hinweis zur Plan-Komplexität",
            "Der Planumfang hat eine Hinweis- oder Teilungsempfehlung ausgelöst.",
            "Dieser Hinweis allein blockiert den Workflow nicht und belegt keine "
            "fehlgeschlagene Prüfung. Planfreigabe und Required-Gates bleiben maßgeblich.",
            [
                "Planumfang und gegebenenfalls die Teilungsempfehlung prüfen.",
                "Den tatsächlichen Workflow- und Gatestatus getrennt betrachten; "
                "aus dem Hinweis allein keinen Neustart oder Reparaturbedarf ableiten.",
            ],
        )
    if logger == "samuel.adapters.llm.prompts":
        return _diagnostic_description(
            "configuration",
            "Promptkonfiguration prüfen",
            "Beim Lesen oder Verwalten einer Promptdatei wurde ein Problem gemeldet; "
            "Datei und Fehlerklasse stehen in den technischen Details.",
            "Die effektive Promptquelle kann abweichen oder fehlen. "
            "Ob die Aufgabe fortgesetzt wurde, zeigt ihr eigener Runstatus.",
            [
                "Dateinamen, Scope und effektive Promptquelle im Dashboard prüfen.",
                "Dateirechte, UTF-8-Inhalt und sichere Pfade der betroffenen Quelle prüfen; "
                "Symlinkschutz beibehalten.",
                continuation_guidance,
            ],
        )
    if logger == "samuel.core.bootstrap" and text.startswith(
        "runtime run-projection backfill failed"
    ):
        return _diagnostic_description(
            "product",
            "Run-Projektion konnte nicht wiederhergestellt werden",
            "Der Abgleich oder Audit-Backfill der gespeicherten Run-Projektion ist fehlgeschlagen; "
            "die konkrete Exceptionklasse steht in den technischen Details.",
            "Dashboard-Runhistorie und Statusprojektionen können unvollständig sein. "
            "Dies beweist keinen Gate-, Provider- oder Candidatefehler.",
            [
                "Exceptionklasse, Dateizeile und Korrelation dieser Meldung prüfen.",
                "Den vorhandenen Run-Projektionspfad korrigieren und mit Regression prüfen; "
                "historische Fehler nicht überschreiben und keinen laufenden Subject reparieren.",
            ],
        )
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
                    continuation_guidance,
                ],
            )
        if "timed out" in text:
            return _diagnostic_description(
                "environment",
                "Git-Befehl hat das Zeitlimit überschritten",
                "Datenträger, Git-Hook oder Remote-Verbindung können langsam oder blockiert sein.",
                "Der betroffene Git-Schritt wurde abgebrochen; Ergebnisse können fehlen.",
                [
                    "Im Dashboard den Git-Schritt und seine letzte bestätigte Wirkung prüfen; "
                    "einen möglicherweise bereits wirksamen Schreibbefehl nicht blind wiederholen.",
                    "Erreichbarkeit des Remotes sowie blockierende Git-Hooks prüfen.",
                    continuation_guidance,
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
                    continuation_guidance,
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
                    continuation_guidance,
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
                continuation_guidance,
            ],
        )

    if event_name in {
        "WorkflowBlocked",
        "WorkflowAborted",
        "PlanBlocked",
        "ReviewBlocked",
        "PRCreationFailed",
        "MergeOutcomeUnknown",
        "EvaluationSubjectInvalidated",
    }:
        return _diagnostic_description(
            "workflow",
            "Workflow-Versuch gestoppt",
            "Der Workflow meldet einen Stopp. Die technische Ursache ist aus dieser "
            "Meldung allein nicht belegt.",
            "Der Versuch ist nicht erfolgreich abgeschlossen; ein Stopp belegt keinen zusätzlichen Gatefehler.",
            [
                "Im Dashboard die Meldungen und Logs desselben Issues und derselben Korrelation "
                "prüfen. Den konkret fehlgeschlagenen Schritt und dessen Befund heranziehen; "
                "bei fehlender Ursache Ereignis, Zeitpunkt und Korrelation für die Fehleranalyse festhalten.",
                continuation_guidance,
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
                continuation_guidance,
            ],
        ),
        "config": (
            "configuration",
            "Konfiguration konnte nicht angewendet werden",
            "Ein Wert fehlt, ist ungültig oder passt nicht zur Umgebung.",
            "Die Funktion nutzt gegebenenfalls keinen oder einen älteren gültigen Stand.",
            [
                "Datei und Feld aus den technischen Details prüfen.",
                "Im Dashboard unter Konfiguration den Änderungsmodus nutzen, sobald keine "
                "Workflows oder offenen Vorgänge mehr laufen; betroffenen Wert korrigieren und validieren.",
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
                continuation_guidance,
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
