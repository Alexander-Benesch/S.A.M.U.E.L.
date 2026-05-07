from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.ports import IConfig, IVersionControl
from samuel.core.types import Comment, Issue
from samuel.slices.dashboard.handler import DashboardHandler


class MockSCM(IVersionControl):
    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="T", body="b", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class MockConfig(IConfig):
    def __init__(self, data: dict[str, Any] | None = None):
        self._data = data or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        pass


class TestDashboardHandler:
    def test_status_with_scm(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig({"agent.mode": "watch"}))
        status = handler.get_status()
        assert status["scm_connected"] is True
        assert status["mode"] == "watch"

    def test_status_without_scm(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=None, config=MockConfig())
        status = handler.get_status()
        assert status["scm_connected"] is False

    def test_status_includes_tiles_score_history_and_anomalies(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).isoformat()
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(json.dumps({"ts": recent, "name": "AuditEvent",
                                "payload": {"message_name": "EvalCompleted",
                                            "score": 0.7, "baseline": 0.5}}) + "\n")
            f.write(json.dumps({"ts": recent, "name": "AuditEvent",
                                "payload": {"message_name": "GateFailed", "reason": "x"}}) + "\n")
        bus = Bus()
        handler = DashboardHandler(
            bus, scm=MockSCM(),
            config=MockConfig({
                "agent.data_dir": str(tmp_path),
                "llm.default.provider": "deepseek",
                "llm.deepseek.model": "deepseek-chat",
            }),
        )
        s = handler.get_status()
        assert isinstance(s["tiles"], list)
        assert any(t["key"] == "scm" for t in s["tiles"])
        assert any(t["key"] == "llm" and t["value"] == "deepseek" for t in s["tiles"])
        assert any(t["key"] == "eval" for t in s["tiles"])
        assert len(s["score_history"]) == 1
        assert s["score_history"][0]["score"] == 0.7
        assert any(a["event"] == "GateFailed" for a in s["anomalies"])

    def test_health_all_connected(self):
        # #194: get_health() delegiert an HealthCheckCommand — Test muss einen
        # Handler registrieren, sonst liefert der Bus "No handler"-Warnung
        # und healthy=False.
        bus = Bus()
        bus.register_command(
            "HealthCheck",
            lambda cmd: {"healthy": True, "checks": {"scm": True, "config": True, "llm": True}},
        )
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig())
        health = handler.get_health()
        assert health["healthy"] is True
        # Schema bleibt dict (backward-compat fuer Frontend)
        assert isinstance(health["checks"], dict)
        assert health["checks"]["scm"] is True
        assert health["checks"]["llm"] is True

    def test_health_scm_missing(self):
        bus = Bus()
        bus.register_command(
            "HealthCheck",
            lambda cmd: {"healthy": False, "checks": {"scm": False, "config": True}},
        )
        handler = DashboardHandler(bus, scm=None, config=MockConfig())
        health = handler.get_health()
        assert health["healthy"] is False
        assert health["checks"]["scm"] is False

    def test_health_includes_application_level_checks(self):
        """#194-AC: LLM, Audit-Sink, Workflow-Engine, Quality-Registry, Metering,
        Idempotency-Store werden vom HealthCheckCommand durchgereicht."""
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {
            "healthy": True,
            "checks": {
                "scm": True, "config": True,
                "llm": True, "audit_sink": True,
                "workflow_engine": True, "quality_registry": True,
                "metering": True, "idempotency_store": True,
            },
        })
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig())
        health = handler.get_health()
        for name in ("llm", "audit_sink", "workflow_engine",
                     "quality_registry", "metering", "idempotency_store"):
            assert name in health["checks"], f"missing check: {name}"

    def test_metrics_aggregated_from_audit_log(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(json.dumps({"name": "AuditEvent", "payload": {
                "message_type": "PlanIssueCommand",
                "message_name": "PlanIssue",
                "duration_ms": 12.0,
            }}) + "\n")
            f.write(json.dumps({"name": "AuditEvent", "payload": {
                "message_type": "PlanIssueCommand",
                "message_name": "PlanIssue",
                "duration_ms": 8.0,
            }}) + "\n")
            f.write(json.dumps({"name": "AuditEvent", "payload": {
                "message_type": "WorkflowAborted",
                "message_name": "WorkflowAborted",
                "source_command": "PlanIssue",
                "reason": "x",
            }}) + "\n")

        bus = Bus()
        handler = DashboardHandler(
            bus, scm=MockSCM(),
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        metrics = handler.get_metrics()
        assert metrics["counts"]["PlanIssue"] == 2
        assert metrics["total_ms"]["PlanIssue"] == 20.0
        assert metrics["errors"]["PlanIssue"] == 1

    def test_metrics_empty_when_no_audit_log(self, tmp_path: Path):
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        metrics = handler.get_metrics()
        assert metrics["counts"] == {}
        assert metrics["errors"] == {}

    def test_api_data_endpoints(self):
        bus = Bus()
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig())
        assert "scm_connected" in handler.get_api_data("status")
        assert "healthy" in handler.get_api_data("health")
        assert "counts" in handler.get_api_data("metrics")
        assert "error" in handler.get_api_data("unknown")

    def test_logs_returned_under_entries_key(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(json.dumps({"ts": "2026-04-29T10:00", "name": "AuditEvent",
                                "payload": {"message_name": "PlanCreated"}}) + "\n")
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        result = handler.get_logs()
        assert isinstance(result, dict)
        assert "entries" in result
        assert len(result["entries"]) == 1
        assert result["entries"][0]["timestamp"] == "2026-04-29T10:00"

    def test_logs_include_level_counts_for_stat_tiles(self, tmp_path: Path):
        # Issue #203: the Logs tab shows info/warn/error tiles fed from this dict
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(json.dumps({"ts": "t1", "name": "AuditEvent",
                                "payload": {"message_name": "GateFailed"}}) + "\n")
            f.write(json.dumps({"ts": "t2", "name": "AuditEvent",
                                "payload": {"message_name": "HealingFailed"}}) + "\n")
            f.write(json.dumps({"ts": "t3", "name": "AuditEvent",
                                "payload": {"message_name": "PlanCreated"}}) + "\n")
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        result = handler.get_logs()
        assert result["level_counts"] == {"info": 1, "warn": 1, "error": 1}

    def test_workflow_uses_data_dir_from_config(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(json.dumps({"ts": "2026-04-29T10:00", "name": "AuditEvent",
                                "payload": {"message_name": "PRCreated", "issue": 42}}) + "\n")
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        wf = handler.get_workflow()
        assert any(i["number"] == 42 for i in wf["issues"])
        issue = next(i for i in wf["issues"] if i["number"] == 42)
        assert issue["timestamp"] == "2026-04-29T10:00"

    def test_security_uses_data_dir_from_config(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(json.dumps({"ts": "t", "name": "AuditEvent",
                                "payload": {"message_name": "GateFailed",
                                            "owasp_risk": "A04: x"}}) + "\n")
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        sec = handler.get_security()
        assert isinstance(sec["owasp"], list)
        a04 = next(r for r in sec["owasp"] if r["id"] == "A04")
        assert a04["count"] == 1

    def test_llm_includes_provider_from_config(self, tmp_path: Path):
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({
                "agent.data_dir": str(tmp_path),
                "llm.default.provider": "deepseek",
            }),
        )
        result = handler.get_llm()
        assert result["provider"] == "deepseek"

    def test_llm_provider_dash_when_no_config(self, tmp_path: Path):
        bus = Bus()
        handler = DashboardHandler(bus, config=None)
        result = handler.get_llm()
        assert result["provider"] == "-"

    def test_workflow_detail_returns_aggregated_view(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(json.dumps({"ts": "2026-04-29T10:00", "name": "AuditEvent",
                                "payload": {"message_name": "PlanCreated", "issue": 42}}) + "\n")
            f.write(json.dumps({"ts": "2026-04-29T10:05", "name": "AuditEvent",
                                "payload": {"message_name": "LLMCallCompleted",
                                            "issue": 42, "provider": "deepseek",
                                            "task": "planning", "tokens": 200, "cost": 0.001}}) + "\n")
            f.write(json.dumps({"ts": "2026-04-29T10:10", "name": "AuditEvent",
                                "payload": {"message_name": "PRCreated", "issue": 42}}) + "\n")
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        d = handler.get_workflow_detail(42)
        assert d["number"] == 42
        assert d["status"] == "pr_created"
        assert d["stages"]["plan"]["status"] == "done"
        assert d["stages"]["pr"]["status"] == "done"
        assert d["llm"]["calls"] == 1
        assert d["llm"]["tokens"] == 200
        assert len(d["events"]) == 3

    def test_workflow_detail_returns_error_for_unknown_issue(self, tmp_path: Path):
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        d = handler.get_workflow_detail(999)
        assert "error" in d
        assert "999" in d["error"]


class TestSetFeatureFlag:
    def test_toggle_known_flag_updates_override(self):
        import tempfile

        from samuel.core.config import FileConfig
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FileConfig(tmp)
            bus = Bus()
            handler = DashboardHandler(bus, config=cfg)

            result = handler.set_feature_flag("eval", False)

            assert result["updated"] is True
            assert result["enabled"] is False
            assert cfg.feature_flag("eval") is False

            result2 = handler.set_feature_flag("eval", True)
            assert result2["updated"] is True
            assert cfg.feature_flag("eval") is True

    def test_toggle_unknown_flag_rejected(self):
        import tempfile

        from samuel.core.config import FileConfig
        with tempfile.TemporaryDirectory() as tmp:
            cfg = FileConfig(tmp)
            bus = Bus()
            handler = DashboardHandler(bus, config=cfg)

            result = handler.set_feature_flag("not_a_real_flag", True)

            assert result["updated"] is False
            assert "unknown flag" in result["error"]

    def test_toggle_without_config_returns_error(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=None)

        result = handler.set_feature_flag("eval", True)
        assert result["updated"] is False

    def test_toggle_with_config_without_overrides_returns_error(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())

        result = handler.set_feature_flag("eval", True)
        assert result["updated"] is False
        assert "does not support overrides" in result["error"]


class TestSelfCheck:
    def test_self_check_returns_structured_checks(self):
        bus = Bus()
        bus.register_command(
            "HealthCheck",
            lambda cmd: {
                "healthy": True,
                "checks": {
                    "python": {"passed": True, "version": "3.12.0"},
                    "scm": {"passed": False, "error": "boom"},
                },
            },
        )
        handler = DashboardHandler(bus, config=MockConfig({"agent.mode": "watch"}))

        result = handler.get_self_check()

        assert result["healthy"] is True
        assert result["mode"] == "watch"
        names = {c["name"] for c in result["checks"]}
        assert names == {"python", "scm"}
        python_check = next(c for c in result["checks"] if c["name"] == "python")
        assert python_check["status"] == "OK"
        assert "version=3.12.0" in python_check["detail"]
        scm_check = next(c for c in result["checks"] if c["name"] == "scm")
        assert scm_check["status"] == "FAIL"
        assert "error=boom" in scm_check["detail"]

    def test_self_check_mode_self(self):
        bus = Bus()
        bus.register_command("HealthCheck", lambda cmd: {"healthy": True, "checks": {}})
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.self_mode": True, "agent.mode": "standard"})
        )
        result = handler.get_self_check()
        assert result["mode"] == "self"

    def test_self_check_with_no_handler_is_safe(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())
        result = handler.get_self_check()
        assert result["healthy"] is False
        assert result["checks"] == []

    def test_self_check_sends_health_check_command(self):
        bus = Bus()
        captured: list = []

        def _h(cmd):
            captured.append(cmd)
            return {"healthy": True, "checks": {}}

        bus.register_command("HealthCheck", _h)
        handler = DashboardHandler(bus, config=MockConfig())

        handler.get_self_check()

        assert len(captured) == 1
        assert isinstance(captured[0], HealthCheckCommand)


class TestLLMRouting:
    def test_routing_included_in_get_llm(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig({"llm.default.provider": "ollama", "llm.default.model": "llama3"}))
        data = handler.get_llm()
        assert "routing" in data
        assert isinstance(data["routing"], list)
        assert data["routing"][0]["provider"] == "ollama"


class TestTamperEvents:
    def test_security_includes_tamper_events_key(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())
        sec = handler.get_security()
        assert "tamper_events" in sec
        assert isinstance(sec["tamper_events"], list)


class TestBranchProtectionInSecurity:
    """#209: Security-Tab zeigt Branch-Protection-Status."""

    def test_security_includes_branch_protection_key(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())
        sec = handler.get_security()
        assert "branch_protection" in sec
        bp = sec["branch_protection"]
        assert bp["available"] is False  # no SCM wired
        assert bp["protected"] is False
        assert bp["branch"] == "main"

    def test_branch_from_config_default_branch(self):
        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.default_branch": "trunk"}),
        )
        sec = handler.get_security()
        assert sec["branch_protection"]["branch"] == "trunk"

    def test_unsupported_scm_marked_unavailable(self):
        # MockSCM has no `branch_protection` capability — handler must
        # treat that as available=False.
        bus = Bus()
        handler = DashboardHandler(bus, scm=MockSCM(), config=MockConfig())
        sec = handler.get_security()
        bp = sec["branch_protection"]
        assert bp["available"] is False
        assert bp["protected"] is False

    def test_protected_branch_returned(self):
        class CapableMockSCM(MockSCM):
            @property
            def capabilities(self) -> set[str]:
                return {"branch_protection"}

            def get_branch_protection(self, branch: str) -> dict | None:
                return {"branch": branch, "rules": {"required_approvals": 2}}

        bus = Bus()
        handler = DashboardHandler(bus, scm=CapableMockSCM(), config=MockConfig())
        sec = handler.get_security()
        bp = sec["branch_protection"]
        assert bp["available"] is True
        assert bp["protected"] is True
        assert bp["rules"] == {"required_approvals": 2}

    def test_unprotected_branch_returns_protected_false(self):
        class CapableMockSCM(MockSCM):
            @property
            def capabilities(self) -> set[str]:
                return {"branch_protection"}

            def get_branch_protection(self, branch: str) -> dict | None:
                return None

        bus = Bus()
        handler = DashboardHandler(bus, scm=CapableMockSCM(), config=MockConfig())
        bp = handler.get_security()["branch_protection"]
        assert bp["available"] is True
        assert bp["protected"] is False

    def test_request_failure_caught_and_reported(self):
        class FlakyMockSCM(MockSCM):
            @property
            def capabilities(self) -> set[str]:
                return {"branch_protection"}

            def get_branch_protection(self, branch: str) -> dict | None:
                raise RuntimeError("network timeout")

        bus = Bus()
        handler = DashboardHandler(bus, scm=FlakyMockSCM(), config=MockConfig())
        bp = handler.get_security()["branch_protection"]
        assert bp["available"] is True
        assert bp["protected"] is False
        assert bp.get("error") == "request_failed"


class TestStatusRecoveredCount:
    """#277 audit-fix: Status-Tab Aggregate Card 'Recovered Issues'."""

    def test_status_includes_recovered_count_field(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())
        status = handler.get_status()
        assert "recovered_count" in status
        assert isinstance(status["recovered_count"], int)
        assert status["recovered_count"] == 0  # no audit data -> zero

    def test_status_recovered_count_counts_recovered_trend(self, tmp_path: Path):
        """Issue with failed -> passed runs increments recovered_count."""
        from datetime import datetime, timezone

        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        # tz-aware ISO timestamps so get_system_tiles' cutoff comparison works
        # (regression-friendly: matches the pattern used by test_status_*).
        recent = datetime.now(timezone.utc).isoformat()
        with open(log_dir / "agent.jsonl", "w") as f:
            # Issue 42: failed run + passed run -> trend=recovered
            f.write(json.dumps({
                "ts": recent, "name": "AuditEvent",
                "payload": {
                    "message_name": "GateFailed", "issue": 42,
                    "correlation_id": "run-A",
                },
            }) + "\n")
            f.write(json.dumps({
                "ts": recent, "name": "AuditEvent",
                "payload": {
                    "message_name": "PRCreated", "issue": 42,
                    "correlation_id": "run-B",
                },
            }) + "\n")
            # Issue 99: single passing run -> trend="" (no count)
            f.write(json.dumps({
                "ts": recent, "name": "AuditEvent",
                "payload": {
                    "message_name": "PRCreated", "issue": 99,
                    "correlation_id": "run-X",
                },
            }) + "\n")

        bus = Bus()
        handler = DashboardHandler(
            bus, config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        status = handler.get_status()
        assert status["recovered_count"] == 1


class TestComplianceLegendEndpoint:
    """#252: Handler liefert OWASP- + AI-Act-Legend für Compliance-Tab."""

    def test_legend_endpoint_returns_owasp_and_ai_act(self):
        bus = Bus()
        handler = DashboardHandler(bus, config=MockConfig())
        legend = handler.get_compliance_legend()
        assert "owasp" in legend and isinstance(legend["owasp"], list)
        assert "ai_act" in legend and isinstance(legend["ai_act"], list)
        assert len(legend["owasp"]) == 10  # Top-10
        assert len(legend["ai_act"]) >= 5  # Mindestens 12, 13, 14, 15, 50


# #204: get_settings includes premium / llm_config / api_keys
class TestGetSettingsExtended:
    def _make_handler(self, tmp_path: Path):
        from unittest.mock import MagicMock
        bus = Bus()
        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "agent.config_dir": str(tmp_path),
            "llm.default.provider": "ollama",
            "llm.default.model": "llama3",
        }.get(key, default)
        config._overrides = {}
        return DashboardHandler(bus, config=config)

    def test_get_settings_includes_llm_config(self, tmp_path: Path):
        h = self._make_handler(tmp_path)
        result = h.get_settings()
        assert "llm_config" in result
        assert isinstance(result["llm_config"], list)

    def test_get_settings_includes_premium_status_free_mode(self, tmp_path: Path, monkeypatch):
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "_LICENSE", None)
        h = self._make_handler(tmp_path)
        result = h.get_settings()
        assert "premium_status" in result
        assert result["premium_status"]["active"] is False

    def test_get_settings_includes_premium_status_active(self, tmp_path: Path, monkeypatch):
        from samuel.core import license as _lic
        fake = _lic.License(
            email="alice@example.com",
            features=frozenset({"llm_routing"}),
            issued_at="2026-05-05T12:00:00Z",
        )
        monkeypatch.setattr(_lic, "_LICENSE", fake)
        h = self._make_handler(tmp_path)
        result = h.get_settings()
        assert result["premium_status"]["active"] is True
        assert result["premium_status"]["email"] == "alice@example.com"
        assert "llm_routing" in result["premium_status"]["features"]

    def test_get_settings_includes_api_keys(self, tmp_path: Path):
        h = self._make_handler(tmp_path)
        result = h.get_settings()
        assert "api_keys" in result
        assert isinstance(result["api_keys"], list)


# #309: Per-Task LLM-Config Write (Premium llm_routing_dashboard_write)
class TestSetLLMTaskConfig:
    def _make_handler(self, tmp_path: Path):
        from unittest.mock import MagicMock
        bus = Bus()
        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "agent.config_dir": str(tmp_path),
        }.get(key, default)
        return DashboardHandler(bus, config=config)

    def _activate_premium(self, monkeypatch):
        from samuel.core import license as _lic
        fake = _lic.License(
            email="t@x", features=frozenset({"llm_routing_dashboard_write"}),
            issued_at="2026-05-05T12:00:00Z",
        )
        monkeypatch.setattr(_lic, "_LICENSE", fake)

    def test_set_llm_task_config_premium_active(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "claude", "model": "claude-opus"})
        assert res["updated"] is True
        assert res["task"] == "planning"
        assert res["cfg"]["provider"] == "claude"

    def test_set_llm_task_config_free_mode_blocks(self, tmp_path, monkeypatch):
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "_LICENSE", None)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "claude"})
        assert res["updated"] is False
        assert "premium" in res["error"]

    def test_set_llm_task_config_unknown_task(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("not_a_task", {"provider": "claude"})
        assert res["updated"] is False
        assert "unknown task" in res["error"]

    def test_set_llm_task_config_invalid_provider(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "fakellm"})
        assert res["updated"] is False
        assert "unknown provider" in res["error"]

    def test_set_llm_task_config_writes_to_disk(self, tmp_path, monkeypatch):
        import json as _json
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        h.set_llm_task_config("review", {"provider": "deepseek", "model": "deepseek-coder"})
        fp = tmp_path / "llm" / "defaults.json"
        assert fp.exists()
        data = _json.loads(fp.read_text(encoding="utf-8"))
        assert data["tasks"]["review"]["provider"] == "deepseek"
        assert data["tasks"]["review"]["model"] == "deepseek-coder"

    def test_set_llm_task_config_clears_field_when_value_empty(self, tmp_path, monkeypatch):
        import json as _json
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        # Set a base_url first
        h.set_llm_task_config("planning", {"provider": "ollama", "base_url": "http://x:11434"})
        # Then clear it via empty string
        h.set_llm_task_config("planning", {"base_url": ""})
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert "base_url" not in data["tasks"]["planning"]
        assert data["tasks"]["planning"]["provider"] == "ollama"

    def test_set_llm_task_config_rejects_unknown_field(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "claude", "rogue": "x"})
        assert res["updated"] is False
        assert "unknown fields" in res["error"]

    # #316: Schedule-Block Validation + Premium-Gate
    def _activate_premium_with_schedule(self, monkeypatch):
        from samuel.core import license as _lic
        fake = _lic.License(
            email="t@x",
            features=frozenset({"llm_routing_dashboard_write", "llm_routing_advanced"}),
            issued_at="2026-05-05T12:00:00Z",
        )
        monkeypatch.setattr(_lic, "_LICENSE", fake)

    def test_set_llm_task_config_with_valid_schedule(self, tmp_path, monkeypatch):
        """#316-AC: name matches issue-body anchor."""
        import json as _json
        self._activate_premium_with_schedule(monkeypatch)
        h = self._make_handler(tmp_path)
        sched = {
            "active": True, "from": "22:00", "to": "06:00",
            "provider": "claude", "model": "claude-opus",
        }
        res = h.set_llm_task_config("planning", {"provider": "deepseek", "schedule": sched})
        assert res["updated"] is True
        assert res["cfg"]["schedule"] == sched
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert data["tasks"]["planning"]["schedule"]["from"] == "22:00"

    def test_set_llm_task_config_with_invalid_time_format(self, tmp_path, monkeypatch):
        """#316-AC: name matches issue-body anchor."""
        self._activate_premium_with_schedule(monkeypatch)
        h = self._make_handler(tmp_path)
        for bad in ("25:00", "22-00", "abc", "12:99"):
            res = h.set_llm_task_config("planning", {
                "schedule": {
                    "active": True, "from": bad, "to": "06:00",
                    "provider": "claude", "model": "claude-opus",
                }
            })
            assert res["updated"] is False
            assert "schedule.from" in res["error"] or "invalid" in res["error"]

    def test_set_llm_task_config_schedule_clear_when_inactive(self, tmp_path, monkeypatch):
        """#316-AC: active=False removes the schedule field on disk."""
        import json as _json
        self._activate_premium_with_schedule(monkeypatch)
        h = self._make_handler(tmp_path)
        # First: set an active schedule
        h.set_llm_task_config("planning", {
            "schedule": {
                "active": True, "from": "22:00", "to": "06:00",
                "provider": "claude", "model": "claude-opus",
            }
        })
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert "schedule" in data["tasks"]["planning"]
        # Then: send active=false -> schedule removed
        h.set_llm_task_config("planning", {"schedule": {"active": False}})
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert "schedule" not in data["tasks"]["planning"]

    def test_set_llm_task_config_schedule_blocked_without_advanced_feature(self, tmp_path, monkeypatch):
        """Without llm_routing_advanced: schedule is rejected even with premium."""
        self._activate_premium(monkeypatch)  # only dashboard_write, NOT advanced
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {
            "schedule": {
                "active": True, "from": "22:00", "to": "06:00",
                "provider": "claude", "model": "claude-opus",
            }
        })
        assert res["updated"] is False
        assert "llm_routing_advanced" in res["error"]

    def test_set_llm_task_config_schedule_unknown_provider(self, tmp_path, monkeypatch):
        self._activate_premium_with_schedule(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {
            "schedule": {
                "active": True, "from": "22:00", "to": "06:00",
                "provider": "fakellm", "model": "x",
            }
        })
        assert res["updated"] is False
        assert "schedule.provider" in res["error"]

    def test_set_llm_task_config_schedule_empty_model(self, tmp_path, monkeypatch):
        self._activate_premium_with_schedule(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {
            "schedule": {
                "active": True, "from": "22:00", "to": "06:00",
                "provider": "claude", "model": "",
            }
        })
        assert res["updated"] is False
        assert "schedule.model" in res["error"]

    def test_save_then_get_roundtrip_preserves_system_prompt(
        self, tmp_path, monkeypatch,
    ):
        """#338-audit: User saves a system_prompt, reloads — value must come
        back from get_settings(). Was missing before because get_llm_routing
        dropped the field."""
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        save_res = h.set_llm_task_config(
            "review",
            {"provider": "deepseek", "system_prompt": "reviewer.md"},
        )
        assert save_res["updated"] is True

        settings = h.get_settings()
        review = next(
            r for r in settings.get("llm_config", []) if r["task"] == "review"
        )
        assert review["system_prompt"] == "reviewer.md"

    # #351: per-provider prompt-override map.
    def test_set_llm_task_config_accepts_system_prompt_by_provider(
        self, tmp_path, monkeypatch,
    ):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {
            "provider": "deepseek",
            "system_prompt": "planner.md",
            "system_prompt_by_provider": {
                "deepseek": "planner_local.md",
                "claude": "planner_kompakt.md",
            },
        })
        assert res["updated"] is True
        assert res["cfg"]["system_prompt_by_provider"] == {
            "deepseek": "planner_local.md",
            "claude": "planner_kompakt.md",
        }

    def test_set_llm_task_config_rejects_unknown_provider_in_map(
        self, tmp_path, monkeypatch,
    ):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {
            "system_prompt_by_provider": {"frobnicator": "x.md"},
        })
        assert res["updated"] is False
        assert "system_prompt_by_provider" in res["error"]
        assert "frobnicator" in res["error"]

    def test_set_llm_task_config_rejects_path_traversal_in_map_value(
        self, tmp_path, monkeypatch,
    ):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {
            "system_prompt_by_provider": {"deepseek": "../etc/passwd.md"},
        })
        assert res["updated"] is False
        assert "system_prompt_by_provider" in res["error"]

    def test_set_llm_task_config_rejects_non_md_in_map_value(
        self, tmp_path, monkeypatch,
    ):
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {
            "system_prompt_by_provider": {"deepseek": "planner.txt"},
        })
        assert res["updated"] is False
        assert "system_prompt_by_provider" in res["error"]
        assert ".md" in res["error"]

    def test_empty_map_drops_field_from_persisted_config(
        self, tmp_path, monkeypatch,
    ):
        """UX-pattern: passing {} clears the override (mirrors empty-string
        behaviour for scalar fields)."""
        self._activate_premium(monkeypatch)
        h = self._make_handler(tmp_path)
        # First save: map is set
        h.set_llm_task_config("planning", {
            "provider": "deepseek",
            "system_prompt_by_provider": {"deepseek": "x.md"},
        })
        # Then save: empty map -> field is removed
        res = h.set_llm_task_config("planning", {
            "system_prompt_by_provider": {},
        })
        assert res["updated"] is True
        assert "system_prompt_by_provider" not in res["cfg"]


