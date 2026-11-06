from __future__ import annotations

import threading
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.acceptance import (
    AcceptanceApproval,
    PlanningSourceSnapshot,
    issue_revision_digest,
    latest_active_plan,
    parse_acceptance_contract,
    persist_plan_approval,
    render_planning_source,
)
from samuel.core.bus import Bus
from samuel.core.commands import ImplementCommand, PlanIssueCommand
from samuel.core.configuration_session import ConfigurationConflict, ConfigurationSession
from samuel.core.events import Event
from samuel.core.ports import IVersionControl
from samuel.core.state import OperationIntentRecord
from samuel.core.types import PR, Comment, Issue, Label, SCMLabelEvent
from samuel.core.workflow_recovery import WorkflowRecovery
from samuel.slices.run_projection.handler import RunProjectionHandler

PLAN = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] example.py"


@pytest.fixture
def runtime(tmp_path: Path) -> tuple[Bus, WorkflowRecovery, Any]:
    store = SQLiteStateStore(tmp_path / "data")
    bus = Bus()
    bus.state_store = store
    bus.authority_state_store = store.authority
    bus.run_projection_store = store.projections
    bus.configuration_session = ConfigurationSession(store.authority)
    scm = Mock(spec=IVersionControl)
    scm.repository_identity = "fixture/repository"
    issue = Issue(42, "Task", "Implement the task", "open")
    comments: list[Comment] = []
    scm.get_issue.side_effect = lambda number: deepcopy(issue)
    scm.get_comments.side_effect = lambda number: deepcopy(comments)
    scm.fixture_issue, scm.fixture_comments = issue, comments

    def post(number: int, body: str) -> Comment:
        comment = Comment(len(comments) + 1, body, "agent", "2026-11-05T10:00:00Z")
        comments.append(comment)
        return comment

    def swap(number: int, remove: str, add: str) -> None:
        issue.labels[:] = [label for label in issue.labels if label.name != remove]
        if add:
            issue.labels.append(Label(len(issue.labels) + 1, add))

    scm.post_comment.side_effect = post
    scm.swap_label.side_effect = swap
    bus.workflow_recovery = recovery = WorkflowRecovery(bus, scm)
    RunProjectionHandler(bus, store.projections).register()
    return bus, recovery, scm


def fail(bus: Bus, event: str = "PlanBlocked") -> str:
    def handler(cmd: Any) -> None:
        bus.publish(
            Event(
                name=event,
                correlation_id=cmd.correlation_id,
                payload={"issue": 42, "reason": "fixture_failure"},
            )
        )

    bus.register_command("PlanIssue", handler)
    cmd = PlanIssueCommand(issue_number=42)
    bus.send(cmd)
    return str(cmd.correlation_id)


@pytest.mark.parametrize(
    "event",
    [
        "PlanBlocked",
        "WorkflowBlocked",
        "ReviewBlocked",
        "PRCreationFailed",
        "WorkflowAborted",
        "EvaluationSubjectInvalidated",
        "ProviderVerificationBlocked",
        "CandidateEvaluationFailed",
        "CandidateSubmissionRejected",
        "LLMUnavailable",
        "MergeOutcomeUnknown",
    ],
)
def test_terminal_failure_fences_new_dispatch_until_explicit_action(runtime, event: str) -> None:
    bus, recovery, scm = runtime
    correlation = fail(bus, event)
    handler = Mock()
    bus.register_command("PlanIssue", handler)
    for _ in range(3):
        assert bus.send(PlanIssueCommand(issue_number=42))["success"] is False
    handler.assert_not_called()
    status = recovery.inspect(42)
    assert status["attempt"] == correlation
    assert status["safe_entry"] == "planning"
    assert status["recoverability"] == "new_planning_only"
    assert set(status["actions"]) == {"end", "replan"}
    assert status["reason"] == "fixture_failure"


def test_failure_journal_survives_a_new_controller(runtime) -> None:
    bus, recovery, scm = runtime
    fail(bus)
    bus.workflow_recovery = other = WorkflowRecovery(bus, scm)
    assert other.inspect(42)["status"] == "finished"
    assert bus.send(PlanIssueCommand(issue_number=42))["success"] is False


def test_explicit_end_revokes_bad_plan_and_releases_config_blocker(runtime) -> None:
    bus, recovery, scm = runtime
    old = scm.post_comment(42, PLAN)
    scm.fixture_issue.labels = [
        Label(1, "status:plan"),
        Label(2, "status:approved"),
        Label(3, "area:docs"),
    ]
    bus.configuration_session._update(lambda s: s["issues"].update({"42": "PlanPosted"}))
    status = recovery.inspect(42)
    recovery.action(42, "end", status["version"], "Plan is wrong", "operator:alice")
    assert latest_active_plan(scm.get_comments(42)) is None
    assert scm.get_comments(42)[0] == old
    assert {l.name for l in scm.fixture_issue.labels} == {"area:docs"}
    assert bus.configuration_session.state()["issues"] == {}
    assert bus.configuration_session.blockers(bus.configuration_session.state()) == []
    assert bus.send(PlanIssueCommand(issue_number=42))["success"] is False


