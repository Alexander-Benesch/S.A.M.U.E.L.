from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.events import (
    IssueClosed,
    IssueCommented,
    IssueOpened,
    PullRequestClosed,
    PullRequestMerged,
    PullRequestOpened,
)
from samuel.core.ports import IVersionControl

log = logging.getLogger(__name__)

_ACTIVITY_EVENTS = {
    event_cls().name: event_cls
    for event_cls in (
        IssueOpened,
        IssueClosed,
        IssueCommented,
        PullRequestOpened,
        PullRequestMerged,
        PullRequestClosed,
    )
}


class SCMActivityPoller:
    """Persistent, overlapping SCM activity poll with event-level dedup keys."""

    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl,
        state_path: Path,
        *,
        initial_days: int = 7,
        overlap_seconds: int = 60,
        interval_seconds: int = 60,
        limit: int = 250,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._state_path = state_path
        self._initial_days = max(1, int(initial_days))
        self._overlap_seconds = max(0, int(overlap_seconds))
        self._interval_seconds = max(1, int(interval_seconds))
        self._limit = max(1, min(int(limit), 500))
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def poll(self, correlation_id: str = "") -> dict[str, Any]:
        now = self._normalize(self._now_fn())
        state = self._load_state()
        raw_cursor = state.get("cursor")
        cursor = self._parse_timestamp(raw_cursor)
        if raw_cursor not in (None, "") and cursor is None:
            log.warning("SCM activity cursor is invalid; resetting initial sync window")
        if cursor is not None and cursor > now:
            log.warning("SCM activity cursor is in the future; resetting initial sync window")
            cursor = None
        if cursor is not None and (now - cursor).total_seconds() < self._interval_seconds:
            return {
                "activity_observed": 0,
                "activity_forwarded": 0,
                "activity_deduplicated": 0,
                "activity_poll": "interval_skip",
            }

        since = (
            cursor - timedelta(seconds=self._overlap_seconds)
            if cursor is not None
            else now - timedelta(days=self._initial_days)
        )
        rows = self._scm.list_scm_activity(self._format_timestamp(since), limit=self._limit)
        legacy_keys = self._legacy_activity_keys(since) if cursor is None else set()
        forwarded = 0
        deduplicated = 0
        for row in rows:
            event_cls = _ACTIVITY_EVENTS.get(row.event)
            if event_cls is None:
                log.warning("SCM adapter returned unknown activity event: %s", row.event)
                continue
            activity_id = row.activity_id
            if activity_id in legacy_keys or f"{row.event}:{row.number}" in legacy_keys:
                deduplicated += 1
                continue
            self._bus.publish(
                event_cls(
                    payload={
                        "number": row.number,
                        "title": row.title,
                        "url": row.url,
                        "actor": row.actor,
                        "actor_type": row.actor_type,
                        "source": "polling",
                        "timestamp": row.timestamp,
                        "activity_id": activity_id,
                        "idempotency_key": f"scm_activity:{activity_id}",
                    },
                    correlation_id=correlation_id,
                )
            )
            forwarded += 1

        saved = self._save_state({"cursor": self._format_timestamp(now)})
        return {
            "activity_observed": len(rows),
            "activity_forwarded": forwarded,
            "activity_deduplicated": deduplicated,
            "activity_poll": "ok",
            "activity_cursor_saved": saved,
            "activity_since": self._format_timestamp(since),
        }

    def _legacy_activity_keys(self, since: datetime) -> set[str]:
        """Best-effort migration dedup for audit rows written before #390.

        New webhook events are deduplicated persistently by the bus key.  On
        the first poll after an upgrade, older rows have no ``activity_id``;
        their event+number pair prevents the bounded initial backfill from
        visibly replaying the same observation.
        """

        keys: set[str] = set()
        log_dir = self._state_path.parent / "logs"
        invalid_rows = 0
        for path in sorted(log_dir.glob("agent*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                log.warning("Could not read activity audit history %s: %s", path, exc)
                continue
            for line in lines:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    invalid_rows += 1
                    continue
                if not isinstance(event, dict):
                    continue
                event_time = self._parse_timestamp(event.get("ts"))
                if event_time is None or event_time < since:
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                event_name = str(payload.get("message_name") or "")
                if event_name not in _ACTIVITY_EVENTS:
                    continue
                activity_id = payload.get("activity_id")
                if isinstance(activity_id, str) and activity_id:
                    keys.add(activity_id)
                number = payload.get("number")
                if number not in (None, ""):
                    keys.add(f"{event_name}:{number}")
        if invalid_rows:
            log.warning(
                "Ignored %d invalid audit row(s) while seeding SCM activity deduplication",
                invalid_rows,
            )
        return keys

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {}
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read SCM activity cursor %s: %s", self._state_path, exc)
            return {}
        return value if isinstance(value, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> bool:
        temporary = self._state_path.with_suffix(".tmp")
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self._state_path)
            return True
        except OSError as exc:
            log.warning("Could not persist SCM activity cursor %s: %s", self._state_path, exc)
            return False

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return SCMActivityPoller._normalize(
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            )
        except ValueError:
            return None

    @staticmethod
    def _normalize(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _format_timestamp(value: datetime) -> str:
        return SCMActivityPoller._normalize(value).isoformat().replace("+00:00", "Z")
