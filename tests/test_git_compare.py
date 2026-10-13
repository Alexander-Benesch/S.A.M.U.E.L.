from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from samuel.adapters.git_compare import compare_local_commits, read_local_file_at_revision
from samuel.core.errors import (
    CandidateFileTooLargeError,
    SCMRevisionError,
    SubjectTooLargeError,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "one.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "one.txt")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "one.txt").write_text("base\nhead\n", encoding="utf-8")
    (repo / "two.txt").write_text("second\n", encoding="utf-8")
    _git(repo, "add", "one.txt", "two.txt")
    _git(repo, "commit", "-qm", "head")
    return repo, base, _git(repo, "rev-parse", "HEAD")


def test_compare_returns_complete_diff_and_files_for_exact_pair(tmp_path: Path) -> None:
    repo, base, head = _repository(tmp_path)

    comparison = compare_local_commits(
        project_root=repo,
        repository="https://scm.example/owner/repo",
        base_sha=base,
        head_sha=head,
        max_diff_bytes=100_000,
    )

    assert comparison.base_sha == base
    assert comparison.head_sha == head
    assert comparison.changed_files == ("one.txt", "two.txt")
    assert "+head" in comparison.diff
    assert "two.txt" in comparison.diff
    assert comparison.diff_bytes == len(comparison.diff.encode("utf-8"))


def test_compare_exposes_both_rename_paths_and_deleted_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "outside.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "deleted.py").write_text("DELETE = True\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "outside.py", "inside.py")
    (repo / "deleted.py").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "rename and delete")
    head = _git(repo, "rev-parse", "HEAD")

    comparison = compare_local_commits(
        project_root=repo,
        repository="owner/repo",
        base_sha=base,
        head_sha=head,
        max_diff_bytes=100_000,
    )

    assert comparison.changed_files == ("deleted.py", "inside.py", "outside.py")
    assert "outside.py" in comparison.diff
    assert "inside.py" in comparison.diff
    assert "deleted.py" in comparison.diff


def test_compare_fails_closed_instead_of_truncating(tmp_path: Path) -> None:
    repo, base, head = _repository(tmp_path)

    with pytest.raises(SubjectTooLargeError) as error:
        compare_local_commits(
            project_root=repo,
            repository="https://scm.example/owner/repo",
            base_sha=base,
            head_sha=head,
            max_diff_bytes=10,
        )

    assert error.value.code == "subject_too_large"


def test_compare_rejects_unknown_commit(tmp_path: Path) -> None:
    repo, base, _ = _repository(tmp_path)

    with pytest.raises(SCMRevisionError) as error:
        compare_local_commits(
            project_root=repo,
            repository="https://scm.example/owner/repo",
            base_sha=base,
            head_sha="f" * 40,
            max_diff_bytes=100_000,
        )

    assert error.value.code == "unknown_commit"


def test_compare_requires_configured_checkout() -> None:
    with pytest.raises(SCMRevisionError) as error:
        compare_local_commits(
            project_root=None,
            repository="https://scm.example/owner/repo",
            base_sha="a" * 40,
            head_sha="b" * 40,
            max_diff_bytes=100_000,
        )

    assert error.value.code == "repository_checkout_missing"


def test_read_file_uses_exact_revision_not_mutable_worktree(tmp_path: Path) -> None:
    repo, _, head = _repository(tmp_path)
    (repo / "two.txt").write_text("mutable\n", encoding="utf-8")

    content = read_local_file_at_revision(
        project_root=repo,
        head_sha=head,
        path="two.txt",
        max_file_bytes=1000,
    )

    assert content == "second\n"


def test_read_file_returns_none_when_absent_at_revision(tmp_path: Path) -> None:
    repo, _, head = _repository(tmp_path)

    assert (
        read_local_file_at_revision(
            project_root=repo,
            head_sha=head,
            path="missing.py",
            max_file_bytes=1000,
        )
        is None
    )


def test_read_file_fails_closed_on_resource_limit(tmp_path: Path) -> None:
    repo, _, head = _repository(tmp_path)

    with pytest.raises(CandidateFileTooLargeError) as error:
        read_local_file_at_revision(
            project_root=repo,
            head_sha=head,
            path="two.txt",
            max_file_bytes=2,
        )

    assert error.value.code == "candidate_file_too_large"


def test_read_file_rejects_non_canonical_path(tmp_path: Path) -> None:
    repo, _, head = _repository(tmp_path)

    with pytest.raises(SCMRevisionError) as error:
        read_local_file_at_revision(
            project_root=repo,
            head_sha=head,
            path="../two.txt",
            max_file_bytes=1000,
        )

    assert error.value.code == "invalid_candidate_path"
