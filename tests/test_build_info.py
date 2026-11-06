from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path

from samuel import __version__
from samuel.build_info import product_version, resolve_build_info


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def test_product_version_uses_normalized_distribution_metadata() -> None:
    expected = importlib.metadata.version("samuel")
    assert product_version() == expected
    assert __version__ == expected


def test_explicit_full_revision_supports_packaged_builds(tmp_path: Path) -> None:
    revision = "A" * 40
    info = resolve_build_info(
        project_root=tmp_path,
        environ={"SAMUEL_BUILD_REVISION": revision, "SAMUEL_BUILD_DIRTY": "true"},
    )
    assert info.revision == revision.lower()
    assert info.dirty is True
    assert info.revision_source == "environment"


def test_missing_scm_metadata_never_invents_a_revision(tmp_path: Path) -> None:
    info = resolve_build_info(project_root=tmp_path, environ={})
    assert info.revision is None
    assert info.dirty is None
    assert info.revision_source == "unavailable"


def test_missing_package_metadata_uses_non_release_fallback(monkeypatch) -> None:
    def missing(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr("samuel.build_info.version", missing)
    assert product_version() == "0+unknown"


def test_git_source_build_reports_full_head_and_dirty_state(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "initial")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    clean = resolve_build_info(project_root=tmp_path, environ={})
    assert clean.revision == revision
    assert clean.dirty is False
    assert clean.revision_source == "git"

    tracked.write_text("two\n", encoding="utf-8")
    dirty = resolve_build_info(project_root=tmp_path, environ={})
    assert dirty.revision == revision
    assert dirty.dirty is True

    tracked.write_text("one\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")
    untracked = resolve_build_info(project_root=tmp_path, environ={})
    assert untracked.revision == revision
    assert untracked.dirty is True


def test_invalid_revision_override_is_not_accepted_as_evidence(tmp_path: Path) -> None:
    info = resolve_build_info(
        project_root=tmp_path,
        environ={"SAMUEL_BUILD_REVISION": "main"},
    )
    assert info.revision is None
    assert info.revision_source == "invalid_environment"


def test_cli_version_matches_package_metadata() -> None:
    console_script = Path(sys.prefix) / "bin" / "samuel"
    assert console_script.is_file()
    result = subprocess.run(
        [str(console_script), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == f"samuel {importlib.metadata.version('samuel')}"
