from __future__ import annotations

import json
import os
import select
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("key_source", ["environment", "dotenv"])
def test_identity_operator_lifecycle_preserves_signed_audit_chain(
    tmp_path, monkeypatch, key_source
):
    from samuel.adapters.audit.jsonl import JSONLAuditSink, verify_chain
    from samuel.adapters.state.sqlite import SQLiteStateStore

    key = "synthetic-identity-audit-key"
    if key_source == "environment":
        monkeypatch.setenv("SAMUEL_AUDIT_HMAC_KEY", key)
    else:
        monkeypatch.delenv("SAMUEL_AUDIT_HMAC_KEY", raising=False)
        (tmp_path / ".env").write_text(f"SAMUEL_AUDIT_HMAC_KEY={key}\n")
    config = _config(tmp_path)
    data = tmp_path / "runtime"
    sink = JSONLAuditSink(data / "logs" / "agent.jsonl", hmac_key=key)
    sink.write({"evt": "existing_runtime_record"})
    password = tmp_path / "password"
    password.write_text("synthetic long administrator password\n")
    password.chmod(0o600)
    for arguments in (
        ("bootstrap", "--username", "admin", "--password-file", str(password)),
        ("cutover", "--client-inventory-confirmed", "--reason", "fixture inventory"),
    ):
        result = _run(config, *arguments)
        assert result.returncode == 0, result.stderr
    store = SQLiteStateStore(data)
    backup = store.backup(tmp_path / "backup.sqlite3")
    store.restore(backup)
    result = _run(
        config,
        "recover",
        "--username",
        "admin",
        "--password-file",
        str(password),
        "--reason",
        "fixture source recovery",
    )
    assert result.returncode == 0, result.stderr
    files = sorted((data / "logs").glob("agent*.jsonl"))
    checks = [verify_chain(path, key) for path in files]
    assert files and all(check["ok"] for check in checks), checks
    records = [json.loads(line) for path in files for line in path.read_text().splitlines()]
    events = {record.get("payload", record).get("evt") for record in records}
    assert {"identity_bootstrapped", "identity_cutover", "identity_recovered"} <= events
    assert password.read_text().strip() not in "".join(path.read_text() for path in files)


def test_identity_cli_does_not_report_success_when_signed_audit_append_is_refused(
    tmp_path, monkeypatch
):
    from samuel.adapters.audit.jsonl import JSONLAuditSink

    monkeypatch.delenv("SAMUEL_AUDIT_HMAC_KEY", raising=False)
    config = _config(tmp_path)
    log_dir = tmp_path / "runtime" / "logs"
    JSONLAuditSink(log_dir / "agent.jsonl", hmac_key="existing-key").write({"evt": "prior"})
    before = {p.name: p.read_bytes() for p in log_dir.glob("agent*.jsonl")}
    password = tmp_path / "password"
    password.write_text("synthetic long administrator password\n")
    password.chmod(0o600)
    result = _run(config, "bootstrap", "--username", "admin", "--password-file", str(password))
    assert result.returncode == 1
    assert not json.loads(result.stdout)["ok"]
    assert "unsigned audit append refused" in json.loads(result.stdout)["error"]["detail"]
    assert {p.name: p.read_bytes() for p in log_dir.glob("agent*.jsonl")} == before
    assert password.read_text().strip() not in result.stdout + result.stderr
    # The local identity mutation is retained for operator diagnosis, not
    # erased or falsely reported as a successful audited bootstrap.
    assert json.loads(_run(config, "status").stdout)["identity"]["status"] == "active"


