from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import CreatePRCommand
from samuel.core.events import Event
from samuel.core.ports import IExternalGate, IVersionControl
from samuel.core.types import PR, Comment, GateContext, GateResult, Issue
from samuel.slices.pr_gates.handler import PRGatesHandler


class MockSCM(IVersionControl):
    def __init__(self, plan_comment: str = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] h.py"):
        self._plan = plan_comment

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return [Comment(id=1, body=self._plan, user="bot")]

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=2, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestPRGatesHandler:
    def test_all_gates_pass(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [1,2,3,4,5,6,7,8,9,10,11,12,"13a","13b"], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is True
        assert any(e.name == "PRCreated" for e in events)

    def test_required_gate_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [1], "optional": [], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is False
        assert any(e.name == "GateFailed" for e in events)
        assert not any(e.name == "PRCreated" for e in events)

    def test_optional_gate_warns_but_passes(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [1], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is True
        assert any(e.name == "PRCreated" for e in events)

    def test_disabled_gate_skipped(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [1], "optional": [], "disabled": [1], "custom": []}')
        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is True

    def test_no_config_defaults_to_all_required(self, tmp_path: Path):
        bus = Bus()
        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path / "nonexistent"))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result is not None

    def test_correlation_id_flows(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [1], "optional": [], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        handler.handle(CreatePRCommand(issue_number=42, branch="main", correlation_id="gate-corr-1"))

        for e in events:
            assert e.correlation_id == "gate-corr-1"

    def test_external_gate_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class FailingGate(IExternalGate):
            name = "secrets_scan"
            def run(self, context: GateContext) -> GateResult:
                return GateResult(gate="secrets_scan", passed=False, reason="Secrets found")

        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(
            bus, scm=MockSCM(), config_dir=str(tmp_path),
            external_gates=[FailingGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is False
        assert any(e.name == "GateFailed" for e in events)

    def test_external_gate_passes(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class PassingGate(IExternalGate):
            name = "lint_check"
            def run(self, context: GateContext) -> GateResult:
                return GateResult(gate="lint_check", passed=True, reason="All clean")

        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(
            bus, scm=MockSCM(), config_dir=str(tmp_path),
            external_gates=[PassingGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is True

    def test_external_gate_exception_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class BrokenGate(IExternalGate):
            name = "broken"
            def run(self, context: GateContext) -> GateResult:
                raise ConnectionError("timeout")

        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(
            bus, scm=MockSCM(), config_dir=str(tmp_path),
            external_gates=[BrokenGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is False

    def test_pr_created_on_scm(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')

        class PRCreatingSCM(MockSCM):
            def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
                return PR(id=1, number=99, title=title, html_url="http://gitea/pr/99")

        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=PRCreatingSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True
        assert result["pr_number"] == 99
        assert result["pr_url"] == "http://gitea/pr/99"

        pr_event = next(e for e in events if e.name == "PRCreated")
        assert pr_event.payload["pr_number"] == 99
        assert pr_event.payload["pr_url"] == "http://gitea/pr/99"

    def test_pr_creation_failure_still_publishes_event(self, tmp_path: Path):
        """If SCM.create_pr raises, gates still pass and PRCreated is published."""
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True
        assert "pr_number" not in result
        assert any(e.name == "PRCreated" for e in events)

    def test_publishes_gates_passed_when_all_gates_pass(self, tmp_path: Path):
        """#258: GatesPassed-Event muss vor PRCreated publisht werden, sodass
        das Dashboard die gates-Stage als 'done' anzeigen kann."""
        (tmp_path / "gates.json").write_text('{"required": [], "optional": [], "disabled": [], "custom": []}')
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True
        # GatesPassed wird publisht, mit Issue-Nr und Anzahl der Gates
        gates_passed = [e for e in events if e.name == "GatesPassed"]
        assert len(gates_passed) == 1
        assert gates_passed[0].payload["issue"] == 42
        assert "gates_run" in gates_passed[0].payload
        # Reihenfolge: GatesPassed VOR PRCreated
        names = [e.name for e in events]
        assert names.index("GatesPassed") < names.index("PRCreated")

    def test_no_gates_passed_when_blocked(self, tmp_path: Path):
        """#258: bei blockiertem Run (GateFailed) wird GatesPassed NICHT publisht."""
        (tmp_path / "gates.json").write_text(
            '{"required": [1], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        # Issue auf 'main'-Branch → Gate 1 fails → blocked
        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is False
        # Kein GatesPassed wenn ein Gate fehlschlug
        assert not any(e.name == "GatesPassed" for e in events)
        # GateFailed wurde publisht
        assert any(e.name == "GateFailed" for e in events)


class _MockConfig:
    """Test-Helper: minimaler IConfig fuer feature_flag()."""

    def __init__(self, **flags: bool) -> None:
        self._flags = flags

    def feature_flag(self, name: str) -> bool:
        return self._flags.get(name, False)


class _PRCreatingMergingSCM(MockSCM):
    """Test-Helper: create_pr liefert PR, merge_pr trackt Aufrufe."""

    def __init__(self, merge_returns: bool = True, merge_raises: bool = False):
        super().__init__()
        self.merge_calls: list[int] = []
        self._merge_returns = merge_returns
        self._merge_raises = merge_raises

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        return PR(id=1, number=99, title=title, html_url="http://gitea/pr/99")

    def merge_pr(self, pr_id: int) -> bool:
        self.merge_calls.append(pr_id)
        if self._merge_raises:
            raise RuntimeError("simulated SCM merge failure")
        return self._merge_returns


class TestAutoMerge:
    """#193: auto_merge_pr-Feature-Flag verdrahtet."""

    def _gates_open(self, tmp_path: Path) -> None:
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

    def test_auto_merge_disabled_does_not_call_merge_pr(self, tmp_path: Path):
        self._gates_open(tmp_path)
        bus = Bus()
        bus.config = _MockConfig(auto_merge_pr=False)
        events = _collect_events(bus)
        scm = _PRCreatingMergingSCM()

        handler = PRGatesHandler(bus, scm=scm, config_dir=str(tmp_path))
        handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert scm.merge_calls == [], "merge_pr darf bei flag=False nicht aufgerufen werden"
        assert not any(e.name == "PRMerged" for e in events)

    def test_auto_merge_enabled_calls_merge_pr_and_publishes(self, tmp_path: Path):
        self._gates_open(tmp_path)
        bus = Bus()
        bus.config = _MockConfig(auto_merge_pr=True)
        events = _collect_events(bus)
        scm = _PRCreatingMergingSCM(merge_returns=True)

        handler = PRGatesHandler(bus, scm=scm, config_dir=str(tmp_path))
        handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert scm.merge_calls == [99]
        merged = [e for e in events if e.name == "PRMerged"]
        assert len(merged) == 1
        assert merged[0].payload["issue"] == 42
        assert merged[0].payload["pr_number"] == 99
        assert merged[0].payload["branch"] == "samuel/issue-42"

    def test_auto_merge_enabled_merge_fails_no_event(self, tmp_path: Path):
        self._gates_open(tmp_path)
        bus = Bus()
        bus.config = _MockConfig(auto_merge_pr=True)
        events = _collect_events(bus)
        scm = _PRCreatingMergingSCM(merge_returns=False)

        handler = PRGatesHandler(bus, scm=scm, config_dir=str(tmp_path))
        handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert scm.merge_calls == [99], "merge_pr wird angefragt"
        assert not any(e.name == "PRMerged" for e in events), "ohne Erfolg kein Event"

    def test_auto_merge_enabled_scm_raises_no_event(self, tmp_path: Path):
        """Bus-Resilience §1.2 — merge_pr-Exception darf den Workflow nicht crashen."""
        self._gates_open(tmp_path)
        bus = Bus()
        bus.config = _MockConfig(auto_merge_pr=True)
        events = _collect_events(bus)
        scm = _PRCreatingMergingSCM(merge_raises=True)

        handler = PRGatesHandler(bus, scm=scm, config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True, "PRCreated/PRGates-Pass-Pfad bleibt unbeeinflusst"
        assert not any(e.name == "PRMerged" for e in events)