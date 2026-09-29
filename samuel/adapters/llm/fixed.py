"""#368 Task 8: deterministischer LLM-Adapter fuer reproduzierbare E2E-/Demo-Runs.

Der ``ManualAdapter`` ist Mensch-im-Loop (wartet auf eine getippte Antwort) und
damit nicht reproduzierbar. ``FixedResponseAdapter`` gibt vorab definierte
Antworten in Reihenfolge zurueck — gleiche Eingabe, gleiche Ausgabe, ohne
Netzwerk. Damit lassen sich Gate-/Workflow-Szenarien deterministisch testen
(z.B. ein PR, der bewusst eine erfundene Funktion + eine Workflow-Permission
einfuehrt) und die FP-Rate auf bekannten Faellen messen.
"""

from __future__ import annotations

from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse


class FixedResponseAdapter(ILLMProvider):
    def __init__(
        self,
        responses: str | list[str] | list[LLMResponse],
        *,
        context_window: int = 128_000,
        model: str = "fixed",
    ) -> None:
        if isinstance(responses, str):
            responses = [responses]
        self._responses: list[Any] = list(responses)
        self._context_window = context_window
        self._model = model
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls.append(messages)
        idx = len(self.calls) - 1
        if idx < len(self._responses):
            item = self._responses[idx]
        elif self._responses:
            item = self._responses[-1]  # letzte Antwort wiederholen
        else:
            item = ""
        if isinstance(item, LLMResponse):
            return item
        prompt = messages[-1].get("content", "") if messages else ""
        text = str(item)
        return LLMResponse(
            text=text,
            input_tokens=self.estimate_tokens(prompt),
            output_tokens=self.estimate_tokens(text),
            model_used=self._model,
        )

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    @property
    def context_window(self) -> int:
        return self._context_window
