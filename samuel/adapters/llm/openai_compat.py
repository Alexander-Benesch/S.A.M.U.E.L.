from __future__ import annotations

import contextlib
import time
from typing import Any

from samuel.adapters.llm.http import http_post
from samuel.adapters.llm.provider_errors import call_json, malformed, usage_count
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse, is_truncated_stop_reason


class OpenAICompatAdapter(ILLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        context_window: int = 128_000,
        max_tokens: int = 4096,
        timeout: int = 120,
        provider_caps: set[str] | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._context_window = context_window
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._caps = provider_caps or set()

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def capabilities(self) -> set[str]:
        return self._caps

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        payload = {
            "model": kwargs.get("model", self._model),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
        }
        # #335: JSON-Mode nur, wenn der Provider es kann (Capability-Gate) —
        # sonst lehnen manche Endpoints den Request ab.
        response_format = kwargs.get("response_format")
        if response_format and "structured_output" in self._caps:
            payload["response_format"] = response_format
        reasoning = kwargs.get("reasoning")
        if isinstance(reasoning, dict) and reasoning:
            payload["reasoning"] = reasoning

        t0 = time.monotonic()
        result = call_json(
            "openai_compatible",
            lambda: http_post(
                f"{self._base_url}/chat/completions",
                payload,
                {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                self._timeout,
            ),
        )
        latency = int((time.monotonic() - t0) * 1000)

        choices = result.get("choices")
        if not isinstance(choices, list) or not choices:
            raise malformed("openai_compatible", "missing_choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise malformed("openai_compatible", "invalid_choice")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise malformed("openai_compatible", "missing_message")
        finish_reason = choice.get("finish_reason")
        if not isinstance(finish_reason, str) or not finish_reason:
            finish_reason = "stop"
        content = message.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif content is None:
            text = ""
        else:
            raise malformed("openai_compatible", "missing_content")
        # A provider can spend the whole completion budget before producing
        # visible content (for example on reasoning tokens).  Preserve its
        # explicit truncation signal so the slice can use the existing
        # fail-closed token-limit path.  Empty content without that signal is
        # still a malformed response and never becomes an apparent success.
        if not text and not is_truncated_stop_reason(finish_reason):
            raise malformed("openai_compatible", "missing_content")
        raw_usage = result.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        usage_reported = all(
            isinstance(usage.get(field), int)
            and not isinstance(usage.get(field), bool)
            and usage.get(field, -1) >= 0
            for field in ("prompt_tokens", "completion_tokens")
        )
        prompt_details = usage.get("prompt_tokens_details", {})
        if not isinstance(prompt_details, dict):
            prompt_details = {}
        completion_details = usage.get("completion_tokens_details", {})
        if not isinstance(completion_details, dict):
            completion_details = {}
        # #335: bei angefordertem JSON-Mode den Text als Struktur parsen.
        # Fehlerhaftes JSON -> structured=None, text bleibt erhalten (Fallback
        # auf den Freitext-Parser bleibt moeglich).
        structured = None
        if response_format and "structured_output" in self._caps:
            import json as _json

            with contextlib.suppress(ValueError, TypeError):
                parsed = _json.loads(text)
                if isinstance(parsed, dict):
                    structured = parsed
        model_used = result.get("model")
        if not isinstance(model_used, str) or not model_used:
            model_used = self._model
        return LLMResponse(
            text=text,
            input_tokens=usage_count(usage.get("prompt_tokens")),
            output_tokens=usage_count(usage.get("completion_tokens")),
            cached_tokens=usage_count(prompt_details.get("cached_tokens")),
            reasoning_tokens=usage_count(completion_details.get("reasoning_tokens")),
            stop_reason=finish_reason,
            model_used=model_used,
            latency_ms=latency,
            usage_reported=usage_reported,
            structured=structured,
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def list_models(self) -> list[dict]:
        """#311: Default — Subclasses (LMStudio) override mit eigenem Endpoint.
        Fuer DeepSeek/OpenAI ist der OpenRouter-Cache die Quelle."""
        return []
