from __future__ import annotations

import subprocess
import sys


def test_version_flag_prints_version():
    result = subprocess.run(
        [sys.executable, "-m", "samuel", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("samuel ")


def test_short_version_flag_prints_version():
    result = subprocess.run(
        [sys.executable, "-m", "samuel", "-V"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("samuel ")
