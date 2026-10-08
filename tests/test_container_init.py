from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest

from tools.container_init import ContainerInitError, initialize, read_manifest, verify_image_inspect
from tools.release_gate import ReleaseGateError, verify_oci_install_delivery

ROOT = Path(__file__).parents[1]
IMAGE = "registry.example/samuel@sha256:" + "a" * 64


def _manifest() -> dict:
    return {
        "schema_version": 2,
        "product": "samuel",
        "version": "2.0.0a27",
        "tag": "v2.0.0a27",
        "commit": "b" * 40,
        "container": {
            "reference": IMAGE,
            "image": "registry.example/samuel",
            "digest": "sha256:" + "a" * 64,
            "platform": "linux/amd64",
            "tag": "v2.0.0a27",
        },
    }


def _inputs(tmp_path: Path) -> dict:
    roots = [tmp_path / name for name in ("operator", "state", "workspaces")]
    for path in roots:
        path.mkdir()
    defaults = tmp_path / "defaults"
    (defaults / "llm").mkdir(parents=True)
    (defaults / "agent.json").write_text(json.dumps({"workspace": {"work_dir": "old"}}))
    (defaults / "llm" / "defaults.json").write_text('{"planning":{"provider":"manual"}}\n')
    return {
        "manifest": _manifest(),
        "manifest_sha256": "c" * 64,
        "config_root": roots[0],
        "data_root": roots[1],
        "work_root": roots[2],
        "defaults": defaults,
        "compose_source": ROOT,
        "host_config_root": "/etc/samuel",
        "host_data_root": "/var/lib/samuel",
        "host_work_root": "/srv/samuel/workspaces",
        "port": 7777,
        "project": "samuel-test",
        "owner": (os.getuid(), os.getgid()),
    }


def test_clean_install_materializes_defaults_and_separate_compose_environment(tmp_path: Path):
    inputs = _inputs(tmp_path)
    assert initialize(**inputs) == "initialized"
    config = inputs["config_root"]
    assert "SAMUEL_API_KEY=" not in (config / ".env").read_text()
    assert (config / ".env").stat().st_mode & 0o777 == 0o600
    assert (config / "config" / "llm" / "defaults.json").read_text().startswith('{"planning"')
    agent = json.loads((config / "config" / "agent.json").read_text())
    assert agent["data_dir"] == "/app/data"
    assert agent["workspace"]["work_dir"] == "/samuel-workspaces"
    variables = (config / "compose.env").read_text()
    assert f"SAMUEL_IMAGE={IMAGE}\n" in variables
    assert "SAMUEL_DASHBOARD_BIND=127.0.0.1\n" in variables
    assert "SAMUEL_ENV_FILE=/etc/samuel/.env\n" in variables
    assert "SAMUEL_API_KEY" not in variables
    assert (inputs["data_root"] / "backups").is_dir()
    assert (config / "compose" / "docker-compose.setup.yml").read_bytes() == (
        ROOT / "docker-compose.setup.yml"
    ).read_bytes()


def test_rerun_preserves_changed_operator_config_secrets_and_state(tmp_path: Path):
    inputs = _inputs(tmp_path)
    initialize(**inputs)
    config = inputs["config_root"]
    (config / ".env").write_text("SAMUEL_API_KEY=operator-value\n")
    (config / "config" / "agent.json").write_text('{"operator":"changed"}\n')
    (inputs["data_root"] / "state.sqlite3").write_bytes(b"operator-state")
    before = {
        p: p.read_bytes()
        for root in (config, inputs["data_root"])
        for p in root.rglob("*")
        if p.is_file()
    }
    assert initialize(**inputs) == "already_initialized"
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize("root_name", ["config_root", "data_root", "work_root"])
def test_nonempty_roots_fail_before_changes(tmp_path: Path, root_name: str):
    inputs = _inputs(tmp_path)
    existing = inputs[root_name] / "existing.yaml"
    existing.write_text("operator: retained\n")
    with pytest.raises(ContainerInitError, match="must be empty"):
        initialize(**inputs)
    assert existing.read_text() == "operator: retained\n"
    assert not (inputs["config_root"] / "config").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("port", 0),
        ("project", "../other"),
        ("host_data_root", "/data\nSAMUEL_IMAGE=bad"),
        ("host_work_root", "/srv/../other"),
    ],
)
def test_invalid_layout_fails_before_changes(tmp_path: Path, field: str, value):
    inputs = _inputs(tmp_path)
    inputs[field] = value
    with pytest.raises(ContainerInitError):
        initialize(**inputs)
    assert not any(inputs["config_root"].iterdir())


