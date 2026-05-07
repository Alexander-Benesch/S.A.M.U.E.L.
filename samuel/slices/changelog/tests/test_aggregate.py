"""Tests for changelog/aggregate.py (#163)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from samuel.slices.changelog.aggregate import (
    aggregate_from_git,
    latest_tag,
    phase_tag,
)


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Initialize a fresh git repo with a deterministic commit chain."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)
    _run(["git", "config", "commit.gpgsign", "false"], repo)
    return repo


def _commit(repo: Path, subject: str, content: str = "x") -> None:
    f = repo / "file.txt"
    f.write_text(f.read_text() + content if f.exists() else content)
    _run(["git", "add", "file.txt"], repo)
    _run(["git", "commit", "-q", "-m", subject], repo)


class TestAggregateFromGit:
    def test_parses_conventional_commits_with_issue_ref(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat(planner): add skeleton example (#338)")
        _commit(tmp_repo, "fix(audit): drop trailing newline (#100)")

        entries = aggregate_from_git(tmp_repo)

        assert len(entries) == 2
        # newest first
        assert entries[0] == {
            "issue": "100",
            "title": "drop trailing newline",
            "category": "fix",
        }
        assert entries[1] == {
            "issue": "338",
            "title": "add skeleton example",
            "category": "feature",
        }

    def test_skips_commits_without_issue_ref(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat: with ref (#50)")
        _commit(tmp_repo, "feat: no ref here")
        _commit(tmp_repo, "chore: housekeeping")

        entries = aggregate_from_git(tmp_repo)

        assert len(entries) == 1
        assert entries[0]["issue"] == "50"

    def test_skips_non_conventional_subjects(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "Random commit message (#99)")
        _commit(tmp_repo, "WIP fix bug (#100)")

        entries = aggregate_from_git(tmp_repo)

        assert entries == []

    def test_dedupes_by_issue_number(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat: first attempt (#42)")
        _commit(tmp_repo, "fix: follow-up on same issue (#42)")

        entries = aggregate_from_git(tmp_repo)

        # newest commit (fix) wins
        assert len(entries) == 1
        assert entries[0]["category"] == "fix"
        assert entries[0]["title"] == "follow-up on same issue"

    def test_maps_categories(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat: a (#1)")
        _commit(tmp_repo, "fix: b (#2)")
        _commit(tmp_repo, "refactor: c (#3)")
        _commit(tmp_repo, "perf: d (#4)")
        _commit(tmp_repo, "docs: e (#5)")
        _commit(tmp_repo, "chore: f (#6)")

        entries = {e["issue"]: e["category"] for e in aggregate_from_git(tmp_repo)}

        assert entries == {
            "1": "feature",
            "2": "fix",
            "3": "refactor",
            "4": "perf",
            "5": "docs",
            "6": "chore",
        }

    def test_since_rev_excludes_earlier_commits(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat: before tag (#10)")
        _run(["git", "tag", "v1"], tmp_repo)
        _commit(tmp_repo, "feat: after tag (#20)")

        entries = aggregate_from_git(tmp_repo, since_rev="v1")

        assert len(entries) == 1
        assert entries[0]["issue"] == "20"

    def test_breaking_change_marker_handled(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat!: breaking (#7)")

        entries = aggregate_from_git(tmp_repo)

        assert len(entries) == 1
        assert entries[0]["title"] == "breaking"

    def test_invalid_rev_returns_empty(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat: x (#1)")

        entries = aggregate_from_git(tmp_repo, since_rev="does-not-exist")

        assert entries == []


class TestLatestTag:
    def test_returns_most_recent_tag(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat: a (#1)")
        _run(["git", "tag", "v1"], tmp_repo)
        _commit(tmp_repo, "feat: b (#2)")
        _run(["git", "tag", "v2"], tmp_repo)

        assert latest_tag(tmp_repo) == "v2"

    def test_no_tag_returns_empty(self, tmp_repo: Path) -> None:
        _commit(tmp_repo, "feat: a (#1)")

        assert latest_tag(tmp_repo) == ""


class TestPhaseTag:
    def test_phase_tag_format(self) -> None:
        assert phase_tag(13) == "phase-13-complete"
        assert phase_tag(0) == "phase-0-complete"
