from __future__ import annotations

import pytest

from samuel.core.acceptance import parse_acceptance_contract
from samuel.core.bus import Bus
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import (
    CandidateEvaluationCompleted,
    CandidateEvaluationFailed,
    CandidateSubmissionRejected,
    CandidateVerificationPending,
    CodeGenerated,
    EvaluationSubjectInvalidated,
    Event,
    GateFailedEvent,
    GatesPassed,
    HealingAttemptStarted,
    PlanApproved,
    PlanBlocked,
    PlanCreated,
    PlanPosted,
    PlanReplanRejected,
    PlanValidated,
    PRCreated,
    PRCreationFailed,
    WorkflowBlocked,
)
from samuel.core.ports import IVersionControl
from samuel.core.types import PR, Comment, Issue
from samuel.slices.labels.handler import LabelsHandler


class FakeSCM(IVersionControl):
    def __init__(self) -> None:
        self.swap_calls: list[tuple[int, str, str]] = []
        self.fail_on: set[tuple[str, str]] = set()
        self.labels: dict[int, set[str]] = {}

    @property
    def repository_identity(self) -> str:
        return "owner/repo"

    def swap_label(self, number: int, remove: str, add: str) -> None:
        if (remove, add) in self.fail_on:
            raise RuntimeError("simulated failure")
        self.swap_calls.append((number, remove, add))
        current = self.labels.setdefault(number, set())
        if remove:
            current.discard(remove)
        if add:
            current.add(add)

    # Unused — stubs to satisfy ABC
    def get_issue(self, number: int) -> Issue:
        raise NotImplementedError

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        raise NotImplementedError

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        raise NotImplementedError

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {}

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None: ...
    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""


@pytest.fixture
def bus() -> Bus:
    return Bus()


@pytest.fixture
def scm() -> FakeSCM:
    return FakeSCM()


@pytest.fixture
def handler(bus: Bus, scm: FakeSCM) -> LabelsHandler:
    h = LabelsHandler(bus, scm=scm)
    h.register()
    return h


