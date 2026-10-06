from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.adapters.workspace.git import GitWorktreeManager
from samuel.core.acceptance import (
    AcceptanceApproval,
    PlanningSourceSnapshot,
    issue_revision_digest,
    parse_acceptance_contract,
    render_planning_source,
)
from samuel.core.bus import Bus, ErrorMiddleware
from samuel.core.commands import ImplementCommand, PlanIssueCommand, ResumePendingCommand
from samuel.core.errors import ProviderUnavailable, SCMRevisionError
from samuel.core.evaluation_observation import EvaluationObservationIdentity
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import Event, GateEvaluationCompleted, HealingSuggested
from samuel.core.git import git_control_plane_paths
from samuel.core.ports import IConfig, ILLMProvider, IVersionControl
from samuel.core.types import Comment, Issue, LLMResponse
from samuel.core.workflow import WorkflowEngine
from samuel.core.workspaces import WorkspaceError
from samuel.slices.ac_verification.handler import ACVerificationHandler
from samuel.slices.healing.bound import BoundHealingCoordinator
from samuel.slices.implementation.handler import ImplementationHandler
from samuel.slices.implementation.patch_targets import resolve_patch_target
from samuel.slices.planning.handler import PlanningHandler
from samuel.slices.resume.handler import ResumeCoordinator


class _ResumeConfig(IConfig):
    def get(self, key: str, default=None):
        return True if key == "agent.resume.enabled" else default

    def feature_flag(self, name: str) -> bool:
        return False

    def reload(self) -> None:
        return None


def _classify_orphans(tmp_path: Path, manager: GitWorktreeManager) -> None:
    store = SQLiteStateStore(tmp_path / "state")
    coordinator = ResumeCoordinator(
        Bus(),
        authority_store=store.authority,
        workspace_manager=manager,
        config=_ResumeConfig(),
        owner_id="test-owner",
        projection_store=store.projections,
    )
    assert coordinator.handle(ResumePendingCommand())["attempted"] == 0


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    remote = tmp_path / "remote.git"
    root = tmp_path / "project"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    root.mkdir()
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "base")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "main")
    return root, _git(root, "rev-parse", "HEAD")


def _manager(tmp_path: Path, **kwargs: int) -> GitWorktreeManager:
    return GitWorktreeManager(
        tmp_path / "workspaces",
        reserve_bytes=kwargs.get("reserve_bytes", 1024),
        minimum_free_bytes=kwargs.get("minimum_free_bytes", 0),
        quarantine_max_count=kwargs.get("quarantine_max_count", 4),
        quarantine_max_bytes=kwargs.get("quarantine_max_bytes", 1024 * 1024),
    )


class _SCM(IVersionControl):
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def repository_identity(self) -> str:
        return f"file://{self.root}"

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Workspace", body="Implement change", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        issue = self.get_issue(number)
        source = PlanningSourceSnapshot(
            schema_version=1,
            repository=self.repository_identity,
            base_ref="main",
            base_sha=self.resolve_ref("main"),
            issue_digest=issue_revision_digest(
                number=issue.number,
                title=issue.title,
                body=issue.body,
            ),
        )
        return [
            Comment(
                id=1,
                body=(
                    "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] tracked.txt"
                    f"\n\n---\n\n{render_planning_source(source)}"
                ),
                user="bot",
            )
        ]

    def resolve_ref(self, ref: str) -> str:
        return _git(self.root, "rev-parse", f"origin/{ref}")

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=2, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str):
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        return None

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"name": name, "color": color}

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        return None

    def merge_pr(self, pr_id: int) -> bool:
        return False

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""


