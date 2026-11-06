from __future__ import annotations

import json
import multiprocessing
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from samuel.adapters.api.rest import RestAPI
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.bus import Bus, IdempotencyMiddleware, IdempotencyStore
from samuel.core.commands import ImplementCommand, PlanIssueCommand, ScanIssuesCommand
from samuel.core.config import FileConfig
from samuel.core.configuration_mode import ConfigurationAuthority
from samuel.core.configuration_session import ConfigurationConflict, ConfigurationSession
from samuel.core.events import Event
from samuel.llm_configuration import LLMConfigurationArea, LLMRuntime, read_documents
from samuel.slices.dashboard.handler import DashboardHandler


class Area:
    def __init__(self) -> None:
        self.value = {"model": "old"}
        self.active = "old"
        self.fail = False

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.value)

    def validate(self, draft: dict[str, Any]) -> dict[str, Any]:
        if not draft["model"]:
            raise ValueError("missing model")
        return {"model": draft["model"], "benchmark": "underqualified"}

    def prepare(self, draft: dict[str, Any]) -> str:
        return str(draft["model"])

    def persist(self, draft: dict[str, Any]) -> None:
        self.value = deepcopy(draft)
        if self.fail:
            raise OSError("interrupted write")

    def activate(self, prepared: Any) -> None:
        self.active = prepared


@pytest.fixture
def session(tmp_path: Path) -> ConfigurationSession:
    result = ConfigurationSession(SQLiteStateStore(tmp_path / "state").authority)
    result.areas["llm"] = Area()
    return result


def test_draft_apply_shared_admission_and_unrelated_setup_freeze(
    session: ConfigurationSession, tmp_path: Path
) -> None:
    authority = ConfigurationAuthority("production", source="test", config_dir=tmp_path)
    authority.session = session
    state = session.enter("llm", "admin")
    assert authority.writable is False
    assert authority.blocked_result() is not None
    with pytest.raises(ConfigurationConflict), session.admission():
        pytest.fail("work admitted during editing")
    state = session.stage("admin", state["version"], {"model": "new/free-id"})
    assert session.areas["llm"].snapshot()["model"] == "old"
    state = session.apply("admin", state["version"])
    assert state["phase"] == "idle" and state["revision"] == 1
    assert session.areas["llm"].snapshot()["model"] == "new/free-id"
    with session.admission():
        pass


def test_racing_process_admission_cannot_enter_edit_mode(
    session: ConfigurationSession, tmp_path: Path
) -> None:
    other = ConfigurationSession(SQLiteStateStore(tmp_path / "state").authority)
    other.areas["llm"] = Area()
    with other.admission("watch"), pytest.raises(ConfigurationConflict, match="Ausführung"):
        session.enter("llm", "admin")
    session.enter("llm", "admin")
    with pytest.raises(ConfigurationConflict), other.admission("self"):
        pass


def test_atomic_enter_loses_to_work_started_during_snapshot(session: ConfigurationSession) -> None:
    area = session.areas["llm"]
    entered, release = threading.Event(), threading.Event()

    def worker() -> None:
        with session.admission():
            entered.set()
            release.wait(5)

    original = area.snapshot

    def snapshot() -> dict[str, Any]:
        thread.start()
        assert entered.wait(5)
        return original()

    thread = threading.Thread(target=worker)
    area.snapshot = snapshot  # type: ignore[method-assign]
    try:
        with pytest.raises(ConfigurationConflict):
            session.enter("llm", "admin")
        assert session.state()["phase"] == "idle"
    finally:
        release.set()
        thread.join(5)


def test_owner_and_version_reject_stale_tabs(session: ConfigurationSession) -> None:
    state = session.enter("llm", "admin")
    with pytest.raises(ConfigurationConflict, match="anderen"):
        session.stage("other", state["version"], {"model": "x"})
    session.stage("admin", state["version"], {"model": "x"})
    with pytest.raises(ConfigurationConflict, match="neu laden"):
        session.apply("admin", state["version"])


