from __future__ import annotations

import hashlib
import json
import os

import pytest

from samuel.release_trust import ReleaseTrustError, release_source_document
from tests.test_container_init import ROOT, _inputs, _manifest
from tests.test_update_installer import update_kit as update_kit
from tools.container_init import ContainerInitError, initialize, prepare_installed_update
from tools.release_gate import materialize_oci_installer


@pytest.fixture
def installed_update(update_kit, tmp_path):
    repository, target_manifest, target_assets, source_path = update_kit
    source_document = json.loads(source_path.read_bytes())
    profile = source_document["profile"]
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile))
    old_dir = tmp_path / "old-release"
    old_dir.mkdir()
    old_assets = materialize_oci_installer(ROOT, old_dir, "2.0.0a34")
    old_manifest = _manifest()
    old_manifest.update(version="2.0.0a34", tag="v2.0.0a34", commit="a" * 40)
    old_manifest["container"].update(
        tag="v2.0.0a34",
        reference="registry.example/samuel@sha256:" + "c" * 64,
        digest="sha256:" + "c" * 64,
    )
    old_manifest["artifacts"] = [
        {
            "name": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
        }
        for p in old_assets
    ]
    old_raw = json.dumps(old_manifest).encode()
    inputs = _inputs(tmp_path)
    inputs.update(
        manifest=old_manifest,
        manifest_sha256=hashlib.sha256(old_raw).hexdigest(),
        owner=(10001, 10001),
        host_log_root="/var/log/samuel",
        host_backup_root="/srv/samuel/backups",
    )
    initialize(**inputs)
    repository.publish(
        json.dumps(target_manifest).encode(),
        extras={
            "releases/2.0.0a34/manifest.json": old_raw,
            **{"releases/2.0.0a34/" + p.name: p.read_bytes() for p in old_assets},
            **{"releases/2.0.0a35/" + p.name: p.read_bytes() for p in target_assets},
        },
    )
    return dict(
        config_root=inputs["config_root"],
        host_root="/",
        profile_path=profile_path,
        root_path=repository.anchor,
        cache=repository.cache,
        image=profile["bootstrap_image"],
        target_version="2.0.0a35",
        source_state_schema=10,
        target_state_schema=10,
        fetcher=repository,
    )


def snapshot(config):
    return {str(p.relative_to(config)): p.read_bytes() for p in config.rglob("*") if p.is_file()}


def install_source(args):
    profile = json.loads(args["profile_path"].read_bytes())
    receipt = json.loads((args["config_root"] / ".container-install.json").read_bytes())
    path = args["config_root"] / ".release-source.json"
    path.write_bytes(
        release_source_document(profile, args["root_path"].read_bytes(), receipt["manifest_sha256"])
    )
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("existing_source", [False, True])
def test_both_signed_kits_are_prepared_without_installation_changes(
    installed_update, existing_source
):
    args = installed_update
    if existing_source:
        install_source(args)
    before = snapshot(args["config_root"])
    result = prepare_installed_update(**args)
    assert result["release_source_adoption_required"] is (not existing_source)
    assert result["installation_performed"] is False
    assert result["operator_approval"] == "required"
    assert result["host_checks"] == "not_verified"
    assert result["initial_handoff"] == "not_qualified_by_this_check"
    assert result["source_installation"]["receipt"]["version"] == "2.0.0a34"
    assert "samuel-oci-2.0.0a34.tar.gz" in result["source_installer"]["archive"]
    assert "samuel-oci-2.0.0a35.tar.gz" in result["installer"]["archive"]
    for part in ("source_installer", "installer"):
        for path in result[part].values():
            assert (args["cache"] / path).exists()
    assert snapshot(args["config_root"]) == before
    assert prepare_installed_update(**args) == result


@pytest.mark.parametrize(
    "field", ["metadata_url", "targets_url", "trust_root_sha256", "manifest_target_template"]
)
def test_package_cannot_change_installed_trust_before_network(installed_update, field):
    args = installed_update
    install_source(args)
    profile = json.loads(args["profile_path"].read_bytes())
    profile[field] = {
        "metadata_url": "http://other.test/metadata/",
        "targets_url": "http://other.test/targets/",
        "trust_root_sha256": "f" * 64,
        "manifest_target_template": "other/{version}/manifest.json",
    }[field]
    args["profile_path"].write_text(json.dumps(profile))
    before = snapshot(args["config_root"])
    with pytest.raises(ContainerInitError, match="binding"):
        prepare_installed_update(**args)
    assert not args["fetcher"].calls
    assert snapshot(args["config_root"]) == before


