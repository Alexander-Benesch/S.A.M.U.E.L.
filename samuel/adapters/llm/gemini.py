"""#303: Gemini adapter — Google Generative Language API.

API-Doc: https://ai.google.dev/gemini-api/docs
Auth: ``?key=`` query param. Default model: ``gemini-2.0-flash``.
"""
from __future__ import annotations

import time
from typing import Any

from samuel.adapters.llm.http import http_get, http_post
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

        url = f"{self.BASE_URL}/models/{self._model}:generateContent?key={self._api_key}"
        body = {"contents": contents, "generationConfig": gen_cfg}

        t0 = time.monotonic()
        result = http_post(
            url, body, {"Content-Type": "application/json"}, self._timeout,
        )
        latency = int((time.monotonic() - t0) * 1000)

        candidates = result.get("candidates") or []
        if candidates and isinstance(candidates[0], dict):
            parts = candidates[0].get("content", {}).get("parts") or []
            text = parts[0].get("text", "").strip() if parts else ""
            stop_reason = candidates[0].get("finishReason", "STOP").lower()
        else:
            text = ""
            stop_reason = "no_candidates"

        usage = result.get("usageMetadata", {})
        return LLMResponse(
            text=text,
            input_tokens=int(usage.get("promptTokenCount") or 0),
            output_tokens=int(usage.get("candidatesTokenCount") or 0),
            cached_tokens=int(usage.get("cachedContentTokenCount") or 0),
            stop_reason=stop_reason,
            model_used=self._model,
            latency_ms=latency,
        )

    def validate(self) -> dict:
        """#211: Live validation via models-listing endpoint."""
        if not self._api_key:
            return {"valid": False, "detail": "no api key", "balance": None}
        try:
            url = f"{self.BASE_URL}/models?key={self._api_key}"
            status, _ = http_get(url, timeout=5)
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
