from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path
from typing import Any

from samuel.adapters.git_compare import compare_local_commits, read_local_file_at_revision
from samuel.adapters.github.api import GitHubAPI, GitHubAPIError
from samuel.core.errors import SCMRevisionError
from samuel.core.evaluation_subject import PullRequestRevision, RevisionComparison
from samuel.core.ports import IAuthProvider, IVersionControl
from samuel.core.types import PR, Comment, Issue, Label, SCMLabelEvent

log = logging.getLogger(__name__)


def _response_dict(value: dict | list | None, operation: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"GitHub {operation} returned {type(value).__name__}, expected object")
    return value


def _response_list(value: dict | list | None, operation: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"GitHub {operation} returned an invalid list")
    return value


def normalize_github_api_url(base_url: str) -> str:
    """Return the REST API base for public GitHub or GitHub Enterprise."""

    value = (base_url or "https://github.com").rstrip("/")
    parsed = urllib.parse.urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in {"github.com", "www.github.com", "api.github.com"}:
        return "https://api.github.com"
    if parsed.path.rstrip("/").endswith("/api/v3"):
        return value
    return f"{value}/api/v3"


class GitHubAdapter(IVersionControl):
    def __init__(
        self,
        repo: str,
        auth: IAuthProvider,
        *,
        base_url: str = "https://api.github.com",
        project_root: Path | None = None,
        request_timeout: float = 60.0,
        bot_user: str = "",
    ):
        self._repo = repo
        self._bot_user = bot_user
        self._project_root = project_root
        base_url = normalize_github_api_url(base_url)
        self._api = GitHubAPI(auth, base_url=base_url, timeout=request_timeout)
        parsed = urllib.parse.urlsplit(base_url)
        self._html_base = (
            "https://github.com"
            if parsed.hostname == "api.github.com"
            else urllib.parse.urlunsplit(parsed._replace(path=parsed.path.removesuffix("/api/v3")))
        )

    @property
    def capabilities(self) -> set[str]:
        return {
            "labels",
            "webhooks_full",
            "checks",
            "pull_request_reviews",
            "branch_protection",
            "immutable_revisions",
            "label_events",
        }

    @property
    def repository_identity(self) -> str:
        return f"{self._html_base}/{self._repo}"

    def resolve_ref(self, ref: str) -> str:
        encoded_ref = urllib.parse.quote(ref, safe="")
        data = _response_dict(
            self._api.request("GET", f"/repos/{self._repo}/commits/{encoded_ref}"),
            "resolve revision",
        )
        sha = data.get("sha")
        if not isinstance(sha, str):
            raise SCMRevisionError("invalid_revision_response", "SCM returned no commit ID")
        return sha.lower()

    def resolve_ref_optional(self, ref: str) -> str | None:
        try:
            return self.resolve_ref(ref)
        except GitHubAPIError as exc:
            if exc.status == 404:
                return None
            raise

    def compare_commits(
        self, base_sha: str, head_sha: str, *, max_diff_bytes: int
    ) -> RevisionComparison:
        return compare_local_commits(
            project_root=self._project_root,
            repository=self.repository_identity,
            base_sha=base_sha,
            head_sha=head_sha,
            max_diff_bytes=max_diff_bytes,
        )

    def read_file_at_revision(self, head_sha: str, path: str, *, max_file_bytes: int) -> str | None:
        return read_local_file_at_revision(
            project_root=self._project_root,
            head_sha=head_sha,
            path=path,
            max_file_bytes=max_file_bytes,
        )

    def get_pr_revision(self, pr_id: int) -> PullRequestRevision:
        data = _response_dict(
            self._api.request("GET", f"/repos/{self._repo}/pulls/{pr_id}"),
            "pull request revision",
        )
        base = data.get("base")
        head = data.get("head")
        if not isinstance(base, dict) or not isinstance(head, dict):
            raise SCMRevisionError(
                "invalid_pr_revision_response", "SCM returned no pull-request revisions"
            )
        return PullRequestRevision(
            repository=self.repository_identity,
            base_sha=str(base.get("sha", "")).lower(),
            head_sha=str(head.get("sha", "")).lower(),
        )

    def get_pr(self, pr_id: int) -> PR:
        data = _response_dict(
            self._api.request("GET", f"/repos/{self._repo}/pulls/{pr_id}"),
            "get pull request",
        )
        return self._to_pr(data)

    def find_pr_by_marker(self, marker: str, *, head: str, base: str) -> PR | None:
        if not marker or any(ord(char) < 32 for char in marker):
            raise SCMRevisionError("invalid_pr_marker", "PR intent marker is not canonical")
        matches: list[PR] = []
        for page in range(1, 101):
            rows = _response_list(
                self._api.request(
                    "GET",
                    f"/repos/{self._repo}/pulls?state=all&per_page=100&page={page}",
                ),
                "list pull requests",
            )
            for row in rows:
                head_row = row.get("head")
                base_row = row.get("base")
                if (
                    isinstance(head_row, dict)
                    and isinstance(base_row, dict)
                    and str(head_row.get("ref", "")) == head
                    and str(base_row.get("ref", "")) == base
                    and f"<!-- {marker} -->" in str(row.get("body", ""))
                ):
                    matches.append(self._to_pr(row))
            if len(rows) < 100:
                break
        if len(matches) > 1:
            raise SCMRevisionError(
                "pr_marker_ambiguous",
                "More than one pull request carries the bound intent marker",
            )
        return matches[0] if matches else None

    def get_branch_protection(self, branch: str) -> dict | None:
        """#209: GET /repos/{owner}/{repo}/branches/{branch}/protection.

        GitHub returns 404 when the branch is unprotected — mapped to
        ``None``. Raw rules wrapped under ``rules``.
        """
        try:
            data = self._api.request(
                "GET",
                f"/repos/{self._repo}/branches/{branch}/protection",
            )
        except GitHubAPIError as e:
            if e.status == 404:
                return None
            raise
        if not data:
            return None
        return {"branch": branch, "rules": _response_dict(data, "branch protection")}

    def get_issue(self, number: int) -> Issue:
        data = self._api.request("GET", f"/repos/{self._repo}/issues/{number}")
        return self._to_issue(_response_dict(data, "get issue"))

    def get_comments(self, number: int) -> list[Comment]:
        data = _response_list(
            self._api.request("GET", f"/repos/{self._repo}/issues/{number}/comments"),
            "list comments",
        )
        return [self._to_comment(c) for c in data]

    def get_label_events(self, number: int, label: str) -> list[SCMLabelEvent]:
        events: list[SCMLabelEvent] = []
        page = 1
        while True:
            rows = _response_list(
                self._api.request(
                    "GET", f"/repos/{self._repo}/issues/{number}/events?per_page=100&page={page}"
                ),
                "issue events",
            )
            for row in rows:
                label_row = row.get("label")
                if (
                    row.get("event") != "labeled"
                    or not isinstance(label_row, dict)
                    or str(label_row.get("name", "")) != label
                ):
                    continue
                actor_value = row.get("actor")
                actor_row: dict[str, Any] = actor_value if isinstance(actor_value, dict) else {}
                actor = str(actor_row.get("login") or "")
                is_bot = str(actor_row.get("type", "")).casefold() == "bot" or bool(
                    self._bot_user and actor == self._bot_user
                )
                events.append(
                    SCMLabelEvent(
                        source_id=f"github-event:{row.get('id', '')}",
                        label=label,
                        actor=actor,
                        actor_type="bot" if is_bot else "human",
                        timestamp=str(row.get("created_at") or ""),
                    )
                )
            if len(rows) < 100:
                break
            page += 1
        return events

    def post_comment(self, number: int, body: str) -> Comment:
        data = self._api.request(
            "POST",
            f"/repos/{self._repo}/issues/{number}/comments",
            {"body": body},
        )
        return self._to_comment(_response_dict(data, "post comment"))

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        data = self._api.request(
            "POST",
            f"/repos/{self._repo}/pulls",
            {"title": title, "body": body, "head": head, "base": base},
        )
        return self._to_pr(_response_dict(data, "create pull request"))

    def swap_label(self, number: int, remove: str, add: str) -> None:
        # Remove first, then add — prevents double labels on partial failure
        if remove:
            try:
                self._api.request(
                    "DELETE",
                    f"/repos/{self._repo}/issues/{number}/labels/{remove}",
                )
            except Exception:
                log.warning("Failed to remove label %s from #%d", remove, number)
        if add:
            self._api.request(
                "POST",
                f"/repos/{self._repo}/issues/{number}/labels",
                {"labels": [add]},
            )

    def list_labels(self) -> list[dict]:
        data = _response_list(
            self._api.request("GET", f"/repos/{self._repo}/labels?per_page=100"),
            "list labels",
        )
        return [
            {
                "id": l["id"],
                "name": l["name"],
                "color": l.get("color", ""),
                "description": l.get("description", "") or "",
            }
            for l in data
        ]

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        data = self._api.request(
            "POST",
            f"/repos/{self._repo}/labels",
            {"name": name, "color": color, "description": description},
        )
        data = _response_dict(data, "create label")
        return {
            "id": data["id"],
            "name": data["name"],
            "color": data.get("color", ""),
            "description": data.get("description", "") or "",
        }

    def list_issues(self, labels: list[str]) -> list[Issue]:
        params = "?state=open&per_page=50"
        if labels:
            params += f"&labels={','.join(labels)}"
        data = _response_list(
            self._api.request("GET", f"/repos/{self._repo}/issues{params}"), "list issues"
        )
        return [self._to_issue(i) for i in data if "pull_request" not in i]

    def close_issue(self, number: int) -> None:
        self._api.request(
            "PATCH",
            f"/repos/{self._repo}/issues/{number}",
            {"state": "closed"},
        )

    def merge_pr(self, pr_id: int) -> bool:
        self._api.request(
            "PUT",
            f"/repos/{self._repo}/pulls/{pr_id}/merge",
            {"merge_method": "merge"},
        )
        return True

    def issue_url(self, number: int) -> str:
        return f"{self._html_base}/{self._repo}/issues/{number}"

    def pr_url(self, pr_id: int) -> str:
        return f"{self._html_base}/{self._repo}/pull/{pr_id}"

    def branch_url(self, branch: str) -> str:
        return f"{self._html_base}/{self._repo}/tree/{branch}"

    @staticmethod
    def _to_issue(data: dict) -> Issue:
        return Issue(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            state=data["state"],
            labels=[Label(id=l["id"], name=l["name"]) for l in data.get("labels", [])],
        )

    @staticmethod
    def _to_comment(data: dict) -> Comment:
        return Comment(
            id=data["id"],
            body=data.get("body") or "",
            user=data.get("user", {}).get("login", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    @staticmethod
    def _to_pr(data: dict) -> PR:
        return PR(
            id=data.get("id", 0),
            number=data["number"],
            title=data["title"],
            html_url=data.get("html_url", ""),
            state=data.get("state", "open"),
            merged=data.get("merged", False),
        )
