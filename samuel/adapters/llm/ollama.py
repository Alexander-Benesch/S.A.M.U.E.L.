from __future__ import annotations

import logging
import time
from typing import Any

from samuel.adapters.llm.http import http_post
from samuel.adapters.llm.provider_errors import call_json, malformed, usage_count
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

log = logging.getLogger(__name__)


class OllamaAdapter(ILLMProvider):
    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def context_window(self) -> int:
        return 128_000

    @property
    def capabilities(self) -> set[str]:
        return set()

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        prompt = "\n".join(m.get("content", "") for m in messages)
        payload = {
            "model": kwargs.get("model", self._model),
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.2),
                "num_predict": kwargs.get("max_tokens", self._max_tokens),
            },
        }
        if system := kwargs.get("system"):
            payload["system"] = system

        t0 = time.monotonic()
        result = call_json(
            "ollama",
            lambda: http_post(
                f"{self._base_url}/api/generate",
                payload,
                {"Content-Type": "application/json"},
                self._timeout,
            ),
        )
        latency = int((time.monotonic() - t0) * 1000)

        text = result.get("response")
        if not isinstance(text, str) or not text.strip():
            raise malformed("ollama", "missing_response")
        if result.get("done") is False:
            raise malformed("ollama", "incomplete_response")
        model_used = result.get("model")
        if not isinstance(model_used, str) or not model_used:
            model_used = self._model

        return LLMResponse(
            text=text.strip(),
            input_tokens=usage_count(result.get("prompt_eval_count")),
            output_tokens=usage_count(result.get("eval_count")),
            stop_reason=(str(result.get("done_reason")) if result.get("done_reason") else "stop"),
            model_used=model_used,
            latency_ms=latency,
            usage_reported=all(
                isinstance(result.get(field), int)
                and not isinstance(result.get(field), bool)
                and result.get(field, -1) >= 0
                for field in ("prompt_eval_count", "eval_count")
            ),
        )

    def validate(self) -> dict:
        """#211: Live health-check via GET /api/tags (no auth required)."""
        try:
            from samuel.adapters.llm.http import http_get

            status, _ = http_get(f"{self._base_url}/api/tags", timeout=5)
        except Exception:  # noqa: BLE001
            return {"valid": False, "detail": "unreachable", "balance": None}
        if status == 200:
            return {"valid": True, "detail": "http 200", "balance": None}
        return {"valid": False, "detail": f"http {status}", "balance": None}

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def list_models(self) -> list[dict]:
        """#311: Lokal installierte Ollama-Modelle via GET /api/tags."""
        try:
            from samuel.adapters.llm.http import http_get

            status, body = http_get(f"{self._base_url}/api/tags", timeout=5)
        except Exception as exc:  # noqa: BLE001
            log.warning("Ollama model listing failed: %s", type(exc).__name__)
            return []
        if status != 200 or not isinstance(body, dict):
            return []
        rows: list[dict] = []
        for m in body.get("models") or []:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or m.get("model") or "")
            if not name:
                continue
            rows.append(
                {
                    "id": name,
                    "name": name,
                    "model": name,
                    "prompt_per_1k": 0.0,
                    "completion_per_1k": 0.0,
                    "context_length": 0,
                    "max_completion_tokens": 0,
                }
            )
        return sorted(rows, key=lambda r: r["id"])
