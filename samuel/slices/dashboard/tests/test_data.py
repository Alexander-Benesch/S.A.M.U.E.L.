"""Tests for the new Phase 14.6 data-layer helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from samuel.core.ports import IConfig
from samuel.slices.dashboard.data import (
    build_quality_heatmap,
    get_api_key_status,
    get_command_metrics,
    get_compliance_legend,
    get_llm_quality_scores,
    get_llm_routing,
    get_llm_routing_schedule,
    get_llm_usage,
    get_log_entries,
    get_log_level_counts,
    get_otel_gen_ai_calls,
    get_problems,
    get_quality_from_log,
    get_quality_overview,
    get_runtime_anomalies,
    get_scm_activity,
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


def test_workflow_detail_exposes_tri_state_gate_results(tmp_path: Path) -> None:
    _write_audit(
        tmp_path,
        [
            {
                "ts": "2026-08-29T12:00:00Z",
                "name": "AuditEvent",
                "payload": {
                    "message_name": "GateEvaluationCompleted",
                    "issue": 620,
                    "correlation_id": "preflight-run",
                    "blocked": True,
                    "gate_results": [
                        {
                            "gate": "7b",
                            "passed": False,
                            "executed": True,
                            "status": "failed",
                            "authority": "required",
                            "phase": "preflight",
                            "reason": "scope violation",
                        },
                        {
                            "gate": 11,
                            "passed": None,
                            "executed": False,
                            "status": "skipped_precondition",
                            "authority": "required",
                            "phase": "post_candidate",
                            "reason": "preflight failed",
                        },
                    ],
                },
            }
        ],
    )

    detail = get_workflow_issue_detail(620, str(tmp_path))

    assert detail is not None
    assert [item["status"] for item in detail["gate_results"]] == [
        "failed",
        "skipped_precondition",
    ]
    assert detail["gate_results"][1]["passed"] is None
    assert detail["stages"]["gates"]["reason"] == "scope violation"


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
        cfg = _Cfg(
            {
                "llm.default.provider": "deepseek",
                "llm.default.model": "deepseek-chat",
                "llm.tasks.planning.provider": "claude",
                "llm.tasks.planning.model": "claude-sonnet-4-6",
                "llm.tasks.review.provider": "ollama",
            }
        )
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
        (llm_dir / "defaults.json").write_text(
            json.dumps(
                {
                    "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
                    "tasks": {
                        "implement": {"max_tokens": 8192, "temperature": 0.1},
                        "eval": {"max_tokens": 2048, "temperature": 0.0},
                    },
                }
            )
        )
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
        self,
        tmp_path: Path,
    ) -> None:
        """#338-audit: every persisted task field must round-trip through
        get_llm_routing — otherwise the LLM-Editor reload appears to drop
        the user's saved values (system_prompt was the missing one)."""
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(
            json.dumps(
                {
                    "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
                    "tasks": {
                        "review": {
                            "provider": "deepseek",
                            "model": "deepseek-chat",
                            "base_url": "https://api.deepseek.com",
                            "system_prompt": "reviewer.md",
                            "timeout": 180,
                            "schedule": {
                                "active": True,
                                "from": "22:00",
                                "to": "06:00",
                                "provider": "ollama",
                                "model": "llama3",
                            },
                        },
                    },
                }
            )
        )
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        review = next(r for r in rows if r["task"] == "review")
        assert review["system_prompt"] == "reviewer.md"
        assert review["base_url"] == "https://api.deepseek.com"
        assert review["timeout"] == 180  # task-specific, not the base 60
        assert review["schedule"]["active"] is True
        assert review["schedule"]["provider"] == "ollama"

    def test_saved_provider_and_model_override_bootstrap_default(self, tmp_path: Path) -> None:
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "planning": {
                            "provider": "openrouter",
                            "model": "nvidia/nemotron-test",
                        }
                    }
                }
            )
        )
        cfg = _Cfg(
            {
                "llm.default.provider": "deepseek",
                "llm.default.model": "deepseek-chat",
            }
        )

        planning = next(
            row
            for row in get_llm_routing(cfg, config_dir=str(tmp_path))
            if row["task"] == "planning"
        )

        assert planning["provider"] == "openrouter"
        assert planning["model"] == "nvidia/nemotron-test"

    def test_routing_row_defaults_empty_strings_when_field_absent(
        self,
        tmp_path: Path,
    ) -> None:
        """When a task has no system_prompt configured, the row reports an
        empty string (so the frontend dropdown can default to '(none)')."""
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {"planning": {"provider": "ollama", "model": "x"}},
                }
            )
        )
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
                checks.append((base / "model" / str(model) / effective, f"operator-model:{model}"))
            if provider:
                checks.append(
                    (base / "provider" / str(provider) / effective, f"operator-provider:{provider}")
                )
            checks.append((base / effective, "operator-generic"))
            for p, label in checks:
                if p.is_file():
                    return {"source": label, "path": str(p), "mtime": 1.0}
            return {"source": "package", "path": f"/pkg/{effective}", "mtime": 1.0}

        return _resolve

    def test_routing_row_includes_system_prompt_source(
        self,
        tmp_path: Path,
    ) -> None:
        """#348: row carries which cascade-layer the active prompt comes
        from, so the editor can show "[package]" / "[operator-...]"."""
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True)
        (llm_dir / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "planning": {
                            "provider": "deepseek",
                            "model": "deepseek-chat",
                            "system_prompt": "planner.md",
                        },
                        # No system_prompt configured -> source must report "none"
                        "review": {"provider": "ollama", "model": "llama3"},
                    },
                }
            )
        )
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(
            cfg,
            config_dir=str(tmp_path),
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
            "source": "none",
            "path": "",
            "mtime": 0.0,
        }

    def test_system_prompt_source_picks_provider_override_when_available(
        self,
        tmp_path: Path,
    ) -> None:
        """When a per-provider override file exists, the row reports
        operator-provider:<name> as the active source."""
        prov_dir = tmp_path / "llm" / "prompts" / "provider" / "deepseek"
        prov_dir.mkdir(parents=True)
        (prov_dir / "planner.md").write_text("DEEPSEEK PLANNER", encoding="utf-8")
        (tmp_path / "llm" / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "planning": {
                            "provider": "deepseek",
                            "model": "deepseek-chat",
                            "system_prompt": "planner.md",
                        },
                    },
                }
            )
        )
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(
            cfg,
            config_dir=str(tmp_path),
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
        self,
        tmp_path: Path,
    ) -> None:
        """Without an injected resolver (slice-iso fallback), row still
        carries the slot but reports source=none."""
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "planning": {
                            "provider": "ollama",
                            "model": "llama3",
                            "system_prompt": "planner.md",
                        },
                    },
                }
            )
        )
        cfg = _Cfg({"llm.default.provider": "ollama"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        plan = next(r for r in rows if r["task"] == "planning")
        assert plan["system_prompt_source"]["source"] == "none"

    def test_routing_row_carries_system_prompt_by_provider(
        self,
        tmp_path: Path,
    ) -> None:
        """#351: per-provider override map round-trips through the row so
        the editor can render and re-save it."""
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "planning": {
                            "provider": "deepseek",
                            "model": "deepseek-chat",
                            "system_prompt": "planner.md",
                            "system_prompt_by_provider": {
                                "deepseek": "planner_local.md",
                                "claude": "planner_kompakt.md",
                            },
                        },
                    },
                }
            )
        )
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        plan = next(r for r in rows if r["task"] == "planning")
        assert plan["system_prompt_by_provider"] == {
            "deepseek": "planner_local.md",
            "claude": "planner_kompakt.md",
        }

    def test_routing_row_source_reflects_by_provider_override(
        self,
        tmp_path: Path,
    ) -> None:
        """#351 + #348: when the active provider has an entry, the source-
        indicator must point to that file (not to the task default)."""
        prompts_dir = tmp_path / "llm" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "planner_local.md").write_text(
            "LOCAL",
            encoding="utf-8",
        )
        (tmp_path / "llm" / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "planning": {
                            "provider": "deepseek",
                            "model": "deepseek-chat",
                            "system_prompt": "planner.md",
                            "system_prompt_by_provider": {
                                "deepseek": "planner_local.md",
                            },
                        },
                    },
                }
            )
        )
        cfg = _Cfg({"llm.default.provider": "deepseek"})
        rows = get_llm_routing(
            cfg,
            config_dir=str(tmp_path),
            prompt_source_resolver=self._file_based_resolver(prompts_dir),
        )
        plan = next(r for r in rows if r["task"] == "planning")
        # Source points at the by_provider override file, not the default.
        assert plan["system_prompt_source"]["source"] == "operator-generic"
        assert plan["system_prompt_source"]["path"].endswith("planner_local.md")

    def test_routing_row_empty_by_provider_when_field_absent(
        self,
        tmp_path: Path,
    ) -> None:
        """Default for missing field is empty dict, not None — frontend
        can iterate over it without null-check."""
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "review": {"provider": "ollama", "model": "llama3"},
                    },
                }
            )
        )
        cfg = _Cfg({"llm.default.provider": "ollama"})
        rows = get_llm_routing(cfg, config_dir=str(tmp_path))
        rev = next(r for r in rows if r["task"] == "review")
        assert rev["system_prompt_by_provider"] == {}

    def test_reasoning_reserve_and_benchmark_quality_are_explicit(self, tmp_path: Path) -> None:
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(
            json.dumps(
                {
                    "default": {"max_tokens": 4096, "reasoning_reserve": 0},
                    "benchmark_thresholds": {"default": 50, "planning": 70},
                    "tasks": {
                        "planning": {
                            "provider": "openrouter",
                            "model": "vendor/reasoner",
                            "reasoning_reserve": 2048,
                            "cost_advisory_enabled": True,
                            "overqualification_margin_ratio": 0.2,
                        }
                    },
                }
            )
        )
        calls = []

        def resolver(model: str, task: str, threshold: float, margin: float) -> dict:
            calls.append((model, task, threshold, margin))
            return {
                "reasoning": {"is_reasoning": True, "source": "openrouter_metadata"},
                "suitability": {
                    "available": False,
                    "status": "no_data",
                    "index": "intelligence_index",
                    "score": None,
                    "threshold": threshold,
                },
            }

        rows = get_llm_routing(
            _Cfg({"llm.default.provider": "openrouter"}),
            config_dir=str(tmp_path),
            model_quality_resolver=resolver,
        )

        plan = rows[0]
        assert plan["reasoning_reserve"] == 2048
        assert plan["model_quality"]["suitability"]["status"] == "no_data"
        assert plan["reasoning_guidance"]["mode"] == "explicit_max_tokens"
        assert plan["reasoning_guidance"]["effective_max_tokens"] == 6144
        assert plan["reasoning_guidance"]["configuration_source"] == "task_override"
        assert plan["reasoning_guidance"]["recommendation"]
        assert plan["cost_advisory_enabled"] is True
        assert plan["overqualification_margin_ratio"] == 0.2
        assert calls == [("vendor/reasoner", "planning", 70.0, 0.2)]

    def test_zero_reserve_means_provider_default_not_reasoning_disabled(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "llm").mkdir(parents=True)
        (tmp_path / "llm" / "defaults.json").write_text(
            json.dumps(
                {
                    "default": {"max_tokens": 4096, "reasoning_reserve": 0},
                    "tasks": {"planning": {"provider": "openrouter", "model": "vendor/r"}},
                }
            )
        )

        rows = get_llm_routing(
            _Cfg({"llm.default.provider": "openrouter"}),
            config_dir=str(tmp_path),
            model_quality_resolver=lambda *_: {
                "reasoning": {
                    "is_reasoning": True,
                    "source": "openrouter_supported_parameters",
                    "metadata": {"default_enabled": True},
                },
                "suitability": {},
            },
        )

        guidance = rows[0]["reasoning_guidance"]
        assert guidance["mode"] == "provider_default"
        assert "nicht deaktiviert" in guidance["semantics"]
        assert guidance["configuration_source"] == "inherited_default"


def test_llm_usage_surfaces_truncations_with_issue_context(tmp_path: Path) -> None:
    _write_audit(
        tmp_path,
        [
            {
                "ts": "2026-08-21T10:00:00Z",
                "payload": {
                    "message_name": "LLMCallCompleted",
                    "task": "planning",
                    "provider": "openrouter",
                    "model": "vendor/reasoner",
                    "issue": 427,
                    "stop_reason": "length",
                    "tokens": 5000,
                    "content_max_tokens": 4096,
                    "reasoning_reserve": 1024,
                },
            }
        ],
    )

    usage = get_llm_usage(str(tmp_path))

    assert usage["truncations"] == [
        {
            "timestamp": "2026-08-21T10:00:00Z",
            "task": "planning",
            "provider": "openrouter",
            "model": "vendor/reasoner",
            "issue": 427,
            "stop_reason": "length",
            "content_max_tokens": 4096,
            "reasoning_reserve": 1024,
        }
    ]


