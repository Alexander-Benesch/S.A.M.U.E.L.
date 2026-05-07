from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from samuel.adapters.llm.circuit_breaker import CircuitBreakerAdapter
from samuel.adapters.llm.claude import ClaudeAdapter
from samuel.adapters.llm.costs import configure_cache_ttl
from samuel.adapters.llm.deepseek import DeepSeekAdapter
from samuel.adapters.llm.gemini import GeminiAdapter
from samuel.adapters.llm.lmstudio import LMStudioAdapter
from samuel.adapters.llm.manual import ManualAdapter
from samuel.adapters.llm.metering import MeteringLLMAdapter
from samuel.adapters.llm.ollama import OllamaAdapter
from samuel.adapters.llm.openai import OpenAIAdapter
from samuel.adapters.llm.openrouter import OpenRouterAdapter
from samuel.adapters.llm.prompts import load_system_prompt
from samuel.adapters.llm.sanitizer import SanitizingLLMAdapter
from samuel.adapters.llm.system_prompt import SystemPromptInjectorAdapter
from samuel.adapters.llm.task_routing import TaskRoutingLLMAdapter
from samuel.core.ports import IConfig, ILLMProvider, ISecretsProvider

log = logging.getLogger(__name__)


def _load_llm_defaults(config_dir: str | Path = "config") -> dict:
    """Load LLM defaults from config/llm/defaults.json."""
    path = Path(config_dir) / "llm" / "defaults.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to load LLM defaults from %s: %s", path, exc)
    return {}


def _build_inner(
    provider_name: str,
    config: IConfig,
    secrets: ISecretsProvider,
    *,
    model_override: str | None = None,
    base_url_override: str | None = None,
    timeout_override: int | None = None,
) -> ILLMProvider:
    """Build the raw inner adapter for ``provider_name`` with optional overrides.

    #301: ``base_url_override`` and ``timeout_override`` allow per-task config
    to override the global defaults — needed for v1-Parität (e.g. local LMStudio
    on a specific port, or tighter timeout for review tasks).
    """
    cfg_model = f"llm.{provider_name}.model"
    if provider_name == "claude":
        # Claude uses fixed api.anthropic.com; base_url-override ignored.
        return ClaudeAdapter(
            api_key=secrets.get("ANTHROPIC_API_KEY"),
            model=model_override or config.get(cfg_model, "claude-sonnet-4-6"),
        )
    if provider_name == "deepseek":
        adapter = DeepSeekAdapter(
            api_key=secrets.get("DEEPSEEK_API_KEY"),
            model=model_override or config.get(cfg_model, "deepseek-chat"),
            timeout=timeout_override or 120,
        )
        if base_url_override:
            adapter._base_url = base_url_override.rstrip("/")
        return adapter
    if provider_name == "ollama":
        return OllamaAdapter(
            model=model_override or config.get(cfg_model, "llama3"),
            base_url=base_url_override or config.get("llm.ollama.url", "http://localhost:11434"),
        )
    if provider_name == "lmstudio":
        return LMStudioAdapter(
            model=model_override or config.get(cfg_model, "local-model"),
            base_url=base_url_override or config.get("llm.lmstudio.url", "http://localhost:1234/v1"),
            timeout=timeout_override or 120,
        )
    if provider_name == "gemini":
        return GeminiAdapter(
            api_key=secrets.get("GEMINI_API_KEY"),
            model=model_override or config.get(cfg_model, "gemini-2.0-flash"),
            timeout=timeout_override or 60,
        )
    if provider_name == "openai":
        return OpenAIAdapter(
            api_key=secrets.get("OPENAI_API_KEY"),
            model=model_override or config.get(cfg_model, "gpt-4o-mini"),
            timeout=timeout_override or 120,
        )
    if provider_name == "openrouter":
        # #318: OpenRouter-Gateway — vendor/model als ``model`` (z.B. "anthropic/claude-sonnet-4-6").
        return OpenRouterAdapter(
            api_key=secrets.get("OPENROUTER_API_KEY"),
            model=model_override or config.get(cfg_model, "anthropic/claude-sonnet-4-6"),
            timeout=timeout_override or 60,
        )
    if provider_name == "manual":
        return ManualAdapter(
            data_dir=config.get("llm.manual.data_dir", "data/manual_llm"),
            poll_interval=float(config.get("llm.manual.poll_interval", 1.0)),
            timeout_seconds=float(timeout_override or config.get("llm.manual.timeout", 3600)),
            context_window_size=int(config.get("llm.manual.context_window", 200_000)),
        )
    raise ValueError(
        f"Unknown LLM provider '{provider_name}'. "
        "Available: claude, deepseek, gemini, openai, openrouter, ollama, lmstudio, manual"
    )


