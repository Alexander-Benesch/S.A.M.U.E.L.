"""Explicit SCM metadata read using existing clients; never sends a webhook."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.gitea.api import GiteaAPI, GiteaAPIError
from samuel.adapters.github.adapter import normalize_github_api_url
from samuel.adapters.github.api import GitHubAPI, GitHubAPIError
from samuel.core.permission_diagnostics import (
    PermissionActor,
    PermissionDiagnostic,
    PermissionOperation,
    PermissionOutcome,
)
from samuel.core.webhook_diagnostics import summarize_hooks, timestamp


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect rejected", headers, fp)


def read_webhook_configuration(provider: str, url: str, token: str, repo: str) -> dict[str, Any]:
    def result(
        outcome: PermissionOutcome, *, status: int | None = None, hooks: list | None = None
    ) -> dict[str, Any]:
        return {
            "state": "read"
            if hooks is not None
            else "restricted"
            if outcome == PermissionOutcome.DENIED
            else "unknown",
            "observed_at": timestamp(),
            "hooks": hooks or [],
            "permission_diagnostic": PermissionDiagnostic(
                PermissionActor.RUNTIME,
                PermissionOperation.HOOK_READ,
                outcome,
                status,
                "GET",
                "/repos/{owner}/{repo}/hooks",
            ).to_dict(),
        }

    parts = repo.split("/")
    if (
        provider not in {"gitea", "github"}
        or not (url and token)
        or len(parts) != 2
        or any(not p or p in {".", ".."} for p in parts)
    ):
        return result(PermissionOutcome.UNKNOWN)
    path = "/repos/" + "/".join(urllib.parse.quote(p, safe="") for p in parts) + "/hooks"
    try:
        auth = StaticTokenAuth(token)
        opener = urllib.request.build_opener(_NoRedirect())
        if provider == "gitea":
            raw = GiteaAPI(url, auth, timeout=8, opener=opener).request(
                "GET", path + "?limit=50&page=1"
            )
        else:
            raw = GitHubAPI(
                auth, base_url=normalize_github_api_url(url), timeout=8, opener=opener
            ).request("GET", path + "?per_page=50&page=1")
        hooks = summarize_hooks(raw, provider)
        return result(
            PermissionOutcome.SUCCEEDED if hooks is not None else PermissionOutcome.UNKNOWN,
            hooks=hooks,
        )
    except (GiteaAPIError, GitHubAPIError) as exc:
        return result(
            PermissionOutcome.DENIED if exc.status in {401, 403} else PermissionOutcome.UNKNOWN,
            status=exc.status,
        )
    except Exception:
        # Provider errors may include credentials, URLs or raw hook secrets.
        return {
            **result(PermissionOutcome.UNKNOWN),
            "detail": "Hook-Metadaten konnten nicht gelesen werden; Verbindung und konfigurierten Endpoint prüfen.",
        }
