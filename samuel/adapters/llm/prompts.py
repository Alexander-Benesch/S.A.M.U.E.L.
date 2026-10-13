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
import os
import re
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from samuel.core.config import prompt_filename_error

log = logging.getLogger(__name__)

_PACKAGE_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "core" / "prompts"

# Sanitize provider/model so directory names cannot escape the prompts root.
# Allowed: lowercase letters, digits, _, -, . — anything else collapses to `_`.
# Multiple `_` collapse to one. Empty result -> "" (skip the level entirely).
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@contextmanager
def _prompt_directory(path: Path, *, root: Path, create: bool = False) -> Iterator[int]:
    """Anchor access at the trusted root; never follow links below it.

    Opening each component relative to its directory descriptor also prevents a
    checked component from being swapped for a symlink before the next access.
    Descriptor-relative/no-follow operations are required; no unsafe fallback.
    """
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise OSError("safe prompt file operations unavailable on this platform")
    parts = path.relative_to(root).parts
    if any(part in (".", "..") for part in parts):
        raise OSError("invalid prompt directory")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(root.resolve(), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, dir_fd=descriptor)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _read_prompt(path: Path, root: Path) -> tuple[str, os.stat_result]:
    with _prompt_directory(path.parent, root=root) as directory:
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError("prompt is not a regular file")
            return stream.read(), metadata


def _candidate_root(path: Path, config_dir: str | Path) -> Path:
    # Package defaults are installed assets; the operator root is explicit config.
    return _PACKAGE_PROMPTS_DIR.parent if path.parent == _PACKAGE_PROMPTS_DIR else Path(config_dir)


