"""Suiteweite Isolation von lokaler S.A.M.U.E.L.-Konfiguration."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator

import pytest


def _is_project_environment_key(key: str) -> bool:
    return (
        key.startswith(("SAMUEL_", "SCM_", "GITEA_"))
        or key.endswith("_API_KEY")
        or key == "SLICE_HMAC_KEY"
    )


@pytest.fixture(autouse=True)
def isolate_project_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests duerfen weder von lokaler `.env` abhaengen noch sie weiterreichen.

    Der Snapshot stellt auch Variablen wieder her, die Produktivcode direkt in
    ``os.environ`` schreibt und daher nicht vom ``monkeypatch``-Undo erfasst
    wuerden.
    """
    before = os.environ.copy()
    for key in tuple(os.environ):
        if _is_project_environment_key(key):
            monkeypatch.delenv(key, raising=False)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


@pytest.fixture(autouse=True)
def isolate_samuel_logging() -> Iterator[None]:
    """Do not let bootstrapped audit bridges escape their owning test.

    This specifically protects production-style relative audit paths from
    receiving warnings intentionally emitted by later negative-path tests.
    """

    from samuel.core.logging import AuditDiagnosticHandler

    logger = logging.getLogger("samuel")
    before_handlers = list(logger.handlers)
    before_level = logger.level
    try:
        yield
    finally:
        for handler in list(logger.handlers):
            if handler in before_handlers:
                continue
            if isinstance(handler, AuditDiagnosticHandler):
                bus = getattr(handler, "_bus", None)
                close = getattr(bus, "close", None)
                if callable(close):
                    close()
            if handler in logger.handlers:
                logger.removeHandler(handler)
                handler.close()
        logger.handlers[:] = before_handlers
        logger.setLevel(before_level)
