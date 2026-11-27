"""Operator orchestration with a Docker double and the actual identity CLI.

This is not a Docker-host, release-distribution or browser qualification.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.test_cli_identity import _config, _console_script, _run, _terminal_run
from tests.test_container_init import IMAGE, ROOT, _published_kit


def _installer(tmp_path: Path, *, failure: str = "") -> tuple[list[str], dict[str, str], Path]:
    import hashlib

    config = _config(tmp_path)
    manifest, archive = _published_kit(tmp_path)
    manifest_file = tmp_path / "release-manifest.json"
    manifest_file.write_text(json.dumps(manifest))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text("""#!/usr/bin/env python3
import json,os,sys,subprocess,hashlib
from pathlib import Path
a=sys.argv[1:]
guard=Path(os.environ['TEST_DOCKER_TRACE']).parent/'maintenance-container'
with Path(os.environ['TEST_DOCKER_TRACE']).open('a') as stream:
    stream.write(json.dumps(a)+'\\n')
if a[:2]==['version','--format']: print('26.1.5')
elif a[:2]==['info','--format']: print('linux/amd64')
elif a[:2]==['compose','version']: print('2.26.1')
elif a[0]=='pull': pass
elif a[:2]==['image','inspect']:
    if '--format' not in a: print('[]')
    elif 'version' in a[a.index('--format')+1]: print('2.0.0a27')
    else: print('b'*40)
elif a[:3]==['exec','f'*64,'python']:
    assert '/api/v1/auth/mode' in a[-1] and 'local_identity' in a[-1]
elif a[0]=='run':
    if '-i' in a: sys.stdin.read()
    if 'verify' in a and os.environ.get('TEST_FAILURE')=='verify': sys.exit(1)
    if 'init' in a:
        root=Path(a[a.index('--config-root')+1]);root.mkdir(parents=True,exist_ok=True)
        (root/'.container-install.json').write_text('{}')
        if '--first-local-account' in a:
            auth=Path(os.environ['TEST_CONFIG'])/'auth.json'
            data=json.loads(auth.read_text());data['access_mode']='local_identity';auth.write_text(json.dumps(data))
    print('initialized')
elif a[:4]==['inspect','--type','container','--format']:
    cid='f'*64
    if a[4]=='{{.Id}}':print(cid)
    elif a[4]=='{{.Id}}|{{.State.Status}}' and a[-1]==cid:print(cid+'|running')
    else:sys.exit(1)
elif a[:2]==['inspect','--format']:
    if a[-1].endswith('-samuel-maintenance'):
        if not (guard/'metadata.json').exists():sys.exit(1)
        data=json.loads((guard/'metadata.json').read_text())
        if data['name']!=a[-1]:sys.exit(1)
        if 'attempt' in a[2]:print(data['id']+'|'+data['attempt'])
        else:
            proc=Path('/proc')/str(data['pid'])/'stat'
            running=proc.exists() and proc.read_text().split()[2]!='Z'
            status='running' if data['status']=='running' and running else 'exited'
            print(data['id']+'|'+status+'|'+os.environ['TEST_IMAGE']+'|'+data['binding']+'|'+str(data['operator']))
    else:print('wrong-image' if os.environ.get('TEST_FAILURE')=='running-image' else os.environ['TEST_IMAGE'])
elif a[0]=='rm':
    data=json.loads((guard/'metadata.json').read_text())
    if data['id']!=a[1]:sys.exit(1)
    (guard/'metadata.json').unlink();guard.rmdir()
