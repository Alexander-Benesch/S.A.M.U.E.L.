from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from samuel.core.commands import Command
from samuel.core.events import (
    AuditEvent,
    Event,
)

log = logging.getLogger(__name__)

Handler = Callable[[Any], Any]
Middleware = Callable[[Event | Command, Callable[..., Any]], Any]


HandledCommandErrorClass = Literal["not_found", "aborted", "internal"]


@dataclass(frozen=True, slots=True)
class HandledCommandFailure:
    """Bounded outcome for a command failure consumed by ``ErrorMiddleware``.

    The value deliberately carries no exception message or provider payload.
    It lets synchronous adapters distinguish a handled failure from a valid
    handler result of ``None`` without making exceptions the workflow API.
    """

    error_class: HandledCommandErrorClass
    reason_code: str
    correlation_id: str
    command_name: str
    issue: int | None = None

    def __bool__(self) -> bool:
        """Remain false-y for legacy CLI/health consumers of optional results."""

        return False


# ErrorMiddleware intentionally converts command exceptions into structured
# workflow evidence instead of raising them through the CLI.  Keep the error
# type in the current execution context so an enclosing AuditMiddleware does
# not record that handled failure as a successful command.  Nested event
# publication receives its own token and restores this command value.
_handled_command_error: ContextVar[str | None] = ContextVar(
    "samuel_handled_command_error",
    default=None,
)


class DeadLetterQueue:
    """#334: Persistenter Speicher fuer Events, deren Handler crashen.

    Ohne DLQ verschwindet ein Event still, wenn sein Subscriber eine Exception
    wirft (``Bus.publish`` isoliert Handler bewusst, damit ein fehlerhafter
    Subscriber die anderen nicht blockiert — aber das Event ist dann verloren).
    Die DLQ macht den Verlust sichtbar und wiederherstellbar (CLI
    ``samuel dlq list|replay``).

    Append-only JSONL, thread-safe. Eine Zeile pro fehlgeschlagenem
    (Event, Handler)-Paar mit ``id, ts, event_name, handler, error, stack,
    payload, correlation_id``.
    """

    def __init__(self, path: Path | None = None):
        self._lock = threading.Lock()
        self._path = path

    def record(
        self,
        *,
        event_name: str,
        payload: dict,
        error: str,
        stack: str = "",
        handler: str = "",
        correlation_id: str | None = None,
    ) -> str:
        from datetime import datetime, timezone
        from uuid import uuid4

        entry_id = str(uuid4())
        entry = {
            "id": entry_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_name": event_name,
            "handler": handler,
            "error": error,
            "stack": stack,
            "payload": payload if isinstance(payload, dict) else {},
            "correlation_id": correlation_id or "",
        }
        if self._path is None:
            return entry_id
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                log.warning("Failed to persist dead-letter entry")
        return entry_id

    def list(self, limit: int | None = None) -> list[dict]:
        """Neueste zuerst. ``limit=None`` -> alle."""
        if self._path is None or not self._path.exists():
            return []
        rows: list[dict] = []
        with self._lock:
            try:
                for line in self._path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except OSError:
                return []
        rows.reverse()
        return rows[:limit] if limit else rows

    def get(self, entry_id: str) -> dict | None:
        for row in self.list():
            if row.get("id") == entry_id:
                return row
        return None


