"""#270: run_llm_loop dekoriert Patches mit Inline-Markern (gated, mit Fallback)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse
from samuel.slices.implementation.llm_loop import run_llm_loop

ATTR = {"enabled": True, "verbosity": "minimal", "version": "", "issue": 270, "date": "2026-05-29"}


class _OneShotLLM(ILLMProvider):
    """Liefert in Runde 1 strukturierte Patches, danach nichts mehr."""

    def __init__(self, patches: list[dict], model: str = "deepseek"):
        self._patches = patches
        self._model = model
        self._calls = 0

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self._calls += 1
        if self._calls == 1:
            return LLMResponse(
                text="",
                input_tokens=10,
                output_tokens=5,
                model_used=self._model,
                structured={"patches": self._patches},
            )
        return LLMResponse(text="", input_tokens=1, output_tokens=1, model_used=self._model)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 128_000


def test_write_patch_gets_inline_marker(tmp_path: Path):
    llm = _OneShotLLM([{"file": "new.py", "type": "write", "write": "print(1)\n"}])
    result = run_llm_loop(llm, "impl", tmp_path, attribution=ATTR)
    content = (tmp_path / "new.py").read_text()
    assert content.startswith("# llm: deepseek 2026-05-29\n")
    assert "print(1)" in content
    assert result["model"] == "deepseek"


def test_no_marker_when_attribution_disabled(tmp_path: Path):
    llm = _OneShotLLM([{"file": "new.py", "type": "write", "write": "print(1)\n"}])
    result = run_llm_loop(llm, "impl", tmp_path, attribution={"enabled": False})
    content = (tmp_path / "new.py").read_text()
    assert "llm:" not in content
    assert content == "print(1)\n"
    assert result["model"] == "deepseek"


def test_no_marker_without_attribution_arg(tmp_path: Path):
    llm = _OneShotLLM([{"file": "new.py", "type": "write", "write": "print(1)\n"}])
    run_llm_loop(llm, "impl", tmp_path)
    assert "llm:" not in (tmp_path / "new.py").read_text()


def test_unknown_extension_not_marked(tmp_path: Path):
    llm = _OneShotLLM([{"file": "page.html", "type": "write", "write": "<div>x</div>\n"}])
    run_llm_loop(llm, "impl", tmp_path, attribution=ATTR)
    assert (tmp_path / "page.html").read_text() == "<div>x</div>\n"


def test_fallback_when_marker_breaks_python(tmp_path: Path):
    """Marker bricht den Patch (Teil-Zeilen-Replace) -> unmarkiert anwenden."""
    target = tmp_path / "a.py"
    target.write_text("value = 1\n")
    # search '1' -> replace '2'; mit Marker davor entstuende 'value = # llm..\n2'
    # (SyntaxError) -> Fallback liefert sauberes 'value = 2'.
    llm = _OneShotLLM([{"file": "a.py", "search": "1", "replace": "2"}])
    result = run_llm_loop(llm, "impl", tmp_path, attribution=ATTR)
    content = target.read_text()
    assert "llm:" not in content
    assert content == "value = 2"
    assert any(p.get("file") == "a.py" for p in result["patches_applied"])
