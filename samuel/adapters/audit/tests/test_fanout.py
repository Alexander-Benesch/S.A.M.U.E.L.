"""#368 Task 5: Fan-out-Audit-Sink."""

from __future__ import annotations

from samuel.adapters.audit.fanout import FanOutAuditSink
from samuel.core.ports import IAuditSink


class _Recorder(IAuditSink):
    def __init__(self):
        self.written = []

    def write(self, event):
        self.written.append(event)

    def query(self, query):
        return list(self.written)


class _Broken(IAuditSink):
    def write(self, event):
        raise RuntimeError("boom")

    def query(self, query):
        return []


class _Stoppable(_Recorder):
    def __init__(self):
        super().__init__()
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class _BrokenStop(_Recorder):
    def stop(self):
        raise RuntimeError("stop boom")


def test_writes_to_all_sinks():
    a, b = _Recorder(), _Recorder()
    FanOutAuditSink([a, b]).write({"x": 1})
    assert a.written == [{"x": 1}] and b.written == [{"x": 1}]


def test_one_failing_sink_does_not_stop_others():
    good = _Recorder()
    FanOutAuditSink([_Broken(), good]).write({"x": 1})
    assert good.written == [{"x": 1}]


def test_query_uses_first_nonempty():
    a, b = _Recorder(), _Recorder()
    b.write({"y": 2})
    assert FanOutAuditSink([a, b]).query(None) == [{"y": 2}]


def test_stop_reaches_all_stoppable_sinks_and_is_idempotent():
    a, b = _Stoppable(), _Stoppable()
    sink = FanOutAuditSink([a, b])

    sink.stop()
    sink.stop()

    assert a.stop_calls == 1
    assert b.stop_calls == 1


def test_broken_stop_does_not_prevent_later_sink_shutdown():
    good = _Stoppable()

    FanOutAuditSink([_BrokenStop(), good]).stop()

    assert good.stop_calls == 1
