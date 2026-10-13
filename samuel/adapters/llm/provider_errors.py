from __future__ import annotations

import re
import urllib.error
from collections.abc import Callable
from typing import Any

from samuel.adapters.llm.retry import RETRYABLE_HTTP_STATUS
from samuel.core.errors import ProviderUnavailable

_SAFE_ERROR_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")


def status_code(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 100 <= value <= 599:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit():
        parsed = int(value)
        return parsed if 100 <= parsed <= 599 else None
    return None


def safe_error_code(value: Any, fallback: str) -> str:
    if isinstance(value, bool):
        return fallback
    text = str(value) if isinstance(value, (int, str)) else ""
    return text if _SAFE_ERROR_CODE.fullmatch(text) else fallback


def usage_count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def malformed(provider: str, code: str) -> ProviderUnavailable:
    return ProviderUnavailable(
        provider,
        category="malformed_response",
        code=code,
    )


def payload_error(provider: str, result: dict[str, Any]) -> ProviderUnavailable | None:
    raw_error = result.get("error")
    if raw_error is None:
        return None
    error = raw_error if isinstance(raw_error, dict) else {}
    status = next(
        (
            candidate
            for candidate in (
                status_code(error.get("status")),
                status_code(error.get("status_code")),
                status_code(error.get("code")),
                status_code(result.get("status")),
                status_code(result.get("status_code")),
            )
            if candidate is not None
        ),
        None,
    )
    code = safe_error_code(
        error.get("code") or error.get("status") or error.get("type"), "provider_error"
    )
    return ProviderUnavailable(
        provider,
        category="provider_error",
        code=code,
        status=status,
        retryable=status in RETRYABLE_HTTP_STATUS,
    )


def call_json(provider: str, operation: Callable[[], Any]) -> dict[str, Any]:
    """Execute one JSON provider call and expose only bounded failure data."""

    try:
        result = operation()
    except urllib.error.HTTPError as exc:
        status = status_code(exc.code)
        raise ProviderUnavailable(
            provider,
            category="http_error",
            code=f"http_{status}" if status is not None else "http_error",
            status=status,
            retryable=status in RETRYABLE_HTTP_STATUS,
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise ProviderUnavailable(
            provider,
            category="transport_error",
            code="transport_unavailable",
            retryable=True,
        ) from exc
    except ValueError as exc:
        raise malformed(provider, "invalid_json_object") from exc
    if not isinstance(result, dict):
        raise malformed(provider, "invalid_json_object")
    error = payload_error(provider, result)
    if error is not None:
        raise error
    return result
