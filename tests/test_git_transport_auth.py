from __future__ import annotations

import os
import subprocess
import sys
from base64 import b64encode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from samuel.adapters.auth.static_token import StaticTokenAuth
from samuel.adapters.git_transport import HttpGitTransportAuth
from samuel.adapters.git_transport.askpass import SECRET_ENV, USERNAME_ENV
from samuel.core.errors import GitTransportAuthError
from samuel.core.git import _remote_run


def _helper(tmp_path: Path) -> Path:
    helper = tmp_path / "trusted-askpass"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o700)
    return helper


def _functional_helper(tmp_path: Path) -> Path:
    helper = tmp_path / "functional-askpass"
    helper.write_text(
        f"#!{sys.executable}\n"
        "from samuel.adapters.git_transport.askpass import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    return helper


def _auth(tmp_path: Path, token: str = "credential-sentinel") -> HttpGitTransportAuth:
    return HttpGitTransportAuth(
        "https://gitea.example.invalid/owner/repository",
        "demo-example-bot",
        StaticTokenAuth(token),
        askpass_path=_helper(tmp_path),
    )


def test_transport_overlay_uses_askpass_without_argv_or_git_config_secret(
    tmp_path: Path,
) -> None:
    token = "credential-sentinel"
    transport = _auth(tmp_path, token)

    with transport.environment(
        "https://gitea.example.invalid/owner/repository.git", "fetch"
    ) as overlay:
        captured = dict(overlay)
        assert captured[SECRET_ENV] == token
        assert captured[USERNAME_ENV] == "demo-example-bot"
        assert captured["GIT_ASKPASS_REQUIRE"] == "force"
        assert captured["GIT_TERMINAL_PROMPT"] == "0"
        assert captured["GIT_CONFIG_GLOBAL"] == os.devnull
        assert captured["GIT_CONFIG_NOSYSTEM"] == "1"
        assert captured["GIT_CONFIG_COUNT"] == "1"
        assert captured["GIT_CONFIG_KEY_0"] == "credential.helper"
        assert captured["GIT_CONFIG_VALUE_0"] == ""
        assert "GIT_CONFIG_KEY_1" not in captured
        assert "GIT_CONFIG_VALUE_1" not in captured
        assert token not in captured["GIT_ASKPASS"]
        assert all("extraheader" not in value.lower() for value in captured.values())

    assert not overlay


@pytest.mark.parametrize(
    "remote",
    [
        "ssh://git@gitea.example.invalid/owner/repository.git",
        "https://user:secret@gitea.example.invalid/owner/repository.git",
        "https://other.example.invalid/owner/repository.git",
        "https://gitea.example.invalid/owner/other.git",
        "https://gitea.example.invalid/owner/repository.git?credential=value",
        "https://gitea.example.invalid/owner/repository.git#fragment",
    ],
)
def test_transport_rejects_unbound_or_credential_bearing_remote(
    tmp_path: Path, remote: str
) -> None:
    with (
        pytest.raises(GitTransportAuthError) as error,
        _auth(tmp_path).environment(remote, "fetch"),
    ):
        pass

    assert error.value.code == "git_remote_not_authorized"
    assert "secret" not in error.value.safe_message


def test_transport_rejects_missing_credential_and_untrusted_helper(tmp_path: Path) -> None:
    helper = _helper(tmp_path)
    missing = HttpGitTransportAuth(
        "https://gitea.example.invalid/owner/repository",
        "demo-example-bot",
        StaticTokenAuth(""),
        askpass_path=helper,
    )
    with (
        pytest.raises(GitTransportAuthError) as missing_error,
        missing.environment("https://gitea.example.invalid/owner/repository.git", "push"),
    ):
        pass
    assert missing_error.value.code == "git_credential_unavailable"

    missing_user = HttpGitTransportAuth(
        "https://gitea.example.invalid/owner/repository",
        "",
        StaticTokenAuth("credential-sentinel"),
        askpass_path=helper,
    )
    with (
        pytest.raises(GitTransportAuthError) as user_error,
        missing_user.environment("https://gitea.example.invalid/owner/repository.git", "fetch"),
    ):
        pass
    assert user_error.value.code == "git_credential_unavailable"

    symlink = tmp_path / "askpass-link"
    symlink.symlink_to(helper)
    linked = HttpGitTransportAuth(
        "https://gitea.example.invalid/owner/repository",
        "demo-example-bot",
        StaticTokenAuth("credential-sentinel"),
        askpass_path=symlink,
    )
    with (
        pytest.raises(GitTransportAuthError) as helper_error,
        linked.environment("https://gitea.example.invalid/owner/repository.git", "fetch"),
    ):
        pass
    assert helper_error.value.code == "git_askpass_unavailable"


def test_network_git_receives_secret_only_in_environment(tmp_path: Path) -> None:
    token = "credential-sentinel"
    transport = _auth(tmp_path, token)
    calls: list[tuple[list[str], dict[str, str]]] = []

    def run(args: list[str], **kwargs: object) -> MagicMock:
        environment = dict(cast(dict[str, str], kwargs.get("env", {})))
        calls.append((args, environment))
        result = MagicMock(returncode=0, stdout="", stderr="")
        if args == ["git", "remote", "get-url", "origin"]:
            result.stdout = "https://gitea.example.invalid/owner/repository.git\n"
        return result

    with patch("subprocess.run", side_effect=run):
        ok, _ = _remote_run(["fetch", "origin", "main"], tmp_path, transport, "fetch")

    assert ok is True
    assert len(calls) == 2
    local_args, local_environment = calls[0]
    network_args, network_environment = calls[1]
    assert token not in "\0".join(local_args)
    assert token not in "\0".join(network_args)
    assert SECRET_ENV not in local_environment
    assert network_environment[SECRET_ENV] == token
    assert "SCM_TOKEN" not in network_environment


def test_network_git_redacts_remote_stderr(tmp_path: Path, caplog) -> None:
    token = "credential-sentinel"
    transport = _auth(tmp_path, token)

    def run(args: list[str], **_kwargs: object) -> MagicMock:
        if args == ["git", "remote", "get-url", "origin"]:
            return MagicMock(
                returncode=0,
                stdout="https://gitea.example.invalid/owner/repository.git\n",
                stderr="",
            )
        return MagicMock(
            returncode=1,
            stdout="",
            stderr=f"remote returned {token}",
        )

    with patch("subprocess.run", side_effect=run):
        ok, error = _remote_run(["fetch", "origin", "main"], tmp_path, transport, "fetch")

    assert ok is False
    assert error == "git_transport_failed"
    assert token not in caplog.text


def test_real_git_uses_forced_askpass_while_terminal_prompt_is_disabled(
    tmp_path: Path,
) -> None:
    username = "test-user"
    token = "credential-sentinel"
    expected = "Basic " + b64encode(f"{username}:{token}".encode()).decode()
    authenticated = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP callback name
            if self.headers.get("Authorization") == expected:
                authenticated.set()
                self.send_response(404)
            else:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="test"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    remote = f"http://127.0.0.1:{server.server_port}/owner/repository.git"
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=repository, check=True)
    transport = HttpGitTransportAuth(
        remote.removesuffix(".git"),
        username,
        StaticTokenAuth(token),
        askpass_path=_functional_helper(tmp_path),
    )
    try:
        ok, error = _remote_run(["fetch", "origin", "main"], repository, transport, "fetch")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert ok is False
    assert error == "git_transport_failed"
    assert authenticated.is_set()


@pytest.mark.parametrize(
    ("prompt", "name"),
    [("Username for 'https://example.invalid':", USERNAME_ENV), ("Password:", SECRET_ENV)],
)
def test_askpass_helper_reads_value_from_environment_not_arguments(prompt: str, name: str) -> None:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        USERNAME_ENV: "test-user",
        SECRET_ENV: "credential-sentinel",
    }
    completed = subprocess.run(
        [sys.executable, "-m", "samuel.adapters.git_transport.askpass", prompt],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == environment[name]
    assert "credential-sentinel" not in "\0".join(completed.args)


def test_askpass_helper_fails_closed_for_unknown_prompt() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "samuel.adapters.git_transport.askpass", "Other prompt"],
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(Path.cwd())},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
