from __future__ import annotations

from samuel.slices.privacy.ai_act import (
    ai_attribution_trailer,
    enrich_llm_event_payload,
    get_risk_classification,
)


class TestAIAttribution:
    def test_trailer_with_version(self):
        trailer = ai_attribution_trailer("claude-3.5-sonnet", "20240620")
        assert trailer == "AI-Generated-By: claude-3.5-sonnet@20240620"

    def test_trailer_without_version(self):
        trailer = ai_attribution_trailer("ollama/codellama")
        assert trailer == "AI-Generated-By: ollama/codellama"

    def test_trailer_format_machine_readable(self):
        trailer = ai_attribution_trailer("deepseek-coder", "v2")
        assert trailer.startswith("AI-Generated-By: ")
        assert ":" in trailer


class TestEnrichLLMEvent:
    def test_adds_prompt_hash(self):
        payload = enrich_llm_event_payload(
            {"issue": 42},
            prompt="Generate a function",
        )

        assert "prompt_hash" in payload
        assert len(payload["prompt_hash"]) == 16
        assert payload["issue"] == 42

    def test_adds_all_fields(self):
        payload = enrich_llm_event_payload(
            {},
            prompt="test",
            system_prompt_version="v3.2",
            temperature=0.7,
            model_version="claude-3.5-sonnet-20240620",
        )

        assert payload["prompt_hash"] is not None
        assert payload["system_prompt_version"] == "v3.2"
        assert payload["temperature"] == 0.7
        assert payload["model_version"] == "claude-3.5-sonnet-20240620"

    def test_preserves_existing_payload(self):
        payload = enrich_llm_event_payload(
            {"issue": 42, "correlation_id": "abc"},
            prompt="test",
        )

        assert payload["issue"] == 42
        assert payload["correlation_id"] == "abc"

    def test_empty_prompt_no_hash(self):
        payload = enrich_llm_event_payload({})
        assert "prompt_hash" not in payload

    def test_consistent_hash(self):
        p1 = enrich_llm_event_payload({}, prompt="same prompt")
        p2 = enrich_llm_event_payload({}, prompt="same prompt")
        assert p1["prompt_hash"] == p2["prompt_hash"]


class TestRiskClassification:
    def test_classification_is_limited_risk(self):
        rc = get_risk_classification()
        assert rc["classification"] == "Limited Risk"

    def test_has_article_reference(self):
        rc = get_risk_classification()
        assert "Art. 6" in rc["article"]
        assert "Art. 50" in rc["article"]

    def test_has_justification(self):
        rc = get_risk_classification()
        assert len(rc["justification"]) > 100
        assert "Annex III" in rc["justification"]

    def test_risk_classification_separates_mandatory_and_voluntary(self):
        """#366: ``mandatory_obligations`` (nur Art. 50) ist strikt getrennt
        von ``voluntary_practices`` (freiwillige High-Risk-Standards).
        Alte Felder ``transparency_measures`` und ``human_oversight``
        existieren nicht mehr — sie hatten Pflichterfuellung von Art. 14
        suggeriert, was juristisch falsch war."""
        rc = get_risk_classification()
        assert "mandatory_obligations" in rc
        assert "voluntary_practices" in rc
        assert "transparency_measures" not in rc
        assert "human_oversight" not in rc

    def test_mandatory_obligations_only_art50(self):
        """#366: Limited Risk verpflichtet ausschliesslich auf Art. 50.
        AI-Attribution-Trailer muss explizit als Mass aufgefuehrt sein,
        weil das die einzige technische Erfuellung der einzigen Pflicht ist."""
        rc = get_risk_classification()
        mandatory = rc["mandatory_obligations"]
        assert mandatory["article"] == "Art. 50"
        assert any("AI-Generated-By" in m for m in mandatory["measures"])

    def test_voluntary_practices_carry_disclaimer_and_high_risk_analogues(self):
        """#366: Der ``voluntary_practices``-Block dokumentiert freiwillige
        Anwendung von High-Risk-Standards — das muss durch einen Disclaimer
        klar als _nicht_ rechtliche Pflicht gekennzeichnet sein, und die
        konkreten Massnahmen muessen pro analogem Artikel gelistet sein."""
        rc = get_risk_classification()
        voluntary = rc["voluntary_practices"]
        assert "freiwillig" in voluntary["disclaimer"].lower()
        analogues = voluntary["high_risk_equivalents"]
        analog_articles = {a["analog_to"] for a in analogues}
        # Mindestens Art. 12 (Logging), Art. 14 (Oversight), Art. 15 (Robustness)
        assert {"Art. 12", "Art. 14", "Art. 15"}.issubset(analog_articles)
        # Gate-Mechanismen muessen unter Art. 14 stehen (Human Oversight),
        # nicht mehr in einem separaten Pflicht-Block
        art14 = next(a for a in analogues if a["analog_to"] == "Art. 14")
        assert any("Gate" in m for m in art14["measures"])
        art12 = next(a for a in analogues if a["analog_to"] == "Art. 12")
        assert any("Retention-Dry-Run" in m for m in art12["measures"])
        assert all("PII-Anonymisierung nach 30 Tagen" not in m for m in art12["measures"])