def test_symlink_default_is_rejected_before_writes(tmp_path: Path):
    inputs = _inputs(tmp_path)
    (inputs["defaults"] / "escaped.json").symlink_to(tmp_path / "external")
    with pytest.raises(ContainerInitError, match="symlink"):
        initialize(**inputs)
    assert not any(inputs["config_root"].iterdir())


def test_changed_image_binding_is_not_an_update(tmp_path: Path):
    inputs = _inputs(tmp_path)
    initialize(**inputs)
    inputs["manifest"] = dict(inputs["manifest"], commit="d" * 40)
    with pytest.raises(ContainerInitError, match="not an update"):
        initialize(**inputs)


def test_manifest_hash_and_immutable_identity(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest()))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert read_manifest(path, digest, IMAGE)["version"] == "2.0.0a27"
    with pytest.raises(ContainerInitError, match="SHA-256 mismatch"):
        read_manifest(path, "0" * 64, IMAGE)
    with pytest.raises(ContainerInitError, match="container.reference"):
        read_manifest(path, digest, "registry.example/samuel:latest")
    with pytest.raises(ContainerInitError, match="container.reference"):
        read_manifest(path, digest, IMAGE.replace("a" * 64, "d" * 64))


@pytest.mark.parametrize(
    "field,value", [("schema_version", 1), ("tag", "v2.0.0a15"), ("commit", "short")]
)
def test_inconsistent_manifest_identity_is_rejected(tmp_path: Path, field: str, value):
    manifest = _manifest()
    manifest[field] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ContainerInitError, match="identity"):
        read_manifest(path, hashlib.sha256(path.read_bytes()).hexdigest(), IMAGE)


def test_image_labels_and_actual_user_must_match_manifest(monkeypatch):
    manifest = _manifest()
    owner = (123, 456)
    monkeypatch.setattr(os, "getuid", lambda: owner[0])
    monkeypatch.setattr(os, "getgid", lambda: owner[1])
    inspected: list[dict[str, Any]] = [
        {
            "Config": {
                "Labels": {
                    "org.opencontainers.image.version": manifest["version"],
                    "org.opencontainers.image.revision": manifest["commit"],
                }
            },
            "Os": "linux",
            "Architecture": "amd64",
            "RepoDigests": [IMAGE],
        }
    ]
    verify_image_inspect(manifest, inspected, owner)
    inspected[0]["Config"]["Labels"]["org.opencontainers.image.revision"] = "d" * 40
    with pytest.raises(ContainerInitError, match="OCI identity"):
        verify_image_inspect(manifest, inspected, owner)


def test_shell_rejects_invalid_checksum_without_docker_or_host_mutations(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest()))
    root = tmp_path / "empty-host"
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "tools" / "samuel-container"),
            "init",
            "--manifest",
            str(manifest),
            "--manifest-sha256",
            "0" * 64,
            "--image",
            IMAGE,
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "SHA-256 mismatch" in result.stderr
    assert not root.exists()


