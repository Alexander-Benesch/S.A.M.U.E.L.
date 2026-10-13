from __future__ import annotations

from pathlib import Path

import pytest

from samuel.core.config import GatesConfigSchema, load_gates_config


class TestGatesConfigSchema:
    def test_default_values(self):
        cfg = GatesConfigSchema()
        assert 1 in cfg.required
        assert 4 not in cfg.required + cfg.optional + cfg.disabled
        assert 10 not in cfg.required + cfg.optional + cfg.disabled
        assert cfg.disabled == []
        assert cfg.custom == []
        assert cfg.parameters.max_diff_bytes == 2_000_000
        assert cfg.parameters.max_quality_file_bytes == 1_000_000
        assert cfg.policy_version == "2026-08-28.bound.v2"

    def test_custom_values(self):
        cfg = GatesConfigSchema(
            required=[1, 2],
            optional=[3],
            disabled=[6],
            custom=[{"name": "test", "type": "webhook"}],
        )
        assert cfg.required == [1, 2]
        assert cfg.disabled == [6]

    def test_retired_eval_score_threshold_is_rejected(self):
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            GatesConfigSchema(parameters={"eval_score_threshold": 0.85})

    def test_unknown_top_level_gate_setting_is_rejected(self):
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            GatesConfigSchema.model_validate({"eval_score_threshold": 0.85})

    def test_custom_subject_policy_and_diff_limit(self):
        cfg = GatesConfigSchema(
            policy_version="release.v2",
            parameters={"max_diff_bytes": 4096},
        )

        assert cfg.policy_version == "release.v2"
        assert cfg.parameters.max_diff_bytes == 4096

    @pytest.mark.parametrize("invalid", [0, -1, 100_000_001])
    def test_invalid_diff_limit_is_rejected(self, invalid):
        with pytest.raises(ValueError):
            GatesConfigSchema(parameters={"max_diff_bytes": invalid})

    @pytest.mark.parametrize("gate_id", [4, 10])
    def test_retired_score_gates_are_rejected(self, gate_id):
        with pytest.raises(ValueError, match="unknown or retired gate IDs"):
            GatesConfigSchema(required=[gate_id], optional=[])

    def test_string_gate_ids(self):
        cfg = GatesConfigSchema(required=["13a", "13b"], optional=[])
        assert "13a" in cfg.required


class TestLoadGatesConfig:
    def test_loads_from_file(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [1, 2], "optional": [3], "disabled": [6], "custom": [], '
            '"parameters": {"max_diff_bytes": 4096}}'
        )
        cfg = load_gates_config(tmp_path)
        assert cfg.required == [1, 2]
        assert cfg.disabled == [6]
        assert cfg.parameters.max_diff_bytes == 4096

    def test_missing_file_returns_default(self, tmp_path: Path):
        cfg = load_gates_config(tmp_path)
        assert 1 in cfg.required
        assert cfg.disabled == []

    def test_invalid_json_raises(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text("{invalid json")
        with pytest.raises(ValueError, match="Invalid gates config"):
            load_gates_config(tmp_path)

    def test_disabled_gate_6_skipped(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [1, 2, 3], "optional": [5], "disabled": [6], "custom": []}'
        )
        cfg = load_gates_config(tmp_path)
        assert 6 in cfg.disabled
        assert 6 not in cfg.required
        assert 6 not in cfg.optional
