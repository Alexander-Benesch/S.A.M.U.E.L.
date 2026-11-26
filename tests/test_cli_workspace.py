from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from samuel.adapters.workspace.git import GitWorktreeManager


def _console_script() -> Path:
    script = Path(sys.prefix) / "bin" / "samuel"
    assert script.is_file()
    return script


def _config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text(
        json.dumps(
            {
                "data_dir": "runtime",
                "workspace": {
                    "work_dir": "workspaces",
                    "reserve_mebibytes": 1,
                    "minimum_free_mebibytes": 0,
                    "quarantine_max_count": 2,
                    "quarantine_max_mebibytes": 4,
                },
            }
        ),
        encoding="utf-8",
    )
    return config_dir


def test_workspace_list_and_prune_are_deterministic_without_bootstrap(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    manager = GitWorktreeManager(
        tmp_path / "workspaces",
        data_dir=tmp_path / "runtime",
        reserve_bytes=1024,
        minimum_free_bytes=0,
        quarantine_max_count=2,
        quarantine_max_bytes=4 * 1024 * 1024,
    )
    assert manager.list_workspaces() == []

    listed = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "workspace",
            "list",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    pruned = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "workspace",
            "prune",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert listed.returncode == pruned.returncode == 0
    assert json.loads(listed.stdout)["workspace"] == []
    assert json.loads(pruned.stdout)["workspace"] == {
        "records_removed": 0,
        "trees_removed": 0,
    }


def test_workspace_inspect_requires_identity(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "workspace",
            "inspect",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "workspace_id_required"


def test_workspace_discard_requires_identity_and_reason(tmp_path: Path) -> None:
    config_dir = _config(tmp_path)
    result = subprocess.run(
        [
            str(_console_script()),
            "--config",
            str(config_dir),
            "workspace",
            "discard",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == ("workspace_discard_arguments_required")
