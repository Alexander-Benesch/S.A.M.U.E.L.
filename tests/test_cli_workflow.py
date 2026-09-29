from __future__ import annotations

import pytest

from samuel.cli import main


def test_cli_reports_missing_workflow_without_traceback(tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / "agent.json").write_text('{"mode":"does-not-exist"}', encoding="utf-8")
    monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)

    with pytest.raises(SystemExit) as stopped:
        main(["--config", str(tmp_path), "health"])

    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert "ERROR: Workflow definition not found:" in error
    assert "Traceback" not in error
