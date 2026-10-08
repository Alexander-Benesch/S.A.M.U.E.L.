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
