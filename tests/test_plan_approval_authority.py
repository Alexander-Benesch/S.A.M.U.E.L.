from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from pathlib import Path

import pytest

from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.acceptance import (
    PLAN_APPROVAL_AUTHORITY_KIND,
    AcceptanceApproval,
    AcceptanceContract,
    PlanApprovalAuthorityError,
    PlanningSourceSnapshot,
    PlanRevocation,
    issue_revision_digest,
    parse_acceptance_contract,
    persist_plan_approval,
    persist_plan_approval_with_status,
    render_plan_revocation,
    render_planning_source,
    resolve_plan_approval,
    text_digest,
)
from samuel.core.bus import Bus
from samuel.core.events import Event
from samuel.core.state import StateStoreError, WorkflowBudgetAdmissionRecord
from samuel.core.types import Comment, Issue, Label, SCMLabelEvent


class _SCM:
    repository_identity = "owner/repo"

    def __init__(self, *, base_sha: str, issue: Issue, event: SCMLabelEvent) -> None:
        self.base_sha = base_sha
        self.issue = issue
        self.event = event

    def get_issue(self, number: int) -> Issue:
        assert number == self.issue.number
        return self.issue

    def resolve_ref(self, ref: str) -> str:
        assert ref == "main"
        return self.base_sha

    def get_label_events(self, number: int, label: str) -> list[SCMLabelEvent]:
        assert number == self.issue.number
        assert label in {"", "status:approved"}
        return [self.event]


def _state(tmp_path: Path) -> SQLiteStateStore:
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        f"36 25 0:32 / {tmp_path} rw,relatime - ext4 device rw\n",
        encoding="utf-8",
    )
    return SQLiteStateStore(tmp_path / "state", mountinfo_path=mountinfo)


def _fixture() -> tuple[
    str,
    Issue,
    Comment,
    AcceptanceContract,
    AcceptanceApproval,
    SCMLabelEvent,
]:
    base_sha = "a" * 40
    issue = Issue(
        42,
        "Durable approval",
        "Human approval must survive MANUAL pending.",
        "open",
        labels=[Label(1, "status:failed")],
    )
    source = PlanningSourceSnapshot(
        schema_version=1,
        repository="owner/repo",
        base_ref="main",
        base_sha=base_sha,
        issue_digest=issue_revision_digest(
            number=issue.number,
            title=issue.title,
            body=issue.body,
        ),
    )
    plan = Comment(
        71,
        "## Plan\n### Akzeptanzkriterien\n- [ ] [MANUAL] Human verifies candidate\n\n"
        + render_planning_source(source),
        "samuel",
        "2026-09-25T10:00:00Z",
    )
    contract = parse_acceptance_contract(plan.body)
    event = SCMLabelEvent(
        source_id="gitea-timeline:72",
        label="status:approved",
        actor="alice",
        actor_type="human",
        timestamp="2026-09-25T10:01:00Z",
    )
    approval = AcceptanceApproval(
        state="approved",
        actor="alice",
        method="status:approved/polling",
        source_id="plan:71;gitea-timeline:72",
        approved_at=event.timestamp,
        contract_hash=contract.contract_hash,
        plan_comment_id=plan.id,
    )
    return base_sha, issue, plan, contract, approval, event


def test_durable_approval_survives_status_projection_and_restart(tmp_path: Path) -> None:
    base_sha, issue, plan, contract, approval, event = _fixture()
    state = _state(tmp_path)
    persisted = persist_plan_approval(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=approval,
        transport="authenticated_scm_polling",
    )
    assert persisted.kind == PLAN_APPROVAL_AUTHORITY_KIND

    # The mutable projection has moved to failed and no approved label remains.
    assert {label.name for label in issue.labels} == {"status:failed"}
    restarted = _state(tmp_path)
    resolved = resolve_plan_approval(
        restarted.authority,
        scm=_SCM(base_sha=base_sha, issue=issue, event=event),  # type: ignore[arg-type]
        repository="owner/repo",
        issue_number=issue.number,
        plan_comment=plan,
        contract=contract,  # type: ignore[arg-type]
        comments=[plan],
        expected_base_sha=base_sha,
    )
    assert resolved == approval


def test_replan_revokes_durable_approval(tmp_path: Path) -> None:
    base_sha, issue, plan, contract, approval, event = _fixture()
    state = _state(tmp_path)
    persist_plan_approval(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=approval,
        transport="authenticated_scm_polling",
    )
    revocation = PlanRevocation(
        schema_version=1,
        plan_comment_id=plan.id,
        contract_hash=contract.contract_hash,  # type: ignore[attr-defined]
        reason_digest=text_digest("new requirements"),
        revoked_at="2026-09-25T10:02:00Z",
        actor="operator:local-cli",
    )
    revocation_comment = Comment(
        73,
        render_plan_revocation(revocation),
        plan.user,
        revocation.revoked_at,
    )

    with pytest.raises(PlanApprovalAuthorityError) as exc:
        resolve_plan_approval(
            state.authority,
            scm=_SCM(base_sha=base_sha, issue=issue, event=event),  # type: ignore[arg-type]
            repository="owner/repo",
            issue_number=issue.number,
            plan_comment=plan,
            contract=contract,  # type: ignore[arg-type]
            comments=[plan, revocation_comment],
        )
    assert exc.value.code == "plan_approval_revoked_or_superseded"


