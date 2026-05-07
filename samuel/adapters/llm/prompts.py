"""#301/#338: System-Prompt-Loader fuer Per-Task system_prompt-Field.

Search-Order (most-specific wins, #338 Schicht B):
  1. <config_dir>/llm/prompts/model/<sanitized-model>/<name>     — model-Override
  2. <config_dir>/llm/prompts/provider/<sanitized-provider>/<name> — provider-Override
  3. <config_dir>/llm/prompts/<name>                              — generic Operator-Override
  4. samuel/core/prompts/<name>                                   — Package-Default

Returns empty string if missing (graceful, kein Crash). #301 portiert die 7
v1-Prompts: analyst, docs_writer, healer, log_analyst, planner, reviewer,
senior_python.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_PACKAGE_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "core" / "prompts"

# Sanitize provider/model so directory names cannot escape the prompts root.
# Allowed: lowercase letters, digits, _, -, . — anything else collapses to `_`.
# Multiple `_` collapse to one. Empty result -> "" (skip the level entirely).
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_segment(value: str | None) -> str:
    """Map an arbitrary provider/model string to a safe single-segment dir.

    Strips path separators (``/``, ``\\``), traversal (``..``), and any
    non-allowed character. Returns ``""`` when nothing is left, signalling
    to the caller to skip the corresponding lookup level.
    """
    if not value:
        return ""
    cleaned = _SANITIZE_RE.sub("_", str(value).strip()).strip("._-")
    cleaned = re.sub(r"_+", "_", cleaned)
    if cleaned in ("", ".", ".."):
        return ""
    return cleaned


def _resolve_effective_filename(
    name: str | None,
    by_provider: dict | None,
    provider: str | None,
) -> str:
    """#351 Hybrid: pick the filename the runtime should actually load.

    ``by_provider`` is the optional ``{provider: filename}`` map persisted
    on the task. When the active ``provider`` has an entry, the map wins
    over ``name`` (the task's default ``system_prompt``). Map values are
    structurally validated by the handler, but we keep a defence-in-depth
    check here against path-traversal so this function can be called
    directly from tests / future call-sites.
    """
    if not (isinstance(by_provider, dict) and provider):
        return name or ""
    override = by_provider.get(provider)
    if not isinstance(override, str) or not override.strip():
        return name or ""
    if "/" in override or "\\" in override or ".." in override:
        # Reject traversal — fall back to default name.
        log.warning(
            "system_prompt_by_provider value rejected for provider=%s: %r",
            provider, override,
        )
        return name or ""
    return override


def load_system_prompt(
    name: str | None,
    config_dir: str | Path = "config",
    *,
    provider: str | None = None,
    model: str | None = None,
    by_provider: dict | None = None,
) -> str:
    """Return the system prompt content for ``name``, or empty string if missing.

    ``name`` is a filename like ``"senior_python.md"`` (with extension). The
    lookup walks the 4-stage ladder (#338 Schicht B) — see module docstring.
    Operator-overrides win over the package default; the most specific
    operator-override wins among the override layers.

    ``provider`` / ``model`` are optional — when omitted, the caller falls
    back to the legacy 2-stage behaviour (generic-operator > package).
    Sanitization keeps each value to a single safe directory segment.

    ``by_provider`` (#351 Hybrid): optional ``{provider: filename}`` map
    from the task config. When the active ``provider`` has an entry, that
    filename wins over ``name``. The cascade then proceeds normally on
    the chosen filename. This lets the operator pin a specific Library-
    file to a single provider (e.g. local 7B-models get a beefier prompt)
    without touching the global default.
    """
    name = _resolve_effective_filename(name, by_provider, provider)
    if not name:
        return ""
    name_str = str(name).strip()
    if not name_str:
        return ""

    base = Path(config_dir) / "llm" / "prompts"
    candidates: list[Path] = []

    sanitized_model = _sanitize_segment(model)
    if sanitized_model:
        candidates.append(base / "model" / sanitized_model / name_str)

    sanitized_provider = _sanitize_segment(provider)
    if sanitized_provider:
        candidates.append(base / "provider" / sanitized_provider / name_str)

    candidates.append(base / name_str)
    candidates.append(_PACKAGE_PROMPTS_DIR / name_str)

    for path in candidates:
        if not path.is_file():
            continue
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("system_prompt unreadable at %s: %s", path, exc)

    log.warning(
        "system_prompt not found: %s (searched: %s)",
        name_str, ", ".join(str(p) for p in candidates),
    )
    return ""


def load_prompt_at_scope(
    name: str | None, config_dir: str | Path = "config",
    scope: str | None = None,
) -> str:
    """#338 Schicht C: load the operator-override file at exactly one
    scope (no cascade fallback).

    Returns the file content if present, empty string otherwise. Only
    the operator-override scopes are reachable here — package-default
    is **not** returned (use ``load_system_prompt`` for that).

    Used by the dashboard modal so the UI can display "what is currently
    written at scope X" rather than "what would the cascade resolve to".
    """
    if not name:
        return ""
    name_str = str(name).strip()
    if not name_str:
        return ""
    sub, err = _scope_to_subdir(scope)
    if err:
        return ""
    base = Path(config_dir) / "llm" / "prompts"
    fp = base if sub is None else base / sub
    fp = fp / name_str
    if not fp.is_file():
        return ""
    try:
        return fp.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("load_prompt_at_scope unreadable %s: %s", fp, exc)
        return ""


def _scope_to_subdir(scope: str | None) -> tuple[str | None, str]:
    """#338 Schicht C: parse scope into (subdir or None, error).

    Accepts:
    - ``""`` / ``None`` / ``"generic"``  -> (None, "")  meaning the
      generic operator-override directory ``<config_dir>/llm/prompts/``
    - ``"provider:<name>"``               -> ("provider/<sanitized>", "")
    - ``"model:<id>"``                    -> ("model/<sanitized>", "")

    Returns ``(None, "invalid scope: ...")`` for malformed input. The
    sanitization is the same as in ``load_system_prompt`` so paths can
    never escape the prompts root.
    """
    if not scope or scope == "generic":
        return None, ""
    s = str(scope).strip()
    if ":" not in s:
        return None, f"invalid scope: {s!r}"
    kind, _, raw = s.partition(":")
    kind = kind.strip().lower()
    raw = raw.strip()
    if kind not in ("provider", "model"):
        return None, f"invalid scope kind: {kind!r}"
    seg = _sanitize_segment(raw)
    if not seg:
        return None, f"invalid scope value for {kind}: {raw!r}"
    return f"{kind}/{seg}", ""


def list_available_prompts(
    config_dir: str | Path = "config", scope: str | None = None,
) -> list[dict]:
    """#315/#338: Liste aller .md-Files.

    - ``scope=None`` (or ``"generic"``): legacy view — Package-defaults
      plus generic Operator-Override (``<config_dir>/llm/prompts/``).
      Operator-Override wins for shared names (``source: "operator"``).
    - ``scope="provider:<name>"`` / ``"model:<id>"``: list ONLY the
      scoped Operator-Overrides at that level (no merge with package).
    """
    if scope and scope != "generic":
        sub, err = _scope_to_subdir(scope)
        if err or sub is None:
            return []
        scoped_dir = Path(config_dir) / "llm" / "prompts" / sub
        if not scoped_dir.is_dir():
            return []
        rows: list[dict] = []
        for f in scoped_dir.glob("*.md"):
            try:
                rows.append({
                    "name":   f.name,
                    "source": f"operator-{sub.split('/')[0]}",
                    "size":   f.stat().st_size,
                })
            except OSError as exc:
                log.warning("list prompts: scoped %s unreadable: %s", f, exc)
        return sorted(rows, key=lambda r: r["name"])

    # Legacy path (scope=None or "generic")
    rows_dict: dict[str, dict] = {}
    if _PACKAGE_PROMPTS_DIR.is_dir():
        for f in _PACKAGE_PROMPTS_DIR.glob("*.md"):
            try:
                rows_dict[f.name] = {
                    "name":   f.name,
                    "source": "package",
                    "size":   f.stat().st_size,
                }
            except OSError as exc:
                log.warning("list prompts: package %s unreadable: %s", f, exc)
    op_dir = Path(config_dir) / "llm" / "prompts"
    if op_dir.is_dir():
        for f in op_dir.glob("*.md"):
            try:
                rows_dict[f.name] = {
                    "name":   f.name,
                    "source": "operator",
                    "size":   f.stat().st_size,
                }
            except OSError as exc:
                log.warning("list prompts: operator %s unreadable: %s", f, exc)
    return sorted(rows_dict.values(), key=lambda r: r["name"])


def write_prompt(
    name: str, content: str, config_dir: str | Path = "config",
    scope: str | None = None,
) -> dict:
    """#315/#338: Schreibt einen Operator-Override.

    Default: ``<config_dir>/llm/prompts/<name>`` (generic).
    With ``scope="provider:lmstudio"`` -> ``provider/lmstudio/<name>``.
    With ``scope="model:qwen2.5-coder-7b"`` -> ``model/qwen2.5-coder-7b/<name>``.

    Premium-only: ``llm_routing_dashboard_write``. Atomar via tmp+rename.
    Validation:
      - ``name`` muss auf ``.md`` enden, keine Pfad-Separatoren enthalten
      - ``content`` darf nicht leer sein
      - ``scope`` muss gueltig sein (siehe ``_scope_to_subdir``)
    """
    from samuel.core import license as _lic
    if not (_lic.is_premium_active()
            and _lic.has_feature("llm_routing_dashboard_write")):
        return {
            "saved": False,
            "error": "premium feature llm_routing_dashboard_write required",
        }
    name_str = str(name or "").strip()
    if not name_str.endswith(".md"):
        return {"saved": False, "error": "name must end with .md"}
    if "/" in name_str or "\\" in name_str or ".." in name_str:
        return {"saved": False, "error": "invalid characters in name"}
    if not isinstance(content, str) or not content.strip():
        return {"saved": False, "error": "content must be a non-empty string"}

    sub, scope_err = _scope_to_subdir(scope)
    if scope_err:
        return {"saved": False, "error": scope_err}

    base = Path(config_dir) / "llm" / "prompts"
    op_dir = base if sub is None else base / sub
    fp = op_dir / name_str
    tmp = fp.with_suffix(".tmp")
    try:
        op_dir.mkdir(parents=True, exist_ok=True)
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(fp)
    except OSError as exc:
        return {"saved": False, "error": f"could not write prompt: {exc}"}

    source = "operator" if sub is None else f"operator-{sub.split('/')[0]}"
    return {
        "saved": True, "name": name_str, "size": len(content),
        "source": source, "scope": scope or "generic",
    }


def delete_prompt(
    name: str, config_dir: str | Path = "config",
    scope: str | None = None,
) -> dict:
    """#338 Schicht C: Reset-to-Default — entfernt einen Operator-Override.

    Default scope (``None`` / ``"generic"``) loescht
    ``<config_dir>/llm/prompts/<name>``. Mit ``scope="provider:..."`` oder
    ``"model:..."`` wird die scope-spezifische Datei entfernt. Liefert
    ``deleted=False`` wenn die Datei gar nicht existierte (no-op, idempotent).

    Premium-only: ``llm_routing_dashboard_write``.
    """
    from samuel.core import license as _lic
    if not (_lic.is_premium_active()
            and _lic.has_feature("llm_routing_dashboard_write")):
        return {
            "deleted": False,
            "error": "premium feature llm_routing_dashboard_write required",
        }
    name_str = str(name or "").strip()
    if not name_str.endswith(".md"):
        return {"deleted": False, "error": "name must end with .md"}
    if "/" in name_str or "\\" in name_str or ".." in name_str:
        return {"deleted": False, "error": "invalid characters in name"}

    sub, scope_err = _scope_to_subdir(scope)
    if scope_err:
        return {"deleted": False, "error": scope_err}

    base = Path(config_dir) / "llm" / "prompts"
    op_dir = base if sub is None else base / sub
    fp = op_dir / name_str
    if not fp.exists():
        return {
            "deleted": False, "name": name_str,
            "scope": scope or "generic",
            "reason": "no override at this scope",
        }
    try:
        fp.unlink()
    except OSError as exc:
        return {"deleted": False, "error": f"could not delete prompt: {exc}"}
    return {"deleted": True, "name": name_str, "scope": scope or "generic"}


def resolve_prompt_source(
    name: str | None, config_dir: str | Path = "config",
    *, provider: str | None = None, model: str | None = None,
    by_provider: dict | None = None,
) -> dict:
    """#338 Schicht C: Source-Indikator fuer das Dashboard-Modal.

    Walkt die gleiche 4-Stufen-Leiter wie ``load_system_prompt`` und gibt
    zurueck welcher Layer den Prompt heute liefern wuerde — ``source``,
    ``path`` und ``mtime`` (so kann der Operator im UI sehen ob er gerade
    den Package-Default oder einen Override sieht).

    ``by_provider`` (#351 Hybrid): when set and the active ``provider`` has
    an entry, the source query runs against that filename, not ``name``.
    Source label gets a ``+by_provider`` suffix so the badge can highlight
    that this row is taking a per-provider override branch.
    """
    name = _resolve_effective_filename(name, by_provider, provider)
    if not name:
        return {"source": "none", "path": "", "mtime": 0.0}
    name_str = str(name).strip()
    if not name_str:
        return {"source": "none", "path": "", "mtime": 0.0}

    base = Path(config_dir) / "llm" / "prompts"
    levels: list[tuple[str, Path]] = []
    sm = _sanitize_segment(model)
    if sm:
        levels.append((f"operator-model:{sm}", base / "model" / sm / name_str))
    sp = _sanitize_segment(provider)
    if sp:
        levels.append((f"operator-provider:{sp}", base / "provider" / sp / name_str))
    levels.append(("operator-generic", base / name_str))
    levels.append(("package", _PACKAGE_PROMPTS_DIR / name_str))

    for src, path in levels:
        if path.is_file():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            return {"source": src, "path": str(path), "mtime": mtime}
    return {"source": "none", "path": "", "mtime": 0.0}
