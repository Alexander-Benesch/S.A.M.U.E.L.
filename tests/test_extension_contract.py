from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from samuel.extensions import (
    CAPABILITY_ID,
    ArtifactReference,
    CapabilityManifest,
    CapabilityPolicy,
    ExtensionRequest,
    ExtensionResult,
    canonical_contract_bytes,
    contract_digest,
    load_capability_manifest,
    load_extension_policy,
    load_extension_result,
    resolve_capability,
    validate_result_binding,
    verify_artifact_reference,
)
from samuel.extensions.cli import main as extension_main
from samuel.extensions.contract import MAX_CONTRACT_BYTES, ContractError

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests/fixtures/external_documentation_consumer"
SHA = "1" * 40
DIGEST = "sha256:" + "2" * 64


def _manifest() -> CapabilityManifest:
    return CapabilityManifest.model_validate_json((FIXTURE / "capability.json").read_text())


def _request() -> ExtensionRequest:
    return ExtensionRequest(
        schema="samuel-extension-request.v1",
        capability_id=CAPABILITY_ID,
        contract_version="1.0",
        request_id="fixture-1",
        subject={"repository": "example/docs", "head_sha": SHA},
        claim_family="documentation.inventory.v1",
        effect="advisory",
        policy_digest=DIGEST,
        input_artifact={
            "path": "request-payload.json",
            "digest": DIGEST,
            "size_bytes": 17,
            "media_type": "application/json",
        },
    )


def test_shipped_configuration_is_optional_disabled_and_installation_does_not_activate() -> None:
    policy = load_extension_policy(ROOT / "config/extensions.json")

    resolution = resolve_capability(policy, manifest_path=FIXTURE / "capability.json")

    assert policy == CapabilityPolicy(
        enabled=False,
        required=False,
        contract_version="1.0",
        manifest_path=None,
    )
    assert resolution.status == "disabled"
    assert resolution.available is False
    assert resolution.blocked is False


def test_missing_operator_file_preserves_optional_disabled_default(tmp_path: Path) -> None:
    policy = load_extension_policy(tmp_path / "extensions.json")

    assert policy == CapabilityPolicy()
    assert resolve_capability(policy).status == "disabled"


@pytest.mark.parametrize(
    ("policy", "manifest", "status", "blocked"),
    [
        (CapabilityPolicy(enabled=False, required=True), None, "disabled", True),
        (CapabilityPolicy(enabled=True, required=False), None, "absent", False),
        (CapabilityPolicy(enabled=True, required=True), None, "absent", True),
    ],
)
def test_required_and_optional_absence_are_distinct(
    policy: CapabilityPolicy,
    manifest: Path | None,
    status: str,
    blocked: bool,
) -> None:
    resolution = resolve_capability(policy, manifest_path=manifest)

    assert resolution.status == status
    assert resolution.blocked is blocked
    assert resolution.available is False


def test_enabled_compatible_manifest_is_available() -> None:
    resolution = resolve_capability(
        CapabilityPolicy(enabled=True),
        manifest_path=FIXTURE / "capability.json",
    )

    assert resolution.status == "available"
    assert resolution.available is True
    assert resolution.manifest == _manifest()


def test_incompatible_manifest_blocks_only_when_required(tmp_path: Path) -> None:
    value = json.loads((FIXTURE / "capability.json").read_text())
    value["contract_version"] = "2.0"
    manifest = tmp_path / "capability.json"
    manifest.write_text(json.dumps(value), encoding="utf-8")

    optional = resolve_capability(CapabilityPolicy(enabled=True), manifest_path=manifest)
    required = resolve_capability(
        CapabilityPolicy(enabled=True, required=True), manifest_path=manifest
    )

    assert optional.status == required.status == "incompatible"
    assert optional.blocked is False
    assert required.blocked is True


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"unknown": True}),
        lambda value: value.update({"effect": "required"}),
        lambda value: value.update({"credentials": ["SCM_TOKEN"]}),
        lambda value: value.update({"permissions": ["repository:write"]}),
        lambda value: value.update({"claim_families": []}),
    ],
)
def test_manifest_is_closed_advisory_and_minimal(tmp_path: Path, mutation) -> None:
    value = json.loads((FIXTURE / "capability.json").read_text())
    mutation(value)
    path = tmp_path / "capability.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ContractError):
        load_capability_manifest(path)


