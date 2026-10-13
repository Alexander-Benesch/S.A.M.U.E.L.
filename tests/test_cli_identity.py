from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _console_script() -> Path:
    script = Path(sys.prefix) / "bin" / "samuel"
    assert script.is_file()
    return script


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    (config / "agent.json").write_text(json.dumps({"data_dir": "runtime"}), encoding="utf-8")
    (config / "auth.json").write_text(
        (ROOT / "config" / "auth.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return config


def _run(config: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_console_script()), "--config", str(config), "identity", *arguments, "--json"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_identity_cli_bootstraps_and_cuts_over_without_exposing_password(tmp_path: Path) -> None:
    config = _config(tmp_path)
    password = "correct horse battery staple"
    password_file = tmp_path / "admin-password"
    password_file.write_text(password + "\n", encoding="utf-8")
    password_file.chmod(0o600)

    bootstrap = _run(
        config,
        "bootstrap",
        "--username",
        "admin",
        "--password-file",
        str(password_file),
    )
    assert bootstrap.returncode == 0
    assert password not in bootstrap.stdout + bootstrap.stderr
    payload = json.loads(bootstrap.stdout)["identity"]
    assert payload["status"] == "active"
    assert payload["roles"] == ["administrator"]

    connection = sqlite3.connect(tmp_path / "runtime" / "samuel-state.sqlite3")
    stored_hash = connection.execute(
        "SELECT password_hash FROM identity_principals WHERE username = 'admin'"
    ).fetchone()[0]
    connection.close()
    assert stored_hash.startswith("$argon2")
    assert password not in stored_hash

    cutover = _run(
        config,
        "cutover",
        "--client-inventory-confirmed",
        "--reason",
        "all dashboard clients inventoried",
    )
    assert cutover.returncode == 0
    assert json.loads(cutover.stdout)["identity"] == {
        "access_mode": "local_identity",
        "changed": True,
        "status": "active",
    }
    assert json.loads((config / "auth.json").read_text())["access_mode"] == "local_identity"

    repeated = _run(
        config,
        "cutover",
        "--client-inventory-confirmed",
        "--reason",
        "idempotency verification",
    )
    assert repeated.returncode == 0
    assert json.loads(repeated.stdout)["identity"]["changed"] is False


def test_identity_cli_rejects_unsafe_password_file_and_unready_cutover(tmp_path: Path) -> None:
    config = _config(tmp_path)
    password_file = tmp_path / "admin-password"
    password_file.write_text("long-enough-password\n", encoding="utf-8")
    password_file.chmod(0o644)

    rejected = _run(
        config,
        "bootstrap",
        "--username",
        "admin",
        "--password-file",
        str(password_file),
    )
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["error"]["code"] == "identity_command_invalid"

    password_file.chmod(0o600)
    symlink = tmp_path / "linked-password"
    symlink.symlink_to(password_file)
    linked = _run(
        config,
        "bootstrap",
        "--username",
        "admin",
        "--password-file",
        str(symlink),
    )
    assert linked.returncode == 1
    assert json.loads(linked.stdout)["error"]["code"] == "identity_command_invalid"

    cutover = _run(config, "cutover", "--reason", "inventory is not confirmed")
    assert cutover.returncode == 1
    assert json.loads(cutover.stdout)["error"]["code"] == "identity_command_invalid"
    assert json.loads((config / "auth.json").read_text())["access_mode"] == "legacy_api_key"
