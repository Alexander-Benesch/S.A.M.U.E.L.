from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from samuel.core.ports import IPatchApplier


def _normalize_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines())


# #152: ``SLICE: pfad/datei.py:100-200`` — der LLM fordert gezielt Zeilen an.
_SLICE_RE = re.compile(r"SLICE:\s*([A-Za-z0-9_./\-]+):(\d+)\s*-\s*(\d+)")


def parse_slice_requests(text: str) -> list[tuple[str, int, int]]:
    """#152: SLICE-Requests aus dem LLM-Output parsen.

    Liefert ``[(file, start, end), ...]`` (dedupliziert, Reihenfolge erhalten);
    ueberspringt Bereiche mit ``end < start``."""
    out: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()
    for m in _SLICE_RE.finditer(text or ""):
        rel, start, end = m.group(1), int(m.group(2)), int(m.group(3))
        if end < start:
            continue
        key = (rel, start, end)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def parse_patches_structured(data: Any) -> list[dict[str, Any]]:
    """#335: Patches aus validiertem JSON statt aus SEARCH/REPLACE-Freitext.

    Erwartet ``{"patches": [...]}`` oder eine blanke Liste. Jeder Eintrag traegt
    ``file`` + ``type`` und die typ-spezifischen Felder:

    - ``replace_lines``: ``lines: [start, end]``, ``replace: str``
    - ``write``: ``write|content: str``
    - ``search_replace`` (Default): ``search: str``, ``replace: str``

    Liefert die gleiche interne Patch-Dict-Form wie :func:`parse_patches`,
    damit die bestehenden Applier sie unveraendert verarbeiten. Strukturell
    unbrauchbare Eintraege werden uebersprungen (robust gegen LLM-Ausrutscher).
    """
    if isinstance(data, dict):
        items = data.get("patches", [])
    elif isinstance(data, list):
        items = data
    else:
        return []
    patches: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rel = item.get("file")
        if not rel or not isinstance(rel, str):
            continue
        ptype = item.get("type") or "search_replace"
        if ptype == "replace_lines":
            lines = item.get("lines")
            if (
                isinstance(lines, (list, tuple))
                and len(lines) == 2
                and all(isinstance(n, int) for n in lines)
                and isinstance(item.get("replace"), str)
            ):
                patches.append(
                    {
                        "file": rel,
                        "lines": (lines[0], lines[1]),
                        "replace": item["replace"],
                        "type": "replace_lines",
                    }
                )
        elif ptype == "write":
            content = item.get("write", item.get("content"))
            if isinstance(content, str):
                patches.append({"file": rel, "write": content, "type": "write"})
        else:  # search_replace
            if isinstance(item.get("search"), str) and isinstance(item.get("replace"), str):
                patches.append(
                    {
                        "file": rel,
                        "search": item["search"],
                        "replace": item["replace"],
                    }
                )
    return patches


def parse_patches(text: str) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    current_file: str | None = None
    state = "idle"
    search_lines: list[str] = []
    replace_lines: list[str] = []
    write_lines: list[str] = []
    replace_line_range: tuple[int, int] | None = None

    for line in text.splitlines():
        stripped = line.rstrip()

        if state == "idle" and current_file:
            rl_match = re.match(r"REPLACE\s+LINES?\s+(\d+)\s*[-–]\s*(\d+)", stripped)
            if rl_match:
                replace_line_range = (int(rl_match.group(1)), int(rl_match.group(2)))
                state = "replace_lines"
                replace_lines = []
                continue

        if state == "replace_lines":
            if stripped in ("END REPLACE", "END_REPLACE"):
                patches.append(
                    {
                        "file": current_file,
                        "lines": replace_line_range,
                        "replace": "\n".join(replace_lines),
                        "type": "replace_lines",
                    }
                )
                state = "idle"
                replace_lines = []
                replace_line_range = None
            else:
                replace_lines.append(line)
            continue

        if state == "idle" and stripped.startswith("## WRITE: "):
            current_file = stripped[len("## WRITE: ") :].strip()
            state = "write"
            write_lines = []
            continue

        if state == "write":
            if stripped == "## END_WRITE":
                patches.append(
                    {
                        "file": current_file,
                        "write": "\n".join(write_lines),
                        "type": "write",
                    }
                )
                state = "idle"
                write_lines = []
            else:
                write_lines.append(line)
            continue

        if state == "idle" and stripped.startswith("## ") and "." in stripped[3:]:
            current_file = stripped[3:].strip()
        elif stripped == "<<<<<<< SEARCH" and current_file:
            state = "search"
            search_lines = []
        elif stripped == "=======" and state == "search":
            state = "replace"
            replace_lines = []
        elif stripped == ">>>>>>> REPLACE" and state == "replace":
            patches.append(
                {
                    "file": current_file,
                    "search": "\n".join(search_lines),
                    "replace": "\n".join(replace_lines),
                }
            )
            state = "idle"
            search_lines = []
            replace_lines = []
        elif state == "search":
            search_lines.append(line)
        elif state == "replace":
            replace_lines.append(line)

    if state == "write" and write_lines:
        patches.append(
            {
                "file": current_file,
                "write": "\n".join(write_lines),
                "type": "write",
            }
        )

    return patches


