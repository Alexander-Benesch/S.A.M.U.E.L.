from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.state import (
    AuthorityLeaseRecord,
    AuthorityRecord,
    HealingClaimRecord,
    OperationIntentRecord,
    StateStoreError,
    WorkflowCheckpointRecord,
)
from samuel.core.workspaces import WorkspaceRecord
from samuel.slices.state_reconcile import StateReconcileCoordinator


class _Workspaces:
    def __init__(self, records: list[WorkspaceRecord] | None = None) -> None:
        self.records = records or []

    def list_workspaces(self) -> list[WorkspaceRecord]:
        return list(self.records)


class _SCM:
    def __init__(
        self, refs: dict[str, str | None], *, fail: bool = False, merged: bool = False
    ) -> None:
        self.refs = refs
        self.fail = fail
        self.merged = merged

    def resolve_ref_optional(self, ref: str) -> str | None:
        if self.fail:
            raise RuntimeError("transport detail must not escape")
        return self.refs.get(ref)

    def get_pr_revision(self, _number: int) -> object:
        if self.fail:
            raise RuntimeError("transport detail must not escape")
        return SimpleNamespace(head_sha="head", base_sha="base")

    def get_pr(self, _number: int) -> object:
        if self.fail:
            raise RuntimeError("transport detail must not escape")
        return SimpleNamespace(merged=self.merged)

    def find_pr_by_marker(self, marker: str, *, head: str, base: str) -> object | None:
        if self.fail:
            raise RuntimeError("transport detail must not escape")
        if marker == "samuel-intent:pr" and head == "issue-2" and base == "main":
            return SimpleNamespace(number=17)
        return None


def _mountinfo(tmp_path: Path) -> Path:
    path = tmp_path / "mountinfo"
    path.write_text(
        f"36 25 0:32 / {tmp_path} rw,relatime - ext4 device rw\n",
        encoding="utf-8",
    )
    return path


def _restored_state(tmp_path: Path) -> tuple[SQLiteStateStore, str]:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "source", mountinfo_path=mountinfo)
    source.authority.claim_healing(HealingClaimRecord("attempted", 1, "run-1"))
    source.authority.finish_healing("attempted", status="attempted", outcome="failed_test")
    source.authority.claim_healing(HealingClaimRecord("claimed", 2, "run-2"))
    source.authority.put_intent(
        OperationIntentRecord(
            "push-intent",
            "push",
            "pending",
            1,
            "run-1",
            "branch:head",
            {"branch": "issue-1", "expected_head": "head"},
        )
    )
    source.authority.finish_intent(
        "push-intent",
        status="applied",
        postcondition={"remote_head": "head"},
    )
    source.authority.put_intent(
        OperationIntentRecord(
            "commit-intent",
            "commit",
            "pending",
            2,
            "run-2",
            "parent:tree",
            {"expected_parent": "parent", "expected_tree": "tree"},
        )
    )
    source.authority.acquire_lease(
        AuthorityLeaseRecord(
            "expired-lease",
            "owner",
            datetime.now(timezone.utc) - timedelta(minutes=1),
            1,
        )
    )
    backup = source.backup(tmp_path / "source.sqlite3")
    live = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    operation = live.restore(backup)
    return live, operation.operation_id


def test_scan_classifies_bound_objects_and_keeps_uncertain_effects_unresolved(
    tmp_path: Path,
) -> None:
    store, operation_id = _restored_state(tmp_path)
    workspaces = _Workspaces(
        [
            WorkspaceRecord(
                "quarantine",
                "run",
                "/repo",
                "/work/quarantine",
                "issue-1",
                "head",
                "main",
                "quarantined",
                1,
                0,
                "2026-08-30T00:00:00+00:00",
                "2026-08-30T00:00:00+00:00",
            )
        ]
    )
    coordinator = StateReconcileCoordinator(
        authority_store=store.authority,
        workspace_manager=workspaces,  # type: ignore[arg-type]
        scm=_SCM({"issue-1": "head"}),  # type: ignore[arg-type]
    )

    result = coordinator.scan(operation_id)
    status = coordinator.status(operation_id)
    entries = {(row["object_type"], row["object_key"]): row for row in status["entries"]}

    assert result["scan_status"] == "completed"
    assert entries[("intent", "push-intent")]["classification"] == "verified_effect"
    assert entries[("intent", "commit-intent")]["classification"] == "unresolved"
    assert entries[("healing_claim", "attempted")]["classification"] == "verified_effect"
    assert entries[("healing_claim", "claimed")]["classification"] == "unresolved"
    assert entries[("lease", "expired-lease")]["classification"] == "verified_absent"
    assert entries[("workspace", "quarantine")]["classification"] == "abandoned"


