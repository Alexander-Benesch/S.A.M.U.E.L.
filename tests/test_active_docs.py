from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from samuel.core.gate_metadata import GATE_NAMES

ROOT = Path(__file__).parents[1]
ACTIVE_DOCS = (
    ROOT / "MANIFESTO.md",
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / ".claude" / "CLAUDE.md",
    *sorted((ROOT / "docs").glob("*.md")),
)
TECHNICAL_DESCRIPTIONS = tuple(sorted((ROOT / "technische Beschreibungen").glob("*.md")))


def test_active_docs_do_not_depend_on_workstation_or_legacy_checkout() -> None:
    forbidden = (
        "/home/",
        "SAMUEL_V1_ROOT",
        "gitea-agent/.env",
    )

    findings = [
        f"{path.relative_to(ROOT)}: {value}"
        for path in ACTIVE_DOCS
        for value in forbidden
        if value in path.read_text(encoding="utf-8")
    ]

    assert findings == []


def test_active_docs_do_not_reference_removed_session_documents() -> None:
    removed = (
        "docs/PHASE_WORKFLOW.md",
        "docs/HANDOVER_2026-06-01.md",
        "docs/PHASE_1_HARDENING_CHARTER.md",
    )

    findings = [
        f"{path.relative_to(ROOT)}: {value}"
        for path in ACTIVE_DOCS
        for value in removed
        if value in path.read_text(encoding="utf-8")
    ]

    assert findings == []


def test_manifesto_separates_current_truth_from_open_direction() -> None:
    manifesto = (ROOT / "MANIFESTO.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for heading in (
        "## Unsere These",
        "## Leitprinzipien",
        "## Was heute existiert",
        "## Wohin das Projekt geht",
        "## Was wir bewusst nicht bauen",
        "## Mitarbeit und Diskussion",
    ):
        assert heading in manifesto
    for authority in (
        "docs/README_technical.md",
        "docs/RUNTIME_REFERENCE.md",
        "docs/CAPABILITY_MATRIX.md",
        "docs/adr/README.md",
    ):
        assert authority in manifesto
    for open_issue in ("#520", "#521", "#639", "#658", "#679"):
        assert open_issue in manifesto
    assert "Echte Candidate-Sandbox (#619)" not in manifesto
    assert "keine Runtime-Spezifikation" in manifesto
    assert "passive, workerneutrale Übergabe" in manifesto
    assert "allgemeine aktive Fremdworkersteuerung" in manifesto
    assert "keine juristische" in manifesto
    assert "Benötigte Ebenen austauschbarer Nicht-Core-Capabilities" in manifesto
    assert "Drei Ebenen jeder Capability" not in manifesto
    assert "Kein Producer, Agent oder Provider erhält implizite Autorität" in manifesto
    assert "Self-Mode verändert Candidates, nicht seine eigene Autorität" in manifesto
    assert "Candidate oder Producer eine Evidence erzeugen" in manifesto
    assert "[S.A.M.U.E.L. Manifest](MANIFESTO.md)" in readme


def test_active_configuration_does_not_advertise_removed_context_dir() -> None:
    checked_files = (ROOT / ".env.example", ROOT / "docs" / "INSTALL.md")

    findings = [
        str(path.relative_to(ROOT))
        for path in checked_files
        if "CONTEXT_DIR" in path.read_text(encoding="utf-8")
    ]

    assert findings == []
    install_text = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    assert "`PROJECT_ROOT` | Lokaler Pfad des überwachten Projekts" in install_text


