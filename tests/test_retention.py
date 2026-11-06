from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.retention import RetentionError, RetentionPolicyConfig
from samuel.core.state import (
    ManagedBackupRecord,
    ObservationRecord,
    RunProjectionRecord,
    ScoreDerivationRecord,
    StateStoreError,
)
from samuel.slices.privacy.retention import (
    RetentionCoordinator,
    _row_protection,
    create_managed_backup,
)

ROOT = Path(__file__).resolve().parents[1]


def test_applied_provider_dispatch_remains_retention_protected() -> None:
    assert (
        _row_protection(
            "operation_intents",
            {"operation": "provider_dispatch.v1", "status": "applied"},
        )
        == "provider_verification_or_reconcile_relevant"
    )


def _document() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / "config" / "privacy.json").read_text(encoding="utf-8")),
    )


def _policy(tmp_path: Path, document: dict[str, Any] | None = None) -> RetentionPolicyConfig:
    config = tmp_path / "privacy.json"
    config.write_text(json.dumps(document or _document()), encoding="utf-8")
    return RetentionPolicyConfig.load(config, project_root=tmp_path)


def _enforcement_policy(tmp_path: Path) -> RetentionPolicyConfig:
    document = _document()
    document["retention"]["categories"]["score_derivations"]["mode"] = "enforce"
    return _policy(tmp_path, document)


def _put_derivation(
    store: SQLiteStateStore,
    suffix: str,
    *,
    derived_at: datetime,
) -> str:
    observation_key = "sha256:" + suffix * 64
    score_key = "sha256:" + chr(ord(suffix) + 1) * 64
    store.observations.put_observation(
        ObservationRecord(
            observation_key=observation_key,
            subject_key="sha256:" + "d" * 64,
            evidence_digest="sha256:" + "e" * 64,
            observation_schema="bound.v2",
            issue_number=673,
            payload={},
            observed_at=derived_at,
        )
    )
    store.observations.put_derivation(
        ScoreDerivationRecord(
            score_key=score_key,
            observation_key=observation_key,
            scoring_policy_version="retention-canary.v1",
            scoring_policy_digest="sha256:" + "f" * 64,
            formula_version="canary.v1",
            issue_number=673,
            score=1.0,
            payload={},
            derived_at=derived_at,
        )
    )
    return score_key


def test_shipped_catalog_is_complete_and_dry_run_is_non_deleting(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    policy = _policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )
    before = store.dump()

    report = coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))

    assert coordinator.validate_catalog() == []
    assert len(store.retention.catalog()) == 26
    assert len(report["categories"]) == 29
    assert report["findings"] == []
    assert report["delete_capability_present"] is True
    assert report["active_enforcement_categories"] == []
    assert report["authorized_enforcement_categories"] == []
    assert {row["requested_mode"] for row in report["categories"]} == {"report_only"}
    assert report["retention_emergency_stop"] is True
    assert report["future_enforcement_blocked"] is True
    assert store.dump() == before
    status = coordinator.status()
    assert status["retention_emergency_stop"] is True
    assert status["future_enforcement_blocked"] is True
    assert status["pending_review_count"] == 29
    assert status["last_execution"] is None
    assert all(row["category_digest"].startswith("sha256:") for row in status["categories"])


def test_unknown_schema_object_is_visible_and_unknown_config_category_blocks(
    tmp_path: Path,
) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    connection = sqlite3.connect(store.path)
    connection.execute("CREATE TABLE future_runtime_state(id TEXT, updated_at TEXT)")
    connection.commit()
    connection.close()
    coordinator = RetentionCoordinator(
        policy=_policy(tmp_path),
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )

    findings = coordinator.validate_catalog()
    assert findings == [
        {
            "code": "retention_catalog_source_unconfigured",
            "category": "future_runtime_state",
            "detail": "runtime-state table has no retention category",
        }
    ]

    document = _document()
    document["retention"]["categories"]["invented"] = deepcopy(
        document["retention"]["categories"]["observations"]
    )
    policy = _policy(tmp_path, document)
    with pytest.raises(RetentionError) as error:
        RetentionCoordinator(
            policy=policy,
            state=store.retention,
            authority=store.authority,
            execution=store.retention_execution,
        ).validate_catalog()
    assert error.value.code == "retention_category_unknown"

    invalid_external = _document()
    invalid_external["retention"]["categories"]["workspaces"]["source"] = "other_registry"
    with pytest.raises(RetentionError) as external_error:
        RetentionCoordinator(
            policy=_policy(tmp_path, invalid_external),
            state=store.retention,
            authority=store.authority,
            execution=store.retention_execution,
        ).validate_catalog()
    assert external_error.value.code == "retention_external_contract_invalid"


