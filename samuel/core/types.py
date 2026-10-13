from __future__ import annotations

import hashlib
import html as _html_mod
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal, SupportsInt

from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.gate_metadata import GATE_STATUSES, GateAuthority, GateStatus


@dataclass
class Label:
    id: int
    name: str


@dataclass
class Issue:
    number: int
    title: str
    body: str
    state: str
    labels: list[Label] = field(default_factory=list)


@dataclass
class Comment:
    id: int
    body: str
    user: str
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SCMLabelEvent:
    """One provider-normalized label transition with attributable SCM evidence."""

    source_id: str
    label: str
    actor: str
    actor_type: str
    timestamp: str
    operation: str = "add"

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", canonical_scm_timestamp(self.timestamp))


@dataclass
class PR:
    id: int
    number: int
    title: str
    html_url: str
    state: str = "open"
    merged: bool = False


@dataclass(frozen=True)
class SCMActivity:
    """Provider-neutral repository activity returned by SCM polling ports."""

    event: str
    number: int
    timestamp: str
    title: str = ""
    url: str = ""
    actor: str = ""
    actor_type: str = "human"
    object_id: int | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", canonical_scm_timestamp(self.timestamp))

    @property
    def activity_id(self) -> str:
        discriminator = self.object_id if self.object_id not in (None, "") else self.number
        return f"{self.event}:{discriminator}:{self.timestamp}"


def canonical_scm_timestamp(value: str) -> str:
    """Canonical UTC form so webhook and polling facts share the same ID."""

    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def scm_timestamp_at_or_after(value: str, boundary: str) -> bool:
    """Compare two valid SCM timestamps; malformed or missing values fail closed."""

    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        lower_bound = datetime.fromisoformat(boundary.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    if lower_bound.tzinfo is None:
        lower_bound = lower_bound.replace(tzinfo=timezone.utc)
    return observed.astimezone(timezone.utc) >= lower_bound.astimezone(timezone.utc)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    stop_reason: str = "end_turn"
    model_used: str = ""
    latency_ms: int = 0
    # False means the provider returned content without trustworthy usage
    # counters.  A cumulative workflow budget must then retain its complete
    # pre-call reservation instead of treating zeroes as free usage.
    usage_reported: bool = True
    # #335: bei strukturiertem Output (JSON-Mode) die geparste JSON-Struktur;
    # ``None`` wenn der Provider Freitext lieferte.
    structured: dict | None = None


TRUNCATED_STOP_REASONS = frozenset({"length", "max_tokens", "token_limit"})


def is_truncated_stop_reason(reason: str | None) -> bool:
    """Normalize provider-specific output-token-limit stop reasons."""

    return str(reason or "").strip().lower() in TRUNCATED_STOP_REASONS


@dataclass
class GateContext:
    issue_number: int
    branch: str
    changed_files: list[str]
    diff: str
    plan_comment: str | None = None
    pr_url: str | None = None
    project_root: Path | None = None
    path_risk_configured: bool = False
    subject: EvaluationSubject | None = None
    correlation_id: str = ""
    max_quality_file_bytes: int = 1_000_000
    read_candidate_file: Callable[[str], str | None] | None = None
    acceptance_evidence: dict | None = None
    acceptance_contract: dict | None = None
    architecture_policy: dict | None = None


@dataclass
class GateResult:
    gate: int | str
    passed: bool | None
    reason: str
    owasp_risk: str | None = None
    subject: EvaluationSubject | None = None
    executed: bool = True
    status: GateStatus | None = None
    reason_code: str | None = None
    authority: GateAuthority | None = None
    tool: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status is None:
            self.status = "passed" if self.passed is True else "failed"
        if self.status not in GATE_STATUSES:
            raise ValueError(f"unsupported gate status: {self.status}")
        if self.reason_code is None:
            gate_code = "".join(
                char if char.isalnum() else "_" for char in str(self.gate).lower()
            ).strip("_")
            self.reason_code = f"gate_{gate_code}_{self.status}"
        if self.authority not in {None, "required", "optional"}:
            raise ValueError(f"unsupported gate authority: {self.authority}")
        if not self.executed:
            if self.passed is not None or self.status != "skipped_precondition":
                raise ValueError(
                    "a non-executed gate must be skipped_precondition with passed=None"
                )
            return
        if self.passed is None:
            raise ValueError("an executed gate must have a boolean result")
        if self.status == "skipped_precondition":
            raise ValueError("skipped_precondition cannot be marked executed")
        if self.status in {"passed", "not_applicable"} and self.passed is not True:
            raise ValueError(f"{self.status} gate evidence must carry passed=True")
        if (
            self.status
            in {
                "failed",
                "error",
                "missing_evidence",
                "manual_pending",
                "not_evaluated",
            }
            and self.passed is not False
        ):
            raise ValueError(f"{self.status} gate evidence must carry passed=False")


@dataclass
class AuditQuery:
    issue: int | None = None
    correlation_id: str | None = None
    owasp_risk: str | None = None
    event_name: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 100


@dataclass
class SkeletonEntry:
    name: str
    kind: str
    file: str
    line_start: int
    line_end: int
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    language: str = ""


@dataclass
class HealCommand:
    issue: int
    failure_type: str
    context: dict = field(default_factory=dict)
    attempt: int = 1


@dataclass
class WorkflowCheckpoint:
    issue: int
    phase: str
    step: str
    state: dict = field(default_factory=dict)


def safe_int(value: object, default: int = 0) -> int:
    try:
        if isinstance(value, (str, bytes, bytearray, SupportsInt)):
            return int(value)
        return default
    except (TypeError, ValueError):
        return default


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def strip_html(text: str) -> str:
    if not isinstance(text, str):
        return str(text) if text else ""
    if "<" not in text:
        return _html_mod.unescape(text).strip() if "&" in text else text
    parts: list[str] = []

    class _S(HTMLParser):
        def handle_data(self, data: str) -> None:
            parts.append(data)

    _S().feed(text)
    return _html_mod.unescape("".join(parts)).strip()


_COMMENT_REQUIRED_FIELDS: dict[str, list[str]] = {
    "plan": ["## Analyse", "## Plan", "## Risiko"],
    "completion": ["## Änderungen", "## Tests"],
    "review": ["## Review"],
}


def validate_comment(
    body: str,
    comment_type: str,
    *,
    required_fields: dict[str, list[str]] | None = None,
) -> list[str]:
    fields = (required_fields or _COMMENT_REQUIRED_FIELDS).get(comment_type, [])
    return [f for f in fields if f.lower() not in body.lower()]


# Bound execution-provider domain contracts (#679).
VERIFICATION_REQUEST_SCHEMA = "verification-request.v1"
PROVIDER_RUN_SCHEMA = "provider-run.v1"
PROVIDER_EVIDENCE_SCHEMA = "provider-acceptance-evidence.v1"

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUEST_KEY_RE = re.compile(r"^verification:sha256:[0-9a-f]{64}$")
_FULL_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _text(value: object, field: str, *, limit: int = 4096) -> str:
    result = str(value).strip()
    if (
        not result
        or len(result) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in result)
    ):
        raise ValueError(f"{field} must be a canonical non-empty string")
    return result