@pytest.mark.parametrize(
    "profile", ["standard", "autonomous", "night", "patch", "watch", "self", "chat"]
)
def test_new_attempt_has_fresh_identity_and_preserves_failed_evidence(runtime, profile) -> None:
    import json

    from samuel.core.workflow import WorkflowEngine

    bus, recovery, scm = runtime
    old_correlation = fail(bus)
    before = deepcopy(recovery._records(42))
    captured = []

    def replacement(cmd: Any) -> None:
        captured.append(cmd)
        assert recovery.authorized_restart(42, cmd.correlation_id)
        assert recovery.requires_human(42, cmd.correlation_id)
        source = PlanningSourceSnapshot(
            schema_version=1,
            repository="fixture/repository",
            base_ref="main",
            base_sha="a" * 40,
            issue_digest=issue_revision_digest(
                number=42, title=scm.fixture_issue.title, body=scm.fixture_issue.body
            ),
        )
        plan = PLAN + "\n" + render_planning_source(source)
        comment = scm.post_comment(42, plan)
        bus.publish(
            Event(
                name="PlanPosted",
                correlation_id=cmd.correlation_id,
                payload={
                    "issue": 42,
                    "plan_comment_id": comment.id,
                    "acceptance_contract": parse_acceptance_contract(plan).as_dict(),
                },
            )
        )

    bus.register_command("ReplanIssue", replacement)
    status = recovery.inspect(42)
    result = recovery.action(42, "replan", status["version"], "Cause fixed", "operator:alice")
    assert result["attempt"] != old_correlation
    assert captured[0].correlation_id == result["attempt"]
    assert all(r in recovery._records(42) for r in before)
    consumer = Mock()
    bus.register_command("Implement", consumer)
    # Autonomous planning policy cannot approve a recovery plan.
    bus.send(
        ImplementCommand(
            issue_number=42,
            payload={"acceptance_approval": {"state": "approved", "method": "plan_validated"}},
        )
    )
    consumer.assert_not_called()
    active = latest_active_plan(scm.get_comments(42))
    assert active is not None
    plan, contract = active
    event = SCMLabelEvent(
        "fixture:approved", "status:approved", "alice", "human", "2026-11-05T10:01:00Z"
    )
    approval = AcceptanceApproval(
        state="approved",
        actor="alice",
        method="status:approved/polling",
        source_id=f"plan:{plan.id};fixture:approved",
        approved_at=event.timestamp,
        plan_comment_id=plan.id,
        contract_hash=contract.contract_hash,
    )
    scm.get_label_events.return_value = [event]
    scm.resolve_ref.return_value = "a" * 40
    persist_plan_approval(
        bus.authority_state_store,
        repository="fixture/repository",
        issue_number=42,
        contract=contract,
        approval=approval,
        transport="authenticated_scm_polling",
    )
    definition = json.loads(
        (Path(__file__).parents[1] / "config/workflows" / f"{profile}.json").read_text()
    )
    WorkflowEngine(bus, definition)
    bus.publish(
        Event(
            name="PlanApproved",
            payload={
                "issue": 42,
                "acceptance_approval": approval.as_dict(),
                "acceptance_contract": contract.as_dict(),
            },
        )
    )
    consumer.assert_called_once()
    assert consumer.call_args.args[0].payload["branch"].startswith("samuel/issue-42-attempt-")
    with pytest.raises(ConfigurationConflict):
        recovery.action(42, "replan", status["version"], "Double click", "operator:alice")


def test_stale_tab_and_active_work_do_not_revoke_plan(runtime) -> None:
    bus, recovery, scm = runtime
    scm.post_comment(42, PLAN)
    status = recovery.inspect(42)
    scm.fixture_issue.body = "Changed scope"
    with pytest.raises(ConfigurationConflict):
        recovery.action(42, "end", status["version"], "Bad plan", "alice")
    assert latest_active_plan(scm.get_comments(42))
    status = recovery.inspect(42)
    with bus.configuration_session.admission("watch"), pytest.raises(ConfigurationConflict):
        recovery.action(42, "end", status["version"], "Bad plan", "alice")
    assert latest_active_plan(scm.get_comments(42))


def test_unknown_external_effect_blocks_retirement_and_replanning(runtime) -> None:
    bus, recovery, scm = runtime
    correlation = fail(bus)
    bus.authority_state_store.put_intent(
        OperationIntentRecord(
            intent_key="uncertain-push",
            operation="push",
            status="pending",
            issue_number=42,
            correlation_id=correlation,
            subject_key="candidate",
            payload={},
        )
    )
    status = recovery.inspect(42)
    assert status["actions"] == []
    assert "external_effect_unresolved" in status["blockers"]
    with pytest.raises(ConfigurationConflict):
        recovery.action(42, "replan", status["version"], "Try again", "alice")
    scm.post_comment.assert_not_called()


def test_partial_label_failure_remains_fenced_and_is_recoverable(runtime) -> None:
    bus, recovery, scm = runtime
    fail(bus)
    scm.post_comment(42, PLAN)
    original = scm.swap_label.side_effect
    scm.swap_label.side_effect = OSError("offline")
    status = recovery.inspect(42)
    with pytest.raises(OSError):
        recovery.action(42, "end", status["version"], "Bad plan", "alice")
    assert latest_active_plan(scm.get_comments(42)) is None
    assert bus.send(PlanIssueCommand(issue_number=42))["success"] is False
    scm.swap_label.side_effect = original
    status = recovery.inspect(42)
    recovery.action(42, "end", status["version"], "Complete retirement", "alice")
    assert "42" not in bus.configuration_session.state()["issues"]


def test_stage_failure_that_heals_is_not_a_terminal_failure(runtime) -> None:
    bus, recovery, scm = runtime

    def handler(cmd: Any) -> None:
        for name in ("GateFailed", "HealingStarted", "PRCreated", "ReviewCompleted"):
            bus.publish(
                Event(
                    name=name,
                    payload={"issue": 42, "pr_number": 7},
                    correlation_id=cmd.correlation_id,
                )
            )

    bus.register_command("Implement", handler)
    bus.send(ImplementCommand(issue_number=42))
    assert not recovery._fenced(recovery._records(42))


def test_late_old_events_cannot_restore_configuration_blocker(runtime) -> None:
    bus, recovery, scm = runtime
    old = fail(bus)
    status = recovery.inspect(42)
    recovery.action(42, "end", status["version"], "Done", "alice")
    subscriber = Mock()
    bus.subscribe("PlanPosted", subscriber)
    bus.publish(Event(name="PlanPosted", payload={"issue": 42}, correlation_id=old))
    subscriber.assert_not_called()
    assert bus.configuration_session.state()["issues"] == {}


def test_crashed_dispatch_is_unknown_and_not_automatically_retried(runtime) -> None:
    bus, recovery, scm = runtime
    bus.register_command("PlanIssue", Mock(side_effect=RuntimeError("interruption")))
    with pytest.raises(RuntimeError):
        bus.send(PlanIssueCommand(issue_number=42))
    consumer = Mock()
    bus.register_command("PlanIssue", consumer)
    assert bus.send(PlanIssueCommand(issue_number=42))["success"] is False
    consumer.assert_not_called()
    assert recovery.inspect(42)["status"] == "interrupted"


