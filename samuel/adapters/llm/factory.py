from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from samuel.adapters.llm.circuit_breaker import CircuitBreakerAdapter
from samuel.adapters.llm.claude import ClaudeAdapter
from samuel.adapters.llm.costs import configure_cache_ttl, configure_catalog_endpoints
from samuel.adapters.llm.deepseek import DeepSeekAdapter
from samuel.adapters.llm.fallback import FallbackLLMAdapter
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
from samuel.adapters.llm.token_budget import TokenBudgetLLMAdapter
from samuel.adapters.llm.workflow_budget import (
    LogicalCallLLMAdapter,
    WorkflowTokenBudgetLLMAdapter,
)
from samuel.core.ports import IAuthorityStateStore, IConfig, ILLMProvider, ISecretsProvider

log = logging.getLogger(__name__)

_PROVIDER_SECRET_KEYS: dict[str, str] = {
    "claude": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
_LOCAL_OR_MANUAL_PROVIDERS = frozenset({"ollama", "lmstudio", "manual"})


def _load_llm_defaults(config_dir: str | Path = "config") -> dict:
    """Load LLM defaults from config/llm/defaults.json."""
    path = Path(config_dir) / "llm" / "defaults.json"
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception as exc:
            log.warning("Failed to load LLM defaults from %s: %s", path, exc)
    return {}


def _provider_readiness(
    provider: str,
    model: str,
    config: IConfig,
    secrets: ISecretsProvider,
) -> dict[str, Any]:
    """Describe one configured provider without exposing or probing secrets."""

    secret_key = _PROVIDER_SECRET_KEYS.get(provider)
    credential_configured = bool(secrets.get(secret_key)) if secret_key else None
    model_configured = bool(model.strip())
    row: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "credential": (
            "configured"
            if credential_configured is True
            else "missing"
            if credential_configured is False
            else "not_required"
        ),
        "model_status": "configured_unverified" if model_configured else "missing",
        "reachability": "not_checked",
    }
    if secret_key:
        row["required_env"] = secret_key
    elif provider not in _LOCAL_OR_MANUAL_PROVIDERS:
        row.update(
            {
                "passed": False,
                "status": "unsupported_provider",
                "guidance": f"Provider {provider!r} in der LLM-Konfiguration korrigieren.",
            }
        )
        return row

    if not model_configured:
        row.update(
            {
                "passed": False,
                "status": "model_missing",
                "guidance": f"Eine Modell-ID für Provider {provider} konfigurieren.",
            }
        )
        return row
    if credential_configured is False:
        row.update(
            {
                "passed": False,
                "status": "credential_missing",
                "guidance": f"{secret_key} im Samuel-Prozess setzen und Health wiederholen.",
            }
        )
        return row

    if provider == "openrouter":
        from samuel.adapters.llm.costs import get_openrouter_model_status

        catalog = get_openrouter_model_status(model)
        row["catalog"] = catalog
        row["model_status"] = catalog["status"]
        if catalog["available"] is False:
            row.update(
                {
                    "passed": False,
                    "status": "model_unavailable",
                    "guidance": (
                        "Die effektive OpenRouter-Modell-ID gegen den frisch aktualisierten "
                        "Katalog prüfen; es wird kein Ersatzmodell gewählt."
                    ),
                }
            )
            return row
        if catalog["available"] is None:
            row["status"] = "configured_availability_unknown"
            row["guidance"] = (
                "OpenRouter-Modellkatalog aktualisieren; bis dahin ist die "
                "Providerverfügbarkeit unbekannt, nicht als live geprüft."
            )

    row.setdefault("status", "configured")
    row["passed"] = True
    return row


