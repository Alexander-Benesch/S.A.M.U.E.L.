"""Actual Bash + maintenance CLI/State, with explicit Docker/release helper doubles.

This covers ordering, approval and persistent admission, not OCI qualification.
The helper functions and actual container qualification have separate evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.configuration_session import ConfigurationConflict
from tests.test_cli_identity import _terminal_run
from tests.test_container_maintenance import _calls, _run
from tests.test_container_maintenance import operator as operator


@pytest.fixture
def update_operator(operator, tmp_path):
    command, env, session, requests = operator
    installed = _run(command, env)
    assert installed.returncode == 0, installed.stderr
    command[2] = "start"
    started = _run(command, env)
    assert started.returncode == 0, started.stderr
    assert session.state()["phase"] == "idle"

    Path(env["TEST_DOCKER_TRACE"]).write_text("")
    docker = tmp_path / "bin/docker"
    script = docker.read_text()
    script = script.replace(
        "    if '-i' in a: sys.stdin.read()",
        """    if 'update-context' in a:
        destination=next(x.split('src=',1)[1].split(',dst=',1)[0] for x in a if ',dst=/bootstrap/operator-context' in x)
        for name in ('compose.env','maintenance.yml'): (Path(destination)/name).write_text('fixture-only')
        print('SAMUEL_UPDATE_CONTEXT\\n2.0.0a34\\ninstallers/'+'d'*64+'\\n-\\n-\\nsource')
        sys.exit(0)
    if 'update-step' in a:
        step=a[a.index('--update-step')+1]
        if os.environ.get('TEST_FAILURE')==step: sys.exit(1)
        print(json.dumps({'stage':step}))
        sys.exit(0)
    if '-i' in a: sys.stdin.read()""",
    )
    script = script.replace(
        "        if 'attempt' in a[2]:print(data['id']+'|'+data['attempt'])",
        """        if '.State.Running' in a[2]:print('true|'+data['attempt']+'|'+data['binding'])
        elif 'attempt' in a[2]:print(data['id']+'|'+data['attempt'])""",
    )
    script = script.replace(
        "elif a[0]=='rm':",
        "elif a[0]=='ps': pass\nelif a[0]=='rm':",
    )
    docker.write_text(script)
    cache = tmp_path / "host/srv/samuel/release-cache"
    cache.mkdir(mode=0o700)
    (cache / "installers" / ("d" * 64)).mkdir(parents=True)
    preparations = cache / "update-preparations"
    preparations.mkdir(mode=0o700)
    raw = json.dumps({"target_image": env["TEST_IMAGE"]}).encode()
    binding = hashlib.sha256(raw).hexdigest()
    preparation = preparations / (binding + ".json")
    preparation.write_bytes(raw)
    preparation.chmod(0o600)
    env["TEST_UPDATE_BINDING"] = binding
    command[2] = "update"
    command += ["--update-preparation", str(preparation), "--update-preparation-sha256", binding]
    yield command, env, session


def run_update(command, env, answer=b"yes\n"):
    return _terminal_run(
        command, [(b"Type yes to authorize this exact update operation: ", answer)], env=env
    )


def test_operator_update_holds_real_admission_until_target_readiness(update_operator):
    command, env, session = update_operator
    code, output = run_update(command, env)
    assert code == 0, output
    calls = _calls(env)
    begin = next(i for i, c in enumerate(calls) if "maintenance" in c)
    stop = next(i for i, c in enumerate(calls) if "stop" in c)
    steps = {
        c[c.index("--update-step") + 1]: i for i, c in enumerate(calls) if "--update-step" in c
    }
    start = next(i for i, c in enumerate(calls) if "up" in c)
    readiness = next(i for i, c in enumerate(calls) if "exec" in c)
    assert begin < stop < steps["capture"] < steps["toolchain"] < steps["apply"] < start < readiness
    assert "--backup-before-transition" in calls[begin]
    assert env["TEST_UPDATE_BINDING"] in calls[begin]
    assert session.state()["phase"] == "idle"
    store = SQLiteStateStore(Path(env["TEST_CONFIG"]).parent / "runtime", read_only=True)
    assert len(store.retention.list_managed_backups()) == 1
    assert "production runtime ready" in output
    assert not any("docker.sock" in arg for c in calls for arg in c)


@pytest.mark.parametrize("failure", ["stop", "capture", "toolchain", "apply", "start", "readiness"])
def test_failed_update_stays_closed_until_explicit_bound_recovery(update_operator, failure):
    command, env, session = update_operator
    code, output = run_update(command, dict(env, TEST_FAILURE=failure))
    assert code != 0 and "production runtime ready" not in output
    pending = session.state()["maintenance"]
    assert pending["binding"] == env["TEST_UPDATE_BINDING"] and pending["step"] == "pending"
    assert "backup" in pending
    with pytest.raises(ConfigurationConflict), session.admission():
        pass
    code, output = run_update(command + ["--recover-update", env["TEST_UPDATE_BINDING"]], env)
    assert code == 0, output
    assert session.state()["phase"] == "idle"
    assert "--resume-pending" in next(c for c in reversed(_calls(env)) if "maintenance" in c)


@pytest.mark.parametrize("restoration", [False, True])
def test_update_admission_failure_points_to_bound_update_recovery(request, restoration):
    command, env, session = request.getfixturevalue(
        "restoration_operator" if restoration else "update_operator"
    )
    before = session.state()
    docker = Path(env["PATH"].split(":")[0]) / "docker"
    script = docker.read_text()
    marker = "    if 'maintenance' in a:"
    assert marker in script
    docker.write_text(
        script.replace(
            marker,
            "    if 'maintenance' in a and os.environ.get('TEST_FAILURE')=='admission': sys.exit(1)\n"
            + marker,
        )
    )
    run = run_restoration if restoration else run_update
    code, output = run(command, dict(env, TEST_FAILURE="admission"))
    assert code != 0
    error = next(
        line for line in output.splitlines() if "maintenance admission unavailable" in line
    )
    flag = "--restore-update" if restoration else "--recover-update"
    assert flag + " " + env["TEST_UPDATE_BINDING"] in error
    assert "--recover-maintenance" not in error
    assert "previous operator process ended" in error
    assert session.state() == before
    assert not any("stop" in call or "up" in call for call in _calls(env))


def test_declined_update_never_begins_maintenance_or_host_mutation(update_operator):
    command, env, session = update_operator
    before = session.state()
    code, output = run_update(command, env, b"no\n")
    assert code != 0 and "not approved" in output
    assert session.state() == before
    assert not any(
        "maintenance" in c or "stop" in c or "up" in c or "update-step" in c for c in _calls(env)
    )


@pytest.mark.parametrize("fault", ["digest", "image", "mode", "parent"])
def test_unbound_executable_image_is_rejected_before_any_image_is_pulled_or_executed(
    update_operator, fault
):
    command, env, _session = update_operator
    preparation = Path(command[command.index("--update-preparation") + 1])
    if fault == "digest":
        preparation.write_text("changed")
    elif fault == "image":
        command += ["--image", "untrusted/image@sha256:" + "f" * 64]
    elif fault == "mode":
        preparation.chmod(0o644)
    else:
        preparation.parent.chmod(0o777)
    result = _run(command, env)
    assert result.returncode != 0
    assert not any(call[0] in {"run", "pull"} for call in _calls(env))


def test_recovery_validator_can_reconstruct_private_ownership_without_active_write_mounts(
    update_operator,
):
    command, env, session = update_operator
    code, _output = run_update(command, dict(env, TEST_FAILURE="apply"))
    assert code != 0 and session.state()["phase"] == "maintenance"
    docker = Path(env["PATH"].split(":")[0]) / "docker"
    source = docker.read_text()
    assert "\\nsource" in source
    docker.write_text(source.replace("\\nsource", "\\npending"))
    Path(env["TEST_DOCKER_TRACE"]).write_text("")
    code, output = run_update(command + ["--recover-update", env["TEST_UPDATE_BINDING"]], env)
    assert code == 0, output
    calls = _calls(env)
    steps = {c[c.index("--update-step") + 1]: c for c in calls if "--update-step" in c}
    for step in ("verify", "toolchain"):
        call = steps[step]
        capabilities = {call[i + 1] for i, item in enumerate(call) if item == "--cap-add"}
        assert capabilities == {"DAC_READ_SEARCH", "CHOWN", "FOWNER"}
        assert call[call.index("--network") + 1] == "none"
        assert "--read-only" in call and "--privileged" not in call
        mounts = [call[i + 1] for i, item in enumerate(call) if item == "--mount"]
        active = [m for m in mounts if "dst=/prepare/" in m and "toolchains" not in m]
        assert active and all(m.endswith(",readonly") for m in active)
        assert all("docker.sock" not in m for m in mounts)
        assert any("dst=/bootstrap/cache,readonly" in m for m in mounts)
    assert session.state()["phase"] == "idle"


@pytest.fixture
def restoration_operator(update_operator, tmp_path):
    command, env, session = update_operator
    code, output = run_update(command, dict(env, TEST_FAILURE="start"))
    assert code != 0, output
    backup = session.state()["maintenance"]["backup"]["path"]
    source_image = "fixture/source@sha256:" + "e" * 64
    overlay = (
        tmp_path
        / "host/srv/samuel/release-cache/update-captures"
        / env["TEST_UPDATE_BINDING"]
        / ("e" * 32)
        / "restore-compose.json"
    )
    overlay.parent.mkdir(parents=True, mode=0o700)
    overlay.write_text(json.dumps({"services": {"samuel": {"healthcheck": {"disable": True}}}}))
    env = dict(env, TEST_SOURCE_IMAGE=source_image, TEST_RESTORE_BACKUP=backup)
    docker = tmp_path / "bin/docker"
    source = docker.read_text().replace("\\nsource", "\\npending")
    source = source.replace(
        "    if '--format' not in a: print('[]')",
        """    if a[-1]==os.environ.get('TEST_SOURCE_IMAGE'):
        print('2.0.0a34' if '--format' in a and 'version' in a[a.index('--format')+1] else 'c'*40)
    elif '--format' not in a: print('[]')""",
    )
    source = source.replace(
        "        print(json.dumps({'stage':step}))",
        """        if step=='restore':
            binding=os.environ['TEST_UPDATE_BINDING']
            print('RESTORE_BACKUP /app/data/backups/fixture.sqlite3 sha256:'+'f'*64)
            print('RESTORE_SOURCE '+os.environ['TEST_SOURCE_IMAGE']+' '+'c'*40+' 2.0.0a34')
            print('RESTORE_CONTEXT update-captures/'+binding+'/'+'e'*32+'/restore-compose.json')
            print('RESTORE_INSTALLER artifacts/'+'a'*64+'/manifest.json '+'a'*64+' artifacts/'+'b'*64+'/source.tar.gz installers/'+'d'*64)
        print(json.dumps({'stage':step}))""",
    )
    source = source.replace(
        "elif a[0]=='compose':",
        """elif a[0]=='compose':
    if a[-2:]==['config','--images']:
        print(os.environ['TEST_SOURCE_IMAGE']);sys.exit(0)
    if 'state' in a and 'restore' in a:
        if os.environ.get('TEST_RESTORE_STATE_FAILURE')=='1':sys.exit(1)
        overlay=next(a[i+1] for i,arg in enumerate(a) if arg=='-f' and a[i+1].endswith('restore-compose.json'))
        assert json.loads(Path(overlay).read_text())['services']['samuel']['healthcheck']=={'disable':True}
        args=a[a.index('state'):];args[args.index('--source')+1]=os.environ['TEST_RESTORE_BACKUP']
        os.execv(os.environ['TEST_SAMUEL'],[os.environ['TEST_SAMUEL'],'--config',os.environ['TEST_CONFIG'],*args])