def test_scan_failure_cannot_be_abandoned_and_successful_rescan_replaces_it(
    tmp_path: Path,
) -> None:
    store, operation_id = _restored_state(tmp_path)
    failed = StateReconcileCoordinator(
        authority_store=store.authority,
        workspace_manager=_Workspaces(),  # type: ignore[arg-type]
        scm=_SCM({}, fail=True),  # type: ignore[arg-type]
    )

    result = failed.scan(operation_id)
    assert result == {
        "operation_id": operation_id,
        "scan_status": "scan_failed",
        "error_code": "state_reconcile_scan_failed",
        "entries": 0,
    }
    with pytest.raises(StateStoreError) as blocked:
        failed.classify(
            operation_id,
            "intent",
            "push-intent",
            classification="abandoned",
            reason="network failed",
        )
    assert blocked.value.code == "state_reconcile_scan_incomplete"

    recovered = StateReconcileCoordinator(
        authority_store=store.authority,
        workspace_manager=_Workspaces(),  # type: ignore[arg-type]
        scm=_SCM({"issue-1": "head"}),  # type: ignore[arg-type]
    )
    assert recovered.scan(operation_id)["scan_status"] == "completed"
    assert store.list_restore_operations()[-1].scan_status == "completed"


def test_complete_requires_operator_classification_of_every_unresolved_object(
    tmp_path: Path,
) -> None:
    store, operation_id = _restored_state(tmp_path)
    coordinator = StateReconcileCoordinator(
        authority_store=store.authority,
        workspace_manager=_Workspaces(),  # type: ignore[arg-type]
        scm=_SCM({"issue-1": "head"}),  # type: ignore[arg-type]
    )
    coordinator.scan(operation_id)

    with pytest.raises(StateStoreError) as unresolved:
        coordinator.complete(operation_id)
    assert unresolved.value.code == "state_reconcile_unresolved"

    status = coordinator.status(operation_id)
    for entry in status["entries"]:
        if entry["classification"] == "unresolved":
            coordinator.classify(
                operation_id,
                entry["object_type"],
                entry["object_key"],
                classification="abandoned",
                reason="operator reconciled external state",
            )
    completed = coordinator.complete(operation_id)
    assert completed["status"] == "completed"
    assert store.status().reconcile_required is False


def test_pending_pr_intent_uses_backend_neutral_marker_fallback(tmp_path: Path) -> None:
    store, operation_id = _restored_state(tmp_path)
    store.authority.put_intent(
        OperationIntentRecord(
            "pr-intent",
            "create_pr",
            "pending",
            2,
            "run-2",
            "head",
            {
                "head": "issue-2",
                "base": "main",
                "head_sha": "head",
                "base_sha": "base",
                "intent_marker": "samuel-intent:pr",
            },
        )
    )
    coordinator = StateReconcileCoordinator(
        authority_store=store.authority,
        workspace_manager=_Workspaces(),  # type: ignore[arg-type]
        scm=_SCM({"issue-1": "head"}),  # type: ignore[arg-type]
    )

    coordinator.scan(operation_id)
    entries = {
        (row["object_type"], row["object_key"]): row
        for row in coordinator.status(operation_id)["entries"]
    }
    assert entries[("intent", "pr-intent")]["classification"] == "verified_effect"
    assert entries[("intent", "pr-intent")]["reason"] == "pull_request_revision_verified"


