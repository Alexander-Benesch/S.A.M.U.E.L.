"""Tests for the new Phase 14.6 data-layer helpers."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from samuel.core.ports import IConfig
from samuel.slices.dashboard.data import (
    get_api_key_status,
    get_command_metrics,
    get_compliance_legend,
    get_llm_quality_scores,
    get_llm_routing,
    get_llm_routing_schedule,
    get_log_entries,
    get_log_level_counts,
    get_otel_gen_ai_calls,
    get_runtime_anomalies,
    get_score_history,
    get_security_overview,
    get_system_tiles,
    get_tamper_events,
    get_token_history,
    get_workflow_issue_detail,
    get_workflow_issues,
    get_workflow_runs,
    load_audit_events,
)


class _Cfg(IConfig):
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        pass


def _write_audit(tmp_path: Path, events: list[dict]) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "agent.jsonl", "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


class TestGetLLMRouting:
    def test_no_config_returns_default_row(self) -> None:
        rows = get_llm_routing(None)
        assert len(rows) == 1
        assert rows[0]["task"] == "default"
        assert rows[0]["provider"] == "-"
        assert rows[0]["model"] == "-"
        assert rows[0]["max_tokens"] is None
        assert rows[0]["temperature"] is None

    def test_default_only(self, tmp_path: Path) -> None:
        # No config_dir provided → defaults are missing → max_tokens stays None
        cfg = _Cfg({"llm.default.provider": "deepseek", "llm.default.model": "deepseek-chat"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        assert len(rows) == 1
        r = rows[0]
        assert r["task"] == "default"
        assert r["provider"] == "deepseek"
        assert r["model"] == "deepseek-chat"
        assert r["max_tokens"] is None

    def test_task_specific_overrides_included(self, tmp_path: Path) -> None:
        # #225: LLM_TASK_NAMES auf kanonische Long-Form reduziert — pr_review entfernt,
        # review ist jetzt der korrekte Task-Name.
        cfg = _Cfg({
            "llm.default.provider": "deepseek",
            "llm.default.model": "deepseek-chat",
            "llm.tasks.planning.provider": "claude",
            "llm.tasks.planning.model": "claude-sonnet-4-6",
            "llm.tasks.review.provider": "ollama",
        })
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        assert {r["task"] for r in rows} == {"planning", "review"}
        planning = next(r for r in rows if r["task"] == "planning")
        assert planning["provider"] == "claude"
        assert planning["model"] == "claude-sonnet-4-6"
        review = next(r for r in rows if r["task"] == "review")
        assert review["provider"] == "ollama"
        assert review["model"] == "deepseek-chat"  # fallback to default

    def test_max_tokens_from_defaults_json(self, tmp_path: Path) -> None:
        # defaults.json provides per-task max_tokens; routing must surface it
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(json.dumps({
            "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
            "tasks": {
                "implement": {"max_tokens": 8192, "temperature": 0.1},
                "eval": {"max_tokens": 2048, "temperature": 0.0},
            },
        }))
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        assert {r["task"] for r in rows} == {"implement", "eval"}
        impl = next(r for r in rows if r["task"] == "implement")
        assert impl["max_tokens"] == 8192
        assert impl["temperature"] == 0.1
        assert impl["timeout"] == 60  # from default
        ev = next(r for r in rows if r["task"] == "eval")
        assert ev["max_tokens"] == 2048

    def test_routing_row_carries_system_prompt_and_base_url_and_schedule(
        self, tmp_path: Path,
    ) -> None:
        """#338-audit: every persisted task field must round-trip through
        get_llm_routing — otherwise the LLM-Editor reload appears to drop
        the user's saved values (system_prompt was the missing one)."""
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(json.dumps({
            "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
            "tasks": {
                "review": {
                    "provider":      "deepseek",
                    "model":         "deepseek-chat",
                    "base_url":      "https://api.deepseek.com",
                    "system_prompt": "reviewer.md",
                    "timeout":       180,
                    "schedule":      {
                        "active": True, "from": "22:00", "to": "06:00",
                        "provider": "ollama", "model": "llama3",
                    },
                },
            },
        }))
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        review = next(r for r in rows if r["task"] == "review")
        assert review["system_prompt"] == "reviewer.md"
        assert review["base_url"] == "https://api.deepseek.com"
        assert review["timeout"] == 180  # task-specific, not the base 60
        assert review["schedule"]["active"] is True
        assert review["schedule"]["provider"] == "ollama"

    def test_routing_row_defaults_empty_strings_when_field_absent(
        self, tmp_path: Path,
    ) -> None:
        """When a task has no system_prompt configured, the row reports an
        empty string (so the frontend dropdown can default to '(none)')."""
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(json.dumps({
            "tasks": {"planning": {"provider": "ollama", "model": "x"}},
        }))
        cfg = _Cfg({"llm.default.provider": "ollama"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        planning = next(r for r in rows if r["task"] == "planning")
        assert planning["system_prompt"] == ""
        assert planning["base_url"] == ""
        assert planning["schedule"] == {}

    @staticmethod
    def _file_based_resolver(base: Path):
        """Mock resolver mirroring the cascade contract of
        ``samuel.adapters.llm.prompts.resolve_prompt_source``. Slice tests
        must not import the adapter directly (architecture rule); the real
        resolver has its own tests in ``samuel/adapters/llm/tests/``.
        """
        def _resolve(name, cdir, provider, model, by_provider=None):  # noqa: ARG001
            # #351: by_provider map wins for the active provider (mirrors
            # the real resolver). Empty/missing -> use ``name``.
            effective = name
            if isinstance(by_provider, dict) and provider in (by_provider or {}):
                v = by_provider[provider]
                if isinstance(v, str) and v.strip() and "/" not in v and ".." not in v:
                    effective = v
            if not effective:
                return {"source": "none", "path": "", "mtime": 0.0}
            checks: list[tuple[Path, str]] = []
            if model:
                checks.append((base / "model" / str(model) / effective,
                               f"operator-model:{model}"))
            if provider:
                checks.append((base / "provider" / str(provider) / effective,
                               f"operator-provider:{provider}"))
            checks.append((base / effective, "operator-generic"))
            for p, label in checks:
                if p.is_file():
                    return {"source": label, "path": str(p), "mtime": 1.0}
            return {"source": "package", "path": f"/pkg/{effective}", "mtime": 1.0}
        return _resolve

    def test_routing_row_includes_system_prompt_source(
        self, tmp_path: Path,
    ) -> None:
        """#348: row carries which cascade-layer the active prompt comes
        from, so the editor can show "[package]" / "[operator-...]"."""
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(json.dumps({
            "tasks": {
                "planning": {
                    "provider":      "deepseek",
                    "model":         "deepseek-chat",
                    "system_prompt": "planner.md",
                },
                # No system_prompt configured -> source must report "none"
                "review": {"provider": "ollama", "model": "llama3"},
            },
        }))
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(
            cfg, config_dir=str(tmp_path),
            prompt_source_resolver=self._file_based_resolver(
                tmp_path / "llm" / "prompts",
            ),
        )
        plan = next(r for r in rows if r["task"] == "planning")
        rev = next(r for r in rows if r["task"] == "review")
        assert "system_prompt_source" in plan
        # No operator override present anywhere -> falls through to package.
        assert plan["system_prompt_source"]["source"] == "package"
        # No prompt configured -> source = none, resolver not consulted.
        assert rev["system_prompt_source"] == {
            "source": "none", "path": "", "mtime": 0.0,
        }

    def test_system_prompt_source_picks_provider_override_when_available(
        self, tmp_path: Path,
    ) -> None:
        """When a per-provider override file exists, the row reports
        operator-provider:<name> as the active source."""
        prov_dir = tmp_path / "llm" / "prompts" / "provider" / "deepseek"
        prov_dir.mkdir(parents=True)
        (prov_dir / "planner.md").write_text("DEEPSEEK PLANNER", encoding="utf-8")
        (tmp_path / "llm" / "defaults.json").write_text(json.dumps({
            "tasks": {
                "planning": {
                    "provider":      "deepseek",
                    "model":         "deepseek-chat",
                    "system_prompt": "planner.md",
                },
            },
        }))
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(
            cfg, config_dir=str(tmp_path),
            prompt_source_resolver=self._file_based_resolver(
                tmp_path / "llm" / "prompts",
            ),
        )
        plan = next(r for r in rows if r["task"] == "planning")
        assert plan["system_prompt_source"]["source"] == "operator-provider:deepseek"
        assert plan["system_prompt_source"]["path"].endswith(
            "provider/deepseek/planner.md",
        )

    def test_routing_row_omits_source_call_when_no_resolver_wired(
        self, tmp_path: Path,
    ) -> None:
        """Without an injected resolver (slice-iso fallback), row still
        carries the slot but reports source=none."""
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(json.dumps({
            "tasks": {
                "planning": {
                    "provider":      "ollama",
                    "model":         "llama3",
                    "system_prompt": "planner.md",
                },
            },
        }))
        cfg = _Cfg({"llm.default.provider": "ollama"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        plan = next(r for r in rows if r["task"] == "planning")
        assert plan["system_prompt_source"]["source"] == "none"

    def test_routing_row_carries_system_prompt_by_provider(
        self, tmp_path: Path,
    ) -> None:
        """#351: per-provider override map round-trips through the row so
        the editor can render and re-save it."""
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(json.dumps({
            "tasks": {
                "planning": {
                    "provider":      "deepseek",
                    "model":         "deepseek-chat",
                    "system_prompt": "planner.md",
                    "system_prompt_by_provider": {
                        "deepseek": "planner_local.md",
                        "claude":   "planner_kompakt.md",
                    },
                },
            },
        }))
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        plan = next(r for r in rows if r["task"] == "planning")
        assert plan["system_prompt_by_provider"] == {
            "deepseek": "planner_local.md",
            "claude":   "planner_kompakt.md",
        }

    def test_routing_row_source_reflects_by_provider_override(
        self, tmp_path: Path,
    ) -> None:
        """#351 + #348: when the active provider has an entry, the source-
        indicator must point to that file (not to the task default)."""
        prompts_dir = tmp_path / "llm" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "planner_local.md").write_text(
            "LOCAL", encoding="utf-8",
        )
        (tmp_path / "llm" / "defaults.json").write_text(json.dumps({
            "tasks": {
                "planning": {
                    "provider":      "deepseek",
                    "model":         "deepseek-chat",
                    "system_prompt": "planner.md",
                    "system_prompt_by_provider": {
                        "deepseek": "planner_local.md",
                    },
                },
            },
        }))
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(
            cfg, config_dir=str(tmp_path),
            prompt_source_resolver=self._file_based_resolver(prompts_dir),
        )
        plan = next(r for r in rows if r["task"] == "planning")
        # Source points at the by_provider override file, not the default.
        assert plan["system_prompt_source"]["source"] == "operator-generic"
        assert plan["system_prompt_source"]["path"].endswith("planner_local.md")

    def test_routing_row_empty_by_provider_when_field_absent(
        self, tmp_path: Path,
    ) -> None:
        """Default for missing field is empty dict, not None — frontend
        can iterate over it without null-check."""
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(json.dumps({
            "tasks": {
                "review": {"provider": "ollama", "model": "llama3"},
            },
        }))
        cfg = _Cfg({"llm.default.provider": "ollama"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        rev = next(r for r in rows if r["task"] == "review")
        assert rev["system_prompt_by_provider"] == {}


class TestGetTamperEvents:
    def test_tamper_message_names_detected(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "2026-04-17T10:00", "name": "x", "payload": {"message_name": "PlanCreated"}},
            {"ts": "2026-04-17T10:01", "name": "x", "payload": {"message_name": "TamperDetected", "reason": "bad"}},
            {"ts": "2026-04-17T10:02", "name": "x", "payload": {"message_name": "UnauthorizedChange"}},
            {"ts": "2026-04-17T10:03", "name": "x", "payload": {"message_name": "IntegrityViolation"}},
        ])
        events = get_tamper_events(str(tmp_path))
        names = [e["event"] for e in events]
        # Newest first
        assert names == ["IntegrityViolation", "UnauthorizedChange", "TamperDetected"]
        assert events[2]["detail"] == "bad"

    def test_broken_trust_boundaries_matched_via_owasp(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "x", "payload": {"message_name": "Whatever", "owasp_risk": "broken_trust_boundaries"}},
        ])
        events = get_tamper_events(str(tmp_path))
        assert len(events) == 1
        assert events[0]["owasp"] == "broken_trust_boundaries"

    def test_empty_when_no_matches(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "x", "payload": {"message_name": "PlanCreated"}},
        ])
        events = get_tamper_events(str(tmp_path))
        assert events == []

    def test_limit_applied(self, tmp_path: Path) -> None:
        many = [
            {"ts": f"t{i}", "name": "x", "payload": {"message_name": "TamperDetected"}}
            for i in range(30)
        ]
        _write_audit(tmp_path, many)
        events = get_tamper_events(str(tmp_path), limit=20)
        assert len(events) == 20


