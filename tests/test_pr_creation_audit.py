from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from samuel.adapters.audit.jsonl import JSONLAuditSink
from samuel.core.bus import AuditMiddleware, Bus
from samuel.core.commands import CreatePRCommand
from samuel.core.evaluation_subject import PullRequestRevision, RevisionComparison
from samuel.core.ports import IVersionControl
from samuel.core.types import Comment, Issue
from samuel.slices.pr_gates.handler import PRGatesHandler


@pytest.mark.parametrize("context_available", [True, False])
def test_pr_creation_failure_is_persisted_without_exception_secrets(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, context_available: bool
) -> None:
    """The production audit middleware persists bounded PR failure evidence."""
    (tmp_path / "gates.json").write_text(
        '{"policy_version":"audit.v1","required":[5],"optional":[],"disabled":[],"custom":[]}'
    )
    secret = "Authorization: Bearer audit-secret-value"
    scm_mock = Mock(spec=IVersionControl)
    if context_available:
        scm_mock.get_issue.return_value = Issue(42, "Bound issue", "Fix safe.py", "open")
    else:
        scm_mock.get_issue.side_effect = OSError(secret)
    scm_mock.get_comments.return_value = [Comment(id=1, body="## Plan\n- [ ] verify", user="bot")]
    scm_mock.repository_identity = "owner/repo"
    scm_mock.resolve_ref.side_effect = ["a" * 40, "b" * 40]
    scm_mock.compare_commits.return_value = RevisionComparison(
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        changed_files=("safe.py",),
        diff="+safe",
        diff_bytes=5,
    )
    scm_mock.get_pr_revision.return_value = PullRequestRevision(
        repository="owner/repo", base_sha="a" * 40, head_sha="b" * 40
    )
    scm_mock.create_pr.side_effect = RuntimeError(secret)

    audit_path = tmp_path / "audit.jsonl"
    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink=JSONLAuditSink(audit_path, rotation="none")))
    handler = PRGatesHandler(
        bus,
        scm=cast(IVersionControl, scm_mock),
        config_dir=str(tmp_path),
    )

    result = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="samuel/issue-42",
            correlation_id="run-516-audit",
        )
    )

    records = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failure_records = [
        record
        for record in records
        if record.get("payload", {}).get("message_name") == "PRCreationFailed"
    ]
    gate_records = [
        record
        for record in records
        if record.get("payload", {}).get("message_name") == "GateEvaluationCompleted"
    ]

    assert result["passed"] is False
    assert len(failure_records) == 1
    assert len(gate_records) == 1
    gate_payload = gate_records[0]["payload"]
    assert gate_payload["gate_results"][0]["gate"] == 5
    assert gate_payload["gate_results"][0]["passed"] is True
    assert (
        gate_payload["gate_results"][0]["evaluation_subject"] == gate_payload["evaluation_subject"]
    )
    payload = failure_records[0]["payload"]
    assert payload["issue"] == 42
    assert payload["branch"] == "samuel/issue-42"
    assert payload["correlation_id"] == "run-516-audit"
    assert payload["gates_passed"] is True
    assert payload["pr_created"] is False
    assert payload["error"] == {
        "code": "scm_create_pr_failed",
        "type": "RuntimeError",
        "provider": "Mock",
        "message": "SCM did not confirm creation of a valid pull request",
        "remediation": "Verify SCM configuration and repository connectivity before retrying",
    }
    persisted = audit_path.read_text(encoding="utf-8")
    assert secret not in persisted
    assert secret not in caplog.text
    assert secret not in str(result)