def test_two_threads_cannot_start_the_same_issue(runtime) -> None:
    bus, recovery, scm = runtime
    entered, release = threading.Event(), threading.Event()

    def handler(cmd: Any) -> None:
        entered.set()
        assert release.wait(5)

    bus.register_command("PlanIssue", handler)
    thread = threading.Thread(target=lambda: bus.send(PlanIssueCommand(issue_number=42)))
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(ConfigurationConflict):
            bus.send(PlanIssueCommand(issue_number=42))
    finally:
        release.set()
        thread.join(5)


def test_existing_pr_requires_explicit_resolution(runtime) -> None:
    bus, recovery, scm = runtime
    fail(bus)
    bus.authority_state_store.put_intent(
        OperationIntentRecord(
            intent_key="created-pr",
            operation="create_pr",
            status="pending",
            issue_number=42,
            correlation_id="old",
            subject_key="candidate",
            payload={},
            postcondition={"pr_number": 7},
        )
    )
    bus.authority_state_store.finish_intent(
        "created-pr", status="applied", postcondition={"pr_number": 7}
    )
    scm.get_pr.return_value = PR(7, 7, "Existing", "http://example.invalid/pr/7")
    assert recovery.inspect(42)["actions"] == []
    scm.get_pr.return_value = PR(7, 7, "Closed", "http://example.invalid/pr/7", state="closed")
    assert "replan" in recovery.inspect(42)["actions"]


def test_real_planner_recovery_waits_for_human_even_in_autonomous_profile(runtime) -> None:
    from samuel.core.workflow import WorkflowEngine
    from samuel.slices.planning.handler import PlanningHandler
    from samuel.slices.planning.tests.test_handler import GOOD_PLAN, MockLLM

    bus, recovery, scm = runtime
    from samuel.slices.labels.handler import LabelsHandler

    LabelsHandler(bus, scm=scm).register()
    old = fail(bus)
    llm = MockLLM(GOOD_PLAN)
    planner = PlanningHandler(bus, scm=scm, llm=llm, plan_approval_required=False)
    bus.register_command("ReplanIssue", planner.handle)
    consumer = Mock()
    bus.register_command("Implement", consumer)
    WorkflowEngine(bus, {"steps": [{"on": "PlanValidated", "send": "Implement"}]})
    status = recovery.inspect(42)
    result = recovery.action(42, "replan", status["version"], "Repair the bad plan", "alice")
    assert result["attempt"] != old
    assert llm.call_count == 1
    # No native ownership proof: preserve the existing human-action label.
    assert {l.name for l in scm.fixture_issue.labels} == {"status:plan", "help wanted"}
    active = latest_active_plan(scm.get_comments(42))
    assert active is not None
    assert "wartet auf menschliche Freigabe" in active[0].body
    assert "Repair the bad plan" in llm.prompts[0]
    consumer.assert_not_called()
    assert recovery.plan_binding(42)["plan_comment_id"] == active[0].id
    # An invented approval payload is insufficient, including through the
    # recovery-only PlanApproved subscription in an autonomous profile.
    bus.publish(
        Event(
            name="PlanApproved",
            payload={
                "issue": 42,
                "acceptance_approval": {
                    "state": "approved",
                    "method": "status:approved",
                    "plan_comment_id": active[0].id,
                    "contract_hash": active[1].contract_hash,
                },
            },
        )
    )
    consumer.assert_not_called()


def test_manual_wait_is_not_offered_as_technical_resume(runtime) -> None:
    from samuel.core.state import WorkflowCheckpointRecord

    bus, recovery, scm = runtime
    scm.post_comment(42, PLAN)
    bus.authority_state_store.put_checkpoint(
        WorkflowCheckpointRecord(
            checkpoint_key="manual",
            issue_number=42,
            correlation_id="waiting",
            workflow="standard",
            boundary="manual_pending",
            repository="fixture/repository",
            branch="candidate",
            base_ref="main",
            head_sha="a" * 40,
            workspace_id="",
            evaluation_subject={},
            resume_eligible=True,
            payload={},
        )
    )
    status = recovery.inspect(42)
    assert "resume" not in status["actions"]
    assert "replan" in status["actions"]


def test_technical_checkpoint_can_reconcile_its_uncertain_effect(runtime) -> None:
    from samuel.core.state import WorkflowCheckpointRecord

    bus, recovery, scm = runtime
    bus.authority_state_store.put_checkpoint(
        WorkflowCheckpointRecord(
            checkpoint_key="push",
            issue_number=42,
            correlation_id="interrupted",
            workflow="standard",
            boundary="push_pending",
            repository="fixture/repository",
            branch="candidate",
            base_ref="main",
            head_sha="a" * 40,
            workspace_id="",
            evaluation_subject={},
            resume_eligible=True,
            payload={},
        )
    )
    bus.authority_state_store.put_intent(
        OperationIntentRecord(
            intent_key="push-uncertain",
            operation="push",
            status="pending",
            issue_number=42,
            correlation_id="interrupted",
            subject_key="candidate",
            payload={},
        )
    )
    status = recovery.inspect(42)
    assert status["actions"] == ["resume"]
    assert "external_effect_unresolved" in status["blockers"]


