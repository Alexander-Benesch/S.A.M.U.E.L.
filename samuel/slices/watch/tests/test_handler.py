from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from samuel.core.bus import Bus, ErrorMiddleware
from samuel.core.commands import ScanIssuesCommand
from samuel.core.errors import AgentAbort
from samuel.core.events import Event, PlanPosted, PRCreated
from samuel.core.ports import IConfig, IVersionControl
from samuel.core.state import AuthorityRecord
from samuel.core.types import Comment, Issue, Label, SCMActivity, SCMLabelEvent
from samuel.core.workflow import WorkflowEngine
from samuel.slices.watch.handler import (
    LABEL_APPROVED,
    LABEL_PLAN,
    WatchHandler,
)


class MockSCM(IVersionControl):
    def __init__(self, issues_by_label: dict[str, list[Issue]] | None = None):
        self._issues = issues_by_label or {}
        self.label_swaps: list[tuple[int, str, str]] = []

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return []

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=1, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        self.label_swaps.append((number, remove, add))

    def list_issues(self, labels: list[str]) -> list[Issue]:
        key = labels[0] if labels else ""
        return self._issues.get(key, [])

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


class _ApprovalAuthority:
    def __init__(self) -> None:
        self.records: dict[str, AuthorityRecord] = {}

    def find_budget_admission(self, **_kwargs: Any) -> Any:
        return SimpleNamespace(admission_key="budget-plan")

    def put_authority_record(self, record: AuthorityRecord) -> bool:
        self.records.setdefault(record.record_key, record)
        return True

    def get_authority_record(self, key: str) -> AuthorityRecord | None:
        return self.records.get(key)


