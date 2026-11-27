from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import subprocess
import tarfile
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from tools.release_gate import (
    ReleaseGateError,
    artifact_versions,
    materialize_runtime_lock,
    restore_remote_annotated_tag,
    run_gate,
    verify_artifacts,
    verify_changelog,
    verify_legacy_authority_window,
    verify_runtime_surfaces,
    verify_source_identity,
    verify_version_authority,
    verify_version_override,
    write_manifest,
)

ROOT = Path(__file__).parents[1]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _release_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        """[project]
name = "samuel"
dynamic = ["version"]

[tool.setuptools_scm]
version_scheme = "guess-next-dev"
local_scheme = "node-and-date"
fallback_version = "0+unknown"

[tool.setuptools_scm.tag]
prefix = "v"
strict = true
regex = '^(?P<version>(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)(?:(?:a|b|rc)(?:0|[1-9]\\d*))?)$'
"""
    )
    (root / "CHANGELOG.md").write_text("## [2.0.0a1] - 2026-08-25\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Release Test")
    _git(root, "config", "user.email", "release@example.invalid")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "release")
    _git(root, "branch", "-M", "main")
    _git(root, "branch", "origin/main")
    return root


def test_pre_tag_binds_clean_head_and_rejects_existing_tag(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    expected = _git(root, "rev-parse", "HEAD")

    assert verify_source_identity(
        root,
        tag="v2.0.0a1",
        commit_ref="origin/main",
        mode="pre-tag",
    ) == ("2.0.0a1", expected)

    _git(root, "tag", "-a", "v2.0.0a1", "-m", "release")
    assert verify_source_identity(
        root,
        tag="v2.0.0a1",
        commit_ref="origin/main",
        mode="post-tag",
    ) == ("2.0.0a1", expected)
    with pytest.raises(ReleaseGateError, match="create-only"):
        verify_source_identity(
            root,
            tag="v2.0.0a1",
            commit_ref="origin/main",
            mode="pre-tag",
        )


def test_post_tag_requires_annotated_tag_on_exact_head(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    _git(root, "tag", "v2.0.0a1")

    with pytest.raises(ReleaseGateError, match="not annotated"):
        verify_source_identity(
            root,
            tag="v2.0.0a1",
            commit_ref="origin/main",
            mode="post-tag",
        )


def test_restore_remote_tag_recovers_checkout_lightweight_ref(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    remote = tmp_path / "remote.git"
    _git(root, "init", "--bare", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "tag", "-a", "v2.0.0a1", "-m", "release")
    _git(root, "push", "origin", "refs/tags/v2.0.0a1")

    _git(root, "update-ref", "refs/tags/v2.0.0a1", "HEAD")
    assert _git(root, "cat-file", "-t", "refs/tags/v2.0.0a1") == "commit"

    restore_remote_annotated_tag(root, tag="v2.0.0a1")

    assert _git(root, "cat-file", "-t", "refs/tags/v2.0.0a1") == "tag"
    assert (
        verify_source_identity(
            root,
            tag="v2.0.0a1",
            commit_ref="origin/main",
            mode="post-tag",
        )[0]
        == "2.0.0a1"
    )


def test_restore_remote_tag_rejects_lightweight_remote(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    remote = tmp_path / "remote.git"
    _git(root, "init", "--bare", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "tag", "v2.0.0a1")
    _git(root, "push", "origin", "refs/tags/v2.0.0a1")

    with pytest.raises(ReleaseGateError, match="remote tag.*not annotated"):
        restore_remote_annotated_tag(root, tag="v2.0.0a1")


def test_remote_tag_restoration_is_post_tag_only(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)

    with pytest.raises(ReleaseGateError, match="only valid in post-tag mode"):
        run_gate(
            root=root,
            dist_dir=tmp_path,
            tag="v2.0.0a1",
            commit_ref="origin/main",
            mode="pre-tag",
            restore_remote_tag=True,
        )


def test_gate_rejects_dirty_wrong_ref_invalid_and_mismatched_tags(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    (root / "dirty").write_text("x")
    with pytest.raises(ReleaseGateError, match="not clean"):
        verify_source_identity(
            root,
            tag="v2.0.0a1",
            commit_ref="origin/main",
            mode="pre-tag",
        )

    (root / "dirty").unlink()
    with pytest.raises(ReleaseGateError, match="invalid product tag"):
        verify_source_identity(
            root,
            tag="phase-13-complete",
            commit_ref="origin/main",
            mode="pre-tag",
        )
    _git(root, "commit", "--allow-empty", "-q", "-m", "newer")
    with pytest.raises(ReleaseGateError, match="not the intended"):
        verify_source_identity(
            root,
            tag="v2.0.0a1",
            commit_ref="origin/main",
            mode="pre-tag",
        )


def _write_artifacts(dist_dir: Path, version: str) -> tuple[Path, Path]:
    wheel = dist_dir / "samuel-2.0.0a1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("samuel-2.0.0a1.dist-info/METADATA", f"Version: {version}\n")

    sdist = dist_dir / "samuel-2.0.0a1.tar.gz"
    payload = f"Version: {version}\n".encode()
    with tarfile.open(sdist, "w:gz") as archive:
        info = tarfile.TarInfo("samuel-2.0.0a1/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return wheel, sdist


def test_artifacts_use_embedded_metadata_and_manifest_binds_checksums(tmp_path: Path) -> None:
    wheel, sdist = _write_artifacts(tmp_path, "2.0.0a1")

    assert artifact_versions(tmp_path) == {wheel: "2.0.0a1", sdist: "2.0.0a1"}

    manifest_path = write_manifest(
        tmp_path,
        tag="v2.0.0a1",
        version="2.0.0a1",
        commit="a" * 40,
        artifacts=[sdist, wheel],
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["tag"] == "v2.0.0a1"
    assert manifest["commit"] == "a" * 40
    assert [item["name"] for item in manifest["artifacts"]] == sorted([wheel.name, sdist.name])
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])


def test_runtime_lock_is_materialized_as_versioned_release_asset(tmp_path: Path) -> None:
    root = tmp_path / "root"
    dist = tmp_path / "dist"
    (root / "containers").mkdir(parents=True)
    dist.mkdir()
    content = b"pydantic==2.12.5 --hash=sha256:" + b"a" * 64 + b"\n"
    (root / "requirements-container.lock").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    (root / "containers" / "lock-policy.json").write_text(
        json.dumps(
            {
                "lock_contract": {
                    "runtime_lock": {
                        "path": "requirements-container.lock",
                        "sha256": f"sha256:{digest}",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    asset = materialize_runtime_lock(root, dist, "2.0.0a9")

    assert asset.name == "samuel-runtime-2.0.0a9.lock"
    assert asset.read_bytes() == content
    asset.write_text("drift", encoding="utf-8")
    with pytest.raises(ReleaseGateError, match="existing runtime lock asset differs"):
        materialize_runtime_lock(root, dist, "2.0.0a9")


def test_artifact_cardinality_and_changelog_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ReleaseGateError, match="exactly one"):
        artifact_versions(tmp_path)

    root = tmp_path / "docs"
    root.mkdir()
    (root / "CHANGELOG.md").write_text("## [Unreleased]\n")
    with pytest.raises(ReleaseGateError, match="no dated"):
        verify_changelog(root, "2.0.0a1")

    _write_artifacts(tmp_path, "2.0.0a0")
    with pytest.raises(ReleaseGateError, match="artifact version mismatch"):
        verify_artifacts(tmp_path, "2.0.0a1")


def test_static_or_unconfigured_version_authority_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "static"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "samuel"\nversion = "2.0.0a2"\n')

    with pytest.raises(ReleaseGateError, match="must not define a static"):
        verify_version_authority(root, tag="v2.0.0a2")


def test_pretag_override_is_exact_and_forbidden_post_tag() -> None:
    key = "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SAMUEL"

    verify_version_override(mode="pre-tag", version="2.0.0a3", environ={key: "2.0.0a3"})
    with pytest.raises(ReleaseGateError, match="pre-tag build must set"):
        verify_version_override(mode="pre-tag", version="2.0.0a3", environ={})
    with pytest.raises(ReleaseGateError, match="post-tag build must not set"):
        verify_version_override(mode="post-tag", version="2.0.0a3", environ={key: "2.0.0a3"})
    verify_version_override(mode="post-tag", version="2.0.0a3", environ={})


def test_legacy_authority_is_allowed_only_for_introduction_release(tmp_path: Path) -> None:
    config = tmp_path / "config"
    workflows = config / "workflows"
    workflows.mkdir(parents=True)
    (config / "gates.legacy.json").write_text("{}", encoding="utf-8")
    (workflows / "standard.json").write_text(
        '{"name":"standard","steps":[],"legacy_steps":[]}', encoding="utf-8"
    )

    verify_legacy_authority_window(tmp_path, "2.0.0a4")
    with pytest.raises(ReleaseGateError, match="expired after 2.0.0a4"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_current_tree_satisfies_following_release_authority_contract() -> None:
    verify_legacy_authority_window(ROOT, "2.0.0a5")


def _rollout_document() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / "docs" / "rollout" / "issue-399.json").read_text()),
    )


def _write_rollout_evidence(
    tmp_path: Path, document: dict[str, Any] | None = None
) -> dict[str, Any]:
    evidence_dir = tmp_path / "docs" / "rollout"
    evidence_dir.mkdir(parents=True)
    schema = ROOT / "docs" / "rollout" / "issue-399.schema.json"
    (evidence_dir / schema.name).write_bytes(schema.read_bytes())
    value = deepcopy(document if document is not None else _rollout_document())
    (evidence_dir / "issue-399.json").write_text(
        json.dumps(value),
        encoding="utf-8",
    )
    return value


def _case(document: dict, case_id: str) -> dict:
    return next(case for case in document["cases"] if case["id"] == case_id)


def test_following_release_accepts_complete_bound_rollout_evidence(tmp_path: Path) -> None:
    _write_rollout_evidence(tmp_path)

    verify_legacy_authority_window(tmp_path, "2.0.0a5")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_sha", "abc123"),
        ("head_sha", "abc123"),
        ("contract_hash", "sha256:short"),
        ("policy_digest", "sha256:short"),
        ("observation_key", "run:success"),
        ("correlation_id", "not-a-uuid"),
        ("observed_at", "2026-08-28T14:08:53+02:00"),
    ],
)
def test_rollout_evidence_rejects_invalid_subject_binding(
    tmp_path: Path, field: str, value: str
) -> None:
    document = _rollout_document()
    _case(document, "success")["subject"][field] = value
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="rollout evidence is invalid"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_rollout_evidence_rejects_missing_binding_field_and_placeholder(tmp_path: Path) -> None:
    document = _rollout_document()
    del _case(document, "success")["subject"]["contract_hash"]
    _case(document, "required_gate_block")["evidence"] = ["x"]
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="missing contract_hash"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_rollout_evidence_requires_each_case_exactly_once(tmp_path: Path, mutation: str) -> None:
    document = _rollout_document()
    if mutation == "missing":
        document["cases"].pop()
    else:
        document["cases"][-1] = deepcopy(document["cases"][0])
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="each required case exactly once|duplicate"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_success_requires_pr_bound_to_subject(tmp_path: Path) -> None:
    document = _rollout_document()
    success = _case(document, "success")
    success["evidence"]["pr_created"]["head_sha"] = "f" * 40
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="base/head must match"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_success_without_pr_is_rejected(tmp_path: Path) -> None:
    document = _rollout_document()
    _case(document, "success")["evidence"]["pr_created"] = {"count": 0}
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="invalid fields"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_healing_requires_new_fast_forward_head_and_one_attempt(tmp_path: Path) -> None:
    document = _rollout_document()
    healing = _case(document, "evidence_healing_new_head")["evidence"]
    healing["healing"]["healed_parent_sha"] = "f" * 40
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="fast-forward heal"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_terminal_refail_requires_no_second_attempt_and_no_pr(tmp_path: Path) -> None:
    document = _rollout_document()
    refail = _case(document, "terminal_refail")["evidence"]
    refail["healing"]["second_attempts"] = 1
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="second_attempts must be 0"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_terminal_refail_with_pr_is_rejected(tmp_path: Path) -> None:
    document = _rollout_document()
    refail = _case(document, "terminal_refail")["evidence"]
    refail["pr_created"] = {
        "count": 1,
        "number": 99,
        "url": "https://example.test/repo/pulls/99",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
    }
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="invalid fields"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_rollback_requires_closed_mode_order_and_identical_state(tmp_path: Path) -> None:
    document = _rollout_document()
    rollback = _case(document, "legacy_rollback")["evidence"]
    rollback["transitions"][1]["gate_profile"] = "default"
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="gate_profile must be 'legacy'"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_rollback_requires_identical_state_without_migration(tmp_path: Path) -> None:
    document = _rollout_document()
    rollback = _case(document, "legacy_rollback")["evidence"]
    rollback["state_hashes"]["after"]["quality_metrics.json"] = "sha256:" + "f" * 64
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="prove no data migration"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_rollout_evidence_is_bound_to_exact_schema_bytes(tmp_path: Path) -> None:
    document = _rollout_document()
    document["schema_digest"] = "sha256:" + "0" * 64
    _write_rollout_evidence(tmp_path, document)

    with pytest.raises(ReleaseGateError, match="schema_digest"):
        verify_legacy_authority_window(tmp_path, "2.0.0a5")


def test_current_runtime_surfaces_match_distribution_metadata() -> None:
    verify_runtime_surfaces(importlib.metadata.version("samuel"))
