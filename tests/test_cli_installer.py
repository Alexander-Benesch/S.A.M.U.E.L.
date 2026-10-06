"""#402: systemd-Unit-Generator (install-service)."""

from __future__ import annotations

from samuel.cli import _list_gitea_repos, _render_systemd_unit, _resolve_console_entrypoint


def test_unit_contains_paths_and_mode():
    unit = _render_systemd_unit(
        user="deploy",
        workdir="/srv/samuel",
        executable="/srv/samuel/.venv/bin/samuel",
        mode="watch",
    )
    assert "User=deploy" in unit
    assert "WorkingDirectory=/srv/samuel" in unit
    assert "EnvironmentFile=/srv/samuel/.env" in unit
    assert "ExecStart=/srv/samuel/.venv/bin/samuel watch" in unit
    assert "python -m samuel" not in unit
    assert "[Install]" in unit and "WantedBy=multi-user.target" in unit


def test_dashboard_mode():
    unit = _render_systemd_unit(
        user="u",
        workdir="/w",
        executable="/venv/bin/samuel",
        mode="dashboard",
    )
    assert "ExecStart=/venv/bin/samuel dashboard --configuration-mode production" in unit
    assert "S.A.M.U.E.L. (dashboard)" in unit


def test_console_entrypoint_resolution_fails_closed_without_installed_script(tmp_path, monkeypatch):
    interpreter = tmp_path / "python"
    interpreter.write_text("", encoding="utf-8")
    monkeypatch.setattr("samuel.cli.sys.executable", str(interpreter))
    monkeypatch.setattr("samuel.cli.sys.argv", ["python"])
    monkeypatch.setattr("samuel.cli.shutil.which", lambda _name: None)

    assert _resolve_console_entrypoint() is None


def test_console_entrypoint_preserves_verified_stable_release_symlink(tmp_path, monkeypatch):
    release = tmp_path / "releases" / "2.0.0a9"
    (release / "bin").mkdir(parents=True)
    (release / "venv" / "bin").mkdir(parents=True)
    launcher = release / "bin" / "samuel"
    runtime = release / "venv" / "bin" / "samuel"
    interpreter = release / "venv" / "bin" / "python"
    for path in (launcher, runtime, interpreter):
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
    current = tmp_path / "current"
    current.symlink_to(release, target_is_directory=True)
    stable = current / "bin" / "samuel"
    monkeypatch.setenv("SAMUEL_STABLE_ENTRYPOINT", str(stable))
    monkeypatch.setattr("samuel.cli.sys.executable", str(interpreter))

    assert _resolve_console_entrypoint() == stable


def test_repository_discovery_failure_is_visible(monkeypatch, caplog):
    def _raise(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    assert _list_gitea_repos("https://gitea.example.test", "secret") == []
    assert "Gitea repository list unavailable: OSError" in caplog.text


# #402/server-move: _scm_probe (repo-Endpoint + 403-Toleranz)
import json as _json  # noqa: E402
import urllib.error as _uerr  # noqa: E402
import urllib.request as _ureq  # noqa: E402

from samuel.cli import _gitea_branch_protection_probe, _scm_probe  # noqa: E402


class _FakeResp:
    def __init__(self, payload):
        self._p = _json.dumps(payload).encode()

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_probe_repo_ok(monkeypatch):
    responses = iter(
        (
            _FakeResp({"full_name": "o/r", "default_branch": "main"}),
            _FakeResp({"branch_name": "main", "enable_push": False}),
        )
    )
    monkeypatch.setattr(_ureq, "urlopen", lambda *a, **k: next(responses))
    res = _scm_probe("gitea", "http://x", "t", repo="o/r")
    assert res["ok"] and "o/r" in res["detail"]
    assert res["branch_protection"]["access"] == "ok"
    assert res["branch_protection"]["configured"] is True
    assert res["branch_protection"]["rules"]["enable_push"] is False


def test_probe_repo_read_success_reports_separate_rule_restriction(monkeypatch):
    calls = 0

    def _respond(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _FakeResp({"full_name": "o/r", "default_branch": "main"})
        raise _uerr.HTTPError("u", 403, "Forbidden", {}, None)

    monkeypatch.setattr(_ureq, "urlopen", _respond)
    res = _scm_probe("gitea", "http://x", "t", repo="o/r")

    assert res["ok"] is True
    assert res["branch_protection"]["access"] == "restricted"
    assert "Admin" not in res["branch_protection"]["detail"]
    assert "Operator" in res["branch_protection"]["detail"]


def test_probe_user_ok(monkeypatch):
    monkeypatch.setattr(_ureq, "urlopen", lambda *a, **k: _FakeResp({"login": "alice"}))
    res = _scm_probe("gitea", "http://x", "t")
    assert res["ok"] and "alice" in res["detail"]


def test_probe_403_without_repo_is_ok(monkeypatch):
    def _raise(*a, **k):
        raise _uerr.HTTPError("u", 403, "Forbidden", {}, None)

    monkeypatch.setattr(_ureq, "urlopen", _raise)
    res = _scm_probe("gitea", "http://x", "t")
    assert res["ok"] and "user-Scope" in res["detail"]


def test_probe_401_is_fail(monkeypatch):
    def _raise(*a, **k):
        raise _uerr.HTTPError("u", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(_ureq, "urlopen", _raise)
    res = _scm_probe("gitea", "http://x", "t")
    assert not res["ok"] and "401" in res["detail"]


def test_probe_403_with_repo_is_fail(monkeypatch):
    def _raise(*a, **k):
        raise _uerr.HTTPError("u", 403, "Forbidden", {}, None)

    monkeypatch.setattr(_ureq, "urlopen", _raise)
    res = _scm_probe("gitea", "http://x", "t", repo="o/r")
    assert not res["ok"]


def test_branch_protection_probe_missing_rule_is_explicit(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise _uerr.HTTPError("u", 404, "Not Found", {}, None)

    monkeypatch.setattr(_ureq, "urlopen", _raise)
    result = _gitea_branch_protection_probe("http://x", "t", "o/r", "main")

    assert result["access"] == "ok"
    assert result["configured"] is False
    assert result["branch"] == "main"


def test_branch_protection_probe_invalid_payload_is_unknown(monkeypatch):
    monkeypatch.setattr(_ureq, "urlopen", lambda *_a, **_k: _FakeResp(["unexpected"]))

    result = _gitea_branch_protection_probe("http://x", "t", "o/r", "main")

    assert result["access"] == "unknown"


def test_branch_protection_probe_unknown_error_does_not_copy_transport_text(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic-secret-in-url")

    monkeypatch.setattr(_ureq, "urlopen", fail)
    result = _gitea_branch_protection_probe("http://x", "t", "o/r", "main")
    assert result["access"] == "unknown"
    assert "synthetic-secret" not in result["detail"]
    assert "RuntimeError" in result["detail"]


def test_branch_protection_probe_http_reason_does_not_copy_provider_text(monkeypatch):
    def fail(*_args, **_kwargs):
        raise _uerr.HTTPError("u", 502, "synthetic-secret-in-reason", {}, None)

    monkeypatch.setattr(_ureq, "urlopen", fail)
    result = _gitea_branch_protection_probe("http://x", "t", "o/r", "main")
    assert result["access"] == "unknown"
    assert result["detail"] == "HTTP 502 beim Branchschutz-Read"