class TestGetTamperEvents:
    def test_tamper_message_names_detected(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {"ts": "2026-04-17T10:00", "name": "x", "payload": {"message_name": "PlanCreated"}},
                {
                    "ts": "2026-04-17T10:01",
                    "name": "x",
                    "payload": {"message_name": "TamperDetected", "reason": "bad"},
                },
                {
                    "ts": "2026-04-17T10:02",
                    "name": "x",
                    "payload": {"message_name": "UnauthorizedChange"},
                },
                {
                    "ts": "2026-04-17T10:03",
                    "name": "x",
                    "payload": {"message_name": "IntegrityViolation"},
                },
            ],
        )
        events = get_tamper_events(str(tmp_path))
        names = [e["event"] for e in events]
        # Newest first
        assert names == ["IntegrityViolation", "UnauthorizedChange", "TamperDetected"]
        assert events[2]["detail"] == "bad"
        assert events[2]["classification"] == "external_signature"
        assert events[2]["level"] == "error"
        assert events[2]["component"] == "webhook"
        assert events[0]["classification"] == "internal_integrity"
        assert events[0]["summary"] == "Interne Integritätsprüfung fehlgeschlagen"
        assert events[0]["impact"]
        assert events[0]["remediation"]

    def test_security_event_has_same_error_baseline_in_logs_and_problems(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "IntegrityViolation",
                        "level": "info",
                        "reason": "audit chain mismatch",
                        "correlation_id": "integrity-run",
                    },
                }
            ],
        )

        assert get_log_level_counts(str(tmp_path))["error"] == 1
        problems = get_problems(str(tmp_path))
        assert len(problems) == 1
        assert problems[0]["level"] == "error"
        tamper = get_tamper_events(str(tmp_path))
        assert tamper[0]["level"] == "error"
        assert tamper[0]["run"] == "integrity-run"

    def test_supply_chain_matched_via_owasp(self, tmp_path: Path) -> None:
        """#290: ASI04 agentic_supply_chain ist die neue Tamper-Klassifikation."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "x",
                    "payload": {"message_name": "Whatever", "owasp_risk": "agentic_supply_chain"},
                },
            ],
        )
        events = get_tamper_events(str(tmp_path))
        assert len(events) == 1
        assert events[0]["owasp"] == "agentic_supply_chain"

    def test_legacy_broken_trust_boundaries_still_matched(self, tmp_path: Path) -> None:
        """#290: alte Audit-Logs mit ``broken_trust_boundaries`` weiter als
        Tamper erkannt (Backward-Compat fuer historische Daten)."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "x",
                    "payload": {
                        "message_name": "Whatever",
                        "owasp_risk": "broken_trust_boundaries",
                    },
                },
            ],
        )
        events = get_tamper_events(str(tmp_path))
        assert len(events) == 1
        assert events[0]["owasp"] == "broken_trust_boundaries"

    def test_empty_when_no_matches(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {"ts": "t", "name": "x", "payload": {"message_name": "PlanCreated"}},
            ],
        )
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
        (log_dir / "agent_2026-04-15.jsonl").write_text(json.dumps({"name": "Old"}) + "\n")
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
        (log_dir / "agent.jsonl").write_text("not json\n" + json.dumps({"name": "OK"}) + "\n")
        events = load_audit_events(str(tmp_path))
        assert [e["name"] for e in events] == ["OK"]


class TestGetCommandMetrics:
    def test_aggregates_counts_and_total_ms_per_command(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "PlanIssueCommand",
                        "message_name": "PlanIssue",
                        "duration_ms": 12.5,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "PlanIssueCommand",
                        "message_name": "PlanIssue",
                        "duration_ms": 7.5,
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "ImplementCommand",
                        "message_name": "Implement",
                        "duration_ms": 100.0,
                    },
                },
            ],
        )
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["counts"] == {"PlanIssue": 2, "Implement": 1}
        assert metrics["total_ms"] == {"PlanIssue": 20.0, "Implement": 100.0}
        assert metrics["errors"] == {}

    def test_skips_event_messages(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "PlanCreated",  # not a Command
                        "message_name": "PlanCreated",
                    },
                },
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "PlanIssueCommand",
                        "message_name": "PlanIssue",
                        "duration_ms": 1.0,
                    },
                },
            ],
        )
        metrics = get_command_metrics(str(tmp_path))
        assert "PlanCreated" not in metrics["counts"]
        assert metrics["counts"] == {"PlanIssue": 1}

    def test_attributes_workflow_aborted_to_source_command(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "ImplementCommand",
                        "message_name": "Implement",
                        "duration_ms": 5.0,
                    },
                },
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "WorkflowAborted",
                        "message_name": "WorkflowAborted",
                        "source_command": "Implement",
                        "reason": "gate failed",
                    },
                },
            ],
        )
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["counts"] == {"Implement": 1}
        assert metrics["errors"] == {"Implement": 1}

    def test_handles_missing_duration_gracefully(self, tmp_path: Path) -> None:
        # Old-format audit lines without duration_ms still count toward
        # 'counts' but contribute nothing to total_ms.
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "PlanIssueCommand",
                        "message_name": "PlanIssue",
                    },
                },
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "PlanIssueCommand",
                        "message_name": "PlanIssue",
                        "duration_ms": 4.0,
                    },
                },
            ],
        )
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["counts"] == {"PlanIssue": 2}
        assert metrics["total_ms"] == {"PlanIssue": 4.0}

    def test_empty_log_returns_empty_dicts(self, tmp_path: Path) -> None:
        metrics = get_command_metrics(str(tmp_path))
        assert metrics == {"counts": {}, "errors": {}, "total_ms": {}}

    def test_error_field_in_command_audit_counts_as_error(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_type": "EvaluateCommand",
                        "message_name": "Evaluate",
                        "duration_ms": 2.0,
                        "error": "RuntimeError",
                    },
                },
            ],
        )
        metrics = get_command_metrics(str(tmp_path))
        assert metrics["errors"] == {"Evaluate": 1}


class TestGetLogEntriesShape:
    def test_entries_use_timestamp_field(self, tmp_path: Path) -> None:
        # Frontend expects ``timestamp`` (not ``ts``) — see server.py:361
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 5,
                    },
                },
            ],
        )
        entries = get_log_entries(str(tmp_path))
        assert len(entries) == 1
        assert entries[0]["timestamp"] == "2026-04-29T10:00"
        assert "ts" not in entries[0]

    def test_entries_include_full_payload_as_meta(self, tmp_path: Path) -> None:
        # Issue #203: ▼-toggle row needs full payload to show provider/model/tokens/cost
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "tokens_used": 4096,
                        "cost": 0.012,
                    },
                },
            ],
        )
        entries = get_log_entries(str(tmp_path))
        meta = entries[0]["meta"]
        assert meta["provider"] == "deepseek"
        assert meta["model"] == "deepseek-chat"
        assert meta["tokens_used"] == 4096
        assert meta["cost"] == 0.012

    def test_entries_meta_is_independent_copy(self, tmp_path: Path) -> None:
        # Mutating meta on one entry must not bleed into the underlying audit data
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 5,
                    },
                },
            ],
        )
        entries = get_log_entries(str(tmp_path))
        entries[0]["meta"]["mutated"] = True
        entries2 = get_log_entries(str(tmp_path))
        assert "mutated" not in entries2[0]["meta"]

    def test_resolved_at_annotation_from_payload_prev_timestamp(self, tmp_path: Path) -> None:
        # AuditHandler-style record: prev_timestamp at top level of payload
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "self_check_fatal",
                        "reason": "config missing",
                    },
                },
                {
                    "ts": "2026-04-29T10:05:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "self_check_resolved",
                        "prev_timestamp": "2026-04-29T10:00:00",
                    },
                },
            ],
        )
        entries = get_log_entries(str(tmp_path))
        fatal = next(e for e in entries if e["event"] == "self_check_fatal")
        assert fatal.get("resolved_at") == "2026-04-29 10:05:00"

    def test_resolved_at_annotation_from_bridge_meta_prev_timestamp(self, tmp_path: Path) -> None:
        # bridge.audit() emits ``payload.evt`` and ``payload.meta.prev_timestamp``
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00:00",
                    "name": "AuditEvent",
                    "payload": {
                        "evt": "self_check_fatal",
                        "msg": "FATAL",
                    },
                },
                {
                    "ts": "2026-04-29T10:07:30",
                    "name": "AuditEvent",
                    "payload": {
                        "evt": "self_check_resolved",
                        "meta": {"prev_timestamp": "2026-04-29T10:00:00"},
                    },
                },
            ],
        )
        entries = get_log_entries(str(tmp_path))
        fatal = next(e for e in entries if e["meta"].get("evt") == "self_check_fatal")
        assert fatal.get("resolved_at") == "2026-04-29 10:07:30"

    def test_unresolved_fatal_has_no_resolved_at(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "self_check_fatal",
                    },
                },
            ],
        )
        entries = get_log_entries(str(tmp_path))
        fatal = next(e for e in entries if e["event"] == "self_check_fatal")
        assert "resolved_at" not in fatal


class TestGetProblems:
    def test_returns_only_warnings_errors_and_blockades(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {"message_name": "PlanCreated", "issue": 429},
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "DiagnosticRaised",
                        "level": "warning",
                        "category": "llm",
                        "issue": 429,
                        "reason": "provider timeout",
                        "file": "samuel/adapters/llm/openai.py",
                        "logger": "samuel.adapters.llm.openai",
                        "line": 41,
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanBlocked",
                        "issue": 430,
                        "reason": "scope creep",
                        "files": ["samuel/server.py"],
                    },
                },
            ],
        )

        problems = get_problems(str(tmp_path))

        assert [problem["timestamp"] for problem in problems] == ["t3", "t2"]
        assert problems[0]["level"] == "warn"
        assert problems[0]["reason"] == "scope creep"
        assert problems[0]["file"] == "samuel/server.py"
        assert problems[1]["category"] == "llm"
        assert problems[1]["issue"] == 429
        assert problems[1]["line"] == 41
        assert problems[1]["problem_type"] == "llm_provider"
        assert problems[1]["cause"]
        assert problems[1]["impact"]
        assert problems[1]["next_steps"]
        assert problems[1]["status"] == "active"

    def test_groups_repeated_diagnostics_and_preserves_instances(self, tmp_path: Path) -> None:
        second_seen = datetime.now(timezone.utc)
        first_seen = second_seen - timedelta(minutes=5)
        payload = {
            "message_name": "DiagnosticRaised",
            "level": "warning",
            "category": "system",
            "reason": "git diff --name-only failed: remote unavailable",
            "file": "samuel/core/git.py",
            "logger": "samuel.core.git",
        }
        _write_audit(
            tmp_path,
            [
                {"ts": first_seen.isoformat(), "name": "AuditEvent", "payload": payload},
                {"ts": second_seen.isoformat(), "name": "AuditEvent", "payload": payload},
            ],
        )

        problems = get_problems(str(tmp_path))

        assert len(problems) == 1
        assert problems[0]["count"] == 2
        assert problems[0]["first_seen"] == first_seen.isoformat()
        assert problems[0]["last_seen"] == second_seen.isoformat()
        assert len(problems[0]["instances"]) == 2

    def test_cross_issue_group_preserves_each_instance_without_claiming_one_issue(
        self, tmp_path: Path
    ) -> None:
        common = {
            "message_name": "DiagnosticRaised",
            "level": "warning",
            "category": "llm",
            "reason": "provider timeout",
            "logger": "samuel.adapters.llm.openrouter",
            "fingerprint": "provider-timeout",
        }
        _write_audit(
            tmp_path,
            [
                {"ts": "2026-08-31T10:00:00Z", "payload": {**common, "issue": 11}},
                {"ts": "2026-08-31T10:01:00Z", "payload": {**common, "issue": 16}},
            ],
        )

        problems = get_problems(str(tmp_path))

        assert len(problems) == 1
        assert problems[0]["issue"] == ""
        assert problems[0]["issues"] == [11, 16]
        assert [instance["issue"] for instance in problems[0]["instances"]] == [11, 16]

    def test_marks_proven_legacy_test_batch_without_deleting_raw_audit(
        self, tmp_path: Path
    ) -> None:
        batch_start = datetime.now(timezone.utc) - timedelta(minutes=20)

        def diagnostic(ts: str, reason: str) -> dict:
            return {
                "ts": ts,
                "name": "AuditEvent",
                "payload": {
                    "message_name": "DiagnosticRaised",
                    "level": "error",
                    "category": "system",
                    "reason": reason,
                    "file": "samuel/core/git.py",
                    "logger": "samuel.core.git",
                },
            }

        events = [
            diagnostic(
                (batch_start - timedelta(milliseconds=50)).isoformat(),
                "SCM not configured, running without version control",
            ),
            diagnostic(batch_start.isoformat(), "git log timed out"),
            diagnostic(
                (batch_start + timedelta(milliseconds=100)).isoformat(),
                "create_branch: cannot switch to main before recreating feat/x: dirty worktree",
            ),
            diagnostic(
                (batch_start + timedelta(milliseconds=200)).isoformat(),
                "create_branch: post-condition failed — on 'some-other-branch' instead of 'feat/x'",
            ),
            diagnostic(
                (batch_start + timedelta(minutes=10)).isoformat(),
                "git status failed: real failure",
            ),
        ]
        _write_audit(tmp_path, events)
        raw_before = (tmp_path / "logs" / "agent.jsonl").read_bytes()

        problems = get_problems(str(tmp_path))

        assert sum(p["count"] for p in problems if p["status"] == "invalid_test_data") == 4
        assert next(p for p in problems if "real failure" in p["reason"])["status"] == "active"
        assert (tmp_path / "logs" / "agent.jsonl").read_bytes() == raw_before

    def test_explicit_resolution_marks_older_occurrence_resolved(self, tmp_path: Path) -> None:
        payload = {
            "message_name": "DiagnosticRaised",
            "level": "warning",
            "category": "llm",
            "reason": "provider timeout",
            "logger": "samuel.adapters.llm.openai",
            "fingerprint": "known-diagnostic",
        }
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-08-21T10:00:00+00:00",
                    "name": "AuditEvent",
                    "payload": payload,
                },
                {
                    "ts": "2026-08-21T10:01:00+00:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "DiagnosticResolved",
                        "fingerprint": "known-diagnostic",
                    },
                },
            ],
        )

        problems = get_problems(str(tmp_path))

        assert problems[0]["status"] == "resolved"


