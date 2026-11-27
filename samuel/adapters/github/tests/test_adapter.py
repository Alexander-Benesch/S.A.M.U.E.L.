from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from samuel.adapters.github.adapter import GitHubAdapter, normalize_github_api_url
from samuel.adapters.github.api import GitHubAPIError
from samuel.adapters.github.auth import GitHubAppAuth, GitHubTokenAuth
from samuel.core.evaluation_subject import RevisionComparison
from samuel.core.ports import IAuthProvider
from samuel.core.types import PR, Issue


def _generate_rsa_pem() -> str:
    """Generate a test RSA private key in PEM format."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    except ImportError:
        return ""


class MockAuth(IAuthProvider):
    def get_token(self) -> str:
        return "ghp_test_token"

    def is_valid(self) -> bool:
        return True

    def refresh(self) -> None:
        pass


def _make_adapter(responses: list[dict | list | None]) -> tuple[GitHubAdapter, MagicMock]:
    auth = MockAuth()
    adapter = GitHubAdapter("owner/repo", auth, base_url="https://api.github.com")

    call_count = 0

    def mock_request(method: str, path: str, data: dict | None = None) -> Any:
        nonlocal call_count
        if call_count < len(responses):
            resp = responses[call_count]
            call_count += 1
            return resp
        return None

    adapter._api.request = MagicMock(side_effect=mock_request)
    return adapter, adapter._api.request


class TestGitHubAdapter:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://github.com", "https://api.github.com"),
            ("https://api.github.com", "https://api.github.com"),
            ("https://git.example.test", "https://git.example.test/api/v3"),
            ("https://git.example.test/api/v3", "https://git.example.test/api/v3"),
        ],
    )
    def test_normalizes_api_url(self, value, expected):
        assert normalize_github_api_url(value) == expected

    def test_capabilities(self):
        adapter = GitHubAdapter("o/r", MockAuth())
        caps = adapter.capabilities
        assert "labels" in caps
        assert "webhooks_full" in caps
        assert "checks" in caps
        assert "immutable_revisions" in caps

    def test_resolves_ref_to_full_commit(self):
        adapter, request = _make_adapter([{"sha": "A" * 40}])

        resolved = adapter.resolve_ref("feature/a b")

        assert resolved == "a" * 40
        request.assert_called_once_with("GET", "/repos/owner/repo/commits/feature%2Fa%20b")
        assert adapter.repository_identity == "https://github.com/owner/repo"

    def test_reads_exact_pull_request_revision(self):
        adapter, _ = _make_adapter([{"base": {"sha": "a" * 40}, "head": {"sha": "b" * 40}}])

        revision = adapter.get_pr_revision(17)

        assert revision.repository == adapter.repository_identity
        assert revision.base_sha == "a" * 40
        assert revision.head_sha == "b" * 40

    def test_resume_lookup_by_number_and_bound_marker(self):
        row = {
            "id": 5,
            "number": 10,
            "title": "Resume",
            "html_url": "https://github.com/owner/repo/pull/10",
            "body": "<!-- samuel-intent:create_pr:sha256:abc -->",
            "head": {"ref": "feature/resume", "sha": "b" * 40},
            "base": {"ref": "main", "sha": "a" * 40},
        }
        adapter, request = _make_adapter([row, [row]])

        by_number = adapter.get_pr(10)
        by_marker = adapter.find_pr_by_marker(
            "samuel-intent:create_pr:sha256:abc",
            head="feature/resume",
            base="main",
        )

        assert by_number.number == 10
        assert by_marker is not None and by_marker.number == 10
        assert request.call_args_list[1].args == (
            "GET",
            "/repos/owner/repo/pulls?state=all&per_page=100&page=1",
        )

    def test_optional_ref_returns_none_only_for_confirmed_404(self):
        adapter, _ = _make_adapter([])
        adapter._api.request = MagicMock(side_effect=GitHubAPIError(404, "GET", "/missing"))
        assert adapter.resolve_ref_optional("missing") is None

        adapter._api.request = MagicMock(side_effect=GitHubAPIError(503, "GET", "/unknown"))
        with pytest.raises(GitHubAPIError):
            adapter.resolve_ref_optional("unknown")

    def test_compare_delegates_the_exact_commit_pair(self):
        adapter, _ = _make_adapter([])
        expected = RevisionComparison(
            repository=adapter.repository_identity,
            base_sha="a" * 40,
            head_sha="b" * 40,
            changed_files=("one.py",),
            diff="+one",
            diff_bytes=4,
        )
        with patch(
            "samuel.adapters.github.adapter.compare_local_commits", return_value=expected
        ) as compare:
            actual = adapter.compare_commits("a" * 40, "b" * 40, max_diff_bytes=4096)

        assert actual is expected
        compare.assert_called_once_with(
            project_root=None,
            repository=adapter.repository_identity,
            base_sha="a" * 40,
            head_sha="b" * 40,
            max_diff_bytes=4096,
        )

    def test_get_issue(self):
        adapter, mock = _make_adapter(
            [
                {
                    "number": 42,
                    "title": "Test issue",
                    "body": "Body text",
                    "state": "open",
                    "labels": [{"id": 1, "name": "bug"}],
                }
            ]
        )

        issue = adapter.get_issue(42)

        assert isinstance(issue, Issue)
        assert issue.number == 42
        assert issue.title == "Test issue"
        assert len(issue.labels) == 1
        assert issue.labels[0].name == "bug"
        mock.assert_called_once_with("GET", "/repos/owner/repo/issues/42")

    def test_get_comments(self):
        adapter, mock = _make_adapter(
            [
                [
                    {
                        "id": 1,
                        "body": "First",
                        "user": {"login": "alice"},
                        "created_at": "2026-01-01",
                    },
                    {
                        "id": 2,
                        "body": "Second",
                        "user": {"login": "bob"},
                        "created_at": "2026-01-02",
                    },
                ]
            ]
        )

        comments = adapter.get_comments(10)

        assert len(comments) == 2
        assert comments[0].user == "alice"
        assert comments[1].body == "Second"

    def test_get_label_events_preserves_human_actor_and_time(self):
        adapter, _mock = _make_adapter(
            [
                [
                    {
                        "id": 91,
                        "event": "labeled",
                        "created_at": "2026-09-17T10:00:00Z",
                        "actor": {"login": "alice", "type": "User"},
                        "label": {"name": "status:approved"},
                    }
                ]
            ]
        )

        events = adapter.get_label_events(10, "status:approved")

        assert len(events) == 1
        assert events[0].source_id == "github-event:91"
        assert events[0].actor_type == "human"

    def test_post_comment(self):
        adapter, mock = _make_adapter(
            [
                {
                    "id": 99,
                    "body": "My comment",
                    "user": {"login": "bot"},
                    "created_at": "2026-01-01",
                },
            ]
        )

        comment = adapter.post_comment(10, "My comment")

        assert comment.id == 99
        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/issues/10/comments",
            {"body": "My comment"},
        )

    def test_create_pr(self):
        adapter, mock = _make_adapter(
            [
                {
                    "id": 5,
                    "number": 100,
                    "title": "New PR",
                    "html_url": "https://github.com/owner/repo/pull/100",
                    "state": "open",
                    "merged": False,
                }
            ]
        )

        pr = adapter.create_pr("feature", "main", "New PR", "Description")

        assert isinstance(pr, PR)
        assert pr.number == 100
        assert pr.html_url == "https://github.com/owner/repo/pull/100"

    def test_list_issues_filters_prs(self):
        adapter, mock = _make_adapter(
            [
                [
                    {"number": 1, "title": "Issue", "state": "open", "labels": []},
                    {
                        "number": 2,
                        "title": "PR as issue",
                        "state": "open",
                        "labels": [],
                        "pull_request": {"url": "..."},
                    },
                ]
            ]
        )

        issues = adapter.list_issues([])

        assert len(issues) == 1
        assert issues[0].number == 1

    def test_close_issue(self):
        adapter, mock = _make_adapter([None])
        adapter.close_issue(42)
        mock.assert_called_once_with("PATCH", "/repos/owner/repo/issues/42", {"state": "closed"})

    def test_merge_pr(self):
        adapter, mock = _make_adapter([None])
        result = adapter.merge_pr(100)
        assert result is True
        mock.assert_called_once_with(
            "PUT", "/repos/owner/repo/pulls/100/merge", {"merge_method": "merge"}
        )

    def test_issue_url_github_com(self):
        adapter = GitHubAdapter("owner/repo", MockAuth())
        assert adapter.issue_url(42) == "https://github.com/owner/repo/issues/42"

    def test_pr_url_github_com(self):
        adapter = GitHubAdapter("owner/repo", MockAuth())
        assert adapter.pr_url(10) == "https://github.com/owner/repo/pull/10"

    def test_branch_url(self):
        adapter = GitHubAdapter("owner/repo", MockAuth())
        assert adapter.branch_url("feat/x") == "https://github.com/owner/repo/tree/feat/x"

    def test_swap_label(self):
        adapter, mock = _make_adapter([None, None])
        adapter.swap_label(5, "old-label", "new-label")
        assert mock.call_count == 2

    def test_list_labels(self):
        adapter, mock = _make_adapter(
            [
                [
                    {"id": 1, "name": "bug", "color": "ff0000", "description": "a bug"},
                    {"id": 2, "name": "docs", "color": "00ff00", "description": None},
                ]
            ]
        )
        labels = adapter.list_labels()
        assert len(labels) == 2
        assert labels[0]["name"] == "bug"
        assert labels[1]["description"] == ""
        mock.assert_called_once_with("GET", "/repos/owner/repo/labels?per_page=100")

    def test_create_label(self):
        adapter, mock = _make_adapter(
            [
                {
                    "id": 99,
                    "name": "new-label",
                    "color": "abcdef",
                    "description": "x",
                }
            ]
        )
        result = adapter.create_label("new-label", "abcdef", "x")
        assert result["name"] == "new-label"
        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/labels",
            {"name": "new-label", "color": "abcdef", "description": "x"},
        )


class TestGitHubTokenAuth:
    def test_token_auth(self):
        auth = GitHubTokenAuth("ghp_abc123")
        assert auth.get_token() == "ghp_abc123"
        assert auth.is_valid() is True
        auth.refresh()

    def test_empty_token_invalid(self):
        auth = GitHubTokenAuth("")
        assert auth.is_valid() is False


class TestGitHubAppAuth:
    def test_creates_jwt(self):
        pem = _generate_rsa_pem()
        if not pem:
            pytest.skip("cryptography package not installed")
        auth = GitHubAppAuth("12345", pem, "67890")
        jwt = auth._create_jwt()
        parts = jwt.split(".")
        assert len(parts) == 3

    def test_token_refresh_needed_initially(self):
        auth = GitHubAppAuth("12345", "secret-key", "67890")
        assert auth.is_valid() is False


class TestGetBranchProtection:
    def test_returns_rules_when_protected(self):
        rules = {
            "url": "https://api.github.com/repos/owner/repo/branches/main/protection",
            "required_pull_request_reviews": {"required_approving_review_count": 2},
            "enforce_admins": {"enabled": True},
        }
        adapter, mock = _make_adapter([rules])

        result = adapter.get_branch_protection("main")

        mock.assert_called_once_with(
            "GET",
            "/repos/owner/repo/branches/main/protection",
        )
        assert result == {"branch": "main", "rules": rules}

    def test_returns_none_for_404(self):
        auth = MockAuth()
        adapter = GitHubAdapter("owner/repo", auth)
        err = GitHubAPIError(404, "GET", "/repos/owner/repo/branches/main/protection")
        adapter._api.request = MagicMock(side_effect=err)

        assert adapter.get_branch_protection("main") is None

    def test_returns_none_when_payload_empty(self):
        adapter, _ = _make_adapter([None])

        assert adapter.get_branch_protection("main") is None

    def test_propagates_non_404_errors(self):
        auth = MockAuth()
        adapter = GitHubAdapter("owner/repo", auth)
        err = GitHubAPIError(500, "GET", "/repos/owner/repo/branches/main/protection")
        adapter._api.request = MagicMock(side_effect=err)

        with pytest.raises(GitHubAPIError):
            adapter.get_branch_protection("main")

    def test_capability_advertised(self):
        adapter = GitHubAdapter("owner/repo", MockAuth())
        assert "branch_protection" in adapter.capabilities


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://api.github.com", "https://github.com/owner/repo"),
        (
            "https://api.github.com.attacker.example",
            "https://api.github.com.attacker.example/owner/repo",
        ),
        (
            "https://enterprise.example/api.github.com",
            "https://enterprise.example/api.github.com/owner/repo",
        ),
        (
            "https://enterprise.example/api/team/api/v3",
            "https://enterprise.example/api/team/owner/repo",
        ),
    ],
)
def test_repository_identity_preserves_exact_enterprise_origin(url, expected):
    adapter = GitHubAdapter("owner/repo", MockAuth(), base_url=url)
    assert adapter.repository_identity == expected
