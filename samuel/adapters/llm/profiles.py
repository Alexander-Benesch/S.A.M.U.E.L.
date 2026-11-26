"""Non-authoritative prompt provenance; never stores prompt bodies in evidence."""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from typing import Any

CONTRACT_VERSION = "samuel-prompt-contract/1"
REFERENCE_PROMPTS = {
    "planning": "planner.md",
    "implementation": "senior_python.md",
    "review": "reviewer.md",
    "healing": "healer.md",
    "evaluation": "log_analyst.md",
}
# Metering opens a fresh capture for each physical call, including failed calls.
prompt_capture: ContextVar[dict[str, Any] | None] = ContextVar("prompt_capture", default=None)


def prompt_digest(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )


def prompt_profile(
    resolved: dict,
    *,
    task: str,
    provider: str,
    model: str,
    route: str = "standard",
    custom_binding: bool = False,
) -> dict[str, Any]:
    return {
        "task": task,
        "route": route,
        "provider": provider,
        "model": model,
        "name": resolved["name"],
        "source": resolved["source"],
        "content_sha256": prompt_digest(resolved["content"].strip()),
        "classification": "reference"
        if (
            resolved["source"] == "package"
            and not custom_binding
            and resolved["name"] == REFERENCE_PROMPTS.get(task)
        )
        else "custom",
        "qualification": "not_established",
        "runtime_contract": CONTRACT_VERSION,
    }
