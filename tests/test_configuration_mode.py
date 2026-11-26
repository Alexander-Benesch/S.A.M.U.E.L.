from __future__ import annotations

import json
import multiprocessing
import threading
from pathlib import Path
from typing import Any

import pytest

from samuel.adapters.api.rest import RestAPI
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.bus import Bus
from samuel.core.config import FileConfig
from samuel.core.configuration_mode import (
    CONFIGURATION_FROZEN,
    ConfigurationAuthority,
    resolve_configuration_mode,
)
from samuel.core.configuration_session import ConfigurationConflict, ConfigurationSession
from samuel.slices.dashboard.handler import DashboardHandler
from samuel.slices.setup.handler import SetupHandler


def _setup_handler(tmp_path: Path) -> tuple[DashboardHandler, ConfigurationSession]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "llm.json").write_text('{"default": {}}')
    (config_dir / "agent.json").write_text(json.dumps({"config_dir": str(config_dir)}))
    authority = ConfigurationAuthority("setup", source="test", config_dir=config_dir)
    session = ConfigurationSession(SQLiteStateStore(tmp_path / "state").authority)
    authority.session = session
    return DashboardHandler(
        Bus(), config=FileConfig(config_dir), configuration_authority=authority
    ), session


def _try_admission(data_dir: str, result: Any) -> None:
    session = ConfigurationSession(SQLiteStateStore(Path(data_dir)).authority)
    try:
        with session.admission():
            result.put("admitted")
    except ConfigurationConflict:
        result.put("blocked")


@pytest.mark.parametrize(
    "method,args",
    [
        ("set_feature_flag", ("eval", True)),
        ("set_risk_class", ("high_risk",)),
        ("set_attribution", (True, "full")),
        ("set_extension_configuration", ({"enabled": True},)),
        ("set_llm_global_config", ({"provider": "manual"},)),
        ("set_llm_task_config", ("planning", {"provider": "manual", "model": "test"})),
    ],
)
def test_setup_writes_reject_active_work_before_any_file_change(
    tmp_path: Path, method: str, args: tuple[Any, ...]
) -> None:
    handler, session = _setup_handler(tmp_path)
    before = {p: p.read_bytes() for p in (tmp_path / "config").rglob("*") if p.is_file()}
    with session.admission("planning"):
        result = getattr(handler, method)(*args)
    assert result["updated"] is False
    assert result["code"] == CONFIGURATION_FROZEN
    assert {p: p.read_bytes() for p in (tmp_path / "config").rglob("*") if p.is_file()} == before