def test_install_prerequisites_separate_roles_paths_and_secret_channels() -> None:
    install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    container_ops = (ROOT / "docs" / "CONTAINER_RELEASE_OPERATIONS.md").read_text(encoding="utf-8")
    runner_ops = (ROOT / "docs" / "CI_RUNNER_OPERATIONS.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for marker in (
        "### 1.1 Betriebsarten und externe Voraussetzungen",
        "Wheel/venv",
        "OCI/Docker",
        "Dashboard",
        "Watch/Einzellauf",
        "Release-/Image-Publish",
        "Externer Gitea-Actions-Runner",
        "### 1.2 Accounts, Credentials und kleinste Rechte",
        "S.A.M.U.E.L.-SCM-Bot",
        "Private-Registry-Leser",
        "Package-Publisher",
        "Gitea-Runner-Registrierung",
        "### 1.3 Pfade: erhalten, ersetzen oder getrennt prüfen",
        "agent.data_dir",
        "agent.workspace.work_dir",
        "managed_backup_dir",
        "`doctor` und `health` prüfen",
    ):
        assert marker in install

    assert "read:package" in install
    assert "write:package" in install
    assert "--password-stdin" in install
    assert "--password-stdin" in container_ops
    assert "Die `--token`-Variante ist im Betriebsrunbook\nunzulässig" in runner_ops
    assert "SCM_URL=https://gitea.example.invalid" in env_example
    assert "SCM_TOKEN=…" not in install


def test_operator_preflight_contract_is_selective_and_secret_free() -> None:
    rules = (ROOT / "docs" / "OPERATING_RULES.md").read_text(encoding="utf-8")
    install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

    for marker in (
        "Qualification-Operatorpreflight vor der ersten Wirkung",
        "stored_effective=match|mismatch|not_applicable",
        "Ein lokaler Seed-Transferpfad ist keine Runtime-Remoteauthority",
        "Demo-SCM,\nRuntime-Bot-Konfiguration",
        "planning`, `implementation`, `review`,\n`healing` und `evaluation",
    ):
        assert marker in rules
    assert "vollständige alte `.env`" in rules
    assert "alle fünf wirksamen Taskrouten" in install
    assert "`missing` und `mismatch`\nblockieren" in install


def test_active_public_docs_do_not_expose_private_reference_network() -> None:
    private_ipv4 = re.compile(
        r"(?<![\d.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![\d.])"
    )
    checked = (*ACTIVE_DOCS, ROOT / ".env.example")
    findings = [
        str(path.relative_to(ROOT))
        for path in checked
        if private_ipv4.search(path.read_text(encoding="utf-8"))
        or "example-owner" in path.read_text(encoding="utf-8")
    ]

    assert findings == []


def test_historical_gap_analyses_are_archived() -> None:
    assert not list((ROOT / "docs").glob("*GAP_ANALYSE*.md"))
    assert (ROOT / "docs" / "archive" / "V2.1_GAP_ANALYSE_THEMATISCH.md").is_file()


def test_llm_config_ownership_and_precedence_are_documented() -> None:
    technical = (ROOT / "docs" / "README_technical.md").read_text(encoding="utf-8")

    for config_path in (
        "config/llm.json",
        "config/llm/defaults.json",
        "config/llm/providers.json",
    ):
        assert config_path in technical
    assert "SAMUEL_LLM_PROVIDER" in technical
    assert "keine** Laufzeit-Prioritaet" in technical
    assert "Schedule-Modell vor Task-Modell" in technical


def test_technical_descriptions_bind_review_to_date_and_commit() -> None:
    marker = re.compile(
        r"\*\*Prüfdatum:\*\* \d{4}-\d{2}-\d{2} · \*\*Abgeglichener Commit:\*\*\s*"
        r"`[0-9a-f]{40}`"
    )
    legacy_current_marker = re.compile(r"(?i)\bStand(?:\s*\*\*)?:?\s*Phase\b")

    findings = []
    for path in TECHNICAL_DESCRIPTIONS:
        text = path.read_text(encoding="utf-8")
        if marker.search(text) is None:
            findings.append(f"{path.relative_to(ROOT)}: Prüfdatum/Commit fehlt")
        if legacy_current_marker.search(text) is not None:
            findings.append(f"{path.relative_to(ROOT)}: aktive Phase-Stand-Markierung")

    assert findings == []


