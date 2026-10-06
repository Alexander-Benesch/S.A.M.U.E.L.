from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# #269: Mappings extern in config/compliance/ai_act.json. Bei Bootstrap-Fehler
# fail loud — Compliance darf nicht silently broken sein.
# #292: Pfad innerhalb des Packages — funktioniert auch bei pip-installierten
# Deployments, wo das CWD nicht das Repo-Root ist. Vorher zeigte der Pfad
# auf "/config/compliance/" und brach jeden Production-Import.
_COMPLIANCE_DIR = Path(__file__).resolve().parent / "compliance"


# #373: EU-AI-Act-Risikoklassen einer Deployment-Umgebung. ``minimal_risk`` und
# ``limited_risk`` loesen fuer High-Risk-Artikel ``voluntary`` aus, ``high_risk``
# loest ``required`` aus. ``DEFAULT_RISK_CLASS`` = Self-Mode-Sicht (SAMUEL
# beaufsichtigt sich selbst → Limited Risk, vgl. #366), damit das bisherige
# Verhalten ohne explizite Konfiguration unveraendert bleibt.
RISK_CLASSES: tuple[str, ...] = ("minimal_risk", "limited_risk", "high_risk")
DEFAULT_RISK_CLASS = "limited_risk"

# Sentinel im ``applies_to`` eines Artikels: gilt fuer jede Risikoklasse
# (z.B. Art. 50 — Transparenzpflicht unabhaengig vom Risiko).
_APPLIES_TO_ALL = "all"

_RISK_CLASS_ENV = "SAMUEL_RISK_CLASS"


def _load() -> dict[str, Any]:
    fp = _COMPLIANCE_DIR / "ai_act.json"
    if not fp.exists():
        raise RuntimeError(f"compliance/ai_act.json missing: {fp} (siehe Issue #269 fuer Format)")
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"compliance/ai_act.json not parsable: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("compliance/ai_act.json top level must be an object")
    for k in ("articles", "mappings", "fallbacks"):
        if k not in data:
            raise RuntimeError(f"compliance/ai_act.json missing key: {k}")
    # #373: jeder Artikel deklariert seinen Adressatenkreis ``applies_to`` —
    # die Risikoklassen, fuer die der Artikel Pflicht ist (oder ``"all"``).
    # Die effektive Pflicht/freiwillig-Einstufung wird daraus + der
    # Deployment-Risikoklasse zur Laufzeit abgeleitet, statt statisch im JSON
    # zu stehen (vorher ``obligation``, vgl. #366/#373).
    _valid_targets = set(RISK_CLASSES) | {_APPLIES_TO_ALL}
    for art in data["articles"]:
        applies = art.get("applies_to")
        if not isinstance(applies, list) or not applies:
            raise RuntimeError(
                f"compliance/ai_act.json article {art.get('id', '?')}: "
                f"'applies_to' must be a non-empty list (got {applies!r})"
            )
        bad = [t for t in applies if t not in _valid_targets]
        if bad:
            raise RuntimeError(
                f"compliance/ai_act.json article {art.get('id', '?')}: "
                f"invalid 'applies_to' entries {bad} "
                f"(expected from {sorted(_valid_targets)})"
            )
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
AI_ACT_DESCRIPTIONS: dict[str, str] = {a["id"]: a["description"] for a in _DATA["articles"]}


# #373: article-id -> Adressatenkreis (Risikoklassen, fuer die der Artikel
# Pflicht ist; ``"all"`` = unabhaengig von der Risikoklasse).
ARTICLE_APPLIES_TO: dict[str, list[str]] = {
    a["id"]: list(a["applies_to"]) for a in _DATA["articles"]
}


def resolve_risk_class(persisted: str | None = None) -> tuple[str, str]:
    """EU-AI-Act-Risikoklasse der Deployment-Umgebung + ihre Quelle.

    #373: SAMUEL wird in fremde Projekte eingesetzt, um deren LLM-Aktivitaet zu
    ueberwachen. Die Risikoklasse des Host-Projekts entscheidet, ob die
    High-Risk-Artikel (12-15) Pflicht oder freiwillig sind — nicht eine feste
    Eigenschaft von SAMUEL selbst.

    #374: Im Dashboard editierbar. Aufloesungs-Prioritaet:

    1. env ``SAMUEL_RISK_CLASS`` — expliziter Deployment-Override (z.B.
       Container/CI). Gewinnt, damit Ops die Klasse hart fixieren koennen.
    2. ``persisted`` — der im Dashboard gesetzte, in ``config/compliance.json``
       gespeicherte Wert (vom Handler durchgereicht).
    3. Default ``limited_risk`` = Self-Mode (SAMUEL beaufsichtigt sich selbst,
       vgl. #366).

    Ungueltige Werte werden mit Warnung uebersprungen — Compliance darf nicht
    hart crashen, aber auch nicht still eine falsche Klasse vortaeuschen.

    Returns:
        ``(risk_class, source)`` mit ``source`` aus ``{"env", "config",
        "default"}`` — die UI sperrt den Selektor, wenn die Klasse per env
        fixiert ist.
    """
    raw = os.environ.get(_RISK_CLASS_ENV, "").strip().lower()
    if raw:
        if raw in RISK_CLASSES:
            return raw, "env"
        log.warning(
            "%s=%r is not a valid risk class %s — ignoring env override",
            _RISK_CLASS_ENV,
            raw,
            list(RISK_CLASSES),
        )
    if persisted:
        p = str(persisted).strip().lower()
        if p in RISK_CLASSES:
            return p, "config"
        log.warning(
            "persisted risk class %r is not valid %s — falling back to %r",
            persisted,
            list(RISK_CLASSES),
            DEFAULT_RISK_CLASS,
        )
    return DEFAULT_RISK_CLASS, "default"


def deployment_risk_class(persisted: str | None = None) -> str:
    """Effektive Deployment-Risikoklasse (ohne Quelle). Siehe
    :func:`resolve_risk_class` fuer die Aufloesungs-Prioritaet."""
    return resolve_risk_class(persisted)[0]


def obligation_for(article_id: str, risk_class: str | None = None) -> str:
    """Effektive Pflicht eines Artikels fuer eine Deployment-Risikoklasse.

    Returns ``"required"`` wenn der Artikel die gegebene Risikoklasse adressiert
    (oder ``"all"`` adressiert), sonst ``"voluntary"``. ``risk_class=None``
    nutzt :func:`deployment_risk_class`.
    """
    rc = risk_class or deployment_risk_class()
    applies = ARTICLE_APPLIES_TO.get(article_id, [])
    if _APPLIES_TO_ALL in applies or rc in applies:
        return "required"
    return "voluntary"


def ai_act_articles(risk_class: str | None = None) -> list[dict[str, str]]:
    """EU-AI-Act-Artikel fuer die Compliance-Tab-Tabelle (#252), sortiert.

    #373: ``obligation`` wird pro Artikel aus dem Adressatenkreis + der
    Deployment-Risikoklasse abgeleitet (statt statisch im JSON). Default ist die
    aktuelle Deployment-Risikoklasse; ein expliziter ``risk_class`` erlaubt das
    Vorschauen anderer Klassen (und macht die Ableitung testbar).
    """
    rc = risk_class or deployment_risk_class()
    return [
        {
            "article": a["id"],
            "description": a["description"],
            "obligation": obligation_for(a["id"], rc),
        }
        for a in _DATA["articles"]
    ]
