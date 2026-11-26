from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from samuel.release_trust import (
    ReleaseTrustError,
    read_release_source,
    release_manifest_target,
    release_source_document,
    validate_release_profile,
)
from tests.test_container_init import IMAGE, _inputs
from tests.test_release_trust import Repository
from tools.container_init import ContainerInitError, initialize, install_release_source


@pytest.fixture
def source(tmp_path: Path):
    repository = Repository(tmp_path)
    root = repository.anchor.read_bytes()
    profile = {
        "schema_version": 1,
        "bootstrap_image": IMAGE,
        "trust_root_sha256": hashlib.sha256(root).hexdigest(),
        "metadata_url": "http://release.example.test/metadata/",
        "targets_url": "http://release.example.test/targets/",
        "manifest_target": "release/2.0.0a35/manifest.json",
        "manifest_target_template": "release/{version}/manifest.json",
    }
    path = tmp_path / "source.json"
    path.write_bytes(release_source_document(profile, root, "c" * 64))
    return path, profile, root


def test_profile_resolves_only_operator_supplied_template_without_network(source):
    _, profile, _ = source
    assert release_manifest_target(profile) == "release/2.0.0a35/manifest.json"
    assert release_manifest_target(profile, "2.0.0b1") == "release/2.0.0b1/manifest.json"
    del profile["manifest_target_template"]
    assert validate_release_profile(profile) == profile
    assert release_manifest_target(profile) == "release/2.0.0a35/manifest.json"
    with pytest.raises(ReleaseTrustError, match="not configured"):
        release_manifest_target(profile, "2.0.0a36")


@pytest.mark.parametrize(
    "template",
    [
        "https://other.test/{version}",
        "../{version}/manifest.json",
        "/{version}",
        "releases/latest.json",
        "{version}/{version}",
        "{version}/{image}",
        "{version}?x=1",
        "{version}/$(command)",
        "{version}/space name",
    ],
)
def test_template_cannot_select_another_channel_or_command(source, template):
    _, profile, _ = source
    profile["manifest_target_template"] = template
    with pytest.raises(ReleaseTrustError):
        validate_release_profile(profile)


@pytest.mark.parametrize(
    "version", ["latest", "v2.0.0a36", "2.0.0a36.dev1", "../other", "2.0.0a36;sh"]
)
def test_version_input_cannot_be_a_path_or_command(source, version):
    _, profile, _ = source
    with pytest.raises(ReleaseTrustError, match="canonical"):
        release_manifest_target(profile, version)


@pytest.mark.parametrize("failure", ["root", "handoff", "extra", "symlink", "fifo", "oversize"])
def test_source_record_is_bounded_and_does_not_acquire_first_trust(source, failure, tmp_path):
    path, _, _ = source
    value = json.loads(path.read_bytes())
    if failure == "root":
        value["root"] = "other"
    elif failure == "handoff":
        value["initial_handoff"] = "verified"
    elif failure == "extra":
        value["shell"] = "arbitrary"
    if failure in {"root", "handoff", "extra"}:
        path.write_text(json.dumps(value))
    elif failure == "oversize":
        path.write_bytes(b" " * 3_000_000)
    else:
        path.unlink()
        if failure == "fifo":
            os.mkfifo(path)
        else:
            target = tmp_path / "other.json"
            target.write_text(json.dumps(value))
            path.symlink_to(target)
    with pytest.raises((ReleaseTrustError, OSError)):
        read_release_source(path)


