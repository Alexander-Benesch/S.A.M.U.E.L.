"""Persisted dispatch/reconcile state machine for external verification."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.ports import IAuthorityStateStore, IExecutionProvider
from samuel.core.state import AuthorityRecord, OperationIntentRecord, WorkflowCheckpointRecord
from samuel.core.types import (
    ExecutionProviderError,
    ProviderDispatchResult,
    ProviderEvidence,
    ProviderRunReference,
    VerificationAuthority,
    VerificationCriterion,
    VerificationProgress,
    VerificationRequest,
)

REQUEST_RECORD_KIND = "verification_request.v1"
DISPATCH_OPERATION = "provider_dispatch.v1"
log = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("verification time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("provider evidence timestamp lacks a timezone")
    return parsed.astimezone(timezone.utc)


def _validated_consumer_context(
    consumer_mode: str,
    value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    allowed = (
        {"head_sha"}
        if consumer_mode == "passive_candidate"
        else {
            "branch",
            "base",
            "workspace_id",
            "healing_origin_observation_key",
            "acceptance_approval",
        }
    )
    if set(value) - allowed:
        raise ValueError("provider consumer context contains unsupported fields")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("provider consumer context must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > 16_384:
        raise ValueError("provider consumer context exceeds the bounded state contract")
    return dict(value)


class ProviderVerificationCoordinator:
    """Coordinate one provider effect without turning retries into new work."""

    def __init__(
        self,
        *,
        provider: IExecutionProvider,
        authority_store: IAuthorityStateStore,
        provider_profile: str,
        provider_profile_digest: str,
        clock: Callable[[], datetime] = _utc_now,
        nonce_factory: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self._provider = provider
        self._authority = authority_store
        self._provider_profile = provider_profile
        self._provider_profile_digest = provider_profile_digest
        self._clock = clock
        self._nonce_factory = nonce_factory

    @staticmethod
    def _checkpoint_key(request_key: str) -> str:
        return f"provider:{request_key}"

    @staticmethod
    def _intent_key(request_key: str) -> str:
        return f"dispatch:{request_key}"

    @staticmethod
    def _same_authority(
        request: VerificationRequest,
        *,
        subject: EvaluationSubject,
        authority: VerificationAuthority,
        criteria: tuple[VerificationCriterion, ...],
        policy_binding: dict[str, Any],
        provider_profile: str,
        provider_profile_digest: str,
        consumer_mode: str,
    ) -> bool:
        return (
            request.subject == subject
            and request.authority == authority
            and request.criteria == criteria
            and request.policy_binding == policy_binding
            and request.provider_profile == provider_profile
            and request.provider_profile_digest == provider_profile_digest
            and request.consumer_mode == consumer_mode
        )

    def _matching_request(
        self,
        *,
        subject: EvaluationSubject,
        authority: VerificationAuthority,
        criteria: tuple[VerificationCriterion, ...],
        policy_binding: dict[str, Any],
        consumer_mode: str,
    ) -> VerificationRequest | None:
        for record in reversed(self._authority.list_authority_records()):
            if record.kind != REQUEST_RECORD_KIND:
                continue
            try:
                request = VerificationRequest.from_dict(record.payload)
            except (TypeError, ValueError):
                continue
            if self._same_authority(
                request,
                subject=subject,
                authority=authority,
                criteria=criteria,
                policy_binding=policy_binding,
                provider_profile=self._provider_profile,
                provider_profile_digest=self._provider_profile_digest,
                consumer_mode=consumer_mode,
            ):
                return request
        return None

    def request(
        self,
        *,
        subject: EvaluationSubject,
        authority: VerificationAuthority,
        criteria: tuple[VerificationCriterion, ...],
        policy_binding: dict[str, Any],
        correlation_id: str,
        new_request: bool = False,
        consumer_mode: Literal["passive_candidate", "reference_worker"] = "passive_candidate",
        consumer_context: dict[str, Any] | None = None,
    ) -> VerificationProgress:
        """Create one request, or recover the existing exact request.

        ``new_request`` is the explicit operator action that allows another
        provider execution for an otherwise identical subject.  Ordinary
        retries always recover the already persisted request.
        """

        consumer_context = _validated_consumer_context(consumer_mode, consumer_context)
        existing = self._matching_request(
            subject=subject,
            authority=authority,
            criteria=criteria,
            policy_binding=policy_binding,
            consumer_mode=consumer_mode,
        )
        if existing is not None and not new_request:
            return self.advance(existing.request_key)

        now = self._clock()
        request = VerificationRequest.build(
            request_nonce=self._nonce_factory(),
            authorized_at=_timestamp(now),
            subject=subject,
            authority=authority,
            criteria=criteria,
            policy_binding=policy_binding,
            provider_profile=self._provider_profile,
            provider_profile_digest=self._provider_profile_digest,
            consumer_mode=consumer_mode,
        )
        self._authority.put_authority_record(
            AuthorityRecord(
                record_key=request.request_key,
                kind=REQUEST_RECORD_KIND,
                payload=request.as_dict(),
            )
        )
        intent_key = self._intent_key(request.request_key)
        self._authority.put_intent(
            OperationIntentRecord(
                intent_key=intent_key,
                operation=DISPATCH_OPERATION,
                status="pending",
                issue_number=authority.issue_number,
                correlation_id=correlation_id,
                subject_key=request.request_key,
                payload={
                    "request_key": request.request_key,
                    "provider_profile": self._provider_profile,
                    "provider_profile_digest": self._provider_profile_digest,
                    "repository": subject.repository,
                    "base_sha": subject.base_sha,
                    "head_sha": subject.head_sha,
                    "recovery_authority": "request_key",
                },
            )
        )
        self._put_checkpoint(
            request,
            correlation_id=correlation_id,
            boundary="provider_dispatch_pending",
            reference=None,
            reason_code="dispatch_not_confirmed",
            resume_eligible=True,
            consumer_context=consumer_context,
        )
        try:
            result = self._provider.dispatch(request)
        except Exception as exc:  # noqa: BLE001 - ambiguous external effect remains recoverable
            log.warning(
                "Provider dispatch outcome is unknown for %s (%s)",
                request.request_key,
                type(exc).__name__,
            )
            self._put_checkpoint(
                request,
                correlation_id=correlation_id,
                boundary="provider_dispatch_unknown",
                reference=None,
                reason_code="dispatch_outcome_unknown",
                resume_eligible=True,
                consumer_context=consumer_context,
            )
            return VerificationProgress(
                request=request,
                status="dispatch_unknown",
                reason_code="dispatch_outcome_unknown",
            )
        return self._apply_dispatch_result(
            request,
            result,
            correlation_id=correlation_id,
            consumer_context=consumer_context,
        )

    def advance(self, request_key: str) -> VerificationProgress:
        record = self._authority.get_authority_record(request_key)
        if record is None or record.kind != REQUEST_RECORD_KIND:
            raise ExecutionProviderError(
                "verification_request_missing",
                "Verification request is not present in authoritative state",
            )
        request = VerificationRequest.from_dict(record.payload)
        checkpoint = self._authority.get_checkpoint(self._checkpoint_key(request_key))
        if checkpoint is None:
            raise ExecutionProviderError(
                "verification_checkpoint_missing",
                "Verification request has no recovery checkpoint",
            )
        if checkpoint.evaluation_subject != request.subject.as_dict():
            raise ExecutionProviderError(
                "verification_checkpoint_mismatch",
                "Verification checkpoint differs from its immutable request",
            )
        reference = self._checkpoint_reference(checkpoint)
        if checkpoint.boundary == "provider_evidence_ready":
            raw_evidence = checkpoint.payload.get("evidence")
            if not isinstance(raw_evidence, dict):
                raise ExecutionProviderError(
                    "provider_evidence_missing",
                    "Evidence-ready checkpoint contains no provider evidence",
                )
            stored_evidence = ProviderEvidence.from_dict(raw_evidence)
            self._validate_evidence(request, stored_evidence)
            return VerificationProgress(
                request=request,
                status="evidence_ready",
                reason_code="provider_evidence_ready",
                reference=stored_evidence.reference,
                evidence=stored_evidence,
            )
        if checkpoint.boundary == "provider_terminal_blocked":
            return VerificationProgress(
                request=request,
                status="blocked",
                reason_code=str(checkpoint.payload.get("reason_code") or "provider_failed"),
                reference=reference,
            )
        if checkpoint.boundary in {"provider_completed", "provider_failed"}:
            return VerificationProgress(
                request=request,
                status="blocked",
                reason_code=str(
                    checkpoint.payload.get("reason_code")
                    or "provider_verification_already_consumed"
                ),
                reference=reference,
            )

        if reference is None:
            try:
                result = self._provider.reconcile(request, None)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Provider dispatch reconciliation is unknown for %s (%s)",
                    request.request_key,
                    type(exc).__name__,
                )
                return VerificationProgress(
                    request=request,
                    status="dispatch_unknown",
                    reason_code="dispatch_reconcile_unknown",
                )
            progress = self._apply_dispatch_result(
                request,
                result,
                correlation_id=checkpoint.correlation_id,
                consumer_context=(
                    checkpoint.payload.get("consumer_context")
                    if isinstance(checkpoint.payload.get("consumer_context"), dict)
                    else None
                ),
            )
            if progress.reference is None or progress.status == "blocked":
                return progress
            reference = progress.reference

        try:
            evidence = self._provider.read_evidence(request, reference)
        except ExecutionProviderError as exc:
            self._terminal_block(
                request,
                checkpoint.correlation_id,
                reference,
                reason_code=exc.code,
            )
            return VerificationProgress(
                request=request,
                status="blocked",
                reason_code=exc.code,
                reference=reference,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Provider evidence status is temporarily unknown for %s (%s)",
                request.request_key,
                type(exc).__name__,
            )
            return VerificationProgress(
                request=request,
                status="running",
                reason_code="provider_result_unknown",
                reference=reference,
            )
        if evidence is None:
            self._put_checkpoint(
                request,
                correlation_id=checkpoint.correlation_id,
                boundary="provider_running",
                reference=reference,
                reason_code="provider_run_pending",
                resume_eligible=True,
                consumer_context=(
                    checkpoint.payload.get("consumer_context")
                    if isinstance(checkpoint.payload.get("consumer_context"), dict)
                    else None
                ),
            )
            return VerificationProgress(
                request=request,
                status="running",
                reason_code="provider_run_pending",
                reference=reference,
            )
        try:
            self._validate_evidence(request, evidence)
        except (TypeError, ValueError, ExecutionProviderError) as exc:
            code = (
                exc.code if isinstance(exc, ExecutionProviderError) else "provider_evidence_invalid"
            )
            self._terminal_block(
                request,
                checkpoint.correlation_id,
                reference,
                reason_code=code,
            )
            return VerificationProgress(
                request=request,
                status="blocked",
                reason_code=code,
                reference=reference,
            )
        self._put_checkpoint(
            request,
            correlation_id=checkpoint.correlation_id,
            boundary="provider_evidence_ready",
            reference=reference,
            reason_code="provider_evidence_ready",
            resume_eligible=True,
            evidence=evidence,
            consumer_context=(
                checkpoint.payload.get("consumer_context")
                if isinstance(checkpoint.payload.get("consumer_context"), dict)
                else None
            ),
        )
        return VerificationProgress(
            request=request,
            status="evidence_ready",
            reason_code="provider_evidence_ready",
            reference=reference,
            evidence=evidence,
        )

    def acknowledge(self, request_key: str, *, outcome: str) -> None:
        """Mark gate consumption terminal without deleting recovery evidence."""

        if outcome not in {"completed", "failed"}:
            raise ValueError("provider verification outcome is invalid")
        request_record = self._authority.get_authority_record(request_key)
        checkpoint = self._authority.get_checkpoint(self._checkpoint_key(request_key))
        if request_record is None or checkpoint is None:
            raise ExecutionProviderError(
                "verification_request_missing",
                "Verification request cannot be acknowledged",
            )
        request = VerificationRequest.from_dict(request_record.payload)
        if checkpoint.boundary != "provider_evidence_ready":
            raise ExecutionProviderError(
                "provider_evidence_not_ready",
                "Provider evidence is not ready for terminal acknowledgement",
            )
        self._put_checkpoint(
            request,
            correlation_id=checkpoint.correlation_id,
            boundary=f"provider_{outcome}",
            reference=self._checkpoint_reference(checkpoint),
            reason_code=f"provider_verification_{outcome}",
            resume_eligible=False,
            evidence=(
                ProviderEvidence.from_dict(checkpoint.payload["evidence"])
                if isinstance(checkpoint.payload.get("evidence"), dict)
                else None
            ),
            consumer_context=(
                checkpoint.payload.get("consumer_context")
                if isinstance(checkpoint.payload.get("consumer_context"), dict)
                else None
            ),
        )

    def _apply_dispatch_result(
        self,
        request: VerificationRequest,
        result: ProviderDispatchResult,
        *,
        correlation_id: str,
        consumer_context: dict[str, Any] | None = None,
    ) -> VerificationProgress:
        if result.state == "accepted":
            assert result.reference is not None
            if result.reference.request_key != request.request_key:
                return self._terminal_block(
                    request,
                    correlation_id,
                    None,
                    reason_code="dispatch_request_mismatch",
                )
            intent = self._authority.get_intent(self._intent_key(request.request_key))
            if intent is not None and intent.status == "pending":
                self._authority.finish_intent(
                    intent.intent_key,
                    status="applied",
                    postcondition={
                        "request_key": request.request_key,
                        "provider": result.reference.provider,
                        "repository": result.reference.repository,
                        "run_id": result.reference.run_id,
                        "attempt": result.reference.attempt,
                        "verification_complete": False,
                    },
                )
            self._put_checkpoint(
                request,
                correlation_id=correlation_id,
                boundary="provider_running",
                reference=result.reference,
                reason_code="provider_run_pending",
                resume_eligible=True,
                consumer_context=consumer_context,
            )
            return VerificationProgress(
                request=request,
                status="running",
                reason_code="provider_run_pending",
                reference=result.reference,
            )
        if result.state == "unknown":
            self._put_checkpoint(
                request,
                correlation_id=correlation_id,
                boundary="provider_dispatch_unknown",
                reference=None,
                reason_code=result.reason_code,
                resume_eligible=True,
                consumer_context=consumer_context,
            )
            return VerificationProgress(
                request=request,
                status="dispatch_unknown",
                reason_code=result.reason_code,
            )
        intent = self._authority.get_intent(self._intent_key(request.request_key))
        if intent is not None and intent.status == "pending":
            self._authority.finish_intent(
                intent.intent_key,
                status="failed" if result.state == "rejected" else "mismatch",
                postcondition={
                    "request_key": request.request_key,
                    "external_effect": False,
                    "absence_proven": result.state == "proven_absent",
                    "reason_code": result.reason_code,
                },
            )
        return self._terminal_block(
            request,
            correlation_id,
            None,
            reason_code=result.reason_code,
            consumer_context=consumer_context,
        )

    def _terminal_block(
        self,
        request: VerificationRequest,
        correlation_id: str,
        reference: ProviderRunReference | None,
        *,
        reason_code: str,
        consumer_context: dict[str, Any] | None = None,
    ) -> VerificationProgress:
        self._put_checkpoint(
            request,
            correlation_id=correlation_id,
            boundary="provider_terminal_blocked",
            reference=reference,
            reason_code=reason_code,
            resume_eligible=False,
            consumer_context=consumer_context,
        )
        return VerificationProgress(
            request=request,
            status="blocked",
            reason_code=reason_code,
            reference=reference,
        )

    def _put_checkpoint(
        self,
        request: VerificationRequest,
        *,
        correlation_id: str,
        boundary: str,
        reference: ProviderRunReference | None,
        reason_code: str,
        resume_eligible: bool,
        evidence: ProviderEvidence | None = None,
        consumer_context: dict[str, Any] | None = None,
    ) -> None:
        self._authority.put_checkpoint(
            WorkflowCheckpointRecord(
                checkpoint_key=self._checkpoint_key(request.request_key),
                issue_number=request.authority.issue_number,
                correlation_id=correlation_id,
                workflow="provider_verification",
                boundary=boundary,
                repository=request.subject.repository,
                branch=request.subject.head_sha,
                base_ref=request.subject.base_sha,
                head_sha=request.subject.head_sha,
                workspace_id="",
                evaluation_subject=request.subject.as_dict(),
                resume_eligible=resume_eligible,
                payload={
                    "schema": "provider-verification-checkpoint.v1",
                    "request_key": request.request_key,
                    "reason_code": reason_code,
                    "mutation_authority": "none",
                    "consumer_mode": request.consumer_mode,
                    **(
                        {"consumer_context": dict(consumer_context)}
                        if consumer_context is not None
                        else {}
                    ),
                    **({"reference": reference.as_dict()} if reference is not None else {}),
                    **({"evidence": evidence.as_dict()} if evidence is not None else {}),
                },
            )
        )

    @staticmethod
    def _checkpoint_reference(
        checkpoint: WorkflowCheckpointRecord,
    ) -> ProviderRunReference | None:
        value = checkpoint.payload.get("reference")
        return ProviderRunReference.from_dict(value) if isinstance(value, dict) else None

    def _validate_evidence(
        self,
        request: VerificationRequest,
        evidence: ProviderEvidence,
    ) -> None:
        if evidence.request_key != request.request_key:
            raise ExecutionProviderError(
                "provider_request_mismatch", "Provider evidence belongs to another request"
            )
        if evidence.subject != request.subject:
            raise ExecutionProviderError(
                "provider_subject_mismatch", "Provider evidence belongs to another subject"
            )
        if evidence.provider_profile_digest != request.provider_profile_digest:
            raise ExecutionProviderError(
                "provider_profile_mismatch", "Provider evidence used another trust profile"
            )
        if evidence.nonce != request.request_nonce:
            raise ExecutionProviderError(
                "provider_replay_detected", "Provider evidence nonce differs from the request"
            )
        expected = {(item.criterion_id, item.tag) for item in request.criteria}
        observed = {(item.criterion_id, item.tag) for item in evidence.criteria}
        if observed != expected:
            raise ExecutionProviderError(
                "provider_criteria_mismatch", "Provider evidence does not cover exact criteria"
            )
        try:
            authorized_at = _parse_timestamp(request.authorized_at)
            issued_at = _parse_timestamp(evidence.issued_at)
            expires_at = _parse_timestamp(evidence.expires_at)
        except ValueError as exc:
            raise ExecutionProviderError(
                "provider_freshness_invalid", "Provider evidence timestamps are invalid"
            ) from exc
        if issued_at < authorized_at or expires_at <= issued_at or self._clock() > expires_at:
            raise ExecutionProviderError(
                "provider_freshness_invalid", "Provider evidence is stale or pre-dates authority"
            )
