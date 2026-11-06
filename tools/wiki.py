#!/usr/bin/env python3
"""Build the deterministic, non-authoritative S.A.M.U.E.L. developer wiki."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
control_matrix = importlib.import_module("tools.control_matrix")

MANIFEST_PATH = ROOT / "docs" / "capabilities" / "wiki-manifest.json"
DOCUMENT_CONTRACT_PATH = ROOT / "docs" / "capabilities" / "document-contract.json"
MATRIX_PATH = ROOT / "docs" / "capabilities" / "control-matrix.json"

EXPECTED_PAGE_IDS = (
    "wiki.home",
    "wiki.architecture",
    "wiki.pipeline",
    "wiki.components",
    "wiki.assurance",
    "wiki.configuration",
    "wiki.operations",
    "wiki.security",
    "wiki.decisions",
    "wiki.document-status",
)
EXPECTED_PERSONAS = ("developer", "maintainer", "operator", "reviewer")
CLASS_LABELS = {
    "runtime_reference": "Runtime-Referenz",
    "adr": "ADR / Entscheidung",
    "operations": "Betrieb",
    "target_architecture": "Zielarchitektur",
    "history": "Historie",
}
MODE_LABELS = {"generated": "deterministisch generiert", "manual": "manuell gepflegt"}
CONTENT_BLOCK_TYPES = {"source_section", "resolved_fact"}
CONTENT_BLOCK_ID = re.compile(r"^wiki\.[a-z0-9-]+\.[a-z0-9-]+$")
MARKDOWN_LINK_RE = re.compile(r"(!?\[[^]]+\]\()([^)]+)(\))")
TICK = chr(96)
FACT_RESOLVERS = {
    "runtime_inventory": {
        "source": "tools/control_matrix.py::_runtime_inventory_truth",
        "document_class": "runtime_reference",
    },
    "workflow_steps": {
        "source": "tools/control_matrix.py::_workflow_steps_truth",
        "document_class": "runtime_reference",
    },
    "gate_profiles": {
        "source": "tools/control_matrix.py::_gate_truth+_threshold_truth",
        "document_class": "runtime_reference",
    },
    "policy_thresholds": {
        "source": "tools/control_matrix.py::_threshold_truth",
        "document_class": "runtime_reference",
    },
}


class WikiError(ValueError):
    """Raised when the wiki projection cannot be bound deterministically."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WikiError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WikiError(f"{path} must contain a JSON object")
    return value


def _digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _fact_payload(name: str) -> Any:
    """Resolve a bounded wiki fact through the existing governance resolvers."""

    if name == "runtime_inventory":
        return control_matrix._runtime_inventory_truth()
    if name == "workflow_steps":
        return control_matrix._workflow_steps_truth()
    if name == "gate_profiles":
        gate_ids, gate_names = control_matrix._gate_truth()
        profiles = control_matrix._threshold_truth()["shipped_gate_profiles"]
        return {
            "gates": [
                {"id": gate_id, "name": gate_names[gate_id]}
                for gate_id in sorted(gate_ids, key=control_matrix._gate_sort_key)
            ],
            "profiles": profiles,
        }
    if name == "policy_thresholds":
        thresholds = control_matrix._threshold_truth()
        return {
            "code_defaults": thresholds["code_defaults"],
            "shipped_eval": thresholds["shipped_eval"],
        }
    raise WikiError(f"unknown resolved_fact selector: {name}")


