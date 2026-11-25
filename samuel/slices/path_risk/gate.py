"""#368 Task 2: Path-Risk-Classifier als External-Gate.

Ein konfigurierbarer Classifier (``config/path_risk.json``) statt mehrerer fest
verdrahteter Pfad-Gates. Audit-Teams erweitern die Risiko-Klassen per JSON, ohne
Code zu schreiben. Klassen mit ``level: "block"`` blockieren den PR (z.B.
Secrets); ``level: "warn"`` ist beobachtend (taucht im Reviewer-Briefing auf,
blockt aber nicht — neue Gates starten bewusst nicht-blockierend, #368-Nichtziel).

Gate 7 (``scope_guard``) bleibt der eingebaute Minimal-Fallback fuer den
Secret-Block, falls ``path_risk.json`` fehlt oder dieser Gate nicht verdrahtet
wird.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from samuel.core.path_risk import path_matches_pattern
from samuel.core.ports import IExternalGate
from samuel.core.types import GateContext, GateResult

log = logging.getLogger(__name__)


def classify_paths(
    files: list[str],
    classes: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Pro Risiko-Klasse die getroffenen Dateien (Reihenfolge der Klassen
    erhalten). Eine Datei kann in mehreren Klassen auftauchen."""
    hits: dict[str, list[str]] = {}
    for cls in classes:
        name = cls.get("name", "?")
        patterns = cls.get("patterns", [])
        matched = [f for f in files if any(path_matches_pattern(f, pat) for pat in patterns)]
        if matched:
            hits[name] = matched
    return hits


def load_path_risk_classes(config_dir: str | Path) -> list[dict[str, Any]]:
    """Risiko-Klassen aus ``config/path_risk.json`` (leer bei Fehlen/Fehler)."""
    path = Path(config_dir) / "path_risk.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("path_risk.json unlesbar: %s", exc)
        return []
    classes = data.get("classes") if isinstance(data, dict) else None
    return classes if isinstance(classes, list) else []


class PathRiskGate(IExternalGate):
    name = "path_risk"

    def __init__(self, classes: list[dict[str, Any]]):
        self._classes = classes
        self._by_name = {c.get("name"): c for c in classes}

    @classmethod
    def from_config(cls, config_dir: str | Path) -> PathRiskGate | None:
        classes = load_path_risk_classes(config_dir)
        return cls(classes) if classes else None

    def run(self, context: GateContext) -> GateResult:
        files = context.changed_files or []
        hits = classify_paths(files, self._classes)
        if not hits:
            return GateResult(gate=self.name, passed=True, reason="Keine riskanten Pfade")

        blocking = [name for name in hits if self._by_name.get(name, {}).get("level") == "block"]
        if blocking:
            cls = self._by_name.get(blocking[0], {})
            offenders = hits[blocking[0]][:3]
            return GateResult(
                gate=self.name,
                passed=False,
                reason=f"Riskante Pfade ({blocking[0]}): {', '.join(offenders)}",
                owasp_risk=cls.get("owasp"),
            )
        # Nur warn-Level: beobachtend, blockt nicht.
        summary = "; ".join(f"{name}: {', '.join(fs[:2])}" for name, fs in hits.items())
        return GateResult(
            gate=self.name,
            passed=True,
            reason=f"Risiko-Klassen erkannt (warn): {summary}",
        )
