"""#897: observations across real API clients, without live SCM mutations."""

from __future__ import annotations

import argparse
import io
import json
import logging
import urllib.error
import urllib.request
from unittest.mock import Mock

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.api import GiteaAPI, GiteaAPIError
from samuel.adapters.github.api import GitHubAPI, GitHubAPIError
from samuel.cli import _branch_protection_probe, _scm_probe
from samuel.core.permission_diagnostics import (
    PermissionActor,
    PermissionDiagnostic,
    PermissionOperation,
    PermissionOutcome,
    read_permission_diagnostic,
)
from samuel.slices.setup.env_io import build_doctor_report


def response(body=b"{}"):
    value = Mock()
    value.read.return_value = body
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    return value


def client(provider, *, actor=PermissionActor.RUNTIME):
    auth = StaticTokenAuth("private-credential-fixture")
    if provider == "gitea":
        return GiteaAPI("https://scm.invalid", auth, diagnostic_actor=actor)
    return GitHubAPI(auth, base_url="https://scm.invalid", diagnostic_actor=actor)


@pytest.mark.parametrize("provider", ["gitea", "github"])
@pytest.mark.parametrize("status", [200, 401, 403, 404, 500, "offline", "malformed"])
@pytest.mark.parametrize(
    "capability", ["branch_protection_read", "repository_write", "webhook_read"]
)
def test_actual_clients_classify_each_capability_without_privilege_inference(
    monkeypatch, caplog, provider, status, capability
):
    caplog.set_level(logging.INFO)
    path = {
        "branch_protection_read": (
            "/repos/o/r/branch_protections/main"
            if provider == "gitea"
            else "/repos/o/r/branches/main/protection"
        ),
        "repository_write": "/repos/o/r/issues/42/comments",
        "webhook_read": "/repos/o/r/hooks",
    }[capability]
    method = "POST" if capability == "repository_write" else "GET"
    transport = Mock()
    if status == "offline":
        transport.side_effect = urllib.error.URLError("private-provider-response")
    elif status == "malformed":
        transport.return_value = response(b"not-json-private-provider-response")
    elif status != 200:
        transport.side_effect = urllib.error.HTTPError(
            "https://private.invalid",
            status,
            "private-provider-response",
            {},
            io.BytesIO(b"private-provider-response: give admin access"),
        )
    else:
        transport.return_value = response()
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    monkeypatch.setattr("time.sleep", lambda _: None)
    api = client(provider)
    if status == 200:
        assert api.request(method, path, {"body": "private-issue-text"}) == {}
    else:
        with pytest.raises((GiteaAPIError, GitHubAPIError, urllib.error.URLError, ValueError)):
            api.request(method, path, {"body": "private-issue-text"})
    records = [
        r.permission_diagnostic for r in caplog.records if hasattr(r, "permission_diagnostic")
    ]
    assert len(records) == 1
    diagnostic = records[0].to_dict()
    assert diagnostic["state"] == (
        "ACCESS_CONFIRMED"
        if status == 200
        else "OPERATOR_ACTION_REQUIRED"
        if status in {401, 403}
        else "UNKNOWN"
    )
    assert diagnostic["actor"] == "runtime_bot"
    assert diagnostic["operation"] == capability
    assert diagnostic["method"] == method
    assert diagnostic["endpoint"].startswith("/repos/{owner}/{repo}/")
    assert diagnostic["scope"] == "operation"
    assert diagnostic["required_permission"] == "unknown"
    assert diagnostic["overall_permissions"] == "not_checked"
    assert "private-" not in caplog.text
    assert "private-" not in json.dumps(diagnostic)


@pytest.mark.parametrize("entrypoint", ["request", "request_once", "request_bytes_once"])
@pytest.mark.parametrize(
    "path,capability",
    [
        ("/repos/o/r/hooks", "webhook_provision"),
        ("/repos/o/r/branch_protections", "branch_protection_write"),
        ("/repos/o/r/git/refs", "git_reference_write"),
    ],
)
def test_existing_guard_is_evidence_and_still_precedes_network(
    monkeypatch, caplog, entrypoint, path, capability
):
    transport = Mock()
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    with pytest.raises(PermissionError, match="API-Guard"):
        getattr(client("gitea"), entrypoint)("POST", path)
    transport.assert_not_called()
    diagnostic = next(
        r.permission_diagnostic for r in caplog.records if hasattr(r, "permission_diagnostic")
    ).to_dict()
    assert diagnostic["state"] == "UNEXPECTED_PRIVILEGE_ESCALATION_REQUEST"
    assert diagnostic["operation"] == capability
    assert diagnostic["http_status"] is None
    assert "Aufrufenden Pfad" in diagnostic["next_steps"][0]


