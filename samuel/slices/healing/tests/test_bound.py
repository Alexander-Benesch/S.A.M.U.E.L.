from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.evaluation_observation import EvaluationObservationIdentity
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import Event, GateEvaluationCompleted
from samuel.core.issue_context import current_workflow_correlation
from samuel.core.ports import IConfig, ILLMProvider, IPromptRiskAnalyzer
from samuel.core.state import AuthorityWriteResult, HealingClaimRecord, StateStoreError
from samuel.core.types import LLMResponse
from samuel.slices.healing.bound import (
    BoundHealingCoordinator,
    classify_bound_healing,
)


class _Config(IConfig):
    def get(self, key: str, default: Any = None) -> Any:
        return default

    def feature_flag(self, name: str) -> bool:
        return name == "healing"

    def reload(self) -> None:
        pass


class _LLM(ILLMProvider):
    def __init__(self) -> None:
        self.calls = 0
        self.correlation_ids: list[str | None] = []
        self.prompts: list[str] = []

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        self.correlation_ids.append(current_workflow_correlation())
        self.prompts.append(str(messages[0]["content"]))
        return LLMResponse(
            text="patch suggestion",
            input_tokens=20,
            output_tokens=10,
            stop_reason="end_turn",
        )

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class _FailingLLM(_LLM):
    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        raise RuntimeError("provider unavailable")


class _TruncatedLLM(_LLM):
    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text="partial patch",
            input_tokens=20,
            output_tokens=10,
            stop_reason="max_tokens",
        )


