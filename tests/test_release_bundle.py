from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from samuel.release_trust import ReleaseTrustError, fetch_release_inputs
from tests.test_release_trust import Repository


def _bundle(repository: Repository) -> tuple[dict[str, Any], dict[str, bytes]]:
    assets = {f"artifact-{i}.tar.gz": f"release input {i}".encode() for i in range(7)}
    manifest = {
        "schema_version": 2,
        "product": "samuel",
        "version": "2.0.0a34",
        "tag": "v2.0.0a34",
        "commit": "a" * 40,
        "artifacts": [
            {"name": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in assets.items()
        ],
    }
    return manifest, assets


def _publish(repository: Repository, manifest: Any, assets: dict[str, bytes]) -> None:
    repository.publish(
        json.dumps(manifest).encode(), extras={"releases/" + k: v for k, v in assets.items()}
    )


def _retrieve(repository: Repository) -> dict[str, Any]:
    return fetch_release_inputs(
        root_path=repository.anchor,
        root_sha256=repository.anchor_hash,
        metadata_url="https://repository.example.test/metadata/",
        targets_url="https://repository.example.test/targets/",
        cache_dir=repository.cache,
        target=repository.target,
        fetcher=repository,
    )


def test_signed_release_fetches_every_bound_input_without_installing(tmp_path: Path) -> None:
    repository = Repository(tmp_path)
    manifest, assets = _bundle(repository)
    _publish(repository, manifest, assets)
    receipt = _retrieve(repository)
    assert receipt["version"] == manifest["version"]
    assert receipt["revision"] == manifest["commit"]
    assert receipt["verification"] == "tuf_signed_manifest_and_bound_artifacts"
    assert receipt["initial_handoff"] == "not_qualified_by_this_check"
    assert receipt["installation_performed"] is False
    assert json.loads(Path(receipt["manifest"]["path"]).read_bytes()) == manifest
    assert {
        Path(r["path"]).name: Path(r["path"]).read_bytes() for r in receipt["artifacts"]
    } == assets
    assert not (tmp_path / "config").exists() and not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    "failure",
    [
        "product",
        "version",
        "missing-version",
        "tag",
        "tag-type",
        "revision",
        "schema",
        "bool-schema",
        "empty",
        "duplicate",
        "traversal",
        "hash",
        "negative-size",
        "bool-size",
        "self-reference",
        "not-object",
        "artifact-not-object",
    ],
)
def test_invalid_signed_manifest_rejected_before_any_artifact_fetch(
    tmp_path: Path, failure: str
) -> None:
    repository = Repository(tmp_path)
    manifest, assets = _bundle(repository)
    if failure in {"product", "version", "tag"}:
        manifest[failure] = "invalid"
    elif failure == "missing-version":
        del manifest["version"]
    elif failure == "tag-type":
        manifest["tag"] = None
    elif failure == "revision":
        manifest["commit"] = "abc"
    elif failure in {"schema", "bool-schema"}:
        manifest["schema_version"] = 99 if failure == "schema" else True
    elif failure == "empty":
        manifest["artifacts"] = []
    elif failure == "duplicate":
        manifest["artifacts"].append(manifest["artifacts"][0])
    elif failure in {"traversal", "self-reference"}:
        manifest["artifacts"][-1]["name"] = (
            "../evil" if failure == "traversal" else "release-manifest.json"
        )
    elif failure == "hash":
        manifest["artifacts"][-1]["sha256"] = "invalid"
    elif failure in {"negative-size", "bool-size"}:
        manifest["artifacts"][-1]["size"] = -1 if failure == "negative-size" else True
    elif failure == "artifact-not-object":
        manifest["artifacts"].append("bad")
    payload: Any = [] if failure == "not-object" else manifest
    _publish(repository, payload, assets)
    with pytest.raises(ReleaseTrustError):
        _retrieve(repository)
    assert all(
        p.endswith(".release-manifest.json") for p in repository.calls if p.startswith("targets/")
    )
    assert not list((repository.cache / "artifacts").rglob("artifact-*"))


@pytest.mark.parametrize(
    "failure", ["manifest-hash", "manifest-size", "tampered-target", "missing-target"]
)
def test_incomplete_or_inconsistent_release_never_returns_complete_receipt(
    tmp_path: Path, failure: str
) -> None:
    repository = Repository(tmp_path)
    manifest, assets = _bundle(repository)
    last = manifest["artifacts"][-1]
    if failure == "manifest-hash":
        last["sha256"] = "0" * 64
    elif failure == "manifest-size":
        last["size"] += 1
    elif failure == "missing-target":
        del assets[last["name"]]
    _publish(repository, manifest, assets)
    if failure == "tampered-target":
        key = next(k for k in repository.files if k.endswith("." + last["name"]))
        repository.files[key] = b"forged"
    with pytest.raises(ReleaseTrustError):
        _retrieve(repository)
    first = manifest["artifacts"][0]
    assert (
        repository.cache / "artifacts" / first["sha256"] / first["name"]
    ).read_bytes() == assets[first["name"]]
    assert not (repository.cache / "current").exists()


def test_installed_cli_fetches_complete_release_over_explicit_transport(tmp_path: Path) -> None:
    repository = Repository(tmp_path)
    manifest, assets = _bundle(repository)
    _publish(repository, manifest, assets)
    served = tmp_path / "served"
    for name, content in repository.files.items():
        path = served / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
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
                "--release",
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
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        receipt = json.loads(result.stdout)
        assert len(receipt["artifacts"]) == 7
        assert receipt["initial_handoff"] == "not_qualified_by_this_check"
        assert receipt["installation_performed"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_generated_oci_kit_remains_accepted_by_existing_installer_checks(tmp_path: Path) -> None:
    from tests.test_container_init import IMAGE, ROOT, _published_kit
    from tools.container_init import read_manifest, verify_delivery

    repository = Repository(tmp_path)
    published = tmp_path / "published"
    published.mkdir()
    manifest, archive = _published_kit(published)
    assets = {
        item["name"]: (published / item["name"]).read_bytes() for item in manifest["artifacts"]
    }
    _publish(repository, manifest, assets)
    result = _retrieve(repository)
    received = read_manifest(Path(result["manifest"]["path"]), result["manifest"]["sha256"], IMAGE)
    fetched_archive = next(
        Path(item["path"])
        for item in result["artifacts"]
        if Path(item["path"]).name == archive.name
    )
    verify_delivery(received, fetched_archive, ROOT)
    assert len(result["artifacts"]) == 3
    assert result["installation_performed"] is False
