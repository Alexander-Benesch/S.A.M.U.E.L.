from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from samuel.core.acceptance import (
    AcceptanceApproval,
    PlanningSourceSnapshot,
    issue_revision_digest,
    latest_active_plan,
    parse_acceptance_contract,
    persist_plan_approval,
    render_planning_source,
)
from samuel.core.bus import Bus
from samuel.core.commands import (
    CreatePRCommand,
    RequestCandidateVerificationCommand,
    SubmitCandidateCommand,
)
from samuel.core.config import EvalSchema
from samuel.core.errors import SCMRevisionError, SubjectTooLargeError
from samuel.core.evaluation_observation import EvaluationObservationIdentity, canonical_digest
from samuel.core.evaluation_subject import (
    EvaluationSubject,
    PullRequestRevision,
    RevisionComparison,
)
from samuel.core.events import Event
from samuel.core.ports import IExternalGate, IVersionControl
from samuel.core.state import (
    AuthorityRecord,
    AuthorityWriteResult,
    ObservationRecord,
    OperationIntentRecord,
    WorkflowBudgetAdmissionRecord,
    WorkflowCheckpointRecord,
)
from samuel.core.types import (
    PR,
    Comment,
    GateContext,
    GateResult,
    Issue,
    Label,
    ProviderCriterionEvidence,
    ProviderEvidence,
    ProviderRunReference,
    SCMLabelEvent,
    VerificationProgress,
    VerificationRequest,
)
from samuel.slices.pr_gates.handler import PRGatesHandler


class MockSCM(IVersionControl):
    BASE_SHA = "a" * 40
    HEAD_SHA = "b" * 40

    def __init__(
        self,
        plan_comment: str = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] h.py",
        *,
        changed_files: tuple[str, ...] = (),
        diff: str = "",
    ):
        self._plan = plan_comment
        self.changed_files = changed_files
        self.diff = diff
        self._last_base_sha = self.BASE_SHA
        self._last_head_sha = self.HEAD_SHA
        self.last_file_read: tuple[str, str, int] | None = None
        self.file_contents = {path: "pass\n" for path in changed_files if path.endswith(".py")}

    @property
    def repository_identity(self) -> str:
        return "owner/repo"

    def resolve_ref(self, ref: str) -> str:
        return self.BASE_SHA if ref == "main" else self.HEAD_SHA

    def compare_commits(
        self, base_sha: str, head_sha: str, *, max_diff_bytes: int
    ) -> RevisionComparison:
        self._last_base_sha = base_sha
        self._last_head_sha = head_sha
        return RevisionComparison(
            repository=self.repository_identity,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_files=self.changed_files,
            diff=self.diff,
            diff_bytes=len(self.diff.encode()),
        )

    def read_file_at_revision(self, head_sha: str, path: str, *, max_file_bytes: int) -> str | None:
        assert head_sha == self.HEAD_SHA
        self.last_file_read = (head_sha, path, max_file_bytes)
        return self.file_contents.get(path)

    def get_pr_revision(self, pr_id: int) -> PullRequestRevision:
        return PullRequestRevision(
            repository=self.repository_identity,
            base_sha=self._last_base_sha,
            head_sha=self._last_head_sha,
        )

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="Test", body="body", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return [Comment(id=1, body=self._plan, user="bot")]

    def post_comment(self, number: int, body: str) -> Comment:
        return Comment(id=2, body=body, user="bot")

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        return PR(id=1, number=99, title=title, html_url="http://gitea/pr/99")

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        return True

    def issue_url(self, number: int) -> str:
        return ""

    def pr_url(self, pr_id: int) -> str:
        return ""

    def branch_url(self, branch: str) -> str:
        return ""

    def list_labels(self) -> list[dict]:
        return []

    def create_label(self, name: str, color: str, description: str = "") -> dict:
        return {"id": 0, "name": name, "color": color, "description": description}


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class _DurableAuthority:
    def __init__(self) -> None:
        self.epoch = 0
        self.records: dict[str, AuthorityRecord] = {}
        self.admissions: dict[str, WorkflowBudgetAdmissionRecord] = {}
        self.intents: dict[str, OperationIntentRecord] = {}
        self.checkpoints: dict[str, WorkflowCheckpointRecord] = {}

    def _written(self, created: bool = True) -> AuthorityWriteResult:
        self.epoch += int(created)
        return AuthorityWriteResult(created, self.epoch)

    def put_authority_record(self, record: AuthorityRecord) -> bool:
        current = self.records.get(record.record_key)
        if current is not None and current != record:
            raise AssertionError("authority record conflict")
        self.records.setdefault(record.record_key, record)
        return current is None

    def get_authority_record(self, key: str) -> AuthorityRecord | None:
        return self.records.get(key)

    def put_budget_admission(self, record: WorkflowBudgetAdmissionRecord) -> AuthorityWriteResult:
        created = record.admission_key not in self.admissions
        self.admissions.setdefault(record.admission_key, record)
        return self._written(created)

    def bind_budget_plan(
        self, admission_key: str, *, plan_contract_hash: str, plan_comment_id: int
    ) -> AuthorityWriteResult:
        current = self.admissions[admission_key]
        updated = replace(
            current,
            plan_contract_hash=plan_contract_hash,
            plan_comment_id=plan_comment_id,
        )
        created = updated != current
        self.admissions[admission_key] = updated
        return self._written(created)

    def find_budget_admission(self, **kwargs: Any) -> WorkflowBudgetAdmissionRecord | None:
        return next(
            (
                row
                for row in self.admissions.values()
                if row.repository == kwargs["repository"]
                and row.issue_number == kwargs["issue_number"]
                and row.plan_contract_hash == kwargs["plan_contract_hash"]
                and row.plan_comment_id == kwargs["plan_comment_id"]
            ),
            None,
        )

    def get_intent(self, key: str) -> OperationIntentRecord | None:
        return self.intents.get(key)

    def put_intent(self, record: OperationIntentRecord) -> AuthorityWriteResult:
        created = record.intent_key not in self.intents
        self.intents.setdefault(record.intent_key, record)
        return self._written(created)

    def finish_intent(
        self, key: str, *, status: str, postcondition: dict[str, Any]
    ) -> AuthorityWriteResult:
        self.intents[key] = replace(self.intents[key], status=status, postcondition=postcondition)  # type: ignore[arg-type]
        return self._written()

    def get_checkpoint(self, key: str) -> WorkflowCheckpointRecord | None:
        return self.checkpoints.get(key)

    def put_checkpoint(self, record: WorkflowCheckpointRecord) -> AuthorityWriteResult:
        created = record.checkpoint_key not in self.checkpoints
        self.checkpoints[record.checkpoint_key] = record
        return self._written(created)

    def authority_status(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "instance": "33333333-3333-4333-8333-333333333333",
            "reconcile_required": False,
        }


def _durable_authority(tmp_path: Path, scm: IVersionControl, issue_number: int) -> Any:
    del tmp_path
    authority = _DurableAuthority()
    plan, approval_comment = scm.get_comments(issue_number)[:2]
    contract = parse_acceptance_contract(plan.body)
    admission_key = f"budget-{issue_number}"
    authority.put_budget_admission(
        WorkflowBudgetAdmissionRecord(
            admission_key=admission_key,
            repository=scm.repository_identity,
            issue_number=issue_number,
            invocation_digest="sha256:invocation",
            source_digest="sha256:source",
            policy_digest="sha256:policy",
            correlation_id=f"planning-{issue_number}",
            token_limit=100_000,
        )
    )
    authority.bind_budget_plan(
        admission_key,
        plan_contract_hash=contract.contract_hash,
        plan_comment_id=plan.id,
    )
    persist_plan_approval(
        authority,  # type: ignore[arg-type]
        repository=scm.repository_identity,
        issue_number=issue_number,
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
    return authority


class _VerificationSpy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, cmd: Any) -> dict[str, Any]:
        self.calls += 1
        contract = cmd.payload["acceptance_contract"]
        criteria = contract["criteria"]
        return {
            "acceptance_evidence": {
                "schema_version": 1,
                "evaluation_subject": cmd.subject.as_dict(),
                "contract": contract,
                "results": [
                    {
                        "criterion_id": criterion["criterion_id"],
                        "tag": criterion["tag"],
                        "status": "passed",
                        "reason": "verified",
                        "evidence": {
                            "schema_version": 1,
                            "kind": "diff",
                            "path": criterion["text"],
                            "changed": True,
                        },
                    }
                    for criterion in criteria
                ],
            }
        }