class MockConfig(IConfig):
    def __init__(
        self,
        *,
        features: dict[str, bool] | None = None,
        values: dict[str, Any] | None = None,
    ) -> None:
        self.reload_count = 0
        self._features = features or {}
        self._values = values or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return self._features.get(name, False)

    def reload(self) -> None:
        self.reload_count += 1


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestWatchHandler:
    def test_dispatches_ready_issues_to_planning(self):
        issues = {
            "ready-for-agent": [
                Issue(number=10, title="A", body="", state="open"),
                Issue(number=11, title="B", body="", state="open"),
            ]
        }
        scm = MockSCM(issues)
        bus = Bus()
        bus.register_command(
            "PlanIssue",
            lambda command: bus.publish(
                PlanPosted(
                    payload={"issue": command.payload["issue"]},
                    correlation_id=command.correlation_id or "",
                )
            ),
        )
        WorkflowEngine(bus, {"steps": [{"on": "IssueReady", "send": "PlanIssue"}]})
        events = _collect_events(bus)

        handler = WatchHandler(bus, scm=scm, max_parallel=1)
        result = handler.handle(ScanIssuesCommand())

        assert result["dispatched"] == 2
        assert result["planned"] == 2
        issue_ready = [e for e in events if e.name == "IssueReady"]
        assert len(issue_ready) == 2

    def test_dispatches_approved_issues_to_implementation(self):
        issues = {
            LABEL_APPROVED: [
                Issue(
                    number=10,
                    title="A",
                    body="",
                    state="open",
                    labels=[Label(id=1, name=LABEL_PLAN), Label(id=2, name=LABEL_APPROVED)],
                )
            ],
        }

        class PlanSCM(MockSCM):
            @property
            def repository_identity(self) -> str:
                return "owner/repo"

            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(
                        id=4,
                        body="## Plan\n- [ ] [DIFF] candidate.py",
                        user="bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

            def get_label_events(self, number: int, label: str):
                return [SCMLabelEvent("event:1", label, "alice", "human", "2026-08-25T10:00:00Z")]

        class BudgetAuthority(_ApprovalAuthority):
            def __init__(self) -> None:
                super().__init__()
                self.contract_hash = ""

            def find_budget_admission(self, **kwargs: Any) -> Any:
                assert kwargs["repository"] == "owner/repo"
                assert kwargs["issue_number"] == 10
                assert kwargs["plan_comment_id"] == 4
                self.contract_hash = str(kwargs["plan_contract_hash"])
                return SimpleNamespace(admission_key="budget-plan-10")

        scm = PlanSCM(issues)
        bus = Bus()
        bus.register_command(
            "Implement",
            lambda command: bus.publish(
                PRCreated(
                    payload={"issue": command.payload["issue"]},
                    correlation_id=command.correlation_id or "",
                )
            ),
        )
        WorkflowEngine(bus, {"steps": [{"on": "PlanApproved", "send": "Implement"}]})
        events = _collect_events(bus)

        authority = BudgetAuthority()
        handler = WatchHandler(bus, scm=scm, authority_store=authority)  # type: ignore[arg-type]
        result = handler.handle(ScanIssuesCommand())

        assert result["approved"] == 1
        approved = [e for e in events if e.name == "PlanApproved"]
        assert len(approved) == 1
        assert approved[0].payload["issue"] == 10
        receipt = approved[0].payload["acceptance_approval"]
        assert receipt["state"] == "approved"
        assert receipt["method"] == "status:approved/polling"
        assert receipt["contract_hash"].startswith("sha256:")
        assert authority.contract_hash == receipt["contract_hash"]
        assert approved[0].payload["budget_admission_key"] == "budget-plan-10"

    def test_approved_label_without_authority_store_blocks(self):
        issue = Issue(
            number=10,
            title="A",
            body="",
            state="open",
            labels=[Label(id=1, name=LABEL_PLAN), Label(id=2, name=LABEL_APPROVED)],
        )

        class PlanSCM(MockSCM):
            @property
            def repository_identity(self) -> str:
                return "owner/repo"

            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(
                        id=4,
                        body="## Plan\n- [ ] [DIFF] candidate.py",
                        user="bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

            def get_label_events(self, number: int, label: str):
                return [SCMLabelEvent("event:1", label, "alice", "human", "2026-08-25T10:00:00Z")]

        bus = Bus()
        events = _collect_events(bus)
        result = WatchHandler(bus, scm=PlanSCM({LABEL_APPROVED: [issue]})).handle(
            ScanIssuesCommand()
        )

        assert result["approved"] == 0
        assert result["dispatched_failed"] == 1
        assert any(
            event.name == "WorkflowBlocked"
            and event.payload.get("reason") == "plan_approval_authority_store_missing"
            for event in events
        )
        assert not any(event.name == "PlanApproved" for event in events)

    def test_missing_budget_admission_still_blocks_approved_plan(self):
        issue = Issue(
            number=10,
            title="A",
            body="",
            state="open",
            labels=[Label(id=1, name=LABEL_PLAN), Label(id=2, name=LABEL_APPROVED)],
        )

        class PlanSCM(MockSCM):
            @property
            def repository_identity(self) -> str:
                return "owner/repo"

            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(
                        id=4,
                        body="## Plan\n- [ ] [DIFF] candidate.py",
                        user="bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

            def get_label_events(self, number: int, label: str):
                return [SCMLabelEvent("event:1", label, "alice", "human", "2026-08-25T10:00:00Z")]

        class MissingBudgetAuthority(_ApprovalAuthority):
            def find_budget_admission(self, **kwargs: Any) -> None:
                return None

        bus = Bus()
        events = _collect_events(bus)
        result = WatchHandler(
            bus,
            scm=PlanSCM({LABEL_APPROVED: [issue]}),
            authority_store=MissingBudgetAuthority(),  # type: ignore[arg-type]
        ).handle(ScanIssuesCommand())

        assert result["approved"] == 0
        assert result["dispatched_failed"] == 1
        assert not any(event.name == "PlanApproved" for event in events)
        assert any(
            event.name == "WorkflowBlocked"
            and event.payload.get("reason") == "workflow_budget_admission_missing"
            for event in events
        )

    def test_polling_does_not_turn_ok_comment_into_approval(self):
        issue = Issue(
            number=16,
            title="Comment without webhook",
            body="",
            state="open",
            labels=[Label(id=1, name=LABEL_PLAN)],
        )

        class CommentSCM(MockSCM):
            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(id=4, body="## Plan\n- [ ] [DIFF] candidate.py", user="bot"),
                    Comment(id=5, body="ok", user="operator"),
                ]

        bus = Bus()
        events = _collect_events(bus)

        result = WatchHandler(
            bus,
            scm=CommentSCM({LABEL_PLAN: [issue]}),
        ).handle(ScanIssuesCommand())

        assert result["approved"] == 0
        assert result["dispatched"] == 0
        assert not any(event.name == "PlanApproved" for event in events)

    @pytest.mark.parametrize(
        "approval_event",
        [
            SCMLabelEvent("event:old", "status:approved", "alice", "human", "2026-08-25T08:00:00Z"),
            SCMLabelEvent(
                "event:bot", "status:approved", "example-bot", "bot", "2026-08-25T10:00:00Z"
            ),
            SCMLabelEvent("event:unknown", "status:approved", "", "human", "2026-08-25T10:00:00Z"),
            SCMLabelEvent("event:malformed", "status:approved", "alice", "human", "not-a-time"),
        ],
    )
    def test_polling_rejects_unbound_or_non_human_approval(self, approval_event):
        issue = Issue(
            number=17,
            title="Stale approval",
            body="",
            state="open",
            labels=[Label(id=1, name=LABEL_PLAN), Label(id=2, name=LABEL_APPROVED)],
        )

        class EvidenceSCM(MockSCM):
            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(
                        id=9,
                        body="## Plan\n- [ ] [DIFF] candidate.py",
                        user="bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

            def get_label_events(self, number: int, label: str):
                return [approval_event]

        bus = Bus()
        events = _collect_events(bus)
        result = WatchHandler(bus, scm=EvidenceSCM({LABEL_APPROVED: [issue]})).handle(
            ScanIssuesCommand()
        )

        assert result["approved"] == 0
        assert result["ignored_approvals"] >= 1
        assert not any(event.name == "PlanApproved" for event in events)

    def test_normal_command_exception_is_a_failed_dispatch(self):
        issue = Issue(number=12, title="Broken", body="", state="open")
        bus = Bus()
        bus.add_middleware(ErrorMiddleware(bus=bus))

        def fail(_command):
            raise RuntimeError("boom")

        bus.register_command("PlanIssue", fail)
        WorkflowEngine(bus, {"steps": [{"on": "IssueReady", "send": "PlanIssue"}]})

        result = WatchHandler(bus, scm=MockSCM({"ready-for-agent": [issue]})).handle(
            ScanIssuesCommand(correlation_id="corr-normal-error")
        )

        assert result["dispatched"] == 1
        assert result["dispatched_failed"] == 1
        assert result["planned"] == 0
        assert result["dispatch_outcomes"] == [
            {
                "issue": 12,
                "correlation_id": "corr-normal-error",
                "phase": "planning",
                "status": "aborted",
                "terminal_event": "WorkflowAborted",
            }
        ]

    def test_approval_command_exception_is_not_counted_as_approved(self):
        issue = Issue(
            number=14,
            title="Approval fails",
            body="",
            state="open",
            labels=[Label(id=1, name=LABEL_PLAN), Label(id=2, name=LABEL_APPROVED)],
        )

        class PlanSCM(MockSCM):
            @property
            def repository_identity(self) -> str:
                return "owner/repo"

            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(
                        id=5,
                        body="## Plan\n- [ ] [DIFF] candidate.py",
                        user="bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

            def get_label_events(self, number: int, label: str):
                return [SCMLabelEvent("event:2", label, "alice", "human", "2026-08-25T10:00:00Z")]

        bus = Bus()
        bus.add_middleware(ErrorMiddleware(bus=bus))

        def fail(_command):
            raise RuntimeError("implementation failed")

        bus.register_command("Implement", fail)
        WorkflowEngine(bus, {"steps": [{"on": "PlanApproved", "send": "Implement"}]})

        result = WatchHandler(
            bus,
            scm=PlanSCM({LABEL_APPROVED: [issue]}),
            authority_store=_ApprovalAuthority(),  # type: ignore[arg-type]
        ).handle(ScanIssuesCommand(correlation_id="corr-approval-error"))

        assert result["approved"] == 0
        assert result["dispatched_failed"] == 1
        assert result["dispatch_outcomes"] == [
            {
                "issue": 14,
                "correlation_id": "corr-approval-error",
                "phase": "approval",
                "status": "aborted",
                "terminal_event": "WorkflowAborted",
            }
        ]

    def test_agent_abort_is_bound_to_terminal_dispatch_outcome(self):
        issue = Issue(number=13, title="Abort", body="", state="open")
        bus = Bus()
        bus.add_middleware(ErrorMiddleware(bus=bus))

        def abort(_command):
            raise AgentAbort("policy stop", gate=4, issue=13)

        bus.register_command("PlanIssue", abort)
        WorkflowEngine(bus, {"steps": [{"on": "IssueReady", "send": "PlanIssue"}]})

        result = WatchHandler(bus, scm=MockSCM({"ready-for-agent": [issue]})).handle(
            ScanIssuesCommand(correlation_id="corr-agent-abort")
        )

        assert result["planned"] == 0
        assert result["dispatched_failed"] == 1
        assert result["dispatch_outcomes"][0] == {
            "issue": 13,
            "correlation_id": "corr-agent-abort",
            "phase": "planning",
            "status": "aborted",
            "terminal_event": "WorkflowAborted",
        }

    def test_mixed_batch_keeps_success_and_failure_per_issue(self):
        issues = [
            Issue(number=20, title="Works", body="", state="open"),
            Issue(number=21, title="Fails", body="", state="open"),
        ]
        bus = Bus()

        def process(event):
            if event.payload["issue"] == 20:
                bus.publish(
                    PlanPosted(
                        payload={"issue": 20},
                        correlation_id=event.correlation_id,
                    )
                )
            else:
                raise RuntimeError("broken subscriber")

        bus.subscribe("IssueReady", process)
        result = WatchHandler(bus, scm=MockSCM({"ready-for-agent": issues})).handle(
            ScanIssuesCommand(correlation_id="corr-mixed")
        )

        assert result["dispatched"] == 2
        assert result["planned"] == 1
        assert result["dispatched_failed"] == 1
        assert [entry["issue"] for entry in result["dispatch_outcomes"]] == [20, 21]
        assert [entry["status"] for entry in result["dispatch_outcomes"]] == [
            "planned",
            "failed",
        ]

    def test_does_not_approve_without_a_previously_visible_plan(self):
        issues = {
            LABEL_APPROVED: [
                Issue(
                    number=10,
                    title="A",
                    body="",
                    state="open",
                    labels=[Label(id=1, name=LABEL_APPROVED)],
                )
            ],
        }
        scm = MockSCM(issues)
        bus = Bus()
        events = _collect_events(bus)

        result = WatchHandler(bus, scm=scm).handle(ScanIssuesCommand())

        assert result["approved"] == 0
        assert result["ignored_approvals"] == 1
        assert not any(e.name == "PlanApproved" for e in events)

    def test_dispatches_all_issues_sequentially_and_releases_slot(self):
        issues = {
            "ready-for-agent": [
                Issue(number=i, title=f"Issue {i}", body="", state="open") for i in range(5)
            ]
        }
        scm = MockSCM(issues)
        bus = Bus()
        handler = WatchHandler(bus, scm=scm, max_parallel=1)
        observed: list[int] = []
        active_snapshots: list[set[int]] = []

        def observe_dispatch(event):
            observed.append(event.payload["issue"])
            active_snapshots.append(set(handler._active))

        bus.subscribe("IssueReady", observe_dispatch)
        result = handler.handle(ScanIssuesCommand())

        assert result["dispatched"] == 5
        assert observed == list(range(5))
        assert active_snapshots == [{issue} for issue in range(5)]
        assert handler._active == set()
        assert handler._try_acquire(99) is True
        handler._release(99)

    @pytest.mark.parametrize("value", [0, 2, True, 1.0])
    def test_rejects_parallel_handler_without_dispatcher(self, value):
        with pytest.raises(ValueError, match="max_parallel must be exactly 1"):
            WatchHandler(Bus(), max_parallel=value)

    def test_no_scm_returns_zero(self):
        bus = Bus()
        handler = WatchHandler(bus, scm=None)
        result = handler.handle(ScanIssuesCommand())
        assert result["dispatched"] == 0

    def test_hot_reload_called(self):
        scm = MockSCM()
        config = MockConfig()
        bus = Bus()

        handler = WatchHandler(bus, scm=scm, config=config)
        handler.handle(ScanIssuesCommand())

        assert config.reload_count == 1

    def test_label_consistency_fixes_duplicates(self):
        issues_plan = [
            Issue(
                number=42,
                title="X",
                body="",
                state="open",
                labels=[Label(id=1, name=LABEL_PLAN), Label(id=2, name=LABEL_APPROVED)],
            ),
        ]
        scm = MockSCM({LABEL_PLAN: issues_plan, LABEL_APPROVED: []})
        bus = Bus()

        handler = WatchHandler(bus, scm=scm)
        result = handler.handle(ScanIssuesCommand())

        assert result["label_fixes"] >= 1
        assert len(scm.label_swaps) >= 1

    def test_correlation_id_flows(self):
        issues = {
            "ready-for-agent": [
                Issue(number=10, title="A", body="", state="open"),
            ]
        }
        scm = MockSCM(issues)
        bus = Bus()
        bus.register_command("PlanIssue", lambda cmd: None)
        events = _collect_events(bus)

        handler = WatchHandler(bus, scm=scm)
        handler.handle(ScanIssuesCommand(correlation_id="watch-corr-1"))

        for e in events:
            if e.name == "IssueReady":
                assert e.correlation_id == "watch-corr-1"

    def test_empty_approved_list(self):
        scm = MockSCM({LABEL_APPROVED: []})
        bus = Bus()

        handler = WatchHandler(bus, scm=scm)
        result = handler.handle(ScanIssuesCommand())

        assert result["dispatched"] == 0

    def test_activity_polling_is_disabled_by_default(self):
        result = WatchHandler(Bus(), scm=MockSCM(), config=MockConfig()).handle(ScanIssuesCommand())

        assert result["activity_poll"] == "disabled"
        assert result["activity_observed"] == 0

    def test_activity_polling_is_wired_when_enabled(self, tmp_path):
        class ActivitySCM(MockSCM):
            @property
            def capabilities(self) -> set[str]:
                return {"activity_polling"}

            def list_scm_activity(self, since: str, limit: int = 250) -> list[SCMActivity]:
                return [
                    SCMActivity(
                        event="IssueOpened",
                        number=390,
                        timestamp="2026-08-21T10:00:00Z",
                        title="Polling",
                        actor="alice",
                    )
                ]

        config = MockConfig(
            features={"scm_activity_polling": True},
            values={"agent.data_dir": str(tmp_path)},
        )
        bus = Bus()
        events = _collect_events(bus)

        result = WatchHandler(bus, scm=ActivitySCM(), config=config).handle(
            ScanIssuesCommand(correlation_id="corr-390")
        )

        assert result["activity_poll"] == "ok"
        assert result["activity_observed"] == 1
        assert result["activity_forwarded"] == 1
        observed = [event for event in events if event.name == "IssueOpened"]
        assert len(observed) == 1
        assert observed[0].payload["source"] == "polling"
        assert observed[0].correlation_id == "corr-390"
        assert (tmp_path / "scm_activity_poll.json").exists()
