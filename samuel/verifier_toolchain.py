"""Explicit OCI operator preparation; never called by planning or candidate tests."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from samuel.core.config import VerifierToolchainSchema
from samuel.core.process_environment import verifier_process_environment
from samuel.core.test_runner import artifact_files, python_identity, validate_toolchain


def prepare_toolchain_for_release(
    *,
    root: Path,
    previous: VerifierToolchainSchema,
    source_version: str,
    source_revision: str,
    source_image: str,
    target_image: str,
) -> dict[str, Any]:
    """Recheck immutable inputs for the target runtime; preserve the old tree.

    This operator-only preparation neither registers the result nor transfers
    workflow/test evidence. Activation still requires the independent installer
    checks and the actual target-runtime runner/readiness proof.
    """
    from samuel.build_info import product_tag_sort_key
    from samuel.core.test_runner import _read_toolchain_manifest, _validate_toolchain_contents

    if (
        any(parent.is_symlink() for parent in (root, *root.parents))
        or not root.is_dir()
        or any(root.iterdir())
    ):
        raise ValueError("toolchain output must be an empty regular directory")
    manifest = _read_toolchain_manifest(previous)
    identity = python_identity()
    before = {**identity, "runtime_version": source_version, "runtime_revision": source_revision}
    old_order = product_tag_sort_key(f"v{source_version}")
    new_order = product_tag_sort_key(f"v{identity['runtime_version']}")
    image_pattern = r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}"
    if (
        old_order is None
        or new_order is None
        or new_order <= old_order
        or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_revision) is None
        or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", identity["runtime_revision"]) is None
        or re.fullmatch(image_pattern, source_image) is None
        or re.fullmatch(image_pattern, target_image) is None
        or source_image == target_image
    ):
        raise ValueError("toolchain transition requires distinct immutable release identities")
    if manifest.get("python") != before or manifest.get("runtime_image") != source_image:
        raise ValueError("source toolchain identity or Python/platform compatibility differs")
    previous_path = Path(previous.manifest)
    source_root, target_root = previous_path.parent.resolve(), root.resolve()
    if (
        source_root == target_root
        or source_root in target_root.parents
        or target_root in source_root.parents
    ):
        raise ValueError("source and target toolchain directories must not overlap")
    _validate_toolchain_contents(previous_path, manifest)
    # Reuse only already verified package bytes. No network, resolver, install
    # hook or candidate source is consulted. Failures leave a visible partial
    # staging directory; the previous registration and packages stay untouched.
    shutil.copytree(previous_path.parent / "packages", root / "packages")
    shutil.copyfile(previous_path.parent / "requirements.lock", root / "requirements.lock")
    manifest.update(python=identity, runtime_image=target_image)
    path = root / "toolchain-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    validate_toolchain(VerifierToolchainSchema(manifest=str(path), sha256=digest))
    _seal_toolchain(root)
    return {"manifest": str(path), "sha256": digest}


def _seal_toolchain(root: Path) -> None:
    for entry in root.rglob("*"):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


def prepare_toolchain(
    *, root: Path, lock: Path, lock_sha256: str, wheelhouse: Path, runtime_image: str | None = None
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", lock_sha256):
        raise ValueError("invalid toolchain lock SHA-256")
    if root.is_symlink() or not root.is_dir() or any(root.iterdir()):
        raise ValueError("toolchain output must be an empty regular directory")
    if lock.is_symlink() or not lock.is_file():
        raise ValueError("toolchain requirements lock must be a regular file")
    raw = lock.read_bytes()
    if hashlib.sha256(raw).hexdigest() != lock_sha256:
        raise ValueError("toolchain requirements lock digest mismatch")
    # Only exact index-style pins and SHA-256 hashes; no URLs, includes, options,
    # editable sources or candidate build hooks can enter this offline operation.
    entries = [
        line.strip()
        for line in raw.decode().replace("\\\n", " ").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    pattern = r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+(?:\s+--hash=sha256:[0-9a-f]{64})+"
    if not entries or any(re.fullmatch(pattern, entry) is None for entry in entries):
        raise ValueError("toolchain lock requires exact pins with SHA-256 hashes only")
    if wheelhouse.is_symlink() or not wheelhouse.is_dir():
        raise ValueError("toolchain wheelhouse must be a regular directory")
    if any(
        path.is_symlink() or not path.is_file() or path.suffix != ".whl"
        for path in wheelhouse.iterdir()
    ):
        raise ValueError("toolchain wheelhouse accepts regular wheel files only")
    (root / "requirements.lock").write_bytes(raw)
    with verifier_process_environment(sys.executable) as environment:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "install",
                "--no-cache-dir",
                "--no-index",
                "--require-hashes",
                "--no-compile",
                "--only-binary=:all:",
                "--find-links",
                str(wheelhouse),
                "--target",
                str(root / "packages"),
                "-r",
                str(root / "requirements.lock"),
            ],
            cwd=str(root),
            env=environment,
            capture_output=True,
            timeout=300,
            check=False,
        )
    if result.returncode:
        raise ValueError(
            "offline hash-locked toolchain installation failed; output preserved for inspection"
        )
    manifest = {
        "schema_version": 1,
        "runtime_image": runtime_image,
        "python": python_identity(),
        "lock_sha256": lock_sha256,
        "distributions": {
            dist.metadata["Name"]: dist.version
            for dist in importlib.metadata.distributions(path=[str(root / "packages")])
        },
        "files": artifact_files(root / "packages"),
    }
    path = root / "toolchain-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    validate_toolchain(VerifierToolchainSchema(manifest=str(path), sha256=digest))
    _seal_toolchain(root)
    return {"manifest": str(path), "sha256": digest}


def toolchain_overlay(host_root: str) -> str:
    """The fixed existing read-only mount; never a caller-authored Compose job."""
    if (
        not isinstance(host_root, str)
        or not re.fullmatch(r"/[A-Za-z0-9/._-]+", host_root)
        or ".." in Path(host_root).parts
        or str(Path(host_root)) != host_root
    ):
        raise ValueError("invalid absolute host toolchain directory")
    return (
        "services:\n  samuel:\n    volumes:\n      - type: bind\n"
        f"        source: {host_root}\n        target: /opt/samuel-verifier\n"
        "        read_only: true\n        bind:\n          create_host_path: false\n"
    )


def register_toolchain(config_root: Path, host_root: str, binding: dict[str, Any]) -> None:
    """Register only after preparation; source config and installed Compose remain canonical."""
    content = toolchain_overlay(host_root)
    evaluation_path = config_root / "config" / "eval.json"
    if (
        evaluation_path.is_symlink()
        or not evaluation_path.is_file()
        or evaluation_path.parent.is_symlink()
    ):
        raise ValueError("operator evaluation configuration must be a regular file")
    override = config_root / "compose" / "docker-compose.toolchain.yml"
    receipt = config_root / ".verifier-toolchain.json"
    if override.exists() or receipt.exists() or override.is_symlink() or receipt.is_symlink():
        raise ValueError(
            "toolchain already registered; replacement requires a new installation binding"
        )
    evaluation = json.loads(evaluation_path.read_text())
    if evaluation.get("verifier_toolchain"):
        raise ValueError("existing verifier toolchain configuration is preserved")
    evaluation["verifier_toolchain"] = binding
    receipt.write_text(
        json.dumps(
            {
                "binding": binding,
                "host_root": host_root,
                "compose_sha256": hashlib.sha256(content.encode()).hexdigest(),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    override.write_text(content)
    temporary = evaluation_path.with_suffix(".json.toolchain-prepared")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(evaluation, indent=2) + "\n")
    metadata = evaluation_path.stat()
    import os

    os.chown(temporary, metadata.st_uid, metadata.st_gid)
    temporary.chmod(metadata.st_mode & 0o777)
    temporary.replace(evaluation_path)


def verify_registration(config_root: Path) -> dict[str, Any] | None:
    from samuel.core.project_binding import regular_path

    receipt = config_root / ".verifier-toolchain.json"
    override = config_root / "compose" / "docker-compose.toolchain.yml"
    if not any(path.exists() or path.is_symlink() for path in (receipt, override)):
        return None
    if (
        not regular_path(receipt)
        or not regular_path(override)
        or not receipt.is_file()
        or not override.is_file()
    ):
        raise ValueError("toolchain registration is incomplete or unsafe")
    data = json.loads(receipt.read_text())
    if not isinstance(data, dict) or set(data) != {"binding", "host_root", "compose_sha256"}:
        raise ValueError("invalid toolchain registration fields")
    expected = toolchain_overlay(data["host_root"]).encode()
    if (
        override.read_bytes() != expected
        or hashlib.sha256(expected).hexdigest() != data["compose_sha256"]
    ):
        raise ValueError("registered toolchain Compose mount changed")
    evaluation_path = config_root / "config" / "eval.json"
    if not regular_path(evaluation_path) or not evaluation_path.is_file():
        raise ValueError("registered toolchain policy path is unsafe")
    evaluation = json.loads(evaluation_path.read_text())
    if evaluation.get("verifier_toolchain") != data["binding"]:
        raise ValueError("registered toolchain policy binding changed")
    return data
