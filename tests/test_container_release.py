from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import pytest

from tools import container_release
from tools.container_release import (
    ContainerReleaseError,
    load_policy,
    publisher_preflight,
    record_container_manifest,
    verify_container_contract,
    verify_gitea_publisher,
    verify_image_inspect,
)

ROOT = Path(__file__).parents[1]
CONTRACT_FILES = (
    ".dockerignore",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.setup.yml",
    "pyproject.toml",
    "requirements-container.lock",
    "requirements-container-build.lock",
    "containers/lock-policy.json",
)


def _contract_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in CONTRACT_FILES:
        source = ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return root


def _manifest(path: Path, *, commit: str = "a" * 40) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product": "samuel",
                "version": "2.0.0a3",
                "tag": "v2.0.0a3",
                "commit": commit,
                "artifacts": [{"name": "samuel.whl", "sha256": "b" * 64, "size": 1}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_current_container_contract_is_complete_and_hash_bound() -> None:
    evidence = verify_container_contract(ROOT)

    assert evidence["base_image"].startswith("python:3.12-slim@sha256:")
    assert evidence["base_platform_manifest_digest"].startswith("sha256:")
    assert evidence["runtime_packages"] >= 9
    assert evidence["build_packages"] >= 2
    assert evidence["runtime_lock_sha256"].startswith("sha256:")
    assert evidence["build_lock_sha256"].startswith("sha256:")
    assert evidence["system_packages_sha256"].startswith("sha256:")
    assert evidence["git_version"] == "2.47.3"


def test_python_package_builds_share_a_fixed_source_date_epoch() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    globals_, builder, runtime = dockerfile.split("FROM ${PYTHON_IMAGE} AS ")
    assert "ARG SOURCE_DATE_EPOCH=315532800" in globals_.splitlines()
    for stage in (builder, runtime):
        before_install = stage.split("RUN python -m pip install", 1)[0]
        assert "ARG SOURCE_DATE_EPOCH" in before_install.splitlines()


def test_healthcheck_timeout_targets_the_checker_not_a_surviving_shell_child(tmp_path):
    """Exercise the shipped shell command, including environment expansion."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    command = dockerfile.split("HEALTHCHECK", 1)[1].split("CMD ", 1)[1].splitlines()[0]
    observed = tmp_path / "checker.pid"
    checker = tmp_path / "samuel"
    checker.write_text(
        f"#!{sys.executable}\n"
        "import os,sys,time\n"
        f"assert sys.argv[1:] == ['--config', {str(tmp_path)!r}, 'health']\n"
        f"open({str(observed)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    checker.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    env["SAMUEL_RUNTIME_CONFIG_DIR"] = str(tmp_path)
    process = subprocess.Popen(["/bin/sh", "-c", command], env=env)
    checker_pid = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and (
            not observed.exists() or not observed.read_text().strip()
        ):
            time.sleep(0.01)
        assert observed.exists(), "Healthcheck did not start its configured checker"
        checker_pid = int(observed.read_text())
        process.kill()
        process.wait(timeout=5)
        assert checker_pid == process.pid, "Docker would kill only the wrapper shell"
        with pytest.raises(ProcessLookupError):
            os.kill(checker_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if checker_pid is not None and checker_pid != process.pid:
            with suppress(ProcessLookupError):
                os.kill(checker_pid, 9)


def test_setup_contract_rejects_inherited_production_file_mounts(tmp_path: Path) -> None:
    root = _contract_root(tmp_path)
    setup = root / "docker-compose.setup.yml"
    setup.write_text(setup.read_text().replace("volumes: !override", "volumes:"))
    with pytest.raises(ContainerReleaseError, match="setup persistence contract"):
        verify_container_contract(root)


@pytest.mark.parametrize("field,value", [("generator", "uv==0"), ("exclude_newer", "today")])
def test_contract_rejects_unreviewed_lock_generation(
    tmp_path: Path, field: str, value: str
) -> None:
    root = _contract_root(tmp_path)
    policy_path = root / "containers" / "lock-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["lock_contract"][field] = value
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ContainerReleaseError):
        verify_container_contract(root)


def test_contract_rejects_dependency_and_lock_drift(tmp_path: Path) -> None:
    dependency_root = _contract_root(tmp_path / "dependency")
    pyproject = dependency_root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            '"pydantic>=2.0,<3",', '"pydantic>=2.0,<3",\n    "packaging>=24",'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ContainerReleaseError, match="runtime_requirements.*stale"):
        verify_container_contract(dependency_root)

    lock_root = _contract_root(tmp_path / "lock")
    lock = lock_root / "requirements-container.lock"
    lock.write_text(lock.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
    with pytest.raises(ContainerReleaseError, match="digest is stale"):
        verify_container_contract(lock_root)


@pytest.mark.parametrize("descriptor", ["runtime_lock", "build_lock"])
def test_contract_rejects_inherited_unlocked_pip(tmp_path: Path, descriptor: str) -> None:
    root = _contract_root(tmp_path)
    policy_path = root / "containers/lock-policy.json"
    policy = json.loads(policy_path.read_text())
    binding = policy["lock_contract"][descriptor]
    lock = root / binding["path"]
    lines = lock.read_text().splitlines(keepends=True)
    retained = []
    removing = False
    for line in lines:
        if line and not line[0].isspace():
            removing = line.startswith("pip==")
        if not removing:
            retained.append(line)
    lock.write_text("".join(retained))
    # Matching bytes/hash alone must not allow an inherited, unreviewed installer.
    binding["sha256"] = "sha256:" + hashlib.sha256(lock.read_bytes()).hexdigest()
    policy_path.write_text(json.dumps(policy))
    with pytest.raises(ContainerReleaseError, match="misses direct requirements: pip"):
        verify_container_contract(root)


def test_contract_rejects_open_base_or_operator_state_context(tmp_path: Path) -> None:
    base_root = _contract_root(tmp_path / "base")
    dockerfile = base_root / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "python:3.12-slim@sha256:", "python:3.12-slim#sha256:"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ContainerReleaseError, match="Dockerfile base image differs"):
        verify_container_contract(base_root)

    context_root = _contract_root(tmp_path / "context")
    dockerignore = context_root / ".dockerignore"
    dockerignore.write_text(dockerignore.read_text(encoding="utf-8") + "!.env\n", encoding="utf-8")
    with pytest.raises(ContainerReleaseError, match="context allowlist"):
        verify_container_contract(context_root)


def test_contract_rejects_module_entrypoint_in_runtime_image(tmp_path: Path) -> None:
    root = _contract_root(tmp_path)
    dockerfile = root / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            'ENTRYPOINT ["samuel"]', 'ENTRYPOINT ["python", "-m", "samuel"]'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContainerReleaseError, match="installed console entry point"):
        verify_container_contract(root)


def test_contract_rejects_unbound_system_package_or_dockerfile_drift(tmp_path: Path) -> None:
    policy_root = _contract_root(tmp_path / "policy")
    policy_path = policy_root / "containers" / "lock-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["system_packages"]["packages"]["git"] = "latest"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ContainerReleaseError, match="Git system package version"):
        verify_container_contract(policy_root)

    dockerfile_root = _contract_root(tmp_path / "dockerfile")
    dockerfile = dockerfile_root / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "ARG GIT_RUNTIME_VERSION=2.47.3", "ARG GIT_RUNTIME_VERSION=2.47.2"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ContainerReleaseError, match="GIT_RUNTIME_VERSION differs"):
        verify_container_contract(dockerfile_root)


def test_image_inspection_binds_oci_runtime_identity_and_platform() -> None:
    version = "2.0.0a3"
    commit = "a" * 40
    source = "https://forge.example/owner/samuel"
    base = "python:3.12-slim@sha256:" + "b" * 64
    inspect: dict[str, Any] = {
        "Os": "linux",
        "Architecture": "amd64",
        "Config": {
            "Labels": {
                "org.opencontainers.image.version": version,
                "org.opencontainers.image.revision": commit,
                "org.opencontainers.image.source": source,
                "org.opencontainers.image.base.name": base,
                "org.opencontainers.image.licenses": "Apache-2.0",
            },
            "Env": [
                f"SAMUEL_BUILD_REVISION={commit}",
                "SAMUEL_RUNTIME_CONFIG_DIR=/app/config",
            ],
            "Healthcheck": {
                "Test": [
                    "CMD-SHELL",
                    'exec samuel --config "${SAMUEL_RUNTIME_CONFIG_DIR}" health',
                ]
            },
        },
    }

    verify_image_inspect(
        inspect, version=version, commit=commit, source_url=source, base_image=base
    )
    inspect["Config"]["Labels"]["org.opencontainers.image.revision"] = "c" * 40
    with pytest.raises(ContainerReleaseError, match="OCI label mismatch"):
        verify_image_inspect(
            inspect, version=version, commit=commit, source_url=source, base_image=base
        )


def test_image_inspection_requires_runtime_config_binding() -> None:
    version = "2.0.0a3"
    commit = "a" * 40
    source = "https://forge.example/owner/samuel"
    base = "python:3.12-slim@sha256:" + "b" * 64
    inspect: dict[str, Any] = {
        "Os": "linux",
        "Architecture": "amd64",
        "Config": {
            "Labels": {
                "org.opencontainers.image.version": version,
                "org.opencontainers.image.revision": commit,
                "org.opencontainers.image.source": source,
                "org.opencontainers.image.base.name": base,
                "org.opencontainers.image.licenses": "Apache-2.0",
            },
            "Env": [f"SAMUEL_BUILD_REVISION={commit}"],
        },
    }

    with pytest.raises(ContainerReleaseError, match="runtime config directory"):
        verify_image_inspect(
            inspect, version=version, commit=commit, source_url=source, base_image=base
        )


@pytest.mark.parametrize(
    "health_command",
    ["samuel health || exit 1", 'samuel --config "${SAMUEL_RUNTIME_CONFIG_DIR}" health || exit 1'],
)
def test_image_inspection_requires_bound_runtime_healthcheck(health_command: str) -> None:
    version = "2.0.0a3"
    commit = "a" * 40
    source = "https://forge.example/owner/samuel"
    base = "python:3.12-slim@sha256:" + "b" * 64
    inspect: dict[str, Any] = {
        "Os": "linux",
        "Architecture": "amd64",
        "Config": {
            "Labels": {
                "org.opencontainers.image.version": version,
                "org.opencontainers.image.revision": commit,
                "org.opencontainers.image.source": source,
                "org.opencontainers.image.base.name": base,
                "org.opencontainers.image.licenses": "Apache-2.0",
            },
            "Env": [
                f"SAMUEL_BUILD_REVISION={commit}",
                "SAMUEL_RUNTIME_CONFIG_DIR=/app/config",
            ],
            "Healthcheck": {"Test": ["CMD-SHELL", health_command]},
        },
    }

    with pytest.raises(ContainerReleaseError, match="runtime config binding"):
        verify_image_inspect(
            inspect, version=version, commit=commit, source_url=source, base_image=base
        )


def test_manifest_upgrade_records_digest_and_lock_provenance(tmp_path: Path) -> None:
    commit = "a" * 40
    digest = "sha256:" + "c" * 64
    path = _manifest(tmp_path / "release-manifest.json", commit=commit)

    manifest = record_container_manifest(
        path,
        tag="v2.0.0a3",
        commit=commit,
        image_repository="registry.example/owner/samuel",
        image_digest=digest,
        policy=load_policy(ROOT),
    )

    assert manifest["schema_version"] == 2
    assert manifest["container"]["reference"] == (f"registry.example/owner/samuel@{digest}")
    assert manifest["container"]["runtime_lock_sha256"].startswith("sha256:")
    assert manifest["container"]["system_packages_sha256"].startswith("sha256:")
    assert manifest["container"]["git_version"] == "2.47.3"
    assert json.loads(path.read_text(encoding="utf-8")) == manifest


def test_runtime_verification_requires_contract_git_and_pip_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = "2.0.0a9.dev0"
    commit = "a" * 40
    root = _contract_root(tmp_path)
    expected_pip = container_release._verify_lock(root / "requirements-container.lock", {"pip"})[
        "pip"
    ]
    installed_pip: str | None = expected_pip

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, check
        if "python" in command:
            stdout = json.dumps(
                {
                    "version": version,
                    "pip": installed_pip,
                    "build": {
                        "revision": commit,
                        "product_version": version,
                        "revision_source": "environment",
                    },
                }
            )
        elif "git" in command:
            stdout = "git version 2.47.3\n"
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(container_release, "_run", fake_run)
    container_release._verify_runtime(
        ["docker"],
        "samuel:test",
        root=root,
        version=version,
        commit=commit,
        git_version="2.47.3",
    )

    with pytest.raises(ContainerReleaseError, match="runtime Git version"):
        container_release._verify_runtime(
            ["docker"],
            "samuel:test",
            root=root,
            version=version,
            commit=commit,
            git_version="2.47.2",
        )

    for installed_pip in ("25.0.1", None):
        with pytest.raises(ContainerReleaseError, match="runtime pip version"):
            container_release._verify_runtime(
                ["docker"],
                "samuel:test",
                root=root,
                version=version,
                commit=commit,
                git_version="2.47.3",
            )


@pytest.mark.parametrize(
    "repository,digest",
    [
        ("Registry.example/owner/samuel", "sha256:" + "c" * 64),
        ("registry.example/owner/samuel", "latest"),
    ],
)
def test_manifest_upgrade_rejects_mutable_or_ambiguous_identity(
    tmp_path: Path, repository: str, digest: str
) -> None:
    path = _manifest(tmp_path / "release-manifest.json")
    with pytest.raises(ContainerReleaseError):
        record_container_manifest(
            path,
            tag="v2.0.0a3",
            commit="a" * 40,
            image_repository=repository,
            image_digest=digest,
            policy=load_policy(ROOT),
        )


def _tested_distribution(dist: Path) -> tuple[Path, str]:
    path = _manifest(dist / "release-manifest.json")
    payload = dist / "samuel.whl"
    payload.write_bytes(b"a")
    manifest = json.loads(path.read_bytes())
    manifest["artifacts"][0]["sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "change", ["half_binding", "mutable_tag", "wheel", "manifest", "extra", "symlink"]
)
def test_tested_distribution_rejects_drift_before_any_push(tmp_path: Path, change: str) -> None:
    manifest, manifest_digest = _tested_distribution(tmp_path)
    image_id = "sha256:" + "1" * 64
    if change == "half_binding":
        manifest_digest = ""
    elif change == "mutable_tag":
        image_id = "samuel:tested"
    elif change == "manifest":
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    elif change == "extra":
        (tmp_path / "extra").touch()
    elif change == "symlink":
        (tmp_path / "samuel.whl").unlink()
        (tmp_path / "samuel.whl").symlink_to(manifest)
    else:
        (tmp_path / "samuel.whl").write_bytes(b"b")
    with pytest.raises(ContainerReleaseError):
        container_release._verify_tested_distribution(manifest, image_id, manifest_digest)


def test_publish_rejects_a_changed_posttag_gate_before_registry_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, expected = _tested_distribution(tmp_path)

    def changed_gate(**kwargs: Any) -> Path:
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        return manifest

    monkeypatch.setattr(container_release, "run_gate", changed_gate)
    with pytest.raises(ContainerReleaseError, match="differs from the tested manifest"):
        container_release.publish(
            root=ROOT,
            dist_dir=tmp_path,
            tag="v2.0.0a3",
            commit_ref="origin/main",
            image_repository="registry.example/owner/samuel",
            source_url="https://forge.example/owner/samuel",
            compose_env_file=tmp_path / "operator.env",
            docker_command="docker",
            publisher_api_url="https://registry.example",
            publisher_user="owner",
            release_host_id="test",
            tested_image_id="sha256:" + "1" * 64,
            tested_manifest_sha256=expected,
        )


@pytest.mark.parametrize("operation", ["publish", "recover"])
@pytest.mark.parametrize("mismatch", ["none", "remote_config", "pulled_image"])
def test_qualified_image_promotes_or_recovers_only_matching_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    mismatch: str,
) -> None:
    manifest, manifest_hash = _tested_distribution(tmp_path)
    expected_id = "sha256:" + "1" * 64
    wrong_id = "sha256:" + "2" * 64
    repo = "registry.example/owner/samuel"
    registry_digest = "sha256:" + "3" * 64
    remote = repo + "@" + registry_digest
    commands: list[list[str]] = []

    @contextmanager
    def session(**kwargs: Any):
        yield ["docker"], {}

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1:3] == ["manifest", "inspect"]:
            if command[-1] == remote:
                value = wrong_id if mismatch == "remote_config" else expected_id
                return subprocess.CompletedProcess(
                    command, 0, json.dumps({"config": {"digest": value}}), ""
                )
            if operation == "publish":
                return subprocess.CompletedProcess(command, 1, "", "manifest unknown")
        return subprocess.CompletedProcess(command, 0, "", "")

    def inspect(docker: list[str], image: str, *, root: Path) -> dict[str, Any]:
        value = wrong_id if mismatch == "pulled_image" and image == remote else expected_id
        return {"Id": value, "RepoDigests": [remote]}

    monkeypatch.setattr(container_release, "_publisher_docker_session", session)
    monkeypatch.setattr(container_release, "_run", run)
    monkeypatch.setattr(container_release, "_inspect_image", inspect)
    monkeypatch.setattr(
        container_release,
        "verify_container_contract",
        lambda _: {"base_image": "pinned", "git_version": "2.47.3"},
    )
    monkeypatch.setattr(container_release, "_verify_runtime", lambda *a, **kw: None)
    monkeypatch.setattr(container_release, "verify_image_inspect", lambda *a, **kw: None)
    monkeypatch.setattr(container_release, "_smoke_compose", lambda *a, **kw: {"health": "healthy"})
    monkeypatch.setattr(container_release, "run_gate", lambda **kw: manifest)
    kwargs: dict[str, Any] = dict(
        root=ROOT,
        dist_dir=tmp_path,
        tag="v2.0.0a3",
        commit_ref="origin/main",
        image_repository=repo,
        source_url="https://forge.example/owner/samuel",
        compose_env_file=tmp_path / "operator.env",
        docker_command="docker",
        publisher_api_url="https://registry.example",
        publisher_user="owner",
        release_host_id="test",
        tested_image_id=expected_id,
        tested_manifest_sha256=manifest_hash,
    )
    command = container_release.publish if operation == "publish" else container_release.recover
    if mismatch == "none":
        result = command(**kwargs)
        assert result["publisher"]["tested_artifacts"] == {
            "image_id": expected_id,
            "manifest_sha256": manifest_hash,
            "remote_config_digest": expected_id,
        }
        assert json.loads(manifest.read_bytes())["container"]["reference"] == remote
    else:
        with pytest.raises(ContainerReleaseError, match="published image differs"):
            command(**kwargs)
        assert json.loads(manifest.read_bytes())["schema_version"] == 1
    actions = [cmd[1] for cmd in commands]
    assert "build" not in actions and actions.count("pull") == 1
    assert actions.count("push") == int(operation == "publish")
    assert [cmd for cmd in commands if cmd[1] == "tag"] == (
        [["docker", "tag", expected_id, repo + ":v2.0.0a3"]] if operation == "publish" else []
    )


def test_recovery_rejects_an_already_recorded_manifest(tmp_path: Path) -> None:
    path = _manifest(tmp_path / "release-manifest.json")
    recorded = json.loads(path.read_text(encoding="utf-8"))
    recorded["schema_version"] = 2
    recorded["container"] = {"reference": "registry.example/owner/samuel@sha256:" + "c" * 64}
    path.write_text(json.dumps(recorded), encoding="utf-8")

    with pytest.raises(ContainerReleaseError, match="unrecorded schema-1"):
        container_release._verify_recovery_manifest(path)


def test_recovery_verifies_existing_digest_without_publish_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commit = "a" * 40
    digest = "sha256:" + "c" * 64
    image_repository = "registry.example/owner/samuel"
    manifest_path = _manifest(tmp_path / "release-manifest.json", commit=commit)
    commands: list[list[str]] = []
    recorded: dict[str, Any] = {}

    @contextmanager
    def publisher_session(**_kwargs: Any):
        yield ["docker"], {"identity": {"status": "verified"}}

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, input_text, check
        commands.append(command)
        if "image" in command and "inspect" in command:
            image = command[-1]
            labels = {
                "org.opencontainers.image.version": "2.0.0a3",
                "org.opencontainers.image.revision": commit,
                "org.opencontainers.image.source": "https://forge.example/owner/samuel",
                "org.opencontainers.image.base.name": "python:3.12-slim@sha256:" + "b" * 64,
                "org.opencontainers.image.licenses": "Apache-2.0",
            }
            stdout = json.dumps(
                [
                    {
                        "Os": "linux",
                        "Architecture": "amd64",
                        "RepoDigests": [f"{image_repository}@{digest}"],
                        "Config": {
                            "Labels": labels,
                            "Env": [
                                f"SAMUEL_BUILD_REVISION={commit}",
                                "SAMUEL_RUNTIME_CONFIG_DIR=/app/config",
                            ],
                            "Healthcheck": {
                                "Test": [
                                    "CMD-SHELL",
                                    'exec samuel --config "${SAMUEL_RUNTIME_CONFIG_DIR}" health',
                                ]
                            },
                        },
                        "Id": image,
                    }
                ]
            )
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def fake_record(path: Path, **kwargs: Any) -> dict[str, Any]:
        recorded.update(kwargs)
        return {"schema_version": 2}

    monkeypatch.setattr(
        container_release,
        "verify_container_contract",
        lambda _root: {
            "base_image": "python:3.12-slim@sha256:" + "b" * 64,
            "git_version": "2.47.3",
        },
    )
    monkeypatch.setattr(container_release, "run_gate", lambda **_kwargs: manifest_path)
    monkeypatch.setattr(container_release, "_publisher_docker_session", publisher_session)
    monkeypatch.setattr(container_release, "_run", fake_run)
    monkeypatch.setattr(container_release, "_verify_runtime", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        container_release, "_smoke_compose", lambda *_args, **_kwargs: {"health": "healthy"}
    )
    monkeypatch.setattr(container_release, "record_container_manifest", fake_record)
    monkeypatch.setattr(container_release, "load_policy", lambda _root: {})

    evidence = container_release.recover(
        root=tmp_path,
        dist_dir=tmp_path / "dist",
        tag="v2.0.0a3",
        commit_ref="origin/main",
        image_repository=image_repository,
        source_url="https://forge.example/owner/samuel",
        compose_env_file=tmp_path / "operator.env",
        docker_command="docker",
        publisher_api_url="https://registry.example",
        publisher_user="owner",
        release_host_id="release-host",
    )

    assert evidence["digest_reference"] == f"{image_repository}@{digest}"
    assert evidence["recovery"] == {"status": "verified", "mutations": "none"}
    assert recorded["image_digest"] == digest
    assert all(not ({"push", "build", "tag"} & set(command)) for command in commands)
    assert any("pull" in command for command in commands)


def test_recovery_blocks_missing_remote_tag_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _manifest(tmp_path / "release-manifest.json")
    commands: list[list[str]] = []

    @contextmanager
    def publisher_session(**_kwargs: Any):
        yield ["docker"], {"identity": {"status": "verified"}}

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, input_text, check
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="manifest unknown")

    monkeypatch.setattr(container_release, "verify_container_contract", lambda _root: {})
    monkeypatch.setattr(container_release, "run_gate", lambda **_kwargs: manifest_path)
    monkeypatch.setattr(container_release, "_publisher_docker_session", publisher_session)
    monkeypatch.setattr(container_release, "_run", fake_run)

    with pytest.raises(ContainerReleaseError, match="already published create-only"):
        container_release.recover(
            root=tmp_path,
            dist_dir=tmp_path / "dist",
            tag="v2.0.0a3",
            commit_ref="origin/main",
            image_repository="registry.example/owner/samuel",
            source_url="https://forge.example/owner/samuel",
            compose_env_file=tmp_path / "operator.env",
            docker_command="docker",
            publisher_api_url="https://registry.example",
            publisher_user="owner",
            release_host_id="release-host",
        )

    assert commands
    assert all(not ({"push", "build", "tag", "pull"} & set(command)) for command in commands)


def test_compose_smoke_passes_control_values_across_sudo_env_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    (root / "config").mkdir(parents=True)
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    operator_env = tmp_path / "operator.env"
    operator_env.write_text("", encoding="utf-8")
    commit = "a" * 40
    image = "registry.example/owner/samuel@sha256:" + "b" * 64
    observed_variables: list[str] = []
    observed_commands: list[list[str]] = []
    observed_data_modes: list[int] = []
    observed_workspace_modes: list[int] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, check
        observed_commands.append(command)
        if "compose" in command:
            variables_path = Path(command[command.index("--env-file") + 1])
            variables = variables_path.read_text(encoding="utf-8")
            observed_variables.append(variables)
            data_line = next(
                line for line in variables.splitlines() if line.startswith("SAMUEL_DATA_DIR=")
            )
            observed_data_modes.append(
                stat.S_IMODE(Path(data_line.split("=", 1)[1]).stat().st_mode)
            )
            workspace_line = next(
                line for line in variables.splitlines() if line.startswith("SAMUEL_WORK_DIR=")
            )
            observed_workspace_modes.append(
                stat.S_IMODE(Path(workspace_line.split("=", 1)[1]).stat().st_mode)
            )
        if "ps" in command:
            stdout = "container-id\n"
        elif "container" in command and "inspect" in command:
            stdout = json.dumps([{"State": {"Health": {"Status": "healthy"}}}])
        elif "exec" in command:
            stdout = json.dumps(
                {
                    "product_version": "2.0.0a3",
                    "revision": commit,
                }
            )
        else:
            stdout = ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(container_release, "_run", fake_run)
    monkeypatch.setattr(container_release, "_free_local_port", lambda: 17777)

    evidence = container_release._smoke_compose(
        ["sudo", "-n", "docker"],
        image,
        root=root,
        env_file=operator_env,
        version="2.0.0a3",
        commit=commit,
    )

    assert evidence["health"] == "healthy"
    assert observed_variables
    assert all(f"SAMUEL_IMAGE={image}" in document for document in observed_variables)
    assert all(f"SAMUEL_ENV_FILE={operator_env}" in document for document in observed_variables)
    assert all("SAMUEL_WORK_DIR=" in document for document in observed_variables)
    assert observed_data_modes and set(observed_data_modes) == {0o777}
    assert observed_workspace_modes and set(observed_workspace_modes) == {0o777}
    assert any(
        "/bootstrap/container_init.py prepare-smoke" in " ".join(command)
        for command in observed_commands
    )
    assert any("--pull always" in " ".join(command) for command in observed_commands)
    assert not any("chmod a+rwX" in " ".join(command) for command in observed_commands)


def test_gitea_publisher_proof_separates_identity_scope_read_and_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def fake_json(api_url: str, path: str, token: str) -> Any:
        assert api_url == "https://registry.example"
        assert token == "publisher-secret"
        observed.append(path)
        if path == "/api/v1/token":
            return {
                "user": {"login": "owner"},
                "scopes": ["read:package", "read:user", "write:package"],
            }
        return []

    monkeypatch.setattr(container_release, "_gitea_json", fake_json)
    proof = verify_gitea_publisher(
        api_url="https://registry.example",
        image_repository="registry.example/owner/samuel",
        publisher_user="owner",
        release_host_id="release-primary",
        publisher_token="publisher-secret",
        runtime_scm_token="runtime-secret",
        allow_insecure=False,
    )

    assert observed == [
        "/api/v1/token",
        "/api/v1/packages/owner?type=container&limit=1",
    ]
    assert proof["identity"] == {"status": "verified", "login": "owner"}
    assert proof["credential_separation"]["runtime_scm_credential"] == "different"
    assert proof["scope"]["single_package_isolation"] is False
    assert proof["owner_read"]["status"] == "verified"
    assert proof["write_qualification"]["probe_push"] is False
    assert proof["organizational_binding"]["release_host_id"] == "release-primary"


@pytest.mark.parametrize(
    "publisher_token,runtime_token,scopes,error",
    [
        ("same", "same", ["write:package"], "must differ"),
        ("publisher", "runtime", ["read:package"], "does not prove write:package"),
        (
            "publisher",
            "runtime",
            ["write:package", "write:repository"],
            "broader write scope",
        ),
    ],
)
def test_gitea_publisher_proof_blocks_credential_or_scope_drift(
    monkeypatch: pytest.MonkeyPatch,
    publisher_token: str,
    runtime_token: str,
    scopes: list[str],
    error: str,
) -> None:
    monkeypatch.setattr(
        container_release,
        "_gitea_json",
        lambda *_args: {"user": {"login": "owner"}, "scopes": scopes},
    )
    with pytest.raises(ContainerReleaseError, match=error):
        verify_gitea_publisher(
            api_url="https://registry.example",
            image_repository="registry.example/owner/samuel",
            publisher_user="owner",
            release_host_id="release-primary",
            publisher_token=publisher_token,
            runtime_scm_token=runtime_token,
            allow_insecure=False,
        )


def test_publisher_preflight_uses_isolated_login_and_never_pushes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAMUEL_OCI_PUBLISHER_TOKEN", "publisher-secret")
    monkeypatch.setenv("SCM_TOKEN", "runtime-secret")
    monkeypatch.setattr(
        container_release,
        "verify_gitea_publisher",
        lambda **_kwargs: {"schema_version": 1},
    )
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, check
        commands.append(command)
        assert "SAMUEL_OCI_PUBLISHER_TOKEN" not in os.environ
        assert "SCM_TOKEN" not in os.environ
        if "login" in command:
            assert input_text == "publisher-secret\n"
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "manifest" in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="manifest unknown")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(container_release, "_run", fake_run)
    proof = publisher_preflight(
        root=tmp_path,
        image_repository="registry.example/owner/samuel",
        tag="v2.0.0a16",
        api_url="https://registry.example",
        publisher_user="owner",
        release_host_id="release-primary",
        docker_command="sudo -n docker",
        registry_insecure=False,
    )

    assert proof["tag_absence"]["status"] == "verified"
    assert any("--password-stdin" in command for command in commands)
    assert all("publisher-secret" not in command for command in commands)
    assert not any("push" in command for command in commands)
    assert all("--config" in command for command in commands)
    assert os.environ["SAMUEL_OCI_PUBLISHER_TOKEN"] == "publisher-secret"
    assert os.environ["SCM_TOKEN"] == "runtime-secret"


@pytest.mark.parametrize(
    "returncode,detail,error",
    [
        (0, "", "already exists"),
        (1, "unauthorized", "cannot prove container tag absence"),
    ],
)
def test_tag_absence_never_treats_existing_or_unreadable_as_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    detail: str,
    error: str,
) -> None:
    monkeypatch.setattr(
        container_release,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["docker"], returncode, stdout="", stderr=detail
        ),
    )
    with pytest.raises(ContainerReleaseError, match=error):
        container_release._prove_tag_absence(
            ["docker"],
            "registry.example/owner/samuel:v2.0.0a16",
            root=tmp_path,
            registry_insecure=False,
        )


@pytest.mark.parametrize("remote_exists", [True, False])
def test_failed_push_is_reconciled_without_retry_or_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote_exists: bool
) -> None:
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, input_text, check
        commands.append(command)
        returncode = 0 if "manifest" in command and remote_exists else 1
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="")

    monkeypatch.setattr(container_release, "_run", fake_run)
    with pytest.raises(
        ContainerReleaseError, match="preserve it" if remote_exists else "do not retry"
    ):
        container_release._push_create_only(
            ["docker"],
            "registry.example/owner/samuel:v2.0.0a16",
            root=tmp_path,
            registry_insecure=False,
        )

    assert len([command for command in commands if "push" in command]) == 1
    assert not any("delete" in command or "rm" in command for command in commands)


def test_smoke_cleanup_covers_config_even_when_prepare_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operator_env = tmp_path / "operator.env"
    operator_env.touch()
    roots: list[Path] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "prepare-smoke" in command:
            path = Path(command[command.index("--volume") + 1].split(":")[0])
            roots.append(path)
            (path / "config").mkdir()
            (path / "config" / "private.json").write_text("test configuration")
            raise ContainerReleaseError("prepare failed")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    original = shutil.rmtree

    def restricted_remove(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path) in roots and (Path(path) / "config").exists():
            raise PermissionError("runtime-owned config")
        original(path, *args, **kwargs)

    def docker_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "--pull" in command and command[command.index("--pull") + 1] == "never":
            assert "--network" in command and "none" in command
            assert command[command.index("--user") + 1] == "0:0"
            original(roots[0] / "config")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return fake_run(command, **kwargs)

    monkeypatch.setattr(container_release, "_run", docker_run)
    monkeypatch.setattr(shutil, "rmtree", restricted_remove)
    with pytest.raises(ContainerReleaseError, match="prepare failed"):
        container_release._smoke_compose(
            ["sudo", "-n", "docker"],
            "samuel:test",
            root=tmp_path,
            env_file=operator_env,
            version="2.0.0a3",
            commit="a" * 40,
        )
    assert roots and not roots[0].exists()


@pytest.mark.parametrize("body_fails", [False, True])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_publisher_owned_metadata_cleanup_and_primary_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body_fails: bool, cleanup_fails: bool
) -> None:
    monkeypatch.setenv("SAMUEL_OCI_PUBLISHER_TOKEN", "publisher-secret")
    monkeypatch.setattr(container_release, "verify_gitea_publisher", lambda **_kw: {})
    roots: list[Path] = []
    cleanup_commands: list[list[str]] = []
    original = shutil.rmtree

    def restricted_remove(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path) in roots and (Path(path) / "buildx").exists():
            raise PermissionError("root-owned buildx")
        original(path, *args, **kwargs)

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "login" in command:
            path = Path(command[command.index("--config") + 1])
            roots.append(path)
            (path / "buildx").mkdir()
            (path / "config.json").write_text("publisher-secret")
        if "run" in command:
            cleanup_commands.append(command)
            assert "--pull" in command and command[command.index("--pull") + 1] == "never"
            assert "none" in command and "0:0" in command
            assert "publisher-secret" not in " ".join(command)
            assert not (roots[0] / "config.json").exists()
            if cleanup_fails:
                raise ContainerReleaseError("cleanup engine unavailable")
            original(roots[0] / "buildx")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(container_release, "_run", fake_run)
    monkeypatch.setattr(shutil, "rmtree", restricted_remove)
    primary = ContainerReleaseError("original smoke failure")

    def exercise() -> None:
        with container_release._publisher_docker_session(
            root=ROOT,
            docker_command="sudo -n docker",
            api_url="https://registry.example",
            image_repository="registry.example/owner/samuel",
            publisher_user="owner",
            release_host_id="test",
            registry_insecure=False,
        ):
            if body_fails:
                raise primary

    try:
        if body_fails:
            with pytest.raises(ContainerReleaseError, match="original smoke failure") as caught:
                exercise()
            assert caught.value is primary
            if cleanup_fails:
                assert any("cleanup" in note for note in primary.__notes__)
        elif cleanup_fails:
            with pytest.raises(ContainerReleaseError, match="cleanup"):
                exercise()
        else:
            exercise()
        assert cleanup_commands
        assert roots[0].exists() == cleanup_fails
        assert os.environ["SAMUEL_OCI_PUBLISHER_TOKEN"] == "publisher-secret"
    finally:
        for path in roots:
            if path.exists():
                original(path)


def test_cleanup_script_keeps_external_symlink_targets(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep"
    sentinel.write_text("unchanged")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "directory-link").symlink_to(outside, target_is_directory=True)
    (scratch / "file-link").symlink_to(sentinel)
    (scratch / "broken-link").symlink_to(tmp_path / "absent")
    (scratch / "config").mkdir()
    (scratch / "config" / "private").write_text("test value")
    result = subprocess.run(
        [os.sys.executable, "-c", container_release._TEMPORARY_CLEANUP_SCRIPT, str(scratch)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert list(scratch.iterdir()) == []
    assert sentinel.read_text() == "unchanged"


@pytest.mark.parametrize("body_fails", [False, True])
def test_cleanup_shutdown_preserves_original_error(body_fails: bool) -> None:
    primary = ContainerReleaseError("original failure")

    def exercise() -> None:
        try:
            if body_fails:
                raise primary
        finally:
            with container_release._cleanup_preserving_failure("test shutdown"):
                raise OSError("engine unreachable")

    if body_fails:
        with pytest.raises(ContainerReleaseError, match="original failure") as caught:
            exercise()
        assert caught.value is primary
        assert primary.__notes__ == ["test shutdown also failed: engine unreachable"]
    else:
        with pytest.raises(OSError, match="engine unreachable"):
            exercise()


def test_failed_login_and_logout_remove_credentials_without_masking_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAMUEL_OCI_PUBLISHER_TOKEN", "publisher-secret")
    monkeypatch.setattr(container_release, "verify_gitea_publisher", lambda **_kw: {})
    paths: list[Path] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "login" in command:
            directory = Path(command[command.index("--config") + 1])
            paths.append(directory)
            (directory / "config.json").write_text("publisher-secret")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="login refused")
        raise OSError("logout unavailable")

    monkeypatch.setattr(container_release, "_run", fake_run)
    with (
        pytest.raises(ContainerReleaseError, match="registry login failed") as caught,
        container_release._publisher_docker_session(
            root=tmp_path,
            docker_command="sudo -n docker",
            api_url="https://registry.example",
            image_repository="registry.example/owner/samuel",
            publisher_user="owner",
            release_host_id="test",
            registry_insecure=False,
        ),
    ):
        pytest.fail("failed login must not yield a publisher session")
    assert paths and not paths[0].exists()
    assert any("logout unavailable" in note for note in caught.value.__notes__)
    assert os.environ["SAMUEL_OCI_PUBLISHER_TOKEN"] == "publisher-secret"
