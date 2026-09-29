"""Evidence-bound healing coordinator for the gate-authority workflow."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Literal

from samuel.core.acceptance import only_manual_acceptance_pending
from samuel.core.bus import Bus
from samuel.core.evaluation_observation import validate_completed_observation
from samuel.core.events import (
    Event,
    HealingAborted,
    HealingAttemptCompleted,
    HealingAttemptStarted,
    HealingClassified,
    HealingSuggested,
    TokenLimitHit,
    WorkflowBlocked,
)
from samuel.core.issue_context import issue_scope
from samuel.core.ports import IAuthorityStateStore, IConfig, ILLMProvider, IPromptRiskAnalyzer
from samuel.core.security_policy import PROMPT_GUARD_MARKERS
from samuel.core.state import HealingClaimRecord, StateStoreError, authority_event_binding
from samuel.core.types import is_truncated_stop_reason

Classification = Literal["healable", "not_healable", "not_needed", "waiting"]
log = logging.getLogger(__name__)

_AUTOMATIC_EVIDENCE_KINDS = {
    "DIFF": "diff",
    "EXISTS": "exists",
    "IMPORT": "import",
    "GREP": "grep",
    "GREP:NOT": "grep:not",
    "TEST": "test",
}


@dataclass(frozen=True)
class BoundHealingClassification:
    classification: Classification
    reason: str
    failed_criteria: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_bound_healing(payload: dict[str, Any]) -> BoundHealingClassification:
    if not payload.get("blocked"):
        return BoundHealingClassification("not_needed", "required_gates_passed")
    if payload.get("manual_pending") is True and only_manual_acceptance_pending(
        payload.get("gate_results", []), payload.get("acceptance_evidence")
    ):
        return BoundHealingClassification("waiting", "manual_pending")
    if payload.get("healing_origin_observation_key"):
        return BoundHealingClassification("not_healable", "repeated_failure")
    gate_results = payload.get("gate_results")
    if not isinstance(gate_results, list):
        return BoundHealingClassification("not_healable", "missing_gate_results")
    required_failures = [
        item
        for item in gate_results
        if isinstance(item, dict)
        and item.get("authority") == "required"
        and item.get("passed") is False
    ]
    gate_11 = [item for item in required_failures if item.get("gate") == 11]
    if len(gate_11) != 1 or gate_11[0].get("passed") is not False:
        return BoundHealingClassification("not_healable", "gate_11_not_failed")
    if len(required_failures) != 1:
        return BoundHealingClassification("not_healable", "multiple_required_gate_failures")
    acceptance = payload.get("acceptance_evidence")
    results = acceptance.get("results") if isinstance(acceptance, dict) else None
    if not isinstance(results, list):
        return BoundHealingClassification("not_healable", "missing_acceptance_evidence")

    blocked_statuses = {"manual_pending", "missing_evidence", "error", "not_applicable"}
    for item in results:
        if not isinstance(item, dict):
            return BoundHealingClassification("not_healable", "invalid_acceptance_evidence")
        status = item.get("status")
        if status in blocked_statuses:
            return BoundHealingClassification("not_healable", str(status))

    failed = tuple(
        item
        for item in results
        if item.get("status") == "failed"
        and item.get("tag") != "MANUAL"
        and _has_actionable_automatic_evidence(item)
    )
    all_failed = [item for item in results if item.get("status") == "failed"]
    if len(failed) != 1 or len(all_failed) != 1:
        return BoundHealingClassification("not_healable", "ambiguous_failed_criteria")
    return BoundHealingClassification("healable", "single_automatic_failure", failed)


def _has_actionable_automatic_evidence(result: dict[str, Any]) -> bool:
    """Reject arbitrary dictionaries that are not verifier evidence."""

    tag = str(result.get("tag", ""))
    evidence = result.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
        return False
    if evidence.get("kind") != _AUTOMATIC_EVIDENCE_KINDS.get(tag):
        return False
    required_fields = {
        "DIFF": ("path", "changed"),
        "EXISTS": ("path", "exists"),
        "IMPORT": ("module", "importable"),
        "GREP": ("pattern", "found"),
        "GREP:NOT": ("pattern", "absent"),
        "TEST": ("test_name", "runner", "exit_code"),
    }.get(tag, ())
    return bool(required_fields) and all(field in evidence for field in required_fields)


def _mutation_authority_reason(payload: dict[str, Any], correlation_id: str) -> str | None:
    """Validate the exact workflow grant before any claim or provider call."""

    if payload.get("evaluation_mode") != "reference_worker":
        return "mutation_authority_missing"
    authority = payload.get("mutation_authority")
    subject = payload.get("evaluation_subject")
    acceptance = payload.get("acceptance_evidence")
    contract = acceptance.get("contract") if isinstance(acceptance, dict) else None
    approval = contract.get("approval") if isinstance(contract, dict) else None
    if not all(isinstance(value, dict) for value in (authority, subject, contract, approval)):
        return "mutation_authority_missing"
    assert isinstance(authority, dict)
    assert isinstance(subject, dict)
    assert isinstance(contract, dict)
    assert isinstance(approval, dict)
    workspace_id = payload.get("workspace_id")
    expected = {
        "schema_version": 1,
        "authority": "mutate_candidate",
        "source": "approved_plan_workflow",
        "issue": payload.get("issue"),
        "plan_comment_id": approval.get("plan_comment_id"),
        "contract_hash": subject.get("contract_hash"),
        "approval_source_id": approval.get("source_id"),
        "workspace_id": workspace_id,
        "correlation_id": correlation_id,
    }
    if authority != expected:
        return "mutation_authority_invalid"
    if (
        approval.get("state") != "approved"
        or contract.get("contract_hash") != subject.get("contract_hash")
        or approval.get("contract_hash") != subject.get("contract_hash")
        or not isinstance(workspace_id, str)
        or not workspace_id
        or workspace_id != workspace_id.strip()
        or not correlation_id
    ):
        return "mutation_authority_invalid"
    return None


class BoundHealingCoordinator:
    def __init__(
        self,
        bus: Bus,
        *,
        llm: ILLMProvider | None,
        config: IConfig | None,
        authority_store: IAuthorityStateStore | None = None,
        prompt_risk_analyzer: IPromptRiskAnalyzer | None = None,
    ) -> None:
        self._bus = bus
        self._llm = llm
        self._config = config
        self._prompt_risk_analyzer = prompt_risk_analyzer
        self._authority = authority_store

    def register(self) -> None:
        self._bus.subscribe("GateEvaluationCompleted", self.on_gate_evaluation)

    def on_gate_evaluation(self, event: Event) -> dict[str, Any]:
        payload = event.payload or {}
        issue = int(payload.get("issue", 0))
        observation_key = str(payload.get("observation_key", ""))
        try:
            validate_completed_observation(payload)
        except ValueError:
            log.exception("Bound healing rejected an invalid gate observation")
            classification = BoundHealingClassification("not_healable", "invalid_bound_observation")
        else:
            classification = classify_bound_healing(payload)
        if classification.classification == "healable":
            authority_reason = _mutation_authority_reason(payload, event.correlation_id)
            if authority_reason is not None:
                classification = BoundHealingClassification("not_healable", authority_reason)
        classified_payload = {
            "issue": issue,
            "cat": "workflow",
            "evt": "healing_classified",
            "observation_key": observation_key,
            "dry_run": False,
            **classification.as_dict(),
        }
        self._bus.publish(
            HealingClassified(payload=classified_payload, correlation_id=event.correlation_id)
        )
        if classification.classification == "waiting":
            return classified_payload
        if classification.classification != "healable":
            if payload.get("blocked"):
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue,
                            "reason": f"bound_healing:{classification.reason}",
                            "observation_key": observation_key,
                        },
                        correlation_id=event.correlation_id,
                    )
                )
            return classified_payload
        if self._config is None or not self._config.feature_flag("healing"):
            return self._block(issue, observation_key, "disabled", event.correlation_id)
        if self._llm is None:
            return self._block(issue, observation_key, "no_llm", event.correlation_id)
        if self._authority is None:
            return self._block(
                issue, observation_key, "authority_store_unavailable", event.correlation_id
            )
        try:
            authority_status = self._authority.authority_status()
            if authority_status.get("reconcile_required"):
                return self._block(
                    issue, observation_key, "authority_reconcile_required", event.correlation_id
                )
            claim_result = self._authority.claim_healing(
                HealingClaimRecord(
                    observation_key=observation_key,
                    issue_number=issue,
                    correlation_id=event.correlation_id,
                )
            )
            claimed = bool(observation_key) and claim_result.changed
        except StateStoreError:
            return self._block(issue, observation_key, "attempt_store_error", event.correlation_id)
        if not claimed:
            return {**classified_payload, "dispatched": False, "reason": "already_claimed"}

        criterion = classification.failed_criteria[0]
        self._bus.publish(
            HealingAttemptStarted(
                payload={
                    "issue": issue,
                    "evt": "healing_attempt_started",
                    "attempt": 1,
                    "max_attempts": 1,
                    "failure_type": "acceptance_evidence",
                    "observation_key": observation_key,
                    "criterion_id": criterion.get("criterion_id"),
                    **authority_event_binding(
                        self._authority.authority_status(),
                        authority_epoch=claim_result.authority_epoch,
                    ),
                },
                correlation_id=event.correlation_id,
            )
        )
        prompt = _build_bound_heal_prompt(criterion)
        if self._prompt_risk_analyzer is not None:
            try:
                self._prompt_risk_analyzer.inspect_text(
                    issue_number=issue,
                    source="bound_healing_prompt",
                    text=prompt,
                    correlation_id=event.correlation_id,
                )
            except Exception as exc:  # noqa: BLE001 - advisory analysis must not strand claim
                log.warning("Prompt-risk analysis failed for bound healing #%d: %s", issue, exc)
        try:
            with issue_scope(
                issue,
                event.correlation_id,
                event.payload.get("budget_admission_key"),
            ):
                response = self._llm.complete(
                    [{"role": "user", "content": prompt}],
                    task="healing",
                    guards=["prompt_guards", "bound_acceptance_evidence", "single_attempt"],
                )
        except Exception:  # noqa: BLE001 - provider failures become terminal workflow evidence
            log.exception("Bound healing provider failed; routing to terminal block")
            return self._finish_and_block(issue, observation_key, "llm_error", event.correlation_id)
        tokens_used = response.input_tokens + response.output_tokens
        max_tokens = int(self._config.get("healing.max_tokens", 50_000) if self._config else 50_000)
        if tokens_used > max_tokens or is_truncated_stop_reason(response.stop_reason):
            reason = (
                "token_budget_exhausted" if tokens_used > max_tokens else "llm_response_truncated"
            )
            if reason == "llm_response_truncated":
                self._bus.publish(
                    TokenLimitHit(
                        payload={"issue": issue, "task": "healing", "reason": reason},
                        correlation_id=event.correlation_id,
                    )
                )
            return self._finish_and_block(
                issue,
                observation_key,
                reason,
                event.correlation_id,
                total_tokens=tokens_used,
            )

        try:
            finish_result = self._authority.finish_healing(
                observation_key,
                status="attempted",
                outcome="suggested",
            )
        except StateStoreError:
            return self._block(
                issue,
                observation_key,
                "attempt_store_error",
                event.correlation_id,
                attempts_used=1,
                total_tokens=tokens_used,
            )
        self._bus.publish(
            HealingAttemptCompleted(
                payload={
                    "issue": issue,
                    "evt": "healing_attempt_completed",
                    "attempt": 1,
                    "max_attempts": 1,
                    "tokens_used": tokens_used,
                    "status": "evidence_suggestion_created",
                    "observation_key": observation_key,
                    "criterion_id": criterion.get("criterion_id"),
                    **authority_event_binding(
                        self._authority.authority_status(),
                        authority_epoch=finish_result.authority_epoch,
                    ),
                },
                correlation_id=event.correlation_id,
            )
        )
        subject = payload["evaluation_subject"]
        approval = payload.get("acceptance_evidence", {}).get("contract", {}).get("approval")
        suggestion_payload = {
            "issue": issue,
            "evt": "healing_suggested",
            "attempt": 1,
            "suggestion": response.text,
            "heal_hint": _healing_hint(criterion, response.text),
            "failure_type": "acceptance_evidence",
            "branch": payload.get("branch", ""),
            "base": payload.get("base", "main"),
            "resume_head_sha": subject["head_sha"],
            "evaluation_subject": subject,
            **({"workspace_id": payload["workspace_id"]} if "workspace_id" in payload else {}),
            "healing_origin_observation_key": observation_key,
            "failed_criterion": criterion,
        }
        if isinstance(approval, dict):
            suggestion_payload["acceptance_approval"] = approval
        self._bus.publish(
            HealingSuggested(payload=suggestion_payload, correlation_id=event.correlation_id)
        )
        return {**classified_payload, "dispatched": True, "tokens_used": tokens_used}

    def _finish_and_block(
        self,
        issue: int,
        observation_key: str,
        outcome: str,
        correlation_id: str,
        *,
        total_tokens: int = 0,
    ) -> dict[str, Any]:
        assert self._authority is not None
        try:
            result = self._authority.finish_healing(
                observation_key,
                status="attempted",
                outcome=outcome,
            )
        except StateStoreError:
            return self._block(
                issue,
                observation_key,
                "attempt_store_error",
                correlation_id,
                attempts_used=1,
                total_tokens=total_tokens,
            )
        return self._block(
            issue,
            observation_key,
            outcome,
            correlation_id,
            authority_epoch=result.authority_epoch,
            attempts_used=1,
            total_tokens=total_tokens,
        )

    def _block(
        self,
        issue: int,
        observation_key: str,
        reason: str,
        correlation_id: str,
        authority_epoch: int | None = None,
        *,
        attempts_used: int = 0,
        total_tokens: int = 0,
    ) -> dict[str, Any]:
        aborted_payload: dict[str, Any] = {
            "issue": issue,
            "evt": "healing_aborted",
            "reason": reason,
            "attempts_used": attempts_used,
            "total_tokens": total_tokens,
            "observation_key": observation_key,
        }
        if authority_epoch is not None:
            assert self._authority is not None
            aborted_payload.update(
                authority_event_binding(
                    self._authority.authority_status(),
                    authority_epoch=authority_epoch,
                )
            )
        self._bus.publish(
            HealingAborted(
                payload=aborted_payload,
                correlation_id=correlation_id,
            )
        )
        self._bus.publish(
            WorkflowBlocked(
                payload={
                    "issue": issue,
                    "reason": f"bound_healing:{reason}",
                    "observation_key": observation_key,
                },
                correlation_id=correlation_id,
            )
        )
        return {"classification": "not_healable", "reason": reason, "dispatched": False}


def _build_bound_heal_prompt(criterion: dict[str, Any]) -> str:
    evidence = json.dumps(criterion.get("evidence"), ensure_ascii=False, sort_keys=True)
    return (
        f"{PROMPT_GUARD_MARKERS[0]}\n{PROMPT_GUARD_MARKERS[1]}\n\n"
        "# Gebundener Healing-Versuch\n\n"
        f"Kriterium: {criterion.get('criterion_id')} [{criterion.get('tag')}]\n"
        f"Grund: {criterion.get('reason', '')}\n"
        f"Evidence: {evidence}\n\n"
        "Beschreibe knapp die belegte Ursache und genau eine konkrete, minimale "
        "Korrekturrichtung fuer den Implementierungsagenten. Erzeuge keinen Patch und "
        "keine Befehle. Beziehe dich nur auf die genannte Evidence."
    )


def _healing_hint(criterion: dict[str, Any], suggestion: str) -> str:
    return (
        "## Gebundene Acceptance-Evidence\n"
        f"- Kriterium: {criterion.get('criterion_id')} [{criterion.get('tag')}]\n"
        f"- Status: {criterion.get('status')}\n"
        f"- Grund: {criterion.get('reason', '')}\n\n"
        "## Einmaliger Korrekturvorschlag\n"
        f"{suggestion}"
    )
