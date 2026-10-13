"""#368 Task 3: Symbol-Resolution-Gate."""

from __future__ import annotations

from pathlib import Path

from samuel.core.types import GateContext
from samuel.slices.symbol_resolution.gate import (
    SymbolResolutionGate,
    extract_added_imports,
    local_modules_in_diff,
)


class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def _py_diff(*lines: str) -> str:
    return "+++ b/samuel/x.py\n" + "".join(f"+{ln}\n" for ln in lines)


def _ctx(diff, files=None):
    return GateContext(
        issue_number=1, branch="b", changed_files=files or ["samuel/x.py"], diff=diff
    )


class TestExtraction:
    def test_extract_imports_py_only(self):
        diff = (
            _py_diff("import requests", "from os import path")
            + "+++ b/notes.txt\n+import shouldignore\n"
        )
        assert extract_added_imports(diff) == {"requests", "os"}

    def test_local_modules(self):
        assert local_modules_in_diff(["samuel/slices/foo/bar.py"]) >= {
            "bar",
            "foo",
            "slices",
            "samuel",
        }


class TestSymbolResolutionGate:
    def test_stdlib_import_resolved(self, tmp_path: Path):
        gate = SymbolResolutionGate(bus=_FakeBus(), project_root=tmp_path, config_dir=tmp_path)
        res = gate.run(_ctx(_py_diff("import os", "from json import dumps")))
        assert res.passed is True
        assert res.owasp_risk is None

    def test_unresolved_import_flagged_as_finding(self, tmp_path: Path):
        bus = _FakeBus()
        gate = SymbolResolutionGate(bus=bus, project_root=tmp_path, config_dir=tmp_path)
        res = gate.run(_ctx(_py_diff("import totallymadeuplib")))
        assert res.passed is True  # warn-only, blockt nicht
        assert res.owasp_risk == "LLM09:2025"
        assert any(e.name == "UnresolvedSymbol" for e in bus.events)
        ev = [e for e in bus.events if e.name == "UnresolvedSymbol"][0]
        assert ev.payload["symbols"] == ["totallymadeuplib"]

    def test_lockfile_package_resolves_import(self, tmp_path: Path):
        (tmp_path / "poetry.lock").write_text('name = "requests"\n')
        gate = SymbolResolutionGate(bus=_FakeBus(), project_root=tmp_path, config_dir=tmp_path)
        res = gate.run(_ctx(_py_diff("import requests")))
        assert res.owasp_risk is None  # durch Lockfile erklaert

    def test_first_party_import_resolved(self, tmp_path: Path):
        (tmp_path / "mymod.py").write_text("x = 1\n")
        gate = SymbolResolutionGate(bus=_FakeBus(), project_root=tmp_path, config_dir=tmp_path)
        res = gate.run(_ctx(_py_diff("import mymod")))
        assert res.owasp_risk is None

    def test_defined_in_diff_resolved(self, tmp_path: Path):
        # neue Datei helper.py im Diff -> import helper aufgeloest
        diff = "+++ b/helper.py\n+def f():\n+    pass\n" + _py_diff("import helper")
        gate = SymbolResolutionGate(bus=_FakeBus(), project_root=tmp_path, config_dir=tmp_path)
        res = gate.run(_ctx(diff, files=["helper.py", "samuel/x.py"]))
        assert res.owasp_risk is None

    def test_lockfile_change_publishes_event(self, tmp_path: Path):
        bus = _FakeBus()
        gate = SymbolResolutionGate(bus=bus, project_root=tmp_path, config_dir=tmp_path)
        diff = '+++ b/poetry.lock\n+name = "newdep"\n'
        gate.run(_ctx(diff, files=["poetry.lock"]))
        lc = [e for e in bus.events if e.name == "LockfileChanged"]
        assert lc and lc[0].payload["added"] == ["newdep"]

    def test_no_imports_passes(self, tmp_path: Path):
        gate = SymbolResolutionGate(bus=_FakeBus(), project_root=tmp_path, config_dir=tmp_path)
        res = gate.run(_ctx("+++ b/samuel/x.py\n+x = 1\n"))
        assert res.passed is True
        assert "Keine neuen Imports" in res.reason
