from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import tools.control_matrix as control_matrix
from tools.control_matrix import MatrixError


def test_checked_in_document_contract_is_valid_and_rendered() -> None:
    contract = control_matrix.load_document_contract()

    truth = control_matrix.validate_document_contract(contract)

    assert "docs/RUNTIME_REFERENCE.md" in truth["documents"]
    assert "docs/adr/README.md" in truth["documents"]
    assert {
        "runtime-reference",
        "architecture-watch-concurrency",
        "technical-ac-tags",
        "operating-plan-complexity",
        "technical-persistence-artifacts",
        "adr-index",
        "design-claims-to-code",
        "technical-cli-reference",
    } <= truth["sections"]


def test_python_symbol_binding_ignores_unrelated_symbol_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "module.py"
    source.write_text("def target():\n    return 1\n\ndef unrelated():\n    return 2\n")
    monkeypatch.setattr(control_matrix, "ROOT", tmp_path)
    descriptor = [{"path": "module.py", "kind": "python_symbol", "symbol": "target"}]

    initial = control_matrix._contract_source_digest(descriptor)
    source.write_text("def target():\n    return 1\n\ndef unrelated():\n    return 3\n")
    assert control_matrix._contract_source_digest(descriptor) == initial

    source.write_text("def target():\n    return 4\n\ndef unrelated():\n    return 3\n")
    assert control_matrix._contract_source_digest(descriptor) != initial


def test_stale_manual_section_binding_is_rejected() -> None:
    contract = deepcopy(control_matrix.load_document_contract())
    section = next(item for item in contract["sections"] if item["mode"] == "manual")
    section["source_digest"] = "sha256:" + "0" * 64

    with pytest.raises(MatrixError, match="source binding is stale"):
        control_matrix.validate_document_contract(contract)


def test_render_precondition_rejects_stale_manual_review() -> None:
    contract = deepcopy(control_matrix.load_document_contract())
    section = next(item for item in contract["sections"] if item["mode"] == "manual")
    section["source_digest"] = "sha256:" + "0" * 64

    with pytest.raises(MatrixError, match="manual documentation review required before render"):
        control_matrix._require_manual_reviews_current(contract)


def test_impact_report_names_section_sources_and_required_proofs() -> None:
    contract = deepcopy(control_matrix.load_document_contract())
    section = next(item for item in contract["sections"] if item["id"] == "technical-cli-reference")
    section["source_digest"] = "sha256:" + "0" * 64

    impact = control_matrix.document_contract_impact(contract)
    item = next(entry for entry in impact if entry["section"] == "technical-cli-reference")

    assert item["reason"] == "source_binding_changed"
    assert "samuel/cli.py" in item["sources"]
    assert (
        "tests/test_cli_help.py::test_every_subcommand_help_contains_an_example" in item["proofs"]
    )


def test_design_binding_excludes_cyclic_matrix_audit_metadata() -> None:
    contract = control_matrix.load_document_contract()
    section = next(item for item in contract["sections"] if item["id"] == "design-claims-to-code")
    matrix_sources = [
        source
        for source in section["sources"]
        if source["path"] == "docs/capabilities/control-matrix.json"
    ]

    assert matrix_sources
    assert all(source["kind"] == "json_pointer" for source in matrix_sources)
    assert all(not source["pointer"].startswith("/audit") for source in matrix_sources)


def test_runtime_reference_changes_with_shipped_eval_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_load = control_matrix._load_json
    original = control_matrix.render_runtime_reference()

    def changed_load(path: Path) -> object:
        value = original_load(path)
        if path == control_matrix.ROOT / "config" / "eval.json":
            assert isinstance(value, dict)
            return {**value, "baseline": 0.73}
        return value

    monkeypatch.setattr(control_matrix, "_load_json", changed_load)

    changed = control_matrix.render_runtime_reference()

    assert "Eval-Baseline `0.8` | `config/eval.json`" in original
    assert "Eval-Baseline `0.73` | `config/eval.json`" in changed
    assert changed != original


def test_runtime_reference_changes_with_shipped_retention_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_load = control_matrix._load_json
    original = control_matrix.render_runtime_reference()

    def changed_load(path: Path) -> object:
        value = original_load(path)
        if path == control_matrix.ROOT / "config" / "privacy.json":
            assert isinstance(value, dict)
            changed = deepcopy(value)
            changed["retention"]["managed_backup_dir"] = "runtime/managed-backups"
            return changed
        return value

    monkeypatch.setattr(control_matrix, "_load_json", changed_load)

    changed = control_matrix.render_runtime_reference()

    assert "Managed-Backup-Grenze `data/backups`" in original
    assert "Managed-Backup-Grenze `runtime/managed-backups`" in changed
    assert changed != original


def test_runtime_reference_generates_exact_verifier_environment_allowlist() -> None:
    truth = control_matrix._verifier_environment_truth()
    rendered = control_matrix.render_runtime_reference()

    assert truth["profile"] == "verifier-sterile.v1"
    assert truth["keys"] == sorted(
        [
            "HOME",
            "LANG",
            "LC_ALL",
            "NO_COLOR",
            "PATH",
            "PYTHONUNBUFFERED",
            "PYTHONUTF8",
            "TEMP",
            "TMP",
            "TMPDIR",
            "TZ",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_RUNTIME_DIR",
            "XDG_STATE_HOME",
        ]
    )
    assert "Candidate-Prozessumgebung `verifier-sterile.v1`" in rendered
    assert all(f"`{name}`" in rendered for name in truth["keys"])


