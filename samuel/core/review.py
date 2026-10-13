"""Closed, subject-bound review decision contract."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from samuel.core.evaluation_subject import EvaluationSubject, RevisionComparison
from samuel.core.types import canonical_digest

ReviewDecisionValue = Literal["pass", "block", "indeterminate"]
ReviewFindingSeverity = Literal["blocker", "suggestion"]

REVIEW_SCHEMA_VERSION = 2
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CODE_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "decision",
        "subject_sha256",
        "diff_sha256",
        "policy",
        "tool",
        "prompt_sha256",
        "findings",
    }
)


def classify_review_contract_error(error: ValueError) -> str:
    """Return a bounded diagnostic class without retaining provider output."""

    message = str(error)
    if message == "review response is not one JSON document":
        return "not_json_document"
    if message.startswith("review response contains duplicate field"):
        return "duplicate_field"
    if "must contain exactly" in message:
        return "closed_schema_mismatch"
    if "belongs to another" in message or "differs from subject" in message:
        return "binding_mismatch"
    if message in {
        "pass review cannot contain blocker findings",
        "block review needs at least one blocker finding",
    }:
        return "decision_findings_mismatch"
    return "field_value_invalid"


def text_digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _canonical_text(value: object, field: str, *, limit: int = 4096) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    result = value.strip()
    if (
        not result
        or result != value
        or len(result) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in result)
    ):
        raise ValueError(f"{field} must be canonical non-empty text")
    return result


def _digest(value: object, field: str) -> str:
    result = _canonical_text(value, field, limit=71)
    if _DIGEST_RE.fullmatch(result) is None:
        raise ValueError(f"{field} must be a sha256 digest")
    return result


def _closed_object(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} must contain exactly {sorted(fields)}")
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"review response contains duplicate field {key!r}")
        result[key] = value
    return result


@dataclass(frozen=True)
class ReviewFinding:
    severity: ReviewFindingSeverity
    code: str
    summary: str

    def __post_init__(self) -> None:
        if self.severity not in {"blocker", "suggestion"}:
            raise ValueError("review finding severity is invalid")
        if len(self.code) > 64 or _CODE_RE.fullmatch(self.code) is None:
            raise ValueError("review finding code is invalid")
        _canonical_text(self.summary, "review finding summary")

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object) -> ReviewFinding:
        row = _closed_object(value, frozenset({"severity", "code", "summary"}), "finding")
        severity = row["severity"]
        if severity not in {"blocker", "suggestion"}:
            raise ValueError("review finding severity is invalid")
        code = row["code"]
        summary = row["summary"]
        if not isinstance(code, str) or not isinstance(summary, str):
            raise ValueError("review finding text fields must be strings")
        return cls(
            severity=severity,  # type: ignore[arg-type]
            code=code,
            summary=summary,
        )


@dataclass(frozen=True)
class ReviewDecision:
    schema_version: int
    decision: ReviewDecisionValue
    subject: EvaluationSubject
    diff_sha256: str
    policy_version: str
    policy_digest: str
    tool_kind: str
    tool_name: str
    prompt_sha256: str
    findings: tuple[ReviewFinding, ...]
    producer_model: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported review schema version")
        if self.decision not in {"pass", "block", "indeterminate"}:
            raise ValueError("invalid review decision")
        _digest(self.diff_sha256, "diff_sha256")
        _canonical_text(self.policy_version, "policy version")
        _digest(self.policy_digest, "policy_digest")
        _canonical_text(self.tool_kind, "tool kind")
        _canonical_text(self.tool_name, "tool name")
        _digest(self.prompt_sha256, "prompt_sha256")
        if self.producer_model:
            _canonical_text(self.producer_model, "producer model", limit=256)
        if self.policy_version != self.subject.policy_version:
            raise ValueError("review policy version differs from subject")
        if self.policy_digest != self.subject.policy_digest:
            raise ValueError("review policy digest differs from subject")
        blocker_count = sum(item.severity == "blocker" for item in self.findings)
        if self.decision == "pass" and blocker_count:
            raise ValueError("pass review cannot contain blocker findings")
        if self.decision == "block" and not blocker_count:
            raise ValueError("block review needs at least one blocker finding")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision,
            "subject_sha256": canonical_digest(self.subject.as_dict()),
            "diff_sha256": self.diff_sha256,
            "policy": {
                "version": self.policy_version,
                "digest": self.policy_digest,
            },
            "tool": {"kind": self.tool_kind, "name": self.tool_name},
            "prompt_sha256": self.prompt_sha256,
            "findings": [item.as_dict() for item in self.findings],
            "producer_model": self.producer_model,
        }


def parse_review_decision(
    raw: str,
    *,
    expected_subject: EvaluationSubject,
    expected_diff_sha256: str,
    expected_prompt_sha256: str,
    expected_tool_kind: str,
    expected_tool_name: str,
    producer_model: str = "",
) -> ReviewDecision:
    """Parse one closed JSON document and verify every authority binding."""

    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ValueError("review response is not one JSON document") from exc
    document = _closed_object(value, _TOP_LEVEL_FIELDS, "review decision")
    if type(document["schema_version"]) is not int:
        raise ValueError("review schema version is invalid")
    policy = _closed_object(document["policy"], frozenset({"version", "digest"}), "policy")
    tool = _closed_object(document["tool"], frozenset({"kind", "name"}), "tool")
    findings_raw = document["findings"]
    if not isinstance(findings_raw, list) or len(findings_raw) > 100:
        raise ValueError("review findings must be a bounded list")
    decision_value = document["decision"]
    if decision_value not in {"pass", "block", "indeterminate"}:
        raise ValueError("invalid review decision")
    string_fields = {
        "subject_sha256": document["subject_sha256"],
        "diff_sha256": document["diff_sha256"],
        "policy.version": policy["version"],
        "policy.digest": policy["digest"],
        "tool.kind": tool["kind"],
        "tool.name": tool["name"],
        "prompt_sha256": document["prompt_sha256"],
    }
    if any(not isinstance(item, str) for item in string_fields.values()):
        raise ValueError("review decision text fields must be strings")
    subject_sha256 = _digest(document["subject_sha256"], "subject_sha256")
    if subject_sha256 != canonical_digest(expected_subject.as_dict()):
        raise ValueError("review decision belongs to another evaluation subject")
    decision = ReviewDecision(
        schema_version=document["schema_version"],
        decision=decision_value,  # type: ignore[arg-type]
        subject=expected_subject,
        diff_sha256=document["diff_sha256"],
        policy_version=policy["version"],
        policy_digest=policy["digest"],
        tool_kind=tool["kind"],
        tool_name=tool["name"],
        prompt_sha256=document["prompt_sha256"],
        findings=tuple(ReviewFinding.from_dict(item) for item in findings_raw),
        producer_model=producer_model,
    )
    if decision.diff_sha256 != expected_diff_sha256:
        raise ValueError("review decision belongs to another diff")
    if decision.prompt_sha256 != expected_prompt_sha256:
        raise ValueError("review decision belongs to another prompt")
    if (decision.tool_kind, decision.tool_name) != (expected_tool_kind, expected_tool_name):
        raise ValueError("review decision belongs to another tool contract")
    return decision


def render_change_context(
    *, title: str, context: str, comparison: RevisionComparison, subject: EvaluationSubject
) -> str:
    """Render SCM facts for humans; this is not a review decision or new claim."""
    from samuel.core.bus import scrub_secrets

    if (comparison.repository, comparison.base_sha, comparison.head_sha) != (
        subject.repository,
        subject.base_sha,
        subject.head_sha,
    ):
        raise ValueError("change comparison is not bound to the candidate")
    safe_title = scrub_secrets(" ".join(title.split()))[:300]
    safe_context = scrub_secrets(context).strip()[:1200]
    diff = scrub_secrets(comparison.diff)
    excerpt = "\n".join(diff.splitlines()[:60])[:6000]
    lines = [
        f"Thema: {safe_title}",
        "",
        "### Auftragskontext",
        *(f"> {line}" for line in safe_context.splitlines()),
        "",
        "### Tatsächliche Änderung gegenüber der freigegebenen Base",
        *(f"- `{scrub_secrets(path)}`" for path in comparison.changed_files),
        "",
        "Der folgende redigierte Ausschnitt zeigt entfernte (`-`) und "
        "hinzugefügte (`+`) Zeilen. Den vollständigen Vergleich enthält der PR.",
        "",
        *("    " + line for line in excerpt.splitlines()),
        "",
        f"Candidate: `{subject.head_sha}`.",
    ]
    return "\n".join(lines)