class TestArticleObligationDerivation:
    """#373: Die Pflicht/freiwillig-Einstufung pro Artikel ist NICHT statisch,
    sondern wird aus dem Adressatenkreis (``applies_to``) + der Deployment-
    Risikoklasse abgeleitet."""

    def test_art50_required_for_every_risk_class(self):
        """Art. 50 (Transparenz fuer KI-Inhalte) adressiert ``all`` Systeme —
        Pflicht unabhaengig von der Risikoklasse."""
        from samuel.core.ai_act import RISK_CLASSES, obligation_for

        for rc in RISK_CLASSES:
            assert obligation_for("Art. 50", rc) == "required", rc

    def test_high_risk_articles_voluntary_for_limited_risk(self):
        """Self-Mode (Limited Risk): Art. 12-15 adressieren nur Hochrisiko-
        Systeme → hier freiwillig."""
        from samuel.core.ai_act import obligation_for

        for art in ("Art. 12", "Art. 13", "Art. 14", "Art. 15"):
            assert obligation_for(art, "limited_risk") == "voluntary", art
            assert obligation_for(art, "minimal_risk") == "voluntary", art

    def test_high_risk_articles_required_for_high_risk_deployment(self):
        """Hochrisiko-Host-Deployment: Art. 12-15 werden Pflicht — SAMUEL
        liefert die Compliance-Instrumente des ueberwachten Systems."""
        from samuel.core.ai_act import obligation_for

        for art in ("Art. 12", "Art. 13", "Art. 14", "Art. 15"):
            assert obligation_for(art, "high_risk") == "required", art

    def test_legend_articles_carry_derived_obligation(self):
        """Compliance-Tab kann Pflicht/freiwillig visuell trennen, weil der
        abgeleitete Wert pro Artikel mitgeliefert wird."""
        from samuel.core.ai_act import ai_act_articles

        for entry in ai_act_articles("limited_risk"):
            assert entry["obligation"] in ("required", "voluntary"), (
                f"Article {entry['article']} missing obligation field"
            )

    def test_load_fails_loud_when_applies_to_missing(self, tmp_path, monkeypatch):
        """Schema-Validation: JSON ohne ``applies_to`` -> RuntimeError,
        Compliance darf nicht silently broken sein."""
        import json as _json

        bad_payload = {
            "articles": [
                {"id": "Art. 50", "title": "x", "description": "y"},
            ],
            "mappings": [],
            "fallbacks": {},
        }
        (tmp_path / "ai_act.json").write_text(
            _json.dumps(bad_payload),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "samuel.core.ai_act._COMPLIANCE_DIR",
            tmp_path,
        )
        import pytest

        from samuel.core import ai_act

        with pytest.raises(RuntimeError, match="applies_to"):
            ai_act._load()

    def test_load_fails_loud_on_invalid_applies_to_target(self, tmp_path, monkeypatch):
        """Unbekannte Risikoklasse in ``applies_to`` -> RuntimeError."""
        import json as _json

        bad_payload = {
            "articles": [
                {
                    "id": "Art. 50",
                    "title": "x",
                    "description": "y",
                    "applies_to": ["catastrophic_risk"],
                },
            ],
            "mappings": [],
            "fallbacks": {},
        }
        (tmp_path / "ai_act.json").write_text(
            _json.dumps(bad_payload),
            encoding="utf-8",
        )
        monkeypatch.setattr("samuel.core.ai_act._COMPLIANCE_DIR", tmp_path)
        import pytest

        from samuel.core import ai_act

        with pytest.raises(RuntimeError, match="applies_to"):
            ai_act._load()


