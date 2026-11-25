from __future__ import annotations

import hashlib
import io
import json
import multiprocessing
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.configuration_mode import ConfigurationAuthority
from samuel.core.configuration_session import ConfigurationConflict, ConfigurationSession
from samuel.core.state import StateStoreError
from tests.test_cli_state import _config, _console_script

BINDING = "a" * 64


def test_backup_preparation_holds_both_fences_before_persisting_maintenance(tmp_path: Path) -> None:
    session = _session(tmp_path)
    before = session.state()
    calls = []

    def prepare() -> None:
        calls.append("backup")
        assert session.state() == before
        parent, child = multiprocessing.Pipe()
        process = multiprocessing.Process(target=_try_admission, args=(str(tmp_path), child))
        process.start()
        assert parent.poll(5) and parent.recv() == "blocked"
        process.join(5)
        assert process.exitcode == 0
        with pytest.raises(ConfigurationConflict), _session(tmp_path).configuration_write():
            pytest.fail("configuration entered during backup")

    with session.host_transition(
        "production", "operator", "update", BINDING, before_transition=prepare
    ):
        assert session.state()["maintenance"]["step"] == "pending"
    assert calls == ["backup"]
    with (
        pytest.raises(ConfigurationConflict, match="Ruhezustand"),
        session.host_transition(
            "production", "operator", "retry", BINDING, before_transition=prepare
        ),
    ):
        pass
    assert calls == ["backup"]


@pytest.mark.parametrize("failure", ["backup", "state", "scm", "authority"])
def test_failed_backup_preparation_never_enters_maintenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    session = _session(tmp_path)
    before = session.state()

    def prepare() -> None:
        if failure == "backup":
            raise OSError("disk full")
        if failure == "state":
            state = session.state()
            state["revision"] += 1
            session._save(state)
        elif failure == "scm":
            session.external_blockers = lambda: ["SCM unavailable"]
        elif failure == "authority":
            monkeypatch.setattr(
                session.store, "authority_status", lambda: {"reconcile_required": True}
            )

    with (
        pytest.raises((OSError, ConfigurationConflict)),
        session.host_transition(
            "production", "operator", "update", BINDING, before_transition=prepare
        ),
    ):
        pytest.fail("host transition admitted after failed preparation")
    assert session.state()["phase"] == "idle"
    assert "maintenance" not in session.state()
    if failure != "state":
        assert session.state() == before


@pytest.mark.parametrize("blocker", ["active", "issues", "phase", "external"])
def test_busy_installation_never_runs_backup_preparation(tmp_path: Path, blocker: str) -> None:
    session = _session(tmp_path)
    state = session.state()
    if blocker in {"active", "issues"}:
        state[blocker] = {"7": "waiting"}
    elif blocker == "phase":
        state["phase"] = "editing"
    else:
        session.external_blockers = lambda: ["SCM unavailable"]
    session._save(state)

    def prepare() -> None:
        pytest.fail("backup attempted with a blocker")

    with (
        pytest.raises(ConfigurationConflict),
        session.host_transition(
            "production", "operator", "update", BINDING, before_transition=prepare
        ),
    ):
        pass


@pytest.mark.parametrize("completion", ["COMMIT\n", ""])
def test_cli_pretransition_backup_is_consistent_idle_state_and_preserves_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completion: str,
) -> None:
    from samuel.cli import _cmd_maintenance

    config = _config(tmp_path)
    shutil.copyfile(Path(__file__).parents[1] / "config/privacy.json", config / "privacy.json")
    store = SQLiteStateStore(tmp_path / "runtime")
    session = ConfigurationSession(store.authority)
    state = session.state()
    state["prompt_bindings"] = {"7": {"manifest": {"test": "preserved"}}}
    session._save(state)
    before = session.state()
    bus = SimpleNamespace(configuration_session=session, state_store=store)
    args = SimpleNamespace(
        target="production",
        reason="explicit update",
        binding=BINDING,
        backup_before_transition=True,
        config=str(config),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(completion))
    assert _cmd_maintenance(bus, args) == (0 if completion else 1)  # type: ignore[arg-type]
    output = capsys.readouterr().out.splitlines()
    assert output[0].startswith("SAMUEL_MAINTENANCE_BACKUP ")
    receipt = json.loads(output[0].split(" ", 1)[1])
    path = Path(receipt["path"])
    assert receipt["digest"] == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        saved = connection.execute(
            "SELECT payload_json FROM authority_records WHERE record_key=?",
            ("configuration:admission:v1",),
        ).fetchone()
        assert json.loads(saved[0]) == before
    assert output[1] == "SAMUEL_MAINTENANCE_READY"
    assert ("SAMUEL_MAINTENANCE_COMMITTED" in output) == bool(completion)
    assert session.state()["prompt_bindings"] == before["prompt_bindings"]
    assert session.state()["phase"] == ("idle" if completion else "maintenance")


