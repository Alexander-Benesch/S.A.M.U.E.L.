from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from samuel.core.types import LLMResponse
from samuel.slices.implementation.llm_loop import run_llm_loop
from samuel.slices.implementation.patch_targets import resolve_patch_target


class _Responses:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.context_window = 32_000

    def complete(self, messages: list[dict[str, str]], **_: Any) -> LLMResponse:
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="", input_tokens=1, output_tokens=1)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4


def _text_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, input_tokens=10, output_tokens=20)


def _structured_response(patch: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        text="",
        input_tokens=10,
        output_tokens=20,
        structured={"patches": [patch]},
    )


class TestPatchTargetResolver:
    @pytest.mark.parametrize(
        ("raw", "reason"),
        [
            ("", "empty"),
            (" nested/file.go", "not_normalized"),
            ("nested/file.go ", "not_normalized"),
            ("nested\nfile.go", "control_character"),
            ("/tmp/file.go", "absolute"),
            ("C:\\tmp\\file.go", "absolute"),
            ("C:file.go", "absolute"),
            ("\\\\server\\share\\file.go", "absolute"),
            ("nested\\file.go", "non_portable_separator"),
            ("../file.go", "traversal"),
            ("nested/../../file.go", "traversal"),
            (".git/config", "git_control_plane"),
            ("nested/.GIT/HEAD", "git_control_plane"),
            ("nested//file.go", "not_normalized"),
            ("nested/./file.go", "not_normalized"),
            (".", "project_root"),
        ],
    )
    def test_rejects_non_portable_or_escaping_targets(
        self, tmp_path: Path, raw: str, reason: str
    ) -> None:
        target, actual_reason = resolve_patch_target(tmp_path, raw)

        assert target is None
        assert actual_reason == reason

    def test_resolves_nested_target_inside_project(self, tmp_path: Path) -> None:
        target, rejection = resolve_patch_target(tmp_path, "nested/new.go")

        assert rejection is None
        assert target is not None
        assert target.path == tmp_path / "nested/new.go"
        assert target.relative == "nested/new.go"

    def test_rejects_symlink_escape(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir()
        (tmp_path / "escape").symlink_to(outside, target_is_directory=True)

        target, rejection = resolve_patch_target(tmp_path, "escape/file.go")

        assert target is None
        assert rejection == "outside_project"

    def test_canonicalizes_symlink_that_stays_inside_project(self, tmp_path: Path) -> None:
        actual = tmp_path / "actual"
        actual.mkdir()
        (tmp_path / "alias").symlink_to(actual, target_is_directory=True)

        target, rejection = resolve_patch_target(tmp_path, "alias/file.go")

        assert rejection is None
        assert target is not None
        assert target.path == actual / "file.go"
        assert target.relative == "actual/file.go"

    def test_rejects_discovered_internal_git_admin_path(self, tmp_path: Path) -> None:
        admin = tmp_path / "repository-admin"
        admin.mkdir()

        target, rejection = resolve_patch_target(
            tmp_path,
            "repository-admin/config",
            git_control_paths=(admin,),
        )

        assert target is None
        assert rejection == "git_control_plane"


@pytest.mark.parametrize("structured", [False, True], ids=["text", "structured"])
class TestLoopRejectsUnsafePatchTargets:
    def test_rejects_write_traversal_without_outside_mutation(
        self, tmp_path: Path, structured: bool
    ) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-escaped.ts"
        outside.unlink(missing_ok=True)
        response = (
            _structured_response(
                {"file": f"../{outside.name}", "type": "write", "write": "changed\n"}
            )
            if structured
            else _text_response(f"## WRITE: ../{outside.name}\nchanged\n## END_WRITE")
        )

        result = run_llm_loop(_Responses([response]), "impl", tmp_path)

        assert result["success"] is False
        assert result["reason"] == "unsafe_patch_target"
        assert result["failures"] == ["patch_target_rejected:traversal"]
        assert result["diagnostic"]["rejection_codes"] == ["traversal"]
        assert result["rollback"]["status"] == "not_needed"
        assert not outside.exists()
        assert str(outside) not in repr(result)

    def test_rejects_absolute_search_replace_without_outside_mutation(
        self, tmp_path: Path, structured: bool
    ) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-absolute.txt"
        outside.write_text("before\n", encoding="utf-8")
        response = (
            _structured_response(
                {
                    "file": str(outside),
                    "type": "search_replace",
                    "search": "before",
                    "replace": "after",
                }
            )
            if structured
            else _text_response(
                f"## {outside}\n<<<<<<< SEARCH\nbefore\n=======\nafter\n>>>>>>> REPLACE"
            )
        )

        result = run_llm_loop(_Responses([response]), "impl", tmp_path)

        assert result["reason"] == "unsafe_patch_target"
        assert result["failures"] == ["patch_target_rejected:absolute"]
        assert outside.read_text(encoding="utf-8") == "before\n"
        assert str(outside) not in repr(result)

    def test_rejects_replace_lines_through_escaping_symlink(
        self, tmp_path: Path, structured: bool
    ) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-symlink.go"
        outside.write_text("package before\n", encoding="utf-8")
        (tmp_path / "linked.go").symlink_to(outside)
        response = (
            _structured_response(
                {
                    "file": "linked.go",
                    "type": "replace_lines",
                    "lines": [1, 1],
                    "replace": "package after",
                }
            )
            if structured
            else _text_response("## linked.go\nREPLACE LINES 1-1\npackage after\nEND REPLACE")
        )

        result = run_llm_loop(_Responses([response]), "impl", tmp_path)

        assert result["reason"] == "unsafe_patch_target"
        assert result["failures"] == ["patch_target_rejected:outside_project"]
        assert outside.read_text(encoding="utf-8") == "package before\n"


def test_loop_validates_every_target_before_first_write(tmp_path: Path) -> None:
    safe = tmp_path / "safe.go"
    safe.write_text("package safe\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-mixed.go"
    outside.unlink(missing_ok=True)
    response = _text_response(
        "## safe.go\n"
        "<<<<<<< SEARCH\npackage safe\n=======\npackage changed\n>>>>>>> REPLACE\n"
        f"## WRITE: ../{outside.name}\noutside\n## END_WRITE"
    )

    result = run_llm_loop(_Responses([response]), "impl", tmp_path)

    assert result["reason"] == "unsafe_patch_target"
    assert safe.read_text(encoding="utf-8") == "package safe\n"
    assert not outside.exists()
    assert result["rounds_stats"][0]["applied"] == 0


def test_unsafe_later_round_rolls_back_previous_progress(tmp_path: Path) -> None:
    target = tmp_path / "existing.go"
    target.write_text("package before\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-later.go"
    outside.unlink(missing_ok=True)
    first = _text_response(
        "## existing.go\n"
        "<<<<<<< SEARCH\npackage before\n=======\npackage after\n>>>>>>> REPLACE\n"
        "## missing.go\n"
        "<<<<<<< SEARCH\nmissing\n=======\nreplacement\n>>>>>>> REPLACE"
    )
    second = _text_response(f"## WRITE: ../{outside.name}\noutside\n## END_WRITE")

    result = run_llm_loop(_Responses([first, second]), "impl", tmp_path)

    assert result["reason"] == "unsafe_patch_target"
    assert result["patches_applied"] == []
    assert result["patches_rolled_back"] == 1
    assert result["rollback"]["status"] == "completed"
    assert target.read_text(encoding="utf-8") == "package before\n"
    assert not outside.exists()


def test_loop_allows_nested_non_python_file(tmp_path: Path) -> None:
    response = _text_response("## WRITE: nested/new.go\npackage nested\n## END_WRITE")

    result = run_llm_loop(_Responses([response]), "impl", tmp_path)

    assert result["success"] is True
    assert (tmp_path / "nested/new.go").read_text(encoding="utf-8") == "package nested\n"
    assert result["patches_applied"][0]["file"] == "nested/new.go"


def test_loop_uses_canonical_in_root_symlink_target(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    target = actual / "module.go"
    target.write_text("package before\n", encoding="utf-8")
    (tmp_path / "alias").symlink_to(actual, target_is_directory=True)
    response = _text_response(
        "## alias/module.go\n"
        "<<<<<<< SEARCH\npackage before\n=======\npackage after\n>>>>>>> REPLACE"
    )

    result = run_llm_loop(_Responses([response]), "impl", tmp_path)

    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "package after\n"
    assert result["patches_applied"][0]["file"] == "actual/module.go"


@pytest.mark.parametrize(
    ("target_name", "response"),
    [
        (
            ".git/config",
            "## .git/config\n<<<<<<< SEARCH\nbefore\n=======\nafter\n>>>>>>> REPLACE",
        ),
        (
            ".git/HEAD",
            "## WRITE: .git/HEAD\nrefs/heads/attacker\n## END_WRITE",
        ),
        (
            ".git/hooks/pre-commit",
            "## .git/hooks/pre-commit\nREPLACE LINES 1-1\necho attacker\nEND REPLACE",
        ),
        (
            "vendor/.git",
            "## WRITE: vendor/.git\ngitdir: /attacker\n## END_WRITE",
        ),
    ],
)
def test_loop_keeps_git_metadata_byte_exact(
    tmp_path: Path, target_name: str, response: str
) -> None:
    target = tmp_path / target_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"before\n")
    before = target.read_bytes()

    result = run_llm_loop(_Responses([_text_response(response)]), "impl", tmp_path)

    assert result["reason"] == "unsafe_patch_target"
    assert result["failures"] == ["patch_target_rejected:git_control_plane"]
    assert result["diagnostic"]["rejection_codes"] == ["git_control_plane"]
    assert target.read_bytes() == before
    assert target_name not in repr(result)


def test_linked_external_git_dir_and_marker_stay_byte_exact(tmp_path: Path) -> None:
    external_git_dir = tmp_path.parent / f"{tmp_path.name}-gitdir"
    subprocess.run(
        ["git", "init", "-q", "--separate-git-dir", str(external_git_dir), str(tmp_path)],
        check=True,
    )
    marker = tmp_path / ".git"
    config = external_git_dir / "config"
    marker_before = marker.read_bytes()
    config_before = config.read_bytes()

    result = run_llm_loop(
        _Responses([_text_response("## WRITE: .git\ngitdir: /attacker\n## END_WRITE")]),
        "impl",
        tmp_path,
    )

    assert result["reason"] == "unsafe_patch_target"
    assert marker.read_bytes() == marker_before
    assert config.read_bytes() == config_before


def test_effective_internal_separate_git_dir_is_protected(tmp_path: Path) -> None:
    admin = tmp_path / "repository-admin"
    subprocess.run(
        ["git", "init", "-q", "--separate-git-dir", str(admin), str(tmp_path)],
        check=True,
    )
    config = admin / "config"
    before = config.read_bytes()
    response = _structured_response(
        {
            "file": "repository-admin/config",
            "type": "search_replace",
            "search": "[core]",
            "replace": "[attacker]",
        }
    )

    result = run_llm_loop(_Responses([response]), "impl", tmp_path)

    assert result["reason"] == "unsafe_patch_target"
    assert result["failures"] == ["patch_target_rejected:git_control_plane"]
    assert config.read_bytes() == before


def test_normal_dotfile_remains_patchable(tmp_path: Path) -> None:
    response = _text_response(
        "## WRITE: .editorconfig\nroot = true\n[*]\ncharset = utf-8\n## END_WRITE"
    )

    result = run_llm_loop(_Responses([response]), "impl", tmp_path)

    assert result["success"] is True
    assert (tmp_path / ".editorconfig").read_text(encoding="utf-8") == (
        "root = true\n[*]\ncharset = utf-8\n"
    )
