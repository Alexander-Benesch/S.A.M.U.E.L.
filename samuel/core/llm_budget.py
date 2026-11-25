"""Stable identities for the cumulative workflow token authority."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from samuel.core.commands import Command
from samuel.core.state import WorkflowBudgetAdmissionRecord


def bound_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def command_invocation_digest(command: Command) -> str:
    """Bind the accepted command without treating correlation as authority."""

    return bound_digest(
        {
            "name": command.name,
            "idempotency_key": command.idempotency_key,
            "correlation_id": command.correlation_id,
            "payload": command.payload,
            "issue_number": getattr(command, "issue_number", 0),
            "reason": getattr(command, "reason", ""),
        }
    )


def workflow_budget_admission(
    *,
    repository: str,
    issue_number: int,
    command: Command,
    source_digest: str,
    policy_digest: str,
    token_limit: int,
) -> WorkflowBudgetAdmissionRecord:
    if not repository.strip() or issue_number <= 0:
        raise ValueError("workflow budget requires repository and positive issue")
    if not source_digest.startswith("sha256:") or not policy_digest.startswith("sha256:"):
        raise ValueError("workflow budget requires bound source and policy digests")
    if isinstance(token_limit, bool) or token_limit <= 0:
        raise ValueError("workflow token limit must be positive")
    invocation_digest = command_invocation_digest(command)
    admission_key = bound_digest(
        {
            "repository": repository,
            "issue_number": issue_number,
            "invocation_digest": invocation_digest,
            "source_digest": source_digest,
            "policy_digest": policy_digest,
        }
    )
    return WorkflowBudgetAdmissionRecord(
        admission_key=f"workflow-budget:{admission_key}",
        repository=repository,
        issue_number=issue_number,
        invocation_digest=invocation_digest,
        source_digest=source_digest,
        policy_digest=policy_digest,
        correlation_id=command.correlation_id or "",
        token_limit=token_limit,
    )
