from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from samuel.core.config import EvalSchema, GatesConfigSchema, VerifierToolchainSchema
from samuel.core.evaluation_subject import gate_policy_binding
from samuel.core.test_runner import (
    VerifierRunnerPolicy,
    artifact_files,
    check_test_readiness,
    check_test_runner_installation,
    python_identity,
    resolve_test_runner,
    validate_toolchain,
)
from samuel.slices.ac_verification.handler import _check_test
from samuel.verifier_toolchain import prepare_toolchain, register_toolchain, verify_registration


@pytest.fixture
def toolchain(tmp_path: Path) -> VerifierToolchainSchema:
    root = tmp_path / "toolchain"
    packages = root / "packages"
    packages.mkdir(parents=True)
    # Copy actual installed distributions, no synthetic presence-only module.
    for name in (
        "pytest",
        "iniconfig",
        "packaging",
        "pluggy",
        "pygments",
        "exceptiongroup",
        "tomli",
        "typing_extensions",
    ):
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for entry in dist.files or []:
            top = entry.parts[0]
            if top in {"..", "__pycache__"}:
                continue
            source = Path(dist.locate_file(top))
            target = packages / top
            if not target.exists():
                if source.is_dir():
                    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
                elif source.is_file():
                    shutil.copyfile(source, target)
    lock = root / "requirements.lock"
    lock.write_text("# test artifact; real operator preparation checks exact hashes separately\n")
    manifest = {
        "schema_version": 1,
        "python": python_identity(),
        "files": artifact_files(packages),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "distributions": {
            dist.metadata["Name"]: dist.version
            for dist in importlib.metadata.distributions(path=[str(packages)])
        },
    }
    path = root / "toolchain-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True))
    return VerifierToolchainSchema(
        manifest=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_real_bound_pytest_readiness_and_execution_are_sterile(toolchain, tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_example.py").write_text(
        "import os\ndef test_ok():\n assert 'SCM_TOKEN' not in os.environ\n"
        " assert 'PYTHONPATH' not in os.environ\n assert 'PIP_INDEX_URL' not in os.environ\n"
    )
    monkeypatch.setenv("SCM_TOKEN", "synthetic-private-token")
    monkeypatch.setenv("PYTHONPATH", "/candidate/untrusted")
    monkeypatch.setenv("PIP_INDEX_URL", "https://synthetic-secret.invalid")
    policy = VerifierRunnerPolicy.from_eval_config(
        EvalSchema(test_cmd=f"{sys.executable} -m pytest -q {{test}}", verifier_toolchain=toolchain)
    )
    assert check_test_runner_installation(project, policy)["passed"]
    assert check_test_readiness("test_example.py::test_ok", project, policy)["passed"]
    result = _check_test("test_example.py::test_ok", project, policy)
    assert result["passed"] is True
    assert result["toolchain_sha256"] == toolchain.sha256
    (project / "test_example.py").write_text("def test_ok():\n assert False\n")
    assert _check_test("test_example.py::test_ok", project, policy)["passed"] is False


@pytest.mark.parametrize(
    "change", ["manifest", "package", "added", "lock", "symlink", "pth", "missing"]
)
def test_toolchain_drift_blocks_doctor_planning_and_test(toolchain, tmp_path, change):
    root = Path(toolchain.manifest).parent
    if change == "manifest":
        Path(toolchain.manifest).write_text("{}")
    elif change == "package":
        (root / "packages" / "pytest" / "__init__.py").write_text("raise RuntimeError('changed')")
    elif change == "added":
        (root / "packages" / "extra.py").write_text("pass")
    elif change == "lock":
        (root / "requirements.lock").write_text("changed")
    elif change == "symlink":
        (root / "packages" / "extra.py").symlink_to("/etc/passwd")
    elif change == "pth":
        (root / "packages" / "extra.pth").write_text("import os")
    else:
        Path(toolchain.manifest).unlink()
    policy = VerifierRunnerPolicy.from_eval_config(
        EvalSchema(test_cmd=f"{sys.executable} -m pytest -q {{test}}", verifier_toolchain=toolchain)
    )
    for result in (
        check_test_runner_installation(tmp_path, policy),
        check_test_readiness("test_x", tmp_path, policy),
        _check_test("test_x", tmp_path, policy),
    ):
        assert result["passed"] is False
        assert result["status"] == "missing_evidence"


def test_binding_changes_policy_digest_without_changing_old_default(toolchain):
    gates = GatesConfigSchema()
    old = gate_policy_binding(gates, EvalSchema(), None)
    assert old == gate_policy_binding(gates, EvalSchema(verifier_toolchain=None), None)
    bound = gate_policy_binding(gates, EvalSchema(verifier_toolchain=toolchain), None)
    assert bound["policy_digest"] != old["policy_digest"]


@pytest.mark.parametrize(
    ("startup_seconds", "test_timeout", "expected_ready"),
    [(12, 60, True), (12, 5, False), (70, 3600, False)],
)
def test_bound_runner_startup_respects_a_bounded_operator_budget(
    toolchain, tmp_path, monkeypatch, startup_seconds, test_timeout, expected_ready
):
    """A slow version probe is not a missing toolchain, but has a hard deadline."""
    policy = VerifierRunnerPolicy.from_eval_config(
        EvalSchema(
            test_cmd=f"{sys.executable} -m pytest -q {{test}}",
            test_timeout=test_timeout,
            verifier_toolchain=toolchain,
        )
    )

    def delayed_version_probe(command, **kwargs):
        assert command[-1] == "--version"
        assert not any(name in kwargs["env"] for name in ("SCM_TOKEN", "PYTHONPATH"))
        if startup_seconds > kwargs["timeout"]:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, stdout=b"pytest\n", stderr=b"")

    monkeypatch.setattr(subprocess, "run", delayed_version_probe)
    for result in (
        check_test_runner_installation(tmp_path, policy),
        check_test_readiness("test_x", tmp_path, policy),
    ):
        assert result["passed"] is expected_ready
        assert result["status"] == ("ready" if expected_ready else "missing_evidence")