class _FailingPromptRiskAnalyzer(IPromptRiskAnalyzer):
    def inspect_issue_text(
        self,
        *,
        issue_number: int,
        title: str,
        body: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        raise RuntimeError("advisory analyzer unavailable")

    def inspect_text(
        self,
        *,
        issue_number: int,
        source: str,
        text: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        raise RuntimeError("advisory analyzer unavailable")


class _Authority:
    def __init__(self, *, reconcile_required: bool = False) -> None:
        self.claims: dict[str, HealingClaimRecord] = {}
        self.epoch = 0
        self.reconcile_required = reconcile_required

    def authority_status(self) -> dict[str, Any]:
        return {
            "reconcile_required": self.reconcile_required,
            "epoch": self.epoch,
            "instance": "11111111-1111-4111-8111-111111111111",
        }

    def claim_healing(self, record: HealingClaimRecord) -> AuthorityWriteResult:
        if record.observation_key in self.claims:
            return AuthorityWriteResult(False, self.epoch)
        self.claims[record.observation_key] = record
        self.epoch += 1
        return AuthorityWriteResult(True, self.epoch)

    def finish_healing(
        self,
        observation_key: str,
        *,
        status: str,
        outcome: str | None = None,
        reason: str | None = None,
    ) -> AuthorityWriteResult:
        current = self.claims[observation_key]
        self.epoch += 1
        self.claims[observation_key] = HealingClaimRecord(
            observation_key=observation_key,
            issue_number=current.issue_number,
            correlation_id=current.correlation_id,
            status=status,  # type: ignore[arg-type]
            outcome=outcome,
            reason=reason,
        )
        return AuthorityWriteResult(True, self.epoch)


class _FailingFinishAuthority(_Authority):
    def finish_healing(
        self,
        observation_key: str,
        *,
        status: str,
        outcome: str | None = None,
        reason: str | None = None,
    ) -> AuthorityWriteResult:
        raise StateStoreError("state_write_failed", "healing finalization failed")


def _payload(
    *, status: str = "failed", evidence: Any = None, correlation_id: str = "active"
) -> dict[str, Any]:
    subject = {
        "repository": "owner/repo",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "contract_hash": "sha256:" + "c" * 64,
        "policy_version": "gates.v1",
        "policy_digest": "sha256:" + "d" * 64,
    }
    payload = {
        "issue": 399,
        "branch": "samuel/issue-399",
        "base": "main",
        "blocked": True,
        "observation_key": "sha256:" + "e" * 64,
        "evaluation_subject": subject,
        "gate_results": [
            {
                "gate": 11,
                "passed": False,
                "executed": True,
                "status": "failed",
                "reason_code": f"gate_11_{status}",
                "authority": "required",
                "evaluation_subject": subject,
            }
        ],
        "acceptance_evidence": {
            "evaluation_subject": subject,
            "contract": {
                "contract_hash": subject["contract_hash"],
                "approval": {
                    "state": "approved",
                    "source_id": "plan:7;label:event:8",
                    "plan_comment_id": 7,
                    "contract_hash": subject["contract_hash"],
                },
            },
            "results": [
                {
                    "criterion_id": "AC-1234",
                    "tag": "TEST",
                    "status": status,
                    "reason": "test failed",
                    "evidence": (
                        {
                            "schema_version": 1,
                            "kind": "test",
                            "test_name": "tests/test_feature.py::test_feature",
                            "runner": "pytest",
                            "exit_code": 1,
                        }
                        if evidence is None
                        else evidence
                    ),
                }
            ],
        },
        "workspace_id": "workspace-399",
        "evaluation_mode": "reference_worker",
        "mutation_authority": {
            "schema_version": 1,
            "authority": "mutate_candidate",
            "source": "approved_plan_workflow",
            "issue": 399,
            "plan_comment_id": 7,
            "contract_hash": subject["contract_hash"],
            "approval_source_id": "plan:7;label:event:8",
            "workspace_id": "workspace-399",
            "correlation_id": correlation_id,
        },
    }
    identity = EvaluationObservationIdentity.build(
        subject=EvaluationSubject.from_dict(subject),
        gate_results=payload["gate_results"],
        acceptance_evidence=payload["acceptance_evidence"],
    )
    payload["observation_schema_version"] = identity.schema_version
    payload["gate_result_schema_version"] = 2
    payload["observation_key"] = identity.observation_key
    payload["evidence_digest"] = identity.evidence_digest
    return payload


def _collect(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", events.append)
    return events


def test_classifier_only_accepts_one_automatic_failure_with_evidence() -> None:
    assert classify_bound_healing(_payload()).classification == "healable"
    assert classify_bound_healing(_payload(status="manual_pending")).reason == "manual_pending"
    assert classify_bound_healing(_payload(evidence={})).reason == "ambiguous_failed_criteria"
    assert (
        classify_bound_healing(_payload(evidence={"schema_version": 1, "kind": "test"})).reason
        == "ambiguous_failed_criteria"
    )

    multiple = _payload()
    multiple["gate_results"].append(
        {"gate": 9, "passed": False, "status": "failed", "authority": "required"}
    )
    assert classify_bound_healing(multiple).reason == "multiple_required_gate_failures"


def test_preflight_block_skips_healing_without_claim_or_llm() -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _LLM()
    authority = _Authority()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=authority,
    )
    payload = _payload()
    subject = EvaluationSubject.from_dict(payload["evaluation_subject"])
    payload["acceptance_evidence"] = None
    payload["gate_results"] = [
        {
            "gate": "7b",
            "passed": False,
            "executed": True,
            "status": "failed",
            "reason_code": "gate_7b_failed",
            "authority": "required",
            "evaluation_subject": subject.as_dict(),
        },
        {
            "gate": 11,
            "passed": None,
            "executed": False,
            "status": "skipped_precondition",
            "reason_code": "gate_11_skipped_precondition",
            "authority": "required",
            "evaluation_subject": subject.as_dict(),
        },
    ]
    identity = EvaluationObservationIdentity.build(
        subject=subject,
        gate_results=payload["gate_results"],
        acceptance_evidence=None,
    )
    payload["observation_schema_version"] = identity.schema_version
    payload["gate_result_schema_version"] = 2
    payload["observation_key"] = identity.observation_key
    payload["evidence_digest"] = identity.evidence_digest

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(payload=payload, correlation_id="preflight")
    )

    assert result["classification"] == "not_healable"
    assert result["reason"] == "gate_11_not_failed"
    assert llm.calls == 0
    assert authority.claims == {}
    blocked = next(event for event in events if event.name == "WorkflowBlocked")
    assert blocked.payload["reason"] == "bound_healing:gate_11_not_failed"


def test_coordinator_dispatches_once_for_duplicate_delivery(tmp_path) -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _LLM()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=_Authority(),
    )
    payload = _payload()
    payload["workspace_id"] = "run-workspace:sha256:" + "f" * 64
    payload["mutation_authority"]["workspace_id"] = payload["workspace_id"]
    event = GateEvaluationCompleted(payload=payload, correlation_id="active")

    first = coordinator.on_gate_evaluation(event)
    second = coordinator.on_gate_evaluation(event)

    assert first["dispatched"] is True
    assert second["dispatched"] is False
    assert llm.calls == 1
    assert "Korrekturrichtung fuer den Implementierungsagenten" in llm.prompts[0]
    assert "Erzeuge keinen Patch" in llm.prompts[0]
    assert "SEARCH/REPLACE" not in llm.prompts[0]
    suggestions = [event for event in events if event.name == "HealingSuggested"]
    assert len(suggestions) == 1
    assert suggestions[0].payload["resume_head_sha"] == "b" * 40
    assert suggestions[0].payload["workspace_id"] == payload["workspace_id"]
    assert suggestions[0].payload["healing_origin_observation_key"].startswith("sha256:")
    started = next(event for event in events if event.name == "HealingAttemptStarted")
    assert started.payload["authority_series"] == "authority.v2"
    assert started.payload["instance_uuid"] == "11111111-1111-4111-8111-111111111111"
    completed = next(event for event in events if event.name == "HealingAttemptCompleted")
    assert completed.payload["authority_series"] == "authority.v2"


