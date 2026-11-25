from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from securesystemslib.signer import CryptoSigner
from tuf.api.exceptions import DownloadHTTPError
from tuf.api.metadata import Metadata, MetaFile, Root, Snapshot, TargetFile, Targets, Timestamp
from tuf.ngclient.fetcher import FetcherInterface

from samuel.release_trust import ReleaseTrustError, fetch_release_target


class Repository(FetcherInterface):
    def __init__(self, tmp_path: Path) -> None:
        self.keys = {
            role: CryptoSigner.generate_ed25519()
            for role in ("root", "targets", "snapshot", "timestamp")
        }
        self.expires = datetime.now(timezone.utc) + timedelta(days=7)
        self.root = Metadata(Root(expires=self.expires))
        for role, key in self.keys.items():
            self.root.signed.add_key(key.public_key, role)
        self.root.sign(self.keys["root"])
        self.anchor = tmp_path / "trusted-root.json"
        self.anchor.write_bytes(self.root.to_bytes())
        self.anchor_hash = hashlib.sha256(self.anchor.read_bytes()).hexdigest()
        self.target = "releases/release-manifest.json"
        self.files: dict[str, bytes] = {}
        self.calls: list[str] = []
        self.publish(b'{"product":"samuel","fixture":true}')
        self.cache = tmp_path / "cache"

    def publish(
        self,
        data: bytes,
        *,
        version: int = 1,
        expired: bool = False,
        extras: dict[str, bytes] | None = None,
    ) -> None:
        self.data = data
        self.target_info = TargetFile.from_data(self.target, data, ["sha256"])
        inputs = {self.target: data, **(extras or {})}
        infos = {
            name: TargetFile.from_data(name, content, ["sha256"])
            for name, content in inputs.items()
        }
        targets = Metadata(Targets(version=version, expires=self.expires, targets=infos))
        targets.sign(self.keys["targets"])
        target_bytes = targets.to_bytes()
        snapshot = Metadata(
            Snapshot(
                version=version,
                expires=self.expires,
                meta={"targets.json": MetaFile.from_data(version, target_bytes, ["sha256"])},
            )
        )
        snapshot.sign(self.keys["snapshot"])
        snapshot_bytes = snapshot.to_bytes()
        expires = datetime.now(timezone.utc) - timedelta(days=1) if expired else self.expires
        timestamp = Metadata(
            Timestamp(
                version=version,
                expires=expires,
                snapshot_meta=MetaFile.from_data(version, snapshot_bytes, ["sha256"]),
            )
        )
        timestamp.sign(self.keys["timestamp"])
        self.files.update(
            {
                f"metadata/{version}.targets.json": target_bytes,
                f"metadata/{version}.snapshot.json": snapshot_bytes,
                "metadata/timestamp.json": timestamp.to_bytes(),
            }
        )

        for name, content in inputs.items():
            prefix, basename = name.rsplit("/", 1) if "/" in name else ("", name)
            path = f"{prefix}/" if prefix else ""
            self.files[f"targets/{path}{infos[name].hashes['sha256']}.{basename}"] = content

    def _fetch(self, url: str) -> Iterator[bytes]:
        path = urlsplit(url).path.lstrip("/")
        self.calls.append(path)
        if path not in self.files:
            raise DownloadHTTPError("fixture not found", 404)
        yield self.files[path]

    def retrieve(self, **overrides: Any) -> dict[str, Any]:
        args = {
            "root_path": self.anchor,
            "root_sha256": self.anchor_hash,
            "metadata_url": "https://repository.example.test/metadata/",
            "targets_url": "https://repository.example.test/targets/",
            "cache_dir": self.cache,
            "target": self.target,
            "fetcher": self,
        }
        args.update(overrides)
        return fetch_release_target(**args)


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    return Repository(tmp_path)


def test_verified_fetch_preserves_artifact_name_and_requires_no_runtime_setup(
    repository: Repository,
) -> None:
    result = repository.retrieve()
    assert Path(result["path"]).read_bytes() == repository.data
    assert Path(result["path"]).name == "release-manifest.json"
    assert result["sha256"] == hashlib.sha256(repository.data).hexdigest()
    assert result["verification"] == "tuf_signed_target"
    assert result["initial_handoff"] == "not_qualified_by_this_check"
    assert result["installation_performed"] is False
    assert (repository.cache.stat().st_mode & 0o777) == 0o700


