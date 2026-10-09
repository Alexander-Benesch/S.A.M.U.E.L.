#!/usr/bin/env python3
"""Validate and render S.A.M.U.E.L. control and documentation contracts.

The runtime code and shipped configuration remain authoritative for behaviour
and activation.  This tool validates the audit assessment and source-bound
documentation against those sources; it is deliberately not imported by the
product runtime.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs" / "capabilities" / "control-matrix.json"
OUTPUT_PATH = ROOT / "docs" / "CAPABILITY_MATRIX.md"
DOCUMENT_CONTRACT_PATH = ROOT / "docs" / "capabilities" / "document-contract.json"
RUNTIME_REFERENCE_PATH = ROOT / "docs" / "RUNTIME_REFERENCE.md"
ADR_INDEX_PATH = ROOT / "docs" / "adr" / "README.md"

DOCUMENT_CLASSES = {
    "runtime_reference",
    "adr",
    "operations",
    "target_architecture",
    "history",
}
DOCUMENT_MODES = {"generated", "manual"}
SOURCE_SELECTOR_KINDS = {"file", "glob", "python_symbol", "json_pointer", "text_range"}
DOCUMENT_REVIEW_STATES = {"reviewed", "review_required"}

CONTROL_CLASSES = {
    "input_context",
    "execution",
    "artifact_commit",
    "process_contract",
    "evidence_telemetry",
}
LIFECYCLE_STATES = {
    "implemented",
    "unwired",
    "disabled",
    "experimental",
    "deprecated",
    "planned",
    "unknown",
    "not_applicable",
}
EFFECT_MODES = {"enforced", "advisory", "telemetry", "disabled", "not_applicable"}
READINESS_STATES = {"ready", "blocked", "not_target"}
RUNTIME_KINDS = {"gate", "external_gate", "middleware", "python", "scm", "configuration"}


class MatrixError(ValueError):
    """Raised when the governance artifact diverges from repository truth."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatrixError(f"cannot read {path.relative_to(ROOT)}: {exc}") from exc


def load_matrix() -> dict[str, Any]:
    value = _load_json(MATRIX_PATH)
    if not isinstance(value, dict):
        raise MatrixError("control matrix root must be an object")
    return value


def load_document_contract() -> dict[str, Any]:
    value = _load_json(DOCUMENT_CONTRACT_PATH)
    if not isinstance(value, dict):
        raise MatrixError("document contract root must be an object")
    return value


def _gate_truth() -> tuple[set[str], dict[str, str]]:
    sys.path.insert(0, str(ROOT))
    try:
        from samuel.core.gate_metadata import GATE_NAMES
        from samuel.slices.pr_gates.gates import GATE_REGISTRY
    finally:
        sys.path.pop(0)
    ids = {str(gate_id) for gate_id in GATE_REGISTRY}
    names = {str(gate_id): str(name) for gate_id, name in GATE_NAMES.items()}
    if ids != set(names):
        raise MatrixError("GATE_REGISTRY and GATE_NAMES already diverge")
    return ids, names


def _external_gate_truth() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted((ROOT / "samuel" / "slices").glob("*/gate.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(
                (isinstance(base, ast.Name) and base.id == "IExternalGate")
                or (isinstance(base, ast.Attribute) and base.attr == "IExternalGate")
                for base in node.bases
            ):
                continue
            for statement in node.body:
                if (
                    isinstance(statement, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "name"
                        for target in statement.targets
                    )
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                ):
                    found[statement.value.value] = node.name
    return found


def _middleware_truth() -> list[str]:
    tree = ast.parse(
        (ROOT / "samuel" / "core" / "bootstrap.py").read_text(encoding="utf-8"),
        filename="samuel/core/bootstrap.py",
    )
    result: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_middleware" or not node.args:
            continue
        constructor = node.args[0]
        if isinstance(constructor, ast.Call):
            if isinstance(constructor.func, ast.Name):
                result.append(constructor.func.id)
            elif isinstance(constructor.func, ast.Attribute):
                result.append(constructor.func.attr)
    return result


def _workflow_truth() -> dict[str, set[str]]:
    workflows: dict[str, set[str]] = {}
    for path in sorted((ROOT / "config" / "workflows").glob("*.json")):
        value = _load_json(path)
        name = str(value.get("name", path.stem))
        workflows[name] = {
            str(step.get("send"))
            for step in value.get("steps", [])
            if isinstance(step, dict) and step.get("send")
        }
    return workflows


def _audited_paths() -> list[Path]:
    """Return active product, policy, proof, and claim sources.

    Archives and generated matrix output are intentionally excluded. The
    digest forces an explicit matrix review after relevant source changes
    without turning this audit artifact into runtime configuration.
    """
    paths: set[Path] = set()
    for pattern in (
        "samuel/**/*.py",
        "samuel/**/*.json",
        "tests/**/*.py",
        "config/**/*.json",
        ".gitea/workflows/*",
        "tools/control_matrix.py",
        "tools/wiki.py",
        "tools/wiki_publish.py",
        "pyproject.toml",
        "docs/capabilities/document-contract.json",
        "docs/capabilities/wiki-manifest.json",
        ".claude/CLAUDE.md",
        "CHANGELOG.md",
        "README.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "docs/**/*.md",
        "technische Beschreibungen/*",
    ):
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    paths = {
        path
        for path in paths
        if not (
            path.is_relative_to(ROOT / "docs")
            and "archive" in path.relative_to(ROOT / "docs").parts
        )
    }
    paths.discard(OUTPUT_PATH)
    paths.discard(RUNTIME_REFERENCE_PATH)
    paths.discard(ADR_INDEX_PATH)
    paths.discard(MATRIX_PATH)
    tracked = _tracked_paths()
    if tracked is not None:
        paths.intersection_update(tracked)
    return sorted(paths)


def _tracked_paths() -> set[Path] | None:
    """Return repository-tracked files, or ``None`` outside a Git checkout.

    Local ignored or untracked configuration must not change the reviewed
    source digest: CI evaluates the committed repository artifact, not an
    operator's working-directory overlay.
    """

    top = subprocess.run(  # noqa: S603,S607 - fixed read-only Git command
        ["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != ROOT.resolve():
        return None
    listed = subprocess.run(  # noqa: S603,S607 - fixed read-only Git command
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if listed.returncode != 0:
        return None
    return {
        ROOT / raw.decode("utf-8", errors="surrogateescape")
        for raw in listed.stdout.split(b"\0")
        if raw
    }


def _source_digest() -> str:
    digest = hashlib.sha256()
    for path in _audited_paths():
        relative = path.relative_to(ROOT).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _active_document_paths() -> set[str]:
    paths = {
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "MANIFESTO.md",
        "README.md",
        "SECURITY.md",
    }
    paths.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "docs").rglob("*.md")
        if "archive" not in path.relative_to(ROOT / "docs").parts
        and path not in {OUTPUT_PATH, RUNTIME_REFERENCE_PATH, ADR_INDEX_PATH}
    )
    paths.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "technische Beschreibungen").glob("*.md")
    )
    return paths


def _document_contract_paths() -> set[str]:
    """Return every active document, including generated reference outputs."""

    paths = _active_document_paths()
    paths.add(".claude/CLAUDE.md")
    paths.update(
        {
            OUTPUT_PATH.relative_to(ROOT).as_posix(),
            RUNTIME_REFERENCE_PATH.relative_to(ROOT).as_posix(),
            ADR_INDEX_PATH.relative_to(ROOT).as_posix(),
        }
    )
    return paths


def _node_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                return target.id
    return None


