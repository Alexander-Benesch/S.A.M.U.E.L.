"""Tests for REST API, webhook ingress, and API key auth."""

from __future__ import annotations

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from samuel.adapters.api.auth import APIKeyAuth
from samuel.adapters.api.rest import RestAPI
from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.acceptance import AcceptanceApproval, latest_active_plan, persist_plan_approval
from samuel.core.bus import AuditMiddleware, Bus, ErrorMiddleware
from samuel.core.events import Event, IssueReady
from samuel.core.state import AuthorityRecord
from samuel.core.types import Comment, SCMLabelEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_events(bus: Bus) -> list:
    events: list = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


def _make_bus_with_handlers() -> Bus:
    """Create a Bus with dummy command handlers so send() doesn't warn."""
    bus = Bus()
    bus.register_command("PlanIssue", lambda cmd: {"ok": True, "issue": cmd.issue_number})
    bus.register_command("Implement", lambda cmd: {"ok": True, "issue": cmd.issue_number})
    bus.register_command("HealthCheck", lambda cmd: {"status": "healthy"})
    bus.register_command("ScanIssues", lambda cmd: {"scanned": True})
    return bus


class _ApprovalSCM:
    repository_identity = "owner/repo"

    def __init__(self, label_events: list[SCMLabelEvent] | None = None) -> None:
        self.label_events = (
            label_events
            if label_events is not None
            else [
                SCMLabelEvent(
                    "gitea-timeline:81",
                    "status:approved",
                    "operator",
                    "human",
                    "2026-08-25T10:00:00Z",
                )
            ]
        )

    def get_comments(self, number: int):
        return [
            Comment(
                id=7,
                body="## Plan\n- [ ] [DIFF] candidate.py",
                user="example-bot",
                created_at="2026-08-25T09:00:00Z",
            )
        ]

    def get_label_events(self, number: int, label: str):
        assert number == 16
        if not label:
            return self.label_events
        return [
            event
            for event in self.label_events
            if event.label == label and event.operation == "add"
        ]


class _ApprovalAuthority:
    def __init__(self) -> None:
        self.records: dict[str, AuthorityRecord] = {}

    def find_budget_admission(self, **_kwargs):
        return type("Admission", (), {"admission_key": "budget-plan"})()

    def put_authority_record(self, record: AuthorityRecord) -> bool:
        self.records.setdefault(record.record_key, record)
        return True

    def get_authority_record(self, key: str) -> AuthorityRecord | None:
        return self.records.get(key)


_APPROVAL_SECRET = "approval-webhook-secret"
_NATIVE_DELIVERY_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_NATIVE_FIXTURE = Path(__file__).parent / "fixtures" / "gitea-1.27.2-issue-label-approved.json"


