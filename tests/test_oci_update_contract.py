from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from samuel.local_release import (
    LocalReleaseError,
    oci_update_contract,
    validate_oci_update_contract,
)
from tools.container_release import ContainerReleaseError, load_policy, record_container_manifest

ROOT = Path(__file__).parents[1]


def _manifest():
    return {
        "schema_version": 2,
        "product": "samuel",
        "version": "2.0.0a35",
        "tag": "v2.0.0a35",
        "commit": "a" * 40,
        "artifacts": [],
        "update_contract": {**oci_update_contract(), "source_versions": ["2.0.0a34"]},
    }


def _validate(manifest, **overrides):
    inputs = {"source_version": "2.0.0a34", "source_state_schema": 10, "target_state_schema": 10}
    return validate_oci_update_contract(manifest, **(inputs | overrides))


def test_declared_compatibility_is_neither_host_qualification_nor_authorization():
    manifest = _manifest()
    before = copy.deepcopy(manifest)
    result = _validate(manifest)
    assert result == {
        "status": "declared_compatible",
        "source_version": "2.0.0a34",
        "target_version": "2.0.0a35",
        "migration": "none",
        "host_checks": "not_verified",
        "operator_approval": "required",
        "backup": "required",
        "qualification": "not_evaluated",
    }
    assert manifest == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "future"),
        ("source_versions", []),
        ("source_versions", ["2.0.0a33"]),
        ("source_versions", ["2.0.0a34", "2.0.0a34"]),
        ("source_versions", ["2.0.0a34", {}]),
        ("source_versions", ["2.0.0a34", "latest"]),
        ("source_state_schema", True),
        ("source_state_schema", 9),
        ("target_state_schema", 11),
        ("migration", "shell command"),
        ("preserve", ["configuration"]),
        ("project_binding_schema", "project-binding.v1"),
        ("runtime_owner", "chown"),
        ("release_rebinding", ["workflow_approval"]),
        ("command", "exec arbitrary"),
    ],
)
def test_unsupported_or_weakened_contract_is_rejected(field, value):
    manifest = _manifest()
    manifest["update_contract"][field] = value
    with pytest.raises(LocalReleaseError):
        _validate(manifest)


def test_update_must_declare_narrow_release_rebinding_without_approval_transfer():
    manifest = _manifest()
    assert manifest["update_contract"]["release_rebinding"] == [
        "installation_release_identity",
        "project_installation_sha256",
        "verifier_release_identity_after_content_and_platform_check",
    ]
    del manifest["update_contract"]["release_rebinding"]
    with pytest.raises(LocalReleaseError, match="explicit OCI update contract"):
        _validate(manifest)


@pytest.mark.parametrize("contract", [None, {}, [], "compatible"])
def test_missing_contract_is_not_inferred_from_a_valid_release(contract):
    manifest = _manifest()
    manifest["update_contract"] = contract
    with pytest.raises(LocalReleaseError, match="explicit OCI update contract"):
        _validate(manifest)


@pytest.mark.parametrize("version", ["2.0.0a33", "2.0.0a34", "2.0.0a35.dev1", "latest"])
def test_same_old_and_nonrelease_targets_are_rejected(version):
    manifest = _manifest()
    manifest.update(version=version, tag=f"v{version}")
    with pytest.raises(LocalReleaseError, match="newer OCI release"):
        _validate(manifest)


@pytest.mark.parametrize(
    "inputs",
    [
        {"source_state_schema": 9},
        {"target_state_schema": 11},
        {"source_state_schema": True},
        {"target_state_schema": "10"},
        {"source_version": "2.0.0a33"},
    ],
)
def test_observed_version_and_schema_must_match_the_declaration(inputs):
    with pytest.raises(LocalReleaseError):
        _validate(_manifest(), **inputs)


def _publish_manifest(path: Path, version: str):
    document = _manifest()
    document.pop("update_contract")
    document.update(version=version, tag=f"v{version}", schema_version=1)
    path.write_text(json.dumps(document))
    return record_container_manifest(
        path,
        tag=f"v{version}",
        commit="a" * 40,
        image_repository="registry.example/owner/samuel",
        image_digest="sha256:" + "b" * 64,
        policy=load_policy(ROOT),
    )


def test_existing_manifest_publisher_binds_contract_only_for_successor_releases(tmp_path):
    old = _publish_manifest(tmp_path / "old.json", "2.0.0a34")
    assert "update_contract" not in old
    new = _publish_manifest(tmp_path / "new.json", "2.0.0a39")
    assert new["update_contract"] == oci_update_contract()
    assert json.loads((tmp_path / "new.json").read_text()) == new
    assert new["update_contract"]["source_versions"] == []
    with pytest.raises(LocalReleaseError, match="source release is not explicitly supported"):
        _validate(new)


def test_new_state_schema_blocks_publication_until_contract_is_reviewed(tmp_path, monkeypatch):
    monkeypatch.setattr("samuel.adapters.state.sqlite.SCHEMA_VERSION", 11)
    path = tmp_path / "manifest.json"
    with pytest.raises(ContainerReleaseError, match="review the OCI update contract"):
        _publish_manifest(path, "2.0.0a35")
    assert json.loads(path.read_text())["schema_version"] == 1
