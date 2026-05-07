"""Dashboard data aggregation layer."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from samuel.core.ai_act import classify as _classify_ai_act
from samuel.core.owasp import classify as _classify_owasp

# #211: API-key validation cache — 5min TTL, in-memory, single-process.
_VALIDATION_CACHE: dict[str, tuple[float, dict]] = {}
_VALIDATION_TTL_SECONDS = 300


def _cached_validate(provider_name: str, adapter) -> dict:
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
            result = adapter.validate()
        except Exception as exc:  # noqa: BLE001
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


# Gate-ID → human-readable name. Mirrors GATE_REGISTRY in
# samuel/slices/pr_gates/gates.py — slice isolation forbids importing
# from another slice, so this small lookup is duplicated. Keep in sync.
_GATE_NAMES: dict[int | str, str] = {
    1: "BranchGuard",
    2: "PlanComment",
    3: "MetadataBlock",
    4: "EvalTimestamp",
    5: "DiffNotEmpty",
    6: "SelfConsistency",
    7: "ScopeGuard",
    8: "SliceGate",
    9: "QualityPipeline",
    10: "EvalScore",
    11: "ACVerification",
    12: "ReadyToClose",
    "13a": "BranchFreshness",
    "13b": "DestructiveDiff",
}


def _gate_label(gate_id: Any, fallback: str = "") -> str:
    """Return ``GATE_NAMES[gate_id]`` if present, else stringified id (or
    fallback when id is empty)."""
    if gate_id in _GATE_NAMES:
        return _GATE_NAMES[gate_id]
    if gate_id is None or gate_id == "":
        return fallback
    return str(gate_id)


_BARRIER_MSG_NAMES: set[str] = {"GateFailed", "SecurityTripwireTriggered", "WorkflowAborted"}


# Maps OWASP risk-NAME (as returned by classify(cat, evt)) to OWASP-Top-10 A-ID
# used in the Security tab. payload.owasp_risk values like "A05:2021" already
# have the A-prefix; classify-derived names need this lookup.
_OWASP_NAME_TO_ID: dict[str, str] = {
    "unrestricted_agency":      "A01",
    "uncontrolled_behavior":    "A02",
    "inadequate_sandboxing":    "A03",
    "broken_trust_boundaries":  "A04",
    "identity_access_abuse":    "A05",
    "unmonitored_activities":   "A06",
    "unsafe_tool_integration":  "A07",
    "excessive_autonomy":       "A08",
    "inadequate_feedback_loops": "A09",
    "opaque_reasoning":         "A10",
}


def get_security_overview(data_dir: str = "data") -> dict[str, Any]:
    """OWASP Agentic AI risk overview from audit events.

    The returned ``owasp`` list contains, per risk id, a ``recent`` array of
    up to 5 events ``{timestamp, event, message, issue}`` so the UI can show
    what specifically triggered each risk classification.
    """
    events = load_audit_events(data_dir, 500)

    owasp_risks: dict[str, dict[str, Any]] = {
        "A01": {"name": "Unrestricted Agency", "events": 0, "last": "", "recent": []},
        "A02": {"name": "Uncontrolled Agentic Behavior", "events": 0, "last": "", "recent": []},
        "A03": {"name": "Inadequate Sandboxing", "events": 0, "last": "", "recent": []},
        "A04": {"name": "Broken Trust Boundaries", "events": 0, "last": "", "recent": []},
        "A05": {"name": "Identity & Access Abuse", "events": 0, "last": "", "recent": []},
        "A06": {"name": "Unmonitored Agent Activities", "events": 0, "last": "", "recent": []},
        "A07": {"name": "Unsafe Tool/API Integration", "events": 0, "last": "", "recent": []},
        "A08": {"name": "Excessive Autonomy", "events": 0, "last": "", "recent": []},
        "A09": {"name": "Inadequate Feedback Loops", "events": 0, "last": "", "recent": []},
        "A10": {"name": "Opaque Agent Reasoning", "events": 0, "last": "", "recent": []},
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
            if ":" in owasp:
                risk_key = owasp.split(":")[0]
            else:
                risk_key = _OWASP_NAME_TO_ID.get(owasp, owasp)
            if risk_key in owasp_risks:
                owasp_risks[risk_key]["events"] += 1
                owasp_risks[risk_key]["last"] = evt.get("ts", "")
                owasp_risks[risk_key]["recent"].append({
                    "timestamp": evt.get("ts", ""),
                    "event": payload.get("message_name", ""),
                    "message": _build_message(evt),
                    "issue": payload.get("issue", ""),
                })

        msg_name = payload.get("message_name", "")
        if msg_name in _BARRIER_MSG_NAMES:
            gate_id = payload.get("gate")
            barriers.append({
                "timestamp": evt.get("ts", ""),
                "issue": payload.get("issue", ""),
                "event": _gate_label(gate_id, fallback=msg_name),
                "step": str(payload.get("step", "")),
                "action": "blocked" if msg_name == "GateFailed" else "warn",
                "owasp": owasp,
                "detail": payload.get("reason", ""),
            })

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


def get_compliance_legend() -> dict[str, list[dict]]:
    """Compliance-Legend für Audit-Tab/Compliance-Tab (#252).

    Liefert OWASP Top-10 Agentic AI + EU AI Act Artikel mit Beschreibungen.
    Operator kann damit Codes wie ``A05`` oder ``Art. 14`` im Audit-Trail
    direkt nachschlagen statt extern recherchieren zu müssen.

    Returns:
        ``{"owasp": [{id, name, key, description}, ...],
           "ai_act": [{article, description}, ...]}``
    """
    from samuel.core.ai_act import AI_ACT_ARTICLES
    from samuel.core.owasp import OWASP_TOP10

    return {
        "owasp": [dict(entry) for entry in OWASP_TOP10],
        "ai_act": [dict(entry) for entry in AI_ACT_ARTICLES],
    }


def get_workflow_issues(data_dir: str = "data") -> list[dict]:
    """Get issue processing status from audit events.

    Per issue the row carries (#277):
    - ``runs_count``: number of distinct ``correlation_id`` runs seen
    - ``trend``: one of ``recovered``/``regressed``/``passed``/``failed``/``""``
    """
    events = load_audit_events(data_dir, 500)
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
            }
            corr_ids_by_issue[issue_num] = set()

        msg_name = payload.get("message_name", "")
        issues[issue_num]["events"].append({
            "name": msg_name,
            "ts": evt.get("ts", ""),
            "detail": payload.get("reason", ""),
        })
        issues[issue_num]["last_event"] = msg_name
        issues[issue_num]["timestamp"] = evt.get("ts", "")

        corr = str(payload.get("correlation_id") or "")
        if corr:
            corr_ids_by_issue[issue_num].add(corr)

        # Determine status from event
        if msg_name == "PRCreated":
            issues[issue_num]["status"] = "pr_created"
        elif msg_name in ("WorkflowBlocked", "WorkflowAborted", "GateFailed"):
            issues[issue_num]["status"] = "blocked"
        elif msg_name == "CodeGenerated":
            issues[issue_num]["status"] = "implemented"
        elif msg_name == "PlanCreated":
            issues[issue_num]["status"] = "planned"
        elif msg_name == "IssueReady":
            issues[issue_num]["status"] = "ready"

    for num, corr_ids in corr_ids_by_issue.items():
        issues[num]["runs_count"] = len(corr_ids)
        if len(corr_ids) >= 2:
            # Re-derive trend from the runs aggregator so failed -> passed
            # transitions land in the issue list, not just in the detail
            # view (#277).
            runs = get_workflow_runs(num, data_dir)
            issues[num]["trend"] = _classify_workflow_trend(runs)

    return sorted(issues.values(), key=lambda x: x.get("timestamp", ""), reverse=True)[:30]


_PIPELINE_STAGE_EVENTS: dict[str, set[str]] = {
    # #258: jede Stage hat sowohl Pass- als auch Fail-Events. Vorher zeigten
    # gates/quality "pending" für erfolgreiche Runs weil nur Failure-Events
    # gemappt waren.
    # #238: PlanPreCheckCompleted/PlanComplexityWarn ebenfalls Plan-Stage.
    "plan": {"PlanCreated", "PlanValidated", "PlanBlocked",
             "PlanPreCheckCompleted", "PlanComplexityWarn"},
    "implement": {"CodeGenerated", "Implement", "ImplementationFailed", "PRCreated"},
    "llm": {"LLMCallCompleted", "LLMUnavailable", "TokenLimitHit"},
    "gates": {"GatesPassed", "GateFailed", "SecurityTripwireTriggered"},
    "eval": {"Evaluate", "EvalCompleted", "EvalFailed"},
    "quality": {"QualityPassed", "QualityFailed"},
    # #239: Healing-Stage zwischen quality und pr
    "healing": {"HealingAttemptStarted", "HealingAttemptCompleted",
                "HealingSuggested", "HealingAborted"},
    "pr": {"CreatePR", "PRCreated"},
    # #258: kein ReviewCompleted-Event existiert heute; PRCreated implies
    # Review-Stage als done. ReviewBlocked wäre ein expliziter Fehler-Pfad
    # (heute auch nicht publisht, aber für zukünftige Erweiterung beibehalten).
    "review": {"ReviewCompleted", "ReviewBlocked", "PRCreated"},
}

_STAGE_FAIL_EVENTS: set[str] = {
    "PlanBlocked", "ImplementationFailed", "LLMUnavailable", "TokenLimitHit",
    "GateFailed", "SecurityTripwireTriggered", "EvalFailed", "QualityFailed",
    "ReviewBlocked", "WorkflowAborted", "WorkflowBlocked",
    # #239: HealingAborted markiert healing-stage als failed
    "HealingAborted",
}


def get_workflow_issue_detail(
    issue_num: int, data_dir: str = "data", limit: int = 1000
) -> dict[str, Any] | None:
    """Detailed view for a single issue: audit trail, pipeline stages, score, LLM.

    Returns ``None`` if no events for this issue. Otherwise a dict with:
    - ``number``: the issue number
    - ``status``: overall status (mirrors get_workflow_issues)
    - ``branch``: last branch name seen in any event
    - ``events``: up to 30 audit events for this issue (newest last) with
      timestamp/level/category/event/message/owasp/gate/action
    - ``stages``: per-stage summary dict (plan/implement/llm/gates/eval/
      quality/pr/review): ``{status: 'done'|'failed'|'pending', last_ts,
      count, fail_count}``
    - ``score``: latest Evaluate/EvalCompleted aggregate (value, baseline,
      passed, checks_passed, checks_total, last_ts, reason)
    - ``llm``: aggregated LLMCallCompleted (calls, tokens, cost, by_provider,
      by_task)
    """
    events = load_audit_events(data_dir, limit)
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
        trail.append({
            "timestamp": ts,
            "level": _classify_level(evt),
            "category": cat,
            "event": name,
            "message": _build_message(evt),
            "owasp": payload.get("owasp_risk") or _classify_owasp(cat, evt_key) or "",
            "ai_act": _classify_ai_act(cat, evt_key) or "",
            "gate": payload.get("gate", ""),
            "reason": payload.get("reason", ""),
        })

    # --- pipeline stages ---
    stages: dict[str, dict[str, Any]] = {}
    for stage, names in _PIPELINE_STAGE_EVENTS.items():
        matched = [(ts, name, p) for ts, name, p, _ in issue_events if name in names]
        if not matched:
            stages[stage] = {"status": "pending", "last_ts": "", "count": 0, "fail_count": 0}
            continue
        fail = sum(1 for _, n, _ in matched if n in _STAGE_FAIL_EVENTS)
        last_ts, last_name, _ = matched[-1]
        status = "failed" if last_name in _STAGE_FAIL_EVENTS else "done"
        stages[stage] = {
            "status": status,
            "last_ts": last_ts,
            "count": len(matched),
            "fail_count": fail,
        }

    # --- overall status (same logic as get_workflow_issues) ---
    overall_status = "unknown"
    last_branch = ""
    for ts, name, payload, _ in issue_events:
        if payload.get("branch"):
            last_branch = str(payload["branch"])
        if name == "PRCreated":
            overall_status = "pr_created"
        elif name in ("WorkflowBlocked", "WorkflowAborted", "GateFailed"):
            overall_status = "blocked"
        elif name == "CodeGenerated" and overall_status not in ("pr_created",):
            overall_status = "implemented"
        elif name == "PlanCreated" and overall_status == "unknown":
            overall_status = "planned"
        elif name == "IssueReady" and overall_status == "unknown":
            overall_status = "ready"

    # --- score (latest Evaluate / EvalCompleted / EvalFailed) ---
    score: dict[str, Any] = {"value": None, "baseline": None, "passed": None,
                             "checks_passed": None, "checks_total": None,
                             "last_ts": "", "reason": ""}
    for ts, name, payload, _ in issue_events:
        if name in ("Evaluate", "EvalCompleted", "EvalFailed"):
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
    by_task: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "tokens": 0, "cost": 0.0}
    )
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
        calls_detail.append({
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
        })

    # --- TEST runs aggregation (TestRunCompleted events for this issue) ---
    test_runs: list[dict[str, Any]] = []
    for ts, name, payload, _ in issue_events:
        if name != "TestRunCompleted":
            continue
        test_runs.append({
            "timestamp": ts,
            "test_name": str(payload.get("test_name", "")),
            "runner": str(payload.get("runner", "unknown")),
            "passed": bool(payload.get("passed", False)),
            "exit_code": payload.get("exit_code"),
            "duration_ms": payload.get("duration_ms"),
        })

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
            healing["attempts"].append({
                "timestamp":  ts,
                "n":          int(payload.get("attempt", 0) or 0),
                "prev_score": payload.get("prev_score"),
                "new_score":  payload.get("new_score"),
                "delta":      payload.get("score_delta"),
                "tokens":     int(payload.get("tokens_used", 0) or 0),
                "status":     str(payload.get("status", "")),
            })
            healing["total_tokens"] += int(payload.get("tokens_used", 0) or 0)
        elif name == "HealingAborted":
            healing["why_stopped"] = str(payload.get("reason", ""))

    # --- Plan-Pre-Check + Complexity (#238) ---
    pre_check: dict[str, Any] = {}
    complexity: dict[str, Any] = {}
    for ts, name, payload, _ in issue_events:
        if name == "PlanPreCheckCompleted":
            pre_check = {
                "timestamp":         ts,
                "structural":        payload.get("structural_score"),
                "skeleton":          payload.get("skeleton_score"),
                "ac_dry_run":        payload.get("ac_dry_run_score"),
                "overall_pass":      bool(payload.get("overall_pass", False)),
                "retry_attempt":     int(payload.get("retry_attempt", 0) or 0),
                "blocking_failures": list(payload.get("blocking_failures") or []),
            }
            cx = payload.get("complexity")
            if isinstance(cx, dict):
                complexity = {
                    "ac_count":              int(cx.get("ac_count", 0) or 0),
                    "file_count":            int(cx.get("file_count", 0) or 0),
                    "slice_count":           int(cx.get("slice_count", 0) or 0),
                    "pflicht_bereich_count": int(cx.get("pflicht_bereich_count", 0) or 0),
                    "recommendation":        str(cx.get("recommendation", "ok")),
                }
        elif name == "PlanComplexityWarn":
            complexity = {
                "ac_count":              int(payload.get("ac_count", 0) or 0),
                "file_count":            int(payload.get("file_count", 0) or 0),
                "slice_count":           int(payload.get("slice_count", 0) or 0),
                "pflicht_bereich_count": int(payload.get("pflicht_bereich_count", 0) or 0),
                "recommendation":        str(payload.get("recommendation", "ok")),
            }

    # --- AC-Verifications aggregation (ACVerified/ACFailed for this issue) ---
    # #236: pro AC ein Eintrag mit tag/arg/passed/reason für Dashboard.
    acceptance_checks: list[dict[str, Any]] = []
    for ts, name, payload, _ in issue_events:
        if name not in ("ACVerified", "ACFailed"):
            continue
        acceptance_checks.append({
            "timestamp": ts,
            "tag": str(payload.get("tag", "")),
            "arg": str(payload.get("arg", "")),
            "passed": bool(payload.get("passed", False)),
            "reason": str(payload.get("reason", "")),
        })
    # Cap auf last 50 — bei vielen ACs nicht den Trail sprengen
    acceptance_checks = acceptance_checks[-50:]

    # --- AC-Verifications aggregation (ACVerified/ACFailed for this issue) ---
    # #236: pro AC ein Eintrag mit tag/arg/passed/reason für Dashboard.
    acceptance_checks: list[dict[str, Any]] = []
    for ts, name, payload, _ in issue_events:
        if name not in ("ACVerified", "ACFailed"):
            continue
        acceptance_checks.append({
            "timestamp": ts,
            "tag": str(payload.get("tag", "")),
            "arg": str(payload.get("arg", "")),
            "passed": bool(payload.get("passed", False)),
            "reason": str(payload.get("reason", "")),
        })
    # Cap auf last 50 — bei vielen ACs nicht den Trail sprengen
    acceptance_checks = acceptance_checks[-50:]

    runs = get_workflow_runs(issue_num, data_dir, limit)
    trend = _classify_workflow_trend(runs)

    return {
        "number": issue_num,
        "status": overall_status,
        "branch": last_branch,
        "events": trail,
        "stages": stages,
        "score": score,
        "test_runs": test_runs,
        "acceptance_checks": acceptance_checks,
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
            "by_provider": {
                k: {**v, "cost": round(v["cost"], 6)} for k, v in by_provider.items()
            },
            "by_task": {
                k: {**v, "cost": round(v["cost"], 6)} for k, v in by_task.items()
            },
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
}


def _classify_run_final_status(events: list[tuple[str, str, dict]]) -> str:
    """#277: derive a single final status for a run from its event-list.

    Priority order (highest first), so a successful PR overrides a
    transient failure earlier in the same run:
    - ``pr_created`` if any PRCreated event present
    - ``aborted`` if any WorkflowAborted
    - ``blocked`` if any WorkflowBlocked or GateFailed
    - ``eval_failed`` if any EvalFailed (and no recovery via PRCreated)
    - ``incomplete`` otherwise
    """
    names = {name for _, name, _ in events}
    if "PRCreated" in names:
        return "pr_created"
    if "WorkflowAborted" in names:
        return "aborted"
    if "WorkflowBlocked" in names or "GateFailed" in names:
        return "blocked"
    if "EvalFailed" in names:
        return "eval_failed"
    return "incomplete"


_RUN_PASSED_STATUSES: set[str] = {"pr_created"}


def get_workflow_runs(
    issue_num: int, data_dir: str = "data", limit: int = 2000,
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
    events = load_audit_events(data_dir, limit)
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
            if n in ("EvalCompleted", "EvalFailed") and "score" in p:
                try:
                    score = float(p["score"])
                except (TypeError, ValueError):
                    pass

        stages_done = sum(
            1 for s, ns in _PIPELINE_STAGE_EVENTS.items()
            if any(n in ns and n not in _STAGE_FAIL_EVENTS for n in names)
        )
        stages_failed = sum(
            1 for s, ns in _PIPELINE_STAGE_EVENTS.items()
            if any(n in ns and n in _STAGE_FAIL_EVENTS for n in names)
        )

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
                except (TypeError, ValueError):
                    pass

        runs.append({
            "run_id": corr,
            "start_ts": evts[0][0],
            "end_ts": evts[-1][0],
            "final_status": _classify_run_final_status(evts),
            "score": score,
            "stages_done": stages_done,
            "stages_failed": stages_failed,
            "gate_failures": gate_failures,
            "pr_number": pr_number,
            "event_count": len(evts),
        })

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
        "GateFailed", "WorkflowAborted", "WorkflowBlocked",
        "SecurityTripwireTriggered", "ImplementationFailed",
        "TamperDetected", "UnauthorizedChange", "IntegrityViolation",
    },
    "warn": {
        "HealingFailed", "QualityFailed", "EvalFailed", "TokenLimitHit",
        "LLMUnavailable", "PlanBlocked", "ReviewBlocked",
        # #239: HealingAborted ist Operator-Eingriff erforderlich
        "HealingAborted",
    },
}


def get_score_history(data_dir: str = "data", limit: int = 15) -> list[dict]:
    """Return the latest ``limit`` Eval outcomes for trend display.

    Picks ``EvalCompleted`` and ``EvalFailed`` events (which carry score/
    baseline). ``Evaluate`` is skipped because it is fired before scoring
    completes and so has no score. Newest first. Each row:
    ``{timestamp, score, baseline, passed, reason, issue, correlation_id}``.
    """
    events = load_audit_events(data_dir, 1000)
    rows: list[dict] = []
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        msg = payload.get("message_name", "")
        if msg not in ("EvalCompleted", "EvalFailed"):
            continue
        rows.append({
            "timestamp": evt.get("ts", ""),
            "score": payload.get("score"),
            "baseline": payload.get("baseline"),
            "passed": msg == "EvalCompleted",
            "reason": str(payload.get("reason", "") or ""),
            "issue": payload.get("issue"),
            "correlation_id": payload.get("correlation_id", ""),
        })
    rows.reverse()
    return rows[:limit]


def get_runtime_anomalies(
    data_dir: str = "data", hours: int = 24, limit: int = 50
) -> list[dict]:
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
        elif msg in _ANOMALY_LEVEL_EVENTS["warn"] or msg == "TestRunCompleted" and not payload.get("passed", True):
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
        rows.append({
            "timestamp": evt.get("ts", ""),
            "level": level,
            "event": msg,
            "category": cat,
            "message": _build_message(evt),
            "issue": payload.get("issue"),
            "owasp": payload.get("owasp_risk") or _classify_owasp(cat, evt_key) or "",
        })
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


def get_system_tiles(
    data_dir: str = "data", config: Any = None, scm: Any = None
) -> list[dict]:
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
        tiles.append({
            "key": "scm",
            "label": "SCM",
            "value": "connected",
            "kind": "ok",
            "detail": repo or "configured",
        })
    else:
        tiles.append({
            "key": "scm",
            "label": "SCM",
            "value": "offline",
            "kind": "err",
            "detail": "no SCM adapter",
        })

    # LLM provider/model
    if config:
        provider = str(config.get("llm.default.provider", "-") or "-")
        model = "-"
        if provider != "-":
            model = str(config.get(f"llm.{provider}.model", "-") or "-")
        kind = "ok" if provider != "-" else "warn"
        tiles.append({
            "key": "llm",
            "label": "LLM",
            "value": provider,
            "kind": kind,
            "detail": model,
        })
    else:
        tiles.append({
            "key": "llm", "label": "LLM", "value": "-",
            "kind": "warn", "detail": "no config",
        })

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
    tiles.append({
        "key": "disk", "label": "Disk", "value": value,
        "kind": kind, "detail": detail,
    })

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
    tiles.append({
        "key": "events_24h", "label": "Events 24h",
        "value": str(recent), "kind": "ok" if recent else "neutral",
        "detail": f"{errors} errors" if errors else "no errors",
    })
    tiles.append({
        "key": "errors_24h", "label": "Errors 24h",
        "value": str(errors), "kind": err_kind,
        "detail": "GateFailed/Aborted/etc.",
    })

    # Latest Eval
    history = get_score_history(data_dir, limit=1)
    if history:
        h = history[0]
        score = h.get("score")
        baseline = h.get("baseline")
        passed = h.get("passed")
        kind = "ok" if passed else "err"
        if score is not None and baseline is not None:
            value = f"{score} / {baseline}"
        elif score is not None:
            value = str(score)
        else:
            value = "FAIL" if not passed else "OK"
        detail = h.get("timestamp", "")[:19] or "-"
        if h.get("reason"):
            detail = f"{detail} — {h['reason'][:40]}"
        tiles.append({
            "key": "eval", "label": "Eval (last)",
            "value": value, "kind": kind, "detail": detail,
        })
    else:
        tiles.append({
            "key": "eval", "label": "Eval (last)",
            "value": "-", "kind": "neutral", "detail": "no eval events",
        })

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
        rows.append({
            "timestamp": evt.get("ts", ""),
            "gen_ai.system": payload.get("provider", ""),
            "gen_ai.request.model": payload.get("model", ""),
            "gen_ai.usage.input_tokens": payload.get("input_tokens"),
            "gen_ai.usage.output_tokens": payload.get("output_tokens"),
            "gen_ai.usage.total_tokens": total_tokens,
            "gen_ai.client.operation.duration": payload.get("latency_ms"),
            "gen_ai.response.finish_reasons": payload.get("stop_reason", ""),
            "task": payload.get("task", ""),
        })
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
        rows.append({
            "timestamp": evt.get("ts", ""),
            "provider": payload.get("provider", ""),
            "model": payload.get("model", ""),
            "task": payload.get("task", ""),
            "tokens": payload.get("tokens"),
            "input_tokens": payload.get("input_tokens"),
            "output_tokens": payload.get("output_tokens"),
            "cached_tokens": payload.get("cached_tokens"),
            "cost": payload.get("cost"),
            "latency_ms": payload.get("latency_ms"),
            "stop_reason": payload.get("stop_reason", ""),
            "issue": payload.get("issue"),
            "guards": list(payload.get("guards", []) or []),
            "tools_loaded": list(payload.get("tools_loaded", []) or []),
            "context_sections": list(payload.get("context_sections", []) or []),
            "prompt_tokens_est": payload.get("prompt_tokens_est"),
        })
    rows.reverse()
    return rows[:limit]


def get_llm_quality_scores(data_dir: str = "data", limit: int = 500) -> list[dict]:
    """Pair LLMCallCompleted with EvalCompleted via correlation_id.

    For every LLMCall that shares a correlation_id with at least one
    EvalCompleted/EvalFailed in the same log, attribute that eval-outcome
    to the (provider, model, task) tuple.

    Returns one row per (provider, model, task) with: calls (number of
    correlated calls), passed (count of EvalCompleted), failed (count of
    EvalFailed), success_rate_pct, avg_score, last_ts.

    Limitation: events without correlation_id (or without a paired Eval)
    contribute to ``calls`` but not to pass/fail. This means tracking is
    pessimistic until the LLM-issue-correlation gap (#206) is closed.
    """
    events = load_audit_events(data_dir, limit)
    # Build correlation_id -> (passed: bool|None, score: float|None, ts: str)
    eval_by_corr: dict[str, dict] = {}
    for evt in events:
        payload = evt.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        msg = payload.get("message_name", "")
        if msg not in ("EvalCompleted", "EvalFailed"):
            continue
        corr = payload.get("correlation_id") or ""
        if not corr:
            continue
        eval_by_corr[corr] = {
            "passed": msg == "EvalCompleted",
            "score": payload.get("score"),
            "ts": evt.get("ts", ""),
        }

    by_key: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "passed": 0, "failed": 0, "score_sum": 0.0,
                 "score_count": 0, "last_ts": ""}
    )
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
        bucket["calls"] += 1
        bucket["last_ts"] = evt.get("ts", "")
        corr = payload.get("correlation_id") or ""
        eval_info = eval_by_corr.get(corr)
        if eval_info is None:
            continue
        if eval_info["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
        score = eval_info.get("score")
        if isinstance(score, (int, float)):
            bucket["score_sum"] += float(score)
            bucket["score_count"] += 1

    rows: list[dict] = []
    for (provider, model, task), b in by_key.items():
        graded = b["passed"] + b["failed"]
        rows.append({
            "provider": provider,
            "model": model,
            "task": task,
            "calls": b["calls"],
            "graded": graded,
            "passed": b["passed"],
            "failed": b["failed"],
            "success_rate_pct": round(b["passed"] / graded * 100) if graded else None,
            "avg_score": round(b["score_sum"] / b["score_count"], 3) if b["score_count"] else None,
            "last_ts": b["last_ts"],
        })
    rows.sort(key=lambda r: r["last_ts"], reverse=True)
    return rows


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load %s: %s", path, exc)
        return {}


def get_api_key_status(
    config_dir: str = "config",
    *,
    balance_resolver=None,
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
    events = load_audit_events(data_dir, 500)

    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    by_task: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})

    for evt in events:
        payload = evt.get("payload", {})
        msg_name = payload.get("message_name", "")
        if msg_name == "LLMCallCompleted":
            total_calls += 1
            tokens = payload.get("tokens", 0) or payload.get("input_tokens", 0) + payload.get("output_tokens", 0)
            cost = payload.get("cost", 0.0)
            task = payload.get("task", "default")
            total_tokens += tokens
            total_cost += cost
            by_task[task]["calls"] += 1
            by_task[task]["tokens"] += tokens
            by_task[task]["cost"] += cost

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "by_task": dict(by_task),
    }


def get_branches() -> list[dict]:
    """Get git branch overview."""
    branches = []
    try:
        result = subprocess.run(
            ["git", "branch", "--format=%(refname:short) %(upstream:trackshort) %(committerdate:relative)"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.strip().split(" ", 2)
                if parts and parts[0] and parts[0] != "main":
                    branches.append({
                        "name": parts[0],
                        "track": parts[1] if len(parts) > 1 else "",
                        "age": parts[2] if len(parts) > 2 else "",
                    })
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
    ("auto_merge_pr", "Auto-Merge nach Gates", False),
    ("hallucination_guard", "Hallucination-Guard", True),
    ("sequence_validator", "Sequence-Validator", True),
    ("scope_guard", "Scope-Guard", True),
    ("acceptance_check", "AC-Verifikation", True),
    ("llm_attribution", "AI-Attribution in Commits", True),
    ("health_checks", "Health-Checks bei Start", True),
]


def get_feature_flags(config) -> list[dict]:
    """Get all feature flags with current state."""
    flags = []
    for key, desc, default in KNOWN_FEATURE_FLAGS:
        flags.append({
            "key": key,
            "enabled": config.feature_flag(key) if config else default,
            "description": desc,
        })
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


def get_llm_routing(
    config, config_dir: str = "config",
    prompt_source_resolver: Callable[
        [str, str, str | None, str | None, dict | None], dict[str, Any],
    ] | None = None,
) -> list[dict]:
    """Return provider/model per task with max_tokens/temperature/timeout.

    Resolves per task in this order:
    - provider/model: ``llm.tasks.<task>.provider/model`` → ``llm.default.*``
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
        return [{
            "task": "default", "provider": "-", "model": "-",
            "max_tokens": None, "temperature": None, "timeout": None,
        }]

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

    def _row(task: str) -> dict[str, Any]:
        prov = config.get(f"llm.tasks.{task}.provider") or default_provider
        mdl = config.get(f"llm.tasks.{task}.model") or default_model
        task_cfg = task_overrides.get(task, {}) if isinstance(task_overrides, dict) else {}
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
                sp_name, config_dir, prov, mdl, sp_by_provider,
            )
        else:
            sp_source = {"source": "none", "path": "", "mtime": 0.0}
        # All persisted task fields must round-trip through this view, otherwise
        # the LLM-Editor reload appears to "lose" the saved value (#338-audit:
        # `system_prompt` was missing from the row, so the dropdown rendered
        # empty after reload even though the JSON still held the override).
        return {
            "task":                       task,
            "provider":                   prov,
            "model":                      mdl,
            "base_url":                   task_cfg.get("base_url", ""),
            "max_tokens":                 task_cfg.get("max_tokens", base_max_tokens),
            "temperature":                task_cfg.get("temperature", base_temperature),
            "timeout":                    task_cfg.get("timeout", base_timeout),
            "system_prompt":              sp_name,
            "system_prompt_source":       sp_source,
            "system_prompt_by_provider":  sp_by_provider,
            "schedule":                   task_cfg.get("schedule") or {},
        }

    # Take the union of LLM_TASK_NAMES and tasks present in defaults.json
    seen: dict[str, dict[str, Any]] = {}
    for task in LLM_TASK_NAMES:
        if config.get(f"llm.tasks.{task}.provider") is not None or \
                config.get(f"llm.tasks.{task}.model") is not None or \
                task in task_overrides:
            seen[task] = _row(task)
    for task in task_overrides:
        if task not in seen:
            seen[task] = _row(task)

    if not seen:
        return [{
            "task": "default", "provider": default_provider, "model": default_model,
            "max_tokens": base_max_tokens, "temperature": base_temperature,
            "timeout": base_timeout,
        }]
    return list(seen.values())


def get_llm_routing_schedule(config, config_dir: str = "config") -> dict[str, Any]:
    """#302: Return per-task schedule blocks with current active state.

    Reads ``config/llm/defaults.json:tasks..schedule``. The ``enabled``
    flag reflects whether the premium feature ``llm_routing_advanced`` is
    active — if not, schedule blocks are present but inert.
    """
    from samuel.core import license as _lic
    from samuel.core.schedule import schedule_active as _schedule_active

    enabled = _lic.is_premium_active() and _lic.has_feature("llm_routing_advanced")

    defaults_path = Path(config_dir) / "llm" / "defaults.json"
    tasks_cfg: dict = {}
    if defaults_path.is_file():
        try:
            tasks_cfg = (json.loads(defaults_path.read_text(encoding="utf-8"))
                         .get("tasks") or {})
        except Exception as exc:
            log.warning("Failed to parse %s: %s", defaults_path, exc)

    rows = []
    for task_name, cfg in tasks_cfg.items():
        if not isinstance(cfg, dict):
            continue
        sched = cfg.get("schedule")
        if not isinstance(sched, dict):
            continue
        rows.append({
            "task": task_name,
            "day_provider": cfg.get("provider", "-"),
            "day_model": cfg.get("model", "-"),
            "night_provider": sched.get("provider", "-"),
            "night_model": sched.get("model", "-"),
            "from": sched.get("from", "-"),
            "to": sched.get("to", "-"),
            "active_now": enabled and _schedule_active(sched),
        })

    return {
        "enabled": enabled,
        "tasks": rows,
        "night_hours": "config-driven (per task)",
    }


_TAMPER_MSG_NAMES: set[str] = {
    "TamperDetected",
    "UnauthorizedChange",
    "IntegrityViolation",
}


def get_tamper_events(data_dir: str = "data", limit: int = 20) -> list[dict]:
    """Return tamper / integrity / broken trust boundary events.

    Includes payload message_name in {TamperDetected, UnauthorizedChange,
    IntegrityViolation} OR owasp_risk == ``broken_trust_boundaries``.
    Newest first, capped at ``limit``.
    """
    events = load_audit_events(data_dir, 500)
    matches: list[dict] = []
    for evt in events:
        payload = evt.get("payload", {}) or {}
        msg_name = payload.get("message_name", "")
        owasp = str(payload.get("owasp_risk", "")).lower()
        if msg_name in _TAMPER_MSG_NAMES or "broken_trust_boundaries" in owasp:
            matches.append({
                "ts": evt.get("ts", ""),
                "event": msg_name or evt.get("name", ""),
                "owasp": payload.get("owasp_risk", ""),
                "detail": payload.get("reason", "") or payload.get("detail", ""),
                "issue": payload.get("issue", ""),
            })
    matches.reverse()
    return matches[:limit]


def _classify_level(evt: dict) -> str:
    payload = evt.get("payload", {})
    name = payload.get("message_name", "")
    if name in ("GateFailed", "WorkflowAborted", "WorkflowBlocked", "SecurityTripwireTriggered", "ImplementationFailed"):
        return "error"
    if name in ("HealingFailed", "QualityFailed", "EvalFailed", "TokenLimitHit"):
        return "warn"
    return "info"


def _classify_category(evt: dict) -> str:
    payload = evt.get("payload", {})
    name = payload.get("message_name", "")
    categories = {
        "PlanCreated": "workflow", "PlanValidated": "workflow", "PlanBlocked": "workflow",
        "CodeGenerated": "workflow", "PRCreated": "workflow", "IssueReady": "workflow",
        "GateFailed": "gates", "GatesPassed": "gates",
        "SecurityTripwireTriggered": "security",
        "LLMCallCompleted": "llm", "LLMUnavailable": "llm",
        "EvalCompleted": "eval", "EvalFailed": "eval", "TestRunCompleted": "eval",
        "ACVerified": "eval", "ACFailed": "eval",
        "PlanContextLoaded": "context",
        "ACVerified": "eval", "ACFailed": "eval",
        "PlanPreCheckCompleted": "guard",
        "PlanComplexityWarn": "plan",
        # #239: Healing-Loop-Events
        "HealingSuggested": "workflow",
        "HealingAttemptStarted": "workflow",
        "HealingAttemptCompleted": "workflow",
        "HealingAborted": "workflow",
        "HealthCheck": "system", "ConfigReloaded": "config",
        "HealingFailed": "workflow",
        "QualityFailed": "quality", "QualityPassed": "quality",
        "WorkflowAborted": "workflow", "WorkflowBlocked": "workflow",
    }
    return categories.get(name, "system")


def _build_message(evt: dict) -> str:
    payload = evt.get("payload", {})
    name = payload.get("message_name", "")
    reason = payload.get("reason", "")
    if reason:
        return f"{name}: {reason}"
    return name
