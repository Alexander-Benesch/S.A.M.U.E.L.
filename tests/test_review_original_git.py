"""Immutable Git integration stays outside slice tests (adapter boundary)."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from samuel.adapters.git_compare import compare_local_commits
from samuel.core.bus import Bus
from samuel.core.commands import ReviewCommand
from samuel.core.evaluation_subject import EvaluationSubject, RevisionComparison
from samuel.slices.review.handler import ReviewHandler
from samuel.slices.review.tests.test_handler import MockLLM, MockSCM, _payload
from samuel.slices.review.tests.test_original_input import reference


def test_review_uses_immutable_git_not_current_worktree(tmp_path: Path) -> None:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "--initial-branch=main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    file = tmp_path / "safe.py"
    file.write_text("safe = False\n")
    git("add", "safe.py")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    file.write_text("safe = True\n")
    git("commit", "-am", "candidate")
    head = git("rev-parse", "HEAD")

    class GitSCM(MockSCM):
        def compare_commits(self, base_sha, head_sha, *, max_diff_bytes) -> RevisionComparison:
            return compare_local_commits(
                project_root=tmp_path,
                repository=self.repository,
                base_sha=base_sha,
                head_sha=head_sha,
                max_diff_bytes=max_diff_bytes,
            )

    scm = GitSCM()
    original = scm.compare_commits(base, head, max_diff_bytes=1_000_000).diff
    scm.original_diff = original
    payload = _payload(scm)
    subject = replace(
        EvaluationSubject.from_dict(payload["evaluation_subject"]), base_sha=base, head_sha=head
    )
    payload["evaluation_subject"] = subject.as_dict()
    payload["diff_reference"] = reference(payload)
    file.write_text("dirty_worktree = True\n")
    llm = MockLLM()
    result = ReviewHandler(Bus(), scm=scm, llm=llm).handle(
        ReviewCommand(payload=payload, correlation_id="attempt-a")
    )
    assert result["reviewed"] is True
    assert original in llm.prompts[0]
    assert "dirty_worktree" not in llm.prompts[0]