class Bus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._command_handlers: dict[str, Handler] = {}
        self._middlewares: list[Middleware] = []
        # Optional runtime references (set by bootstrap)
        self.scm: Any = None
        self.config: Any = None
        self.audit_sink: Any = None
        self.llm_activity_resolver: Callable[[], dict[str, Any]] | None = None
        self.session: Any = None
        self.sequence: Any = None
        self.labels: Any = None
        self.dlq: Any = None  # #334: DeadLetterQueue, gesetzt von bootstrap
        self.audit_diagnostic_handler: Any = None
        self.state_store: Any = None
        self.observation_store: Any = None
        self.run_projection_store: Any = None
        self.quality_registry: Any = None
        self.authority_state_store: Any = None
        self.retention_coordinator: Any = None
        self.workspace_manager: Any = None
        self.resume_coordinator: Any = None
        self._closed = False

    def close(self) -> None:
        """Release process-global diagnostics and drain owned audit sinks."""

        if self._closed:
            return
        self._closed = True

        from samuel.core.logging import detach_audit_diagnostics

        detach_audit_diagnostics(self.audit_diagnostic_handler)
        self.audit_diagnostic_handler = None

        sinks: list[Any] = []
        if self.audit_sink is not None:
            sinks.append(self.audit_sink)
        for middleware in self._middlewares:
            sink = getattr(middleware, "_sink", None)
            if sink is not None and all(sink is not known for known in sinks):
                sinks.append(sink)
        for sink in sinks:
            stop = getattr(sink, "stop", None)
            if not callable(stop):
                continue
            try:
                stop()
            except Exception:
                log.exception("Audit-Sink stop() failed")

    def add_middleware(self, mw: Middleware) -> None:
        self._middlewares.append(mw)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        self._subscribers[event_name].append(handler)

    def register_command(self, command_name: str, handler: Handler) -> None:
        self._command_handlers[command_name] = handler

    def has_handler(self, command_name: str) -> bool:
        return command_name in self._command_handlers

    def publish(self, event: Event) -> None:
        # A workflow-budget key is a digest identity, never a credential.  It
        # follows the existing synchronous event/command chain so later
        # phases reuse the admission created before Planning instead of
        # inventing authority from a correlation ID.
        from samuel.core.issue_context import current_budget_admission

        budget_admission_key = current_budget_admission()
        if budget_admission_key and "budget_admission_key" not in event.payload:
            event.payload["budget_admission_key"] = budget_admission_key

        def dispatch(msg: Event | Command) -> None:
            for handler in self._subscribers.get(msg.name, []):
                try:
                    handler(msg)
                except Exception as exc:
                    self._dead_letter(msg, handler, exc)
            for handler in self._subscribers.get("*", []):
                try:
                    handler(msg)
                except Exception as exc:
                    self._dead_letter(msg, handler, exc, wildcard=True)

        self._run_through_middlewares(event, dispatch)

    def _dead_letter(
        self,
        msg: Event | Command,
        handler: Handler,
        exc: Exception,
        *,
        wildcard: bool = False,
    ) -> None:
        """#334: Handler-Crash protokollieren UND in die DLQ schreiben.

        Handler bleiben isoliert (ein Fehler stoppt die anderen Subscriber
        nicht), aber das Event ist nicht mehr still verloren.
        """
        kind = "Wildcard handler" if wildcard else "Handler"
        log.exception("%s error for event %s", kind, msg.name)
        if self.dlq is None:
            return
        import traceback

        try:
            self.dlq.record(
                event_name=msg.name,
                payload=getattr(msg, "payload", {}) or {},
                error=type(exc).__name__ + ": " + str(exc),
                stack="".join(traceback.format_exception(exc)),
                handler=getattr(handler, "__qualname__", repr(handler)),
                correlation_id=getattr(msg, "correlation_id", None),
            )
        except Exception:
            log.exception("Failed to record dead-letter for %s", msg.name)

    def send(self, command: Command) -> Any:
        def dispatch(msg: Event | Command) -> Any:
            handler = self._command_handlers.get(msg.name)
            if handler is None:
                from samuel.core.events import UnhandledCommand

                self.publish(UnhandledCommand(payload={"command": msg.name}))
                log.warning("No handler for command: %s", msg.name)
                return None
            return handler(msg)

        return self._run_through_middlewares(command, dispatch)

    def _run_through_middlewares(
        self,
        msg: Event | Command,
        final: Callable[[Event | Command], Any],
    ) -> Any:
        chain: Callable[[Event | Command], Any] = final
        for mw in reversed(self._middlewares):
            prev = chain

            def chain(
                m: Event | Command,
                _prev: Callable[[Event | Command], Any] = prev,
                _mw: Middleware = mw,
            ) -> Any:
                return _mw(m, _prev)

        return chain(msg)


# --- Middlewares ---


