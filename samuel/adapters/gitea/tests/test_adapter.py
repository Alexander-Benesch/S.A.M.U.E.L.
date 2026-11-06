from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.adapter import GiteaAdapter
from samuel.adapters.gitea.api import GiteaAPIError
from samuel.core.evaluation_subject import RevisionComparison
from samuel.core.external_evidence import SCMCheckReference
from samuel.core.ports import ISCMCheckEvidenceReader, IVersionControl
from samuel.core.types import PR, Comment, Issue, Label


@pytest.fixture
def auth():
    return StaticTokenAuth("test-token")


@pytest.fixture
def adapter(auth):
    return GiteaAdapter("http://gitea.local", "owner/repo", auth)


ISSUE_DATA = {
    "number": 42,
    "title": "Test issue",
    "body": "Some body",
    "state": "open",
    "labels": [{"id": 1, "name": "bug"}],
}

COMMENT_DATA = {
    "id": 100,
    "body": "A comment",
    "user": {"login": "bot"},
    "created_at": "2026-01-01T00:00:00Z",
}

PR_DATA = {
    "id": 5,
    "number": 10,
    "title": "My PR",
    "html_url": "http://gitea.local/owner/repo/pulls/10",
    "state": "open",
    "merged": False,
}

LABELS_DATA = [
    {"id": 1, "name": "bug"},
    {"id": 2, "name": "in-progress"},
    {"id": 3, "name": "done"},
]


