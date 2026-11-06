"""#153: Param-Size-Check fuer lokale LLM-Modelle.

Aus v1 portiert: lokale Modelle (Ollama/LM Studio) unter einer Mindest-
Parametergroesse liefern erfahrungsgemaess schlechte Code-Qualitaet. Wir parsen
die Groesse aus dem Modellnamen (``llama3:8b`` -> 8.0, ``qwen2.5-14b`` -> 14.0)
und warnen, wenn sie unter ``min_local_model_params_b`` liegt — oder wenn sie
sich gar nicht ableiten laesst (dann ist die Qualitaet unbekannt).
"""

from __future__ import annotations

import re

# Provider, die lokal laufen — nur fuer die der Param-Size-Check sinnvoll ist
# (Cloud-Modelle wie deepseek/claude tragen keine Groesse im Namen).
LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "lmstudio"})

DEFAULT_MIN_LOCAL_PARAMS_B = 7.0

# z.B. "llama3:8b", "qwen2.5-14b", "phi-3-mini-3.8b", "mixtral:8x7b"
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]\b")
_MOE_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+(?:\.\d+)?)\s*[bB]\b")


def parse_param_size_b(model_name: str) -> float | None:
    """Parametergroesse in Milliarden (B) aus dem Modellnamen, sonst ``None``.

    Erkennt auch Mixture-of-Experts-Notation (``8x7b`` -> 56.0)."""
    if not model_name:
        return None
    moe = _MOE_RE.search(model_name)
    if moe:
        return float(moe.group(1)) * float(moe.group(2))
    m = _SIZE_RE.search(model_name)
    if m:
        return float(m.group(1))
    return None


def check_local_model_size(
    provider: str,
    model: str,
    min_b: float = DEFAULT_MIN_LOCAL_PARAMS_B,
    local_providers: frozenset[str] = LOCAL_PROVIDERS,
) -> dict | None:
    """Warnung (dict) falls ein lokales Modell die Mindestgroesse unterschreitet
    oder die Groesse unbekannt ist; sonst ``None`` (kein Befund).

    Schema: ``{provider, model, params_b, min_b, reason}`` mit ``reason`` aus
    ``{"below_min", "unknown_size"}``.
    """
    if (provider or "").lower() not in local_providers:
        return None
    params_b = parse_param_size_b(model)
    if params_b is None:
        return {
            "provider": provider,
            "model": model,
            "params_b": None,
            "min_b": min_b,
            "reason": "unknown_size",
        }
    if params_b < min_b:
        return {
            "provider": provider,
            "model": model,
            "params_b": params_b,
            "min_b": min_b,
            "reason": "below_min",
        }
    return None
