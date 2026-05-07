from __future__ import annotations

import importlib
import json
import logging
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import Command, VerifyACCommand
from samuel.core.events import ACFailed, ACVerified, TestRunCompleted
from samuel.core.project_files import (
    CODE_EXTENSIONS,
    CONFIG_EXTENSIONS,
    iter_project_files,
)

log = logging.getLogger(__name__)

ACHandler = Callable[[str, Path | None], dict[str, Any]]

_AC_REGISTRY: dict[str, ACHandler] = {}

_SAFE_IMPORT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./ -]+$")
_SAFE_TEST_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_:.\-]*$")

_DEFAULT_TEST_TIMEOUT = 60

# (marker_filename, [command_template_with_{test}_placeholder]) — first match wins
_TEST_RUNNER_MARKERS: list[tuple[str, list[str]]] = [
    # Python markers use sys.executable -m pytest so the call works without
    # pytest being on PATH (e.g. when samuel is started as `.venv/bin/python
    # -m samuel` without activating the venv first). #254.
    ("pyproject.toml", [sys.executable, "-m", "pytest", "-q", "-k", "{test}"]),
    ("pytest.ini",     [sys.executable, "-m", "pytest", "-q", "-k", "{test}"]),
    ("setup.cfg",      [sys.executable, "-m", "pytest", "-q", "-k", "{test}"]),
    ("package.json",   ["npx", "jest", "-t", "{test}"]),
    ("go.mod",         ["go", "test", "-run", "{test}", "./..."]),
    ("Cargo.toml",     ["cargo", "test", "{test}"]),
    ("pom.xml",        ["mvn", "test", "-Dtest={test}"]),
]


def _load_eval_config(project_root: Path) -> dict[str, Any]:
    cfg_path = project_root / "config" / "eval.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("eval.json not parsable: %s", exc)
        return {}


def _resolve_test_runner(
    project_root: Path, test_name: str,
) -> tuple[list[str], int, str] | None:
    """Resolve a test runner command for the given test name.

    Priority:
      1. config/eval.json:test_cmd (string with {test} placeholder)
      2. Marker auto-detection (pyproject.toml/package.json/go.mod/...)

    Returns (cmd_list, timeout_seconds, runner_label) or None.
    """
    cfg = _load_eval_config(project_root)
    timeout = int(cfg.get("test_timeout") or _DEFAULT_TEST_TIMEOUT)

    test_cmd = cfg.get("test_cmd")
    if isinstance(test_cmd, str) and test_cmd.strip():
        parts = test_cmd.split()
        cmd = [p.replace("{test}", test_name) for p in parts]
        return cmd, timeout, "config"

    for marker, template in _TEST_RUNNER_MARKERS:
        if (project_root / marker).exists():
            cmd = [p.replace("{test}", test_name) for p in template]
            return cmd, timeout, marker.split(".")[0]

    return None


def register_ac_handler(tag: str, handler: ACHandler) -> None:
    _AC_REGISTRY[tag] = handler


def _sanitize_path(arg: str, project_root: Path) -> Path | None:
    cleaned = arg.strip().replace("..", "")
    if not _SAFE_PATH_RE.match(cleaned):
        return None
    resolved = (project_root / cleaned).resolve()
    if not str(resolved).startswith(str(project_root.resolve())):
        return None
    return resolved


