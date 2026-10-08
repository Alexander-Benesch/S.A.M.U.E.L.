from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class AuditDiagnosticHandler(logging.Handler):
    """Mirror WARNING/ERROR records to the event bus without log recursion."""

    _EXCLUDED_PREFIXES = (
        "samuel.adapters.audit",
        "samuel.slices.audit_trail",
        "samuel.core.bus",
        "samuel.core.logging",
    )

    def __init__(self, bus: Any) -> None:
        super().__init__(level=logging.WARNING)
        self._bus = bus
        self._local = threading.local()

    @staticmethod
    def _category(logger_name: str) -> str:
        parts = set(logger_name.split("."))
        for category in (
            "llm",
            "dashboard",
            "planning",
            "implementation",
            "review",
            "healing",
            "gitea",
            "github",
            "config",
            "setup",
            "watch",
        ):
            if category in parts:
                return "scm" if category in {"gitea", "github"} else category
        return "system"

    @staticmethod
    def _source_file(pathname: str) -> str:
        try:
            path = Path(pathname).resolve()
            return str(path.relative_to(Path.cwd().resolve()))
        except (OSError, ValueError):
            return Path(pathname).name

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(self._EXCLUDED_PREFIXES):
            return
        if getattr(self._local, "active", False):
            return
        self._local.active = True
        try:
            from samuel.core.events import DiagnosticRaised
            from samuel.core.issue_context import current_issue, current_workflow_correlation

            category = self._category(record.name)
            reason = record.getMessage()
            from samuel.core.errors import describe_diagnostic

            payload: dict[str, Any] = {
                "level": record.levelname.lower(),
                "category": category,
                "reason": reason,
                "logger": record.name,
                "file": self._source_file(record.pathname),
                "line": record.lineno,
                "exception": (
                    record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else ""
                ),
                "provenance": "runtime",
                **describe_diagnostic(
                    logger=record.name,
                    reason=reason,
                    category=category,
                    event_name="DiagnosticRaised",
                ),
            }
            issue = current_issue()
            if issue is not None:
                payload["issue"] = issue
            workflow_correlation = current_workflow_correlation()
            event = (
                DiagnosticRaised(payload=payload, correlation_id=workflow_correlation)
                if workflow_correlation
                else DiagnosticRaised(payload=payload)
            )
            self._bus.publish(event)
        except Exception:
            # A logging handler must never raise into application code.  Do not
            # log here: that would recurse through this same handler.
            self.handleError(record)
        finally:
            self._local.active = False


def attach_audit_diagnostics(bus: Any) -> AuditDiagnosticHandler:
    """Attach exactly one audit bridge to the SAMUEL logger tree."""

    root = logging.getLogger("samuel")
    for existing in list(root.handlers):
        if isinstance(existing, AuditDiagnosticHandler):
            root.removeHandler(existing)
    handler = AuditDiagnosticHandler(bus)
    root.addHandler(handler)
    return handler


def detach_audit_diagnostics(handler: AuditDiagnosticHandler | None = None) -> None:
    """Detach an audit bridge without disturbing regular log handlers.

    ``bootstrap`` installs a process-global handler on the ``samuel`` logger.
    Long-lived test processes and embedded users therefore need an explicit
    lifecycle operation; otherwise a warning emitted after a runtime ended is
    still written through the old bus and its audit sink.
    """

    root = logging.getLogger("samuel")
    for existing in list(root.handlers):
        if not isinstance(existing, AuditDiagnosticHandler):
            continue
        if handler is not None and existing is not handler:
            continue
        root.removeHandler(existing)
        existing.close()


def setup_logging(
    level: str = "INFO", log_file: str | None = None, max_log_size_mb: int = 10
) -> None:
    root = logging.getLogger("samuel")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not root.handlers:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)

        if log_file:
            max_bytes = max_log_size_mb * 1024 * 1024
            fh = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
