"""#269: Tests fuer JSON-Loading der OWASP/AI-Act-Mappings.

Sicherstellt, dass die Externalisierung der Mappings nach
config/compliance/*.json:
  1. Sauber laedt (Smoke)
  2. Fail loud auf fehlende oder kaputte JSON wirft
  3. Bestehende classify()-API byte-fuer-byte das gleiche zurueckgibt
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def test_owasp_loaded_from_json():
    from samuel.core import owasp
    assert owasp.OWASP_RISK_MAP, "Mapping muss non-empty sein"
    # Smoke: bekannter Eintrag aus dem alten Hardcoded-Stand
    assert owasp.classify("scm", "pr_merge") == "broken_trust_boundaries"
    assert owasp.classify("eval", "ac_verified") == "inadequate_feedback_loops"
    # Fallback-Pfad
    assert owasp.classify("guard", "unknown_evt") == "inadequate_sandboxing"


def test_ai_act_loaded_from_json():
    from samuel.core import ai_act
    assert ai_act.AI_ACT_ARTICLE_MAP, "Mapping muss non-empty sein"
    assert ai_act.classify("scm", "pr_merge") == "Art. 12"
    assert ai_act.classify("llm", "llm_call") == "Art. 50"
    # Fallback-Pfad
    assert ai_act.classify("eval", "unknown_evt") == "Art. 15"


def test_owasp_top10_has_ten_entries():
    from samuel.core import owasp
    assert len(owasp.OWASP_TOP10) == 10
    ids = {c["id"] for c in owasp.OWASP_TOP10}
    assert ids == {f"A{i:02d}" for i in range(1, 11)}


def test_ai_act_articles_sorted():
    from samuel.core import ai_act
    ids = [a["article"] for a in ai_act.AI_ACT_ARTICLES]
    assert ids == sorted(ids)


def test_owasp_fail_loud_on_missing_json(tmp_path: Path, monkeypatch):
    """Fehlende owasp.json -> RuntimeError, kein silent leerer Mapping."""
    monkeypatch.setattr(
        "samuel.core.owasp._COMPLIANCE_DIR",
        tmp_path / "nope",
    )
    # _load wird als Modul-Funktion direkt aufgerufen, importlib.reload waere
    # zu invasiv — testen wir _load() direkt.
    from samuel.core import owasp
    with pytest.raises(RuntimeError, match="missing"):
        owasp._load()


def test_owasp_fail_loud_on_broken_json(tmp_path: Path, monkeypatch):
    """Kaputte JSON -> RuntimeError mit klarer Begruendung."""
    (tmp_path / "owasp.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr("samuel.core.owasp._COMPLIANCE_DIR", tmp_path)
    from samuel.core import owasp
    with pytest.raises(RuntimeError, match="not parsable"):
        owasp._load()


def test_owasp_fail_loud_on_missing_key(tmp_path: Path, monkeypatch):
    """JSON ohne 'mappings' -> RuntimeError."""
    (tmp_path / "owasp.json").write_text(
        json.dumps({"categories": [], "fallbacks": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("samuel.core.owasp._COMPLIANCE_DIR", tmp_path)
    from samuel.core import owasp
    with pytest.raises(RuntimeError, match="missing key"):
        owasp._load()


def test_ai_act_fail_loud_on_missing_json(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("samuel.core.ai_act._COMPLIANCE_DIR", tmp_path / "nope")
    from samuel.core import ai_act
    with pytest.raises(RuntimeError, match="missing"):
        ai_act._load()


def test_compliance_dir_is_package_relative():
    """#292: _COMPLIANCE_DIR muss innerhalb des samuel-Packages liegen,
    sonst funktionieren pip-installierte Deployments nicht (Regression aus #269)."""
    from samuel.core import owasp, ai_act
    pkg_root = Path(owasp.__file__).resolve().parent  # samuel/core/
    assert owasp._COMPLIANCE_DIR == pkg_root / "compliance"
    assert ai_act._COMPLIANCE_DIR == pkg_root / "compliance"
    # Beide File muessen existieren — sonst war das Verschieben nicht vollstaendig
    assert (owasp._COMPLIANCE_DIR / "owasp.json").exists()
    assert (ai_act._COMPLIANCE_DIR / "ai_act.json").exists()


def test_compliance_loads_when_cwd_is_not_repo_root(tmp_path: Path, monkeypatch):
    """#292: pip-Deployment-Szenario — cwd ist nicht das Repo-Root.
    Loading muss trotzdem klappen, weil _COMPLIANCE_DIR package-relativ ist."""
    monkeypatch.chdir(tmp_path)
    from samuel.core import owasp, ai_act
    # Re-load nach chdir — Pfad muss weiter auflöesen
    owasp._load()  # darf nicht crashen
    ai_act._load()


def test_compliance_jsons_in_package_data():
    """#292: pyproject.toml muss core/compliance/*.json als package-data deklarieren,
    sonst reisen die Files bei pip-install nicht mit."""
    pyproject_text = (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "core/compliance/*.json" in pyproject_text, (
        "package-data muss core/compliance/*.json enthalten — sonst pip-install bricht den Import"
    )