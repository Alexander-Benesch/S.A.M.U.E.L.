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
