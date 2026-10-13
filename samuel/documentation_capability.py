"""Product-side preparation, verification and projection for documentation claims."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import quote, urlsplit

from pydantic import ValidationError

from samuel.core.security_policy import SECRET_RULES
from samuel.extensions import (
    ArtifactReference,
    ContractError,
    ExtensionRequest,
    ExtensionResult,
    ExtensionSubject,
    canonical_contract_bytes,
    contract_digest,
    load_extension_request,
    load_extension_result,
    validate_result_binding,
    verify_artifact_reference,
)
from samuel.extensions.documentation import (
    DocumentationClaims,
    DocumentationPolicy,
    load_documentation_claims,
    load_documentation_policy,
)

_PRIVATE_IPV4 = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
_LOCAL_SECRET_PATH = re.compile(r"(?:/root/\.(?:config|ssh)|/home/[^/\s]+/\.ssh)(?:/|\b)")
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_. -]+$")


@dataclass(frozen=True)
class DocumentationVerification:
    request: ExtensionRequest
    result: ExtensionResult
    policy: DocumentationPolicy
    claims: DocumentationClaims


def _digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _safe_repository_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 512
        or path.is_absolute()
        or value != path.as_posix()
        or any(
            part in {"", ".", ".."} or _SAFE_COMPONENT.fullmatch(part) is None
            for part in path.parts
        )
    ):
        raise ContractError("repository path must be normalized, relative and bounded")
    return value


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=not binary,
    )
    if completed.returncode:
        raise ContractError(f"local Git lookup failed: {' '.join(args[:2])}")
    return cast(str | bytes, completed.stdout)


def _head(root: Path) -> str:
    value = str(_git(root, "rev-parse", "HEAD")).strip()
    try:
        ExtensionSubject(repository="example/repository", head_sha=value)
    except ValidationError as exc:
        raise ContractError("repository HEAD is not a full canonical Git SHA") from exc
    return value


def _git_blob(root: Path, head_sha: str, path: str) -> bytes:
    safe_path = _safe_repository_path(path)
    value = _git(root, "cat-file", "blob", f"{head_sha}:{safe_path}", binary=True)
    if not isinstance(value, bytes):
        raise ContractError("local Git returned an invalid blob")
    return value


def _model_from_bytes(data: bytes, model: type[DocumentationPolicy]) -> DocumentationPolicy:
    try:
        return model.model_validate_json(data)
    except (UnicodeDecodeError, ValidationError) as exc:
        raise ContractError("documentation policy is not valid closed UTF-8 JSON") from exc


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ContractError("exchange directory must not be a symlink")
    staging = path.with_suffix(path.suffix + ".tmp")
    if staging.exists() or staging.is_symlink():
        raise ContractError("stale or unsafe exchange staging file exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(staging, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    os.replace(staging, path)


def _artifact(path: str, data: bytes) -> ArtifactReference:
    return ArtifactReference(
        path=path,
        digest=_digest(data),
        size_bytes=len(data),
        media_type="application/json",
    )


def prepare_documentation_exchange(
    *,
    repository_root: Path,
    repository: str,
    policy_path: str,
    exchange_root: Path,
    request_id: str,
) -> tuple[ExtensionRequest, Path]:
    """Bind a tracked policy and consumer tool to the repository's exact HEAD."""

    head_sha = _head(repository_root)
    policy_blob = _git_blob(repository_root, head_sha, policy_path)
    policy = _model_from_bytes(policy_blob, DocumentationPolicy)
    if policy.repository != repository:
        raise ContractError("documentation policy repository does not match the request subject")
    tool_blob = _git_blob(repository_root, head_sha, policy.consumer.path)
    if _digest(tool_blob) != policy.consumer.tool_digest:
        raise ContractError("consumer tool digest does not match the bound repository blob")

    canonical_policy = canonical_contract_bytes(policy) + b"\n"
    policy_name = "documentation-policy.json"
    policy_output = exchange_root / policy_name
    _atomic_write(policy_output, canonical_policy)
    request = ExtensionRequest(
        schema="samuel-extension-request.v1",
        capability_id="documentation.static_claims",
        contract_version="1.0",
        request_id=request_id,
        subject=ExtensionSubject(repository=repository, head_sha=head_sha),
        claim_family="documentation.inventory.v1",
        effect="advisory",
        policy_digest=contract_digest(policy),
        input_artifact=_artifact(policy_name, canonical_policy),
    )
    _atomic_write(
        exchange_root / "request.json",
        request.model_dump_json(by_alias=True, exclude_none=True, indent=2).encode("utf-8") + b"\n",
    )
    return request, policy_output