@pytest.mark.parametrize("change", ["contract", "subject", "source", "event"])
def test_foreign_or_stale_approval_blocks(tmp_path: Path, change: str) -> None:
    base_sha, issue, plan, contract, approval, event = _fixture()
    state = _state(tmp_path)
    persist_plan_approval(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=approval,
        transport="authenticated_scm_polling",
    )
    repository = "other/repo" if change == "subject" else "owner/repo"
    used_contract = contract
    if change == "contract":
        used_contract = parse_acceptance_contract(
            "## Plan\n### Akzeptanzkriterien\n- [ ] [MANUAL] Different contract"
        )
    scm = _SCM(base_sha=("b" * 40 if change == "source" else base_sha), issue=issue, event=event)
    if change == "event":
        scm.event = SCMLabelEvent(
            source_id="gitea-timeline:999",
            label="status:approved",
            actor="alice",
            actor_type="human",
            timestamp=event.timestamp,
        )

    with pytest.raises(PlanApprovalAuthorityError):
        resolve_plan_approval(
            state.authority,
            scm=scm,  # type: ignore[arg-type]
            repository=repository,
            issue_number=issue.number,
            plan_comment=plan,
            contract=used_contract,  # type: ignore[arg-type]
            comments=[plan],
        )


def test_missing_authority_and_label_alone_cannot_fabricate_approval(tmp_path: Path) -> None:
    base_sha, issue, plan, contract, _approval, event = _fixture()
    state = _state(tmp_path)
    issue.labels = [Label(2, "status:approved")]

    with pytest.raises(PlanApprovalAuthorityError) as exc:
        resolve_plan_approval(
            state.authority,
            scm=_SCM(base_sha=base_sha, issue=issue, event=event),  # type: ignore[arg-type]
            repository="owner/repo",
            issue_number=issue.number,
            plan_comment=plan,
            contract=contract,  # type: ignore[arg-type]
            comments=[plan],
        )
    assert exc.value.code == "plan_approval_authority_missing"


def test_approval_replay_is_idempotent_and_different_receipt_conflicts(tmp_path: Path) -> None:
    _base_sha, issue, _plan, contract, approval, _event = _fixture()
    state = _state(tmp_path)
    first, first_created = persist_plan_approval_with_status(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=approval,
        transport="authenticated_scm_polling",
    )
    second, second_created = persist_plan_approval_with_status(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=approval,
        transport="authenticated_scm_polling",
    )
    assert first_created is True
    assert second_created is False
    assert first.payload == second.payload
    assert (
        len(
            [
                record
                for record in state.authority.list_authority_records()
                if record.kind == first.kind
            ]
        )
        == 1
    )

    changed = AcceptanceApproval(
        state="approved",
        actor="bob",
        method=approval.method,
        source_id="plan:71;gitea-timeline:74",
        approved_at="2026-09-25T10:03:00Z",
        contract_hash=approval.contract_hash,
        plan_comment_id=approval.plan_comment_id,
    )
    with pytest.raises(StateStoreError) as exc:
        persist_plan_approval(
            state.authority,
            repository="owner/repo",
            issue_number=issue.number,
            contract=contract,  # type: ignore[arg-type]
            approval=changed,
            transport="authenticated_scm_polling",
        )
    assert exc.value.code == "plan_approval_replay_conflict"


@pytest.mark.parametrize("first_transport", ["signed_webhook", "authenticated_scm_polling"])
def test_same_label_decision_replays_across_webhook_and_polling(
    tmp_path: Path,
    first_transport: str,
) -> None:
    _base_sha, issue, _plan, contract, polling, _event = _fixture()
    state = _state(tmp_path)
    webhook = AcceptanceApproval(
        state="approved",
        actor=polling.actor,
        method="status:approved",
        source_id="plan:71;label:9:2026-09-25T10:01:00Z",
        approved_at=polling.approved_at,
        contract_hash=polling.contract_hash,
        plan_comment_id=polling.plan_comment_id,
    )
    first = webhook if first_transport == "signed_webhook" else polling
    second = polling if first_transport == "signed_webhook" else webhook
    second_transport = (
        "authenticated_scm_polling" if first_transport == "signed_webhook" else "signed_webhook"
    )

    persisted = persist_plan_approval(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=first,
        transport=first_transport,
    )
    replayed = persist_plan_approval(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=second,
        transport=second_transport,
    )

    assert replayed == persisted
    assert replayed.payload["approval"] == first.as_dict()
    assert len(state.authority.list_authority_records()) == 1