class TestGetLogLevelCounts:
    def test_counts_grouped_by_classified_level(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {"ts": "t1", "name": "AuditEvent", "payload": {"message_name": "GateFailed"}},
                {"ts": "t2", "name": "AuditEvent", "payload": {"message_name": "WorkflowAborted"}},
                {"ts": "t3", "name": "AuditEvent", "payload": {"message_name": "HealingFailed"}},
                {"ts": "t4", "name": "AuditEvent", "payload": {"message_name": "PlanCreated"}},
                {"ts": "t5", "name": "AuditEvent", "payload": {"message_name": "PRCreated"}},
            ],
        )
        counts = get_log_level_counts(str(tmp_path))
        assert counts == {"info": 2, "warn": 1, "error": 2}

    def test_counts_zero_when_empty(self, tmp_path: Path) -> None:
        (tmp_path / "logs").mkdir()
        assert get_log_level_counts(str(tmp_path)) == {"info": 0, "warn": 0, "error": 0}


class TestGetWorkflowIssuesShape:
    def test_issues_use_timestamp_field(self, tmp_path: Path) -> None:
        # Frontend expects ``timestamp`` (not ``last_ts``) — see server.py:326
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 5,
                    },
                },
                {
                    "ts": "2026-04-29T11:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 5,
                    },
                },
            ],
        )
        issues = get_workflow_issues(str(tmp_path))
        assert len(issues) == 1
        assert issues[0]["timestamp"] == "2026-04-29T11:00"
        assert "last_ts" not in issues[0]