def _python_symbol_text(path: Path, symbol: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    current: ast.AST = tree
    selected: ast.AST | None = None
    for part in symbol.split("."):
        body = getattr(current, "body", [])
        selected = next((node for node in body if _node_name(node) == part), None)
        if selected is None:
            raise MatrixError(
                f"document source selector {symbol!r} is absent from {path.relative_to(ROOT)}"
            )
        current = selected
    assert selected is not None
    start = getattr(selected, "lineno", None)
    end = getattr(selected, "end_lineno", None)
    if not isinstance(start, int) or not isinstance(end, int):
        raise MatrixError(f"cannot locate source lines for {symbol!r} in {path.relative_to(ROOT)}")
    return "\n".join(source.splitlines()[start - 1 : end])


def _json_pointer_value(path: Path, pointer: str) -> Any:
    value = _load_json(path)
    if pointer in {"", "/"}:
        return value
    current = value
    for raw_part in pointer.removeprefix("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        try:
            current = current[int(part)] if isinstance(current, list) else current[part]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MatrixError(
                f"document JSON pointer {pointer!r} is absent from {path.relative_to(ROOT)}"
            ) from exc
    return current


def _text_range(path: Path, start_marker: str, end_marker: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        raise MatrixError(
            f"document text-range start {start_marker!r} is absent from {path.relative_to(ROOT)}"
        )
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise MatrixError(
            f"document text-range end {end_marker!r} is absent from {path.relative_to(ROOT)}"
        )
    return text[start : end + len(end_marker)]


def _selected_source(source: dict[str, Any]) -> bytes:
    path_text = str(source.get("path", ""))
    kind = str(source.get("kind", ""))
    if kind not in SOURCE_SELECTOR_KINDS:
        raise MatrixError(f"invalid document source selector kind {kind!r} for {path_text}")
    if kind == "glob":
        paths = sorted(path for path in ROOT.glob(path_text) if path.is_file())
        if not paths:
            raise MatrixError(f"document source glob has no files: {path_text}")
        chunks: list[bytes] = []
        for matched in paths:
            relative = matched.relative_to(ROOT).as_posix().encode()
            content = matched.read_bytes()
            chunks.extend(
                [
                    len(relative).to_bytes(4, "big"),
                    relative,
                    len(content).to_bytes(8, "big"),
                    content,
                ]
            )
        return b"".join(chunks)
    path = ROOT / path_text
    if not path.is_file():
        raise MatrixError(f"document source does not exist: {path_text}")
    if kind == "file":
        return path.read_bytes()
    if kind == "python_symbol":
        return _python_symbol_text(path, str(source.get("symbol", ""))).encode()
    if kind == "json_pointer":
        value = _json_pointer_value(path, str(source.get("pointer", "")))
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return _text_range(
        path,
        str(source.get("start", "")),
        str(source.get("end", "")),
    ).encode()


def _contract_source_digest(sources: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for source in sources:
        descriptor = json.dumps(source, ensure_ascii=False, sort_keys=True).encode()
        selected = _selected_source(source)
        digest.update(len(descriptor).to_bytes(4, "big"))
        digest.update(descriptor)
        digest.update(len(selected).to_bytes(8, "big"))
        digest.update(selected)
    return f"sha256:{digest.hexdigest()}"


def _source_label(source: dict[str, Any]) -> str:
    """Render one selector without hiding its binding granularity."""

    path = str(source["path"])
    kind = str(source["kind"])
    if kind == "python_symbol":
        return f"{path}::{source['symbol']}"
    if kind == "json_pointer":
        return f"{path}#{source['pointer']}"
    if kind == "text_range":
        return f"{path}::{source['start']}…{source['end']}"
    if kind == "glob":
        return f"glob:{path}"
    return path


def _bind_generated_rendering(rendered: str, section: dict[str, Any]) -> str:
    """Add manifest-derived provenance to a generated document or fragment."""

    source_lines = [
        *[f"- `{_source_label(source)}`" for source in section["sources"]],
        f"- Vertrag: `docs/capabilities/document-contract.json::{section['id']}`",
    ]
    source_block = "\n".join(source_lines)
    end_marker = re.search(r"<!-- docs-contract:[^:]+:end -->\s*$", rendered)
    if end_marker:
        return (
            rendered[: end_marker.start()].rstrip()
            + "\n\n**Quellenbindung:**\n"
            + source_block
            + "\n"
            + rendered[end_marker.start() :]
        )
    return rendered.rstrip() + "\n\n## Quellenbindung\n\n" + source_block + "\n"


def document_contract_impact(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Report source-bound sections requiring regeneration or manual review."""

    impacts: list[dict[str, Any]] = []
    defaults = contract.get("section_defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    sections = contract.get("sections", [])
    if not isinstance(sections, list):
        return impacts
    for section in sections:
        if not isinstance(section, dict):
            continue
        sources = section.get("sources", [])
        if not isinstance(sources, list) or not sources:
            continue
        try:
            expected = _contract_source_digest(sources)
        except MatrixError as exc:
            impacts.append(
                {
                    "section": str(section.get("id", "")),
                    "document": str(section.get("document", "")),
                    "mode": str(section.get("mode", "")),
                    "reason": str(exc),
                    "sources": [_source_label(item) for item in sources],
                    "proofs": section.get("proofs", []),
                }
            )
            continue
        if section.get("source_digest") != expected:
            impacts.append(
                {
                    "section": str(section.get("id", "")),
                    "document": str(section.get("document", "")),
                    "mode": str(section.get("mode", "")),
                    "reason": "source_binding_changed",
                    "sources": [_source_label(item) for item in sources],
                    "proofs": section.get("proofs", []),
                    "review_rule": str(section.get("review_rule", defaults.get("review_rule", ""))),
                    "expected_source_digest": expected,
                }
            )
    return impacts


def _require_manual_reviews_current(contract: dict[str, Any]) -> None:
    """Prevent render from rubber-stamping source changes in manual prose."""

    impacts = [item for item in document_contract_impact(contract) if item["mode"] == "manual"]
    if not impacts:
        return
    details = "; ".join(
        f"{item['section']} ({item['document']}): {item['reason']}" for item in impacts
    )
    raise MatrixError(f"manual documentation review required before render: {details}")


def _workflow_steps_truth() -> dict[str, list[dict[str, Any]]]:
    workflows: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((ROOT / "config" / "workflows").glob("*.json")):
        value = _load_json(path)
        name = str(value.get("name", path.stem))
        workflows[name] = [
            {
                "on": str(step["on"]),
                "send": str(step["send"]),
                **({"condition": str(step["condition"])} if step.get("condition") else {}),
            }
            for step in value.get("steps", [])
            if isinstance(step, dict) and step.get("on") and step.get("send")
        ]
    return workflows


def _runtime_inventory_truth() -> dict[str, int]:
    def classes(path: Path, excluded: set[str] | None = None) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        excluded = excluded or set()
        return {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name not in excluded
        }

    return {
        "commands": len(classes(ROOT / "samuel" / "core" / "commands.py", {"Command"})),
        "events": len(classes(ROOT / "samuel" / "core" / "events.py", {"Event"})),
        "ports": len(classes(ROOT / "samuel" / "core" / "ports.py")),
        "slices": len(
            [
                path
                for path in (ROOT / "samuel" / "slices").iterdir()
                if path.is_dir() and (path / "__init__.py").is_file()
            ]
        ),
        "adapter_groups": len(
            [
                path
                for path in (ROOT / "samuel" / "adapters").iterdir()
                if path.is_dir() and (path / "__init__.py").is_file()
            ]
        ),
        "core_modules": len(list((ROOT / "samuel" / "core").glob("*.py"))),
    }


def _ac_tag_truth() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    try:
        from samuel.slices.ac_verification import handler as verification
        from samuel.slices.evaluation import bound_scoring
        from samuel.slices.planning import handler as planning
        from samuel.slices.scoring import handler as scoring
    finally:
        sys.path.pop(0)
    available = set(verification._AC_REGISTRY)
    accepted = set(planning._VALID_AC_TAGS)
    if available != accepted:
        raise MatrixError(
            f"AC tag registry drift: verifier={sorted(available)} planner={sorted(accepted)}"
        )
    return {
        "available": sorted(available),
        "planner_accepted": sorted(accepted),
        "plan_deferred": sorted(verification._PLAN_DEFERRED_TAGS),
        "complexity_counted": sorted(planning._COMPLEXITY_PFLICHT_TAGS),
        "score_families": {
            name: sorted(tags) for name, tags in sorted(scoring._TAG_FAMILIES.items())
        },
        "hallucination_tags": sorted(scoring._HALLUCINATION_TAGS),
        "bound_categories": dict(sorted(bound_scoring.TAG_CATEGORIES.items())),
    }


def _threshold_truth() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    try:
        from samuel.core.config import EvalSchema
        from samuel.slices.planning import handler as planning
    finally:
        sys.path.pop(0)
    eval_config = _load_json(ROOT / "config" / "eval.json")
    gate_profiles = {
        path.stem: _load_json(path) for path in sorted((ROOT / "config").glob("gates*.json"))
    }
    return {
        "code_defaults": {
            "eval.baseline": EvalSchema.model_fields["baseline"].default,
            "planning.complexity": dict(planning._COMPLEXITY_DEFAULTS),
        },
        "shipped_eval": {
            "baseline": eval_config.get("baseline"),
            "weights": eval_config.get("weights", {}),
            "fail_fast_on": eval_config.get("fail_fast_on", []),
            "policy_version": eval_config.get("policy_version"),
            "formula_version": eval_config.get("formula_version"),
            "test_policy_version": eval_config.get("test_policy_version"),
            "test_cmd": eval_config.get("test_cmd"),
            "test_timeout": eval_config.get("test_timeout"),
        },
        "shipped_gate_profiles": gate_profiles,
    }


def _verifier_environment_truth() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    try:
        from samuel.core.process_environment import (
            VERIFIER_ENVIRONMENT_KEYS,
            VERIFIER_ENVIRONMENT_PROFILE,
        )
    finally:
        sys.path.pop(0)
    return {
        "profile": VERIFIER_ENVIRONMENT_PROFILE,
        "keys": sorted(VERIFIER_ENVIRONMENT_KEYS),
    }


def _watch_concurrency_truth() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    try:
        from samuel.core.config import (
            SUPPORTED_WATCH_MAX_PARALLEL,
            resolve_watch_parallelism,
        )
    finally:
        sys.path.pop(0)

    watch_path = ROOT / "samuel" / "slices" / "watch" / "handler.py"
    watch_tree = ast.parse(watch_path.read_text(encoding="utf-8"), filename=str(watch_path))
    watch_class = next(
        (
            node
            for node in watch_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "WatchHandler"
        ),
        None,
    )
    if watch_class is None:
        raise MatrixError("WatchHandler is absent")
    methods = {node.name: node for node in watch_class.body if isinstance(node, ast.FunctionDef)}
    if not {"handle", "_try_acquire", "_release"} <= set(methods):
        raise MatrixError("WatchHandler concurrency methods drifted")
    guarded_dispatches = 0
    for node in ast.walk(methods["handle"]):
        if not isinstance(node, ast.Try):
            continue
        releases = [
            call
            for statement in node.finalbody
            for call in ast.walk(statement)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "_release"
        ]
        publishes = [
            call
            for statement in node.body
            for call in ast.walk(statement)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "publish"
        ]
        if releases and publishes:
            guarded_dispatches += 1
    if guarded_dispatches != 2:
        raise MatrixError(
            f"expected two WatchHandler publish/finally release paths, found {guarded_dispatches}"
        )

    bus_path = ROOT / "samuel" / "core" / "bus.py"
    bus_tree = ast.parse(bus_path.read_text(encoding="utf-8"), filename=str(bus_path))
    bus_class = next(
        (node for node in bus_tree.body if isinstance(node, ast.ClassDef) and node.name == "Bus"),
        None,
    )
    publish = next(
        (
            node
            for node in getattr(bus_class, "body", [])
            if isinstance(node, ast.FunctionDef) and node.name == "publish"
        ),
        None,
    )
    if publish is None:
        raise MatrixError("Bus.publish is absent or asynchronous")

    bootstrap_text = (ROOT / "samuel" / "core" / "bootstrap.py").read_text(encoding="utf-8")
    if "release_slot" in bootstrap_text:
        raise MatrixError("bootstrap unexpectedly contains terminal-event release_slot wiring")
    agent_max_parallel = _load_json(ROOT / "config" / "agent.json").get("max_parallel")
    workflow_max_parallel = {
        path.stem: _load_json(path).get("max_parallel")
        for path in sorted((ROOT / "config" / "workflows").glob("*.json"))
    }
    for workflow_name, workflow_limit in workflow_max_parallel.items():
        try:
            resolve_watch_parallelism(agent_max_parallel, workflow_limit)
        except ValueError as exc:
            raise MatrixError(f"unsupported Watch parallelism in {workflow_name}: {exc}") from exc
    return {
        "bus_mode": "synchronous",
        "scan_dispatch": "sequential",
        "guarded_dispatches": guarded_dispatches,
        "acquire_method": "WatchHandler._try_acquire",
        "release_method": "WatchHandler._release",
        "release_trigger": "synchronous dispatch return via try/finally",
        "terminal_event_subscription": False,
        "coordination_scope": "process-local",
        "multi_process_coordination": False,
        "supported_max_parallel": SUPPORTED_WATCH_MAX_PARALLEL,
        "agent_max_parallel": agent_max_parallel,
        "workflow_max_parallel": workflow_max_parallel,
        "unsupported_values": "fail-closed",
    }


def _gate_effects(gate_id: str) -> list[dict[str, str]]:
    effects: list[dict[str, str]] = []
    for profile, filename in (
        ("default", "gates.json"),
        ("self", "gates.self.json"),
        ("audit", "gates.audit.json"),
    ):
        value = _load_json(ROOT / "config" / filename)
        required = {str(item) for item in value.get("required", [])}
        optional = {str(item) for item in value.get("optional", [])}
        disabled = {str(item) for item in value.get("disabled", [])}
        if gate_id in disabled:
            mode = "disabled"
        elif gate_id in required:
            mode = "enforced"
        elif gate_id in optional:
            mode = "advisory"
        else:
            raise MatrixError(f"gate {gate_id} is absent from profile {profile}")
        effects.append(
            {
                "context": f"gate-profile:{profile}",
                "mode": mode,
                "source": f"config/{filename}",
            }
        )
    return effects


def _require_text(control: dict[str, Any], key: str) -> None:
    if not isinstance(control.get(key), str) or not control[key].strip():
        raise MatrixError(f"{control.get('id', '?')}: {key} must be non-empty text")


def _validate_reference(control_id: str, reference: str) -> None:
    path_text = reference.split("#", 1)[0].split("::", 1)[0]
    path = ROOT / path_text
    if not path.is_file():
        raise MatrixError(f"{control_id}: missing reference {reference}")
    marker = ""
    if "::" in reference:
        marker = reference.rsplit("::", 1)[1]
    elif "#" in reference:
        marker = reference.rsplit("#", 1)[1]
    if marker and marker not in path.read_text(encoding="utf-8"):
        raise MatrixError(f"{control_id}: marker {marker!r} not found in {path_text}")


def validate(matrix: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if matrix.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    audit = matrix.get("audit")
    if not isinstance(audit, dict) or not isinstance(audit.get("baseline_commit"), str):
        errors.append("audit.baseline_commit is required")
    elif len(audit["baseline_commit"]) != 40:
        errors.append("audit.baseline_commit must be a full SHA-1")
    if not isinstance(audit, dict) or audit.get("source_digest") != _source_digest():
        errors.append(f"audit.source_digest is stale; reviewed source digest is {_source_digest()}")
    reviewed_documents = (
        set(audit.get("reviewed_active_documents", [])) if isinstance(audit, dict) else set()
    )
    if reviewed_documents != _active_document_paths():
        errors.append(
            "active-document review drift: "
            f"matrix={sorted(reviewed_documents)} "
            f"runtime={sorted(_active_document_paths())}"
        )
    baseline = matrix.get("release_baseline")
    if not isinstance(baseline, dict) or baseline.get("id") != "reference-worker-first-release":
        errors.append("release_baseline.id must be reference-worker-first-release")
    qualification = matrix.get("reference_qualification")
    if not isinstance(qualification, dict):
        errors.append("reference_qualification is required")
    else:
        qualification_status = qualification.get("status")
        qualification_missing = qualification.get("missing")
        qualification_observed = qualification.get("observed")
        qualification_findings = qualification.get("known_findings")
        if qualification.get("id") != "internal-d0":
            errors.append("reference_qualification.id must be internal-d0")
        if not isinstance(qualification.get("authority_issue"), int):
            errors.append("reference_qualification.authority_issue must be an issue number")
        if qualification_status not in {"not_started", "partial", "qualified"}:
            errors.append("reference_qualification.status is invalid")
        if not isinstance(qualification_observed, list):
            errors.append("reference_qualification.observed must be a list")
        if not isinstance(qualification_missing, list):
            errors.append("reference_qualification.missing must be a list")
        if not isinstance(qualification_findings, list) or any(
            not isinstance(item, int) for item in qualification_findings
        ):
            errors.append("reference_qualification.known_findings must contain issue numbers")
        if qualification_status == "qualified" and (
            qualification_missing or not isinstance(qualification.get("qualified_release"), str)
        ):
            errors.append(
                "qualified reference_qualification requires a release and no missing evidence"
            )
    controls = matrix.get("controls")
    if not isinstance(controls, list) or not controls:
        errors.append("controls must be a non-empty list")
    if errors:
        raise MatrixError("; ".join(errors))
    assert isinstance(baseline, dict)
    assert isinstance(controls, list)

    gate_ids, gate_names = _gate_truth()
    external_truth = _external_gate_truth()
    middleware_truth = _middleware_truth()
    workflow_truth = _workflow_truth()
    bootstrap_text = (ROOT / "samuel" / "core" / "bootstrap.py").read_text(encoding="utf-8")

    seen_ids: set[str] = set()
    matrix_gates: dict[str, dict[str, Any]] = {}
    matrix_external: dict[str, dict[str, Any]] = {}
    matrix_middlewares: list[str] = []
    controls_by_id: dict[str, dict[str, Any]] = {}

    for raw in controls:
        if not isinstance(raw, dict):
            errors.append("every control must be an object")
            continue
        control = raw
        control_id = str(control.get("id", ""))
        if not control_id or control_id in seen_ids:
            errors.append(f"duplicate or empty control id: {control_id!r}")
            continue
        seen_ids.add(control_id)
        controls_by_id[control_id] = control
        for key in (
            "name",
            "objective",
            "actual_behavior",
            "failure_behavior",
            "subject_binding",
            "evidence",
            "trust_and_data",
        ):
            try:
                _require_text(control, key)
            except MatrixError as exc:
                errors.append(str(exc))
        if control.get("class") not in CONTROL_CLASSES:
            errors.append(f"{control_id}: invalid class {control.get('class')!r}")
        if control.get("lifecycle") not in LIFECYCLE_STATES:
            errors.append(f"{control_id}: invalid lifecycle {control.get('lifecycle')!r}")
        if control.get("baseline_readiness") not in READINESS_STATES:
            errors.append(f"{control_id}: invalid baseline_readiness")
        runtime = control.get("runtime")
        if not isinstance(runtime, dict) or runtime.get("kind") not in RUNTIME_KINDS:
            errors.append(f"{control_id}: invalid runtime descriptor")
            continue
        kind = runtime["kind"]
        if kind == "gate":
            gate_id = str(runtime.get("gate_id", ""))
            matrix_gates[gate_id] = control
            effects = _gate_effects(gate_id) if gate_id in gate_ids else []
            if control.get("name") != gate_names.get(gate_id):
                errors.append(
                    f"{control_id}: gate name must reuse GATE_NAMES ({gate_names.get(gate_id)!r})"
                )
        else:
            effects = control.get("effects", [])
        if kind == "external_gate":
            matrix_external[str(runtime.get("external_name", ""))] = control
            class_name = str(runtime.get("class_name", ""))
            if control.get("lifecycle") != "unwired" and class_name not in bootstrap_text:
                errors.append(f"{control_id}: external gate {class_name} is not wired in bootstrap")
        if kind == "middleware":
            matrix_middlewares.append(str(runtime.get("class_name", "")))
        if not isinstance(effects, list) or not effects:
            errors.append(f"{control_id}: effective modes are missing")
            effects = []
        for effect in effects:
            if not isinstance(effect, dict) or effect.get("mode") not in EFFECT_MODES:
                errors.append(f"{control_id}: invalid effect {effect!r}")

        references = control.get("references", [])
        if not isinstance(references, list) or not references:
            errors.append(f"{control_id}: references are required")
        else:
            for reference in references:
                try:
                    _validate_reference(control_id, str(reference))
                except MatrixError as exc:
                    errors.append(str(exc))

        proofs = control.get("proofs", {})
        if not isinstance(proofs, dict):
            errors.append(f"{control_id}: proofs must be an object")
            proofs = {}
        for proof_kind in ("positive", "negative", "bypass"):
            values = proofs.get(proof_kind, [])
            if not isinstance(values, list):
                errors.append(f"{control_id}: proofs.{proof_kind} must be a list")
                continue
            for reference in values:
                try:
                    _validate_reference(control_id, str(reference))
                except MatrixError as exc:
                    errors.append(str(exc))
        if any(effect.get("mode") == "enforced" for effect in effects if isinstance(effect, dict)):
            if not proofs.get("positive") or not proofs.get("negative"):
                errors.append(
                    f"{control_id}: enforced controls require positive and negative proofs"
                )
            if not proofs.get("bypass") and not proofs.get("bypass_rationale"):
                errors.append(f"{control_id}: enforced controls require bypass proof or rationale")

        claims = control.get("claims", [])
        if not isinstance(claims, list):
            errors.append(f"{control_id}: claims must be a list")
        else:
            for claim in claims:
                if not isinstance(claim, dict) or claim.get("disposition") not in {
                    "verified",
                    "qualified",
                    "withdrawn",
                    "target",
                }:
                    errors.append(f"{control_id}: invalid claim mapping {claim!r}")
                    continue
                document = ROOT / str(claim.get("document", ""))
                if not document.is_file():
                    errors.append(f"{control_id}: claim document does not exist: {document}")
                    continue
                section = str(claim.get("section", "")).strip()
                if not section or section not in document.read_text(encoding="utf-8"):
                    errors.append(
                        f"{control_id}: claim section {section!r} is absent from "
                        f"{document.relative_to(ROOT)}"
                    )

    if set(matrix_gates) != gate_ids:
        errors.append(
            f"gate inventory drift: matrix={sorted(matrix_gates)} runtime={sorted(gate_ids)}"
        )
    if set(matrix_external) != set(external_truth):
        errors.append(
            "external-gate inventory drift: "
            f"matrix={sorted(matrix_external)} runtime={sorted(external_truth)}"
        )
    else:
        for name, class_name in external_truth.items():
            if matrix_external[name]["runtime"].get("class_name") != class_name:
                errors.append(f"external gate {name} must use runtime class {class_name}")
    if matrix_middlewares != middleware_truth:
        errors.append(
            f"middleware order drift: matrix={matrix_middlewares} runtime={middleware_truth}"
        )

    target_ids = baseline.get("controls", []) if isinstance(baseline, dict) else []
    if len(target_ids) != len(set(target_ids)):
        errors.append("release baseline contains duplicate control IDs")
    for control_id in target_ids:
        target_control = controls_by_id.get(control_id)
        if target_control is None:
            errors.append(f"release baseline references unknown control {control_id}")
        elif target_control.get("baseline_readiness") == "not_target":
            errors.append(f"release baseline control {control_id} is marked not_target")
    expected_status = (
        "ready"
        if target_ids
        and all(
            controls_by_id.get(item, {}).get("baseline_readiness") == "ready" for item in target_ids
        )
        else "blocked"
    )
    if baseline.get("status") != expected_status:
        errors.append(
            f"release baseline status must be derived as {expected_status!r}, got {baseline.get('status')!r}"
        )
    observed_workflows = matrix.get("observed_workflows", {})
    normalized_observed = (
        {str(name): set(commands) for name, commands in observed_workflows.items()}
        if isinstance(observed_workflows, dict)
        else {}
    )
    if normalized_observed != workflow_truth:
        errors.append(
            f"workflow inventory drift: matrix={normalized_observed} runtime={workflow_truth}"
        )

    if errors:
        raise MatrixError("\n".join(f"- {error}" for error in errors))
    return {
        "gate_ids": gate_ids,
        "gate_names": gate_names,
        "external_gates": external_truth,
        "middlewares": middleware_truth,
        "workflows": workflow_truth,
        "controls_by_id": controls_by_id,
    }


def _effect_label(control: dict[str, Any]) -> str:
    runtime = control["runtime"]
    effects = (
        _gate_effects(str(runtime["gate_id"]))
        if runtime["kind"] == "gate"
        else control.get("effects", [])
    )
    return "; ".join(f"{item['context']}: {item['mode']}" for item in effects)


def _issues(control: dict[str, Any]) -> str:
    values = control.get("issues", [])
    return ", ".join(f"#{value}" for value in values) if values else "—"


def render(matrix: dict[str, Any]) -> str:
    truth = validate(matrix)
    baseline = matrix["release_baseline"]
    qualification = matrix["reference_qualification"]
    qualification_release = (
        f"`{qualification['qualified_release']}`"
        if qualification.get("qualified_release")
        else "**keiner**"
    )
    controls_by_id = truth["controls_by_id"]
    lines = [
        "# S.A.M.U.E.L. Capability-/Wirksamkeitsmatrix",
        "",
        "> Diese Datei wird aus `docs/capabilities/control-matrix.json` erzeugt.",
        "> Code und ausgelieferte Konfiguration bleiben die Quellen für Verhalten und",
        "> Aktivierung; die Matrix ist die Quelle für Bewertung und öffentliche Claims.",
        "",
        f"**Auditdatum:** {matrix['audit']['date']}",
        f"**Geprüfter Ausgangscommit:** `{matrix['audit']['baseline_commit']}`",
        f"**Geprüfter Quelldigest:** `{matrix['audit']['source_digest']}`",
        f"**Schema:** `{matrix['schema_version']}`",
        "",
        "## Statusmodell",
        "",
        "`lifecycle` beschreibt Existenz und Reife. Die effektive Wirkung wird getrennt",
        "je realem Profil oder Pfad als `enforced`, `advisory`, `telemetry`, `disabled`",
        "oder `not_applicable` geführt. Ein registrierter oder als `required`",
        "konfigurierter Name ist deshalb noch kein Wirksamkeitsnachweis.",
        "",
        "## Reale Referenzqualification",
        "",
        f"Profil-ID: `{qualification['id']}` · Authority-Issue: "
        f"#{qualification['authority_issue']} · Status: **{qualification['status']}** · "
        f"Qualifizierter Release: {qualification_release}",
        "",
        "Die Proofs der Einzelkontrollen sind automatisierte Code-/Integrationsnachweise. "
        "Die reale Qualification bewertet zusätzlich genau eine externe Installation und "
        "einen vollständigen Paket-/Image-zu-PR-Lauf; beide Aussagen werden nicht "
        "miteinander gleichgesetzt.",
        "",
        "| Belegklasse | Stand |",
        "|---|---|",
        "| Real beobachtet | " + "; ".join(qualification["observed"]) + " |",
        "| Für Qualification fehlt | " + ("; ".join(qualification["missing"]) or "—") + " |",
        "| Bekannte Findings | "
        + (", ".join(f"#{item}" for item in qualification["known_findings"]) or "—")
        + " |",
        "",
        "## First-Release-Baseline",
        "",
        f"Profil-ID: `{baseline['id']}` · Status: **{baseline['status']}** ·",
        "Die Produktversionspolitik #487, konsistente Versionsflächen #489, Release-Gates #490 und die tagbasierte Authority #488 sind umgesetzt; die Dachabnahme #479 ist abgeschlossen. `v2.0.0a1` blieb nach roter Tag-CI unveröffentlicht; das veröffentlichte `v2.0.0a2` ist der strikte SCM-Anker. Exakte Tags, Dev-/Dirty-Stände, Phase-Tag-Ausschluss, sdist/wheel und der metadatenlose Nicht-Release-Fallback sind automatisiert geprüft.",
        "",
        "| Kontroll-ID | Kontrolle | Bereitschaft | Blocker |",
        "|---|---|---|---|",
    ]
    for control_id in baseline["controls"]:
        control = controls_by_id[control_id]
        blockers = _issues(control) if control["baseline_readiness"] == "blocked" else "—"
        lines.append(
            f"| `{control_id}` | {control['name']} | **{control['baseline_readiness']}** | {blockers} |"
        )

    class_titles = {
        "input_context": "Input und Kontext",
        "execution": "Ausführung",
        "artifact_commit": "Artefakt und Commit",
        "process_contract": "Prozess und Vertrag",
        "evidence_telemetry": "Evidenz und Telemetrie",
    }
    for class_id, title in class_titles.items():
        class_controls = [item for item in matrix["controls"] if item["class"] == class_id]
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| ID | Präziser Ist-Name | Lifecycle | Tatsächliche Wirkung | Folgeissue |",
                "|---|---|---|---|---|",
            ]
        )
        for control in class_controls:
            lines.append(
                f"| `{control['id']}` | {control['name']} | {control['lifecycle']} | "
                f"{_effect_label(control)} | {_issues(control)} |"
            )

    lines.extend(["", "## Einzelbefunde", ""])
    for control in matrix["controls"]:
        lines.extend(
            [
                f"### `{control['id']}` — {control['name']}",
                "",
                f"- **Schutzziel:** {control['objective']}",
                f"- **Tatsächliches Verhalten:** {control['actual_behavior']}",
                f"- **Fehler/fehlende Daten:** {control['failure_behavior']}",
                f"- **Prüfgegenstand:** {control['subject_binding']}",
                f"- **Evidence:** {control['evidence']}",
                f"- **Vertrauen/Vollständigkeit:** {control['trust_and_data']}",
                f"- **Fundstellen:** {', '.join(f'`{ref}`' for ref in control['references'])}",
                f"- **Issues:** {_issues(control)}",
                "",
            ]
        )
    lines.extend(
        [
            "## Betriebsgrenze",
            "",
            "Der auf diesem Repository nachgewiesene native Gitea-Mergepfad ist externe,",
            "veränderliche Betriebskonfiguration und deshalb kein portabler Code-Nachweis.",
            "Andere Installationen müssen dieselbe Regel konfigurieren und mit `samuel doctor`",
            "vor einer Freigabe sowie nach SCM-/Berechtigungsänderungen erneut nachweisen.",
            "",
        ]
    )
    return "\n".join(lines)


def render_watch_concurrency() -> str:
    truth = _watch_concurrency_truth()
    assert truth["guarded_dispatches"] == 2
    return "\n".join(
        [
            "<!-- docs-contract:watch-concurrency:start -->",
            "Der Watch-Slice verwendet den synchronen `Bus`. Für jedes dispatchte Issue",
            "belegt `WatchHandler._try_acquire()` unmittelbar vor `IssueReady` beziehungsweise",
            "`PlanApproved` einen Slot. Beide Veröffentlichungen stehen in einem eigenen",
            "`try/finally`; `WatchHandler._release()` gibt den Slot beim synchronen Rücklauf",
            "der verschachtelten Bus-Verarbeitung frei.",
            "",
            "Ein einzelner Scan dispatcht die gefundenen Issues damit sequenziell. Die",
            "prozesslokale Semaphore erzeugt keinen Dispatcher und koordiniert keine anderen",
            "S.A.M.U.E.L.-Prozesse. Sie belegt und schützt im unterstützten Modus genau einen",
            "Slot; daraus folgt keine Mehrprozess- oder Workspace-Isolation.",
            "",
            "Es gibt keine Bootstrap-Subscription auf eine feste Liste von Terminalevents und",
            "keine öffentliche `release_slot()`-Methode. Damit hängt die Freigabe im heutigen",
            "synchronen Modell weder von der Vollständigkeit einer Terminalevent-Liste noch von",
            "einem bestimmten Erfolgs- oder Fehlerereignis ab. Ein späterer asynchroner Bus müsste",
            "Slot-Lebensdauer, Ownership und terminale Freigabe neu und explizit entscheiden.",
            "",
            "- Unterstützte In-Process-Watch-Parallelität: exakt `max_parallel = 1`.",
            "- `config/agent.json` und alle ausgelieferten `config/workflows/*.json` setzen `1`.",
            "- Jede Quelle wird einzeln geprüft; Werte ungleich `1` blockieren den Start",
            "  fail-closed und werden nicht durch ein Minimum oder einen Override verborgen.",
            "- Eine spätere Parallelisierung verlangt einen expliziten Dispatcher samt",
            "  Capability-, Schema-, Workspace-/Prozess- und Dokumentationsänderung.",
            "",
            "#573 belegt die synchrone `try/finally`-Freigabe. #614 begrenzt zusätzlich die",
            "dafür zulässige Konfiguration; es deutet den abgeschlossenen Nachweis nicht um.",
            "<!-- docs-contract:watch-concurrency:end -->",
        ]
    )


def render_ac_tag_table() -> str:
    ac = _ac_tag_truth()
    descriptions = {
        "DIFF": (
            "Pfad ist in `RevisionComparison.changed_files`",
            "`[DIFF] tests/test_handler.py`",
        ),
        "EXISTS": ("Pfad existiert im gebundenen Candidate-Checkout", "`[EXISTS] config/app.json`"),
        "GREP": (
            "Pattern existiert repositoryweit in einer unterstützten Code-/Konfigurationsdatei des gebundenen Candidate-Checkouts",
            '`[GREP] "def handle_idempotency"`',
        ),
        "GREP:NOT": (
            "Pattern existiert repositoryweit in keiner unterstützten Code-/Konfigurationsdatei",
            "`[GREP:NOT] 'token = \"legacy\"'`",
        ),
        "IMPORT": (
            "Python-Modul ist im Candidate-Checkout importierbar",
            "`[IMPORT] samuel.slices.foo`",
        ),
        "MANUAL": (
            "benötigt einen gebundenen menschlichen Receipt",
            "`[MANUAL] UI-Verhalten geprüft`",
        ),
        "TEST": (
            "Runner-kompatibler sicherer Selektor läuft mit dem aufgelösten "
            "projektspezifischen Runner",
            "Pytest: `[TEST] tests/test_x.py::test_y`; Unittest: `[TEST] tests.test_x`",
        ),
    }
    if set(descriptions) != set(ac["available"]):
        raise MatrixError(
            "AC tag documentation descriptors drifted: "
            f"described={sorted(descriptions)} runtime={ac['available']}"
        )
    lines = [
        "<!-- docs-contract:ac-tags:start -->",
        "| Tag | Prüfung | Beispiel |",
        "|-----|----------|----------|",
    ]
    for tag in ac["available"]:
        description, example = descriptions[tag]
        lines.append(f"| `[{tag}]` | {description} | {example} |")
    lines.append("<!-- docs-contract:ac-tags:end -->")
    return "\n".join(lines)


def render_plan_complexity_rule() -> str:
    truth = _threshold_truth()
    tags = _ac_tag_truth()["complexity_counted"]
    split_threshold = int(truth["code_defaults"]["planning.complexity"]["pflicht_split"])
    return "\n".join(
        [
            "<!-- docs-contract:plan-complexity:start -->",
            "Die Heuristik zählt genau sechs automatisch prüfbare Tag-Bereiche: "
            + ", ".join(f"`{tag}`" for tag in tags)
            + ". `MANUAL` ist Readiness und zählt nicht als automatischer Bereich.",
            "",
            f"Bei mehr als `{split_threshold}` verschiedenen gezählten Bereichen lautet die "
            "Runtime-Empfehlung `split_recommended`. Mit den ausgelieferten Code-Defaults lösen "
            "damit fünf oder sechs Bereiche die Empfehlung aus. Operatorseitige "
            "`eval.json::plan_complexity`-Werte können den Schwellenwert überschreiben und müssen "
            "für den konkreten Lauf separat nachgewiesen werden.",
            "<!-- docs-contract:plan-complexity:end -->",
        ]
    )


def _persistence_artifact_truth() -> list[dict[str, str]]:
    audit_config = _load_json(ROOT / "config" / "audit.json")
    privacy_config = _load_json(ROOT / "config" / "privacy.json")
    sinks = {
        str(item.get("type")): item
        for item in audit_config.get("sinks", [])
        if isinstance(item, dict) and item.get("type") and item.get("path")
    }
    jsonl = sinks.get("jsonl", {})
    sarif = sinks.get("sarif", {})
    jsonl_path = str(jsonl.get("path", "nicht konfiguriert"))
    rotation = str(jsonl.get("rotation", "none"))
    artifacts = [
        {
            "path": "<data_dir>/idempotency.json",
            "content": "Idempotency-Store",
            "source": "samuel/core/bootstrap.py",
            "provenance": "codegebundener Dateiname",
        },
        {
            "path": "<data_dir>/dlq.jsonl",
            "content": "Dead-Letter-Queue für fehlgeschlagene Subscriber",
            "source": "samuel/core/bootstrap.py",
            "provenance": "codegebundener Dateiname",
        },
        {
            "path": "<data_dir>/samuel-state.sqlite3",
            "content": "versionierte Beobachtungen, Ableitungen, Quality-/Run-Projektionen und Autoritätszustand",
            "source": "samuel/adapters/state/sqlite.py",
            "provenance": "Schema v10; Claims/Checkpoints/Intents/Leases/Restore/Reconcile/Epoch, Retention-Katalog, Kategorie-Autorität und Ausführungsbelege aktiv",
        },
        {
            "path": "<data_dir>/samuel-state-authority.json",
            "content": "synchrone UUID-/Epoch-Hochwassermarke außerhalb des DB-Backup-Artefakts",
            "source": "samuel/adapters/state/sqlite.py",
            "provenance": "0600, atomar ersetzt; Abweichung führt in Reconcile",
        },
        {
            "path": "<data_dir>/.samuel-state-authority.lock",
            "content": "lokaler Mehrprozess-Lock für monotone Witness-Synchronisierung",
            "source": "samuel/adapters/state/sqlite.py",
            "provenance": "0600; Laufzeit-Lock, kein Backup- oder Autoritätsartefakt",
        },
        {
            "path": str(
                privacy_config.get("retention", {}).get("managed_backup_dir", "data/backups")
            ),
            "content": "SQLite-konsistente, registrierte Runtime-State-Backups",
            "source": "config/privacy.json",
            "provenance": "einzige technisch verwaltete Backup-Retentiongrenze; externe Kopien bleiben Betreiberverantwortung",
        },
        {
            "path": jsonl_path,
            "content": (
                f"Audit-Trail; ausgelieferte Rotation `{rotation}`; bei gesetztem HMAC-Key "
                "ein per POSIX-`flock` serialisierter Dateikopf für alle lokalen Prozesse"
            ),
            "source": "config/audit.json",
            "provenance": "ausgeliefert konfiguriert; signierte Appends verweigern beschädigte Tails",
        },
        {
            "path": f"{jsonl_path}.fallback",
            "content": (
                "synchroner Audit-Fallback bei Queue-Überlauf oder Schreibfehler; "
                "eigenständige Kette, kein Vollständigkeitsnachweis für das Haupttranskript"
            ),
            "source": "samuel/core/bootstrap.py",
            "provenance": ("aus konfiguriertem JSONL-Pfad abgeleitet und separat zu verifizieren"),
        },
        {
            "path": str(sarif.get("path", "nicht konfiguriert")),
            "content": "SARIF-Findings-Export",
            "source": "config/audit.json",
            "provenance": "ausgeliefert konfiguriert",
        },
        {
            "path": "<data_dir>/score_history.json.migrated-<sha256>",
            "content": "checksumarchivierte ungebundene Legacy-Eval-History",
            "source": "samuel/adapters/state/legacy.py",
            "provenance": "einseitiger Import; kein aktiver Runtime-Writer",
        },
        {
            "path": "<data_dir>/eval_baselines.json.migrated-<sha256>",
            "content": "checksumarchivierte High-Water-Legacywerte ohne Runtime-Autorität",
            "source": "samuel/adapters/state/legacy.py",
            "provenance": "einseitiger Import als Legacy-Projektion",
        },
        {
            "path": "<data_dir>/evaluation_observations.json.migrated-<sha256>",
            "content": "checksumarchivierte gebundene Legacy-Beobachtungen und Ableitungen",
            "source": "samuel/adapters/state/legacy.py",
            "provenance": "einseitiger Import; aktive Daten liegen in SQLite",
        },
        {
            "path": "<data_dir>/bound_healing_attempts.json.migrated-<sha256>",
            "content": "checksumarchivierter früherer At-most-once-Nachweis",
            "source": "samuel/adapters/state/legacy.py",
            "provenance": "Claims liegen nach einseitigem Import in SQLite",
        },
        {
            "path": "<data_dir>/quality_metrics.json.migrated-<sha256>",
            "content": "checksumarchivierte Legacy-EWMA je Provider, Modell und Task",
            "source": "samuel/adapters/state/legacy.py",
            "provenance": "einseitiger Import; aktive Serienprojektion liegt in SQLite",
        },
        {
            "path": "<data_dir>/scm_activity_poll.json",
            "content": "Cursor für optionales SCM-Activity-Polling",
            "source": "samuel/slices/watch/handler.py",
            "provenance": "codegebundener Dateiname, featureabhängig",
        },
        {
            "path": "<work_dir>/workspaces.sqlite3",
            "content": "lokale Registry für Run-/Verifikations-Worktrees und Quarantäne",
            "source": "samuel/adapters/workspace/git.py",
            "provenance": "getrennt von data_dir und vom State-Backup ausgeschlossen",
        },
        {
            "path": "<work_dir>/trees/",
            "content": "mutierbare Run- und detached Verifikations-Worktrees",
            "source": "samuel/adapters/workspace/git.py",
            "provenance": "unvertrauenswürdiger Candidatezustand; kein Backup-Artefakt",
        },
        {
            "path": "<work_dir>/locks/",
            "content": "prozessunabhängige Branch-/Workspace-flock-Dateien",
            "source": "samuel/adapters/workspace/git.py",
            "provenance": "lokale Ownership-Evidence; kein Sandbox-Ersatz",
        },
    ]
    for artifact in artifacts:
        path = artifact["path"]
        if path == "nicht konfiguriert":
            raise MatrixError(f"required shipped audit sink is absent: {artifact['content']}")
    return artifacts


def render_persistence_artifacts() -> str:
    lines = [
        "<!-- docs-contract:persistence-artifacts:start -->",
        "| Verzeichnis/Datei | Inhalt | Herkunft |",
        "|---|---|---|",
    ]
    for artifact in _persistence_artifact_truth():
        lines.append(
            f"| `{artifact['path']}` | {artifact['content']} | "
            f"`{artifact['source']}`; {artifact['provenance']} |"
        )
    lines.append("<!-- docs-contract:persistence-artifacts:end -->")
    return "\n".join(lines)


def _gate_profile_rows() -> list[str]:
    rows: list[str] = []
    for path in sorted((ROOT / "config").glob("gates*.json")):
        value = _load_json(path)
        profile = "default" if path.name == "gates.json" else path.stem.removeprefix("gates.")
        parameters = ", ".join(
            f"`{key}={value}`" for key, value in sorted(value.get("parameters", {}).items())
        )
        rows.append(
            f"| `{profile}` | `{value.get('policy_version')}` | "
            f"{', '.join(f'`{item}`' for item in value.get('required', [])) or '—'} | "
            f"{', '.join(f'`{item}`' for item in value.get('optional', [])) or '—'} | "
            f"{', '.join(f'`{item}`' for item in value.get('disabled', [])) or '—'} | "
            f"{parameters or '—'} |"
        )
    return rows


def _gate_sort_key(gate_id: str) -> tuple[int, str]:
    match = re.fullmatch(r"([0-9]+)(.*)", gate_id)
    return (int(match.group(1)), match.group(2)) if match else (sys.maxsize, gate_id)


def render_runtime_reference() -> str:
    from samuel.core.gate_metadata import (
        EVALUATION_OBSERVATION_SCHEMA_VERSION,
        GATE_RESULT_SCHEMA_VERSION,
        PRE_FLIGHT_GATE_IDS,
    )
    from samuel.core.retention import RetentionPolicyConfig

    inventory = _runtime_inventory_truth()
    gate_ids, gate_names = _gate_truth()
    ac = _ac_tag_truth()
    thresholds = _threshold_truth()
    verifier_environment = _verifier_environment_truth()
    workflows = _workflow_steps_truth()
    watch = _watch_concurrency_truth()
    artifacts = _persistence_artifact_truth()
    agent_config = _load_json(ROOT / "config" / "agent.json")
    RetentionPolicyConfig.load(ROOT / "config" / "privacy.json", project_root=ROOT)
    privacy_config = _load_json(ROOT / "config" / "privacy.json")
    retention = privacy_config.get("retention", {})
    retention_categories = retention.get("categories", {})
    retention_profiles = retention.get("profiles", {})
    workspace = agent_config.get("workspace", {})
    if not isinstance(workspace, dict):
        raise MatrixError("config/agent.json#/workspace must be an object")

    lines = [
        "# S.A.M.U.E.L. — Generierte Runtime-Referenz",
        "",
        "> Diese Datei wird durch `python tools/control_matrix.py render` aus Code und",
        "> ausgelieferter Konfiguration erzeugt. Nicht manuell bearbeiten. Sie beschreibt",
        "> verfügbare und ausgelieferte Fakten; operatorseitige Overrides bestimmen den",
        "> effektiv aktiven Zustand und müssen für den konkreten Betrieb separat nachgewiesen",
        "> werden. Wirksamkeitsbewertungen bleiben in `docs/CAPABILITY_MATRIX.md`.",
        "",
        "## Quellen- und Statusmodell",
        "",
        "- **Verfügbar:** Registry, Schema oder produktiver Code stellt die Fähigkeit bereit.",
        "- **Konfiguriert:** eine ausgelieferte Config beziehungsweise ein Workflow wählt Werte.",
        "- **Effektiv aktiv:** ausgewähltes Profil plus operatorseitige Overrides; nicht aus dem",
        "  Repository allein ableitbar.",
        "",
        "Ein Code-Default wird ausdrücklich als Default und nicht als ausgelieferter oder",
        "effektiv aktiver Wert ausgegeben.",
        "",
        "## Runtime-Inventar",
        "",
        "| Artefaktklasse | Verfügbar im Code |",
        "|---|---:|",
        f"| Commands | {inventory['commands']} |",
        f"| Events | {inventory['events']} |",
        f"| Ports | {inventory['ports']} |",
        f"| Slices | {inventory['slices']} |",
        f"| Adapter-Gruppen | {inventory['adapter_groups']} |",
        f"| Core-Module einschließlich Paketmodul | {inventory['core_modules']} |",
        "",
        "## AC-Tags",
        "",
        "Verifier-Registry und Planner-Zulassung müssen exakt dieselbe Menge enthalten:",
        "",
        f"`{', '.join(ac['available'])}`",
        "",
        "| Tag | Planner | Plan-Dry-Run | Gebundene Beobachtung | Direkte Kompatibilitätsfamilien |",
        "|---|---|---|---|---|",
    ]
    for tag in ac["available"]:
        families = [name for name, tags in ac["score_families"].items() if tag in set(tags)]
        if tag in ac["hallucination_tags"]:
            families.append("hallucination_free")
        bound_category = ac["bound_categories"].get(tag)
        rendered_bound_category = f"`{bound_category}`" if bound_category else "keine"
        lines.append(
            f"| `[{tag}]` | zugelassen | "
            f"{'deferred' if tag in ac['plan_deferred'] else 'ausgeführt'} | "
            f"{rendered_bound_category} | "
            f"{', '.join(f'`{name}`' for name in families) or 'keine'} |"
        )
    lines.extend(
        [
            "",
            "Die Plan-Komplexitätsheuristik zählt ausschließlich: "
            + ", ".join(f"`{tag}`" for tag in ac["complexity_counted"])
            + ".",
            "",
            "`GREP` und `GREP:NOT` sind repositoryweite Textprüfungen über die unterstützten",
            "Code-/Konfigurationsdateien des gebundenen Candidate-Checkouts. Sie besitzen",
            "kein Pfadargument. Nach einem gequoteten Pattern sind nur Zeilenende oder ein",
            "eindeutiger Beschreibungstrenner zulässig; ein scheinbarer Pfadsuffix blockiert",
            "den neuen Contract vor `PlanPosted`. Der äußere Pattern-Delimiter darf doppelt",
            "oder einfach sein; enthält das Pattern eine Art Anführungszeichen, wird die andere",
            "außen verwendet. Backslash-Escapes für den äußeren Delimiter sind nicht Teil der",
            "Grammatik. Enthält das Pattern beide Arten oder ist Verhalten dateigebunden, ist",
            "ein fokussiertes `[TEST]`-Kriterium zu verwenden.",
            "",
            "Ein `[TEST]`-Argument ist entweder ein sicherer logischer Testname oder ein",
            "sicherer Pytest-Node-ID mit mindestens einem `::`-Segment. Bloße Dateipfade",
            "sind kein portabler Selektor für die unterstützten projektspezifischen Runner",
            "und werden bereits vor `PlanPosted` abgelehnt. Es gibt keinen stillen",
            "Full-Suite- oder Runner-Fallback.",
            "",
            "Zusätzlich muss der Selektor zur vor dem Plan aufgelösten einzelnen",
            "Runner-Authority passen. Planning prüft ohne Testausführung: explizites",
            "Control-Plane-`test_cmd` vor Marker, vorhandenes Binary beziehungsweise",
            "Python-Modul und bekannte Selektorgrammar. Unittest verlangt einen gepunkteten",
            "Python-Namen; Pytest-Node-IDs sind nur mit einem Pytest-Runner und direkter",
            "Positionsbindung von `{test}` zulässig. Fehlende oder inkompatible Readiness",
            "blockiert nach dem einzigen Retry vor `PlanPosted`. Doctor verwendet dieselbe",
            "Auflösung; keiner der beiden Pfade installiert, ersetzt oder startet einen Runner.",
            "",
            "## Gates und ausgelieferte Profile",
            "",
            "### Verfügbare Gates",
            "",
            "| ID | Registry-Name |",
            "|---|---|",
        ]
    )
    for gate_id in sorted(gate_ids, key=_gate_sort_key):
        lines.append(f"| `{gate_id}` | {gate_names[gate_id]} |")
    lines.extend(
        [
            "",
            "### Konfigurierte Profile",
            "",
            "| Profil | Policy | Required | Optional | Disabled | Parameter |",
            "|---|---|---|---|---|---|",
            *_gate_profile_rows(),
            "",
            "Ausgeliefert wird ausschließlich der gebundene Gate-Autoritätspfad.",
            "Ein Authority-Schalter und ein Legacy-Profil existieren nicht mehr; veraltete",
            "Authority-Settings blockieren den Bootstrap. Nicht-Self-Läufe erlauben",
            "`default` oder `audit`; Self erzwingt unabhängig von `SAMUEL_GATES_PROFILE`",
            "das eigene Profil. Andere explizite Werte blockieren vor dem Bus-Wiring.",
            "Ein Eintrag in `required` belegt allein noch keine Subject-Bindung oder Wirksamkeit;",
            "dafür ist die Capability-/Wirksamkeitsmatrix maßgeblich.",
            "",
            f"GateResult-Schema `{GATE_RESULT_SCHEMA_VERSION}`, Observation-Schema "
            f"`{EVALUATION_OBSERVATION_SCHEMA_VERSION}`. Statische Preflight-Gates: "
            + ", ".join(
                f"`{gate_id}`"
                for gate_id in sorted(
                    PRE_FLIGHT_GATE_IDS,
                    key=lambda value: _gate_sort_key(str(value)),
                )
            )
            + ". Bei einem Required-Preflight-Fehler werden alle nachgelagerten "
            "internen und externen Gates als `skipped_precondition` geführt; "
            "Candidate-Verifikation wird nicht gestartet. Jedes v2-Resultat bindet "
            "außerdem einen kanonischen Reason-Code, Required-/Optional-Authority und "
            "denselben EvaluationSubject.",
            "",
            "## Schwellen und Gewichtungen",
            "",
            "| Wert | Herkunft | Status |",
            "|---|---|---|",
            f"| Eval-Baseline `{thresholds['code_defaults']['eval.baseline']}` | `EvalSchema` | unverdrahteter Kompatibilitätscode; keine Runtime-Autorität |",
            f"| Eval-Baseline `{thresholds['shipped_eval']['baseline']}` | `config/eval.json` | passive Scoring-Konfiguration; weder Subject-Digest noch Runtime-Autorität |",
            "",
            f"Scoring-Policy `{thresholds['shipped_eval']['policy_version']}`, Formel "
            f"`{thresholds['shipped_eval']['formula_version']}`. Ausgelieferte Gewichte: "
            + ", ".join(
                f"`{name}={value}`"
                for name, value in sorted(thresholds["shipped_eval"]["weights"].items())
            )
            + ".",
            "",
            "TEST-Runner-Policy "
            f"`{thresholds['shipped_eval']['test_policy_version']}`: "
            f"`test_cmd={thresholds['shipped_eval']['test_cmd']!r}`, "
            f"`test_timeout={thresholds['shipped_eval']['test_timeout']}` Sekunden. "
            "Sie stammt aus dem Bootstrap-Control-Plane-Snapshot und ihr Runner-Teil "
            "bindet den EvaluationSubject-Policy-Digest; Candidate-Konfiguration ist "
            "keine Policyquelle.",
            "",
            f"Candidate-Prozessumgebung `{verifier_environment['profile']}`: ausschließlich "
            + ", ".join(f"`{name}`" for name in verifier_environment["keys"])
            + ". HOME/TMP/XDG werden je Prozess managerseitig neu erzeugt; PATH besteht "
            "aus Interpreter-, festen System- und gegebenenfalls absolut konfigurierten "
            "Runner-Verzeichnissen. Parent-Environment und Benutzerprofile werden nicht "
            "übernommen. Das ist Environment-Härtung, keine Dateisystem-, Prozess- oder "
            "Netzwerksandbox.",
            "",
            "Unverdrahtetes Kompatibilitäts-Fail-Fast (nicht autoritativ): "
            + (
                ", ".join(f"`{value}`" for value in thresholds["shipped_eval"]["fail_fast_on"])
                or "keines"
            )
            + ".",
            "",
            "Gate 4 und Gate 10 sind aus Registry, Schema und Profilen entfernt.",
            "Ausschließlich die Required-Gates des gewählten Profils treffen die",
            "Freigabeentscheidung.",
            "",
            "## Worktree-Lifecycle",
            "",
            "Ein gemeinsamer `IWorkspaceManager` stellt zwei Profile bereit: einen",
            "branch- und rungebundenen, mutierbaren Run-Worktree sowie einen detached",
            "Verifikations-Worktree für den exakten Candidate-Head. Gebundenes Healing",
            "verwendet denselben aktiven Run-Worktree reentrant; Gate 11 verwendet das",
            "Verifikationsprofil. Der Manager erzwingt Git-Ziel-, Ownership-, Kapazitäts-",
            "und Quarantänegrenzen, ist aber ausdrücklich keine Prozesssandbox.",
            "",
            f"Ausgeliefertes `work_dir`: `{workspace.get('work_dir')}`; konservative Buchung "
            f"`{workspace.get('reserve_mebibytes')} MiB`, Mindestfreiraum "
            f"`{workspace.get('minimum_free_mebibytes')} MiB`, Quarantänegrenzen "
            f"`{workspace.get('quarantine_max_count')}` Einträge / "
            f"`{workspace.get('quarantine_max_mebibytes')} MiB`; Operatorfrist "
            f"`{workspace.get('quarantine_retention_hours')} Stunden`. Der relative Pfad wird "
            "vom Installationsroot aus aufgelöst und muss auf einem lokalen Dateisystem "
            "außerhalb von Repository und `data_dir` liegen. Effektive Betreiberwerte "
            "sind separat nachzuweisen.",
            "",
            "## Persistente Laufzeitartefakte",
            "",
            "| Pfad | Inhalt | Herkunft |",
            "|---|---|---|",
            *[
                f"| `{artifact['path']}` | {artifact['content']} | "
                f"`{artifact['source']}`; {artifact['provenance']} |"
                for artifact in artifacts
            ],
            "",
            "Eine Dateiexistenz belegt noch keine ausreichende Retention, Neustartfestigkeit",
            "oder Backup-/Restore-Policy. Stufe 5b liefert Report, Managed Backup und Replay;",
            "das 5c-Fundament ist ausschließlich operatorgeführt und ausgeliefert deaktiviert.",
            "",
            "## Retention Stufe 5b und deaktiviertes 5c-Fundament",
            "",
            f"Schema `{retention.get('schema_version')}`, ausgeliefertes Profil "
            f"`{retention.get('active_profile')}`, Operatorrolle "
            f"`{retention.get('operator_role')}`, Managed-Backup-Grenze "
            f"`{retention.get('managed_backup_dir')}`. Die globale Notabschaltung ist im "
            "State gespeichert und nicht Teil eines Policy-Digests. Alle ausgelieferten "
            "Kategorien bleiben `report_only`; es gibt keinen Scheduler und keine aktive "
            "Löschkategorie.",
            "",
            "| Profil | Rolle | Kategorie-Untergrenzen |",
            "|---|---|---|",
            *[
                f"| `{name}` | `{profile.get('role')}` | "
                + (
                    ", ".join(
                        f"`{category}={period}`"
                        for category, period in sorted(profile.get("minimums", {}).items())
                    )
                    or "keine"
                )
                + " |"
                for name, profile in sorted(retention_profiles.items())
            ],
            "",
            "| Kategorie | Speicher/Quelle | Modus | Zeitraum | Anker |",
            "|---|---|---|---|---|",
            *[
                f"| `{name}` | `{category.get('storage')}` / `{category.get('source')}` | "
                f"`{category.get('mode')}` | "
                f"`{category.get('period')}` | `{category.get('anchor')}` |"
                for name, category in sorted(retention_categories.items())
            ],
            "",
            "`samuel retention dry-run --json` berechnet absolute UTC-Cutoffs und",
            "Schutzgründe ohne Mutation. Für die einzige registrierte Strategie",
            "`score_derivations` bindet der Report zusätzlich Cutoff, Anker, die",
            "Plan-Schemaserie `retention-execution-plan.v1`, den klassifizierten",
            "Schutzvertrag und privacy-sichere Objektidentitäten des aktuell",
            "ungeschützten Kandidatensatzes in einem Plan-Digest. `approve` bindet eine",
            "Kategorie an ihre aktuellen Kategorie- und Profil-/Rollendigests. `activate`",
            "bindet außerdem den zulässigen absoluten Cutoff an den serverseitigen",
            "Aktivierungszeitpunkt. `execute` revalidiert diese Grantbindung sowie Katalog,",
            "Klassifikation und Kandidaten unmittelbar in der Löschtransaktion. Ein",
            "historischer Receipt kann identitätsgeprüft ohne neue Wirkung auch nach Stop-",
            "oder Policyänderungen gelesen werden. `execute`, `suspend`, `pause` und",
            "`unpause` sind explizite Operatoraktionen; kein Hintergrundpfad ruft Vollzug",
            "auf. `backup` verwendet die",
            "SQLite Backup API innerhalb der verwalteten Grenze. `replay-scores`",
            "publiziert keine Events und aktualisiert keine Quality-EWMA. Diese",
            "Betriebsdefaults sind keine universellen Rechtsfristen oder",
            "Konformitätszusage; externe Backupkopien bleiben Betreiberverantwortung.",
            "",
            "## Workflowübergänge",
            "",
            "| Workflow | Gebundener Gate-Autoritätspfad |",
            "|---|---|",
        ]
    )
    for name, steps in workflows.items():
        chain = "<br>".join(
            f"`{step['on']} → {step['send']}`"
            + (f" (`{step['condition']}`)" if step.get("condition") else "")
            for step in steps
        )
        lines.append(f"| `{name}` | {chain} |")
    lines.extend(
        [
            "",
            "## Watch-Concurrency",
            "",
            f"Busmodus: **{watch['bus_mode']}**. Acquire: `{watch['acquire_method']}`. "
            f"Release: `{watch['release_method']}`.",
            "",
            "Der Slot wird in zwei synchronen Dispatchpfaden per `try/finally` freigegeben. Es",
            "existiert keine Terminalevent-Subscription für diese Freigabe. Die ausführliche",
            "Architekturbeschreibung in §5.4 wird aus demselben geprüften Vertrag erzeugt.",
            "Der Scan dispatcht **sequenziell**, die Koordination ist",
            "**prozesslokal**, und alle ausgelieferten Profile erlauben",
            f"ausschließlich `max_parallel={watch['supported_max_parallel']}`. Höhere Werte",
            "blockieren den Start; mehrere Prozesse werden nicht koordiniert.",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_adr(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise MatrixError(f"ADR front matter is missing: {path.relative_to(ROOT)}")
    raw_header, body = text[4:].split("\n---\n", 1)
    metadata: dict[str, Any] = {}
    for line in raw_header.splitlines():
        key, separator, raw_value = line.partition(":")
        if not separator:
            raise MatrixError(f"invalid ADR front matter in {path.relative_to(ROOT)}: {line}")
        value = raw_value.strip()
        if value.startswith("["):
            try:
                metadata[key.strip()] = json.loads(value)
            except json.JSONDecodeError as exc:
                raise MatrixError(f"invalid ADR list in {path.relative_to(ROOT)}: {line}") from exc
        else:
            metadata[key.strip()] = value
    metadata["path"] = path.relative_to(ROOT).as_posix()
    metadata["body"] = body
    return metadata


def _adr_decision_digest(body: str) -> str:
    normalized = body.replace("\r\n", "\n").strip().encode("utf-8")
    return f"sha256:{hashlib.sha256(normalized).hexdigest()}"


def _adr_truth() -> list[dict[str, Any]]:
    adrs = [
        _parse_adr(path)
        for path in sorted((ROOT / "docs" / "adr").glob("*.md"))
        if path != ADR_INDEX_PATH
    ]
    ids = [str(item.get("id", "")) for item in adrs]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"ADR-[0-9]{4}", item) for item in ids):
        raise MatrixError(f"ADR IDs must be unique ADR-NNNN values: {ids}")
    by_id = {str(item["id"]): item for item in adrs}
    allowed_statuses = {"proposed", "accepted", "superseded", "rejected"}
    for adr in adrs:
        missing = [
            field
            for field in (
                "id",
                "title",
                "status",
                "decision_issue",
                "decision_date",
                "decision_digest",
            )
            if not str(adr.get(field, "")).strip()
        ]
        if missing:
            raise MatrixError(f"{adr.get('path')}: missing ADR fields {missing}")
        if adr["status"] not in allowed_statuses:
            raise MatrixError(f"{adr['id']}: invalid ADR status {adr['status']!r}")
        expected_digest = _adr_decision_digest(str(adr["body"]))
        if adr["decision_digest"] != expected_digest:
            raise MatrixError(
                f"{adr['id']}: decision body changed; reviewed digest is {expected_digest}"
            )
        supersedes = adr.get("supersedes", [])
        superseded_by = adr.get("superseded_by", [])
        if not isinstance(supersedes, list) or not isinstance(superseded_by, list):
            raise MatrixError(f"{adr['id']}: supersession fields must be lists")
        for other_id in [*supersedes, *superseded_by]:
            if other_id not in by_id:
                raise MatrixError(f"{adr['id']}: unknown ADR supersession target {other_id}")
        if adr["status"] == "superseded" and not superseded_by:
            raise MatrixError(f"{adr['id']}: superseded ADR requires superseded_by")
    return adrs


def render_adr_index() -> str:
    lines = [
        "# Architecture Decision Records",
        "",
        "> Diese Datei wird durch `python tools/control_matrix.py render` aus den",
        "> versionierten ADR-Dateien erzeugt. Akzeptierte Entscheidungen werden nicht",
        "> still umgeschrieben, sondern durch einen neuen ADR abgelöst.",
        "",
        "| ADR | Entscheidung | Status | Issue | Datum |",
        "|---|---|---|---:|---|",
    ]
    for adr in _adr_truth():
        path = Path(str(adr["path"]))
        lines.append(
            f"| [`{adr['id']}`]({path.name}) | {adr['title']} | `{adr['status']}` | "
            f"#{adr['decision_issue']} | {adr['decision_date']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _replace_generated_block(text: str, block_id: str, rendered: str) -> str:
    start_marker = f"<!-- docs-contract:{block_id}:start -->"
    end_marker = f"<!-- docs-contract:{block_id}:end -->"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < start:
        raise MatrixError(f"generated documentation block {block_id!r} is missing")
    end += len(end_marker)
    return text[:start] + rendered + text[end:]


def _markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    for explicit in re.findall(r"<(?:a|span)\s+(?:id|name)=[\"']([^\"']+)[\"']", text):
        anchors.add(explicit)
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, flags=re.MULTILINE):
        plain = re.sub(r"<[^>]+>", "", heading)
        plain = re.sub(r"[`*~]", "", plain).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", plain, flags=re.UNICODE)
        slug = re.sub(r"\s", "-", slug).strip("-")
        occurrence = counts.get(slug, 0)
        counts[slug] = occurrence + 1
        anchors.add(f"{slug}-{occurrence}" if occurrence else slug)
    return anchors


def _validate_document_links(paths: set[str]) -> list[str]:
    errors: list[str] = []
    markdown_link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    repository_path = re.compile(r"`((?:docs|technische Beschreibungen)/[^`\n]+?\.md)(?:#[^`]*)?`")
    for path_text in sorted(paths):
        path = ROOT / path_text
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        for target in markdown_link.findall(prose):
            raw_target = target.strip().strip("<>")
            cleaned, _, anchor = raw_target.partition("#")
            cleaned = cleaned.replace("%20", " ")
            if "://" in cleaned or cleaned.startswith(("mailto:", "/")):
                continue
            resolved = path if not cleaned and anchor else (path.parent / cleaned).resolve()
            if not cleaned and not anchor:
                continue
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{path_text}: Markdown target escapes repository {target}")
                continue
            if not resolved.exists():
                errors.append(f"{path_text}: missing Markdown target {target}")
            elif anchor and resolved.suffix.lower() == ".md":
                normalized_anchor = anchor.lower().replace("%20", "-")
                if normalized_anchor not in _markdown_anchors(resolved):
                    errors.append(f"{path_text}: missing Markdown anchor {target}")
        for target in repository_path.findall(prose):
            if not (ROOT / target).is_file():
                errors.append(f"{path_text}: missing repository document `{target}`")
    return errors


def validate_document_contract(contract: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if contract.get("schema_version") != "1.0":
        errors.append("document contract schema_version must be 1.0")
    if contract.get("generator_version") != "1.0":
        errors.append("document contract generator_version must be 1.0")
    documents = contract.get("documents")
    if not isinstance(documents, list):
        errors.append("document contract documents must be a list")
        documents = []
    classified: set[str] = set()
    for document in documents:
        if not isinstance(document, dict):
            errors.append("every document classification must be an object")
            continue
        path_text = str(document.get("path", ""))
        if not path_text or path_text in classified:
            errors.append(f"duplicate or empty document classification: {path_text!r}")
            continue
        classified.add(path_text)
        if document.get("class") not in DOCUMENT_CLASSES:
            errors.append(f"{path_text}: invalid document class {document.get('class')!r}")
        if document.get("mode") not in DOCUMENT_MODES:
            errors.append(f"{path_text}: invalid document mode {document.get('mode')!r}")
        if document.get("status", contract.get("active_document_status")) != "active":
            errors.append(f"{path_text}: active document status must be 'active'")
        if not (ROOT / path_text).is_file():
            errors.append(f"classified active document does not exist: {path_text}")
    active = _document_contract_paths()
    if classified != active:
        errors.append(
            f"document classification drift: manifest={sorted(classified)} runtime={sorted(active)}"
        )

    generators: dict[str, dict[str, str]] = {
        "runtime_reference": {
            "document": RUNTIME_REFERENCE_PATH.relative_to(ROOT).as_posix(),
            "rendered": render_runtime_reference(),
        },
        "watch_concurrency": {
            "document": "docs/SAMUEL_ARCHITECTURE_V2.1.md",
            "rendered": render_watch_concurrency(),
        },
        "ac_tags": {
            "document": "docs/README_technical.md",
            "rendered": render_ac_tag_table(),
        },
        "plan_complexity": {
            "document": "docs/OPERATING_RULES.md",
            "rendered": render_plan_complexity_rule(),
        },
        "persistence_artifacts": {
            "document": "docs/README_technical.md",
            "rendered": render_persistence_artifacts(),
        },
        "adr_index": {
            "document": ADR_INDEX_PATH.relative_to(ROOT).as_posix(),
            "rendered": render_adr_index(),
        },
    }
    sections = contract.get("sections")
    if not isinstance(sections, list):
        errors.append("document contract sections must be a list")
        sections = []
    seen_sections: set[str] = set()
    configured_generators: set[str] = set()
    generated_sections: dict[str, dict[str, Any]] = {}
    section_defaults = contract.get("section_defaults", {})
    if not isinstance(section_defaults, dict):
        errors.append("document contract section_defaults must be an object")
        section_defaults = {}
    for section in sections:
        if not isinstance(section, dict):
            errors.append("every document section contract must be an object")
            continue
        section_id = str(section.get("id", ""))
        if not section_id or section_id in seen_sections:
            errors.append(f"duplicate or empty document section id: {section_id!r}")
            continue
        seen_sections.add(section_id)
        mode = section.get("mode")
        document = str(section.get("document", ""))
        sources = section.get("sources", [])
        if document not in classified:
            errors.append(f"{section_id}: section document is not classified: {document}")
        if mode not in DOCUMENT_MODES:
            errors.append(f"{section_id}: invalid section mode {mode!r}")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{section_id}: sources are required")
            sources = []
        else:
            for source in sources:
                if not isinstance(source, dict):
                    errors.append(f"{section_id}: source must be an object")
                    continue
                try:
                    _selected_source(source)
                except MatrixError as exc:
                    errors.append(f"{section_id}: {exc}")
        proofs = section.get("proofs")
        if not isinstance(proofs, list) or not proofs:
            errors.append(f"{section_id}: proofs are required")
        else:
            for proof in proofs:
                try:
                    _validate_reference(section_id, str(proof))
                except MatrixError as exc:
                    errors.append(str(exc))
        owner = section.get("owner", section_defaults.get("owner"))
        review_status = section.get("review_status", section_defaults.get("review_status"))
        review_rule = section.get("review_rule", section_defaults.get("review_rule"))
        if not str(owner or "").strip():
            errors.append(f"{section_id}: owner is required")
        if review_status not in DOCUMENT_REVIEW_STATES:
            errors.append(f"{section_id}: invalid review_status {review_status!r}")
        if not str(review_rule or "").strip():
            errors.append(f"{section_id}: review_rule is required")
        try:
            expected_digest = _contract_source_digest(sources)
        except MatrixError as exc:
            errors.append(f"{section_id}: {exc}")
            expected_digest = ""
        if expected_digest and section.get("source_digest") != expected_digest:
            source_labels = ", ".join(_source_label(item) for item in sources)
            errors.append(
                f"{section_id}: source binding is stale; reviewed digest is "
                f"{expected_digest}; sources=[{source_labels}]; proofs={proofs or []}"
            )
        if mode == "manual":
            heading = str(section.get("heading", "")).strip()
            target_path = ROOT / document
            if not heading or (
                target_path.is_file() and heading not in target_path.read_text(encoding="utf-8")
            ):
                errors.append(f"{section_id}: manual section heading is absent: {heading!r}")
        elif mode == "generated":
            generator = str(section.get("generator", ""))
            configured_generators.add(generator)
            generated_sections[generator] = section
            descriptor = generators.get(generator)
            if descriptor is None:
                errors.append(f"{section_id}: unknown generator {generator!r}")
            elif descriptor["document"] != document:
                errors.append(
                    f"{section_id}: generator {generator!r} targets {descriptor['document']}, not {document}"
                )
    if configured_generators != set(generators):
        errors.append(
            f"generated-section inventory drift: manifest={sorted(configured_generators)} "
            f"runtime={sorted(generators)}"
        )
    for generator, descriptor in generators.items():
        section = generated_sections.get(generator)
        if section is not None:
            descriptor["rendered"] = _bind_generated_rendering(descriptor["rendered"], section)

    if RUNTIME_REFERENCE_PATH.is_file():
        if (
            RUNTIME_REFERENCE_PATH.read_text(encoding="utf-8")
            != generators["runtime_reference"]["rendered"]
        ):
            errors.append("docs/RUNTIME_REFERENCE.md is stale")
    if ADR_INDEX_PATH.is_file():
        if ADR_INDEX_PATH.read_text(encoding="utf-8") != generators["adr_index"]["rendered"]:
            errors.append("docs/adr/README.md is stale")
    architecture_path = ROOT / "docs" / "SAMUEL_ARCHITECTURE_V2.1.md"
    if architecture_path.is_file():
        architecture = architecture_path.read_text(encoding="utf-8")
        try:
            expected = _replace_generated_block(
                architecture,
                "watch-concurrency",
                generators["watch_concurrency"]["rendered"],
            )
            if architecture != expected:
                errors.append("architecture watch-concurrency block is stale")
        except MatrixError as exc:
            errors.append(str(exc))
    for path, block_id, generator in (
        (ROOT / "docs" / "README_technical.md", "ac-tags", "ac_tags"),
        (
            ROOT / "docs" / "README_technical.md",
            "persistence-artifacts",
            "persistence_artifacts",
        ),
        (ROOT / "docs" / "OPERATING_RULES.md", "plan-complexity", "plan_complexity"),
    ):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            expected = _replace_generated_block(text, block_id, generators[generator]["rendered"])
            if text != expected:
                errors.append(f"{path.relative_to(ROOT)} {block_id} block is stale")
        except MatrixError as exc:
            errors.append(str(exc))

    errors.extend(_validate_document_links(classified))
    if errors:
        raise MatrixError("\n".join(f"- {error}" for error in errors))
    return {"documents": classified, "sections": seen_sections}


def render_document_contract(contract: dict[str, Any]) -> None:
    _require_manual_reviews_current(contract)
    refreshed = copy.deepcopy(contract)
    sections = refreshed.get("sections", [])
    generated_sections = {
        str(section.get("generator", "")): section
        for section in sections
        if isinstance(section, dict) and section.get("mode") == "generated"
    }
    for section in generated_sections.values():
        sources = section.get("sources", [])
        if isinstance(sources, list) and sources:
            section["source_digest"] = _contract_source_digest(sources)

    raw_renderings = {
        "runtime_reference": render_runtime_reference(),
        "watch_concurrency": render_watch_concurrency(),
        "ac_tags": render_ac_tag_table(),
        "plan_complexity": render_plan_complexity_rule(),
        "persistence_artifacts": render_persistence_artifacts(),
        "adr_index": render_adr_index(),
    }
    bound_renderings = {
        generator: _bind_generated_rendering(rendered, generated_sections[generator])
        for generator, rendered in raw_renderings.items()
        if generator in generated_sections
    }
    if set(bound_renderings) != set(raw_renderings):
        missing = sorted(set(raw_renderings) - set(bound_renderings))
        raise MatrixError(f"generated document contracts are missing: {missing}")

    DOCUMENT_CONTRACT_PATH.write_text(
        json.dumps(refreshed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    RUNTIME_REFERENCE_PATH.write_text(bound_renderings["runtime_reference"], encoding="utf-8")
    ADR_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADR_INDEX_PATH.write_text(bound_renderings["adr_index"], encoding="utf-8")
    architecture_path = ROOT / "docs" / "SAMUEL_ARCHITECTURE_V2.1.md"
    architecture = architecture_path.read_text(encoding="utf-8")
    architecture_path.write_text(
        _replace_generated_block(
            architecture,
            "watch-concurrency",
            bound_renderings["watch_concurrency"],
        ),
        encoding="utf-8",
    )
    for path, block_id, rendered in (
        (ROOT / "docs" / "README_technical.md", "ac-tags", bound_renderings["ac_tags"]),
        (
            ROOT / "docs" / "README_technical.md",
            "persistence-artifacts",
            bound_renderings["persistence_artifacts"],
        ),
        (
            ROOT / "docs" / "OPERATING_RULES.md",
            "plan-complexity",
            bound_renderings["plan_complexity"],
        ),
    ):
        text = path.read_text(encoding="utf-8")
        path.write_text(_replace_generated_block(text, block_id, rendered), encoding="utf-8")
    validate_document_contract(refreshed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "render", "impact"))
    args = parser.parse_args()
    try:
        matrix = load_matrix()
        contract = load_document_contract()
        if args.command == "impact":
            print(json.dumps(document_contract_impact(contract), ensure_ascii=False, indent=2))
            return 0
        rendered = render(matrix)
        if args.command == "render":
            render_document_contract(contract)
            OUTPUT_PATH.write_text(rendered, encoding="utf-8")
            print(
                "rendered "
                f"{OUTPUT_PATH.relative_to(ROOT)}, "
                f"{RUNTIME_REFERENCE_PATH.relative_to(ROOT)}, "
                f"{ADR_INDEX_PATH.relative_to(ROOT)} and bound fragments"
            )
            return 0
        actual = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if actual != rendered:
            raise MatrixError(
                "docs/CAPABILITY_MATRIX.md is stale; run python tools/control_matrix.py render"
            )
        document_truth = validate_document_contract(contract)
        print(
            f"control matrix valid: {len(matrix['controls'])} controls, "
            f"baseline={matrix['release_baseline']['status']}; "
            f"document contract valid: {len(document_truth['documents'])} documents, "
            f"{len(document_truth['sections'])} bound sections"
        )
        return 0
    except MatrixError as exc:
        print(f"control matrix invalid:\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
