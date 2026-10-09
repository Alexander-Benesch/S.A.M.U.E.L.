#!/usr/bin/env python3
"""Generate the hash-bound Linux container locks and their review contract (#555)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 maintainer path
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("containers/lock-policy.json")
RUNTIME_LOCK_PATH = Path("requirements-container.lock")
BUILD_LOCK_PATH = Path("requirements-container-build.lock")

UV_VERSION = "0.12.6"
PYTHON_VERSION = "3.10"
PYTHON_PLATFORM = "x86_64-unknown-linux-gnu"
RUNTIME_EXTRAS = ("dashboard", "llm", "github", "tree-sitter")

INITIAL_BASE_IMAGE = {
    "reference": (
        "python:3.10-slim@sha256:bb5bd66c26727f4f5b5557f24fb6024d57e44c22e6c81bcec522777bad8ac586"
    ),
    "platform": "linux/amd64",
    "platform_manifest_digest": (
        "sha256:41879110355be910760dc900311985910a539646a4855183ae741062c107a340"
    ),
    "verified_at": "2026-08-27T14:05:00Z",
}

INITIAL_SYSTEM_PACKAGES = {
    "provider": "debian-snapshot",
    "snapshot": "20260824T000000Z",
    "repositories": [
        "http://snapshot.debian.org/archive/debian/20260824T000000Z",
        "http://snapshot.debian.org/archive/debian-security/20260824T000000Z",
    ],
    "packages": {"git": "1:2.47.3-0+deb13u1"},
    "runtime_versions": {"git": "2.47.3"},
}


class ContainerLockError(RuntimeError):
    """The declared lock inputs or generator are invalid."""


def _sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _read_pyproject(root: Path) -> dict[str, Any]:
    with (root / "pyproject.toml").open("rb") as stream:
        document = tomllib.load(stream)
    if not isinstance(document, dict):
        raise ContainerLockError("pyproject.toml must contain a TOML table")
    return document


def lock_inputs(root: Path = ROOT) -> dict[str, Any]:
    """Return the canonical build/runtime inputs covered by the lock contract."""

    document = _read_pyproject(root)
    project = document.get("project")
    build_system = document.get("build-system")
    if not isinstance(project, dict) or not isinstance(build_system, dict):
        raise ContainerLockError("pyproject.toml must define project and build-system tables")

    dependencies = project.get("dependencies")
    optional = project.get("optional-dependencies")
    build_requirements = build_system.get("requires")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise ContainerLockError("project.dependencies must be a string list")
    if not isinstance(optional, dict):
        raise ContainerLockError("project.optional-dependencies must be a table")
    if not isinstance(build_requirements, list) or not all(
        isinstance(item, str) for item in build_requirements
    ):
        raise ContainerLockError("build-system.requires must be a string list")

    runtime_requirements = list(dependencies)
    for extra in RUNTIME_EXTRAS:
        values = optional.get(extra)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ContainerLockError(f"project.optional-dependencies.{extra} must be a string list")
        runtime_requirements.extend(values)

    return {
        "python_version": PYTHON_VERSION,
        "python_platform": PYTHON_PLATFORM,
        "runtime_extras": list(RUNTIME_EXTRAS),
        "runtime_requirements": runtime_requirements,
        "build_requirements": list(build_requirements),
    }


def lock_source_digest(inputs: dict[str, Any]) -> str:
    canonical = json.dumps(inputs, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return _sha256_bytes(canonical.encode("utf-8"))


def _verify_uv() -> None:
    completed = subprocess.run(  # noqa: S603 - current interpreter and fixed module/arguments
        [sys.executable, "-m", "uv", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    expected = f"uv {UV_VERSION} "
    if completed.returncode != 0 or not completed.stdout.startswith(expected):
        detail = completed.stderr.strip() or completed.stdout.strip() or "uv is unavailable"
        raise ContainerLockError(f"lock generation requires uv {UV_VERSION}: {detail}")


def _compile_lock(
    *,
    requirements: list[str],
    destination: Path,
    exclude_newer: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="samuel-container-lock-") as temporary:
        input_path = Path(temporary) / "requirements.in"
        output_path = Path(temporary) / destination.name
        input_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "compile",
            str(input_path),
            "--output-file",
            str(output_path),
            "--python-version",
            PYTHON_VERSION,
            "--python-platform",
            PYTHON_PLATFORM,
            "--generate-hashes",
            "--only-binary",
            ":all:",
            "--no-annotate",
            "--no-python-downloads",
            "--exclude-newer",
            exclude_newer,
            "--custom-compile-command",
            "python tools/update_container_locks.py",
        ]
        completed = subprocess.run(  # noqa: S603 - structured fixed tool invocation
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "uv compile failed"
            raise ContainerLockError(f"cannot generate {destination.name}: {detail}")
        destination.write_bytes(output_path.read_bytes())


def _existing_base_image(root: Path) -> dict[str, Any]:
    policy_path = root / POLICY_PATH
    if not policy_path.exists():
        return dict(INITIAL_BASE_IMAGE)
    try:
        document = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContainerLockError(f"cannot preserve base-image policy: {exc}") from exc
    base_image = document.get("base_image")
    if not isinstance(base_image, dict):
        raise ContainerLockError("existing lock policy has no base_image object")
    return base_image


def _existing_system_packages(root: Path) -> dict[str, Any]:
    policy_path = root / POLICY_PATH
    if not policy_path.exists():
        return dict(INITIAL_SYSTEM_PACKAGES)
    try:
        document = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContainerLockError(f"cannot preserve system-package policy: {exc}") from exc
    system_packages = document.get("system_packages")
    if not isinstance(system_packages, dict):
        raise ContainerLockError("existing lock policy has no system_packages object")
    return system_packages


def generate(*, root: Path = ROOT, exclude_newer: str) -> None:
    _verify_uv()
    inputs = lock_inputs(root)
    runtime_lock = root / RUNTIME_LOCK_PATH
    build_lock = root / BUILD_LOCK_PATH
    _compile_lock(
        requirements=inputs["runtime_requirements"],
        destination=runtime_lock,
        exclude_newer=exclude_newer,
    )
    _compile_lock(
        requirements=inputs["build_requirements"],
        destination=build_lock,
        exclude_newer=exclude_newer,
    )

    policy = {
        "schema_version": 1,
        "base_image": _existing_base_image(root),
        "system_packages": _existing_system_packages(root),
        "lock_contract": {
            "generator": f"uv=={UV_VERSION}",
            "exclude_newer": exclude_newer,
            **inputs,
            "source_digest": lock_source_digest(inputs),
            "runtime_lock": {
                "path": RUNTIME_LOCK_PATH.as_posix(),
                "sha256": _sha256_bytes(runtime_lock.read_bytes()),
            },
            "build_lock": {
                "path": BUILD_LOCK_PATH.as_posix(),
                "sha256": _sha256_bytes(build_lock.read_bytes()),
            },
        },
    }
    policy_path = root / POLICY_PATH
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exclude-newer",
        required=True,
        help="RFC 3339 package upload cutoff recorded in the lock policy",
    )
    args = parser.parse_args()
    try:
        generate(exclude_newer=args.exclude_newer)
    except (ContainerLockError, OSError, subprocess.SubprocessError) as exc:
        print(f"container lock update failed: {exc}", file=sys.stderr)
        return 1
    print(f"container locks updated with uv {UV_VERSION}: {POLICY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