@pytest.mark.parametrize("root_hash", ["", "invalid", "0" * 64])
def test_root_binding_fails_before_network_or_cache_mutation(
    repository: Repository, root_hash: str
) -> None:
    with pytest.raises(ReleaseTrustError):
        repository.retrieve(root_sha256=root_hash)
    assert not repository.calls and not repository.cache.exists()


def test_replacing_root_and_untrusted_adjacent_hash_does_not_replace_external_binding(
    repository: Repository,
) -> None:
    other = CryptoSigner.generate_ed25519()
    forged = copy.deepcopy(repository.root)
    forged.signed.revoke_key(repository.keys["root"].public_key.keyid, "root")
    forged.signed.add_key(other.public_key, "root")
    forged.sign(other)
    repository.anchor.write_bytes(forged.to_bytes())
    repository.anchor.with_suffix(".sha256").write_text(
        hashlib.sha256(forged.to_bytes()).hexdigest()
    )
    with pytest.raises(ReleaseTrustError, match="binding mismatch"):
        repository.retrieve()
    assert not repository.calls


def test_root_requires_valid_signature_threshold_even_when_bytes_match(
    repository: Repository,
) -> None:
    second = CryptoSigner.generate_ed25519()
    repository.root.signed.add_key(second.public_key, "root")
    repository.root.signed.roles["root"].threshold = 2
    repository.root.sign(repository.keys["root"])
    repository.anchor.write_bytes(repository.root.to_bytes())
    repository.anchor_hash = hashlib.sha256(repository.anchor.read_bytes()).hexdigest()
    with pytest.raises(ReleaseTrustError, match="UnsignedMetadataError"):
        repository.retrieve()
    assert not repository.calls


@pytest.mark.parametrize("failure", ["expired", "signature", "artifact", "missing"])
def test_unverified_inputs_never_publish_an_artifact(repository: Repository, failure: str) -> None:
    if failure == "expired":
        repository.publish(repository.data, expired=True)
    elif failure == "signature":
        doc = Metadata.from_bytes(repository.files["metadata/timestamp.json"])
        doc.sign(CryptoSigner.generate_ed25519())
        repository.files["metadata/timestamp.json"] = doc.to_bytes()
    elif failure == "artifact":
        key = next(k for k in repository.files if k.startswith("targets/"))
        repository.files[key] = b"x" * len(repository.data)
    else:
        repository.target = "releases/missing.json"
    with pytest.raises(ReleaseTrustError):
        repository.retrieve()
    assert not list((repository.cache / "artifacts").rglob("release-manifest.json"))


def test_timestamp_rollback_is_rejected_across_client_restarts(repository: Repository) -> None:
    old = repository.files["metadata/timestamp.json"]
    repository.retrieve()
    repository.publish(b"new verified release", version=2)
    repository.retrieve()
    repository.files["metadata/timestamp.json"] = old
    with pytest.raises(ReleaseTrustError, match="BadVersionNumberError"):
        repository.retrieve()


def test_forged_cached_root_cannot_authorize_a_different_repository(
    repository: Repository, tmp_path: Path
) -> None:
    previous = repository.retrieve()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other = Repository(other_dir)
    other.publish(b"attacker artifact")
    (repository.cache / "metadata/root.json").write_bytes(other.anchor.read_bytes())
    repository.files = other.files
    with pytest.raises(ReleaseTrustError):
        repository.retrieve()
    assert Path(previous["path"]).read_bytes() == repository.data


@pytest.mark.parametrize("old_signature", [True, False])
def test_root_rotation_requires_both_old_and_new_authority(
    repository: Repository, old_signature: bool
) -> None:
    new_key = CryptoSigner.generate_ed25519()
    rotated = copy.deepcopy(repository.root)
    rotated.signed.version = 2
    rotated.signed.revoke_key(repository.keys["root"].public_key.keyid, "root")
    rotated.signed.add_key(new_key.public_key, "root")
    rotated.sign(new_key)
    if old_signature:
        rotated.sign(repository.keys["root"], append=True)
    repository.files["metadata/2.root.json"] = rotated.to_bytes()
    if old_signature:
        result = repository.retrieve()
        assert Path(result["path"]).read_bytes() == repository.data
    else:
        with pytest.raises(ReleaseTrustError, match="UnsignedMetadataError"):
            repository.retrieve()