class TestLoadAuditEventsRotation:
    def test_reads_rotated_files(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "agent_2026-04-15.jsonl").write_text(
            json.dumps({"name": "Old", "ts": "2026-04-15T00:00:00Z"}) + "\n"
        )
        (log_dir / "agent_2026-04-29.jsonl").write_text(
            json.dumps({"name": "Recent", "ts": "2026-04-29T00:00:00Z"}) + "\n"
        )
        events = load_audit_events(str(tmp_path))
        names = [e["name"] for e in events]
        assert names == ["Old", "Recent"]

    def test_reads_unrotated_agent_jsonl(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.jsonl").write_text(
            json.dumps({"name": "X"}) + "\n" + json.dumps({"name": "Y"}) + "\n"
        )
        events = load_audit_events(str(tmp_path))
        assert [e["name"] for e in events] == ["X", "Y"]

    def test_combines_rotated_and_unrotated(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.jsonl").write_text(json.dumps({"name": "Live"}) + "\n")
        (log_dir / "agent_2026-04-15.jsonl").write_text(
            json.dumps({"name": "Old"}) + "\n"
        )
        events = load_audit_events(str(tmp_path))
        names = [e["name"] for e in events]
        assert sorted(names) == ["Live", "Old"]

    def test_limit_applied_across_files(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "agent_2026-04-15.jsonl").write_text(
            "\n".join(json.dumps({"name": f"Old{i}"}) for i in range(50)) + "\n"
        )
        (log_dir / "agent_2026-04-29.jsonl").write_text(
            "\n".join(json.dumps({"name": f"New{i}"}) for i in range(50)) + "\n"
        )
        events = load_audit_events(str(tmp_path), limit=20)
        assert len(events) == 20
        assert all(e["name"].startswith("New") for e in events)

    def test_no_logs_dir_returns_empty(self, tmp_path: Path) -> None:
        assert load_audit_events(str(tmp_path)) == []

    def test_invalid_json_lines_skipped(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.jsonl").write_text(
            "not json\n" + json.dumps({"name": "OK"}) + "\n"
        )
        events = load_audit_events(str(tmp_path))
        assert [e["name"] for e in events] == ["OK"]


class TestGetCommandMetrics:
    def test_aggregates_counts_and_total_ms_per_command(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_type": "PlanIssueCommand",
                "message_name": "PlanIssue",
                "duration_ms": 12.5,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_type": "PlanIssueCommand",
                "message_name": "PlanIssue",
                "duration_ms": 7.5,
            }},
            {"ts": "t3", "name": "AuditEvent", "payload": {
                "message_type": "ImplementCommand",
                "message_name": "Implement",
                "duration_ms": 100.0,
            }},
        ])
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["counts"] == {"PlanIssue": 2, "Implement": 1}
        assert metrics["total_ms"] == {"PlanIssue": 20.0, "Implement": 100.0}
        assert metrics["errors"] == {}

    def test_skips_event_messages(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_type": "PlanCreated",  # not a Command
                "message_name": "PlanCreated",
            }},
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_type": "PlanIssueCommand",
                "message_name": "PlanIssue",
                "duration_ms": 1.0,
            }},
        ])
        metrics = get_command_metrics(str(tmp_path))
        assert "PlanCreated" not in metrics["counts"]
        assert metrics["counts"] == {"PlanIssue": 1}

    def test_attributes_workflow_aborted_to_source_command(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_type": "ImplementCommand",
                "message_name": "Implement",
                "duration_ms": 5.0,
            }},
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_type": "WorkflowAborted",
                "message_name": "WorkflowAborted",
                "source_command": "Implement",
                "reason": "gate failed",
            }},
        ])
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["counts"] == {"Implement": 1}
        assert metrics["errors"] == {"Implement": 1}

    def test_handles_missing_duration_gracefully(self, tmp_path: Path) -> None:
        # Old-format audit lines without duration_ms still count toward
        # 'counts' but contribute nothing to total_ms.
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_type": "PlanIssueCommand",
                "message_name": "PlanIssue",
            }},
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_type": "PlanIssueCommand",
                "message_name": "PlanIssue",
                "duration_ms": 4.0,
            }},
        ])
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["counts"] == {"PlanIssue": 2}
        assert metrics["total_ms"] == {"PlanIssue": 4.0}

    def test_empty_log_returns_empty_dicts(self, tmp_path: Path) -> None:
        metrics = get_command_metrics(str(tmp_path))
        assert metrics == {"counts": {}, "errors": {}, "total_ms": {}}

    def test_error_field_in_command_audit_counts_as_error(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_type": "EvaluateCommand",
                "message_name": "Evaluate",
                "duration_ms": 2.0,
                "error": "RuntimeError",
            }},
        ])
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["errors"] == {"Evaluate": 1}


