from __future__ import annotations

import errno
import json
import stat
from pathlib import Path
from typing import Any

import pytest

from samuel.core.bus import Bus
from samuel.core.ports import IConfig
from samuel.slices.setup.handler import REQUIRED_DIRS, SetupHandler


@pytest.fixture(autouse=True)
def _explicit_setup_configuration_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAMUEL_CONFIGURATION_MODE", "setup")


class MockConfig(IConfig):
    def get(self, key: str, default: Any = None) -> Any:
        return default

    def feature_flag(self, name: str) -> bool:
        return False


class FakeSCM:
    def __init__(self, existing: list[dict] | None = None, fail_on: set[str] | None = None) -> None:
        self._labels = list(existing or [])
        self._fail_on = fail_on or set()
        self.created: list[dict] = []

    def list_labels(self) -> list[dict]:
        return list(self._labels)

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        if name in self._fail_on:
            raise RuntimeError(f"simulated failure for {name}")
        new = {
            "id": len(self._labels) + 1,
            "name": name,
            "color": color,
            "description": description,
        }
        self._labels.append(new)
        self.created.append(new)
        return new


class TestSetupHandler:
    @staticmethod
    def _clear_setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
        for key in (
            "SCM_PROVIDER",
            "SCM_URL",
            "SCM_USER",
            "SCM_TOKEN",
            "SCM_REPO",
            "SCM_BOT_USER",
            "SCM_REQUIRED_STATUS_CONTEXT",
            "SAMUEL_API_KEY",
            "SLICE_HMAC_KEY",
            "SAMUEL_AUDIT_HMAC_KEY",
            "DEEPSEEK_API_KEY",
            "OLLAMA_URL",
        ):
            monkeypatch.delenv(key, raising=False)

    @staticmethod
    def _dashboard_payload(**overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scm_provider": "gitea",
            "scm_url": "https://gitea.example.test",
            "scm_token": "scm-secret",
            "scm_repo": "owner/repo",
            "dashboard_port": "7777",
            "llm_provider": "deepseek",
            "llm_model": "deepseek-chat",
            "llm_api_key": "llm-secret",
        }
        payload.update(overrides)
        return payload

    def test_dashboard_status_never_exposes_secrets(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        (tmp_path / ".env").write_text(
            "SCM_URL=https://gitea.example.test\nSCM_TOKEN=top-secret\n"
            "SCM_REPO=owner/repo\nSAMUEL_API_KEY=dashboard-secret\n"
            "DEEPSEEK_API_KEY=llm-secret\n"
        )
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "llm.json").write_text(
            json.dumps({"default": {"provider": "deepseek"}, "deepseek": {}})
        )

        result = SetupHandler(Bus(), project_root=tmp_path).dashboard_status()

        serialized = json.dumps(result)
        assert result["first_run"] is False
        assert result["values"]["llm_key_configured"] is True
        assert result["values"]["scm_required_status_context"] == (
            "CI / lint-and-test (pull_request)"
        )
        assert result["values"]["scm_required_status_context_source"] == "shipped_default"
        assert "top-secret" not in serialized
        assert "dashboard-secret" not in serialized
        assert "llm-secret" not in serialized

    def test_dashboard_configure_persists_and_emits_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from samuel.slices.setup.env_io import parse_env

        self._clear_setup_env(monkeypatch)
        events: list[Any] = []
        bus = Bus()
        bus.subscribe("ConfigChanged", events.append)
        handler = SetupHandler(
            bus,
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": True, "detail": "ok"},
            llm_tester=lambda *_args: {"valid": True, "detail": "ok"},
        )

        result = handler.configure_dashboard(self._dashboard_payload())

        assert result["configured"] is True
        assert result["restart_required"] is True
        assert len(result["api_key"]) == 48
        dotenv = parse_env((tmp_path / ".env").read_text())
        assert dotenv["SCM_TOKEN"] == "scm-secret"
        assert dotenv["SCM_REQUIRED_STATUS_CONTEXT"] == "CI / lint-and-test (pull_request)"
        assert dotenv["DEEPSEEK_API_KEY"] == "llm-secret"
        assert dotenv["SAMUEL_API_KEY"] == result["api_key"]
        assert len(dotenv["SLICE_HMAC_KEY"]) == 64
        assert len(dotenv["SAMUEL_AUDIT_HMAC_KEY"]) == 64
        assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
        llm = json.loads((tmp_path / "config" / "llm.json").read_text())
        assert llm["default"]["provider"] == "deepseek"
        assert llm["deepseek"]["model"] == "deepseek-chat"
        assert events[0].payload["source"] == "dashboard"

    def test_dashboard_configure_persists_custom_required_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from samuel.slices.setup.env_io import parse_env

        self._clear_setup_env(monkeypatch)
        handler = SetupHandler(
            Bus(),
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": True},
            llm_tester=lambda *_args: {"valid": True},
        )

        result = handler.configure_dashboard(
            self._dashboard_payload(scm_required_status_context="CI / demo-tests (pull_request)")
        )

        assert result["configured"] is True
        dotenv = parse_env((tmp_path / ".env").read_text())
        assert dotenv["SCM_REQUIRED_STATUS_CONTEXT"] == "CI / demo-tests (pull_request)"
        status = handler.dashboard_status()
        assert status["values"]["scm_required_status_context_source"] == "configured"

    def test_dashboard_configure_rejects_explicit_empty_required_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        handler = SetupHandler(Bus(), project_root=tmp_path)

        result = handler.configure_dashboard(
            self._dashboard_payload(scm_required_status_context="")
        )

        assert result["configured"] is False
        assert any("SCM_REQUIRED_STATUS_CONTEXT" in error for error in result["errors"])

    def test_existing_dashboard_key_is_preserved_but_not_returned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        (tmp_path / ".env").write_text("SAMUEL_API_KEY=existing-key\n")
        handler = SetupHandler(
            Bus(),
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": True},
            llm_tester=lambda *_args: {"valid": True},
        )

        result = handler.configure_dashboard(self._dashboard_payload())

        assert result["configured"] is True
        assert result["api_key"] == ""
        assert "existing-key" not in json.dumps(result)

    def test_runtime_security_values_and_existing_llm_provider_are_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from samuel.slices.setup.env_io import parse_env

        self._clear_setup_env(monkeypatch)
        monkeypatch.setenv("SLICE_HMAC_KEY", "runtime-webhook-key")
        monkeypatch.setenv("SAMUEL_AUDIT_HMAC_KEY", "runtime-audit-key")
        monkeypatch.setenv("DASHBOARD_PORT", "8123")
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "llm.json").write_text(
            '{"default": {"provider": "manual"}, "manual": {}}\n'
        )
        handler = SetupHandler(
            Bus(),
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": True},
        )
        payload = self._dashboard_payload()
        for key in ("llm_provider", "llm_model", "llm_api_key", "dashboard_port"):
            payload.pop(key)

        result = handler.configure_dashboard(payload)

        assert result["configured"] is True
        dotenv = parse_env((tmp_path / ".env").read_text())
        assert dotenv["SLICE_HMAC_KEY"] == "runtime-webhook-key"
        assert dotenv["SAMUEL_AUDIT_HMAC_KEY"] == "runtime-audit-key"
        assert dotenv["DASHBOARD_PORT"] == "8123"
        llm = json.loads((tmp_path / "config" / "llm.json").read_text())
        assert llm["default"]["provider"] == "manual"

    def test_failed_probe_does_not_write_without_explicit_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        handler = SetupHandler(
            Bus(),
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": False, "detail": "401"},
        )

        result = handler.configure_dashboard(self._dashboard_payload())

        assert result["configured"] is False
        assert "401" in result["errors"][0]
        assert not (tmp_path / ".env").exists()
        assert not (tmp_path / "config" / "llm.json").exists()

    def test_explicit_override_can_persist_unverified_configuration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        handler = SetupHandler(
            Bus(),
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": False, "detail": "offline"},
            llm_tester=lambda *_args: {"valid": False, "detail": "offline"},
        )

        result = handler.configure_dashboard(self._dashboard_payload(allow_unverified=True))

        assert result["configured"] is True
        assert result["probes"]["scm"]["valid"] is False
        assert result["probes"]["llm"]["valid"] is False

    def test_malformed_llm_config_is_not_overwritten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        (tmp_path / "config").mkdir()
        llm_path = tmp_path / "config" / "llm.json"
        llm_path.write_text("{broken")
        handler = SetupHandler(Bus(), project_root=tmp_path)

        result = handler.configure_dashboard(self._dashboard_payload())

        assert result["configured"] is False
        assert "llm.json" in result["errors"][0]
        assert llm_path.read_text() == "{broken"
        assert not (tmp_path / ".env").exists()

    def test_rejects_newline_injection_before_writing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        result = SetupHandler(Bus(), project_root=tmp_path).configure_dashboard(
            self._dashboard_payload(scm_token="valid\nINJECTED=yes")
        )
        assert result["configured"] is False
        assert not (tmp_path / ".env").exists()

    def test_local_llm_uses_default_url_as_env_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from samuel.slices.setup.env_io import parse_env

        self._clear_setup_env(monkeypatch)
        handler = SetupHandler(
            Bus(),
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": True},
            llm_tester=lambda *_args: {"valid": True},
        )

        result = handler.configure_dashboard(
            self._dashboard_payload(llm_provider="ollama", llm_api_key="")
        )

        assert result["configured"] is True
        dotenv = parse_env((tmp_path / ".env").read_text())
        assert dotenv["OLLAMA_URL"] == "http://localhost:11434"
        llm = json.loads((tmp_path / "config" / "llm.json").read_text())
        assert llm["ollama"]["url"] == "http://localhost:11434"

    def test_validation_failure_leaves_existing_files_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        (tmp_path / ".env").write_text("KEEP=yes\n")
        result = SetupHandler(Bus(), project_root=tmp_path).configure_dashboard(
            self._dashboard_payload(scm_url="not-a-url")
        )
        assert result["configured"] is False
        assert (tmp_path / ".env").read_text() == "KEEP=yes\n"

    def test_multi_file_write_rolls_back_on_second_replace_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        (tmp_path / "config").mkdir()
        llm_path = tmp_path / "config" / "llm.json"
        old_llm = '{"default": {"provider": "manual"}}\n'
        llm_path.write_text(old_llm)
        original_replace = Path.replace

        def fail_env_replace(path: Path, target: Path):
            if path.name == ".env.samuel-setup.tmp":
                raise OSError("simulated env rename failure")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", fail_env_replace)
        handler = SetupHandler(
            Bus(),
            project_root=tmp_path,
            scm_tester=lambda *_args: {"valid": True},
            llm_tester=lambda *_args: {"valid": True},
        )

        result = handler.configure_dashboard(self._dashboard_payload())

        assert result["configured"] is False
        assert llm_path.read_text() == old_llm
        assert not (tmp_path / ".env").exists()

    def test_atomic_write_many_uses_rename_when_available(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("OLD=yes\n")

        SetupHandler._atomic_write_many([(env_path, "NEW=yes\n", 0o600)])

        assert env_path.read_text() == "NEW=yes\n"
        assert stat.S_IMODE(env_path.stat().st_mode) == 0o600

    def test_atomic_write_many_supports_explicit_busy_bind_mount(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("OLD=yes\n")
        env_path.chmod(0o644)
        original_replace = Path.replace

        def busy_env_replace(path: Path, target: Path):
            if path.name == ".env.samuel-setup.tmp":
                raise OSError(errno.EBUSY, "simulated bind mount")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", busy_env_replace)

        SetupHandler._atomic_write_many(
            [(env_path, "NEW=yes\n", 0o600)],
            bind_mount_fallback_paths=frozenset({env_path}),
        )

        assert env_path.read_text() == "NEW=yes\n"
        assert stat.S_IMODE(env_path.stat().st_mode) == 0o600

    def test_busy_bind_mount_stages_outside_non_writable_image_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("OLD=yes\n")
        original_write_text = Path.write_text

        def deny_sibling_staging(path: Path, content: str, *args: Any, **kwargs: Any) -> int:
            if path.name == ".env.samuel-setup.tmp":
                raise OSError(errno.EACCES, "simulated image directory")
            return original_write_text(path, content, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", deny_sibling_staging)

        SetupHandler._atomic_write_many(
            [(env_path, "NEW=yes\n", 0o600)],
            bind_mount_fallback_paths=frozenset({env_path}),
        )

        assert env_path.read_text() == "NEW=yes\n"
        assert stat.S_IMODE(env_path.stat().st_mode) == 0o600

    def test_busy_bind_mount_error_before_in_place_write_rolls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path = tmp_path / "config" / "llm.json"
        config_path.parent.mkdir()
        config_path.write_text("old-config\n")
        env_path = tmp_path / ".env"
        env_path.write_text("OLD=yes\n")
        original_replace = Path.replace

        def fail_before_env_write(path: Path, target: Path):
            if path.name == "llm.json.samuel-setup.tmp":
                raise OSError(errno.EIO, "simulated pre-write failure")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", fail_before_env_write)

        with pytest.raises(OSError, match="pre-write"):
            SetupHandler._atomic_write_many(
                [(config_path, "new-config\n", None), (env_path, "NEW=yes\n", 0o600)],
                bind_mount_fallback_paths=frozenset({env_path}),
            )

        assert config_path.read_text() == "old-config\n"
        assert env_path.read_text() == "OLD=yes\n"

    def test_busy_bind_mount_write_failure_rolls_back_prior_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path = tmp_path / "config" / "llm.json"
        config_path.parent.mkdir()
        config_path.write_text("old-config\n")
        env_path = tmp_path / ".env"
        env_path.write_text("OLD=yes\n")
        original_replace = Path.replace
        original_in_place = SetupHandler._write_staged_in_place

        def busy_env_replace(path: Path, target: Path):
            if path.name == ".env.samuel-setup.tmp":
                raise OSError(errno.EBUSY, "simulated bind mount")
            return original_replace(path, target)

        def fail_new_env_write(path: Path, staged: Path, *, mode: int | None) -> None:
            if staged.name == ".env.samuel-setup.tmp":
                raise OSError(errno.EIO, "simulated in-place failure")
            original_in_place(path, staged, mode=mode)

        monkeypatch.setattr(Path, "replace", busy_env_replace)
        monkeypatch.setattr(SetupHandler, "_write_staged_in_place", fail_new_env_write)

        with pytest.raises(OSError, match="in-place failure"):
            SetupHandler._atomic_write_many(
                [(config_path, "new-config\n", None), (env_path, "NEW=yes\n", 0o600)],
                bind_mount_fallback_paths=frozenset({env_path}),
            )

        assert config_path.read_text() == "old-config\n"
        assert env_path.read_text() == "OLD=yes\n"

    def test_busy_bind_mount_rolls_back_when_later_replace_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("OLD=yes\n")
        config_path = tmp_path / "config" / "llm.json"
        config_path.parent.mkdir()
        config_path.write_text("old-config\n")
        original_replace = Path.replace

        def busy_then_fail(path: Path, target: Path):
            if path.name == ".env.samuel-setup.tmp":
                raise OSError(errno.EBUSY, "simulated bind mount")
            if path.name == "llm.json.samuel-setup.tmp":
                raise OSError(errno.EIO, "simulated later failure")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", busy_then_fail)

        with pytest.raises(OSError, match="later failure"):
            SetupHandler._atomic_write_many(
                [(env_path, "NEW=yes\n", 0o600), (config_path, "new-config\n", None)],
                bind_mount_fallback_paths=frozenset({env_path}),
            )

        assert env_path.read_text() == "OLD=yes\n"
        assert config_path.read_text() == "old-config\n"

    def test_rejects_short_custom_dashboard_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_setup_env(monkeypatch)
        result = SetupHandler(Bus(), project_root=tmp_path).configure_dashboard(
            self._dashboard_payload(dashboard_api_key="too-short")
        )
        assert result["configured"] is False
        assert "24" in result["errors"][0]

    def test_check_prerequisites_missing_dirs(self, tmp_path: Path) -> None:
        bus = Bus()
        handler = SetupHandler(bus, project_root=tmp_path)

        result = handler.check_prerequisites()

        assert result["ready"] is False
        for d in REQUIRED_DIRS:
            assert any(d in issue for issue in result["issues"])

    def test_check_prerequisites_dirs_present(self, tmp_path: Path) -> None:
        bus = Bus()
        for d in REQUIRED_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        handler = SetupHandler(bus, project_root=tmp_path)

        result = handler.check_prerequisites()

        dir_issues = [i for i in result["issues"] if "directory missing" in i]
        assert len(dir_issues) == 0

    def test_ensure_directories_creates_dirs(self, tmp_path: Path) -> None:
        bus = Bus()
        handler = SetupHandler(bus, project_root=tmp_path)

        created = handler.ensure_directories()

        assert len(created) == len(REQUIRED_DIRS)
        for d in REQUIRED_DIRS:
            assert (tmp_path / d).is_dir()
            assert d in created

    def test_ensure_directories_skips_existing(self, tmp_path: Path) -> None:
        bus = Bus()
        for d in REQUIRED_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        handler = SetupHandler(bus, project_root=tmp_path)

        created = handler.ensure_directories()

        assert len(created) == 0

    def test_ensure_then_check_prerequisites(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bus = Bus()
        monkeypatch.setenv("SCM_URL", "http://example.com")
        monkeypatch.setenv("SCM_TOKEN", "tok")
        monkeypatch.setenv("SCM_REPO", "owner/repo")
        handler = SetupHandler(bus, project_root=tmp_path)

        handler.ensure_directories()
        result = handler.check_prerequisites()

        assert result["ready"] is True
        assert result["issues"] == []

    def test_env_vars_missing_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bus = Bus()
        for d in REQUIRED_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        monkeypatch.delenv("SCM_URL", raising=False)
        monkeypatch.delenv("SCM_TOKEN", raising=False)
        monkeypatch.delenv("SCM_REPO", raising=False)
        monkeypatch.delenv("GITEA_URL", raising=False)
        monkeypatch.delenv("GITEA_TOKEN", raising=False)
        monkeypatch.delenv("GITEA_REPO", raising=False)
        handler = SetupHandler(bus, project_root=tmp_path)

        result = handler.check_prerequisites()

        assert result["ready"] is False
        env_issues = [i for i in result["issues"] if "env var missing" in i]
        assert len(env_issues) == 3


class TestSyncLabels:
    def _write_labels(self, tmp_path: Path, names: list[str]) -> Path:
        (tmp_path / "config").mkdir(exist_ok=True)
        labels_file = tmp_path / "config" / "labels.json"
        with open(labels_file, "w") as f:
            json.dump(
                {
                    "labels": [
                        {"name": n, "color": "cccccc", "description": f"{n} desc"} for n in names
                    ]
                },
                f,
            )
        return labels_file

    def test_sync_creates_missing_labels(self, tmp_path: Path) -> None:
        scm = FakeSCM(
            existing=[{"id": 1, "name": "ready-for-agent", "color": "0e8a16", "description": ""}]
        )
        self._write_labels(tmp_path, ["ready-for-agent", "in-progress", "needs-review"])
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=scm)

        result = handler.sync_labels()

        assert result["synced"] is True
        assert result["created"] == ["in-progress", "needs-review"]
        assert result["skipped"] == ["ready-for-agent"]
        assert result["errors"] == []
        assert {l["name"] for l in scm.created} == {"in-progress", "needs-review"}

    def test_sync_is_idempotent(self, tmp_path: Path) -> None:
        scm = FakeSCM(
            existing=[
                {"id": 1, "name": "in-progress", "color": "1d76db", "description": ""},
                {"id": 2, "name": "needs-review", "color": "fbca04", "description": ""},
            ]
        )
        self._write_labels(tmp_path, ["in-progress", "needs-review"])
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=scm)

        result = handler.sync_labels()

        assert result["synced"] is True
        assert result["created"] == []
        assert len(result["skipped"]) == 2
        assert scm.created == []

    def test_sync_reports_errors_but_continues(self, tmp_path: Path) -> None:
        scm = FakeSCM(existing=[], fail_on={"in-progress"})
        self._write_labels(tmp_path, ["ready-for-agent", "in-progress", "needs-review"])
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=scm)

        result = handler.sync_labels()

        assert result["synced"] is False
        assert "ready-for-agent" in result["created"]
        assert "needs-review" in result["created"]
        assert any("in-progress" in e for e in result["errors"])

    def test_sync_without_scm_returns_error(self, tmp_path: Path) -> None:
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=None)
        result = handler.sync_labels()
        assert result["synced"] is False
        assert "SCM not configured" in result["error"]

    def test_sync_with_missing_file_returns_error(self, tmp_path: Path) -> None:
        handler = SetupHandler(Bus(), project_root=tmp_path, scm=FakeSCM())
        result = handler.sync_labels(tmp_path / "does-not-exist.json")
        assert result["synced"] is False
        assert "not found" in result["error"]