def _fact_digest(value: Any) -> str:
    return _digest(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _content_block_expected_digest(
    block: dict[str, Any],
    *,
    output_dir: str,
    page_path: str,
    root: Path = ROOT,
) -> str:
    """Resolve one existing content-block binding without changing it."""

    block_type = str(block.get("type", ""))
    if block_type == "source_section":
        content_source = _safe_relative_path(block.get("source"), suffix=".md")
        selector = block.get("selector")
        if (
            not isinstance(selector, dict)
            or set(selector) != {"heading"}
            or not str(selector.get("heading", "")).strip()
        ):
            raise WikiError("source_section requires exact heading selector")
        source_text = (root / content_source).read_text(encoding="utf-8")
        section, _, _ = _source_section(source_text, str(selector["heading"]))
        _render_source_section(
            block,
            output_dir=output_dir,
            page_path=page_path,
            root=root,
        )
        return _digest(section.encode("utf-8"))
    if block_type == "resolved_fact":
        selector = str(block.get("selector", ""))
        if selector not in FACT_RESOLVERS:
            raise WikiError(f"unknown resolved_fact selector: {selector}")
        return _fact_digest(_fact_payload(selector))
    raise WikiError(f"unknown content block type: {block_type}")


def wiki_impact(
    manifest: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    *,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    """Return read-only review impacts for existing page and block bindings."""

    manifest = manifest or _read_json(root / MANIFEST_PATH.relative_to(ROOT))
    contract = contract or _read_json(root / DOCUMENT_CONTRACT_PATH.relative_to(ROOT))
    pages = manifest.get("pages", [])
    if not isinstance(pages, list):
        raise WikiError("wiki manifest pages must be a list")

    page_by_source: dict[str, dict[str, str]] = {}
    impacts: list[dict[str, Any]] = []
    output_dir = str(manifest.get("output_dir", ""))

    for page in pages:
        if not isinstance(page, dict):
            continue
        metadata = {
            "page_id": str(page.get("id", "")),
            "page_path": str(page.get("path", "")),
            "page_title": str(page.get("title", "")),
        }
        sources = page.get("sources", [])
        if isinstance(sources, list):
            for source in sources:
                page_by_source[str(source)] = metadata

        blocks = page.get("content_blocks", [])
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            base = {
                **metadata,
                "relation": "content_block",
                "block_id": str(block.get("id", "")),
                "block_type": str(block.get("type", "")),
                "source": str(block.get("source", "")),
                "declared_source_digest": str(block.get("source_digest", "")),
            }
            try:
                expected = _content_block_expected_digest(
                    block,
                    output_dir=output_dir,
                    page_path=metadata["page_path"],
                    root=root,
                )
            except (OSError, UnicodeError, WikiError, KeyError, TypeError, ValueError) as exc:
                impacts.append(
                    {
                        **base,
                        "reason": "binding_unresolvable",
                        "detail": str(exc),
                    }
                )
                continue
            if base["declared_source_digest"] != expected:
                impacts.append(
                    {
                        **base,
                        "reason": "source_binding_changed",
                        "expected_source_digest": expected,
                    }
                )

    for item in control_matrix.document_contract_impact(contract):
        document = str(item.get("document", ""))
        primary_metadata = page_by_source.get(document)
        if primary_metadata is None:
            impacts.append(
                {
                    "page_id": "",
                    "page_path": "",
                    "page_title": "",
                    "relation": "document_contract_section",
                    "section": str(item.get("section", "")),
                    "document": document,
                    "reason": "primary_page_unresolved",
                    "detail": str(item.get("reason", "")),
                }
            )
            continue
        impacts.append(
            {
                **primary_metadata,
                "relation": "document_contract_section",
                "section": str(item.get("section", "")),
                "document": document,
                "reason": str(item.get("reason", "")),
                "sources": item.get("sources", []),
                "proofs": item.get("proofs", []),
                **(
                    {"expected_source_digest": item["expected_source_digest"]}
                    if "expected_source_digest" in item
                    else {}
                ),
            }
        )

    return sorted(
        impacts,
        key=lambda item: (
            str(item.get("page_id", "")),
            str(item.get("relation", "")),
            str(item.get("block_id", item.get("section", ""))),
        ),
    )


def _safe_relative_path(value: object, *, suffix: str | None = None) -> str:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or path.as_posix() != text:
        raise WikiError(f"unsafe relative path: {text!r}")
    if suffix is not None and path.suffix != suffix:
        raise WikiError(f"path must end in {suffix}: {text!r}")
    return text


def validate_manifest(
    manifest: dict[str, Any], contract: dict[str, Any], *, root: Path = ROOT
) -> dict[str, dict[str, str]]:
    """Validate stable page identity and exact primary-source coverage."""

    errors: list[str] = []
    if manifest.get("schema_version") != "1.1":
        errors.append("wiki manifest schema_version must be 1.1")
    if manifest.get("generator_version") != "1.1":
        errors.append("wiki manifest generator_version must be 1.1")
    if manifest.get("authority") != "non_authoritative_projection":
        errors.append("wiki manifest authority must be non_authoritative_projection")
    if manifest.get("output_dir") != "wiki":
        errors.append("wiki manifest output_dir must be wiki")
    if not str(manifest.get("repository", "")).strip():
        errors.append("wiki manifest repository is required")

    documents = contract.get("documents", [])
    if not isinstance(documents, list):
        raise WikiError("document contract documents must be a list")
    classified: dict[str, dict[str, str]] = {}
    for item in documents:
        if not isinstance(item, dict):
            errors.append("document classifications must be objects")
            continue
        path = str(item.get("path", ""))
        if not path or path in classified:
            errors.append(f"duplicate or empty document path: {path!r}")
            continue
        classified[path] = {
            "class": str(item.get("class", "")),
            "mode": str(item.get("mode", "")),
        }

    pages = manifest.get("pages", [])
    if not isinstance(pages, list):
        raise WikiError("wiki manifest pages must be a list")
    page_ids = tuple(str(page.get("id", "")) for page in pages if isinstance(page, dict))
    if page_ids != EXPECTED_PAGE_IDS:
        errors.append(f"stable page order must be {list(EXPECTED_PAGE_IDS)}, got {list(page_ids)}")

    target_paths: set[str] = set()
    publication_paths: set[str] = set()
    assigned: list[str] = []
    block_ids: set[str] = set()
    known_page_ids = set(page_ids)
    for page in pages:
        if not isinstance(page, dict):
            errors.append("wiki pages must be objects")
            continue
        page_id = str(page.get("id", ""))
        try:
            target = _safe_relative_path(page.get("path"), suffix=".md")
        except WikiError as exc:
            errors.append(f"{page_id or '?'}: {exc}")
            target = ""
        if target in target_paths:
            errors.append(f"duplicate wiki target path: {target!r}")
        elif target:
            target_paths.add(target)
        try:
            publication_target = _safe_relative_path(page.get("publication_path"), suffix=".md")
        except WikiError as exc:
            errors.append(f"{page_id or '?'} publication: {exc}")
            publication_target = ""
        if publication_target in publication_paths:
            errors.append(f"duplicate wiki publication path: {publication_target!r}")
        elif publication_target:
            publication_paths.add(publication_target)
        if not str(page.get("title", "")).strip():
            errors.append(f"{page_id}: title is required")
        if not str(page.get("purpose", "")).strip():
            errors.append(f"{page_id}: purpose is required")
        audiences = page.get("audiences", [])
        if not isinstance(audiences, list) or not audiences:
            errors.append(f"{page_id}: audiences are required")
        elif any(str(item) not in EXPECTED_PERSONAS for item in audiences):
            errors.append(f"{page_id}: unknown audience")
        related = page.get("related_pages", [])
        if not isinstance(related, list):
            errors.append(f"{page_id}: related_pages must be a list")
        elif any(str(item) not in known_page_ids for item in related):
            errors.append(f"{page_id}: related page is unknown")
        sources = page.get("sources", [])
        if not isinstance(sources, list) or not sources:
            errors.append(f"{page_id}: at least one primary source is required")
            continue
        for source in sources:
            try:
                source_path = _safe_relative_path(source, suffix=".md")
            except WikiError as exc:
                errors.append(f"{page_id}: {exc}")
                continue
            assigned.append(source_path)
            resolved = (root / source_path).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                errors.append(f"{page_id}: source escapes repository: {source_path}")
                continue
            if not resolved.is_file():
                errors.append(f"{page_id}: source does not exist: {source_path}")
        blocks = page.get("content_blocks", [])
        if not isinstance(blocks, list) or not blocks:
            errors.append(f"{page_id}: at least one content block is required")
            continue
        for block in blocks:
            if not isinstance(block, dict):
                errors.append(f"{page_id}: content blocks must be objects")
                continue
            block_id = str(block.get("id", ""))
            if not CONTENT_BLOCK_ID.fullmatch(block_id) or not block_id.startswith(page_id + "."):
                errors.append(f"{page_id}: invalid content block id: {block_id!r}")
            elif block_id in block_ids:
                errors.append(f"duplicate content block id: {block_id}")
            else:
                block_ids.add(block_id)
            block_type = str(block.get("type", ""))
            if block_type not in CONTENT_BLOCK_TYPES:
                errors.append(f"{block_id or page_id}: unknown content block type")
                continue
            document_class = str(block.get("document_class", ""))
            if document_class not in CLASS_LABELS:
                errors.append(f"{block_id}: invalid document_class")
            declared_digest = str(block.get("source_digest", ""))
            if re.fullmatch(r"sha256:[0-9a-f]{64}", declared_digest) is None:
                errors.append(f"{block_id}: source_digest must be sha256")
            if block_type == "source_section":
                try:
                    content_source = _safe_relative_path(block.get("source"), suffix=".md")
                except WikiError as exc:
                    errors.append(f"{block_id}: {exc}")
                    continue
                metadata = classified.get(content_source)
                if metadata is None:
                    errors.append(f"{block_id}: source is not an active document: {content_source}")
                    continue
                if metadata["class"] != document_class:
                    errors.append(
                        f"{block_id}: document_class mismatch; expected {metadata['class']}"
                    )
                selector = block.get("selector")
                if (
                    not isinstance(selector, dict)
                    or set(selector) != {"heading"}
                    or not str(selector.get("heading", "")).strip()
                ):
                    errors.append(f"{block_id}: source_section requires exact heading selector")
                    continue
                try:
                    actual_digest = _content_block_expected_digest(
                        block,
                        output_dir=str(manifest.get("output_dir", "")),
                        page_path=target,
                        root=root,
                    )
                    if actual_digest != declared_digest:
                        errors.append(f"{block_id}: stale source_digest; expected {actual_digest}")
                except (OSError, UnicodeError, WikiError) as exc:
                    errors.append(f"{block_id}: {exc}")
            else:
                selector = str(block.get("selector", ""))
                resolver = FACT_RESOLVERS.get(selector)
                if resolver is None:
                    errors.append(f"{block_id}: unknown resolved_fact selector: {selector}")
                    continue
                if str(block.get("source", "")) != resolver["source"]:
                    errors.append(f"{block_id}: resolved_fact source must be {resolver['source']}")
                if document_class != resolver["document_class"]:
                    errors.append(
                        f"{block_id}: document_class must be {resolver['document_class']}"
                    )
                try:
                    actual_digest = _content_block_expected_digest(
                        block,
                        output_dir=str(manifest.get("output_dir", "")),
                        page_path=target,
                        root=root,
                    )
                    if actual_digest != declared_digest:
                        errors.append(f"{block_id}: stale source_digest; expected {actual_digest}")
                except (KeyError, TypeError, ValueError, control_matrix.MatrixError) as exc:
                    errors.append(f"{block_id}: cannot resolve fact: {exc}")

    assigned_set = set(assigned)
    duplicates = sorted(path for path in assigned_set if assigned.count(path) != 1)
    if duplicates:
        errors.append(f"documents assigned more than once: {duplicates}")
    if assigned_set != set(classified):
        errors.append(
            "wiki coverage drift: "
            f"missing={sorted(set(classified) - assigned_set)}, "
            f"extra={sorted(assigned_set - set(classified))}"
        )

    personas = manifest.get("personas", {})
    if not isinstance(personas, dict) or tuple(personas) != EXPECTED_PERSONAS:
        errors.append(f"personas must be ordered as {list(EXPECTED_PERSONAS)}")
    else:
        for persona, route in personas.items():
            if not isinstance(route, list) or not route:
                errors.append(f"persona route must be non-empty: {persona}")
            elif any(str(page_id) not in known_page_ids for page_id in route):
                errors.append(f"persona route references unknown page: {persona}")

    if errors:
        raise WikiError("\n".join(f"- {error}" for error in errors))
    return classified


def _heading_entries(text: str) -> list[tuple[int, int, str, str]]:
    """Extract line, level, title, and GitHub-style anchor outside code fences."""

    headings: list[tuple[int, int, str, str]] = []
    counts: dict[str, int] = {}
    fence_char = ""
    fence_length = 0
    for line_number, line in enumerate(text.splitlines()):
        if fence_char:
            closing = re.match(rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_length},}}\s*$", line)
            if closing is not None:
                fence_char = ""
                fence_length = 0
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if opening is not None:
            marker = opening.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match is None:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(2))
        title = re.sub(r"[`*~]", "", title).strip()
        slug = re.sub(r"[^\w\- ]", "", title.lower(), flags=re.UNICODE)
        slug = re.sub(r"\s", "-", slug).strip("-")
        occurrence = counts.get(slug, 0)
        counts[slug] = occurrence + 1
        anchor = f"{slug}-{occurrence}" if occurrence else slug
        headings.append((line_number, len(match.group(1)), title, anchor))
    return headings


