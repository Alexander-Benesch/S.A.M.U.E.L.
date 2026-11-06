from __future__ import annotations

from samuel.core.commands import (
    BuildContextCommand,
    ChangelogCommand,
    Command,
    CreatePRCommand,
    EvaluateCommand,
    HealCommand,
    HealthCheckCommand,
    ImplementCommand,
    PlanIssueCommand,
    ReloadConfigCommand,
    ReviewCommand,
    RunQualityCommand,
    ScanIssuesCommand,
    ShutdownCommand,
    VerifyACCommand,
    create_command,
)
from samuel.core.evaluation_subject import EvaluationSubject


def test_command_base_fields():
    c = Command(name="Test")
    assert c.name == "Test"
    assert c.idempotency_key is None
    assert c.correlation_id is not None
    assert len(c.correlation_id) == 36


def test_command_with_idempotency():
    c = CreatePRCommand(idempotency_key="pr:42:feat/x")
    assert c.name == "CreatePR"
    assert c.idempotency_key == "pr:42:feat/x"


def test_all_command_types_instantiable():
    cmd_classes = [
        ScanIssuesCommand,
        PlanIssueCommand,
        ImplementCommand,
        CreatePRCommand,
        EvaluateCommand,
        HealCommand,
        ReviewCommand,
        HealthCheckCommand,
        ReloadConfigCommand,
        ShutdownCommand,
        BuildContextCommand,
        RunQualityCommand,
        VerifyACCommand,
        ChangelogCommand,
    ]
    for cls in cmd_classes:
        c = cls()
        assert c.name != ""
        assert isinstance(c.payload, dict)


def test_create_pr_command_restores_evaluation_subject_from_event_payload():
    subject = EvaluationSubject(
        repository="https://scm.example/owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="v1",
        policy_digest="sha256:" + "d" * 64,
    )

    command = create_command(
        "CreatePR",
        payload={"issue": 42, "evaluation_subject": subject.as_dict()},
    )

    assert isinstance(command, CreatePRCommand)
    assert command.subject == subject

    verify = create_command(
        "VerifyAC",
        payload={"issue": 42, "evaluation_subject": subject.as_dict()},
    )
    assert isinstance(verify, VerifyACCommand)
    assert verify.subject == subject
