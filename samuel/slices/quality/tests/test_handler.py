from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import RunQualityCommand
from samuel.core.ports import IQualityCheck
from samuel.slices.quality.handler import QualityHandler


def _collect_events(bus: Bus) -> list:
    events: list = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class StubPassCheck(IQualityCheck):
    supported_extensions = {".py"}

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> Any:
        return {"passed": True}


class StubFailCheck(IQualityCheck):
    supported_extensions = {".py"}

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> Any:
        return {"passed": False, "reason": "quality issue found"}


class StubWildcardCheck(IQualityCheck):
    supported_extensions = {"*"}

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def run(self, file: Path, content: str, skeleton: dict[str, Any]) -> Any:
        self.calls.append(file)
        return {"passed": True}


class TestQualityHandlerPass:
    def test_pass_when_no_checks(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is True
        event_names = [e.name for e in events]
        assert "QualityPassed" in event_names

    def test_pass_with_passing_check(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def foo(): pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[StubPassCheck()], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is True
        event_names = [e.name for e in events]
        assert "QualityPassed" in event_names
        assert "QualityFailed" not in event_names


class TestQualityHandlerFail:
    def test_fail_when_file_missing(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["nonexistent.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is False
        assert result["results"][0]["reason"] == "not found"
        event_names = [e.name for e in events]
        assert "QualityFailed" in event_names

    def test_fail_with_failing_check(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("bad code\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[StubFailCheck()], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 42})
        result = handler.handle(cmd)

        assert result["passed"] is False
        event_names = [e.name for e in events]
        assert "QualityFailed" in event_names
        assert "QualityPassed" not in event_names


class TestQualityEvents:
    def test_quality_passed_event_contains_issue(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 99})
        handler.handle(cmd)

        passed_events = [e for e in events if e.name == "QualityPassed"]
        assert len(passed_events) == 1
        assert passed_events[0].payload["issue"] == 99

    def test_quality_failed_event_contains_failures(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["missing.py"], "issue": 7})
        handler.handle(cmd)

        failed_events = [e for e in events if e.name == "QualityFailed"]
        assert len(failed_events) == 1
        assert len(failed_events[0].payload["failures"]) >= 1

    def test_correlation_id_propagated(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(
            payload={"files": ["handler.py"], "issue": 1},
            correlation_id="corr-123",
        )
        handler.handle(cmd)

        passed_events = [e for e in events if e.name == "QualityPassed"]
        assert passed_events[0].correlation_id == "corr-123"

    def test_quality_passed_propagates_branch(self, tmp_path: Path):
        """#274: branch aus RunQualityCommand-Payload muss in QualityPassed
        landen — sonst geht er in der Workflow-Chain verloren bis CreatePR
        und Gate 1 (BranchGuard) flaggt fälschlich main/master."""
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={
            "files": ["handler.py"],
            "issue": 274,
            "branch": "samuel/issue-274",
            "base": "main",
            "patches_applied": 5,
            "rounds": 2,
        })
        handler.handle(cmd)

        passed = next(e for e in events if e.name == "QualityPassed")
        assert passed.payload["branch"] == "samuel/issue-274"
        assert passed.payload["base"] == "main"
        assert passed.payload["patches_applied"] == 5
        assert passed.payload["rounds"] == 2

    def test_quality_failed_propagates_branch(self, tmp_path: Path):
        """#274: gleiche Garantie für QualityFailed."""
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={
            "files": ["missing.py"],  # triggert Failure
            "issue": 274,
            "branch": "samuel/issue-274",
            "patches_applied": 3,
        })
        handler.handle(cmd)

        failed = next(e for e in events if e.name == "QualityFailed")
        assert failed.payload["branch"] == "samuel/issue-274"
        assert failed.payload["patches_applied"] == 3

    def test_quality_passed_without_branch_does_not_crash(self, tmp_path: Path):
        """#274: Payload ohne branch/base — kein Crash, einfach kein carry."""
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        # Kein branch im Payload
        cmd = RunQualityCommand(payload={"files": ["handler.py"], "issue": 5})
        handler.handle(cmd)

        passed = next(e for e in events if e.name == "QualityPassed")
        assert "branch" not in passed.payload
        assert passed.payload["issue"] == 5

    def test_empty_files_list_passes(self, tmp_path: Path):
        bus = Bus()
        events = _collect_events(bus)
        handler = QualityHandler(bus, checks=[], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": [], "issue": 1})
        result = handler.handle(cmd)

        assert result["passed"] is True
        event_names = [e.name for e in events]
        assert "QualityPassed" in event_names

    def test_check_extension_mismatch_skipped(self, tmp_path: Path):
        (tmp_path / "readme.md").write_text("# Hello\n")
        bus = Bus()
        _collect_events(bus)
        # StubFailCheck only supports .py, so .md files skip it
        handler = QualityHandler(bus, checks=[StubFailCheck()], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["readme.md"], "issue": 1})
        result = handler.handle(cmd)

        assert result["passed"] is True

    def test_wildcard_check_runs_on_any_extension(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        (tmp_path / "readme.md").write_text("# Hello\n")
        bus = Bus()
        _collect_events(bus)
        wildcard = StubWildcardCheck()
        handler = QualityHandler(bus, checks=[wildcard], project_root=tmp_path)

        cmd = RunQualityCommand(payload={"files": ["handler.py", "readme.md"], "issue": 1})
        handler.handle(cmd)

        called_suffixes = sorted(p.suffix for p in wildcard.calls)
        assert called_suffixes == [".md", ".py"]
