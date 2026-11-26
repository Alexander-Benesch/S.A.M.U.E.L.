"""Real operator shell and request parser; Docker registration is a recorded double."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from tests.test_cli_identity import _terminal_run
from tests.test_container_maintenance import _calls, _run, operator  # noqa: F401
from tools.container_init import ContainerInitError, project_request_inputs


@pytest.fixture
def prepared_operator(operator, tmp_path: Path):  # noqa: F811
    command, env, session, _ = operator
    command[2] = "start"
    root = tmp_path / "host/etc/samuel"
    (root / "config").mkdir(parents=True)
    (root / "compose").mkdir()
    for relative in (
        "var/lib/samuel",
        "var/log/samuel",
        "srv/samuel/workspaces",
        "srv/samuel/backups",
    ):
        (tmp_path / "host" / relative).mkdir(parents=True)
    (root / ".container-install.json").write_text("{}")
    (root / ".env").write_text(
        f"SCM_PROVIDER=gitea\nSCM_URL={env['SCM_URL']}\nSCM_REPO=fixture/project\n"
    )
    source = tmp_path / "dedicated-source"
    source.mkdir()
    request = {
        "schema": "project-registration-request.v1",
        "host_source": str(source),
        "container_target": "/projects/source",
        "repository": env["SCM_URL"] + "/fixture/project",
        "initial_revision": "a" * 40,
    }
    path = root / "config/project-registration-request.json"
    path.write_text(json.dumps(request))
    stat = tmp_path / "bin/stat"
    stat.write_text('#!/bin/sh\necho "0 0 755 1 2"\n')
    stat.chmod(0o755)
    docker = tmp_path / "bin/docker"
    docker.write_text(
        docker.read_text()
        .replace(
            "elif a[0]=='run':\n",
            """elif a[0]=='run':
    if 'project-request' in a:
        mounts={}
        for value in a:
            if value.startswith('type=bind,'):
                fields=dict(piece.split('=',1) for piece in value.split(',') if '=' in piece)
                mounts[fields['dst']]=fields['src']
        args=a[a.index('/bootstrap/container_init.py'):]
        args=[mounts.get(value,value) for value in args]
        os.execv(sys.executable,[sys.executable,*args])
    if 'register-project' in a:
        if os.environ.get('TEST_FAILURE')=='register-project':sys.exit(1)
        root=Path(a[a.index('--config-root')+1])
        (root/'config/project-binding.json').write_text('{}')
        (root/'compose/docker-compose.project.yml').write_text('services: {}')
""",
        )
        .replace(
            "        if os.environ.get('TEST_REAL_MAINTENANCE')=='1':",
            """        if os.environ.get('TEST_MUTATE_PROJECT'):
            request=Path(os.environ['TEST_MUTATE_PROJECT'])
            value=json.loads(request.read_text());value['initial_revision']='b'*40;request.write_text(json.dumps(value))
        if os.environ.get('TEST_REAL_MAINTENANCE')=='1':""",
        )
    )
    env["PATH"] = f"{tmp_path / 'bin'}:{sys.prefix}/bin:{os.environ['PATH']}"
    return command, env, session, path


def test_start_rechecks_approved_preparation_and_reuses_existing_registration(prepared_operator):
    command, env, session, path = prepared_operator
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = _run(command + ["--approve-project", digest], env)
    assert result.returncode == 0, result.stderr
    calls = _calls(env)
    reads = [i for i, call in enumerate(calls) if "project-request" in call]
    guard = next(i for i, call in enumerate(calls) if "maintenance" in call)
    stop = next(i for i, call in enumerate(calls) if "stop" in call)
    register = next(i for i, call in enumerate(calls) if "register-project" in call)
    start = next(i for i, call in enumerate(calls) if "up" in call)
    assert len(reads) == 2 and reads[0] < guard < reads[1] < stop < register < start
    assert "--project-revision" in calls[register] and "a" * 40 in calls[register]
    assert any(arg.endswith("docker-compose.project.yml") for arg in calls[start])
    assert all("docker.sock" not in arg for call in calls for arg in call)
    assert "--user" not in calls[reads[0]] and "--network" in calls[reads[0]]
    assert session.state()["phase"] == "idle"


@pytest.mark.parametrize("failure", ["approval", "changed", "register-project"])
def test_project_failure_cannot_start_production(prepared_operator, failure):
    command, env, session, path = prepared_operator
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if failure == "approval":
        digest = "0" * 64
    elif failure == "changed":
        env["TEST_MUTATE_PROJECT"] = str(path)
    else:
        env["TEST_FAILURE"] = failure
    result = _run(command + ["--approve-project", digest], env)
    assert result.returncode != 0
    expected = {
        "approval": "project approval differs",
        "changed": "project preparation changed",
        "register-project": "installation prerequisites failed",
    }
    assert expected[failure] in result.stderr
    calls = _calls(env)
    assert not any("up" in call for call in calls)
    if failure != "register-project":
        assert not any("stop" in call for call in calls)
    if failure != "approval":
        assert session.state()["maintenance"]["step"] == "pending"


def test_interactive_decline_keeps_setup_running(prepared_operator):
    command, env, _, _ = prepared_operator
    code, output = _terminal_run(
        command,
        [(b"Type yes to authorize this project registration and Production start: ", b"no\n")],
        env=env,
    )
    assert code != 0 and "not approved" in output
    assert not any("maintenance" in call or "stop" in call or "up" in call for call in _calls(env))


def test_request_parser_rechecks_current_scm_without_network(prepared_operator):
    _, _, _, path = prepared_operator
    env = path.parent.parent / ".env"
    assert project_request_inputs(path.parent, env)[-1] == "a" * 40
    env.write_text("SCM_PROVIDER=gitea\nSCM_URL=https://other.example.test\nSCM_REPO=other/repo\n")
    with pytest.raises(ContainerInitError, match="configured SCM"):
        project_request_inputs(path.parent, env)


def test_interactive_single_start_confirms_and_completes_registration(prepared_operator):
    command, env, session, _ = prepared_operator
    code, output = _terminal_run(
        command,
        [(b"Type yes to authorize this project registration and Production start: ", b"yes\n")],
        env=env,
    )
    assert code == 0, output
    assert sum("register-project" in call for call in _calls(env)) == 1
    assert session.state()["phase"] == "idle"
