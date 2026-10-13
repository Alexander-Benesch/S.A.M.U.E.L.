from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from samuel.cli import _cmd_resume
from samuel.core.bus import Bus
from samuel.core.state import StateStoreError


class _Coordinator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "pending": 1, "blocked": 0, "last_outcome": {}}

    def list(self) -> list[dict[str, Any]]:
        return [{"checkpoint_key": "checkpoint-1", "resume_eligible": True}]

    def inspect(self, checkpoint_key: str) -> dict[str, Any]:
        if checkpoint_key != "checkpoint-1":
            raise StateStoreError("resume_checkpoint_missing", "missing")
        return {"checkpoint_key": checkpoint_key, "boundary": "push_pending"}

    def abandon(self, checkpoint_key: str, *, reason: str) -> dict[str, Any]:
        self.calls.append(("abandon", checkpoint_key, reason))
        return {"checkpoint_key": checkpoint_key, "status": "abandoned"}

    def cleanup(self, checkpoint_key: str, *, reason: str) -> dict[str, Any]:
        self.calls.append(("cleanup", checkpoint_key, reason))
        return {"checkpoint_key": checkpoint_key, "status": "cleaned"}


def _args(action: str, checkpoint_key: str = "", reason: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        action=action,
        checkpoint_key=checkpoint_key,
        reason=reason,
        json=True,
    )


def test_resume_list_and_inspect_are_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    bus = Bus()
    bus.resume_coordinator = _Coordinator()

    assert _cmd_resume(bus, _args("list")) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["resume"]["status"]["pending"] == 1
    assert listed["resume"]["checkpoints"][0]["checkpoint_key"] == "checkpoint-1"

    assert _cmd_resume(bus, _args("inspect", "checkpoint-1")) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["resume"] == {
        "boundary": "push_pending",
        "checkpoint_key": "checkpoint-1",
    }


@pytest.mark.parametrize("action", ["abandon", "cleanup"])
def test_destructive_resume_operator_actions_require_reason(
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    bus = Bus()
    bus.resume_coordinator = _Coordinator()

    assert _cmd_resume(bus, _args(action, "checkpoint-1")) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == f"resume_{action}_arguments_required"


@pytest.mark.parametrize("action", ["attempt", "resume"])
def test_targeted_attempt_and_resume_alias_report_pending_as_nonzero(
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    bus = Bus()
    bus.resume_coordinator = _Coordinator()
    bus.register_command(
        "ResumePending",
        lambda command: {
            "attempted": 1,
            "resumed": 0,
            "blocked": 1,
            "details": [
                {
                    "checkpoint_key": command.payload["checkpoint_key"],
                    "pending": True,
                    "reason": "resume_lease_live",
                }
            ],
        },
    )

    assert _cmd_resume(bus, _args(action, "checkpoint-1")) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["resume"]["details"][0]["reason"] == "resume_lease_live"


def _runtime(tmp_path: Path, *, checkpoint: bool = True) -> tuple[Path, Any]:
    from samuel.adapters.state.sqlite import SQLiteStateStore
    from samuel.core.state import WorkflowCheckpointRecord

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text(
        json.dumps({"data_dir": "state", "resume": {"enabled": True}}), encoding="utf-8"
    )
    store = SQLiteStateStore("state", config_dir=config_dir)
    if checkpoint:
        store.authority.put_checkpoint(
            WorkflowCheckpointRecord(
                checkpoint_key="checkpoint-1",
                issue_number=987,
                correlation_id="resume-test",
                workflow="default",
                boundary="push_pending",
                repository="owner/project",
                branch="fix/example",
                base_ref="main",
                head_sha="a" * 40,
                workspace_id="",
                evaluation_subject={},
                resume_eligible=True,
                payload={},
            )
        )
    return config_dir, store


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode & 0o777)
        for path in root.rglob("*")
        if path.is_file()
        and path.name not in {"samuel-state.sqlite3-shm", "samuel-state.sqlite3-wal"}
    }


def _public_resume(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    config_dir: Path,
    *arguments: str,
) -> tuple[int, dict[str, Any]]:
    from samuel.cli import main

    with pytest.raises(SystemExit) as exit_info:
        main(["--config", str(config_dir), "resume", *arguments, "--json"])
    assert isinstance(exit_info.value.code, int)
    return exit_info.value.code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("project", [None, "missing", "valid"])
