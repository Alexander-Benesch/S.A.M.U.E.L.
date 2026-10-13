from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from samuel.core.project_binding import (
    PROJECT_BINDING_FILE,
    inspect_project,
    project_readiness,
)
from samuel.project_binding import (
    configured_project_status,
    register_project,
    verify_project_registration,
)


@pytest.fixture
def project_installation(tmp_path: Path) -> tuple[Path, Path, str]:
    operator = tmp_path / "operator"
    (operator / "config").mkdir(parents=True)
    (operator / "compose").mkdir()
    (operator / ".env").write_text("# operator\nSCM_TOKEN=preserved-secret\n")
    (operator / ".env").chmod(0o600)
    receipt: dict[str, Any] = {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "image": "image@sha256:" + "a" * 64,
    }
    for key in ("config_root", "data_root", "work_root", "log_root", "backup_root"):
        receipt[key] = str(operator if key == "config_root" else tmp_path / key)
    (operator / ".container-install.json").write_text(json.dumps(receipt))
    repo = tmp_path / "source"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Project Test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "add", "origin", "https://git.example/owner/repo.git")
    (repo / "source.py").write_text("answer = 42\n")
    git("add", "source.py")
    git("commit", "-m", "initial")
    return operator, repo, git("rev-parse", "HEAD")


def _register(installation: tuple[Path, Path, str], **overrides: str) -> dict[str, Any]:
    operator, repo, revision = installation
    values = dict(
        host_source=str(repo),
        container_target="/projects/target",
        repository="https://git.example/owner/repo",
        revision=revision,
    )
    values.update(overrides)
    return register_project(operator, source=repo, **values)


def _source_snapshot(repo: Path) -> dict[str, str]:
    return {
        str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in repo.rglob("*")
        if p.is_file()
    }


def test_registration_preserves_source_and_secrets_and_is_idempotent(project_installation) -> None:
    operator, repo, revision = project_installation
    before = _source_snapshot(repo)
    binding = _register(project_installation)
    assert binding["initial_revision"] == revision
    assert verify_project_registration(operator) == binding
    assert _register(project_installation) == binding
    assert _source_snapshot(repo) == before
    env = (operator / ".env").read_text()
    assert "SCM_TOKEN=preserved-secret" in env
    assert "PROJECT_ROOT=/projects/target" in env
    assert (operator / ".env").stat().st_mode & 0o777 == 0o600
    overlay = (operator / "compose/docker-compose.project.yml").read_text()
    assert "create_host_path: false" in overlay
    assert "read_only: false" in overlay
    assert "environment:" not in overlay


@pytest.mark.parametrize(
    "kind",
    ["origin", "credential", "revision", "overlap", "target", "linked", "alternates", "symlink"],
)
def test_invalid_project_never_registers_or_changes_environment(
    project_installation, kind: str
) -> None:
    operator, repo, _ = project_installation
    original = (operator / ".env").read_bytes()
    overrides = {}
    if kind == "origin":
        overrides["repository"] = "https://git.example.attacker/owner/repo"
    if kind == "credential":
        overrides["repository"] = "https://user:secret@git.example/owner/repo"
    if kind == "revision":
        overrides["revision"] = "b" * 40
    if kind == "overlap":
        overrides["host_source"] = str(operator)
    if kind == "target":
        overrides["container_target"] = "/app/data/project"
    if kind == "linked":
        (repo / ".git").rename(repo / "gitdir")
        (repo / ".git").write_text("gitdir: gitdir\n")
    if kind == "alternates":
        (repo / ".git/objects/info/alternates").write_text("/other/objects\n")
    if kind == "symlink":
        (repo / ".git").rename(repo / "gitdir")
        (repo / ".git").symlink_to(repo / "gitdir", target_is_directory=True)
    with pytest.raises(ValueError):
        _register(project_installation, **overrides)
    assert (operator / ".env").read_bytes() == original
    assert not (operator / "config" / PROJECT_BINDING_FILE).exists()
    assert not (operator / "compose/docker-compose.project.yml").exists()


