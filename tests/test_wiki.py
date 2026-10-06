from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tools import wiki

IDENTITY = {
    "head_sha": "a" * 40,
    "generated_at": "2026-08-29T00:00:00Z",
    "created_at": "2026-08-29T01:00:00Z",
    "document_contract_digest": "sha256:" + "b" * 64,
    "source_digest": "sha256:" + "c" * 64,
}


def _manifest() -> dict[str, Any]:
    return deepcopy(wiki._read_json(wiki.MANIFEST_PATH))


def _contract() -> dict[str, Any]:
    return deepcopy(wiki._read_json(wiki.DOCUMENT_CONTRACT_PATH))


def test_checked_in_wiki_impact_is_empty() -> None:
    assert wiki.wiki_impact() == []


def test_wiki_impact_maps_stale_source_section_to_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    block = manifest["pages"][0]["content_blocks"][0]
    expected = wiki._content_block_expected_digest(
        block,
        output_dir=manifest["output_dir"],
        page_path=manifest["pages"][0]["path"],
    )
    block["source_digest"] = "sha256:" + "0" * 64
    monkeypatch.setattr(wiki.control_matrix, "document_contract_impact", lambda _: [])

    impacts = wiki.wiki_impact(manifest=manifest, contract=_contract())

    assert impacts == [
        {
            "page_id": "wiki.home",
            "page_path": "index.md",
            "page_title": "Start und Systemüberblick",
            "relation": "content_block",
            "block_id": "wiki.home.product-purpose",
            "block_type": "source_section",
            "source": "README.md",
            "declared_source_digest": "sha256:" + "0" * 64,
            "reason": "source_binding_changed",
            "expected_source_digest": expected,
        }
    ]


def test_wiki_impact_maps_stale_resolved_fact_to_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    block = next(
        item
        for item in manifest["pages"][0]["content_blocks"]
        if item["id"] == "wiki.home.runtime-inventory"
    )
    block["source_digest"] = "sha256:" + "0" * 64
    monkeypatch.setattr(wiki.control_matrix, "document_contract_impact", lambda _: [])

    impacts = wiki.wiki_impact(manifest=manifest, contract=_contract())

    assert len(impacts) == 1
    assert impacts[0]["page_id"] == "wiki.home"
    assert impacts[0]["block_id"] == "wiki.home.runtime-inventory"
    assert impacts[0]["block_type"] == "resolved_fact"
    assert impacts[0]["reason"] == "source_binding_changed"
    assert impacts[0]["expected_source_digest"].startswith("sha256:")


def test_wiki_impact_maps_document_contract_section_to_primary_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wiki.control_matrix,
        "document_contract_impact",
        lambda _: [
            {
                "section": "technical-runtime",
                "document": "docs/README_technical.md",
                "mode": "manual",
                "reason": "source_binding_changed",
                "sources": ["tools/wiki.py"],
                "proofs": ["tests/test_wiki.py"],
                "expected_source_digest": "sha256:" + "d" * 64,
            }
        ],
    )

    impacts = wiki.wiki_impact(manifest=_manifest(), contract=_contract())

    assert impacts == [
        {
            "page_id": "wiki.components",
            "page_path": "components.md",
            "page_title": "Komponentenreferenz",
            "relation": "document_contract_section",
            "section": "technical-runtime",
            "document": "docs/README_technical.md",
            "reason": "source_binding_changed",
            "sources": ["tools/wiki.py"],
            "proofs": ["tests/test_wiki.py"],
            "expected_source_digest": "sha256:" + "d" * 64,
        }
    ]


def test_wiki_impact_keeps_unresolvable_binding_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    block = manifest["pages"][0]["content_blocks"][0]
    block["selector"] = {"heading": "Missing impact heading"}
    before = deepcopy(manifest)
    monkeypatch.setattr(wiki.control_matrix, "document_contract_impact", lambda _: [])

    impacts = wiki.wiki_impact(manifest=manifest, contract=_contract())

    assert manifest == before
    assert len(impacts) == 1
    assert impacts[0]["page_id"] == "wiki.home"
    assert impacts[0]["block_id"] == "wiki.home.product-purpose"
    assert impacts[0]["reason"] == "binding_unresolvable"
    assert "Missing impact heading" in impacts[0]["detail"]


