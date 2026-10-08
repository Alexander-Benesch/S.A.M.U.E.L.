"""Shared TEST-runner policy resolution and planning/Doctor readiness checks.

The helpers inspect the operator-controlled runner policy and the bound project.
Readiness may run an explicitly bound toolchain's version probe in an empty
directory. It never runs candidate tests, installs tools or chooses a fallback.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from samuel.core.acceptance import parse_test_criterion_argument
from samuel.core.config import EvalSchema, VerifierToolchainSchema
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
    verifier_toolchain: VerifierToolchainSchema | None = None

    @classmethod
    def from_eval_config(cls, config: EvalSchema) -> VerifierRunnerPolicy:
        return cls(
            policy_version=config.test_policy_version,
            test_cmd=config.test_cmd,
            test_timeout=config.test_timeout,
            verifier_toolchain=config.verifier_toolchain,
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
        command = [part.replace("{test}", test_name) for part in parts]
        return _bind_toolchain(command, policy), timeout, "config"

    for marker, template in TEST_RUNNER_MARKERS:
        if not (project_root / marker).exists():
            continue
        if marker in {"pyproject.toml", "pytest.ini", "setup.cfg"} and "::" in test_name:
            command = [sys.executable, "-m", "pytest", "-q", test_name]
        else:
            command = [part.replace("{test}", test_name) for part in template]
        return _bind_toolchain(command, policy), timeout, marker.split(".")[0]
    return None


def _bind_toolchain(command: list[str], policy: VerifierRunnerPolicy) -> list[str]:
    if policy.verifier_toolchain is None:
        return command
    validate_toolchain(policy.verifier_toolchain)
    if runner_kind(command) != "pytest" or command[1:3] != ["-m", "pytest"]:
        raise ValueError("bound Python toolchain requires python -m pytest")
    executable = _runner_executable(command, Path.cwd())
    if executable is None or executable.resolve() != Path(sys.executable).resolve():
        raise ValueError("bound toolchain requires the active Samuel Python interpreter")
    packages = str(Path(policy.verifier_toolchain.manifest).parent / "packages")
    return [sys.executable, "-I", "-c", TOOLCHAIN_RUN_SCRIPT, packages, "pytest", *command[3:]]


def runner_kind(command: list[str]) -> str:
    """Classify only runner forms whose selector grammar is known here."""

    executable = Path(command[0]).name.casefold() if command else ""
    if command[1:4] == ["-I", "-c", TOOLCHAIN_RUN_SCRIPT]:
        return "pytest"
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
    if policy.verifier_toolchain is not None:
        if not _runner_metadata_probe(command[:6] + ["--version"]):
            return {
                "passed": False,
                "status": "missing_evidence",
                "reason": "bound pytest toolchain cannot run in the sterile environment",
                **evidence,
            }
        evidence["toolchain_sha256"] = policy.verifier_toolchain.sha256
    elif "-m" in command and kind in {"pytest", "unittest"}:
        module_index = command.index("-m") + 1
        module = command[module_index] if module_index < len(command) else ""
        same_python_environment = (
            executable.resolve() == Path(sys.executable).resolve()
            and executable.parent.resolve() == Path(sys.executable).parent.resolve()
        )
        if module == "unittest":
            module_available = True
        elif same_python_environment:
            module_available = _runner_metadata_probe(
                [
                    str(executable),
                    "-I",
                    "-c",
                    "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('pytest') is not None else 1)",
                ]
            )
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


def _runner_metadata_probe(command: list[str]) -> bool:
    import subprocess
    import tempfile

    from samuel.core.process_environment import verifier_process_environment

    try:
        with (
            tempfile.TemporaryDirectory(prefix="samuel-toolchain-probe-") as probe_root,
            verifier_process_environment(command[0]) as environment,
        ):
            probe = subprocess.run(
                command,
                cwd=probe_root,
                env=environment,
                capture_output=True,
                timeout=8,
                check=False,
            )
        return probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


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
    try:
        resolved = resolve_test_runner(project_root, "samuel_readiness_probe", policy)
    except (ValueError, OSError) as exc:
        return {
            "passed": False,
            "status": "missing_evidence",
            "reason": str(exc),
            **policy_evidence,
        }
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

    try:
        resolved = resolve_test_runner(project_root, test_name, policy)
    except (ValueError, OSError) as exc:
        return {
            "passed": False,
            "status": "missing_evidence",
            "reason": str(exc),
            **policy_evidence,
        }
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


TOOLCHAIN_RUN_SCRIPT = """import os,runpy,sys
root,module,*args=sys.argv[1:]
sys.dont_write_bytecode=True
sys.path=[root,os.getcwd()]+[p for p in sys.path if 'site-packages' not in p and 'dist-packages' not in p]
sys.argv=[module]+args
runpy.run_module(module,run_name='__main__',alter_sys=True)
"""


def python_identity() -> dict[str, Any]:
    return {
        "implementation": sys.implementation.name,
        "version": list(sys.version_info[:3]),
        "platform": platform.system(),
        "machine": platform.machine(),
        "cache_tag": sys.implementation.cache_tag,
        "runtime_version": importlib.metadata.version("samuel"),
        "runtime_revision": os.environ.get("SAMUEL_BUILD_REVISION", ""),
    }


def artifact_files(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("verifier toolchain packages directory is missing or unsafe")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.suffix == ".pth":
            raise ValueError("verifier toolchain contains a symlink or unsupported .pth file")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif not path.is_dir():
            raise ValueError("verifier toolchain contains a non-regular entry")
    if not files:
        raise ValueError("verifier toolchain is empty")
    return files


def validate_toolchain(binding: VerifierToolchainSchema) -> dict[str, Any]:
    path = Path(binding.manifest)
    if any(parent.is_symlink() for parent in (path, *path.parents)) or not path.is_file():
        raise ValueError("verifier toolchain manifest is missing or unsafe")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding.sha256:
        raise ValueError("verifier toolchain manifest digest mismatch")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported verifier toolchain manifest")
    if manifest.get("python") != python_identity():
        raise ValueError("verifier toolchain Python/platform/release identity mismatch")
    if manifest.get("files") != artifact_files(path.parent / "packages"):
        raise ValueError("verifier toolchain contents changed")
    lock = path.parent / "requirements.lock"
    if lock.is_symlink() or not lock.is_file():
        raise ValueError("verifier toolchain lock is missing or unsafe")
    if hashlib.sha256(lock.read_bytes()).hexdigest() != manifest.get("lock_sha256"):
        raise ValueError("verifier toolchain lock digest mismatch")
    versions = {
        dist.metadata["Name"]: dist.version
        for dist in importlib.metadata.distributions(path=[str(path.parent / "packages")])
    }
    if manifest.get("distributions") != versions or "pytest" not in versions:
        raise ValueError("verifier toolchain distribution identity mismatch or pytest absent")
    return manifest
