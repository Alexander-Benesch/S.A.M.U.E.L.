"""Tests for the --self run main-branch pre-check (#227)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from samuel.cli import _check_self_run_branch


class TestCheckSelfRunBranch:
    def test_allows_main(self, tmp_path: Path):
        with patch("samuel.core.git.current_branch", return_value="main"):
            assert _check_self_run_branch(tmp_path, allow_non_main=False) is True

    def test_blocks_non_main(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        with patch("samuel.core.git.current_branch", return_value="phase/something"):
            assert _check_self_run_branch(tmp_path, allow_non_main=False) is False
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "phase/something" in err
        assert "main" in err

    def test_allow_non_main_overrides_block(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ):
        with patch("samuel.core.git.current_branch", return_value="some-other"):
            assert _check_self_run_branch(tmp_path, allow_non_main=True) is True
        err = capsys.readouterr().err
        assert "WARN" in err
        assert "some-other" in err

    def test_blocks_empty_branch_name(self, tmp_path: Path):
        """Empty branch name (git command failed) must NOT be treated as main —
        treat it as a hard block so we don't proceed with no idea where we are."""
        with patch("samuel.core.git.current_branch", return_value=""):
            assert _check_self_run_branch(tmp_path, allow_non_main=False) is False

    def test_passes_cwd_to_current_branch(self, tmp_path: Path):
        with patch("samuel.core.git.current_branch", return_value="main") as m:
            _check_self_run_branch(tmp_path, allow_non_main=False)
            assert m.call_args.kwargs.get("cwd") == tmp_path
