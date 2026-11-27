from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from samuel.local_release import LocalReleaseError, oci_update_contract, prepare_oci_update
from samuel.release_trust import ReleaseTrustError, release_source_document
from tests.test_release_bundle import _bundle
from tests.test_release_trust import Repository


@pytest.fixture
def update_source(tmp_path: Path):
    repository = Repository(tmp_path)
    repository.target = "releases/2.0.0a35/release-manifest.json"
    manifest, assets = _bundle(repository)
    manifest.update(
        version="2.0.0a35",
        tag="v2.0.0a35",
        update_contract={**oci_update_contract(), "source_versions": ["2.0.0a34"]},
    )
    profile = {
        "schema_version": 1,
        "bootstrap_image": "registry.example.test/samuel@sha256:" + "d" * 64,
        "trust_root_sha256": repository.anchor_hash,
        "metadata_url": "https://repository.example.test/metadata/",
        "targets_url": "https://repository.example.test/targets/",
        "manifest_target": "releases/2.0.0a34/release-manifest.json",
        "manifest_target_template": "releases/{version}/release-manifest.json",
    }
    source = tmp_path / "source.json"
    source.write_bytes(release_source_document(profile, repository.anchor.read_bytes(), "b" * 64))
    return repository, manifest, assets, source


def _publish(update_source, *, expired: bool = False) -> None:
    repository, manifest, assets, _ = update_source
    repository.publish(
        json.dumps(manifest).encode(),
        extras={"releases/2.0.0a35/" + name: data for name, data in assets.items()},
        expired=expired,
    )


def _prepare(update_source, **overrides: Any) -> dict[str, Any]:
    repository, _, _, source = update_source
    args = {
        "source_path": source,
        "cache_dir": repository.cache,
        "source_version": "2.0.0a34",
        "target_version": "2.0.0a35",
        "source_state_schema": 10,
        "target_state_schema": 10,
        "fetcher": repository,
    }
    return prepare_oci_update(**(args | overrides))


def test_update_preparation_binds_signed_inputs_without_changing_operator_state(update_source):
    repository, manifest, assets, source = update_source
    _publish(update_source)
    before = source.read_bytes()
    result = _prepare(update_source)
    assert result["compatibility"]["status"] == "declared_compatible"
    assert result["source_version"] == "2.0.0a34"
    assert result["target_version"] == "2.0.0a35"
    assert result["manifest_sha256"] == hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
    assert result["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert len(result["inputs"]["artifacts"]) == len(assets)
    assert result["host_checks"] == "not_verified"
    assert result["operator_approval"] == "required"
    assert result["initial_handoff"] == "not_qualified_by_this_check"
    assert result["compatibility"]["qualification"] == "not_evaluated"
    assert not result["installation_performed"]
    assert "authority_witness" in result["backup_required"]
    assert "sqlite_online_backup_including_identity_and_authority" in result["backup_required"]
    assert source.read_bytes() == before
    assert not (repository.cache / "current").exists()


@pytest.mark.parametrize("version", ["latest", "../other", "2.0.0a35;sh", "v2.0.0a35"])
def test_bad_target_never_contacts_repository(update_source, version):
    repository, _, _, _ = update_source
    with pytest.raises(ReleaseTrustError, match="canonical"):
        _prepare(update_source, target_version=version)
    assert not repository.calls


def test_missing_operator_resolution_is_not_inferred(update_source):
    repository, _, _, source = update_source
    value = json.loads(source.read_bytes())
    del value["profile"]["manifest_target_template"]
    source.write_text(json.dumps(value))
    with pytest.raises(ReleaseTrustError, match="not configured"):
        _prepare(update_source)
    assert not repository.calls


def test_signed_manifest_with_other_version_is_not_the_requested_release(update_source):
    _, manifest, _, _ = update_source
    manifest.update(version="2.0.0a36", tag="v2.0.0a36")
    _publish(update_source)
    with pytest.raises(LocalReleaseError, match="requested target"):
        _prepare(update_source)


@pytest.mark.parametrize("failure", ["missing-contract", "weakened", "schema", "source"])
def test_signed_bytes_do_not_replace_compatibility(update_source, failure):
    _, manifest, _, _ = update_source
    overrides: dict[str, Any] = {}
    if failure == "missing-contract":
        del manifest["update_contract"]
    elif failure == "weakened":
        manifest["update_contract"]["preserve"] = ["configuration"]
    elif failure == "schema":
        overrides["source_state_schema"] = 9
    else:
        overrides["source_version"] = "2.0.0a33"
    _publish(update_source)
    with pytest.raises(LocalReleaseError):
        _prepare(update_source, **overrides)


@pytest.mark.parametrize("failure", ["expired", "asset", "root"])
def test_unverified_input_cannot_produce_update_preparation(update_source, failure):
    repository, _, _, source = update_source
    _publish(update_source, expired=failure == "expired")
    if failure == "asset":
        key = next(k for k in repository.files if k.endswith("artifact-0.tar.gz"))
        repository.files[key] = b"corrupted"
    elif failure == "root":
        value = json.loads(source.read_bytes())
        value["root"] += "x"
        source.write_text(json.dumps(value))
    with pytest.raises(ReleaseTrustError):
        _prepare(update_source)


def test_operator_reprepares_from_own_source_instead_of_dashboard_claim(update_source, tmp_path):
    repository, _, _, source = update_source
    _publish(update_source)
    private = tmp_path / "private.json"
    private.write_bytes(source.read_bytes())
    dashboard = _prepare(update_source)
    dashboard["operator_approval"] = "granted"
    dashboard["host_checks"] = "passed"
    dashboard["initial_handoff"] = "qualified"
    operator = _prepare(update_source, source_path=private, cache_dir=tmp_path / "operator-cache")
    assert operator["manifest_sha256"] == dashboard["manifest_sha256"]
    assert operator["operator_approval"] == "required"
    assert operator["host_checks"] == "not_verified"
    assert operator["initial_handoff"] == "not_qualified_by_this_check"
    assert repository.calls.count("metadata/timestamp.json") >= 2


@pytest.mark.parametrize("failure", ["owner", "permissions"])
def test_operator_preparation_rejects_unsafe_source_before_network(update_source, failure):
    import os

    repository, _, _, source = update_source
    source.chmod(0o600 if failure == "owner" else 0o644)
    owner = (os.geteuid() + (failure == "owner"), os.getegid())
    with pytest.raises(ReleaseTrustError, match="owner or private permissions"):
        _prepare(update_source, source_owner=owner)
    assert not repository.calls
    assert not repository.cache.exists()


def test_operator_preparation_reuses_tuf_from_private_source_without_accepting_approval(
    update_source,
):
    import os

    _, _, _, source = update_source
    source.chmod(0o600)
    _publish(update_source)
    result = _prepare(update_source, source_owner=(os.geteuid(), os.getegid()))
    assert result["compatibility"]["status"] == "declared_compatible"
    assert result["operator_approval"] == "required"
    assert result["host_checks"] == "not_verified"
    assert result["initial_handoff"] == "not_qualified_by_this_check"
    assert not result["installation_performed"]
