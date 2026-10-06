from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


@dataclass
class Event:
    name: str
    payload: dict = field(default_factory=dict)
    ts: datetime = field(default_factory=_now)
    source: str = ""
    event_version: int = 1
    correlation_id: str = field(default_factory=_uuid)
    causation_id: str | None = None


# --- Workflow Events ---


@dataclass
class IssueReady(Event):
    name: str = "IssueReady"


@dataclass
class PlanCreated(Event):
    name: str = "PlanCreated"


@dataclass
class PlanValidated(Event):
    name: str = "PlanValidated"


@dataclass
class PlanBlocked(Event):
    name: str = "PlanBlocked"


@dataclass
class ClarificationRequested(Event):
    name: str = "ClarificationRequested"


@dataclass
class ClarificationWaiting(Event):
    name: str = "ClarificationWaiting"


@dataclass
class ClarificationAccepted(Event):
    name: str = "ClarificationAccepted"


@dataclass
class ClarificationSuperseded(Event):
    name: str = "ClarificationSuperseded"


@dataclass
class PlanPosted(Event):
    name: str = "PlanPosted"


@dataclass
class PlanReplanRejected(Event):
    """Ordinary planning refused because an authoritative plan is active."""

    name: str = "PlanReplanRejected"


@dataclass
class PlanRevoked(Event):
    """A concrete plan was explicitly revoked before replacement planning."""

    name: str = "PlanRevoked"


@dataclass
class PlanApproved(Event):
    name: str = "PlanApproved"


@dataclass
class PlanFeedbackReceived(Event):
    name: str = "PlanFeedbackReceived"


@dataclass
class PlanRetry(Event):
    name: str = "PlanRetry"


@dataclass
class PlanRetryEvaluated(Event):
    """Records the contract-aware selection of one planning retry."""

    name: str = "PlanRetryEvaluated"


@dataclass
class PlanRevised(Event):
    name: str = "PlanRevised"


@dataclass
class CodeGenerated(Event):
    name: str = "CodeGenerated"


@dataclass
class QualityPassed(Event):
    name: str = "QualityPassed"


@dataclass
class QualityFailed(Event):
    name: str = "QualityFailed"


@dataclass
class GatesPassed(Event):
    """All required PR-Gates passed for an issue. Published by pr_gates
    handler right before PRCreated. Used by the dashboard to mark the
    `gates`-stage as done (#258)."""

    name: str = "GatesPassed"


@dataclass
class GateEvaluationCompleted(Event):
    """Complete per-gate evidence for one immutable evaluation subject."""

    name: str = "GateEvaluationCompleted"


@dataclass
class GateEvaluationUnavailable(Event):
    """A gate run could not produce one complete bound observation."""

    name: str = "GateEvaluationUnavailable"


@dataclass
class CandidateVerificationPending(Event):
    """Passive candidate awaits an explicitly authorized provider result."""

    name: str = "CandidateVerificationPending"


@dataclass
class CandidateEvaluationCompleted(Event):
    """Passive candidate evaluation completed without mutation authority."""

    name: str = "CandidateEvaluationCompleted"


@dataclass
class CandidateEvaluationFailed(Event):
    """Passive candidate evaluation reached a terminal negative result."""

    name: str = "CandidateEvaluationFailed"


@dataclass
class CandidateSubmissionRejected(Event):
    """Candidate submission could not establish its authoritative binding."""

    name: str = "CandidateSubmissionRejected"


@dataclass
class ProviderVerificationRequested(Event):
    """An exact authorized provider request was durably created or recovered."""

    name: str = "ProviderVerificationRequested"


@dataclass
class ProviderVerificationPending(Event):
    """Dispatch attribution or provider execution is still pending."""

    name: str = "ProviderVerificationPending"


@dataclass
class ProviderVerificationBlocked(Event):
    """Provider verification reached a fail-closed terminal outcome."""

    name: str = "ProviderVerificationBlocked"


@dataclass
class ProviderGateEvaluationCompleted(Event):
    """Passive provider evidence was evaluated without mutation authority."""

    name: str = "ProviderGateEvaluationCompleted"


@dataclass
class AuthorityReconcileRequired(Event):
    """Persisted authority state cannot safely authorize Healing or Resume."""

    name: str = "AuthorityReconcileRequired"


@dataclass
class ResumeAttempted(Event):
    """A bound checkpoint entered the OS-lock/lease/prerequisite sequence."""

    name: str = "ResumeAttempted"


@dataclass
class ResumeCompleted(Event):
    """A restart-persistent finalization checkpoint reached its next workflow event."""

    name: str = "ResumeCompleted"


@dataclass
class ResumeBlocked(Event):
    """A checkpoint was left pending or quarantined with a bounded reason."""

    name: str = "ResumeBlocked"


