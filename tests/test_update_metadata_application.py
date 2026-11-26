from __future__ import annotations

import hashlib
import json
import os
import tarfile
from pathlib import Path

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.slices.privacy.retention import create_managed_backup
from samuel.slices.setup.handler import SetupHandler
from tests.test_container_init import ROOT
from tests.test_retention import _policy
from tests.test_update_bindings import toolchain_update as toolchain_update
from tests.test_update_metadata import bind_project
from tests.test_update_metadata import metadata as metadata
from tests.test_update_metadata import registered_metadata as registered_metadata
from tests.test_verifier_toolchain import toolchain as toolchain
from tools.container_init import ContainerInitError, apply_update_metadata, capture_update_files
from tools.release_gate import materialize_oci_installer


@pytest.fixture
def application(metadata, tmp_path, request):
    registered = getattr(request, "param", None) == "registered"
    if registered:
        request.getfixturevalue("registered_metadata")
    config = metadata["config_root"]
    receipt_path = config / ".container-install.json"
    receipt = json.loads(receipt_path.read_bytes())
    published = tmp_path / "source-published"
    published.mkdir()
    assets = materialize_oci_installer(ROOT, published, receipt["version"])
    source = json.loads(metadata["manifest_path"].read_bytes())
    source.update(
        version=receipt["version"], tag="v" + receipt["version"], commit=receipt["revision"]
    )
    source["container"].update(
        reference=receipt["image"],
        image=receipt["image"].split("@")[0],
        digest=receipt["image"].split("@")[1],
        tag="v" + receipt["version"],
    )
    source["artifacts"] = [
        {
            "name": p.name,
            "size": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in assets
    ]
    manifest = published / "manifest.json"
    manifest.write_text(json.dumps(source))
    receipt["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    bind_project(metadata, tmp_path)
    for name in ("config/eval.json", "config/project-binding.json"):
        policy = config / name
        policy.chmod(0o600)
        os.chown(policy, 10001, 10001)
        os.setxattr(policy, "user.samuel-preserve", b"original-policy-attributes")
    store = SQLiteStateStore(tmp_path / "state")
    backup = create_managed_backup(
        policy=_policy(tmp_path), diagnostics=store, state=store.retention
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    parent = tmp_path / "private-captures"
    parent.mkdir(mode=0o700)
    capture = dict(
        config_root=config,
        data_root=tmp_path / "state",
        log_root=logs,
        work_root=tmp_path / "workspaces",
        host_root="/",
        manifest_path=manifest,
        installer_archive=assets[0],
        installer_source=ROOT,
        state_backup=backup.path,
        state_backup_sha256=backup.digest.removeprefix("sha256:"),
        destination=parent / "attempt",
    )
    if registered:
        binding = json.loads((config / ".verifier-toolchain.json").read_bytes())["binding"]
        capture["toolchain_root"] = Path(binding["manifest"]).parent
    capture_update_files(**capture)
    metadata.update(
        capture_directory=capture["destination"],
        capture_sha256=hashlib.sha256(
            (capture["destination"] / "capture.json").read_bytes()
        ).hexdigest(),
    )
    return metadata


def snapshot(root):
    return {
        str(p.relative_to(root)): (
            p.read_bytes(),
            p.stat().st_uid,
            p.stat().st_gid,
            p.stat().st_mode & 0o777,
            {n: os.getxattr(p, n) for n in os.listxattr(p)},
        )
        for p in root.rglob("*")
        if p.is_file()
    }


def test_apply_fixed_metadata_preserves_owner_permissions_and_original_capture(application):
    args = application
    config = args["config_root"]
    before = snapshot(config)
    capture_before = snapshot(args["capture_directory"])
    result = apply_update_metadata(**args)
    assert result["stage"] == "metadata_applied"
    assert result["runtime_started"] is False and result["maintenance_completed"] is False
    after = snapshot(config)
    assert set(after) == set(before)
    assert {n for n in after if after[n][0] != before[n][0]} == {
        ".container-install.json",
        "compose.env",
        "config/project-binding.json",
    }
    assert all(after[name][1:] == before[name][1:] for name in before)
    assert all(
        snapshot(args["capture_directory"])[name] == value for name, value in capture_before.items()
    )
    assert (args["capture_directory"] / "metadata-pending.json").stat().st_mode & 0o777 == 0o600
    assert json.loads((args["capture_directory"] / "metadata-applied.json").read_bytes()) == result
    with pytest.raises(ContainerInitError, match="already attempted"):
        apply_update_metadata(**args)


def test_existing_atomic_writer_preserves_metadata_on_write_and_rollback(tmp_path, monkeypatch):
    if os.geteuid() != 0:
        pytest.skip("actual stopped-installation ownership preservation requires root")
    first, second = tmp_path / "first", tmp_path / "second"
    for p in (first, second):
        p.write_text("before")
        p.chmod(0o640)
        os.chown(p, 10001, 10002)
        os.setxattr(p, "user.original", b"keep")
    before = snapshot(tmp_path)
    original = Path.replace

    def replace(self, target):
        if target == second and self.name.endswith(".tmp"):
            raise OSError("injected replacement failure")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OSError, match="injected"):
        SetupHandler._atomic_write_many(
            [(first, "new", None), (second, "new", None)], preserve_metadata=True
        )
    assert snapshot(tmp_path) == before
    monkeypatch.setattr(Path, "replace", original)
    SetupHandler._atomic_write_many(
        [(first, "new", None), (second, "new", None)], preserve_metadata=True
    )
    after = snapshot(tmp_path)
    assert all(after[n][0] == b"new" and after[n][1:] == before[n][1:] for n in before)


@pytest.mark.parametrize(
    "failure",
    [
        "capture-digest",
        "archive-bytes",
        "archive-owner",
        "capture-owner",
        "directory-permissions",
        "directory-symlink",
        "source-drift",
        "source-permissions",
        "source-attributes",
        "new-target",
        "already-pending",
        "non-root",
    ],
)
def test_invalid_capture_or_changed_inputs_never_write_active_metadata(
    application, tmp_path, monkeypatch, failure
):
    args = application
    directory = args["capture_directory"]
    if failure == "capture-digest":
        args["capture_sha256"] = "f" * 64
    elif failure == "archive-bytes":
        with (directory / "files.tar").open("ab") as stream:
            stream.write(b"unbound bytes")
    elif failure in {"archive-owner", "capture-owner"}:
        os.chown(
            directory / ("files.tar" if failure == "archive-owner" else "capture.json"),
            10001,
            10001,
        )
    elif failure == "directory-permissions":
        directory.chmod(0o755)
    elif failure == "directory-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        args["capture_directory"] = alias
    elif failure == "source-drift":
        path = args["config_root"] / "config/eval.json"
        path.write_text('{"test_timeout":123}')
    elif failure == "source-permissions":
        (args["config_root"] / "config/project-binding.json").chmod(0o644)
    elif failure == "source-attributes":
        os.setxattr(args["config_root"] / "config/project-binding.json", "user.changed", b"changed")
    elif failure == "new-target":
        args["manifest_sha256"] = "f" * 64
    elif failure == "already-pending":
        (directory / "metadata-pending.json").write_text("pending")
    else:
        monkeypatch.setattr(os, "geteuid", lambda: 10001)
    before = snapshot(args["config_root"])
    with pytest.raises((ValueError, OSError, RuntimeError)):
        apply_update_metadata(**args)
    assert snapshot(args["config_root"]) == before
    assert not (directory / "metadata-applied.json").exists()


@pytest.mark.parametrize("process_loss", [False, True])
def test_mid_write_failure_never_marks_completion_or_discards_recovery_input(
    application, monkeypatch, process_loss
):
    args = application
    before = snapshot(args["config_root"])
    directory = args["capture_directory"]
    original_archive = (directory / "files.tar").read_bytes()
    original = Path.replace

    def replace(self, target):
        if target == args["config_root"] / "config/project-binding.json" and self.name.endswith(
            ".tmp"
        ):
            if process_loss:
                raise SystemExit("injected abrupt exit")
            raise OSError("injected write failure")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises((SystemExit, OSError)):
        apply_update_metadata(**args)
    after = snapshot(args["config_root"])
    if not process_loss:
        assert after == before
    else:
        assert after != before
        assert after[".container-install.json"] == before[".container-install.json"]
    assert (directory / "metadata-pending.json").exists()
    assert not (directory / "metadata-applied.json").exists()
    assert (directory / "files.tar").read_bytes() == original_archive
    with pytest.raises(ContainerInitError, match="explicit recovery"):
        apply_update_metadata(**args)


def test_pending_marker_failure_happens_before_any_active_write(application, monkeypatch):
    before = snapshot(application["config_root"])

    def fail_link(*args, **kwargs):
        raise OSError("injected durable marker failure")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="injected"):
        apply_update_metadata(**application)
    assert snapshot(application["config_root"]) == before
    assert not (application["capture_directory"] / "metadata-applied.json").exists()


def test_metadata_preservation_cannot_enable_bind_mount_fallback(tmp_path):
    with pytest.raises(ValueError, match="ordinary files"):
        SetupHandler._atomic_write_many(
            [], preserve_metadata=True, bind_mount_fallback_paths=frozenset({tmp_path / "target"})
        )


def test_source_change_after_pending_marker_is_not_overwritten(application, monkeypatch):
    original = os.link
    changed = application["config_root"] / "config/eval.json"

    def link(source, target, **kwargs):
        original(source, target, **kwargs)
        changed.write_bytes(b'{"external_change":"preserve"}')

    monkeypatch.setattr(os, "link", link)
    before = snapshot(application["config_root"])
    with pytest.raises(ContainerInitError, match="changed before writing"):
        apply_update_metadata(**application)
    after = snapshot(application["config_root"])
    assert {n for n in after if after[n] != before[n]} == {"config/eval.json"}
    assert changed.read_bytes() == b'{"external_change":"preserve"}'
    assert not (application["capture_directory"] / "metadata-applied.json").exists()


@pytest.mark.parametrize("failure", ["file-sync", "completion-sync"])
def test_late_sync_failure_leaves_pending_without_false_completion(
    application, monkeypatch, failure
):
    original = os.fsync

    def fsync(descriptor):
        path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        if (
            failure == "file-sync"
            and path == application["config_root"] / ".container-install.json"
        ):
            raise OSError("injected file sync failure")
        if (
            failure == "completion-sync"
            and path == application["capture_directory"]
            and (path / "metadata-applied.json").exists()
        ):
            raise OSError("injected completion sync failure")
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(OSError, match="injected"):
        apply_update_metadata(**application)
    assert (application["capture_directory"] / "metadata-pending.json").exists()
    assert not (application["capture_directory"] / "metadata-applied.json").exists()
    assert (
        json.loads((application["config_root"] / ".container-install.json").read_bytes())["version"]
        == "2.0.0a35"
    )


def test_attribute_staging_failure_preserves_all_active_bytes(application, monkeypatch):
    before = snapshot(application["config_root"])
    original = os.setxattr

    def setxattr(path, name, value, **kwargs):
        if ".samuel-setup-" in str(path):
            raise OSError("injected attribute preservation failure")
        return original(path, name, value, **kwargs)

    monkeypatch.setattr(os, "setxattr", setxattr)
    with pytest.raises(OSError, match="injected"):
        apply_update_metadata(**application)
    assert snapshot(application["config_root"]) == before
    assert not (application["capture_directory"] / "metadata-applied.json").exists()


@pytest.mark.parametrize("application", ["registered"], indirect=True)
def test_registered_toolchain_application_preserves_other_evaluation_values(application):
    config = application["config_root"]
    before = snapshot(config)
    old_eval = json.loads((config / "config/eval.json").read_bytes())
    result = apply_update_metadata(**application)
    new_eval = json.loads((config / "config/eval.json").read_bytes())
    assert {k: v for k, v in new_eval.items() if k != "verifier_toolchain"} == {
        k: v for k, v in old_eval.items() if k != "verifier_toolchain"
    }
    assert new_eval["verifier_toolchain"] != old_eval["verifier_toolchain"]
    after = snapshot(config)
    assert all(after[name][1:] == before[name][1:] for name in before)
    assert result["runtime_started"] is False


def test_incomplete_archive_cannot_be_used_even_with_a_matching_new_archive_hash(application):
    directory = application["capture_directory"]
    archive = directory / "files.tar"
    replacement = directory / "replacement.tar"
    with (
        tarfile.open(archive, "r:") as old,
        tarfile.open(replacement, "w", format=tarfile.PAX_FORMAT) as new,
    ):
        for member in old.getmembers():
            if member.name != "state/managed-backup.sqlite3":
                new.addfile(member, old.extractfile(member) if member.isfile() else None)
    replacement.chmod(0o600)
    replacement.replace(archive)
    receipt = directory / "capture.json"
    data = json.loads(receipt.read_bytes())
    data.update(
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        archive_size=archive.stat().st_size,
    )
    receipt.write_text(json.dumps(data))
    application["capture_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    before = snapshot(application["config_root"])
    with pytest.raises(ContainerInitError, match="required bound artifact"):
        apply_update_metadata(**application)
    assert snapshot(application["config_root"]) == before
