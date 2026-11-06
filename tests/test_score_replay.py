from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.config import EvalSchema
from samuel.core.state import ObservationRecord
from samuel.slices.evaluation.replay import ScoreReplay


def test_score_replay_is_idempotent_multi_formula_and_side_effect_free(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    observed_at = datetime(2026, 8, 30, 9, 0, tzinfo=timezone.utc)
    observation = ObservationRecord(
        observation_key="sha256:" + "a" * 64,
        subject_key="sha256:" + "b" * 64,
        evidence_digest="sha256:" + "c" * 64,
        observation_schema="bound.v2",
        issue_number=667,
        payload={
            "evaluation_subject": {"repository": "example/repo"},
            "gate_results": [
                {"authority": "required", "passed": True},
            ],
            "acceptance_evidence": {
                "results": [
                    {"criterion_id": "AC-1", "tag": "TEST", "status": "passed"},
                    {"criterion_id": "AC-2", "tag": "DIFF", "status": "failed"},
                ]
            },
        },
        observed_at=observed_at,
    )
    store.observations.put_observation(observation)
    policies = [
        EvalSchema(policy_version="policy.v1", formula_version="formula.v1"),
        EvalSchema(policy_version="policy.v1", formula_version="formula.v2"),
    ]
    replay = ScoreReplay(store.observations, policies)
    quality_before = store.dump()["row_counts"]["quality_metrics"]

    first = replay.replay(issue_number=667)
    second = replay.replay(issue_number=667)

    assert first["created"] == 2
    assert first["duplicates"] == 0
    assert first["workflow_events_published"] == 0
    assert first["quality_metrics_updated"] == 0
    assert second["created"] == 0
    assert second["duplicates"] == 2
    assert {row.formula_version for row in store.observations.list_derivations(667)} == {
        "formula.v1",
        "formula.v2",
    }
    assert all(row.derived_at == observed_at for row in store.observations.list_derivations(667))
    assert store.dump()["row_counts"]["quality_metrics"] == quality_before