def _headings(text: str) -> list[tuple[int, str, str]]:
    """Extract GitHub-style heading anchors without parsing code fences."""

    return [(level, title, anchor) for _, level, title, anchor in _heading_entries(text)]


def _source_section(text: str, heading: str) -> tuple[str, int, set[str]]:
    entries = _heading_entries(text)
    matches = [entry for entry in entries if entry[2] == heading]
    if not matches:
        raise WikiError(f"source_section heading is missing: {heading!r}")
    if len(matches) != 1:
        raise WikiError(f"source_section heading is ambiguous: {heading!r}")
    start, level, _, _ = matches[0]
    end = len(text.splitlines())
    for line_number, candidate_level, _, _ in entries:
        if line_number > start and candidate_level <= level:
            end = line_number
            break
    lines = text.splitlines()[start:end]
    section = "\n".join(lines).rstrip() + "\n"
    anchors = {anchor for line_number, _, _, anchor in entries if start <= line_number < end}
    return section, level, anchors


def _relative_link(*, from_page: str, target: str) -> str:
    start = PurePosixPath(from_page).parent.as_posix()
    relative = posixpath.relpath(target, start=start)
    return quote(relative, safe="/")


def _source_link(
    path: str,
    *,
    output_dir: str,
    page_path: str,
    anchor: str = "",
) -> str:
    source_target = (PurePosixPath(output_dir) / page_path).parent
    target = posixpath.relpath(path, start=source_target.as_posix())
    target = quote(target, safe="/")
    return f"{target}#{quote(anchor)}" if anchor else target


