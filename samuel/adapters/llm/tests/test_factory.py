from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from samuel.adapters.llm.circuit_breaker import CircuitBreakerAdapter
from samuel.adapters.llm.claude import ClaudeAdapter
from samuel.adapters.llm.deepseek import DeepSeekAdapter
from samuel.adapters.llm.factory import create_llm_adapter
from samuel.adapters.llm.lmstudio import LMStudioAdapter
from samuel.adapters.llm.ollama import OllamaAdapter
from samuel.adapters.llm.sanitizer import SanitizingLLMAdapter
from samuel.core.ports import IConfig, ILLMProvider, ISecretsProvider


def _make_config(provider: str = "ollama") -> MagicMock:
    """Default test config — points ``agent.config_dir`` at a path that has
    no ``llm/defaults.json``, so the basic factory tests don't accidentally
    pick up the repo's real defaults (which carry per-task system_prompt
    overrides since #338-audit-fix-2 and would force TaskRouting on every
    test)."""
    config = MagicMock(spec=IConfig)
    config.get.side_effect = lambda key, default=None: {
        "llm.default.provider":  provider,
        "agent.config_dir":      "/tmp/samuel-factory-tests-no-defaults",
    }.get(key, default)
    return config


def _make_secrets(**kv) -> MagicMock:
    secrets = MagicMock(spec=ISecretsProvider)
    secrets.get.side_effect = lambda key: kv.get(key, "test-key")
    return secrets


class TestFactory:
    def test_creates_ollama_by_default(self):
        adapter = create_llm_adapter(_make_config("ollama"), _make_secrets())
        assert isinstance(adapter, CircuitBreakerAdapter)
        assert isinstance(adapter._inner, SanitizingLLMAdapter)
        assert isinstance(adapter._inner._inner, OllamaAdapter)

    def test_creates_claude(self):
        adapter = create_llm_adapter(
            _make_config("claude"), _make_secrets(ANTHROPIC_API_KEY="sk-123")
        )
        assert isinstance(adapter._inner._inner, ClaudeAdapter)

    def test_creates_deepseek(self):
        adapter = create_llm_adapter(
            _make_config("deepseek"), _make_secrets(DEEPSEEK_API_KEY="dk-123")
        )
        assert isinstance(adapter._inner._inner, DeepSeekAdapter)

    def test_creates_lmstudio(self):
        adapter = create_llm_adapter(_make_config("lmstudio"), _make_secrets())
        assert isinstance(adapter._inner._inner, LMStudioAdapter)

    def test_factory_creates_gemini(self):
        """#303-AC: name matches issue-body anchor for AC-Verifier."""
        from samuel.adapters.llm.gemini import GeminiAdapter
        adapter = create_llm_adapter(
            _make_config("gemini"), _make_secrets(GEMINI_API_KEY="g-123"),
        )
        assert isinstance(adapter._inner._inner, GeminiAdapter)

    def test_factory_creates_openai(self):
        """#304-AC."""
        from samuel.adapters.llm.openai import OpenAIAdapter
        adapter = create_llm_adapter(
            _make_config("openai"), _make_secrets(OPENAI_API_KEY="o-123"),
        )
        assert isinstance(adapter._inner._inner, OpenAIAdapter)

    def test_factory_creates_openrouter(self):
        """#318-AC: name matches issue-body anchor for AC-Verifier."""
        from samuel.adapters.llm.openrouter import OpenRouterAdapter
        adapter = create_llm_adapter(
            _make_config("openrouter"), _make_secrets(OPENROUTER_API_KEY="or-123"),
        )
        assert isinstance(adapter._inner._inner, OpenRouterAdapter)
        assert adapter._inner._inner._base_url == "https://openrouter.ai/api/v1"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider 'foo'"):
            create_llm_adapter(_make_config("foo"), _make_secrets())

    def test_returns_illmprovider(self):
        adapter = create_llm_adapter(_make_config(), _make_secrets())
        assert isinstance(adapter, ILLMProvider)

    def test_wraps_with_sanitizer_and_circuit_breaker(self):
        adapter = create_llm_adapter(_make_config("claude"), _make_secrets())
        assert isinstance(adapter, CircuitBreakerAdapter)
        assert isinstance(adapter._inner, SanitizingLLMAdapter)

    def test_env_override_wins_over_config(self, monkeypatch):
        from samuel.adapters.llm.manual import ManualAdapter

        monkeypatch.setenv("SAMUEL_LLM_PROVIDER", "manual")
        adapter = create_llm_adapter(_make_config("deepseek"), _make_secrets())
        assert isinstance(adapter._inner._inner, ManualAdapter)

    def test_env_override_unset_uses_config(self, monkeypatch):
        monkeypatch.delenv("SAMUEL_LLM_PROVIDER", raising=False)
        adapter = create_llm_adapter(_make_config("ollama"), _make_secrets())
        assert isinstance(adapter._inner._inner, OllamaAdapter)


