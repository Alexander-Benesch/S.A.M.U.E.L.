from __future__ import annotations

import json
from pathlib import Path

import pytest

from samuel.adapters.api.rest import RestAPI
from samuel.core.bus import Bus
from samuel.core.config import FileConfig
from samuel.core.configuration_mode import (
    CONFIGURATION_FROZEN,
    ConfigurationAuthority,
    resolve_configuration_mode,
)
from samuel.slices.dashboard.handler import DashboardHandler
from samuel.slices.setup.handler import SetupHandler


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
