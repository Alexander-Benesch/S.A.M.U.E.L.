from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from samuel.release_trust import ReleaseTrustError
from tests.test_installed_update_preparation import installed_update as installed_update
from tests.test_update_installer import update_kit as update_kit
from tools.container_init import ContainerInitError, prepare_update_command


@pytest.fixture
def command_preparation(installed_update, tmp_path):
    report = tmp_path / "state.json"
    report.write_text(
        json.dumps(
            {
                "action": "status",
                "ok": True,
                "state": {
                    "healthy": True,
                    "path": "/app/data/samuel-state.sqlite3",
                    "schema_version": 10,
                    "configuration": {"phase": "idle", "maintenance": {}},
                    "authority": {
                        "instance": "1" * 32,
                        "epoch": 1,
                        "witness_epoch": 1,
                        "reconcile_required": False,
                        "active_restore_operation": None,
                        "restore_sentinel_present": False,
                    },
                },
            }
        )
    )
    report.chmod(0o600)
    args = {
        k: v
        for k, v in installed_update.items()
        if k not in {"source_state_schema", "target_state_schema"}
    }
    return {**args, "state_report": report}


def test_private_preparation_keeps_original_receipt_and_bounded_relative_inputs(
    command_preparation,
):
    args = command_preparation
    result = prepare_update_command(**args)
    assert len(result) == 9
    document = args["cache"] / result[7]
    raw = document.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result[8]
    assert document.stat().st_mode & 0o777 == 0o600
    assert document.parent.stat().st_mode & 0o777 == 0o700
    value = json.loads(raw)
    assert (
        value["original_receipt"].encode()
        == (args["config_root"] / ".container-install.json").read_bytes()
    )
    assert value["source_state_schema"] == 10
    assert value["installation_performed"] is False
    assert value["operator_approval"] == "required"
    assert prepare_update_command(**args) == result


def test_update_preparation_preserves_actual_restored_state_identity(command_preparation, tmp_path):
    from samuel.adapters.state.sqlite import SQLiteStateStore
    from samuel.core.state import ReconcileEntryRecord

    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(f"36 25 0:32 / {tmp_path} rw,relatime - ext4 device rw\n")
    store = SQLiteStateStore(tmp_path / "live", mountinfo_path=mountinfo)
    original = store.status().authority_instance
    operation = store.restore(store.backup(tmp_path / "backup.sqlite3"))
    restored = store.status().authority_instance
    assert restored != original and len(restored) == 36
    args = command_preparation

    def observe():
        value = store.status().as_dict()
        # The real container reports its mount path, not the test host's path.
        value["path"] = "/app/data/samuel-state.sqlite3"
        value["configuration"] = {"phase": "idle", "maintenance": {}}
        args["state_report"].write_text(
            json.dumps({"action": "status", "ok": True, "state": value})
        )

    observe()
    with pytest.raises(ContainerInitError, match="observation"):
        prepare_update_command(**args)
    assert not args["fetcher"].calls
    store.authority.replace_reconcile_scan(
        operation.operation_id,
        [
            ReconcileEntryRecord(
                operation.operation_id,
                "inventory",
                "complete",
                "verified_effect",
                "inventory_completed",
            )
        ],
    )
    store.authority.complete_reconcile(operation.operation_id)
    observe()
    result = prepare_update_command(**args)
    value = json.loads((args["cache"] / result[7]).read_bytes())
    assert value["observed_state"]["authority"]["instance"] == restored
    assert store.status().authority_instance == restored
    assert value["operator_approval"] == "required"
    assert value["installation_performed"] is False


@pytest.mark.parametrize("instance", [None, "", 123, "g" * 32, "1" * 31, "1-" * 18])
def test_invalid_state_instance_never_prepares_update(command_preparation, instance):
    args = command_preparation
    value = json.loads(args["state_report"].read_bytes())
    value["state"]["authority"]["instance"] = instance
    args["state_report"].write_text(json.dumps(value))
    with pytest.raises(ContainerInitError, match="observation"):
        prepare_update_command(**args)
    assert not args["fetcher"].calls
    assert not args["cache"].exists()


@pytest.mark.parametrize("epoch", [True, -1, "1", 1.0])
def test_invalid_matching_state_and_witness_epoch_never_prepares_update(command_preparation, epoch):
    args = command_preparation
    value = json.loads(args["state_report"].read_bytes())
    value["state"]["authority"].update(epoch=epoch, witness_epoch=epoch)
    args["state_report"].write_text(json.dumps(value))
    with pytest.raises(ContainerInitError, match="observation"):
        prepare_update_command(**args)
    assert not args["fetcher"].calls


