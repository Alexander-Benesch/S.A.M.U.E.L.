from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.adapters.workspace.git import GitWorktreeManager
from samuel.core import git as core_git
from samuel.core.acceptance import parse_acceptance_contract
from samuel.core.bus import Bus
from samuel.core.commands import CreatePRCommand, ImplementCommand, ResumePendingCommand
from samuel.core.evaluation_subject import (
    EvaluationSubject,
    PullRequestRevision,
    RevisionComparison,
)
from samuel.core.events import Event, PRCreated
from samuel.core.ports import IConfig, IVersionControl
from samuel.core.state import AuthorityLeaseRecord, StateStoreError, WorkflowCheckpointRecord
from samuel.core.types import PR, Comment, Issue
from samuel.core.workspaces import WorkspaceError
from samuel.slices.implementation.handler import ImplementationHandler
from samuel.slices.labels.handler import LabelsHandler
from samuel.slices.pr_gates.handler import PRGatesHandler
from samuel.slices.resume.handler import ResumeCoordinator

_PLAN = "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] tracked.txt"
_BINDING = {
    "policy_version": "resume-test.v1",
    "policy_digest": "sha256:" + "a" * 64,
    "gate_schema_version": 2,
    "observation_schema_version": 2,
}


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    root = tmp_path / "project"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    root.mkdir()
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "Resume Test")
    _git(root, "config", "user.email", "resume@example.invalid")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "base")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "main")
    return root, remote


class _Config(IConfig):
    def get(self, key: str, default: Any = None) -> Any:
        values = {
            "agent.resume.enabled": True,
            "agent.git.signing_required": False,
            "agent.git.signing_key": "",
        }
        return values.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return name == "auto_implement_llm"

    def reload(self) -> None:
        return None


