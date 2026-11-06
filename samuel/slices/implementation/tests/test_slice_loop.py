"""#152: SLICE-Request-Loop in run_llm_loop (gezieltes Nachladen + Anti-Scan)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse
from samuel.slices.implementation.llm_loop import run_llm_loop


class _ScriptedLLM(ILLMProvider):
    """Liefert pro Runde den naechsten Text aus einer Skript-Liste."""

    def __init__(self, scripted: list[str]):
        self._scripted = scripted
        self._i = 0
        self.prompts: list[str] = []

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.prompts.append(messages[-1]["content"])
        text = self._scripted[self._i] if self._i < len(self._scripted) else ""
        self._i += 1
        return LLMResponse(text=text, input_tokens=5, output_tokens=5, model_used="m")

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 128_000


def test_slice_request_served_then_patch_applies(tmp_path: Path):
    (tmp_path / "big.py").write_text("x = 1\n" * 400)
    served: list = []

    def resolver(rel, start, end):
        served.append((rel, start, end))
        return f"### {rel}:{start}-{end}\n```\n{start} | x = 1\n```"

    # Runde 1: SLICE-Request (keine Patches) -> bedient.
    # Runde 2: echter Patch -> angewandt.
    patch = "## WRITE: new.py\nprint(1)\n## END_WRITE"
    llm = _ScriptedLLM(["SLICE: big.py:100-120", patch])
    result = run_llm_loop(llm, "impl", tmp_path, slice_resolver=resolver)

    assert served == [("big.py", 100, 120)]
    assert result["success"] is True
    assert (tmp_path / "new.py").exists()
    # Slice-Antwort floss in den 2. Prompt
    assert "Angeforderter Code" in llm.prompts[1]
    assert "big.py:100-120" in llm.prompts[1]


def test_prompt_observer_runs_before_every_llm_round(tmp_path: Path):
    (tmp_path / "big.py").write_text("x = 1\n" * 400)
    observed: list[tuple[int, str]] = []

    def resolver(rel, start, end):
        return f"### {rel}:{start}-{end}\n```\ncode\n```"

    llm = _ScriptedLLM(["SLICE: big.py:100-120", "## WRITE: new.py\nprint(1)\n## END_WRITE"])
    run_llm_loop(
        llm,
        "base prompt",
        tmp_path,
        slice_resolver=resolver,
        on_prompt=lambda round_num, prompt: observed.append((round_num, prompt)),
    )

    assert [round_num for round_num, _ in observed] == [1, 2]
    assert observed[0][1] == "base prompt"
    assert "Angeforderter Code" in observed[1][1]


def test_no_resolver_means_no_slice_loop(tmp_path: Path):
    llm = _ScriptedLLM(["SLICE: big.py:1-10", "SLICE: big.py:1-10"])
    result = run_llm_loop(llm, "impl", tmp_path)  # kein resolver
    # Ohne Resolver: erste Runde ohne Patches -> Abbruch, kein Patch.
    assert result["success"] is False
    assert llm._i == 1  # nur eine Runde


def test_slice_rounds_capped(tmp_path: Path):
    (tmp_path / "big.py").write_text("x = 1\n" * 400)

    def resolver(rel, start, end):
        return f"### {rel}:{start}-{end}\n```\ncode\n```"

    # 5 verschiedene SLICE-Runden; MAX_SLICE_ROUNDS=3 -> danach kein Serving mehr.
    scripted = [f"SLICE: big.py:{i}-{i + 10}" for i in range(1, 6)]
    llm = _ScriptedLLM(scripted)
    result = run_llm_loop(llm, "impl", tmp_path, slice_resolver=resolver)
    assert result["success"] is False
    # nach 3 Slice-Runden bricht die 4. (kein Patch, Budget erschoepft) ab
    assert llm._i == 4


def test_duplicate_slice_not_reserved(tmp_path: Path):
    (tmp_path / "big.py").write_text("x = 1\n" * 400)
    calls: list = []

    def resolver(rel, start, end):
        calls.append((rel, start, end))
        return f"### {rel}:{start}-{end}\n```\ncode\n```"

    # gleiche Range zweimal -> beim 2. Mal dedupliziert (kein neuer Block ->
    # keine Slice-Runde -> Abbruch).
    llm = _ScriptedLLM(["SLICE: big.py:1-10", "SLICE: big.py:1-10", "x"])
    run_llm_loop(llm, "impl", tmp_path, slice_resolver=resolver)
    assert calls == [("big.py", 1, 10)]
