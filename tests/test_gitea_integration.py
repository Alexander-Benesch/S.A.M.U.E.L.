"""Integration tests for GiteaAdapter against a real Gitea instance.

Skipped unless SCM_URL and SCM_TOKEN env vars are set.
Tries to load .env file if env vars are not already present.
Uses an existing issue (reads only, no writes) to avoid side effects.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.adapter import GiteaAdapter
from samuel.core.types import Comment, Issue
from samuel.slices.setup.env_io import parse_env


def _load_env_fallback() -> dict[str, str]:
    """Lese lokale Integrationseinstellungen ohne den Prozess zu veraendern."""
    values: dict[str, str] = {}
    for env_path in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
        if env_path.exists():
            values.update(parse_env(env_path.read_text(encoding="utf-8")))
            break
    return values


_INTEGRATION_ENV = _load_env_fallback()
_INTEGRATION_ENV.update(os.environ)

GITEA_URL = _INTEGRATION_ENV.get("SCM_URL", "") or _INTEGRATION_ENV.get("GITEA_URL", "")
GITEA_TOKEN = _INTEGRATION_ENV.get("SCM_TOKEN", "") or _INTEGRATION_ENV.get("GITEA_TOKEN", "")
GITEA_REPO = _INTEGRATION_ENV.get("SCM_REPO", "") or _INTEGRATION_ENV.get("GITEA_REPO", "")

skip_no_gitea = pytest.mark.skipif(
    not (GITEA_URL and GITEA_TOKEN and GITEA_REPO),
    reason="SCM_URL / SCM_TOKEN / SCM_REPO not set",
)


def test_env_fallback_does_not_mutate_process() -> None:
    before = os.environ.copy()
    _load_env_fallback()
    unchanged = os.environ == before
    assert unchanged


@pytest.fixture
def adapter():
    auth = StaticTokenAuth(GITEA_TOKEN)
    return GiteaAdapter(GITEA_URL, GITEA_REPO, auth)


@pytest.fixture
def existing_issue(adapter):
    """Read the configured repository; never provision a test subject."""
    issues = adapter.list_issues([])
    if not issues:
        pytest.skip("configured repository has no readable open issue")
    return issues[0]


@skip_no_gitea
class TestGiteaIntegration:
    def test_get_issue(self, adapter, existing_issue):
        issue = adapter.get_issue(existing_issue.number)
        assert isinstance(issue, Issue)
        assert issue.number == existing_issue.number
        assert isinstance(issue.title, str) and issue.title

    def test_get_comments(self, adapter, existing_issue):
        comments = adapter.get_comments(existing_issue.number)
        assert isinstance(comments, list)
        for c in comments:
            assert isinstance(c, Comment)

    def test_list_issues(self, adapter):
        issues = adapter.list_issues([])
        assert isinstance(issues, list)
        assert all(isinstance(i, Issue) for i in issues)

    def test_issue_url(self, adapter, existing_issue):
        url = adapter.issue_url(existing_issue.number)
        assert f"/issues/{existing_issue.number}" in url
        assert GITEA_URL in url

    def test_capabilities(self, adapter):
        assert "labels" in adapter.capabilities


def test_env_fallback_reuses_canonical_quoted_value_parser(tmp_path, monkeypatch) -> None:
    from samuel.slices.setup.env_io import merge_env

    monkeypatch.chdir(tmp_path)
    dummy = "fixture's quoted value with spaces"
    (tmp_path / ".env").write_text(merge_env("", {"SCM_TOKEN": dummy}), encoding="utf-8")
    before = dict(os.environ)
    observed = _load_env_fallback()
    unchanged = dict(os.environ) == before
    assert unchanged
    assert observed["SCM_TOKEN"] == dummy


def test_empty_scm_fixture_stays_unavailable_without_provisioning() -> None:
    class ReadOnlySCM:
        def list_issues(self, labels):
            assert labels == []
            return []

    with pytest.raises(pytest.skip.Exception, match="no readable open issue"):
        existing_issue.__wrapped__(ReadOnlySCM())
