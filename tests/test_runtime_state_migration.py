from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from samuel.adapters.llm.metering import MeteringLLMAdapter
from samuel.adapters.state.legacy import LegacyStateMigrator
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.bus import Bus, DeadLetterQueue
from samuel.core.events import Event
from samuel.core.issue_context import issue_scope
from samuel.core.ports import IRunProjectionStore
from samuel.core.state import (
    ObservationRecord,
    RunProjectionRecord,
    ScoreDerivationRecord,
    StateStoreError,
)
from samuel.core.types import LLMResponse
from samuel.slices.dashboard.data import (
    get_score_history,
    get_workflow_issue_detail,
    get_workflow_issues,
    get_workflow_runs,
)
from samuel.slices.run_projection.handler import RunProjectionHandler


def _mountinfo(tmp_path: Path) -> Path:
    path = tmp_path / "mountinfo"
    path.write_text(f"36 25 0:32 / {tmp_path} rw - ext4 device rw\n", encoding="utf-8")
    return path


def _store(tmp_path: Path) -> SQLiteStateStore:
    return SQLiteStateStore(tmp_path / "data", mountinfo_path=_mountinfo(tmp_path))


def _legacy_documents(data_dir: Path) -> dict[str, bytes]:
    observation_key = "sha256:" + "a" * 64
    score_key = "sha256:" + "b" * 64
    subject = {
        "repository": "owner/repo",
        "base_sha": "c" * 40,
        "head_sha": "d" * 40,
        "contract_hash": "sha256:" + "e" * 64,
        "policy_version": "gates.v1",
        "policy_digest": "sha256:" + "f" * 64,
    }
    documents = {
        "evaluation_observations.json": {
            "schema_version": 1,
            "observations": {
                observation_key: {
                    "schema_version": 1,
                    "observation_key": observation_key,
                    "evidence_digest": "sha256:" + "1" * 64,
                    "issue": 627,
                    "correlation_ids": ["run-legacy"],
                    "evaluation_subject": subject,
                    "gate_results": [],
                    "acceptance_evidence": None,
                }
            },
            "scores": {
                score_key: {
                    "score_key": score_key,
                    "observation_key": observation_key,
                    "issue": 627,
                    "score": 0.75,
                    "non_binding": True,
                    "label": "Nicht bindende Qualitätsbeobachtung",
                    "evidence_origin": "bound_acceptance_evidence",
                    "scoring_policy_version": "eval.v1",
                    "scoring_policy_digest": "sha256:" + "2" * 64,
                    "formula_version": "bound.v1",
                }
            },
            "unavailable": {
                "sha256:" + "3" * 64: {
                    "terminal_key": "sha256:" + "3" * 64,
                    "issue": 628,
                    "status": "not_evaluated",
                }
            },
        },
        "quality_metrics.json": {
            "p|m|implementation": {
                "provider": "p",
                "model": "m",
                "task": "implementation",
                "evidence_origin": "unbound_worktree",
                "scoring_policy_version": "legacy",
                "formula_version": "legacy",
                "ewma_score": 0.6,
                "count": 2,
                "passed": 1,
                "failed": 1,
                "observed": 0,
                "last_score": 0.7,
                "last_ts": "2026-08-28T10:00:00+00:00",
            }
        },
        "score_history.json": [
            {
                "ts": "2026-08-28T10:00:00+00:00",
                "issue": 626,
                "score": 0.6,
                "baseline": 0.8,
                "passed": False,
                "criteria": {},
            }
        ],
        "eval_baselines.json": {"626": 0.8},
    }
    raw_documents: dict[str, bytes] = {}
    for filename, document in documents.items():
        raw = (json.dumps(document, sort_keys=True) + "\n").encode()
        (data_dir / filename).write_bytes(raw)
        raw_documents[filename] = raw
    return raw_documents