class TestGetSecurityOverviewShape:
    def test_owasp_returned_as_array(self, tmp_path: Path) -> None:
        # #290: Frontend expects array ``owasp: [{id, category, count, last}]``
        # mit ASI01..ASI10 als IDs. Historische ``A04:...``-Strings werden
        # ueber OWASP_LEGACY_ID_MAP auf ASI04 aufgeloest.
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "owasp_risk": "A04: Broken Trust",
                    },
                },
            ],
        )
        result = get_security_overview(str(tmp_path))
        assert "risks" not in result
        assert isinstance(result["owasp"], list)
        assert len(result["owasp"]) == 10  # one entry per ASI01..ASI10
        # Legacy A04 wird zu ASI04 (Agentic Supply Chain Vulnerabilities)
        asi04 = next(r for r in result["owasp"] if r["id"] == "ASI04")
        assert asi04["count"] == 1
        assert asi04["last"] == "2026-04-29T10:00"
        assert asi04["category"] == "Agentic Supply Chain Vulnerabilities"
        # Other risks present but with count 0
        asi01 = next(r for r in result["owasp"] if r["id"] == "ASI01")
        assert asi01["count"] == 0

    def test_barriers_use_frontend_field_names(self, tmp_path: Path) -> None:
        # Frontend reads barriers[].timestamp + barriers[].event
        # — see server.py:382 (b.timestamp||b.time, b.type||b.event)
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "gate": "BranchNotMain",
                        "reason": "Branch ist main/master",
                        "issue": 176,
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 5,
                    },
                },
            ],
        )
        assert get_workflow_issue_detail(99, str(tmp_path)) is None

    def test_audit_trail_chronological_and_capped_at_30(self, tmp_path: Path) -> None:
        events = [
            {
                "ts": f"2026-04-29T10:{i:02d}",
                "name": "AuditEvent",
                "payload": {
                    "message_name": "Implement",
                    "issue": 7,
                    "reason": f"r{i}",
                },
            }
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 1,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "CodeGenerated",
                        "issue": 1,
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "issue": 1,
                        "gate": 3,
                    },
                },
            ],
        )
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

    def test_failed_stage_exposes_concrete_reason_and_file(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanBlocked",
                        "issue": 429,
                        "reason": "scope_creep: file outside approved scope",
                        "files": ["samuel/server.py"],
                    },
                }
            ],
        )

        detail = get_workflow_issue_detail(429, str(tmp_path))

        assert detail is not None
        stage = detail["stages"]["plan"]
        assert stage["status"] == "failed"
        assert stage["event"] == "PlanBlocked"
        assert stage["reason"] == "scope_creep: file outside approved scope"
        assert stage["file"] == "samuel/server.py"

    def test_workflow_blocked_is_assigned_to_its_concrete_stage(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "WorkflowBlocked",
                        "issue": 429,
                        "source_command": "Implement",
                        "reason": "no_progress",
                    },
                }
            ],
        )

        detail = get_workflow_issue_detail(429, str(tmp_path))

        assert detail is not None
        assert detail["stages"]["implement"]["status"] == "failed"
        assert detail["stages"]["implement"]["reason"] == "no_progress"

    def test_workflow_budget_block_is_visible_in_llm_stage(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "WorkflowBudgetAdmitted",
                        "issue": 549,
                        "token_limit": 500000,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMBudgetBlocked",
                        "issue": 549,
                        "reason": "workflow_token_budget_exhausted",
                    },
                },
            ],
        )

        detail = get_workflow_issue_detail(549, str(tmp_path))

        assert detail is not None
        assert detail["stages"]["llm"]["status"] == "failed"
        assert detail["stages"]["llm"]["reason"] == "workflow_token_budget_exhausted"

    def test_no_parseable_patches_is_visible_as_implementation_failure(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "WorkflowBlocked",
                        "issue": 588,
                        "task": "implementation",
                        "reason": "no_parseable_patches",
                        "failures": ["no_parseable_patches"],
                        "diagnostic": {
                            "round": 1,
                            "patch_count": 0,
                            "applied_patch_count": 0,
                        },
                    },
                }
            ],
        )

        detail = get_workflow_issue_detail(588, str(tmp_path))

        assert detail is not None
        assert detail["status"] == "blocked"
        assert detail["stages"]["implement"]["status"] == "failed"
        assert detail["stages"]["implement"]["reason"] == "no_parseable_patches"

    def test_workspace_rollback_failure_is_visible_as_implementation_failure(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "WorkflowBlocked",
                        "issue": 598,
                        "task": "implementation",
                        "reason": "workspace_rollback_failed",
                        "trigger_reason": "token_limit",
                        "rollback": {
                            "status": "failed",
                            "files_restored": 0,
                            "files_removed": 0,
                            "directories_removed": 0,
                            "failures": 1,
                        },
                    },
                }
            ],
        )

        detail = get_workflow_issue_detail(598, str(tmp_path))

        assert detail is not None
        assert detail["status"] == "blocked"
        assert detail["stages"]["implement"]["status"] == "failed"
        assert detail["stages"]["implement"]["reason"] == "workspace_rollback_failed"

    def test_stage_gates_done_on_passed_event(self, tmp_path: Path) -> None:
        """#258: GatesPassed-Event markiert gates-Stage als done.

        Vorher zeigte gates "pending" für erfolgreiche Runs weil nur
        GateFailed/SecurityTripwireTriggered im Mapping war."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GatesPassed",
                        "issue": 258,
                        "gates_run": 12,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["gates"]["status"] == "done"
        assert d["stages"]["gates"]["count"] == 1
        assert d["stages"]["gates"]["fail_count"] == 0

    def test_stage_quality_done_on_passed_event(self, tmp_path: Path) -> None:
        """#258: QualityPassed-Event markiert quality-Stage als done."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "QualityPassed",
                        "issue": 258,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["quality"]["status"] == "done"

    def test_stage_review_done_when_pr_created(self, tmp_path: Path) -> None:
        """A profile without a review transition still completes at PR creation."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 258,
                        "pr_number": 999,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["review"]["status"] == "done"
        assert d["stages"]["pr"]["status"] == "done"

    def test_required_review_stays_pending_until_structured_outcome(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 468,
                        "pr_number": 1000,
                        "review_required": True,
                        "correlation_id": "run-468",
                    },
                }
            ],
        )
        pending = get_workflow_issue_detail(468, str(tmp_path))
        assert pending is not None
        assert pending["stages"]["review"]["status"] == "pending"

        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 468,
                        "pr_number": 1000,
                        "review_required": True,
                        "correlation_id": "run-468",
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ReviewCompleted",
                        "issue": 468,
                        "decision": "pass",
                        "correlation_id": "run-468",
                    },
                },
            ],
        )
        completed = get_workflow_issue_detail(468, str(tmp_path))
        assert completed is not None
        assert completed["status"] == "reviewed"
        assert completed["last_event"] == "ReviewCompleted"
        assert completed["stages"]["review"]["status"] == "done"

    def test_pr_creation_failed_marks_pr_failed_without_completing_review(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GatesPassed",
                        "issue": 516,
                        "correlation_id": "run-516",
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreationFailed",
                        "issue": 516,
                        "correlation_id": "run-516",
                        "reason": "SCM did not confirm creation of a valid pull request",
                    },
                },
            ],
        )

        detail = get_workflow_issue_detail(516, str(tmp_path))

        assert detail is not None
        assert detail["status"] == "blocked"
        assert detail["stages"]["gates"]["status"] == "done"
        assert detail["stages"]["pr"]["status"] == "failed"
        assert detail["stages"]["pr"]["event"] == "PRCreationFailed"
        assert detail["stages"]["review"]["status"] == "pending"

    def test_manual_pending_is_projected_as_waiting_without_failed_gates(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "CodeGenerated",
                        "issue": 679,
                        "correlation_id": "run-manual-679",
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateEvaluationCompleted",
                        "issue": 679,
                        "correlation_id": "run-manual-679",
                        "blocked": True,
                        "manual_pending": True,
                        "gate_results": [
                            {
                                "gate": 11,
                                "authority": "required",
                                "passed": False,
                                "status": "manual_pending",
                                "reason": "Human acceptance pending",
                            }
                        ],
                    },
                },
            ],
        )

        detail = get_workflow_issue_detail(679, str(tmp_path))

        assert detail is not None
        assert detail["status"] == "manual_pending"
        assert detail["stages"]["gates"]["status"] == "pending"
        assert detail["stages"]["pr"]["status"] == "pending"
        assert detail["runs"][0]["final_status"] == "manual_pending"
        assert detail["runs"][0]["stages_failed"] == 0

    def test_gate_block_without_healing_attempt_or_pr_has_truthful_stages(
        self, tmp_path: Path
    ) -> None:
        """#578: exact rollout sequence must not invent an attempt or PR."""

        correlation_id = "run-578"
        base_payload = {"issue": 578, "correlation_id": correlation_id}
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        **base_payload,
                        "message_name": "GateEvaluationCompleted",
                        "blocked": True,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        **base_payload,
                        "message_name": "HealingClassified",
                        "classification": "not_healable",
                        "reason": "ambiguous_failed_criteria",
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        **base_payload,
                        "message_name": "WorkflowBlocked",
                        "reason": "bound_healing:ambiguous_failed_criteria",
                    },
                },
                {
                    "ts": "t4",
                    "name": "AuditEvent",
                    "payload": {**base_payload, "message_name": "CreatePR"},
                },
            ],
        )

        detail = get_workflow_issue_detail(578, str(tmp_path))

        assert detail is not None
        assert detail["status"] == "blocked"
        assert detail["stages"]["gates"]["status"] == "failed"
        assert detail["stages"]["gates"]["event"] == "GateEvaluationCompleted"
        assert detail["stages"]["pr"] == {
            "status": "blocked",
            "last_ts": "t1",
            "count": 0,
            "fail_count": 0,
            "reason": "Required gate profile blocked the candidate before PR creation",
            "event": "GateEvaluationCompleted",
            "file": "",
            "files": [],
        }
        assert detail["runs"][0]["stages_done"] == 0
        assert detail["runs"][0]["stages_failed"] == 1
        assert detail["stages"]["healing"] == {
            "status": "not_attempted",
            "last_ts": "t2",
            "count": 0,
            "fail_count": 0,
            "reason": "ambiguous_failed_criteria",
            "event": "HealingClassified",
            "file": "",
            "files": [],
        }

    def test_create_pr_dispatch_without_outcome_remains_pending(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "CreatePR",
                        "issue": 578,
                        "correlation_id": "run-dispatched",
                    },
                }
            ],
        )

        detail = get_workflow_issue_detail(578, str(tmp_path))

        assert detail is not None
        assert detail["stages"]["pr"]["status"] == "pending"
        assert detail["stages"]["pr"]["count"] == 0

    def test_healing_attempt_evidence_counts_one_attempt(self, tmp_path: Path) -> None:
        base_payload = {
            "issue": 578,
            "correlation_id": "run-healed",
            "observation_key": "sha256:" + "a" * 64,
            "attempt": 1,
        }
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {**base_payload, "message_name": "HealingAttemptStarted"},
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {**base_payload, "message_name": "HealingAttemptCompleted"},
                },
            ],
        )

        detail = get_workflow_issue_detail(578, str(tmp_path))

        assert detail is not None
        assert detail["stages"]["healing"]["status"] == "done"
        assert detail["stages"]["healing"]["count"] == 1
        assert detail["stages"]["healing"]["fail_count"] == 0
        assert detail["runs"][0]["stages_done"] == 1
        assert detail["runs"][0]["stages_failed"] == 0

    def test_latest_correlated_run_does_not_inherit_old_pr_or_healing_outcome(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "HealingAttemptStarted",
                        "issue": 578,
                        "correlation_id": "old-run",
                        "attempt": 1,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 578,
                        "correlation_id": "old-run",
                        "pr_number": 1,
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateEvaluationCompleted",
                        "issue": 578,
                        "correlation_id": "new-run",
                        "blocked": True,
                    },
                },
                {
                    "ts": "t4",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "HealingClassified",
                        "issue": 578,
                        "correlation_id": "new-run",
                        "classification": "not_healable",
                        "reason": "missing_evidence",
                    },
                },
            ],
        )

        detail = get_workflow_issue_detail(578, str(tmp_path))

        assert detail is not None
        assert detail["stages"]["pr"]["status"] == "blocked"
        assert detail["stages"]["healing"]["status"] == "not_attempted"
        assert detail["stages"]["healing"]["count"] == 0

    def test_stage_implement_inferred_from_pr_created(self, tmp_path: Path) -> None:
        """#258 + #257: PRCreated impliziert implement-Stage als done — robust
        gegen verlorenes CodeGenerated-Event (Audit-Loss-Defense-in-Depth)."""
        _write_audit(
            tmp_path,
            [
                # Kein CodeGenerated-Event (simuliert verlorenes Event)
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 258,
                        "pr_number": 999,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        assert d["stages"]["implement"]["status"] == "done"

    def test_pipeline_all_stages_done_for_successful_run(self, tmp_path: Path) -> None:
        """#258: realistischer Self-Mode-Run zeigt alle 8 Stages 'done'."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 258,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanValidated",
                        "issue": 258,
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "CodeGenerated",
                        "issue": 258,
                    },
                },
                {
                    "ts": "t4",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "issue": 258,
                        "task": "implementation",
                    },
                },
                {
                    "ts": "t5",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "QualityPassed",
                        "issue": 258,
                    },
                },
                {
                    "ts": "t6",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalCompleted",
                        "issue": 258,
                        "score": 1.0,
                    },
                },
                {
                    "ts": "t7",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GatesPassed",
                        "issue": 258,
                        "gates_run": 12,
                    },
                },
                {
                    "ts": "t8",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 258,
                        "pr_number": 999,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(258, str(tmp_path))
        assert d is not None
        for stage_name in ("plan", "implement", "llm", "gates", "quality", "eval", "pr", "review"):
            assert d["stages"][stage_name]["status"] == "done", (
                f"Stage {stage_name} should be 'done', got {d['stages'][stage_name]}"
            )

    def test_score_aggregated_from_eval_events(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "Evaluate",
                        "issue": 9,
                        "score": 80,
                        "baseline": 60,
                        "checks_passed": 4,
                        "checks_total": 5,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalCompleted",
                        "issue": 9,
                        "score": 80,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(9, str(tmp_path))
        assert d is not None
        assert d["score"]["value"] == 80
        assert d["score"]["baseline"] == 60
        assert d["score"]["passed"] is True
        assert d["score"]["checks_passed"] == 4
        assert d["score"]["checks_total"] == 5

    def test_score_passed_false_on_eval_failed(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalFailed",
                        "issue": 11,
                        "reason": "no scores",
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(11, str(tmp_path))
        assert d is not None
        assert d["score"]["passed"] is False
        assert d["score"]["reason"] == "no scores"

    def test_bound_score_detail_has_no_release_outcome(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ScoreObserved",
                        "issue": 399,
                        "score": 0.75,
                        "coverage": 0.5,
                        "label": "Nicht bindende Qualitätsbeobachtung",
                        "non_binding": True,
                        "observation_key": "sha256:" + "a" * 64,
                        "score_key": "sha256:" + "b" * 64,
                        "scoring_policy_version": "policy.v1",
                        "scoring_policy_digest": "sha256:" + "c" * 64,
                        "formula_version": "formula.v1",
                        "evidence_origin": "bound_acceptance_evidence",
                    },
                }
            ],
        )
        detail = get_workflow_issue_detail(399, str(tmp_path))
        assert detail is not None
        assert detail["score"]["label"] == "Nicht bindende Qualitätsbeobachtung"
        assert detail["score"]["non_binding"] is True
        assert detail["score"]["passed"] is None
        assert detail["score"]["baseline"] is None

    def test_llm_aggregated_per_provider_and_task(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "issue": 13,
                        "provider": "deepseek",
                        "task": "implementation",
                        "tokens": 500,
                        "cost": 0.001,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "issue": 13,
                        "provider": "deepseek",
                        "task": "planning",
                        "input_tokens": 100,
                        "output_tokens": 200,
                        "cost": 0.0005,
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "issue": 13,
                        "provider": "claude",
                        "task": "planning",
                        "tokens": 300,
                        "cost": 0.01,
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "issue": 50,
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "task": "planning",
                        "tokens": 500,
                        "cost": 0.001,
                        "latency_ms": 1234,
                        "stop_reason": "stop",
                        "guards": ["prompt_guards", "plan_validator"],
                        "tools_loaded": ["PythonASTBuilder", "GoRegexBuilder"],
                        "context_sections": ["skeleton", "grep"],
                        "prompt_tokens_est": 1500,
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "issue": 51,
                        "provider": "deepseek",
                        "task": "planning",
                        "tokens": 100,
                        "cost": 0.0,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(51, str(tmp_path))
        assert d is not None
        c = d["llm"]["calls_detail"][0]
        assert c["guards"] == []
        assert c["tools_loaded"] == []
        assert c["context_sections"] == []
        assert c["prompt_tokens_est"] is None

    def test_branch_is_last_seen(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "CodeGenerated",
                        "issue": 4,
                        "branch": "samuel/issue-4",
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "Implement",
                        "issue": 4,
                        "branch": "samuel/issue-4-v2",
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(4, str(tmp_path))
        assert d is not None
        assert d["branch"] == "samuel/issue-4-v2"

    def test_overall_status_pr_created_overrides_implemented(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "CodeGenerated",
                        "issue": 22,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PRCreated",
                        "issue": 22,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(22, str(tmp_path))
        assert d is not None
        assert d["status"] == "pr_created"

    def test_skips_other_issues(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 1,
                    },
                },
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "Implement",
                        "issue": 2,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(1, str(tmp_path))
        assert d is not None
        assert len(d["events"]) == 1
        assert d["events"][0]["event"] == "PlanCreated"
        assert d["stages"]["implement"]["status"] == "pending"


class TestSecurityOverviewExtras:
    def test_barrier_translates_gate_id_to_name(self, tmp_path: Path) -> None:
        # GateFailed.payload.gate is a numeric ID; the dashboard must show
        # the human-readable name (e.g. 1 → BranchGuard).
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "gate": 1,
                        "reason": "Branch ist main",
                        "issue": 9,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "gate": "13a",
                        "reason": "Branch zu alt",
                    },
                },
            ],
        )
        result = get_security_overview(str(tmp_path))
        events = [b["event"] for b in result["barriers"]]
        assert "BranchGuard" in events
        assert "BranchFreshness" in events

    def test_barrier_event_falls_back_to_msg_name_when_no_gate_id(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "WorkflowAborted",
                        "reason": "stop",
                    },
                },
            ],
        )
        result = get_security_overview(str(tmp_path))
        assert result["barriers"][0]["event"] == "WorkflowAborted"
        assert result["barriers"][0]["action"] == "warn"

    def test_barrier_includes_step_field(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "gate": 7,
                        "step": "round_2",
                    },
                },
            ],
        )
        result = get_security_overview(str(tmp_path))
        assert result["barriers"][0]["step"] == "round_2"

    def test_owasp_includes_recent_events_per_risk(self, tmp_path: Path) -> None:
        # #290: legacy A04 (broken_trust_boundaries) ist jetzt ASI04 (agentic_supply_chain)
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "owasp_risk": "A04:Trust",
                        "reason": "r1",
                        "issue": 1,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "SecurityTripwireTriggered",
                        "owasp_risk": "A04",
                        "reason": "r2",
                    },
                },
            ],
        )
        result = get_security_overview(str(tmp_path))
        asi04 = next(r for r in result["owasp"] if r["id"] == "ASI04")
        assert asi04["count"] == 2
        assert isinstance(asi04["recent"], list)
        assert len(asi04["recent"]) == 2
        assert asi04["recent"][0]["event"] == "GateFailed"
        assert asi04["recent"][0]["issue"] == 1

    def test_owasp_recent_capped_at_5(self, tmp_path: Path) -> None:
        # #290: legacy A07 (unsafe_tool_integration) -> ASI02 (tool_misuse)
        events = [
            {
                "ts": f"t{i}",
                "name": "AuditEvent",
                "payload": {
                    "message_name": "GateFailed",
                    "owasp_risk": "A07",
                },
            }
            for i in range(8)
        ]
        _write_audit(tmp_path, events)
        result = get_security_overview(str(tmp_path))
        asi02 = next(r for r in result["owasp"] if r["id"] == "ASI02")
        assert asi02["count"] == 8
        assert len(asi02["recent"]) == 5

    def test_owasp_overview_uses_classify_fallback_for_unmarked_events(
        self, tmp_path: Path
    ) -> None:
        """Events ohne payload.owasp_risk werden via classify(cat, evt) klassifiziert
        und tragen zum classified_pct + active_risks bei.

        #290: Neue ASI-Klassifikation:
        - workflow-Fallback -> agent_goal_hijack -> ASI01
        - llm-Fallback -> identity_privilege_abuse -> ASI03
        - Legacy A04 -> ASI04 (agentic_supply_chain)
        """
        _write_audit(
            tmp_path,
            [
                # 1) PlanCreated → cat="workflow", fallback agent_goal_hijack → ASI01
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 1,
                    },
                },
                # 2) LLMCallCompleted → cat="llm", fallback identity_privilege_abuse → ASI03
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "issue": 1,
                    },
                },
                # 3) Explicit GateFailed mit Legacy A04 → ASI04 via legacy_id resolution
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "owasp_risk": "A04:Trust",
                    },
                },
            ],
        )
        result = get_security_overview(str(tmp_path))
        asi01 = next(r for r in result["owasp"] if r["id"] == "ASI01")
        asi03 = next(r for r in result["owasp"] if r["id"] == "ASI03")
        asi04 = next(r for r in result["owasp"] if r["id"] == "ASI04")
        assert asi01["count"] == 1, f"PlanCreated should map to ASI01, got owasp={result['owasp']}"
        assert asi03["count"] == 1
        assert asi04["count"] == 1
        # All three events classified
        assert result["classified_pct"] == 100
        assert result["active_risks"] == 3

    def test_maps_provider_to_system_and_model(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "latency_ms": 234,
                        "stop_reason": "stop",
                        "task": "planning",
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "claude",
                        "model": "sonnet",
                        "tokens": 999,
                    },
                },
            ],
        )
        rows = get_otel_gen_ai_calls(str(tmp_path))
        assert rows[0]["gen_ai.usage.total_tokens"] == 999

    def test_skips_non_llm_events(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                    },
                },
            ],
        )
        assert get_otel_gen_ai_calls(str(tmp_path)) == []

    def test_newest_first(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "p1",
                        "model": "m",
                    },
                },
                {
                    "ts": "2026-04-29T11:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "p2",
                        "model": "m",
                    },
                },
            ],
        )
        rows = get_otel_gen_ai_calls(str(tmp_path))
        assert rows[0]["gen_ai.system"] == "p2"
        assert rows[1]["gen_ai.system"] == "p1"


class TestGetTokenHistory:
    def test_returns_chronological_newest_first(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "2026-04-29T10:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "task": "planning",
                        "input_tokens": 100,
                        "output_tokens": 200,
                        "tokens": 300,
                        "cached_tokens": 0,
                        "cost": 0.001,
                        "latency_ms": 500,
                        "stop_reason": "stop",
                    },
                },
                {
                    "ts": "2026-04-29T11:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "claude",
                        "model": "sonnet",
                        "task": "implement",
                        "tokens": 800,
                        "cost": 0.05,
                        "latency_ms": 1200,
                    },
                },
            ],
        )
        rows = get_token_history(str(tmp_path))
        assert len(rows) == 2
        assert rows[0]["timestamp"] == "2026-04-29T11:00"
        assert rows[0]["provider"] == "claude"
        assert rows[1]["provider"] == "deepseek"
        assert rows[1]["input_tokens"] == 100
        assert rows[1]["cost"] == 0.001

    def test_skips_non_llm_events(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {"ts": "t", "name": "AuditEvent", "payload": {"message_name": "PlanCreated"}},
            ],
        )
        assert get_token_history(str(tmp_path)) == []

    def test_passes_through_phase1_metadata(self, tmp_path: Path) -> None:
        """Phase 3 (#218): guards/tools_loaded/context_sections/prompt_tokens_est
        gehoeren ins LLM-Tab History, damit das Dashboard die Phase-1-Anreicherung
        sichtbar macht."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "claude",
                        "model": "sonnet",
                        "task": "implementation",
                        "tokens": 800,
                        "cost": 0.05,
                        "guards": ["prompt_guards", "context_validator"],
                        "tools_loaded": ["PythonASTBuilder"],
                        "context_sections": ["skeleton", "grep", "relevant_files"],
                        "prompt_tokens_est": 4200,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "deepseek",
                        "task": "planning",
                        "tokens": 100,
                    },
                },
            ],
        )
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
            {
                "ts": f"t{i:02d}",
                "name": "AuditEvent",
                "payload": {
                    "message_name": "LLMCallCompleted",
                    "provider": "p",
                    "model": "m",
                },
            }
            for i in range(80)
        ]
        _write_audit(tmp_path, many)
        rows = get_token_history(str(tmp_path), limit=20)
        assert len(rows) == 20