def test_http_recovery_requires_operator_csrf_fresh_session_and_current_version(
    runtime, tmp_path, monkeypatch
) -> None:
    import json
    import urllib.error
    import urllib.request
    from http.cookiejar import CookieJar

    from samuel.adapters.auth.local import LocalIdentityService
    from samuel.core.config import FileConfig
    from samuel.server import create_server

    bus, recovery, scm = runtime
    fail(bus)
    root = tmp_path / "config"
    root.mkdir()
    auth = json.loads((Path(__file__).parents[1] / "config/auth.json").read_text())
    auth["access_mode"] = "local_identity"
    (root / "auth.json").write_text(json.dumps(auth))
    config = FileConfig(root)
    config.set_override("agent.config_dir", str(root))
    identity = LocalIdentityService(
        bus.state_store.identity, instance_uuid=lambda: bus.state_store.status().authority_instance
    )
    identity.bootstrap("admin", "administrator-password")
    admin = identity.login("admin", "administrator-password", client_key="fixture").actor
    identity.create_user(admin, "operator", "operator-password-long", ("operator",))
    server = create_server(bus, host="127.0.0.1", port=0, config=config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(path: str, body=None, csrf=True):
        headers = {"Content-Type": "application/json"}
        if body is not None and csrf:
            headers["X-CSRF-Token"] = str(next(c.value for c in jar if c.name == "samuel_csrf"))
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    try:
        request(
            "/api/v1/auth/login", {"username": "admin", "password": "administrator-password"}, False
        )
        path = "/api/v1/issues/42/recovery"
        assert request(path, {"action": "end"})[0] == 403
        request(
            "/api/v1/auth/login",
            {"username": "operator", "password": "operator-password-long"},
            False,
        )
        code, status = request(path)
        assert code == 200
        body = {"action": "end", "reason": "Cause understood", "version": status["version"]}
        assert request(path, body, False)[0] == 403
        with monkeypatch.context() as patch:
            patch.setattr(LocalIdentityService, "is_fresh", lambda self, actor: False)
            assert request(path, body)[0] == 403
        assert request(path, {**body, "version": "stale"})[0] == 409
        code, result = request(path, body)
        assert code == 200 and result["updated"]
        assert request(path, body)[0] == 409
        assert bus.configuration_session.state()["issues"] == {}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_watch_with_stale_start_label_never_retries_terminal_attempt(runtime) -> None:
    from samuel.core.commands import ScanIssuesCommand
    from samuel.core.workflow import WorkflowEngine
    from samuel.slices.watch.handler import WatchHandler

    bus, recovery, scm = runtime
    fail(bus)
    scm.fixture_issue.labels = [Label(1, "ready-for-agent"), Label(2, "status:failed")]
    scm.list_issues.side_effect = lambda labels: (
        [scm.fixture_issue] if labels == ["ready-for-agent"] else []
    )
    scm.capabilities = set()
    consumer = Mock()
    bus.register_command("PlanIssue", consumer)
    WorkflowEngine(bus, {"steps": [{"on": "IssueReady", "send": "PlanIssue"}]})
    watch = WatchHandler(bus, scm=scm, authority_store=bus.authority_state_store)
    before = deepcopy(recovery._records(42))
    for _ in range(3):
        watch.handle(ScanIssuesCommand())
    consumer.assert_not_called()
    scm.post_comment.assert_not_called()
    assert recovery._records(42) == before


def test_foreign_checkpoint_cannot_be_abandoned_by_issue_number(runtime) -> None:
    from samuel.core.state import WorkflowCheckpointRecord

    bus, recovery, scm = runtime
    scm.post_comment(42, PLAN)
    bus.authority_state_store.put_checkpoint(
        WorkflowCheckpointRecord(
            checkpoint_key="foreign",
            issue_number=42,
            correlation_id="foreign",
            workflow="standard",
            boundary="manual_pending",
            repository="another/repository",
            branch="candidate",
            base_ref="main",
            head_sha="a" * 40,
            workspace_id="",
            evaluation_subject={},
            resume_eligible=True,
            payload={},
        )
    )
    status = recovery.inspect(42)
    assert not status["actions"]
    assert "foreign_checkpoint_binding" in status["blockers"]


def test_exception_failure_does_not_leak_provider_message_in_inspection(runtime) -> None:
    bus, recovery, scm = runtime

    def handler(cmd: Any) -> None:
        bus.publish(
            Event(
                name="PlanBlocked",
                correlation_id=cmd.correlation_id,
                payload={"issue": 42, "reason": "sk-abcdefghijklmnopqrstuvwxyz123456"},
            )
        )

    bus.register_command("PlanIssue", handler)
    bus.send(PlanIssueCommand(issue_number=42))
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in str(recovery.inspect(42))


def test_policy_drift_requires_new_plan_not_a_stage_override(runtime) -> None:
    bus, recovery, scm = runtime
    fail(bus, "EvaluationSubjectInvalidated")
    status = recovery.inspect(42)
    for action in ("retry", "implementation", "review", "force", "skip_gate"):
        with pytest.raises(ValueError, match="unsupported"):
            recovery.action(42, action, status["version"], "Changed policy", "alice")
    assert status["safe_entry"] == "planning"


def test_public_run_and_rest_do_not_report_a_fenced_attempt_as_started(runtime, capsys) -> None:
    import argparse

    from samuel.adapters.api.rest import RestAPI
    from samuel.cli import _cmd_run

    bus, recovery, scm = runtime
    fail(bus)
    consumer = Mock()
    bus.register_command("PlanIssue", consumer)
    assert _cmd_run(bus, argparse.Namespace(issue=42)) == 1
    assert "recovery inspect" in capsys.readouterr().err
    result = RestAPI(bus).handle_request("POST", "/api/v1/issues/42/plan")
    assert result["status"] == 409
    consumer.assert_not_called()


def test_subscriber_exception_cannot_turn_unknown_work_into_retry_permission(runtime) -> None:
    from samuel.core.workflow import WorkflowEngine

    bus, recovery, scm = runtime
    consumer = Mock(side_effect=RuntimeError("fixture"))
    bus.register_command("PlanIssue", consumer)
    WorkflowEngine(bus, {"steps": [{"on": "IssueReady", "send": "PlanIssue"}]})
    bus.publish(Event(name="IssueReady", payload={"issue": 42}))
    assert recovery.inspect(42)["status"] == "finished"
    bus.publish(Event(name="IssueReady", payload={"issue": 42}))
    assert consumer.call_count == 1


def test_interrupted_retirement_without_prior_journal_can_be_completed(runtime) -> None:
    bus, recovery, scm = runtime
    scm.post_comment(42, PLAN)
    status = recovery.inspect(42)
    original = scm.swap_label.side_effect
    scm.swap_label.side_effect = OSError("interrupted")
    with pytest.raises(OSError):
        recovery.action(42, "end", status["version"], "Bad plan", "alice")
    assert latest_active_plan(scm.get_comments(42)) is None
    scm.swap_label.side_effect = original
    after = recovery.inspect(42)
    assert "end" in after["actions"]
    recovery.action(42, "end", after["version"], "Complete end", "alice")
    assert not recovery._fenced(recovery._records(42))


@pytest.mark.parametrize("terminal", [False, True])
def test_provider_resume_reconciles_interruption_but_never_retries_terminal(runtime, terminal):
    from types import SimpleNamespace

    from samuel.core.commands import ResumePendingCommand
    from samuel.core.state import WorkflowCheckpointRecord
    from samuel.slices.resume.handler import ResumeCoordinator

    bus, recovery, scm = runtime
    correlation = fail(bus) if terminal else "interrupted-provider"
    if not terminal:
        recovery._write("execution", 42, "crashed", correlation=correlation, stage="CreatePR")
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key="provider-bound",
        issue_number=42,
        correlation_id=correlation,
        workflow="provider_verification",
        boundary="provider_running",
        repository=scm.repository_identity,
        branch="b" * 40,
        base_ref="a" * 40,
        head_sha="b" * 40,
        workspace_id="",
        evaluation_subject={},
        resume_eligible=True,
        payload={
            "request_key": "bound-request",
            "consumer_context": {"branch": "candidate", "base": "main"},
        },
    )
    bus.authority_state_store.put_checkpoint(checkpoint)
    provider = Mock()
    provider.advance.return_value = SimpleNamespace(
        status="evidence_ready",
        reason_code="provider_evidence_ready",
        request=SimpleNamespace(consumer_mode="reference_worker", subject=None),
    )
    workspaces = Mock()
    workspaces.list_workspaces.return_value = []
    config = Mock()
    config.get.side_effect = lambda key, default=None: (
        True if key == "agent.resume.enabled" else default
    )
    consumer = Mock(return_value={"passed": True, "pr_created": True})
    bus.register_command("CreatePR", consumer)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=bus.authority_state_store,
        workspace_manager=workspaces,
        config=config,
        owner_id="new-process",
        provider_verification=provider,
    )
    status = recovery.inspect(42)
    assert status["safe_entry"] == ("planning" if terminal else "technical_finalization")
    if not terminal:
        assert status["reason"] == "dispatch_interrupted"
        assert status["stage"] == "delivery"
    outcome = coordinator.handle(ResumePendingCommand())
    if terminal:
        assert outcome["blocked"] == 1
        provider.advance.assert_not_called()
        consumer.assert_not_called()
    else:
        assert outcome["resumed"] == 1
        consumer.assert_called_once()
        assert not recovery._fenced(recovery._records(42))