def test_healable_failure_without_exact_mutation_authority_never_claims_or_calls_llm() -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _LLM()
    authority = _Authority()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=authority,
    )
    payload = _payload(correlation_id="passive")
    payload["evaluation_mode"] = "passive_submission"
    payload.pop("mutation_authority")

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(payload=payload, correlation_id="passive")
    )

    assert result["classification"] == "not_healable"
    assert result["reason"] == "mutation_authority_missing"
    assert llm.calls == 0
    assert authority.claims == {}
    assert not any(event.name in {"HealingAttemptStarted", "HealingSuggested"} for event in events)


def test_llm_call_inherits_bound_healing_run_correlation() -> None:
    bus = Bus()
    llm = _LLM()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=_Authority(),
    )

    coordinator.on_gate_evaluation(
        GateEvaluationCompleted(
            payload=_payload(correlation_id="healing-run-399"),
            correlation_id="healing-run-399",
        )
    )

    assert llm.correlation_ids == ["healing-run-399"]


def test_second_failed_head_routes_terminal_without_another_attempt(tmp_path) -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _LLM()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=_Authority(),
    )
    payload = _payload()
    payload["healing_origin_observation_key"] = "sha256:" + "1" * 64

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(payload=payload, correlation_id="retry")
    )

    assert result["reason"] == "repeated_failure"
    assert llm.calls == 0
    assert not any(event.name == "HealingSuggested" for event in events)
    blocked = next(event for event in events if event.name == "WorkflowBlocked")
    assert blocked.payload["reason"] == "bound_healing:repeated_failure"


def test_invalid_observation_never_triggers_active_healing(tmp_path) -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _LLM()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=_Authority(),
    )
    payload = _payload()
    payload["observation_key"] = "sha256:" + "0" * 64

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(payload=payload, correlation_id="tampered")
    )

    assert result["classification"] == "not_healable"
    assert result["reason"] == "invalid_bound_observation"
    assert llm.calls == 0
    assert not any(event.name == "HealingSuggested" for event in events)
    blocked = next(event for event in events if event.name == "WorkflowBlocked")
    assert blocked.payload["reason"] == "bound_healing:invalid_bound_observation"