class TestGetLLMQualityScores:
    def test_correlates_via_correlation_id(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "claude",
                        "model": "sonnet",
                        "task": "implement",
                        "correlation_id": "c1",
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalCompleted",
                        "score": 0.9,
                        "correlation_id": "c1",
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "claude",
                        "model": "sonnet",
                        "task": "implement",
                        "correlation_id": "c2",
                    },
                },
                {
                    "ts": "t4",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalFailed",
                        "correlation_id": "c2",
                    },
                },
            ],
        )
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

    def test_calls_without_eval_pair_are_explicitly_unattributed(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "deepseek",
                        "model": "x",
                        "task": "plan",
                        "correlation_id": "c-no-eval",
                    },
                },
            ],
        )
        rows = get_llm_quality_scores(str(tmp_path))
        assert len(rows) == 1
        assert rows[0]["calls"] == 0
        assert rows[0]["unattributed_calls"] == 1
        assert rows[0]["other_series_calls"] == 0
        assert rows[0]["graded"] == 0
        assert rows[0]["success_rate_pct"] is None

    def test_empty_log_returns_empty_list(self, tmp_path: Path) -> None:
        assert get_llm_quality_scores(str(tmp_path)) == []

    def test_bound_quality_presence_excludes_legacy_eval_series(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "p",
                        "model": "m",
                        "task": "impl",
                        "correlation_id": "legacy",
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalCompleted",
                        "score": 0.0,
                        "correlation_id": "legacy",
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "p",
                        "model": "m",
                        "task": "impl",
                        "correlation_id": "bound",
                    },
                },
                {
                    "ts": "t4",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ScoreObserved",
                        "issue": 2,
                        "score": 1.0,
                        "correlation_id": "bound",
                        "label": "Nicht bindende Qualitätsbeobachtung",
                        "non_binding": True,
                        "evidence_origin": "bound_acceptance_evidence",
                        "observation_key": "sha256:" + "a" * 64,
                        "score_key": "sha256:" + "b" * 64,
                        "scoring_policy_version": "eval.v1",
                        "scoring_policy_digest": "sha256:" + "c" * 64,
                        "formula_version": "bound.v1",
                    },
                },
            ],
        )

        row = get_llm_quality_scores(str(tmp_path))[0]
        assert row["calls"] == 1
        assert row["other_series_calls"] == 1
        assert row["unattributed_calls"] == 0
        assert row["graded"] == 0
        assert row["avg_score"] == 1.0
        assert row["evidence_origin"] == "bound_acceptance_evidence"
        assert row["scoring_policy_version"] == "eval.v1"
        assert row["formula_version"] == "bound.v1"

    def test_latest_bound_formula_is_not_mixed_with_previous_formula(self, tmp_path: Path) -> None:
        def observed(correlation_id: str, score: float, formula: str) -> dict:
            return {
                "ts": f"score-{formula}",
                "name": "AuditEvent",
                "payload": {
                    "message_name": "ScoreObserved",
                    "score": score,
                    "correlation_id": correlation_id,
                    "label": "Nicht bindende Qualitätsbeobachtung",
                    "non_binding": True,
                    "evidence_origin": "bound_acceptance_evidence",
                    "observation_key": "sha256:" + "a" * 64,
                    "score_key": "sha256:" + "b" * 64,
                    "scoring_policy_version": "eval.v1",
                    "scoring_policy_digest": "sha256:" + "c" * 64,
                    "formula_version": formula,
                },
            }

        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "p",
                        "model": "m",
                        "task": "impl",
                        "correlation_id": "old",
                    },
                },
                observed("old", 0.0, "bound.v1"),
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "LLMCallCompleted",
                        "provider": "p",
                        "model": "m",
                        "task": "impl",
                        "correlation_id": "new",
                    },
                },
                observed("new", 1.0, "bound.v2"),
            ],
        )

        row = get_llm_quality_scores(str(tmp_path))[0]
        assert row["calls"] == 1
        assert row["other_series_calls"] == 1
        assert row["avg_score"] == 1.0
        assert row["formula_version"] == "bound.v2"


class TestGetApiKeyStatus:
    def _write_providers(self, tmp_path: Path, data: dict) -> None:
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        (llm_dir / "providers.json").write_text(json.dumps(data))

    def test_configured_when_env_var_present(self, tmp_path: Path, monkeypatch: Any) -> None:
        self._write_providers(
            tmp_path,
            {
                "providers": {
                    "deepseek": {"model": "deepseek-chat", "env_key": "DEEPSEEK_API_KEY"}
                },
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret")
        rows = get_api_key_status(str(tmp_path))
        assert len(rows) == 1
        assert rows[0]["provider"] == "deepseek"
        assert rows[0]["status"] == "configured"
        assert rows[0]["env_key"] == "DEEPSEEK_API_KEY"

    def test_missing_when_env_var_absent(self, tmp_path: Path, monkeypatch: Any) -> None:
        self._write_providers(
            tmp_path,
            {
                "providers": {"claude": {"model": "sonnet", "env_key": "ANTHROPIC_API_KEY"}},
            },
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        rows = get_api_key_status(str(tmp_path))
        assert rows[0]["status"] == "missing"
        assert "set $ANTHROPIC_API_KEY" in rows[0]["note"]

    def test_url_only_for_local_providers(self, tmp_path: Path) -> None:
        self._write_providers(
            tmp_path,
            {
                "providers": {"ollama": {"model": "llama3", "url": "http://localhost:11434"}},
            },
        )
        rows = get_api_key_status(str(tmp_path))
        assert rows[0]["status"] == "url_only"
        assert rows[0]["url"] == "http://localhost:11434"

    def test_no_providers_file_returns_empty(self, tmp_path: Path) -> None:
        # No providers.json at all
        assert get_api_key_status(str(tmp_path)) == []


class TestGetLLMRoutingSchedule:
    """#302: Per-task schedule config. Old day_provider/night_provider fields
    were replaced with a per-task tasks list."""

    def test_without_schedule_is_not_reported_active(self, tmp_path) -> None:
        s = get_llm_routing_schedule(None, config_dir=str(tmp_path))

        assert s["feature_available"] is True
        assert s["configured"] is False
        assert s["enabled"] is False
        assert s["active_now"] is False
        assert s["tasks"] == []

    def test_enabled_when_schedule_is_configured(self, tmp_path) -> None:
        # Build a defaults.json with a schedule
        import json as _json

        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(
            _json.dumps(
                {
                    "tasks": {
                        "implementation": {
                            "provider": "deepseek",
                            "model": "deepseek-coder",
                            "schedule": {
                                "active": True,
                                "from": "22:00",
                                "to": "06:00",
                                "provider": "claude",
                                "model": "claude-opus",
                            },
                        },
                    },
                }
            )
        )

        s = get_llm_routing_schedule(None, config_dir=str(tmp_path))
        assert s["feature_available"] is True
        assert s["configured"] is True
        assert s["enabled"] is True
        assert len(s["tasks"]) == 1
        row = s["tasks"][0]
        assert row["task"] == "implementation"
        assert row["day_provider"] == "deepseek"
        assert row["night_provider"] == "claude"
        assert row["from"] == "22:00"


class TestGetScoreHistory:
    def test_bound_score_is_labelled_non_binding_without_pass_fail(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ScoreObserved",
                        "issue": 399,
                        "score": 0.75,
                        "coverage": 0.5,
                        "label": "Nicht bindende Qualitätsbeobachtung",
                        "non_binding": True,
                        "observation_key": "sha256:" + "a" * 64,
                        "score_key": "sha256:" + "b" * 64,
                        "scoring_policy_version": "policy.v1",
                        "scoring_policy_digest": "sha256:" + "c" * 64,
                        "formula_version": "formula.v1",
                        "evidence_origin": "bound_acceptance_evidence",
                    },
                }
            ],
        )

        rows = get_score_history(str(tmp_path))
        assert rows[0]["score"] == 0.75
        assert rows[0]["passed"] is None
        assert rows[0]["non_binding"] is True
        assert rows[0]["baseline"] is None
        assert rows[0]["coverage"] == 0.5

    def test_picks_eval_completed_and_failed_only(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "Evaluate",  # skipped
                        "score": None,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalCompleted",
                        "score": 0.9,
                        "baseline": 0.5,
                        "issue": 1,
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalFailed",
                        "score": 0.1,
                        "baseline": 0.5,
                        "reason": "low",
                    },
                },
            ],
        )
        rows = get_score_history(str(tmp_path))
        # newest first
        assert [r["passed"] for r in rows] == [False, True]
        assert rows[0]["score"] == 0.1
        assert rows[0]["reason"] == "low"
        assert rows[1]["score"] == 0.9
        assert rows[1]["issue"] == 1

    def test_limit_applied(self, tmp_path: Path) -> None:
        many = [
            {
                "ts": f"t{i:03d}",
                "name": "AuditEvent",
                "payload": {
                    "message_name": "EvalCompleted",
                    "score": float(i),
                },
            }
            for i in range(20)
        ]
        _write_audit(tmp_path, many)
        rows = get_score_history(str(tmp_path), limit=5)
        assert len(rows) == 5
        # newest first → highest scores
        assert rows[0]["score"] == 19.0