def test_impact_cli_is_read_only_and_does_not_require_clean_repository(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("impact must not inspect identity or write a bundle")

    monkeypatch.setattr(sys, "argv", ["wiki.py", "impact"])
    monkeypatch.setattr(wiki, "repository_identity", unexpected)
    monkeypatch.setattr(wiki, "_write_bundle", unexpected)

    assert wiki.main() == 0
    assert json.loads(capsys.readouterr().out) == []


def test_checked_in_manifest_covers_contract_and_renders_useful_pages() -> None:
    manifest = _manifest()
    contract = _contract()

    classified = wiki.validate_manifest(manifest, contract)
    pages, receipt = wiki.build_bundle(
        manifest=manifest,
        contract=contract,
        identity=IDENTITY,
    )

    assert tuple(page["id"] for page in manifest["pages"]) == wiki.EXPECTED_PAGE_IDS
    assert len(classified) == len(contract["documents"])
    assert set(pages) == {
        "index.md",
        "architecture.md",
        "pipeline.md",
        "components.md",
        "assurance.md",
        "configuration.md",
        "operations.md",
        "security.md",
        "decisions.md",
        "document-status.md",
    }
    home = pages["index.md"].decode("utf-8")
    assert "## Wege nach Aufgabe" in home
    assert "**Developer:**" in home
    assert f"**{len(contract['documents'])} aktive Dokumente**" in home
    assert "## Kerninhalt" in home
    assert "## Gebundene Quellen und Vertiefung" in home
    assert "Entwicklerteams beschreiben Aufgaben in Issues" in home
    assert "Wer hat diese Änderung geschrieben?" in home
    assert "**Klasse:** Zielarchitektur" in home
    assert "### Laufzeitinventar" in home
    assert "PIPELINE 3:  PR-GATES (einzige Freigabeautorität)" in home
    assert "**Klasse:** Runtime-Referenz" in home
    assert "[`README.md`](../README.md)" in home
    assert len(receipt["page_manifest"]) == 10
    assert all(item["content_block_count"] >= 1 for item in receipt["page_manifest"])
    assert receipt["findings"] == []

    inventory = pages["document-status.md"].decode("utf-8")
    assert "## Vollständiges aktives Dokumentinventar" in inventory
    assert all(f"[`{item['path']}`]" in inventory for item in contract["documents"])

    architecture = pages["architecture.md"].decode("utf-8")
    assert "Runtime-Referenz" in architecture
    assert "Zielarchitektur" in architecture
    assert "Event Bus (Mediator)" in architecture
    assert "### 13. Security-Model" in architecture
    assert "Nicht-Ziele (bewusst ausgeklammert)" in architecture

    pipeline = pages["pipeline.md"].decode("utf-8")
    assert "GateEvaluationUnavailable" in pipeline
    assert "ScoreObserved ohne Workflowkante" in pipeline

    assurance = pages["assurance.md"].decode("utf-8")
    assert "`EvaluationSubject` aus Repository" in assurance
    assert "vollständigem Base-/Head-SHA" in assurance
    assert "### Ausgelieferte Gate-Profile" in assurance

    configuration = pages["configuration.md"].decode("utf-8")
    assert "Effektive Provider-Prioritaet fuer einen Task" in configuration

    components = pages["components.md"].decode("utf-8")
    assert "### 7. Adapter-Katalog" in components
    assert "#### Ports im Detail" in components

    operations = pages["operations.md"].decode("utf-8")
    assert "### 12. Update / Troubleshooting / Deinstallation" in operations
    assert "| Workflow-Label | `public-runner-example` |" in operations
    assert "### 15. Persistenz" in operations

    security = pages["security.md"].decode("utf-8")
    assert "Advisory prompt-injection signal" in security
    assert "not a process, filesystem or network sandbox" in security

    decisions = pages["decisions.md"].decode("utf-8")
    assert "`ADR-0649`" in decisions

    document_status = pages["document-status.md"].decode("utf-8")
    assert "## Gebundener Buildstatus" in document_status
    assert (
        f"`{len(contract['documents'])}/{len(contract['documents'])}` aktive Dokumente"
        in document_status
    )
    assert "Seiten mit `" in document_status
    assert "ohne Finding validiert" in document_status

    assert all("## Kerninhalt" in content.decode("utf-8") for content in pages.values())
    assert all(
        any(
            str(block["id"]) in pages[str(page["path"])].decode("utf-8")
            for block in page["content_blocks"]
        )
        for page in manifest["pages"]
    )


def test_wall_clock_changes_only_receipt_created_at() -> None:
    first_pages, first = wiki.build_bundle(identity=IDENTITY)
    second_pages, second = wiki.build_bundle(
        identity={**IDENTITY, "created_at": "2099-12-31T23:59:59Z"}
    )

    assert first_pages == second_pages
    assert first["artifact_digest"] == second["artifact_digest"]
    assert first["created_at"] != second["created_at"]
    assert {key: value for key, value in first.items() if key != "created_at"} == {
        key: value for key, value in second.items() if key != "created_at"
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["pages"][0].update(id="wiki.changed"), "stable page order"),
        (lambda value: value["pages"].reverse(), "stable page order"),
        (lambda value: value["pages"][0].update(path="../escape.md"), "unsafe relative path"),
        (
            lambda value: value["pages"][1].update(publication_path="Home.md"),
            "duplicate wiki publication path",
        ),
        (
            lambda value: value["pages"][1]["sources"].append("README.md"),
            "assigned more than once",
        ),
        (lambda value: value["pages"][0]["sources"].pop(), "wiki coverage drift"),
        (
            lambda value: value["pages"][0]["sources"].__setitem__(0, "docs/missing.md"),
            "source does not exist",
        ),
        (
            lambda value: value["pages"][0]["content_blocks"][0].update(id=""),
            "invalid content block id",
        ),
        (
            lambda value: value["pages"][0]["content_blocks"][1].update(
                id=value["pages"][0]["content_blocks"][0]["id"]
            ),
            "duplicate content block id",
        ),
        (
            lambda value: value["pages"][0]["content_blocks"][0].update(
                source="docs/missing-content-source.md"
            ),
            "source is not an active document",
        ),
        (
            lambda value: value["pages"][0]["content_blocks"][0]["selector"].update(
                heading="Missing heading"
            ),
            "source_section heading is missing",
        ),
        (
            lambda value: value["pages"][0]["content_blocks"][0].update(
                source_digest="sha256:" + "0" * 64
            ),
            "stale source_digest",
        ),
        (
            lambda value: value["pages"][0]["content_blocks"][0].update(
                document_class="operations"
            ),
            "document_class mismatch",
        ),
    ],
)
def test_manifest_mutations_fail_closed(
    mutation: Callable[[dict[str, Any]], None], message: str
) -> None:
    manifest = _manifest()
    assert callable(mutation)
    mutation(manifest)

    with pytest.raises(wiki.WikiError, match=message):
        wiki.validate_manifest(manifest, _contract())


