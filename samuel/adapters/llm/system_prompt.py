"""#338 Schicht B (Wiring): SystemPromptInjectorAdapter.

Wraps an ``ILLMProvider`` and prepends a configured system message to
each ``complete`` call — unless the caller already supplied a system
message at index 0 (then the caller's choice wins, defensive default).

Why a wrapper rather than per-adapter logic: the seven providers
(claude/deepseek/gemini/openai/openrouter/ollama/lmstudio/manual) share
no message-prep code, and the task-specific system prompt lookup
(generic > provider > model from ``load_system_prompt``) is itself a
cross-cutting concern. Putting the inject at adapter-wrap time keeps
each leaf adapter dumb and testable.
"""
from __future__ import annotations

from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class SystemPromptInjectorAdapter(ILLMProvider):
    def __init__(self, inner: ILLMProvider, *, system_prompt: str) -> None:
        self._inner = inner
        # Empty / whitespace-only prompts are a no-op so the wrapper is
        # safe to put in front of every adapter without conditional
        # construction at the call-site.
        self._prompt = (system_prompt or "").strip()

    @property
    def context_window(self) -> int:
        return self._inner.context_window

    @property
    def capabilities(self) -> set[str]:
        return self._inner.capabilities

    def estimate_tokens(self, text: str) -> int:
        return self._inner.estimate_tokens(text)

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        if not self._prompt:
            return self._inner.complete(messages, **kwargs)
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            # Caller already supplied a system prompt. Don't override —
            # the slice may have built a more specific one (e.g.
            # plan-context-with-skeleton). The configured task-prompt
            # is treated as a *default* only.
            return self._inner.complete(messages, **kwargs)
        injected = [{"role": "system", "content": self._prompt}, *messages]
        return self._inner.complete(injected, **kwargs)
