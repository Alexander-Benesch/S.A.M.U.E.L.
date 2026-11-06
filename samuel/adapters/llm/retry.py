from __future__ import annotations

import logging
import socket
import urllib.error
from collections.abc import Callable
from typing import Any

from samuel.core.errors import ProviderUnavailable
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 1.0

# HTTP-Status, die transient sind und einen Retry lohnen. 429 = Rate-Limit,
# 5xx = Server-/Gateway-Fehler. 4xx ausser 429 sind permanent (z.B. 401/400)
# und werden NICHT wiederholt. OpenAI-kompatible Responsevalidierung nutzt
# dieselbe Menge, damit genau eine Retryklassifikation gilt.
RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504, 529})


def is_retryable(exc: BaseException) -> bool:
    """#337: True wenn der Fehler transient ist (Rate-Limit / 5xx / Timeout).

    ``HTTPError`` ist eine ``URLError``-Subklasse — daher zuerst auf den
    konkreten Status pruefen (nur 429/5xx retrybar), erst danach generische
    Netzwerk-/Timeout-Fehler.
    """
    if isinstance(exc, ProviderUnavailable):
        return exc.retryable
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_HTTP_STATUS
    # generische Netzwerk-/Timeout-Fehler (URLError schliesst socket-Fehler ein)
    return isinstance(exc, (TimeoutError, socket.timeout, urllib.error.URLError))


class RetryLLMAdapter(ILLMProvider):
    """Wiederholt ``complete`` bei transienten Provider-Fehlern mit
    Exponential-Backoff (1s, 2s, 4s, ...).

    #337: Sitzt im Factory-Wrap zwischen Metering und Sanitizer — der
    CircuitBreaker liegt darueber und sieht daher eine ganze Retry-Sequenz als
    *einen* Versuch (er zaehlt erst hoch, wenn alle Retries erschoepft sind).
    Nicht-retrybare Fehler (z.B. 401, 400) werden sofort durchgereicht.
    """

    def __init__(
        self,
        inner: ILLMProvider,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay_s: float = DEFAULT_BASE_DELAY_S,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self._inner = inner
        self._max_attempts = max(1, int(max_attempts))
        self._base_delay_s = max(0.0, float(base_delay_s))
        # injizierbar fuer Tests (kein echtes sleep)
        import time

        self._sleep = sleep_fn or time.sleep

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        last_exc: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._inner.complete(messages, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not is_retryable(exc) or attempt >= self._max_attempts:
                    raise
                delay = self._base_delay_s * (2 ** (attempt - 1))
                log.warning(
                    "LLM call failed (%s), retry %d/%d in %.1fs",
                    type(exc).__name__,
                    attempt,
                    self._max_attempts - 1,
                    delay,
                )
                self._sleep(delay)
        # unerreichbar — die Schleife re-raised vorher; defensiv:
        assert last_exc is not None
        raise last_exc

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)
