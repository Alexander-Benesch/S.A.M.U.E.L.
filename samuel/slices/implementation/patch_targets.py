from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


@dataclass(frozen=True)
class ResolvedPatchTarget:
    """Canonical, project-root-bound target for an implementation patch."""

    path: Path
    relative: str


def resolve_patch_target(
    project_root: Path,
    raw_target: Any,
    *,
    git_control_paths: Iterable[Path] = (),
) -> tuple[ResolvedPatchTarget | None, str | None]:
    """Resolve an untrusted patch target without allowing a root escape.

    Rejection reasons are deliberately content-free so callers can expose them
    in events and diagnostics without reflecting attacker-controlled paths.
    """

    if not isinstance(raw_target, str):
        return None, "invalid_type"
    if not raw_target:
        return None, "empty"
    if raw_target != raw_target.strip():
        return None, "not_normalized"
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_target):
        return None, "control_character"

    posix_target = PurePosixPath(raw_target)
    windows_target = PureWindowsPath(raw_target)
    if posix_target.is_absolute() or windows_target.is_absolute() or windows_target.drive:
        return None, "absolute"
    if "\\" in raw_target:
        return None, "non_portable_separator"
    if ".." in posix_target.parts:
        return None, "traversal"
    if any(part.casefold() == ".git" for part in posix_target.parts):
        return None, "git_control_plane"
    if raw_target != posix_target.as_posix():
        return None, "not_normalized"

    try:
        root = project_root.resolve(strict=True)
        candidate = (root / posix_target).resolve(strict=False)
    except (OSError, RuntimeError):
        return None, "resolution_error"

    if candidate == root:
        return None, "project_root"
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        return None, "outside_project"

    for raw_control_path in git_control_paths:
        try:
            control_path = raw_control_path.resolve(strict=False)
        except (OSError, RuntimeError):
            return None, "resolution_error"
        if candidate == control_path or candidate.is_relative_to(control_path):
            return None, "git_control_plane"
    return ResolvedPatchTarget(path=candidate, relative=relative), None