@dataclass
class ScoreObserved(Event):
    """Non-binding score derivation of one bound gate observation."""

    name: str = "ScoreObserved"


@dataclass
class PRCreated(Event):
    name: str = "PRCreated"


@dataclass
class PRCreationFailed(Event):
    """The gates passed, but the SCM did not confirm a valid pull request.

    This is a terminal failure event.  It is deliberately separate from
    ``GateFailed`` because it says nothing about the gate result, and separate
    from ``PRCreated`` because no downstream review or merge action may follow.
    """

    name: str = "PRCreationFailed"


@dataclass
class EvaluationSubjectInvalidated(Event):
    """The SCM PR no longer points at the artifact for which gates passed."""

    name: str = "EvaluationSubjectInvalidated"


@dataclass
class PRMerged(Event):
    """#193: Auto-Merge nach Gates-Pass + create_pr (feature_flag).
    Mapping greift auf bestehende ("scm", "pr_merge")-Eintraege in
    OWASP_RISK_MAP und AI_ACT_ARTICLE_MAP — keine neuen Mapping-Entries."""

    name: str = "PRMerged"


@dataclass
class ReviewCompleted(Event):
    """A closed review document was validated against the exact subject."""

    name: str = "ReviewCompleted"


@dataclass
class ReviewBlocked(Event):
    """Review or merge policy stopped without granting merge authority."""

    name: str = "ReviewBlocked"


@dataclass
class MergeOutcomeUnknown(Event):
    """A persisted merge intent has no unambiguous SCM postcondition."""

    name: str = "MergeOutcomeUnknown"


# --- #230: SCM-Activity-Events (rein beobachtend) ---
# Speisen reale Repo-Aktivitaet (Webhook) in den Bus, auch wenn sie "am
# Framework vorbei" passiert (manuelle UI-/API-Aktionen). Bewusst eigene Namen
# statt PRCreated/PRMerged wiederzuverwenden: jene sind Workflow-Events des Bots
# (loesen z.B. Auto-Merge aus); diese hier loesen NICHTS aus, sie machen nur
# sichtbar, was im Repo geschah. Payload traegt ``actor``, ``actor_type``
# (bot|human), ``source`` ("webhook"|"polling"), ``number`` (Issue/PR),
# ``title``, ``url``, ``timestamp`` and a stable ``activity_id`` used to
# deduplicate webhook and polling observations.
# Kategorie ``scm`` -> AI-Act Art. 12 (Logging) / OWASP agentic_supply_chain.
@dataclass
class IssueOpened(Event):
    name: str = "IssueOpened"


@dataclass
class IssueClosed(Event):
    name: str = "IssueClosed"


@dataclass
class IssueCommented(Event):
    name: str = "IssueCommented"


@dataclass
class PullRequestOpened(Event):
    name: str = "PullRequestOpened"


@dataclass
class PullRequestMerged(Event):
    name: str = "PullRequestMerged"


@dataclass
class PullRequestClosed(Event):
    name: str = "PullRequestClosed"


@dataclass
class TestRunCompleted(Event):
    name: str = "TestRunCompleted"


@dataclass
class PlanContextLoaded(Event):
    """#237: Plan-Stage hat Code-Kontext geladen (Skeleton + relevant Files +
    Grep + Architektur-Constraints). Payload zaehlt die Tokens pro Section."""

    name: str = "PlanContextLoaded"


@dataclass
class ACVerified(Event):
    """#236: pro erfolgreich verifiziertem Akzeptanzkriterium publisht."""

    name: str = "ACVerified"


@dataclass
class ACFailed(Event):
    """#236: pro fehlgeschlagenem Akzeptanzkriterium publisht."""

    name: str = "ACFailed"


@dataclass
class ACManualPending(Event):
    """A manual acceptance criterion is visible but not yet human-approved.

    This is deliberately neither ``ACVerified`` nor ``ACFailed``: automatic
    verification cannot decide a MANUAL criterion, and an LLM-owned checkbox
    must never turn it into successful evidence.
    """

    name: str = "ACManualPending"


@dataclass
class PlanPreCheckCompleted(Event):
    """#238: Plan-Pre-Check (Skeleton-Validation + AC-Dry-Run + Komplexitaets-
    Score) abgeschlossen. Payload enthaelt structural_score, skeleton_score,
    ac_dry_run_score, blocking_failures, retry_attempt, overall_pass."""

    name: str = "PlanPreCheckCompleted"


@dataclass
class ScopeCreepDetected(Event):
    """#247 Schicht B: Plan referenziert Dateien/Themen, die im Issue-Body nicht
    verankert sind (Scope-Creep-Verdacht). Payload: issue, files (Liste), count,
    reason. Warn-only per Default; bei Feature-Flag ``scope_guard`` → PlanBlocked.
    Kategorie ``plan`` → OWASP ASI01 (Agent Goal Hijack), AI-Act Art. 14."""

    name: str = "ScopeCreepDetected"