def _check_diff(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    path = _sanitize_path(arg, project_root)
    if path is None:
        return {"passed": False, "reason": f"path rejected (traversal blocked): {arg}"}
    return {"passed": path.exists(), "reason": f"{'exists' if path.exists() else 'not found'}: {arg}"}


def _check_exists(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    path = _sanitize_path(arg, project_root)
    if path is None:
        return {"passed": False, "reason": f"path rejected (traversal blocked): {arg}"}
    return {"passed": path.exists(), "reason": f"{'exists' if path.exists() else 'not found'}: {arg}"}


def _check_import(arg: str, project_root: Path | None) -> dict[str, Any]:
    module_name = arg.strip()
    if not _SAFE_IMPORT_RE.match(module_name):
        return {"passed": False, "reason": f"import rejected (invalid chars): {arg}"}
    if any(dangerous in module_name for dangerous in ("os", "sys", "subprocess", "shutil", "pathlib")):
        return {"passed": False, "reason": f"import rejected (blocked module): {arg}"}
    try:
        importlib.import_module(module_name)
        return {"passed": True, "reason": f"importable: {module_name}"}
    except ImportError as exc:
        return {"passed": False, "reason": f"import failed: {exc}"}


def _check_grep(arg: str, project_root: Path | None) -> dict[str, Any]:
    """#236: sprachneutral via iter_project_files (CODE+CONFIG-Extensions).
    Vorher rglob("*.py") — Python-only. Jetzt deckt .go/.ts/.json/.yaml etc."""
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    pattern = arg.strip().strip('"').strip("'")
    extensions = CODE_EXTENSIONS | CONFIG_EXTENSIONS
    for src_file in iter_project_files(project_root, extensions=extensions):
        try:
            if pattern in src_file.read_text(encoding="utf-8", errors="replace"):
                try:
                    rel = src_file.relative_to(project_root)
                except ValueError:
                    try:
                        rel = src_file.relative_to(project_root.resolve())
                    except ValueError:
                        rel = src_file.name
                return {"passed": True, "reason": f"found in {rel}"}
        except OSError:
            continue
    return {"passed": False, "reason": f"pattern not found: {pattern}"}


def _check_grep_not(arg: str, project_root: Path | None) -> dict[str, Any]:
    result = _check_grep(arg, project_root)
    return {"passed": not result["passed"], "reason": result["reason"].replace("found", "still present") if result["passed"] else f"confirmed absent: {arg.strip()}"}


def _check_manual(arg: str, project_root: Path | None) -> dict[str, Any]:
    return {"passed": False, "reason": f"manual check required: {arg}", "manual": True}


def _check_test(arg: str, project_root: Path | None) -> dict[str, Any]:
    if not project_root:
        return {"passed": False, "reason": "no project root"}
    test_name = arg.strip()
    if not _SAFE_TEST_NAME_RE.match(test_name):
        return {"passed": False, "reason": f"test name rejected: {arg}"}

    resolved = _resolve_test_runner(project_root, test_name)
    if resolved is None:
        return {
            "passed": False,
            "manual": True,
            "reason": "no test runner configured (set config/eval.json:test_cmd or add marker file)",
            "runner": "none",
        }
    cmd, timeout, runner = resolved

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=str(project_root), capture_output=True, text=True,
            timeout=timeout, shell=False, check=False,
        )
    except FileNotFoundError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "passed": False,
            "reason": f"test runner binary not found: {cmd[0]}",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": None,
            "output_excerpt": str(exc),
        }
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "passed": False,
            "reason": f"test timeout after {timeout}s: {test_name}",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": None,
            "output_excerpt": "",
        }
    except OSError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return {
            "passed": False,
            "reason": f"test runner OS error: {exc}",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": None,
            "output_excerpt": "",
        }

    duration_ms = int((time.monotonic() - t0) * 1000)
    output_excerpt = (proc.stdout or proc.stderr or "")[-500:]
    if proc.returncode == 0:
        return {
            "passed": True,
            "reason": f"tests passed: {test_name} ({runner})",
            "runner": runner,
            "duration_ms": duration_ms,
            "exit_code": 0,
            "output_excerpt": output_excerpt,
        }
    return {
        "passed": False,
        "reason": f"tests failed: {test_name} (exit={proc.returncode})",
        "runner": runner,
        "duration_ms": duration_ms,
        "exit_code": proc.returncode,
        "output_excerpt": output_excerpt,
    }


register_ac_handler("DIFF", _check_diff)
register_ac_handler("EXISTS", _check_exists)
register_ac_handler("IMPORT", _check_import)
register_ac_handler("GREP", _check_grep)
register_ac_handler("GREP:NOT", _check_grep_not)
register_ac_handler("MANUAL", _check_manual)
register_ac_handler("TEST", _check_test)


AC_PATTERN = re.compile(r"- \[.\] \[([A-Z:]+)\]\s*(.+)")

# #236: Trenner zwischen arg und Beschreibung in einer Plan-AC-Zeile.
# Em-Dash, En-Dash, Whitespace-Doppelpunkt, sowie ASCII-Doppel-Bindestrich.
_ARG_SEPARATORS = (" — ", " – ", " : ", " -- ")