class TestGiteaAdapterInterface:
    def test_implements_iversioncontrol(self, adapter):
        assert isinstance(adapter, IVersionControl)
        assert isinstance(adapter, ISCMCheckEvidenceReader)

    def test_capabilities(self, adapter):
        assert adapter.capabilities == {
            "labels",
            "webhooks_basic",
            "branch_protection",
            "activity_polling",
            "immutable_revisions",
            "native_expected_head_merge",
            "label_events",
            "scm_check_evidence_advisory",
        }

    def test_reads_narrow_actions_evidence_without_logs(self, adapter):
        run = {
            "id": 704,
            "run_attempt": 1,
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "b" * 40,
            "head_branch": None,
            "path": "ci.yml@refs/pull/7/head",
            "started_at": "2026-09-18T09:59:00Z",
            "completed_at": "2026-09-18T10:00:00Z",
            "pull_requests": [
                {
                    "number": 7,
                    "base": {"sha": "a" * 40},
                    "head": {"sha": "b" * 40},
                }
            ],
            "html_url": "http://gitea.local/owner/repo/actions/runs/704",
            "future_field": {"raw": "not retained"},
        }
        jobs = {
            "jobs": [
                {
                    "id": 9,
                    "name": "tests",
                    "status": "completed",
                    "conclusion": "success",
                    "runner_id": 2,
                    "runner_name": "runner",
                    "runner_labels": None,
                    "started_at": "2026-09-18T09:59:00Z",
                    "completed_at": "2026-09-18T10:00:00Z",
                    "html_url": "http://gitea.local/owner/repo/actions/runs/704/jobs/9",
                    "logs": "must not be retained",
                }
            ]
        }
        statuses = [
            {
                "id": 11,
                "context": "CI / tests (pull_request)",
                "status": "success",
                "target_url": "/owner/repo/actions/runs/704/jobs/9",
                "creator": None,
                "created_at": "2026-09-18T10:00:00Z",
                "updated_at": "2026-09-18T10:00:00Z",
                "description": "not retained",
            }
        ]
        workflow = {"sha": "e" * 40, "content": "must not be retained"}
        with patch.object(
            adapter._api,
            "request",
            side_effect=[run, jobs, statuses, workflow],
        ) as request:
            observation = adapter.read_check_evidence(
                SCMCheckReference(provider="gitea", repository="owner/repo", run_id=704)
            )

        assert observation.workflow_path == ".gitea/workflows/ci.yml"
        assert observation.workflow_blob_sha == "e" * 40
        assert observation.reported_attempt == 1
        assert observation.pull_request_number == 7
        assert observation.pull_request_base_sha == "a" * 40
        assert observation.pull_request_head_sha == "b" * 40
        assert observation.started_at == "2026-09-18T09:59:00Z"
        assert observation.completed_at == "2026-09-18T10:00:00Z"
        assert observation.missing_facts == ("runner_labels",)
        assert observation.unknown_fields == ("future_field",)
        assert "must not be retained" not in str(observation.as_dict())
        assert request.call_args_list[-1].args == (
            "GET",
            f"/repos/owner/repo/contents/.gitea/workflows/ci.yml?ref={'b' * 40}",
        )

    def test_rejects_wrong_provider_repository_and_run_identity(self, adapter):
        with pytest.raises(ValueError, match="provider=gitea"):
            adapter.read_check_evidence(
                SCMCheckReference(provider="github", repository="owner/repo", run_id=704)
            )
        with pytest.raises(ValueError, match="configured repository"):
            adapter.read_check_evidence(
                SCMCheckReference(provider="gitea", repository="other/repo", run_id=704)
            )
        with (
            patch.object(adapter._api, "request", return_value={"id": 705}),
            pytest.raises(ValueError, match="different run"),
        ):
            adapter.read_check_evidence(
                SCMCheckReference(provider="gitea", repository="owner/repo", run_id=704)
            )

    def test_rejects_malformed_job_and_pull_request_payloads(self, adapter):
        run = {
            "id": 704,
            "run_attempt": 1,
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "b" * 40,
            "path": "ci.yml@refs/pull/7/head",
            "pull_requests": [{"number": 7, "base": {}, "head": {}}],
        }
        with (
            patch.object(adapter._api, "request", side_effect=[run, {"jobs": {}}]),
            pytest.raises(ValueError, match="jobs response has invalid shape"),
        ):
            adapter.read_check_evidence(
                SCMCheckReference(provider="gitea", repository="owner/repo", run_id=704)
            )

    def test_rejects_untrusted_head_and_workflow_path_before_content_read(self, adapter):
        with (
            patch.object(
                adapter._api,
                "request",
                return_value={"id": 704, "head_sha": "../../branch"},
            ) as request,
            pytest.raises(ValueError, match="invalid head_sha"),
        ):
            adapter.read_check_evidence(
                SCMCheckReference(provider="gitea", repository="owner/repo", run_id=704)
            )
        assert request.call_count == 1

        run = {
            "id": 704,
            "run_attempt": 1,
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "b" * 40,
            "path": "../private.yml@refs/heads/main",
        }
        with (
            patch.object(
                adapter._api,
                "request",
                side_effect=[run, {"jobs": []}, []],
            ) as request,
            pytest.raises(ValueError, match="workflow path is invalid"),
        ):
            adapter.read_check_evidence(
                SCMCheckReference(provider="gitea", repository="owner/repo", run_id=704)
            )
        assert request.call_count == 3

        with (
            patch.object(
                adapter._api,
                "request",
                side_effect=[
                    {
                        **run,
                        "event": "pull_request",
                        "path": "ci.yml@refs/pull/7/head",
                        "pull_requests": ["invalid"],
                    },
                    {"jobs": []},
                    [],
                    {"sha": "e" * 40},
                ],
            ),
            pytest.raises(ValueError, match="pull-request reference has invalid shape"),
        ):
            adapter.read_check_evidence(
                SCMCheckReference(provider="gitea", repository="owner/repo", run_id=704)
            )

    def test_resolves_ref_to_full_commit(self, adapter):
        with patch.object(adapter._api, "request", return_value={"sha": "A" * 40}) as request:
            resolved = adapter.resolve_ref("feature/a b")

        assert resolved == "a" * 40
        request.assert_called_once_with("GET", "/repos/owner/repo/git/commits/feature%2Fa%20b")
        assert adapter.repository_identity == "http://gitea.local/owner/repo"

    def test_reads_exact_pull_request_revision(self, adapter):
        response = {"base": {"sha": "a" * 40}, "head": {"sha": "b" * 40}}
        with patch.object(adapter._api, "request", return_value=response):
            revision = adapter.get_pr_revision(17)

        assert revision.repository == adapter.repository_identity
        assert revision.base_sha == "a" * 40
        assert revision.head_sha == "b" * 40

    def test_resume_lookup_by_number_and_bound_marker(self, adapter):
        row = {
            **PR_DATA,
            "body": "before\n<!-- samuel-intent:create_pr:sha256:abc -->\nafter",
            "head": {"ref": "feature/resume", "sha": "b" * 40},
            "base": {"ref": "main", "sha": "a" * 40},
        }
        with patch.object(adapter._api, "request", side_effect=[row, [row]]) as request:
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
            "/repos/owner/repo/pulls?state=all&limit=50&page=1",
        )

    def test_optional_ref_returns_none_only_for_confirmed_404(self, adapter):
        with patch.object(
            adapter._api,
            "request",
            side_effect=GiteaAPIError(404, "GET", "/missing"),
        ):
            assert adapter.resolve_ref_optional("missing") is None

        with (
            patch.object(
                adapter._api,
                "request",
                side_effect=GiteaAPIError(503, "GET", "/unknown"),
            ),
            pytest.raises(GiteaAPIError),
        ):
            adapter.resolve_ref_optional("unknown")

    def test_compare_delegates_the_exact_commit_pair(self, adapter):
        expected = RevisionComparison(
            repository=adapter.repository_identity,
            base_sha="a" * 40,
            head_sha="b" * 40,
            changed_files=("one.py",),
            diff="+one",
            diff_bytes=4,
        )
        with patch(
            "samuel.adapters.gitea.adapter.compare_local_commits", return_value=expected
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


class TestGetIssue:
    def test_returns_issue(self, adapter):
        with patch.object(adapter._api, "request", return_value=ISSUE_DATA):
            issue = adapter.get_issue(42)
        assert isinstance(issue, Issue)
        assert issue.number == 42
        assert issue.title == "Test issue"
        assert issue.labels == [Label(id=1, name="bug")]


class TestGetComments:
    def test_returns_comments(self, adapter):
        with patch.object(adapter._api, "request", return_value=[COMMENT_DATA]):
            comments = adapter.get_comments(42)
        assert len(comments) == 1
        assert isinstance(comments[0], Comment)
        assert comments[0].user == "bot"

    def test_empty_comments(self, adapter):
        with patch.object(adapter._api, "request", return_value=[]):
            comments = adapter.get_comments(42)
        assert comments == []

    def test_label_events_preserve_actor_time_and_source(self, adapter):
        rows = [
            {
                "id": 81,
                "type": "label",
                "created_at": "2026-09-17T10:00:00Z",
                "user": {"login": "alice"},
                "label": {"name": "status:approved"},
            },
            {
                "id": 82,
                "type": "label",
                "created_at": "2026-09-17T10:01:00Z",
                "user": {"login": "bot"},
                "label": {"name": "other"},
            },
        ]
        with patch.object(adapter._api, "request", return_value=rows):
            events = adapter.get_label_events(42, "status:approved")

        assert len(events) == 1
        assert events[0].source_id == "gitea-timeline:81"
        assert events[0].actor == "alice"
        assert events[0].timestamp == "2026-09-17T10:00:00Z"

    def test_empty_label_filter_returns_all_add_remove_transitions(self, adapter):
        rows = [
            {
                "id": 81,
                "type": "label",
                "created_at": "2026-09-17T10:00:00Z",
                "user": {"login": "alice"},
                "label": {"name": "status:approved"},
            },
            {
                "id": 82,
                "type": "label",
                "created_at": "2026-09-17T10:01:00Z",
                "user": {"login": "alice"},
                "label": {"name": "status:approved"},
                "removed": True,
            },
            {
                "id": 83,
                "type": "label",
                "created_at": "2026-09-17T10:02:00Z",
                "user": {"login": "alice"},
                "label": {"name": "risk:low"},
            },
        ]
        with patch.object(adapter._api, "request", return_value=rows):
            events = adapter.get_label_events(42, "")

        assert [(event.label, event.operation) for event in events] == [
            ("status:approved", "add"),
            ("status:approved", "remove"),
            ("risk:low", "add"),
        ]


class TestPostComment:
    def test_posts_and_returns(self, adapter):
        with patch.object(adapter._api, "request", return_value=COMMENT_DATA) as mock:
            comment = adapter.post_comment(42, "Hello")
        mock.assert_called_once_with(
            "POST", "/repos/owner/repo/issues/42/comments", {"body": "Hello"}
        )
        assert isinstance(comment, Comment)
        assert comment.body == "A comment"


class TestCreatePR:
    def test_creates_pr(self, adapter):
        with patch.object(adapter._api, "request", return_value=PR_DATA) as mock:
            pr = adapter.create_pr("feature", "main", "My PR", "Description")
        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/pulls",
            {"title": "My PR", "body": "Description", "head": "feature", "base": "main"},
        )
        assert isinstance(pr, PR)
        assert pr.html_url == "http://gitea.local/owner/repo/pulls/10"