def test_setup_writes_hold_the_shared_fence_until_persistence_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, session = _setup_handler(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = handler._persist_json_key
    results: list[dict[str, Any]] = []

    def persist(filename: str, key_path: str, value: Any) -> tuple[bool, str]:
        entered.set()
        assert release.wait(15)
        return original(filename, key_path, value)

    monkeypatch.setattr(handler, "_persist_json_key", persist)
    thread = threading.Thread(target=lambda: results.append(handler.set_feature_flag("eval", True)))
    thread.start()
    try:
        assert entered.wait(5)
        # An independently opened store/process must observe the same OS fence.
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        child = context.Process(target=_try_admission, args=(str(tmp_path / "state"), queue))
        child.start()
        child.join(10)
        if child.is_alive():
            child.kill()
            child.join(5)
        assert child.exitcode == 0
        assert queue.get(timeout=2) == "blocked"
        queue.close()
        other = ConfigurationSession(SQLiteStateStore(tmp_path / "state").authority)
        with pytest.raises(ConfigurationConflict), other.configuration_write():
            pytest.fail("second writer entered")
    finally:
        release.set()
        thread.join(5)
    assert results[0]["updated"] is True and results[0]["restart_required"] is True
    assert json.loads((tmp_path / "config/features.json").read_text())["eval"] is True
    with session.admission():
        pass


def test_setup_write_failure_releases_fence_without_granting_nested_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, session = _setup_handler(tmp_path)

    def persist(filename: str, key_path: str, value: Any) -> tuple[bool, str]:
        with pytest.raises(ConfigurationConflict), session.admission("nested workflow"):
            pytest.fail("configuration writer acquired workflow authority")
        return False, "disk full"

    monkeypatch.setattr(handler, "_persist_json_key", persist)
    result = handler.set_feature_flag("eval", True)
    assert result["updated"] is False and result["error"] == "disk full"
    assert not (tmp_path / "config/features.json").exists()
    with session.admission():
        pass


def test_first_setup_does_not_probe_or_persist_during_active_work(tmp_path: Path) -> None:
    handler, session = _setup_handler(tmp_path)
    setup = SetupHandler(
        Bus(),
        project_root=tmp_path,
        configuration_authority=handler._configuration_authority,
    )
    before = (tmp_path / "config/llm.json").read_bytes()
    with session.admission():
        result = setup.configure_dashboard({"scm_token": "must-not-be-persisted"})
    assert result["configured"] is False and result["code"] == CONFIGURATION_FROZEN
    assert not (tmp_path / ".env").exists()
    assert (tmp_path / "config/llm.json").read_bytes() == before


def test_first_setup_can_establish_scm_while_configuration_writes_are_fenced(
    tmp_path: Path,
) -> None:
    handler, session = _setup_handler(tmp_path)
    session.external_blockers = lambda: ["SCM is not configured yet"]
    probes: list[str] = []

    def probe(*args: str) -> dict[str, Any]:
        with pytest.raises(ConfigurationConflict), session.admission():
            pytest.fail("SCM probe lost the configuration fence")
        probes.append(args[0])
        return {"valid": True}

    setup = SetupHandler(
        Bus(),
        project_root=tmp_path,
        configuration_authority=handler._configuration_authority,
        scm_tester=probe,
    )
    result = setup.configure_dashboard(
        {
            "scm_provider": "gitea",
            "scm_url": "https://gitea.example.test",
            "scm_token": "test-only-secret",
            "scm_repo": "owner/repo",
            "llm_provider": "manual",
        }
    )
    assert result["configured"] is True and result["restart_required"] is True
    assert probes == ["gitea"]
    assert "SCM_REPO=owner/repo" in (tmp_path / ".env").read_text()
    assert json.loads((tmp_path / "config/llm.json").read_text())["default"]["provider"] == "manual"
    assert session.state()["phase"] == "idle"


def test_setup_rest_write_reports_conflict_without_mutation(tmp_path: Path) -> None:
    handler, session = _setup_handler(tmp_path)
    api = RestAPI(Bus(), dashboard_handler=handler)
    with session.admission():
        response = api.handle_request(
            "POST", "/api/v1/settings/flag", {"name": "eval", "enabled": True}
        )
    assert response["status"] == 409
    assert response["data"]["code"] == CONFIGURATION_FROZEN
    assert not (tmp_path / "config/features.json").exists()


@pytest.mark.parametrize("phase", ["editing", "probing", "applying", "failed", "restoring"])
def test_setup_write_preserves_unfinished_configuration_session(tmp_path: Path, phase: str) -> None:
    handler, session = _setup_handler(tmp_path)
    state = session.state()
    state["phase"] = phase
    saved = session._save(state)
    result = handler.set_feature_flag("eval", True)
    assert result["updated"] is False and result["code"] == CONFIGURATION_FROZEN
    assert session.state() == saved
    assert not (tmp_path / "config/features.json").exists()


def test_configuration_mode_defaults_to_production_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAMUEL_CONFIGURATION_MODE", raising=False)

    assert resolve_configuration_mode() == ("production", "shipped_default")
    with pytest.raises(ValueError, match="production.*setup"):
        resolve_configuration_mode("automatic")


def test_configuration_status_separates_stored_from_effective_without_secret_digest(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "features.json").write_text('{"eval": false}\n', encoding="utf-8")
    authority = ConfigurationAuthority("setup", source="command_line", config_dir=config_dir)
    effective = authority.status()["effective_config_digest"]

    (tmp_path / ".env").write_text("TOKEN=secret-value\n", encoding="utf-8")
    (config_dir / "external-secret.json").symlink_to(tmp_path / ".env")
    assert authority.status()["stored_config_digest"] == effective
    (config_dir / "features.json").write_text('{"eval": true}\n', encoding="utf-8")
    status = authority.status()

    assert status["stored_config_digest"] != effective
    assert status["restart_required"] is True
    assert status["secret_environment_in_digest"] is False


def test_production_mode_blocks_dashboard_override_before_file_or_runtime_mutation(
    tmp_path: Path,
) -> None:
    config = FileConfig(tmp_path)
    authority = ConfigurationAuthority("production", source="command_line", config_dir=tmp_path)
    handler = DashboardHandler(
        Bus(),
        config=config,
        configuration_authority=authority,
    )

    result = handler.set_feature_flag("eval", True)

    assert result["updated"] is False
    assert result["code"] == CONFIGURATION_FROZEN
    assert not (tmp_path / "features.json").exists()
    assert config.feature_flag("eval") is False


def test_production_mode_blocks_every_dashboard_configuration_family(tmp_path: Path) -> None:
    config = FileConfig(tmp_path)
    authority = ConfigurationAuthority("production", source="command_line", config_dir=tmp_path)
    handler = DashboardHandler(
        Bus(),
        config=config,
        configuration_authority=authority,
    )

    results = [
        handler.set_risk_class("high_risk"),
        handler.set_attribution(True, "full"),
        handler.set_llm_global_config({"provider": "deepseek", "fallbacks": []}),
        handler.set_llm_task_config(
            "planning",
            {"provider": "deepseek", "model": "deepseek-chat"},
        ),
    ]

    assert all(result["code"] == CONFIGURATION_FROZEN for result in results)
    assert not (tmp_path / "compliance.json").exists()
    assert not (tmp_path / "features.json").exists()
    assert not (tmp_path / "privacy.json").exists()
    assert not (tmp_path / "llm.json").exists()
    assert not (tmp_path / "llm" / "defaults.json").exists()


def test_production_mode_blocks_dashboard_setup_before_persistence(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "llm.json").write_text(json.dumps({"default": {}}), encoding="utf-8")
    authority = ConfigurationAuthority(
        "production",
        source="command_line",
        config_dir=config_dir,
    )
    handler = SetupHandler(
        Bus(),
        project_root=tmp_path,
        configuration_authority=authority,
    )

    result = handler.configure_dashboard({"unexpected": "input"})

    assert result["configured"] is False
    assert result["code"] == CONFIGURATION_FROZEN
    assert not (tmp_path / ".env").exists()


def test_production_mode_blocks_dashboard_label_sync_before_remote_effect(
    tmp_path: Path,
) -> None:
    class Setup:
        def configuration_mutation_blocked(self) -> dict[str, object]:
            return {
                "synced": False,
                "code": CONFIGURATION_FROZEN,
                "error": "frozen",
            }

        def sync_labels(self) -> None:
            raise AssertionError("production mode must block before the SCM effect")

    response = RestAPI(Bus(), setup_handler=Setup()).handle_request("POST", "/api/v1/setup/labels")

    assert response["status"] == 409
    assert response["data"]["code"] == CONFIGURATION_FROZEN
