"""Non-binding score derivation from commit-bound acceptance evidence."""

from __future__ import annotations

from typing import Any

from samuel.core.config import EvalSchema

TAG_CATEGORIES = {
    "TEST": "test_pass_rate",
    "IMPORT": "syntax_valid",
    "DIFF": "hallucination_free",
    "EXISTS": "hallucination_free",
    "GREP": "scope_compliant",
    "GREP:NOT": "scope_compliant",
}

_EVALUATED_STATUSES = frozenset({"passed", "failed"})
_KNOWN_STATUSES = frozenset(
    {
        "passed",
        "failed",
        "manual_pending",
        "not_applicable",
        "missing_evidence",
        "error",
    }
)
MAX_CRITERIA_PER_OBSERVATION = 10_000


def derive_bound_score(
    acceptance_evidence: dict[str, Any] | None,
    config: EvalSchema,
) -> dict[str, Any]:
    """Derive one replayable telemetry value without release semantics."""

    if not isinstance(acceptance_evidence, dict):
        return _not_scoreable(config, "missing_acceptance_evidence")
    raw_results = acceptance_evidence.get("results")
    if not isinstance(raw_results, list):
        return _not_scoreable(config, "invalid_acceptance_evidence")
    if len(raw_results) > MAX_CRITERIA_PER_OBSERVATION:
        return _not_scoreable(config, "criteria_limit_exceeded")

    criteria: list[dict[str, Any]] = []
    category_values: dict[str, list[float]] = {name: [] for name in config.weights}
    category_present: dict[str, int] = {name: 0 for name in config.weights}
    automatic_total = 0
    automatic_evaluated = 0
    unmapped: list[str] = []

    for raw in raw_results:
        if not isinstance(raw, dict):
            return _not_scoreable(config, "invalid_criterion_result")
        criterion_id = str(raw.get("criterion_id", ""))
        tag = str(raw.get("tag", ""))
        status = str(raw.get("status", ""))
        if not criterion_id or not tag or status not in _KNOWN_STATUSES:
            return _not_scoreable(config, "invalid_criterion_result")
        mode = "manual" if tag == "MANUAL" else "automatic"
        applicable = status != "not_applicable"
        category = TAG_CATEGORIES.get(tag)
        criteria.append(
            {
                "criterion_id": criterion_id,
                "tag": tag,
                "status": status,
                "mode": mode,
                "applicable": applicable,
                "category": category,
                "evidence_source": "bound_acceptance_evidence",
            }
        )
        if mode == "manual":
            continue
        automatic_total += 1
        if status in _EVALUATED_STATUSES:
            automatic_evaluated += 1
        if category is None:
            unmapped.append(criterion_id)
            continue
        if status == "not_applicable":
            continue
        category_present[category] = category_present.get(category, 0) + 1
        if status in _EVALUATED_STATUSES:
            category_values.setdefault(category, []).append(1.0 if status == "passed" else 0.0)

    if unmapped:
        return _not_scoreable(
            config,
            "unmapped_automatic_criteria",
            criteria=criteria,
            coverage=_coverage(automatic_evaluated, automatic_total),
        )

    categories: dict[str, dict[str, Any]] = {}
    weighted = 0.0
    applicable_weight = 0.0
    for name, weight in config.weights.items():
        values = category_values.get(name, [])
        applicable = bool(values)
        category_score = round(sum(values) / len(values), 4) if values else None
        categories[name] = {
            "applicable": applicable,
            "score": category_score,
            "weight": weight,
            "criteria_total": category_present.get(name, 0),
            "criteria_evaluated": len(values),
            "criteria_passed": sum(1 for value in values if value == 1.0),
        }
        if category_score is not None:
            weighted += category_score * weight
            applicable_weight += weight

    if applicable_weight == 0:
        return _not_scoreable(
            config,
            "no_automatic_applicable_criteria",
            criteria=criteria,
            categories=categories,
            coverage=_coverage(automatic_evaluated, automatic_total),
        )
    return {
        "score": round(weighted / applicable_weight, 4),
        "scoreability": "scoreable",
        "not_scoreable_reason": None,
        "criteria": criteria,
        "categories": categories,
        "coverage": _coverage(automatic_evaluated, automatic_total),
        "applicable_weight": round(applicable_weight, 4),
        "non_binding": True,
    }


def _coverage(evaluated: int, total: int) -> dict[str, Any]:
    return {
        "automatic_total": total,
        "automatic_evaluated": evaluated,
        "ratio": round(evaluated / total, 4) if total else None,
    }


def _not_scoreable(
    config: EvalSchema,
    reason: str,
    *,
    criteria: list[dict[str, Any]] | None = None,
    categories: dict[str, dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "score": None,
        "scoreability": "not_scoreable",
        "not_scoreable_reason": reason,
        "criteria": criteria or [],
        "categories": categories
        or {
            name: {
                "applicable": False,
                "score": None,
                "weight": weight,
                "criteria_total": 0,
                "criteria_evaluated": 0,
                "criteria_passed": 0,
            }
            for name, weight in config.weights.items()
        },
        "coverage": coverage or _coverage(0, 0),
        "applicable_weight": 0.0,
        "non_binding": True,
    }