@pytest.mark.parametrize("kind", ["env", "overlay", "receipt", "partial"])
def test_registration_tampering_blocks_restart(project_installation, kind: str) -> None:
    operator, _, _ = project_installation
    _register(project_installation)
    if kind == "env":
        (operator / ".env").write_text("PROJECT_ROOT=/other\n")
    if kind == "overlay":
        (operator / "compose/docker-compose.project.yml").write_text("services: {}\n")
    if kind == "receipt":
        (operator / ".container-install.json").write_text("{}\n")
    if kind == "partial":
        (operator / "config" / PROJECT_BINDING_FILE).unlink()
    with pytest.raises(ValueError):
        verify_project_registration(operator)


def test_registered_runtime_checks_root_scm_and_owner(project_installation, monkeypatch) -> None:
    operator, repo, _ = project_installation
    binding = _register(project_installation)
    assert (
        inspect_project(repo, repository=binding["repository"], binding=binding)["reason_code"]
        == "project_binding_root_mismatch"
    )
    assert (
        inspect_project(
            repo,
            repository="https://git.example/other/repo",
            binding=binding,
            check_mount_target=False,
        )["reason_code"]
        == "project_binding_scm_mismatch"
    )
    monkeypatch.setattr(os, "getuid", lambda: binding["uid"] + 1)
    assert (
        inspect_project(
            repo, repository=binding["repository"], binding=binding, check_mount_target=False
        )["reason_code"]
        == "project_runtime_owner_mismatch"
    )


