"""#368 Task 4: Lockfile-Reader + Diff-Extraktion.

Lockfiles sind in :data:`samuel.core.project_files.DEFAULT_EXCLUDE_FILES` von der
allgemeinen Datei-Iteration ausgeschlossen (sie sind kein Quellcode-Kontext).
Fuer das Dependency-Tracking (Task 4) + die Symbol-Resolution (Task 3) werden sie
hier gezielt — per explizitem Pfad bzw. aus dem Git-Diff — gelesen.

Liefert pro Lockfile die enthaltenen Paketnamen und aus einem Unified-Diff die
neu hinzugekommenen / entfernten Pakete. Bewusst heuristisch + tolerant: lieber
ein Paket zu viel erkannt (resolved) als ein Quellcode-Import faelschlich als
Halluzination geflaggt.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Unterstuetzte Lockfile-Basenamen.
LOCKFILES: frozenset[str] = frozenset(
    {
        "package-lock.json",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "go.sum",
        "Pipfile.lock",
    }
)

# TOML-artige Lockfiles (poetry/uv/Cargo): ``name = "paket"`` je [[package]].
_TOML_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]+)"')
# go.sum: ``modul/pfad vX.Y.Z hash`` — erstes Token ist der Modulpfad.
_GOSUM_RE = re.compile(r"^([^\s]+)\s+v\S+")
# npm package-lock: Schluessel ``"node_modules/paket"``.
_NPM_RE = re.compile(r'"node_modules/([^"/]+)"')


def is_lockfile(name: str) -> bool:
    return Path(name).name in LOCKFILES


def _names_from_lines(lockfile_name: str, lines: list[str]) -> set[str]:
    base = Path(lockfile_name).name
    out: set[str] = set()
    if base == "go.sum":
        for ln in lines:
            m = _GOSUM_RE.match(ln)
            if m:
                out.add(m.group(1))
    elif base == "package-lock.json":
        for ln in lines:
            for m in _NPM_RE.finditer(ln):
                out.add(m.group(1))
    else:  # poetry.lock, uv.lock, Cargo.lock (TOML)
        for ln in lines:
            m = _TOML_NAME_RE.match(ln)
            if m:
                out.add(m.group(1))
    return out


def parse_lockfile(name: str, content: str) -> set[str]:
    """Paketnamen aus einem Lockfile-Inhalt. ``Pipfile.lock`` (JSON) wird
    speziell behandelt; sonst zeilenbasiert."""
    base = Path(name).name
    if base == "Pipfile.lock":
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return set()
        out: set[str] = set()
        for section in ("default", "develop"):
            sec = data.get(section)
            if isinstance(sec, dict):
                out.update(sec.keys())
        return out
    return _names_from_lines(name, content.splitlines())


# Diff-Header: ``+++ b/pfad/zur/datei`` (oder ``a/``).
_DIFF_TARGET_RE = re.compile(r"^\+\+\+ [ab]/(.+)$")


def added_removed_from_diff(diff_text: str) -> dict[str, set[str]]:
    """Neu hinzugekommene / entfernte Pakete aus einem Unified-Diff.

    Scannt die Lockfile-Abschnitte des Diffs (anhand der ``+++ b/<lockfile>``-
    Header) und extrahiert Paketnamen aus den ``+``- bzw. ``-``-Zeilen.
    Returns ``{"added": {...}, "removed": {...}}``."""
    added_lines: dict[str, list[str]] = {}
    removed_lines: dict[str, list[str]] = {}
    current: str | None = None
    for raw in (diff_text or "").splitlines():
        m = _DIFF_TARGET_RE.match(raw)
        if m:
            current = m.group(1) if is_lockfile(m.group(1)) else None
            continue
        if current is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            added_lines.setdefault(current, []).append(raw[1:])
        elif raw.startswith("-") and not raw.startswith("---"):
            removed_lines.setdefault(current, []).append(raw[1:])

    added: set[str] = set()
    removed: set[str] = set()
    for name, lines in added_lines.items():
        added |= _names_from_lines(name, lines)
    for name, lines in removed_lines.items():
        removed |= _names_from_lines(name, lines)
    # Versions-Bumps (Paket in beiden) zaehlen weder als neu noch als entfernt.
    return {"added": added - removed, "removed": removed - added}


def read_current_lockfile_packages(project_root: Path) -> set[str]:
    """Paketnamen aus allen vorhandenen Lockfiles im Projekt (direkt gelesen,
    trotz Ausschluss in der allgemeinen Datei-Iteration)."""
    out: set[str] = set()
    for name in LOCKFILES:
        fp = project_root / name
        if fp.exists():
            try:
                out |= parse_lockfile(name, fp.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return out
