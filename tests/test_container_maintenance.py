"""Real operator shell and CLI/state protocol; Docker/SCM remain explicit doubles."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from samuel.core.configuration_session import ConfigurationConflict
from tests.test_container_onboarding import _installer
from tests.test_host_maintenance import _session


@pytest.fixture
def operator(tmp_path: Path):
    command, env, config = _installer(tmp_path)
    agent = (config / "agent.json").read_bytes()
    shutil.copytree(Path(__file__).parents[1] / "config", config, dirs_exist_ok=True)
    (config / "agent.json").write_bytes(agent)
    requests: list[str] = []

    class SCM(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path.startswith("/api/v1/repos/fixture/project/issues?")
            assert self.headers["Authorization"] == "token fixture-only-token"
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SCM)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {key: value for key, value in env.items() if not key.startswith("SCM_")}
    env.update(
        TEST_REAL_MAINTENANCE="1",
        SCM_PROVIDER="gitea",
        SCM_URL=f"http://127.0.0.1:{server.server_port}",
        SCM_USER="fixture",
        SCM_TOKEN="fixture-only-token",
        SCM_REPO="fixture/project",
    )
    try:
        yield command[:-2], env, _session(tmp_path / "runtime"), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _run(command, env):
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)


def _calls(env):
    return [json.loads(line) for line in Path(env["TEST_DOCKER_TRACE"]).read_text().splitlines()]


def test_install_then_explicit_start_holds_same_state_through_host_actions(operator):
    command, env, session, requests = operator
    result = _run(command, env)
    assert result.returncode == 0, result.stderr
    assert session.state()["maintenance"]["step"] == "setup"
    with pytest.raises(ConfigurationConflict), session.admission():
        pass
    calls = _calls(env)
    begin = next(i for i, call in enumerate(calls) if "maintenance" in call)
    stop = next(i for i, call in enumerate(calls) if "stop" in call)
    setup = next(i for i, call in enumerate(calls) if "--non-interactive" in call)
    start = next(i for i, call in enumerate(calls) if "up" in call)
    assert begin < stop < setup < start
    assert any(arg.endswith("maintenance-healthcheck.json") for arg in calls[begin])
    assert not any(arg.endswith("maintenance-healthcheck.json") for arg in calls[start])
    assert not any(arg.endswith("docker-compose.setup.yml") for arg in calls[begin])
    assert any(arg.endswith("docker-compose.setup.yml") for arg in calls[setup])
    assert not any("labels=" in path for path in requests)  # No production admission check.
    production_command = result.stdout.split("same host privileges:\n", 1)[1].splitlines()[0]
    result = _run(["bash", "-c", production_command], env)
    assert result.returncode == 0, result.stderr
    assert "production runtime ready" in result.stdout
    assert session.state()["phase"] == "idle" and "maintenance" not in session.state()
    assert sum("labels=" in path for path in requests) == 6  # Three labels, before and after.
    with session.admission():
        pass
    assert not any("docker.sock" in arg for call in _calls(env) for arg in call)
    removals = [call for call in _calls(env) if call[0] == "rm"]
    assert len(removals) == 2
    assert all(len(call) == 2 and len(call[1]) == 64 for call in removals)


@pytest.mark.parametrize("failure", ["stop", "start", "readiness", "running-image"])
def test_host_failure_keeps_pending_state_and_bound_retry_recovers(operator, failure):
    command, env, session, _ = operator
    result = _run(command, dict(env, TEST_FAILURE=failure))
    assert result.returncode != 0
    assert "runtime ready" not in result.stdout and "same host privileges:" not in result.stdout
    pending = session.state()
    assert pending["phase"] == "maintenance"
    assert pending["maintenance"]["step"] == "pending"
    with pytest.raises(ConfigurationConflict), session.admission():
        pass
    command[2] = "setup"
    result = _run(command, env)
    assert result.returncode == 0, result.stderr
    assert session.state()["maintenance"]["binding"] == pending["maintenance"]["binding"]
    assert session.state()["maintenance"]["step"] == "setup"
    assert session.state()["revision"] == pending["revision"]


def test_existing_work_blocks_before_any_runtime_stop(operator):
    command, env, session, _ = operator
    state = session.state()
    state["issues"] = {"7": "waiting for approval"}
    session._save(state)
    before = session.state()
    result = _run(command, env)
    assert result.returncode != 0 and "runtime ready" not in result.stdout
    assert session.state() == before
    assert not any("stop" in call or "up" in call for call in _calls(env))


def test_slow_container_start_waits_for_real_admission_before_host_actions(operator, tmp_path):
    command, env, session, _ = operator
    docker = tmp_path / "bin/docker"
    docker.write_text(
        docker.read_text().replace(
            "        if os.environ.get('TEST_REAL_MAINTENANCE')=='1':",
            "        import time\n"
            "        time.sleep(63)\n"
            "        if os.environ.get('TEST_REAL_MAINTENANCE')=='1':",
        )
    )
    # Actual delay exceeds the former 60-second response window. The real CLI
    # still acquires State/SCM locks; the Docker double never invents READY.
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        metadata = tmp_path / "maintenance-container/metadata.json"
        while not metadata.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.02)
        assert metadata.exists()
        assert session.state()["phase"] == "idle"
        assert not any("stop" in call or "up" in call for call in _calls(env))
        stdout, stderr = process.communicate(timeout=90)
        assert process.returncode == 0, stderr
        assert "setup runtime ready" in stdout
        assert session.state()["maintenance"]["step"] == "setup"
        calls = _calls(env)
        assert next(i for i, call in enumerate(calls) if "maintenance" in call) < next(
            i for i, call in enumerate(calls) if "stop" in call
        )
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)


def test_expired_initial_response_never_acts_on_a_late_admission(operator, tmp_path):
    command, env, session, _ = operator
    docker = tmp_path / "bin/docker"
    docker.write_text(
        docker.read_text().replace(
            "        if os.environ.get('TEST_REAL_MAINTENANCE')=='1':",
            "        import time\n"
            "        time.sleep(0.4)\n"
            "        if os.environ.get('TEST_REAL_MAINTENANCE')=='1':",
        )
    )
    # Scale only the first response deadline for the stalled/late reply case.
    # Preserve $0, installer paths, remaining deadlines and the real State CLI.
    script = Path(command[1]).read_text()
    assert script.count("read -r -t 180 marker") == 1
    script = script.replace("read -r -t 180 marker", "read -r -t 0.1 marker", 1)
    result = _run(["bash", "-c", script, command[1], *command[2:]], env)
    assert result.returncode != 0 and "maintenance admission unavailable" in result.stderr
    assert "runtime ready" not in result.stdout
    assert not any("stop" in call or "up" in call for call in _calls(env))
    assert session.state()["maintenance"]["step"] == "pending"
    with pytest.raises(ConfigurationConflict), session.admission():
        pass


def test_parallel_operator_and_process_loss_cannot_release_work(operator, tmp_path):
    command, env, session, _ = operator
    docker = tmp_path / "bin/docker"
    text = docker.read_text()
    text = text.replace(
        "    if 'stop' in a and",
        "    if 'stop' in a and os.environ.get('TEST_HOLD')=='1':\n"
        "        import time\n"
        "        Path(os.environ['TEST_STOP_READY']).write_text('ready')\n"
        "        time.sleep(30)\n"
        "    if 'stop' in a and",
    )
    docker.write_text(text)
    marker = tmp_path / "stop-ready"
    first = subprocess.Popen(
        command,
        env=dict(env, TEST_HOLD="1", TEST_STOP_READY=str(marker)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            assert first.poll() is None
            time.sleep(0.02)
        assert marker.exists()
        second_command = command.copy()
        second_command[2] = "setup"
        second = _run(second_command, env)
        assert second.returncode != 0
        forced = _run([*second_command, "--recover-maintenance", "yes"], env)
        assert forced.returncode != 0 and "recovery denied" in forced.stderr
        assert sum("stop" in call for call in _calls(env)) == 1
        with pytest.raises(ConfigurationConflict), session.admission():
            pass
        os.killpg(first.pid, signal.SIGKILL)
        first.communicate(timeout=10)
        assert session.state()["maintenance"]["step"] == "pending"
        retained = _run(second_command, env)
        assert retained.returncode != 0
        assert session.state()["maintenance"]["step"] == "pending"
        recovered = _run([*second_command, "--recover-maintenance", "yes"], env)
        assert recovered.returncode == 0, recovered.stderr
        assert session.state()["maintenance"]["step"] == "setup"
    finally:
        if first.poll() is None:
            os.killpg(first.pid, signal.SIGKILL)
            first.communicate(timeout=10)


def test_cli_process_loss_does_not_allow_parallel_host_actions(operator, tmp_path):
    command, env, session, _ = operator
    docker = tmp_path / "bin/docker"
    docker.write_text(
        docker.read_text().replace(
            "    if 'up' in a and",
            "    if 'up' in a and os.environ.get('TEST_HOLD_UP')=='1':\n"
            "        import time\n"
            "        Path(os.environ['TEST_UP_READY']).write_text('ready')\n"
            "        while not Path(os.environ['TEST_UP_RELEASE']).exists():time.sleep(0.02)\n"
            "    if 'up' in a and",
        )
    )
    ready, release = tmp_path / "up-ready", tmp_path / "up-release"
    first = subprocess.Popen(
        command,
        env=dict(env, TEST_HOLD_UP="1", TEST_UP_READY=str(ready), TEST_UP_RELEASE=str(release)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            assert first.poll() is None
            time.sleep(0.02)
        assert ready.exists()
        metadata = tmp_path / "maintenance-container/metadata.json"
        os.kill(json.loads(metadata.read_text())["pid"], signal.SIGKILL)
        deadline = time.monotonic() + 5
        while json.loads(metadata.read_text())["status"] != "exited":
            assert time.monotonic() < deadline
            time.sleep(0.02)
        # The old OS lock is gone, but the installer still owns its Docker name.
        with session.store.configuration_lock(work=True):
            pass
        retry = command.copy()
        retry[2] = "setup"
        second = _run(retry, env)
        assert second.returncode != 0
        forced = _run([*retry, "--recover-maintenance", "yes"], env)
        assert forced.returncode != 0 and "operator process still exists" in forced.stderr
        assert sum("stop" in call for call in _calls(env)) == 1
        assert session.state()["maintenance"]["step"] == "pending"
        release.write_text("continue")
        output, _ = first.communicate(timeout=10)
        assert first.returncode != 0 and "runtime ready" not in output
        assert not metadata.exists()
        recovered = _run(retry, env)
        assert recovered.returncode == 0, recovered.stderr
    finally:
        if first.poll() is None:
            os.killpg(first.pid, signal.SIGKILL)
            first.communicate(timeout=10)


def test_recovery_never_removes_foreign_binding(operator, tmp_path):
    command, env, session, _ = operator
    result = _run(command, env)
    assert result.returncode == 0, result.stderr
    guard = tmp_path / "maintenance-container"
    guard.mkdir()
    metadata = guard / "metadata.json"
    data = {
        "name": "samuel-samuel-maintenance",
        "attempt": "foreign-attempt",
        "id": "e" * 64,
        "binding": "f" * 64,
        "status": "exited",
        "pid": 0,
        "operator": 0,
    }
    metadata.write_text(json.dumps(data))
    before = session.state()
    command[2] = "setup"
    result = _run([*command, "--recover-maintenance", "yes"], env)
    assert result.returncode != 0 and "recovery denied" in result.stderr
    assert json.loads(metadata.read_text()) == data
    assert session.state() == before


@pytest.mark.parametrize("operation", ["start", "setup", "doctor"])
def test_existing_operator_preflight_mounts_all_installation_roots_read_only(operator, operation):
    command, env, _, _ = operator
    assert _run(command, env).returncode == 0
    before = len(_calls(env))
    command[2] = operation
    result = _run(command, env)
    assert result.returncode == 0, result.stderr
    calls = _calls(env)[before:]
    checked = [call for call in calls if "verify-installed" in call]
    assert len(checked) == 1
    for destination in ("config-root", "data", "workspaces", "logs", "backups"):
        mounts = [arg for arg in checked[0] if f"dst=/prepare/{destination}," in arg]
        assert len(mounts) == 1 and mounts[0].endswith(",readonly")
    assert not any("init" in call for call in calls)


def test_missing_installed_directory_is_not_recreated_before_preflight(operator):
    command, env, _, _ = operator
    assert _run(command, env).returncode == 0
    root = Path(command[command.index("--root") + 1])
    missing = root / "var/log/samuel"
    missing.rmdir()
    before = len(_calls(env))
    command[2] = "start"
    result = _run(command, env)
    assert result.returncode != 0
    assert "existing installation directory missing" in result.stderr
    assert not missing.exists()
    assert not any(
        "init" in call
        or "verify-installed" in call
        or "maintenance" in call
        or "stop" in call
        or "up" in call
        for call in _calls(env)[before:]
    )
