"""Tests for the per-issue baseline store (Issue #213)."""
from __future__ import annotations

import json
from pathlib import Path

from samuel.slices.evaluation.baseline_store import (
    get_baseline,
    load_baselines,
    promote_baseline,
)


class TestLoadBaselines:
    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        assert load_baselines(tmp_path) == {}

    def test_corrupt_json_treated_as_empty(self, tmp_path: Path) -> None:
        (tmp_path / "eval_baselines.json").write_text("not json")
        assert load_baselines(tmp_path) == {}

    def test_non_dict_payload_treated_as_empty(self, tmp_path: Path) -> None:
        (tmp_path / "eval_baselines.json").write_text(json.dumps([1, 2, 3]))
        assert load_baselines(tmp_path) == {}

    def test_keys_coerced_to_int_values_to_float(self, tmp_path: Path) -> None:
        (tmp_path / "eval_baselines.json").write_text(json.dumps({"42": 0.9, "7": 1}))
        result = load_baselines(tmp_path)
        assert result == {42: 0.9, 7: 1.0}

    def test_unparseable_entries_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "eval_baselines.json").write_text(
            json.dumps({"42": 0.9, "abc": "xyz"})
        )
        assert load_baselines(tmp_path) == {42: 0.9}


class TestGetBaseline:
    def test_default_when_missing(self, tmp_path: Path) -> None:
        assert get_baseline(tmp_path, 42) == 0.0
        assert get_baseline(tmp_path, 42, default=0.5) == 0.5

    def test_returns_persisted_value(self, tmp_path: Path) -> None:
        (tmp_path / "eval_baselines.json").write_text(json.dumps({"42": 0.85}))
        assert get_baseline(tmp_path, 42) == 0.85


class TestPromoteBaseline:
    def test_creates_file_on_first_promote(self, tmp_path: Path) -> None:
        new = promote_baseline(tmp_path, 42, 0.7)
        assert new == 0.7
        assert (tmp_path / "eval_baselines.json").exists()
        data = json.loads((tmp_path / "eval_baselines.json").read_text())
        assert data == {"42": 0.7}

    def test_promotes_only_when_score_higher(self, tmp_path: Path) -> None:
        promote_baseline(tmp_path, 42, 0.9)
        # Lower score does NOT regress the baseline
        new = promote_baseline(tmp_path, 42, 0.5)
        assert new == 0.9
        data = json.loads((tmp_path / "eval_baselines.json").read_text())
        assert data == {"42": 0.9}

    def test_equal_score_keeps_baseline(self, tmp_path: Path) -> None:
        promote_baseline(tmp_path, 42, 0.7)
        new = promote_baseline(tmp_path, 42, 0.7)
        assert new == 0.7

    def test_isolated_per_issue(self, tmp_path: Path) -> None:
        promote_baseline(tmp_path, 42, 0.9)
        promote_baseline(tmp_path, 99, 0.5)
        baselines = load_baselines(tmp_path)
        assert baselines == {42: 0.9, 99: 0.5}

    def test_atomic_write_uses_tmp_then_rename(self, tmp_path: Path) -> None:
        # After write, the .tmp file must NOT linger (rename moves it)
        promote_baseline(tmp_path, 42, 0.7)
        assert (tmp_path / "eval_baselines.json").exists()
        assert not (tmp_path / "eval_baselines.tmp").exists()
