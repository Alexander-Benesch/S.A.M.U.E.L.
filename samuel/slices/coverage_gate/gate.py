"""#368 Task 7: Coverage-Diff-Gate.

Bisher gibt es nur Plan-AC-Coverage (Planning-Slice), nicht Test-Coverage der
geaenderten Code-Pfade. Dieses Gate liest einen ``coverage.py``-XML-Report
(Cobertura-Format) und warnt fuer modifizierte Quelldateien ohne Test-Treffer.

Bewusst warn-only (passed=True): neue Gates starten optional, bis ihre FP-Rate
belegt ist (#368 Task 8). Fehlt ``coverage.xml``, ist das Gate ein No-op —
es blockiert nie und faellt nie hart aus.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from samuel.core.ports import IExternalGate
from samuel.core.types import GateContext, GateResult

log = logging.getLogger(__name__)


def parse_coverage_xml(content: str) -> dict[str, bool]:
    """Cobertura-XML -> ``{dateipfad: hat_treffer}``. ``hat_treffer`` ist True,
    wenn ``line-rate > 0`` oder mind. eine Zeile ``hits > 0`` hat."""
    covered: dict[str, bool] = {}
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return {}
    for cls in root.iter("class"):
        fn = cls.get("filename", "")
        if not fn:
            continue
        hit = False
        try:
            hit = float(cls.get("line-rate") or 0) > 0
        except ValueError:
            hit = False
        if not hit:
            for line in cls.iter("line"):
                try:
                    if int(line.get("hits") or 0) > 0:
                        hit = True
                        break
                except ValueError:
                    continue
        covered[fn] = covered.get(fn, False) or hit
    return covered


def _is_test_file(path: str) -> bool:
    p = path.lower()
    return (
        "/tests/" in p
        or p.startswith("tests/")
        or "/test_" in p
        or Path(p).name.startswith("test_")
    )


def _has_coverage(path: str, covered: dict[str, bool]) -> bool:
    """Hat die geaenderte Datei einen (treffenden) Coverage-Eintrag? Match per
    Pfad-Suffix (coverage.xml-Pfade sind oft relativ/anders verwurzelt)."""
    base = Path(path).name
    for cov_path, hit in covered.items():
        if not hit:
            continue
        if path.endswith(cov_path) or cov_path.endswith(path) or Path(cov_path).name == base:
            return True
    return False


class CoverageDiffGate(IExternalGate):
    name = "coverage_diff"

    def __init__(self, coverage_path: str | Path = "coverage.xml"):
        self._path = Path(coverage_path)

    def run(self, context: GateContext) -> GateResult:
        if not self._path.exists():
            return GateResult(
                gate=self.name, passed=True, reason="Keine Coverage-Daten (coverage.xml fehlt)"
            )
        try:
            covered = parse_coverage_xml(self._path.read_text(encoding="utf-8"))
        except OSError as exc:
            log.warning("coverage.xml unlesbar: %s", exc)
            return GateResult(gate=self.name, passed=True, reason="coverage.xml unlesbar")

        modified = [
            f for f in (context.changed_files or []) if f.endswith(".py") and not _is_test_file(f)
        ]
        uncovered = [f for f in modified if not _has_coverage(f, covered)]
        if not uncovered:
            return GateResult(
                gate=self.name,
                passed=True,
                reason=f"{len(modified)} geaenderte Datei(en) testabgedeckt",
            )
        # warn-only: blockt nicht.
        return GateResult(
            gate=self.name,
            passed=True,
            reason=f"Modifiziert ohne Test-Treffer (warn): {', '.join(uncovered[:5])}",
        )
