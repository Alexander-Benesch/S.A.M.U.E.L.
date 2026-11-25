from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile

import pytest

from samuel.local_release import LocalReleaseError, oci_update_contract
from samuel.release_trust import ReleaseTrustError, release_source_document
from tests.test_container_init import IMAGE, ROOT, _manifest
from tests.test_release_trust import Repository
from tools.container_init import ContainerInitError, prepare_update_installer, verify_delivery
from tools.release_gate import materialize_oci_installer


@pytest.fixture
def update_kit(tmp_path):
    if os.geteuid() != 0:
        pytest.skip("actual private root-owned operator input requires root")
    repository = Repository(tmp_path)
    repository.target = "releases/2.0.0a35/manifest.json"
    published = tmp_path / "published"
    published.mkdir()
    paths = materialize_oci_installer(ROOT, published, "2.0.0a35")
    manifest = _manifest()
    manifest.update(
        version="2.0.0a35",
        tag="v2.0.0a35",
        update_contract={**oci_update_contract(), "source_versions": ["2.0.0a34"]},
    )
    manifest["container"]["tag"] = "v2.0.0a35"
    manifest["artifacts"] = [
        {
            "name": p.name,
            "size": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in paths
    ]
    source = tmp_path / "operator-source.json"
    source.write_bytes(
        release_source_document(
            {
                "schema_version": 1,
                "bootstrap_image": IMAGE,
                "trust_root_sha256": repository.anchor_hash,
                "metadata_url": "http://fixture.test/metadata/",
                "targets_url": "http://fixture.test/targets/",
                "manifest_target": "releases/2.0.0a34/manifest.json",
                "manifest_target_template": "releases/{version}/manifest.json",
            },
            repository.anchor.read_bytes(),
            "f" * 64,
        )
    )
    source.chmod(0o600)
    return repository, manifest, paths, source


def publish(update_kit):
    repository, manifest, paths, _ = update_kit
    repository.publish(
        json.dumps(manifest).encode(),
        extras={"releases/2.0.0a35/" + path.name: path.read_bytes() for path in paths},
    )


def prepare(update_kit):
    repository, _, _, source = update_kit
    return prepare_update_installer(
        source_path=source,
        cache=repository.cache,
        target_version="2.0.0a35",
        source_version="2.0.0a34",
        source_state_schema=10,
        target_state_schema=10,
        fetcher=repository,
    )


def test_operator_prepares_verified_kit_without_activation_or_source_changes(update_kit):
    repository, manifest, _, source = update_kit
    before = source.read_bytes()
    publish(update_kit)
    result = prepare(update_kit)
    kit = result["installer"]
    verify_delivery(
        manifest, repository.cache / kit["archive"], repository.cache / kit["directory"]
    )
    assert (repository.cache / kit["directory"] / "tools/samuel-container").read_bytes() == (
        ROOT / "tools/samuel-container"
    ).read_bytes()
    assert result["operator_approval"] == "required"
    assert result["host_checks"] == "not_verified"
    assert result["initial_handoff"] == "not_qualified_by_this_check"
    assert not result["installation_performed"]
    assert source.read_bytes() == before
    assert prepare(update_kit)["installer"] == kit
    assert not (repository.cache / "current").exists()


def test_changed_cached_kit_is_rejected_instead_of_repaired(update_kit):
    repository, _, _, _ = update_kit
    publish(update_kit)
    result = prepare(update_kit)
    script = repository.cache / result["installer"]["directory"] / "tools/samuel-container"
    script.write_text("changed")
    with pytest.raises(ContainerInitError, match="differs from release"):
        prepare(update_kit)
    assert script.read_text() == "changed"


@pytest.mark.parametrize("failure", ["permissions", "owner", "root"])
def test_operator_kit_rejects_untrusted_source_before_network(update_kit, failure):
    repository, _, _, source = update_kit
    if failure == "permissions":
        source.chmod(0o644)
    elif failure == "owner":
        os.chown(source, 10001, 10001)
    else:
        value = json.loads(source.read_bytes())
        value["root"] += "changed"
        source.write_text(json.dumps(value))
    with pytest.raises(ReleaseTrustError):
        prepare(update_kit)
    assert not repository.calls
    assert not repository.cache.exists()


@pytest.mark.parametrize("failure", ["compatibility", "image", "installer", "version"])
def test_invalid_update_never_extracts_kit(update_kit, failure):
    repository, manifest, _, _ = update_kit
    if failure == "compatibility":
        manifest["update_contract"]["source_versions"] = []
    elif failure == "image":
        manifest.pop("container")
    elif failure == "installer":
        manifest["artifacts"] = [
            a for a in manifest["artifacts"] if not a["name"].endswith(".tar.gz")
        ]
    else:
        manifest.update(version="2.0.0a36", tag="v2.0.0a36")
    publish(update_kit)
    with pytest.raises((LocalReleaseError, ContainerInitError, ReleaseTrustError)):
        prepare(update_kit)
    assert not (repository.cache / "installers").exists()


def test_signed_unsafe_update_archive_uses_same_preextraction_guard(update_kit):
    repository, manifest, paths, _ = update_kit
    archive = paths[0]
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo("samuel-oci/../escape")
        member.size = 3
        bundle.addfile(member, io.BytesIO(b"bad"))
    artifact = next(a for a in manifest["artifacts"] if a["name"] == archive.name)
    artifact.update(
        size=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    publish(update_kit)
    with pytest.raises(ContainerInitError, match="unsafe"):
        prepare(update_kit)
    assert not (repository.cache.parent / "escape").exists()
    assert not list((repository.cache / "installers").iterdir())
