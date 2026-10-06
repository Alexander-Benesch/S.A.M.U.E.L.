"""Slice-neutral acceptance-contract and evidence types.

The issue plan remains the single source of acceptance criteria.  This module
only gives that existing text a stable, auditable representation; it does not
introduce a second contract store.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.state import AuthorityRecord, StateStoreError
from samuel.core.types import Comment, Issue, scm_timestamp_at_or_after

if TYPE_CHECKING:
    from samuel.core.ports import IAuthorityStateStore, IVersionControl

AcceptanceStatus = Literal[
    "passed",
    "failed",
    "manual_pending",
    "not_applicable",
    "missing_evidence",
    "error",
]

ACCEPTANCE_STATUSES = frozenset(
    {
        "passed",
        "failed",
        "manual_pending",
        "not_applicable",
        "missing_evidence",
        "error",
    }
)

_CRITERION_RE = re.compile(r"^\s*-\s*\[([^\]])\]\s*\[([A-Z:]+)\]\s*(.+?)\s*$", re.MULTILINE)
_REVISION_RE = re.compile(
    r"^\s*(?:Acceptance-Contract-Revision|Contract-Revision)\s*:\s*([A-Za-z0-9._-]+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHECKBOX_RE = re.compile(r"^(\s*-\s*)\[[^\]]\](\s*\[[A-Z:]+\])", re.MULTILINE)
_SCOPE_HEADING_RE = re.compile(r"^###\s+(?:Änderungsscope|Change Scope)\s*$", re.MULTILINE)
_SCOPE_SCHEMA_RE = re.compile(r"^Scope-Schema:\s*([0-9]+)\s*$", re.MULTILINE)
_SCOPE_EXPANSION_RE = re.compile(
    r"^Architecture-Expansion:\s*(disabled|allowed)\s*$",
    re.MULTILINE,
)
_SCOPE_ENTRY_RE = re.compile(r"^-\s+\[(FILE|PATH)\]\s+`([^`]+)`\s*$", re.MULTILINE)
_GREP_TAGS = frozenset({"GREP", "GREP:NOT"})
_CRITERION_DESCRIPTION_SEPARATORS = (" — ", " – ", " : ", " -- ")
_SAFE_TEST_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_:.\-]*$")
_SAFE_PYTEST_NODE_ID_RE = re.compile(r"^[a-zA-Z0-9_./-]+\.py(?:::[a-zA-Z0-9_.\[\]-]+)+$")


def _canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def canonical_acceptance_source(plan_text: str) -> str:
    """Canonical plan text with presentation-only checkbox state removed."""

    source = plan_text
    if source.lstrip().startswith("## Plan für Issue #"):
        status_end = source.find("\n\n", source.find("**Status:**"))
        if status_end >= 0:
            source = source[status_end + 2 :]
        # The published wrapper always appends its metadata separator after
        # the complete plan.  Plans may legitimately contain Markdown
        # separators themselves, including as their final line, so only the
        # last separator can delimit the system-owned footer.
        metadata_start = source.rfind("\n\n---\n")
        if metadata_start >= 0:
            source = source[:metadata_start]
    return _canonical_text(_CHECKBOX_RE.sub(r"\1[ ]\2", source))


def parse_grep_criterion_argument(value: str) -> str:
    """Return the repository-wide GREP pattern or reject ambiguous suffixes.

    GREP has no path argument. A quoted pattern may only be followed by an
    explicit prose separator; otherwise text such as ``"pattern" file.py``
    would look path-bound while the verifier silently searches the repository.
    Historical unquoted multi-word patterns remain one complete pattern.
    """

    text = value.strip()
    if not text:
        raise ValueError("GREP criterion needs a non-empty pattern")

    if text[0] in {'"', "'", "`"}:
        delimiter = text[0]
        closing = text.find(delimiter, 1)
        if closing < 0:
            raise ValueError("GREP delimited pattern is not closed")
        pattern = text[1:closing]
        remainder = text[closing + 1 :]
        if remainder and not any(
            remainder.startswith(separator) and remainder[len(separator) :].strip()
            for separator in _CRITERION_DESCRIPTION_SEPARATORS
        ):
            if delimiter in {'"', "'"} and f"\\{delimiter}" in text:
                raise ValueError(
                    "GREP quoted patterns do not support escaped delimiters; "
                    "wrap a pattern containing double quotes in single quotes "
                    "(or vice versa), or use a focused TEST criterion"
                )
            raise ValueError(
                "GREP does not support a path or other suffix after the pattern; "
                "use an explicit description separator or a focused TEST criterion"
            )
    else:
        separator_positions = [
            (text.find(separator), separator)
            for separator in _CRITERION_DESCRIPTION_SEPARATORS
            if text.find(separator) >= 0
        ]
        if separator_positions:
            position, separator = min(separator_positions, key=lambda item: item[0])
            pattern = text[:position]
            if not text[position + len(separator) :].strip():
                raise ValueError("GREP description separator needs a description")
        else:
            pattern = text

    if not pattern.strip():
        raise ValueError("GREP criterion needs a non-empty pattern")
    return pattern


def parse_test_criterion_argument(value: str) -> str:
    """Return one verifier-safe test selector from a TEST criterion.

    Only a logical test name or a pytest node id with at least one ``::``
    component is portable to the existing controlled runner boundary. A bare
    file path must not be presented for approval as executable evidence.
    """

    rest = value.strip()
    for separator in _CRITERION_DESCRIPTION_SEPARATORS:
        position = rest.find(separator)
        if position >= 0:
            rest = rest[:position].strip()
            break
    test_name = rest
    if "::" in test_name:
        path_text = test_name.split("::", 1)[0]
        path = PurePosixPath(path_text)
        if (
            not _SAFE_PYTEST_NODE_ID_RE.fullmatch(test_name)
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path_text.split("/"))
        ):
            raise ValueError(f"pytest node id rejected: {test_name or value}")
    elif not _SAFE_TEST_NAME_RE.fullmatch(test_name):
        raise ValueError(f"test name rejected: {test_name or value}")
    return test_name


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_MARKER_RE = re.compile(r"<!-- samuel-source-snapshot: (\{[^\r\n]*\}) -->")
_REVOCATION_MARKER_RE = re.compile(r"<!-- samuel-plan-revocation: (\{[^\r\n]*\}) -->")
_AUTHORITATIVE_PLAN_HEADING_RE = re.compile(r"^## Plan(?: für Issue #[0-9]+)?\s*$", re.MULTILINE)


def issue_revision_digest(*, number: int, title: str, body: str) -> str:
    """Identify the exact issue requirements used to build a plan."""

    return _digest({"number": int(number), "title": str(title), "body": str(body)})


@dataclass(frozen=True)
class PlanningSourceSnapshot:
    """System-owned identity of the repository and issue planning inputs."""

    schema_version: int
    repository: str
    base_ref: str
    base_sha: str
    issue_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported planning source schema")
        if not self.repository or any(char.isspace() for char in self.repository):
            raise ValueError("planning source needs a canonical repository identity")
        if "-->" in self.repository:
            raise ValueError("invalid repository identity")
        if (
            not self.base_ref
            or any(char.isspace() or ord(char) < 32 for char in self.base_ref)
            or ".." in self.base_ref
            or "//" in self.base_ref
            or self.base_ref.endswith(("/", ".lock"))
        ):
            raise ValueError("planning source needs a canonical base ref")
        if not _SHA_RE.fullmatch(self.base_sha):
            raise ValueError("planning source needs a full lowercase commit SHA")
        if not _DIGEST_RE.fullmatch(self.issue_digest):
            raise ValueError("planning source needs a canonical issue digest")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PlanningSourceSnapshot:
        return cls(
            schema_version=int(value.get("schema_version", 0)),
            repository=str(value.get("repository", "")),
            base_ref=str(value.get("base_ref", "")),
            base_sha=str(value.get("base_sha", "")),
            issue_digest=str(value.get("issue_digest", "")),
        )


def render_planning_source(snapshot: PlanningSourceSnapshot) -> str:
    """Render one machine-readable, non-authoritative presentation marker."""

    payload = json.dumps(
        snapshot.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"<!-- samuel-source-snapshot: {payload} -->"


def parse_planning_source(text: str) -> PlanningSourceSnapshot | None:
    """Parse exactly one system-owned source marker from a plan comment."""

    matches = _SOURCE_MARKER_RE.findall(text)
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("plan contains multiple planning source snapshots")
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise ValueError("invalid planning source snapshot") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid planning source snapshot")
    return PlanningSourceSnapshot.from_dict(value)


@dataclass(frozen=True)
class PlanRevocation:
    """Immutable SCM evidence that one concrete plan comment is no longer active."""

    schema_version: int
    plan_comment_id: int
    contract_hash: str
    reason_digest: str
    revoked_at: str
    actor: str
    method: str = "samuel replan"

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.plan_comment_id <= 0:
            raise ValueError("invalid plan revocation identity")
        if not _DIGEST_RE.fullmatch(self.contract_hash):
            raise ValueError("invalid revoked contract hash")
        if not _DIGEST_RE.fullmatch(self.reason_digest):
            raise ValueError("invalid replan reason digest")
        if not self.revoked_at or not self.actor or not self.method:
            raise ValueError("plan revocation needs time, actor and method")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PlanRevocation:
        return cls(
            schema_version=int(value.get("schema_version", 0)),
            plan_comment_id=int(value.get("plan_comment_id", 0)),
            contract_hash=str(value.get("contract_hash", "")),
            reason_digest=str(value.get("reason_digest", "")),
            revoked_at=str(value.get("revoked_at", "")),
            actor=str(value.get("actor", "")),
            method=str(value.get("method", "")),
        )


def text_digest(value: str) -> str:
    """Return the canonical digest used for an operator supplied replan reason."""

    return _digest({"text": _canonical_text(value)})


def render_plan_revocation(revocation: PlanRevocation) -> str:
    payload = json.dumps(
        revocation.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return f"<!-- samuel-plan-revocation: {payload} -->"


def parse_plan_revocations(text: str) -> tuple[PlanRevocation, ...]:
    revocations: list[PlanRevocation] = []
    for raw in _REVOCATION_MARKER_RE.findall(text):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid plan revocation marker") from exc
        if not isinstance(value, dict):
            raise ValueError("invalid plan revocation marker")
        revocations.append(PlanRevocation.from_dict(value))
    return tuple(revocations)


def _canonical_scope_path(value: str, *, kind: Literal["file", "path"]) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if (
        not normalized
        or normalized != value
        or normalized != normalized.strip()
        or "\\" in normalized
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise ValueError("scope path must be a canonical repository-relative POSIX path")
    candidate = PurePosixPath(normalized.rstrip("/"))
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("scope path must not be absolute or contain traversal")
    canonical = candidate.as_posix()
    if kind == "path":
        if not normalized.endswith("/"):
            raise ValueError("PATH scope entries must end with /")
        return canonical + "/"
    if normalized.endswith("/"):
        raise ValueError("FILE scope entries must not end with /")
    return canonical


@dataclass(frozen=True)
class AcceptanceScopeEntry:
    kind: Literal["file", "path"]
    value: str

    def __post_init__(self) -> None:
        canonical = _canonical_scope_path(self.value, kind=self.kind)
        if canonical != self.value:
            raise ValueError("scope entry is not canonical")

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AcceptanceScopeEntry:
        kind = str(value.get("kind", ""))
        if kind not in {"file", "path"}:
            raise ValueError("scope entry kind must be file or path")
        return cls(kind=kind, value=str(value.get("value", "")))  # type: ignore[arg-type]

    def matches(self, candidate: str) -> bool:
        if self.kind == "file":
            return candidate == self.value
        return candidate.startswith(self.value)


@dataclass(frozen=True)
class AcceptanceScope:
    schema_version: int
    entries: tuple[AcceptanceScopeEntry, ...]
    architecture_expansion: Literal["disabled", "allowed"]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported acceptance scope schema")
        if not self.entries:
            raise ValueError("acceptance scope must contain at least one entry")
        identities = [(entry.kind, entry.value) for entry in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError("acceptance scope entries must be unique")
        if self.architecture_expansion not in {"disabled", "allowed"}:
            raise ValueError("invalid architecture expansion mode")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.as_dict() for entry in self.entries],
            "architecture_expansion": self.architecture_expansion,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AcceptanceScope:
        entries = value.get("entries")
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError("acceptance scope entries must be a list")
        return cls(
            schema_version=int(value.get("schema_version", 0)),
            entries=tuple(AcceptanceScopeEntry.from_dict(item) for item in entries),
            architecture_expansion=str(value.get("architecture_expansion", "")),  # type: ignore[arg-type]
        )


def parse_acceptance_scope(plan_text: str) -> AcceptanceScope | None:
    """Parse the single structured scope section from an approved plan.

    Missing scope remains representable for old plans so the enforced scope
    gate can report ``missing_evidence``.  A present but malformed or
    ambiguous section is rejected and can never become positive evidence.
    """

    canonical_source = canonical_acceptance_source(plan_text)
    headings = list(_SCOPE_HEADING_RE.finditer(canonical_source))
    if not headings:
        return None
    if len(headings) != 1:
        raise ValueError("acceptance contract contains multiple scope sections")
    start = headings[0].end()
    next_heading = re.search(r"^#{1,3}\s+", canonical_source[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(canonical_source)
    section = canonical_source[start:end].strip()

    schema_matches = _SCOPE_SCHEMA_RE.findall(section)
    expansion_matches = _SCOPE_EXPANSION_RE.findall(section)
    if len(schema_matches) != 1 or len(expansion_matches) != 1:
        raise ValueError("scope needs exactly one schema and architecture-expansion declaration")
    entries: list[AcceptanceScopeEntry] = []
    for raw_kind, raw_path in _SCOPE_ENTRY_RE.findall(section):
        kind: Literal["file", "path"] = "file" if raw_kind == "FILE" else "path"
        entries.append(
            AcceptanceScopeEntry(
                kind=kind,
                value=_canonical_scope_path(raw_path, kind=kind),
            )
        )
    recognized_lines = {
        f"Scope-Schema: {schema_matches[0]}",
        f"Architecture-Expansion: {expansion_matches[0]}",
        *(f"- [{'FILE' if item.kind == 'file' else 'PATH'}] `{item.value}`" for item in entries),
    }
    content_lines = {line.strip() for line in section.splitlines() if line.strip()}
    if content_lines != recognized_lines:
        raise ValueError("scope section contains unrecognized or non-canonical declarations")
    return AcceptanceScope(
        schema_version=int(schema_matches[0]),
        entries=tuple(entries),
        architecture_expansion=expansion_matches[0],  # type: ignore[arg-type]
    )


MAX_QUESTIONS_PER_ROUND = 3
MAX_CLARIFICATION_ROUNDS = 2

_EXPLICIT_GAP_RE = re.compile(
    r"(?i)(?:\bTBD\b|\bTODO\b|\bFIXME\b|\bzu\s+klären\b|"
    r"\bungeklärt\b|(?:^|\s)(?:offen|unklar)\s*:|\?{3,})"
)
_AC_RE = re.compile(r"\[(GREP(?::NOT)?)\]\s*(?:`([^`]+)`|\"([^\"]+)\"|'([^']+)')")
_ANSWER_HEADER_RE = re.compile(
    r"(?im)^S\.A\.M\.U\.E\.L\.-Klärung:\s*([a-z0-9][a-z0-9._:-]*)/R([12])\s*$"
)
_NUMBERED_ANSWER_RE = re.compile(r"(?m)^\s*([1-3])[.)]\s+(.+?)\s*$")
_QUESTION_MARKER_RE = re.compile(r"<!-- samuel-clarification-request: (\{[^\r\n]*\}) -->")
_BASIS_MARKER_RE = re.compile(r"<!-- samuel-clarification-basis: (\{[^\r\n]*\}) -->")


def comment_body_digest(comment: Comment) -> str:
    return _digest({"body": comment.body})


def comment_revision(comment: Comment) -> str:
    return comment.updated_at or comment.created_at


@dataclass(frozen=True)
class ReadinessDecision:
    state: Literal["ready", "needs_clarification", "blocked"]
    reasons: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()


def assess_issue_readiness(issue: Issue) -> ReadinessDecision:
    """Classify only explicit machine-observable issue conditions.

    No text length, model score, author role, or inferred semantic completeness
    participates in this decision.
    """

    if not issue.title.strip() or not issue.body.strip():
        return ReadinessDecision("blocked", ("issue_source_empty",))
    if any(ord(char) < 32 and char not in "\t\n\r" for char in issue.title + issue.body):
        return ReadinessDecision("blocked", ("issue_source_control_character",))

    positive: set[str] = set()
    negative: set[str] = set()
    for match in _AC_RE.finditer(issue.body):
        value = next(group for group in match.groups()[1:] if group is not None).strip()
        (negative if match.group(1) == "GREP:NOT" else positive).add(value)
    contradictions = sorted(
        pos for pos in positive for neg in negative if pos == neg or pos in neg or neg in pos
    )
    if contradictions:
        return ReadinessDecision(
            "needs_clarification",
            ("explicit_acceptance_contradiction",),
            tuple(
                f"Welches beobachtbare Ziel soll das widersprüchliche GREP-Kriterium "
                f"{value!r} ersetzen?"
                for value in contradictions[:MAX_QUESTIONS_PER_ROUND]
            ),
        )

    gaps: list[str] = []
    for line in issue.body.splitlines():
        candidate = line.strip(" -*\t")
        if candidate and _EXPLICIT_GAP_RE.search(candidate):
            gaps.append(candidate[:240])
    if gaps:
        return ReadinessDecision(
            "needs_clarification",
            ("explicit_requirement_gap",),
            tuple(
                f"Wie soll diese ausdrücklich offene Anforderung entschieden werden: {gap}"
                for gap in gaps[:MAX_QUESTIONS_PER_ROUND]
            ),
        )
    return ReadinessDecision("ready")


@dataclass(frozen=True)
class ClarificationRequest:
    schema_version: int
    series_key: str
    round_number: int
    source_digest: str
    deadline_at: str
    questions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported clarification request schema")
        if self.round_number not in {1, 2}:
            raise ValueError("clarification round must be one or two")
        if not 1 <= len(self.questions) <= MAX_QUESTIONS_PER_ROUND:
            raise ValueError("clarification request must contain one to three questions")

    @property
    def digest(self) -> str:
        return _digest(asdict(self))

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["questions"] = list(self.questions)
        return value


def render_clarification_request(request: ClarificationRequest) -> str:
    marker = (
        json.dumps(request.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    questions = "\n".join(
        f"{index}. {html.escape(question)}" for index, question in enumerate(request.questions, 1)
    )
    return (
        f"## Klärung für Issue\n\n{questions}\n\n"
        "Bitte antworte in **einem neuen Kommentar** mit exakt diesem Kopf und "
        "nummerierten Antworten:\n\n"
        f"`S.A.M.U.E.L.-Klärung: {request.series_key}/R{request.round_number}`\n\n"
        f"Frist: `{request.deadline_at}`. Antworten nach der Frist oder Änderungen "
        "am Antwortkommentar werden nicht still übernommen.\n\n"
        f"<!-- samuel-clarification-request: {marker} -->"
    )


def parse_clarification_answer(
    comment: Comment, request: ClarificationRequest
) -> tuple[str, ...] | None:
    lines = [line.strip() for line in comment.body.splitlines() if line.strip()]
    if not lines:
        return None
    match = _ANSWER_HEADER_RE.fullmatch(lines[0])
    if match is None:
        return None
    if match.group(1) != request.series_key or int(match.group(2)) != request.round_number:
        return None
    found: dict[int, str] = {}
    for line in lines[1:]:
        answer_match = _NUMBERED_ANSWER_RE.fullmatch(line)
        if answer_match is None:
            return ()
        number = int(answer_match.group(1))
        if number in found:
            return ()
        found[number] = answer_match.group(2).strip()
    expected = set(range(1, len(request.questions) + 1))
    if set(found) != expected or any(not found[index] for index in expected):
        return ()
    return tuple(found[index] for index in sorted(expected))


@dataclass(frozen=True)
class ClarificationBasis:
    schema_version: int
    series_key: str
    source_digest: str
    rounds: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.series_key:
            raise ValueError("invalid clarification basis")
        if not 1 <= len(self.rounds) <= MAX_CLARIFICATION_ROUNDS:
            raise ValueError("invalid clarification basis rounds")

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "series_key": self.series_key,
            "source_digest": self.source_digest,
            "rounds": list(self.rounds),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ClarificationBasis:
        rounds = value.get("rounds")
        if not isinstance(rounds, list) or not all(isinstance(item, dict) for item in rounds):
            raise ValueError("invalid clarification basis rounds")
        return cls(
            schema_version=int(value.get("schema_version", 0)),
            series_key=str(value.get("series_key", "")),
            source_digest=str(value.get("source_digest", "")),
            rounds=tuple(rounds),
        )


def render_clarification_basis(basis: ClarificationBasis) -> str:
    payload = (
        json.dumps(basis.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    visible: list[str] = ["## Gebundene Klärungsbasis"]
    for round_data in basis.rounds:
        visible.append(f"### Runde {round_data['round_number']}")
        for question, answer in zip(round_data["questions"], round_data["answers"], strict=True):
            visible.extend(
                (f"- **Frage:** {html.escape(question)}", f"  **Antwort:** {html.escape(answer)}")
            )
        visible.append(
            f"- Evidence: Antwortkommentar #{round_data['answer_comment_id']} von "
            f"`{round_data['answer_actor']}`"
        )
    return "\n\n".join(visible) + f"\n\n<!-- samuel-clarification-basis: {payload} -->"


def parse_clarification_basis(text: str) -> ClarificationBasis | None:
    matches = _BASIS_MARKER_RE.findall(text)
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("plan needs at most one clarification basis")
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise ValueError("invalid clarification basis marker") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid clarification basis marker")
    return ClarificationBasis.from_dict(value)


def parse_clarification_request(text: str) -> ClarificationRequest | None:
    matches = _QUESTION_MARKER_RE.findall(text)
    if len(matches) != 1:
        return None
    try:
        value = json.loads(matches[0])
        questions = value.get("questions")
        if not isinstance(questions, list):
            return None
        return ClarificationRequest(
            schema_version=int(value.get("schema_version", 0)),
            series_key=str(value.get("series_key", "")),
            round_number=int(value.get("round_number", 0)),
            source_digest=str(value.get("source_digest", "")),
            deadline_at=str(value.get("deadline_at", "")),
            questions=tuple(str(item) for item in questions),
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def verify_clarification_basis(
    basis: ClarificationBasis,
    comments: list[Comment],
    *,
    source_digest: str | None = None,
) -> tuple[bool, str]:
    """Re-read all mutable SCM inputs named by one plan basis."""

    if source_digest is not None and basis.source_digest != source_digest:
        return False, "clarification_source_drift"
    by_id = {comment.id: comment for comment in comments}
    for round_data in basis.rounds:
        try:
            question = by_id[int(round_data["question_comment_id"])]
            answer = by_id[int(round_data["answer_comment_id"])]
        except (KeyError, TypeError, ValueError):
            return False, "clarification_comment_missing"
        if comment_body_digest(question) != round_data.get("question_digest") or comment_revision(
            question
        ) != round_data.get("question_revision"):
            return False, "clarification_question_edited"
        if (
            comment_body_digest(answer) != round_data.get("answer_digest")
            or comment_revision(answer) != round_data.get("answer_revision")
            or answer.user != round_data.get("answer_actor")
            or answer.created_at != round_data.get("answer_created_at")
        ):
            return False, "clarification_answer_edited"
        request = parse_clarification_request(question.body)
        if request is None:
            return False, "clarification_request_invalid"
        if (
            request.series_key != basis.series_key
            or request.source_digest != basis.source_digest
            or request.round_number != int(round_data.get("round_number", 0))
            or request.questions != tuple(round_data.get("questions", ()))
        ):
            return False, "clarification_request_mismatch"
        if (
            not answer.user
            or not scm_timestamp_at_or_after(answer.created_at, comment_revision(question))
            or not scm_timestamp_at_or_after(comment_revision(answer), answer.created_at)
        ):
            return False, "clarification_answer_outside_bound_window"
        if not scm_timestamp_at_or_after(request.deadline_at, answer.created_at) or not (
            scm_timestamp_at_or_after(request.deadline_at, comment_revision(answer))
        ):
            return False, "clarification_answer_late_or_unversioned"
        parsed_answers = parse_clarification_answer(answer, request)
        if parsed_answers is None or tuple(parsed_answers) != tuple(round_data.get("answers", ())):
            return False, "clarification_answer_mismatch"
    return True, "verified"


@dataclass(frozen=True)
class AcceptanceCriterion:
    criterion_id: str
    tag: str
    text: str
    mode: Literal["automatic", "manual"]
    required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AcceptanceCriterion:
        mode = str(value.get("mode", ""))
        if mode not in {"automatic", "manual"}:
            raise ValueError("criterion mode must be automatic or manual")
        criterion_id = str(value.get("criterion_id", ""))
        tag = str(value.get("tag", ""))
        text = str(value.get("text", ""))
        if not criterion_id or not tag or not text:
            raise ValueError("criterion id, tag and text are required")
        return cls(
            criterion_id=criterion_id,
            tag=tag,
            text=text,
            mode=mode,  # type: ignore[arg-type]
            required=bool(value.get("required", True)),
        )


@dataclass(frozen=True)
class AcceptanceApproval:
    state: Literal["approved", "unapproved"]
    actor: str = ""
    method: str = ""
    source_id: str = ""
    approved_at: str = ""
    contract_hash: str = ""
    plan_comment_id: int = 0

    def __post_init__(self) -> None:
        if self.state not in {"approved", "unapproved"}:
            raise ValueError("invalid acceptance approval state")
        if self.state == "approved" and not all(
            (
                self.actor,
                self.method,
                self.source_id,
                self.approved_at,
                self.contract_hash,
                self.plan_comment_id > 0,
            )
        ):
            raise ValueError("approved acceptance contract needs a traceable receipt")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AcceptanceApproval:
        state = str(value.get("state", "unapproved"))
        if state not in {"approved", "unapproved"}:
            raise ValueError("invalid acceptance approval state")
        approval = cls(
            state=state,  # type: ignore[arg-type]
            actor=str(value.get("actor", "")),
            method=str(value.get("method", "")),
            source_id=str(value.get("source_id", "")),
            approved_at=str(value.get("approved_at", "")),
            contract_hash=str(value.get("contract_hash", "")),
            plan_comment_id=int(value.get("plan_comment_id", 0)),
        )
        return approval


@dataclass(frozen=True)
class AcceptanceContract:
    schema_version: int
    revision: str
    contract_hash: str
    criteria: tuple[AcceptanceCriterion, ...]
    scope: AcceptanceScope | None = None
    source_snapshot: PlanningSourceSnapshot | None = None
    clarification_basis: ClarificationBasis | None = None
    approval: AcceptanceApproval = AcceptanceApproval(state="unapproved")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "contract_hash": self.contract_hash,
            "criteria": [criterion.as_dict() for criterion in self.criteria],
            "scope": self.scope.as_dict() if self.scope is not None else None,
            "source_snapshot": (
                self.source_snapshot.as_dict() if self.source_snapshot is not None else None
            ),
            "clarification_basis": (
                self.clarification_basis.as_dict() if self.clarification_basis is not None else None
            ),
            "approval": self.approval.as_dict(),
        }

    def with_approval(self, approval: AcceptanceApproval) -> AcceptanceContract:
        if approval.state == "approved" and approval.contract_hash != self.contract_hash:
            raise ValueError("approval receipt belongs to a different acceptance contract")
        return replace(self, approval=approval)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AcceptanceContract:
        contract = cls(
            schema_version=int(value.get("schema_version", 0)),
            revision=str(value.get("revision", "")),
            contract_hash=str(value.get("contract_hash", "")),
            criteria=tuple(
                AcceptanceCriterion.from_dict(item)
                for item in value.get("criteria", [])
                if isinstance(item, dict)
            ),
            scope=(
                AcceptanceScope.from_dict(value["scope"])
                if isinstance(value.get("scope"), dict)
                else None
            ),
            source_snapshot=(
                PlanningSourceSnapshot.from_dict(value["source_snapshot"])
                if isinstance(value.get("source_snapshot"), dict)
                else None
            ),
            clarification_basis=(
                ClarificationBasis.from_dict(value["clarification_basis"])
                if isinstance(value.get("clarification_basis"), dict)
                else None
            ),
            approval=AcceptanceApproval.from_dict(
                value.get("approval", {}) if isinstance(value.get("approval"), dict) else {}
            ),
        )
        if (
            contract.schema_version not in {1, 2, 3}
            or not contract.revision
            or not contract.contract_hash
        ):
            raise ValueError("invalid acceptance contract")
        if contract.schema_version == 1 and contract.scope is not None:
            raise ValueError("acceptance contract schema v1 cannot carry scope")
        if contract.schema_version == 1 and contract.source_snapshot is not None:
            raise ValueError("acceptance contract schema v1 cannot carry a planning source")
        if contract.schema_version < 3 and contract.clarification_basis is not None:
            raise ValueError("acceptance contract schema before v3 cannot carry clarification")
        if contract.schema_version == 3 and contract.clarification_basis is None:
            raise ValueError("acceptance contract schema v3 needs clarification evidence")
        ids = [criterion.criterion_id for criterion in contract.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("acceptance criterion ids must be unique")
        return contract


def parse_acceptance_contract(
    plan_text: str,
    *,
    source_snapshot: PlanningSourceSnapshot | None = None,
    allow_embedded_source: bool = True,
) -> AcceptanceContract:
    """Parse the approved plan into one deterministic contract revision."""

    embedded_source = parse_planning_source(plan_text)
    if embedded_source is not None and not allow_embedded_source:
        raise ValueError("plan draft must not provide its own planning source")
    if (
        source_snapshot is not None
        and embedded_source is not None
        and source_snapshot != embedded_source
    ):
        raise ValueError("planning source does not match the system-owned snapshot")
    bound_source = source_snapshot or embedded_source
    canonical_source = canonical_acceptance_source(plan_text)
    clarification_basis = parse_clarification_basis(canonical_source)
    scope = parse_acceptance_scope(canonical_source)
    revision_match = _REVISION_RE.search(canonical_source)
    revision = revision_match.group(1) if revision_match else "1"
    criteria: list[AcceptanceCriterion] = []
    seen: set[str] = set()
    for match in _CRITERION_RE.finditer(canonical_source):
        tag = match.group(2)
        text = _canonical_text(match.group(3)).strip()
        if tag in _GREP_TAGS:
            parse_grep_criterion_argument(text)
        elif tag == "TEST":
            parse_test_criterion_argument(text)
        identity = _digest({"tag": tag, "text": text})[7:23]
        criterion_id = f"AC-{identity}"
        if criterion_id in seen:
            raise ValueError("duplicate acceptance criterion")
        seen.add(criterion_id)
        criteria.append(
            AcceptanceCriterion(
                criterion_id=criterion_id,
                tag=tag,
                text=text,
                mode="manual" if tag == "MANUAL" else "automatic",
            )
        )
    schema_version = 3 if clarification_basis is not None else 2
    contract_value = {
        "schema_version": schema_version,
        "revision": revision,
        "source": canonical_source,
        "criteria": [criterion.as_dict() for criterion in criteria],
        "scope": scope.as_dict() if scope is not None else None,
        "source_snapshot": bound_source.as_dict() if bound_source is not None else None,
        "clarification_basis": (
            clarification_basis.as_dict() if clarification_basis is not None else None
        ),
    }
    return AcceptanceContract(
        schema_version=schema_version,
        revision=revision,
        contract_hash=_digest(contract_value),
        criteria=tuple(criteria),
        scope=scope,
        source_snapshot=bound_source,
        clarification_basis=clarification_basis,
    )


def _trusted_plan_revocations(comments: list[Any]) -> list[tuple[Any, PlanRevocation]]:
    trusted: list[tuple[Any, PlanRevocation]] = []
    comments_by_id = {int(comment.id): comment for comment in comments}
    positions = {int(comment.id): index for index, comment in enumerate(comments)}
    for comment in comments:
        for revocation in parse_plan_revocations(str(comment.body)):
            target = comments_by_id.get(revocation.plan_comment_id)
            if (
                target is None
                or positions[revocation.plan_comment_id] >= positions[int(comment.id)]
            ):
                continue
            # A user cannot revoke another actor's system-owned plan by
            # copying the public marker syntax into an arbitrary comment.
            if not comment.user or comment.user != target.user:
                continue
            target_contract = parse_acceptance_contract(str(target.body))
            if target_contract.contract_hash != revocation.contract_hash:
                raise ValueError("plan revocation contract hash mismatch")
            trusted.append((comment, revocation))
    return trusted


def latest_plan_revocation(comments: list[Any]) -> tuple[Any, PlanRevocation] | None:
    """Return the newest trusted revocation marker, if one exists."""

    revocations = _trusted_plan_revocations(comments)
    return revocations[-1] if revocations else None


def latest_active_plan(comments: list[Any]) -> tuple[Any, AcceptanceContract] | None:
    """Return the newest authoritative plan not revoked by a later marker.

    Revocations bind to the immutable SCM comment id. This keeps a newly
    generated, text-identical plan distinct from the plan it supersedes.
    """

    revoked = {
        revocation.plan_comment_id for _comment, revocation in _trusted_plan_revocations(comments)
    }
    for comment in reversed(comments):
        body = str(comment.body)
        if comment.id in revoked:
            continue
        if "## Nicht autoritativer Planentwurf" in body:
            continue
        if not _AUTHORITATIVE_PLAN_HEADING_RE.search(body):
            continue
        return comment, parse_acceptance_contract(body)
    return None


def clarification_evidence_failure(
    contract: AcceptanceContract,
    issue: Any,
    comments: list[Any],
) -> str | None:
    """Return a safe failure code when a bound clarification input changed."""

    basis = contract.clarification_basis
    if basis is None:
        return None
    source = contract.source_snapshot
    if source is None:
        return "clarification_source_missing"
    observed_issue_digest = issue_revision_digest(
        number=int(issue.number), title=str(issue.title), body=str(issue.body)
    )
    if observed_issue_digest != source.issue_digest:
        return "clarification_issue_changed"
    valid, reason = verify_clarification_basis(basis, comments, source_digest=source.digest)
    return None if valid else reason


@dataclass(frozen=True)
class AcceptanceResult:
    criterion_id: str
    status: AcceptanceStatus
    reason: str
    tag: str
    evidence: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AcceptanceEvidence:
    schema_version: int
    subject: EvaluationSubject
    contract: AcceptanceContract
    results: tuple[AcceptanceResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_subject": self.subject.as_dict(),
            "contract": self.contract.as_dict(),
            "results": [result.as_dict() for result in self.results],
        }


def manual_receipts_for_subject(
    comments: list[Comment],
    plan_comment: Comment,
    contract: AcceptanceContract,
    subject: EvaluationSubject,
    *,
    after: str = "",
) -> dict[str, dict[str, str]]:
    """Read exact human MANUAL receipts from the active plan's SCM comments."""

    ids = {criterion.criterion_id for criterion in contract.criteria if criterion.mode == "manual"}
    if not ids:
        return {}
    receipt_re = re.compile(
        r"^/samuel\s+accept\s+(AC-[0-9a-f]{16})\s+"
        r"--contract\s+(sha256:[0-9a-f]{64})\s+"
        r"--head\s+([0-9a-f]{40}|[0-9a-f]{64})$",
        re.IGNORECASE,
    )
    try:
        plan_index = next(
            index for index, item in enumerate(comments) if item.id == plan_comment.id
        )
    except StopIteration:
        return {}
    receipts: dict[str, dict[str, str]] = {}
    for comment in comments[plan_index + 1 :]:
        match = receipt_re.fullmatch(comment.body.strip())
        if not match or not comment.user or comment.user == plan_comment.user:
            continue
        if after and not scm_timestamp_at_or_after(comment.created_at, after):
            continue
        criterion_id, receipt_contract, receipt_head = match.groups()
        if (
            criterion_id not in ids
            or receipt_contract != contract.contract_hash
            or receipt_head != subject.head_sha
        ):
            continue
        receipts[criterion_id] = {
            "criterion_id": criterion_id,
            "actor": comment.user,
            "method": "comment",
            "source_id": f"comment:{comment.id}",
            "approved_at": comment.created_at,
            "contract_hash": receipt_contract,
            "head_sha": receipt_head,
        }
    return receipts


