from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_wiki import IDENTITY
from tools import wiki, wiki_publish


def test_script_entrypoint_loads_from_repository_root() -> None:
    completed = subprocess.run(
        [sys.executable, str(wiki.ROOT / "tools" / "wiki_publish.py"), "--help"],
        cwd=wiki.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--source-url-template" in completed.stdout


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _bare_remote(tmp_path: Path, *, with_placeholder: bool) -> tuple[Path, str | None]:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    if not with_placeholder:
        return remote, None
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--initial-branch=main", str(seed))
    (seed / "Home.md").write_text("Willkommen im Wiki.\n", encoding="utf-8")
    _git(seed, "add", "Home.md")
    _git(
        seed,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "placeholder",
    )
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "origin", "main")
    return remote, _git(seed, "rev-parse", "HEAD")


def _publication_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict]:
    manifest = wiki._read_json(wiki.MANIFEST_PATH)
    pages, receipt = wiki.build_bundle(manifest=manifest, identity=IDENTITY)
    source = tmp_path / "source"
    (source / "wiki").mkdir(parents=True)
    for path, content in pages.items():
        target = source / "wiki" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    monkeypatch.setattr(wiki, "ROOT", source)
    monkeypatch.setattr(wiki, "check_materialized", lambda: receipt)
    monkeypatch.setattr(wiki, "_read_json", lambda _: manifest)
    return manifest, receipt


def test_projection_maps_home_sidebar_and_bound_source_links() -> None:
    manifest = wiki._read_json(wiki.MANIFEST_PATH)
    pages, receipt = wiki.build_bundle(manifest=manifest, identity=IDENTITY)
    projected = wiki_publish.project_pages(
        pages,
        manifest,
        receipt,
        "https://scm.example/org/repo/blob/{head_sha}/{path}",
    )

    assert len(projected) == 12
    assert "Home.md" in projected
    assert "_Sidebar.md" in projected
    home = projected["Home.md"].decode()
    assert "(Architecture)" in home
    assert f"https://scm.example/org/repo/blob/{IDENTITY['head_sha']}/README.md" in home
    assert "../../README.md" not in home


@pytest.mark.parametrize("with_placeholder", [False, True])
def test_publish_and_idempotent_noop_on_local_git_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_placeholder: bool
) -> None:
    _publication_fixture(tmp_path, monkeypatch)
    remote, placeholder_head = _bare_remote(tmp_path, with_placeholder=with_placeholder)
    receipt_path = tmp_path / "publication.json"
    kwargs = {
        "remote": str(remote),
        "source_url_template": "https://scm.example/org/repo/blob/{head_sha}/{path}",
        "branch": "main",
        "receipt_path": receipt_path,
        "adopt_existing_head": placeholder_head,
    }

    first = wiki_publish.publish(**kwargs)
    receipt_path.unlink()
    second = wiki_publish.publish(**kwargs)

    assert first["status"] == "published"
    assert second["status"] == "unchanged"
    assert second["target_commit"] == first["target_commit"]
    assert second["previous_target_commit"] == first["target_commit"]
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == "unchanged"
    inspect = tmp_path / "inspect"
    _git(tmp_path, "clone", str(remote), str(inspect))
    assert (inspect / "Home.md").is_file()
    assert (inspect / wiki_publish.MARKER).is_file()


def test_unmanaged_or_tampered_remote_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publication_fixture(tmp_path, monkeypatch)
    remote, placeholder_head = _bare_remote(tmp_path, with_placeholder=True)
    kwargs = {
        "remote": str(remote),
        "source_url_template": "https://scm.example/org/repo/blob/{head_sha}/{path}",
        "branch": "main",
        "receipt_path": tmp_path / "publication.json",
    }

    with pytest.raises(wiki_publish.PublishError, match="exact --adopt-existing-head"):
        wiki_publish.publish(**kwargs, adopt_existing_head="0" * 40)

    wiki_publish.publish(**kwargs, adopt_existing_head=placeholder_head)
    tamper = tmp_path / "tamper"
    _git(tmp_path, "clone", str(remote), str(tamper))
    (tamper / "foreign.md").write_text("foreign\n", encoding="utf-8")
    _git(tamper, "add", "foreign.md")
    _git(
        tamper,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "foreign",
    )
    _git(tamper, "push", "origin", "main")

    with pytest.raises(wiki_publish.PublishError, match="unknown or missing managed files"):
        wiki_publish.publish(**kwargs)


def test_concurrent_remote_progress_blocks_without_force_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publication_fixture(tmp_path, monkeypatch)
    remote, placeholder_head = _bare_remote(tmp_path, with_placeholder=True)
    original_git = wiki_publish._git
    raced = False

    def advance_remote_before_publisher_push(cwd: Path, *args: str, check: bool = True) -> str:
        nonlocal raced
        if args[:2] == ("push", "origin") and not raced:
            raced = True
            racer = tmp_path / "racer"
            _git(tmp_path, "clone", str(remote), str(racer))
            (racer / "race.md").write_text("concurrent update\n", encoding="utf-8")
            _git(racer, "add", "race.md")
            _git(
                racer,
                "-c",
                "user.name=Concurrent Writer",
                "-c",
                "user.email=concurrent@example.invalid",
                "commit",
                "-m",
                "concurrent wiki update",
            )
            _git(racer, "push", "origin", "main")
        return original_git(cwd, *args, check=check)

    monkeypatch.setattr(wiki_publish, "_git", advance_remote_before_publisher_push)

    with pytest.raises(wiki_publish.PublishError, match="rejected"):
        wiki_publish.publish(
            remote=str(remote),
            source_url_template="https://scm.example/org/repo/blob/{head_sha}/{path}",
            branch="main",
            receipt_path=tmp_path / "publication.json",
            adopt_existing_head=placeholder_head,
        )

    assert raced is True
    inspect = tmp_path / "race-inspect"
    _git(tmp_path, "clone", str(remote), str(inspect))
    assert (inspect / "race.md").read_text(encoding="utf-8") == "concurrent update\n"
    assert not (inspect / wiki_publish.MARKER).exists()


def test_unsafe_receipt_staging_blocks_before_remote_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publication_fixture(tmp_path, monkeypatch)
    remote, placeholder_head = _bare_remote(tmp_path, with_placeholder=True)
    receipt = tmp_path / "publication.json"
    victim = tmp_path / "victim"
    victim.write_text("unchanged", encoding="utf-8")
    receipt.with_suffix(".json.tmp").symlink_to(victim)

    with pytest.raises(wiki_publish.PublishError, match="staging"):
        wiki_publish.publish(
            remote=str(remote),
            source_url_template="https://scm.example/org/repo/blob/{head_sha}/{path}",
            branch="main",
            receipt_path=receipt,
            adopt_existing_head=placeholder_head,
        )

    assert victim.read_text(encoding="utf-8") == "unchanged"
    assert _git(tmp_path, "--git-dir", str(remote), "rev-parse", "main") == placeholder_head
