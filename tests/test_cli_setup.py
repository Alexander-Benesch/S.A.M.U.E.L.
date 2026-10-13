from __future__ import annotations

import argparse

from samuel import cli


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
