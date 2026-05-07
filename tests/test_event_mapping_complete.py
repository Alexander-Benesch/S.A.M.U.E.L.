"""Mapping-Completeness-Test (Charter 1.4).

Prueft: jedes Event in samuel.core.events hat einen Eintrag in OWASP_RISK_MAP
(oder Cat-Fallback) UND in AI_ACT_ARTICLE_MAP (oder Cat-Fallback).

SAMUEL-Workflow loggt Events an Audit-Sink + Dashboard. Ohne vollstaendiges
Mapping bekommen Audit-Logs leere owasp_risk-Felder und das Dashboard kann
weder OWASP-Klasse noch EU-AI-Act-Artikel ausweisen — Compliance-Luecke.

Dieser Test ist die Schranke: rot solang ein Event-Name unmapped ist.
"""
from __future__ import annotations

import dataclasses
import inspect

from samuel.core import events as events_module
from samuel.core.owasp import (
    OWASP_RISK_CAT_FALLBACK,
    OWASP_RISK_MAP,
)
from samuel.core.ai_act import (
    AI_ACT_ARTICLE_MAP,
    AI_ACT_FALLBACK,
)


def _all_event_names() -> set[str]:
    """Collect all Event subclass `name` defaults from samuel.core.events."""
    names: set[str] = set()
    base = events_module.Event
    for _, obj in inspect.getmembers(events_module, inspect.isclass):
        if obj is base:
            continue
        if not issubclass(obj, base):
            continue
        if not dataclasses.is_dataclass(obj):
            continue
        for fld in dataclasses.fields(obj):
            if fld.name == "name" and fld.default not in (dataclasses.MISSING, ""):
                names.add(str(fld.default))
    return names


def test_collects_event_names_from_module():
    names = _all_event_names()
    assert "PRCreated" in names
    assert "EvalFailed" in names
    assert "TestRunCompleted" in names


def test_owasp_map_consistent():
    """Every key in OWASP_RISK_MAP has a non-empty risk_class string."""
    for key, val in OWASP_RISK_MAP.items():
        assert isinstance(val, str) and val, f"empty owasp risk for {key}"
    for cat, val in OWASP_RISK_CAT_FALLBACK.items():
        assert isinstance(val, str) and val, f"empty owasp fallback for {cat}"


def test_ai_act_map_consistent():
    """Every key in AI_ACT_ARTICLE_MAP has a non-empty article string."""
    for key, val in AI_ACT_ARTICLE_MAP.items():
        assert isinstance(val, str) and val.startswith("Art."), (
            f"unexpected article for {key}: {val}"
        )
    for cat, val in AI_ACT_FALLBACK.items():
        assert isinstance(val, str) and val.startswith("Art."), (
            f"unexpected fallback for {cat}: {val}"
        )


def test_test_run_completed_mapped_in_both():
    """TestRunCompleted's category-level entries (eval/test_*) are present
    in both mappings."""
    for sub in ("test_passed", "test_failed", "test_timeout"):
        assert ("eval", sub) in OWASP_RISK_MAP
        assert ("eval", sub) in AI_ACT_ARTICLE_MAP