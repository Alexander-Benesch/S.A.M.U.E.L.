from __future__ import annotations

from unittest.mock import patch

from samuel.adapters.llm.claude import ClaudeAdapter
from samuel.adapters.llm.deepseek import DeepSeekAdapter
from samuel.adapters.llm.lmstudio import LMStudioAdapter
from samuel.adapters.llm.ollama import OllamaAdapter
from samuel.adapters.llm.openai_compat import OpenAICompatAdapter
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

CLAUDE_RESPONSE = {
    "content": [{"text": "Hello world"}],
    "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 3},
    "stop_reason": "end_turn",
    "model": "claude-sonnet-4-6",
}

OPENAI_RESPONSE = {
    "choices": [{"message": {"content": "Hello world"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 2}},
    "model": "deepseek-chat",
}

OLLAMA_RESPONSE = {
    "response": "Hello world",
    "model": "llama3",
    "prompt_eval_count": 10,
    "eval_count": 5,
}

MESSAGES = [{"role": "user", "content": "hi"}]


class TestClaudeAdapter:
    def test_implements_interface(self):
        adapter = ClaudeAdapter(api_key="test")
        assert isinstance(adapter, ILLMProvider)

    def test_capabilities(self):
        adapter = ClaudeAdapter(api_key="test")
        assert "tool_use" in adapter.capabilities
        assert "streaming" in adapter.capabilities

    def test_context_window(self):
        adapter = ClaudeAdapter(api_key="test", model="claude-opus-4-6")
        assert adapter.context_window == 200_000

    @patch("samuel.adapters.llm.claude.http_post", return_value=CLAUDE_RESPONSE)
    def test_complete(self, mock_post):
        adapter = ClaudeAdapter(api_key="test-key")
        resp = adapter.complete(MESSAGES)
        assert isinstance(resp, LLMResponse)
        assert resp.text == "Hello world"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.cached_tokens == 3
        assert resp.model_used == "claude-sonnet-4-6"
        assert resp.latency_ms >= 0

    def test_estimate_tokens(self):
        adapter = ClaudeAdapter(api_key="test")
        assert adapter.estimate_tokens("hello world") > 0


class TestDeepSeekAdapter:
    def test_implements_interface(self):
        assert isinstance(DeepSeekAdapter(api_key="test"), ILLMProvider)

    @patch("samuel.adapters.llm.openai_compat.http_post", return_value=OPENAI_RESPONSE)
    def test_complete(self, mock_post):
        adapter = DeepSeekAdapter(api_key="test-key")
        resp = adapter.complete(MESSAGES)
        assert resp.text == "Hello world"
        assert resp.input_tokens == 10
        assert resp.cached_tokens == 2

    def test_context_window(self):
        assert DeepSeekAdapter(api_key="test").context_window == 128_000


class TestOllamaAdapter:
    def test_implements_interface(self):
        assert isinstance(OllamaAdapter(), ILLMProvider)

    @patch("samuel.adapters.llm.ollama.http_post", return_value=OLLAMA_RESPONSE)
    def test_complete(self, mock_post):
        adapter = OllamaAdapter(model="llama3")
        resp = adapter.complete(MESSAGES)
        assert resp.text == "Hello world"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.model_used == "llama3"

    def test_capabilities_empty(self):
        assert OllamaAdapter().capabilities == set()


class TestLMStudioAdapter:
    def test_implements_interface(self):
        assert isinstance(LMStudioAdapter(), ILLMProvider)

    def test_context_window(self):
        assert LMStudioAdapter().context_window == 32_000

    # #328-followup: /v1-suffix-Normalisierung
    def test_lmstudio_appends_v1_if_missing(self):
        a = LMStudioAdapter(base_url="http://192.168.1.158:1234")
        assert a._base_url == "http://192.168.1.158:1234/v1"

    def test_lmstudio_keeps_v1_if_present(self):
        a = LMStudioAdapter(base_url="http://192.168.1.158:1234/v1")
        assert a._base_url == "http://192.168.1.158:1234/v1"

    def test_lmstudio_strips_trailing_slash_then_appends_v1(self):
        a = LMStudioAdapter(base_url="http://localhost:1234/")
        assert a._base_url == "http://localhost:1234/v1"

    def test_lmstudio_validate_rejects_200_without_data_array(self, monkeypatch):
        """#328-followup: 200 mit Error-Body (z.B. /models statt /v1/models)
        darf nicht als 'Connection OK' gelten."""
        monkeypatch.setattr(
            "samuel.adapters.llm.http.http_get",
            lambda *a, **kw: (200, {"error": "Unexpected endpoint"}),
        )
        a = LMStudioAdapter(base_url="http://192.168.1.158:1234/v1")
        res = a.validate()
        assert res["valid"] is False
        assert "OpenAI-compat" in res["detail"] or "/v1" in res["detail"]

    def test_lmstudio_validate_accepts_200_with_data_array(self, monkeypatch):
        monkeypatch.setattr(
            "samuel.adapters.llm.http.http_get",
            lambda *a, **kw: (200, {"data": [{"id": "model-x"}]}),
        )
        a = LMStudioAdapter()
        res = a.validate()
        assert res["valid"] is True


class TestOpenAICompatAdapter:
    @patch("samuel.adapters.llm.openai_compat.http_post", return_value=OPENAI_RESPONSE)
    def test_complete(self, mock_post):
        adapter = OpenAICompatAdapter(
            api_key="key", base_url="http://api.example.com/v1", model="gpt-4o"
        )
        resp = adapter.complete(MESSAGES)
        assert isinstance(resp, LLMResponse)
        assert resp.text == "Hello world"


# #211: validate() tests
class TestAdapterValidate:
    def test_claude_validate_no_api_key(self):
        from samuel.adapters.llm.claude import ClaudeAdapter
        a = ClaudeAdapter(api_key="", model="claude-sonnet-4-6")
        res = a.validate()
        assert res["valid"] is False
        assert "no api key" in res["detail"]

    def test_claude_validate_unauthorized(self, monkeypatch):
        from samuel.adapters.llm.claude import ClaudeAdapter
        monkeypatch.setattr("samuel.adapters.llm.http.http_head", lambda *a, **kw: 401)
        a = ClaudeAdapter(api_key="bad-key", model="claude-sonnet-4-6")
        res = a.validate()
        assert res["valid"] is False
        assert res["detail"] == "unauthorized"


# #304: OpenAI top-level adapter
class TestOpenAIAdapter:
    def test_implements_interface(self):
        from samuel.adapters.llm.openai import OpenAIAdapter
        assert isinstance(OpenAIAdapter(api_key="test"), ILLMProvider)

    @patch("samuel.adapters.llm.openai_compat.http_post", return_value=OPENAI_RESPONSE)
    def test_openai_adapter_complete(self, mock_post):
        """#304-AC: name matches issue-body anchor."""
        from samuel.adapters.llm.openai import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="key")
        resp = adapter.complete(MESSAGES)
        assert isinstance(resp, LLMResponse)
        assert resp.text == "Hello world"

    def test_openai_validate_no_api_key(self):
        from samuel.adapters.llm.openai import OpenAIAdapter
        a = OpenAIAdapter(api_key="")
        res = a.validate()
        assert res["valid"] is False
        assert "no api key" in res["detail"]

    def test_openai_validate_ok(self, monkeypatch):
        from samuel.adapters.llm.openai import OpenAIAdapter
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", lambda *a, **kw: (200, {"data": []}))
        a = OpenAIAdapter(api_key="ok")
        res = a.validate()
        assert res["valid"] is True

    def test_openai_validate_unauthorized(self, monkeypatch):
        from samuel.adapters.llm.openai import OpenAIAdapter
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", lambda *a, **kw: (401, None))
        a = OpenAIAdapter(api_key="bad")
        res = a.validate()
        assert res["valid"] is False
        assert res["detail"] == "unauthorized"

    def test_claude_validate_ok(self, monkeypatch):
        from samuel.adapters.llm.claude import ClaudeAdapter
        monkeypatch.setattr("samuel.adapters.llm.http.http_head", lambda *a, **kw: 200)
        a = ClaudeAdapter(api_key="ok", model="claude-sonnet-4-6")
        res = a.validate()
        assert res["valid"] is True

    def test_deepseek_validate_returns_balance(self, monkeypatch):
        from samuel.adapters.llm.deepseek import DeepSeekAdapter
        body = {"balance_infos": [{"total_balance": "12.50"}]}
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", lambda *a, **kw: (200, body))
        a = DeepSeekAdapter(api_key="dk")
        res = a.validate()
        assert res["valid"] is True
        assert res["balance"] == 12.5

    def test_deepseek_validate_unauthorized(self, monkeypatch):
        from samuel.adapters.llm.deepseek import DeepSeekAdapter
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", lambda *a, **kw: (401, None))
        a = DeepSeekAdapter(api_key="bad")
        res = a.validate()
        assert res["valid"] is False
        assert res["detail"] == "unauthorized"

    def test_ollama_validate_unreachable(self, monkeypatch):
        from samuel.adapters.llm.ollama import OllamaAdapter
        def _raise(*a, **kw):
            raise OSError("connection refused")
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", _raise)
        a = OllamaAdapter(model="llama3")
        res = a.validate()
        assert res["valid"] is False
        assert res["detail"] == "unreachable"

    def test_ollama_validate_ok(self, monkeypatch):
        from samuel.adapters.llm.ollama import OllamaAdapter
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", lambda *a, **kw: (200, {"models": []}))
        a = OllamaAdapter(model="llama3")
        res = a.validate()
        assert res["valid"] is True

    def test_lmstudio_validate_ok(self, monkeypatch):
        from samuel.adapters.llm.lmstudio import LMStudioAdapter
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", lambda *a, **kw: (200, {"data": []}))
        a = LMStudioAdapter()
        res = a.validate()
        assert res["valid"] is True

    def test_manual_validate_writable(self, tmp_path):
        from samuel.adapters.llm.manual import ManualAdapter
        a = ManualAdapter(data_dir=str(tmp_path), poll_interval=0.1, timeout_seconds=2)
        res = a.validate()
        assert res["valid"] is True
        assert res["detail"] == "fs ok"

    def test_manual_validate_missing_dir(self, tmp_path):
        # ManualAdapter.__init__ creates the data_dir; check that a clearly
        # missing dir is detected when we point at a path that won't be auto-created.
        from samuel.adapters.llm.manual import ManualAdapter
        a = ManualAdapter(data_dir=str(tmp_path), poll_interval=0.1, timeout_seconds=2)
        # Simulate dir-disappearance after init (rare but possible: removed mount)
        import shutil
        shutil.rmtree(tmp_path)
        res = a.validate()
        assert res["valid"] is False
        assert "missing" in res["detail"]