@dataclass
class PromptInjectionRiskDetected(Event):
    """Advisory phrase-based risk signal for untrusted issue input.

    The payload contains matched indicator identifiers, never the raw issue
    text.  It is evidence of a heuristic signal, not proof of an attack and
    not a blocking decision by itself.
    """

    name: str = "PromptInjectionRiskDetected"


@dataclass
class SecretRiskDetected(Event):
    """Bounded advisory evidence for a secret-shaped candidate value.

    Only stable rule identifiers and diff line numbers are published.  The
    matched value is deliberately absent from the event payload.
    """

    name: str = "SecretRiskDetected"


@dataclass
class OutOfScopeDiff(Event):
    """#247 Schicht C: Diff berührt Dateien, die der Plan nicht referenziert.
    Payload: issue, files (Liste), count, reason. Warn-only per Default.
    Kategorie ``guard`` → OWASP ASI01 (Agent Goal Hijack), AI-Act Art. 14."""

    name: str = "OutOfScopeDiff"


@dataclass
class PlanComplexityWarn(Event):
    """#238 Schicht A (aus #247): Plan-Komplexitaet ueberschritt Schwelle.
    Payload: ac_count, file_count, slice_count, pflicht_bereich_count,
    recommendation in {warn, split_recommended}."""

    name: str = "PlanComplexityWarn"


@dataclass
class GateFailedEvent(Event):
    name: str = "GateFailed"


@dataclass
class Scored(Event):
    name: str = "Scored"


@dataclass
class EvalCompleted(Event):
    name: str = "EvalCompleted"


@dataclass
class EvalFailed(Event):
    name: str = "EvalFailed"


# --- Terminal Events ---


@dataclass
class WorkflowBlocked(Event):
    name: str = "WorkflowBlocked"


@dataclass
class WorkflowAborted(Event):
    name: str = "WorkflowAborted"


@dataclass
class LLMUnavailable(Event):
    name: str = "LLMUnavailable"


# --- Framework Events ---


@dataclass
class TokenLimitHit(Event):
    name: str = "TokenLimitHit"


@dataclass
class WorkflowBudgetAdmitted(Event):
    name: str = "WorkflowBudgetAdmitted"


@dataclass
class LLMBudgetAttemptReserved(Event):
    name: str = "LLMBudgetAttemptReserved"


@dataclass
class LLMBudgetAttemptSettled(Event):
    name: str = "LLMBudgetAttemptSettled"


@dataclass
class LLMBudgetBlocked(Event):
    name: str = "LLMBudgetBlocked"


@dataclass
class ConfigReloaded(Event):
    name: str = "ConfigReloaded"


@dataclass
class DiagnosticRaised(Event):
    """Structured warning/error emitted from Python logging into the audit bus.

    Payload fields: level, category, reason, logger, file, line, exception,
    issue.  This bridges caught runtime failures outside command/event handlers
    into the same audit stream used by the dashboard.
    """

    name: str = "DiagnosticRaised"


@dataclass
class TamperDetected(Event):
    """#208: Manipulation an Code/Artefakten erkannt — z.B. eine Webhook-
    Payload, deren HMAC-Signatur nicht verifiziert (HMAC existiert genau zur
    Tamper-Erkennung), oder eine manuelle Code-Aenderung in einer laufenden
    Workflow-Phase. Payload: author, files (Liste), mode (self/manual/external),
    step, owasp_risk, reason, issue. Kategorie ``security`` → OWASP ASI04
    (Agentic Supply Chain), AI-Act Art. 15 (Robustheit/Cybersicherheit)."""

    name: str = "TamperDetected"


@dataclass
class UnauthorizedChange(Event):
    """#208: Push/Branch-Manipulation ausserhalb des Agents (unautorisierter
    Akteur). Payload: author, files, mode, step, owasp_risk, reason, issue."""

    name: str = "UnauthorizedChange"


@dataclass
class IntegrityViolation(Event):
    """#208: Hash-/Signatur-Mismatch (z.B. fehlgeschlagene Audit-Log-HMAC-Chain-
    Verifikation, siehe #333). Payload: files, expected, actual, owasp_risk,
    reason, issue."""

    name: str = "IntegrityViolation"


@dataclass
class ConfigChanged(Event):
    """#375: Operator-Aenderung einer Konfiguration zur Laufzeit (z.B. die
    EU-AI-Act-Deployment-Risikoklasse im Dashboard). Payload: ``setting``,
    ``old``, ``new``, ``source`` (z.B. ``dashboard``), ``reason``. Kategorie
    ``config`` → AI-Act Art. 12 (Logging): die Aenderung der Compliance-
    Einstufung muss selbst nachvollziehbar sein."""

    name: str = "ConfigChanged"


