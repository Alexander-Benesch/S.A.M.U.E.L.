from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from samuel.core.config import EvalSchema, GatesConfigSchema, VerifierToolchainSchema
from samuel.core.evaluation_subject import gate_policy_binding
from samuel.core.test_runner import (
    VerifierRunnerPolicy,
    artifact_files,
    check_test_runner_installation,
    validate_toolchain,
)
from samuel.project_binding import prepare_project_for_release, verify_project_registration
from samuel.slices.ac_verification.handler import _check_test
from samuel.verifier_toolchain import prepare_toolchain_for_release
from tests.test_project_binding import _register, _source_snapshot
from tests.test_project_binding import project_installation as project_installation
from tests.test_verifier_toolchain import toolchain as toolchain

SOURCE_IMAGE = "fixture/samuel@sha256:" + "a" * 64
TARGET_IMAGE = "fixture/samuel@sha256:" + "b" * 64


@pytest.fixture
def project_update(project_installation):
    root, repo, revision = project_installation
    path = root / ".container-install.json"
    source = json.loads(path.read_bytes())
    source.update(
        version="2.0.0a34", revision="a" * 40, manifest_sha256="c" * 64, image=SOURCE_IMAGE
    )
    path.write_text(json.dumps(source))
    original = _register(project_installation)
    target = {
        **source,
        "version": "2.0.0a35",
        "revision": "b" * 40,
        "manifest_sha256": "d" * 64,
        "image": TARGET_IMAGE,
    }
    return root, repo, original, target


def test_release_preparation_preserves_project_identity_and_writes_nothing(project_update):
    root, repo, original, target = project_update
    before_source = _source_snapshot(repo)
    before_config = _source_snapshot(root)
    raw = json.dumps(target).encode()
    result = prepare_project_for_release(root, raw)
    assert result == {**original, "installation_sha256": hashlib.sha256(raw).hexdigest()}
    assert _source_snapshot(repo) == before_source
    assert _source_snapshot(root) == before_config
    assert verify_project_registration(root) == original
    assert result is not None
    assert result["initial_revision"] == original["initial_revision"]


def test_project_history_can_advance_without_becoming_a_new_registration(project_update):
    root, repo, original, target = project_update
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "operator advancement"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    before = _source_snapshot(repo)
    result = prepare_project_for_release(root, json.dumps(target).encode())
    assert result is not None
    assert result["initial_revision"] == original["initial_revision"]
    assert _source_snapshot(repo) == before  # No checkout/reset of the original registration SHA.


@pytest.mark.parametrize(
    "field,value",
    [
        ("uid", 32123),
        ("gid", 32123),
        ("work_root", "/other"),
        ("data_root", "/other"),
        ("project", "other"),
        ("extra", "untrusted"),
        ("version", "2.0.0a34"),
        ("manifest_sha256", "invalid"),
        ("revision", "main"),
        ("image", "fixture/samuel:latest"),
    ],
)
def test_project_rebinding_cannot_change_installation_scope(project_update, field, value):
    root, _, _, target = project_update
    target[field] = value
    before = _source_snapshot(root)
    with pytest.raises(ValueError):
        prepare_project_for_release(root, json.dumps(target).encode())
    assert _source_snapshot(root) == before


def test_drifted_previous_registration_cannot_be_rebound(project_update):
    root, _, _, target = project_update
    (root / ".container-install.json").write_text("{}")
    with pytest.raises(ValueError, match="binding changed"):
        prepare_project_for_release(root, json.dumps(target).encode())


def test_unregistered_installation_is_not_silently_given_a_project(project_update):
    root, _, _, target = project_update
    (root / "config/project-binding.json").unlink()
    (root / "compose/docker-compose.project.yml").unlink()
    assert prepare_project_for_release(root, json.dumps(target).encode()) is None


