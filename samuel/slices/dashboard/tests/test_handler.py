from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.ports import IConfig, IRunProjectionStore, IVersionControl
from samuel.core.state import RunProjectionRecord
from samuel.core.types import Comment, Issue
from samuel.slices.dashboard.handler import DashboardHandler


@pytest.fixture(autouse=True)
def _explicit_setup_configuration_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAMUEL_CONFIGURATION_MODE", "setup")


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


class MemoryProjectionStore(IRunProjectionStore):
    def __init__(self) -> None:
        self.records: dict[str, RunProjectionRecord] = {}

    def upsert_projection(self, record: RunProjectionRecord) -> None:
        self.records[record.projection_key] = record

    def get_projection(self, projection_key: str) -> RunProjectionRecord | None:
        return self.records.get(projection_key)

    def list_projections(
        self,
        issue_number: int | None = None,
        *,
        series: str | None = None,
    ) -> list[RunProjectionRecord]:
        return [
            record
            for record in self.records.values()
            if (issue_number is None or record.issue_number == issue_number)
            and (series is None or record.series == series)
        ]


class ProjectionState:
    def __init__(self, instance_uuid: str = "dashboard-test-instance") -> None:
        self.instance_uuid = instance_uuid

    def status(self) -> Any:
        return SimpleNamespace(authority_instance=self.instance_uuid)


