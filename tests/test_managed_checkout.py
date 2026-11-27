import hashlib
import json
from pathlib import Path

import pytest

from tests.test_container_init import ROOT, _inputs
from tools.container_init import ContainerInitError, initialize, project_request_inputs


def test_new_personal_installation_defaults_and_retry(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["defaults"] = ROOT / "config"
    initialize(**inputs, first_local_account=True)
    config = inputs["config_root"] / "config"
    assert json.loads((config / "auth.json").read_bytes())["access_mode"] == "local_identity"
    models = config / "llm/defaults.json"
    original = json.loads(models.read_bytes())
    assert all(
        "provider" not in task and "model" not in task for task in original["tasks"].values()
    )
    original["tasks"]["planning"]["model"] = "operator-choice"
    models.write_text(json.dumps(original))
    assert initialize(**inputs, first_local_account=True) == "already_initialized"
    assert json.loads(models.read_bytes()) == original


def test_managed_start_binds_browser_confirmation_to_project(tmp_path: Path):
    project = dict(
        schema="project-registration-request.v1",
        host_source="/srv/samuel/project",
        container_target="/projects/codebase",
        repository="https://git.example/org/project",
        initial_revision="a" * 40,
    )
    request = tmp_path / "project-registration-request.json"
    request.write_text(json.dumps(project))
    env = tmp_path / "operator.env"
    env.write_text("SCM_PROVIDER=gitea\nSCM_URL=https://git.example\nSCM_REPO=org/project\n")
    with pytest.raises(FileNotFoundError):
        project_request_inputs(tmp_path, env, managed_start=True)
    marker = tmp_path / ".managed-start"
    marker.write_text(hashlib.sha256(request.read_bytes()).hexdigest() + "\n")
    marker.chmod(0o600)
    assert (
        project_request_inputs(tmp_path, env, managed_start=True)[-1] == project["initial_revision"]
    )
    request.write_text(json.dumps(dict(project, initial_revision="b" * 40)))
    with pytest.raises(ContainerInitError, match="Startanforderung"):
        project_request_inputs(tmp_path, env, managed_start=True)
