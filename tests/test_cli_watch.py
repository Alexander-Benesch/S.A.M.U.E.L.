from __future__ import annotations

from argparse import Namespace
from typing import Any

from samuel.cli import _cmd_watch


class _WatchBus:
    config = None

    def __init__(self, result: Any = None, *, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def send(self, _command: Any) -> Any:
        if self._error is not None:
            raise self._error
        return self._result


def _args() -> Namespace:
    return Namespace(interval=60, once=True)


def test_watch_once_returns_zero_for_fail_closed_success_result() -> None:
    bus = _WatchBus({"dispatched": 1, "dispatched_failed": 0, "planned": 1})

    assert _cmd_watch(bus, _args()) == 0  # type: ignore[arg-type]


def test_watch_once_returns_nonzero_for_failed_dispatch() -> None:
    bus = _WatchBus({"dispatched": 2, "dispatched_failed": 1, "planned": 1})

    assert _cmd_watch(bus, _args()) == 1  # type: ignore[arg-type]


def test_watch_once_returns_nonzero_for_missing_result() -> None:
    assert _cmd_watch(_WatchBus(None), _args()) == 1  # type: ignore[arg-type]


def test_watch_once_returns_nonzero_for_raised_exception() -> None:
    bus = _WatchBus(error=RuntimeError("scan failed"))

    assert _cmd_watch(bus, _args()) == 1  # type: ignore[arg-type]