def only_manual_acceptance_pending(
    gate_results: list[dict[str, Any]], acceptance_evidence: dict[str, Any] | None
) -> bool:
    """True only when the sole required block is unapproved MANUAL evidence."""

    if not isinstance(acceptance_evidence, dict):
        return False
    contract = acceptance_evidence.get("contract")
    results = acceptance_evidence.get("results")
    if not isinstance(contract, dict) or not isinstance(results, list):
        return False
    criteria = contract.get("criteria")
    if not isinstance(criteria, list):
        return False
    required = {
        item.get("criterion_id"): item
        for item in criteria
        if isinstance(item, dict) and item.get("required", True)
    }
    by_id = {
        item.get("criterion_id"): item
        for item in results
        if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)
    }
    if not required or len(by_id) != len(results) or not set(required) <= set(by_id):
        return False
    pending = False
    for criterion_id, criterion in required.items():
        status = by_id[criterion_id].get("status")
        if status == "manual_pending" and criterion.get("mode") == "manual":
            pending = True
        elif status != "passed":
            return False
    if not pending:
        return False
    failures = [
        item
        for item in gate_results
        if isinstance(item, dict)
        and item.get("authority") == "required"
        and item.get("passed") is not True
    ]
    return (
        bool(failures)
        and any(item.get("gate") == 11 for item in failures)
        and all(
            item.get("gate") in (11, 12)
            and item.get("passed") is False
            and item.get("status") == "manual_pending"
            for item in failures
        )
    )


