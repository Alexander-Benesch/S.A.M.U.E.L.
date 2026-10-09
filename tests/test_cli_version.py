from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from importlib.metadata import version
from pathlib import Path

from samuel import __build_info__
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.cli import _cmd_doctor


def _console_script() -> Path:
    script = Path(sys.prefix) / "bin" / "samuel"
    assert script.is_file(), "installed console entry point is required by the test environment"
    return script


def test_version_flag_prints_version():
    result = subprocess.run(
        [str(_console_script()), "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"samuel {version('samuel')}"


def test_short_version_flag_prints_version():
    result = subprocess.run(
        [str(_console_script()), "-V"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == f"samuel {version('samuel')}"


def test_doctor_reports_product_version_and_separate_build_revision(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for name in ("SCM_URL", "SCM_TOKEN", "SCM_REPO", "SCM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "samuel.slices.setup.env_io.build_doctor_report", lambda *_args, **_kwargs: []
    )

    assert _cmd_doctor(Namespace(config=str(tmp_path))) == 0
    output = capsys.readouterr().out
    assert f"Produktversion                      {__build_info__.product_version}" in output
    assert "Build-Revision" in output
    if __build_info__.revision:
        assert __build_info__.revision in output


def test_doctor_persists_bounded_qualification_in_existing_state(tmp_path, monkeypatch, capsys):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "runtime"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text(
        json.dumps({"data_dir": str(data_dir)}),
        encoding="utf-8",
    )
    state = SQLiteStateStore(data_dir)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "samuel.slices.setup.env_io.build_doctor_report",
        lambda *_args, **_kwargs: [
            {"status": "ok", "name": "state", "detail": "ready"},
            {"status": "warn", "name": "provider", "detail": "not probed"},
        ],
    )

    assert _cmd_doctor(Namespace(config=str(config_dir))) == 0

    projection = state.projections.get_projection("health-readiness:doctor")
    assert projection is not None
    assert projection.status == "passed"
    assert projection.payload["instance_uuid"] == state.status().authority_instance
    assert projection.payload["summary"]["warnings"] == 1
    capsys.readouterr()
