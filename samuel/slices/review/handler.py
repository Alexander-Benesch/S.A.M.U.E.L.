from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from samuel.core.acceptance import (
    ACCEPTANCE_STATUSES,
    AcceptanceContract,
    PlanApprovalAuthorityError,
    latest_active_plan,
    resolve_plan_approval,
)
from samuel.core.bus import Bus, scrub_secrets
from samuel.core.commands import Command, ReviewCommand
from samuel.core.config import GateParametersSchema
from samuel.core.errors import ProviderUnavailable
from samuel.core.evaluation_observation import EvaluationObservationIdentity
from samuel.core.evaluation_subject import EvaluationSubject, PullRequestRevision
from samuel.core.events import (
    Event,
    MergeOutcomeUnknown,
    PRMerged,
    ReviewBlocked,
    ReviewCompleted,
    TokenLimitHit,
    WorkflowBlocked,
)
from samuel.core.issue_context import issue_scope
from samuel.core.ports import (
    IAuthorityStateStore,
    ILLMProvider,
    IObservationStore,
    IPromptRiskAnalyzer,
    IVersionControl,
)
from samuel.core.review import (
    ReviewDecision,
    classify_review_contract_error,
    parse_review_decision,
    render_change_context,
    text_digest,
)
from samuel.core.security_policy import PROMPT_GUARD_MARKERS
from samuel.core.state import OperationIntentRecord, StateStoreError
from samuel.core.types import canonical_digest, is_truncated_stop_reason

log = logging.getLogger(__name__)


