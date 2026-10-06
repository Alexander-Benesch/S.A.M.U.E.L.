"""Tests for samuel.core.git — subprocess-based git operations."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from samuel.core.git import (
    _run,
    changed_files,
    checkout,
    commit,
    commit_tree_transaction,
    create_branch,
    current_branch,
    diff_text,
    git_control_plane_paths,
    prepare_branch_at_head,
    push,
    stage_files,
)


def _mock_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock subprocess.run result."""
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


class TestRun:
    def test_success(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="ok\n")) as mock:
            ok, out = _run(["status"])
            assert ok is True
            assert out == "ok"
            mock.assert_called_once()

    def test_failure(self):
        with patch("subprocess.run", return_value=_mock_run(stderr="error", returncode=1)):
            ok, out = _run(["checkout", "nonexistent"])
            assert ok is False
            assert out == "error"

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            ok, out = _run(["log"])
            assert ok is False
            assert out == "timeout"

    def test_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok, out = _run(["status"])
            assert ok is False
            assert out == "git not found"

    def test_cwd_passed(self, tmp_path: Path):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            _run(["status"], cwd=tmp_path)
            assert mock.call_args[1]["cwd"] == str(tmp_path)

    def test_force_push_is_blocked_before_subprocess(self):
        with patch("subprocess.run") as mock:
            ok, out = _run(["push", "--force", "origin", "main"])

        assert ok is False
        assert out == "blocked by command safety policy"
        mock.assert_not_called()

    def test_force_push_short_flag_is_blocked_before_subprocess(self):
        with patch("subprocess.run") as mock:
            ok, out = _run(["push", "-f", "origin", "main"])

        assert ok is False
        assert out == "blocked by command safety policy"
        mock.assert_not_called()

    def test_reset_hard_is_blocked_before_subprocess(self):
        with patch("subprocess.run") as mock:
            ok, out = _run(["reset", "--hard", "origin/main"])

        assert ok is False
        assert out == "blocked by command safety policy"
        mock.assert_not_called()

    def test_reset_hard_with_git_worktree_option_is_blocked(self):
        with patch("subprocess.run") as mock:
            ok, out = _run(["-C", "/tmp/project", "reset", "--hard", "origin/main"])

        assert ok is False
        assert out == "blocked by command safety policy"
        mock.assert_not_called()

    def test_force_like_argument_on_non_push_command_is_not_policy_blocked(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok, _ = _run(["checkout", "push", "--force"])

        assert ok is True
        mock.assert_called_once()


class TestCurrentBranch:
    def test_returns_branch_name(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="main\n")):
            assert current_branch() == "main"

    def test_empty_on_failure(self):
        with patch("subprocess.run", return_value=_mock_run(returncode=1, stderr="err")):
            assert current_branch() == ""


