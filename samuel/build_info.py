"""Product version and source-build identity.

Product tags feed distribution metadata through setuptools-scm; the installed
metadata is the sole runtime version source.  The full Git revision remains
separate evidence and is never a second manually maintained product version.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_DISTRIBUTION = "samuel"
_UNKNOWN_VERSION = "0+unknown"
_FULL_GIT_REVISION = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")
_PRODUCT_TAG = re.compile(
    r"v(?P<version>"
    r"(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:(?P<stage>a|b|rc)(?P<serial>0|[1-9]\d*))?"
    r")\Z"
)


@dataclass(frozen=True)
class BuildInfo:
    """Immutable product/build identity resolved once at process start."""

    product_version: str
    revision: str | None
    dirty: bool | None
    revision_source: str

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "product_version": self.product_version,
            "revision": self.revision,
            "dirty": self.dirty,
            "revision_source": self.revision_source,
        }


def product_version_from_tag(tag: str) -> str | None:
    """Return a canonical released product version, or ``None`` for other tags."""

    match = _PRODUCT_TAG.fullmatch(tag)
    return match.group("version") if match else None


def product_tag(version_value: str) -> str:
    """Return the canonical product tag or reject unsupported PEP-440 forms."""

    tag = f"v{version_value}"
    if product_version_from_tag(tag) != version_value:
        raise ValueError(f"not a canonical S.A.M.U.E.L. product version: {version_value!r}")
    return tag


def product_tag_sort_key(tag: str) -> tuple[int, int, int, int, int] | None:
    """Return the project release order for a canonical tag."""

    match = _PRODUCT_TAG.fullmatch(tag)
    if match is None:
        return None
    stage = match.group("stage")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        {"a": 0, "b": 1, "rc": 2, None: 3}[stage],
        int(match.group("serial") or 0),
    )


def product_version() -> str:
    """Return the normalized installed package version, or an honest fallback."""

    try:
        return version(_DISTRIBUTION)
    except PackageNotFoundError:
        return _UNKNOWN_VERSION


def _git_output(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed executable and arguments
        ["git", *args],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=3,
    )


def resolve_build_info(
    *,
    project_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> BuildInfo:
    """Resolve package metadata plus an optional full source revision.

    ``SAMUEL_BUILD_REVISION`` is intended for packaged/container deployments
    whose source checkout is not present.  It must be a full SHA-1/SHA-256 Git
    object id.  Otherwise only the repository containing this package is
    inspected; the current working directory is never treated as authority.
    """

    env = os.environ if environ is None else environ
    explicit = env.get("SAMUEL_BUILD_REVISION", "").strip()
    if explicit:
        if not _FULL_GIT_REVISION.fullmatch(explicit):
            return BuildInfo(product_version(), None, None, "invalid_environment")
        dirty_raw = env.get("SAMUEL_BUILD_DIRTY", "").strip().lower()
        dirty = dirty_raw in {"1", "true", "yes"} if dirty_raw else None
        return BuildInfo(product_version(), explicit.lower(), dirty, "environment")

    root = project_root or Path(__file__).resolve().parent.parent
    try:
        top_level = _git_output(root, "rev-parse", "--show-toplevel")
        if top_level.returncode != 0:
            raise RuntimeError("not a Git worktree")
        repository = Path(top_level.stdout.strip()).resolve()
        if repository != root.resolve():
            raise RuntimeError("package is not rooted in the detected Git worktree")

        head = _git_output(repository, "rev-parse", "--verify", "HEAD")
        revision = head.stdout.strip().lower()
        if head.returncode != 0 or not _FULL_GIT_REVISION.fullmatch(revision):
            raise RuntimeError("HEAD is not a full Git object id")

        status = _git_output(repository, "status", "--porcelain", "--untracked-files=normal")
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        return BuildInfo(product_version(), revision, dirty, "git")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return BuildInfo(product_version(), None, None, "unavailable")