@pytest.mark.parametrize(
    ("merged", "expected_classification", "expected_reason"),
    [
        (True, "verified_effect", "merge_postcondition_verified"),
        (False, "unresolved", "merge_effect_not_confirmed"),
    ],
)
def test_merge_intent_reconciles_real_pr_postcondition(
    tmp_path: Path,
    merged: bool,
    expected_classification: str,
    expected_reason: str,
) -> None:
    store, operation_id = _restored_state(tmp_path)
    store.authority.put_intent(
        OperationIntentRecord(
            "merge-intent",
            "merge_pr",
            "pending",
            2,
            "run-2",
            "head",
            {
                "pr_number": 17,
                "expected_head_sha": "head",
                "base_sha": "base",
            },
        )
    )
    coordinator = StateReconcileCoordinator(
        authority_store=store.authority,
        workspace_manager=_Workspaces(),  # type: ignore[arg-type]
        scm=_SCM({}, merged=merged),  # type: ignore[arg-type]
    )

    coordinator.scan(operation_id)
    entries = {
        (row["object_type"], row["object_key"]): row
        for row in coordinator.status(operation_id)["entries"]
    }
    assert entries[("intent", "merge-intent")]["classification"] == expected_classification
    assert entries[("intent", "merge-intent")]["reason"] == expected_reason


@pytest.mark.parametrize(
    ("boundary", "resume_eligible", "expected"),
    [
        ("provider_running", True, "unresolved"),
        ("provider_completed", False, "verified_effect"),
    ],
)
def test_restore_never_treats_applied_provider_dispatch_as_completed_verification(
    tmp_path: Path,
    boundary: str,
    resume_eligible: bool,
    expected: str,
) -> None:
    mountinfo = _mountinfo(tmp_path)
    source = SQLiteStateStore(tmp_path / "provider-source", mountinfo_path=mountinfo)
    request_key = "verification:sha256:" + "9" * 64
    source.authority.put_authority_record(
        AuthorityRecord(
            record_key=request_key,
            kind="verification_request.v1",
            payload={"request_key": request_key},
        )
    )
    source.authority.put_intent(
        OperationIntentRecord(
            intent_key=f"dispatch:{request_key}",
            operation="provider_dispatch.v1",
            status="pending",
            issue_number=679,
            correlation_id="provider-run",
            subject_key=request_key,
            payload={"request_key": request_key},
        )
    )
    source.authority.finish_intent(
        f"dispatch:{request_key}",
        status="applied",
        postcondition={"run_id": "704", "verification_complete": False},
    )
    source.authority.put_checkpoint(
        WorkflowCheckpointRecord(
            checkpoint_key=f"provider:{request_key}",
            issue_number=679,
            correlation_id="provider-run",
            workflow="provider_verification",
            boundary=boundary,
            repository="https://gitea.example/owner/repo",
            branch="b" * 40,
            base_ref="a" * 40,
            head_sha="b" * 40,
            workspace_id="",
            evaluation_subject={"head_sha": "b" * 40},
            resume_eligible=resume_eligible,
            payload={"request_key": request_key},
        )
    )
    backup = source.backup(tmp_path / "provider-source.sqlite3")
    live = SQLiteStateStore(tmp_path / "provider-live", mountinfo_path=mountinfo)
    operation = live.restore(backup)
    coordinator = StateReconcileCoordinator(
        authority_store=live.authority,
        workspace_manager=_Workspaces(),  # type: ignore[arg-type]
        scm=_SCM({}),  # type: ignore[arg-type]
    )

    coordinator.scan(operation.operation_id)
    entries = {
        (row["object_type"], row["object_key"]): row
        for row in coordinator.status(operation.operation_id)["entries"]
    }

    assert entries[("intent", f"dispatch:{request_key}")]["classification"] == expected
    assert entries[("authority_record", request_key)]["classification"] == expected
