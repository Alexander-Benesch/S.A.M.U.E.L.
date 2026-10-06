"""#270: Kenntlichmachung von LLM-generiertem Code (Shared Kernel).

Zwei Ebenen, strikt getrennt (vgl. finalisierte Entscheidung 2026-05-29):

* **Audit-Ebene** — ``AI-Generated-By``-Commit-Trailer + ``LLMCallCompleted``-
  Events. Immer aktiv (EU-AI-Act Art. 50 Transparenzpflicht, nie abschaltbar).
* **Externe-Sichtbarkeits-Ebene** — Inline-Marker im Quellcode + ``Co-Authored-By``-
  Trailer (von GitHub als sichtbarer Co-Autor gerendert). Steuerbar ueber das
  Feature-Flag ``llm_attribution``. Bei Deployment-Risikoklasse ``high_risk``
  gesperrt (nicht abschaltbar), weil die Transparenz dort Pflicht-Instrument ist.

Liegt im Shared Kernel, weil mehrere Slices die reine Logik brauchen
(``implementation`` dekoriert Patches, ``pr_gates``/Wiring baut Trailer) und
Slices sich gegenseitig nicht importieren duerfen. ``enrich_llm_event_payload``
+ ``RISK_CLASSIFICATION`` bleiben im privacy-Slice
(:mod:`samuel.slices.privacy.ai_act`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel import __version__

# Dateiendung -> Zeilen-Kommentar-Praefix. Bewusst nur Line-Comment-Sprachen:
# Block-Comment-only-Formate (HTML/CSS) wuerden Oeffnungs-/Schluss-Tokens
# brauchen — fuer die liefern wir keinen Marker (None), statt den Code zu
# riskieren. Unbekannte Endung -> kein Marker (kein Korrumpieren, kein Spam).
COMMENT_PREFIX: dict[str, str] = {
    ".py": "#",
    ".pyi": "#",
    ".sh": "#",
    ".bash": "#",
    ".zsh": "#",
    ".rb": "#",
    ".pl": "#",
    ".r": "#",
    ".jl": "#",
    ".yaml": "#",
    ".yml": "#",
    ".toml": "#",
    ".cfg": "#",
    ".ini": "#",
    ".tf": "#",
    ".dockerfile": "#",
    ".mk": "#",
    ".js": "//",
    ".jsx": "//",
    ".mjs": "//",
    ".cjs": "//",
    ".ts": "//",
    ".tsx": "//",
    ".go": "//",
    ".java": "//",
    ".kt": "//",
    ".kts": "//",
    ".c": "//",
    ".h": "//",
    ".cpp": "//",
    ".hpp": "//",
    ".cc": "//",
    ".cs": "//",
    ".rs": "//",
    ".swift": "//",
    ".php": "//",
    ".scala": "//",
    ".dart": "//",
    ".proto": "//",
    ".sql": "--",
    ".lua": "--",
    ".hs": "--",
    ".elm": "--",
    ".ada": "--",
}

VERBOSITY_MINIMAL = "minimal"
VERBOSITY_FULL = "full"


def ai_attribution_trailer(model: str, version: str = "") -> str:
    """``AI-Generated-By``-Commit-Trailer (Audit-Ebene, immer aktiv, Art. 50)."""
    model_id = f"{model}@{version}" if version else model
    return f"AI-Generated-By: {model_id}"


def comment_prefix(file_ext: str) -> str | None:
    """Zeilen-Kommentar-Praefix fuer eine Dateiendung, sonst ``None``."""
    return COMMENT_PREFIX.get((file_ext or "").lower())


def marker_text(
    model: str,
    *,
    date: str,
    verbosity: str = VERBOSITY_MINIMAL,
    version: str = "",
    issue: int | str | None = None,
) -> str:
    """Marker-Text OHNE Kommentar-Praefix.

    ``minimal`` (Default): ``llm: <model> <date>``.
    ``full``: zusaetzlich ``@<version>`` (falls vorhanden) und ``(#<issue>)``.
    """
    model_id = model
    if verbosity == VERBOSITY_FULL and version:
        model_id = f"{model}@{version}"
    text = f"llm: {model_id} {date}"
    if verbosity == VERBOSITY_FULL and issue:
        text = f"{text} (#{issue})"
    return text


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def mark_content(content: str, *, prefix: str, text: str) -> str:
    """Fuege GENAU EINEN Marker am Block-Kopf ein (kein Zeilen-Spam).

    * Bei Shebang (``#!...``) bzw. Python-Coding-Zeile wird der Marker danach
      eingefuegt, damit die ausfuehrbare/Encoding-Semantik intakt bleibt.
    * Idempotent: ist im Kopf (erste 3 Zeilen ab Einfuegeposition) bereits ein
      ``llm:``-Marker vorhanden, bleibt der Inhalt unveraendert.
    * Die Einrueckung des Markers folgt der Block-Kopf-Zeile, damit der Marker
      bei eingerueckten Bloecken (z.B. innerhalb einer Funktion) korrekt sitzt.
    """
    lines = content.split("\n")
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1
    if idx < len(lines):
        probe = lines[idx].lstrip()
        if probe.startswith("#") and "coding:" in lines[idx]:
            idx += 1
    head = "\n".join(lines[idx : idx + 3])
    if "llm:" in head:
        return content
    indent = _leading_ws(lines[idx]) if idx < len(lines) else ""
    lines.insert(idx, f"{indent}{prefix} {text}")
    return "\n".join(lines)


def decorate_patch(
    patch: dict[str, Any],
    *,
    model: str,
    date: str,
    verbosity: str = VERBOSITY_MINIMAL,
    version: str = "",
    issue: int | str | None = None,
) -> dict[str, Any]:
    """Liefere eine Kopie des Patches mit Inline-Marker im einzufuegenden Code.

    Greift in das ``write``- bzw. ``replace``-Feld ein (neue Datei / ersetzter
    Block). Unbekannte Dateiendung -> Patch unveraendert zurueck. Der Aufrufer
    sollte bei Apply-Fehler auf den unmarkierten Patch zurueckfallen, damit die
    Kennzeichnung niemals einen sonst gueltigen Patch verwirft.
    """
    rel = patch.get("file", "")
    prefix = comment_prefix(Path(rel).suffix)
    if not prefix:
        return patch
    text = marker_text(
        model,
        date=date,
        verbosity=verbosity,
        version=version,
        issue=issue,
    )
    decorated = dict(patch)
    if patch.get("type") == "write" and isinstance(patch.get("write"), str):
        decorated["write"] = mark_content(patch["write"], prefix=prefix, text=text)
    elif isinstance(patch.get("replace"), str):
        decorated["replace"] = mark_content(patch["replace"], prefix=prefix, text=text)
    else:
        return patch
    return decorated


def commit_trailers(
    *,
    model: str = "",
    system_id: str = "S.A.M.U.E.L.",
    system_version: str = __version__,
    build_revision: str = "",
    build_dirty: bool = False,
    external_visible: bool = True,
    co_author_email: str = "noreply@samuel.local",
) -> str:
    """Trailer-Block fuer LLM-generierte Commits.

    * ``AI-Generated-By: <system_id>@<system_version>`` — IMMER (Audit/Art. 50).
    * ``SAMUEL-Build-Revision`` — voller Commit-SHA, wenn im Build bekannt.
    * ``Co-Authored-By: <model> <email>`` — nur bei ``external_visible`` und
      bekanntem Modell. Das ist der von GitHub sichtbar gerenderte Co-Autor,
      den der Operator unterdruecken koennen muss (Toggle).
    """
    lines = [ai_attribution_trailer(system_id, system_version)]
    if build_revision:
        lines.append(f"SAMUEL-Build-Revision: {build_revision}")
        if build_dirty:
            lines.append("SAMUEL-Build-Dirty: true")
    if external_visible and model:
        lines.append(f"Co-Authored-By: {model} <{co_author_email}>")
    return "\n".join(lines)