def test_legacy_import_is_one_way_checksum_bound_and_series_safe(tmp_path: Path) -> None:
    store = _store(tmp_path)
    raw_documents = _legacy_documents(store.data_dir)

    report = LegacyStateMigrator(store).migrate()

    assert report["imported_sources"] == 4
    assert len(store.observations.list_observations(627)) == 1
    assert len(store.observations.list_derivations(627)) == 1
    assert len(store.observations.list_terminals(628)) == 1
    assert store.quality_metrics.score_for("p", "m", "implementation") == 0.6
    assert (
        get_score_history(
            str(store.data_dir),
            observation_store=store.observations,
            projection_store=store.projections,
        )[0]["observation_schema"]
        == "bound.v1"
    )
    for filename, raw in raw_documents.items():
        assert not (store.data_dir / filename).exists()
        archives = list(store.data_dir.glob(f"{filename}.migrated-*"))
        assert len(archives) == 1
        assert archives[0].read_bytes() == raw
        assert archives[0].stat().st_mode & 0o777 == 0o400

    assert LegacyStateMigrator(store).migrate()["sources"] == []

    (store.data_dir / "quality_metrics.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(StateStoreError) as changed:
        LegacyStateMigrator(store).migrate()
    assert changed.value.code == "state_legacy_changed"


def test_healing_claim_import_is_atomic_one_way_and_preserves_at_most_once(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    source = store.data_dir / "bound_healing_attempts.json"
    raw = (
        json.dumps(
            {
                "schema_version": 1,
                "attempts": {
                    "obs-claimed": {"status": "claimed"},
                    "obs-suggested": {"status": "suggested"},
                    "obs-error": {"status": "llm_error"},
                },
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    source.write_bytes(raw)

    report = LegacyStateMigrator(store).migrate_authority()

    assert report["imported_sources"] == 1
    claimed = store.authority.get_healing_claim("obs-claimed")
    suggested = store.authority.get_healing_claim("obs-suggested")
    error = store.authority.get_healing_claim("obs-error")
    assert claimed is not None
    assert claimed.status == "claimed"
    assert suggested is not None
    assert (suggested.status, suggested.outcome) == ("attempted", "suggested")
    assert error is not None
    assert (error.status, error.outcome) == ("attempted", "llm_error")
    assert not source.exists()
    archives = list(store.data_dir.glob("bound_healing_attempts.json.migrated-*"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == raw
    assert archives[0].stat().st_mode & 0o777 == 0o400
    assert LegacyStateMigrator(store).migrate_authority()["sources"] == []

    source.write_text('{"schema_version":1,"attempts":{}}\n', encoding="utf-8")
    with pytest.raises(StateStoreError) as changed:
        LegacyStateMigrator(store).migrate_authority()
    assert changed.value.code == "state_legacy_changed"


def test_invalid_healing_claim_source_does_not_partially_import(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = store.data_dir / "bound_healing_attempts.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "attempts": {
                    "valid": {"status": "claimed"},
                    "invalid": {"status": 7},
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StateStoreError) as invalid:
        LegacyStateMigrator(store).migrate_authority()

    assert invalid.value.code == "state_legacy_invalid"
    assert store.authority.get_healing_claim("valid") is None
    assert source.exists()


def test_dashboard_history_treats_observation_schema_change_as_series_cut(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    old_time = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)
    new_time = datetime(2026, 8, 29, 11, 0, tzinfo=timezone.utc)
    for suffix, schema, score, observed_at in (
        ("old", "bound.v1", 0.95, old_time),
        ("new", "bound.v2", 0.55, new_time),
    ):
        observation_key = f"observation-{suffix}"
        store.observations.put_observation(
            ObservationRecord(
                observation_key=observation_key,
                subject_key=f"subject-{suffix}",
                evidence_digest=f"evidence-{suffix}",
                observation_schema=schema,
                payload={"issue": 627},
                issue_number=627,
                observed_at=observed_at,
            )
        )
        store.observations.put_derivation(
            ScoreDerivationRecord(
                score_key=f"score-{suffix}",
                observation_key=observation_key,
                scoring_policy_version="eval.v1",
                scoring_policy_digest="policy-digest",
                formula_version="bound.v1",
                score=score,
                payload={"coverage": 1.0},
                issue_number=627,
                observation_schema=schema,
                derived_at=observed_at,
            )
        )

    history = get_score_history(
        str(store.data_dir),
        observation_store=store.observations,
        projection_store=store.projections,
    )

    assert [(row["observation_schema"], row["score"]) for row in history] == [("bound.v2", 0.55)]


def test_run_projection_survives_audit_removal_and_replay_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bus = Bus()
    projector = RunProjectionHandler(bus, store.projections)
    projector.register()
    event = Event(
        name="PRCreated",
        payload={"issue": 627, "pr_number": 628, "token": "secret-value"},
        correlation_id="run-627",
    )

    bus.publish(event)
    bus.publish(event)

    rows = store.projections.list_projections(627, series="workflow-run.v1")
    assert len(rows) == 1
    assert len(rows[0].payload["events"]) == 1
    assert "secret-value" not in json.dumps(rows[0].payload)
    assert (
        get_workflow_runs(
            627,
            str(store.data_dir),
            projection_store=store.projections,
        )[0]["pr_number"]
        == 628
    )

    logs = store.data_dir / "logs"
    logs.mkdir()
    (logs / "agent.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-08-29T12:00:00+00:00",
                "payload": {
                    **event.payload,
                    "message_name": "PRCreated",
                    "message_type": "PRCreated",
                    "correlation_id": "run-627",
                    "duration_ms": 3.2,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    projector.backfill_audit(store.data_dir)
    assert len(store.projections.list_projections(627)[0].payload["events"]) == 1
    (logs / "agent.jsonl").unlink()
    reopened = _store(tmp_path)
    assert (
        get_workflow_runs(
            627,
            str(store.data_dir),
            projection_store=reopened.projections,
        )[0]["final_status"]
        == "pr_created"
    )


@pytest.mark.parametrize(
    "event_name",
    [
        "PlanBlocked",
        "PlanReplanRejected",
        "LLMUnavailable",
        "WorkflowAborted",
        "WorkflowBlocked",
        "PRCreationFailed",
        "EvaluationSubjectInvalidated",
    ],
)
def test_projection_materializes_real_failure_terminals_as_blocked(
    tmp_path: Path,
    event_name: str,
) -> None:
    store = _store(tmp_path)
    bus = Bus()
    RunProjectionHandler(bus, store.projections).register()

    bus.publish(Event(name=event_name, payload={"issue": 672}, correlation_id="run-672"))

    row = store.projections.list_projections(672, series="workflow-run.v1")[0]
    assert row.status == "blocked"
    assert row.payload["outcome"]["terminal_event"] == event_name


def test_projection_reduction_is_idempotent_and_independent_of_delivery_order(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    bus = Bus()
    RunProjectionHandler(bus, store.projections).register()
    created = Event(
        name="PRCreated",
        payload={"issue": 672, "pr_number": 676},
        correlation_id="run-recovered",
        ts=datetime(2026, 8, 30, 12, 2, tzinfo=timezone.utc),
    )
    earlier_block = Event(
        name="PlanBlocked",
        payload={"issue": 672},
        correlation_id="run-recovered",
        ts=datetime(2026, 8, 30, 12, 1, tzinfo=timezone.utc),
    )

    bus.publish(created)
    bus.publish(earlier_block)
    before_duplicate = store.projections.list_projections(672, series="workflow-run.v1")[0]
    bus.publish(earlier_block)

    row = store.projections.list_projections(672, series="workflow-run.v1")[0]
    assert row.status == "complete"
    assert row.payload["outcome"] == {
        "status": "pr_created",
        "terminal_event": "PRCreated",
    }
    assert len(row.payload["events"]) == 2
    assert row.updated_at == before_duplicate.updated_at

    bus.publish(
        Event(
            name="EvaluationSubjectInvalidated",
            payload={"issue": 672},
            correlation_id="run-recovered",
            ts=datetime(2026, 8, 30, 12, 3, tzinfo=timezone.utc),
        )
    )
    assert store.projections.list_projections(672, series="workflow-run.v1")[0].status == "blocked"


def test_dashboard_state_is_consistent_from_out_of_order_run_projection(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bus = Bus()
    RunProjectionHandler(bus, store.projections).register()
    bus.publish(
        Event(
            name="PlanValidated",
            payload={"issue": 738},
            correlation_id="run-738",
            ts=datetime(2026, 9, 1, 12, 3, tzinfo=timezone.utc),
        )
    )
    bus.publish(
        Event(
            name="IssueReady",
            payload={"issue": 738},
            correlation_id="run-738",
            ts=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        )
    )

    rows = get_workflow_issues(
        str(store.data_dir),
        projection_store=store.projections,
    )
    detail = get_workflow_issue_detail(
        738,
        str(store.data_dir),
        projection_store=store.projections,
    )

    assert detail is not None
    assert rows[0]["status"] == detail["status"] == "planned"
    assert rows[0]["last_event"] == detail["last_event"] == "PlanValidated"
    assert detail["runs"][0]["final_status"] == "incomplete"


def test_existing_projection_reconciliation_separates_blocked_and_unbound(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    for key, correlation_id, event_name in (
        ("stale-blocked", "run-plan", "PlanBlocked"),
        ("legacy-call", "call-only", "LLMCallCompleted"),
    ):
        store.projections.upsert_projection(
            RunProjectionRecord(
                projection_key=key,
                issue_number=414,
                correlation_id=correlation_id,
                series="workflow-run.v1",
                status="running",
                payload={
                    "schema": "workflow-run.v1",
                    "events": [
                        {
                            "ts": "2026-08-20T10:00:00+00:00",
                            "event_key": key,
                            "payload": {
                                "message_name": event_name,
                                "issue": 414,
                                "correlation_id": correlation_id,
                            },
                        }
                    ],
                },
                updated_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
            )
        )
    projector = RunProjectionHandler(Bus(), store.projections)

    first = projector.reconcile_existing()
    second = projector.reconcile_existing()

    assert first == {
        "scanned": 2,
        "updated": 2,
        "running": 0,
        "unbound": 1,
        "blocked": 1,
        "complete": 0,
    }
    assert second["updated"] == 0
    assert {row.projection_key: row.status for row in store.projections.list_projections(414)} == {
        "legacy-call": "unbound",
        "stale-blocked": "blocked",
    }
    runs = get_workflow_runs(414, str(store.data_dir), projection_store=store.projections)
    assert [run["run_id"] for run in runs] == ["run-plan"]
    assert runs[0]["final_status"] == "blocked"


def test_metered_llm_event_joins_existing_workflow_run_projection(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bus = Bus()
    RunProjectionHandler(bus, store.projections).register()
    inner = Mock()
    inner.complete.return_value = LLMResponse(
        text="plan",
        input_tokens=10,
        output_tokens=5,
        stop_reason="end_turn",
        model_used="test-model",
    )
    metered = MeteringLLMAdapter(inner, bus, "test")

    bus.publish(Event(name="IssueReady", payload={"issue": 675}, correlation_id="run-675"))
    with issue_scope(675, "run-675"):
        metered.complete([{"role": "user", "content": "plan"}], task="planning")

    rows = store.projections.list_projections(675, series="workflow-run.v1")
    assert len(rows) == 1
    assert rows[0].correlation_id == "run-675"
    assert [event["payload"]["message_name"] for event in rows[0].payload["events"]] == [
        "IssueReady",
        "LLMCallCompleted",
    ]
    assert rows[0].payload["events"][1]["payload"]["workflow_correlation_bound"] is True


def test_restart_preserves_exact_quality_series_and_multiple_issue_runs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bus = Bus()
    projector = RunProjectionHandler(bus, store.projections)
    projector.register()
    for correlation_id, pr_number in (("run-a", 701), ("run-b", 702)):
        bus.publish(
            Event(
                name="PRCreated",
                payload={"issue": 627, "pr_number": pr_number},
                correlation_id=correlation_id,
            )
        )
    for schema, score in (("bound.v1", 0.9), ("bound.v2", 0.4)):
        store.quality_metrics.record(
            "provider",
            "model",
            "implementation",
            score,
            None,
            {
                "evidence_origin": "bound_acceptance_evidence",
                "observation_schema": schema,
                "scoring_policy_version": "eval.v1",
                "formula_version": "bound.v1",
            },
        )

    reopened = _store(tmp_path)
    runs = reopened.projections.list_projections(627, series="workflow-run.v1")
    quality = reopened.quality_metrics.aggregates()

    assert {run.correlation_id for run in runs} == {"run-a", "run-b"}
    assert {(row["observation_schema"], row["ewma_score"]) for row in quality} == {
        ("bound.v1", 0.9),
        ("bound.v2", 0.4),
    }


def test_projection_subscriber_failure_is_dlq_visible_and_does_not_block(tmp_path: Path) -> None:
    class BrokenProjectionStore(IRunProjectionStore):
        def get_projection(self, projection_key: str) -> RunProjectionRecord | None:
            return None

        def list_projections(
            self,
            issue_number: int | None = None,
            *,
            series: str | None = None,
        ) -> list[RunProjectionRecord]:
            return []

        def upsert_projection(self, record: RunProjectionRecord) -> None:
            raise StateStoreError("state_locked", "Runtime-state database is locked or busy")

    bus = Bus()
    bus.dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    observed: list[str] = []
    RunProjectionHandler(bus, BrokenProjectionStore()).register()
    bus.subscribe("*", lambda event: observed.append(event.name))

    bus.publish(Event(name="CodeGenerated", payload={"issue": 627}, correlation_id="run"))

    assert observed == ["CodeGenerated"]
    assert bus.dlq.list()[0]["event_name"] == "CodeGenerated"
    assert "locked or busy" in bus.dlq.list()[0]["error"]