class TestDeploymentRiskClass:
    """#373: Deployment-Risikoklasse aus env ``SAMUEL_RISK_CLASS``."""

    def test_default_is_limited_risk(self, monkeypatch):
        from samuel.core.ai_act import DEFAULT_RISK_CLASS, deployment_risk_class

        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        assert deployment_risk_class() == DEFAULT_RISK_CLASS == "limited_risk"

    def test_env_override(self, monkeypatch):
        from samuel.core.ai_act import deployment_risk_class

        monkeypatch.setenv("SAMUEL_RISK_CLASS", "high_risk")
        assert deployment_risk_class() == "high_risk"

    def test_case_insensitive_and_trimmed(self, monkeypatch):
        from samuel.core.ai_act import deployment_risk_class

        monkeypatch.setenv("SAMUEL_RISK_CLASS", "  High_Risk  ")
        assert deployment_risk_class() == "high_risk"

    def test_invalid_falls_back_to_default(self, monkeypatch):
        from samuel.core.ai_act import deployment_risk_class

        monkeypatch.setenv("SAMUEL_RISK_CLASS", "bogus")
        assert deployment_risk_class() == "limited_risk"

    def test_obligation_for_uses_deployment_class_when_unspecified(self, monkeypatch):
        from samuel.core.ai_act import obligation_for

        monkeypatch.setenv("SAMUEL_RISK_CLASS", "high_risk")
        assert obligation_for("Art. 14") == "required"
        monkeypatch.setenv("SAMUEL_RISK_CLASS", "limited_risk")
        assert obligation_for("Art. 14") == "voluntary"


class TestResolveRiskClassSource:
    """#374: ``resolve_risk_class`` liefert (Klasse, Quelle) mit Prioritaet
    env-Override > persistierter Dashboard-Wert > Default."""

    def test_default_source_when_nothing_set(self, monkeypatch):
        from samuel.core.ai_act import resolve_risk_class

        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        assert resolve_risk_class(None) == ("limited_risk", "default")

    def test_persisted_used_when_no_env(self, monkeypatch):
        from samuel.core.ai_act import resolve_risk_class

        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        assert resolve_risk_class("high_risk") == ("high_risk", "config")

    def test_env_overrides_persisted(self, monkeypatch):
        from samuel.core.ai_act import resolve_risk_class

        monkeypatch.setenv("SAMUEL_RISK_CLASS", "minimal_risk")
        # persistierter Wert wird vom env-Override geschlagen
        assert resolve_risk_class("high_risk") == ("minimal_risk", "env")

    def test_invalid_env_falls_through_to_persisted(self, monkeypatch):
        from samuel.core.ai_act import resolve_risk_class

        monkeypatch.setenv("SAMUEL_RISK_CLASS", "bogus")
        assert resolve_risk_class("high_risk") == ("high_risk", "config")

    def test_invalid_persisted_falls_through_to_default(self, monkeypatch):
        from samuel.core.ai_act import resolve_risk_class

        monkeypatch.delenv("SAMUEL_RISK_CLASS", raising=False)
        assert resolve_risk_class("bogus") == ("limited_risk", "default")
