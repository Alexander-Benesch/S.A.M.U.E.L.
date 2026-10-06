from __future__ import annotations

import pytest

from samuel.core.config import (
    DEFAULT_SCM_REQUIRED_STATUS_CONTEXT,
    SCMConfig,
    load_scm_config,
    resolve_scm_required_status_context,
    scm_policy_binding,
)


class TestSCMConfigNew:
    def test_loads_from_scm_vars(self, monkeypatch):
        monkeypatch.setenv("SCM_PROVIDER", "gitea")
        monkeypatch.setenv("SCM_URL", "http://gitea.local")
        monkeypatch.setenv("SCM_TOKEN", "tok-123")
        monkeypatch.setenv("SCM_REPO", "owner/repo")
        monkeypatch.setenv("SCM_USER", "admin")
        monkeypatch.setenv("SCM_BOT_USER", "bot")
        monkeypatch.setenv("SCM_REQUIRED_STATUS_CONTEXT", "CI / target-tests (pull_request)")

        cfg = load_scm_config()
        assert cfg.provider == "gitea"
        assert cfg.url == "http://gitea.local"
        assert cfg.token == "tok-123"
        assert cfg.repo == "owner/repo"
        assert cfg.user == "admin"
        assert cfg.bot_user == "bot"
        assert cfg.required_status_context == "CI / target-tests (pull_request)"

    def test_defaults_provider_to_gitea(self, monkeypatch):
        monkeypatch.setenv("SCM_URL", "http://gitea.local")
        monkeypatch.setenv("SCM_TOKEN", "tok")
        monkeypatch.setenv("SCM_REPO", "o/r")
        monkeypatch.delenv("SCM_PROVIDER", raising=False)

        cfg = load_scm_config()
        assert cfg.provider == "gitea"
        assert cfg.required_status_context == DEFAULT_SCM_REQUIRED_STATUS_CONTEXT

    def test_explicit_empty_required_context_is_rejected(self, monkeypatch):
        monkeypatch.setenv("SCM_URL", "http://gitea.local")
        monkeypatch.setenv("SCM_TOKEN", "tok")
        monkeypatch.setenv("SCM_REPO", "o/r")
        monkeypatch.setenv("SCM_REQUIRED_STATUS_CONTEXT", "   ")

        with pytest.raises(ValueError, match="SCM_REQUIRED_STATUS_CONTEXT"):
            load_scm_config()


class TestSCMConfigLegacy:
    def test_maps_gitea_vars(self, monkeypatch):
        monkeypatch.delenv("SCM_PROVIDER", raising=False)
        monkeypatch.delenv("SCM_URL", raising=False)
        monkeypatch.setenv("GITEA_URL", "http://legacy.local")
        monkeypatch.setenv("GITEA_TOKEN", "old-tok")
        monkeypatch.setenv("GITEA_REPO", "old/repo")
        monkeypatch.setenv("GITEA_USER", "olduser")
        monkeypatch.setenv("GITEA_BOT_USER", "oldbot")

        cfg = load_scm_config()
        assert cfg.provider == "gitea"
        assert cfg.url == "http://legacy.local"
        assert cfg.token == "old-tok"
        assert cfg.repo == "old/repo"

    def test_scm_takes_precedence_over_legacy(self, monkeypatch):
        monkeypatch.setenv("SCM_URL", "http://new.local")
        monkeypatch.setenv("SCM_TOKEN", "new-tok")
        monkeypatch.setenv("SCM_REPO", "new/repo")
        monkeypatch.setenv("GITEA_URL", "http://old.local")

        cfg = load_scm_config()
        assert cfg.url == "http://new.local"


class TestSCMConfigMissing:
    def test_raises_without_config(self, monkeypatch):
        for var in (
            "SCM_PROVIDER",
            "SCM_URL",
            "SCM_TOKEN",
            "SCM_REPO",
            "SCM_REQUIRED_STATUS_CONTEXT",
            "GITEA_URL",
            "GITEA_TOKEN",
            "GITEA_REPO",
        ):
            monkeypatch.delenv(var, raising=False)

        with pytest.raises(ValueError, match="SCM not configured"):
            load_scm_config()


class TestSCMConfigSchema:
    def test_pydantic_validation(self):
        cfg = SCMConfig(url="http://x", token="t", repo="o/r")
        assert cfg.provider == "gitea"
        assert cfg.user == ""
        assert cfg.required_status_context == DEFAULT_SCM_REQUIRED_STATUS_CONTEXT

    def test_rejects_multiline_required_context(self):
        with pytest.raises(ValueError, match="single line"):
            SCMConfig(
                url="http://x",
                token="t",
                repo="o/r",
                required_status_context="CI / ok\nCI / other",
            )


def test_required_context_source_and_policy_binding(monkeypatch):
    monkeypatch.delenv("SCM_REQUIRED_STATUS_CONTEXT", raising=False)
    value, source = resolve_scm_required_status_context()
    assert value == DEFAULT_SCM_REQUIRED_STATUS_CONTEXT
    assert source == "shipped_default"

    config = SCMConfig(
        provider="Gitea",
        url="http://x",
        token="t",
        repo="o/r",
        required_status_context="CI / demo-tests (pull_request)",
    )
    assert scm_policy_binding(config) == {
        "provider": "gitea",
        "required_status_context": "CI / demo-tests (pull_request)",
    }


def test_explicit_shipped_value_has_same_effective_policy_binding(monkeypatch):
    monkeypatch.delenv("SCM_REQUIRED_STATUS_CONTEXT", raising=False)
    implicit, implicit_source = resolve_scm_required_status_context()
    monkeypatch.setenv("SCM_REQUIRED_STATUS_CONTEXT", DEFAULT_SCM_REQUIRED_STATUS_CONTEXT)
    explicit, explicit_source = resolve_scm_required_status_context()

    assert implicit_source == "shipped_default"
    assert explicit_source == "configured"
    assert implicit == explicit
    assert scm_policy_binding(
        SCMConfig(url="u", token="t", repo="r", required_status_context=implicit)
    ) == (
        scm_policy_binding(
            SCMConfig(url="u", token="t", repo="r", required_status_context=explicit)
        )
    )


@pytest.mark.parametrize("prefix", ["SCM", "GITEA"])
@pytest.mark.parametrize("missing", ["URL", "TOKEN", "REPO"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_incomplete_scm_is_unconfigured(monkeypatch, prefix, missing, value):
    for key in (
        "SCM_PROVIDER",
        "SCM_URL",
        "SCM_TOKEN",
        "SCM_REPO",
        "GITEA_URL",
        "GITEA_TOKEN",
        "GITEA_REPO",
    ):
        monkeypatch.delenv(key, raising=False)
    if prefix == "SCM":
        monkeypatch.setenv("SCM_PROVIDER", "gitea")
    for key, complete in (
        ("URL", "https://gitea.test"),
        ("TOKEN", "test-token"),
        ("REPO", "owner/repo"),
    ):
        monkeypatch.setenv(f"{prefix}_{key}", complete)
    if value is None:
        monkeypatch.delenv(f"{prefix}_{missing}")
    else:
        monkeypatch.setenv(f"{prefix}_{missing}", value)
    with pytest.raises(ValueError, match="SCM not configured"):
        load_scm_config()