def _list_prompts(path: Path, root: Path, source: str) -> list[dict]:
    rows: list[dict] = []
    try:
        with _prompt_directory(path, root=root) as directory:
            for name in os.listdir(directory):
                if prompt_filename_error(name):
                    continue
                try:
                    metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISREG(metadata.st_mode):
                    rows.append({"name": name, "source": source, "size": metadata.st_size})
    except OSError:
        log.warning("prompt directory unavailable: %s", path)
    return rows


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
    if prompt_filename_error(override):
        # Reject traversal — fall back to default name.
        log.warning(
            "system_prompt_by_provider value rejected for provider=%s: %r",
            provider,
            override,
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
    if prompt_filename_error(name_str):
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
        try:
            return _read_prompt(path, _candidate_root(path, config_dir))[0]
        except (OSError, UnicodeError) as exc:
            log.warning("system_prompt unreadable at %s (%s)", path, type(exc).__name__)

    log.warning(
        "system_prompt not found: %s (searched: %s)",
        name_str,
        ", ".join(str(p) for p in candidates),
    )
    return ""


def load_prompt_at_scope(
    name: str | None,
    config_dir: str | Path = "config",
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
    if prompt_filename_error(name_str):
        return ""
    sub, err = _scope_to_subdir(scope)
    if err:
        return ""
    base = Path(config_dir) / "llm" / "prompts"
    fp = base if sub is None else base / sub
    fp = fp / name_str
    try:
        return _read_prompt(fp, Path(config_dir))[0]
    except (OSError, UnicodeError) as exc:
        log.warning("load_prompt_at_scope unreadable %s (%s)", fp, type(exc).__name__)
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
    config_dir: str | Path = "config",
    scope: str | None = None,
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
        return sorted(
            _list_prompts(scoped_dir, Path(config_dir), f"operator-{sub.split('/')[0]}"),
            key=lambda row: row["name"],
        )

    rows_dict = {
        row["name"]: row
        for row in _list_prompts(_PACKAGE_PROMPTS_DIR, _PACKAGE_PROMPTS_DIR.parent, "package")
    }
    op_dir = Path(config_dir) / "llm" / "prompts"
    rows_dict.update(
        {row["name"]: row for row in _list_prompts(op_dir, Path(config_dir), "operator")}
    )
    return sorted(rows_dict.values(), key=lambda row: row["name"])


def write_prompt(
    name: str,
    content: str,
    config_dir: str | Path = "config",
    scope: str | None = None,
) -> dict:
    """#315/#338: Schreibt einen Operator-Override.

    Default: ``<config_dir>/llm/prompts/<name>`` (generic).
    With ``scope="provider:lmstudio"`` -> ``provider/lmstudio/<name>``.
    With ``scope="model:qwen2.5-coder-7b"`` -> ``model/qwen2.5-coder-7b/<name>``.

    Atomar via tmp+rename. Der HTTP-Zugriff bleibt durch den Dashboard-API-Key
    geschützt; diese Funktion validiert zusätzlich Pfad, Scope und Inhalt.
    Validation:
      - ``name`` muss auf ``.md`` enden, keine Pfad-Separatoren enthalten
      - ``content`` darf nicht leer sein
      - ``scope`` muss gueltig sein (siehe ``_scope_to_subdir``)
    """
    name_str = str(name or "").strip()
    if error := prompt_filename_error(name_str):
        return {"saved": False, "error": error}
    if not isinstance(content, str) or not content.strip():
        return {"saved": False, "error": "content must be a non-empty string"}

    sub, scope_err = _scope_to_subdir(scope)
    if scope_err:
        return {"saved": False, "error": scope_err}

    base = Path(config_dir) / "llm" / "prompts"
    op_dir = base if sub is None else base / sub
    try:
        with _prompt_directory(op_dir, root=Path(config_dir), create=True) as directory:
            temporary = f".samuel-prompt-{uuid.uuid4().hex}.tmp"
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, name_str, src_dir_fd=directory, dst_dir_fd=directory)
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(temporary, dir_fd=directory)
    except OSError as exc:
        return {"saved": False, "error": f"could not write prompt: {exc}"}

    source = "operator" if sub is None else f"operator-{sub.split('/')[0]}"
    return {
        "saved": True,
        "name": name_str,
        "size": len(content),
        "source": source,
        "scope": scope or "generic",
    }


def delete_prompt(
    name: str,
    config_dir: str | Path = "config",
    scope: str | None = None,
) -> dict:
    """#338 Schicht C: Reset-to-Default — entfernt einen Operator-Override.

    Default scope (``None`` / ``"generic"``) loescht
    ``<config_dir>/llm/prompts/<name>``. Mit ``scope="provider:..."`` oder
    ``"model:..."`` wird die scope-spezifische Datei entfernt. Liefert
    ``deleted=False`` wenn die Datei gar nicht existierte (no-op, idempotent).

    Der HTTP-Zugriff bleibt durch den Dashboard-API-Key geschützt; diese
    Funktion validiert zusätzlich Pfad und Scope.
    """
    name_str = str(name or "").strip()
    if error := prompt_filename_error(name_str):
        return {"deleted": False, "error": error}

    sub, scope_err = _scope_to_subdir(scope)
    if scope_err:
        return {"deleted": False, "error": scope_err}

    base = Path(config_dir) / "llm" / "prompts"
    op_dir = base if sub is None else base / sub
    try:
        with _prompt_directory(op_dir, root=Path(config_dir)) as directory:
            os.unlink(name_str, dir_fd=directory)
    except FileNotFoundError:
        return {
            "deleted": False,
            "name": name_str,
            "scope": scope or "generic",
            "reason": "no override at this scope",
        }
    except OSError as exc:
        return {"deleted": False, "error": f"could not delete prompt: {exc}"}
    return {"deleted": True, "name": name_str, "scope": scope or "generic"}


def resolve_prompt_source(
    name: str | None,
    config_dir: str | Path = "config",
    *,
    provider: str | None = None,
    model: str | None = None,
    by_provider: dict | None = None,
    scope: str | None = None,
) -> dict:
    """#338 Schicht C: Source-Indikator fuer das Dashboard-Modal.

    Walkt die gleiche 4-Stufen-Leiter wie ``load_system_prompt`` und gibt
    zurueck welcher Layer den Prompt heute liefern wuerde — ``source``,
    ``path`` und ``mtime`` (so kann der Operator im UI sehen ob er gerade
    den Package-Default oder einen Override sieht).

    ``by_provider`` (#351 Hybrid): when set and the active ``provider`` has
    an entry, the source query runs against that filename, not ``name``.
    With ``scope`` set, match ``load_prompt_at_scope`` exactly: inspect only
    that operator layer without falling back to another scope or package.
    """
    name = _resolve_effective_filename(name, by_provider, provider)
    if not name:
        return {"source": "none", "path": "", "mtime": 0.0}
    name_str = str(name).strip()
    if prompt_filename_error(name_str):
        return {"source": "none", "path": "", "mtime": 0.0}

    base = Path(config_dir) / "llm" / "prompts"
    levels: list[tuple[str, Path]] = []
    if scope is not None:
        sub, err = _scope_to_subdir(scope)
        if err:
            return {"source": "none", "path": "", "mtime": 0.0}
        source = "operator-generic" if sub is None else "operator-" + sub.replace("/", ":", 1)
        levels.append((source, (base if sub is None else base / sub) / name_str))
    else:
        sm = _sanitize_segment(model)
        if sm:
            levels.append((f"operator-model:{sm}", base / "model" / sm / name_str))
        sp = _sanitize_segment(provider)
        if sp:
            levels.append((f"operator-provider:{sp}", base / "provider" / sp / name_str))
        levels.append(("operator-generic", base / name_str))
        levels.append(("package", _PACKAGE_PROMPTS_DIR / name_str))

    for src, path in levels:
        try:
            _, metadata = _read_prompt(path, _candidate_root(path, config_dir))
        except (OSError, UnicodeError):
            continue
        mtime = metadata.st_mtime
        return {"source": src, "path": str(path), "mtime": mtime}
    return {"source": "none", "path": "", "mtime": 0.0}