class TestGetLogEntriesShape:
    def test_entries_use_timestamp_field(self, tmp_path: Path) -> None:
        # Frontend expects ``timestamp`` (not ``ts``) — see server.py:361
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 5,
            }},
        ])
        entries = get_log_entries(str(tmp_path))
        assert len(entries) == 1
        assert entries[0]["timestamp"] == "2026-04-29T10:00"
        assert "ts" not in entries[0]

    def test_entries_include_full_payload_as_meta(self, tmp_path: Path) -> None:
        # Issue #203: ▼-toggle row needs full payload to show provider/model/tokens/cost
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted",
                "provider": "deepseek", "model": "deepseek-chat",
                "tokens_used": 4096, "cost": 0.012,
            }},
        ])
        entries = get_log_entries(str(tmp_path))
        meta = entries[0]["meta"]
        assert meta["provider"] == "deepseek"
        assert meta["model"] == "deepseek-chat"
        assert meta["tokens_used"] == 4096
        assert meta["cost"] == 0.012

    def test_entries_meta_is_independent_copy(self, tmp_path: Path) -> None:
        # Mutating meta on one entry must not bleed into the underlying audit data
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 5,
            }},
        ])
        entries = get_log_entries(str(tmp_path))
        entries[0]["meta"]["mutated"] = True
        entries2 = get_log_entries(str(tmp_path))
        assert "mutated" not in entries2[0]["meta"]

    def test_resolved_at_annotation_from_payload_prev_timestamp(self, tmp_path: Path) -> None:
        # AuditHandler-style record: prev_timestamp at top level of payload
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00:00", "name": "AuditEvent", "payload": {
                "message_name": "self_check_fatal", "reason": "config missing",
            }},
            {"ts": "2026-04-29T10:05:00", "name": "AuditEvent", "payload": {
                "message_name": "self_check_resolved",
                "prev_timestamp": "2026-04-29T10:00:00",
            }},
        ])
        entries = get_log_entries(str(tmp_path))
        fatal = next(e for e in entries if e["event"] == "self_check_fatal")
        assert fatal.get("resolved_at") == "2026-04-29 10:05:00"

    def test_resolved_at_annotation_from_bridge_meta_prev_timestamp(self, tmp_path: Path) -> None:
        # bridge.audit() emits ``payload.evt`` and ``payload.meta.prev_timestamp``
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00:00", "name": "AuditEvent", "payload": {
                "evt": "self_check_fatal", "msg": "FATAL",
            }},
            {"ts": "2026-04-29T10:07:30", "name": "AuditEvent", "payload": {
                "evt": "self_check_resolved",
                "meta": {"prev_timestamp": "2026-04-29T10:00:00"},
            }},
        ])
        entries = get_log_entries(str(tmp_path))
        fatal = next(e for e in entries if e["meta"].get("evt") == "self_check_fatal")
        assert fatal.get("resolved_at") == "2026-04-29 10:07:30"

    def test_unresolved_fatal_has_no_resolved_at(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00:00", "name": "AuditEvent", "payload": {
                "message_name": "self_check_fatal",
            }},
        ])
        entries = get_log_entries(str(tmp_path))
        fatal = next(e for e in entries if e["event"] == "self_check_fatal")
        assert "resolved_at" not in fatal


class TestGetLogLevelCounts:
    def test_counts_grouped_by_classified_level(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {"message_name": "GateFailed"}},
            {"ts": "t2", "name": "AuditEvent", "payload": {"message_name": "WorkflowAborted"}},
            {"ts": "t3", "name": "AuditEvent", "payload": {"message_name": "HealingFailed"}},
            {"ts": "t4", "name": "AuditEvent", "payload": {"message_name": "PlanCreated"}},
            {"ts": "t5", "name": "AuditEvent", "payload": {"message_name": "PRCreated"}},
        ])
        counts = get_log_level_counts(str(tmp_path))
        assert counts == {"info": 2, "warn": 1, "error": 2}

    def test_counts_zero_when_empty(self, tmp_path: Path) -> None:
        (tmp_path / "logs").mkdir()
        assert get_log_level_counts(str(tmp_path)) == {"info": 0, "warn": 0, "error": 0}


class TestGetWorkflowIssuesShape:
    def test_issues_use_timestamp_field(self, tmp_path: Path) -> None:
        # Frontend expects ``timestamp`` (not ``last_ts``) — see server.py:326
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 5,
            }},
            {"ts": "2026-04-29T11:00", "name": "AuditEvent", "payload": {
                "message_name": "PRCreated", "issue": 5,
            }},
        ])
        issues = get_workflow_issues(str(tmp_path))
        assert len(issues) == 1
        assert issues[0]["timestamp"] == "2026-04-29T11:00"
        assert "last_ts" not in issues[0]


class TestGetSecurityOverviewShape:
    def test_owasp_returned_as_array(self, tmp_path: Path) -> None:
        # Frontend expects array ``owasp: [{id, category, count, last}]``
        # — see server.py:376-378 (the dict ``risks`` form was unused)
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed",
                "owasp_risk": "A04: Broken Trust",
            }},
        ])
        result = get_security_overview(str(tmp_path))
        assert "risks" not in result
        assert isinstance(result["owasp"], list)
        assert len(result["owasp"]) == 10  # one entry per A01..A10
        a04 = next(r for r in result["owasp"] if r["id"] == "A04")
        assert a04["count"] == 1
        assert a04["last"] == "2026-04-29T10:00"
        assert a04["category"] == "Broken Trust Boundaries"
        # Other risks present but with count 0
        a01 = next(r for r in result["owasp"] if r["id"] == "A01")
        assert a01["count"] == 0

    def test_barriers_use_frontend_field_names(self, tmp_path: Path) -> None:
        # Frontend reads barriers[].timestamp + barriers[].event
        # — see server.py:382 (b.timestamp||b.time, b.type||b.event)
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed",
                "gate": "BranchNotMain",
                "reason": "Branch ist main/master",
                "issue": 176,
            }},
        ])
        result = get_security_overview(str(tmp_path))
        assert len(result["barriers"]) == 1
        bar = result["barriers"][0]
        assert bar["timestamp"] == "2026-04-29T10:00"
        assert bar["event"] == "BranchNotMain"
        assert bar["action"] == "blocked"
        assert bar["detail"] == "Branch ist main/master"
        assert bar["issue"] == 176
        assert "ts" not in bar
        assert "gate" not in bar


