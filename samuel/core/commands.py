from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from samuel.core.evaluation_subject import EvaluationSubject


def _uuid() -> str:
    return str(uuid4())


@dataclass
class Command:
    name: str
    payload: dict = field(default_factory=dict)
    idempotency_key: str | None = None
    correlation_id: str | None = field(default_factory=_uuid)


@dataclass
class ScanIssuesCommand(Command):
    name: str = "ScanIssues"


@dataclass
class PlanIssueCommand(Command):
    name: str = "PlanIssue"
    issue_number: int = 0
    clarification_continuation_authorized: bool = False


@dataclass
class ReplanIssueCommand(Command):
    name: str = "ReplanIssue"
    issue_number: int = 0
    reason: str = ""


@dataclass
class ImplementCommand(Command):
    name: str = "Implement"
    issue_number: int = 0


@dataclass
class CreatePRCommand(Command):
    name: str = "CreatePR"
    issue_number: int = 0
    branch: str = ""
    base: str = "main"
    subject: EvaluationSubject | None = None


@dataclass
class SubmitCandidateCommand(Command):
    """Passively evaluate an immutable candidate already present in SCM."""

    name: str = "SubmitCandidate"
    issue_number: int = 0
    head_sha: str = ""


@dataclass
class RequestCandidateVerificationCommand(Command):
    """Explicitly authorize or recover provider verification for a candidate."""

    name: str = "RequestCandidateVerification"
    issue_number: int = 0
    head_sha: str = ""
    new_request: bool = False


@dataclass
class ScoreCommand(Command):
    name: str = "Score"
    issue_number: int = 0


@dataclass
class EvaluateCommand(Command):
    name: str = "Evaluate"
    issue_number: int = 0


@dataclass
class HealCommand(Command):
    name: str = "Heal"


@dataclass
class ReviewCommand(Command):
    name: str = "Review"


@dataclass
class HealthCheckCommand(Command):
    name: str = "HealthCheck"


@dataclass
class ReloadConfigCommand(Command):
    name: str = "ReloadConfig"


@dataclass
class ShutdownCommand(Command):
    name: str = "Shutdown"


@dataclass
class BuildContextCommand(Command):
    name: str = "BuildContext"


@dataclass
class RunQualityCommand(Command):
    name: str = "RunQuality"


@dataclass
class VerifyACCommand(Command):
    name: str = "VerifyAC"
    subject: EvaluationSubject | None = None


@dataclass
class ChangelogCommand(Command):
    name: str = "Changelog"


@dataclass
class CheckRetentionCommand(Command):
    name: str = "CheckRetention"


@dataclass
class ResumePendingCommand(Command):
    name: str = "ResumePending"


COMMAND_REGISTRY: dict[str, type[Command]] = {
    "ScanIssues": ScanIssuesCommand,
    "PlanIssue": PlanIssueCommand,
    "ReplanIssue": ReplanIssueCommand,
    "Implement": ImplementCommand,
    "CreatePR": CreatePRCommand,
    "SubmitCandidate": SubmitCandidateCommand,
    "RequestCandidateVerification": RequestCandidateVerificationCommand,
    "Score": ScoreCommand,
    "Evaluate": EvaluateCommand,
    "Heal": HealCommand,
    "Review": ReviewCommand,
    "HealthCheck": HealthCheckCommand,
    "ReloadConfig": ReloadConfigCommand,
    "Shutdown": ShutdownCommand,
    "BuildContext": BuildContextCommand,
    "RunQuality": RunQualityCommand,
    "VerifyAC": VerifyACCommand,
    "Changelog": ChangelogCommand,
    "CheckRetention": CheckRetentionCommand,
    "ResumePending": ResumePendingCommand,
}


_PAYLOAD_ALIASES = {"issue": "issue_number", "evaluation_subject": "subject"}


def create_command(name: str, payload: dict | None = None, **kwargs: Any) -> Command:
    cls = COMMAND_REGISTRY.get(name, Command)
    p = payload or {}
    init_fields = {f.name for f in cls.__dataclass_fields__.values()} - {
        "name",
        "payload",
        "idempotency_key",
        "correlation_id",
    }
    extra = {}
    for k in init_fields:
        if k in p:
            extra[k] = p[k]
        else:
            for alias, target in _PAYLOAD_ALIASES.items():
                if target == k and alias in p:
                    extra[k] = p[alias]
                    break
    if cls in {CreatePRCommand, VerifyACCommand} and isinstance(extra.get("subject"), dict):
        extra["subject"] = EvaluationSubject.from_dict(extra["subject"])
    return cls(payload=p, **extra, **kwargs)