def test_identity_cli_rejects_symlinked_audit_secret_before_identity_mutation(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("SAMUEL_AUDIT_HMAC_KEY", raising=False)
    config = _config(tmp_path)
    secret = tmp_path / "external-env"
    secret.write_text("SAMUEL_AUDIT_HMAC_KEY=not-for-this-installation\n")
    (tmp_path / ".env").symlink_to(secret)
    password = tmp_path / "password"
    password.write_text("synthetic long administrator password\n")
    password.chmod(0o600)
    result = _run(config, "bootstrap", "--username", "admin", "--password-file", str(password))
    assert result.returncode == 1
    assert "not-for-this-installation" not in result.stdout + result.stderr
    status = _run(config, "status")
    assert status.returncode == 0
    assert json.loads(status.stdout)["identity"]["status"] == "uninitialized"
    assert json.loads((config / "auth.json").read_text())["access_mode"] == "legacy_api_key"


def _terminal_run(
    command: list[str], answers: list[tuple[bytes, bytes]], *, env: dict[str, str] | None = None
) -> tuple[int, str]:
    import errno
    import pty

    master, slave = pty.openpty()
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(slave)
    output = bytearray()
    next_answer = 0
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    data = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    break
                if not data:
                    break
                output.extend(data)
                if next_answer < len(answers):
                    marker, answer = answers[next_answer]
                    if marker in output:
                        os.write(master, answer)
                        next_answer += 1
            elif process.poll() is not None:
                break
        else:
            pytest.fail("interactive command timed out")
        assert next_answer == len(answers), "interactive command did not reach expected prompts"
        return process.wait(timeout=5), output.decode(errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)


@pytest.mark.parametrize("confirmation", ["interactive-admin-password", "different-password"])
def test_identity_password_prompt_is_hidden_and_confirmation_binds_bootstrap(
    tmp_path: Path, confirmation: str
) -> None:
    config = _config(tmp_path)
    password = "interactive-admin-password"
    code, output = _terminal_run(
        [
            str(_console_script()),
            "--config",
            str(config),
            "identity",
            "bootstrap",
            "--username",
            "admin",
            "--prompt-password",
        ],
        [
            (b"Administrator password: ", password.encode() + b"\n"),
            (b"Confirm administrator password: ", confirmation.encode() + b"\n"),
        ],
    )
    assert password not in output and confirmation not in output
    status = json.loads(_run(config, "status").stdout)["identity"]
    if confirmation == password:
        assert code == 0
        assert status["principals"][0]["roles"] == ["administrator"]
        with sqlite3.connect(tmp_path / "runtime/samuel-state.sqlite3") as connection:
            stored_hash = connection.execute(
                "SELECT password_hash FROM identity_principals"
            ).fetchone()[0]
        from argon2 import PasswordHasher

        assert PasswordHasher().verify(stored_hash, password)
    else:
        assert code == 1
        assert "confirmation does not match" in output
        assert status["principals"] == []
    assert json.loads((config / "auth.json").read_text())["access_mode"] == "legacy_api_key"
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert password.encode() not in path.read_bytes()


def test_identity_password_prompt_refuses_pipe_and_conflicting_sources(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = _run(config, "bootstrap", "--username", "admin", "--prompt-password")
    assert result.returncode == 1
    assert "interactive terminal" in result.stdout
    conflict = _run(config, "bootstrap", "--prompt-password", "--password-file", "/unused")
    assert conflict.returncode == 2
    invalid_action = _run(config, "recover", "--prompt-password")
    assert invalid_action.returncode == 1
    assert "only supported for identity bootstrap" in invalid_action.stdout
    assert json.loads(_run(config, "status").stdout)["identity"]["principals"] == []


def test_identity_password_prompt_cancellation_creates_no_administrator(tmp_path: Path) -> None:
    config = _config(tmp_path)
    code, output = _terminal_run(
        [
            str(_console_script()),
            "--config",
            str(config),
            "identity",
            "bootstrap",
            "--username",
            "admin",
            "--prompt-password",
        ],
        [(b"Administrator password: ", b"\x04")],
    )
    assert code == 1
    assert "password entry cancelled" in output
    assert "Traceback" not in output
    assert json.loads(_run(config, "status").stdout)["identity"]["principals"] == []


def test_interactive_bootstrap_never_resets_an_existing_administrator(tmp_path: Path) -> None:
    config = _config(tmp_path)
    password_file = tmp_path / "existing-password"
    password_file.write_text("existing-administrator-password")
    password_file.chmod(0o600)
    assert (
        _run(
            config, "bootstrap", "--username", "admin", "--password-file", str(password_file)
        ).returncode
        == 0
    )
    database = tmp_path / "runtime/samuel-state.sqlite3"
    with sqlite3.connect(database) as connection:
        before = connection.execute(
            "SELECT principal_id, password_hash FROM identity_principals"
        ).fetchall()
    replacement = b"must-not-replace-existing-password\n"
    code, output = _terminal_run(
        [
            str(_console_script()),
            "--config",
            str(config),
            "identity",
            "bootstrap",
            "--username",
            "admin",
            "--prompt-password",
        ],
        [
            (b"Administrator password: ", replacement),
            (b"Confirm administrator password: ", replacement),
        ],
    )
    assert code == 1
    assert replacement.strip().decode() not in output
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT principal_id, password_hash FROM identity_principals"
            ).fetchall()
            == before
        )


def test_identity_password_prompt_never_falls_back_to_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    import getpass
    import warnings

    from samuel.cli import _read_identity_password

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    def insecure_fallback(prompt: str) -> str:
        warnings.warn("Cannot control echo", getpass.GetPassWarning, stacklevel=2)
        pytest.fail("must stop before reading an echoed password")

    monkeypatch.setattr(getpass, "getpass", insecure_fallback)
    with pytest.raises(ValueError, match="secure terminal unavailable"):
        _read_identity_password("", prompt=True)