def test_cli_backup_failure_and_invalid_target_never_announce_readiness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from samuel.cli import _cmd_maintenance

    config = _config(tmp_path)
    shutil.copyfile(Path(__file__).parents[1] / "config/privacy.json", config / "privacy.json")
    # An unusable existing backup destination must stop before host readiness.
    (tmp_path / "data").mkdir()
    (tmp_path / "data/backups").write_text("not a directory")
    store = SQLiteStateStore(tmp_path / "runtime")
    session = ConfigurationSession(store.authority)
    bus = SimpleNamespace(configuration_session=session, state_store=store)
    args = SimpleNamespace(
        target="production",
        reason="explicit",
        binding=BINDING,
        backup_before_transition=True,
        config=str(config),
    )
    before = session.state()
    assert _cmd_maintenance(bus, args) == 1  # type: ignore[arg-type]
    assert "SAMUEL_MAINTENANCE_" not in capsys.readouterr().out
    assert session.state() == before
    args.target = "setup"
    assert _cmd_maintenance(bus, args) == 2  # type: ignore[arg-type]
    assert "SAMUEL_MAINTENANCE_" not in capsys.readouterr().out
    assert session.state() == before


def _session(root: Path) -> ConfigurationSession:
    return ConfigurationSession(SQLiteStateStore(root).authority)


def _try_admission(root: str, connection: Any) -> None:
    try:
        with _session(Path(root)).admission():
            connection.send("admitted")
    except ConfigurationConflict:
        connection.send("blocked")
    finally:
        connection.close()


