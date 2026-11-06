from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

from samuel.documentation_capability import (
    build_documentation_projection,
    prepare_documentation_exchange,
    verify_documentation_exchange,
)
from samuel.extensions import (
    ArtifactReference,
    ContractError,
    ExtensionResult,
    contract_digest,
)
from samuel.extensions.documentation import (
    DocumentationClaim,
    DocumentationClaims,
    DocumentationPolicy,
)

ROOT = Path(__file__).parents[1]


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=not binary,
    )
    return cast(str | bytes, completed.stdout)


def _digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _repository(
    tmp_path: Path, *, sensitive: bool = False, secret: bool = False
) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-b", "main")
    (root / "docs").mkdir()
    (root / "tools").mkdir()
    readme = "# Example\n"
    if sensitive:
        readme += "Internal endpoint: http://" + ".".join(("192", "168", "1", "10")) + ":8080\n"
    if secret:
        readme += "credential = sk-" + "a" * 32 + "\n"
    (root / "README.md").write_text(readme, encoding="utf-8")
    (root / "docs/OPERATIONS.md").write_text("# Operations\n\nRun safely.\n", encoding="utf-8")
    tool = b"print('external consumer fixture')\n"
    (root / "tools/documentation_consumer.py").write_bytes(tool)
    policy = {
        "schema": "samuel-documentation-inventory-policy.v1",
        "repository": "example/documentation",
        "consumer": {
            "consumer_id": "fixture.documentation-consumer",
            "path": "tools/documentation_consumer.py",
            "tool_digest": _digest(tool),
        },
        "documents": ["README.md", "docs/OPERATIONS.md"],
    }
    (root / "documentation-policy.json").write_text(
        json.dumps(policy, indent=2) + "\n", encoding="utf-8"
    )
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    return root, str(_git(root, "rev-parse", "HEAD")).strip()