def test_approval_is_bound_to_category_and_profile_digests(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    policy = _policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )
    coordinator.approve("observations", reason="reviewed for the active role")
    report = coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    observations = next(row for row in report["categories"] if row["category"] == "observations")
    assert observations["effective_mode"] == "report_only"

    unrelated = _document()
    unrelated["retention"]["categories"]["run_projections"]["period"] = "P120D"
    unrelated_policy = _policy(tmp_path, unrelated)
    unrelated_report = RetentionCoordinator(
        policy=unrelated_policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    ).dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    observations = next(
        row for row in unrelated_report["categories"] if row["category"] == "observations"
    )
    assert observations["effective_mode"] == "report_only"

    changed = deepcopy(unrelated)
    changed["retention"]["categories"]["observations"]["period"] = "P2Y"
    changed_policy = _policy(tmp_path, changed)
    changed_report = RetentionCoordinator(
        policy=changed_policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    ).dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    observations = next(
        row for row in changed_report["categories"] if row["category"] == "observations"
    )
    assert observations["effective_mode"] == "report_only_pending_review"


def test_profile_minimum_and_retired_anonymize_setting_fail_closed(tmp_path: Path) -> None:
    document = _document()
    document["retention"]["profiles"]["eu_operational"]["minimums"] = {"observations": "P1Y"}
    document["retention"]["categories"]["observations"]["period"] = "P6M"
    with pytest.raises(RetentionError) as too_short:
        _policy(tmp_path, document)
    assert too_short.value.code == "retention_period_below_profile_minimum"

    legacy = _document()
    legacy["retention"]["pii_anonymize_after_days"] = 30
    with pytest.raises(RetentionError) as retired:
        _policy(tmp_path, legacy)
    assert retired.value.code == "retention_legacy_anonymize_setting"


def test_inactive_profiles_and_managed_backup_path_are_validated(tmp_path: Path) -> None:
    invalid_profile = _document()
    invalid_profile["retention"]["profiles"]["unused"] = {
        "role": "operator",
        "minimums": {"unknown_category": "P1Y"},
    }
    with pytest.raises(RetentionError) as profile_error:
        _policy(tmp_path, invalid_profile)
    assert profile_error.value.code == "retention_profile_category_unknown"

    blank_backup = _document()
    blank_backup["retention"]["managed_backup_dir"] = "  "
    with pytest.raises(RetentionError) as backup_error:
        _policy(tmp_path, blank_backup)
    assert backup_error.value.code == "retention_managed_backup_dir_invalid"

    unknown_field = _document()
    unknown_field["retention"]["categories"]["observations"]["silent_default"] = True
    with pytest.raises(RetentionError) as field_error:
        _policy(tmp_path, unknown_field)
    assert field_error.value.code == "retention_category_field_unknown"

    unknown_anchor = _document()
    unknown_anchor["retention"]["categories"]["observations"]["anchor"] = "missing_column"
    with pytest.raises(RetentionError) as anchor_error:
        _policy(tmp_path, unknown_anchor)
    assert anchor_error.value.code == "retention_anchor_unknown"

    non_allowlisted = _document()
    non_allowlisted["retention"]["categories"]["observations"]["mode"] = "enforce"
    with pytest.raises(RetentionError) as allowlist_error:
        _policy(tmp_path, non_allowlisted)
    assert allowlist_error.value.code == "retention_execution_category_not_allowlisted"


def test_calendar_period_overflow_fails_with_safe_retention_error() -> None:
    from samuel.core.retention import CalendarPeriod

    with pytest.raises(RetentionError) as error:
        CalendarPeriod.parse("P9999Y").subtract_from(datetime(2026, 8, 30, tzinfo=timezone.utc))
    assert error.value.code == "retention_period_invalid"


