from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from samuel.adapters.quality.checks import (
    DiffSizeCheck,
    PythonSyntaxCheck,
    ScopeGuard,
    TreeSitterTypeScriptCheck,
)
from samuel.adapters.quality.registry import (
    QUALITY_CHECKS,
    get_all_unique_checks,
    get_checks_for,
    load_registry_from_config,
    register_check,
)


class TestPythonSyntaxCheck:
    def test_valid_python(self, tmp_path: Path):
        f = tmp_path / "good.py"
        f.write_text("def hello():\n    return 42\n")

        check = PythonSyntaxCheck()
        result = check.run(f, f.read_text(), {})

        assert result["passed"] is True

    def test_invalid_python(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("def hello(\n")

        check = PythonSyntaxCheck()
        result = check.run(f, f.read_text(), {})

        assert result["passed"] is False
        assert "SyntaxError" in result["reason"]

    def test_supported_extensions(self):
        assert PythonSyntaxCheck().supported_extensions == {".py"}


class TestTreeSitterTypeScriptCheck:
    def test_valid_typescript(self, tmp_path: Path):
        f = tmp_path / "good.ts"
        f.write_text("function hello(): number { return 42; }\n")

        check = TreeSitterTypeScriptCheck()
        result = check.run(f, f.read_text(), {})

        assert result["passed"] is True
        if result.get("status") == "not_applicable":
            assert "not installed" in result["reason"]

    def test_invalid_typescript(self, tmp_path: Path):
        f = tmp_path / "bad.ts"
        f.write_text("function hello( { return; }\n")

        check = TreeSitterTypeScriptCheck()
        result = check.run(f, f.read_text(), {})

        if result.get("status") == "not_applicable":
            assert result["passed"] is True
            assert "not installed" in result["reason"]
            return
        assert result["passed"] is False

    def test_supported_extensions(self):
        check = TreeSitterTypeScriptCheck()
        assert ".ts" in check.supported_extensions
        assert ".tsx" in check.supported_extensions
        assert ".js" in check.supported_extensions

    def test_missing_optional_parser_is_explicitly_not_applicable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        original_import = builtins.__import__

        def import_without_tree_sitter(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "tree_sitter":
                raise ImportError("not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", import_without_tree_sitter)
        file = tmp_path / "candidate.ts"
        file.write_text("invalid(")

        result = TreeSitterTypeScriptCheck().run(file, file.read_text(), {})

        assert result == {
            "passed": True,
            "status": "not_applicable",
            "reason": "tree-sitter parser not installed",
        }


class TestScopeGuard:
    def test_clean_code(self, tmp_path: Path):
        f = tmp_path / "clean.py"
        content = "import os\nresult = os.path.join('a', 'b')\n"
        f.write_text(content)

        result = ScopeGuard().run(f, content, {})

        assert result["passed"] is True

    def test_dangerous_os_system(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        content = "import os\nos.system('rm -rf /')\n"
        f.write_text(content)

        result = ScopeGuard().run(f, content, {})

        assert result["passed"] is False
        assert len(result["violations"]) >= 1

    def test_dangerous_eval(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        content = "x = eval(input())\n"
        f.write_text(content)

        result = ScopeGuard().run(f, content, {})

        assert result["passed"] is False

    def test_wildcard_extension(self):
        assert ScopeGuard().supported_extensions == {"*"}


class TestDiffSizeCheck:
    def test_small_file(self, tmp_path: Path):
        f = tmp_path / "small.py"
        content = "x = 1\n" * 100
        f.write_text(content)

        result = DiffSizeCheck().run(f, content, {})

        assert result["passed"] is True

    def test_large_file(self, tmp_path: Path):
        f = tmp_path / "huge.py"
        content = "x = 1\n" * 6000
        f.write_text(content)

        result = DiffSizeCheck().run(f, content, {})

        assert result["passed"] is False


class TestRegistry:
    def test_load_defaults(self):
        load_registry_from_config()

        py_checks = get_checks_for(".py")
        assert len(py_checks) >= 2

        ts_checks = get_checks_for(".ts")
        assert len(ts_checks) >= 2

    def test_wildcard_included(self):
        load_registry_from_config()

        unknown = get_checks_for(".unknown")
        assert len(unknown) >= 1

    def test_register_custom_check(self):
        QUALITY_CHECKS.clear()

        class CustomCheck:
            supported_extensions = {".custom"}

            def run(self, file, content, skeleton):
                return {"passed": True}

        register_check(CustomCheck())
        checks = get_checks_for(".custom")
        assert len(checks) == 1

    def test_config_override_disabled(self, tmp_path: Path):
        config = tmp_path / "hooks.json"
        config.write_text('{"quality_checks": {"disabled": [".ts", ".tsx"]}}')

        load_registry_from_config(config)

        ts_checks = get_checks_for(".ts")
        wildcard_only = all("*" in c.supported_extensions for c in ts_checks)
        assert wildcard_only or len(ts_checks) == len(get_checks_for(".unknown"))

    def test_get_all_unique_checks_after_load(self):
        QUALITY_CHECKS.clear()
        load_registry_from_config()

        unique = get_all_unique_checks()
        classes = [type(c) for c in unique]
        assert len(unique) == len({id(check) for check in unique}) == 6
        names = {c.__name__ for c in classes}
        assert "PythonSyntaxCheck" in names
        assert "DiffSizeCheck" in names
        assert "ScopeGuard" in names

    def test_extensions_mapping_is_effective(self, tmp_path: Path):
        config = tmp_path / "hooks.json"
        config.write_text(
            '{"quality_checks":{"disabled":[],"extensions":'
            '{".py":["PythonSyntaxCheck"],"*":["ScopeGuard"]}}}'
        )
        load_registry_from_config(config)
        assert [type(check).__name__ for check in get_checks_for(".py")] == [
            "PythonSyntaxCheck",
            "ScopeGuard",
        ]
        assert [type(check).__name__ for check in get_checks_for(".ts")] == ["ScopeGuard"]

    @pytest.mark.parametrize(
        ("document", "message"),
        [
            (
                '{"quality_checks":{"extensions":{".py":["ImaginaryLintCheck"]}}}',
                "unknown quality check",
            ),
            (
                '{"quality_checks":{"extensions":{".py":["TreeSitterTypeScriptCheck"]}}}',
                "does not support",
            ),
            ("{", "invalid quality config"),
        ],
    )
    def test_invalid_configuration_is_rejected(self, tmp_path: Path, document: str, message: str):
        config = tmp_path / "hooks.json"
        config.write_text(document)
        with pytest.raises(ValueError, match=message):
            load_registry_from_config(config)
