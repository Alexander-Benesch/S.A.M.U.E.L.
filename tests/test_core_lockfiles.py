"""#368 Task 4: Lockfile-Reader + Diff-Extraktion."""

from __future__ import annotations

import json
from pathlib import Path

from samuel.core.lockfiles import (
    added_removed_from_diff,
    is_lockfile,
    parse_lockfile,
    read_current_lockfile_packages,
)


class TestParseLockfile:
    def test_toml_poetry(self):
        content = '[[package]]\nname = "requests"\nversion = "2.0"\n\n[[package]]\nname = "click"\n'
        assert parse_lockfile("poetry.lock", content) == {"requests", "click"}

    def test_cargo(self):
        assert parse_lockfile("Cargo.lock", 'name = "serde"\n') == {"serde"}

    def test_go_sum(self):
        content = "github.com/foo/bar v1.2.3 h1:abc=\ngithub.com/foo/bar v1.2.3/go.mod h1:def=\n"
        assert parse_lockfile("go.sum", content) == {"github.com/foo/bar"}

    def test_npm(self):
        content = '{\n  "packages": {\n    "node_modules/lodash": {},\n    "node_modules/axios": {}\n  }\n}'
        assert parse_lockfile("package-lock.json", content) == {"lodash", "axios"}

    def test_pipfile_lock(self):
        content = json.dumps({"default": {"flask": {}}, "develop": {"pytest": {}}})
        assert parse_lockfile("Pipfile.lock", content) == {"flask", "pytest"}


class TestIsLockfile:
    def test_recognised(self):
        assert is_lockfile("poetry.lock")
        assert is_lockfile("path/to/uv.lock")
        assert not is_lockfile("main.py")


class TestDiffExtraction:
    def test_added_and_removed(self):
        diff = (
            "diff --git a/poetry.lock b/poetry.lock\n"
            "--- a/poetry.lock\n"
            "+++ b/poetry.lock\n"
            '+name = "newpkg"\n'
            '-name = "oldpkg"\n'
        )
        out = added_removed_from_diff(diff)
        assert out["added"] == {"newpkg"}
        assert out["removed"] == {"oldpkg"}

    def test_version_bump_not_counted(self):
        diff = '+++ b/poetry.lock\n-name = "samepkg"\n+name = "samepkg"\n'
        out = added_removed_from_diff(diff)
        assert out["added"] == set()
        assert out["removed"] == set()

    def test_non_lockfile_section_ignored(self):
        diff = '+++ b/src/app.py\n+name = "notapkg"\n'
        assert added_removed_from_diff(diff) == {"added": set(), "removed": set()}


def test_read_current_lockfile_packages(tmp_path: Path):
    (tmp_path / "poetry.lock").write_text('name = "rich"\n')
    (tmp_path / "Cargo.lock").write_text('name = "tokio"\n')
    assert read_current_lockfile_packages(tmp_path) == {"rich", "tokio"}
