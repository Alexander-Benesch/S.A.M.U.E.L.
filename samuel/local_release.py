#!/usr/bin/env python3
"""Stage and atomically activate a manifest-bound local S.A.M.U.E.L. release.

This is deliberately a small installation boundary, not a package manager or
service orchestrator.  It never updates a release in place and never mutates
an existing operator configuration, runtime state, workspace or extension.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path
from typing import Any


class LocalReleaseError(RuntimeError):
    """A local release cannot be staged or activated safely."""


_FULL_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_PRODUCT_VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:(?:a|b|rc)(?:0|[1-9]\d*))?\Z"
)
_RECEIPT = "release.json"


@dataclass(frozen=True)
class ReleaseLayout:
    """Explicit immutable and persistent path classes for a local deployment."""

    install_root: Path = Path("/opt/samuel")
    config_root: Path = Path("/etc/samuel")
    data_root: Path = Path("/var/lib/samuel")
    log_root: Path = Path("/var/log/samuel")
    service_root: Path = Path("/srv/samuel")

    @property
    def releases_root(self) -> Path:
        return self.install_root / "releases"

    @property
    def current(self) -> Path:
        return self.install_root / "current"

    @property
    def config_dir(self) -> Path:
        return self.config_root / "config"

    @property
    def workspaces_root(self) -> Path:
        return self.service_root / "workspaces"

    @property
    def extensions_root(self) -> Path:
        return self.service_root / "extensions"

    @property
    def backups_root(self) -> Path:
        return self.service_root / "backups"

    def validated(self) -> ReleaseLayout:
        roots = {
            "install": self.install_root,
            "config": self.config_root,
            "data": self.data_root,
            "log": self.log_root,
            "service": self.service_root,
        }
        normalized: dict[str, Path] = {}
        for name, path in roots.items():
            expanded = path.expanduser()
            if not expanded.is_absolute():
                raise LocalReleaseError(f"{name} root must be absolute: {path}")
            if expanded.is_symlink():
                raise LocalReleaseError(f"{name} root must not be a symlink: {path}")
            resolved = expanded.resolve(strict=False)
            if resolved == Path("/"):
                raise LocalReleaseError(f"{name} root must not be /")
            normalized[name] = resolved
        for left_name, left in normalized.items():
            for right_name, right in normalized.items():
                if left_name >= right_name:
                    continue
                if left == right or left in right.parents or right in left.parents:
                    raise LocalReleaseError(
                        f"deployment roots must not overlap: {left_name}={left}, "
                        f"{right_name}={right}"
                    )
        return ReleaseLayout(
            install_root=normalized["install"],
            config_root=normalized["config"],
            data_root=normalized["data"],
            log_root=normalized["log"],
            service_root=normalized["service"],
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalReleaseError(f"cannot read {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LocalReleaseError(f"{description} must be a JSON object: {path}")
    return value


def _manifest_artifact(manifest: Mapping[str, Any], path: Path) -> dict[str, Any]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise LocalReleaseError("release manifest has no artifact list")
    matches = [
        item for item in artifacts if isinstance(item, dict) and item.get("name") == path.name
    ]
    if len(matches) != 1:
        raise LocalReleaseError(f"release manifest must bind exactly one {path.name} artifact")
    item = matches[0]
    expected_digest = item.get("sha256")
    expected_size = item.get("size")
    if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise LocalReleaseError(f"release manifest has an invalid digest for {path.name}")
    if not isinstance(expected_size, int) or expected_size < 0:
        raise LocalReleaseError(f"release manifest has an invalid size for {path.name}")
    actual_size = path.stat().st_size
    actual_digest = _sha256(path)
    if actual_size != expected_size or actual_digest != expected_digest:
        raise LocalReleaseError(f"artifact does not match release manifest: {path.name}")
    return item


def _wheel_identity(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise LocalReleaseError(f"wheel has {len(names)} METADATA entries: {path.name}")
            metadata = BytesParser().parsebytes(archive.read(names[0]))
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise LocalReleaseError(f"cannot read wheel metadata {path}: {exc}") from exc
    name = str(metadata.get("Name") or "").strip().lower().replace("_", "-")
    version = str(metadata.get("Version") or "").strip()
    if name != "samuel" or not version:
        raise LocalReleaseError(f"wheel is not the S.A.M.U.E.L. distribution: {path.name}")
    return name, version


def validate_release_inputs(
    *, manifest_path: Path, wheel_path: Path, runtime_lock_path: Path
) -> dict[str, str]:
    """Bind the local install to one release manifest, wheel, lock and revision."""

    for path, description in (
        (manifest_path, "release manifest"),
        (wheel_path, "wheel"),
        (runtime_lock_path, "runtime lock"),
    ):
        if not path.is_file() or path.is_symlink():
            raise LocalReleaseError(f"{description} must be a regular file: {path}")

    manifest = _read_json(manifest_path, "release manifest")
    if manifest.get("schema_version") not in {1, 2} or manifest.get("product") != "samuel":
        raise LocalReleaseError("unsupported release manifest identity")
    version = manifest.get("version")
    tag = manifest.get("tag")
    revision = manifest.get("commit")
    if not isinstance(version, str) or _PRODUCT_VERSION.fullmatch(version) is None:
        raise LocalReleaseError("release manifest has no canonical product version")
    if tag != f"v{version}":
        raise LocalReleaseError("release manifest tag and version differ")
    if not isinstance(revision, str) or _FULL_REVISION.fullmatch(revision) is None:
        raise LocalReleaseError("release manifest has no full source revision")
    expected_lock_name = f"samuel-runtime-{version}.lock"
    if runtime_lock_path.name != expected_lock_name:
        raise LocalReleaseError(
            f"runtime lock must use the version-bound name {expected_lock_name!r}"
        )

    _manifest_artifact(manifest, wheel_path)
    _manifest_artifact(manifest, runtime_lock_path)
    _, wheel_version = _wheel_identity(wheel_path)
    if wheel_version != version:
        raise LocalReleaseError(
            f"wheel version {wheel_version!r} differs from manifest version {version!r}"
        )
    return {
        "version": version,
        "revision": revision,
        "wheel_sha256": _sha256(wheel_path),
        "runtime_lock_sha256": _sha256(runtime_lock_path),
        "manifest_sha256": _sha256(manifest_path),
    }


def initialize_layout(layout: ReleaseLayout, defaults_dir: Path) -> None:
    """Initialize persistent roots once; never merge over operator configuration."""

    layout = layout.validated()
    if not defaults_dir.is_dir() or defaults_dir.is_symlink():
        raise LocalReleaseError(f"defaults directory is unavailable: {defaults_dir}")
    if layout.config_root.exists() and any(layout.config_root.iterdir()):
        raise LocalReleaseError(
            f"configuration root is not empty; refusing to merge defaults: {layout.config_root}"
        )

    layout.config_dir.mkdir(parents=True, mode=0o750, exist_ok=True)
    for source in sorted(defaults_dir.rglob("*")):
        relative = source.relative_to(defaults_dir)
        if relative.as_posix() in {"license.json", "license.local.json"}:
            continue
        target = layout.config_dir / relative
        if source.is_symlink():
            raise LocalReleaseError(f"default configuration must not contain symlinks: {source}")
        if source.is_dir():
            target.mkdir(mode=0o750, exist_ok=True)
        elif source.is_file():
            target.write_bytes(source.read_bytes())
            target.chmod(0o640)

    agent_path = layout.config_dir / "agent.json"
    agent = _read_json(agent_path, "default agent configuration")
    workspace = agent.get("workspace")
    if not isinstance(workspace, dict):
        raise LocalReleaseError("default agent configuration has no workspace object")
    agent["config_dir"] = str(layout.config_dir)
    agent["data_dir"] = str(layout.data_root)
    agent["log_file"] = str(layout.log_root / "samuel.log")
    workspace["work_dir"] = str(layout.workspaces_root)
    agent_path.write_text(json.dumps(agent, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    agent_path.chmod(0o640)

    audit_path = layout.config_dir / "audit.json"
    audit = _read_json(audit_path, "default audit configuration")
    sinks = audit.get("sinks")
    if not isinstance(sinks, list):
        raise LocalReleaseError("default audit configuration has no sinks list")
    for sink in sinks:
        if not isinstance(sink, dict):
            raise LocalReleaseError("default audit sink must be an object")
        if sink.get("type") == "jsonl":
            sink["path"] = str(layout.data_root / "logs" / "agent.jsonl")
        elif sink.get("type") == "sarif":
            sink["path"] = str(layout.data_root / "logs" / "findings.sarif")
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    audit_path.chmod(0o640)

    privacy_path = layout.config_dir / "privacy.json"
    privacy = _read_json(privacy_path, "default privacy configuration")
    retention = privacy.get("retention")
    if not isinstance(retention, dict):
        raise LocalReleaseError("default privacy configuration has no retention object")
    retention["managed_backup_dir"] = str(layout.backups_root)
    privacy_path.write_text(
        json.dumps(privacy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    privacy_path.chmod(0o640)

    for root, mode in (
        (layout.releases_root, 0o755),
        (layout.data_root, 0o750),
        (layout.data_root / "logs", 0o750),
        (layout.log_root, 0o750),
        (layout.service_root, 0o755),
        (layout.workspaces_root, 0o750),
        (layout.extensions_root, 0o750),
        (layout.backups_root, 0o750),
    ):
        root.mkdir(parents=True, mode=mode, exist_ok=True)


def _child_environment(revision: str | None = None) -> dict[str, str]:
    allowed = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "LANG",
            "LC_ALL",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
        }
    }
    allowed.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    if revision:
        allowed["SAMUEL_BUILD_REVISION"] = revision
        allowed["SAMUEL_BUILD_DIRTY"] = "0"
    return allowed


def _run(
    command: Sequence[str], *, cwd: Path, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(  # noqa: S603 - structured operator artifacts and fixed tools
        list(command),
        cwd=cwd,
        env=dict(env),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "command failed"
        raise LocalReleaseError(f"release staging command failed: {detail}")
    return completed


def _write_launcher(path: Path, *, revision: str) -> None:
    content = f"""#!/bin/sh