def _sensitive_findings(path: str, content: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), 1):
        for rule in SECRET_RULES:
            if rule.scan and rule.detector.search(line):
                findings.append({"path": path, "line": line_number, "rule_id": rule.rule_id})
                break
        if _PRIVATE_IPV4.search(line):
            findings.append(
                {"path": path, "line": line_number, "rule_id": "private-network-address"}
            )
        if _LOCAL_SECRET_PATH.search(line):
            findings.append({"path": path, "line": line_number, "rule_id": "local-secret-path"})
    return findings


def verify_documentation_exchange(
    *,
    repository_root: Path,
    exchange_root: Path,
    request_path: Path,
    result_path: Path,
) -> DocumentationVerification:
    """Verify exact coverage and repository bytes before any publication effect."""

    request = load_extension_request(request_path)
    result = load_extension_result(result_path)
    validate_result_binding(request, result)
    if result.status != "passed":
        raise ContractError(f"documentation consumer did not pass: {result.status}")
    policy_file = verify_artifact_reference(exchange_root, request.input_artifact)
    claims_file = verify_artifact_reference(exchange_root, result.output_artifact)
    policy = load_documentation_policy(policy_file)
    claims = load_documentation_claims(claims_file)

    if contract_digest(policy) != request.policy_digest:
        raise ContractError("documentation policy digest does not match the request")
    if policy.repository != request.subject.repository:
        raise ContractError("documentation policy repository does not match the request")
    if claims.subject != request.subject or claims.policy_digest != request.policy_digest:
        raise ContractError("documentation claims do not match the request subject and policy")
    if (
        claims.consumer_id != policy.consumer.consumer_id
        or claims.tool_digest != policy.consumer.tool_digest
    ):
        raise ContractError("documentation claims do not match the bound consumer tool")
    claim_paths = [item.path for item in claims.documents]
    if claim_paths != policy.documents:
        raise ContractError("documentation claims do not provide exact policy coverage")
    if _head(repository_root) != request.subject.head_sha:
        raise ContractError("repository checkout does not match the request head")
    tool_blob = _git_blob(repository_root, request.subject.head_sha, policy.consumer.path)
    if _digest(tool_blob) != policy.consumer.tool_digest:
        raise ContractError("bound consumer tool differs from the request policy")

    findings: list[dict[str, Any]] = []
    for claim in claims.documents:
        content = _git_blob(repository_root, request.subject.head_sha, claim.path)
        if len(content) != claim.size_bytes or _digest(content) != claim.digest:
            raise ContractError(f"documentation claim differs from bound Git content: {claim.path}")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError(f"documentation claim is not UTF-8: {claim.path}") from exc
        findings.extend(_sensitive_findings(claim.path, text))
    if findings:
        summary = ", ".join(
            f"{item['path']}:{item['line']}:{item['rule_id']}" for item in findings[:20]
        )
        raise ContractError(
            f"documentation publication blocked by sensitive-data policy: {summary}"
        )
    return DocumentationVerification(request=request, result=result, policy=policy, claims=claims)


def build_documentation_projection(
    verification: DocumentationVerification,
    *,
    source_url_template: str,
) -> dict[str, bytes]:
    """Project only bounded metadata; source prose receives no truth assertion."""

    if "{head_sha}" not in source_url_template or "{path}" not in source_url_template:
        raise ContractError("source URL template requires {head_sha} and {path}")
    probe = source_url_template.format(
        head_sha=verification.request.subject.head_sha, path="README.md"
    )
    parsed = urlsplit(probe)
    if parsed.username or parsed.password or parsed.scheme not in {"http", "https"}:
        raise ContractError("source URL template must be credential-free HTTP(S)")

    subject = verification.request.subject
    lines = [
        "# Documentation inventory",
        "",
        "> Nicht autoritative Advisory-Projektion. Die Tabelle bestätigt nur die",
        "> unten gebundenen Dateifakten; freie Prosa erhält keine Wahrheitszusage.",
        "",
        f"Subject: `{subject.repository}@{subject.head_sha}`  ",
        f"Policy: `{verification.request.policy_digest}`  ",
        f"Consumer: `{verification.claims.consumer_id}` / `{verification.claims.tool_digest}`  ",
        f"Claims artifact: `{verification.result.output_artifact.digest}`",
        "",
        "| Pfad | Bytes | SHA-256 |",
        "|---|---:|---|",
    ]
    for claim in verification.claims.documents:
        url = source_url_template.format(
            head_sha=subject.head_sha,
            path=quote(claim.path, safe="/"),
        )
        lines.append(f"| [{claim.path}]({url}) | {claim.size_bytes} | `{claim.digest}` |")
    lines.append("")
    home = ("\n".join(lines) + "\n").encode("utf-8")
    sidebar = b"# Documentation\n\n- [Inventory](Home)\n"
    footer = (
        "Nicht autoritative Advisory-Projektion · "
        f"Subject `{subject.repository}@{subject.head_sha}` · "
        f"Artifact `{verification.result.output_artifact.digest}`\n"
    ).encode()
    return {"Home.md": home, "_Sidebar.md": sidebar, "_Footer.md": footer}
