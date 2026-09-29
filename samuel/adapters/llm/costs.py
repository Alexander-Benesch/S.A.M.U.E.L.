from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_OPENROUTER_BENCHMARKS_URL = "https://openrouter.ai/api/v1/benchmarks"
_CACHE_MAX_AGE = 86400  # default: 24 hours
_CACHE_SCHEMA_VERSION = 3


def configure_cache_ttl(hours: int) -> None:
    """Set the pricing cache TTL from config (in hours)."""
    global _CACHE_MAX_AGE
    _CACHE_MAX_AGE = hours * 3600


_or_cache: dict[str, dict] | None = None
_or_cache_ts: float = 0.0
_or_cache_schema: int = 0


def _default_cache_path() -> Path:
    return Path("data/openrouter_models.json")


def _load_or_cache(cache_path: Path | None = None) -> dict[str, dict]:
    global _or_cache, _or_cache_schema, _or_cache_ts
    if _or_cache is not None and (time.time() - _or_cache_ts) < _CACHE_MAX_AGE:
        return _or_cache
    cp = cache_path or _default_cache_path()
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            _or_cache = data.get("models", {})
            _or_cache_ts = data.get("fetched_at", 0)
            _or_cache_schema = int(data.get("schema_version", 1) or 1)
            if (time.time() - _or_cache_ts) < _CACHE_MAX_AGE:
                return _or_cache
        except Exception as e:
            log.debug("Failed to load OpenRouter cache: %s", e)
    return _or_cache or {}


