"""Fetch signed release inputs; never install, activate, or establish first trust."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tuf.api.exceptions import DownloadError, RepositoryError
from tuf.ngclient import Updater, UpdaterConfig
from tuf.ngclient.fetcher import FetcherInterface


class ReleaseTrustError(RuntimeError):
    """Release input verification failed; no installation action is authorized."""


def _base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ReleaseTrustError("explicit HTTP(S) repository URL without credentials required")
    return value.rstrip("/") + "/"


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ReleaseTrustError("release cache directories must be private and owned by the caller")


def validate_release_profile(value: Any) -> dict[str, Any]:
    """Validate operator-supplied source data; select no channel or trust anchor."""
    fields = {
        "schema_version",
        "bootstrap_image",
        "trust_root_sha256",
        "metadata_url",
        "targets_url",
        "manifest_target",
    }
    if (
        not isinstance(value, dict)
        or not fields <= set(value)
        or set(value) - fields - {"manifest_target_template"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or any(not isinstance(v, str) for k, v in value.items() if k != "schema_version")
    ):
        raise ReleaseTrustError("invalid release source profile")
    if (
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", value["bootstrap_image"])
        is None
        or re.fullmatch(r"[0-9a-f]{64}", value["trust_root_sha256"]) is None
    ):
        raise ReleaseTrustError("release source requires immutable verifier and root bindings")
    _base_url(value["metadata_url"])
    _base_url(value["targets_url"])
    _validate_target(value["manifest_target"])
    if "manifest_target_template" in value:
        template = value["manifest_target_template"]
        if template.count("{version}") != 1:
            raise ReleaseTrustError("release target template requires exactly one {version}")
        _validate_target(template.replace("{version}", "2.0.0a34"))
    return dict(value)


def _validate_target(target: str) -> None:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*", target) is None:
        raise ReleaseTrustError("target must be a safe relative release artifact path")


def release_manifest_target(profile: dict[str, Any], version: str | None = None) -> str:
    profile = validate_release_profile(profile)
    if version is None:
        return str(profile["manifest_target"])
    from samuel.build_info import product_version_from_tag

    if not isinstance(version, str) or product_version_from_tag(f"v{version}") != version:
        raise ReleaseTrustError("canonical target release version required")
    template = profile.get("manifest_target_template")
    if not template:
        raise ReleaseTrustError("operator has not configured release target resolution")
    return str(template.replace("{version}", version))


def release_source_document(profile: dict[str, Any], root: bytes, manifest_sha256: str) -> bytes:
    profile = validate_release_profile(profile)
    if (
        len(root) > UpdaterConfig().root_max_length
        or hashlib.sha256(root).hexdigest() != profile["trust_root_sha256"]
        or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
    ):
        raise ReleaseTrustError("release source root or manifest binding differs")
    return (
        json.dumps(
            {
                "schema": "release-source.v1",
                "profile": profile,
                "root": root.decode("utf-8"),
                "bootstrap_manifest_sha256": manifest_sha256,
                "initial_handoff": "not_qualified_by_this_check",
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()


def read_release_input(
    path: Path,
    *,
    expected_owner: tuple[int, int] | None,
    max_length: int,
    label: str,
) -> bytes:
    """Read bounded bytes with ownership and drift checks on the opened file."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ReleaseTrustError(f"{label} must be a regular file")
        if expected_owner is not None and (
            (before.st_uid, before.st_gid) != expected_owner or before.st_mode & 0o077
        ):
            raise ReleaseTrustError(f"operator {label} owner or private permissions differ")
        raw = stream.read(max_length + 1)
        after = os.fstat(stream.fileno())
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ReleaseTrustError(f"{label} changed while reading")
    if len(raw) > max_length:
        raise ReleaseTrustError(f"{label} exceeds size limit")
    return raw


def read_release_source(
    path: Path, *, expected_owner: tuple[int, int] | None = None
) -> dict[str, Any]:
    """Read one source snapshot; privileged callers must require their fixed owner.

    The descriptor check applies to the bytes actually read, not a prior path
    stat. It does not establish first trust or validate installation identity.
    """
    raw = read_release_input(
        path,
        expected_owner=expected_owner,
        max_length=4 * UpdaterConfig().root_max_length,
        label="release source",
    )
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or set(value)
        != {"schema", "profile", "root", "bootstrap_manifest_sha256", "initial_handoff"}
        or value["schema"] != "release-source.v1"
        or value["initial_handoff"] != "not_qualified_by_this_check"
        or not isinstance(value["root"], str)
        or not isinstance(value["bootstrap_manifest_sha256"], str)
    ):
        raise ReleaseTrustError("invalid release source document")
    release_source_document(
        value["profile"], value["root"].encode(), value["bootstrap_manifest_sha256"]
    )
    return value


