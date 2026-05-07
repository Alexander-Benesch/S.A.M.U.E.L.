from __future__ import annotations

from samuel.adapters.llm.openai_compat import OpenAICompatAdapter


class LMStudioAdapter(OpenAICompatAdapter):
    def __init__(
        self,
        model: str = "local-model",
        base_url: str = "http://localhost:1234/v1",
        max_tokens: int = 4096,
        timeout: int = 120,
    ):
        # #328-followup: LM Studio's OpenAI-compat-API liegt unter ``/v1``.
        # Wenn der User die Server-Root-URL ohne ``/v1`` eingibt (z.B.
        # ``http://192.168.1.158:1234``), antwortet LM Studio mit
        # ``{"error":"Unexpected endpoint"}`` (status 200) auf ``/models``
        # und auf ``/chat/completions`` — Connection-Test sieht "200 OK",
        # aber list_models() liefert nichts und Calls scheitern.
        # Wir ergaenzen ``/v1`` transparent. Ist es schon vorhanden, no-op.
        url = base_url.rstrip("/")
        if not url.endswith("/v1"):
            url = url + "/v1"
        super().__init__(
            api_key="lm-studio",
            base_url=url,
            model=model,
            context_window=32_000,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    def validate(self) -> dict:
        """#211: Live health-check via GET /v1/models (no auth required).

        #328-followup: pruefe zusaetzlich, ob die Antwort ein OpenAI-compat
        Schema enthaelt (``data`` als list). Sonst liefert LM Studio bei
        falschem Pfad einen 200 mit Error-Body — Connection-OK ware irre-
        fuehrend.
        """
        try:
            from samuel.adapters.llm.http import http_get
            status, body = http_get(f"{self._base_url}/models", timeout=5)
        except Exception:  # noqa: BLE001
            return {"valid": False, "detail": "unreachable", "balance": None}
        if status == 200 and isinstance(body, dict) and isinstance(body.get("data"), list):
            return {"valid": True, "detail": "http 200", "balance": None}
        if status == 200:
            return {
                "valid": False,
                "detail": "endpoint reached but not OpenAI-compat (check URL ends with /v1)",
                "balance": None,
            }
        return {"valid": False, "detail": f"http {status}", "balance": None}

    def list_models(self) -> list[dict]:
        """#311: Lokal geladene LM-Studio-Modelle via GET /v1/models."""
        try:
            from samuel.adapters.llm.http import http_get
            status, body = http_get(f"{self._base_url}/models", timeout=5)
        except Exception:  # noqa: BLE001
            return []
        if status != 200 or not isinstance(body, dict):
            return []
        rows: list[dict] = []
        for m in body.get("data") or []:
            if not isinstance(m, dict):
                continue
            mid = str(m.get("id") or "")
            if not mid:
                continue
            rows.append({
                "id":                    mid,
                "name":                  mid,
                "model":                 mid,
                "prompt_per_1k":         0.0,
                "completion_per_1k":     0.0,
                "context_length":        0,
                "max_completion_tokens": 0,
            })
        return sorted(rows, key=lambda r: r["id"])