def test_version_policy_defines_release_and_independent_domains() -> None:
    policy_path = ROOT / "docs" / "VERSIONING.md"
    policy = policy_path.read_text(encoding="utf-8")

    for marker in (
        "v2.0.0a1",
        "v2.0.0a2",
        "ungetaggte Entwicklungsbaseline",
        "MAJOR",
        "MINOR",
        "PATCH",
        "Alpha",
        "Beta",
        "Release Candidate",
        "Build-Identität",
        "REST-API",
        "Event-Schema",
        "Konfiguration und Workflows",
        "Architektur und Dokumente",
        "Prompt und Modell",
        "Fremdformate/-APIs",
        "phase-*-complete",
    ):
        assert marker in policy

    assert "docs/VERSIONING.md" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/VERSIONING.md" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "`2.0.0a7`" in security
    assert "Latest supported alpha" in security
    assert "earlier published alphas" in security
    assert "`v2.0.0a1`" in security
    assert "no published release" in security
    assert "2.x     | Yes" not in security


def test_current_product_surfaces_do_not_duplicate_a_raw_version() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    dashboard = (ROOT / "samuel" / "server.py").read_text(encoding="utf-8")
    policy = (ROOT / "docs" / "VERSIONING.md").read_text(encoding="utf-8")

    for current_surface in (readme, security, dashboard):
        assert "2.0.0-alpha" not in current_surface
        assert "2.0.0a0" not in current_surface
    assert 'id="product-version">__SAMUEL_PRODUCT_VERSION__' in dashboard
    assert "render_dashboard_html(__build_info__.product_version)" in dashboard
    assert "2.0.0a1" not in dashboard
    assert "2.0.0a2" not in dashboard
    assert "#489" in policy
    assert "#490" in policy
    assert "#488" in policy


def test_ai_act_baseline_status_matches_capability_matrix() -> None:
    matrix = json.loads(
        (ROOT / "docs" / "capabilities" / "control-matrix.json").read_text(encoding="utf-8")
    )
    status = matrix["release_baseline"]["status"]
    compliance = (ROOT / "docs" / "AI_ACT_COMPLIANCE.md").read_text(encoding="utf-8")

    assert f"First-Release-Baseline hat den technischen Status `{status}`" in compliance


def _top_level_classes(path: Path, excluded: set[str] | None = None) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    excluded = excluded or set()
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name not in excluded
    }