def _digest(value: object, field: str) -> str:
    result = str(value).strip().lower()
    if not _DIGEST_RE.fullmatch(result):
        raise ValueError(f"{field} must be a sha256 digest")
    return result


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class VerificationAuthority:
    """Exact SCM approval and plan instance that authorized one request."""

    issue_number: int
    plan_comment_id: int
    contract_hash: str
    approval_source_id: str
    approval_actor: str
    approval_method: str

    def __post_init__(self) -> None:
        if isinstance(self.issue_number, bool) or self.issue_number <= 0:
            raise ValueError("issue_number must be positive")
        if isinstance(self.plan_comment_id, bool) or self.plan_comment_id <= 0:
            raise ValueError("plan_comment_id must be positive")
        object.__setattr__(self, "contract_hash", _digest(self.contract_hash, "contract_hash"))
        object.__setattr__(
            self,
            "approval_source_id",
            _text(self.approval_source_id, "approval_source_id"),
        )
        object.__setattr__(self, "approval_actor", _text(self.approval_actor, "approval_actor"))
        object.__setattr__(self, "approval_method", _text(self.approval_method, "approval_method"))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> VerificationAuthority:
        return cls(
            issue_number=_positive_int(value.get("issue_number"), "issue_number"),
            plan_comment_id=_positive_int(value.get("plan_comment_id"), "plan_comment_id"),
            contract_hash=str(value.get("contract_hash", "")),
            approval_source_id=str(value.get("approval_source_id", "")),
            approval_actor=str(value.get("approval_actor", "")),
            approval_method=str(value.get("approval_method", "")),
        )


@dataclass(frozen=True)
class VerificationCriterion:
    criterion_id: str
    tag: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_id", _text(self.criterion_id, "criterion_id"))
        object.__setattr__(self, "tag", _text(self.tag, "criterion_tag").upper())
        object.__setattr__(self, "text", _text(self.text, "criterion_text"))

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> VerificationCriterion:
        return cls(
            criterion_id=str(value.get("criterion_id", "")),
            tag=str(value.get("tag", "")),
            text=str(value.get("text", "")),
        )