class _LocalSCM(IVersionControl):
    def __init__(self, root: Path, remote: Path) -> None:
        self.root = root
        self.remote = remote
        self.prs: list[dict[str, Any]] = []
        self.label_swaps: list[tuple[int, str, str]] = []
        self.raise_after_create = False
        self.plan = _PLAN

    @property
    def repository_identity(self) -> str:
        return "local/resume-test"

    def _remote_ref(self, ref: str) -> str | None:
        result = subprocess.run(
            ["git", "--git-dir", str(self.remote), "rev-parse", f"refs/heads/{ref}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def resolve_ref(self, ref: str) -> str:
        value = self._remote_ref(ref)
        if value is None:
            raise RuntimeError("unknown ref")
        return value

    def resolve_ref_optional(self, ref: str) -> str | None:
        return self._remote_ref(ref)

    def compare_commits(
        self, base_sha: str, head_sha: str, *, max_diff_bytes: int
    ) -> RevisionComparison:
        diff = _git(self.root, "diff", f"{base_sha}..{head_sha}")
        return RevisionComparison(
            repository=self.repository_identity,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_files=("tracked.txt",),
            diff=diff[:max_diff_bytes],
            diff_bytes=len(diff.encode("utf-8")),
        )

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Resume", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return [Comment(id=1, body=self.plan, user="bot")]

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=2, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        number = len(self.prs) + 1
        head_sha = self.resolve_ref(head)
        base_sha = self.resolve_ref(base)
        self.prs.append(
            {
                "number": number,
                "head": head,
                "base": base,
                "head_sha": head_sha,
                "base_sha": base_sha,
                "body": body,
            }
        )
        if self.raise_after_create:
            self.raise_after_create = False
            raise SystemExit(73)
        return PR(
            id=number,
            number=number,
            title=title,
            html_url=f"https://example.invalid/pr/{number}",
        )

    def get_pr(self, pr_id: int) -> PR:
        row = next(item for item in self.prs if item["number"] == pr_id)
        return PR(
            id=pr_id,
            number=pr_id,
            title="Resume",
            html_url=f"https://example.invalid/pr/{row['number']}",
        )

    def find_pr_by_marker(self, marker: str, *, head: str, base: str) -> PR | None:
        matches = [
            row
            for row in self.prs
            if row["head"] == head and row["base"] == base and f"<!-- {marker} -->" in row["body"]
        ]
        if len(matches) > 1:
            raise RuntimeError("ambiguous marker")
        return self.get_pr(int(matches[0]["number"])) if matches else None

    def get_pr_revision(self, pr_id: int) -> PullRequestRevision:
        row = next(item for item in self.prs if item["number"] == pr_id)
        return PullRequestRevision(
            repository=self.repository_identity,
            base_sha=str(row["base_sha"]),
            head_sha=str(row["head_sha"]),
        )

    def swap_label(self, number: int, remove: str, add: str) -> None:
        self.label_swaps.append((number, remove, add))

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"name": name, "color": color}

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        return None

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return f"https://example.invalid/issues/{number}"

    def pr_url(self, pr_id: int) -> str:
        return f"https://example.invalid/pr/{pr_id}"

    def branch_url(self, branch: str) -> str:
        return f"https://example.invalid/branches/{branch}"


def _manager(work_dir: Path, data_dir: Path) -> GitWorktreeManager:
    return GitWorktreeManager(
        work_dir,
        data_dir=data_dir,
        reserve_bytes=1024,
        minimum_free_bytes=0,
        quarantine_max_count=8,
        quarantine_max_bytes=8 * 1024 * 1024,
    )


def _crash_during_finalization(
    root: str,
    remote: str,
    work_dir: str,
    data_dir: str,
    crash_boundary: str,
    ready: Any = None,
    release: Any = None,
) -> None:
    root_path = Path(root)
    remote_path = Path(remote)
    state = SQLiteStateStore(Path(data_dir))
    manager = _manager(Path(work_dir), Path(data_dir))
    scm = _LocalSCM(root_path, remote_path)
    bus = Bus()
    handler = ImplementationHandler(
        bus,
        scm=scm,
        project_root=root_path,
        config=_Config(),
        authority_store=state.authority,
        workspace_manager=manager,
        resume_policy_binding=_BINDING,
        resume_owner_id="crashed-owner",
        resume_lease_seconds=5,
    )
    # Keep the drill quick while still exercising a genuinely live then
    # expired persisted lease in two separate processes.
    handler._resume_lease_seconds = 1  # type: ignore[assignment]
    issue = 633
    correlation = f"crash-{crash_boundary}"
    branch = f"samuel/resume-{crash_boundary}"
    workspace_id = handler._authority_key(
        "run-workspace", scm.repository_identity, correlation, branch
    )
    workspace = manager.acquire_run(
        repository_root=root_path,
        workspace_id=workspace_id,
        branch=branch,
        base_ref="main",
    )
    (workspace.path / "tracked.txt").write_text(f"candidate {crash_boundary}\n", encoding="utf-8")
    assert core_git.stage_files(["tracked.txt"], workspace.path)
    parent = core_git.head_sha(workspace.path)
    tree = core_git.index_tree(workspace.path)
    binding = {
        **_BINDING,
        "contract_hash": parse_acceptance_contract(_PLAN).contract_hash,
    }
    result = {
        "success": True,
        "patches_applied": [{"file": "tracked.txt"}],
        "round": 1,
        "model": "test/model",
        "failures": [],
    }
    original_persist = handler._persist_finalization_checkpoint

    def persist_then_crash(**kwargs: Any) -> int | None:
        epoch = original_persist(**kwargs)
        if kwargs["boundary"] == crash_boundary:
            if ready is not None and release is not None:
                ready.set()
                release.wait(15)
            os._exit(71)
        return epoch

    handler._persist_finalization_checkpoint = persist_then_crash  # type: ignore[method-assign]
    real_commit = core_git.commit_tree_transaction
    real_push = core_git.push

    def commit_then_crash(*args: Any, **kwargs: Any) -> str:
        committed = real_commit(*args, **kwargs)
        assert committed
        os._exit(71)

    def push_then_crash(*args: Any, **kwargs: Any) -> bool:
        pushed = real_push(*args, **kwargs)
        assert pushed
        os._exit(71)

    if crash_boundary == "after_code_generated":
        bus.subscribe("CodeGenerated", lambda _event: os._exit(71))
    with ExitStack() as stack:
        if crash_boundary == "after_commit_effect":
            stack.enter_context(
                patch(
                    "samuel.core.git.commit_tree_transaction",
                    side_effect=commit_then_crash,
                )
            )
        if crash_boundary == "after_push_effect":
            stack.enter_context(patch("samuel.core.git.push", side_effect=push_then_crash))
        handler._finalize_candidate(
            cmd=ImplementCommand(issue_number=issue, correlation_id=correlation),
            issue_number=issue,
            project=workspace.path,
            workspace_id=workspace_id,
            branch_name=branch,
            base_ref="main",
            expected_parent=parent,
            expected_tree=tree,
            commit_message=f"test: {crash_boundary}",
            resume_binding=binding,
            result=result,
            resumed=False,
        )
    os._exit(72)


def _compete_for_expired_lease(
    data_dir: str,
    owner: str,
    ready: Any,
    start: Any,
    results: Any,
) -> None:
    state = SQLiteStateStore(Path(data_dir))
    ready.put(owner)
    start.wait(10)
    try:
        write = state.authority.acquire_lease(
            AuthorityLeaseRecord(
                resource_key="workspace-cas",
                owner_id=owner,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
                version=2,
            ),
            expected_version=1,
        )
    except StateStoreError as exc:
        results.put((owner, "blocked", exc.code))
    else:
        results.put((owner, "acquired", write.authority_epoch))


@pytest.mark.parametrize(
    "boundary",
    [
        "commit_pending",
        "after_commit_effect",
        "push_pending",
        "after_push_effect",
        "gates_pending",
        "after_code_generated",
    ],
)
def test_hard_crash_resume_is_effect_idempotent_across_real_processes(
    tmp_path: Path,
    boundary: str,
) -> None:
    root, remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    context = multiprocessing.get_context("fork")
    child = context.Process(
        target=_crash_during_finalization,
        args=(str(root), str(remote), str(work_dir), str(data_dir), boundary),
    )
    child.start()
    child.join(15)
    assert child.exitcode == 71

    state = SQLiteStateStore(data_dir)
    manager = _manager(work_dir, data_dir)
    scm = _LocalSCM(root, remote)
    bus = Bus()
    implementation = ImplementationHandler(
        bus,
        scm=scm,
        project_root=root,
        config=_Config(),
        authority_store=state.authority,
        workspace_manager=manager,
        resume_policy_binding=_BINDING,
        resume_owner_id="replacement-owner",
        resume_lease_seconds=5,
    )
    bus.register_command("Implement", implementation.handle)
    events: list[Event] = []
    bus.subscribe("*", events.append)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="replacement-owner",
        projection_store=state.projections,
    )

    live = coordinator.handle(ResumePendingCommand())
    assert live["resumed"] == 0
    assert live["details"][0]["pending"] is True
    assert live["details"][0]["reason"] == "resume_lease_live"

    time.sleep(1.05)
    completed = coordinator.handle(ResumePendingCommand())
    assert completed["resumed"] == 1
    checkpoint = state.authority.list_checkpoints(resume_eligible=True)[0]
    assert checkpoint.boundary == "gates_pending"
    assert scm.resolve_ref(checkpoint.branch) == checkpoint.head_sha
    assert len(state.authority.list_intents(correlation_id=checkpoint.correlation_id)) == 2
    assert [event.name for event in events].count("CodeGenerated") == 1
    branch_count = subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "rev-list",
            "--count",
            f"main..{checkpoint.branch}",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert branch_count == "1"