class _AuthoritySpy:
    def __init__(self, timeline: list[str]) -> None:
        self.timeline = timeline
        self.epoch = 0
        self.intent: OperationIntentRecord | None = None

    def put_intent(self, record: Any) -> AuthorityWriteResult:
        self.timeline.append(f"intent:{record.operation}")
        self.epoch += 1
        self.intent = record
        return AuthorityWriteResult(True, self.epoch)

    def get_intent(self, _intent_key: str) -> OperationIntentRecord | None:
        return self.intent

    def get_checkpoint(self, _checkpoint_key: str) -> None:
        return None

    def authority_status(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "instance": "33333333-3333-4333-8333-333333333333",
            "reconcile_required": False,
        }

    def find_budget_admission(self, **_kwargs: Any) -> Any:
        return SimpleNamespace(admission_key="budget-run-42")

    def finish_intent(
        self,
        _intent_key: str,
        *,
        status: str,
        postcondition: dict[str, Any],
    ) -> AuthorityWriteResult:
        self.timeline.append(f"intent_done:create_pr:{status}")
        self.epoch += 1
        assert self.intent is not None
        self.intent = replace(self.intent, status=status, postcondition=postcondition)
        return AuthorityWriteResult(True, self.epoch)


class TestPRGatesHandler:
    def test_pr_intent_precedes_effect_and_verified_postcondition_precedes_event(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )
        timeline: list[str] = []

        class OrderedSCM(MockSCM):
            def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
                timeline.append("effect:create_pr")
                return super().create_pr(head, base, title, body)

        bus = Bus()
        events = _collect_events(bus)
        bus.subscribe("PRCreated", lambda _event: timeline.append("event:PRCreated"))
        handler = PRGatesHandler(
            bus,
            scm=OrderedSCM(),
            config_dir=str(tmp_path),
            authority_store=_AuthoritySpy(timeline),  # type: ignore[arg-type]
            review_required=True,
        )

        result = handler.handle(
            CreatePRCommand(issue_number=42, branch="feature/test", correlation_id="run-42")
        )

        assert result["passed"] is True
        assert timeline == [
            "intent:create_pr",
            "effect:create_pr",
            "intent_done:create_pr:applied",
            "event:PRCreated",
        ]
        created = next(event for event in events if event.name == "PRCreated")
        assert created.payload["authority_epoch"] == 2
        assert created.payload["authority_series"] == "authority.v2"
        assert created.payload["instance_uuid"] == "33333333-3333-4333-8333-333333333333"
        assert created.payload["review_required"] is True

    def test_all_gates_pass(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [1,2,3,5,6,7,8,9,11,12,"13a","13b"], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is True
        assert any(e.name == "PRCreated" for e in events)

    def test_successful_healing_pr_preserves_origin_observation(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)
        origin = "sha256:" + "a" * 64

        result = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path)).handle(
            CreatePRCommand(
                issue_number=42,
                branch="feature/test",
                payload={"healing_origin_observation_key": origin},
                correlation_id="healing-run",
            )
        )

        created = next(event for event in events if event.name == "PRCreated")
        assert result["passed"] is True
        assert created.correlation_id == "healing-run"
        assert created.payload["healing_origin_observation_key"] == origin

    def test_required_gate_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [1], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is False
        assert any(e.name == "GateFailed" for e in events)
        assert not any(e.name == "PRCreated" for e in events)


class TestPreflightGateOrdering:
    PLAN = """## Plan
Agent-Metadaten
### Änderungsscope
Scope-Schema: 1
- [FILE] `h.py`
Architecture-Expansion: disabled
### Akzeptanzkriterien
- [ ] [DIFF] h.py
"""

    @staticmethod
    def _write_gates(tmp_path: Path, *, required: list[int | str]) -> None:
        import json

        (tmp_path / "gates.json").write_text(
            json.dumps(
                {
                    "policy_version": "preflight-test.v1",
                    "required": required,
                    "optional": [],
                    "disabled": [],
                    "custom": [],
                    "parameters": {"max_diff_bytes": 100_000},
                }
            ),
            encoding="utf-8",
        )

    def test_scope_preflight_skips_candidate_and_every_post_candidate_gate(
        self, tmp_path: Path
    ) -> None:
        self._write_gates(tmp_path, required=["7b", 11])
        bus = Bus()
        events = _collect_events(bus)
        verifier = _VerificationSpy()
        bus.register_command("VerifyAC", verifier)

        class ExternalSpy(IExternalGate):
            name = "external-spy"
            calls = 0

            def run(self, context: GateContext) -> GateResult:
                self.calls += 1
                return GateResult(gate=self.name, passed=True, reason="ok")

        external = ExternalSpy()
        result = PRGatesHandler(
            bus,
            scm=MockSCM(
                plan_comment=self.PLAN,
                changed_files=("outside.py",),
                diff="+outside",
            ),
            config_dir=tmp_path,
            external_gates=[external],
        ).handle(CreatePRCommand(issue_number=620, branch="feature/preflight"))

        assert result["passed"] is False
        assert verifier.calls == 0
        assert external.calls == 0
        evidence = {item["gate"]: item for item in result["gate_results"]}
        assert evidence["7b"]["executed"] is True
        assert evidence["7b"]["passed"] is False
        assert evidence["7b"]["authority"] == "required"
        assert evidence["7b"]["reason_code"] == "gate_7b_failed"
        assert evidence[11]["executed"] is False
        assert evidence[11]["passed"] is None
        assert evidence[11]["status"] == "skipped_precondition"
        assert evidence[11]["reason_code"] == "gate_11_skipped_precondition"
        assert evidence["external-spy"]["status"] == "skipped_precondition"
        completed = [event for event in events if event.name == "GateEvaluationCompleted"]
        assert len(completed) == 1
        assert completed[0].payload["acceptance_evidence"] is None
        assert completed[0].payload["observation_schema_version"] == 2
        assert not any(
            event.name == "GateFailed" and event.payload["gate"] == 11 for event in events
        )

    def test_syntax_preflight_never_dispatches_candidate_verification(self, tmp_path: Path) -> None:
        self._write_gates(tmp_path, required=[9, 11])
        bus = Bus()
        verifier = _VerificationSpy()
        bus.register_command("VerifyAC", verifier)
        scm = MockSCM(
            plan_comment=self.PLAN,
            changed_files=("h.py",),
            diff="+def broken(",
        )
        scm.file_contents["h.py"] = "def broken(\n"

        result = PRGatesHandler(bus, scm=scm, config_dir=tmp_path).handle(
            CreatePRCommand(issue_number=620, branch="feature/preflight")
        )

        assert result["passed"] is False
        assert verifier.calls == 0
        evidence = {item["gate"]: item for item in result["gate_results"]}
        assert evidence[9]["status"] == "failed"
        assert evidence[11]["status"] == "skipped_precondition"

    def test_unknown_freshness_is_required_preflight_failure(self, tmp_path: Path) -> None:
        self._write_gates(tmp_path, required=["13a", 11])
        bus = Bus()
        verifier = _VerificationSpy()
        bus.register_command("VerifyAC", verifier)

        result = PRGatesHandler(
            bus,
            scm=MockSCM(plan_comment=self.PLAN),
            config_dir=tmp_path,
            project_root=tmp_path,
        ).handle(CreatePRCommand(issue_number=620, branch="feature/preflight"))

        assert result["passed"] is False
        assert verifier.calls == 0
        evidence = {item["gate"]: item for item in result["gate_results"]}
        assert evidence["13a"]["passed"] is False
        assert evidence["13a"]["executed"] is True
        assert evidence["13a"]["status"] == "failed"
        assert evidence[11]["status"] == "skipped_precondition"

    def test_green_preflight_executes_gate_11_once(self, tmp_path: Path) -> None:
        self._write_gates(tmp_path, required=["7b", 8, 9, 11, "13b"])

        class ApprovedSCM(MockSCM):
            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(id=1, body=self._plan, user="bot"),
                    Comment(id=2, body="ok", user="reviewer", created_at="2026-08-29T12:00:00Z"),
                ]

        bus = Bus()
        verifier = _VerificationSpy()
        bus.register_command("VerifyAC", verifier)
        scm = ApprovedSCM(
            plan_comment=self.PLAN,
            changed_files=("h.py",),
            diff="+++ b/h.py\n+pass",
        )
        result = PRGatesHandler(
            bus,
            scm=scm,
            config_dir=tmp_path,
            authority_store=_durable_authority(tmp_path, scm, 620),
        ).handle(CreatePRCommand(issue_number=620, branch="feature/preflight"))

        assert result["passed"] is True
        assert verifier.calls == 1
        assert [item["gate"] for item in result["gate_results"]] == ["7b", 8, 9, "13b", 11]
        evidence = {item["gate"]: item for item in result["gate_results"]}
        assert all(evidence[gate]["executed"] is True for gate in ("7b", 8, 9, 11, "13b"))
        assert evidence[11]["status"] == "passed"

    def test_comment_or_status_evidence_without_durable_authority_blocks_gate_11(
        self, tmp_path: Path
    ) -> None:
        self._write_gates(tmp_path, required=[11])

        class ApprovedSCM(MockSCM):
            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(id=1, body=self._plan, user="bot"),
                    Comment(id=2, body="ok", user="reviewer", created_at="2026-08-29T12:00:00Z"),
                ]

        bus = Bus()
        bus.register_command("VerifyAC", _VerificationSpy())
        result = PRGatesHandler(
            bus,
            scm=ApprovedSCM(plan_comment=self.PLAN),
            config_dir=tmp_path,
        ).handle(CreatePRCommand(issue_number=620, branch="feature/preflight"))

        assert result["passed"] is False
        evidence = {item["gate"]: item for item in result["gate_results"]}
        assert evidence[11]["status"] == "missing_evidence"


