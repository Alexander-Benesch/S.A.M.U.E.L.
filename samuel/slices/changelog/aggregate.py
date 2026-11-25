"""Aggregate changelog entries from git log (#163).

Parses conventional-commit messages between two revisions and returns the
entry-list shape expected by ``ChangelogCommand`` /
``ChangelogHandler.handle``.
"""

from __future__ import annotations

import re
from pathlib import Path

from samuel.build_info import product_tag_sort_key
from samuel.core import git as _git

# feat(scope)?: title (#123)   — scope and "(#NNN)" both optional in regex
# but we drop entries without an issue ref because the changelog renderer
# requires it.
_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|refactor|perf|docs|test|chore|build|ci|style)"
    r"(?:\([^)]+\))?!?:\s+"
    r"(?P<title>.+?)"
    r"\s*\(#(?P<issue>\d+)\)\s*$"
)

_CATEGORY_MAP = {
    "feat": "feature",
    "fix": "fix",
    "refactor": "refactor",
    "perf": "perf",
    "docs": "docs",
}


def aggregate_from_git(
    project_root: Path,
    since_rev: str = "",
    until_rev: str = "HEAD",
) -> list[dict[str, str]]:
    """Walk a git-log range and extract changelog entries.

    Only commits whose subject matches ``<type>(scope)?: title (#NNN)`` are
    kept. Commits without an issue ref are skipped — the renderer needs the
    number.

    Args:
        project_root: repo root for the ``git log`` call.
        since_rev: lower bound (exclusive). Empty -> log from repo start.
        until_rev: upper bound (inclusive). Defaults to HEAD.

    Returns:
        List of ``{"issue", "title", "category"}`` dicts in git-log order
        (newest first).
    """
    rev_range = f"{since_rev}..{until_rev}" if since_rev else until_rev
    ok, out = _git._run(
        ["log", rev_range, "--pretty=format:%s"],
        cwd=project_root,
    )
    if not ok:
        return []

    entries: list[dict[str, str]] = []
    seen_issues: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _CONVENTIONAL_RE.match(line)
        if not m:
            continue
        issue = m.group("issue")
        if issue in seen_issues:
            # Multiple commits for the same issue → first (newest) wins.
            continue
        seen_issues.add(issue)
        type_ = m.group("type")
        entries.append(
            {
                "issue": issue,
                "title": m.group("title").strip(),
                "category": _CATEGORY_MAP.get(type_, type_),
            }
        )
    return entries


def latest_tag(project_root: Path) -> str:
    """Return the highest reachable canonical product tag (or empty string).

    Historical ``phase-*-complete`` markers and malformed ``v*`` tags are not
    release boundaries. ``--phase`` remains an explicit opt-in in the CLI.
    """
    ok, out = _git._run(
        [
            "for-each-ref",
            "--merged=HEAD",
            "--sort=-version:refname",
            "--format=%(refname:short)",
            "refs/tags/v*",
        ],
        cwd=project_root,
    )
    if not ok:
        return ""
    product_tags = [tag.strip() for tag in out.splitlines() if product_tag_sort_key(tag.strip())]
    return max(
        product_tags, key=lambda tag: product_tag_sort_key(tag) or (0, 0, 0, 0, 0), default=""
    )


def phase_tag(phase: int) -> str:
    """Map a phase number to its release-tag (`phase-N-complete`)."""
    return f"phase-{phase}-complete"
