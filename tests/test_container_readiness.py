from __future__ import annotations

import io
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import samuel

ROOT = Path(__file__).parents[1]


def run_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    access: str = "local_identity",
    mode: str = "production",
    healthy: bool = True,
    drift: str = "",
) -> list[str]:
    config = tmp_path / "config"
    config.mkdir(parents=True)
    (config / "auth.json").write_text(json.dumps({"access_mode": access}))
    monkeypatch.setenv("SAMUEL_RUNTIME_CONFIG_DIR", str(config))
    monkeypatch.setenv("SAMUEL_INSTALL_EXPECTED_MODE", mode)
    monkeypatch.setenv("SAMUEL_INSTALL_EXPECTED_VERSION", "2.0.0a30")
    monkeypatch.setenv("SAMUEL_INSTALL_EXPECTED_REVISION", "a" * 40)
    if access == "legacy_api_key":
        monkeypatch.setenv("SAMUEL_API_KEY", "fixture-only")
    else:
        monkeypatch.delenv("SAMUEL_API_KEY", raising=False)
    binding = {
        "product_version": "2.0.0a29" if drift == "version" else "2.0.0a30",
        "revision": "b" * 40 if drift == "revision" else "a" * 40,
    }
    monkeypatch.setattr(samuel, "__build_info__", SimpleNamespace(as_dict=lambda: binding))
    actual_mode = "wrong" if drift == "mode" else mode
    original_read = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if str(path) == "/proc/1/cmdline":
            return f"python\0/usr/local/bin/samuel\0dashboard\0--configuration-mode\0{actual_mode}\0".encode()
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    checks = {name: True for name in ("python", "git", "config", "state", "authority")}
    if drift == "authority":
        checks["authority"] = False
    health = {"healthy": healthy, "checks": checks}
    requests: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        assert timeout == 5
        requests.append(request.full_url)
        result: dict[str, Any]
        if access == "local_identity":
            assert request.full_url.endswith("/api/v1/auth/mode")
            assert not request.headers
            result = {
                "access_mode": "legacy_api_key" if drift == "auth_mode" else access,
                "identity_status": "recovery_pending" if drift == "identity" else "active",
            }
        else:
            assert request.headers.get("X-api-key") == "fixture-only"
            if request.full_url.endswith("/setup/status"):
                result = {"configuration": {"mode": actual_mode}}
            elif request.full_url.endswith("/dashboard/status"):
                result = {"build": binding}
            else:
                result = health
        return io.BytesIO(json.dumps(result).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    def run(argv: list[str], **kwargs):
        assert argv == ["samuel", "health", "--json"]
        assert kwargs == {"capture_output": True, "text": True, "timeout": 60}
        cli_health = {"healthy": healthy, "checks": {k: {"passed": v} for k, v in checks.items()}}
        output = "not-json" if drift == "malformed" else json.dumps(cli_health)
        exit_code = 2 if drift == "cli_error" else 0 if healthy else 1
        return subprocess.CompletedProcess(argv, exit_code, output, "")

    monkeypatch.setattr(subprocess, "run", run)
    match = re.search(
        r"probe='(.*?)'\n# Compare", (ROOT / "tools/samuel-container").read_text(), re.S
    )
    assert match
    exec(compile(match[1], "installed-readiness-probe", "exec"), {})
    return requests


@pytest.mark.parametrize("access", ["local_identity", "legacy_api_key"])
@pytest.mark.parametrize("mode", ["setup", "production"])
def test_installer_probe_respects_both_auth_modes(tmp_path, monkeypatch, access, mode):
    requests = run_probe(tmp_path, monkeypatch, access=access, mode=mode)
    assert len(requests) == (1 if access == "local_identity" else 3)


@pytest.mark.parametrize("access", ["local_identity", "legacy_api_key"])
@pytest.mark.parametrize("drift", ["mode", "version", "revision"])
def test_installer_probe_rejects_wrong_runtime_binding(tmp_path, monkeypatch, access, drift):
    with pytest.raises(SystemExit) as error:
        run_probe(tmp_path, monkeypatch, access=access, drift=drift)
    assert error.value.code == 42


@pytest.mark.parametrize("drift", ["auth_mode", "identity", "cli_error", "malformed"])
def test_local_identity_probe_fails_closed_without_readiness(tmp_path, monkeypatch, drift):
    with pytest.raises((AssertionError, ValueError)):
        run_probe(tmp_path, monkeypatch, drift=drift)


def test_production_probe_requires_healthy_cli(tmp_path, monkeypatch):
    with pytest.raises(AssertionError):
        run_probe(tmp_path, monkeypatch, healthy=False)


def test_setup_can_repair_scm_but_never_ignores_authority_failure(tmp_path, monkeypatch):
    run_probe(tmp_path, monkeypatch, mode="setup", healthy=False)
    with pytest.raises(AssertionError):
        run_probe(tmp_path / "other", monkeypatch, mode="setup", healthy=False, drift="authority")