@dataclass(frozen=True)
class VerificationRequest:
    """Immutable authority record written before provider dispatch."""

    request_key: str
    request_nonce: str
    authorized_at: str
    subject: EvaluationSubject
    authority: VerificationAuthority
    criteria: tuple[VerificationCriterion, ...]
    policy_binding: dict[str, Any]
    provider_profile: str
    provider_profile_digest: str
    consumer_mode: Literal["passive_candidate", "reference_worker"]
    schema: str = VERIFICATION_REQUEST_SCHEMA
    purpose: Literal["acceptance_verification"] = "acceptance_verification"
    mutation_authority: Literal["none"] = "none"

    def __post_init__(self) -> None:
        if self.schema != VERIFICATION_REQUEST_SCHEMA:
            raise ValueError("unsupported verification request schema")
        if self.purpose != "acceptance_verification" or self.mutation_authority != "none":
            raise ValueError("verification request authority fields are invalid")
        if not _REQUEST_KEY_RE.fullmatch(self.request_key):
            raise ValueError("request_key is invalid")
        object.__setattr__(self, "request_nonce", _text(self.request_nonce, "request_nonce"))
        object.__setattr__(self, "authorized_at", _text(self.authorized_at, "authorized_at"))
        if self.authority.issue_number <= 0:
            raise ValueError("verification authority is invalid")
        if self.authority.contract_hash != self.subject.contract_hash:
            raise ValueError("verification authority differs from subject contract")
        if not self.criteria:
            raise ValueError("verification request needs acceptance criteria")
        ids = [item.criterion_id for item in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("verification request criterion ids must be unique")
        if not isinstance(self.policy_binding, dict) or not self.policy_binding:
            raise ValueError("verification request needs a policy binding")
        object.__setattr__(
            self, "provider_profile", _text(self.provider_profile, "provider_profile")
        )
        if self.consumer_mode not in {"passive_candidate", "reference_worker"}:
            raise ValueError("verification request consumer mode is invalid")
        object.__setattr__(
            self,
            "provider_profile_digest",
            _digest(self.provider_profile_digest, "provider_profile_digest"),
        )
        expected = self.derive_key(
            request_nonce=self.request_nonce,
            authorized_at=self.authorized_at,
            subject=self.subject,
            authority=self.authority,
            criteria=self.criteria,
            policy_binding=self.policy_binding,
            provider_profile=self.provider_profile,
            provider_profile_digest=self.provider_profile_digest,
            consumer_mode=self.consumer_mode,
        )
        if self.request_key != expected:
            raise ValueError("verification request key does not match its binding")

    @staticmethod
    def derive_key(
        *,
        request_nonce: str,
        authorized_at: str,
        subject: EvaluationSubject,
        authority: VerificationAuthority,
        criteria: tuple[VerificationCriterion, ...],
        policy_binding: dict[str, Any],
        provider_profile: str,
        provider_profile_digest: str,
        consumer_mode: Literal["passive_candidate", "reference_worker"],
    ) -> str:
        digest = canonical_digest(
            {
                "schema": VERIFICATION_REQUEST_SCHEMA,
                "purpose": "acceptance_verification",
                "request_nonce": request_nonce,
                "authorized_at": authorized_at,
                "subject": subject.as_dict(),
                "authority": authority.as_dict(),
                "criteria": [item.as_dict() for item in criteria],
                "policy_binding": policy_binding,
                "provider_profile": provider_profile,
                "provider_profile_digest": provider_profile_digest,
                "consumer_mode": consumer_mode,
            }
        )
        return f"verification:{digest}"

    @classmethod
    def build(
        cls,
        *,
        request_nonce: str,
        authorized_at: str,
        subject: EvaluationSubject,
        authority: VerificationAuthority,
        criteria: tuple[VerificationCriterion, ...],
        policy_binding: dict[str, Any],
        provider_profile: str,
        provider_profile_digest: str,
        consumer_mode: Literal["passive_candidate", "reference_worker"],
    ) -> VerificationRequest:
        return cls(
            request_key=cls.derive_key(
                request_nonce=request_nonce,
                authorized_at=authorized_at,
                subject=subject,
                authority=authority,
                criteria=criteria,
                policy_binding=policy_binding,
                provider_profile=provider_profile,
                provider_profile_digest=provider_profile_digest,
                consumer_mode=consumer_mode,
            ),
            request_nonce=request_nonce,
            authorized_at=authorized_at,
            subject=subject,
            authority=authority,
            criteria=criteria,
            policy_binding=policy_binding,
            provider_profile=provider_profile,
            provider_profile_digest=provider_profile_digest,
            consumer_mode=consumer_mode,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "purpose": self.purpose,
            "request_key": self.request_key,
            "request_nonce": self.request_nonce,
            "authorized_at": self.authorized_at,
            "subject": self.subject.as_dict(),
            "authority": self.authority.as_dict(),
            "criteria": [item.as_dict() for item in self.criteria],
            "policy_binding": self.policy_binding,
            "provider_profile": self.provider_profile,
            "provider_profile_digest": self.provider_profile_digest,
            "consumer_mode": self.consumer_mode,
            "mutation_authority": self.mutation_authority,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> VerificationRequest:
        if value.get("purpose") != "acceptance_verification":
            raise ValueError("unsupported verification request purpose")
        if value.get("mutation_authority") != "none":
            raise ValueError("verification request may not carry mutation authority")
        criteria = value.get("criteria")
        if not isinstance(criteria, list) or any(not isinstance(item, dict) for item in criteria):
            raise ValueError("verification request criteria are invalid")
        policy = value.get("policy_binding")
        if not isinstance(policy, dict):
            raise ValueError("verification request policy binding is invalid")
        authority = value.get("authority")
        subject = value.get("subject")
        if not isinstance(authority, dict) or not isinstance(subject, dict):
            raise ValueError("verification request authority binding is invalid")
        return cls(
            schema=str(value.get("schema", "")),
            request_key=str(value.get("request_key", "")),
            request_nonce=str(value.get("request_nonce", "")),
            authorized_at=str(value.get("authorized_at", "")),
            subject=EvaluationSubject.from_dict(subject),
            authority=VerificationAuthority.from_dict(authority),
            criteria=tuple(VerificationCriterion.from_dict(item) for item in criteria),
            policy_binding=policy,
            provider_profile=str(value.get("provider_profile", "")),
            provider_profile_digest=str(value.get("provider_profile_digest", "")),
            consumer_mode=str(value.get("consumer_mode", "")),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class ProviderRunReference:
    provider: str
    repository: str
    run_id: str
    attempt: int
    request_key: str
    schema: str = PROVIDER_RUN_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROVIDER_RUN_SCHEMA:
            raise ValueError("unsupported provider run schema")
        object.__setattr__(self, "provider", _text(self.provider, "provider").lower())
        object.__setattr__(self, "repository", _text(self.repository, "repository"))
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        if isinstance(self.attempt, bool) or self.attempt <= 0:
            raise ValueError("attempt must be positive")
        if not _REQUEST_KEY_RE.fullmatch(self.request_key):
            raise ValueError("provider run request key is invalid")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ProviderRunReference:
        return cls(
            schema=str(value.get("schema", "")),
            provider=str(value.get("provider", "")),
            repository=str(value.get("repository", "")),
            run_id=str(value.get("run_id", "")),
            attempt=_positive_int(value.get("attempt"), "attempt"),
            request_key=str(value.get("request_key", "")),
        )


DispatchState = Literal["accepted", "unknown", "proven_absent", "rejected"]


@dataclass(frozen=True)
class ProviderDispatchResult:
    state: DispatchState
    reference: ProviderRunReference | None = None
    reason_code: str = ""

    def __post_init__(self) -> None:
        if self.state not in {"accepted", "unknown", "proven_absent", "rejected"}:
            raise ValueError("invalid provider dispatch state")
        if self.state == "accepted" and self.reference is None:
            raise ValueError("accepted provider dispatch needs a run reference")
        if self.state != "accepted" and self.reference is not None:
            raise ValueError("non-accepted provider dispatch may not claim a run")
        if self.state != "accepted":
            object.__setattr__(self, "reason_code", _text(self.reason_code, "reason_code"))


@dataclass(frozen=True)
class ProviderCriterionEvidence:
    criterion_id: str
    tag: str
    status: Literal["passed", "failed", "missing_evidence", "error"]
    reason: str
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_id", _text(self.criterion_id, "criterion_id"))
        object.__setattr__(self, "tag", _text(self.tag, "criterion_tag").upper())
        if self.status not in {"passed", "failed", "missing_evidence", "error"}:
            raise ValueError("invalid provider criterion status")
        object.__setattr__(self, "reason", _text(self.reason, "criterion_reason"))
        object.__setattr__(
            self, "evidence_digest", _digest(self.evidence_digest, "evidence_digest")
        )

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ProviderCriterionEvidence:
        return cls(
            criterion_id=str(value.get("criterion_id", "")),
            tag=str(value.get("tag", "")),
            status=str(value.get("status", "")),  # type: ignore[arg-type]
            reason=str(value.get("reason", "")),
            evidence_digest=str(value.get("evidence_digest", "")),
        )


@dataclass(frozen=True)
class ProviderEvidence:
    request_key: str
    subject: EvaluationSubject
    reference: ProviderRunReference
    provider_profile_digest: str
    workflow_digest: str
    tool_digest: str
    environment_digest: str
    issuer: str
    issued_at: str
    expires_at: str
    nonce: str
    criteria: tuple[ProviderCriterionEvidence, ...]
    integrity: dict[str, Any]
    schema: str = PROVIDER_EVIDENCE_SCHEMA
    mutation_authority: Literal["none"] = "none"

    def __post_init__(self) -> None:
        if self.schema != PROVIDER_EVIDENCE_SCHEMA:
            raise ValueError("unsupported provider evidence schema")
        if self.mutation_authority != "none":
            raise ValueError("provider evidence may not carry mutation authority")
        if not _REQUEST_KEY_RE.fullmatch(self.request_key):
            raise ValueError("provider evidence request key is invalid")
        if self.reference.request_key != self.request_key:
            raise ValueError("provider evidence run differs from request")
        for digest_field in (
            "provider_profile_digest",
            "workflow_digest",
            "tool_digest",
            "environment_digest",
        ):
            object.__setattr__(
                self,
                digest_field,
                _digest(getattr(self, digest_field), digest_field),
            )
        for text_field in ("issuer", "issued_at", "expires_at", "nonce"):
            object.__setattr__(
                self,
                text_field,
                _text(getattr(self, text_field), text_field),
            )
        if not self.criteria:
            raise ValueError("provider evidence needs criterion results")
        ids = [item.criterion_id for item in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("provider criterion ids must be unique")
        if not isinstance(self.integrity, dict) or not self.integrity:
            raise ValueError("provider evidence needs an integrity proof")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_key": self.request_key,
            "subject": self.subject.as_dict(),
            "reference": self.reference.as_dict(),
            "provider_profile_digest": self.provider_profile_digest,
            "workflow_digest": self.workflow_digest,
            "tool_digest": self.tool_digest,
            "environment_digest": self.environment_digest,
            "issuer": self.issuer,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "criteria": [item.as_dict() for item in self.criteria],
            "mutation_authority": self.mutation_authority,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "integrity": self.integrity}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ProviderEvidence:
        if value.get("mutation_authority") != "none":
            raise ValueError("provider evidence may not carry mutation authority")
        subject = value.get("subject")
        reference = value.get("reference")
        criteria = value.get("criteria")
        integrity = value.get("integrity")
        if (
            not isinstance(subject, dict)
            or not isinstance(reference, dict)
            or not isinstance(criteria, list)
            or any(not isinstance(item, dict) for item in criteria)
            or not isinstance(integrity, dict)
        ):
            raise ValueError("provider evidence has an invalid shape")
        return cls(
            schema=str(value.get("schema", "")),
            request_key=str(value.get("request_key", "")),
            subject=EvaluationSubject.from_dict(subject),
            reference=ProviderRunReference.from_dict(reference),
            provider_profile_digest=str(value.get("provider_profile_digest", "")),
            workflow_digest=str(value.get("workflow_digest", "")),
            tool_digest=str(value.get("tool_digest", "")),
            environment_digest=str(value.get("environment_digest", "")),
            issuer=str(value.get("issuer", "")),
            issued_at=str(value.get("issued_at", "")),
            expires_at=str(value.get("expires_at", "")),
            nonce=str(value.get("nonce", "")),
            criteria=tuple(ProviderCriterionEvidence.from_dict(item) for item in criteria),
            integrity=integrity,
        )

    @property
    def evidence_digest(self) -> str:
        return canonical_digest(self.as_dict())


@dataclass(frozen=True)
class VerificationProgress:
    request: VerificationRequest
    status: Literal["dispatch_unknown", "running", "evidence_ready", "blocked"]
    reason_code: str
    reference: ProviderRunReference | None = None
    evidence: ProviderEvidence | None = None

    @property
    def pending(self) -> bool:
        return self.status in {"dispatch_unknown", "running"}


class ExecutionProviderError(RuntimeError):
    """Safe provider failure with an operator-facing reason code."""

    def __init__(self, code: str, message: str):
        self.code = _text(code, "provider_error_code")
        self.safe_message = _text(message, "provider_error_message")
        super().__init__(self.safe_message)
