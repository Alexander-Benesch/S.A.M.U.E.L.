from __future__ import annotations

import json
import time
from typing import Any

from samuel.adapters.llm.costs import estimate_cost


class TestEstimateCost:
    def setup_method(self):
        """#311-followup: empty Cache mit fresh TTL — _load_or_cache faellt sonst
        auf disk-cache zurueck und liefert OpenRouter-Preise statt hardcoded Fallback."""
        import time as _t

        from samuel.adapters.llm import costs as _costs

        _costs._or_cache = {}
        _costs._or_cache_ts = _t.time()  # fresh — TTL-check passes, leerer Cache wird genutzt
        _costs._or_cache_schema = 3

    def teardown_method(self):
        from samuel.adapters.llm import costs as _costs

        _costs._or_cache = None
        _costs._or_cache_ts = 0.0
        _costs._or_cache_schema = 0

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
        _costs._or_cache_schema = 0

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
        _costs._or_cache_schema = 3

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

    def test_get_pricing_info_reports_cache_state(self, tmp_path):
        from samuel.adapters.llm.costs import get_pricing_info

        cache_path = tmp_path / "models.json"
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "fetched_at": time.time(),
                    "benchmark_count": 1,
                    "benchmark_error": None,
                    "models": {"a": {}, "b": {}, "c": {}},
                }
            )
        )
        info = get_pricing_info(cache_path)
        assert info["available"] is True
        assert info["count"] == 3
        assert info["source"] == "openrouter"
        assert info["fetched_at"] > 0
        assert info["status"] == "fresh"

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


