from __future__ import annotations

import logging
from typing import Any

from samuel.core.bus import AuditMiddleware, Bus
from samuel.core.issue_context import issue_scope
from samuel.core.logging import (
    AuditDiagnosticHandler,
    attach_audit_diagnostics,
    detach_audit_diagnostics,
    setup_logging,
)


def test_setup_logging_creates_handler():
    logger = logging.getLogger("samuel")
    logger.handlers.clear()
    setup_logging(level="DEBUG")
    assert len(logger.handlers) >= 1
    assert logger.level == logging.DEBUG


def test_setup_logging_no_duplicate_handlers():
    logger = logging.getLogger("samuel")
    logger.handlers.clear()
    setup_logging(level="INFO")
    count = len(logger.handlers)
    setup_logging(level="INFO")
    assert len(logger.handlers) == count


def test_warning_is_mirrored_as_structured_diagnostic():
    logger = logging.getLogger("samuel.adapters.llm.example")
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("DiagnosticRaised", events.append)
    handler = AuditDiagnosticHandler(bus)
    record = logger.makeRecord(
        logger.name,
        logging.WARNING,
        __file__,
        42,
        "provider failed: %s",
        ("timeout",),
        None,
    )

    with issue_scope(429):
        handler.emit(record)

    assert len(events) == 1
    payload = events[0].payload
    assert payload["level"] == "warning"
    assert payload["category"] == "llm"
    assert payload["reason"] == "provider failed: timeout"
    assert payload["issue"] == 429
    assert payload["file"].endswith("tests/test_core_logging.py")
    assert payload["provenance"] == "runtime"
    assert payload["problem_type"] == "llm_provider"
    assert payload["title"] == "LLM-Aufruf fehlgeschlagen"
    assert payload["cause"]
    assert payload["impact"]
    assert payload["next_steps"]


def test_warning_inherits_bound_workflow_correlation():
    logger = logging.getLogger("samuel.adapters.llm.example")
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("DiagnosticRaised", events.append)
    handler = AuditDiagnosticHandler(bus)
    record = logger.makeRecord(
        logger.name,
        logging.WARNING,
        __file__,
        42,
        "retrying provider",
        (),
        None,
    )

    with issue_scope(429, "planning-run-429"):
        handler.emit(record)

    assert len(events) == 1
    assert events[0].payload["issue"] == 429
    assert events[0].correlation_id == "planning-run-429"


def test_attach_audit_diagnostics_replaces_existing_bridge():
    logger = logging.getLogger("samuel")
    logger.handlers.clear()
    try:
        attach_audit_diagnostics(Bus())
        attach_audit_diagnostics(Bus())

        assert sum(isinstance(h, AuditDiagnosticHandler) for h in logger.handlers) == 1
    finally:
        logger.handlers.clear()


def test_detach_audit_diagnostics_removes_only_requested_bridge():
    logger = logging.getLogger("samuel")
    logger.handlers.clear()
    console = logging.NullHandler()
    logger.addHandler(console)
    handler = attach_audit_diagnostics(Bus())

    detach_audit_diagnostics(handler)

    assert logger.handlers == [console]


def test_warning_reaches_audit_middleware_as_diagnostic_event():
    class Sink:
        def __init__(self) -> None:
            self.events: list[Any] = []

        def write(self, event) -> None:
            self.events.append(event)

    sink = Sink()
    bus = Bus()
    bus.add_middleware(AuditMiddleware(sink))
    handler = AuditDiagnosticHandler(bus)
    logger = logging.getLogger("samuel.slices.implementation.context_builder")
    record = logger.makeRecord(
        logger.name,
        logging.ERROR,
        __file__,
        73,
        "skeleton failed",
        (),
        None,
    )

    handler.emit(record)

    assert len(sink.events) == 1
    payload = sink.events[0].payload
    assert payload["message_name"] == "DiagnosticRaised"
    assert payload["level"] == "error"
    assert payload["category"] == "implementation"


def test_prompt_fallback_emits_only_real_read_problem_to_bound_audit(tmp_path):
    from samuel.adapters.llm.prompts import load_system_prompt

    bus = Bus()
    events: list[Any] = []
    bus.subscribe("DiagnosticRaised", events.append)
    handler = AuditDiagnosticHandler(bus)
    logger = logging.getLogger("samuel.adapters.llm.prompts")
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    try:
        with issue_scope(890, "prompt-read-890"):
            assert load_system_prompt("planner.md", tmp_path, provider="test", model="test")
            assert events == []
            override = tmp_path / "llm/prompts/planner.md"
            override.parent.mkdir(parents=True)
            override.write_bytes(b"\xff")
            assert load_system_prompt("planner.md", tmp_path, provider="test", model="test")
        assert len(events) == 1
        diagnostic = events[0]
        assert diagnostic.payload["issue"] == 890
        assert diagnostic.correlation_id == "prompt-read-890"
        assert diagnostic.payload["level"] == "warning"
        assert diagnostic.payload["title"] == "Promptkonfiguration prüfen"
        assert diagnostic.payload["problem_type"] == "configuration"
        assert "UnicodeDecodeError" in diagnostic.payload["reason"]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
