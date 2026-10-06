"""Persisted, passive health/readiness/qualification projections."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from samuel.core.ports import IRunProjectionStore
from samuel.core.state import RunProjectionRecord

log = logging.getLogger(__name__)

SERIES = "health-readiness.v1"
DEFAULT_MAX_AGE_SECONDS = 3600
KINDS = (
    "technical_health",
    "operational_readiness",
    "doctor",
    "audit_integrity",
)
STATUSES = {
    "technical_health": frozenset({"passed", "failed"}),
    "operational_readiness": frozenset({"ready", "blocked", "unknown"}),
    "doctor": frozenset({"passed", "failed", "not_checked"}),
    "audit_integrity": frozenset({"passed", "failed", "not_checked"}),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def record_projection(
    store: IRunProjectionStore,
    *,
    kind: str,
    status: str,
    instance_uuid: str,
    summary: dict[str, Any],
    observed_at: datetime | None = None,
    preserve_current_failure: bool = False,
) -> RunProjectionRecord:
    """Replace one bounded status projection without granting authority."""

    if kind not in KINDS:
        raise ValueError(f"unsupported readiness projection kind: {kind}")
    if status not in STATUSES[kind]:
        raise ValueError(f"unsupported {kind} projection status: {status}")
    at = observed_at or _now()
    projection_key = f"health-readiness:{kind}"
    previous = store.get_projection(projection_key)
    if (
        preserve_current_failure
        and status == "not_checked"
        and previous is not None
        and previous.status == "failed"
    ):
        return previous
    resolved_finding: dict[str, str] | None = None
    if (
        status == "passed"
        and previous is not None
        and previous.status == "failed"
        and str(previous.payload.get("instance_uuid", "")) == instance_uuid
    ):
        resolved_finding = {
            "evidence_digest": str(previous.payload.get("evidence_digest", "")),
            "checked_at": str(previous.payload.get("checked_at", previous.updated_at.isoformat())),
        }
    facts = {
        "schema": SERIES,
        "kind": kind,
        "status": status,
        "instance_uuid": instance_uuid,
        "checked_at": at.isoformat(),
        "summary": summary,
        "resolved_finding": resolved_finding,
    }
    record = RunProjectionRecord(
        projection_key=projection_key,
        issue_number=0,
        correlation_id="",
        series=SERIES,
        status=status,
        payload={**facts, "evidence_digest": _digest(facts)},
        updated_at=at,
    )
    store.upsert_projection(record)
    return record


def snapshot(
    store: IRunProjectionStore | None,
    *,
    instance_uuid: str,
    now: datetime | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Read current projections; missing, restored, or old evidence never passes."""

    current_time = now or _now()
    try:
        rows = store.list_projections(series=SERIES) if store is not None else []
    except Exception as exc:  # noqa: BLE001 - projection reads are explicitly non-blocking
        log.warning("Readiness projection unavailable: %s", type(exc).__name__)
        rows = []
    by_kind = {
        str(row.payload.get("kind")): row for row in rows if str(row.payload.get("kind")) in KINDS
    }
    result: dict[str, Any] = {}
    for kind in KINDS:
        row = by_kind.get(kind)
        if row is None:
            result[kind] = {
                "status": "not_checked",
                "lifecycle": "not_checked",
                "current": False,
            }
            continue
        same_instance = str(row.payload.get("instance_uuid", "")) == instance_uuid
        age = current_time - row.updated_at
        fresh = timedelta(0) <= age <= timedelta(seconds=max_age_seconds)
        current = same_instance and fresh
        result[kind] = {
            "status": row.status if current else "stale",
            "result": row.status,
            "lifecycle": (
                "stale"
                if not current
                else "resolved"
                if row.status == "passed" and row.payload.get("resolved_finding")
                else "active"
            ),
            "current": current,
            "checked_at": str(row.payload.get("checked_at", row.updated_at.isoformat())),
            "evidence_digest": str(row.payload.get("evidence_digest", "")),
            "summary": dict(row.payload.get("summary", {})),
            "resolved_finding": row.payload.get("resolved_finding"),
            "stale_reason": (
                None
                if current
                else "instance_changed"
                if not same_instance
                else "timestamp_in_future"
                if age < timedelta(0)
                else "evidence_expired"
            ),
        }
    qualification_rows = [result[name] for name in ("doctor", "audit_integrity")]
    if any(row["status"] == "failed" for row in qualification_rows):
        qualification_status = "failed"
    elif all(row["status"] == "passed" for row in qualification_rows):
        qualification_status = "passed"
    else:
        qualification_status = "not_checked"
    return {
        "technical_health": result["technical_health"],
        "operational_readiness": result["operational_readiness"],
        "qualification": {
            "status": qualification_status,
            "doctor": result["doctor"],
            "audit_integrity": result["audit_integrity"],
        },
    }
