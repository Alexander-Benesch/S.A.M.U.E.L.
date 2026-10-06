from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any
from unittest.mock import Mock

from samuel.core.acceptance import (
    AcceptanceApproval,
    parse_acceptance_contract,
    persist_plan_approval,
)
from samuel.core.bus import Bus
from samuel.core.commands import ReviewCommand
from samuel.core.config import load_workflow_config
from samuel.core.evaluation_subject import EvaluationSubject, PullRequestRevision
from samuel.core.events import PRCreated
from samuel.core.issue_context import current_workflow_correlation
from samuel.core.ports import ILLMProvider, IVersionControl
from samuel.core.review import text_digest
from samuel.core.state import AuthorityRecord, OperationIntentRecord
from samuel.core.types import PR, Comment, Issue, LLMResponse, canonical_digest
from samuel.core.workflow import WorkflowEngine
from samuel.slices.review.handler import ReviewHandler

PLAN = "## Plan\nAgent-Metadaten\n### Akzeptanzkriterien\n- [ ] [DIFF] safe.py"


class MockAuthority:
    def __init__(self) -> None:
        self.intents: dict[str, OperationIntentRecord] = {}
        self.records: dict[str, AuthorityRecord] = {}
        contract = parse_acceptance_contract(PLAN)
        persist_plan_approval(
            self,  # type: ignore[arg-type]
            repository="https://scm.example/owner/repo",
            issue_number=42,
            contract=contract,
            approval=AcceptanceApproval(
                state="approved",
                actor="maintainer",
                method="comment",
                source_id="plan:10;comment:11",
                approved_at="2026-09-19T01:01:00Z",
                contract_hash=contract.contract_hash,
                plan_comment_id=10,
            ),
            transport="signed_webhook",
        )

    def put_authority_record(self, record: AuthorityRecord) -> bool:
        self.records.setdefault(record.record_key, record)
        return True

    def get_authority_record(self, key: str) -> AuthorityRecord | None:
        return self.records.get(key)

    def get_intent(self, key: str) -> OperationIntentRecord | None:
        return self.intents.get(key)

    def put_intent(self, record: OperationIntentRecord) -> object:
        self.intents.setdefault(record.intent_key, record)
        return object()

    def finish_intent(self, key: str, *, status: str, postcondition: dict[str, Any]) -> object:
        current = self.intents[key]
        if current.status != "pending" and (
            current.status != status or current.postcondition != postcondition
        ):
            raise AssertionError("terminal intent must not be rewritten")
        self.intents[key] = replace(current, status=status, postcondition=postcondition)  # type: ignore[arg-type]
        return object()


class MockSCM(IVersionControl):
    def __init__(self, *, qualified_merge: bool = False) -> None:
        self.posted: list[tuple[int, str]] = []
        self.plan = Comment(id=10, body=PLAN, user="samuel", created_at="2026-09-19T01:00:00Z")
        self.approval = Comment(
            id=11,
            body="/approve",
            user="maintainer",
            created_at="2026-09-19T01:01:00Z",
        )
        self.revision: PullRequestRevision | None = None
        self.pr = PR(id=12, number=12, title="PR", html_url="https://scm/pr/12")
        self.merge_calls: list[tuple[int, str | None]] = []
        self.qualified_merge = qualified_merge

    @property
    def capabilities(self) -> set[str]:
        return {"native_expected_head_merge"} if self.qualified_merge else set()

    def get_issue(self, number: int) -> Issue:
        return Issue(number=number, title="T", body="b", state="open")

    def get_comments(self, number: int) -> list[Comment]:
        return [self.plan, self.approval]

    def post_comment(self, number: int, body: str) -> Comment:
        self.posted.append((number, body))
        return Comment(id=20, body=body, user="bot")

    def get_pr(self, pr_id: int) -> PR:
        return self.pr

    def get_pr_revision(self, pr_id: int) -> PullRequestRevision:
        assert self.revision is not None
        return self.revision

    def create_pr(self, head: str, base: str, title: str, body: str) -> PR:
        raise NotImplementedError

    def swap_label(self, number: int, remove: str, add: str) -> None:
        pass

    def list_issues(self, labels: list[str]) -> list[Issue]:
        return []

    def close_issue(self, number: int) -> None:
        pass

    def merge_pr(self, pr_id: int) -> bool:
        raise AssertionError("unbound merge must not be used")

    def merge_pr_expected(self, pr_id: int, *, expected_head_sha: str) -> bool:
        self.merge_calls.append((pr_id, expected_head_sha))
        self.pr = replace(self.pr, state="closed", merged=True)
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