def _consume(
    repository_root: Path,
    exchange_root: Path,
    *,
    paths: list[str] | None = None,
) -> tuple[Path, ExtensionResult]:
    request_data = json.loads((exchange_root / "request.json").read_text(encoding="utf-8"))
    from samuel.extensions import ExtensionRequest

    request = ExtensionRequest.model_validate(request_data)
    policy = DocumentationPolicy.model_validate_json(
        (exchange_root / "documentation-policy.json").read_text(encoding="utf-8")
    )
    selected = paths or policy.documents
    documents: list[DocumentationClaim] = []
    for path in selected:
        content = _git(
            repository_root,
            "cat-file",
            "blob",
            f"{request.subject.head_sha}:{path}",
            binary=True,
        )
        assert isinstance(content, bytes)
        documents.append(
            DocumentationClaim(
                path=path,
                digest=_digest(content),
                size_bytes=len(content),
                media_type="text/markdown",
            )
        )
    claims = DocumentationClaims(
        schema="samuel-documentation-inventory-claims.v1",
        subject=request.subject,
        policy_digest=request.policy_digest,
        consumer_id=policy.consumer.consumer_id,
        tool_digest=policy.consumer.tool_digest,
        documents=documents,
    )
    claims_bytes = claims.model_dump_json(by_alias=True, indent=2).encode() + b"\n"
    claims_path = exchange_root / "documentation-claims.json"
    claims_path.write_bytes(claims_bytes)
    result = ExtensionResult(
        schema="samuel-extension-result.v1",
        capability_id=request.capability_id,
        contract_version=request.contract_version,
        request_id=request.request_id,
        request_digest=contract_digest(request),
        subject=request.subject,
        claim_family=request.claim_family,
        effect=request.effect,
        status="passed",
        output_artifact=ArtifactReference(
            path=claims_path.name,
            digest=_digest(claims_bytes),
            size_bytes=len(claims_bytes),
            media_type="application/json",
        ),
    )
    result_path = exchange_root / "result.json"
    result_path.write_text(result.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    return result_path, result


def test_prepare_verify_and_project_exact_inventory(tmp_path: Path) -> None:
    repository, head = _repository(tmp_path)
    exchange = tmp_path / "exchange"

    request, _ = prepare_documentation_exchange(
        repository_root=repository,
        repository="example/documentation",
        policy_path="documentation-policy.json",
        exchange_root=exchange,
        request_id="documentation-1",
    )
    result_path, result = _consume(repository, exchange)
    verification = verify_documentation_exchange(
        repository_root=repository,
        exchange_root=exchange,
        request_path=exchange / "request.json",
        result_path=result_path,
    )
    projection = build_documentation_projection(
        verification,
        source_url_template="https://scm.example/example/documentation/src/commit/{head_sha}/{path}",
    )

    assert request.subject.head_sha == head
    assert verification.result == result
    assert sorted(projection) == ["Home.md", "_Footer.md", "_Sidebar.md"]
    home = projection["Home.md"].decode()
    assert "Nicht autoritative Advisory-Projektion" in home
    assert f"example/documentation@{head}" in home
    assert "README.md" in home and "docs/OPERATIONS.md" in home


def test_exact_policy_coverage_is_required(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    exchange = tmp_path / "exchange"
    prepare_documentation_exchange(
        repository_root=repository,
        repository="example/documentation",
        policy_path="documentation-policy.json",
        exchange_root=exchange,
        request_id="documentation-coverage",
    )
    result_path, _ = _consume(repository, exchange, paths=["README.md"])

    with pytest.raises(ContractError, match="exact policy coverage"):
        verify_documentation_exchange(
            repository_root=repository,
            exchange_root=exchange,
            request_path=exchange / "request.json",
            result_path=result_path,
        )


def test_prepare_rejects_consumer_tool_drift(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    policy_path = repository / "documentation-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["consumer"]["tool_digest"] = "sha256:" + "0" * 64
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    _git(repository, "add", "documentation-policy.json")
    _git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "bad binding",
    )

    with pytest.raises(ContractError, match="tool digest"):
        prepare_documentation_exchange(
            repository_root=repository,
            repository="example/documentation",
            policy_path="documentation-policy.json",
            exchange_root=tmp_path / "exchange",
            request_id="documentation-tool-drift",
        )


def test_prepare_rejects_symlinked_staging_file(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    exchange = tmp_path / "exchange"
    exchange.mkdir()
    victim = tmp_path / "victim"
    victim.write_text("unchanged", encoding="utf-8")
    (exchange / "documentation-policy.json.tmp").symlink_to(victim)

    with pytest.raises(ContractError, match="staging"):
        prepare_documentation_exchange(
            repository_root=repository,
            repository="example/documentation",
            policy_path="documentation-policy.json",
            exchange_root=exchange,
            request_id="documentation-staging",
        )
    assert victim.read_text(encoding="utf-8") == "unchanged"


def test_verifier_rejects_checkout_head_drift(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    exchange = tmp_path / "exchange"
    prepare_documentation_exchange(
        repository_root=repository,
        repository="example/documentation",
        policy_path="documentation-policy.json",
        exchange_root=exchange,
        request_id="documentation-head-drift",
    )
    result_path, _ = _consume(repository, exchange)
    (repository / "new.txt").write_text("later\n", encoding="utf-8")
    _git(repository, "add", "new.txt")
    _git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "advance",
    )

    with pytest.raises(ContractError, match="checkout does not match"):
        verify_documentation_exchange(
            repository_root=repository,
            exchange_root=exchange,
            request_path=exchange / "request.json",
            result_path=result_path,
        )


def test_sensitive_document_blocks_without_copying_value(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path, sensitive=True)
    exchange = tmp_path / "exchange"
    prepare_documentation_exchange(
        repository_root=repository,
        repository="example/documentation",
        policy_path="documentation-policy.json",
        exchange_root=exchange,
        request_id="documentation-sensitive",
    )
    result_path, _ = _consume(repository, exchange)

    with pytest.raises(ContractError, match="private-network-address") as error:
        verify_documentation_exchange(
            repository_root=repository,
            exchange_root=exchange,
            request_path=exchange / "request.json",
            result_path=result_path,
        )
    assert ".".join(("192", "168", "1", "10")) not in str(error.value)


def test_secret_shape_blocks_without_copying_value(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path, secret=True)
    exchange = tmp_path / "exchange"
    prepare_documentation_exchange(
        repository_root=repository,
        repository="example/documentation",
        policy_path="documentation-policy.json",
        exchange_root=exchange,
        request_id="documentation-secret",
    )
    result_path, _ = _consume(repository, exchange)

    with pytest.raises(ContractError, match="prefixed-api-key") as error:
        verify_documentation_exchange(
            repository_root=repository,
            exchange_root=exchange,
            request_path=exchange / "request.json",
            result_path=result_path,
        )
    assert "sk-" + "a" * 32 not in str(error.value)


@pytest.mark.parametrize(
    ("filename", "model"),
    [
        ("documentation-policy.v1.json", DocumentationPolicy),
        ("documentation-claims.v1.json", DocumentationClaims),
    ],
)
def test_packaged_documentation_schemas_match_models(filename: str, model: type[BaseModel]) -> None:
    checked_in = json.loads((ROOT / "samuel/extensions/schemas" / filename).read_text())
    assert checked_in == model.model_json_schema(by_alias=True, mode="validation")


def test_documentation_policy_rejects_unsorted_duplicate_or_unsafe_paths() -> None:
    base = {
        "schema": "samuel-documentation-inventory-policy.v1",
        "repository": "example/documentation",
        "consumer": {
            "consumer_id": "fixture",
            "path": "tools/consumer.py",
            "tool_digest": "sha256:" + "1" * 64,
        },
    }
    for documents in (
        ["docs/Z.md", "README.md"],
        ["README.md", "README.md"],
        ["../README.md"],
        ["README.txt"],
    ):
        with pytest.raises(ValidationError):
            DocumentationPolicy.model_validate({**base, "documents": documents})
