from __future__ import annotations

import atexit
import errno
import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

from samuel.core.ports import IAuditSink

log = logging.getLogger(__name__)


class AsyncAuditSink(IAuditSink):
    """JSONL-Sink mit Drain-Thread.

    Writes go into a bounded queue; a daemon worker drains them to the inner
    sink. On full queue, security-relevant events fall back to a synchronous
    sink, others are dropped with a logged WARNING.

    Lifecycle (#257): the worker is a daemon thread, so it would normally die
    on ``sys.exit`` with un-drained events. We register :py:meth:`stop` via
    :py:mod:`atexit`, which Python runs before thread cleanup. Explicit
    callers (``samuel.cli``) may call :py:meth:`stop` earlier to deterministic-
    ally flush before exit.
    """

    def __init__(
        self,
        inner: IAuditSink,
        fallback: IAuditSink,
        buffer_size: int = 100,
        *,
        diagnostic: Callable[[str, str, str], None] | None = None,
    ):
        self._diagnostic = diagnostic
        self._report_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._inner = inner
        self._fallback = fallback
        self._queue: queue.Queue[dict | None] = queue.Queue(maxsize=buffer_size)
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._stopped = False
        self._report("started")
        self._worker.start()
        atexit.register(self.stop)

    @staticmethod
    def _error_code(exc: Exception) -> str:
        # Never copy exception messages, paths, event payloads or credentials.
        cause = exc.__cause__ if isinstance(exc.__cause__, OSError) else exc
        if isinstance(cause, OSError):
            if cause.errno in {errno.EACCES, errno.EPERM}:
                return "permission_denied"
            if cause.errno == errno.ENOSPC:
                return "no_space"
            return "io_error"
        from samuel.adapters.audit.jsonl import AuditWriteError

        return "append_refused" if isinstance(exc, AuditWriteError) else "write_error"

    def _report(self, state: str, primary: str = "", fallback: str = "") -> None:
        if self._diagnostic is None:
            return
        with self._report_lock:
            try:
                self._diagnostic(state, primary, fallback)
            except Exception as exc:
                # Audit logger is excluded from the bus logging bridge.
                log.warning("Audit writer projection unavailable (%s)", type(exc).__name__)

    def _write_fallback(self, event: Any, primary_error: str) -> None:
        try:
            self._fallback.write(event)
        except Exception as exc:
            fallback_error = self._error_code(exc)
            self._report("write_failed", primary_error, fallback_error)
            log.error("Audit primary/fallback write failed (%s/%s)", primary_error, fallback_error)
        else:
            self._report("fallback_written", primary_error)
            log.warning("Audit primary degraded; fallback written (%s)", primary_error)

    def write(self, event: Any) -> None:
        with self._lifecycle_lock:
            if self._stopped:
                self._report("stopped_event_rejected", "writer_stopped")
                return
            try:
                self._queue.put_nowait(event)
                return
            except queue.Full:
                pass
        is_security = bool(
            isinstance(event, dict)
            and (
                event.get("owasp_risk")
                or event.get("lvl") == "error"
                or (
                    isinstance(event.get("payload"), dict)
                    and (
                        event["payload"].get("owasp_risk") or event["payload"].get("lvl") == "error"
                    )
                )
            )
        )
        if is_security:
            self._write_fallback(event, "queue_full")
        else:
            self._report("queue_dropped", "queue_full")
            log.warning("Audit buffer full; event dropped")

    def query(self, query: Any) -> list[Any]:
        return self._inner.query(query)

    def _drain(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                break
            try:
                self._inner.write(event)
            except Exception as exc:
                code = self._error_code(exc)
                log.warning("Audit primary write failed (%s)", code)
                self._write_fallback(event, code)
            else:
                self._report("primary_written")

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._stopped:
                return
            self._stopped = True
        try:
            self._queue.put(None, timeout=5)
        except queue.Full:
            self._report("shutdown_unconfirmed", "drain_timeout")
            return
        self._worker.join(timeout=5)
        if self._worker.is_alive():
            self._report("shutdown_unconfirmed", "drain_timeout")
