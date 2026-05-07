"""#301: Tests for the system-prompt loader."""
from __future__ import annotations

from pathlib import Path

from samuel.adapters.llm.prompts import load_system_prompt


def test_load_system_prompt_from_package():
    text = load_system_prompt("senior_python.md")
    assert "Rolle" in text or "Python" in text
    assert len(text) > 100


def test_load_system_prompt_operator_override(tmp_path):
    prompts_dir = tmp_path / "llm" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "custom.md").write_text("# CUSTOM PROMPT\nFor operator override test.", encoding="utf-8")

    text = load_system_prompt("custom.md", config_dir=str(tmp_path))
    assert "CUSTOM PROMPT" in text


def test_load_system_prompt_operator_overrides_package(tmp_path):
    """Operator file with same name as package file wins."""
    prompts_dir = tmp_path / "llm" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "planner.md").write_text("OPERATOR PLANNER", encoding="utf-8")

    text = load_system_prompt("planner.md", config_dir=str(tmp_path))
    assert text == "OPERATOR PLANNER"


def test_load_system_prompt_missing_returns_empty():
    text = load_system_prompt("nonexistent_xyz.md")
    assert text == ""


def test_load_system_prompt_empty_name_returns_empty():
    assert load_system_prompt("") == ""
    assert load_system_prompt(None) == ""


# #315: list_available_prompts + write_prompt
class TestListAvailablePrompts:
    def test_list_available_prompts_includes_package_and_operator(self, tmp_path):
        """#315-AC: name matches issue-body anchor for AC-Verifier."""
        from samuel.adapters.llm.prompts import list_available_prompts

        prompts_dir = tmp_path / "llm" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "custom_op.md").write_text("OP PROMPT", encoding="utf-8")
        (prompts_dir / "planner.md").write_text("OVERRIDE PLANNER", encoding="utf-8")

        rows = list_available_prompts(config_dir=str(tmp_path))
        names = {r["name"]: r for r in rows}
        # Package defaults present
        assert "senior_python.md" in names
        assert names["senior_python.md"]["source"] == "package"
        # Operator-only file present
        assert "custom_op.md" in names
        assert names["custom_op.md"]["source"] == "operator"
        # Override wins for shared name
        assert names["planner.md"]["source"] == "operator"
        # Sorted by name
        sorted_names = sorted(r["name"] for r in rows)
        assert [r["name"] for r in rows] == sorted_names

    def test_list_available_prompts_no_operator_dir(self, tmp_path):
        """Without operator dir: only package defaults."""
        from samuel.adapters.llm.prompts import list_available_prompts
        rows = list_available_prompts(config_dir=str(tmp_path))
        names = {r["name"] for r in rows}
        assert "senior_python.md" in names
        for r in rows:
            assert r["source"] == "package"

    def test_list_available_prompts_size_field(self, tmp_path):
        from samuel.adapters.llm.prompts import list_available_prompts
        rows = list_available_prompts(config_dir=str(tmp_path))
        for r in rows:
            assert isinstance(r["size"], int) and r["size"] > 0