def test_passive_inspection_never_refreshes_index_or_runs_candidate(project_installation) -> None:
    _, repo, _ = project_installation
    marker = repo / "executed"
    (repo / "source.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    before = _source_snapshot(repo)
    for _ in range(2):
        status = inspect_project(repo, repository="https://git.example/owner/repo")
        assert status["passed"] is True
        assert status["active_io_qualified"] is False
        assert status["candidate_isolation_qualified"] is False
    assert _source_snapshot(repo) == before
    assert not marker.exists()


def test_oci_missing_binding_is_blocked_without_bootstrap(
    project_installation, monkeypatch
) -> None:
    operator, repo, _ = project_installation
    monkeypatch.setenv("SAMUEL_PROJECT_BINDING_REQUIRED", "1")
    status = project_readiness(
        operator / "config", root=repo, repository="https://git.example/owner/repo"
    )
    assert status["reason_code"] == "project_binding_missing"
    assert not status["passed"]


@pytest.mark.parametrize(
    ("provider", "url", "origin"),
    [
        ("gitea", "https://git.example", "https://git.example/owner/repo"),
        ("github", "https://api.github.com", "https://github.com/owner/repo"),
        (
            "github",
            "https://github.enterprise.example/api/v3",
            "https://github.enterprise.example/owner/repo",
        ),
    ],
)
def test_configured_project_uses_existing_scm_adapter_identity(
    project_installation, monkeypatch, provider, url, origin
) -> None:
    operator, repo, _ = project_installation
    subprocess.run(["git", "remote", "set-url", "origin", origin + ".git"], cwd=repo, check=True)
    for k, v in {
        "SCM_PROVIDER": provider,
        "SCM_URL": url,
        "SCM_REPO": "owner/repo",
        "PROJECT_ROOT": str(repo),
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("SAMUEL_PROJECT_BINDING_REQUIRED", raising=False)
    status = configured_project_status(operator / "config")
    assert status["passed"], status
    assert status["repository"] == origin


@pytest.mark.parametrize("kind", ["modified", "untracked", "staged", "push-url", "worktree"])
def test_registration_rejects_dirty_or_redirected_source(project_installation, kind) -> None:
    operator, repo, _ = project_installation
    before_env = (operator / ".env").read_bytes()
    if kind in {"modified", "staged"}:
        (repo / "source.py").write_text("changed = True\n")
    if kind == "staged":
        subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
    if kind == "untracked":
        (repo / "unexpected.py").write_text("untracked\n")
    if kind == "push-url":
        subprocess.run(
            ["git", "remote", "set-url", "--push", "origin", "https://other.example/o/r"],
            cwd=repo,
            check=True,
        )
    if kind == "worktree":
        subprocess.run(["git", "config", "core.worktree", str(operator)], cwd=repo, check=True)
    before = _source_snapshot(repo)
    with pytest.raises(ValueError, match="blocked"):
        _register(project_installation)
    assert _source_snapshot(repo) == before
    assert (operator / ".env").read_bytes() == before_env
    assert not (operator / "config" / PROJECT_BINDING_FILE).exists()


def test_inspection_disables_repository_fsmonitor_hook(project_installation) -> None:
    _, repo, _ = project_installation
    hook = repo.parent / "fsmonitor.sh"
    marker = repo.parent / "hook-executed"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    hook.chmod(0o755)
    subprocess.run(["git", "config", "core.fsmonitor", str(hook)], cwd=repo, check=True)
    _register(project_installation)
    assert not marker.exists()


def test_registration_write_failure_preserves_operator_env(
    project_installation, monkeypatch
) -> None:
    operator, repo, _ = project_installation
    before = (operator / ".env").read_bytes(), _source_snapshot(repo)
    original = os.fsync
    calls = 0

    def fail(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic full disk")
        original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="full disk"):
        _register(project_installation)
    assert (operator / ".env").read_bytes() == before[0]
    assert _source_snapshot(repo) == before[1]
    assert not (operator / "config" / PROJECT_BINDING_FILE).exists()
    assert not (operator / "compose/docker-compose.project.yml").exists()
    assert not (operator / ".env.project-prepared").exists()


@pytest.mark.parametrize("failure", ["network", "space", "inodes"])
def test_registered_project_blocks_unsupported_storage(
    project_installation, monkeypatch, failure
) -> None:
    from types import SimpleNamespace

    from samuel.adapters.workspace import git as workspace_git

    operator, repo, _ = project_installation
    _register(project_installation)
    monkeypatch.setenv("PROJECT_ROOT", str(repo))
    if failure == "network":
        monkeypatch.setattr(workspace_git, "_mount_type", lambda _: "nfs4")
    else:
        monkeypatch.setattr(
            os,
            "statvfs",
            lambda _: SimpleNamespace(
                f_bavail=0 if failure == "space" else 10**9,
                f_frsize=4096,
                f_favail=0 if failure == "inodes" else 1000,
            ),
        )
    status = configured_project_status(operator / "config")
    assert not status["passed"]
    assert status["reason_code"] == (
        "project_filesystem_remote"
        if failure == "network"
        else "project_workspace_capacity_insufficient"
    )


def test_watch_blocks_unregistered_oci_before_bootstrap(project_installation, monkeypatch) -> None:
    import samuel.core.bootstrap as bootstrap_module
    from samuel import cli

    operator, repo, _ = project_installation
    monkeypatch.setenv("PROJECT_ROOT", str(repo))
    monkeypatch.setenv("SAMUEL_PROJECT_BINDING_REQUIRED", "1")
    monkeypatch.setattr(
        bootstrap_module, "bootstrap", lambda *a, **k: pytest.fail("bootstrap mutated authority")
    )
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", str(operator / "config"), "watch"])
    assert exc.value.code == 2


@pytest.mark.parametrize("change", ["replace", "missing", "permissions", "owner", "push_origin"])
def test_registered_source_change_blocks_without_side_effects(
    project_installation, monkeypatch, change
):
    operator, repo, _ = project_installation
    binding = _register(project_installation)
    if change == "replace":
        import shutil

        old = repo.with_name("original")
        repo.rename(old)
        shutil.copytree(old, repo)
    elif change == "missing":
        repo.rename(repo.with_name("original"))
    elif change == "permissions":
        repo.chmod(0o777)
    elif change == "owner":
        binding = {**binding, "gid": binding["gid"] + 1}
    else:
        subprocess.run(
            ["git", "remote", "set-url", "--push", "origin", "https://other.invalid/o/r"],
            cwd=repo,
            check=True,
        )
    before = _source_snapshot(repo) if repo.exists() else {}
    status = inspect_project(
        repo,
        repository=binding["repository"],
        binding=binding,
        check_mount_target=False,
        check_runtime_identity=False,
    )
    assert not status["passed"]
    assert before == (_source_snapshot(repo) if repo.exists() else {})
    assert not status["candidate_isolation_qualified"]