class TestPRGatesAndEvaluationSubject:
    def _gates(self, tmp_path: Path, document: str | None = None) -> None:
        (tmp_path / "gates.json").write_text(
            document
            or '{"policy_version":"test.v1","required":[],"optional":[],'
            '"disabled":[],"custom":[],"parameters":{"max_diff_bytes":1000}}'
        )

    def test_all_gate_results_and_success_evidence_share_one_subject(self, tmp_path: Path):
        self._gates(
            tmp_path,
            '{"policy_version":"test.v1","required":[5],"optional":[12],"disabled":[],"custom":[]}',
        )

        class PassingExternalGate(IExternalGate):
            name = "external"

            def run(self, context: GateContext) -> GateResult:
                assert context.subject is not None
                return GateResult(gate=self.name, passed=True, reason="ok")

        bus = Bus()
        events = _collect_events(bus)
        scm = _CapturingSCM(changed_files=("h.py",), diff="+complete")
        handler = PRGatesHandler(
            bus,
            scm=scm,
            config_dir=tmp_path,
            external_gates=[PassingExternalGate()],
        )

        result = handler.handle(
            CreatePRCommand(
                issue_number=42,
                branch="feature/x",
                correlation_id="run-identity",
            )
        )

        subject = result["evaluation_subject"]
        assert result["passed"] is True
        assert all(gate.subject and gate.subject.as_dict() == subject for gate in result["results"])
        for event in events:
            if event.name in {"GatesPassed", "PRCreated"}:
                assert event.payload["evaluation_subject"] == subject
        body = scm.created_body or ""
        assert subject["base_sha"] in body
        assert subject["head_sha"] in body
        assert subject["contract_hash"] in body
        assert "run-identity" in body

    def test_subject_policy_digest_binds_test_runner_policy(self, tmp_path: Path):
        self._gates(tmp_path)

        first = PRGatesHandler(
            Bus(),
            scm=MockSCM(),
            config_dir=tmp_path,
            eval_config=EvalSchema(
                test_policy_version="runner.v1",
                test_cmd="trusted-runner {test}",
                test_timeout=30,
            ),
        ).handle(CreatePRCommand(issue_number=42, branch="feature/x"))
        second = PRGatesHandler(
            Bus(),
            scm=MockSCM(),
            config_dir=tmp_path,
            eval_config=EvalSchema(
                test_policy_version="runner.v2",
                test_cmd="trusted-runner {test}",
                test_timeout=30,
            ),
        ).handle(CreatePRCommand(issue_number=42, branch="feature/x"))

        assert (
            first["evaluation_subject"]["policy_digest"]
            != second["evaluation_subject"]["policy_digest"]
        )

    def test_subject_policy_digest_binds_candidate_process_profile(self, tmp_path: Path):
        self._gates(tmp_path)
        first_handler = PRGatesHandler(Bus(), scm=MockSCM(), config_dir=tmp_path)
        second_handler = PRGatesHandler(Bus(), scm=MockSCM(), config_dir=tmp_path)
        first_handler._candidate_process_policy = {"environment_profile": "profile.v1"}
        second_handler._candidate_process_policy = {"environment_profile": "profile.v2"}

        first = first_handler.handle(CreatePRCommand(issue_number=42, branch="feature/x"))
        second = second_handler.handle(CreatePRCommand(issue_number=42, branch="feature/x"))

        assert (
            first["evaluation_subject"]["policy_digest"]
            != second["evaluation_subject"]["policy_digest"]
        )

    def test_subject_policy_digest_binds_scm_required_context(self, tmp_path: Path):
        self._gates(tmp_path)
        first = PRGatesHandler(
            Bus(),
            scm=MockSCM(),
            config_dir=tmp_path,
            scm_policy={
                "provider": "gitea",
                "required_status_context": "CI / lint-and-test (pull_request)",
            },
        ).handle(CreatePRCommand(issue_number=42, branch="feature/x"))
        second = PRGatesHandler(
            Bus(),
            scm=MockSCM(),
            config_dir=tmp_path,
            scm_policy={
                "provider": "gitea",
                "required_status_context": "CI / demo-tests (pull_request)",
            },
        ).handle(CreatePRCommand(issue_number=42, branch="feature/x"))

        assert (
            first["evaluation_subject"]["policy_digest"]
            != second["evaluation_subject"]["policy_digest"]
        )

    def test_python_syntax_evidence_reads_exact_head_and_records_tool(self, tmp_path: Path):
        self._gates(
            tmp_path,
            '{"policy_version":"test.v1","required":[9],"optional":[],"disabled":[],"custom":[],"parameters":{"max_quality_file_bytes":4096}}',
        )
        scm = MockSCM(changed_files=("h.py",), diff="+pass")
        bus = Bus()
        events = _collect_events(bus)

        result = PRGatesHandler(bus, scm=scm, config_dir=tmp_path).handle(
            CreatePRCommand(
                issue_number=42,
                branch="feature/x",
                payload={"workspace_id": "run-workspace:sha256:" + "f" * 64},
            )
        )

        assert result["passed"] is True
        assert scm.last_file_read == (MockSCM.HEAD_SHA, "h.py", 4096)
        completed = next(event for event in events if event.name == "GateEvaluationCompleted")
        evidence = completed.payload["gate_results"][0]
        assert evidence["status"] == "passed"
        assert evidence["tool"]["name"] == "cpython.ast"
        assert evidence["evaluation_subject"]["head_sha"] == MockSCM.HEAD_SHA
        assert completed.payload["observation_schema_version"] == 2
        assert completed.payload["gate_result_schema_version"] == 2
        assert completed.payload["observation_key"].startswith("sha256:")
        assert completed.payload["evidence_digest"].startswith("sha256:")
        assert completed.payload["evidence_provenance"]["gate_results"] == (
            "bound_evaluation_subject"
        )
        assert completed.payload["workspace_id"].startswith("run-workspace:sha256:")

    def test_reference_worker_binds_exact_mutation_authority(self, tmp_path: Path) -> None:
        self._gates(
            tmp_path,
            '{"policy_version":"test.v1","required":[],"optional":[],"disabled":[],"custom":[]}',
        )

        class ApprovedSCM(MockSCM):
            def get_comments(self, number: int) -> list[Comment]:
                return [
                    Comment(id=10, body=self._plan, user="bot"),
                    Comment(
                        id=11,
                        body="/approve",
                        user="maintainer",
                        created_at="2026-09-18T08:01:00Z",
                    ),
                ]

        bus = Bus()
        events = _collect_events(bus)
        scm = ApprovedSCM()
        PRGatesHandler(
            bus,
            scm=scm,
            config_dir=tmp_path,
            authority_store=_durable_authority(tmp_path, scm, 42),
        ).handle(
            CreatePRCommand(
                issue_number=42,
                branch="feature/x",
                payload={"workspace_id": "workspace-42"},
                correlation_id="reference-run-42",
            )
        )

        completed = next(event for event in events if event.name == "GateEvaluationCompleted")
        authority = completed.payload["mutation_authority"]
        assert completed.payload["evaluation_mode"] == "reference_worker"
        assert authority == {
            "schema_version": 1,
            "authority": "mutate_candidate",
            "source": "approved_plan_workflow",
            "issue": 42,
            "plan_comment_id": 10,
            "contract_hash": completed.payload["evaluation_subject"]["contract_hash"],
            "approval_source_id": "plan:10;comment:11",
            "workspace_id": "workspace-42",
            "correlation_id": "reference-run-42",
        }

    @pytest.mark.parametrize(
        ("error", "code"),
        [
            (SCMRevisionError("unknown_commit", "unknown"), "unknown_commit"),
            (SCMRevisionError("diff_failed", "diff failed"), "diff_failed"),
            (SubjectTooLargeError(1000), "subject_too_large"),
        ],
    )
    def test_comparison_failures_are_not_evaluated(
        self, tmp_path: Path, error: SCMRevisionError, code: str
    ):
        self._gates(tmp_path)

        class FailingComparisonSCM(MockSCM):
            def compare_commits(
                self, base_sha: str, head_sha: str, *, max_diff_bytes: int
            ) -> RevisionComparison:
                raise error

        bus = Bus()
        events = _collect_events(bus)
        result = PRGatesHandler(bus, scm=FailingComparisonSCM(), config_dir=tmp_path).handle(
            CreatePRCommand(issue_number=42, branch="feature/x")
        )

        assert result["passed"] is False
        assert result["gates_passed"] is False
        assert result["subject_error"]["code"] == code
        assert [event.name for event in events] == [
            "GateFailed",
            "GateEvaluationUnavailable",
        ]
        assert events[0].payload["status"] == "not_evaluated"
        evidence = events[0].payload["evaluation_subject"]
        assert evidence["base_sha"] == MockSCM.BASE_SHA
        assert evidence["head_sha"] == MockSCM.HEAD_SHA
        terminal = events[1].payload
        assert terminal["status"] == "not_evaluated"
        assert terminal["error"]["code"] == code
        assert terminal["evaluation_subject"] == evidence
        assert terminal["terminal_key"].startswith("sha256:")

    def test_comparison_with_contradicting_pair_is_rejected(self, tmp_path: Path):
        self._gates(tmp_path)

        class ContradictingSCM(MockSCM):
            def compare_commits(
                self, base_sha: str, head_sha: str, *, max_diff_bytes: int
            ) -> RevisionComparison:
                return RevisionComparison(
                    repository=self.repository_identity,
                    base_sha=base_sha,
                    head_sha="c" * 40,
                    changed_files=(),
                    diff="",
                    diff_bytes=0,
                )

        result = PRGatesHandler(Bus(), scm=ContradictingSCM(), config_dir=tmp_path).handle(
            CreatePRCommand(issue_number=42, branch="feature/x")
        )

        assert result["subject_error"]["code"] == "comparison_subject_mismatch"

    def test_missing_resolved_revision_blocks_before_gates(self, tmp_path: Path):
        self._gates(tmp_path)

        class MissingRevisionSCM(MockSCM):
            def resolve_ref(self, ref: str) -> str:
                return self.BASE_SHA if ref == "main" else ""

        bus = Bus()
        events = _collect_events(bus)
        result = PRGatesHandler(bus, scm=MissingRevisionSCM(), config_dir=tmp_path).handle(
            CreatePRCommand(issue_number=42, branch="feature/x")
        )

        assert result["subject_error"]["code"] == "invalid_evaluation_subject"
        assert events[0].payload["status"] == "not_evaluated"
        assert not any(event.name == "GateEvaluationCompleted" for event in events)

    def test_preexisting_subject_change_blocks_re_evaluation(self, tmp_path: Path):
        self._gates(tmp_path)
        stale = EvaluationSubject(
            repository="owner/repo",
            base_sha="a" * 40,
            head_sha="c" * 40,
            contract_hash="sha256:" + "d" * 64,
            policy_version="test.v1",
            policy_digest="sha256:" + "e" * 64,
        )

        result = PRGatesHandler(Bus(), scm=MockSCM(), config_dir=tmp_path).handle(
            CreatePRCommand(issue_number=42, branch="feature/x", subject=stale)
        )

        assert result["subject_error"]["code"] == "evaluation_subject_changed"

    def test_pr_head_movement_invalidates_before_pr_created(self, tmp_path: Path):
        self._gates(tmp_path)

        class MovedPRSCM(MockSCM):
            def get_pr_revision(self, pr_id: int) -> PullRequestRevision:
                revision = super().get_pr_revision(pr_id)
                return PullRequestRevision(
                    repository=revision.repository,
                    base_sha=revision.base_sha,
                    head_sha="c" * 40,
                )

        bus = Bus()
        events = _collect_events(bus)
        result = PRGatesHandler(bus, scm=MovedPRSCM(), config_dir=tmp_path).handle(
            CreatePRCommand(issue_number=42, branch="feature/x")
        )

        assert result["passed"] is False
        assert result["pr_created"] is True
        assert result["subject_error"]["code"] == "pr_revision_changed"
        assert any(event.name == "EvaluationSubjectInvalidated" for event in events)
        assert not any(event.name == "PRCreated" for event in events)

    def test_optional_gate_warns_but_passes(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [1], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is True
        assert any(e.name == "PRCreated" for e in events)

    def test_disabled_gate_skipped(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [1], "custom": []}'
        )
        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is True

    def test_no_config_defaults_to_all_required(self, tmp_path: Path):
        bus = Bus()
        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path / "nonexistent"))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result is not None

    def test_correlation_id_flows(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [1], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        handler.handle(
            CreatePRCommand(issue_number=42, branch="main", correlation_id="gate-corr-1")
        )

        for e in events:
            assert e.correlation_id == "gate-corr-1"

    def test_external_gate_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

        class FailingGate(IExternalGate):
            name = "secrets_scan"

            def run(self, context: GateContext) -> GateResult:
                return GateResult(gate="secrets_scan", passed=False, reason="Secrets found")

        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(
            bus,
            scm=MockSCM(),
            config_dir=str(tmp_path),
            external_gates=[FailingGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is False
        assert any(e.name == "GateFailed" for e in events)

    def test_external_gate_passes(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

        class PassingGate(IExternalGate):
            name = "lint_check"

            def run(self, context: GateContext) -> GateResult:
                return GateResult(gate="lint_check", passed=True, reason="All clean")

        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(
            bus,
            scm=MockSCM(),
            config_dir=str(tmp_path),
            external_gates=[PassingGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is True

    def test_path_risk_external_gate_marks_builtin_fallback_as_delegated(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [7], "optional": [], "disabled": [], "custom": []}'
        )

        class CapturingPathRiskGate(IExternalGate):
            name = "path_risk"

            def run(self, context: GateContext) -> GateResult:
                assert context.path_risk_configured is True
                return GateResult(gate=self.name, passed=True, reason="configured check passed")

        bus = Bus()
        handler = PRGatesHandler(
            bus,
            scm=MockSCM(changed_files=("keys/server.pem",), diff="private key material"),
            config_dir=str(tmp_path),
            external_gates=[CapturingPathRiskGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is True

    def test_external_gate_exception_blocks(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

        class BrokenGate(IExternalGate):
            name = "broken"

            def run(self, context: GateContext) -> GateResult:
                raise ConnectionError("timeout")

        bus = Bus()
        _collect_events(bus)

        handler = PRGatesHandler(
            bus,
            scm=MockSCM(),
            config_dir=str(tmp_path),
            external_gates=[BrokenGate()],
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        assert result["passed"] is False

    def test_pr_created_on_scm(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

        class PRCreatingSCM(MockSCM):
            def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
                return PR(id=1, number=99, title=title, html_url="http://gitea/pr/99")

        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(
            bus,
            scm=PRCreatingSCM(changed_files=("safe.py",), diff="+safe change"),
            config_dir=str(tmp_path),
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True
        assert result["gates_passed"] is True
        assert result["pr_created"] is True
        assert result["pr_number"] == 99
        assert result["pr_url"] == "http://gitea/pr/99"

        pr_events = [e for e in events if e.name == "PRCreated"]
        assert len(pr_events) == 1
        pr_event = pr_events[0]
        assert pr_event.payload["pr_number"] == 99
        assert pr_event.payload["pr_url"] == "http://gitea/pr/99"
        assert pr_event.payload["changed_files"] == ["safe.py"]
        assert pr_event.payload["diff"] == "+safe change"

    def test_pr_creation_exception_fails_closed_without_secret_leak(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """SCM exceptions produce bounded failure evidence, never PR success."""
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

        class RaisingSCM(MockSCM):
            def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
                raise RuntimeError("Authorization: token top-secret-value")

        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=RaisingSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is False
        assert result["gates_passed"] is True
        assert result["pr_created"] is False
        assert "pr_number" not in result
        assert result["pr_error"]["code"] == "scm_create_pr_failed"
        assert result["pr_error"]["type"] == "RuntimeError"
        assert not any(e.name == "PRCreated" for e in events)
        failed = [e for e in events if e.name == "PRCreationFailed"]
        assert len(failed) == 1
        assert failed[0].payload["source_command"] == "CreatePR"
        assert failed[0].payload["pr_created"] is False
        assert "top-secret-value" not in caplog.text
        assert "top-secret-value" not in str(failed[0].payload)
        assert "top-secret-value" not in str(result)

    def test_missing_scm_adapter_fails_closed(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=None, config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is False
        assert result["gates_passed"] is False
        assert result["pr_created"] is False
        assert result["subject_error"] == {
            "code": "scm_adapter_missing",
            "type": "SCMRevisionError",
            "message": "An SCM adapter is required to establish an evaluation subject",
        }
        assert [e.name for e in events] == [
            "GateFailed",
            "GateEvaluationUnavailable",
        ]
        assert "evaluation_subject" not in events[1].payload
        assert events[1].payload["terminal_key"].startswith("sha256:")
        assert not any(e.name == "PRCreated" for e in events)

    @pytest.mark.parametrize(
        "invalid_result",
        [
            None,
            PR(id=1, number=0, title="invalid", html_url="http://gitea/pr/0"),
            PR(id=1, number=1, title="invalid", html_url=""),
            PR(id=1, number=1, title="invalid", html_url="/relative/pr/1"),
            PR(
                id=1,
                number=1,
                title="invalid",
                html_url="http://token:secret@gitea/pr/1",
            ),
            PR(
                id=1,
                number=1,
                title="invalid",
                html_url="http://gitea/pr/1?access_token=secret",
            ),
            PR(id=1, number=1, title="invalid", html_url="http://gitea/pr/1#secret"),
            PR(id=1, number=1, title="invalid", html_url="http://gitea:bad/pr/1"),
            PR(id=1, number=1, title="invalid", html_url="http://gitea/pr/1\nsecret"),
            PR(id=1, number=1, title="invalid", html_url=" http://gitea/pr/1"),
            PR(id=1, number=1, title="invalid", html_url="http://gitea/pr/1 "),
            PR(id=1, number=1, title="invalid", html_url="http://[invalid/pr/1"),
        ],
    )
    def test_invalid_scm_response_fails_closed(self, tmp_path: Path, invalid_result: Any):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

        class InvalidResponseSCM(MockSCM):
            def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
                return invalid_result

        bus = Bus()
        events = _collect_events(bus)
        handler = PRGatesHandler(bus, scm=InvalidResponseSCM(), config_dir=str(tmp_path))

        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is False
        assert result["pr_created"] is False
        assert result["pr_error"]["code"] == "invalid_scm_response"
        assert not any(e.name == "PRCreated" for e in events)
        assert sum(e.name == "PRCreationFailed" for e in events) == 1

    def test_pr_failure_does_not_trigger_review_or_auto_merge(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

        class TrackingFailingSCM(MockSCM):
            def __init__(self) -> None:
                super().__init__()
                self.merge_calls: list[int] = []

            def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
                raise ConnectionError("SCM unavailable")

            def merge_pr(self, pr_id: int) -> bool:
                self.merge_calls.append(pr_id)
                return True

        bus = Bus()
        bus.config = _MockConfig(auto_merge_pr=True)
        review_triggers: list[Event] = []
        bus.subscribe("PRCreated", review_triggers.append)
        events = _collect_events(bus)
        scm = TrackingFailingSCM()
        handler = PRGatesHandler(bus, scm=scm, config_dir=str(tmp_path))

        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is False
        assert review_triggers == []
        assert scm.merge_calls == []
        assert not any(e.name in {"PRCreated", "PRMerged"} for e in events)
        assert any(e.name == "PRCreationFailed" for e in events)

    def test_publishes_gates_passed_when_all_gates_pass(self, tmp_path: Path):
        """#258: GatesPassed-Event muss vor PRCreated publisht werden, sodass
        das Dashboard die gates-Stage als 'done' anzeigen kann."""
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert result["passed"] is True
        # GatesPassed wird publisht, mit Issue-Nr und Anzahl der Gates
        gates_passed = [e for e in events if e.name == "GatesPassed"]
        assert len(gates_passed) == 1
        assert gates_passed[0].payload["issue"] == 42
        assert "gates_run" in gates_passed[0].payload
        # Reihenfolge: GatesPassed VOR PRCreated
        names = [e.name for e in events]
        assert names.index("GatesPassed") < names.index("PRCreated")

    def test_no_gates_passed_when_blocked(self, tmp_path: Path):
        """#258: bei blockiertem Run (GateFailed) wird GatesPassed NICHT publisht."""
        (tmp_path / "gates.json").write_text(
            '{"required": [1], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)

        # Issue auf 'main'-Branch → Gate 1 fails → blocked
        handler = PRGatesHandler(bus, scm=MockSCM(), config_dir=str(tmp_path))
        result = handler.handle(CreatePRCommand(issue_number=42, branch="main"))

        assert result["passed"] is False
        # Kein GatesPassed wenn ein Gate fehlschlug
        assert not any(e.name == "GatesPassed" for e in events)
        # GateFailed wurde publisht
        assert any(e.name == "GateFailed" for e in events)


class _MockConfig:
    """Test-Helper: minimaler IConfig fuer feature_flag()."""

    def __init__(self, **flags: bool) -> None:
        self._flags = flags

    def feature_flag(self, name: str) -> bool:
        return self._flags.get(name, False)


class _PRCreatingMergingSCM(MockSCM):
    """Test-Helper: create_pr liefert PR, merge_pr trackt Aufrufe."""

    def __init__(self, merge_returns: bool = True, merge_raises: bool = False):
        super().__init__()
        self.merge_calls: list[int] = []
        self._merge_returns = merge_returns
        self._merge_raises = merge_raises

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        return PR(id=1, number=99, title=title, html_url="http://gitea/pr/99")

    def merge_pr(self, pr_id: int) -> bool:
        self.merge_calls.append(pr_id)
        if self._merge_raises:
            raise RuntimeError("simulated SCM merge failure")
        return self._merge_returns


class TestAutoMerge:
    """Merge policy runs only after the separate structured review."""

    def _gates_open(self, tmp_path: Path) -> None:
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )

    def test_pr_gate_never_merges_even_when_feature_is_enabled(self, tmp_path: Path):
        self._gates_open(tmp_path)
        bus = Bus()
        bus.config = _MockConfig(auto_merge_pr=True)
        events = _collect_events(bus)
        scm = _PRCreatingMergingSCM()

        handler = PRGatesHandler(bus, scm=scm, config_dir=str(tmp_path))
        handler.handle(CreatePRCommand(issue_number=42, branch="samuel/issue-42"))

        assert scm.merge_calls == []
        assert any(e.name == "PRCreated" for e in events)
        assert not any(e.name == "PRMerged" for e in events)


class TestOutOfScopeDiff:
    """#529: commitgebundener Contract-Scope via Gates-Handler."""

    PLAN = """## Plan
Agent-Metadaten
### Änderungsscope
Scope-Schema: 1
- [FILE] `h.py`
Architecture-Expansion: disabled
### Akzeptanzkriterien
- [ ] [DIFF] h.py
"""

    def test_out_of_scope_diff_blocks_and_emits_bound_evidence(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": ["7b"], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)
        handler = PRGatesHandler(
            bus,
            scm=MockSCM(
                plan_comment=self.PLAN,
                changed_files=("unrelated.py",),
                diff="diff",
            ),
            config_dir=str(tmp_path),
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))

        oos = [e for e in events if e.name == "OutOfScopeDiff"]
        assert len(oos) == 1
        assert oos[0].payload["files"] == ["unrelated.py"]
        assert oos[0].payload["scope_evidence"]["head_sha"] == MockSCM.HEAD_SHA
        assert result["passed"] is False

    def test_in_scope_diff_no_warning(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": ["7b"], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        events = _collect_events(bus)
        handler = PRGatesHandler(
            bus,
            scm=MockSCM(plan_comment=self.PLAN, changed_files=("h.py",), diff="diff"),
            config_dir=str(tmp_path),
        )
        result = handler.handle(CreatePRCommand(issue_number=42, branch="feature/test"))
        assert not any(e.name == "OutOfScopeDiff" for e in events)
        assert result["passed"] is True


class _CapturingSCM(MockSCM):
    """#368: faengt den PR-Body fuer Briefing-Assertions ab."""

    def __init__(
        self,
        plan_comment: str = "## Plan\nAgent-Metadaten\n- [ ] [DIFF] h.py",
        *,
        changed_files: tuple[str, ...] = (),
        diff: str = "",
    ):
        super().__init__(plan_comment, changed_files=changed_files, diff=diff)
        self.created_body: str | None = None

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        self.created_body = body
        return PR(id=1, number=7, title=title, html_url="http://scm/pr/7")


def test_score_payload_has_no_gate_or_workflow_authority(tmp_path: Path):
    (tmp_path / "gates.json").write_text(
        '{"required": [], "optional": [], "disabled": [], "custom": []}'
    )
    bus = Bus()
    handler = PRGatesHandler(bus, scm=_CapturingSCM(), config_dir=str(tmp_path))

    result = handler.handle(
        CreatePRCommand(issue_number=42, branch="feature/x", payload={"score": 0.0})
    )

    assert result["passed"] is True
    assert all(gate.gate not in {4, 10} for gate in result["results"])


class TestReviewerBriefing:
    """The PR body presents gate authority separately from passive scores."""

    def test_briefing_rendered_in_body(self, tmp_path: Path):
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )
        bus = Bus()
        scm = _CapturingSCM()
        handler = PRGatesHandler(bus, scm=scm, config_dir=str(tmp_path))
        handler.handle(
            CreatePRCommand(
                issue_number=42,
                branch="feature/x",
                payload={"score": 0.95},
                correlation_id="corr-xyz",
            )
        )
        body = scm.created_body or ""
        assert "S.A.M.U.E.L. Gate-Entscheidung" in body
        assert "Freigabeautorität" in body
        assert "Eval-Score" not in body
        assert "95" not in body
        assert "corr-xyz" in body  # Correlation-ID
        assert "| 10 EvalScore |" not in body
        assert "default" in body  # Profil
        assert "SARIF) folgt" not in body
        assert "#368 Task 5" not in body

    def test_briefing_distinguishes_every_v2_gate_state(self, tmp_path: Path) -> None:
        (tmp_path / "gates.json").write_text(
            '{"required": [], "optional": [], "disabled": [], "custom": []}'
        )
        subject = EvaluationSubject(
            repository="owner/repo",
            base_sha="a" * 40,
            head_sha="b" * 40,
            contract_hash="sha256:" + "c" * 64,
            policy_version="preflight.v2",
            policy_digest="sha256:" + "d" * 64,
        )
        results = [
            GateResult(gate=1, passed=True, status="passed", reason="ok"),
            GateResult(gate=2, passed=False, status="failed", reason="failed"),
            GateResult(gate=3, passed=False, status="error", reason="error"),
            GateResult(gate=9, passed=True, status="not_applicable", reason="n/a"),
            GateResult(
                gate=11,
                passed=None,
                executed=False,
                status="skipped_precondition",
                reason="skip",
            ),
        ]

        rendered = PRGatesHandler(
            Bus(), scm=MockSCM(), config_dir=tmp_path
        )._render_reviewer_briefing(results, "run-v2", subject)

        assert all(label in rendered for label in ("PASS", "FAIL", "ERROR", "N/A", "SKIP"))


def test_explicit_authority_profile_never_falls_back_on_invalid_config(tmp_path: Path):
    (tmp_path / "gates.self.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid gates config"):
        PRGatesHandler(
            Bus(),
            scm=_CapturingSCM(),
            config_dir=tmp_path,
            gates_profile="self",
        )


class _CandidateSCM(MockSCM):
    def __init__(
        self,
        *,
        changed_files: tuple[str, ...] = ("allowed.py",),
        scope_path: str | None = None,
    ) -> None:
        self.issue = Issue(
            number=521,
            title="Candidate requirements",
            body="Evaluate an existing candidate",
            state="open",
            labels=[Label(id=1, name="status:approved")],
        )
        snapshot = PlanningSourceSnapshot(
            schema_version=1,
            repository="owner/repo",
            base_ref="main",
            base_sha=self.BASE_SHA,
            issue_digest=issue_revision_digest(
                number=self.issue.number,
                title=self.issue.title,
                body=self.issue.body,
            ),
        )
        scope_path = scope_path or (changed_files[0] if changed_files else "allowed.py")
        plan = (
            "## Plan\n"
            "### Änderungsscope\n"
            "Scope-Schema: 1\n"
            "Architecture-Expansion: disabled\n"
            f"- [FILE] `{scope_path}`\n"
            "### Akzeptanzkriterien\n"
            f"- [ ] [DIFF] {scope_path}\n\n"
            f"{render_planning_source(snapshot)}"
        )
        super().__init__(plan, changed_files=changed_files, diff="+candidate\n")
        self.pr_calls = 0

    def get_issue(self, number: int) -> Issue:
        assert number == 521
        return self.issue

    def get_comments(self, number: int) -> list[Comment]:
        assert number == 521
        return [
            Comment(
                id=71,
                body=self._plan,
                user="samuel-bot",
                created_at="2026-09-18T08:00:00Z",
            )
        ]

    def get_label_events(self, number: int, label: str) -> list[SCMLabelEvent]:
        assert number == 521
        assert label == "status:approved"
        return [
            SCMLabelEvent(
                source_id="label:event:72",
                label=label,
                actor="maintainer",
                actor_type="human",
                timestamp="2026-09-18T08:01:00Z",
            )
        ]

    def create_pr(self, head: str, base: str, title: str, body: str) -> Any:
        self.pr_calls += 1
        return super().create_pr(head, base, title, body)


class _ObservationStore:
    def __init__(self, records: list[ObservationRecord] | None = None) -> None:
        self.records = records or []

    def list_observations(self, issue_number: int | None = None) -> list[ObservationRecord]:
        return [
            record
            for record in self.records
            if issue_number is None or record.issue_number == issue_number
        ]


def _candidate_handler(
    tmp_path: Path,
    scm: _CandidateSCM,
    *,
    records: list[ObservationRecord] | None = None,
    bus: Bus | None = None,
    provider_verification: Any = None,
) -> PRGatesHandler:
    (tmp_path / "gates.json").write_text(
        '{"policy_version":"candidate.v1","required":["7b",11],'
        '"optional":[],"disabled":[],"custom":[]}',
        encoding="utf-8",
    )
    authority = _candidate_authority(tmp_path, scm)
    return PRGatesHandler(
        bus or Bus(),
        scm=scm,
        config_dir=tmp_path,
        project_root=tmp_path,
        observation_store=_ObservationStore(records),  # type: ignore[arg-type]
        provider_verification=provider_verification,
        authority_store=authority,
    )


def _candidate_authority(tmp_path: Path, scm: _CandidateSCM) -> Any:
    del tmp_path
    authority = _DurableAuthority()
    plan = scm.get_comments(521)[0]
    contract = parse_acceptance_contract(plan.body)
    admission_key = "candidate-budget-521"
    authority.put_budget_admission(
        WorkflowBudgetAdmissionRecord(
            admission_key=admission_key,
            repository=scm.repository_identity,
            issue_number=521,
            invocation_digest="sha256:invocation",
            source_digest="sha256:source",
            policy_digest="sha256:policy",
            correlation_id="candidate-521",
            token_limit=100_000,
        )
    )
    authority.bind_budget_plan(
        admission_key,
        plan_contract_hash=contract.contract_hash,
        plan_comment_id=plan.id,
    )
    event = scm.get_label_events(521, "status:approved")[0]
    persist_plan_approval(
        authority,  # type: ignore[arg-type]
        repository=scm.repository_identity,
        issue_number=521,
        contract=contract,
        approval=AcceptanceApproval(
            state="approved",
            actor=event.actor,
            method="status:approved/polling",
            source_id=f"plan:{plan.id};{event.source_id}",
            approved_at=event.timestamp,
            contract_hash=contract.contract_hash,
            plan_comment_id=plan.id,
        ),
        transport="authenticated_scm_polling",
    )
    return authority


class _ProviderCoordinator:
    def __init__(
        self,
        *,
        completed: bool = False,
        passed: bool = True,
        blocked: bool = False,
    ) -> None:
        self.completed = completed
        self.passed = passed
        self.blocked = blocked
        self.calls: list[dict[str, Any]] = []
        self.acknowledged: list[tuple[str, str]] = []

    def request(self, **kwargs: Any) -> VerificationProgress:
        self.calls.append(kwargs)
        request = VerificationRequest.build(
            request_nonce="provider-nonce",
            authorized_at="2026-09-18T08:02:00Z",
            subject=kwargs["subject"],
            authority=kwargs["authority"],
            criteria=kwargs["criteria"],
            policy_binding=kwargs["policy_binding"],
            provider_profile="fixture-v1",
            provider_profile_digest="sha256:" + "f" * 64,
            consumer_mode=kwargs.get("consumer_mode", "passive_candidate"),
        )
        reference = ProviderRunReference(
            provider="fixture",
            repository="owner/repo",
            run_id="704",
            attempt=1,
            request_key=request.request_key,
        )
        if self.blocked:
            return VerificationProgress(
                request=request,
                status="blocked",
                reason_code="provider_integrity_invalid",
                reference=reference,
            )
        if not self.completed:
            return VerificationProgress(
                request=request,
                status="running",
                reason_code="provider_run_pending",
                reference=reference,
            )
        evidence = ProviderEvidence(
            request_key=request.request_key,
            subject=request.subject,
            reference=reference,
            provider_profile_digest=request.provider_profile_digest,
            workflow_digest="sha256:" + "1" * 64,
            tool_digest="sha256:" + "2" * 64,
            environment_digest="sha256:" + "3" * 64,
            issuer="fixture-control-plane",
            issued_at="2026-09-18T08:03:00Z",
            expires_at="2026-09-18T09:03:00Z",
            nonce=request.request_nonce,
            criteria=tuple(
                ProviderCriterionEvidence(
                    criterion_id=criterion.criterion_id,
                    tag=criterion.tag,
                    status="passed" if self.passed else "failed",
                    reason="provider result",
                    evidence_digest="sha256:" + "4" * 64,
                )
                for criterion in request.criteria
            ),
            integrity={"scheme": "fixture", "verified": True},
        )
        return VerificationProgress(
            request=request,
            status="evidence_ready",
            reason_code="provider_evidence_ready",
            reference=reference,
            evidence=evidence,
        )

    def acknowledge(self, request_key: str, *, outcome: str) -> None:
        self.acknowledged.append((request_key, outcome))


def _candidate_observation(
    scm: _CandidateSCM,
    pending: dict[str, Any],
    preflight: list[dict[str, Any]],
    *,
    gate_11_passed: bool,
) -> ObservationRecord:
    subject = EvaluationSubject.from_dict(pending["evaluation_subject"])
    plan, contract = latest_active_plan(scm.get_comments(521)) or (None, None)
    assert plan is not None and contract is not None
    approval = AcceptanceApproval(
        state="approved",
        actor="maintainer",
        method="status:approved/polling",
        source_id="plan:71;label:event:72",
        approved_at="2026-09-18T08:01:00Z",
        contract_hash=contract.contract_hash,
        plan_comment_id=71,
    )
    bound_contract = contract.with_approval(approval).as_dict()
    acceptance = {
        "schema_version": 1,
        "evaluation_subject": subject.as_dict(),
        "contract": bound_contract,
        "results": [
            {
                "criterion_id": bound_contract["criteria"][0]["criterion_id"],
                "tag": "DIFF",
                "status": "passed" if gate_11_passed else "failed",
                "reason": "verified" if gate_11_passed else "not verified",
                "evidence": {
                    "schema_version": 1,
                    "kind": "diff",
                    "path": "allowed.py",
                    "changed": gate_11_passed,
                },
            }
        ],
    }
    gate_11 = {
        "gate": 11,
        "passed": gate_11_passed,
        "executed": True,
        "status": "passed" if gate_11_passed else "failed",
        "reason_code": "gate_11_passed" if gate_11_passed else "gate_11_failed",
        "reason": "bound acceptance evidence",
        "owasp_risk": None,
        "phase": "post_candidate",
        "authority": "required",
        "evaluation_subject": subject.as_dict(),
    }
    gates = [*preflight, gate_11]
    identity = EvaluationObservationIdentity.build(
        subject=subject,
        gate_results=gates,
        acceptance_evidence=acceptance,
    )
    payload = {
        "schema_version": identity.schema_version,
        "observation_key": identity.observation_key,
        "evidence_digest": identity.evidence_digest,
        "issue": 521,
        "evaluation_subject": subject.as_dict(),
        "gate_results": gates,
        "acceptance_evidence": acceptance,
        "gate_result_schema_version": 2,
        "observation_schema_version": identity.schema_version,
        "evidence_provenance": {
            "gate_results": "bound_evaluation_subject",
            "acceptance_evidence": "bound_acceptance_evidence",
        },
    }
    return ObservationRecord(
        observation_key=identity.observation_key,
        subject_key=canonical_digest(subject.as_dict()),
        evidence_digest=identity.evidence_digest,
        observation_schema=f"bound.v{identity.schema_version}",
        payload=payload,
        issue_number=521,
    )


def test_passive_candidate_waits_without_verifier_pr_or_mutation(tmp_path: Path) -> None:
    bus = Bus()
    events = _collect_events(bus)
    scm = _CandidateSCM()
    handler = _candidate_handler(tmp_path, scm, bus=bus)

    result = handler.handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )
    repeated = handler.handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_verification_pending"
    assert repeated["submission_key"] == result["submission_key"]
    assert result["mutation_authority"] == "none"
    assert scm.pr_calls == 0
    assert [event.name for event in events] == [
        "CandidateVerificationPending",
        "CandidateVerificationPending",
    ]


def test_passive_candidate_reuses_exact_observation_and_completes_without_pr(
    tmp_path: Path,
) -> None:
    scm = _CandidateSCM()
    pending = _candidate_handler(tmp_path, scm).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )
    record = _candidate_observation(
        scm,
        pending,
        pending["preflight_gate_results"],
        gate_11_passed=True,
    )
    bus = Bus()
    events = _collect_events(bus)

    result = _candidate_handler(tmp_path, scm, records=[record], bus=bus).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_evaluation_completed"
    assert result["observation_key"] == record.observation_key
    assert result["mutation_authority"] == "none"
    assert scm.pr_calls == 0
    assert not any(event.name in {"GateEvaluationCompleted", "PRCreated"} for event in events)


def test_explicit_provider_request_does_not_collapse_into_passive_evidence_read(
    tmp_path: Path,
) -> None:
    scm = _CandidateSCM()
    pending = _candidate_handler(tmp_path, scm).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )
    record = _candidate_observation(
        scm,
        pending,
        pending["preflight_gate_results"],
        gate_11_passed=True,
    )
    provider = _ProviderCoordinator()

    result = _candidate_handler(
        tmp_path,
        scm,
        records=[record],
        provider_verification=provider,
    ).handle_provider_candidate(
        RequestCandidateVerificationCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_verification_pending"
    assert result["reason_code"] == "provider_run_pending"
    assert len(provider.calls) == 1


def test_passive_gate_failure_is_terminal_without_healing_event(tmp_path: Path) -> None:
    scm = _CandidateSCM()
    pending = _candidate_handler(tmp_path, scm).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )
    record = _candidate_observation(
        scm,
        pending,
        pending["preflight_gate_results"],
        gate_11_passed=False,
    )
    bus = Bus()
    events = _collect_events(bus)

    result = _candidate_handler(tmp_path, scm, records=[record], bus=bus).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_evaluation_failed"
    assert result["reason_code"] == "required_gate_failed"
    assert not any(event.name.startswith("Healing") for event in events)


@pytest.mark.parametrize(
    ("command", "reason_code"),
    [
        (SubmitCandidateCommand(issue_number=521, head_sha="main"), "candidate_head_invalid"),
        (
            SubmitCandidateCommand(
                issue_number=521,
                head_sha=MockSCM.HEAD_SHA,
                payload={"acceptance_approval": {"state": "approved"}},
            ),
            "producer_authority_fields_rejected",
        ),
    ],
)
def test_passive_candidate_rejects_untrusted_or_ambiguous_input(
    tmp_path: Path,
    command: SubmitCandidateCommand,
    reason_code: str,
) -> None:
    result = _candidate_handler(tmp_path, _CandidateSCM()).handle_candidate(command)

    assert result["status"] == "candidate_submission_rejected"
    assert result["reason_code"] == reason_code


def test_passive_candidate_rejects_issue_drift(tmp_path: Path) -> None:
    scm = _CandidateSCM()
    scm.issue.body = "changed after planning"

    result = _candidate_handler(tmp_path, scm).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["reason_code"] == "candidate_issue_drift"


def test_passive_candidate_rejects_head_and_base_drift(tmp_path: Path) -> None:
    scm = _CandidateSCM()
    handler = _candidate_handler(tmp_path, scm)

    wrong_head = handler.handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha="c" * 40)
    )
    assert wrong_head["reason_code"] == "candidate_head_mismatch"

    class _MovedBaseSCM(_CandidateSCM):
        def resolve_ref(self, ref: str) -> str:
            if ref == "main":
                return "d" * 40
            return super().resolve_ref(ref)

    moved = _MovedBaseSCM()
    base_drift = _candidate_handler(tmp_path, moved).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=moved.HEAD_SHA)
    )
    assert base_drift["reason_code"] == "candidate_base_drift"


def test_passive_candidate_scope_violation_is_terminal_without_provider_dispatch(
    tmp_path: Path,
) -> None:
    bus = Bus()
    events = _collect_events(bus)
    scm = _CandidateSCM(changed_files=("outside.py",), scope_path="allowed.py")

    result = _candidate_handler(tmp_path, scm, bus=bus).handle_candidate(
        SubmitCandidateCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_evaluation_failed"
    assert result["reason_code"] == "gate_7b_failed"
    assert any(event.name == "OutOfScopeDiff" for event in events)
    assert not any(event.name == "CandidateVerificationPending" for event in events)


def test_provider_request_starts_only_after_required_preflight(tmp_path: Path) -> None:
    provider = _ProviderCoordinator()
    scm = _CandidateSCM(changed_files=("outside.py",), scope_path="allowed.py")
    handler = _candidate_handler(
        tmp_path,
        scm,
        provider_verification=provider,
    )

    result = handler.handle_provider_candidate(
        RequestCandidateVerificationCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_evaluation_failed"
    assert result["reason_code"] == "gate_7b_failed"
    assert provider.calls == []


def test_provider_request_is_visible_pending_and_never_mutates(tmp_path: Path) -> None:
    provider = _ProviderCoordinator()
    bus = Bus()
    events = _collect_events(bus)
    scm = _CandidateSCM()
    handler = _candidate_handler(
        tmp_path,
        scm,
        bus=bus,
        provider_verification=provider,
    )

    result = handler.handle_provider_candidate(
        RequestCandidateVerificationCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_verification_pending"
    assert result["reason_code"] == "provider_run_pending"
    assert result["mutation_authority"] == "none"
    assert scm.pr_calls == 0
    assert provider.calls[0]["new_request"] is False
    names = [event.name for event in events]
    assert "ProviderVerificationRequested" in names
    assert "ProviderVerificationPending" in names
    assert "GateEvaluationCompleted" not in names
    assert not any(name.startswith("Healing") for name in names)


@pytest.mark.parametrize(
    ("provider_passed", "expected_status", "acknowledged"),
    [
        (True, "candidate_evaluation_completed", "completed"),
        (False, "candidate_evaluation_failed", "failed"),
    ],
)
def test_provider_evidence_drives_gate_11_without_pr_or_healing(
    tmp_path: Path,
    provider_passed: bool,
    expected_status: str,
    acknowledged: str,
) -> None:
    provider = _ProviderCoordinator(completed=True, passed=provider_passed)
    bus = Bus()
    events = _collect_events(bus)
    scm = _CandidateSCM()
    handler = _candidate_handler(
        tmp_path,
        scm,
        bus=bus,
        provider_verification=provider,
    )

    result = handler.handle_provider_candidate(
        RequestCandidateVerificationCommand(
            issue_number=521,
            head_sha=scm.HEAD_SHA,
            new_request=True,
        )
    )

    assert result["status"] == expected_status
    assert result["mutation_authority"] == "none"
    assert scm.pr_calls == 0
    assert provider.calls[0]["new_request"] is True
    assert provider.acknowledged == [(result["request_key"], acknowledged)]
    names = [event.name for event in events]
    assert "ProviderGateEvaluationCompleted" in names
    assert "GateEvaluationCompleted" not in names
    assert "PRCreated" not in names
    assert not any(name.startswith("Healing") for name in names)


def test_passive_provider_ignores_later_status_projection_change(
    tmp_path: Path,
) -> None:
    class RevokedAfterDispatchSCM(_CandidateSCM):
        issue_reads = 0

        def get_issue(self, number: int) -> Issue:
            issue = super().get_issue(number)
            self.issue_reads += 1
            if self.issue_reads > 2:
                return replace(issue, labels=[])
            return issue

    provider = _ProviderCoordinator(completed=True)
    bus = Bus()
    events = _collect_events(bus)
    scm = RevokedAfterDispatchSCM()

    result = _candidate_handler(
        tmp_path,
        scm,
        bus=bus,
        provider_verification=provider,
    ).handle_provider_candidate(
        RequestCandidateVerificationCommand(issue_number=521, head_sha=scm.HEAD_SHA)
    )

    assert result["status"] == "candidate_evaluation_completed"
    assert provider.acknowledged == [(result["request_key"], "completed")]
    assert scm.pr_calls == 0
    names = [event.name for event in events]
    assert "ProviderVerificationBlocked" not in names
    assert "ProviderGateEvaluationCompleted" in names
    assert "GateEvaluationCompleted" not in names


def _reference_command(scm: _CandidateSCM) -> CreatePRCommand:
    active = latest_active_plan(scm.get_comments(521))
    assert active is not None
    plan, contract = active
    approval = AcceptanceApproval(
        state="approved",
        actor="maintainer",
        method="status:approved/polling",
        source_id="plan:71;label:event:72",
        approved_at="2026-09-18T08:01:00Z",
        contract_hash=contract.contract_hash,
        plan_comment_id=plan.id,
    )
    return CreatePRCommand(
        issue_number=521,
        branch="feature/provider",
        payload={
            "acceptance_approval": approval.as_dict(),
            "workspace_id": "workspace-521",
        },
        correlation_id="reference-provider-521",
    )


def test_reference_worker_waits_for_provider_without_local_verifier_or_pr(
    tmp_path: Path,
) -> None:
    provider = _ProviderCoordinator()
    bus = Bus()
    events = _collect_events(bus)
    verifier = _VerificationSpy()
    bus.register_command("VerifyAC", verifier)
    scm = _CandidateSCM()

    result = _candidate_handler(
        tmp_path,
        scm,
        bus=bus,
        provider_verification=provider,
    ).handle(_reference_command(scm))

    assert result["provider_pending"] is True
    assert result["reason_code"] == "provider_run_pending"
    assert verifier.calls == 0
    assert scm.pr_calls == 0
    assert provider.calls[0]["consumer_mode"] == "reference_worker"
    context = provider.calls[0]["consumer_context"]
    assert context["branch"] == "feature/provider"
    assert context["base"] == "main"
    assert context["workspace_id"] == "workspace-521"
    assert context["acceptance_approval"]["source_id"] == "plan:71;label:event:72"
    assert not any(event.name in {"GateEvaluationCompleted", "PRCreated"} for event in events)


@pytest.mark.parametrize(
    ("provider_passed", "expected_passed", "expected_prs", "outcome"),
    [(True, True, 1, "completed"), (False, False, 0, "failed")],
)
def test_reference_worker_consumes_provider_evidence_before_gate_decision(
    tmp_path: Path,
    provider_passed: bool,
    expected_passed: bool,
    expected_prs: int,
    outcome: str,
) -> None:
    provider = _ProviderCoordinator(completed=True, passed=provider_passed)
    bus = Bus()
    events = _collect_events(bus)
    verifier = _VerificationSpy()
    bus.register_command("VerifyAC", verifier)
    scm = _CandidateSCM()

    result = _candidate_handler(
        tmp_path,
        scm,
        bus=bus,
        provider_verification=provider,
    ).handle(_reference_command(scm))

    assert result["passed"] is expected_passed
    assert scm.pr_calls == expected_prs
    assert verifier.calls == 0
    assert provider.acknowledged == [
        (provider.calls[0]["subject"] and result["request_key"], outcome)
    ]
    completed = [event for event in events if event.name == "GateEvaluationCompleted"]
    assert len(completed) == 1
    assert completed[0].payload["request_key"] == result["request_key"]
    assert completed[0].payload["mutation_authority"]["workspace_id"] == "workspace-521"
    assert completed[0].payload["evidence_provenance"]["acceptance_evidence"] == (
        "bound_acceptance_evidence"
    )


def test_reference_provider_trust_failure_cannot_enter_healing_or_pr_path(
    tmp_path: Path,
) -> None:
    provider = _ProviderCoordinator(blocked=True)
    bus = Bus()
    events = _collect_events(bus)
    scm = _CandidateSCM()

    result = _candidate_handler(
        tmp_path,
        scm,
        bus=bus,
        provider_verification=provider,
    ).handle(_reference_command(scm))

    assert result["provider_blocked"] is True
    assert result["reason_code"] == "provider_integrity_invalid"
    assert scm.pr_calls == 0
    assert provider.acknowledged == []
    assert "ProviderVerificationBlocked" in [event.name for event in events]
    assert not any(
        event.name in {"GateEvaluationCompleted", "PRCreated"} or event.name.startswith("Healing")
        for event in events
    )


def test_reference_provider_ignores_later_status_projection_change(
    tmp_path: Path,
) -> None:
    class RevokedAfterDispatchSCM(_CandidateSCM):
        issue_reads = 0

        def get_issue(self, number: int) -> Issue:
            issue = super().get_issue(number)
            self.issue_reads += 1
            if self.issue_reads > 1:
                return replace(issue, labels=[])
            return issue

    provider = _ProviderCoordinator(completed=True)
    bus = Bus()
    events = _collect_events(bus)
    scm = RevokedAfterDispatchSCM()

    result = _candidate_handler(
        tmp_path,
        scm,
        bus=bus,
        provider_verification=provider,
    ).handle(_reference_command(scm))

    assert result["passed"] is True
    assert provider.acknowledged == [(result["request_key"], "completed")]
    assert scm.pr_calls == 1
    assert "ProviderVerificationBlocked" not in [event.name for event in events]
    assert any(event.name == "GateEvaluationCompleted" for event in events)
