from __future__ import annotations

from datetime import datetime, timedelta, timezone

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.health_projection import record_projection, snapshot


def test_projection_survives_reopen_and_requires_current_instance(tmp_path) -> None:
    state = SQLiteStateStore(tmp_path)
    instance = state.status().authority_instance
    record_projection(
        state.projections,
        kind="doctor",
        status="passed",
        instance_uuid=instance,
        summary={"checks": 7, "failed": 0},
    )

    reopened = SQLiteStateStore(tmp_path)
    current = snapshot(reopened.projections, instance_uuid=instance)
    restored = snapshot(reopened.projections, instance_uuid="replacement-instance")

    assert current["qualification"]["doctor"]["status"] == "passed"
    assert restored["qualification"]["doctor"]["status"] == "stale"
    assert restored["qualification"]["doctor"]["stale_reason"] == "instance_changed"
    assert restored["qualification"]["status"] == "not_checked"


def test_expired_and_missing_projections_never_pass(tmp_path) -> None:
    state = SQLiteStateStore(tmp_path)
    instance = state.status().authority_instance
    observed = datetime(2026, 9, 18, 8, tzinfo=timezone.utc)
    record_projection(
        state.projections,
        kind="technical_health",
        status="passed",
        instance_uuid=instance,
        summary={"checks": {"state": True}},
        observed_at=observed,
    )

    result = snapshot(
        state.projections,
        instance_uuid=instance,
        now=observed + timedelta(hours=2),
    )

    assert result["technical_health"]["status"] == "stale"
    assert result["operational_readiness"] == {
        "status": "not_checked",
        "lifecycle": "not_checked",
        "current": False,
    }
    assert result["qualification"]["status"] == "not_checked"

    future = snapshot(
        state.projections,
        instance_uuid=instance,
        now=observed - timedelta(seconds=1),
    )
    assert future["technical_health"]["status"] == "stale"
    assert future["technical_health"]["stale_reason"] == "timestamp_in_future"


def test_missing_audit_data_does_not_erase_current_failure(tmp_path) -> None:
    state = SQLiteStateStore(tmp_path)
    instance = state.status().authority_instance
    failed = record_projection(
        state.projections,
        kind="audit_integrity",
        status="failed",
        instance_uuid=instance,
        summary={"failed_files": 1},
    )

    retained = record_projection(
        state.projections,
        kind="audit_integrity",
        status="not_checked",
        instance_uuid="replacement-instance",
        summary={"reason": "audit_logs_missing"},
        preserve_current_failure=True,
    )

    assert retained == failed
    result = snapshot(state.projections, instance_uuid="replacement-instance")
    assert result["qualification"]["audit_integrity"]["status"] == "stale"
    assert result["qualification"]["audit_integrity"]["result"] == "failed"
    assert result["qualification"]["status"] == "not_checked"


def test_qualification_requires_both_current_authoritative_sources(tmp_path) -> None:
    state = SQLiteStateStore(tmp_path)
    instance = state.status().authority_instance
    for kind in ("doctor", "audit_integrity"):
        record_projection(
            state.projections,
            kind=kind,
            status="passed",
            instance_uuid=instance,
            summary={"bounded": True},
        )

    assert (
        snapshot(state.projections, instance_uuid=instance)["qualification"]["status"] == "passed"
    )


def test_successful_recheck_binds_resolution_to_previous_failure(tmp_path) -> None:
    state = SQLiteStateStore(tmp_path)
    instance = state.status().authority_instance
    failed = record_projection(
        state.projections,
        kind="doctor",
        status="failed",
        instance_uuid=instance,
        summary={"failed": 1},
    )
    record_projection(
        state.projections,
        kind="doctor",
        status="passed",
        instance_uuid=instance,
        summary={"failed": 0},
    )

    doctor = snapshot(state.projections, instance_uuid=instance)["qualification"]["doctor"]
    assert doctor["status"] == "passed"
    assert doctor["lifecycle"] == "resolved"
    assert doctor["resolved_finding"]["evidence_digest"] == failed.payload["evidence_digest"]


def test_projection_read_failure_returns_not_checked(caplog) -> None:
    class FailingStore:
        def list_projections(self, issue_number=None, *, series=None):
            raise OSError("private storage detail")

    result = snapshot(FailingStore(), instance_uuid="current")  # type: ignore[arg-type]

    assert result["technical_health"]["status"] == "not_checked"
    assert result["qualification"]["status"] == "not_checked"
    assert "OSError" in caplog.text
    assert "private storage detail" not in caplog.text