class TestDashboardTestRuns:
    def test_dashboard_test_runs_renders(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "TestRunCompleted",
                        "issue": 246,
                        "test_name": "test_alpha",
                        "runner": "pytest",
                        "passed": True,
                        "exit_code": 0,
                        "duration_ms": 1200,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "TestRunCompleted",
                        "issue": 246,
                        "test_name": "test_beta",
                        "runner": "jest",
                        "passed": False,
                        "exit_code": 1,
                        "duration_ms": 800,
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "TestRunCompleted",
                        "issue": 246,
                        "test_name": "ok_test",
                        "passed": True,
                    },
                },
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "TestRunCompleted",
                        "issue": 246,
                        "test_name": "broken_test",
                        "passed": False,
                    },
                },
            ],
        )
        rows = get_runtime_anomalies(str(tmp_path))
        events = [r["event"] for r in rows]
        # Failed test must be reported as anomaly
        assert "TestRunCompleted" in events
        # Passed test must NOT be reported (special-case)
        passed_count = sum(1 for r in rows if r["event"] == "TestRunCompleted")
        assert passed_count == 1, f"Expected 1 anomaly (failed only), got {passed_count}"

    def test_ai_act_classification_in_audit_trail(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "TestRunCompleted",
                        "issue": 246,
                        "evt": "test_failed",
                        "passed": False,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalCompleted",
                        "issue": 246,
                        "evt": "eval_run",
                    },
                },
            ],
        )
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

    def test_tamper_events_classified_and_listed(self, tmp_path: Path) -> None:
        """#208: TamperDetected/UnauthorizedChange/IntegrityViolation werden als
        security/ASI04/Art.15 klassifiziert und von get_tamper_events erfasst."""
        import json as _json

        from samuel.core.ai_act import classify as classify_ai_act
        from samuel.core.owasp import classify as classify_owasp
        from samuel.slices.dashboard.data import (
            _classify_category,
            _event_key,
            get_tamper_events,
        )

        for name in ("TamperDetected", "UnauthorizedChange", "IntegrityViolation"):
            evt = {"payload": {"message_name": name}}
            cat = _classify_category(evt)
            assert cat == "security"
            assert classify_owasp(cat, _event_key(evt["payload"])) == "agentic_supply_chain"
            assert classify_ai_act(cat, _event_key(evt["payload"])) == "Art. 15"

        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "agent.jsonl").write_text(
            _json.dumps(
                {
                    "ts": "2026-05-29T10:00:00",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "TamperDetected",
                        "reason": "webhook signature verification failed",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        events = get_tamper_events(str(tmp_path))
        assert any(e["event"] == "TamperDetected" for e in events)

    def test_dlq_entries_empty_when_no_file(self, tmp_path: Path) -> None:
        from samuel.slices.dashboard.data import get_dlq_entries

        assert get_dlq_entries(str(tmp_path)) == []

    def test_dlq_entries_newest_first(self, tmp_path: Path) -> None:
        import json as _json

        from samuel.slices.dashboard.data import get_dlq_entries

        fp = tmp_path / "dlq.jsonl"
        fp.write_text(
            _json.dumps({"id": "1", "event_name": "A", "error": "e"})
            + "\n"
            + _json.dumps({"id": "2", "event_name": "B", "error": "e"})
            + "\n",
            encoding="utf-8",
        )
        rows = get_dlq_entries(str(tmp_path))
        assert [r["event_name"] for r in rows] == ["B", "A"]

    def test_legend_returns_owasp_and_ai_act(self) -> None:
        legend = get_compliance_legend()
        assert "owasp" in legend
        assert "ai_act" in legend
        assert isinstance(legend["owasp"], list)
        assert isinstance(legend["ai_act"], list)

    def test_legend_owasp_has_all_top10(self) -> None:
        """#290: Vollständige OWASP-Top-10 ASI01..ASI10 mit ID, Name, Key, Beschreibung."""
        legend = get_compliance_legend()
        ids = {entry["id"] for entry in legend["owasp"]}
        assert ids == {f"ASI{i:02d}" for i in range(1, 11)}, (
            f"Expected ASI01..ASI10, got {sorted(ids)}"
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
            assert entry["description"], f"Missing description for {entry['article']}"

    def test_legend_ai_act_articles_have_obligation(self, monkeypatch) -> None:
        """#371/#373: jeder AI-Act-Artikel in der Legend traegt ein gueltiges
        ``obligation`` (``required``/``voluntary``), damit das Dashboard die
        Pflicht/freiwillig-Badges rendern kann. Default-Deployment (Self-Mode,
        Limited Risk): Art. 50 Pflicht, Art. 12/13/14/15 freiwillig."""
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        legend = get_compliance_legend()
        assert legend["ai_act_risk_class"] == "limited_risk"
        assert legend["ai_act_risk_class_source"] == "default"
        obligations = {entry["article"]: entry["obligation"] for entry in legend["ai_act"]}
        assert obligations, "ai_act legend empty"
        for article, oblig in obligations.items():
            assert oblig in ("required", "voluntary"), f"{article}: invalid obligation {oblig!r}"
        assert obligations["Art. 50"] == "required"
        for art in ("Art. 12", "Art. 13", "Art. 14", "Art. 15"):
            assert obligations[art] == "voluntary", (
                f"{art} expected voluntary, got {obligations[art]!r}"
            )

    def test_legend_obligation_flips_for_high_risk_deployment(self, monkeypatch) -> None:
        """#373: in einem Hochrisiko-Deployment werden Art. 12-15 Pflicht und
        ``ai_act_risk_class`` spiegelt die aktive Klasse — sonst wirkt ein
        ``freiwillig`` an einem Hochrisiko-System irrefuehrend."""
        monkeypatch.setenv("SAMUEL_RISK_CLASS", "high_risk")
        legend = get_compliance_legend()
        assert legend["ai_act_risk_class"] == "high_risk"
        assert legend["ai_act_risk_class_source"] == "env"
        obligations = {entry["article"]: entry["obligation"] for entry in legend["ai_act"]}
        assert obligations["Art. 50"] == "required"
        for art in ("Art. 12", "Art. 13", "Art. 14", "Art. 15"):
            assert obligations[art] == "required", (
                f"{art} expected required under high_risk, got {obligations[art]!r}"
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
        named_values = {v for v in OWASP_RISK_MAP.values() if not v.startswith("A0")}
        missing = named_values - legend_keys
        assert not missing, f"Risk-keys in OWASP_RISK_MAP without legend entry: {missing}"

    def test_legend_articles_match_ai_act_map_values(self) -> None:
        """Charter §1.4: jeder Artikel in AI_ACT_ARTICLE_MAP muss
        Beschreibung haben."""
        from samuel.core.ai_act import AI_ACT_ARTICLE_MAP

        legend = get_compliance_legend()
        legend_articles = {entry["article"] for entry in legend["ai_act"]}
        used_articles = set(AI_ACT_ARTICLE_MAP.values())
        missing = used_articles - legend_articles
        assert not missing, f"Articles in AI_ACT_ARTICLE_MAP without legend entry: {missing}"


class TestPlanContext:
    """#237: PlanContextLoaded-Events fliessen in
    workflow_issue_detail.plan_context."""

    def test_plan_context_in_dashboard_detail(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanContextLoaded",
                        "issue": 237,
                        "evt": "plan_context_load",
                        "skeleton_tokens": 1500,
                        "relevant_files_count": 5,
                        "grep_hits": 12,
                        "total_context_tokens": 4200,
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanPreCheckCompleted",
                        "issue": 238,
                        "evt": "plan_pre_check",
                        "structural_score": 100,
                        "skeleton_score": 100,
                        "ac_dry_run_score": 80,
                        "coverage_score": 75,
                        "coverage_missing": ["path: samuel/core/other.py"],
                        "overall_pass": True,
                        "retry_attempt": 0,
                        "blocking_failures": [],
                        "complexity": {
                            "ac_count": 5,
                            "file_count": 3,
                            "slice_count": 2,
                            "pflicht_bereich_count": 3,
                            "recommendation": "ok",
                        },
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(238, str(tmp_path))
        assert d is not None
        pc = d["pre_check"]
        assert pc["structural"] == 100
        assert pc["skeleton"] == 100
        assert pc["ac_dry_run"] == 80
        assert pc["coverage"] == 75
        assert pc["coverage_missing"] == ["path: samuel/core/other.py"]
        assert pc["overall_pass"] is True
        cx = d["complexity"]
        assert cx["ac_count"] == 5
        assert cx["recommendation"] == "ok"

    def test_complexity_warn_anomaly(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanComplexityWarn",
                        "issue": 238,
                        "evt": "complexity_warn",
                        "ac_count": 12,
                        "file_count": 8,
                        "slice_count": 6,
                        "pflicht_bereich_count": 5,
                        "recommendation": "split_recommended",
                    },
                },
            ],
        )
        rows = get_runtime_anomalies(str(tmp_path), hours=24)
        assert any(r["event"] == "PlanComplexityWarn" for r in rows)

    def test_failed_retry_is_terminal_and_keeps_pre_check_reason(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanPreCheckCompleted",
                        "issue": 655,
                        "structural_score": 100,
                        "skeleton_score": 100,
                        "ac_dry_run_score": 100,
                        "coverage_score": 0,
                        "coverage_missing": ["path: samuel/core/other.py"],
                        "overall_pass": False,
                        "retry_attempt": 1,
                        "blocking_failures": ["coverage: path: samuel/core/other.py"],
                        "complexity": {"recommendation": "ok"},
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanBlocked",
                        "issue": 655,
                        "evt": "plan_pre_check_blocked",
                        "reason": "pre_check_failed",
                        "overall_pass": False,
                        "retry_attempt": 1,
                    },
                },
            ],
        )

        detail = get_workflow_issue_detail(655, str(tmp_path))

        assert detail is not None
        assert detail["pre_check"]["coverage"] == 0
        assert detail["pre_check"]["retry_attempt"] == 1
        assert detail["stages"]["plan"]["status"] == "failed"
        assert detail["stages"]["plan"]["reason"] == "pre_check_failed"


