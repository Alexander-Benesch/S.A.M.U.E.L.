from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.configuration_mode import ConfigurationAuthority
from samuel.core.health_projection import snapshot as readiness_snapshot
from samuel.core.ports import IConfig, IVersionControl
from samuel.slices.dashboard.data import (
    KNOWN_FEATURE_FLAGS,
    get_api_key_status,
    get_branches,
    get_command_metrics,
    get_compliance_legend,
    get_dlq_entries,
    get_feature_flags,
    get_llm_quality_scores,
    get_llm_routing,
    get_llm_routing_schedule,
    get_llm_usage,
    get_log_entries,
    get_log_level_counts,
    get_otel_gen_ai_calls,
    get_problems,
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
)

log = logging.getLogger(__name__)


class DashboardHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        config: IConfig | None = None,
        transfer_warning_fn: Callable[[], list[dict[str, Any]]] | None = None,
        balance_resolver: Callable[[str, str | None, str | None], tuple[float | None, str]]
        | None = None,
        connection_tester: Callable[[str, dict], dict[str, Any]] | None = None,
        prompt_source_resolver: Callable[
            [str, str, str | None, str | None, dict | None],
            dict[str, Any],
        ]
        | None = None,
        model_quality_resolver: Callable[[str, str, float, float], dict[str, Any]] | None = None,
        model_cache_status_resolver: Callable[[], dict[str, Any]] | None = None,
        quality_registry: Any = None,
        observation_store: Any = None,
        run_projection_store: Any = None,
        product_version: str = "0+unknown",
        build_revision: str | None = None,
        build_dirty: bool | None = None,
        build_revision_source: str = "unavailable",
        configuration_authority: ConfigurationAuthority | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._config = config
        # #153: IQualityMetricsRegistry, vom Wiring (server.py) injiziert —
        # Slice-Iso erlaubt hier keinen direkten Adapter-Import.
        self._quality_registry = quality_registry
        self._observation_store = observation_store
        self._run_projection_store = run_projection_store
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
        # #425/#428: Adapter-owned OpenRouter metadata is resolved in the
        # wiring layer to preserve dashboard slice isolation.
        self._model_quality_resolver = model_quality_resolver
        self._model_cache_status_resolver = model_cache_status_resolver
        self._build_info: dict[str, str | bool | None] = {
            "product_version": product_version,
            "revision": build_revision,
            "dirty": build_dirty,
            "revision_source": build_revision_source,
        }
        config_dir = str(config.get("agent.config_dir", "config")) if config else "config"
        self._configuration_authority = configuration_authority or ConfigurationAuthority.resolve(
            config_dir
        )
        self._effective_extension_configuration = self._extension_configuration_snapshot()

    def configuration_status(self) -> dict[str, Any]:
        return self._configuration_authority.status()

    def configuration_mutation_blocked(self) -> dict[str, Any] | None:
        return self._configuration_authority.blocked_result()

    def mark_configuration_persisted(self) -> None:
        self._configuration_authority.mark_persisted()

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
            1
            for i in get_workflow_issues(data_dir, self._run_projection_store)
            if i.get("trend") == "recovered"
        )
        return {
            "build": dict(self._build_info),
            "mode": mode,
            "self_mode": self_mode,
            "scm_connected": self._scm is not None,
            "metrics": metrics,
            "transfer_warnings": warnings,
            "tiles": get_system_tiles(data_dir, config=self._config, scm=self._scm),
            "score_history": get_score_history(
                data_dir,
                observation_store=self._observation_store,
                projection_store=self._run_projection_store,
            ),
            "anomalies": get_runtime_anomalies(data_dir),
            "recovered_count": recovered,
            "resume": (
                self._bus.resume_coordinator.status()
                if self._bus.resume_coordinator is not None
                else {
                    "enabled": False,
                    "pending": 0,
                    "blocked": 0,
                    "last_outcome": {},
                }
            ),
        }

    def get_viewer_status(self) -> dict[str, Any]:
        """Return passive, content-poor status without reading logs or providers."""

        readiness = self._passive_readiness()
        return {
            "service": "samuel",
            "available": True,
            "product_version": self._build_info["product_version"],
            "access": "viewer",
            "technical_health": readiness["technical_health"]["status"],
            "operational_readiness": readiness["operational_readiness"]["status"],
            "qualification": readiness["qualification"]["status"],
        }

    def _passive_readiness(self) -> dict[str, Any]:
        instance_uuid = "unavailable"
        state_store = getattr(self._bus, "state_store", None)
        if state_store is not None:
            try:
                instance_uuid = str(state_store.status().authority_instance)
            except Exception as exc:  # noqa: BLE001 - passive status must remain bounded
                log.warning("Passive readiness state unavailable: %s", type(exc).__name__)
                instance_uuid = "unavailable"
        return readiness_snapshot(
            self._run_projection_store,
            instance_uuid=instance_uuid,
        )

    def get_health(self) -> dict[str, Any]:
        """Expose the latest passive technical projection without provider I/O."""
        projected = self._passive_readiness()
        technical = projected["technical_health"]
        summary = technical.get("summary", {})
        checks = summary.get("checks", {}) if isinstance(summary, dict) else {}
        retention: dict[str, Any] = {
            "schema": "samuel-retention-status.v1",
            "status": "not_checked",
            "retention_emergency_stop": True,
            "future_enforcement_blocked": True,
            "pending_review_count": 0,
            "categories": [],
            "last_execution": None,
            "findings": [],
        }
        coordinator = getattr(self._bus, "retention_coordinator", None)
        if coordinator is not None:
            try:
                retention = {**coordinator.status(), "status": "available"}
            except Exception as exc:  # noqa: BLE001 - passive status remains available
                log.warning("Passive retention status unavailable: %s", type(exc).__name__)
        return {
            "healthy": technical["status"] == "passed",
            "checks": dict(checks) if isinstance(checks, dict) else {},
            "retention": retention,
            **projected,
            "passive": True,
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

    def get_problems(self) -> dict[str, Any]:
        problems = get_problems(self._data_dir())
        active = [problem for problem in problems if problem["status"] == "active"]
        return {
            "problems": problems,
            "counts": {
                "error": sum(1 for problem in active if problem["level"] == "error"),
                "warn": sum(1 for problem in active if problem["level"] == "warn"),
                "historical": sum(1 for problem in problems if problem["status"] != "active"),
            },
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
                "available": False,
                "protected": False,
                "branch": branch,
                "rules": None,
            }
        if "branch_protection" not in (self._scm.capabilities or set()):
            return {
                "available": False,
                "protected": False,
                "branch": branch,
                "rules": None,
            }
        try:
            result = self._scm.get_branch_protection(branch)
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status", None)
            permission_denied = status in {401, 403}
            if permission_denied:
                log.info(
                    "Branch-Protection fuer %s nicht lesbar: SCM-Recht fehlt (HTTP %s)",
                    branch,
                    status,
                )
            else:
                log.warning("get_branch_protection failed", exc_info=True)
            failure = {
                "available": True,
                "protected": False,
                "branch": branch,
                "rules": None,
                "error": "permission_denied" if permission_denied else "request_failed",
            }
            if permission_denied:
                failure["required_permission"] = "repository_admin"
                failure["http_status"] = status
            return failure
        if result is None:
            return {
                "available": True,
                "protected": False,
                "branch": branch,
                "rules": None,
            }
        return {
            "available": True,
            "protected": True,
            "branch": result.get("branch", branch),
            "rules": result.get("rules"),
        }

    # #374: Persistierte Deployment-Risikoklasse — operator-editierbar im
    # Dashboard. Quelle der Wahrheit: ``config/compliance.json`` (env
    # ``SAMUEL_RISK_CLASS`` bleibt expliziter Override mit Vorrang).
    _RISK_CLASS_FILE = "compliance.json"
    _RISK_CLASS_KEY = "risk_classification"

    def _risk_class_path(self) -> Path:
        from pathlib import Path as _Path

        return _Path(self._config_dir()) / self._RISK_CLASS_FILE

    def _read_persisted_risk_class(self) -> str | None:
        """Lese die im Dashboard gesetzte Risikoklasse aus config/compliance.json.

        ``None`` wenn Datei/Key fehlen oder unlesbar — dann greift env/Default.
        """
        import json as _json

        fp = self._risk_class_path()
        if not fp.exists():
            return None
        try:
            data = _json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, _json.JSONDecodeError) as exc:
            log.warning("could not read %s: %s", fp, exc)
            return None
        val = data.get(self._RISK_CLASS_KEY)
        return str(val) if val else None

    def get_compliance_legend(self) -> dict[str, Any]:
        """Return OWASP Top-10 Agentic AI + EU AI Act article descriptions.

        OWASP-Daten sind statisch (``samuel.core.owasp``). Die AI-Act-
        Obligationen werden aus der aktiven Deployment-Risikoklasse abgeleitet
        (#373); die Klasse loest sich aus env-Override > persistiertem
        Dashboard-Wert > Default auf (#374). Exposed via Dashboard, damit
        Operatoren Codes wie ``A05``/``Art. 14`` inline aufloesen koennen (#252).
        """
        from samuel.core.ai_act import resolve_risk_class

        rc, source = resolve_risk_class(self._read_persisted_risk_class())
        legend = get_compliance_legend(risk_class=rc, risk_class_source=source)
        # #270: LLM-Code-Kennzeichnung im selben Aufruf, damit das Compliance-Tab
        # Toggle + Verbosity + high_risk-Sperre ohne zweiten Roundtrip rendert.
        legend["attribution"] = self.get_attribution()
        return legend

    def set_risk_class(self, value: str) -> dict[str, Any]:
        """Persistiere die Deployment-Risikoklasse nach config/compliance.json.

        #374: validiert gegen ``RISK_CLASSES``, atomic write (tmp+rename).
        Ist die Klasse per env ``SAMUEL_RISK_CLASS`` fixiert, wird der
        persistierte Wert trotzdem gespeichert, aber der env-Override behaelt
        zur Laufzeit Vorrang — die UI signalisiert das.
        """
        blocked = self.configuration_mutation_blocked()
        if blocked is not None:
            return blocked

        import json as _json

        from samuel.core.ai_act import RISK_CLASSES, resolve_risk_class

        val = str(value or "").strip().lower()
        if val not in RISK_CLASSES:
            return {
                "updated": False,
                "error": f"invalid risk class: {value!r} (expected one of {list(RISK_CLASSES)})",
            }
        # alte effektive Klasse VOR dem Schreiben festhalten (fuer Audit-Diff)
        old_class, _ = resolve_risk_class(self._read_persisted_risk_class())
        fp = self._risk_class_path()
        try:
            data = _json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
            if not isinstance(data, dict):
                data = {}
        except (OSError, _json.JSONDecodeError) as exc:
            return {"updated": False, "error": f"could not read {fp.name}: {exc}"}
        data[self._RISK_CLASS_KEY] = val
        tmp = fp.with_suffix(".tmp")
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                _json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(fp)
        except OSError as exc:
            return {"updated": False, "error": f"could not write {fp.name}: {exc}"}
        self._configuration_authority.mark_persisted()
        # #375: Aenderung der Compliance-Einstufung selbst nachvollziehbar machen
        # (AI-Act Art. 12). Publish nur bei tatsaechlicher Aenderung; env-Override
        # behaelt zur Laufzeit Vorrang, der persistierte Wert wurde aber geaendert.
        if val != old_class:
            from samuel.core.events import ConfigChanged

            try:
                self._bus.publish(
                    ConfigChanged(
                        payload={
                            "setting": "ai_act_risk_class",
                            "old": old_class,
                            "new": val,
                            "source": "dashboard",
                            "reason": f"AI-Act-Deployment-Risikoklasse {old_class} -> {val}",
                        }
                    )
                )
            except Exception:
                log.exception("failed to publish ConfigChanged for risk class")
        return {
            "updated": True,
            "risk_class": val,
            "changed": val != old_class,
            "restart_required": True,
            "configuration": self.configuration_status(),
        }

    def _persist_json_key(self, filename: str, key_path: str, value: Any) -> tuple[bool, str]:
        """#270: Persistiere einen (ggf. verschachtelten) Key atomar nach
        ``config/<filename>``. ``key_path`` mit ``.`` getrennt. Returns
        ``(ok, error)``."""
        import json as _json
        from pathlib import Path as _Path

        fp = _Path(self._config_dir()) / filename
        try:
            data = _json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
            if not isinstance(data, dict):
                data = {}
        except (OSError, _json.JSONDecodeError) as exc:
            return False, f"could not read {fp.name}: {exc}"
        cur = data
        parts = key_path.split(".")
        for p in parts[:-1]:
            nxt = cur.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[p] = nxt
            cur = nxt
        cur[parts[-1]] = value
        tmp = fp.with_suffix(".tmp")
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                _json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tmp.replace(fp)
        except OSError as exc:
            return False, f"could not write {fp.name}: {exc}"
        return True, ""

    def get_attribution(self) -> dict[str, Any]:
        """#270: Zustand der LLM-Code-Kennzeichnung (externe Sichtbarkeit).

        ``enabled`` = Feature-Flag ``llm_attribution`` (Inline-Marker +
        ``Co-Authored-By``). ``locked`` = ``True`` bei Deployment-Risikoklasse
        ``high_risk`` — dort ist die Kennzeichnung Pflicht (Art. 50) und nicht
        abschaltbar. Die Audit-Ebene (``AI-Generated-By`` + ``LLMCallCompleted``)
        ist davon unabhaengig und immer aktiv.
        """
        from samuel.core.ai_act import resolve_risk_class

        rc, _ = resolve_risk_class(self._read_persisted_risk_class())
        enabled = True
        verbosity = "minimal"
        if self._config is not None:
            enabled = bool(self._config.feature_flag("llm_attribution"))
            verbosity = str(self._config.get("privacy.attribution.verbosity", "minimal"))
        return {
            "enabled": enabled,
            "verbosity": verbosity,
            "locked": rc == "high_risk",
            "risk_class": rc,
        }

    def set_attribution(
        self,
        enabled: bool,
        verbosity: str | None = None,
    ) -> dict[str, Any]:
        """#270: Externe LLM-Code-Kennzeichnung setzen (persistiert + auditiert).

        * ``high_risk`` -> abgelehnt (``locked``): Art. 50 macht die Kennzeichnung
          dort zur Pflicht.
        * Persistiert ``features.llm_attribution`` (features.json) +
          ggf. ``privacy.attribution.verbosity`` (privacy.json), atomar, und
          setzt In-Memory-Overrides fuer sofortige Wirkung.
        * Publisht ``ConfigChanged`` (Art. 12); beim Deaktivieren mit
          Art.-50-Warnung. Die Audit-Ebene bleibt unberuehrt.
        """
        blocked = self.configuration_mutation_blocked()
        if blocked is not None:
            return blocked

        from samuel.core.ai_act import resolve_risk_class

        rc, _ = resolve_risk_class(self._read_persisted_risk_class())
        if rc == "high_risk":
            return {
                "updated": False,
                "locked": True,
                "error": "Bei Deployment-Risikoklasse high_risk ist die "
                "LLM-Code-Kennzeichnung Pflicht (EU-AI-Act Art. 50) "
                "und nicht abschaltbar.",
            }
        if self._config is None:
            return {"updated": False, "error": "config not available"}
        old_enabled = bool(self._config.feature_flag("llm_attribution"))
        new_enabled = bool(enabled)

        v: str | None = None
        if verbosity is not None:
            v = str(verbosity).strip().lower()
            if v not in ("minimal", "full"):
                return {
                    "updated": False,
                    "error": f"invalid verbosity: {verbosity!r} (expected 'minimal' or 'full')",
                }

        ok, err = self._persist_json_key(
            "features.json",
            "llm_attribution",
            new_enabled,
        )
        if not ok:
            return {"updated": False, "error": err}
        self._configuration_authority.mark_persisted()
        if v is not None:
            ok, err = self._persist_json_key(
                "privacy.json",
                "attribution.verbosity",
                v,
            )
            if not ok:
                return {
                    "updated": False,
                    "code": "configuration_partial_persistence",
                    "error": err,
                    "restart_required": True,
                    "configuration": self.configuration_status(),
                }

        warning = None
        if old_enabled != new_enabled:
            from samuel.core.events import ConfigChanged

            reason = f"LLM-Code-Kennzeichnung (extern sichtbar) {old_enabled} -> {new_enabled}"
            if not new_enabled:
                warning = (
                    "Verstoss gegen EU-AI-Act Art. 50: KI-generierter Code wird "
                    "extern nicht mehr gekennzeichnet (Inline-Marker + "
                    "Co-Authored-By unterdrueckt). Die Audit-Spur "
                    "(AI-Generated-By + LLMCallCompleted) bleibt erhalten."
                )
                reason += " — WARNUNG Art. 50 (externe Transparenz deaktiviert)"
            try:
                self._bus.publish(
                    ConfigChanged(
                        payload={
                            "setting": "llm_attribution",
                            "old": old_enabled,
                            "new": new_enabled,
                            "source": "dashboard",
                            "reason": reason,
                        }
                    )
                )
            except Exception:
                log.exception("failed to publish ConfigChanged for llm_attribution")

        result: dict[str, Any] = {
            "updated": True,
            "enabled": new_enabled,
            "changed": old_enabled != new_enabled,
            "restart_required": True,
            "configuration": self.configuration_status(),
        }
        if v is not None:
            result["verbosity"] = v
        if warning:
            result["warning"] = warning
        return result

    def get_dlq(self) -> dict[str, Any]:
        """#334: Dead-Letter-Queue-Eintraege (fehlgeschlagene Event-Handler).

        Read-only; Re-Publish laeuft ueber CLI ``samuel dlq replay <id>``.
        """
        entries = get_dlq_entries(self._data_dir())
        return {"entries": entries, "count": len(entries)}

    def get_workflow(self) -> dict[str, Any]:
        """Return workflow issues and branch overview.

        #277: ``recovered_count`` is a summary signal — number of issues
        whose latest run passed after at least one previous failure.
        Useful as a self-healing-effectiveness indicator for the operator.
        """
        issues = get_workflow_issues(self._data_dir(), self._run_projection_store)
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
        detail = get_workflow_issue_detail(
            int(issue_number),
            self._data_dir(),
            projection_store=self._run_projection_store,
        )
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
            self._config,
            config_dir=config_dir,
            prompt_source_resolver=self._prompt_source_resolver,
            model_quality_resolver=self._model_quality_resolver,
        )
        usage["routing_schedule"] = get_llm_routing_schedule(self._config)
        usage["history"] = get_token_history(data_dir)
        self._add_reasoning_feedback(usage["routing"], usage["history"])
        usage["quality"] = get_llm_quality_scores(
            data_dir,
            projection_store=self._run_projection_store,
        )
        usage["api_keys"] = get_api_key_status(config_dir)
        usage["model_cache"] = (
            self._model_cache_status_resolver() if self._model_cache_status_resolver else {}
        )
        import os as _os

        usage["provider"] = _os.environ.get("SAMUEL_LLM_PROVIDER") or (
            str(self._config.get("llm.default.provider", "-")) if self._config else "-"
        )
        return usage

    @staticmethod
    def _add_reasoning_feedback(routing: list[dict], history: list[dict]) -> None:
        for row in routing:
            samples = [
                call
                for call in history
                if call.get("task") == row.get("task")
                and call.get("provider") == row.get("provider")
                and call.get("model") == row.get("model")
            ]
            observed = [
                int(call["reasoning_tokens"])
                for call in samples
                if isinstance(call.get("reasoning_tokens"), (int, float))
            ]
            truncations = sum(
                1
                for call in samples
                if str(call.get("stop_reason", "")).lower()
                in {"length", "max_tokens", "token_limit"}
            )
            row["reasoning_feedback"] = {
                "calls": len(samples),
                "reasoning_samples": len(observed),
                "average_reasoning_tokens": (
                    round(sum(observed) / len(observed), 1) if observed else None
                ),
                "max_reasoning_tokens": max(observed) if observed else None,
                "truncations": truncations,
                "note": (
                    "Ausgabe wurde abgeschnitten; Content-Limit, Prompt und gemessene "
                    "Reasoning-Nutzung gemeinsam prüfen — keine automatische Kostenerhöhung."
                    if truncations
                    else "Gemessene Nutzung anzeigen; Reserve nur bei belegtem Bedarf ändern."
                    if observed
                    else "Noch keine getrennte Reasoning-Telemetrie für diese Route."
                ),
            }

    def get_quality(self) -> dict[str, Any]:
        """#153: Daten fuer den Quality-Tab — Provider x Task Heatmap, Matrix
        (issue-korreliert + persistierter EWMA), Param-Size-Warnungen."""
        min_b = 7.0
        if self._config is not None:
            try:
                min_b = float(self._config.get("llm.min_local_model_params_b", 7.0))
            except (TypeError, ValueError):
                min_b = 7.0
        return get_quality_overview(
            self._data_dir(),
            min_params_b=min_b,
            registry=self._quality_registry,
            projection_store=self._run_projection_store,
        )

    def get_activity(self) -> dict[str, Any]:
        """#230: SCM-Activity-Stream (Webhook) fuer den Activity-Tab."""
        return {"activity": get_scm_activity(self._data_dir())}

    def get_settings(self) -> dict[str, Any]:
        """Return feature flags, LLM config, model cache, and API-key status."""
        config_dir = (
            str(self._config.get("agent.config_dir", "config")) if self._config else "config"
        )
        return {
            "flags": get_feature_flags(self._config),
            "configuration": self.configuration_status(),
            "extensions": self.get_extension_configuration(),
            "llm_global_config": self.get_llm_global_config(),
            "llm_config": (
                get_llm_routing(
                    self._config,
                    config_dir=config_dir,
                    prompt_source_resolver=self._prompt_source_resolver,
                    model_quality_resolver=self._model_quality_resolver,
                )
                if self._config
                else []
            ),
            "model_cache": (
                self._model_cache_status_resolver() if self._model_cache_status_resolver else {}
            ),
            # #311-followup: balance_resolver wird vom Wiring-Layer (server.py)
            # injiziert — Slice-Iso erlaubt keinen direkten Adapter-Import hier.
            "api_keys": get_api_key_status(config_dir, balance_resolver=self._balance_resolver),
        }

    def get_extension_configuration(self) -> dict[str, Any]:
        """Return the effective, non-secret public extension selection."""

        stored = self._extension_configuration_snapshot()
        effective = self._effective_extension_configuration
        return {
            **stored,
            "effective_enabled": effective["enabled"],
            "effective_required": effective["required"],
            "effective_available": effective["available"],
            "effective_blocked": effective["blocked"],
            "effective_status": effective["status"],
            "effective_reason": effective["reason"],
        }

    def _extension_configuration_snapshot(self) -> dict[str, Any]:
        """Resolve one stored selection without mutating the startup snapshot."""

        from samuel.extensions import load_extension_policy, resolve_capability
        from samuel.extensions.contract import ContractError

        path = Path(self._config_dir()) / "extensions.json"
        try:
            policy = load_extension_policy(path)
            resolution = resolve_capability(policy)
        except ContractError as exc:
            return {
                "capability_id": "documentation.static_claims",
                "enabled": False,
                "required": False,
                "available": False,
                "blocked": True,
                "status": "incompatible",
                "reason": str(exc),
                "contract_version": "1.0",
                "manifest_path": None,
            }
        return {
            **resolution.model_dump(exclude={"manifest"}),
            "contract_version": policy.contract_version,
            "manifest_path": policy.manifest_path,
        }

    def set_extension_configuration(self, value: dict[str, Any]) -> dict[str, Any]:
        """Persist the one public extension selection under the D08 boundary."""

        blocked = self.configuration_mutation_blocked()
        if blocked is not None:
            return blocked

        from pydantic import ValidationError

        from samuel.extensions import (
            CapabilityPolicy,
            ExtensionConfiguration,
        )

        if not isinstance(value, dict):
            return {"updated": False, "error": "extension configuration must be an object"}
        unknown = set(value) - {"enabled", "required", "manifest_path"}
        if unknown:
            return {"updated": False, "error": f"unknown fields: {', '.join(sorted(unknown))}"}
        try:
            policy = CapabilityPolicy.model_validate(value)
            configuration = ExtensionConfiguration(
                schema_version="1.0",
                capabilities={"documentation.static_claims": policy},
            )
        except ValidationError as exc:
            return {"updated": False, "error": f"invalid extension configuration: {exc}"}

        path = Path(self._config_dir()) / "extensions.json"
        temporary = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                configuration.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            return {"updated": False, "error": f"could not write extensions.json: {exc}"}
        self._configuration_authority.mark_persisted()
        return {
            "updated": True,
            "restart_required": True,
            "extension": self.get_extension_configuration(),
            "configuration": self.configuration_status(),
        }

    def get_llm_global_config(self) -> dict[str, Any]:
        """Return the effective default provider and ordered fallback chain."""
        import json as _json
        import os as _os
        from pathlib import Path as _Path

        config_dir = self._config_dir()
        path = _Path(config_dir) / "llm.json"
        try:
            data = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, _json.JSONDecodeError) as exc:
            log.warning("Could not read LLM global config %s: %s", path, exc)
            data = {}
        raw_default = data.get("default") if isinstance(data, dict) else None
        default_cfg: dict[str, Any] = raw_default if isinstance(raw_default, dict) else {}
        provider = default_cfg.get("provider") or (
            self._config.get("llm.default.provider", "-") if self._config else "-"
        )
        fallbacks = default_cfg.get("fallbacks")
        if not isinstance(fallbacks, list):
            fallbacks = []
        environment_provider = _os.environ.get("SAMUEL_LLM_PROVIDER", "").strip()
        return {
            "provider": str(provider),
            "effective_provider": environment_provider or str(provider),
            "provider_source": "environment" if environment_provider else "config",
            "fallbacks": [str(name) for name in fallbacks],
            "providers": sorted(self._KNOWN_PROVIDERS),
            "restart_required": False,
        }

    def set_llm_global_config(self, cfg: dict) -> dict[str, Any]:
        """Persist default provider/fallback chain to top-level ``llm.json``.

        This is the same file consumed by ``FileConfig`` and the LLM factory;
        ``llm/providers.json`` remains the provider catalogue/API-key metadata,
        not a competing runtime default (#419).
        """
        blocked = self.configuration_mutation_blocked()
        if blocked is not None:
            return blocked

        import json as _json
        import os as _os
        from pathlib import Path as _Path

        if not isinstance(cfg, dict):
            return {"updated": False, "error": "config must be a dict"}
        unknown = set(cfg) - {"provider", "fallbacks"}
        if unknown:
            return {"updated": False, "error": f"unknown fields: {', '.join(sorted(unknown))}"}
        provider = str(cfg.get("provider") or "").strip()
        fallbacks = cfg.get("fallbacks", [])
        if provider not in self._KNOWN_PROVIDERS:
            return {"updated": False, "error": f"unknown provider: {provider}"}
        if not isinstance(fallbacks, list):
            return {"updated": False, "error": "fallbacks must be a list"}
        normalized: list[str] = []
        for value in fallbacks:
            name = str(value).strip()
            if name not in self._KNOWN_PROVIDERS:
                return {"updated": False, "error": f"unknown fallback provider: {name}"}
            if name != provider and name not in normalized:
                normalized.append(name)

        path = _Path(self._config_dir()) / "llm.json"
        try:
            data = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, _json.JSONDecodeError) as exc:
            return {"updated": False, "error": f"could not read llm.json: {exc}"}
        default_cfg = data.setdefault("default", {})
        if not isinstance(default_cfg, dict):
            default_cfg = {}
            data["default"] = default_cfg
        default_cfg["provider"] = provider
        default_cfg["fallbacks"] = normalized
        temporary = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                _json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            return {"updated": False, "error": f"could not write llm.json: {exc}"}
        self._configuration_authority.mark_persisted()
        return {
            "updated": True,
            "provider": provider,
            "fallbacks": normalized,
            # Existing adapter instances are immutable; the new chain becomes
            # effective on the next agent process start.
            "restart_required": True,
            "environment_override": bool(_os.environ.get("SAMUEL_LLM_PROVIDER")),
            "configuration": self.configuration_status(),
        }

    # #309: Per-Task LLM configuration write.
    _CANONICAL_TASKS = frozenset(
        {
            "planning",
            "implementation",
            "review",
            "healing",
            "evaluation",
        }
    )
    _KNOWN_PROVIDERS = frozenset(
        {
            "claude",
            "deepseek",
            "gemini",
            "openai",
            "openrouter",
            "ollama",
            "lmstudio",
            "manual",
        }
    )
    _ALLOWED_FIELDS = frozenset(
        {
            "provider",
            "model",
            "base_url",
            "timeout",
            "system_prompt",
            "max_tokens",
            "reasoning_reserve",
            "temperature",
            "cost_advisory_enabled",
            "overqualification_margin_ratio",
            "schedule",  # #316
            "system_prompt_by_provider",  # #351 Hybrid: per-provider override map
        }
    )

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
                return (
                    False,
                    f"system_prompt_by_provider value for {prov!r} must be non-empty string",
                )
            if not name.endswith(".md"):
                return False, f"system_prompt_by_provider value for {prov!r} must end with .md"
            if "/" in name or "\\" in name or ".." in name:
                return (
                    False,
                    f"system_prompt_by_provider value for {prov!r} contains path separator/traversal",
                )
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

        Empty-string/None values in cfg remove the field — UX pattern for
        "Override entfernen". HTTP callers remain protected by the dashboard
        API key; this method enforces the configuration schema.
        """
        blocked = self.configuration_mutation_blocked()
        if blocked is not None:
            return blocked

        import json as _json

        if task not in self._CANONICAL_TASKS:
            return {"updated": False, "error": f"unknown task: {task}"}
        if not isinstance(cfg, dict):
            return {"updated": False, "error": "config must be a dict"}

        provider = cfg.get("provider")
        if provider and provider not in self._KNOWN_PROVIDERS:
            return {"updated": False, "error": f"unknown provider: {provider}"}

        if "max_tokens" in cfg and cfg["max_tokens"] not in (None, ""):
            value = cfg["max_tokens"]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                return {"updated": False, "error": "max_tokens must be a positive integer"}
        if "reasoning_reserve" in cfg and cfg["reasoning_reserve"] not in (None, ""):
            value = cfg["reasoning_reserve"]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return {
                    "updated": False,
                    "error": "reasoning_reserve must be a non-negative integer",
                }
        if "cost_advisory_enabled" in cfg and not isinstance(cfg["cost_advisory_enabled"], bool):
            return {"updated": False, "error": "cost_advisory_enabled must be boolean"}
        if "overqualification_margin_ratio" in cfg and cfg[
            "overqualification_margin_ratio"
        ] not in (None, ""):
            value = cfg["overqualification_margin_ratio"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= float(value) <= 1
            ):
                return {
                    "updated": False,
                    "error": "overqualification_margin_ratio must be between 0 and 1",
                }

        # Reject unknown fields (silent drop would mask typos)
        unknown_fields = [k for k in cfg if k not in self._ALLOWED_FIELDS]
        if unknown_fields:
            return {
                "updated": False,
                "error": f"unknown fields: {', '.join(unknown_fields)}",
            }

        # #316: schedule block — structural validation remains mandatory.
        if "schedule" in cfg and cfg["schedule"] not in (None, ""):
            ok, err = self._validate_schedule(cfg["schedule"])
            if not ok:
                return {"updated": False, "error": err}

        # #351: per-provider override map — structural validation. Empty
        # value drops the field via the merge loop below (UX: clear-all).
        if "system_prompt_by_provider" in cfg and cfg["system_prompt_by_provider"] not in (
            None,
            "",
            {},
        ):
            ok, err = self._validate_prompt_by_provider_map(
                cfg["system_prompt_by_provider"],
                self._KNOWN_PROVIDERS,
            )
            if not ok:
                return {"updated": False, "error": err}

        config_dir = (
            str(self._config.get("agent.config_dir", "config")) if self._config else "config"
        )
        from pathlib import Path as _Path

        fp = _Path(config_dir) / "llm" / "defaults.json"
        try:
            data = _json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
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

        warnings: list[str] = []
        reserve = int(merged.get("reasoning_reserve", 0) or 0)
        if reserve:
            effective_provider = str(
                merged.get("provider")
                or (self._config.get("llm.default.provider", "") if self._config else "")
            )
            if effective_provider and effective_provider != "openrouter":
                return {
                    "updated": False,
                    "error": (
                        "reasoning_reserve is only an explicit control for the openrouter "
                        "provider; use 0 for provider default"
                    ),
                }
            model = str(merged.get("model", ""))
            base_defaults = data.get("default", {}) if isinstance(data.get("default"), dict) else {}
            content = int(merged.get("max_tokens", base_defaults.get("max_tokens", 0)) or 0)
            if self._model_quality_resolver and model:
                raw_margin = merged.get("overqualification_margin_ratio", 0.2)
                margin = float(0.2 if raw_margin is None else raw_margin)
                quality = self._model_quality_resolver(model, task, 0.0, margin)
                reasoning = quality.get("reasoning", {}) if isinstance(quality, dict) else {}
                source = str(reasoning.get("source", ""))
                if not reasoning.get("is_reasoning") and "heuristic" not in source:
                    return {
                        "updated": False,
                        "error": "selected model does not expose reasoning capability",
                    }
                limit = int(reasoning.get("max_completion_tokens", 0) or 0)
                if content and limit and content + reserve > limit:
                    return {
                        "updated": False,
                        "error": (
                            f"content + reasoning reserve ({content + reserve}) exceeds "
                            f"model max_completion_tokens ({limit})"
                        ),
                    }
                if "heuristic" in source:
                    warnings.append(
                        "Reasoning capability is based on stale/name metadata; refresh the "
                        "OpenRouter model cache for validation."
                    )

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

        self._configuration_authority.mark_persisted()

        return {
            "updated": True,
            "task": task,
            "cfg": merged,
            "restart_required": True,
            "warnings": warnings,
            "configuration": self.configuration_status(),
        }

    def test_connection(self, provider: str, cfg: dict) -> dict[str, Any]:
        """#314: Test-Connection — baut temporaeren Adapter aus Form-Werten,
        ruft ``validate()``. Liefert ``{valid, detail, balance}``.

        Der HTTP-Aufruf ist durch den Dashboard-API-Key geschützt; die
        Provider- und Eingabevalidierung greift unabhängig davon.
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
        result = self._connection_tester(prov, clean)
        if not result.get("valid"):
            from samuel.core.events import DiagnosticRaised

            self._bus.publish(
                DiagnosticRaised(
                    payload={
                        "level": "warning",
                        "category": "llm",
                        "reason": f"Provider-Verbindung fehlgeschlagen: {result.get('detail', '')}",
                        "provider": prov,
                        "file": "config/llm/defaults.json",
                        "source": "dashboard_connection_test",
                    }
                )
            )
        return result

    def set_feature_flag(self, name: str, enabled: bool) -> dict[str, Any]:
        """Persist a feature flag for the next production process."""

        blocked = self.configuration_mutation_blocked()
        if blocked is not None:
            return blocked
        known_keys = {k for k, _, _ in KNOWN_FEATURE_FLAGS}
        if name not in known_keys:
            return {"updated": False, "error": f"unknown flag: {name}"}
        if self._config is None:
            return {"updated": False, "error": "config not available"}
        ok, error = self._persist_json_key("features.json", name, bool(enabled))
        if not ok:
            return {"updated": False, "error": error}
        self._configuration_authority.mark_persisted()
        return {
            "updated": True,
            "name": name,
            "enabled": bool(enabled),
            "restart_required": True,
            "configuration": self.configuration_status(),
        }

    def get_self_mode_health(self, limit: int = 50) -> dict[str, Any]:
        """#319: Aggregierte Self-Mode-Health-Statistik aus jsonl-Metrics.

        Liest ``<agent.data_dir>/logs/self_mode_metrics.jsonl`` (geschrieben
        von ImplementationHandler), aggregiert die letzten ``limit`` Runs.
        Liefert Erfolgsquote, Durchschnitts-Rounds, Hang-Rate (no_progress),
        und die letzten 20 Run-Records fuer Detail-Tabelle.
        """
        import json as _json
        from pathlib import Path as _Path

        fp = _Path(self._data_dir()) / "logs" / "self_mode_metrics.jsonl"
        records: list[dict] = []
        invalid_rows = 0
        if fp.is_file():
            try:
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(_json.loads(line))
                    except _json.JSONDecodeError:
                        invalid_rows += 1
                        continue
            except OSError as exc:
                log.warning("Could not read self-mode metrics: %s", exc)
        if invalid_rows:
            log.warning(
                "Ignored %d invalid row(s) in self-mode metrics %s",
                invalid_rows,
                fp,
            )
        # Letzte ``limit`` Runs (chronologisch aelteste->neueste in der Datei)
        recent = records[-limit:]
        total = len(recent)
        if total == 0:
            return {
                "total": 0,
                "success_rate": None,
                "no_progress_rate": None,
                "avg_rounds": None,
                "avg_duration_s": None,
                "recent_runs": [],
            }
        success_count = sum(1 for r in recent if r.get("success"))
        no_progress_count = sum(1 for r in recent if r.get("reason") == "no_progress")
        rounds_sum = sum(int(r.get("rounds", 0)) for r in recent)
        duration_sum = sum(float(r.get("duration_seconds", 0)) for r in recent)
        return {
            "total": total,
            "success_rate": round(success_count / total, 3),
            "no_progress_rate": round(no_progress_count / total, 3),
            "avg_rounds": round(rounds_sum / total, 2),
            "avg_duration_s": round(duration_sum / total, 2),
            "recent_runs": list(reversed(recent[-20:])),  # neueste zuerst
        }

    def get_self_check(self) -> dict[str, Any]:
        """Run HealthCheckCommand and return structured checks list.

        Each check: name, status (OK/FAIL), time (empty if not provided),
        detail (version / error / extra info). Also includes the agent mode.
        """
        probe = self._run_active_provider_probes()
        payload: dict[str, Any] = {}
        if probe is not None:
            payload["provider_probe"] = probe
        result = self._bus.send(HealthCheckCommand(payload=payload)) or {}
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
            checks.append(
                {
                    "name": name,
                    "status": "OK" if passed else "FAIL",
                    "time": "",
                    "detail": detail,
                }
            )
        mode = self._config.get("agent.mode", "standard") if self._config else "standard"
        self_mode = bool(self._config.get("agent.self_mode", False)) if self._config else False
        return {
            "mode": "self" if self_mode else mode,
            "healthy": bool(result.get("healthy", False)) if isinstance(result, dict) else False,
            "checks": checks,
            "technical_health": (
                dict(result.get("technical_health", {})) if isinstance(result, dict) else {}
            ),
            "operational_readiness": (
                dict(result.get("operational_readiness", {})) if isinstance(result, dict) else {}
            ),
            "qualification": (
                dict(result.get("qualification", {})) if isinstance(result, dict) else {}
            ),
        }

    def _run_active_provider_probes(self) -> dict[str, Any] | None:
        """Probe configured task routes without retaining provider responses.

        This is intentionally available only through the permission-protected
        self-check endpoint. Health and viewer reads remain passive. The
        connection tester belongs to the wiring layer and returns provider
        details for the interactive editor, so this method reduces those
        results to fixed route facts before they enter Health or the durable
        readiness projection.
        """
        if self._connection_tester is None or self._config is None:
            return None
        config_dir = str(self._config.get("agent.config_dir", "config"))
        routes = get_llm_routing(self._config, config_dir=config_dir)
        observations: list[dict[str, Any]] = []
        for route in routes:
            task = str(route.get("task", "default"))
            provider = str(route.get("provider", "")).strip().lower()
            model = str(route.get("model", "")).strip()
            if not provider or provider == "-" or not model or model == "-":
                observations.append(
                    {"task": task, "provider": provider or "unknown", "passed": False}
                )
                continue
            cfg: dict[str, Any] = {"model": model}
            base_url = route.get("base_url")
            timeout = route.get("timeout")
            if isinstance(base_url, str) and base_url:
                cfg["base_url"] = base_url
            if isinstance(timeout, int) and timeout > 0:
                cfg["timeout"] = timeout
            try:
                result = self._connection_tester(provider, cfg)
                passed = bool(result.get("valid")) if isinstance(result, dict) else False
            except Exception:  # noqa: BLE001 - details can be credential-adjacent
                log.warning("Active provider probe failed for task %s", task)
                passed = False
            observations.append({"task": task, "provider": provider, "passed": passed})
        return {
            "schema": "samuel-provider-probe.v1",
            "performed": True,
            "passed": bool(observations) and all(row["passed"] for row in observations),
            "routes": observations,
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