class IdempotencyStore:
    def __init__(self, path: Path | None = None, ttl_hours: int = 24):
        self._lock = threading.Lock()
        self._processing = threading.Condition(self._lock)
        self._processing_owners: dict[str, int] = {}
        self._path = path
        self._ttl = ttl_hours * 3600
        self._keys: dict[str, float] = {}
        if path and path.exists():
            try:
                self._keys = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                self._keys = {}

    def has_key(self, key: str) -> bool:
        with self._lock:
            self._evict()
            return key in self._keys

    def set_key(self, key: str) -> None:
        with self._lock:
            self._keys[key] = time.time()
            self._persist()

    @contextmanager
    def processing_key(self, key: str) -> Iterator[bool]:
        """Serialize one in-process key without holding the store lock during dispatch.

        Completion is persisted only after dispatch returns, as before. A failed
        dispatch releases the claim without recording the key, so a waiting
        delivery can retry. A process exit also loses only the in-flight claim.
        """
        owner = threading.get_ident()
        nested = False
        with self._processing:
            while key in self._processing_owners:
                if self._processing_owners[key] == owner:
                    # A nested delivery with the same key cannot dispatch again.
                    nested = True
                    break
                self._processing.wait()
            if not nested:
                self._processing_owners[key] = owner
        if nested:
            yield False
            return
        try:
            yield True
        finally:
            with self._processing:
                del self._processing_owners[key]
                self._processing.notify_all()

    def _evict(self) -> None:
        cutoff = time.time() - self._ttl
        self._keys = {k: v for k, v in self._keys.items() if v > cutoff}

    def _persist(self) -> None:
        if self._path:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(json.dumps(self._keys))
            except OSError:
                log.warning("Failed to persist idempotency store")


class IdempotencyMiddleware:
    def __init__(self, store: IdempotencyStore | None = None):
        self._store = store or IdempotencyStore()

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        key = msg.idempotency_key if isinstance(msg, Command) else None
        if isinstance(msg, Event) and isinstance(msg.payload, dict):
            event_key = msg.payload.get("idempotency_key")
            if isinstance(event_key, str) and event_key:
                key = event_key
        if not key:
            return next_(msg)
        with self._store.processing_key(key) as acquired:
            if not acquired or self._store.has_key(key):
                log.info(
                    "Deduplicated %s: %s", "command" if isinstance(msg, Command) else "event", key
                )
                return None
            result = next_(msg)
            self._store.set_key(key)
            return result


def scrub_secrets(text: str) -> str:
    """Replace known secret patterns in *text* with ``***REDACTED***``."""
    from samuel.core.security_policy import redact_secrets

    return redact_secrets(text)