def test_recovery_clarification_continues_only_its_existing_series(runtime):
    from datetime import datetime, timezone

    from samuel.core.state import PlanningClarificationRecord, WorkflowBudgetAdmissionRecord

    bus, recovery, scm = runtime
    fail(bus)

    def start(cmd):
        bus.authority_state_store.put_budget_admission(
            WorkflowBudgetAdmissionRecord(
                admission_key="admission",
                repository=scm.repository_identity,
                issue_number=42,
                invocation_digest="sha256:" + "b" * 64,
                source_digest="sha256:" + "a" * 64,
                policy_digest="sha256:" + "c" * 64,
                correlation_id=cmd.correlation_id,
                token_limit=1000,
            )
        )
        bus.authority_state_store.put_planning_clarification(
            PlanningClarificationRecord(
                series_key="new-series",
                repository=scm.repository_identity,
                issue_number=42,
                source_digest="sha256:" + "a" * 64,
                admission_key="admission",
                correlation_id=cmd.correlation_id,
                status="waiting",
                round_number=1,
                deadline_at=datetime.now(timezone.utc),
                rounds=({},),
            )
        )

    bus.register_command("ReplanIssue", start)
    status = recovery.inspect(42)
    result = recovery.action(42, "replan", status["version"], "Clarify the new plan", "alice")
    consumer = Mock()
    bus.register_command("PlanIssue", consumer)
    bus.send(PlanIssueCommand(issue_number=42, clarification_continuation_authorized=True))
    cmd = consumer.call_args.args[0]
    assert cmd.correlation_id == result["attempt"]
    assert cmd.clarification_continuation_authorized is False
    assert recovery.requires_human(42, cmd.correlation_id)
    status = recovery.inspect(42)
    recovery.action(42, "end", status["version"], "Stop waiting", "alice")
    consumer.reset_mock()
    bus.send(PlanIssueCommand(issue_number=42))
    consumer.assert_not_called()


def test_legacy_failure_requires_explicit_new_planning_without_reusing_authority(runtime):
    bus, recovery, scm = runtime
    scm.fixture_issue.labels = [Label(1, "status:failed"), Label(2, "ready-for-agent")]
    consumer = Mock()
    bus.register_command("PlanIssue", consumer)
    assert (
        bus.send(PlanIssueCommand(issue_number=42))["reason"]
        == "legacy_failure_requires_new_planning"
    )
    consumer.assert_not_called()
    status = recovery.inspect(42)
    assert status["attempt"] is None
    assert status["actions"] == ["replan"]
    replacement = Mock()
    bus.register_command("ReplanIssue", replacement)
    result = recovery.action(42, "replan", status["version"], "Legacy failure reviewed", "alice")
    replacement.assert_called_once()
    assert recovery.requires_human(42, result["attempt"])


@pytest.fixture
def projected_runtime(runtime):
    from samuel.slices.labels.handler import LabelsHandler

    bus, recovery, scm = runtime
    LabelsHandler(bus, scm=scm).register()
    scm.list_issues.side_effect = lambda labels: (
        [deepcopy(scm.fixture_issue)]
        if set(labels) <= {label.name for label in scm.fixture_issue.labels}
        else []
    )
    scm.list_scm_activity.return_value = []
    return bus, recovery, scm


def _labels(scm) -> set[str]:
    return {label.name for label in scm.fixture_issue.labels}


def _seed_labels(scm, *labels: str) -> None:
    scm.fixture_issue.labels[:] = [Label(i + 1, name) for i, name in enumerate(labels)]


def _run_events(bus, rows, *, command="PlanIssue", correlation="fixture-attempt"):
    from samuel.core.commands import Command

    def run(cmd):
        for name, payload in rows:
            bus.publish(
                Event(name=name, correlation_id=correlation, payload={"issue": 42, **payload})
            )

    bus.register_command(command, run)
    return bus.send(Command(name=command, payload={"issue": 42}, correlation_id=correlation))


