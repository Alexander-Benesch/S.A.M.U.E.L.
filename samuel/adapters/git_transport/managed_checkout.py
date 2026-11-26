"""Prepare the installer-provisioned project as the unprivileged setup user."""

import os
import subprocess
from pathlib import Path
from typing import Any

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.git_transport.http import HttpGitTransportAuth
from samuel.core import git
from samuel.core.git_remote import canonical_repository_url
from samuel.core.project_binding import inspect_project, validate_project_request

TARGET = Path("/projects/codebase")


def prepare_checkout(
    host: str, repository: str, branch: str, username: str, token: str
) -> tuple[dict[str, Any], str]:
    repo = canonical_repository_url(repository)
    if not any(
        row.split()[4] == str(TARGET)
        for row in Path("/proc/self/mountinfo").read_text().splitlines()
    ):
        raise ValueError("Der vorbereitete Projektordner ist nicht eingebunden.")
    if branch and (
        branch.startswith("-")
        or len(branch) > 255
        or subprocess.run(
            ["git", "check-ref-format", "refs/heads/" + branch], capture_output=True, check=False
        ).returncode
    ):
        raise ValueError("Ungültiger Git-Branchname.")
    if not any(TARGET.iterdir()):
        auth = HttpGitTransportAuth(repo, username or "x-access-token", StaticTokenAuth(token))
        with auth.environment(repo, "fetch") as credentials:
            policy = git.git_process_environment(credentials, strip_path_overrides=True)
            env = {
                k: v
                for k, v in policy.items()
                if k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
                or k in credentials
                or k
                in {
                    "GIT_CONFIG_COUNT",
                    "GIT_CONFIG_GLOBAL",
                    "GIT_CONFIG_SYSTEM",
                    "GIT_CONFIG_NOSYSTEM",
                    "GIT_TERMINAL_PROMPT",
                }
            }
            env["PATH"] = os.defpath
            try:
                if branch:
                    head = subprocess.run(
                        [
                            "git",
                            "-c",
                            "http.followRedirects=false",
                            "ls-remote",
                            "--heads",
                            "--exit-code",
                            "--",
                            repo + ".git",
                            "refs/heads/" + branch,
                        ],
                        cwd=TARGET,
                        env=env,
                        capture_output=True,
                        timeout=60,
                        check=False,
                    )
                    if head.returncode or not head.stdout.strip().endswith(
                        ("\trefs/heads/" + branch).encode()
                    ):
                        raise ValueError(
                            "Branch nicht gefunden. Namen und Repository-Zugang prüfen."
                        )
                result = subprocess.run(
                    [
                        "git",
                        "-c",
                        "http.followRedirects=false",
                        "clone",
                        "--template=",
                        "--no-local",
                        "--no-recurse-submodules",
                        *(["--branch", branch] if branch else []),
                        "--",
                        repo + ".git",
                        ".",
                    ],
                    cwd=TARGET,
                    env=env,
                    capture_output=True,
                    timeout=300,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError(
                    "Zeitlimit beim Klonen erreicht. Projektordner und Netzwerk prüfen."
                ) from exc
            if result.returncode:
                raise ValueError(
                    "Checkout fehlgeschlagen. Repository, Branch und Leserecht des Tokens prüfen."
                )
    observed = inspect_project(TARGET, repository=repo)
    if not observed["passed"]:
        raise ValueError("Vorhandenen Projektordner prüfen: " + observed["reason_code"])
    actual_branch = git.current_branch(TARGET)
    if not actual_branch or actual_branch == "HEAD" or (branch and branch != actual_branch):
        raise ValueError("Der ausgecheckte Branch passt nicht zur Auswahl.")
    request = validate_project_request(
        dict(
            schema="project-registration-request.v1",
            host_source=host,
            container_target=str(TARGET),
            repository=repo,
            initial_revision=observed["observed_revision"],
        )
    )
    return request, actual_branch