def test_documented_runtime_inventory_matches_source() -> None:
    technical = (ROOT / "docs" / "README_technical.md").read_text(encoding="utf-8")
    ai_technical = (ROOT / "docs" / "AI_ACT_TECHNICAL_DOC.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "SAMUEL_ARCHITECTURE_V2.1.md").read_text(encoding="utf-8")
    design = (ROOT / "docs" / "SAMUEL_DESIGN_DECISIONS.md").read_text(encoding="utf-8")
    matrix = json.loads(
        (ROOT / "docs" / "capabilities" / "control-matrix.json").read_text(encoding="utf-8")
    )

    command_count = len(_top_level_classes(ROOT / "samuel" / "core" / "commands.py", {"Command"}))
    event_count = len(_top_level_classes(ROOT / "samuel" / "core" / "events.py", {"Event"}))
    port_count = len(_top_level_classes(ROOT / "samuel" / "core" / "ports.py"))
    slice_count = len(
        [
            path
            for path in (ROOT / "samuel" / "slices").iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        ]
    )
    adapter_group_count = len(
        [
            path
            for path in (ROOT / "samuel" / "adapters").iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        ]
    )
    core_module_count = len(list((ROOT / "samuel" / "core").glob("*.py")))
    gate_count = len(GATE_NAMES)

    assert f"Events ({event_count}) und Commands ({command_count})" in technical
    assert f"Die {port_count} Ports gesamt" in technical
    assert f"Slice-Katalog ({slice_count} Slices)" in technical
    assert f"({core_module_count} Python-Module einschließlich Paketmodul)" in ai_technical
    assert f"({slice_count} Slices)" in ai_technical
    assert f"({adapter_group_count} Adapter-Gruppen)" in ai_technical
    assert f"PR-Gates ({gate_count})" in technical
    assert "Contract-Scope Schema 2" in technical
    assert f"{gate_count} registrierte Prüfungen" in architecture
    assert "| **7b** |" in architecture
    assert "Teil A (E1–E19)" in design
    assert f"{len(matrix['controls'])} bestehende Mechanismen" in design
    assert "`data/workflow_runs/" not in technical
    assert "`data/eval_history/" not in technical
    assert "`data/checkpoints/" not in technical
    assert "`data/health.jsonl`" not in technical
    assert "`data/sequence/" not in technical
    assert "Session- und Implementation-Checkpoints" in technical
    assert "nur im Prozessspeicher" in technical
    assert "`--chat-workflow`-CLI-Flag existiert nicht" in technical
    assert "Im Bootstrap registrieren (Step 7)" in technical


def test_supported_runtime_invocations_use_installed_console_entrypoint() -> None:
    technical = (ROOT / "docs" / "README_technical.md").read_text(encoding="utf-8")
    install = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    service = (ROOT / "samuel.service").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    for document in (technical, install):
        assert "python -m samuel run" not in document
        assert 'SAMUEL_BUILD_VERSION="$(python -m samuel' not in document
    assert "python -m samuel" not in service
    assert "python -m samuel" not in dockerfile
    assert 'ENTRYPOINT ["samuel"]' in dockerfile


def test_contributor_commands_cover_repository_wide_ci_style_checks() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert ".venv/bin/python -m pytest tests/ samuel/ -q" in contributing
    assert ".venv/bin/ruff check ." in contributing
    assert ".venv/bin/ruff format --check ." in contributing


def test_compliance_docs_do_not_overstate_retention_or_transport_controls() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    compliance = (ROOT / "docs" / "AI_ACT_COMPLIANCE.md").read_text(encoding="utf-8")
    technical = (ROOT / "docs" / "AI_ACT_TECHNICAL_DOC.md").read_text(encoding="utf-8")
    vvt = (ROOT / "docs" / "DSGVO_VVT.md").read_text(encoding="utf-8")
    combined = "\n".join((readme, compliance, technical, vvt))

    assert "löscht sie aber nicht" in combined
    assert "altersbas" in combined
    assert "schreibende Requests CSRF-gebunden" in combined
    assert "kein eigener CSRF-Token" not in combined
    assert "Betreiber" in combined
    assert "Audit-Logs nach 365 Tagen geloescht" not in combined
    assert "Kein persistenter Speicher beim LLM-Provider" not in combined
    assert "HTTPS/TLS fuer alle API-Calls" not in combined
    assert "VVT-Generator" not in combined
    assert "Rechtssichere LLM-Nutzung" not in combined
    assert "keine autonome Aktion ohne Gate-Freigabe" not in combined


def test_versioning_keeps_revision_bound_release_evidence() -> None:
    policy = (ROOT / "docs" / "VERSIONING.md").read_text(encoding="utf-8")

    for evidence in (
        "84c909cbdb1e712a2ff2ba89ef09ac414c6c8099",
        "9f656f70af6cf24fc7a4119cd3db4439bbdf2a03",
        "Gitea-Run #496",
        "#538",
        "#539",
        "#540",
        "#541",
        "Gitea-Prerelease #9",
        "4bf59e5d23b45ff7d42337c5f9db87726997aa4dd0d096f6baf9ba8f74a3305d",
        "d97226f33d411c09f11d38c9736580739a12d88e1ae1143f052e34bbf0439db7",
        "offenen Issue #555",
    ):
        assert evidence in policy
