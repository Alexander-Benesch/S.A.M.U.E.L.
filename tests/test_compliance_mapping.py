from __future__ import annotations

import json
from pathlib import Path

import pytest

from samuel.core import compliance_mapping
from samuel.core.compliance_mapping import COMPLIANCE_DIR, load_mapping


@pytest.mark.parametrize(
    ("filename", "controls", "reference", "key"),
    [("owasp", "categories", "risk", "key"), ("ai_act", "articles", "article", "id")],
)
def test_existing_frameworks_preserve_all_exact_and_fallback_mappings(
    filename: str, controls: str, reference: str, key: str
) -> None:
    pack = load_mapping(
        COMPLIANCE_DIR / f"{filename}.json",
        controls_key=controls,
        reference_key=reference,
        control_key=key,
    )
    data = json.loads((COMPLIANCE_DIR / f"{filename}.json").read_text())
    for row in data["mappings"]:
        assert pack.reference(row["cat"], row["evt"]) == row[reference]
    for cat, value in data["fallbacks"].items():
        assert pack.reference(cat, "unmapped-fixture-event") == value
    assert pack.reference("unknown", "unknown") is None


def test_changed_definition_preserves_historical_identity_and_evidence(tmp_path: Path) -> None:
    original = load_mapping(COMPLIANCE_DIR / "cra.json")
    before = original.annotate(
        scope="repo-a/release-1",
        selected_scopes=("repo-a/release-1",),
        evidence_id="sha256:" + "1" * 64,
        category="eval",
        event="test_run",
    )
    data = json.loads((COMPLIANCE_DIR / "cra.json").read_text())
    data["mapping_version"] = "1.1.0"
    data["mappings"][0]["control"] = "risk-assessment"
    target = tmp_path / "changed.json"
    target.write_text(json.dumps(data))
    changed = load_mapping(target)
    assert changed.reference("eval", "test_run") == "risk-assessment"
    assert original.reference("eval", "test_run") == "security-tests"
    assert changed.digest != original.digest
    assert before is not None
    assert before["control"] == "security-tests"
    assert before["mapping_digest"] == original.digest
    assert before["mapping_version"] == "1.0.0"
    assert before["evidence_id"] == "sha256:" + "1" * 64


def test_same_version_content_change_has_a_distinct_mapping_identity(tmp_path: Path) -> None:
    data = json.loads((COMPLIANCE_DIR / "cra.json").read_text())
    original = load_mapping(COMPLIANCE_DIR / "cra.json")
    data["mappings"][0]["control"] = "risk-assessment"
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(data))
    assert load_mapping(path).digest != original.digest


def test_selection_is_exact_and_same_evidence_can_serve_multiple_frameworks() -> None:
    args = {
        "scope": "repo-a/release-1",
        "selected_scopes": ("repo-a/release-1",),
        "evidence_id": "existing-evaluation-observation",
        "category": "guard",
        "event": "quality_check",
    }
    cra = load_mapping(COMPLIANCE_DIR / "cra.json")
    gdpr = load_mapping(COMPLIANCE_DIR / "gdpr.json")
    a, b = cra.annotate(**args), gdpr.annotate(**args)
    assert a is not None and b is not None
    assert a["evidence_id"] == b["evidence_id"] == args["evidence_id"]
    assert a["framework"] != b["framework"]
    assert a["effect"] == b["effect"] == "advisory"
    assert cra.annotate(**{**args, "selected_scopes": ()}) is None
    assert cra.annotate(**{**args, "scope": "repo-a/release-10"}) is None


@pytest.mark.parametrize("change", ["unknown-control", "duplicate", "bad-controls", "empty-id"])
def test_invalid_definition_is_rejected_before_annotation(tmp_path: Path, change: str) -> None:
    data = json.loads((COMPLIANCE_DIR / "cra.json").read_text())
    if change == "unknown-control":
        data["mappings"][0]["control"] = "absent"
    elif change == "duplicate":
        data["mappings"].append(data["mappings"][0])
    elif change == "bad-controls":
        data["controls"] = None
    else:
        data["framework"] = ""
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError):
        load_mapping(path)


@pytest.mark.parametrize("invalid", ["json", "utf8", "surrogate"])
def test_bad_optional_cra_definition_does_not_damage_existing_frameworks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    from samuel.core import ai_act, owasp
    from samuel.slices.dashboard.data import get_compliance_legend

    baseline = get_compliance_legend()
    for path in COMPLIANCE_DIR.glob("*.json"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    if invalid == "json":
        (tmp_path / "cra.json").write_text("{broken")
    elif invalid == "utf8":
        (tmp_path / "cra.json").write_bytes(b"\xff\xfe")
    else:
        definition = json.loads((COMPLIANCE_DIR / "cra.json").read_text())
        definition["source"] = "\ud800"
        (tmp_path / "cra.json").write_text(json.dumps(definition))
    monkeypatch.setattr(compliance_mapping, "COMPLIANCE_DIR", tmp_path)
    result = get_compliance_legend()
    assert result["owasp"] == baseline["owasp"]
    assert result["ai_act"] == baseline["ai_act"]
    assert result["frameworks"][-1]["status"] == "invalid"
    assert all(item.get("status") != "invalid" for item in result["frameworks"][:-1])
    assert owasp.classify("scm", "pr_merge") == "agentic_supply_chain"
    assert ai_act.classify("scm", "pr_merge") == "Art. 12"


def test_cra_legend_names_real_existing_primitives() -> None:
    root = Path(__file__).resolve().parents[1]
    for control in load_mapping(COMPLIANCE_DIR / "cra.json").legend()["controls"]:
        assert control["evidence_types"]
        assert all((root / primitive).exists() for primitive in control["primitives"])