class TestGetWorkflowIssueDetail:
    def test_returns_none_when_no_events_for_issue(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 5,
            }},
        ])
        assert get_workflow_issue_detail(99, str(tmp_path)) is None

    def test_audit_trail_chronological_and_capped_at_30(self, tmp_path: Path) -> None:
        events = [
            {"ts": f"2026-04-29T10:{i:02d}", "name": "AuditEvent", "payload": {
                "message_name": "Implement", "issue": 7, "reason": f"r{i}",
            }}
            for i in range(40)
        ]
        _write_audit(tmp_path, events)
        d = get_workflow_issue_detail(7, str(tmp_path))
        assert d is not None
        # Newest 30 chronologically (last 30 of the source list)
        assert len(d["events"]) == 30
        assert d["events"][0]["timestamp"] == "2026-04-29T10:10"
        assert d["events"][-1]["timestamp"] == "2026-04-29T10:39"
        assert all("level" in e and "category" in e for e in d["events"])

    def test_pipeline_stages_marked_done_failed_pending(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 1,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "CodeGenerated", "issue": 1,
            }},
            {"ts": "t3", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "issue": 1, "gate": 3,
            }},
        ])
        d = get_workflow_issue_detail(1, str(tmp_path))
        assert d is not None
        assert d["stages"]["plan"]["status"] == "done"
        assert d["stages"]["plan"]["count"] == 1
        assert d["stages"]["implement"]["status"] == "done"
        assert d["stages"]["gates"]["status"] == "failed"
        assert d["stages"]["gates"]["fail_count"] == 1
        # Stages without events are pending
        assert d["stages"]["pr"]["status"] == "pending"
        assert d["stages"]["eval"]["status"] == "pending"

    def test_stage_gates_done_on_passed_event(self, tmp_path: Path) -> None:
        """#258: GatesPassed-Event markiert gates-Stage als done.

        Vorher zeigte gates "pending" für erfolgreiche Runs weil nur
        GateFailed/SecurityTripwireTriggered im Mapping war."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "GatesPassed", "issue": 258, "gates_run": 12,
            }},
        ])
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["gates"]["status"] == "done"
        assert d["stages"]["gates"]["count"] == 1
        assert d["stages"]["gates"]["fail_count"] == 0

    def test_stage_quality_done_on_passed_event(self, tmp_path: Path) -> None:
        """#258: QualityPassed-Event markiert quality-Stage als done."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "QualityPassed", "issue": 258,
            }},
        ])
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["quality"]["status"] == "done"

    def test_stage_review_done_when_pr_created(self, tmp_path: Path) -> None:
        """#258: PRCreated impliziert review-Stage als done (kein
        ReviewCompleted-Event existiert heute)."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "PRCreated", "issue": 258, "pr_number": 999,
            }},
        ])
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["review"]["status"] == "done"
        assert d["stages"]["pr"]["status"] == "done"

    def test_stage_implement_inferred_from_pr_created(
        self, tmp_path: Path
    ) -> None:
        """#258 + #257: PRCreated impliziert implement-Stage als done — robust
        gegen verlorenes CodeGenerated-Event (Audit-Loss-Defense-in-Depth)."""
        _write_audit(tmp_path, [
            # Kein CodeGenerated-Event (simuliert verlorenes Event)
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "PRCreated", "issue": 258, "pr_number": 999,
            }},
        ])
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["implement"]["status"] == "done"

    def test_pipeline_all_stages_done_for_successful_run(
        self, tmp_path: Path
    ) -> None:
        """#258: realistischer Self-Mode-Run zeigt alle 8 Stages 'done'."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 258,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "PlanValidated", "issue": 258,
            }},
            {"ts": "t3", "name": "AuditEvent", "payload": {
                "message_name": "CodeGenerated", "issue": 258,
            }},
            {"ts": "t4", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "issue": 258, "task": "implementation",
            }},
            {"ts": "t5", "name": "AuditEvent", "payload": {
                "message_name": "QualityPassed", "issue": 258,
            }},
            {"ts": "t6", "name": "AuditEvent", "payload": {
                "message_name": "EvalCompleted", "issue": 258, "score": 1.0,
            }},
            {"ts": "t7", "name": "AuditEvent", "payload": {
                "message_name": "GatesPassed", "issue": 258, "gates_run": 12,
            }},
            {"ts": "t8", "name": "AuditEvent", "payload": {
                "message_name": "PRCreated", "issue": 258, "pr_number": 999,
            }},
        ])
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        for stage_name in ("plan", "implement", "llm", "gates", "quality", "eval", "pr", "review"):
            assert d["stages"][stage_name]["status"] == "done", (
                f"Stage {stage_name} should be 'done', got {d['stages'][stage_name]}"
            )

    def test_score_aggregated_from_eval_events(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "Evaluate", "issue": 9,
                "score": 80, "baseline": 60, "checks_passed": 4, "checks_total": 5,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "EvalCompleted", "issue": 9, "score": 80,
            }},
        ])
        d = get_workflow_issue_detail(9, str(tmp_path))
        assert d is not None
        assert d["score"]["value"] == 80
        assert d["score"]["baseline"] == 60
        assert d["score"]["passed"] is True
        assert d["score"]["checks_passed"] == 4
        assert d["score"]["checks_total"] == 5

    def test_score_passed_false_on_eval_failed(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "EvalFailed", "issue": 11, "reason": "no scores",
            }},
        ])
        d = get_workflow_issue_detail(11, str(tmp_path))
        assert d is not None
        assert d["score"]["passed"] is False
        assert d["score"]["reason"] == "no scores"

    def test_llm_aggregated_per_provider_and_task(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "issue": 13,
                "provider": "deepseek", "task": "implementation",
                "tokens": 500, "cost": 0.001,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "issue": 13,
                "provider": "deepseek", "task": "planning",
                "input_tokens": 100, "output_tokens": 200, "cost": 0.0005,
            }},
            {"ts": "t3", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "issue": 13,
                "provider": "claude", "task": "planning",
                "tokens": 300, "cost": 0.01,
            }},
        ])
        d = get_workflow_issue_detail(13, str(tmp_path))
        assert d is not None
        assert d["llm"]["calls"] == 3
        assert d["llm"]["tokens"] == 1100  # 500 + 300 + 300
        assert round(d["llm"]["cost"], 4) == 0.0115
        assert d["llm"]["by_provider"]["deepseek"]["calls"] == 2
        assert d["llm"]["by_provider"]["claude"]["calls"] == 1
        assert d["llm"]["by_task"]["planning"]["calls"] == 2
        assert d["llm"]["by_task"]["planning"]["tokens"] == 600

    def test_calls_detail_includes_phase1_metadata(self, tmp_path: Path) -> None:
        """Phase 3 (#218): pro LLM-Call die Phase-1-Felder
        (task/guards/tools_loaded/context_sections/prompt_tokens_est)
        in llm.calls_detail durchreichen, damit das Workflow-Issue-Detail
        die Felder auflisten kann."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "issue": 50,
                "provider": "deepseek", "model": "deepseek-chat",
                "task": "planning",
                "tokens": 500, "cost": 0.001, "latency_ms": 1234,
                "stop_reason": "stop",
                "guards": ["prompt_guards", "plan_validator"],
                "tools_loaded": ["PythonASTBuilder", "GoRegexBuilder"],
                "context_sections": ["skeleton", "grep"],
                "prompt_tokens_est": 1500,
            }},
        ])
        d = get_workflow_issue_detail(50, str(tmp_path))
        assert d is not None
        details = d["llm"]["calls_detail"]
        assert len(details) == 1
        c = details[0]
        assert c["task"] == "planning"
        assert c["provider"] == "deepseek"
        assert c["model"] == "deepseek-chat"
        assert c["tokens"] == 500
        assert c["latency_ms"] == 1234
        assert c["stop_reason"] == "stop"
        assert c["guards"] == ["prompt_guards", "plan_validator"]
        assert c["tools_loaded"] == ["PythonASTBuilder", "GoRegexBuilder"]
        assert c["context_sections"] == ["skeleton", "grep"]
        assert c["prompt_tokens_est"] == 1500

    def test_calls_detail_omits_for_old_events(self, tmp_path: Path) -> None:
        """Old LLMCallCompleted events without Phase-1 fields must still
        produce a row — empty lists, prompt_tokens_est=None."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "issue": 51,
                "provider": "deepseek", "task": "planning",
                "tokens": 100, "cost": 0.0,
            }},
        ])
        d = get_workflow_issue_detail(51, str(tmp_path))
        assert d is not None
        c = d["llm"]["calls_detail"][0]
        assert c["guards"] == []
        assert c["tools_loaded"] == []
        assert c["context_sections"] == []
        assert c["prompt_tokens_est"] is None

    def test_branch_is_last_seen(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "CodeGenerated", "issue": 4, "branch": "samuel/issue-4",
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "Implement", "issue": 4, "branch": "samuel/issue-4-v2",
            }},
        ])
        d = get_workflow_issue_detail(4, str(tmp_path))
        assert d is not None
        assert d["branch"] == "samuel/issue-4-v2"

    def test_overall_status_pr_created_overrides_implemented(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "CodeGenerated", "issue": 22,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "PRCreated", "issue": 22,
            }},
        ])
        d = get_workflow_issue_detail(22, str(tmp_path))
        assert d is not None
        assert d["status"] == "pr_created"

    def test_skips_other_issues(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 1,
            }},
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "Implement", "issue": 2,
            }},
        ])
        d = get_workflow_issue_detail(1, str(tmp_path))
        assert d is not None
        assert len(d["events"]) == 1
        assert d["events"][0]["event"] == "PlanCreated"
        assert d["stages"]["implement"]["status"] == "pending"


