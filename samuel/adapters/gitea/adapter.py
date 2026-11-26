from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from samuel.adapters.git_compare import compare_local_commits, read_local_file_at_revision
from samuel.adapters.gitea.api import GiteaAPI, GiteaAPIError
from samuel.core.errors import SCMRevisionError
from samuel.core.evaluation_subject import PullRequestRevision, RevisionComparison
from samuel.core.external_evidence import (
    SCMCheckJob,
    SCMCheckObservation,
    SCMCheckReference,
    SCMCommitStatus,
)
from samuel.core.ports import IAuthProvider, ISCMCheckEvidenceReader, IVersionControl
from samuel.core.types import PR, Comment, Issue, Label, SCMActivity, SCMLabelEvent

log = logging.getLogger(__name__)
_FULL_GIT_OBJECT_ID = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")


def _response_dict(value: dict | list | None, operation: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Gitea {operation} returned {type(value).__name__}, expected object")
    return value


def _response_list(value: dict | list | None, operation: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"Gitea {operation} returned an invalid list")
    return value


def _positive_provider_int(value: object, field: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Gitea {field} must be a positive integer")
    return value


class GiteaAdapter(IVersionControl, ISCMCheckEvidenceReader):
    def __init__(
        self,
        base_url: str,
        repo: str,
        auth: IAuthProvider,
        *,
        bot_user: str = "",
        project_root: Path | None = None,
        request_timeout: float = 60.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._repo = repo
        self._api = GiteaAPI(base_url, auth, timeout=request_timeout)
        self._label_cache: dict[str, int] | None = None
        self._bot_user = bot_user
        self._project_root = project_root
        self._activity_states: dict[tuple[str, int], str] = {}

    @property
    def capabilities(self) -> set[str]:
        return {
            "labels",
            "webhooks_basic",
            "branch_protection",
            "activity_polling",
            "immutable_revisions",
            "native_expected_head_merge",
            "label_events",
            "scm_check_evidence_advisory",
        }

    @property
    def repository_identity(self) -> str:
        return f"{self._base_url}/{self._repo}"

    def resolve_ref(self, ref: str) -> str:
        encoded_ref = urllib.parse.quote(ref, safe="")
        data = _response_dict(
            self._api.request("GET", f"/repos/{self._repo}/git/commits/{encoded_ref}"),
            "resolve revision",
        )
        sha = data.get("sha")
        if not isinstance(sha, str):
            raise SCMRevisionError("invalid_revision_response", "SCM returned no commit ID")
        return sha.lower()

    def resolve_ref_optional(self, ref: str) -> str | None:
        try:
            return self.resolve_ref(ref)
        except GiteaAPIError as exc:
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

    def read_check_evidence(self, reference: SCMCheckReference) -> SCMCheckObservation:
        """Pull and narrowly project one existing Gitea Actions run.

        Job logs and arbitrary payload values are deliberately not retained.
        The result contains provider facts only and carries no gate authority.
        """

        if reference.provider != "gitea":
            raise ValueError("Gitea evidence reader requires provider=gitea")
        if reference.repository != self._repo:
            raise ValueError("evidence reference repository differs from configured repository")
        run = _response_dict(
            self._api.request("GET", f"/repos/{self._repo}/actions/runs/{reference.run_id}"),
            "read actions run",
        )
        if run.get("id") != reference.run_id:
            raise ValueError("Gitea actions response belongs to a different run")
        head_sha = str(run.get("head_sha") or "").lower()
        if _FULL_GIT_OBJECT_ID.fullmatch(head_sha) is None:
            raise ValueError("Gitea actions run has invalid head_sha")
        jobs_payload = _response_dict(
            self._api.request("GET", f"/repos/{self._repo}/actions/runs/{reference.run_id}/jobs"),
            "read actions jobs",
        )
        job_rows = jobs_payload.get("jobs")
        if not isinstance(job_rows, list) or any(not isinstance(row, dict) for row in job_rows):
            raise ValueError("Gitea actions jobs response has invalid shape")
        status_rows = _response_list(
            self._api.request("GET", f"/repos/{self._repo}/statuses/{head_sha}"),
            "read commit statuses",
        )

        missing: set[str] = set()
        jobs: list[SCMCheckJob] = []
        for row in job_rows:
            labels = row.get("runner_labels")
            if labels is None:
                missing.add("runner_labels")
                normalized_labels: tuple[str, ...] = ()
            elif isinstance(labels, list) and all(isinstance(item, str) for item in labels):
                normalized_labels = tuple(sorted(set(labels)))
            else:
                raise ValueError("Gitea job runner_labels has invalid shape")
            runner = row.get("runner") if isinstance(row.get("runner"), dict) else {}
            runner_id = row.get("runner_id", runner.get("id"))
            runner_name = row.get("runner_name", runner.get("name"))
            jobs.append(
                SCMCheckJob(
                    job_id=_positive_provider_int(row.get("id"), "job id") or 0,
                    name=str(row.get("name") or ""),
                    status=str(row.get("status") or ""),
                    conclusion=str(row["conclusion"]) if row.get("conclusion") else None,
                    runner_id=_positive_provider_int(runner_id, "runner id", optional=True),
                    runner_name=str(runner_name) if runner_name else None,
                    runner_labels=normalized_labels,
                    started_at=str(row["started_at"]) if row.get("started_at") else None,
                    completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
                    url=str(row["html_url"]) if row.get("html_url") else None,
                )
            )

        statuses: list[SCMCommitStatus] = []
        for row in status_rows:
            creator = row.get("creator")
            creator_name = (
                str(creator.get("login"))
                if isinstance(creator, dict) and creator.get("login")
                else None
            )
            statuses.append(
                SCMCommitStatus(
                    status_id=_positive_provider_int(row.get("id"), "status id") or 0,
                    context=str(row.get("context") or ""),
                    state=str(row.get("status") or row.get("state") or ""),
                    target_url=str(row["target_url"]) if row.get("target_url") else None,
                    creator=creator_name,
                    created_at=str(row["created_at"]) if row.get("created_at") else None,
                    updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
                )
            )

        reported_attempt = run.get("run_attempt", run.get("attempt"))
        if reported_attempt is None:
            missing.add("run_attempt")
        elif not isinstance(reported_attempt, int) or isinstance(reported_attempt, bool):
            raise ValueError("Gitea actions run attempt has invalid shape")
        workflow_path, workflow_ref = self._workflow_identity(run.get("path"))
        workflow_blob_sha = self._workflow_blob_sha(workflow_path, head_sha)
        if workflow_path is None:
            missing.add("workflow_path")
        if workflow_blob_sha is None:
            missing.add("workflow_blob_sha")
        if not any(
            run.get(key) for key in ("created_at", "updated_at", "started_at", "completed_at")
        ):
            missing.add("run_timestamps")

        pull_request_number: int | None = None
        pull_request_base_sha: str | None = None
        pull_request_head_sha: str | None = None
        pull_requests = run.get("pull_requests")
        if isinstance(pull_requests, list) and len(pull_requests) == 1:
            pull = pull_requests[0]
            if not isinstance(pull, dict):
                raise ValueError("Gitea actions pull-request reference has invalid shape")
            base = pull.get("base")
            head = pull.get("head")
            pull_request_number = _positive_provider_int(
                pull.get("number"), "pull-request number", optional=True
            )
            pull_request_base_sha = (
                str(base.get("sha")).lower() if isinstance(base, dict) and base.get("sha") else None
            )
            pull_request_head_sha = (
                str(head.get("sha")).lower() if isinstance(head, dict) and head.get("sha") else None
            )
        elif pull_requests:
            missing.add("pull_request_unambiguous")
        elif str(run.get("event") or "").lower() == "pull_request":
            missing.add("pull_request_binding")

        known_run_fields = {
            "id",
            "run_number",
            "attempt",
            "run_attempt",
            "event",
            "status",
            "conclusion",
            "head_sha",
            "head_branch",
            "path",
            "url",
            "html_url",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "previous_attempt_url",
            "repository",
            "repository_id",
            "pull_requests",
            "display_title",
            "workflow_id",
            "actor",
            "triggering_actor",
            "trigger_actor",
        }
        unknown = tuple(sorted(str(key) for key in run if key not in known_run_fields))
        return SCMCheckObservation(
            provider="gitea",
            provider_instance=self._base_url,
            repository=self._repo,
            run_id=reference.run_id,
            requested_attempt=reference.attempt,
            reported_attempt=reported_attempt,
            event=str(run.get("event") or ""),
            head_sha=head_sha,
            pull_request_number=pull_request_number,
            pull_request_base_sha=pull_request_base_sha,
            pull_request_head_sha=pull_request_head_sha,
            head_branch=str(run["head_branch"]) if run.get("head_branch") else None,
            status=str(run.get("status") or ""),
            conclusion=str(run["conclusion"]) if run.get("conclusion") else None,
            started_at=str(run["started_at"]) if run.get("started_at") else None,
            completed_at=str(run["completed_at"]) if run.get("completed_at") else None,
            workflow_path=workflow_path,
            workflow_ref=workflow_ref,
            workflow_blob_sha=workflow_blob_sha,
            run_url=str(run["html_url"]) if run.get("html_url") else None,
            jobs=tuple(sorted(jobs, key=lambda item: item.job_id)),
            commit_statuses=tuple(sorted(statuses, key=lambda item: item.status_id)),
            missing_facts=tuple(sorted(missing)),
            unknown_fields=unknown,
        )

    @staticmethod
    def _workflow_identity(value: object) -> tuple[str | None, str | None]:
        if not isinstance(value, str) or not value.strip():
            return None, None
        path, separator, ref = value.strip().partition("@")
        if not path.startswith(".gitea/workflows/"):
            path = f".gitea/workflows/{path.lstrip('/')}"
        if (
            len(path) > 1024
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
        ):
            raise ValueError("Gitea workflow path is invalid")
        return path, ref if separator and ref else None

    def _workflow_blob_sha(self, path: str | None, head_sha: str) -> str | None:
        if path is None:
            return None
        encoded_path = urllib.parse.quote(path, safe="/")
        query = urllib.parse.urlencode({"ref": head_sha})
        try:
            value = _response_dict(
                self._api.request("GET", f"/repos/{self._repo}/contents/{encoded_path}?{query}"),
                "read workflow blob",
            )
        except GiteaAPIError as exc:
            if exc.status == 404:
                return None
            raise
        sha = value.get("sha")
        return str(sha).lower() if sha else None

    def find_pr_by_marker(self, marker: str, *, head: str, base: str) -> PR | None:
        if not marker or any(ord(char) < 32 for char in marker):
            raise SCMRevisionError("invalid_pr_marker", "PR intent marker is not canonical")
        matches: list[PR] = []
        for page in range(1, 101):
            rows = _response_list(
                self._api.request(
                    "GET",
                    f"/repos/{self._repo}/pulls?state=all&limit=50&page={page}",
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
            if len(rows) < 50:
                break
        if len(matches) > 1:
            raise SCMRevisionError(
                "pr_marker_ambiguous",
                "More than one pull request carries the bound intent marker",
            )
        return matches[0] if matches else None

    def list_scm_activity(self, since: str, limit: int = 250) -> list[SCMActivity]:
        """Normalize Gitea issues, PRs and comments into activity facts.

        ``since`` is intentionally supplied by the caller's persistent cursor.
        Event timestamps (created/closed/merged) are filtered independently so
        an edit of an old object cannot masquerade as a new activity.
        """

        bounded_limit = max(1, min(int(limit), 500))
        issue_rows = self._activity_pages(
            f"/repos/{self._repo}/issues",
            {"state": "all", "since": since, "type": "issues"},
            bounded_limit,
        )
        pull_rows = self._activity_pages(
            f"/repos/{self._repo}/issues",
            {"state": "all", "since": since, "type": "pulls"},
            bounded_limit,
        )
        comment_rows = self._activity_pages(
            f"/repos/{self._repo}/issues/comments",
            {"since": since},
            bounded_limit,
        )

        issue_by_number = {
            int(row.get("number") or 0): row
            for row in [*issue_rows, *pull_rows]
            if isinstance(row, dict) and row.get("number")
        }
        activities: list[SCMActivity] = []

        for row in issue_rows:
            if not isinstance(row, dict):
                continue
            self._append_open_close_activity(activities, row, since, pull_request=False)

        for row in pull_rows:
            if not isinstance(row, dict):
                continue
            self._append_open_close_activity(activities, row, since, pull_request=True)

        for row in comment_rows:
            if not isinstance(row, dict):
                continue
            created_at = str(row.get("created_at") or "")
            if not self._at_or_after(created_at, since):
                continue
            parent_url = str(row.get("issue_url") or row.get("pull_request_url") or "")
            number = self._number_from_url(parent_url)
            if not number:
                log.warning("Gitea activity comment has no resolvable issue number")
                continue
            parent = issue_by_number.get(number, {})
            actor = self._login(row.get("user"))
            activities.append(
                SCMActivity(
                    event="IssueCommented",
                    number=number,
                    timestamp=created_at,
                    title=str(parent.get("title") or ""),
                    url=str(parent.get("html_url") or parent_url),
                    actor=actor,
                    actor_type=self._actor_type(actor),
                    object_id=row.get("id"),
                )
            )

        unique = {activity.activity_id: activity for activity in activities}
        return sorted(unique.values(), key=lambda activity: activity.timestamp)[-bounded_limit:]

    def _activity_pages(self, path: str, params: dict[str, object], limit: int) -> list[dict]:
        page_size = min(limit, 50)
        rows: list[dict] = []
        page = 1
        while len(rows) < limit:
            query = urllib.parse.urlencode({**params, "limit": page_size, "page": page})
            value = self._api.request("GET", f"{path}?{query}") or []
            if not isinstance(value, list):
                log.warning("Gitea activity endpoint returned an invalid response for %s", path)
                break
            batch = [row for row in value if isinstance(row, dict)]
            rows.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return rows[:limit]

    def _append_open_close_activity(
        self,
        activities: list[SCMActivity],
        row: dict,
        since: str,
        *,
        pull_request: bool,
    ) -> None:
        number = int(row.get("number") or 0)
        if not number:
            return
        title = str(row.get("title") or "")
        url = str(row.get("html_url") or "")
        author = self._login(row.get("user"))
        created_at = str(row.get("created_at") or "")
        state_key = ("pull" if pull_request else "issue", number)
        previous_state = self._activity_states.get(state_key)
        current_state = str(row.get("state") or "")
        if self._at_or_after(created_at, since):
            activities.append(
                SCMActivity(
                    event="PullRequestOpened" if pull_request else "IssueOpened",
                    number=number,
                    timestamp=created_at,
                    title=title,
                    url=url,
                    actor=author,
                    actor_type=self._actor_type(author),
                )
            )
        elif current_state == "open" and previous_state in {None, "closed"}:
            reopened = self._timeline_transition(number, "reopen", since)
            if reopened is not None:
                reopened_at, actor = reopened
                activities.append(
                    SCMActivity(
                        event="PullRequestOpened" if pull_request else "IssueOpened",
                        number=number,
                        timestamp=reopened_at,
                        title=title,
                        url=url,
                        actor=actor or author,
                        actor_type=self._actor_type(actor or author),
                    )
                )

        closed_at = str(row.get("closed_at") or "")
        if pull_request:
            raw_pr_info = row.get("pull_request")
            pr_info: dict[str, Any] = raw_pr_info if isinstance(raw_pr_info, dict) else {}
            merged_at = str(pr_info.get("merged_at") or "")
            merged = bool(pr_info.get("merged"))
            transition_at = merged_at if merged else closed_at
            if not self._at_or_after(transition_at, since):
                self._activity_states[state_key] = current_state
                return
            actor = author
            if merged:
                try:
                    detail = _response_dict(
                        self._api.request("GET", f"/repos/{self._repo}/pulls/{number}"),
                        "pull detail",
                    )
                    actor = self._login(detail.get("merged_by")) or author
                    url = str(detail.get("html_url") or url)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not resolve merge actor for PR #%d: %s", number, exc)
            else:
                transition = self._timeline_transition(number, "close", since)
                actor = (transition[1] or author) if transition is not None else author
            activities.append(
                SCMActivity(
                    event="PullRequestMerged" if merged else "PullRequestClosed",
                    number=number,
                    timestamp=merged_at if merged else closed_at,
                    title=title,
                    url=url,
                    actor=actor,
                    actor_type=self._actor_type(actor),
                )
            )
        else:
            if not self._at_or_after(closed_at, since):
                self._activity_states[state_key] = current_state
                return
            transition = self._timeline_transition(number, "close", since)
            actor = (transition[1] or author) if transition is not None else author
            activities.append(
                SCMActivity(
                    event="IssueClosed",
                    number=number,
                    timestamp=closed_at,
                    title=title,
                    url=url,
                    actor=actor,
                    actor_type=self._actor_type(actor),
                )
            )
        self._activity_states[state_key] = current_state

    def _timeline_transition(
        self,
        number: int,
        transition_type: str,
        since: str,
    ) -> tuple[str, str] | None:
        try:
            query = urllib.parse.urlencode({"since": since, "limit": 50})
            rows = _response_list(
                self._api.request("GET", f"/repos/{self._repo}/issues/{number}/timeline?{query}"),
                "issue timeline",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not resolve %s actor for #%d: %s", transition_type, number, exc)
            return None
        candidates: list[tuple[datetime, str, str]] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("type") != transition_type:
                continue
            raw_timestamp = str(row.get("created_at") or "")
            current = self._parse_timestamp(raw_timestamp)
            if current is None or not self._at_or_after(raw_timestamp, since):
                continue
            candidates.append((current, raw_timestamp, self._login(row.get("user"))))
        if not candidates:
            return None
        _, timestamp, actor = max(candidates, key=lambda item: item[0])
        return timestamp, actor

    def _actor_type(self, actor: str) -> str:
        return "bot" if self._bot_user and actor == self._bot_user else "human"

    @staticmethod
    def _login(value: Any) -> str:
        return (
            str(value.get("login") or value.get("username") or "")
            if isinstance(value, dict)
            else ""
        )

    @staticmethod
    def _number_from_url(url: str) -> int:
        try:
            return int(url.rstrip("/").rsplit("/", 1)[-1])
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _at_or_after(cls, value: str, since: str) -> bool:
        current = cls._parse_timestamp(value)
        threshold = cls._parse_timestamp(since)
        return current is not None and threshold is not None and current >= threshold

    def get_branch_protection(self, branch: str) -> dict | None:
        """#209: GET /repos/{repo}/branch_protections/{branch}.

        Gitea returns 404 when the branch is unprotected — we map that to
        ``None``. The raw rule object (push restrictions, required reviews,
        ...) is wrapped under ``rules`` so callers can read whatever they
        need.
        """
        try:
            data = self._api.request(
                "GET",
                f"/repos/{self._repo}/branch_protections/{branch}",
            )
        except GiteaAPIError as e:
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
                    "GET", f"/repos/{self._repo}/issues/{number}/timeline?limit=50&page={page}"
                ),
                "issue timeline",
            )
            for row in rows:
                label_row = row.get("label")
                label_name = str(label_row.get("name", "")) if isinstance(label_row, dict) else ""
                removed = row.get("removed") is True
                if row.get("type") != "label" or not label_name:
                    continue
                if label and (label_name != label or removed):
                    continue
                user_value = row.get("user")
                user: dict[str, Any] = user_value if isinstance(user_value, dict) else {}
                actor = str(user.get("login") or user.get("username") or "")
                events.append(
                    SCMLabelEvent(
                        source_id=f"gitea-timeline:{row.get('id', '')}",
                        label=label_name,
                        actor=actor,
                        actor_type=self._actor_type(actor),
                        timestamp=str(row.get("created_at") or ""),
                        operation="remove" if removed else "add",
                    )
                )
            if len(rows) < 50:
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
        labels = self._get_all_labels()
        # Remove first, then add — prevents double labels on partial failure
        if remove in labels:
            try:
                self._api.request(
                    "DELETE",
                    f"/repos/{self._repo}/issues/{number}/labels/{labels[remove]}",
                )
            except Exception:
                log.warning("Failed to remove label %s from #%d", remove, number)
        if add in labels:
            self._api.request(
                "POST",
                f"/repos/{self._repo}/issues/{number}/labels",
                {"labels": [labels[add]]},
            )

    def list_labels(self) -> list[dict]:
        data = _response_list(
            self._api.request("GET", f"/repos/{self._repo}/labels"), "list labels"
        )
        return [
            {
                "id": l["id"],
                "name": l["name"],
                "color": l.get("color", ""),
                "description": l.get("description", ""),
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
        self._label_cache = None
        return {
            "id": data["id"],
            "name": data["name"],
            "color": data.get("color", ""),
            "description": data.get("description", ""),
        }

    def list_issues(self, labels: list[str]) -> list[Issue]:
        all_issues: list[Issue] = []
        page = 1
        limit = 50
        while True:
            params = f"?type=issues&state=open&limit={limit}&page={page}"
            if labels:
                params += f"&labels={','.join(labels)}"
            batch = _response_list(
                self._api.request("GET", f"/repos/{self._repo}/issues{params}"),
                "list issues",
            )
            all_issues.extend(self._to_issue(i) for i in batch)
            if len(batch) < limit:
                break
            page += 1
        return all_issues

    def close_issue(self, number: int) -> None:
        self._api.request(
            "PATCH",
            f"/repos/{self._repo}/issues/{number}",
            {"state": "closed"},
        )

    def merge_pr(self, pr_id: int) -> bool:
        self._api.request(
            "POST",
            f"/repos/{self._repo}/pulls/{pr_id}/merge",
            {"Do": "merge", "delete_branch_after_merge": True},
        )
        return True

    def merge_pr_expected(self, pr_id: int, *, expected_head_sha: str) -> bool:
        if _FULL_GIT_OBJECT_ID.fullmatch(expected_head_sha) is None:
            raise ValueError("Gitea merge requires an expected full head revision")
        self._api.request(
            "POST",
            f"/repos/{self._repo}/pulls/{pr_id}/merge",
            {
                "Do": "merge",
                "delete_branch_after_merge": True,
                "head_commit_id": expected_head_sha,
            },
        )
        return True

    def issue_url(self, number: int) -> str:
        return f"{self._base_url}/{self._repo}/issues/{number}"

    def pr_url(self, pr_id: int) -> str:
        return f"{self._base_url}/{self._repo}/pulls/{pr_id}"

    def branch_url(self, branch: str) -> str:
        return f"{self._base_url}/{self._repo}/src/branch/{branch}"

    def _get_all_labels(self) -> dict[str, int]:
        if self._label_cache is None:
            data = _response_list(
                self._api.request("GET", f"/repos/{self._repo}/labels"), "list labels"
            )
            self._label_cache = {label["name"]: label["id"] for label in data}
        return self._label_cache

    @staticmethod
    def _to_issue(data: dict) -> Issue:
        return Issue(
            number=data["number"],
            title=data["title"],
            body=data.get("body", ""),
            state=data["state"],
            labels=[Label(id=l["id"], name=l["name"]) for l in data.get("labels", [])],
        )

    @staticmethod
    def _to_comment(data: dict) -> Comment:
        return Comment(
            id=data["id"],
            body=data.get("body", ""),
            user=data.get("user", {}).get("login", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    @staticmethod
    def _to_pr(data: dict) -> PR:
        return PR(
            id=data["id"],
            number=data["number"],
            title=data["title"],
            html_url=data.get("html_url", ""),
            state=data.get("state", "open"),
            merged=data.get("merged", False),
        )
