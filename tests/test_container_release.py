from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from contextlib import contextmanager
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

    assert evidence["base_image"].startswith("python:3.10-slim@sha256:")
    assert evidence["base_platform_manifest_digest"].startswith("sha256:")
    assert evidence["runtime_packages"] >= 9
    assert evidence["build_packages"] >= 2
    assert evidence["runtime_lock_sha256"].startswith("sha256:")
    assert evidence["build_lock_sha256"].startswith("sha256:")
    assert evidence["system_packages_sha256"].startswith("sha256:")
    assert evidence["git_version"] == "2.47.3"


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


def test_contract_rejects_open_base_or_operator_state_context(tmp_path: Path) -> None:
    base_root = _contract_root(tmp_path / "base")
    dockerfile = base_root / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "python:3.10-slim@sha256:", "python:3.10-slim#sha256:"
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
    base = "python:3.10-slim@sha256:" + "b" * 64
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
                    'samuel --config "${SAMUEL_RUNTIME_CONFIG_DIR}" health || exit 1',
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
    base = "python:3.10-slim@sha256:" + "b" * 64
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


def test_image_inspection_requires_bound_runtime_healthcheck() -> None:
    version = "2.0.0a3"
    commit = "a" * 40
    source = "https://forge.example/owner/samuel"
    base = "python:3.10-slim@sha256:" + "b" * 64
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
            "Healthcheck": {"Test": ["CMD-SHELL", "samuel health || exit 1"]},
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


def test_runtime_verification_requires_the_contract_git_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = "2.0.0a9.dev0"
    commit = "a" * 40

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
        root=tmp_path,
        version=version,
        commit=commit,
        git_version="2.47.3",
    )

    with pytest.raises(ContainerReleaseError, match="runtime Git version"):
        container_release._verify_runtime(
            ["docker"],
            "samuel:test",
            root=tmp_path,
            version=version,
            commit=commit,
            git_version="2.47.2",
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
                "org.opencontainers.image.base.name": "python:3.10-slim@sha256:" + "b" * 64,
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
                                    'samuel --config "${SAMUEL_RUNTIME_CONFIG_DIR}" health || exit 1',
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
            "base_image": "python:3.10-slim@sha256:" + "b" * 64,
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
        "chown --reference=/samuel-workspaces" in " ".join(command) for command in observed_commands
    )
    assert any("--pull always" in " ".join(command) for command in observed_commands)
    assert sum("find /cleanup" in " ".join(command) for command in observed_commands) == 2


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