class TestSwapLabel:
    def test_removes_then_adds(self, adapter):
        calls = []

        def mock_request(method, path, data=None):
            calls.append((method, path, data))
            if path.endswith("/labels") and method == "GET":
                return LABELS_DATA
            return None

        with patch.object(adapter._api, "request", side_effect=mock_request):
            adapter.swap_label(42, "bug", "done")

        assert calls[0] == ("GET", "/repos/owner/repo/labels", None)
        assert calls[1] == ("DELETE", "/repos/owner/repo/issues/42/labels/1", None)
        assert calls[2] == (
            "POST",
            "/repos/owner/repo/issues/42/labels",
            {"labels": [3]},
        )


class TestListLabels:
    def test_returns_labels(self, adapter):
        with patch.object(
            adapter._api,
            "request",
            return_value=[
                {"id": 1, "name": "bug", "color": "ff0000", "description": "buggy"},
                {"id": 2, "name": "docs", "color": "00ff00"},
            ],
        ):
            labels = adapter.list_labels()
        assert len(labels) == 2
        assert labels[0] == {"id": 1, "name": "bug", "color": "ff0000", "description": "buggy"}
        assert labels[1]["description"] == ""


class TestCreateLabel:
    def test_creates_and_invalidates_cache(self, adapter):
        adapter._label_cache = {"existing": 1}
        with patch.object(
            adapter._api,
            "request",
            return_value={
                "id": 99,
                "name": "new-label",
                "color": "abcdef",
                "description": "x",
            },
        ) as mock:
            result = adapter.create_label("new-label", "abcdef", "x")

        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/labels",
            {"name": "new-label", "color": "abcdef", "description": "x"},
        )
        assert result == {"id": 99, "name": "new-label", "color": "abcdef", "description": "x"}
        assert adapter._label_cache is None


