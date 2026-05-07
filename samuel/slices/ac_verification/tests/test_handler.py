from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from samuel.core.bus import Bus
from samuel.core.commands import VerifyACCommand
from samuel.core.events import Event
from samuel.slices.ac_verification.handler import (
    ACVerificationHandler,
    _check_grep,
    _check_grep_not,
    _check_test,
    _resolve_test_runner,
)


class TestCheckTest:
    def test_pytest_pass_via_marker(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        completed = subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="1 passed\n", stderr="",
        )
        with patch("samuel.slices.ac_verification.handler.subprocess.run", return_value=completed):
            result = _check_test("my_test", tmp_path)
        assert result["passed"] is True
        assert result["runner"] == "pyproject"
        assert result["exit_code"] == 0

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

    def test_no_runner_configured_is_manual(self, tmp_path: Path):
        result = _check_test("my_test", tmp_path)
        assert result["passed"] is False
        assert result.get("manual") is True
        assert "no test runner" in result["reason"]

    def test_invalid_name_rejected(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        result = _check_test("name with spaces; rm -rf /", tmp_path)
        assert result["passed"] is False
        assert "rejected" in result["reason"]

    def test_test_cmd_overrides_marker(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "eval.json").write_text(
            '{"test_cmd": "custom-runner --filter {test}", "test_timeout": 30}'
        )
        cmd, timeout, runner = _resolve_test_runner(tmp_path, "my_test")
        assert cmd == ["custom-runner", "--filter", "my_test"]
        assert timeout == 30
        assert runner == "config"

    def test_multi_language_routing_jest(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name": "x"}')
        cmd, _timeout, runner = _resolve_test_runner(tmp_path, "my_test")
        assert cmd[0] == "npx" and "jest" in cmd
        assert runner == "package"

    def test_multi_language_routing_go(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module x\n")
        cmd, _timeout, runner = _resolve_test_runner(tmp_path, "my_test")
        assert cmd[0] == "go" and "test" in cmd
        assert runner == "go"

    def test_multi_language_routing_cargo(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        cmd, _timeout, runner = _resolve_test_runner(tmp_path, "my_test")
        assert cmd[0] == "cargo"
        assert runner == "Cargo"

    def test_test_runner_uses_sys_executable_for_pyproject(self, tmp_path: Path):
        """#254: pyproject-Marker liefert sys.executable -m pytest, nicht bare pytest.
        So funktioniert die Ausführung auch ohne PATH-aktivierte venv."""
        import sys as _sys
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        cmd, _timeout, runner = _resolve_test_runner(tmp_path, "test_x")
        assert cmd[0] == _sys.executable
        assert cmd[1:3] == ["-m", "pytest"]
        assert "test_x" in cmd
        assert runner == "pyproject"

    def test_test_runner_other_languages_unchanged(self, tmp_path: Path):
        """#254: nur Python-Marker geändert; jest/go/cargo/mvn unverändert auf PATH."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")
        cmd, _timeout, _ = _resolve_test_runner(tmp_path, "test_x")
        assert cmd[0] == "cargo"
        assert "{test}" not in " ".join(cmd)

    def test_test_run_completed_event_published(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        completed = subprocess.CompletedProcess(
            args=["pytest"], returncode=0, stdout="", stderr="",
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

    def test_manual_keeps_full_description(self, tmp_path: Path):
        from samuel.slices.ac_verification.handler import _extract_arg
        msg = "User klickt Button — kein Em-Dash-Stripping"
        assert _extract_arg("MANUAL", msg) == msg

    def test_exists_extracts_first_token_only(self, tmp_path: Path):
        from samuel.slices.ac_verification.handler import _extract_arg
        assert _extract_arg("EXISTS", "samuel/core/ai_act.py — moved-Datei") == "samuel/core/ai_act.py"

    def test_arg_separators_defined_once(self):
        """#283: Block 2 entfernt — nach Fix darf _ARG_SEPARATORS-Literal nur einmal
        in der Source vorkommen. Verhindert kuenftige Re-Duplikate."""
        src = Path(__file__).parent.parent.joinpath("handler.py").read_text(encoding="utf-8")
        assert src.count("_ARG_SEPARATORS = (") == 1, (
            "Duplicate _ARG_SEPARATORS-Definition wieder eingeschlichen — Block 2 von #283 "
            "darf nicht zurueckkommen."
        )


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
    """#236: pro AC wird ACVerified oder ACFailed publisht."""

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
    def test_manual_always_fails_with_flag(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [MANUAL] Check the UI visually"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False
        assert result["results"][0]["manual"] is True
        assert result["manual"] == 1


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

        plan = (
            "- [ ] [EXISTS] handler.py\n"
            "- [ ] [GREP] class Handler\n"
        )
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