def test_artifact_digest_binds_page_identity_path_and_exact_bytes() -> None:
    manifest = _manifest()
    pages, receipt = wiki.build_bundle(manifest=manifest, identity=IDENTITY)
    reversed_mapping = dict(reversed(list(pages.items())))
    changed = dict(pages)
    changed["index.md"] += b"\nchanged\n"

    assert wiki._artifact_digest(manifest["pages"], reversed_mapping) == receipt["artifact_digest"]
    assert wiki._artifact_digest(manifest["pages"], changed) != receipt["artifact_digest"]

    changed_manifest = deepcopy(manifest)
    changed_manifest["pages"][0]["path"] = "home.md"
    changed_outputs = {
        "home.md": pages["index.md"],
        **{k: v for k, v in pages.items() if k != "index.md"},
    }
    assert (
        wiki._artifact_digest(changed_manifest["pages"], changed_outputs)
        != receipt["artifact_digest"]
    )


def test_bundle_writer_emits_only_pages_and_required_receipt(tmp_path: Path) -> None:
    pages, receipt = wiki.build_bundle(identity=IDENTITY)
    output = tmp_path / "wiki"

    wiki._write_bundle(output, pages, receipt)

    assert {
        path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()
    } == {
        *pages,
        "build-receipt.json",
    }
    written = json.loads((output / "build-receipt.json").read_text(encoding="utf-8"))
    assert set(written) == {
        "repository",
        "head_sha",
        "document_contract_digest",
        "source_digest",
        "generator_version",
        "artifact_digest",
        "page_manifest",
        "findings",
        "created_at",
    }

    (output / "obsolete.md").write_text("old\n", encoding="utf-8")
    wiki._write_bundle(output, pages, receipt)
    assert not (output / "obsolete.md").exists()
    assert not list(tmp_path.glob(".wiki-build-*"))
    assert not list(tmp_path.glob(".wiki-previous-*"))


