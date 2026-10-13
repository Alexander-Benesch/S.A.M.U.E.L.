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
        "audit_writer": audit_writer_snapshot(
            rows, instance_uuid=instance_uuid, now=current_time, max_age_seconds=max_age_seconds
        ),
        "qualification": {
            "status": qualification_status,
            "doctor": result["doctor"],
            "audit_integrity": result["audit_integrity"],
        },
    }


_AUDIT_WRITE_STATES = frozenset(
    {
        "started",
        "primary_written",
        "fallback_written",
        "write_failed",
        "queue_dropped",
        "stopped_event_rejected",
        "shutdown_unconfirmed",
    }
)
_AUDIT_ERROR_CODES = frozenset(
    {
        "",
        "append_refused",
        "permission_denied",
        "no_space",
        "io_error",
        "write_error",
        "queue_full",
        "writer_stopped",
        "drain_timeout",
    }
)


def record_audit_writer(
    store: IRunProjectionStore,
    *,
    instance_uuid: str,
    writer_id: str,
    process_uuid: str,
    state: str,
    primary_error: str = "",
    fallback_error: str = "",
    observed_at: datetime | None = None,
) -> RunProjectionRecord:
    """One bounded diagnostic per JSONL destination in the existing store.

    Atomic replacement protects counters across threads and processes. Startup
    invalidates a previous success, preserves unresolved faults and never proves
    recovery. Only a completed primary append resolves primary degradation.
    Lost-event counts survive that recovery; chain integrity is a separate fact.
    """
    if state not in _AUDIT_WRITE_STATES:
        raise ValueError("unsupported audit writer state")
    if primary_error not in _AUDIT_ERROR_CODES or fallback_error not in _AUDIT_ERROR_CODES:
        raise ValueError("unsupported audit writer error code")
    key = "health-readiness:audit_writer:" + writer_id
    for _ in range(20):
        previous = store.get_projection(key)
        same = previous is not None and previous.payload.get("instance_uuid") == instance_uuid
        old = previous.payload.get("summary", {}) if same and previous else {}
        lost = int(old.get("lost_events", 0)) + int(
            state in {"write_failed", "queue_dropped", "stopped_event_rejected"}
        )
        uncertain = int(old.get("unconfirmed_shutdowns", 0)) + int(state == "shutdown_unconfirmed")
        degraded = bool(old.get("primary_degraded", False))
        resolved = old.get("resolved_finding")
        last_failure = old.get("last_failure")
        if state == "primary_written":
            if degraded or old.get("last_write") in {"write_failed", "shutdown_unconfirmed"}:
                resolved = (
                    {
                        "evidence_digest": previous.payload.get("evidence_digest", ""),
                        "checked_at": previous.updated_at.isoformat(),
                    }
                    if previous
                    else None
                )
            degraded = False
        elif state in {"fallback_written", "write_failed"}:
            degraded = True
        if state not in {"started", "primary_written"}:
            last_failure = {
                "state": state,
                "primary_error": primary_error,
                "fallback_error": fallback_error,
                "process_uuid": process_uuid,
            }
        last_write = state if state != "started" else "not_checked"
        status = (
            "loss_detected"
            if lost
            else "degraded"
            if degraded
            else "unknown"
            if state in {"started", "shutdown_unconfirmed"}
            else "written"
        )
        at = observed_at or _now()
        summary = {
            "writer_id": writer_id,
            "sink": "jsonl",
            "process_uuid": process_uuid,
            "last_write": last_write,
            "primary_degraded": degraded,
            "lost_events": lost,
            "unconfirmed_shutdowns": uncertain,
            "fallback_events": int(old.get("fallback_events", 0))
            + int(state == "fallback_written"),
            "last_failure": last_failure,
            "resolved_finding": resolved,
            "integrity_verified": False,
            "completeness_proven": False,
            "previous_instance_finding": (
                old.get("previous_instance_finding")
                if same
                else {
                    "instance_uuid": previous.payload.get("instance_uuid"),
                    "result": previous.status,
                    "evidence_digest": previous.payload.get("evidence_digest"),
                    "lost_events": previous.payload.get("summary", {}).get("lost_events", 0),
                }
                if previous
                else None
            ),
        }
        facts = {
            "schema": SERIES,
            "kind": "audit_writer",
            "status": status,
            "instance_uuid": instance_uuid,
            "checked_at": at.isoformat(),
            "summary": summary,
        }
        record = RunProjectionRecord(
            projection_key=key,
            issue_number=0,
            correlation_id="",
            series=SERIES,
            status=status,
            payload={**facts, "evidence_digest": _digest(facts)},
            updated_at=at,
        )
        if store.compare_and_swap_projection(record, previous):
            return record
    raise RuntimeError("audit writer projection contention")


def audit_writer_snapshot(
    rows: list[RunProjectionRecord], *, instance_uuid: str, now: datetime, max_age_seconds: int
) -> dict[str, Any]:
    writers: list[dict[str, Any]] = []
    for row in rows:
        if row.payload.get("kind") != "audit_writer":
            continue
        same = row.payload.get("instance_uuid") == instance_uuid
        fresh = timedelta(0) <= now - row.updated_at <= timedelta(seconds=max_age_seconds)
        current = same and fresh
        writers.append(
            {
                "status": row.status if current else "stale",
                "result": row.status,
                "current": current,
                "checked_at": row.updated_at.isoformat(),
                "evidence_digest": row.payload.get("evidence_digest", ""),
                "summary": dict(row.payload.get("summary", {})),
                "stale_reason": None
                if current
                else "instance_changed"
                if not same
                else "timestamp_in_future"
                if now < row.updated_at
                else "evidence_expired",
            }
        )
    statuses = {writer["status"] for writer in writers}
    status = (
        "loss_detected"
        if "loss_detected" in statuses
        else "degraded"
        if "degraded" in statuses
        else "unknown"
        if not writers or statuses - {"written"}
        else "written"
    )
    return {
        "status": status,
        "writers": writers,
        "scope": "observed_jsonl_writes",
        "integrity_verified": False,
        "completeness_proven": False,
    }
