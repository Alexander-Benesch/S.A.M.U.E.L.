from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by Python 3.10 CI
    import tomli as tomllib

from tools.release_gate import artifact_versions

ROOT = Path(__file__).parents[1]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _version(root: Path) -> str:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "setuptools_scm",
            "--root",
            str(root),
            "--config",
            str(root / "pyproject.toml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _version_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    package = root / "samuel"
    package.mkdir(parents=True)
    shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(ROOT / "LICENSE", root / "LICENSE")
    (package / "__init__.py").write_text("", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Version Test")
    _git(root, "config", "user.email", "version@example.invalid")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "release")
    _git(root, "tag", "-a", "v2.0.0a2", "-m", "release")
    return root


def _build(root: Path, dist: Path) -> dict[Path, str]:
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(dist)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return artifact_versions(dist)


def test_pyproject_has_one_dynamic_product_version_authority() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        document = tomllib.load(stream)

    project = document["project"]
    scm = document["tool"]["setuptools_scm"]
    assert "version" not in project
    assert project["dynamic"] == ["version"]
    assert scm["version_scheme"] == "guess-next-dev"
    assert scm["local_scheme"] == "node-and-date"
    assert scm["fallback_version"] == "0+unknown"
    assert scm["tag"]["prefix"] == "v"
    assert scm["tag"]["strict"] is True


def test_exact_product_tag_and_built_artifacts_have_exact_version(tmp_path: Path) -> None:
    root = _version_repo(tmp_path)
    assert _version(root) == "2.0.0a2"

    dist = tmp_path / "dist"
    assert set(_build(root, dist).values()) == {"2.0.0a2"}


def test_development_phase_tag_and_dirty_versions_are_unambiguous(tmp_path: Path) -> None:
    root = _version_repo(tmp_path)
    _git(root, "commit", "--allow-empty", "-q", "-m", "development")
    revision = _git(root, "rev-parse", "--short", "HEAD")
    _git(root, "tag", "phase-14-complete")

    clean = _version(root)
    assert clean.startswith("2.0.0a3.dev1+")
    assert f"g{revision}" in clean
    assert "phase" not in clean
    assert set(_build(root, tmp_path / "dev-dist").values()) == {clean}

    (root / "samuel" / "__init__.py").write_text("# dirty\n", encoding="utf-8")
    dirty = _version(root)
    assert dirty != clean
    assert f"g{revision}" in dirty
    assert ".d" in dirty


def test_source_without_scm_or_package_metadata_uses_non_release_fallback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "unpacked-source"
    package = root / "samuel"
    package.mkdir(parents=True)
    shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(ROOT / "LICENSE", root / "LICENSE")
    (package / "__init__.py").write_text("", encoding="utf-8")

    assert _version(root) == "0+unknown"
    assert set(_build(root, tmp_path / "fallback-dist").values()) == {"0+unknown"}
