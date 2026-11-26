#!/usr/bin/env python3
"""OCI first-install helper (#970), executed inside the verified release image.

The operator does not need Python on the Docker host. Existing initialization
uses the standard library; bootstrap fetching loads the installed trust client.
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
import tempfile
from contextlib import suppress
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


def _installer_files(bundle: tarfile.TarFile) -> list[tuple[str, tarfile.TarInfo]]:
    """Validate archive paths before either comparison or extraction."""
    seen: set[str] = set()
    files = []
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
        files.append((relative, member))
    required = {
        "tools/samuel-container",
        "tools/container_init.py",
        "docker-compose.yml",
        "docker-compose.setup.yml",
        "docs/INSTALL.md",
    }
    if not required <= seen:
        raise ContainerInitError("release installer is incomplete")
    return files


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
    with tarfile.open(archive, "r:gz") as bundle:
        for relative, member in _installer_files(bundle):
            path = source / relative
            stream = bundle.extractfile(member)
            if (
                path.is_symlink()
                or not path.is_file()
                or stream is None
                or path.read_bytes() != stream.read()
            ):
                raise ContainerInitError(f"extracted installer differs from release: {relative}")


def _prepare_release_installer(result: dict[str, Any], cache: Path) -> tuple[Path, Path, Path]:
    """Reuse the same verified extraction for bootstrap and operator updates."""
    from samuel.local_release import verify_manifest_artifact

    manifest_path = Path(result["manifest"]["path"])
    manifest = json.loads(manifest_path.read_bytes())
    container = manifest.get("container")
    if not isinstance(container, dict):
        raise ContainerInitError("release lacks OCI image binding")
    read_manifest(manifest_path, result["manifest"]["sha256"], container.get("reference", ""))
    archive_name = f"samuel-oci-{result['version']}.tar.gz"
    matches = [a for a in result["artifacts"] if Path(a["path"]).name == archive_name]
    if len(matches) != 1:
        raise ContainerInitError("release lacks its bound OCI installer")
    archive = Path(matches[0]["path"])
    verify_manifest_artifact(manifest, archive)
    installers = cache / "installers"
    installers.mkdir(mode=0o700, exist_ok=True)
    if installers.is_symlink() or installers.stat().st_mode & 0o077:
        raise ContainerInitError("installer cache must be private")
    destination = installers / matches[0]["sha256"]
    if not destination.exists():
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=installers) as temporary:
            staged = Path(temporary) / "samuel-oci"
            staged.mkdir(mode=0o700)
            with tarfile.open(archive, "r:gz") as bundle:
                for relative, member in _installer_files(bundle):
                    path = staged / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    stream = bundle.extractfile(member)
                    if stream is None:
                        raise ContainerInitError("installer file cannot be read")
                    with path.open("xb") as output:
                        shutil.copyfileobj(stream, output)
            # The private outer cache protects host access. The kit itself is
            # bind-mounted read-only for the image's non-root delivery verifier.
            # Explicit chmod also works under the operator's private umask.
            for entry in (staged, *staged.rglob("*")):
                entry.chmod(0o755 if entry.is_dir() else 0o644)
            verify_delivery(manifest, archive, staged)
            # No overwrite: a concurrent preparation may already have published
            # the same content-addressed directory. Reverify it below.
            try:
                staged.rename(destination)
            except OSError:
                if not destination.is_dir():
                    raise
    if destination.is_symlink():
        raise ContainerInitError("installer cache must not be a symlink")
    verify_delivery(manifest, archive, destination)
    for entry in (destination, *destination.rglob("*")):
        expected_mode = 0o755 if entry.is_dir() else 0o644
        if (
            entry.is_symlink()
            or not (entry.is_file() or entry.is_dir())
            or entry.stat().st_mode & 0o777 != expected_mode
        ):
            raise ContainerInitError("cached installer permissions differ; no implicit repair")
    return manifest_path, archive, destination


def prepare_update_installer(
    *,
    source_path: Path,
    cache: Path,
    target_version: str,
    source_version: str,
    source_state_schema: int,
    target_state_schema: int,
    fetcher: Any = None,
) -> dict[str, Any]:
    """Independently prepare a target kit from the private operator source.

    No dashboard receipt, command, image override or approval is accepted. The
    caller must still verify observed host/runtime bindings and hold maintenance
    across backup and activation; this preparation performs neither operation.
    """
    from samuel.local_release import prepare_oci_update

    prepared = prepare_oci_update(
        source_path=source_path,
        cache_dir=cache,
        target_version=target_version,
        source_version=source_version,
        source_state_schema=source_state_schema,
        target_state_schema=target_state_schema,
        fetcher=fetcher,
        source_owner=(0, 0),
    )
    manifest, archive, directory = _prepare_release_installer(prepared["inputs"], cache)
    return {
        **prepared,
        "installer": {
            "manifest": str(manifest.relative_to(cache)),
            "archive": str(archive.relative_to(cache)),
            "directory": str(directory.relative_to(cache)),
        },
    }


def prepare_installed_update(
    *,
    config_root: Path,
    host_root: str,
    profile_path: Path,
    root_path: Path,
    cache: Path,
    image: str,
    target_version: str,
    source_state_schema: int,
    target_state_schema: int,
    fetcher: Any = None,
) -> dict[str, Any]:
    """Bind both release kits to the installed source, without host activation.

    Only an actual a34 installation may lack the later private source record.
    In that case the explicitly supplied bootstrap binding remains provisional:
    this function never adopts it or qualifies its initial handoff. The caller
    must obtain the schema through read-only diagnostics, then independently
    check the actual target runtime before approval and the held transition.
    """
    from samuel.release_trust import (
        fetch_release_inputs,
        read_release_source,
        release_manifest_target,
        release_source_document,
        validate_release_profile,
    )

    if os.geteuid() != 0:
        raise ContainerInitError("update preparation requires the local root operator")
    profile = validate_release_profile(json.loads(profile_path.read_bytes()))
    root = root_path.read_bytes()
    if (
        profile["bootstrap_image"] != image
        or hashlib.sha256(root).hexdigest() != profile["trust_root_sha256"]
    ):
        raise ContainerInitError("bootstrap verifier or initial root binding differs")
    installed = read_installation_receipt(
        config_root / ".container-install.json", host_root=host_root
    )
    receipt = installed["receipt"]
    source_path = config_root / ".release-source.json"
    source = None
    if source_path.exists() or source_path.is_symlink():
        source = read_release_source(source_path, expected_owner=(0, 0))
        # The package may have a newer verifier/initial release. It must not
        # replace the installation's trust root, channel or version resolution.
        trust_fields = (
            "trust_root_sha256",
            "metadata_url",
            "targets_url",
            "manifest_target_template",
        )
        if source["root"].encode() != root or any(
            source["profile"].get(key) != profile.get(key) for key in trust_fields
        ):
            raise ContainerInitError("bootstrap differs from the installed release trust binding")
        source_document = release_source_document(
            source["profile"], root, source["bootstrap_manifest_sha256"]
        )
        selected_profile = source["profile"]
    else:
        if receipt["version"] != "2.0.0a34":
            raise ContainerInitError("missing installed release source requires explicit recovery")
        selected_profile = profile
        source_document = release_source_document(profile, root, receipt["manifest_sha256"])
    # Both kits must be available before any transition: the old one is also
    # required for the existing file capture and local recovery path.
    with tempfile.TemporaryDirectory(prefix="samuel-installed-update-") as temporary:
        anchor = Path(temporary) / "trusted-root.json"
        anchor.write_bytes(root)
        original = fetch_release_inputs(
            root_path=anchor,
            root_sha256=selected_profile["trust_root_sha256"],
            metadata_url=selected_profile["metadata_url"],
            targets_url=selected_profile["targets_url"],
            cache_dir=cache,
            target=release_manifest_target(selected_profile, receipt["version"]),
            fetcher=fetcher,
        )
        if original["manifest"]["sha256"] != receipt["manifest_sha256"]:
            raise ContainerInitError("signed source manifest differs from the installed release")
        old_manifest = read_manifest(
            Path(original["manifest"]["path"]), receipt["manifest_sha256"], receipt["image"]
        )
        if (
            old_manifest["version"] != receipt["version"]
            or old_manifest["commit"] != receipt["revision"]
        ):
            raise ContainerInitError("signed source identity differs from the installed release")
        old_manifest_path, old_archive, old_directory = _prepare_release_installer(original, cache)
        provisional_source = Path(temporary) / "source.json"
        provisional_source.write_bytes(source_document)
        provisional_source.chmod(0o600)
        prepared = prepare_update_installer(
            source_path=provisional_source,
            cache=cache,
            target_version=target_version,
            source_version=receipt["version"],
            source_state_schema=source_state_schema,
            target_state_schema=target_state_schema,
            fetcher=fetcher,
        )
    if (
        read_installation_receipt(config_root / ".container-install.json", host_root=host_root)
        != installed
    ):
        raise ContainerInitError("installed receipt changed during release preparation")
    if source is not None:
        if read_release_source(source_path, expected_owner=(0, 0)) != source:
            raise ContainerInitError("installed release source changed during preparation")
    elif source_path.exists() or source_path.is_symlink():
        raise ContainerInitError("release source appeared during preparation")
    return {
        **prepared,
        "source_installation": installed,
        "source_installer": {
            "manifest": str(old_manifest_path.relative_to(cache)),
            "archive": str(old_archive.relative_to(cache)),
            "directory": str(old_directory.relative_to(cache)),
        },
        "release_source_document": source_document.decode(),
        "release_source_adoption_required": source is None,
    }


def read_update_state_report(path: Path) -> dict[str, Any]:
    """Read the installer-created report, not a dashboard-supplied status."""
    from samuel.core.state import StateStoreError, authority_event_binding
    from samuel.release_trust import read_release_input

    observed = json.loads(
        read_release_input(
            path,
            expected_owner=(0, 0),
            max_length=1_048_576,
            label="operator state observation",
        )
    )
    state = observed.get("state") if isinstance(observed, dict) else None
    authority = state.get("authority") if isinstance(state, dict) else None
    if (
        not isinstance(observed, dict)
        or observed.get("action") != "status"
        or observed.get("ok") is not True
        or not isinstance(state, dict)
        or state.get("healthy") is not True
        or state.get("path") != "/app/data/samuel-state.sqlite3"
        or type(state.get("schema_version")) is not int
        or not isinstance(authority, dict)
        or authority.get("witness_epoch") != authority.get("epoch")
        or authority.get("reconcile_required") is not False
        or authority.get("active_restore_operation") is not None
        or authority.get("restore_sentinel_present") is not False
    ):
        raise ContainerInitError("existing read-only state observation is unavailable or blocked")
    try:
        # Restore creates a hyphenated UUID; retain the State contract and exact identity.
        authority_event_binding(authority)
    except StateStoreError as exc:
        raise ContainerInitError(
            "existing read-only state observation is unavailable or blocked"
        ) from exc
    return state


def prepare_update_command(
    *,
    config_root: Path,
    host_root: str,
    profile_path: Path,
    root_path: Path,
    cache: Path,
    image: str,
    target_version: str,
    state_report: Path,
    fetcher: Any = None,
) -> list[str]:
    """Prepare typed installer inputs from the operator's own read-only process.

    The state report is generated by the outer installer in a private temporary
    directory, never supplied by the dashboard. This only stores preparation
    bytes; the outer installer still requires fresh host checks and approval.
    """
    from samuel.adapters.state.sqlite import SCHEMA_VERSION
    from samuel.release_trust import _private_directory, read_release_input

    state = read_update_state_report(state_report)
    configuration = state.get("configuration")
    if (
        not isinstance(configuration, dict)
        or configuration.get("phase") != "idle"
        or configuration.get("maintenance") != {}
    ):
        raise ContainerInitError("configuration or maintenance pending; explicit recovery required")
    prepared = prepare_installed_update(
        config_root=config_root,
        host_root=host_root,
        profile_path=profile_path,
        root_path=root_path,
        cache=cache,
        image=image,
        target_version=target_version,
        source_state_schema=state["schema_version"],
        target_state_schema=SCHEMA_VERSION,
        fetcher=fetcher,
    )
    original_receipt = read_release_input(
        config_root / ".container-install.json",
        expected_owner=(0, 0),
        max_length=65536,
        label="installation receipt",
    )
    if hashlib.sha256(original_receipt).hexdigest() != prepared["source_installation"]["sha256"]:
        raise ContainerInitError("source installation changed after preparation")
    prepared.update(
        original_receipt=original_receipt.decode(),
        observed_state=state,
        source_state_schema=state["schema_version"],
        host_root=host_root,
    )
    from samuel.verifier_toolchain import verify_registration

    registration = verify_registration(config_root)
    if registration is not None:
        expected_prefix = host_root.rstrip("/") + "/srv/samuel/toolchains/"
        if (
            re.fullmatch(
                re.escape(expected_prefix) + r"(?:sha256-|update-)[0-9a-f]{64}",
                registration["host_root"],
            )
            is None
            or registration["binding"]["manifest"] != "/opt/samuel-verifier/toolchain-manifest.json"
        ):
            raise ContainerInitError("installed toolchain is outside the fixed operator layout")
    prepared["source_toolchain"] = registration
    target_manifest = json.loads((cache / prepared["installer"]["manifest"]).read_bytes())
    prepared["target_image"] = target_manifest["container"]["reference"]
    raw = (json.dumps(prepared, sort_keys=True, separators=(",", ":")) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    directory = cache / "update-preparations"
    _private_directory(directory)
    path = directory / (digest + ".json")
    if not path.exists() and not path.is_symlink():
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=directory) as temporary:
            staged = Path(temporary) / "prepared.json"
            with staged.open("xb") as output:
                os.chmod(staged, 0o600)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            with suppress(FileExistsError):
                os.link(staged, path)
    if (
        read_release_input(
            path, expected_owner=(0, 0), max_length=2_097_152, label="operator update preparation"
        )
        != raw
    ):
        raise ContainerInitError("existing update preparation differs; no replacement")
    # A previous process may have linked the correct bytes but lost power before
    # syncing the directory. An equal existing file must cross the same barrier.
    for parent in (directory, cache):
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    kit = prepared["installer"]
    manifest = json.loads((cache / kit["manifest"]).read_bytes())
    receipt = prepared["source_installation"]["receipt"]
    return [
        kit["manifest"],
        prepared["manifest_sha256"],
        kit["archive"],
        kit["directory"],
        manifest["container"]["reference"],
        str(receipt["port"]),
        receipt["project"],
        str(path.relative_to(cache)),
        digest,
    ]


def verify_update_state_identity(value: dict[str, Any], observed: dict[str, Any]) -> None:
    previous = value["observed_state"]["authority"]
    current = observed["authority"]
    if current["instance"] != previous["instance"] or current["epoch"] < previous["epoch"]:
        raise ContainerInitError("installation state identity or authority epoch changed")


def refresh_update_inputs(
    value: dict[str, Any],
    *,
    host_root: str,
    profile_path: Path,
    root_path: Path,
    cache: Path,
    image: str,
    source_state_schema: int,
    fetcher: Any = None,
) -> None:
    # Reuse independent TUF/source verification from the original receipt; a
    # partially written target receipt is never treated as a fresh source.
    with tempfile.TemporaryDirectory(prefix="samuel-update-recheck-") as temporary:
        original = Path(temporary)
        for name, content in (
            (".container-install.json", value["original_receipt"]),
            (".release-source.json", value["release_source_document"]),
        ):
            target = original / name
            target.write_text(content)
            target.chmod(0o600)
        refreshed = prepare_installed_update(
            config_root=original,
            host_root=host_root,
            profile_path=profile_path,
            root_path=root_path,
            cache=cache,
            image=image,
            target_version=value["target_version"],
            source_state_schema=value["source_state_schema"],
            target_state_schema=source_state_schema,
            fetcher=fetcher,
        )
    for key in (
        "source_installation",
        "source_installer",
        "installer",
        "manifest_sha256",
        "target_version",
        "release_source_document",
    ):
        if refreshed[key] != value[key]:
            raise ContainerInitError(
                "fresh release verification differs from the pending operation"
            )


def prepare_update_recovery(
    *,
    config_root: Path,
    host_root: str,
    profile_path: Path,
    root_path: Path,
    cache: Path,
    image: str,
    preparation_sha256: str,
    state_report: Path,
    fetcher: Any = None,
) -> list[str]:
    """Select only the explicitly named, still-pending update and refresh trust."""
    from samuel.release_trust import read_release_input

    if re.fullmatch(r"[0-9a-f]{64}", preparation_sha256) is None:
        raise ContainerInitError("exact previous preparation digest required for recovery")
    observed = read_update_state_report(state_report)
    configuration = observed.get("configuration", {})
    if not isinstance(configuration, dict):
        raise ContainerInitError("configuration observation unavailable")
    maintenance = configuration.get("maintenance", {})
    if (
        not isinstance(maintenance, dict)
        or configuration.get("phase") != "maintenance"
        or maintenance.get("binding") != preparation_sha256
        or maintenance.get("target") != "production"
        or maintenance.get("step") != "pending"
    ):
        raise ContainerInitError("recovery requires this exact pending production transition")
    path = cache / "update-preparations" / (preparation_sha256 + ".json")
    raw = read_release_input(
        path,
        expected_owner=(0, 0),
        max_length=2_097_152,
        label="previous update preparation",
    )
    if hashlib.sha256(raw).hexdigest() != preparation_sha256:
        raise ContainerInitError("previous preparation digest differs")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or value.get("source_state_schema") != observed["schema_version"]
    ):
        raise ContainerInitError("recovery state schema differs from the approved operation")
    verify_update_state_identity(value, observed)
    refresh_update_inputs(
        value,
        host_root=host_root,
        profile_path=profile_path,
        root_path=root_path,
        cache=cache,
        image=image,
        source_state_schema=observed["schema_version"],
        fetcher=fetcher,
    )
    kit = value["installer"]
    manifest = json.loads((cache / kit["manifest"]).read_bytes())
    checked = read_update_preparation(
        path,
        preparation_sha256,
        config_root=config_root,
        host_root=host_root,
        cache=cache,
        manifest_sha256=value["manifest_sha256"],
        image=manifest["container"]["reference"],
        recovery=True,
    )
    receipt = checked["source_installation"]["receipt"]
    return [
        kit["manifest"],
        value["manifest_sha256"],
        kit["archive"],
        kit["directory"],
        manifest["container"]["reference"],
        str(receipt["port"]),
        receipt["project"],
        str(path.relative_to(cache)),
        preparation_sha256,
    ]


def read_update_preparation(
    path: Path,
    expected_sha256: str,
    *,
    config_root: Path,
    host_root: str,
    cache: Path,
    manifest_sha256: str,
    image: str,
    recovery: bool = False,
) -> dict[str, Any]:
    """Recheck the private output of this invocation's independent TUF preparation.

    This is an internal continuation, not a public way to approve cached or
    dashboard-authored input. The outer command must generate it afresh and
    obtain explicit approval before the held transition and metadata writes.
    """
    from samuel.release_trust import read_release_input, read_release_source

    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ContainerInitError("verified update preparation digest required")
    raw = read_release_input(
        path, expected_owner=(0, 0), max_length=2_097_152, label="operator update preparation"
    )
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ContainerInitError("operator update preparation digest differs")
    value = json.loads(raw)
    current = read_installation_receipt(
        config_root / ".container-install.json", host_root=host_root
    )
    if (
        not isinstance(value, dict)
        or value.get("schema") != "oci-update-preparation.v1"
        or value.get("installation_performed") is not False
        or value.get("operator_approval") != "required"
        or value.get("host_root") != host_root
        or (not recovery and value.get("source_installation") != current)
        or value.get("manifest_sha256") != manifest_sha256
        or value.get("target_image") != image
        or not isinstance(value.get("original_receipt"), str)
    ):
        raise ContainerInitError(
            "prepared update does not match the current installation or target"
        )
    with tempfile.TemporaryDirectory(prefix="samuel-source-selection-") as temporary:
        original_path = Path(temporary) / ".container-install.json"
        original_path.write_text(value["original_receipt"])
        original_path.chmod(0o600)
        original = read_installation_receipt(original_path, host_root=host_root)
        if value.get("source_installation") != original:
            raise ContainerInitError("original receipt differs from bound source")
        source_path = Path(temporary) / "source.json"
        source_path.write_text(value["release_source_document"])
        source_path.chmod(0o600)
        source = read_release_source(source_path, expected_owner=(0, 0))
        active_source = config_root / ".release-source.json"
        if active_source.exists() or active_source.is_symlink():
            if read_release_source(active_source, expected_owner=(0, 0)) != source:
                raise ContainerInitError("installed release source differs from preparation")
        elif (
            original["receipt"]["version"] != "2.0.0a34"
            or value.get("release_source_adoption_required") is not True
        ):
            raise ContainerInitError("installed release source missing")
        profile_path = Path(temporary) / "profile.json"
        profile_path.write_text(json.dumps(source["profile"]))
        root_path = Path(temporary) / "root.json"
        root_path.write_text(source["root"])
        # Reuse the existing root-owned cache selection and full old-kit check.
        # Its image argument binds the source profile; the actual target image
        # is independently verified by the caller's ordinary image check.
        old = installed_operator_inputs(
            profile_path=profile_path,
            root_path=root_path,
            receipt_path=original_path,
            cache=cache,
            host_root=host_root,
            image=source["profile"]["bootstrap_image"],
        )
    if value.get("source_installer") != {
        "manifest": old[0],
        "archive": old[2],
        "directory": old[3],
    }:
        raise ContainerInitError("prepared source installer differs from the installed kit")
    kit = value.get("installer")
    if not isinstance(kit, dict) or set(kit) != {"manifest", "archive", "directory"}:
        raise ContainerInitError("invalid target installer inputs")
    patterns = {
        "manifest": r"artifacts/[0-9a-f]{64}/[A-Za-z0-9][A-Za-z0-9._-]*",
        "archive": r"artifacts/[0-9a-f]{64}/samuel-oci-[A-Za-z0-9._-]+\.tar\.gz",
        "directory": r"installers/[0-9a-f]{64}",
    }
    if any(
        not isinstance(kit[key], str) or re.fullmatch(pattern, kit[key]) is None
        for key, pattern in patterns.items()
    ):
        raise ContainerInitError("target kit must use bounded cache paths")
    target = read_manifest(cache / kit["manifest"], manifest_sha256, image)
    verify_delivery(target, cache / kit["archive"], cache / kit["directory"])
    if target["version"] != value.get("target_version"):
        raise ContainerInitError("prepared target version differs")
    from samuel.adapters.state.sqlite import SCHEMA_VERSION
    from samuel.local_release import validate_oci_update_contract

    validate_oci_update_contract(
        target,
        source_version=original["receipt"]["version"],
        source_state_schema=value.get("source_state_schema"),
        target_state_schema=SCHEMA_VERSION,
    )
    expected_target = {
        **original["receipt"],
        "manifest_sha256": manifest_sha256,
        "version": target["version"],
        "revision": target["commit"],
        "image": image,
    }
    if current["receipt"] not in (original["receipt"], expected_target):
        raise ContainerInitError("current receipt is neither the bound source nor the exact target")
    return value


def write_update_context(
    value: dict[str, Any], *, destination: Path, image: str, host_root: str
) -> list[str]:
    """Render fixed old Compose inputs, never an active or caller-authored job."""
    from samuel.verifier_toolchain import toolchain_overlay

    if (
        destination.resolve() != destination
        or not destination.is_dir()
        or any(destination.iterdir())
    ):
        raise ContainerInitError("empty private operator context required")
    info = destination.stat()
    if (info.st_uid, info.st_gid) != (0, 0) or info.st_mode & 0o077:
        raise ContainerInitError("operator context must remain private")
    receipt = value["source_installation"]["receipt"]
    old_kit = value["source_installer"]["directory"]
    if re.fullmatch(r"installers/[0-9a-f]{64}", old_kit) is None:
        raise ContainerInitError("source installer outside the protected cache")
    registration = value.get("source_toolchain")
    toolchain_root, toolchain_digest = "-", "-"
    if registration is not None:
        toolchain_root = registration["host_root"]
        toolchain_digest = registration["binding"]["sha256"]
        if (
            re.fullmatch(
                re.escape(host_root.rstrip("/") + "/srv/samuel/toolchains/")
                + r"(?:sha256-|update-)[0-9a-f]{64}",
                toolchain_root,
            )
            is None
            or re.fullmatch(r"[0-9a-f]{64}", toolchain_digest) is None
            or registration["binding"]["manifest"] != "/opt/samuel-verifier/toolchain-manifest.json"
        ):
            raise ContainerInitError("source toolchain outside the fixed installation layout")
        _write(destination / "toolchain.yml", toolchain_overlay(toolchain_root), owner=(0, 0))
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", image) is None:
        raise ContainerInitError("immutable maintenance image required")
    _write(destination / "compose.env", _compose_environment(receipt), owner=(0, 0))
    _write(
        destination / "maintenance.yml",
        "services:\n  samuel:\n    image: " + image + "\n",
        owner=(0, 0),
    )
    return [receipt["version"], old_kit, toolchain_root, toolchain_digest]


def read_update_capture_selection(cache: Path, preparation_sha256: str) -> tuple[Path, str]:
    from samuel.release_trust import read_release_input

    if re.fullmatch(r"[0-9a-f]{64}", preparation_sha256) is None:
        raise ContainerInitError("fixed preparation digest required")
    parent = cache / "update-captures" / preparation_sha256
    for directory in (parent.parent, parent):
        if directory.resolve() != directory or not directory.is_dir():
            raise ContainerInitError("selected capture parent must be canonical")
        info = directory.stat()
        if (info.st_uid, info.st_gid) != (0, 0) or info.st_mode & 0o077:
            raise ContainerInitError("selected capture parent must remain private")
    raw = read_release_input(
        parent / "selected.json",
        expected_owner=(0, 0),
        max_length=65536,
        label="selected update capture",
    )
    selected = json.loads(raw)
    if (
        not isinstance(selected, dict)
        or set(selected) != {"preparation_sha256", "attempt", "capture_sha256"}
        or selected["preparation_sha256"] != preparation_sha256
        or re.fullmatch(r"[0-9a-f]{32}", str(selected["attempt"])) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(selected["capture_sha256"])) is None
    ):
        raise ContainerInitError("capture selection does not bind this preparation")
    return parent / selected["attempt"], selected["capture_sha256"]


def read_update_backup_response(
    backup_receipt: Path, previous_authority: dict[str, Any]
) -> dict[str, Any]:
    """Validate the existing guard response; it does not authorize a restore."""
    from samuel.release_trust import read_release_input

    backup = json.loads(
        read_release_input(
            backup_receipt,
            expected_owner=(0, 0),
            max_length=65536,
            label="held maintenance backup response",
        )
    )
    if (
        not isinstance(backup, dict)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(backup.get("digest"))) is None
        or not isinstance(backup.get("path"), str)
        or re.fullmatch(r"/app/data/backups/[A-Za-z0-9._/-]+", backup["path"]) is None
        or str(Path(backup["path"])) != backup["path"]
        or ".." in Path(backup["path"]).parts
    ):
        raise ContainerInitError("backup is outside the existing installation backup mount")
    if (
        backup.get("instance_uuid") != previous_authority["instance"]
        or type(backup.get("authority_epoch")) is not int
        or backup["authority_epoch"] < previous_authority["epoch"]
    ):
        raise ContainerInitError("held backup belongs to a different state identity or epoch")
    return backup


def perform_update_step(
    *,
    step: str,
    preparation: Path,
    preparation_sha256: str,
    config_root: Path,
    data_root: Path,
    log_root: Path,
    work_root: Path,
    backup_root: Path,
    host_root: str,
    cache: Path,
    manifest_path: Path,
    manifest_sha256: str,
    image: str,
    installer_archive: Path,
    installer_source: Path,
    backup_receipt: Path | None = None,
    toolchains: Path | None = None,
    recovery: bool = False,
) -> dict[str, Any]:
    """Wire existing helpers while the outer operator holds the maintenance guard.

    No step opens admission, starts a runtime, establishes trust or chooses a
    release. The outer command must check its private, fresh state observation,
    obtain approval and keep the guard alive across every call and host action.
    """
    from uuid import uuid4

    from samuel.release_trust import _private_directory, read_release_input
    from samuel.slices.setup.handler import SetupHandler

    if os.geteuid() != 0 or step not in {"capture", "toolchain", "verify", "apply", "restore"}:
        raise ContainerInitError("fixed operator update step required")
    value = read_update_preparation(
        preparation,
        preparation_sha256,
        config_root=config_root,
        host_root=host_root,
        cache=cache,
        manifest_sha256=manifest_sha256,
        image=image,
        recovery=recovery,
    )
    source = value["source_installation"]["receipt"]
    old_kit = value["source_installer"]
    for root in (config_root, config_root / "config", data_root, log_root, work_root, backup_root):
        if root.resolve() != root or not root.is_dir():
            raise ContainerInitError("existing update root is not a canonical directory")
        info = root.stat()
        if (info.st_uid, info.st_gid) != (source["uid"], source["gid"]):
            raise ContainerInitError("existing update directory owner differs")
    registration = value.get("source_toolchain")
    old_toolchain = Path("/opt/samuel-verifier") if registration is not None else None
    if registration is not None and (
        not isinstance(registration, dict)
        or registration.get("binding", {}).get("manifest")
        != "/opt/samuel-verifier/toolchain-manifest.json"
        or not isinstance(registration.get("host_root"), str)
        or re.fullmatch(
            re.escape(host_root.rstrip("/") + "/srv/samuel/toolchains/")
            + r"(?:sha256-|update-)[0-9a-f]{64}",
            registration["host_root"],
        )
        is None
    ):
        raise ContainerInitError("source toolchain binding is outside this installation")
    parent = cache / "update-captures" / preparation_sha256

    def sync(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    if step == "capture":
        if backup_receipt is None:
            raise ContainerInitError("held maintenance backup response required")
        backup = read_update_backup_response(backup_receipt, value["observed_state"]["authority"])
        state_backup = backup_root / Path(backup["path"]).relative_to("/app/data/backups")
        if parent.exists() and (
            (parent / "selected.json").exists() or (parent / "selected.json").is_symlink()
        ):
            if not recovery:
                raise ContainerInitError("capture already selected; explicit recovery required")
            directory, digest = read_update_capture_selection(cache, preparation_sha256)
            raw = read_release_input(
                directory / "capture.json",
                expected_owner=(0, 0),
                max_length=65536,
                label="selected file capture",
            )
            capture = json.loads(raw)
            if (
                hashlib.sha256(raw).hexdigest() != digest
                or capture.get("source_installation_sha256")
                != value["source_installation"]["sha256"]
                or capture.get("state_backup_sha256") != backup["digest"][7:]
            ):
                raise ContainerInitError("selected capture differs from the held backup binding")
            sync(parent)
            sync(parent.parent)
            sync(cache)
            return {"capture": str(directory), "capture_sha256": digest, "reused": True}
        if state_backup.resolve() != state_backup or not state_backup.is_file():
            raise ContainerInitError("managed backup path changed")
        _private_directory(cache / "update-captures")
        _private_directory(parent)
        attempt = uuid4().hex
        directory = parent / attempt
        capture_update_files(
            config_root=config_root,
            data_root=data_root,
            log_root=log_root,
            work_root=work_root,
            host_root=host_root,
            manifest_path=cache / old_kit["manifest"],
            installer_archive=cache / old_kit["archive"],
            installer_source=cache / old_kit["directory"],
            state_backup=state_backup,
            state_backup_sha256=backup["digest"][7:],
            destination=directory,
            toolchain_root=old_toolchain,
        )
        digest = hashlib.sha256((directory / "capture.json").read_bytes()).hexdigest()
        selected = {
            "preparation_sha256": preparation_sha256,
            "attempt": attempt,
            "capture_sha256": digest,
        }
        staged = SetupHandler._stage_private_file(
            (json.dumps(selected, sort_keys=True) + "\n").encode(),
            suffix=".selection",
            directory=parent,
            mode=0o600,
        )
        try:
            os.link(staged, parent / "selected.json")
            sync(parent)
            sync(parent.parent)
            sync(cache)
        finally:
            staged.unlink(missing_ok=True)
        return {"capture": str(directory), "capture_sha256": digest, "reused": False}
    directory, digest = read_update_capture_selection(cache, preparation_sha256)
    restoration = directory / "restore-pending.json"
    if step == "apply" and (restoration.exists() or restoration.is_symlink()):
        raise ContainerInitError("restoration already started; forward activation denied")
    if step == "restore" and (not recovery or backup_receipt is None):
        raise ContainerInitError("restoration requires explicit recovery and held backup")
    target_toolchain = None
    if registration is not None:
        if toolchains is None or toolchains.resolve() != toolchains or not toolchains.is_dir():
            raise ContainerInitError("fixed toolchain parent mount required")
        metadata = toolchains.stat()
        if (metadata.st_uid, metadata.st_gid) != (0, 0) or metadata.st_mode & 0o022:
            raise ContainerInitError("toolchain parent must remain operator owned")
        target_toolchain = toolchains / ("update-" + manifest_sha256)
        if step == "toolchain" and not target_toolchain.exists():
            from samuel.core.config import VerifierToolchainSchema
            from samuel.verifier_toolchain import prepare_toolchain_for_release

            # Preserve incomplete copies. Only a fully verified, sealed copy is
            # placed at the fixed final name; the old artifact is never modified.
            staged_root = toolchains / (".update-" + uuid4().hex)
            staged_root.mkdir(mode=0o700)
            prepare_toolchain_for_release(
                root=staged_root,
                previous=VerifierToolchainSchema(**registration["binding"]),
                source_version=source["version"],
                source_revision=source["revision"],
                source_image=source["image"],
                target_image=image,
            )
            for path in staged_root.rglob("*"):
                if path.is_file():
                    with path.open("rb") as stream:
                        os.fsync(stream.fileno())
            for path in sorted(
                (p for p in staged_root.rglob("*") if p.is_dir()),
                key=lambda p: len(p.parts),
                reverse=True,
            ):
                sync(path)
            sync(staged_root)
            if target_toolchain.exists() or target_toolchain.is_symlink():
                raise ContainerInitError("target toolchain appeared during preparation")
            staged_root.rename(target_toolchain)
            sync(toolchains)
    if target_toolchain is not None and (
        target_toolchain.resolve() != target_toolchain or not target_toolchain.is_dir()
    ):
        raise ContainerInitError("target toolchain must be a canonical retained directory")
    if step == "toolchain" and target_toolchain is not None:
        for path in target_toolchain.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        for path in sorted(
            (p for p in target_toolchain.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            sync(path)
        sync(target_toolchain)
        sync(target_toolchain.parent)
    pending = directory / "metadata-pending.json"
    resume = pending.exists() or pending.is_symlink()
    if resume and not recovery:
        raise ContainerInitError("metadata already attempted; explicit recovery required")
    metadata_arguments: dict[str, Any] = dict(
        config_root=config_root,
        host_root=host_root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        image=image,
        installer_archive=installer_archive,
        installer_source=installer_source,
        source_state_schema=value["source_state_schema"],
        capture_directory=directory,
        capture_sha256=digest,
        prepared_toolchain=target_toolchain,
    )
    if step == "restore":
        assert backup_receipt is not None
        backup = read_update_backup_response(backup_receipt, value["observed_state"]["authority"])
        raw_capture = read_release_input(
            directory / "capture.json",
            expected_owner=(0, 0),
            max_length=65536,
            label="restoration capture",
        )
        captured = json.loads(raw_capture)
        if (
            hashlib.sha256(raw_capture).hexdigest() != digest
            or captured.get("state_backup_sha256") != backup["digest"][7:]
        ):
            raise ContainerInitError("restoration backup differs from the selected capture")
        backup_file = backup_root / Path(backup["path"]).relative_to("/app/data/backups")
        if backup_file.resolve() != backup_file or not backup_file.is_file():
            raise ContainerInitError("restoration backup path changed")
        descriptor = os.open(backup_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != backup["digest"][7:]:
                raise ContainerInitError("restoration backup bytes changed")
        result = restore_update_metadata(**metadata_arguments)
        return {
            **result,
            "backup_path": backup["path"],
            "backup_digest": backup["digest"],
            "source_image": source["image"],
            "source_revision": source["revision"],
            "source_version": source["version"],
            "source_installer": {**old_kit, "manifest_sha256": source["manifest_sha256"]},
            "restore_compose": str((directory / "restore-compose.json").relative_to(cache)),
        }
    result = apply_update_metadata(**metadata_arguments, resume=resume, verify_only=step != "apply")
    if step == "apply":
        # a34 did not retain this later source record. The independently checked
        # operator profile is adopted only under the same explicit update guard.
        with tempfile.TemporaryDirectory(prefix="samuel-update-source-") as temporary:
            source_path = Path(temporary) / "source.json"
            source_path.write_text(value["release_source_document"])
            source_path.chmod(0o600)
            install_release_source(
                config_root,
                source_path,
                json.loads(value["release_source_document"])["bootstrap_manifest_sha256"],
                (source["uid"], source["gid"]),
                durable=True,
            )
    return result


def prepare_bootstrap(profile_path: Path, root_path: Path, cache: Path, image: str) -> list[str]:
    """Prepare the existing installer; never establish trust or start the runtime."""
    from samuel.release_trust import (
        _private_directory,
        fetch_release_inputs,
        release_source_document,
        validate_release_profile,
    )

    profile = validate_release_profile(json.loads(profile_path.read_bytes()))
    if profile["bootstrap_image"] != image:
        raise ContainerInitError("invalid bootstrap profile or verifier image binding")
    result = fetch_release_inputs(
        root_path=root_path,
        root_sha256=profile["trust_root_sha256"],
        metadata_url=profile["metadata_url"],
        targets_url=profile["targets_url"],
        cache_dir=cache,
        target=profile["manifest_target"],
    )
    manifest_path, archive, destination = _prepare_release_installer(result, cache)
    source = release_source_document(profile, root_path.read_bytes(), result["manifest"]["sha256"])
    sources = cache / "sources"
    _private_directory(sources)
    source_path = sources / (hashlib.sha256(source).hexdigest() + ".json")
    if source_path.exists() or source_path.is_symlink():
        if (
            source_path.is_symlink()
            or not source_path.is_file()
            or source_path.read_bytes() != source
        ):
            raise ContainerInitError("cached release source differs")
    else:
        with tempfile.TemporaryDirectory(prefix=".source-", dir=sources) as temporary:
            staged_source = Path(temporary) / "source.json"
            with staged_source.open("xb") as output:
                os.chmod(staged_source, 0o600)
                output.write(source)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(staged_source, source_path)
            except FileExistsError:
                if source_path.is_symlink() or source_path.read_bytes() != source:
                    raise ContainerInitError("cached release source differs") from None
    return [
        str(manifest_path.relative_to(cache)),
        result["manifest"]["sha256"],
        str(archive.relative_to(cache)),
        str(destination.relative_to(cache)),
        str(source_path.relative_to(cache)),
    ]


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


def read_installation_receipt(path: Path, *, host_root: str) -> dict[str, Any]:
    """Read the existing operator record without accepting arbitrary host roots.

    This is selection input for the independent release/installed-layout checks,
    not authority to stop a service, write metadata, or activate an image.
    """
    from samuel.release_trust import read_release_input

    if (
        not re.fullmatch(r"/[A-Za-z0-9/._-]*", host_root)
        or host_root.startswith("//")
        or str(Path(host_root)) != host_root
        or ".." in Path(host_root).parts
    ):
        raise ContainerInitError("canonical absolute installation root required")
    raw = read_release_input(
        path, expected_owner=(0, 0), max_length=65_536, label="installation receipt"
    )
    receipt = json.loads(raw)
    roots = {
        "config_root": "/etc/samuel",
        "data_root": "/var/lib/samuel",
        "work_root": "/srv/samuel/workspaces",
        "log_root": "/var/log/samuel",
        "backup_root": "/srv/samuel/backups",
    }
    fields = {
        *roots,
        "manifest_sha256",
        "version",
        "revision",
        "image",
        "stage",
        "port",
        "project",
        "uid",
        "gid",
    }
    if not isinstance(receipt, dict) or set(receipt) != fields:
        raise ContainerInitError("invalid installation receipt fields")
    if any(receipt[key] != host_root.rstrip("/") + suffix for key, suffix in roots.items()):
        raise ContainerInitError("installation receipt belongs to a different host layout")
    patterns = {
        "manifest_sha256": r"[0-9a-f]{64}",
        "version": r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?",
        "revision": r"[0-9a-f]{40}|[0-9a-f]{64}",
        "image": r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}",
        "project": r"[a-z0-9][a-z0-9_-]*",
    }
    if (
        any(
            not isinstance(receipt[key], str) or re.fullmatch(pattern, receipt[key]) is None
            for key, pattern in patterns.items()
        )
        or receipt["stage"] != "initialized"
        or type(receipt["port"]) is not int
        or not 1 <= receipt["port"] <= 65_535
        or any(
            type(receipt[key]) is not int or not 1 <= receipt[key] <= 2**31 - 1
            for key in ("uid", "gid")
        )
    ):
        raise ContainerInitError("invalid installation receipt identity")
    return {"receipt": receipt, "sha256": hashlib.sha256(raw).hexdigest()}


def installed_operator_inputs(
    *,
    profile_path: Path,
    root_path: Path,
    receipt_path: Path,
    cache: Path,
    host_root: str,
    image: str,
) -> list[str]:
    """Select the existing cached kit; never download, repair, or change a release.

    The verified bootstrap image reads only the private operator receipt/cache.
    The delegated installer still checks image, delivery, layout and admission.
    """
    from samuel.release_trust import validate_release_profile

    profile = validate_release_profile(json.loads(profile_path.read_bytes()))
    if (
        profile["bootstrap_image"] != image
        or hashlib.sha256(root_path.read_bytes()).hexdigest() != profile["trust_root_sha256"]
    ):
        raise ContainerInitError("bootstrap verifier or initial root binding differs")
    receipt = read_installation_receipt(receipt_path, host_root=host_root)["receipt"]

    if not cache.is_absolute():
        raise ContainerInitError("absolute installed cache required")

    def checked(path: Path, *, directory: bool = False) -> Path:
        for relative in reversed(path.relative_to(cache).parents):
            entry = cache / relative
            if entry.is_symlink() or not entry.is_dir():
                raise ContainerInitError("installed release cache path is unsafe")
            metadata = entry.stat()
            if (metadata.st_uid, metadata.st_gid) != (0, 0) or metadata.st_mode & (
                0o077 if entry == cache else 0o022
            ):
                raise ContainerInitError(
                    "installed release cache must be private and operator-owned"
                )
        if path.is_symlink() or not (path.is_dir() if directory else path.is_file()):
            raise ContainerInitError("installed release cache entry is missing or unsafe")
        metadata = path.stat()
        if (metadata.st_uid, metadata.st_gid) != (0, 0) or metadata.st_mode & 0o022:
            raise ContainerInitError("installed release cache must be operator-owned")
        return path

    manifest_dir = checked(cache / "artifacts" / receipt["manifest_sha256"], directory=True)
    manifests = list(manifest_dir.iterdir())
    if (
        len(manifests) != 1
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", manifests[0].name) is None
    ):
        raise ContainerInitError("installed manifest cache is ambiguous")
    manifest_path = checked(manifests[0])
    manifest = read_manifest(manifest_path, receipt["manifest_sha256"], receipt["image"])
    if manifest["version"] != receipt["version"] or manifest["commit"] != receipt["revision"]:
        raise ContainerInitError("installed manifest and receipt identities differ")
    name = f"samuel-oci-{manifest['version']}.tar.gz"
    assets = manifest.get("artifacts")
    if not isinstance(assets, list):
        raise ContainerInitError("installed release lacks artifact bindings")
    matches = [item for item in assets if isinstance(item, dict) and item.get("name") == name]
    if (
        len(matches) != 1
        or re.fullmatch(r"[0-9a-f]{64}", str(matches[0].get("sha256", ""))) is None
    ):
        raise ContainerInitError("installed release lacks one bound installer")
    archive = checked(cache / "artifacts" / matches[0]["sha256"] / name)
    kit = checked(cache / "installers" / matches[0]["sha256"], directory=True)
    for entry in kit.rglob("*"):
        checked(entry, directory=entry.is_dir())
    verify_delivery(manifest, archive, kit)
    return [
        str(manifest_path.relative_to(cache)),
        receipt["manifest_sha256"],
        str(archive.relative_to(cache)),
        str(kit.relative_to(cache)),
        receipt["image"],
        str(receipt["port"]),
        receipt["project"],
    ]


_UPDATE_METADATA_FILES = (
    ".env",
    ".container-install.json",
    "compose.env",
    "compose/docker-compose.yml",
    "compose/docker-compose.setup.yml",
    "config/project-binding.json",
    "compose/docker-compose.project.yml",
    "config/eval.json",
    ".verifier-toolchain.json",
    "compose/docker-compose.toolchain.yml",
)


def prepare_update_metadata(
    *,
    config_root: Path,
    host_root: str,
    manifest_path: Path,
    manifest_sha256: str,
    image: str,
    installer_archive: Path,
    installer_source: Path,
    source_state_schema: int,
    prepared_toolchain: Path | None = None,
) -> dict[str, Any]:
    """Prepare fixed release metadata without changing active files or authority.

    Execute in the independently verified target image. The operator still has
    to authenticate release inputs, verify the live installation, hold fences,
    capture backups and explicitly activate the complete set. Returned bytes
    are not a shell instruction or an approval.
    """
    from samuel.adapters.state.sqlite import SCHEMA_VERSION
    from samuel.core.project_binding import regular_path
    from samuel.local_release import validate_oci_update_contract
    from samuel.project_binding import prepare_project_for_release
    from samuel.slices.setup.handler import SetupHandler
    from samuel.verifier_toolchain import verify_registration

    def source_bytes() -> dict[str, bytes | None]:
        values: dict[str, bytes | None] = {}
        for name in _UPDATE_METADATA_FILES:
            path = config_root / name
            if not regular_path(path):
                raise ContainerInitError("installed update metadata path is unsafe")
            values[name] = SetupHandler._read_regular_bytes(path) if path.exists() else None
        return values

    before = source_bytes()
    source = read_installation_receipt(config_root / ".container-install.json", host_root=host_root)
    previous = source["receipt"]
    manifest = read_manifest(manifest_path, manifest_sha256, image)
    verify_delivery(manifest, installer_archive, installer_source)
    owner = verify_runtime(manifest)
    if owner != (previous["uid"], previous["gid"]):
        raise ContainerInitError("update must preserve the actual runtime owner")
    compatibility = validate_oci_update_contract(
        manifest,
        source_version=previous["version"],
        source_state_schema=source_state_schema,
        target_state_schema=SCHEMA_VERSION,
    )
    target = {
        **previous,
        "manifest_sha256": manifest_sha256,
        "version": manifest["version"],
        "revision": manifest["commit"],
        "image": image,
    }
    raw_target = (json.dumps(target, indent=2) + "\n").encode()
    project = prepare_project_for_release(config_root, raw_target)
    files = {
        ".container-install.json": raw_target,
        "compose.env": _compose_environment(target).encode(),
        **{
            "compose/" + name: (installer_source / name).read_bytes()
            for name in ("docker-compose.yml", "docker-compose.setup.yml")
        },
    }
    if project is not None:
        files["config/project-binding.json"] = (json.dumps(project, indent=2) + "\n").encode()
    verify_registration(config_root)
    registration_path = config_root / ".verifier-toolchain.json"
    evaluation_raw = before["config/eval.json"]
    evaluation = json.loads(evaluation_raw) if evaluation_raw is not None else {}
    if not isinstance(evaluation, dict):
        raise ContainerInitError("evaluation policy must be an object")
    if not registration_path.exists() and evaluation.get("verifier_toolchain"):
        raise ContainerInitError("unregistered evaluation toolchain cannot be rebound")
    if registration_path.exists():
        if prepared_toolchain is None:
            raise ContainerInitError(
                "registered toolchain requires a separately verified target copy"
            )
        from samuel.core.config import VerifierToolchainSchema
        from samuel.core.test_runner import (
            _read_toolchain_manifest,
            _validate_toolchain_contents,
            validate_toolchain,
        )
        from samuel.verifier_toolchain import register_toolchain

        registration = json.loads(registration_path.read_bytes())
        old_binding = VerifierToolchainSchema(**registration["binding"])
        old_manifest = _read_toolchain_manifest(old_binding)
        _validate_toolchain_contents(Path(old_binding.manifest), old_manifest)
        target_path = prepared_toolchain / "toolchain-manifest.json"
        target_binding = VerifierToolchainSchema(
            manifest=str(target_path), sha256=hashlib.sha256(target_path.read_bytes()).hexdigest()
        )
        new_manifest = validate_toolchain(target_binding)
        old_python = {
            **new_manifest["python"],
            "runtime_version": previous["version"],
            "runtime_revision": previous["revision"],
        }
        if (
            old_manifest.get("python") != old_python
            or old_manifest.get("runtime_image") != previous["image"]
            or new_manifest.get("runtime_image") != image
            or {k: v for k, v in old_manifest.items() if k not in {"python", "runtime_image"}}
            != {k: v for k, v in new_manifest.items() if k not in {"python", "runtime_image"}}
        ):
            raise ContainerInitError(
                "prepared toolchain changes source contents or runtime binding"
            )
        # Reuse the existing registration serializer in a private temporary
        # layout. The active evaluation policy and registration are never written.
        if evaluation.get("verifier_toolchain") != registration["binding"]:
            raise ContainerInitError("evaluation toolchain registration changed")
        evaluation.pop("verifier_toolchain")
        target_host_root = (
            host_root.rstrip("/") + "/srv/samuel/toolchains/update-" + manifest_sha256
        )
        with tempfile.TemporaryDirectory(prefix="samuel-update-registration-") as temporary:
            staged = Path(temporary)
            (staged / "config").mkdir()
            (staged / "compose").mkdir()
            (staged / "config/eval.json").write_text(json.dumps(evaluation))
            register_toolchain(
                staged,
                target_host_root,
                {
                    "manifest": "/opt/samuel-verifier/toolchain-manifest.json",
                    "sha256": target_binding.sha256,
                },
            )
            for name in (
                "config/eval.json",
                ".verifier-toolchain.json",
                "compose/docker-compose.toolchain.yml",
            ):
                files[name] = (staged / name).read_bytes()
        if json.loads(registration_path.read_bytes()) != registration:
            raise ContainerInitError("toolchain registration changed during update preparation")
    elif prepared_toolchain is not None:
        raise ContainerInitError("update cannot introduce an unregistered toolchain")
    # Verify inputs again rather than publishing a mixed set after a concurrent
    # preparation change. The caller's held fences remain mandatory at activation.
    if (
        read_installation_receipt(config_root / ".container-install.json", host_root=host_root)
        != source
    ):
        raise ContainerInitError("source installation changed during update preparation")
    if prepare_project_for_release(config_root, raw_target) != project:
        raise ContainerInitError("project registration changed during update preparation")
    verify_delivery(manifest, installer_archive, installer_source)
    if source_bytes() != before:
        raise ContainerInitError("installed metadata changed during update preparation")
    return {
        "schema": "oci-update-metadata.v1",
        "source_installation_sha256": source["sha256"],
        "target_installation_sha256": hashlib.sha256(raw_target).hexdigest(),
        "target_manifest_sha256": manifest_sha256,
        "source_files_sha256": {
            name: hashlib.sha256(raw).hexdigest() if raw is not None else None
            for name, raw in before.items()
        },
        "compatibility": compatibility,
        "files": files,
        "activation_performed": False,
    }


def apply_update_metadata(
    *,
    config_root: Path,
    host_root: str,
    manifest_path: Path,
    manifest_sha256: str,
    image: str,
    installer_archive: Path,
    installer_source: Path,
    source_state_schema: int,
    capture_directory: Path,
    capture_sha256: str,
    prepared_toolchain: Path | None = None,
    resume: bool = False,
    verify_only: bool = False,
) -> dict[str, Any]:
    """Write the fixed metadata after a verified capture, never start a runtime.

    The caller must independently approve the release, hold maintenance fences
    and stop every writer. A pending marker and the original archive survive
    failure/process loss. Explicit resume may only finish that same fixed target;
    it never restores state or releases admission. It is not a public operator
    entry point, and the caller must verify a still-pending maintenance operation.
    """
    import base64
    import stat

    from samuel.core.project_binding import regular_path
    from samuel.release_trust import read_release_input
    from samuel.slices.setup.handler import SetupHandler

    if os.geteuid() != 0:
        raise ContainerInitError("metadata application requires the local root operator")
    if re.fullmatch(r"[0-9a-f]{64}", capture_sha256) is None:
        raise ContainerInitError("bound capture receipt digest required")
    if (
        not capture_directory.is_absolute()
        or capture_directory.resolve() != capture_directory
        or not capture_directory.is_dir()
    ):
        raise ContainerInitError("capture directory must be an existing canonical directory")
    directory_info = capture_directory.stat()
    if (directory_info.st_uid, directory_info.st_gid) != (0, 0) or directory_info.st_mode & 0o077:
        raise ContainerInitError("capture directory must remain private and operator-owned")
    if not resume and any(
        (capture_directory / name).exists() or (capture_directory / name).is_symlink()
        for name in ("metadata-pending.json", "metadata-applied.json")
    ):
        raise ContainerInitError(
            "metadata application already attempted; explicit recovery required"
        )
    if resume and not (capture_directory / "metadata-pending.json").exists():
        raise ContainerInitError("explicit resume requires the original pending operation")
    raw_capture = read_release_input(
        capture_directory / "capture.json",
        expected_owner=(0, 0),
        max_length=65536,
        label="file capture receipt",
    )
    capture = json.loads(raw_capture)
    if (
        hashlib.sha256(raw_capture).hexdigest() != capture_sha256
        or not isinstance(capture, dict)
        or capture.get("schema") != "oci-update-file-capture.v1"
        or capture.get("stage") != "files_captured"
        or capture.get("archive") != "files.tar"
        or capture.get("restoration_performed") is not False
    ):
        raise ContainerInitError("capture does not bind the source installation")
    captured_metadata: dict[str, tuple[int, int, int, dict[str, bytes]]] = {}
    descriptor = os.open(
        capture_directory / "files.tar", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_uid, before.st_gid) != (0, 0)
            or before.st_mode & 0o077
            or before.st_size != capture.get("archive_size")
            or hashlib.file_digest(stream, "sha256").hexdigest() != capture.get("archive_sha256")
        ):
            raise ContainerInitError("captured archive binding differs")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:") as bundle:
            members = bundle.getmembers()
            required_artifacts = {
                "state/managed-backup.sqlite3": capture.get("state_backup_sha256")
            }
            # Recreate only the fixed old metadata in a private temporary layout.
            # No general archive extraction, live restore or archived code execution.
            with tempfile.TemporaryDirectory(prefix="samuel-metadata-resume-") as temporary:
                source_config = Path(temporary) if resume else config_root
                if resume:
                    for name in _UPDATE_METADATA_FILES:
                        matches = [m for m in members if m.name == "configuration/" + name]
                        if not matches:
                            continue
                        if len(matches) != 1 or not (matches[0].isfile() or matches[0].islnk()):
                            raise ContainerInitError("capture has ambiguous recovery metadata")
                        archived = bundle.extractfile(matches[0])
                        if archived is None:
                            raise ContainerInitError("captured recovery metadata unavailable")
                        path = source_config / name
                        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with archived, path.open("xb") as output:
                            os.fchmod(output.fileno(), 0o600)
                            shutil.copyfileobj(archived, output)
                        os.chown(path, matches[0].uid, matches[0].gid)
                        path.chmod(matches[0].mode)
                prepared = prepare_update_metadata(
                    config_root=source_config,
                    host_root=host_root,
                    manifest_path=manifest_path,
                    manifest_sha256=manifest_sha256,
                    image=image,
                    installer_archive=installer_archive,
                    installer_source=installer_source,
                    source_state_schema=source_state_schema,
                    prepared_toolchain=prepared_toolchain,
                )
                registration = source_config / ".verifier-toolchain.json"
                if registration.exists():
                    required_artifacts["verifier_toolchain/toolchain-manifest.json"] = json.loads(
                        SetupHandler._read_regular_bytes(registration)
                    )["binding"]["sha256"]
            if capture.get("source_installation_sha256") != prepared["source_installation_sha256"]:
                raise ContainerInitError("capture does not bind the source installation")
            for name, digest in required_artifacts.items():
                matches = [m for m in members if m.name == name]
                if (
                    not isinstance(digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    or len(matches) != 1
                    or not (matches[0].isfile() or matches[0].islnk())
                ):
                    raise ContainerInitError("capture lacks a required bound artifact")
                archived = bundle.extractfile(matches[0])
                if archived is None:
                    raise ContainerInitError("captured artifact is unavailable")
                with archived:
                    if hashlib.file_digest(archived, "sha256").hexdigest() != digest:
                        raise ContainerInitError("captured artifact digest differs")
            for name, expected in prepared["source_files_sha256"].items():
                matches = [m for m in members if m.name == "configuration/" + name]
                if expected is None:
                    if matches:
                        raise ContainerInitError("captured metadata differs from current source")
                    continue
                if len(matches) != 1 or not (matches[0].isfile() or matches[0].islnk()):
                    raise ContainerInitError("capture lacks unambiguous source metadata")
                member = matches[0]
                live = config_root / name
                info = live.stat(follow_symlinks=False)
                archived_attributes = json.loads(
                    member.pax_headers.get("SAMUEL.xattrs.base64", "null")
                )
                live_attributes = {
                    key: os.getxattr(live, key, follow_symlinks=False)
                    for key in os.listxattr(live, follow_symlinks=False)
                }
                if (
                    not stat.S_ISREG(info.st_mode)
                    or (member.uid, member.gid, member.mode)
                    != (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))
                    or not isinstance(archived_attributes, dict)
                    or {
                        key: base64.b64decode(value, validate=True)
                        for key, value in archived_attributes.items()
                    }
                    != live_attributes
                ):
                    raise ContainerInitError("captured metadata ownership or attributes changed")
                captured_metadata[name] = (
                    info.st_uid,
                    info.st_gid,
                    stat.S_IMODE(info.st_mode),
                    live_attributes,
                )
                archived = bundle.extractfile(member)
                if archived is None:
                    raise ContainerInitError("captured metadata is unavailable")
                with archived:
                    if hashlib.file_digest(archived, "sha256").hexdigest() != expected:
                        raise ContainerInitError("captured metadata differs from current source")
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ContainerInitError("capture changed during verification")
    files = prepared["files"]
    entries = []
    for name, content in files.items():
        path = config_root / name
        expected = prepared["source_files_sha256"][name]
        current_digest = hashlib.sha256(SetupHandler._read_regular_bytes(path)).hexdigest()
        target_digest = hashlib.sha256(content).hexdigest()
        allowed = {expected, target_digest} if resume else {expected}
        if expected is None or current_digest not in allowed:
            raise ContainerInitError("active metadata changed before application")
        if not resume or current_digest != target_digest:
            entries.append((path, content.decode("utf-8"), None))
    # The receipt changes last. Neither that ordering nor per-file replace is a
    # multi-file crash transaction. Durable maintenance must remain closed until
    # actual target readiness has been verified by the outer operator.
    entries.sort(key=lambda entry: entry[0].name == ".container-install.json")
    result = {
        "schema": "oci-update-metadata-application.v1",
        "source_installation_sha256": prepared["source_installation_sha256"],
        "target_installation_sha256": prepared["target_installation_sha256"],
        "target_manifest_sha256": manifest_sha256,
        "capture_sha256": capture_sha256,
        "files_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        "runtime_started": False,
        "maintenance_completed": False,
    }

    def sync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def marker(name: str, stage: str) -> None:
        temporary = SetupHandler._stage_private_file(
            (json.dumps({**result, "stage": stage}, sort_keys=True, indent=2) + "\n").encode(),
            suffix=".pending",
            directory=capture_directory,
            mode=0o600,
        )
        target = capture_directory / name
        linked = False
        try:
            os.link(temporary, target)
            linked = True
            sync_directory(capture_directory)
        except OSError:
            if linked:
                target.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def verify_marker(name: str, stage: str) -> None:
        raw = read_release_input(
            capture_directory / name,
            expected_owner=(0, 0),
            max_length=65536,
            label="metadata operation",
        )
        if json.loads(raw) != {**result, "stage": stage}:
            raise ContainerInitError("pending operation does not bind this exact target")

    if resume:
        verify_marker("metadata-pending.json", "metadata_write_pending")
        if (capture_directory / "metadata-applied.json").exists() or (
            capture_directory / "metadata-applied.json"
        ).is_symlink():
            verify_marker("metadata-applied.json", "metadata_applied")
    elif not verify_only:
        marker("metadata-pending.json", "metadata_write_pending")
    for name, expected in prepared["source_files_sha256"].items():
        path = config_root / name
        if not regular_path(path):
            raise ContainerInitError("active metadata path changed before writing")
        if expected is None:
            if path.exists():
                raise ContainerInitError("active metadata appeared before writing")
            continue
        info = path.stat(follow_symlinks=False)
        current_metadata = (
            info.st_uid,
            info.st_gid,
            stat.S_IMODE(info.st_mode),
            {
                key: os.getxattr(path, key, follow_symlinks=False)
                for key in os.listxattr(path, follow_symlinks=False)
            },
        )
        allowed = {expected}
        if resume and name in files:
            allowed.add(hashlib.sha256(files[name]).hexdigest())
        if (
            hashlib.sha256(SetupHandler._read_regular_bytes(path)).hexdigest() not in allowed
            or current_metadata != captured_metadata[name]
        ):
            raise ContainerInitError("active metadata changed before writing")
    if verify_only:
        return {**result, "stage": "metadata_verified"}
    SetupHandler._atomic_write_many(entries, preserve_metadata=True)
    for name, expected in result["files_sha256"].items():
        path = config_root / name
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if (
                not stat.S_ISREG(os.fstat(stream.fileno()).st_mode)
                or hashlib.file_digest(stream, "sha256").hexdigest() != expected
            ):
                raise ContainerInitError("applied metadata verification failed")
            os.fsync(stream.fileno())
    for directory in {(config_root / name).parent for name in files}:
        sync_directory(directory)
    if resume and (capture_directory / "metadata-applied.json").exists():
        verify_marker("metadata-applied.json", "metadata_applied")
    else:
        marker("metadata-applied.json", "metadata_applied")
    return {**result, "stage": "metadata_applied"}


def restore_update_metadata(
    *,
    config_root: Path,
    host_root: str,
    manifest_path: Path,
    manifest_sha256: str,
    image: str,
    installer_archive: Path,
    installer_source: Path,
    source_state_schema: int,
    capture_directory: Path,
    capture_sha256: str,
    prepared_toolchain: Path | None = None,
) -> dict[str, Any]:
    """Return only the update's fixed metadata to its captured source release.

    The caller holds maintenance and stops the runtime. State is restored only
    through the existing State CLI afterward; witness, audit and workspace data
    are never replaced here. The durable marker fences forward activation after
    an explicitly authorized restoration has begun.
    """
    import stat

    from samuel.release_trust import read_release_input
    from samuel.slices.setup.handler import SetupHandler

    verified = apply_update_metadata(
        config_root=config_root,
        host_root=host_root,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        image=image,
        installer_archive=installer_archive,
        installer_source=installer_source,
        source_state_schema=source_state_schema,
        capture_directory=capture_directory,
        capture_sha256=capture_sha256,
        prepared_toolchain=prepared_toolchain,
        resume=True,
        verify_only=True,
    )
    raw = read_release_input(
        capture_directory / "capture.json",
        expected_owner=(0, 0),
        max_length=65536,
        label="restore capture",
    )
    if hashlib.sha256(raw).hexdigest() != capture_sha256:
        raise ContainerInitError("restore capture changed after verification")
    capture = json.loads(raw)
    source_files: dict[str, bytes] = {}
    descriptor = os.open(
        capture_directory / "files.tar", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_uid, before.st_gid) != (0, 0)
            or before.st_mode & 0o077
            or before.st_size != capture["archive_size"]
            or hashlib.file_digest(stream, "sha256").hexdigest() != capture["archive_sha256"]
        ):
            raise ContainerInitError("restore archive changed after verification")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            members = archive.getmembers()
            for name in verified["files_sha256"]:
                matches = [m for m in members if m.name == "configuration/" + name]
                if name not in _UPDATE_METADATA_FILES or len(matches) != 1:
                    raise ContainerInitError("ambiguous source restoration metadata")
                member = matches[0]
                if not (member.isfile() or member.islnk()):
                    raise ContainerInitError("invalid source restoration metadata")
                content = archive.extractfile(member)
                if content is None:
                    raise ContainerInitError("source restoration metadata unavailable")
                with content:
                    # These exact captured files already passed the existing
                    # update validator. Do not make rollback reject a size that
                    # the forward operation accepted.
                    source_files[name] = content.read()
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ContainerInitError("restore archive changed during read")
    if (
        hashlib.sha256(source_files[".container-install.json"]).hexdigest()
        != verified["source_installation_sha256"]
    ):
        raise ContainerInitError("restored receipt differs from the bound source")
    result = {
        "schema": "oci-update-metadata-restoration.v1",
        "source_installation_sha256": verified["source_installation_sha256"],
        "target_manifest_sha256": manifest_sha256,
        "capture_sha256": capture_sha256,
        "files_sha256": {
            name: hashlib.sha256(raw).hexdigest() for name, raw in source_files.items()
        },
        "state_restored": False,
        "runtime_started": False,
        "maintenance_completed": False,
    }
    for name, document in (
        ("restore-compose.json", {"services": {"samuel": {"healthcheck": {"disable": True}}}}),
        ("restore-pending.json", result),
    ):
        marker = capture_directory / name
        marker_bytes = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
        if marker.exists() or marker.is_symlink():
            existing = read_release_input(
                marker, expected_owner=(0, 0), max_length=65536, label="pending restoration"
            )
            if existing != marker_bytes:
                raise ContainerInitError("pending restoration does not bind this source")
        else:
            temporary = SetupHandler._stage_private_file(
                marker_bytes, suffix=".pending", directory=capture_directory, mode=0o600
            )
            try:
                os.link(temporary, marker)
            finally:
                temporary.unlink(missing_ok=True)
    descriptor = os.open(capture_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    entries = [
        (config_root / name, content.decode("utf-8"), None)
        for name, content in source_files.items()
        if SetupHandler._read_regular_bytes(config_root / name) != content
    ]
    entries.sort(key=lambda entry: entry[0].name == ".container-install.json")
    SetupHandler._atomic_write_many(entries, preserve_metadata=True)
    for name, expected in result["files_sha256"].items():
        descriptor = os.open(config_root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ContainerInitError("restored metadata verification failed")
            os.fsync(stream.fileno())
    for directory in {(config_root / name).parent for name in source_files}:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return {**result, "stage": "source_metadata_restored"}


def capture_update_files(
    *,
    config_root: Path,
    data_root: Path,
    log_root: Path,
    work_root: Path,
    host_root: str,
    manifest_path: Path,
    installer_archive: Path,
    installer_source: Path,
    state_backup: Path,
    state_backup_sha256: str,
    destination: Path,
    toolchain_root: Path | None = None,
) -> dict[str, Any]:
    """Capture ancillary files and an existing SQLite backup, without restoring.

    The operator must already hold the maintenance fences and stop the runtime
    and other writers. Metadata rechecks detect drift; they are not a filesystem
    freeze. The live SQLite main/WAL and lock files are never used as a backup.
    """
    import base64
    import stat

    if os.geteuid() != 0:
        raise ContainerInitError("operator file capture requires root ownership")
    if re.fullmatch(r"[0-9a-f]{64}", state_backup_sha256) is None:
        raise ContainerInitError("verified managed SQLite backup digest required")
    source = read_installation_receipt(config_root / ".container-install.json", host_root=host_root)
    receipt = source["receipt"]
    manifest = read_manifest(manifest_path, receipt["manifest_sha256"], receipt["image"])
    if manifest["version"] != receipt["version"] or manifest["commit"] != receipt["revision"]:
        raise ContainerInitError("backup release and installation identities differ")
    verify_delivery(manifest, installer_archive, installer_source)
    installer_digest = next(
        item["sha256"]
        for item in manifest["artifacts"]
        if item["name"] == f"samuel-oci-{manifest['version']}.tar.gz"
    )
    roots = {
        "configuration": config_root,
        "runtime_files": data_root,
        "logs": log_root,
        "workspaces": work_root,
    }
    if toolchain_root is not None:
        roots["verifier_toolchain"] = toolchain_root
    for root in (*roots.values(), destination.parent):
        if not root.is_absolute() or root.resolve() != root or not root.is_dir():
            raise ContainerInitError("capture roots must be canonical existing directories")
    if any(destination == root or root in destination.parents for root in roots.values()):
        raise ContainerInitError("capture destination must be outside all captured roots")
    if destination.resolve() != destination:
        raise ContainerInitError("capture destination must be canonical")
    if state_backup.name in {
        "samuel-state.sqlite3",
        "samuel-state.sqlite3-wal",
        "samuel-state.sqlite3-shm",
    }:
        raise ContainerInitError("live SQLite files are not managed backups")
    live_state = data_root / "samuel-state.sqlite3"
    if live_state.exists() and state_backup.samefile(live_state):
        raise ContainerInitError("live SQLite files are not managed backups")
    parent = destination.parent.stat()
    if (parent.st_uid, parent.st_gid) != (0, 0) or parent.st_mode & 0o077:
        raise ContainerInitError("capture parent must be private and operator-owned")
    skipped_runtime = {
        "samuel-state.sqlite3",
        "samuel-state.sqlite3-wal",
        "samuel-state.sqlite3-shm",
        ".samuel-state-authority.lock",
        ".samuel-state-lifecycle.lock",
        "configuration.lock",
        "configuration-work.lock",
        "logs",
        "backups",
    }
    fingerprints: dict[str, tuple[int, ...]] = {}
    hardlinks: dict[tuple[int, int], tuple[str, tuple[int, ...]]] = {}
    members = 0
    payload_bytes = 0

    def fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    def add_file(
        bundle: tarfile.TarFile, path: Path, name: str, expected: str | None = None
    ) -> None:
        nonlocal members, payload_bytes
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ContainerInitError("capture input must be a regular file")
            if expected is not None:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != expected:
                    raise ContainerInitError("bound capture input bytes differ")
                stream.seek(0)
            member = tarfile.TarInfo(name)
            member.size, member.mode = before.st_size, stat.S_IMODE(before.st_mode)
            member.uid, member.gid, member.mtime = before.st_uid, before.st_gid, before.st_mtime
            attributes = {
                key: base64.b64encode(os.getxattr(stream.fileno(), key)).decode("ascii")
                for key in os.listxattr(stream.fileno())
            }
            member.pax_headers = {
                "SAMUEL.xattrs.base64": json.dumps(attributes, sort_keys=True),
                "mtime": f"{before.st_mtime_ns // 1_000_000_000}.{before.st_mtime_ns % 1_000_000_000:09d}",
            }
            previous = hardlinks.get((before.st_dev, before.st_ino))
            if previous is not None:
                if previous[1] != fingerprint(before):
                    raise ContainerInitError("hardlinked capture input changed")
                member.type, member.linkname, member.size = tarfile.LNKTYPE, previous[0], 0
                bundle.addfile(member)
            else:
                bundle.addfile(member, stream)
                hardlinks[(before.st_dev, before.st_ino)] = (name, fingerprint(before))
                payload_bytes += before.st_size
            if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
                raise ContainerInitError("capture input changed during read")
            if fingerprint(path.lstat()) != fingerprint(before):
                raise ContainerInitError("capture input was replaced")
            fingerprints[str(path)] = fingerprint(before)
            members += 1

    def add_tree(bundle: tarfile.TarFile, root: Path, prefix: str) -> None:
        nonlocal members

        def fail(error: OSError) -> None:
            raise error

        root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for directory, dirs, files, descriptor in os.fwalk(
                ".", dir_fd=root_descriptor, follow_symlinks=False, onerror=fail
            ):
                relative = Path(directory)
                if prefix == "runtime_files" and relative == Path("."):
                    dirs[:] = [name for name in dirs if name not in skipped_runtime]
                    files = [name for name in files if name not in skipped_runtime]
                dirs.sort()
                directory_path = root / relative
                before = os.fstat(descriptor)
                fingerprints[str(directory_path)] = fingerprint(before)
                member = tarfile.TarInfo(str(Path(prefix) / relative))
                member.type, member.mode = tarfile.DIRTYPE, stat.S_IMODE(before.st_mode)
                member.uid, member.gid, member.mtime = before.st_uid, before.st_gid, before.st_mtime
                attributes = {
                    key: base64.b64encode(os.getxattr(descriptor, key)).decode("ascii")
                    for key in os.listxattr(descriptor)
                }
                member.pax_headers = {
                    "SAMUEL.xattrs.base64": json.dumps(attributes, sort_keys=True),
                    "mtime": f"{before.st_mtime_ns // 1_000_000_000}.{before.st_mtime_ns % 1_000_000_000:09d}",
                }
                bundle.addfile(member)
                members += 1
                for name in sorted([*dirs, *files]):
                    metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    path = directory_path / name
                    archive_name = str(Path(prefix) / relative / name)
                    if stat.S_ISLNK(metadata.st_mode):
                        member = tarfile.TarInfo(archive_name)
                        member.type = tarfile.SYMTYPE
                        member.linkname = os.readlink(name, dir_fd=descriptor)
                        member.mode = stat.S_IMODE(metadata.st_mode)
                        member.uid, member.gid, member.mtime = (
                            metadata.st_uid,
                            metadata.st_gid,
                            metadata.st_mtime,
                        )
                        link_path = Path(f"/proc/self/fd/{descriptor}") / name
                        attributes = {
                            key: base64.b64encode(
                                os.getxattr(link_path, key, follow_symlinks=False)
                            ).decode("ascii")
                            for key in os.listxattr(link_path, follow_symlinks=False)
                        }
                        member.pax_headers = {
                            "SAMUEL.xattrs.base64": json.dumps(attributes, sort_keys=True),
                            "mtime": f"{metadata.st_mtime_ns // 1_000_000_000}."
                            f"{metadata.st_mtime_ns % 1_000_000_000:09d}",
                        }
                        bundle.addfile(member)
                        if fingerprint(path.lstat()) != fingerprint(metadata):
                            raise ContainerInitError("capture link changed")
                        fingerprints[str(path)] = fingerprint(metadata)
                        members += 1
                    elif stat.S_ISREG(metadata.st_mode):
                        # Resolve through the held directory descriptor, not through
                        # a mutable path prefix in an untrusted workspace tree.
                        add_file(bundle, Path(f"/proc/self/fd/{descriptor}") / name, archive_name)
                        captured = fingerprints.pop(str(Path(f"/proc/self/fd/{descriptor}") / name))
                        if captured != fingerprint(metadata):
                            raise ContainerInitError("capture input changed before read")
                        fingerprints[str(path)] = fingerprint(metadata)
                    elif not stat.S_ISDIR(metadata.st_mode):
                        raise ContainerInitError("special files cannot be captured")

        finally:
            os.close(root_descriptor)

    # Creation is exclusive. A failed attempt is retained without a completion
    # receipt; no existing backup, source, installer or live state is repaired.
    destination.mkdir(mode=0o700)
    archive = destination / "files.tar"
    with archive.open("x+b") as output:
        os.fchmod(output.fileno(), 0o600)
        with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as bundle:
            add_file(bundle, state_backup, "state/managed-backup.sqlite3", state_backup_sha256)
            add_file(
                bundle, manifest_path, "installation/manifest.json", receipt["manifest_sha256"]
            )
            add_file(bundle, installer_archive, "installation/installer.tar.gz", installer_digest)
            for prefix, root in roots.items():
                add_tree(bundle, root, prefix)
        for path, expected in fingerprints.items():
            if fingerprint(Path(path).lstat()) != expected:
                raise ContainerInitError("capture source changed before completion")
        if (
            read_installation_receipt(config_root / ".container-install.json", host_root=host_root)
            != source
        ):
            raise ContainerInitError("installation changed during file capture")
        output.flush()
        os.fsync(output.fileno())
        output.seek(0)
        archive_sha256 = hashlib.file_digest(output, "sha256").hexdigest()
    result = {
        "schema": "oci-update-file-capture.v1",
        "source_installation_sha256": source["sha256"],
        "source_manifest_sha256": receipt["manifest_sha256"],
        "source_version": receipt["version"],
        "source_image": receipt["image"],
        "state_backup_sha256": state_backup_sha256,
        "archive": "files.tar",
        "archive_sha256": archive_sha256,
        "archive_size": archive.stat().st_size,
        "members": members,
        "payload_bytes": payload_bytes,
        "stage": "files_captured",
        "restoration_performed": False,
    }
    pending = destination / "capture.json.pending"
    with pending.open("x", encoding="utf-8") as receipt_output:
        os.fchmod(receipt_output.fileno(), 0o600)
        receipt_output.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
        receipt_output.flush()
        os.fsync(receipt_output.fileno())
    completed = destination / "capture.json"
    try:
        pending.rename(completed)
        for directory in (destination, destination.parent):
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except OSError:
        # Retain the attempted archive for diagnosis, without a success marker.
        completed.unlink(missing_ok=True)
        raise
    return result


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
    existing_only: bool = False,
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
    if existing_only:
        raise ContainerInitError(
            "existing installation receipt required; no initialization performed"
        )
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
    # Docker must not create this writable override mount with root ownership.
    (config / "llm" / "prompts").mkdir(parents=True, exist_ok=True)
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
    from samuel.slices.setup.env_io import ensure_security_keys, merge_env

    # The first maintenance process is already an audit writer. Persist keys
    # before any runtime can bootstrap; later setup must preserve these bytes.
    _write(
        config_root / ".env",
        merge_env(
            "# Operator environment; configure through the authenticated Setup dashboard.\n",
            ensure_security_keys({}),
        ),
        owner=owner,
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


def install_release_source(
    config_root: Path,
    source: Path,
    manifest_sha256: str,
    owner: tuple[int, int],
    *,
    allow_create: bool = True,
    durable: bool = False,
) -> None:
    """Retain operator source separately from its non-authoritative runtime view."""
    from samuel.release_trust import read_release_source, release_source_document

    value = read_release_source(source)
    if value["bootstrap_manifest_sha256"] != manifest_sha256:
        raise ContainerInitError("release source belongs to another bootstrap manifest")
    content = release_source_document(
        value["profile"], value["root"].encode(), manifest_sha256
    ).decode()
    targets = [
        (config_root / ".release-source.json", (0, 0)),
        (config_root / "config/release-source.json", owner),
    ]
    for path, identity in targets:
        if not allow_create and not path.exists():
            raise ContainerInitError(
                "existing installation lacks release source; explicit recovery required"
            )
        if path.exists() or path.is_symlink():
            if (
                path.is_symlink()
                or not path.is_file()
                or path.read_text() != content
                or (path.stat().st_uid, path.stat().st_gid) != identity
                or path.stat().st_mode & 0o077
            ):
                raise ContainerInitError(
                    "existing release source differs; no implicit trust change"
                )
    for path, identity in targets:
        if not path.exists():
            if not durable:
                _write(path, content, owner=identity)
            else:
                from samuel.slices.setup.handler import SetupHandler

                staged = SetupHandler._stage_private_file(
                    content.encode(),
                    suffix=".source",
                    directory=path.parent,
                    mode=0o600,
                )
                try:
                    os.chown(staged, *identity)
                    with staged.open("rb") as stream:
                        os.fsync(stream.fileno())
                    os.link(staged, path)
                finally:
                    staged.unlink(missing_ok=True)
        if durable:
            # Retry repeats the barrier after a link succeeded but its ack/sync
            # was lost. Existing complete sources are never replaced.
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def project_request_inputs(config_dir: Path, env_path: Path) -> list[str]:
    """Read untrusted preparation as runtime user; never inspect a host source."""
    from samuel.core.bootstrap import _build_scm_adapter
    from samuel.core.config import SCMConfig
    from samuel.core.git_remote import canonical_repository_url
    from samuel.core.project_binding import project_request_document
    from samuel.slices.setup.env_io import parse_env

    document = project_request_document(config_dir)
    if document is None:
        raise ContainerInitError("project preparation missing")
    request, digest = document
    env = parse_env(env_path.read_text())
    scm = _build_scm_adapter(
        SCMConfig(
            provider=env.get("SCM_PROVIDER", "gitea"),
            url=env.get("SCM_URL", ""),
            repo=env.get("SCM_REPO", ""),
            token="",
        )
    )
    if request["repository"] != canonical_repository_url(scm.repository_identity):
        raise ContainerInitError("project preparation differs from configured SCM")
    return [
        digest,
        request["host_source"],
        request["container_target"],
        request["repository"],
        request["initial_revision"],
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "verify",
            "verify-installed",
            "verify-update-source",
            "init",
            "prepare-smoke",
            "prepare-toolchain",
            "register-project",
            "prepare-bootstrap",
            "installed-operator",
            "installation-inputs",
            "prepare-update",
            "recover-update",
            "update-step",
            "update-context",
            "project-request",
        ),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--image")
    parser.add_argument("--bootstrap-profile", type=Path)
    parser.add_argument("--bootstrap-root", type=Path)
    parser.add_argument("--bootstrap-cache", type=Path)
    parser.add_argument("--installation-receipt", type=Path)
    parser.add_argument("--state-report", type=Path)
    parser.add_argument("--update-preparation", type=Path)
    parser.add_argument("--update-preparation-sha256")
    parser.add_argument("--target-version")
    parser.add_argument(
        "--update-step", choices=("capture", "toolchain", "verify", "apply", "restore")
    )
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument("--toolchains", type=Path)
    parser.add_argument("--operator-context", type=Path)
    parser.add_argument("--recover-update", action="store_true")
    parser.add_argument("--host-root", default="/")
    parser.add_argument("--operator-env", type=Path)
    parser.add_argument("--release-source", type=Path)
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
    parser.add_argument("--project-source")
    parser.add_argument("--project-target")
    parser.add_argument("--project-repository")
    parser.add_argument("--project-revision")
    args = parser.parse_args()
    try:
        if args.command == "installation-inputs":
            if not args.installation_receipt:
                raise ContainerInitError("existing installation receipt required")
            installation = read_installation_receipt(
                args.installation_receipt, host_root=args.host_root
            )
            receipt = installation["receipt"]
            print("SAMUEL_INSTALLATION_INPUTS")
            print("\n".join(str(receipt[key]) for key in ("uid", "gid", "port", "project")))
            return 0
        if args.command in {"prepare-update", "recover-update"}:
            if not all(
                (
                    args.bootstrap_profile,
                    args.bootstrap_root,
                    args.bootstrap_cache,
                    args.image,
                    args.target_version
                    if args.command == "prepare-update"
                    else args.update_preparation_sha256,
                    args.state_report,
                )
            ):
                raise ContainerInitError(
                    "bootstrap binding, target and operator state observation required"
                )
            common = dict(
                config_root=Path(args.config_root),
                host_root=args.host_root,
                profile_path=args.bootstrap_profile,
                root_path=args.bootstrap_root,
                cache=args.bootstrap_cache,
                image=args.image,
                state_report=args.state_report,
            )
            if args.command == "prepare-update":
                values = prepare_update_command(**common, target_version=args.target_version)
            else:
                values = prepare_update_recovery(
                    **common, preparation_sha256=args.update_preparation_sha256
                )
            print("SAMUEL_UPDATE_PREPARED")
            print("\n".join(values))
            return 0
        if args.command == "installed-operator":
            if not all(
                (
                    args.bootstrap_profile,
                    args.bootstrap_root,
                    args.bootstrap_cache,
                    args.installation_receipt,
                    args.image,
                )
            ):
                raise ContainerInitError("verified bootstrap and installed receipt required")
            values = installed_operator_inputs(
                profile_path=args.bootstrap_profile,
                root_path=args.bootstrap_root,
                receipt_path=args.installation_receipt,
                cache=args.bootstrap_cache,
                host_root=args.host_root,
                image=args.image,
            )
            print("SAMUEL_INSTALLED_OPERATOR")
            print("\n".join(values))
            return 0
        if args.command == "project-request":
            if not args.operator_env:
                raise ContainerInitError("operator environment required")
            values = project_request_inputs(Path(args.config_root), args.operator_env)
            print("SAMUEL_PROJECT_REQUEST")
            print("\n".join(values))
            return 0
        if args.command == "prepare-bootstrap":
            if not all(
                (args.bootstrap_profile, args.bootstrap_root, args.bootstrap_cache, args.image)
            ):
                raise ContainerInitError("bootstrap profile, root, cache and image are required")
            prepared = prepare_bootstrap(
                args.bootstrap_profile, args.bootstrap_root, args.bootstrap_cache, args.image
            )
            print("SAMUEL_BOOTSTRAP_PREPARED")
            print("\n".join(prepared))
            return 0
        if args.command == "prepare-smoke":
            owner = runtime_owner()
            smoke_config = Path("/prepare/config")
            shutil.copytree(Path("/app/config"), smoke_config)
            (smoke_config / "llm" / "prompts").mkdir(parents=True, exist_ok=True)
            for path in [smoke_config, *smoke_config.rglob("*")]:
                os.chown(path, *owner)
                path.chmod(0o700 if path.is_dir() else 0o600)
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
        if args.release_source:
            from samuel.release_trust import read_release_source

            source = read_release_source(args.release_source)
            if source["bootstrap_manifest_sha256"] != args.manifest_sha256:
                raise ContainerInitError("release source belongs to another bootstrap manifest")
        owner = verify_runtime(manifest)
        if args.command == "update-context":
            if not all(
                (
                    args.update_preparation,
                    args.update_preparation_sha256,
                    args.bootstrap_cache,
                    args.operator_context,
                )
            ):
                raise ContainerInitError("protected update inputs and context required")
            value = read_update_preparation(
                args.update_preparation,
                args.update_preparation_sha256,
                config_root=Path("/prepare/config-root"),
                host_root=args.host_root,
                cache=args.bootstrap_cache,
                manifest_sha256=args.manifest_sha256,
                image=args.image,
                recovery=args.recover_update,
            )
            if (
                value["source_installation"]["receipt"]["uid"],
                value["source_installation"]["receipt"]["gid"],
            ) != owner:
                raise ContainerInitError("target runtime owner differs from the installation")
            source_receipt = value["source_installation"]["receipt"]
            if args.port != source_receipt["port"] or args.project != source_receipt["project"]:
                raise ContainerInitError(
                    "operator port or Compose project differs from the installation"
                )
            if not args.state_report:
                raise ContainerInitError("fresh operator state observation required")
            observed = read_update_state_report(args.state_report)
            configuration = observed.get("configuration", {})
            if not isinstance(configuration, dict):
                raise ContainerInitError("configuration observation unavailable")
            maintenance = configuration.get("maintenance", {})
            if args.recover_update:
                if (
                    configuration.get("phase") != "maintenance"
                    or not isinstance(maintenance, dict)
                    or maintenance.get("binding") != args.update_preparation_sha256
                    or maintenance.get("target") != "production"
                    or maintenance.get("step") != "pending"
                ):
                    raise ContainerInitError("this exact pending update is required")
            elif configuration.get("phase") != "idle" or maintenance != {}:
                raise ContainerInitError("configuration or maintenance pending")
            if observed["schema_version"] != value["source_state_schema"]:
                raise ContainerInitError("actual state schema changed after preparation")
            verify_update_state_identity(value, observed)
            # Internal CLI flags do not turn a saved preparation into authority.
            # Refresh TUF here too, before the prompt, even for direct invocation.
            source_document = json.loads(value["release_source_document"])
            with tempfile.TemporaryDirectory(prefix="samuel-context-trust-") as temporary:
                profile = Path(temporary) / "profile.json"
                root = Path(temporary) / "root.json"
                profile.write_text(json.dumps(source_document["profile"]))
                root.write_text(source_document["root"])
                refresh_update_inputs(
                    value,
                    host_root=args.host_root,
                    profile_path=profile,
                    root_path=root,
                    cache=args.bootstrap_cache,
                    image=source_document["profile"]["bootstrap_image"],
                    source_state_schema=observed["schema_version"],
                )
            context = write_update_context(
                value, destination=args.operator_context, image=args.image, host_root=args.host_root
            )
            selected_path = (
                args.bootstrap_cache
                / "update-captures"
                / args.update_preparation_sha256
                / "selected.json"
            )
            metadata_started = False
            restoration_started = False
            if selected_path.exists() or selected_path.is_symlink():
                capture, _digest = read_update_capture_selection(
                    args.bootstrap_cache, args.update_preparation_sha256
                )
                pending = capture / "metadata-pending.json"
                metadata_started = pending.exists() or pending.is_symlink()
                restoring = capture / "restore-pending.json"
                restoration_started = restoring.exists() or restoring.is_symlink()
            print("SAMUEL_UPDATE_CONTEXT")
            print("\n".join(context))
            print(
                "restoring" if restoration_started else "pending" if metadata_started else "source"
            )
            return 0
        if args.command == "update-step":
            if not all(
                (
                    args.update_step,
                    args.update_preparation,
                    args.update_preparation_sha256,
                    args.bootstrap_cache,
                    args.installer_archive,
                )
            ):
                raise ContainerInitError("fixed update step and protected inputs required")
            step_result = perform_update_step(
                step=args.update_step,
                preparation=args.update_preparation,
                preparation_sha256=args.update_preparation_sha256,
                config_root=Path("/prepare/config-root"),
                data_root=Path("/prepare/data"),
                log_root=Path("/prepare/logs"),
                work_root=Path("/prepare/workspaces"),
                backup_root=Path("/prepare/backups"),
                host_root=args.host_root,
                cache=args.bootstrap_cache,
                manifest_path=args.manifest,
                manifest_sha256=args.manifest_sha256,
                image=args.image,
                installer_archive=args.installer_archive,
                installer_source=args.installer_source,
                backup_receipt=args.backup_receipt,
                toolchains=args.toolchains,
                recovery=args.recover_update,
            )
            print(json.dumps(step_result, sort_keys=True))
            if args.update_step == "restore":
                print(
                    "RESTORE_BACKUP "
                    + step_result["backup_path"]
                    + " "
                    + step_result["backup_digest"]
                )
                print(
                    "RESTORE_SOURCE "
                    + " ".join(
                        step_result[key]
                        for key in ("source_image", "source_revision", "source_version")
                    )
                )
                print("RESTORE_CONTEXT " + step_result["restore_compose"])
                source_kit = step_result["source_installer"]
                print(
                    "RESTORE_INSTALLER "
                    + " ".join(
                        source_kit[key]
                        for key in ("manifest", "manifest_sha256", "archive", "directory")
                    )
                )
            if args.update_step in {"verify", "toolchain", "apply"}:
                binding_path = Path("/prepare/config-root/config/project-binding.json")
                if binding_path.exists():
                    from samuel.core.project_binding import validate_binding

                    binding = validate_binding(json.loads(binding_path.read_bytes()))
                    source_identity = binding["source_identity"]
                    print(
                        "PROJECT_BINDING",
                        binding["host_source"],
                        source_identity["device"],
                        source_identity["inode"],
                        binding["uid"],
                        binding["gid"],
                    )
            return 0
        if args.command == "verify":
            verify_image_inspect(manifest, json.load(sys.stdin), owner)
            print("release identity and non-root image ownership verified")
        else:
            installation_manifest = manifest
            installation_manifest_sha256 = args.manifest_sha256
            installation_compose_source = Path("/bootstrap")
            if args.command == "verify-update-source":
                if not all(
                    (args.update_preparation, args.update_preparation_sha256, args.bootstrap_cache)
                ):
                    raise ContainerInitError("private update preparation and cache required")
                prepared_update = read_update_preparation(
                    args.update_preparation,
                    args.update_preparation_sha256,
                    config_root=Path("/prepare/config-root"),
                    host_root=args.host_root,
                    cache=args.bootstrap_cache,
                    manifest_sha256=args.manifest_sha256,
                    image=args.image,
                )
                source_receipt = prepared_update["source_installation"]["receipt"]
                installation_manifest_sha256 = source_receipt["manifest_sha256"]
                installation_manifest = read_manifest(
                    args.bootstrap_cache / prepared_update["source_installer"]["manifest"],
                    installation_manifest_sha256,
                    source_receipt["image"],
                )
                installation_compose_source = (
                    args.bootstrap_cache / prepared_update["source_installer"]["directory"]
                )
            result = initialize(
                manifest=installation_manifest,
                manifest_sha256=installation_manifest_sha256,
                config_root=Path("/prepare/config-root"),
                data_root=Path("/prepare/data"),
                work_root=Path("/prepare/workspaces"),
                defaults=Path("/app/config"),
                compose_source=installation_compose_source,
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
                existing_only=args.command in {"verify-installed", "verify-update-source"},
            )
            if args.release_source:
                install_release_source(
                    Path("/prepare/config-root"),
                    args.release_source,
                    args.manifest_sha256,
                    owner,
                    allow_create=result == "initialized",
                )
            print(result)
            if args.command == "verify-update-source":
                print("UPDATE_SOURCE", source_receipt["version"], installation_manifest_sha256)
            from samuel.project_binding import register_project, verify_project_registration

            project_binding = verify_project_registration(Path("/prepare/config-root"))
            if project_binding is not None:
                source_identity = project_binding["source_identity"]
                print(
                    "PROJECT_BINDING",
                    project_binding["host_source"],
                    source_identity["device"],
                    source_identity["inode"],
                    project_binding["uid"],
                    project_binding["gid"],
                )
            if args.command == "register-project":
                if not all(
                    (
                        args.project_source,
                        args.project_target,
                        args.project_repository,
                        args.project_revision,
                    )
                ):
                    raise ContainerInitError(
                        "project source, target, repository and initial revision required"
                    )
                register_project(
                    Path("/prepare/config-root"),
                    source=Path("/prepare/project"),
                    host_source=args.project_source,
                    container_target=args.project_target,
                    repository=args.project_repository,
                    revision=args.project_revision,
                )
                print(
                    "Project registered; source unchanged; active I/O and candidate isolation unqualified"
                )
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

                registration_data = verify_registration(Path("/prepare/config-root"))
                if args.command == "verify-update-source" and registration_data is not None:
                    expected_prefix = args.host_root.rstrip("/") + "/srv/samuel/toolchains/"
                    source_root = registration_data["host_root"]
                    toolchain_binding = registration_data["binding"]
                    if (
                        not source_root.startswith(expected_prefix)
                        or re.fullmatch(
                            r"(?:sha256-|update-)[0-9a-f]{64}", source_root[len(expected_prefix) :]
                        )
                        is None
                        or not isinstance(toolchain_binding, dict)
                        or toolchain_binding.get("manifest")
                        != "/opt/samuel-verifier/toolchain-manifest.json"
                        or re.fullmatch(r"[0-9a-f]{64}", str(toolchain_binding.get("sha256", "")))
                        is None
                    ):
                        raise ContainerInitError(
                            "source toolchain is outside this installation's fixed layout"
                        )
                    print("TOOLCHAIN_BINDING", source_root, toolchain_binding["sha256"])
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
    except (
        RuntimeError,
        ImportError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        tarfile.TarError,
    ) as exc:
        print(f"container init failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