class TestSecurityOverviewExtras:
    def test_barrier_translates_gate_id_to_name(self, tmp_path: Path) -> None:
        # GateFailed.payload.gate is a numeric ID; the dashboard must show
        # the human-readable name (e.g. 1 → BranchGuard).
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "gate": 1,
                "reason": "Branch ist main", "issue": 9,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "gate": "13a",
                "reason": "Branch zu alt",
            }},
        ])
        result = get_security_overview(str(tmp_path))
        events = [b["event"] for b in result["barriers"]]
        assert "BranchGuard" in events
        assert "BranchFreshness" in events

    def test_barrier_event_falls_back_to_msg_name_when_no_gate_id(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "WorkflowAborted", "reason": "stop",
            }},
        ])
        result = get_security_overview(str(tmp_path))
        assert result["barriers"][0]["event"] == "WorkflowAborted"
        assert result["barriers"][0]["action"] == "warn"

    def test_barrier_includes_step_field(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "gate": 7, "step": "round_2",
            }},
        ])
        result = get_security_overview(str(tmp_path))
        assert result["barriers"][0]["step"] == "round_2"

    def test_owasp_includes_recent_events_per_risk(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "owasp_risk": "A04:Trust",
                "reason": "r1", "issue": 1,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "SecurityTripwireTriggered", "owasp_risk": "A04",
                "reason": "r2",
            }},
        ])
        result = get_security_overview(str(tmp_path))
        a04 = next(r for r in result["owasp"] if r["id"] == "A04")
        assert a04["count"] == 2
        assert isinstance(a04["recent"], list)
        assert len(a04["recent"]) == 2
        assert a04["recent"][0]["event"] == "GateFailed"
        assert a04["recent"][0]["issue"] == 1

    def test_owasp_recent_capped_at_5(self, tmp_path: Path) -> None:
        events = [
            {"ts": f"t{i}", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "owasp_risk": "A07",
            }}
            for i in range(8)
        ]
        _write_audit(tmp_path, events)
        result = get_security_overview(str(tmp_path))
        a07 = next(r for r in result["owasp"] if r["id"] == "A07")
        assert a07["count"] == 8
        assert len(a07["recent"]) == 5

    def test_owasp_overview_uses_classify_fallback_for_unmarked_events(
        self, tmp_path: Path
    ) -> None:
        """Events ohne payload.owasp_risk werden via classify(cat, evt) klassifiziert
        und tragen zum classified_pct + active_risks bei."""
        _write_audit(tmp_path, [
            # 1) PlanCreated → cat="workflow", fallback "uncontrolled_behavior" → A02
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 1,
            }},
            # 2) LLMCallCompleted → cat="llm", fallback "unmonitored_activities" → A06
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "issue": 1,
            }},
            # 3) Explicit GateFailed mit A04 → bleibt A04
            {"ts": "t3", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "owasp_risk": "A04:Trust",
            }},
        ])
        result = get_security_overview(str(tmp_path))
        a02 = next(r for r in result["owasp"] if r["id"] == "A02")
        a06 = next(r for r in result["owasp"] if r["id"] == "A06")
        a04 = next(r for r in result["owasp"] if r["id"] == "A04")
        assert a02["count"] == 1, f"PlanCreated should map to A02, got owasp={result['owasp']}"
        assert a06["count"] == 1
        assert a04["count"] == 1
        # All three events classified
        assert result["classified_pct"] == 100
        assert result["active_risks"] == 3
    def test_maps_provider_to_system_and_model(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted",
                "provider": "deepseek", "model": "deepseek-chat",
                "input_tokens": 100, "output_tokens": 50,
                "latency_ms": 234, "stop_reason": "stop", "task": "planning",
            }},
        ])
        rows = get_otel_gen_ai_calls(str(tmp_path))
        assert len(rows) == 1
        r = rows[0]
        assert r["gen_ai.system"] == "deepseek"
        assert r["gen_ai.request.model"] == "deepseek-chat"
        assert r["gen_ai.usage.input_tokens"] == 100
        assert r["gen_ai.usage.output_tokens"] == 50
        assert r["gen_ai.usage.total_tokens"] == 150
        assert r["gen_ai.client.operation.duration"] == 234
        assert r["gen_ai.response.finish_reasons"] == "stop"
        assert r["task"] == "planning"

    def test_uses_explicit_tokens_field_when_present(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted",
                "provider": "claude", "model": "sonnet",
                "tokens": 999,
            }},
        ])
        rows = get_otel_gen_ai_calls(str(tmp_path))
        assert rows[0]["gen_ai.usage.total_tokens"] == 999

    def test_skips_non_llm_events(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated",
            }},
        ])
        assert get_otel_gen_ai_calls(str(tmp_path)) == []

    def test_newest_first(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "provider": "p1", "model": "m",
            }},
            {"ts": "2026-04-29T11:00", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "provider": "p2", "model": "m",
            }},
        ])
        rows = get_otel_gen_ai_calls(str(tmp_path))
        assert rows[0]["gen_ai.system"] == "p2"
        assert rows[1]["gen_ai.system"] == "p1"