def _render_source(
    path: str,
    metadata: dict[str, str],
    *,
    output_dir: str,
    page_path: str,
    root: Path,
) -> list[str]:
    text = (root / path).read_text(encoding="utf-8")
    headings = _headings(text)
    title = headings[0][1] if headings else PurePosixPath(path).name
    lines = [
        f"### {title}",
        "",
        f"- **Quelle:** [`{path}`]("
        f"{_source_link(path, output_dir=output_dir, page_path=page_path)})",
        f"- **Klasse:** {CLASS_LABELS.get(metadata['class'], metadata['class'])}",
        f"- **Pflegemodus:** {MODE_LABELS.get(metadata['mode'], metadata['mode'])}",
        "- **Rolle:** primäre Quelle dieser Wiki-Projektion; die Wiki-Seite ist nicht autoritativ",
        "",
        "**Inhaltsweg:**",
        "",
    ]
    major_headings = [item for item in headings if item[0] == 2]
    outline = major_headings if major_headings else [item for item in headings if item[0] > 2][:12]
    if not outline:
        lines.append("- Kein weiterführender Markdown-Abschnitt ausgewiesen.")
    else:
        for level, heading, anchor in outline:
            indent = "  " * max(0, level - 2)
            lines.append(
                f"{indent}- [{heading}]("
                f"{_source_link(path, output_dir=output_dir, page_path=page_path, anchor=anchor)})"
            )
    lines.append("")
    return lines