def test_failed_download_keeps_previous_artifact_and_unlocks_cache(repository: Repository) -> None:
    first = repository.retrieve()
    path = Path(first["path"])
    key = next(k for k in repository.files if k.startswith("targets/"))
    original = repository.files[key]
    repository.files[key] = b"corrupt"
    with pytest.raises(ReleaseTrustError):
        repository.retrieve()
    assert path.read_bytes() == original
    repository.files[key] = original
    assert repository.retrieve()["path"] == first["path"]


def test_failed_cache_publication_preserves_old_bytes_and_can_retry(
    repository: Repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = repository.retrieve()
    destination = Path(previous["path"])
    replace = os.replace

    def fail_publication(source: Any, target: Any) -> None:
        if Path(target) == destination:
            raise OSError("fixture: cache publication failed")
        replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr("samuel.release_trust.os.replace", fail_publication)
        with pytest.raises(OSError, match="publication failed"):
            repository.retrieve()
    assert destination.read_bytes() == repository.data
    assert not list((repository.cache / "artifacts").glob(".fetch-*"))
    assert repository.retrieve()["path"] == previous["path"]


@pytest.mark.parametrize(
    "target", ["../root.json", "/root.json", "a/../b", "a\\b", "a?x=1", "a/%2e%2e/b"]
)
def test_target_path_cannot_escape_release_cache(repository: Repository, target: str) -> None:
    with pytest.raises(ReleaseTrustError, match="safe relative"):
        repository.retrieve(target=target)
    assert not repository.calls and not repository.cache.exists()


def test_root_cannot_be_a_symlink_or_reside_in_cache(
    repository: Repository, tmp_path: Path
) -> None:
    link = tmp_path / "link.json"
    link.symlink_to(repository.anchor)
    with pytest.raises(OSError):
        repository.retrieve(root_path=link)
    with pytest.raises(ReleaseTrustError, match="outside"):
        repository.retrieve(cache_dir=tmp_path)
    assert not repository.calls


def test_parallel_fetch_is_rejected_without_network_activity(repository: Repository) -> None:
    repository.cache.mkdir(mode=0o700)
    with (repository.cache / ".fetch.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ReleaseTrustError, match="another release fetch"):
            repository.retrieve()
    assert not repository.calls
    repository.retrieve()


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/metadata",
        "https://user:secret@example.test/",
        "http://example.test/?token=secret",
        "http://example.test/#root",
        "http://example.test/\nmetadata",
    ],
)
def test_repository_urls_cannot_smuggle_credentials_or_local_paths(
    repository: Repository, url: str
) -> None:
    with pytest.raises(ReleaseTrustError, match="explicit HTTP"):
        repository.retrieve(metadata_url=url)
    assert not repository.calls and not repository.cache.exists()


def test_unprotected_or_linked_cache_is_rejected(repository: Repository, tmp_path: Path) -> None:
    repository.cache.mkdir(mode=0o700)
    # mkdir applies the operator's umask. Exercise an actually non-private cache.
    repository.cache.chmod(0o755)
    with pytest.raises(ReleaseTrustError, match="private"):
        repository.retrieve()
    repository.cache.chmod(0o700)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (repository.cache / "metadata").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReleaseTrustError, match="private"):
        repository.retrieve()
    assert not list(outside.iterdir()) and not repository.calls


def test_cli_fetches_over_explicit_http_without_claiming_transport_or_initial_trust(
    repository: Repository, tmp_path: Path
) -> None:
    served = tmp_path / "repository"
    for name, value in repository.files.items():
        path = served / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(served))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        result = subprocess.run(
            [
                str(Path(sys.prefix) / "bin/samuel-release"),
                "fetch",
                "--trust-root",
                str(repository.anchor),
                "--trust-root-sha256",
                repository.anchor_hash,
                "--metadata-url",
                base + "/metadata/",
                "--targets-url",
                base + "/targets/",
                "--cache-dir",
                str(repository.cache),
                "--target",
                repository.target,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        receipt = json.loads(result.stdout)
        assert Path(receipt["path"]).read_bytes() == repository.data
        assert receipt["initial_handoff"] == "not_qualified_by_this_check"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
