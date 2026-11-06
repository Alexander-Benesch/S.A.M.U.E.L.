from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


def _console_script() -> Path:
    script = Path(sys.prefix) / "bin" / "samuel"
    assert script.is_file(), "installed console entry point is required by the test environment"
    return script


def test_installed_console_script_ignores_colliding_package_in_working_directory(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "foreign-package-imported"
    foreign_package = tmp_path / "samuel"
    foreign_package.mkdir()
    foreign_package.joinpath("__init__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n",
        encoding="utf-8",
    )
    foreign_package.joinpath("cli.py").write_text(
        "def main():\n    raise SystemExit('foreign CLI executed')\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(_console_script()), "--version"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"samuel {version('samuel')}"
    assert not marker.exists()
