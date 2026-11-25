from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from samuel.core.config import EvalSchema, load_eval_config


class TestEvalSchema:
    def test_valid_defaults(self):
        cfg = EvalSchema()
        assert abs(sum(cfg.weights.values()) - 1.0) < 0.01
        assert cfg.baseline == 0.8
        assert cfg.fail_fast_on == []

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="weights must sum to 1.0"):
            EvalSchema(weights={"a": 0.5, "b": 0.3})

    def test_fail_fast_on_unknown_check(self):
        with pytest.raises(ValueError, match="unknown checks"):
            EvalSchema(
                weights={"a": 0.5, "b": 0.5},
                fail_fast_on=["c"],
            )

    def test_fail_fast_on_valid(self):
        cfg = EvalSchema(
            weights={"a": 0.5, "b": 0.5},
            fail_fast_on=["a"],
        )
        assert cfg.fail_fast_on == ["a"]

    def test_custom_weights(self):
        cfg = EvalSchema(
            weights={"x": 0.7, "y": 0.3},
            baseline=0.5,
        )
        assert cfg.weights["x"] == 0.7
        assert cfg.baseline == 0.5

    def test_runner_policy_is_validated(self):
        cfg = EvalSchema(test_cmd='pytest -q "{test}"', test_timeout=30)

        assert cfg.test_cmd == 'pytest -q "{test}"'
        assert cfg.test_timeout == 30

    def test_runner_command_requires_test_placeholder(self):
        with pytest.raises(ValueError, match="test_cmd must contain"):
            EvalSchema(test_cmd="pytest -q")

    def test_runner_command_requires_valid_quoting(self):
        with pytest.raises(ValueError, match="valid shell-like quoting"):
            EvalSchema(test_cmd='pytest -q "{test}')

    @pytest.mark.parametrize("timeout", [0, 3601])
    def test_runner_timeout_is_bounded(self, timeout: int):
        with pytest.raises(ValueError):
            EvalSchema(test_timeout=timeout)

    def test_legacy_criteria_is_accepted_but_warns_and_has_no_weight_effect(
        self, caplog: pytest.LogCaptureFixture
    ):
        with caplog.at_level(logging.WARNING):
            cfg = EvalSchema.model_validate(
                {
                    "criteria": [{"name": "legacy", "weight": 1.0}],
                    "weights": {"current": 1.0},
                }
            )

        assert cfg.weights == {"current": 1.0}
        assert "criteria is deprecated" in caplog.text

    def test_legacy_criteria_is_marked_deprecated_in_json_schema(self):
        field_schema = EvalSchema.model_json_schema()["properties"]["criteria"]
        assert field_schema["deprecated"] is True


class TestLoadEvalConfig:
    def test_load_from_file(self, tmp_path: Path):
        data = {
            "weights": {"a": 0.6, "b": 0.4},
            "baseline": 0.7,
            "fail_fast_on": ["a"],
            "test_policy_version": "test.runner.v2",
            "test_cmd": "custom-runner {test}",
            "test_timeout": 45,
        }
        (tmp_path / "eval.json").write_text(json.dumps(data))
        cfg = load_eval_config(tmp_path)
        assert cfg.weights == {"a": 0.6, "b": 0.4}
        assert cfg.baseline == 0.7
        assert cfg.fail_fast_on == ["a"]
        assert cfg.test_policy_version == "test.runner.v2"
        assert cfg.test_cmd == "custom-runner {test}"
        assert cfg.test_timeout == 45

    def test_missing_file_returns_defaults(self, tmp_path: Path):
        cfg = load_eval_config(tmp_path)
        assert cfg.baseline == 0.8
        assert len(cfg.weights) == 4

    def test_invalid_json_raises(self, tmp_path: Path):
        (tmp_path / "eval.json").write_text("not json")
        with pytest.raises(ValueError, match="Invalid eval.json"):
            load_eval_config(tmp_path)

    def test_invalid_weights_raises(self, tmp_path: Path):
        (tmp_path / "eval.json").write_text('{"weights": {"a": 0.1}}')
        with pytest.raises(ValueError, match="validation failed"):
            load_eval_config(tmp_path)