def test_restored_instance_format_is_not_normalized_during_recovery(command_preparation):
    from tools.container_init import prepare_update_recovery

    args = command_preparation
    value = json.loads(args["state_report"].read_bytes())
    instance = "07418fcd-b99e-410b-adbf-ca946fe96dca"
    value["state"]["authority"]["instance"] = instance
    args["state_report"].write_text(json.dumps(value))
    result = prepare_update_command(**args)
    pending_report(args, result[8])
    value = json.loads(args["state_report"].read_bytes())
    value["state"]["authority"]["instance"] = instance.replace("-", "")
    args["state_report"].write_text(json.dumps(value))
    calls = list(args["fetcher"].calls)
    with pytest.raises(ContainerInitError, match="identity or authority"):
        prepare_update_recovery(
            **{k: v for k, v in args.items() if k != "target_version"}, preparation_sha256=result[8]
        )
    assert args["fetcher"].calls == calls


@pytest.mark.parametrize(
    "fault",
    [
        "not_object",
        "failed",
        "other_action",
        "path",
        "schema",
        "reconcile",
        "restore",
        "sentinel",
        "permissions",
    ],
)
def test_unusable_operator_observation_cannot_prepare_host_inputs(command_preparation, fault):
    args = command_preparation
    path = args["state_report"]
    value = json.loads(path.read_bytes())
    if fault == "not_object":
        value = []
    elif fault == "failed":
        value["ok"] = False
    elif fault == "other_action":
        value["action"] = "dump"
    elif fault == "path":
        value["state"]["path"] = "/another-installation/state.sqlite3"
    elif fault == "schema":
        value["state"]["schema_version"] = "10"
    elif fault == "reconcile":
        value["state"]["authority"]["reconcile_required"] = True
    elif fault == "restore":
        value["state"]["authority"]["active_restore_operation"] = "pending"
    elif fault == "sentinel":
        value["state"]["authority"]["restore_sentinel_present"] = True
    else:
        path.chmod(0o644)
    path.write_text(json.dumps(value))
    with pytest.raises((ContainerInitError, ReleaseTrustError)):
        prepare_update_command(**args)
    assert not args["fetcher"].calls
    assert not args["cache"].exists()


def test_changed_preparation_file_is_not_overwritten(command_preparation):
    args = command_preparation
    result = prepare_update_command(**args)
    document = args["cache"] / result[7]
    document.write_text("changed")
    with pytest.raises(ContainerInitError, match="no replacement"):
        prepare_update_command(**args)
    assert document.read_text() == "changed"


def test_internal_continuation_rechecks_the_installed_source_and_both_kits(command_preparation):
    from tools.container_init import read_update_preparation

    args = command_preparation
    result = prepare_update_command(**args)
    checked = read_update_preparation(
        args["cache"] / result[7],
        result[8],
        config_root=args["config_root"],
        host_root=args["host_root"],
        cache=args["cache"],
        manifest_sha256=result[1],
        image=result[4],
    )
    assert checked["source_installation"]["receipt"]["version"] == "2.0.0a34"
    assert checked["target_version"] == "2.0.0a35"


@pytest.mark.parametrize(
    "fault",
    [
        "digest",
        "source_receipt",
        "source_kit",
        "target_kit",
        "host_root",
        "target_image",
        "path",
        "version",
    ],
)
def test_internal_continuation_rejects_drift_and_arbitrary_inputs(command_preparation, fault):
    from tools.container_init import read_update_preparation

    args = command_preparation
    result = prepare_update_command(**args)
    path = args["cache"] / result[7]
    digest, host_root, image = result[8], args["host_root"], result[4]
    value = json.loads(path.read_bytes())
    if fault == "digest":
        digest = "f" * 64
    elif fault == "source_receipt":
        receipt = args["config_root"] / ".container-install.json"
        content = json.loads(receipt.read_bytes())
        content["port"] += 1
        receipt.write_text(json.dumps(content))
    elif fault in {"source_kit", "target_kit"}:
        kit = value["source_installer" if fault == "source_kit" else "installer"]
        (args["cache"] / kit["directory"] / "tools/samuel-container").write_text("changed")
    elif fault == "host_root":
        host_root = "/another-host"
    elif fault == "target_image":
        image = "fixture/other@sha256:" + "f" * 64
    else:
        if fault == "path":
            value["installer"]["archive"] = "../../untrusted.tar.gz"
        else:
            value["target_version"] = "2.0.0a36"
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ContainerInitError):
        read_update_preparation(
            path,
            digest,
            config_root=args["config_root"],
            host_root=host_root,
            cache=args["cache"],
            manifest_sha256=result[1],
            image=image,
        )