PLAN_APPROVAL_AUTHORITY_KIND = "plan_approval.v1"
PLAN_APPROVAL_AUTHORITY_SCHEMA = "plan-approval-authority.v1"


class PlanApprovalAuthorityError(StateStoreError):
    """Fail-closed error while materializing or resolving plan authority."""


def plan_approval_authority_key(
    *,
    repository: str,
    issue_number: int,
    plan_comment_id: int,
    contract_hash: str,
) -> str:
    identity = {
        "schema": PLAN_APPROVAL_AUTHORITY_SCHEMA,
        "repository": repository,
        "issue_number": issue_number,
        "plan_comment_id": plan_comment_id,
        "contract_hash": contract_hash,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"plan-approval:sha256:{hashlib.sha256(encoded).hexdigest()}"


def _transport_for(approval: AcceptanceApproval, transport: str | None) -> str:
    if transport:
        return transport
    if approval.method.endswith("/polling"):
        return "authenticated_scm_polling"
    if approval.method.endswith("/webhook") or approval.method == "comment":
        return "signed_webhook"
    if approval.method == "plan_validated":
        return "planning_policy"
    raise PlanApprovalAuthorityError(
        "plan_approval_transport_invalid",
        "Plan approval transport is not an authorized canonical transport",
    )


def persist_plan_approval(
    store: IAuthorityStateStore,
    *,
    repository: str,
    issue_number: int,
    contract: AcceptanceContract,
    approval: AcceptanceApproval,
    transport: str | None = None,
) -> AuthorityRecord:
    """Persist one immutable approval receipt in the existing authority store."""

    record, _created = persist_plan_approval_with_status(
        store,
        repository=repository,
        issue_number=issue_number,
        contract=contract,
        approval=approval,
        transport=transport,
    )
    return record


def persist_plan_approval_with_status(
    store: IAuthorityStateStore,
    *,
    repository: str,
    issue_number: int,
    contract: AcceptanceContract,
    approval: AcceptanceApproval,
    transport: str | None = None,
) -> tuple[AuthorityRecord, bool]:
    """Persist one immutable approval receipt and report a create-only write."""

    if (
        approval.state != "approved"
        or approval.plan_comment_id <= 0
        or approval.contract_hash != contract.contract_hash
        or issue_number <= 0
        or not repository
    ):
        raise PlanApprovalAuthorityError(
            "plan_approval_binding_invalid",
            "Plan approval does not match the repository, issue, plan and contract",
        )
    source_revision = (
        contract.source_snapshot.as_dict() if contract.source_snapshot is not None else None
    )
    record = AuthorityRecord(
        record_key=plan_approval_authority_key(
            repository=repository,
            issue_number=issue_number,
            plan_comment_id=approval.plan_comment_id,
            contract_hash=approval.contract_hash,
        ),
        kind=PLAN_APPROVAL_AUTHORITY_KIND,
        payload={
            "schema": PLAN_APPROVAL_AUTHORITY_SCHEMA,
            "subject": {
                "repository": repository,
                "issue_number": issue_number,
                "plan_comment_id": approval.plan_comment_id,
                "contract_hash": approval.contract_hash,
                "source_revision": source_revision,
            },
            "approval": approval.as_dict(),
            "source": {
                "actor": approval.actor,
                "method": approval.method,
                "source_id": approval.source_id,
                "approved_at": approval.approved_at,
                "transport": _transport_for(approval, transport),
            },
            "lifecycle": {
                "state_at_issuance": "active",
                "revocation_authority": "active_plan_and_plan_revocation.v1",
            },
        },
    )
    try:
        existing = store.get_authority_record(record.record_key)
    except Exception as exc:
        raise PlanApprovalAuthorityError(
            "plan_approval_lookup_failed",
            "Existing plan approval authority could not be read",
        ) from exc
    if existing is not None:
        return _resolve_approval_replay(existing, record), False
    try:
        created = store.put_authority_record(record)
    except StateStoreError:
        # Another authorized ingress can win the create-only race for the
        # same SCM label transition. Re-read and accept only its equivalent
        # canonical human decision; every other collision remains fail-closed.
        existing = store.get_authority_record(record.record_key)
        if existing is not None:
            return _resolve_approval_replay(existing, record), False
        raise
    except Exception as exc:  # adapters must remain fail-closed
        raise PlanApprovalAuthorityError(
            "plan_approval_persist_failed",
            "Plan approval authority could not be persisted",
        ) from exc
    persisted = store.get_authority_record(record.record_key)
    if persisted is None or persisted.kind != record.kind or persisted.payload != record.payload:
        raise PlanApprovalAuthorityError(
            "plan_approval_persist_unconfirmed",
            "Plan approval authority could not be read back exactly",
        )
    return persisted, created


def _resolve_approval_replay(
    existing: AuthorityRecord,
    proposed: AuthorityRecord,
) -> AuthorityRecord:
    if existing.kind == proposed.kind and existing.payload == proposed.payload:
        return existing
    existing_payload = existing.payload
    proposed_payload = proposed.payload
    try:
        existing_approval = AcceptanceApproval.from_dict(existing_payload["approval"])
        proposed_approval = AcceptanceApproval.from_dict(proposed_payload["approval"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanApprovalAuthorityError(
            "plan_approval_replay_conflict",
            "Existing plan approval authority is not replay-compatible",
        ) from exc
    existing_source = existing_payload.get("source")
    proposed_source = proposed_payload.get("source")
    same_label_decision = (
        existing.kind == proposed.kind == PLAN_APPROVAL_AUTHORITY_KIND
        and existing_payload.get("schema") == proposed_payload.get("schema")
        and existing_payload.get("subject") == proposed_payload.get("subject")
        and existing_payload.get("lifecycle") == proposed_payload.get("lifecycle")
        and isinstance(existing_source, dict)
        and isinstance(proposed_source, dict)
        and existing_approval.state == proposed_approval.state == "approved"
        and existing_approval.actor == proposed_approval.actor
        and existing_approval.approved_at == proposed_approval.approved_at
        and existing_approval.contract_hash == proposed_approval.contract_hash
        and existing_approval.plan_comment_id == proposed_approval.plan_comment_id
        and existing_approval.method.startswith("status:approved")
        and proposed_approval.method.startswith("status:approved")
        and existing_source.get("actor") == proposed_source.get("actor")
        and existing_source.get("approved_at") == proposed_source.get("approved_at")
        and {existing_source.get("transport"), proposed_source.get("transport")}
        == {"authenticated_scm_polling", "signed_webhook"}
    )
    if same_label_decision:
        return existing
    raise PlanApprovalAuthorityError(
        "plan_approval_replay_conflict",
        "Existing plan approval authority is not replay-compatible",
    )


def _approval_comment_is_unchanged(
    comments: list[Comment],
    *,
    plan_comment_id: int,
    approval: AcceptanceApproval,
) -> bool:
    prefix = f"plan:{plan_comment_id};comment:"
    if not approval.source_id.startswith(prefix):
        return False
    try:
        comment_id = int(approval.source_id.removeprefix(prefix))
        plan_index = next(index for index, row in enumerate(comments) if row.id == plan_comment_id)
    except (StopIteration, ValueError):
        return False
    return any(
        row.id == comment_id
        and row.body.strip().casefold() in {"ok", "/approve"}
        and row.user == approval.actor
        and row.created_at == approval.approved_at
        and (not row.updated_at or row.updated_at == row.created_at)
        for row in comments[plan_index + 1 :]
    )


def _polling_label_event_exists(
    scm: IVersionControl,
    *,
    issue_number: int,
    plan_comment_id: int,
    approval: AcceptanceApproval,
) -> bool:
    prefix = f"plan:{plan_comment_id};"
    if not approval.source_id.startswith(prefix):
        return False
    event_source_id = approval.source_id.removeprefix(prefix)
    return any(
        event.source_id == event_source_id
        and event.label == "status:approved"
        and event.operation == "add"
        and event.actor == approval.actor
        and event.actor_type == "human"
        and event.timestamp == approval.approved_at
        for event in scm.get_label_events(issue_number, "status:approved")
    )


def _signed_webhook_label_event_exists(
    scm: IVersionControl,
    *,
    issue_number: int,
    plan_comment_id: int,
    approval: AcceptanceApproval,
) -> bool:
    prefix = f"plan:{plan_comment_id};"
    marker = ";delivery:"
    if not approval.source_id.startswith(prefix) or marker not in approval.source_id:
        return False
    evidence = approval.source_id.removeprefix(prefix)
    event_source_id, delivery_id = evidence.rsplit(marker, 1)
    if not event_source_id or not delivery_id:
        return False
    return any(
        event.source_id == event_source_id
        and event.label == "status:approved"
        and event.operation == "add"
        and event.actor == approval.actor
        and event.actor_type == "human"
        and event.timestamp == approval.approved_at
        for event in scm.get_label_events(issue_number, "")
    )


def resolve_plan_approval(
    store: IAuthorityStateStore,
    *,
    scm: IVersionControl,
    repository: str,
    issue_number: int,
    plan_comment: Comment,
    contract: AcceptanceContract,
    comments: list[Comment],
    supplied: dict[str, Any] | None = None,
    expected_base_sha: str | None = None,
) -> AcceptanceApproval:
    """Resolve and revalidate durable approval without consulting status labels."""

    try:
        active = latest_active_plan(comments)
    except ValueError as exc:
        raise PlanApprovalAuthorityError(
            "plan_approval_active_plan_invalid",
            "Active plan evidence is malformed",
        ) from exc
    if (
        active is None
        or active[0].id != plan_comment.id
        or active[0] != plan_comment
        or active[1].contract_hash != contract.contract_hash
        or (active[0].updated_at and active[0].updated_at != active[0].created_at)
    ):
        raise PlanApprovalAuthorityError(
            "plan_approval_revoked_or_superseded",
            "Plan approval authority was revoked or superseded",
        )

    key = plan_approval_authority_key(
        repository=repository,
        issue_number=issue_number,
        plan_comment_id=plan_comment.id,
        contract_hash=contract.contract_hash,
    )
    record = store.get_authority_record(key)
    if record is None:
        raise PlanApprovalAuthorityError(
            "plan_approval_authority_missing",
            "No durable plan approval authority exists for the active plan",
        )
    if record.kind != PLAN_APPROVAL_AUTHORITY_KIND:
        raise PlanApprovalAuthorityError(
            "plan_approval_authority_invalid",
            "Stored plan approval authority has an unexpected kind",
        )
    payload = record.payload
    subject = payload.get("subject")
    source = payload.get("source")
    approval_value = payload.get("approval")
    lifecycle = payload.get("lifecycle")
    if (
        payload.get("schema") != PLAN_APPROVAL_AUTHORITY_SCHEMA
        or not isinstance(subject, dict)
        or not isinstance(source, dict)
        or not isinstance(approval_value, dict)
        or not isinstance(lifecycle, dict)
        or lifecycle.get("state_at_issuance") != "active"
        or lifecycle.get("revocation_authority") != "active_plan_and_plan_revocation.v1"
    ):
        raise PlanApprovalAuthorityError(
            "plan_approval_authority_invalid",
            "Stored plan approval authority is malformed",
        )
    expected_source_revision = (
        contract.source_snapshot.as_dict() if contract.source_snapshot is not None else None
    )
    if subject != {
        "repository": repository,
        "issue_number": issue_number,
        "plan_comment_id": plan_comment.id,
        "contract_hash": contract.contract_hash,
        "source_revision": expected_source_revision,
    }:
        raise PlanApprovalAuthorityError(
            "plan_approval_subject_mismatch",
            "Stored plan approval authority belongs to another subject",
        )
    if contract.source_snapshot is not None:
        snapshot = contract.source_snapshot
        try:
            issue = scm.get_issue(issue_number)
            source_is_current = (
                snapshot.repository == repository == scm.repository_identity
                and scm.resolve_ref(snapshot.base_ref) == snapshot.base_sha
                and issue.number == issue_number
                and issue_revision_digest(
                    number=issue.number,
                    title=issue.title,
                    body=issue.body,
                )
                == snapshot.issue_digest
            )
        except Exception as exc:
            raise PlanApprovalAuthorityError(
                "plan_approval_source_revision_unavailable",
                "Plan approval source revision could not be revalidated",
            ) from exc
        if not source_is_current:
            raise PlanApprovalAuthorityError(
                "plan_approval_source_revision_mismatch",
                "Plan approval source revision was superseded",
            )
    if (
        expected_base_sha is not None
        and contract.source_snapshot is not None
        and contract.source_snapshot.base_sha != expected_base_sha
    ):
        raise PlanApprovalAuthorityError(
            "plan_approval_source_revision_mismatch",
            "Stored plan approval authority belongs to another source revision",
        )
    try:
        approval = AcceptanceApproval.from_dict(approval_value)
    except (TypeError, ValueError) as exc:
        raise PlanApprovalAuthorityError(
            "plan_approval_authority_invalid",
            "Stored plan approval receipt is malformed",
        ) from exc
    if (
        approval.state != "approved"
        or approval.plan_comment_id != plan_comment.id
        or approval.contract_hash != contract.contract_hash
        or source
        != {
            "actor": approval.actor,
            "method": approval.method,
            "source_id": approval.source_id,
            "approved_at": approval.approved_at,
            "transport": source.get("transport"),
        }
    ):
        raise PlanApprovalAuthorityError(
            "plan_approval_authority_invalid",
            "Stored plan approval receipt does not match its authority binding",
        )
    if supplied is not None:
        try:
            supplied_approval = AcceptanceApproval.from_dict(supplied)
        except (TypeError, ValueError) as exc:
            raise PlanApprovalAuthorityError(
                "plan_approval_supplied_invalid",
                "Supplied plan approval receipt is malformed",
            ) from exc
        if supplied_approval != approval:
            raise PlanApprovalAuthorityError(
                "plan_approval_supplied_mismatch",
                "Supplied plan approval receipt differs from durable authority",
            )

    transport = str(source.get("transport") or "")
    if transport == "authenticated_scm_polling":
        source_valid = _polling_label_event_exists(
            scm,
            issue_number=issue_number,
            plan_comment_id=plan_comment.id,
            approval=approval,
        )
    elif transport == "signed_webhook" and approval.method.startswith("comment"):
        source_valid = _approval_comment_is_unchanged(
            comments,
            plan_comment_id=plan_comment.id,
            approval=approval,
        )
    elif transport == "signed_webhook" and approval.method.startswith("status:approved"):
        source_valid = approval.source_id.startswith(
            f"plan:{plan_comment.id};label:"
        ) or _signed_webhook_label_event_exists(
            scm,
            issue_number=issue_number,
            plan_comment_id=plan_comment.id,
            approval=approval,
        )
    else:
        source_valid = False
    if not source_valid:
        raise PlanApprovalAuthorityError(
            "plan_approval_source_stale",
            "Original plan approval source can no longer be revalidated",
        )
    return approval
