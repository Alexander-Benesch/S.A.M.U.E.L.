"""#318: OpenRouter-Gateway-Adapter — unified Billing + Balance.

Nutzt OpenRouter (https://openrouter.ai) als Gateway fuer 350+ Modelle aller
grossen Provider (Anthropic, OpenAI, Google, DeepSeek, ...). Vorteile:

- **Unified Billing**: eine Rechnung fuer alle Modelle
- **Balance abrufbar** via ``GET /api/v1/auth/key``
- **Pricing automatisch** (kommt ueber den OpenRouter-Cache aus #311)
- **Kein API-Key-Management** pro Provider noetig

Tradeoff: ~50ms Gateway-Latenz, ~5% Markup. Lokale Provider (Ollama/LMStudio)
gehen NICHT ueber OpenRouter — die nutzt der User direkt.
"""
from __future__ import annotations

from samuel.adapters.llm.openai_compat import OpenAICompatAdapter


class OpenRouterAdapter(OpenAICompatAdapter):
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-sonnet-4-6",
        max_tokens: int = 4096,
        timeout: int = 60,
        referer: str = "https://samuel.local",
        title: str = "S.A.M.U.E.L.",
    ):
        # OpenAI-kompatibles Schema; OpenRouter akzeptiert beliebige
        # vendor/model-IDs als ``model``-Parameter.
        super().__init__(
            api_key=api_key,
            base_url=self.BASE_URL,
            model=model,
            context_window=200_000,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        # Optional: HTTP-Referer + X-Title fuer OpenRouter-Stats — diese Header
        # werden in OpenRouters Dashboard angezeigt und helfen beim Tracking.
        self._referer = referer
        self._title = title

    def validate(self) -> dict:
        """Live validation via /auth/key — liefert Balance direkt mit zurueck."""
        if not self._api_key:
            return {"valid": False, "detail": "no api key", "balance": None}
        try:
            from samuel.adapters.llm.http import http_get
            status, body = http_get(
                f"{self.BASE_URL}/auth/key",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=5,
            )
        except Exception:  # noqa: BLE001
            return {"valid": False, "detail": "unreachable", "balance": None}
        if status == 200 and isinstance(body, dict):
            data = body.get("data") or {}
            limit = data.get("limit")
            usage = data.get("usage") or 0
            remaining = data.get("limit_remaining")
            if remaining is None and limit is not None:
                try:
                    remaining = float(limit) - float(usage)
                except (TypeError, ValueError):
                    remaining = None
            balance: float | None
            try:
                balance = float(remaining) if remaining is not None else None
            except (TypeError, ValueError):
                balance = None
            return {"valid": True, "detail": "http 200", "balance": balance}
        if status in (401, 403):
            return {"valid": False, "detail": "unauthorized", "balance": None}
        return {"valid": False, "detail": f"http {status}", "balance": None}

    def list_models(self) -> list[dict]:
        """Liefert ALLE OpenRouter-Modelle aus dem Cache (#311) — kein Vendor-Filter.

        Im Gegensatz zu Provider-spezifischen ``get_models_for_provider()``
        listet der OpenRouter-Adapter alle 350+ Modelle, weil der User sie
        ueber sein OpenRouter-Account erreicht (mit ``vendor/model``-IDs).
        """
        from samuel.adapters.llm.costs import _load_or_cache
        cache = _load_or_cache()
        if not cache:
            return []
        rows: list[dict] = []
        for mid, info in cache.items():
            model_name = mid.split("/", 1)[1] if "/" in mid else mid
            rows.append({
                "id":                    mid,
                "name":                  info.get("name", mid),
                "model":                 mid,  # vendor/model fuer OpenRouter-API
                "prompt_per_1k":         round(float(info.get("prompt", 0) or 0) * 1000, 6),
                "completion_per_1k":     round(float(info.get("completion", 0) or 0) * 1000, 6),
                "context_length":        info.get("context_length", 0),
                "max_completion_tokens": info.get("max_completion_tokens", 0),
            })
        return sorted(rows, key=lambda r: r["id"])