def _signed_webhook(adapter: WebhookIngressAdapter, event: str, payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(_APPROVAL_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return adapter.handle_webhook(event, payload, signature, raw_body=body)


def _native_gitea_webhook(
    adapter: WebhookIngressAdapter,
    payload: dict,
    *,
    event: str = "issues",
    event_subtype: str = "issue_label",
    delivery_id: str = _NATIVE_DELIVERY_ID,
) -> dict:
    body = json.dumps(payload, indent=2).encode()
    signature = hmac.new(_APPROVAL_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return adapter.handle_webhook(
        event,
        payload,
        signature,
        raw_body=body,
        provider="gitea",
        event_subtype=event_subtype,
        delivery_id=delivery_id,
    )


def _native_gitea_label_payload(
    *,
    label: str = "status:approved",
    actor: str = "operator",
    actor_type: str = "",
    updated_at: str = "2026-08-25T10:00:00Z",
) -> dict:
    fixture = json.loads(_NATIVE_FIXTURE.read_text(encoding="utf-8"))
    payload: dict = fixture["payload"]
    payload["issue"]["updated_at"] = updated_at
    payload["issue"]["labels"] = [
        {"id": 3, "name": "status:plan"},
        {"id": 4, "name": label},
    ]
    payload["sender"] = {"login": actor}
    if actor_type:
        payload["sender"]["type"] = actor_type
    return payload


# ---------------------------------------------------------------------------
# Tests: RestAPI
# ---------------------------------------------------------------------------


class TestRestAPI:
    """Tests for RestAPI request routing."""

    def test_post_plan_dispatches_plan_issue_command(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/42/plan")

        assert resp["status"] == 202
        assert resp["data"]["ok"] is True
        assert resp["data"]["issue"] == 42

    def test_post_implement_dispatches_implement_command(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/7/implement")

        assert resp["status"] == 202
        assert resp["data"]["ok"] is True
        assert resp["data"]["issue"] == 7

    def test_post_plan_keeps_202_for_legitimate_none_result(self):
        bus = Bus()
        bus.register_command("PlanIssue", lambda _cmd: None)
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/42/plan")

        assert resp == {"status": 202, "data": None}

    def test_post_plan_maps_handled_not_found_to_correlated_problem(self):
        class TargetNotFound(Exception):
            status = 404

        written = []
        events = _collect_events(bus := Bus())
        bus.add_middleware(
            AuditMiddleware(sink=type("Sink", (), {"write": lambda _, e: written.append(e)})())
        )
        bus.add_middleware(ErrorMiddleware(bus=bus))

        def fail(_cmd):
            raise TargetNotFound("private upstream payload")

        bus.register_command("PlanIssue", fail)
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/999999/plan")

        assert resp["status"] == 404
        problem = resp["data"]
        assert problem == {
            "type": "urn:samuel:problem:command-target-not-found",
            "title": "Command target not found",
            "status": 404,
            "detail": "The command target is unavailable.",
            "code": "command_target_not_found",
            "correlation_id": problem["correlation_id"],
            "command": "PlanIssue",
            "issue": 999999,
        }
        assert problem["correlation_id"]
        correlated = [
            event for event in events if event.name in {"DiagnosticRaised", "WorkflowAborted"}
        ]
        assert len(correlated) == 2
        assert {event.correlation_id for event in correlated} == {problem["correlation_id"]}
        assert {event.payload["reason"] for event in correlated} == {"command_target_not_found"}
        command_audit = next(
            event for event in written if event.payload.get("message_name") == "PlanIssue"
        )
        assert command_audit.payload["correlation_id"] == problem["correlation_id"]
        assert command_audit.payload["error"] == "command_target_not_found"
        assert "private upstream payload" not in str(resp)
        assert "private upstream payload" not in str(correlated)

    def test_post_implement_maps_handled_internal_error_to_500_problem(self):
        bus = Bus()
        bus.add_middleware(ErrorMiddleware(bus=bus))
        bus.register_command(
            "Implement", lambda _cmd: (_ for _ in ()).throw(RuntimeError("private detail"))
        )
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/7/implement")

        assert resp["status"] == 500
        assert resp["data"]["code"] == "internal_command_error"
        assert resp["data"]["issue"] == 7
        assert "private detail" not in str(resp)

    def test_problem_response_survives_diagnostic_publication_failure(self):
        from samuel.core.events import DiagnosticRaised

        class DiagnosticFailingBus(Bus):
            def publish(self, event):
                if isinstance(event, DiagnosticRaised):
                    raise RuntimeError("diagnostic transport unavailable")
                return super().publish(event)

        bus = DiagnosticFailingBus()
        bus.add_middleware(ErrorMiddleware(bus=bus))
        aborted: list[Event] = []
        bus.subscribe("WorkflowAborted", aborted.append)
        bus.register_command(
            "PlanIssue", lambda _cmd: (_ for _ in ()).throw(RuntimeError("private detail"))
        )
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/issues/42/plan")

        assert resp["status"] == 500
        assert resp["data"]["code"] == "internal_command_error"
        assert len(aborted) == 1
        assert aborted[0].correlation_id == resp["data"]["correlation_id"]

    def test_get_health_returns_200(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("GET", "/api/v1/health")

        assert resp["status"] == 200
        assert resp["data"]["status"] == "healthy"

    def test_get_metrics_returns_data(self):
        from samuel.core.bus import MetricsMiddleware

        bus = _make_bus_with_handlers()
        mw = MetricsMiddleware()
        bus.add_middleware(mw)
        api = RestAPI(bus)

        resp = api.handle_request("GET", "/api/metrics")

        assert resp["status"] == 200
        assert "counts" in resp["data"]
        assert "errors" in resp["data"]

    def test_get_metrics_delegates_to_dashboard_handler_when_present(self):
        # When wired with a dashboard handler, /api/metrics must use the
        # cross-process audit-log aggregator (not the in-memory middleware),
        # so it returns the same data as /api/v1/dashboard/metrics.
        bus = _make_bus_with_handlers()

        class FakeDashboard:
            def get_metrics(self) -> dict[str, object]:
                return {"counts": {"PlanIssue": 7}, "errors": {}, "total_ms": {"PlanIssue": 50.0}}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request("GET", "/api/metrics")
        assert resp["status"] == 200
        assert resp["data"]["counts"] == {"PlanIssue": 7}
        assert resp["data"]["total_ms"] == {"PlanIssue": 50.0}

    def test_unknown_route_returns_404(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("GET", "/api/v1/nonexistent")

        assert resp["status"] == 404
        assert "not found" in resp["error"]

    def test_test_connection_route_calls_dashboard(self):
        """#314-AC: POST /api/v1/dashboard/llm/test-connection -> dashboard.test_connection."""
        bus = _make_bus_with_handlers()
        captured: dict = {}

        class FakeDashboard:
            def test_connection(self, provider, cfg):
                captured["provider"] = provider
                captured["cfg"] = cfg
                return {"valid": True, "detail": "http 200", "balance": 5.0}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request(
            "POST",
            "/api/v1/dashboard/llm/test-connection",
            body={"provider": "deepseek", "config": {"model": "deepseek-chat"}},
        )
        assert resp["status"] == 200
        assert resp["data"]["valid"] is True
        assert resp["data"]["balance"] == 5.0
        assert captured["provider"] == "deepseek"

    def test_test_connection_route_400_when_no_provider(self):
        bus = _make_bus_with_handlers()

        class FakeDashboard:
            def test_connection(self, provider, cfg):
                return {"valid": True}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request(
            "POST",
            "/api/v1/dashboard/llm/test-connection",
            body={"config": {}},
        )
        assert resp["status"] == 400

    def test_risk_class_route_calls_dashboard(self):
        """#374-AC: POST /api/v1/settings/risk-class -> dashboard.set_risk_class."""
        bus = _make_bus_with_handlers()
        captured: dict = {}

        class FakeDashboard:
            def set_risk_class(self, value):
                captured["value"] = value
                return {"updated": True, "risk_class": value}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request(
            "POST",
            "/api/v1/settings/risk-class",
            body={"risk_class": "high_risk"},
        )
        assert resp["status"] == 200
        assert resp["data"]["risk_class"] == "high_risk"
        assert captured["value"] == "high_risk"

    def test_risk_class_route_400_when_missing(self):
        bus = _make_bus_with_handlers()

        class FakeDashboard:
            def set_risk_class(self, value):
                return {"updated": True}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request("POST", "/api/v1/settings/risk-class", body={})
        assert resp["status"] == 400

    def test_risk_class_route_400_on_invalid_value(self):
        bus = _make_bus_with_handlers()

        class FakeDashboard:
            def set_risk_class(self, value):
                return {"updated": False, "error": "invalid risk class: 'x'"}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request(
            "POST",
            "/api/v1/settings/risk-class",
            body={"risk_class": "x"},
        )
        assert resp["status"] == 400
        assert resp["data"]["updated"] is False

    def test_attribution_route_calls_dashboard(self):
        """#270: POST /api/v1/settings/attribution -> dashboard.set_attribution."""
        bus = _make_bus_with_handlers()
        captured: dict = {}

        class FakeDashboard:
            def set_attribution(self, enabled, verbosity=None):
                captured["enabled"] = enabled
                captured["verbosity"] = verbosity
                return {"updated": True, "enabled": enabled}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request(
            "POST",
            "/api/v1/settings/attribution",
            body={"enabled": False, "verbosity": "full"},
        )
        assert resp["status"] == 200
        assert resp["data"]["enabled"] is False
        assert captured == {"enabled": False, "verbosity": "full"}

    def test_attribution_route_400_when_missing(self):
        bus = _make_bus_with_handlers()

        class FakeDashboard:
            def set_attribution(self, enabled, verbosity=None):
                return {"updated": True}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request("POST", "/api/v1/settings/attribution", body={})
        assert resp["status"] == 400

    def test_attribution_route_409_when_locked(self):
        """high_risk -> Sperre -> 409 Conflict."""
        bus = _make_bus_with_handlers()

        class FakeDashboard:
            def set_attribution(self, enabled, verbosity=None):
                return {"updated": False, "locked": True, "error": "Pflicht"}

        api = RestAPI(bus, dashboard_handler=FakeDashboard())
        resp = api.handle_request(
            "POST",
            "/api/v1/settings/attribution",
            body={"enabled": False},
        )
        assert resp["status"] == 409
        assert resp["data"]["locked"] is True

    def test_auth_failure_returns_401(self):
        bus = _make_bus_with_handlers()
        auth = APIKeyAuth(valid_keys=["secret123"])
        api = RestAPI(bus, auth_middleware=auth)

        resp = api.handle_request(
            "GET", "/api/v1/health", headers={"Authorization": "Bearer wrong"}
        )

        assert resp["status"] == 401
        assert resp["error"] == "unauthorized"

    def test_auth_success_allows_request(self):
        bus = _make_bus_with_handlers()
        auth = APIKeyAuth(valid_keys=["secret123"])
        api = RestAPI(bus, auth_middleware=auth)

        resp = api.handle_request(
            "GET",
            "/api/v1/health",
            headers={"Authorization": "Bearer secret123"},
        )

        assert resp["status"] == 200


# ---------------------------------------------------------------------------
# Tests: WebhookIngressAdapter
# ---------------------------------------------------------------------------


class TestWebhookIngressAdapter:
    """Tests for the webhook ingress adapter."""

    def test_issue_created_publishes_issue_ready(self):
        bus = _make_bus_with_handlers()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)

        payload = {"issue": {"number": 5}}
        resp = wh.handle_webhook("issue-created", payload)

        assert resp["status"] == 202
        assert resp["action"] == "issue_ready"
        issue_ready_events = [e for e in events if isinstance(e, IssueReady)]
        assert len(issue_ready_events) == 1
        assert issue_ready_events[0].payload["issue"] == 5

    def test_issue_labeled_with_approved_dispatches_plan(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        payload = {
            "issue": {
                "number": 10,
                "updated_at": "2026-08-25T10:00:00Z",
                "labels": [{"name": "status:plan"}],
            },
            "label": {"id": 3, "name": "status:approved"},
            "sender": {"login": "operator"},
        }
        resp = _signed_webhook(wh, "issue-labeled", payload)

        assert resp["status"] == 202
        assert resp["action"] == "plan_approved"
        assert resp["issue"] == 10

    def test_human_approval_without_signed_durable_authority_blocks(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        events = _collect_events(bus)
        payload = {
            "issue": {
                "number": 10,
                "updated_at": "2026-08-25T10:00:00Z",
                "labels": [{"name": "status:plan"}],
            },
            "label": {"id": 3, "name": "status:approved"},
            "sender": {"login": "operator"},
        }

        response = WebhookIngressAdapter(bus).handle_webhook("issue-labeled", payload)

        assert response["status"] == 409
        assert response["reason"] == "plan_approval_authority_persist_failed"
        assert not any(event.name == "PlanApproved" for event in events)

    def test_real_gitea_label_event_publishes_plan_approved(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET, bot_user="example-bot")

        payload = {
            "action": "label",
            "issue": {
                "number": 16,
                "updated_at": "2026-08-25T10:00:00Z",
                "labels": [{"name": "status:plan"}],
            },
            "label": {"id": 4, "name": "status:approved"},
            "sender": {"login": "operator"},
        }
        resp = _signed_webhook(
            wh,
            "issues",
            payload,
        )

        assert resp["action"] == "plan_approved"
        assert any(e.name == "PlanApproved" and e.payload["issue"] == 16 for e in events)

    def test_native_gitea_issue_label_add_publishes_plan_approved(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET, bot_user="example-bot")

        response = _native_gitea_webhook(wh, _native_gitea_label_payload())

        assert response == {"status": 202, "action": "plan_approved", "issue": 16}
        assert any(event.name == "PlanApproved" for event in events)
        assert len(bus.authority_state_store.records) == 1
        approval = next(event for event in events if event.name == "PlanApproved")
        assert approval.payload["acceptance_approval"]["source_id"] == (
            "plan:7;gitea-timeline:81;delivery:" + _NATIVE_DELIVERY_ID
        )
        record = next(iter(bus.authority_state_store.records.values()))
        assert record.payload["source"]["transport"] == "signed_webhook"

    def test_native_fixture_matches_observed_gitea_shape(self):
        fixture = json.loads(_NATIVE_FIXTURE.read_text(encoding="utf-8"))

        assert fixture["headers"]["X-Gitea-Event"] == "issues"
        assert fixture["headers"]["X-Gitea-Event-Type"] == "issue_label"
        assert fixture["payload"]["action"] == "label_updated"
        assert "changes" not in fixture["payload"]
        assert sorted(fixture["payload"]) == [
            "action",
            "commit_id",
            "issue",
            "number",
            "repository",
            "sender",
        ]

    def test_native_gitea_wrong_label_does_not_create_authority(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(
            wh,
            _native_gitea_label_payload(label="risk:low"),
        )

        assert response["action"] == "ignored"
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_native_gitea_other_label_at_webhook_time_does_not_reuse_approval(self):
        timeline = [
            SCMLabelEvent(
                "gitea-timeline:82",
                "risk:low",
                "operator",
                "human",
                "2026-08-25T10:00:00Z",
            )
        ]
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM(timeline)
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(wh, _native_gitea_label_payload())

        assert response["action"] == "ignored"
        assert response["reason"] == (
            "provider timeline event is not the matching human approval addition"
        )
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_native_gitea_later_label_update_cannot_reuse_historical_approval(self):
        timeline = [
            SCMLabelEvent(
                "gitea-timeline:81",
                "status:approved",
                "operator",
                "human",
                "2026-08-25T10:00:00Z",
            ),
            SCMLabelEvent(
                "gitea-timeline:82",
                "risk:low",
                "operator",
                "human",
                "2026-08-25T10:01:00Z",
            ),
        ]
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM(timeline)
        bus.authority_state_store = _ApprovalAuthority()
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(
            wh,
            _native_gitea_label_payload(updated_at="2026-08-25T10:01:00Z"),
        )

        assert response["action"] == "ignored"
        assert bus.authority_state_store.records == {}

    def test_native_gitea_later_label_update_does_not_rematerialize_authority(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)
        approved = _native_gitea_webhook(wh, _native_gitea_label_payload())
        bus.scm.label_events.append(
            SCMLabelEvent(
                "gitea-timeline:82",
                "risk:low",
                "operator",
                "human",
                "2026-08-25T10:01:00Z",
            )
        )

        later = _native_gitea_webhook(
            wh,
            _native_gitea_label_payload(updated_at="2026-08-25T10:01:00Z"),
            delivery_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        )

        assert approved["action"] == "plan_approved"
        assert later["action"] == "ignored"
        assert len(bus.authority_state_store.records) == 1
        assert len([event for event in events if event.name == "PlanApproved"]) == 1

    @pytest.mark.parametrize(
        "timeline",
        [
            [],
            [
                SCMLabelEvent(
                    "gitea-timeline:81",
                    "status:approved",
                    "operator",
                    "human",
                    "2026-08-25T10:00:00Z",
                ),
                SCMLabelEvent(
                    "gitea-timeline:82",
                    "risk:low",
                    "operator",
                    "human",
                    "2026-08-25T10:00:00Z",
                ),
            ],
        ],
        ids=["missing", "ambiguous"],
    )
    def test_native_gitea_timeline_correlation_must_be_unique(self, timeline):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM(timeline)
        bus.authority_state_store = _ApprovalAuthority()
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(wh, _native_gitea_label_payload())

        assert response["action"] == "ignored"
        assert response["reason"] == (
            "native label event is not uniquely correlated to the provider timeline"
        )
        assert bus.authority_state_store.records == {}

    def test_native_gitea_webhook_and_timeline_actor_must_match(self):
        timeline = [
            SCMLabelEvent(
                "gitea-timeline:81",
                "status:approved",
                "different-human",
                "human",
                "2026-08-25T10:00:00Z",
            )
        ]
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM(timeline)
        bus.authority_state_store = _ApprovalAuthority()
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(wh, _native_gitea_label_payload())

        assert response["action"] == "ignored"
        assert bus.authority_state_store.records == {}

    @pytest.mark.parametrize("delivery_id", ["", "not-a-delivery", "A" * 36])
    def test_native_gitea_delivery_id_is_required_for_authority(self, delivery_id):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(
            wh,
            _native_gitea_label_payload(),
            delivery_id=delivery_id,
        )

        assert response["action"] == "ignored"
        assert response["reason"] == "native delivery id is missing or malformed"
        assert bus.authority_state_store.records == {}

    @pytest.mark.parametrize("action", ["label_updated", "label_cleared"])
    def test_native_gitea_label_removal_does_not_create_authority(self, action):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM(
            [
                SCMLabelEvent(
                    "gitea-timeline:82",
                    "status:approved",
                    "operator",
                    "human",
                    "2026-08-25T10:00:00Z",
                    operation="remove",
                )
            ]
        )
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)
        payload = _native_gitea_label_payload()
        payload["action"] = action
        payload["issue"]["labels"] = [{"name": "status:plan"}]

        response = _native_gitea_webhook(wh, payload)

        assert response["action"] == "ignored"
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_native_gitea_bot_actor_does_not_create_authority(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET, bot_user="example-bot")

        response = _native_gitea_webhook(
            wh,
            _native_gitea_label_payload(actor="example-bot", actor_type="Bot"),
        )

        assert response["action"] == "ignored"
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_native_gitea_stale_label_event_is_rejected(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM(
            [
                SCMLabelEvent(
                    "gitea-timeline:80",
                    "status:approved",
                    "operator",
                    "human",
                    "2026-08-25T08:59:59Z",
                )
            ]
        )
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(
            wh,
            _native_gitea_label_payload(updated_at="2026-08-25T08:59:59Z"),
        )

        assert response["action"] == "ignored"
        assert response["reason"] == "provider timeline approval predates the active plan"
        assert not any(event.name == "PlanApproved" for event in events)

    def test_native_gitea_wrong_plan_contract_admission_is_blocked(self):
        class WrongPlanAuthority(_ApprovalAuthority):
            def find_budget_admission(self, **_kwargs):
                return None

        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = WrongPlanAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(wh, _native_gitea_label_payload())

        assert response == {
            "status": 409,
            "action": "blocked",
            "reason": "workflow_budget_admission_missing",
        }
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_native_gitea_plan_change_during_correlation_is_blocked(self):
        class ChangingPlanSCM(_ApprovalSCM):
            def __init__(self):
                super().__init__()
                self.comment_reads = 0

            def get_comments(self, number: int):
                self.comment_reads += 1
                comments = super().get_comments(number)
                if self.comment_reads == 1:
                    return comments
                return [
                    Comment(
                        id=7,
                        body="## Plan\n- [ ] [DIFF] replacement.py",
                        user="example-bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

        bus = _make_bus_with_handlers()
        bus.scm = ChangingPlanSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(wh, _native_gitea_label_payload())

        assert response == {
            "status": 200,
            "action": "ignored",
            "reason": "approval evidence is not bound to the active plan",
        }
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_native_gitea_does_not_adopt_polling_transport_authority(self):
        scm = _ApprovalSCM()
        authority = _ApprovalAuthority()
        plan, contract = latest_active_plan(scm.get_comments(16)) or (None, None)
        assert plan is not None and contract is not None
        persist_plan_approval(
            authority,  # type: ignore[arg-type]
            repository=scm.repository_identity,
            issue_number=16,
            contract=contract,
            approval=AcceptanceApproval(
                state="approved",
                actor="operator",
                method="status:approved/polling",
                source_id=f"plan:{plan.id};gitea-timeline:81",
                approved_at="2026-08-25T10:00:00Z",
                contract_hash=contract.contract_hash,
                plan_comment_id=plan.id,
            ),
            transport="authenticated_scm_polling",
        )
        bus = _make_bus_with_handlers()
        bus.scm = scm
        bus.authority_state_store = authority
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(wh, _native_gitea_label_payload())

        assert response == {
            "status": 409,
            "action": "blocked",
            "reason": "signed_webhook_authority_transport_required",
        }
        assert not any(event.name == "PlanApproved" for event in events)
        assert len(authority.records) == 1

    def test_native_gitea_repository_and_issue_must_match(self):
        for mutate in (
            lambda payload: payload["repository"].update(full_name="foreign/repo"),
            lambda payload: payload.update(number=999),
        ):
            bus = _make_bus_with_handlers()
            bus.scm = _ApprovalSCM()
            bus.authority_state_store = _ApprovalAuthority()
            events = _collect_events(bus)
            wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)
            payload = _native_gitea_label_payload()
            mutate(payload)

            response = _native_gitea_webhook(wh, payload)

            assert response["action"] == "ignored"
            assert response["reason"] == "repository or issue binding mismatch"
            assert not any(event.name == "PlanApproved" for event in events)
            assert bus.authority_state_store.records == {}

    def test_native_gitea_replay_is_idempotent_and_conflict_fails_closed(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)
        payload = _native_gitea_label_payload()

        first = _native_gitea_webhook(wh, payload, delivery_id=_NATIVE_DELIVERY_ID)
        replay = _native_gitea_webhook(wh, payload, delivery_id=_NATIVE_DELIVERY_ID)
        bus.scm.label_events = [
            SCMLabelEvent(
                "gitea-timeline:81",
                "status:approved",
                "another-human",
                "human",
                "2026-08-25T10:00:00Z",
            )
        ]
        conflicting = _native_gitea_label_payload(actor="another-human")
        conflict = _native_gitea_webhook(
            wh,
            conflicting,
            delivery_id=_NATIVE_DELIVERY_ID,
        )

        assert first["action"] == "plan_approved"
        assert replay == {
            "status": 200,
            "action": "ignored",
            "reason": "approval delivery already materialized",
        }
        assert conflict == {
            "status": 409,
            "action": "blocked",
            "reason": "plan_approval_authority_persist_failed",
        }
        assert len(bus.authority_state_store.records) == 1
        assert len([event for event in events if event.name == "PlanApproved"]) == 1

    def test_parallel_signed_native_approval_materializes_once(self, tmp_path: Path):
        database = SQLiteStateStore(tmp_path)
        simultaneous = Barrier(2)

        class PersistentApprovalAuthority:
            def find_budget_admission(self, **_kwargs):
                simultaneous.wait(timeout=3)
                return type("Admission", (), {"admission_key": "budget-plan"})()

            def put_authority_record(self, record):
                return database.authority.put_authority_record(record)

            def get_authority_record(self, key):
                return database.authority.get_authority_record(key)

        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = PersistentApprovalAuthority()
        events = _collect_events(bus)
        adapter = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)
        payload = _native_gitea_label_payload()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(lambda _: _native_gitea_webhook(adapter, payload), range(2))
            )

        assert sorted(result["action"] for result in results) == ["ignored", "plan_approved"]
        assert len([event for event in events if event.name == "PlanApproved"]) == 1
        assert len(database.authority.list_authority_records()) == 1

    @pytest.mark.parametrize(
        ("event", "event_subtype"),
        [("future_event", "issue_label"), ("issues", "future_issue_event")],
    )
    def test_signed_unknown_native_event_cannot_create_authority(self, event, event_subtype):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)

        response = _native_gitea_webhook(
            wh,
            _native_gitea_label_payload(),
            event=event,
            event_subtype=event_subtype,
        )

        assert response["action"] == "ignored"
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_native_gitea_unknown_subtype_cannot_use_legacy_label_mapping(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)
        payload = _native_gitea_label_payload()
        payload["action"] = "labeled"
        payload["label"] = {"id": 4, "name": "status:approved"}

        response = _native_gitea_webhook(
            wh,
            payload,
            event_subtype="future_issue_event",
        )

        assert response["action"] == "ignored"
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_label_approval_carries_receipt_for_exact_visible_contract(self):
        bus = _make_bus_with_handlers()
        events = _collect_events(bus)

        class ApprovalSCM:
            repository_identity = "owner/repo"

            def get_comments(self, number: int):
                return [
                    Comment(
                        id=7,
                        body="## Plan\n- [x] [DIFF] candidate.py",
                        user="example-bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

        bus.scm = ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET, bot_user="example-bot")
        payload = {
            "action": "labeled",
            "issue": {
                "number": 16,
                "updated_at": "2026-08-25T10:00:00Z",
                "labels": [{"name": "status:plan"}],
            },
            "label": {"id": 4, "name": "status:approved"},
            "sender": {"login": "operator"},
        }
        _signed_webhook(
            wh,
            "issues",
            payload,
        )

        approval = next(e for e in events if e.name == "PlanApproved").payload[
            "acceptance_approval"
        ]
        assert approval["state"] == "approved"
        assert approval["actor"] == "operator"
        assert approval["source_id"] == "plan:7;label:4:2026-08-25T10:00:00Z"
        assert approval["plan_comment_id"] == 7
        assert approval["contract_hash"].startswith("sha256:")

    def test_label_approval_blocks_without_exact_budget_admission(self):
        bus = _make_bus_with_handlers()
        events = _collect_events(bus)

        class ApprovalSCM:
            repository_identity = "owner/repo"

            def get_comments(self, number: int):
                return [
                    Comment(
                        id=7,
                        body="## Plan\n- [x] [DIFF] candidate.py",
                        user="example-bot",
                        created_at="2026-08-25T09:00:00Z",
                    )
                ]

        class MissingAuthority:
            def find_budget_admission(self, **kwargs):
                assert kwargs["repository"] == "owner/repo"
                assert kwargs["issue_number"] == 16
                assert kwargs["plan_comment_id"] == 7
                assert kwargs["plan_contract_hash"].startswith("sha256:")
                return None

        bus.scm = ApprovalSCM()
        bus.authority_state_store = MissingAuthority()
        wh = WebhookIngressAdapter(bus, bot_user="example-bot")
        response = wh.handle_webhook(
            "issues",
            {
                "action": "labeled",
                "issue": {
                    "number": 16,
                    "updated_at": "2026-08-25T10:00:00Z",
                    "labels": [{"name": "status:plan"}],
                },
                "label": {"id": 4, "name": "status:approved"},
                "sender": {"login": "operator"},
            },
        )

        assert response["status"] == 409
        assert response["reason"] == "workflow_budget_admission_missing"
        assert any(event.name == "WorkflowBlocked" for event in events)
        assert not any(event.name == "PlanApproved" for event in events)

    def test_approved_label_without_visible_plan_is_ignored(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)

        resp = wh.handle_webhook(
            "issues",
            {
                "action": "label",
                "issue": {"number": 16, "labels": [{"name": "status:approved"}]},
                "label": {"name": "status:approved"},
                "sender": {"login": "operator"},
            },
        )

        assert resp == {
            "status": 200,
            "action": "ignored",
            "reason": "no visible plan awaiting approval",
        }
        assert not any(e.name == "PlanApproved" for e in events)

    def test_label_event_before_active_plan_is_not_rebound(self):
        bus = _make_bus_with_handlers()

        class NewerPlanSCM:
            def get_comments(self, number: int):
                return [
                    Comment(
                        id=12,
                        body="## Plan\n- [ ] [DIFF] candidate.py",
                        user="example-bot",
                        created_at="2026-08-25T11:00:00Z",
                    )
                ]

        bus.scm = NewerPlanSCM()
        events = _collect_events(bus)
        response = WebhookIngressAdapter(bus, bot_user="example-bot").handle_webhook(
            "issues",
            {
                "action": "labeled",
                "issue": {
                    "number": 16,
                    "updated_at": "2026-08-25T10:00:00Z",
                    "labels": [{"name": "status:plan"}],
                },
                "label": {"id": 4, "name": "status:approved"},
                "sender": {"login": "operator"},
            },
        )

        assert response["action"] == "ignored"
        assert not any(event.name == "PlanApproved" for event in events)

    def test_ok_comment_approves_only_visible_plan(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET, bot_user="example-bot")

        payload = {
            "action": "created",
            "issue": {"number": 16, "labels": [{"name": "status:plan"}]},
            "comment": {
                "id": 8,
                "body": "ok",
                "created_at": "2026-08-25T10:00:00Z",
            },
            "sender": {"login": "operator"},
        }
        resp = _signed_webhook(
            wh,
            "issue_comment",
            payload,
        )

        assert resp["action"] == "plan_approved"
        assert any(e.name == "IssueCommented" for e in events)
        assert any(e.name == "PlanApproved" for e in events)

    def test_bot_ok_comment_cannot_self_approve(self):
        bus = _make_bus_with_handlers()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, bot_user="example-bot")

        resp = wh.handle_webhook(
            "issue_comment",
            {
                "action": "created",
                "issue": {"number": 16, "labels": [{"name": "status:plan"}]},
                "comment": {"body": "ok"},
                "sender": {"login": "example-bot"},
            },
        )

        assert resp["action"] == "issue_commented"
        assert not any(e.name == "PlanApproved" for e in events)

    def test_push_triggers_scan(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus)

        resp = wh.handle_webhook("push", {"ref": "refs/heads/main"})

        assert resp["status"] == 202
        assert resp["action"] == "scan_triggered"

    def test_unknown_event_type_ignored(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus)

        resp = wh.handle_webhook("unknown-event", {})

        assert resp["status"] == 200
        assert resp["action"] == "ignored"

    def test_invalid_signature_returns_401(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret="my-secret")

        resp = wh.handle_webhook("issue-created", {"issue": {"number": 1}}, signature="bad-sig")

        assert resp["status"] == 401
        assert "invalid signature" in resp["error"]


class TestWebhookSCMActivity:
    """#230: reale Gitea-Events -> beobachtende SCM-Activity-Events."""

    def _names(self, events):
        return [e.name for e in events]

    def test_issue_closed(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)
        resp = wh.handle_webhook(
            "issues",
            {
                "action": "closed",
                "issue": {"number": 42, "title": "T", "html_url": "u"},
                "sender": {"login": "alice"},
            },
        )
        assert resp["status"] == 202 and resp["action"] == "issue_closed"
        assert "IssueClosed" in self._names(ev)
        p = [e for e in ev if e.name == "IssueClosed"][0].payload
        assert p["number"] == 42 and p["actor"] == "alice"
        assert p["actor_type"] == "human" and p["source"] == "webhook"

    def test_issue_opened(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)
        resp = wh.handle_webhook(
            "issues",
            {
                "action": "opened",
                "issue": {"number": 7, "created_at": "2026-08-21T10:00:00Z"},
                "sender": {"login": "x"},
            },
        )
        assert resp["action"] == "issue_opened"
        event = [event for event in ev if event.name == "IssueOpened"][0]
        assert event.payload["timestamp"] == "2026-08-21T10:00:00Z"
        assert event.payload["activity_id"] == "IssueOpened:7:2026-08-21T10:00:00Z"
        assert event.payload["idempotency_key"].startswith("scm_activity:")

    def test_issue_comment_created(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)
        resp = wh.handle_webhook(
            "issue_comment",
            {
                "action": "created",
                "issue": {"number": 9},
                "comment": {"id": 99, "created_at": "2026-08-21T10:01:00Z"},
                "sender": {"login": "y"},
            },
        )
        assert resp["action"] == "issue_commented"
        event = [event for event in ev if event.name == "IssueCommented"][0]
        assert event.payload["activity_id"] == "IssueCommented:99:2026-08-21T10:01:00Z"

    def test_pull_request_opened(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)
        resp = wh.handle_webhook(
            "pull_request",
            {
                "action": "opened",
                "pull_request": {"number": 3, "title": "PR"},
                "sender": {"login": "z"},
            },
        )
        assert resp["action"] == "pr_opened"
        assert "PullRequestOpened" in self._names(ev)

    def test_pull_request_merged(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)
        resp = wh.handle_webhook(
            "pull_request",
            {
                "action": "closed",
                "pull_request": {"number": 3, "merged": True},
                "sender": {"login": "z"},
            },
        )
        assert resp["action"] == "pr_merged"
        assert "PullRequestMerged" in self._names(ev)

    def test_pull_request_closed_unmerged(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)
        resp = wh.handle_webhook(
            "pull_request",
            {
                "action": "closed",
                "pull_request": {"number": 4, "merged": False},
                "sender": {"login": "z"},
            },
        )
        assert resp["action"] == "pr_closed"
        assert "PullRequestClosed" in self._names(ev)

    def test_bot_actor_classified_via_bot_user(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, bot_user="samuel-bot")
        wh.handle_webhook(
            "issues",
            {
                "action": "closed",
                "issue": {"number": 1},
                "sender": {"login": "samuel-bot"},
            },
        )
        assert [e for e in ev if e.name == "IssueClosed"][0].payload["actor_type"] == "bot"

    def test_unhandled_action_ignored(self):
        bus = _make_bus_with_handlers()
        ev = _collect_events(bus)
        wh = WebhookIngressAdapter(bus)
        resp = wh.handle_webhook("issues", {"action": "assigned", "issue": {"number": 1}})
        assert resp["action"] == "ignored"
        assert not any(e.name == "IssueClosed" for e in ev)

    def test_invalid_signature_publishes_tamper_detected(self):
        """#208: nicht verifizierbare Webhook-Signatur -> TamperDetected
        (HMAC dient der Tamper-Erkennung). Sichtbar im Security-Tab."""
        from samuel.core.events import TamperDetected

        bus = _make_bus_with_handlers()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret="my-secret")

        wh.handle_webhook("push", {"x": 1}, signature="sha256=deadbeef")

        tamper = [e for e in events if isinstance(e, TamperDetected)]
        assert len(tamper) == 1
        assert tamper[0].payload["reason"] == "webhook signature verification failed"
        assert tamper[0].payload["owasp_risk"] == "agentic_supply_chain"
        assert tamper[0].payload["event_type"] == "push"

    def test_valid_signature_does_not_publish_tamper(self):
        from samuel.core.events import TamperDetected

        secret = "my-secret"
        bus = _make_bus_with_handlers()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=secret)
        payload = {"issue": {"number": 3}}
        body = json.dumps(payload, separators=(",", ":")).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        wh.handle_webhook("issue-created", payload, signature=sig, raw_body=body)
        assert [e for e in events if isinstance(e, TamperDetected)] == []

    def test_valid_signature_accepted(self):
        secret = "my-secret"
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret=secret)

        payload = {"issue": {"number": 3}}
        body = json.dumps(payload, separators=(",", ":")).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        resp = wh.handle_webhook("issue-created", payload, signature=sig, raw_body=body)

        assert resp["status"] == 202

    def test_native_gitea_signature_uses_unmodified_body_and_bare_digest(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret="my-secret")
        payload = {"issue": {"number": 3}}
        raw_body = b'{\n  "issue": {"number": 3}\n}'
        signature = hmac.new(b"my-secret", raw_body, hashlib.sha256).hexdigest()

        response = wh.handle_webhook(
            "issue-created",
            payload,
            signature,
            raw_body=raw_body,
            provider="gitea",
        )

        assert response["status"] == 200

    @pytest.mark.parametrize(
        "signature",
        [
            "",
            "not-a-digest",
            "sha256=" + "0" * 64,
            "A" * 64,
            "0" * 63,
            "0" * 65,
        ],
    )
    def test_native_gitea_missing_or_malformed_signature_is_denied(self, signature):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret="my-secret")

        response = wh.handle_webhook(
            "issues",
            {"action": "opened"},
            signature,
            raw_body=b'{"action":"opened"}',
            provider="gitea",
            event_subtype="issues",
        )

        assert response["status"] == 401

    def test_native_gitea_wrong_digest_is_denied(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret="my-secret")

        response = wh.handle_webhook(
            "issues",
            {"action": "opened"},
            "0" * 64,
            raw_body=b'{"action":"opened"}',
            provider="gitea",
            event_subtype="issues",
        )

        assert response["status"] == 401

    def test_native_gitea_approval_without_signature_is_denied_before_mapping(self):
        bus = _make_bus_with_handlers()
        bus.scm = _ApprovalSCM()
        bus.authority_state_store = _ApprovalAuthority()
        events = _collect_events(bus)
        wh = WebhookIngressAdapter(bus, secret=_APPROVAL_SECRET)
        payload = _native_gitea_label_payload()
        raw_body = json.dumps(payload, indent=2).encode()

        response = wh.handle_webhook(
            "issues",
            payload,
            "",
            raw_body=raw_body,
            provider="gitea",
            event_subtype="issue_label",
            delivery_id="unsigned-approval",
        )

        assert response["status"] == 401
        assert not any(event.name == "PlanApproved" for event in events)
        assert bus.authority_state_store.records == {}

    def test_github_prefixed_signature_contract_remains_supported(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret="my-secret")
        payload = {"issue": {"number": 3}}
        raw_body = json.dumps(payload, separators=(",", ":")).encode()
        signature = "sha256=" + hmac.new(b"my-secret", raw_body, hashlib.sha256).hexdigest()

        response = wh.handle_webhook(
            "issue-created",
            payload,
            signature,
            raw_body=raw_body,
            provider="github",
        )

        assert response["status"] == 202

    def test_webhook_observability_excludes_signature_and_payload(self, caplog):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus, secret="my-secret")
        raw_body = b'{"private":"payload-value"}'
        signature = hmac.new(b"my-secret", raw_body, hashlib.sha256).hexdigest()

        with caplog.at_level("INFO"):
            wh.handle_webhook(
                "unknown",
                {"private": "payload-value"},
                signature,
                raw_body=raw_body,
                provider="gitea",
                event_subtype="unknown",
                delivery_id="safe-delivery-id",
            )

        logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "stage=received" in logs
        assert "stage=signature" in logs and "result=pass" in logs
        assert "stage=mapping" in logs
        assert signature not in logs
        assert "payload-value" not in logs

    def test_missing_issue_number_returns_400(self):
        bus = _make_bus_with_handlers()
        wh = WebhookIngressAdapter(bus)

        resp = wh.handle_webhook("issue-created", {"issue": {}})

        assert resp["status"] == 400


# ---------------------------------------------------------------------------
# Tests: APIKeyAuth
# ---------------------------------------------------------------------------


class TestAPIKeyAuth:
    """Tests for the API key authentication middleware."""

    def test_no_keys_fail_closed(self):
        auth = APIKeyAuth(valid_keys=None)

        assert auth.authenticate({}) is False
        assert auth.authenticate({"Authorization": "Bearer anything"}) is False

    def test_empty_keys_fail_closed(self):
        auth = APIKeyAuth(valid_keys=[])

        assert auth.authenticate({}) is False

    def test_valid_bearer_token_passes(self):
        auth = APIKeyAuth(valid_keys=["token-abc"])

        assert auth.authenticate({"Authorization": "Bearer token-abc"}) is True

    def test_valid_x_api_key_passes(self):
        auth = APIKeyAuth(valid_keys=["key-xyz"])

        assert auth.authenticate({"X-API-Key": "key-xyz"}) is True

    def test_invalid_token_rejects(self):
        auth = APIKeyAuth(valid_keys=["correct-key"])

        assert auth.authenticate({"Authorization": "Bearer wrong-key"}) is False

    def test_no_auth_header_rejects(self):
        auth = APIKeyAuth(valid_keys=["some-key"])

        assert auth.authenticate({}) is False

    def test_lowercase_header_works(self):
        auth = APIKeyAuth(valid_keys=["key-123"])

        assert auth.authenticate({"authorization": "Bearer key-123"}) is True
        assert auth.authenticate({"x-api-key": "key-123"}) is True


# ---------------------------------------------------------------------------
# Tests: Phase 14.6 endpoints (POST /setup/labels, POST /settings/flag)
# ---------------------------------------------------------------------------


class _StubSetup:
    def __init__(self, result: dict):
        self._result = result
        self.called = False

    def sync_labels(self) -> dict:
        self.called = True
        return self._result


class _StubDashboard:
    def __init__(self, result: dict, llm_task_result: dict | None = None):
        self._result = result
        self._llm_task_result = llm_task_result or {"updated": True, "task": "x"}
        self.calls: list[tuple[str, bool]] = []
        self.llm_task_calls: list[tuple[str, dict]] = []
        self.llm_global_calls: list[dict] = []
        self.extension_calls: list[dict] = []

    def set_feature_flag(self, name: str, enabled: bool) -> dict:
        self.calls.append((name, enabled))
        return self._result

    def set_llm_task_config(self, task: str, cfg: dict) -> dict:
        self.llm_task_calls.append((task, cfg))
        return self._llm_task_result

    def set_llm_global_config(self, cfg: dict) -> dict:
        self.llm_global_calls.append(cfg)
        return {"updated": True, "provider": cfg.get("provider"), "fallbacks": []}

    def set_extension_configuration(self, cfg: dict) -> dict:
        self.extension_calls.append(cfg)
        return self._result


class TestRestAPISetupLabels:
    def test_post_setup_labels_invokes_handler(self):
        bus = _make_bus_with_handlers()
        setup = _StubSetup({"synced": True, "created": ["a"], "skipped": [], "errors": []})
        api = RestAPI(bus, setup_handler=setup)

        resp = api.handle_request("POST", "/api/v1/setup/labels")

        assert resp["status"] == 200
        assert setup.called is True
        assert resp["data"]["created"] == ["a"]

    def test_post_setup_labels_without_handler_returns_503(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request("POST", "/api/v1/setup/labels")

        assert resp["status"] == 503


class TestRestAPISettingsFlag:
    def test_post_settings_flag_updates(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": True, "name": "eval", "enabled": True})
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request(
            "POST", "/api/v1/settings/flag", body={"name": "eval", "enabled": True}
        )

        assert resp["status"] == 200
        assert dash.calls == [("eval", True)]
        assert resp["data"]["enabled"] is True

    def test_post_settings_flag_missing_body_returns_400(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": False, "error": "x"})
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request("POST", "/api/v1/settings/flag", body={})
        assert resp["status"] == 400

    def test_post_settings_flag_unknown_returns_400(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": False, "error": "unknown flag: foo"})
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request(
            "POST", "/api/v1/settings/flag", body={"name": "foo", "enabled": True}
        )
        assert resp["status"] == 400

    def test_post_settings_flag_without_handler_returns_503(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request(
            "POST", "/api/v1/settings/flag", body={"name": "eval", "enabled": True}
        )
        assert resp["status"] == 503


class TestRestAPIExtensionSettings:
    def test_extension_settings_route_uses_dashboard_handler(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": True, "restart_required": True})
        api = RestAPI(bus, dashboard_handler=dash)
        body = {"enabled": True, "required": False, "manifest_path": "/x/capability.json"}

        response = api.handle_request(
            "POST", "/api/v1/settings/extensions/documentation", body=body
        )

        assert response["status"] == 200
        assert dash.extension_calls == [body]

    def test_extension_settings_route_preserves_production_freeze(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": False, "code": "configuration_frozen"})
        api = RestAPI(bus, dashboard_handler=dash)

        response = api.handle_request("POST", "/api/v1/settings/extensions/documentation", body={})

        assert response["status"] == 409

    def test_extension_settings_route_requires_handler(self):
        api = RestAPI(_make_bus_with_handlers())

        response = api.handle_request("POST", "/api/v1/settings/extensions/documentation", body={})

        assert response["status"] == 503


class TestRestAPISettingsLLMTask:
    """#309: POST /api/v1/settings/llm/task — Per-Task LLM-Config Write."""

    def test_settings_llm_global_endpoint_routes_to_handler(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": True})
        api = RestAPI(bus, dashboard_handler=dash)

        response = api.handle_request(
            "POST",
            "/api/v1/settings/llm/global",
            body={"provider": "deepseek", "fallbacks": ["openrouter"]},
        )

        assert response["status"] == 200
        assert dash.llm_global_calls == [{"provider": "deepseek", "fallbacks": ["openrouter"]}]

    def test_settings_llm_task_endpoint_routes_to_handler(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard(
            {"updated": True, "name": "x", "enabled": True},
            llm_task_result={"updated": True, "task": "planning", "cfg": {"provider": "claude"}},
        )
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request(
            "POST",
            "/api/v1/settings/llm/task",
            body={"task": "planning", "config": {"provider": "claude"}},
        )

        assert resp["status"] == 200
        assert dash.llm_task_calls == [("planning", {"provider": "claude"})]
        assert resp["data"]["updated"] is True

    def test_settings_llm_task_endpoint_returns_400_on_unknown_task(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard(
            {"updated": False, "error": "x"},
            llm_task_result={"updated": False, "error": "unknown task: not_a_task"},
        )
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request(
            "POST",
            "/api/v1/settings/llm/task",
            body={"task": "not_a_task", "config": {}},
        )

        assert resp["status"] == 400
        assert "unknown task" in resp["data"]["error"]

    def test_settings_llm_task_endpoint_missing_task_returns_400(self):
        bus = _make_bus_with_handlers()
        dash = _StubDashboard({"updated": True, "name": "x", "enabled": True})
        api = RestAPI(bus, dashboard_handler=dash)

        resp = api.handle_request(
            "POST",
            "/api/v1/settings/llm/task",
            body={"config": {"provider": "x"}},
        )
        assert resp["status"] == 400

    def test_settings_llm_task_endpoint_without_handler_returns_503(self):
        bus = _make_bus_with_handlers()
        api = RestAPI(bus)

        resp = api.handle_request(
            "POST",
            "/api/v1/settings/llm/task",
            body={"task": "planning", "config": {}},
        )
        assert resp["status"] == 503
