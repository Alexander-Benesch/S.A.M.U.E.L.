"""#368 Task 3: Symbol-Resolution mit Resolution-Context (External-Gate).

Halluzinations-Erkennung fuer erfundene Imports — mit Nuance, damit legitim
generierter / neu eingefuehrter Code NICHT falsch-positiv geflaggt wird. Jedes
im Diff neu importierte Top-Level-Modul wird gegen mehrere Quellen geprueft:

  (a) im selben Diff definiert (neue Datei/Modul),
  (b) Generator-Output laut ``config/architecture.json`` (``code_generators``),
  (c) durch Lockfile / Lockfile-Diff erklaert (Task 4),

  zusaetzlich (FP-Reduktion, bewusst weitergedacht):
  (d) Python-Stdlib,
  (e) First-Party (Modul existiert im Projekt).

Erst wenn KEINE Quelle passt -> ``UnresolvedSymbol`` (OWASP LLM09 Misinformation).
Bewusst nicht-blockierend (warn): neue Gates starten optional, bis ihre
FP-Rate belegt ist (#368 Task 8). Die Import-Extraktion ist Python-fokussiert
(Sprache dieses Repos); andere Sprachen folgen bei Bedarf.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from samuel.core.lockfiles import added_removed_from_diff, read_current_lockfile_packages
from samuel.core.ports import IExternalGate
from samuel.core.types import GateContext, GateResult

log = logging.getLogger(__name__)

OWASP_LLM_MISINFORMATION = "LLM09:2025"

_DIFF_TARGET_RE = re.compile(r"^\+\+\+ [ab]/(.+)$")
_IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z_][\w]*)")
_FROM_RE = re.compile(r"^\s*from\s+([a-zA-Z_][\w]*)")


def _normalize(name: str) -> str:
    return name.lower().replace("-", "").replace("_", "")


def extract_added_imports(diff_text: str) -> set[str]:
    """Top-Level-Modulnamen aus ``+``-Zeilen (nur .py-Dateiabschnitte).

    Relative Imports (``from . import x``) werden ignoriert (immer first-party).
    """
    imports: set[str] = set()
    in_py = False
    for raw in (diff_text or "").splitlines():
        m = _DIFF_TARGET_RE.match(raw)
        if m:
            in_py = m.group(1).endswith(".py")
            continue
        if not in_py or not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:]
        mi = _IMPORT_RE.match(line) or _FROM_RE.match(line)
        if mi:
            imports.add(mi.group(1))
    return imports


def local_modules_in_diff(changed_files: list[str]) -> set[str]:
    """(a) Im Diff definierte Modulnamen: Basenamen geaenderter .py-Dateien +
    deren Paket-Verzeichnisnamen."""
    mods: set[str] = set()
    for f in changed_files or []:
        if not f.endswith(".py"):
            continue
        parts = f.split("/")
        stem = parts[-1][:-3]  # ohne .py
        if stem and stem != "__init__":
            mods.add(stem)
        for p in parts[:-1]:
            if p:
                mods.add(p)
    return mods


def load_code_generators(config_dir: str | Path) -> list[str]:
    """(b) Generator-Output-Pfade aus ``config/architecture.json``."""
    path = Path(config_dir) / "architecture.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    gens = data.get("code_generators") if isinstance(data, dict) else None
    return [str(g) for g in gens] if isinstance(gens, list) else []


def _generator_module_names(generators: list[str]) -> set[str]:
    """Modulnamen aus Generator-Output-Pfaden ableiten (Basename + Dir-Teile)."""
    names: set[str] = set()
    for g in generators:
        for part in g.replace("*", "").strip("/").split("/"):
            part = part.split(".")[0]
            if part:
                names.add(part)
    return names


class SymbolResolutionGate(IExternalGate):
    name = "symbol_resolution"

    def __init__(
        self,
        bus: Any = None,
        project_root: Path | str = ".",
        config_dir: str | Path = "config",
    ) -> None:
        self._bus = bus
        self._project_root = Path(project_root)
        self._config_dir = config_dir

    def _publish(self, event: Any) -> None:
        if self._bus is not None:
            try:
                self._bus.publish(event)
            except Exception:
                log.exception("publish from SymbolResolutionGate failed")

    def run(self, context: GateContext) -> GateResult:
        from samuel.core.events import LockfileChanged, UnresolvedSymbol

        diff = context.diff or ""
        # Task 4: Lockfile-Diff -> Event + erklaerte Pakete.
        lock_changes = added_removed_from_diff(diff)
        lock_added = lock_changes["added"]
        if lock_added or lock_changes["removed"]:
            self._publish(
                LockfileChanged(
                    payload={
                        "issue": context.issue_number,
                        "added": sorted(lock_added),
                        "removed": sorted(lock_changes["removed"]),
                    }
                )
            )

        imports = extract_added_imports(diff)
        if not imports:
            return GateResult(gate=self.name, passed=True, reason="Keine neuen Imports")

        # Resolution-Quellen.
        defined = local_modules_in_diff(context.changed_files)  # (a)
        generators = _generator_module_names(load_code_generators(self._config_dir))  # (b)
        pkgs = {
            _normalize(p) for p in read_current_lockfile_packages(self._project_root) | lock_added
        }  # (c)
        stdlib = set(getattr(sys, "stdlib_module_names", set()))  # (d)

        unresolved: list[str] = []
        for mod in sorted(imports):
            if (
                mod in defined
                or mod in generators
                or mod in stdlib
                or _normalize(mod) in pkgs
                or self._is_first_party(mod)
            ):  # (e)
                continue
            unresolved.append(mod)

        if not unresolved:
            return GateResult(
                gate=self.name, passed=True, reason=f"{len(imports)} Import(e) aufgeloest"
            )

        self._publish(
            UnresolvedSymbol(
                payload={
                    "issue": context.issue_number,
                    "symbols": unresolved,
                    "owasp_risk": OWASP_LLM_MISINFORMATION,
                    "reason": f"Nicht aufloesbare Imports: {', '.join(unresolved)}",
                }
            )
        )
        # Warn-only: passed=True, aber als Finding (owasp_risk) sichtbar.
        return GateResult(
            gate=self.name,
            passed=True,
            reason=f"Nicht aufloesbare Imports (warn): {', '.join(unresolved[:5])}",
            owasp_risk=OWASP_LLM_MISINFORMATION,
        )

    def _is_first_party(self, mod: str) -> bool:
        return (self._project_root / mod).is_dir() or (self._project_root / f"{mod}.py").is_file()