class TestAcceptanceChecks:
    """#236: ACVerified/ACFailed-Events erscheinen im Dashboard
    workflow-issue-detail.acceptance_checks-Slot."""

    def test_acceptance_checks_in_workflow_detail(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ACVerified",
                        "issue": 236,
                        "tag": "DIFF",
                        "arg": "handler.py",
                        "passed": True,
                        "reason": "exists: handler.py",
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ACFailed",
                        "issue": 236,
                        "tag": "DIFF",
                        "arg": "missing.py",
                        "passed": False,
                        "reason": "not found: missing.py",
                    },
                },
                {
                    "ts": "t3",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ACManualPending",
                        "issue": 236,
                        "tag": "MANUAL",
                        "arg": "UI visually pruefen",
                        "passed": None,
                        "reason": "manual check required: UI visually pruefen",
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(236, str(tmp_path))
        assert d is not None
        checks = d["acceptance_checks"]
        assert len(checks) == 3
        passed_check = next(c for c in checks if c["tag"] == "DIFF" and c["arg"] == "handler.py")
        assert passed_check["passed"] is True
        assert passed_check["status"] == "passed"
        failed_check = next(c for c in checks if c["arg"] == "missing.py")
        assert failed_check["passed"] is False
        assert failed_check["status"] == "failed"
        assert "not found" in failed_check["reason"]
        manual_check = next(c for c in checks if c["tag"] == "MANUAL")
        assert manual_check["passed"] is None
        assert manual_check["status"] == "manual_pending"


class TestOwaspClassification:
    def test_owasp_classification_in_audit_trail(self, tmp_path: Path) -> None:
        """Events ohne payload.owasp_risk bekommen OWASP via classify(cat, evt)."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "TestRunCompleted",
                        "issue": 251,
                        "evt": "test_failed",
                        "passed": False,
                    },
                },
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",
                        "issue": 251,
                    },
                },
            ],
        )
        d = get_workflow_issue_detail(251, str(tmp_path))
        assert d is not None
        events = d["events"]
        owasps = [e["owasp"] for e in events]
        # Both entries get a non-empty OWASP via classify fallback
        assert all(o != "" for o in owasps), f"Empty OWASP found: {owasps}"
        # #290: eval/test_failed maps to cascading_failures (ASI08)
        eval_e = next((e for e in events if e["event"] == "TestRunCompleted"), None)
        assert eval_e is not None
        assert eval_e["owasp"] == "cascading_failures"

    def test_owasp_passes_payload_value_when_set(self, tmp_path: Path) -> None:
        """Wenn payload.owasp_risk gesetzt ist, hat es Vorrang vor classify."""
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "issue": 252,
                        "owasp_risk": "A05:2021",
                        "gate": 8,
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",  # info → skip
                    },
                },
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "reason": "x",
                    },
                },
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalFailed",
                        "reason": "y",
                    },
                },
            ],
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": old,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "reason": "old gate",
                    },
                },
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                        "reason": "fresh gate",
                    },
                },
            ],
        )
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
        cfg = _Cfg(
            {
                "llm.default.provider": "deepseek",
                "llm.deepseek.model": "deepseek-chat",
            }
        )
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
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "EvalCompleted",
                        "score": 0.8,
                        "baseline": 0.5,
                    },
                },
            ],
        )
        tiles = get_system_tiles(str(tmp_path))
        ev = next(t for t in tiles if t["key"] == "eval")
        assert ev["kind"] == "ok"
        assert "0.8" in ev["value"] and "0.5" in ev["value"]

    def test_errors_24h_tile_counts_recent_errors(self, tmp_path: Path) -> None:
        recent = datetime.now(timezone.utc).isoformat()
        _write_audit(
            tmp_path,
            [
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "GateFailed",
                    },
                },
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "WorkflowAborted",
                    },
                },
                {
                    "ts": recent,
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PlanCreated",  # not an error
                    },
                },
            ],
        )
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
        _d._VALIDATION_CACHE["provY"] = (
            ts0 - _d._VALIDATION_TTL_SECONDS - 1,
            _d._VALIDATION_CACHE["provY"][1],
        )
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
        _write_audit(
            tmp_path,
            [
                # Run A — failed (GateFailed)
                _evt("2026-05-01T09:12", "IssueReady", 42, "run-A"),
                _evt("2026-05-01T09:13", "PlanCreated", 42, "run-A"),
                _evt(
                    "2026-05-01T09:18", "GateFailed", 42, "run-A", gate=1, reason="branch is main"
                ),
                _evt("2026-05-01T09:19", "WorkflowBlocked", 42, "run-A"),
                # Run B — succeeded
                _evt("2026-05-01T14:22", "IssueReady", 42, "run-B"),
                _evt("2026-05-01T14:25", "PlanCreated", 42, "run-B"),
                _evt("2026-05-01T14:28", "EvalCompleted", 42, "run-B", score=1.0),
                _evt("2026-05-01T14:29", "PRCreated", 42, "run-B", pr_number=275),
            ],
        )

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

    def test_pr_creation_failed_run_is_not_successful(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "GatesPassed", 516, "run-failed"),
                _evt(
                    "2026-05-01T09:01",
                    "PRCreationFailed",
                    516,
                    "run-failed",
                    reason="SCM did not confirm creation of a valid pull request",
                ),
            ],
        )

        runs = get_workflow_runs(516, str(tmp_path))

        assert len(runs) == 1
        assert runs[0]["final_status"] == "blocked"
        assert runs[0]["pr_number"] is None
        assert runs[0]["stages_failed"] == 1

    def test_rejected_implicit_replan_is_blocked_in_plan_stage(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt(
                    "2026-09-17T09:00",
                    "PlanReplanRejected",
                    53,
                    "run-rejected",
                    reason="active_plan_requires_explicit_replan",
                    owasp_risk="agent_goal_hijack",
                    ai_act_article="Art. 14",
                ),
            ],
        )

        runs = get_workflow_runs(53, str(tmp_path))
        detail = get_workflow_issue_detail(53, str(tmp_path))
        logs = get_log_entries(str(tmp_path))
        security = get_security_overview(str(tmp_path))

        assert len(runs) == 1
        assert runs[0]["final_status"] == "blocked"
        assert runs[0]["stages_failed"] == 1
        assert detail is not None
        assert detail["status"] == "blocked"
        assert detail["last_event"] == "PlanReplanRejected"
        assert detail["stages"]["plan"]["status"] == "failed"
        assert detail["events"][0]["owasp"] == "agent_goal_hijack"
        assert detail["events"][0]["ai_act"] == "Art. 14"
        assert logs[0]["level"] == "warn"
        assert logs[0]["category"] == "workflow"
        assert logs[0]["owasp"] == "agent_goal_hijack"
        asi01 = next(item for item in security["owasp"] if item["id"] == "ASI01")
        assert asi01["count"] == 1
        assert asi01["recent"][0]["event"] == "PlanReplanRejected"

    def test_gate_failure_without_terminal_outcome_remains_incomplete(
        self,
        tmp_path: Path,
    ) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "GateFailed", 516, "run-healing"),
                _evt("2026-05-01T09:01", "HealingAttemptStarted", 516, "run-healing"),
            ],
        )

        runs = get_workflow_runs(516, str(tmp_path))

        assert runs[0]["final_status"] == "incomplete"

    def test_passive_candidate_pending_success_and_failure_are_visible(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                _evt(
                    "2026-09-18T09:00",
                    "CandidateVerificationPending",
                    521,
                    "candidate-pending",
                    reason="provider evidence pending",
                ),
                _evt(
                    "2026-09-18T10:00",
                    "CandidateEvaluationCompleted",
                    521,
                    "candidate-complete",
                ),
                _evt(
                    "2026-09-18T11:00",
                    "CandidateEvaluationFailed",
                    521,
                    "candidate-failed",
                    reason="required gate failed",
                ),
            ],
        )

        runs = get_workflow_runs(521, str(tmp_path))
        detail = get_workflow_issue_detail(521, str(tmp_path))

        assert [run["final_status"] for run in runs] == ["incomplete", "evaluated", "blocked"]
        assert [run["stages_done"] for run in runs] == [0, 1, 0]
        assert detail is not None
        assert detail["status"] == "blocked"
        assert detail["last_event"] == "CandidateEvaluationFailed"
        assert detail["stages"]["gates"]["status"] == "failed"

    def test_provider_request_run_attempt_and_mutation_boundary_are_visible(
        self, tmp_path: Path
    ) -> None:
        request_key = "verification:sha256:" + "a" * 64
        _write_audit(
            tmp_path,
            [
                _evt(
                    "2026-09-18T09:00",
                    "ProviderVerificationRequested",
                    679,
                    "provider-run",
                    request_key=request_key,
                    provider_profile="gitea-reference-v1",
                    provider_profile_digest="sha256:" + "b" * 64,
                    provider_run={"run_id": "704", "attempt": 2},
                    mutation_authority="none",
                ),
                _evt(
                    "2026-09-18T09:01",
                    "ProviderVerificationPending",
                    679,
                    "provider-run",
                    request_key=request_key,
                    reason_code="provider_run_pending",
                    status="candidate_verification_pending",
                    provider_run={"run_id": "704", "attempt": 2},
                    mutation_authority="none",
                ),
            ],
        )

        detail = get_workflow_issue_detail(679, str(tmp_path))
        runs = get_workflow_runs(679, str(tmp_path))

        assert detail is not None
        assert detail["stages"]["gates"]["status"] == "pending"
        assert detail["provider_verifications"][-1] == {
            "timestamp": "2026-09-18T09:01",
            "event": "ProviderVerificationPending",
            "request_key": request_key,
            "profile": "",
            "profile_digest": "",
            "run_id": "704",
            "attempt": 2,
            "status": "candidate_verification_pending",
            "reason_code": "provider_run_pending",
            "mutation_authority": "none",
        }
        assert runs[0]["final_status"] == "incomplete"

    def test_subject_invalidation_revokes_earlier_pr_success(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-08-24T09:00", "GatesPassed", 515, "run-moved"),
                _evt(
                    "2026-08-24T09:01",
                    "PRCreated",
                    515,
                    "run-moved",
                    pr_number=42,
                ),
                _evt(
                    "2026-08-24T09:02",
                    "EvaluationSubjectInvalidated",
                    515,
                    "run-moved",
                    pr_number=42,
                ),
            ],
        )

        runs = get_workflow_runs(515, str(tmp_path))

        assert runs[0]["final_status"] == "blocked"
        assert runs[0]["stages_failed"] == 1

    def test_score_per_run(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "EvalFailed", 42, "run-A", score=0.4),
                _evt("2026-05-01T10:00", "EvalCompleted", 42, "run-B", score=0.9),
            ],
        )

        runs = get_workflow_runs(42, str(tmp_path))

        assert {r["run_id"]: r["score"] for r in runs} == {
            "run-A": 0.4,
            "run-B": 0.9,
        }

    def test_pr_number_attribution(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "PRCreated", 42, "run-A", pr_number=100),
                _evt("2026-05-01T10:00", "PRCreated", 42, "run-B", pr_number=200),
            ],
        )

        runs = get_workflow_runs(42, str(tmp_path))

        # PR is attributed to its own run, not bled across.
        assert {r["run_id"]: r["pr_number"] for r in runs} == {
            "run-A": 100,
            "run-B": 200,
        }

    def test_event_without_correlation_id_dropped(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "x",
                    "name": "AuditEvent",
                    "payload": {"message_name": "PRCreated", "issue": 42},
                },
                _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
            ],
        )

        runs = get_workflow_runs(42, str(tmp_path))

        assert len(runs) == 1
        assert runs[0]["run_id"] == "run-A"

    def test_other_issues_not_included(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
                _evt("2026-05-01T09:00", "PRCreated", 99, "run-X"),
            ],
        )

        runs = get_workflow_runs(42, str(tmp_path))

        assert [r["run_id"] for r in runs] == ["run-A"]

    def test_empty_when_no_events(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [])
        assert get_workflow_runs(42, str(tmp_path)) == []


class TestRecoveryTrendDetection:
    """#277: trend recovered/regressed is derived from the last two runs."""

    def test_failed_then_passed_is_recovered(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "WorkflowBlocked", 42, "run-A"),
                _evt("2026-05-01T10:00", "PRCreated", 42, "run-B"),
            ],
        )
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert detail["trend"] == "recovered"

    def test_passed_then_failed_is_regressed(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
                _evt("2026-05-01T10:00", "WorkflowBlocked", 42, "run-B"),
            ],
        )
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert detail["trend"] == "regressed"

    def test_passed_passed_is_passed(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
                _evt("2026-05-01T10:00", "PRCreated", 42, "run-B"),
            ],
        )
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert detail["trend"] == "passed"

    def test_failed_failed_is_failed(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "WorkflowBlocked", 42, "run-A"),
                _evt("2026-05-01T10:00", "WorkflowBlocked", 42, "run-B"),
            ],
        )
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert detail["trend"] == "failed"

    def test_single_run_has_no_trend(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "PRCreated", 42, "run-A"),
            ],
        )
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert detail["trend"] == ""


class TestWorkflowIssueDetailIncludesRunsSlot:
    """#277-AC: detail dict carries the runs[] aggregate."""

    def test_runs_slot_present(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "PRCreated", 42, "run-A", pr_number=10),
            ],
        )
        detail = get_workflow_issue_detail(42, str(tmp_path))
        assert detail is not None
        assert "runs" in detail
        assert len(detail["runs"]) == 1
        assert detail["runs"][0]["pr_number"] == 10
        assert "trend" in detail


class TestWorkflowIssuesIncludesRunsCount:
    """#277: Workflow-Tab listet runs_count + trend pro Issue."""

    def test_runs_count_matches_distinct_correlation_ids(
        self,
        tmp_path: Path,
    ) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-05-01T09:00", "WorkflowBlocked", 42, "run-A"),
                _evt("2026-05-01T10:00", "PRCreated", 42, "run-B"),
                _evt("2026-05-01T10:00", "PRCreated", 99, "run-X"),
            ],
        )
        rows = get_workflow_issues(str(tmp_path))
        by_num = {r["number"]: r for r in rows}
        assert by_num[42]["runs_count"] == 2
        assert by_num[42]["trend"] == "recovered"
        assert by_num[99]["runs_count"] == 1
        assert by_num[99]["trend"] == ""


class TestWorkflowIssueStateReduction:
    """#738: delivery order must not masquerade as workflow causality."""

    def test_synchronous_issue_ready_audit_does_not_downgrade_plan(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-09-01T10:02:00+00:00", "PlanPosted", 32, "run-d0"),
                _evt("2026-09-01T10:03:00+00:00", "PlanValidated", 32, "run-d0"),
                # The outer seed dispatch is audited physically last even
                # though its event timestamp predates the nested plan facts.
                _evt("2026-09-01T10:00:00+00:00", "IssueReady", 32, "run-d0"),
            ],
        )

        row = get_workflow_issues(str(tmp_path))[0]
        detail = get_workflow_issue_detail(32, str(tmp_path))

        assert detail is not None
        assert row["status"] == detail["status"] == "planned"
        assert row["last_event"] == detail["last_event"] == "PlanValidated"
        assert row["timestamp"] == detail["status_timestamp"] == ("2026-09-01T10:03:00+00:00")
        assert detail["runs"][0]["final_status"] == "incomplete"

    def test_normal_chronological_plan_order_has_same_projection(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-09-01T10:00:00+00:00", "IssueReady", 33, "run-normal"),
                _evt("2026-09-01T10:01:00+00:00", "PlanCreated", 33, "run-normal"),
                _evt("2026-09-01T10:02:00+00:00", "PlanPosted", 33, "run-normal"),
                _evt("2026-09-01T10:03:00+00:00", "PlanValidated", 33, "run-normal"),
            ],
        )

        row = get_workflow_issues(str(tmp_path))[0]
        detail = get_workflow_issue_detail(33, str(tmp_path))

        assert detail is not None
        assert row["status"] == detail["status"] == "planned"
        assert row["last_event"] == detail["last_event"] == "PlanValidated"

    def test_seed_trigger_cannot_downgrade_later_phases(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-09-01T11:02:00+00:00", "CodeGenerated", 34, "run-code"),
                _evt("2026-09-01T11:00:00+00:00", "IssueReady", 34, "run-code"),
                _evt("2026-09-01T12:02:00+00:00", "WorkflowBlocked", 35, "run-block"),
                _evt("2026-09-01T12:00:00+00:00", "IssueReady", 35, "run-block"),
                _evt("2026-09-01T13:02:00+00:00", "PRCreated", 36, "run-pr"),
                _evt("2026-09-01T13:00:00+00:00", "IssueReady", 36, "run-pr"),
            ],
        )

        rows = {row["number"]: row for row in get_workflow_issues(str(tmp_path))}

        assert (rows[34]["status"], rows[34]["last_event"]) == (
            "implemented",
            "CodeGenerated",
        )
        assert (rows[35]["status"], rows[35]["last_event"]) == (
            "blocked",
            "WorkflowBlocked",
        )
        assert (rows[36]["status"], rows[36]["last_event"]) == (
            "pr_created",
            "PRCreated",
        )

    def test_new_ambiguous_run_does_not_inherit_old_success(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _evt("2026-09-01T09:00:00+00:00", "PRCreated", 37, "old-run"),
                _evt("2026-09-01T14:00:00+00:00", "PlanIssue", 37, "new-run"),
            ],
        )

        row = get_workflow_issues(str(tmp_path))[0]
        detail = get_workflow_issue_detail(37, str(tmp_path))

        assert detail is not None
        assert row["status"] == detail["status"] == "unknown"
        assert row["last_event"] == detail["last_event"] == "PlanIssue"
        assert row["runs_count"] == len(detail["runs"]) == 2


def _llm(issue, provider, model, task, ts):
    return {
        "ts": ts,
        "name": "AuditEvent",
        "payload": {
            "message_name": "LLMCallCompleted",
            "provider": provider,
            "model": model,
            "task": task,
            "issue": issue,
        },
    }


def _eval(issue, score, passed, ts):
    return {
        "ts": ts,
        "name": "AuditEvent",
        "payload": {
            "message_name": "EvalCompleted" if passed else "EvalFailed",
            "issue": issue,
            "score": score,
        },
    }


