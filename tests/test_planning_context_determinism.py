from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from samuel.core.project_files import iter_project_files
from samuel.core.types import Issue
from samuel.slices.planning.handler import (
    _build_plan_prompt,
    _render_plan_files,
    _render_plan_grep,
)

_SOURCES = {
    "z.py": "needle = 'z'\n",
    "package/b.py": "needle = 'b'\n",
    "a.py": "needle = 'a'\n",
    "package/a.py": "needle = 'package-a'\n",
}


def _materialize(root: Path, order: Iterable[str]) -> None:
    for relative in order:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_SOURCES[relative])


def _grep(root: Path, *, limit: int = 3) -> str:
    return _render_plan_grep(
        root,
        ["needle"],
        frozenset({".py"}),
        [],
        limit_per_kw=limit,
    )


def _planning_prompt(root: Path) -> str:
    files = [path.relative_to(root).as_posix() for path in iter_project_files(root)]
    sections = {
        "skeleton": "## Skeleton\n\n### a.py\n  L1-1: module a",
        "plan_files": _render_plan_files(root, files),
        "grep": _grep(root, limit=10),
        "constraints": "## Architektur-Constraints\n- Repositorygrenze bleibt unverändert.",
    }
    issue = Issue(
        number=892,
        title="Planning-Kontext deterministisch ordnen",
        body="Alle needle-Treffer müssen stabil und vollständig eingebunden werden.",
        state="open",
    )
    return _build_plan_prompt(
        issue,
        context_sections=sections,
        test_selector_guidance=(
            "  - [ ] [TEST] tests.test_context — Test grün\n    Wirksamer Runner: unittest."
        ),
    )


def test_grep_output_is_identical_across_creation_orders(tmp_path: Path) -> None:
    forward = tmp_path / "forward"
    reverse = tmp_path / "reverse"
    paths = tuple(_SOURCES)
    _materialize(forward, paths)
    _materialize(reverse, reversed(paths))

    assert _grep(forward) == _grep(reverse)


def test_full_planning_prompt_digest_is_identical_across_creation_orders(
    tmp_path: Path,
) -> None:
    forward = tmp_path / "forward"
    reverse = tmp_path / "reverse"
    paths = tuple(_SOURCES)
    _materialize(forward, paths)
    _materialize(reverse, reversed(paths))

    forward_prompt = _planning_prompt(forward)
    reverse_prompt = _planning_prompt(reverse)

    assert forward_prompt.encode() == reverse_prompt.encode()
    assert (
        hashlib.sha256(forward_prompt.encode()).digest()
        == hashlib.sha256(reverse_prompt.encode()).digest()
    )


def test_grep_sorting_preserves_every_hit_and_reference(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    _materialize(root, reversed(tuple(_SOURCES)))

    output = _grep(root, limit=10)
    observed = [line.removeprefix("  ") for line in output.splitlines() if ":L" in line]
    expected = [f"{relative}:L1: {_SOURCES[relative].strip()}" for relative in sorted(_SOURCES)]

    assert observed == expected
    assert len(observed) == len(_SOURCES)
    assert len(set(observed)) == len(_SOURCES)
