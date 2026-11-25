"""Version-bound advisory mappings; never grant execution or gate authority.

The existing OWASP/AI-Act facades retain their public contracts. New mappings
consume the same package-data loader and can annotate an explicitly selected
scope without reading or changing runtime policy, configuration or evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from samuel.core.evaluation_observation import canonical_digest

COMPLIANCE_DIR = Path(__file__).resolve().parent / "compliance"


def load_definition(path: Path, required: tuple[str, ...]) -> dict[str, Any]:
    """Read one definition only; a broken unselected pack is not imported."""

    label = f"compliance/{path.name}"
    if not path.is_file():
        raise RuntimeError(f"{label} missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} not parsable") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{label} top level must be an object")
    for key in required:
        if key not in data:
            raise RuntimeError(f"{label} missing key: {key}")
    return data


@dataclass(frozen=True)
class MappingDefinition:
    """Immutable mapping snapshot. Digests distinguish changed same-version data."""

    framework: str
    version: str
    mapping_version: str
    source: str
    digest: str
    controls_json: str
    mappings: tuple[tuple[str, str, str], ...]
    fallbacks: tuple[tuple[str, str], ...]

    def reference(self, category: str, event: str) -> str | None:
        for cat, evt, control in self.mappings:
            if (cat, evt) == (category, event):
                return control
        return dict(self.fallbacks).get(category)

    def identity(self) -> dict[str, str]:
        return {
            "framework": self.framework,
            "version": self.version,
            "mapping_version": self.mapping_version,
            "mapping_digest": self.digest,
            "source": self.source,
        }

    def legend(self) -> dict[str, Any]:
        return {**self.identity(), "effect": "advisory", "controls": json.loads(self.controls_json)}

    def annotate(
        self,
        *,
        scope: str,
        selected_scopes: tuple[str, ...],
        evidence_id: str,
        category: str,
        event: str,
    ) -> dict[str, str] | None:
        """Reference existing evidence without copying it or deciding its validity.

        Exact scope selection is supplied by the consumer, never inferred from
        file presence, an event payload or another framework's configuration.
        The returned identity must be persisted with a historical annotation.
        """

        if scope not in selected_scopes:
            return None
        if not scope.strip() or not evidence_id.strip():
            raise ValueError("selected mapping requires scope and evidence identity")
        reference = self.reference(category, event)
        if reference is None:
            return None
        return {
            **self.identity(),
            "scope": scope,
            "evidence_id": evidence_id,
            "control": reference,
            "effect": "advisory",
        }


def load_mapping(
    path: Path,
    *,
    controls_key: str = "controls",
    reference_key: str = "control",
    control_key: str = "id",
) -> MappingDefinition:
    """Load any declarative mapping; no framework-specific execution branches."""

    data = load_definition(
        path,
        (
            "framework",
            "version",
            "mapping_version",
            "source",
            controls_key,
            "mappings",
            "fallbacks",
        ),
    )
    for key in ("framework", "version", "mapping_version", "source"):
        value = data[key]
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise RuntimeError(f"compliance/{path.name} invalid identity: {key}")
    controls = data[controls_key]
    mappings = data["mappings"]
    fallbacks = data["fallbacks"]
    if (
        not isinstance(controls, list)
        or not isinstance(mappings, list)
        or not isinstance(fallbacks, dict)
    ):
        raise RuntimeError(f"compliance/{path.name} invalid mapping collections")
    keys: set[str] = set()
    for item in controls:
        if not isinstance(item, dict) or not isinstance(item.get(control_key), str):
            raise RuntimeError(f"compliance/{path.name} invalid control")
        key = item[control_key]
        if not key.strip() or key in keys:
            raise RuntimeError(f"compliance/{path.name} duplicate or empty control")
        keys.add(key)
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in mappings:
        if not isinstance(row, dict):
            raise RuntimeError(f"compliance/{path.name} invalid mapping row")
        cat, evt, ref = row.get("cat"), row.get("evt"), row.get(reference_key)
        if (
            not isinstance(cat, str)
            or not cat.strip()
            or not isinstance(evt, str)
            or not evt.strip()
            or not isinstance(ref, str)
            or not ref.strip()
        ):
            raise RuntimeError(f"compliance/{path.name} invalid mapping row")
        if ref not in keys or (cat, evt) in seen:
            raise RuntimeError(f"compliance/{path.name} unknown or duplicate mapping")
        rows.append((cat, evt, ref))
        seen.add((cat, evt))
    for cat, ref in fallbacks.items():
        if (
            not isinstance(cat, str)
            or not cat.strip()
            or not isinstance(ref, str)
            or ref not in keys
        ):
            raise RuntimeError(f"compliance/{path.name} invalid fallback")
    try:
        digest = canonical_digest(data)
    except UnicodeError as exc:
        raise RuntimeError(f"compliance/{path.name} invalid text encoding") from exc
    return MappingDefinition(
        framework=data["framework"],
        version=data["version"],
        mapping_version=data["mapping_version"],
        source=data["source"],
        digest=digest,
        controls_json=json.dumps(controls, ensure_ascii=False, sort_keys=True),
        mappings=tuple(rows),
        fallbacks=tuple(sorted(fallbacks.items())),
    )
