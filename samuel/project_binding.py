"""Explicit stopped-installation OCI project registration (#988). No provisioning."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from samuel.core.git_remote import canonical_repository_url
from samuel.core.project_binding import (
    PROJECT_BINDING_FILE,
    PROJECT_BINDING_SCHEMA,
    inspect_project,
    paths_overlap,
    project_overlay,
    read_project_binding,
    regular_path,
    validate_binding,
)
from samuel.slices.setup.env_io import merge_env, parse_env


def verify_project_registration(config_root: Path) -> dict[str, Any] | None:
    binding = read_project_binding(config_root / "config")
    overlay = config_root / "compose/docker-compose.project.yml"
    if binding is None and not overlay.exists() and not overlay.is_symlink():
        return None
    if binding is None or not regular_path(overlay) or not overlay.is_file():
        raise ValueError("project registration is incomplete")
    if overlay.read_text() != project_overlay(binding["host_source"], binding["container_target"]):
        raise ValueError("registered project Compose mount changed")
    installation = config_root / ".container-install.json"
    if not regular_path(installation) or not installation.is_file():
        raise ValueError("project installation binding is unavailable")
    if hashlib.sha256(installation.read_bytes()).hexdigest() != binding["installation_sha256"]:
        raise ValueError("project installation binding changed")
    env_path = config_root / ".env"
    if not regular_path(env_path) or not env_path.is_file():
        raise ValueError("project environment is unavailable")
    if parse_env(env_path.read_text()).get("PROJECT_ROOT") != binding["container_target"]:
        raise ValueError("PROJECT_ROOT differs from registered project mount")
    return binding


def register_project(
    config_root: Path,
    *,
    source: Path,
    host_source: str,
    container_target: str,
    repository: str,
    revision: str,
) -> dict[str, Any]:
    """Inspect as runtime owner, then register. Never chown/clone/checkout the source."""
    installation_path = config_root / ".container-install.json"
    if not regular_path(config_root) or not regular_path(installation_path):
        raise ValueError("installation path is unsafe")
    raw_installation = installation_path.read_bytes()
    installation = json.loads(raw_installation)
    owner = (installation["uid"], installation["gid"])
    content = project_overlay(host_source, container_target)
    binding = validate_binding(
        {
            "schema": PROJECT_BINDING_SCHEMA,
            "profile": "local-reference",
            "host_source": host_source,
            "container_target": container_target,
            "repository": canonical_repository_url(repository),
            "initial_revision": revision,
            "uid": owner[0],
            "gid": owner[1],
            "installation_sha256": hashlib.sha256(raw_installation).hexdigest(),
            "compose_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "source_identity": {"device": source.stat().st_dev, "inode": source.stat().st_ino},
        }
    )
    for key in ("config_root", "data_root", "work_root", "log_root", "backup_root"):
        if paths_overlap(Path(host_source), Path(installation[key])):
            raise ValueError("project source overlaps installation storage")
    toolchain = config_root / ".verifier-toolchain.json"
    if toolchain.exists():
        if not regular_path(toolchain):
            raise ValueError("toolchain registration is unsafe")
        if paths_overlap(Path(host_source), Path(json.loads(toolchain.read_text())["host_root"])):
            raise ValueError("project source overlaps verifier toolchain")
    if not regular_path(source):
        raise ValueError("project source is unsafe")
    storage_error = _check_local_storage(source)
    if storage_error:
        raise ValueError(storage_error)
    existing = verify_project_registration(config_root)
    if existing is not None:
        if existing != binding:
            raise ValueError("project already registered; replacement requires a new binding")
    if not (source / ".git").is_dir():
        raise ValueError("project must be a standalone Git repository")
    # The bootstrap container runs as root only to write operator registration.
    # Source inspection uses the actual image identity, without changing ownership.
    previous = os.geteuid(), os.getegid()
    groups = os.getgroups()
    try:
        if previous[0] == 0:
            os.setgroups([owner[1]])
            os.setegid(owner[1])
            os.seteuid(owner[0])
        result = inspect_project(
            source,
            repository=repository,
            binding=binding,
            expected_revision=revision,
            check_runtime_identity=False,
            check_mount_target=False,
        )
    finally:
        if previous[0] == 0:
            os.seteuid(previous[0])
            os.setegid(previous[1])
            os.setgroups(groups)
    if not result["passed"]:
        raise ValueError(f"project registration blocked: {result['reason_code']}")
    if existing is not None:
        return existing
    env_path = config_root / ".env"
    if not regular_path(env_path) or not env_path.is_file():
        raise ValueError("operator environment is unsafe")
    old_env = env_path.read_text()
    if parse_env(old_env).get("PROJECT_ROOT") not in (None, "", container_target):
        raise ValueError("existing PROJECT_ROOT differs; preserve operator configuration")
    targets = {
        config_root / "compose/docker-compose.project.yml": content,
        config_root / "config" / PROJECT_BINDING_FILE: json.dumps(binding, indent=2, sort_keys=True)
        + "\n",
    }
    if any(p.exists() or p.is_symlink() or not regular_path(p.parent) for p in targets):
        raise ValueError("project registration destination already exists or is unsafe")
    prepared_env = env_path.with_name(".env.project-prepared")
    created: list[Path] = []
    try:
        for path, value in {
            prepared_env: merge_env(old_env, {"PROJECT_ROOT": container_target}),
            **targets,
        }.items():
            with path.open("x", encoding="utf-8") as stream:
                created.append(path)
                os.fchmod(stream.fileno(), 0o600)
                os.fchown(stream.fileno(), *owner)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
        prepared_env.replace(env_path)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    verify_project_registration(config_root)
    return binding


def _check_local_storage(
    root: Path, work: Path | None = None, minimum_bytes: int = 0
) -> str | None:
    from samuel.adapters.workspace.git import _NETWORK_FILESYSTEMS, _mount_type
    from samuel.core.workspaces import WorkspaceError

    try:
        for path in (root,) if work is None else (root, work):
            if _mount_type(path) in _NETWORK_FILESYSTEMS:
                return "project_filesystem_remote"
        if work is not None:
            existing = next(path for path in (work, *work.parents) if path.exists())
            info = os.statvfs(existing)
            if info.f_bavail * info.f_frsize < minimum_bytes or info.f_favail == 0:
                return "project_workspace_capacity_insufficient"
    except (OSError, WorkspaceError):
        return "project_filesystem_unknown"
    return None


def configured_project_status(
    config_dir: Path,
    *,
    root: Path | None = None,
    repository: str | None = None,
) -> dict[str, Any]:
    """Compose existing config/SCM identity without bootstrap or provider contact."""
    from samuel.adapters.state.sqlite import resolve_data_dir
    from samuel.adapters.workspace.git import resolve_work_dir
    from samuel.core.bootstrap import _build_scm_adapter
    from samuel.core.config import SCMConfig
    from samuel.core.project_binding import configured_project_root, project_readiness

    try:
        env_path = config_dir.resolve().parent / ".env"
        dotenv = parse_env(env_path.read_text()) if env_path.is_file() else {}

        def get(key: str) -> str:
            return os.environ.get(key, dotenv.get(key, ""))

        if root is None:
            root = configured_project_root(config_dir, get("PROJECT_ROOT"))
        if repository is None and get("SCM_URL") and get("SCM_REPO"):
            scm_config = SCMConfig(
                provider=get("SCM_PROVIDER") or "gitea",
                url=get("SCM_URL"),
                repo=get("SCM_REPO"),
                token="",
            )
            repository = _build_scm_adapter(scm_config).repository_identity
        config_file = config_dir / "agent.json"
        agent = json.loads(config_file.read_text()) if config_file.is_file() else {}

        work = resolve_work_dir(
            agent.get("workspace", {}).get("work_dir", "../samuel-workspaces"),
            config_dir=config_dir,
        )
        data = resolve_data_dir(agent.get("data_dir", "data"), config_dir=config_dir)
        registered = (config_dir / PROJECT_BINDING_FILE).exists()
        if registered and root is not None:
            minimum = (
                int(agent.get("workspace", {}).get("minimum_free_mebibytes", 512)) * 1024 * 1024
            )
            storage_error = _check_local_storage(root, work, minimum)
            if storage_error:
                return {
                    "passed": False,
                    "status": "blocked",
                    "reason_code": storage_error,
                    "registered": True,
                }
        return project_readiness(
            config_dir,
            root=root,
            repository=repository,
            protected_roots=(config_dir, work, data),
        )
    except (OSError, ValueError, TypeError, KeyError):
        return {
            "passed": False,
            "status": "blocked",
            "reason_code": "project_configuration_invalid",
        }