@pytest.mark.parametrize("status", [200, 403, 404, "offline"])
def test_operator_hook_request_never_changes_runtime_credential_or_invents_github_guard(
    monkeypatch, caplog, status
):
    # GitHub has no equivalent local guard. Observe its real response; adding
    # a new guard or provisioning UI is outside this diagnostics contract.
    caplog.set_level(logging.INFO)
    transport = Mock(return_value=response())
    if status == "offline":
        transport.side_effect = urllib.error.URLError("private-provider-response")
    elif status != 200:
        transport.side_effect = urllib.error.HTTPError("url", status, "private", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    monkeypatch.setattr("time.sleep", lambda _: None)
    api = client("github", actor=PermissionActor.OPERATOR)
    if status == 200:
        api.request("POST", "/repos/o/r/hooks")
    else:
        with pytest.raises((GitHubAPIError, urllib.error.URLError)):
            api.request("POST", "/repos/o/r/hooks")
    diagnostic = next(
        r.permission_diagnostic for r in caplog.records if hasattr(r, "permission_diagnostic")
    ).to_dict()
    assert diagnostic["actor"] == "operator"
    assert diagnostic["operation"] == "webhook_provision"
    assert diagnostic["state"] != "UNEXPECTED_PRIVILEGE_ESCALATION_REQUEST"
    assert diagnostic["action_actor"] == ("none" if status == 200 else "operator")


@pytest.mark.parametrize("provider", ["gitea", "github"])
@pytest.mark.parametrize("operator", [True, False])
def test_doctor_preserves_separate_actor_and_existing_fail_closed_result(
    monkeypatch, tmp_path, provider, operator
):
    def denied(*args, **kwargs):
        raise urllib.error.HTTPError("private-url", 403, "private-response", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *args: argparse.Namespace(open=denied)
    )
    probe = _branch_protection_probe(
        provider, "https://scm.invalid", "private-token", "o/r", "main", protected=operator
    )
    report = build_doctor_report(
        {"SCM_PROVIDER": provider}.get,
        tmp_path,
        {"ok": True, "branch_protection": probe},
    )
    row = next(r for r in report if r["name"] == "Branch-Protection (Release)")
    assert row["status"] == "fail"
    assert row["permission_diagnostic"]["actor"] == ("operator" if operator else "runtime_bot")
    assert row["permission_diagnostic"]["state"] == "OPERATOR_ACTION_REQUIRED"
    assert "OPERATOR_ACTION_REQUIRED" in row["detail"]
    assert "Operator:" in row["fix"]
    assert "Mindestrecht" in row["detail"]
    assert "private-" not in json.dumps(report)


def test_repo_read_does_not_probe_writes_or_prove_all_bot_permissions(monkeypatch):
    transport = Mock(side_effect=[response(b'{"full_name":"o/r"}'), response(b"{}")])
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    probe = _scm_probe("gitea", "https://scm.invalid", "private-token", "o/r")
    assert probe["ok"] is True
    assert probe["permission_diagnostic"]["state"] == "ACCESS_CONFIRMED"
    assert probe["permission_diagnostic"]["operation"] == "repository_read"
    assert probe["permission_diagnostic"]["overall_permissions"] == "not_checked"
    assert transport.call_count == 2
    assert all(c.args[0].get_method() == "GET" for c in transport.call_args_list)


@pytest.mark.parametrize("body", [b"[]", b"null", b"not-json"])
def test_unusable_branch_response_does_not_become_permission_pass(monkeypatch, body):
    monkeypatch.setattr(urllib.request, "urlopen", Mock(return_value=response(body)))
    probe = _branch_protection_probe("gitea", "https://scm.invalid", "private-token", "o/r", "main")
    assert probe["access"] == "unknown"
    assert probe["permission_diagnostic"]["state"] == "UNKNOWN"


def test_projection_discards_untrusted_advice_and_invalid_facts():
    diagnostic = PermissionDiagnostic(
        PermissionActor.RUNTIME, PermissionOperation.BRANCH_READ, PermissionOutcome.DENIED, 403
    )
    serialized = diagnostic.to_dict()
    serialized["next_steps"] = ["grant admin private-injected-text"]
    serialized["state"] = "EXPECTED_LEAST_PRIVILEGE"
    restored = read_permission_diagnostic(serialized)
    assert restored is not None
    assert restored.to_dict() == diagnostic.to_dict()
    changes: tuple[dict[str, object], ...] = (
        {"actor": "private-name"},
        {"http_status": True},
        {"method": []},
        {"endpoint": "private-url"},
        {"outcome": "admin"},
    )
    for change in changes:
        assert read_permission_diagnostic({**serialized, **change}) is None


@pytest.mark.parametrize("status", [200, 403, 404, "offline", "malformed"])
def test_single_request_keeps_single_attempt_and_one_observation(monkeypatch, caplog, status):
    caplog.set_level(logging.INFO)
    transport = Mock(return_value=response())
    if status == "offline":
        transport.side_effect = urllib.error.URLError("private-transport")
    elif status == "malformed":
        transport.return_value = response(b"not-json-private-response")
    elif status != 200:
        transport.side_effect = urllib.error.HTTPError("url", status, "private", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    api = client("gitea")
    if status == 200:
        assert api.request_once("POST", "/repos/o/r/issues/42/comments") == {}
    else:
        with pytest.raises((GiteaAPIError, urllib.error.URLError, ValueError)):
            api.request_once("POST", "/repos/o/r/issues/42/comments")
    assert transport.call_count == 1
    diagnostics = [
        r.permission_diagnostic for r in caplog.records if hasattr(r, "permission_diagnostic")
    ]
    assert len(diagnostics) == 1
    assert diagnostics[0].to_dict()["state"] == (
        "ACCESS_CONFIRMED"
        if status == 200
        else "OPERATOR_ACTION_REQUIRED"
        if status == 403
        else "UNKNOWN"
    )