def _extract_arg(tag: str, rest_raw: str) -> str:
    """#236: Tag-spezifische Argument-Extraktion.

    Vorher griff handle() einfach ``match.group(2).strip()`` — das saugt den
    ganzen Rest der Zeile inklusive Em-Dash-Beschreibung ein und _sanitize_path
    lehnt das wegen Em-Dash ab.

    Regeln pro Tag:
    - DIFF/EXISTS/IMPORT: erstes Whitespace-getrenntes Token
    - GREP/GREP:NOT: quoted string ("..." oder '...') — Quotes gestrippt
    - TEST: bis zum ersten Trenner ( — , – , : , -- ) oder Zeilenende
    - MANUAL: ganze Restzeile (Beschreibung ist hier inhaltlich der Punkt)
    """
    rest = rest_raw.strip()
    if tag in ("DIFF", "EXISTS", "IMPORT"):
        return rest.split()[0] if rest else ""
    if tag in ("GREP", "GREP:NOT"):
        # Quoted string: "pattern" oder 'pattern' bevorzugt; sonst erstes Token
        m = re.match(r'^"([^"]*)"', rest) or re.match(r"^'([^']*)'", rest)
        if m:
            return m.group(1)
        return rest.split()[0] if rest else ""
    if tag == "TEST":
        for sep in _ARG_SEPARATORS:
            i = rest.find(sep)
            if i >= 0:
                rest = rest[:i].strip()
                break
        return rest.split()[0] if rest else ""
    if tag == "MANUAL":
        return rest
    return rest


class ACVerificationHandler:
    def __init__(
        self,
        bus: Bus,
        project_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._root = project_root

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, VerifyACCommand)

        plan_text = cmd.payload.get("plan_text", "")
        if not plan_text:
            return {"verified": False, "reason": "no plan text", "results": []}

        issue_number = cmd.payload.get("issue")
        correlation_id = cmd.correlation_id or ""
        results: list[dict[str, Any]] = []
        for match in AC_PATTERN.finditer(plan_text):
            tag = match.group(1)
            # #236: tag-spezifische Argument-Extraktion (ohne Em-Dash-Suffix)
            arg = _extract_arg(tag, match.group(2))
            handler = _AC_REGISTRY.get(tag)
            if handler:
                result = handler(arg, self._root)
                result["tag"] = tag
                result["arg"] = arg
                results.append(result)
                if tag == "TEST":
                    self._bus.publish(TestRunCompleted(
                        payload={
                            "issue": issue_number,
                            "test_name": arg,
                            "runner": result.get("runner", "unknown"),
                            "passed": bool(result.get("passed", False)),
                            "exit_code": result.get("exit_code"),
                            "duration_ms": result.get("duration_ms"),
                            "output_excerpt": result.get("output_excerpt", ""),
                        },
                        correlation_id=correlation_id,
                    ))
                # #236: pro AC ein ACVerified/ACFailed Event publishen — sichtbar
                # im Dashboard via acceptance_checks-Slot.
                ac_payload = {
                    "issue": issue_number,
                    "tag": tag,
                    "arg": arg,
                    "passed": bool(result.get("passed", False)),
                    "reason": str(result.get("reason", "")),
                    "evt": "ac_verified" if result.get("passed") else "ac_failed",
                }
                if result.get("passed"):
                    self._bus.publish(ACVerified(
                        payload=ac_payload, correlation_id=correlation_id,
                    ))
                else:
                    self._bus.publish(ACFailed(
                        payload=ac_payload, correlation_id=correlation_id,
                    ))
            else:
                results.append({"tag": tag, "arg": arg, "passed": False, "reason": f"unknown tag: {tag}"})

        passed_count = sum(1 for r in results if r.get("passed"))
        manual_count = sum(1 for r in results if r.get("manual"))
        auto_total = len(results) - manual_count
        auto_passed = sum(1 for r in results if r.get("passed") and not r.get("manual"))

        return {
            "verified": auto_passed == auto_total and auto_total > 0,
            "total": len(results),
            "passed": passed_count,
            "manual": manual_count,
            "results": results,
        }