class _LLM(ILLMProvider):
    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        return LLMResponse(
            text=("## tracked.txt\n<<<<<<< SEARCH\nbase\n=======\ncandidate\n>>>>>>> REPLACE\n"),
            input_tokens=10,
            output_tokens=10,
            stop_reason="end_turn",
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


def test_run_and_verification_profiles_share_registry_and_stay_outside_repo(
    tmp_path: Path,
) -> None:
    root, head = _repository(tmp_path)
    (root / ".env").write_text("SECRET=not-copied\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "runtime-secret.txt").write_text("not copied\n", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "python").write_text("not copied\n", encoding="utf-8")
    (root / ".cache").mkdir()
    (root / ".cache" / "tool").write_text("not copied\n", encoding="utf-8")
    manager = _manager(tmp_path)

    run = manager.acquire_run(
        repository_root=root,
        workspace_id="run:42",
        branch="samuel/issue-42",
        base_ref="main",
    )
    verification = manager.acquire_verification(
        repository_root=root,
        workspace_id="verify:42",
        head_sha=head,
    )

    assert run.path.parent != root
    assert run.branch == "samuel/issue-42"
    assert (
        _git(root, "reflog", "show", "--format=%gs", "-1", "samuel/issue-42")
        == "samuel: create run-worktree branch"
    )
    assert verification.head_sha == head
    assert (run.path / ".git").is_file()
    assert (verification.path / ".git").is_file()
    assert not (run.path / ".env").exists()
    assert not (run.path / "data").exists()
    assert not (run.path / ".venv").exists()
    assert not (run.path / ".cache").exists()
    assert {record.profile for record in manager.list_workspaces()} == {"run", "verification"}

    manager.release(verification.workspace_id)
    manager.release(run.workspace_id)
    assert all(record.status == "terminal" for record in manager.list_workspaces())
    assert manager.prune() == {"trees_removed": 0, "records_removed": 2}
    assert manager.list_workspaces() == []


def test_verification_materializes_remote_commit_and_ignores_dirty_local_tree(
    tmp_path: Path,
) -> None:
    root, original_head = _repository(tmp_path)
    (root / "tracked.txt").write_text("remote\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "remote base")
    _git(root, "push", "origin", "main")
    remote_head = _git(root, "rev-parse", "HEAD")
    _git(root, "reset", "--hard", original_head)
    (root / "tracked.txt").write_text("dirty local\n", encoding="utf-8")
    manager = _manager(tmp_path)

    verification = manager.acquire_verification(
        repository_root=root,
        workspace_id="verify:remote-base",
        head_sha=remote_head,
        base_ref="main",
    )

    assert verification.head_sha == remote_head
    assert (verification.path / "tracked.txt").read_text(encoding="utf-8") == "remote\n"
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "dirty local\n"
    manager.release(verification.workspace_id)


def test_bound_workspaces_block_when_remote_base_moved(tmp_path: Path) -> None:
    root, head = _repository(tmp_path)
    manager = _manager(tmp_path)

    with pytest.raises(WorkspaceError) as verification_error:
        manager.acquire_verification(
            repository_root=root,
            workspace_id="verify:stale",
            head_sha="f" * 40,
            base_ref="main",
        )
    with pytest.raises(WorkspaceError) as run_error:
        manager.acquire_run(
            repository_root=root,
            workspace_id="run:stale",
            branch="samuel/issue-stale",
            base_ref="main",
            expected_base_sha="f" * 40,
        )

    assert verification_error.value.code == "workspace_base_changed"
    assert run_error.value.code == "workspace_base_changed"
    assert _git(root, "rev-parse", "origin/main") == head


def test_planning_context_and_contract_are_bound_to_remote_base(tmp_path: Path) -> None:
    root, original_head = _repository(tmp_path)
    (root / "tracked.txt").write_text("remote tracked marker\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "remote planning base")
    _git(root, "push", "origin", "main")
    remote_head = _git(root, "rev-parse", "HEAD")
    _git(root, "reset", "--hard", original_head)
    (root / "tracked.txt").write_text("local tracked marker\n", encoding="utf-8")
    scm = _SCM(root)
    scm.get_comments = lambda number: []  # type: ignore[method-assign]
    scm.get_issue = lambda number: Issue(  # type: ignore[method-assign]
        number=number,
        title="Tracked marker",
        body="Change the tracked marker",
        state="open",
    )
    posted: list[str] = []

    def post_comment(number: int, body: str) -> Comment:
        posted.append(body)
        return Comment(id=2, body=body, user="bot")

    scm.post_comment = post_comment  # type: ignore[method-assign]

    class _PlanningLLM(_LLM):
        def __init__(self) -> None:
            self.prompt = ""

        def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
            self.prompt = messages[0]["content"]
            return LLMResponse(
                text=(
                    "## Analyse\nUpdate `tracked.txt`.\n\n"
                    "### Änderungsscope\nScope-Schema: 1\n"
                    "- [FILE] `tracked.txt`\nArchitecture-Expansion: disabled\n\n"
                    "### Akzeptanzkriterien\n"
                    "- [ ] [DIFF] tracked.txt — Datei geändert\n"
                    "- [ ] [TEST] tests/test_workspace_manager.py::test_workspace — Tests grün\n"
                ),
                input_tokens=10,
                output_tokens=10,
            )

    llm = _PlanningLLM()
    events: list[Event] = []
    bus = Bus()
    bus.subscribe("*", events.append)
    handler = PlanningHandler(
        bus,
        scm=scm,
        llm=llm,
        project_root=root,
        workspace_manager=_manager(tmp_path),
        keyword_extensions={".txt"},
    )

    result = handler.handle(PlanIssueCommand(issue_number=42, correlation_id="plan-bound"))

    assert result["score"] >= 80
    assert "remote tracked marker" in llm.prompt
    assert "local tracked marker" not in llm.prompt
    assert posted and f'"base_sha":"{remote_head}"' in posted[-1]
    context_event = next(event for event in events if event.name == "PlanContextLoaded")
    assert context_event.payload["source_snapshot"]["base_sha"] == remote_head


def test_planning_blocks_before_llm_when_repository_has_no_base_commit(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)

    class _NoCommitSCM(_SCM):
        def get_comments(self, number: int) -> list[Comment]:
            return []

        def resolve_ref(self, ref: str) -> str:
            raise SCMRevisionError("revision_not_found", "Repository has no base commit")

    class _NeverLLM(_LLM):
        def __init__(self) -> None:
            self.called = False

        def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
            self.called = True
            return super().complete(messages, **kwargs)

    llm = _NeverLLM()
    events: list[Event] = []
    bus = Bus()
    bus.subscribe("*", events.append)
    handler = PlanningHandler(
        bus,
        scm=_NoCommitSCM(root),
        llm=llm,
        project_root=root,
        workspace_manager=_manager(tmp_path),
    )

    result = handler.handle(PlanIssueCommand(issue_number=42, correlation_id="no-commit"))

    assert result is None
    assert llm.called is False
    assert any(
        event.name == "PlanBlocked" and event.payload["reason"] == "revision_not_found"
        for event in events
    )


def test_planning_blocks_before_llm_when_scm_ref_resolution_is_unavailable(
    tmp_path: Path,
) -> None:
    root, _ = _repository(tmp_path)

    class _UnavailableSCM(_SCM):
        def get_comments(self, number: int) -> list[Comment]:
            return []

        def resolve_ref(self, ref: str) -> str:
            raise OSError("SCM unavailable")

    class _NeverLLM(_LLM):
        def __init__(self) -> None:
            self.called = False

        def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
            self.called = True
            return super().complete(messages, **kwargs)

    llm = _NeverLLM()
    events: list[Event] = []
    bus = Bus()
    bus.subscribe("*", events.append)
    handler = PlanningHandler(
        bus,
        scm=_UnavailableSCM(root),
        llm=llm,
        project_root=root,
        workspace_manager=_manager(tmp_path),
    )

    result = handler.handle(PlanIssueCommand(issue_number=42, correlation_id="scm-down"))

    assert result is None
    assert llm.called is False
    assert any(
        event.name == "PlanBlocked"
        and event.payload["reason"] == "planning_source_snapshot_unavailable"
        for event in events
    )


def test_implementation_blocks_before_llm_when_planned_base_moved(tmp_path: Path) -> None:
    root, planned_head = _repository(tmp_path)
    issue = Issue(number=42, title="Workspace", body="Implement change", state="open")
    source = PlanningSourceSnapshot(
        schema_version=1,
        repository=f"file://{root}",
        base_ref="main",
        base_sha=planned_head,
        issue_digest=issue_revision_digest(
            number=issue.number,
            title=issue.title,
            body=issue.body,
        ),
    )
    frozen_plan = (
        "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] tracked.txt"
        f"\n\n---\n\n{render_planning_source(source)}"
    )
    (root / "tracked.txt").write_text("new base\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "move main")
    _git(root, "push", "origin", "main")

    class _FrozenSCM(_SCM):
        def get_comments(self, number: int) -> list[Comment]:
            return [Comment(id=1, body=frozen_plan, user="bot")]

    class _NeverLLM(_LLM):
        def __init__(self) -> None:
            self.called = False

        def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
            self.called = True
            return super().complete(messages, **kwargs)

    llm = _NeverLLM()
    events: list[Event] = []
    bus = Bus()
    bus.subscribe("*", events.append)
    handler = ImplementationHandler(
        bus,
        scm=_FrozenSCM(root),
        llm=llm,
        project_root=root,
        enforce_context_quality=False,
        workspace_manager=_manager(tmp_path),
    )

    result = handler.handle(ImplementCommand(issue_number=42, correlation_id="stale-plan"))

    assert result["success"] is False
    assert result["reason"] == "planning_base_changed"
    assert llm.called is False
    assert any(
        event.name == "WorkflowBlocked" and event.payload["reason"] == "planning_base_changed"
        for event in events
    )


def test_implementation_rejects_approval_from_superseded_plan_instance(tmp_path: Path) -> None:
    root, planned_head = _repository(tmp_path)
    issue = Issue(number=42, title="Workspace", body="Implement change", state="open")
    source = PlanningSourceSnapshot(
        schema_version=1,
        repository=f"file://{root}",
        base_ref="main",
        base_sha=planned_head,
        issue_digest=issue_revision_digest(
            number=issue.number,
            title=issue.title,
            body=issue.body,
        ),
    )
    plan = (
        "## Plan\n### Akzeptanzkriterien\n- [ ] [DIFF] tracked.txt"
        f"\n\n---\n\n{render_planning_source(source)}"
    )
    contract = parse_acceptance_contract(plan)

    class _CurrentPlanSCM(_SCM):
        def get_comments(self, number: int) -> list[Comment]:
            return [Comment(id=22, body=plan, user="bot")]

    stale_approval = AcceptanceApproval(
        state="approved",
        actor="alice",
        method="status:approved/polling",
        source_id="plan:21;event:9",
        approved_at="2026-09-17T10:00:00Z",
        contract_hash=contract.contract_hash,
        plan_comment_id=21,
    )
    handler = ImplementationHandler(Bus(), scm=_CurrentPlanSCM(root), project_root=root)

    with pytest.raises(ValueError, match="planning_approval_changed"):
        handler._planning_source(
            42,
            ImplementCommand(
                issue_number=42,
                payload={
                    "acceptance_contract": contract.as_dict(),
                    "acceptance_approval": stale_approval.as_dict(),
                },
            ),
        )


def test_implementation_mutates_only_run_worktree_and_pushes_content_bound_commit(
    tmp_path: Path,
) -> None:
    root, original_head = _repository(tmp_path)
    manager = _manager(tmp_path)
    bus = Bus()
    generated: list[Event] = []
    bus.subscribe("CodeGenerated", generated.append)
    handler = ImplementationHandler(
        bus,
        scm=_SCM(root),
        llm=_LLM(),
        project_root=root,
        enforce_context_quality=False,
        workspace_manager=manager,
    )

    result = handler.handle(ImplementCommand(issue_number=42, correlation_id="run-42"))

    assert result["success"] is True
    assert _git(root, "rev-parse", "HEAD") == original_head
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    remote_head = _git(root, "rev-parse", "origin/samuel/issue-42")
    assert remote_head != original_head
    assert _git(root, "show", f"{remote_head}:tracked.txt") == "candidate"
    assert len(generated) == 1
    assert generated[0].payload["workspace_id"].startswith("run-workspace:sha256:")
    records = manager.list_workspaces()
    assert len(records) == 1 and records[0].status == "terminal"
    assert not Path(records[0].path).exists()


def test_synchronous_bound_healing_reuses_worktree_and_redispatches_gate_path(
    tmp_path: Path,
) -> None:
    root, original_head = _repository(tmp_path)
    manager = _manager(tmp_path)
    bus = Bus()

    class _HealingLLM(_LLM):
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
            self.calls += 1
            before = "base" if self.calls == 1 else "candidate"
            after = "candidate" if self.calls == 1 else "healed"
            return LLMResponse(
                text=(
                    f"## tracked.txt\n<<<<<<< SEARCH\n{before}\n=======\n{after}\n>>>>>>> REPLACE\n"
                ),
                input_tokens=10,
                output_tokens=10,
                stop_reason="end_turn",
            )

    llm = _HealingLLM()
    handler = ImplementationHandler(
        bus,
        scm=_SCM(root),
        llm=llm,
        project_root=root,
        enforce_context_quality=False,
        workspace_manager=manager,
    )
    generated: list[Event] = []
    gate_heads: list[str] = []
    bus.subscribe("CodeGenerated", generated.append)
    bus.register_command("Implement", handler.handle)

    def run_gate_path(command) -> dict[str, bool]:
        branch = command.payload["branch"]
        candidate_head = _git(root, "rev-parse", f"origin/{branch}")
        gate_heads.append(candidate_head)
        if len(gate_heads) == 1:
            bus.publish(
                HealingSuggested(
                    correlation_id=command.correlation_id,
                    payload={
                        "issue": 42,
                        "branch": branch,
                        "resume_head_sha": candidate_head,
                        "workspace_id": command.payload["workspace_id"],
                        "heal_hint": "repair the failed criterion",
                    },
                )
            )
        return {"passed": len(gate_heads) == 2}

    bus.register_command("CreatePR", run_gate_path)
    WorkflowEngine(
        bus,
        {
            "steps": [
                {"on": "CodeGenerated", "send": "CreatePR"},
                {"on": "HealingSuggested", "send": "Implement"},
            ]
        },
    )

    first = bus.send(
        ImplementCommand(
            issue_number=42,
            correlation_id="healing-run",
            payload={},
        )
    )

    assert first["success"] is True
    assert llm.calls == 2
    assert len(generated) == 2
    assert len(gate_heads) == 2 and gate_heads[0] != gate_heads[1]
    assert generated[0].payload["workspace_id"] == generated[1].payload["workspace_id"]
    assert _git(root, "show", "origin/samuel/issue-42:tracked.txt") == "healed"
    assert _git(root, "rev-parse", "HEAD") == original_head
    record = manager.inspect(generated[0].payload["workspace_id"])
    assert record is not None and record.status == "terminal"
    assert not Path(record.path).exists()


def test_implementation_provider_unavailable_blocks_correlated_run(tmp_path: Path) -> None:
    root, original_head = _repository(tmp_path)
    manager = _manager(tmp_path)
    bus = Bus()
    bus.add_middleware(ErrorMiddleware(bus))
    events: list[Event] = []
    bus.subscribe("*", events.append)

    class _UnavailableLLM(_LLM):
        def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
            raise ProviderUnavailable(
                "openrouter",
                reason="raw provider response must remain private",
                code="missing_content",
                retryable=False,
            )

    handler = ImplementationHandler(
        bus,
        scm=_SCM(root),
        llm=_UnavailableLLM(),
        project_root=root,
        enforce_context_quality=False,
        workspace_manager=manager,
    )
    bus.register_command("Implement", handler.handle)

    result = bus.send(ImplementCommand(issue_number=42, correlation_id="implementation-run-42"))

    blocked = [event for event in events if event.name == "WorkflowBlocked"]
    assert result["reason"] == "provider_unavailable"
    assert len(blocked) == 1
    assert blocked[0].correlation_id == "implementation-run-42"
    assert blocked[0].payload["issue"] == 42
    assert blocked[0].payload["reason"] == "provider_unavailable"
    assert blocked[0].payload["provider_error"] == {
        "code": "missing_content",
        "retryable": False,
    }
    assert not {"WorkflowAborted", "CodeGenerated", "PRCreated"} & {event.name for event in events}
    assert "raw provider response" not in str(blocked[0].payload)
    assert _git(root, "rev-parse", "HEAD") == original_head
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "base\n"


def test_bound_healing_implementation_provider_unavailable_blocks_without_mutation(
    tmp_path: Path,
) -> None:
    root, original_head = _repository(tmp_path)
    manager = _manager(tmp_path)
    state = SQLiteStateStore(tmp_path / "state")
    bus = Bus()
    bus.add_middleware(ErrorMiddleware(bus))
    events: list[Event] = []
    bus.subscribe("*", events.append)
    scm = _SCM(root)
    observation_keys: list[str] = []

    class _HealingConfig(IConfig):
        def get(self, key: str, default=None):
            return default

        def feature_flag(self, name: str) -> bool:
            return name == "healing"

        def reload(self) -> None:
            pass

    class _BoundLLM(_LLM):
        def __init__(self) -> None:
            self.implementation_calls = 0
            self.healing_calls = 0

        def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
            if kwargs.get("task") == "healing":
                self.healing_calls += 1
                return LLMResponse(
                    text="Repair the failed criterion", input_tokens=5, output_tokens=5
                )
            self.implementation_calls += 1
            if self.implementation_calls == 1:
                text = "## tracked.txt\n<<<<<<< SEARCH\nbase\n=======\ncandidate\n>>>>>>> REPLACE\n"
            elif self.implementation_calls == 2:
                text = (
                    "## tracked.txt\n<<<<<<< SEARCH\ncandidate\n=======\ntemporary\n>>>>>>> REPLACE\n"
                    "## missing.txt\n<<<<<<< SEARCH\nabsent\n=======\nreplacement\n>>>>>>> REPLACE\n"
                )
            else:
                raise ProviderUnavailable(
                    "openrouter",
                    reason="raw provider response must remain private",
                    code="missing_content",
                    status=503,
                    retryable=False,
                )
            return LLMResponse(text=text, input_tokens=10, output_tokens=10)

    llm = _BoundLLM()
    handler = ImplementationHandler(
        bus,
        scm=scm,
        llm=llm,
        project_root=root,
        enforce_context_quality=False,
        workspace_manager=manager,
    )
    bus.register_command("Implement", handler.handle)
    BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_HealingConfig(),
        authority_store=state.authority,
    ).register()
    WorkflowEngine(bus, {"steps": [{"on": "HealingSuggested", "send": "Implement"}]})

    def on_candidate(event: Event) -> None:
        candidate_head = _git(root, "rev-parse", "origin/samuel/issue-42")
        subject = EvaluationSubject.from_dict(
            {
                "repository": scm.repository_identity,
                "base_sha": original_head,
                "head_sha": candidate_head,
                "contract_hash": parse_acceptance_contract(
                    scm.get_comments(42)[0].body
                ).contract_hash,
                "policy_version": "gates.v1",
                "policy_digest": "sha256:" + "d" * 64,
            }
        )
        subject_data = subject.as_dict()
        gate_results = [
            {
                "gate": 11,
                "passed": False,
                "executed": True,
                "status": "failed",
                "reason_code": "gate_11_failed",
                "authority": "required",
                "evaluation_subject": subject_data,
            }
        ]
        approval = {
            "state": "approved",
            "actor": "maintainer",
            "method": "scm_label",
            "source_id": "plan:1;label:event:8",
            "approved_at": "2026-09-29T09:00:00Z",
            "plan_comment_id": 1,
            "contract_hash": subject.contract_hash,
        }
        acceptance_evidence = {
            "evaluation_subject": subject_data,
            "contract": {"contract_hash": subject.contract_hash, "approval": approval},
            "results": [
                {
                    "criterion_id": "AC-1234",
                    "tag": "TEST",
                    "status": "failed",
                    "reason": "test failed",
                    "evidence": {
                        "schema_version": 1,
                        "kind": "test",
                        "test_name": "tests/test_feature.py::test_feature",
                        "runner": "pytest",
                        "exit_code": 1,
                    },
                }
            ],
        }
        identity = EvaluationObservationIdentity.build(
            subject=subject,
            gate_results=gate_results,
            acceptance_evidence=acceptance_evidence,
        )
        observation_keys.append(identity.observation_key)
        workspace_id = event.payload["workspace_id"]
        bus.publish(
            GateEvaluationCompleted(
                payload={
                    "issue": 42,
                    "branch": "samuel/issue-42",
                    "base": "main",
                    "blocked": True,
                    "observation_key": identity.observation_key,
                    "evidence_digest": identity.evidence_digest,
                    "observation_schema_version": identity.schema_version,
                    "gate_result_schema_version": 2,
                    "evaluation_subject": subject_data,
                    "gate_results": gate_results,
                    "acceptance_evidence": acceptance_evidence,
                    "workspace_id": workspace_id,
                    "evaluation_mode": "reference_worker",
                    "mutation_authority": {
                        "schema_version": 1,
                        "authority": "mutate_candidate",
                        "source": "approved_plan_workflow",
                        "issue": 42,
                        "plan_comment_id": 1,
                        "contract_hash": subject.contract_hash,
                        "approval_source_id": approval["source_id"],
                        "workspace_id": workspace_id,
                        "correlation_id": event.correlation_id,
                    },
                },
                correlation_id=event.correlation_id,
            )
        )

    bus.subscribe("CodeGenerated", on_candidate)
    result = bus.send(ImplementCommand(issue_number=42, correlation_id="healing-run-42"))

    assert result["success"] is True
    assert llm.healing_calls == 1
    assert llm.implementation_calls == 3
    assert [event.name for event in events].count("HealingAttemptStarted") == 1
    assert [event.name for event in events].count("HealingSuggested") == 1
    assert [event.name for event in events].count("CodeGenerated") == 1
    blocked = [event for event in events if event.name == "WorkflowBlocked"]
    assert len(blocked) == 1
    assert blocked[0].correlation_id == "healing-run-42"
    assert blocked[0].payload["reason"] == "provider_unavailable"
    assert blocked[0].payload["provider_error"] == {
        "code": "missing_content",
        "retryable": False,
        "status": 503,
    }
    assert not {"WorkflowAborted", "PRCreated"} & {event.name for event in events}
    assert "raw provider response" not in str(blocked[0].payload)
    claim = state.authority.get_healing_claim(observation_keys[0])
    assert claim is not None and claim.status == "attempted" and claim.outcome == "suggested"
    assert _git(root, "rev-parse", "HEAD") == original_head
    assert (root / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert _git(root, "show", "origin/samuel/issue-42:tracked.txt") == "candidate"
    assert all(not Path(record.path).exists() for record in manager.list_workspaces())


def test_linked_worktree_keeps_git_control_plane_protection(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    manager = _manager(tmp_path)
    run = manager.acquire_run(
        repository_root=root,
        workspace_id="run:603",
        branch="samuel/issue-603-proof",
        base_ref="main",
    )

    control_paths = git_control_plane_paths(run.path)
    allowed, allowed_reason = resolve_patch_target(
        run.path,
        "tracked.txt",
        git_control_paths=control_paths,
    )
    blocked, blocked_reason = resolve_patch_target(
        run.path,
        ".git/HEAD",
        git_control_paths=control_paths,
    )

    assert allowed is not None and allowed_reason is None
    assert blocked is None and blocked_reason == "git_control_plane"
    assert any(not path.is_relative_to(run.path) for path in control_paths)
    manager.release(run.workspace_id)


def test_ac_verifier_uses_shared_verification_profile(tmp_path: Path) -> None:
    root, head = _repository(tmp_path)
    manager = _manager(tmp_path)
    handler = ACVerificationHandler(Bus(), project_root=root, workspace_manager=manager)

    with handler._candidate_root(head, "gate-run-42") as (candidate, error):
        assert error == ""
        assert candidate is not None
        assert (candidate / "tracked.txt").read_text(encoding="utf-8") == "base\n"
        active = manager.list_workspaces()
        assert len(active) == 1
        assert active[0].profile == "verification"
        assert active[0].status == "active"

    record = manager.list_workspaces()[0]
    assert record.status == "terminal"
    assert not Path(record.path).exists()


def test_second_manager_cannot_own_same_branch(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    first = _manager(tmp_path)
    run = first.acquire_run(
        repository_root=root,
        workspace_id="run:first",
        branch="samuel/issue-1",
        base_ref="main",
    )
    second = _manager(tmp_path)

    with pytest.raises(WorkspaceError, match="owned by another process") as error:
        second.acquire_run(
            repository_root=root,
            workspace_id="run:second",
            branch="samuel/issue-1",
            base_ref="main",
        )

    assert error.value.code == "workspace_owned"
    assert first.inspect(run.workspace_id).status == "active"  # type: ignore[union-attr]
    first.release(run.workspace_id)


def test_separate_process_cannot_take_a_live_branch_lock(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    first = _manager(tmp_path)
    run = first.acquire_run(
        repository_root=root,
        workspace_id="run:parent",
        branch="samuel/issue-process-lock",
        base_ref="main",
    )
    script = """
from pathlib import Path
from samuel.adapters.workspace.git import GitWorktreeManager
from samuel.core.workspaces import WorkspaceError

manager = GitWorktreeManager(
    Path({work_dir!r}), reserve_bytes=1024, minimum_free_bytes=0,
    quarantine_max_count=4, quarantine_max_bytes=1024 * 1024,
)
try:
    manager.acquire_run(
        repository_root=Path({root!r}), workspace_id="run:child",
        branch="samuel/issue-process-lock", base_ref="main",
    )
except WorkspaceError as exc:
    print(exc.code)
""".format(work_dir=str(tmp_path / "workspaces"), root=str(root))

    child = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert child.returncode == 0
    assert child.stdout.strip() == "workspace_owned"
    assert first.inspect(run.workspace_id).status == "active"  # type: ignore[union-attr]
    first.release(run.workspace_id)


def test_separate_process_can_own_a_different_branch(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    first = _manager(tmp_path)
    parent = first.acquire_run(
        repository_root=root,
        workspace_id="run:parent-other",
        branch="samuel/issue-parent",
        base_ref="main",
    )
    script = """
from pathlib import Path
from samuel.adapters.workspace.git import GitWorktreeManager

manager = GitWorktreeManager(
    Path({work_dir!r}), reserve_bytes=1024, minimum_free_bytes=0,
    quarantine_max_count=4, quarantine_max_bytes=1024 * 1024,
)
workspace = manager.acquire_run(
    repository_root=Path({root!r}), workspace_id="run:child-other",
    branch="samuel/issue-child", base_ref="main",
)
print(workspace.branch, flush=True)
manager.release(workspace.workspace_id)
""".format(work_dir=str(tmp_path / "workspaces"), root=str(root))

    child = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert child.returncode == 0
    assert child.stdout.strip() == "samuel/issue-child"
    assert parent.path.exists()
    assert first.inspect(parent.workspace_id).status == "active"  # type: ignore[union-attr]
    first.release(parent.workspace_id)


def test_hard_process_exit_is_quarantined_by_explicit_resume_classification(
    tmp_path: Path,
) -> None:
    root, _ = _repository(tmp_path)
    script = """
import os
from pathlib import Path
from samuel.adapters.workspace.git import GitWorktreeManager

manager = GitWorktreeManager(
    Path({work_dir!r}), reserve_bytes=1024, minimum_free_bytes=0,
    quarantine_max_count=4, quarantine_max_bytes=1024 * 1024,
)
workspace = manager.acquire_run(
    repository_root=Path({root!r}), workspace_id="run:crashed-child",
    branch="samuel/issue-crashed-child", base_ref="main",
)
print(workspace.path, flush=True)
os._exit(0)
""".format(work_dir=str(tmp_path / "workspaces"), root=str(root))
    child = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0

    recovered = _manager(tmp_path)
    assert recovered.inspect("run:crashed-child").status == "active"  # type: ignore[union-attr]
    _classify_orphans(tmp_path, recovered)
    record = recovered.inspect("run:crashed-child")

    assert record is not None
    assert record.status == "quarantined"
    assert record.reason == "owner_process_missing_without_resume_authority"
    assert Path(child.stdout.strip()).exists()


def test_bound_healing_reuses_active_run_until_outer_owner_releases(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    manager = _manager(tmp_path)
    first = manager.acquire_run(
        repository_root=root,
        workspace_id="run:healing",
        branch="samuel/issue-healing",
        base_ref="main",
    )
    (first.path / "tracked.txt").write_text("candidate\n", encoding="utf-8")
    _git(first.path, "add", "tracked.txt")
    _git(first.path, "commit", "-m", "candidate")
    candidate_head = _git(first.path, "rev-parse", "HEAD")

    nested = manager.acquire_run(
        repository_root=root,
        workspace_id="run:healing",
        branch="samuel/issue-healing",
        base_ref="main",
        expected_head=candidate_head,
    )

    assert nested.path == first.path
    assert nested.head_sha == candidate_head
    manager.release(nested.workspace_id)
    assert first.path.exists()
    assert manager.inspect(first.workspace_id).status == "active"  # type: ignore[union-attr]
    manager.release(first.workspace_id)
    assert not first.path.exists()
    assert manager.inspect(first.workspace_id).status == "terminal"  # type: ignore[union-attr]


def test_abandoned_owner_becomes_visible_after_resume_classification(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    first = _manager(tmp_path)
    run = first.acquire_run(
        repository_root=root,
        workspace_id="run:abandoned",
        branch="samuel/issue-abandoned",
        base_ref="main",
    )
    first._unlock(run.workspace_id)  # simulate the lock release caused by process death

    second = _manager(tmp_path)
    assert second.inspect(run.workspace_id).status == "active"  # type: ignore[union-attr]
    _classify_orphans(tmp_path, second)

    record = second.inspect(run.workspace_id)
    assert record is not None
    assert record.status == "quarantined"
    assert record.reason == "owner_process_missing_without_resume_authority"
    assert run.path.exists()
    assert second.prune() == {"trees_removed": 0, "records_removed": 0}


def test_quarantine_capacity_blocks_new_run_without_deleting_evidence(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    manager = _manager(tmp_path, quarantine_max_count=1)
    first = manager.acquire_run(
        repository_root=root,
        workspace_id="run:q",
        branch="samuel/issue-q",
        base_ref="main",
    )
    manager.quarantine(first.workspace_id, reason="crash")

    with pytest.raises(WorkspaceError) as error:
        manager.acquire_run(
            repository_root=root,
            workspace_id="run:blocked",
            branch="samuel/issue-blocked",
            base_ref="main",
        )

    assert error.value.code == "workspace_quarantine_capacity"
    assert first.path.exists()
    quarantined = manager.inspect(first.workspace_id)
    assert quarantined is not None
    assert datetime.fromisoformat(quarantined.quarantine_until) > datetime.now(timezone.utc)


def test_operator_discard_requires_reason_and_terminalizes_reviewed_quarantine(
    tmp_path: Path,
) -> None:
    root, _ = _repository(tmp_path)
    manager = _manager(tmp_path)
    run = manager.acquire_run(
        repository_root=root,
        workspace_id="run:reviewed",
        branch="samuel/issue-reviewed",
        base_ref="main",
    )
    manager.quarantine(run.workspace_id, reason="hard stop")

    with pytest.raises(WorkspaceError) as missing_reason:
        manager.discard_quarantine(run.workspace_id, reason="")
    manager.discard_quarantine(run.workspace_id, reason="operator inspected evidence")

    assert missing_reason.value.code == "workspace_discard_reason_required"
    record = manager.inspect(run.workspace_id)
    assert record is not None and record.status == "terminal"
    assert record.reason.startswith("operator_discard:")
    assert not run.path.exists()


def test_real_free_space_preflight_blocks_before_worktree_creation(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    free = shutil.disk_usage(tmp_path).free
    manager = _manager(tmp_path, minimum_free_bytes=free)

    with pytest.raises(WorkspaceError) as error:
        manager.acquire_run(
            repository_root=root,
            workspace_id="run:no-capacity",
            branch="samuel/issue-no-capacity",
            base_ref="main",
        )

    assert error.value.code == "workspace_capacity_insufficient"
    assert manager.inspect("run:no-capacity") is None
    assert not (tmp_path / "workspaces" / "trees" / "run").exists()


def test_prune_removes_terminal_records_and_unambiguous_git_orphans(tmp_path: Path) -> None:
    root, head = _repository(tmp_path)
    manager = _manager(tmp_path)
    terminal = manager.acquire_verification(
        repository_root=root,
        workspace_id="verify:terminal",
        head_sha=head,
    )
    manager.release(terminal.workspace_id)
    orphan = tmp_path / "orphan-worktree"
    _git(root, "worktree", "add", "--detach", str(orphan), head)
    shutil.rmtree(orphan)
    assert str(orphan) in _git(root, "worktree", "list", "--porcelain")

    result = manager.prune()

    assert result == {"trees_removed": 0, "records_removed": 1}
    assert str(orphan) not in _git(root, "worktree", "list", "--porcelain")


def test_workspace_state_overlap_and_invalid_capacity_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError) as overlap:
        GitWorktreeManager(
            tmp_path / "runtime" / "workspaces",
            data_dir=tmp_path / "runtime",
        )
    with pytest.raises(WorkspaceError) as invalid:
        GitWorktreeManager(tmp_path / "other", reserve_bytes=0)

    assert overlap.value.code == "workspace_state_overlap"
    assert invalid.value.code == "workspace_configuration_invalid"


@pytest.mark.parametrize(
    "name",
    (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_COMMON_DIR",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ),
)
def test_dangerous_git_path_override_blocks_manager_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    monkeypatch.setenv(name, os.fspath(tmp_path / "override"))

    with pytest.raises(WorkspaceError) as error:
        _manager(tmp_path)

    assert error.value.code == "workspace_git_environment_unsafe"
