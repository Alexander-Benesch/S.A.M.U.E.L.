"""Action-bound safety policy for commands executed by S.A.M.U.E.L.

The policy operates on argument vectors at the execution boundary.  Text
inspection remains available for diagnostics, but is not the enforcement
mechanism for subprocess calls.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

_TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DROP", re.compile(r"\bDROP\b", re.IGNORECASE)),
    ("TRUNCATE", re.compile(r"\bTRUNCATE\b", re.IGNORECASE)),
    ("rm -rf", re.compile(r"(?:^|\s)rm\s+-rf(?:\s|$)", re.IGNORECASE)),
)

_DELETE_STATEMENT = re.compile(r"\bDELETE\s+FROM\b[^;]*(?:;|$)", re.IGNORECASE)
_WHERE_CLAUSE = re.compile(r"\bWHERE\b", re.IGNORECASE)


def _git_subcommand(args: list[str] | tuple[str, ...]) -> tuple[str, list[str]]:
    """Return a Git subcommand and its arguments after global options."""

    normalized = list(args)
    if normalized and normalized[0] == "git":
        normalized = normalized[1:]
    index = 0
    options_with_value = {"-c", "-C", "--git-dir", "--work-tree", "--namespace"}
    while index < len(normalized) and normalized[index].startswith("-"):
        option = normalized[index]
        index += 2 if option in options_with_value else 1
    if index >= len(normalized):
        return "", []
    return normalized[index], normalized[index + 1 :]


def blocked_git_patterns(args: list[str] | tuple[str, ...]) -> list[str]:
    """Return destructive Git patterns found in an argument vector."""

    command, command_args = _git_subcommand(args)
    blocked: list[str] = []
    if command == "push":
        if "--force" in command_args:
            blocked.append("git push --force")
        if "-f" in command_args:
            blocked.append("git push -f")
    if command == "reset" and "--hard" in command_args:
        blocked.append("git reset --hard")
    return blocked


def validate_command_args(args: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Evaluate an already-tokenized command without shell reconstruction."""

    blocked = blocked_git_patterns(args)
    return {"safe": not blocked, "blocked_patterns": blocked}


def validate_command_text(command_text: str) -> dict[str, Any]:
    """Evaluate diagnostic free text using the same Git argument policy."""

    blocked = [name for name, pattern in _TEXT_PATTERNS if pattern.search(command_text)]
    for statement in _DELETE_STATEMENT.finditer(command_text):
        if not _WHERE_CLAUSE.search(statement.group(0)):
            blocked.append("DELETE FROM without WHERE")
            break
    try:
        args = shlex.split(command_text)
    except ValueError:
        args = []
    for pattern in blocked_git_patterns(args):
        if pattern not in blocked:
            blocked.append(pattern)
    return {"safe": not blocked, "blocked_patterns": blocked}
