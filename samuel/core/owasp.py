from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# #269: Mappings extern in config/compliance/owasp.json. Bei Bootstrap-Fehler
# fail loud — Compliance darf nicht silently broken sein.
# #292: Pfad innerhalb des Packages — funktioniert auch bei pip-installierten
# Deployments, wo das CWD nicht das Repo-Root ist.
# #290: ASI01..ASI10-Migration. ``legacy_keys`` mapt alte A01..A10-Risk-Keys
# auf ihre ASI-Aequivalente, damit historische Audit-Logs interpretierbar
# bleiben.
_COMPLIANCE_DIR = Path(__file__).resolve().parent / "compliance"


def _load() -> dict[str, Any]:
    fp = _COMPLIANCE_DIR / "owasp.json"
    if not fp.exists():
        raise RuntimeError(f"compliance/owasp.json missing: {fp} (siehe Issue #269 fuer Format)")
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"compliance/owasp.json not parsable: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("compliance/owasp.json top level must be an object")
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

# #290: Legacy-Key-Resolution. ``unrestricted_agency`` -> ``identity_privilege_abuse``,
# ``broken_trust_boundaries`` -> ``agentic_supply_chain`` usw. Wird genutzt um
# alte Audit-Log-Eintraege (mit A01-A10-Keys) auf die neue Taxonomie
# aufzuloesen.
OWASP_LEGACY_KEY_MAP: dict[str, str] = {
    k: v for k, v in _DATA.get("legacy_keys", {}).items() if not k.startswith("_")
}

# #290: Legacy-ID-Resolution. ``A04`` -> ``ASI04`` (broken_trust → supply chain)
# usw. Wird vom Dashboard genutzt, damit Audit-Eintraege mit
# ``payload.owasp_risk = "A04:Trust"`` weiter im richtigen ASI-Bucket landen.
OWASP_LEGACY_ID_MAP: dict[str, str] = {
    k: v for k, v in _DATA.get("legacy_ids", {}).items() if not k.startswith("_")
}


def classify(cat: str, evt: str) -> str | None:
    """Liefere den ASI-Risk-Key fuer ein (category, event)-Paar."""
    return OWASP_RISK_MAP.get((cat, evt)) or OWASP_RISK_CAT_FALLBACK.get(cat)


def resolve_legacy_key(risk_key: str) -> str:
    """#290: Wenn ein Audit-Log-Eintrag noch einen alten A01-A10-Risk-Key
    traegt (``unrestricted_agency``, ``excessive_autonomy`` usw.), liefere
    den neuen ASI-Key zurueck. Sonst ``risk_key`` unveraendert.

    Wird vom Dashboard / Audit-Trail-Renderer genutzt, damit historische
    Eintraege nach der Migration weiter sauber klassifiziert werden.
    """
    return OWASP_LEGACY_KEY_MAP.get(risk_key, risk_key)


# OWASP Top-10 fuer Agentic AI — Beschreibungen pro Risiko-Kategorie.
# Sprache: Deutsch (Charter-Sprache). Seit #290 offiziell ASI01..ASI10
# (2026-Taxonomie).
OWASP_DESCRIPTIONS: dict[str, str] = {c["key"]: c["description"] for c in _DATA["categories"]}

# OWASP Top-10 mit ID-Mapping — fuer die Security-Tab-Anzeige.
OWASP_TOP10: list[dict[str, str]] = list(_DATA["categories"])
