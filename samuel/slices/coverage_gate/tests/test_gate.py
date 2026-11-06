"""#368 Task 7: Coverage-Diff-Gate."""

from __future__ import annotations

from samuel.core.types import GateContext
from samuel.slices.coverage_gate.gate import CoverageDiffGate, parse_coverage_xml

_XML = """<?xml version="1.0"?>
<coverage>
 <packages><package><classes>
  <class filename="samuel/foo.py" line-rate="0.8"><lines><line number="1" hits="1"/></lines></class>
  <class filename="samuel/bar.py" line-rate="0.0"><lines><line number="1" hits="0"/></lines></class>
 </classes></package></packages>
</coverage>
"""


def _ctx(files):
    return GateContext(issue_number=1, branch="b", changed_files=files, diff="")


class TestParseCoverageXml:
    def test_hit_and_miss(self):
        cov = parse_coverage_xml(_XML)
        assert cov["samuel/foo.py"] is True
        assert cov["samuel/bar.py"] is False

    def test_invalid_xml(self):
        assert parse_coverage_xml("<not valid") == {}


class TestCoverageDiffGate:
    def test_noop_without_coverage_file(self, tmp_path):
        gate = CoverageDiffGate(tmp_path / "coverage.xml")
        res = gate.run(_ctx(["samuel/foo.py"]))
        assert res.passed is True
        assert "fehlt" in res.reason

    def test_covered_file_ok(self, tmp_path):
        (tmp_path / "coverage.xml").write_text(_XML)
        gate = CoverageDiffGate(tmp_path / "coverage.xml")
        res = gate.run(_ctx(["samuel/foo.py"]))
        assert res.passed is True
        assert "testabgedeckt" in res.reason

    def test_uncovered_file_warns(self, tmp_path):
        (tmp_path / "coverage.xml").write_text(_XML)
        gate = CoverageDiffGate(tmp_path / "coverage.xml")
        res = gate.run(_ctx(["samuel/bar.py"]))
        assert res.passed is True  # warn-only
        assert "ohne Test-Treffer" in res.reason
        assert "samuel/bar.py" in res.reason

    def test_test_files_excluded(self, tmp_path):
        (tmp_path / "coverage.xml").write_text(_XML)
        gate = CoverageDiffGate(tmp_path / "coverage.xml")
        # nur eine Testdatei geaendert -> keine Warnung
        res = gate.run(_ctx(["samuel/slices/x/tests/test_x.py"]))
        assert "ohne Test-Treffer" not in res.reason