@pytest.mark.parametrize(
    "configuration",
    [
        None,
        {},
        {"phase": "editing"},
        {"phase": "maintenance"},
        {"phase": "idle", "maintenance": {"binding": "foreign"}},
    ],
)
def test_normal_update_cannot_skip_open_configuration_or_maintenance(
    command_preparation, configuration
):
    args = command_preparation
    report = args["state_report"]
    value = json.loads(report.read_bytes())
    value["state"]["configuration"] = configuration
    report.write_text(json.dumps(value))
    with pytest.raises(ContainerInitError, match="explicit recovery"):
        prepare_update_command(**args)
    assert not args["fetcher"].calls


def test_existing_preparation_still_syncs_directory_after_lost_ack(
    command_preparation, monkeypatch
):
    import os
    from pathlib import Path

    args = command_preparation
    first = prepare_update_command(**args)
    original = os.fsync
    synced = set()

    def sync(descriptor):
        synced.add(Path(os.readlink(f"/proc/self/fd/{descriptor}")))
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", sync)
    assert prepare_update_command(**args) == first
    assert {args["cache"], args["cache"] / "update-preparations"} <= synced


def pending_report(args, digest):
    path = args["state_report"]
    value = json.loads(path.read_bytes())
    value["state"]["configuration"] = {
        "phase": "maintenance",
        "maintenance": {"binding": digest, "target": "production", "step": "pending"},
    }
    path.write_text(json.dumps(value))


def test_explicit_recovery_rechecks_signed_source_target_and_keeps_original_binding(
    command_preparation,
):
    from tools.container_init import prepare_update_recovery

    args = command_preparation
    result = prepare_update_command(**args)
    original = (args["cache"] / result[7]).read_bytes()
    pending_report(args, result[8])
    recovery = {k: v for k, v in args.items() if k != "target_version"}
    before_calls = len(args["fetcher"].calls)
    assert prepare_update_recovery(**recovery, preparation_sha256=result[8]) == result
    assert len(args["fetcher"].calls) > before_calls
    assert (args["cache"] / result[7]).read_bytes() == original


@pytest.mark.parametrize("fault", ["completed", "foreign", "setup", "closed_step", "schema"])
def test_recovery_never_opens_a_new_transition_from_a_saved_preparation(command_preparation, fault):
    from tools.container_init import prepare_update_recovery

    args = command_preparation
    result = prepare_update_command(**args)
    pending_report(args, result[8])
    path = args["state_report"]
    value = json.loads(path.read_bytes())
    configuration = value["state"]["configuration"]
    if fault == "completed":
        configuration["phase"] = "idle"
    elif fault == "foreign":
        configuration["maintenance"]["binding"] = "f" * 64
    elif fault == "setup":
        configuration["maintenance"]["target"] = "setup"
    elif fault == "closed_step":
        configuration["maintenance"]["step"] = "production"
    else:
        value["state"]["schema_version"] += 1
    path.write_text(json.dumps(value))
    before = list(args["fetcher"].calls)
    recovery = {k: v for k, v in args.items() if k != "target_version"}
    with pytest.raises(ContainerInitError):
        prepare_update_recovery(**recovery, preparation_sha256=result[8])
    assert args["fetcher"].calls == before