class TestDashboardHandler:
    def test_status_exposes_bound_resume_state(self):
        class ResumeStatus:
            @staticmethod
            def status() -> dict[str, Any]:
                return {
                    "enabled": True,
                    "pending": 2,
                    "blocked": 1,
                    "last_outcome": {"reason": "resume_lease_live"},
                }

        bus = Bus()
        bus.resume_coordinator = ResumeStatus()

        status = DashboardHandler(bus, config=MockConfig()).get_status()

        assert status["resume"] == {
            "enabled": True,
            "pending": 2,
            "blocked": 1,
            "last_outcome": {"reason": "resume_lease_live"},
        }

    def test_status_exposes_injected_product_and_build_identity(self):
        revision = "c" * 40
        handler = DashboardHandler(
            Bus(),
            config=MockConfig(),
            product_version="2.0.0a0",
            build_revision=revision,
            build_dirty=True,
            build_revision_source="git",
        )

        assert handler.get_status()["build"] == {
            "product_version": "2.0.0a0",
            "revision": revision,
            "dirty": True,
            "revision_source": "git",
        }

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
            f.write(
                json.dumps(
                    {
                        "ts": recent,
                        "name": "AuditEvent",
                        "payload": {"message_name": "EvalCompleted", "score": 0.7, "baseline": 0.5},
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": recent,
                        "name": "AuditEvent",
                        "payload": {"message_name": "GateFailed", "reason": "x"},
                    }
                )
                + "\n"
            )
        bus = Bus()
        handler = DashboardHandler(
            bus,
            scm=MockSCM(),
            config=MockConfig(
                {
                    "agent.data_dir": str(tmp_path),
                    "llm.default.provider": "deepseek",
                    "llm.deepseek.model": "deepseek-chat",
                }
            ),
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
        from samuel.core.health_projection import record_projection

        bus = Bus()
        state = ProjectionState()
        projections = MemoryProjectionStore()
        bus.state_store = state
        checks = {"scm": True, "config": True, "llm": True}
        record_projection(
            projections,
            kind="technical_health",
            status="passed",
            instance_uuid=state.instance_uuid,
            summary={"checks": checks},
        )
        handler = DashboardHandler(
            bus,
            scm=MockSCM(),
            config=MockConfig(),
            run_projection_store=projections,
        )
        health = handler.get_health()
        assert health["healthy"] is True
        assert health["checks"] == checks
        assert health["passive"] is True

    def test_health_exposes_bounded_retention_authority(self):
        from samuel.core.health_projection import record_projection

        bus = Bus()
        state = ProjectionState()
        projections = MemoryProjectionStore()
        bus.state_store = state

        class RetentionStatus:
            @staticmethod
            def status():
                return {
                    "schema": "samuel-retention-status.v1",
                    "retention_emergency_stop": True,
                    "future_enforcement_blocked": True,
                    "pending_review_count": 1,
                    "categories": [
                        {
                            "category": "score_derivations",
                            "effective_mode": "report_only_pending_review",
                            "category_digest": "sha256:" + "a" * 64,
                            "profile_role_digest": "sha256:" + "b" * 64,
                            "evidence_digest": None,
                            "grant_cutoff_utc": None,
                            "activated_at": None,
                        }
                    ],
                    "last_execution": None,
                    "findings": [],
                }

        bus.retention_coordinator = RetentionStatus()
        record_projection(
            projections,
            kind="technical_health",
            status="passed",
            instance_uuid=state.instance_uuid,
            summary={"checks": {"state": True}},
        )
        health = DashboardHandler(
            bus,
            config=MockConfig(),
            run_projection_store=projections,
        ).get_health()

        assert health["retention"]["status"] == "available"
        assert health["retention"]["pending_review_count"] == 1
        assert health["retention"]["categories"][0]["category_digest"].startswith("sha256:")

    def test_health_scm_missing(self):
        from samuel.core.health_projection import record_projection

        bus = Bus()
        state = ProjectionState()
        projections = MemoryProjectionStore()
        bus.state_store = state
        record_projection(
            projections,
            kind="technical_health",
            status="failed",
            instance_uuid=state.instance_uuid,
            summary={"checks": {"scm": False, "config": True}},
        )
        handler = DashboardHandler(
            bus,
            scm=None,
            config=MockConfig(),
            run_projection_store=projections,
        )
        health = handler.get_health()
        assert health["healthy"] is False
        assert health["checks"]["scm"] is False

    def test_metrics_aggregated_from_audit_log(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(
                json.dumps(
                    {
                        "name": "AuditEvent",
                        "payload": {
                            "message_type": "PlanIssueCommand",
                            "message_name": "PlanIssue",
                            "duration_ms": 12.0,
                        },
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "name": "AuditEvent",
                        "payload": {
                            "message_type": "PlanIssueCommand",
                            "message_name": "PlanIssue",
                            "duration_ms": 8.0,
                        },
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "name": "AuditEvent",
                        "payload": {
                            "message_type": "WorkflowAborted",
                            "message_name": "WorkflowAborted",
                            "source_command": "PlanIssue",
                            "reason": "x",
                        },
                    }
                )
                + "\n"
            )

        bus = Bus()
        handler = DashboardHandler(
            bus,
            scm=MockSCM(),
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        metrics = handler.get_metrics()
        assert metrics["counts"]["PlanIssue"] == 2
        assert metrics["total_ms"]["PlanIssue"] == 20.0
        assert metrics["errors"]["PlanIssue"] == 1

    def test_metrics_empty_when_no_audit_log(self, tmp_path: Path):
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
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
            f.write(
                json.dumps(
                    {
                        "ts": "2026-04-29T10:00",
                        "name": "AuditEvent",
                        "payload": {"message_name": "PlanCreated"},
                    }
                )
                + "\n"
            )
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
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
            f.write(
                json.dumps(
                    {"ts": "t1", "name": "AuditEvent", "payload": {"message_name": "GateFailed"}}
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {"ts": "t2", "name": "AuditEvent", "payload": {"message_name": "HealingFailed"}}
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {"ts": "t3", "name": "AuditEvent", "payload": {"message_name": "PlanCreated"}}
                )
                + "\n"
            )
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        result = handler.get_logs()
        assert result["level_counts"] == {"info": 1, "warn": 1, "error": 1}

    def test_workflow_uses_data_dir_from_config(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-04-29T10:00",
                        "name": "AuditEvent",
                        "payload": {"message_name": "PRCreated", "issue": 42},
                    }
                )
                + "\n"
            )
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        wf = handler.get_workflow()
        assert any(i["number"] == 42 for i in wf["issues"])
        issue = next(i for i in wf["issues"] if i["number"] == 42)
        assert issue["timestamp"] == "2026-04-29T10:00"

    def test_security_uses_data_dir_from_config(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        with open(log_dir / "agent.jsonl", "w") as f:
            f.write(
                json.dumps(
                    {
                        "ts": "t",
                        "name": "AuditEvent",
                        "payload": {"message_name": "GateFailed", "owasp_risk": "A04: x"},
                    }
                )
                + "\n"
            )
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        sec = handler.get_security()
        assert isinstance(sec["owasp"], list)
        # #290: Legacy A04 wird zu ASI04 (Agentic Supply Chain Vulnerabilities)
        asi04 = next(r for r in sec["owasp"] if r["id"] == "ASI04")
        assert asi04["count"] == 1

    def test_llm_includes_provider_from_config(self, tmp_path: Path):
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig(
                {
                    "agent.data_dir": str(tmp_path),
                    "llm.default.provider": "deepseek",
                }
            ),
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
            f.write(
                json.dumps(
                    {
                        "ts": "2026-04-29T10:00",
                        "name": "AuditEvent",
                        "payload": {"message_name": "PlanCreated", "issue": 42},
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": "2026-04-29T10:05",
                        "name": "AuditEvent",
                        "payload": {
                            "message_name": "LLMCallCompleted",
                            "issue": 42,
                            "provider": "deepseek",
                            "task": "planning",
                            "tokens": 200,
                            "cost": 0.001,
                        },
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": "2026-04-29T10:10",
                        "name": "AuditEvent",
                        "payload": {"message_name": "PRCreated", "issue": 42},
                    }
                )
                + "\n"
            )
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
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
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
        )
        d = handler.get_workflow_detail(999)
        assert "error" in d
        assert "999" in d["error"]


class TestSetRiskClass:
    """#374: Deployment-Risikoklasse im Dashboard editierbar + persistiert."""

    def _handler(self, tmp_path: Path):
        bus = Bus()
        return DashboardHandler(
            bus,
            config=MockConfig({"agent.config_dir": str(tmp_path)}),
        )

    def test_set_persists_and_legend_reflects_it(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        h = self._handler(tmp_path)

        # Default-Zustand: Self-Mode (Limited Risk), keine Datei
        legend = h.get_compliance_legend()
        assert legend["ai_act_risk_class"] == "limited_risk"
        assert legend["ai_act_risk_class_source"] == "default"

        res = h.set_risk_class("high_risk")
        assert res["updated"] is True
        assert (tmp_path / "compliance.json").exists()

        # Persistiert -> Legend leitet Pflicht fuer Art. 12-15 ab
        legend2 = h.get_compliance_legend()
        assert legend2["ai_act_risk_class"] == "high_risk"
        assert legend2["ai_act_risk_class_source"] == "config"
        obl = {e["article"]: e["obligation"] for e in legend2["ai_act"]}
        assert obl["Art. 14"] == "required"
        assert obl["Art. 50"] == "required"

    def test_invalid_value_rejected_and_not_written(self, tmp_path: Path):
        h = self._handler(tmp_path)
        res = h.set_risk_class("catastrophic")
        assert res["updated"] is False
        assert "invalid risk class" in res["error"]
        assert not (tmp_path / "compliance.json").exists()

    def test_env_override_wins_and_source_is_env(self, tmp_path: Path, monkeypatch):
        h = self._handler(tmp_path)
        h.set_risk_class("minimal_risk")  # persistiert
        monkeypatch.setenv("SAMUEL_RISK_CLASS", "high_risk")  # env-Override
        legend = h.get_compliance_legend()
        assert legend["ai_act_risk_class"] == "high_risk"
        assert legend["ai_act_risk_class_source"] == "env"

    def test_value_normalized(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        h = self._handler(tmp_path)
        res = h.set_risk_class("  High_Risk  ")
        assert res["updated"] is True
        assert res["risk_class"] == "high_risk"

    def test_change_publishes_config_changed_event(self, tmp_path: Path, monkeypatch):
        """#375: erfolgreiche Aenderung publisht ConfigChanged mit alt/neu/Quelle
        (AI-Act Art. 12 — die Compliance-Einstufung selbst ist auditierbar)."""
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        bus = Bus()
        captured: list = []
        bus.subscribe("ConfigChanged", lambda e: captured.append(e))
        h = DashboardHandler(
            bus,
            config=MockConfig({"agent.config_dir": str(tmp_path)}),
        )
        res = h.set_risk_class("high_risk")
        assert res["updated"] is True and res["changed"] is True
        assert len(captured) == 1
        p = captured[0].payload
        assert p["setting"] == "ai_act_risk_class"
        assert p["old"] == "limited_risk"
        assert p["new"] == "high_risk"
        assert p["source"] == "dashboard"

    def test_invalid_value_does_not_publish(self, tmp_path: Path):
        bus = Bus()
        captured: list = []
        bus.subscribe("ConfigChanged", lambda e: captured.append(e))
        h = DashboardHandler(
            bus,
            config=MockConfig({"agent.config_dir": str(tmp_path)}),
        )
        h.set_risk_class("nonsense")
        assert captured == []

    def test_noop_change_does_not_publish(self, tmp_path: Path, monkeypatch):
        """Setzen auf den bereits aktiven Wert publisht nichts (kein Rausch-Event)."""
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        bus = Bus()
        captured: list = []
        bus.subscribe("ConfigChanged", lambda e: captured.append(e))
        h = DashboardHandler(
            bus,
            config=MockConfig({"agent.config_dir": str(tmp_path)}),
        )
        res = h.set_risk_class("limited_risk")  # == Default, kein echter Wechsel
        assert res["updated"] is True and res["changed"] is False
        assert captured == []


class _AttrConfig(IConfig):
    """#270: Config-Stub mit feature_flag aus dict + _overrides (live)."""

    def __init__(self, config_dir: Path, features: dict | None = None):
        self._data = {"agent.config_dir": str(config_dir)}
        self._features = dict(features or {})
        self._overrides: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return self._data.get(key, default)

    def feature_flag(self, name: str) -> bool:
        k = f"features.{name}"
        if k in self._overrides:
            return bool(self._overrides[k])
        return bool(self._features.get(name, False))

    def reload(self) -> None:
        pass


class TestSetAttribution:
    """#270: Externe LLM-Code-Kennzeichnung — Toggle, Persistenz, Audit, Sperre."""

    def test_enable_persists_and_publishes(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        bus = Bus()
        captured: list = []
        bus.subscribe("ConfigChanged", lambda e: captured.append(e))
        h = DashboardHandler(bus, config=_AttrConfig(tmp_path, {"llm_attribution": False}))

        res = h.set_attribution(True)
        assert res["updated"] is True and res["changed"] is True
        assert "warning" not in res
        data = json.loads((tmp_path / "features.json").read_text())
        assert data["llm_attribution"] is True
        assert h.get_attribution()["enabled"] is False
        assert res["restart_required"] is True
        assert len(captured) == 1
        p = captured[0].payload
        assert p["setting"] == "llm_attribution"
        assert p["old"] is False and p["new"] is True

    def test_disable_emits_art50_warning(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        bus = Bus()
        captured: list = []
        bus.subscribe("ConfigChanged", lambda e: captured.append(e))
        h = DashboardHandler(bus, config=_AttrConfig(tmp_path, {"llm_attribution": True}))

        res = h.set_attribution(False)
        assert res["updated"] is True and res["changed"] is True
        assert "Art. 50" in res["warning"]
        assert "Art. 50" in captured[0].payload["reason"]

    def test_high_risk_locks_toggle(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        (tmp_path / "compliance.json").write_text(
            json.dumps({"risk_classification": "high_risk"}), encoding="utf-8"
        )
        bus = Bus()
        h = DashboardHandler(bus, config=_AttrConfig(tmp_path, {"llm_attribution": True}))

        res = h.set_attribution(False)
        assert res["updated"] is False and res["locked"] is True
        assert "Art. 50" in res["error"]
        # features.json NICHT geschrieben
        assert not (tmp_path / "features.json").exists()
        assert h.get_attribution()["locked"] is True

    def test_verbosity_persisted_and_validated(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        bus = Bus()
        h = DashboardHandler(bus, config=_AttrConfig(tmp_path, {"llm_attribution": True}))

        res = h.set_attribution(True, "full")
        assert res["updated"] is True and res["verbosity"] == "full"
        priv = json.loads((tmp_path / "privacy.json").read_text())
        assert priv["attribution"]["verbosity"] == "full"

        bad = h.set_attribution(True, "loud")
        assert bad["updated"] is False and "invalid verbosity" in bad["error"]

    def test_second_file_failure_reports_partial_persistence_and_restart(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        h = DashboardHandler(Bus(), config=_AttrConfig(tmp_path, {"llm_attribution": False}))
        calls = 0

        def persist(_filename, _key, _value):
            nonlocal calls
            calls += 1
            return (True, "") if calls == 1 else (False, "simulated second-file failure")

        monkeypatch.setattr(h, "_persist_json_key", persist)

        result = h.set_attribution(True, "full")

        assert result["updated"] is False
        assert result["code"] == "configuration_partial_persistence"
        assert result["restart_required"] is True
        assert result["configuration"]["restart_required"] is True

    def test_noop_does_not_publish(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        bus = Bus()
        captured: list = []
        bus.subscribe("ConfigChanged", lambda e: captured.append(e))
        h = DashboardHandler(bus, config=_AttrConfig(tmp_path, {"llm_attribution": True}))

        res = h.set_attribution(True)  # bereits an
        assert res["updated"] is True and res["changed"] is False
        assert captured == []


class TestGetQuality:
    """#153: Quality-Tab-Endpoint — Struktur + Param-Size aus Config."""

    def test_returns_overview_structure(self, tmp_path: Path) -> None:
        bus = Bus()
        cfg = MockConfig(
            {
                "agent.data_dir": str(tmp_path),
                "llm.min_local_model_params_b": 5,
            }
        )
        h = DashboardHandler(bus, config=cfg)
        out = h.get_quality()
        assert set(out) >= {
            "matrix",
            "heatmap",
            "selected_series",
            "attribution",
            "param_warnings",
            "min_params_b",
        }
        assert out["min_params_b"] == 5.0
        assert out["heatmap"] == {"tasks": [], "rows": []}
        assert out["selected_series"] == {
            "evidence_origin": "unbound_worktree",
            "observation_schema": "legacy.v1",
            "scoring_policy_version": "legacy",
            "formula_version": "legacy",
        }
        assert out["attribution"] == {
            "series_calls": 0,
            "unattributed_calls": 0,
            "other_series_calls": 0,
        }

    def test_min_params_defaults_to_seven(self, tmp_path: Path) -> None:
        bus = Bus()
        h = DashboardHandler(bus, config=MockConfig({"agent.data_dir": str(tmp_path)}))
        assert h.get_quality()["min_params_b"] == 7.0


class TestGetActivity:
    """#230: Activity-Endpoint liefert den SCM-Stream."""

    def test_returns_activity_list(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.jsonl").write_text(
            json.dumps(
                {
                    "ts": "t1",
                    "name": "AuditEvent",
                    "payload": {
                        "message_name": "PullRequestMerged",
                        "number": 9,
                        "actor": "bot",
                        "actor_type": "bot",
                        "source": "webhook",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        bus = Bus()
        h = DashboardHandler(bus, config=MockConfig({"agent.data_dir": str(tmp_path)}))
        out = h.get_activity()
        assert "activity" in out
        assert out["activity"][0]["event"] == "PullRequestMerged"

    def test_empty_when_no_log(self, tmp_path: Path) -> None:
        bus = Bus()
        h = DashboardHandler(bus, config=MockConfig({"agent.data_dir": str(tmp_path)}))
        assert h.get_activity() == {"activity": []}


class TestSetFeatureFlag:
    def test_toggle_known_flag_persists_for_restart(self):
        import tempfile

        from samuel.core.config import FileConfig

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "agent.json").write_text(
                json.dumps({"config_dir": tmp}),
                encoding="utf-8",
            )
            cfg = FileConfig(tmp)
            bus = Bus()
            handler = DashboardHandler(bus, config=cfg)

            result = handler.set_feature_flag("eval", False)

            assert result["updated"] is True
            assert result["enabled"] is False
            assert cfg.feature_flag("eval") is False

            result2 = handler.set_feature_flag("eval", True)
            assert result2["updated"] is True
            assert cfg.feature_flag("eval") is False
            assert json.loads((Path(tmp) / "features.json").read_text())["eval"] is True
            assert result2["restart_required"] is True

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

    def test_toggle_with_config_without_overrides_persists_without_live_override(self, tmp_path):
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.config_dir": str(tmp_path)}),
        )

        result = handler.set_feature_flag("eval", True)
        assert result["updated"] is True
        assert json.loads((tmp_path / "features.json").read_text())["eval"] is True


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

    def test_self_check_runs_active_probes_for_configured_task_routes(self, tmp_path: Path):
        defaults = tmp_path / "llm" / "defaults.json"
        defaults.parent.mkdir()
        defaults.write_text(
            json.dumps(
                {
                    "default": {"timeout": 60},
                    "tasks": {
                        "planning": {
                            "provider": "openrouter",
                            "model": "vendor/planner",
                            "timeout": 12,
                        },
                        "implementation": {
                            "provider": "deepseek",
                            "model": "coder",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        bus = Bus()
        commands: list[HealthCheckCommand] = []

        def health(cmd: HealthCheckCommand) -> dict[str, Any]:
            commands.append(cmd)
            return {
                "healthy": True,
                "checks": {},
                "operational_readiness": {"status": "ready"},
            }

        bus.register_command(
            "HealthCheck",
            health,
        )
        calls: list[tuple[str, dict[str, Any]]] = []

        def tester(provider: str, cfg: dict[str, Any]) -> dict[str, Any]:
            calls.append((provider, cfg))
            return {"valid": provider == "openrouter", "detail": "private provider response"}

        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.config_dir": str(tmp_path)}),
            connection_tester=tester,
        )

        handler.get_self_check()

        assert calls == [
            ("openrouter", {"model": "vendor/planner", "timeout": 12}),
            ("deepseek", {"model": "coder", "timeout": 60}),
        ]
        probe = commands[0].payload["provider_probe"]
        assert probe == {
            "schema": "samuel-provider-probe.v1",
            "performed": True,
            "passed": False,
            "routes": [
                {"task": "planning", "provider": "openrouter", "passed": True},
                {"task": "implementation", "provider": "deepseek", "passed": False},
            ],
        }
        assert "private provider response" not in str(probe)


class TestLLMRouting:
    def test_routing_included_in_get_llm(self, tmp_path):
        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig(
                {
                    "agent.config_dir": str(tmp_path),
                    "llm.default.provider": "ollama",
                    "llm.default.model": "llama3",
                }
            ),
        )
        data = handler.get_llm()
        assert "routing" in data
        assert isinstance(data["routing"], list)
        assert data["routing"][0]["provider"] == "ollama"

    def test_configured_route_and_old_reservation_are_not_current_activity(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "agent.jsonl").write_text(
            json.dumps(
                {
                    "payload": {
                        "message_name": "LLMBudgetAttemptReserved",
                        "task": "review",
                        "provider": "old-provider",
                        "model": "old-model",
                        "attempt_key": "old-attempt",
                        "correlation_id": "old-run",
                        "issue": 1,
                    }
                }
            )
            + "\n"
        )
        handler = DashboardHandler(
            Bus(),
            config=MockConfig(
                {"agent.data_dir": str(tmp_path), "llm.default.provider": "configured"}
            ),
            llm_activity_resolver=lambda: {"status": "idle", "calls": [], "last_call": None},
        )
        data = handler.get_llm()
        assert data["provider"] == "configured"
        assert data["activity"] == {"status": "idle", "calls": [], "last_call": None}

    def test_missing_or_broken_live_source_is_unknown_without_provider_action(self):
        def unavailable():
            raise ValueError("private response")

        for resolver in (None, unavailable):
            bus = Bus()
            events: list[Any] = []
            bus.subscribe("*", events.append)
            data = DashboardHandler(bus, llm_activity_resolver=resolver).get_llm()
            assert data["activity"] == {"status": "unknown", "calls": [], "last_call": None}
            assert "private response" not in str(data)
            assert events == []


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
            bus,
            config=MockConfig({"agent.default_branch": "trunk"}),
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

    def test_permission_failure_isolated_and_classified(self):
        class PermissionFailure(RuntimeError):
            status = 403

        class WriteOnlySCM(MockSCM):
            @property
            def capabilities(self) -> set[str]:
                return {"branch_protection"}

            def get_branch_protection(self, branch: str) -> dict | None:
                raise PermissionFailure("admin write required")

        bus = Bus()
        handler = DashboardHandler(bus, scm=WriteOnlySCM(), config=MockConfig())

        security = handler.get_security()
        bp = security["branch_protection"]

        assert bp == {
            "available": True,
            "protected": False,
            "branch": "main",
            "rules": None,
            "error": "permission_denied",
            "required_permission": "unknown",
            "http_status": 403,
        }
        assert "owasp" in security


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
            f.write(
                json.dumps(
                    {
                        "ts": recent,
                        "name": "AuditEvent",
                        "payload": {
                            "message_name": "WorkflowBlocked",
                            "issue": 42,
                            "correlation_id": "run-A",
                        },
                    }
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "ts": recent,
                        "name": "AuditEvent",
                        "payload": {
                            "message_name": "PRCreated",
                            "issue": 42,
                            "correlation_id": "run-B",
                        },
                    }
                )
                + "\n"
            )
            # Issue 99: single passing run -> trend="" (no count)
            f.write(
                json.dumps(
                    {
                        "ts": recent,
                        "name": "AuditEvent",
                        "payload": {
                            "message_name": "PRCreated",
                            "issue": 99,
                            "correlation_id": "run-X",
                        },
                    }
                )
                + "\n"
            )

        bus = Bus()
        handler = DashboardHandler(
            bus,
            config=MockConfig({"agent.data_dir": str(tmp_path)}),
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


# #204: get_settings includes LLM config, model cache, and API keys.
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
        assert "llm_global_config" in result

    def test_get_settings_has_no_entitlement_status(self, tmp_path: Path):
        h = self._make_handler(tmp_path)
        result = h.get_settings()

        assert "premium_status" not in result

    def test_get_settings_includes_api_keys(self, tmp_path: Path):
        h = self._make_handler(tmp_path)
        result = h.get_settings()
        assert "api_keys" in result
        assert isinstance(result["api_keys"], list)

    def test_get_settings_includes_model_cache_status(self, tmp_path: Path):
        h = self._make_handler(tmp_path)
        h._model_cache_status_resolver = lambda: {"status": "upgrade_required"}

        result = h.get_settings()

        assert result["model_cache"] == {"status": "upgrade_required"}

    def test_extension_configuration_is_stored_but_not_hot_reloaded(self, tmp_path: Path):
        manifest = tmp_path / "capability.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "samuel-extension-capability.v1",
                    "capability_id": "documentation.static_claims",
                    "contract_version": "1.0",
                    "transport": "filesystem-json",
                    "effect": "advisory",
                    "claim_families": ["documentation.inventory.v1"],
                    "permissions": ["repository:read"],
                    "credentials": [],
                }
            ),
            encoding="utf-8",
        )
        handler = self._make_handler(tmp_path)

        result = handler.set_extension_configuration(
            {"enabled": True, "required": False, "manifest_path": str(manifest)}
        )

        assert result["updated"] is True
        assert result["restart_required"] is True
        assert result["extension"]["status"] == "available"
        assert result["extension"]["effective_status"] == "disabled"
        stored = json.loads((tmp_path / "extensions.json").read_text(encoding="utf-8"))
        assert stored["capabilities"]["documentation.static_claims"]["enabled"] is True

    def test_extension_configuration_is_frozen_in_production(self, tmp_path: Path):
        from samuel.core.configuration_mode import ConfigurationAuthority

        authority = ConfigurationAuthority("production", source="test", config_dir=tmp_path)
        handler = DashboardHandler(
            Bus(),
            config=MockConfig({"agent.config_dir": str(tmp_path)}),
            configuration_authority=authority,
        )

        result = handler.set_extension_configuration(
            {"enabled": True, "required": True, "manifest_path": "/tmp/capability.json"}
        )

        assert result["updated"] is False
        assert result["code"] == "configuration_frozen"
        assert not (tmp_path / "extensions.json").exists()

    def test_extension_configuration_rejects_coercion_and_unknown_fields(
        self, tmp_path: Path
    ) -> None:
        handler = self._make_handler(tmp_path)

        coerced = handler.set_extension_configuration(
            {"enabled": "true", "required": False, "manifest_path": None}
        )
        unknown = handler.set_extension_configuration(
            {"enabled": True, "required": False, "manifest_path": None, "secret": "x"}
        )

        assert coerced["updated"] is False
        assert unknown["updated"] is False


# #309: Per-task LLM configuration writes.
class TestSetLLMTaskConfig:
    def _make_handler(self, tmp_path: Path):
        from unittest.mock import MagicMock

        bus = Bus()
        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "agent.config_dir": str(tmp_path),
        }.get(key, default)
        return DashboardHandler(bus, config=config)

    def test_set_llm_task_config_general_path(self, tmp_path):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "claude", "model": "claude-opus"})
        assert res["updated"] is True
        assert res["task"] == "planning"
        assert res["cfg"]["provider"] == "claude"

    def test_set_llm_global_config_round_trips_without_hot_reload(self, tmp_path, monkeypatch):
        import json as _json

        monkeypatch.delenv("SAMUEL_LLM_PROVIDER", raising=False)
        h = self._make_handler(tmp_path)

        result = h.set_llm_global_config(
            {"provider": "deepseek", "fallbacks": ["openrouter", "ollama", "openrouter"]}
        )

        assert result["updated"] is True
        assert result["provider"] == "deepseek"
        assert result["fallbacks"] == ["openrouter", "ollama"]
        assert result["restart_required"] is True
        assert result["environment_override"] is False
        assert result["configuration"]["restart_required"] is True
        data = _json.loads((tmp_path / "llm.json").read_text())
        assert data["default"] == {
            "provider": "deepseek",
            "fallbacks": ["openrouter", "ollama"],
        }
        assert h.get_llm_global_config()["fallbacks"] == ["openrouter", "ollama"]

    def test_global_config_reports_environment_override_as_effective(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAMUEL_LLM_PROVIDER", "ollama")
        handler = self._make_handler(tmp_path)
        handler.set_llm_global_config({"provider": "deepseek", "fallbacks": []})

        global_config = handler.get_llm_global_config()

        assert global_config["provider"] == "deepseek"
        assert global_config["effective_provider"] == "ollama"
        assert global_config["provider_source"] == "environment"

    def test_set_llm_global_config_rejects_unknown_fallback(self, tmp_path):
        result = self._make_handler(tmp_path).set_llm_global_config(
            {"provider": "deepseek", "fallbacks": ["made-up"]}
        )
        assert result["updated"] is False
        assert "unknown fallback" in result["error"]

    def test_legacy_license_data_does_not_change_task_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAMUEL_LICENSE_KEY", "legacy-invalid-value")
        (tmp_path / "license.json").write_text("legacy-invalid-value", encoding="utf-8")
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "claude"})
        assert res["updated"] is True

    def test_set_llm_task_config_unknown_task(self, tmp_path, monkeypatch):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("not_a_task", {"provider": "claude"})
        assert res["updated"] is False
        assert "unknown task" in res["error"]

    def test_set_llm_task_config_invalid_provider(self, tmp_path, monkeypatch):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "fakellm"})
        assert res["updated"] is False
        assert "unknown provider" in res["error"]

    def test_set_llm_task_config_writes_to_disk(self, tmp_path, monkeypatch):
        import json as _json

        h = self._make_handler(tmp_path)
        h.set_llm_task_config("review", {"provider": "deepseek", "model": "deepseek-coder"})
        fp = tmp_path / "llm" / "defaults.json"
        assert fp.exists()
        data = _json.loads(fp.read_text(encoding="utf-8"))
        assert data["tasks"]["review"]["provider"] == "deepseek"
        assert data["tasks"]["review"]["model"] == "deepseek-coder"

    def test_saved_task_provider_is_returned_by_settings_view(self, tmp_path, monkeypatch):
        handler = self._make_handler(tmp_path)

        saved = handler.set_llm_task_config(
            "planning",
            {"provider": "openrouter", "model": "vendor/planner-model"},
        )
        planning = next(
            row for row in handler.get_settings()["llm_config"] if row["task"] == "planning"
        )

        assert saved["updated"] is True
        assert planning["provider"] == "openrouter"
        assert planning["model"] == "vendor/planner-model"

    def test_set_llm_task_config_clears_field_when_value_empty(self, tmp_path, monkeypatch):
        import json as _json

        h = self._make_handler(tmp_path)
        # Set a base_url first
        h.set_llm_task_config("planning", {"provider": "ollama", "base_url": "http://x:11434"})
        # Then clear it via empty string
        h.set_llm_task_config("planning", {"base_url": ""})
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert "base_url" not in data["tasks"]["planning"]
        assert data["tasks"]["planning"]["provider"] == "ollama"

    def test_set_llm_task_config_rejects_unknown_field(self, tmp_path, monkeypatch):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config("planning", {"provider": "claude", "rogue": "x"})
        assert res["updated"] is False
        assert "unknown fields" in res["error"]

    def test_set_llm_task_config_validates_reasoning_reserve(self, tmp_path, monkeypatch):
        h = self._make_handler(tmp_path)

        invalid = h.set_llm_task_config("planning", {"reasoning_reserve": -1})
        valid = h.set_llm_task_config("planning", {"reasoning_reserve": 2048})

        assert invalid["updated"] is False
        assert "non-negative integer" in invalid["error"]
        assert valid["updated"] is True
        saved = json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert saved["tasks"]["planning"]["reasoning_reserve"] == 2048

    def test_set_llm_task_config_validates_cost_advisory_controls(self, tmp_path, monkeypatch):
        h = self._make_handler(tmp_path)

        bad_flag = h.set_llm_task_config("planning", {"cost_advisory_enabled": "yes"})
        bad_margin = h.set_llm_task_config("planning", {"overqualification_margin_ratio": 1.1})
        valid = h.set_llm_task_config(
            "planning",
            {
                "cost_advisory_enabled": False,
                "overqualification_margin_ratio": 0.35,
            },
        )

        assert bad_flag["updated"] is False
        assert bad_margin["updated"] is False
        assert valid["updated"] is True
        saved = json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert saved["tasks"]["planning"]["cost_advisory_enabled"] is False
        assert saved["tasks"]["planning"]["overqualification_margin_ratio"] == 0.35

    def test_set_llm_task_config_rejects_budget_above_model_limit(self, tmp_path, monkeypatch):
        base = self._make_handler(tmp_path)
        h = DashboardHandler(
            base._bus,
            config=base._config,
            model_quality_resolver=lambda *_: {
                "reasoning": {
                    "is_reasoning": True,
                    "source": "openrouter_supported_parameters",
                    "max_completion_tokens": 5000,
                },
                "suitability": {},
            },
        )

        result = h.set_llm_task_config(
            "planning",
            {
                "provider": "openrouter",
                "model": "vendor/reasoner",
                "max_tokens": 4096,
                "reasoning_reserve": 2048,
            },
        )

        assert result["updated"] is False
        assert "exceeds" in result["error"]

    def test_reasoning_feedback_uses_measured_tokens_and_truncation(self):
        routing: list[dict[str, Any]] = [
            {"task": "planning", "provider": "openrouter", "model": "vendor/r"}
        ]
        history: list[dict[str, Any]] = [
            {
                "task": "planning",
                "provider": "openrouter",
                "model": "vendor/r",
                "reasoning_tokens": 800,
                "stop_reason": "stop",
            },
            {
                "task": "planning",
                "provider": "openrouter",
                "model": "vendor/r",
                "reasoning_tokens": 1200,
                "stop_reason": "length",
            },
        ]

        DashboardHandler._add_reasoning_feedback(routing, history)

        feedback = routing[0]["reasoning_feedback"]
        assert feedback["average_reasoning_tokens"] == 1000.0
        assert feedback["max_reasoning_tokens"] == 1200
        assert feedback["truncations"] == 1
        assert "keine automatische" in feedback["note"]

    # #316: Schedule block validation.

    def test_set_llm_task_config_with_valid_schedule(self, tmp_path, monkeypatch):
        """#316-AC: name matches issue-body anchor."""
        import json as _json

        h = self._make_handler(tmp_path)
        sched = {
            "active": True,
            "from": "22:00",
            "to": "06:00",
            "provider": "claude",
            "model": "claude-opus",
        }
        res = h.set_llm_task_config("planning", {"provider": "deepseek", "schedule": sched})
        assert res["updated"] is True
        assert res["cfg"]["schedule"] == sched
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert data["tasks"]["planning"]["schedule"]["from"] == "22:00"

    def test_set_llm_task_config_with_invalid_time_format(self, tmp_path, monkeypatch):
        """#316-AC: name matches issue-body anchor."""
        h = self._make_handler(tmp_path)
        for bad in ("25:00", "22-00", "abc", "12:99"):
            res = h.set_llm_task_config(
                "planning",
                {
                    "schedule": {
                        "active": True,
                        "from": bad,
                        "to": "06:00",
                        "provider": "claude",
                        "model": "claude-opus",
                    }
                },
            )
            assert res["updated"] is False
            assert "schedule.from" in res["error"] or "invalid" in res["error"]

    def test_set_llm_task_config_schedule_clear_when_inactive(self, tmp_path, monkeypatch):
        """#316-AC: active=False removes the schedule field on disk."""
        import json as _json

        h = self._make_handler(tmp_path)
        # First: set an active schedule
        h.set_llm_task_config(
            "planning",
            {
                "schedule": {
                    "active": True,
                    "from": "22:00",
                    "to": "06:00",
                    "provider": "claude",
                    "model": "claude-opus",
                }
            },
        )
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert "schedule" in data["tasks"]["planning"]
        # Then: send active=false -> schedule removed
        h.set_llm_task_config("planning", {"schedule": {"active": False}})
        data = _json.loads((tmp_path / "llm" / "defaults.json").read_text())
        assert "schedule" not in data["tasks"]["planning"]

    def test_set_llm_task_config_schedule_unknown_provider(self, tmp_path, monkeypatch):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config(
            "planning",
            {
                "schedule": {
                    "active": True,
                    "from": "22:00",
                    "to": "06:00",
                    "provider": "fakellm",
                    "model": "x",
                }
            },
        )
        assert res["updated"] is False
        assert "schedule.provider" in res["error"]

    def test_set_llm_task_config_schedule_empty_model(self, tmp_path, monkeypatch):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config(
            "planning",
            {
                "schedule": {
                    "active": True,
                    "from": "22:00",
                    "to": "06:00",
                    "provider": "claude",
                    "model": "",
                }
            },
        )
        assert res["updated"] is False
        assert "schedule.model" in res["error"]

    def test_save_then_get_roundtrip_preserves_system_prompt(
        self,
        tmp_path,
        monkeypatch,
    ):
        """#338-audit: User saves a system_prompt, reloads — value must come
        back from get_settings(). Was missing before because get_llm_routing
        dropped the field."""
        h = self._make_handler(tmp_path)
        save_res = h.set_llm_task_config(
            "review",
            {"provider": "deepseek", "system_prompt": "reviewer.md"},
        )
        assert save_res["updated"] is True

        settings = h.get_settings()
        review = next(r for r in settings.get("llm_config", []) if r["task"] == "review")
        assert review["system_prompt"] == "reviewer.md"

    # #351: per-provider prompt-override map.
    def test_set_llm_task_config_accepts_system_prompt_by_provider(
        self,
        tmp_path,
        monkeypatch,
    ):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config(
            "planning",
            {
                "provider": "deepseek",
                "system_prompt": "planner.md",
                "system_prompt_by_provider": {
                    "deepseek": "planner_local.md",
                    "claude": "planner_kompakt.md",
                },
            },
        )
        assert res["updated"] is True
        assert res["cfg"]["system_prompt_by_provider"] == {
            "deepseek": "planner_local.md",
            "claude": "planner_kompakt.md",
        }

    def test_set_llm_task_config_rejects_unknown_provider_in_map(
        self,
        tmp_path,
        monkeypatch,
    ):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config(
            "planning",
            {
                "system_prompt_by_provider": {"frobnicator": "x.md"},
            },
        )
        assert res["updated"] is False
        assert "system_prompt_by_provider" in res["error"]
        assert "frobnicator" in res["error"]

    def test_set_llm_task_config_rejects_path_traversal_in_map_value(
        self,
        tmp_path,
        monkeypatch,
    ):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config(
            "planning",
            {
                "system_prompt_by_provider": {"deepseek": "../etc/passwd.md"},
            },
        )
        assert res["updated"] is False
        assert "system_prompt_by_provider" in res["error"]

    def test_set_llm_task_config_rejects_non_md_in_map_value(
        self,
        tmp_path,
        monkeypatch,
    ):
        h = self._make_handler(tmp_path)
        res = h.set_llm_task_config(
            "planning",
            {
                "system_prompt_by_provider": {"deepseek": "planner.txt"},
            },
        )
        assert res["updated"] is False
        assert "system_prompt_by_provider" in res["error"]
        assert ".md" in res["error"]

    def test_empty_map_drops_field_from_persisted_config(
        self,
        tmp_path,
        monkeypatch,
    ):
        """UX-pattern: passing {} clears the override (mirrors empty-string
        behaviour for scalar fields)."""
        h = self._make_handler(tmp_path)
        # First save: map is set
        h.set_llm_task_config(
            "planning",
            {
                "provider": "deepseek",
                "system_prompt_by_provider": {"deepseek": "x.md"},
            },
        )
        # Then save: empty map -> field is removed
        res = h.set_llm_task_config(
            "planning",
            {
                "system_prompt_by_provider": {},
            },
        )
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
        h = self._make_handler(
            tester=lambda p, c: {"valid": False, "detail": "unauthorized", "balance": None}
        )
        res = h.test_connection("claude", {"model": "x"})
        assert res["valid"] is False
        assert res["detail"] == "unauthorized"

    def test_test_connection_failure_publishes_diagnostic(self):
        from unittest.mock import MagicMock

        bus = Bus()
        events: list[Any] = []
        bus.subscribe("DiagnosticRaised", events.append)
        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: default
        h = DashboardHandler(
            bus,
            config=config,
            connection_tester=lambda p, c: {
                "valid": False,
                "detail": "unauthorized",
                "balance": None,
            },
        )

        h.test_connection("claude", {"model": "x"})

        assert len(events) == 1
        assert events[0].payload["level"] == "warning"
        assert events[0].payload["category"] == "llm"
        assert "unauthorized" in events[0].payload["reason"]

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
    def _write_metrics(self, data_dir: Path, lines: list[dict]) -> None:
        import json as _json

        log_dir = data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fp = log_dir / "self_mode_metrics.jsonl"
        fp.write_text("\n".join(_json.dumps(r) for r in lines) + "\n", encoding="utf-8")

    def test_get_self_mode_health_empty_when_no_metrics(self, tmp_path):
        h = DashboardHandler(Bus(), config=MockConfig({"agent.data_dir": str(tmp_path)}))
        result = h.get_self_mode_health()
        assert result["total"] == 0
        assert result["success_rate"] is None
        assert result["recent_runs"] == []

    def test_get_self_mode_health_aggregates_correctly(self, tmp_path):
        self._write_metrics(
            tmp_path,
            [
                {
                    "issue": 1,
                    "ts": "2026-05-05T10:00:00Z",
                    "duration_seconds": 60.0,
                    "rounds": 1,
                    "success": True,
                    "reason": "complete",
                    "patches_applied": 5,
                    "rounds_stats": [],
                },
                {
                    "issue": 2,
                    "ts": "2026-05-05T11:00:00Z",
                    "duration_seconds": 120.0,
                    "rounds": 3,
                    "success": False,
                    "reason": "no_progress",
                    "patches_applied": 2,
                    "rounds_stats": [],
                },
                {
                    "issue": 3,
                    "ts": "2026-05-05T12:00:00Z",
                    "duration_seconds": 90.0,
                    "rounds": 2,
                    "success": True,
                    "reason": "complete",
                    "patches_applied": 8,
                    "rounds_stats": [],
                },
            ],
        )
        h = DashboardHandler(Bus(), config=MockConfig({"agent.data_dir": str(tmp_path)}))
        r = h.get_self_mode_health()
        assert r["total"] == 3
        assert r["success_rate"] == 2 / 3 or abs(r["success_rate"] - 2 / 3) < 0.01
        assert r["no_progress_rate"] == 1 / 3 or abs(r["no_progress_rate"] - 1 / 3) < 0.01
        assert r["avg_rounds"] == 2.0
        assert r["avg_duration_s"] == 90.0
        assert len(r["recent_runs"]) == 3
        # neueste zuerst
        assert r["recent_runs"][0]["issue"] == 3

    def test_get_self_mode_health_limits_to_recent(self, tmp_path):
        self._write_metrics(
            tmp_path,
            [
                {
                    "issue": i,
                    "ts": f"t{i}",
                    "duration_seconds": 10.0,
                    "rounds": 1,
                    "success": True,
                    "reason": "complete",
                    "patches_applied": 1,
                    "rounds_stats": [],
                }
                for i in range(60)
            ],
        )
        h = DashboardHandler(Bus(), config=MockConfig({"agent.data_dir": str(tmp_path)}))
        r = h.get_self_mode_health(limit=50)
        assert r["total"] == 50
        # recent_runs hat max 20 (newest first)
        assert len(r["recent_runs"]) == 20
        assert r["recent_runs"][0]["issue"] == 59  # neueste


@pytest.mark.parametrize(
    "status,reasons",
    [
        ("ready", []),
        ("blocked", ["llm_unavailable"]),
        ("unknown", ["not_checked"]),
        ("stale", ["expired"]),
    ],
)
def test_project_readiness_preserves_other_reasons_and_is_passive(monkeypatch, status, reasons):
    import copy

    import samuel.slices.dashboard.handler as module

    snapshot = {
        "operational_readiness": {"status": status, "reasons": reasons},
        "technical_health": {"status": "healthy"},
    }
    original = copy.deepcopy(snapshot)
    monkeypatch.setattr(module, "readiness_snapshot", lambda *a, **kw: copy.deepcopy(snapshot))
    project = {"passed": False, "reason_code": "project_missing"}
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    handler = DashboardHandler(bus, project_status=lambda: dict(project))
    for _ in range(2):
        result = handler._passive_readiness()
        assert result["operational_readiness"]["reasons"] == [*reasons, "project_missing"]
        assert result["operational_readiness"]["status"] == "blocked"
        assert result["technical_health"] == original["technical_health"]
    project["passed"] = True
    result = handler._passive_readiness()
    assert result["operational_readiness"]["status"] == status
    assert result["operational_readiness"]["reasons"] == reasons
    assert snapshot == original
    assert events == []
