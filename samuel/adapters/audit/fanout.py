"""#368 Task 5: Fan-out-Audit-Sink — schreibt jedes Event in mehrere Sinks.

Erlaubt parallele Sinks (z.B. JSONL als Volltranskript + SARIF als Findings-
Export), ohne dass die AuditMiddleware mehrere Sinks kennen muss. Ein
fehlschlagender Sink stoppt die anderen nicht.
"""

from __future__ import annotations

import logging
from typing import Any

from samuel.core.ports import IAuditSink
from samuel.core.types import AuditQuery

log = logging.getLogger(__name__)


class FanOutAuditSink(IAuditSink):
    def __init__(self, sinks: list[IAuditSink]):
        self._sinks = sinks
        self._stopped = False

    def write(self, event: Any) -> None:
        for sink in self._sinks:
            try:
                sink.write(event)
            except Exception:
                log.exception("FanOut sink %s write failed", type(sink).__name__)

    def query(self, query: AuditQuery) -> list[Any]:
        # Abfragen gegen den ersten abfragbaren Sink (i.d.R. JSONL).
        for sink in self._sinks:
            res = sink.query(query)
            if res:
                return res
        return []

    def stop(self) -> None:
        """Stop every stoppable child sink, even if one child fails."""

        if self._stopped:
            return
        self._stopped = True
        for sink in self._sinks:
            stop = getattr(sink, "stop", None)
            if not callable(stop):
                continue
            try:
                stop()
            except Exception:
                log.exception("FanOut sink %s stop failed", type(sink).__name__)
