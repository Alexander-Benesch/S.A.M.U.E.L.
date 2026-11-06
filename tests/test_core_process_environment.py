from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from samuel.core.process_environment import (
    VERIFIER_ENVIRONMENT_KEYS,
    VERIFIER_ENVIRONMENT_PROFILE,
    verifier_executable_path,
    verifier_process_environment,
)
from samuel.core.test_runner import VerifierRunnerPolicy, check_test_runner_installation


def test_verifier_environment_contains_only_documented_values(monkeypatch) -> None:
    monkeypatch.setenv("SCM_TOKEN", "test-sentinel")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-sentinel")
    monkeypatch.setenv("GIT_DIR", "/operator/git")
    monkeypatch.setenv("GIT_ASKPASS", "/operator/askpass")
    monkeypatch.setenv("SAMUEL_GIT_ASKPASS_SECRET", "test-sentinel")
    monkeypatch.setenv("SAMUEL_GIT_ASKPASS_USERNAME", "test-user")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/operator/ssh-agent")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-sentinel")
    monkeypatch.setenv("PYTHONPATH", "/operator/python")
    monkeypatch.setenv("HOME", "/operator/home")
    monkeypatch.setenv("PATH", "/operator/profile/bin")

    with verifier_process_environment(sys.executable) as environment:
        runtime_root = Path(environment["HOME"]).parent
        assert set(environment) == set(VERIFIER_ENVIRONMENT_KEYS)
        assert environment["HOME"] != "/operator/home"
        assert environment["PATH"].split(os.pathsep)[0] == str(Path(sys.executable).parent)
        assert "/operator/profile/bin" not in environment["PATH"].split(os.pathsep)
        for name in (
            "SCM_TOKEN",
            "OPENROUTER_API_KEY",
            "GIT_DIR",
            "GIT_ASKPASS",
            "SAMUEL_GIT_ASKPASS_SECRET",
            "SAMUEL_GIT_ASKPASS_USERNAME",
            "SSH_AUTH_SOCK",
            "AWS_SECRET_ACCESS_KEY",
            "PYTHONPATH",
        ):
            assert name not in environment
        for name in (
            "HOME",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_RUNTIME_DIR",
            "XDG_STATE_HOME",
        ):
            assert Path(environment[name]).is_dir()

    assert VERIFIER_ENVIRONMENT_PROFILE == "verifier-sterile.v1"
    assert not runtime_root.exists()


def test_absolute_control_plane_executable_adds_only_its_directory(tmp_path: Path) -> None:
    executable = tmp_path / "trusted" / "runner"
    with verifier_process_environment(str(executable)) as environment:
        paths = environment["PATH"].split(os.pathsep)

    assert str(executable.parent) in paths
    assert str(tmp_path) not in paths


def test_relative_python_runner_keeps_active_virtualenv_bin(monkeypatch, tmp_path: Path) -> None:
    venv_bin = tmp_path / "candidate-venv" / "bin"
    venv_bin.mkdir(parents=True)
    venv_python = venv_bin / "python"
    venv_python.symlink_to(Path(sys.executable))
    monkeypatch.setattr(sys, "executable", str(venv_python))

    executable_path = verifier_executable_path("python")

    assert executable_path.split(os.pathsep)[0] == str(venv_bin)
    assert shutil.which("python", path=executable_path) == str(venv_python)
    readiness = check_test_runner_installation(
        tmp_path,
        VerifierRunnerPolicy(
            policy_version="test",
            test_cmd="python -m unittest {test}",
            test_timeout=60,
        ),
    )
    assert readiness["passed"] is True
    assert readiness["runner_kind"] == "unittest"
