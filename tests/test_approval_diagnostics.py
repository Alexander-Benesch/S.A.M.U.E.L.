"""Signed native deliveries and passive UI readback at the approval boundary (#948)."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.acceptance import (
    PlanRevocation,
    latest_active_plan,
    render_plan_revocation,
    text_digest,
)
from samuel.core.approval_diagnostics import SERIES, snapshot
from samuel.core.bus import Bus
from samuel.core.events import Event, PlanPosted
from samuel.core.state import WorkflowBudgetAdmissionRecord
from samuel.core.types import Comment, Issue, Label, SCMLabelEvent
from samuel.core.workflow import WorkflowEngine
from samuel.server import create_server
from samuel.slices.dashboard.handler import DashboardHandler
from samuel.slices.labels.handler import LabelsHandler
from samuel.slices.run_projection.handler import RunProjectionHandler

SECRET = "synthetic-issue948-hmac"
DELIVERY = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class SCM:
    repository_identity = "owner/repo"

    def __init__(self) -> None:
        self.comments = [
            Comment(71, "## Plan\n- [ ] [DIFF] candidate.ts", "samuel", "2026-10-19T10:00:00Z")
        ]
        self.issue = Issue(16, "Example", "Bound subject", "open", [Label(9, "status:approved")])
        self.timeline = [
            SCMLabelEvent(
                "gitea-timeline:81", "status:approved", "alice", "human", "2026-10-19T10:01:00Z"
            )
        ]
        self.swaps: list[tuple[str, str]] = []
        self.feedback: list[Comment] = []

    def get_comments(self, number: int) -> list[Comment]:
        assert number == 16
        return list(self.comments)

    def get_issue(self, number: int) -> Issue:
        assert number == 16
        return self.issue

    def post_comment(self, number: int, body: str) -> Comment:
        assert number == 16
        comment = Comment(100 + len(self.feedback), body, "samuel", "2026-10-19T10:05:00Z")
        self.comments.append(comment)
        self.feedback.append(comment)
        return comment

    def get_label_events(self, number: int, label: str) -> list[SCMLabelEvent]:
        assert number == 16
        return [event for event in self.timeline if not label or event.label == label]

    def swap_label(self, number: int, remove: str, add: str) -> None:
        assert number == 16
        self.swaps.append((remove, add))
        self.issue.labels = [label for label in self.issue.labels if label.name != remove]
        if add and add not in {label.name for label in self.issue.labels}:
            self.issue.labels.append(Label(10, add))


@pytest.fixture
def subject(tmp_path: Path):
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(f"36 25 0:32 / {tmp_path} rw,relatime - ext4 device rw\n")
    state = SQLiteStateStore(tmp_path / "state", mountinfo_path=mountinfo)
    bus = Bus()
    scm = SCM()
    bus.scm = scm
    bus.authority_state_store = state.authority
    bus.run_projection_store = state.projections
    active = latest_active_plan(scm.comments)
    assert active is not None
    admission = WorkflowBudgetAdmissionRecord(
        admission_key="approval948-budget",
        repository=scm.repository_identity,
        issue_number=16,
        invocation_digest="sha256:" + "1" * 64,
        source_digest="sha256:" + "2" * 64,
        policy_digest="sha256:" + "3" * 64,
        correlation_id="approval948-plan",
        token_limit=1000,
    )
    state.authority.put_budget_admission(admission)
    state.authority.bind_budget_plan(
        admission.admission_key,
        plan_contract_hash=active[1].contract_hash,
        plan_comment_id=active[0].id,
    )
    return bus, scm, state


def deliver(bus: Bus, *, plan_label: bool = True, **changes: Any) -> dict[str, Any]:
    payload = {
        "action": "label_updated",
        "number": 16,
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "alice"},
        "issue": {
            "number": 16,
            "updated_at": changes.pop("timestamp", "2026-10-19T10:01:00Z"),
            "labels": [{"name": "status:approved"}]
            + ([{"name": "status:plan"}] if plan_label else []),
        },
    }
    payload.update(changes)
    raw = json.dumps(payload).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return WebhookIngressAdapter(bus, secret=SECRET, bot_user="samuel").handle_webhook(
        "issues",
        payload,
        signature,
        raw_body=raw,
        provider="gitea",
        event_subtype="issue_label",
        delivery_id=DELIVERY,
    )


def readback(bus: Bus) -> dict[str, Any]:
    return snapshot(
        scm=bus.scm,
        authority=bus.authority_state_store,
        projections=bus.run_projection_store,
        issue=16,
    )


@pytest.mark.parametrize("labels_first", [False, True])
def test_native_delivery_before_or_after_label_projection(subject, labels_first):
    bus, scm, state = subject
    events: list[Event] = []
    implementations: list[Any] = []
    bus.subscribe("*", events.append)
    bus.register_command("Implement", implementations.append)
    WorkflowEngine(bus, {"steps": [{"on": "PlanApproved", "send": "Implement"}]})
    LabelsHandler(bus, scm=scm).register()
    if labels_first:
        bus.publish(PlanPosted(payload={"issue": 16}))
    result = deliver(bus, plan_label=labels_first)
    if labels_first:
        assert result["action"] == "plan_approved"
    else:
        assert result["approval_diagnostic"]["reason_code"] == "plan_labels_incomplete"
        assert result["approval_diagnostic"]["diagnostic_persisted"] is True
        view = readback(bus)
        assert view["status"] == "not_materialized"
        assert view["last_delivery"]["reason_code"] == "plan_labels_incomplete"
        assert "erneut setzen" in view["next_action"]
        assert state.authority.list_authority_records() == []
        assert scm.swaps == []  # A diagnostic cannot clean up the approval label.
        bus.publish(PlanPosted(payload={"issue": 16}))
        # A bot projecting status:plan cannot replay the old human decision.
        projection = deliver(bus, timestamp="2026-10-19T10:02:00Z", sender={"login": "samuel"})
        assert projection["action"] == "ignored"
        assert deliver(bus, plan_label=False)["action"] == "ignored"
        assert not implementations
        scm.timeline.extend(
            [
                SCMLabelEvent(
                    "gitea-timeline:82",
                    "status:approved",
                    "alice",
                    "human",
                    "2026-10-19T10:03:00Z",
                    operation="remove",
                ),
                SCMLabelEvent(
                    "gitea-timeline:83", "status:approved", "alice", "human", "2026-10-19T10:04:00Z"
                ),
            ]
        )
        assert deliver(bus, timestamp="2026-10-19T10:04:00Z")["action"] == "plan_approved"
    assert readback(bus)["status"] == "accepted"
    assert len(implementations) == 1
    assert "status:approved" in {label.name for label in scm.issue.labels}
    deliver(bus, timestamp="2026-10-19T10:04:00Z" if not labels_first else "2026-10-19T10:01:00Z")
    assert len(implementations) == 1
    # Even a late ignored delivery cannot downgrade valid durable authority.
    deliver(bus, plan_label=False)
    assert readback(bus)["status"] == "accepted"
    assert "last_delivery" not in readback(bus)
    assert sum(event.name == "PlanApproved" for event in events) == 1


@pytest.mark.parametrize("failure", ["ambiguous", "old", "removal", "bot", "foreign"])
def test_current_native_countercases_explain_without_granting_authority(subject, failure):
    bus, scm, state = subject
    kwargs: dict[str, Any] = {}
    if failure == "ambiguous":
        scm.timeline.append(replace(scm.timeline[0], source_id="gitea-timeline:82"))
    elif failure == "old":
        scm.comments[0] = replace(scm.comments[0], created_at="2026-10-19T10:02:00Z")
    elif failure == "removal":
        scm.timeline[0] = replace(scm.timeline[0], operation="remove")
    elif failure == "bot":
        kwargs["sender"] = {"login": "samuel"}
    else:
        kwargs["repository"] = {"full_name": "other/repo"}
    result = deliver(bus, **kwargs)
    assert result["action"] == "ignored"
    assert state.authority.list_authority_records() == []
    assert readback(bus)["status"] == "not_materialized"
    if failure == "foreign":
        assert "approval_diagnostic" not in result
        assert state.projections.list_projections(series=SERIES) == []
    else:
        assert result["approval_diagnostic"]["message"]
        assert result["approval_diagnostic"]["next_action"]


@pytest.mark.parametrize("change", ["replacement", "revocation", "edited", "source_lost"])
def test_passive_readback_does_not_transfer_or_resurrect_approval(subject, change):
    bus, scm, state = subject
    assert deliver(bus)["action"] == "plan_approved"
    original = list(state.authority.list_authority_records())
    if change == "replacement":
        scm.comments.append(replace(scm.comments[0], id=72, created_at="2026-10-19T10:03:00Z"))
    elif change == "revocation":
        active = latest_active_plan(scm.comments)
        assert active is not None
        revocation = PlanRevocation(
            1,
            71,
            active[1].contract_hash,
            text_digest("human withdrawal"),
            "2026-10-19T10:03:00Z",
            "operator:local-cli",
        )
        scm.comments.append(
            Comment(72, render_plan_revocation(revocation), "samuel", revocation.revoked_at)
        )
    elif change == "edited":
        scm.comments[0] = replace(scm.comments[0], updated_at="2026-10-19T10:03:00Z")
    else:
        scm.timeline = []
    view = readback(bus)
    assert view["status"] != "accepted"
    assert "erneut setzen" not in view["next_action"] or change == "replacement"
    assert state.authority.list_authority_records() == original
    assert scm.swaps == []


def test_old_delivery_diagnostic_does_not_move_to_replacement_plan(subject):
    bus, scm, state = subject
    deliver(bus, plan_label=False)
    assert readback(bus)["last_delivery"]
    scm.comments.append(replace(scm.comments[0], id=72, created_at="2026-10-19T10:03:00Z"))
    assert "last_delivery" not in readback(bus)
    deliver(bus, plan_label=False)
    assert "last_delivery" not in readback(bus)
    rows = state.projections.list_projections(series=SERIES)
    assert len([row for row in rows if row.status == "delivery_not_materialized"]) == 1
    assert all(row.payload["plan_comment_id"] == 71 for row in rows)


def test_missing_or_broken_dependencies_never_report_accepted(subject):
    bus, scm, state = subject
    bus.run_projection_store = None
    assert deliver(bus, plan_label=False)["approval_diagnostic"]["diagnostic_persisted"] is False
    assert readback(bus)["status"] == "not_materialized"
    bus.authority_state_store = None
    assert readback(bus)["status"] == "unknown"
    bus.authority_state_store = state.authority
    scm.get_comments = lambda _: (_ for _ in ()).throw(OSError("private provider payload"))
    view = readback(bus)
    assert view["status"] == "unknown"
    assert "private" not in json.dumps(view)
    result = deliver(bus, plan_label=False)
    assert result["approval_diagnostic"]["diagnostic_persisted"] is False
    assert "private" not in json.dumps(result)


def test_dashboard_detail_uses_existing_authority_and_does_not_create_a_run(subject):
    bus, scm, state = subject
    handler = RunProjectionHandler(bus, state.projections)
    handler.register()
    bus.publish(PlanPosted(payload={"issue": 16}, correlation_id="plan948"))
    before = state.projections.list_projections(series="workflow-run.v1")
    deliver(bus, plan_label=False)
    dashboard = DashboardHandler(bus, scm=scm, run_projection_store=state.projections)
    detail = dashboard.get_workflow_detail(16)
    assert detail["plan_approval"]["status"] == "not_materialized"
    assert detail["plan_approval"]["label_is_authority"] is False
    assert state.projections.list_projections(series="workflow-run.v1") == before
    assert state.authority.list_authority_records() == []


def test_diagnostic_store_failure_does_not_change_approval_or_leak_payloads(subject):
    bus, scm, state = subject

    class BrokenProjection:
        def upsert_projection(self, _record):
            raise OSError("private diagnostic failure")

        def get_projection(self, _key):
            raise OSError("private diagnostic failure")

    bus.run_projection_store = BrokenProjection()
    result = deliver(bus, plan_label=False)
    assert result["approval_diagnostic"]["diagnostic_persisted"] is False
    assert state.authority.list_authority_records() == []
    assert "private" not in json.dumps(readback(bus))
    assert deliver(bus)["action"] == "plan_approved"
    assert readback(bus)["status"] == "accepted"
    assert scm.swaps == []


def test_invalid_signature_cannot_write_a_diagnostic(subject):
    bus, scm, state = subject
    result = WebhookIngressAdapter(bus, secret=SECRET).handle_webhook(
        "issues",
        {"issue": {"number": 16}},
        "invalid",
        raw_body=b"{}",
        provider="gitea",
        event_subtype="issue_label",
        delivery_id=DELIVERY,
    )
    assert result["status"] == 401
    assert state.projections.list_projections(series=SERIES) == []
    assert state.authority.list_authority_records() == []


def test_passive_http_detail_survives_projection_reopen_without_workflow_effects(subject):
    bus, scm, state = subject
    RunProjectionHandler(bus, state.projections).register()
    bus.publish(PlanPosted(payload={"issue": 16}, correlation_id="plan948-http"))
    deliver(bus, plan_label=False)
    # A second adapter instance reads the persisted projection after reopening.
    from samuel.adapters.state.sqlite import SQLiteRunProjectionStore

    bus.run_projection_store = SQLiteRunProjectionStore(state)
    events: list[Event] = []
    bus.subscribe("*", events.append)
    srv = create_server(bus, scm=scm, host="127.0.0.1", port=0, authentication=False)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/api/v1/dashboard/workflow/16"
        with urllib.request.urlopen(url, timeout=3) as response:
            detail = json.load(response)
        assert detail["plan_approval"]["status"] == "not_materialized"
        assert detail["plan_approval"]["last_delivery"]["reason_code"] == "plan_labels_incomplete"
        assert events == []
        assert scm.swaps == []
        assert state.authority.list_authority_records() == []
        with urllib.request.urlopen(
            url.rsplit("/workflow/", 1)[0] + "/logs", timeout=3
        ) as response:
            logs = json.load(response)
        compact = [r for r in logs["entries"] if r["event"] == "Planfreigabe-Hinweis"]
        assert len(compact) == 1 and compact[0]["issue"] == 16
        assert compact[0]["meta"]["reason_code"] == "plan_labels_incomplete"
        assert len(scm.feedback) == 1
        assert events == []
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=3)


def test_issue_feedback_and_compact_logs_are_deduplicated_and_resolved(subject, tmp_path):
    bus, scm, state = subject
    dashboard = DashboardHandler(bus, scm=scm, run_projection_store=state.projections)
    dashboard._data_dir = lambda: str(tmp_path)
    result = deliver(bus, plan_label=False)
    assert result["approval_diagnostic"]["issue_feedback"] == "posted"
    assert len(scm.feedback) == 1
    body = scm.feedback[0].body
    assert "nicht als neue Planfreigabe übernommen" in body
    assert "Nächster Schritt" in body and "erneut setzen" in body
    assert "[Plan-Kommentar 71](#issuecomment-71)" in body
    active = latest_active_plan(scm.comments)
    assert active is not None and active[0].id == 71
    logs = dashboard.get_logs()
    assert len(logs["entries"]) == 1
    row = logs["entries"][0]
    assert row["issue"] == 16 and row["level"] == "warn"
    assert row["meta"]["reason_code"] == "plan_labels_incomplete"
    assert logs["level_counts"] == {"info": 0, "warn": 1, "error": 0}
    deliver(bus, plan_label=False)
    assert len(scm.feedback) == 1
    assert dashboard.get_logs() == logs  # Replays cannot renew the observation timestamp.
    assert deliver(bus)["action"] == "plan_approved"
    assert len(scm.feedback) == 2
    assert "Planfreigabe wurde für diesen Plan angenommen" in scm.feedback[-1].body
    resolved = dashboard.get_logs()
    assert len(resolved["entries"]) == 1
    assert resolved["entries"][0]["meta"]["status"] == "resolved"
    assert resolved["entries"][0]["resolved_at"]
    assert resolved["level_counts"] == {"info": 1, "warn": 0, "error": 0}
    deliver(bus, plan_label=False)
    deliver(bus)
    assert len(scm.feedback) == 2
    assert dashboard.get_logs() == resolved


def test_two_runtime_instances_claim_only_one_issue_notice(subject, tmp_path):
    bus, scm, state = subject
    second_state = SQLiteStateStore(tmp_path / "state", mountinfo_path=tmp_path / "mountinfo")
    second_bus = Bus()
    second_bus.scm = scm
    second_bus.authority_state_store = second_state.authority
    second_bus.run_projection_store = second_state.projections
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda b: deliver(b, plan_label=False), [bus, second_bus] * 4))
    assert all(r["action"] == "ignored" for r in results)
    assert len(scm.feedback) == 1
    assert state.authority.list_authority_records() == []


@pytest.mark.parametrize("write_happened", [False, True])
def test_uncertain_comment_post_is_not_blindly_retried(subject, write_happened):
    bus, scm, state = subject
    actual_post = scm.post_comment
    calls = []

    def uncertain_post(number, body):
        calls.append(1)
        if write_happened:
            actual_post(number, body)
        raise OSError("private provider payload")

    scm.post_comment = uncertain_post
    first = deliver(bus, plan_label=False)
    assert first["approval_diagnostic"]["issue_feedback"] == "unknown"
    second = deliver(bus, plan_label=False)
    assert second["approval_diagnostic"]["issue_feedback"] == (
        "already_posted" if write_happened else "unknown"
    )
    assert calls == [1]
    assert "private provider" not in json.dumps(second)
    assert state.authority.list_authority_records() == []
    assert len(scm.feedback) == int(write_happened)


def test_unknown_authority_feedback_does_not_advise_removing_valid_labels(subject):
    bus, scm, state = subject

    class UnreadableAuthority:
        def get_authority_record(self, _key):
            raise OSError("private authority error")

    bus.authority_state_store = UnreadableAuthority()
    deliver(bus, plan_label=False)
    assert len(scm.feedback) == 1
    assert "Keine Labels auf Verdacht entfernen" in scm.feedback[0].body
    assert "erneut setzen" not in scm.feedback[0].body
    assert "private authority" not in scm.feedback[0].body
    assert scm.swaps == []


def test_feedback_comment_cannot_become_a_bot_approval(subject):
    bus, scm, state = subject
    deliver(bus, plan_label=False)
    events: list[Event] = []
    bus.subscribe("*", events.append)
    payload = {
        "action": "created",
        "issue": {"number": 16, "labels": [{"name": "status:plan"}]},
        "comment": {
            "id": scm.feedback[0].id,
            "body": scm.feedback[0].body,
            "created_at": scm.feedback[0].created_at,
        },
        "sender": {"login": "samuel", "type": "Bot"},
    }
    raw = json.dumps(payload).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    WebhookIngressAdapter(bus, secret=SECRET, bot_user="samuel").handle_webhook(
        "issue_comment",
        payload,
        signature,
        raw_body=raw,
        provider="gitea",
    )
    assert not any(event.name == "PlanApproved" for event in events)
    assert state.authority.list_authority_records() == []
    assert len(scm.feedback) == 1


def test_feedback_claim_does_not_cross_a_plan_replacement(subject):
    bus, scm, state = subject
    deliver(bus, plan_label=False)
    scm.comments.append(replace(scm.comments[0], id=72, created_at="2026-10-19T10:03:00Z"))
    deliver(bus, plan_label=False)  # Old timestamp may not notify the replacement plan.
    assert len(scm.feedback) == 1
    deliver(bus, plan_label=False, timestamp="2026-10-19T10:04:00Z")
    assert len(scm.feedback) == 2
    assert "[Plan-Kommentar 72](#issuecomment-72)" in scm.feedback[-1].body


def test_log_merge_sorts_audit_and_projection_timestamps_by_actual_time(subject, tmp_path):
    from datetime import datetime, timedelta, timezone

    bus, scm, state = subject
    deliver(bus, plan_label=False)
    folder = tmp_path / "logs"
    folder.mkdir()
    later = datetime.now(timezone.utc) + timedelta(minutes=1)
    (folder / "agent.jsonl").write_text(
        json.dumps(
            {
                "ts": later.isoformat(sep=" "),
                "payload": {"message_name": "LaterAudit", "issue": 16},
            }
        )
        + "\n"
    )
    dashboard = DashboardHandler(bus, scm=scm, run_projection_store=state.projections)
    dashboard._data_dir = lambda: str(tmp_path)
    logs = dashboard.get_logs()
    assert [e["event"] for e in logs["entries"]] == ["LaterAudit", "Planfreigabe-Hinweis"]
    assert sum(logs["level_counts"].values()) == len(logs["entries"])


@pytest.mark.parametrize("resolved", [False, True])
def test_busy_audit_tail_retains_only_unresolved_approval_guidance(subject, tmp_path, resolved):
    from datetime import datetime, timedelta, timezone

    bus, scm, state = subject
    deliver(bus, plan_label=False)
    dashboard = DashboardHandler(bus, scm=scm, run_projection_store=state.projections)
    dashboard._data_dir = lambda: str(tmp_path)
    original = dashboard.get_logs()["entries"][0]
    if resolved:
        assert deliver(bus)["action"] == "plan_approved"
    folder = tmp_path / "logs"
    folder.mkdir()
    later = datetime.now(timezone.utc) + timedelta(minutes=1)
    (folder / "agent.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "ts": (later + timedelta(seconds=index)).isoformat(sep=" "),
                    "payload": {"message_name": "LaterAudit", "issue": 16, "reason": str(index)},
                }
            )
            + "\n"
            for index in range(230)
        )
    )
    before = state.projections.list_projections(series=SERIES)
    logs = dashboard.get_logs()
    assert len(logs["entries"]) == 200
    hints = [entry for entry in logs["entries"] if entry["event"] == "Planfreigabe-Hinweis"]
    assert hints == ([] if resolved else [original])
    assert logs["entries"][0]["message"].endswith("229")
    assert logs["level_counts"] == {
        "info": 200 if resolved else 199,
        "warn": int(not resolved),
        "error": 0,
    }
    assert state.projections.list_projections(series=SERIES) == before
    assert dashboard.get_logs() == logs
    if not resolved:
        deliver(bus, plan_label=False)
        assert dashboard.get_logs() == logs
        assert state.authority.list_authority_records() == []
        assert len(scm.feedback) == 1


def test_more_than_200_active_approval_hints_keep_the_newest_without_growing_response(subject):
    from datetime import timedelta

    bus, scm, state = subject
    deliver(bus, plan_label=False)
    original = next(
        row
        for row in state.projections.list_projections(series=SERIES)
        if row.status == "delivery_not_materialized"
    )
    for index in range(1, 206):
        state.projections.upsert_projection(
            replace(
                original,
                projection_key=f"{SERIES}:synthetic-{index}",
                issue_number=1000 + index,
                updated_at=original.updated_at + timedelta(seconds=index),
                payload={**original.payload, "issue": 1000 + index},
            )
        )
    dashboard = DashboardHandler(bus, scm=scm, run_projection_store=state.projections)
    entries = dashboard.get_logs()["entries"]
    assert len(entries) == 200
    assert [entry["issue"] for entry in entries] == list(range(1205, 1005, -1))
    assert all(entry["event"] == "Planfreigabe-Hinweis" for entry in entries)
    assert state.authority.list_authority_records() == []


def test_missing_notification_cas_does_not_change_an_accepted_approval(subject):
    from samuel.core.ports import IRunProjectionStore

    bus, scm, state = subject

    class NoCAS(IRunProjectionStore):
        def get_projection(self, key):
            return state.projections.get_projection(key)

        def upsert_projection(self, record):
            state.projections.upsert_projection(record)

        def list_projections(self, issue_number=None, *, series=None):
            return state.projections.list_projections(issue_number, series=series)

    bus.run_projection_store = NoCAS()
    events: list[Event] = []
    bus.subscribe("*", events.append)
    assert deliver(bus)["action"] == "plan_approved"
    assert readback(bus)["status"] == "accepted"
    assert len(scm.feedback) == 0
    assert sum(event.name == "PlanApproved" for event in events) == 1
