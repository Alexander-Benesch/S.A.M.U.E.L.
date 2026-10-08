#!/usr/bin/env python3
"""OCI first-install helper (#970), executed inside the verified release image.

Standard library only: the operator does not need Python on the Docker host.
The sibling samuel-container script supplies only the three installation mounts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any


class ContainerInitError(RuntimeError):
    """The release or first-install layout is inconsistent."""


def read_manifest(path: Path, expected_sha256: str, image: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ContainerInitError("expected manifest SHA-256 must contain 64 lowercase hex digits")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ContainerInitError("manifest SHA-256 mismatch")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ContainerInitError("manifest must be a JSON object")
    container = manifest.get("container")
    version = manifest.get("version")
    revision = manifest.get("commit")
    if (
        manifest.get("schema_version") != 2
        or manifest.get("product") != "samuel"
        or not isinstance(container, dict)
        or not isinstance(version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version)
        or manifest.get("tag") != f"v{version}"
        or not isinstance(revision, str)
        or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision)
    ):
        raise ContainerInitError("unsupported or inconsistent release manifest identity")
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", image)
        or container.get("reference") != image
        or container.get("digest") != image.rsplit("@", 1)[1]
        or container.get("image") != image.rsplit("@", 1)[0]
        or container.get("tag") != manifest["tag"]
        or container.get("platform") != "linux/amd64"
    ):
        raise ContainerInitError("container.reference, digest, tag or platform mismatch")
    return manifest


def verify_runtime(manifest: dict[str, Any]) -> tuple[int, int]:
    if (
        importlib.metadata.version("samuel") != manifest["version"]
        or os.environ.get("SAMUEL_BUILD_REVISION") != manifest["commit"]
        or platform.system() != "Linux"
        or platform.machine() != "x86_64"
    ):
        raise ContainerInitError("image runtime version, revision or platform mismatch")
    return runtime_owner()


def runtime_owner() -> tuple[int, int]:
    """Single ownership source for publisher smoke and operator bootstrap."""
    data = Path("/app/data").stat()
    workspace = Path("/samuel-workspaces").stat()
    owner = (data.st_uid, data.st_gid)
    if owner[0] == 0 or owner[1] == 0 or owner != (workspace.st_uid, workspace.st_gid):
        raise ContainerInitError("image lacks consistent non-root runtime ownership")
    return owner


def verify_delivery(manifest: dict[str, Any], archive: Path, source: Path) -> None:
    """Bind the complete extracted installer and Compose files to release assets."""
    assets = manifest.get("artifacts")
    if not isinstance(assets, list):
        raise ContainerInitError("release manifest lacks installer artifact binding")
    by_name = {item.get("name"): item for item in assets if isinstance(item, dict)}
    if len(by_name) != len(assets):
        raise ContainerInitError("ambiguous release artifact names")
    names = (
        f"samuel-oci-{manifest['version']}.tar.gz",
        "docker-compose.yml",
        "docker-compose.setup.yml",
    )
    for name in names:
        path = archive if name == names[0] else source / name
        item = by_name.get(name)
        if not isinstance(item, dict) or not path.is_file() or path.is_symlink():
            raise ContainerInitError(f"missing release artifact: {name}")
        raw = path.read_bytes()
        if len(raw) != item.get("size") or hashlib.sha256(raw).hexdigest() != item.get("sha256"):
            raise ContainerInitError(f"release artifact binding mismatch: {name}")
    required = {
        "tools/samuel-container",
        "tools/container_init.py",
        "docker-compose.yml",
        "docker-compose.setup.yml",
        "docs/INSTALL.md",
    }
    seen: set[str] = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if member.isdir() and parts and parts[0] == "samuel-oci" and ".." not in parts:
                continue
            if len(parts) < 2 or parts[0] != "samuel-oci" or ".." in parts or not member.isfile():
                raise ContainerInitError("installer archive contains an unsafe member")
            relative = "/".join(parts[1:])
            if relative in seen:
                raise ContainerInitError("installer archive contains duplicate members")
            seen.add(relative)
            path = source / relative
            stream = bundle.extractfile(member)
            if (
                path.is_symlink()
                or not path.is_file()
                or stream is None
                or path.read_bytes() != stream.read()
            ):
                raise ContainerInitError(f"extracted installer differs from release: {relative}")
    if not required <= seen:
        raise ContainerInitError("release installer is incomplete")


def verify_image_inspect(manifest: dict[str, Any], inspect: Any, owner: tuple[int, int]) -> None:
    if not isinstance(inspect, list) or len(inspect) != 1 or not isinstance(inspect[0], dict):
        raise ContainerInitError("expected one inspected image")
    item = inspect[0]
    labels = item.get("Config", {}).get("Labels") or {}
    if (
        labels.get("org.opencontainers.image.version") != manifest["version"]
        or labels.get("org.opencontainers.image.revision") != manifest["commit"]
        or f"{item.get('Os')}/{item.get('Architecture')}" != manifest["container"]["platform"]
        or manifest["container"]["reference"] not in (item.get("RepoDigests") or [])
        or (os.getuid(), os.getgid()) != owner
    ):
        raise ContainerInitError("OCI identity or default runtime user mismatch")


def _regular_tree(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ContainerInitError(f"unexpected symlink or special file: {path.name}")


def _write(path: Path, content: str, *, owner: tuple[int, int], mode: int = 0o600) -> None:
    with path.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), mode)
        os.fchown(stream.fileno(), *owner)
        stream.write(content)


def _compose_environment(receipt: dict[str, Any]) -> str:
    variables = {
        "SAMUEL_IMAGE": receipt["image"],
        "SAMUEL_ENV_FILE": f"{receipt['config_root']}/.env",
        "SAMUEL_CONFIG_DIR": f"{receipt['config_root']}/config",
        "SAMUEL_DATA_DIR": receipt["data_root"],
        "SAMUEL_WORK_DIR": receipt["work_root"],
        "SAMUEL_LOG_DIR": receipt["log_root"],
        "SAMUEL_BACKUP_DIR": receipt["backup_root"],
        "SAMUEL_DASHBOARD_BIND": "127.0.0.1",
        "SAMUEL_DASHBOARD_PORT": str(receipt["port"]),
        "COMPOSE_PROJECT_NAME": receipt["project"],
    }
    return "".join(f"{key}={value}\n" for key, value in variables.items())


def initialize(
    *,
    manifest: dict[str, Any],
    manifest_sha256: str,
    config_root: Path,
    data_root: Path,
    work_root: Path,
    defaults: Path,
    compose_source: Path,
    host_config_root: str,
    host_data_root: str,
    host_work_root: str,
    port: int,
    project: str,
    owner: tuple[int, int],
    log_root: Path | None = None,
    backup_root: Path | None = None,
    host_log_root: str | None = None,
    host_backup_root: str | None = None,
) -> str:
    roots = (config_root, data_root, work_root) + tuple(
        p for p in (log_root, backup_root) if p is not None
    )
    if not 1 <= port <= 65535 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
        raise ContainerInitError("invalid dashboard port or Compose project name")
    for value in (
        host_config_root,
        host_data_root,
        host_work_root,
        host_log_root or host_data_root + "/logs",
        host_backup_root or host_data_root + "/backups",
    ):
        if not re.fullmatch(r"/[A-Za-z0-9/._-]+", value) or ".." in Path(value).parts:
            raise ContainerInitError(
                "host paths must be absolute without traversal or special characters"
            )
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            raise ContainerInitError("installation mounts must be regular directories")
    receipt = {
        "manifest_sha256": manifest_sha256,
        "version": manifest["version"],
        "revision": manifest["commit"],
        "image": manifest["container"]["reference"],
        "config_root": host_config_root,
        "data_root": host_data_root,
        "work_root": host_work_root,
        "log_root": host_log_root or host_data_root + "/logs",
        "backup_root": host_backup_root or host_data_root + "/backups",
        "stage": "initialized",
        "port": port,
        "project": project,
        "uid": owner[0],
        "gid": owner[1],
    }
    receipt_path = config_root / ".container-install.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        if receipt_path.is_symlink() or json.loads(receipt_path.read_text()) != receipt:
            raise ContainerInitError("existing installation binding differs; init is not an update")
        expected = [config_root / ".env", config_root / "compose.env"]
        expected += [
            config_root / "compose" / name
            for name in ("docker-compose.yml", "docker-compose.setup.yml")
        ]
        if not all(path.is_file() and not path.is_symlink() for path in expected):
            raise ContainerInitError("existing installation is incomplete")
        for root in (*roots, config_root / "config"):
            if (
                root.is_symlink()
                or not root.is_dir()
                or (root.stat().st_uid, root.stat().st_gid) != owner
            ):
                raise ContainerInitError("existing installation directory ownership differs")
        env = config_root / ".env"
        if env.stat().st_mode & 0o077 or (env.stat().st_uid, env.stat().st_gid) != owner:
            raise ContainerInitError("existing operator .env permissions differ")
        if (config_root / "compose.env").read_text() != _compose_environment(receipt):
            raise ContainerInitError("installed Compose environment differs from release binding")
        for name in ("docker-compose.yml", "docker-compose.setup.yml"):
            if (config_root / "compose" / name).read_bytes() != (
                compose_source / name
            ).read_bytes():
                raise ContainerInitError("installed Compose file differs from release binding")
        return "already_initialized"
    if any(any(root.iterdir()) for root in roots):
        raise ContainerInitError(
            "first-install paths must be empty; refusing to overwrite existing files"
        )
    _regular_tree(defaults)
    for name in ("docker-compose.yml", "docker-compose.setup.yml"):
        source = compose_source / name
        if not source.is_file() or source.is_symlink():
            raise ContainerInitError("installer lacks shipped Compose files")
    # No mutation occurs before the complete input/empty-layout checks above.
    for root in roots:
        root.chmod(0o750 if root == config_root else 0o700)
        os.chown(root, *owner)
    config = config_root / "config"
    shutil.copytree(defaults, config)
    for path in [config, *config.rglob("*")]:
        os.chown(path, *owner)
        path.chmod(0o700 if path.is_dir() else 0o600)
    # Bind image defaults explicitly to container paths, never host paths.
    agent_path = config / "agent.json"
    agent = json.loads(agent_path.read_text())
    agent.update(config_dir="/app/config", data_dir="/app/data")
    agent["workspace"]["work_dir"] = "/samuel-workspaces"
    agent_path.write_text(json.dumps(agent, indent=2) + "\n")
    for name in ("logs", "backups"):
        path = data_root / name
        path.mkdir(mode=0o700)
        os.chown(path, *owner)
    _write(
        config_root / ".env", "# Operator environment; configure using samuel setup.\n", owner=owner
    )
    compose_dir = config_root / "compose"
    compose_dir.mkdir(mode=0o700)
    for name in ("docker-compose.yml", "docker-compose.setup.yml"):
        _write(
            compose_dir / name,
            (compose_source / name).read_text(),
            owner=(os.getuid(), os.getgid()),
        )
    _write(
        config_root / "compose.env",
        _compose_environment(receipt),
        owner=(os.getuid(), os.getgid()),
    )
    _write(receipt_path, json.dumps(receipt, indent=2) + "\n", owner=(os.getuid(), os.getgid()))
    return "initialized"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "init", "prepare-smoke", "prepare-toolchain"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--image")
    parser.add_argument("--installer-archive", type=Path)
    parser.add_argument("--installer-source", type=Path, default=Path("/bootstrap/source"))
    parser.add_argument("--config-root", default="/etc/samuel")
    parser.add_argument("--data-root", default="/var/lib/samuel")
    parser.add_argument("--work-root", default="/srv/samuel/workspaces")
    parser.add_argument("--log-root", default="/var/log/samuel")
    parser.add_argument("--backup-root", default="/srv/samuel/backups")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--project", default="samuel")
    parser.add_argument("--requirements-lock", type=Path)
    parser.add_argument("--lock-sha256")
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--host-toolchain-root")
    args = parser.parse_args()
    try:
        if args.command == "prepare-smoke":
            owner = runtime_owner()
            for path in (
                Path("/prepare/data"),
                Path("/prepare/workspaces"),
                Path("/prepare/data/logs"),
                Path("/prepare/data/backups"),
            ):
                path.mkdir(exist_ok=True)
                os.chown(path, *owner)
                path.chmod(0o700)
            return 0
        if not args.manifest or not args.manifest_sha256 or not args.image:
            raise ContainerInitError("manifest, checksum and image are required")
        manifest = read_manifest(args.manifest, args.manifest_sha256, args.image)
        if args.installer_archive:
            verify_delivery(manifest, args.installer_archive, args.installer_source)
        owner = verify_runtime(manifest)
        if args.command == "verify":
            verify_image_inspect(manifest, json.load(sys.stdin), owner)
            print("release identity and non-root image ownership verified")
        else:
            result = initialize(
                manifest=manifest,
                manifest_sha256=args.manifest_sha256,
                config_root=Path("/prepare/config-root"),
                data_root=Path("/prepare/data"),
                work_root=Path("/prepare/workspaces"),
                defaults=Path("/app/config"),
                compose_source=Path("/bootstrap"),
                host_config_root=args.config_root,
                host_data_root=args.data_root,
                host_work_root=args.work_root,
                port=args.port,
                project=args.project,
                owner=owner,
                log_root=Path("/prepare/logs"),
                backup_root=Path("/prepare/backups"),
                host_log_root=args.log_root,
                host_backup_root=args.backup_root,
            )
            print(result)
            registration = Path("/prepare/config-root/.verifier-toolchain.json")
            override = Path("/prepare/config-root/compose/docker-compose.toolchain.yml")
            if (
                args.command == "prepare-toolchain"
                or registration.exists()
                or override.exists()
                or registration.is_symlink()
                or override.is_symlink()
            ):
                from samuel.verifier_toolchain import (
                    prepare_toolchain,
                    register_toolchain,
                    verify_registration,
                )

                verify_registration(Path("/prepare/config-root"))
            if args.command == "prepare-toolchain":
                if (
                    not args.requirements_lock
                    or not args.lock_sha256
                    or not args.wheelhouse
                    or not args.host_toolchain_root
                ):
                    raise ContainerInitError(
                        "toolchain lock, digest, wheelhouse and host directory required"
                    )
                binding = prepare_toolchain(
                    root=Path("/opt/samuel-verifier"),
                    lock=args.requirements_lock,
                    lock_sha256=args.lock_sha256,
                    wheelhouse=args.wheelhouse,
                    runtime_image=args.image,
                )
                register_toolchain(Path("/prepare/config-root"), args.host_toolchain_root, binding)
                print("Python verifier toolchain prepared and registered: " + binding["sha256"])
    except (ContainerInitError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"container init failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
