"""Slice-neutral path-pattern primitives used by PR security gates."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Final

DEFAULT_SECRET_PATH_PATTERNS: Final = (
    ".env",
    "secrets",
    "credentials",
    "*.pem",
    "id_rsa",
)


def path_matches_pattern(path: str, pattern: str) -> bool:
    normalized_path = path.lower()
    normalized_pattern = pattern.lower()
    return (
        fnmatch.fnmatch(normalized_path, normalized_pattern)
        or fnmatch.fnmatch(Path(normalized_path).name, normalized_pattern)
        or normalized_pattern in normalized_path
    )