# #303: Gemini adapter
class TestGeminiAdapter:
    def test_implements_interface(self):
        from samuel.adapters.llm.gemini import GeminiAdapter
        assert isinstance(GeminiAdapter(api_key="test"), ILLMProvider)

    @patch("samuel.adapters.llm.gemini.http_post")
    def test_gemini_adapter_complete(self, mock_post):
        """#303-AC: name matches issue-body anchor for AC-Verifier."""
        from samuel.adapters.llm.gemini import GeminiAdapter
        mock_post.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello world"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        }
        adapter = GeminiAdapter(api_key="key")
        resp = adapter.complete(MESSAGES)
        assert isinstance(resp, LLMResponse)
        assert resp.text == "Hello world"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5

    def test_estimate_tokens(self):
        from samuel.adapters.llm.gemini import GeminiAdapter
        assert GeminiAdapter(api_key="k").estimate_tokens("hello world") > 0

    def test_gemini_validate_no_api_key(self):
        from samuel.adapters.llm.gemini import GeminiAdapter
        a = GeminiAdapter(api_key="")
        res = a.validate()
        assert res["valid"] is False
        assert "no api key" in res["detail"]

    def test_gemini_validate_ok(self, monkeypatch):
        from samuel.adapters.llm.gemini import GeminiAdapter
        monkeypatch.setattr("samuel.adapters.llm.gemini.http_get", lambda *a, **kw: (200, {"models": []}))
        a = GeminiAdapter(api_key="ok")
        res = a.validate()
        assert res["valid"] is True

    def test_gemini_validate_unauthorized(self, monkeypatch):
        from samuel.adapters.llm.gemini import GeminiAdapter
        monkeypatch.setattr("samuel.adapters.llm.gemini.http_get", lambda *a, **kw: (403, None))
        a = GeminiAdapter(api_key="bad")
        res = a.validate()
        assert res["valid"] is False
        assert res["detail"] == "unauthorized"