class ReviewHandler:
    def __init__(
        self,
        bus: Bus,
        scm: IVersionControl | None = None,
        llm: ILLMProvider | None = None,
        prompt_risk_analyzer: IPromptRiskAnalyzer | None = None,
        prompt_sanitizer: Callable[[str], tuple[str, list[dict[str, Any]]]] | None = None,
        *,
        authority_store: IAuthorityStateStore | None = None,
        observation_store: IObservationStore | None = None,
        auto_merge_enabled: bool = False,
        expected_head_merge_qualified: bool = False,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._llm = llm
        self._prompt_risk_analyzer = prompt_risk_analyzer
        self._prompt_sanitizer = prompt_sanitizer
        self._authority = authority_store
        self._observations = observation_store
        self._auto_merge_enabled = auto_merge_enabled
        self._expected_head_merge_qualified = expected_head_merge_qualified

    def observe_merge(self, event: Event) -> None:
        """Project a native merge against the durable candidate, never request a merge."""
        payload = event.payload or {}
        number = payload.get("number")
        if (
            self._authority is None
            or self._scm is None
            or payload.get("source") not in {"webhook", "polling"}
            or type(number) is not int
            or number <= 0
        ):
            return
        try:
            intents = [
                intent
                for intent in self._authority.list_intents(status="applied")
                if intent.operation == "create_pr"
                and intent.postcondition.get("pr_number") == number
                and intent.payload.get("repository") == self._scm.repository_identity
            ]
            if len(intents) != 1:
                return
            intent = intents[0]
            raw_subject = intent.payload.get("evaluation_subject")
            if not isinstance(raw_subject, dict):
                return
            subject = EvaluationSubject.from_dict(raw_subject)
            pr = self._scm.get_pr(number)
            revision = self._scm.get_pr_revision(number)
            # The base branch moves on merge. Compare the immutable candidate
            # head, not the now-advanced base, to the original bound subject.
            if (
                not pr.merged
                or pr.number != number
                or revision.repository != subject.repository
                or revision.head_sha != subject.head_sha
                or intent.payload.get("head_sha") != subject.head_sha
                or intent.postcondition.get("head_sha") != subject.head_sha
                or intent.payload.get("repository") != subject.repository
                or intent.payload.get("base_sha") != subject.base_sha
                or intent.postcondition.get("base_sha") != subject.base_sha
            ):
                return
            self._bus.publish(
                PRMerged(
                    payload={
                        "issue": intent.issue_number,
                        "pr_number": number,
                        "evaluation_subject": subject.as_dict(),
                        "actor": payload.get("actor", ""),
                        "actor_type": payload.get("actor_type", ""),
                        "source": payload["source"],
                        "cat": "scm",
                        "evt": "native_merge_confirmed",
                        "idempotency_key": f"native_merge_observation:{intent.intent_key}",
                    },
                    correlation_id=intent.correlation_id,
                )
            )
            self._post_merge_summary(intent.issue_number, number, subject)
            self._post_change_summary(intent.issue_number, number, subject)
        except Exception as exc:
            # SCM response/error text may contain credentials or payloads.
            log.warning("Native merge observation deferred (%s)", type(exc).__name__)

    def _post_merge_summary(
        self, issue_number: int, pr_number: int, subject: EvaluationSubject
    ) -> None:
        scm = self._scm
        if scm is None:
            return
        marker = f"<!-- samuel-merged:{canonical_digest(subject.as_dict())}:{pr_number} -->"
        try:
            comments = scm.get_comments(issue_number)
            if any(marker in comment.body for comment in comments):
                return
            issue = scm.get_issue(issue_number)
            title = scrub_secrets(" ".join(issue.title.split()))
            lines = [
                f"## Entwicklungsabschluss für Issue #{issue_number}",
                "",
                f"Auftrag: {title}",
                f"PR #{pr_number} wurde im SCM als gemergt bestätigt.",
                f"Candidate: `{subject.head_sha}`",
                f"Contract: `{subject.contract_hash}`",
            ]
            active = latest_active_plan(comments)
            if active is not None and active[1].contract_hash == subject.contract_hash:
                lines.extend(["", "Freigegebener Umfang dieses Candidates:"])
                statuses = self._merge_acceptance_statuses(
                    issue_number, subject, active[1], active[0].id
                )
                labels = {"passed": "PASS", "manual_pending": "MANUAL offen"}
                for criterion in active[1].criteria:
                    description = scrub_secrets(" ".join(criterion.text.split()))
                    status = statuses.get(criterion.criterion_id, "unknown")
                    checked = "x" if status == "passed" else " "
                    label = labels.get(status, status.upper())
                    lines.append(
                        f"- [{checked}] [{criterion.tag}] {description} — "
                        f"{label} (`{criterion.criterion_id}`)"
                    )
                lines.append(
                    "Checkboxen zeigen nur den gebundenen Kriteriennachweis, keine Issuefreigabe."
                )
            lines.extend(
                [
                    "",
                    "Der Development-Hauptpfad endet hier. Der Merge ist kein Golden-/D0-Nachweis "
                    "und schließt das Issue nicht automatisch; dessen eigener Restumfang bleibt maßgeblich.",
                    marker,
                ]
            )
            scm.post_comment(issue_number, "\n".join(lines))
        except Exception as exc:
            log.warning(
                "Merge summary unavailable for issue #%d (%s)", issue_number, type(exc).__name__
            )

    def _merge_acceptance_statuses(
        self,
        issue_number: int,
        subject: EvaluationSubject,
        contract: AcceptanceContract,
        plan_comment_id: int,
    ) -> dict[str, str]:
        """Read immutable candidate evidence; a merge is never a substitute."""
        if self._observations is None:
            return {}
        try:
            records = self._observations.list_observations(issue_number)
            for record in reversed(records):
                payload = record.payload
                if (
                    record.issue_number != issue_number
                    or record.evidence_origin != "bound_acceptance_evidence"
                    or record.subject_key != canonical_digest(subject.as_dict())
                    or payload.get("evaluation_subject") != subject.as_dict()
                ):
                    continue
                evidence = payload.get("acceptance_evidence")
                if (
                    not isinstance(evidence, dict)
                    or evidence.get("evaluation_subject") != subject.as_dict()
                ):
                    return {}
                observed_contract = AcceptanceContract.from_dict(evidence.get("contract", {}))
                if (
                    observed_contract.contract_hash != contract.contract_hash
                    or observed_contract.criteria != contract.criteria
                    or observed_contract.approval.state != "approved"
                    or observed_contract.approval.plan_comment_id != plan_comment_id
                ):
                    return {}
                identity = EvaluationObservationIdentity.build(
                    subject=subject,
                    gate_results=payload["gate_results"],
                    acceptance_evidence=evidence,
                    schema_version=payload["schema_version"],
                )
                if (
                    record.observation_schema != f"bound.v{identity.schema_version}"
                    or record.observation_key != identity.observation_key
                    or record.evidence_digest != identity.evidence_digest
                    or payload.get("observation_key") != identity.observation_key
                    or payload.get("evidence_digest") != identity.evidence_digest
                ):
                    return {}
                results = evidence.get("results")
                if not isinstance(results, list) or any(
                    not isinstance(row, dict) for row in results
                ):
                    return {}
                expected = {
                    criterion.criterion_id: criterion.tag for criterion in contract.criteria
                }
                statuses: dict[str, str] = {}
                for row in results:
                    criterion_id = row.get("criterion_id")
                    if criterion_id not in expected or criterion_id in statuses:
                        return {}
                    status = row.get("status")
                    statuses[criterion_id] = (
                        status
                        if status in ACCEPTANCE_STATUSES
                        and row.get("tag") == expected[criterion_id]
                        else "unknown"
                    )
                return statuses
        except Exception as exc:
            log.warning("Merge acceptance evidence unavailable (%s)", type(exc).__name__)
        return {}

    def _post_change_summary(
        self, issue_number: int, pr_number: int, subject: EvaluationSubject
    ) -> None:
        """Explain the actual immutable change separately from workflow evidence."""
        scm = self._scm
        if scm is None:
            return
        marker = f"<!-- samuel-change:{canonical_digest(subject.as_dict())}:{pr_number} -->"
        try:
            comments = scm.get_comments(issue_number)
            if any(marker in comment.body for comment in comments):
                return
            active = latest_active_plan(comments)
            if active is None or active[1].contract_hash != subject.contract_hash:
                return
            comparison = scm.compare_commits(
                subject.base_sha,
                subject.head_sha,
                max_diff_bytes=GateParametersSchema().max_diff_bytes,
            )
            issue = scm.get_issue(issue_number)
            explanation = render_change_context(
                title=issue.title, context=issue.body, comparison=comparison, subject=subject
            )
            lines = [
                f"## Fachliche Änderung für Issue #{issue_number}",
                "",
                explanation,
                "",
                f"PR #{pr_number}.",
                "Dieser Änderungskommentar ist eine Erklärung; die S.A.M.U.E.L.-Nachweise "
                "stehen separat im Entwicklungsabschluss.",
                marker,
            ]
            scm.post_comment(issue_number, "\n".join(lines))
        except Exception as exc:
            log.warning(
                "Change summary unavailable for issue #%d (%s)", issue_number, type(exc).__name__
            )

    @staticmethod
    def _bound_prompt(
        *,
        diff: str,
        subject: EvaluationSubject,
        acceptance_contract: AcceptanceContract,
        acceptance_evidence: object,
        gate_results: object,
        diff_digest: str,
        prompt_sanitizer: Callable[[str], tuple[str, list[dict[str, Any]]]] | None = None,
    ) -> tuple[str, str]:
        review_contract = acceptance_contract.as_dict()
        review_contract.pop("approval", None)
        review_contract.pop("source_snapshot", None)
        review_contract.pop("clarification_basis", None)
        subject_sha256 = canonical_digest(subject.as_dict())
        acceptance_status = ReviewHandler._acceptance_status(
            acceptance_evidence,
            acceptance_contract,
            subject,
        )
        gate_status = ReviewHandler._required_gate_status(gate_results, subject)
        prompt = (
            f"{PROMPT_GUARD_MARKERS[0]}\n"
            f"{PROMPT_GUARD_MARKERS[1]}\n\n"
            "# Bound code review\n\n"
            "Inspect the exact diff for correctness, security, maintainability, and the "
            "approved acceptance contract. Return exactly one JSON object and no Markdown.\n\n"
            "Allowed top-level fields are schema_version, decision, subject_sha256, "
            "diff_sha256, "
            "policy, tool, prompt_sha256, findings. decision is pass, block, or "
            "indeterminate. schema_version must be the integer 2. Each finding has "
            "exactly severity (blocker or suggestion), "
            "code (lower snake case), and summary. pass cannot contain a blocker; block "
            "needs at least one blocker.\n\n"
            f"Subject SHA-256: {subject_sha256}\n"
            "Pre-review verification for this exact subject:\n"
            f"- Acceptance: {acceptance_status}\n"
            f"- Required gates: {gate_status}\n\n"
            "Interpret acceptance patterns semantically. Markdown inline-code delimiters "
            "and the outer quotes around GREP or GREP:NOT patterns are transport syntax; "
            "they are not source bytes unless the pattern itself explicitly contains them.\n\n"
            f"Acceptance contract: {json.dumps(review_contract, sort_keys=True)}\n"
            f"Diff SHA-256: {diff_digest}\n"
            f"Policy: {json.dumps({'version': subject.policy_version, 'digest': subject.policy_digest}, sort_keys=True)}\n"
            'Tool: {"kind":"llm","name":"review"}\n\n'
            f"## Exact diff\n{diff}"
        )
        if prompt_sanitizer is not None:
            prompt, _ = prompt_sanitizer(prompt)
        prompt_digest = text_digest(prompt)
        return f"{prompt}\nPrompt SHA-256: {prompt_digest}\n", prompt_digest

    @staticmethod
    def _acceptance_status(
        acceptance_evidence: object,
        contract: AcceptanceContract,
        subject: EvaluationSubject,
    ) -> str:
        total = len(contract.criteria)
        if not isinstance(acceptance_evidence, dict):
            return "unavailable (do not infer PASS)"
        if acceptance_evidence.get("evaluation_subject") != subject.as_dict():
            return "unavailable (subject binding mismatch)"
        results = acceptance_evidence.get("results")
        if not isinstance(results, list):
            return "unavailable (results missing)"
        expected = {criterion.criterion_id for criterion in contract.criteria}
        passed = {
            row.get("criterion_id")
            for row in results
            if isinstance(row, dict) and row.get("status") == "passed"
        }
        if passed == expected and len(results) == total:
            return f"{total}/{total} PASS"
        return f"{len(passed & expected)}/{total} NOT VERIFIED"

    @staticmethod
    def _required_gate_status(gate_results: object, subject: EvaluationSubject) -> str:
        if not isinstance(gate_results, list):
            return "unavailable (do not infer PASS)"
        required = [
            row
            for row in gate_results
            if isinstance(row, dict) and row.get("authority") == "required"
        ]
        if not required:
            return "unavailable (required results missing)"
        passed = sum(
            row.get("passed") is True and row.get("evaluation_subject") == subject.as_dict()
            for row in required
        )
        if passed == len(required):
            return f"{passed}/{len(required)} PASS"
        return f"{passed}/{len(required)} NOT VERIFIED"

    def _blocked(
        self,
        *,
        issue_number: int,
        correlation_id: str,
        reason_code: str,
        pr_number: int = 0,
        subject: EvaluationSubject | None = None,
        decision: str = "indeterminate",
        validation_error_class: str | None = None,
        provider_error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "issue": issue_number,
            "pr_number": pr_number,
            "decision": decision,
            "reason_code": reason_code,
            "reason": reason_code,
            "cat": "workflow",
            "evt": "review_blocked",
            "lvl": "warn",
        }
        if subject is not None:
            payload["evaluation_subject"] = subject.as_dict()
        if validation_error_class is not None:
            payload["validation_error_class"] = validation_error_class
        if provider_error is not None:
            payload["provider_error"] = provider_error
        self._bus.publish(ReviewBlocked(payload=payload, correlation_id=correlation_id))
        return {"reviewed": False, **payload}

    @staticmethod
    def _revision_matches(revision: PullRequestRevision, subject: EvaluationSubject) -> bool:
        return (
            revision.repository == subject.repository
            and revision.base_sha == subject.base_sha
            and revision.head_sha == subject.head_sha
        )

    def _fresh_human_approval(
        self,
        *,
        issue_number: int,
        subject: EvaluationSubject,
        supplied_contract: AcceptanceContract,
    ) -> bool:
        assert self._scm is not None
        comments = self._scm.get_comments(issue_number)
        active = latest_active_plan(comments)
        if active is None:
            return False
        plan, current_contract = active
        approval = supplied_contract.approval
        if (
            (plan.updated_at and plan.updated_at != plan.created_at)
            or current_contract.contract_hash != supplied_contract.contract_hash
            or current_contract.contract_hash != subject.contract_hash
            or approval.state != "approved"
            or approval.contract_hash != current_contract.contract_hash
            or approval.plan_comment_id != plan.id
            or approval.actor == "samuel:planning-policy"
            or not approval.actor
        ):
            return False
        if self._authority is None or not callable(
            getattr(self._authority, "get_authority_record", None)
        ):
            return False
        try:
            resolved = resolve_plan_approval(
                self._authority,
                scm=self._scm,
                repository=subject.repository,
                issue_number=issue_number,
                plan_comment=plan,
                contract=current_contract,
                comments=comments,
                supplied=approval.as_dict(),
                expected_base_sha=subject.base_sha,
            )
        except PlanApprovalAuthorityError:
            return False
        return resolved == approval

    @staticmethod
    def _required_gates_passed(gate_results: object, subject: EvaluationSubject) -> bool:
        if not isinstance(gate_results, list) or not gate_results:
            return False
        required = [
            row
            for row in gate_results
            if isinstance(row, dict) and row.get("authority") == "required"
        ]
        return bool(required) and all(
            row.get("passed") is True and row.get("evaluation_subject") == subject.as_dict()
            for row in required
        )

    @staticmethod
    def _merge_intent_key(
        *,
        issue_number: int,
        pr_number: int,
        subject: EvaluationSubject,
    ) -> str:
        return "merge:" + canonical_digest(
            {
                "schema_version": 1,
                "issue": issue_number,
                "pr_number": pr_number,
                "subject": subject.as_dict(),
            }
        )

    def _reconcile_merge(
        self,
        *,
        intent_key: str,
        issue_number: int,
        pr_number: int,
        correlation_id: str,
        subject: EvaluationSubject,
        existing: OperationIntentRecord,
    ) -> dict[str, Any]:
        assert self._scm is not None
        assert self._authority is not None
        try:
            pr = self._scm.get_pr(pr_number)
            revision = self._scm.get_pr_revision(pr_number)
        except Exception:
            if existing.status == "applied":
                return {
                    "reviewed": True,
                    "decision": "pass",
                    "merge": "merged",
                    "reason_code": "merge_previously_confirmed",
                }
            if existing.status == "pending":
                self._authority.finish_intent(
                    intent_key,
                    status="unresolved",
                    postcondition={"pr_number": pr_number, "scm_state_readable": False},
                )
            self._bus.publish(
                MergeOutcomeUnknown(
                    payload={
                        "issue": issue_number,
                        "pr_number": pr_number,
                        "reason_code": "merge_postcondition_unreadable",
                        "reason": "merge_postcondition_unreadable",
                        "cat": "scm",
                        "evt": "merge_outcome_unknown",
                        "lvl": "warn",
                        "evaluation_subject": subject.as_dict(),
                    },
                    correlation_id=correlation_id,
                )
            )
            return {"reviewed": True, "decision": "pass", "merge": "unresolved"}
        if pr.merged and self._revision_matches(revision, subject):
            if existing.status == "pending":
                self._authority.finish_intent(
                    intent_key,
                    status="applied",
                    postcondition={
                        "pr_number": pr_number,
                        "merged": True,
                        "head_sha": revision.head_sha,
                        "base_sha": revision.base_sha,
                    },
                )
            self._bus.publish(
                PRMerged(
                    payload={
                        "issue": issue_number,
                        "pr_number": pr_number,
                        "evaluation_subject": subject.as_dict(),
                        "cat": "scm",
                        "evt": "expected_head_merge_confirmed",
                        "lvl": "info",
                    },
                    correlation_id=correlation_id,
                )
            )
            return {"reviewed": True, "decision": "pass", "merge": "merged"}
        if not self._revision_matches(revision, subject):
            if existing.status == "pending":
                self._authority.finish_intent(
                    intent_key,
                    status="mismatch",
                    postcondition={
                        "pr_number": pr_number,
                        "merged": pr.merged,
                        "head_sha": revision.head_sha,
                        "base_sha": revision.base_sha,
                    },
                )
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="merge_subject_changed",
                subject=subject,
                decision="pass",
            )
        if existing.status == "pending":
            self._authority.finish_intent(
                intent_key,
                status="unresolved",
                postcondition={
                    "pr_number": pr_number,
                    "merged": False,
                    "head_sha": revision.head_sha,
                    "base_sha": revision.base_sha,
                },
            )
        self._bus.publish(
            MergeOutcomeUnknown(
                payload={
                    "issue": issue_number,
                    "pr_number": pr_number,
                    "reason_code": "merge_effect_not_confirmed",
                    "reason": "merge_effect_not_confirmed",
                    "cat": "scm",
                    "evt": "merge_outcome_unknown",
                    "lvl": "warn",
                    "evaluation_subject": subject.as_dict(),
                },
                correlation_id=correlation_id,
            )
        )
        return {"reviewed": True, "decision": "pass", "merge": "unresolved"}

    def _auto_merge(
        self,
        *,
        cmd: ReviewCommand,
        issue_number: int,
        pr_number: int,
        subject: EvaluationSubject,
        supplied_contract: AcceptanceContract,
        decision: ReviewDecision,
    ) -> dict[str, Any]:
        correlation_id = cmd.correlation_id or ""
        if self._scm is None or self._authority is None:
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="merge_authority_state_unavailable",
                subject=subject,
                decision="pass",
            )
        if (
            "native_expected_head_merge" not in self._scm.capabilities
            or not self._expected_head_merge_qualified
        ):
            return {
                "reviewed": True,
                "decision": "pass",
                "merge": "manual",
                "reason_code": "native_expected_head_merge_unqualified",
            }
        try:
            if not self._fresh_human_approval(
                issue_number=issue_number,
                subject=subject,
                supplied_contract=supplied_contract,
            ):
                return self._blocked(
                    issue_number=issue_number,
                    pr_number=pr_number,
                    correlation_id=correlation_id,
                    reason_code="merge_approval_not_fresh",
                    subject=subject,
                    decision="pass",
                )
            if not self._required_gates_passed(cmd.payload.get("gate_results"), subject):
                return self._blocked(
                    issue_number=issue_number,
                    pr_number=pr_number,
                    correlation_id=correlation_id,
                    reason_code="merge_required_gates_not_bound",
                    subject=subject,
                    decision="pass",
                )
            revision = self._scm.get_pr_revision(pr_number)
            if not self._revision_matches(revision, subject):
                return self._blocked(
                    issue_number=issue_number,
                    pr_number=pr_number,
                    correlation_id=correlation_id,
                    reason_code="pre_merge_revision_changed",
                    subject=subject,
                    decision="pass",
                )
        except Exception:
            log.warning(
                "Merge authority recheck failed for issue #%s and PR #%s",
                issue_number,
                pr_number,
            )
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="merge_authority_recheck_failed",
                subject=subject,
                decision="pass",
            )

        review_digest = canonical_digest(decision.as_dict())
        intent_key = self._merge_intent_key(
            issue_number=issue_number,
            pr_number=pr_number,
            subject=subject,
        )
        try:
            existing = self._authority.get_intent(intent_key)
            if existing is not None:
                if existing.payload.get("review_digest") != review_digest:
                    return self._blocked(
                        issue_number=issue_number,
                        pr_number=pr_number,
                        correlation_id=correlation_id,
                        reason_code="merge_review_changed",
                        subject=subject,
                        decision="pass",
                    )
                return self._reconcile_merge(
                    intent_key=intent_key,
                    issue_number=issue_number,
                    pr_number=pr_number,
                    correlation_id=correlation_id,
                    subject=subject,
                    existing=existing,
                )
            self._authority.put_intent(
                OperationIntentRecord(
                    intent_key=intent_key,
                    operation="merge_pr",
                    status="pending",
                    issue_number=issue_number,
                    correlation_id=correlation_id,
                    subject_key=subject.head_sha,
                    payload={
                        "pr_number": pr_number,
                        "repository": subject.repository,
                        "base_sha": subject.base_sha,
                        "expected_head_sha": subject.head_sha,
                        "review_digest": review_digest,
                    },
                )
            )
        except StateStoreError:
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="merge_intent_write_failed",
                subject=subject,
                decision="pass",
            )
        with suppress(Exception):
            self._scm.merge_pr_expected(pr_number, expected_head_sha=subject.head_sha)
        persisted = self._authority.get_intent(intent_key)
        if persisted is None:
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="merge_intent_missing_after_write",
                subject=subject,
                decision="pass",
            )
        return self._reconcile_merge(
            intent_key=intent_key,
            issue_number=issue_number,
            pr_number=pr_number,
            correlation_id=correlation_id,
            subject=subject,
            existing=persisted,
        )

    def handle(self, cmd: Command) -> Any:
        assert isinstance(cmd, ReviewCommand)
        diff = cmd.payload.get("diff", "")
        issue_number = int(cmd.payload.get("issue", 0))
        pr_number = int(cmd.payload.get("pr_number", 0))
        correlation_id = cmd.correlation_id or ""
        try:
            subject = EvaluationSubject.from_dict(cmd.payload["evaluation_subject"])
            supplied_contract = AcceptanceContract.from_dict(cmd.payload["acceptance_contract"])
            if supplied_contract.contract_hash != subject.contract_hash:
                raise ValueError("acceptance contract differs from review subject")
        except (KeyError, TypeError, ValueError):
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="review_subject_unbound",
            )
        if not isinstance(diff, str) or not diff:
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="review_diff_missing",
                subject=subject,
            )
        if not self._llm:
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="review_provider_unavailable",
                subject=subject,
            )

        diff_digest = text_digest(diff)
        prompt, prompt_digest = self._bound_prompt(
            diff=diff,
            subject=subject,
            acceptance_contract=supplied_contract,
            acceptance_evidence=cmd.payload.get("acceptance_evidence"),
            gate_results=cmd.payload.get("gate_results"),
            diff_digest=diff_digest,
            prompt_sanitizer=self._prompt_sanitizer,
        )
        if self._prompt_risk_analyzer is not None:
            try:
                self._prompt_risk_analyzer.inspect_text(
                    issue_number=issue_number,
                    source="review_prompt",
                    text=prompt,
                    correlation_id=correlation_id,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Prompt-risk analysis failed for review #%s: %s", issue_number, exc)

        review_kwargs = {
            "task": "review",
            "guards": ["prompt_guards"],
            "response_format": {"type": "json_object"},
        }
        try:
            if issue_number:
                with issue_scope(
                    issue_number, correlation_id, cmd.payload.get("budget_admission_key")
                ):
                    response = self._llm.complete(
                        [{"role": "user", "content": prompt}], **review_kwargs
                    )
            else:
                response = self._llm.complete(
                    [{"role": "user", "content": prompt}], **review_kwargs
                )
        except ProviderUnavailable as exc:
            provider_error: dict[str, Any] = {
                "code": exc.code,
                "retryable": exc.retryable,
            }
            if exc.status is not None:
                provider_error["status"] = exc.status
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="provider_unavailable",
                subject=subject,
                provider_error=provider_error,
            )

        if is_truncated_stop_reason(response.stop_reason):
            payload = {
                "issue": issue_number,
                "task": "review",
                "reason": "llm_response_truncated",
                "stop_reason": response.stop_reason,
                "model": response.model_used,
                "output_tokens": response.output_tokens,
            }
            self._bus.publish(TokenLimitHit(payload=payload, correlation_id=correlation_id))
            self._bus.publish(WorkflowBlocked(payload=payload, correlation_id=correlation_id))
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="llm_response_truncated",
                subject=subject,
            )
        try:
            decision = parse_review_decision(
                response.text,
                expected_subject=subject,
                expected_diff_sha256=diff_digest,
                expected_prompt_sha256=prompt_digest,
                expected_tool_kind="llm",
                expected_tool_name="review",
                producer_model=response.model_used,
            )
        except ValueError as exc:
            return self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code="review_contract_invalid",
                subject=subject,
                validation_error_class=classify_review_contract_error(exc),
            )

        review_digest = canonical_digest(decision.as_dict())
        safe_review = decision.as_dict()
        for finding in safe_review["findings"]:
            finding["summary"] = scrub_secrets(finding["summary"])
        event_payload = {
            "issue": issue_number,
            "pr_number": pr_number,
            "decision": decision.decision,
            "review": safe_review,
            "review_digest": review_digest,
            "evaluation_subject": subject.as_dict(),
            "cat": "workflow",
            "evt": "structured_review_completed",
            "lvl": "info",
        }
        self._bus.publish(ReviewCompleted(payload=event_payload, correlation_id=correlation_id))
        if self._scm is not None and issue_number:
            finding_lines = [
                f"- `{item['severity']}` `{item['code']}`: {item['summary']}"
                for item in safe_review["findings"]
            ]
            rendered_findings = "\n".join(finding_lines) if finding_lines else "- keine"
            self._scm.post_comment(
                issue_number,
                "## Strukturierter Review\n\n"
                f"Entscheid: `{decision.decision}`\n\n"
                f"Candidate: `{subject.head_sha}`\n\n"
                f"Acceptance: {self._acceptance_status(cmd.payload.get('acceptance_evidence'), supplied_contract, subject)}\n\n"
                "`suggestion` ist ein nicht blockierender Verbesserungshinweis; "
                "`pass` bestätigt die gebundene Reviewentscheidung, nicht die Abwesenheit aller Hinweise.\n\n"
                f"Diff: `{decision.diff_sha256}`\n\n"
                f"Findings:\n{rendered_findings}",
            )

        result: dict[str, Any] = {
            "reviewed": True,
            "decision": decision.decision,
            "review": safe_review,
            "review_digest": review_digest,
            "tokens_used": response.input_tokens + response.output_tokens,
        }
        if decision.decision != "pass":
            blocked = self._blocked(
                issue_number=issue_number,
                pr_number=pr_number,
                correlation_id=correlation_id,
                reason_code=f"review_decision_{decision.decision}",
                subject=subject,
                decision=decision.decision,
            )
            return {**result, **blocked}
        if not self._auto_merge_enabled:
            return {**result, "merge": "manual", "reason_code": "auto_merge_disabled"}
        return {
            **result,
            **self._auto_merge(
                cmd=cmd,
                issue_number=issue_number,
                pr_number=pr_number,
                subject=subject,
                supplied_contract=supplied_contract,
                decision=decision,
            ),
        }
