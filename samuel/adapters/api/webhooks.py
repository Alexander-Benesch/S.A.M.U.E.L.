from __future__ import annotations

import hashlib
import hmac
import logging
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from samuel.core.acceptance import (
    AcceptanceApproval,
    clarification_evidence_failure,
    latest_active_plan,
    persist_plan_approval_with_status,
)
from samuel.core.bus import Bus
from samuel.core.commands import ScanIssuesCommand
from samuel.core.events import (
    Event,
    IssueClosed,
    IssueCommented,
    IssueOpened,
    IssueReady,
    PlanApproved,
    PullRequestClosed,
    PullRequestMerged,
    PullRequestOpened,
    TamperDetected,
    WorkflowBlocked,
)
from samuel.core.state import AuthorityRecord, StateStoreError
from samuel.core.types import SCMLabelEvent, canonical_scm_timestamp, scm_timestamp_at_or_after

log = logging.getLogger(__name__)

_GITEA_SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_SIGNATURE_RE = re.compile(r"^sha256=[0-9a-f]{64}$")
_GITEA_DELIVERY_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_GITEA_TIMELINE_SOURCE_RE = re.compile(r"^gitea-timeline:[1-9][0-9]*$")


class WebhookIngressAdapter:
    def __init__(self, bus: Bus, secret: str = "", bot_user: str = "") -> None:
        self._bus = bus
        self._secret = secret
        # #230: zur actor_type-Klassifikation (bot vs human). Leer -> alles als
        # "human" gewertet (Webhook-beobachtete Aktivitaet ist per Definition
        # die, die "am Framework vorbei" laeuft).
        self._bot_user = bot_user

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _mapping_list(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def handle_webhook(
        self,
        event_type: str,
        payload: dict[str, Any],
        signature: str = "",
        *,
        raw_body: bytes | None = None,
        provider: str = "github",
        event_subtype: str = "",
        delivery_id: str = "",
    ) -> dict[str, Any]:
        normalized_provider = provider.casefold()
        normalized_type = (event_type or "").casefold()
        normalized_subtype = (event_subtype or "").casefold()
        self._observe(
            "received",
            provider=normalized_provider,
            event_type=normalized_type,
            event_subtype=normalized_subtype,
            delivery_id=delivery_id,
        )
        signature_valid = not self._secret or self._verify_signature(
            raw_body,
            signature,
            provider=normalized_provider,
        )
        self._observe(
            "signature",
            provider=normalized_provider,
            event_type=normalized_type,
            event_subtype=normalized_subtype,
            delivery_id=delivery_id,
            result="not_checked" if not self._secret else ("pass" if signature_valid else "denied"),
        )
        if not signature_valid:
            # #208: HMAC-Signatur dient genau der Tamper-Erkennung. Eine nicht
            # verifizierbare Payload ist entweder gefaelscht oder unterwegs
            # manipuliert — als TamperDetected publishen, damit es im Security-
            # Tab/Banner sichtbar wird (OWASP ASI04, AI-Act Art. 15).
            self._bus.publish(
                TamperDetected(
                    payload={
                        "mode": "external",
                        "reason": "webhook signature verification failed",
                        "event_type": event_type,
                        "owasp_risk": "agentic_supply_chain",
                        "files": [],
                    }
                )
            )
            return self._mapping_result(
                {"status": 401, "error": "invalid signature"},
                provider=normalized_provider,
                event_type=normalized_type,
                event_subtype=normalized_subtype,
                delivery_id=delivery_id,
            )

        if normalized_provider != "gitea" and event_type == "issue-created":
            result = self._on_issue_created(payload)
            return self._mapping_result(
                result,
                provider=normalized_provider,
                event_type=normalized_type,
                event_subtype=normalized_subtype,
                delivery_id=delivery_id,
            )

        if normalized_provider != "gitea" and event_type == "issue-labeled":
            result = self._on_issue_labeled(payload)
            return self._mapping_result(
                result,
                provider=normalized_provider,
                event_type=normalized_type,
                event_subtype=normalized_subtype,
                delivery_id=delivery_id,
            )

        action = str(payload.get("action", "")).casefold()
        if (
            normalized_provider == "gitea"
            and normalized_type == "issues"
            and normalized_subtype == "issue_label"
        ):
            approval_evidence = None
            reason = "native label event is not an approval label trigger"
            if action == "label_updated":
                approval_evidence, reason = self._native_gitea_approval_event(
                    payload,
                    delivery_id=delivery_id,
                )
            if approval_evidence is not None:
                approval_event, plan_comment_id, contract_hash = approval_evidence
                result = self._on_issue_labeled(
                    payload,
                    label={"name": "status:approved"},
                    native_gitea=True,
                    delivery_id=delivery_id,
                    approval_source_id=(f"{approval_event.source_id};delivery:{delivery_id}"),
                    approved_at=approval_event.timestamp,
                    expected_plan_comment_id=plan_comment_id,
                    expected_contract_hash=contract_hash,
                )
            else:
                result = {
                    "status": 200,
                    "action": "ignored",
                    "reason": reason,
                }
            return self._mapping_result(
                result,
                provider=normalized_provider,
                event_type=normalized_type,
                event_subtype=normalized_subtype,
                delivery_id=delivery_id,
            )

        if (
            normalized_provider != "gitea"
            and normalized_type in ("issues", "issue")
            and action
            in {
                "label",
                "labeled",
                "labelled",
            }
        ):
            approval = self._on_issue_labeled(payload)
            if self._mapping(payload.get("label")).get("name") == "status:approved":
                return self._mapping_result(
                    approval,
                    provider=normalized_provider,
                    event_type=normalized_type,
                    event_subtype=normalized_subtype,
                    delivery_id=delivery_id,
                )

        if event_type == "push":
            result = self._on_push(payload)
            return self._mapping_result(
                result,
                provider=normalized_provider,
                event_type=normalized_type,
                event_subtype=normalized_subtype,
                delivery_id=delivery_id,
            )

        # #230: reale Gitea-Events (X-Gitea-Event) tragen die konkrete Aktion in
        # payload["action"] — beobachtende SCM-Activity-Events daraus ableiten.
        activity = self._on_scm_activity(event_type, payload)
        if activity is not None:
            return self._mapping_result(
                activity,
                provider=normalized_provider,
                event_type=normalized_type,
                event_subtype=normalized_subtype,
                delivery_id=delivery_id,
            )

        return self._mapping_result(
            {"status": 200, "action": "ignored", "event_type": event_type},
            provider=normalized_provider,
            event_type=normalized_type,
            event_subtype=normalized_subtype,
            delivery_id=delivery_id,
        )

    @staticmethod
    def _observe(stage: str, **fields: object) -> None:
        safe = " ".join(
            f"{name}={str(value)[:160]}"
            for name, value in sorted(fields.items())
            if value not in {"", None}
        )
        log.info("webhook stage=%s%s", stage, f" {safe}" if safe else "")

    def _mapping_result(
        self,
        result: dict[str, Any],
        *,
        provider: str,
        event_type: str,
        event_subtype: str,
        delivery_id: str,
    ) -> dict[str, Any]:
        self._observe(
            "mapping",
            provider=provider,
            event_type=event_type,
            event_subtype=event_subtype,
            delivery_id=delivery_id,
            result=result.get("action") or "denied",
            reason=result.get("reason") or result.get("error") or "",
            status=result.get("status"),
        )
        return result

    def _native_gitea_approval_event(
        self,
        payload: dict[str, Any],
        *,
        delivery_id: str,
    ) -> tuple[tuple[SCMLabelEvent, int, str] | None, str]:
        if _GITEA_DELIVERY_RE.fullmatch(delivery_id) is None:
            return None, "native delivery id is missing or malformed"
        if not self._native_gitea_subject_matches(payload):
            return None, "repository or issue binding mismatch"

        issue = self._mapping(payload.get("issue"))
        labels = self._mapping_list(issue.get("labels"))
        label_names = {str(label.get("name", "")) for label in labels}
        if not {"status:plan", "status:approved"}.issubset(label_names):
            return None, "approval and active plan labels are not both present"

        actor, actor_type = self._actor(payload)
        if not actor or actor_type != "human":
            return None, "human webhook actor is required"
        approved_at = canonical_scm_timestamp(str(issue.get("updated_at") or ""))
        if not approved_at or not scm_timestamp_at_or_after(approved_at, approved_at):
            return None, "native label event timestamp is missing or malformed"

        scm = getattr(self._bus, "scm", None)
        if scm is None or not callable(getattr(scm, "get_label_events", None)):
            return None, "provider label timeline is unavailable"
        try:
            comments = scm.get_comments(int(issue.get("number", 0)))
            active = latest_active_plan(comments)
            if active is None:
                return None, "active plan evidence is unavailable"
            plan, contract = active
            plan_created_at = canonical_scm_timestamp(plan.created_at)
            if not plan_created_at or not scm_timestamp_at_or_after(
                plan_created_at, plan_created_at
            ):
                return None, "active plan timestamp is missing or malformed"
            timeline = scm.get_label_events(int(issue.get("number", 0)), "")
        except Exception as exc:  # provider evidence lookup must remain fail-closed
            log.warning(
                "provider label timeline lookup failed",
                extra={"error_type": type(exc).__name__},
            )
            return None, "provider label timeline lookup failed"
        correlated = [event for event in timeline if event.timestamp == approved_at]
        if len(correlated) != 1:
            return None, "native label event is not uniquely correlated to the provider timeline"
        event = correlated[0]
        if (
            _GITEA_TIMELINE_SOURCE_RE.fullmatch(event.source_id) is None
            or event.label != "status:approved"
            or event.operation != "add"
            or not event.actor
            or event.actor_type != "human"
            or event.actor != actor
        ):
            return None, "provider timeline event is not the matching human approval addition"
        if not scm_timestamp_at_or_after(event.timestamp, plan_created_at):
            return None, "provider timeline approval predates the active plan"
        return (event, plan.id, contract.contract_hash), ""

    @staticmethod
    def _repository_slug(identity: str) -> str:
        parsed = urlsplit(identity)
        path = parsed.path if parsed.scheme else identity
        parts = [part for part in path.strip("/").split("/") if part]
        return "/".join(parts[-2:]) if len(parts) >= 2 else path.strip("/")

    def _native_gitea_subject_matches(self, payload: dict[str, Any]) -> bool:
        scm = getattr(self._bus, "scm", None)
        if scm is None:
            return False
        issue = self._mapping(payload.get("issue"))
        repository = self._mapping(payload.get("repository"))
        try:
            top_level_number = int(payload.get("number", 0))
            issue_number = int(issue.get("number", 0))
        except (TypeError, ValueError):
            return False
        repository_name = str(repository.get("full_name") or "")
        expected_repository = self._repository_slug(str(scm.repository_identity))
        return (
            top_level_number > 0
            and top_level_number == issue_number
            and bool(repository_name)
            and repository_name == expected_repository
        )

    # --- #230: SCM-Activity (rein beobachtend) ---

    def _actor(self, payload: dict[str, Any]) -> tuple[str, str]:
        """(actor, actor_type) aus dem Gitea-``sender``. ``actor_type`` ist
        "bot" wenn der Sender dem konfigurierten ``bot_user`` entspricht, sonst
        "human"."""
        sender = self._mapping(payload.get("sender"))
        actor = str(sender.get("login") or sender.get("username") or "")
        actor_type = (
            "bot"
            if (self._bot_user and actor == self._bot_user)
            or str(sender.get("type", "")).casefold() == "bot"
            else "human"
        )
        return actor, actor_type

    def _acceptance_approval(
        self,
        issue_number: int,
        *,
        actor: str,
        method: str,
        source_id: str,
        approved_at: str = "",
        expected_plan_comment_id: int = 0,
        expected_contract_hash: str = "",
    ) -> dict[str, Any] | None:
        scm = getattr(self._bus, "scm", None)
        if scm is None:
            return None
        try:
            comments = scm.get_comments(issue_number)
            active = latest_active_plan(comments)
            if active is None:
                return None
            plan, contract = active
            if expected_plan_comment_id and (
                plan.id != expected_plan_comment_id
                or contract.contract_hash != expected_contract_hash
            ):
                return None
            if contract.clarification_basis is not None:
                issue = scm.get_issue(issue_number)
                clarification_failure = clarification_evidence_failure(contract, issue, comments)
                if clarification_failure is not None:
                    self._bus.publish(
                        WorkflowBlocked(
                            payload={
                                "issue": issue_number,
                                "stage": "approval",
                                "reason": clarification_failure,
                            }
                        )
                    )
                    return None
                source = contract.source_snapshot
                if (
                    source is None
                    or source.repository != scm.repository_identity
                    or scm.resolve_ref(source.base_ref) != source.base_sha
                ):
                    self._bus.publish(
                        WorkflowBlocked(
                            payload={
                                "issue": issue_number,
                                "stage": "approval",
                                "reason": "clarification_source_changed",
                            }
                        )
                    )
                    return None
            normalized_approval_time = canonical_scm_timestamp(approved_at)
            plan_time = canonical_scm_timestamp(plan.created_at)
            if not scm_timestamp_at_or_after(normalized_approval_time, plan_time):
                return None
            receipt = AcceptanceApproval(
                state="approved",
                actor=actor,
                method=method,
                source_id=f"plan:{plan.id};{source_id}",
                approved_at=normalized_approval_time,
                contract_hash=contract.contract_hash,
                plan_comment_id=plan.id,
            ).as_dict()
            receipt["_acceptance_contract"] = contract.as_dict()
            return receipt
        except (OSError, StopIteration, ValueError):
            return None

    def _budget_admission_key(self, issue_number: int, approval: dict[str, Any]) -> str | None:
        authority = getattr(self._bus, "authority_state_store", None)
        if authority is None:
            return ""
        scm = getattr(self._bus, "scm", None)
        if scm is None:
            return None
        try:
            admission = authority.find_budget_admission(
                repository=scm.repository_identity,
                issue_number=issue_number,
                plan_contract_hash=str(approval.get("contract_hash") or ""),
                plan_comment_id=int(approval.get("plan_comment_id") or 0),
            )
        except Exception as exc:  # webhook approval remains fail-closed and observable
            self._bus.publish(
                WorkflowBlocked(
                    payload={
                        "issue": issue_number,
                        "stage": "approval",
                        "reason": "workflow_budget_admission_lookup_failed",
                        "error_type": type(exc).__name__,
                    }
                )
            )
            return None
        return admission.admission_key if admission is not None else None

    def _persist_plan_approval_authority(
        self,
        issue_number: int,
        approval: dict[str, Any],
        acceptance_contract: object,
    ) -> tuple[AuthorityRecord, bool] | None:
        authority = getattr(self._bus, "authority_state_store", None)
        scm = getattr(self._bus, "scm", None)
        if (
            authority is None
            or not callable(getattr(authority, "put_authority_record", None))
            or not callable(getattr(authority, "get_authority_record", None))
            or scm is None
            or not self._secret
            or not isinstance(acceptance_contract, dict)
        ):
            return None
        try:
            from samuel.core.acceptance import AcceptanceContract

            record, created = persist_plan_approval_with_status(
                authority,
                repository=scm.repository_identity,
                issue_number=issue_number,
                contract=AcceptanceContract.from_dict(acceptance_contract),
                approval=AcceptanceApproval.from_dict(approval),
                transport="signed_webhook",
            )
        except (AttributeError, StateStoreError, TypeError, ValueError):
            return None
        return record, created

    def _on_scm_activity(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        action = str(payload.get("action", "")).lower()
        base = (event_type or "").lower()

        if base in ("issues", "issue"):
            issue = self._mapping(payload.get("issue"))
            number = issue.get("number", 0)
            if action == "opened":
                return self._publish_activity(IssueOpened, "issue_opened", number, issue, payload)
            if action == "closed":
                return self._publish_activity(IssueClosed, "issue_closed", number, issue, payload)
            return None

        if base in ("issue_comment", "issue-comment"):
            if action != "created":
                return None
            issue = self._mapping(payload.get("issue"))
            activity = self._publish_activity(
                IssueCommented,
                "issue_commented",
                issue.get("number", 0),
                issue,
                payload,
            )
            approval = self._on_issue_comment_approval(payload)
            return approval or activity

        if base in ("pull_request", "pull-request"):
            pr = self._mapping(payload.get("pull_request"))
            number = pr.get("number", 0)
            if action == "opened":
                return self._publish_activity(PullRequestOpened, "pr_opened", number, pr, payload)
            if action == "closed":
                if pr.get("merged"):
                    return self._publish_activity(
                        PullRequestMerged, "pr_merged", number, pr, payload
                    )
                return self._publish_activity(PullRequestClosed, "pr_closed", number, pr, payload)
            return None

        return None

    def _publish_activity(
        self,
        event_cls: Callable[..., Event],
        kind: str,
        number: Any,
        obj: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        actor, actor_type = self._actor(payload)
        event_name = event_cls().name
        timestamp = self._activity_timestamp(kind, obj, payload)
        object_id = ""
        if kind == "issue_commented":
            comment = self._mapping(payload.get("comment"))
            object_id = comment.get("id", "")
        discriminator = object_id or number
        activity_id = f"{event_name}:{discriminator}:{timestamp}"
        self._bus.publish(
            event_cls(
                payload={
                    "number": number,
                    "title": obj.get("title", ""),
                    "url": obj.get("html_url", ""),
                    "actor": actor,
                    "actor_type": actor_type,
                    "source": "webhook",
                    "timestamp": timestamp,
                    "activity_id": activity_id,
                    "idempotency_key": f"scm_activity:{activity_id}",
                }
            )
        )
        return {"status": 202, "action": kind, "number": number, "actor_type": actor_type}

    @staticmethod
    def _activity_timestamp(kind: str, obj: dict[str, Any], payload: dict[str, Any]) -> str:
        if kind == "issue_commented":
            comment = WebhookIngressAdapter._mapping(payload.get("comment"))
            value = comment.get("created_at") or comment.get("updated_at") or ""
            return canonical_scm_timestamp(str(value))
        if kind == "pr_merged":
            value = obj.get("merged_at") or obj.get("closed_at") or obj.get("updated_at") or ""
            return canonical_scm_timestamp(str(value))
        if kind in {"issue_closed", "pr_closed"}:
            value = obj.get("closed_at") or obj.get("updated_at") or ""
            return canonical_scm_timestamp(str(value))
        value = obj.get("created_at") or obj.get("updated_at") or ""
        return canonical_scm_timestamp(str(value))

    def _on_issue_created(self, payload: dict[str, Any]) -> dict[str, Any]:
        issue_number = self._mapping(payload.get("issue")).get("number", 0)
        if not issue_number:
            return {"status": 400, "error": "missing issue number"}

        self._bus.publish(
            IssueReady(
                payload={"issue": issue_number, "source": "webhook"},
            )
        )
        return {"status": 202, "action": "issue_ready", "issue": issue_number}

    def _on_issue_labeled(
        self,
        payload: dict[str, Any],
        *,
        label: dict[str, Any] | None = None,
        native_gitea: bool = False,
        delivery_id: str = "",
        approval_source_id: str = "",
        approved_at: str = "",
        expected_plan_comment_id: int = 0,
        expected_contract_hash: str = "",
    ) -> dict[str, Any]:
        issue = self._mapping(payload.get("issue"))
        issue_number = issue.get("number", 0)
        label_data = label if label is not None else self._mapping(payload.get("label"))
        label_name = label_data.get("name", "")

        if label_name == "status:approved" and issue_number:
            if native_gitea and not self._native_gitea_subject_matches(payload):
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="rejected",
                    reason="repository_or_issue_binding_mismatch",
                )
                return {
                    "status": 200,
                    "action": "ignored",
                    "reason": "repository or issue binding mismatch",
                }
            actor, actor_type = self._actor(payload)
            if not actor or actor_type == "bot":
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="rejected",
                    reason="human_actor_required",
                )
                return {"status": 200, "action": "ignored", "reason": "bot approval rejected"}
            labels = self._mapping_list(issue.get("labels"))
            label_names = {
                str(current.get("name", "")) for current in labels if isinstance(current, dict)
            }
            if "status:plan" not in label_names:
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="rejected",
                    reason="active_plan_label_missing",
                )
                return {
                    "status": 200,
                    "action": "ignored",
                    "reason": "no visible plan awaiting approval",
                }
            effective_approved_at = approved_at or str(issue.get("updated_at") or "")
            approval = self._acceptance_approval(
                issue_number,
                actor=actor,
                method="status:approved",
                source_id=(
                    approval_source_id
                    or f"label:{label_data.get('id', 'status:approved')}:{effective_approved_at}"
                ),
                approved_at=effective_approved_at,
                expected_plan_comment_id=expected_plan_comment_id,
                expected_contract_hash=expected_contract_hash,
            )
            if approval is None:
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="rejected",
                    reason="active_plan_binding_failed",
                )
                return {
                    "status": 200,
                    "action": "ignored",
                    "reason": "approval evidence is not bound to the active plan",
                }
            acceptance_contract = approval.pop("_acceptance_contract", None)
            budget_admission_key = self._budget_admission_key(issue_number, approval)
            if budget_admission_key is None:
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue_number,
                            "stage": "approval",
                            "reason": "workflow_budget_admission_missing",
                        }
                    )
                )
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="rejected",
                    reason="workflow_budget_admission_missing",
                )
                return {
                    "status": 409,
                    "action": "blocked",
                    "reason": "workflow_budget_admission_missing",
                }
            persisted_approval = self._persist_plan_approval_authority(
                issue_number,
                approval,
                acceptance_contract,
            )
            if persisted_approval is None:
                self._bus.publish(
                    WorkflowBlocked(
                        payload={
                            "issue": issue_number,
                            "stage": "approval",
                            "reason": "plan_approval_authority_persist_failed",
                        }
                    )
                )
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="rejected",
                    reason="plan_approval_authority_persist_failed",
                )
                return {
                    "status": 409,
                    "action": "blocked",
                    "reason": "plan_approval_authority_persist_failed",
                }
            approval_authority, authority_created = persisted_approval
            authority_source = approval_authority.payload.get("source")
            if native_gitea and (
                not isinstance(authority_source, dict)
                or authority_source.get("transport") != "signed_webhook"
            ):
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="rejected",
                    reason="signed_webhook_authority_transport_required",
                )
                return {
                    "status": 409,
                    "action": "blocked",
                    "reason": "signed_webhook_authority_transport_required",
                }
            if native_gitea and not authority_created:
                self._observe(
                    "authority",
                    issue=issue_number,
                    delivery_id=delivery_id,
                    result="idempotent_replay",
                )
                return {
                    "status": 200,
                    "action": "ignored",
                    "reason": "approval delivery already materialized",
                }
            approval = AcceptanceApproval.from_dict(
                approval_authority.payload["approval"]
            ).as_dict()
            self._bus.publish(
                PlanApproved(
                    payload={
                        "issue": issue_number,
                        "actor": actor,
                        "source": "webhook",
                        "approval_method": "status:approved",
                        **({"acceptance_approval": approval} if approval else {}),
                        **(
                            {"acceptance_contract": acceptance_contract}
                            if isinstance(acceptance_contract, dict)
                            else {}
                        ),
                        **(
                            {"budget_admission_key": budget_admission_key}
                            if budget_admission_key
                            else {}
                        ),
                        **({"plan_approval_authority_key": approval_authority.record_key}),
                    }
                )
            )
            self._observe(
                "authority",
                issue=issue_number,
                delivery_id=delivery_id,
                result="materialized",
            )
            return {"status": 202, "action": "plan_approved", "issue": issue_number}

        return {"status": 200, "action": "ignored"}

    def _on_issue_comment_approval(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        issue = self._mapping(payload.get("issue"))
        labels = self._mapping_list(issue.get("labels"))
        label_names = {str(label.get("name", "")) for label in labels}
        if "status:plan" not in label_names:
            return None

        comment = self._mapping(payload.get("comment"))
        body = str(comment.get("body", "")).strip().casefold()
        if body not in {"ok", "/approve"}:
            return None

        actor, actor_type = self._actor(payload)
        if not actor or actor_type == "bot":
            return None

        issue_number = issue.get("number", 0)
        if not issue_number:
            return None
        comment_id = comment.get("id", "")
        approved_at = str(comment.get("created_at") or "")
        approval = self._acceptance_approval(
            issue_number,
            actor=actor,
            method="comment",
            source_id=f"comment:{comment_id}",
            approved_at=approved_at,
        )
        if approval is None:
            return None
        acceptance_contract = approval.pop("_acceptance_contract", None)
        budget_admission_key = self._budget_admission_key(issue_number, approval)
        if budget_admission_key is None:
            self._bus.publish(
                WorkflowBlocked(
                    payload={
                        "issue": issue_number,
                        "stage": "approval",
                        "reason": "workflow_budget_admission_missing",
                    }
                )
            )
            return {
                "status": 409,
                "action": "blocked",
                "reason": "workflow_budget_admission_missing",
            }
        persisted_approval = self._persist_plan_approval_authority(
            issue_number,
            approval,
            acceptance_contract,
        )
        if persisted_approval is None:
            self._bus.publish(
                WorkflowBlocked(
                    payload={
                        "issue": issue_number,
                        "stage": "approval",
                        "reason": "plan_approval_authority_persist_failed",
                    }
                )
            )
            return {
                "status": 409,
                "action": "blocked",
                "reason": "plan_approval_authority_persist_failed",
            }
        approval_authority, _authority_created = persisted_approval
        approval = AcceptanceApproval.from_dict(approval_authority.payload["approval"]).as_dict()
        self._bus.publish(
            PlanApproved(
                payload={
                    "issue": issue_number,
                    "actor": actor,
                    "source": "webhook",
                    "approval_method": "comment",
                    **({"acceptance_approval": approval} if approval else {}),
                    **(
                        {"acceptance_contract": acceptance_contract}
                        if isinstance(acceptance_contract, dict)
                        else {}
                    ),
                    **(
                        {"budget_admission_key": budget_admission_key}
                        if budget_admission_key
                        else {}
                    ),
                    **({"plan_approval_authority_key": approval_authority.record_key}),
                }
            )
        )
        return {"status": 202, "action": "plan_approved", "issue": issue_number}

    def _on_push(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._bus.send(ScanIssuesCommand())
        return {"status": 202, "action": "scan_triggered"}

    def _verify_signature(
        self,
        raw_body: bytes | None,
        signature: str,
        *,
        provider: str,
    ) -> bool:
        if raw_body is None or not signature:
            return False
        expected = hmac.new(self._secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if provider == "gitea":
            if _GITEA_SIGNATURE_RE.fullmatch(signature) is None:
                return False
            supplied = signature
        elif provider == "github":
            if _GITHUB_SIGNATURE_RE.fullmatch(signature) is None:
                return False
            supplied = signature.removeprefix("sha256=")
        else:
            return False
        return hmac.compare_digest(expected, supplied)