def test_failed_probe_requires_conscious_override_and_check_cannot_erase_it(
    session: ConfigurationSession,
) -> None:
    state = session.enter("llm", "admin")
    state = session.probe("admin", state["version"], "planning", lambda draft: {"valid": False})
    state = session.stage("admin", state["version"], state["draft"])
    with pytest.raises(ValueError, match="bestätigen"):
        session.apply("admin", state["version"])
    events: list[dict] = []
    session.audit = events.append
    session.apply("admin", state["version"], override_failed_probe=True)
    assert any(row["action"] == "apply_override" for row in events)
    assert all("draft" not in row and "model" not in row for row in events)


def test_failed_apply_stays_frozen_and_can_restore_after_restart(
    session: ConfigurationSession, tmp_path: Path
) -> None:
    area = session.areas["llm"]
    state = session.enter("llm", "admin")
    state = session.stage("admin", state["version"], {"model": "new"})
    area.fail = True  # type: ignore[attr-defined]
    with pytest.raises(OSError):
        session.apply("admin", state["version"])
    restarted = ConfigurationSession(SQLiteStateStore(tmp_path / "state").authority)
    restarted.areas["llm"] = area
    assert restarted.state()["phase"] == "failed"
    with pytest.raises(ConfigurationConflict), restarted.admission():
        pass
    area.fail = False  # type: ignore[attr-defined]
    state = restarted.cancel("replacement-admin", restarted.state()["version"], recovery=True)
    assert state["phase"] == "idle"
    assert area.snapshot() == {"model": "old"}


@pytest.mark.parametrize("phase", ["editing", "probing", "applying", "restoring", "failed"])
def test_restart_never_expires_a_mode(
    session: ConfigurationSession, tmp_path: Path, phase: str
) -> None:
    state = session.enter("llm", "admin")
    state["phase"] = phase
    session._save(state)
    other = ConfigurationSession(SQLiteStateStore(tmp_path / "state").authority)
    with pytest.raises(ConfigurationConflict), other.admission():
        pass


@pytest.mark.parametrize(
    "event", ["PlanPosted", "ACManualPending", "ReviewBlocked", "MergeOutcomeUnknown"]
)
def test_human_wait_is_busy_after_synchronous_dispatch_returns(
    session: ConfigurationSession, event: str
) -> None:
    bus = Bus()
    bus.configuration_session = session
    bus.register_command(
        "PlanIssue", lambda cmd: bus.publish(Event(name=event, payload={"issue": 7}))
    )
    bus.send(PlanIssueCommand(issue_number=7))
    with pytest.raises(ConfigurationConflict, match="Issue #7"):
        session.enter("llm", "admin")


def test_review_completed_waiting_only_for_human_merge_is_idle(
    session: ConfigurationSession,
) -> None:
    bus = Bus()
    bus.configuration_session = session

    def run(cmd: Any) -> None:
        bus.publish(Event(name="PRCreated", payload={"issue": 7, "review_required": True}))
        with pytest.raises(ConfigurationConflict):
            session.enter("llm", "admin")
        bus.publish(Event(name="ReviewCompleted", payload={"issue": 7}))

    bus.register_command("Implement", run)
    bus.send(ImplementCommand(issue_number=7))
    assert session.enter("llm", "admin")["phase"] == "editing"


def test_busy_does_not_consume_watch_or_idempotency_key(session: ConfigurationSession) -> None:
    bus = Bus()
    bus.configuration_session = session
    store = IdempotencyStore()
    bus.add_middleware(IdempotencyMiddleware(store))
    handler = MagicMock(return_value={"dispatched": 0})
    bus.register_command("ScanIssues", handler)
    state = session.enter("llm", "admin")
    command = ScanIssuesCommand(idempotency_key="delivery")
    assert RestAPI(bus).handle_request("POST", "/api/v1/scan")["status"] == 409
    with pytest.raises(ConfigurationConflict):
        bus.send(command)
    assert not store.has_key("delivery")
    handler.assert_not_called()
    session.cancel("admin", state["version"])
    bus.send(command)
    handler.assert_called_once()