@pytest.mark.parametrize("action", ["list", "inspect"])
def test_public_resume_diagnostics_need_no_target_or_runtime_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    project: str | None,
    action: str,
) -> None:
    from samuel.core import bootstrap

    config_dir, store = _runtime(tmp_path)
    monkeypatch.delenv("SAMUEL_RUNTIME_CONFIG_DIR", raising=False)
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SCM_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    if project:
        root = tmp_path / project
        if project == "valid":
            root.mkdir()
            (root / ".git").mkdir()
        monkeypatch.setenv("PROJECT_ROOT", str(root))

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("passive resume must not bootstrap, run Git or call the network")

    monkeypatch.setattr(bootstrap, "bootstrap", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    # Read-only diagnosis must not silently repair permissions either.
    store.path.chmod(0o640)
    store.lifecycle_lock_path.chmod(0o640)
    before = _snapshot(tmp_path)
    code, result = _public_resume(
        monkeypatch, capsys, config_dir, action, *(["checkpoint-1"] if action == "inspect" else [])
    )
    assert code == 0 and result["ok"] is True
    status = result["resume"]["status"]
    assert status["pending"] == 1 and status["reconcile_required"] is False
    if action == "inspect":
        assert result["resume"]["checkpoint_key"] == "checkpoint-1"
    else:
        assert result["resume"]["checkpoints"][0]["checkpoint_key"] == "checkpoint-1"
    assert _snapshot(tmp_path) == before


def test_public_resume_empty_existing_state_is_distinct_from_missing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SAMUEL_RUNTIME_CONFIG_DIR", raising=False)
    config_dir, store = _runtime(tmp_path, checkpoint=False)
    code, result = _public_resume(monkeypatch, capsys, config_dir, "list")
    assert code == 0 and result["resume"]["checkpoints"] == []
    store.path.unlink()
    before = _snapshot(tmp_path)
    code, result = _public_resume(monkeypatch, capsys, config_dir, "list")
    assert code == 1 and result["ok"] is False
    assert result["error"]["code"] == "state_missing"
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("document", [None, "{", "[]", '{"data_dir": ""}'])
def test_public_resume_missing_or_invalid_config_is_json_error_without_state_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    document: str | None,
) -> None:
    monkeypatch.delenv("SAMUEL_RUNTIME_CONFIG_DIR", raising=False)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    if document is not None:
        (config_dir / "agent.json").write_text(document, encoding="utf-8")
    before = _snapshot(tmp_path)
    code, result = _public_resume(monkeypatch, capsys, config_dir, "list")
    assert code == 1 and result["error"]["code"] == "resume_config_invalid"
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("damage", ["corrupt", "old_schema", "missing_lock"])
def test_public_resume_damaged_state_is_not_migrated_or_recreated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    damage: str,
) -> None:
    import sqlite3

    monkeypatch.delenv("SAMUEL_RUNTIME_CONFIG_DIR", raising=False)
    config_dir, store = _runtime(tmp_path)
    if damage == "corrupt":
        store.path.write_bytes(b"not a database")
    elif damage == "old_schema":
        with sqlite3.connect(store.path) as connection:
            connection.execute("PRAGMA user_version = 9")
    else:
        store.lifecycle_lock_path.unlink()
    before = _snapshot(tmp_path)
    code, result = _public_resume(monkeypatch, capsys, config_dir, "list")
    assert code == 1 and result["ok"] is False
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "damage",
    [
        "missing_witness",
        "wrong_instance",
        "epoch_rollback",
        "witness_lag",
        "restore_interrupted",
        "reconcile",
    ],
)
def test_public_resume_reports_reconcile_without_authority_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    damage: str,
) -> None:
    monkeypatch.delenv("SAMUEL_RUNTIME_CONFIG_DIR", raising=False)
    config_dir, store = _runtime(tmp_path)
    witness = json.loads(store.authority_witness_path.read_text())
    if damage == "missing_witness":
        store.authority_witness_path.unlink()
    elif damage == "wrong_instance":
        witness["instance_uuid"] = "different-instance"
        store.authority_witness_path.write_text(json.dumps(witness))
    elif damage in {"epoch_rollback", "witness_lag"}:
        witness["authority_epoch"] += 1 if damage == "epoch_rollback" else -1
        store.authority_witness_path.write_text(json.dumps(witness))
    elif damage == "restore_interrupted":
        store.restore_sentinel_path.write_text("{}")
    else:
        store._mark_reconcile("existing_reconcile_reason")
    before = _snapshot(tmp_path)
    code, result = _public_resume(monkeypatch, capsys, config_dir, "list")
    assert code == 0 and result["resume"]["checkpoints"]
    status = result["resume"]["status"]
    assert status["enabled"] is False and status["reconcile_required"] is True
    assert status["reconcile_reason"]
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("action", ["attempt", "resume", "abandon", "cleanup"])
def test_public_mutating_resume_keeps_target_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    from samuel.cli import main
    from samuel.core import bootstrap

    monkeypatch.delenv("SAMUEL_RUNTIME_CONFIG_DIR", raising=False)
    monkeypatch.delenv("PROJECT_ROOT", raising=False)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("missing target must be rejected before bootstrap")

    monkeypatch.setattr(bootstrap, "bootstrap", forbidden)
    with pytest.raises(SystemExit) as exit_info:
        main(["--config", str(tmp_path), "resume", action, "checkpoint-1", "--json"])
    assert exit_info.value.code == 2
    assert "PROJECT_ROOT" in capsys.readouterr().err


def test_readonly_store_sees_live_wal_and_rejects_mutation(tmp_path: Path) -> None:
    import sqlite3

    from samuel.adapters.state.sqlite import SQLiteStateStore

    _, store = _runtime(tmp_path)
    with sqlite3.connect(store.path) as writer:
        writer.execute(
            "UPDATE workflow_checkpoints SET branch = 'live-wal' WHERE checkpoint_key = 'checkpoint-1'"
        )
        writer.commit()
        reader = SQLiteStateStore(store.data_dir, read_only=True)
        checkpoint = reader.authority.get_checkpoint("checkpoint-1")
        assert checkpoint is not None and checkpoint.branch == "live-wal"
        before = _snapshot(tmp_path)
        with pytest.raises(StateStoreError) as failure:
            reader.authority.clear_checkpoint("checkpoint-1")
        assert failure.value.code == "state_readonly"
        with pytest.raises(StateStoreError, match="diagnostics cannot mutate"):
            reader._sync_authority_witness()
        assert _snapshot(tmp_path) == before
