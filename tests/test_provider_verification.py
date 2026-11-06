from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.types import (
    ProviderCriterionEvidence,
    ProviderDispatchResult,
    ProviderEvidence,
    ProviderRunReference,
    VerificationAuthority,
    VerificationCriterion,
    canonical_digest,
)
from samuel.slices.provider_verification.coordinator import ProviderVerificationCoordinator

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


class Provider:
    def __init__(self) -> None:
        self.dispatches = 0
        self.reconciles = 0
        self.reads = 0
        self.dispatch_error = False
        self.reconcile_result = ProviderDispatchResult(
            state="unknown", reason_code="run_not_yet_attributable"
        )
        self.evidence: ProviderEvidence | None = None

    def dispatch(self, request):
        self.dispatches += 1
        if self.dispatch_error:
            raise TimeoutError("response lost")
        return ProviderDispatchResult(
            state="accepted",
            reference=ProviderRunReference(
                provider="fixture",
                repository="owner/repo",
                run_id="71",
                attempt=1,
                request_key=request.request_key,
            ),
        )

    def reconcile(self, request, reference):
        self.reconciles += 1
        return self.reconcile_result

    def read_evidence(self, request, reference):
        self.reads += 1
        return self.evidence


@pytest.fixture
def binding():
    subject = EvaluationSubject(
        repository="https://scm.example/owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="1",
        policy_digest="sha256:" + "d" * 64,
    )
    authority = VerificationAuthority(
        issue_number=71,
        plan_comment_id=42536,
        contract_hash=subject.contract_hash,
        approval_source_id="label-event:9",
        approval_actor="maintainer",
        approval_method="scm_label_timeline",
    )
    criteria = (
        VerificationCriterion(
            criterion_id="ac-1",
            tag="TEST",
            text="tests/test_demo.py::test_pipeline",
        ),
    )
    policy = {"policy_version": "1", "policy_digest": subject.policy_digest}
    profile_digest = canonical_digest({"profile": "fixture-v1"})
    return subject, authority, criteria, policy, profile_digest


def coordinator(tmp_path: Path, provider: Provider) -> ProviderVerificationCoordinator:
    state = SQLiteStateStore(tmp_path / "state")
    return ProviderVerificationCoordinator(
        provider=provider,
        authority_store=state.authority,
        provider_profile="fixture-v1",
        provider_profile_digest=canonical_digest({"profile": "fixture-v1"}),
        clock=lambda: NOW,
        nonce_factory=lambda: "nonce-1",
    )


def start(coordinator, binding, **kwargs):
    subject, authority, criteria, policy, _profile_digest = binding
    return coordinator.request(
        subject=subject,
        authority=authority,
        criteria=criteria,
        policy_binding=policy,
        correlation_id="corr-1",
        **kwargs,
    )


def evidence_for(progress, binding) -> ProviderEvidence:
    subject, _authority, criteria, _policy, profile_digest = binding
    assert progress.reference is not None
    return ProviderEvidence(
        request_key=progress.request.request_key,
        subject=subject,
        reference=progress.reference,
        provider_profile_digest=profile_digest,
        workflow_digest="sha256:" + "1" * 64,
        tool_digest="sha256:" + "2" * 64,
        environment_digest="sha256:" + "3" * 64,
        issuer="fixture-control-plane",
        issued_at=(NOW + timedelta(seconds=1)).isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        nonce=progress.request.request_nonce,
        criteria=(
            ProviderCriterionEvidence(
                criterion_id=criteria[0].criterion_id,
                tag=criteria[0].tag,
                status="passed",
                reason="trusted fixture passed",
                evidence_digest="sha256:" + "4" * 64,
            ),
        ),
        integrity={"scheme": "fixture", "verified": True},
    )


def test_dispatch_is_persisted_before_effect_and_duplicate_recovers(tmp_path, binding):
    state = SQLiteStateStore(tmp_path / "state")

    class InspectingProvider(Provider):
        def dispatch(self, request):
            assert state.authority.get_authority_record(request.request_key) is not None
            intent = state.authority.get_intent(f"dispatch:{request.request_key}")
            checkpoint = state.authority.get_checkpoint(f"provider:{request.request_key}")
            assert intent is not None and intent.status == "pending"
            assert checkpoint is not None and checkpoint.boundary == "provider_dispatch_pending"
            return super().dispatch(request)

    provider = InspectingProvider()
    service = ProviderVerificationCoordinator(
        provider=provider,
        authority_store=state.authority,
        provider_profile="fixture-v1",
        provider_profile_digest=canonical_digest({"profile": "fixture-v1"}),
        clock=lambda: NOW,
        nonce_factory=lambda: "nonce-1",
    )

    first = start(service, binding)
    second = start(service, binding)

    assert first.status == "running"
    assert second.status == "running"
    assert second.request.request_key == first.request.request_key
    assert provider.dispatches == 1
    assert provider.reads == 1


