from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.test_update_bindings import toolchain_update as toolchain_update
from tests.test_update_metadata import metadata as metadata
from tests.test_update_metadata import registered_metadata as registered_metadata
from tests.test_update_metadata_application import application as application
from tests.test_update_metadata_application import snapshot
from tests.test_verifier_toolchain import toolchain as toolchain
from tools.container_init import apply_update_metadata


def interrupt(args, monkeypatch, *, late=False):
    if late:
        original_sync = os.fsync

        def fsync(descriptor):
            if Path(os.readlink(f"/proc/self/fd/{descriptor}")) == args["config_root"]:
                raise OSError("interrupted directory sync")
            return original_sync(descriptor)

        with monkeypatch.context() as patch:
            patch.setattr(os, "fsync", fsync)
            with pytest.raises(OSError, match="interrupted"):
                apply_update_metadata(**args)
    else:
        original = Path.replace

        def replace(self, target):
            if target == args["config_root"] / "config/project-binding.json" and self.name.endswith(
                ".tmp"
            ):
                raise SystemExit("interrupted process")
            return original(self, target)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "replace", replace)
            with pytest.raises(SystemExit, match="interrupted"):
                apply_update_metadata(**args)
    assert (args["capture_directory"] / "metadata-pending.json").exists()
    assert not (args["capture_directory"] / "metadata-applied.json").exists()


def test_explicit_resume_finishes_only_the_previously_bound_target(application, monkeypatch):
    config = application["config_root"]
    original = snapshot(config)
    archive = (application["capture_directory"] / "files.tar").read_bytes()
    interrupt(application, monkeypatch)
    result = apply_update_metadata(**application, resume=True)
    assert result["stage"] == "metadata_applied"
    assert not result["runtime_started"] and not result["maintenance_completed"]
    assert json.loads((config / ".container-install.json").read_bytes())["version"] == "2.0.0a35"
    assert all(snapshot(config)[n][1:] == original[n][1:] for n in original)
    assert (application["capture_directory"] / "files.tar").read_bytes() == archive
    assert (config / ".env").read_bytes() == original[".env"][0]


def test_late_resume_syncs_existing_target_and_parents_without_rewriting(application, monkeypatch):
    interrupt(application, monkeypatch, late=True)
    config = application["config_root"]
    before = {
        str(p): (p.stat().st_ino, p.stat().st_mtime_ns) for p in config.rglob("*") if p.is_file()
    }
    synced = set()
    original = os.fsync

    def fsync(descriptor):
        synced.add(Path(os.readlink(f"/proc/self/fd/{descriptor}")))
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    result = apply_update_metadata(**application, resume=True)
    after = {
        str(p): (p.stat().st_ino, p.stat().st_mtime_ns) for p in config.rglob("*") if p.is_file()
    }
    assert after == before
    assert {config, config / "config", config / "compose"} <= synced
    assert result["stage"] == "metadata_applied"


def test_existing_valid_metadata_completion_is_not_a_new_activation(application):
    first = apply_update_metadata(**application)
    before = snapshot(application["config_root"])
    markers = snapshot(application["capture_directory"])
    second = apply_update_metadata(**application, resume=True)
    assert second == first
    assert snapshot(application["config_root"]) == before
    assert snapshot(application["capture_directory"]) == markers


