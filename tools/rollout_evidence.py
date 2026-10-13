"""Structured, offline validation for the bound-authority rollout (#399/#580)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from samuel.core.evaluation_subject import EvaluationSubject

SCHEMA_VERSION = "1.0"
REQUIRED_CASE_IDS = frozenset(
    {
        "success",
        "required_gate_block",
        "evidence_healing_new_head",
        "terminal_refail",
        "legacy_rollback",
    }
)

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FULL_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_STABLE_STORES = frozenset(
    {
        "evaluation_observations.json",
        "bound_healing_attempts.json",
        "quality_metrics.json",
    }
)


class RolloutEvidenceError(ValueError):
    """The checked-in rollout evidence does not satisfy its release contract."""


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RolloutEvidenceError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise RolloutEvidenceError(f"{path} must be a list")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise RolloutEvidenceError(f"{path} has invalid fields: {'; '.join(details)}")


def _text(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise RolloutEvidenceError(f"{path} must be a non-empty canonical string")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RolloutEvidenceError(f"{path} must be an integer >= {minimum}")
    return value


def _exact(value: Any, expected: Any, path: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise RolloutEvidenceError(f"{path} must be {expected!r}")


def _digest(value: Any, path: str) -> str:
    text = _text(value, path)
    if _DIGEST_RE.fullmatch(text) is None:
        raise RolloutEvidenceError(f"{path} must be a sha256 digest")
    return text


def _full_sha(value: Any, path: str) -> str:
    text = _text(value, path)
    if _FULL_SHA_RE.fullmatch(text) is None:
        raise RolloutEvidenceError(f"{path} must be a full lowercase Git object ID")
    return text


def _url(value: Any, path: str) -> str:
    text = _text(value, path)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RolloutEvidenceError(f"{path} must be an absolute HTTP(S) URL")
    return text


def _uuid(value: Any, path: str) -> str:
    text = _text(value, path)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise RolloutEvidenceError(f"{path} must be a canonical UUID") from exc
    if str(parsed) != text:
        raise RolloutEvidenceError(f"{path} must be a canonical UUID")
    return text


def _utc_timestamp(value: Any, path: str) -> str:
    text = _text(value, path)
    if _UTC_TIMESTAMP_RE.fullmatch(text) is None:
        raise RolloutEvidenceError(f"{path} must be a canonical UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise RolloutEvidenceError(f"{path} must be a valid UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise RolloutEvidenceError(f"{path} must use UTC")
    return text


def _validate_run(value: Any, path: str, repository: str) -> None:
    run = _object(value, path)
    _exact_keys(
        run,
        {"issue_number", "issue_url", "evidence_comment_id", "evidence_comment_url"},
        path,
    )
    issue_number = _integer(run["issue_number"], f"{path}.issue_number", minimum=1)
    issue_url = _url(run["issue_url"], f"{path}.issue_url")
    expected_issue_url = f"{repository.rstrip('/')}/issues/{issue_number}"
    if issue_url != expected_issue_url:
        raise RolloutEvidenceError(
            f"{path}.issue_url must identify issue {issue_number} in the subject repository"
        )
    comment_id = _integer(run["evidence_comment_id"], f"{path}.evidence_comment_id", minimum=1)
    comment_url = _url(run["evidence_comment_url"], f"{path}.evidence_comment_url")
    if f"#issuecomment-{comment_id}" not in comment_url:
        raise RolloutEvidenceError(
            f"{path}.evidence_comment_url must identify evidence comment {comment_id}"
        )


def _validate_subject(value: Any, path: str) -> dict[str, str]:
    subject = _object(value, path)
    _exact_keys(
        subject,
        {
            "repository",
            "base_sha",
            "head_sha",
            "contract_hash",
            "policy_version",
            "policy_digest",
            "observation_key",
            "correlation_id",
            "observed_at",
        },
        path,
    )
    try:
        EvaluationSubject.from_dict(subject)
    except ValueError as exc:
        raise RolloutEvidenceError(f"{path} is not a valid EvaluationSubject: {exc}") from exc
    repository = _url(subject["repository"], f"{path}.repository")
    if subject["base_sha"] == subject["head_sha"]:
        raise RolloutEvidenceError(f"{path} base_sha and head_sha must differ")
    observation_key = _digest(subject["observation_key"], f"{path}.observation_key")
    correlation_id = _uuid(subject["correlation_id"], f"{path}.correlation_id")
    observed_at = _utc_timestamp(subject["observed_at"], f"{path}.observed_at")
    return {
        **{key: str(subject[key]) for key in EvaluationSubject.__dataclass_fields__},
        "repository": repository,
        "observation_key": observation_key,
        "correlation_id": correlation_id,
        "observed_at": observed_at,
    }


def _validate_gate_result(value: Any, path: str, *, blocked: bool, count: int = 1) -> None:
    result = _object(value, path)
    _exact_keys(result, {"count", "blocked", "gate_results"}, path)
    _exact(result["count"], count, f"{path}.count")
    _exact(result["blocked"], blocked, f"{path}.blocked")
    _integer(result["gate_results"], f"{path}.gate_results", minimum=1)


def _validate_score(value: Any, path: str, *, count: int) -> None:
    score = _object(value, path)
    _exact_keys(score, {"count", "non_binding"}, path)
    _exact(score["count"], count, f"{path}.count")
    _exact(score["non_binding"], True, f"{path}.non_binding")


def _validate_pr(
    value: Any,
    path: str,
    *,
    expected_count: int,
    base_sha: str | None = None,
    head_sha: str | None = None,
) -> None:
    pr = _object(value, path)
    if expected_count == 0:
        _exact_keys(pr, {"count"}, path)
        _exact(pr["count"], 0, f"{path}.count")
        return
    _exact_keys(pr, {"count", "number", "url", "base_sha", "head_sha"}, path)
    _exact(pr["count"], expected_count, f"{path}.count")
    _integer(pr["number"], f"{path}.number", minimum=1)
    _url(pr["url"], f"{path}.url")
    observed_base = _full_sha(pr["base_sha"], f"{path}.base_sha")
    observed_head = _full_sha(pr["head_sha"], f"{path}.head_sha")
    if observed_base != base_sha or observed_head != head_sha:
        raise RolloutEvidenceError(f"{path} base/head must match the released subject")


def _validate_matching_healed_subject(
    initial: dict[str, str], value: Any, path: str
) -> dict[str, str]:
    healed = _validate_subject(value, path)
    for key in ("repository", "base_sha", "contract_hash", "policy_version", "policy_digest"):
        if healed[key] != initial[key]:
            raise RolloutEvidenceError(f"{path}.{key} must match the initial subject")
    if healed["correlation_id"] != initial["correlation_id"]:
        raise RolloutEvidenceError(f"{path}.correlation_id must match the initial subject")
    if healed["head_sha"] == initial["head_sha"]:
        raise RolloutEvidenceError(f"{path}.head_sha must identify a new candidate")
    if healed["observation_key"] == initial["observation_key"]:
        raise RolloutEvidenceError(f"{path}.observation_key must identify new evidence")
    return healed


def _validate_success(case: dict[str, Any], subject: dict[str, str], path: str) -> None:
    evidence = _object(case["evidence"], f"{path}.evidence")
    _exact_keys(
        evidence,
        {"gate_evaluation_completed", "score_observed", "gates_passed", "pr_created"},
        f"{path}.evidence",
    )
    _validate_gate_result(
        evidence["gate_evaluation_completed"],
        f"{path}.evidence.gate_evaluation_completed",
        blocked=False,
    )
    _validate_score(evidence["score_observed"], f"{path}.evidence.score_observed", count=1)
    _exact(evidence["gates_passed"], 1, f"{path}.evidence.gates_passed")
    _validate_pr(
        evidence["pr_created"],
        f"{path}.evidence.pr_created",
        expected_count=1,
        base_sha=subject["base_sha"],
        head_sha=subject["head_sha"],
    )


def _validate_required_block(case: dict[str, Any], _subject: dict[str, str], path: str) -> None:
    evidence = _object(case["evidence"], f"{path}.evidence")
    _exact_keys(
        evidence,
        {
            "gate_evaluation_completed",
            "score_observed",
            "healing_classified",
            "healing_attempts_started",
            "workflow_blocked",
            "pr_created",
        },
        f"{path}.evidence",
    )
    _validate_gate_result(
        evidence["gate_evaluation_completed"],
        f"{path}.evidence.gate_evaluation_completed",
        blocked=True,
    )
    _validate_score(evidence["score_observed"], f"{path}.evidence.score_observed", count=1)
    classified = _object(evidence["healing_classified"], f"{path}.evidence.healing_classified")
    _exact_keys(
        classified, {"count", "classification", "reason"}, f"{path}.evidence.healing_classified"
    )
    _exact(classified["count"], 1, f"{path}.evidence.healing_classified.count")
    _exact(
        classified["classification"],
        "not_healable",
        f"{path}.evidence.healing_classified.classification",
    )
    _text(classified["reason"], f"{path}.evidence.healing_classified.reason")
    _exact(evidence["healing_attempts_started"], 0, f"{path}.evidence.healing_attempts_started")
    blocked = _object(evidence["workflow_blocked"], f"{path}.evidence.workflow_blocked")
    _exact_keys(blocked, {"count", "reason"}, f"{path}.evidence.workflow_blocked")
    _exact(blocked["count"], 1, f"{path}.evidence.workflow_blocked.count")
    _text(blocked["reason"], f"{path}.evidence.workflow_blocked.reason")
    _validate_pr(evidence["pr_created"], f"{path}.evidence.pr_created", expected_count=0)


def _validate_healing_counts(
    value: Any, path: str, initial: dict[str, str], healed: dict[str, str]
) -> None:
    healing = _object(value, path)
    _exact_keys(
        healing,
        {
            "classified",
            "attempts_started",
            "attempts_completed",
            "max_attempts",
            "second_attempts",
            "failed_head",
            "healed_parent_sha",
            "healed_head",
        },
        path,
    )
    _exact(healing["classified"], 2, f"{path}.classified")
    _exact(healing["attempts_started"], 1, f"{path}.attempts_started")
    _exact(healing["attempts_completed"], 1, f"{path}.attempts_completed")
    _exact(healing["max_attempts"], 1, f"{path}.max_attempts")
    _exact(healing["second_attempts"], 0, f"{path}.second_attempts")
    if (
        healing["failed_head"] != initial["head_sha"]
        or healing["healed_parent_sha"] != initial["head_sha"]
        or healing["healed_head"] != healed["head_sha"]
    ):
        raise RolloutEvidenceError(f"{path} must prove a fast-forward heal from the failed head")


def _validate_healing(case: dict[str, Any], initial: dict[str, str], path: str) -> None:
    evidence = _object(case["evidence"], f"{path}.evidence")
    _exact_keys(
        evidence,
        {
            "healed_subject",
            "gate_evaluation_completed",
            "score_observed",
            "healing",
            "gates_passed",
            "pr_created",
        },
        f"{path}.evidence",
    )
    healed = _validate_matching_healed_subject(
        initial, evidence["healed_subject"], f"{path}.evidence.healed_subject"
    )
    gates = _object(
        evidence["gate_evaluation_completed"],
        f"{path}.evidence.gate_evaluation_completed",
    )
    _exact_keys(
        gates,
        {"count", "initial_blocked", "healed_blocked", "gate_results_each"},
        f"{path}.evidence.gate_evaluation_completed",
    )
    _exact(gates["count"], 2, f"{path}.evidence.gate_evaluation_completed.count")
    _exact(
        gates["initial_blocked"], True, f"{path}.evidence.gate_evaluation_completed.initial_blocked"
    )
    _exact(
        gates["healed_blocked"], False, f"{path}.evidence.gate_evaluation_completed.healed_blocked"
    )
    _integer(
        gates["gate_results_each"],
        f"{path}.evidence.gate_evaluation_completed.gate_results_each",
        minimum=1,
    )
    _validate_score(evidence["score_observed"], f"{path}.evidence.score_observed", count=2)
    _validate_healing_counts(evidence["healing"], f"{path}.evidence.healing", initial, healed)
    _exact(evidence["gates_passed"], 1, f"{path}.evidence.gates_passed")
    _validate_pr(
        evidence["pr_created"],
        f"{path}.evidence.pr_created",
        expected_count=1,
        base_sha=healed["base_sha"],
        head_sha=healed["head_sha"],
    )


def _validate_terminal_refail(case: dict[str, Any], initial: dict[str, str], path: str) -> None:
    evidence = _object(case["evidence"], f"{path}.evidence")
    _exact_keys(
        evidence,
        {
            "healed_subject",
            "gate_evaluation_completed",
            "score_observed",
            "healing",
            "workflow_blocked",
            "pr_created",
        },
        f"{path}.evidence",
    )
    healed = _validate_matching_healed_subject(
        initial, evidence["healed_subject"], f"{path}.evidence.healed_subject"
    )
    gates = _object(
        evidence["gate_evaluation_completed"],
        f"{path}.evidence.gate_evaluation_completed",
    )
    _exact_keys(
        gates,
        {"count", "initial_blocked", "healed_blocked", "gate_results_each"},
        f"{path}.evidence.gate_evaluation_completed",
    )
    _exact(gates["count"], 2, f"{path}.evidence.gate_evaluation_completed.count")
    _exact(
        gates["initial_blocked"], True, f"{path}.evidence.gate_evaluation_completed.initial_blocked"
    )
    _exact(
        gates["healed_blocked"], True, f"{path}.evidence.gate_evaluation_completed.healed_blocked"
    )
    _integer(
        gates["gate_results_each"],
        f"{path}.evidence.gate_evaluation_completed.gate_results_each",
        minimum=1,
    )
    _validate_score(evidence["score_observed"], f"{path}.evidence.score_observed", count=2)
    _validate_healing_counts(evidence["healing"], f"{path}.evidence.healing", initial, healed)
    blocked = _object(evidence["workflow_blocked"], f"{path}.evidence.workflow_blocked")
    _exact_keys(blocked, {"count", "reason"}, f"{path}.evidence.workflow_blocked")
    _exact(blocked["count"], 1, f"{path}.evidence.workflow_blocked.count")
    if blocked["reason"] != "bound_healing:repeated_failure":
        raise RolloutEvidenceError(
            f"{path}.evidence.workflow_blocked.reason must prove repeated_failure"
        )
    _validate_pr(evidence["pr_created"], f"{path}.evidence.pr_created", expected_count=0)


def _validate_state_hashes(value: Any, path: str) -> dict[str, str]:
    hashes = _object(value, path)
    _exact_keys(hashes, set(_STABLE_STORES), path)
    return {name: _digest(hashes[name], f"{path}.{name}") for name in sorted(hashes)}


def _validate_legacy_rollback(case: dict[str, Any], subject: dict[str, str], path: str) -> None:
    evidence = _object(case["evidence"], f"{path}.evidence")
    _exact_keys(
        evidence,
        {
            "drill_observed_at",
            "runtime_revision",
            "transitions",
            "data_migration",
            "mixed_state",
            "state_hashes",
            "implementation",
        },
        f"{path}.evidence",
    )
    _utc_timestamp(evidence["drill_observed_at"], f"{path}.evidence.drill_observed_at")
    _full_sha(evidence["runtime_revision"], f"{path}.evidence.runtime_revision")
    _exact(evidence["data_migration"], False, f"{path}.evidence.data_migration")
    _exact(evidence["mixed_state"], False, f"{path}.evidence.mixed_state")

    transitions = _list(evidence["transitions"], f"{path}.evidence.transitions")
    if len(transitions) != 3:
        raise RolloutEvidenceError(f"{path}.evidence.transitions must contain bound/legacy/bound")
    expected = (
        ("bound_gate_authority", "default", True, False, False),
        ("legacy_score_authority", "legacy", False, True, True),
        ("bound_gate_authority", "default", True, False, False),
    )
    for index, (raw, values) in enumerate(zip(transitions, expected, strict=True)):
        transition_path = f"{path}.evidence.transitions[{index}]"
        transition = _object(raw, transition_path)
        _exact_keys(
            transition,
            {
                "authority_mode",
                "gate_profile",
                "policy_version",
                "policy_digest",
                "bound_healing_active",
                "gate_10_required",
                "legacy_steps_active",
            },
            transition_path,
        )
        authority, profile, healing, gate_10, legacy_steps = values
        _exact(transition["authority_mode"], authority, f"{transition_path}.authority_mode")
        _exact(transition["gate_profile"], profile, f"{transition_path}.gate_profile")
        _text(transition["policy_version"], f"{transition_path}.policy_version")
        _digest(transition["policy_digest"], f"{transition_path}.policy_digest")
        _exact(
            transition["bound_healing_active"], healing, f"{transition_path}.bound_healing_active"
        )
        _exact(transition["gate_10_required"], gate_10, f"{transition_path}.gate_10_required")
        _exact(
            transition["legacy_steps_active"],
            legacy_steps,
            f"{transition_path}.legacy_steps_active",
        )
    for index in (0, 2):
        transition = transitions[index]
        if (
            transition["policy_version"] != subject["policy_version"]
            or transition["policy_digest"] != subject["policy_digest"]
        ):
            raise RolloutEvidenceError(
                f"{path}.evidence.transitions[{index}] must match the bound reference subject policy"
            )

    state_hashes = _object(evidence["state_hashes"], f"{path}.evidence.state_hashes")
    _exact_keys(state_hashes, {"before", "legacy", "after"}, f"{path}.evidence.state_hashes")
    before = _validate_state_hashes(state_hashes["before"], f"{path}.evidence.state_hashes.before")
    legacy = _validate_state_hashes(state_hashes["legacy"], f"{path}.evidence.state_hashes.legacy")
    after = _validate_state_hashes(state_hashes["after"], f"{path}.evidence.state_hashes.after")
    if not (before == legacy == after):
        raise RolloutEvidenceError(f"{path}.evidence.state_hashes must prove no data migration")

    implementation = _object(evidence["implementation"], f"{path}.evidence.implementation")
    _exact_keys(
        implementation,
        {"issue", "pr", "source_sha", "merge_sha", "pr_ci_run", "push_ci_run"},
        f"{path}.evidence.implementation",
    )
    _exact(implementation["issue"], 579, f"{path}.evidence.implementation.issue")
    _exact(implementation["pr"], 590, f"{path}.evidence.implementation.pr")
    _full_sha(implementation["source_sha"], f"{path}.evidence.implementation.source_sha")
    _full_sha(implementation["merge_sha"], f"{path}.evidence.implementation.merge_sha")
    _integer(implementation["pr_ci_run"], f"{path}.evidence.implementation.pr_ci_run", minimum=1)
    _integer(
        implementation["push_ci_run"], f"{path}.evidence.implementation.push_ci_run", minimum=1
    )


_CASE_VALIDATORS = {
    "success": _validate_success,
    "required_gate_block": _validate_required_block,
    "evidence_healing_new_head": _validate_healing,
    "terminal_refail": _validate_terminal_refail,
    "legacy_rollback": _validate_legacy_rollback,
}


def validate_rollout_evidence(
    document: Any,
    *,
    schema_name: str,
    schema_digest: str,
) -> None:
    """Validate one complete, closed-world rollout evidence document."""

    root = _object(document, "rollout")
    _exact_keys(
        root,
        {
            "schema_version",
            "schema",
            "schema_digest",
            "decision_issue",
            "rollout_issue",
            "generated_at",
            "cases",
        },
        "rollout",
    )
    _exact(root["schema_version"], SCHEMA_VERSION, "rollout.schema_version")
    _exact(root["schema"], schema_name, "rollout.schema")
    _exact(root["schema_digest"], schema_digest, "rollout.schema_digest")
    _exact(root["decision_issue"], 399, "rollout.decision_issue")
    _exact(root["rollout_issue"], 577, "rollout.rollout_issue")
    _utc_timestamp(root["generated_at"], "rollout.generated_at")

    cases = _list(root["cases"], "rollout.cases")
    if len(cases) != len(REQUIRED_CASE_IDS):
        raise RolloutEvidenceError("rollout.cases must contain each required case exactly once")
    seen: set[str] = set()
    repository: str | None = None
    for index, raw_case in enumerate(cases):
        path = f"rollout.cases[{index}]"
        case = _object(raw_case, path)
        _exact_keys(case, {"id", "result", "run", "subject", "evidence"}, path)
        case_id = _text(case["id"], f"{path}.id")
        if case_id not in REQUIRED_CASE_IDS:
            raise RolloutEvidenceError(f"{path}.id is not a required rollout case")
        if case_id in seen:
            raise RolloutEvidenceError(f"duplicate rollout case: {case_id}")
        seen.add(case_id)
        _exact(case["result"], "passed", f"{path}.result")
        subject = _validate_subject(case["subject"], f"{path}.subject")
        _validate_run(case["run"], f"{path}.run", subject["repository"])
        if repository is None:
            repository = subject["repository"]
        elif subject["repository"] != repository:
            raise RolloutEvidenceError("all rollout cases must identify the same repository")
        _CASE_VALIDATORS[case_id](case, subject, path)

    missing = sorted(REQUIRED_CASE_IDS - seen)
    if missing:
        raise RolloutEvidenceError("missing rollout cases: " + ", ".join(missing))


def load_and_validate_rollout_evidence(evidence_path: Path, schema_path: Path) -> None:
    """Load the checked-in schema/evidence pair and bind evidence to schema bytes."""

    try:
        schema_bytes = schema_path.read_bytes()
        schema = json.loads(schema_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise RolloutEvidenceError(f"rollout evidence schema cannot be read: {exc}") from exc
    schema_object = _object(schema, "schema")
    if schema_object.get("$id") != schema_path.name:
        raise RolloutEvidenceError("rollout evidence schema $id must match its filename")
    if schema_object.get("version") != SCHEMA_VERSION:
        raise RolloutEvidenceError(f"rollout evidence schema version must be {SCHEMA_VERSION}")
    schema_digest = "sha256:" + hashlib.sha256(schema_bytes).hexdigest()

    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RolloutEvidenceError(
            f"bound-authority rollout evidence cannot be read: {exc}"
        ) from exc
    validate_rollout_evidence(
        evidence,
        schema_name=schema_path.name,
        schema_digest=schema_digest,
    )