def test_audit_uses_last_event_timestamp_and_protects_ambiguous_files(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    old = tmp_path / "agent_2025.jsonl"
    old.write_text(
        json.dumps({"ts": "2025-01-01T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    partial = tmp_path / "agent_partial.jsonl"
    partial.write_text(
        json.dumps({"ts": "2025-01-01T00:00:00Z"}) + "\n{",
        encoding="utf-8",
    )
    empty = tmp_path / "agent_empty.jsonl"
    empty.write_text("", encoding="utf-8")
    out_of_order = tmp_path / "agent_out_of_order.jsonl"
    out_of_order.write_text(
        json.dumps({"ts": "2026-08-01T00:00:00Z"})
        + "\n"
        + json.dumps({"ts": "2025-01-02T00:00:00Z"})
        + "\n",
        encoding="utf-8",
    )
    report = RetentionCoordinator(
        policy=_policy(tmp_path),
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
        audit_files=[old, partial, empty, out_of_order, tmp_path / "missing.jsonl"],
    ).dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))

    audit = next(row for row in report["categories"] if row["category"] == "audit_logs")
    assert audit["candidate_count"] == 2
    assert audit["protected_count"] == 3
    assert audit["protection_counts"] == {
        "corrupt_or_partial": 1,
        "empty": 1,
        "unreadable": 1,
    }


def test_run_projection_retention_never_selects_non_terminal_state(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    old = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for key, status in (("active-run", "running"), ("terminal-run", "blocked")):
        store.projections.upsert_projection(
            RunProjectionRecord(
                projection_key=key,
                issue_number=672,
                correlation_id=key,
                series="workflow-run.v1",
                status=status,
                payload={"schema": "workflow-run.v1", "events": []},
                updated_at=old,
            )
        )

    report = RetentionCoordinator(
        policy=_policy(tmp_path),
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    ).dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    projections = next(row for row in report["categories"] if row["category"] == "run_projections")

    assert projections["candidate_count"] == 1
    assert projections["protected_count"] == 1
    assert projections["protection_counts"] == {"non_terminal_never": 1}
    assert "non_terminal_never" in projections["protections"]


def test_managed_backup_uses_backup_api_and_registry(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    policy = _policy(tmp_path)

    record = create_managed_backup(
        policy=policy,
        diagnostics=store,
        state=store.retention,
        at=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
    )

    assert record.path.parent == tmp_path / "data" / "backups"
    assert record.path.is_file()
    assert store.retention.list_managed_backups() == [record]
    assert record.digest.startswith("sha256:")


def test_open_restore_digest_pins_managed_backup(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    policy = _policy(tmp_path)
    policy.managed_backup_dir.mkdir(parents=True)
    path = policy.managed_backup_dir / "old.sqlite3"
    path.write_bytes(b"registered backup artifact")
    record = ManagedBackupRecord(
        backup_id="old-backup",
        path=path,
        digest="sha256:" + "d" * 64,
        instance_uuid=store.status().authority_instance,
        authority_epoch=0,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    store.retention.register_managed_backup(record)
    connection = sqlite3.connect(store.path)
    connection.execute(
        "INSERT INTO restore_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "restore-open",
            "reconcile_required",
            record.digest,
            record.instance_uuid,
            record.instance_uuid,
            0,
            None,
            "operator restore",
            "pending",
            None,
            "2026-08-01T00:00:00+00:00",
            None,
        ),
    )
    connection.commit()
    connection.close()

    report = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    ).dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    backups = next(row for row in report["categories"] if row["category"] == "managed_backups")

    assert backups["candidate_count"] == 0
    assert backups["protection_counts"] == {"open_restore_digest_pin": 1}


def test_reconcile_entries_are_protected_only_while_restore_is_open(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    instance = store.status().authority_instance
    connection = sqlite3.connect(store.path)
    for operation_id, status in (
        ("restore-open", "reconcile_required"),
        ("restore-done", "completed"),
    ):
        connection.execute(
            "INSERT INTO restore_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                status,
                "sha256:" + operation_id[-4:] * 16,
                instance,
                instance,
                0,
                None,
                "operator restore",
                "completed",
                None,
                "2024-01-01T00:00:00+00:00",
                "2024-01-01T00:00:00+00:00" if status == "completed" else None,
            ),
        )
        connection.execute(
            "INSERT INTO reconcile_entries VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                "intent",
                operation_id,
                "verified_effect",
                "verified",
                "{}",
                "2024-01-01T00:00:00+00:00",
            ),
        )
    connection.commit()
    connection.close()

    report = RetentionCoordinator(
        policy=_policy(tmp_path),
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    ).dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    entries = next(row for row in report["categories"] if row["category"] == "reconcile_entries")

    assert entries["candidate_count"] == 1
    assert entries["protection_counts"] == {"open_restore_never": 1}


def test_score_derivation_canary_is_bound_atomic_restart_safe_and_idempotent(
    tmp_path: Path,
) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    old_key = _put_derivation(
        store,
        "a",
        derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    _put_derivation(
        store,
        "b",
        derived_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )
    report = coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    category = next(row for row in report["categories"] if row["category"] == "score_derivations")
    assert category["effective_mode"] == "report_only_pending_review"
    assert category["candidate_object_ids"] == [old_key]
    cutoff = datetime.fromisoformat(category["cutoff_utc"])
    plan_digest = category["plan_digest"]

    coordinator.approve("score_derivations", reason="reviewed canary category")
    coordinator.activate(
        "score_derivations",
        plan_digest=plan_digest,
        cutoff_utc=cutoff,
        reason="activate exact canary plan",
    )
    stopped_report = coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))
    assert stopped_report["authorized_enforcement_categories"] == ["score_derivations"]
    assert stopped_report["active_enforcement_categories"] == []
    coordinator.set_emergency_stop(False, reason="operator starts canary drill")

    reopened = SQLiteStateStore(tmp_path / "state")
    restarted = RetentionCoordinator(
        policy=policy,
        state=reopened.retention,
        authority=reopened.authority,
        execution=reopened.retention_execution,
    )
    first = restarted.execute(
        "score_derivations",
        plan_digest=plan_digest,
        cutoff_utc=cutoff,
        reason="execute synthetic canary",
    )
    repeat = restarted.execute(
        "score_derivations",
        plan_digest=plan_digest,
        cutoff_utc=cutoff,
        reason="execute synthetic canary",
    )

    assert first == repeat
    assert first["candidate_count"] == first["deleted_count"] == 1
    assert reopened.observations.get_derivation(old_key) is None
    assert len(reopened.observations.list_derivations(673)) == 1
    receipts = reopened.retention_execution.list_executions("score_derivations")
    assert len(receipts) == 1
    assert receipts[0].object_ids == (old_key,)
    status = reopened.status().as_dict()["authority"]
    assert status["retention_last_execution"]["plan_digest"] == plan_digest
    assert status["retention_category_states"][0]["state"] == "enforce"
    dashboard = restarted.status()
    assert dashboard["pending_review_count"] == 28
    assert dashboard["last_execution"]["plan_digest"] == plan_digest
    active = next(row for row in dashboard["categories"] if row["category"] == "score_derivations")
    assert active["effective_mode"] == "enforce"
    assert active["grant_cutoff_utc"] == cutoff.isoformat()


def test_retention_activation_rejects_cutoff_that_is_not_yet_eligible(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    _put_derivation(store, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    activated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    coordinator = RetentionCoordinator(
        policy=_enforcement_policy(tmp_path),
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
        clock=lambda: activated_at,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=datetime(2026, 9, 1, tzinfo=timezone.utc))["categories"]
        if item["category"] == "score_derivations"
    )
    coordinator.approve("score_derivations", reason="review")

    with pytest.raises(RetentionError) as error:
        coordinator.activate(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=datetime.fromisoformat(row["cutoff_utc"]),
            reason="must reject a future eligibility boundary",
        )

    assert error.value.code == "retention_cutoff_not_yet_eligible"
    state = store.retention_execution.get_category_state("score_derivations")
    assert state is not None
    assert state.state == "report_only"


def test_bound_cutoff_remains_valid_and_receipt_replays_after_policy_stop_and_time(
    tmp_path: Path,
) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    _put_derivation(store, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    activated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
        clock=lambda: activated_at,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=activated_at)["categories"]
        if item["category"] == "score_derivations"
    )
    cutoff = datetime.fromisoformat(row["cutoff_utc"])
    coordinator.approve("score_derivations", reason="review")
    coordinator.activate(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="bind eligible cutoff",
    )
    grant = store.retention_execution.get_category_state("score_derivations")
    assert grant is not None
    assert grant.activated_at == activated_at
    assert grant.grant_cutoff_utc == cutoff
    coordinator.set_emergency_stop(False, reason="execute qualified plan")

    later = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
        clock=lambda: datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    receipt = later.execute(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="execute later without expiring the conservative grant",
    )
    later.set_emergency_stop(True, reason="stop future effects")

    changed_document = _document()
    changed_document["retention"]["categories"]["score_derivations"]["period"] = "P1Y"
    changed = RetentionCoordinator(
        policy=_policy(tmp_path, changed_document),
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )
    replay = changed.execute(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="read historical receipt",
    )
    assert replay == receipt

    with pytest.raises(RetentionError) as mismatch:
        changed.execute(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=cutoff.replace(day=cutoff.day + 1),
            reason="false receipt identity",
        )
    assert mismatch.value.code == "retention_receipt_identity_mismatch"

    connection = sqlite3.connect(store.path)
    connection.execute(
        "UPDATE retention_executions SET object_ids_json = '[]' WHERE plan_digest = ?",
        (row["plan_digest"],),
    )
    connection.commit()
    connection.close()
    with pytest.raises(StateStoreError) as corrupt:
        store.retention_execution.get_execution(row["plan_digest"])
    assert corrupt.value.code == "state_retention_execution_invalid"


def test_legacy_unbound_enforcement_grant_requires_reactivation(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    _put_derivation(store, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    activated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
        clock=lambda: activated_at,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=activated_at)["categories"]
        if item["category"] == "score_derivations"
    )
    cutoff = datetime.fromisoformat(row["cutoff_utc"])
    coordinator.approve("score_derivations", reason="review")
    coordinator.activate(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="activate",
    )
    coordinator.set_emergency_stop(False, reason="inspect migrated grant")
    connection = sqlite3.connect(store.path)
    connection.execute(
        "UPDATE retention_category_states SET grant_cutoff_utc = NULL, activated_at = NULL "
        "WHERE category_id = 'score_derivations'"
    )
    connection.commit()
    connection.close()

    with pytest.raises(RetentionError) as error:
        coordinator.execute(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=cutoff,
            reason="legacy grant must block",
        )

    assert error.value.code == "retention_grant_invalid"
    assert len(store.observations.list_derivations(673)) == 1


def test_execution_revalidates_classification_inside_delete_transaction(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    _put_derivation(store, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    activated_at = datetime(2026, 8, 30, tzinfo=timezone.utc)
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
        clock=lambda: activated_at,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=activated_at)["categories"]
        if item["category"] == "score_derivations"
    )
    cutoff = datetime.fromisoformat(row["cutoff_utc"])
    coordinator.approve("score_derivations", reason="review")
    coordinator.activate(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="activate classified contract",
    )
    coordinator.set_emergency_stop(False, reason="exercise transaction check")
    connection = sqlite3.connect(store.path)
    connection.execute("ALTER TABLE score_derivations ADD COLUMN future_payload TEXT")
    connection.commit()
    connection.close()

    with pytest.raises(StateStoreError) as error:
        store.retention_execution.execute_score_derivations(
            plan_digest=row["plan_digest"],
            category_digest=row["category_digest"],
            profile_role_digest=row["profile_role_digest"],
            cutoff_utc=cutoff,
            anchor=row["anchor"],
            object_ids=tuple(row["candidate_object_ids"]),
            field_classification=policy.categories["score_derivations"].fields,
            payload_classification=policy.categories["score_derivations"].payload_paths,
            reason="classification changed after activation",
        )

    assert error.value.code == "state_retention_classification_invalid"
    assert len(store.observations.list_derivations(673)) == 1


def test_score_derivation_plan_drift_blocks_and_suspends_category(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    _put_derivation(store, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))["categories"]
        if item["category"] == "score_derivations"
    )
    cutoff = datetime.fromisoformat(row["cutoff_utc"])
    coordinator.approve("score_derivations", reason="review")
    coordinator.activate(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="activate",
    )
    coordinator.set_emergency_stop(False, reason="run drill")
    _put_derivation(store, "b", derived_at=datetime(2025, 2, 1, tzinfo=timezone.utc))

    with pytest.raises(StateStoreError) as error:
        coordinator.execute(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=cutoff,
            reason="must detect drift",
        )

    assert error.value.code == "state_retention_plan_drift"
    assert len(store.observations.list_derivations(673)) == 2
    assert store.retention_execution.list_executions() == []
    category_state = store.retention_execution.get_category_state("score_derivations")
    assert category_state is not None
    assert category_state.state == "suspended"


def test_score_derivation_delete_failure_rolls_back_and_suspends(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    _put_derivation(store, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))["categories"]
        if item["category"] == "score_derivations"
    )
    cutoff = datetime.fromisoformat(row["cutoff_utc"])
    coordinator.approve("score_derivations", reason="review")
    coordinator.activate(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="activate",
    )
    coordinator.set_emergency_stop(False, reason="run drill")
    connection = sqlite3.connect(store.path)
    connection.execute(
        "CREATE TRIGGER retention_canary_abort BEFORE DELETE ON score_derivations "
        "BEGIN SELECT RAISE(ABORT, 'synthetic abort'); END"
    )
    connection.commit()
    connection.close()

    with pytest.raises(StateStoreError) as error:
        coordinator.execute(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=cutoff,
            reason="exercise rollback",
        )

    assert error.value.code == "state_io_error"
    assert len(store.observations.list_derivations(673)) == 1
    assert store.retention_execution.list_executions() == []
    category_state = store.retention_execution.get_category_state("score_derivations")
    assert category_state is not None
    assert category_state.state == "suspended"