def test_reconcile_blocks_before_claim_and_llm() -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _LLM()
    authority = _Authority(reconcile_required=True)
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=authority,
    )

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(
            payload=_payload(correlation_id="reconcile"), correlation_id="reconcile"
        )
    )

    assert result["reason"] == "authority_reconcile_required"
    assert llm.calls == 0
    assert authority.claims == {}
    blocked = next(event for event in events if event.name == "WorkflowBlocked")
    assert blocked.payload["reason"] == "bound_healing:authority_reconcile_required"


def test_provider_failure_counts_the_started_domain_attempt() -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _FailingLLM()
    authority = _Authority()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=authority,
    )

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(
            payload=_payload(correlation_id="provider-error"),
            correlation_id="provider-error",
        )
    )

    assert result["reason"] == "llm_error"
    assert llm.calls == 1
    assert [event.name for event in events].count("HealingAttemptStarted") == 1
    aborted = next(event for event in events if event.name == "HealingAborted")
    assert aborted.payload["attempts_used"] == 1
    assert aborted.payload["total_tokens"] == 0
    claim = next(iter(authority.claims.values()))
    assert claim.status == "attempted"
    assert claim.outcome == "llm_error"


def test_pre_attempt_block_keeps_attempt_count_at_zero() -> None:
    bus = Bus()
    events = _collect(bus)
    authority = _Authority()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=None,
        config=_Config(),
        authority_store=authority,
    )

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(payload=_payload(correlation_id="no-llm"), correlation_id="no-llm")
    )

    assert result["reason"] == "no_llm"
    assert not any(event.name == "HealingAttemptStarted" for event in events)
    aborted = next(event for event in events if event.name == "HealingAborted")
    assert aborted.payload["attempts_used"] == 0
    assert aborted.payload["total_tokens"] == 0
    assert authority.claims == {}


def test_truncated_response_preserves_known_attempt_tokens() -> None:
    bus = Bus()
    events = _collect(bus)
    authority = _Authority()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=_TruncatedLLM(),
        config=_Config(),
        authority_store=authority,
    )

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(
            payload=_payload(correlation_id="truncated"), correlation_id="truncated"
        )
    )

    assert result["reason"] == "llm_response_truncated"
    aborted = next(event for event in events if event.name == "HealingAborted")
    assert aborted.payload["attempts_used"] == 1
    assert aborted.payload["total_tokens"] == 30


def test_finish_failure_still_counts_the_started_attempt() -> None:
    bus = Bus()
    events = _collect(bus)
    coordinator = BoundHealingCoordinator(
        bus,
        llm=_LLM(),
        config=_Config(),
        authority_store=_FailingFinishAuthority(),
    )

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(
            payload=_payload(correlation_id="finish-error"), correlation_id="finish-error"
        )
    )

    assert result["reason"] == "attempt_store_error"
    aborted = next(event for event in events if event.name == "HealingAborted")
    assert aborted.payload["attempts_used"] == 1
    assert aborted.payload["total_tokens"] == 30


def test_advisory_prompt_risk_failure_does_not_strand_claim() -> None:
    bus = Bus()
    events = _collect(bus)
    llm = _LLM()
    authority = _Authority()
    coordinator = BoundHealingCoordinator(
        bus,
        llm=llm,
        config=_Config(),
        authority_store=authority,
        prompt_risk_analyzer=_FailingPromptRiskAnalyzer(),
    )

    result = coordinator.on_gate_evaluation(
        GateEvaluationCompleted(
            payload=_payload(correlation_id="advisory-error"),
            correlation_id="advisory-error",
        )
    )

    assert result["dispatched"] is True
    assert llm.calls == 1
    assert any(event.name == "HealingAttemptCompleted" for event in events)
    assert not any(event.name == "HealingAborted" for event in events)
    claim = next(iter(authority.claims.values()))
    assert claim.status == "attempted"
    assert claim.outcome == "suggested"