@pytest.fixture
def update_steps(command_preparation, tmp_path, monkeypatch):
    from samuel.adapters.state.sqlite import SQLiteStateStore
    from samuel.slices.privacy.retention import create_managed_backup
    from tests.test_retention import _policy

    args = command_preparation
    store = SQLiteStateStore(tmp_path / "state")
    status = store.status()
    observation = json.loads(args["state_report"].read_bytes())
    observation["state"]["authority"].update(
        instance=status.authority_instance,
        epoch=status.authority_epoch,
        witness_epoch=status.witness_epoch,
    )
    args["state_report"].write_text(json.dumps(observation))
    prepared = prepare_update_command(**args)
    backup = create_managed_backup(
        policy=_policy(tmp_path), diagnostics=store, state=store.retention
    )
    report = tmp_path / "backup-response.json"
    report.write_text(
        json.dumps(
            {
                "path": "/app/data/backups/" + backup.path.name,
                "digest": backup.digest,
                "instance_uuid": backup.instance_uuid,
                "authority_epoch": backup.authority_epoch,
            }
        )
    )
    report.chmod(0o600)
    logs = tmp_path / "logs"
    logs.mkdir()
    import os

    os.chown(logs, 10001, 10001)
    os.chown(backup.path.parent, 10001, 10001)
    monkeypatch.setattr("tools.container_init.verify_runtime", lambda _: (10001, 10001))
    return dict(
        preparation=args["cache"] / prepared[7],
        preparation_sha256=prepared[8],
        config_root=args["config_root"],
        data_root=tmp_path / "state",
        log_root=logs,
        work_root=tmp_path / "workspaces",
        backup_root=backup.path.parent,
        host_root=args["host_root"],
        cache=args["cache"],
        manifest_path=args["cache"] / prepared[0],
        manifest_sha256=prepared[1],
        image=prepared[4],
        installer_archive=args["cache"] / prepared[2],
        installer_source=args["cache"] / prepared[3],
        backup_receipt=report,
    )


def test_fixed_steps_use_existing_capture_then_verify_and_apply_without_releasing_maintenance(
    update_steps,
):
    from tests.test_update_metadata_application import snapshot
    from tools.container_init import perform_update_step

    args = update_steps
    before = snapshot(args["config_root"])
    result = perform_update_step(**args, step="capture")
    assert result["reused"] is False
    assert snapshot(args["config_root"]) == before
    for step in ("toolchain", "verify"):
        assert perform_update_step(**args, step=step)["stage"] == "metadata_verified"
        assert snapshot(args["config_root"]) == before
    result = perform_update_step(**args, step="apply")
    assert result["stage"] == "metadata_applied"
    assert not result["runtime_started"] and not result["maintenance_completed"]
    assert (
        json.loads((args["config_root"] / ".container-install.json").read_bytes())["version"]
        == "2.0.0a35"
    )
    source = json.loads((args["config_root"] / ".release-source.json").read_bytes())
    assert source["initial_handoff"] == "not_qualified_by_this_check"
    assert (args["config_root"] / ".env").read_bytes() == before[".env"][0]
    again = perform_update_step(**args, step="apply", recovery=True)
    assert again == result


@pytest.mark.parametrize(
    "path",
    [
        "/etc/shadow",
        "/app/data/backups/../../state.sqlite3",
        "/app/data/backups//other",
        "/app/data/backups/./other",
    ],
)
def test_backup_output_cannot_select_arbitrary_operator_files(update_steps, path):
    from tools.container_init import perform_update_step

    args = update_steps
    report = args["backup_receipt"]
    value = json.loads(report.read_bytes())
    value["path"] = path
    report.write_text(json.dumps(value))
    with pytest.raises(ContainerInitError, match="backup mount"):
        perform_update_step(**args, step="capture")
    assert not (args["cache"] / "update-captures").exists()


@pytest.mark.parametrize("fault", ["instance", "epoch"])
def test_recovery_rejects_replaced_state_before_release_fetch(command_preparation, fault):
    from tools.container_init import prepare_update_recovery

    args = command_preparation
    result = prepare_update_command(**args)
    pending_report(args, result[8])
    value = json.loads(args["state_report"].read_bytes())
    if fault == "instance":
        value["state"]["authority"]["instance"] = "2" * 32
    else:
        value["state"]["authority"].update(epoch=0, witness_epoch=0)
    args["state_report"].write_text(json.dumps(value))
    calls = list(args["fetcher"].calls)
    with pytest.raises(ContainerInitError, match="identity or authority"):
        prepare_update_recovery(
            **{k: v for k, v in args.items() if k != "target_version"}, preparation_sha256=result[8]
        )
    assert args["fetcher"].calls == calls


def test_backup_from_other_state_is_not_captured_as_this_installation(update_steps):
    from tools.container_init import perform_update_step

    args = update_steps
    backup = json.loads(args["backup_receipt"].read_bytes())
    backup["instance_uuid"] = "f" * 32
    args["backup_receipt"].write_text(json.dumps(backup))
    with pytest.raises(ContainerInitError, match="different state identity"):
        perform_update_step(**args, step="capture")
    assert not (args["cache"] / "update-captures").exists()