def test_non_python_marker_keeps_existing_runner(tmp_path):
    (tmp_path / "go.mod").write_text("module example.invalid/project\n")
    resolved = resolve_test_runner(tmp_path, "TestExample")
    assert resolved is not None
    assert resolved[0] == [
        "go",
        "test",
        "-run",
        "TestExample",
        "./...",
    ]


def test_parent_only_pytest_presence_cannot_make_readiness_green(tmp_path, monkeypatch):
    import importlib.util
    import venv

    clean = tmp_path / "clean-python"
    venv.EnvBuilder(with_pip=False).create(clean)
    interpreter = clean / "bin" / "python"
    fake_parent = tmp_path / "parent-only"
    fake_parent.mkdir()
    (fake_parent / "pytest.py").write_text("# parent-only presence is not a toolchain\n")
    monkeypatch.setenv("PYTHONPATH", str(fake_parent))
    monkeypatch.setattr(sys, "executable", str(interpreter))
    monkeypatch.setattr(importlib.util, "find_spec", lambda module: object())
    policy = VerifierRunnerPolicy.from_eval_config(
        EvalSchema(test_cmd=f"{interpreter} -m pytest -q {{test}}")
    )
    result = check_test_runner_installation(tmp_path, policy)
    assert result["passed"] is False
    assert result["status"] == "missing_evidence"


def test_toolchain_rejects_other_python_identity(toolchain):
    path = Path(toolchain.manifest)
    manifest = json.loads(path.read_text())
    manifest["python"]["version"] = [0, 0, 0]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_toolchain(
            toolchain.model_copy(update={"sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        )


def test_registration_preserves_runtime_token_and_detects_mount_or_policy_drift(
    toolchain, tmp_path
):
    root = tmp_path / "config-root"
    (root / "config").mkdir(parents=True)
    (root / "compose").mkdir()
    env = root / ".env"
    env.write_text("SCM_TOKEN=synthetic-runtime-token\n")
    evaluation = root / "config" / "eval.json"
    evaluation.write_text('{"test_cmd": "python -m pytest -q {test}", "test_timeout": 42}')
    binding = toolchain.model_dump()
    register_toolchain(root, "/srv/samuel/toolchains/sha256-" + "a" * 64, binding)
    verify_registration(root)
    assert env.read_text() == "SCM_TOKEN=synthetic-runtime-token\n"
    assert json.loads(evaluation.read_text())["test_timeout"] == 42
    override = root / "compose" / "docker-compose.toolchain.yml"
    assert "read_only: true" in override.read_text()
    override.write_text(override.read_text().replace("read_only: true", "read_only: false"))
    with pytest.raises(ValueError, match="mount changed"):
        verify_registration(root)


@pytest.mark.parametrize(
    "content",
    ["pytest>=8", "--index-url https://invalid", "-r other", "pytest @ https://invalid/wheel.whl"],
)
def test_preparation_rejects_unlocked_or_option_based_requirements_before_pip(tmp_path, content):
    output = tmp_path / "output"
    output.mkdir()
    lock = tmp_path / "requirements.lock"
    lock.write_text(content)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    with pytest.raises(ValueError, match="exact pins"):
        prepare_toolchain(
            root=output,
            lock=lock,
            lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
            wheelhouse=wheelhouse,
        )
    assert list(output.iterdir()) == []