@pytest.fixture
def toolchain_update(toolchain, tmp_path, monkeypatch):
    import samuel.core.test_runner as runner
    import samuel.verifier_toolchain as operator

    path = Path(toolchain.manifest)
    manifest = json.loads(path.read_bytes())
    target_python = {
        **manifest["python"],
        "runtime_version": "2.0.0a35",
        "runtime_revision": "b" * 40,
    }
    manifest["python"].update(runtime_version="2.0.0a34", runtime_revision="a" * 40)
    manifest["runtime_image"] = SOURCE_IMAGE
    path.write_text(json.dumps(manifest, sort_keys=True))
    old = VerifierToolchainSchema(
        manifest=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(runner, "python_identity", lambda: dict(target_python))
    monkeypatch.setattr(operator, "python_identity", lambda: dict(target_python))
    root = tmp_path / "new-toolchain"
    root.mkdir()
    args = {
        "root": root,
        "previous": old,
        "source_version": "2.0.0a34",
        "source_revision": "a" * 40,
        "source_image": SOURCE_IMAGE,
        "target_image": TARGET_IMAGE,
    }
    return args, target_python


def test_target_toolchain_rechecks_bytes_and_runs_real_pytest_without_old_evidence(
    toolchain_update, tmp_path, monkeypatch
):
    args, _ = toolchain_update
    old = args["previous"]
    previous = Path(old.manifest).parent
    before = _source_snapshot(previous)
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_toolchain(old)
    binding = VerifierToolchainSchema(**prepare_toolchain_for_release(**args))
    manifest = validate_toolchain(binding)
    assert manifest["runtime_image"] == TARGET_IMAGE
    assert manifest["files"] == artifact_files(previous / "packages")
    assert _source_snapshot(previous) == before
    assert binding.sha256 != old.sha256
    assert (
        gate_policy_binding(GatesConfigSchema(), EvalSchema(verifier_toolchain=old), None)[
            "policy_digest"
        ]
        != gate_policy_binding(GatesConfigSchema(), EvalSchema(verifier_toolchain=binding), None)[
            "policy_digest"
        ]
    )
    assert args["root"].stat().st_mode & 0o777 == 0o555
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_update.py").write_text(
        'import os\ndef test_ok():\n assert "SCM_TOKEN" not in os.environ\n assert "PYTHONPATH" not in os.environ\n'
    )
    monkeypatch.setenv("SCM_TOKEN", "fixture-secret-not-in-runner")
    policy = VerifierRunnerPolicy.from_eval_config(
        EvalSchema(test_cmd=f"{sys.executable} -m pytest -q {{test}}", verifier_toolchain=binding)
    )
    assert check_test_runner_installation(project, policy)["passed"]
    proof = _check_test("test_update.py::test_ok", project, policy)
    assert proof["passed"] and proof["toolchain_sha256"] == binding.sha256


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", [3, 99, 0]),
        ("implementation", "different"),
        ("machine", "other"),
        ("platform", "other"),
        ("cache_tag", "other"),
        ("runtime_revision", "c" * 40),
    ],
)
def test_changed_python_abi_or_source_identity_requires_separate_qualification(
    toolchain_update, field, value
):
    args, target = toolchain_update
    if field == "runtime_revision":
        args["source_revision"] = value
    else:
        target[field] = value
    with pytest.raises(ValueError, match="compatibility differs"):
        prepare_toolchain_for_release(**args)
    assert not list(args["root"].iterdir())


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_image", TARGET_IMAGE),
        ("target_image", SOURCE_IMAGE),
        ("target_image", "fixture/samuel:latest"),
        ("source_version", "latest"),
    ],
)
def test_toolchain_rebinding_requires_explicit_immutable_release_pair(
    toolchain_update, field, value
):
    args, _ = toolchain_update
    args[field] = value
    with pytest.raises(ValueError):
        prepare_toolchain_for_release(**args)
    assert not list(args["root"].iterdir())


@pytest.mark.parametrize("drift", ["package", "lock", "manifest", "symlink"])
def test_toolchain_drift_is_not_relabelled_as_a_new_valid_release(toolchain_update, drift):
    args, _ = toolchain_update
    source = Path(args["previous"].manifest).parent
    if drift == "package":
        (source / "packages/pytest/__init__.py").write_text("changed")
    elif drift == "lock":
        (source / "requirements.lock").write_text("changed")
    elif drift == "manifest":
        Path(args["previous"].manifest).write_text("{}")
    else:
        (source / "packages/linked").symlink_to("/etc/passwd")
    with pytest.raises(ValueError):
        prepare_toolchain_for_release(**args)
    assert not list(args["root"].iterdir())


def test_toolchain_output_must_not_overlap_preserved_source(toolchain_update):
    args, _ = toolchain_update
    child = Path(args["previous"].manifest).parent / "packages/new-output"
    child.mkdir()
    args["root"] = child
    with pytest.raises(ValueError, match="overlap"):
        prepare_toolchain_for_release(**args)
    assert not list(child.iterdir())


def test_partial_toolchain_copy_never_changes_old_registration(toolchain_update, monkeypatch):
    import samuel.verifier_toolchain as operator

    args, _ = toolchain_update
    source = Path(args["previous"].manifest).parent
    before = _source_snapshot(source)

    def fail(*_args, **_kwargs):
        raise OSError("fixture storage failure")

    monkeypatch.setattr(operator.shutil, "copyfile", fail)
    with pytest.raises(OSError, match="storage failure"):
        prepare_toolchain_for_release(**args)
    assert _source_snapshot(source) == before
    assert not (args["root"] / "toolchain-manifest.json").exists()