class TestGetQualityFromLog:
    """#153: Korrelation ueber issue (statt correlation_id) + last-call-Regel."""

    def test_eval_attributed_to_last_call_of_issue(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _llm(50, "deepseek", "chat", "planning", "t1"),
                _llm(50, "deepseek", "chat", "implementation", "t2"),
                _eval(50, 0.9, True, "t3"),
            ],
        )
        rows = get_quality_from_log(str(tmp_path))
        by_task = {r["task"]: r for r in rows}
        # Nur die Implementation als letzter Call ist der Evalserie zugeordnet.
        assert by_task["implementation"]["graded"] == 1
        assert by_task["implementation"]["calls"] == 1
        assert by_task["implementation"]["passed"] == 1
        assert by_task["implementation"]["avg_score"] == 0.9
        assert by_task["planning"]["graded"] == 0
        assert by_task["planning"]["calls"] == 0
        assert by_task["planning"]["unattributed_calls"] == 1

    def test_correlation_survives_high_frequency_noise(self, tmp_path: Path) -> None:
        # Regression: LLM/Eval-Events dürfen nicht aus dem Lese-Fenster fallen,
        # wenn danach viele hochfrequente Events (HealthCheck) folgen. Sonst
        # bliebe der Quality-Tab faelschlich leer, obwohl die Daten im Log sind.
        noise = [
            {"ts": f"t9{i:04d}", "name": "AuditEvent", "payload": {"message_name": "HealthCheck"}}
            for i in range(800)
        ]
        _write_audit(
            tmp_path,
            [
                _llm(50, "deepseek", "chat", "implementation", "t1"),
                _eval(50, 0.9, True, "t2"),
                *noise,
            ],
        )
        rows = get_quality_from_log(str(tmp_path))  # Default-Limit
        impl = [r for r in rows if r["task"] == "implementation"]
        assert impl and impl[0]["graded"] == 1 and impl[0]["avg_score"] == 0.9

    def test_failed_eval_counts_as_failed(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _llm(60, "p", "m", "impl", "t1"),
                _eval(60, 0.3, False, "t2"),
            ],
        )
        r = get_quality_from_log(str(tmp_path))[0]
        assert r["failed"] == 1
        assert r["success_rate_pct"] == 0

    def test_call_without_eval_is_explicitly_unattributed(self, tmp_path: Path) -> None:
        _write_audit(tmp_path, [_llm(70, "p", "m", "impl", "t1")])
        r = get_quality_from_log(str(tmp_path))[0]
        assert r["calls"] == 0
        assert r["unattributed_calls"] == 1
        assert r["other_series_calls"] == 0
        assert r["graded"] == 0
        assert r["success_rate_pct"] is None

    def test_empty(self, tmp_path: Path) -> None:
        assert get_quality_from_log(str(tmp_path)) == []

    def test_bound_quality_presence_excludes_legacy_issue_outcomes(self, tmp_path: Path) -> None:
        bound = {
            "ts": "t4",
            "name": "AuditEvent",
            "payload": {
                "message_name": "ScoreObserved",
                "issue": 2,
                "score": 1.0,
                "label": "Nicht bindende Qualitätsbeobachtung",
                "non_binding": True,
                "evidence_origin": "bound_acceptance_evidence",
                "observation_key": "sha256:" + "a" * 64,
                "score_key": "sha256:" + "b" * 64,
                "scoring_policy_version": "eval.v1",
                "scoring_policy_digest": "sha256:" + "c" * 64,
                "formula_version": "bound.v1",
            },
        }
        _write_audit(
            tmp_path,
            [
                _llm(1, "p", "m", "impl", "t1"),
                _eval(1, 0.0, False, "t2"),
                _llm(2, "p", "m", "impl", "t3"),
                bound,
            ],
        )

        row = get_quality_from_log(str(tmp_path))[0]
        assert row["calls"] == 1
        assert row["other_series_calls"] == 1
        assert row["unattributed_calls"] == 0
        assert row["graded"] == 0
        assert row["avg_score"] == 1.0
        assert row["evidence_origin"] == "bound_acceptance_evidence"
        assert row["scoring_policy_version"] == "eval.v1"
        assert row["formula_version"] == "bound.v1"

    def test_legacy_policy_formula_and_unattributed_calls_never_mix(self, tmp_path: Path) -> None:
        def call(issue: int, correlation_id: str, ts: str) -> dict:
            event: dict[str, Any] = _llm(issue, "p", "m", "impl", ts)
            event["payload"]["correlation_id"] = correlation_id
            return event

        def observed(
            issue: int,
            correlation_id: str,
            score: float,
            policy: str,
            formula: str,
            ts: str,
        ) -> dict:
            return {
                "ts": ts,
                "name": "AuditEvent",
                "payload": {
                    "message_name": "ScoreObserved",
                    "issue": issue,
                    "score": score,
                    "correlation_id": correlation_id,
                    "label": "Nicht bindende Qualitätsbeobachtung",
                    "non_binding": True,
                    "evidence_origin": "bound_acceptance_evidence",
                    "observation_key": "sha256:" + f"{issue:x}" * 64,
                    "score_key": "sha256:" + f"{issue + 5:x}" * 64,
                    "scoring_policy_version": policy,
                    "scoring_policy_digest": "sha256:" + "c" * 64,
                    "formula_version": formula,
                },
            }

        legacy_eval = _eval(1, 0.0, False, "t2")
        legacy_eval["payload"]["correlation_id"] = "legacy"
        _write_audit(
            tmp_path,
            [
                call(1, "legacy", "t1"),
                legacy_eval,
                call(2, "policy-1", "t3"),
                observed(2, "policy-1", 1.0, "policy.v1", "formula.v1", "t4"),
                call(3, "policy-2", "t5"),
                observed(3, "policy-2", 0.2, "policy.v2", "formula.v1", "t6"),
                call(4, "formula-2", "t7"),
                observed(4, "formula-2", 0.8, "policy.v2", "formula.v2", "t8"),
                call(5, "no-evaluation", "t9"),
            ],
        )

        issue_row = get_quality_from_log(str(tmp_path))[0]
        correlation_row = get_llm_quality_scores(str(tmp_path))[0]
        for row in (issue_row, correlation_row):
            assert row["calls"] == 1
            assert row["other_series_calls"] == 3
            assert row["unattributed_calls"] == 1
            assert row["avg_score"] == 0.8
            assert row["evidence_origin"] == "bound_acceptance_evidence"
            assert row["scoring_policy_version"] == "policy.v2"
            assert row["formula_version"] == "formula.v2"

        class _Reg:
            def aggregates(self):
                return [
                    {
                        "provider": "p",
                        "model": "m",
                        "task": "impl",
                        "evidence_origin": origin,
                        "scoring_policy_version": policy,
                        "formula_version": formula,
                        "ewma_score": score,
                        "last_ts": ts,
                    }
                    for origin, policy, formula, score, ts in (
                        ("unbound_worktree", "legacy", "legacy", 0.0, "t2"),
                        (
                            "bound_acceptance_evidence",
                            "policy.v1",
                            "formula.v1",
                            1.0,
                            "t4",
                        ),
                        (
                            "bound_acceptance_evidence",
                            "policy.v2",
                            "formula.v1",
                            0.2,
                            "t6",
                        ),
                        (
                            "bound_acceptance_evidence",
                            "policy.v2",
                            "formula.v2",
                            0.8,
                            "t8",
                        ),
                    )
                ]

        overview = get_quality_overview(str(tmp_path), registry=_Reg())
        assert overview["matrix"][0]["ewma_score"] == 0.8
        assert overview["heatmap"]["rows"][0]["cells"] == [0.8]
        assert overview["selected_series"] == {
            "evidence_origin": "bound_acceptance_evidence",
            "observation_schema": "bound.v1",
            "scoring_policy_version": "policy.v2",
            "formula_version": "formula.v2",
        }
        assert overview["attribution"] == {
            "series_calls": 1,
            "unattributed_calls": 1,
            "other_series_calls": 3,
        }


class TestBuildQualityHeatmap:
    def test_pivot_provider_model_by_task(self) -> None:
        rows = [
            {"provider": "p", "model": "m", "task": "plan", "avg_score": 0.8},
            {"provider": "p", "model": "m", "task": "impl", "avg_score": 0.5},
            {"provider": "q", "model": "n", "task": "plan", "avg_score": 1.0},
        ]
        hm = build_quality_heatmap(rows)
        assert hm["tasks"] == ["impl", "plan"]
        pm = {(r["provider"], r["model"]): r["cells"] for r in hm["rows"]}
        assert pm[("p", "m")] == [0.5, 0.8]  # impl, plan
        assert pm[("q", "n")] == [None, 1.0]  # kein impl fuer q/n


class TestGetQualityOverview:
    def test_selected_series_remains_visible_without_attributable_call(
        self, tmp_path: Path
    ) -> None:
        _write_audit(
            tmp_path,
            [
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ScoreObserved",
                        "issue": 2,
                        "score": 1.0,
                        "label": "Nicht bindende Qualitätsbeobachtung",
                        "non_binding": True,
                        "evidence_origin": "bound_acceptance_evidence",
                        "observation_key": "sha256:" + "a" * 64,
                        "score_key": "sha256:" + "b" * 64,
                        "scoring_policy_version": "eval.v1",
                        "scoring_policy_digest": "sha256:" + "c" * 64,
                        "formula_version": "bound.v1",
                    },
                }
            ],
        )

        overview = get_quality_overview(str(tmp_path))
        assert overview["matrix"] == []
        assert overview["selected_series"] == {
            "evidence_origin": "bound_acceptance_evidence",
            "observation_schema": "bound.v1",
            "scoring_policy_version": "eval.v1",
            "formula_version": "bound.v1",
        }

    def test_overview_merges_registry_ewma_and_warns(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _llm(80, "ollama", "llama3:3b", "impl", "t1"),
                _eval(80, 1.0, True, "t2"),
            ],
        )

        class _Reg:
            def aggregates(self):
                return [
                    {"provider": "ollama", "model": "llama3:3b", "task": "impl", "ewma_score": 0.66}
                ]

        ov = get_quality_overview(str(tmp_path), min_params_b=7, registry=_Reg())
        assert ov["min_params_b"] == 7
        row = ov["matrix"][0]
        assert row["ewma_score"] == 0.66
        # 3b lokales Modell < 7 -> Warnung
        assert any(
            w["model"] == "llama3:3b" and w["reason"] == "below_min" for w in ov["param_warnings"]
        )
        assert ov["heatmap"]["tasks"] == ["impl"]

    def test_overview_never_overlays_legacy_ewma_on_bound_rows(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                _llm(2, "p", "m", "impl", "t1"),
                {
                    "ts": "t2",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "ScoreObserved",
                        "issue": 2,
                        "score": 1.0,
                        "label": "Nicht bindende Qualitätsbeobachtung",
                        "non_binding": True,
                        "evidence_origin": "bound_acceptance_evidence",
                        "observation_key": "sha256:" + "a" * 64,
                        "score_key": "sha256:" + "b" * 64,
                        "scoring_policy_version": "eval.v1",
                        "scoring_policy_digest": "sha256:" + "c" * 64,
                        "formula_version": "bound.v1",
                    },
                },
            ],
        )

        class _Reg:
            def aggregates(self):
                return [
                    {
                        "provider": "p",
                        "model": "m",
                        "task": "impl",
                        "evidence_origin": "unbound_worktree",
                        "scoring_policy_version": "legacy",
                        "formula_version": "legacy",
                        "ewma_score": 0.1,
                    },
                    {
                        "provider": "p",
                        "model": "m",
                        "task": "impl",
                        "evidence_origin": "bound_acceptance_evidence",
                        "scoring_policy_version": "eval.v1",
                        "formula_version": "bound.v1",
                        "ewma_score": 0.9,
                    },
                ]

        row = get_quality_overview(str(tmp_path), registry=_Reg())["matrix"][0]
        assert row["evidence_origin"] == "bound_acceptance_evidence"
        assert row["ewma_score"] == 0.9


class TestGetScmActivity:
    """#230/#390: SCM-Activity-Stream aus dem Audit-Log."""

    def _act(self, ts, name, number, actor_type):
        return {
            "ts": ts,
            "name": "AuditEvent",
            "payload": {
                "message_name": name,
                "number": number,
                "actor": "x",
                "actor_type": actor_type,
                "source": "webhook",
            },
        }

    def test_filters_and_sorts_scm_events(self, tmp_path: Path) -> None:
        _write_audit(
            tmp_path,
            [
                self._act("t1", "IssueOpened", 1, "human"),
                {
                    "ts": "t1b",
                    "name": "AuditEvent",
                    "payload": {"message_name": "LLMCallCompleted"},
                },
                self._act("t2", "PullRequestMerged", 2, "bot"),
                self._act("t3", "IssueClosed", 1, "human"),
            ],
        )
        rows = get_scm_activity(str(tmp_path))
        # nur SCM-Events, neueste zuerst
        assert [r["event"] for r in rows] == ["IssueClosed", "PullRequestMerged", "IssueOpened"]
        assert rows[0]["label"] == "Issue geschlossen"
        assert rows[1]["actor_type"] == "bot"

    def test_empty(self, tmp_path: Path) -> None:
        assert get_scm_activity(str(tmp_path)) == []

    def test_polling_event_uses_original_scm_timestamp(self, tmp_path: Path) -> None:
        event = self._act("audit-time", "IssueOpened", 390, "human")
        event["payload"]["source"] = "polling"
        event["payload"]["timestamp"] = "2026-08-21T10:00:00Z"
        _write_audit(tmp_path, [event])

        rows = get_scm_activity(str(tmp_path))

        assert rows[0]["ts"] == "2026-08-21T10:00:00Z"
        assert rows[0]["source"] == "polling"