def test_setup_transition_holds_process_fences_then_allows_only_setup_writes(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    session.external_blockers = lambda: ["SCM not configured"]
    with session.host_transition("setup", "operator", "initial", BINDING) as done:
        assert session.state()["phase"] == "maintenance"
        parent, child = multiprocessing.Pipe()
        process = multiprocessing.Process(target=_try_admission, args=(str(tmp_path), child))
        process.start()
        assert parent.poll(5) and parent.recv() == "blocked"
        process.join(5)
        assert process.exitcode == 0
        with (
            pytest.raises(ConfigurationConflict),
            _session(tmp_path).host_transition("setup", "other", "parallel", BINDING),
        ):
            pytest.fail("second operator admitted")
        done()
    restarted = _session(tmp_path)
    assert restarted.state()["maintenance"]["step"] == "setup"
    with restarted.configuration_write(setup=True):
        pass
    for method in (restarted.admission, restarted.operator_action, restarted.configuration_write):
        with pytest.raises(ConfigurationConflict), method():
            pytest.fail("maintenance admitted work")
    setup = ConfigurationAuthority("setup", source="test", config_dir=tmp_path)
    setup.session = restarted
    production = ConfigurationAuthority("production", source="test", config_dir=tmp_path)
    production.session = restarted
    assert setup.blocked_result() is None
    assert production.blocked_result() is not None
    with pytest.raises(ConfigurationConflict):
        restarted.cancel("admin", restarted.state()["version"], recovery=True)
    with pytest.raises(ConfigurationConflict):
        restarted.reconcile_dispatch("admin")


def test_interrupted_transition_remains_closed_and_requires_same_binding(tmp_path: Path) -> None:
    session = _session(tmp_path)
    with session.host_transition("setup", "operator", "explicit", BINDING):
        pass
    restarted = _session(tmp_path)
    pending = restarted.state()
    with pytest.raises(ConfigurationConflict), restarted.admission():
        pass
    with pytest.raises(ConfigurationConflict), restarted.configuration_write(setup=True):
        pass
    with (
        pytest.raises(ConfigurationConflict, match="anderen Installation"),
        restarted.host_transition("production", "operator", "retry", "b" * 64),
    ):
        pass
    assert restarted.state() == pending
    with restarted.host_transition("setup", "operator", "retry", BINDING) as complete:
        complete()
    assert restarted.setup_writes_allowed()


def test_only_explicit_production_completion_releases_admission_and_keeps_bindings(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path)
    state = session.state()
    state["prompt_bindings"] = {"7": {"manifest": {"test": "preserved"}}}
    session._save(state)
    before = session.state()
    with session.host_transition("production", "operator", "explicit start", BINDING) as complete:
        state = complete()
        assert state["phase"] == "idle"
        with pytest.raises(ConfigurationConflict):
            complete()
        with pytest.raises(ConfigurationConflict), _session(tmp_path).admission():
            pass
    assert session.state()["revision"] == before["revision"]
    assert session.state()["prompt_bindings"] == before["prompt_bindings"]
    with session.admission():
        pass


@pytest.mark.parametrize("blocker", ["active", "issues", "phase", "external"])
def test_existing_blockers_prevent_transition_without_state_change(
    tmp_path: Path, blocker: str
) -> None:
    session = _session(tmp_path)
    state = session.state()
    if blocker in {"active", "issues"}:
        state[blocker] = {"7": "waiting"}
    elif blocker == "phase":
        state["phase"] = "failed"
    else:
        session.external_blockers = lambda: ["SCM issue #7"]
    session._save(state)
    before = session.state()
    with (
        pytest.raises(ConfigurationConflict),
        session.host_transition(
            "production" if blocker == "external" else "setup", "operator", "requested", BINDING
        ),
    ):
        pass
    assert session.state() == before


@pytest.mark.parametrize(
    "target,actor,binding",
    [("invalid", "operator", BINDING), ("setup", "", BINDING), ("setup", "operator", "invalid")],
)
def test_invalid_operator_binding_has_no_state_effect(
    tmp_path: Path, target: str, actor: str, binding: str
) -> None:
    session = _session(tmp_path)
    with pytest.raises(ValueError), session.host_transition(target, actor, "explicit", binding):
        pass
    assert session.state()["version"] == 0


@pytest.mark.parametrize("when", ["begin", "complete"])
def test_audit_failure_keeps_transition_pending(tmp_path: Path, when: str) -> None:
    session = _session(tmp_path)

    def fail(payload: dict[str, Any]) -> None:
        raise OSError("audit unavailable")

    if when == "begin":
        session.audit = fail
    with (
        pytest.raises(OSError, match="audit unavailable"),
        session.host_transition("production", "operator", "explicit", BINDING) as complete,
    ):
        session.audit = fail
        complete()
    assert _session(tmp_path).state()["maintenance"]["step"] == "pending"


def test_sqlite_contention_never_audits_completion_before_commit(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path, timeout=0.05)
    session = ConfigurationSession(store.authority)
    events: list[dict[str, Any]] = []
    session.audit = events.append
    with session.host_transition("setup", "operator", "test", BINDING) as complete:
        with sqlite3.connect(store.path) as reservation:
            reservation.execute("BEGIN IMMEDIATE")
            with pytest.raises(StateStoreError) as error:
                complete()
            assert error.value.code == "state_locked"
        assert session.state()["maintenance"]["step"] == "pending"
    assert [entry["action"] for entry in events] == [
        "host_transition_started",
        "host_transition_commit_requested",
    ]
    with session.host_transition("setup", "operator", "explicit retry", BINDING) as retry:
        committed = retry()
    assert events[-1]["action"] == "host_transition_commit_recorded"
    assert events[-1]["phase"] == "maintenance" and events[-1]["maintenance"]["step"] == "pending"
    assert events[-1]["version"] == committed["last_host_transition"]["commit_version"]
    assert events[0]["maintenance"]["operation_id"] != committed["maintenance"]["operation_id"]


@pytest.mark.parametrize("target", ["setup", "production", "stopped"])
@pytest.mark.parametrize("failure", ["audit", "state_after_audit"])
def test_confirmed_maintenance_requires_audited_bound_retry(
    tmp_path: Path, target: str, failure: str
) -> None:
    store = SQLiteStateStore(tmp_path, timeout=0.05)
    session = ConfigurationSession(store.authority)
    recorded = []
    with sqlite3.connect(store.path) as reservation:

        def interrupt_completion(payload: dict[str, Any]) -> None:
            if payload["action"] == "host_transition_commit_recorded":
                recorded.append(payload)
                assert session.state()["maintenance"] == payload["maintenance"]
                if failure == "audit":
                    raise OSError("audit acknowledgement unavailable")
                reservation.execute("BEGIN IMMEDIATE")

        session.audit = interrupt_completion
        with (
            pytest.raises((OSError, StateStoreError)),
            session.host_transition(target, "operator", "explicit", BINDING) as complete,
        ):
            complete()
        reservation.rollback()

    restarted = _session(tmp_path)
    state = restarted.state()
    assert state["phase"] == "maintenance" and state["maintenance"]["step"] == "pending"
    assert not restarted.setup_writes_allowed() and "last_host_transition" not in state
    with pytest.raises(ConfigurationConflict), restarted.admission():
        pytest.fail("incomplete transition admitted work")
    different = "production" if target == "setup" else "setup"
    with (
        pytest.raises(ConfigurationConflict),
        restarted.host_transition(different, "operator", "retry", BINDING),
    ):
        pytest.fail("retry changed the accepted target")
    with (
        pytest.raises(ConfigurationConflict),
        restarted.host_transition(target, "operator", "retry", "b" * 64),
    ):
        pytest.fail("retry changed the installation")
    restarted.audit = recorded.append
    with restarted.host_transition(
        target, "operator", "retry", BINDING, require_pending=True
    ) as retry:
        assert restarted.state() == state
        final = retry()
    first, repeat = recorded
    assert repeat == first
    assert first["version"] == state["maintenance"]["commit_version"]
    assert final["last_host_transition"] == {
        "operation_id": first["maintenance"]["operation_id"],
        "binding": BINDING,
        "target": target,
        "commit_version": first["version"],
    }
    assert final["version"] == first["version"] + 1
    assert final["phase"] == ("idle" if target == "production" else "maintenance")


def test_installed_cli_eof_preserves_pending_state_without_dashboard(tmp_path: Path) -> None:
    config = _config(tmp_path)
    agent = (config / "agent.json").read_bytes()
    shutil.copytree(Path(__file__).parents[1] / "config", config, dirs_exist_ok=True)
    (config / "agent.json").write_bytes(agent)
    command = [
        str(_console_script()),
        "--config",
        str(config),
        "maintenance",
        "--target",
        "setup",
        "--binding",
        BINDING,
        "--reason",
        "fixture explicit install",
    ]
    env = {key: value for key, value in os.environ.items() if not key.startswith("SCM_")}
    result = subprocess.run(
        command, input="", text=True, capture_output=True, cwd=tmp_path, env=env, timeout=20
    )
    assert result.returncode == 1, result.stderr
    assert "SAMUEL_MAINTENANCE_READY" in result.stdout
    state = _session(tmp_path / "runtime").state()
    assert state["phase"] == "maintenance" and state["maintenance"]["step"] == "pending"
    assert not state["active"] and not state["issues"]
    assert not list(tmp_path.rglob("*.sock"))
    # Existing state operator inspection remains available after losing the UI.
    status = subprocess.run(
        [str(_console_script()), "--config", str(config), "state", "status", "--json"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=20,
    )
    assert status.returncode == 0 and json.loads(status.stdout)["ok"]
    blocked = command.copy()
    blocked[blocked.index("--target") + 1] = "production"
    before = _session(tmp_path / "runtime").state()
    production = subprocess.run(
        blocked, input="COMMIT\n", text=True, capture_output=True, cwd=tmp_path, env=env, timeout=20
    )
    assert production.returncode == 2 and "SAMUEL_MAINTENANCE_READY" not in production.stdout
    assert _session(tmp_path / "runtime").state() == before
    retry = subprocess.run(
        command,
        input="COMMIT\n",
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=20,
    )
    assert retry.returncode == 0, retry.stderr
    assert _session(tmp_path / "runtime").state()["maintenance"]["step"] == "setup"


@pytest.mark.parametrize("blocker", ["scm", "authority"])
def test_new_blocker_before_completion_keeps_production_pending(
    tmp_path: Path, blocker: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _session(tmp_path)
    with session.host_transition("production", "operator", "explicit", BINDING) as complete:
        if blocker == "scm":
            session.external_blockers = lambda: ["SCM became unavailable"]
        else:
            monkeypatch.setattr(
                session.store, "authority_status", lambda: {"reconcile_required": True}
            )
        with pytest.raises(ConfigurationConflict):
            complete()
    assert _session(tmp_path).state()["maintenance"]["step"] == "pending"
    with pytest.raises(ConfigurationConflict), _session(tmp_path).admission():
        pass


def test_completion_callback_expires_when_operator_scope_exits(tmp_path: Path) -> None:
    session = _session(tmp_path)
    with session.host_transition("production", "operator", "explicit", BINDING) as complete:
        pass
    with pytest.raises(ConfigurationConflict):
        complete()
    assert _session(tmp_path).state()["phase"] == "maintenance"


def test_initial_setup_still_checks_durable_external_operation_intents(tmp_path: Path) -> None:
    from samuel.core.state import OperationIntentRecord

    session = _session(tmp_path)
    session.store.put_intent(
        OperationIntentRecord(
            intent_key="pending-pr",
            operation="create_pr",
            status="pending",
            issue_number=7,
            correlation_id="fixture",
            subject_key="fixture",
            payload={"preserve": True},
        )
    )
    before = session.store.get_intent("pending-pr")
    with (
        pytest.raises(ConfigurationConflict),
        session.host_transition("setup", "operator", "initial", BINDING),
    ):
        pass
    assert session.state()["version"] == 0
    assert session.store.get_intent("pending-pr") == before


@pytest.mark.parametrize("completion", ["COMMIT\n", "unexpected\n"])
def test_installed_cli_accepts_only_fixed_explicit_completion(
    tmp_path: Path, completion: str
) -> None:
    config = _config(tmp_path)
    agent_data = json.loads((config / "agent.json").read_text())
    agent_data["resume"] = {"enabled": True}
    agent = json.dumps(agent_data).encode()
    shutil.copytree(Path(__file__).parents[1] / "config", config, dirs_exist_ok=True)
    (config / "agent.json").write_bytes(agent)
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config),
            "maintenance",
            "--target",
            "setup",
            "--binding",
            BINDING,
            "--reason",
            "fixture",
        ],
        input=completion,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        timeout=20,
    )
    success = completion == "COMMIT\n"
    assert result.returncode == (0 if success else 1), result.stderr
    assert "LLM: adapter created" not in result.stderr
    assert "Health: critical=" not in result.stderr
    assert "Workflow '" not in result.stderr
    assert ("SAMUEL_MAINTENANCE_COMMITTED" in result.stdout) is success
    state = _session(tmp_path / "runtime").state()
    assert state["phase"] == "maintenance"
    assert state["maintenance"]["step"] == ("setup" if success else "pending")
    if success:
        report = subprocess.run(
            [
                str(_console_script()),
                "--config",
                str(config),
                "state",
                "status",
                "--read-only",
                "--json",
            ],
            capture_output=True,
            check=True,
            cwd=tmp_path,
            timeout=20,
        )
        observed = json.loads(report.stdout)["state"]["configuration"]
        assert observed["last_host_transition"] == state["last_host_transition"]
        assert (
            observed["maintenance"]["commit_version"]
            == state["last_host_transition"]["commit_version"]
        )