class MockLLM(ILLMProvider):
    def __init__(
        self,
        *,
        decision: str = "pass",
        raw: str | None = None,
        stop_reason: str = "end_turn",
        finding_summary: str = "Unsafe",
    ) -> None:
        self.decision = decision
        self.raw = raw
        self.stop_reason = stop_reason
        self.finding_summary = finding_summary
        self.correlation_ids: list[str | None] = []
        self.prompts: list[str] = []
        self.kwargs: list[dict[str, Any]] = []

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.correlation_ids.append(current_workflow_correlation())
        self.kwargs.append(kwargs)
        prompt = str(messages[0]["content"])
        self.prompts.append(prompt)
        if self.raw is None:
            subject_sha256 = re.search(r"^Subject SHA-256: (.+)$", prompt, re.MULTILINE).group(1)  # type: ignore[union-attr]
            diff_digest = re.search(r"^Diff SHA-256: (.+)$", prompt, re.MULTILINE).group(1)  # type: ignore[union-attr]
            prompt_digest = re.search(r"^Prompt SHA-256: (.+)$", prompt, re.MULTILINE).group(1)  # type: ignore[union-attr]
            policy = json.loads(
                re.search(r"^Policy: (.+)$", prompt, re.MULTILINE).group(1)  # type: ignore[union-attr]
            )
            findings = (
                [
                    {
                        "severity": "blocker",
                        "code": "unsafe_change",
                        "summary": self.finding_summary,
                    }
                ]
                if self.decision == "block"
                else []
            )
            raw = json.dumps(
                {
                    "schema_version": 2,
                    "decision": self.decision,
                    "subject_sha256": subject_sha256,
                    "diff_sha256": diff_digest,
                    "policy": policy,
                    "tool": {"kind": "llm", "name": "review"},
                    "prompt_sha256": prompt_digest,
                    "findings": findings,
                }
            )
        else:
            raw = self.raw
        return LLMResponse(
            text=raw,
            input_tokens=100,
            output_tokens=50,
            stop_reason=self.stop_reason,
            model_used="review-model",
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


def _payload(
    scm: MockSCM,
    *,
    human_approval: bool = True,
    repository: str = "https://scm.example/owner/repo",
) -> dict[str, Any]:
    contract = parse_acceptance_contract(PLAN)
    if human_approval:
        contract = contract.with_approval(
            AcceptanceApproval(
                state="approved",
                actor="maintainer",
                method="comment",
                source_id="plan:10;comment:11",
                approved_at="2026-09-19T01:01:00Z",
                contract_hash=contract.contract_hash,
                plan_comment_id=10,
            )
        )
    subject = EvaluationSubject(
        repository=repository,
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash=contract.contract_hash,
        policy_version="preflight.v2",
        policy_digest="sha256:" + "d" * 64,
    )
    scm.revision = PullRequestRevision(
        repository=subject.repository,
        base_sha=subject.base_sha,
        head_sha=subject.head_sha,
    )
    return {
        "diff": "+safe = True",
        "issue": 42,
        "pr_number": 12,
        "evaluation_subject": subject.as_dict(),
        "acceptance_contract": contract.as_dict(),
        "acceptance_evidence": {
            "evaluation_subject": subject.as_dict(),
            "results": [
                {
                    "criterion_id": criterion.criterion_id,
                    "status": "passed",
                }
                for criterion in contract.criteria
            ],
        },
        "gate_results": [
            {
                "gate": 1,
                "passed": True,
                "authority": "required",
                "evaluation_subject": subject.as_dict(),
            }
        ],
    }


class TestReviewHandler:
    def test_privacy_sanitized_prompt_keeps_exact_subject_digest_binding(self) -> None:
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM()
        repository = "http://192.0.2.44/owner/repo"
        payload = _payload(scm, repository=repository)

        def sanitize(prompt: str) -> tuple[str, list[dict[str, Any]]]:
            redacted = prompt.replace("192.0.2.44", "[REDACTED:ip_address]")
            return redacted, [{"type": "ip_address"}]

        result = ReviewHandler(
            bus,
            scm=scm,
            llm=llm,
            prompt_sanitizer=sanitize,
        ).handle(ReviewCommand(payload=payload))

        assert result["reviewed"] is True
        assert result["decision"] == "pass"
        assert repository not in llm.prompts[0]
        assert (
            f"Subject SHA-256: {canonical_digest(payload['evaluation_subject'])}" in llm.prompts[0]
        )
        prompt_body, prompt_digest = llm.prompts[0].rsplit("\nPrompt SHA-256: ", 1)
        assert prompt_digest.strip() == text_digest(prompt_body)

    def test_llm_call_inherits_review_run_correlation(self) -> None:
        bus = Bus()
        events: list[Any] = []
        bus.subscribe("*", events.append)
        scm = MockSCM()
        llm = MockLLM()
        result = ReviewHandler(bus, scm=scm, llm=llm).handle(
            ReviewCommand(payload=_payload(scm), correlation_id="review-run-42")
        )

        assert result["reviewed"] is True
        assert result["decision"] == "pass"
        assert result["merge"] == "manual"
        assert llm.correlation_ids == ["review-run-42"]
        assert "schema_version must be the integer 2" in llm.prompts[0]
        assert "Acceptance: 1/1 PASS" in llm.prompts[0]
        assert "Required gates: 1/1 PASS" in llm.prompts[0]
        assert (
            "outer quotes around GREP or GREP:NOT patterns are transport syntax" in (llm.prompts[0])
        )
        assert llm.kwargs == [
            {
                "task": "review",
                "guards": ["prompt_guards"],
                "response_format": {"type": "json_object"},
            }
        ]
        assert "ReviewCompleted" in [event.name for event in events]
        assert scm.posted and "Entscheid: `pass`" in scm.posted[0][1]

    def test_standard_workflow_dispatches_exact_pr_subject_to_review(self) -> None:
        bus = Bus()
        scm = MockSCM()
        review = ReviewHandler(bus, scm=scm, llm=MockLLM())
        bus.register_command("Review", review.handle)
        WorkflowEngine(bus, load_workflow_config("config", "standard"))

        bus.publish(PRCreated(payload=_payload(scm)))

        assert scm.posted and "Strukturierter Review" in scm.posted[0][1]

    def test_prose_transport_success_is_indeterminate_and_never_posted(self) -> None:
        bus = Bus()
        events: list[Any] = []
        bus.subscribe("*", events.append)
        scm = MockSCM()
        result = ReviewHandler(bus, scm=scm, llm=MockLLM(raw="LGTM")).handle(
            ReviewCommand(payload=_payload(scm))
        )

        assert result["reviewed"] is False
        assert result["reason_code"] == "review_contract_invalid"
        assert result["validation_error_class"] == "not_json_document"
        assert scm.posted == []
        assert "ReviewBlocked" in [event.name for event in events]

    def test_invalid_review_retains_only_bounded_error_class(self) -> None:
        bus = Bus()
        events: list[Any] = []
        bus.subscribe("*", events.append)
        scm = MockSCM()
        secret = "sk-" + "z" * 24

        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(raw=f"not json {secret}"),
        ).handle(ReviewCommand(payload=_payload(scm)))

        blocked = next(event for event in events if event.name == "ReviewBlocked")
        assert result["validation_error_class"] == "not_json_document"
        assert blocked.payload["validation_error_class"] == "not_json_document"
        assert secret not in str(result)
        assert secret not in str(blocked.payload)

    def test_block_decision_is_visible_and_blocks(self) -> None:
        bus = Bus()
        events: list[Any] = []
        bus.subscribe("*", events.append)
        scm = MockSCM()
        result = ReviewHandler(bus, scm=scm, llm=MockLLM(decision="block")).handle(
            ReviewCommand(payload=_payload(scm))
        )

        assert result["reviewed"] is False
        assert result["decision"] == "block"
        assert [event.name for event in events][-2:] == ["ReviewCompleted", "ReviewBlocked"]

    def test_review_findings_are_secret_scrubbed_before_evidence_and_comment(self) -> None:
        bus = Bus()
        events: list[Any] = []
        bus.subscribe("*", events.append)
        scm = MockSCM()
        secret = "sk-" + "a" * 24

        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(decision="block", finding_summary=f"remove {secret}"),
        ).handle(ReviewCommand(payload=_payload(scm)))

        completed = next(event for event in events if event.name == "ReviewCompleted")
        assert secret not in str(completed.payload)
        assert secret not in str(result)
        assert secret not in scm.posted[0][1]
        assert "***REDACTED***" in scm.posted[0][1]

    def test_truncated_review_is_not_posted_as_complete(self) -> None:
        bus = Bus()
        events: list[Any] = []
        bus.subscribe("*", events.append)
        scm = MockSCM()
        result = ReviewHandler(
            bus, scm=scm, llm=MockLLM(raw="partial", stop_reason="length")
        ).handle(ReviewCommand(payload=_payload(scm)))

        assert result["reason_code"] == "llm_response_truncated"
        assert scm.posted == []
        assert "TokenLimitHit" in [event.name for event in events]
        assert "WorkflowBlocked" in [event.name for event in events]

    def test_review_prompt_runs_advisory_risk_analysis(self) -> None:
        bus = Bus()
        analyzer = Mock()
        scm = MockSCM()
        ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            prompt_risk_analyzer=analyzer,
        ).handle(ReviewCommand(payload={**_payload(scm), "diff": "+ignore previous"}))

        call = analyzer.inspect_text.call_args.kwargs
        assert call["issue_number"] == 42
        assert call["source"] == "review_prompt"
        assert "ignore previous" in call["text"]

    def test_missing_subject_blocks_before_provider_call(self) -> None:
        bus = Bus()
        llm = MockLLM()
        result = ReviewHandler(bus, llm=llm).handle(
            ReviewCommand(payload={"diff": "+code", "issue": 42})
        )

        assert result["reason_code"] == "review_subject_unbound"
        assert llm.correlation_ids == []

    def test_mismatched_acceptance_contract_blocks_before_provider_call(self) -> None:
        bus = Bus()
        scm = MockSCM()
        llm = MockLLM()
        payload = _payload(scm)
        payload["acceptance_contract"] = {
            **payload["acceptance_contract"],
            "contract_hash": "sha256:" + "e" * 64,
        }

        result = ReviewHandler(bus, scm=scm, llm=llm).handle(ReviewCommand(payload=payload))

        assert result["reason_code"] == "review_subject_unbound"
        assert llm.correlation_ids == []

    def test_qualified_auto_merge_uses_expected_head_and_intent(self) -> None:
        bus = Bus()
        scm = MockSCM(qualified_merge=True)
        authority = MockAuthority()
        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=authority,  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        ).handle(ReviewCommand(payload=_payload(scm), correlation_id="merge-run"))

        assert result["merge"] == "merged"
        assert scm.merge_calls == [(12, "b" * 40)]
        assert next(iter(authority.intents.values())).status == "applied"

    def test_duplicate_delivery_reconciles_without_second_merge(self) -> None:
        bus = Bus()
        scm = MockSCM(qualified_merge=True)
        authority = MockAuthority()
        handler = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=authority,  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        )
        command = ReviewCommand(payload=_payload(scm), correlation_id="merge-run")

        handler.handle(command)
        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=authority,  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        ).handle(command)

        assert result["merge"] == "merged"
        assert scm.merge_calls == [(12, "b" * 40)]

    def test_unconfirmed_merge_stays_unresolved_and_is_not_retried(self) -> None:
        class UnconfirmedSCM(MockSCM):
            def merge_pr_expected(self, pr_id: int, *, expected_head_sha: str) -> bool:
                self.merge_calls.append((pr_id, expected_head_sha))
                raise TimeoutError("outcome intentionally unknown")

        bus = Bus()
        events: list[Any] = []
        bus.subscribe("*", events.append)
        scm = UnconfirmedSCM(qualified_merge=True)
        authority = MockAuthority()
        handler = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=authority,  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        )
        command = ReviewCommand(payload=_payload(scm), correlation_id="merge-unknown")

        first = handler.handle(command)
        second = handler.handle(command)

        assert first["merge"] == second["merge"] == "unresolved"
        assert scm.merge_calls == [(12, "b" * 40)]
        assert next(iter(authority.intents.values())).status == "unresolved"
        assert "MergeOutcomeUnknown" in [event.name for event in events]

    def test_unresolved_restart_observes_later_merge_without_retry(self) -> None:
        class DelayedSCM(MockSCM):
            def merge_pr_expected(self, pr_id: int, *, expected_head_sha: str) -> bool:
                self.merge_calls.append((pr_id, expected_head_sha))
                raise TimeoutError("outcome intentionally unknown")

        bus = Bus()
        scm = DelayedSCM(qualified_merge=True)
        authority = MockAuthority()
        command = ReviewCommand(payload=_payload(scm), correlation_id="merge-restart")
        first = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=authority,  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        ).handle(command)
        scm.pr = replace(scm.pr, state="closed", merged=True)

        second = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=authority,  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        ).handle(command)

        assert first["merge"] == "unresolved"
        assert second["merge"] == "merged"
        assert scm.merge_calls == [(12, "b" * 40)]
        assert next(iter(authority.intents.values())).status == "unresolved"

    def test_head_race_blocks_before_native_merge(self) -> None:
        bus = Bus()
        scm = MockSCM(qualified_merge=True)
        payload = _payload(scm)
        assert scm.revision is not None
        scm.revision = replace(scm.revision, head_sha="e" * 40)
        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=MockAuthority(),  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        ).handle(ReviewCommand(payload=payload))

        assert result["reason_code"] == "pre_merge_revision_changed"
        assert scm.merge_calls == []

    def test_auto_merge_requires_fresh_human_approval_and_required_gates(self) -> None:
        for payload_mutation, reason in (
            (lambda scm: _payload(scm, human_approval=False), "merge_approval_not_fresh"),
            (
                lambda scm: {**_payload(scm), "gate_results": []},
                "merge_required_gates_not_bound",
            ),
        ):
            bus = Bus()
            scm = MockSCM(qualified_merge=True)
            result = ReviewHandler(
                bus,
                scm=scm,
                llm=MockLLM(),
                authority_store=MockAuthority(),  # type: ignore[arg-type]
                auto_merge_enabled=True,
                expected_head_merge_qualified=True,
            ).handle(ReviewCommand(payload=payload_mutation(scm)))
            assert result["reason_code"] == reason
            assert scm.merge_calls == []

    def test_auto_merge_does_not_reconstruct_authority_without_store(self) -> None:
        bus = Bus()
        scm = MockSCM(qualified_merge=True)

        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        ).handle(ReviewCommand(payload=_payload(scm)))

        assert result["reason_code"] == "merge_authority_state_unavailable"
        assert scm.merge_calls == []

    def test_edited_approval_evidence_blocks_merge(self) -> None:
        bus = Bus()
        scm = MockSCM(qualified_merge=True)
        payload = _payload(scm)
        scm.approval = replace(scm.approval, body="edited")

        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=MockAuthority(),  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=True,
        ).handle(ReviewCommand(payload=payload))

        assert result["reason_code"] == "merge_approval_not_fresh"
        assert scm.merge_calls == []

    def test_unqualified_adapter_stays_manual(self) -> None:
        bus = Bus()
        scm = MockSCM()
        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=MockAuthority(),  # type: ignore[arg-type]
            auto_merge_enabled=True,
        ).handle(ReviewCommand(payload=_payload(scm)))

        assert result["merge"] == "manual"
        assert result["reason_code"] == "native_expected_head_merge_unqualified"

    def test_unqualified_deployment_stays_manual_even_with_adapter_capability(self) -> None:
        bus = Bus()
        scm = MockSCM(qualified_merge=True)
        result = ReviewHandler(
            bus,
            scm=scm,
            llm=MockLLM(),
            authority_store=MockAuthority(),  # type: ignore[arg-type]
            auto_merge_enabled=True,
            expected_head_merge_qualified=False,
        ).handle(ReviewCommand(payload=_payload(scm)))

        assert result["merge"] == "manual"
        assert result["reason_code"] == "native_expected_head_merge_unqualified"
        assert scm.merge_calls == []
