from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock

import pytest

from samuel.adapters.llm.retry import RetryLLMAdapter, is_retryable
from samuel.core.errors import ProviderUnavailable
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

MESSAGES = [{"role": "user", "content": "hi"}]
OK = LLMResponse(text="ok", input_tokens=5, output_tokens=3)


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "boom", {}, None)


def _inner(side_effect=None, return_value=OK):
    m = MagicMock(spec=ILLMProvider)
    m.context_window = 128_000
    m.capabilities = {"tool_use"}
    m.estimate_tokens.return_value = 7
    if side_effect is not None:
        m.complete.side_effect = side_effect
    else:
        m.complete.return_value = return_value
    return m


class TestIsRetryable:
    def test_rate_limit_and_5xx_retryable(self):
        for code in (429, 500, 502, 503, 504):
            assert is_retryable(_http_error(code)) is True

    def test_4xx_not_retryable(self):
        for code in (400, 401, 403, 404):
            assert is_retryable(_http_error(code)) is False

    def test_timeout_retryable(self):
        assert is_retryable(TimeoutError()) is True
        assert is_retryable(TimeoutError()) is True

    def test_urlerror_retryable(self):
        assert is_retryable(urllib.error.URLError("dns")) is True

    def test_value_error_not_retryable(self):
        assert is_retryable(ValueError("nope")) is False

    def test_typed_provider_error_uses_explicit_classification(self):
        assert is_retryable(
            ProviderUnavailable(
                "openai_compatible",
                category="provider_error",
                code="429",
                status=429,
                retryable=True,
            )
        )
        assert not is_retryable(
            ProviderUnavailable(
                "openai_compatible",
                category="provider_error",
                code="401",
                status=401,
                retryable=False,
            )
        )


class TestRetryAdapter:
    def test_succeeds_first_try_no_sleep(self):
        slept: list = []
        a = RetryLLMAdapter(_inner(), sleep_fn=slept.append)
        assert a.complete(MESSAGES).text == "ok"
        assert slept == []

    def test_retries_then_succeeds(self):
        slept: list = []
        inner = _inner(side_effect=[_http_error(429), _http_error(503), OK])
        a = RetryLLMAdapter(inner, max_attempts=3, base_delay_s=1.0, sleep_fn=slept.append)
        assert a.complete(MESSAGES).text == "ok"
        # Exponential-Backoff: 1s, dann 2s
        assert slept == [1.0, 2.0]
        assert inner.complete.call_count == 3

    def test_exhausts_and_raises_last(self):
        slept: list = []
        inner = _inner(side_effect=[_http_error(503)] * 3)
        a = RetryLLMAdapter(inner, max_attempts=3, base_delay_s=1.0, sleep_fn=slept.append)
        with pytest.raises(urllib.error.HTTPError):
            a.complete(MESSAGES)
        assert inner.complete.call_count == 3
        # max_attempts=3 -> 2 Sleeps zwischen 3 Versuchen
        assert slept == [1.0, 2.0]

    def test_non_retryable_raises_immediately(self):
        slept: list = []
        inner = _inner(side_effect=[_http_error(401), OK])
        a = RetryLLMAdapter(inner, max_attempts=3, sleep_fn=slept.append)
        with pytest.raises(urllib.error.HTTPError):
            a.complete(MESSAGES)
        assert inner.complete.call_count == 1  # kein Retry bei 401
        assert slept == []

    def test_delegates_interface(self):
        a = RetryLLMAdapter(_inner())
        assert a.context_window == 128_000
        assert a.capabilities == {"tool_use"}
        assert a.estimate_tokens("xxxxxxxx") == 7


class TestFactoryWrap:
    def test_wrap_disabled_returns_inner(self):
        from samuel.adapters.llm.factory import _wrap_retry

        inner = _inner()
        assert _wrap_retry(inner, {"retry": {"enabled": False}}) is inner
        assert _wrap_retry(inner, {}) is inner

    def test_wrap_enabled_returns_retry_adapter(self):
        from samuel.adapters.llm.factory import _wrap_retry

        inner = _inner()
        wrapped = _wrap_retry(
            inner, {"retry": {"enabled": True, "max_attempts": 2, "base_delay_s": 0.5}}
        )
        assert isinstance(wrapped, RetryLLMAdapter)
        assert wrapped._max_attempts == 2
        assert wrapped._base_delay_s == 0.5
