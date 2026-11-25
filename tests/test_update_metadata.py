from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from samuel.core.project_binding import project_overlay, validate_binding
from samuel.local_release import LocalReleaseError, oci_update_contract
from samuel.verifier_toolchain import prepare_toolchain_for_release, register_toolchain
from tests.test_container_init import ROOT, _inputs, _manifest
from tests.test_project_binding import _source_snapshot
from tests.test_update_bindings import SOURCE_IMAGE, TARGET_IMAGE
from tests.test_update_bindings import toolchain_update as toolchain_update
from tests.test_verifier_toolchain import toolchain as toolchain
from tools.container_init import ContainerInitError, initialize, prepare_update_metadata
from tools.release_gate import materialize_oci_installer


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    if os.geteuid() != 0:
        pytest.skip("actual private root-owned operator receipt required")
    inputs = _inputs(tmp_path)
    source = _manifest()
    source.update(version="2.0.0a34", tag="v2.0.0a34", commit="a" * 40)
    source["container"].update(reference=SOURCE_IMAGE, image="fixture/samuel", tag="v2.0.0a34")
    inputs.update(
        manifest=source,
        owner=(10001, 10001),
        host_log_root="/var/log/samuel",
        host_backup_root="/srv/samuel/backups",
    )
    initialize(**inputs)
    config = inputs["config_root"]
    (config / "config/eval.json").write_text('{"test_timeout":91,"operator_value":"preserve"}')
    destination = tmp_path / "published"
    destination.mkdir()
    assets = materialize_oci_installer(ROOT, destination, "2.0.0a35")
    target = _manifest()
    target.update(
        version="2.0.0a35",
        tag="v2.0.0a35",
        update_contract={**oci_update_contract(), "source_versions": ["2.0.0a34"]},
    )
    target["container"].update(
        reference=TARGET_IMAGE, image="fixture/samuel", digest="sha256:" + "b" * 64, tag="v2.0.0a35"
    )
    target["artifacts"] = [
        {
            "name": p.name,
            "size": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in assets
    ]
    path = destination / "manifest.json"
    path.write_text(json.dumps(target))
    monkeypatch.setattr("tools.container_init.verify_runtime", lambda _: (10001, 10001))
    return dict(
        config_root=config,
        host_root="/",
        manifest_path=path,
        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        image=TARGET_IMAGE,
        installer_archive=assets[0],
        installer_source=ROOT,
        source_state_schema=10,
    )


def bind_project(args, tmp_path):
    root = args["config_root"]
    source = tmp_path / "project-source"
    source.mkdir()
    content = project_overlay(str(source), "/projects/target")
    binding = validate_binding(
        {
            "schema": "project-binding.v2",
            "profile": "local-reference",
            "host_source": str(source),
            "container_target": "/projects/target",
            "repository": "https://git.example/owner/repo",
            "initial_revision": "c" * 40,
            "uid": 10001,
            "gid": 10001,
            "installation_sha256": hashlib.sha256(
                (root / ".container-install.json").read_bytes()
            ).hexdigest(),
            "compose_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "source_identity": {"device": source.stat().st_dev, "inode": source.stat().st_ino},
        }
    )
    (root / "config/project-binding.json").write_text(json.dumps(binding))
    (root / "compose/docker-compose.project.yml").write_text(content)
    with (root / ".env").open("a") as output:
        output.write("PROJECT_ROOT=/projects/target\n")
    return binding


def test_metadata_preparation_changes_only_release_fields_and_no_active_bytes(metadata):
    config = metadata["config_root"]
    before = _source_snapshot(config)
    old = json.loads((config / ".container-install.json").read_bytes())
    result = prepare_update_metadata(**metadata)
    assert _source_snapshot(config) == before
    assert result["activation_performed"] is False
    assert result["compatibility"]["operator_approval"] == "required"
    files = result["files"]
    assert set(files) == {
        ".container-install.json",
        "compose.env",
        "compose/docker-compose.yml",
        "compose/docker-compose.setup.yml",
    }
    target = json.loads(files[".container-install.json"])
    changed = {k for k in target if target[k] != old[k]}
    assert changed == {"version", "revision", "image", "manifest_sha256"}
    assert (
        result["target_installation_sha256"]
        == hashlib.sha256(files[".container-install.json"]).hexdigest()
    )
    assert (
        files["compose.env"].decode().replace(TARGET_IMAGE, SOURCE_IMAGE)
        == (config / "compose.env").read_text()
    )
    assert (
        result["source_files_sha256"][".container-install.json"]
        == before[".container-install.json"]
    )
    assert result["source_files_sha256"][".verifier-toolchain.json"] is None


def test_same_project_metadata_preserves_identity_and_initial_revision(metadata, tmp_path):
    original = bind_project(metadata, tmp_path)
    before = _source_snapshot(metadata["config_root"])
    result = prepare_update_metadata(**metadata)
    assert json.loads(result["files"]["config/project-binding.json"]) == {
        **original,
        "installation_sha256": result["target_installation_sha256"],
    }
    assert "compose/docker-compose.project.yml" not in result["files"]
    assert _source_snapshot(metadata["config_root"]) == before


@pytest.fixture
def registered_metadata(metadata, toolchain_update):
    args, _ = toolchain_update
    register_toolchain(
        metadata["config_root"], "/srv/samuel/toolchains/original", args["previous"].model_dump()
    )
    prepare_toolchain_for_release(**args)
    metadata["prepared_toolchain"] = args["root"]
    return metadata, args


def test_existing_registration_serializer_preserves_evaluation_policy(registered_metadata):
    args, _ = registered_metadata
    config = args["config_root"]
    before = _source_snapshot(config)
    old_eval = json.loads((config / "config/eval.json").read_bytes())
    result = prepare_update_metadata(**args)
    files = result["files"]
    new_eval = json.loads(files["config/eval.json"])
    assert {k: v for k, v in old_eval.items() if k != "verifier_toolchain"} == {
        k: v for k, v in new_eval.items() if k != "verifier_toolchain"
    }
    registration = json.loads(files[".verifier-toolchain.json"])
    assert registration["binding"] == new_eval["verifier_toolchain"]
    assert registration["binding"]["manifest"] == "/opt/samuel-verifier/toolchain-manifest.json"
    assert registration["host_root"] == "/srv/samuel/toolchains/update-" + args["manifest_sha256"]
    assert (
        hashlib.sha256(files["compose/docker-compose.toolchain.yml"]).hexdigest()
        == registration["compose_sha256"]
    )
    assert _source_snapshot(config) == before


@pytest.mark.parametrize(
    "failure",
    [
        "missing-copy",
        "changed-package",
        "changed-source-image",
        "changed-target-image",
        "changed-policy-binding",
    ],
)
def test_invalid_toolchain_preparation_cannot_produce_metadata(registered_metadata, failure):
    args, source_args = registered_metadata
    if failure == "missing-copy":
        args["prepared_toolchain"] = None
    elif failure == "changed-package":
        path = next(
            p for p in (args["prepared_toolchain"] / "packages").rglob("*.py") if p.is_file()
        )
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b"\nchanged")
    elif failure == "changed-policy-binding":
        path = args["config_root"] / "config/eval.json"
        data = json.loads(path.read_bytes())
        data["verifier_toolchain"]["sha256"] = "d" * 64
        path.write_text(json.dumps(data))
    else:
        path = (
            Path(source_args["previous"].manifest)
            if failure == "changed-source-image"
            else args["prepared_toolchain"] / "toolchain-manifest.json"
        )
        data = json.loads(path.read_bytes())
        data["runtime_image"] = "other@sha256:" + "d" * 64
        path.chmod(0o600)
        path.write_text(json.dumps(data))
    before = _source_snapshot(args["config_root"])
    with pytest.raises((ValueError, ContainerInitError)):
        prepare_update_metadata(**args)
    assert _source_snapshot(args["config_root"]) == before


