"""#402: Dashboard-Bind-Auflösung (CLI-Flag > Env > Default)."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time

import pytest

from samuel.cli import _dashboard_display_host, _make_signal_handler, _resolve_dashboard_bind


def test_defaults(monkeypatch):
    monkeypatch.delenv("DASHBOARD_HOST", raising=False)
    monkeypatch.delenv("DASHBOARD_PORT", raising=False)
    assert _resolve_dashboard_bind(None, None) == ("0.0.0.0", 7777)


def test_env_used_when_no_flag(monkeypatch):
    monkeypatch.setenv("DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setenv("DASHBOARD_PORT", "8888")
    assert _resolve_dashboard_bind(None, None) == ("127.0.0.1", 8888)


def test_flag_overrides_env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PORT", "8888")
    assert _resolve_dashboard_bind("0.0.0.0", 9000) == ("0.0.0.0", 9000)


def test_invalid_env_port_falls_back(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PORT", "notaport")
    monkeypatch.delenv("DASHBOARD_HOST", raising=False)
    assert _resolve_dashboard_bind(None, None) == ("0.0.0.0", 7777)


def test_explicit_dashboard_host_is_preserved():
    assert _dashboard_display_host("192.0.2.22") == "192.0.2.22"


def test_wildcard_dashboard_host_uses_routable_address(monkeypatch):
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def connect(self, _target):
            return None

        def getsockname(self):
            return ("192.0.2.23", 54321)

    monkeypatch.setattr(socket, "socket", lambda *_args: FakeSocket())
    assert _dashboard_display_host("0.0.0.0") == "192.0.2.23"


def test_wildcard_dashboard_host_falls_back_to_localhost(monkeypatch):
    def no_route(*_args):
        raise OSError("no route")

    monkeypatch.setattr(socket, "socket", no_route)
    monkeypatch.setattr(socket, "gethostbyname", no_route)
    assert _dashboard_display_host("0.0.0.0") == "127.0.0.1"


def test_dashboard_signal_handler_graceful_then_hard_exit():
    hard_exits: list[int] = []
    handler = _make_signal_handler(hard_exits.append)

    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGINT, None)
    handler(signal.SIGINT, None)

    assert hard_exits == [128 + signal.SIGINT]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX SIGINT lifecycle")
def test_dashboard_sigint_releases_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "samuel",
            "dashboard",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "SAMUEL_API_KEY": "isolated-dashboard-lifecycle-test-key"},
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail(f"dashboard exited before listening: {proc.returncode}")
                time.sleep(0.05)
        else:
            pytest.fail("dashboard did not listen within five seconds")

        proc.send_signal(signal.SIGINT)
        assert proc.wait(timeout=5) == 0

        with socket.socket() as rebound:
            rebound.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            rebound.bind(("127.0.0.1", port))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
