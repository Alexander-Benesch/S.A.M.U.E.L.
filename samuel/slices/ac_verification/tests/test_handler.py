from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from samuel.core.acceptance import AcceptanceApproval, parse_acceptance_contract
from samuel.core.bus import Bus
from samuel.core.commands import VerifyACCommand
from samuel.core.config import EvalSchema
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import Event
from samuel.slices.ac_verification.handler import (
    ACVerificationHandler,
    VerifierRunnerPolicy,
    _check_grep,
    _check_grep_not,
    _check_import_at_candidate,
    _check_test,
    _check_test_readiness,
    _resolve_test_runner,
)


class TestCheckTest:
    def test_pytest_pass_via_marker(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        completed = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=0,
            stdout="1 passed\n",
            stderr="",
        )
        with patch("samuel.slices.ac_verification.handler.subprocess.run", return_value=completed):
            result = _check_test("my_test", tmp_path)
        assert result["passed"] is True
        assert result["runner"] == "pyproject"
        assert result["exit_code"] == 0

    def test_test_output_excerpt_is_bounded_and_secret_redacted(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        secret = "ghp_" + "a" * 36
        completed = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=1,
            stdout=("x" * 600) + "\n" + secret,
            stderr="",
        )
        with patch("samuel.slices.ac_verification.handler.subprocess.run", return_value=completed):
            result = _check_test("my_test", tmp_path)

        assert result["passed"] is False
        assert len(result["output_excerpt"]) <= 500
        assert secret not in result["output_excerpt"]
        assert "***REDACTED***" in result["output_excerpt"]

    def test_runner_not_found(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        with patch(
            "samuel.slices.ac_verification.handler.subprocess.run",
            side_effect=FileNotFoundError("pytest"),
        ):
            result = _check_test("my_test", tmp_path)
        assert result["passed"] is False
        assert "not found" in result["reason"]

    def test_timeout(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        with patch(
            "samuel.slices.ac_verification.handler.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=60),
        ):
            result = _check_test("my_test", tmp_path)
        assert result["passed"] is False
        assert "timeout" in result["reason"]

    def test_environment_setup_error_is_fail_closed_without_error_content(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        sentinel = "test-sentinel-not-a-credential"
        with patch(
            "samuel.slices.ac_verification.handler.verifier_process_environment",
            side_effect=OSError(sentinel),
        ):
            result = _check_test("my_test", tmp_path)

        assert result["passed"] is False
        assert result["status"] == "error"
        assert sentinel not in str(result)
        assert result["process_environment_profile"] == "verifier-sterile.v1"

    def test_no_runner_configured_is_manual(self, tmp_path: Path):
        result = _check_test("my_test", tmp_path)
        assert result["passed"] is False
        assert result.get("manual") is True
        assert "no test runner" in result["reason"]

    def test_test_without_runner_remains_automatic_failure_in_summary(self, tmp_path: Path):
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("ACFailed", events.append)
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        result = handler.handle(
            VerifyACCommand(payload={"plan_text": "- [ ] [TEST] test_missing_runner"})
        )

        assert result["automatic_total"] == 1
        assert result["automatic_failed"] == 1
        assert result["manual_pending"] == 0
        assert len(events) == 1

    def test_invalid_name_rejected(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        result = _check_test("name with spaces; rm -rf /", tmp_path)
        assert result["passed"] is False
        assert "rejected" in result["reason"]
        assert result["runner_policy_source"] == "control_plane"
        assert result["runner_policy_version"] == "schema-default"

    def test_control_plane_test_cmd_overrides_marker(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        policy = VerifierRunnerPolicy.from_eval_config(
            EvalSchema(
                test_cmd='custom-runner --filter "{test}"',
                test_timeout=30,
            )
        )
        resolved = _resolve_test_runner(tmp_path, "my_test", policy)
        assert resolved is not None
        cmd, timeout, runner = resolved
        assert cmd == ["custom-runner", "--filter", "my_test"]
        assert timeout == 30
        assert runner == "config"

    def test_unittest_readiness_accepts_dotted_module_without_execution(self, tmp_path: Path):
        import sys as _sys

        policy = VerifierRunnerPolicy.from_eval_config(
            EvalSchema(test_cmd=f"{_sys.executable} -m unittest {{test}}")
        )

        with patch("samuel.slices.ac_verification.handler.subprocess.run") as run:
            result = _check_test_readiness("tests.test_board", tmp_path, policy)

        assert result["passed"] is True
        assert result["status"] == "ready"
        assert result["runner_kind"] == "unittest"
        run.assert_not_called()

    def test_unittest_readiness_rejects_pytest_node_id_without_execution(self, tmp_path: Path):
        import sys as _sys

        policy = VerifierRunnerPolicy.from_eval_config(
            EvalSchema(test_cmd=f"{_sys.executable} -m unittest {{test}}")
        )

        with patch("samuel.slices.ac_verification.handler.subprocess.run") as run:
            result = _check_test_readiness(
                "tests/test_board.py::TestLeaderboard::test_highest_score_first",
                tmp_path,
                policy,
            )

        assert result["passed"] is False
        assert result["status"] == "incompatible_selector"
        assert result["runner_kind"] == "unittest"
        assert "tests.test_module" in result["reason"]
        run.assert_not_called()

    def test_pytest_node_id_rejects_keyword_bound_placeholder(self, tmp_path: Path):
        import sys as _sys

        policy = VerifierRunnerPolicy.from_eval_config(
            EvalSchema(test_cmd=f"{_sys.executable} -m pytest -q -k {{test}}")
        )

        with patch("samuel.slices.ac_verification.handler.subprocess.run") as run:
            result = _check_test_readiness(
                "tests/test_board.py::TestLeaderboard::test_highest_score_first",
                tmp_path,
                policy,
            )

        assert result["passed"] is False
        assert result["status"] == "incompatible_selector"
        assert "direct positional argument" in result["reason"]
        run.assert_not_called()

    def test_pytest_logical_selector_allows_keyword_bound_placeholder(self, tmp_path: Path):
        import sys as _sys

        policy = VerifierRunnerPolicy.from_eval_config(
            EvalSchema(test_cmd=f"{_sys.executable} -m pytest -q -k {{test}}")
        )

        result = _check_test_readiness("highest_score_first", tmp_path, policy)

        assert result["passed"] is True
        assert result["runner_kind"] == "pytest"

    def test_external_python_pytest_module_is_not_assumed_available(self, tmp_path: Path):
        external_python = tmp_path / "python9"
        external_python.write_text("#!/bin/sh\nexit 0\n")
        external_python.chmod(0o700)
        policy = VerifierRunnerPolicy.from_eval_config(
            EvalSchema(test_cmd=f"{external_python} -m pytest -q {{test}}")
        )

        result = _check_test_readiness("test_example", tmp_path, policy)

        assert result["passed"] is False
        assert result["status"] == "missing_evidence"
        assert "active environment" in result["reason"]

    def test_planning_phase_reports_missing_runner_before_candidate(self, tmp_path: Path):
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", events.append)
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        result = handler.handle(
            VerifyACCommand(
                payload={
                    "plan_text": "- [ ] [TEST] tests.test_board",
                    "issue": 756,
                    "phase": "planning",
                }
            )
        )

        check = result["results"][0]
        assert result["verified"] is False
        assert result["runner_readiness_failed"] == 1
        assert check["passed"] is None
        assert check["runner_ready"] is False
        assert check["readiness_status"] == "missing_evidence"
        assert check["deferred"] is True
        assert not events

    def test_candidate_eval_config_cannot_override_control_plane_policy(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "eval.json").write_text(
            '{"test_cmd":"candidate-command {test}","test_timeout":1}'
        )
        policy = VerifierRunnerPolicy.from_eval_config(
            EvalSchema(test_cmd="trusted-command {test}", test_timeout=41)
        )

        resolved = _resolve_test_runner(tmp_path, "my_test", policy)

        assert resolved == (["trusted-command", "my_test"], 41, "config")

    def test_candidate_eval_config_cannot_override_marker_defaults(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "eval.json").write_text(
            '{"test_cmd":"candidate-command {test}","test_timeout":1}'
        )

        resolved = _resolve_test_runner(tmp_path, "my_test")

        assert resolved is not None
        cmd, timeout, runner = resolved
        assert "candidate-command" not in cmd
        assert timeout == 60
        assert runner == "pyproject"

    def test_multi_language_routing_jest(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        resolved = _resolve_test_runner(tmp_path, "my_test")
        assert resolved is not None
        cmd, _timeout, runner = resolved
        assert cmd[0] == "npx" and "jest" in cmd
        assert runner == "package"

    def test_multi_language_routing_go(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module x\n")
        resolved = _resolve_test_runner(tmp_path, "my_test")
        assert resolved is not None
        cmd, _timeout, runner = resolved
        assert cmd[0] == "go" and "test" in cmd
        assert runner == "go"

    def test_multi_language_routing_cargo(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        resolved = _resolve_test_runner(tmp_path, "my_test")
        assert resolved is not None
        cmd, _timeout, runner = resolved
        assert cmd[0] == "cargo"
        assert runner == "Cargo"

    def test_test_runner_uses_sys_executable_for_pyproject(self, tmp_path: Path):
        """#254: pyproject-Marker liefert sys.executable -m pytest, nicht bare pytest.
        So funktioniert die Ausführung auch ohne PATH-aktivierte venv."""
        import sys as _sys

        (tmp_path / "pyproject.toml").write_text("[project]\n")
        resolved = _resolve_test_runner(tmp_path, "test_x")
        assert resolved is not None
        cmd, _timeout, runner = resolved
        assert cmd[0] == _sys.executable
        assert cmd[1:3] == ["-m", "pytest"]
        assert "test_x" in cmd
        assert runner == "pyproject"

    def test_pytest_node_id_is_invoked_directly(self, tmp_path: Path):
        import sys as _sys

        (tmp_path / "pyproject.toml").write_text("[project]\n")
        node_id = "tests/test_example.py::test_selected[param-1]"
        resolved = _resolve_test_runner(tmp_path, node_id)
        assert resolved is not None
        cmd, _timeout, runner = resolved
        assert cmd == [_sys.executable, "-m", "pytest", "-q", node_id]
        assert "-k" not in cmd
        assert runner == "pyproject"

    def test_simple_pytest_name_keeps_k_fallback(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        resolved = _resolve_test_runner(tmp_path, "test_selected")
        assert resolved is not None
        cmd, _timeout, _runner = resolved
        assert cmd[-2:] == ["-k", "test_selected"]

    def test_pytest_node_id_rejects_traversal(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        result = _check_test("../test_example.py::test_selected", tmp_path)
        assert result["passed"] is False
        assert "node id rejected" in result["reason"]

    def test_test_runner_other_languages_unchanged(self, tmp_path: Path):
        """#254: nur Python-Marker geändert; jest/go/cargo/mvn unverändert auf PATH."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        resolved = _resolve_test_runner(tmp_path, "test_x")
        assert resolved is not None
        cmd, _timeout, _ = resolved
        assert cmd[0] == "cargo"
        assert "{test}" not in " ".join(cmd)

    def test_test_run_completed_event_published(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        completed = subprocess.CompletedProcess(
            args=["pytest"],
            returncode=0,
            stdout="",
            stderr="",
        )
        captured: list[Event] = []
        bus = Bus()
        bus.subscribe("TestRunCompleted", lambda e: captured.append(e))

        with patch("samuel.slices.ac_verification.handler.subprocess.run", return_value=completed):
            handler = ACVerificationHandler(bus, project_root=tmp_path)
            cmd = VerifyACCommand(payload={"plan_text": "- [ ] [TEST] my_test", "issue": 42})
            handler.handle(cmd)

        assert len(captured) == 1
        evt = captured[0]
        assert evt.payload["test_name"] == "my_test"
        assert evt.payload["passed"] is True
        assert evt.payload["issue"] == 42
        assert evt.payload["process_environment_profile"] == "verifier-sterile.v1"

    def test_python_test_receives_no_parent_credentials(self, tmp_path: Path, monkeypatch):
        secret_names = (
            "SCM_TOKEN",
            "OPENROUTER_API_KEY",
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_ASKPASS",
            "SAMUEL_GIT_ASKPASS_SECRET",
            "SAMUEL_GIT_ASKPASS_USERNAME",
            "SSH_AUTH_SOCK",
            "GPG_TTY",
            "AWS_SECRET_ACCESS_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "AZURE_CLIENT_SECRET",
            "PYTHONPATH",
        )
        for name in secret_names:
            monkeypatch.setenv(name, "test-sentinel-not-a-credential")
        monkeypatch.setenv("HOME", "/operator/home")
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        (tmp_path / "test_environment.py").write_text(
            "import os\n"
            "from pathlib import Path\n\n"
            "def test_sterile_environment():\n"
            f"    forbidden = {secret_names!r}\n"
            "    assert all(name not in os.environ for name in forbidden)\n"
            "    assert os.environ['HOME'] != '/operator/home'\n"
            "    assert Path(os.environ['HOME']).is_dir()\n"
            "    assert Path(os.environ['TMPDIR']).is_dir()\n",
            encoding="utf-8",
        )

        result = _check_test("test_environment.py::test_sterile_environment", tmp_path)

        assert result["passed"] is True
        assert result["process_environment_profile"] == "verifier-sterile.v1"

    def test_non_python_runner_does_not_load_parent_shell_profile(
        self, tmp_path: Path, monkeypatch
    ):
        profile_marker = tmp_path / "profile-loaded"
        profile = tmp_path / "operator-profile"
        profile.write_text(f"touch {profile_marker}\n", encoding="utf-8")
        runner = tmp_path / "trusted-runner"
        runner.write_text(
            "#!/bin/bash\n"
            'test -z "${SCM_TOKEN:-}"\n'
            'test "$HOME" != /operator/home\n'
            'test -d "$TMPDIR"\n',
            encoding="utf-8",
        )
        runner.chmod(0o700)
        monkeypatch.setenv("BASH_ENV", str(profile))
        monkeypatch.setenv("SCM_TOKEN", "test-sentinel-not-a-credential")
        monkeypatch.setenv("HOME", "/operator/home")
        policy = VerifierRunnerPolicy.from_eval_config(EvalSchema(test_cmd=f"{runner} {{test}}"))

        result = _check_test("focused_check", tmp_path, policy)

        assert result["passed"] is True
        assert not profile_marker.exists()
        assert result["process_environment_profile"] == "verifier-sterile.v1"


def test_candidate_import_receives_no_parent_credentials(tmp_path: Path, monkeypatch) -> None:
    secret_names = (
        "SCM_TOKEN",
        "OPENROUTER_API_KEY",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_ASKPASS",
        "SAMUEL_GIT_ASKPASS_SECRET",
        "SAMUEL_GIT_ASKPASS_USERNAME",
        "SSH_ASKPASS",
        "GPG_TTY",
        "AWS_SESSION_TOKEN",
        "PYTHONPATH",
    )
    for name in secret_names:
        monkeypatch.setenv(name, "test-sentinel-not-a-credential")
    monkeypatch.setenv("HOME", "/operator/home")
    (tmp_path / "environment_probe.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        f"forbidden = {secret_names!r}\n"
        "assert all(name not in os.environ for name in forbidden)\n"
        "assert os.environ['HOME'] != '/operator/home'\n"
        "assert Path(os.environ['XDG_CONFIG_HOME']).is_dir()\n",
        encoding="utf-8",
    )

    result = _check_import_at_candidate("environment_probe", tmp_path)

    assert result["passed"] is True
    assert result["process_environment_profile"] == "verifier-sterile.v1"


class TestExtractArg:
    """#236: Tag-spezifische Argument-Extraktion."""

    def test_diff_extracts_first_token_only(self, tmp_path: Path):
        from samuel.slices.ac_verification.handler import _extract_arg

        assert _extract_arg("DIFF", "handler.py — Beschreibung") == "handler.py"
        assert _extract_arg("DIFF", "samuel/server.py") == "samuel/server.py"

    def test_test_handles_em_dash_separator(self, tmp_path: Path):
        from samuel.slices.ac_verification.handler import _extract_arg

        assert _extract_arg("TEST", "my_test — Beschreibung") == "my_test"
        assert _extract_arg("TEST", "test_x – kurze Notiz") == "test_x"
        assert _extract_arg("TEST", "test_y -- ASCII-trenner") == "test_y"

    def test_grep_extracts_quoted_string(self, tmp_path: Path):
        from samuel.slices.ac_verification.handler import _extract_arg

        assert _extract_arg("GREP", '"foo bar" — Beschreibung') == "foo bar"
        assert _extract_arg("GREP:NOT", "'baz' — gone") == "baz"

    @pytest.mark.parametrize("tag", ["GREP", "GREP:NOT"])
    def test_grep_unwraps_one_markdown_inline_code_pattern(self, tag: str):
        from samuel.slices.ac_verification.handler import _extract_arg

        assert (
            _extract_arg(tag, '`token = "synthetic-demo-value"`')
            == 'token = "synthetic-demo-value"'
        )

    def test_grep_keeps_unquoted_multiword_pattern(self):
        from samuel.slices.ac_verification.handler import _extract_arg

        assert _extract_arg("GREP", "class MyHandler") == "class MyHandler"

    def test_grep_rejects_apparent_path_suffix(self):
        from samuel.slices.ac_verification.handler import _extract_arg

        with pytest.raises(ValueError, match="does not support a path or other suffix"):
            _extract_arg("GREP", '"marker" game/domain/board.py')

    def test_manual_keeps_full_description(self, tmp_path: Path):
        from samuel.slices.ac_verification.handler import _extract_arg

        msg = "User klickt Button — kein Em-Dash-Stripping"
        assert _extract_arg("MANUAL", msg) == msg

    def test_exists_extracts_first_token_only(self, tmp_path: Path):
        from samuel.slices.ac_verification.handler import _extract_arg

        assert (
            _extract_arg("EXISTS", "samuel/core/ai_act.py — moved-Datei") == "samuel/core/ai_act.py"
        )

    @pytest.mark.parametrize("tag", ["DIFF", "EXISTS", "IMPORT"])
    def test_path_like_tag_unwraps_one_markdown_inline_code_token(self, tag: str):
        from samuel.slices.ac_verification.handler import _extract_arg

        assert _extract_arg(tag, "`game/web/settings.py`") == "game/web/settings.py"

    def test_unmatched_or_unsafe_inline_code_remains_rejected(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        unmatched = handler.handle(
            VerifyACCommand(payload={"plan_text": "- [ ] [EXISTS] `candidate.py"})
        )
        traversal = handler.handle(
            VerifyACCommand(payload={"plan_text": "- [ ] [EXISTS] `../outside.py`"})
        )

        assert unmatched["results"][0]["status"] == "error"
        assert traversal["results"][0]["status"] == "error"

    def test_arg_separators_are_centralized_in_acceptance_contract(self):
        """#283/#754: Beschreibungstrenner besitzen genau eine Core-Authority."""
        src = Path(__file__).parent.parent.joinpath("handler.py").read_text(encoding="utf-8")
        core = (
            Path(__file__).parents[3].joinpath("core", "acceptance.py").read_text(encoding="utf-8")
        )

        assert "_ARG_SEPARATORS = (" not in src
        assert core.count("_CRITERION_DESCRIPTION_SEPARATORS = (") == 1


class TestGrepSprachneutral:
    """#236-Mitfix: _check_grep nutzt iter_project_files statt rglob('*.py')."""

    def test_grep_searches_non_python_files(self, tmp_path: Path):
        # .go-Datei mit Pattern — muss gefunden werden (Sprachneutralitaet)
        content = "package main\n// magic_marker_xyz\n"
        (tmp_path / "main.go").write_text(content)
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = '- [ ] [GREP] "magic_marker_xyz"'
        result = handler.handle(VerifyACCommand(payload={"plan_text": plan}))
        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_planning_phase_defers_target_state_without_false_failure(self, tmp_path: Path):
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", events.append)
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = '- [ ] [GREP] "future_marker"'

        result = handler.handle(
            VerifyACCommand(payload={"plan_text": plan, "issue": 417, "phase": "planning"})
        )

        assert result["verified"] is True
        assert result["deferred"] == 1
        assert result["results"][0]["passed"] is None
        assert result["results"][0]["deferred"] is True
        assert not any(event.name == "ACFailed" for event in events)

    def test_post_implementation_phase_still_fails_missing_target_state(self, tmp_path: Path):
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", events.append)
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = '- [ ] [GREP] "future_marker"'

        result = handler.handle(VerifyACCommand(payload={"plan_text": plan, "issue": 417}))

        assert result["results"][0]["passed"] is False
        assert any(event.name == "ACFailed" for event in events)

    def test_planning_phase_defers_new_diff_path_without_false_failure(self, tmp_path: Path):
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", events.append)
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = "- [ ] [DIFF] future_file.py"

        result = handler.handle(
            VerifyACCommand(payload={"plan_text": plan, "issue": 417, "phase": "planning"})
        )

        assert result["results"][0]["deferred"] is True
        assert not any(event.name == "ACFailed" for event in events)

    def test_grep_searches_typescript_files(self, tmp_path: Path):
        (tmp_path / "app.ts").write_text("const x = 'magic_ts_marker';\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = '- [ ] [GREP] "magic_ts_marker"'
        result = handler.handle(VerifyACCommand(payload={"plan_text": plan}))
        assert result["results"][0]["passed"] is True

    def test_grep_searches_yaml_files(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("key: magic_yaml_marker\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = '- [ ] [GREP] "magic_yaml_marker"'
        result = handler.handle(VerifyACCommand(payload={"plan_text": plan}))
        assert result["results"][0]["passed"] is True


class TestGrepRelativeRoot:
    """#280: _check_grep darf bei beliebiger project_root-Form nicht crashen.

    Reproduktion: project_root=Path('.') (relativ) trifft auf src_file mit
    absolutem Pfad (iter_project_files resolved root intern). relative_to
    wirft ValueError. Fix: Fallback-Kaskade auf project_root.resolve(),
    dann src_file.name als Last-Resort.
    """

    def test_check_grep_relative_project_root(self, tmp_path: Path, monkeypatch):
        # cwd auf tmp_path zeigen, damit Path('.') tmp_path entspricht
        monkeypatch.chdir(tmp_path)
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "code.py").write_text("magic_marker_280\n")

        result = _check_grep("magic_marker_280", Path("."))

        assert result["passed"] is True
        # kein Crash, Reason enthaelt entweder relativen Pfad oder Dateiname
        assert "code.py" in result["reason"]

    def test_check_grep_resolved_project_root(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file.py").write_text("abs_marker_280\n")

        result = _check_grep("abs_marker_280", tmp_path.resolve())

        assert result["passed"] is True
        assert "file.py" in result["reason"]

    def test_check_grep_not_relative_root(self, tmp_path: Path, monkeypatch):
        # GREP:NOT mit relativem project_root und nicht-vorhandenem Pattern
        # → passed=True (confirmed absent), kein Crash auf relative_to-Pfad
        monkeypatch.chdir(tmp_path)
        (tmp_path / "file.py").write_text("unrelated content\n")

        result = _check_grep_not("never_present_marker_280", Path("."))

        assert result["passed"] is True
        assert "never_present_marker_280" in result["reason"]


class TestACEventsPublished:
    """Every AC publishes its truthful automatic/readiness state."""

    def test_ac_verified_event_published(self, tmp_path: Path):
        (tmp_path / "exists.py").write_text("# existing\n")
        bus = Bus()
        captured: list = []
        bus.subscribe("ACVerified", lambda e: captured.append(e))
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = "- [ ] [DIFF] exists.py"
        handler.handle(VerifyACCommand(payload={"plan_text": plan, "issue": 236}))
        assert len(captured) == 1
        evt = captured[0]
        assert evt.payload["issue"] == 236
        assert evt.payload["tag"] == "DIFF"
        assert evt.payload["arg"] == "exists.py"
        assert evt.payload["passed"] is True
        assert evt.payload["evt"] == "ac_verified"

    def test_ac_failed_event_published(self, tmp_path: Path):
        bus = Bus()
        captured: list = []
        bus.subscribe("ACFailed", lambda e: captured.append(e))
        handler = ACVerificationHandler(bus, project_root=tmp_path)
        plan = "- [ ] [DIFF] missing.py — sollte fehlen"
        handler.handle(VerifyACCommand(payload={"plan_text": plan, "issue": 236}))
        assert len(captured) == 1
        evt = captured[0]
        assert evt.payload["passed"] is False
        assert evt.payload["evt"] == "ac_failed"
        # arg darf NICHT die Em-Dash-Beschreibung enthalten
        assert evt.payload["arg"] == "missing.py"

    def test_manual_pending_event_is_not_automatic_failure(self):
        bus = Bus()
        pending: list = []
        failed: list = []
        verified: list = []
        bus.subscribe("ACManualPending", lambda e: pending.append(e))
        bus.subscribe("ACFailed", lambda e: failed.append(e))
        bus.subscribe("ACVerified", lambda e: verified.append(e))
        handler = ACVerificationHandler(bus)

        handler.handle(
            VerifyACCommand(
                payload={
                    "plan_text": "- [x] [MANUAL] Check the UI visually",
                    "issue": 514,
                }
            )
        )

        assert len(pending) == 1
        assert failed == []
        assert verified == []
        assert pending[0].payload == {
            "issue": 514,
            "tag": "MANUAL",
            "arg": "Check the UI visually",
            "passed": None,
            "status": "manual_pending",
            "reason": "manual check required: Check the UI visually",
            "evt": "ac_manual_pending",
        }


class TestDiffCheck:
    def test_diff_passes_when_file_exists(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [DIFF] handler.py"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True
        assert result["results"][0]["tag"] == "DIFF"

    def test_diff_fails_when_file_missing(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [DIFF] nonexistent.py"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False


class TestExistsCheck:
    def test_exists_passes_when_file_present(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("key: value\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [EXISTS] config.yaml"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_exists_fails_when_missing(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [EXISTS] missing.yaml"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False


class TestImportCheck:
    def test_import_passes_for_safe_stdlib(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [IMPORT] json"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_import_fails_for_nonexistent_module(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [IMPORT] nonexistent_module_xyz_123"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False
        assert "import failed" in result["results"][0]["reason"]

    def test_import_blocks_injection(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = '- [ ] [IMPORT] os; os.system("rm -rf /")'
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["results"][0]["passed"] is False
        assert "rejected" in result["results"][0]["reason"]

    def test_import_blocks_dangerous_modules(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        for module in ["os", "sys", "subprocess", "shutil"]:
            plan = f"- [ ] [IMPORT] {module}"
            cmd = VerifyACCommand(payload={"plan_text": plan})
            result = handler.handle(cmd)
            assert result["results"][0]["passed"] is False
            assert "blocked module" in result["results"][0]["reason"]


class TestPathTraversal:
    def test_path_traversal_blocked(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [DIFF] ../../../etc/passwd"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["results"][0]["passed"] is False
        assert "traversal blocked" in result["results"][0]["reason"]

    def test_exists_traversal_blocked(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [EXISTS] ../../etc/shadow"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["results"][0]["passed"] is False
        assert "traversal blocked" in result["results"][0]["reason"]


class TestGrepCheck:
    def test_grep_finds_pattern(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("class MyHandler:\n    pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP] class MyHandler"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_grep_fails_when_pattern_absent(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def something(): pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP] class MissingClass"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False


class TestGrepNotCheck:
    def test_grep_not_passes_when_absent(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def clean_code(): pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP:NOT] deprecated_function"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_grep_not_fails_when_present(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def deprecated_function(): pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP:NOT] deprecated_function"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False


class TestManualCheck:
    def test_manual_is_pending_and_not_automatically_verified(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [MANUAL] Check the UI visually"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is None
        assert result["results"][0]["status"] == "manual_pending"
        assert result["results"][0]["manual"] is True
        assert result["manual"] == 1
        assert result["manual_pending"] == 1
        assert result["automatic_total"] == 0
        assert result["automatic_passed"] == 0
        assert result["automatic_failed"] == 0


class TestUnknownTag:
    def test_unknown_tag_fails_gracefully(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [FOOBAR] something"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False
        assert "unknown tag" in result["results"][0]["reason"]


class TestMixedACs:
    def test_mixed_auto_checks(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("class Handler:\n    pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [EXISTS] handler.py\n- [ ] [GREP] class Handler\n"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["total"] == 2
        assert result["passed"] == 2

    def test_empty_plan_not_verified(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        cmd = VerifyACCommand(payload={"plan_text": ""})
        result = handler.handle(cmd)

        assert result["verified"] is False


class TestCommitBoundAcceptanceEvidence:
    @staticmethod
    def _repository(tmp_path: Path) -> str:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
        )
        (tmp_path / "candidate.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "candidate.py"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "candidate"], cwd=tmp_path, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _subject(contract_hash: str, head_sha: str) -> EvaluationSubject:
        return EvaluationSubject(
            repository="owner/repo",
            base_sha="a" * 40,
            head_sha=head_sha,
            contract_hash=contract_hash,
            policy_version="test.v1",
            policy_digest="sha256:" + "d" * 64,
        )

    def test_automatic_result_is_bound_to_exact_candidate_checkout(self, tmp_path: Path):
        head = self._repository(tmp_path)
        plan = "- [x] [EXISTS] candidate.py"
        contract = parse_acceptance_contract(plan)
        approved = contract.with_approval(
            AcceptanceApproval(
                state="approved",
                actor="alice",
                method="comment",
                source_id="comment:2",
                approved_at="2026-09-17T10:00:00Z",
                contract_hash=contract.contract_hash,
                plan_comment_id=1,
            )
        )
        subject = self._subject(contract.contract_hash, head)
        bus = Bus()
        events: list[Event] = []
        bus.subscribe("*", events.append)

        result = ACVerificationHandler(bus, project_root=tmp_path).handle(
            VerifyACCommand(
                subject=subject,
                payload={
                    "plan_text": plan,
                    "acceptance_contract": approved.as_dict(),
                    "changed_files": ["candidate.py"],
                },
            )
        )

        assert result["verified"] is True
        assert result["results"][0]["status"] == "passed"
        assert result["results"][0]["evidence"] == {
            "schema_version": 1,
            "kind": "exists",
            "path": "candidate.py",
            "exists": True,
        }
        assert result["acceptance_evidence"]["evaluation_subject"] == subject.as_dict()
        verified = next(event for event in events if event.name == "ACVerified")
        assert verified.payload["criterion_id"] == contract.criteria[0].criterion_id
        assert verified.payload["evaluation_subject"] == subject.as_dict()

    def test_real_planner_inline_code_exists_path_is_verified(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=tmp_path,
            check=True,
        )
        target = tmp_path / "game" / "web" / "settings.py"
        target.parent.mkdir(parents=True)
        target.write_text('token = "synthetic-demo-value"\n', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "candidate"], cwd=tmp_path, check=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        plan = "- [ ] [EXISTS] `game/web/settings.py`"
        contract = parse_acceptance_contract(plan)
        approved = contract.with_approval(
            AcceptanceApproval(
                state="approved",
                actor="alice",
                method="status:approved/polling",
                source_id="plan:1;gitea-timeline:2",
                approved_at="2026-09-22T10:01:50Z",
                contract_hash=contract.contract_hash,
                plan_comment_id=1,
            )
        )

        result = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(
                subject=self._subject(contract.contract_hash, head),
                payload={
                    "plan_text": plan,
                    "acceptance_contract": approved.as_dict(),
                    "changed_files": ["game/web/settings.py"],
                },
            )
        )

        assert contract.criteria[0].text == "`game/web/settings.py`"
        assert result["verified"] is True
        assert result["results"][0]["status"] == "passed"
        assert result["results"][0]["arg"] == "game/web/settings.py"
        assert result["results"][0]["evidence"] == {
            "schema_version": 1,
            "kind": "exists",
            "path": "game/web/settings.py",
            "exists": True,
        }

    def test_real_planner_inline_code_grep_pattern_is_verified(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=tmp_path,
            check=True,
        )
        target = tmp_path / "game" / "web" / "settings.py"
        target.parent.mkdir(parents=True)
        target.write_text('token = "synthetic-demo-value"\n', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "candidate"], cwd=tmp_path, check=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        plan = '- [ ] [GREP] `token = "synthetic-demo-value"`'
        contract = parse_acceptance_contract(plan)
        approved = contract.with_approval(
            AcceptanceApproval(
                state="approved",
                actor="alice",
                method="status:approved/polling",
                source_id="plan:1;gitea-timeline:2",
                approved_at="2026-09-22T11:10:39Z",
                contract_hash=contract.contract_hash,
                plan_comment_id=1,
            )
        )

        result = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(
                subject=self._subject(contract.contract_hash, head),
                payload={
                    "plan_text": plan,
                    "acceptance_contract": approved.as_dict(),
                    "changed_files": ["game/web/settings.py"],
                },
            )
        )

        assert contract.criteria[0].text == '`token = "synthetic-demo-value"`'
        assert result["verified"] is True
        assert result["results"][0]["status"] == "passed"
        assert result["results"][0]["arg"] == 'token = "synthetic-demo-value"'

    def test_each_automatic_tag_persists_bounded_structured_evidence(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
        )
        (tmp_path / "candidate.py").write_text("VALUE = 1\n", encoding="utf-8")
        (tmp_path / "test_candidate.py").write_text(
            "from candidate import VALUE\n\ndef test_value():\n    assert VALUE == 1\n",
            encoding="utf-8",
        )
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\npythonpath = ['.']\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "candidate"], cwd=tmp_path, check=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        plan = "\n".join(
            [
                "- [ ] [DIFF] candidate.py",
                "- [ ] [EXISTS] candidate.py",
                "- [ ] [IMPORT] candidate",
                '- [ ] [GREP] "VALUE = 1"',
                '- [ ] [GREP:NOT] "FORBIDDEN"',
                "- [ ] [TEST] test_candidate.py::test_value",
            ]
        )
        contract = parse_acceptance_contract(plan)

        result = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(
                subject=self._subject(contract.contract_hash, head),
                payload={
                    "plan_text": plan,
                    "acceptance_contract": contract.as_dict(),
                    "changed_files": ["candidate.py"],
                },
            )
        )

        assert result["verified"] is True
        evidence_by_tag = {item["tag"]: item["evidence"] for item in result["results"]}
        assert {tag: evidence["kind"] for tag, evidence in evidence_by_tag.items()} == {
            "DIFF": "diff",
            "EXISTS": "exists",
            "IMPORT": "import",
            "GREP": "grep",
            "GREP:NOT": "grep:not",
            "TEST": "test",
        }
        assert all(evidence["schema_version"] == 1 for evidence in evidence_by_tag.values())
        assert len(evidence_by_tag["TEST"]["output_excerpt"]) <= 500
        assert evidence_by_tag["TEST"]["runner_policy_source"] == "control_plane"
        assert evidence_by_tag["TEST"]["runner_policy_version"] == EvalSchema().test_policy_version
        assert evidence_by_tag["TEST"]["process_environment_profile"] == ("verifier-sterile.v1")
        assert evidence_by_tag["IMPORT"]["process_environment_profile"] == ("verifier-sterile.v1")

    def test_stale_contract_and_unknown_head_never_verify(self, tmp_path: Path):
        head = self._repository(tmp_path)
        plan = "- [ ] [EXISTS] candidate.py"
        contract = parse_acceptance_contract(plan)
        subject = self._subject(contract.contract_hash, head)
        stale = parse_acceptance_contract("- [ ] [EXISTS] other.py")

        stale_result = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(
                subject=subject,
                payload={"plan_text": plan, "acceptance_contract": stale.as_dict()},
            )
        )
        missing_head = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(
                subject=self._subject(contract.contract_hash, "f" * 40),
                payload={"plan_text": plan, "acceptance_contract": contract.as_dict()},
            )
        )

        assert stale_result["status"] == "missing_evidence"
        assert missing_head["results"][0]["status"] == "error"

    def test_import_runs_in_fresh_candidate_interpreter(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
        )
        (tmp_path / "candidate_module.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "candidate_module.py"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "candidate"], cwd=tmp_path, check=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        plan = "- [ ] [IMPORT] candidate_module"
        contract = parse_acceptance_contract(plan)

        result = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(
                subject=self._subject(contract.contract_hash, head),
                payload={"plan_text": plan, "acceptance_contract": contract.as_dict()},
            )
        )

        assert result["results"][0]["status"] == "passed"
        assert result["results"][0]["exit_code"] == 0

    def test_manual_requires_exact_human_receipt(self, tmp_path: Path):
        head = self._repository(tmp_path)
        plan = "- [x] [MANUAL] Dashboard prüfen"
        contract = parse_acceptance_contract(plan)
        subject = self._subject(contract.contract_hash, head)
        criterion_id = contract.criteria[0].criterion_id
        payload: dict[str, Any] = {
            "plan_text": plan,
            "acceptance_contract": contract.as_dict(),
            "manual_receipts": {
                criterion_id: {
                    "criterion_id": criterion_id,
                    "actor": "alice",
                    "source_id": "comment:3",
                    "contract_hash": contract.contract_hash,
                    "head_sha": head,
                }
            },
        }

        accepted = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(subject=subject, payload=payload)
        )
        payload["manual_receipts"][criterion_id]["head_sha"] = "e" * 40
        stale = ACVerificationHandler(Bus(), project_root=tmp_path).handle(
            VerifyACCommand(subject=subject, payload=payload)
        )

        assert accepted["results"][0]["status"] == "passed"
        assert stale["results"][0]["status"] == "manual_pending"
