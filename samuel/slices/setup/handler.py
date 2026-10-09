from __future__ import annotations

import errno
import json
import logging
import os
import secrets
import tempfile
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samuel.core.bus import Bus
from samuel.core.config import resolve_scm_required_status_context
from samuel.core.configuration_mode import ConfigurationAuthority
from samuel.core.ports import IConfig, ISecretsProvider, IVersionControl

log = logging.getLogger(__name__)

REQUIRED_DIRS = ["config", "data", "data/logs"]
REQUIRED_ENV = ["SCM_URL", "SCM_TOKEN", "SCM_REPO"]

SCMTester = Callable[[str, str, str, str], dict[str, Any]]
LLMTester = Callable[[str, dict[str, Any], str], dict[str, Any]]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class SetupHandler:
    def __init__(
        self,
        bus: Bus,
        config: IConfig | None = None,
        project_root: Path | None = None,
        secrets: ISecretsProvider | None = None,
        scm: IVersionControl | None = None,
        scm_tester: SCMTester | None = None,
        llm_tester: LLMTester | None = None,
        configuration_authority: ConfigurationAuthority | None = None,
        project_status: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._bus = bus
        self._project_status = project_status
        self._config = config
        self._root = project_root or Path(".")
        self._secrets = secrets
        self._scm = scm
        self._scm_tester = scm_tester
        self._llm_tester = llm_tester
        self._configuration_authority = configuration_authority or ConfigurationAuthority.resolve(
            self._config_dir()
        )

    def dashboard_status(self) -> dict[str, Any]:
        """Non-secret first-run state consumed by the dashboard wizard."""

        from samuel.slices.setup.env_io import LLM_PROVIDER_ENV_KEYS, parse_env

        env_path = self._root / ".env"
        try:
            dotenv = parse_env(env_path.read_text(encoding="utf-8")) if env_path.exists() else {}
        except OSError as exc:
            log.warning("Could not read dashboard setup environment %s: %s", env_path, exc)
            dotenv = {}

        def get(key: str) -> str:
            return str(os.environ.get(key) or dotenv.get(key) or "")

        def get_raw(key: str) -> str | None:
            if key in os.environ:
                return os.environ[key]
            return dotenv.get(key)

        try:
            required_status_context, required_status_context_source = (
                resolve_scm_required_status_context(get_raw)
            )
        except ValueError:
            required_status_context = str(get_raw("SCM_REQUIRED_STATUS_CONTEXT") or "")
            required_status_context_source = "invalid"

        config_dir = self._config_dir()
        llm_data = self._read_json(config_dir / "llm.json")
        default = _mapping(llm_data.get("default"))
        provider = str(default.get("provider") or "")
        provider_cfg = _mapping(llm_data.get(provider))
        env_key = LLM_PROVIDER_ENV_KEYS.get(provider, "")
        scm_configured = all(get(key) for key in ("SCM_URL", "SCM_TOKEN", "SCM_REPO"))
        api_key_configured = bool(get("SAMUEL_API_KEY"))
        llm_configured = bool(provider) and (
            provider in {"manual", "ollama", "lmstudio"} or bool(env_key and get(env_key))
        )
        return {
            "first_run": not (scm_configured and api_key_configured),
            "scm_configured": scm_configured,
            "api_key_configured": api_key_configured,
            "llm_configured": llm_configured,
            "values": {
                "scm_provider": get("SCM_PROVIDER") or "gitea",
                "scm_url": get("SCM_URL"),
                "scm_user": get("SCM_USER"),
                "scm_repo": get("SCM_REPO"),
                "scm_bot_user": get("SCM_BOT_USER"),
                "scm_required_status_context": required_status_context,
                "scm_required_status_context_source": required_status_context_source,
                "project_root": get("PROJECT_ROOT"),
                "dashboard_port": get("DASHBOARD_PORT") or "7777",
                "llm_provider": provider or "deepseek",
                "llm_model": str(provider_cfg.get("model") or ""),
                "llm_base_url": str(provider_cfg.get("url") or ""),
                "llm_key_configured": bool(env_key and get(env_key)),
            },
            "configuration": self._configuration_authority.status(),
            "project": self._project_status() if self._project_status is not None else None,
        }

    def configure_dashboard(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and atomically persist first-run SCM/LLM configuration."""

        from samuel.slices.setup.env_io import LLM_PROVIDER_ENV_KEYS, merge_env, parse_env

        blocked = self._configuration_authority.blocked_result(success_field="configured")
        if blocked is not None:
            blocked["errors"] = [blocked["error"]]
            return blocked

        if not isinstance(payload, dict):
            return {"configured": False, "errors": ["request body must be an object"]}
        clean = {key: str(value).strip() for key, value in payload.items() if value is not None}
        if any("\n" in value or "\r" in value for value in clean.values()):
            return {"configured": False, "errors": ["configuration values must be single-line"]}

        env_path = self._root / ".env"
        try:
            existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        except OSError as exc:
            return {"configured": False, "errors": [f"could not read .env: {exc}"]}
        existing = parse_env(existing_text)

        def current(key: str) -> str:
            return str(os.environ.get(key) or existing.get(key) or "")

        def current_raw(key: str) -> str | None:
            if key in os.environ:
                return os.environ[key]
            return existing.get(key)

        config_dir = self._config_dir()
        llm_path = config_dir / "llm.json"
        try:
            llm_data = self._read_json(llm_path, strict=True)
        except (OSError, ValueError) as exc:
            return {"configured": False, "errors": [f"could not read llm.json: {exc}"]}
        existing_default = _mapping(llm_data.get("default"))

        scm_provider = clean.get("scm_provider") or current("SCM_PROVIDER") or "gitea"
        scm_url = (clean.get("scm_url") or current("SCM_URL")).rstrip("/")
        scm_token = clean.get("scm_token") or current("SCM_TOKEN")
        scm_repo = clean.get("scm_repo") or current("SCM_REPO")
        requested_required_status_context = (
            clean["scm_required_status_context"]
            if "scm_required_status_context" in clean
            else current_raw("SCM_REQUIRED_STATUS_CONTEXT")
        )
        required_status_context_error = ""
        try:
            required_status_context, _source = resolve_scm_required_status_context(
                lambda _key: requested_required_status_context
            )
        except ValueError as exc:
            required_status_context = ""
            required_status_context_error = str(exc)
        llm_provider = clean.get("llm_provider") or str(
            existing_default.get("provider") or "deepseek"
        )
        existing_provider_cfg = _mapping(llm_data.get(llm_provider))
        llm_model = clean.get("llm_model") or str(existing_provider_cfg.get("model") or "")
        llm_base_url = (
            clean.get("llm_base_url") or str(existing_provider_cfg.get("url") or "")
        ).rstrip("/")
        if llm_provider == "ollama":
            llm_base_url = llm_base_url or current("OLLAMA_URL") or "http://localhost:11434"
        elif llm_provider == "lmstudio":
            llm_base_url = llm_base_url or current("LMSTUDIO_URL") or "http://localhost:1234/v1"
        errors = self._validate_dashboard_values(
            scm_provider=scm_provider,
            scm_url=scm_url,
            scm_token=scm_token,
            scm_repo=scm_repo,
            llm_provider=llm_provider,
            project_root=clean.get("project_root", ""),
            dashboard_port=clean.get("dashboard_port") or current("DASHBOARD_PORT") or "7777",
            llm_base_url=llm_base_url,
        )
        if required_status_context_error:
            errors.append(required_status_context_error)
        if clean.get("dashboard_api_key") and len(clean["dashboard_api_key"]) < 24:
            errors.append("dashboard API key must contain at least 24 characters")
        env_key = LLM_PROVIDER_ENV_KEYS.get(llm_provider, "")
        llm_secret = (
            llm_base_url
            if llm_provider in {"ollama", "lmstudio"}
            else clean.get("llm_api_key") or (current(env_key) if env_key else "")
        )
        if env_key and llm_provider not in {"ollama", "lmstudio"} and not llm_secret:
            errors.append(f"API key required for {llm_provider}")
        from samuel.core.project_binding import read_project_binding

        try:
            binding = read_project_binding(config_dir)
        except (ValueError, OSError):
            errors.append("Project registration is invalid; inspect the stopped installation")
            binding = None
        if (
            binding is not None
            and (clean.get("project_root") or current("PROJECT_ROOT"))
            != binding["container_target"]
        ):
            errors.append(
                "PROJECT_ROOT must match the registered OCI mount; change it on the stopped host installation"
            )
        if errors:
            return {"configured": False, "errors": errors}

        allow_unverified = bool(payload.get("allow_unverified", False))
        probes: dict[str, Any] = {}
        if self._scm_tester:
            probes["scm"] = self._scm_tester(scm_provider, scm_url, scm_token, scm_repo)
            if not probes["scm"].get("valid") and not allow_unverified:
                return {
                    "configured": False,
                    "errors": [f"SCM connection failed: {probes['scm'].get('detail', 'unknown')}"],
                    "probes": probes,
                }
        llm_cfg = {
            "model": llm_model,
            "base_url": llm_base_url,
        }
        if self._llm_tester and llm_provider != "manual":
            probes["llm"] = self._llm_tester(llm_provider, llm_cfg, llm_secret)
            if not probes["llm"].get("valid") and not allow_unverified:
                return {
                    "configured": False,
                    "errors": [f"LLM connection failed: {probes['llm'].get('detail', 'unknown')}"],
                    "probes": probes,
                }

        old_api_key = existing.get("SAMUEL_API_KEY") or os.environ.get("SAMUEL_API_KEY", "")
        api_key = clean.get("dashboard_api_key") or old_api_key or secrets.token_hex(24)
        generated_api_key = not old_api_key and not clean.get("dashboard_api_key")
        updates = {
            "SCM_PROVIDER": scm_provider,
            "SCM_URL": scm_url,
            "SCM_USER": clean.get("scm_user") or current("SCM_USER"),
            "SCM_TOKEN": scm_token,
            "SCM_REPO": scm_repo,
            "SCM_BOT_USER": clean.get("scm_bot_user") or current("SCM_BOT_USER"),
            "SCM_REQUIRED_STATUS_CONTEXT": required_status_context,
            "SAMUEL_API_KEY": api_key,
            "SLICE_HMAC_KEY": current("SLICE_HMAC_KEY") or secrets.token_hex(32),
            "SAMUEL_AUDIT_HMAC_KEY": current("SAMUEL_AUDIT_HMAC_KEY") or secrets.token_hex(32),
            "DASHBOARD_PORT": clean.get("dashboard_port") or current("DASHBOARD_PORT") or "7777",
        }
        if clean.get("project_root"):
            updates["PROJECT_ROOT"] = clean["project_root"]
        if env_key:
            updates[env_key] = llm_secret

        default = llm_data.setdefault("default", {})
        if not isinstance(default, dict):
            default = {}
            llm_data["default"] = default
        default["provider"] = llm_provider
        provider_cfg = llm_data.setdefault(llm_provider, {})
        if not isinstance(provider_cfg, dict):
            provider_cfg = {}
            llm_data[llm_provider] = provider_cfg
        if llm_model:
            provider_cfg["model"] = llm_model
        if llm_base_url and llm_provider in {"ollama", "lmstudio"}:
            provider_cfg["url"] = llm_base_url

        try:
            self._atomic_write_many(
                [
                    (llm_path, json.dumps(llm_data, indent=2, ensure_ascii=False) + "\n", None),
                    (env_path, merge_env(existing_text, updates), 0o600),
                ],
                bind_mount_fallback_paths=frozenset({env_path}),
            )
        except OSError as exc:
            log.warning("Dashboard setup persistence failed: %s", exc)
            return {"configured": False, "errors": [f"could not persist setup: {exc}"]}

        self.ensure_directories()
        self._configuration_authority.mark_persisted()
        try:
            from samuel.core.events import ConfigChanged

            self._bus.publish(
                ConfigChanged(
                    payload={
                        "setting": "first_run_setup",
                        "source": "dashboard",
                        "fields": ["scm", "llm", "security", "project_root"],
                        "reason": "dashboard setup persisted; restart required",
                    }
                )
            )
        except Exception:  # noqa: BLE001
            log.exception("Failed to publish dashboard setup change")
        return {
            "configured": True,
            "restart_required": True,
            "probes": probes,
            "api_key": api_key if generated_api_key else "",
            "configuration": self._configuration_authority.status(),
        }

    def configuration_mutation_blocked(self) -> dict[str, Any] | None:
        return self._configuration_authority.blocked_result(success_field="synced")

    def _config_dir(self) -> Path:
        if self._config:
            return Path(str(self._config.get("agent.config_dir", self._root / "config")))
        return self._root / "config"

    @staticmethod
    def _read_json(path: Path, *, strict: bool = False) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if strict:
                raise ValueError(str(exc)) from exc
            log.warning("Could not read setup config %s: %s", path, exc)
            return {}
        if strict and not isinstance(value, dict):
            raise ValueError("top-level JSON value must be an object")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _atomic_write(path: Path, content: str, mode: int | None = None) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(content, encoding="utf-8")
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)

    @staticmethod
    def _atomic_write_many(
        entries: list[tuple[Path, str, int | None]],
        *,
        bind_mount_fallback_paths: frozenset[Path] = frozenset(),
    ) -> None:
        """Stage all files first and roll back if one replacement fails.

        A filesystem cannot atomically rename two independent files at once.
        Staging plus rollback nevertheless prevents a normal write/rename error
        from leaving dashboard setup half-applied.  Docker cannot rename over
        a single-file bind mount.  Callers may explicitly opt such a target
        into the narrowly scoped, synchronised in-place fallback.
        """

        staged: list[tuple[Path, Path, bool]] = []
        originals: dict[Path, tuple[bytes | None, int | None]] = {}
        replaced: list[Path] = []
        try:
            for path, content, mode in entries:
                path.parent.mkdir(parents=True, exist_ok=True)
                originals[path] = (
                    path.read_bytes() if path.exists() else None,
                    (path.stat().st_mode & 0o777) if path.exists() else None,
                )
                temporary = path.with_name(path.name + ".samuel-setup.tmp")
                requires_in_place = False
                try:
                    temporary.write_text(content, encoding="utf-8")
                except OSError as exc:
                    temporary.unlink(missing_ok=True)
                    if (
                        exc.errno not in {errno.EACCES, errno.EPERM}
                        or path not in bind_mount_fallback_paths
                    ):
                        raise
                    # The image-owned /app directory is not writable by the
                    # non-root runtime user, even though Docker exposes the
                    # individual .env mount as rw.  Stage privately in /tmp;
                    # crossing filesystems rules out rename, so use the same
                    # explicitly permitted in-place path below.
                    temporary = SetupHandler._stage_private_file(
                        content.encode("utf-8"), suffix=".tmp"
                    )
                    requires_in_place = True
                if mode is not None:
                    temporary.chmod(mode)
                staged.append((path, temporary, requires_in_place))
            for path, temporary, requires_in_place in staged:
                if requires_in_place:
                    # Register before writing: a controlled write error may
                    # have truncated the bind-mounted target, so rollback must
                    # restore its captured content.
                    replaced.append(path)
                    SetupHandler._write_staged_in_place(
                        path, temporary, mode=temporary.stat().st_mode & 0o777
                    )
                    continue
                try:
                    temporary.replace(path)
                except OSError as exc:
                    if exc.errno != errno.EBUSY or path not in bind_mount_fallback_paths:
                        raise
                    # Register before writing: a controlled write error may
                    # have truncated the bind-mounted target, so rollback must
                    # restore its captured content.
                    replaced.append(path)
                    SetupHandler._write_staged_in_place(
                        path, temporary, mode=temporary.stat().st_mode & 0o777
                    )
                else:
                    replaced.append(path)
        except OSError as write_error:
            rollback_failures: list[str] = []
            for path in reversed(replaced):
                try:
                    old_content, old_mode = originals[path]
                    if old_content is None:
                        path.unlink(missing_ok=True)
                        continue
                    # A denied open may leave the target entirely unchanged.
                    # Rewriting it would repeat the denial and prevent rollback
                    # of files which were already changed earlier in the batch.
                    if path.read_bytes() == old_content and path.stat().st_mode & 0o777 == old_mode:
                        continue
                    rollback = path.with_name(path.name + ".samuel-setup.rollback")
                    try:
                        requires_in_place = False
                        try:
                            rollback.write_bytes(old_content)
                        except OSError as exc:
                            if (
                                exc.errno not in {errno.EACCES, errno.EPERM}
                                or path not in bind_mount_fallback_paths
                            ):
                                raise
                            rollback = SetupHandler._stage_private_file(
                                old_content, suffix=".rollback"
                            )
                            requires_in_place = True
                        if old_mode is not None:
                            rollback.chmod(old_mode)
                        if requires_in_place:
                            SetupHandler._write_staged_in_place(path, rollback, mode=old_mode)
                        else:
                            try:
                                rollback.replace(path)
                            except OSError as exc:
                                if (
                                    exc.errno != errno.EBUSY
                                    or path not in bind_mount_fallback_paths
                                ):
                                    raise
                                SetupHandler._write_staged_in_place(path, rollback, mode=old_mode)
                    finally:
                        rollback.unlink(missing_ok=True)
                except OSError:
                    # A permanently unavailable target must not prevent the
                    # remaining independent files from being restored.
                    rollback_failures.append(path.name)
            if rollback_failures:
                raise OSError(
                    write_error.errno,
                    f"{write_error.strerror}; rollback incomplete: {', '.join(rollback_failures)}",
                ) from write_error
            raise
        finally:
            for _path, temporary, _requires_in_place in staged:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _stage_private_file(content: bytes, *, suffix: str) -> Path:
        """Share private staging when an explicit file mount has an image-owned parent."""
        descriptor, name = tempfile.mkstemp(prefix="samuel-setup-", suffix=suffix)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as staged_file:
                staged_file.write(content)
                staged_file.flush()
                os.fsync(staged_file.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return temporary

    @staticmethod
    def _write_staged_in_place(path: Path, staged: Path, *, mode: int | None) -> None:
        """Synchronously replace one explicit Docker file-bind-mount target.

        The setup process runs while production is stopped.  This retains
        staging and rollback for controlled errors, but is deliberately not a
        substitute for rename atomicity across a process or host crash.
        """

        with path.open("r+b") as target, staged.open("rb") as source:
            target.seek(0)
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
            target.truncate()
            target.flush()
            os.fsync(target.fileno())
        if mode is not None:
            path.chmod(mode)

    @staticmethod
    def _validate_dashboard_values(**values: str) -> list[str]:
        errors: list[str] = []
        if values["scm_provider"] not in {"gitea", "github"}:
            errors.append("SCM provider must be gitea or github")
        parsed = urllib.parse.urlparse(values["scm_url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append("SCM URL must be an absolute http(s) URL")
        elif parsed.username or parsed.password:
            errors.append("SCM URL must not contain credentials")
        if not values["scm_token"]:
            errors.append("SCM token is required")
        repo_parts = values["scm_repo"].split("/")
        if len(repo_parts) != 2 or not all(repo_parts):
            errors.append("SCM repository must use owner/name")
        if values["llm_provider"] not in {
            "claude",
            "deepseek",
            "gemini",
            "openai",
            "openrouter",
            "ollama",
            "lmstudio",
            "manual",
        }:
            errors.append("unknown LLM provider")
        try:
            port = int(values["dashboard_port"])
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            errors.append("dashboard port must be between 1 and 65535")
        project_root = values["project_root"]
        if project_root and not Path(project_root).expanduser().is_dir():
            errors.append("PROJECT_ROOT does not exist or is not a directory")
        llm_base_url = values["llm_base_url"]
        if values["llm_provider"] in {"ollama", "lmstudio"}:
            parsed_llm = urllib.parse.urlparse(llm_base_url)
            if parsed_llm.scheme not in {"http", "https"} or not parsed_llm.netloc:
                errors.append("local LLM URL must be an absolute http(s) URL")
        return errors

    def check_prerequisites(self) -> dict[str, Any]:
        issues: list[str] = []

        for d in REQUIRED_DIRS:
            p = self._root / d
            if not p.exists():
                issues.append(f"directory missing: {d}")

        for env in REQUIRED_ENV:
            legacy = {"SCM_URL": "GITEA_URL", "SCM_TOKEN": "GITEA_TOKEN", "SCM_REPO": "GITEA_REPO"}
            found = False
            if self._secrets:
                try:
                    if self._secrets.get(env):
                        found = True
                except Exception as exc:  # noqa: BLE001
                    log.warning("Secret provider lookup failed for %s: %s", env, exc)
                if not found:
                    try:
                        legacy_key = legacy.get(env, "")
                        if legacy_key and self._secrets.get(legacy_key):
                            found = True
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Secret provider lookup failed for %s: %s", legacy_key, exc)
            else:
                if os.environ.get(env) or os.environ.get(legacy.get(env, "")):
                    found = True
            if not found:
                issues.append(f"env var missing: {env}")

        return {
            "ready": len(issues) == 0,
            "issues": issues,
        }

    def ensure_directories(self) -> list[str]:
        created: list[str] = []
        for d in REQUIRED_DIRS:
            p = self._root / d
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                created.append(d)
        return created

    def sync_labels(self, labels_file: Path | None = None) -> dict[str, Any]:
        if self._scm is None:
            return {"synced": False, "error": "SCM not configured"}

        labels_path = labels_file or (self._root / "config" / "labels.json")
        if not labels_path.exists():
            return {"synced": False, "error": f"Labels file not found: {labels_path}"}

        try:
            with open(labels_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            return {"synced": False, "error": f"Failed to read {labels_path}: {exc}"}

        desired = data.get("labels", [])
        try:
            existing_raw = self._scm.list_labels()
        except Exception as exc:
            log.exception("Failed to list remote labels")
            return {"synced": False, "error": f"list_labels failed: {exc}"}

        existing = {l["name"]: l for l in existing_raw}
        created: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for label in desired:
            name = label["name"]
            if name in existing:
                skipped.append(name)
                continue
            try:
                self._scm.create_label(
                    name=name,
                    color=label.get("color", "cccccc"),
                    description=label.get("description", ""),
                )
                created.append(name)
                log.info("Created label: %s", name)
            except Exception as exc:
                msg = f"{name}: {exc}"
                errors.append(msg)
                log.warning("Failed to create label %s: %s", name, exc)

        return {
            "synced": len(errors) == 0,
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "total": len(desired),
        }