def _installer_archive(
    tmp_path: Path, *, omit: str = "", stale_doc: bool = False, stale_headline: bool = False
) -> Path:
    import io

    path = tmp_path / "samuel-2.0.0a27.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name in (
            "tools/samuel-container",
            "tools/container_init.py",
            "docker-compose.yml",
            "docker-compose.setup.yml",
            "docs/INSTALL.md",
        ):
            if name == omit:
                continue
            raw = (ROOT / name).read_bytes()
            if name == "docs/INSTALL.md" and stale_doc:
                raw = raw.replace(
                    b"<!-- oci-first-install:start -->",
                    b"<!-- oci-first-install:start -->\ngit checkout v2.0.0a15\n",
                )
            if name == "docs/INSTALL.md" and stale_headline:
                raw = "`v2.0.0a26` ist der jüngste veröffentlichte Alpha-Kandidat.\n".encode() + raw
            member = tarfile.TarInfo("samuel-2.0.0a27/" + name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    return path


def test_release_gate_checks_actual_shipped_installer_archive(tmp_path: Path):
    verify_oci_install_delivery(_installer_archive(tmp_path))


@pytest.mark.parametrize(
    "omit", ["tools/samuel-container", "tools/container_init.py", "docker-compose.setup.yml"]
)
def test_release_gate_rejects_missing_operator_delivery(tmp_path: Path, omit: str):
    with pytest.raises(ReleaseGateError, match="lacks OCI first-install"):
        verify_oci_install_delivery(_installer_archive(tmp_path, omit=omit))


def test_release_gate_rejects_historical_identity_in_current_installation_commands(tmp_path: Path):
    with pytest.raises(ReleaseGateError, match="hard-code"):
        verify_oci_install_delivery(_installer_archive(tmp_path, stale_doc=True))


def _published_kit(tmp_path: Path) -> tuple[dict, Path]:
    from tools.release_gate import materialize_oci_installer

    paths = materialize_oci_installer(ROOT, tmp_path, "2.0.0a27")
    manifest = _manifest()
    manifest["artifacts"] = [
        {
            "name": p.name,
            "size": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in paths
    ]
    return manifest, paths[0]


def test_release_bound_installer_checks_archive_and_extracted_files(tmp_path: Path):
    from tools.container_init import verify_delivery

    manifest, archive = _published_kit(tmp_path)
    verify_delivery(manifest, archive, ROOT)
    manifest["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(ContainerInitError, match="artifact binding mismatch"):
        verify_delivery(manifest, archive, ROOT)


@pytest.mark.parametrize(
    "name", ["docker-compose.yml", "docker-compose.setup.yml", "tools/samuel-container"]
)
def test_mixed_or_changed_operator_files_are_rejected(tmp_path: Path, name: str):
    import shutil

    from tools.container_init import verify_delivery

    manifest, archive = _published_kit(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            if member.isdir():
                continue
            path = source.joinpath(*Path(member.name).parts[1:])
            path.parent.mkdir(parents=True, exist_ok=True)
            stream = bundle.extractfile(member)
            assert stream is not None
            with path.open("wb") as out:
                shutil.copyfileobj(stream, out)
    (source / name).write_text("changed operator delivery\n")
    with pytest.raises(ContainerInitError, match="binding mismatch|differs from release"):
        verify_delivery(manifest, archive, source)


def test_published_installer_is_deterministic_and_create_only(tmp_path: Path):
    from tools.release_gate import materialize_oci_installer

    _, archive = _published_kit(tmp_path)
    original = archive.read_bytes()
    assert materialize_oci_installer(ROOT, tmp_path, "2.0.0a27")[0].read_bytes() == original
    archive.write_bytes(b"other release asset")
    with pytest.raises(ReleaseGateError, match="existing OCI installer asset differs"):
        materialize_oci_installer(ROOT, tmp_path, "2.0.0a27")


@pytest.mark.parametrize("root_name", ["log_root", "backup_root"])
def test_nonempty_external_logs_and_backups_block_initialization(tmp_path: Path, root_name: str):
    inputs = _inputs(tmp_path)
    for name in ("log_root", "backup_root"):
        inputs[name] = tmp_path / name
        inputs[name].mkdir()
    (inputs[root_name] / "existing").write_text("preserve")
    with pytest.raises(ContainerInitError, match="must be empty"):
        initialize(**inputs)
    assert (inputs[root_name] / "existing").read_text() == "preserve"
    assert not (inputs["config_root"] / ".container-install.json").exists()


def test_partial_io_failure_never_writes_completed_receipt(tmp_path: Path, monkeypatch):
    import tools.container_init as module

    inputs = _inputs(tmp_path)

    def no_space(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module, "_write", no_space)
    with pytest.raises(OSError, match="disk full"):
        initialize(**inputs)
    assert not (inputs["config_root"] / ".container-install.json").exists()
    # Partial config blocks a new bootstrap rather than being overwritten.
    with pytest.raises(ContainerInitError, match="must be empty"):
        initialize(**inputs)


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("missing", "docker missing"),
        ("daemon", "daemon inaccessible"),
        ("old-engine", "Engine >=26"),
        ("old-compose", "Compose >=2.26"),
        ("missing-compose", "Compose plugin missing"),
        ("host-arch", "host platform"),
        ("daemon-arch", "daemon platform"),
        ("pull", "image unavailable"),
        ("login", "existing docker login"),
        ("invalid-manifest", "immutable container.reference"),
        ("verify", "invalid release manifest"),
    ],
)
def test_bootstrap_preflight_and_registry_failures_preserve_empty_host(
    tmp_path: Path, failure: str, expected: str
):
    import shutil

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("dirname", "sha256sum", "realpath", "sed", "mktemp", "cp", "chmod", "rm"):
        executable = shutil.which(name)
        assert executable is not None
        (bin_dir / name).symlink_to(executable)
    (bin_dir / "uname").write_text(
        '#!/bin/bash\nif [[ "$1" == -s ]]; then echo Linux; elif [[ "$FAILURE" == host-arch ]]; then echo aarch64; else echo x86_64; fi\n'
    )
    (bin_dir / "uname").chmod(0o755)
    if failure != "missing":
        (bin_dir / "docker").write_text("""#!/bin/bash
case "$1/$2" in
 version/--format) [[ "$FAILURE" != daemon ]] || exit 1; if [[ "$FAILURE" == old-engine ]]; then echo 25.0.0; else echo 26.1.5; fi ;;
 info/--format) if [[ "$FAILURE" == daemon-arch ]]; then echo linux/aarch64; else echo linux/x86_64; fi ;;
 compose/version) [[ "$FAILURE" != missing-compose ]] || exit 1; if [[ "$FAILURE" == old-compose ]]; then echo 2.20.0; else echo 2.26.1; fi ;;
 pull/--platform) if [[ "$FAILURE" == pull || "$FAILURE" == login ]]; then echo 'private-diagnostic-SCM_TOKEN=should-never-leak' >&2; exit 1; fi ;;
 image/inspect) echo '[]' ;;
 run/--rm) echo 'invalid release manifest' >&2; exit 1 ;;
 *) exit 99 ;;
esac
""")
        (bin_dir / "docker").chmod(0o755)
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({} if failure == "invalid-manifest" else _manifest()))
    root = tmp_path / "new-host"
    result = subprocess.run(
        [
            "/bin/bash",
            str(ROOT / "tools/samuel-container"),
            "init",
            "--manifest",
            str(manifest),
            "--manifest-sha256",
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "--root",
            str(root),
        ],
        env={"PATH": str(bin_dir), "FAILURE": failure},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert expected in result.stderr
    assert "should-never-leak" not in result.stdout + result.stderr
    assert not root.exists()


@pytest.mark.parametrize("failure", ["cli-setup", "start", "readiness", "identity"])
def test_runtime_failure_does_not_claim_completed_installation(tmp_path: Path, failure: str):
    import shutil
    import sys

    probe_fixture = tmp_path / "api-fixture.py"
    probe_fixture.write_text("""import io,json,os,sys,urllib.request
for index,arg in enumerate(sys.argv):
 if arg=='-e':
  key,value=sys.argv[index+1].split('=',1);os.environ[key]=value
os.environ['SAMUEL_API_KEY']='synthetic-fixture-key'
os.environ['SAMUEL_BUILD_REVISION']='d'*40
os.environ.setdefault('SAMUEL_INSTALL_EXPECTED_VERSION','2.0.0a27')
def response(request,timeout):
 path=request.full_url
 if path.endswith('/setup/status'):value={'configuration':{'mode':'setup'}}
 elif path.endswith('/dashboard/status'):value={'build':{'product_version':'2.0.0a27','revision':'d'*40}}
 else:value={'healthy':True}
 return io.BytesIO(json.dumps(value).encode())
urllib.request.urlopen=response
exec(sys.argv[-1])
""")
    _, archive = _published_kit(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest()))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in (
        "dirname",
        "sha256sum",
        "realpath",
        "sed",
        "mktemp",
        "cp",
        "chmod",
        "rm",
        "cmp",
        "mkdir",
    ):
        executable = shutil.which(name)
        assert executable is not None
        (bin_dir / name).symlink_to(executable)
    (bin_dir / "sleep").write_text("#!/bin/bash\nexit 0\n")
    (bin_dir / "uname").write_text(
        '#!/bin/bash\nif [[ "$1" == -s ]]; then echo Linux; else echo x86_64; fi\n'
    )
    (bin_dir / "docker").write_text("""#!/bin/bash
case "$1/$2" in
 version/--format) echo 26.1.5 ;;
 info/--format) echo linux/amd64 ;;
 compose/version) echo 2.26.1 ;;
 pull/--platform) exit 0 ;;
 image/inspect) if [[ "$3" == --format ]]; then if [[ "$4" == *version* ]]; then echo 2.0.0a27; else echo bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb; fi; else echo '[]'; fi ;;
 inspect/--format) echo "$TEST_IMAGE" ;;
 run/--rm) if [[ " $* " == *" -i "* ]]; then while IFS= read -r ignored; do :; done; fi; echo initialized ;;
 compose/--env-file)
  for arg in "$@"; do
    if [[ "$arg" == run && "$FAILURE" == cli-setup ]]; then exit 1; fi
    if [[ "$arg" == up && "$FAILURE" == start ]]; then exit 1; fi
    if [[ "$arg" == exec ]]; then
      if [[ "$FAILURE" == identity ]]; then exec "$TEST_INTERPRETER" "$TEST_PROBE_SCRIPT" "$@"; fi
      exit 1
    fi
    if [[ "$arg" == ps ]]; then echo synthetic-container; fi
  done ;;
 *) exit 99 ;;
esac
""")
    for name in ("sleep", "uname", "docker"):
        (bin_dir / name).chmod(0o755)
    env = {
        "PATH": str(bin_dir),
        "FAILURE": failure,
        "TEST_INTERPRETER": sys.executable,
        "TEST_PROBE_SCRIPT": str(probe_fixture),
        "TEST_IMAGE": IMAGE,
    }
    # env must inherit this controlled PATH rather than the real host Docker.
    actual_env = shutil.which("env")
    assert actual_env is not None
    (bin_dir / "env").symlink_to(actual_env)
    result = subprocess.run(
        [
            "/bin/bash",
            str(ROOT / "tools/samuel-container"),
            "install",
            "--manifest",
            str(manifest),
            "--manifest-sha256",
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "--installer-archive",
            str(archive),
            "--root",
            str(tmp_path / "host"),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "runtime ready" not in result.stdout and "Open:" not in result.stdout
    assert "failed" in result.stderr


def test_image_runtime_architecture_is_validated_before_ownership(monkeypatch):
    import tools.container_init as module

    monkeypatch.setattr(module.importlib.metadata, "version", lambda _: "2.0.0a27")
    monkeypatch.setenv("SAMUEL_BUILD_REVISION", "b" * 40)
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    with pytest.raises(ContainerInitError, match="platform mismatch"):
        module.verify_runtime(_manifest())


@pytest.mark.parametrize(
    "relative", ["compose.env", "compose/docker-compose.yml", "compose/docker-compose.setup.yml"]
)
def test_changed_installed_compose_control_blocks_before_runtime_start(
    tmp_path: Path, relative: str
):
    inputs = _inputs(tmp_path)
    initialize(**inputs)
    operator = inputs["config_root"] / "config/agent.json"
    before = operator.read_bytes()
    control = inputs["config_root"] / relative
    control.write_text("SAMUEL_IMAGE=foreign-runtime\n")
    with pytest.raises(ContainerInitError, match="differs from release binding"):
        initialize(**inputs)
    assert operator.read_bytes() == before


def test_compose_internal_bind_cannot_be_shadowed_by_wizard_environment(monkeypatch):
    from samuel.cli import _resolve_dashboard_bind

    monkeypatch.setenv("DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setenv("DASHBOARD_PORT", "9090")

    for filename in ("docker-compose.yml", "docker-compose.setup.yml"):
        line = next(
            line
            for line in (ROOT / filename).read_text().splitlines()
            if line.strip().startswith("command:")
        )
        command = json.loads(line.split(":", 1)[1].strip())
        assert _resolve_dashboard_bind(
            command[command.index("--host") + 1], int(command[command.index("--port") + 1])
        ) == ("0.0.0.0", 7777)


@pytest.mark.parametrize("mode", ["setup", "production"])
@pytest.mark.parametrize("local_ready", [True, False])
@pytest.mark.parametrize("healthy", [True, False])
def test_readiness_distinguishes_empty_setup_from_production(
    monkeypatch, mode, local_ready, healthy
):
    import io
    import urllib.request

    source = (ROOT / "tools/samuel-container").read_text()
    probe = source.split("probe='", 1)[1].split("'\n# Compare", 1)[0]
    monkeypatch.setenv("SAMUEL_API_KEY", "test-key")
    monkeypatch.setenv("SAMUEL_INSTALL_EXPECTED_MODE", mode)
    monkeypatch.setenv("SAMUEL_INSTALL_EXPECTED_VERSION", "2.0.0a27")
    monkeypatch.setenv("SAMUEL_INSTALL_EXPECTED_REVISION", "b" * 40)

    def response(request, timeout):
        if request.full_url.endswith("/setup/status"):
            value = {"configuration": {"mode": mode}}
        elif request.full_url.endswith("/dashboard/status"):
            value = {"build": {"product_version": "2.0.0a27", "revision": "b" * 40}}
        else:
            value = {
                "healthy": healthy,
                "checks": {key: True for key in ("python", "git", "config", "state", "authority")},
            }
            value["checks"]["authority"] = local_ready
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(urllib.request, "urlopen", response)
    expected_ready = local_ready if mode == "setup" else healthy
    if expected_ready:
        exec(probe, {})
    else:
        with pytest.raises(AssertionError):
            exec(probe, {})


def test_release_gate_rejects_stale_current_release_claim_outside_oci_commands(tmp_path):
    with pytest.raises(ReleaseGateError, match="current release claim"):
        verify_oci_install_delivery(_installer_archive(tmp_path, stale_headline=True))