@pytest.mark.parametrize(
    "failure",
    [
        "missing-pending",
        "pending-owner",
        "pending-symlink",
        "pending-target",
        "different-target",
        "environment-drift",
        "third-file-bytes",
        "changed-owner",
        "target-artifact",
        "archive-bytes",
        "foreign-completion",
    ],
)
def test_resume_never_accepts_unknown_changes_or_a_different_operation(
    application, monkeypatch, tmp_path, failure
):
    args = application
    interrupt(args, monkeypatch)
    pending = args["capture_directory"] / "metadata-pending.json"
    if failure == "missing-pending":
        pending.unlink()
    elif failure == "pending-owner":
        os.chown(pending, 10001, 10001)
    elif failure == "pending-symlink":
        elsewhere = tmp_path / "elsewhere"
        pending.rename(elsewhere)
        pending.symlink_to(elsewhere)
    elif failure == "pending-target":
        data = json.loads(pending.read_bytes())
        data["target_manifest_sha256"] = "f" * 64
        pending.write_text(json.dumps(data))
    elif failure == "different-target":
        path = args["manifest_path"]
        data = json.loads(path.read_bytes())
        data["commit"] = "f" * 40
        path.write_text(json.dumps(data))
        args["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif failure == "environment-drift":
        with (args["config_root"] / ".env").open("ab") as output:
            output.write(b"CHANGED_SECRET=keep-external-value\n")
    elif failure == "third-file-bytes":
        (args["config_root"] / "compose.env").write_bytes(b"unexpected third content")
    elif failure == "changed-owner":
        os.chown(args["config_root"] / "config/project-binding.json", 10002, 10002)
    elif failure == "target-artifact":
        args["installer_archive"].write_bytes(b"changed target archive")
    elif failure == "archive-bytes":
        with (args["capture_directory"] / "files.tar").open("ab") as output:
            output.write(b"changed source archive")
    else:
        (args["capture_directory"] / "metadata-applied.json").write_text('{"other":"operation"}')
    before = snapshot(args["config_root"])
    with pytest.raises((ValueError, OSError, RuntimeError)):
        apply_update_metadata(**args, resume=True)
    assert snapshot(args["config_root"]) == before


@pytest.mark.parametrize("application", ["registered"], indirect=True)
def test_resume_uses_archived_old_registration_after_target_registration_was_written(
    application, monkeypatch
):
    interrupt(application, monkeypatch, late=True)
    source_registration = json.loads(
        (application["config_root"] / ".verifier-toolchain.json").read_bytes()
    )
    result = apply_update_metadata(**application, resume=True)
    assert result["stage"] == "metadata_applied"
    assert (
        json.loads((application["config_root"] / ".verifier-toolchain.json").read_bytes())
        == source_registration
    )
    assert result["maintenance_completed"] is False


def test_operator_preservation_keeps_full_unix_mode_on_write_and_rollback(tmp_path, monkeypatch):
    from samuel.slices.setup.handler import SetupHandler

    if os.geteuid() != 0:
        pytest.skip("actual operator metadata preservation requires root")
    first, second = tmp_path / "first", tmp_path / "second"
    for path in (first, second):
        path.write_text("old")
        os.chown(path, 10001, 10002)
        path.chmod(0o2640)
    original = Path.replace

    def replace(self, target):
        if target == second and self.name.endswith(".tmp"):
            raise OSError("injected replacement failure")
        return original(self, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", replace)
        with pytest.raises(OSError, match="injected"):
            SetupHandler._atomic_write_many(
                [(first, "new", None), (second, "new", None)], preserve_metadata=True
            )
    assert all(
        path.read_text() == "old" and path.stat().st_mode & 0o7777 == 0o2640
        for path in (first, second)
    )
    SetupHandler._atomic_write_many(
        [(first, "new", None), (second, "new", None)], preserve_metadata=True
    )
    assert all(
        path.read_text() == "new" and path.stat().st_mode & 0o7777 == 0o2640
        for path in (first, second)
    )


def test_preparation_rechecks_operator_environment_without_overwriting_external_changes(
    metadata, monkeypatch
):
    import tools.container_init as module

    original = module.verify_runtime
    path = metadata["config_root"] / ".env"

    def runtime(manifest):
        with path.open("ab") as output:
            output.write(b"EXTERNAL_ENV_CHANGE=preserve\n")
        return original(manifest)

    monkeypatch.setattr(module, "verify_runtime", runtime)
    with pytest.raises(module.ContainerInitError, match="metadata changed"):
        module.prepare_update_metadata(**metadata)
    assert path.read_bytes().endswith(b"EXTERNAL_ENV_CHANGE=preserve\n")


@pytest.mark.parametrize("interrupted", [False, True])
def test_metadata_preflight_uses_same_validation_without_any_active_or_marker_write(
    application, monkeypatch, interrupted
):
    if interrupted:
        interrupt(application, monkeypatch)
    config_before = snapshot(application["config_root"])
    capture_before = snapshot(application["capture_directory"])
    result = apply_update_metadata(**application, resume=interrupted, verify_only=True)
    assert result["stage"] == "metadata_verified"
    assert result["runtime_started"] is False
    assert result["maintenance_completed"] is False
    assert snapshot(application["config_root"]) == config_before
    assert snapshot(application["capture_directory"]) == capture_before


def test_metadata_preflight_does_not_accept_foreign_pending_operation(application, monkeypatch):
    interrupt(application, monkeypatch)
    pending = application["capture_directory"] / "metadata-pending.json"
    data = json.loads(pending.read_bytes())
    data["target_manifest_sha256"] = "f" * 64
    pending.write_text(json.dumps(data))
    before = snapshot(application["config_root"])
    with pytest.raises(RuntimeError, match="exact target"):
        apply_update_metadata(**application, resume=True, verify_only=True)
    assert snapshot(application["config_root"]) == before
