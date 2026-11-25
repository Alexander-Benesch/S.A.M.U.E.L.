from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.cli import main
from samuel.core.state import (
    HealingClaimRecord,
    ReconcileEntryRecord,
    RunProjectionRecord,
    StateStoreError,
)


def _console_script() -> Path:
    script = Path(sys.prefix) / "bin" / "samuel"
    assert script.is_file()
    return script


def _config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text(
        json.dumps(
            {
                "data_dir": "runtime",
                "workspace": {
                    "work_dir": "workspaces",
                    "minimum_free_mebibytes": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    return config_dir


def test_installed_state_status_and_dump_are_deterministic_and_payload_free(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    command = [str(_console_script()), "--config", str(config_dir), "state"]

    status = subprocess.run(
        [*command, "status", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    first_dump = subprocess.run(
        [*command, "dump", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    second_dump = subprocess.run(
        [*command, "dump", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert status.returncode == 0
    status_payload = json.loads(status.stdout)
    assert status_payload["ok"] is True
    assert status_payload["state"]["schema_version"] == 10
    assert status_payload["state"]["authority"]["retention_emergency_stop"] is True
    assert status_payload["state"]["projections"] == {
        "error_code": None,
        "failure_semantics": "non_blocking",
        "healthy": True,
    }
    assert status_payload["state"]["path"] == str(tmp_path / "runtime" / "samuel-state.sqlite3")
    assert status_payload["state"]["resume"] == {
        "blocked": 0,
        "configured": False,
        "enabled": False,
        "last_outcome": {},
        "pending": 0,
        "reconcile_required": False,
    }
    assert first_dump.returncode == second_dump.returncode == 0
    assert first_dump.stdout == second_dump.stdout
    dump_payload = json.loads(first_dump.stdout)
    assert dump_payload["state"]["payloads_included"] is False
    assert dump_payload["state"]["authority_counts"]["claims"]["claimed"] == 0
    assert dump_payload["state"]["resume"]["pending"] == 0


def test_state_cli_abandons_claim_with_reason_and_never_prints_payload(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    store = SQLiteStateStore(tmp_path / "runtime")
    store.authority.claim_healing(
        HealingClaimRecord(
            observation_key="sha256:" + "a" * 64,
            issue_number=629,
            correlation_id="run-629",
        )
    )

    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            "abandon-healing",
            "--observation-key",
            "sha256:" + "a" * 64,
            "--reason",
            "operator reviewed unresolved claim",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["state"]["status"] == "abandoned"
    assert "operator reviewed" not in result.stdout
    reopened = SQLiteStateStore(tmp_path / "runtime")
    claim = reopened.authority.get_healing_claim("sha256:" + "a" * 64)
    assert claim is not None
    assert claim.status == "abandoned"


def test_state_cli_reprojects_run_outcomes_without_printing_payloads(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    store = SQLiteStateStore(tmp_path / "runtime")
    for key, correlation_id, message_name in (
        ("blocked", "run-blocked", "PlanBlocked"),
        ("unbound", "call-unbound", "LLMCallCompleted"),
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
                                "message_name": message_name,
                                "issue": 414,
                                "correlation_id": correlation_id,
                                "secret": "must-not-print",
                            },
                        }
                    ],
                },
            )
        )

    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            "reproject-runs",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["state"] == {
        "blocked": 1,
        "complete": 0,
        "manual_pending": 0,
        "running": 0,
        "scanned": 2,
        "unbound": 1,
        "updated": 2,
    }
    assert "must-not-print" not in result.stdout
    reopened = SQLiteStateStore(tmp_path / "runtime")
    assert {row.projection_key: row.status for row in reopened.projections.list_projections()} == {
        "blocked": "blocked",
        "unbound": "unbound",
    }


def test_state_cli_reports_corrupt_database_without_bootstrap(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    data_dir = tmp_path / "runtime"
    data_dir.mkdir()
    (data_dir / "samuel-state.sqlite3").write_bytes(b"not sqlite")

    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            "status",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload == {
        "action": "status",
        "error": {
            "code": "state_corrupt",
            "message": "Runtime-state database is corrupt or unreadable",
        },
        "ok": False,
    }


def test_state_cli_reports_newer_schema_fail_closed(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    data_dir = tmp_path / "runtime"
    data_dir.mkdir()
    connection = sqlite3.connect(data_dir / "samuel-state.sqlite3")
    connection.execute("PRAGMA user_version = 99")
    connection.close()

    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            "status",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "state_schema_too_new"
    assert "99" in payload["error"]["message"]


def test_state_cli_restores_and_requires_explicit_reconcile_completion(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    source = SQLiteStateStore(tmp_path / "source")
    source.authority.claim_healing(HealingClaimRecord("claim", 666, "run"))
    backup = source.backup(tmp_path / "backup.sqlite3")
    SQLiteStateStore(tmp_path / "runtime")
    command = [str(_console_script()), "--config", str(config_dir), "state"]

    restored = subprocess.run(
        [*command, "restore", "--source", str(backup), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert restored.returncode == 0
    restored_payload = json.loads(restored.stdout)
    operation_id = restored_payload["state"]["operation_id"]
    assert restored_payload["state"]["status"] == "reconcile_required"
    assert "claim" not in restored.stdout

    open_status = subprocess.run(
        [*command, "status", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert open_status.returncode == 0
    open_authority = json.loads(open_status.stdout)["state"]["authority"]
    assert open_authority["active_restore_operation"] == operation_id
    assert open_authority["restore_scan_status"] == "pending"
    assert open_authority["restore_sentinel_present"] is False

    store = SQLiteStateStore(tmp_path / "runtime")
    store.authority.replace_reconcile_scan(
        operation_id,
        [
            ReconcileEntryRecord(
                operation_id,
                "inventory",
                "complete",
                "verified_effect",
                "inventory_completed",
            ),
            ReconcileEntryRecord(
                operation_id,
                "healing_claim",
                "claim",
                "unresolved",
                "operator review required",
            ),
        ],
    )
    classified = subprocess.run(
        [
            *command,
            "reconcile-classify",
            "--operation-id",
            operation_id,
            "--object-type",
            "healing_claim",
            "--object-key",
            "claim",
            "--classification",
            "abandoned",
            "--reason",
            "operator verified no effect",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert classified.returncode == 0
    assert "operator verified" not in classified.stdout

    completed = subprocess.run(
        [
            *command,
            "reconcile-complete",
            "--operation-id",
            operation_id,
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["state"]["status"] == "completed"
    assert SQLiteStateStore(tmp_path / "runtime").status().reconcile_required is False


def test_normal_bootstrap_reports_state_failure_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def blocked(*_args: object, **_kwargs: object) -> object:
        raise StateStoreError("state_corrupt", "Runtime-state database is corrupt")

    monkeypatch.setattr("samuel.core.bootstrap.bootstrap", blocked)

    with pytest.raises(SystemExit) as exc_info:
        main(["health"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: Runtime-state database is corrupt\n"
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("action", ["status", "dump"])
def test_readonly_state_cli_observes_committed_wal_without_bootstrap_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], action: str
) -> None:
    config_dir = _config(tmp_path)
    store = SQLiteStateStore(tmp_path / "runtime")

    def forbidden(*args, **kwargs):
        raise AssertionError("read-only diagnostics must not initialize state or bootstrap")

    monkeypatch.setattr(SQLiteStateStore, "_initialize", forbidden)
    monkeypatch.setattr("samuel.core.bootstrap.bootstrap", forbidden)
    # Keep a writer connected: the committed value exists in WAL, not just the
    # main database. A shortcut using immutable=1 would miss this observation.
    with sqlite3.connect(store.path) as writer:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE authority_metadata SET retention_emergency_stop=0")
        writer.commit()
        paths = [store.path, store.authority_witness_path, Path(str(store.path) + "-wal")]
        before = {path: path.read_bytes() for path in paths}
        with pytest.raises(SystemExit) as exit_info:
            main(["--config", str(config_dir), "state", action, "--read-only", "--json"])
        assert exit_info.value.code == 0
        result = json.loads(capsys.readouterr().out)
        state = result["state"]["status"] if action == "dump" else result["state"]
        assert state["schema_version"] == 10
        assert state["authority"]["retention_emergency_stop"] is False
        assert {path: path.read_bytes() for path in paths} == before


@pytest.mark.parametrize("action", ["status", "dump"])
def test_installed_readonly_state_cli_never_creates_missing_state(tmp_path: Path, action: str):
    config_dir = _config(tmp_path)
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            action,
            "--read-only",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "state_missing"
    assert not (tmp_path / "runtime").exists()


@pytest.mark.parametrize("version", [9, 99])
def test_readonly_state_cli_does_not_migrate_incompatible_schema(tmp_path: Path, version: int):
    config_dir = _config(tmp_path)
    store = SQLiteStateStore(tmp_path / "runtime")
    with sqlite3.connect(store.path) as connection:
        connection.execute(f"PRAGMA user_version={version}")
    before = store.path.read_bytes()
    witness = store.authority_witness_path.read_bytes()
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            "status",
            "--read-only",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False
    assert store.path.read_bytes() == before
    assert store.authority_witness_path.read_bytes() == witness


@pytest.mark.parametrize(
    "action",
    ["restore", "reproject-runs", "abandon-healing", "reconcile-scan", "reconcile-complete"],
)
def test_readonly_rejects_mutating_actions_before_store_creation(tmp_path: Path, action: str):
    config_dir = _config(tmp_path)
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            action,
            "--read-only",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "state_readonly_action_invalid"
    assert not (tmp_path / "runtime").exists()


@pytest.mark.parametrize("missing", ["lock", "witness"])
def test_readonly_state_cli_preserves_missing_authority_inputs(tmp_path: Path, missing: str):
    config_dir = _config(tmp_path)
    store = SQLiteStateStore(tmp_path / "runtime")
    path = store.lifecycle_lock_path if missing == "lock" else store.authority_witness_path
    path.unlink()
    before = store.path.read_bytes()
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            "status",
            "--read-only",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(result.stdout)
    if missing == "lock":
        assert result.returncode == 1
        assert payload["error"]["code"] == "state_lifecycle_lock_failed"
    else:
        assert result.returncode == 0
        assert payload["state"]["authority"]["reconcile_required"] is True
    assert not path.exists()
    assert store.path.read_bytes() == before


def test_readonly_state_exposes_only_fixed_maintenance_recovery_identity(tmp_path: Path):
    from samuel.core.configuration_session import ConfigurationSession

    config_dir = _config(tmp_path)
    store = SQLiteStateStore(tmp_path / "runtime")
    session = ConfigurationSession(store.authority)
    with session.host_transition("production", "operator", "private operator reason", "e" * 64):
        pass
    before = store.path.read_bytes()
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "state",
            "status",
            "--read-only",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    configuration = json.loads(result.stdout)["state"]["configuration"]
    assert configuration["phase"] == "maintenance"
    assert configuration["maintenance"] == {
        key: value
        for key, value in session.state()["maintenance"].items()
        if key in {"operation_id", "binding", "target", "step"}
    }
    assert "private operator reason" not in result.stdout
    assert store.path.read_bytes() == before
