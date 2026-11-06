from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

import tools.control_matrix as control_matrix
from tools.control_matrix import MatrixError


def _impact_git(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True).strip()


def _impact_write(repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _impact_commit(repo: Path) -> str:
    _impact_git(repo, "add", "--all")
    _impact_git(repo, "commit", "-qm", "documentation impact fixture")
    return _impact_git(repo, "rev-parse", "HEAD")


@pytest.fixture
def impact_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _impact_git(tmp_path, "init", "-q")
    _impact_git(tmp_path, "config", "user.name", "Documentation Test")
    _impact_git(tmp_path, "config", "user.email", "docs@example.invalid")
    _impact_git(tmp_path, "config", "commit.gpgsign", "false")
    monkeypatch.setattr(control_matrix, "ROOT", tmp_path)
    _impact_write(tmp_path, "README.md", "# fixture\n")
    return tmp_path


def test_change_impact_finds_new_unbound_cli_api_and_config_without_importing(
    impact_repo: Path,
) -> None:
    base = _impact_commit(impact_repo)
    _impact_write(
        impact_repo,
        "new_component/entry.py",
        'raise RuntimeError("must not import")\n'
        'parser.add_parser("launch")\nparser.add_argument("--new-option")\n'
        'route = "POST /api/new"\n',
    )
    _impact_write(impact_repo, "config/new.json", '{"feature": {"enabled": true}}')
    head = _impact_commit(impact_repo)
    report = control_matrix.document_change_impact(base, head)
    changed = {item["path"]: item for item in report["changes"]}

    assert set(changed) == {"new_component/entry.py", "config/new.json"}
    assert changed["new_component/entry.py"]["surface_hints"]["added"] == [
        "add_argument:--new-option",
        "add_parser:launch",
        "api_literal:POST /api/new",
    ]
    assert changed["config/new.json"]["surface_hints"]["added"] == [
        "json_field:/feature",
        "json_field:/feature/enabled",
    ]
    assert all(item["binding_assessment"] == "unbound" for item in changed.values())
    assert all(item["semantic_review_required"] for item in changed.values())
    assert report["contract_present"] == {"base": False, "head": False}
    assert report["authority"] == "advisory"


def test_change_impact_retains_old_binding_when_source_and_binding_are_removed(
    impact_repo: Path,
) -> None:
    contract = {
        "sections": [
            {
                "id": "old-api",
                "document": "docs/api.md",
                "mode": "manual",
                "sources": [{"kind": "python_symbol", "path": "product/api.py", "symbol": "call"}],
            }
        ]
    }
    _impact_write(impact_repo, "docs/capabilities/document-contract.json", json.dumps(contract))
    _impact_write(impact_repo, "product/api.py", "def call():\n    return 1\n")
    base = _impact_commit(impact_repo)
    (impact_repo / "product/api.py").unlink()
    _impact_write(impact_repo, "docs/capabilities/document-contract.json", '{"sections": []}')
    head = _impact_commit(impact_repo)

    report = control_matrix.document_change_impact(base, head)
    deleted = next(item for item in report["changes"] if item["path"] == "product/api.py")
    assert deleted["status"] == "D"
    assert deleted["bindings_before"][0]["section"] == "old-api"
    assert deleted["bindings_after"] == []
    assert deleted["semantic_review_required"]


def test_change_impact_maps_rename_and_preserves_special_filename(impact_repo: Path) -> None:
    path = "product/old\n[1].py"
    _impact_write(impact_repo, path, "def run():\n    return 1\n")
    base = _impact_commit(impact_repo)
    (impact_repo / path).rename(impact_repo / "product/new.py")
    head = _impact_commit(impact_repo)
    report = control_matrix.document_change_impact(base, head)

    assert len(report["changes"]) == 1
    change = report["changes"][0]
    assert change["status"] == "R100"
    assert change["previous_path"] == path
    assert change["path"] == "product/new.py"
    assert change["surface_hints"]["base_status"] == "partial_structural_hints"
    assert change["semantic_review_required"]


@pytest.mark.parametrize(
    "path,before,after",
    [
        (
            "samuel/workflow.py",
            "def permit():\n    return False\n",
            "def permit():\n    return True\n",
        ),
        ("config/feature.json", '{"required": false}', '{"required": true}'),
        (".claude/CLAUDE.md", "Review permissions.\n", "Review permissions and restart effects.\n"),
    ],
)
def test_unchanged_surface_does_not_waive_semantic_review(
    impact_repo: Path,
    path: str,
    before: str,
    after: str,
) -> None:
    _impact_write(impact_repo, path, before)
    base = _impact_commit(impact_repo)
    _impact_write(impact_repo, path, after)
    head = _impact_commit(impact_repo)

    report = control_matrix.document_change_impact(base, head)
    change = report["changes"][0]
    assert change["path"] == path
    assert change["surface_hints"]["added"] == change["surface_hints"]["removed"] == []
    assert change["semantic_review_required"]
    assert "concrete reason no update is needed" in report["review_record"]


def test_change_impact_uses_commits_not_dirty_checkout_or_config_values(impact_repo: Path) -> None:
    _impact_write(impact_repo, "config/new.json", '{"key": "old-value"}')
    base = _impact_commit(impact_repo)
    _impact_write(impact_repo, "config/new.json", '{"key": "fixture-secret-do-not-output"}')
    head = _impact_commit(impact_repo)
    _impact_write(impact_repo, "config/new.json", '{"uncommitted-field": 1}')
    _impact_write(impact_repo, ".env", "PRIVATE=untracked-value\n")

    report = control_matrix.document_change_impact(base, head)
    serialized = json.dumps(report)
    assert report["base_commit"] == base and report["head_commit"] == head
    assert {item["path"] for item in report["changes"]} == {"config/new.json"}
    assert "fixture-secret-do-not-output" not in serialized
    assert "uncommitted-field" not in serialized and "untracked-value" not in serialized


@pytest.mark.parametrize(
    "path,text", [("product/broken.py", "def incomplete("), ("config/broken.json", "{")]
)
def test_unparseable_changed_source_is_visible_and_requires_review(
    impact_repo: Path,
    path: str,
    text: str,
) -> None:
    base = _impact_commit(impact_repo)
    _impact_write(impact_repo, path, text)
    head = _impact_commit(impact_repo)
    change = control_matrix.document_change_impact(base, head)["changes"][0]
    assert change["surface_hints"]["head_status"] == "unresolved"
    assert change["semantic_review_required"]


def test_change_impact_rejects_unreadable_ref_and_malformed_contract(impact_repo: Path) -> None:
    base = _impact_commit(impact_repo)
    with pytest.raises(MatrixError, match="Git input"):
        control_matrix.document_change_impact("--help", base)
    _impact_write(impact_repo, "docs/capabilities/document-contract.json", '{"sections": [null]}')
    head = _impact_commit(impact_repo)
    with pytest.raises(MatrixError, match="source bindings"):
        control_matrix.document_change_impact(base, head)


def test_change_impact_glob_binding_is_only_a_candidate(impact_repo: Path) -> None:
    contract = {
        "sections": [
            {
                "id": "components",
                "document": "docs/components.md",
                "mode": "manual",
                "sources": [{"kind": "glob", "path": "product/**/*.py"}],
            }
        ]
    }
    _impact_write(impact_repo, "docs/capabilities/document-contract.json", json.dumps(contract))
    base = _impact_commit(impact_repo)
    _impact_write(impact_repo, "product/new/feature.py", "enabled = True\n")
    head = _impact_commit(impact_repo)
    change = control_matrix.document_change_impact(base, head)["changes"][0]
    assert change["binding_assessment"] == "candidate_bindings"
    assert change["bindings_after"][0]["section"] == "components"
    assert change["semantic_review_required"]


def test_change_impact_empty_diff_has_no_semantic_pass(impact_repo: Path) -> None:
    commit = _impact_commit(impact_repo)
    report = control_matrix.document_change_impact(commit, commit)
    assert report["changes"] == []
    assert report["authority"] == "advisory"
    assert any("No semantic PASS" in limit for limit in report["limits"])


def test_change_impact_cli_preserves_legacy_mode_and_rejects_check_arguments(
    impact_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = _impact_commit(impact_repo)
    _impact_write(impact_repo, "new.py", "enabled = True\n")
    head = _impact_commit(impact_repo)
    monkeypatch.setattr("sys.argv", ["control_matrix.py", "impact", "--base", base])
    assert control_matrix.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["head_commit"] == head
    assert report["changes"][0]["path"] == "new.py"

    monkeypatch.setattr(control_matrix, "load_matrix", lambda: {})
    monkeypatch.setattr(control_matrix, "load_document_contract", lambda: {"sections": []})
    monkeypatch.setattr("sys.argv", ["control_matrix.py", "impact"])
    assert control_matrix.main() == 0
    assert json.loads(capsys.readouterr().out) == []

    monkeypatch.setattr("sys.argv", ["control_matrix.py", "check", "--base", base])
    assert control_matrix.main() == 1
    assert "only supported by impact" in capsys.readouterr().err


@pytest.mark.parametrize("store_kind", ["runtime", "workspace"])
def test_sqlite_document_schema_matches_created_store(tmp_path: Path, store_kind: str) -> None:
    from samuel.adapters.state.sqlite import SQLiteStateStore
    from samuel.adapters.workspace.git import GitWorktreeManager

    if store_kind == "runtime":
        path = SQLiteStateStore(tmp_path / "state").path
        rendered = control_matrix.render_sqlite_schema()
    else:
        path = GitWorktreeManager(tmp_path / "work")._db_path
        rendered = control_matrix.render_workspace_schema()
    with sqlite3.connect(path) as actual, sqlite3.connect(":memory:") as documented:
        for statement in re.findall(r"```sql\n(.*?)\n```", rendered, flags=re.S):
            documented.execute(statement)
        query = (
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
        assert documented.execute(query).fetchall() == actual.execute(query).fetchall()
        tables = actual.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        description = (control_matrix.ROOT / "docs/STATE_STORE.md").read_text()
        for (name,) in tables:
            assert f"| `{name}` |" in description


def test_document_index_lists_every_project_markdown() -> None:
    index = (control_matrix.ROOT / "docs/README.md").read_text()
    paths = control_matrix._tracked_paths()
    assert paths is not None, "Inventory verification requires the repository checkout"
    for path in paths:
        relative = path.relative_to(control_matrix.ROOT).as_posix()
        if path.suffix == ".md" or relative.startswith("docs/"):
            assert f"[{relative}]" in index, f"Documentation missing from inventory: {relative}"


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
    assert "Statische Preflight-Gates: `7`, `7b`, `8`, `9`, `13a`, `13b`" in rendered
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


def test_technical_slice_catalog_covers_every_shipped_slice() -> None:
    import re

    text = (control_matrix.ROOT / "docs/README_technical.md").read_text(encoding="utf-8")
    catalog = text.split("## 6. Slice-Katalog", 1)[1].split("## 7.", 1)[0]
    described = set(re.findall(r"^\| `([a-z_]+)` \|", catalog, re.MULTILINE))
    shipped = {
        path.parent.name for path in (control_matrix.ROOT / "samuel/slices").glob("*/__init__.py")
    }

    assert described == shipped, (
        f"undocumented={shipped - described}; obsolete={described - shipped}"
    )


def test_api_reference_covers_http_dispatch_and_exact_permissions() -> None:
    import ast
    import re

    from samuel.adapters.api.auth import AUTHENTICATED, permission_for_request
    from samuel.core import identity

    text = (control_matrix.ROOT / "docs/README_technical.md").read_text(encoding="utf-8")
    table = text.split("## 18. API-Endpoints", 1)[1].split("\nPlan-, Implement-", 1)[0]
    documented: dict[str, set[str]] = {method: set() for method in ("GET", "POST", "DELETE")}
    for line in table.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 4 or cells[0] not in documented:
            continue
        method, path_cell, _description, access = cells
        permissions = re.findall(r"`([A-Z_]+)`", access)
        for path in re.findall(r"`(/[^`]+)`", path_cell):
            documented[method].add(path)
            if permissions:
                concrete = re.sub(r"\{[^}]+\}", "example", path)
                assert permission_for_request(method, concrete) == getattr(identity, permissions[0])
            elif "Authentisiert" in access:
                assert permission_for_request(method, path) == AUTHENTICATED

    server_tree = ast.parse((control_matrix.ROOT / "samuel/server.py").read_text())
    handler = next(
        node
        for node in server_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SAMUELRequestHandler"
    )
    for function in handler.body:
        if not isinstance(function, ast.FunctionDef) or function.name not in {
            "do_GET",
            "do_POST",
            "do_DELETE",
        }:
            continue
        method = function.name.removeprefix("do_")
        for node in ast.walk(function):
            if isinstance(node, ast.Compare):
                for value in node.comparators:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        if value.value.startswith("/api/"):
                            assert value.value in documented[method], (method, value.value)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr != "startswith" or not node.args:
                    continue
                value = node.args[0]
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    if value.value.startswith("/api/"):
                        assert any(path.startswith(value.value) for path in documented[method]), (
                            method,
                            value.value,
                        )

    rest_tree = ast.parse((control_matrix.ROOT / "samuel/adapters/api/rest.py").read_text())
    for node in ast.walk(rest_tree):
        if isinstance(node, ast.Compare):
            for value in node.comparators:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    if " /api/" in value.value:
                        method, path = value.value.split(" ", 1)
                        assert path in documented[method], (method, path)


def test_technical_reference_names_every_installed_console_script() -> None:
    import tomllib

    project = tomllib.loads((control_matrix.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    text = (control_matrix.ROOT / "docs/README_technical.md").read_text(encoding="utf-8")

    assert all(f"`{name}`" in text for name in project["project"]["scripts"])


def test_runtime_grep_reference_includes_supported_inline_code_hull() -> None:
    rendered = control_matrix.render_runtime_reference()

    assert "vollständige Markdown-Inline-Code-Hülle" in rendered
    assert "Enthält das Pattern beide Arten" not in rendered


def test_technical_reference_documents_every_tracked_repository_tool() -> None:
    import subprocess

    root = control_matrix.ROOT
    tracked = subprocess.run(
        ["git", "ls-files", "--", "tools/"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    text = (root / "docs/README_technical.md").read_text(encoding="utf-8")
    catalog = text.split("## 25. Repositorywerkzeuge und zusätzliche Projektdateien", 1)[1]

    assert tracked
    for path in tracked:
        assert f"`{Path(path).name}`" in catalog, path