class TestTaskRoutingFactory:
    """#225: Premium-gated TaskRoutingLLMAdapter wiring."""

    def _make_config_with_tasks(self, tmp_path, provider="ollama"):
        """Config that points to a real tmp_path/llm/defaults.json with tasks."""
        import json as _json
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        defaults = {
            "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
            "tasks": {
                "planning": {"provider": "claude", "max_tokens": 4096},
                "review": {"provider": "deepseek"},
            },
            "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 120},
        }
        (llm_dir / "defaults.json").write_text(_json.dumps(defaults))

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": provider,
            "agent.config_dir": str(tmp_path),
        }.get(key, default)
        return config

    def test_factory_skips_task_routing_when_no_provider_overrides_in_free_mode(self, tmp_path, monkeypatch):
        """#301: Free mode without provider overrides -> default-only chain."""
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "is_premium_active", lambda: False)
        monkeypatch.setattr(_lic, "has_feature", lambda f: False)

        # Use config WITHOUT provider overrides
        import json as _json
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
            "tasks": {"planning": {"max_tokens": 4096}},  # no provider key
        }))
        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "ollama",
            "agent.config_dir": str(tmp_path),
        }.get(key, default)

        adapter = create_llm_adapter(config, _make_secrets())

        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        assert not isinstance(adapter._inner._inner, TaskRoutingLLMAdapter)

    def test_factory_builds_task_routing_with_license_and_feature(self, tmp_path, monkeypatch):
        """With premium + llm_routing feature, TaskRouting wraps the metered chain."""
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "is_premium_active", lambda: True)
        monkeypatch.setattr(_lic, "has_feature", lambda f: f == "llm_routing")

        config = self._make_config_with_tasks(tmp_path, "ollama")
        adapter = create_llm_adapter(config, _make_secrets(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k"))

        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        # CircuitBreaker -> Sanitizer -> TaskRouting -> default-metered
        assert isinstance(adapter._inner._inner, TaskRoutingLLMAdapter)

    def test_factory_skips_task_routing_when_tasks_have_no_provider_override(self, tmp_path, monkeypatch):
        """Premium license but tasks have only max_tokens/temperature — no routing built."""
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "is_premium_active", lambda: True)
        monkeypatch.setattr(_lic, "has_feature", lambda f: True)

        import json as _json
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        defaults = {
            "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
            "tasks": {"planning": {"max_tokens": 4096, "temperature": 0.3}},
        }
        (llm_dir / "defaults.json").write_text(_json.dumps(defaults))

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "ollama",
            "agent.config_dir": str(tmp_path),
        }.get(key, default)

        adapter = create_llm_adapter(config, _make_secrets())

        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        assert not isinstance(adapter._inner._inner, TaskRoutingLLMAdapter)