class TestGetTokenHistory:
    def test_returns_chronological_newest_first(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "2026-04-29T10:00", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "provider": "deepseek",
                "model": "deepseek-chat", "task": "planning",
                "input_tokens": 100, "output_tokens": 200, "tokens": 300,
                "cached_tokens": 0, "cost": 0.001, "latency_ms": 500,
                "stop_reason": "stop",
            }},
            {"ts": "2026-04-29T11:00", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "provider": "claude",
                "model": "sonnet", "task": "implement",
                "tokens": 800, "cost": 0.05, "latency_ms": 1200,
            }},
        ])
        rows = get_token_history(str(tmp_path))
        assert len(rows) == 2
        assert rows[0]["timestamp"] == "2026-04-29T11:00"
        assert rows[0]["provider"] == "claude"
        assert rows[1]["provider"] == "deepseek"
        assert rows[1]["input_tokens"] == 100
        assert rows[1]["cost"] == 0.001

    def test_skips_non_llm_events(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {"message_name": "PlanCreated"}},
        ])
        assert get_token_history(str(tmp_path)) == []

    def test_passes_through_phase1_metadata(self, tmp_path: Path) -> None:
        """Phase 3 (#218): guards/tools_loaded/context_sections/prompt_tokens_est
        gehoeren ins LLM-Tab History, damit das Dashboard die Phase-1-Anreicherung
        sichtbar macht."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "provider": "claude",
                "model": "sonnet", "task": "implementation",
                "tokens": 800, "cost": 0.05,
                "guards": ["prompt_guards", "context_validator"],
                "tools_loaded": ["PythonASTBuilder"],
                "context_sections": ["skeleton", "grep", "relevant_files"],
                "prompt_tokens_est": 4200,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "provider": "deepseek",
                "task": "planning", "tokens": 100,
            }},
        ])
        rows = get_token_history(str(tmp_path))
        # Newest first → planning row before implementation row
        assert rows[0]["task"] == "planning"
        # Old row without phase-1 fields gets empty lists / None
        assert rows[0]["guards"] == []
        assert rows[0]["tools_loaded"] == []
        assert rows[0]["prompt_tokens_est"] is None
        # Phase-1-enriched row carries through unchanged
        assert rows[1]["guards"] == ["prompt_guards", "context_validator"]
        assert rows[1]["tools_loaded"] == ["PythonASTBuilder"]
        assert rows[1]["context_sections"] == ["skeleton", "grep", "relevant_files"]
        assert rows[1]["prompt_tokens_est"] == 4200

    def test_limit_applied(self, tmp_path: Path) -> None:
        many = [
            {"ts": f"t{i:02d}", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted", "provider": "p", "model": "m",
            }}
            for i in range(80)
        ]
        _write_audit(tmp_path, many)
        rows = get_token_history(str(tmp_path), limit=20)
        assert len(rows) == 20


class TestGetLLMQualityScores:
    def test_correlates_via_correlation_id(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted",
                "provider": "claude", "model": "sonnet", "task": "implement",
                "correlation_id": "c1",
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "EvalCompleted",
                "score": 0.9, "correlation_id": "c1",
            }},
            {"ts": "t3", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted",
                "provider": "claude", "model": "sonnet", "task": "implement",
                "correlation_id": "c2",
            }},
            {"ts": "t4", "name": "AuditEvent", "payload": {
                "message_name": "EvalFailed",
                "correlation_id": "c2",
            }},
        ])
        rows = get_llm_quality_scores(str(tmp_path))
        assert len(rows) == 1
        r = rows[0]
        assert r["provider"] == "claude"
        assert r["model"] == "sonnet"
        assert r["task"] == "implement"
        assert r["calls"] == 2
        assert r["graded"] == 2
        assert r["passed"] == 1
        assert r["failed"] == 1
        assert r["success_rate_pct"] == 50
        assert r["avg_score"] == 0.9

    def test_calls_without_eval_pair_count_but_dont_grade(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "LLMCallCompleted",
                "provider": "deepseek", "model": "x", "task": "plan",
                "correlation_id": "c-no-eval",
            }},
        ])
        rows = get_llm_quality_scores(str(tmp_path))
        assert len(rows) == 1
        assert rows[0]["calls"] == 1
        assert rows[0]["graded"] == 0
        assert rows[0]["success_rate_pct"] is None

    def test_empty_log_returns_empty_list(self, tmp_path: Path) -> None:
        assert get_llm_quality_scores(str(tmp_path)) == []


class TestGetApiKeyStatus:
    def _write_providers(self, tmp_path: Path, data: dict) -> None:
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        (llm_dir / "providers.json").write_text(json.dumps(data))

    def test_configured_when_env_var_present(self, tmp_path: Path, monkeypatch: Any) -> None:
        self._write_providers(tmp_path, {
            "providers": {"deepseek": {"model": "deepseek-chat", "env_key": "DEEPSEEK_API_KEY"}},
        })
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret")
        rows = get_api_key_status(str(tmp_path))
        assert len(rows) == 1
        assert rows[0]["provider"] == "deepseek"
        assert rows[0]["status"] == "configured"
        assert rows[0]["env_key"] == "DEEPSEEK_API_KEY"

    def test_missing_when_env_var_absent(self, tmp_path: Path, monkeypatch: Any) -> None:
        self._write_providers(tmp_path, {
            "providers": {"claude": {"model": "sonnet", "env_key": "ANTHROPIC_API_KEY"}},
        })
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        rows = get_api_key_status(str(tmp_path))
        assert rows[0]["status"] == "missing"
        assert "set $ANTHROPIC_API_KEY" in rows[0]["note"]

    def test_url_only_for_local_providers(self, tmp_path: Path) -> None:
        self._write_providers(tmp_path, {
            "providers": {"ollama": {"model": "llama3", "url": "http://localhost:11434"}},
        })
        rows = get_api_key_status(str(tmp_path))
        assert rows[0]["status"] == "url_only"
        assert rows[0]["url"] == "http://localhost:11434"

    def test_no_providers_file_returns_empty(self, tmp_path: Path) -> None:
        # No providers.json at all
        assert get_api_key_status(str(tmp_path)) == []


class TestGetLLMRoutingSchedule:
    """#302: Per-task schedule config. Old day_provider/night_provider fields
    were replaced with per-task tasks-list. Premium feature: llm_routing_advanced."""

    def test_disabled_without_premium(self, tmp_path, monkeypatch) -> None:
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "_LICENSE", None)
        s = get_llm_routing_schedule(None, config_dir=str(tmp_path))
        assert s["enabled"] is False
        assert s["tasks"] == []

    def test_enabled_when_premium_advanced_active(self, tmp_path, monkeypatch) -> None:
        from samuel.core import license as _lic
        fake = _lic.License(
            email="x@y", features=frozenset({"llm_routing_advanced"}),
            issued_at="2026-05-05T12:00:00Z",
        )
        monkeypatch.setattr(_lic, "_LICENSE", fake)

        # Build a defaults.json with a schedule
        import json as _json
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "tasks": {
                "implementation": {
                    "provider": "deepseek",
                    "model": "deepseek-coder",
                    "schedule": {
                        "active": True, "from": "22:00", "to": "06:00",
                        "provider": "claude", "model": "claude-opus",
                    },
                },
            },
        }))

        s = get_llm_routing_schedule(None, config_dir=str(tmp_path))
        assert s["enabled"] is True
        assert len(s["tasks"]) == 1
        row = s["tasks"][0]
        assert row["task"] == "implementation"
        assert row["day_provider"] == "deepseek"
        assert row["night_provider"] == "claude"
        assert row["from"] == "22:00"


class TestGetScoreHistory:
    def test_picks_eval_completed_and_failed_only(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "Evaluate",  # skipped
                "score": None,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "EvalCompleted", "score": 0.9,
                "baseline": 0.5, "issue": 1,
            }},
            {"ts": "t3", "name": "AuditEvent", "payload": {
                "message_name": "EvalFailed", "score": 0.1,
                "baseline": 0.5, "reason": "low",
            }},
        ])
        rows = get_score_history(str(tmp_path))
        # newest first
        assert [r["passed"] for r in rows] == [False, True]
        assert rows[0]["score"] == 0.1
        assert rows[0]["reason"] == "low"
        assert rows[1]["score"] == 0.9
        assert rows[1]["issue"] == 1

    def test_limit_applied(self, tmp_path: Path) -> None:
        many = [
            {"ts": f"t{i:03d}", "name": "AuditEvent", "payload": {
                "message_name": "EvalCompleted", "score": float(i),
            }}
            for i in range(20)
        ]
        _write_audit(tmp_path, many)
        rows = get_score_history(str(tmp_path), limit=5)
        assert len(rows) == 5
        # newest first → highest scores
        assert rows[0]["score"] == 19.0


class TestDashboardTestRuns:
    def test_dashboard_test_runs_renders(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "TestRunCompleted", "issue": 246,
                "test_name": "test_alpha", "runner": "pytest",
                "passed": True, "exit_code": 0, "duration_ms": 1200,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "TestRunCompleted", "issue": 246,
                "test_name": "test_beta", "runner": "jest",
                "passed": False, "exit_code": 1, "duration_ms": 800,
            }},
        ])
        d = get_workflow_issue_detail(246, str(tmp_path))
        assert d is not None
        runs = d["test_runs"]
        assert len(runs) == 2
        assert runs[0]["test_name"] == "test_alpha"
        assert runs[0]["runner"] == "pytest"
        assert runs[0]["passed"] is True
        assert runs[1]["test_name"] == "test_beta"
        assert runs[1]["runner"] == "jest"
        assert runs[1]["passed"] is False

    def test_anomaly_on_test_failed(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(minutes=10)).isoformat()
        _write_audit(tmp_path, [
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "TestRunCompleted", "issue": 246,
                "test_name": "ok_test", "passed": True,
            }},
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "TestRunCompleted", "issue": 246,
                "test_name": "broken_test", "passed": False,
            }},
        ])
        rows = get_runtime_anomalies(str(tmp_path))
        events = [r["event"] for r in rows]
        # Failed test must be reported as anomaly
        assert "TestRunCompleted" in events
        # Passed test must NOT be reported (special-case)
        passed_count = sum(
            1 for r in rows if r["event"] == "TestRunCompleted"
        )
        assert passed_count == 1, f"Expected 1 anomaly (failed only), got {passed_count}"

    def test_ai_act_classification_in_audit_trail(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "TestRunCompleted", "issue": 246,
                "evt": "test_failed", "passed": False,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "EvalCompleted", "issue": 246,
                "evt": "eval_run",
            }},
        ])
        d = get_workflow_issue_detail(246, str(tmp_path))
        assert d is not None
        events = d["events"]
        # Each trail entry has an ai_act field
        assert all("ai_act" in e for e in events)
        # eval-category events get an Art. reference
        eval_entries = [e for e in events if e.get("category") == "eval"]
        assert eval_entries, "Expected at least one eval-category entry"
        assert any(e["ai_act"].startswith("Art.") for e in eval_entries), (
            f"Expected Art. mapping, got: {[e['ai_act'] for e in eval_entries]}"
        )


class TestComplianceLegend:
    """#252: OWASP Top-10 Agentic AI + EU AI Act Artikel-Beschreibungen
    sind im Dashboard sichtbar (Compliance-Tab)."""

    def test_legend_returns_owasp_and_ai_act(self) -> None:
        legend = get_compliance_legend()
        assert "owasp" in legend
        assert "ai_act" in legend
        assert isinstance(legend["owasp"], list)
        assert isinstance(legend["ai_act"], list)

    def test_legend_owasp_has_all_top10(self) -> None:
        """Vollständige OWASP-Top-10 mit ID, Name, Key, Beschreibung."""
        legend = get_compliance_legend()
        ids = {entry["id"] for entry in legend["owasp"]}
        assert ids == {f"A{i:02d}" for i in range(1, 11)}, (
            f"Expected A01..A10, got {sorted(ids)}"
        )
        for entry in legend["owasp"]:
            assert entry["name"], f"Missing name for {entry['id']}"
            assert entry["key"], f"Missing risk-key for {entry['id']}"
            assert entry["description"], f"Missing description for {entry['id']}"

    def test_legend_ai_act_articles_have_descriptions(self) -> None:
        legend = get_compliance_legend()
        articles = {entry["article"] for entry in legend["ai_act"]}
        # Mindestens die im Self-Mode-Workflow auftretenden Artikel
        for required in ("Art. 12", "Art. 13", "Art. 14", "Art. 15", "Art. 50"):
            assert required in articles, f"Missing {required}"
        for entry in legend["ai_act"]:
            assert entry["description"], (
                f"Missing description for {entry['article']}"
            )

    def test_legend_keys_match_owasp_risk_map_values(self) -> None:
        """Charter §1.4: jeder Risk-Key in OWASP_RISK_MAP muss in der Legend
        mit Beschreibung erscheinen, sonst sieht der Operator
        unklassifizierte Codes im Dashboard."""
        from samuel.core.owasp import OWASP_RISK_MAP
        legend = get_compliance_legend()
        legend_keys = {entry["key"] for entry in legend["owasp"]}
        # Alle Werte in der Map (außer A0X:2021-Codes von Gates) müssen
        # in der Legend auftauchen
        named_values = {
            v for v in OWASP_RISK_MAP.values() if not v.startswith("A0")
        }
        missing = named_values - legend_keys
        assert not missing, (
            f"Risk-keys in OWASP_RISK_MAP without legend entry: {missing}"
        )

    def test_legend_articles_match_ai_act_map_values(self) -> None:
        """Charter §1.4: jeder Artikel in AI_ACT_ARTICLE_MAP muss
        Beschreibung haben."""
        from samuel.core.ai_act import AI_ACT_ARTICLE_MAP
        legend = get_compliance_legend()
        legend_articles = {entry["article"] for entry in legend["ai_act"]}
        used_articles = set(AI_ACT_ARTICLE_MAP.values())
        missing = used_articles - legend_articles
        assert not missing, (
            f"Articles in AI_ACT_ARTICLE_MAP without legend entry: {missing}"
        )


class TestPlanContext:
    """#237: PlanContextLoaded-Events fliessen in
    workflow_issue_detail.plan_context."""

    def test_plan_context_in_dashboard_detail(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "PlanContextLoaded", "issue": 237,
                "evt": "plan_context_load",
                "skeleton_tokens": 1500,
                "relevant_files_count": 5,
                "grep_hits": 12,
                "total_context_tokens": 4200,
            }},
        ])
        d = get_workflow_issue_detail(237, str(tmp_path))
        assert d is not None
        ctx = d["plan_context"]
        assert ctx["skeleton_tokens"] == 1500
        assert ctx["relevant_files_count"] == 5
        assert ctx["grep_hits"] == 12
        assert ctx["total_context_tokens"] == 4200


class TestPlanPreCheck238:
    """#238: PlanPreCheckCompleted + PlanComplexityWarn fliessen in
    workflow_issue_detail.pre_check und workflow_issue_detail.complexity."""

    def test_pre_check_event_in_dashboard(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "PlanPreCheckCompleted", "issue": 238,
                "evt": "plan_pre_check",
                "structural_score": 100,
                "skeleton_score": 100,
                "ac_dry_run_score": 80,
                "overall_pass": True,
                "retry_attempt": 0,
                "blocking_failures": [],
                "complexity": {
                    "ac_count": 5, "file_count": 3, "slice_count": 2,
                    "pflicht_bereich_count": 3, "recommendation": "ok",
                },
            }},
        ])
        d = get_workflow_issue_detail(238, str(tmp_path))
        assert d is not None
        pc = d["pre_check"]
        assert pc["structural"] == 100
        assert pc["skeleton"] == 100
        assert pc["ac_dry_run"] == 80
        assert pc["overall_pass"] is True
        cx = d["complexity"]
        assert cx["ac_count"] == 5
        assert cx["recommendation"] == "ok"

    def test_complexity_warn_anomaly(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": datetime.now(timezone.utc).isoformat(), "name": "AuditEvent",
             "payload": {
                "message_name": "PlanComplexityWarn", "issue": 238,
                "evt": "complexity_warn",
                "ac_count": 12, "file_count": 8, "slice_count": 6,
                "pflicht_bereich_count": 5, "recommendation": "split_recommended",
            }},
        ])
        rows = get_runtime_anomalies(str(tmp_path), hours=24)
        assert any(r["event"] == "PlanComplexityWarn" for r in rows)


class TestAcceptanceChecks:
    """#236: ACVerified/ACFailed-Events erscheinen im Dashboard
    workflow-issue-detail.acceptance_checks-Slot."""

    def test_acceptance_checks_in_workflow_detail(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "ACVerified", "issue": 236,
                "tag": "DIFF", "arg": "handler.py", "passed": True,
                "reason": "exists: handler.py",
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "ACFailed", "issue": 236,
                "tag": "DIFF", "arg": "missing.py", "passed": False,
                "reason": "not found: missing.py",
            }},
        ])
        d = get_workflow_issue_detail(236, str(tmp_path))
        assert d is not None
        checks = d["acceptance_checks"]
        assert len(checks) == 2
        passed_check = next(c for c in checks if c["tag"] == "DIFF" and c["arg"] == "handler.py")
        assert passed_check["passed"] is True
        failed_check = next(c for c in checks if c["arg"] == "missing.py")
        assert failed_check["passed"] is False
        assert "not found" in failed_check["reason"]


class TestAcceptanceChecks:
    """#236: ACVerified/ACFailed-Events erscheinen im Dashboard
    workflow-issue-detail.acceptance_checks-Slot."""

    def test_acceptance_checks_in_workflow_detail(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "ACVerified", "issue": 236,
                "tag": "DIFF", "arg": "handler.py", "passed": True,
                "reason": "exists: handler.py",
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "ACFailed", "issue": 236,
                "tag": "DIFF", "arg": "missing.py", "passed": False,
                "reason": "not found: missing.py",
            }},
        ])
        d = get_workflow_issue_detail(236, str(tmp_path))
        assert d is not None
        checks = d["acceptance_checks"]
        assert len(checks) == 2
        passed_check = next(c for c in checks if c["tag"] == "DIFF" and c["arg"] == "handler.py")
        assert passed_check["passed"] is True
        failed_check = next(c for c in checks if c["arg"] == "missing.py")
        assert failed_check["passed"] is False
        assert "not found" in failed_check["reason"]


class TestOwaspClassification:
    def test_owasp_classification_in_audit_trail(self, tmp_path: Path) -> None:
        """Events ohne payload.owasp_risk bekommen OWASP via classify(cat, evt)."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "TestRunCompleted", "issue": 251,
                "evt": "test_failed", "passed": False,
            }},
            {"ts": "t2", "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated", "issue": 251,
            }},
        ])
        d = get_workflow_issue_detail(251, str(tmp_path))
        assert d is not None
        events = d["events"]
        owasps = [e["owasp"] for e in events]
        # Both entries get a non-empty OWASP via classify fallback
        assert all(o != "" for o in owasps), f"Empty OWASP found: {owasps}"
        # eval/test_failed maps to inadequate_feedback_loops
        eval_e = next((e for e in events if e["event"] == "TestRunCompleted"), None)
        assert eval_e is not None
        assert eval_e["owasp"] == "inadequate_feedback_loops"

    def test_owasp_passes_payload_value_when_set(self, tmp_path: Path) -> None:
        """Wenn payload.owasp_risk gesetzt ist, hat es Vorrang vor classify."""
        _write_audit(tmp_path, [
            {"ts": "t1", "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "issue": 252,
                "owasp_risk": "A05:2021",
                "gate": 8,
            }},
        ])
        d = get_workflow_issue_detail(252, str(tmp_path))
        assert d is not None
        events = d["events"]
        assert len(events) == 1
        # payload value preserved, not overwritten by classify
        assert events[0]["owasp"] == "A05:2021"


