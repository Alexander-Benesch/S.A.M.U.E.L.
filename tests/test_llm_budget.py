from samuel.core.commands import PlanIssueCommand
from samuel.core.llm_budget import workflow_budget_admission


def _admission(command: PlanIssueCommand):
    return workflow_budget_admission(
        repository="owner/repo",
        issue_number=command.issue_number,
        command=command,
        source_digest="sha256:" + "a" * 64,
        policy_digest="sha256:" + "b" * 64,
        token_limit=100_000,
    )


def test_replay_of_exact_invocation_reuses_budget_identity() -> None:
    command = PlanIssueCommand(
        issue_number=549,
        correlation_id="run-549",
        idempotency_key="plan-549",
        payload={"source": "watch"},
    )

    assert _admission(command).admission_key == _admission(command).admission_key


def test_correlation_alone_cannot_authorize_another_issue() -> None:
    first = _admission(PlanIssueCommand(issue_number=549, correlation_id="same-run"))
    second = _admission(PlanIssueCommand(issue_number=575, correlation_id="same-run"))

    assert first.admission_key != second.admission_key


def test_consciously_new_invocation_gets_new_budget_identity() -> None:
    first = _admission(
        PlanIssueCommand(
            issue_number=549,
            correlation_id="run-one",
            idempotency_key="authorization-one",
        )
    )
    second = _admission(
        PlanIssueCommand(
            issue_number=549,
            correlation_id="run-two",
            idempotency_key="authorization-two",
        )
    )

    assert first.admission_key != second.admission_key
