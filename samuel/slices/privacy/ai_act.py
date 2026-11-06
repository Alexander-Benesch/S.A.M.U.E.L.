from __future__ import annotations

import hashlib
from typing import Any

# #270: kanonische Trailer-Logik liegt im Shared Kernel
# (samuel.core.attribution), damit auch der implementation-Slice sie nutzen
# kann, ohne den privacy-Slice zu importieren (Slice-Iso). Re-Export hier fuer
# Backward-Compat (bootstrap-Wiring + Tests importieren von hier).
from samuel.core.attribution import ai_attribution_trailer

__all__ = [
    "ai_attribution_trailer",
    "enrich_llm_event_payload",
    "RISK_CLASSIFICATION",
    "get_risk_classification",
]


def enrich_llm_event_payload(
    payload: dict[str, Any],
    *,
    prompt: str = "",
    system_prompt_version: str = "",
    temperature: float | None = None,
    model_version: str = "",
) -> dict[str, Any]:
    enriched = dict(payload)
    if prompt:
        enriched["prompt_hash"] = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    if system_prompt_version:
        enriched["system_prompt_version"] = system_prompt_version
    if temperature is not None:
        enriched["temperature"] = temperature
    if model_version:
        enriched["model_version"] = model_version
    return enriched


# #366: Strikte Trennung zwischen Pflicht-Mass (Art. 50 fuer Limited Risk)
# und freiwillig angewandten High-Risk-Standards (Art. 12/13/14/15). VO
# 2024/1689 Art. 12, 14, 15 adressieren ausschliesslich Hochrisiko-KI-
# Systeme; SAMUEL ist Limited Risk und erfuellt diese Artikel daher NICHT
# als Pflicht — wir wenden die Standards freiwillig an, weil sie gute
# Praxis sind, nicht weil das Gesetz uns dazu zwingt.
#
# #373: Diese Einstufung beschreibt SAMUEL im SELF-MODE (der Agent
# beaufsichtigt sich selbst). Wird SAMUEL in ein fremdes Projekt eingesetzt,
# gilt die Risikoklasse des HOST-Systems (env SAMUEL_RISK_CLASS); ist das ein
# Hochrisiko-System, werden Art. 12-15 fuer dieses System Pflicht und SAMUELs
# Kontrollen sind dann dessen Compliance-Instrumente. Die laufzeit-abgeleitete
# Pflicht/freiwillig-Einstufung liegt in ``samuel.core.ai_act.obligation_for``.
RISK_CLASSIFICATION = {
    "system": "S.A.M.U.E.L.",
    "scope": "self",
    "classification": "Limited Risk",
    "article": "Art. 6, Art. 50 EU AI Act (VO 2024/1689)",
    "justification": (
        "S.A.M.U.E.L. generiert Code-Vorschlaege unter menschlicher Aufsicht. "
        "Kein autonomes Handeln ohne Gate-Approval. Kein High-Risk-Anwendungsfall "
        "(nicht in Annex III gelistet). Einzige rechtliche Pflicht aus dem AI Act: "
        "Transparenz fuer KI-generierte Inhalte (Art. 50), erfuellt via "
        "AI-Attribution-Trailer in jedem KI-generierten Commit."
    ),
    "mandatory_obligations": {
        "article": "Art. 50",
        "title": "Transparenz fuer KI-generierte Inhalte",
        "measures": [
            "AI-Generated-By Git-Trailer in jedem KI-generierten Commit",
            "LLMCallCompleted-Events mit model_version (Audit-Spur fuer "
            "Operator und betroffene Nutzer)",
            "Inline-Marker (llm: <modell> <datum>) am Kopf KI-erzeugter "
            "Code-Bloecke + Co-Authored-By-Trailer (extern sichtbar, #270) — "
            "abschaltbar fuer Limited Risk, bei high_risk Pflicht",
        ],
    },
    "voluntary_practices": {
        "disclaimer": (
            "Folgende Massnahmen orientieren sich an Hochrisiko-Standards "
            "(VO 2024/1689 Art. 12-15). Im Self-Mode (SAMUEL beaufsichtigt "
            "sich selbst, Limited Risk) sind sie NICHT verpflichtend; SAMUEL "
            "wendet sie freiwillig an, weil sie gute technische Praxis sind. "
            "Wird SAMUEL in ein Hochrisiko-Host-System eingesetzt "
            "(SAMUEL_RISK_CLASS=high_risk), werden diese Massnahmen fuer das "
            "Host-System zu Pflicht-Instrumenten."
        ),
        "high_risk_equivalents": [
            {
                "analog_to": "Art. 12",
                "topic": "Logging",
                "measures": [
                    "JSONL Audit-Trail mit Correlation-IDs",
                    "Kategorieweiser Retention-Dry-Run unter eu_operational; "
                    "Stufe 5b loescht und anonymisiert nicht automatisch",
                ],
            },
            {
                "analog_to": "Art. 14",
                "topic": "Human Oversight",
                "measures": [
                    "Gate-System: Kein PR ohne 14 Pruefungen",
                    "Plan-Approval: Mensch kann Plan ablehnen/aendern",
                    "Watch-Mode: Semaphore-kontrollierte Parallelitaet",
                    "Self-Mode: Zusaetzliche Parity-Tests",
                ],
            },
            {
                "analog_to": "Art. 15",
                "topic": "Robustness",
                "measures": [
                    "Eval-Score-History (Score 0-100% pro Run)",
                    "Healing-Budget-Kontrolle",
                    "Test-Run-Verifikation als Default",
                ],
            },
        ],
    },
}


def get_risk_classification() -> dict[str, Any]:
    return dict(RISK_CLASSIFICATION)
