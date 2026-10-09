"""Offline validation for the real-port preflight rollout evidence (#620/#653)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from samuel.core.evaluation_observation import (
    ScoreDerivationIdentity,
    validate_completed_observation,
)
from samuel.core.evaluation_subject import EvaluationSubject

SCHEMA_VERSION = "1.0"
REQUIRED_CASE_IDS = frozenset(
    {
        "success",
        "scope_fail",
        "syntax_fail",
        "freshness_unknown",
        "subject_unavailable",
        "gate11_healable",
    }
)
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")


class PreflightRolloutEvidenceError(ValueError):
    """Checked-in #620 rollout evidence violates its closed contract."""


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PreflightRolloutEvidenceError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise PreflightRolloutEvidenceError(f"{path} must be a list")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise PreflightRolloutEvidenceError(f"{path} has invalid fields: {'; '.join(details)}")


def _text(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise PreflightRolloutEvidenceError(f"{path} must be a canonical non-empty string")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PreflightRolloutEvidenceError(f"{path} must be an integer >= {minimum}")
    return value


def _exact(value: Any, expected: Any, path: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise PreflightRolloutEvidenceError(f"{path} must be {expected!r}")


def _digest(value: Any, path: str) -> str:
    text = _text(value, path)
    if _DIGEST_RE.fullmatch(text) is None:
        raise PreflightRolloutEvidenceError(f"{path} must be a sha256 digest")
    return text


def _sha(value: Any, path: str) -> str:
    text = _text(value, path)
    if _SHA_RE.fullmatch(text) is None:
        raise PreflightRolloutEvidenceError(f"{path} must be a full Git SHA-1")
    return text


def _url(value: Any, path: str) -> str:
    text = _text(value, path)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PreflightRolloutEvidenceError(f"{path} must be an absolute HTTP(S) URL")
    return text


def _timestamp(value: Any, path: str) -> str:
    text = _text(value, path)
    if _TIMESTAMP_RE.fullmatch(text) is None:
        raise PreflightRolloutEvidenceError(f"{path} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise PreflightRolloutEvidenceError(f"{path} must be a valid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise PreflightRolloutEvidenceError(f"{path} must use UTC")
    return text


def _validate_run(value: Any, path: str, repository: str) -> None:
    run = _object(value, path)
    _exact_keys(
        run,
        {"issue_number", "issue_url", "evidence_comment_id", "evidence_comment_url"},
        path,
    )
    number = _integer(run["issue_number"], f"{path}.issue_number", minimum=1)
    issue_url = _url(run["issue_url"], f"{path}.issue_url")
    if issue_url != f"{repository.rstrip('/')}/issues/{number}":
        raise PreflightRolloutEvidenceError(f"{path}.issue_url must bind the fixture issue")
    comment_id = _integer(run["evidence_comment_id"], f"{path}.evidence_comment_id", minimum=1)
    comment_url = _url(run["evidence_comment_url"], f"{path}.evidence_comment_url")
    if comment_url != f"{issue_url}#issuecomment-{comment_id}":
        raise PreflightRolloutEvidenceError(
            f"{path}.evidence_comment_url must bind the immutable evidence comment"
        )


_CASE_KEYS = {
    "id",
    "result",
    "run",
    "branch",
    "correlation_id",
    "verifier_dispatches",
    "terminal",
    "subject",
    "gate_results",
    "acceptance_evidence",
    "score_observation",
    "healing",
    "candidate_process_events",
    "fault_injection",
    "pr",
}


def _validate_subject(value: Any, path: str, repository: str) -> EvaluationSubject:
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
        },
        path,
    )
    try:
        parsed = EvaluationSubject.from_dict(subject)
    except ValueError as exc:
        raise PreflightRolloutEvidenceError(f"{path} is invalid: {exc}") from exc
    if parsed.repository != repository:
        raise PreflightRolloutEvidenceError(f"{path}.repository must match rollout.repository")
    if parsed.base_sha == parsed.head_sha:
        raise PreflightRolloutEvidenceError(f"{path} base/head must differ")
    return parsed


def _gate_map(case: dict[str, Any], path: str) -> dict[str, dict[str, Any]]:
    results = _list(case["gate_results"], f"{path}.gate_results")
    mapped: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(results):
        result = _object(raw, f"{path}.gate_results[{index}]")
        gate = str(result.get("gate"))
        if gate in mapped:
            raise PreflightRolloutEvidenceError(f"{path} contains duplicate gate {gate}")
        mapped[gate] = result
    return mapped


def _assert_gate(
    gates: dict[str, dict[str, Any]],
    gate: str,
    *,
    passed: bool | None,
    executed: bool,
    status: str,
    path: str,
) -> None:
    if gate not in gates:
        raise PreflightRolloutEvidenceError(f"{path} is missing gate {gate}")
    result = gates[gate]
    _exact(result.get("passed"), passed, f"{path}.gate[{gate}].passed")
    _exact(result.get("executed"), executed, f"{path}.gate[{gate}].executed")
    _exact(result.get("status"), status, f"{path}.gate[{gate}].status")
    _exact(result.get("authority"), "required", f"{path}.gate[{gate}].authority")


def _validate_score(case: dict[str, Any], path: str, *, completed: bool) -> None:
    score = _object(case["score_observation"], f"{path}.score_observation")
    _exact_keys(
        score,
        {
            "count",
            "score",
            "scoreability",
            "not_scoreable_reason",
            "non_binding",
            "observation_key",
            "evidence_digest",
            "score_key",
            "scoring_policy_version",
            "scoring_policy_digest",
            "formula_version",
        },
        f"{path}.score_observation",
    )
    if not completed:
        _exact(score["count"], 0, f"{path}.score_observation.count")
        if any(value is not None for key, value in score.items() if key != "count"):
            raise PreflightRolloutEvidenceError(
                f"{path}.score_observation must be empty for unavailable subjects"
            )
        return
    _exact(score["count"], 1, f"{path}.score_observation.count")
    _exact(score["non_binding"], True, f"{path}.score_observation.non_binding")
    terminal = case["terminal"]
    _exact(
        score["observation_key"],
        terminal["observation_key"],
        f"{path}.score_observation.observation_key",
    )
    _exact(
        score["evidence_digest"],
        terminal["evidence_digest"],
        f"{path}.score_observation.evidence_digest",
    )
    expected = ScoreDerivationIdentity.build(
        observation_key=_digest(score["observation_key"], f"{path}.score.observation_key"),
        scoring_policy_version=_text(
            score["scoring_policy_version"], f"{path}.score.scoring_policy_version"
        ),
        scoring_policy_digest=_digest(
            score["scoring_policy_digest"], f"{path}.score.scoring_policy_digest"
        ),
        formula_version=_text(score["formula_version"], f"{path}.score.formula_version"),
    )
    _exact(score["score_key"], expected.score_key, f"{path}.score_observation.score_key")


def _validate_healing(case: dict[str, Any], path: str, *, completed: bool) -> None:
    healing = _object(case["healing"], f"{path}.healing")
    _exact_keys(healing, {"count", "classification", "reason", "llm_calls", "claims"}, path)
    _exact(healing["llm_calls"], 0, f"{path}.healing.llm_calls")
    _exact(healing["claims"], 0, f"{path}.healing.claims")
    if completed:
        _exact(healing["count"], 1, f"{path}.healing.count")
        _text(healing["classification"], f"{path}.healing.classification")
        _text(healing["reason"], f"{path}.healing.reason")
    else:
        _exact(healing["count"], 0, f"{path}.healing.count")
        _exact(healing["classification"], None, f"{path}.healing.classification")
        _exact(healing["reason"], None, f"{path}.healing.reason")


def _validate_pr(case: dict[str, Any], path: str, *, expected: int) -> None:
    pr = _object(case["pr"], f"{path}.pr")
    _exact_keys(pr, {"count", "number", "url", "base_sha", "head_sha"}, f"{path}.pr")
    _exact(pr["count"], expected, f"{path}.pr.count")
    if expected == 0:
        if any(value is not None for key, value in pr.items() if key != "count"):
            raise PreflightRolloutEvidenceError(f"{path}.pr must not claim a PR")
        return
    subject = _object(case["subject"], f"{path}.subject")
    _integer(pr["number"], f"{path}.pr.number", minimum=1)
    _url(pr["url"], f"{path}.pr.url")
    _exact(pr["base_sha"], subject["base_sha"], f"{path}.pr.base_sha")
    _exact(pr["head_sha"], subject["head_sha"], f"{path}.pr.head_sha")


def _validate_completed(case: dict[str, Any], path: str, repository: str) -> None:
    subject = _validate_subject(case["subject"], f"{path}.subject", repository)
    terminal = _object(case["terminal"], f"{path}.terminal")
    _exact(terminal["event"], "GateEvaluationCompleted", f"{path}.terminal.event")
    _exact(terminal["count"], 1, f"{path}.terminal.count")
    _timestamp(terminal["observed_at"], f"{path}.terminal.observed_at")
    _exact(terminal["terminal_key"], None, f"{path}.terminal.terminal_key")
    _exact(terminal["status"], None, f"{path}.terminal.status")
    _exact(terminal["error_code"], None, f"{path}.terminal.error_code")
    _exact(terminal["gate_result_schema_version"], 2, f"{path}.terminal.gate schema")
    _exact(terminal["observation_schema_version"], 2, f"{path}.terminal.observation schema")
    observation_key = _digest(terminal["observation_key"], f"{path}.terminal.observation_key")
    evidence_digest = _digest(terminal["evidence_digest"], f"{path}.terminal.evidence_digest")
    payload = {
        "evaluation_subject": subject.as_dict(),
        "gate_results": case["gate_results"],
        "acceptance_evidence": case["acceptance_evidence"],
        "gate_result_schema_version": 2,
        "observation_schema_version": 2,
        "observation_key": observation_key,
        "evidence_digest": evidence_digest,
    }
    try:
        _, identity = validate_completed_observation(payload)
    except ValueError as exc:
        raise PreflightRolloutEvidenceError(f"{path} observation is invalid: {exc}") from exc
    _exact(identity.observation_key, observation_key, f"{path}.terminal.observation_key")
    _validate_score(case, path, completed=True)
    _validate_healing(case, path, completed=True)


def _validate_unavailable(case: dict[str, Any], path: str) -> None:
    _exact(case["subject"], None, f"{path}.subject")
    _exact(case["acceptance_evidence"], None, f"{path}.acceptance_evidence")
    _exact(case["gate_results"], [], f"{path}.gate_results")
    _exact(case["verifier_dispatches"], 0, f"{path}.verifier_dispatches")
    terminal = _object(case["terminal"], f"{path}.terminal")
    _exact(terminal["event"], "GateEvaluationUnavailable", f"{path}.terminal.event")
    _exact(terminal["count"], 1, f"{path}.terminal.count")
    _timestamp(terminal["observed_at"], f"{path}.terminal.observed_at")
    _digest(terminal["terminal_key"], f"{path}.terminal.terminal_key")
    for field in (
        "observation_key",
        "evidence_digest",
        "gate_result_schema_version",
        "observation_schema_version",
    ):
        _exact(terminal[field], None, f"{path}.terminal.{field}")
    _exact(terminal["status"], "not_evaluated", f"{path}.terminal.status")
    _exact(terminal["error_code"], "subject_resolution_failed", f"{path}.terminal.error_code")
    _validate_score(case, path, completed=False)
    _validate_healing(case, path, completed=False)
    _validate_pr(case, path, expected=0)


def _validate_case_semantics(case: dict[str, Any], path: str) -> None:
    case_id = str(case["id"])
    processes = _object(case["candidate_process_events"], f"{path}.candidate_process_events")
    _exact_keys(processes, {"test_run_completed"}, f"{path}.candidate_process_events")
    test_runs = _integer(processes["test_run_completed"], f"{path}.test_run_completed")
    gates = _gate_map(case, path)
    score = case["score_observation"]
    healing = case["healing"]

    if case_id == "success":
        _exact(list(gates), ["7b", "8", "9", "13a", "13b", "11"], f"{path}.gates")
        for gate in gates:
            _assert_gate(gates, gate, passed=True, executed=True, status="passed", path=path)
        _exact(case["verifier_dispatches"], 1, f"{path}.verifier_dispatches")
        _exact(score["scoreability"], "scoreable", f"{path}.scoreability")
        _exact(score["score"], 1.0, f"{path}.score")
        _exact(healing["classification"], "not_needed", f"{path}.healing.classification")
        _validate_pr(case, path, expected=1)
    elif case_id in {"scope_fail", "syntax_fail"}:
        failed_gate = "7b" if case_id == "scope_fail" else "9"
        _assert_gate(gates, failed_gate, passed=False, executed=True, status="failed", path=path)
        _assert_gate(
            gates,
            "11",
            passed=None,
            executed=False,
            status="skipped_precondition",
            path=path,
        )
        _exact(case["verifier_dispatches"], 0, f"{path}.verifier_dispatches")
        _exact(test_runs, 0, f"{path}.test_run_completed")
        _exact(score["scoreability"], "not_scoreable", f"{path}.scoreability")
        _exact(score["score"], None, f"{path}.score")
        _exact(
            score["not_scoreable_reason"],
            "missing_acceptance_evidence",
            f"{path}.not_scoreable_reason",
        )
        _exact(healing["classification"], "not_healable", f"{path}.healing.classification")
        _exact(healing["reason"], "gate_11_not_failed", f"{path}.healing.reason")
        _validate_pr(case, path, expected=0)
    elif case_id == "freshness_unknown":
        _exact(list(gates), ["13a", "11"], f"{path}.gates")
        _assert_gate(gates, "13a", passed=False, executed=True, status="failed", path=path)
        _assert_gate(
            gates, "11", passed=None, executed=False, status="skipped_precondition", path=path
        )
        _exact(case["verifier_dispatches"], 0, f"{path}.verifier_dispatches")
        fault = _object(case["fault_injection"], f"{path}.fault_injection")
        _exact_keys(
            fault,
            {"kind", "comparison_completed", "local_git_metadata_hidden", "restored"},
            f"{path}.fault_injection",
        )
        _exact(fault["kind"], "bound_objects_unavailable_after_comparison", f"{path}.fault.kind")
        for key in ("comparison_completed", "local_git_metadata_hidden", "restored"):
            _exact(fault[key], True, f"{path}.fault.{key}")
        _exact(score["scoreability"], "not_scoreable", f"{path}.scoreability")
        _validate_pr(case, path, expected=0)
    elif case_id == "gate11_healable":
        for gate in ("7b", "8", "9", "13a", "13b"):
            _assert_gate(gates, gate, passed=True, executed=True, status="passed", path=path)
        _assert_gate(gates, "11", passed=False, executed=True, status="failed", path=path)
        _exact(case["verifier_dispatches"], 1, f"{path}.verifier_dispatches")
        acceptance = _object(case["acceptance_evidence"], f"{path}.acceptance_evidence")
        results = _list(acceptance.get("results"), f"{path}.acceptance_evidence.results")
        failed = [
            item for item in results if isinstance(item, dict) and item.get("status") == "failed"
        ]
        if len(failed) != 1 or not isinstance(failed[0].get("evidence"), dict):
            raise PreflightRolloutEvidenceError(
                f"{path} must contain exactly one actionable failed criterion"
            )
        _exact(healing["classification"], "healable", f"{path}.healing.classification")
        _exact(healing["reason"], "single_automatic_failure", f"{path}.healing.reason")
        _validate_pr(case, path, expected=0)
    elif case_id == "subject_unavailable":
        _validate_unavailable(case, path)
    else:
        raise PreflightRolloutEvidenceError(f"unknown case {case_id}")

    if case_id != "freshness_unknown":
        _exact(case["fault_injection"], None, f"{path}.fault_injection")


def validate_preflight_rollout_evidence(
    document: Any,
    *,
    schema_name: str,
    schema_digest: str,
) -> None:
    rollout = _object(document, "rollout")
    _exact_keys(
        rollout,
        {
            "schema_version",
            "schema",
            "schema_digest",
            "decision_issue",
            "rollout_issue",
            "product_commit",
            "generated_at",
            "repository",
            "cases",
        },
        "rollout",
    )
    _exact(rollout["schema_version"], SCHEMA_VERSION, "rollout.schema_version")
    _exact(rollout["schema"], schema_name, "rollout.schema")
    _exact(rollout["schema_digest"], schema_digest, "rollout.schema_digest")
    _exact(rollout["decision_issue"], 620, "rollout.decision_issue")
    _exact(rollout["rollout_issue"], 653, "rollout.rollout_issue")
    _sha(rollout["product_commit"], "rollout.product_commit")
    _timestamp(rollout["generated_at"], "rollout.generated_at")
    repository = _url(rollout["repository"], "rollout.repository")
    cases = _list(rollout["cases"], "rollout.cases")
    if len(cases) != len(REQUIRED_CASE_IDS):
        raise PreflightRolloutEvidenceError("rollout must contain exactly six cases")
    seen: set[str] = set()
    for index, raw_case in enumerate(cases):
        path = f"rollout.cases[{index}]"
        case = _object(raw_case, path)
        _exact_keys(case, _CASE_KEYS, path)
        case_id = _text(case["id"], f"{path}.id")
        if case_id not in REQUIRED_CASE_IDS or case_id in seen:
            raise PreflightRolloutEvidenceError(f"invalid or duplicate rollout case: {case_id}")
        seen.add(case_id)
        _exact(case["result"], "passed", f"{path}.result")
        _text(case["branch"], f"{path}.branch")
        _text(case["correlation_id"], f"{path}.correlation_id")
        _validate_run(case["run"], f"{path}.run", repository)
        if case_id != "subject_unavailable":
            _validate_completed(case, path, repository)
        _validate_case_semantics(case, path)
    if seen != REQUIRED_CASE_IDS:
        raise PreflightRolloutEvidenceError("each required rollout case must occur once")


def load_and_validate_preflight_rollout_evidence(
    evidence_path: Path,
    schema_path: Path,
) -> None:
    try:
        schema_bytes = schema_path.read_bytes()
        schema = json.loads(schema_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightRolloutEvidenceError(f"schema cannot be read: {exc}") from exc
    schema_object = _object(schema, "schema")
    if schema_object.get("$id") != schema_path.name:
        raise PreflightRolloutEvidenceError("schema $id must match its filename")
    if schema_object.get("version") != SCHEMA_VERSION:
        raise PreflightRolloutEvidenceError(f"schema version must be {SCHEMA_VERSION}")
    schema_digest = "sha256:" + hashlib.sha256(schema_bytes).hexdigest()
    try:
        document = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightRolloutEvidenceError(f"evidence cannot be read: {exc}") from exc
    validate_preflight_rollout_evidence(
        document,
        schema_name=schema_path.name,
        schema_digest=schema_digest,
    )