class TestListIssues:
    def test_returns_issues(self, adapter):
        with patch.object(adapter._api, "request", return_value=[ISSUE_DATA]):
            issues = adapter.list_issues(["bug"])
        assert len(issues) == 1
        assert issues[0].number == 42


class TestListSCMActivity:
    def test_normalizes_open_close_merge_and_comment(self, auth):
        adapter = GiteaAdapter(
            "http://gitea.local",
            "owner/repo",
            auth,
            bot_user="samuel-bot",
        )
        issue = {
            "number": 42,
            "title": "Issue",
            "html_url": "http://gitea.local/owner/repo/issues/42",
            "created_at": "2026-08-20T20:00:00Z",
            "closed_at": "2026-08-21T01:00:00Z",
            "user": {"login": "alice"},
        }
        pull = {
            "number": 10,
            "title": "PR",
            "html_url": "http://gitea.local/owner/repo/pulls/10",
            "created_at": "2026-08-21T02:00:00Z",
            "closed_at": "2026-08-21T03:00:00Z",
            "user": {"login": "alice"},
            "pull_request": {
                "merged": True,
                "merged_at": "2026-08-21T03:00:00Z",
            },
        }
        comment = {
            "id": 100,
            "issue_url": "http://gitea.local/owner/repo/issues/42",
            "created_at": "2026-08-21T01:30:00Z",
            "user": {"login": "carol"},
        }

        def request(method, path, data=None):
            assert method == "GET" and data is None
            if "type=issues" in path:
                return [issue]
            if "type=pulls" in path:
                return [pull]
            if path.endswith("/issues/comments?since=2026-08-21T00%3A00%3A00Z&limit=50&page=1"):
                return [comment]
            if path.endswith("/issues/42/timeline?since=2026-08-21T00%3A00%3A00Z&limit=50"):
                return [
                    {
                        "type": "close",
                        "created_at": "2026-08-21T01:00:00Z",
                        "user": {"login": "bob"},
                    }
                ]
            if path.endswith("/pulls/10"):
                return {"merged_by": {"login": "samuel-bot"}, "html_url": pull["html_url"]}
            raise AssertionError(path)

        with patch.object(adapter._api, "request", side_effect=request):
            rows = adapter.list_scm_activity("2026-08-21T00:00:00Z", limit=50)

        assert [row.event for row in rows] == [
            "IssueClosed",
            "IssueCommented",
            "PullRequestOpened",
            "PullRequestMerged",
        ]
        assert rows[0].actor == "bob"
        assert rows[1].title == "Issue"
        assert rows[1].activity_id == "IssueCommented:100:2026-08-21T01:30:00Z"
        assert rows[-1].actor_type == "bot"

    def test_detects_reopen_transition_without_replaying_original_open(self, adapter):
        reopened = {
            "number": 42,
            "title": "Issue",
            "state": "open",
            "html_url": "http://gitea.local/owner/repo/issues/42",
            "created_at": "2026-08-01T00:00:00Z",
            "updated_at": "2026-08-21T02:00:00Z",
            "closed_at": None,
            "user": {"login": "alice"},
        }

        def request(method, path, data=None):
            if "type=issues" in path:
                return [reopened]
            if "type=pulls" in path or "/issues/comments?" in path:
                return []
            if "/issues/42/timeline?" in path:
                return [
                    {
                        "type": "reopen",
                        "created_at": "2026-08-21T02:00:00Z",
                        "user": {"login": "bob"},
                    }
                ]
            raise AssertionError(path)

        with patch.object(adapter._api, "request", side_effect=request):
            rows = adapter.list_scm_activity("2026-08-21T00:00:00Z")

        assert len(rows) == 1
        assert rows[0].event == "IssueOpened"
        assert rows[0].timestamp == "2026-08-21T02:00:00Z"
        assert rows[0].actor == "bob"

    def test_edited_old_comment_is_not_reported_as_new(self, adapter):
        old_comment = {
            "id": 5,
            "issue_url": "http://gitea.local/owner/repo/issues/42",
            "created_at": "2026-08-20T00:00:00Z",
            "updated_at": "2026-08-21T02:00:00Z",
            "user": {"login": "alice"},
        }
        responses = [[], [], [old_comment]]
        with patch.object(adapter._api, "request", side_effect=responses):
            rows = adapter.list_scm_activity("2026-08-21T00:00:00Z")
        assert rows == []

    def test_pull_request_comment_uses_pull_url_for_number(self, adapter):
        comment = {
            "id": 101,
            "issue_url": "",
            "pull_request_url": "http://gitea.local/owner/repo/pulls/10",
            "created_at": "2026-08-21T01:30:00Z",
            "user": {"login": "carol"},
        }
        responses = [[], [], [comment]]
        with patch.object(adapter._api, "request", side_effect=responses):
            rows = adapter.list_scm_activity("2026-08-21T00:00:00Z")

        assert len(rows) == 1
        assert rows[0].event == "IssueCommented"
        assert rows[0].number == 10
        assert rows[0].url.endswith("/pulls/10")

    def test_paginates_up_to_configured_limit(self, adapter):
        issues = [
            {
                "number": number,
                "title": f"Issue {number}",
                "state": "open",
                "html_url": f"http://gitea.local/owner/repo/issues/{number}",
                "created_at": f"2026-08-21T00:{number - 1:02d}:00Z",
                "closed_at": None,
                "user": {"login": "alice"},
            }
            for number in range(1, 61)
        ]
        requested_issue_pages = []

        def request(method, path, data=None):
            if "type=issues" in path:
                page = 2 if "page=2" in path else 1
                requested_issue_pages.append(page)
                return issues[50:] if page == 2 else issues[:50]
            return []

        with patch.object(adapter._api, "request", side_effect=request):
            rows = adapter.list_scm_activity("2026-08-21T00:00:00Z", limit=60)

        assert len(rows) == 60
        assert requested_issue_pages == [1, 2]