def test_live_os_lock_blocks_takeover_before_lease_or_git_mutation(tmp_path: Path) -> None:
    root, remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    child = context.Process(
        target=_crash_during_finalization,
        args=(
            str(root),
            str(remote),
            str(work_dir),
            str(data_dir),
            "commit_pending",
            ready,
            release,
        ),
    )
    child.start()
    assert ready.wait(10)

    state = SQLiteStateStore(data_dir)
    manager = _manager(work_dir, data_dir)
    scm = _LocalSCM(root, remote)
    bus = Bus()
    events: list[Event] = []
    bus.subscribe("*", events.append)
    LabelsHandler(bus, scm=scm).register()
    handler = ImplementationHandler(
        bus,
        scm=scm,
        project_root=root,
        config=_Config(),
        authority_store=state.authority,
        workspace_manager=manager,
        resume_policy_binding=_BINDING,
        resume_owner_id="blocked-owner",
    )
    bus.register_command("Implement", handler.handle)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="blocked-owner",
    )
    before = state.authority.list_checkpoints(resume_eligible=True)[0]
    before_lease = state.authority.get_lease(before.workspace_id)

    outcome = coordinator.handle(
        ResumePendingCommand(payload={"source": "watch_cycle"}, correlation_id="competing-watch")
    )

    after = state.authority.get_checkpoint(before.checkpoint_key)
    live_workspace = manager.inspect(before.workspace_id)
    live_workspace_status = live_workspace.status if live_workspace is not None else None
    after_lease = state.authority.get_lease(before.workspace_id)
    after_intents = state.authority.list_intents(correlation_id=before.correlation_id)
    release.set()
    child.join(10)

    assert child.exitcode == 71
    assert outcome["blocked"] == 1
    assert outcome["details"][0]["reason"] == "workspace_owned"
    assert [event.name for event in events].count("ResumeAttempted") == 1
    assert [event.name for event in events].count("ResumeBlocked") == 1
    assert not any(event.name == "WorkflowBlocked" for event in events)
    assert not any(add == "status:failed" for _, _, add in scm.label_swaps)
    assert scm.prs == []
    assert live_workspace_status == "active"
    assert after == before
    assert after_lease == before_lease
    assert after_intents == []


