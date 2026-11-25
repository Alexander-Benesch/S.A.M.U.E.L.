from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.acceptance import PlanningSourceSnapshot
from samuel.core.bus import Bus
from samuel.core.commands import PlanIssueCommand, ScanIssuesCommand
from samuel.core.events import PlanPosted
from samuel.core.state import PlanningClarificationRecord, WorkflowBudgetAdmissionRecord
from samuel.core.types import Comment, Issue, Label
from samuel.slices.planning.clarification import ClarificationCoordinator
from samuel.slices.planning.handler import PlanningHandler
from samuel.slices.watch.handler import WatchHandler


class _SCM:
    def __init__(self) -> None:
        self.comments: list[Comment] = []

    def get_comments(self, _number: int) -> list[Comment]:
        return list(self.comments)

    def post_comment(self, _number: int, body: str) -> Comment:
        comment = Comment(
            id=len(self.comments) + 1,
            body=body,
            user="samuel",
            created_at="2026-09-19T10:00:00Z",
            updated_at="2026-09-19T10:00:00Z",
        )
        self.comments.append(comment)
        return comment


def _setup(tmp_path: Path):
    database = SQLiteStateStore(tmp_path)
    authority = database.authority
    snapshot = PlanningSourceSnapshot(
        schema_version=1,
        repository="owner/repo",
        base_ref="main",
        base_sha="a" * 40,
        issue_digest="sha256:" + "b" * 64,
    )
    now = datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)
    authority.put_budget_admission(
        WorkflowBudgetAdmissionRecord(
            admission_key="budget-1",
            repository="owner/repo",
            issue_number=7,
            invocation_digest="sha256:" + "c" * 64,
            source_digest=snapshot.digest,
            policy_digest="sha256:" + "d" * 64,
            correlation_id="run-7",
            token_limit=1000,
            created_at=now,
            updated_at=now,
        )
    )
    return database, authority, snapshot, now


def test_dialog_survives_restart_and_accepts_exact_answer(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    issue = Issue(7, "Timeout", "TBD: Timeout festlegen", "open")
    coordinator = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=3600,
        now=lambda: now,
    )

    assert coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-7",
    ) == (False, None)
    record = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert record is not None and record.status == "waiting"
    assert len(scm.comments) == 1

    # A newly constructed coordinator represents process restart.
    scm.comments.append(
        Comment(
            id=2,
            body=f"S.A.M.U.E.L.-Klärung: {record.series_key}/R1\n1. 30 Sekunden",
            user="alice",
            created_at="2026-09-19T10:05:00Z",
            updated_at="2026-09-19T10:05:00Z",
        )
    )
    restarted = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=3600,
        now=lambda: now + timedelta(minutes=10),
    )
    proceed, basis = restarted.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-8",
    )
    assert proceed is True and basis is not None
    assert basis.rounds[0]["answer_actor"] == "alice"
    assert any(event.name == "ClarificationAccepted" for event in events)


def test_restart_recovers_question_staged_before_scm_delivery(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    staged = PlanningClarificationRecord(
        series_key="clr-staged",
        repository="owner/repo",
        issue_number=7,
        source_digest=snapshot.digest,
        admission_key="budget-1",
        correlation_id="run-7",
        status="waiting",
        round_number=1,
        deadline_at=now + timedelta(hours=1),
        rounds=(
            {
                "round_number": 1,
                "questions": ["Welches Timeout soll gelten?"],
                "question_comment_id": 0,
                "question_digest": "",
                "question_revision": "",
            },
        ),
        created_at=now,
        updated_at=now,
    )
    authority.put_planning_clarification(staged)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    coordinator = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=3600,
        now=lambda: now,
    )

    assert coordinator.process(
        issue=Issue(7, "Timeout", "Offen: Timeout", "open"),
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-8",
    ) == (False, None)
    recovered = authority.find_active_planning_clarification(
        repository="owner/repo", issue_number=7
    )
    assert recovered is not None
    assert recovered.rounds[0]["question_comment_id"] == 1
    assert len(scm.comments) == 1
    assert any(event.name == "ClarificationRequested" for event in events)


