"""#270: Tests fuer die LLM-Code-Kennzeichnung im Shared Kernel."""

from __future__ import annotations

from samuel.core.attribution import (
    ai_attribution_trailer,
    comment_prefix,
    commit_trailers,
    decorate_patch,
    mark_content,
    marker_text,
)


class TestCommentPrefix:
    def test_known_extensions(self):
        assert comment_prefix(".py") == "#"
        assert comment_prefix(".js") == "//"
        assert comment_prefix(".sql") == "--"
        assert comment_prefix(".YAML") == "#"  # case-insensitive

    def test_unknown_extension_returns_none(self):
        assert comment_prefix(".html") is None
        assert comment_prefix(".css") is None
        assert comment_prefix("") is None
        assert comment_prefix(".unknown") is None


class TestMarkerText:
    def test_minimal(self):
        assert marker_text("deepseek", date="2026-05-29") == "llm: deepseek 2026-05-29"

    def test_full_adds_version_and_issue(self):
        txt = marker_text(
            "deepseek",
            date="2026-05-29",
            verbosity="full",
            version="v2",
            issue=270,
        )
        assert txt == "llm: deepseek@v2 2026-05-29 (#270)"

    def test_minimal_ignores_version_and_issue(self):
        txt = marker_text(
            "deepseek",
            date="2026-05-29",
            version="v2",
            issue=270,
        )
        assert txt == "llm: deepseek 2026-05-29"


class TestMarkContent:
    def test_single_marker_at_top(self):
        out = mark_content("print(1)", prefix="#", text="llm: x 2026")
        assert out == "# llm: x 2026\nprint(1)"

    def test_marker_after_shebang(self):
        out = mark_content("#!/usr/bin/env python\nprint(1)", prefix="#", text="llm: x 2026")
        lines = out.split("\n")
        assert lines[0] == "#!/usr/bin/env python"
        assert lines[1] == "# llm: x 2026"

    def test_marker_after_coding_line(self):
        out = mark_content("# -*- coding: utf-8 -*-\nx=1", prefix="#", text="llm: x 2026")
        lines = out.split("\n")
        assert "coding:" in lines[0]
        assert lines[1] == "# llm: x 2026"

    def test_idempotent(self):
        first = mark_content("print(1)", prefix="#", text="llm: x 2026")
        second = mark_content(first, prefix="#", text="llm: y 2027")
        assert second == first  # no second marker added

    def test_indentation_follows_block_head(self):
        out = mark_content("    return 1", prefix="#", text="llm: x 2026")
        assert out == "    # llm: x 2026\n    return 1"


class TestDecoratePatch:
    def test_write_patch_marked(self):
        p = {"file": "new.py", "type": "write", "write": "print(1)\n"}
        out = decorate_patch(p, model="deepseek", date="2026-05-29")
        assert out["write"].startswith("# llm: deepseek 2026-05-29\n")
        assert p["write"] == "print(1)\n"  # original untouched

    def test_search_replace_patch_marked(self):
        p = {"file": "a.py", "search": "old", "replace": "new_code"}
        out = decorate_patch(p, model="m", date="2026")
        assert out["replace"] == "# llm: m 2026\nnew_code"

    def test_replace_lines_patch_marked(self):
        p = {"file": "a.js", "type": "replace_lines", "lines": (1, 2), "replace": "const x=1;"}
        out = decorate_patch(p, model="m", date="2026")
        assert out["replace"] == "// llm: m 2026\nconst x=1;"

    def test_unknown_extension_unchanged(self):
        p = {"file": "page.html", "type": "write", "write": "<div></div>"}
        out = decorate_patch(p, model="m", date="2026")
        assert out is p

    def test_no_double_marking(self):
        p = {"file": "a.py", "search": "old", "replace": "x=1"}
        once = decorate_patch(p, model="m", date="2026")
        twice = decorate_patch(once, model="other", date="2099")
        assert twice["replace"] == once["replace"]


class TestCommitTrailers:
    def test_ai_generated_by_always_present(self):
        out = commit_trailers(
            model="deepseek",
            system_version="2.0.0a0",
            build_revision="a" * 40,
            external_visible=False,
        )
        assert "AI-Generated-By: S.A.M.U.E.L.@2.0.0a0" in out
        assert f"SAMUEL-Build-Revision: {'a' * 40}" in out
        assert "Co-Authored-By" not in out

    def test_co_authored_by_when_external_and_model(self):
        out = commit_trailers(
            model="deepseek",
            system_version="2.0.0a0",
            external_visible=True,
            co_author_email="bot@x.dev",
        )
        assert "AI-Generated-By: S.A.M.U.E.L.@2.0.0a0" in out
        assert "Co-Authored-By: deepseek <bot@x.dev>" in out

    def test_no_co_author_without_model(self):
        out = commit_trailers(model="", system_version="2.0.0a0", external_visible=True)
        assert "Co-Authored-By" not in out

    def test_dirty_build_is_explicit(self):
        out = commit_trailers(
            system_version="2.0.0a0",
            build_revision="b" * 40,
            build_dirty=True,
        )
        assert "SAMUEL-Build-Dirty: true" in out

    def test_ai_attribution_trailer_format(self):
        assert ai_attribution_trailer("m", "v2") == "AI-Generated-By: m@v2"
        assert ai_attribution_trailer("m") == "AI-Generated-By: m"