set -eu
export SAMUEL_BUILD_REVISION='{revision}'
export SAMUEL_BUILD_DIRTY=0
export SAMUEL_STABLE_ENTRYPOINT="$0"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
release_dir=$(dirname -- "$script_dir")
exec "$release_dir/venv/bin/samuel" "$@"
"""
    path.parent.mkdir(parents=True, mode=0o755)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _probe_release(release_dir: Path, *, version: str, revision: str) -> dict[str, str]:
    launcher = release_dir / "bin" / "samuel"
    interpreter = release_dir / "venv" / "bin" / "python"
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise LocalReleaseError(f"installed console launcher is unavailable: {launcher}")
    env = _child_environment(revision)
    cli = _run([str(launcher), "--version"], cwd=release_dir, env=env).stdout.strip()
    if cli != f"samuel {version}":
        raise LocalReleaseError(f"installed CLI version mismatch: {cli!r}")
    probe_source = (
        "import importlib.metadata,json,pathlib,samuel;"
        "d=importlib.metadata.distribution('samuel');"
        "print(json.dumps({'version':samuel.__version__,"
        "'revision':samuel.__build_info__.revision,"
        "'module':str(pathlib.Path(samuel.__file__).resolve()),"
        "'metadata':str(pathlib.Path(d._path).resolve())},sort_keys=True))"
    )
    payload = json.loads(
        _run([str(interpreter), "-I", "-c", probe_source], cwd=release_dir, env=env).stdout
    )
    if payload.get("version") != version or payload.get("revision") != revision:
        raise LocalReleaseError("installed package version/revision mismatch")
    release_resolved = release_dir.resolve()
    for key in ("module", "metadata"):
        observed = Path(str(payload.get(key, ""))).resolve(strict=False)
        if release_resolved not in observed.parents:
            raise LocalReleaseError(f"installed {key} escapes release directory: {observed}")
    return {key: str(payload[key]) for key in ("version", "revision", "module", "metadata")}


def stage_release(
    *,
    layout: ReleaseLayout,
    manifest_path: Path,
    wheel_path: Path,
    runtime_lock_path: Path,
    python_executable: Path = Path(sys.executable),
) -> Path:
    """Build a complete sibling release and publish it only after isolated probes."""

    layout = layout.validated()
    _verify_install_root(layout)
    identity = validate_release_inputs(
        manifest_path=manifest_path,
        wheel_path=wheel_path,
        runtime_lock_path=runtime_lock_path,
    )
    version = identity["version"]
    release_dir = layout.releases_root / version
    if release_dir.exists() or release_dir.is_symlink():
        raise LocalReleaseError(f"release already exists; refusing in-place update: {release_dir}")
    layout.releases_root.mkdir(parents=True, mode=0o755, exist_ok=True)
    # Python venv launchers contain absolute interpreter paths and are not
    # relocatable.  Build directly at the final, inactive version path.  The
    # directory is not activatable until every probe passes and a receipt
    # exists; failures remain visible for explicit operator review/removal.
    release_dir.mkdir(mode=0o700)

    env = _child_environment()
    _run(
        [str(python_executable), "-m", "venv", str(release_dir / "venv")],
        cwd=release_dir,
        env=env,
    )
    pip = release_dir / "venv" / "bin" / "python"
    _run(
        [
            str(pip),
            "-m",
            "pip",
            "install",
            "--isolated",
            "--require-hashes",
            "-r",
            str(runtime_lock_path),
        ],
        cwd=release_dir,
        env=env,
    )
    _run(
        [str(pip), "-m", "pip", "install", "--isolated", "--no-deps", str(wheel_path)],
        cwd=release_dir,
        env=env,
    )
    _write_launcher(release_dir / "bin" / "samuel", revision=identity["revision"])
    probe = _probe_release(release_dir, version=version, revision=identity["revision"])
    receipt = {
        "schema_version": 1,
        "product": "samuel",
        **identity,
        "probe": probe,
    }
    (release_dir / _RECEIPT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    release_dir.chmod(0o755)
    return release_dir


def verify_release(layout: ReleaseLayout, version: str) -> dict[str, Any]:
    layout = layout.validated()
    if _PRODUCT_VERSION.fullmatch(version) is None:
        raise LocalReleaseError(f"invalid product version: {version!r}")
    release_dir = layout.releases_root / version
    if not release_dir.is_dir() or release_dir.is_symlink():
        raise LocalReleaseError(f"release directory is unavailable: {release_dir}")
    receipt = _read_json(release_dir / _RECEIPT, "release receipt")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("product") != "samuel"
        or receipt.get("version") != version
        or not isinstance(receipt.get("revision"), str)
        or _FULL_REVISION.fullmatch(str(receipt["revision"])) is None
    ):
        raise LocalReleaseError(f"release receipt identity is invalid: {release_dir / _RECEIPT}")
    receipt["probe"] = _probe_release(
        release_dir, version=version, revision=str(receipt["revision"])
    )
    return receipt


@contextmanager
def _activation_lock(layout: ReleaseLayout) -> Iterator[None]:
    layout.install_root.mkdir(parents=True, mode=0o755, exist_ok=True)
    lock_path = layout.install_root / ".activation.lock"
    with lock_path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def _current_version(layout: ReleaseLayout) -> str | None:
    current = layout.current
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise LocalReleaseError(f"current path is not a symlink: {current}")
    resolved = current.resolve(strict=False)
    releases = layout.releases_root.resolve(strict=False)
    if releases not in resolved.parents or resolved.parent != releases:
        raise LocalReleaseError(f"current symlink escapes releases root: {current} -> {resolved}")
    return resolved.name


def _verify_install_root(layout: ReleaseLayout) -> None:
    """Reject unclassified overlays beside the managed immutable releases."""

    if not layout.install_root.exists():
        return
    if layout.install_root.is_symlink():
        raise LocalReleaseError(
            f"immutable install root must not be a symlink: {layout.install_root}"
        )
    allowed = {"releases", "current", ".activation.lock"}
    unexpected = sorted(
        path.name for path in layout.install_root.iterdir() if path.name not in allowed
    )
    if unexpected:
        raise LocalReleaseError(
            "unclassified entries in immutable install root: " + ", ".join(unexpected)
        )
    if not layout.releases_root.exists():
        return
    if layout.releases_root.is_symlink():
        raise LocalReleaseError(f"releases root must not be a symlink: {layout.releases_root}")
    invalid_releases = sorted(
        path.name
        for path in layout.releases_root.iterdir()
        if not (
            not path.is_symlink()
            and path.is_dir()
            and _PRODUCT_VERSION.fullmatch(path.name) is not None
        )
    )
    if invalid_releases:
        raise LocalReleaseError(
            "unclassified entries in releases root: " + ", ".join(invalid_releases)
        )


def activate_release(
    layout: ReleaseLayout, *, version: str, expected_current: str | None
) -> str | None:
    """CAS-switch ``current`` to a verified release using one atomic rename."""

    layout = layout.validated()
    _verify_install_root(layout)
    verify_release(layout, version)
    with _activation_lock(layout):
        observed = _current_version(layout)
        if observed != expected_current:
            raise LocalReleaseError(
                f"active release changed: expected {expected_current or 'none'}, "
                f"observed {observed or 'none'}"
            )
        temporary = layout.install_root / f".current-{uuid.uuid4().hex}"
        temporary.symlink_to(Path("releases") / version)
        os.replace(temporary, layout.current)
        if _current_version(layout) != version:
            raise LocalReleaseError("atomic activation verification failed")
        return observed


def _layout_from_args(args: argparse.Namespace) -> ReleaseLayout:
    return ReleaseLayout(
        install_root=args.install_root,
        config_root=args.config_root,
        data_root=args.data_root,
        log_root=args.log_root,
        service_root=args.service_root,
    ).validated()


def _add_layout_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--install-root", type=Path, default=Path("/opt/samuel"))
    parser.add_argument("--config-root", type=Path, default=Path("/etc/samuel"))
    parser.add_argument("--data-root", type=Path, default=Path("/var/lib/samuel"))
    parser.add_argument("--log-root", type=Path, default=Path("/var/log/samuel"))
    parser.add_argument("--service-root", type=Path, default=Path("/srv/samuel"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="initialize empty persistent deployment roots")
    _add_layout_arguments(init)
    init.add_argument("--defaults", type=Path, required=True)

    stage = subcommands.add_parser("stage", help="stage and verify one immutable release")
    _add_layout_arguments(stage)
    stage.add_argument("--manifest", type=Path, required=True)
    stage.add_argument("--wheel", type=Path, required=True)
    stage.add_argument("--runtime-lock", type=Path, required=True)
    stage.add_argument("--python", type=Path, default=Path(sys.executable))

    activate = subcommands.add_parser("activate", help="atomically switch the current symlink")
    _add_layout_arguments(activate)
    activate.add_argument("--version", required=True)
    activate.add_argument(
        "--expected-current",
        required=True,
        help="currently active version, or 'none' for the first activation",
    )

    verify = subcommands.add_parser("verify", help="verify an installed immutable release")
    _add_layout_arguments(verify)
    verify.add_argument("--version", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        layout = _layout_from_args(args)
        if args.command == "init":
            initialize_layout(layout, args.defaults.resolve())
            print(f"initialized persistent layout at {layout.service_root}")
        elif args.command == "stage":
            release = stage_release(
                layout=layout,
                manifest_path=args.manifest.resolve(),
                wheel_path=args.wheel.resolve(),
                runtime_lock_path=args.runtime_lock.resolve(),
                python_executable=args.python.resolve(),
            )
            print(f"staged and verified {release}")
        elif args.command == "activate":
            expected = None if args.expected_current == "none" else args.expected_current
            previous = activate_release(layout, version=args.version, expected_current=expected)
            print(f"activated {args.version}; previous={previous or 'none'}")
        else:
            receipt = verify_release(layout, args.version)
            print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
        return 0
    except (LocalReleaseError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