# #311: list_models() per Adapter
class TestListModels:
    def test_ollama_list_models(self, monkeypatch):
        from samuel.adapters.llm.ollama import OllamaAdapter
        monkeypatch.setattr(
            "samuel.adapters.llm.http.http_get",
            lambda *a, **kw: (200, {"models": [{"name": "llama3:8b"}, {"name": "qwen:7b"}]}),
        )
        a = OllamaAdapter(model="llama3")
        rows = a.list_models()
        assert len(rows) == 2
        ids = [r["id"] for r in rows]
        assert "llama3:8b" in ids
        assert "qwen:7b" in ids

    def test_ollama_list_models_unreachable_returns_empty(self, monkeypatch):
        from samuel.adapters.llm.ollama import OllamaAdapter
        def _raise(*a, **kw):
            raise OSError("connection refused")
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", _raise)
        a = OllamaAdapter(model="llama3")
        assert a.list_models() == []

    def test_lmstudio_list_models(self, monkeypatch):
        from samuel.adapters.llm.lmstudio import LMStudioAdapter
        monkeypatch.setattr(
            "samuel.adapters.llm.http.http_get",
            lambda *a, **kw: (200, {"data": [{"id": "qwen-7b-coder"}, {"id": "phi-3"}]}),
        )
        a = LMStudioAdapter()
        rows = a.list_models()
        assert len(rows) == 2
        assert "phi-3" in [r["id"] for r in rows]

    def test_manual_list_models_returns_empty(self, tmp_path):
        from samuel.adapters.llm.manual import ManualAdapter
        a = ManualAdapter(data_dir=str(tmp_path), poll_interval=0.1, timeout_seconds=2)
        assert a.list_models() == []

    def test_claude_list_models_returns_empty(self):
        from samuel.adapters.llm.claude import ClaudeAdapter
        assert ClaudeAdapter(api_key="k").list_models() == []

    def test_gemini_list_models_returns_empty(self):
        from samuel.adapters.llm.gemini import GeminiAdapter
        assert GeminiAdapter(api_key="k").list_models() == []


