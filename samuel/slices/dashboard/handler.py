from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.ports import IConfig, IVersionControl
from samuel.slices.dashboard.data import (
    KNOWN_FEATURE_FLAGS,
    get_api_key_status,
    get_branches,
    get_command_metrics,
    get_compliance_legend,
    get_feature_flags,
    get_llm_quality_scores,
    get_llm_routing,
    get_llm_routing_schedule,
    get_llm_usage,
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
)

log = logging.getLogger(__name__)


class DashboardHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config: IConfig | None = None,
        transfer_warning_fn: Callable[[], list[dict[str, Any]]] | None = None,
        balance_resolver: Callable[[str, str | None, str | None],
                                    tuple[float | None, str]] | None = None,
        connection_tester: Callable[[str, dict], dict[str, Any]] | None = None,
        prompt_source_resolver: Callable[
            [str, str, str | None, str | None, dict | None], dict[str, Any],
        ] | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._config = config
        self._transfer_warning_fn = transfer_warning_fn
        # #311-followup: balance_resolver wird vom Wiring (server.py) injiziert.
        # Slice-Iso (test_no_direct_adapter_usage) verbietet hier den Adapter-Import.
        self._balance_resolver = balance_resolver
        # #314: connection_tester ebenfalls aus dem Wiring — baut den Adapter mit
        # Form-Werten + ruft validate(). Slice darf weder factory noch adapter
        # direkt importieren.
        self._connection_tester = connection_tester
        # #348: prompt_source_resolver — wired auf
        # samuel.adapters.llm.prompts.resolve_prompt_source. Auch hier:
        # Slice-Iso erlaubt keinen direkten Adapter-Import in data.py.
        self._prompt_source_resolver = prompt_source_resolver

    def get_transfer_warnings(self) -> list[dict[str, Any]]:
        if self._transfer_warning_fn:
            return self._transfer_warning_fn()
        return []

    def get_status(self) -> dict[str, Any]:
        metrics = self._get_metrics()
        transfer_warnings = self.get_transfer_warnings()
        warnings = [w for w in transfer_warnings if w.get("warning")]
        mode = self._config.get("agent.mode", "standard") if self._config else "standard"
        self_mode = bool(self._config.get("agent.self_mode", False)) if self._config else False
        data_dir = self._data_dir()
        # #277: Recovered Issues = Anzahl Issues, deren letzter Run erfolgreich
        # war nachdem mind. ein vorheriger Run gescheitert war (Self-Healing-
        # Indikator fuer den Status-Tab).
        recovered = sum(
            1 for i in get_workflow_issues(data_dir) if i.get("trend") == "recovered"
        )
        return {
            "mode": mode,
            "self_mode": self_mode,
            "scm_connected": self._scm is not None,
            "metrics": metrics,
            "transfer_warnings": warnings,
            "tiles": get_system_tiles(data_dir, config=self._config, scm=self._scm),
            "score_history": get_score_history(data_dir),
            "anomalies": get_runtime_anomalies(data_dir),
            "recovered_count": recovered,
        }

    def get_health(self) -> dict[str, Any]:
        """#194: Vollstaendige Gesundheits-Pruefung via HealthCheckCommand.

        Frueher lieferte diese Methode nur ``{scm, config}``. Seit #194 zieht sie
        ihre Daten aus ``get_self_check()``, sodass ``/api/v1/dashboard/health``
        und der Self-Check-Tab dieselbe Quelle nutzen (LLM-Adapter, Audit-Sink,
        Workflow-Engine, Quality-Registry, Metering, Idempotency-Store — alles
        was der ``HealthCheckCommand`` einsammelt).

        Schema bleibt backward-compatible (``checks`` als dict), damit Frontend
        + bestehende Tests nicht brechen.
        """
        full = self.get_self_check()
        checks_dict = {
            c["name"]: c.get("status") == "OK"
            for c in full.get("checks", [])
            if isinstance(c, dict) and c.get("name")
        }
        return {
            "healthy": bool(full.get("healthy", False)),
            "checks": checks_dict,
        }

    def get_metrics(self) -> dict[str, Any]:
        return self._get_metrics()

    def _data_dir(self) -> str:
        if self._config:
            return str(self._config.get("agent.data_dir", "data"))
        return "data"

    def _get_metrics(self) -> dict[str, Any]:
        return get_command_metrics(self._data_dir())

    def get_logs(self) -> dict[str, Any]:
        """Return formatted audit log entries wrapped in ``entries`` plus
        ``level_counts`` (info/warn/error) for the Stat-Tiles."""
        data_dir = self._data_dir()
        return {
            "entries": get_log_entries(data_dir),
            "level_counts": get_log_level_counts(data_dir),
        }

    def get_security(self) -> dict[str, Any]:
        """Return OWASP overview, tamper alerts, OTel gen_ai calls, and
        branch-protection status (#209)."""
        data_dir = self._data_dir()
        overview = get_security_overview(data_dir)
        overview["tamper_events"] = get_tamper_events(data_dir)
        overview["otel_calls"] = get_otel_gen_ai_calls(data_dir)
        overview["branch_protection"] = self._get_branch_protection_status()
        return overview

    def _get_branch_protection_status(self) -> dict[str, Any]:
        """#209: query the SCM for protection on the default branch.

        Always returns a dict so the frontend can render a tile without
        null-checks. Fields:
        - ``available``: SCM is wired and supports the call
        - ``protected``: branch has at least one rule attached
        - ``branch``: the branch name that was queried
        - ``rules``: raw SCM payload (or None)
        - ``error`` (optional): set on request failure
        """
        branch = "main"
        if self._config:
            branch = str(self._config.get("agent.default_branch", "main"))
        if not self._scm:
            return {
                "available": False, "protected": False,
                "branch": branch, "rules": None,
            }
        if "branch_protection" not in (self._scm.capabilities or set()):
            return {
                "available": False, "protected": False,
                "branch": branch, "rules": None,
            }
        try:
            result = self._scm.get_branch_protection(branch)
        except Exception:
            log.warning("get_branch_protection failed", exc_info=True)
            return {
                "available": True, "protected": False,
                "branch": branch, "rules": None, "error": "request_failed",
            }
        if result is None:
            return {
                "available": True, "protected": False,
                "branch": branch, "rules": None,
            }
        return {
            "available": True, "protected": True,
            "branch": result.get("branch", branch),
            "rules": result.get("rules"),
        }

    def get_compliance_legend(self) -> dict[str, list[dict[str, Any]]]:
        """Return OWASP Top-10 Agentic AI + EU AI Act article descriptions.

        Static data (sourced from ``samuel.core.owasp``/``samuel.core.ai_act``)
        — exposed via dashboard so operators can resolve codes like ``A05``
        or ``Art. 14`` inline (#252).
        """
        return get_compliance_legend()

    def get_workflow(self) -> dict[str, Any]:
        """Return workflow issues and branch overview.

        #277: ``recovered_count`` is a summary signal — number of issues
        whose latest run passed after at least one previous failure.
        Useful as a self-healing-effectiveness indicator for the operator.
        """
        issues = get_workflow_issues(self._data_dir())
        recovered = sum(1 for i in issues if i.get("trend") == "recovered")
        return {
            "issues": issues,
            "branches": get_branches(),
            "recovered_count": recovered,
        }

    def get_workflow_detail(self, issue_number: int) -> dict[str, Any]:
        """Return per-issue audit trail, pipeline stages, score, LLM aggregation.

        Returns ``{"error": "..."}`` if the issue has no events in the audit
        log (so the HTTP layer can map to 404).
        """
        detail = get_workflow_issue_detail(int(issue_number), self._data_dir())
        if detail is None:
            return {"error": f"no audit events for issue #{issue_number}"}
        return detail

    def _config_dir(self) -> str:
        if self._config:
            return str(self._config.get("agent.config_dir", "config"))
        return "config"

    def get_llm(self) -> dict[str, Any]:
        """Return LLM token usage, cost, routing, schedule, history, quality,
        api-key-status, and active provider."""
        data_dir = self._data_dir()
        config_dir = self._config_dir()
        usage = get_llm_usage(data_dir)
        usage["routing"] = get_llm_routing(
            self._config, config_dir=config_dir,
            prompt_source_resolver=self._prompt_source_resolver,
        )
        usage["routing_schedule"] = get_llm_routing_schedule(self._config)
        usage["history"] = get_token_history(data_dir)
        usage["quality"] = get_llm_quality_scores(data_dir)
        usage["api_keys"] = get_api_key_status(config_dir)
        usage["provider"] = (
            str(self._config.get("llm.default.provider", "-")) if self._config else "-"
        )
        return usage

    def get_settings(self) -> dict[str, Any]:
        """Return feature flags, LLM config, premium status, and API-key status."""
        # #204: erweitert um llm_config / premium_status / api_keys fuer Settings-Tab
        from samuel.core import license as _lic
        config_dir = (
            str(self._config.get("agent.config_dir", "config"))
            if self._config else "config"
        )
        return {
            "flags":          get_feature_flags(self._config),
            "llm_config":     (
                get_llm_routing(
                    self._config, config_dir=config_dir,
                    prompt_source_resolver=self._prompt_source_resolver,
                )
                if self._config else []
            ),
            "premium_status": _lic.license_status(),
            # #311-followup: balance_resolver wird vom Wiring-Layer (server.py)
            # injiziert — Slice-Iso erlaubt keinen direkten Adapter-Import hier.
            "api_keys":       get_api_key_status(config_dir, balance_resolver=self._balance_resolver),
        }

    # #309: Per-Task LLM-Config Write — Premium-only `llm_routing_dashboard_write`.
    _CANONICAL_TASKS = frozenset({
        "planning", "implementation", "review", "healing", "evaluation",
    })
    _KNOWN_PROVIDERS = frozenset({
        "claude", "deepseek", "gemini", "openai", "openrouter",
        "ollama", "lmstudio", "manual",
    })
    _ALLOWED_FIELDS = frozenset({
        "provider", "model", "base_url", "timeout",
        "system_prompt", "max_tokens", "temperature",
        "schedule",  # #316
        "system_prompt_by_provider",  # #351 Hybrid: per-provider override map
    })

    @staticmethod
    def _validate_prompt_by_provider_map(
        m: Any,
        known_providers: frozenset,
    ) -> tuple[bool, str]:
        """#351: Validate ``system_prompt_by_provider`` map.

        Required when present:
          - dict mapping known-provider-name (lowercase) -> .md filename
          - filename: non-empty, ends with .md, no path separators / traversal
        Empty / None means "no map" — caller drops the field instead of storing.
        """
        if not isinstance(m, dict):
            return False, "system_prompt_by_provider must be a dict"
        for prov, name in m.items():
            if not isinstance(prov, str) or prov not in known_providers:
                return False, f"system_prompt_by_provider key not a known provider: {prov!r}"
            if not isinstance(name, str) or not name.strip():
                return False, f"system_prompt_by_provider value for {prov!r} must be non-empty string"
            if not name.endswith(".md"):
                return False, f"system_prompt_by_provider value for {prov!r} must end with .md"
            if "/" in name or "\\" in name or ".." in name:
                return False, f"system_prompt_by_provider value for {prov!r} contains path separator/traversal"
        return True, ""

    @staticmethod
    def _validate_schedule(schedule: Any) -> tuple[bool, str]:
        """#316: Validate the optional schedule sub-block.

        Required when present:
          - active: bool
          - from / to: HH:MM strings (24h)
          - provider: in _KNOWN_PROVIDERS
          - model: non-empty string
        """
        if not isinstance(schedule, dict):
            return False, "schedule must be a dict"
        active = schedule.get("active")
        if not isinstance(active, bool):
            return False, "schedule.active must be bool"
        # When inactive, only ``active=False`` is required — other fields are optional
        if not active:
            return True, ""
        for time_field in ("from", "to"):
            v = schedule.get(time_field)
            if not isinstance(v, str):
                return False, f"schedule.{time_field} must be HH:MM string"
            parts = v.split(":")
            if len(parts) != 2:
                return False, f"schedule.{time_field} invalid format: {v}"
            try:
                hh, mm = int(parts[0]), int(parts[1])
            except ValueError:
                return False, f"schedule.{time_field} invalid format: {v}"
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                return False, f"schedule.{time_field} out of range: {v}"
        prov = schedule.get("provider")
        if not isinstance(prov, str) or prov not in DashboardHandler._KNOWN_PROVIDERS:
            return False, f"schedule.provider unknown: {prov!r}"
        model = schedule.get("model")
        if not isinstance(model, str) or not model.strip():
            return False, "schedule.model must be a non-empty string"
        return True, ""

    def set_llm_task_config(self, task: str, cfg: dict) -> dict[str, Any]:
        """#309: Schreibe Per-Task-Config nach config/llm/defaults.json (atomar).

        Premium-only (`llm_routing_dashboard_write`). Empty-string/None values
        in cfg remove the field — UX-pattern fuer "Override entfernen".
        """
        import json as _json

        from samuel.core import license as _lic

        if not (_lic.is_premium_active()
                and _lic.has_feature("llm_routing_dashboard_write")):
            return {
                "updated": False,
                "error": "premium feature llm_routing_dashboard_write required",
            }
        if task not in self._CANONICAL_TASKS:
            return {"updated": False, "error": f"unknown task: {task}"}
        if not isinstance(cfg, dict):
            return {"updated": False, "error": "config must be a dict"}

        provider = cfg.get("provider")
        if provider and provider not in self._KNOWN_PROVIDERS:
            return {"updated": False, "error": f"unknown provider: {provider}"}

        # Reject unknown fields (silent drop would mask typos)
        unknown_fields = [k for k in cfg if k not in self._ALLOWED_FIELDS]
        if unknown_fields:
            return {
                "updated": False,
                "error": f"unknown fields: {', '.join(unknown_fields)}",
            }

        # #316: schedule-Block — require llm_routing_advanced + structural validation
        if "schedule" in cfg and cfg["schedule"] not in (None, ""):
            if not _lic.has_feature("llm_routing_advanced"):
                return {
                    "updated": False,
                    "error": "premium feature llm_routing_advanced required for schedule",
                }
            ok, err = self._validate_schedule(cfg["schedule"])
            if not ok:
                return {"updated": False, "error": err}

        # #351: per-provider override map — structural validation. Empty
        # value drops the field via the merge loop below (UX: clear-all).
        if (
            "system_prompt_by_provider" in cfg
            and cfg["system_prompt_by_provider"] not in (None, "", {})
        ):
            ok, err = self._validate_prompt_by_provider_map(
                cfg["system_prompt_by_provider"], self._KNOWN_PROVIDERS,
            )
            if not ok:
                return {"updated": False, "error": err}

        config_dir = (
            str(self._config.get("agent.config_dir", "config"))
            if self._config else "config"
        )
        from pathlib import Path as _Path
        fp = _Path(config_dir) / "llm" / "defaults.json"
        try:
            data = (_json.loads(fp.read_text(encoding="utf-8"))
                    if fp.exists() else {})
        except (OSError, _json.JSONDecodeError) as exc:
            return {
                "updated": False,
                "error": f"could not read defaults.json: {exc}",
            }

        tasks = data.setdefault("tasks", {})
        existing = tasks.get(task) if isinstance(tasks.get(task), dict) else {}
        merged = dict(existing)
        for k, v in cfg.items():
            if v in (None, "", {}):
                # #351: empty map for system_prompt_by_provider also drops field
                merged.pop(k, None)
            elif k == "schedule" and isinstance(v, dict) and v.get("active") is False:
                # #316: inactive schedule -> remove field instead of storing dead config
                merged.pop("schedule", None)
            else:
                merged[k] = v
        tasks[task] = merged

        # Atomic write: tmp + rename
        tmp = fp.with_suffix(".tmp")
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                _json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(fp)
        except OSError as exc:
            return {
                "updated": False,
                "error": f"could not write defaults.json: {exc}",
            }

        return {"updated": True, "task": task, "cfg": merged}

    def test_connection(self, provider: str, cfg: dict) -> dict[str, Any]:
        """#314: Test-Connection — baut temporaeren Adapter aus Form-Werten,
        ruft ``validate()``. Liefert ``{valid, detail, balance}``.

        Nicht premium-gated: Validation ist fuer alle nuetzlich, der Editor
        selbst ist premium-gated.
        """
        prov = (provider or "").lower()
        if prov not in self._KNOWN_PROVIDERS:
            return {"valid": False, "detail": f"unknown provider: {provider}", "balance": None}
        if self._connection_tester is None:
            return {
                "valid": False,
                "detail": "connection tester not wired",
                "balance": None,
            }
        if not isinstance(cfg, dict):
            return {"valid": False, "detail": "config must be a dict", "balance": None}
        clean = {k: v for k, v in cfg.items() if k in self._ALLOWED_FIELDS and v not in (None, "")}
        return self._connection_tester(prov, clean)

    def set_feature_flag(self, name: str, enabled: bool) -> dict[str, Any]:
        """Toggle a feature flag via in-memory config override.

        Override is NOT persisted to disk — it lasts for the process lifetime.
        """
        known_keys = {k for k, _, _ in KNOWN_FEATURE_FLAGS}
        if name not in known_keys:
            return {"updated": False, "error": f"unknown flag: {name}"}
        if self._config is None:
            return {"updated": False, "error": "config not available"}
        overrides = getattr(self._config, "_overrides", None)
        if overrides is None or not isinstance(overrides, dict):
            return {"updated": False, "error": "config does not support overrides"}
        overrides[f"features.{name}"] = bool(enabled)
        return {"updated": True, "name": name, "enabled": bool(enabled)}

    def get_self_mode_health(self, limit: int = 50) -> dict[str, Any]:
        """#319: Aggregierte Self-Mode-Health-Statistik aus jsonl-Metrics.

        Liest ``data/logs/self_mode_metrics.jsonl`` (geschrieben von
        ImplementationHandler), aggregiert die letzten ``limit`` Runs.
        Liefert Erfolgsquote, Durchschnitts-Rounds, Hang-Rate (no_progress),
        und die letzten 20 Run-Records fuer Detail-Tabelle.
        """
        import json as _json
        from pathlib import Path as _Path

        fp = _Path("data") / "logs" / "self_mode_metrics.jsonl"
        records: list[dict] = []
        if fp.is_file():
            try:
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(_json.loads(line))
                    except _json.JSONDecodeError:
                        continue
            except OSError:
                pass
        # Letzte ``limit`` Runs (chronologisch aelteste->neueste in der Datei)
        recent = records[-limit:]
        total = len(recent)
        if total == 0:
            return {
                "total":              0,
                "success_rate":       None,
                "no_progress_rate":   None,
                "avg_rounds":         None,
                "avg_duration_s":     None,
                "recent_runs":        [],
            }
        success_count = sum(1 for r in recent if r.get("success"))
        no_progress_count = sum(1 for r in recent if r.get("reason") == "no_progress")
        rounds_sum = sum(int(r.get("rounds", 0)) for r in recent)
        duration_sum = sum(float(r.get("duration_seconds", 0)) for r in recent)
        return {
            "total":              total,
            "success_rate":       round(success_count / total, 3),
            "no_progress_rate":   round(no_progress_count / total, 3),
            "avg_rounds":         round(rounds_sum / total, 2),
            "avg_duration_s":     round(duration_sum / total, 2),
            "recent_runs":        list(reversed(recent[-20:])),  # neueste zuerst
        }

    def get_self_check(self) -> dict[str, Any]:
        """Run HealthCheckCommand and return structured checks list.

        Each check: name, status (OK/FAIL), time (empty if not provided),
        detail (version / error / extra info). Also includes the agent mode.
        """
        result = self._bus.send(HealthCheckCommand(payload={})) or {}
        raw_checks = result.get("checks", {}) if isinstance(result, dict) else {}
        checks: list[dict[str, Any]] = []
        for name, val in raw_checks.items():
            if isinstance(val, dict):
                passed = bool(val.get("passed", False))
                detail_bits: list[str] = []
                for k, v in val.items():
                    if k == "passed":
                        continue
                    detail_bits.append(f"{k}={v}")
                detail = ", ".join(detail_bits)
            else:
                passed = bool(val)
                detail = ""
            checks.append({
                "name": name,
                "status": "OK" if passed else "FAIL",
                "time": "",
                "detail": detail,
            })
        mode = self._config.get("agent.mode", "standard") if self._config else "standard"
        self_mode = bool(self._config.get("agent.self_mode", False)) if self._config else False
        return {
            "mode": "self" if self_mode else mode,
            "healthy": bool(result.get("healthy", False)) if isinstance(result, dict) else False,
            "checks": checks,
        }

    def get_api_data(self, endpoint: str) -> dict[str, Any]:
        if endpoint == "status":
            return self.get_status()
        if endpoint == "health":
            return self.get_health()
        if endpoint == "metrics":
            return self.get_metrics()
        if endpoint == "transfer_warnings":
            return {"transfer_warnings": self.get_transfer_warnings()}
        if endpoint == "logs":
            return self.get_logs()
        if endpoint == "security":
            return self.get_security()
        if endpoint == "workflow":
            return self.get_workflow()
        if endpoint == "llm":
            return self.get_llm()
        if endpoint == "settings":
            return self.get_settings()
        if endpoint == "self_check":
            return self.get_self_check()
        return {"error": f"unknown endpoint: {endpoint}"}
