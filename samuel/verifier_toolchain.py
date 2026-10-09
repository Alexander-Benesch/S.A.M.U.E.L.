"""Explicit OCI operator preparation; never called by planning or candidate tests."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from samuel.core.config import VerifierToolchainSchema
from samuel.core.process_environment import verifier_process_environment
from samuel.core.test_runner import artifact_files, python_identity, validate_toolchain


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
    for entry in root.rglob("*"):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)
    return {"manifest": str(path), "sha256": digest}


def register_toolchain(config_root: Path, host_root: str, binding: dict[str, Any]) -> None:
    """Register only after preparation; source config and installed Compose remain canonical."""
    if not re.fullmatch(r"/[A-Za-z0-9/._-]+", host_root) or ".." in Path(host_root).parts:
        raise ValueError("invalid absolute host toolchain directory")
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
    content = (
        "services:\n  samuel:\n    volumes:\n      - type: bind\n"
        f"        source: {host_root}\n        target: /opt/samuel-verifier\n"
        "        read_only: true\n        bind:\n          create_host_path: false\n"
    )
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


def verify_registration(config_root: Path) -> None:
    receipt = config_root / ".verifier-toolchain.json"
    override = config_root / "compose" / "docker-compose.toolchain.yml"
    if not receipt.exists() and not override.exists():
        return
    if (
        receipt.is_symlink()
        or override.is_symlink()
        or not receipt.is_file()
        or not override.is_file()
    ):
        raise ValueError("toolchain registration is incomplete or unsafe")
    data = json.loads(receipt.read_text())
    if hashlib.sha256(override.read_bytes()).hexdigest() != data["compose_sha256"]:
        raise ValueError("registered toolchain Compose mount changed")
    evaluation = json.loads((config_root / "config" / "eval.json").read_text())
    if evaluation.get("verifier_toolchain") != data["binding"]:
        raise ValueError("registered toolchain policy binding changed")