# #318: OpenRouter Gateway Adapter
class TestOpenRouterAdapter:
    def test_implements_interface(self):
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        assert isinstance(OpenRouterAdapter(api_key="test"), ILLMProvider)

    def test_base_url(self):
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        a = OpenRouterAdapter(api_key="k")
        assert a.BASE_URL == "https://openrouter.ai/api/v1"
        assert a._base_url == "https://openrouter.ai/api/v1"

    @patch("samuel.adapters.llm.openai_compat.http_post", return_value=OPENAI_RESPONSE)
    def test_openrouter_adapter_complete(self, mock_post):
        """#318-AC: name matches issue-body anchor for AC-Verifier."""
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        adapter = OpenRouterAdapter(api_key="key", model="anthropic/claude-sonnet-4-6")
        resp = adapter.complete(MESSAGES)
        assert isinstance(resp, LLMResponse)
        assert resp.text == "Hello world"

    def test_openrouter_validate_no_api_key(self):
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        a = OpenRouterAdapter(api_key="")
        res = a.validate()
        assert res["valid"] is False
        assert res["balance"] is None

    def test_openrouter_validate_returns_balance(self, monkeypatch):
        """#318-AC: validate() liefert Balance via /auth/key."""
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        body = {"data": {"limit": 25.0, "usage": 7.5, "limit_remaining": 17.5}}
        monkeypatch.setattr(
            "samuel.adapters.llm.http.http_get",
            lambda *a, **kw: (200, body),
        )
        a = OpenRouterAdapter(api_key="ok")
        res = a.validate()
        assert res["valid"] is True
        assert res["balance"] == 17.5

    def test_openrouter_validate_balance_computed_from_limit_minus_usage(self, monkeypatch):
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        body = {"data": {"limit": 10.0, "usage": 3.0}}  # no limit_remaining
        monkeypatch.setattr(
            "samuel.adapters.llm.http.http_get",
            lambda *a, **kw: (200, body),
        )
        a = OpenRouterAdapter(api_key="ok")
        res = a.validate()
        assert res["valid"] is True
        assert res["balance"] == 7.0

    def test_openrouter_validate_unauthorized(self, monkeypatch):
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        monkeypatch.setattr(
            "samuel.adapters.llm.http.http_get",
            lambda *a, **kw: (401, None),
        )
        a = OpenRouterAdapter(api_key="bad")
        res = a.validate()
        assert res["valid"] is False
        assert res["detail"] == "unauthorized"

    def test_openrouter_validate_unreachable(self, monkeypatch):
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        def _raise(*a, **kw):
            raise OSError("connection refused")
        monkeypatch.setattr("samuel.adapters.llm.http.http_get", _raise)
        a = OpenRouterAdapter(api_key="x")
        res = a.validate()
        assert res["valid"] is False
        assert res["detail"] == "unreachable"

    def test_openrouter_list_models_returns_all(self, monkeypatch):
        """#318-AC: list_models() liefert ALLE Modelle (kein Vendor-Filter)."""
        from samuel.adapters.llm import costs
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        fake_cache = {
            "anthropic/claude-sonnet-4-6": {"name": "Claude Sonnet 4.6", "prompt": 0.000003, "completion": 0.000015, "context_length": 200000},
            "openai/gpt-4o-mini":           {"name": "GPT-4o Mini",       "prompt": 0.00000015, "completion": 0.0000006, "context_length": 128000},
            "deepseek/deepseek-chat":       {"name": "DeepSeek Chat",      "prompt": 0.00000014, "completion": 0.00000028, "context_length": 64000},
        }
        monkeypatch.setattr(costs, "_or_cache", fake_cache)
        import time as _t
        monkeypatch.setattr(costs, "_or_cache_ts", _t.time())
        a = OpenRouterAdapter(api_key="k")
        rows = a.list_models()
        assert len(rows) == 3
        ids = [r["id"] for r in rows]
        assert "anthropic/claude-sonnet-4-6" in ids
        assert "openai/gpt-4o-mini" in ids
        assert "deepseek/deepseek-chat" in ids
        # ``model`` field should be the full vendor/model id (used as OpenRouter model param)
        for r in rows:
            assert "/" in r["model"]