def _rewrite_content_link(
    target: str,
    *,
    source: str,
    local_anchors: set[str],
    output_dir: str,
    page_path: str,
    root: Path,
) -> str:
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return target
    path_part, separator, anchor = target.partition("#")
    decoded_anchor = unquote(anchor)
    if not path_part:
        if decoded_anchor in local_anchors:
            return target
        return _source_link(
            source,
            output_dir=output_dir,
            page_path=page_path,
            anchor=decoded_anchor,
        )
    if "?" in path_part:
        raise WikiError(f"source_section link queries are unsupported: {target}")
    decoded_path = unquote(path_part)
    repository_path = posixpath.normpath(
        posixpath.join(PurePosixPath(source).parent.as_posix(), decoded_path)
    )
    if repository_path == ".." or repository_path.startswith("../"):
        raise WikiError(f"source_section link escapes repository: {source} -> {target}")
    resolved = (root / repository_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise WikiError(f"source_section link escapes repository: {source} -> {target}") from exc
    if not resolved.is_file():
        raise WikiError(f"source_section link target is missing: {source} -> {target}")
    if separator and resolved.suffix.lower() == ".md":
        target_anchors = {item[2] for item in _headings(resolved.read_text(encoding="utf-8"))}
        if decoded_anchor not in target_anchors:
            raise WikiError(f"source_section link anchor is missing: {source} -> {target}")
    return _source_link(
        repository_path,
        output_dir=output_dir,
        page_path=page_path,
        anchor=decoded_anchor if separator else "",
    )


def _render_source_section(
    block: dict[str, Any],
    *,
    output_dir: str,
    page_path: str,
    root: Path,
) -> list[str]:
    source = str(block["source"])
    selector = block["selector"]
    heading = str(selector["heading"])
    text = (root / source).read_text(encoding="utf-8")
    section, root_level, local_anchors = _source_section(text, heading)
    section_anchor = _headings(section)[0][2]
    lines = [
        f"> **Quellengebundener Abschnitt:** [{TICK}{source}{TICK}]("
        f"{_source_link(source, output_dir=output_dir, page_path=page_path, anchor=section_anchor)}) "
        f"· {CLASS_LABELS[str(block['document_class'])]} · "
        f"{TICK}{block['id']}{TICK}",
        "",
    ]
    fence_char = ""
    fence_length = 0
    for line in section.splitlines():
        if fence_char:
            lines.append(line)
            if re.match(rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_length},}}\s*$", line):
                fence_char = ""
                fence_length = 0
            continue
        opening = re.match(r"^ {0,3}((?:\x60){3,}|~{3,})(.*)$", line)
        if opening is not None:
            marker = opening.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            lines.append(line)
            continue
        heading_match = re.match(r"^(#{1,6})(\s+.+)$", line)
        if heading_match is not None:
            level = min(6, 3 + len(heading_match.group(1)) - root_level)
            line = "#" * level + heading_match.group(2)

        def replace(match: re.Match[str]) -> str:
            rewritten = _rewrite_content_link(
                match.group(2),
                source=source,
                local_anchors=local_anchors,
                output_dir=output_dir,
                page_path=page_path,
                root=root,
            )
            return match.group(1) + rewritten + match.group(3)

        lines.append(MARKDOWN_LINK_RE.sub(replace, line))
    lines.append("")
    return lines


def _display_fact(value: Any) -> str:
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return f"{TICK}{serialized}{TICK}"
    if isinstance(value, (int, float)):
        return f"{TICK}{value}{TICK}"
    return str(value)