def test_restart_ignores_request_marker_with_mismatched_bound_source(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    staged = PlanningClarificationRecord(
        series_key="clr-staged",
        repository="owner/repo",
        issue_number=7,
        source_digest=snapshot.digest,
        admission_key="budget-1",
        correlation_id="run-7",
        status="waiting",
        round_number=1,
        deadline_at=now + timedelta(hours=1),
        rounds=(
            {
                "round_number": 1,
                "questions": ["Welches Timeout soll gelten?"],
                "question_comment_id": 0,
                "question_digest": "",
                "question_revision": "",
            },
        ),
        created_at=now,
        updated_at=now,
    )
    authority.put_planning_clarification(staged)
    scm = _SCM()
    scm.comments.append(
        Comment(
            id=1,
            body=(
                '## Klärung\n\n<!-- samuel-clarification-request: {"deadline_at":'
                '"2026-09-19T11:00:00+00:00","questions":["Welches Timeout soll '
                'gelten?"],"round_number":1,"schema_version":1,"series_key":'
                '"clr-staged","source_digest":"sha256:ungebunden"} -->'
            ),
            user="mallory",
            created_at="2026-09-19T10:00:00Z",
            updated_at="2026-09-19T10:00:00Z",
        )
    )
    coordinator = ClarificationCoordinator(
        bus=Bus(), scm=scm, store=authority, wait_seconds=3600, now=lambda: now
    )

    assert coordinator.process(
        issue=Issue(7, "Timeout", "Offen: Timeout", "open"),
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-8",
    ) == (False, None)
    recovered = authority.find_active_planning_clarification(
        repository="owner/repo", issue_number=7
    )
    assert recovered is not None
    assert recovered.rounds[0]["question_comment_id"] == 2
    assert len(scm.comments) == 2


def test_timeout_is_terminal_and_does_not_create_contract(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    clock = [now]
    coordinator = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=10,
        now=lambda: clock[0],
    )
    issue = Issue(7, "Timeout", "Offen: Timeout", "open")
    coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-7",
    )
    clock[0] += timedelta(seconds=11)
    assert coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-8",
    ) == (False, None)
    latest = authority.find_latest_planning_clarification(repository="owner/repo", issue_number=7)
    assert latest is not None and latest.status == "timed_out"
    assert [event.name for event in events][-2:] == ["PlanBlocked", "WorkflowAborted"]


def test_missing_explicit_wait_blocks_before_request(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    coordinator = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=None,
        now=lambda: now,
    )
    assert coordinator.process(
        issue=Issue(7, "Timeout", "Offen: Timeout", "open"),
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-7",
    ) == (False, None)
    assert not scm.comments or "Planung blockiert" in scm.comments[0].body
    assert any(
        event.payload.get("reason") == "clarification_wait_not_explicitly_configured"
        for event in events
    )


def test_duplicate_answers_are_terminal_and_never_form_a_basis(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    coordinator = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=3600,
        now=lambda: now,
    )
    issue = Issue(7, "Timeout", "Offen: Timeout", "open")
    coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-7",
    )
    record = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert record is not None
    for comment_id, actor in ((2, "alice"), (3, "bob")):
        scm.comments.append(
            Comment(
                id=comment_id,
                body=f"S.A.M.U.E.L.-Klärung: {record.series_key}/R1\n1. 30 Sekunden",
                user=actor,
                created_at="2026-09-19T10:05:00Z",
                updated_at="2026-09-19T10:05:00Z",
            )
        )

    assert coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-8",
    ) == (False, None)
    latest = authority.find_latest_planning_clarification(repository="owner/repo", issue_number=7)
    assert latest is not None and latest.status == "exhausted"
    assert any(event.payload.get("reason") == "clarification_answer_duplicate" for event in events)


def test_late_answer_is_terminal_even_when_observed_before_poll_timeout(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    coordinator = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=10,
        now=lambda: now,
    )
    issue = Issue(7, "Timeout", "Offen: Timeout", "open")
    coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-7",
    )
    record = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert record is not None
    scm.comments.append(
        Comment(
            id=2,
            body=f"S.A.M.U.E.L.-Klärung: {record.series_key}/R1\n1. 30 Sekunden",
            user="alice",
            created_at="2026-09-19T10:00:05Z",
            updated_at="2026-09-19T10:00:11Z",
        )
    )

    assert coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-8",
    ) == (False, None)
    latest = authority.find_latest_planning_clarification(repository="owner/repo", issue_number=7)
    assert latest is not None and latest.status == "timed_out"
    assert any(
        event.payload.get("reason") == "clarification_answer_late_or_unversioned"
        for event in events
    )


