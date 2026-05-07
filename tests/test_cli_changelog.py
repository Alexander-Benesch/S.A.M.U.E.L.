"""CLI integration for `samuel changelog` (#163)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from samuel.cli import _cmd_changelog, _build_parser


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def tmp_repo_with_config(tmp_path: Path) -> Path:
    """Repo where ``project_root = config.parent`` resolves to the repo dir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").mkdir()
    _run_git(["init", "-q"], repo)
    _run_git(["config", "user.email", "t@e.com"], repo)
    _run_git(["config", "user.name", "T"], repo)
    _run_git(["config", "commit.gpgsign", "false"], repo)
    (repo / "f").write_text("x")
    _run_git(["add", "f"], repo)
    _run_git(["commit", "-q", "-m", "initial"], repo)
    return repo


def _commit_and_optionally_tag(repo: Path, subject: str, tag: str = "") -> None:
    f = repo / "f"
    f.write_text(f.read_text() + ".")
    _run_git(["add", "f"], repo)
    _run_git(["commit", "-q", "-m", subject], repo)
    if tag:
        _run_git(["tag", tag], repo)


class TestChangelogHelp:
    def test_subcommand_listed_in_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "samuel", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "changelog" in result.stdout

    def test_subcommand_help_lists_options(self) -> None:
        parser = _build_parser()
        # --help on subparser raises SystemExit(0) after printing
        with pytest.raises(SystemExit):
            parser.parse_args(["changelog", "--help"])


class TestCmdChangelog:
    def test_uses_phase_tag_when_phase_arg_given(
        self, tmp_repo_with_config: Path,
    ) -> None:
        repo = tmp_repo_with_config
        _commit_and_optionally_tag(repo, "feat: pre-tag (#1)", tag="phase-1-complete")
        _commit_and_optionally_tag(repo, "feat: after-tag (#2)")

        bus = MagicMock()
        bus.send.return_value = {
            "generated": True, "changelog": "# Changelog", "entry_count": 1,
        }
        args = MagicMock(
            config=str(repo / "config"),
            phase=1, since=None, post_to_issue=None, out=None,
        )

        rc = _cmd_changelog(bus, args)

        assert rc == 0
        sent_cmd = bus.send.call_args.args[0]
        assert sent_cmd.payload["entries"] == [
            {"issue": "2", "title": "after-tag", "category": "feature"},
        ]

    def test_falls_back_to_latest_tag_when_no_args(
        self, tmp_repo_with_config: Path,
    ) -> None:
        repo = tmp_repo_with_config
        _commit_and_optionally_tag(repo, "feat: pre (#1)", tag="v1")
        _commit_and_optionally_tag(repo, "fix: post (#2)")

        bus = MagicMock()
        bus.send.return_value = {
            "generated": True, "changelog": "# Changelog", "entry_count": 1,
        }
        args = MagicMock(
            config=str(repo / "config"),
            phase=None, since=None, post_to_issue=None, out=None,
        )

        rc = _cmd_changelog(bus, args)

        assert rc == 0
        sent = bus.send.call_args.args[0]
        assert sent.payload["entries"][0]["issue"] == "2"

    def test_no_tag_no_since_returns_error(
        self, tmp_repo_with_config: Path, capsys,
    ) -> None:
        repo = tmp_repo_with_config  # no tags
        bus = MagicMock()
        args = MagicMock(
            config=str(repo / "config"),
            phase=None, since=None, post_to_issue=None, out=None,
        )

        rc = _cmd_changelog(bus, args)

        assert rc == 1
        bus.send.assert_not_called()
        assert "Kein Git-Tag" in capsys.readouterr().err

    def test_no_entries_returns_error(
        self, tmp_repo_with_config: Path, capsys,
    ) -> None:
        repo = tmp_repo_with_config
        _run_git(["tag", "v1"], repo)
        # no commits after tag
        bus = MagicMock()
        args = MagicMock(
            config=str(repo / "config"),
            phase=None, since="v1", post_to_issue=None, out=None,
        )

        rc = _cmd_changelog(bus, args)

        assert rc == 1
        bus.send.assert_not_called()
        assert "Keine Changelog-Eintraege" in capsys.readouterr().err

    def test_writes_to_out_file(
        self, tmp_repo_with_config: Path, tmp_path: Path,
    ) -> None:
        repo = tmp_repo_with_config
        _run_git(["tag", "v1"], repo)
        _commit_and_optionally_tag(repo, "feat: x (#9)")

        out_file = tmp_path / "CHANGELOG.md"
        bus = MagicMock()
        bus.send.return_value = {
            "generated": True,
            "changelog": "# Changelog\n- feat #9",
            "entry_count": 1,
        }
        args = MagicMock(
            config=str(repo / "config"),
            phase=None, since="v1", post_to_issue=None, out=str(out_file),
        )

        rc = _cmd_changelog(bus, args)

        assert rc == 0
        assert out_file.read_text() == "# Changelog\n- feat #9"

    def test_post_to_issue_propagates_to_payload(
        self, tmp_repo_with_config: Path,
    ) -> None:
        repo = tmp_repo_with_config
        _run_git(["tag", "v1"], repo)
        _commit_and_optionally_tag(repo, "feat: x (#9)")

        bus = MagicMock()
        bus.send.return_value = {
            "generated": True, "changelog": "x", "entry_count": 1,
        }
        args = MagicMock(
            config=str(repo / "config"),
            phase=None, since="v1", post_to_issue=42, out=None,
        )

        rc = _cmd_changelog(bus, args)

        assert rc == 0
        sent = bus.send.call_args.args[0]
        assert sent.payload["post_to_issue"] == 42
