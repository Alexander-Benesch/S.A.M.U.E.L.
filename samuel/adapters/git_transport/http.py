"""HTTP Git authentication bound to one configured repository."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from samuel.adapters.git_transport.askpass import SECRET_ENV, USERNAME_ENV
from samuel.core.errors import GitTransportAuthError
from samuel.core.git_remote import endpoint as _endpoint
from samuel.core.git_remote import parse_http_url as _parse_http_url
from samuel.core.ports import IAuthProvider, IGitTransportAuth


class HttpGitTransportAuth(IGitTransportAuth):
    """Provide an argv-free askpass environment for one exact repository."""

    def __init__(
        self,
        repository_url: str,
        username: str,
        auth: IAuthProvider,
        *,
        askpass_path: str | Path | None = None,
    ) -> None:
        expected = _parse_http_url(repository_url.rstrip("/"), code="git_auth_config_invalid")
        normalized_username = username.strip()
        if any(character in normalized_username for character in "\r\n\0"):
            raise GitTransportAuthError(
                "git_auth_config_invalid",
                "Git transport username is missing or invalid",
            )
        self._expected_endpoint = _endpoint(expected)
        self._expected_path = expected.path.rstrip("/")
        self._username = normalized_username
        self._auth = auth
        self._askpass_path = Path(askpass_path) if askpass_path else None

    def _trusted_askpass(self) -> Path:
        candidate = (
            self._askpass_path or Path(sys.executable).absolute().parent / "samuel-git-askpass"
        )
        if not candidate.is_absolute():
            raise GitTransportAuthError(
                "git_askpass_unavailable",
                "Installed Git askpass helper is unavailable",
            )
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise GitTransportAuthError(
                "git_askpass_unavailable",
                "Installed Git askpass helper is unavailable",
            ) from exc
        if candidate.is_symlink() or not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise GitTransportAuthError(
                "git_askpass_unavailable",
                "Installed Git askpass helper is unavailable",
            )
        return resolved

    def _validate_remote(self, remote_url: str) -> None:
        remote = _parse_http_url(remote_url, code="git_remote_not_authorized")
        remote_path = remote.path.rstrip("/")
        if remote_path.endswith(".git"):
            remote_path = remote_path[:-4]
        if _endpoint(remote) != self._expected_endpoint or remote_path != self._expected_path:
            raise GitTransportAuthError(
                "git_remote_not_authorized",
                "Git remote does not match the configured SCM repository",
            )

    @contextmanager
    def environment(
        self,
        remote_url: str,
        operation: Literal["fetch", "push"],
    ) -> Iterator[Mapping[str, str]]:
        if operation not in {"fetch", "push"}:
            raise GitTransportAuthError(
                "git_operation_not_authorized",
                "Git transport operation is not authorized",
            )
        self._validate_remote(remote_url)
        if not self._username:
            raise GitTransportAuthError(
                "git_credential_unavailable",
                "Git transport username is unavailable",
            )
        if not self._auth.is_valid():
            raise GitTransportAuthError(
                "git_credential_unavailable",
                "Git transport credential is unavailable",
            )
        secret = self._auth.get_token()
        if not secret or any(character in secret for character in "\r\n\0"):
            raise GitTransportAuthError(
                "git_credential_unavailable",
                "Git transport credential is unavailable",
            )
        overlay = {
            "GIT_ASKPASS": str(self._trusted_askpass()),
            "GIT_ASKPASS_REQUIRE": "force",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_VALUE_0": "",
            "GIT_TERMINAL_PROMPT": "0",
            SECRET_ENV: secret,
            USERNAME_ENV: self._username,
        }
        try:
            yield overlay
        finally:
            overlay.clear()
