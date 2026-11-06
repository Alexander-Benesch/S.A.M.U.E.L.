"""Explicit LLM configuration wiring; the session lifecycle lives in the kernel."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from samuel.adapters.llm.factory import configured_llm_model, create_llm_adapter
from samuel.adapters.llm.prompts import resolve_prompt_source
from samuel.adapters.secrets.env_secrets import EnvSecretsProvider
from samuel.core.bus import Bus
from samuel.core.ports import IConfig, ILLMProvider
from samuel.core.types import LLMResponse

FILES = ("llm.json", "llm/defaults.json")


class LLMConfigView(IConfig):
    def __init__(self, base: IConfig, document: dict[str, Any]) -> None:
        self.base, self.document = base, deepcopy(document)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "llm" or key.startswith("llm."):
            value: Any = self.document
            for part in key.split(".")[1:]:
                if not isinstance(value, dict) or part not in value:
                    return default
                value = value[part]
            return value
        return self.base.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return self.base.feature_flag(name)

    def reload(self) -> None:
        pass


class LLMRuntime(ILLMProvider):
    """Stable reference shared by every consumer; swap a complete prepared graph."""

    def __init__(self, inner: ILLMProvider | None, config: IConfig, bus: Bus) -> None:
        self.inner, self.config, self.bus = inner, config, bus
        self.revision = -1
        self._lock = threading.RLock()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @property
    def context_window(self) -> int:
        if self.inner is None:
            raise RuntimeError("LLM runtime unavailable")
        return self.inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self.inner.capabilities if self.inner is not None else set()

    def estimate_tokens(self, text: str) -> int:
        if self.inner is None:
            raise RuntimeError("LLM runtime unavailable")
        return self.inner.estimate_tokens(text)

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        if self.inner is None:
            raise RuntimeError("LLM runtime unavailable")
        return self.inner.complete(messages, **kwargs)

    def prepare(self, draft: dict[str, Any]) -> ILLMProvider:
        return create_llm_adapter(
            LLMConfigView(self.config, draft["llm.json"]),
            EnvSecretsProvider(),
            bus=self.bus,
            quality_lookup=self.bus.quality_registry.score_for,
            authority_store=self.bus.authority_state_store,
            defaults_override=draft["llm/defaults.json"],
        )

    def activate(self, prepared: ILLMProvider) -> None:
        with self._lock:
            self.inner = prepared
            self.bus.llm_routing_summary = deepcopy(getattr(prepared, "routing_summary", {}))

    def refresh(self, revision: int) -> None:
        with self._lock:
            if revision != self.revision:
                root = Path(str(self.config.get("agent.config_dir", "config")))
                self.activate(self.prepare(read_documents(root)))
                self.revision = revision


def read_documents(root: Path) -> dict[str, Any]:
    documents = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("LLM configuration must not use symbolic links")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{name} must be an object")
        documents[name] = data
    return documents


class LLMConfigurationArea:
    def __init__(self, root: Path, runtime: LLMRuntime, dashboard: Any) -> None:
        self.root, self.runtime, self.dashboard = root, runtime, dashboard

    def snapshot(self) -> dict[str, Any]:
        return read_documents(self.root)

    def validate(self, draft: dict[str, Any]) -> dict[str, Any]:
        current = self.snapshot()
        if not isinstance(draft, dict) or set(draft) != set(FILES):
            raise ValueError("Only the two LLM documents may be edited")
        global_doc = draft["llm.json"]
        defaults = draft["llm/defaults.json"]
        if not isinstance(global_doc, dict) or not isinstance(defaults, dict):
            raise ValueError("LLM documents must be objects")
        # Preserve provider credentials/metadata, budgets, retry policy and every
        # non-editor field. Only the existing default provider/fallback fields move.
        expected = deepcopy(current["llm.json"])
        global_cfg = global_doc.get("default", {})
        result = self.dashboard.prepare_llm_global_config(
            {key: global_cfg.get(key) for key in ("provider", "fallbacks")}, expected
        )
        if not result.get("updated"):
            raise ValueError(result["error"])
        if expected != global_doc:
            raise ValueError("Only default provider/fallbacks may change in llm.json")
        if {k: v for k, v in defaults.items() if k != "tasks"} != {
            k: v for k, v in current["llm/defaults.json"].items() if k != "tasks"
        }:
            raise ValueError("Workflow budgets and global LLM policies are not editable here")
        tasks = defaults.get("tasks")
        if not isinstance(tasks, dict) or not tasks:
            raise ValueError("Tasks must be a non-empty object")
        if set(tasks) != set(current["llm/defaults.json"].get("tasks", {})):
            raise ValueError("Task set must remain unchanged")
        rows = []
        for task, cfg in tasks.items():
            checked = {**deepcopy(defaults), "tasks": {}}
            result = self.dashboard.prepare_llm_task_config(
                task,
                cfg,
                checked,
                os.environ.get("SAMUEL_LLM_PROVIDER") or str(global_cfg["provider"]),
            )
            if not result.get("updated"):
                raise ValueError(f"{task}: {result['error']}")
            if checked["tasks"][task] != cfg:
                raise ValueError(f"{task}: remove empty overrides before applying")
            routes = [("standard", cfg)]
            if cfg.get("schedule", {}).get("active"):
                routes.append(("schedule", cfg["schedule"]))
            for route, selected in routes:
                primary = (
                    selected.get("provider")
                    or os.environ.get("SAMUEL_LLM_PROVIDER")
                    or global_cfg["provider"]
                )
                if route == "schedule":
                    unknown = (
                        set(selected) - self.dashboard._ALLOWED_FIELDS - {"active", "from", "to"}
                    )
                    if unknown or "schedule" in selected:
                        raise ValueError("Unknown schedule fields")
                    route_cfg = {
                        k: v for k, v in selected.items() if k not in {"active", "from", "to"}
                    }
                    route_cfg.setdefault(
                        "reasoning_reserve",
                        cfg.get(
                            "reasoning_reserve",
                            defaults.get("default", {}).get("reasoning_reserve", 0),
                        ),
                    )
                    schedule_check = self.dashboard.prepare_llm_task_config(
                        task, route_cfg, {**deepcopy(defaults), "tasks": {}}, primary
                    )
                    if not schedule_check.get("updated"):
                        raise ValueError(f"{task} schedule: {schedule_check['error']}")
                providers = list(dict.fromkeys([primary, *global_cfg["fallbacks"]]))
                for index, provider in enumerate(providers):
                    model = configured_llm_model(
                        LLMConfigView(self.runtime.config, global_doc),
                        provider,
                        selected.get("model") if index == 0 else None,
                    )
                    prompt = selected.get("system_prompt", "")
                    mapping = selected.get("system_prompt_by_provider")
                    source = resolve_prompt_source(
                        prompt, str(self.root), provider=provider, model=model, by_provider=mapping
                    )
                    quality = self.dashboard._model_quality_resolver
                    thresholds = defaults.get("benchmark_thresholds", {})
                    threshold = float(thresholds.get(task, thresholds.get("default", 50.0)))
                    rows.append(
                        {
                            "task": task,
                            "route": route if index == 0 else f"{route}/fallback-{index}",
                            "provider": provider,
                            "model": model,
                            "prompt": mapping.get(provider, prompt)
                            if isinstance(mapping, dict)
                            else prompt,
                            "prompt_source": source,
                            "consumer": task != "evaluation",
                            "advisory": quality(
                                model,
                                task,
                                threshold,
                                float(cfg.get("overqualification_margin_ratio", 0.2)),
                            )
                            if quality and model
                            else {"status": "unknown"},
                            "warnings": result.get("warnings", []),
                        }
                    )
        # Bind prompt contents by digest without sending bodies to the UI/audit.
        digest = hashlib.sha256()
        for root in (self.root / "llm" / "prompts", Path(__file__).parent / "core" / "prompts"):
            for path in sorted(root.rglob("*.md")):
                if not path.is_symlink():
                    digest.update(str(path.relative_to(root)).encode())
                    digest.update(path.read_bytes())
        return {
            "binding": {
                "routes": [
                    {k: v for k, v in row.items() if k not in {"advisory", "warnings"}}
                    for row in rows
                ],
                "prompt_digest": digest.hexdigest(),
                "environment_override": os.environ.get("SAMUEL_LLM_PROVIDER") or None,
                "fallbacks": global_cfg["fallbacks"],
            },
            "routes": rows,
            "prompt_digest": digest.hexdigest(),
            "fallbacks": global_cfg["fallbacks"],
            "environment_override": os.environ.get("SAMUEL_LLM_PROVIDER") or None,
            "connection_test": "optional; provider.validate only",
            "benchmarks": "advisory; no activation gate",
            "benchmark_source": self.dashboard._model_cache_status_resolver()
            if self.dashboard._model_cache_status_resolver
            else {"status": "unknown"},
        }

    def prepare(self, draft: dict[str, Any]) -> ILLMProvider:
        return self.runtime.prepare(draft)

    def persist(self, draft: dict[str, Any]) -> None:
        # The durable session journal fences ALL readers that can start work.
        # In-place writes support narrowly writable Docker file bind mounts.
        # A crash at any byte leaves the mode blocked until explicit restoration.
        for name in FILES:
            path = self.root / name
            if path.parent.is_symlink():
                raise ValueError("Unsafe LLM configuration directory")
            descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("LLM configuration must be a regular file")
                stream.write(json.dumps(draft[name], ensure_ascii=False, indent=2) + "\n")
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
        if self.snapshot() != draft:
            raise OSError("LLM configuration readback mismatch")

    def activate(self, prepared: ILLMProvider) -> None:
        self.runtime.activate(prepared)
        self.dashboard.configuration_activated(
            LLMConfigView(self.runtime.config, self.snapshot()["llm.json"])
        )
