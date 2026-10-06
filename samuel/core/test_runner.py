"""Shared TEST-runner policy resolution and planning/Doctor readiness checks.

The helpers in this module inspect the operator-controlled runner policy and
the bound project only.  They never execute a runner, install a tool, rewrite
a selector, or choose a fallback after resolution.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from samuel.core.acceptance import parse_test_criterion_argument
from samuel.core.config import EvalSchema
from samuel.core.process_environment import verifier_executable_path

_SAFE_NODE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./ -]+$")
_SAFE_UNITTEST_SELECTOR_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$")
_DEFAULT_TEST_TIMEOUT = 60


@dataclass(frozen=True)
class VerifierRunnerPolicy:
    policy_version: str
    test_cmd: str | None
    test_timeout: int
    source: str = "control_plane"

    @classmethod
    def from_eval_config(cls, config: EvalSchema) -> VerifierRunnerPolicy:
        return cls(
            policy_version=config.test_policy_version,
            test_cmd=config.test_cmd,
            test_timeout=config.test_timeout,
        )


DEFAULT_TEST_RUNNER_POLICY = VerifierRunnerPolicy(
    policy_version="schema-default",
    test_cmd=None,
    test_timeout=_DEFAULT_TEST_TIMEOUT,
)


# (marker_filename, command_template_with_{test}_placeholder) -- first match wins.
TEST_RUNNER_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pyproject.toml", (sys.executable, "-m", "pytest", "-q", "-k", "{test}")),
    ("pytest.ini", (sys.executable, "-m", "pytest", "-q", "-k", "{test}")),
    ("setup.cfg", (sys.executable, "-m", "pytest", "-q", "-k", "{test}")),
    ("package.json", ("npx", "jest", "-t", "{test}")),
    ("go.mod", ("go", "test", "-run", "{test}", "./...")),
    ("Cargo.toml", ("cargo", "test", "{test}")),
    ("pom.xml", ("mvn", "test", "-Dtest={test}")),
)


def resolve_test_runner(
    project_root: Path,
    test_name: str,
    policy: VerifierRunnerPolicy = DEFAULT_TEST_RUNNER_POLICY,
) -> tuple[list[str], int, str] | None:
    """Resolve exactly one configured or marker-selected runner."""

    timeout = policy.test_timeout
    if policy.test_cmd:
        parts = shlex.split(policy.test_cmd)
        return [part.replace("{test}", test_name) for part in parts], timeout, "config"

    for marker, template in TEST_RUNNER_MARKERS:
        if not (project_root / marker).exists():
            continue
        if marker in {"pyproject.toml", "pytest.ini", "setup.cfg"} and "::" in test_name:
            command = [sys.executable, "-m", "pytest", "-q", test_name]
        else:
            command = [part.replace("{test}", test_name) for part in template]
        return command, timeout, marker.split(".")[0]
    return None


def runner_kind(command: list[str]) -> str:
    """Classify only runner forms whose selector grammar is known here."""

    executable = Path(command[0]).name.casefold() if command else ""
    python_executable = executable.removesuffix(".exe")
    if executable in {"pytest", "py.test"}:
        return "pytest"
    if executable in {"jest", "npx"} and any(
        Path(part).name.casefold() == "jest" for part in command
    ):
        return "jest"
    if executable == "go" and "test" in command[1:]:
        return "go"
    if executable == "cargo" and "test" in command[1:]:
        return "cargo"
    if executable in {"mvn", "mvnw"} and "test" in command[1:]:
        return "maven"
    if re.fullmatch(r"(?:python|pypy)\d*(?:\.\d+)*", python_executable) and "-m" in command:
        module_index = command.index("-m") + 1
        if module_index < len(command):
            module = command[module_index].casefold()
            if module in {"pytest", "unittest"}:
                return module
    return "custom"


def _runner_executable(command: list[str], project_root: Path) -> Path | None:
    if not command:
        return None
    raw = Path(command[0])
    if raw.is_absolute():
        candidate = raw
    elif "/" in command[0] or "\\" in command[0]:
        candidate = (project_root / raw).resolve()
    else:
        found = shutil.which(command[0], path=verifier_executable_path(command[0]))
        if not found:
            return None
        candidate = Path(found)
    return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None


def _installation_readiness(
    command: list[str],
    project_root: Path,
    *,
    runner: str,
    kind: str,
    policy: VerifierRunnerPolicy,
) -> dict[str, Any]:
    evidence = {
        "runner": runner,
        "runner_kind": kind,
        "runner_policy_source": policy.source,
        "runner_policy_version": policy.policy_version,
    }
    executable = _runner_executable(command, project_root)
    if executable is None:
        return {
            "passed": False,
            "status": "missing_evidence",
            "reason": f"test runner binary is not available: {Path(command[0]).name}",
            **evidence,
        }
    if "-m" in command and kind in {"pytest", "unittest"}:
        module_index = command.index("-m") + 1
        module = command[module_index] if module_index < len(command) else ""
        same_python_environment = (
            executable.resolve() == Path(sys.executable).resolve()
            and executable.parent.resolve() == Path(sys.executable).parent.resolve()
        )
        if module == "unittest":
            module_available = True
        elif same_python_environment:
            try:
                module_available = bool(module and importlib.util.find_spec(module) is not None)
            except (ImportError, ModuleNotFoundError, ValueError):
                module_available = False
        else:
            module_available = False
        if not module_available:
            return {
                "passed": False,
                "status": "missing_evidence",
                "reason": (
                    f"test runner module is not available in the active environment: "
                    f"{module or 'unknown'}"
                ),
                **evidence,
            }
    return {"passed": True, "status": "ready", **evidence}


def check_test_runner_installation(
    project_root: Path | None,
    policy: VerifierRunnerPolicy = DEFAULT_TEST_RUNNER_POLICY,
) -> dict[str, Any]:
    """Inspect whether the single effective runner exists, without execution."""

    policy_evidence = {
        "runner_policy_source": policy.source,
        "runner_policy_version": policy.policy_version,
    }
    if project_root is None:
        return {
            "passed": False,
            "status": "missing_evidence",
            "reason": "no project root for test runner readiness",
            **policy_evidence,
        }
    resolved = resolve_test_runner(project_root, "samuel_readiness_probe", policy)
    if resolved is None:
        return {
            "passed": False,
            "status": "missing_evidence",
            "reason": (
                "no test runner configured in control-plane eval.json "
                "and no supported project marker found"
            ),
            "runner": "none",
            **policy_evidence,
        }
    command, _timeout, runner = resolved
    kind = runner_kind(command)
    return _installation_readiness(
        command,
        project_root,
        runner=runner,
        kind=kind,
        policy=policy,
    )


def check_test_readiness(
    arg: str,
    project_root: Path | None,
    policy: VerifierRunnerPolicy = DEFAULT_TEST_RUNNER_POLICY,
) -> dict[str, Any]:
    """Validate runner and selector compatibility without executing tests."""

    policy_evidence = {
        "runner_policy_source": policy.source,
        "runner_policy_version": policy.policy_version,
    }
    if project_root is None:
        return {
            "passed": False,
            "status": "missing_evidence",
            "reason": "no project root for test runner readiness",
            **policy_evidence,
        }
    try:
        test_name = parse_test_criterion_argument(arg)
    except ValueError as exc:
        return {"passed": False, "status": "error", "reason": str(exc), **policy_evidence}

    if "::" in test_name:
        raw_path = test_name.split("::", 1)[0]
        cleaned = raw_path.strip()
        resolved_path = (project_root / cleaned).resolve()
        try:
            resolved_path.relative_to(project_root.resolve())
            inside_project = True
        except ValueError:
            inside_project = False
        if not _SAFE_NODE_PATH_RE.fullmatch(cleaned) or not inside_project:
            return {
                "passed": False,
                "status": "error",
                "reason": f"pytest node id rejected: {test_name}",
                **policy_evidence,
            }

    resolved = resolve_test_runner(project_root, test_name, policy)
    if resolved is None:
        return check_test_runner_installation(project_root, policy)
    command, _timeout, runner = resolved
    kind = runner_kind(command)
    if "::" in test_name and kind != "pytest":
        guidance = (
            "use a dotted selector such as tests.test_module"
            if kind == "unittest"
            else "use a runner-compatible logical selector"
        )
        return {
            "passed": False,
            "status": "incompatible_selector",
            "reason": f"pytest node id is incompatible with resolved {kind} runner; {guidance}",
            "runner": runner,
            "runner_kind": kind,
            **policy_evidence,
        }
    if "::" in test_name and kind == "pytest":
        selector_positions = [index for index, part in enumerate(command) if part == test_name]
        selector_is_positional = any(
            index == 0 or command[index - 1] not in {"-k", "--keyword"}
            for index in selector_positions
        )
        if not selector_is_positional:
            return {
                "passed": False,
                "status": "incompatible_selector",
                "reason": (
                    "pytest node id requires {test} as a direct positional argument; "
                    "the resolved runner binds it as a keyword expression"
                ),
                "runner": runner,
                "runner_kind": kind,
                **policy_evidence,
            }
    if kind == "unittest" and not _SAFE_UNITTEST_SELECTOR_RE.fullmatch(test_name):
        return {
            "passed": False,
            "status": "incompatible_selector",
            "reason": (
                "unittest requires a dotted Python module, class or method selector "
                "such as tests.test_module"
            ),
            "runner": runner,
            "runner_kind": kind,
            **policy_evidence,
        }
    if kind == "unittest" and test_name not in command:
        return {
            "passed": False,
            "status": "incompatible_selector",
            "reason": "unittest requires {test} as a separate selector argument",
            "runner": runner,
            "runner_kind": kind,
            **policy_evidence,
        }

    installation = _installation_readiness(
        command,
        project_root,
        runner=runner,
        kind=kind,
        policy=policy,
    )
    if not installation.get("passed"):
        return installation
    return {
        **installation,
        "reason": (
            f"test selector is compatible with resolved {kind} runner; "
            "execution remains deferred until candidate verification"
        ),
    }
