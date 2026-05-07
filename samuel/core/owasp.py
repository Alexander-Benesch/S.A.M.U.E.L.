from __future__ import annotations

import json
from pathlib import Path

# #269: Mappings extern in config/compliance/owasp.json. Bei Bootstrap-Fehler
# fail loud — Compliance darf nicht silently broken sein.
# #292: Pfad innerhalb des Packages — funktioniert auch bei pip-installierten
# Deployments, wo das CWD nicht das Repo-Root ist. Vorher zeigte der Pfad
# auf "/config/compliance/" und brach jeden Production-Import.
_COMPLIANCE_DIR = Path(__file__).resolve().parent / "compliance"


def _load() -> dict:
    fp = _COMPLIANCE_DIR / "owasp.json"
    if not fp.exists():
        raise RuntimeError(
            f"compliance/owasp.json missing: {fp} (siehe Issue #269 fuer Format)"
        )
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"compliance/owasp.json not parsable: {exc}"
        ) from exc
    for k in ("categories", "mappings", "fallbacks"):
        if k not in data:
            raise RuntimeError(f"compliance/owasp.json missing key: {k}")
    return data


_DATA = _load()

# (category, event_name) -> risk_class. #269: aus JSON geladen (vorher hardcoded).
OWASP_RISK_MAP: dict[tuple[str, str], str] = {
    (m["cat"], m["evt"]): m["risk"] for m in _DATA["mappings"]
}

OWASP_RISK_CAT_FALLBACK: dict[str, str] = dict(_DATA["fallbacks"])


def classify(cat: str, evt: str) -> str | None:
    return OWASP_RISK_MAP.get((cat, evt)) or OWASP_RISK_CAT_FALLBACK.get(cat)


# OWASP Top-10 fuer Agentic AI (#252) — Beschreibungen pro Risiko-Kategorie.
# Sprache: Deutsch (Charter-Sprache). Migration auf ASI01..ASI10 (offizielle
# 2026-Taxonomie) tracked in #290.
OWASP_DESCRIPTIONS: dict[str, str] = {
    c["key"]: c["description"] for c in _DATA["categories"]
}

# OWASP Top-10 mit ID-Mapping (#252) — fuer die Security-Tab-Anzeige.
OWASP_TOP10: list[dict[str, str]] = list(_DATA["categories"])