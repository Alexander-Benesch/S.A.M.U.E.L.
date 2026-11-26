"""Explicit authority boundary for operator configuration mutations."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, Literal, cast

ConfigurationMode = Literal["production", "setup"]

CONFIGURATION_MODE_ENV = "SAMUEL_CONFIGURATION_MODE"
CONFIGURATION_FROZEN = "configuration_frozen"


def serialized_configuration_write(
    *,
    success_field: str = "updated",
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Keep a handler's setup authorization and complete write under one fence."""

    def decorate(method: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @wraps(method)
        def guarded(self: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
            from samuel.core.configuration_session import ConfigurationConflict

            authority: ConfigurationAuthority = self._configuration_authority
            # Preserve the handler's existing production/error response contract.
            if not authority.writable or authority.session is None:
                return method(self, *args, **kwargs)
            try:
                with authority.session.configuration_write(setup=True):
                    return method(self, *args, **kwargs)
            except ConfigurationConflict as exc:
                return {
                    success_field: False,
                    "code": CONFIGURATION_FROZEN,
                    "error": str(exc),
                    "errors": [str(exc)],
                    "configuration": authority.status(),
                }

        return guarded

    return decorate


def resolve_configuration_mode(value: str | None = None) -> tuple[ConfigurationMode, str]:
    """Resolve one explicit process mode without inferring write authority."""

    if value is None:
        raw = os.environ.get(CONFIGURATION_MODE_ENV)
        source = "environment" if raw is not None else "shipped_default"
    else:
        raw = value
        source = "command_line"
    normalized = str(raw or "production").strip().lower()
    if normalized not in {"production", "setup"}:
        raise ValueError(f"{CONFIGURATION_MODE_ENV} must be 'production' or 'setup'")
    return cast(ConfigurationMode, normalized), source


def _configuration_digest(config_dir: Path, *, exclude_llm: bool = False) -> str | None:
    """Hash non-secret operator files; environment secrets are deliberately excluded."""

    digest = hashlib.sha256()
    try:
        if config_dir.is_dir():
            paths = sorted(
                path
                for path in config_dir.rglob("*")
                if path.is_file()
                and not path.is_symlink()
                and path.suffix in {".json", ".md"}
                and not path.name.endswith((".tmp", ".rollback"))
            )
            for path in paths:
                if exclude_llm and path.relative_to(config_dir).as_posix() in {
                    "llm.json",
                    "llm/defaults.json",
                }:
                    continue
                if exclude_llm and path.relative_to(config_dir).as_posix().startswith(
                    "llm/prompts/"
                ):
                    continue
                relative = path.relative_to(config_dir).as_posix().encode("utf-8")
                content = path.read_bytes()
                digest.update(len(relative).to_bytes(8, "big"))
                digest.update(relative)
                digest.update(len(content).to_bytes(8, "big"))
                digest.update(content)
    except OSError:
        return None
    return f"sha256:{digest.hexdigest()}"


class ConfigurationAuthority:
    """Process-scoped mode and stored/effective configuration projection."""

    def __init__(
        self,
        mode: ConfigurationMode,
        *,
        source: str,
        config_dir: Path | str,
    ) -> None:
        if mode not in {"production", "setup"}:
            raise ValueError("configuration mode must be production or setup")
        self._mode = mode
        self._source = source
        self._config_dir = Path(config_dir)
        self._effective_digest = _configuration_digest(self._config_dir)
        self._other_digest = _configuration_digest(self._config_dir, exclude_llm=True)
        self._persisted_change = False
        self.session: Any = None

    @classmethod
    def resolve(
        cls,
        config_dir: Path | str,
        value: str | None = None,
    ) -> ConfigurationAuthority:
        mode, source = resolve_configuration_mode(value)
        return cls(mode, source=source, config_dir=config_dir)

    @property
    def writable(self) -> bool:
        return self._mode == "setup"

    def mark_persisted(self) -> None:
        self._persisted_change = True

    def activated(self) -> None:
        if self._other_digest != _configuration_digest(self._config_dir, exclude_llm=True):
            self._persisted_change = True
            return
        self._effective_digest = _configuration_digest(self._config_dir)
        self._persisted_change = False

    def status(self) -> dict[str, Any]:
        stored_digest = _configuration_digest(self._config_dir)
        restart_required = (
            self._persisted_change
            or stored_digest is None
            or self._effective_digest is None
            or stored_digest != self._effective_digest
        )
        return {
            "session": self.session.state() if self.session is not None else None,
            "mode": self._mode,
            "source": self._source,
            "writable": self.writable,
            "stored_config_digest": stored_digest,
            "effective_config_digest": self._effective_digest,
            "digest_status": (
                "available"
                if stored_digest is not None and self._effective_digest is not None
                else "unavailable"
            ),
            "restart_required": restart_required,
            "secret_environment_in_digest": False,
        }

    def blocked_result(self, *, success_field: str = "updated") -> dict[str, Any] | None:
        if self.writable and (self.session is None or self.session.setup_writes_allowed()):
            return None
        return {
            success_field: False,
            "code": CONFIGURATION_FROZEN,
            "error": (
                "operator configuration is frozen in production mode; "
                "use the dashboard configuration mode for LLM settings; setup is for installation"
            ),
            "configuration": self.status(),
        }
