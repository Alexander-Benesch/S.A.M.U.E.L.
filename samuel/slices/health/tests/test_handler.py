from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from samuel.core.bus import Bus
from samuel.core.commands import HealthCheckCommand
from samuel.core.events import Event
from samuel.core.ports import (
    IConfig,
    ILLMProvider,
    IRunProjectionStore,
    IStateDiagnostics,
    IVersionControl,
)
from samuel.core.state import RestoreOperationRecord, RunProjectionRecord, StateStoreStatus
from samuel.core.types import PR, Comment, Issue, LLMResponse
from samuel.slices.health.handler import HealthHandler


class MockSCM(IVersionControl):
    def __init__(self) -> None:
        self.posted: list[tuple[int, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="T", body="b", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted.append((number, body))
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
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


class MockLLM(ILLMProvider):
    def __init__(self, text: str = "response") -> None:
        self._text = text

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class MockUnreadyLLM(MockLLM):
    readiness_status = {
        "passed": False,
        "status": "configuration_missing",
        "failed_routes": ["planning"],
        "routes": [
            {
                "task": "planning",
                "provider": "openrouter",
                "passed": False,
                "candidates": [
                    {
                        "provider": "openrouter",
                        "credential": "missing",
                        "required_env": "OPENROUTER_API_KEY",
                        "guidance": (
                            "OPENROUTER_API_KEY im Samuel-Prozess setzen und Health wiederholen."
                        ),
                    }
                ],
            }
        ],
        "live_probe": "not_performed",
    }


class MockDynamicReadinessLLM(MockLLM):
    readiness_status = {"passed": True, "status": "stale-static-value"}

    def __init__(self) -> None:
        super().__init__()
        self.current = {"passed": True, "status": "fresh"}

    def readiness_status_resolver(self) -> dict[str, Any]:
        return dict(self.current)


class MockConfig(IConfig):
    def get(self, key: str, default: Any = None) -> Any:
        return default

    def feature_flag(self, name: str) -> bool:
        return False


class MockState(IStateDiagnostics):
    def __init__(self, *, reconcile_required: bool = False) -> None:
        self._reconcile_required = reconcile_required

    def status(self) -> StateStoreStatus:
        return StateStoreStatus(
            healthy=True,
            path=Path("/var/lib/samuel/samuel-state.sqlite3"),
            schema_version=1,
            supported_schema_version=1,
            journal_mode="wal",
            auto_vacuum="incremental",
            foreign_keys=True,
            filesystem_type="ext4",
            filesystem_mount=Path("/var/lib/samuel"),
            tables=("schema_migrations",),
            authority_epoch=8,
            authority_instance="instance-health-test",
            witness_epoch=9 if self._reconcile_required else 8,
            reconcile_required=self._reconcile_required,
            reconcile_reason=(
                "state_authority_witness_ahead" if self._reconcile_required else None
            ),
        )

    def dump(self) -> dict[str, Any]:
        return {"payloads_included": False}

    def backup(self, destination: Path) -> Path:
        return destination

    def restore(
        self,
        source: Path,
        *,
        audit_epoch: int = 0,
        supersede_operation_id: str | None = None,
        reason: str | None = None,
    ) -> RestoreOperationRecord:
        raise NotImplementedError

    def list_restore_operations(self) -> list[RestoreOperationRecord]:
        return []


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


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


class TestHealthHandler:
    def test_active_check_persists_passive_layers_without_qualification_claim(
        self,
    ) -> None:
        state = MockState()
        projections = MemoryProjectionStore()
        handler = HealthHandler(
            Bus(),
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=state,
            projection_store=projections,
        )

        result = handler.handle(HealthCheckCommand())

        assert result["technical_health"]["status"] == "passed"
        assert result["operational_readiness"]["status"] == "unknown"
        assert result["qualification"]["status"] == "not_checked"
        technical = projections.get_projection("health-readiness:technical_health")
        readiness = projections.get_projection("health-readiness:operational_readiness")
        assert technical is not None and technical.status == "passed"
        assert readiness is not None and readiness.status == "unknown"

    def test_self_check_provider_probe_makes_readiness_ready(self) -> None:
        projections = MemoryProjectionStore()
        handler = HealthHandler(
            Bus(),
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=MockState(),
            projection_store=projections,
        )

        result = handler.handle(
            HealthCheckCommand(
                payload={
                    "provider_probe": {
                        "schema": "samuel-provider-probe.v1",
                        "performed": True,
                        "routes": [{"task": "planning", "provider": "openrouter", "passed": True}],
                    }
                }
            )
        )

        assert result["healthy"] is True
        assert result["checks"]["llm"]["live_probe"] == "performed"
        assert result["checks"]["llm"]["probed_routes"] == ["planning"]
        assert result["operational_readiness"]["status"] == "ready"
        readiness = projections.get_projection("health-readiness:operational_readiness")
        assert readiness is not None and readiness.status == "ready"

    def test_failed_self_check_provider_probe_blocks_without_provider_detail(self) -> None:
        handler = HealthHandler(
            Bus(), scm=MockSCM(), llm=MockLLM(), config=MockConfig(), state=MockState()
        )

        result = handler.handle(
            HealthCheckCommand(
                payload={
                    "provider_probe": {
                        "schema": "samuel-provider-probe.v1",
                        "performed": True,
                        "routes": [
                            {
                                "task": "implementation",
                                "provider": "openrouter",
                                "passed": False,
                                "detail": "private token-like provider response",
                            }
                        ],
                    }
                }
            )
        )

        assert result["healthy"] is False
        assert result["checks"]["llm"]["status"] == "live_probe_failed"
        assert result["checks"]["llm"]["failed_live_probe_routes"] == ["implementation"]
        assert result["operational_readiness"]["status"] == "blocked"
        assert "private token-like provider response" not in str(result)

    def test_passive_health_does_not_erase_current_self_check_readiness(self) -> None:
        projections = MemoryProjectionStore()
        handler = HealthHandler(
            Bus(),
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=MockState(),
            projection_store=projections,
        )
        handler.handle(
            HealthCheckCommand(
                payload={
                    "provider_probe": {
                        "schema": "samuel-provider-probe.v1",
                        "performed": True,
                        "routes": [{"task": "planning", "passed": True}],
                    }
                }
            )
        )

        passive_result = handler.handle(HealthCheckCommand())

        assert passive_result["operational_readiness"]["status"] == "unknown"
        readiness = projections.get_projection("health-readiness:operational_readiness")
        assert readiness is not None and readiness.status == "ready"

    def test_resume_status_is_visible_without_becoming_a_separate_health_authority(
        self,
    ) -> None:
        bus = Bus()
        handler = HealthHandler(
            bus,
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=MockState(),
            resume_status=lambda: {
                "enabled": True,
                "pending": 2,
                "blocked": 1,
                "last_outcome": {"reason": "resume_lease_live"},
            },
        )

        result = handler.handle(HealthCheckCommand())

        assert result["critical"] is True
        assert result["checks"]["authority"] == {
            "passed": True,
            "epoch": 8,
            "witness_epoch": 8,
            "reconcile_required": False,
            "reconcile_reason": None,
            "active_restore_operation": None,
            "restore_scan_status": None,
            "restore_sentinel_present": False,
            "retention_emergency_stop": True,
            "retention_category_states": [],
            "retention_last_execution": None,
            "retention_future_enforcement_blocked": True,
            "resume_enabled": True,
            "resume_pending": 2,
            "resume_blocked": 1,
            "resume_last_outcome": {"reason": "resume_lease_live"},
        }

    def test_all_healthy(self) -> None:
        bus = Bus()
        handler = HealthHandler(
            bus,
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=MockState(),
        )
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is True
        assert result["critical"] is True
        assert result["checks"]["python"]["passed"] is True
        assert result["checks"]["git"]["passed"] is True

    def test_execution_provider_status_is_bounded_and_visible(self) -> None:
        handler = HealthHandler(
            Bus(),
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=MockState(),
            execution_provider_status={
                "passed": True,
                "configured": True,
                "enabled": False,
                "required_qualified": False,
                "status": "disabled",
            },
        )

        result = handler.handle(HealthCheckCommand())

        assert result["checks"]["execution_provider"] == {
            "passed": True,
            "configured": True,
            "enabled": False,
            "required_qualified": False,
            "status": "disabled",
        }
        assert result["checks"]["git"]["status"] == "ready"
        assert result["checks"]["scm"]["passed"] is True
        assert result["checks"]["llm"]["passed"] is True
        assert result["checks"]["config"]["passed"] is True
        assert result["checks"]["authority"]["passed"] is True

    def test_missing_git_is_unhealthy_with_actionable_secret_free_guidance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samuel.slices.health.handler.shutil.which", lambda _name: None)
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(
            bus,
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=MockState(),
        )

        result = handler.handle(HealthCheckCommand())

        assert result["healthy"] is False
        assert result["critical"] is True
        assert result["checks"]["git"] == {
            "passed": False,
            "status": "executable_missing",
            "required_executable": "git",
            "guidance": (
                "Git in der S.A.M.U.E.L.-Runtime installieren und den Health-Check wiederholen."
            ),
        }
        assert not any(e.name == "StartupBlocked" for e in events)

    def test_reconcile_is_critical_and_visible_to_health_consumers(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(
            bus,
            scm=MockSCM(),
            llm=MockLLM(),
            config=MockConfig(),
            state=MockState(reconcile_required=True),
        )

        result = handler.handle(HealthCheckCommand())

        assert result["healthy"] is False
        assert result["critical"] is False
        assert result["checks"]["state"]["authority"]["reconcile_required"] is True
        assert result["checks"]["authority"] == {
            "passed": False,
            "epoch": 8,
            "witness_epoch": 9,
            "reconcile_required": True,
            "reconcile_reason": "state_authority_witness_ahead",
            "active_restore_operation": None,
            "restore_scan_status": None,
            "restore_sentinel_present": False,
            "retention_emergency_stop": True,
            "retention_category_states": [],
            "retention_last_execution": None,
            "retention_future_enforcement_blocked": True,
            "resume_enabled": False,
        }
        assert any(e.name == "StartupBlocked" for e in events)

    def test_missing_scm(self) -> None:
        bus = Bus()
        handler = HealthHandler(
            bus, scm=None, llm=MockLLM(), config=MockConfig(), state=MockState()
        )
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is False
        assert result["critical"] is True
        assert result["checks"]["scm"]["passed"] is False

    def test_missing_config_triggers_startup_blocked(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(bus, scm=MockSCM(), llm=MockLLM(), config=None, state=MockState())
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is False
        assert result["critical"] is False
        assert any(e.name == "StartupBlocked" for e in events)

    def test_missing_llm_not_critical(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(
            bus, scm=MockSCM(), llm=None, config=MockConfig(), state=MockState()
        )
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["healthy"] is False
        assert result["critical"] is True
        assert not any(e.name == "StartupBlocked" for e in events)

    def test_effective_llm_route_without_credential_is_unhealthy_but_secret_free(self) -> None:
        bus = Bus()
        handler = HealthHandler(
            bus,
            scm=MockSCM(),
            llm=MockUnreadyLLM(),
            config=MockConfig(),
            state=MockState(),
        )

        result = handler.handle(HealthCheckCommand())

        assert result["healthy"] is False
        assert result["critical"] is True
        assert result["checks"]["llm"]["failed_routes"] == ["planning"]
        assert "OPENROUTER_API_KEY" in str(result["checks"]["llm"])
        assert "secret-value" not in str(result["checks"]["llm"])

    def test_each_health_check_uses_current_readiness_evidence(self) -> None:
        llm = MockDynamicReadinessLLM()
        handler = HealthHandler(
            Bus(),
            scm=MockSCM(),
            llm=llm,
            config=MockConfig(),
            state=MockState(),
        )

        first = handler.handle(HealthCheckCommand())
        llm.current = {
            "passed": False,
            "status": "model_unavailable",
            "failed_routes": ["review"],
        }
        second = handler.handle(HealthCheckCommand())

        assert first["checks"]["llm"] == {"passed": True, "status": "fresh"}
        assert second["checks"]["llm"] == {
            "passed": False,
            "status": "model_unavailable",
            "failed_routes": ["review"],
        }
        assert second["healthy"] is False

    def test_readiness_resolver_failure_is_secret_free_and_unhealthy(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        llm = MockLLM()

        def fail() -> dict[str, Any]:
            raise RuntimeError("private-token-value")

        llm.readiness_status_resolver = fail  # type: ignore[attr-defined]
        handler = HealthHandler(
            Bus(),
            scm=MockSCM(),
            llm=llm,
            config=MockConfig(),
            state=MockState(),
        )

        result = handler.handle(HealthCheckCommand())

        assert result["checks"]["llm"] == {
            "passed": False,
            "status": "readiness_evaluation_failed",
            "guidance": "LLM-Konfiguration und Modellkatalog prüfen und Health wiederholen.",
            "live_probe": "not_performed",
        }
        assert "private-token-value" not in str(result)
        assert "private-token-value" not in caplog.text

    def test_correlation_id_flows(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(bus, scm=MockSCM(), llm=MockLLM(), config=None, state=MockState())
        cmd = HealthCheckCommand(correlation_id="health-corr-1")

        handler.handle(cmd)

        for e in events:
            assert e.correlation_id == "health-corr-1"

    def test_scm_reachable(self) -> None:
        bus = Bus()
        handler = HealthHandler(
            bus, scm=MockSCM(), llm=MockLLM(), config=MockConfig(), state=MockState()
        )
        cmd = HealthCheckCommand()

        result = handler.handle(cmd)

        assert result["checks"]["scm"]["reachable"] is True

    def test_missing_state_is_critical(self) -> None:
        bus = Bus()
        events = _collect_events(bus)
        handler = HealthHandler(bus, scm=MockSCM(), llm=MockLLM(), config=MockConfig())

        result = handler.handle(HealthCheckCommand())

        assert result["checks"]["state"]["passed"] is False
        assert result["critical"] is False
        assert any(e.name == "StartupBlocked" for e in events)
