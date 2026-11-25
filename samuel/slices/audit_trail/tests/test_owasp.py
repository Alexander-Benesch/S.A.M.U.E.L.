from __future__ import annotations

from samuel.slices.audit_trail.owasp import (
    OWASP_RISK_CAT_FALLBACK,
    OWASP_RISK_MAP,
    classify,
)


def test_classify_exact_match():
    # #290: ASI01..ASI10 statt A01..A10
    assert classify("scm", "git_commit") == "agentic_supply_chain"
    assert classify("guard", "quality_check") == "unexpected_code_execution"
    assert classify("llm", "llm_call") == "identity_privilege_abuse"


def test_classify_cat_fallback():
    # llm-Fallback: ASI03 identity_privilege_abuse (Attribution-Luecke)
    assert classify("llm", "some_unknown_event") == "identity_privilege_abuse"
    # security-Fallback: ASI03
    assert classify("security", "unknown") == "identity_privilege_abuse"


def test_classify_unknown_returns_none():
    assert classify("totally_unknown", "unknown") is None


def test_all_map_values_are_valid_owasp():
    # #290: gueltige Risk-Keys sind jetzt die ASI01..ASI10-Schluessel.
    valid = {
        "agent_goal_hijack",
        "tool_misuse",
        "identity_privilege_abuse",
        "agentic_supply_chain",
        "unexpected_code_execution",
        "memory_context_poisoning",
        "insecure_inter_agent",
        "cascading_failures",
        "human_agent_trust_exploitation",
        "rogue_agents",
    }
    for event_key, risk in OWASP_RISK_MAP.items():
        assert risk in valid, f"Invalid OWASP risk '{risk}' for {event_key}"
    for category, fallback in OWASP_RISK_CAT_FALLBACK.items():
        assert fallback in valid, f"Invalid OWASP fallback '{fallback}' for {category}"


def test_legacy_keys_resolve_to_new_taxonomy():
    """#290: ``unrestricted_agency`` (A01-Era) muss auf ``identity_privilege_abuse``
    (ASI03) aufloesen, damit historische Audit-Logs nach der Migration
    weiter klassifiziert werden koennen."""
    from samuel.core.owasp import OWASP_LEGACY_KEY_MAP, resolve_legacy_key

    assert resolve_legacy_key("unrestricted_agency") == "identity_privilege_abuse"
    assert resolve_legacy_key("broken_trust_boundaries") == "agentic_supply_chain"
    assert resolve_legacy_key("excessive_autonomy") == "agent_goal_hijack"
    # Unbekannter / bereits neuer Key: unveraendert
    assert resolve_legacy_key("agent_goal_hijack") == "agent_goal_hijack"
    assert resolve_legacy_key("unknown_xyz") == "unknown_xyz"
    # Mapping deckt alle 10 alten A01-A10-Keys ab
    assert len(OWASP_LEGACY_KEY_MAP) == 10


def test_all_fallback_cats_covered():
    expected_cats = {
        "guard",
        "llm",
        "eval",
        "scm",
        "workflow",
        "system",
        "routing",
        "context",
        "health",
        "config",
        "perf",
        "error",
        "security",
        # #258: gates und quality als eigene Kategorien
        "gates",
        "quality",
        # #238: plan-Kategorie fuer PlanComplexityWarn
        "plan",
    }
    assert set(OWASP_RISK_CAT_FALLBACK.keys()) == expected_cats