def test_bundle_writer_rejects_symlink_output(tmp_path: Path) -> None:
    pages, receipt = wiki.build_bundle(identity=IDENTITY)
    outside = tmp_path / "outside"
    outside.mkdir()
    output = tmp_path / "wiki"
    output.symlink_to(outside, target_is_directory=True)

    with pytest.raises(wiki.WikiError, match="real directory path"):
        wiki._write_bundle(output, pages, receipt)

    assert not list(outside.iterdir())


def test_generated_links_resolve_to_page_or_repository_source() -> None:
    pages, _ = wiki.build_bundle(identity=IDENTITY)
    links = re.compile(r"\[[^]]+\]\(([^)]+)\)")

    for page_path, content in pages.items():
        for target in links.findall(content.decode("utf-8")):
            clean = target.split("#", 1)[0].replace("%20", " ")
            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", clean):
                continue
            if clean.startswith("../"):
                resolved = (wiki.ROOT / "wiki" / page_path).parent / clean
                assert resolved.resolve().is_file()
            else:
                assert clean in pages


def test_source_links_follow_output_and_nested_page_paths() -> None:
    assert (
        wiki._source_link(
            "docs/README_technical.md",
            output_dir="wiki",
            page_path="nested/components.md",
        )
        == "../../docs/README_technical.md"
    )
    assert (
        wiki._source_link(
            "technische Beschreibungen/README.md",
            output_dir="wiki",
            page_path="pipeline.md",
            anchor="A B",
        )
        == "../technische%20Beschreibungen/README.md#A%20B"
    )


