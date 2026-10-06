from __future__ import annotations

import hashlib
import hmac
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.adapters.llm.token_budget import TokenBudgetLLMAdapter
from samuel.adapters.llm.workflow_budget import (
    LogicalCallLLMAdapter,
    WorkflowTokenBudgetLLMAdapter,
)
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.acceptance import (
    AcceptanceApproval,
    parse_acceptance_contract,
    persist_plan_approval,
)
from samuel.core.bus import Bus
from samuel.core.commands import CreatePRCommand, ScanIssuesCommand
from samuel.core.evaluation_subject import (
    EvaluationSubject,
    PullRequestRevision,
    RevisionComparison,
)
from samuel.core.events import Event
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.state import (
    LLMBudgetAttemptRecord,
    WorkflowBudgetAdmissionRecord,
    WorkflowCheckpointRecord,
)
from samuel.core.types import PR, Comment, Issue, Label, LLMResponse, SCMLabelEvent
from samuel.core.workflow import WorkflowEngine
from samuel.slices.ac_verification.handler import ACVerificationHandler
from samuel.slices.healing.bound import BoundHealingCoordinator
from samuel.slices.labels.handler import LabelsHandler
from samuel.slices.pr_gates.handler import PRGatesHandler
from samuel.slices.review.handler import ReviewHandler
from samuel.slices.watch.handler import WatchHandler


class CandidateSCM(IVersionControl):
    def __init__(self, base: str, head: str) -> None:
        self.base = base
        self.head = head
        self.posted_comments: list[Comment] = []
        self.closed_issues: list[int] = []
        self.plan = """## Plan
### Änderungsscope
Scope-Schema: 1
- [FILE] `candidate.py`
Architecture-Expansion: disabled
### Akzeptanzkriterien
- [x] [DIFF] candidate.py — Datei geändert"""

    @property
    def repository_identity(self) -> str:
        return "owner/repo"

    def resolve_ref(self, ref: str) -> str:
        return self.base if ref == "main" else self.head

    def compare_commits(
        self, base_sha: str, head_sha: str, *, max_diff_bytes: int
    ) -> RevisionComparison:
        diff = "+VALUE = 2\n-VALUE = 1\n"
        return RevisionComparison(
            repository=self.repository_identity,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_files=("candidate.py",),
            diff=diff,
            diff_bytes=len(diff.encode()),
        )

    def get_pr_revision(self, pr_id: int) -> PullRequestRevision:
        return PullRequestRevision(self.repository_identity, self.base, self.head)

    def get_issue(self, number: int) -> Issue:
        return Issue(number, "Test", "body", "open")

    def get_comments(self, number: int) -> list[Comment]:
        return [
            Comment(1, self.plan, "samuel", "2026-08-25T10:00:00Z"),
            Comment(2, "/approve", "alice", "2026-08-25T10:01:00Z"),
        ]

    def post_comment(self, number: int, body: str) -> Comment:
        comment = Comment(100 + len(self.posted_comments), body, "samuel")
        self.posted_comments.append(comment)
        return comment

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        return PR(1, 7, title, "http://scm/pr/7")

    def swap_label(self, number: int, remove: str, add: str) -> None: ...

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {}

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        self.closed_issues.append(number)

    def merge_pr(self, pr_id: int) -> bool:
        return False

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""