@pytest.mark.parametrize("fault", ["mode", "owner", "symlink", "malformed"])
def test_invalid_existing_source_is_not_replaced_with_package(installed_update, fault):
    args = installed_update
    path = install_source(args)
    if fault == "mode":
        path.chmod(0o644)
    elif fault == "owner":
        os.chown(path, 10001, 10001)
    elif fault == "symlink":
        renamed = path.with_suffix(".old")
        path.rename(renamed)
        path.symlink_to(renamed)
    else:
        path.write_text("invalid")
    with pytest.raises((ReleaseTrustError, OSError, ValueError)):
        prepare_installed_update(**args)
    assert not args["fetcher"].calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("manifest_sha256", "f" * 64),
        ("revision", "f" * 40),
        ("image", "fixture/other@sha256:" + "f" * 64),
    ],
)
def test_signed_old_release_must_match_actual_receipt(installed_update, field, value):
    args = installed_update
    path = args["config_root"] / ".container-install.json"
    receipt = json.loads(path.read_bytes())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    before = snapshot(args["config_root"])
    with pytest.raises(ContainerInitError):
        prepare_installed_update(**args)
    assert snapshot(args["config_root"]) == before
    assert not (args["cache"] / "installers").exists()


def test_missing_source_on_newer_installation_requires_recovery(installed_update):
    args = installed_update
    path = args["config_root"] / ".container-install.json"
    receipt = json.loads(path.read_bytes())
    receipt["version"] = "2.0.0a35"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ContainerInitError, match="explicit recovery"):
        prepare_installed_update(**args)
    assert not args["fetcher"].calls


@pytest.mark.parametrize("what", ["receipt", "source", "appearing_source"])
def test_concurrent_source_changes_prevent_complete_preparation(
    installed_update, monkeypatch, what
):
    args = installed_update
    if what == "source":
        source_path = install_source(args)
    from tools import container_init

    original = container_init.prepare_update_installer

    def changed(**kwargs):
        result = original(**kwargs)
        if what == "receipt":
            path = args["config_root"] / ".container-install.json"
            value = json.loads(path.read_bytes())
            value["port"] += 1
            path.write_text(json.dumps(value))
        elif what == "source":
            value = json.loads(source_path.read_bytes())
            value["bootstrap_manifest_sha256"] = "f" * 64
            source_path.write_text(json.dumps(value))
        else:
            install_source(args)
        return result

    monkeypatch.setattr(container_init, "prepare_update_installer", changed)
    with pytest.raises(ContainerInitError, match="changed|appeared"):
        prepare_installed_update(**args)


@pytest.mark.parametrize("field", ["source_state_schema", "target_state_schema"])
def test_observed_schema_mismatch_never_returns_update_preparation(installed_update, field):
    from samuel.local_release import LocalReleaseError

    args = {**installed_update, field: 9}
    before = snapshot(args["config_root"])
    with pytest.raises(LocalReleaseError, match="schema"):
        prepare_installed_update(**args)
    assert snapshot(args["config_root"]) == before


def test_newer_package_verifier_preserves_installed_source_document(installed_update):
    args = installed_update
    source = install_source(args)
    before = source.read_bytes()
    profile = json.loads(args["profile_path"].read_bytes())
    profile["bootstrap_image"] = "fixture/new-verifier@sha256:" + "c" * 64
    args["profile_path"].write_text(json.dumps(profile))
    args["image"] = profile["bootstrap_image"]
    result = prepare_installed_update(**args)
    assert result["release_source_document"].encode() == before
    assert source.read_bytes() == before


def test_unmatched_package_verifier_is_rejected_before_network(installed_update):
    args = {**installed_update, "image": "fixture/other@sha256:" + "c" * 64}
    with pytest.raises(ContainerInitError, match="verifier"):
        prepare_installed_update(**args)
    assert not args["fetcher"].calls
