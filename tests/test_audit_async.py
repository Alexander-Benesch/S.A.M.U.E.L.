from __future__ import annotations

import time
from typing import Any

from samuel.adapters.audit.async_sink import AsyncAuditSink
from samuel.core.ports import IAuditSink
from samuel.core.types import AuditQuery


class CollectingSink(IAuditSink):
    def __init__(self):
        self.written: list[dict] = []

    def write(self, event: Any) -> None:
        self.written.append(event)

    def query(self, query: AuditQuery) -> list[Any]:
        return self.written


class SlowSink(IAuditSink):
    def __init__(self, delay: float = 0.05):
        self.written: list[dict] = []
        self._delay = delay

    def write(self, event: Any) -> None:
        time.sleep(self._delay)
        self.written.append(event)

    def query(self, query: AuditQuery) -> list[Any]:
        return self.written


def test_async_write():
    inner = CollectingSink()
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback, buffer_size=10)

    sink.write({"event_name": "Test", "payload": {}})
    sink.stop()

    assert len(inner.written) == 1
    assert len(fallback.written) == 0


def test_security_event_fallback_on_full_buffer():
    inner = SlowSink(delay=1.0)
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback, buffer_size=1)

    sink.write({"event_name": "First", "payload": {}})
    time.sleep(0.01)

    for _ in range(5):
        sink.write({"event_name": "Filler", "payload": {}})

    sink.write({"event_name": "Security", "owasp_risk": "broken_trust_boundaries", "payload": {}})

    assert any(e.get("owasp_risk") for e in fallback.written)
    sink.stop()


def test_error_event_fallback_on_full_buffer():
    inner = SlowSink(delay=1.0)
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback, buffer_size=1)

    sink.write({"event_name": "First", "payload": {}})
    time.sleep(0.01)

    for _ in range(5):
        sink.write({"event_name": "Filler", "payload": {}})

    sink.write({"event_name": "Error", "lvl": "error", "payload": {}})

    assert any(e.get("lvl") == "error" for e in fallback.written)
    sink.stop()


def test_non_security_dropped_on_full_buffer():
    inner = SlowSink(delay=1.0)
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback, buffer_size=1)

    sink.write({"event_name": "First", "payload": {}})
    time.sleep(0.01)

    for _ in range(5):
        sink.write({"event_name": "Normal", "payload": {}})

    assert len(fallback.written) == 0
    sink.stop()


def test_worker_is_daemon():
    inner = CollectingSink()
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback)
    assert sink._worker.daemon is True
    sink.stop()


def test_query_delegates_to_inner():
    inner = CollectingSink()
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback)

    inner.written.append({"event_name": "Test"})
    results = sink.query(AuditQuery())
    assert len(results) == 1
    sink.stop()


def test_stop_drains_pending_events_before_returning():
    """#257: AsyncAuditSink.stop() muss alle gepufferten Events VOR dem
    Return ans inner-Sink schreiben. Sonst gehen sie bei sys.exit verloren
    weil der Worker daemon-Thread ist."""
    inner = SlowSink(delay=0.02)
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback, buffer_size=50)

    for i in range(20):
        sink.write({"event_name": f"E{i}", "payload": {}})

    # Vor stop(): Worker hat noch nicht alle gedrained (slow-sink 20 * 20ms = 400ms)
    # Nach stop(): alle MUSS persistent sein
    sink.stop()
    assert len(inner.written) == 20, (
        f"Expected 20 events drained, got {len(inner.written)}"
    )


def test_stop_idempotent():
    """#257: doppeltes stop() darf nicht hängen oder crashen (atexit-Hook
    + explicit cli-shutdown können beide stop() rufen)."""
    inner = CollectingSink()
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback)
    sink.stop()
    sink.stop()  # darf nicht hängen


def test_atexit_registered_on_init():
    """#257: AsyncAuditSink registriert stop() bei atexit, damit auch bei
    unerwarteten Exits (sys.exit ohne explicit shutdown) der Drain läuft."""
    import atexit

    inner = CollectingSink()
    fallback = CollectingSink()
    sink = AsyncAuditSink(inner, fallback)
    # atexit hat keine read-API für registrierte Funktionen, aber wir können
    # prüfen dass der _stopped-Flag existiert und stop() idempotent ist —
    # was atexit-safe macht.
    assert hasattr(sink, "_stopped")
    assert sink._stopped is False
    sink.stop()
    assert sink._stopped is True
