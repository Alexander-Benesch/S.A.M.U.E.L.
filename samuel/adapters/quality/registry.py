from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from samuel.core.ports import IQualityCheck

log = logging.getLogger(__name__)


QUALITY_CHECKS: dict[str, list[IQualityCheck]] = {}

_DEFAULT_CHECK_NAMES: dict[str, list[str]] = {
    ".py": ["PythonSyntaxCheck"],
    ".ts": ["TreeSitterTypeScriptCheck"],
    ".tsx": ["TreeSitterTypeScriptCheck"],
    ".js": ["TreeSitterTypeScriptCheck"],
    "*": ["DiffSizeCheck", "ScopeGuard"],
}


def register_check(check: IQualityCheck, *, extension: str | None = None) -> None:
    if extension is not None:
        QUALITY_CHECKS.setdefault(extension, []).append(check)
    else:
        for ext in check.supported_extensions:
            QUALITY_CHECKS.setdefault(ext, []).append(check)


def get_checks_for(extension: str) -> list[IQualityCheck]:
    specific = QUALITY_CHECKS.get(extension, [])
    if extension == "*":
        return list(specific)
    wildcard = QUALITY_CHECKS.get("*", [])
    return specific + wildcard


def get_all_unique_checks() -> list[IQualityCheck]:
    seen: set[int] = set()
    result: list[IQualityCheck] = []
    for checks in QUALITY_CHECKS.values():
        for check in checks:
            identity = id(check)
            if identity not in seen:
                seen.add(identity)
                result.append(check)
    return result


def _validate_extension(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("quality-check extension must be a canonical string")
    if value != "*" and (
        not value.startswith(".")
        or value.lower() != value
        or any(char in value for char in "/\\ \t\r\n")
    ):
        raise ValueError(f"invalid quality-check extension: {value!r}")
    return value


def _load_check_names(config_path: Path | None) -> dict[str, list[str]]:
    if config_path is None or not config_path.exists():
        return {extension: list(names) for extension, names in _DEFAULT_CHECK_NAMES.items()}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid quality config: {config_path}") from exc
    if not isinstance(data, dict) or set(data) - {"quality_checks"}:
        raise ValueError("hooks.json must contain only the quality_checks object")
    quality = data.get("quality_checks")
    if not isinstance(quality, dict) or set(quality) - {"disabled", "extensions"}:
        raise ValueError("quality_checks contains unknown or invalid fields")
    raw_extensions = quality.get("extensions", _DEFAULT_CHECK_NAMES)
    if not isinstance(raw_extensions, dict):
        raise ValueError("quality_checks.extensions must be an object")
    configured: dict[str, list[str]] = {}
    for raw_extension, raw_names in raw_extensions.items():
        extension = _validate_extension(raw_extension)
        if not isinstance(raw_names, list) or not all(isinstance(name, str) for name in raw_names):
            raise ValueError(f"quality checks for {extension} must be a list of names")
        if len(raw_names) != len(set(raw_names)):
            raise ValueError(f"duplicate quality check configured for {extension}")
        configured[extension] = list(raw_names)
    disabled = quality.get("disabled", [])
    if not isinstance(disabled, list):
        raise ValueError("quality_checks.disabled must be a list of extensions")
    for raw_extension in disabled:
        extension = _validate_extension(raw_extension)
        if extension not in configured:
            raise ValueError(f"disabled quality extension is not configured: {extension}")
        configured.pop(extension)
    return configured


def load_registry_from_config(config_path: Path | None = None) -> None:
    from samuel.adapters.quality.checks import (
        DiffSizeCheck,
        PythonSyntaxCheck,
        ScopeGuard,
        TreeSitterTypeScriptCheck,
    )

    check_types: dict[str, type[IQualityCheck]] = {
        "PythonSyntaxCheck": PythonSyntaxCheck,
        "TreeSitterTypeScriptCheck": TreeSitterTypeScriptCheck,
        "DiffSizeCheck": DiffSizeCheck,
        "ScopeGuard": ScopeGuard,
    }
    configured = _load_check_names(config_path)

    QUALITY_CHECKS.clear()
    for extension, names in configured.items():
        for name in names:
            check_type = check_types.get(name)
            if check_type is None:
                raise ValueError(f"unknown quality check: {name}")
            check = check_type()
            supported = check.supported_extensions
            if extension not in supported and "*" not in supported:
                raise ValueError(f"quality check {name} does not support {extension}")
            check.supported_extensions = {extension}
            register_check(check, extension=extension)

    total = sum(len(v) for v in QUALITY_CHECKS.values())
    log.info(
        "Quality registry: %d configured checks across %d extensions%s",
        total,
        len(QUALITY_CHECKS),
        f" from {config_path}" if config_path else " (defaults)",
    )
