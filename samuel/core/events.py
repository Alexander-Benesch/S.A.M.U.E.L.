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
class PlanPosted(Event):
    name: str = "PlanPosted"


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
class PRCreated(Event):
    name: str = "PRCreated"


@dataclass
class PRMerged(Event):
    """#193: Auto-Merge nach Gates-Pass + create_pr (feature_flag).
    Mapping greift auf bestehende ("scm", "pr_merge")-Eintraege in
    OWASP_RISK_MAP und AI_ACT_ARTICLE_MAP — keine neuen Mapping-Entries."""
    name: str = "PRMerged"


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
class ACVerified(Event):
    """#236: pro erfolgreich verifiziertem Akzeptanzkriterium publisht."""
    name: str = "ACVerified"


@dataclass
class ACFailed(Event):
    """#236: pro fehlgeschlagenem Akzeptanzkriterium publisht."""
    name: str = "ACFailed"


@dataclass
class PlanPreCheckCompleted(Event):
    """#238: Plan-Pre-Check (Skeleton-Validation + AC-Dry-Run + Komplexitaets-
    Score) abgeschlossen. Payload enthaelt structural_score, skeleton_score,
    ac_dry_run_score, blocking_failures, retry_attempt, overall_pass."""
    name: str = "PlanPreCheckCompleted"


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
class ConfigReloaded(Event):
    name: str = "ConfigReloaded"


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
class HealingFailed(Event):
    name: str = "HealingFailed"


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
    """#239: Heal-Loop terminiert. Payload: issue, reason
    (budget_exhausted/no_improvement/token_budget), attempts_used,
    total_tokens."""
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