def test_health_cli_does_not_resume_a_live_run_workspace(tmp_path: Path) -> None:
    root, _remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "workflows").mkdir()
    (config_dir / "workflows" / "standard.json").write_text(
        json.dumps({"name": "standard", "steps": [], "max_risk": 3, "max_parallel": 1}),
        encoding="utf-8",
    )
    audit_path = tmp_path / "health-audit.jsonl"
    (config_dir / "audit.json").write_text(
        json.dumps({"sinks": [{"type": "jsonl", "path": str(audit_path), "rotation": "none"}]}),
        encoding="utf-8",
    )
    (config_dir / "agent.json").write_text(
        json.dumps(
            {
                "log_level": "WARNING",
                "data_dir": str(data_dir),
                "workspace": {
                    "work_dir": str(work_dir),
                    "reserve_mebibytes": 1,
                    "minimum_free_mebibytes": 0,
                },
                "resume": {"enabled": True, "lease_seconds": 60},
            }
        ),
        encoding="utf-8",
    )
    state = SQLiteStateStore(data_dir)
    manager = _manager(work_dir, data_dir)
    issue = 633
    correlation_id = "active-healthcheck-run"
    branch = f"samuel/issue-{issue}"
    workspace_id = ImplementationHandler._authority_key("run-workspace", "", correlation_id, branch)
    workspace = manager.acquire_run(
        repository_root=root,
        workspace_id=workspace_id,
        branch=branch,
        base_ref="main",
    )
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key="checkpoint-active-healthcheck-run",
        issue_number=issue,
        correlation_id=correlation_id,
        workflow="implementation_finalization",
        boundary="gates_pending",
        repository="",
        branch=branch,
        base_ref="main",
        head_sha=workspace.head_sha,
        workspace_id=workspace_id,
        evaluation_subject={},
        resume_eligible=True,
        payload={"resume_status": "pending"},
    )
    state.authority.put_checkpoint(checkpoint)
    environment = {
        **os.environ,
        "PROJECT_ROOT": str(root),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    environment.pop("SAMUEL_RUNTIME_CONFIG_DIR", None)
    environment.pop("SAMUEL_WORKFLOW_OVERRIDE", None)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "samuel", "--config", str(config_dir), "health"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

        assert result.returncode in {0, 1}, result.stderr
        assert "Technical health:" in result.stdout
        events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        names = {event.get("payload", {}).get("message_name") for event in events}
        assert "ResumeAttempted" not in names
        assert "WorkflowBlocked" not in names
        assert "ResumePending" not in names
        assert state.authority.get_checkpoint(checkpoint.checkpoint_key) == checkpoint
        assert not any(
            record.kind == "resume_terminal" for record in state.authority.list_authority_records()
        )
        record = manager.inspect(workspace_id)
        assert record is not None and record.status == "active"
        assert workspace.path.is_dir()
        with pytest.raises(WorkspaceError, match="owned by another process"):
            _manager(work_dir, data_dir).acquire_existing_run(
                repository_root=root, workspace_id=workspace_id, branch=branch
            )
    finally:
        manager.release(workspace_id)


def test_expired_lease_has_exactly_one_cas_winner_across_processes(tmp_path: Path) -> None:
    data_dir = tmp_path / "state"
    state = SQLiteStateStore(data_dir)
    state.authority.acquire_lease(
        AuthorityLeaseRecord(
            resource_key="workspace-cas",
            owner_id="expired-owner",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            version=1,
        )
    )
    context = multiprocessing.get_context("fork")
    ready = context.Queue()
    start = context.Event()
    results = context.Queue()
    contenders = [
        context.Process(
            target=_compete_for_expired_lease,
            args=(str(data_dir), owner, ready, start, results),
        )
        for owner in ("owner-a", "owner-b")
    ]
    for contender in contenders:
        contender.start()
    assert {ready.get(timeout=10), ready.get(timeout=10)} == {"owner-a", "owner-b"}
    start.set()
    for contender in contenders:
        contender.join(10)
        assert contender.exitcode == 0
    outcomes = [results.get(timeout=10), results.get(timeout=10)]

    assert sorted(item[1] for item in outcomes) == ["acquired", "blocked"]
    winner = next(item[0] for item in outcomes if item[1] == "acquired")
    persisted = SQLiteStateStore(data_dir).authority.get_lease("workspace-cas")
    assert persisted is not None
    assert persisted.owner_id == winner
    assert persisted.version == 2


def test_remote_drift_is_quarantined_and_never_force_pushed(tmp_path: Path) -> None:
    root, remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    context = multiprocessing.get_context("fork")
    child = context.Process(
        target=_crash_during_finalization,
        args=(str(root), str(remote), str(work_dir), str(data_dir), "gates_pending"),
    )
    child.start()
    child.join(15)
    assert child.exitcode == 71
    state = SQLiteStateStore(data_dir)
    checkpoint = state.authority.list_checkpoints(resume_eligible=True)[0]
    foreign_head = _git(root, "rev-parse", "main")
    subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "update-ref",
            f"refs/heads/{checkpoint.branch}",
            foreign_head,
        ],
        check=True,
    )
    time.sleep(1.05)

    manager = _manager(work_dir, data_dir)
    scm = _LocalSCM(root, remote)
    bus = Bus()
    handler = ImplementationHandler(
        bus,
        scm=scm,
        project_root=root,
        config=_Config(),
        authority_store=state.authority,
        workspace_manager=manager,
        resume_policy_binding=_BINDING,
        resume_owner_id="replacement-owner",
    )
    bus.register_command("Implement", handler.handle)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="replacement-owner",
    )

    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome["details"][0]["reason"] == "resume_remote_changed"
    record = manager.inspect(checkpoint.workspace_id)
    assert record is not None and record.status == "quarantined"
    assert scm.resolve_ref(checkpoint.branch) == foreign_head