def test_two_unresolved_rounds_exhaust_without_partial_basis(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    coordinator = ClarificationCoordinator(
        bus=bus,
        scm=scm,
        store=authority,
        wait_seconds=3600,
        now=lambda: now,
    )
    issue = Issue(7, "Timeout", "Offen: Timeout", "open")
    coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-7",
    )
    record = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert record is not None
    scm.comments.append(
        Comment(
            id=2,
            body=f"S.A.M.U.E.L.-Klärung: {record.series_key}/R1\n1. TBD",
            user="alice",
            created_at="2026-09-19T10:05:00Z",
            updated_at="2026-09-19T10:05:00Z",
        )
    )
    assert coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-8",
    ) == (False, None)
    round_two = authority.find_active_planning_clarification(
        repository="owner/repo", issue_number=7
    )
    assert round_two is not None and round_two.round_number == 2
    scm.comments.append(
        Comment(
            id=4,
            body=f"S.A.M.U.E.L.-Klärung: {record.series_key}/R2\n1. Offen: weiterhin",
            user="alice",
            created_at="2026-09-19T10:10:00Z",
            updated_at="2026-09-19T10:10:00Z",
        )
    )
    assert coordinator.process(
        issue=issue,
        source_snapshot=snapshot,
        admission_key="budget-1",
        correlation_id="run-9",
    ) == (False, None)
    latest = authority.find_latest_planning_clarification(repository="owner/repo", issue_number=7)
    assert latest is not None and latest.status == "exhausted"
    assert len(latest.rounds) == 2


def test_source_drift_requires_explicit_run_before_new_series(tmp_path: Path) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    issue = Issue(7, "Timeout", "Offen: Timeout", "open")
    handler = PlanningHandler(
        bus,
        scm=scm,
        llm=cast(Any, object()),  # not reached while the issue still needs clarification
        project_root=tmp_path,
        authority_store=authority,
        workflow_budget_policy={"token_limit": 1000},
        workflow_policy_digest="sha256:" + "d" * 64,
        clarification_wait_seconds=3600,
    )
    handler._handle_budgeted(
        PlanIssueCommand(issue_number=7, correlation_id="run-7"),
        7,
        issue=issue,
        project_root=tmp_path,
        source_snapshot=snapshot,
    )
    old = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert old is not None

    changed_snapshot = PlanningSourceSnapshot(
        schema_version=1,
        repository="owner/repo",
        base_ref="main",
        base_sha="a" * 40,
        issue_digest="sha256:" + "e" * 64,
    )
    handler._handle_budgeted(
        PlanIssueCommand(issue_number=7, correlation_id="watch-8"),
        7,
        issue=issue,
        project_root=tmp_path,
        source_snapshot=changed_snapshot,
    )
    assert authority.get_planning_clarification(old.series_key).status == "superseded"  # type: ignore[union-attr]
    assert any(
        event.payload.get("reason") == "clarification_continuation_requires_explicit_run"
        for event in events
    )
    assert (
        authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
        is None
    )

    handler._handle_budgeted(
        PlanIssueCommand(
            issue_number=7,
            correlation_id="operator-9",
            clarification_continuation_authorized=True,
        ),
        7,
        issue=issue,
        project_root=tmp_path,
        source_snapshot=changed_snapshot,
    )
    new = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert new is not None and new.series_key != old.series_key
    assert new.source_digest == changed_snapshot.digest


class _WatchSCM(_SCM):
    capabilities = {"issues"}

    def __init__(self, issue: Issue) -> None:
        super().__init__()
        self.issue = issue

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return [self.issue] if "ready-for-agent" in labels else []

    def swap_label(self, _number: int, _remove: str, _add: str) -> None:
        raise AssertionError("Clarification must not change approval labels")


