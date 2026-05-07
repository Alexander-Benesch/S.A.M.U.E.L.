"""#304: OpenAI top-level adapter — uses OpenAICompatAdapter base + custom validate."""
from __future__ import annotations

from samuel.adapters.llm.openai_compat import OpenAICompatAdapter


class OpenAIAdapter(OpenAICompatAdapter):
    BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        super().__init__(
            api_key=api_key,
            base_url=self.BASE_URL,
            model=model,
            context_window=128_000,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    def validate(self) -> dict:
        """#211: Live validation via /v1/models with Authorization Bearer."""
        if not self._api_key:
            return {"valid": False, "detail": "no api key", "balance": None}
        try:
            from samuel.adapters.llm.http import http_get
            status, _ = http_get(
                f"{self.BASE_URL}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=5,
            )
        except Exception:  # noqa: BLE001
            return {"valid": False, "detail": "unreachable", "balance": None}
        if status == 200:
            return {"valid": True, "detail": "http 200", "balance": None}
        if status in (401, 403):
            return {"valid": False, "detail": "unauthorized", "balance": None}
        return {"valid": False, "detail": f"http {status}", "balance": None}
