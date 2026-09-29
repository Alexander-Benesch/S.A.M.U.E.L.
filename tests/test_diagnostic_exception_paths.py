from __future__ import annotations

import ast
from pathlib import Path


def _is_broad_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}


def _has_observable_failure_path(handler: ast.ExceptHandler) -> bool:
    """Recognise logging, propagation, events, or structured error results.

    Returning an empty collection/``None`` alone is intentionally not enough:
    that was the exact class of silent failure missed by the original #429
    guard.  Calls to ``_dead_letter`` count as durable failure recording.
    """

    tree = ast.Module(body=handler.body, type_ignores=[])
    observable_calls = {
        "debug",
        "info",
        "warning",
        "error",
        "exception",
        "critical",
        "publish",
        "handleError",
        "print",
        "_dead_letter",
    }
    diagnostic_keys = {"error", "detail", "valid", "reason", "exception"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in observable_calls:
                return True
            values = [*node.args, *(keyword.value for keyword in node.keywords)]
            if any(_dict_keys(value) & diagnostic_keys for value in values):
                return True
        if isinstance(node, ast.Return) and _dict_keys(node.value) & diagnostic_keys:
            return True
    return False


def _dict_keys(node: ast.AST | None) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    return {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def test_production_code_has_no_silent_broad_exception_handler() -> None:
    """#429: broad failures need an observable or explicitly structured outcome."""

    findings: list[str] = []
    for path in Path("samuel").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or not _is_broad_exception(node):
                continue
            if not _has_observable_failure_path(node):
                findings.append(f"{path}:{node.lineno}")

    assert findings == [], "unobservable broad exception handler(s): " + ", ".join(findings)