@pytest.mark.parametrize("resolved", [False, True])
def test_watch_second_question_belongs_to_current_dispatch(tmp_path: Path, resolved: bool) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    issue = Issue(7, "Timeout", "Offen: Timeout", "open", labels=[Label(1, "risk:low")])
    scm = _WatchSCM(issue)
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    coordinator = ClarificationCoordinator(
        bus=bus, scm=scm, store=authority, wait_seconds=3600, now=lambda: now
    )
    accepted: list[Any] = []

    def planning(event: Any) -> None:
        proceed, basis = coordinator.process(
            issue=issue,
            source_snapshot=snapshot,
            admission_key="budget-1",
            correlation_id=event.correlation_id,
        )
        if proceed:
            accepted.append(basis)
            bus.publish(PlanPosted(payload={"issue": 7}, correlation_id=event.correlation_id))

    bus.subscribe("IssueReady", planning)
    watch = WatchHandler(bus, scm=cast(Any, scm))
    first = watch.handle(ScanIssuesCommand(payload={}, correlation_id="scan-first"))
    assert first["dispatched_failed"] == 0
    assert first["dispatch_outcomes"][0]["status"] == "waiting"
    record = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert record is not None
    scm.comments.append(
        Comment(
            id=2,
            body=f"S.A.M.U.E.L.-Klärung: {record.series_key}/R1\n1. TBD",
            user="alice",
            created_at="2026-09-19T10:05:00Z",
            updated_at="2026-09-19T10:05:00Z",
        )
    )
    second = watch.handle(ScanIssuesCommand(payload={}, correlation_id="scan-second"))
    assert second["dispatched_failed"] == 0
    assert second["planned"] == 0
    assert second["dispatch_outcomes"][0]["status"] == "waiting"
    requested = [event for event in events if event.name == "ClarificationRequested"]
    assert [(event.payload["round"], event.correlation_id) for event in requested] == [
        (1, "scan-first"),
        (2, "scan-second"),
    ]
    second_record = authority.get_planning_clarification(record.series_key)
    assert second_record is not None
    assert second_record.correlation_id == record.correlation_id == "scan-first"
    assert second_record.admission_key == record.admission_key == "budget-1"
    assert second_record.source_digest == record.source_digest == snapshot.digest
    assert accepted == []
    text = "30 Sekunden" if resolved else "TBD"
    scm.comments.append(
        Comment(
            id=4,
            body=f"S.A.M.U.E.L.-Klärung: {record.series_key}/R2\n1. {text}",
            user="alice",
            created_at="2026-09-19T10:10:00Z",
            updated_at="2026-09-19T10:10:00Z",
        )
    )
    third = watch.handle(ScanIssuesCommand(payload={}, correlation_id="scan-third"))
    if resolved:
        assert third["planned"] == 1 and third["dispatched_failed"] == 0
        assert len(accepted) == 1 and len(accepted[0].rounds) == 2
    else:
        assert third["planned"] == 0 and third["dispatched_failed"] == 1
        assert accepted == []
        assert any(
            event.payload.get("reason") == "clarification_rounds_exhausted"
            and event.correlation_id == "scan-third"
            for event in events
        )


@pytest.mark.parametrize("delivered", [False, True])
def test_recovered_question_uses_current_correlation_without_rebinding_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delivered: bool
) -> None:
    _database, authority, snapshot, now = _setup(tmp_path)
    scm = _SCM()
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("*", events.append)
    issue = Issue(7, "Timeout", "Offen: Timeout", "open")
    original_post = scm.post_comment

    def interrupted_post(number: int, body: str) -> Comment:
        if delivered:
            original_post(number, body)
        raise OSError("SCM connection interrupted")

    monkeypatch.setattr(scm, "post_comment", interrupted_post)
    first = ClarificationCoordinator(
        bus=bus, scm=scm, store=authority, wait_seconds=3600, now=lambda: now
    )
    assert first.process(
        issue=issue, source_snapshot=snapshot, admission_key="budget-1", correlation_id="first"
    ) == (False, None)
    before = authority.find_active_planning_clarification(repository="owner/repo", issue_number=7)
    assert before is not None and before.rounds[0]["question_comment_id"] == 0
    monkeypatch.setattr(scm, "post_comment", original_post)
    restarted = ClarificationCoordinator(
        bus=bus, scm=scm, store=authority, wait_seconds=3600, now=lambda: now
    )
    assert restarted.process(
        issue=issue, source_snapshot=snapshot, admission_key="budget-1", correlation_id="restarted"
    ) == (False, None)
    requested = [event for event in events if event.name == "ClarificationRequested"]
    assert len(requested) == 1 and requested[0].correlation_id == "restarted"
    assert len(scm.comments) == 1
    after = authority.get_planning_clarification(before.series_key)
    assert after is not None and after.rounds[0]["question_comment_id"] == scm.comments[0].id
    assert after.correlation_id == before.correlation_id == "first"
    assert after.admission_key == before.admission_key
    assert after.source_digest == before.source_digest
    assert after.deadline_at == before.deadline_at
