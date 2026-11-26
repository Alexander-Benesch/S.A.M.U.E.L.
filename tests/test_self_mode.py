from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from samuel.cli import (
    _activate_self_mode,
    _build_parser,
    _configured_target_project,
    _load_env_file,
    _shutdown_audit_sinks,
    _validate_target_project,
)
from samuel.core.config import FileConfig
from samuel.core.ports import IAuditSink
from samuel.core.types import AuditQuery


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SAMUEL_SELF_MODE", "SAMUEL_ENV_FILE", "TEST_KEY", "OVERRIDE_KEY"):
        monkeypatch.delenv(var, raising=False)


class TestLoadEnvFile:
    def test_sets_variables(self, tmp_path: Path, clean_env: None) -> None:
        env = tmp_path / ".env"
        env.write_text("TEST_KEY=value1\nOTHER=value2\n")
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "value1"
        assert os.environ["OTHER"] == "value2"

    def test_setdefault_without_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_KEY", "preexisting")
        env = tmp_path / ".env"
        env.write_text("TEST_KEY=new-value\n")
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "preexisting"

    def test_override_replaces(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY", "preexisting")
        env = tmp_path / ".env"
        env.write_text("TEST_KEY=new-value\n")
        _load_env_file(env, override=True)
        assert os.environ["TEST_KEY"] == "new-value"

    def test_ignores_comments_and_empty_lines(self, tmp_path: Path, clean_env: None) -> None:
        env = tmp_path / ".env"
        env.write_text("# comment\n\nTEST_KEY=x\n")
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "x"

    def test_strips_quotes(self, tmp_path: Path, clean_env: None) -> None:
        env = tmp_path / ".env"
        env.write_text('TEST_KEY="quoted-value"\n')
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "quoted-value"

    def test_decodes_shell_safe_special_characters(self, tmp_path: Path, clean_env: None) -> None:
        env = tmp_path / ".env"
        env.write_text("TEST_KEY='value with $ and '\"'\"' quote'\n")
        _load_env_file(env, override=False)
        assert os.environ["TEST_KEY"] == "value with $ and ' quote"

    def test_missing_file_is_noop(self, tmp_path: Path, clean_env: None) -> None:
        _load_env_file(tmp_path / "missing.env", override=False)
        assert "TEST_KEY" not in os.environ


class TestActivateSelfMode:
    def test_loads_env_then_agent_override(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text("TEST_KEY=base\nOVERRIDE_KEY=base\n")
        (tmp_path / ".env.agent").write_text("OVERRIDE_KEY=agent\n")

        agent_env = _activate_self_mode(tmp_path)

        assert os.environ["TEST_KEY"] == "base"
        assert os.environ["OVERRIDE_KEY"] == "agent"
        assert os.environ["SAMUEL_SELF_MODE"] == "1"
        assert agent_env == tmp_path / ".env.agent"

    def test_no_agent_env_still_sets_flag(self, tmp_path: Path, clean_env: None) -> None:
        (tmp_path / ".env").write_text("TEST_KEY=base\n")
        agent_env = _activate_self_mode(tmp_path)
        assert os.environ["SAMUEL_SELF_MODE"] == "1"
        assert agent_env is None


class TestConfiguredTargetProject:
    def test_reads_project_root_from_config_adjacent_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        target = tmp_path / "target"
        target.mkdir()
        (target / ".git").mkdir()
        (tmp_path / ".env").write_text("PROJECT_ROOT=target\n")
        monkeypatch.delenv("PROJECT_ROOT", raising=False)

        resolved = _configured_target_project(config_dir)

        assert resolved == target.resolve()
        assert _validate_target_project(resolved) == (True, "")

    def test_missing_target_is_rejected(self) -> None:
        ok, reason = _validate_target_project(None)

        assert ok is False
        assert "Kein Zielsystem konfiguriert" in reason
        assert "samuel run --self <nr>" in reason

    def test_non_repository_target_is_rejected(self, tmp_path: Path) -> None:
        ok, reason = _validate_target_project(tmp_path)

        assert ok is False
        assert "kein Git-Repository" in reason


class TestCliParser:
    def test_self_flag_parsed(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--self", "health"])
        assert args.self_mode is True
        assert args.command == "health"

    def test_default_is_not_self_mode(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["health"])
        assert args.self_mode is False


class TestConfigOverride:
    def test_override_takes_precedence(self, tmp_path: Path) -> None:
        (tmp_path / "agent.json").write_text('{"mode": "standard"}')
        cfg = FileConfig(tmp_path)
        assert cfg.get("agent.mode") == "standard"

        cfg._overrides["agent.mode"] = "self"
        assert cfg.get("agent.mode") == "self"

    def test_override_does_not_affect_other_keys(self, tmp_path: Path) -> None:
        (tmp_path / "agent.json").write_text('{"mode": "standard", "log_level": "INFO"}')
        cfg = FileConfig(tmp_path)
        cfg._overrides["agent.mode"] = "self"
        assert cfg.get("agent.log_level") == "INFO"


class TestSelfModeParity:
    """Self-Mode darf keine Security-Entscheidungen relaxen.

    Security-bezogene Slices dürfen SAMUEL_SELF_MODE / self_mode nicht
    referenzieren — das verhindert dass Gates oder Audit-Regeln
    im Self-Mode still abgeschaltet werden (Sandbox-Escape-Risk).
    """

    SECURITY_SLICES = [
        "samuel/slices/audit_trail",
        "samuel/slices/security",
        "samuel/slices/privacy",
        "samuel/slices/pr_gates",
    ]

    FORBIDDEN_PATTERNS = [
        "SAMUEL_SELF_MODE",
        "self_mode",
        '"--self"',
        "'--self'",
    ]

    def test_security_slices_do_not_reference_self_mode(self) -> None:
        repo_root = Path(__file__).parent.parent
        offenders: list[str] = []
        for slice_path in self.SECURITY_SLICES:
            for py_file in (repo_root / slice_path).rglob("*.py"):
                if "tests/" in str(py_file) or "test_" in py_file.name:
                    continue
                content = py_file.read_text(encoding="utf-8")
                for pattern in self.FORBIDDEN_PATTERNS:
                    if pattern in content:
                        offenders.append(f"{py_file.relative_to(repo_root)}: {pattern}")
        assert not offenders, (
            "Security-Slices dürfen Self-Mode nicht referenzieren:\n  " + "\n  ".join(offenders)
        )


class _OverrideConfig:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def set_override(self, key: str, value: Any) -> None:
        self.values[key] = value


class TestWorkflowOverrideOrdering:
    """#260: SAMUEL_WORKFLOW_OVERRIDE muss VOR bootstrap gesetzt werden,
    weil bootstrap das Workflow-File anhand des aktuellen agent.mode-Werts
    aussucht. cli.py setzte bisher den config-Override NACH bootstrap →
    Self-Mode lud standard.json statt self.json."""

    def test_self_flag_sets_workflow_override_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """--self vor bootstrap → SAMUEL_WORKFLOW_OVERRIDE=self im env."""
        monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
        # Stub bootstrap to capture env at call time
        captured: dict[str, str] = {}

        def fake_bootstrap(config_path, project_root=None, *, auto_resume=True):
            captured["env"] = os.environ.get("SAMUEL_WORKFLOW_OVERRIDE", "")
            assert auto_resume is False
            from samuel.core.bus import Bus

            b = Bus()
            b.config = _OverrideConfig()
            return b

        monkeypatch.setattr("samuel.core.bootstrap.bootstrap", fake_bootstrap)
        monkeypatch.setattr("samuel.cli.sys.exit", lambda rc: None)
        monkeypatch.setattr(
            "samuel.cli._cmd_run",
            lambda bus, args: 0,
        )
        monkeypatch.setattr(
            "samuel.cli._check_self_run_branch",
            lambda root, allow: True,
        )
        # health-cmd avoids the issue-fetch path
        from samuel.cli import main

        main(["--self", "--config", str(tmp_path), "health"])
        assert captured["env"] == "self", (
            f"--self should set SAMUEL_WORKFLOW_OVERRIDE=self, got {captured['env']!r}"
        )

    def test_no_self_flag_does_not_force_workflow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Ohne --self bleibt env-var ungesetzt (config-default greift)."""
        monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
        captured: dict[str, str] = {}

        def fake_bootstrap(config_path, project_root=None, *, auto_resume=True):
            captured["env"] = os.environ.get("SAMUEL_WORKFLOW_OVERRIDE", "")
            assert auto_resume is False
            from samuel.core.bus import Bus

            b = Bus()
            b.config = _OverrideConfig()
            return b

        monkeypatch.setattr("samuel.core.bootstrap.bootstrap", fake_bootstrap)
        monkeypatch.setattr("samuel.cli.sys.exit", lambda rc: None)
        from samuel.cli import main

        main(["--config", str(tmp_path), "health"])
        assert captured["env"] == "", (
            f"Without --self, env should be unset, got {captured['env']!r}"
        )

    def test_explicit_workflow_flag_wins_over_self(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """--workflow X (subcommand-arg von 'run') mit --self → X wird geladen,
        nicht self. Reihenfolge: explizit > implicit-self > config-default."""
        monkeypatch.delenv("SAMUEL_WORKFLOW_OVERRIDE", raising=False)
        captured: dict[str, str] = {}

        def fake_bootstrap(config_path, project_root=None):
            captured["env"] = os.environ.get("SAMUEL_WORKFLOW_OVERRIDE", "")
            from samuel.core.bus import Bus

            b = Bus()
            b.config = _OverrideConfig()
            return b

        monkeypatch.setattr("samuel.core.bootstrap.bootstrap", fake_bootstrap)
        monkeypatch.setattr("samuel.cli.sys.exit", lambda rc: None)
        monkeypatch.setattr(
            "samuel.cli._check_self_run_branch",
            lambda root, allow: True,
        )
        monkeypatch.setattr(
            "samuel.cli._cmd_run",
            lambda bus, args: 0,
        )
        from samuel.cli import main

        main(
            [
                "--self",
                "--config",
                str(tmp_path),
                "run",
                "999",
                "--workflow",
                "night",
            ]
        )
        assert captured["env"] == "night", f"--workflow night should win, got {captured['env']!r}"


class TestShutdownAuditSinks:
    """#257: CLI muss alle AsyncAuditSinks vor sys.exit drainen.

    Sonst sterben daemon-Threads mit gepufferten Workflow-Events im Queue,
    Audit-Log wird unvollständig (~30-50% Verlust beobachtet bei #254).
    """

    def test_shutdown_drains_async_sink(self) -> None:
        from samuel.adapters.audit.async_sink import AsyncAuditSink
        from samuel.core.bus import AuditMiddleware, Bus

        class _Inner:
            def __init__(self) -> None:
                self.written: list = []

            def write(self, event) -> None:
                # Slow drain — simulates real I/O
                import time

                time.sleep(0.01)
                self.written.append(event)

            def query(self, q):
                return self.written

        class _Fallback:
            def write(self, event) -> None:
                pass

            def query(self, q):
                return []

        inner = _Inner()
        sink = AsyncAuditSink(inner=inner, fallback=_Fallback(), buffer_size=100)
        bus = Bus()
        mw = AuditMiddleware(sink=sink)
        bus.add_middleware(mw)

        # Queue 30 events fast
        for i in range(30):
            sink.write({"event_name": f"E{i}", "payload": {}})

        # Without shutdown: drain not finished (30 * 10ms = 300ms expected)
        # _shutdown_audit_sinks must wait until everything is in inner
        _shutdown_audit_sinks(bus)
        assert len(inner.written) == 30, f"shutdown drained only {len(inner.written)}/30"

    def test_shutdown_drains_async_sink_inside_fanout(self) -> None:
        from samuel.adapters.audit.async_sink import AsyncAuditSink
        from samuel.adapters.audit.fanout import FanOutAuditSink
        from samuel.core.bus import AuditMiddleware, Bus

        class _Inner(IAuditSink):
            def __init__(self) -> None:
                self.written: list[Any] = []

            def write(self, event: Any) -> None:
                self.written.append(event)

            def query(self, q: AuditQuery) -> list[Any]:
                return self.written

        class _Fallback(IAuditSink):
            def write(self, event: Any) -> None:
                pass

            def query(self, q: AuditQuery) -> list[Any]:
                return []

        inner = _Inner()
        async_sink = AsyncAuditSink(inner=inner, fallback=_Fallback(), buffer_size=100)
        fanout = FanOutAuditSink([async_sink, _Inner()])
        bus = Bus()
        bus.audit_sink = fanout
        bus.add_middleware(AuditMiddleware(sink=fanout))
        for i in range(30):
            fanout.write({"event_name": f"E{i}", "payload": {}})

        _shutdown_audit_sinks(bus)

        assert len(inner.written) == 30

    def test_shutdown_handles_bus_without_sinks(self) -> None:
        """Robust gegen Bus ohne AuditMiddleware (Edge-Case bei minimal-Setups)."""
        from samuel.core.bus import Bus

        bus = Bus()
        # Should not crash
        _shutdown_audit_sinks(bus)

    def test_shutdown_handles_middleware_without_sink(self) -> None:
        """Robust gegen Middleware ohne `_sink`-Attribut (z.B. ErrorMiddleware)."""
        from samuel.core.bus import Bus, ErrorMiddleware

        bus = Bus()
        bus.add_middleware(ErrorMiddleware(bus=bus))
        # Should not crash
        _shutdown_audit_sinks(bus)


def test_self_mode_metrics_follow_configured_data_dir(tmp_path: Path) -> None:
    """#472: writer and dashboard reader share the central runtime data path."""

    import json

    from samuel.core.bus import Bus
    from samuel.slices.dashboard.handler import DashboardHandler
    from samuel.slices.implementation.handler import ImplementationHandler

    config_dir = tmp_path / "config"
    configured_data = tmp_path / "runtime-data"
    config_dir.mkdir()
    (config_dir / "agent.json").write_text(
        json.dumps({"data_dir": str(configured_data)}), encoding="utf-8"
    )
    config = FileConfig(config_dir)

    ImplementationHandler(Bus(), scm=None, llm=None, config=config)._append_self_mode_metrics(
        issue_number=472,
        duration_seconds=1.25,
        result={
            "round": 2,
            "success": True,
            "reason": "complete",
            "patches_applied": ["change"],
            "input_tokens": 10,
            "output_tokens": 5,
            "rounds_stats": [],
        },
    )

    metrics_path = configured_data / "logs" / "self_mode_metrics.jsonl"
    assert metrics_path.is_file()
    health = DashboardHandler(Bus(), config=config).get_self_mode_health()
    assert health["total"] == 1
    assert health["recent_runs"][0]["issue"] == 472
