from __future__ import annotations

from samuel.adapters.llm.costs import estimate_cost


class TestEstimateCost:
    def setup_method(self):
        """#311-followup: empty Cache mit fresh TTL — _load_or_cache faellt sonst
        auf disk-cache zurueck und liefert OpenRouter-Preise statt hardcoded Fallback."""
        import time as _t
        from samuel.adapters.llm import costs as _costs
        _costs._or_cache = {}
        _costs._or_cache_ts = _t.time()  # fresh — TTL-check passes, leerer Cache wird genutzt

    def teardown_method(self):
        from samuel.adapters.llm import costs as _costs
        _costs._or_cache = None
        _costs._or_cache_ts = 0.0

    def test_local_providers_free(self):
        assert estimate_cost("ollama", "llama3", input_tokens=1000, output_tokens=500) == 0.0
        assert estimate_cost("lmstudio", "model", input_tokens=1000, output_tokens=500) == 0.0

    def test_zero_tokens(self):
        assert estimate_cost("claude", "claude-sonnet-4-6", input_tokens=0, output_tokens=0) == 0.0

    def test_hardcoded_fallback(self):
        cost = estimate_cost("claude", "claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
        assert cost > 0
        expected = 3.0 * 1500 / 1_000_000
        assert abs(cost - expected) < 1e-6

    def test_cached_tokens_reduce_cost(self):
        full = estimate_cost("claude", "claude-opus-4-6", input_tokens=1000, output_tokens=500)
        assert full > 0

    def test_unknown_provider_fallback(self):
        cost = estimate_cost("unknown", "model", input_tokens=1000, output_tokens=500)
        assert cost == 0.0

    def test_deepseek_cost(self):
        cost = estimate_cost("deepseek", "deepseek-chat", input_tokens=10000, output_tokens=5000)
        expected = 0.14 * 15000 / 1_000_000
        assert abs(cost - expected) < 1e-6


# #311: Models-Discovery API
class TestGetModelsForProvider:
    def teardown_method(self):
        """Reset cache zwischen Tests, damit kein State leakt."""
        from samuel.adapters.llm import costs as _costs
        _costs._or_cache = None
        _costs._or_cache_ts = 0.0

    def setup_method(self):
        from samuel.adapters.llm import costs as _costs
        _costs._or_cache = {
            "anthropic/claude-sonnet-4-6": {
                "name": "Claude Sonnet 4.6",
                "prompt": 0.000003,
                "completion": 0.000015,
                "context_length": 200_000,
                "max_completion_tokens": 8192,
            },
            "openai/gpt-4o-mini": {
                "name": "GPT-4o Mini",
                "prompt": 0.00000015,
                "completion": 0.0000006,
                "context_length": 128_000,
                "max_completion_tokens": 16384,
            },
            "google/gemini-2.0-flash": {
                "name": "Gemini 2.0 Flash",
                "prompt": 0.0000001,
                "completion": 0.0000004,
                "context_length": 1_000_000,
                "max_completion_tokens": 8192,
            },
        }
        import time as _t
        _costs._or_cache_ts = _t.time()

    def test_get_models_for_provider_filters_by_prefix(self):
        from samuel.adapters.llm.costs import get_models_for_provider
        rows = get_models_for_provider("claude")
        assert len(rows) == 1
        assert rows[0]["model"] == "claude-sonnet-4-6"
        assert rows[0]["prompt_per_1k"] == round(0.000003 * 1000, 6)

    def test_get_models_for_provider_openai(self):
        from samuel.adapters.llm.costs import get_models_for_provider
        rows = get_models_for_provider("openai")
        assert len(rows) == 1
        assert rows[0]["model"] == "gpt-4o-mini"

    def test_get_models_for_provider_gemini_via_google_vendor(self):
        from samuel.adapters.llm.costs import get_models_for_provider
        rows = get_models_for_provider("gemini")
        assert len(rows) == 1
        assert rows[0]["model"] == "gemini-2.0-flash"

    def test_get_models_for_provider_returns_empty_for_local(self):
        from samuel.adapters.llm.costs import get_models_for_provider
        for prov in ("ollama", "lmstudio", "manual"):
            assert get_models_for_provider(prov) == []

    def test_get_models_for_provider_unknown_returns_empty(self):
        from samuel.adapters.llm.costs import get_models_for_provider
        assert get_models_for_provider("xxx_unknown") == []

    def test_get_pricing_info_reports_cache_state(self):
        from samuel.adapters.llm.costs import get_pricing_info
        info = get_pricing_info()
        assert info["available"] is True
        assert info["count"] == 3
        assert info["source"] == "openrouter"
        assert info["fetched_at"] > 0

    def test_get_models_for_openrouter_returns_all(self):
        """#318-AC: openrouter-Provider liefert ALLE Cache-Modelle."""
        from samuel.adapters.llm.costs import get_models_for_provider
        rows = get_models_for_provider("openrouter")
        assert len(rows) == 3
        ids = {r["id"] for r in rows}
        assert ids == {
            "anthropic/claude-sonnet-4-6",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash",
        }
        # ``model`` field is full vendor/model id (used as OpenRouter API ``model`` param)
        for r in rows:
            assert "/" in r["model"]
            assert r["model"] == r["id"]