class TestGetRuntimeAnomalies:
    def test_filters_to_warn_and_error_only(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=1)).isoformat()
        _write_audit(tmp_path, [
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated",  # info → skip
            }},
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "reason": "x",
            }},
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "EvalFailed", "reason": "y",
            }},
        ])
        rows = get_runtime_anomalies(str(tmp_path))
        levels = [r["level"] for r in rows]
        assert "error" in levels
        assert "warn" in levels
        events = [r["event"] for r in rows]
        assert "PlanCreated" not in events

    def test_skips_events_older_than_hours_window(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        old = (now - timedelta(hours=48)).isoformat()
        recent = (now - timedelta(minutes=30)).isoformat()
        _write_audit(tmp_path, [
            {"ts": old, "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "reason": "old gate",
            }},
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "GateFailed", "reason": "fresh gate",
            }},
        ])
        rows = get_runtime_anomalies(str(tmp_path), hours=24)
        reasons = [r["message"] for r in rows]
        assert any("fresh gate" in m for m in reasons)
        assert not any("old gate" in m for m in reasons)


class TestGetSystemTiles:
    def test_scm_tile_reflects_adapter_presence(self, tmp_path: Path) -> None:
        tiles = get_system_tiles(str(tmp_path), config=None, scm=None)
        scm = next(t for t in tiles if t["key"] == "scm")
        assert scm["kind"] == "err"
        tiles = get_system_tiles(str(tmp_path), config=None, scm=object())
        scm = next(t for t in tiles if t["key"] == "scm")
        assert scm["kind"] == "ok"

    def test_llm_tile_reads_provider_and_model_from_config(self, tmp_path: Path) -> None:
        cfg = _Cfg({
            "llm.default.provider": "deepseek",
            "llm.deepseek.model": "deepseek-chat",
        })
        tiles = get_system_tiles(str(tmp_path), config=cfg, scm=None)
        llm = next(t for t in tiles if t["key"] == "llm")
        assert llm["value"] == "deepseek"
        assert llm["detail"] == "deepseek-chat"
        assert llm["kind"] == "ok"

    def test_disk_tile_present_with_used_pct(self, tmp_path: Path) -> None:
        tiles = get_system_tiles(str(tmp_path))
        disk = next(t for t in tiles if t["key"] == "disk")
        assert "used" in disk["detail"] or "stat failed" in disk["detail"]

    def test_eval_tile_uses_latest_eval_event(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "t", "name": "AuditEvent", "payload": {
                "message_name": "EvalCompleted", "score": 0.8, "baseline": 0.5,
            }},
        ])
        tiles = get_system_tiles(str(tmp_path))
        ev = next(t for t in tiles if t["key"] == "eval")
        assert ev["kind"] == "ok"
        assert "0.8" in ev["value"] and "0.5" in ev["value"]

    def test_errors_24h_tile_counts_recent_errors(self, tmp_path: Path) -> None:
        recent = datetime.now(timezone.utc).isoformat()
        _write_audit(tmp_path, [
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "GateFailed",
            }},
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "WorkflowAborted",
            }},
            {"ts": recent, "name": "AuditEvent", "payload": {
                "message_name": "PlanCreated",  # not an error
            }},
        ])
        tiles = get_system_tiles(str(tmp_path))
        errs = next(t for t in tiles if t["key"] == "errors_24h")
        assert errs["value"] == "2"


