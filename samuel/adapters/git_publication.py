"""Provider-neutral publication of a validated file projection to Git.

The adapter owns the existing marker, no-force, no-op and receipt effects.  It
does not decide which source data is trustworthy enough to publish; callers
must supply an already validated projection and its exact source bindings.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MARKER = ".samuel-wiki-publication.json"
MAX_PUBLICATION_FILES = 256
MAX_PUBLICATION_BYTES = 16 * 1024 * 1024
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEAD = re.compile(r"^[0-9a-f]{40}$")


class PublishError(RuntimeError):
    """Raised when a projection cannot be published without losing authority."""


def publication_digest(files: Mapping[str, bytes]) -> str:
    value = hashlib.sha256()
    for path, content in sorted(files.items()):
        descriptor = path.encode()
        value.update(len(descriptor).to_bytes(4, "big"))
        value.update(descriptor)
        value.update(len(content).to_bytes(8, "big"))
        value.update(content)
    return f"sha256:{value.hexdigest()}"


def safe_remote(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise PublishError("remote URL must not contain credentials")
    if parsed.scheme:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value


def run_git(cwd: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode:
        raise PublishError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _read_marker(root: Path) -> dict[str, Any] | None:
    path = root / MARKER
    if path.is_symlink():
        raise PublishError("publication marker must not be a symlink")
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublishError("invalid publication marker") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise PublishError("invalid publication marker")
    return value


def _validate_projection(projected: Mapping[str, bytes]) -> dict[str, bytes]:
    if not projected or len(projected) > MAX_PUBLICATION_FILES:
        raise PublishError("publication projection has an invalid file count")
    checked: dict[str, bytes] = {}
    total = 0
    for raw_path, content in projected.items():
        path = PurePosixPath(raw_path)
        if (
            not raw_path
            or path.is_absolute()
            or raw_path != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
            or raw_path == MARKER
        ):
            raise PublishError("publication projection contains an unsafe path")
        if not isinstance(content, bytes):
            raise PublishError("publication projection content must be bytes")
        total += len(content)
        if total > MAX_PUBLICATION_BYTES:
            raise PublishError("publication projection exceeds its byte limit")
        checked[raw_path] = content
    return checked


def publish_projection(
    *,
    projected: Mapping[str, bytes],
    source_head_sha: str,
    input_artifact_digest: str,
    remote: str,
    branch: str,
    receipt_path: Path,
    commit_subject: str,
    adopt_existing_head: str | None = None,
    author_name: str = "S.A.M.U.E.L. Wiki Publisher",
    author_email: str = "samuel-wiki@localhost",
    git_runner: Callable[..., str] = run_git,
) -> dict[str, Any]:
    """Publish validated bytes while preserving the established Git effects."""

    remote = safe_remote(remote)
    projection = _validate_projection(projected)
    if _HEAD.fullmatch(source_head_sha) is None:
        raise PublishError("source head must be a full lowercase Git SHA")
    if _DIGEST.fullmatch(input_artifact_digest) is None:
        raise PublishError("input artifact digest must be canonical SHA-256")
    if not branch or any(char in branch for char in "\r\n\x00"):
        raise PublishError("target branch is invalid")
    if (
        not commit_subject
        or len(commit_subject) > 120
        or any(char in commit_subject for char in "\r\n\x00")
    ):
        raise PublishError("commit subject is invalid")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if receipt_path.parent.is_symlink() or receipt_path.is_symlink():
        raise PublishError("publication receipt path must not be a symlink")
    staging = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    if staging.exists() or staging.is_symlink():
        raise PublishError("stale or unsafe publication receipt staging file exists")
    content_digest = publication_digest(projection)

    temp_root = Path(tempfile.mkdtemp(prefix="samuel-wiki-publish-"))
    work = temp_root / "wiki"
    try:
        clone = subprocess.run(
            ["git", "clone", "--branch", branch, remote, str(work)],
            check=False,
            capture_output=True,
            text=True,
        )
        if clone.returncode:
            work.mkdir()
            git_runner(work, "init", "-b", branch)
            git_runner(work, "remote", "add", "origin", remote)
        previous_head = git_runner(work, "rev-parse", "HEAD", check=False) or None
        tracked = set(git_runner(work, "ls-files").splitlines()) if previous_head else set()
        marker = _read_marker(work)
        if marker is None and tracked and adopt_existing_head != previous_head:
            raise PublishError(
                f"unmanaged wiki at {previous_head}; exact --adopt-existing-head required"
            )
        if marker is not None:
            raw_managed = marker.get("managed_files", [])
            if not isinstance(raw_managed, list) or not all(
                isinstance(item, str) for item in raw_managed
            ):
                raise PublishError("publication marker has an invalid managed file set")
            managed = set(raw_managed)
            if tracked != managed | {MARKER}:
                raise PublishError("remote contains unknown or missing managed files")
            current: dict[str, bytes] = {}
            for path in managed:
                target = work / path
                if target.is_symlink() or not target.is_file():
                    raise PublishError("remote contains an unsafe managed file")
                current[path] = target.read_bytes()
            if publication_digest(current) != marker.get("published_content_digest"):
                raise PublishError("remote content differs from its publication marker")

        expected_marker = {
            "schema_version": "1.0",
            "input_artifact_digest": input_artifact_digest,
            "source_head_sha": source_head_sha,
            "published_content_digest": content_digest,
            "managed_files": sorted(projection),
        }
        if marker == expected_marker and all(
            (work / path).read_bytes() == data for path, data in projection.items()
        ):
            status = "unchanged"
            new_head = previous_head
        else:
            for child in work.iterdir():
                if child.name == ".git":
                    continue
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            for path, content in projection.items():
                target = work / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            (work / MARKER).write_text(
                json.dumps(expected_marker, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            git_runner(work, "add", "-A")
            git_runner(
                work,
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                f"user.name={author_name}",
                "-c",
                f"user.email={author_email}",
                "commit",
                "-m",
                f"docs: publish {commit_subject} {source_head_sha[:12]}",
            )
            git_runner(work, "push", "origin", f"HEAD:{branch}")
            new_head = git_runner(work, "rev-parse", "HEAD")
            status = "published"

        result = {
            "schema_version": "1.0",
            "status": status,
            "target_remote": remote,
            "target_branch": branch,
            "previous_target_commit": previous_head,
            "target_commit": new_head,
            "input_artifact_digest": input_artifact_digest,
            "source_head_sha": source_head_sha,
            "published_content_digest": content_digest,
            "published_files": sorted(projection),
            "created_at": datetime.now(tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(staging, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            staging.unlink(missing_ok=True)
            raise
        os.replace(staging, receipt_path)
        return result
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