def test_contract_loader_rejects_duplicate_keys_symlinks_and_large_inputs(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    with pytest.raises(ContractError, match="duplicate JSON key"):
        load_capability_manifest(duplicate)

    link = tmp_path / "link.json"
    link.symlink_to(FIXTURE / "capability.json")
    with pytest.raises(ContractError, match="symlink"):
        load_capability_manifest(link)

    large = tmp_path / "large.json"
    large.write_bytes(b" " * (MAX_CONTRACT_BYTES + 1))
    with pytest.raises(ContractError, match="exceeds"):
        load_capability_manifest(large)


@pytest.mark.parametrize("path", ["../claims.json", "/claims.json", "a/../claims.json", "a\\b"])
def test_artifact_paths_are_bounded(path: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            path=path,
            digest=DIGEST,
            size_bytes=1,
            media_type="application/json",
        )


def test_external_fixture_uses_only_public_namespace_and_round_trips(tmp_path: Path) -> None:
    script = FIXTURE / "consumer.py"
    imports = {
        alias.name
        for node in ast.walk(ast.parse(script.read_text(encoding="utf-8")))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(ast.parse(script.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(
        name.startswith(("samuel.slices", "samuel.adapters", "samuel.core")) for name in imports
    )
    assert "samuel.extensions" in imports

    payload = b'{"documents":[]}'
    request = _request().model_copy(
        update={
            "input_artifact": ArtifactReference(
                path="request-payload.json",
                digest=f"sha256:{hashlib.sha256(payload).hexdigest()}",
                size_bytes=len(payload),
                media_type="application/json",
            )
        }
    )
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (tmp_path / "request-payload.json").write_bytes(payload)
    output_path = tmp_path / "result.json"

    completed = subprocess.run(
        [sys.executable, str(script), str(request_path), str(output_path)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )

    assert completed.returncode == 0, completed.stderr
    result = load_extension_result(output_path)
    validate_result_binding(request, result)
    assert result.effect == "advisory"
    assert result.status == "passed"


def test_artifact_verification_rejects_content_drift_and_symlink(tmp_path: Path) -> None:
    content = b'{"claims":[]}'
    target = tmp_path / "claims.json"
    target.write_bytes(content)
    reference = ArtifactReference(
        path="claims.json",
        digest=f"sha256:{hashlib.sha256(content).hexdigest()}",
        size_bytes=len(content),
        media_type="application/json",
    )
    assert verify_artifact_reference(tmp_path, reference) == target

    target.write_bytes(content + b"\n")
    with pytest.raises(ContractError, match="size does not match"):
        verify_artifact_reference(tmp_path, reference)

    target.unlink()
    real = tmp_path / "real.json"
    real.write_bytes(content)
    target.symlink_to(real)
    with pytest.raises(ContractError, match="symlink"):
        verify_artifact_reference(tmp_path, reference)


def test_result_cannot_be_replayed_for_other_request_or_subject() -> None:
    request = _request()
    result = ExtensionResult(
        schema="samuel-extension-result.v1",
        capability_id=CAPABILITY_ID,
        contract_version="1.0",
        request_id=request.request_id,
        request_digest=contract_digest(request),
        subject=request.subject,
        claim_family=request.claim_family,
        effect="advisory",
        status="passed",
        output_artifact={
            "path": "claims.json",
            "digest": DIGEST,
            "size_bytes": 1,
            "media_type": "application/json",
        },
    )
    validate_result_binding(request, result)

    changed = request.model_copy(update={"request_id": "fixture-2"})
    with pytest.raises(ContractError, match="exact bound request"):
        validate_result_binding(changed, result)


def test_contract_digest_uses_language_neutral_sorted_canonical_json() -> None:
    request = _request()
    expected = json.dumps(
        request.model_dump(exclude_none=True, by_alias=True, mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert canonical_contract_bytes(request) == expected
    assert contract_digest(request) == f"sha256:{hashlib.sha256(expected).hexdigest()}"


def test_cli_status_is_fail_closed_only_for_required_capability(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    optional = tmp_path / "optional.json"
    optional.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "capabilities": {
                    CAPABILITY_ID: {
                        "enabled": True,
                        "required": False,
                        "contract_version": "1.0",
                        "manifest_path": None,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert extension_main(["status", "--config", str(optional)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "absent"

    value = json.loads(optional.read_text(encoding="utf-8"))
    value["capabilities"][CAPABILITY_ID]["required"] = True
    optional.write_text(json.dumps(value), encoding="utf-8")
    assert extension_main(["status", "--config", str(optional)]) == 1
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["blocked"] is True
    assert blocked["status"] == "absent"


@pytest.mark.parametrize(
    ("filename", "model"),
    [
        ("capability-manifest.v1.json", CapabilityManifest),
        ("request.v1.json", ExtensionRequest),
        ("result.v1.json", ExtensionResult),
    ],
)
def test_packaged_json_schemas_match_public_models(filename: str, model: type[BaseModel]) -> None:
    checked_in = json.loads((ROOT / "samuel/extensions/schemas" / filename).read_text())

    assert checked_in == model.model_json_schema(by_alias=True, mode="validation")