def _render_resolved_fact(block: dict[str, Any]) -> list[str]:
    selector = str(block["selector"])
    payload = _fact_payload(selector)
    metadata = FACT_RESOLVERS[selector]
    lines = [
        f"> **Deterministisch aufgelöster Fact:** "
        f"{TICK}{metadata['source']}{TICK} · "
        f"{CLASS_LABELS[str(block['document_class'])]} · "
        f"{TICK}{block['id']}{TICK}",
        "",
    ]
    if selector == "runtime_inventory":
        lines.extend(["### Laufzeitinventar", "", "| Artefaktklasse | Anzahl |", "|---|---:|"])
        labels = {
            "commands": "Commands",
            "events": "Events",
            "ports": "Ports",
            "slices": "Slices",
            "adapter_groups": "Adapter-Gruppen",
            "core_modules": "Core-Module",
        }
        for key, label in labels.items():
            lines.append(f"| {label} | {payload[key]} |")
    elif selector == "workflow_steps":
        lines.extend(
            [
                "### Ausgelieferte Workflowübergänge",
                "",
                "| Workflow | Ereignis | Command | Bedingung |",
                "|---|---|---|---|",
            ]
        )
        for workflow, steps in payload.items():
            for step in steps:
                lines.append(
                    f"| {TICK}{workflow}{TICK} | {TICK}{step['on']}{TICK} | "
                    f"{TICK}{step['send']}{TICK} | {step.get('condition', '—')} |"
                )
    elif selector == "gate_profiles":
        lines.extend(["### Verfügbare Gates", "", "| ID | Registry-Name |", "|---|---|"])
        for gate in payload["gates"]:
            lines.append(f"| {TICK}{gate['id']}{TICK} | {gate['name']} |")
        lines.extend(
            [
                "",
                "### Ausgelieferte Gate-Profile",
                "",
                "| Profil | Policy | Required | Optional | Disabled |",
                "|---|---|---|---|---|",
            ]
        )
        for filename, profile in payload["profiles"].items():
            name = "default" if filename == "gates" else filename.removeprefix("gates.")
            required = ", ".join(f"{TICK}{item}{TICK}" for item in profile.get("required", []))
            optional = ", ".join(f"{TICK}{item}{TICK}" for item in profile.get("optional", []))
            disabled = ", ".join(f"{TICK}{item}{TICK}" for item in profile.get("disabled", []))
            lines.append(
                f"| {TICK}{name}{TICK} | {TICK}{profile.get('policy_version')}{TICK} | "
                f"{required or '—'} | {optional or '—'} | {disabled or '—'} |"
            )
    elif selector == "policy_thresholds":
        lines.extend(
            [
                "### Ausgelieferte Evaluation- und Test-Policy",
                "",
                "| Herkunft | Schlüssel | Wert |",
                "|---|---|---|",
            ]
        )
        for origin, values in payload.items():
            for key, value in values.items():
                lines.append(
                    f"| {TICK}{origin}{TICK} | {TICK}{key}{TICK} | {_display_fact(value)} |"
                )
    lines.extend(["", f"Fact-Digest: {TICK}{_fact_digest(payload)}{TICK}", ""])
    return lines


