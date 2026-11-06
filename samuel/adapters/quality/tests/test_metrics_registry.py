"""#153: Tests fuer die persistierte Quality-Metrics-Registry (EWMA)."""

from __future__ import annotations

import json
from pathlib import Path

from samuel.adapters.quality.metrics_registry import FileQualityMetricsRegistry


def test_first_record_sets_ewma_to_score(tmp_path: Path):
    reg = FileQualityMetricsRegistry(tmp_path)
    reg.record("deepseek", "deepseek-chat", "implementation", 1.0, True)
    assert reg.score_for("deepseek", "deepseek-chat", "implementation") == 1.0
    assert (tmp_path / "quality_metrics.json").exists()


def test_ewma_weights_recent_score(tmp_path: Path):
    reg = FileQualityMetricsRegistry(tmp_path, alpha=0.3)
    reg.record("p", "m", "t", 1.0, True)
    reg.record("p", "m", "t", 0.0, False)
    # 0.3*0 + 0.7*1.0 = 0.7
    assert reg.score_for("p", "m", "t") == 0.7


def test_aggregates_counts_pass_fail(tmp_path: Path):
    reg = FileQualityMetricsRegistry(tmp_path)
    reg.record("p", "m", "t", 1.0, True)
    reg.record("p", "m", "t", 1.0, True)
    reg.record("p", "m", "t", 0.0, False)
    rows = reg.aggregates()
    assert len(rows) == 1
    r = rows[0]
    assert r["count"] == 3
    assert r["passed"] == 2
    assert r["failed"] == 1
    assert r["success_rate_pct"] == 67  # 2/3


def test_score_for_unknown_returns_none(tmp_path: Path):
    reg = FileQualityMetricsRegistry(tmp_path)
    assert reg.score_for("x", "y", "z") is None


def test_separate_keys_isolated(tmp_path: Path):
    reg = FileQualityMetricsRegistry(tmp_path)
    reg.record("p", "m", "plan", 0.5, True)
    reg.record("p", "m", "impl", 1.0, True)
    assert reg.score_for("p", "m", "plan") == 0.5
    assert reg.score_for("p", "m", "impl") == 1.0
    assert len(reg.aggregates()) == 2


def test_corrupt_file_is_tolerated(tmp_path: Path):
    (tmp_path / "quality_metrics.json").write_text("{not json", encoding="utf-8")
    reg = FileQualityMetricsRegistry(tmp_path)
    reg.record("p", "m", "t", 1.0, True)  # should not raise
    assert reg.score_for("p", "m", "t") == 1.0
    # file is now valid JSON again
    json.loads((tmp_path / "quality_metrics.json").read_text())


def test_bound_and_legacy_observations_never_share_an_ewma_series(tmp_path: Path):
    reg = FileQualityMetricsRegistry(tmp_path, alpha=0.3)
    reg.record("p", "m", "t", 0.0, False)
    reg.record(
        "p",
        "m",
        "t",
        1.0,
        None,
        metadata={
            "evidence_origin": "bound_acceptance_evidence",
            "scoring_policy_version": "eval.v1",
            "formula_version": "bound.v1",
        },
    )

    rows = reg.aggregates()
    assert len(rows) == 2
    by_origin = {row["evidence_origin"]: row for row in rows}
    assert by_origin["unbound_worktree"]["ewma_score"] == 0.0
    assert by_origin["bound_acceptance_evidence"]["ewma_score"] == 1.0
