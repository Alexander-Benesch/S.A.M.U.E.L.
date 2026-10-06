#!/usr/bin/env python3
"""Fail-closed pre/post-tag gate for S.A.M.U.E.L. product releases (#490)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Mapping
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from samuel.build_info import product_version_from_tag  # noqa: E402
from tools.rollout_evidence import (  # noqa: E402
    RolloutEvidenceError,
    load_and_validate_rollout_evidence,
)

_FULL_GIT_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_PRETEND_VERSION_ENV = "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SAMUEL"
_LEGACY_SCORE_AUTHORITY_LAST_RELEASE = "2.0.0a4"


class ReleaseGateError(RuntimeError):
    """A release identity or artifact is inconsistent."""


def _git(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed executable and structured arguments
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ReleaseGateError(f"git {' '.join(args)}: {detail}")
    return completed.stdout.strip() if completed.returncode == 0 else ""


def verify_version_authority(root: Path, *, tag: str) -> None:
    """Require the reviewed tag-derived setuptools-scm contract."""

    with (root / "pyproject.toml").open("rb") as stream:
        document = tomllib.load(stream)
    project = document.get("project", {})
    if project.get("version") is not None:
        raise ReleaseGateError("pyproject.toml must not define a static project.version")
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list) or "version" not in dynamic:
        raise ReleaseGateError("pyproject.toml must declare project.version as dynamic")

    scm = document.get("tool", {}).get("setuptools_scm", {})
    expected = {
        "version_scheme": "guess-next-dev",
        "local_scheme": "node-and-date",
        "fallback_version": "0+unknown",
    }
    for key, value in expected.items():
        if scm.get(key) != value:
            raise ReleaseGateError(f"tool.setuptools_scm.{key} must be {value!r}")

    tag_config = scm.get("tag", {})
    if tag_config.get("prefix") != "v" or tag_config.get("strict") is not True:
        raise ReleaseGateError("setuptools-scm must use strict v-prefixed product tags")
    tag_regex = tag_config.get("regex")
    version = product_version_from_tag(tag)
    if not isinstance(tag_regex, str) or version is None:
        raise ReleaseGateError("setuptools-scm product-tag regex is missing or invalid")
    try:
        match = re.fullmatch(tag_regex, version)
    except re.error as exc:
        raise ReleaseGateError(f"invalid setuptools-scm tag regex: {exc}") from exc
    if match is None or match.groupdict().get("version") != version:
        raise ReleaseGateError(f"setuptools-scm would not resolve product tag {tag!r}")


def verify_version_override(
    *, mode: str, version: str, environ: Mapping[str, str] | None = None
) -> None:
    """Constrain the disposable pre-tag override and forbid it after tagging."""

    value = (os.environ if environ is None else environ).get(_PRETEND_VERSION_ENV, "")
    if mode == "pre-tag" and value != version:
        raise ReleaseGateError(f"pre-tag build must set {_PRETEND_VERSION_ENV}={version!r}")
    if mode == "post-tag" and value:
        raise ReleaseGateError(f"post-tag build must not set {_PRETEND_VERSION_ENV}")


def restore_remote_annotated_tag(root: Path, *, tag: str, remote: str = "origin") -> None:
    """Restore an annotated tag object after checkout replaced its local ref."""

    if product_version_from_tag(tag) is None:
        raise ReleaseGateError(f"invalid product tag: {tag!r}")
    tag_ref = f"refs/tags/{tag}"
    _git(root, "fetch", "--force", "--no-tags", remote, f"{tag_ref}:{tag_ref}")
    tag_type = _git(root, "cat-file", "-t", tag_ref, check=False)
    if tag_type != "tag":
        raise ReleaseGateError(f"remote tag {tag!r} is missing or is not annotated")


def verify_source_identity(root: Path, *, tag: str, commit_ref: str, mode: str) -> tuple[str, str]:
    """Bind a clean checkout, main ref and optional annotated tag to one commit."""

    version = product_version_from_tag(tag)
    if version is None:
        raise ReleaseGateError(f"invalid product tag: {tag!r}")
    verify_version_authority(root, tag=tag)

    head = _git(root, "rev-parse", "--verify", "HEAD").lower()
    expected = _git(root, "rev-parse", "--verify", f"{commit_ref}^{{commit}}").lower()
    if not _FULL_GIT_REVISION.fullmatch(head) or head != expected:
        raise ReleaseGateError(
            f"HEAD {head!r} is not the intended {commit_ref} commit {expected!r}"
        )

    dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise ReleaseGateError("release checkout is not clean")

    tag_ref = f"refs/tags/{tag}"
    tag_type = _git(root, "cat-file", "-t", tag_ref, check=False)
    if mode == "pre-tag":
        if tag_type:
            raise ReleaseGateError(f"tag {tag!r} already exists; release tags are create-only")
    elif mode == "post-tag":
        if tag_type != "tag":
            raise ReleaseGateError(f"tag {tag!r} is missing or is not annotated")
        tagged_commit = _git(root, "rev-list", "-n", "1", tag).lower()
        if tagged_commit != head:
            raise ReleaseGateError(
                f"tag {tag!r} points to {tagged_commit!r}, expected checked commit {head!r}"
            )
    else:
        raise ReleaseGateError(f"unsupported release-gate mode: {mode!r}")

    return version, head


def verify_changelog(root: Path, version: str) -> None:
    """Require a dated, reviewed release section instead of only Unreleased."""

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    release_heading = re.compile(
        rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
        re.MULTILINE,
    )
    if release_heading.search(changelog) is None:
        raise ReleaseGateError(f"CHANGELOG.md has no dated [{version}] release entry")


def _product_version_order(version: str) -> tuple[int, int, int, int, int]:
    match = re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:(a|b|rc)(0|[1-9]\d*))?",
        version,
    )
    if match is None:
        raise ReleaseGateError(f"invalid product version for authority window: {version!r}")
    stage = {"a": 0, "b": 1, "rc": 2, None: 3}[match.group(4)]
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        stage,
        int(match.group(5) or 0),
    )


def verify_legacy_authority_window(root: Path, version: str) -> None:
    """Allow rollback only in a4; later releases need evidence and removal."""

    if _product_version_order(version) <= _product_version_order(
        _LEGACY_SCORE_AUTHORITY_LAST_RELEASE
    ):
        return

    legacy_locations: list[str] = []
    if (root / "config" / "gates.legacy.json").exists():
        legacy_locations.append("config/gates.legacy.json")
    for path in sorted((root / "config" / "workflows").glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReleaseGateError(f"cannot validate authority workflow {path}: {exc}") from exc
        if isinstance(document, dict) and document.get("legacy_steps") is not None:
            legacy_locations.append(path.relative_to(root).as_posix() + "#/legacy_steps")
    config_source = root / "samuel" / "core" / "config.py"
    if config_source.exists() and "legacy_score_authority" in config_source.read_text(
        encoding="utf-8"
    ):
        legacy_locations.append("samuel/core/config.py#legacy_score_authority")
    if legacy_locations:
        raise ReleaseGateError(
            "legacy_score_authority expired after 2.0.0a4; remove: " + ", ".join(legacy_locations)
        )

    rollout_dir = root / "docs" / "rollout"
    try:
        load_and_validate_rollout_evidence(
            rollout_dir / "issue-399.json",
            rollout_dir / "issue-399.schema.json",
        )
    except RolloutEvidenceError as exc:
        raise ReleaseGateError(f"bound-authority rollout evidence is invalid: {exc}") from exc


def verify_runtime_surfaces(version: str) -> None:
    """Check the package, Python API, CLI and dashboard status contract."""

    from importlib.metadata import version as distribution_version

    import samuel
    from samuel.core.bus import Bus
    from samuel.slices.dashboard.handler import DashboardHandler

    observed: dict[str, str] = {
        "distribution metadata": distribution_version("samuel"),
        "samuel.__version__": samuel.__version__,
    }
    completed = subprocess.run(  # noqa: S603 - current verified interpreter/module
        [sys.executable, "-m", "samuel", "--version"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ReleaseGateError(f"samuel --version failed: {completed.stderr.strip()}")
    observed["CLI"] = completed.stdout.strip().removeprefix("samuel ")

    dashboard = DashboardHandler(Bus(), product_version=samuel.__version__)
    observed["dashboard status"] = str(dashboard.get_status()["build"]["product_version"])

    mismatches = {surface: value for surface, value in observed.items() if value != version}
    if mismatches:
        detail = ", ".join(f"{surface}={value!r}" for surface, value in mismatches.items())
        raise ReleaseGateError(f"runtime version mismatch: expected {version!r}; {detail}")


def _metadata_version(raw: bytes, artifact: str) -> str:
    value = BytesParser().parsebytes(raw)["Version"]
    if not value:
        raise ReleaseGateError(f"{artifact} has no Version metadata")
    return value


def artifact_versions(dist_dir: Path) -> dict[Path, str]:
    """Read one fresh wheel and one fresh sdist without trusting filenames."""

    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseGateError(
            f"expected exactly one wheel and one sdist, found {len(wheels)} and {len(sdists)}"
        )

    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise ReleaseGateError(f"{wheel.name} has {len(metadata_names)} METADATA files")
        wheel_version = _metadata_version(archive.read(metadata_names[0]), wheel.name)

    sdist = sdists[0]
    with tarfile.open(sdist, mode="r:gz") as archive:
        members = [
            member
            for member in archive.getmembers()
            if member.isfile()
            and PurePosixPath(member.name).name == "PKG-INFO"
            and len(PurePosixPath(member.name).parts) == 2
        ]
        if len(members) != 1:
            raise ReleaseGateError(f"{sdist.name} has {len(members)} root PKG-INFO files")
        stream = archive.extractfile(members[0])
        if stream is None:
            raise ReleaseGateError(f"{sdist.name} PKG-INFO cannot be read")
        sdist_version = _metadata_version(stream.read(), sdist.name)

    return {wheel: wheel_version, sdist: sdist_version}


def verify_artifacts(dist_dir: Path, version: str) -> list[Path]:
    versions = artifact_versions(dist_dir)
    mismatches = {path.name: value for path, value in versions.items() if value != version}
    if mismatches:
        detail = ", ".join(f"{name}={value!r}" for name, value in mismatches.items())
        raise ReleaseGateError(f"artifact version mismatch: expected {version!r}; {detail}")
    return sorted(versions)


def materialize_runtime_lock(root: Path, dist_dir: Path, version: str) -> Path:
    """Publish the reviewed runtime lock as a manifest-bound local-install asset."""

    source = root / "requirements-container.lock"
    policy_path = root / "containers" / "lock-policy.json"
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        expected = policy["lock_contract"]["runtime_lock"]
        expected_path = expected["path"]
        expected_digest = expected["sha256"]
        content = source.read_bytes()
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReleaseGateError(f"runtime lock authority is invalid: {exc}") from exc
    actual_digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
    if expected_path != "requirements-container.lock" or actual_digest != expected_digest:
        raise ReleaseGateError("runtime lock differs from containers/lock-policy.json")
    target = dist_dir / f"samuel-runtime-{version}.lock"
    if target.exists() and target.read_bytes() != content:
        raise ReleaseGateError(f"existing runtime lock asset differs: {target.name}")
    target.write_bytes(content)
    return target


def write_manifest(
    dist_dir: Path,
    *,
    tag: str,
    version: str,
    commit: str,
    artifacts: list[Path],
) -> Path:
    """Write deterministic release identity and checksums beside the artifacts."""

    files: list[dict[str, Any]] = []
    for path in sorted(artifacts, key=lambda item: item.name):
        raw = path.read_bytes()
        files.append(
            {
                "name": path.name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
            }
        )
    manifest = {
        "schema_version": 1,
        "product": "samuel",
        "version": version,
        "tag": tag,
        "commit": commit,
        "artifacts": files,
    }
    target = dist_dir / "release-manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def run_gate(
    *,
    root: Path,
    dist_dir: Path,
    tag: str,
    commit_ref: str,
    mode: str,
    restore_remote_tag: bool = False,
) -> Path:
    if restore_remote_tag:
        if mode != "post-tag":
            raise ReleaseGateError("remote tag restoration is only valid in post-tag mode")
        restore_remote_annotated_tag(root, tag=tag)
    version, commit = verify_source_identity(root, tag=tag, commit_ref=commit_ref, mode=mode)
    verify_version_override(mode=mode, version=version)
    verify_legacy_authority_window(root, version)
    verify_changelog(root, version)
    if mode == "post-tag":
        verify_runtime_surfaces(version)
    artifacts = verify_artifacts(dist_dir, version)
    artifacts.append(materialize_runtime_lock(root, dist_dir, version))
    return write_manifest(
        dist_dir,
        tag=tag,
        version=version,
        commit=commit,
        artifacts=artifacts,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pre-tag", "post-tag"), required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit-ref", default="origin/main")
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--restore-remote-tag",
        action="store_true",
        help="restore and verify the annotated origin tag after checkout rewrote its local ref",
    )
    args = parser.parse_args()

    try:
        manifest = run_gate(
            root=args.root.resolve(),
            dist_dir=args.dist_dir.resolve(),
            tag=args.tag,
            commit_ref=args.commit_ref,
            mode=args.mode,
            restore_remote_tag=args.restore_remote_tag,
        )
    except (OSError, ReleaseGateError, subprocess.SubprocessError) as exc:
        print(f"release gate failed: {exc}", file=sys.stderr)
        return 1

    print(f"release gate passed: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