def test_runtime_reference_binds_preflight_and_evidence_schema_truth() -> None:
    rendered = control_matrix.render_runtime_reference()

    assert "GateResult-Schema `2`, Observation-Schema `2`" in rendered
    assert "Statische Preflight-Gates: `7b`, `8`, `9`, `13a`, `13b`" in rendered
    assert "als `skipped_precondition` geführt" in rendered
    assert "Candidate-Verifikation wird nicht gestartet" in rendered


def test_ac_registry_and_generated_table_are_exact() -> None:
    truth = control_matrix._ac_tag_truth()
    rendered = control_matrix.render_ac_tag_table()

    assert truth["available"] == [
        "DIFF",
        "EXISTS",
        "GREP",
        "GREP:NOT",
        "IMPORT",
        "MANUAL",
        "TEST",
    ]
    assert "[EXISTS]" in rendered
    assert "[USE]" not in rendered
    assert "[REQUIRE]" not in rendered


def test_watch_concurrency_reference_is_bound_to_sync_try_finally() -> None:
    truth = control_matrix._watch_concurrency_truth()
    rendered = control_matrix.render_watch_concurrency()

    assert truth == {
        "bus_mode": "synchronous",
        "scan_dispatch": "sequential",
        "guarded_dispatches": 2,
        "acquire_method": "WatchHandler._try_acquire",
        "release_method": "WatchHandler._release",
        "release_trigger": "synchronous dispatch return via try/finally",
        "terminal_event_subscription": False,
        "coordination_scope": "process-local",
        "multi_process_coordination": False,
        "supported_max_parallel": 1,
        "agent_max_parallel": 1,
        "workflow_max_parallel": {
            "autonomous": 1,
            "chat": 1,
            "night": 1,
            "patch": 1,
            "self": 1,
            "standard": 1,
            "watch": 1,
        },
        "unsupported_values": "fail-closed",
    }
    assert "keine Bootstrap-Subscription" in rendered
    assert "`try/finally`" in rendered
    assert "koordiniert keine anderen" in rendered
    assert "Werte ungleich `1` blockieren den Start" in rendered


def test_persistence_reference_names_config_and_code_provenance() -> None:
    rendered = control_matrix.render_persistence_artifacts()

    assert "`data/logs/agent.jsonl`" in rendered
    assert "`data/logs/agent.jsonl.fallback`" in rendered
    assert "ausgeliefert konfiguriert" in rendered
    assert "`<data_dir>/quality_metrics.json.migrated-<sha256>`" in rendered
    assert "`<data_dir>/samuel-state.sqlite3`" in rendered
    assert "`data/backups`" in rendered
    assert "Schema v10" in rendered
    assert "technisch verwaltete Backup-Retentiongrenze" in rendered
    assert "aktive Serienprojektion liegt in SQLite" in rendered
    assert "einseitiger Import" in rendered
    assert "codegebundener Dateiname" in rendered


def test_checked_in_generated_reference_lists_its_bound_sources() -> None:
    rendered = control_matrix.RUNTIME_REFERENCE_PATH.read_text(encoding="utf-8")

    assert "## Quellenbindung" in rendered
    assert "`samuel/core/commands.py`" in rendered
    assert "document-contract.json::runtime-reference" in rendered


def test_missing_generated_block_is_rejected() -> None:
    with pytest.raises(MatrixError, match="generated documentation block"):
        control_matrix._replace_generated_block("# no marker\n", "missing", "replacement")


def test_missing_repository_document_in_prose_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guide = tmp_path / "guide.md"
    guide.write_text("Siehe `docs/missing.md`.\n", encoding="utf-8")
    monkeypatch.setattr(control_matrix, "ROOT", tmp_path)

    assert control_matrix._validate_document_links({"guide.md"}) == [
        "guide.md: missing repository document `docs/missing.md`"
    ]


def test_missing_markdown_anchor_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guide = tmp_path / "guide.md"
    target = tmp_path / "target.md"
    guide.write_text("[Abschnitt](target.md#missing)\n", encoding="utf-8")
    target.write_text("# Vorhanden\n", encoding="utf-8")
    monkeypatch.setattr(control_matrix, "ROOT", tmp_path)

    assert control_matrix._validate_document_links({"guide.md", "target.md"}) == [
        "guide.md: missing Markdown anchor target.md#missing"
    ]


def test_markdown_target_cannot_escape_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (tmp_path / "outside.md").write_text("# Outside\n", encoding="utf-8")
    (repository / "guide.md").write_text("[Outside](../outside.md)\n", encoding="utf-8")
    monkeypatch.setattr(control_matrix, "ROOT", repository)

    assert control_matrix._validate_document_links({"guide.md"}) == [
        "guide.md: Markdown target escapes repository ../outside.md"
    ]


def test_superseded_adr_requires_known_successor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    body = "# Old\n"
    decision_digest = control_matrix._adr_decision_digest(body)
    (adr_dir / "0001-old.md").write_text(
        "---\n"
        "id: ADR-0001\n"
        "title: Old decision\n"
        "status: superseded\n"
        "decision_issue: 1\n"
        "decision_date: 2026-08-28\n"
        f"decision_digest: {decision_digest}\n"
        "supersedes: []\n"
        "superseded_by: []\n"
        f"---\n\n{body}",
        encoding="utf-8",
    )
    monkeypatch.setattr(control_matrix, "ROOT", tmp_path)
    monkeypatch.setattr(control_matrix, "ADR_INDEX_PATH", adr_dir / "README.md")

    with pytest.raises(MatrixError, match="superseded ADR requires superseded_by"):
        control_matrix._adr_truth()