def test_foreign_head_and_tree_are_quarantined_without_reset(tmp_path: Path) -> None:
    root, remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    context = multiprocessing.get_context("fork")
    child = context.Process(
        target=_crash_during_finalization,
        args=(str(root), str(remote), str(work_dir), str(data_dir), "commit_pending"),
    )
    child.start()
    child.join(15)
    assert child.exitcode == 71
    state = SQLiteStateStore(data_dir)
    checkpoint = state.authority.list_checkpoints(resume_eligible=True)[0]
    manager = _manager(work_dir, data_dir)
    workspace = manager.acquire_existing_run(
        repository_root=root,
        workspace_id=checkpoint.workspace_id,
        branch=checkpoint.branch,
    )
    (workspace.path / "tracked.txt").write_text("foreign operator state\n", encoding="utf-8")
    _git(workspace.path, "add", "tracked.txt")
    _git(workspace.path, "commit", "-m", "foreign commit")
    foreign_head = _git(workspace.path, "rev-parse", "HEAD")
    manager.detach(workspace.workspace_id)
    time.sleep(1.05)
    scm = _LocalSCM(root, remote)
    bus = Bus()
    handler = ImplementationHandler(
        bus,
        scm=scm,
        project_root=root,
        config=_Config(),
        authority_store=state.authority,
        workspace_manager=manager,
        resume_policy_binding=_BINDING,
        resume_owner_id="replacement-owner",
    )
    bus.register_command("Implement", handler.handle)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="replacement-owner",
    )

    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome["details"][0]["reason"] == "resume_index_changed"
    assert _git(workspace.path, "rev-parse", "HEAD") == foreign_head
    record = manager.inspect(checkpoint.workspace_id)
    assert record is not None and record.status == "quarantined"


@pytest.mark.parametrize("drift", ["contract", "policy", "gate_schema", "observation_schema"])
def test_contract_policy_and_schema_drift_quarantine_fail_closed(
    tmp_path: Path,
    drift: str,
) -> None:
    root, remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    context = multiprocessing.get_context("fork")
    child = context.Process(
        target=_crash_during_finalization,
        args=(str(root), str(remote), str(work_dir), str(data_dir), "commit_pending"),
    )
    child.start()
    child.join(15)
    assert child.exitcode == 71
    time.sleep(1.05)
    state = SQLiteStateStore(data_dir)
    checkpoint = state.authority.list_checkpoints(resume_eligible=True)[0]
    manager = _manager(work_dir, data_dir)
    scm = _LocalSCM(root, remote)
    binding = dict(_BINDING)
    if drift == "contract":
        scm.plan = _PLAN + "\n- [ ] [GREP] tracked.txt :: candidate"
    elif drift == "policy":
        binding["policy_digest"] = "sha256:" + "b" * 64
    elif drift == "gate_schema":
        binding["gate_schema_version"] = 3
    else:
        binding["observation_schema_version"] = 3
    bus = Bus()
    handler = ImplementationHandler(
        bus,
        scm=scm,
        project_root=root,
        config=_Config(),
        authority_store=state.authority,
        workspace_manager=manager,
        resume_policy_binding=binding,
        resume_owner_id="replacement-owner",
    )
    bus.register_command("Implement", handler.handle)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="replacement-owner",
    )

    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome["details"][0]["reason"] == "resume_policy_or_contract_changed"
    record = manager.inspect(checkpoint.workspace_id)
    assert record is not None and record.status == "quarantined"


def test_reconcile_mode_blocks_resume_before_workspace_ownership(tmp_path: Path) -> None:
    root, remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    context = multiprocessing.get_context("fork")
    child = context.Process(
        target=_crash_during_finalization,
        args=(str(root), str(remote), str(work_dir), str(data_dir), "commit_pending"),
    )
    child.start()
    child.join(15)
    assert child.exitcode == 71
    state = SQLiteStateStore(data_dir)
    checkpoint = state.authority.list_checkpoints(resume_eligible=True)[0]
    state.compare_audit_authority_epoch(int(state.authority.authority_status()["epoch"]) + 10)
    manager = _manager(work_dir, data_dir)
    coordinator = ResumeCoordinator(
        Bus(),
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="replacement-owner",
    )

    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome == {
        "enabled": False,
        "attempted": 0,
        "resumed": 0,
        "blocked": 0,
        "reason": "authority_reconcile_required",
    }
    assert state.authority.get_checkpoint(checkpoint.checkpoint_key) == checkpoint
    assert manager.inspect(checkpoint.workspace_id).status == "active"  # type: ignore[union-attr]