def _build_llm_readiness(
    *,
    config: IConfig,
    secrets: ISecretsProvider,
    default_provider: str,
    fallback_names: list[str],
    tasks_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Bind readiness to the task routes that the factory actually builds."""

    raw_routes: list[tuple[str, str, str]] = []
    if tasks_cfg:
        from samuel.core.schedule import schedule_active

        for task_name, raw_task in tasks_cfg.items():
            if not isinstance(raw_task, dict):
                continue
            effective = raw_task
            schedule = raw_task.get("schedule")
            if isinstance(schedule, dict) and schedule_active(schedule):
                effective = {**raw_task, **schedule}
            provider = str(effective.get("provider") or default_provider).strip()
            model = str(
                effective.get("model") or config.get(f"llm.{provider}.model", "") or ""
            ).strip()
            raw_routes.append((str(task_name), provider, model))
    else:
        model = str(config.get(f"llm.{default_provider}.model", "") or "").strip()
        raw_routes.append(("default", default_provider, model))

    routes: list[dict[str, Any]] = []
    for task, primary, model in raw_routes:
        candidates: list[dict[str, Any]] = []
        for index, provider in enumerate(
            dict.fromkeys([primary, *(name for name in fallback_names if name != primary)])
        ):
            candidate_model = (
                model if index == 0 else str(config.get(f"llm.{provider}.model", "") or "").strip()
            )
            candidate = _provider_readiness(provider, candidate_model, config, secrets)
            candidate["role"] = "primary" if index == 0 else "fallback"
            candidates.append(candidate)
        selected = next((item for item in candidates if item["passed"]), None)
        routes.append(
            {
                "task": task,
                "provider": primary,
                "model": model,
                "passed": selected is not None,
                "status": (
                    "ready"
                    if selected is not None and selected["role"] == "primary"
                    else "ready_via_configured_fallback"
                    if selected is not None
                    else "unavailable"
                ),
                "selected_provider": selected["provider"] if selected else None,
                "candidates": candidates,
            }
        )

    failed_routes = [route["task"] for route in routes if not route["passed"]]
    return {
        "passed": not failed_routes,
        "status": "ready" if not failed_routes else "configuration_missing",
        "routes": routes,
        "failed_routes": failed_routes,
        "fallbacks": fallback_names,
        "live_probe": "not_performed",
    }


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
            timeout=timeout_override or 120,
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
            timeout=timeout_override or 120,
        )
    if provider_name == "lmstudio":
        return LMStudioAdapter(
            model=model_override or config.get(cfg_model, "local-model"),
            base_url=base_url_override
            or config.get("llm.lmstudio.url", "http://localhost:1234/v1"),
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
    inner: ILLMProvider,
    bus: Any | None,
    provider_name: str,
    quality_lookup: Any = None,
    *,
    model_name: str = "",
) -> ILLMProvider:
    return (
        MeteringLLMAdapter(
            inner,
            bus=bus,
            provider_name=provider_name,
            quality_lookup=quality_lookup,
            model_name=model_name,
        )
        if bus
        else inner
    )


def _wrap_retry(inner: ILLMProvider, llm_defaults: dict) -> ILLMProvider:
    """#337: Wrap mit RetryLLMAdapter, falls in defaults.json aktiviert
    (``retry.enabled``). Bei deaktiviert/fehlend: inner unveraendert."""
    cfg = llm_defaults.get("retry") or {}
    if not cfg.get("enabled", False):
        return inner
    from samuel.adapters.llm.retry import (
        DEFAULT_BASE_DELAY_S,
        DEFAULT_MAX_ATTEMPTS,
        RetryLLMAdapter,
    )

    attempts = cfg.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    base_delay = cfg.get("base_delay_s", DEFAULT_BASE_DELAY_S)
    log.info("LLM-Retry: aktiv (max_attempts=%s, base_delay_s=%s)", attempts, base_delay)
    return RetryLLMAdapter(inner, max_attempts=attempts, base_delay_s=base_delay)


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
        system_prompt_name,
        config_dir,
        provider=provider,
        model=model,
        by_provider=by_provider,
    )
    if not prompt_text.strip():
        log.warning(
            "system_prompt %r resolved to empty (provider=%s, model=%s, "
            "by_provider=%s) — wrapper skipped, leaf adapter sees raw messages",
            system_prompt_name,
            provider,
            model,
            by_provider,
        )
        return inner
    return SystemPromptInjectorAdapter(inner, system_prompt=prompt_text)


def create_llm_adapter(
    config: IConfig,
    secrets: ISecretsProvider,
    bus: Any | None = None,
    quality_lookup: Any = None,
    authority_store: IAuthorityStateStore | None = None,
) -> ILLMProvider:
    provider = os.environ.get("SAMUEL_LLM_PROVIDER") or config.get("llm.default.provider", "ollama")
    config_dir = config.get("agent.config_dir", "config")
    llm_defaults = _load_llm_defaults(config_dir)

    configure_catalog_endpoints(config)
    pricing_cache_hours = llm_defaults.get("pricing_cache_hours")
    if pricing_cache_hours is not None:
        configure_cache_ttl(int(pricing_cache_hours))

    default_params = llm_defaults.get("default", {})
    max_tokens = default_params.get("max_tokens", 4096)
    temperature = default_params.get("temperature", 0.2)
    workflow_budget_config = llm_defaults.get("workflow_budget") or {}
    if not isinstance(workflow_budget_config, dict):
        raise ValueError("workflow_budget must be an object")
    workflow_token_limit = workflow_budget_config.get("token_limit", 500_000)
    if (
        isinstance(workflow_token_limit, bool)
        or not isinstance(workflow_token_limit, int)
        or workflow_token_limit <= 0
    ):
        raise ValueError("workflow_budget.token_limit must be a positive integer")

    cb_config = llm_defaults.get("circuit_breaker", {})
    failure_threshold = cb_config.get("failure_threshold")
    cooldown_seconds = cb_config.get("cooldown_seconds")

    raw_fallbacks = config.get("llm.default.fallbacks", [])
    fallback_names = (
        [str(name).strip() for name in raw_fallbacks if str(name).strip()]
        if isinstance(raw_fallbacks, list)
        else []
    )
    metered_adapters: list[MeteringLLMAdapter] = []

    def _build_provider_chain(
        primary: str,
        *,
        model_override: str | None = None,
        base_url_override: str | None = None,
        timeout_override: int | None = None,
        system_prompt_name: str | None = None,
        by_provider: dict | None = None,
        content_max_tokens: int | None = None,
        task_temperature: float | None = None,
        reasoning_reserve: int = 0,
    ) -> ILLMProvider:
        providers: list[tuple[str, ILLMProvider]] = []
        ordered_names = [primary, *(name for name in fallback_names if name != primary)]
        for index, provider_name in enumerate(dict.fromkeys(ordered_names)):
            try:
                inner = _build_inner(
                    provider_name,
                    config,
                    secrets,
                    model_override=model_override if index == 0 else None,
                    base_url_override=base_url_override if index == 0 else None,
                    timeout_override=timeout_override,
                )
            except ValueError:
                if index == 0:
                    raise
                log.warning("LLM fallback provider %s is unknown and was skipped", provider_name)
                continue
            effective_model = (
                model_override
                if index == 0 and model_override
                else getattr(inner, "_model", None)
                or config.get(f"llm.{provider_name}.model", None)
            )
            if authority_store is not None:
                inner = WorkflowTokenBudgetLLMAdapter(
                    inner,
                    authority_store=authority_store,
                    provider=provider_name,
                    model=str(effective_model or ""),
                    bus=bus,
                )
            inner = _wrap_system_prompt(
                inner,
                system_prompt_name=system_prompt_name,
                config_dir=str(config_dir),
                provider=provider_name,
                model=effective_model,
                by_provider=by_provider,
            )
            inner = _wrap_metered(
                inner, bus, provider_name, quality_lookup, model_name=str(effective_model or "")
            )
            if isinstance(inner, MeteringLLMAdapter):
                metered_adapters.append(inner)
            providers.append(
                (
                    provider_name,
                    TokenBudgetLLMAdapter(
                        inner,
                        provider=provider_name,
                        model=effective_model,
                        content_max_tokens=content_max_tokens,
                        temperature=task_temperature,
                        reasoning_reserve=reasoning_reserve,
                    ),
                )
            )
        if len(providers) == 1:
            return providers[0][1]
        return FallbackLLMAdapter(
            providers,
            on_fallback=bus.publish if bus is not None else None,
        )

    # Default chain (always built): provider lookup + metering + optional
    # ordered provider failover from config/llm.json::default.fallbacks.
    metered: ILLMProvider = _build_provider_chain(
        provider,
        content_max_tokens=max_tokens,
        task_temperature=temperature,
        reasoning_reserve=int(default_params.get("reasoning_reserve", 0) or 0),
    )

    # #301: TaskRoutingLLMAdapter — static per-task routing is general config.
    # #338-audit: a task that only sets `system_prompt` (no provider override)
    # must still get the SystemPromptInjector wrapper — otherwise the
    # configured prompt is silently dropped at runtime. Build a per-task
    # adapter from the default provider in that case.
    tasks_cfg = llm_defaults.get("tasks") or {}
    # #351: task is routing-relevant if it has a provider override, a
    # system_prompt, or a system_prompt_by_provider map (any of which
    # needs the per-task wrapper).
    runtime_fields = {
        "provider",
        "model",
        "base_url",
        "timeout",
        "system_prompt",
        "system_prompt_by_provider",
        "max_tokens",
        "temperature",
        "reasoning_reserve",
    }
    has_task_routing_relevant = any(
        isinstance(t, dict) and any(field in t for field in runtime_fields)
        for t in tasks_cfg.values()
    )

    if has_task_routing_relevant:
        by_task: dict[str, ILLMProvider] = {}
        task_routing_summary: dict[str, str] = {}
        for task_name, task_cfg in tasks_cfg.items():
            if not isinstance(task_cfg, dict):
                continue
            t_provider = task_cfg.get("provider")
            t_model = task_cfg.get("model")
            t_system_prompt = task_cfg.get("system_prompt")
            t_by_provider = task_cfg.get("system_prompt_by_provider")
            if not any(field in task_cfg for field in runtime_fields):
                continue

            # When only `system_prompt` / `system_prompt_by_provider` is set
            # (no provider override) we still need an adapter for this task
            # so the wrapper can wrap something — clone the default
            # provider's chain.
            effective_provider = t_provider or provider
            try:
                t_inner = _build_provider_chain(
                    effective_provider,
                    model_override=t_model,
                    base_url_override=task_cfg.get("base_url"),
                    timeout_override=task_cfg.get("timeout"),
                    system_prompt_name=t_system_prompt,
                    by_provider=t_by_provider,
                    content_max_tokens=task_cfg.get("max_tokens", max_tokens),
                    task_temperature=task_cfg.get("temperature", temperature),
                    reasoning_reserve=int(
                        task_cfg.get(
                            "reasoning_reserve",
                            default_params.get("reasoning_reserve", 0),
                        )
                        or 0
                    ),
                )
            except ValueError as exc:
                log.warning("TaskRouting: skipping task=%s (%s)", task_name, exc)
                continue
            by_task[task_name] = t_inner
            task_routing_summary[task_name] = effective_provider

        if by_task:
            log.info("LLM-TaskRouting: aktiv (%d Tasks gemappt)", len(by_task))
            metered = TaskRoutingLLMAdapter(default=metered, by_task=by_task)
        else:
            log.info("LLM-TaskRouting: skipped (no valid task overrides)")

    # #302: Time-window schedule through the same general routing path.
    schedules = {
        name: cfg["schedule"]
        for name, cfg in tasks_cfg.items()
        if isinstance(cfg, dict) and isinstance(cfg.get("schedule"), dict)
    }

    if schedules:
        from samuel.adapters.llm.scheduled_routing import ScheduledTaskRoutingAdapter

        by_task_night: dict[str, ILLMProvider] = {}
        for task_name, sched in schedules.items():
            t_provider = sched.get("provider")
            if not t_provider:
                continue
            try:
                n_inner = _build_provider_chain(
                    t_provider,
                    model_override=sched.get("model"),
                    base_url_override=sched.get("base_url"),
                    timeout_override=sched.get("timeout"),
                    system_prompt_name=sched.get("system_prompt"),
                    by_provider=sched.get("system_prompt_by_provider"),
                    content_max_tokens=sched.get(
                        "max_tokens",
                        tasks_cfg.get(task_name, {}).get("max_tokens", max_tokens),
                    ),
                    task_temperature=sched.get(
                        "temperature",
                        tasks_cfg.get(task_name, {}).get("temperature", temperature),
                    ),
                    reasoning_reserve=int(
                        sched.get(
                            "reasoning_reserve",
                            tasks_cfg.get(task_name, {}).get(
                                "reasoning_reserve",
                                default_params.get("reasoning_reserve", 0),
                            ),
                        )
                        or 0
                    ),
                )
            except ValueError as exc:
                log.warning("Schedule: skipping task=%s (%s)", task_name, exc)
                continue
            by_task_night[task_name] = n_inner

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

    pii_config = None
    try:
        privacy_path = Path(config_dir) / "privacy.json"
        if privacy_path.exists():
            privacy_data = json.loads(privacy_path.read_text(encoding="utf-8"))
            pii_config = privacy_data.get("pii_scrubbing")
    except Exception as e:
        log.warning("Failed to load PII scrubbing config: %s", e)

    # #337: Retry mit Exponential-Backoff zwischen Metering und Sanitizer.
    # Liegt UNTER dem CircuitBreaker, damit eine ganze Retry-Sequenz dort als
    # ein Versuch zaehlt (CB oeffnet nicht schon nach dem ersten Rate-Limit).
    retried = _wrap_retry(metered, llm_defaults)
    if authority_store is not None:
        retried = LogicalCallLLMAdapter(retried)

    adapter = CircuitBreakerAdapter(
        SanitizingLLMAdapter(retried, pii_config=pii_config),
        failure_threshold=failure_threshold,
        cooldown_seconds=cooldown_seconds,
    )

    adapter.default_max_tokens = max_tokens  # type: ignore[attr-defined]
    adapter.default_temperature = temperature  # type: ignore[attr-defined]
    adapter.routing_summary = {  # type: ignore[attr-defined]
        "default": provider,
        "fallbacks": fallback_names,
        "tasks": task_routing_summary if has_task_routing_relevant else {},
    }
    adapter.workflow_budget_policy = {  # type: ignore[attr-defined]
        "schema": "workflow-token-budget.v1",
        "token_limit": workflow_token_limit,
        "input_bound": "utf8-bytes-plus-message-framing.v1",
        "output_bound": "provider-enforced-max-tokens",
        "money_authority": False,
    }

    def _call_activity_status() -> dict[str, Any]:
        snapshots = [item.call_activity_status() for item in tuple(metered_adapters)]
        calls = [call for snapshot in snapshots for call in snapshot["calls"]]
        finished = [snapshot["last_call"] for snapshot in snapshots if snapshot["last_call"]]
        return {
            "status": "running" if calls else "idle" if snapshots else "unknown",
            "calls": sorted(calls, key=lambda call: (call["started_at"], call["call_id"])),
            "last_call": max(finished, key=lambda call: call["finished_at"]) if finished else None,
            "source": "runtime_metering",
        }

    adapter.call_activity_status = _call_activity_status  # type: ignore[attr-defined]

    def _readiness_status() -> dict[str, Any]:
        return _build_llm_readiness(
            config=config,
            secrets=secrets,
            default_provider=provider,
            fallback_names=fallback_names,
            tasks_cfg=tasks_cfg if isinstance(tasks_cfg, dict) else {},
        )

    # Keep the materialized value for compatibility with adapter consumers,
    # but let Health re-evaluate provider-owned catalogue evidence on every
    # check.  A catalogue refresh must not require an agent restart before it
    # can change readiness from unknown to available (or unavailable).
    adapter.readiness_status = _readiness_status()  # type: ignore[attr-defined]
    adapter.readiness_status_resolver = _readiness_status  # type: ignore[attr-defined]

    return adapter