class TestModelQualityMetadata:
    def setup_method(self):
        import time

        from samuel.adapters.llm import costs

        costs._or_cache = {
            "vendor/reasoner": {
                "reasoning": {"supported_efforts": ["low", "high"]},
                "benchmarks": {
                    "intelligence_index": 72.5,
                    "coding_index": 41.0,
                    "agentic_index": 60.0,
                },
                "prompt": 0.000010,
                "completion": 0.000020,
                "additional_pricing": {},
                "benchmark_sources": ["openrouter"],
            },
            "vendor/plain": {
                "reasoning": {},
                "benchmarks": {"intelligence_index": 55.0},
                "prompt": 0.000005,
                "completion": 0.000015,
                "additional_pricing": {},
                "benchmark_sources": ["openrouter"],
            },
            # Cache entries created before #425 have no ``reasoning`` key.
            "nvidia/nemotron-3-super-120b-a12b:free": {"name": "Nemotron"},
        }
        costs._or_cache_ts = time.time()
        costs._or_cache_schema = 3

    def teardown_method(self):
        from samuel.adapters.llm import costs

        costs._or_cache = None
        costs._or_cache_ts = 0.0
        costs._or_cache_schema = 0

    def test_reasoning_metadata_is_exposed(self):
        from samuel.adapters.llm.costs import get_model_reasoning_info

        info = get_model_reasoning_info("vendor/reasoner")
        assert info["is_reasoning"] is True
        assert info["source"] == "openrouter_metadata"

    def test_stale_cache_entry_uses_conservative_name_fallback(self):
        from samuel.adapters.llm.costs import get_model_reasoning_info

        info = get_model_reasoning_info("nvidia/nemotron-3-super-120b-a12b:free")
        assert info == {
            "is_reasoning": True,
            "source": "model_name_heuristic_stale_cache",
            "metadata": {},
        }

    def test_explicit_empty_metadata_remains_authoritative(self):
        from samuel.adapters.llm.costs import get_model_reasoning_info

        info = get_model_reasoning_info("vendor/plain")
        assert info["is_reasoning"] is False
        assert info["source"] == "openrouter_metadata"

    def test_supported_parameters_identify_reasoning_when_detail_object_is_absent(self):
        from samuel.adapters.llm import costs
        from samuel.adapters.llm.costs import get_model_reasoning_info

        assert costs._or_cache is not None
        costs._or_cache["vendor/current"] = {
            "reasoning": {},
            "supported_parameters": ["max_tokens", "reasoning", "reasoning_effort"],
            "max_completion_tokens": 16_384,
        }

        info = get_model_reasoning_info("vendor/current")

        assert info["is_reasoning"] is True
        assert info["source"] == "openrouter_supported_parameters"
        assert info["max_completion_tokens"] == 16_384

    def test_fresh_supported_parameters_are_authoritative_for_plain_model(self):
        from samuel.adapters.llm import costs
        from samuel.adapters.llm.costs import get_model_reasoning_info

        assert costs._or_cache is not None
        costs._or_cache["vendor/current-plain"] = {
            "reasoning": {},
            "supported_parameters": ["max_tokens", "temperature"],
        }

        info = get_model_reasoning_info("vendor/current-plain")

        assert info["is_reasoning"] is False
        assert info["source"] == "openrouter_supported_parameters"

    def test_task_relevant_benchmark_and_threshold(self):
        from samuel.adapters.llm.costs import get_model_suitability

        planning = get_model_suitability("vendor/reasoner", "planning", threshold=70)
        implementation = get_model_suitability("vendor/reasoner", "implementation", threshold=50)
        assert planning["index"] == "intelligence_index"
        assert planning["status"] == "suitable"
        assert implementation["index"] == "coding_index"
        assert implementation["status"] == "below_threshold"

    def test_overqualification_uses_only_task_score_threshold_and_relative_margin(self):
        from samuel.adapters.llm.costs import get_model_suitability

        result = get_model_suitability(
            "vendor/reasoner",
            "planning",
            threshold=50,
            overqualification_margin_ratio=0.2,
        )

        assert result["status"] == "overqualified"
        assert result["overqualified_at"] == 60.0

    def test_missing_benchmark_stays_no_data(self):
        from samuel.adapters.llm.costs import get_model_suitability

        result = get_model_suitability("nvidia/nemotron-3-super-120b-a12b:free", "planning")
        assert result == {
            "available": False,
            "status": "no_data",
            "index": "intelligence_index",
            "score": None,
            "threshold": 50.0,
        }

    def test_cost_advisory_uses_strict_pareto_and_stable_model_id_tie_break(self):
        from samuel.adapters.llm import costs
        from samuel.adapters.llm.costs import get_model_cost_advisory

        assert costs._or_cache is not None
        costs._or_cache["vendor/a-alternative"] = {
            "benchmarks": {"intelligence_index": 52.0},
            "benchmark_sources": ["openrouter"],
            "prompt": 0.000006,
            "completion": 0.000019,
            "additional_pricing": {},
        }
        costs._or_cache["vendor/z-alternative"] = {
            "benchmarks": {"intelligence_index": 58.0},
            "benchmark_sources": ["openrouter"],
            "prompt": 0.000004,
            "completion": 0.000018,
            "additional_pricing": {},
        }

        result = get_model_cost_advisory(
            "vendor/reasoner",
            "planning",
            threshold=50,
            overqualification_margin_ratio=0.2,
            enabled=True,
        )

        recommendation = result["recommendation"]
        assert isinstance(recommendation, dict)
        assert result["status"] == "recommendation_available"
        assert recommendation["model"] == "vendor/a-alternative"
        assert recommendation["candidate_count"] == 3
        assert recommendation["tie_break"] == "canonical_model_id"

    def test_cost_advisory_rejects_crossing_or_additional_prices_and_no_data(self):
        from samuel.adapters.llm import costs
        from samuel.adapters.llm.costs import get_model_cost_advisory

        assert costs._or_cache is not None
        costs._or_cache["vendor/plain"]["prompt"] = 0.000004
        costs._or_cache["vendor/plain"]["completion"] = 0.000030
        costs._or_cache["vendor/extra-fee"] = {
            "benchmarks": {"intelligence_index": 55.0},
            "benchmark_sources": ["openrouter"],
            "prompt": 0.000001,
            "completion": 0.000001,
            "additional_pricing": {"request": 0.01},
        }
        costs._or_cache["vendor/too-weak"] = {
            "benchmarks": {"intelligence_index": 49.9},
            "benchmark_sources": ["openrouter"],
            "prompt": 0.000001,
            "completion": 0.000001,
            "additional_pricing": {},
        }

        result = get_model_cost_advisory(
            "vendor/reasoner",
            "planning",
            threshold=50,
            overqualification_margin_ratio=0.2,
            enabled=True,
        )
        no_data = get_model_cost_advisory(
            "nvidia/nemotron-3-super-120b-a12b:free",
            "planning",
            threshold=50,
            overqualification_margin_ratio=0.2,
            enabled=True,
        )

        assert result["status"] == "overqualified_no_comparable_alternative"
        assert no_data["status"] == "no_data"

    def test_cost_advisory_requires_current_schema_and_honors_disable(self):
        from samuel.adapters.llm import costs
        from samuel.adapters.llm.costs import get_model_cost_advisory

        costs._or_cache_schema = 2
        stale_schema = get_model_cost_advisory(
            "vendor/reasoner",
            "planning",
            threshold=50,
            overqualification_margin_ratio=0.2,
            enabled=True,
        )
        disabled = get_model_cost_advisory(
            "vendor/reasoner",
            "planning",
            threshold=50,
            overqualification_margin_ratio=0.2,
            enabled=False,
        )

        assert stale_schema["status"] == "incomparable_generation"
        assert disabled["enabled"] is False
        assert disabled["recommendation"] is None