# #211: validation cache tests
class TestApiKeyValidationCache:
    def test_validation_cache_hits_within_ttl(self, monkeypatch):
        from samuel.slices.dashboard import data as _d
        _d._VALIDATION_CACHE.clear()

        calls = {"n": 0}
        class Mock:
            def validate(self):
                calls["n"] += 1
                return {"valid": True, "detail": "ok", "balance": None}
        a = Mock()

        r1 = _d._cached_validate("provX", a)
        r2 = _d._cached_validate("provX", a)
        assert r1 == r2
        assert calls["n"] == 1  # cache hit on second call

    def test_validation_cache_expires_after_ttl(self, monkeypatch):
        from samuel.slices.dashboard import data as _d
        _d._VALIDATION_CACHE.clear()

        calls = {"n": 0}
        class Mock:
            def validate(self):
                calls["n"] += 1
                return {"valid": True, "detail": "ok", "balance": None}
        a = Mock()

        # First call populates cache
        _d._cached_validate("provY", a)
        # Move time forward beyond TTL
        ts0 = _d._VALIDATION_CACHE["provY"][0]
        _d._VALIDATION_CACHE["provY"] = (ts0 - _d._VALIDATION_TTL_SECONDS - 1, _d._VALIDATION_CACHE["provY"][1])
        # Second call should refresh
        _d._cached_validate("provY", a)
        assert calls["n"] == 2

    def test_validation_cache_catches_exceptions(self):
        from samuel.slices.dashboard import data as _d
        _d._VALIDATION_CACHE.clear()
        class Boom:
            def validate(self):
                raise RuntimeError("boom")
        res = _d._cached_validate("provZ", Boom())
        assert res["valid"] is False
        assert "validate() raised" in res["detail"]

    def test_validation_cache_skips_when_no_validate_method(self):
        from samuel.slices.dashboard import data as _d
        _d._VALIDATION_CACHE.clear()
        class NoValidate:
            pass
        res = _d._cached_validate("provN", NoValidate())
        assert res["valid"] is False
        assert "not implemented" in res["detail"]


def _evt(ts: str, name: str, issue: int, corr: str, **extra: Any) -> dict:
    """Build a single audit-event row in the shape used on disk."""
    return {
        "ts": ts,
        "name": "AuditEvent",
        "payload": {
            "message_name": name,
            "issue": issue,
            "correlation_id": corr,
            **extra,
        },
    }


class TestWorkflowRuns:
    """#277: get_workflow_runs groups events by correlation_id."""

    def test_groups_by_correlation_id(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            # Run A — failed (GateFailed)
            _evt("2026-05-01T09:12", "IssueReady",   42, "run-A"),
            _evt("2026-05-01T09:13", "PlanCreated",  42, "run-A"),
            _evt("2026-05-01T09:18", "GateFailed",   42, "run-A",
                 gate=1, reason="branch is main"),
            # Run B — succeeded
            _evt("2026-05-01T14:22", "IssueReady",   42, "run-B"),
            _evt("2026-05-01T14:25", "PlanCreated",  42, "run-B"),
            _evt("2026-05-01T14:28", "EvalCompleted", 42, "run-B", score=1.0),
            _evt("2026-05-01T14:29", "PRCreated",    42, "run-B", pr_number=275),
        ])

        runs = get_workflow_runs(42, str(tmp_path))

        assert len(runs) == 2
        # chronological: run-A (failed) before run-B (passed)
        assert runs[0]["run_id"] == "run-A"
        assert runs[0]["final_status"] == "blocked"
        assert runs[0]["pr_number"] is None
        assert len(runs[0]["gate_failures"]) == 1
        assert runs[1]["run_id"] == "run-B"
        assert runs[1]["final_status"] == "pr_created"
        assert runs[1]["pr_number"] == 275
        assert runs[1]["score"] == 1.0

    def test_score_per_run(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "EvalFailed", 42, "run-A", score=0.4),
            _evt("2026-05-01T10:00", "EvalCompleted", 42, "run-B", score=0.9),
        ])

        runs = get_workflow_runs(42, str(tmp_path))

        assert {r["run_id"]: r["score"] for r in runs} == {
            "run-A": 0.4, "run-B": 0.9,
        }

    def test_pr_number_attribution(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "PRCreated", 42, "run-A", pr_number=100),
            _evt("2026-05-01T10:00", "PRCreated", 42, "run-B", pr_number=200),
        ])

        runs = get_workflow_runs(42, str(tmp_path))

        # PR is attributed to its own run, not bled across.
        assert {r["run_id"]: r["pr_number"] for r in runs} == {
            "run-A": 100, "run-B": 200,
        }

    def test_event_without_correlation_id_dropped(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            {"ts": "x", "name": "AuditEvent",
             "payload": {"message_name": "PRCreated", "issue": 42}},
            _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
        ])

        runs = get_workflow_runs(42, str(tmp_path))

        assert len(runs) == 1
        assert runs[0]["run_id"] == "run-A"

    def test_other_issues_not_included(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
            _evt("2026-05-01T09:00", "PRCreated", 99, "run-X"),
        ])

        runs = get_workflow_runs(42, str(tmp_path))

        assert [r["run_id"] for r in runs] == ["run-A"]

    def test_empty_when_no_events(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [])
        assert get_workflow_runs(42, str(tmp_path)) == []


class TestRecoveryTrendDetection:
    """#277: trend recovered/regressed is derived from the last two runs."""

    def test_failed_then_passed_is_recovered(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "GateFailed", 42, "run-A"),
            _evt("2026-05-01T10:00", "PRCreated",  42, "run-B"),
        ])
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert detail["trend"] == "recovered"

    def test_passed_then_failed_is_regressed(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "PRCreated",  42, "run-A"),
            _evt("2026-05-01T10:00", "GateFailed", 42, "run-B"),
        ])
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail["trend"] == "regressed"

    def test_passed_passed_is_passed(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
            _evt("2026-05-01T10:00", "PRCreated", 42, "run-B"),
        ])
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail["trend"] == "passed"

    def test_failed_failed_is_failed(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "GateFailed", 42, "run-A"),
            _evt("2026-05-01T10:00", "GateFailed", 42, "run-B"),
        ])
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail["trend"] == "failed"

    def test_single_run_has_no_trend(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
        ])
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail["trend"] == ""


class TestWorkflowIssueDetailIncludesRunsSlot:
    """#277-AC: detail dict carries the runs[] aggregate."""

    def test_runs_slot_present(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "PRCreated", 42, "run-A", pr_number=10),
        ])
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert "runs" in detail
        assert len(detail["runs"]) == 1
        assert detail["runs"][0]["pr_number"] == 10
        assert "trend" in detail


class TestWorkflowIssuesIncludesRunsCount:
    """#277: Workflow-Tab listet runs_count + trend pro Issue."""

    def test_runs_count_matches_distinct_correlation_ids(
        self, tmp_path: Path,
    ) -> None:
        _write_audit(tmp_path, [
            _evt("2026-05-01T09:00", "GateFailed", 42, "run-A"),
            _evt("2026-05-01T10:00", "PRCreated",  42, "run-B"),
            _evt("2026-05-01T10:00", "PRCreated",  99, "run-X"),
        ])
        rows = get_workflow_issues(str(tmp_path))
        by_num = {r["number"]: r for r in rows}
        assert by_num[42]["runs_count"] == 2
        assert by_num[42]["trend"] == "recovered"
        assert by_num[99]["runs_count"] == 1
        assert by_num[99]["trend"] == ""
