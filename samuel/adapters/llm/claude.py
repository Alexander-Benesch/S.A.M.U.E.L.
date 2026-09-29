from __future__ import annotations

import time
from typing import Any

from samuel.adapters.llm.http import http_post
from samuel.adapters.llm.provider_errors import call_json, malformed, usage_count
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

_CONTEXT_WINDOWS = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}


class ClaudeAdapter(ILLMProvider):
    BASE_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def context_window(self) -> int:
        return _CONTEXT_WINDOWS.get(self._model, 200_000)

    @property
    def capabilities(self) -> set[str]:
        return {"streaming", "tool_use", "structured_output"}

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        payload: dict = {
            "model": kwargs.get("model", self._model),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "temperature": kwargs.get("temperature", 0.2),
            "messages": messages,
        }
        if system := kwargs.get("system"):
            payload["system"] = system

        t0 = time.monotonic()
        result = call_json(
            "claude",
            lambda: http_post(
                self.BASE_URL,
                payload,
                {
                    "x-api-key": self._api_key,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                },
                self._timeout,
            ),
        )
        latency = int((time.monotonic() - t0) * 1000)

        content = result.get("content")
        if not isinstance(content, list) or not content:
            raise malformed("claude", "missing_content")
        text_blocks = [
            block.get("text", "").strip()
            for block in content
            if isinstance(block, dict)
            and block.get("type", "text") == "text"
            and isinstance(block.get("text"), str)
            and block.get("text", "").strip()
        ]
        if not text_blocks:
            raise malformed("claude", "missing_text_content")
        text = "\n".join(text_blocks)
        raw_usage = result.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        usage_reported = all(
            isinstance(usage.get(field), int)
            and not isinstance(usage.get(field), bool)
            and usage.get(field, -1) >= 0
            for field in ("input_tokens", "output_tokens")
        )
        stop_reason = result.get("stop_reason")
        if not isinstance(stop_reason, str) or not stop_reason:
            stop_reason = "end_turn"
        model_used = result.get("model")
        if not isinstance(model_used, str) or not model_used:
            model_used = self._model
        return LLMResponse(
            text=text,
            input_tokens=usage_count(usage.get("input_tokens")),
            output_tokens=usage_count(usage.get("output_tokens")),
            cached_tokens=usage_count(usage.get("cache_read_input_tokens")),
            stop_reason=stop_reason,
            model_used=model_used,
            latency_ms=latency,
            usage_reported=usage_reported,
        )

    def validate(self) -> dict:
        """#211: Live API-Key validation via HEAD /v1/messages (no token cost)."""
        if not self._api_key:
            return {"valid": False, "detail": "no api key", "balance": None}
        try:
            from samuel.adapters.llm.http import http_head

            status = http_head(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=5,
            )
        except Exception:  # noqa: BLE001
            return {"valid": False, "detail": "unreachable", "balance": None}
        if status in (200, 204, 405):
            # 405 = HEAD not allowed but auth was accepted
            return {"valid": True, "detail": f"http {status}", "balance": None}
        if status in (401, 403):
            return {"valid": False, "detail": "unauthorized", "balance": None}
        return {"valid": False, "detail": f"http {status}", "balance": None}

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def list_models(self) -> list[dict]:
        """#311: OpenRouter-Cache ist die Quelle fuer Claude-Modelle."""
        return []
