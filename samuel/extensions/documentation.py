"""Closed payload contract for ``documentation.inventory.v1``."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, field_validator

from samuel.extensions.contract import (
    ExtensionSubject,
    _ClosedModel,
    _load_model,
    _validate_digest,
)

DOCUMENTATION_POLICY_SCHEMA = "samuel-documentation-inventory-policy.v1"
DOCUMENTATION_CLAIMS_SCHEMA = "samuel-documentation-inventory-claims.v1"
MAX_DOCUMENTS = 128
MAX_DOCUMENT_BYTES = 1_048_576
MAX_DOCUMENTATION_BYTES = 8_388_608
_CONSUMER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_. -]+$")


def _validate_repository_path(value: str) -> str:
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
        raise ValueError("path must be a normalized safe relative repository path")
    return value


def _validate_document_path(value: str) -> str:
    value = _validate_repository_path(value)
    if PurePosixPath(value).suffix.lower() != ".md":
        raise ValueError("document path must name a Markdown file")
    return value


class DocumentationConsumer(_ClosedModel):
    consumer_id: str = Field(min_length=1, max_length=128)
    path: str
    tool_digest: str

    @field_validator("consumer_id")
    @classmethod
    def validate_consumer_id(cls, value: str) -> str:
        if _CONSUMER_ID.fullmatch(value) is None:
            raise ValueError("consumer_id must be canonical")
        return value

    _path = field_validator("path")(_validate_repository_path)
    _digest = field_validator("tool_digest")(_validate_digest)


class DocumentationPolicy(_ClosedModel):
    schema_id: Literal["samuel-documentation-inventory-policy.v1"] = Field(alias="schema")
    repository: str = Field(min_length=3, max_length=255)
    consumer: DocumentationConsumer
    documents: list[str] = Field(min_length=1, max_length=MAX_DOCUMENTS)

    @field_validator("repository")
    @classmethod
    def validate_repository(cls, value: str) -> str:
        ExtensionSubject(repository=value, head_sha="0" * 40)
        return value

    @field_validator("documents")
    @classmethod
    def validate_documents(cls, value: list[str]) -> list[str]:
        checked = [_validate_document_path(item) for item in value]
        if checked != sorted(set(checked)):
            raise ValueError("documents must be unique and sorted")
        return checked


class DocumentationClaim(_ClosedModel):
    path: str
    digest: str
    size_bytes: int = Field(ge=0, le=MAX_DOCUMENT_BYTES)
    media_type: Literal["text/markdown"]

    _path = field_validator("path")(_validate_document_path)
    _digest = field_validator("digest")(_validate_digest)


class DocumentationClaims(_ClosedModel):
    schema_id: Literal["samuel-documentation-inventory-claims.v1"] = Field(alias="schema")
    subject: ExtensionSubject
    policy_digest: str
    consumer_id: str = Field(min_length=1, max_length=128)
    tool_digest: str
    documents: list[DocumentationClaim] = Field(min_length=1, max_length=MAX_DOCUMENTS)

    _policy_digest = field_validator("policy_digest")(_validate_digest)
    _tool_digest = field_validator("tool_digest")(_validate_digest)

    @field_validator("consumer_id")
    @classmethod
    def validate_consumer_id(cls, value: str) -> str:
        if _CONSUMER_ID.fullmatch(value) is None:
            raise ValueError("consumer_id must be canonical")
        return value

    @field_validator("documents")
    @classmethod
    def validate_documents(cls, value: list[DocumentationClaim]) -> list[DocumentationClaim]:
        paths = [item.path for item in value]
        if paths != sorted(set(paths)):
            raise ValueError("document claims must be unique and sorted by path")
        if sum(item.size_bytes for item in value) > MAX_DOCUMENTATION_BYTES:
            raise ValueError("document claims exceed the aggregate byte limit")
        return value


def load_documentation_policy(path: Path | str) -> DocumentationPolicy:
    return DocumentationPolicy.model_validate(_load_model(Path(path), DocumentationPolicy))


def load_documentation_claims(path: Path | str) -> DocumentationClaims:
    return DocumentationClaims.model_validate(_load_model(Path(path), DocumentationClaims))
