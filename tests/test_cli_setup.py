from __future__ import annotations

import argparse
import json

import pytest

from samuel import cli


def test_retired_interactive_setup_is_nonmutating_and_points_to_dashboard(
    tmp_path, monkeypatch, capsys
) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("retired wizard must not prompt, probe or initialize configuration")

    monkeypatch.setattr("builtins.input", forbidden)
    monkeypatch.setattr(cli, "_scm_probe", forbidden)
    assert cli._cmd_setup(argparse.Namespace(config=str(tmp_path / "config"))) == 2
    assert not list(tmp_path.iterdir())
    output = capsys.readouterr().out
    assert "Dashboard" in output and "--non-interactive" in output


def test_installed_initializer_without_scm_is_repeatable_and_keeps_secrets_private(tmp_path):
    import os
    import shutil
    import subprocess
    from pathlib import Path

    from samuel.slices.setup.env_io import parse_env
    from tests.test_cli_state import _console_script

    config = tmp_path / "config"
    shutil.copytree(Path(__file__).parents[1] / "config", config)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SCM_", "SAMUEL_"))
        and key not in {"PROJECT_ROOT", "SLICE_HMAC_KEY", "TZ", "DASHBOARD_PORT"}
    }
    command = [str(_console_script()), "--config", str(config), "setup"]
    retired = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=20
    )
    assert retired.returncode == 2 and not (tmp_path / ".env").exists()
    original = None
    for _ in range(2):
        result = subprocess.run(
            [*command, "--non-interactive"],
            cwd=tmp_path,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        saved = (tmp_path / ".env").read_bytes()
        values = parse_env(saved.decode())
        for key in ("SAMUEL_API_KEY", "SLICE_HMAC_KEY", "SAMUEL_AUDIT_HMAC_KEY"):
            assert values[key] and values[key] not in result.stdout + result.stderr
        assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
        assert "--configuration-mode setup" in result.stdout
        assert "--configuration-mode production" in result.stdout
        assert not values.get("SCM_TOKEN") and not values.get("SCM_REPO")
        if original is not None:
            assert saved == original
        original = saved


def test_noninteractive_setup_never_echoes_existing_dashboard_credential(
    tmp_path, monkeypatch, capsys
) -> None:
    secret = "setup-output-must-not-contain-this-value"
    (tmp_path / ".env").write_text(
        "SCM_PROVIDER=gitea\n"
        "SCM_URL=http://example.invalid\n"
        "SCM_USER=bot\n"
        "SCM_TOKEN=token\n"
        "SCM_REPO=owner/repo\n"
        f"SAMUEL_API_KEY={secret}\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_scm_probe", lambda *_args: {"ok": True, "detail": "ok"})
    monkeypatch.setattr(cli, "_cmd_doctor", lambda _args: 0)
    assert (
        cli._cmd_setup(argparse.Namespace(config=str(tmp_path / "config"), non_interactive=True))
        == 0
    )
    output = capsys.readouterr().out
    assert secret not in output
    assert "Dashboard/REST-Auth: konfiguriert" in output
    assert "--configuration-mode setup" in output
    assert "--configuration-mode production" in output
    assert "samuel watch" not in output


def _isolated_setup(tmp_path, monkeypatch):
    from samuel.slices.setup.handler import SetupHandler

    monkeypatch.setenv("SCM_PROVIDER", "github")
    monkeypatch.setenv("SCM_URL", "https://api.github.com")
    monkeypatch.setenv("SCM_REPO", "example/project")
    monkeypatch.setenv("SCM_USER", "synthetic-bot")
    monkeypatch.setenv("SCM_TOKEN", "synthetic-scm-credential")
    monkeypatch.setenv("SAMUEL_API_KEY", "synthetic-dashboard-credential")
    monkeypatch.setattr(cli, "_scm_probe", lambda *_args: {"ok": True, "detail": "mock probe"})
    monkeypatch.setattr(cli, "_cmd_doctor", lambda _args: 0)
    monkeypatch.setattr(SetupHandler, "ensure_directories", lambda self: [])
    return argparse.Namespace(config=str(tmp_path / "config"), non_interactive=True)


@pytest.mark.parametrize("explicit_timezone", [None, "Asia/Tokyo"])
def test_repeated_setup_preserves_dashboard_timezone_unless_explicitly_overridden(
    tmp_path, monkeypatch, explicit_timezone
):
    args = _isolated_setup(tmp_path, monkeypatch)
    monkeypatch.delenv("TZ", raising=False)
    if explicit_timezone:
        monkeypatch.setenv("TZ", explicit_timezone)
    monkeypatch.setattr(cli, "_detect_timezone", lambda: "UTC")
    config = tmp_path / "config"
    config.mkdir()
    agent = config / "agent.json"
    agent.write_text(json.dumps({"timezone": "Europe/Berlin", "max_parallel": 1}))
    for _ in range(2):
        assert cli._cmd_setup(args) == 0
        assert json.loads(agent.read_text()) == {
            "timezone": explicit_timezone or "Europe/Berlin",
            "max_parallel": 1,
        }


@pytest.mark.parametrize("content", ["{broken", "[]", '{"timezone": 12}'])
def test_setup_does_not_replace_unreadable_existing_agent_config(tmp_path, monkeypatch, content):
    args = _isolated_setup(tmp_path, monkeypatch)
    config = tmp_path / "config"
    config.mkdir()
    agent = config / "agent.json"
    agent.write_text(content)
    assert cli._cmd_setup(args) == 1
    assert agent.read_text() == content
    assert not (tmp_path / ".env").exists()


def test_setup_rejects_symlink_without_touching_external_env(tmp_path, monkeypatch, capsys):
    outside = tmp_path / "outside"
    outside.write_text("PRIVATE=synthetic-secret\n")
    (tmp_path / ".env").symlink_to(outside)
    result = cli._cmd_setup(_isolated_setup(tmp_path, monkeypatch))
    assert result == 1
    assert outside.read_text() == "PRIVATE=synthetic-secret\n"
    assert "synthetic-secret" not in capsys.readouterr().out


def test_setup_permission_failure_is_reported_without_success_or_partial_env(
    tmp_path, monkeypatch, capsys
):
    import os

    args = _isolated_setup(tmp_path, monkeypatch)

    def deny_permissions(*args, **kwargs):
        raise PermissionError("synthetic permission failure")

    monkeypatch.setattr(os, "fchmod", deny_permissions)
    assert cli._cmd_setup(args) == 1
    assert not (tmp_path / ".env").exists()
    assert not list(tmp_path.glob(".env.samuel-setup-*"))
    output = capsys.readouterr().out
    assert ".env geschrieben" not in output
    assert "synthetic-dashboard-credential" not in output


def test_cli_setup_secret_bytes_are_private_before_first_write(tmp_path, monkeypatch):
    import os
    import stat
    from pathlib import Path

    args = _isolated_setup(tmp_path, monkeypatch)
    original_fdopen = os.fdopen
    original_write_text = Path.write_text
    modes = []

    class ObservedFile:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *exc):
            return self.stream.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, content):
            modes.append(stat.S_IMODE(os.fstat(self.stream.fileno()).st_mode))
            return self.stream.write(content)

    def observe_fdopen(*args, **kwargs):
        return ObservedFile(original_fdopen(*args, **kwargs))

    def observe_legacy_write(path, *args, **kwargs):
        result = original_write_text(path, *args, **kwargs)
        if path.name == ".env":
            modes.append(stat.S_IMODE(path.stat().st_mode))
        return result

    monkeypatch.setattr(os, "fdopen", observe_fdopen)
    monkeypatch.setattr(Path, "write_text", observe_legacy_write)
    previous_umask = os.umask(0o022)
    try:
        assert cli._cmd_setup(args) == 0
    finally:
        os.umask(previous_umask)
    assert modes and set(modes) == {0o600}
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
