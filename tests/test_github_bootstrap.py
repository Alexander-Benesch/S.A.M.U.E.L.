import base64
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from tests.test_container_init import _published_kit
from tests.test_release_trust import Repository
from tools.github_bootstrap import IMAGE, RELEASES, build_entry


def test_public_entry_binds_exact_kit_root_image_and_release(tmp_path: Path) -> None:
    repository = Repository(tmp_path)
    manifest, archive = _published_kit(tmp_path)
    container = manifest["container"]
    container.update(image=IMAGE, reference=f"{IMAGE}@{container['digest']}")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    entry = build_entry(manifest_path, repository.anchor)
    subprocess.run(["bash", "-n"], input=entry, check=True)
    encoded = entry.split(b"<<'SAMUEL_PAYLOAD'\n")[1].split(b"\nSAMUEL_PAYLOAD\n")[0]
    payload = base64.b64decode(encoded)
    assert hashlib.sha256(payload).hexdigest().encode() in entry
    with tarfile.open(fileobj=io.BytesIO(payload)) as bundle, tarfile.open(archive) as kit:
        assert set(bundle.getnames()) == {
            "tools/samuel-container",
            "tools/container_init.py",
            "bootstrap-profile.json",
            "trusted-root.json",
        }
        for name in ("tools/samuel-container", "tools/container_init.py"):
            member, original = bundle.extractfile(name), kit.extractfile("samuel-oci/" + name)
            assert member and original and member.read() == original.read()
        root = bundle.extractfile("trusted-root.json")
        assert root and root.read() == repository.anchor.read_bytes()
        profile_file = bundle.extractfile("bootstrap-profile.json")
        assert profile_file
        profile = json.load(profile_file)
        assert profile["trust_root_sha256"] == repository.anchor_hash
        assert profile["bootstrap_image"] == container["reference"]
        assert profile["metadata_url"] == profile["targets_url"] == f"{RELEASES}/{manifest['tag']}/"
    archive.write_bytes(archive.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="differs"):
        build_entry(manifest_path, repository.anchor)


def test_public_entry_points_to_private_log_with_inner_error(tmp_path: Path) -> None:
    import os
    import stat

    from tests.test_cli_identity import _terminal_run

    if os.geteuid() != 0:
        pytest.skip("the public entry requires a root PTY")

    repository = Repository(tmp_path)
    manifest, _ = _published_kit(tmp_path)
    container = manifest["container"]
    container.update(image=IMAGE, reference=f"{IMAGE}@{container['digest']}")
    manifest_path = tmp_path / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    entry = build_entry(manifest_path, repository.anchor)
    script = tmp_path / "samuel-install.sh"
    # Isolate both host directories while executing the actual embedded installer.
    script.write_bytes(
        entry.replace(b"/opt/", os.fsencode(tmp_path) + b"/").replace(
            b"/var/log/", os.fsencode(tmp_path) + b"/"
        )
    )
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\necho 'test-credential-only' >&2\nexit 23\n")
    docker.chmod(0o755)
    code, output = _terminal_run(
        ["bash", str(script)], [], env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    )
    (log,) = tmp_path.glob("samuel-install.*.log")
    assert code != 0 and output.strip().endswith(str(log))
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    detail = log.read_text()
    assert (
        "Docker daemon inaccessible" in detail and "host-check" in detail and "Status=23" in detail
    )
    assert f"exit={code}" in detail and "test-credential-only" not in detail + output

    code, output = _terminal_run(["bash", str(script), "--port", "invalid-sensitive"], [])
    (next_log,) = set(tmp_path.glob("samuel-install.*.log")) - {log}
    assert code == 2 and output.strip().endswith(str(next_log))
    assert "Aufruf:" in next_log.read_text() and "exit=2" in next_log.read_text()
    assert "invalid-sensitive" not in next_log.read_text() + output