def _wrap_metered(
    inner: ILLMProvider, bus: Any | None, provider_name: str,
) -> ILLMProvider:
    return (
        MeteringLLMAdapter(inner, bus=bus, provider_name=provider_name)
        if bus else inner
    )


def _wrap_system_prompt(
    inner: ILLMProvider,
    *,
    system_prompt_name: str | None,
    config_dir: str,
    provider: str | None,
    model: str | None,
    by_provider: dict | None = None,
) -> ILLMProvider:
    """#338 Schicht B Wiring: resolve the task's ``system_prompt`` config
    via the 4-stage cascade (model > provider > generic > package) and
    wrap the inner adapter so the prompt is auto-prepended at runtime.

    Returns ``inner`` unchanged when no prompt is configured or the
    cascade resolves to empty (e.g. typo'd filename) — keeps the wrap
    side-effect-free in the legacy code path.

    ``by_provider`` (#351 Hybrid): per-provider override map from the task
    config. ``load_system_prompt`` consults it first; when an entry exists
    for the active provider, that filename is used instead of the task's
    default ``system_prompt``.
    """
    # We may still need to wrap even when system_prompt_name is empty —
    # if the by_provider map has an entry for this provider, that entry
    # is the effective prompt.
    has_by_prov_entry = (
        isinstance(by_provider, dict)
        and provider
        and isinstance(by_provider.get(provider), str)
        and by_provider[provider].strip()
    )
    if not system_prompt_name and not has_by_prov_entry:
        return inner
    prompt_text = load_system_prompt(
        system_prompt_name, config_dir,
        provider=provider, model=model,
        by_provider=by_provider,
    )
    if not prompt_text.strip():
        log.warning(
            "system_prompt %r resolved to empty (provider=%s, model=%s, "
            "by_provider=%s) — wrapper skipped, leaf adapter sees raw messages",
            system_prompt_name, provider, model, by_provider,
        )
        return inner
    return SystemPromptInjectorAdapter(inner, system_prompt=prompt_text)


