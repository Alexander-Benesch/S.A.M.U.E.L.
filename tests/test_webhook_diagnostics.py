"""#905: metadata/receiver evidence never grants workflow or native delivery authority."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest

from samuel.adapters.api.auth import permission_for_request
from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.adapters.gitea.api import GiteaAPI, GiteaAPIError
from samuel.adapters.github.api import GitHubAPI, GitHubAPIError
from samuel.core.bus import Bus
from samuel.core.events import Event
from samuel.core.identity import READ_DIAGNOSTICS, RUN_PROVIDER_PROBES
from samuel.core.webhook_diagnostics import (
    WebhookObservations,
    build_webhook_report,
    summarize_hooks,
    target_summary,
    timestamp,
)
from samuel.webhook_probe import read_webhook_configuration


def hook(provider="gitea"):
    return {
        "active": True,
        "type": "gitea",
        "name": "web",
        "events": ["issues", "issue_label", "issue_comment", "pull_request", "push"],
        "config": {
            "url": "http://user:private-secret@192.0.2.5:7777/api/v1/webhook?token=private-secret",
            "content_type": "json",
            "secret": "private-secret",
        },
        "authorization_header": "private-secret",
    }


def check(report, code):
    return next(c for c in report["checks"] if c["code"] == code)


@pytest.mark.parametrize("provider", ["gitea", "github"])
@pytest.mark.parametrize("status", [200, 401, 403, 404, 500, "malformed", "offline"])
def test_metadata_only_known_read_with_existing_credential(monkeypatch, provider, status):
    calls = []

    def request(self, method, path, *args, **kwargs):
        calls.append((method, path, self._auth.get_token()))
        if type(status) is int and status != 200:
            cls = GiteaAPIError if provider == "gitea" else GitHubAPIError
            raise cls(status, method, path, "private-secret")
        if status == "offline":
            raise OSError("private-secret")
        return [hook()] if status == 200 else {"private-secret": True}

    monkeypatch.setattr(GiteaAPI if provider == "gitea" else GitHubAPI, "request", request)
    read = read_webhook_configuration(provider, "https://scm.invalid", "existing-token", "o/r")
    assert calls == [
        (
            "GET",
            "/repos/o/r/hooks?"
            + ("limit=50&page=1" if provider == "gitea" else "per_page=50&page=1"),
            "existing-token",
        )
    ]
    assert read["permission_diagnostic"]["state"] == (
        "ACCESS_CONFIRMED"
        if status == 200
        else "OPERATOR_ACTION_REQUIRED"
        if status in {401, 403}
        else "UNKNOWN"
    )
    assert read["permission_diagnostic"]["actor"] == "runtime_bot"
    assert read["permission_diagnostic"]["operation"] == "webhook_read"
    assert "private-secret" not in json.dumps(read)
    report = build_webhook_report(provider, True, hook_read=read)
    assert check(report, "native_delivery")["state"] == "not_proven"
    assert all(c["status"] != "fail" for c in report["checks"])
    if status == 200:
        assert report["hooks"][0]["missing_events"] == []
        assert report["hooks"][0]["target"]["credentials_or_query"] is True


@pytest.mark.parametrize(
    "provider,repo",
    [("unsupported", "o/r"), ("gitea", "../r"), ("gitea", "o"), ("github", "o/r/x")],
)
def test_invalid_binding_has_no_network(monkeypatch, provider, repo):
    request = Mock(side_effect=AssertionError("network"))
    monkeypatch.setattr(GiteaAPI, "request", request)
    monkeypatch.setattr(GitHubAPI, "request", request)
    assert (
        read_webhook_configuration(provider, "https://scm.invalid", "token", repo)["state"]
        == "unknown"
    )
    request.assert_not_called()


@pytest.mark.parametrize(
    "url,private,path",
    [
        ("http://192.0.2.26:7777/api/v1/webhook", True, True),
        ("http://[::1]/api/v1/webhook", True, True),
        ("https://8.8.8.8/api/v1/webhook", False, True),
        ("http://localhost/api/v1/webhook", True, True),
        ("https://receiver.example.invalid/api/v1/webhook", None, True),
        ("https://receiver.example.invalid/private-secret", None, False),
        ("https://receiver.example.invalid:bad/api/v1/webhook", None, False),
        ("file:///private-secret", None, False),
    ],
)
def test_target_classification_without_dns_or_target_request(url, private, path):
    result = target_summary(url)
    assert result["private_target"] is private
    assert result["receiver_path"] is path
    assert "private-secret" not in json.dumps(result)


def test_missing_events_disabled_and_unknown_type_are_visible():
    value = hook()
    value.update(active=False, type="slack", events=["push", {"bad": True}])
    rows = summarize_hooks([value], "gitea")
    assert rows is not None
    result = rows[0]
    assert not result["active"] and not result["supported_type"]
    assert "issue_label" in result["missing_events"]
    assert "issue_comment" in result["missing_events"]
    assert len(summarize_hooks([hook()] * 70, "gitea")) == 50
    assert summarize_hooks([None], "gitea") is None


@pytest.mark.parametrize(
    "signature,expected", [("valid", "pass"), ("bad", "denied"), ("keyless", "not_checked")]
)
def test_real_ingress_outcomes_never_become_native_delivery_proof(signature, expected):
    bus = Bus()
    adapter = WebhookIngressAdapter(bus, secret="" if signature == "keyless" else "secret")
    raw = b'{"private-payload":"must-not-appear"}'
    signed = hmac.new(b"secret", raw, hashlib.sha256).hexdigest() if signature == "valid" else "bad"
    result = adapter.handle_webhook(
        "unknown-event",
        json.loads(raw),
        signed,
        raw_body=raw,
        provider="gitea",
        delivery_id="private-id",
    )
    report = build_webhook_report(
        "gitea", signature != "keyless", observations=adapter.observations.snapshot()
    )
    assert check(report, "signature")["state"] == expected
    assert check(report, "native_delivery")["state"] == "not_proven"
    assert check(report, "mapping")["state"] == ("denied" if signature == "bad" else "ignored")
    assert result["status"] == (401 if signature == "bad" else 200)
    assert "private-" not in json.dumps(report)
    assert build_webhook_report("gitea", True, observations=WebhookObservations().snapshot())[
        "informational_only"
    ]
    bus.close()


@pytest.mark.parametrize("age", [-1, 3601, 86400])
def test_stale_or_future_evidence_is_never_current(age):
    now = datetime.now(timezone.utc)
    date = (now - timedelta(seconds=age)).isoformat()
    report = build_webhook_report(
        "gitea",
        True,
        now=now,
        hook_read={
            "state": "read",
            "observed_at": date,
            "hooks": summarize_hooks([hook()], "gitea"),
        },
        observations={"signature": {"outcome": "pass", "observed_at": date, "provider": "gitea"}},
    )
    assert check(report, "hook_configuration")["state"] == "stale"
    assert check(report, "signature")["state"] == "stale"
    assert check(report, "native_delivery")["state"] == "not_proven"


def test_authorization_separates_passive_read_and_explicit_scm_read():
    assert permission_for_request("GET", "/api/v1/dashboard/webhook") == READ_DIAGNOSTICS
    assert permission_for_request("POST", "/api/v1/dashboard/webhook/read") == RUN_PROVIDER_PROBES


@contextmanager
def serving(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def test_real_http_dashboard_is_passive_until_explicit_metadata_read(monkeypatch, tmp_path):
    from samuel.server import create_server

    calls = []

    class SCM(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.command, self.path, self.headers.get("Authorization")))
            data = json.dumps([hook()]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    (tmp_path / "auth.json").write_bytes(Path("config/auth.json").read_bytes())
    bus = Bus()
    events: list[Event] = []
    bus.subscribe("*", events.append)
    commands = Mock(side_effect=AssertionError("no command dispatch"))
    monkeypatch.setattr(bus, "send", commands)
    with serving(ThreadingHTTPServer(("127.0.0.1", 0), SCM)) as scm:
        for key, value in {
            "SCM_PROVIDER": "gitea",
            "SCM_URL": scm,
            "SCM_REPO": "o/r",
            "SCM_TOKEN": "existing-token",
            "SLICE_HMAC_KEY": "secret",
            "SAMUEL_API_KEY": "dashboard-key",
        }.items():
            monkeypatch.setenv(key, value)
        server = create_server(
            bus, host="127.0.0.1", port=0, config={"agent.config_dir": str(tmp_path)}
        )
        with serving(server) as base:
            headers = {"X-API-Key": "dashboard-key", "Content-Type": "application/json"}
            path = base + "/api/v1/dashboard/webhook"
            for url in (path, path + "/read"):
                with pytest.raises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(
                        urllib.request.Request(url, data=b"{}" if url.endswith("read") else None)
                    )
                assert exc.value.code == 401
            response = json.load(
                urllib.request.urlopen(urllib.request.Request(path, headers=headers))
            )
            assert check(response, "hook_configuration")["state"] == "not_checked"
            assert calls == []
            response = json.load(
                urllib.request.urlopen(
                    urllib.request.Request(
                        path + "/read",
                        data=b'{"url":"https://untrusted.invalid","token":"other"}',
                        headers=headers,
                    )
                )
            )
            assert len(calls) == 1
            assert calls[0] == (
                "GET",
                "/api/v1/repos/o/r/hooks?limit=50&page=1",
                "token existing-token",
            )
            assert check(response, "native_delivery")["state"] == "not_proven"
            assert "private-secret" not in json.dumps(response)
            again = json.load(urllib.request.urlopen(urllib.request.Request(path, headers=headers)))
            assert again == response
            assert len(calls) == 1
            html = urllib.request.urlopen(base).read().decode()
            assert 'id="set-webhook"' in html and 'id="setup-webhook"' in html
    assert events == []
    commands.assert_not_called()
    bus.close()


@pytest.mark.parametrize("read,existing_failure", [(False, False), (True, False), (True, True)])
def test_doctor_diagnostics_do_not_change_exit_or_qualification(
    monkeypatch, tmp_path, capsys, read, existing_failure
):
    from samuel.cli import _cmd_doctor

    monkeypatch.setattr(
        "samuel.slices.setup.env_io.build_doctor_report",
        lambda *a, **kw: [
            {
                "name": "existing",
                "status": "fail" if existing_failure else "ok",
                "detail": "",
                "fix": "",
            }
        ],
    )
    monkeypatch.setattr("samuel.project_binding.configured_project_status", lambda *a: {})
    record = Mock()
    monkeypatch.setattr("samuel.cli._record_doctor_qualification", record)
    probe = Mock(return_value={"state": "restricted", "observed_at": timestamp(), "hooks": []})
    monkeypatch.setattr("samuel.webhook_probe.read_webhook_configuration", probe)
    assert _cmd_doctor(argparse.Namespace(config=str(tmp_path), webhook=read)) == int(
        existing_failure
    )
    assert probe.call_count == int(read)
    assert record.call_args.kwargs["summary"]["checks"] == 1
    output = capsys.readouterr().out
    assert "not_proven" in output and "ALLOWED_HOST_LIST" in output


def test_other_provider_and_new_process_do_not_reuse_signature_observation():
    observations = WebhookObservations()
    observations.record("signature", {"provider": "github", "result": "pass"})
    assert (
        check(
            build_webhook_report("gitea", True, observations=observations.snapshot()), "signature"
        )["state"]
        == "not_checked"
    )
    assert (
        check(
            build_webhook_report("github", True, observations=observations.snapshot()), "signature"
        )["state"]
        == "pass"
    )
    assert (
        check(
            build_webhook_report("github", True, observations=WebhookObservations().snapshot()),
            "signature",
        )["state"]
        == "not_checked"
    )


@pytest.mark.parametrize("provider", ["gitea", "github"])
def test_actual_client_never_forwards_credential_on_redirect(provider):
    calls = []

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/private-secret-target")
            self.end_headers()

        def log_message(self, *_args):
            pass

    with serving(ThreadingHTTPServer(("127.0.0.1", 0), Redirect)) as url:
        result = read_webhook_configuration(provider, url, "private-secret-token", "o/r")
    assert len(calls) == 1 and calls[0].startswith(
        "/api/v1/repos/o/r/hooks" if provider == "gitea" else "/api/v3/repos/o/r/hooks"
    )
    assert result["state"] == "unknown"
    assert result["permission_diagnostic"]["http_status"] == 302
    assert "private-secret" not in json.dumps(result)