def _crash_dispatch(path: str) -> None:
    session = ConfigurationSession(SQLiteStateStore(Path(path)).authority)
    with session.admission("watch"):
        os._exit(0)


def test_crashed_dispatch_requires_explicit_reconciliation(
    session: ConfigurationSession, tmp_path: Path
) -> None:
    child = multiprocessing.get_context("fork").Process(
        target=_crash_dispatch, args=(str(tmp_path / "state"),)
    )
    child.start()
    child.join(5)
    assert child.exitcode == 0
    with pytest.raises(ConfigurationConflict):
        session.enter("llm", "admin")
    session.reconcile_dispatch("admin")
    assert session.enter("llm", "admin")["phase"] == "editing"


def test_recovery_never_interrupts_a_live_action(session: ConfigurationSession) -> None:
    state = session.enter("llm", "admin")
    with session.store.configuration_lock(), pytest.raises(ConfigurationConflict, match="läuft"):
        session.cancel("replacement-admin", state["version"], recovery=True)


def test_runtime_refreshes_new_revision_before_work(
    session: ConfigurationSession, tmp_path: Path
) -> None:
    other = ConfigurationSession(SQLiteStateStore(tmp_path / "state").authority)
    revisions: list[int] = []
    other.refresh = revisions.append
    state = session.enter("llm", "admin")
    session.apply("admin", state["version"])
    with other.admission():
        assert revisions == [1]


def make_llm_area(
    tmp_path: Path,
) -> tuple[ConfigurationSession, LLMConfigurationArea, DashboardHandler]:
    root = tmp_path / "config"
    (root / "llm").mkdir(parents=True)
    (root / "llm.json").write_text(
        json.dumps(
            {"default": {"provider": "manual", "fallbacks": []}, "manual": {"model": "offline"}}
        )
    )
    (root / "llm/defaults.json").write_text(
        json.dumps(
            {
                "default": {"max_tokens": 100, "temperature": 0.2},
                "workflow_budget": {"token_limit": 5000},
                "tasks": {
                    "planning": {
                        "provider": "manual",
                        "model": "offline",
                        "system_prompt": "planner.md",
                    }
                },
            }
        )
    )
    config = FileConfig(root)
    config.set_override("agent.config_dir", str(root))
    bus = Bus()
    store = SQLiteStateStore(tmp_path / "runtime")
    bus.authority_state_store = store.authority
    bus.quality_registry = store.quality_metrics
    session = ConfigurationSession(store.authority)
    bus.configuration_session = session
    runtime = LLMRuntime(None, config, bus)
    bus.llm_runtime = runtime
    authority = ConfigurationAuthority("production", source="test", config_dir=root)
    authority.session = session
    dashboard = DashboardHandler(bus, config=config, configuration_authority=authority)
    area = LLMConfigurationArea(root, runtime, dashboard)
    session.areas["llm"] = area
    return session, area, dashboard


def test_full_llm_change_preserves_budget_and_other_settings(tmp_path: Path) -> None:
    session, area, dashboard = make_llm_area(tmp_path)
    before = area.snapshot()
    state = session.enter("llm", "admin")
    result = dashboard.configuration_action(
        {
            "action": "stage",
            "version": state["version"],
            "task": "planning",
            "config": {
                "model": "free-model-not-in-a-catalog",
                "temperature": 0.4,
                "schedule": {
                    "active": True,
                    "from": "22:00",
                    "to": "06:00",
                    "provider": "manual",
                    "model": "night",
                },
            },
        },
        "admin",
    )
    assert result["updated"], result
    state = result["session"]
    assert len(state["preview"]["routes"]) == 2
    assert dashboard.set_feature_flag("eval", True)["code"] == "configuration_frozen"
    session.apply("admin", state["version"])
    assert (
        read_documents(area.root)["llm/defaults.json"]["workflow_budget"]
        == before["llm/defaults.json"]["workflow_budget"]
    )
    assert area.runtime.inner is not None
    assert dashboard.configuration_status()["restart_required"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("timeout", 0),
        ("temperature", float("nan")),
        ("base_url", "https://secret:token@example.org"),
        ("max_tokens", -1),
    ],
)
def test_invalid_local_values_block_before_files_change(
    tmp_path: Path, field: str, value: Any
) -> None:
    session, area, dashboard = make_llm_area(tmp_path)
    before = area.snapshot()
    state = session.enter("llm", "admin")
    result = dashboard.configuration_action(
        {
            "action": "stage",
            "version": state["version"],
            "task": "planning",
            "config": {field: value},
        },
        "admin",
    )
    assert result["updated"] is False
    assert area.snapshot() == before


