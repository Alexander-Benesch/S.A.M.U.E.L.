"""Signed-input/installer integration, not a qualified handoff or Docker-host E2E."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.test_cli_identity import _terminal_run
from tests.test_container_init import IMAGE, ROOT, _published_kit
from tests.test_container_onboarding import _installer
from tests.test_release_trust import Repository
from tools.container_init import ContainerInitError, prepare_bootstrap, verify_delivery


@pytest.fixture
def bootstrap(tmp_path: Path):
    repository = Repository(tmp_path)
    published = tmp_path / "published"
    published.mkdir()
    manifest, archive = _published_kit(published)
    served = tmp_path / "served"
    served.mkdir()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(served))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = {
        "schema_version": 1,
        "bootstrap_image": IMAGE,
        "trust_root_sha256": repository.anchor_hash,
        "metadata_url": f"http://127.0.0.1:{server.server_port}/metadata/",
        "targets_url": f"http://127.0.0.1:{server.server_port}/targets/",
        "manifest_target": repository.target,
    }
    profile_path = tmp_path / "bootstrap-profile.json"
    profile_path.write_text(json.dumps(profile))

    def publish():
        assets = {i["name"]: (published / i["name"]).read_bytes() for i in manifest["artifacts"]}
        repository.publish(
            json.dumps(manifest).encode(), extras={"releases/" + k: v for k, v in assets.items()}
        )
        for name, content in repository.files.items():
            path = served / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    publish()
    try:
        yield repository, profile_path, manifest, archive, publish
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_prepared_kit_reuses_existing_delivery_checks_and_survives_retry(bootstrap):
    repository, profile, manifest, archive, _ = bootstrap
    result = prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
    assert len(result) == 5
    source = repository.cache / result[3]
    verify_delivery(manifest, repository.cache / result[2], source)
    assert (source / "tools/samuel-container").read_bytes() == (
        ROOT / "tools/samuel-container"
    ).read_bytes()
    assert prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE) == result
    (source / "tools/samuel-container").write_text("modified")
    with pytest.raises(ContainerInitError, match="differs from release"):
        prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)


@pytest.mark.parametrize("change", ["image", "root", "schema", "unknown", "missing"])
def test_invalid_bootstrap_binding_cannot_prepare_installer(bootstrap, change):
    repository, profile_path, _, _, _ = bootstrap
    profile = json.loads(profile_path.read_bytes())
    if change == "image":
        profile["bootstrap_image"] = "other@sha256:" + "b" * 64
    elif change == "root":
        profile["trust_root_sha256"] = "0" * 64
    elif change == "schema":
        profile["schema_version"] = True
    elif change == "unknown":
        profile["shell"] = "touch /tmp/forbidden"
    else:
        del profile["metadata_url"]
    profile_path.write_text(json.dumps(profile))
    with pytest.raises(RuntimeError):
        prepare_bootstrap(profile_path, repository.anchor, repository.cache, IMAGE)
    assert not (repository.cache / "installers").exists()


@pytest.mark.parametrize(
    "kind", ["traversal", "absolute", "symlink", "hardlink", "duplicate", "missing"]
)
def test_signed_but_unsafe_archive_is_rejected_before_extraction(bootstrap, kind):
    repository, profile, manifest, archive, publish = bootstrap
    replacement = archive.with_suffix(".replacement")
    with tarfile.open(archive, "r:gz") as original, tarfile.open(replacement, "w:gz") as output:
        for member in original.getmembers():
            if kind == "missing" and member.name.endswith("tools/samuel-container"):
                continue
            output.addfile(member, original.extractfile(member) if member.isfile() else None)
        if kind != "missing":
            names = {
                "traversal": "samuel-oci/../escaped",
                "absolute": "/escaped",
                "duplicate": "samuel-oci/tools/samuel-container",
            }
            member = tarfile.TarInfo(names.get(kind, "samuel-oci/linked"))
            if kind in {"symlink", "hardlink"}:
                member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
                member.linkname = "/outside"
                output.addfile(member)
            else:
                member.size = 3
                output.addfile(member, io.BytesIO(b"bad"))
    replacement.replace(archive)
    item = next(i for i in manifest["artifacts"] if i["name"] == archive.name)
    item.update(
        size=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    publish()
    with pytest.raises(ContainerInitError, match="unsafe|duplicate|incomplete"):
        prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
    assert not list((repository.cache / "installers").iterdir())
    assert not (repository.cache.parent / "escaped").exists()


def _bootstrap_operator(bootstrap, tmp_path: Path):
    repository, profile, _, _, _ = bootstrap
    operator = tmp_path / "operator"
    operator.mkdir()
    _, env, config = _installer(operator)
    docker = operator / "bin/docker"
    source = docker.read_text().replace(
        "elif a[0]=='run':\n",
        """elif a[0]=='run':
    if 'prepare-bootstrap' in a:
        mounts={}
        for value in a:
            if value.startswith('type=bind,'):
                fields=dict(piece.split('=',1) for piece in value.split(',') if '=' in piece)
                mounts[fields['dst']]=fields['src']
        args=a[a.index('/bootstrap/container_init.py'):]
        args=[mounts.get(value,value) for value in args]
        os.execv(sys.executable,[sys.executable,*args])