@pytest.mark.skipif(os.geteuid() != 0, reason="actual installer ownership requires root")
def test_actual_initialization_retains_separate_operator_source_and_runtime_view(source, tmp_path):
    path, profile, root = source
    install = tmp_path / "installation"
    install.mkdir()
    inputs = _inputs(install)
    inputs["owner"] = (10001, 10001)
    assert initialize(**inputs) == "initialized"
    config_root = inputs["config_root"]
    install_release_source(config_root, path, "c" * 64, inputs["owner"])
    operator = config_root / ".release-source.json"
    runtime = config_root / "config/release-source.json"
    assert operator.read_bytes() == runtime.read_bytes() == path.read_bytes()
    assert operator.stat().st_uid == 0 and runtime.stat().st_uid == 10001
    assert operator.stat().st_mode & 0o777 == runtime.stat().st_mode & 0o777 == 0o600
    value = read_release_source(runtime)
    assert value["profile"] == profile and value["root"].encode() == root
    assert value["initial_handoff"] == "not_qualified_by_this_check"
    assert initialize(**inputs) == "already_initialized"
    install_release_source(config_root, path, "c" * 64, inputs["owner"], allow_create=False)
    before = operator.read_bytes()
    runtime.write_text("modified runtime projection")
    with pytest.raises(ContainerInitError, match="no implicit trust change"):
        install_release_source(config_root, path, "c" * 64, inputs["owner"], allow_create=False)
    assert operator.read_bytes() == before


def test_different_manifest_or_existing_installation_cannot_add_source_implicitly(source, tmp_path):
    path, _, _ = source
    config_root = tmp_path / "operator"
    (config_root / "config").mkdir(parents=True)
    with pytest.raises(ContainerInitError, match="another bootstrap manifest"):
        install_release_source(config_root, path, "d" * 64, (10001, 10001))
    with pytest.raises(ContainerInitError, match="explicit recovery"):
        install_release_source(config_root, path, "c" * 64, (10001, 10001), allow_create=False)
    assert list(config_root.iterdir()) == [config_root / "config"]
    assert list((config_root / "config").iterdir()) == []


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o620, 0o602, 0o610, 0o601, 0o666])
def test_operator_source_requires_private_descriptor_permissions(source, mode):
    path, _, _ = source
    path.chmod(mode)
    # Advisory reads remain possible; this is not an operator authority claim.
    assert read_release_source(path)["schema"] == "release-source.v1"
    with pytest.raises(ReleaseTrustError, match="owner or private permissions"):
        read_release_source(path, expected_owner=(os.geteuid(), os.getegid()))


@pytest.mark.parametrize("identity", ["user", "group"])
def test_operator_source_checks_actual_descriptor_owner(source, identity):
    path, _, _ = source
    path.chmod(0o600)
    owner = (os.geteuid() + (identity == "user"), os.getegid() + (identity == "group"))
    with pytest.raises(ReleaseTrustError, match="owner or private permissions"):
        read_release_source(path, expected_owner=owner)


def test_private_source_still_does_not_establish_first_trust(source):
    path, _, _ = source
    path.chmod(0o600)
    result = read_release_source(path, expected_owner=(os.geteuid(), os.getegid()))
    assert result["initial_handoff"] == "not_qualified_by_this_check"


@pytest.mark.parametrize("change", ["permissions", "bytes"])
def test_source_changes_during_descriptor_read_fail_closed(source, monkeypatch, change):
    path, _, _ = source
    path.chmod(0o600)
    original_fstat = os.fstat
    calls = 0

    def concurrent_change(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            if change == "permissions":
                path.chmod(0o666)
            else:
                path.write_bytes(path.read_bytes() + b" ")
        return original_fstat(descriptor)

    monkeypatch.setattr(os, "fstat", concurrent_change)
    with pytest.raises(ReleaseTrustError, match="changed while reading"):
        read_release_source(path, expected_owner=(os.geteuid(), os.getegid()))


def test_operator_ownership_is_not_taken_from_a_preopen_path_stat(source, monkeypatch):
    from types import SimpleNamespace

    path, _, _ = source
    path.chmod(0o600)
    # A forged path-stat cannot authorize a file whose opened descriptor has
    # another owner. The reader must not use these path-level claims.
    monkeypatch.setattr(Path, "stat", lambda *a, **k: SimpleNamespace(st_uid=78901, st_gid=78901))
    with pytest.raises(ReleaseTrustError, match="owner or private permissions"):
        read_release_source(path, expected_owner=(78901, 78901))