# #314: Test-Connection (LLM-Editor)
class TestConnection:
    def _make_handler(self, tester=None):
        from unittest.mock import MagicMock
        bus = Bus()
        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: default
        return DashboardHandler(bus, config=config, connection_tester=tester)

    def test_test_connection_endpoint_calls_validate(self):
        """#314-AC: name matches issue-body anchor for AC-Verifier."""
        called: dict = {}
        def fake_tester(provider: str, cfg: dict) -> dict:
            called["provider"] = provider
            called["cfg"] = cfg
            return {"valid": True, "detail": "http 200", "balance": 12.5}
        h = self._make_handler(tester=fake_tester)
        res = h.test_connection("deepseek", {"model": "deepseek-chat"})
        assert called["provider"] == "deepseek"
        assert called["cfg"] == {"model": "deepseek-chat"}
        assert res["valid"] is True
        assert res["balance"] == 12.5

    def test_test_connection_endpoint_with_unknown_provider_returns_400(self):
        """#314-AC: unknown provider rejected."""
        h = self._make_handler(tester=lambda p, c: {"valid": True, "detail": "", "balance": None})
        res = h.test_connection("fakellm", {})
        assert res["valid"] is False
        assert "unknown provider" in res["detail"]

    def test_test_connection_no_tester_wired(self):
        h = self._make_handler(tester=None)
        res = h.test_connection("claude", {"model": "x"})
        assert res["valid"] is False
        assert "not wired" in res["detail"]

    def test_test_connection_strips_unknown_fields(self):
        captured: dict = {}
        def fake_tester(provider: str, cfg: dict) -> dict:
            captured.update(cfg)
            return {"valid": True, "detail": "ok", "balance": None}
        h = self._make_handler(tester=fake_tester)
        h.test_connection("claude", {"model": "x", "rogue_field": "ignored", "base_url": ""})
        assert captured == {"model": "x"}  # rogue dropped, empty base_url dropped

    def test_test_connection_failure_returns_detail(self):
        h = self._make_handler(tester=lambda p, c: {"valid": False, "detail": "unauthorized", "balance": None})
        res = h.test_connection("claude", {"model": "x"})
        assert res["valid"] is False
        assert res["detail"] == "unauthorized"

    def test_api_keys_section_shows_balance_when_available(self, tmp_path):
        """#314-AC: get_settings()['api_keys'] entries have balance/balance_note."""
        from unittest.mock import MagicMock
        bus = Bus()
        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "agent.config_dir": str(tmp_path),
        }.get(key, default)
        config._overrides = {}
        # Resolver liefert Balance fuer deepseek, "not provided" fuer claude
        def resolver(provider, env_key, url):
            if provider == "deepseek":
                return (12.5, "live")
            return (None, "not provided by API")
        h = DashboardHandler(bus, config=config, balance_resolver=resolver)
        result = h.get_settings()
        api_keys = result.get("api_keys", [])
        assert isinstance(api_keys, list)
        # Each api_key entry should have provider, status, and balance/balance_note keys
        for entry in api_keys:
            assert "provider" in entry
            assert "balance_note" in entry  # always set by data._cached_validate path


