"""#303: Gemini adapter — Google Generative Language API.

API-Doc: https://ai.google.dev/gemini-api/docs
Auth: ``x-goog-api-key`` header. Default model: ``gemini-2.0-flash``.
"""

from __future__ import annotations

import time
from typing import Any

from samuel.adapters.llm.http import http_get, http_post
from samuel.adapters.llm.provider_errors import (
    call_json,
    malformed,
    safe_error_code,
    usage_count,
)
from samuel.core.errors import ProviderUnavailable
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class GeminiAdapter(ILLMProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    capabilities = {"long_context"}
    context_window = 1_000_000

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        max_tokens: int = 4096,
        timeout: int = 60,
    ):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        # Gemini uses ``contents: [{role, parts: [{text}]}]`` instead of OpenAI-style
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            contents.append({"role": role, "parts": [{"text": str(m.get("content", ""))}]})

        max_tokens = int(kwargs.get("max_tokens") or self._max_tokens)
        temperature = kwargs.get("temperature")

        gen_cfg: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if temperature is not None:
            gen_cfg["temperature"] = float(temperature)

        url = f"{self.BASE_URL}/models/{self._model}:generateContent"
        body = {"contents": contents, "generationConfig": gen_cfg}

        t0 = time.monotonic()
        result = call_json(
            "gemini",
            lambda: http_post(
                url,
                body,
                {"Content-Type": "application/json", "x-goog-api-key": self._api_key},
                self._timeout,
            ),
        )
        latency = int((time.monotonic() - t0) * 1000)

        candidates = result.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            feedback = result.get("promptFeedback")
            feedback = feedback if isinstance(feedback, dict) else {}
            block_reason = safe_error_code(feedback.get("blockReason"), "no_candidates")
            if feedback.get("blockReason"):
                raise ProviderUnavailable(
                    "gemini",
                    category="provider_blocked",
                    code=f"prompt_{block_reason.lower()}",
                )
            raise malformed("gemini", "missing_candidates")
        candidate = candidates[0]
        if not isinstance(candidate, dict):
            raise malformed("gemini", "invalid_candidate")
        content = candidate.get("content")
        if not isinstance(content, dict):
            raise malformed("gemini", "missing_content")
        parts = content.get("parts")
        if not isinstance(parts, list):
            raise malformed("gemini", "missing_parts")
        text_parts = [
            part.get("text", "").strip()
            for part in parts
            if isinstance(part, dict)
            and isinstance(part.get("text"), str)
            and part.get("text", "").strip()
        ]
        finish_reason = safe_error_code(candidate.get("finishReason"), "STOP").lower()
        if not text_parts:
            if finish_reason not in {"stop", "finish_reason_unspecified"}:
                raise ProviderUnavailable(
                    "gemini",
                    category="provider_blocked",
                    code=f"finish_{finish_reason}",
                )
            raise malformed("gemini", "missing_text_content")
        text = "\n".join(text_parts)
        stop_reason = finish_reason

        raw_usage = result.get("usageMetadata")
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        usage_reported = all(
            isinstance(usage.get(field), int)
            and not isinstance(usage.get(field), bool)
            and usage.get(field, -1) >= 0
            for field in ("promptTokenCount", "candidatesTokenCount")
        )
        return LLMResponse(
            text=text,
            input_tokens=usage_count(usage.get("promptTokenCount")),
            output_tokens=usage_count(usage.get("candidatesTokenCount")),
            cached_tokens=usage_count(usage.get("cachedContentTokenCount")),
            stop_reason=stop_reason,
            model_used=self._model,
            latency_ms=latency,
            usage_reported=usage_reported,
        )

    def validate(self) -> dict:
        """#211: Live validation via models-listing endpoint."""
        if not self._api_key:
            return {"valid": False, "detail": "no api key", "balance": None}
        try:
            url = f"{self.BASE_URL}/models"
            status, _ = http_get(
                url,
                headers={"x-goog-api-key": self._api_key},
                timeout=5,
            )
        except Exception:  # noqa: BLE001
            return {"valid": False, "detail": "unreachable", "balance": None}
        if status == 200:
            return {"valid": True, "detail": "http 200", "balance": None}
        if status in (401, 403):
            return {"valid": False, "detail": "unauthorized", "balance": None}
        return {"valid": False, "detail": f"http {status}", "balance": None}

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def list_models(self) -> list[dict]:
        """#311: OpenRouter-Cache ist die Quelle fuer Gemini-Modelle."""
        return []