def _delivery_fixture(bus, scm, correlation="fixture-attempt"):
    from samuel.core.evaluation_subject import EvaluationSubject, PullRequestRevision

    scm.post_comment(42, PLAN)
    active = latest_active_plan(scm.get_comments(42))
    assert active is not None
    subject = EvaluationSubject(
        "fixture/repository",
        "a" * 40,
        "b" * 40,
        active[1].contract_hash,
        "v1",
        "sha256:" + "c" * 64,
    )
    payload = {
        "repository": subject.repository,
        "evaluation_subject": subject.as_dict(),
        "head_sha": subject.head_sha,
        "base_sha": subject.base_sha,
    }
    post = {"pr_number": 7, "head_sha": subject.head_sha, "base_sha": subject.base_sha}
    bus.authority_state_store.put_intent(
        OperationIntentRecord(
            intent_key="created",
            operation="create_pr",
            status="pending",
            issue_number=42,
            correlation_id=correlation,
            subject_key=subject.head_sha,
            payload=payload,
        )
    )
    bus.authority_state_store.finish_intent("created", status="applied", postcondition=post)
    scm.get_pr.return_value = PR(7, 7, "Candidate", "http://example.invalid/pr/7")
    scm.get_pr_revision.return_value = PullRequestRevision(
        subject.repository, subject.base_sha, subject.head_sha
    )
    return {"evaluation_subject": subject.as_dict(), "pr_number": 7}


@pytest.mark.parametrize(
    "event",
    ["PlanBlocked", "WorkflowBlocked", "WorkflowAborted", "LLMUnavailable", "PRCreationFailed"],
)
def test_bound_terminal_labels_preserve_unrelated_labels_and_comment_once(projected_runtime, event):
    bus, recovery, scm = projected_runtime
    _seed_labels(
        scm,
        "ready-for-agent",
        "needs-review",
        "in-progress",
        "status:wip",
        "status:approved",
        "status:done",
        "risk:low",
        "owner:alice",
        "help wanted",
    )
    correlation = fail(bus, event)
    assert _labels(scm) == {"status:failed", "help wanted", "risk:low", "owner:alice"}
    comments = scm.get_comments(42)
    assert len(comments) == 1
    assert "Workflow-Versuch beendet" in comments[0].body
    assert correlation in comments[0].body
    assert "Kein automatischer Wiederanlauf" in comments[0].body
    writes = scm.swap_label.call_count
    bus.publish(Event(name=event, correlation_id=correlation, payload={"issue": 42}))
    bus.workflow_recovery = WorkflowRecovery(bus, scm)
    assert bus.send(PlanIssueCommand(issue_number=42))["success"] is False
    assert len(scm.get_comments(42)) == 1
    assert scm.swap_label.call_count == writes


@pytest.mark.parametrize("fails", ["all", "remove", "add", "silent"])
def test_failed_label_writes_cannot_restart_from_watch(projected_runtime, fails):
    from samuel.core.commands import ScanIssuesCommand
    from samuel.slices.watch.handler import WatchHandler

    bus, recovery, scm = projected_runtime
    _seed_labels(scm, "ready-for-agent", "status:approved", "status:plan", "risk:low")
    swap = scm.swap_label.side_effect

    def unreliable(number, remove, add):
        if fails == "silent":
            return
        if fails == "all" or (fails == "remove" and remove) or (fails == "add" and add):
            raise RuntimeError("token='do-not-log-this-secret'")
        swap(number, remove, add)

    scm.swap_label.side_effect = unreliable
    fail(bus)
    handler = Mock()
    bus.subscribe("IssueReady", handler)
    watch = WatchHandler(bus, scm=scm)
    writes, comments = scm.swap_label.call_count, scm.post_comment.call_count
    for _ in range(3):
        result = watch.handle(ScanIssuesCommand())
        assert result["dispatched"] == 0
        assert result["label_fixes"] == 0
    handler.assert_not_called()
    assert scm.swap_label.call_count == writes
    assert scm.post_comment.call_count == comments
    observations = [
        r
        for r in recovery.store.list_authority_records()
        if r.kind == "workflow_label_projection.observation"
    ]
    assert len(observations) == 1 and observations[0].payload["status"] == "unconfirmed"


@pytest.mark.parametrize(
    "labels",
    [
        ("ready-for-agent", "status:failed", "status:approved"),
        ("ready-for-agent", "status:wip"),
        ("ready-for-agent", "needs-review"),
    ],
)
def test_watch_never_repairs_status_conflict_into_an_admission(projected_runtime, labels):
    from samuel.core.commands import ScanIssuesCommand
    from samuel.slices.watch.handler import WatchHandler

    bus, _, scm = projected_runtime
    _seed_labels(scm, *labels, "risk:low")
    handler = Mock()
    bus.subscribe("IssueReady", handler)
    result = WatchHandler(bus, scm=scm).handle(ScanIssuesCommand())
    assert result["dispatched"] == 0
    assert result["admission_blocked"]
    handler.assert_not_called()
    scm.swap_label.assert_not_called()


@pytest.mark.parametrize(
    "events",
    [
        [("GateFailed", {})],
        [("GateFailed", {}), ("GateEvaluationCompleted", {"manual_pending": True})],
        [("PlanReplanRejected", {})],
    ],
)
def test_stage_failure_and_normal_waiting_are_not_terminal(projected_runtime, events):
    bus, _, scm = projected_runtime
    _seed_labels(scm, "status:approved", "risk:low")
    _run_events(bus, events)
    assert "status:failed" not in _labels(scm)
    assert "help wanted" not in _labels(scm)
    assert "status:approved" in _labels(scm)
    scm.post_comment.assert_not_called()


@pytest.mark.parametrize(
    "foreign", ["repository", "issue", "correlation", "subject", "contract", "passive"]
)
def test_unbound_events_cannot_mutate_labels(projected_runtime, foreign):
    bus, _, scm = projected_runtime
    _seed_labels(scm, "ready-for-agent", "risk:low")
    p: dict[str, Any] = {"issue": 42}
    if foreign == "repository":
        p["repository"] = "elsewhere/repository"
    if foreign == "issue":
        p["issue"] = 999
    if foreign in {"subject", "contract"}:
        subject = _delivery_fixture(bus, scm)["evaluation_subject"]
        subject["repository" if foreign == "subject" else "contract_hash"] = (
            "other/repo" if foreign == "subject" else "sha256:" + "e" * 64
        )
        p["evaluation_subject"] = subject
    if foreign == "passive":
        p["mutation_authority"] = "none"

    def run(cmd):
        bus.publish(
            Event(
                name="WorkflowBlocked",
                correlation_id="foreign" if foreign == "correlation" else cmd.correlation_id,
                payload=p,
            )
        )

    bus.register_command("PlanIssue", run)
    before = scm.post_comment.call_count
    bus.send(PlanIssueCommand(issue_number=42))
    scm.swap_label.assert_not_called()
    assert scm.post_comment.call_count == before


