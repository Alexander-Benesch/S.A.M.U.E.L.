from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.test_update_bindings import toolchain_update as toolchain_update
from tests.test_update_metadata import metadata as metadata
from tests.test_update_metadata import registered_metadata as registered_metadata
from tests.test_update_metadata_application import application as application
from tests.test_update_metadata_application import snapshot
from tests.test_update_metadata_recovery import interrupt
from tests.test_verifier_toolchain import toolchain as toolchain
from tools.container_init import ContainerInitError, apply_update_metadata, restore_update_metadata


@pytest.mark.parametrize("application", [None, "registered"], indirect=True)
def test_restore_source_metadata_preserves_capture_owners_and_unmodified_files(application):
    before = snapshot(application["config_root"])
    archive = (application["capture_directory"] / "files.tar").read_bytes()
    apply_update_metadata(**application)
    result = restore_update_metadata(**application)
    assert result["stage"] == "source_metadata_restored"
    assert not result["state_restored"] and not result["maintenance_completed"]
    assert snapshot(application["config_root"]) == before
    assert (application["capture_directory"] / "files.tar").read_bytes() == archive
    assert restore_update_metadata(**application) == result


def test_interrupted_target_application_can_restore_original_metadata(application, monkeypatch):
    before = snapshot(application["config_root"])
    interrupt(application, monkeypatch)
    restore_update_metadata(**application)
    assert snapshot(application["config_root"]) == before


def test_interrupted_restoration_keeps_bound_marker_and_can_retry(application, monkeypatch):
    before = snapshot(application["config_root"])
    apply_update_metadata(**application)
    original_replace = Path.replace

    def replace(self, target):
        if target == application["config_root"] / "config/project-binding.json":
            raise SystemExit("restore interruption")
        return original_replace(self, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", replace)
        with pytest.raises(SystemExit, match="restore interruption"):
            restore_update_metadata(**application)
    assert (application["capture_directory"] / "restore-pending.json").exists()
    restore_update_metadata(**application)
    assert snapshot(application["config_root"]) == before


@pytest.mark.parametrize("fault", ["archive", "foreign-marker", "unrelated-active-bytes"])
def test_restore_rejects_unknown_inputs_without_active_mutation(application, fault):
    apply_update_metadata(**application)
    if fault == "archive":
        with (application["capture_directory"] / "files.tar").open("ab") as stream:
            stream.write(b"tampered")
    elif fault == "foreign-marker":
        (application["capture_directory"] / "restore-pending.json").write_text("{}")
        (application["capture_directory"] / "restore-pending.json").chmod(0o600)
    else:
        (application["config_root"] / "compose.env").write_bytes(b"unrelated changes")
    before = snapshot(application["config_root"])
    with pytest.raises(ContainerInitError):
        restore_update_metadata(**application)
    assert snapshot(application["config_root"]) == before


def test_restore_marker_binds_original_installation_not_only_target(application):
    original = (application["config_root"] / ".container-install.json").read_bytes()
    apply_update_metadata(**application)
    restore_update_metadata(**application)
    marker = json.loads((application["capture_directory"] / "restore-pending.json").read_bytes())
    assert marker["source_installation_sha256"] == hashlib.sha256(original).hexdigest()
    assert marker["capture_sha256"] == application["capture_sha256"]


def test_restore_accepts_metadata_already_accepted_by_update_without_new_size_limit(
    metadata, request
):
    environment = metadata["config_root"] / "compose.env"
    original = environment.read_bytes() + b"\n#" + b"x" * (4 * 1024 * 1024) + b"\n"
    environment.write_bytes(original)
    application = request.getfixturevalue("application")
    apply_update_metadata(**application)
    restore_update_metadata(**application)
    assert environment.read_bytes() == original