class TestCloseIssue:
    def test_closes(self, adapter):
        with patch.object(adapter._api, "request", return_value=None) as mock:
            adapter.close_issue(42)
        mock.assert_called_once_with("PATCH", "/repos/owner/repo/issues/42", {"state": "closed"})


class TestMergePR:
    def test_merges(self, adapter):
        with patch.object(adapter._api, "request", return_value=None) as mock:
            result = adapter.merge_pr(10)
        assert result is True
        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/pulls/10/merge",
            {"Do": "merge", "delete_branch_after_merge": True},
        )

    def test_expected_head_is_sent_to_native_merge(self, adapter):
        with patch.object(adapter._api, "request", return_value=None) as mock:
            result = adapter.merge_pr_expected(10, expected_head_sha="a" * 40)
        assert result is True
        mock.assert_called_once_with(
            "POST",
            "/repos/owner/repo/pulls/10/merge",
            {
                "Do": "merge",
                "delete_branch_after_merge": True,
                "head_commit_id": "a" * 40,
            },
        )

    def test_rejects_invalid_expected_head(self, adapter):
        with pytest.raises(ValueError, match="expected full head revision"):
            adapter.merge_pr_expected(10, expected_head_sha="short")


class TestURLMethods:
    def test_issue_url(self, adapter):
        assert adapter.issue_url(42) == "http://gitea.local/owner/repo/issues/42"

    def test_pr_url(self, adapter):
        assert adapter.pr_url(10) == "http://gitea.local/owner/repo/pulls/10"

    def test_branch_url(self, adapter):
        assert adapter.branch_url("feat/x") == "http://gitea.local/owner/repo/src/branch/feat/x"


