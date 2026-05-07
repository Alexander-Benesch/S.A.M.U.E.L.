from __future__ import annotations

import atexit
import logging
import queue
import threading
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
    ):
        self._inner = inner
        self._fallback = fallback
        self._queue: queue.Queue[dict | None] = queue.Queue(maxsize=buffer_size)
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._stopped = False
        self._worker.start()
        atexit.register(self.stop)

    def write(self, event: Any) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            is_security = bool(
                (isinstance(event, dict) and event.get("owasp_risk"))
                or (isinstance(event, dict) and event.get("lvl") == "error")
                or (
                    isinstance(event, dict)
                    and isinstance(event.get("payload"), dict)
                    and (event["payload"].get("owasp_risk") or event["payload"].get("lvl") == "error")
                )
            )
            if is_security:
                self._fallback.write(event)
            else:
                log.warning("Audit-Buffer voll — Event verworfen")

    def query(self, query: Any) -> list[Any]:
        return self._inner.query(query)

    def _drain(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                break
            try:
                self._inner.write(event)
            except Exception:
                log.exception("AsyncAuditSink inner write failed")
                try:
                    self._fallback.write(event)
                except Exception:
                    log.exception("AsyncAuditSink fallback write also failed")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._queue.put(None)
        self._worker.join(timeout=5)
