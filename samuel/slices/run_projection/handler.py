"""Materialize a redacted per-run event view independently of audit rotation."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.events import Event
from samuel.core.ports import IRunProjectionStore
from samuel.core.security_policy import redact_secrets
from samuel.core.state import RunProjectionRecord
from samuel.core.workflow_outcome import WorkflowOutcome, reduce_workflow_outcome

log = logging.getLogger(__name__)

_DROP_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "body",
        "content",
        "credential",
        "credentials",
        "diff",
        "headers",
        "patch",
        "patches",
        "password",
        "prompt",
        "response",
        "secret",
        "token",
    }
)
_AUDIT_ONLY_KEYS = frozenset({"correlation_id", "duration_ms", "message_name", "message_type"})


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {
            str(key): _safe(item)
            for key, item in value.items()
            if str(key).lower() not in _DROP_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return redact_secrets(str(value))


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class RunProjectionHandler:
    """A passive subscriber whose failures are isolated by :class:`Bus`."""

    def __init__(self, bus: Bus, store: IRunProjectionStore) -> None:
        self._bus = bus
        self._store = store
        # Only the read/modify/write projection is serialized, never the
        # surrounding workflow or an independent dashboard read.
        self._record_lock = threading.Lock()

    def register(self) -> None:
        self._bus.subscribe("*", self.observe)

    def observe(self, event: Event) -> None:
        payload = event.payload or {}
        if not isinstance(payload, dict):
            return
        try:
            issue = int(payload.get("issue", 0) or 0)
        except (TypeError, ValueError):
            return
        if issue <= 0:
            return
        correlation_id = str(event.correlation_id or payload.get("correlation_id") or "")
        self.record(
            issue_number=issue,
            correlation_id=correlation_id,
            event_name=event.name,
            payload=payload,
            timestamp=event.ts,
        )

    def record(
        self,
        *,
        issue_number: int,
        correlation_id: str,
        event_name: str,
        payload: dict[str, Any],
        timestamp: datetime | str,
    ) -> None:
        observed_at = _parse_ts(timestamp)
        safe_payload = _safe(payload)
        if not isinstance(safe_payload, dict):  # pragma: no cover - payload contract above
            return
        for key in _AUDIT_ONLY_KEYS:
            safe_payload.pop(key, None)
        event_key = _digest(
            {
                "event_name": event_name,
                "correlation_id": correlation_id,
                "payload": safe_payload,
            }
        )
        safe_payload["message_name"] = event_name
        safe_payload["correlation_id"] = correlation_id
        envelope = {"ts": observed_at.isoformat(), "payload": safe_payload}
        projection_key = _digest(
            {
                "schema": "workflow-run.v1",
                "issue": issue_number,
                "correlation_id": correlation_id or event_key,
            }
        )
        with self._record_lock:
            self._record_projection(
                projection_key=projection_key,
                issue_number=issue_number,
                correlation_id=correlation_id,
                event_key=event_key,
                envelope=envelope,
                observed_at=observed_at,
            )

    def _record_projection(
        self,
        *,
        projection_key: str,
        issue_number: int,
        correlation_id: str,
        event_key: str,
        envelope: dict[str, Any],
        observed_at: datetime,
    ) -> None:
        current = self._store.get_projection(projection_key)
        events: list[dict[str, Any]] = []
        if current is not None:
            raw_events = current.payload.get("events")
            if isinstance(raw_events, list):
                events = [dict(item) for item in raw_events if isinstance(item, dict)]
        event_is_new = not any(item.get("event_key") == event_key for item in events)
        if event_is_new:
            events.append({**envelope, "event_key": event_key})
        events.sort(key=lambda item: (str(item.get("ts", "")), str(item.get("event_key", ""))))
        outcome = self._outcome(events)
        updated_at = (
            max(observed_at, current.updated_at)
            if event_is_new and current is not None
            else current.updated_at
            if current is not None
            else observed_at
        )
        projection_payload = {
            "schema": "workflow-run.v1",
            "outcome": self._outcome_payload(outcome),
            "events": events,
        }
        if (
            current is not None
            and current.status == outcome.projection_status
            and current.payload == projection_payload
            and current.updated_at == updated_at
        ):
            return
        self._store.upsert_projection(
            RunProjectionRecord(
                projection_key=projection_key,
                issue_number=issue_number,
                correlation_id=correlation_id,
                series="workflow-run.v1",
                status=outcome.projection_status,
                payload=projection_payload,
                updated_at=updated_at,
            )
        )

    @staticmethod
    def _outcome(events: list[dict[str, Any]]) -> WorkflowOutcome:
        facts: list[tuple[str, dict[str, Any]]] = []
        for envelope in events:
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                continue
            facts.append((str(payload.get("message_name") or ""), payload))
        return reduce_workflow_outcome(facts)

    @staticmethod
    def _outcome_payload(outcome: WorkflowOutcome) -> dict[str, Any]:
        return {
            "status": outcome.status,
            "terminal_event": outcome.terminal_event,
        }

    def reconcile_existing(self) -> dict[str, int]:
        """Reclassify stored runs from their redacted events, without audit input."""

        counts = {
            "scanned": 0,
            "updated": 0,
            "running": 0,
            "manual_pending": 0,
            "unbound": 0,
            "blocked": 0,
            "complete": 0,
        }
        for current in self._store.list_projections(series="workflow-run.v1"):
            counts["scanned"] += 1
            raw_events = current.payload.get("events")
            events = (
                [dict(item) for item in raw_events if isinstance(item, dict)]
                if isinstance(raw_events, list)
                else []
            )
            events.sort(key=lambda item: (str(item.get("ts", "")), str(item.get("event_key", ""))))
            outcome = self._outcome(events)
            status = outcome.projection_status
            counts[status] += 1
            payload = {
                "schema": "workflow-run.v1",
                "outcome": self._outcome_payload(outcome),
                "events": events,
            }
            if current.status == status and current.payload == payload:
                continue
            self._store.upsert_projection(
                RunProjectionRecord(
                    projection_key=current.projection_key,
                    issue_number=current.issue_number,
                    correlation_id=current.correlation_id,
                    series=current.series,
                    status=status,
                    payload=payload,
                    updated_at=current.updated_at,
                )
            )
            counts["updated"] += 1
        return counts

    def backfill_audit(self, data_dir: str | Path) -> dict[str, int]:
        """Best-effort initial projection; future correctness no longer uses audit."""

        reconciled = self.reconcile_existing()
        seen = 0
        projected = 0
        for path in sorted((Path(data_dir) / "logs").glob("agent*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                log.warning("Run projection backfill could not read %s: %s", path.name, exc)
                continue
            for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seen += 1
                payload = row.get("payload")
                if not isinstance(payload, dict):
                    continue
                try:
                    issue = int(payload.get("issue", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if issue <= 0:
                    continue
                self.record(
                    issue_number=issue,
                    correlation_id=str(payload.get("correlation_id") or ""),
                    event_name=str(payload.get("message_name") or row.get("name") or ""),
                    payload=payload,
                    timestamp=str(row.get("ts") or ""),
                )
                projected += 1
        return {
            "events_seen": seen,
            "events_projected": projected,
            "projections_scanned": reconciled["scanned"],
            "projections_reclassified": reconciled["updated"],
        }
