"""Dashboard data aggregation layer."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from samuel.core.ai_act import classify as _classify_ai_act
from samuel.core.errors import describe_diagnostic
from samuel.core.gate_metadata import GATE_NAMES
from samuel.core.owasp import classify as _classify_owasp
from samuel.core.ports import IConfig, IObservationStore, IRunProjectionStore
from samuel.core.workflow_outcome import reduce_workflow_outcome

# #211: API-key validation cache — 5min TTL, in-memory, single-process.
_VALIDATION_CACHE: dict[str, tuple[float, dict]] = {}
_VALIDATION_TTL_SECONDS = 300


def _cached_validate(provider_name: str, adapter: Any) -> dict[str, Any]:
    """Run adapter.validate() with TTL cache. Catches exceptions gracefully."""
    import time as _time

    now = _time.monotonic()
    cached = _VALIDATION_CACHE.get(provider_name)
    if cached is not None and (now - cached[0]) < _VALIDATION_TTL_SECONDS:
        return cached[1]
    if not hasattr(adapter, "validate"):
        result = {"valid": False, "detail": "validate() not implemented", "balance": None}
    else:
        try:
            raw_result = adapter.validate()
            result = (
                raw_result
                if isinstance(raw_result, dict)
                else {
                    "valid": False,
                    "detail": "validate() returned invalid data",
                    "balance": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Provider validation failed for %s: %s", provider_name, exc)
            result = {
                "valid": False,
                "detail": f"validate() raised: {type(exc).__name__}",
                "balance": None,
            }
    _VALIDATION_CACHE[provider_name] = (now, result)
    return result


log = logging.getLogger(__name__)


def _parse_audit_ts(ts: str) -> datetime | None:
    """Parse the various ts formats produced by JSONLAuditSink (ISO 8601
    with optional sub-second precision and timezone). Returns ``None`` if
    unparseable."""
    if not ts:
        return None
    try:
        # JSONLAuditSink writes ``2026-04-29 14:53:00.570111+00:00`` (space)
        # — datetime.fromisoformat handles that since 3.11.
        return datetime.fromisoformat(ts.replace(" ", "T"))
    except (ValueError, TypeError):
        return None


def load_audit_events(data_dir: str = "data", limit: int = 200) -> list[dict]:
    """Load recent events from audit logs.

    Reads both the unrotated agent.jsonl and rotated agent_<DATE>.jsonl files
    via glob (matches the JSONLAuditSink rotation behaviour). Returns the
    chronologically latest `limit` events across all files.
    """
    log_dir = Path(data_dir) / "logs"
    if not log_dir.exists():
        return []
    paths = sorted(log_dir.glob("agent*.jsonl"))
    if not paths:
        return []
    all_events: list[dict] = []
    for path in paths:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    all_events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            log.warning("Failed to read audit log: %s", path)
    return all_events[-limit:]


def load_runtime_events(
    data_dir: str = "data",
    limit: int = 200,
    projection_store: IRunProjectionStore | None = None,
) -> list[dict]:
    """Read run events from SQLite, with audit as pre-migration fallback only."""

    if projection_store is None:
        return load_audit_events(data_dir, limit)
    rows = [
        *projection_store.list_projections(series="workflow-run.v1"),
        *projection_store.list_projections(series="workflow.legacy.v1"),
    ]
    events: list[dict] = []
    for row in rows:
        if row.series == "workflow-run.v1" and row.status == "unbound":
            continue
        raw_events = row.payload.get("events")
        if not isinstance(raw_events, list):
            continue
        for event in raw_events:
            if isinstance(event, dict) and isinstance(event.get("payload"), dict):
                events.append({"ts": str(event.get("ts", "")), "payload": event["payload"]})
    if not events:
        return load_audit_events(data_dir, limit)
    events.sort(key=lambda item: str(item.get("ts", "")))
    return events


def get_log_entries(data_dir: str = "data", limit: int = 200) -> list[dict]:
    """Get formatted log entries for the log viewer.

    Each entry exposes the full audit payload as ``meta`` so the UI can
    render a per-row Detail-Toggle (provider, model, tokens, raw payload).
    Entries with ``event == "self_check_fatal"`` carry a ``resolved_at``
    timestamp when a later ``self_check_resolved`` event references them
    via ``payload.prev_timestamp`` (or ``payload.meta.prev_timestamp`` for
    bridge-emitted events).
    """
    events = load_audit_events(data_dir, limit)
    resolved_at_for: dict[str, str] = {}
    for evt in events:
        payload = evt.get("payload", {}) or {}
        if _event_key(payload) != "self_check_resolved":
            continue
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        prev_ts = (meta or {}).get("prev_timestamp") or payload.get("prev_timestamp", "")
        if prev_ts:
            resolved_at_for[_ts_key(prev_ts)] = _ts_human(evt.get("ts", ""))

    entries = []
    for evt in events:
        payload = evt.get("payload", {}) or {}
        ts = evt.get("ts", "")
        cat = _classify_category(evt)
        evt_key = str(payload.get("evt") or payload.get("event_name") or "")
        entry = {
            "timestamp": ts,
            "level": _classify_level(evt),
            "category": cat,
            "event": payload.get("message_name", evt.get("name", "")),
            "message": _build_message(evt),
            "issue": payload.get("issue", ""),
            "correlation_id": payload.get("correlation_id", ""),
            "owasp": payload.get("owasp_risk") or _classify_owasp(cat, evt_key) or "",
            "meta": dict(payload),
        }
        if _event_key(payload) == "self_check_fatal":
            resolved = resolved_at_for.get(_ts_key(ts))
            if resolved:
                entry["resolved_at"] = resolved
        entries.append(entry)
    return list(reversed(entries))


def get_log_level_counts(data_dir: str = "data", limit: int = 200) -> dict[str, int]:
    """Return ``{"info": N, "warn": N, "error": N}`` over the last ``limit``
    audit events. Powers the Logs-tab Stat-Tiles."""
    events = load_audit_events(data_dir, limit)
    counts = {"info": 0, "warn": 0, "error": 0}
    for evt in events:
        lvl = _classify_level(evt)
        if lvl in counts:
            counts[lvl] += 1
    return counts


def get_problems(data_dir: str = "data", limit: int = 200) -> list[dict[str, Any]]:
    """Return the central warning/error/blockade view for the dashboard.

    Includes both domain events (WorkflowBlocked, GateFailed, TokenLimitHit,
    etc.) and ``DiagnosticRaised`` records mirrored from caught runtime
    warnings/errors.  Only bounded, scrubbed diagnostic fields are returned;
    raw payloads remain in the authenticated audit log view.
    """

    events = load_audit_events(data_dir, max(limit * 10, 1000))
    contaminated = _legacy_test_diagnostic_indexes(events)
    resolved_at: dict[str, datetime | None] = {}
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict) or _event_key(payload) != "DiagnosticResolved":
            continue
        fingerprint = str(payload.get("fingerprint", ""))
        if fingerprint:
            resolved_at[fingerprint] = _parse_audit_ts(str(evt.get("ts", "")))

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    for index, evt in enumerate(events):
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        level = _classify_level(evt)
        if level not in {"warn", "error"}:
            continue
        event_name = str(payload.get("message_name") or payload.get("evt") or "")
        files = _diagnostic_files(payload)
        category = _classify_category(evt)
        reason = _diagnostic_reason(payload, event_name)
        logger_name = str(payload.get("logger", ""))
        description = describe_diagnostic(
            logger=logger_name,
            reason=reason,
            category=category,
            event_name=event_name,
        )
        fingerprint = str(payload.get("fingerprint") or "") or _diagnostic_fingerprint(
            category, logger_name, reason, files[0] if files else ""
        )
        timestamp = str(evt.get("ts", ""))
        parsed_ts = _parse_audit_ts(timestamp)
        provenance = str(payload.get("provenance") or "runtime")
        status = "active"
        if index in contaminated:
            provenance = "legacy_test_contamination"
            status = "invalid_test_data"
        elif fingerprint in resolved_at:
            resolution_ts = resolved_at[fingerprint]
            if resolution_ts is None or parsed_ts is None or parsed_ts <= resolution_ts:
                status = "resolved"
        if status == "active" and parsed_ts is not None:
            comparable = parsed_ts if parsed_ts.tzinfo else parsed_ts.replace(tzinfo=timezone.utc)
            if now - comparable > timedelta(days=7):
                status = "stale"

        instance = {
            "timestamp": timestamp,
            "reason": reason,
            "issue": payload.get("issue") or "",
            "correlation_id": str(payload.get("correlation_id", "")),
            "line": payload.get("line"),
        }
        key = (fingerprint, status)
        existing = grouped.get(key)
        if existing is None:
            structured = {
                name: payload.get(name, description[name])
                for name in ("problem_type", "title", "cause", "impact", "next_steps")
            }
            grouped[key] = {
                "timestamp": timestamp,
                "first_seen": timestamp,
                "last_seen": timestamp,
                "count": 1,
                "status": status,
                "provenance": provenance,
                "fingerprint": fingerprint,
                "level": level,
                "category": category,
                "issue": payload.get("issue") or "",
                "issues": [payload.get("issue")] if payload.get("issue") is not None else [],
                "reason": reason,
                "file": files[0] if files else "",
                "files": files,
                "event": event_name,
                "logger": logger_name,
                "line": payload.get("line"),
                "exception": str(payload.get("exception") or payload.get("error_class") or ""),
                "correlation_id": str(payload.get("correlation_id", "")),
                "instances": [instance],
                **structured,
            }
            continue
        existing["last_seen"] = timestamp
        existing["timestamp"] = timestamp
        existing["count"] += 1
        existing["instances"].append(instance)
        existing["instances"] = existing["instances"][-20:]
        issue = payload.get("issue")
        if issue is not None and issue not in existing["issues"]:
            existing["issues"].append(issue)
        existing["issue"] = existing["issues"][0] if len(existing["issues"]) == 1 else ""

    problems = list(grouped.values())
    problems.sort(key=lambda problem: str(problem["last_seen"]), reverse=True)
    return problems[:limit]


def _diagnostic_fingerprint(category: str, logger_name: str, reason: str, file: str) -> str:
    raw = "\0".join((category, logger_name, reason, file)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


_LEGACY_TEST_ANCHORS = (
    "create_branch: cannot switch to main before recreating feat/x: dirty worktree",
    "create_branch: post-condition failed — on 'some-other-branch' instead of 'feat/x'",
)


def _contains_legacy_test_marker(reason: str) -> bool:
    return (
        reason in _LEGACY_TEST_ANCHORS
        or "/tmp/pytest-of-root/" in reason
        or "simulated " in reason.lower()
        or re.search(r"/tmp/tmp[a-zA-Z0-9_]+(?:/|$)", reason) is not None
    )


def _legacy_test_diagnostic_indexes(events: list[dict[str, Any]]) -> set[int]:
    """Identify the old, proven test batches without rewriting audit history."""

    anchors: list[datetime] = []
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict) or not payload.get("logger"):
            continue
        if not _contains_legacy_test_marker(str(payload.get("reason", ""))):
            continue
        parsed = _parse_audit_ts(str(evt.get("ts", "")))
        if parsed is not None:
            anchors.append(parsed)

    contaminated: set[int] = set()
    for index, evt in enumerate(events):
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict) or not payload.get("logger"):
            continue
        parsed = _parse_audit_ts(str(evt.get("ts", "")))
        if parsed is not None and any(
            abs((parsed - anchor).total_seconds()) <= 2 for anchor in anchors
        ):
            contaminated.add(index)
    return contaminated


def _event_key(payload: dict) -> str:
    """Logical event name across both audit emission styles.

    AuditHandler-written records put the event class name in
    ``payload.message_name``; bridge.audit() records use ``payload.evt``.
    """
    return str(payload.get("message_name") or payload.get("evt") or "")


def _ts_key(ts: str) -> str:
    """Truncate to ``YYYY-MM-DD HH:MM:SS`` for fuzzy fatal↔resolved matching."""
    return (ts or "")[:19].replace("T", " ")


def _ts_human(ts: str) -> str:
    return _ts_key(ts)


def _gate_label(gate_id: Any, fallback: str = "") -> str:
    """Return ``GATE_NAMES[gate_id]`` if present, else stringified id (or
    fallback when id is empty)."""
    if gate_id in GATE_NAMES:
        return GATE_NAMES[gate_id]
    if gate_id is None or gate_id == "":
        return fallback
    return str(gate_id)


_BARRIER_MSG_NAMES: set[str] = {"GateFailed", "SecurityTripwireTriggered", "WorkflowAborted"}


# Maps OWASP risk-NAME (as returned by classify(cat, evt)) to OWASP-Top-10 ID
# used in the Security tab. payload.owasp_risk values like "A05:2021" already
# have the A-prefix; classify-derived names need this lookup.
# #290: Source-of-Truth ist OWASP_TOP10 (jetzt ASI01..ASI10). Legacy-Keys
# (A01..A10-Era: ``unrestricted_agency``, ``broken_trust_boundaries`` usw.)
# werden zusaetzlich auf ihre ASI-IDs aufgeloest, damit historische
# Audit-Log-Eintraege im Dashboard weiter klassifiziert angezeigt werden.
def _build_owasp_name_to_id() -> dict[str, str]:
    from samuel.core.owasp import OWASP_LEGACY_KEY_MAP, OWASP_TOP10

    current = {cat["key"]: cat["id"] for cat in OWASP_TOP10}
    legacy = {
        old_key: current[new_key]
        for old_key, new_key in OWASP_LEGACY_KEY_MAP.items()
        if new_key in current
    }
    return {**current, **legacy}


_OWASP_NAME_TO_ID: dict[str, str] = _build_owasp_name_to_id()


def get_security_overview(data_dir: str = "data") -> dict[str, Any]:
    """OWASP Agentic AI risk overview from audit events.

    The returned ``owasp`` list contains, per risk id, a ``recent`` array of
    up to 5 events ``{timestamp, event, message, issue}`` so the UI can show
    what specifically triggered each risk classification.

    #290: IDs sind seit der Migration ASI01..ASI10. Historische Audit-
    Eintraege mit alten A01..A10-IDs werden ueber ``OWASP_LEGACY_ID_MAP``
    auf ihre ASI-Aequivalente aufgeloest, damit sie weiter klassifiziert
    erscheinen.
    """
    from samuel.core.owasp import OWASP_LEGACY_ID_MAP, OWASP_TOP10

    events = load_audit_events(data_dir, 500)

    # owasp_risks dynamisch aus der aktuellen Taxonomie (ASI01..ASI10) bauen.
    owasp_risks: dict[str, dict[str, Any]] = {
        cat["id"]: {
            "name": cat["name"],
            "events": 0,
            "last": "",
            "recent": [],
        }
        for cat in OWASP_TOP10
    }

    barriers = []
    classified = 0
    for evt in events:
        payload = evt.get("payload", {})
        owasp = payload.get("owasp_risk", "")
        if not owasp:
            cat = _classify_category(evt)
            evt_key = str(payload.get("evt") or payload.get("event_name") or "")
            owasp = _classify_owasp(cat, evt_key) or ""
        if owasp:
            classified += 1
            risk_key = owasp.split(":")[0] if ":" in owasp else _OWASP_NAME_TO_ID.get(owasp, owasp)
            # #290: legacy A0X-IDs auf ASI0X aufloesen
            risk_key = OWASP_LEGACY_ID_MAP.get(risk_key, risk_key)
            if risk_key in owasp_risks:
                owasp_risks[risk_key]["events"] += 1
                owasp_risks[risk_key]["last"] = evt.get("ts", "")
                owasp_risks[risk_key]["recent"].append(
                    {
                        "timestamp": evt.get("ts", ""),
                        "event": payload.get("message_name", ""),
                        "message": _build_message(evt),
                        "issue": payload.get("issue", ""),
                    }
                )

        msg_name = payload.get("message_name", "")
        if msg_name in _BARRIER_MSG_NAMES:
            gate_id = payload.get("gate")
            barriers.append(
                {
                    "timestamp": evt.get("ts", ""),
                    "issue": payload.get("issue", ""),
                    "event": _gate_label(gate_id, fallback=msg_name),
                    "step": str(payload.get("step", "")),
                    "action": "blocked" if msg_name == "GateFailed" else "warn",
                    "owasp": owasp,
                    "detail": payload.get("reason", ""),
                }
            )

    # Cap recent per risk to the latest 5 (events are appended in chronological order)
    for r in owasp_risks.values():
        r["recent"] = r["recent"][-5:]

    total = len(events)
    active_risks = sum(1 for r in owasp_risks.values() if r["events"] > 0)
    owasp_array = [
        {
            "id": rid,
            "category": r["name"],
            "count": r["events"],
            "last": r["last"],
            "recent": r["recent"],
        }
        for rid, r in owasp_risks.items()
    ]

    return {
        "total_events": total,
        "classified_pct": round(classified / total * 100) if total else 0,
        "active_risks": active_risks,
        "owasp": owasp_array,
        "barriers": barriers[-30:],
    }


def get_compliance_legend(
    risk_class: str | None = None,
    risk_class_source: str | None = None,
) -> dict[str, Any]:
    """Compliance-Legend für Audit-Tab/Compliance-Tab (#252).

    Liefert OWASP Top-10 Agentic AI + EU AI Act Artikel mit Beschreibungen.
    Operator kann damit Codes wie ``A05`` oder ``Art. 14`` im Audit-Trail
    direkt nachschlagen statt extern recherchieren zu müssen.

    Args:
        risk_class: explizite Deployment-Risikoklasse (vom Handler mit dem
            persistierten ``config/compliance.json``-Wert aufgelöst). ``None``
            → env/Default über :func:`resolve_risk_class`.
        risk_class_source: ``"env"|"config"|"default"`` — wird durchgereicht,
            damit das Dashboard den Selektor sperren kann, wenn die Klasse per
            env fixiert ist.

    Returns:
        ``{"owasp": [{id, name, key, description}, ...],
           "ai_act": [{article, description, obligation}, ...],
           "ai_act_risk_class": "limited_risk",
           "ai_act_risk_class_source": "default"}``

    #373: ``obligation`` pro Artikel wird aus der Deployment-Risikoklasse
    abgeleitet (Self-Mode default ``limited_risk``). ``ai_act_risk_class``
    macht im Dashboard sichtbar, gegen welche Klasse die Pflicht/freiwillig-
    Badges gerechnet sind — sonst wirkt ein ``freiwillig`` an einem
    Hochrisiko-Deployment irreführend.
    """
    from samuel.core.ai_act import ai_act_articles, resolve_risk_class
    from samuel.core.owasp import OWASP_TOP10

    if risk_class is None:
        risk_class, risk_class_source = resolve_risk_class()

    from samuel.core.compliance_mapping import COMPLIANCE_DIR, load_mapping

    frameworks = []
    for filename, controls_key, reference_key, control_key in (
        ("owasp.json", "categories", "risk", "key"),
        ("ai_act.json", "articles", "article", "id"),
        ("gdpr.json", "controls", "control", "id"),
        ("cra.json", "controls", "control", "id"),
    ):
        try:
            definition = load_mapping(
                COMPLIANCE_DIR / filename,
                controls_key=controls_key,
                reference_key=reference_key,
                control_key=control_key,
            )
            frameworks.append(definition.legend())
        except RuntimeError:
            # A bad optional mapping affects its legend, not other frameworks.
            frameworks.append({"definition": filename, "effect": "advisory", "status": "invalid"})

    return {
        "frameworks": frameworks,
        "owasp": [dict(entry) for entry in OWASP_TOP10],
        "ai_act": ai_act_articles(risk_class),
        "ai_act_risk_class": risk_class,
        "ai_act_risk_class_source": risk_class_source or "default",
    }


def get_dlq_entries(data_dir: str = "data", limit: int = 50) -> list[dict]:
    """#334: Dead-Letter-Queue-Eintraege fuer das Dashboard (newest first).

    Liest ``<data_dir>/dlq.jsonl`` (geschrieben von ``DeadLetterQueue``). Read-
    only — Re-Publish laeuft ueber die CLI ``samuel dlq replay <id>``.
    """
    fp = Path(data_dir) / "dlq.jsonl"
    if not fp.exists():
        return []
    rows: list[dict] = []
    try:
        for line in fp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    rows.reverse()
    return rows[:limit]


_PLAN_DISPLAY_EVENTS: dict[str, int] = {
    "ClarificationRequested": 1,
    "ClarificationWaiting": 1,
    "ClarificationAccepted": 1,
    "ClarificationSuperseded": 1,
    "PlanCreated": 1,
    "PlanPosted": 2,
    "PlanValidated": 3,
}


def _workflow_event_order(
    event: tuple[str, str, dict[str, Any]],
    source_index: int,
) -> tuple[int, float, str, int]:
    """Order workflow facts by their event time, not audit delivery order."""

    timestamp = str(event[0] or "")
    parsed = _parse_audit_ts(timestamp)
    return (
        1 if parsed is not None else 0,
        parsed.timestamp() if parsed is not None else 0.0,
        timestamp,
        source_index,
    )


def _latest_workflow_run_facts(
    events: list[tuple[str, str, dict[str, Any]]],
) -> list[tuple[str, str, dict[str, Any]]]:
    """Select the newest correlated run while retaining legacy unbound facts."""

    if not events:
        return []
    grouped: dict[str, list[tuple[int, tuple[str, str, dict[str, Any]]]]] = {}
    for index, event in enumerate(events):
        correlation_id = str(event[2].get("correlation_id") or "")
        grouped.setdefault(correlation_id, []).append((index, event))

    latest_group = max(
        grouped.values(),
        key=lambda group: max(_workflow_event_order(event, index) for index, event in group),
    )
    return [
        event
        for index, event in sorted(
            latest_group,
            key=lambda item: _workflow_event_order(item[1], item[0]),
        )
    ]


def _derive_workflow_issue_state(
    events: list[tuple[str, str, dict[str, Any]]],
) -> tuple[str, str, str]:
    """Return status, causal event and its timestamp for the newest run.

    Nested synchronous dispatch can persist the seed ``IssueReady`` event
    after the planning events it triggered.  The dashboard therefore reduces
    facts semantically inside one correlation rather than treating JSONL
    delivery order as workflow causality.
    """

    facts = _latest_workflow_run_facts(events)
    if not facts:
        return "unknown", "", ""

    outcome = reduce_workflow_outcome((name, payload) for _, name, payload in facts)
    if outcome.terminal_event:
        timestamp = next(
            (ts for ts, name, _ in reversed(facts) if name == outcome.terminal_event),
            "",
        )
        status = (
            outcome.status
            if outcome.status in {"pr_created", "reviewed", "merged", "evaluated"}
            else "blocked"
        )
        return status, outcome.terminal_event, timestamp

    if outcome.status == "manual_pending":
        timestamp = next(
            (
                ts
                for ts, name, payload in reversed(facts)
                if name == "GateEvaluationCompleted" and payload.get("manual_pending") is True
            ),
            "",
        )
        return "manual_pending", "GateEvaluationCompleted", timestamp

    implemented = [(ts, name) for ts, name, _ in facts if name == "CodeGenerated"]
    if implemented:
        timestamp, name = implemented[-1]
        return "implemented", name, timestamp

    planned = [(ts, name) for ts, name, _ in facts if name in _PLAN_DISPLAY_EVENTS]
    if planned:
        timestamp, name = max(planned, key=lambda item: _PLAN_DISPLAY_EVENTS[item[1]])
        return "planned", name, timestamp

    ready = [(ts, name) for ts, name, _ in facts if name == "IssueReady"]
    if ready:
        timestamp, name = ready[-1]
        return "ready", name, timestamp

    timestamp, name, _ = facts[-1]
    active = [
        (ts, event_name)
        for ts, event_name, payload in facts
        if event_name == "LLMBudgetAttemptReserved"
        and payload.get("correlation_id")
        and all(payload.get(key) for key in ("attempt_key", "task", "provider", "model"))
    ]
    if active:
        timestamp, name = active[-1]
        return "running", name, timestamp
    return "unknown", name, timestamp


def get_workflow_issues(
    data_dir: str = "data",
    projection_store: IRunProjectionStore | None = None,
) -> list[dict]:
    """Get issue processing status from audit events.

    Per issue the row carries (#277):
    - ``runs_count``: number of distinct ``correlation_id`` runs seen
    - ``trend``: one of ``recovered``/``regressed``/``passed``/``failed``/``""``
    """
    events = load_runtime_events(data_dir, 100_000, projection_store)
    issues: dict[int, dict] = {}
    # corr-ids per issue, used to compute runs_count without re-loading the
    # audit log via get_workflow_runs.
    corr_ids_by_issue: dict[int, set[str]] = {}

    for evt in events:
        payload = evt.get("payload", {})
        issue_num = payload.get("issue")
        if not issue_num:
            continue
        issue_num = int(issue_num)

        if issue_num not in issues:
            issues[issue_num] = {
                "number": issue_num,
                "events": [],
                "status": "unknown",
                "last_event": "",
                "timestamp": "",
                "runs_count": 0,
                "trend": "",
                "_facts": [],
            }
            corr_ids_by_issue[issue_num] = set()

        msg_name = payload.get("message_name", "")
        issues[issue_num]["events"].append(
            {
                "name": msg_name,
                "ts": evt.get("ts", ""),
                "detail": payload.get("reason", ""),
            }
        )
        issues[issue_num]["_facts"].append((evt.get("ts", ""), msg_name, payload))

        corr = str(payload.get("correlation_id") or "")
        if corr and not (
            msg_name == "LLMCallCompleted" and payload.get("workflow_correlation_bound") is not True
        ):
            corr_ids_by_issue[issue_num].add(corr)

    for num, corr_ids in corr_ids_by_issue.items():
        status, last_event, timestamp = _derive_workflow_issue_state(issues[num].pop("_facts"))
        issues[num]["status"] = status
        issues[num]["last_event"] = last_event
        issues[num]["timestamp"] = timestamp
        issues[num]["runs_count"] = len(corr_ids)
        if len(corr_ids) >= 2:
            # Re-derive trend from the runs aggregator so failed -> passed
            # transitions land in the issue list, not just in the detail
            # view (#277).
            runs = get_workflow_runs(num, data_dir, projection_store=projection_store)
            issues[num]["trend"] = _classify_workflow_trend(runs)

    return sorted(issues.values(), key=lambda x: x.get("timestamp", ""), reverse=True)[:30]


_PIPELINE_STAGE_EVENTS: dict[str, set[str]] = {
    # #258: jede Stage hat sowohl Pass- als auch Fail-Events. Vorher zeigten
    # gates/quality "pending" für erfolgreiche Runs weil nur Failure-Events
    # gemappt waren.
    # #238: PlanPreCheckCompleted/PlanComplexityWarn ebenfalls Plan-Stage.
    "plan": {
        "ClarificationRequested",
        "ClarificationWaiting",
        "ClarificationAccepted",
        "ClarificationSuperseded",
        "PlanCreated",
        "PlanValidated",
        "PlanBlocked",
        "PlanReplanRejected",
        "PlanRevoked",
        "PlanPreCheckCompleted",
        "PlanComplexityWarn",
    },
    "implement": {"CodeGenerated", "Implement", "ImplementationFailed", "PRCreated"},
    "llm": {
        "LLMCallCompleted",
        "LLMUnavailable",
        "TokenLimitHit",
        "WorkflowBudgetAdmitted",
        "LLMBudgetAttemptReserved",
        "LLMBudgetAttemptSettled",
        "LLMBudgetBlocked",
    },
    "gates": {
        "GateEvaluationCompleted",
        "GatesPassed",
        "GateFailed",
        "SecurityTripwireTriggered",
        "CandidateVerificationPending",
        "CandidateEvaluationCompleted",
        "CandidateEvaluationFailed",
        "CandidateSubmissionRejected",
        "ProviderVerificationRequested",
        "ProviderVerificationPending",
        "ProviderVerificationBlocked",
        "ProviderGateEvaluationCompleted",
    },
    "eval": {"ScoreObserved", "Evaluate", "EvalCompleted", "EvalFailed"},
    "quality": {"QualityPassed", "QualityFailed"},
    # #239: Healing-Stage zwischen quality und pr
    "healing": {
        "HealingAttemptStarted",
        "HealingAttemptCompleted",
        "HealingSuggested",
        "HealingAborted",
    },
    # A command dispatch is no outcome evidence: only SCM-confirmed or explicit
    # terminal events may complete/fail the PR stage (#578).
    "pr": {"PRCreated", "PRCreationFailed", "EvaluationSubjectInvalidated"},
    "review": {"ReviewCompleted", "ReviewBlocked", "MergeOutcomeUnknown", "PRCreated"},
}

_STAGE_FAIL_EVENTS: set[str] = {
    "PlanBlocked",
    "PlanReplanRejected",
    "ImplementationFailed",
    "LLMUnavailable",
    "TokenLimitHit",
    "LLMBudgetBlocked",
    "GateFailed",
    "SecurityTripwireTriggered",
    "EvalFailed",
    "QualityFailed",
    "ReviewBlocked",
    "MergeOutcomeUnknown",
    "PRCreationFailed",
    "EvaluationSubjectInvalidated",
    "CandidateEvaluationFailed",
    "CandidateSubmissionRejected",
    "ProviderVerificationBlocked",
    "WorkflowAborted",
    "WorkflowBlocked",
    # #239: HealingAborted markiert healing-stage als failed
    "HealingAborted",
}


def _is_bound_score_observation(payload: dict[str, Any]) -> bool:
    """Accept only provenance- and version-labelled passive observations."""

    return (
        payload.get("non_binding") is True
        and payload.get("evidence_origin") == "bound_acceptance_evidence"
        and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", str(payload.get("observation_key", ""))))
        and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", str(payload.get("score_key", ""))))
        and bool(
            re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(payload.get("scoring_policy_digest", "")),
            )
        )
        and bool(payload.get("scoring_policy_version"))
        and bool(payload.get("formula_version"))
        and payload.get("label") == "Nicht bindende Qualitätsbeobachtung"
    )


def _bound_observation_schema(payload: dict[str, Any]) -> str:
    """Name the pre-#627 bound event shape instead of merging it with legacy eval."""

    return str(payload.get("observation_schema") or "bound.v1")


def _selected_quality_series(events: list[dict]) -> tuple[str, str, str, str]:
    """Select one exact score series; never aggregate formulas or origins.

    Audit events are chronological.  The newest valid bound observation
    therefore defines the active dashboard series.  Deployments without any
    bound observation retain the readable legacy series during rollout.
    """

    selected = ("unbound_worktree", "legacy.v1", "legacy", "legacy")
    for evt in events:
        payload = evt.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("message_name") != "ScoreObserved":
            continue
        if not _is_bound_score_observation(payload):
            continue
        selected = (
            "bound_acceptance_evidence",
            _bound_observation_schema(payload),
            str(payload["scoring_policy_version"]),
            str(payload["formula_version"]),
        )
    return selected


def _quality_series_for_payload(payload: dict[str, Any]) -> tuple[str, str, str, str] | None:
    message_name = payload.get("message_name")
    if message_name in ("EvalCompleted", "EvalFailed"):
        return ("unbound_worktree", "legacy.v1", "legacy", "legacy")
    if message_name == "ScoreObserved" and _is_bound_score_observation(payload):
        return (
            "bound_acceptance_evidence",
            _bound_observation_schema(payload),
            str(payload["scoring_policy_version"]),
            str(payload["formula_version"]),
        )
    return None


def _matches_quality_series(payload: dict[str, Any], series: tuple[str, str, str, str]) -> bool:
    return _quality_series_for_payload(payload) == series


def _diagnostic_reason(payload: dict[str, Any], event_name: str = "") -> str:
    for key in ("reason", "error", "detail", "msg", "message"):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return str(value)
    for key in ("failures", "issues", "blocking_failures"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
    return event_name


def _diagnostic_files(payload: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for key in ("file", "path", "target_file"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            files.append(value.strip())
    raw_files = payload.get("files")
    if isinstance(raw_files, list):
        files.extend(str(value) for value in raw_files if str(value).strip())
    return list(dict.fromkeys(files))


def _stage_for_event(event_name: str, payload: dict[str, Any]) -> str | None:
    for stage, names in _PIPELINE_STAGE_EVENTS.items():
        if event_name in names:
            return stage
    if event_name not in {"WorkflowBlocked", "WorkflowAborted"}:
        return None
    task = str(payload.get("task", "")).lower()
    source = str(payload.get("source_command", "")).lower()
    step = str(payload.get("step", "")).lower()
    reason = _diagnostic_reason(payload).lower()
    combined = " ".join((task, source, step, reason))
    mappings = (
        ("planning", "plan"),
        ("planissue", "plan"),
        ("scope", "plan"),
        ("implementation", "implement"),
        ("implement", "implement"),
        ("no_progress", "implement"),
        ("review", "review"),
        ("healing", "healing"),
        ("heal", "healing"),
        ("quality", "quality"),
        ("eval", "eval"),
        ("gate", "gates"),
        ("llm", "llm"),
        ("token", "llm"),
        ("provider", "llm"),
    )
    for marker, stage in mappings:
        if marker in combined:
            return stage
    return None


def _empty_pipeline_stage() -> dict[str, Any]:
    return {
        "status": "pending",
        "last_ts": "",
        "count": 0,
        "fail_count": 0,
        "reason": "",
        "event": "",
        "file": "",
        "files": [],
    }


def _events_for_latest_correlation(
    issue_events: list[tuple[str, str, dict, dict]],
    *,
    signal_names: set[str],
) -> list[tuple[str, str, dict, dict]]:
    """Keep a stage outcome inside its latest attributable workflow run.

    Historical audit rows without a correlation id retain the legacy issue-wide
    fallback.  Once a latest signal is correlated, older runs cannot make the
    current stage look successful or failed (#578).
    """

    latest = next(
        (event for event in reversed(issue_events) if event[1] in signal_names),
        None,
    )
    if latest is None:
        return issue_events
    correlation_id = str(latest[2].get("correlation_id") or "")
    if not correlation_id:
        return issue_events
    return [
        event
        for event in issue_events
        if str(event[2].get("correlation_id") or "") == correlation_id
    ]


def _derive_healing_stage(
    issue_events: list[tuple[str, str, dict, dict]],
) -> dict[str, Any]:
    """Derive healing from attempts, not from classification or reason text."""

    signal_names = {
        "HealingClassified",
        "HealingAttemptStarted",
        "HealingAttemptCompleted",
        "HealingSuggested",
        "HealingAborted",
        "WorkflowBlocked",
        "WorkflowAborted",
    }
    relevant = [
        event
        for event in issue_events
        if event[1]
        in {
            "HealingClassified",
            "HealingAttemptStarted",
            "HealingAttemptCompleted",
            "HealingSuggested",
            "HealingAborted",
        }
        or (
            event[1] in {"WorkflowBlocked", "WorkflowAborted"}
            and _stage_for_event(event[1], event[2]) == "healing"
        )
    ]
    if not relevant:
        return _empty_pipeline_stage()
    relevant = _events_for_latest_correlation(relevant, signal_names=signal_names)

    started_keys: set[tuple[str, str]] = set()
    completed_keys: set[tuple[str, str]] = set()
    for index, event in enumerate(relevant):
        _, name, payload, _ = event
        if name not in {"HealingAttemptStarted", "HealingAttemptCompleted"}:
            continue
        observation = str(
            payload.get("observation_key") or payload.get("correlation_id") or "legacy"
        )
        raw_attempt = payload.get("attempt")
        attempt = str(raw_attempt) if raw_attempt not in (None, "") else f"event-{index}"
        key = (observation, attempt)
        if name == "HealingAttemptStarted":
            started_keys.add(key)
        else:
            completed_keys.add(key)
    attempt_count = len(started_keys | completed_keys)

    if attempt_count == 0:
        # Classification and availability blocks describe why no attempt was
        # possible; they are not failed LLM healing attempts.
        diagnostic = next(
            (event for event in reversed(relevant) if event[1] == "HealingClassified"),
            relevant[-1],
        )
        ts, name, payload, _ = diagnostic
        return {
            **_empty_pipeline_stage(),
            "status": "not_attempted",
            "last_ts": ts,
            "reason": _diagnostic_reason(payload, name),
            "event": name,
        }

    last_ts, last_name, last_payload, _ = relevant[-1]
    terminal_failure = last_name in {"HealingAborted", "WorkflowBlocked", "WorkflowAborted"}
    completed = any(
        name in {"HealingAttemptCompleted", "HealingSuggested"} for _, name, _, _ in relevant
    )
    status = "failed" if terminal_failure else "done" if completed else "pending"
    files = _diagnostic_files(last_payload) if status == "failed" else []
    return {
        "status": status,
        "last_ts": last_ts,
        "count": attempt_count,
        "fail_count": 1 if terminal_failure else 0,
        "reason": _diagnostic_reason(last_payload, last_name) if status == "failed" else "",
        "event": last_name if status == "failed" else "",
        "file": files[0] if files else "",
        "files": files,
    }


def _derive_pr_stage(
    issue_events: list[tuple[str, str, dict, dict]],
) -> dict[str, Any]:
    """Derive PR state from bound gate and SCM outcome evidence (#578)."""

    signal_names = {
        "CreatePR",
        "GateEvaluationCompleted",
        "PRCreated",
        "PRCreationFailed",
        "EvaluationSubjectInvalidated",
    }
    scoped = _events_for_latest_correlation(issue_events, signal_names=signal_names)
    pr_outcomes = [
        event
        for event in scoped
        if event[1] in {"PRCreated", "PRCreationFailed", "EvaluationSubjectInvalidated"}
    ]
    created = [event for event in pr_outcomes if event[1] == "PRCreated"]
    failures = [event for event in pr_outcomes if event[1] != "PRCreated"]
    if pr_outcomes:
        last_ts, last_name, last_payload, _ = pr_outcomes[-1]
        status = "done" if last_name == "PRCreated" else "failed"
        files = _diagnostic_files(last_payload) if status == "failed" else []
        return {
            "status": status,
            "last_ts": last_ts,
            "count": len(created),
            "fail_count": len(failures),
            "reason": _diagnostic_reason(last_payload, last_name) if status == "failed" else "",
            "event": last_name if status == "failed" else "",
            "file": files[0] if files else "",
            "files": files,
        }

    blocked = [
        event
        for event in scoped
        if event[1] == "GateEvaluationCompleted" and event[2].get("blocked") is True
    ]
    if blocked:
        ts, name, payload, _ = blocked[-1]
        if payload.get("manual_pending") is True:
            return {
                **_empty_pipeline_stage(),
                "last_ts": ts,
                "reason": "Waiting for human acceptance before PR creation",
                "event": name,
            }
        return {
            **_empty_pipeline_stage(),
            "status": "blocked",
            "last_ts": ts,
            "reason": "Required gate profile blocked the candidate before PR creation",
            "event": name,
        }

    # CreatePR proves only dispatch.  It deliberately leaves the outcome
    # pending until SCM confirmation or an explicit terminal event arrives.
    dispatched = [event for event in scoped if event[1] == "CreatePR"]
    if dispatched:
        stage = _empty_pipeline_stage()
        stage["last_ts"] = dispatched[-1][0]
        return stage
    return _empty_pipeline_stage()


def _derive_review_stage(
    issue_events: list[tuple[str, str, dict, dict]],
) -> dict[str, Any]:
    """Keep PR creation pending until its configured review has an outcome."""

    names = {"PRCreated", "ReviewCompleted", "ReviewBlocked", "MergeOutcomeUnknown"}
    scoped = _events_for_latest_correlation(issue_events, signal_names=names)
    outcomes = [event for event in scoped if event[1] in names]
    if not outcomes:
        return _empty_pipeline_stage()
    last_ts, last_name, payload, _ = outcomes[-1]
    if last_name in {"ReviewBlocked", "MergeOutcomeUnknown"}:
        files = _diagnostic_files(payload)
        return {
            "status": "failed",
            "last_ts": last_ts,
            "count": len(outcomes),
            "fail_count": 1,
            "reason": _diagnostic_reason(payload, last_name),
            "event": last_name,
            "file": files[0] if files else "",
            "files": files,
        }
    if last_name == "ReviewCompleted":
        return {
            **_empty_pipeline_stage(),
            "status": "done",
            "last_ts": last_ts,
            "count": len(outcomes),
        }
    return {
        **_empty_pipeline_stage(),
        "status": "pending" if payload.get("review_required") is True else "done",
        "last_ts": last_ts,
        "count": 1,
    }


def _derive_gates_stage(
    issue_events: list[tuple[str, str, dict, dict]],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Let the terminal bound gate outcome win over generic event ordering."""

    candidate_events = [
        event
        for event in issue_events
        if event[1]
        in {
            "CandidateVerificationPending",
            "CandidateEvaluationCompleted",
            "CandidateEvaluationFailed",
            "CandidateSubmissionRejected",
            "ProviderVerificationPending",
            "ProviderVerificationBlocked",
        }
    ]
    if candidate_events:
        candidate_events = _events_for_latest_correlation(
            candidate_events,
            signal_names={
                "CandidateVerificationPending",
                "CandidateEvaluationCompleted",
                "CandidateEvaluationFailed",
                "CandidateSubmissionRejected",
                "ProviderVerificationPending",
                "ProviderVerificationBlocked",
            },
        )
        ts, name, payload, _ = candidate_events[-1]
        if name in {"CandidateVerificationPending", "ProviderVerificationPending"}:
            return {
                **_empty_pipeline_stage(),
                "last_ts": ts,
                "reason": _diagnostic_reason(payload, name),
                "event": name,
            }
        failed = name in {
            "CandidateEvaluationFailed",
            "CandidateSubmissionRejected",
            "ProviderVerificationBlocked",
        }
        return {
            **current,
            "status": "failed" if failed else "done",
            "last_ts": ts,
            "fail_count": 1 if failed else 0,
            "reason": _diagnostic_reason(payload, name) if failed else "",
            "event": name,
        }

    completed = [
        event
        for event in issue_events
        if event[1] in {"GateEvaluationCompleted", "ProviderGateEvaluationCompleted"}
    ]
    if not completed:
        return current
    completed = _events_for_latest_correlation(
        completed,
        signal_names={"GateEvaluationCompleted", "ProviderGateEvaluationCompleted"},
    )
    ts, name, payload, _ = completed[-1]
    if payload.get("blocked") is not True:
        return current
    if payload.get("manual_pending") is True:
        return {
            **current,
            "status": "pending",
            "last_ts": ts,
            "reason": "Waiting for human acceptance",
            "event": name,
        }
    failed_results = [
        result
        for result in payload.get("gate_results", [])
        if isinstance(result, dict) and result.get("passed") is False
    ]
    reason = next(
        (str(result.get("reason")) for result in failed_results if result.get("reason")),
        "Required gate profile blocked the candidate",
    )
    return {
        **current,
        "status": "failed",
        "last_ts": ts,
        "fail_count": max(1, int(current.get("fail_count", 0) or 0)),
        "reason": reason,
        "event": name,
    }


def get_workflow_issue_detail(
    issue_num: int,
    data_dir: str = "data",
    limit: int = 1000,
    projection_store: IRunProjectionStore | None = None,
) -> dict[str, Any] | None:
    """Detailed view for a single issue: audit trail, pipeline stages, score, LLM.

    Returns ``None`` if no events for this issue. Otherwise a dict with:
    - ``number``: the issue number
    - ``status``: overall status (mirrors get_workflow_issues)
    - ``branch``: last branch name seen in any event
    - ``events``: up to 30 audit events for this issue (newest last) with
      timestamp/level/category/event/message/owasp/gate/action
    - ``stages``: per-stage summary dict (plan/implement/llm/gates/eval/
      quality/pr/review): status is ``done``, ``failed``, ``pending``,
      ``blocked`` or ``not_attempted`` plus timestamp and outcome counters.
    - ``score``: latest Evaluate/EvalCompleted aggregate (value, baseline,
      passed, checks_passed, checks_total, last_ts, reason)
    - ``llm``: aggregated LLMCallCompleted (calls, tokens, cost, by_provider,
      by_task)
    """
    events = load_runtime_events(data_dir, max(limit, 100_000), projection_store)
    issue_events: list[tuple[str, str, dict, dict]] = []  # ts, name, payload, raw_evt
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        try:
            evt_issue = int(payload.get("issue") or 0)
        except (TypeError, ValueError):
            continue
        if evt_issue != issue_num:
            continue
        msg_name = payload.get("message_name") or ""
        issue_events.append((evt.get("ts", ""), msg_name, payload, evt))

    if not issue_events:
        return None

    # --- audit trail (last 30, newest last for chronological reading) ---
    trail: list[dict[str, Any]] = []
    for ts, name, payload, evt in issue_events[-30:]:
        cat = _classify_category(evt)
        evt_key = str(payload.get("evt") or payload.get("event_name") or "")
        trail.append(
            {
                "timestamp": ts,
                "level": _classify_level(evt),
                "category": cat,
                "event": name,
                "message": _build_message(evt),
                "owasp": payload.get("owasp_risk") or _classify_owasp(cat, evt_key) or "",
                "ai_act": _classify_ai_act(cat, evt_key) or "",
                "gate": payload.get("gate", ""),
                "reason": payload.get("reason", ""),
            }
        )

    # --- pipeline stages ---
    stages: dict[str, dict[str, Any]] = {}
    for stage in _PIPELINE_STAGE_EVENTS:
        scoped_events = issue_events
        if stage == "quality":
            scoped_events = _events_for_latest_correlation(
                issue_events, signal_names=_PIPELINE_STAGE_EVENTS[stage] | {"PRMerged"}
            )
        matched = [
            (ts, name, payload)
            for ts, name, payload, _ in scoped_events
            if name in _PIPELINE_STAGE_EVENTS[stage]
            or (
                name in {"WorkflowBlocked", "WorkflowAborted"}
                and _stage_for_event(name, payload) == stage
            )
        ]
        if not matched:
            stages[stage] = _empty_pipeline_stage()
            if stage == "quality":
                facts = _latest_workflow_run_facts(
                    [(ts, name, payload) for ts, name, payload, _ in issue_events]
                )
                outcome = reduce_workflow_outcome((name, payload) for _, name, payload in facts)
                if outcome.status == "merged":
                    stages[stage].update(
                        status="not_attempted",
                        reason="Kein separater Quality-Aufruf beobachtet; Gates und CI sind eigene Nachweise.",
                    )
            continue
        fail = sum(1 for _, n, _ in matched if n in _STAGE_FAIL_EVENTS)
        last_ts, last_name, last_payload = matched[-1]
        status = "failed" if last_name in _STAGE_FAIL_EVENTS else "done"
        files = _diagnostic_files(last_payload) if status == "failed" else []
        stages[stage] = {
            "status": status,
            "last_ts": last_ts,
            "count": len(matched),
            "fail_count": fail,
            "reason": _diagnostic_reason(last_payload, last_name) if status == "failed" else "",
            "event": last_name if status == "failed" else "",
            "file": files[0] if files else "",
            "files": files,
        }
    stages["gates"] = _derive_gates_stage(issue_events, stages["gates"])
    stages["healing"] = _derive_healing_stage(issue_events)
    stages["pr"] = _derive_pr_stage(issue_events)
    stages["review"] = _derive_review_stage(issue_events)

    # --- overall status (same reducer as get_workflow_issues) ---
    overall_status, status_event, status_timestamp = _derive_workflow_issue_state(
        [(ts, name, payload) for ts, name, payload, _ in issue_events]
    )
    last_branch = ""
    for _ts, _name, payload, _ in issue_events:
        if payload.get("branch"):
            last_branch = str(payload["branch"])

    # --- non-binding quality observation (legacy eval remains readable) ---
    score: dict[str, Any] = {
        "label": "Nicht bindende Qualitätsbeobachtung",
        "non_binding": True,
        "value": None,
        "baseline": None,
        "passed": None,
        "checks_passed": None,
        "checks_total": None,
        "last_ts": "",
        "reason": "",
    }
    for ts, name, payload, _ in issue_events:
        if name == "ScoreObserved" and _is_bound_score_observation(payload):
            score["value"] = payload.get("score")
            score["baseline"] = None
            score["passed"] = None
            score["coverage"] = payload.get("coverage")
            score["status"] = payload.get("status")
            score["formula_version"] = payload.get("formula_version")
            score["scoring_policy_version"] = payload.get("scoring_policy_version")
            score["evidence_origin"] = payload.get("evidence_origin")
            score["last_ts"] = ts
            score["reason"] = str(payload.get("not_scoreable_reason", "") or "")
        elif name in ("Evaluate", "EvalCompleted", "EvalFailed"):
            score["label"] = "Legacy-Evaluation (historisch)"
            score["non_binding"] = False
            if "score" in payload:
                score["value"] = payload.get("score")
            if "baseline" in payload:
                score["baseline"] = payload.get("baseline")
            if "checks_passed" in payload:
                score["checks_passed"] = payload.get("checks_passed")
            if "checks_total" in payload:
                score["checks_total"] = payload.get("checks_total")
            score["last_ts"] = ts
            if name == "EvalCompleted":
                score["passed"] = True
                score["reason"] = ""
            elif name == "EvalFailed":
                score["passed"] = False
                score["reason"] = str(payload.get("reason", ""))

    # --- LLM aggregation ---
    llm_calls = 0
    llm_tokens = 0
    llm_cost = 0.0
    by_provider: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "tokens": 0, "cost": 0.0}
    )
    by_task: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    calls_detail: list[dict[str, Any]] = []
    for ts, name, payload, _ in issue_events:
        if name != "LLMCallCompleted":
            continue
        llm_calls += 1
        tokens = payload.get("tokens") or (
            int(payload.get("input_tokens", 0)) + int(payload.get("output_tokens", 0))
        )
        cost = float(payload.get("cost", 0.0) or 0.0)
        provider = str(payload.get("provider", "unknown"))
        task = str(payload.get("task", "unknown"))
        llm_tokens += int(tokens or 0)
        llm_cost += cost
        by_provider[provider]["calls"] += 1
        by_provider[provider]["tokens"] += int(tokens or 0)
        by_provider[provider]["cost"] += cost
        by_task[task]["calls"] += 1
        by_task[task]["tokens"] += int(tokens or 0)
        by_task[task]["cost"] += cost
        calls_detail.append(
            {
                "timestamp": ts,
                "task": task,
                "provider": provider,
                "model": str(payload.get("model", "")),
                "tokens": int(tokens or 0),
                "cost": round(cost, 6),
                "latency_ms": payload.get("latency_ms"),
                "stop_reason": str(payload.get("stop_reason", "")),
                "guards": list(payload.get("guards", []) or []),
                "tools_loaded": list(payload.get("tools_loaded", []) or []),
                "context_sections": list(payload.get("context_sections", []) or []),
                "prompt_tokens_est": payload.get("prompt_tokens_est"),
            }
        )

    # --- TEST runs aggregation (TestRunCompleted events for this issue) ---
    test_runs: list[dict[str, Any]] = []
    for ts, name, payload, _ in issue_events:
        if name != "TestRunCompleted":
            continue
        test_runs.append(
            {
                "timestamp": ts,
                "test_name": str(payload.get("test_name", "")),
                "runner": str(payload.get("runner", "unknown")),
                "passed": bool(payload.get("passed", False)),
                "exit_code": payload.get("exit_code"),
                "duration_ms": payload.get("duration_ms"),
            }
        )

    # --- Plan-Context aggregation (#237 PlanContextLoaded) ---
    plan_context: dict[str, Any] = {}
    for ts, name, payload, _ in issue_events:
        if name != "PlanContextLoaded":
            continue
        plan_context = {
            "timestamp": ts,
            "skeleton_tokens": int(payload.get("skeleton_tokens", 0) or 0),
            "relevant_files_count": int(payload.get("relevant_files_count", 0) or 0),
            "grep_hits": int(payload.get("grep_hits", 0) or 0),
            "total_context_tokens": int(payload.get("total_context_tokens", 0) or 0),
        }

    # --- Healing-Loop aggregation (#239) ---
    healing: dict[str, Any] = {"attempts": [], "total_tokens": 0, "why_stopped": ""}
    for ts, name, payload, _ in issue_events:
        if name == "HealingAttemptCompleted":
            healing["attempts"].append(
                {
                    "timestamp": ts,
                    "n": int(payload.get("attempt", 0) or 0),
                    "prev_score": payload.get("prev_score"),
                    "new_score": payload.get("new_score"),
                    "delta": payload.get("score_delta"),
                    "tokens": int(payload.get("tokens_used", 0) or 0),
                    "status": str(payload.get("status", "")),
                }
            )
            healing["total_tokens"] += int(payload.get("tokens_used", 0) or 0)
        elif name == "HealingAborted":
            healing["why_stopped"] = str(payload.get("reason", ""))

    # --- Plan-Pre-Check + Complexity (#238) ---
    pre_check: dict[str, Any] = {}
    complexity: dict[str, Any] = {}
    for ts, name, payload, _ in issue_events:
        if name == "PlanPreCheckCompleted":
            pre_check = {
                "timestamp": ts,
                "structural": payload.get("structural_score"),
                "skeleton": payload.get("skeleton_score"),
                "ac_dry_run": payload.get("ac_dry_run_score"),
                "coverage": payload.get("coverage_score"),
                "coverage_missing": list(payload.get("coverage_missing") or []),
                "overall_pass": bool(payload.get("overall_pass", False)),
                "retry_attempt": int(payload.get("retry_attempt", 0) or 0),
                "blocking_failures": list(payload.get("blocking_failures") or []),
            }
            cx = payload.get("complexity")
            if isinstance(cx, dict):
                complexity = {
                    "ac_count": int(cx.get("ac_count", 0) or 0),
                    "file_count": int(cx.get("file_count", 0) or 0),
                    "slice_count": int(cx.get("slice_count", 0) or 0),
                    "pflicht_bereich_count": int(cx.get("pflicht_bereich_count", 0) or 0),
                    "recommendation": str(cx.get("recommendation", "ok")),
                }
        elif name == "PlanComplexityWarn":
            complexity = {
                "ac_count": int(payload.get("ac_count", 0) or 0),
                "file_count": int(payload.get("file_count", 0) or 0),
                "slice_count": int(payload.get("slice_count", 0) or 0),
                "pflicht_bereich_count": int(payload.get("pflicht_bereich_count", 0) or 0),
                "recommendation": str(payload.get("recommendation", "ok")),
            }

    # --- AC evidence/readiness aggregation for this issue ---
    # MANUAL is an explicit pending state, never an automatic failure (#514).
    acceptance_checks: list[dict[str, Any]] = []
    for ts, name, payload, _ in issue_events:
        if name not in ("ACVerified", "ACFailed", "ACManualPending"):
            continue
        raw_passed = payload.get("passed")
        status = str(
            payload.get("status")
            or (
                "manual_pending"
                if name == "ACManualPending"
                else "passed"
                if raw_passed is True
                else "failed"
            )
        )
        acceptance_checks.append(
            {
                "timestamp": ts,
                "tag": str(payload.get("tag", "")),
                "arg": str(payload.get("arg", "")),
                "passed": raw_passed if isinstance(raw_passed, bool) else None,
                "status": status,
                "reason": str(payload.get("reason", "")),
                "criterion_id": str(payload.get("criterion_id", "")),
                "evaluation_subject": payload.get("evaluation_subject"),
                "correlation_id": str(payload.get("correlation_id", "")),
            }
        )
    # Keep the historical trail, but do not present an old MANUAL wait as the
    # current result. Never transfer evidence across candidate or run bindings.
    active_binding = next(
        (
            (payload["evaluation_subject"], str(payload.get("correlation_id", "")))
            for _, name, payload, _ in reversed(issue_events)
            if name == "GateEvaluationCompleted"
            and isinstance(payload.get("evaluation_subject"), dict)
        ),
        None,
    )
    seen_criteria: set[str] = set()
    for check in reversed(acceptance_checks):
        criterion = check["criterion_id"]
        bound = isinstance(check["evaluation_subject"], dict) and bool(criterion)
        check["current"] = None
        if bound and active_binding is not None:
            matches = (check["evaluation_subject"], check["correlation_id"]) == active_binding
            check["current"] = matches and criterion not in seen_criteria
            if matches:
                seen_criteria.add(criterion)
    # Cap auf last 50 — bei vielen ACs nicht den Trail sprengen
    acceptance_checks = acceptance_checks[-50:]

    provider_verifications: list[dict[str, Any]] = []
    for ts, name, payload, _ in issue_events:
        if name not in {
            "ProviderVerificationRequested",
            "ProviderVerificationPending",
            "ProviderVerificationBlocked",
            "ProviderGateEvaluationCompleted",
        }:
            continue
        run = payload.get("provider_run")
        run = run if isinstance(run, dict) else {}
        provider_verifications.append(
            {
                "timestamp": ts,
                "event": name,
                "request_key": str(payload.get("request_key", "")),
                "profile": str(payload.get("provider_profile", "")),
                "profile_digest": str(payload.get("provider_profile_digest", "")),
                "run_id": str(run.get("run_id", "")),
                "attempt": run.get("attempt"),
                "status": str(payload.get("status", "")),
                "reason_code": str(payload.get("reason_code", "")),
                "mutation_authority": str(payload.get("mutation_authority", "none")),
            }
        )
    provider_verifications = provider_verifications[-50:]

    gate_results: list[dict[str, Any]] = []
    for ts, name, payload, _ in reversed(issue_events):
        if name not in {"GateEvaluationCompleted", "ProviderGateEvaluationCompleted"}:
            continue
        raw_results = payload.get("gate_results")
        if not isinstance(raw_results, list):
            break
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            passed = item.get("passed")
            executed = item.get("executed")
            status = str(item.get("status") or "")
            if type(executed) is not bool:
                executed = passed is not None
            if not status:
                status = "passed" if passed is True else "failed"
            gate_results.append(
                {
                    "timestamp": ts,
                    "gate": str(item.get("gate", "")),
                    "authority": str(item.get("authority", "")),
                    "phase": str(item.get("phase", "")),
                    "executed": executed,
                    "passed": passed if isinstance(passed, bool) else None,
                    "status": status,
                    "reason_code": str(item.get("reason_code", "")),
                    "reason": str(item.get("reason", "")),
                }
            )
        break

    runs = get_workflow_runs(
        issue_num,
        data_dir,
        limit,
        projection_store=projection_store,
    )
    trend = _classify_workflow_trend(runs)

    return {
        "number": issue_num,
        "status": overall_status,
        "last_event": status_event,
        "status_timestamp": status_timestamp,
        "branch": last_branch,
        "events": trail,
        "stages": stages,
        "score": score,
        "test_runs": test_runs,
        "acceptance_checks": acceptance_checks,
        "provider_verifications": provider_verifications,
        "gate_results": gate_results,
        "plan_context": plan_context,
        "pre_check": pre_check,
        "complexity": complexity,
        "healing": healing,
        "runs": runs,
        "trend": trend,
        "llm": {
            "calls": llm_calls,
            "tokens": llm_tokens,
            "cost": round(llm_cost, 6),
            "by_provider": {k: {**v, "cost": round(v["cost"], 6)} for k, v in by_provider.items()},
            "by_task": {k: {**v, "cost": round(v["cost"], 6)} for k, v in by_task.items()},
            "calls_detail": calls_detail,
        },
    }


_ERROR_EVENT_NAMES: set[str] = {
    "WorkflowAborted",
    "WorkflowBlocked",
    "GateFailed",
    "EvalFailed",
    "QualityFailed",
    "PlanBlocked",
    "PlanReplanRejected",
    "PRCreationFailed",
    "EvaluationSubjectInvalidated",
    "CandidateEvaluationFailed",
    "CandidateSubmissionRejected",
    "ProviderVerificationBlocked",
}


def _classify_run_final_status(events: list[tuple[str, str, dict]]) -> str:
    """Derive display status from the shared workflow-outcome authority."""

    outcome = reduce_workflow_outcome((name, payload) for _, name, payload in events)
    if outcome.status != "running":
        return outcome.status
    if any(name == "EvalFailed" for _, name, _ in events):
        return "eval_failed"
    return "incomplete"


_RUN_PASSED_STATUSES: set[str] = {"pr_created", "reviewed", "merged", "evaluated"}


def get_workflow_runs(
    issue_num: int,
    data_dir: str = "data",
    limit: int = 2000,
    projection_store: IRunProjectionStore | None = None,
) -> list[dict[str, Any]]:
    """#277: list every workflow run for a single issue, grouped by
    ``correlation_id``.

    Returns runs in chronological order (oldest first, run #1 first). Per
    run:
    - ``run_id``: ``correlation_id`` of the seed event
    - ``start_ts`` / ``end_ts``
    - ``final_status``: see ``_classify_run_final_status``
    - ``score``: latest Eval{Completed,Failed} score in this run, or None
    - ``stages_done`` / ``stages_failed``: counts across pipeline stages
    - ``gate_failures``: list of GateFailed reasons
    - ``pr_number``: PR number if PRCreated emitted in this run
    - ``event_count``: total events seen with this correlation_id

    Events without a ``correlation_id`` are dropped — they cannot be
    attributed to a run unambiguously.
    """
    events = load_runtime_events(data_dir, max(limit, 100_000), projection_store)
    by_corr: dict[str, list[tuple[str, str, dict]]] = {}
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        try:
            evt_issue = int(payload.get("issue") or 0)
        except (TypeError, ValueError):
            continue
        if evt_issue != issue_num:
            continue
        corr = str(payload.get("correlation_id") or "")
        if not corr:
            continue
        name = str(payload.get("message_name") or "")
        by_corr.setdefault(corr, []).append((evt.get("ts", ""), name, payload))

    runs: list[dict[str, Any]] = []
    for corr, evts in by_corr.items():
        evts.sort(key=lambda x: x[0])
        names = [name for _, name, _ in evts]

        score: float | None = None
        for _, n, p in evts:
            if n in ("ScoreObserved", "EvalCompleted", "EvalFailed") and "score" in p:
                try:
                    score = float(p["score"])
                except (TypeError, ValueError) as exc:
                    log.warning("Invalid evaluation score in audit event: %s", exc)

        done_stage_names = {
            s
            for s, ns in _PIPELINE_STAGE_EVENTS.items()
            if any(n in ns and n not in _STAGE_FAIL_EVENTS for n in names)
        }
        failed_stage_names = {
            s
            for s, ns in _PIPELINE_STAGE_EVENTS.items()
            if any(n in ns and n in _STAGE_FAIL_EVENTS for n in names)
        }
        completed_gate_payloads = [
            p
            for _, n, p in evts
            if n in {"GateEvaluationCompleted", "ProviderGateEvaluationCompleted"}
        ]
        if completed_gate_payloads and completed_gate_payloads[-1].get("manual_pending") is True:
            done_stage_names.discard("gates")
            failed_stage_names.discard("gates")
        elif completed_gate_payloads and completed_gate_payloads[-1].get("blocked") is True:
            done_stage_names.discard("gates")
            failed_stage_names.add("gates")
        candidate_outcomes = [
            name
            for name in names
            if name
            in {
                "CandidateVerificationPending",
                "CandidateEvaluationCompleted",
                "CandidateEvaluationFailed",
                "CandidateSubmissionRejected",
                "ProviderVerificationPending",
                "ProviderVerificationBlocked",
            }
        ]
        if candidate_outcomes:
            candidate_outcome = candidate_outcomes[-1]
            if candidate_outcome in {
                "CandidateVerificationPending",
                "ProviderVerificationPending",
            }:
                done_stage_names.discard("gates")
                failed_stage_names.discard("gates")
            elif candidate_outcome in {
                "CandidateEvaluationFailed",
                "CandidateSubmissionRejected",
                "ProviderVerificationBlocked",
            }:
                done_stage_names.discard("gates")
                failed_stage_names.add("gates")
        healing_started = "HealingAttemptStarted" in names
        healing_completed = any(
            name in {"HealingAttemptCompleted", "HealingSuggested"} for name in names
        )
        healing_failed = "HealingAborted" in names or any(
            name in {"WorkflowBlocked", "WorkflowAborted"}
            and _stage_for_event(name, payload) == "healing"
            for _, name, payload in evts
        )
        if healing_failed and (healing_started or healing_completed):
            done_stage_names.discard("healing")
            failed_stage_names.add("healing")
        elif healing_started and not healing_completed:
            done_stage_names.discard("healing")
        stages_done = len(done_stage_names)
        stages_failed = len(failed_stage_names)

        gate_failures = [
            {
                "ts": ts,
                "gate": str(p.get("gate", "")),
                "reason": str(p.get("reason", "")),
            }
            for ts, n, p in evts
            if n == "GateFailed"
        ]

        pr_number: int | None = None
        for _, n, p in evts:
            if n == "PRCreated" and p.get("pr_number"):
                try:
                    pr_number = int(p["pr_number"])
                except (TypeError, ValueError) as exc:
                    log.warning("Invalid PR number in audit event: %s", exc)

        final_status = _classify_run_final_status(evts)
        if final_status == "unbound":
            continue
        runs.append(
            {
                "run_id": corr,
                "start_ts": evts[0][0],
                "end_ts": evts[-1][0],
                "final_status": final_status,
                "score": score,
                "stages_done": stages_done,
                "stages_failed": stages_failed,
                "gate_failures": gate_failures,
                "pr_number": pr_number,
                "event_count": len(evts),
            }
        )

    runs.sort(key=lambda r: r["start_ts"])
    return runs


def _classify_workflow_trend(runs: list[dict[str, Any]]) -> str:
    """#277: derive a trend marker from the last two runs.

    - ``recovered`` — last run passed, previous one did not
    - ``regressed`` — last run failed, previous one passed
    - ``passed``    — both runs passed
    - ``failed``    — both runs failed
    - ``""`` (empty) — fewer than 2 runs (no trend yet)
    """
    if len(runs) < 2:
        return ""
    terminal = _RUN_PASSED_STATUSES | {"blocked", "aborted", "eval_failed"}
    if any(run["final_status"] not in terminal for run in runs[-2:]):
        return ""
    last_passed = runs[-1]["final_status"] in _RUN_PASSED_STATUSES
    prev_passed = runs[-2]["final_status"] in _RUN_PASSED_STATUSES
    if last_passed and prev_passed:
        return "passed"
    if last_passed and not prev_passed:
        return "recovered"
    if not last_passed and prev_passed:
        return "regressed"
    return "failed"


def get_command_metrics(data_dir: str = "data", limit: int = 2000) -> dict[str, Any]:
    """Aggregate command metrics from persisted audit log.

    Returns counts/total_ms/errors per command name across all rotated
    audit jsonl files. This is cross-process: a dashboard reading the
    metrics sees commands processed by any other run too.

    - ``counts``: number of times each Command was dispatched
    - ``total_ms``: sum of ``payload.duration_ms`` over those calls (only
      counts events that include duration; older audit lines without the
      field are skipped here but still count toward ``counts``)
    - ``errors``: number of error-style events (WorkflowAborted etc.)
      attributed via ``payload.source_command``
    """
    events = load_audit_events(data_dir, limit)
    counts: dict[str, int] = defaultdict(int)
    errors: dict[str, int] = defaultdict(int)
    total_ms: dict[str, float] = defaultdict(float)

    for evt in events:
        payload = evt.get("payload", {}) or {}
        msg_name = payload.get("message_name") or ""
        msg_type = payload.get("message_type", "")
        if msg_type.endswith("Command") and msg_name:
            counts[msg_name] += 1
            duration = payload.get("duration_ms")
            if isinstance(duration, (int, float)):
                total_ms[msg_name] += float(duration)
            if payload.get("error"):
                errors[msg_name] += 1
        if msg_name in _ERROR_EVENT_NAMES:
            src = payload.get("source_command")
            if src:
                errors[src] += 1

    return {
        "counts": dict(counts),
        "errors": dict(errors),
        "total_ms": {k: round(v, 2) for k, v in total_ms.items()},
    }


_ANOMALY_LEVEL_EVENTS: dict[str, set[str]] = {
    "error": {
        "GateFailed",
        "WorkflowAborted",
        "WorkflowBlocked",
        "SecurityTripwireTriggered",
        "ImplementationFailed",
        "PRCreationFailed",
        "EvaluationSubjectInvalidated",
        "CandidateEvaluationFailed",
        "CandidateSubmissionRejected",
        "ProviderVerificationBlocked",
        "TamperDetected",
        "UnauthorizedChange",
        "IntegrityViolation",
    },
    "warn": {
        "HealingFailed",
        "QualityFailed",
        "EvalFailed",
        "TokenLimitHit",
        "LLMUnavailable",
        "LLMBudgetBlocked",
        "PlanBlocked",
        "PlanReplanRejected",
        "ReviewBlocked",
        "MergeOutcomeUnknown",
        # #239: HealingAborted ist Operator-Eingriff erforderlich
        "HealingAborted",
        # #247: Scope-Creep + Out-of-Scope-Diff (warn-only) als Anomalie sichtbar
        "ScopeCreepDetected",
        "OutOfScopeDiff",
    },
}


def get_score_history(
    data_dir: str = "data",
    limit: int = 15,
    observation_store: IObservationStore | None = None,
    projection_store: IRunProjectionStore | None = None,
) -> list[dict]:
    """Return passive bound observations plus readable legacy outcomes.

    Picks ``EvalCompleted`` and ``EvalFailed`` events (which carry score/
    baseline). ``Evaluate`` is skipped because it is fired before scoring
    completes and so has no score. Newest first. Each row:
    ``{timestamp, score, baseline, passed, reason, issue, correlation_id}``.
    """
    if observation_store is not None:
        derivations = observation_store.list_derivations()
        if derivations:
            newest = derivations[-1]
            selected = (
                newest.evidence_origin,
                newest.observation_schema,
                newest.scoring_policy_version,
                newest.formula_version,
            )
            derived_rows: list[dict] = []
            for record in reversed(derivations):
                series = (
                    record.evidence_origin,
                    record.observation_schema,
                    record.scoring_policy_version,
                    record.formula_version,
                )
                if series != selected:
                    continue
                payload = record.payload
                derived_rows.append(
                    {
                        "timestamp": record.derived_at.isoformat(),
                        "score": record.score,
                        "baseline": None,
                        "passed": None,
                        "non_binding": True,
                        "label": "Nicht bindende Qualitätsbeobachtung",
                        "reason": str(payload.get("not_scoreable_reason", "") or ""),
                        "issue": record.issue_number,
                        "correlation_id": "",
                        "coverage": payload.get("coverage"),
                        "formula_version": record.formula_version,
                        "scoring_policy_version": record.scoring_policy_version,
                        "observation_schema": record.observation_schema,
                        "evidence_origin": record.evidence_origin,
                    }
                )
                if len(derived_rows) >= limit:
                    break
            return derived_rows

    events = load_runtime_events(data_dir, 100_000, projection_store)
    rows: list[dict] = []
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        msg = payload.get("message_name", "")
        if msg == "ScoreObserved" and _is_bound_score_observation(payload):
            rows.append(
                {
                    "timestamp": evt.get("ts", ""),
                    "score": payload.get("score"),
                    "baseline": None,
                    "passed": None,
                    "non_binding": True,
                    "label": "Nicht bindende Qualitätsbeobachtung",
                    "reason": str(payload.get("not_scoreable_reason", "") or ""),
                    "issue": payload.get("issue"),
                    "correlation_id": payload.get("correlation_id", ""),
                    "coverage": payload.get("coverage"),
                    "formula_version": payload.get("formula_version"),
                    "scoring_policy_version": payload.get("scoring_policy_version"),
                    "observation_schema": _bound_observation_schema(payload),
                    "evidence_origin": payload.get("evidence_origin"),
                }
            )
            continue
        if msg not in ("EvalCompleted", "EvalFailed"):
            continue
        rows.append(
            {
                "timestamp": evt.get("ts", ""),
                "score": payload.get("score"),
                "baseline": payload.get("baseline"),
                "passed": msg == "EvalCompleted",
                "non_binding": False,
                "label": "Legacy-Evaluation (historisch)",
                "reason": str(payload.get("reason", "") or ""),
                "issue": payload.get("issue"),
                "correlation_id": payload.get("correlation_id", ""),
            }
        )
    rows.reverse()
    return rows[:limit]


def get_runtime_anomalies(data_dir: str = "data", hours: int = 24, limit: int = 50) -> list[dict]:
    """Return warn/error level events from the last ``hours`` for the
    Status-Tab Anomalies section. Newest first."""
    events = load_audit_events(data_dir, 1000)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows: list[dict] = []
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        msg = payload.get("message_name", "")
        level: str | None = None
        if msg in _ANOMALY_LEVEL_EVENTS["error"]:
            level = "error"
        elif (
            msg in _ANOMALY_LEVEL_EVENTS["warn"]
            or msg == "TestRunCompleted"
            and not payload.get("passed", True)
        ):
            level = "warn"
        elif msg == "PlanComplexityWarn" and payload.get("recommendation") == "split_recommended":
            # #238 Schicht A: Plan zu gross -> sichtbar als Anomalie.
            level = "warn"
        elif msg == "PlanPreCheckCompleted" and not payload.get("overall_pass", True):
            # #238: Pre-Check fehlgeschlagen -> Operator muss eingreifen.
            level = "warn"
        else:
            continue
        ts = _parse_audit_ts(evt.get("ts", ""))
        if ts is None:
            # Unparsable timestamps are kept (better visible than silently lost)
            pass
        elif ts < cutoff:
            continue
        cat = _classify_category(evt)
        evt_key = str(payload.get("evt") or payload.get("event_name") or "")
        rows.append(
            {
                "timestamp": evt.get("ts", ""),
                "level": level,
                "event": msg,
                "category": cat,
                "message": _build_message(evt),
                "issue": payload.get("issue"),
                "owasp": payload.get("owasp_risk") or _classify_owasp(cat, evt_key) or "",
            }
        )
    rows.reverse()
    return rows[:limit]


def _disk_usage_for(path: str) -> dict[str, Any]:
    """Return free/used/percent for the filesystem holding ``path``.

    Falls back gracefully if the path does not exist or stat fails — the
    Status-Tab tile then shows ``-``.
    """
    try:
        target = Path(path)
        # shutil.disk_usage requires an existing directory; walk up if needed
        while not target.exists() and target.parent != target:
            target = target.parent
        du = shutil.disk_usage(str(target))
        return {
            "total_gb": round(du.total / (1024**3), 1),
            "used_gb": round(du.used / (1024**3), 1),
            "free_gb": round(du.free / (1024**3), 1),
            "used_pct": round(du.used / du.total * 100, 1),
        }
    except OSError as exc:
        log.warning("disk_usage(%s) failed: %s", path, exc)
        return {"total_gb": None, "used_gb": None, "free_gb": None, "used_pct": None}


def get_system_tiles(data_dir: str = "data", config: Any = None, scm: Any = None) -> list[dict]:
    """Return system status tiles for the Status-Tab top grid.

    Each tile: ``{key, label, value, kind: 'ok'|'warn'|'err'|'neutral',
    detail}``. Tiles cover: SCM-connection, active LLM provider+model,
    disk usage of ``data_dir``, event volume in the last 24h, and the
    latest Eval outcome.
    """
    tiles: list[dict] = []

    # SCM
    repo = ""
    if config:
        repo = str(config.get("scm.repo", "") or config.get("scm_repo", "") or "")
    if scm is not None:
        tiles.append(
            {
                "key": "scm",
                "label": "SCM",
                "value": "connected",
                "kind": "ok",
                "detail": repo or "configured",
            }
        )
    else:
        tiles.append(
            {
                "key": "scm",
                "label": "SCM",
                "value": "offline",
                "kind": "err",
                "detail": "no SCM adapter",
            }
        )

    # LLM provider/model
    if config:
        provider = str(config.get("llm.default.provider", "-") or "-")
        model = "-"
        if provider != "-":
            model = str(config.get(f"llm.{provider}.model", "-") or "-")
        kind = "ok" if provider != "-" else "warn"
        tiles.append(
            {
                "key": "llm",
                "label": "LLM",
                "value": provider,
                "kind": kind,
                "detail": model,
            }
        )
    else:
        tiles.append(
            {
                "key": "llm",
                "label": "LLM",
                "value": "-",
                "kind": "warn",
                "detail": "no config",
            }
        )

    # Disk
    du = _disk_usage_for(data_dir)
    pct = du.get("used_pct")
    if pct is None:
        kind = "warn"
        value = "-"
        detail = "stat failed"
    else:
        if pct >= 90:
            kind = "err"
        elif pct >= 75:
            kind = "warn"
        else:
            kind = "ok"
        value = f"{du['free_gb']} GB free"
        detail = f"{pct}% used of {du['total_gb']} GB"
    tiles.append(
        {
            "key": "disk",
            "label": "Disk",
            "value": value,
            "kind": kind,
            "detail": detail,
        }
    )

    # Audit volume (24h)
    events = load_audit_events(data_dir, 2000)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = 0
    errors = 0
    for evt in events:
        ts = _parse_audit_ts(evt.get("ts", ""))
        if ts is not None and ts < cutoff:
            continue
        recent += 1
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("message_name", "") in _ANOMALY_LEVEL_EVENTS["error"]:
            errors += 1
    err_kind = "ok" if errors == 0 else "warn" if errors < 5 else "err"
    tiles.append(
        {
            "key": "events_24h",
            "label": "Events 24h",
            "value": str(recent),
            "kind": "ok" if recent else "neutral",
            "detail": f"{errors} errors" if errors else "no errors",
        }
    )
    tiles.append(
        {
            "key": "errors_24h",
            "label": "Errors 24h",
            "value": str(errors),
            "kind": err_kind,
            "detail": "GateFailed/Aborted/etc.",
        }
    )

    # Latest passive observation (or a readable legacy outcome)
    history = get_score_history(data_dir, limit=1)
    if history:
        h = history[0]
        score = h.get("score")
        baseline = h.get("baseline")
        passed = h.get("passed")
        non_binding = bool(h.get("non_binding"))
        kind = "neutral" if non_binding else "ok" if passed else "err"
        if score is not None and baseline is not None:
            value = f"{score} / {baseline}"
        elif score is not None:
            value = str(score)
        else:
            value = "n/a" if non_binding else "FAIL" if not passed else "OK"
        detail = h.get("timestamp", "")[:19] or "-"
        if h.get("reason"):
            detail = f"{detail} — {h['reason'][:40]}"
        tiles.append(
            {
                "key": "eval",
                "label": (
                    "Qualitätsbeobachtung (nicht bindend)"
                    if non_binding
                    else "Legacy-Evaluation (historisch)"
                ),
                "value": value,
                "kind": kind,
                "detail": detail,
            }
        )
    else:
        tiles.append(
            {
                "key": "eval",
                "label": "Qualitätsbeobachtung (nicht bindend)",
                "value": "-",
                "kind": "neutral",
                "detail": "no score observations",
            }
        )

    return tiles


def get_otel_gen_ai_calls(data_dir: str = "data", limit: int = 30) -> list[dict]:
    """Return recent LLM calls in OpenTelemetry ``gen_ai.*`` semantic-
    convention shape so the security tab can show them as instrumentation.

    Maps existing payload fields:
    - ``provider`` → ``gen_ai.system``
    - ``model``    → ``gen_ai.request.model``
    - ``tokens`` (or ``input_tokens + output_tokens``) → ``gen_ai.usage.total_tokens``
    - ``input_tokens`` → ``gen_ai.usage.input_tokens``
    - ``output_tokens`` → ``gen_ai.usage.output_tokens``
    - ``latency_ms`` → ``gen_ai.client.operation.duration``
    - ``stop_reason`` → ``gen_ai.response.finish_reasons``

    Newest first, capped at ``limit``.
    """
    events = load_audit_events(data_dir, 500)
    rows: list[dict] = []
    for evt in events:
        payload = evt.get("payload", {}) or {}
        if payload.get("message_name") != "LLMCallCompleted":
            continue
        total_tokens = payload.get("tokens")
        if total_tokens is None:
            in_t = int(payload.get("input_tokens", 0) or 0)
            out_t = int(payload.get("output_tokens", 0) or 0)
            total_tokens = in_t + out_t if (in_t or out_t) else None
        rows.append(
            {
                "timestamp": evt.get("ts", ""),
                "gen_ai.system": payload.get("provider", ""),
                "gen_ai.request.model": payload.get("model", ""),
                "gen_ai.usage.input_tokens": payload.get("input_tokens"),
                "gen_ai.usage.output_tokens": payload.get("output_tokens"),
                "gen_ai.usage.total_tokens": total_tokens,
                "gen_ai.client.operation.duration": payload.get("latency_ms"),
                "gen_ai.response.finish_reasons": payload.get("stop_reason", ""),
                "task": payload.get("task", ""),
            }
        )
    rows.reverse()
    return rows[:limit]


def get_token_history(data_dir: str = "data", limit: int = 50) -> list[dict]:
    """Chronological list of LLMCallCompleted events for the LLM-Tab history.

    Newest first. Returns ``[{timestamp, provider, model, task, tokens,
    input_tokens, output_tokens, cached_tokens, cost, latency_ms,
    stop_reason, issue}]``. ``issue`` is currently ``None`` for almost all
    events because LLMCallCompleted lacks an ``issue`` correlation field
    (see #206); kept here so the column auto-fills once that's fixed.
    """
    events = load_audit_events(data_dir, 500)
    rows: list[dict] = []
    for evt in events:
        payload = evt.get("payload", {}) or {}
        if payload.get("message_name") != "LLMCallCompleted":
            continue
        rows.append(
            {
                "timestamp": evt.get("ts", ""),
                "provider": payload.get("provider", ""),
                "model": payload.get("model", ""),
                "task": payload.get("task", ""),
                "tokens": payload.get("tokens"),
                "input_tokens": payload.get("input_tokens"),
                "output_tokens": payload.get("output_tokens"),
                "cached_tokens": payload.get("cached_tokens"),
                "reasoning_tokens": payload.get("reasoning_tokens"),
                "cost": payload.get("cost"),
                "latency_ms": payload.get("latency_ms"),
                "stop_reason": payload.get("stop_reason", ""),
                "issue": payload.get("issue"),
                "guards": list(payload.get("guards", []) or []),
                "tools_loaded": list(payload.get("tools_loaded", []) or []),
                "context_sections": list(payload.get("context_sections", []) or []),
                "prompt_tokens_est": payload.get("prompt_tokens_est"),
            }
        )
    rows.reverse()
    return rows[:limit]


def get_llm_quality_scores(
    data_dir: str = "data",
    limit: int = 500,
    projection_store: IRunProjectionStore | None = None,
) -> list[dict]:
    """Pair LLM calls with passive bound scores or readable legacy evals.

    For every LLMCall that shares a correlation_id with at least one
    EvalCompleted/EvalFailed in the same log, attribute that eval-outcome
    to the (provider, model, task) tuple.

    ``calls`` counts only the last LLM call attributed to an observation in the
    selected series. Calls without a valid observation (including earlier
    calls sharing the same correlation) are explicit ``unattributed_calls``;
    calls attributed to a different score series are ``other_series_calls``.
    """
    events = load_runtime_events(data_dir, max(limit, 100_000), projection_store)
    selected_series = _selected_quality_series(events)
    # Build correlation_id -> latest valid evaluation, across every series.
    eval_by_corr: dict[str, dict] = {}
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        msg = payload.get("message_name", "")
        series = _quality_series_for_payload(payload)
        if series is None:
            continue
        if msg == "ScoreObserved":
            passed: bool | None = None
        else:
            passed = msg == "EvalCompleted"
        corr = payload.get("correlation_id") or ""
        if not corr:
            continue
        eval_by_corr[corr] = {
            "series": series,
            "passed": passed,
            "score": payload.get("score"),
            "ts": evt.get("ts", ""),
        }

    by_key: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "unattributed_calls": 0,
            "other_series_calls": 0,
            "passed": 0,
            "failed": 0,
            "score_sum": 0.0,
            "score_count": 0,
            "last_ts": "",
        }
    )
    llm_calls: list[tuple[tuple[str, str, str], str, str]] = []
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("message_name") != "LLMCallCompleted":
            continue
        key = (
            str(payload.get("provider", "")),
            str(payload.get("model", "")),
            str(payload.get("task", "")),
        )
        bucket = by_key[key]
        bucket["last_ts"] = evt.get("ts", "")
        llm_calls.append((key, str(payload.get("correlation_id") or ""), evt.get("ts", "")))

    last_call_by_corr: dict[str, int] = {}
    for index, (_, corr, _) in enumerate(llm_calls):
        if corr:
            last_call_by_corr[corr] = index
    for index, (key, corr, _) in enumerate(llm_calls):
        bucket = by_key[key]
        eval_info = eval_by_corr.get(corr)
        if not corr or eval_info is None or last_call_by_corr.get(corr) != index:
            bucket["unattributed_calls"] += 1
            continue
        if eval_info["series"] != selected_series:
            bucket["other_series_calls"] += 1
            continue
        bucket["calls"] += 1
        if eval_info["passed"] is True:
            bucket["passed"] += 1
        elif eval_info["passed"] is False:
            bucket["failed"] += 1
        score = eval_info.get("score")
        if isinstance(score, (int, float)):
            bucket["score_sum"] += float(score)
            bucket["score_count"] += 1

    rows: list[dict] = []
    for (provider, model, task), b in by_key.items():
        graded = b["passed"] + b["failed"]
        rows.append(
            {
                "provider": provider,
                "model": model,
                "task": task,
                "calls": b["calls"],
                "unattributed_calls": b["unattributed_calls"],
                "other_series_calls": b["other_series_calls"],
                "graded": graded,
                "passed": b["passed"],
                "failed": b["failed"],
                "success_rate_pct": round(b["passed"] / graded * 100) if graded else None,
                "avg_score": round(b["score_sum"] / b["score_count"], 3)
                if b["score_count"]
                else None,
                "last_ts": b["last_ts"],
                "evidence_origin": selected_series[0],
                "observation_schema": selected_series[1],
                "scoring_policy_version": selected_series[2],
                "formula_version": selected_series[3],
            }
        )
    rows.sort(key=lambda r: r["last_ts"], reverse=True)
    return rows


def get_quality_from_log(
    data_dir: str = "data",
    limit: int = 5000,
    projection_store: IRunProjectionStore | None = None,
) -> list[dict]:
    """#153: Qualitaet pro (provider, model, task), korreliert ueber ``issue``.

    Anders als :func:`get_llm_quality_scores` (correlation_id, in v2 unzuverlaessig
    wegen #206) paart diese Funktion ueber die Issue-Nummer: das Eval-Outcome
    eines Issues wird dem **letzten** LLM-Call dieses Issues gutgeschrieben (der
    Eval bewertet das erzeugte Ergebnis = i.d.R. die Implementierung). Nur
    dieser Call zählt in ``calls`` der ausgewählten Serie. Frühere oder nicht
    bewertbare Calls sind ``unattributed_calls``; Calls mit einer Beobachtung
    aus einer anderen Serie sind ``other_series_calls``. Das entspricht der
    Live-Attribution des ``QualityMetricsHandler``.

    ``limit`` bewusst hoch (5000): LLM-/Eval-Events sind gegenueber hoch­frequenten
    Events (HealthCheck etc.) selten; ein kleines Fenster liest sonst nur die
    juengsten Health-Checks und findet keine Korrelation (der Quality-Tab bliebe
    faelschlich leer, obwohl die Daten im Log liegen).
    """
    events = load_runtime_events(data_dir, max(limit, 100_000), projection_store)
    selected_series = _selected_quality_series(events)
    eval_by_issue: dict[int, dict] = {}
    llm_calls: list[tuple[tuple[str, str, str], int | None]] = []
    by_key: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "unattributed_calls": 0,
            "other_series_calls": 0,
            "passed": 0,
            "failed": 0,
            "score_sum": 0.0,
            "score_count": 0,
            "last_ts": "",
        }
    )
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        msg = payload.get("message_name", "")
        series = _quality_series_for_payload(payload)
        if series is not None and msg == "ScoreObserved":
            observed_passed: bool | None = None
        elif series is not None:
            observed_passed = msg == "EvalCompleted"
        else:
            observed_passed = None
        if series is not None:
            issue = payload.get("issue")
            if issue is None:
                continue
            try:
                eval_by_issue[int(issue)] = {
                    "series": series,
                    "passed": observed_passed,
                    "score": payload.get("score"),
                }
            except (TypeError, ValueError):
                continue
        elif msg == "LLMCallCompleted":
            key = (
                str(payload.get("provider", "")),
                str(payload.get("model", "")),
                str(payload.get("task", "")),
            )
            bucket = by_key[key]
            bucket["last_ts"] = evt.get("ts", "")
            issue = payload.get("issue")
            try:
                llm_calls.append((key, int(issue) if issue is not None else None))
            except (TypeError, ValueError):
                llm_calls.append((key, None))

    # Letzter LLM-Call (chronologisch) je Issue -> erhaelt genau eine Serie.
    last_call_by_issue: dict[int, int] = {}
    for index, (_, issue) in enumerate(llm_calls):
        if issue is not None:
            last_call_by_issue[issue] = index
    for index, (key, issue) in enumerate(llm_calls):
        bucket = by_key[key]
        ev = eval_by_issue.get(issue) if issue is not None else None
        if issue is None or ev is None or last_call_by_issue.get(issue) != index:
            bucket["unattributed_calls"] += 1
            continue
        if ev["series"] != selected_series:
            bucket["other_series_calls"] += 1
            continue
        bucket["calls"] += 1
        if ev["passed"] is True:
            bucket["passed"] += 1
        elif ev["passed"] is False:
            bucket["failed"] += 1
        score = ev.get("score")
        if isinstance(score, (int, float)):
            bucket["score_sum"] += float(score)
            bucket["score_count"] += 1

    rows: list[dict] = []
    for (provider, model, task), b in by_key.items():
        graded = b["passed"] + b["failed"]
        rows.append(
            {
                "provider": provider,
                "model": model,
                "task": task,
                "calls": b["calls"],
                "unattributed_calls": b["unattributed_calls"],
                "other_series_calls": b["other_series_calls"],
                "graded": graded,
                "passed": b["passed"],
                "failed": b["failed"],
                "success_rate_pct": round(b["passed"] / graded * 100) if graded else None,
                "avg_score": round(b["score_sum"] / b["score_count"], 3)
                if b["score_count"]
                else None,
                "last_ts": b["last_ts"],
                "evidence_origin": selected_series[0],
                "observation_schema": selected_series[1],
                "scoring_policy_version": selected_series[2],
                "formula_version": selected_series[3],
            }
        )
    rows.sort(key=lambda r: r["last_ts"], reverse=True)
    return rows


def build_quality_heatmap(rows: list[dict]) -> dict:
    """#153: Pivot (provider, model) x task -> avg_score fuer die Heatmap.

    Liefert ``{"tasks": [...], "rows": [{provider, model, cells: [score|None,...]}]}``
    in derselben Task-Reihenfolge wie ``tasks``."""
    tasks = sorted({r["task"] for r in rows if r.get("task")})
    models = sorted({(r["provider"], r["model"]) for r in rows})
    cell_by: dict[tuple[str, str], dict[str, Any]] = {
        (p, m): {t: None for t in tasks} for p, m in models
    }
    for r in rows:
        pm = (r["provider"], r["model"])
        if pm in cell_by and r.get("task") in cell_by[pm]:
            cell_by[pm][r["task"]] = r.get("avg_score")
    return {
        "tasks": tasks,
        "rows": [
            {"provider": p, "model": m, "cells": [cell_by[(p, m)][t] for t in tasks]}
            for p, m in models
        ],
    }


def get_quality_overview(
    data_dir: str = "data",
    min_params_b: float = 7.0,
    registry: Any = None,
    projection_store: IRunProjectionStore | None = None,
) -> dict:
    """#153: Daten fuer den Quality-Tab — Matrix + Heatmap + Param-Warnungen.

    ``registry`` (optional, ``IQualityMetricsRegistry``) liefert den persistierten,
    recency-gewichteten EWMA-Score, der den Matrix-Zeilen ueberlagert wird.
    """
    from samuel.core.quality_params import check_local_model_size

    rows = get_quality_from_log(data_dir, projection_store=projection_store)
    selected_series = _selected_quality_series(
        load_runtime_events(data_dir, 100_000, projection_store)
    )

    ewma_by_key: dict[tuple[str, str, str, str, str, str, str], Any] = {}
    if registry is not None:
        try:
            for agg in registry.aggregates():
                origin = str(agg.get("evidence_origin", "unbound_worktree"))
                schema = str(
                    agg.get("observation_schema")
                    or ("bound.v1" if origin == "bound_acceptance_evidence" else "legacy.v1")
                )
                policy = str(agg.get("scoring_policy_version", "legacy"))
                formula = str(agg.get("formula_version", "legacy"))
                ewma_by_key[
                    (agg["provider"], agg["model"], agg["task"], origin, schema, policy, formula)
                ] = agg.get("ewma_score")
        except Exception:
            log.exception("quality registry aggregates failed")
    for r in rows:
        r["ewma_score"] = ewma_by_key.get(
            (
                r["provider"],
                r["model"],
                r["task"],
                r.get("evidence_origin", "unbound_worktree"),
                r.get("observation_schema", "legacy.v1"),
                r.get("scoring_policy_version", "legacy"),
                r.get("formula_version", "legacy"),
            )
        )

    warnings: list[dict] = []
    for provider, model in sorted({(r["provider"], r["model"]) for r in rows}):
        w = check_local_model_size(provider, model, min_params_b)
        if w:
            warnings.append(w)

    return {
        "matrix": rows,
        "heatmap": build_quality_heatmap(rows),
        "selected_series": {
            "evidence_origin": selected_series[0],
            "observation_schema": selected_series[1],
            "scoring_policy_version": selected_series[2],
            "formula_version": selected_series[3],
        },
        "attribution": {
            "series_calls": sum(int(row.get("calls", 0)) for row in rows),
            "unattributed_calls": sum(int(row.get("unattributed_calls", 0)) for row in rows),
            "other_series_calls": sum(int(row.get("other_series_calls", 0)) for row in rows),
        },
        "param_warnings": warnings,
        "min_params_b": min_params_b,
    }


SCM_ACTIVITY_EVENTS: dict[str, str] = {
    "IssueOpened": "Issue geoeffnet",
    "IssueClosed": "Issue geschlossen",
    "IssueCommented": "Issue kommentiert",
    "PullRequestOpened": "PR geoeffnet",
    "PullRequestMerged": "PR gemerged",
    "PullRequestClosed": "PR geschlossen",
}


def get_scm_activity(data_dir: str = "data", limit: int = 3000) -> list[dict]:
    """#230/#390: chronologischer Stream der SCM-Activity-Events.

    Webhooks sind die Primaerquelle; das optionale Polling-Backfill verwendet
    dasselbe Schema. Jede Zeile traegt ``actor``/``actor_type`` (bot|human),
    ``source`` und den urspruenglichen SCM-Zeitpunkt.

    ``limit`` bewusst hoch: SCM-Activity-Events sind gegenueber hochfrequenten
    Events (HealthCheck etc.) selten; ein kleines Fenster verdraengt sie sonst
    schnell aus der Anzeige (analog zum Quality-Tab, #153)."""
    rows: list[dict] = []
    for evt in load_audit_events(data_dir, limit):
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        name = payload.get("message_name", "")
        label = SCM_ACTIVITY_EVENTS.get(name)
        if not label:
            continue
        rows.append(
            {
                "ts": payload.get("timestamp") or evt.get("ts", ""),
                "event": name,
                "label": label,
                "number": payload.get("number"),
                "title": payload.get("title", ""),
                "url": payload.get("url", ""),
                "actor": payload.get("actor", ""),
                "actor_type": payload.get("actor_type", "human"),
                "source": payload.get("source", "webhook"),
            }
        )
    rows.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return rows


FINDING_EVENT_NAMES = frozenset(
    {
        "GateFailed",
        "UnresolvedSymbol",
        "SecurityTripwireTriggered",
        "TamperDetected",
        "UnauthorizedChange",
        "IntegrityViolation",
    }
)


def get_finding_stats(data_dir: str = "data", limit: int = 1000) -> dict:
    """#368 Task 8: Volumen/Rate der Gate-Findings aus dem Audit-Trail.

    Liefert die Grundlage fuer das FP-Raten-Tracking: wie oft feuern die
    (teils warn-only) Findings-Events, pro Typ und ueber wie viele Issues. Eine
    echte False-Positive-Quote erfordert zusaetzlich eine Operator-Bestaetigung
    pro Finding (noch offen) — ohne diese Zahl laesst sich aber nicht
    entscheiden, ob ein Gate von ``optional`` nach ``required`` darf.
    """
    by_event: dict[str, int] = {}
    issues: set = set()
    total = 0
    for evt in load_audit_events(data_dir, limit):
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        name = payload.get("message_name", "")
        is_finding = name in FINDING_EVENT_NAMES or bool(payload.get("owasp_risk"))
        if not is_finding:
            continue
        total += 1
        by_event[name] = by_event.get(name, 0) + 1
        if payload.get("issue") is not None:
            issues.add(payload.get("issue"))
    return {
        "total": total,
        "by_event": by_event,
        "issues_with_findings": len(issues),
        "note": "Echte FP-Quote erfordert Operator-Bestaetigung pro Finding (offen).",
    }


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load %s: %s", path, exc)
        return {}


def get_api_key_status(
    config_dir: str = "config",
    *,
    balance_resolver: Callable[[str, str | None, str | None], tuple[float | None, str]]
    | None = None,
) -> list[dict]:
    """Inspect ``config/llm/providers.json`` and report per provider whether
    its API-key env-var is set and whether a URL is reachable (for local
    providers).

    Status values:
    - ``configured``: env_key is set in environment (we do NOT validate the
      value externally by default — pass a ``balance_resolver`` callable
      to enrich rows with live balance)
    - ``missing``: env_key referenced by config is not in environment
    - ``url_only``: provider needs no key, only a URL (Ollama/LMStudio)
    - ``unknown``: cannot determine

    ``balance_resolver(provider, env_key, url) -> (balance|None, note)`` is
    optional and provided by the caller (handler.py); the slice-isolation
    rule forbids data.py from importing adapters/factory directly.
    """
    providers_path = Path(config_dir) / "llm" / "providers.json"
    data = _load_json_file(providers_path)
    providers = data.get("providers", {}) if isinstance(data, dict) else {}
    rows: list[dict] = []
    import os as _os

    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        env_key = cfg.get("env_key")
        url = cfg.get("url", "")
        if env_key:
            status = "configured" if _os.environ.get(env_key) else "missing"
            note = "" if status == "configured" else f"set ${env_key} in env"
        elif url:
            status = "url_only"
            note = f"local endpoint @ {url}"
        else:
            status = "unknown"
            note = ""
        row: dict = {
            "provider": name,
            "model": cfg.get("model", ""),
            "env_key": env_key or "",
            "url": url,
            "status": status,
            "note": note,
        }
        if balance_resolver is not None:
            try:
                balance, balance_note = balance_resolver(name, env_key, url)
            except Exception as exc:  # noqa: BLE001
                log.warning("balance_resolver for %s raised: %s", name, exc)
                balance, balance_note = None, "lookup failed"
            row["balance"] = balance
            row["balance_note"] = balance_note
        rows.append(row)
    return rows


def get_llm_usage(data_dir: str = "data") -> dict[str, Any]:
    """Get LLM token usage and cost statistics."""
    from samuel.core.types import is_truncated_stop_reason

    events = load_audit_events(data_dir, 500)

    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    by_task: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    truncations: list[dict[str, Any]] = []

    for evt in events:
        payload = evt.get("payload", {})
        msg_name = payload.get("message_name", "")
        if msg_name == "LLMCallCompleted":
            total_calls += 1
            tokens = payload.get("tokens", 0) or payload.get("input_tokens", 0) + payload.get(
                "output_tokens", 0
            )
            cost = payload.get("cost", 0.0)
            task = payload.get("task", "default")
            total_tokens += tokens
            total_cost += cost
            by_task[task]["calls"] += 1
            by_task[task]["tokens"] += tokens
            by_task[task]["cost"] += cost
            if is_truncated_stop_reason(payload.get("stop_reason")):
                truncations.append(
                    {
                        "timestamp": evt.get("ts", evt.get("timestamp", "")),
                        "task": task,
                        "provider": payload.get("provider", ""),
                        "model": payload.get("model", ""),
                        "issue": payload.get("issue"),
                        "stop_reason": payload.get("stop_reason", ""),
                        "content_max_tokens": payload.get("content_max_tokens"),
                        "reasoning_reserve": payload.get("reasoning_reserve", 0),
                    }
                )

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "by_task": dict(by_task),
        "truncations": truncations[-20:],
    }


def get_branches() -> list[dict]:
    """Get git branch overview."""
    branches = []
    try:
        result = subprocess.run(
            [
                "git",
                "branch",
                "--format=%(refname:short) %(upstream:trackshort) %(committerdate:relative)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.strip().split(" ", 2)
                if parts and parts[0] and parts[0] != "main":
                    branches.append(
                        {
                            "name": parts[0],
                            "track": parts[1] if len(parts) > 1 else "",
                            "age": parts[2] if len(parts) > 2 else "",
                        }
                    )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return branches


KNOWN_FEATURE_FLAGS: list[tuple[str, str, bool]] = [
    ("eval", "Evaluation nach jedem Implement", True),
    ("watch", "Watch-Modus (Polling)", True),
    ("healing", "Self-Healing bei Eval-Fail", False),
    ("auto_issues", "Automatische Issue-Erstellung", False),
    ("changelog", "Changelog-Generierung", False),
    ("auto_implement_llm", "Auto-Implement via LLM", True),
    ("auto_merge_pr", "Auto-Merge nach gebundenem Review", False),
    (
        "expected_head_merge_qualified",
        "Native Expected-Head-Mergebedingung real qualifiziert",
        False,
    ),
    ("hallucination_guard", "Hallucination-Guard", True),
    ("sequence_validator", "Sequence-Validator", True),
    ("scope_guard", "Scope-Guard", True),
    ("acceptance_check", "AC-Verifikation", True),
    # #270: ``llm_attribution`` wird NICHT hier als generischer Toggle gefuehrt,
    # sondern im Compliance-Tab mit vollem Kontext (high_risk-Sperre,
    # Art.-50-Warnung, Verbosity) — sonst zwei konkurrierende Schalter fuer
    # dieselbe Einstellung.
    ("health_checks", "Health-Checks bei Start", True),
    (
        "scm_activity_polling",
        "SCM-Activity-Backfill als Webhook-Sicherheitsnetz",
        False,
    ),
]


def get_feature_flags(config: IConfig | None) -> list[dict]:
    """Get all feature flags with current state."""
    flags = []
    for key, desc, default in KNOWN_FEATURE_FLAGS:
        flags.append(
            {
                "key": key,
                "enabled": config.feature_flag(key) if config else default,
                "description": desc,
            }
        )
    return flags


# #225: kanonische Long-Form fuer alle Tasks. Tote Namen (pr_review, issue_analysis,
# log_analysis, docs, deep_coding, test_generation) entfernt — wurden nirgends gerufen.
LLM_TASK_NAMES: list[str] = [
    "planning",
    "implementation",
    "review",
    "healing",
    "evaluation",
]

_TASK_REASONING_RECOMMENDATIONS = {
    "planning": (
        "Provider-Default beibehalten, bis reale Planning-Truncations oder gemessene "
        "Reasoning-Nutzung ein explizites Budget begründen."
    ),
    "implementation": (
        "Sichtbaren Code priorisieren; eine explizite Reserve erst anhand wiederholter "
        "Truncations und Reasoning-Telemetrie setzen."
    ),
    "review": (
        "Provider-Default ist der kostenbewusste Startpunkt; für komplexe Reviews anhand "
        "der Laufzeitdaten gezielt nachschärfen."
    ),
    "healing": (
        "Nur bei nachweislich komplexen Reparaturschleifen explizit erhöhen; Content-Budget "
        "für den vollständigen Patch erhalten."
    ),
    "evaluation": (
        "Provider-Default nutzen; Bewertungsantworten sind meist kurz und profitieren nicht "
        "automatisch von einem großen festen Puffer."
    ),
}


def _reasoning_budget_guidance(
    *,
    task: str,
    provider: str,
    content_max_tokens: Any,
    reserve: Any,
    reserve_source: str,
    reasoning: dict[str, Any],
) -> dict[str, Any]:
    try:
        content = int(content_max_tokens) if content_max_tokens is not None else None
    except (TypeError, ValueError):
        content = None
    try:
        numeric_reserve = max(0, int(reserve or 0))
    except (TypeError, ValueError):
        numeric_reserve = 0
    is_reasoning = bool(reasoning.get("is_reasoning"))
    source = str(reasoning.get("source", "unknown"))
    raw_metadata = reasoning.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_supported = reasoning.get("supported_parameters")
    supported: list[Any] = raw_supported if isinstance(raw_supported, list) else []
    max_completion = int(reasoning.get("max_completion_tokens", 0) or 0)
    effective = content + numeric_reserve if content is not None else None

    if not is_reasoning:
        mode = "not_reasoning"
        semantics = "Das Modell ist laut verfügbarer Erkennung kein Reasoning-Modell."
        validation = "ignored" if numeric_reserve else "not_applicable"
    elif numeric_reserve == 0:
        mode = "provider_default"
        semantics = (
            "0 bedeutet: keine explizite Reserve. Reasoning ist nicht deaktiviert; "
            "Modell und Provider verwenden ihren Default innerhalb des Output-Budgets."
        )
        validation = "refresh_required" if "heuristic" in source else "ok"
    elif provider != "openrouter":
        mode = "unsupported_provider"
        semantics = (
            "Die numerische Reserve wird nur für OpenRouter explizit gesteuert und bei "
            "diesem Provider nicht angewendet."
        )
        validation = "unsupported_provider"
    else:
        mode = "explicit_max_tokens"
        semantics = (
            f"Explizite Task-Reserve {numeric_reserve}; Content {content if content is not None else '?'}; "
            f"effektives Output-Limit {effective if effective is not None else '?'}."
        )
        if "heuristic" in source:
            validation = "refresh_required"
        elif max_completion and effective is not None and effective > max_completion:
            validation = "exceeds_model_limit"
        else:
            validation = "ok"

    return {
        "mode": mode,
        "semantics": semantics,
        "validation": validation,
        "configuration_source": reserve_source,
        "content_max_tokens": content,
        "reasoning_reserve": numeric_reserve,
        "effective_max_tokens": effective,
        "max_completion_tokens": max_completion or None,
        "supported_efforts": metadata.get("supported_efforts"),
        "default_effort": metadata.get("default_effort"),
        "default_enabled": metadata.get("default_enabled"),
        "mandatory": bool(metadata.get("mandatory", False)),
        "supports_max_tokens": bool(metadata.get("supports_max_tokens"))
        or "reasoning" in supported,
        "recommendation": _TASK_REASONING_RECOMMENDATIONS.get(
            task,
            "Provider-Default verwenden und erst anhand realer Laufzeitdaten explizit steuern.",
        ),
    }


def get_llm_routing(
    config: IConfig | None,
    config_dir: str = "config",
    prompt_source_resolver: Callable[
        [str, str, str | None, str | None, dict | None],
        dict[str, Any],
    ]
    | None = None,
    model_quality_resolver: Callable[[str, str, float, float], dict[str, Any]] | None = None,
) -> list[dict]:
    """Return provider/model per task with max_tokens/temperature/timeout.

    Resolves per task in this order:
    - provider/model: ``config/llm/defaults.json::tasks.<task>`` → legacy
      ``llm.tasks.<task>`` → provider-specific model → ``llm.default.*``
    - max_tokens/temperature: ``config/llm/defaults.json::tasks.<task>.*``
      → ``config/llm/defaults.json::default.*``
    - timeout: ``llm.default.timeout`` (no per-task override today)

    The ``defaults.json`` sub-config is loaded directly because FileConfig
    only globs the top-level ``config/`` directory.

    ``prompt_source_resolver`` (#348): optional callable
    ``(name, config_dir, provider, model) -> {"source", "path", "mtime"}``
    injected from the wiring layer (server.py) — slice-iso forbids the
    direct ``samuel.adapters.llm.prompts`` import here. Without it, rows
    still carry ``system_prompt_source`` but report ``source="none"``.
    """
    if config is None:
        return [
            {
                "task": "default",
                "provider": "-",
                "model": "-",
                "max_tokens": None,
                "temperature": None,
                "timeout": None,
                "reasoning_reserve": 0,
                "model_quality": {},
            }
        ]

    default_provider = config.get("llm.default.provider", "-")
    default_model = config.get("llm.default.model", "-")
    if default_model == "-" and default_provider != "-":
        default_model = config.get(f"llm.{default_provider}.model", "-")

    defaults = _load_json_file(Path(config_dir) / "llm" / "defaults.json")
    base_default = defaults.get("default", {}) if isinstance(defaults, dict) else {}
    task_overrides = defaults.get("tasks", {}) if isinstance(defaults, dict) else {}
    base_max_tokens = base_default.get("max_tokens")
    base_temperature = base_default.get("temperature")
    base_timeout = base_default.get("timeout")
    base_reasoning_reserve = base_default.get("reasoning_reserve", 0)
    raw_thresholds = defaults.get("benchmark_thresholds", {}) if isinstance(defaults, dict) else {}
    thresholds = raw_thresholds if isinstance(raw_thresholds, dict) else {}
    default_threshold = float(thresholds.get("default", 50.0))

    def _row(task: str) -> dict[str, Any]:
        raw_task_cfg = task_overrides.get(task, {}) if isinstance(task_overrides, dict) else {}
        task_cfg = raw_task_cfg if isinstance(raw_task_cfg, dict) else {}
        # #419: defaults.json is the runtime source used by the factory and by
        # the dashboard save endpoint. Reading provider/model from FileConfig
        # first made a successful save appear to revert to the bootstrap
        # default on the next refresh.
        prov = (
            task_cfg.get("provider") or config.get(f"llm.tasks.{task}.provider") or default_provider
        )
        mdl = task_cfg.get("model") or config.get(f"llm.tasks.{task}.model")
        if not mdl and prov != "-":
            mdl = config.get(f"llm.{prov}.model")
        mdl = mdl or default_model
        sp_name = task_cfg.get("system_prompt", "")
        # #351: per-provider override map round-trips so the editor can
        # render the "+ per-provider" section.
        sp_by_provider = task_cfg.get("system_prompt_by_provider") or {}
        # #348/#351: which cascade-stage actually delivers this prompt for
        # the active provider? The resolver consults the by_provider map
        # first, then falls through to the cascade for the resolved name.
        has_active_prompt = bool(sp_name) or (
            isinstance(sp_by_provider, dict) and prov in sp_by_provider
        )
        if has_active_prompt and prompt_source_resolver:
            sp_source = prompt_source_resolver(
                sp_name,
                config_dir,
                prov,
                mdl,
                sp_by_provider,
            )
        else:
            sp_source = {"source": "none", "path": "", "mtime": 0.0}
        threshold = float(thresholds.get(task, default_threshold))
        margin_ratio = float(task_cfg.get("overqualification_margin_ratio", 0.2))
        advisory_enabled = bool(task_cfg.get("cost_advisory_enabled", True))
        model_quality = (
            model_quality_resolver(str(mdl), task, threshold, margin_ratio)
            if model_quality_resolver and mdl
            else {}
        )
        reserve_source = "task_override" if "reasoning_reserve" in task_cfg else "inherited_default"
        reserve = task_cfg.get("reasoning_reserve", base_reasoning_reserve)
        reasoning = model_quality.get("reasoning", {}) if isinstance(model_quality, dict) else {}
        # All persisted task fields must round-trip through this view, otherwise
        # the LLM-Editor reload appears to "lose" the saved value (#338-audit:
        # `system_prompt` was missing from the row, so the dropdown rendered
        # empty after reload even though the JSON still held the override).
        return {
            "task": task,
            "provider": prov,
            "model": mdl,
            "base_url": task_cfg.get("base_url", ""),
            "max_tokens": task_cfg.get("max_tokens", base_max_tokens),
            "temperature": task_cfg.get("temperature", base_temperature),
            "timeout": task_cfg.get("timeout", base_timeout),
            "reasoning_reserve": reserve,
            "reasoning_guidance": _reasoning_budget_guidance(
                task=task,
                provider=str(prov),
                content_max_tokens=task_cfg.get("max_tokens", base_max_tokens),
                reserve=reserve,
                reserve_source=reserve_source,
                reasoning=reasoning if isinstance(reasoning, dict) else {},
            ),
            "model_quality": model_quality,
            "cost_advisory_enabled": advisory_enabled,
            "overqualification_margin_ratio": margin_ratio,
            "system_prompt": sp_name,
            "system_prompt_source": sp_source,
            "system_prompt_by_provider": sp_by_provider,
            "schedule": task_cfg.get("schedule") or {},
        }

    # Take the union of LLM_TASK_NAMES and tasks present in defaults.json
    seen: dict[str, dict[str, Any]] = {}
    for task in LLM_TASK_NAMES:
        if (
            config.get(f"llm.tasks.{task}.provider") is not None
            or config.get(f"llm.tasks.{task}.model") is not None
            or task in task_overrides
        ):
            seen[task] = _row(task)
    for task in task_overrides:
        if task not in seen:
            seen[task] = _row(task)

    if not seen:
        return [
            {
                "task": "default",
                "provider": default_provider,
                "model": default_model,
                "max_tokens": base_max_tokens,
                "temperature": base_temperature,
                "timeout": base_timeout,
                "reasoning_reserve": base_reasoning_reserve,
                "model_quality": (
                    model_quality_resolver(str(default_model), "default", default_threshold, 0.2)
                    if model_quality_resolver and default_model
                    else {}
                ),
                "cost_advisory_enabled": True,
                "overqualification_margin_ratio": 0.2,
            }
        ]
    return list(seen.values())


def get_llm_routing_schedule(config: IConfig | None, config_dir: str = "config") -> dict[str, Any]:
    """#302: Return per-task schedule blocks with current active state.

    Reads ``config/llm/defaults.json:tasks..schedule``. Valid configured
    schedules are part of the general routing path and need no entitlement.
    """
    from samuel.core.schedule import schedule_active as _schedule_active

    defaults_path = Path(config_dir) / "llm" / "defaults.json"
    tasks_cfg: dict = {}
    if defaults_path.is_file():
        try:
            tasks_cfg = json.loads(defaults_path.read_text(encoding="utf-8")).get("tasks") or {}
        except Exception as exc:
            log.warning("Failed to parse %s: %s", defaults_path, exc)

    rows = []
    for task_name, cfg in tasks_cfg.items():
        if not isinstance(cfg, dict):
            continue
        sched = cfg.get("schedule")
        if not isinstance(sched, dict):
            continue
        rows.append(
            {
                "task": task_name,
                "day_provider": cfg.get("provider", "-"),
                "day_model": cfg.get("model", "-"),
                "night_provider": sched.get("provider", "-"),
                "night_model": sched.get("model", "-"),
                "from": sched.get("from", "-"),
                "to": sched.get("to", "-"),
                "active_now": _schedule_active(sched),
            }
        )

    return {
        # Kept for API compatibility: the general feature is always available.
        "feature_available": True,
        "configured": bool(rows),
        "enabled": bool(rows),
        "active_now": any(row["active_now"] for row in rows),
        "tasks": rows,
        "night_hours": "config-driven (per task)",
    }


_TAMPER_MSG_NAMES: set[str] = {
    "TamperDetected",
    "UnauthorizedChange",
    "IntegrityViolation",
}


def get_tamper_events(data_dir: str = "data", limit: int = 20) -> list[dict]:
    """Return tamper / integrity / supply-chain events.

    Includes payload message_name in {TamperDetected, UnauthorizedChange,
    IntegrityViolation} OR owasp_risk in the agentic-supply-chain family
    (#290: ``agentic_supply_chain`` ASI04, plus legacy
    ``broken_trust_boundaries`` from pre-#290 audit logs).
    Newest first, capped at ``limit``.
    """
    events = load_audit_events(data_dir, 500)
    matches: list[dict] = []
    for evt in events:
        payload = evt.get("payload", {}) or {}
        msg_name = payload.get("message_name", "")
        owasp = str(payload.get("owasp_risk", "")).lower()
        is_supply_chain = (
            "agentic_supply_chain" in owasp or "broken_trust_boundaries" in owasp  # #290: legacy
        )
        if msg_name in _TAMPER_MSG_NAMES or is_supply_chain:
            category = _classify_category(evt)
            reason = str(payload.get("reason", "") or payload.get("detail", ""))
            description = describe_diagnostic(
                logger=str(payload.get("logger", "")),
                reason=reason,
                category=category,
                event_name=str(msg_name),
            )
            if msg_name == "TamperDetected":
                classification = "external_signature"
                summary = "Externe Signatur-/Webhook-Prüfung fehlgeschlagen"
                default_component = "webhook"
            elif msg_name == "IntegrityViolation":
                classification = "internal_integrity"
                summary = "Interne Integritätsprüfung fehlgeschlagen"
                default_component = "audit_chain"
            elif msg_name == "UnauthorizedChange":
                classification = "unauthorized_change"
                summary = "Nicht autorisierte Änderung erkannt"
                default_component = "policy"
            else:
                classification = "other_supply_chain"
                summary = "Sonstiges Supply-Chain-Sicherheitsereignis"
                default_component = "unknown"
            matches.append(
                {
                    "ts": evt.get("ts", ""),
                    "event": msg_name or evt.get("name", ""),
                    "level": _classify_level(evt),
                    "classification": classification,
                    "summary": summary,
                    "owasp": payload.get("owasp_risk", ""),
                    "detail": reason,
                    "source": payload.get("source") or payload.get("mode") or "runtime",
                    "component": payload.get("component")
                    or payload.get("logger")
                    or default_component,
                    "impact": payload.get("impact") or description["impact"],
                    "correlation_id": payload.get("correlation_id", ""),
                    "run": payload.get("run_id") or payload.get("correlation_id", ""),
                    "issue": payload.get("issue", ""),
                    "remediation": payload.get("next_steps") or description["next_steps"],
                }
            )
    matches.reverse()
    return matches[:limit]


def _classify_level(evt: dict) -> str:
    payload = evt.get("payload", {})
    name = payload.get("message_name", "")
    for baseline, names in _ANOMALY_LEVEL_EVENTS.items():
        if name in names:
            return baseline
    explicit = str(payload.get("level") or payload.get("lvl") or "").lower()
    if explicit in {"error", "critical", "fatal"}:
        return "error"
    if explicit in {"warn", "warning"}:
        return "warn"
    if explicit in {"debug", "info"}:
        return explicit
    if name == "StartupBlocked":
        return "error"
    if name in ("ACFailed", "ACManualPending", "UnresolvedSymbol", "PlanComplexityWarn"):
        return "warn"
    return "info"


def _classify_category(evt: dict) -> str:
    payload = evt.get("payload", {})
    explicit = payload.get("category") or payload.get("cat")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    name = payload.get("message_name", "")
    categories = {
        "PlanCreated": "workflow",
        "PlanValidated": "workflow",
        "PlanBlocked": "workflow",
        "PlanReplanRejected": "workflow",
        "PlanRevoked": "workflow",
        "ClarificationRequested": "workflow",
        "ClarificationWaiting": "workflow",
        "ClarificationAccepted": "workflow",
        "ClarificationSuperseded": "workflow",
        "CodeGenerated": "workflow",
        "PRCreated": "workflow",
        "ReviewCompleted": "workflow",
        "ReviewBlocked": "workflow",
        "MergeOutcomeUnknown": "scm",
        "PRCreationFailed": "scm",
        "EvaluationSubjectInvalidated": "gates",
        "IssueReady": "workflow",
        "GateFailed": "gates",
        "GatesPassed": "gates",
        "SecurityTripwireTriggered": "security",
        "LLMCallCompleted": "llm",
        "LLMUnavailable": "llm",
        "WorkflowBudgetAdmitted": "llm",
        "LLMBudgetAttemptReserved": "llm",
        "LLMBudgetAttemptSettled": "llm",
        "LLMBudgetBlocked": "llm",
        "EvalCompleted": "eval",
        "EvalFailed": "eval",
        "TestRunCompleted": "eval",
        "ACVerified": "eval",
        "ACFailed": "eval",
        "ACManualPending": "eval",
        "PlanContextLoaded": "context",
        "PlanPreCheckCompleted": "guard",
        "PlanComplexityWarn": "plan",
        # #239: Healing-Loop-Events
        "HealingSuggested": "workflow",
        "HealingAttemptStarted": "workflow",
        "HealingAttemptCompleted": "workflow",
        "HealingAborted": "workflow",
        "HealthCheck": "system",
        "ConfigReloaded": "config",
        "ConfigChanged": "config",
        # #208: Tamper-/Integritaets-Events
        "TamperDetected": "security",
        "UnauthorizedChange": "security",
        "IntegrityViolation": "security",
        # #247: Scope-/Out-of-Scope-Waechter
        "ScopeCreepDetected": "plan",
        "OutOfScopeDiff": "guard",
        "HealingFailed": "workflow",
        "QualityFailed": "quality",
        "QualityPassed": "quality",
        "QualityCheckCompleted": "quality",
        # #230: SCM-Activity (Webhook) — cat scm -> AI-Act Art. 12 (Logging)
        "IssueOpened": "scm",
        "IssueClosed": "scm",
        "IssueCommented": "scm",
        "PullRequestOpened": "scm",
        "PullRequestMerged": "scm",
        "PullRequestClosed": "scm",
        # #368: Dependency-/Symbol-Tracking
        "LockfileChanged": "scm",
        "UnresolvedSymbol": "guard",
        "WorkflowAborted": "workflow",
        "WorkflowBlocked": "workflow",
        "DiagnosticRaised": "system",
    }
    return categories.get(name, "system")


def _build_message(evt: dict) -> str:
    raw_payload = evt.get("payload", {})
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    name = payload.get("message_name", "")
    reason = payload.get("reason", "")
    if reason:
        return f"{name}: {reason}"
    return str(name)
