from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from unittest.mock import Mock

import pytest

from samuel.cli import (
    _branch_protection_probe,
    _build_parser,
    _cmd_doctor,
    _read_protected_secret_file,
    _scm_probe,
)
from samuel.slices.setup.env_io import github_release_policy_deviations


def response(data):
    value = Mock()
    value.read.return_value = json.dumps(data).encode()
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    return value


@pytest.mark.parametrize(
    "provider,base,path",
    [
        (
            "gitea",
            "https://scm.invalid",
            "/api/v1/repos/o/r/branch_protections/feature%2Fprotected",
        ),
        ("github", "https://github.com", "/repos/o/r/branches/feature%2Fprotected/protection"),
        (
            "github",
            "https://enterprise.invalid",
            "/api/v3/repos/o/r/branches/feature%2Fprotected/protection",
        ),
    ],
)
def test_separate_token_is_only_sent_to_branch_get(monkeypatch, provider, base, path):
    normal = []
    protected = []

    def repo(req, **_kwargs):
        normal.append(req)
        return response({"full_name": "o/r", "default_branch": "feature/protected"})

    def branch(req, **_kwargs):
        protected.append(req)
        return response({"branch_name": "feature/protected"})

    monkeypatch.setattr(urllib.request, "urlopen", repo)
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *args: argparse.Namespace(open=branch)
    )
    before = dict(os.environ)
    result = _scm_probe(
        provider, base, "normal-runtime", "o/r", branch_protection_token="temporary-read"
    )
    assert result["ok"] and result["branch_protection"]["access"] == "ok"
    assert len(normal) == len(protected) == 1
    assert normal[0].headers["Authorization"] == "token normal-runtime"
    assert protected[0].headers["Authorization"].endswith(" temporary-read")
    assert protected[0].full_url.endswith(path)
    assert protected[0].get_method() == "GET"
    assert os.environ == before
    assert "temporary-read" not in json.dumps(result)


def test_temporary_branch_credential_never_follows_redirect_to_another_endpoint():
    # Exercise urllib's actual redirect handling, with an in-memory HTTP handler.
    requests = []

    class Redirect(urllib.request.HTTPHandler):
        def http_open(self, req):
            import email.message
            import io

            requests.append(req.full_url)
            headers = email.message.Message()
            headers["Location"] = "http://other.invalid/token-sink"
            return urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, code=302)

    original = urllib.request.build_opener
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            urllib.request, "build_opener", lambda *handlers: original(Redirect(), *handlers)
        )
        result = _branch_protection_probe(
            "gitea", "http://scm.invalid", "temporary-read", "o/r", "main", protected=True
        )
    assert result["access"] == "unknown"
    assert requests == ["http://scm.invalid/api/v1/repos/o/r/branch_protections/main"]


@pytest.mark.parametrize("code", [401, 403, 404, 500])
def test_branch_error_does_not_expose_secret(monkeypatch, code):
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://temporary-read.invalid", code, "temporary-read", {}, None
        )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: argparse.Namespace(open=fail))
    result = _branch_protection_probe(
        "github", "https://github.com", "temporary-read", "o/r", "main", protected=True
    )
    assert "temporary-read" not in json.dumps(result)
    assert result["access"] == ("restricted" if code == 403 else "ok" if code == 404 else "unknown")


@pytest.mark.parametrize("unsafe", ["permissions", "symlink", "empty", "fifo", "oversize"])
def test_protected_file_fails_closed(tmp_path, unsafe):
    path = tmp_path / "token"
    if unsafe == "symlink":
        path.symlink_to(tmp_path / "elsewhere")
    elif unsafe == "fifo":
        os.mkfifo(path, 0o600)
    else:
        path.write_text(
            "" if unsafe == "empty" else "x" * 4097 if unsafe == "oversize" else "temporary-read"
        )
        path.chmod(0o644 if unsafe == "permissions" else 0o600)
    with pytest.raises(ValueError):
        _read_protected_secret_file(str(path), "branch protection token")


def test_doctor_parser_and_invalid_file_never_use_runtime_token(tmp_path, capsys, monkeypatch):
    path = tmp_path / "token"
    path.write_text("temporary-read")
    path.chmod(0o644)
    args = _build_parser().parse_args(
        ["--config", str(tmp_path), "doctor", "--branch-protection-token-file", str(path)]
    )
    probe = Mock()
    monkeypatch.setattr("samuel.cli._scm_probe", probe)
    assert _cmd_doctor(args) == 1
    probe.assert_not_called()
    assert "temporary-read" not in capsys.readouterr().err


def github_rules():
    return {
        "required_status_checks": {"contexts": ["CI / lint-and-test (pull_request)"], "checks": []},
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "bypass_pull_request_allowances": {"users": [], "teams": [], "apps": []},
        },
    }


def test_github_native_policy_checks_actual_rules():
    rules = github_rules()
    assert not github_release_policy_deviations(
        rules, required_context="CI / lint-and-test (pull_request)"
    )
    rules["required_pull_request_reviews"]["bypass_pull_request_allowances"]["apps"] = [
        "bypass-bot"
    ]
    assert github_release_policy_deviations(
        rules, required_context="CI / lint-and-test (pull_request)"
    )


@pytest.mark.parametrize("rules", [{}, {"required_status_checks": True}, {"enforce_admins": []}])
def test_github_malformed_or_absent_rule_is_not_pass(rules):
    assert github_release_policy_deviations(rules, required_context="CI")