class LinePatchApplier(IPatchApplier):
    supported_extensions = {"*"}

    def apply(self, file: Path, patches: list[Any]) -> Any:
        results: list[tuple[bool, str]] = []
        for patch in patches:
            ok, msg = self._apply_one(file, patch)
            results.append((ok, msg))
        return results

    def _apply_one(self, file: Path, patch: dict) -> tuple[bool, str]:
        rel = patch.get("file", "")

        if patch.get("type") == "write":
            content = _normalize_ws(patch["write"])
            content = content + "\n"
            if not self.validate(file, content):
                return False, f"validation failed for {rel}"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
            return True, f"{rel} written"

        new_content, error = self._candidate_content(file, patch)
        if error is not None:
            return False, error
        assert new_content is not None

        if not self.validate(file, new_content):
            return False, f"validation failed for {rel}"

        file.write_text(new_content, encoding="utf-8")
        return True, f"{rel} patched"

    def _candidate_content(
        self,
        file: Path,
        patch: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        """Build a non-WRITE candidate without mutating the target file."""

        rel = patch.get("file", "")
        if not file.exists():
            return None, f"{rel} not found"

        original = file.read_text(encoding="utf-8")

        if patch.get("type") == "replace_lines":
            orig_lines = original.splitlines(keepends=True)
            start, end = patch["lines"]
            if start < 1 or end > len(orig_lines):
                return None, f"line range {start}-{end} out of bounds ({len(orig_lines)} lines)"
            new_replace = _normalize_ws(patch["replace"])
            new_lines = orig_lines[: start - 1] + [new_replace + "\n"] + orig_lines[end:]
            new_content = "".join(new_lines)
        else:
            norm_orig = _normalize_ws(original)
            norm_search = _normalize_ws(patch.get("search", ""))
            if norm_search not in norm_orig:
                return None, f"SEARCH not found in {rel}"
            new_content = norm_orig.replace(norm_search, _normalize_ws(patch.get("replace", "")), 1)
        return new_content, None

    def validate(self, file: Path, content: str) -> bool:
        if file.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError:
                return False
        return True


class JSONPatchApplier(IPatchApplier):
    supported_extensions = {".json"}

    def apply(self, file: Path, patches: list[Any]) -> Any:
        results: list[tuple[bool, str]] = []
        for patch in patches:
            if patch.get("type") == "write":
                content = patch["write"]
                if not self.validate(file, content):
                    results.append((False, f"{patch.get('file', '')} invalid JSON after patch"))
                    continue
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content, encoding="utf-8")
                results.append((True, f"{patch.get('file', '')} written"))
            else:
                line_applier = LinePatchApplier()
                new_content, error = line_applier._candidate_content(file, patch)
                if error is not None:
                    results.append((False, error))
                    continue
                assert new_content is not None
                if not self.validate(file, new_content):
                    results.append((False, f"{patch.get('file', '')} invalid JSON after patch"))
                    continue
                file.write_text(new_content, encoding="utf-8")
                results.append((True, f"{patch.get('file', '')} patched"))
        return results

    def validate(self, file: Path, content: str) -> bool:
        try:
            json.loads(content)
            return True
        except (json.JSONDecodeError, ValueError):
            return False


class YAMLPatchApplier(IPatchApplier):
    supported_extensions = {".yaml", ".yml"}

    def apply(self, file: Path, patches: list[Any]) -> Any:
        line_applier = LinePatchApplier()
        return line_applier.apply(file, patches)

    def validate(self, file: Path, content: str) -> bool:
        return True


PATCH_APPLIERS: dict[str, IPatchApplier] = {
    ".py": LinePatchApplier(),
    ".json": JSONPatchApplier(),
    ".yaml": YAMLPatchApplier(),
    ".yml": YAMLPatchApplier(),
    "*": LinePatchApplier(),
}


def get_applier(file_path: Path) -> IPatchApplier:
    return PATCH_APPLIERS.get(file_path.suffix, PATCH_APPLIERS["*"])
