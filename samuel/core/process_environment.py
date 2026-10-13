"""Minimal process environments for code originating from a candidate."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

VERIFIER_ENVIRONMENT_PROFILE = "verifier-sterile.v1"
VERIFIER_ENVIRONMENT_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "NO_COLOR",
    "PATH",
    "PYTHONUNBUFFERED",
    "PYTHONUTF8",
    "TEMP",
    "TMP",
    "TMPDIR",
    "TZ",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "XDG_STATE_HOME",
)

_SYSTEM_EXECUTABLE_DIRS = (
    Path("/usr/local/sbin"),
    Path("/usr/local/bin"),
    Path("/usr/sbin"),
    Path("/usr/bin"),
    Path("/sbin"),
    Path("/bin"),
    Path("/usr/local/go/bin"),
    Path("/usr/local/cargo/bin"),
)


def verifier_executable_path(executable: str | None) -> str:
    """Return the exact executable search path used by verifier processes."""

    # Preserve the interpreter path as invoked.  Resolving it first drops the
    # virtual-environment ``bin`` directory when ``python`` is a symlink to the
    # system interpreter, so relative control-plane runners such as
    # ``python -m unittest`` become unavailable in the sterile environment.
    directories = [Path(sys.executable).parent]
    if executable:
        configured = Path(executable)
        if configured.is_absolute():
            directories.append(configured.resolve(strict=False).parent)
    directories.extend(_SYSTEM_EXECUTABLE_DIRS)
    unique: list[str] = []
    for directory in directories:
        value = str(directory)
        if value not in unique:
            unique.append(value)
    return os.pathsep.join(unique)


def _private_directory(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=False)
    path.chmod(0o700)
    return str(path)


@contextmanager
def verifier_process_environment(
    executable: str | None = None,
) -> Iterator[Mapping[str, str]]:
    """Yield a new allowlisted environment without inherited parent values."""

    temp_root = "/tmp" if os.name == "posix" else None
    with TemporaryDirectory(prefix="samuel-verifier-env-", dir=temp_root) as raw_root:
        root = Path(raw_root)
        home = _private_directory(root / "home")
        temporary = _private_directory(root / "tmp")
        xdg_root = root / "xdg"
        xdg_root.mkdir(mode=0o700)
        environment = {
            "HOME": home,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "NO_COLOR": "1",
            "PATH": verifier_executable_path(executable),
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
            "TEMP": temporary,
            "TMP": temporary,
            "TMPDIR": temporary,
            "TZ": "UTC",
            "XDG_CACHE_HOME": _private_directory(xdg_root / "cache"),
            "XDG_CONFIG_HOME": _private_directory(xdg_root / "config"),
            "XDG_DATA_HOME": _private_directory(xdg_root / "data"),
            "XDG_RUNTIME_DIR": _private_directory(xdg_root / "runtime"),
            "XDG_STATE_HOME": _private_directory(xdg_root / "state"),
        }
        if set(environment) != set(VERIFIER_ENVIRONMENT_KEYS):
            raise RuntimeError("verifier environment does not match its allowlist")
        yield environment