def test_terminal_tombstone_reconciles_crash_before_workspace_cleanup(tmp_path: Path) -> None:
    root, _remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    state = SQLiteStateStore(data_dir)
    manager = _manager(work_dir, data_dir)
    workspace = manager.acquire_run(
        repository_root=root,
        workspace_id="workspace-terminal-crash",
        branch="samuel/terminal-crash",
        base_ref="main",
    )
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key="checkpoint-terminal-crash",
        issue_number=633,
        correlation_id="terminal-crash",
        workflow="implementation_finalization",
        boundary="pr_pending",
        repository="local/resume-test",
        branch=workspace.branch,
        base_ref="main",
        head_sha=workspace.head_sha,
        workspace_id=workspace.workspace_id,
        evaluation_subject={**_BINDING, "contract_hash": "sha256:" + "c" * 64},
        resume_eligible=True,
        payload={"resume_status": "pending"},
    )
    state.authority.put_checkpoint(checkpoint)
    coordinator = ResumeCoordinator(
        Bus(),
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="first-owner",
    )
    with (
        patch.object(manager, "release", side_effect=SystemExit(75)),
        pytest.raises(SystemExit) as crash,
    ):
        coordinator.observe_terminal(
            PRCreated(payload={"issue": 633}, correlation_id="terminal-crash")
        )
    assert crash.value.code == 75
    assert state.authority.get_checkpoint(checkpoint.checkpoint_key) == checkpoint
    manager.detach(workspace.workspace_id)

    reopened_manager = _manager(work_dir, data_dir)
    reopened = ResumeCoordinator(
        Bus(),
        authority_store=SQLiteStateStore(data_dir).authority,
        workspace_manager=reopened_manager,
        config=_Config(),
        owner_id="replacement-owner",
    )
    outcome = reopened.handle(ResumePendingCommand())

    assert outcome["resumed"] == 1
    assert outcome["details"][0]["reason"] == "terminal_cleanup_reconciled"
    assert SQLiteStateStore(data_dir).authority.get_checkpoint(checkpoint.checkpoint_key) is None
    assert reopened_manager.inspect(workspace.workspace_id).status == "terminal"  # type: ignore[union-attr]


def test_dirty_worktree_is_quarantined_without_reset_on_resume(tmp_path: Path) -> None:
    root, remote = _repository(tmp_path)
    data_dir = tmp_path / "state"
    work_dir = tmp_path / "workspaces"
    state = SQLiteStateStore(data_dir)
    manager = _manager(work_dir, data_dir)
    scm = _LocalSCM(root, remote)
    bus = Bus()
    handler = ImplementationHandler(
        bus,
        scm=scm,
        project_root=root,
        config=_Config(),
        authority_store=state.authority,
        workspace_manager=manager,
        resume_policy_binding=_BINDING,
        resume_owner_id="owner",
    )
    bus.register_command("Implement", handler.handle)
    correlation = "dirty-run"
    branch = "samuel/dirty-resume"
    workspace_id = handler._authority_key(
        "run-workspace", scm.repository_identity, correlation, branch
    )
    workspace = manager.acquire_run(
        repository_root=root,
        workspace_id=workspace_id,
        branch=branch,
        base_ref="main",
    )
    (workspace.path / "tracked.txt").write_text("candidate\n", encoding="utf-8")
    core_git.stage_files(["tracked.txt"], workspace.path)
    tree = core_git.index_tree(workspace.path)
    status = core_git.status_porcelain(workspace.path)
    assert status
    state.authority.put_checkpoint(
        WorkflowCheckpointRecord(
            checkpoint_key=handler._checkpoint_key(correlation, 633),
            issue_number=633,
            correlation_id=correlation,
            workflow="implementation_finalization",
            boundary="commit_pending",
            repository=scm.repository_identity,
            branch=branch,
            base_ref="main",
            head_sha=core_git.head_sha(workspace.path),
            workspace_id=workspace_id,
            evaluation_subject={
                **_BINDING,
                "contract_hash": parse_acceptance_contract(_PLAN).contract_hash,
            },
            resume_eligible=True,
            payload={
                "base_sha": scm.resolve_ref("main"),
                "expected_parent": core_git.head_sha(workspace.path),
                "expected_tree": tree,
                "staged_status_digest": hashlib.sha256(status.encode("utf-8")).hexdigest(),
                "commit_message": "test: dirty",
                "patched_files": ["tracked.txt"],
                "rounds": 1,
                "model": "test/model",
                "signing_required": False,
                "signing_key_digest": hashlib.sha256(b"").hexdigest(),
                "event_payload": {"issue": 633, "branch": branch},
                "resume_status": "pending",
            },
        )
    )
    manager.detach(workspace_id)
    (workspace.path / "untracked-secret.txt").write_text("do not delete\n", encoding="utf-8")

    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=manager,
        config=_Config(),
        owner_id="owner",
    )
    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome["blocked"] == 1
    assert outcome["details"][0]["reason"] == "resume_worktree_changed"
    record = manager.inspect(workspace_id)
    assert record is not None and record.status == "quarantined"
    assert (workspace.path / "untracked-secret.txt").read_text(encoding="utf-8") == (
        "do not delete\n"
    )
    checkpoint_key = handler._checkpoint_key(correlation, 633)
    abandoned = coordinator.abandon(checkpoint_key, reason="foreign worktree state reviewed")
    assert abandoned["status"] == "abandoned"
    cleaned = coordinator.cleanup(checkpoint_key, reason="evidence exported by operator")
    assert cleaned["status"] == "cleaned"
    assert state.authority.get_checkpoint(checkpoint_key) is None
    assert not workspace.path.exists()