elif a[0]=='compose':
    overlays=[a[i+1] for i,arg in enumerate(a) if arg=='-f' and a[i+1].endswith('maintenance-healthcheck.json')]
    if 'run' in a:
        assert len(overlays)==1
        assert json.loads(Path(overlays[0]).read_text())=={'services':{'samuel':{'healthcheck':{'disable':True}}}}
    else:
        assert not overlays, 'normal runtime must retain its healthcheck'
    if 'maintenance' in a:
        try:guard.mkdir()
        except FileExistsError:sys.exit(1)
        labels=dict(arg.split('=',1) for arg in a if arg.startswith('org.samuel.lifecycle.'))
        data={'name':a[a.index('--name')+1],'attempt':labels['org.samuel.lifecycle.attempt'],'binding':labels['org.samuel.lifecycle.binding'],'operator':int(labels['org.samuel.lifecycle.operator']),'status':'running','pid':os.getpid()}
        data['id']=hashlib.sha256(data['attempt'].encode()).hexdigest()
        (guard/'metadata.json').write_text(json.dumps(data))
        if os.environ.get('TEST_REAL_MAINTENANCE')=='1':
            args=a[a.index('maintenance'):]
            child=subprocess.Popen([os.environ['TEST_SAMUEL'],'--config',os.environ['TEST_CONFIG'],*args])
            data['pid']=child.pid;(guard/'metadata.json').write_text(json.dumps(data))
            code=child.wait()
        else:
            print('SAMUEL_MAINTENANCE_READY',flush=True)
            code=0 if sys.stdin.readline()=='COMMIT\\n' else 1
            if code==0:
                with Path(os.environ['TEST_DOCKER_TRACE']).open('a') as stream:stream.write(json.dumps(['maintenance_complete'])+'\\n')
                print('SAMUEL_MAINTENANCE_COMMITTED',flush=True)
        data['status']='exited';(guard/'metadata.json').write_text(json.dumps(data))
        sys.exit(code)
    if 'stop' in a and os.environ.get('TEST_FAILURE')=='stop':sys.exit(1)
    if 'exec' in a and os.environ.get('TEST_FAILURE')=='readiness': sys.exit(42)
    if 'up' in a and os.environ.get('TEST_FAILURE')=='start': sys.exit(1)
    if 'run' in a and 'identity' in a:
        action=a[a.index('identity')+1]
        if os.environ.get('TEST_FAILURE')==action: sys.exit(1)
        args=a[a.index('identity'):]
        cmd=[os.environ['TEST_SAMUEL'],'--config',os.environ['TEST_CONFIG'],*args]
        if os.environ.get('TEST_FAILURE')=='after-bootstrap':
            assert subprocess.run(cmd).returncode==0
            sys.exit(1)
        os.execv(cmd[0],cmd)
    elif 'ps' in a:
        trace = Path(os.environ['TEST_DOCKER_TRACE'])
        if any('up' in json.loads(line) for line in trace.read_text().splitlines()):
            print('test-container')