def test_refresh_pricing_merges_authenticated_benchmarks(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock

    from samuel.adapters.llm import costs

    models_response = MagicMock()
    models_response.__enter__.return_value.read.return_value = json.dumps(
        {
            "data": [
                {
                    "id": "vendor/model",
                    "canonical_slug": "vendor/model-20260801",
                    "name": "Model",
                    "pricing": {
                        "prompt": "0.1",
                        "completion": "0.2",
                        "request": "0.01",
                        "image": "0",
                    },
                    "context_length": 100_000,
                    "top_provider": {"max_completion_tokens": 8192},
                    "reasoning": {"supported_efforts": ["low", "high"]},
                    "supported_parameters": ["max_tokens", "reasoning"],
                    "default_parameters": {"temperature": 0.3},
                }
            ]
        }
    ).encode()
    benchmarks_response = MagicMock()
    benchmarks_response.__enter__.return_value.read.return_value = json.dumps(
        {
            "data": [
                {
                    "model_permaslug": "vendor/model-20260801",
                    "source": "openrouter",
                    "intelligence_index": 70.0,
                    "coding_index": 65.0,
                    "agentic_index": 60.0,
                }
            ]
        }
    ).encode()
    urlopen = MagicMock(side_effect=[models_response, benchmarks_response])
    monkeypatch.setattr(costs.urllib.request, "urlopen", urlopen)
    costs._or_cache = None
    costs._or_cache_ts = 0.0

    result = costs.refresh_pricing(tmp_path / "openrouter.json", api_key="secret")

    assert result["error"] is None
    assert result["benchmark_count"] == 1
    assert costs._or_cache is not None
    assert costs._or_cache["vendor/model"]["benchmarks"]["coding_index"] == 65.0
    saved = json.loads((tmp_path / "openrouter.json").read_text())
    assert saved["schema_version"] == 3
    assert saved["models"]["vendor/model"]["supported_parameters"] == [
        "max_tokens",
        "reasoning",
    ]
    assert saved["models"]["vendor/model"]["additional_pricing"] == {"request": 0.01}
    benchmark_request = urlopen.call_args_list[1].args[0]
    assert benchmark_request.full_url.endswith("/api/v1/benchmarks")
    assert benchmark_request.get_header("Authorization") == "Bearer secret"


def test_refresh_pricing_keeps_models_and_reports_benchmark_failure(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from urllib.error import HTTPError

    from samuel.adapters.llm import costs

    models_response = MagicMock()
    models_response.__enter__.return_value.read.return_value = json.dumps(
        {
            "data": [
                {
                    "id": "vendor/model",
                    "pricing": {},
                    "supported_parameters": ["max_tokens"],
                    "top_provider": {"max_completion_tokens": 4096},
                }
            ]
        }
    ).encode()
    monkeypatch.setattr(
        costs.urllib.request,
        "urlopen",
        MagicMock(
            side_effect=[
                models_response,
                HTTPError("https://example.invalid", 403, "forbidden", {}, None),
            ]
        ),
    )

    cache_path = tmp_path / "openrouter.json"
    result = costs.refresh_pricing(cache_path, api_key="invalid")

    assert result["error"] is None
    assert result["count"] == 1
    assert result["benchmark_count"] == 0
    assert "403" in result["benchmark_error"]
    saved = json.loads(cache_path.read_text())
    assert "vendor/model" in saved["models"]
    assert saved["benchmark_error"] == result["benchmark_error"]


def test_old_cache_schema_requires_visible_refresh(tmp_path):
    import json

    from samuel.adapters.llm.costs import get_pricing_info

    cache_path = tmp_path / "old.json"
    cache_path.write_text(json.dumps({"fetched_at": time.time(), "models": {"x": {}}}))

    info = get_pricing_info(cache_path)

    assert info["status"] == "upgrade_required"
    assert info["needs_refresh"] is True
    assert info["schema_version"] == 1


class TestCatalogEndpointConfiguration:
    def setup_method(self):
        from samuel.adapters.llm import costs

        self.original_sources = dict(costs._catalog_sources)
        self.original_cache = (costs._or_cache, costs._or_cache_ts, costs._or_cache_schema)

    def teardown_method(self):
        from samuel.adapters.llm import costs

        costs._catalog_sources = self.original_sources
        costs._or_cache, costs._or_cache_ts, costs._or_cache_schema = self.original_cache

    def test_existing_file_config_overrides_sources_without_completion_mutation(
        self, tmp_path, monkeypatch
    ):
        from unittest.mock import MagicMock

        from samuel.adapters.llm import costs
        from samuel.core.config import FileConfig

        configured: dict[str, Any] = {
            "default": {"provider": "deepseek", "fallbacks": []},
            "deepseek": {"model": "deepseek-chat"},
            "openrouter": {
                "url": "https://completion.example/api/v1",
                "models_url": "https://catalog.example/models",
                "benchmarks_url": "https://metadata.example/benchmarks",
            },
        }
        (tmp_path / "llm.json").write_text(json.dumps(configured))
        config = FileConfig(tmp_path)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data": []}'
        fetch = MagicMock(return_value=response)
        monkeypatch.setattr(costs.urllib.request, "urlopen", fetch)
        result = costs.refresh_pricing(tmp_path / "cache.json", "test-key", config=config)
        assert result["error"] is None
        assert [c.args[0].full_url for c in fetch.call_args_list] == [
            configured["openrouter"]["models_url"],
            configured["openrouter"]["benchmarks_url"],
        ]
        assert config.get("llm.default.provider") == "deepseek"
        assert config.get("llm.deepseek.model") == "deepseek-chat"
        assert config.get("llm.default.fallbacks") == []
        assert config.get("llm.openrouter.url") == "https://completion.example/api/v1"
        saved = json.loads((tmp_path / "cache.json").read_text())
        assert saved["sources"] == costs._catalog_sources

    def test_invalid_urls_are_rejected_before_network_without_secret_diagnostic(
        self, tmp_path, monkeypatch, caplog
    ):
        from unittest.mock import MagicMock

        from samuel.adapters.llm import costs
        from samuel.core.config import FileConfig

        fetch = MagicMock()
        monkeypatch.setattr(costs.urllib.request, "urlopen", fetch)
        for invalid in (
            "file:///etc/passwd",
            "https://user:secret@example/models",
            "https://example/models?token=secret",
            "https://example/models#secret",
            "https://example:bad/models",
            "https://example/models\nsecret",
            "",
            123,
        ):
            (tmp_path / "llm.json").write_text(json.dumps({"openrouter": {"models_url": invalid}}))
            result = costs.refresh_pricing(tmp_path / "cache.json", config=FileConfig(tmp_path))
            assert result["error"] == "ValueError"
            assert not (tmp_path / "cache.json").exists()
        fetch.assert_not_called()
        assert "secret" not in caplog.text

    def test_unreachable_source_does_not_overwrite_cache_or_expose_exception(
        self, tmp_path, monkeypatch, caplog
    ):
        from unittest.mock import MagicMock
        from urllib.error import URLError

        from samuel.adapters.llm import costs

        path = tmp_path / "cache.json"
        path.write_text('{"original": true}')
        monkeypatch.setattr(
            costs.urllib.request, "urlopen", MagicMock(side_effect=URLError("secret response"))
        )
        result = costs.refresh_pricing(path)
        assert result["error"] == "URLError"
        assert path.read_text() == '{"original": true}'
        assert "secret response" not in caplog.text

    def test_incompatible_catalog_fails_without_replacing_prior_evidence(
        self, tmp_path, monkeypatch
    ):
        from unittest.mock import MagicMock

        from samuel.adapters.llm import costs

        path = tmp_path / "cache.json"
        path.write_text('{"original": true}')
        response = MagicMock()
        invalid_documents: list[dict[str, Any]] = [
            {"results": []},
            {"data": {}},
            {"data": [None]},
            {"data": [{"id": ""}]},
        ]
        for invalid in invalid_documents:
            response.__enter__.return_value.read.return_value = json.dumps(invalid).encode()
            monkeypatch.setattr(costs.urllib.request, "urlopen", MagicMock(return_value=response))
            assert costs.refresh_pricing(path)["error"] == "ValueError"
            assert path.read_text() == '{"original": true}'

    def test_source_change_invalidates_cache_but_default_legacy_cache_remains_readable(
        self, tmp_path
    ):
        from samuel.adapters.llm import costs
        from samuel.core.config import FileConfig

        path = tmp_path / "cache.json"
        path.write_text(
            json.dumps(
                {"models": {"old/model": {}}, "fetched_at": time.time(), "schema_version": 3}
            )
        )
        costs._or_cache = None
        costs.configure_catalog_endpoints(FileConfig(tmp_path))
        assert costs._load_or_cache(path) == {"old/model": {}}
        (tmp_path / "llm.json").write_text(
            json.dumps({"openrouter": {"models_url": "https://other.example/models"}})
        )
        costs.configure_catalog_endpoints(FileConfig(tmp_path))
        assert costs._or_cache is None
        assert costs._load_or_cache(path) == {}
        assert costs._or_cache_schema == 0