def test_provider_checkpoint_resumes_without_implementation_or_workspace(
    tmp_path: Path,
) -> None:
    state = SQLiteStateStore(tmp_path / "provider-state")
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key="provider:verification:sha256:" + "1" * 64,
        issue_number=679,
        correlation_id="provider-run",
        workflow="provider_verification",
        boundary="provider_running",
        repository="https://gitea.example/owner/repo",
        branch="b" * 40,
        base_ref="a" * 40,
        head_sha="b" * 40,
        workspace_id="",
        evaluation_subject={"head_sha": "b" * 40},
        resume_eligible=True,
        payload={
            "schema": "provider-verification-checkpoint.v1",
            "request_key": "verification:sha256:" + "1" * 64,
            "mutation_authority": "none",
        },
    )
    state.authority.put_checkpoint(checkpoint)
    provider = MagicMock()
    provider.advance.return_value = SimpleNamespace(
        status="running", reason_code="provider_run_pending"
    )
    workspaces = MagicMock()
    workspaces.list_workspaces.return_value = []
    bus = Bus()
    implementation_calls: list[object] = []
    bus.register_command("Implement", implementation_calls.append)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=workspaces,
        config=_Config(),
        owner_id="owner",
        provider_verification=provider,
    )

    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome["resumed"] == 1
    assert outcome["details"][0]["reason"] == "provider_run_pending"
    assert outcome["details"][0]["pending"] is True
    assert implementation_calls == []
    provider.advance.assert_called_once_with("verification:sha256:" + "1" * 64)
    workspaces.inspect.assert_not_called()


def test_manual_acceptance_checkpoint_survives_resume_without_implementation(
    tmp_path: Path,
) -> None:
    state = SQLiteStateStore(tmp_path / "manual-wait-state")
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key="checkpoint:manual-wait",
        issue_number=679,
        correlation_id="manual-wait-run",
        workflow="implementation_finalization",
        boundary="manual_pending",
        repository="owner/repo",
        branch="samuel/issue-679",
        base_ref="main",
        head_sha="b" * 40,
        workspace_id="workspace-679",
        evaluation_subject={"contract_hash": "sha256:" + "c" * 64},
        resume_eligible=True,
        payload={"resume_status": "waiting_human_acceptance"},
    )
    state.authority.put_checkpoint(checkpoint)
    bus = Bus()
    implementation_calls: list[object] = []
    bus.register_command("Implement", implementation_calls.append)
    workspaces = MagicMock()
    workspaces.list_workspaces.return_value = []
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=workspaces,
        config=_Config(),
        owner_id="new-process",
    )

    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome["attempted"] == 0
    assert outcome["blocked"] == 0
    assert outcome["details"][0]["reason"] == "waiting_human_acceptance"
    assert implementation_calls == []
    assert state.authority.get_checkpoint(checkpoint.checkpoint_key) == checkpoint


