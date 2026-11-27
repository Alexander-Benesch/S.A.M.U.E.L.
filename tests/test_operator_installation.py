from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from samuel.release_trust import ReleaseTrustError
from tests.test_container_init import _inputs
from tools.container_init import ContainerInitError, initialize, read_installation_receipt


@pytest.fixture
def installed(tmp_path: Path):
    if os.geteuid() != 0:
        pytest.skip("actual root-owned operator receipt requires root")
    inputs = _inputs(tmp_path)
    inputs.update(
        owner=(10001, 10001),
        host_log_root="/var/log/samuel",
        host_backup_root="/srv/samuel/backups",
    )
    initialize(**inputs)
    return inputs["config_root"] / ".container-install.json"


def test_existing_receipt_is_read_without_rewriting_or_creating_paths(installed: Path) -> None:
    raw = installed.read_bytes()
    before = installed.stat()
    result = read_installation_receipt(installed, host_root="/")
    assert result == {"receipt": json.loads(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert installed.read_bytes() == raw
    after = installed.stat()
    assert (before.st_mtime_ns, before.st_ctime_ns, before.st_ino) == (
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_ino,
    )
    assert not (installed.parent / "update").exists()


def test_explicit_prefixed_installation_has_same_fixed_path_classes(installed: Path) -> None:
    receipt = json.loads(installed.read_bytes())
    for key in ("config_root", "data_root", "work_root", "log_root", "backup_root"):
        receipt[key] = "/isolated-host" + receipt[key]
    installed.write_text(json.dumps(receipt))
    assert read_installation_receipt(installed, host_root="/isolated-host")["receipt"] == receipt
    with pytest.raises(ContainerInitError, match="different host layout"):
        read_installation_receipt(installed, host_root="/")


@pytest.mark.parametrize(
    "root", ["relative", "//", "/double//path", "/path/../other", "/path/", "/path\nother"]
)
def test_invalid_operator_root_is_rejected_before_receipt_access(tmp_path: Path, root: str) -> None:
    with pytest.raises(ContainerInitError, match="canonical"):
        read_installation_receipt(tmp_path / "missing", host_root=root)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra", "untrusted command"),
        ("config_root", "/another-installation"),
        ("data_root", "/var/lib/samuel/../other"),
        ("work_root", "/"),
        ("log_root", "/tmp/logs"),
        ("backup_root", "/tmp/backups"),
        ("stage", "approved"),
        ("image", "samuel:latest"),
        ("manifest_sha256", "g" * 64),
        ("revision", "short"),
        ("version", "2.0.0a35;command"),
        ("version", None),
        ("port", True),
        ("port", 0),
        ("port", 65536),
        ("uid", 0),
        ("gid", True),
        ("uid", 2**32),
        ("project", "project\nother"),
    ],
)
def test_receipt_cannot_supply_arbitrary_host_instructions(
    installed: Path, field: str, value
) -> None:
    receipt = json.loads(installed.read_bytes())
    receipt[field] = value
    installed.write_text(json.dumps(receipt))
    before = installed.read_bytes()
    with pytest.raises(ContainerInitError):
        read_installation_receipt(installed, host_root="/")
    assert installed.read_bytes() == before


@pytest.mark.parametrize(
    "failure", ["owner", "group", "permissions", "symlink", "fifo", "size", "missing"]
)
def test_operator_receipt_requires_private_regular_root_owned_bytes(
    installed: Path, failure: str
) -> None:
    if failure == "owner":
        os.chown(installed, 10001, 0)
    elif failure == "group":
        os.chown(installed, 0, 10001)
    elif failure == "permissions":
        installed.chmod(0o644)
    elif failure == "symlink":
        original = installed.with_name("original")
        installed.rename(original)
        installed.symlink_to(original)
    elif failure == "fifo":
        installed.unlink()
        os.mkfifo(installed)
    elif failure == "size":
        installed.write_bytes(b" " * 65_537)
    else:
        installed.unlink()
    with pytest.raises((ReleaseTrustError, OSError)):
        read_installation_receipt(installed, host_root="/")


def test_receipt_drift_is_detected_on_the_open_descriptor(
    installed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = os.fstat
    calls = 0

    def change(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            installed.write_bytes(installed.read_bytes() + b" ")
        return original(descriptor)

    monkeypatch.setattr(os, "fstat", change)
    with pytest.raises(ReleaseTrustError, match="changed while reading"):
        read_installation_receipt(installed, host_root="/")
