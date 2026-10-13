from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

from samuel.adapters.state.sqlite import (
    AUTHORITY_WITNESS_LOCK_FILENAME,
    DATABASE_FILENAME,
    SQLiteStateStore,
    audit_authority_high_watermark,
)
from samuel.core.state import (
    AuthorityLeaseRecord,
    AuthorityRecord,
    EvaluationTerminalRecord,
    HealingClaimRecord,
    LLMBudgetAttemptRecord,
    ManagedBackupRecord,
    ObservationRecord,
    OperationIntentRecord,
    PlanningClarificationRecord,
    ReconcileEntryRecord,
    RunProjectionRecord,
    ScoreDerivationRecord,
    StateStoreConflict,
    StateStoreError,
    WorkflowBudgetAdmissionRecord,
    WorkflowCheckpointRecord,
)


def _hold_state_reader(
    data_dir: str,
    mountinfo_path: str,
    ready: Any,
    release: Any,
) -> None:
    store = SQLiteStateStore(Path(data_dir), mountinfo_path=Path(mountinfo_path), timeout=5)
    with store._connection():
        ready.set()
        release.wait(timeout=10)


def _write_authority_after_signal(
    data_dir: str,
    mountinfo_path: str,
    ready: Any,
    completed: Any,
) -> None:
    ready.set()
    store = SQLiteStateStore(Path(data_dir), mountinfo_path=Path(mountinfo_path), timeout=5)
    store.authority.claim_healing(HealingClaimRecord("obs-process-writer", 666, "run-writer"))
    completed.set()


def _mountinfo(tmp_path: Path, filesystem: str = "ext4") -> Path:
    path = tmp_path / "mountinfo"
    path.write_text(
        f"36 25 0:32 / {tmp_path} rw,relatime - {filesystem} device rw\n",
        encoding="utf-8",
    )
    return path


def _store(tmp_path: Path, *, filesystem: str = "ext4", timeout: float = 1.0) -> SQLiteStateStore:
    return SQLiteStateStore(
        tmp_path / "data",
        mountinfo_path=_mountinfo(tmp_path, filesystem),
        timeout=timeout,
    )