def test_dispatch_response_loss_before_notation_reconciles_without_second_post(tmp_path, binding):
    provider = Provider()
    state = SQLiteStateStore(tmp_path / "state")
    authority = state.authority
    original_finish = authority.finish_intent
    failures = 1

    def fail_once(*args, **kwargs):
        nonlocal failures
        if failures:
            failures -= 1
            raise RuntimeError("crash before response notation")
        return original_finish(*args, **kwargs)

    authority.finish_intent = fail_once  # type: ignore[method-assign]
    service = ProviderVerificationCoordinator(
        provider=provider,
        authority_store=authority,
        provider_profile="fixture-v1",
        provider_profile_digest=canonical_digest({"profile": "fixture-v1"}),
        clock=lambda: NOW,
        nonce_factory=lambda: "nonce-1",
    )

    with pytest.raises(RuntimeError, match="response notation"):
        start(service, binding)
    record = authority.list_authority_records()[-1]
    provider.reconcile_result = ProviderDispatchResult(
        state="accepted",
        reference=ProviderRunReference(
            provider="fixture",
            repository="owner/repo",
            run_id="71",
            attempt=1,
            request_key=record.record_key,
        ),
    )

    recovered = start(service, binding)

    assert recovered.status == "running"
    assert provider.dispatches == 1
    assert provider.reconciles == 1


def test_lost_dispatch_response_reconciles_same_request_without_second_post(tmp_path, binding):
    provider = Provider()
    provider.dispatch_error = True
    service = coordinator(tmp_path, provider)

    first = start(service, binding)
    provider.dispatch_error = False
    provider.reconcile_result = ProviderDispatchResult(
        state="accepted",
        reference=ProviderRunReference(
            provider="fixture",
            repository="owner/repo",
            run_id="99",
            attempt=1,
            request_key=first.request.request_key,
        ),
    )
    recovered = start(service, binding)

    assert first.status == "dispatch_unknown"
    assert recovered.status == "running"
    assert recovered.reference is not None and recovered.reference.run_id == "99"
    assert provider.dispatches == 1
    assert provider.reconciles == 1


def test_ambiguous_absence_never_redispatches(tmp_path, binding):
    provider = Provider()
    provider.dispatch_error = True
    service = coordinator(tmp_path, provider)

    first = start(service, binding)
    second = start(service, binding)

    assert first.status == second.status == "dispatch_unknown"
    assert second.reason_code == "run_not_yet_attributable"
    assert provider.dispatches == 1
    assert provider.reconciles == 1


def test_bound_evidence_survives_until_gate_acknowledgement(tmp_path, binding):
    provider = Provider()
    service = coordinator(tmp_path, provider)
    running = start(service, binding)
    provider.evidence = evidence_for(running, binding)

    ready = service.advance(running.request.request_key)
    replay = service.advance(running.request.request_key)

    assert ready.status == replay.status == "evidence_ready"
    assert ready.evidence == provider.evidence
    assert provider.reads == 1
    service.acknowledge(running.request.request_key, outcome="completed")
    checkpoint = service._authority.get_checkpoint(  # noqa: SLF001 - state contract assertion
        service._checkpoint_key(running.request.request_key)  # noqa: SLF001
    )
    assert checkpoint is not None
    assert checkpoint.boundary == "provider_completed"
    assert checkpoint.resume_eligible is False
    consumed = service.advance(running.request.request_key)
    assert consumed.status == "blocked"
    assert consumed.reason_code == "provider_verification_completed"
    assert provider.reads == 1


def test_stale_or_wrong_request_evidence_blocks_fail_closed(tmp_path, binding):
    provider = Provider()
    service = coordinator(tmp_path, provider)
    running = start(service, binding)
    good = evidence_for(running, binding)
    provider.evidence = ProviderEvidence(
        **{
            **good.__dict__,
            "nonce": "replayed-nonce",
        }
    )

    result = service.advance(running.request.request_key)

    assert result.status == "blocked"
    assert result.reason_code == "provider_replay_detected"


def test_explicit_new_request_creates_new_effect_identity(tmp_path, binding):
    provider = Provider()
    nonces = iter(("nonce-1", "nonce-2"))
    state = SQLiteStateStore(tmp_path / "state")
    service = ProviderVerificationCoordinator(
        provider=provider,
        authority_store=state.authority,
        provider_profile="fixture-v1",
        provider_profile_digest=canonical_digest({"profile": "fixture-v1"}),
        clock=lambda: NOW,
        nonce_factory=lambda: next(nonces),
    )

    first = start(service, binding)
    second = start(service, binding, new_request=True)

    assert first.request.request_key != second.request.request_key
    assert provider.dispatches == 2


def test_consumer_context_rejects_unbounded_fields_before_dispatch(tmp_path, binding):
    provider = Provider()
    service = coordinator(tmp_path, provider)

    with pytest.raises(ValueError, match="unsupported fields"):
        start(
            service,
            binding,
            consumer_context={"token": "must-not-enter-authority-state"},
        )

    assert provider.dispatches == 0