class TestGitControlPlanePaths:
    def test_resolves_git_dir_common_dir_index_and_objects(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

        paths = set(git_control_plane_paths(tmp_path))

        assert (tmp_path / ".git").resolve() in paths
        assert (tmp_path / ".git/index").resolve(strict=False) in paths
        assert (tmp_path / ".git/objects").resolve() in paths

    def test_failed_git_discovery_keeps_reserved_marker(self, tmp_path: Path):
        with patch("samuel.core.git._run", return_value=(False, "not a repository")):
            paths = git_control_plane_paths(tmp_path)

        assert paths == ((tmp_path / ".git").resolve(strict=False),)

    def test_effective_index_and_object_overrides_are_protected(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        custom_index = tmp_path / "repository.index"
        custom_objects = tmp_path / "repository-objects"
        custom_objects.mkdir()

        with patch.dict(
            os.environ,
            {
                "GIT_INDEX_FILE": str(custom_index),
                "GIT_OBJECT_DIRECTORY": str(custom_objects),
            },
        ):
            paths = set(git_control_plane_paths(tmp_path))

        assert custom_index.resolve(strict=False) in paths
        assert custom_index.with_name("repository.index.lock").resolve(strict=False) in paths
        assert custom_objects.resolve() in paths


class TestCreateBranch:
    def test_creates_new_branch_when_absent(self):
        """Happy path: branch doesn't exist locally → fresh create from origin."""
        calls = []

        def mock_run(args, **kwargs):
            calls.append(args)
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _mock_run(returncode=1, stderr="not a valid ref")
            if args == ["git", "branch", "--show-current"]:
                return _mock_run(stdout="feat/x\n")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            ok = create_branch("feat/x", "main")
            assert ok is True
            assert ["git", "fetch", "origin", "main"] in calls
            assert ["git", "checkout", "-b", "feat/x", "origin/main"] in calls
            assert ["git", "branch", "-D", "feat/x"] not in calls

    def test_missing_local_branch_probe_is_not_logged_as_warning(self, caplog):
        def mock_run(args, **kwargs):
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _mock_run(returncode=1, stderr="not a valid ref")
            if args == ["git", "branch", "--show-current"]:
                return _mock_run(stdout="feat/x\n")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run), caplog.at_level("WARNING"):
            assert create_branch("feat/x", "main") is True

        assert "not a valid ref" not in caplog.text

    def test_fetch_failure_stops_branch_creation(self):
        calls = []

        def mock_run(args, **kwargs):
            calls.append(args)
            if args[:2] == ["git", "fetch"]:
                return _mock_run(returncode=1, stderr="remote unavailable")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            assert create_branch("feat/x", "main") is False

        assert not any(args[:3] == ["git", "checkout", "-b"] for args in calls)


class TestPrepareBranchAtHead:
    def test_checks_out_only_matching_remote_candidate(self):
        expected = "b" * 40
        calls = []

        def mock_run(args, **kwargs):
            calls.append(args)
            if args == ["git", "status", "--porcelain"]:
                return _mock_run(stdout="")
            if args == ["git", "rev-parse", "origin/feat/x"]:
                return _mock_run(stdout=expected + "\n")
            if args == ["git", "branch", "--show-current"]:
                return _mock_run(stdout="feat/x\n")
            if args == ["git", "rev-parse", "HEAD"]:
                return _mock_run(stdout=expected + "\n")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            assert prepare_branch_at_head("feat/x", expected) is True

        assert ["git", "fetch", "origin", "feat/x"] in calls
        assert ["git", "checkout", "-B", "feat/x", "origin/feat/x"] in calls
        assert not any(call[:3] == ["git", "checkout", "main"] for call in calls)

    def test_refuses_moved_remote_candidate(self):
        expected = "b" * 40
        calls = []

        def mock_run(args, **kwargs):
            calls.append(args)
            if args == ["git", "status", "--porcelain"]:
                return _mock_run(stdout="")
            if args == ["git", "rev-parse", "origin/feat/x"]:
                return _mock_run(stdout="c" * 40 + "\n")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            assert prepare_branch_at_head("feat/x", expected) is False

        assert not any(call[:3] == ["git", "checkout", "-B"] for call in calls)

    def test_refuses_dirty_worktree_before_checkout(self):
        with patch(
            "subprocess.run",
            return_value=_mock_run(stdout=" M user-change.py\n"),
        ) as run:
            assert prepare_branch_at_head("feat/x", "b" * 40) is False

        assert run.call_count == 1


class TestCreateBranchContinued:
    def test_recreates_existing_branch(self):
        """If branch exists locally (stale from prior run): delete + recreate fresh."""
        calls = []

        def mock_run(args, **kwargs):
            calls.append(args)
            if args == ["git", "branch", "--show-current"]:
                return _mock_run(stdout="feat/x\n")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            ok = create_branch("feat/x", "main")
            assert ok is True
            assert ["git", "checkout", "main"] in calls
            assert ["git", "branch", "-D", "feat/x"] in calls
            assert ["git", "checkout", "-b", "feat/x", "origin/main"] in calls

    def test_fails_when_base_checkout_blocked(self):
        """Existing branch + dirty worktree blocks `checkout main` → return False.
        Regression for #226: must NOT silently proceed on the wrong branch."""

        def mock_run(args, **kwargs):
            if args == ["git", "checkout", "main"]:
                return _mock_run(returncode=1, stderr="dirty worktree")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            assert create_branch("feat/x", "main") is False

    def test_fails_when_create_blocked(self):
        """`checkout -b` failure → return False (not silent fallback)."""

        def mock_run(args, **kwargs):
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _mock_run(returncode=1, stderr="not a valid ref")
            if args[:3] == ["git", "checkout", "-b"]:
                return _mock_run(returncode=1, stderr="cannot create")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            assert create_branch("feat/x", "main") is False

    def test_fails_when_postcondition_mismatch(self):
        """All git calls succeed but worktree ends up on wrong branch → False.
        Defends against silent-success bugs in git itself."""

        def mock_run(args, **kwargs):
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _mock_run(returncode=1, stderr="not a valid ref")
            if args == ["git", "branch", "--show-current"]:
                return _mock_run(stdout="some-other-branch\n")
            return _mock_run()

        with patch("subprocess.run", side_effect=mock_run):
            assert create_branch("feat/x", "main") is False


class TestStageFiles:
    def test_stage_all(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = stage_files([])
            assert ok is True
            assert mock.call_args[0][0] == ["git", "add", "-A"]

    def test_stage_specific_files(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = stage_files(["a.py", "b.py"])
            assert ok is True
            assert mock.call_args[0][0] == ["git", "add", "--", "a.py", "b.py"]


class TestCommit:
    def test_commit_message(self, monkeypatch):
        monkeypatch.delenv("SAMUEL_GIT_AUTHOR_NAME", raising=False)
        monkeypatch.delenv("SAMUEL_GIT_AUTHOR_EMAIL", raising=False)
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = commit("fix: stuff")
            assert ok is True
            assert mock.call_args[0][0] == [
                "git",
                "-c",
                "user.name=S.A.M.U.E.L. Reference Agent",
                "-c",
                "user.email=samuel-reference@localhost.invalid",
                "commit",
                "-m",
                "fix: stuff",
            ]


class TestCommitTreeTransaction:
    @staticmethod
    def _repository(tmp_path: Path) -> Path:
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=tmp_path,
            check=True,
        )
        (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True)
        return tmp_path

    @staticmethod
    def _repository_without_identity(tmp_path: Path) -> Path:
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "base",
            ],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        assert (
            subprocess.run(
                ["git", "config", "--local", "--get", "user.name"],
                cwd=tmp_path,
                capture_output=True,
                check=False,
            ).returncode
            != 0
        )
        return tmp_path

    def test_fresh_repository_uses_non_human_reference_identity(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.delenv("SAMUEL_GIT_AUTHOR_NAME", raising=False)
        monkeypatch.delenv("SAMUEL_GIT_AUTHOR_EMAIL", raising=False)
        root = self._repository_without_identity(tmp_path)
        (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()

        commit_sha = commit_tree_transaction(
            "feat: controlled\n",
            expected_parent=parent,
            expected_tree=tree,
            cwd=root,
        )

        assert commit_sha
        identity = subprocess.check_output(
            ["git", "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", commit_sha],
            cwd=root,
            text=True,
        ).strip()
        assert identity.split("\x00") == [
            "S.A.M.U.E.L. Reference Agent",
            "samuel-reference@localhost.invalid",
            "S.A.M.U.E.L. Reference Agent",
            "samuel-reference@localhost.invalid",
        ]

    def test_commit_tree_uses_complete_environment_identity(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_NAME", "Demo Bot")
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_EMAIL", "demo-bot@example.invalid")
        root = self._repository_without_identity(tmp_path)
        (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()

        commit_sha = commit_tree_transaction(
            "feat: controlled\n",
            expected_parent=parent,
            expected_tree=tree,
            cwd=root,
        )

        assert commit_sha
        identity = subprocess.check_output(
            ["git", "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", commit_sha],
            cwd=root,
            text=True,
        ).strip()
        assert identity.split("\x00") == [
            "Demo Bot",
            "demo-bot@example.invalid",
            "Demo Bot",
            "demo-bot@example.invalid",
        ]

    def test_commit_tree_rejects_partial_environment_identity(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_NAME", "Incomplete Bot")
        monkeypatch.delenv("SAMUEL_GIT_AUTHOR_EMAIL", raising=False)
        root = self._repository_without_identity(tmp_path)
        (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()

        assert (
            commit_tree_transaction(
                "feat: controlled\n",
                expected_parent=parent,
                expected_tree=tree,
                cwd=root,
            )
            == ""
        )
        assert (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            == parent
        )

    def test_bypasses_repository_hooks_but_binds_parent_and_tree(self, tmp_path: Path) -> None:
        root = self._repository(tmp_path)
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 91\n", encoding="utf-8")
        hook.chmod(0o700)
        parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()

        commit_sha = commit_tree_transaction(
            "feat: controlled\n",
            expected_parent=parent,
            expected_tree=tree,
            cwd=root,
        )

        assert commit_sha
        assert (
            subprocess.check_output(["git", "rev-parse", "HEAD^"], cwd=root, text=True).strip()
            == parent
        )
        assert (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True
            ).strip()
            == tree
        )
        assert subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True) == ""

    def test_index_change_after_commit_object_blocks_ref_move(self, tmp_path: Path) -> None:
        root = self._repository(tmp_path)
        parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()
        real_run = subprocess.run

        def mutate_after_commit_tree(args, **kwargs):
            result = real_run(args, **kwargs)
            if args[:2] == ["git", "commit-tree"]:
                (root / "late.txt").write_text("late\n", encoding="utf-8")
                real_run(["git", "add", "late.txt"], cwd=root, check=True)
            return result

        with patch("samuel.core.git.subprocess.run", side_effect=mutate_after_commit_tree):
            commit_sha = commit_tree_transaction(
                "feat: controlled\n",
                expected_parent=parent,
                expected_tree=tree,
                cwd=root,
            )

        assert commit_sha == ""
        assert (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            == parent
        )

    def test_required_signing_without_key_is_fail_closed(self, tmp_path: Path) -> None:
        root = self._repository(tmp_path)
        parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()

        assert (
            commit_tree_transaction(
                "feat: unsigned\n",
                expected_parent=parent,
                expected_tree=tree,
                cwd=root,
                signing_required=True,
            )
            == ""
        )

    def test_required_signing_creates_a_verifiable_commit(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        repository = tmp_path / "repository"
        repository.mkdir()
        root = self._repository(repository)
        key_home = tmp_path / "gnupg"
        key_home.mkdir(mode=0o700)
        subprocess.run(
            [
                "gpg",
                "--batch",
                "--homedir",
                str(key_home),
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                "S.A.M.U.E.L. Test <samuel@example.invalid>",
                "ed25519",
                "sign",
                "0",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        listing = subprocess.check_output(
            ["gpg", "--batch", "--homedir", str(key_home), "--with-colons", "--list-secret-keys"],
            text=True,
        )
        fingerprint = next(
            line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:")
        )
        monkeypatch.setenv("GNUPGHOME", str(key_home))
        parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        (root / "tracked.txt").write_text("signed candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
        tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()

        commit_sha = commit_tree_transaction(
            "feat: signed controlled commit\n",
            expected_parent=parent,
            expected_tree=tree,
            cwd=root,
            signing_required=True,
            signing_key=fingerprint,
        )

        assert commit_sha
        subprocess.run(
            ["git", "verify-commit", commit_sha],
            cwd=root,
            env={**os.environ, "GNUPGHOME": str(key_home)},
            capture_output=True,
            text=True,
            check=True,
        )

    def test_commit_with_env_author(self, monkeypatch):
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_NAME", "Bot")
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_EMAIL", "bot@example.com")
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = commit("fix: stuff")
            assert ok is True
            assert mock.call_args[0][0] == [
                "git",
                "-c",
                "user.name=Bot",
                "-c",
                "user.email=bot@example.com",
                "commit",
                "-m",
                "fix: stuff",
            ]

    def test_commit_param_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_NAME", "EnvBot")
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_EMAIL", "env@example.com")
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = commit("fix: stuff", author_name="ParamBot", author_email="param@example.com")
            assert ok is True
            args = mock.call_args[0][0]
            assert "user.name=ParamBot" in args
            assert "user.email=param@example.com" in args
            assert "user.name=EnvBot" not in args

    def test_commit_partial_env_no_override(self, monkeypatch):
        monkeypatch.setenv("SAMUEL_GIT_AUTHOR_NAME", "Bot")
        monkeypatch.delenv("SAMUEL_GIT_AUTHOR_EMAIL", raising=False)
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            assert commit("fix: stuff") is False
            mock.assert_not_called()


class TestPush:
    def test_push_branch(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = push("feat/x")
            assert ok is True
            assert mock.call_args[0][0] == ["git", "push", "-u", "origin", "feat/x"]


class TestCheckout:
    def test_checkout_branch(self):
        with patch("subprocess.run", return_value=_mock_run()) as mock:
            ok = checkout("main")
            assert ok is True
            assert mock.call_args[0][0] == ["git", "checkout", "main"]


class TestChangedFiles:
    def test_returns_file_list(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="a.py\nb.py\n")):
            files = changed_files("main")
            assert files == ["a.py", "b.py"]

    def test_empty_on_no_changes(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="")):
            assert changed_files() == []

    def test_empty_on_failure(self):
        with patch("subprocess.run", return_value=_mock_run(returncode=1, stderr="err")):
            assert changed_files() == []


class TestDiffText:
    def test_returns_diff(self):
        with patch("subprocess.run", return_value=_mock_run(stdout="diff --git ...")):
            assert diff_text() == "diff --git ..."

    def test_empty_on_failure(self):
        with patch("subprocess.run", return_value=_mock_run(returncode=1, stderr="err")):
            assert diff_text() == ""