@pytest.mark.parametrize(
    "failure",
    [
        "schema",
        "owner",
        "contract",
        "manifest",
        "installer",
        "symlink",
        "fifo",
        "unregistered-toolchain",
    ],
)
def test_invalid_source_target_or_metadata_is_rejected(metadata, tmp_path, monkeypatch, failure):
    if failure == "schema":
        metadata["source_state_schema"] = 9
    elif failure == "owner":
        monkeypatch.setattr("tools.container_init.verify_runtime", lambda _: (10002, 10002))
    elif failure == "contract":
        path = metadata["manifest_path"]
        data = json.loads(path.read_bytes())
        data["update_contract"]["preserve"] = []
        path.write_text(json.dumps(data))
        metadata["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif failure == "manifest":
        metadata["manifest_sha256"] = "f" * 64
    elif failure == "installer":
        metadata["installer_archive"].write_bytes(b"changed")
    elif failure == "unregistered-toolchain":
        metadata["prepared_toolchain"] = tmp_path
    else:
        path = metadata["config_root"] / "compose.env"
        path.unlink()
        if failure == "symlink":
            path.symlink_to(metadata["config_root"] / ".env")
        else:
            os.mkfifo(path)
    with pytest.raises((OSError, ContainerInitError, LocalReleaseError)):
        prepare_update_metadata(**metadata)


def test_source_metadata_change_during_preparation_is_not_published(metadata, monkeypatch):
    import tools.container_init as module

    original = module.verify_runtime

    def runtime(manifest):
        path = metadata["config_root"] / "compose.env"
        path.write_bytes(path.read_bytes() + b"CHANGED=1\n")
        return original(manifest)

    monkeypatch.setattr(module, "verify_runtime", runtime)
    with pytest.raises(ContainerInitError, match="metadata changed"):
        prepare_update_metadata(**metadata)


def test_individually_valid_target_toolchain_cannot_replace_package_contents(registered_metadata):
    from samuel.core.test_runner import artifact_files

    args, _ = registered_metadata
    target = args["prepared_toolchain"]
    packages = target / "packages"
    packages.chmod(0o755)
    (packages / "additional.txt").write_text("not present in the original toolchain")
    path = target / "toolchain-manifest.json"
    value = json.loads(path.read_bytes())
    value["files"] = artifact_files(packages)
    path.chmod(0o600)
    path.write_text(json.dumps(value))
    with pytest.raises(ContainerInitError, match="changes source contents"):
        prepare_update_metadata(**args)


@pytest.mark.parametrize(
    "value", [[], {"verifier_toolchain": {"manifest": "/unregistered", "sha256": "a" * 64}}]
)
def test_invalid_or_unregistered_evaluation_policy_cannot_be_ignored(metadata, value):
    path = metadata["config_root"] / "config/eval.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ContainerInitError, match="evaluation"):
        prepare_update_metadata(**metadata)