""",
    )
    docker.write_text(source)
    Path(env["TEST_DOCKER_TRACE"]).write_text("")
    return command + ["--restore-update", env["TEST_UPDATE_BINDING"]], env, session


def run_restoration(command, env, answer=b"yes\n"):
    return _terminal_run(
        command,
        [(b"Type yes to authorize restoration of the source release and State backup: ", answer)],
        env=env,
    )


def test_restore_uses_existing_state_recovery_without_committing_superseded_maintenance(
    restoration_operator,
):
    command, env, session = restoration_operator
    before = session.store.authority_status()
    code, output = run_restoration(command, env)
    assert code == 0, output
    assert "Reconciliation and any required identity recovery are still pending" in output
    after = session.store.authority_status()
    assert after["reconcile_required"] and after["epoch"] > before["epoch"]
    assert after["instance"] != before["instance"]
    with pytest.raises(ConfigurationConflict), session.admission():
        pass
    calls = _calls(env)
    restore = next(i for i, c in enumerate(calls) if "--update-step" in c and "restore" in c)
    state_restore = next(i for i, c in enumerate(calls) if "state" in c and "restore" in c)
    assert next(i for i, c in enumerate(calls) if "stop" in c) < restore < state_restore
    assert not any("up" in c or c == ["maintenance_complete"] for c in calls)
    assert "production runtime ready" not in output


def test_declined_restoration_does_not_stop_or_restore(restoration_operator):
    command, env, session = restoration_operator
    before = session.state()
    code, output = run_restoration(command, env, b"no\n")
    assert code != 0 and "not approved" in output
    assert session.state() == before
    assert not any("stop" in c or "restore" in c or "up" in c for c in _calls(env))


def test_failed_state_restore_keeps_runtime_stopped_and_prints_existing_local_recovery(
    restoration_operator,
):
    command, env, session = restoration_operator
    code, output = run_restoration(command, dict(env, TEST_RESTORE_STATE_FAILURE="1"))
    assert code != 0 and "State restoration did not complete" in output
    assert "state status --json" in output and "reconcile-scan" in output
    assert "start" in output and "--manifest-sha256" in output
    assert session.state()["maintenance"]["step"] == "pending"
    assert not any("up" in c or c == ["maintenance_complete"] for c in _calls(env))