class TestGetBranchProtection:
    def test_returns_rules_when_protected(self, adapter):
        rules = {
            "branch_name": "main",
            "required_approvals": 1,
            "enable_status_check": True,
        }
        with patch.object(adapter._api, "request", return_value=rules) as mock:
            result = adapter.get_branch_protection("main")
        mock.assert_called_once_with(
            "GET",
            "/repos/owner/repo/branch_protections/main",
        )
        assert result == {"branch": "main", "rules": rules}

    def test_returns_none_for_404(self, adapter):
        err = GiteaAPIError(404, "GET", "/repos/owner/repo/branch_protections/main")
        with patch.object(adapter._api, "request", side_effect=err):
            result = adapter.get_branch_protection("main")
        assert result is None

    def test_returns_none_when_payload_empty(self, adapter):
        with patch.object(adapter._api, "request", return_value=None):
            result = adapter.get_branch_protection("main")
        assert result is None

    def test_propagates_non_404_errors(self, adapter):
        err = GiteaAPIError(500, "GET", "/repos/owner/repo/branch_protections/main")
        with (
            patch.object(adapter._api, "request", side_effect=err),
            pytest.raises(GiteaAPIError),
        ):
            adapter.get_branch_protection("main")

    def test_capability_advertised(self, adapter):
        assert "branch_protection" in adapter.capabilities


class TestAPIGuard:
    def test_blocks_hooks_write(self, adapter):
        with pytest.raises(PermissionError, match="API-Guard"):
            adapter._api.request("POST", "/repos/owner/repo/hooks")

    def test_allows_hooks_read(self, adapter):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"[]"
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            adapter._api.request("GET", "/repos/owner/repo/hooks")