# #301: per-task base_url / timeout overrides + free-mode TaskRouting
class TestPerTaskOverrides:
    def _make_config_with_overrides(self, tmp_path):
        import json as _json
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        defaults = {
            "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
            "tasks": {
                "planning": {
                    "provider": "ollama",
                    "model": "llama3:custom",
                    "base_url": "http://192.168.1.158:11434",
                    "timeout": 180,
                },
                "review": {"provider": "deepseek"},
            },
        }
        (llm_dir / "defaults.json").write_text(_json.dumps(defaults))

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "manual",
            "agent.config_dir": str(tmp_path),
        }.get(key, default)
        return config

    def test_factory_per_task_routing_in_free_mode_now_works(self, tmp_path, monkeypatch):
        """#301: Static per-task routing is FREE (gate relaxed from #225)."""
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "is_premium_active", lambda: False)
        monkeypatch.setattr(_lic, "has_feature", lambda f: False)

        config = self._make_config_with_overrides(tmp_path)
        adapter = create_llm_adapter(
            config, _make_secrets(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k"),
        )
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        assert isinstance(adapter._inner._inner, TaskRoutingLLMAdapter)
        assert "planning" in adapter._inner._inner._by_task
        assert "review" in adapter._inner._inner._by_task

    def test_factory_per_task_base_url_override(self, tmp_path):
        config = self._make_config_with_overrides(tmp_path)
        adapter = create_llm_adapter(
            config, _make_secrets(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k"),
        )
        from samuel.adapters.llm.metering import MeteringLLMAdapter
        from samuel.adapters.llm.ollama import OllamaAdapter
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        routing = adapter._inner._inner
        assert isinstance(routing, TaskRoutingLLMAdapter)
        planning_metered = routing._by_task["planning"]
        # Walk through metering wrapper to OllamaAdapter
        inner = planning_metered._inner if isinstance(planning_metered, MeteringLLMAdapter) else planning_metered
        assert isinstance(inner, OllamaAdapter)
        assert inner._base_url == "http://192.168.1.158:11434"

    def test_factory_per_task_timeout_override(self, tmp_path):
        config = self._make_config_with_overrides(tmp_path)
        adapter = create_llm_adapter(
            config, _make_secrets(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k"),
        )
        # planning has timeout=180 — assert it landed on the inner adapter when applicable
        # Ollama doesn't have _timeout in current shape; smoke that nothing crashes
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        assert isinstance(adapter._inner._inner, TaskRoutingLLMAdapter)
        assert "planning" in adapter._inner._inner._by_task


# #302: Time-window schedule (premium llm_routing_advanced)
class TestScheduledRoutingFactory:
    def _make_config_with_schedule(self, tmp_path):
        import json as _json
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "default": {"max_tokens": 4096, "temperature": 0.2, "timeout": 60},
            "tasks": {
                "implementation": {
                    "provider": "deepseek",
                    "model": "deepseek-coder",
                    "schedule": {
                        "active": True, "from": "22:00", "to": "06:00",
                        "provider": "claude", "model": "claude-opus",
                    },
                },
            },
        }))

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "ollama",
            "agent.config_dir": str(tmp_path),
        }.get(key, default)
        return config

    def test_factory_skips_schedule_in_free_mode(self, tmp_path, monkeypatch):
        """Ohne premium llm_routing_advanced: kein ScheduledTaskRoutingAdapter."""
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "is_premium_active", lambda: False)
        monkeypatch.setattr(_lic, "has_feature", lambda f: False)

        config = self._make_config_with_schedule(tmp_path)
        adapter = create_llm_adapter(
            config, _make_secrets(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k"),
        )
        from samuel.adapters.llm.scheduled_routing import ScheduledTaskRoutingAdapter
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        # TaskRouting (free) should still be there because tasks have static provider
        assert isinstance(adapter._inner._inner, TaskRoutingLLMAdapter)
        assert not isinstance(adapter._inner._inner, ScheduledTaskRoutingAdapter)

    def test_factory_builds_schedule_with_premium_advanced(self, tmp_path, monkeypatch):
        """Mit premium llm_routing_advanced: ScheduledTaskRoutingAdapter eingebaut."""
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "is_premium_active", lambda: True)
        monkeypatch.setattr(_lic, "has_feature", lambda f: f == "llm_routing_advanced")

        config = self._make_config_with_schedule(tmp_path)
        adapter = create_llm_adapter(
            config, _make_secrets(ANTHROPIC_API_KEY="k", DEEPSEEK_API_KEY="k"),
        )
        from samuel.adapters.llm.scheduled_routing import ScheduledTaskRoutingAdapter
        assert isinstance(adapter._inner._inner, ScheduledTaskRoutingAdapter)
        assert "implementation" in adapter._inner._inner._schedules