@pytest.mark.parametrize("sequence", ["normal", "reordered", "nested"])
def test_bound_healing_pr_supersedes_stage_failures_in_any_delivery_order(
    projected_runtime, sequence
):
    bus, _, scm = projected_runtime
    delivery = _delivery_fixture(bus, scm)
    _seed_labels(scm, "status:plan", "status:approved", "risk:low")
    rows = [
        ("GateFailed", {}),
        ("HealingAttemptStarted", {"observation_key": "origin"}),
        ("PRCreated", {**delivery, "healing_origin_observation_key": "origin"}),
    ]
    if sequence == "reordered":
        rows = [rows[1], rows[2], rows[0]]
    if sequence == "nested":

        def nested(event):
            bus.publish(
                Event(
                    name="PRCreated",
                    correlation_id=event.correlation_id,
                    payload={"issue": 42, **delivery, "healing_origin_observation_key": "origin"},
                )
            )

        bus.subscribe("GateFailed", nested)
        rows = [rows[1], rows[0]]
    _run_events(bus, rows, command="Implement")
    assert _labels(scm) == {"status:wip", "needs-review", "risk:low"}
    before = scm.swap_label.call_count
    bus.publish(
        Event(name="WorkflowBlocked", payload={"issue": 42}, correlation_id="fixture-attempt")
    )
    assert scm.swap_label.call_count == before
    assert not any("Workflow-Versuch beendet" in c.body for c in scm.get_comments(42))


@pytest.mark.parametrize("fault", ["head", "base", "intent", "healing", "plan", "missing_subject"])
def test_success_with_stale_or_missing_delivery_binding_does_not_clear_failure(
    projected_runtime, fault
):
    from samuel.core.evaluation_subject import PullRequestRevision

    bus, recovery, scm = projected_runtime
    delivery = _delivery_fixture(bus, scm)
    # Existing execution history means this is not a legacy-label-only entry.
    _run_events(bus, [], correlation="earlier")
    _seed_labels(scm, "status:failed", "risk:low")
    subject = delivery["evaluation_subject"]
    if fault == "head":
        scm.get_pr_revision.return_value = PullRequestRevision(
            subject["repository"], subject["base_sha"], "d" * 40
        )
    if fault == "base":
        scm.get_pr_revision.return_value = PullRequestRevision(
            subject["repository"], "d" * 40, subject["head_sha"]
        )
    if fault == "intent":
        delivery["pr_number"] = 8
    if fault == "missing_subject":
        delivery.pop("evaluation_subject")
    rows = [
        ("HealingAttemptStarted", {"observation_key": "origin"}),
        (
            "PRCreated",
            {
                **delivery,
                "healing_origin_observation_key": "wrong" if fault == "healing" else "origin",
            },
        ),
    ]
    if fault == "plan":
        scm.fixture_comments[0].body = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] other.py"
    _run_events(bus, rows, command="Implement")
    assert _labels(scm) == {"status:failed", "risk:low"}
    scm.swap_label.assert_not_called()


def test_native_merge_requires_current_pr_and_preserves_human_help(projected_runtime):
    from samuel.core.evaluation_subject import PullRequestRevision

    bus, _, scm = projected_runtime
    delivery = _delivery_fixture(bus, scm)
    _seed_labels(scm, "status:wip", "needs-review", "help wanted", "owner:alice")
    scm.get_pr.return_value = PR(
        7, 7, "Candidate", "http://example.invalid/pr/7", state="closed", merged=True
    )
    subject = delivery["evaluation_subject"]
    scm.get_pr_revision.return_value = PullRequestRevision(
        subject["repository"], "e" * 40, subject["head_sha"]
    )
    event = Event(
        name="PRMerged", correlation_id="fixture-attempt", payload={"issue": 42, **delivery}
    )
    bus.publish(event)
    assert _labels(scm) == {"status:done", "help wanted", "owner:alice"}
    writes = scm.swap_label.call_count
    bus.publish(event)
    assert scm.swap_label.call_count == writes


def test_terminal_comment_timeout_after_write_is_never_duplicated(projected_runtime, caplog):
    from samuel.slices.labels.projection import BoundLabelProjection

    bus, recovery, scm = projected_runtime
    post = scm.post_comment.side_effect

    def uncertain(number, body):
        post(number, body)
        raise RuntimeError("token='do-not-log-this-secret'")

    scm.post_comment.side_effect = uncertain
    _run_events(bus, [("WorkflowBlocked", {"reason_code": "token='do-not-log-this-secret'"})])
    end = next(
        r for r in recovery.store.list_authority_records() if r.kind == "workflow_recovery.end"
    )
    BoundLabelProjection(recovery, scm).finish(end, [])
    assert len(scm.get_comments(42)) == 1
    assert "do-not-log-this-secret" not in scm.get_comments(42)[0].body
    assert "do-not-log-this-secret" not in caplog.text
    assert _labels(scm) == {"status:failed", "help wanted"}


def test_terminal_comment_reuses_gate_remedy_without_claiming_causality(projected_runtime):
    bus, recovery, scm = projected_runtime
    _run_events(
        bus,
        [
            ("GateFailed", {"gate": "diff_secret_scan", "reason": "token='never-copy-this'"}),
            ("WorkflowBlocked", {"reason": "bound_healing:gate_11_not_failed"}),
        ],
    )
    comments = scm.get_comments(42)
    assert len(comments) == 1
    body = comments[0].body
    assert "Healing für diesen Befund nicht zulässig" in body
    assert "Secret-Referenz" in body
    assert "Korrelation belegt keine Kausalität" in body
    assert "never-copy-this" not in body
    assert "menschliche Planfreigabe" in body
    assert recovery.automatic_entry_reason(42, "planning") == "attempt_finished_or_unresolved"