else: sys.exit(99)
""")
    docker.chmod(0o755)
    command = [
        "bash",
        str(ROOT / "tools/samuel-container"),
        "install",
        "--manifest",
        str(manifest_file),
        "--manifest-sha256",
        hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
        "--installer-archive",
        str(archive),
        "--root",
        str(tmp_path / "host"),
        "--admin-username",
        "admin",
    ]
    env = dict(
        os.environ,
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        TEST_DOCKER_TRACE=str(tmp_path / "docker-trace.jsonl"),
        TEST_SAMUEL=str(_console_script()),
        TEST_CONFIG=str(config),
        TEST_IMAGE=IMAGE,
        TEST_FAILURE=failure,
    )
    return command, env, config


@pytest.mark.parametrize("failure", ["", "verify", "bootstrap", "after-bootstrap", "mismatch"])
def test_operator_onboarding_uses_cli_and_never_starts_after_identity_failure(
    tmp_path: Path, failure: str
) -> None:
    command, env, config = _installer(tmp_path, failure=failure)
    password = b"operator-interactive-password"
    answers: list[tuple[bytes, bytes]] = []
    if failure not in {"verify", "bootstrap"}:
        answers.extend(
            [
                (b"Neues Dashboard-Passwort: ", password + b"\n"),
                (
                    b"Dashboard-Passwort wiederholen: ",
                    (b"different-password" if failure == "mismatch" else password) + b"\n",
                ),
            ]
        )
    if failure == "mismatch":
        answers.extend(
            [
                (b"Neues Dashboard-Passwort: ", password + b"\n"),
                (b"Dashboard-Passwort wiederholen: ", password + b"\n"),
            ]
        )
    code, output = _terminal_run(command, answers, env=env)
    calls = [
        json.loads(line) for line in (tmp_path / "docker-trace.jsonl").read_text().splitlines()
    ]
    auth = json.loads((config / "auth.json").read_text())
    principals = json.loads(_run(config, "status").stdout)["identity"]["principals"]
    assert password.decode() not in output
    assert password.decode() not in json.dumps(calls)
    assert not any("/var/run/docker.sock" in arg for call in calls for arg in call)
    if failure in {"", "mismatch"}:
        assert "127.0.0.1:17777" in output
        assert ("Bitte erneut eingeben" in output) == (failure == "mismatch")
        assert code == 0
        assert auth["access_mode"] == "local_identity"
        assert len(principals) == 1 and principals[0]["roles"] == ["administrator"]
        bootstrap = next(i for i, call in enumerate(calls) if "bootstrap" in call)
        start = next(i for i, call in enumerate(calls) if "up" in call)
        assert bootstrap < start
        assert not any("cutover" in call for call in calls)
        assert (
            calls[bootstrap][calls[bootstrap].index("--reason") + 1]
            == "Erstinstallation mit persönlichen Konten"
        )
        assert "Grund für die Umstellung" not in output
        assert "Sign in with the new local administrator" in output
        assert "without --admin-username" in output
        next_command = output.split("same host privileges:\r\n", 1)[1].splitlines()[0]
        assert "--admin-username" not in next_command
        assert "--prompt-password" not in next_command
        assert "fresh installation" not in next_command
    else:
        assert code != 0
        assert auth["access_mode"] == (
            "legacy_api_key" if failure == "verify" else "local_identity"
        )
        assert not any("up" in call for call in calls)
        assert "setup runtime ready" not in output
        assert "same host privileges:" not in output
        assert len(principals) == (1 if failure == "after-bootstrap" else 0)
        if failure == "verify":
            assert not (tmp_path / "host").exists()
            assert not any("bootstrap" in call for call in calls)


@pytest.mark.parametrize(
    "relative",
    [
        "var/lib/samuel/state.sqlite3",
        "var/log/samuel/agent.jsonl",
        "etc/samuel/config/auth.json",
        "srv/samuel/project/README.md",
    ],
)
def test_existing_unidentified_installation_is_preserved(tmp_path: Path, relative: str) -> None:
    command, env, _ = _installer(tmp_path)
    original = tmp_path / "host" / relative
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"existing installation data")
    code, output = _terminal_run(command, [], env=env)
    assert code != 0 and "Vorhandene Daten" in output
    assert original.read_bytes() == b"existing installation data"
    assert not (tmp_path / "host/var/lib/samuel-installer/pending").exists()
    calls = [
        json.loads(line) for line in (tmp_path / "docker-trace.jsonl").read_text().splitlines()
    ]
    assert not any("identity" in call or "init" in call or "up" in call for call in calls)


@pytest.mark.parametrize("sudo", [False, True])
@pytest.mark.parametrize(
    "filename", ["release", "release with spaces", "release'$(touch injected)`touch injected2`;"]
)
def test_printed_production_command_round_trips_exact_installation_from_another_directory(
    tmp_path: Path, sudo: bool, filename: str
) -> None:
    command, env, _ = _installer(tmp_path)
    command = command[:-2]  # Exercise the compatible noninteractive installation too.
    for option, suffix in [("--manifest", ".json"), ("--installer-archive", ".tar.gz")]:
        index = command.index(option) + 1
        target = tmp_path / (filename + suffix)
        Path(command[index]).rename(target)
        command[index] = str(target)
    command.extend(["--port", "18779", "--project", "separate-codebase"])
    env.pop("SUDO_UID", None)
    if sudo:
        env["SUDO_UID"] = "1000"
    # No privilege escalation in this test; record and forward the printed prefix.
    sudo_double = tmp_path / "bin/sudo"
    sudo_double.write_text('#!/bin/bash\nprintf called > "$TEST_SUDO_TRACE"\nexec "$@"\n')
    sudo_double.chmod(0o755)
    env["TEST_SUDO_TRACE"] = str(tmp_path / "sudo-trace")
    installed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    assert installed.returncode == 0, installed.stderr
    next_command = installed.stdout.split("same host privileges:\n", 1)[1].splitlines()[0]
    assert "--admin-username" not in next_command
    assert "--prompt-password" not in next_command
    trace = Path(env["TEST_DOCKER_TRACE"])
    install_calls = [json.loads(line) for line in trace.read_text().splitlines()]
    assert sum("up" in call for call in install_calls) == 1
    assert not any("SAMUEL_INSTALL_EXPECTED_MODE=production" in call for call in install_calls)
    # The double does not create the real receipt; existing initializer tests cover it.
    (tmp_path / "host/etc/samuel/.container-install.json").write_text("{}")
    elsewhere = tmp_path / "other-working-directory"
    elsewhere.mkdir()
    trace.write_text("")
    started = subprocess.run(
        ["bash", "-c", next_command],
        cwd=elsewhere,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert started.returncode == 0, started.stderr
    assert "production runtime ready" in started.stdout
    assert "same host privileges:" not in started.stdout
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    initialization = next(call for call in calls if "verify-installed" in call)
    assert initialization[initialization.index("--port") + 1] == "18779"
    assert initialization[initialization.index("--project") + 1] == "separate-codebase"
    assert initialization[initialization.index("--config-root") + 1] == str(
        tmp_path / "host/etc/samuel"
    )
    assert (
        initialization[initialization.index("--manifest-sha256") + 1]
        == command[command.index("--manifest-sha256") + 1]
    )
    verification = next(i for i, call in enumerate(calls) if "verify" in call)
    activation = next(i for i, call in enumerate(calls) if "up" in call)
    assert verification < activation
    assert not any("bootstrap" in call or "cutover" in call for call in calls)
    assert not (elsewhere / "injected").exists()
    assert not (elsewhere / "injected2").exists()
    assert (tmp_path / "sudo-trace").exists() == (sudo and os.geteuid() == 0)


@pytest.mark.parametrize("failure", ["start", "readiness", "running-image"])
def test_failed_setup_start_never_offers_the_production_command(
    tmp_path: Path, failure: str
) -> None:
    command, env, _ = _installer(tmp_path, failure=failure)
    result = subprocess.run(command[:-2], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "same host privileges:" not in result.stdout
    assert "setup runtime ready" not in result.stdout


@pytest.mark.parametrize("operation", ["install", "setup", "start"])
def test_onboarding_refuses_noninteractive_or_noninstall_calls(
    tmp_path: Path, operation: str
) -> None:
    command, env, _ = _installer(tmp_path)
    command[2] = operation
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    expected = (
        "interactive terminal" if operation == "install" else "requires the install operation"
    )
    assert expected in result.stderr
    assert not (tmp_path / "docker-trace.jsonl").exists()
    assert not (tmp_path / "host").exists()


def test_resume_preserves_administrator_after_interrupted_bootstrap(tmp_path: Path) -> None:
    command, env, config = _installer(tmp_path, failure="after-bootstrap")
    password = b"private-test-password"
    code, output = _terminal_run(
        command,
        [
            (b"Neues Dashboard-Passwort: ", password + b"\n"),
            (b"Dashboard-Passwort wiederholen: ", password + b"\n"),
        ],
        env=env,
    )
    assert code != 0 and "administrator bootstrap failed" in output
    marker = tmp_path / "host/var/lib/samuel-installer/pending"
    assert marker.is_file()
    before = _run(config, "status").stdout
    env["TEST_FAILURE"] = ""
    code, output = _terminal_run(command, [], env=env)
    assert code == 0, output
    assert "Neues Dashboard-Passwort:" not in output
    assert "setup runtime ready" in output
    assert not marker.exists()
    assert (
        json.loads(before)["identity"]["principals"]
        == json.loads(_run(config, "status").stdout)["identity"]["principals"]
    )