def test_corrupt_second_file_restores_from_durable_before_image(tmp_path: Path) -> None:
    session, area, _ = make_llm_area(tmp_path)
    state = session.enter("llm", "admin")
    original = area.snapshot()
    state["phase"] = "applying"
    session._save(state)
    (area.root / "llm/defaults.json").write_text('{"tasks":')
    restarted = ConfigurationSession(SQLiteStateStore(tmp_path / "runtime").authority)
    restarted.areas["llm"] = area
    restarted.cancel("admin", restarted.state()["version"], recovery=True)
    assert area.snapshot() == original


def test_budget_and_secret_configuration_cannot_be_changed_through_draft(tmp_path: Path) -> None:
    session, area, _ = make_llm_area(tmp_path)
    state = session.enter("llm", "admin")
    draft = deepcopy(state["draft"])
    draft["llm/defaults.json"]["workflow_budget"]["token_limit"] = 999999
    with pytest.raises(ValueError, match="budgets"):
        session.stage("admin", state["version"], draft)
    draft = deepcopy(state["draft"])
    draft["llm.json"]["manual"]["model"] = "unregistered-global-field"
    with pytest.raises(ValueError, match="Only default"):
        session.stage("admin", state["version"], draft)


def test_busy_webhook_returns_retryable_failure_before_consuming_delivery(
    session: ConfigurationSession,
) -> None:
    from samuel.adapters.api.webhooks import WebhookIngressAdapter

    bus = Bus()
    bus.configuration_session = session
    adapter = WebhookIngressAdapter(bus)
    session.enter("llm", "admin")
    result = adapter.handle_webhook("issue-created", {"issue": {"number": 7}})
    assert result["status"] == 503 and result["retryable"] is True
    assert session.state()["issues"] == {}


def test_missing_configuration_runtime_is_reported(tmp_path: Path) -> None:
    handler = DashboardHandler(Bus(), config=FileConfig(tmp_path))
    assert handler.configuration_action({"action": "enter"}, "admin")["updated"] is False


def test_provider_fallback_prompt_preview_and_underqualification_are_advisory(
    tmp_path: Path,
) -> None:
    session, area, dashboard = make_llm_area(tmp_path)
    dashboard._model_quality_resolver = lambda model, task, threshold, margin: {
        "suitability": {
            "status": "below_threshold",
            "score": 1,
            "threshold": threshold,
            "available": True,
        }
    }
    state = session.enter("llm", "admin")
    result = dashboard.configuration_action(
        {
            "action": "stage",
            "version": state["version"],
            "config": {"provider": "manual", "fallbacks": ["ollama"]},
        },
        "admin",
    )
    assert result["updated"], result
    rows = result["session"]["preview"]["routes"]
    assert rows[1]["provider"] == "ollama" and rows[1]["model"] == "llama3"
    assert rows[1]["prompt_source"]["source"] == "package"
    assert rows[0]["advisory"]["suitability"]["threshold"] == 50.0
    assert session.apply("admin", result["session"]["version"])["phase"] == "idle"


