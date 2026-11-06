from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from samuel.slices.implementation.llm_loop import _finalize_result
from samuel.slices.implementation.workspace_transaction import WorkspaceTransaction


def test_rollback_restores_existing_content_and_mode(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_bytes(b"operator: value\n")
    target.chmod(0o640)
    transaction = WorkspaceTransaction()
    transaction.capture(target)

    target.write_bytes(b"llm: changed\n")
    target.chmod(0o600)

    assert transaction.rollback() == {
        "status": "completed",
        "files_restored": 1,
        "files_removed": 0,
        "directories_removed": 0,
        "failures": 0,
    }
    assert target.read_bytes() == b"operator: value\n"
    assert target.stat().st_mode & 0o777 == 0o640


def test_repeated_capture_keeps_first_touch_baseline(tmp_path: Path) -> None:
    target = tmp_path / "state.txt"
    target.write_text("operator\n", encoding="utf-8")
    transaction = WorkspaceTransaction()
    transaction.capture(target)

    target.write_text("round one\n", encoding="utf-8")
    transaction.capture(target)
    target.write_text("round two\n", encoding="utf-8")

    assert transaction.rollback()["status"] == "completed"
    assert target.read_text(encoding="utf-8") == "operator\n"


def test_rollback_removes_new_file_and_directories(tmp_path: Path) -> None:
    target = tmp_path / "generated" / "nested" / "main.go"
    transaction = WorkspaceTransaction()
    transaction.capture(target)
    target.parent.mkdir(parents=True)
    target.write_text("package main\n", encoding="utf-8")

    evidence = transaction.rollback()

    assert evidence == {
        "status": "completed",
        "files_restored": 0,
        "files_removed": 1,
        "directories_removed": 2,
        "failures": 0,
    }
    assert not target.exists()
    assert not (tmp_path / "generated").exists()


def test_commit_keeps_changes(tmp_path: Path) -> None:
    target = tmp_path / "existing.sql"
    target.write_text("SELECT 1;\n", encoding="utf-8")
    transaction = WorkspaceTransaction()
    transaction.capture(target)
    target.write_text("SELECT 2;\n", encoding="utf-8")

    transaction.commit()

    assert transaction.rollback()["status"] == "not_needed"
    assert target.read_text(encoding="utf-8") == "SELECT 2;\n"


def test_release_unchanged_existing_capture_avoids_metadata_rewrite(tmp_path: Path) -> None:
    target = tmp_path / "existing.py"
    target.write_text("value = 1\n", encoding="utf-8")
    before_mtime = target.stat().st_mtime_ns
    transaction = WorkspaceTransaction()
    transaction.capture(target)

    assert transaction.release_if_unchanged(target) is True
    assert transaction.rollback()["status"] == "not_needed"
    assert target.read_text(encoding="utf-8") == "value = 1\n"
    assert target.stat().st_mtime_ns == before_mtime


def test_release_unchanged_missing_capture_drops_parent_cleanup(tmp_path: Path) -> None:
    target = tmp_path / "new" / "module.py"
    transaction = WorkspaceTransaction()
    transaction.capture(target)

    assert transaction.release_if_unchanged(target) is True
    assert transaction.rollback()["status"] == "not_needed"
    assert not target.parent.exists()


def test_release_refuses_changed_capture_and_rollback_still_restores(tmp_path: Path) -> None:
    target = tmp_path / "existing.py"
    target.write_text("before\n", encoding="utf-8")
    transaction = WorkspaceTransaction()
    transaction.capture(target)
    target.write_text("after\n", encoding="utf-8")

    assert transaction.release_if_unchanged(target) is False
    assert transaction.rollback()["status"] == "completed"
    assert target.read_text(encoding="utf-8") == "before\n"


def test_rollback_failure_is_not_reported_as_clean(tmp_path: Path) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("before\n", encoding="utf-8")
    transaction = WorkspaceTransaction()
    transaction.capture(target)
    target.write_text("after\n", encoding="utf-8")

    with patch.object(Path, "write_bytes", side_effect=OSError("read-only")):
        evidence = transaction.rollback()

    assert evidence["status"] == "failed"
    assert evidence["failures"] == 1
    assert target.read_text(encoding="utf-8") == "after\n"


def test_finalize_promotes_rollback_failure_to_terminal_reason(tmp_path: Path) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("before\n", encoding="utf-8")
    transaction = WorkspaceTransaction()
    transaction.capture(target)
    target.write_text("after\n", encoding="utf-8")

    with patch.object(Path, "write_bytes", side_effect=OSError("read-only")):
        result = _finalize_result(
            {
                "success": False,
                "reason": "token_limit",
                "patches_applied": [{"file": "existing.txt"}],
                "failures": [],
            },
            transaction,
        )

    assert result["reason"] == "workspace_rollback_failed"
    assert result["trigger_reason"] == "token_limit"
    assert result["patches_rolled_back"] == 0
    assert result["rollback"]["status"] == "failed"
    assert result["failures"] == ["workspace_rollback_failed"]
