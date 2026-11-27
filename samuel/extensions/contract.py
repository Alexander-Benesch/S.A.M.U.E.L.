"""Versioned JSON boundary for the first external data consumer.

The contract is intentionally data-only.  A manifest describes compatibility;
requests and results bind artifacts.  Nothing in this module discovers,
imports, installs, starts, or trusts external code.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator

CAPABILITY_ID = "documentation.static_claims"
CONTRACT_VERSION = "1.0"
CLAIM_FAMILY = "documentation.inventory.v1"
MAX_CONTRACT_BYTES = 1_048_576
MAX_ARTIFACT_BYTES = 8_388_608
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEAD = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ContractError(ValueError):
    """Raised when an external contract is malformed or incompatible."""


class _ClosedModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_by_alias=True,
        validate_by_name=False,
        serialize_by_alias=True,
    )


def _validate_digest(value: str) -> str:
    if _DIGEST.fullmatch(value) is None:
        raise ValueError("digest must be canonical sha256:<64 lowercase hex>")
    return value


def _validate_relative_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise ValueError("artifact path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("artifact path must be normalized and remain inside the artifact root")
    return value


class ArtifactReference(_ClosedModel):
    path: str = Field(min_length=1, max_length=512)
    digest: str
    size_bytes: int = Field(ge=0, le=MAX_ARTIFACT_BYTES)
    media_type: Literal["application/json"]

    _path = field_validator("path")(_validate_relative_path)
    _digest = field_validator("digest")(_validate_digest)


class CapabilityManifest(_ClosedModel):
    schema_id: Literal["samuel-extension-capability.v1"] = Field(alias="schema")
    capability_id: Literal["documentation.static_claims"]
    contract_version: Literal["1.0"]
    transport: Literal["filesystem-json"]
    effect: Literal["advisory"]
    claim_families: list[Literal["documentation.inventory.v1"]]
    permissions: list[Literal["repository:read"]]
    credentials: list[Literal["unsupported"]] = Field(default_factory=list)

    @field_validator("claim_families")
    @classmethod
    def validate_claim_families(
        cls, value: list[Literal["documentation.inventory.v1"]]
    ) -> list[Literal["documentation.inventory.v1"]]:
        if value != [CLAIM_FAMILY]:
            raise ValueError(f"claim_families must contain exactly {CLAIM_FAMILY!r}")
        return value

    @field_validator("permissions")
    @classmethod
    def validate_permissions(
        cls, value: list[Literal["repository:read"]]
    ) -> list[Literal["repository:read"]]:
        if value != ["repository:read"]:
            raise ValueError("permissions must contain exactly 'repository:read'")
        return value


class CapabilityPolicy(_ClosedModel):
    enabled: StrictBool = False
    required: StrictBool = False
    contract_version: Literal["1.0"] = "1.0"
    manifest_path: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("manifest_path")
    @classmethod
    def validate_manifest_path(cls, value: str | None) -> str | None:
        if value is not None and ("\x00" in value or "\n" in value or "\r" in value):
            raise ValueError("manifest_path must be a single path without control characters")
        return value


class ExtensionConfiguration(_ClosedModel):
    schema_version: Literal["1.0"]
    capabilities: dict[Literal["documentation.static_claims"], CapabilityPolicy]

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(
        cls, value: dict[Literal["documentation.static_claims"], CapabilityPolicy]
    ) -> dict[Literal["documentation.static_claims"], CapabilityPolicy]:
        if set(value) != {CAPABILITY_ID}:
            raise ValueError(f"capabilities must contain exactly {CAPABILITY_ID!r}")
        return value


class ExtensionSubject(_ClosedModel):
    repository: str = Field(min_length=3, max_length=255)
    head_sha: str

    @field_validator("repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        if _REPOSITORY.fullmatch(value) is None:
            raise ValueError("repository must be canonical owner/name")
        return value

    @field_validator("head_sha")
    @classmethod
    def validate_head(cls, value: str) -> str:
        if _HEAD.fullmatch(value) is None:
            raise ValueError("head_sha must be 40 lowercase hexadecimal characters")
        return value


class ExtensionRequest(_ClosedModel):
    schema_id: Literal["samuel-extension-request.v1"] = Field(alias="schema")
    capability_id: Literal["documentation.static_claims"]
    contract_version: Literal["1.0"]
    request_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    subject: ExtensionSubject
    claim_family: Literal["documentation.inventory.v1"]
    effect: Literal["advisory"]
    policy_digest: str
    input_artifact: ArtifactReference

    _policy_digest = field_validator("policy_digest")(_validate_digest)


class ExtensionResult(_ClosedModel):
    schema_id: Literal["samuel-extension-result.v1"] = Field(alias="schema")
    capability_id: Literal["documentation.static_claims"]
    contract_version: Literal["1.0"]
    request_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    request_digest: str
    subject: ExtensionSubject
    claim_family: Literal["documentation.inventory.v1"]
    effect: Literal["advisory"]
    status: Literal["passed", "failed", "indeterminate"]
    output_artifact: ArtifactReference

    _request_digest = field_validator("request_digest")(_validate_digest)


class CapabilityResolution(_ClosedModel):
    capability_id: Literal["documentation.static_claims"] = "documentation.static_claims"
    enabled: bool
    required: bool
    available: bool
    blocked: bool
    status: Literal["disabled", "available", "absent", "incompatible"]
    reason: str
    manifest: CapabilityManifest | None = None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    if path.is_symlink():
        raise ContractError(f"contract path must not be a symlink: {path}")
    try:
        stat = path.stat()
    except OSError as exc:
        raise ContractError(f"contract is unavailable: {path}") from exc
    if not path.is_file():
        raise ContractError(f"contract path must be a regular file: {path}")
    if stat.st_size > MAX_CONTRACT_BYTES:
        raise ContractError(f"contract exceeds {MAX_CONTRACT_BYTES} bytes: {path}")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"contract is not valid UTF-8 JSON: {path}") from exc


def _load_model(path: Path, model: type[_ClosedModel]) -> _ClosedModel:
    try:
        return model.model_validate(_read_json(path))
    except ValidationError as exc:
        raise ContractError(f"invalid {model.__name__}: {exc}") from exc


def load_capability_manifest(path: Path | str) -> CapabilityManifest:
    return CapabilityManifest.model_validate(_load_model(Path(path), CapabilityManifest))


def load_extension_policy(config_path: Path | str) -> CapabilityPolicy:
    path = Path(config_path)
    if not path.exists() and not path.is_symlink():
        return CapabilityPolicy()
    configuration = ExtensionConfiguration.model_validate(_load_model(path, ExtensionConfiguration))
    return configuration.capabilities["documentation.static_claims"]


def load_extension_request(path: Path | str) -> ExtensionRequest:
    return ExtensionRequest.model_validate(_load_model(Path(path), ExtensionRequest))


def load_extension_result(path: Path | str) -> ExtensionResult:
    return ExtensionResult.model_validate(_load_model(Path(path), ExtensionResult))


def contract_digest(value: BaseModel) -> str:
    payload = canonical_contract_bytes(value)
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def canonical_contract_bytes(value: BaseModel) -> bytes:
    """Return the language-neutral canonical JSON used by contract digests."""

    payload = value.model_dump(exclude_none=True, by_alias=True, mode="json")
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_artifact_reference(root: Path | str, reference: ArtifactReference) -> Path:
    """Verify one bounded artifact beneath an explicitly supplied root."""

    artifact_root = Path(root)
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise ContractError("artifact root must be a real directory")
    target = artifact_root / reference.path
    current = artifact_root
    for part in PurePosixPath(reference.path).parts:
        current = current / part
        if current.is_symlink():
            raise ContractError(f"artifact path must not traverse a symlink: {reference.path}")
    try:
        stat = target.stat()
    except OSError as exc:
        raise ContractError(f"artifact is unavailable: {reference.path}") from exc
    if not target.is_file():
        raise ContractError(f"artifact must be a regular file: {reference.path}")
    if stat.st_size != reference.size_bytes:
        raise ContractError(f"artifact size does not match reference: {reference.path}")
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            while chunk := handle.read(65_536):
                digest.update(chunk)
    except OSError as exc:
        raise ContractError(f"artifact cannot be read: {reference.path}") from exc
    actual = f"sha256:{digest.hexdigest()}"
    if actual != reference.digest:
        raise ContractError(f"artifact digest does not match reference: {reference.path}")
    return target


def resolve_capability(
    policy: CapabilityPolicy,
    *,
    manifest_path: Path | str | None = None,
) -> CapabilityResolution:
    configured_path = manifest_path if manifest_path is not None else policy.manifest_path
    if not policy.enabled:
        return CapabilityResolution(
            enabled=False,
            required=policy.required,
            available=False,
            blocked=policy.required,
            status="disabled",
            reason=(
                "required capability is disabled by operator configuration"
                if policy.required
                else "optional capability is disabled"
            ),
        )
    if configured_path is None:
        return CapabilityResolution(
            enabled=True,
            required=policy.required,
            available=False,
            blocked=policy.required,
            status="absent",
            reason="configured capability manifest is absent",
        )
    try:
        manifest = load_capability_manifest(configured_path)
    except ContractError as exc:
        return CapabilityResolution(
            enabled=True,
            required=policy.required,
            available=False,
            blocked=policy.required,
            status="incompatible",
            reason=str(exc),
        )
    return CapabilityResolution(
        enabled=True,
        required=policy.required,
        available=True,
        blocked=False,
        status="available",
        reason="compatible external data consumer is configured",
        manifest=manifest,
    )


def validate_result_binding(request: ExtensionRequest, result: ExtensionResult) -> None:
    expected = {
        "capability_id": request.capability_id,
        "contract_version": request.contract_version,
        "request_id": request.request_id,
        "request_digest": contract_digest(request),
        "subject": request.subject,
        "claim_family": request.claim_family,
        "effect": request.effect,
    }
    actual = {
        "capability_id": result.capability_id,
        "contract_version": result.contract_version,
        "request_id": result.request_id,
        "request_digest": result.request_digest,
        "subject": result.subject,
        "claim_family": result.claim_family,
        "effect": result.effect,
    }
    if actual != expected:
        raise ContractError("extension result does not match its exact bound request")