""",
    )
    docker.write_text(source)
    env["PATH"] = f"{operator / 'bin'}:{sys.prefix}/bin:{os.environ['PATH']}"
    command = [
        "bash",
        str(ROOT / "tools/samuel-container"),
        "install",
        "--bootstrap-profile",
        str(profile),
        "--root",
        str(operator / "host"),
        "--port",
        "18780",
        "--project",
        "single-codebase",
    ]
    return command, env, config


@pytest.mark.parametrize("default_profile", [False, True])
def test_one_bootstrap_call_hands_off_to_existing_installer_and_explicit_start(
    bootstrap, tmp_path: Path, default_profile: bool
):
    command, env, config = _bootstrap_operator(bootstrap, tmp_path)
    if default_profile:
        package = tmp_path / "authenticated-fixture-package"
        (package / "tools").mkdir(parents=True)
        for name in ("samuel-container", "container_init.py"):
            shutil.copyfile(ROOT / "tools" / name, package / "tools" / name)
        shutil.copyfile(bootstrap[1], package / "bootstrap-profile.json")
        shutil.copyfile(bootstrap[0].anchor, package / "trusted-root.json")
        command[1] = str(package / "tools/samuel-container")
        del command[3:5]
    # Signal a browser submission. This Docker double supplies a deliberately
    # incomplete installation receipt, so the independent start verification must refuse it.
    import threading
    import time

    waiting = tmp_path / "operator/host/var/lib/samuel-installer/dashboard"

    def submit():
        for _ in range(180):
            if waiting.exists():
                marker = tmp_path / "operator/host/etc/samuel/config/.managed-start"
                marker.parent.mkdir(exist_ok=True)
                marker.write_text("invalid test receipt")
                return
            time.sleep(0.1)

    threading.Thread(target=submit, daemon=True).start()
    password = b"bootstrap-operator-test-password"
    code, output = _terminal_run(
        command,
        [
            (b"Neues Dashboard-Passwort: ", password + b"\n"),
            (b"Dashboard-Passwort wiederholen: ", password + b"\n"),
        ],
        env=env,
    )
    assert code != 0 and waiting.exists(), output
    assert "Prüfen und starten" in output
    assert output.count("Neues Dashboard-Passwort:") == 1
    assert password.decode() not in output
    assert json.loads((config / "auth.json").read_bytes())["access_mode"] == "local_identity"
    trace = Path(env["TEST_DOCKER_TRACE"])
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    verifier = next(call for call in calls if "prepare-bootstrap" in call)
    assert (
        "--read-only" in verifier and "--cap-drop" in verifier and "no-new-privileges" in verifier
    )
    assert not any("docker.sock" in arg for call in calls for arg in call)
    # One-shot verifiers must not spawn the image's unrelated runtime writer.
    for call in calls:
        if call[0] == "run":
            assert "--no-healthcheck" in call
        if call[0] == "compose" and "run" in call:
            assert any(arg.endswith("maintenance-healthcheck.json") for arg in call)
        if call[0] == "compose" and "up" in call:
            assert not any(arg.endswith("maintenance-healthcheck.json") for arg in call)
    assert not any("SAMUEL_INSTALL_EXPECTED_MODE=production" in call for call in calls)
    assert "first download and extraction may take several minutes" in output
    assert "Grund für die Umstellung" not in output
    assert not any("approval" in call for call in calls)
    assert any("installed-operator" in call for call in calls)


def test_noninteractive_bootstrap_stops_before_docker_or_host_mutation(tmp_path: Path):
    _, env, _ = _installer(tmp_path)
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "tools/samuel-container"),
            "install",
            "--bootstrap-profile",
            str(tmp_path / "missing.json"),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "interactive terminal" in result.stderr
    assert not Path(env["TEST_DOCKER_TRACE"]).exists()


@pytest.mark.parametrize("failure", ["root", "target", "receipt", "source-receipt"])
def test_bootstrap_failure_cannot_reach_identity_or_runtime(
    bootstrap, tmp_path: Path, failure: str
):
    command, env, _ = _bootstrap_operator(bootstrap, tmp_path)
    if failure == "root":
        bootstrap[0].anchor.write_text("forged root")
    elif failure == "target":
        profile = json.loads(bootstrap[1].read_bytes())
        profile["manifest_target"] = "releases/missing.json"
        bootstrap[1].write_text(json.dumps(profile))
    else:
        docker = tmp_path / "operator/bin/docker"
        response = "SAMUEL_BOOTSTRAP_PREPARED\n../../escape\n" + "a" * 64 + "\n/tmp/evil\n/tmp/code"
        if failure == "source-receipt":
            response = "\n".join(
                [
                    "SAMUEL_BOOTSTRAP_PREPARED",
                    "artifacts/" + "a" * 64 + "/manifest.json",
                    "a" * 64,
                    "artifacts/" + "b" * 64 + "/samuel-oci-2.0.0a35.tar.gz",
                    "installers/" + "c" * 64,
                    "../../untrusted-source.json",
                ]
            )
        docker.write_text(
            docker.read_text().replace(
                "if 'prepare-bootstrap' in a:",
                "if 'prepare-bootstrap' in a:\n        print(" + repr(response) + ");sys.exit(0)",
            )
        )
    code, output = _terminal_run(command, [], env=env)
    assert code != 0
    calls = [json.loads(line) for line in Path(env["TEST_DOCKER_TRACE"]).read_text().splitlines()]
    assert not any("identity" in call or "up" in call for call in calls)
    assert not (tmp_path / "operator/host/etc/samuel").exists()
    assert "setup runtime ready" not in output


def test_kit_is_readable_in_nonroot_bind_mount_but_outer_cache_stays_private(bootstrap):
    repository, profile, _, _, _ = bootstrap
    previous_umask = os.umask(0o077)
    try:
        result = prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
    finally:
        os.umask(previous_umask)
    kit = repository.cache / result[3]
    assert repository.cache.stat().st_mode & 0o777 == 0o700
    assert kit.parent.stat().st_mode & 0o777 == 0o700
    for entry in (kit, *kit.rglob("*")):
        assert entry.stat().st_mode & 0o777 == (0o755 if entry.is_dir() else 0o644)


@pytest.mark.parametrize("relative", ["", "tools", "tools/samuel-container"])
def test_unreadable_cached_kit_is_rejected_without_implicit_repair(bootstrap, relative):
    repository, profile, _, _, _ = bootstrap
    result = prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
    entry = repository.cache / result[3] / relative
    mode = 0o700 if entry.is_dir() else 0o600
    entry.chmod(mode)
    with pytest.raises(ContainerInitError, match="permissions differ"):
        prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
    assert entry.stat().st_mode & 0o777 == mode


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_cached_kit_rejects_unexpected_nonregular_entries(bootstrap, kind):
    repository, profile, _, _, _ = bootstrap
    result = prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
    unexpected = repository.cache / result[3] / "unexpected"
    if kind == "symlink":
        unexpected.symlink_to(repository.anchor)
    else:
        os.mkfifo(unexpected)
    with pytest.raises(ContainerInitError, match="permissions differ"):
        prepare_bootstrap(profile, repository.anchor, repository.cache, IMAGE)
