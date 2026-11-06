from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from samuel.local_release import (
    LocalReleaseError,
    ReleaseLayout,
    _child_environment,
    activate_release,
    initialize_layout,
    stage_release,
    validate_release_inputs,
)


def _layout(tmp_path: Path) -> ReleaseLayout:
    return ReleaseLayout(
        install_root=tmp_path / "opt" / "samuel",
        config_root=tmp_path / "etc" / "samuel",
        data_root=tmp_path / "var" / "lib" / "samuel",
        log_root=tmp_path / "var" / "log" / "samuel",
        service_root=tmp_path / "srv" / "samuel",
    ).validated()


def _artifact(path: Path, content: bytes) -> dict[str, object]:
    path.write_bytes(content)
    return {
        "name": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


def _release_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    version = "2.0.0a9"
    wheel = tmp_path / f"samuel-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"samuel-{version}.dist-info/METADATA",
            f"Name: samuel\nVersion: {version}\n",
        )
    lock = tmp_path / f"samuel-runtime-{version}.lock"
    lock_artifact = _artifact(lock, b"pydantic==2.12.5 --hash=sha256:" + b"a" * 64 + b"\n")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product": "samuel",
                "version": version,
                "tag": f"v{version}",
                "commit": "b" * 40,
                "artifacts": [
                    {
                        "name": wheel.name,
                        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                        "size": wheel.stat().st_size,
                    },
                    lock_artifact,
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest, wheel, lock


def _write_verified_release(layout: ReleaseLayout, version: str) -> Path:
    release = layout.releases_root / version
    (release / "bin").mkdir(parents=True)
    launcher = release / "bin" / "samuel"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    (release / "release.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product": "samuel",
                "version": version,
                "revision": "c" * 40,
            }
        ),
        encoding="utf-8",
    )
    return release


def test_manifest_binds_wheel_lock_version_and_revision(tmp_path: Path) -> None:
    manifest, wheel, lock = _release_inputs(tmp_path)

    identity = validate_release_inputs(
        manifest_path=manifest,
        wheel_path=wheel,
        runtime_lock_path=lock,
    )

    assert identity["version"] == "2.0.0a9"
    assert identity["revision"] == "b" * 40
    lock.write_text("changed", encoding="utf-8")
    with pytest.raises(LocalReleaseError, match="does not match"):
        validate_release_inputs(
            manifest_path=manifest,
            wheel_path=wheel,
            runtime_lock_path=lock,
        )


def test_runtime_lock_name_must_match_release_version(tmp_path: Path) -> None:
    manifest, wheel, lock = _release_inputs(tmp_path)
    wrong_name = tmp_path / "requirements-container.lock"
    lock.rename(wrong_name)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["artifacts"][1]["name"] = wrong_name.name
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(LocalReleaseError, match="version-bound name"):
        validate_release_inputs(
            manifest_path=manifest,
            wheel_path=wheel,
            runtime_lock_path=wrong_name,
        )


def test_layout_roots_are_absolute_and_non_overlapping(tmp_path: Path) -> None:
    with pytest.raises(LocalReleaseError, match="must be absolute"):
        ReleaseLayout(install_root=Path("relative")).validated()
    with pytest.raises(LocalReleaseError, match="must not overlap"):
        ReleaseLayout(
            install_root=tmp_path / "samuel",
            config_root=tmp_path / "samuel" / "config",
            data_root=tmp_path / "data",
            log_root=tmp_path / "log",
            service_root=tmp_path / "service",
        ).validated()