def refresh_pricing(cache_path: Path | None = None, api_key: str | None = None) -> dict:
    """Refresh the shared OpenRouter model, pricing, reasoning and benchmark cache.

    The models endpoint is public.  The benchmarks endpoint requires an API
    key; absence or failure leaves benchmark data explicitly unavailable while
    preserving a successful model/pricing refresh.
    """

    global _or_cache, _or_cache_schema, _or_cache_ts
    try:
        req = urllib.request.Request(_OPENROUTER_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
        models_list = raw.get("data", [])
        models_dict: dict[str, dict] = {}
        for m in models_list:
            mid = m.get("id", "")
            raw_pricing = m.get("pricing", {})
            pricing = raw_pricing if isinstance(raw_pricing, dict) else {}
            additional_pricing: dict[str, float | str] = {}
            for name, raw_value in pricing.items():
                if name in {"prompt", "completion"}:
                    continue
                try:
                    numeric_value = float(raw_value or 0)
                except (TypeError, ValueError):
                    additional_pricing[str(name)] = "unreadable"
                else:
                    if numeric_value != 0:
                        additional_pricing[str(name)] = numeric_value
            models_dict[mid] = {
                "name": m.get("name", mid),
                "prompt": float(pricing.get("prompt", 0) or 0),
                "completion": float(pricing.get("completion", 0) or 0),
                "additional_pricing": additional_pricing,
                "context_length": m.get("context_length", 0),
                "canonical_slug": m.get("canonical_slug", ""),
                "max_completion_tokens": m.get("top_provider", {}).get("max_completion_tokens", 0),
                "reasoning": m.get("reasoning") if isinstance(m.get("reasoning"), dict) else {},
                "supported_parameters": (
                    m.get("supported_parameters")
                    if isinstance(m.get("supported_parameters"), list)
                    else []
                ),
                "default_parameters": (
                    m.get("default_parameters")
                    if isinstance(m.get("default_parameters"), dict)
                    else {}
                ),
            }

        benchmark_models: set[str] = set()
        benchmark_error: str | None = "OPENROUTER_API_KEY not configured"
        effective_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if effective_key:
            try:
                breq = urllib.request.Request(
                    _OPENROUTER_BENCHMARKS_URL,
                    headers={"Authorization": f"Bearer {effective_key}"},
                )
                with urllib.request.urlopen(breq, timeout=10) as resp:
                    benchmark_raw = json.loads(resp.read())
                model_aliases = {
                    alias: mid
                    for mid, info in models_dict.items()
                    for alias in (mid, str(info.get("canonical_slug", "")))
                    if alias
                }
                for row in benchmark_raw.get("data", []):
                    permaslug = str(row.get("model_permaslug", ""))
                    model_id = model_aliases.get(permaslug, "")
                    if not model_id:
                        continue
                    values = {
                        name: row.get(name)
                        for name in ("intelligence_index", "coding_index", "agentic_index")
                        if isinstance(row.get(name), (int, float))
                    }
                    if not values:
                        continue
                    models_dict[model_id].setdefault("benchmarks", {}).update(values)
                    models_dict[model_id].setdefault("benchmark_sources", []).append(
                        row.get("source", "openrouter")
                    )
                    benchmark_models.add(model_id)
                benchmark_error = None
            except Exception as exc:
                benchmark_error = str(exc)
                log.warning("OpenRouter benchmark fetch failed: %s", exc)
        now = time.time()
        benchmark_count = len(benchmark_models)
        cp = cache_path or _default_cache_path()
        cp.parent.mkdir(parents=True, exist_ok=True)
        cache_document = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "fetched_at": now,
            "count": len(models_dict),
            "benchmark_count": benchmark_count,
            "benchmark_error": benchmark_error,
            "models": models_dict,
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=cp.parent,
                prefix=f".{cp.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(cache_document, temporary, indent=2, ensure_ascii=False)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            temporary_path.replace(cp)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        _or_cache = models_dict
        _or_cache_ts = now
        _or_cache_schema = _CACHE_SCHEMA_VERSION
        log.info("OpenRouter pricing updated: %d models", len(models_dict))
        return {
            "count": len(models_dict),
            "benchmark_count": benchmark_count,
            "benchmark_error": benchmark_error,
            "fetched_at": now,
            "error": None,
        }
    except Exception as e:
        log.warning("OpenRouter pricing fetch failed: %s", e)
        return {"count": 0, "fetched_at": 0, "error": str(e)}


_COST_PER_1M: dict[tuple[str, str], float] = {
    ("claude", "claude-opus-4-6"): 15.0,
    ("claude", "claude-sonnet-4-6"): 3.0,
    ("claude", "claude-haiku-4-5-20251001"): 0.8,
    ("deepseek", "deepseek-chat"): 0.14,
    ("deepseek", "deepseek-coder"): 0.14,
    ("ollama", ""): 0.0,
    ("lmstudio", ""): 0.0,
}

_PROVIDER_FALLBACK: dict[str, float] = {
    "claude": 3.0,
    "deepseek": 0.14,
    "ollama": 0.0,
    "lmstudio": 0.0,
}


# #311: Public API — Models-Discovery via OpenRouter (Foundation fuer Editor-Dropdown)
_PROVIDER_TO_VENDOR: dict[str, str | None] = {
    "claude": "anthropic",
    "openai": "openai",
    "deepseek": "deepseek",
    "gemini": "google",
    # Local providers — OpenRouter listet sie nicht; Adapter.list_models() ist die Quelle
    "ollama": None,
    "lmstudio": None,
    "manual": None,
}


def get_models_for_provider(provider: str) -> list[dict]:
    """Liefert Modelle (mit Preisen) fuer einen Provider aus dem OpenRouter-Cache.

    Locale Provider (ollama/lmstudio/manual) bekommen leere Liste — fuer die
    ist der Adapter selbst (`list_models()`) die Quelle.

    #318: ``openrouter`` ist der Gateway selbst — liefert ALLE Modelle aus dem
    Cache, weil der User mit ``vendor/model``-IDs jedes davon benutzen kann.
    """
    prov = provider.lower()
    if prov == "openrouter":
        cache = _load_or_cache()
        if not cache:
            return []
        rows: list[dict] = []
        for mid, info in cache.items():
            model_name = mid.split("/", 1)[1] if "/" in mid else mid
            rows.append(
                {
                    "id": mid,
                    "name": info.get("name", mid),
                    "model": mid,  # vendor/model fuer OpenRouter-API
                    "prompt_per_1k": round(float(info.get("prompt", 0) or 0) * 1000, 6),
                    "completion_per_1k": round(float(info.get("completion", 0) or 0) * 1000, 6),
                    "context_length": info.get("context_length", 0),
                    "max_completion_tokens": info.get("max_completion_tokens", 0),
                    "reasoning": info.get("reasoning") or {},
                    "supported_parameters": info.get("supported_parameters") or [],
                    "default_parameters": info.get("default_parameters") or {},
                    "benchmarks": info.get("benchmarks") or {},
                }
            )
        return sorted(rows, key=lambda r: r["id"])

    vendor = _PROVIDER_TO_VENDOR.get(prov)
    if vendor is None:
        return []
    cache = _load_or_cache()
    if not cache:
        return []
    prefix = vendor.lower() + "/"
    vendor_rows: list[dict] = []
    for mid, info in cache.items():
        if not mid.lower().startswith(prefix):
            continue
        model_name = mid.split("/", 1)[1] if "/" in mid else mid
        vendor_rows.append(
            {
                "id": mid,
                "name": info.get("name", mid),
                "model": model_name,
                "prompt_per_1k": round(float(info.get("prompt", 0) or 0) * 1000, 6),
                "completion_per_1k": round(float(info.get("completion", 0) or 0) * 1000, 6),
                "context_length": info.get("context_length", 0),
                "max_completion_tokens": info.get("max_completion_tokens", 0),
                "reasoning": info.get("reasoning") or {},
                "supported_parameters": info.get("supported_parameters") or [],
                "default_parameters": info.get("default_parameters") or {},
                "benchmarks": info.get("benchmarks") or {},
            }
        )
    return sorted(vendor_rows, key=lambda r: r["id"])


def get_pricing_info(cache_path: Path | None = None) -> dict:
    """Return schema, freshness and benchmark state for operator UIs."""

    cp = cache_path or _default_cache_path()
    document: dict = {}
    read_error = ""
    if cp.exists():
        try:
            loaded = json.loads(cp.read_text(encoding="utf-8"))
            document = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            read_error = str(exc)
    models = document.get("models", {}) if isinstance(document.get("models"), dict) else {}
    fetched_at = float(document.get("fetched_at", 0) or 0)
    schema_version = int(document.get("schema_version", 1) or 1) if document else 0
    age_seconds = max(0.0, time.time() - fetched_at) if fetched_at else None
    if read_error:
        status = "unreadable"
    elif not document:
        status = "missing"
    elif schema_version < _CACHE_SCHEMA_VERSION:
        status = "upgrade_required"
    elif age_seconds is not None and age_seconds > _CACHE_MAX_AGE:
        status = "stale"
    else:
        status = "fresh"
    return {
        "available": bool(models),
        "count": len(models),
        "fetched_at": fetched_at,
        "source": "openrouter",
        "ttl_seconds": _CACHE_MAX_AGE,
        "age_seconds": age_seconds,
        "schema_version": schema_version,
        "expected_schema_version": _CACHE_SCHEMA_VERSION,
        "status": status,
        "needs_refresh": status != "fresh",
        "benchmark_count": document.get("benchmark_count"),
        "benchmark_error": document.get("benchmark_error"),
        "read_error": read_error,
    }


def get_openrouter_model_status(model: str, cache_path: Path | None = None) -> dict[str, object]:
    """Return a cautious availability result from the existing model cache.

    Only a fresh, readable OpenRouter catalogue can establish that an exact
    model ID is present or absent.  Missing/stale cache data remains unknown
    and must not be presented as either a successful live probe or a known
    rejection.
    """

    info = get_pricing_info(cache_path)
    cache_status = str(info["status"])
    result: dict[str, object] = {
        "model": model,
        "source": "openrouter_model_cache",
        "cache_status": cache_status,
        "checked": cache_status == "fresh",
    }
    if cache_status != "fresh":
        return {**result, "status": "unknown", "available": None}

    cp = cache_path or _default_cache_path()
    try:
        document = json.loads(cp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            **result,
            "status": "unknown",
            "available": None,
            "cache_status": "unreadable",
            "checked": False,
        }
    raw_models = document.get("models", {}) if isinstance(document, dict) else {}
    models = raw_models if isinstance(raw_models, dict) else {}
    available = model in models
    return {
        **result,
        "status": "available" if available else "missing",
        "available": available,
    }


_REASONING_MODEL_PATTERN = re.compile(
    r"(?:^|[/_-])(?:o1|o3|o4)(?:[-_:]|$)|deepseek[-_/]?r1|(?:^|[/_-])r1(?:[-_:]|$)|"
    r"nemotron|gpt-oss|:thinking",
    re.IGNORECASE,
)


def _find_model_metadata(model: str) -> dict | None:
    cache = _load_or_cache()
    if model in cache:
        return cache[model]
    lowered = model.lower()
    exact_tail = [info for mid, info in cache.items() if mid.lower().split("/", 1)[-1] == lowered]
    return exact_tail[0] if len(exact_tail) == 1 else None


def get_model_reasoning_info(model: str) -> dict[str, object]:
    """Return reasoning capability and whether it came from metadata/heuristic.

    Explicit, current OpenRouter metadata is authoritative.  Older cache
    files did not contain a ``reasoning`` key at all; treating such entries as
    an explicit "not reasoning capable" answer would suppress the conservative
    name fallback after an upgrade.
    """

    metadata = _find_model_metadata(model)
    if (
        metadata is not None
        and isinstance(metadata.get("reasoning"), dict)
        and metadata.get("reasoning")
    ):
        reasoning = metadata.get("reasoning")
        return {
            "is_reasoning": True,
            "source": "openrouter_metadata",
            "metadata": reasoning if isinstance(reasoning, dict) else {},
            "supported_parameters": metadata.get("supported_parameters") or [],
            "max_completion_tokens": metadata.get("max_completion_tokens", 0),
        }
    if metadata is not None and "reasoning" in metadata and "supported_parameters" not in metadata:
        return {
            "is_reasoning": False,
            "source": "openrouter_metadata",
            "metadata": {},
        }
    supported = metadata.get("supported_parameters") if metadata is not None else None
    if isinstance(supported, list):
        assert metadata is not None
        reasoning_supported = any(
            name in supported for name in ("reasoning", "reasoning_effort", "include_reasoning")
        )
        return {
            "is_reasoning": reasoning_supported,
            "source": "openrouter_supported_parameters",
            "metadata": {},
            "supported_parameters": supported,
            "max_completion_tokens": metadata.get("max_completion_tokens", 0),
        }
    heuristic_match = bool(_REASONING_MODEL_PATTERN.search(model or ""))
    if metadata is not None:
        return {
            "is_reasoning": heuristic_match,
            "source": "model_name_heuristic_stale_cache",
            "metadata": {},
        }
    return {
        "is_reasoning": heuristic_match,
        "source": "model_name_heuristic",
        "metadata": {},
    }


TASK_BENCHMARK_INDEX: dict[str, str] = {
    "planning": "intelligence_index",
    "implementation": "coding_index",
    "healing": "coding_index",
    "review": "intelligence_index",
    "evaluation": "intelligence_index",
    "agentic": "agentic_index",
}


def get_model_suitability(
    model: str,
    task: str,
    *,
    threshold: float = 50.0,
    overqualification_margin_ratio: float | None = None,
) -> dict[str, object]:
    """Evaluate a model only from the task-relevant OpenRouter benchmark.

    Parameter count and model-name guesses are intentionally not used as a
    quality substitute.  Missing benchmark data stays visible as ``no_data``.
    """

    index_name = TASK_BENCHMARK_INDEX.get(task, "agentic_index")
    metadata = _find_model_metadata(model)
    benchmarks = metadata.get("benchmarks", {}) if metadata else {}
    score = benchmarks.get(index_name) if isinstance(benchmarks, dict) else None
    if not isinstance(score, (int, float)):
        return {
            "available": False,
            "status": "no_data",
            "index": index_name,
            "score": None,
            "threshold": float(threshold),
        }
    numeric_score = float(score)
    numeric_threshold = float(threshold)
    margin = (
        float(overqualification_margin_ratio)
        if overqualification_margin_ratio is not None
        else None
    )
    overqualified_at = (
        numeric_threshold * (1.0 + margin)
        if margin is not None and 0.0 <= margin <= 1.0 and numeric_threshold > 0
        else None
    )
    if numeric_score < numeric_threshold:
        status = "below_threshold"
    elif overqualified_at is not None and numeric_score >= overqualified_at:
        status = "overqualified"
    else:
        status = "suitable"
    return {
        "available": True,
        "status": status,
        "index": index_name,
        "score": numeric_score,
        "threshold": numeric_threshold,
        "overqualification_margin_ratio": margin,
        "overqualified_at": overqualified_at,
    }


def _comparable_price(metadata: dict | None) -> tuple[float, float] | None:
    if not metadata or metadata.get("additional_pricing") != {}:
        return None
    prompt = metadata.get("prompt")
    completion = metadata.get("completion")
    if not isinstance(prompt, (int, float)) or not isinstance(completion, (int, float)):
        return None
    if float(prompt) <= 0 or float(completion) <= 0:
        return None
    return float(prompt), float(completion)


def get_model_cost_advisory(
    model: str,
    task: str,
    *,
    threshold: float,
    overqualification_margin_ratio: float,
    enabled: bool,
) -> dict[str, object]:
    """Return a workload-neutral, same-generation model cost hint.

    A candidate must meet the same task threshold and strictly Pareto-dominate
    the selected model on prompt/completion price.  Lexical model ordering is
    only a deterministic presentation tie-break, never a cost aggregation.
    """

    suitability = get_model_suitability(
        model,
        task,
        threshold=threshold,
        overqualification_margin_ratio=overqualification_margin_ratio,
    )
    result: dict[str, object] = {
        "enabled": bool(enabled),
        "status": suitability["status"],
        "suitability": suitability,
        "recommendation": None,
    }
    if not enabled or suitability["status"] != "overqualified":
        return result
    if (
        _or_cache_schema != _CACHE_SCHEMA_VERSION
        or not _or_cache_ts
        or time.time() - _or_cache_ts > _CACHE_MAX_AGE
    ):
        return {**result, "status": "incomparable_generation"}

    cache = _load_or_cache()
    selected_metadata = cache.get(model)
    selected_price = _comparable_price(selected_metadata)
    if selected_price is None:
        return {**result, "status": "incomplete_price_basis"}
    selected_sources = sorted(
        str(source) for source in (selected_metadata or {}).get("benchmark_sources", []) if source
    )
    if not selected_sources:
        return {**result, "status": "incomparable_benchmark_basis"}

    candidates: list[tuple[str, tuple[float, float]]] = []
    for candidate_id, metadata in cache.items():
        if candidate_id == model:
            continue
        candidate_suitability = get_model_suitability(
            candidate_id,
            task,
            threshold=threshold,
            overqualification_margin_ratio=overqualification_margin_ratio,
        )
        if candidate_suitability["status"] not in {"suitable", "overqualified"}:
            continue
        candidate_sources = sorted(
            str(source) for source in metadata.get("benchmark_sources", []) if source
        )
        if candidate_sources != selected_sources:
            continue
        candidate_price = _comparable_price(metadata)
        if candidate_price is None:
            continue
        if (
            candidate_price[0] <= selected_price[0]
            and candidate_price[1] <= selected_price[1]
            and candidate_price != selected_price
        ):
            candidates.append((candidate_id, candidate_price))

    if not candidates:
        return {**result, "status": "overqualified_no_comparable_alternative"}
    candidates.sort(key=lambda candidate: candidate[0])
    alternative, alternative_price = candidates[0]
    return {
        **result,
        "status": "recommendation_available",
        "recommendation": {
            "model": alternative,
            "candidate_count": len(candidates),
            "tie_break": "canonical_model_id",
            "selected_price_per_1k": {
                "prompt": round(selected_price[0] * 1000, 6),
                "completion": round(selected_price[1] * 1000, 6),
            },
            "alternative_price_per_1k": {
                "prompt": round(alternative_price[0] * 1000, 6),
                "completion": round(alternative_price[1] * 1000, 6),
            },
            "cache_generation": _or_cache_ts,
            "benchmark_sources": selected_sources,
            "basis": "strict_prompt_completion_pareto",
        },
    }


def _find_or_price(provider: str, model: str) -> tuple[float, float] | None:
    cache = _load_or_cache()
    if not cache:
        return None
    mappings = [
        f"{provider}/{model}",
        f"anthropic/{model}" if provider == "claude" else None,
    ]
    for candidate in mappings:
        if candidate and candidate in cache:
            entry = cache[candidate]
            return (entry["prompt"], entry["completion"])
    mod_lower = model.lower()
    for mid, entry in cache.items():
        if mod_lower and mod_lower in mid.lower():
            return (entry["prompt"], entry["completion"])
    return None


def estimate_cost(
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    prov = provider.lower()
    if prov in ("ollama", "lmstudio"):
        return 0.0
    total = input_tokens + output_tokens
    if total <= 0:
        return 0.0

    or_price = _find_or_price(prov, model)
    if or_price is not None:
        prompt_rate, completion_rate = or_price
        billable_input = input_tokens - cached_tokens
        return round(
            max(0, billable_input) * prompt_rate
            + cached_tokens * prompt_rate * 0.1
            + output_tokens * completion_rate,
            8,
        )

    price = _COST_PER_1M.get((prov, model))
    if price is None:
        for (p, m), v in _COST_PER_1M.items():
            if p == prov and m and m in model:
                price = v
                break
    if price is None:
        price = _PROVIDER_FALLBACK.get(prov, 0.0)
    return round(price * total / 1_000_000, 8)
