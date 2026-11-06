from __future__ import annotations

import os
import selectors
import subprocess
import time
from pathlib import Path, PurePosixPath

from samuel.core.errors import (
    CandidateFileTooLargeError,
    SCMRevisionError,
    SubjectTooLargeError,
)
from samuel.core.evaluation_subject import RevisionComparison


def _run_bounded_git(
    project_root: Path,
    args: list[str],
    *,
    max_output_bytes: int,
    error_code: str,
) -> bytes:
    """Run Git without retaining output beyond the configured resource limit."""

    try:
        process = subprocess.Popen(
            ["git", *args],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise SCMRevisionError("git_unavailable", "Git is unavailable") from exc

    assert process.stdout is not None
    output = bytearray()
    deadline = time.monotonic() + 30
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise SCMRevisionError("git_timeout", "Git comparison timed out")
            ready = selector.select(timeout=remaining)
            if not ready:
                process.kill()
                process.wait()
                raise SCMRevisionError("git_timeout", "Git comparison timed out")
            chunk = os.read(process.stdout.fileno(), 65_536)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > max_output_bytes:
                process.kill()
                process.wait()
                raise SubjectTooLargeError(max_output_bytes)
        return_code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        raise SCMRevisionError("git_timeout", "Git comparison timed out") from exc
    finally:
        selector.close()
        process.stdout.close()
    if return_code != 0:
        raise SCMRevisionError(error_code, "Git could not compare the requested commits")
    return bytes(output)


def _require_local_commit(project_root: Path, sha: str) -> None:
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SCMRevisionError("git_unavailable", "Git is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise SCMRevisionError("git_timeout", "Git revision lookup timed out") from exc
    if result.returncode != 0:
        raise SCMRevisionError("unknown_commit", "Requested commit is unavailable locally")


def compare_local_commits(
    *,
    project_root: Path | None,
    repository: str,
    base_sha: str,
    head_sha: str,
    max_diff_bytes: int,
) -> RevisionComparison:
    if project_root is None:
        raise SCMRevisionError(
            "repository_checkout_missing",
            "SCM adapter has no repository checkout for immutable comparison",
        )
    root = project_root.resolve()
    if not root.is_dir():
        raise SCMRevisionError(
            "repository_checkout_missing",
            "Configured repository checkout does not exist",
        )
    _require_local_commit(root, base_sha)
    _require_local_commit(root, head_sha)
    revision_range = f"{base_sha}...{head_sha}"
    names_bytes = _run_bounded_git(
        root,
        ["diff", "--name-only", "--no-renames", "--no-ext-diff", revision_range],
        max_output_bytes=max_diff_bytes,
        error_code="changed_files_failed",
    )
    diff_bytes = _run_bounded_git(
        root,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            revision_range,
        ],
        max_output_bytes=max_diff_bytes,
        error_code="diff_failed",
    )
    try:
        names = names_bytes.decode("utf-8")
        diff = diff_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SCMRevisionError(
            "non_utf8_diff",
            "Git comparison contains non-UTF-8 data and cannot be evaluated safely",
        ) from exc
    return RevisionComparison(
        repository=repository,
        base_sha=base_sha,
        head_sha=head_sha,
        changed_files=tuple(line for line in names.splitlines() if line),
        diff=diff,
        diff_bytes=len(diff_bytes),
    )


def read_local_file_at_revision(
    *,
    project_root: Path | None,
    head_sha: str,
    path: str,
    max_file_bytes: int,
) -> str | None:
    """Read one UTF-8 blob from an immutable local Git revision.

    ``None`` means that the canonical repository-relative path does not exist
    at ``head_sha``.  Operational, encoding and resource failures remain
    distinguishable and fail closed at the caller.
    """

    if project_root is None:
        raise SCMRevisionError(
            "repository_checkout_missing",
            "SCM adapter has no repository checkout for immutable file access",
        )
    root = project_root.resolve()
    if not root.is_dir():
        raise SCMRevisionError(
            "repository_checkout_missing",
            "Configured repository checkout does not exist",
        )
    candidate_path = PurePosixPath(path)
    if (
        not path
        or candidate_path.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate_path.parts)
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
    ):
        raise SCMRevisionError(
            "invalid_candidate_path",
            "SCM returned a non-canonical candidate file path",
        )
    _require_local_commit(root, head_sha)
    object_spec = f"{head_sha}:{candidate_path.as_posix()}"
    try:
        exists = subprocess.run(
            ["git", "cat-file", "-e", object_spec],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SCMRevisionError("git_unavailable", "Git is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise SCMRevisionError("git_timeout", "Git file lookup timed out") from exc
    if exists.returncode != 0:
        return None
    try:
        content = _run_bounded_git(
            root,
            ["cat-file", "blob", object_spec],
            max_output_bytes=max_file_bytes,
            error_code="candidate_file_read_failed",
        )
    except SubjectTooLargeError as exc:
        raise CandidateFileTooLargeError(max_file_bytes) from exc
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SCMRevisionError(
            "non_utf8_candidate_file",
            "Candidate file is not valid UTF-8 and cannot be syntax-checked",
        ) from exc
