from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.slices.privacy.retention import create_managed_backup
from tests.test_container_init import ROOT, _inputs, _published_kit
from tests.test_retention import _policy
from tools.container_init import ContainerInitError, capture_update_files, initialize


@pytest.fixture
def capture(tmp_path: Path):
    if os.geteuid() != 0:
        pytest.skip("file capture requires actual operator ownership")
    published = tmp_path / "published"
    published.mkdir()
    manifest, archive = _published_kit(published)
    manifest_path = published / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    inputs = _inputs(tmp_path)
    inputs.update(
        manifest=manifest,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        owner=(10001, 10001),
        host_log_root="/var/log/samuel",
        host_backup_root="/srv/samuel/backups",
        log_root=tmp_path / "logs",
    )
    inputs["log_root"].mkdir()
    initialize(**inputs)
    store = SQLiteStateStore(inputs["data_root"])
    backup = create_managed_backup(
        policy=_policy(tmp_path), diagnostics=store, state=store.retention
    )
    (tmp_path / "private-backups").mkdir(mode=0o700)
    return dict(
        config_root=inputs["config_root"],
        data_root=inputs["data_root"],
        log_root=inputs["log_root"],
        work_root=inputs["work_root"],
        host_root="/",
        manifest_path=manifest_path,
        installer_archive=archive,
        installer_source=ROOT,
        state_backup=backup.path,
        state_backup_sha256=backup.digest.removeprefix("sha256:"),
        destination=tmp_path / "private-backups/attempt",
    )


def contents(args):
    return {
        p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
        for key in ("config_root", "data_root", "log_root", "work_root")
        for p in args[key].rglob("*")
        if p.is_file() and not p.is_symlink()
    }


def archived_bytes(bundle: tarfile.TarFile, name: str) -> bytes:
    stream = bundle.extractfile(name)
    assert stream is not None
    return stream.read()


def test_capture_preserves_configuration_evidence_and_real_managed_sqlite_backup(capture, tmp_path):
    args = capture
    (args["log_root"] / "audit.jsonl").write_bytes(b"historical signed evidence\n")
    (args["work_root"] / "pending-change").write_bytes(b"candidate bytes")
    before = contents(args)
    result = capture_update_files(**args)
    assert contents(args) == before
    dest = args["destination"]
    assert json.loads((dest / "capture.json").read_bytes()) == result
    assert result["restoration_performed"] is False
    assert result["stage"] == "files_captured"
    assert result["source_version"] == "2.0.0a27"
    assert result["archive_sha256"] == hashlib.sha256((dest / "files.tar").read_bytes()).hexdigest()
    for path, mode in ((dest, 0o700), (dest / "files.tar", 0o600), (dest / "capture.json", 0o600)):
        info = path.stat()
        assert (info.st_uid, info.st_gid, info.st_mode & 0o777) == (0, 0, mode)
    with tarfile.open(dest / "files.tar") as bundle:
        assert len(bundle.getmembers()) == result["members"]
        for path, name in (
            (args["config_root"] / ".env", "configuration/.env"),
            (args["log_root"] / "audit.jsonl", "logs/audit.jsonl"),
            (args["work_root"] / "pending-change", "workspaces/pending-change"),
            (args["manifest_path"], "installation/manifest.json"),
            (args["installer_archive"], "installation/installer.tar.gz"),
            (args["state_backup"], "state/managed-backup.sqlite3"),
        ):
            assert archived_bytes(bundle, name) == path.read_bytes()
        assert "runtime_files/samuel-state.sqlite3" not in bundle.getnames()
        assert "runtime_files/.samuel-state-authority.lock" not in bundle.getnames()
        # Read a separate copy, never a live DB or a tar extraction into host paths.
        db = tmp_path / "verified-backup.sqlite3"
        db.write_bytes(archived_bytes(bundle, "state/managed-backup.sqlite3"))
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_links_metadata_toolchain_and_empty_directories_are_captured_as_data(capture, tmp_path):
    work = capture["work_root"]
    original = work / "a"
    original.write_bytes(b"preserved")
    original.chmod(0o640)
    os.chown(original, 10001, 10002)
    os.setxattr(original, "user.fixture", b"binary\x00value")
    os.utime(original, ns=(1234567890123456789, 1234567890123456789))
    os.link(original, work / "b")
    (work / "empty").mkdir(mode=0o750)
    secret = tmp_path / "outside"
    secret.mkdir()
    (secret / "not-captured").write_bytes(b"outside secret")
    (work / "directory-link").symlink_to(secret, target_is_directory=True)
    (work / "file-link").symlink_to(secret / "not-captured")
    (work / "dangling").symlink_to("absent")
    capture["toolchain_root"] = tmp_path / "toolchain"
    capture["toolchain_root"].mkdir()
    (capture["toolchain_root"] / "receipt").write_bytes(b"existing verifier binding")
    capture_update_files(**capture)
    with tarfile.open(capture["destination"] / "files.tar") as bundle:
        a = bundle.getmember("workspaces/a")
        assert (a.uid, a.gid, a.mode) == (10001, 10002, 0o640)
        assert a.pax_headers["mtime"] == "1234567890.123456789"
        attributes = json.loads(a.pax_headers["SAMUEL.xattrs.base64"])
        assert base64.b64decode(attributes["user.fixture"]) == b"binary\x00value"
        b = bundle.getmember("workspaces/b")
        assert b.islnk() and b.linkname == "workspaces/a"
        assert bundle.getmember("workspaces/empty").isdir()
        for name in ("directory-link", "file-link", "dangling"):
            assert bundle.getmember("workspaces/" + name).issym()
        assert not any("not-captured" in name for name in bundle.getnames())
        assert archived_bytes(bundle, "verifier_toolchain/receipt") == b"existing verifier binding"