@pytest.mark.parametrize("point", ["before_source_link", "after_private_source"])
def test_source_adoption_failure_leaves_only_absent_or_complete_source_and_can_resume(
    update_steps, monkeypatch, point
):
    import os
    from pathlib import Path

    from tools.container_init import perform_update_step

    args = update_steps
    perform_update_step(**args, step="capture")
    private = args["config_root"] / ".release-source.json"
    runtime = args["config_root"] / "config/release-source.json"
    original_link, original_sync = os.link, os.fsync

    def link(source, target, *extra, **kw):
        if point == "before_source_link" and target == private:
            raise OSError("lost source placement")
        return original_link(source, target, *extra, **kw)

    def sync(descriptor):
        if (
            point == "after_private_source"
            and Path(os.readlink(f"/proc/self/fd/{descriptor}")) == private
        ):
            raise OSError("lost source sync")
        return original_sync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", link)
        patch.setattr(os, "fsync", sync)
        with pytest.raises(OSError, match="lost source"):
            perform_update_step(**args, step="apply")
    if private.exists():
        assert json.loads(private.read_bytes())["schema"] == "release-source.v1"
    assert not runtime.exists()
    result = perform_update_step(**args, step="apply", recovery=True)
    assert result["stage"] == "metadata_applied"
    assert private.read_bytes() == runtime.read_bytes()
    assert not result["maintenance_completed"]


def test_private_capture_selection_cannot_redirect_recovery(update_steps):
    from tools.container_init import perform_update_step

    args = update_steps
    perform_update_step(**args, step="capture")
    selection = args["cache"] / "update-captures" / args["preparation_sha256"] / "selected.json"
    value = json.loads(selection.read_bytes())
    value["attempt"] = "../../elsewhere"
    selection.write_text(json.dumps(value))
    with pytest.raises(ContainerInitError, match="selection"):
        perform_update_step(**args, step="verify", recovery=True)


def test_restore_step_returns_source_metadata_and_keeps_state_for_existing_restore_cli(
    update_steps,
):
    from tests.test_update_metadata_application import snapshot
    from tools.container_init import perform_update_step

    args = update_steps
    original = snapshot(args["config_root"])
    perform_update_step(**args, step="capture")
    perform_update_step(**args, step="apply")
    state_before = snapshot(args["data_root"])
    result = perform_update_step(**args, step="restore", recovery=True)
    assert result["stage"] == "source_metadata_restored" and not result["state_restored"]
    assert snapshot(args["data_root"]) == state_before
    restored = snapshot(args["config_root"])
    assert all(restored[name] == value for name, value in original.items())
    assert result["source_version"] == "2.0.0a34"
    assert result["backup_path"] == json.loads(args["backup_receipt"].read_bytes())["path"]
    overlay = args["cache"] / result["restore_compose"]
    assert json.loads(overlay.read_bytes()) == {
        "services": {"samuel": {"healthcheck": {"disable": True}}}
    }
    with pytest.raises(ContainerInitError, match="restoration already started"):
        perform_update_step(**args, step="apply", recovery=True)
    assert perform_update_step(**args, step="restore", recovery=True) == result


@pytest.mark.parametrize("fault", ["backup-bytes", "backup-binding", "no-explicit-recovery"])
def test_restore_rejects_unknown_backup_before_returning_source_files(update_steps, fault):
    from tests.test_update_metadata_application import snapshot
    from tools.container_init import perform_update_step

    args = update_steps
    perform_update_step(**args, step="capture")
    perform_update_step(**args, step="apply")
    if fault == "backup-bytes":
        backup = json.loads(args["backup_receipt"].read_bytes())
        path = args["backup_root"] / Path(backup["path"]).relative_to("/app/data/backups")
        path.write_bytes(b"damaged backup")
    elif fault == "backup-binding":
        backup = json.loads(args["backup_receipt"].read_bytes())
        backup["digest"] = "sha256:" + "f" * 64
        args["backup_receipt"].write_text(json.dumps(backup))
    before = snapshot(args["config_root"])
    with pytest.raises(ContainerInitError):
        perform_update_step(**args, step="restore", recovery=fault != "no-explicit-recovery")
    assert snapshot(args["config_root"]) == before