def _scrub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an audit copy with secrets scrubbed and source diffs omitted."""
    scrubbed: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "diff" and isinstance(value, str):
            scrubbed[key] = "***SOURCE_DIFF_OMITTED***"
        elif isinstance(value, str):
            scrubbed[key] = scrub_secrets(value)
        else:
            scrubbed[key] = value
    return scrubbed


class AuditMiddleware:
    def __init__(self, sink: Any | None = None):
        self._sink = sink

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        start = time.monotonic()
        error: str | None = None
        failure_token = _handled_command_error.set(None)
        try:
            result = next_(msg)
        except Exception as exc:
            error = type(exc).__name__
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            self._write_audit(msg, duration_ms, error)
            raise
        else:
            error = _handled_command_error.get()
            if error is None and isinstance(result, HandledCommandFailure):
                error = result.reason_code
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            self._write_audit(msg, duration_ms, error)
            return result
        finally:
            _handled_command_error.reset(failure_token)

    def _write_audit(self, msg: Event | Command, duration_ms: float, error: str | None) -> None:
        if not self._sink:
            return
        try:
            original_payload = getattr(msg, "payload", None) or {}
            if not isinstance(original_payload, dict):
                original_payload = {}
            payload = {
                **original_payload,
                "message_type": type(msg).__name__,
                "message_name": msg.name,
                "correlation_id": getattr(msg, "correlation_id", None),
                "duration_ms": duration_ms,
            }
            if error is not None:
                payload["error"] = error
            self._sink.write(AuditEvent(payload=_scrub_payload(payload)))
        except Exception:
            log.exception("Audit write failed")


class ErrorMiddleware:
    def __init__(self, bus: Any | None = None):
        self._bus = bus

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        try:
            return next_(msg)
        except Exception as exc:
            log.exception("Error processing %s", msg.name)
            if isinstance(msg, Command):
                failure = self._command_failure(msg, exc)
                _handled_command_error.set(failure.reason_code)
                if self._bus is not None:
                    self._publish_command_diagnostic(msg, exc, failure)
                    self._publish_command_abort(msg, exc, failure)
                return failure
            return None

    @classmethod
    def _command_failure(cls, msg: Command, exc: Exception) -> HandledCommandFailure:
        from samuel.core.errors import AgentAbort

        if isinstance(exc, AgentAbort):
            error_class: HandledCommandErrorClass = "aborted"
            reason_code = "workflow_aborted"
        elif getattr(exc, "status", None) == 404:
            error_class = "not_found"
            reason_code = "command_target_not_found"
        else:
            error_class = "internal"
            reason_code = "internal_command_error"
        return HandledCommandFailure(
            error_class=error_class,
            reason_code=reason_code,
            correlation_id=getattr(msg, "correlation_id", "") or "",
            command_name=msg.name,
            issue=cls._command_issue(msg),
        )

    @staticmethod
    def _command_issue(msg: Command) -> int | None:
        issue = msg.payload.get("issue") if isinstance(msg.payload, dict) else None
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            issue_number = getattr(msg, "issue_number", 0)
            issue = (
                issue_number
                if isinstance(issue_number, int)
                and not isinstance(issue_number, bool)
                and issue_number > 0
                else None
            )
        return issue if isinstance(issue, int) else None

    def _publish_command_diagnostic(
        self,
        msg: Command,
        exc: Exception,
        failure: HandledCommandFailure,
    ) -> None:
        from samuel.core.errors import AgentAbort, describe_diagnostic
        from samuel.core.events import DiagnosticRaised

        bus = self._bus
        if bus is None or isinstance(exc, AgentAbort):
            return
        reason = failure.reason_code
        payload: dict[str, Any] = {
            "level": "error",
            "category": "system",
            "reason": reason,
            "logger": "samuel.core.bus",
            "file": "samuel/core/bus.py",
            "line": 0,
            "error_class": failure.error_class,
            "provenance": "runtime",
            "source_command": msg.name,
            **describe_diagnostic(
                logger="samuel.core.bus",
                reason=reason,
                category="system",
                event_name="DiagnosticRaised",
            ),
        }
        issue = self._command_issue(msg)
        if issue is not None:
            payload["issue"] = issue
        try:
            bus.publish(
                DiagnosticRaised(
                    payload=payload,
                    correlation_id=getattr(msg, "correlation_id", "") or "",
                )
            )
        except Exception:
            # Diagnostic delivery must never recurse or hide the authoritative
            # terminal WorkflowAborted event emitted immediately afterwards.
            log.warning("Failed to publish DiagnosticRaised for command failure")

    def _publish_command_abort(
        self,
        msg: Command,
        exc: Exception,
        failure: HandledCommandFailure,
    ) -> None:
        from samuel.core.errors import AgentAbort
        from samuel.core.events import WorkflowAborted

        bus = self._bus
        if bus is None:
            return
        if isinstance(exc, AgentAbort):
            payload: dict[str, Any] = {
                "reason": str(exc),
                "gate": exc.gate,
                "issue": exc.issue,
                "source_command": msg.name,
            }
        else:
            payload = {
                "reason": failure.reason_code,
                "error_class": failure.error_class,
                "source_command": msg.name,
            }
            issue = self._command_issue(msg)
            if issue is not None:
                payload["issue"] = issue

        try:
            bus.publish(
                WorkflowAborted(
                    payload=payload,
                    correlation_id=getattr(msg, "correlation_id", "") or "",
                )
            )
        except Exception:
            log.warning("Failed to publish WorkflowAborted for command failure")


class MetricsMiddleware:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counts: dict[str, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self.total_ms: dict[str, float] = defaultdict(float)

    def __call__(self, msg: Event | Command, next_: Callable) -> Any:
        start = time.monotonic()
        try:
            result = next_(msg)
            with self._lock:
                if isinstance(result, HandledCommandFailure):
                    self.errors[msg.name] += 1
                else:
                    self.counts[msg.name] += 1
                self.total_ms[msg.name] += (time.monotonic() - start) * 1000
            return result
        except Exception:
            with self._lock:
                self.errors[msg.name] += 1
            raise