@pytest.mark.parametrize(
    "failure",
    [
        "digest",
        "manifest",
        "archive",
        "parent",
        "inside",
        "link-root",
        "live-db",
        "hardlink-live-db",
    ],
)
def test_invalid_capture_inputs_never_complete_or_modify_source(capture, tmp_path, failure):
    if failure == "digest":
        capture["state_backup_sha256"] = "f" * 64
    elif failure == "manifest":
        capture["manifest_path"].write_text("{}")
    elif failure == "archive":
        capture["installer_archive"].write_bytes(b"altered")
    elif failure == "parent":
        capture["destination"].parent.chmod(0o755)
    elif failure == "inside":
        capture["destination"] = capture["work_root"] / "backup"
    elif failure == "link-root":
        link = tmp_path / "linked-work"
        link.symlink_to(capture["work_root"], target_is_directory=True)
        capture["work_root"] = link
    elif failure == "live-db":
        capture["state_backup"] = capture["data_root"] / "samuel-state.sqlite3"
    else:
        link = tmp_path / "disguised-backup"
        os.link(capture["data_root"] / "samuel-state.sqlite3", link)
        capture["state_backup"] = link
    before = contents(capture)
    with pytest.raises((ContainerInitError, OSError)):
        capture_update_files(**capture)
    assert not (capture["destination"] / "capture.json").exists()
    assert contents(capture) == before


def test_special_files_fail_without_blocking_and_attempt_is_not_reused(capture):
    os.mkfifo(capture["work_root"] / "fifo")
    with pytest.raises(ContainerInitError, match="special files"):
        capture_update_files(**capture)
    dest = capture["destination"]
    assert (dest / "files.tar").exists() and not (dest / "capture.json").exists()
    prior = (dest / "files.tar").read_bytes()
    (capture["work_root"] / "fifo").unlink()
    with pytest.raises(FileExistsError):
        capture_update_files(**capture)
    assert (dest / "files.tar").read_bytes() == prior


@pytest.mark.parametrize("failure", ["write", "fsync", "walk", "source-drift", "archive-drift"])
def test_interrupted_or_changing_capture_has_no_completion_receipt(capture, monkeypatch, failure):
    if failure == "write":
        original = tarfile.TarFile.addfile

        def write(bundle, member, stream=None):
            if member.name.startswith("configuration/"):
                raise OSError("disk full")
            return original(bundle, member, stream)

        monkeypatch.setattr(tarfile.TarFile, "addfile", write)
    elif failure == "fsync":

        def fail(_):
            raise OSError("sync failed")

        monkeypatch.setattr(os, "fsync", fail)
    elif failure == "walk":

        def walk(*args, **kwargs):
            kwargs["onerror"](OSError("directory unavailable"))
            return iter(())

        monkeypatch.setattr(os, "fwalk", walk)
    elif failure == "archive-drift":
        import tools.container_init as module

        original_delivery = module.verify_delivery

        def verify(*args):
            original_delivery(*args)
            capture["installer_archive"].write_bytes(b"changed after verification")

        monkeypatch.setattr(module, "verify_delivery", verify)
    else:
        original = tarfile.TarFile.addfile

        def drift(bundle, member, stream=None):
            result = original(bundle, member, stream)
            if member.name == "configuration/.env":
                path = capture["config_root"] / ".env"
                path.write_bytes(path.read_bytes() + b"\nchanged")
            return result

        monkeypatch.setattr(tarfile.TarFile, "addfile", drift)
    with pytest.raises((OSError, ContainerInitError)):
        capture_update_files(**capture)
    assert not (capture["destination"] / "capture.json").exists()


def test_capture_has_no_nonroot_execution_path(capture, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 10001)
    with pytest.raises(ContainerInitError, match="root ownership"):
        capture_update_files(**capture)
    assert not capture["destination"].exists()


@pytest.mark.parametrize("failure_at", [2, 3, 4])
def test_late_sync_failure_never_leaves_completed_capture(capture, monkeypatch, failure_at):
    original = os.fsync
    count = 0

    def sync(descriptor):
        nonlocal count
        count += 1
        if count == failure_at:
            raise OSError("late persistence failure")
        return original(descriptor)

    monkeypatch.setattr(os, "fsync", sync)
    with pytest.raises(OSError, match="late persistence"):
        capture_update_files(**capture)
    assert not (capture["destination"] / "capture.json").exists()
    assert (capture["destination"] / "files.tar").exists()


def test_runtime_root_swap_cannot_silently_skip_captured_files(capture, monkeypatch):
    original = os.open
    root = capture["work_root"]
    moved = root.with_name("displaced-workspaces")

    def replaced(path, flags, *args, **kwargs):
        if path == root:
            root.rename(moved)
            root.symlink_to(moved, target_is_directory=True)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replaced)
    with pytest.raises(OSError):
        capture_update_files(**capture)
    assert not (capture["destination"] / "capture.json").exists()


def test_existing_complete_capture_is_never_overwritten(capture):
    capture_update_files(**capture)
    dest = capture["destination"]
    before = {p: p.read_bytes() for p in dest.iterdir()}
    with pytest.raises(FileExistsError):
        capture_update_files(**capture)
    assert {p: p.read_bytes() for p in dest.iterdir()} == before