# #319: Self-Mode-Health-Aggregator
class TestGetSelfModeHealth:
    def _write_metrics(self, lines: list[dict]) -> None:
        import json as _json
        from pathlib import Path as _Path
        log_dir = _Path("data") / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fp = log_dir / "self_mode_metrics.jsonl"
        fp.write_text("\n".join(_json.dumps(r) for r in lines) + "\n", encoding="utf-8")

    def _cleanup(self):
        from pathlib import Path as _Path
        fp = _Path("data") / "logs" / "self_mode_metrics.jsonl"
        if fp.exists():
            fp.unlink()

    def test_get_self_mode_health_empty_when_no_metrics(self, tmp_path):
        self._cleanup()
        from unittest.mock import MagicMock
        h = DashboardHandler(Bus(), config=MagicMock())
        result = h.get_self_mode_health()
        assert result["total"] == 0
        assert result["success_rate"] is None
        assert result["recent_runs"] == []

    def test_get_self_mode_health_aggregates_correctly(self, tmp_path):
        self._write_metrics([
            {"issue": 1, "ts": "2026-05-05T10:00:00Z", "duration_seconds": 60.0,
             "rounds": 1, "success": True, "reason": "complete",
             "patches_applied": 5, "rounds_stats": []},
            {"issue": 2, "ts": "2026-05-05T11:00:00Z", "duration_seconds": 120.0,
             "rounds": 3, "success": False, "reason": "no_progress",
             "patches_applied": 2, "rounds_stats": []},
            {"issue": 3, "ts": "2026-05-05T12:00:00Z", "duration_seconds": 90.0,
             "rounds": 2, "success": True, "reason": "complete",
             "patches_applied": 8, "rounds_stats": []},
        ])
        try:
            from unittest.mock import MagicMock
            h = DashboardHandler(Bus(), config=MagicMock())
            r = h.get_self_mode_health()
            assert r["total"] == 3
            assert r["success_rate"] == 2/3 or abs(r["success_rate"] - 2/3) < 0.01
            assert r["no_progress_rate"] == 1/3 or abs(r["no_progress_rate"] - 1/3) < 0.01
            assert r["avg_rounds"] == 2.0
            assert r["avg_duration_s"] == 90.0
            assert len(r["recent_runs"]) == 3
            # neueste zuerst
            assert r["recent_runs"][0]["issue"] == 3
        finally:
            self._cleanup()

    def test_get_self_mode_health_limits_to_recent(self, tmp_path):
        self._write_metrics([
            {"issue": i, "ts": f"t{i}", "duration_seconds": 10.0,
             "rounds": 1, "success": True, "reason": "complete",
             "patches_applied": 1, "rounds_stats": []}
            for i in range(60)
        ])
        try:
            from unittest.mock import MagicMock
            h = DashboardHandler(Bus(), config=MagicMock())
            r = h.get_self_mode_health(limit=50)
            assert r["total"] == 50
            # recent_runs hat max 20 (newest first)
            assert len(r["recent_runs"]) == 20
            assert r["recent_runs"][0]["issue"] == 59  # neueste
        finally:
            self._cleanup()