def fetch_release_target(
    *,
    root_path: Path,
    root_sha256: str,
    metadata_url: str,
    targets_url: str,
    cache_dir: Path,
    target: str,
    fetcher: FetcherInterface | None = None,
) -> dict[str, Any]:
    """Verify one target against an independently supplied bootstrap root binding.

    The caller owns qualification of the bootstrap/root handoff. A matching
    digest here is only a byte binding, not evidence of an authenticated handoff.
    Cached metadata cannot replace this explicit anchor on subsequent calls.
    """
    if re.fullmatch(r"[0-9a-f]{64}", root_sha256) is None:
        raise ReleaseTrustError("an independently supplied initial root SHA-256 is required")
    _validate_target(target)
    metadata_url, targets_url = _base_url(metadata_url), _base_url(targets_url)
    if root_path.resolve().is_relative_to(cache_dir.resolve()):
        raise ReleaseTrustError("bootstrap root must be outside the writable release cache")
    limits = UpdaterConfig()
    descriptor = os.open(root_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ReleaseTrustError("bootstrap root must be a regular file")
        root = stream.read(limits.root_max_length + 1)
    if len(root) > limits.root_max_length or not hmac.compare_digest(
        hashlib.sha256(root).hexdigest(), root_sha256
    ):
        raise ReleaseTrustError("bootstrap root size or SHA-256 binding mismatch")

    _private_directory(cache_dir)
    descriptor = os.open(
        cache_dir / ".fetch.lock",
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ReleaseTrustError("release cache lock must be a regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReleaseTrustError("another release fetch is using this cache") from exc
        metadata_dir, artifacts_dir = cache_dir / "metadata", cache_dir / "artifacts"
        _private_directory(metadata_dir)
        _private_directory(artifacts_dir)
        try:
            updater = Updater(
                str(metadata_dir),
                metadata_url,
                target_base_url=targets_url,
                bootstrap=root,
                fetcher=fetcher,
                config=limits,
            )
            updater.refresh()
            info = updater.get_targetinfo(target)
            if info is None:
                raise ReleaseTrustError("requested artifact is absent from verified TUF metadata")
            digest = info.hashes.get("sha256", "")
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ReleaseTrustError("release artifact requires a signed SHA-256 binding")
            destination_dir = artifacts_dir / digest
            _private_directory(destination_dir)
            destination = destination_dir / target.rsplit("/", 1)[-1]
            # The library verifies bytes before this atomic publication. A failed
            # fetch preserves any previous artifact and all anti-rollback metadata.
            with tempfile.TemporaryDirectory(prefix=".fetch-", dir=artifacts_dir) as temporary:
                staged = Path(temporary) / "artifact"
                updater.download_target(info, filepath=str(staged))
                with staged.open("rb") as stream:
                    os.fsync(stream.fileno())
                os.replace(staged, destination)
            return {
                "target": target,
                "path": str(destination.resolve()),
                "sha256": digest,
                "length": info.length,
                "root_sha256": root_sha256,
                "verification": "tuf_signed_target",
                "initial_handoff": "not_qualified_by_this_check",
                "installation_performed": False,
            }
        except (DownloadError, RepositoryError, ValueError) as exc:
            raise ReleaseTrustError(
                f"TUF verification failed ({type(exc).__name__}): {exc}"
            ) from exc
    finally:
        os.close(descriptor)


def fetch_release_inputs(
    *,
    root_path: Path,
    root_sha256: str,
    metadata_url: str,
    targets_url: str,
    cache_dir: Path,
    target: str,
    fetcher: FetcherInterface | None = None,
) -> dict[str, Any]:
    """Fetch a signed manifest and its signed, manifest-bound sibling artifacts.

    A partial failure leaves verified cache entries, but never a complete receipt.
    This does not unpack, install, authorize activation, or qualify first trust.
    """
    from samuel.build_info import product_version_from_tag
    from samuel.local_release import LocalReleaseError, verify_manifest_artifact

    def retrieve(name: str) -> dict[str, Any]:
        return fetch_release_target(
            root_path=root_path,
            root_sha256=root_sha256,
            metadata_url=metadata_url,
            targets_url=targets_url,
            cache_dir=cache_dir,
            target=name,
            fetcher=fetcher,
        )

    manifest_receipt = retrieve(target)
    try:
        manifest = json.loads(Path(manifest_receipt["path"]).read_bytes())
        if not isinstance(manifest, dict):
            raise ValueError("release manifest must be an object")
        version = product_version_from_tag(manifest.get("tag", ""))
        if (
            version is None
            or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] not in {1, 2}
            or manifest.get("product") != "samuel"
            or manifest.get("version") != version
            or not isinstance(manifest.get("commit"), str)
            or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", manifest["commit"]) is None
        ):
            raise ValueError("release manifest identity or schema is invalid")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("release manifest must bind artifacts")
        names: set[str] = {target.rsplit("/", 1)[-1]}
        # Validate the entire list before fetching anything referenced by it.
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise ValueError("release artifact must be an object")
            name, digest, size = artifact.get("name"), artifact.get("sha256"), artifact.get("size")
            if (
                not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) is None
                or name in names
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or type(size) is not int
                or size < 0
            ):
                raise ValueError("release artifact name, digest or size is invalid")
            names.add(name)
        prefix = target.rsplit("/", 1)[0] + "/" if "/" in target else ""
        receipts = []
        for artifact in artifacts:
            receipt = retrieve(prefix + artifact["name"])
            verify_manifest_artifact(manifest, Path(receipt["path"]))
            receipts.append(receipt)
        return {
            "version": version,
            "revision": manifest["commit"],
            "manifest": manifest_receipt,
            "artifacts": receipts,
            "verification": "tuf_signed_manifest_and_bound_artifacts",
            "initial_handoff": "not_qualified_by_this_check",
            "installation_performed": False,
        }
    except (TypeError, ValueError, LocalReleaseError) as exc:
        raise ReleaseTrustError(f"release input verification failed: {exc}") from exc