@dataclass
class CommandDeduplicated(Event):
    name: str = "CommandDeduplicated"


@dataclass
class UnhandledCommand(Event):
    name: str = "UnhandledCommand"


@dataclass
class AuditEvent(Event):
    name: str = "AuditEvent"


@dataclass
class SecurityTripwireTriggered(Event):
    name: str = "SecurityTripwireTriggered"


@dataclass
class PreCommitCheckCompleted(Event):
    name: str = "PreCommitCheckCompleted"


@dataclass
class StartupBlocked(Event):
    name: str = "StartupBlocked"


@dataclass
class ProviderCircuitOpen(Event):
    name: str = "ProviderCircuitOpen"


@dataclass
class CheckpointSaved(Event):
    name: str = "CheckpointSaved"


@dataclass
class LLMCallCompleted(Event):
    name: str = "LLMCallCompleted"


@dataclass
class LockfileChanged(Event):
    """#368 Task 4: ein Lockfile im PR-Diff aenderte den Dependency-Satz.
    Payload: ``added`` / ``removed`` (Paketnamen), ``issue``. Kategorie ``scm``
    -> AI-Act Art. 12 / OWASP agentic_supply_chain (Lieferketten-Sichtbarkeit)."""

    name: str = "LockfileChanged"


@dataclass
class UnresolvedSymbol(Event):
    """#368 Task 3: im Diff importierte Symbole, die gegen keine Quelle
    aufloesbar waren (weder im Diff definiert, noch Generator-Output, noch
    Stdlib/First-Party, noch durch Lockfile/-Diff erklaert) — Halluzinations-
    Verdacht. Payload: ``symbols``, ``owasp_risk`` (LLM09 Misinformation),
    ``issue``. Kategorie ``guard``."""

    name: str = "UnresolvedSymbol"


@dataclass
class QualityCheckCompleted(Event):
    """#153: gemessene LLM-Qualitaet pro (provider, model, task), abgeleitet aus
    dem Eval-Outcome eines Issues. Payload: ``provider``, ``model``, ``task``,
    ``score`` (0..1), ``passed`` (bool), ``criteria`` (dict der Eval-Kriterien),
    ``issue``. Kategorie ``quality`` -> EU-AI-Act Art. 15 (Robustheit/Genauigkeit):
    die kontinuierliche Qualitaetsmessung der eingesetzten Modelle ist Teil der
    Genauigkeits-/Robustheits-Nachweise."""

    name: str = "QualityCheckCompleted"


@dataclass
class HealingFailed(Event):
    name: str = "HealingFailed"


@dataclass
class HealingClassified(Event):
    """Bound gate evidence classified for one optional healing attempt."""

    name: str = "HealingClassified"


@dataclass
class HealingSuggested(Event):
    """#239: Heal-LLM hat einen Korrektur-Vorschlag erzeugt. Workflow-Step
    `HealingSuggested -> Implement` triggert die naechste Implementierungs-
    Runde mit `heal_hint` im Prompt."""

    name: str = "HealingSuggested"


@dataclass
class HealingAttemptStarted(Event):
    """#239: Beginn einer Heal-Runde. Payload: issue, attempt, max_attempts,
    prev_score, failure_type."""

    name: str = "HealingAttemptStarted"


@dataclass
class HealingAttemptCompleted(Event):
    """#239: Heal-Runde abgeschlossen. Payload: issue, attempt, max_attempts,
    prev_score, new_score, score_delta, tokens_used, status (improved/
    no_improvement)."""

    name: str = "HealingAttemptCompleted"


@dataclass
class HealingAborted(Event):
    """Heal-Loop terminiert.

    ``attempts_used`` counts started domain attempts, not provider-internal
    transport retries. ``total_tokens`` contains known completed-response
    usage and remains zero when a provider error returned no usage evidence.
    """

    name: str = "HealingAborted"


@dataclass
class ImplementationFailed(Event):
    name: str = "ImplementationFailed"


@dataclass
class ConfigValidationFailed(Event):
    name: str = "ConfigValidationFailed"


@dataclass
class ProviderFallbackUsed(Event):
    name: str = "ProviderFallbackUsed"


@dataclass
class BranchCreated(Event):
    name: str = "BranchCreated"


@dataclass
class BranchDeleted(Event):
    name: str = "BranchDeleted"


@dataclass
class SkeletonRebuilt(Event):
    name: str = "SkeletonRebuilt"


@dataclass
class QualityRetry(Event):
    name: str = "QualityRetry"


@dataclass
class IssueSkipped(Event):
    name: str = "IssueSkipped"


@dataclass
class HookIntegrityFailed(Event):
    name: str = "HookIntegrityFailed"