class TestTransitions:
    def test_confirmed_merge_cleans_workflow_labels_without_closing_issue(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler, monkeypatch
    ) -> None:
        plan = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] safe.py"
        monkeypatch.setattr(scm, "get_comments", lambda number: [Comment(10, plan, "bot")])
        subject = EvaluationSubject(
            "owner/repo",
            "a" * 40,
            "b" * 40,
            parse_acceptance_contract(plan).contract_hash,
            "policy",
            "sha256:" + "c" * 64,
        )
        scm.labels[42] = {"needs-review", "status:wip", "risk:low"}
        bus.publish(
            Event(name="PRMerged", payload={"issue": 42, "evaluation_subject": subject.as_dict()})
        )
        assert scm.labels[42] == {"status:done", "risk:low"}
        bus.publish(PlanPosted(payload={"issue": 42}))
        assert "status:done" not in scm.labels[42]

    def test_old_candidate_merge_does_not_finish_new_active_plan(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler, monkeypatch
    ) -> None:
        old = parse_acceptance_contract("## Plan\nAgent-Metadaten\n- [ ] [DIFF] old.py")
        new = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] new.py"
        monkeypatch.setattr(scm, "get_comments", lambda number: [Comment(11, new, "bot")])
        subject = EvaluationSubject(
            "owner/repo", "a" * 40, "b" * 40, old.contract_hash, "policy", "sha256:" + "c" * 64
        )
        scm.labels[42] = {"status:plan", "needs-review"}
        bus.publish(
            Event(name="PRMerged", payload={"issue": 42, "evaluation_subject": subject.as_dict()})
        )
        assert scm.swap_calls == []

    def test_subject_invalidation_removes_merged_projection(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        scm.labels[42] = {"status:done", "risk:low"}
        bus.publish(EvaluationSubjectInvalidated(payload={"issue": 42}))
        assert scm.labels[42] == {"status:failed", "risk:low"}

    def test_issue_ready_adds_ready_for_agent(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(Event(name="IssueReady", payload={"issue_number": 42}))
        assert (42, "", "ready-for-agent") in scm.swap_calls

    def test_plan_created_does_not_claim_visible_plan(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PlanCreated(payload={"issue": 42}))
        assert scm.swap_calls == []

    def test_plan_posted_moves_ready_to_status_plan(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PlanPosted(payload={"issue": 42}))
        assert (42, "ready-for-agent", "status:plan") in scm.swap_calls

    def test_plan_validated_does_not_self_approve(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PlanValidated(payload={"issue": 42}))
        assert scm.swap_calls == []

    def test_plan_approved_preserves_authority_until_pr_created(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        scm.labels[42] = {"status:approved", "status:plan"}

        bus.publish(PlanApproved(payload={"issue": 42}))
        assert (42, "", "status:wip") in scm.swap_calls
        assert (42, "status:plan", "") in scm.swap_calls
        assert (42, "status:failed", "") in scm.swap_calls
        assert scm.labels[42] == {"status:approved", "status:wip"}

        bus.publish(CodeGenerated(payload={"issue": 42}))

        assert "status:approved" in scm.labels[42]

        bus.publish(PRCreated(payload={"issue": 42}))

        assert "status:approved" not in scm.labels[42]
        assert "needs-review" in scm.labels[42]

    def test_code_generated_swaps_ready_to_in_progress_and_wip(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(CodeGenerated(payload={"issue": 42}))
        assert (42, "ready-for-agent", "in-progress") in scm.swap_calls
        assert (42, "", "status:wip") in scm.swap_calls

    def test_pr_created_swaps_in_progress_to_needs_review(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PRCreated(payload={"issue": 42}))
        assert (42, "in-progress", "needs-review") in scm.swap_calls
        assert (42, "status:approved", "") in scm.swap_calls

    def test_plan_blocked_clears_success_labels_and_sets_failed(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PlanBlocked(payload={"issue": 42}))
        assert (42, "status:plan", "") in scm.swap_calls
        assert (42, "help wanted", "") in scm.swap_calls
        assert (42, "", "status:failed") in scm.swap_calls
        assert not any(add == "help wanted" for _, _, add in scm.swap_calls)

    def test_rejected_implicit_replan_preserves_active_plan_labels(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        scm.labels[42] = {"status:plan", "risk:low"}

        bus.publish(
            PlanReplanRejected(
                payload={"issue": 42, "reason": "active_plan_requires_explicit_replan"}
            )
        )

        assert scm.labels[42] == {"status:plan", "risk:low"}
        assert scm.swap_calls == []

    def test_gate_failed_sets_failed(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        bus.publish(GateFailedEvent(payload={"issue": 42}))
        assert (42, "", "status:failed") in scm.swap_calls

    @pytest.mark.parametrize(
        "event_type",
        [
            CandidateVerificationPending,
            CandidateEvaluationCompleted,
            CandidateEvaluationFailed,
            CandidateSubmissionRejected,
        ],
    )
    def test_passive_candidate_outcomes_do_not_mutate_labels(
        self,
        bus: Bus,
        scm: FakeSCM,
        handler: LabelsHandler,
        event_type,
    ) -> None:
        bus.publish(event_type(payload={"issue": 42, "mutation_authority": "none"}))

        assert scm.swap_calls == []

    def test_workflow_blocked_sets_failed(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(WorkflowBlocked(payload={"issue": 42}))
        assert (42, "", "status:failed") in scm.swap_calls

    def test_pr_creation_failed_clears_review_labels_and_sets_failed(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PRCreationFailed(payload={"issue": 42}))

        assert (42, "needs-review", "") in scm.swap_calls
        assert (42, "", "status:failed") in scm.swap_calls
        assert not any(add == "needs-review" for _, _, add in scm.swap_calls)

    def test_subject_invalidation_revokes_review_label(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(EvaluationSubjectInvalidated(payload={"issue": 42}))

        assert (42, "needs-review", "") in scm.swap_calls
        assert (42, "", "status:failed") in scm.swap_calls

    def test_successful_bound_healing_replaces_failed_with_review_state(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        correlation_id = "healing-run"
        origin = "sha256:" + "a" * 64

        bus.publish(GateFailedEvent(payload={"issue": 42}, correlation_id=correlation_id))
        bus.publish(
            HealingAttemptStarted(
                payload={"issue": 42, "observation_key": origin},
                correlation_id=correlation_id,
            )
        )
        bus.publish(
            CodeGenerated(
                payload={"issue": 42, "healing_origin_observation_key": origin},
                correlation_id=correlation_id,
            )
        )
        bus.publish(GatesPassed(payload={"issue": 42}, correlation_id=correlation_id))
        bus.publish(
            PRCreated(
                payload={"issue": 42, "healing_origin_observation_key": origin},
                correlation_id=correlation_id,
            )
        )

        assert scm.labels[42] == {"status:wip", "needs-review"}
        assert (42, "status:failed", "") in scm.swap_calls

    @pytest.mark.parametrize(
        ("pr_correlation_id", "pr_origin"),
        [
            ("unrelated-run", "sha256:" + "a" * 64),
            ("healing-run", "sha256:" + "b" * 64),
            ("healing-run", ""),
        ],
    )
    def test_unbound_pr_does_not_clear_failed_healing_state(
        self,
        bus: Bus,
        scm: FakeSCM,
        handler: LabelsHandler,
        pr_correlation_id: str,
        pr_origin: str,
    ) -> None:
        origin = "sha256:" + "a" * 64
        bus.publish(GateFailedEvent(payload={"issue": 42}, correlation_id="healing-run"))
        bus.publish(
            HealingAttemptStarted(
                payload={"issue": 42, "observation_key": origin},
                correlation_id="healing-run",
            )
        )

        bus.publish(
            PRCreated(
                payload={"issue": 42, "healing_origin_observation_key": pr_origin},
                correlation_id=pr_correlation_id,
            )
        )

        assert "status:failed" in scm.labels[42]
        assert (42, "status:failed", "") not in scm.swap_calls

    def test_terminal_healing_refail_cannot_be_cleared_by_late_pr(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        correlation_id = "healing-run"
        origin = "sha256:" + "a" * 64
        bus.publish(GateFailedEvent(payload={"issue": 42}, correlation_id=correlation_id))
        bus.publish(
            HealingAttemptStarted(
                payload={"issue": 42, "observation_key": origin},
                correlation_id=correlation_id,
            )
        )
        bus.publish(CodeGenerated(payload={"issue": 42}, correlation_id=correlation_id))
        bus.publish(GateFailedEvent(payload={"issue": 42}, correlation_id=correlation_id))
        bus.publish(
            WorkflowBlocked(
                payload={"issue": 42, "reason": "bound_healing:repeated_failure"},
                correlation_id=correlation_id,
            )
        )
        assert scm.labels[42] == {"status:failed"}
        scm.swap_calls.clear()

        bus.publish(
            PRCreated(
                payload={"issue": 42, "healing_origin_observation_key": origin},
                correlation_id=correlation_id,
            )
        )

        assert "status:failed" in scm.labels[42]
        assert (42, "status:failed", "") not in scm.swap_calls

    def test_pr_for_other_issue_cannot_clear_failed_healing_state(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        correlation_id = "healing-run"
        origin = "sha256:" + "a" * 64
        bus.publish(GateFailedEvent(payload={"issue": 42}, correlation_id=correlation_id))
        bus.publish(
            HealingAttemptStarted(
                payload={"issue": 42, "observation_key": origin},
                correlation_id=correlation_id,
            )
        )

        bus.publish(
            PRCreated(
                payload={"issue": 43, "healing_origin_observation_key": origin},
                correlation_id=correlation_id,
            )
        )

        assert scm.labels[42] == {"status:failed"}
        assert (42, "status:failed", "") not in scm.swap_calls


class TestPayloadExtraction:
    def test_issue_number_from_issue_field(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PlanPosted(payload={"issue": 7}))
        assert any(c[0] == 7 for c in scm.swap_calls)

    def test_issue_number_from_issue_number_field(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(Event(name="IssueReady", payload={"issue_number": 8}))
        assert any(c[0] == 8 for c in scm.swap_calls)

    def test_issue_number_as_string_is_accepted(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PlanPosted(payload={"issue": "9"}))
        assert any(c[0] == 9 for c in scm.swap_calls)

    def test_no_issue_number_skips_silently(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(PlanCreated(payload={}))
        assert scm.swap_calls == []


class TestErrorHandling:
    def test_scm_failure_is_swallowed(self, bus: Bus, scm: FakeSCM, handler: LabelsHandler) -> None:
        scm.fail_on.add(("", "ready-for-agent"))
        bus.publish(Event(name="IssueReady", payload={"issue_number": 42}))

    def test_no_scm_skips(self, bus: Bus) -> None:
        h = LabelsHandler(bus, scm=None)
        h.register()
        bus.publish(PlanCreated(payload={"issue": 1}))


class TestNoRegression:
    def test_unrelated_event_triggers_nothing(
        self, bus: Bus, scm: FakeSCM, handler: LabelsHandler
    ) -> None:
        bus.publish(Event(name="SomeUnrelatedEvent", payload={"issue": 42}))
        assert scm.swap_calls == []
