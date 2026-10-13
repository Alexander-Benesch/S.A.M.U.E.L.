from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from samuel.core.types import LLMResponse
from samuel.slices.implementation.llm_loop import (
    _build_retry_prompt,
    _load_file_excerpt_for_patch,
    run_llm_loop,
)


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.context_window = 32000

    def complete(self, messages: list[dict], **_: Any) -> LLMResponse:
        self.prompts.append(messages[-1]["content"])
        text = self._responses.pop(0) if self._responses else ""
        return LLMResponse(text=text, input_tokens=10, output_tokens=20, stop_reason="end")

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4


@dataclass
class _P:
    file: str
    lines: tuple[int, int] | None = None
    search: str | None = None
    type: str | None = None


class TestLoadExcerpt:
    def test_replace_lines_loads_context(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("\n".join(f"line{i}" for i in range(40)))
        excerpt = _load_file_excerpt_for_patch(
            tmp_path,
            {
                "file": "a.py",
                "lines": (20, 22),
                "type": "replace_lines",
            },
        )
        assert "line15" in excerpt
        assert "line20" in excerpt
        assert "line30" in excerpt

    def test_search_anchors_to_hit(self, tmp_path: Path) -> None:
        content = "\n".join(["pre"] * 15 + ["target_line"] + ["post"] * 15)
        (tmp_path / "a.py").write_text(content)
        excerpt = _load_file_excerpt_for_patch(
            tmp_path,
            {
                "file": "a.py",
                "search": "target_line",
                "replace": "x",
            },
        )
        assert "target_line" in excerpt

    def test_missing_file_returns_note(self, tmp_path: Path) -> None:
        excerpt = _load_file_excerpt_for_patch(tmp_path, {"file": "nope.py"})
        assert "existiert nicht" in excerpt

    def test_unsafe_file_returns_content_free_note(self, tmp_path: Path) -> None:
        raw = "../operator-secret.txt"

        excerpt = _load_file_excerpt_for_patch(tmp_path, {"file": raw})

        assert excerpt == "(Patchziel abgelehnt: traversal)"
        assert raw not in excerpt

    def test_git_control_file_is_not_read_for_retry_excerpt(self, tmp_path: Path) -> None:
        target = tmp_path / ".git/config"
        target.parent.mkdir()
        target.write_text("operator-secret\n", encoding="utf-8")

        excerpt = _load_file_excerpt_for_patch(tmp_path, {"file": ".git/config"})

        assert excerpt == "(Patchziel abgelehnt: git_control_plane)"
        assert "operator-secret" not in excerpt


class TestBuildRetryPrompt:
    def test_includes_failure_and_code(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("def foo():\n    pass\n")
        prompt = _build_retry_prompt(
            base_prompt="Base task",
            round_num=1,
            failures_with_patches=[
                ("SEARCH not found in mod.py", {"file": "mod.py", "search": "def foo"})
            ],
            project_root=tmp_path,
        )
        assert "Base task" in prompt
        assert "SEARCH not found" in prompt
        assert "mod.py" in prompt
        assert "def foo" in prompt

    def test_deduplicates_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n")
        prompt = _build_retry_prompt(
            base_prompt="B",
            round_num=1,
            failures_with_patches=[
                ("fail1", {"file": "a.py", "search": "x"}),
                ("fail2", {"file": "a.py", "search": "x"}),
            ],
            project_root=tmp_path,
        )
        assert prompt.count("a.py (aktueller Zustand)") == 1


class TestLoopRetriesWithRealCode:
    def test_invalid_python_write_retry_sees_last_valid_state(self, tmp_path: Path) -> None:
        target = tmp_path / "module.py"
        target.write_text("value = 1\n", encoding="utf-8")
        invalid = "## WRITE: module.py\ndef (\n## END_WRITE"
        valid = "## WRITE: module.py\nvalue = 2\n## END_WRITE"
        llm = ScriptedLLM([invalid, valid])

        result = run_llm_loop(llm, "base prompt", project_root=tmp_path)

        assert result["success"] is True
        assert result["round"] == 2
        assert target.read_text(encoding="utf-8") == "value = 2\n"
        assert "value = 1" in llm.prompts[1]
        assert "def (" not in llm.prompts[1]

    def test_invalid_json_retry_sees_last_valid_state(self, tmp_path: Path) -> None:
        target = tmp_path / "config.json"
        target.write_text('{"ok": true}\n', encoding="utf-8")
        invalid = (
            '## config.json\n<<<<<<< SEARCH\n{"ok": true}\n=======\n{not-json}\n>>>>>>> REPLACE\n'
        )
        valid = (
            "## config.json\n"
            "<<<<<<< SEARCH\n"
            '{"ok": true}\n'
            "=======\n"
            '{"ok": false}\n'
            ">>>>>>> REPLACE\n"
        )
        llm = ScriptedLLM([invalid, valid])

        result = run_llm_loop(llm, "base prompt", project_root=tmp_path)

        assert result["success"] is True
        assert result["round"] == 2
        assert target.read_text(encoding="utf-8") == '{"ok": false}\n'
        assert '{"ok": true}' in llm.prompts[1]
        assert "{not-json}" not in llm.prompts[1]

    def test_retry_includes_real_code_on_failure(self, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("def existing():\n    return 1\n")
        bad_patch = (
            "## f.py\n"
            "<<<<<<< SEARCH\n"
            "def nonexistent():\n"
            "=======\n"
            "def replaced():\n"
            ">>>>>>> REPLACE\n"
        )
        good_patch = (
            "## f.py\n"
            "<<<<<<< SEARCH\n"
            "def existing():\n"
            "    return 1\n"
            "=======\n"
            "def existing():\n"
            "    return 2\n"
            ">>>>>>> REPLACE\n"
        )
        llm = ScriptedLLM([bad_patch, good_patch])

        result = run_llm_loop(llm, "base prompt", project_root=tmp_path)

        assert result["success"] is True
        assert result["round"] == 2
        assert any("aktueller Zustand" in p for p in llm.prompts[1:])
        assert any("def existing()" in p for p in llm.prompts[1:])

    def test_loop_returns_failure_if_still_fails(self, tmp_path: Path) -> None:
        """#319: 2 consecutive zero-applied rounds → abort early with no_progress."""
        (tmp_path / "f.py").write_text("x = 1\n")
        bad = "## f.py\n<<<<<<< SEARCH\nnot-there\n=======\nreplacement\n>>>>>>> REPLACE\n"
        llm = ScriptedLLM([bad] * 5)

        result = run_llm_loop(llm, "base", project_root=tmp_path)

        assert result["success"] is False
        # #319: changed from "partial_failure" — system now aborts early
        assert result["reason"] == "no_progress"
        assert len(result["failures"]) >= 1
        assert result["diagnostic"] == {
            "kind": "apply_failure",
            "round": 2,
            "patch_count": 1,
            "applied_patch_count": 0,
            "apply_failures": [
                {
                    "code": "search_not_found",
                    "target": "f.py",
                    "detail": "SEARCH not found in f.py",
                }
            ],
        }
        # Should have aborted after round 2, not run all 5
        assert result["round"] == 2

    def test_terminal_apply_diagnostic_redacts_applier_detail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "f.py").write_text("x = 1\n")
        patch = "## f.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"
        secret = 'api_key="supersecretvalue"'

        class RejectingApplier:
            def apply(self, _file_path: Path, _patches: list[dict[str, Any]]):
                return [(False, f"provider rejected {secret}")]

        monkeypatch.setattr(
            "samuel.slices.implementation.llm_loop.get_applier",
            lambda _path: RejectingApplier(),
        )

        result = run_llm_loop(ScriptedLLM([patch, patch]), "base", project_root=tmp_path)

        assert result["reason"] == "no_progress"
        assert result["diagnostic"]["apply_failures"] == [
            {
                "code": "apply_rejected",
                "target": "f.py",
                "detail": "provider rejected ***REDACTED***",
            }
        ]
        assert secret not in repr(result)

    def test_loop_aborts_after_two_zero_progress_rounds(self, tmp_path: Path) -> None:
        """#319: 2 consecutive 0-applied rounds → no_progress + early-abort."""
        (tmp_path / "f.py").write_text("x = 1\n")
        bad = "## f.py\n<<<<<<< SEARCH\nmissing\n=======\nx\n>>>>>>> REPLACE\n"
        llm = ScriptedLLM([bad, bad, bad, bad, bad])
        result = run_llm_loop(llm, "base", project_root=tmp_path)
        assert result["reason"] == "no_progress"
        assert result["round"] == 2  # aborted at round 2
        assert len(result.get("rounds_stats", [])) == 2

    def test_loop_includes_rounds_stats_in_result(self, tmp_path: Path) -> None:
        """#319: rounds_stats list für Health-Metriken."""
        (tmp_path / "f.py").write_text("x = 1\n")
        good = "## f.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"
        llm = ScriptedLLM([good])
        result = run_llm_loop(llm, "base", project_root=tmp_path)
        assert result["success"] is True
        assert result["reason"] == "complete"
        assert "rounds_stats" in result
        assert len(result["rounds_stats"]) == 1
        assert result["rounds_stats"][0]["applied"] == 1
        assert result["rounds_stats"][0]["failed"] == 0

    @pytest.mark.parametrize("response", ["", "I cannot provide a patch for this request."])
    def test_non_truncated_response_without_parseable_patch_is_explicitly_blocked(
        self, tmp_path: Path, response: str
    ) -> None:
        result = run_llm_loop(ScriptedLLM([response]), "base", project_root=tmp_path)

        assert result["success"] is False
        assert result["reason"] == "no_parseable_patches"
        assert result["failures"] == ["no_parseable_patches"]
        assert result["diagnostic"] == {
            "round": 1,
            "patch_count": 0,
            "applied_patch_count": 0,
        }
        assert "response" not in result
        assert "text" not in result
        if response:
            assert response not in repr(result)

    def test_no_parseable_patches_rolls_back_earlier_partial_progress(self, tmp_path: Path) -> None:
        target = tmp_path / "existing.txt"
        target.write_text("operator state\n", encoding="utf-8")
        partial = (
            "## existing.txt\n"
            "<<<<<<< SEARCH\noperator state\n=======\nllm state\n>>>>>>> REPLACE\n"
            "## missing.txt\n"
            "<<<<<<< SEARCH\nabsent\n=======\nreplacement\n>>>>>>> REPLACE\n"
        )

        result = run_llm_loop(
            ScriptedLLM([partial, "No patch available."]),
            "base",
            project_root=tmp_path,
        )

        assert result["reason"] == "no_parseable_patches"
        assert result["patches_applied"] == []
        assert result["patches_rolled_back"] == 1
        assert result["rollback"]["status"] == "completed"
        assert target.read_text(encoding="utf-8") == "operator state\n"

    def test_no_progress_rolls_back_earlier_partial_progress(self, tmp_path: Path) -> None:
        target = tmp_path / "existing.txt"
        target.write_text("before\n", encoding="utf-8")
        partial = (
            "## existing.txt\n"
            "<<<<<<< SEARCH\nbefore\n=======\nafter\n>>>>>>> REPLACE\n"
            "## missing.txt\n"
            "<<<<<<< SEARCH\nabsent\n=======\nreplacement\n>>>>>>> REPLACE\n"
        )
        failed = "## missing.txt\n<<<<<<< SEARCH\nabsent\n=======\nreplacement\n>>>>>>> REPLACE\n"

        result = run_llm_loop(
            ScriptedLLM([partial, failed, failed]),
            "base",
            project_root=tmp_path,
        )

        assert result["reason"] == "no_progress"
        assert result["patches_applied"] == []
        assert result["patches_rolled_back"] == 1
        assert result["rollback"]["status"] == "completed"
        assert target.read_text(encoding="utf-8") == "before\n"

    def test_partial_failure_rolls_back_every_created_file(self, tmp_path: Path) -> None:
        responses = [
            (
                f"## WRITE: generated/round_{round_num}.go\n"
                "package generated\n"
                "## END_WRITE\n"
                "## missing.txt\n"
                "<<<<<<< SEARCH\nabsent\n=======\nreplacement\n>>>>>>> REPLACE\n"
            )
            for round_num in range(1, 6)
        ]

        result = run_llm_loop(
            ScriptedLLM(responses),
            "base",
            project_root=tmp_path,
        )

        assert result["reason"] == "partial_failure"
        assert result["round"] == 5
        assert result["patches_applied"] == []
        assert result["patches_rolled_back"] == 5
        assert result["rollback"]["files_removed"] == 5
        assert not (tmp_path / "generated").exists()

    def test_unexpected_exception_rolls_back_partial_progress(self, tmp_path: Path) -> None:
        target = tmp_path / "existing.txt"
        target.write_text("before\n", encoding="utf-8")
        partial = (
            "## existing.txt\n"
            "<<<<<<< SEARCH\nbefore\n=======\nafter\n>>>>>>> REPLACE\n"
            "## missing.txt\n"
            "<<<<<<< SEARCH\nabsent\n=======\nreplacement\n>>>>>>> REPLACE\n"
        )

        class RaiseSecondRound(ScriptedLLM):
            def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
                if self.prompts:
                    raise RuntimeError("provider unavailable")
                return super().complete(messages, **kwargs)

        with pytest.raises(RuntimeError, match="provider unavailable"):
            run_llm_loop(
                RaiseSecondRound([partial]),
                "base",
                project_root=tmp_path,
            )

        assert target.read_text(encoding="utf-8") == "before\n"
