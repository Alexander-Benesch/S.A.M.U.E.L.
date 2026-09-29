from __future__ import annotations

from pathlib import Path

import pytest

from samuel.slices.implementation.patch_parser import (
    JSONPatchApplier,
    LinePatchApplier,
    YAMLPatchApplier,
    get_applier,
    parse_patches,
    parse_slice_requests,
)


class TestParseSliceRequests:
    """#152: SLICE: rel:start-end aus LLM-Output."""

    def test_parses_multiple(self):
        text = "Erst SLICE: a/b.py:100-200 und dann SLICE: c.py:5 - 9 bitte"
        assert parse_slice_requests(text) == [("a/b.py", 100, 200), ("c.py", 5, 9)]

    def test_dedupes(self):
        assert parse_slice_requests("SLICE: x.py:1-5 SLICE: x.py:1-5") == [("x.py", 1, 5)]

    def test_skips_inverted_range(self):
        assert parse_slice_requests("SLICE: x.py:20-10") == []

    def test_empty_when_none(self):
        assert parse_slice_requests("normaler Text ohne Slice") == []
        assert parse_slice_requests("") == []


class TestParsePatches:
    def test_search_replace(self):
        text = "## handler.py\n<<<<<<< SEARCH\nold code\n=======\nnew code\n>>>>>>> REPLACE\n"
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["file"] == "handler.py"
        assert patches[0]["search"] == "old code"
        assert patches[0]["replace"] == "new code"

    def test_replace_lines(self):
        text = "## handler.py\nREPLACE LINES 10-25\nnew line 1\nnew line 2\nEND REPLACE\n"
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["type"] == "replace_lines"
        assert patches[0]["lines"] == (10, 25)
        assert patches[0]["replace"] == "new line 1\nnew line 2"

    def test_write_block(self):
        text = "## WRITE: docs/readme.md\n# Title\nContent here\n## END_WRITE\n"
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["type"] == "write"
        assert patches[0]["file"] == "docs/readme.md"
        assert patches[0]["write"] == "# Title\nContent here"

    def test_multiple_patches(self):
        text = (
            "## a.py\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "## b.py\n"
            "<<<<<<< SEARCH\n"
            "x\n"
            "=======\n"
            "y\n"
            ">>>>>>> REPLACE\n"
        )
        patches = parse_patches(text)
        assert len(patches) == 2
        assert patches[0]["file"] == "a.py"
        assert patches[1]["file"] == "b.py"

    def test_empty_text(self):
        assert parse_patches("") == []

    def test_no_patches_in_text(self):
        assert parse_patches("just some text without patches") == []

    def test_incomplete_write_block(self):
        text = "## WRITE: docs/readme.md\ncontent without end marker\n"
        patches = parse_patches(text)
        assert len(patches) == 1
        assert patches[0]["type"] == "write"