@pytest.mark.parametrize("hard", [False, True])
def test_installed_cli_process_loss_releases_locks_but_keeps_admission_closed(
    tmp_path: Path, hard: bool
) -> None:
    import selectors
    import signal

    config = _config(tmp_path)
    agent = (config / "agent.json").read_bytes()
    shutil.copytree(Path(__file__).parents[1] / "config", config, dirs_exist_ok=True)
    (config / "agent.json").write_bytes(agent)
    process = subprocess.Popen(
        [
            str(_console_script()),
            "--config",
            str(config),
            "maintenance",
            "--target",
            "setup",
            "--binding",
            BINDING,
            "--reason",
            "fixture interrupted",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
    )
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(15), "operator failed to announce readiness"
        assert process.stdout.readline().strip() == "SAMUEL_MAINTENANCE_READY"
        process.send_signal(signal.SIGKILL if hard else signal.SIGTERM)
        _, error = process.communicate(timeout=10)
        assert process.returncode == (-signal.SIGKILL if hard else 130), error
        restarted = _session(tmp_path / "runtime")
        assert restarted.state()["maintenance"]["step"] == "pending"
        with pytest.raises(ConfigurationConflict), restarted.admission():
            pass
        # Recovery uses the same state/binding and succeeds once the dead process
        # has relinquished OS locks. No timer or stale-PID assumption is used.
        with restarted.host_transition("setup", "operator", "retry", BINDING) as complete:
            complete()
        assert restarted.setup_writes_allowed()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_setup_recovery_can_repair_scm_but_production_always_rechecks(tmp_path: Path) -> None:
    session = _session(tmp_path)
    with session.host_transition("setup", "operator", "initial", BINDING):
        pass
    restarted = _session(tmp_path)
    restarted.external_blockers = lambda: ["SCM unavailable"]
    with restarted.host_transition("setup", "operator", "repair initial setup", BINDING) as done:
        done()
    with (
        pytest.raises(ConfigurationConflict, match="SCM unavailable"),
        restarted.host_transition("production", "operator", "start", BINDING),
    ):
        pass
    restarted.external_blockers = lambda: []
    with restarted.host_transition("production", "operator", "start", BINDING) as done:
        done()
    restarted.external_blockers = lambda: ["SCM unavailable"]
    with restarted.host_transition("setup", "operator", "repair normal setup", BINDING) as done:
        done()
    with pytest.raises(ConfigurationConflict), restarted.admission():
        pass


@pytest.mark.parametrize("target", ["setup", "production"])
def test_unknown_authority_blocks_every_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    session = _session(tmp_path)
    monkeypatch.setattr(session.store, "authority_status", lambda: {"reconcile_required": True})
    with (
        pytest.raises(ConfigurationConflict),
        session.host_transition(target, "operator", "requested", BINDING),
    ):
        pass
    assert session.state()["version"] == 0


def test_cli_reports_state_error_code_and_keeps_admission_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from samuel.cli import _cmd_maintenance

    session = _session(tmp_path)
    calls = 0

    def check_external() -> list[str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise StateStoreError("state_locked", "Runtime-state database is locked or busy")
        return []

    session.external_blockers = check_external
    monkeypatch.setattr("sys.stdin", io.StringIO("COMMIT\n"))
    args = SimpleNamespace(target="production", reason="explicit", binding=BINDING)
    bus = SimpleNamespace(configuration_session=session)
    assert _cmd_maintenance(bus, args) == 1  # type: ignore[arg-type]
    captured = capsys.readouterr()
    assert "SAMUEL_MAINTENANCE_READY" in captured.out
    assert "SAMUEL_MAINTENANCE_COMMITTED" not in captured.out
    assert "state_locked" in captured.err
    assert session.state()["maintenance"]["step"] == "pending"


def test_cli_provider_failure_never_exposes_exception_content_or_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from types import SimpleNamespace

    from samuel.cli import _cmd_maintenance

    session = _session(tmp_path)

    def unavailable() -> list[str]:
        raise OSError("fixture-secret-must-not-appear")

    session.external_blockers = unavailable
    bus = SimpleNamespace(configuration_session=session)
    args = SimpleNamespace(target="production", reason="explicit", binding=BINDING)
    assert _cmd_maintenance(bus, args) == 1  # type: ignore[arg-type]
    output = capsys.readouterr()
    assert "fixture-secret" not in output.out + output.err
    assert "SAMUEL_MAINTENANCE_READY" not in output.out
    assert session.state()["version"] == 0


def test_stopped_registration_never_releases_work_or_setup_writes(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.external_blockers = lambda: ["SCM not configured"]
    with session.host_transition(
        "stopped", "operator", "register existing source", BINDING
    ) as done:
        done()
    assert session.state()["maintenance"]["step"] == "stopped"
    assert not session.setup_writes_allowed()
    with pytest.raises(ConfigurationConflict), session.admission():
        pass
    with session.host_transition("setup", "operator", "configure source", BINDING) as done:
        done()
    assert session.setup_writes_allowed()


def test_backup_binding_survives_loss_before_cli_readiness_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from samuel.cli import _cmd_maintenance

    config = _config(tmp_path)
    shutil.copyfile(Path(__file__).parents[1] / "config/privacy.json", config / "privacy.json")
    store = SQLiteStateStore(tmp_path / "runtime")
    session = ConfigurationSession(store.authority)
    bus = SimpleNamespace(configuration_session=session, state_store=store)
    args = SimpleNamespace(
        target="production",
        reason="update",
        binding=BINDING,
        backup_before_transition=True,
        config=str(config),
    )

    def lost_output(*args, **kwargs):
        raise SystemExit("operator stream lost before READY")

    monkeypatch.setattr("builtins.print", lost_output)
    with pytest.raises(SystemExit, match="stream lost"):
        _cmd_maintenance(bus, args)  # type: ignore[arg-type]
    persisted = _session(tmp_path / "runtime").state()
    assert persisted["phase"] == "maintenance"
    backups = store.retention.list_managed_backups()
    assert len(backups) == 1
    assert persisted["maintenance"]["backup"]["backup_id"] == backups[0].backup_id
    assert persisted["maintenance"]["backup"]["digest"] == backups[0].digest


@pytest.mark.parametrize("completion", ["", "COMMIT\n"])
def test_same_bound_retry_reprints_original_backup_without_creating_another(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    completion: str,
) -> None:
    from samuel.cli import _cmd_maintenance

    config = _config(tmp_path)
    shutil.copyfile(Path(__file__).parents[1] / "config/privacy.json", config / "privacy.json")
    store = SQLiteStateStore(tmp_path / "runtime")
    session = ConfigurationSession(store.authority)
    bus = SimpleNamespace(configuration_session=session, state_store=store)
    args = SimpleNamespace(
        target="production",
        reason="update",
        binding=BINDING,
        backup_before_transition=True,
        config=str(config),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert _cmd_maintenance(bus, args) == 1  # type: ignore[arg-type]
    receipt = json.loads(capsys.readouterr().out.splitlines()[0].split(" ", 1)[1])
    pending = session.state()
    assert pending["maintenance"]["backup"] == receipt
    raw_backup = Path(receipt["path"]).read_bytes()
    args.backup_before_transition = False
    monkeypatch.setattr("sys.stdin", io.StringIO(completion))
    assert _cmd_maintenance(bus, args) == (0 if completion else 1)  # type: ignore[arg-type]
    output = capsys.readouterr().out.splitlines()
    assert json.loads(output[0].split(" ", 1)[1]) == receipt
    assert output[1] == "SAMUEL_MAINTENANCE_READY"
    assert len(store.retention.list_managed_backups()) == 1
    assert Path(receipt["path"]).read_bytes() == raw_backup
    if completion:
        assert session.state()["phase"] == "idle"
        assert "maintenance" not in session.state()
    else:
        assert session.state()["maintenance"]["backup"] == receipt
        args.binding = "b" * 64
        with pytest.raises(ConfigurationConflict, match="anderen Installation"):
            _cmd_maintenance(bus, args)  # type: ignore[arg-type]
        assert "SAMUEL_MAINTENANCE_" not in capsys.readouterr().out


def test_backup_binding_survives_audit_failure_before_returning_to_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from samuel.cli import _cmd_maintenance

    config = _config(tmp_path)
    shutil.copyfile(Path(__file__).parents[1] / "config/privacy.json", config / "privacy.json")
    store = SQLiteStateStore(tmp_path / "runtime")
    session = ConfigurationSession(store.authority)
    bus = SimpleNamespace(configuration_session=session, state_store=store)
    args = SimpleNamespace(
        target="production",
        reason="update",
        binding=BINDING,
        backup_before_transition=True,
        config=str(config),
    )

    def audit_failure(*args):
        raise OSError("audit unavailable")

    session.audit = audit_failure
    assert _cmd_maintenance(bus, args) == 1  # type: ignore[arg-type]
    assert "SAMUEL_MAINTENANCE_" not in capsys.readouterr().out
    persisted = _session(tmp_path / "runtime").state()
    assert persisted["phase"] == "maintenance"
    assert (
        persisted["maintenance"]["backup"]["backup_id"]
        == store.retention.list_managed_backups()[0].backup_id
    )


def test_arbitrary_callback_data_cannot_become_a_maintenance_receipt(tmp_path: Path) -> None:
    session = _session(tmp_path)
    before = session.state()
    with (
        pytest.raises(ValueError, match="Managed Backup"),
        session.host_transition(
            "production",
            "operator",
            "update",
            BINDING,
            before_transition=lambda: {"command": "unexpected"},  # type: ignore[arg-type,return-value]
        ),
    ):
        pytest.fail("invalid preparation output admitted")
    assert session.state() == before


def _exit_at_first_maintenance_output(root: str) -> None:
    import builtins

    from samuel.cli import _cmd_maintenance

    path = Path(root)
    store = SQLiteStateStore(path / "runtime")
    bus = SimpleNamespace(
        configuration_session=ConfigurationSession(store.authority), state_store=store
    )
    args = SimpleNamespace(
        target="production",
        reason="process-loss test",
        binding=BINDING,
        backup_before_transition=True,
        config=str(path / "config"),
    )

    def lost_output(*args, **kwargs):
        os._exit(88)

    builtins.print = lost_output
    _cmd_maintenance(bus, args)  # type: ignore[arg-type]
    os._exit(89)


def test_hard_process_exit_retains_backup_binding_and_releases_only_os_locks(tmp_path: Path):
    config = _config(tmp_path)
    shutil.copyfile(Path(__file__).parents[1] / "config/privacy.json", config / "privacy.json")
    SQLiteStateStore(tmp_path / "runtime")
    process = multiprocessing.Process(
        target=_exit_at_first_maintenance_output, args=(str(tmp_path),)
    )
    process.start()
    process.join(10)
    try:
        assert process.exitcode == 88
        session = _session(tmp_path / "runtime")
        pending = session.state()
        backup = pending["maintenance"]["backup"]
        assert pending["phase"] == "maintenance"
        assert Path(backup["path"]).is_file()
        with pytest.raises(ConfigurationConflict), session.admission():
            pytest.fail("process loss reopened admission")
        with session.host_transition(
            "production", "operator", "explicit recovery", BINDING
        ) as complete:
            assert session.state()["maintenance"]["backup"] == backup
            complete()
        assert session.state()["phase"] == "idle"
        assert Path(backup["path"]).is_file()
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)


@pytest.mark.parametrize("prior", ["idle", "completed", "setup", "foreign"])
def test_required_pending_transition_never_opens_a_replacement_operation(tmp_path, prior):
    session = _session(tmp_path)
    if prior != "idle":
        with session.host_transition("production", "operator", "original", BINDING) as complete:
            if prior == "completed":
                complete()
        if prior in {"setup", "foreign"}:
            state = session.state()
            state["maintenance"]["target" if prior == "setup" else "binding"] = (
                "setup" if prior == "setup" else "f" * 64
            )
            session._save(state)
    before = session.state()
    with (
        pytest.raises(ConfigurationConflict, match="offene Wartung"),
        session.host_transition(
            "production",
            "operator",
            "explicit recovery",
            BINDING,
            require_pending=True,
        ),
    ):
        pytest.fail("recovery created a new transition")
    assert session.state() == before


def test_required_pending_transition_can_finish_only_while_the_same_operation_is_open(tmp_path):
    session = _session(tmp_path)
    with session.host_transition("production", "operator", "original", BINDING):
        pass
    with session.host_transition(
        "production", "operator", "explicit recovery", BINDING, require_pending=True
    ) as complete:
        assert session.state()["phase"] == "maintenance"
        complete()
    assert session.state()["phase"] == "idle"
    with (
        pytest.raises(ConfigurationConflict),
        session.host_transition("production", "operator", "replay", BINDING, require_pending=True),
    ):
        pass
