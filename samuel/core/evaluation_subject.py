from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from samuel.core.gate_metadata import (
    EVALUATION_OBSERVATION_SCHEMA_VERSION,
    GATE_RESULT_SCHEMA_VERSION,
)
from samuel.core.process_environment import VERIFIER_ENVIRONMENT_PROFILE

if TYPE_CHECKING:
    from samuel.core.config import EvalSchema, GatesConfigSchema

_SHA_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _require_text(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError(f"{field_name} must be a non-empty canonical string")


def _require_sha(value: str, field_name: str) -> None:
    if not _SHA_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a full lowercase Git object ID")


def _require_digest(value: str, field_name: str) -> None:
    if not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a sha256 digest")


def canonical_contract_text(value: str) -> str:
    """Canonicalize a human-approved acceptance contract before hashing."""

    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def contract_hash(value: str) -> str:
    canonical = canonical_contract_text(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def policy_digest(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def gate_policy_binding(
    gates: GatesConfigSchema,
    evaluation: EvalSchema,
    architecture: dict[str, Any] | None,
    *,
    candidate_process: dict[str, Any] | None = None,
    scm_policy: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the exact policy/schema identity shared by gates and resume."""

    return {
        "policy_version": gates.policy_version,
        "policy_digest": policy_digest(
            {
                "gates": gates.model_dump(mode="json"),
                "preflight_contract": "static-required-before-candidate.v3",
                "architecture": architecture,
                "test_runner": {
                    "policy_version": evaluation.test_policy_version,
                    "test_cmd": evaluation.test_cmd,
                    "test_timeout": evaluation.test_timeout,
                    **(
                        {
                            "verifier_toolchain": evaluation.verifier_toolchain.model_dump(
                                mode="json"
                            )
                        }
                        if evaluation.verifier_toolchain is not None
                        else {}
                    ),
                },
                "candidate_process": candidate_process
                or {"environment_profile": VERIFIER_ENVIRONMENT_PROFILE},
                "scm": dict(scm_policy) if scm_policy is not None else None,
                "gate_result_schema_version": GATE_RESULT_SCHEMA_VERSION,
                "observation_schema_version": EVALUATION_OBSERVATION_SCHEMA_VERSION,
            }
        ),
        "gate_schema_version": GATE_RESULT_SCHEMA_VERSION,
        "observation_schema_version": EVALUATION_OBSERVATION_SCHEMA_VERSION,
    }


@dataclass(frozen=True)
class EvaluationSubject:
    """Immutable identity of the repository artifact evaluated by every gate."""

    repository: str
    base_sha: str
    head_sha: str
    contract_hash: str
    policy_version: str
    policy_digest: str

    def __post_init__(self) -> None:
        _require_text(self.repository, "repository")
        _require_sha(self.base_sha, "base_sha")
        _require_sha(self.head_sha, "head_sha")
        _require_digest(self.contract_hash, "contract_hash")
        _require_text(self.policy_version, "policy_version")
        _require_digest(self.policy_digest, "policy_digest")

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvaluationSubject:
        return cls(
            repository=str(value.get("repository", "")),
            base_sha=str(value.get("base_sha", "")),
            head_sha=str(value.get("head_sha", "")),
            contract_hash=str(value.get("contract_hash", "")),
            policy_version=str(value.get("policy_version", "")),
            policy_digest=str(value.get("policy_digest", "")),
        )


@dataclass(frozen=True)
class RevisionComparison:
    repository: str
    base_sha: str
    head_sha: str
    changed_files: tuple[str, ...]
    diff: str
    diff_bytes: int

    def __post_init__(self) -> None:
        _require_text(self.repository, "repository")
        _require_sha(self.base_sha, "base_sha")
        _require_sha(self.head_sha, "head_sha")
        if self.diff_bytes != len(self.diff.encode("utf-8")):
            raise ValueError("diff_bytes does not match the complete diff")


@dataclass(frozen=True)
class PullRequestRevision:
    repository: str
    base_sha: str
    head_sha: str

    def __post_init__(self) -> None:
        _require_text(self.repository, "repository")
        _require_sha(self.base_sha, "base_sha")
        _require_sha(self.head_sha, "head_sha")