def _render_page(
    page: dict[str, Any],
    *,
    manifest: dict[str, Any],
    classified: dict[str, dict[str, str]],
    identity: dict[str, str],
    pages_by_id: dict[str, dict[str, Any]],
    source_to_page: dict[str, str],
    root: Path,
) -> bytes:
    page_path = str(page["path"])
    output_dir = str(manifest["output_dir"])

    def wiki_link(target_page_id: str) -> str:
        return _relative_link(
            from_page=page_path,
            target=str(pages_by_id[target_page_id]["path"]),
        )

    lines = [
        "<!-- Generated by tools/wiki.py; edit sources and manifest, not this file. -->",
        f"# {page['title']}",
        "",
        "> **Nicht autoritative Wiki-Projektion.** Code, ausgelieferte Konfiguration,",
        "> gebundene Resolver und aktive Quelldokumente bleiben maßgeblich.",
        f"> Subject: `{manifest['repository']}@{identity['head_sha']}` · "
        f"Buildstand: `{identity['generated_at']}`",
        f"> Dokumentvertrag: `{identity['document_contract_digest']}` · "
        f"Quelldigest: `{identity['source_digest']}`",
        "",
        f"[Startseite]({wiki_link('wiki.home')}) · "
        f"[Dokumentstatus]({wiki_link('wiki.document-status')}) · "
        "[Quellenvertrag]("
        f"{_source_link('docs/capabilities/document-contract.json', output_dir=output_dir, page_path=page_path)})",
        "",
        "## Aufgabe dieser Seite",
        "",
        str(page["purpose"]),
        "",
        f"**Zielgruppen:** {', '.join(str(item) for item in page['audiences'])}",
        "",
    ]

    if page["id"] == "wiki.home":
        lines.extend(["## Wege nach Aufgabe", ""])
        for persona, route in manifest["personas"].items():
            links = [f"[{pages_by_id[item]['title']}]({wiki_link(item)})" for item in route]
            lines.append(f"- **{persona.capitalize()}:** " + " → ".join(links))
        class_counts = Counter(item["class"] for item in classified.values())
        mode_counts = Counter(item["mode"] for item in classified.values())
        lines.extend(
            [
                "",
                "## Stand des aktiven Inventars",
                "",
                f"Der Build erschließt **{len(classified)} aktive Dokumente**: "
                + ", ".join(
                    f"{count} {CLASS_LABELS.get(class_name, class_name)}"
                    for class_name, count in sorted(class_counts.items())
                )
                + ".",
                "",
                f"Pflegemodi: {mode_counts['manual']} manuell gepflegt, "
                f"{mode_counts['generated']} deterministisch generiert. "
                f"[Vollständiges Inventar]({wiki_link('wiki.document-status')}).",
                "",
            ]
        )

    lines.extend(["## Kerninhalt", ""])
    for block in page["content_blocks"]:
        if block["type"] == "source_section":
            lines.extend(
                _render_source_section(
                    block,
                    output_dir=output_dir,
                    page_path=page_path,
                    root=root,
                )
            )
        else:
            lines.extend(_render_resolved_fact(block))

    if page["id"] == "wiki.document-status":
        content_block_count = sum(len(item["content_blocks"]) for item in manifest["pages"])
        lines.extend(
            [
                "## Gebundener Buildstatus",
                "",
                "| Prüfgegenstand | Validierter Stand |",
                "|---|---|",
                f"| Repository-Head | `{identity['head_sha']}` |",
                f"| Buildstand | `{identity['generated_at']}` |",
                f"| Dokumentvertrag | `{identity['document_contract_digest']}` |",
                f"| Quelldigest | `{identity['source_digest']}` |",
                f"| Primärquellen-Coverage | `{len(classified)}/{len(classified)}` aktive Dokumente exakt zugeordnet |",
                f"| Content-Coverage | `{len(manifest['pages'])}/{len(manifest['pages'])}` Seiten mit `{content_block_count}` gebundenen Blöcken |",
                "| Driftstatus | Manifest, Quellenklassen, Selektoren, Digests und lokale Links beim Build ohne Finding validiert |",
                "",
                "## Vollständiges aktives Dokumentinventar",
                "",
                "| Quelle | Primäre Wiki-Seite | Klasse | Pflegemodus |",
                "|---|---|---|---|",
            ]
        )
        for source, metadata in classified.items():
            primary = pages_by_id[source_to_page[source]]
            lines.append(
                f"| [`{source}`]("
                f"{_source_link(source, output_dir=output_dir, page_path=page_path)}) | "
                f"[{primary['title']}]({wiki_link(str(primary['id']))}) | "
                f"{CLASS_LABELS.get(metadata['class'], metadata['class'])} | "
                f"{MODE_LABELS.get(metadata['mode'], metadata['mode'])} |"
            )
        lines.append("")

    lines.extend(["## Verwandte Wiki-Seiten", ""])
    for related_id in page["related_pages"]:
        related = pages_by_id[related_id]
        lines.append(f"- [{related['title']}]({wiki_link(related_id)}) — `{related_id}`")
    lines.extend(["", "## Gebundene Quellen und Vertiefung", ""])
    for source in page["sources"]:
        lines.extend(
            _render_source(
                source,
                classified[source],
                output_dir=output_dir,
                page_path=page_path,
                root=root,
            )
        )
    lines.extend(
        [
            "## Aussagegrenze",
            "",
            "Diese Seite enthält deterministisch aufgelöste Facts und ausgewählte,",
            "digestgebundene Abschnitte aus den genannten Primärquellen. Sie bestätigt",
            "nicht pauschal die Korrektheit weiterer freier Prosa und ist weder",
            "EvidenceEnvelope noch Gate-, Release- oder Publication-Receipt.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _artifact_digest(pages: list[dict[str, Any]], outputs: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for page in sorted(pages, key=lambda item: str(item["id"])):
        descriptor = json.dumps(
            {"id": page["id"], "path": page["path"]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        content = outputs[str(page["path"])]
        digest.update(len(descriptor).to_bytes(4, "big"))
        digest.update(descriptor)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def build_bundle(
    *,
    root: Path = ROOT,
    manifest: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    identity: dict[str, str],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    manifest = manifest or _read_json(root / MANIFEST_PATH.relative_to(ROOT))
    contract_path = root / DOCUMENT_CONTRACT_PATH.relative_to(ROOT)
    contract = contract or _read_json(contract_path)
    classified = validate_manifest(manifest, contract, root=root)
    pages = manifest["pages"]
    pages_by_id = {str(page["id"]): page for page in pages}
    source_to_page = {str(source): str(page["id"]) for page in pages for source in page["sources"]}
    outputs = {
        str(page["path"]): _render_page(
            page,
            manifest=manifest,
            classified=classified,
            identity=identity,
            pages_by_id=pages_by_id,
            source_to_page=source_to_page,
            root=root,
        )
        for page in pages
    }
    artifact_digest = _artifact_digest(pages, outputs)
    page_manifest = [
        {
            "id": page["id"],
            "path": page["path"],
            "digest": _digest(outputs[str(page["path"])]),
            "primary_source_count": len(page["sources"]),
            "content_block_count": len(page["content_blocks"]),
        }
        for page in pages
    ]
    receipt = {
        "repository": manifest["repository"],
        "head_sha": identity["head_sha"],
        "document_contract_digest": identity["document_contract_digest"],
        "source_digest": identity["source_digest"],
        "generator_version": manifest["generator_version"],
        "artifact_digest": artifact_digest,
        "page_manifest": page_manifest,
        "findings": [],
        "created_at": identity["created_at"],
    }
    return outputs, receipt


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed Git binary and caller-owned literals
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise WikiError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def repository_identity(*, root: Path = ROOT, created_at: str | None = None) -> dict[str, str]:
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise WikiError("tracked repository state is dirty; commit the bound wiki sources first")
    head_sha = _git(root, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", head_sha) is None:
        raise WikiError("HEAD is not a full SHA-1")
    epoch_text = os.environ.get("SOURCE_DATE_EPOCH") or _git(
        root, "show", "-s", "--format=%ct", head_sha
    )
    try:
        epoch = int(epoch_text)
    except ValueError as exc:
        raise WikiError("SOURCE_DATE_EPOCH must be an integer") from exc
    generated_at = (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    actual_created_at = created_at or datetime.now(tz=timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")

    matrix = control_matrix.load_matrix()
    contract = control_matrix.load_document_contract()
    control_matrix.validate(matrix)
    control_matrix.validate_document_contract(contract)
    return {
        "head_sha": head_sha,
        "generated_at": generated_at,
        "created_at": actual_created_at,
        "document_contract_digest": _digest(DOCUMENT_CONTRACT_PATH.read_bytes()),
        "source_digest": str(matrix["audit"]["source_digest"]),
    }


def _write_bundle(output_dir: Path, pages: dict[str, bytes], receipt: dict[str, Any]) -> None:
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise WikiError(f"wiki output must be a real directory path: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".wiki-build-", dir=output_dir.parent))
    previous: Path | None = None
    try:
        for path, content in pages.items():
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (staging / "build-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output_dir.exists():
            previous = Path(tempfile.mkdtemp(prefix=".wiki-previous-", dir=output_dir.parent))
            previous.rmdir()
            output_dir.replace(previous)
        try:
            staging.replace(output_dir)
        except Exception:
            if previous is not None and previous.exists() and not output_dir.exists():
                previous.replace(output_dir)
                previous = None
            raise
        if previous is not None:
            shutil.rmtree(previous)
            previous = None
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if previous is not None:
            if not output_dir.exists():
                previous.replace(output_dir)
            else:
                shutil.rmtree(previous, ignore_errors=True)
        raise


def check(*, root: Path = ROOT) -> dict[str, Any]:
    first_identity = repository_identity(root=root, created_at="2000-01-01T00:00:00Z")
    second_identity = {**first_identity, "created_at": "2099-12-31T23:59:59Z"}
    first_pages, first_receipt = build_bundle(root=root, identity=first_identity)
    second_pages, second_receipt = build_bundle(root=root, identity=second_identity)
    if first_pages != second_pages:
        raise WikiError("wiki pages differ between builds of the same bound state")
    if first_receipt["artifact_digest"] != second_receipt["artifact_digest"]:
        raise WikiError("artifact_digest differs between builds of the same bound state")
    first_stable = {key: value for key, value in first_receipt.items() if key != "created_at"}
    second_stable = {key: value for key, value in second_receipt.items() if key != "created_at"}
    if first_stable != second_stable or first_receipt["created_at"] == second_receipt["created_at"]:
        raise WikiError("wall-clock variation changed more than receipt.created_at")
    return first_receipt


def check_materialized(*, root: Path = ROOT) -> dict[str, Any]:
    """Verify that the ignored repository-local wiki matches the bound HEAD."""

    identity = repository_identity(root=root, created_at="2000-01-01T00:00:00Z")
    manifest = _read_json(root / MANIFEST_PATH.relative_to(ROOT))
    expected_pages, expected_receipt = build_bundle(
        root=root,
        manifest=manifest,
        identity=identity,
    )
    output_dir = root / str(manifest["output_dir"])
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise WikiError(f"materialized wiki is missing: {output_dir.relative_to(root)}")

    expected_files = {*expected_pages, "build-receipt.json"}
    actual_files = {
        path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*") if path.is_file()
    }
    if actual_files != expected_files:
        raise WikiError(
            "materialized wiki file set differs: "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )

    changed_pages = [
        path
        for path, content in expected_pages.items()
        if (output_dir / path).read_bytes() != content
    ]
    if changed_pages:
        raise WikiError(f"materialized wiki pages are stale or modified: {changed_pages}")

    actual_receipt = _read_json(output_dir / "build-receipt.json")
    expected_stable = {key: value for key, value in expected_receipt.items() if key != "created_at"}
    actual_stable = {key: value for key, value in actual_receipt.items() if key != "created_at"}
    if actual_stable != expected_stable or not str(actual_receipt.get("created_at", "")).strip():
        raise WikiError("materialized wiki receipt does not match the bound repository state")
    return actual_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check", "check-local", "impact"))
    args = parser.parse_args()
    try:
        if args.command == "impact":
            print(json.dumps(wiki_impact(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "check":
            receipt = check()
            print(
                "wiki valid: "
                f"{len(receipt['page_manifest'])} pages, "
                f"artifact={receipt['artifact_digest']}"
            )
            return 0
        if args.command == "check-local":
            receipt = check_materialized()
            print(
                "local wiki current: "
                f"{len(receipt['page_manifest'])} pages, "
                f"artifact={receipt['artifact_digest']}"
            )
            return 0
        identity = repository_identity()
        manifest = _read_json(MANIFEST_PATH)
        pages, receipt = build_bundle(manifest=manifest, identity=identity)
        output_dir = ROOT / str(manifest["output_dir"])
        _write_bundle(output_dir, pages, receipt)
        print(
            f"wiki built: {output_dir.relative_to(ROOT)}, "
            f"{len(pages)} pages, artifact={receipt['artifact_digest']}"
        )
        return 0
    except (WikiError, control_matrix.MatrixError) as exc:
        print(f"wiki invalid:\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