def test_probe_exception_is_failed_evidence_and_successful_retest_replaces_it(
    session: ConfigurationSession,
) -> None:
    state = session.enter("llm", "admin")

    def fail(draft: dict) -> dict:
        raise ConnectionError("private provider detail")

    state = session.probe("admin", state["version"], "planning", fail)
    assert state["phase"] == "editing" and state["probes"][0]["valid"] is False
    assert "private" not in json.dumps(state["probes"])
    state = session.probe("admin", state["version"], "planning", lambda draft: {"valid": True})
    assert len(state["probes"]) == 1
    assert session.apply("admin", state["version"])["phase"] == "idle"


def test_failed_restore_keeps_admission_blocked(session: ConfigurationSession) -> None:
    state = session.enter("llm", "admin")
    session.areas["llm"].fail = True  # type: ignore[attr-defined]
    session.areas["llm"].value = {"model": "partial-write"}  # type: ignore[attr-defined]
    with pytest.raises(OSError):
        session.cancel("admin", state["version"])
    assert session.state()["phase"] == "failed"
    with pytest.raises(ConfigurationConflict), session.admission():
        pass


def test_benchmark_freshness_does_not_prevent_apply(tmp_path: Path) -> None:
    session, area, dashboard = make_llm_area(tmp_path)
    seconds = iter(range(100))
    dashboard._model_cache_status_resolver = lambda: {
        "age_seconds": next(seconds),
        "source": "openrouter",
    }
    state = session.enter("llm", "admin")
    assert session.apply("admin", state["version"])["phase"] == "idle"


def test_apply_preserves_existing_budget_admissions(tmp_path: Path) -> None:
    from samuel.core.state import LLMBudgetAttemptRecord, WorkflowBudgetAdmissionRecord

    session, _, _ = make_llm_area(tmp_path)
    record = WorkflowBudgetAdmissionRecord(
        admission_key="existing",
        repository="repo",
        issue_number=7,
        invocation_digest="i",
        source_digest="s",
        policy_digest="p",
        correlation_id="c",
        token_limit=5000,
    )
    session.store.put_budget_admission(record)
    session.store.reserve_budget_attempt(
        LLMBudgetAttemptRecord(
            attempt_key="call",
            admission_key="existing",
            logical_call_id="logical",
            provider="manual",
            model="offline",
            task="planning",
            input_upper_bound=20,
            output_upper_bound=100,
            reserved_tokens=120,
        )
    )
    with pytest.raises(ConfigurationConflict, match="Budgetversuch"):
        session.enter("llm", "admin")
    session.store.settle_budget_attempt(
        "call",
        status="unknown",
        actual_input_tokens=None,
        actual_output_tokens=None,
        outcome_code="usage_unreported",
    )
    # Unknown usage is already settled conservatively, not an in-flight call.
    before_attempt = session.store.get_budget_attempt("call")
    state = session.enter("llm", "admin")
    session.apply("admin", state["version"])
    assert session.store.get_budget_admission("existing") == record

    assert session.store.get_budget_attempt("call") == before_attempt


def test_compose_keeps_general_config_readonly_with_exact_llm_file_exceptions() -> None:
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text()
    assert "${SAMUEL_CONFIG_DIR:-./config}:/app/config:ro" in compose
    assert "${SAMUEL_CONFIG_DIR:-./config}:/app/config:rw" not in compose
    assert "${SAMUEL_CONFIG_DIR:-./config}/llm.json:/app/config/llm.json:rw" in compose
    assert (
        "${SAMUEL_CONFIG_DIR:-./config}/llm/defaults.json:/app/config/llm/defaults.json:rw"
        in compose
    )
    assert "/app/.env" not in compose


def test_cancel_unchanged_files_needs_no_write_permission(session: ConfigurationSession) -> None:
    state = session.enter("llm", "admin")
    session.areas["llm"].fail = True  # type: ignore[attr-defined]
    assert session.cancel("admin", state["version"])["phase"] == "idle"
    assert session.areas["llm"].snapshot() == {"model": "old"}