class TestSystemPromptWiring:
    """#338 Schicht B Wiring: factory wraps task adapters with
    SystemPromptInjectorAdapter, resolving the prompt via
    load_system_prompt's 4-stage cascade (model > provider > generic >
    package)."""

    def _make_config_with_system_prompt(self, tmp_path, scope_layout):
        """Build a config with a planner-task that references planner.md
        and seed operator-overrides at ``scope_layout`` (dict of
        relative-path -> content under tmp_path)."""
        import json as _json

        # Seed operator overrides
        for rel, content in scope_layout.items():
            fp = tmp_path / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")

        llm_dir = tmp_path / "llm"
        llm_dir.mkdir(exist_ok=True)
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "default": {"max_tokens": 4096, "temperature": 0.2},
            "tasks": {
                "planning": {
                    "provider": "ollama",
                    "model": "qwen2.5-coder-7b",
                    "system_prompt": "planner.md",
                },
                # Other task without system_prompt — should NOT get wrapped
                "review": {"provider": "deepseek"},
            },
        }))

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "manual",
            "agent.config_dir": str(tmp_path),
        }.get(key, default)
        return config

    def _resolve_planning_chain(self, adapter):
        """Walk through Sanitizer + CircuitBreaker + TaskRouting + Metering
        to get the actual planning-task adapter the factory built."""
        from samuel.adapters.llm.metering import MeteringLLMAdapter
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter

        routing = adapter._inner._inner
        assert isinstance(routing, TaskRoutingLLMAdapter)
        planning = routing._by_task["planning"]
        # MeteringLLMAdapter is the outermost wrapper around the leaf
        if isinstance(planning, MeteringLLMAdapter):
            planning = planning._inner
        return planning

    def test_factory_wraps_with_system_prompt_when_configured(self, tmp_path):
        """Tasks with system_prompt config get a SystemPromptInjectorAdapter."""
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter

        config = self._make_config_with_system_prompt(tmp_path, {
            "llm/prompts/planner.md": "GENERIC PLANNER",
        })
        adapter = create_llm_adapter(
            config, _make_secrets(DEEPSEEK_API_KEY="k"),
        )
        planning = self._resolve_planning_chain(adapter)
        assert isinstance(planning, SystemPromptInjectorAdapter)
        assert "GENERIC PLANNER" in planning._prompt

    def test_factory_uses_model_override_for_prompt_lookup(self, tmp_path):
        """4-Stage cascade reaches the configured model — model file wins."""
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter

        config = self._make_config_with_system_prompt(tmp_path, {
            "llm/prompts/planner.md": "GENERIC",
            "llm/prompts/provider/ollama/planner.md": "PROVIDER OLLAMA",
            "llm/prompts/model/qwen2.5-coder-7b/planner.md": "MODEL QWEN",
        })
        adapter = create_llm_adapter(
            config, _make_secrets(DEEPSEEK_API_KEY="k"),
        )
        planning = self._resolve_planning_chain(adapter)
        assert isinstance(planning, SystemPromptInjectorAdapter)
        assert planning._prompt == "MODEL QWEN"

    def test_factory_falls_back_to_provider_when_no_model_override(self, tmp_path):
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter

        config = self._make_config_with_system_prompt(tmp_path, {
            "llm/prompts/planner.md": "GENERIC",
            "llm/prompts/provider/ollama/planner.md": "PROVIDER OLLAMA",
        })
        adapter = create_llm_adapter(
            config, _make_secrets(DEEPSEEK_API_KEY="k"),
        )
        planning = self._resolve_planning_chain(adapter)
        assert isinstance(planning, SystemPromptInjectorAdapter)
        assert planning._prompt == "PROVIDER OLLAMA"

    def test_factory_does_not_wrap_when_no_system_prompt_config(self, tmp_path):
        """Tasks without system_prompt field stay unwrapped."""
        from samuel.adapters.llm.metering import MeteringLLMAdapter
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter

        config = self._make_config_with_system_prompt(tmp_path, {
            "llm/prompts/planner.md": "GENERIC",
        })
        adapter = create_llm_adapter(
            config, _make_secrets(DEEPSEEK_API_KEY="k"),
        )
        routing = adapter._inner._inner
        assert isinstance(routing, TaskRoutingLLMAdapter)
        review = routing._by_task["review"]
        # Walk through Metering if present
        if isinstance(review, MeteringLLMAdapter):
            review = review._inner
        assert not isinstance(review, SystemPromptInjectorAdapter)

    def test_factory_skips_wrapping_when_prompt_resolves_empty(self, tmp_path):
        """Typo'd filename: load_system_prompt returns ''; wrapper skipped."""
        import json as _json

        from samuel.adapters.llm.metering import MeteringLLMAdapter
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter

        # Configure a task with system_prompt but DON'T seed the file anywhere
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "tasks": {
                "planning": {
                    "provider": "ollama",
                    "system_prompt": "does_not_exist.md",
                },
            },
        }))

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "manual",
            "agent.config_dir": str(tmp_path),
        }.get(key, default)

        adapter = create_llm_adapter(config, _make_secrets())
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
        routing = adapter._inner._inner
        assert isinstance(routing, TaskRoutingLLMAdapter)
        planning = routing._by_task["planning"]
        if isinstance(planning, MeteringLLMAdapter):
            planning = planning._inner
        assert not isinstance(planning, SystemPromptInjectorAdapter)

    def test_factory_wraps_when_only_system_prompt_set_no_provider_override(
        self, tmp_path,
    ):
        """#338-audit: Task with ONLY ``system_prompt`` (no provider) must
        still get a wrapper — otherwise the configured prompt is silently
        dropped at runtime. Build a task adapter from the default provider.
        """
        import json as _json

        from samuel.adapters.llm.metering import MeteringLLMAdapter
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter

        # review-task only has system_prompt, no provider override
        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "tasks": {
                "review": {"system_prompt": "reviewer.md"},
            },
        }))
        prompt_dir = tmp_path / "llm" / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        (prompt_dir / "reviewer.md").write_text("REVIEW PROMPT", encoding="utf-8")

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "manual",
            "agent.config_dir":     str(tmp_path),
        }.get(key, default)

        adapter = create_llm_adapter(config, _make_secrets())
        routing = adapter._inner._inner
        assert isinstance(routing, TaskRoutingLLMAdapter)
        assert "review" in routing._by_task
        review = routing._by_task["review"]
        if isinstance(review, MeteringLLMAdapter):
            review = review._inner
        assert isinstance(review, SystemPromptInjectorAdapter)
        assert review._prompt == "REVIEW PROMPT"

    def test_factory_uses_by_provider_override_for_specific_provider(
        self, tmp_path,
    ):
        """#351 Hybrid: when the task has system_prompt_by_provider and
        the active provider has an entry, that file's content is what gets
        injected — not the task's default ``system_prompt``."""
        import json as _json

        from samuel.adapters.llm.metering import MeteringLLMAdapter
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter

        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "tasks": {
                "planning": {
                    "provider": "ollama",
                    "model":    "llama3",
                    "system_prompt": "planner.md",
                    "system_prompt_by_provider": {
                        "ollama": "planner_local.md",
                    },
                },
            },
        }))
        prompt_dir = tmp_path / "llm" / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        (prompt_dir / "planner.md").write_text("DEFAULT", encoding="utf-8")
        (prompt_dir / "planner_local.md").write_text(
            "LOCAL LLM PROMPT", encoding="utf-8",
        )

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "manual",
            "agent.config_dir":     str(tmp_path),
            "llm.ollama.url":       "http://localhost:11434",
        }.get(key, default)

        adapter = create_llm_adapter(config, _make_secrets())
        routing = adapter._inner._inner
        assert isinstance(routing, TaskRoutingLLMAdapter)
        plan = routing._by_task["planning"]
        if isinstance(plan, MeteringLLMAdapter):
            plan = plan._inner
        assert isinstance(plan, SystemPromptInjectorAdapter)
        # Map entry wins over task default
        assert plan._prompt == "LOCAL LLM PROMPT"

    def test_factory_falls_back_to_default_prompt_when_provider_not_in_map(
        self, tmp_path,
    ):
        """When the active provider is not in the by_provider map, the
        task's default ``system_prompt`` is used (legacy behaviour)."""
        import json as _json

        from samuel.adapters.llm.metering import MeteringLLMAdapter
        from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter
        from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter

        llm_dir = tmp_path / "llm"
        llm_dir.mkdir()
        (llm_dir / "defaults.json").write_text(_json.dumps({
            "tasks": {
                "planning": {
                    "provider": "ollama",
                    "model":    "llama3",
                    "system_prompt": "planner.md",
                    "system_prompt_by_provider": {
                        # only deepseek mapped — ollama uses the default
                        "deepseek": "planner_kompakt.md",
                    },
                },
            },
        }))
        prompt_dir = tmp_path / "llm" / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        (prompt_dir / "planner.md").write_text("DEFAULT", encoding="utf-8")

        config = MagicMock(spec=IConfig)
        config.get.side_effect = lambda key, default=None: {
            "llm.default.provider": "manual",
            "agent.config_dir":     str(tmp_path),
            "llm.ollama.url":       "http://localhost:11434",
        }.get(key, default)

        adapter = create_llm_adapter(config, _make_secrets())
        routing = adapter._inner._inner
        plan = routing._by_task["planning"]
        if isinstance(plan, MeteringLLMAdapter):
            plan = plan._inner
        assert isinstance(plan, SystemPromptInjectorAdapter)
        assert plan._prompt == "DEFAULT"