def test_retention_execution_blocks_every_inactive_authority_state(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    _put_derivation(store, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=store.retention,
        authority=store.authority,
        execution=store.retention_execution,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))["categories"]
        if item["category"] == "score_derivations"
    )
    cutoff = datetime.fromisoformat(row["cutoff_utc"])

    with pytest.raises(StateStoreError) as stopped:
        store.retention_execution.execute_score_derivations(
            plan_digest=row["plan_digest"],
            category_digest=row["category_digest"],
            profile_role_digest=row["profile_role_digest"],
            cutoff_utc=cutoff,
            anchor=row["anchor"],
            object_ids=tuple(row["candidate_object_ids"]),
            field_classification=policy.categories["score_derivations"].fields,
            payload_classification=policy.categories["score_derivations"].payload_paths,
            reason="must remain blocked",
        )
    assert stopped.value.code == "state_retention_emergency_stop"

    coordinator.set_emergency_stop(False, reason="inspect other block")
    with pytest.raises(StateStoreError) as pending:
        coordinator.execute(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=cutoff,
            reason="pending must block",
        )
    assert pending.value.code == "state_retention_authority_invalid"
    assert store.retention_execution.get_category_state("score_derivations") is None

    coordinator.approve("score_derivations", reason="review only")
    with pytest.raises(StateStoreError) as report_only:
        coordinator.execute(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=cutoff,
            reason="report-only must block",
        )
    assert report_only.value.code == "state_retention_authority_invalid"

    coordinator.activate(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=cutoff,
        reason="prepare suspension check",
    )
    coordinator.suspend("score_derivations", reason="operator suspends category")
    with pytest.raises(StateStoreError) as suspended:
        coordinator.execute(
            "score_derivations",
            plan_digest=row["plan_digest"],
            cutoff_utc=cutoff,
            reason="suspended must block",
        )
    assert suspended.value.code == "state_retention_authority_invalid"


def test_restore_revokes_retention_execution_authority(tmp_path: Path) -> None:
    source = SQLiteStateStore(tmp_path / "source")
    _put_derivation(source, "a", derived_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    policy = _enforcement_policy(tmp_path)
    coordinator = RetentionCoordinator(
        policy=policy,
        state=source.retention,
        authority=source.authority,
        execution=source.retention_execution,
    )
    row = next(
        item
        for item in coordinator.dry_run(at=datetime(2026, 8, 30, tzinfo=timezone.utc))["categories"]
        if item["category"] == "score_derivations"
    )
    coordinator.approve("score_derivations", reason="review")
    coordinator.activate(
        "score_derivations",
        plan_digest=row["plan_digest"],
        cutoff_utc=datetime.fromisoformat(row["cutoff_utc"]),
        reason="activate before backup",
    )
    coordinator.set_emergency_stop(False, reason="simulate active source")
    backup = source.backup(tmp_path / "active-source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live")

    live.restore(backup)

    assert live.retention.emergency_stop() is True
    restored = live.retention_execution.get_category_state("score_derivations")
    assert restored is not None
    assert restored.state == "suspended"
    assert restored.evidence_digest is None