def create_llm_adapter(
    config: IConfig,
    secrets: ISecretsProvider,
    bus: Any | None = None,
) -> ILLMProvider:
    provider = os.environ.get("SAMUEL_LLM_PROVIDER") or config.get(
        "llm.default.provider", "ollama"
    )
    config_dir = config.get("agent.config_dir", "config")
    llm_defaults = _load_llm_defaults(config_dir)

    pricing_cache_hours = llm_defaults.get("pricing_cache_hours")
    if pricing_cache_hours is not None:
        configure_cache_ttl(int(pricing_cache_hours))

    default_params = llm_defaults.get("default", {})
    max_tokens = default_params.get("max_tokens", 4096)
    temperature = default_params.get("temperature", 0.2)

    cb_config = llm_defaults.get("circuit_breaker", {})
    failure_threshold = cb_config.get("failure_threshold")
    cooldown_seconds = cb_config.get("cooldown_seconds")

    # Default chain (always built): provider lookup + metering
    default_inner = _build_inner(provider, config, secrets)
    metered: ILLMProvider = _wrap_metered(default_inner, bus, provider)

    # #301: TaskRoutingLLMAdapter — gate-Lockerung. Static per-task routing
    # ist FREE (kein License-Check). Premium kommt erst bei time-window
    # schedule-blocks (siehe #302, future feature ``llm_routing_advanced``).
    # #338-audit: a task that only sets `system_prompt` (no provider override)
    # must still get the SystemPromptInjector wrapper — otherwise the
    # configured prompt is silently dropped at runtime. Build a per-task
    # adapter from the default provider in that case.
    tasks_cfg = llm_defaults.get("tasks") or {}
    # #351: task is routing-relevant if it has a provider override, a
    # system_prompt, or a system_prompt_by_provider map (any of which
    # needs the per-task wrapper).
    has_task_routing_relevant = any(
        isinstance(t, dict) and (
            t.get("provider")
            or t.get("system_prompt")
            or t.get("system_prompt_by_provider")
        )
        for t in tasks_cfg.values()
    )

    if has_task_routing_relevant:
        by_task: dict[str, ILLMProvider] = {}
        for task_name, task_cfg in tasks_cfg.items():
            if not isinstance(task_cfg, dict):
                continue
            t_provider = task_cfg.get("provider")
            t_model = task_cfg.get("model")
            t_system_prompt = task_cfg.get("system_prompt")
            t_by_provider = task_cfg.get("system_prompt_by_provider")
            if not t_provider and not t_system_prompt and not t_by_provider:
                continue

            # When only `system_prompt` / `system_prompt_by_provider` is set
            # (no provider override) we still need an adapter for this task
            # so the wrapper can wrap something — clone the default
            # provider's chain.
            effective_provider = t_provider or provider
            effective_model = t_model or config.get(
                f"llm.{effective_provider}.model", None,
            )
            try:
                t_inner = _build_inner(
                    effective_provider, config, secrets,
                    model_override=t_model,
                    base_url_override=task_cfg.get("base_url"),
                    timeout_override=task_cfg.get("timeout"),
                )
            except ValueError as exc:
                log.warning("TaskRouting: skipping task=%s (%s)", task_name, exc)
                continue
            t_inner = _wrap_system_prompt(
                t_inner,
                system_prompt_name=t_system_prompt,
                config_dir=str(config_dir),
                provider=effective_provider,
                model=effective_model,
                by_provider=t_by_provider,
            )
            by_task[task_name] = _wrap_metered(t_inner, bus, effective_provider)

        if by_task:
            log.info("LLM-TaskRouting: aktiv (%d Tasks gemappt)", len(by_task))
            metered = TaskRoutingLLMAdapter(default=metered, by_task=by_task)
        else:
            log.info("LLM-TaskRouting: skipped (no valid task overrides)")

    # #302: Time-Window Schedule (Premium llm_routing_advanced)
    schedules = {
        name: cfg["schedule"]
        for name, cfg in tasks_cfg.items()
        if isinstance(cfg, dict) and isinstance(cfg.get("schedule"), dict)
    }

    if schedules:
        from samuel.core import license as _lic
        if _lic.is_premium_active() and _lic.has_feature("llm_routing_advanced"):
            from samuel.adapters.llm.scheduled_routing import ScheduledTaskRoutingAdapter
            by_task_night: dict[str, ILLMProvider] = {}
            for task_name, sched in schedules.items():
                t_provider = sched.get("provider")
                if not t_provider:
                    continue
                try:
                    n_inner = _build_inner(
                        t_provider, config, secrets,
                        model_override=sched.get("model"),
                        base_url_override=sched.get("base_url"),
                        timeout_override=sched.get("timeout"),
                    )
                except ValueError as exc:
                    log.warning("Schedule: skipping task=%s (%s)", task_name, exc)
                    continue
                n_inner = _wrap_system_prompt(
                    n_inner,
                    system_prompt_name=sched.get("system_prompt"),
                    config_dir=str(config_dir),
                    provider=t_provider,
                    model=sched.get("model"),
                    by_provider=sched.get("system_prompt_by_provider"),
                )
                by_task_night[task_name] = _wrap_metered(n_inner, bus, t_provider)

            if by_task_night:
                # Wrap whatever metered is now (TaskRouting or default) into Scheduled
                if isinstance(metered, TaskRoutingLLMAdapter):
                    day_routes = metered._by_task
                    schedule_default = metered._default
                else:
                    day_routes = {}
                    schedule_default = metered
                log.info("LLM-Schedule: aktiv (%d tasks)", len(by_task_night))
                metered = ScheduledTaskRoutingAdapter(
                    default=schedule_default,
                    by_task_day=day_routes,
                    by_task_night=by_task_night,
                    schedules=schedules,
                )
        else:
            log.info("LLM-Schedule: skipped (no premium / llm_routing_advanced feature missing)")

    pii_config = None
    try:
        privacy_path = Path(config_dir) / "privacy.json"
        if privacy_path.exists():
            privacy_data = json.loads(privacy_path.read_text(encoding="utf-8"))
            pii_config = privacy_data.get("pii_scrubbing")
    except Exception as e:
        log.warning("Failed to load PII scrubbing config: %s", e)

    adapter = CircuitBreakerAdapter(
        SanitizingLLMAdapter(metered, pii_config=pii_config),
        failure_threshold=failure_threshold,
        cooldown_seconds=cooldown_seconds,
    )

    adapter.default_max_tokens = max_tokens  # type: ignore[attr-defined]
    adapter.default_temperature = temperature  # type: ignore[attr-defined]

    return adapter