@pytest.mark.parametrize(
    "reason", ["healing_budget_exhausted", "healing_refailed", "healing_not_allowed"]
)
def test_healing_terminal_failure_has_no_new_automatic_attempt(projected_runtime, reason):
    bus, recovery, scm = projected_runtime
    _run_events(
        bus,
        [
            ("HealingAttemptStarted", {"observation_key": "origin"}),
            ("GateFailed", {}),
            ("WorkflowBlocked", {"reason_code": reason}),
        ],
    )
    assert _labels(scm) == {"status:failed", "help wanted"}
    assert reason in scm.get_comments(42)[0].body
    assert recovery.automatic_entry_reason(42, "planning") == "attempt_finished_or_unresolved"


def test_duplicate_native_plan_approval_never_reenters_implementation(projected_runtime):
    bus, _, scm = projected_runtime
    scm.post_comment(42, PLAN)
    _seed_labels(scm, "status:plan", "status:approved")
    handler = Mock()
    bus.subscribe("PlanApproved", handler)
    bus.publish(Event(name="PlanApproved", payload={"issue": 42}, correlation_id="first"))
    assert _labels(scm) == {"status:wip", "status:approved"}
    bus.publish(
        Event(name="PlanApproved", payload={"issue": 42}, correlation_id="duplicate-delivery")
    )
    assert handler.call_count == 1


def test_new_public_review_can_project_the_existing_bound_candidate(projected_runtime):
    bus, _, scm = projected_runtime
    delivery = _delivery_fixture(bus, scm, correlation="original-implementation")
    _seed_labels(scm, "status:wip", "needs-review")
    _run_events(bus, [("ReviewCompleted", delivery)], command="Review", correlation="new-review")
    assert _labels(scm) == {"status:wip"}


def test_a_newer_success_prevents_replaying_an_older_unprojected_failure(projected_runtime):
    from samuel.slices.labels.projection import BoundLabelProjection

    bus, recovery, scm = projected_runtime
    _run_events(bus, [("WorkflowBlocked", {"repository": "wrong/repository"})])
    old = next(
        r for r in recovery.store.list_authority_records() if r.kind == "workflow_recovery.end"
    )
    status = recovery.inspect(42)
    recovery.action(42, "end", status["version"], "Retire the failure", "alice")
    _seed_labels(scm, "status:done")
    scm.swap_label.reset_mock()
    BoundLabelProjection(recovery, scm).finish(old, [])
    scm.swap_label.assert_not_called()


@pytest.mark.parametrize("origins", [[None], ["first", "second"]])
def test_missing_or_ambiguous_healing_origin_has_no_label_effect(projected_runtime, origins):
    bus, _, scm = projected_runtime
    delivery = _delivery_fixture(bus, scm)
    _seed_labels(scm, "in-progress", "status:approved")
    rows = [("HealingAttemptStarted", {"observation_key": origin}) for origin in origins]
    rows.append(("PRCreated", {**delivery, "healing_origin_observation_key": origins[0]}))
    _run_events(bus, rows, command="Implement")
    scm.swap_label.assert_not_called()


@pytest.mark.parametrize("labels_first", [True, False])
def test_public_run_failure_then_watch_never_retries_even_with_stale_labels(
    runtime, labels_first, capsys
):
    import argparse

    from samuel.cli import _cmd_run
    from samuel.core.commands import ScanIssuesCommand
    from samuel.core.workflow import WorkflowEngine
    from samuel.slices.labels.handler import LabelsHandler
    from samuel.slices.planning.handler import PlanningHandler
    from samuel.slices.planning.tests.test_handler import MockLLM
    from samuel.slices.watch.handler import WatchHandler

    bus, recovery, scm = runtime
    _seed_labels(scm, "ready-for-agent", "risk:low")
    scm.list_issues.side_effect = lambda labels: (
        [deepcopy(scm.fixture_issue)] if "ready-for-agent" in labels else []
    )
    scm.list_scm_activity.return_value = []
    scm.swap_label.side_effect = OSError("fixture_label_write_failure")
    labels = LabelsHandler(bus, scm=scm)
    if labels_first:
        labels.register()
    llm = MockLLM("Invalid plan without an acceptance contract")
    planner = PlanningHandler(bus, scm=scm, llm=llm)
    bus.register_command("PlanIssue", planner.handle)
    WorkflowEngine(bus, {"steps": [{"on": "IssueReady", "send": "PlanIssue"}]})
    if not labels_first:
        labels.register()
    assert _cmd_run(bus, argparse.Namespace(issue=42)) == 1
    calls, comments = llm.call_count, scm.post_comment.call_count
    assert calls > 0
    assert recovery.inspect(42)["status"] == "finished"
    watch = WatchHandler(bus, scm=scm)
    for _ in range(3):
        assert watch.handle(ScanIssuesCommand())["dispatched"] == 0
    assert llm.call_count == calls
    assert scm.post_comment.call_count == comments
    terminal = [c for c in scm.get_comments(42) if "workflow-terminal:" in c.body]
    assert len(terminal) == 1
    assert "Planprüfung" in terminal[0].body
    assert "Nicht autoritativer Planentwurf" in terminal[0].body
    assert len(scm.get_comments(42)) == 1
    assert "ready-for-agent" in _labels(scm)


@pytest.mark.parametrize("changed_identity", [False, True])
def test_duplicate_plan_publication_requires_one_identical_current_binding(
    projected_runtime, changed_identity
):
    bus, _, scm = projected_runtime
    _seed_labels(scm, "ready-for-agent", "risk:low")

    def plan(cmd):
        comment = scm.post_comment(42, PLAN)
        active = latest_active_plan(scm.get_comments(42))
        assert active is not None
        payload = {
            "issue": 42,
            "plan_comment_id": comment.id,
            "acceptance_contract": active[1].as_dict(),
        }
        bus.publish(Event(name="PlanPosted", correlation_id=cmd.correlation_id, payload=payload))
        bus.publish(
            Event(
                name="PlanPosted",
                correlation_id=cmd.correlation_id,
                payload={**payload, "plan_comment_id": comment.id + int(changed_identity)},
            )
        )

    bus.register_command("PlanIssue", plan)
    bus.send(PlanIssueCommand(issue_number=42))
    assert _labels(scm) == (
        {"ready-for-agent", "risk:low"} if changed_identity else {"status:plan", "risk:low"}
    )
    if changed_identity:
        scm.swap_label.assert_not_called()