def test_materialized_check_detects_missing_modified_and_extra_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest()
    pages = {"index.md": b"bound page\n"}
    receipt = {
        "repository": manifest["repository"],
        "head_sha": IDENTITY["head_sha"],
        "document_contract_digest": IDENTITY["document_contract_digest"],
        "source_digest": IDENTITY["source_digest"],
        "generator_version": manifest["generator_version"],
        "artifact_digest": "sha256:" + "d" * 64,
        "page_manifest": [],
        "findings": [],
        "created_at": IDENTITY["created_at"],
    }
    manifest_path = tmp_path / wiki.MANIFEST_PATH.relative_to(wiki.ROOT)
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(wiki, "repository_identity", lambda **_: IDENTITY)
    monkeypatch.setattr(wiki, "build_bundle", lambda **_: (pages, receipt))

    with pytest.raises(wiki.WikiError, match="materialized wiki is missing"):
        wiki.check_materialized(root=tmp_path)

    output = tmp_path / "wiki"
    wiki._write_bundle(output, pages, receipt)
    assert wiki.check_materialized(root=tmp_path) == receipt

    (output / "index.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(wiki.WikiError, match="stale or modified"):
        wiki.check_materialized(root=tmp_path)

    wiki._write_bundle(output, pages, receipt)
    (output / "extra.md").write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(wiki.WikiError, match="file set differs"):
        wiki.check_materialized(root=tmp_path)


def test_source_installer_materializes_wiki_after_package_install(tmp_path: Path) -> None:
    installer = tmp_path / "install.sh"
    shutil.copy2(wiki.ROOT / "install.sh", installer)
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "activate").write_text("", encoding="utf-8")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        'if [ "${1:-}" = "tools/wiki.py" ] && [ "${2:-}" = "build" ]; then\n'
        "  mkdir -p wiki\n"
        "  printf 'materialized\\n' > wiki/index.md\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_pip = fake_bin / "pip"
    fake_pip.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_pip.chmod(0o755)

    completed = subprocess.run(  # noqa: S603 - isolated copied installer and fake PATH
        [str(installer)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PYTHON": str(fake_python),
            "SCM_URL": "",
            "SCM_TOKEN": "",
            "SCM_REPO": "",
            "SAMUEL_SETUP": "",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8") == "materialized\n"
    assert (
        completed.stdout.index("Installiere Paket")
        < completed.stdout.index("Erzeuge lokales Entwickler-Wiki")
        < completed.stdout.index("Installation fertig")
    )


def test_heading_projection_ignores_fences_and_keeps_duplicate_anchors() -> None:
    headings = wiki._headings(
        "# Title\n## Repeat\n```md\n## Not a heading\n```\n## Repeat\n### Details!\n"
    )

    assert headings == [
        (1, "Title", "title"),
        (2, "Repeat", "repeat"),
        (2, "Repeat", "repeat-1"),
        (3, "Details!", "details"),
    ]


def test_source_section_rewrites_links_and_preserves_markdown(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text("# Target\n\nBound target.\n", encoding="utf-8")
    (docs / "source.md").write_text(
        "# Document\n"
        "\n"
        "## Selected\n"
        "\n"
        "[Local](target.md#target) and [outside](#outside).\n"
        "\n"
        "### Child\n"
        "\n"
        "| A | B |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
        "\n"
        "~~~md\n"
        "## Not a heading\n"
        "[Not parsed](missing.md)\n"
        "~~~\n"
        "\n"
        "## Outside\n"
        "\n"
        "Not selected.\n",
        encoding="utf-8",
    )
    block = {
        "id": "wiki.architecture.selected",
        "source": "docs/source.md",
        "document_class": "runtime_reference",
        "selector": {"heading": "Selected"},
    }

    rendered = "\n".join(
        wiki._render_source_section(
            block,
            output_dir="wiki",
            page_path="architecture.md",
            root=tmp_path,
        )
    )

    assert "### Selected" in rendered
    assert "#### Child" in rendered
    assert "| 1 | 2 |" in rendered
    assert "~~~md\n## Not a heading\n[Not parsed](missing.md)\n~~~" in rendered
    assert "[Local](../docs/target.md#target)" in rendered
    assert "[outside](../docs/source.md#outside)" in rendered


def test_source_section_rejects_ambiguous_heading() -> None:
    with pytest.raises(wiki.WikiError, match="ambiguous"):
        wiki._source_section("# Document\n\n## Same\n\nA\n\n## Same\n\nB\n", "Same")


@pytest.mark.parametrize("target", ["missing.md", "target.md#missing-anchor", "../../escape.md"])
def test_source_section_rejects_unresolvable_local_link(tmp_path: Path, target: str) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "target.md").write_text("# Target\n", encoding="utf-8")
    (docs / "source.md").write_text(
        f"# Document\n\n## Selected\n\n[Broken]({target}).\n",
        encoding="utf-8",
    )
    block = {
        "id": "wiki.architecture.selected",
        "source": "docs/source.md",
        "document_class": "runtime_reference",
        "selector": {"heading": "Selected"},
    }

    with pytest.raises(wiki.WikiError, match="missing|escapes repository"):
        wiki._render_source_section(
            block,
            output_dir="wiki",
            page_path="architecture.md",
            root=tmp_path,
        )


def test_resolved_fact_change_requires_new_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    original = wiki.control_matrix._runtime_inventory_truth()
    monkeypatch.setattr(
        wiki.control_matrix,
        "_runtime_inventory_truth",
        lambda: {**original, "commands": original["commands"] + 1},
    )

    with pytest.raises(wiki.WikiError, match="runtime-inventory.*stale source_digest"):
        wiki.validate_manifest(manifest, _contract())
