from __future__ import annotations

import json
from pathlib import Path

# #269: Mappings extern in config/compliance/ai_act.json. Bei Bootstrap-Fehler
# fail loud — Compliance darf nicht silently broken sein.
# #292: Pfad innerhalb des Packages — funktioniert auch bei pip-installierten
# Deployments, wo das CWD nicht das Repo-Root ist. Vorher zeigte der Pfad
# auf "/config/compliance/" und brach jeden Production-Import.
_COMPLIANCE_DIR = Path(__file__).resolve().parent / "compliance"


def _load() -> dict:
    fp = _COMPLIANCE_DIR / "ai_act.json"
    if not fp.exists():
        raise RuntimeError(
            f"compliance/ai_act.json missing: {fp} (siehe Issue #269 fuer Format)"
        )
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"compliance/ai_act.json not parsable: {exc}"
        ) from exc
    for k in ("articles", "mappings", "fallbacks"):
        if k not in data:
            raise RuntimeError(f"compliance/ai_act.json missing key: {k}")
    return data


_DATA = _load()

# (category, event_name) -> EU AI Act article reference. #269: aus JSON.
AI_ACT_ARTICLE_MAP: dict[tuple[str, str], str] = {
    (m["cat"], m["evt"]): m["article"] for m in _DATA["mappings"]
}

AI_ACT_FALLBACK: dict[str, str] = dict(_DATA["fallbacks"])


def classify(cat: str, evt: str) -> str | None:
    """Map (category, event_name) -> EU AI Act article reference.

    Returns the explicit mapping if present, otherwise the category-level
    fallback. Returns None for unknown categories.
    """
    return AI_ACT_ARTICLE_MAP.get((cat, evt)) or AI_ACT_FALLBACK.get(cat)


# EU AI Act Artikel-Beschreibungen (#252) — fuer Compliance-Tab im Dashboard.
# Sprache: Deutsch (Charter-Sprache). Verweise auf VO (EU) 2024/1689.
AI_ACT_DESCRIPTIONS: dict[str, str] = {
    a["id"]: a["description"] for a in _DATA["articles"]
}


# EU AI Act Artikel mit Sortierung (#252) — fuer die Compliance-Tab-Tabelle.
AI_ACT_ARTICLES: list[dict[str, str]] = [
    {"article": a["id"], "description": a["description"]}
    for a in _DATA["articles"]
]