class TestWritePrompt:
    def _activate_premium(self, monkeypatch):
        from samuel.core import license as _lic
        fake = _lic.License(
            email="t@x", features=frozenset({"llm_routing_dashboard_write"}),
            issued_at="2026-05-05T12:00:00Z",
        )
        monkeypatch.setattr(_lic, "_LICENSE", fake)

    def test_write_prompt_premium_blocks_in_free_mode(self, tmp_path, monkeypatch):
        """#315-AC: name matches issue-body anchor."""
        from samuel.adapters.llm.prompts import write_prompt
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "_LICENSE", None)
        res = write_prompt("planner.md", "x", config_dir=str(tmp_path))
        assert res["saved"] is False
        assert "premium" in res["error"]

    def test_write_prompt_atomic(self, tmp_path, monkeypatch):
        """#315-AC: atomic write via tmp+rename."""
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        res = write_prompt("planner.md", "OVERRIDE CONTENT", config_dir=str(tmp_path))
        assert res["saved"] is True
        fp = tmp_path / "llm" / "prompts" / "planner.md"
        assert fp.exists()
        assert fp.read_text(encoding="utf-8") == "OVERRIDE CONTENT"
        # No leftover .tmp file
        assert not fp.with_suffix(".tmp").exists()

    def test_write_prompt_rejects_non_md_name(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        res = write_prompt("script.py", "x", config_dir=str(tmp_path))
        assert res["saved"] is False
        assert ".md" in res["error"]

    def test_write_prompt_rejects_path_traversal(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        for bad in ("../escape.md", "sub/dir.md", "..\\win.md"):
            res = write_prompt(bad, "x", config_dir=str(tmp_path))
            assert res["saved"] is False
            assert "invalid characters" in res["error"]

    def test_write_prompt_rejects_empty_content(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        res = write_prompt("planner.md", "", config_dir=str(tmp_path))
        assert res["saved"] is False
        assert "non-empty" in res["error"]
        res = write_prompt("planner.md", "   ", config_dir=str(tmp_path))
        assert res["saved"] is False

    def test_write_prompt_creates_dir_if_missing(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        assert not (tmp_path / "llm" / "prompts").exists()
        res = write_prompt("planner.md", "x", config_dir=str(tmp_path))
        assert res["saved"] is True
        assert (tmp_path / "llm" / "prompts" / "planner.md").exists()


class TestPerModelLookup:
    """#338 Schicht B: 4-stage lookup (model > provider > generic > package)."""

    def _seed(self, tmp_path: Path, layout: dict[str, str]) -> None:
        for rel, content in layout.items():
            fp = tmp_path / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")

    def test_load_system_prompt_model_override_wins(self, tmp_path):
        """Model-override has highest precedence among operator levels."""
        self._seed(tmp_path, {
            "llm/prompts/model/qwen2.5-coder-7b/planner.md": "MODEL",
            "llm/prompts/provider/lmstudio/planner.md": "PROVIDER",
            "llm/prompts/planner.md": "GENERIC",
        })
        text = load_system_prompt(
            "planner.md",
            config_dir=str(tmp_path),
            provider="lmstudio",
            model="qwen2.5-coder-7b",
        )
        assert text == "MODEL"

    def test_load_system_prompt_falls_through_provider_to_generic(self, tmp_path):
        """When no model-override exists but a provider-override does, the
        provider one is used. When neither, generic is used."""
        # First: provider falls through (no model-override)
        self._seed(tmp_path, {
            "llm/prompts/provider/lmstudio/planner.md": "PROVIDER",
            "llm/prompts/planner.md": "GENERIC",
        })
        text = load_system_prompt(
            "planner.md",
            config_dir=str(tmp_path),
            provider="lmstudio",
            model="qwen2.5-coder-7b",
        )
        assert text == "PROVIDER"
        # Second: only generic exists -> generic wins regardless of provider/model
        for stale in (tmp_path / "llm" / "prompts" / "provider").glob("**/*"):
            if stale.is_file():
                stale.unlink()
        text = load_system_prompt(
            "planner.md",
            config_dir=str(tmp_path),
            provider="lmstudio",
            model="qwen2.5-coder-7b",
        )
        assert text == "GENERIC"

    def test_load_system_prompt_no_override_uses_package_default(self, tmp_path):
        """No operator-overrides at any level -> package default returned."""
        text = load_system_prompt(
            "senior_python.md",
            config_dir=str(tmp_path),
            provider="lmstudio",
            model="qwen2.5-coder-7b",
        )
        assert "Rolle" in text or "Python" in text
        assert len(text) > 100

    def test_legacy_call_without_provider_or_model_still_works(self, tmp_path):
        """Backward-compat: callers from before #338 don't pass provider/model."""
        self._seed(tmp_path, {"llm/prompts/planner.md": "GENERIC"})
        text = load_system_prompt("planner.md", config_dir=str(tmp_path))
        assert text == "GENERIC"

    def test_provider_only_call_still_falls_back_to_generic(self, tmp_path):
        self._seed(tmp_path, {"llm/prompts/planner.md": "GENERIC"})
        text = load_system_prompt(
            "planner.md", config_dir=str(tmp_path), provider="lmstudio",
        )
        assert text == "GENERIC"

    def test_model_segment_with_slash_is_sanitized(self, tmp_path):
        """Model IDs like ``openai/gpt-4o`` must not punch out of the
        prompts root via path traversal."""
        # The dir has `_` (the sanitized form of `openai/gpt-4o`)
        self._seed(tmp_path, {
            "llm/prompts/model/openai_gpt-4o/planner.md": "MODEL",
        })
        text = load_system_prompt(
            "planner.md",
            config_dir=str(tmp_path),
            provider="openrouter",
            model="openai/gpt-4o",
        )
        assert text == "MODEL"

    def test_model_traversal_attempt_rejected(self, tmp_path):
        """Even with .. tricks the lookup must not escape the prompts root."""
        self._seed(tmp_path, {
            "llm/prompts/planner.md": "GENERIC",
        })
        # Place a file outside the expected dir to confirm we don't reach it.
        (tmp_path / "secret.md").write_text("LEAKED", encoding="utf-8")
        text = load_system_prompt(
            "planner.md",
            config_dir=str(tmp_path),
            model="../../../secret",
        )
        # Falls through to generic — the model-segment was sanitized away
        # from any traversal ability.
        assert text == "GENERIC"

    def test_empty_model_skips_model_level(self, tmp_path):
        """An empty / whitespace-only model is treated as 'no model layer'."""
        self._seed(tmp_path, {
            "llm/prompts/provider/lmstudio/planner.md": "PROVIDER",
        })
        text = load_system_prompt(
            "planner.md",
            config_dir=str(tmp_path),
            provider="lmstudio",
            model="   ",
        )
        assert text == "PROVIDER"


class TestDeletePrompt:
    """#338 Schicht C: delete_prompt removes operator-overrides at any scope."""

    def _activate_premium(self, monkeypatch):
        from samuel.core import license as _lic
        fake = _lic.License(
            email="t@x", features=frozenset({"llm_routing_dashboard_write"}),
            issued_at="2026-05-05T12:00:00Z",
        )
        monkeypatch.setattr(_lic, "_LICENSE", fake)

    def _seed_override(self, tmp_path: Path, rel: str, content: str) -> Path:
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return fp

    def test_delete_prompt_premium_blocks_in_free_mode(self, tmp_path, monkeypatch):
        """#338-AC: name matches issue-body anchor."""
        from samuel.adapters.llm.prompts import delete_prompt
        from samuel.core import license as _lic
        monkeypatch.setattr(_lic, "_LICENSE", None)
        # Seed a file so we'd know if delete proceeded
        fp = self._seed_override(tmp_path, "llm/prompts/planner.md", "X")

        res = delete_prompt("planner.md", config_dir=str(tmp_path))

        assert res["deleted"] is False
        assert "premium" in res["error"]
        # File untouched
        assert fp.exists()

    def test_delete_prompt_removes_override(self, tmp_path, monkeypatch):
        """#338-AC: name matches issue-body anchor."""
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import delete_prompt
        fp = self._seed_override(tmp_path, "llm/prompts/planner.md", "OVERRIDE")

        res = delete_prompt("planner.md", config_dir=str(tmp_path))

        assert res["deleted"] is True
        assert res["scope"] == "generic"
        assert not fp.exists()

    def test_delete_prompt_rejects_path_traversal(self, tmp_path, monkeypatch):
        """#338-AC: name matches issue-body anchor."""
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import delete_prompt
        for bad in ("../escape.md", "sub/dir.md", "..\\win.md"):
            res = delete_prompt(bad, config_dir=str(tmp_path))
            assert res["deleted"] is False
            assert "invalid characters" in res["error"]

    def test_delete_prompt_at_provider_scope(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import delete_prompt
        fp = self._seed_override(
            tmp_path, "llm/prompts/provider/lmstudio/planner.md", "PROVIDER",
        )

        res = delete_prompt(
            "planner.md", config_dir=str(tmp_path), scope="provider:lmstudio",
        )

        assert res["deleted"] is True
        assert res["scope"] == "provider:lmstudio"
        assert not fp.exists()

    def test_delete_prompt_at_model_scope(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import delete_prompt
        fp = self._seed_override(
            tmp_path,
            "llm/prompts/model/qwen2.5-coder-7b/planner.md", "MODEL",
        )

        res = delete_prompt(
            "planner.md", config_dir=str(tmp_path),
            scope="model:qwen2.5-coder-7b",
        )

        assert res["deleted"] is True
        assert not fp.exists()

    def test_delete_prompt_idempotent_when_missing(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import delete_prompt

        res = delete_prompt("nonexistent.md", config_dir=str(tmp_path))

        assert res["deleted"] is False
        assert "no override" in res["reason"]

    def test_delete_prompt_rejects_non_md_name(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import delete_prompt
        res = delete_prompt("script.py", config_dir=str(tmp_path))
        assert res["deleted"] is False
        assert ".md" in res["error"]

    def test_delete_prompt_rejects_invalid_scope(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import delete_prompt
        for bad in ("garbage", "provider", "model:"):
            res = delete_prompt(
                "planner.md", config_dir=str(tmp_path), scope=bad,
            )
            assert res["deleted"] is False
            assert "invalid" in res["error"]


class TestWritePromptScoped:
    """#338 Schicht C: write_prompt with scope writes to scope-specific dir."""

    def _activate_premium(self, monkeypatch):
        from samuel.core import license as _lic
        fake = _lic.License(
            email="t@x", features=frozenset({"llm_routing_dashboard_write"}),
            issued_at="2026-05-05T12:00:00Z",
        )
        monkeypatch.setattr(_lic, "_LICENSE", fake)

    def test_write_to_provider_scope(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        res = write_prompt(
            "planner.md", "PROVIDER OVERRIDE",
            config_dir=str(tmp_path), scope="provider:lmstudio",
        )
        assert res["saved"] is True
        assert res["source"] == "operator-provider"
        fp = tmp_path / "llm" / "prompts" / "provider" / "lmstudio" / "planner.md"
        assert fp.exists()
        assert fp.read_text() == "PROVIDER OVERRIDE"

    def test_write_to_model_scope_with_safe_path(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        res = write_prompt(
            "planner.md", "MODEL OVERRIDE",
            config_dir=str(tmp_path),
            scope="model:openai/gpt-4o",
        )
        assert res["saved"] is True
        # Slashes in model id get sanitized to single safe segment
        fp = tmp_path / "llm" / "prompts" / "model" / "openai_gpt-4o" / "planner.md"
        assert fp.exists()

    def test_write_rejects_invalid_scope(self, tmp_path, monkeypatch):
        self._activate_premium(monkeypatch)
        from samuel.adapters.llm.prompts import write_prompt
        res = write_prompt(
            "planner.md", "X", config_dir=str(tmp_path), scope="garbage",
        )
        assert res["saved"] is False
        assert "invalid" in res["error"]


class TestResolvePromptSource:
    """#338 Schicht C: resolve_prompt_source returns the active layer."""

    def test_returns_package_when_no_overrides(self, tmp_path):
        from samuel.adapters.llm.prompts import resolve_prompt_source
        info = resolve_prompt_source(
            "senior_python.md", config_dir=str(tmp_path),
        )
        assert info["source"] == "package"
        assert "core/prompts/senior_python.md" in info["path"]
        assert info["mtime"] > 0

    def test_returns_operator_generic_when_present(self, tmp_path):
        from samuel.adapters.llm.prompts import resolve_prompt_source
        d = tmp_path / "llm" / "prompts"
        d.mkdir(parents=True)
        (d / "planner.md").write_text("X", encoding="utf-8")
        info = resolve_prompt_source(
            "planner.md", config_dir=str(tmp_path),
        )
        assert info["source"] == "operator-generic"

    def test_model_overrides_provider_overrides_generic(self, tmp_path):
        from samuel.adapters.llm.prompts import resolve_prompt_source
        # Seed all 3 levels
        for rel in [
            "llm/prompts/planner.md",
            "llm/prompts/provider/lmstudio/planner.md",
            "llm/prompts/model/qwen2.5-coder-7b/planner.md",
        ]:
            fp = tmp_path / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text("X", encoding="utf-8")

        # Model wins
        info = resolve_prompt_source(
            "planner.md", config_dir=str(tmp_path),
            provider="lmstudio", model="qwen2.5-coder-7b",
        )
        assert info["source"] == "operator-model:qwen2.5-coder-7b"

        # Without model -> provider wins
        info = resolve_prompt_source(
            "planner.md", config_dir=str(tmp_path),
            provider="lmstudio",
        )
        assert info["source"] == "operator-provider:lmstudio"

        # Without provider/model -> generic wins
        info = resolve_prompt_source(
            "planner.md", config_dir=str(tmp_path),
        )
        assert info["source"] == "operator-generic"


class TestListAvailablePromptsScoped:
    """#338 Schicht C: list_available_prompts(scope=...) lists scope-specific dir."""

    def test_lists_only_provider_dir(self, tmp_path):
        from samuel.adapters.llm.prompts import list_available_prompts
        # Mix of generic + provider files — only provider should be returned
        (tmp_path / "llm" / "prompts").mkdir(parents=True)
        (tmp_path / "llm" / "prompts" / "generic.md").write_text("G", encoding="utf-8")
        d = tmp_path / "llm" / "prompts" / "provider" / "lmstudio"
        d.mkdir(parents=True)
        (d / "planner.md").write_text("P", encoding="utf-8")

        rows = list_available_prompts(
            str(tmp_path), scope="provider:lmstudio",
        )

        names = [r["name"] for r in rows]
        assert names == ["planner.md"]
        assert rows[0]["source"] == "operator-provider"

    def test_returns_empty_when_scope_dir_missing(self, tmp_path):
        from samuel.adapters.llm.prompts import list_available_prompts
        rows = list_available_prompts(
            str(tmp_path), scope="model:does-not-exist",
        )
        assert rows == []


class TestLoadPromptAtScope:
    """#338 Schicht C: load_prompt_at_scope loads exactly one scope (no cascade)."""

    def test_returns_empty_when_scope_has_no_override(self, tmp_path):
        from samuel.adapters.llm.prompts import load_prompt_at_scope
        # Seed generic but query model -> should NOT cascade to generic
        d = tmp_path / "llm" / "prompts"
        d.mkdir(parents=True)
        (d / "planner.md").write_text("GENERIC", encoding="utf-8")

        text = load_prompt_at_scope(
            "planner.md", config_dir=str(tmp_path),
            scope="model:qwen2.5",
        )
        assert text == ""

    def test_returns_content_at_scope(self, tmp_path):
        from samuel.adapters.llm.prompts import load_prompt_at_scope
        d = tmp_path / "llm" / "prompts" / "model" / "qwen2.5-coder-7b"
        d.mkdir(parents=True)
        (d / "planner.md").write_text("MODEL", encoding="utf-8")

        text = load_prompt_at_scope(
            "planner.md", config_dir=str(tmp_path),
            scope="model:qwen2.5-coder-7b",
        )
        assert text == "MODEL"


# #351 Hybrid: per-provider override map.
class TestLoadSystemPromptByProvider:
    def test_uses_by_provider_when_provider_matches(self, tmp_path):
        """When ``provider`` has an entry in ``by_provider``, that filename
        wins over ``name`` and the cascade then runs against it."""
        prompts_dir = tmp_path / "llm" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "planner_local.md").write_text(
            "LOCAL PLANNER", encoding="utf-8",
        )

        text = load_system_prompt(
            "planner.md", config_dir=str(tmp_path),
            provider="deepseek",
            by_provider={"deepseek": "planner_local.md"},
        )
        assert text == "LOCAL PLANNER"

    def test_falls_back_to_name_when_provider_not_in_map(self, tmp_path):
        """When the active provider has no entry in the map, the default
        ``name`` is used (legacy behaviour)."""
        prompts_dir = tmp_path / "llm" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "planner.md").write_text(
            "DEFAULT PLANNER", encoding="utf-8",
        )

        text = load_system_prompt(
            "planner.md", config_dir=str(tmp_path),
            provider="ollama",  # not in map
            by_provider={"deepseek": "planner_local.md"},
        )
        assert text == "DEFAULT PLANNER"

    def test_by_provider_value_traversal_falls_back(self, tmp_path):
        """Defence in depth: if a malicious value somehow reaches the
        loader (handler validation should already block it), we ignore it
        and use ``name`` instead of crashing or escaping the prompts dir."""
        (tmp_path / "llm" / "prompts").mkdir(parents=True)
        (tmp_path / "llm" / "prompts" / "planner.md").write_text(
            "DEFAULT", encoding="utf-8",
        )

        text = load_system_prompt(
            "planner.md", config_dir=str(tmp_path),
            provider="deepseek",
            by_provider={"deepseek": "../etc/passwd.md"},
        )
        assert text == "DEFAULT"

    def test_by_provider_empty_value_falls_back(self, tmp_path):
        (tmp_path / "llm" / "prompts").mkdir(parents=True)
        (tmp_path / "llm" / "prompts" / "planner.md").write_text(
            "DEFAULT", encoding="utf-8",
        )

        text = load_system_prompt(
            "planner.md", config_dir=str(tmp_path),
            provider="deepseek",
            by_provider={"deepseek": ""},
        )
        assert text == "DEFAULT"

    def test_resolve_prompt_source_reflects_by_provider_winner(self, tmp_path):
        """#348 Source-Indikator must point at the override-file when the
        cascade actually loads it from there."""
        from samuel.adapters.llm.prompts import resolve_prompt_source

        # operator-generic file for the by_provider value
        (tmp_path / "llm" / "prompts").mkdir(parents=True)
        (tmp_path / "llm" / "prompts" / "planner_local.md").write_text(
            "LOCAL", encoding="utf-8",
        )

        info = resolve_prompt_source(
            "planner.md", config_dir=str(tmp_path),
            provider="deepseek",
            by_provider={"deepseek": "planner_local.md"},
        )
        assert info["source"] == "operator-generic"
        assert info["path"].endswith("planner_local.md")