def _observation(**overrides: object) -> ObservationRecord:
    values: dict[str, object] = {
        "observation_key": "obs-1",
        "subject_key": "subject-1",
        "evidence_digest": "sha256:evidence",
        "observation_schema": "bound.v1",
        "payload": {"criteria": 3},
        "observed_at": datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return ObservationRecord(**values)  # type: ignore[arg-type]


def test_fresh_schema_is_local_versioned_wal_and_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    status = store.status()

    assert status.healthy is True
    assert status.schema_version == 10
    assert status.supported_schema_version == 10
    assert status.journal_mode == "wal"
    assert status.auto_vacuum == "incremental"
    assert status.foreign_keys is True
    assert status.filesystem_type == "ext4"
    assert status.tables == (
        "authority_leases",
        "authority_metadata",
        "authority_records",
        "evaluation_terminals",
        "healing_claims",
        "identity_metadata",
        "identity_principal_roles",
        "identity_principals",
        "identity_sessions",
        "identity_tokens",
        "legacy_imports",
        "llm_budget_attempts",
        "managed_backups",
        "observations",
        "operation_intents",
        "planning_clarifications",
        "quality_metrics",
        "reconcile_entries",
        "restore_operations",
        "retention_category_states",
        "retention_executions",
        "run_projections",
        "schema_migrations",
        "score_derivations",
        "workflow_budget_admissions",
        "workflow_checkpoints",
    )
    assert store.path.stat().st_mode & 0o777 == 0o600

    reopened = _store(tmp_path)
    assert reopened.status().as_dict() == status.as_dict()


def test_relative_data_dir_is_resolved_next_to_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "etc" / "config"
    config_dir.mkdir(parents=True)
    mountinfo = _mountinfo(tmp_path)

    store = SQLiteStateStore("runtime", config_dir=config_dir, mountinfo_path=mountinfo)

    assert store.path == tmp_path / "etc" / "runtime" / DATABASE_FILENAME


def test_observation_and_derivation_are_immutable_and_replayable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    observation = _observation()
    derivation = ScoreDerivationRecord(
        score_key="score-1",
        observation_key=observation.observation_key,
        scoring_policy_version="policy.v1",
        formula_version="formula.v1",
        score=0.75,
        payload={"coverage": 0.5},
        derived_at=datetime(2026, 8, 29, 10, 1, tzinfo=timezone.utc),
    )

    assert store.observations.put_observation(observation) is True
    assert store.observations.put_observation(observation) is False
    assert store.observations.get_observation("obs-1") == observation
    assert store.observations.put_derivation(derivation) is True
    assert store.observations.put_derivation(derivation) is False
    assert store.observations.get_derivation("score-1") == derivation

    with pytest.raises(StateStoreError, match="different bound content") as conflict:
        store.observations.put_observation(_observation(payload={"criteria": 4}))
    assert conflict.value.code == "state_record_conflict"


def test_derivation_requires_bound_observation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = ScoreDerivationRecord(
        score_key="missing-score",
        observation_key="missing-observation",
        scoring_policy_version="policy.v1",
        formula_version="formula.v1",
        score=None,
        payload={},
    )

    with pytest.raises(StateStoreError) as exc_info:
        store.observations.put_derivation(record)

    assert exc_info.value.code == "state_observation_missing"


def test_observation_queries_terminals_and_formula_series_are_persistent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    observation = _observation(issue_number=627, observation_schema="bound.v1")
    assert store.observations.put_observation(observation) is True
    for formula, score in (("formula.v1", 0.75), ("formula.v2", 0.8)):
        assert store.observations.put_derivation(
            ScoreDerivationRecord(
                score_key=f"score-{formula}",
                observation_key=observation.observation_key,
                scoring_policy_version="policy.v1",
                scoring_policy_digest="sha256:policy",
                formula_version=formula,
                score=score,
                payload={"formula": formula},
                issue_number=627,
                observation_schema="bound.v1",
            )
        )
    terminal = EvaluationTerminalRecord(
        terminal_key="terminal-1",
        issue_number=627,
        status="unavailable",
        payload={"reason": "subject unavailable"},
    )
    assert store.observations.put_terminal(terminal) is True
    assert store.observations.put_terminal(terminal) is False

    reopened = _store(tmp_path)
    assert reopened.observations.list_observations(627) == [observation]
    assert [row.formula_version for row in reopened.observations.list_derivations(627)] == [
        "formula.v1",
        "formula.v2",
    ]
    assert reopened.observations.list_terminals(627) == [terminal]


def test_v1_foundation_upgrades_to_current_schema_without_losing_rows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = store.path
    del store
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        DROP TABLE evaluation_terminals;
        DROP TABLE llm_budget_attempts;
        DROP TABLE workflow_budget_admissions;
        DROP TABLE planning_clarifications;
        DROP TABLE authority_leases;
        DROP TABLE authority_metadata;
        DROP TABLE healing_claims;
        DROP TABLE operation_intents;
        DROP TABLE workflow_checkpoints;
        DROP TABLE legacy_imports;
        DROP TABLE quality_metrics;
        DROP TABLE managed_backups;
        DROP TABLE reconcile_entries;
        DROP TABLE restore_operations;
        DROP TABLE retention_category_states;
        DROP TABLE retention_executions;
        DROP INDEX observations_issue_series;
        DROP INDEX score_derivations_issue_series;
        CREATE TABLE observations_v1 AS SELECT
          observation_key, subject_key, evidence_digest, observation_schema,
          payload_json, observed_at FROM observations;
        DROP TABLE score_derivations;
        DROP TABLE observations;
        ALTER TABLE observations_v1 RENAME TO observations;
        CREATE TABLE score_derivations (
          score_key TEXT PRIMARY KEY,
          observation_key TEXT NOT NULL REFERENCES observations(observation_key),
          scoring_policy_version TEXT NOT NULL,
          formula_version TEXT NOT NULL,
          score REAL,
          payload_json TEXT NOT NULL,
          derived_at TEXT NOT NULL
        );
        DROP TABLE identity_tokens;
        DROP TABLE identity_sessions;
        DROP TABLE identity_principal_roles;
        DROP TABLE identity_principals;
        DROP TABLE identity_metadata;
        DELETE FROM schema_migrations WHERE version IN (2, 3, 4, 5, 6, 7, 8, 9, 10);
        PRAGMA user_version = 1;
        """
    )
    connection.commit()
    connection.close()

    upgraded = _store(tmp_path)

    assert upgraded.status().schema_version == 10
    assert "legacy_imports" in upgraded.status().tables


def test_projection_is_replaceable_but_authority_is_create_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    projection = RunProjectionRecord(
        projection_key="run-1",
        issue_number=625,
        correlation_id="corr-1",
        series="bound.v1",
        status="running",
        payload={"step": 1},
        updated_at=datetime(2026, 8, 29, 10, 2, tzinfo=timezone.utc),
    )
    store.projections.upsert_projection(projection)
    replacement = RunProjectionRecord(
        projection_key="run-1",
        issue_number=625,
        correlation_id="corr-1",
        series="bound.v1",
        status="complete",
        payload={"step": 2},
        updated_at=datetime(2026, 8, 29, 10, 3, tzinfo=timezone.utc),
    )
    store.projections.upsert_projection(replacement)
    assert store.projections.get_projection("run-1") == replacement

    authority = AuthorityRecord(
        record_key="intent-1",
        kind="test-only",
        payload={"effect": "none"},
        updated_at=datetime(2026, 8, 29, 10, 4, tzinfo=timezone.utc),
    )
    assert store.authority.put_authority_record(authority) is True
    assert store.authority.put_authority_record(authority) is False
    assert store.authority.get_authority_record("intent-1") == authority
    with pytest.raises(StateStoreError) as conflict:
        store.authority.put_authority_record(
            AuthorityRecord(
                record_key="intent-1",
                kind="test-only",
                payload={"effect": "changed"},
                updated_at=authority.updated_at,
            )
        )
    assert conflict.value.code == "state_record_conflict"


def test_authority_claim_state_machine_is_restart_persistent_and_at_most_once(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    claim = HealingClaimRecord(
        observation_key="obs-claim",
        issue_number=629,
        correlation_id="run-629",
    )

    first = store.authority.claim_healing(claim)
    duplicate = store.authority.claim_healing(claim)
    finished = store.authority.finish_healing(
        claim.observation_key,
        status="attempted",
        outcome="suggested",
    )

    assert first.changed is True
    assert duplicate.changed is False
    assert finished.authority_epoch == first.authority_epoch + 1
    reopened = _store(tmp_path)
    persisted = reopened.authority.get_healing_claim(claim.observation_key)
    assert persisted is not None
    assert (persisted.status, persisted.outcome) == ("attempted", "suggested")
    with pytest.raises(StateStoreConflict):
        reopened.authority.finish_healing(
            claim.observation_key,
            status="abandoned",
            reason="cannot reopen a completed attempt",
        )


def test_parallel_claims_have_exactly_one_winner(tmp_path: Path) -> None:
    first_store = _store(tmp_path)
    second_store = _store(tmp_path)
    barrier = Barrier(2)

    def claim(store: SQLiteStateStore, correlation_id: str) -> bool:
        barrier.wait()
        return store.authority.claim_healing(
            HealingClaimRecord("obs-parallel", 629, correlation_id)
        ).changed

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda args: claim(*args),
                [(first_store, "run-a"), (second_store, "run-b")],
            )
        )

    assert sorted(results) == [False, True]
    persisted = _store(tmp_path).authority.get_healing_claim("obs-parallel")
    assert persisted is not None
    assert persisted.correlation_id in {"run-a", "run-b"}


def test_parallel_authority_writes_never_regress_witness_epoch(tmp_path: Path) -> None:
    first_store = _store(tmp_path)
    second_store = _store(tmp_path)
    barrier = Barrier(2)

    def claim(store: SQLiteStateStore, observation_key: str) -> int:
        barrier.wait()
        return store.authority.claim_healing(
            HealingClaimRecord(observation_key, 629, observation_key)
        ).authority_epoch

    with ThreadPoolExecutor(max_workers=2) as executor:
        epochs = list(
            executor.map(
                lambda args: claim(*args),
                [(first_store, "obs-a"), (second_store, "obs-b")],
            )
        )

    status = _store(tmp_path).status()
    assert sorted(epochs) == [1, 2]
    assert status.authority_epoch == status.witness_epoch == 2
    assert status.reconcile_required is False


def _budget_admission(
    *, admission_key: str = "budget-549", token_limit: int = 1_000
) -> WorkflowBudgetAdmissionRecord:
    return WorkflowBudgetAdmissionRecord(
        admission_key=admission_key,
        repository="example-owner/example",
        issue_number=549,
        invocation_digest="sha256:invocation",
        source_digest="sha256:source",
        policy_digest="sha256:policy",
        correlation_id="run-549",
        token_limit=token_limit,
    )


def _budget_attempt(
    attempt_key: str,
    *,
    admission_key: str = "budget-549",
    input_bound: int = 40,
    output_bound: int = 60,
) -> LLMBudgetAttemptRecord:
    return LLMBudgetAttemptRecord(
        attempt_key=attempt_key,
        admission_key=admission_key,
        logical_call_id="logical-549",
        provider="provider-a",
        model="model-a",
        task="planning",
        input_upper_bound=input_bound,
        output_upper_bound=output_bound,
        reserved_tokens=input_bound + output_bound,
    )


def test_workflow_budget_admission_attempts_and_plan_binding_survive_restart(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    admission = _budget_admission()

    assert store.authority.put_budget_admission(admission).changed is True
    assert store.authority.put_budget_admission(admission).changed is False
    assert (
        store.authority.bind_budget_plan(
            admission.admission_key, plan_contract_hash="sha256:plan", plan_comment_id=17
        ).changed
        is True
    )
    assert (
        store.authority.bind_budget_plan(
            admission.admission_key, plan_contract_hash="sha256:plan", plan_comment_id=17
        ).changed
        is False
    )

    settled = _budget_attempt("attempt-settled")
    unknown = _budget_attempt("attempt-unknown", input_bound=30, output_bound=70)
    assert store.authority.reserve_budget_attempt(settled).changed is True
    assert store.authority.reserve_budget_attempt(settled).changed is False
    store.authority.settle_budget_attempt(
        settled.attempt_key,
        status="settled",
        actual_input_tokens=12,
        actual_output_tokens=8,
        outcome_code="usage_reported",
    )
    store.authority.reserve_budget_attempt(unknown)
    store.authority.settle_budget_attempt(
        unknown.attempt_key,
        status="unknown",
        actual_input_tokens=None,
        actual_output_tokens=None,
        outcome_code="transport_timeout",
    )

    reopened = _store(tmp_path)
    bound = reopened.authority.find_budget_admission(
        repository=admission.repository,
        issue_number=admission.issue_number,
        plan_contract_hash="sha256:plan",
        plan_comment_id=17,
    )
    assert bound is not None
    assert bound.admission_key == admission.admission_key
    assert bound.plan_comment_id == 17
    attempts = reopened.authority.list_budget_attempts(admission_key=admission.admission_key)
    assert [(row.status, row.outcome_code) for row in attempts] == [
        ("settled", "usage_reported"),
        ("unknown", "transport_timeout"),
    ]
    assert attempts[0].actual_input_tokens == 12
    assert attempts[1].reserved_tokens == 100

    replacement = _budget_admission(admission_key="budget-549-replan")
    reopened.authority.put_budget_admission(replacement)
    reopened.authority.bind_budget_plan(
        replacement.admission_key,
        plan_contract_hash="sha256:plan",
        plan_comment_id=18,
    )
    rebound = reopened.authority.find_budget_admission(
        repository=replacement.repository,
        issue_number=replacement.issue_number,
        plan_contract_hash="sha256:plan",
        plan_comment_id=18,
    )
    assert rebound is not None
    assert rebound.admission_key == replacement.admission_key


def test_planning_clarification_uses_versioned_authority_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    admission = _budget_admission()
    store.authority.put_budget_admission(admission)
    now = datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)
    record = PlanningClarificationRecord(
        series_key="clarification-1",
        repository=admission.repository,
        issue_number=admission.issue_number,
        source_digest=admission.source_digest,
        admission_key=admission.admission_key,
        correlation_id=admission.correlation_id,
        status="waiting",
        round_number=1,
        deadline_at=now + timedelta(hours=1),
        rounds=({"round_number": 1},),
        created_at=now,
        updated_at=now,
    )
    store.authority.put_planning_clarification(record)
    assert (
        store.authority.find_active_planning_clarification(
            repository=record.repository, issue_number=record.issue_number
        )
        == record
    )

    answered = PlanningClarificationRecord(
        **{
            **record.__dict__,
            "status": "answered",
            "version": 2,
            "updated_at": now + timedelta(minutes=1),
        }
    )
    store.authority.put_planning_clarification(answered, expected_version=1)
    assert store.authority.get_planning_clarification(record.series_key) == answered
    with pytest.raises(StateStoreConflict):
        store.authority.put_planning_clarification(answered, expected_version=1)

    reopened = _store(tmp_path)
    assert (
        reopened.authority.find_latest_planning_clarification(
            repository=record.repository, issue_number=record.issue_number
        )
        == answered
    )


def test_workflow_budget_parallel_reservations_cannot_exceed_limit(tmp_path: Path) -> None:
    first_store = _store(tmp_path)
    second_store = _store(tmp_path)
    admission = _budget_admission(token_limit=100)
    first_store.authority.put_budget_admission(admission)
    barrier = Barrier(2)

    def reserve(store: SQLiteStateStore, attempt_key: str) -> str:
        barrier.wait()
        try:
            store.authority.reserve_budget_attempt(
                _budget_attempt(attempt_key, input_bound=30, output_bound=30)
            )
        except StateStoreError as exc:
            return exc.code
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda args: reserve(*args),
                [(first_store, "attempt-a"), (second_store, "attempt-b")],
            )
        )

    assert sorted(results) == ["reserved", "workflow_token_budget_exhausted"]
    assert len(_store(tmp_path).authority.list_budget_attempts()) == 1


def test_workflow_budget_refuses_invalid_settlement_and_immutable_rebinding(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    admission = _budget_admission(token_limit=200)
    store.authority.put_budget_admission(admission)
    store.authority.bind_budget_plan(
        admission.admission_key, plan_contract_hash="sha256:one", plan_comment_id=17
    )
    with pytest.raises(StateStoreConflict):
        store.authority.bind_budget_plan(
            admission.admission_key,
            plan_contract_hash="sha256:two",
            plan_comment_id=18,
        )

    attempt = _budget_attempt("attempt-bound", input_bound=20, output_bound=30)
    store.authority.reserve_budget_attempt(attempt)
    with pytest.raises(StateStoreError) as exceeded:
        store.authority.settle_budget_attempt(
            attempt.attempt_key,
            status="settled",
            actual_input_tokens=30,
            actual_output_tokens=30,
            outcome_code="usage_reported",
        )
    assert exceeded.value.code == "workflow_budget_bound_exceeded"
    assert store.authority.get_budget_attempt(attempt.attempt_key).status == "reserved"  # type: ignore[union-attr]


def test_operator_abandon_requires_reason_and_only_transitions_claimed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.authority.claim_healing(HealingClaimRecord("obs-abandon", 629, "run-629"))

    with pytest.raises(StateStoreError) as missing_reason:
        store.authority.finish_healing("obs-abandon", status="abandoned")
    assert missing_reason.value.code == "state_claim_reason_required"
    result = store.authority.finish_healing(
        "obs-abandon",
        status="abandoned",
        reason="operator reconciled external state",
    )
    assert result.changed is True
    abandoned = store.authority.get_healing_claim("obs-abandon")
    assert abandoned is not None
    assert abandoned.status == "abandoned"


def test_checkpoint_intent_and_lease_contracts_survive_restart(tmp_path: Path) -> None:
    store = _store(tmp_path)
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key="checkpoint-629",
        issue_number=629,
        correlation_id="run-629",
        workflow="implementation",
        boundary="round_2",
        repository="owner/repo",
        branch="samuel/issue-629",
        base_ref="main",
        head_sha="a" * 40,
        workspace_id="workspace-629",
        evaluation_subject={"head_sha": "a" * 40},
        resume_eligible=False,
        payload={"round": 2},
    )
    intent = OperationIntentRecord(
        intent_key="intent-629",
        operation="push",
        status="pending",
        issue_number=629,
        correlation_id="run-629",
        subject_key="samuel/issue-629:" + "a" * 40,
        payload={"expected_head": "a" * 40},
    )
    lease = AuthorityLeaseRecord(
        resource_key="workspace-629",
        owner_id="process-a",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        version=1,
    )

    store.authority.put_checkpoint(checkpoint)
    store.authority.put_intent(intent)
    store.authority.acquire_lease(lease)
    store.authority.finish_intent(
        intent.intent_key,
        status="unresolved",
        postcondition={"remote_head": ""},
    )
    reopened = _store(tmp_path)

    reopened_checkpoint = reopened.authority.get_checkpoint(checkpoint.checkpoint_key)
    reopened_intent = reopened.authority.get_intent(intent.intent_key)
    assert reopened_checkpoint == checkpoint
    assert reopened_checkpoint is not None
    assert reopened_checkpoint.resume_eligible is False
    assert reopened_intent is not None
    assert reopened_intent.status == "unresolved"
    assert reopened.authority.get_lease(lease.resource_key) == lease
    with pytest.raises(StateStoreConflict):
        reopened.authority.acquire_lease(lease)


def test_resume_queries_and_lease_release_are_restart_persistent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key="checkpoint-resume",
        issue_number=633,
        correlation_id="run-resume",
        workflow="implementation_finalization",
        boundary="push_pending",
        repository="owner/repo",
        branch="samuel/resume",
        base_ref="main",
        head_sha="b" * 40,
        workspace_id="workspace-resume",
        evaluation_subject={"head_sha": "b" * 40},
        resume_eligible=True,
        payload={"resume_status": "pending"},
    )
    intent = OperationIntentRecord(
        intent_key="intent-resume",
        operation="push",
        status="pending",
        issue_number=633,
        correlation_id="run-resume",
        subject_key="samuel/resume:" + "b" * 40,
        payload={"expected_head": "b" * 40},
    )
    lease = AuthorityLeaseRecord(
        resource_key="workspace-resume",
        owner_id="owner-a",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        version=1,
    )
    store.authority.put_checkpoint(checkpoint)
    store.authority.put_intent(intent)
    store.authority.acquire_lease(lease)

    reopened = _store(tmp_path)
    assert reopened.authority.list_checkpoints(resume_eligible=True) == [checkpoint]
    assert reopened.authority.list_checkpoints(resume_eligible=False) == []
    assert reopened.authority.list_intents(correlation_id="run-resume") == [intent]
    assert reopened.authority.list_intents(status="applied") == []
    released = reopened.authority.release_lease(
        lease.resource_key,
        owner_id=lease.owner_id,
        expected_version=lease.version,
    )
    assert released.changed is True
    assert _store(tmp_path).authority.get_lease(lease.resource_key) is None

    with pytest.raises(StateStoreConflict):
        reopened.authority.release_lease(
            lease.resource_key,
            owner_id=lease.owner_id,
            expected_version=lease.version,
        )


def test_witness_rollback_enters_visible_reconcile_and_blocks_normal_claim_authority(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.authority.claim_healing(HealingClaimRecord("obs-1", 629, "run-629"))
    witness = json.loads(store.authority_witness_path.read_text(encoding="utf-8"))
    witness["authority_epoch"] = 0
    store.authority_witness_path.write_text(json.dumps(witness), encoding="utf-8")

    reopened = _store(tmp_path)
    status = reopened.status()
    assert status.reconcile_required is True
    assert status.reconcile_reason == "state_authority_witness_lag"
    assert "resume_enabled" not in status.as_dict()["authority"]


def test_foreign_witness_uuid_enters_visible_reconcile_after_restart(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.authority.claim_healing(HealingClaimRecord("obs-foreign", 666, "run-foreign"))
    witness = json.loads(store.authority_witness_path.read_text(encoding="utf-8"))
    witness["instance_uuid"] = "00000000-0000-4000-8000-000000000001"
    store.authority_witness_path.write_text(json.dumps(witness), encoding="utf-8")

    reopened = _store(tmp_path)
    status = reopened.status()

    assert status.reconcile_required is True
    assert status.reconcile_reason == "state_authority_instance_mismatch"
    assert status.witness_epoch == -1
    assert "resume_enabled" not in status.as_dict()["authority"]


def test_witness_write_failure_commits_claim_but_raises_before_external_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)

    def fail_witness(_instance_uuid: str, _authority_epoch: int) -> None:
        raise StateStoreError("state_authority_witness_write_failed", "witness failed")

    monkeypatch.setattr(store, "_write_authority_witness", fail_witness)
    with pytest.raises(StateStoreError) as failed:
        store.authority.claim_healing(HealingClaimRecord("obs-fail", 629, "run-629"))
    assert failed.value.code == "state_authority_witness_write_failed"
    assert store.authority.get_healing_claim("obs-fail") is not None

    reopened = _store(tmp_path)
    assert reopened.status().reconcile_required is True


def test_audit_epoch_is_supplemental_and_can_only_force_reconcile(tmp_path: Path) -> None:
    store = _store(tmp_path)
    audit = tmp_path / "agent.jsonl"
    audit.write_text(
        "not-json\n"
        + json.dumps({"payload": {"authority_epoch": 7, "secret": "not-inspected"}})
        + "\n",
        encoding="utf-8",
    )

    maximum = audit_authority_high_watermark([audit])
    store.compare_audit_authority_epoch(maximum)

    assert maximum == 7
    assert store.status().reconcile_required is True
    assert store.status().reconcile_reason == "state_authority_audit_ahead"
    assert _store(tmp_path).status().reconcile_reason == "state_authority_audit_ahead"


def test_audit_epoch_rejects_boolean_and_negative_legacy_values(tmp_path: Path) -> None:
    audit = tmp_path / "agent.jsonl"
    audit.write_text(
        "\n".join(
            [
                json.dumps({"payload": {"authority_epoch": True}}),
                json.dumps({"payload": {"authority_epoch": -1}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert audit_authority_high_watermark([audit]) == 0


def test_restore_creates_new_authority_line_and_requires_complete_reconcile(
    tmp_path: Path,
) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    source.authority.claim_healing(HealingClaimRecord("source-claim", 666, "source-run"))
    backup = source.backup(tmp_path / "source-backup.sqlite3")

    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    live.authority.claim_healing(HealingClaimRecord("discarded-live-claim", 1, "live-run"))
    old_status = live.status()
    operation = live.restore(backup, audit_epoch=old_status.authority_epoch + 7)

    restored = live.status()
    assert operation.restored_from_uuid == source.status().authority_instance
    assert operation.instance_uuid not in {
        source.status().authority_instance,
        old_status.authority_instance,
    }
    assert operation.pre_restore_epoch_highwater == old_status.authority_epoch + 7
    assert restored.authority_epoch == operation.pre_restore_epoch_highwater + 1
    assert restored.authority_epoch == restored.witness_epoch
    assert restored.reconcile_required is True
    assert restored.active_restore_operation == operation.operation_id
    assert restored.restore_scan_status == "pending"
    assert [row.observation_key for row in live.authority.list_healing_claims()] == ["source-claim"]

    live.authority.replace_reconcile_scan(
        operation.operation_id,
        [
            ReconcileEntryRecord(
                operation.operation_id,
                "inventory",
                "complete",
                "verified_effect",
                "inventory_completed",
            ),
            ReconcileEntryRecord(
                operation.operation_id,
                "healing_claim",
                "source-claim",
                "unresolved",
                "claimed",
            ),
        ],
    )
    with pytest.raises(StateStoreError) as unresolved:
        live.authority.complete_reconcile(operation.operation_id, audit_epoch=20)
    assert unresolved.value.code == "state_reconcile_unresolved"

    live.authority.classify_reconcile_entry(
        operation.operation_id,
        "healing_claim",
        "source-claim",
        classification="abandoned",
        reason="operator verified no external attempt",
    )
    completed = live.authority.complete_reconcile(operation.operation_id, audit_epoch=20)
    assert completed.authority_epoch == 21
    assert live.status().reconcile_required is False
    assert live.list_restore_operations()[-1].status == "completed"


def test_restore_migrates_stage_5b_schema_v5_to_current_schema(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "stage-5b.sqlite3")
    connection = sqlite3.connect(backup)
    connection.executescript(
        """
        DROP TABLE retention_category_states;
        DROP TABLE retention_executions;
        DROP TABLE llm_budget_attempts;
        DROP TABLE workflow_budget_admissions;
        DROP TABLE planning_clarifications;
        DROP TABLE identity_tokens;
        DROP TABLE identity_sessions;
        DROP TABLE identity_principal_roles;
        DROP TABLE identity_principals;
        DROP TABLE identity_metadata;
        DELETE FROM schema_migrations WHERE version IN (6, 7, 8, 9, 10);
        PRAGMA user_version = 5;
        """
    )
    connection.commit()
    connection.close()
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)

    operation = live.restore(backup)

    assert operation.status == "reconcile_required"
    assert live.status().schema_version == 10
    assert "retention_category_states" in live.status().tables
    assert "retention_executions" in live.status().tables


def test_restore_preserves_budget_admission_and_unknown_reservation(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    admission = _budget_admission(token_limit=500)
    source.authority.put_budget_admission(admission)
    attempt = _budget_attempt("attempt-before-restore")
    source.authority.reserve_budget_attempt(attempt)
    source.authority.settle_budget_attempt(
        attempt.attempt_key,
        status="unknown",
        actual_input_tokens=None,
        actual_output_tokens=None,
        outcome_code="lost_response",
    )
    backup = source.backup(tmp_path / "budget.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)

    operation = live.restore(backup)

    assert operation.status == "reconcile_required"
    assert live.authority.get_budget_admission(admission.admission_key) is not None
    restored = live.authority.get_budget_attempt(attempt.attempt_key)
    assert restored is not None
    assert restored.status == "unknown"
    assert restored.reserved_tokens == attempt.reserved_tokens


def test_restore_failure_leaves_sentinel_and_restart_fail_closed(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not sqlite")

    with pytest.raises(StateStoreError):
        live.restore(corrupt)

    assert live.restore_sentinel_path.is_file()
    reopened = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    status = reopened.status()
    assert status.reconcile_required is True
    assert status.reconcile_reason == "state_restore_interrupted"
    assert status.restore_sentinel_present is True


def test_restore_swap_failure_is_superseded_without_losing_interrupted_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    original_replace = os.replace

    def fail_database_swap(source_path: object, destination_path: object) -> None:
        if Path(destination_path) == live.path:
            raise OSError("simulated atomic switch failure")
        original_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", fail_database_swap)
    with pytest.raises(StateStoreError):
        live.restore(backup)

    sentinel = json.loads(live.restore_sentinel_path.read_text(encoding="utf-8"))
    interrupted_id = sentinel["operation_id"]
    monkeypatch.setattr(os, "replace", original_replace)
    superseding = live.restore(
        backup,
        supersede_operation_id=interrupted_id,
        reason="operator confirmed interrupted atomic switch",
    )

    operations = {row.operation_id: row for row in live.list_restore_operations()}
    assert operations[interrupted_id].status == "superseded"
    assert superseding.supersedes_operation_id == interrupted_id
    assert live.status().reconcile_required is True


def test_restore_witness_failure_leaves_new_line_blocked_on_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)

    def fail_witness(*, lifecycle: bool = True) -> None:
        raise StateStoreError("state_authority_witness_write_failed", "witness failed")

    monkeypatch.setattr(live, "_sync_authority_witness", fail_witness)
    with pytest.raises(StateStoreError) as failed:
        live.restore(backup)
    assert failed.value.code == "state_authority_witness_write_failed"
    assert live.restore_sentinel_path.is_file()

    reopened = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    assert reopened.status().reconcile_required is True
    assert reopened.status().restore_sentinel_present is True
    assert reopened.list_restore_operations()[-1].status == "reconcile_required"


def test_interrupted_supersession_chains_both_open_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    first = live.restore(backup)
    original_replace = os.replace

    def fail_database_swap(source_path: object, destination_path: object) -> None:
        if Path(destination_path) == live.path:
            raise OSError("simulated supersession switch failure")
        original_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", fail_database_swap)
    with pytest.raises(StateStoreError):
        live.restore(
            backup,
            supersede_operation_id=first.operation_id,
            reason="operator started supersession",
        )
    interrupted_id = json.loads(live.restore_sentinel_path.read_text(encoding="utf-8"))[
        "operation_id"
    ]

    monkeypatch.setattr(os, "replace", original_replace)
    final = live.restore(
        backup,
        supersede_operation_id=interrupted_id,
        reason="operator superseded interrupted supersession",
    )
    operations = {row.operation_id: row for row in live.list_restore_operations()}

    assert operations[first.operation_id].status == "superseded"
    assert operations[interrupted_id].status == "superseded"
    assert operations[interrupted_id].supersedes_operation_id == first.operation_id
    assert final.supersedes_operation_id == interrupted_id


def test_restore_rejects_newer_schema_and_keeps_fail_closed_sentinel(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "future.sqlite3")
    with sqlite3.connect(backup) as connection:
        connection.execute("PRAGMA user_version = 99")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)

    with pytest.raises(StateStoreError) as failed:
        live.restore(backup)
    assert failed.value.code == "state_schema_too_new"
    assert live.restore_sentinel_path.is_file()


def test_restore_refuses_symlinked_sentinel_without_reading_target(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    target = tmp_path / "foreign-sentinel.json"
    target.write_text('{"operation_id":"foreign"}', encoding="utf-8")
    live.restore_sentinel_path.symlink_to(target)

    with pytest.raises(StateStoreError) as failed:
        live.restore(backup, supersede_operation_id="foreign", reason="must not follow link")
    assert failed.value.code == "state_restore_sentinel_unsafe"
    assert live.status().restore_sentinel_present is True


def test_restore_refuses_symlinked_backup_source(tmp_path: Path) -> None:
    live = SQLiteStateStore(tmp_path / "live")
    source = SQLiteStateStore(tmp_path / "source")
    backup = source.backup(tmp_path / "backup.sqlite3")
    link = tmp_path / "backup-link.sqlite3"
    link.symlink_to(backup)

    with pytest.raises(StateStoreError) as failed:
        live.restore(link)

    assert failed.value.code == "state_restore_source_invalid"
    assert live.status().reconcile_required is False


def test_interrupted_restore_sentinel_blocks_authority_changes(tmp_path: Path) -> None:
    live = SQLiteStateStore(tmp_path / "live")
    source = SQLiteStateStore(tmp_path / "source")
    backup = source.backup(tmp_path / "backup.sqlite3")
    original_sync = live._sync_authority_witness

    def fail_witness(*, lifecycle: bool = True) -> None:
        raise StateStoreError(
            "state_authority_witness_write_failed",
            "simulated witness failure",
        )

    live._sync_authority_witness = fail_witness  # type: ignore[method-assign]
    with pytest.raises(StateStoreError):
        live.restore(backup)
    live._sync_authority_witness = original_sync  # type: ignore[method-assign]

    operation = live.list_restore_operations()[-1]
    inventory = ReconcileEntryRecord(
        operation_id=operation.operation_id,
        object_type="inventory",
        object_key="complete",
        classification="verified_effect",
        reason="inventory_completed",
    )
    with pytest.raises(StateStoreError) as scan_failed:
        live.authority.replace_reconcile_scan(operation.operation_id, [inventory])
    assert scan_failed.value.code == "state_restore_interrupted"

    with pytest.raises(StateStoreError) as complete_failed:
        live.authority.complete_reconcile(operation.operation_id)
    assert complete_failed.value.code == "state_restore_interrupted"


def test_open_restore_requires_explicit_supersession_and_fresh_scan(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    first = live.restore(backup)
    live.authority.replace_reconcile_scan(
        first.operation_id,
        [
            ReconcileEntryRecord(
                first.operation_id,
                "inventory",
                "complete",
                "verified_effect",
                "first scan",
            )
        ],
        scan_error_code="state_reconcile_scm_unavailable",
    )

    with pytest.raises(StateStoreError) as open_restore:
        live.restore(backup)
    assert open_restore.value.code == "state_restore_reconcile_open"
    with pytest.raises(StateStoreError) as no_reason:
        live.restore(backup, supersede_operation_id=first.operation_id)
    assert no_reason.value.code == "state_restore_supersession_reason_required"

    second = live.restore(
        backup,
        supersede_operation_id=first.operation_id,
        reason="operator selected a newer known-good backup",
    )
    operations = {row.operation_id: row for row in live.list_restore_operations()}
    assert operations[first.operation_id].status == "superseded"
    assert second.supersedes_operation_id == first.operation_id
    assert second.scan_status == "pending"
    assert live.authority.list_reconcile_entries(second.operation_id) == []

    live.authority.replace_reconcile_scan(
        second.operation_id,
        [],
        scan_error_code="state_reconcile_scm_unavailable",
    )
    with pytest.raises(StateStoreError) as scan_failed:
        live.authority.classify_reconcile_entry(
            second.operation_id,
            "inventory",
            "complete",
            classification="abandoned",
            reason="must not bypass scan failure",
        )
    assert scan_failed.value.code == "state_reconcile_scan_incomplete"


def test_restore_exclusive_lock_waits_for_real_process_reader(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    backup = source.backup(tmp_path / "source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo, timeout=5)
    assert live.lifecycle_lock_path != live.data_dir / AUTHORITY_WITNESS_LOCK_FILENAME

    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_state_reader,
        args=(str(live.data_dir), str(mountinfo), ready, release),
    )
    process.start()
    assert ready.wait(timeout=5)
    with ThreadPoolExecutor(max_workers=1) as pool:
        started = time.monotonic()
        future = pool.submit(live.restore, backup)
        time.sleep(0.2)
        assert future.done() is False
        release.set()
        operation = future.result(timeout=10)
    process.join(timeout=5)
    assert process.exitcode == 0
    assert time.monotonic() - started >= 0.2
    assert operation.status == "reconcile_required"


def test_restore_exclusive_lock_waits_for_real_process_authority_writer(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo, timeout=5)
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    completed = context.Event()

    with live._lifecycle_lock(exclusive=True):
        process = context.Process(
            target=_write_authority_after_signal,
            args=(str(live.data_dir), str(mountinfo), ready, completed),
        )
        process.start()
        assert ready.wait(timeout=5)
        time.sleep(0.2)
        assert completed.is_set() is False

    process.join(timeout=5)
    assert process.exitcode == 0
    assert completed.is_set() is True
    assert live.authority.get_healing_claim("obs-process-writer") is not None


def test_dump_contains_counts_but_no_payloads_or_secrets(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.observations.put_observation(
        _observation(payload={"SCM_TOKEN": "top-secret", "candidate": "private code"})
    )

    dump = store.dump()
    serialized = json.dumps(dump, sort_keys=True)

    assert dump["format"] == "samuel-state-dump.v1"
    assert dump["payloads_included"] is False
    assert dump["row_counts"]["observations"] == 1
    assert "top-secret" not in serialized
    assert "private code" not in serialized


@pytest.mark.parametrize("filesystem", ["nfs", "nfs4", "cifs", "smb3"])
def test_network_filesystems_are_rejected(tmp_path: Path, filesystem: str) -> None:
    with pytest.raises(StateStoreError) as exc_info:
        _store(tmp_path, filesystem=filesystem)
    assert exc_info.value.code == "state_filesystem_remote"
    assert not (tmp_path / "data" / DATABASE_FILENAME).exists()


def test_unknown_or_unreadable_filesystem_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(StateStoreError) as unknown:
        _store(tmp_path, filesystem="mysteryfs")
    assert unknown.value.code == "state_filesystem_unknown"

    with pytest.raises(StateStoreError) as missing:
        SQLiteStateStore(tmp_path / "data", mountinfo_path=tmp_path / "missing")
    assert missing.value.code == "state_filesystem_unknown"


def test_newer_unversioned_and_corrupt_schemas_fail_closed(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / DATABASE_FILENAME
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 11")
    connection.close()
    with pytest.raises(StateStoreError) as newer:
        SQLiteStateStore(data_dir, mountinfo_path=mountinfo)
    assert newer.value.code == "state_schema_too_new"

    path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE foreign_table(value TEXT)")
    connection.close()
    with pytest.raises(StateStoreError) as unversioned:
        SQLiteStateStore(data_dir, mountinfo_path=mountinfo)
    assert unversioned.value.code == "state_schema_unversioned"

    path.unlink()
    path.write_bytes(b"not a sqlite database")
    with pytest.raises(StateStoreError) as corrupt:
        SQLiteStateStore(data_dir, mountinfo_path=mountinfo)
    assert corrupt.value.code == "state_corrupt"


def test_database_symlink_is_rejected_before_sqlite_access(tmp_path: Path) -> None:
    mountinfo = _mountinfo(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = tmp_path / "outside.sqlite3"
    target.touch()
    (data_dir / DATABASE_FILENAME).symlink_to(target)

    with pytest.raises(StateStoreError) as exc_info:
        SQLiteStateStore(data_dir, mountinfo_path=mountinfo)

    assert exc_info.value.code == "state_path_unsafe"


def test_locked_and_readonly_errors_have_stable_redacted_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path, timeout=0.01)
    blocker = sqlite3.connect(store.path)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(StateStoreError) as locked:
            store.observations.put_observation(_observation())
    finally:
        blocker.rollback()
        blocker.close()
    assert locked.value.code == "state_locked"

    def readonly(*_args: object, **_kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError("attempt to write a readonly database SECRET")

    monkeypatch.setattr(sqlite3, "connect", readonly)
    with pytest.raises(StateStoreError) as readonly_error:
        store.status()
    assert readonly_error.value.code == "state_readonly"
    assert "SECRET" not in readonly_error.value.safe_message


def test_backup_api_copies_active_wal_database_and_refuses_overwrite(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.observations.put_observation(_observation())
    destination = tmp_path / "backups" / "state.sqlite3"

    result = store.backup(destination)

    assert result == destination
    assert destination.stat().st_mode & 0o777 == 0o600
    backup = sqlite3.connect(destination)
    try:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert backup.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    finally:
        backup.close()
    with pytest.raises(StateStoreError) as exists:
        store.backup(destination)
    assert exists.value.code == "state_backup_exists"


def test_managed_backup_registry_is_append_only_and_exposes_no_delete(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = ManagedBackupRecord(
        backup_id="backup-1",
        path=tmp_path / "managed" / "state.sqlite3",
        digest="sha256:" + "a" * 64,
        instance_uuid=store.status().authority_instance,
        authority_epoch=store.status().authority_epoch,
        created_at=datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc),
    )

    assert store.retention.register_managed_backup(record) is True
    assert store.retention.register_managed_backup(record) is False
    assert store.retention.list_managed_backups() == [record]
    assert store.retention.emergency_stop() is True
    assert not hasattr(store.retention, "delete")

    conflicting = ManagedBackupRecord(
        backup_id=record.backup_id,
        path=record.path,
        digest="sha256:" + "b" * 64,
        instance_uuid=record.instance_uuid,
        authority_epoch=record.authority_epoch,
        created_at=record.created_at,
    )
    with pytest.raises(StateStoreConflict):
        store.retention.register_managed_backup(conflicting)


def test_projection_failure_is_non_blocking_health_state_and_clears_after_retry(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path, timeout=0.01)
    projection = RunProjectionRecord(
        projection_key="run-health",
        issue_number=627,
        correlation_id="corr-health",
        series="workflow-run.v1",
        status="running",
        payload={"events": []},
    )
    blocker = sqlite3.connect(store.path)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(StateStoreError) as failure:
            store.projections.upsert_projection(projection)
    finally:
        blocker.rollback()
        blocker.close()
    assert failure.value.code == "state_locked"
    assert store.status().projection_healthy is False
    assert store.status().projection_error_code == "state_locked"

    store.projections.upsert_projection(projection)
    assert store.status().projection_healthy is True
    assert store.status().projection_error_code is None


def test_payload_and_timestamp_validation_fail_before_write(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(StateStoreError) as payload:
        store.observations.put_observation(_observation(payload={"bad": float("nan")}))
    assert payload.value.code == "state_payload_invalid"

    with pytest.raises(StateStoreError) as timestamp:
        store.observations.put_observation(
            _observation(observation_key="obs-naive", observed_at=datetime(2026, 8, 29))
        )
    assert timestamp.value.code == "state_timestamp_invalid"