def test_ready_reference_provider_checkpoint_resumes_at_create_pr_boundary(
    tmp_path: Path,
) -> None:
    state = SQLiteStateStore(tmp_path / "provider-consumer-state")
    request_key = "verification:sha256:" + "2" * 64
    subject = EvaluationSubject(
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="provider.v1",
        policy_digest="sha256:" + "d" * 64,
    )
    checkpoint = WorkflowCheckpointRecord(
        checkpoint_key=f"provider:{request_key}",
        issue_number=679,
        correlation_id="provider-reference-run",
        workflow="provider_verification",
        boundary="provider_running",
        repository="owner/repo",
        branch=subject.head_sha,
        base_ref=subject.base_sha,
        head_sha=subject.head_sha,
        workspace_id="",
        evaluation_subject=subject.as_dict(),
        resume_eligible=True,
        payload={
            "schema": "provider-verification-checkpoint.v1",
            "request_key": request_key,
            "mutation_authority": "none",
            "consumer_mode": "reference_worker",
            "consumer_context": {
                "branch": "samuel/issue-679",
                "base": "main",
                "workspace_id": "workspace-679",
                "acceptance_approval": {"state": "approved"},
            },
        },
    )
    state.authority.put_checkpoint(checkpoint)
    provider = MagicMock()
    provider.advance.return_value = SimpleNamespace(
        status="evidence_ready",
        reason_code="provider_evidence_ready",
        request=SimpleNamespace(consumer_mode="reference_worker", subject=subject),
    )
    workspaces = MagicMock()
    workspaces.list_workspaces.return_value = []
    bus = Bus()
    implementation_calls: list[object] = []
    create_pr_calls: list[CreatePRCommand] = []
    bus.register_command("Implement", implementation_calls.append)

    def consume(command: CreatePRCommand) -> dict[str, Any]:
        create_pr_calls.append(command)
        return {"passed": True, "pr_created": True}

    bus.register_command("CreatePR", consume)
    coordinator = ResumeCoordinator(
        bus,
        authority_store=state.authority,
        workspace_manager=workspaces,
        config=_Config(),
        owner_id="owner",
        provider_verification=provider,
    )

    outcome = coordinator.handle(ResumePendingCommand())

    assert outcome["resumed"] == 1
    assert outcome["blocked"] == 0
    assert outcome["details"][0]["pending"] is False
    assert outcome["details"][0]["reason"] == "provider_evidence_consumed"
    assert implementation_calls == []
    assert len(create_pr_calls) == 1
    command = create_pr_calls[0]
    assert command.subject == subject
    assert command.branch == "samuel/issue-679"
    assert command.payload["workspace_id"] == "workspace-679"
    assert command.payload["provider_resume"] is True
    workspaces.inspect.assert_not_called()


def _pr_handler(
    tmp_path: Path,
    bus: Bus,
    scm: _LocalSCM,
    state: SQLiteStateStore,
) -> PRGatesHandler:
    config_dir = tmp_path / "gates-config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "gates.json").write_text(
        '{"policy_version":"resume-pr.v1","required":[],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    return PRGatesHandler(
        bus,
        scm=scm,
        config_dir=config_dir,
        authority_store=state.authority,
    )


def test_pr_api_success_before_notation_is_recovered_only_by_bound_marker(
    tmp_path: Path,
) -> None:
    root, remote = _repository(tmp_path)
    branch = "samuel/pr-marker-recovery"
    _git(root, "checkout", "-b", branch)
    (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "candidate")
    _git(root, "push", "-u", "origin", branch)
    _git(root, "checkout", "main")
    state = SQLiteStateStore(tmp_path / "state")
    scm = _LocalSCM(root, remote)
    scm.raise_after_create = True

    with pytest.raises(SystemExit) as crash:
        _pr_handler(tmp_path, Bus(), scm, state).handle(
            CreatePRCommand(
                issue_number=633,
                branch=branch,
                correlation_id="pr-marker-crash",
            )
        )
    assert crash.value.code == 73
    assert len(scm.prs) == 1

    events: list[Event] = []
    resumed_bus = Bus()
    resumed_bus.subscribe("*", events.append)
    result = _pr_handler(tmp_path, resumed_bus, scm, state).handle(
        CreatePRCommand(
            issue_number=633,
            branch=branch,
            correlation_id="pr-marker-crash",
        )
    )

    assert result["passed"] is True
    assert len(scm.prs) == 1
    assert [event.name for event in events].count("PRCreated") == 1
    intent = state.authority.list_intents(correlation_id="pr-marker-crash")[0]
    assert intent.status == "applied"
    assert intent.postcondition["pr_number"] == 1


def test_noted_pr_is_recovered_by_number_after_prcreated_crash(tmp_path: Path) -> None:
    root, remote = _repository(tmp_path)
    branch = "samuel/pr-number-recovery"
    _git(root, "checkout", "-b", branch)
    (root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "candidate")
    _git(root, "push", "-u", "origin", branch)
    _git(root, "checkout", "main")
    state = SQLiteStateStore(tmp_path / "state")
    scm = _LocalSCM(root, remote)
    crashing_bus = Bus()

    def crash_after_prcreated(_event: Event) -> None:
        raise SystemExit(74)

    crashing_bus.subscribe("PRCreated", crash_after_prcreated)
    with pytest.raises(SystemExit) as crash:
        _pr_handler(tmp_path, crashing_bus, scm, state).handle(
            CreatePRCommand(
                issue_number=633,
                branch=branch,
                correlation_id="pr-number-crash",
            )
        )
    assert crash.value.code == 74
    intent = state.authority.list_intents(correlation_id="pr-number-crash")[0]
    assert intent.status == "applied"
    assert intent.postcondition["pr_number"] == 1

    result = _pr_handler(tmp_path, Bus(), scm, state).handle(
        CreatePRCommand(
            issue_number=633,
            branch=branch,
            correlation_id="pr-number-crash",
        )
    )
    assert result["passed"] is True
    assert len(scm.prs) == 1