class TestLinePatchApplier:
    def test_search_replace_apply(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\nold_var = 2\ny = 3\n")
        applier = LinePatchApplier()
        results = applier.apply(
            f, [{"file": "test.py", "search": "old_var = 2", "replace": "new_var = 2"}]
        )
        assert results[0][0] is True
        assert "new_var = 2" in f.read_text()

    def test_replace_lines_apply(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("a = 1\nb = 2\nc = 3\nd = 4\n")
        applier = LinePatchApplier()
        results = applier.apply(
            f,
            [
                {
                    "file": "test.py",
                    "type": "replace_lines",
                    "lines": (2, 3),
                    "replace": "replaced = 99",
                }
            ],
        )
        assert results[0][0] is True
        content = f.read_text()
        assert "replaced = 99" in content
        assert "b = 2" not in content

    def test_write_apply(self, tmp_path: Path):
        f = tmp_path / "new.md"
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "new.md", "type": "write", "write": "hello"}])
        assert results[0][0] is True
        assert f.read_text().strip() == "hello"

    def test_invalid_python_write_preserves_existing_file_and_metadata(self, tmp_path: Path):
        target = tmp_path / "module.py"
        target.write_text("value = 1\n", encoding="utf-8")
        before = (
            target.read_bytes(),
            target.stat().st_ino,
            target.stat().st_mode,
            target.stat().st_size,
            target.stat().st_mtime_ns,
        )

        result = LinePatchApplier().apply(
            target,
            [{"file": "module.py", "type": "write", "write": "def ("}],
        )

        after = (
            target.read_bytes(),
            target.stat().st_ino,
            target.stat().st_mode,
            target.stat().st_size,
            target.stat().st_mtime_ns,
        )
        assert result == [(False, "validation failed for module.py")]
        assert after == before

    def test_invalid_new_python_write_creates_neither_file_nor_parent(self, tmp_path: Path):
        target = tmp_path / "new" / "module.py"

        result = LinePatchApplier().apply(
            target,
            [{"file": "new/module.py", "type": "write", "write": "def ("}],
        )

        assert result == [(False, "validation failed for new/module.py")]
        assert not target.exists()
        assert not target.parent.exists()

    @pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
    def test_valid_python_write_is_applied(self, tmp_path: Path, existing: bool):
        target = tmp_path / "module.py"
        if existing:
            target.write_text("value = 1\n", encoding="utf-8")

        result = LinePatchApplier().apply(
            target,
            [{"file": "module.py", "type": "write", "write": "value = 2"}],
        )

        assert result == [(True, "module.py written")]
        assert target.read_text(encoding="utf-8") == "value = 2\n"

    def test_syntax_error_rejected(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("x = 1\n")
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "bad.py", "search": "x = 1", "replace": "def ("}])
        assert results[0][0] is False

    def test_search_not_found(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        applier = LinePatchApplier()
        results = applier.apply(
            f, [{"file": "test.py", "search": "nonexistent", "replace": "y = 2"}]
        )
        assert results[0][0] is False

    def test_line_range_out_of_bounds(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\ny = 2\n")
        applier = LinePatchApplier()
        results = applier.apply(
            f,
            [
                {
                    "file": "test.py",
                    "type": "replace_lines",
                    "lines": (1, 10),
                    "replace": "x",
                }
            ],
        )
        assert results[0][0] is False

    def test_file_not_found(self, tmp_path: Path):
        f = tmp_path / "missing.py"
        applier = LinePatchApplier()
        results = applier.apply(f, [{"file": "missing.py", "search": "x", "replace": "y"}])
        assert results[0][0] is False


class TestJSONPatchApplier:
    def test_valid_json_write(self, tmp_path: Path):
        f = tmp_path / "config.json"
        applier = JSONPatchApplier()
        results = applier.apply(
            f, [{"file": "config.json", "type": "write", "write": '{"key": "val"}'}]
        )
        assert results[0][0] is True

    def test_invalid_json_rejected(self, tmp_path: Path):
        f = tmp_path / "config.json"
        applier = JSONPatchApplier()
        results = applier.apply(
            f, [{"file": "config.json", "type": "write", "write": "{invalid json"}]
        )
        assert results[0][0] is False

    def test_validate_method(self, tmp_path: Path):
        applier = JSONPatchApplier()
        assert applier.validate(tmp_path / "x.json", '{"a": 1}') is True
        assert applier.validate(tmp_path / "x.json", "not json") is False

    @pytest.mark.parametrize(
        "patch",
        [
            {"file": "config.json", "search": '"ok": true', "replace": "not-json"},
            {
                "file": "config.json",
                "type": "replace_lines",
                "lines": (1, 1),
                "replace": "{not-json}",
            },
        ],
        ids=["search-replace", "replace-lines"],
    )
    def test_invalid_existing_patch_preserves_content_and_metadata(
        self, tmp_path: Path, patch: dict
    ):
        f = tmp_path / "config.json"
        f.write_text('{"ok": true}\n', encoding="utf-8")
        before = (
            f.read_bytes(),
            f.stat().st_ino,
            f.stat().st_mode,
            f.stat().st_size,
            f.stat().st_mtime_ns,
        )

        result = JSONPatchApplier().apply(f, [patch])

        after = (
            f.read_bytes(),
            f.stat().st_ino,
            f.stat().st_mode,
            f.stat().st_size,
            f.stat().st_mtime_ns,
        )
        assert result == [(False, "config.json invalid JSON after patch")]
        assert after == before

    @pytest.mark.parametrize(
        ("patch", "expected"),
        [
            (
                {"file": "config.json", "search": "true", "replace": "false"},
                '{"ok": false}',
            ),
            (
                {
                    "file": "config.json",
                    "type": "replace_lines",
                    "lines": (1, 1),
                    "replace": '{"ok": false}',
                },
                '{"ok": false}\n',
            ),
        ],
        ids=["search-replace", "replace-lines"],
    )
    def test_valid_existing_patch_is_applied(self, tmp_path: Path, patch: dict, expected: str):
        f = tmp_path / "config.json"
        f.write_text('{"ok": true}\n', encoding="utf-8")

        result = JSONPatchApplier().apply(f, [patch])

        assert result == [(True, "config.json patched")]
        assert f.read_text(encoding="utf-8") == expected

    def test_valid_write_replaces_existing_json(self, tmp_path: Path):
        f = tmp_path / "config.json"
        f.write_text('{"before": true}\n', encoding="utf-8")

        result = JSONPatchApplier().apply(
            f,
            [{"file": "config.json", "type": "write", "write": '{"after": true}'}],
        )

        assert result == [(True, "config.json written")]
        assert f.read_text(encoding="utf-8") == '{"after": true}'


@pytest.mark.parametrize(
    ("suffix", "patch"),
    [
        (".txt", {"file": "target.txt", "search": "absent", "replace": "changed"}),
        (
            ".py",
            {"file": "target.py", "search": "value = 1", "replace": "def ("},
        ),
        (
            ".yaml",
            {
                "file": "target.yaml",
                "type": "replace_lines",
                "lines": (1, 5),
                "replace": "changed: true",
            },
        ),
    ],
    ids=["line-search", "python-validation", "yaml-range"],
)
def test_other_applier_failures_do_not_mutate(tmp_path: Path, suffix: str, patch: dict):
    target = tmp_path / f"target{suffix}"
    target.write_text("value = 1\n", encoding="utf-8")
    before = (target.read_bytes(), target.stat().st_mode, target.stat().st_mtime_ns)

    result = get_applier(target).apply(target, [patch])

    after = (target.read_bytes(), target.stat().st_mode, target.stat().st_mtime_ns)
    assert result[0][0] is False
    assert after == before


class TestRegistry:
    def test_python_gets_line_applier(self):
        assert isinstance(get_applier(Path("test.py")), LinePatchApplier)

    def test_json_gets_json_applier(self):
        assert isinstance(get_applier(Path("config.json")), JSONPatchApplier)

    def test_yaml_gets_yaml_applier(self):
        assert isinstance(get_applier(Path("config.yaml")), YAMLPatchApplier)
        assert isinstance(get_applier(Path("config.yml")), YAMLPatchApplier)

    def test_unknown_gets_fallback(self):
        assert isinstance(get_applier(Path("file.txt")), LinePatchApplier)


# --- #335: structured-mode (JSON-Array von Patches) ----------------------


def test_structured_search_replace():
    from samuel.slices.implementation.patch_parser import parse_patches_structured

    data = {"patches": [{"file": "a.py", "search": "old", "replace": "new"}]}
    out = parse_patches_structured(data)
    assert out == [{"file": "a.py", "search": "old", "replace": "new"}]


def test_structured_replace_lines_and_write():
    from samuel.slices.implementation.patch_parser import parse_patches_structured

    data = {
        "patches": [
            {"file": "a.py", "type": "replace_lines", "lines": [10, 20], "replace": "code"},
            {"file": "b.py", "type": "write", "write": "full"},
        ]
    }
    out = parse_patches_structured(data)
    assert out[0] == {"file": "a.py", "lines": (10, 20), "replace": "code", "type": "replace_lines"}
    assert out[1] == {"file": "b.py", "write": "full", "type": "write"}


def test_structured_accepts_bare_list():
    from samuel.slices.implementation.patch_parser import parse_patches_structured

    out = parse_patches_structured([{"file": "a.py", "search": "x", "replace": "y"}])
    assert len(out) == 1


def test_structured_skips_invalid_items():
    from samuel.slices.implementation.patch_parser import parse_patches_structured

    data = {
        "patches": [
            {"type": "write"},  # kein file
            {"file": "a.py", "type": "replace_lines", "lines": [1]},  # lines unvollstaendig
            {"file": "ok.py", "write": "x", "type": "write"},
        ]
    }
    out = parse_patches_structured(data)
    assert out == [{"file": "ok.py", "write": "x", "type": "write"}]


def test_structured_non_dict_non_list_returns_empty():
    from samuel.slices.implementation.patch_parser import parse_patches_structured

    assert parse_patches_structured("nope") == []
    assert parse_patches_structured(None) == []