def test_changed_source_on_same_transport_is_not_treated_as_cross_channel_replay(
    tmp_path: Path,
) -> None:
    _base_sha, issue, _plan, contract, approval, _event = _fixture()
    state = _state(tmp_path)
    persist_plan_approval(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=approval,
        transport="authenticated_scm_polling",
    )
    changed_source = replace(approval, source_id="plan:71;gitea-timeline:999")

    with pytest.raises(StateStoreError) as exc:
        persist_plan_approval(
            state.authority,
            repository="owner/repo",
            issue_number=issue.number,
            contract=contract,  # type: ignore[arg-type]
            approval=changed_source,
            transport="authenticated_scm_polling",
        )

    assert exc.value.code == "plan_approval_replay_conflict"


def test_signed_webhook_materializes_same_durable_authority(tmp_path: Path) -> None:
    state = _state(tmp_path)
    plan = Comment(
        71,
        "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] candidate.py",
        "samuel",
        "2026-09-25T10:00:00Z",
    )
    contract = parse_acceptance_contract(plan.body)

    class WebhookSCM:
        repository_identity = "owner/repo"

        def get_comments(self, number: int) -> list[Comment]:
            assert number == 42
            return [plan]

    admission = WorkflowBudgetAdmissionRecord(
        admission_key="webhook-plan-42",
        repository="owner/repo",
        issue_number=42,
        invocation_digest="sha256:" + "1" * 64,
        source_digest="sha256:" + "2" * 64,
        policy_digest="sha256:" + "3" * 64,
        correlation_id="planning-42",
        token_limit=1000,
    )
    state.authority.put_budget_admission(admission)
    state.authority.bind_budget_plan(
        admission.admission_key,
        plan_contract_hash=contract.contract_hash,
        plan_comment_id=plan.id,
    )
    bus = Bus()
    bus.scm = WebhookSCM()
    bus.authority_state_store = state.authority
    events: list[Event] = []
    bus.subscribe("*", events.append)
    secret = "synthetic-webhook-secret"
    adapter = WebhookIngressAdapter(bus, secret=secret, bot_user="samuel")
    payload = {
        "issue": {
            "number": 42,
            "updated_at": "2026-09-25T10:01:00Z",
            "labels": [{"name": "status:plan"}],
        },
        "label": {"id": 9, "name": "status:approved"},
        "sender": {"login": "alice"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    result = adapter.handle_webhook("issue-labeled", payload, signature, raw_body=body)

    assert result["action"] == "plan_approved"
    approved = next(event for event in events if event.name == "PlanApproved")
    record = next(
        row
        for row in state.authority.list_authority_records()
        if row.kind == PLAN_APPROVAL_AUTHORITY_KIND
    )
    assert record.payload["approval"] == approved.payload["acceptance_approval"]
    assert record.payload["source"]["transport"] == "signed_webhook"


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_signed_webhook_timeline_source_is_revalidated_as_label_addition(
    tmp_path: Path,
    operation: str,
) -> None:
    base_sha, issue, plan, contract, polling, event = _fixture()
    event = SCMLabelEvent(
        source_id=event.source_id,
        label=event.label,
        actor=event.actor,
        actor_type=event.actor_type,
        timestamp=event.timestamp,
        operation=operation,
    )
    approval = replace(
        polling,
        method="status:approved",
        source_id=(
            f"plan:{plan.id};{event.source_id};delivery:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        ),
    )
    state = _state(tmp_path)
    persist_plan_approval(
        state.authority,
        repository="owner/repo",
        issue_number=issue.number,
        contract=contract,  # type: ignore[arg-type]
        approval=approval,
        transport="signed_webhook",
    )

    if operation == "add":
        assert (
            resolve_plan_approval(
                state.authority,
                scm=_SCM(base_sha=base_sha, issue=issue, event=event),  # type: ignore[arg-type]
                repository="owner/repo",
                issue_number=issue.number,
                plan_comment=plan,
                contract=contract,  # type: ignore[arg-type]
                comments=[plan],
            )
            == approval
        )
    else:
        with pytest.raises(PlanApprovalAuthorityError) as exc:
            resolve_plan_approval(
                state.authority,
                scm=_SCM(base_sha=base_sha, issue=issue, event=event),  # type: ignore[arg-type]
                repository="owner/repo",
                issue_number=issue.number,
                plan_comment=plan,
                contract=contract,  # type: ignore[arg-type]
                comments=[plan],
            )
        assert exc.value.code == "plan_approval_source_stale"
