"""#336: Workflow-Replay aus dem Audit-Log.

Rekonstruiert die Event-Chain eines Issues/Runs aus ``data/logs/agent*.jsonl``
und kann sie **side-effect-frei** erneut publishen (an einen Bus ohne
Handler) — fuer das Debugging fehlgeschlagener Self-Mode-Runs, ohne reale
Aktionen (Commits/PRs) auszuloesen.

Self-contained (kein Slice-Import) — liest die Logs direkt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from samuel.core.workflow_outcome import reduce_workflow_outcome


def _event_name(record: dict) -> str:
    payload = record.get("payload", {}) or {}
    return str(payload.get("message_name") or payload.get("evt") or record.get("name") or "")


def _issue_of(record: dict) -> Any:
    payload = record.get("payload", {}) or {}
    return payload.get("issue", record.get("issue"))


def load_run_events(
    data_dir: str = "data",
    issue: int | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """Audit-Events eines Issues (chronologisch). ``run_id`` filtert zusaetzlich
    nach ``correlation_id`` (ein konkreter Run)."""
    log_dir = Path(data_dir) / "logs"
    if not log_dir.exists():
        return []
    rows: list[dict] = []
    for path in sorted(log_dir.glob("agent*.jsonl")):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if issue is not None and _issue_of(rec) != issue:
                    continue
                if run_id is not None and rec.get("correlation_id") != run_id:
                    continue
                rows.append(rec)
        except OSError:
            continue
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def build_snapshot(events: list[dict], issue: int | None = None) -> dict[str, Any]:
    """#336: Workflow-State-Snapshot aus der Event-Chain.

    Schema: ``{issue, event_count, first_ts, last_ts, status, terminal_event,
    stages (Event-Name -> count), timeline [{ts, event, correlation_id,
    message}]}``.
    """
    timeline: list[dict] = []
    stages: dict[str, int] = {}
    for rec in events:
        name = _event_name(rec)
        stages[name] = stages.get(name, 0) + 1
        payload = rec.get("payload", {}) or {}
        timeline.append(
            {
                "ts": rec.get("ts", ""),
                "event": name,
                "correlation_id": rec.get("correlation_id", ""),
                "message": payload.get("reason", "") or payload.get("message", ""),
            }
        )
    outcome = reduce_workflow_outcome(
        (_event_name(record), record.get("payload", {}) or {}) for record in events
    )
    status = {
        "pr_created": "completed",
        "merged": "completed",
        "blocked": "failed",
        "aborted": "failed",
        "unbound": "unbound",
        "running": "in_progress" if events else "unknown",
    }[outcome.status]
    return {
        "issue": issue,
        "event_count": len(events),
        "first_ts": events[0].get("ts", "") if events else "",
        "last_ts": events[-1].get("ts", "") if events else "",
        "status": status,
        "terminal_event": outcome.terminal_event or "",
        "stages": stages,
        "timeline": timeline,
    }


def replay_to_bus(events: list[dict], bus: Any) -> int:
    """#336: Re-publisht jedes Event als generisches ``Event`` an ``bus``.

    Side-effect-frei, sofern ``bus`` keine realen Handler/Command-Handler
    registriert hat (Replay-Mode = frischer Bus). Gibt die Anzahl
    re-publishter Events zurueck.
    """
    from samuel.core.events import Event

    count = 0
    for rec in events:
        name = _event_name(rec)
        if not name:
            continue
        bus.publish(
            Event(
                name=name,
                payload=dict(rec.get("payload", {}) or {}),
                correlation_id=rec.get("correlation_id", "") or "",
            )
        )
        count += 1
    return count