def _commit(repository: Path, message: str) -> str:
    subprocess.run(["git", "add", "candidate.py"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repository, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_gate_11_consumes_bound_verifier_evidence_not_checkbox_state(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    (repository / "candidate.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = _commit(repository, "base")
    (repository / "candidate.py").write_text("VALUE = 2\n", encoding="utf-8")
    head = _commit(repository, "candidate")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "gates.json").write_text(
        '{"policy_version":"test.v1","required":[11],"optional":[12],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    bus = Bus()
    bus.register_command("VerifyAC", ACVerificationHandler(bus, repository).handle)

    scm = CandidateSCM(base, head)
    state = _bind_candidate_authority(tmp_path, scm)
    result: dict[str, Any] = PRGatesHandler(
        bus,
        scm=scm,
        config_dir=config_dir,
        project_root=repository,
        authority_store=state.authority,
    ).handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42"},
            correlation_id="acceptance-healing-42",
        )
    )

    assert result["passed"] is True
    assert next(item for item in result["results"] if item.gate == 11).status == "passed"
    assert result["acceptance_evidence"]["evaluation_subject"]["head_sha"] == head
    assert result["acceptance_evidence"]["contract"]["approval"]["actor"] == "alice"


def test_real_failed_test_reaches_bound_healing_classification(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    (repository / "candidate.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository / "test_candidate.py").write_text(
        "from candidate import VALUE\n\ndef test_value():\n    assert VALUE == 3\n",
        encoding="utf-8",
    )
    (repository / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath = ['.']\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repository / "candidate.py").write_text("VALUE = 2\n", encoding="utf-8")
    head = _commit(repository, "candidate")

    scm = CandidateSCM(base, head)
    scm.plan = """## Plan
### Änderungsscope
Scope-Schema: 1
- [FILE] `candidate.py`
Architecture-Expansion: disabled
### Akzeptanzkriterien
- [ ] [TEST] test_candidate.py::test_value
"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "gates.json").write_text(
        '{"policy_version":"test.v1","required":[11],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    bus = Bus()
    bus.register_command("VerifyAC", ACVerificationHandler(bus, repository).handle)
    BoundHealingCoordinator(
        bus,
        llm=None,
        config=None,
        authority_store=None,
    ).register()
    events: list[Any] = []
    bus.subscribe("*", events.append)

    result = PRGatesHandler(
        bus,
        scm=scm,
        config_dir=config_dir,
        project_root=repository,
        authority_store=_bind_candidate_authority(tmp_path, scm).authority,
    ).handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42"},
            correlation_id="acceptance-healing-42",
        )
    )

    assert result["passed"] is False
    failed = result["acceptance_evidence"]["results"][0]
    assert failed["status"] == "failed"
    assert failed["evidence"]["kind"] == "test"
    assert failed["evidence"]["exit_code"] != 0
    classified = next(event for event in events if event.name == "HealingClassified")
    assert classified.payload["classification"] == "healable"
    assert classified.payload["reason"] == "single_automatic_failure"


class _ManualCandidateSCM(CandidateSCM):
    PLAN_ID = 71

    def __init__(self, base: str, head: str) -> None:
        super().__init__(base, head)
        self.plan = """## Plan
### Änderungsscope
Scope-Schema: 1
- [FILE] `candidate.py`
Architecture-Expansion: disabled
### Akzeptanzkriterien
- [ ] [DIFF] candidate.py
- [ ] [MANUAL] Candidate wurde am gebundenen Head geprüft
"""
        self.pr = PR(1, 7, "PR", "http://scm/pr/7")
        self.create_pr_calls = 0
        self.created_pr_body = ""
        self.manual_receipt_head = head
        self.manual_receipt_present = True
        self.manual_receipt_contract = ""
        self.manual_receipt_ac = ""
        self.manual_receipt_actor = "alice"
        self.manual_receipt_created_at = "2026-09-24T10:02:00Z"
        self.labels = {"status:approved", "status:wip"}

    def get_comments(self, number: int) -> list[Comment]:
        contract = parse_acceptance_contract(self.plan)
        manual_id = next(item.criterion_id for item in contract.criteria if item.mode == "manual")
        comments = [
            Comment(self.PLAN_ID, self.plan, "samuel", "2026-09-24T10:00:00Z"),
            *self.posted_comments,
        ]
        if self.manual_receipt_present:
            comments.append(
                Comment(
                    73,
                    f"/samuel accept {self.manual_receipt_ac or manual_id} "
                    f"--contract {self.manual_receipt_contract or contract.contract_hash} "
                    f"--head {self.manual_receipt_head}",
                    self.manual_receipt_actor,
                    self.manual_receipt_created_at,
                )
            )
        return comments

    def get_issue(self, number: int) -> Issue:
        return Issue(
            number,
            "Test",
            "body",
            "open",
            [Label(index, name) for index, name in enumerate(sorted(self.labels), 1)],
        )

    def swap_label(self, number: int, remove: str, add: str) -> None:
        assert number == 42
        if remove:
            self.labels.discard(remove)
        if add:
            self.labels.add(add)

    def get_label_events(self, number: int, label: str) -> list[SCMLabelEvent]:
        assert number == 42
        assert label == "status:approved"
        return [
            SCMLabelEvent(
                "gitea-timeline:72",
                label,
                "alice",
                "human",
                "2026-09-24T10:01:00Z",
            )
        ]

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        self.create_pr_calls += 1
        self.created_pr_body = body
        self.pr = PR(self.pr.id, self.pr.number, title, self.pr.html_url)
        return self.pr

    def get_pr(self, pr_id: int) -> PR:
        assert pr_id == self.pr.number
        return self.pr


class _PassingReviewProvider(ILLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        prompt = str(messages[0]["content"])
        subject = re.search(r"^Subject SHA-256: (.+)$", prompt, re.MULTILINE)
        diff = re.search(r"^Diff SHA-256: (.+)$", prompt, re.MULTILINE)
        prompt_digest = re.search(r"^Prompt SHA-256: (.+)$", prompt, re.MULTILINE)
        policy = re.search(r"^Policy: (.+)$", prompt, re.MULTILINE)
        assert subject and diff and prompt_digest and policy
        return LLMResponse(
            text=json.dumps(
                {
                    "schema_version": 2,
                    "decision": "pass",
                    "subject_sha256": subject.group(1),
                    "diff_sha256": diff.group(1),
                    "policy": json.loads(policy.group(1)),
                    "tool": {"kind": "llm", "name": "review"},
                    "prompt_sha256": prompt_digest.group(1),
                    "findings": [],
                }
            ),
            input_tokens=100,
            output_tokens=50,
            stop_reason="stop",
            model_used="review-test",
        )

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    @property
    def context_window(self) -> int:
        return 100_000


def _budget_state(tmp_path: Path) -> SQLiteStateStore:
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        f"36 25 0:32 / {tmp_path} rw,relatime - ext4 device rw\n",
        encoding="utf-8",
    )
    return SQLiteStateStore(tmp_path / "state", mountinfo_path=mountinfo)


def _bind_candidate_authority(tmp_path: Path, scm: CandidateSCM) -> SQLiteStateStore:
    state = _budget_state(tmp_path)
    comments = scm.get_comments(42)
    plan, approval_comment = comments[0], comments[1]
    contract = parse_acceptance_contract(plan.body)
    key = "budget-candidate-42"
    state.authority.put_budget_admission(
        WorkflowBudgetAdmissionRecord(
            admission_key=key,
            repository=scm.repository_identity,
            issue_number=42,
            invocation_digest="sha256:invocation",
            source_digest="sha256:source",
            policy_digest="sha256:workflow-policy",
            correlation_id="planning-42",
            token_limit=100_000,
        )
    )
    state.authority.bind_budget_plan(
        key,
        plan_contract_hash=contract.contract_hash,
        plan_comment_id=plan.id,
    )
    persist_plan_approval(
        state.authority,
        repository=scm.repository_identity,
        issue_number=42,
        contract=contract,
        approval=AcceptanceApproval(
            state="approved",
            actor=approval_comment.user,
            method="comment",
            source_id=f"plan:{plan.id};comment:{approval_comment.id}",
            approved_at=approval_comment.created_at,
            contract_hash=contract.contract_hash,
            plan_comment_id=plan.id,
        ),
        transport="signed_webhook",
    )
    return state


def _bind_admission(
    state: SQLiteStateStore,
    scm: _ManualCandidateSCM,
    *,
    key: str = "budget-manual-42",
) -> str:
    contract = parse_acceptance_contract(scm.plan)
    state.authority.put_budget_admission(
        WorkflowBudgetAdmissionRecord(
            admission_key=key,
            repository=scm.repository_identity,
            issue_number=42,
            invocation_digest="sha256:invocation",
            source_digest="sha256:source",
            policy_digest="sha256:workflow-policy",
            correlation_id="planning-42",
            token_limit=100_000,
        )
    )
    state.authority.bind_budget_plan(
        key,
        plan_contract_hash=contract.contract_hash,
        plan_comment_id=scm.PLAN_ID,
    )
    persist_plan_approval(
        state.authority,
        repository=scm.repository_identity,
        issue_number=42,
        contract=contract,
        approval=AcceptanceApproval(
            state="approved",
            actor="alice",
            method="status:approved/polling",
            source_id=f"plan:{scm.PLAN_ID};gitea-timeline:72",
            approved_at="2026-09-24T10:01:00Z",
            contract_hash=contract.contract_hash,
            plan_comment_id=scm.PLAN_ID,
        ),
        transport="authenticated_scm_polling",
    )
    return key


def _manual_review_runtime(
    tmp_path: Path,
    repository: Path,
    scm: _ManualCandidateSCM,
    state: SQLiteStateStore,
) -> tuple[Bus, PRGatesHandler, _PassingReviewProvider, list[Event]]:
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "gates.json").write_text(
        '{"policy_version":"test.v1","required":[11],"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    bus = Bus()
    events: list[Event] = []
    bus.subscribe("*", events.append)
    LabelsHandler(bus, scm=scm).register()
    bus.register_command("VerifyAC", ACVerificationHandler(bus, repository).handle)
    raw = _PassingReviewProvider()
    llm = LogicalCallLLMAdapter(
        TokenBudgetLLMAdapter(
            WorkflowTokenBudgetLLMAdapter(
                raw,
                authority_store=state.authority,
                provider="test-provider",
                model="review-test",
                bus=bus,
            ),
            provider="test-provider",
            model="review-test",
            content_max_tokens=512,
            temperature=0,
        )
    )
    bus.register_command(
        "Review",
        ReviewHandler(bus, scm=scm, llm=llm, authority_store=state.authority).handle,
    )
    WorkflowEngine(bus, {"steps": [{"on": "PRCreated", "send": "Review"}]})
    handler = PRGatesHandler(
        bus,
        scm=scm,
        config_dir=config_dir,
        project_root=repository,
        authority_store=state.authority,
        review_required=True,
    )
    return bus, handler, raw, events


def _candidate_repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    (repository / "candidate.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = _commit(repository, "base")
    (repository / "candidate.py").write_text("VALUE = 2\n", encoding="utf-8")
    head = _commit(repository, "candidate")
    return repository, base, head


def _bind_manual_checkpoint(
    state: SQLiteStateStore,
    handler: PRGatesHandler,
    scm: _ManualCandidateSCM,
) -> EvaluationSubject:
    contract = parse_acceptance_contract(scm.plan)
    subject, _ = handler._resolve_subject(
        CreatePRCommand(issue_number=42, branch="feature/candidate"), contract
    )
    correlation_id = "manual-pending-42"
    state.authority.put_checkpoint(
        WorkflowCheckpointRecord(
            checkpoint_key=handler._checkpoint_key(correlation_id, 42),
            issue_number=42,
            correlation_id=correlation_id,
            workflow="implementation_finalization",
            boundary="gates_pending",
            repository=subject.repository,
            branch="feature/candidate",
            base_ref="main",
            head_sha=subject.head_sha,
            workspace_id="workspace-42",
            evaluation_subject={},
            resume_eligible=True,
            payload={"event_payload": {"evaluation_subject": subject.as_dict()}},
            updated_at=datetime.fromisoformat("2026-09-24T10:01:30+00:00"),
        )
    )
    return subject


def test_manual_pending_waits_then_public_watch_reevaluates_after_restart(tmp_path: Path) -> None:
    repository, _base, _head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(_base, _head)
    scm.manual_receipt_present = False
    state = _budget_state(tmp_path)
    admission_key = _bind_admission(state, scm)
    bus, handler, _raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    BoundHealingCoordinator(bus, llm=None, config=None, authority_store=state.authority).register()
    subject = _bind_manual_checkpoint(state, handler, scm)

    pending = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            subject=subject,
            payload={"workspace_id": "workspace-42"},
            correlation_id="manual-pending-42",
        )
    )
    assert pending["manual_pending"] is True
    instruction = next(c.body for c in scm.posted_comments if "## MANUAL-Acceptance" in c.body)
    manual_id = next(
        c.criterion_id for c in parse_acceptance_contract(scm.plan).criteria if c.mode == "manual"
    )
    assert (
        f"/samuel accept {manual_id} --contract {subject.contract_hash} --head {subject.head_sha}"
        in instruction
    )
    assert "bestätigen diese Kriterien nicht" in instruction
    assert scm.create_pr_calls == 0
    assert "status:failed" not in scm.labels
    assert not {"GateFailed", "WorkflowBlocked"}.intersection(event.name for event in events)
    assert any(
        event.name == "HealingClassified" and event.payload["classification"] == "waiting"
        for event in events
    )
    waiting = state.authority.get_checkpoint(handler._checkpoint_key("manual-pending-42", 42))
    assert waiting is not None and waiting.boundary == "manual_pending"
    assert waiting.head_sha == subject.head_sha
    assert waiting.payload["event_payload"]["evaluation_subject"] == subject.as_dict()

    # The public ScanIssues command is the same path used by `samuel watch`.
    # Reopen durable authority first: a process restart must retain the wait.
    state = _budget_state(tmp_path)
    bus, handler, raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    bus.register_command("CreatePR", handler.handle)
    watch = WatchHandler(bus, scm=scm, authority_store=state.authority)
    bus.register_command("ScanIssues", watch.handle)
    before = bus.send(ScanIssuesCommand(payload={}))
    assert before["manual_reevaluated"] == 0
    assert scm.create_pr_calls == 0
    resumed_checkpoint = state.authority.get_checkpoint(waiting.checkpoint_key)
    assert resumed_checkpoint is not None
    assert resumed_checkpoint.boundary == "manual_pending"
    assert sum("## MANUAL-Acceptance" in c.body for c in scm.posted_comments) == 1

    scm.manual_receipt_present = True
    after = bus.send(ScanIssuesCommand(payload={}))
    assert after["manual_reevaluated"] == 1
    assert scm.create_pr_calls == 1
    assert raw.calls == 1
    assert any(event.name == "PRCreated" for event in events)
    assert any(event.name == "ReviewCompleted" for event in events)
    assert "status:failed" not in scm.labels
    pr_checkpoint = state.authority.get_checkpoint(waiting.checkpoint_key)
    assert pr_checkpoint is not None
    assert pr_checkpoint.boundary == "pr_pending"
    admission = state.authority.find_budget_admission(
        repository=subject.repository,
        issue_number=42,
        plan_contract_hash=subject.contract_hash,
        plan_comment_id=scm.PLAN_ID,
    )
    assert admission is not None
    assert admission.admission_key == admission_key


@pytest.mark.parametrize("invalid", ["ac", "contract", "head", "actor", "stale"])
def test_public_watch_rejects_unbound_manual_receipt(tmp_path: Path, invalid: str) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    scm.manual_receipt_present = False
    state = _budget_state(tmp_path)
    _bind_admission(state, scm)
    bus, handler, _raw, _events = _manual_review_runtime(tmp_path, repository, scm, state)
    _bind_manual_checkpoint(state, handler, scm)
    pending = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42"},
            correlation_id="manual-pending-42",
        )
    )
    assert pending["manual_pending"] is True
    scm.manual_receipt_present = True
    if invalid == "ac":
        scm.manual_receipt_ac = "AC-" + "f" * 16
    elif invalid == "contract":
        scm.manual_receipt_contract = "sha256:" + "f" * 64
    elif invalid == "head":
        scm.manual_receipt_head = "f" * 40
    elif invalid == "actor":
        scm.manual_receipt_actor = "samuel"
    else:
        scm.manual_receipt_created_at = "2026-09-24T10:01:00Z"

    bus, handler, raw, events = _manual_review_runtime(
        tmp_path, repository, scm, _budget_state(tmp_path)
    )
    bus.register_command("CreatePR", handler.handle)
    bus.register_command(
        "ScanIssues", WatchHandler(bus, scm=scm, authority_store=state.authority).handle
    )
    result = bus.send(ScanIssuesCommand(payload={}))

    assert result["manual_reevaluated"] == 0
    assert scm.create_pr_calls == 0
    assert raw.calls == 0
    assert "status:failed" not in scm.labels
    assert not any(event.name == "PRCreated" for event in events)


def test_real_acceptance_failure_is_not_masked_by_manual_pending(tmp_path: Path) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    scm.plan = scm.plan.replace("[DIFF] candidate.py", "[DIFF] missing.py")
    scm.manual_receipt_present = False
    state = _budget_state(tmp_path)
    _bind_admission(state, scm)
    _bus, handler, _raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    BoundHealingCoordinator(_bus, llm=None, config=None, authority_store=state.authority).register()
    _bind_manual_checkpoint(state, handler, scm)

    result = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42"},
            correlation_id="manual-pending-42",
        )
    )

    assert result["passed"] is False
    assert result["manual_pending"] is False
    assert any(event.name == "GateFailed" for event in events)
    assert any(event.name == "WorkflowBlocked" for event in events)
    assert "status:failed" in scm.labels


def test_manual_reevaluation_recovers_same_budget_admission_through_review(
    tmp_path: Path,
) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    state = _budget_state(tmp_path)
    admission_key = _bind_admission(state, scm)
    prior = LLMBudgetAttemptRecord(
        attempt_key="planning-attempt",
        admission_key=admission_key,
        logical_call_id="planning-call",
        provider="test-provider",
        model="planning-test",
        task="planning",
        input_upper_bound=100,
        output_upper_bound=100,
        reserved_tokens=200,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    state.authority.reserve_budget_attempt(prior)
    state.authority.settle_budget_attempt(
        prior.attempt_key,
        status="settled",
        actual_input_tokens=20,
        actual_output_tokens=10,
        outcome_code="usage_reported",
    )
    scm.manual_receipt_present = False
    _pending_bus, pending_handler, pending_raw, _pending_events = _manual_review_runtime(
        tmp_path,
        repository,
        scm,
        state,
    )
    pending = pending_handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42"},
            correlation_id="manual-pending-42",
        )
    )
    assert pending["passed"] is False
    assert any(
        row["status"] == "manual_pending" for row in pending["acceptance_evidence"]["results"]
    )
    assert pending_raw.calls == 0
    assert scm.create_pr_calls == 0
    assert scm.labels == {"status:failed"}

    scm.manual_receipt_present = True
    # Restart between manual_pending and reevaluation: both the workflow-budget
    # binding and the exact plan approval must be reconstructed from SQLite.
    state = _budget_state(tmp_path)
    _bus, handler, raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    command = CreatePRCommand(
        issue_number=42,
        branch="feature/candidate",
        payload={"workspace_id": "workspace-42", "manual_reevaluation": True},
        correlation_id="manual-continuation-42",
    )

    first = handler.handle(command)

    assert first["passed"] is True
    assert raw.calls == 1
    assert (
        next(event for event in events if event.name == "PRCreated").payload["budget_admission_key"]
        == admission_key
    )
    assert any(
        event.name == "ReviewCompleted" and event.payload["decision"] == "pass" for event in events
    )
    assert len(state.authority.list_budget_admissions()) == 1
    attempts = state.authority.list_budget_attempts(admission_key=admission_key)
    assert [attempt.task for attempt in attempts] == ["planning", "review"]
    assert (attempts[0].actual_input_tokens, attempts[0].actual_output_tokens) == (20, 10)

    second = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42", "manual_reevaluation": True},
            correlation_id="manual-continuation-42",
        )
    )

    assert second["passed"] is True
    assert scm.create_pr_calls == 1
    assert len(state.authority.list_budget_admissions()) == 1
    replay_attempts = state.authority.list_budget_attempts(admission_key=admission_key)
    assert [attempt.task for attempt in replay_attempts] == ["planning", "review", "review"]
    assert (replay_attempts[0].actual_input_tokens, replay_attempts[0].actual_output_tokens) == (
        20,
        10,
    )


def test_manual_reevaluation_without_exact_admission_blocks_before_pr_and_review(
    tmp_path: Path,
) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    state = _budget_state(tmp_path)
    _bus, handler, raw, _events = _manual_review_runtime(tmp_path, repository, scm, state)

    result = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"manual_reevaluation": True},
            correlation_id="manual-continuation-42",
        )
    )

    assert result["passed"] is False
    assert result["subject_error"]["code"] == "workflow_budget_admission_missing"
    assert scm.create_pr_calls == 0
    assert raw.calls == 0


def test_manual_reevaluation_rejects_receipt_for_another_candidate(tmp_path: Path) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    state = _budget_state(tmp_path)
    _bind_admission(state, scm)
    scm.head = "c" * 40
    _bus, handler, raw, _events = _manual_review_runtime(tmp_path, repository, scm, state)

    result = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"manual_reevaluation": True},
            correlation_id="manual-continuation-wrong-candidate-42",
        )
    )

    assert result["passed"] is False
    assert any(
        row["status"] == "manual_pending" for row in result["acceptance_evidence"]["results"]
    )
    assert scm.create_pr_calls == 0
    assert raw.calls == 0


def test_manual_reevaluation_rejects_foreign_admission_and_replanned_contract(
    tmp_path: Path,
) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    state = _budget_state(tmp_path)
    _bind_admission(state, scm)
    _bus, handler, raw, _events = _manual_review_runtime(tmp_path, repository, scm, state)

    foreign = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={
                "manual_reevaluation": True,
                "budget_admission_key": "budget-from-another-plan",
            },
            correlation_id="manual-continuation-42",
        )
    )
    assert foreign["subject_error"]["code"] == "workflow_budget_admission_mismatch"

    scm.plan = scm.plan.replace(
        "Candidate wurde am gebundenen Head geprüft",
        "Candidate wurde nach Replan erneut geprüft",
    )
    replanned = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"manual_reevaluation": True},
            correlation_id="manual-continuation-replan-42",
        )
    )
    assert replanned["subject_error"]["code"] == "workflow_budget_admission_missing"
    assert scm.create_pr_calls == 0
    assert raw.calls == 0


@pytest.mark.parametrize(
    "receipt", ["valid", "wrong_head", "wrong_actor", "stale", "other_issue", "bad_signature"]
)
def test_signed_manual_comment_continues_only_its_bound_wait(tmp_path: Path, receipt: str) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    scm.manual_receipt_present = False
    state = _budget_state(tmp_path)
    _bind_admission(state, scm)
    bus, handler, raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    _bind_manual_checkpoint(state, handler, scm)
    handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42"},
            correlation_id="manual-pending-42",
        )
    )
    # Restore the same durable wait before ingress, without a ScanIssues command.
    state = _budget_state(tmp_path)
    bus, handler, raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    bus.register_command("CreatePR", handler.handle)
    WatchHandler(bus, scm=scm, authority_store=state.authority)
    scm.manual_receipt_present = True
    if receipt == "wrong_head":
        scm.manual_receipt_head = "f" * 40
    elif receipt == "wrong_actor":
        scm.manual_receipt_actor = "samuel"
    elif receipt == "stale":
        scm.manual_receipt_created_at = "2026-09-24T10:01:00Z"
    payload = {
        "action": "created",
        "issue": {"number": 99 if receipt == "other_issue" else 42, "labels": []},
        "comment": {
            "id": 73,
            "body": scm.get_comments(42)[-1].body,
            "created_at": scm.manual_receipt_created_at,
        },
        "sender": {"login": "alice"},
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(b"test-hook", body, hashlib.sha256).hexdigest()
    ingress = WebhookIngressAdapter(bus, secret="test-hook", bot_user="samuel")
    result = ingress.handle_webhook(
        "issue_comment",
        payload,
        signature="0" * 64 if receipt == "bad_signature" else signature,
        raw_body=body,
        provider="gitea",
    )
    if receipt != "valid":
        assert scm.create_pr_calls == 0
        assert raw.calls == 0
        assert not any(e.name == "PRCreated" for e in events)
        return
    assert result["status"] == 202
    assert scm.create_pr_calls == raw.calls == 1
    assert any(e.name == "ReviewCompleted" for e in events)
    assert not any(e.name == "ScanIssues" for e in events)
    ingress.handle_webhook(
        "issue_comment", payload, signature=signature, raw_body=body, provider="gitea"
    )
    assert scm.create_pr_calls == raw.calls == 1


@pytest.mark.parametrize("second_receipt", ["valid", "head", "contract", "actor", "stale", "ac"])
def test_native_manual_receipts_accept_only_each_bound_criterion(
    tmp_path: Path, second_receipt: str
) -> None:
    class MultipleManualSCM(_ManualCandidateSCM):
        second_comment: Comment | None = None

        def get_comments(self, number: int) -> list[Comment]:
            comments = super().get_comments(number)
            if self.second_comment is not None:
                comments.append(self.second_comment)
            return comments

    repository, base, head = _candidate_repository(tmp_path)
    scm = MultipleManualSCM(base, head)
    scm.plan += "- [ ] [MANUAL] Zweite unabhängige fachliche Prüfung\n"
    scm.manual_receipt_present = False
    state = _budget_state(tmp_path)
    admission_key = _bind_admission(state, scm)
    bus, handler, raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    bus.register_command("CreatePR", handler.handle)
    WatchHandler(bus, scm=scm, authority_store=state.authority)
    subject = _bind_manual_checkpoint(state, handler, scm)
    pending = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            subject=subject,
            payload={"workspace_id": "workspace-42"},
            correlation_id="manual-pending-42",
        )
    )
    assert pending["manual_pending"] is True
    contract = parse_acceptance_contract(scm.plan)
    criteria = [criterion for criterion in contract.criteria if criterion.mode == "manual"]
    instruction = next(c.body for c in scm.posted_comments if "## MANUAL-Acceptance" in c.body)
    for criterion in criteria:
        assert (
            f"/samuel accept {criterion.criterion_id} "
            f"--contract {subject.contract_hash} --head {head}"
        ) in instruction

    ingress = WebhookIngressAdapter(bus, secret="test-hook", bot_user="samuel")

    def deliver(comment: Comment) -> None:
        payload = {
            "action": "created",
            "issue": {"number": 42, "labels": []},
            "comment": {
                "id": comment.id,
                "body": comment.body,
                "created_at": comment.created_at,
            },
            "sender": {"login": comment.user},
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"test-hook", body, hashlib.sha256).hexdigest()
        ingress.handle_webhook(
            "issue_comment", payload, signature=signature, raw_body=body, provider="gitea"
        )

    scm.manual_receipt_present = True
    first = scm.get_comments(42)[-1]
    deliver(first)
    assert scm.create_pr_calls == raw.calls == 0
    checkpoint = state.authority.get_checkpoint(handler._checkpoint_key("manual-pending-42", 42))
    assert checkpoint is not None and checkpoint.boundary == "manual_pending"
    assert not any(event.name == "PRCreated" for event in events)
    comments_before_replay = len(scm.posted_comments)
    deliver(first)
    assert scm.create_pr_calls == raw.calls == 0
    assert len(scm.posted_comments) == comments_before_replay

    criterion_id = criteria[1].criterion_id
    receipt_contract = subject.contract_hash
    receipt_head = head
    actor = "alice"
    created_at = "2026-09-24T10:03:00Z"
    if second_receipt == "head":
        receipt_head = "f" * 40
    elif second_receipt == "contract":
        receipt_contract = "sha256:" + "f" * 64
    elif second_receipt == "actor":
        actor = "samuel"
    elif second_receipt == "stale":
        created_at = "2026-09-24T10:01:00Z"
    elif second_receipt == "ac":
        criterion_id = criteria[0].criterion_id
    scm.second_comment = Comment(
        74,
        f"/samuel accept {criterion_id} --contract {receipt_contract} --head {receipt_head}",
        actor,
        created_at,
    )
    deliver(scm.second_comment)
    if second_receipt != "valid":
        assert scm.create_pr_calls == raw.calls == 0
        assert not any(event.name == "PRCreated" for event in events)
        return

    assert scm.create_pr_calls == raw.calls == 1
    assert any(event.name == "ReviewCompleted" for event in events)
    deliver(scm.second_comment)
    assert scm.create_pr_calls == raw.calls == 1
    assert not any(event.name == "ScanIssues" for event in events)
    admission = state.authority.find_budget_admission(
        repository=subject.repository,
        issue_number=42,
        plan_contract_hash=subject.contract_hash,
        plan_comment_id=scm.PLAN_ID,
    )
    assert admission is not None and admission.admission_key == admission_key


@pytest.mark.parametrize(
    "condition", ["merged", "wrong_head", "unmerged", "unknown_pr", "unreadable"]
)
def test_native_human_merge_projects_exact_candidate_without_merging(
    tmp_path: Path, condition: str
) -> None:
    from dataclasses import replace

    from samuel.slices.dashboard.data import get_workflow_issue_detail
    from samuel.slices.run_projection.handler import RunProjectionHandler

    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    state = _budget_state(tmp_path)
    _bind_admission(state, scm)
    bus, handler, raw, events = _manual_review_runtime(tmp_path, repository, scm, state)
    _bind_manual_checkpoint(state, handler, scm)
    RunProjectionHandler(bus, state.projections).register()
    result = handler.handle(
        CreatePRCommand(
            issue_number=42,
            branch="feature/candidate",
            payload={"workspace_id": "workspace-42"},
            correlation_id="manual-pending-42",
        )
    )
    assert result["pr_created"] is True
    # Runtime cleanup removes the resumable checkpoint after review. The
    # applied PR intent must retain the binding across cleanup and restart.
    state.authority.clear_checkpoint(handler._checkpoint_key("manual-pending-42", 42))
    state = _budget_state(tmp_path)
    from samuel.core.bus import IdempotencyMiddleware

    bus.add_middleware(IdempotencyMiddleware())
    review = ReviewHandler(bus, scm=scm, authority_store=state.authority)
    bus.subscribe("PullRequestMerged", review.observe_merge)
    scm.pr = replace(scm.pr, state="closed", merged=condition != "unmerged")
    # SCM base moves on merge; the original candidate binding must survive.
    original_revision = scm.get_pr_revision(scm.pr.number)
    scm.get_pr_revision = lambda pr_id: PullRequestRevision(
        repository=original_revision.repository,
        base_sha="e" * 40,
        head_sha="f" * 40 if condition == "wrong_head" else original_revision.head_sha,
    )
    if condition == "unreadable":

        def unavailable(pr_id: int) -> PR:
            raise OSError("unavailable")

        scm.get_pr = unavailable
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 99 if condition == "unknown_pr" else scm.pr.number,
            "merged": True,
            "merged_at": "2026-10-02T17:21:42Z",
        },
        "sender": {"login": "maintainer"},
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(b"test-hook", body, hashlib.sha256).hexdigest()
    WebhookIngressAdapter(bus, secret="test-hook").handle_webhook(
        "pull_request", payload, signature=signature, raw_body=body, provider="gitea"
    )
    merges = [e for e in events if e.name == "PRMerged"]
    assert len(merges) == (1 if condition == "merged" else 0)
    summaries = [c.body for c in scm.posted_comments if "## Entwicklungsabschluss" in c.body]
    assert len(summaries) == (1 if condition == "merged" else 0)
    assert "## Fachliche Änderung" in scm.created_pr_body
    assert "+VALUE = 2" in scm.created_pr_body and "-VALUE = 1" in scm.created_pr_body
    assert "## S.A.M.U.E.L. Gate-Entscheidung" in scm.created_pr_body
    changes = [c.body for c in scm.posted_comments if "## Fachliche Änderung" in c.body]
    assert len(changes) == (1 if condition == "merged" else 0)
    assert scm.closed_issues == []
    assert raw.calls == 1
    if merges:
        assert merges[0].correlation_id == "manual-pending-42"
        assert merges[0].payload["issue"] == 42
        assert merges[0].payload["evaluation_subject"]["head_sha"] == head
        detail = get_workflow_issue_detail(
            42, str(state.data_dir), projection_store=state.projections
        )
        assert detail is not None and detail["status"] == "merged"
        WebhookIngressAdapter(bus, secret="test-hook").handle_webhook(
            "pull_request", payload, signature=signature, raw_body=body, provider="gitea"
        )
        assert sum(e.name == "PRMerged" for e in events) == 1
        assert sum("## Entwicklungsabschluss" in c.body for c in scm.posted_comments) == 1
        assert sum("## Fachliche Änderung" in c.body for c in scm.posted_comments) == 1
        assert "+VALUE = 2" in changes[0] and "-VALUE = 1" in changes[0]
        assert head in changes[0]
        assert "Gate-Entscheidung" not in changes[0]
        assert head in summaries[0]
        assert "nicht automatisch" in summaries[0]


def test_change_comment_preserves_existing_technical_comment_and_redacts_source(
    tmp_path: Path,
) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    contract = parse_acceptance_contract(scm.plan)
    subject = EvaluationSubject(
        repository=scm.repository_identity,
        base_sha=base,
        head_sha=head,
        contract_hash=contract.contract_hash,
        policy_version="test",
        policy_digest="sha256:" + "d" * 64,
    )
    handler = ReviewHandler(Bus(), scm=scm)
    handler._post_merge_summary(42, 7, subject)
    technical = scm.posted_comments[0].body
    secret = "sk-" + "x" * 32
    scm.get_issue = lambda number: Issue(
        number, "Highest score first", "Descending score order.", "open"
    )
    scm.compare_commits = lambda base_sha, head_sha, *, max_diff_bytes: RevisionComparison(
        scm.repository_identity,
        base_sha,
        head_sha,
        ("candidate.py",),
        "+token = '" + secret + "'\n" + "+VALUE = 2\n" * 100,
        len(("+token = '" + secret + "'\n" + "+VALUE = 2\n" * 100).encode()),
    )
    handler._post_change_summary(42, 7, subject)
    handler._post_change_summary(42, 7, subject)
    assert scm.posted_comments[0].body == technical
    assert len(scm.posted_comments) == 2
    change = scm.posted_comments[1].body
    assert "Highest score first" in change
    assert "Descending score order" in change
    assert secret not in change
    assert change.count("+VALUE = 2") <= 59
    assert scm.closed_issues == []


@pytest.mark.parametrize("condition", ["stale_plan", "wrong_comparison", "readback_failure"])
def test_change_comment_does_not_guess_when_subject_comparison_is_unavailable(
    tmp_path: Path,
    condition: str,
) -> None:
    repository, base, head = _candidate_repository(tmp_path)
    scm = _ManualCandidateSCM(base, head)
    contract = parse_acceptance_contract(scm.plan)
    subject = EvaluationSubject(
        repository=scm.repository_identity,
        base_sha=base,
        head_sha=head,
        contract_hash=contract.contract_hash,
        policy_version="test",
        policy_digest="sha256:" + "d" * 64,
    )
    handler = ReviewHandler(Bus(), scm=scm)
    if condition == "stale_plan":
        scm.plan += "\n- [ ] [MANUAL] Different scope"
    elif condition == "wrong_comparison":
        original = scm.compare_commits
        scm.compare_commits = lambda base_sha, head_sha, *, max_diff_bytes: original(
            base_sha, "f" * 40, max_diff_bytes=max_diff_bytes
        )
    else:

        def unavailable(base_sha: str, head_sha: str, *, max_diff_bytes: int) -> RevisionComparison:
            raise OSError("private provider body")

        scm.compare_commits = unavailable
    handler._post_change_summary(42, 7, subject)
    assert scm.posted_comments == []
    assert scm.closed_issues == []