def test_initialization_separates_core_config_state_and_custom(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    defaults = tmp_path / "defaults"
    (defaults / "workflows").mkdir(parents=True)
    (defaults / "workflows" / "standard.json").write_text("{}\n", encoding="utf-8")
    (defaults / "agent.json").write_text(
        json.dumps({"data_dir": "data", "config_dir": "config", "workspace": {"work_dir": "w"}}),
        encoding="utf-8",
    )
    (defaults / "audit.json").write_text(
        json.dumps(
            {
                "sinks": [
                    {"type": "jsonl", "path": "data/logs/agent.jsonl"},
                    {"type": "sarif", "path": "data/logs/findings.sarif"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (defaults / "privacy.json").write_text(
        json.dumps({"retention": {"managed_backup_dir": "data/backups"}}),
        encoding="utf-8",
    )
    (defaults / "license.json").write_text("secret-like legacy data", encoding="utf-8")

    initialize_layout(layout, defaults)

    agent = json.loads((layout.config_dir / "agent.json").read_text(encoding="utf-8"))
    audit = json.loads((layout.config_dir / "audit.json").read_text(encoding="utf-8"))
    privacy = json.loads((layout.config_dir / "privacy.json").read_text(encoding="utf-8"))
    assert agent["config_dir"] == str(layout.config_dir)
    assert agent["data_dir"] == str(layout.data_root)
    assert agent["workspace"]["work_dir"] == str(layout.workspaces_root)
    assert agent["log_file"] == str(layout.log_root / "samuel.log")
    assert all(str(layout.data_root / "logs") in item["path"] for item in audit["sinks"])
    assert privacy["retention"]["managed_backup_dir"] == str(layout.backups_root)
    assert not (layout.config_dir / "license.json").exists()
    assert layout.extensions_root.is_dir()

    operator_file = layout.config_root / ".env"
    operator_file.write_text("TOKEN=preserve\n", encoding="utf-8")
    with pytest.raises(LocalReleaseError, match="refusing to merge"):
        initialize_layout(layout, defaults)
    assert operator_file.read_text(encoding="utf-8") == "TOKEN=preserve\n"


def test_stage_never_replaces_existing_release_or_current(tmp_path: Path, monkeypatch) -> None:
    layout = _layout(tmp_path)
    manifest, wheel, lock = _release_inputs(tmp_path)
    current_target = _write_verified_release(layout, "2.0.0a8")
    layout.install_root.mkdir(parents=True, exist_ok=True)
    layout.current.symlink_to(current_target)

    def fake_run(command, *, cwd, env):
        if command[1:3] == ["-m", "venv"]:
            (Path(command[3]) / "bin").mkdir(parents=True)
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("samuel.local_release._run", fake_run)
    monkeypatch.setattr(
        "samuel.local_release._probe_release",
        lambda _path, *, version, revision: {
            "version": version,
            "revision": revision,
            "module": "isolated/site-packages/samuel/__init__.py",
            "metadata": "isolated/site-packages/samuel.dist-info",
        },
    )

    release = stage_release(
        layout=layout,
        manifest_path=manifest,
        wheel_path=wheel,
        runtime_lock_path=lock,
    )

    assert release == layout.releases_root / "2.0.0a9"
    assert layout.current.resolve() == current_target.resolve()
    assert json.loads((release / "release.json").read_text())["wheel_sha256"]
    with pytest.raises(LocalReleaseError, match="in-place"):
        stage_release(
            layout=layout,
            manifest_path=manifest,
            wheel_path=wheel,
            runtime_lock_path=lock,
        )


def test_partial_stage_has_no_receipt_and_cannot_replace_current(
    tmp_path: Path, monkeypatch
) -> None:
    layout = _layout(tmp_path)
    manifest, wheel, lock = _release_inputs(tmp_path)
    old = _write_verified_release(layout, "2.0.0a8")
    layout.current.symlink_to(Path("releases") / old.name)

    def fail_install(command, *, cwd, env):
        if command[1:3] == ["-m", "venv"]:
            (Path(command[3]) / "bin").mkdir(parents=True)
            return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise LocalReleaseError("dependency installation failed")

    monkeypatch.setattr("samuel.local_release._run", fail_install)

    with pytest.raises(LocalReleaseError, match="dependency installation failed"):
        stage_release(
            layout=layout,
            manifest_path=manifest,
            wheel_path=wheel,
            runtime_lock_path=lock,
        )
    partial = layout.releases_root / "2.0.0a9"
    assert partial.is_dir()
    assert not (partial / "release.json").exists()
    assert layout.current.resolve() == old.resolve()


def test_activation_is_atomic_cas_and_refuses_non_symlink(tmp_path: Path, monkeypatch) -> None:
    layout = _layout(tmp_path)
    old = _write_verified_release(layout, "2.0.0a8")
    new = _write_verified_release(layout, "2.0.0a9")
    layout.current.symlink_to(Path("releases") / old.name)
    monkeypatch.setattr(
        "samuel.local_release._probe_release",
        lambda _path, *, version, revision: {"version": version, "revision": revision},
    )

    with pytest.raises(LocalReleaseError, match="active release changed"):
        activate_release(layout, version=new.name, expected_current=None)
    previous = activate_release(layout, version=new.name, expected_current=old.name)
    assert previous == old.name
    assert layout.current.is_symlink()
    assert layout.current.resolve() == new.resolve()

    layout.current.unlink()
    layout.current.write_text("not a symlink", encoding="utf-8")
    with pytest.raises(LocalReleaseError, match="not a symlink"):
        activate_release(layout, version=old.name, expected_current=new.name)


def test_activation_rejects_old_product_overlay(tmp_path: Path, monkeypatch) -> None:
    layout = _layout(tmp_path)
    release = _write_verified_release(layout, "2.0.0a9")
    (layout.install_root / "samuel.egg-info").mkdir()
    monkeypatch.setattr(
        "samuel.local_release._probe_release",
        lambda _path, *, version, revision: {"version": version, "revision": revision},
    )

    with pytest.raises(LocalReleaseError, match="unclassified.*samuel.egg-info"):
        activate_release(layout, version=release.name, expected_current=None)

    (layout.install_root / "samuel.egg-info").rmdir()
    (layout.releases_root / ".staging-unclassified").mkdir()
    with pytest.raises(LocalReleaseError, match="unclassified.*staging-unclassified"):
        activate_release(layout, version=release.name, expected_current=None)


def test_child_environment_rejects_old_checkout_import_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/old/checkout")
    monkeypatch.setenv("PYTHONHOME", "/old/runtime")
    monkeypatch.setenv("SCM_TOKEN", "secret")

    child = _child_environment("d" * 40)

    assert "PYTHONPATH" not in child
    assert "PYTHONHOME" not in child
    assert "SCM_TOKEN" not in child
    assert child["PYTHONNOUSERSITE"] == "1"
    assert child["SAMUEL_BUILD_REVISION"] == "d" * 40
