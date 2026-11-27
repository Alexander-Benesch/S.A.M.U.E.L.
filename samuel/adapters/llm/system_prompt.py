"""#338 Schicht B (Wiring): SystemPromptInjectorAdapter.

Wraps an ``ILLMProvider`` and prepends a configured system message to
each ``complete`` call — unless the caller already supplied a system
message at index 0 (then the caller's choice wins, defensive default).

Why a wrapper rather than per-adapter logic: the eight providers
(claude/deepseek/gemini/openai/openrouter/ollama/lmstudio/manual) share
no message-prep code, and the task-specific system prompt lookup
(model > provider > generic > package from ``load_system_prompt``) is itself a
cross-cutting concern. Putting the inject at adapter-wrap time keeps
each leaf adapter dumb and testable.
"""

from __future__ import annotations

from typing import Any

from samuel.adapters.llm.profiles import prompt_capture, prompt_digest
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class SystemPromptInjectorAdapter(ILLMProvider):
    def __init__(
        self, inner: ILLMProvider, *, system_prompt: str, profile: dict[str, Any] | None = None
    ) -> None:
        self._inner = inner
        self.profile = profile or {}
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
        caller_system = bool(messages and messages[0].get("role") == "system")
        effective = (
            messages
            if not self._prompt or caller_system
            else [
                {"role": "system", "content": self._prompt},
                *messages,
            ]
        )
        capture = prompt_capture.get()
        if capture is not None:
            capture.update(self.profile)
            if caller_system:
                capture.update(
                    source="caller",
                    classification="custom",
                    name="",
                    content_sha256=prompt_digest(messages[0].get("content", "")),
                )
            capture["effective_messages_sha256"] = prompt_digest(effective)
        return self._inner.complete(effective, **kwargs)
