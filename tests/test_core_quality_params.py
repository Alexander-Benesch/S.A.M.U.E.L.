"""#153: Tests fuer den Param-Size-Check lokaler LLM-Modelle."""

from __future__ import annotations

from samuel.core.quality_params import check_local_model_size, parse_param_size_b


class TestParseParamSize:
    def test_colon_tag(self):
        assert parse_param_size_b("llama3:8b") == 8.0

    def test_dash_suffix(self):
        assert parse_param_size_b("qwen2.5-14b") == 14.0

    def test_decimal(self):
        assert parse_param_size_b("phi-3-mini-3.8b") == 3.8

    def test_mixture_of_experts(self):
        assert parse_param_size_b("mixtral:8x7b") == 56.0

    def test_uppercase_b(self):
        assert parse_param_size_b("Model-70B") == 70.0

    def test_no_size_returns_none(self):
        assert parse_param_size_b("local-model") is None
        assert parse_param_size_b("") is None


class TestCheckLocalModelSize:
    def test_cloud_provider_never_warns(self):
        assert check_local_model_size("deepseek", "deepseek-chat", 7) is None

    def test_local_below_min_warns(self):
        w = check_local_model_size("ollama", "llama3:3b", 7)
        assert w is not None
        assert w["reason"] == "below_min"
        assert w["params_b"] == 3.0

    def test_local_at_or_above_min_ok(self):
        assert check_local_model_size("ollama", "llama3:8b", 7) is None

    def test_local_unknown_size_warns(self):
        w = check_local_model_size("lmstudio", "local-model", 7)
        assert w is not None
        assert w["reason"] == "unknown_size"
        assert w["params_b"] is None
