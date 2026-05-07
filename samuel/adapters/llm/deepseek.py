from __future__ import annotations

from samuel.adapters.llm.openai_compat import OpenAICompatAdapter


class DeepSeekAdapter(OpenAICompatAdapter):
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        super().__init__(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            model=model,
            context_window=128_000,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    def validate(self) -> dict:
        """#211: Live validation via /v1/user/balance — also returns balance."""
        if not self._api_key:
            return {"valid": False, "detail": "no api key", "balance": None}
        try:
            from samuel.adapters.llm.http import http_get
            status, body = http_get(
                "https://api.deepseek.com/v1/user/balance",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=5,
            )
        except Exception:  # noqa: BLE001
            return {"valid": False, "detail": "unreachable", "balance": None}
        if status == 200 and isinstance(body, dict):
            balance = None
            try:
                infos = body.get("balance_infos") or []
                if infos and isinstance(infos[0], dict):
                    raw = infos[0].get("total_balance")
                    balance = float(raw) if raw is not None else None
            except (TypeError, ValueError, KeyError):
                balance = None
            return {"valid": True, "detail": "http 200", "balance": balance}
        if status in (401, 403):
            return {"valid": False, "detail": "unauthorized", "balance": None}
        return {"valid": False, "detail": f"http {status}", "balance": None}