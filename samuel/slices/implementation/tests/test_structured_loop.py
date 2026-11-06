from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse
from samuel.slices.implementation.llm_loop import run_llm_loop


class _StructuredLLM(ILLMProvider):
    """#335: liefert in Runde 1 strukturierte Patches (JSON), danach nichts."""

    def __init__(self, structured: dict):
        self._structured = structured
        self._calls = 0

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self._calls += 1
        if self._calls == 1:
            return LLMResponse(
                text="", input_tokens=10, output_tokens=5, structured=self._structured
            )
        return LLMResponse(text="", input_tokens=1, output_tokens=1)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 128_000


def test_loop_applies_structured_write_patch(tmp_path: Path):
    structured = {"patches": [{"file": "new.py", "type": "write", "write": "print(1)\n"}]}
    result = run_llm_loop(_StructuredLLM(structured), "impl", tmp_path)
    assert (tmp_path / "new.py").exists()
    assert (tmp_path / "new.py").read_text() == "print(1)\n"
    assert any(p.get("file") == "new.py" for p in result["patches_applied"])


def test_loop_falls_back_to_text_when_no_structured(tmp_path: Path):
    class _TextLLM(ILLMProvider):
        def __init__(self):
            self._n = 0

        def complete(self, messages, **kwargs):
            self._n += 1
            if self._n == 1:
                return LLMResponse(
                    text="## WRITE: t.py\nhello\n## END_WRITE",
                    input_tokens=1,
                    output_tokens=1,
                )
            return LLMResponse(text="", input_tokens=1, output_tokens=1)

        def estimate_tokens(self, text):
            return 1

        @property
        def context_window(self):
            return 1000

    result = run_llm_loop(_TextLLM(), "impl", tmp_path)
    assert (tmp_path / "t.py").exists()
    assert any(p.get("file") == "t.py" for p in result["patches_applied"])


def test_structured_invalid_python_write_is_rejected_without_mutation(tmp_path: Path):
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    before = (target.read_bytes(), target.stat().st_mode, target.stat().st_mtime_ns)
    structured = {"patches": [{"file": "module.py", "type": "write", "write": "def ("}]}

    result = run_llm_loop(_StructuredLLM(structured), "impl", tmp_path)

    after = (target.read_bytes(), target.stat().st_mode, target.stat().st_mtime_ns)
    assert result["success"] is False
    assert result["reason"] == "no_parseable_patches"
    assert after == before
