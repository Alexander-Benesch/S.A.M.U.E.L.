"""Plan-approval diagnostics and feedback; authority remains in acceptance.py."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from samuel.core.acceptance import (
    PlanApprovalAuthorityError,
    latest_active_plan,
    resolve_plan_approval,
)
from samuel.core.ports import IAuthorityStateStore, IRunProjectionStore, IVersionControl
from samuel.core.state import RunProjectionRecord
from samuel.core.types import scm_timestamp_at_or_after

log = logging.getLogger(__name__)
SERIES = "plan-approval-diagnostic.v1"

_RETRY = (
    "Zuerst den aktuellen Plan und status:plan prüfen. Nur wenn keine gültige Freigabe "
    "vorliegt: status:approved durch den Menschen entfernen und erneut setzen oder den "
    "eingerichteten Freigabekommentar verwenden. Ein vorhandenes Label wird nicht nachträglich freigegeben."
)
_CHECK = (
    "Webhookdiagnose und Erreichbarkeit der Plan-/Timeline-Evidence prüfen. "
    "Keine Labels auf Verdacht entfernen und keine Implementierung erzwingen."
)

# Fixed codes/text only: provider payloads and exception messages never enter the projection.
_REASONS = {
    "approval and active plan labels are not both present": (
        "plan_labels_incomplete",
        "Im zugestellten Labelstand fehlen status:plan oder status:approved.",
        _RETRY,
    ),
    "native delivery id is missing or malformed": (
        "delivery_id_invalid",
        "Die native Zustellungskennung fehlt oder ist ungültig.",
        _CHECK,
    ),
    "human webhook actor is required": (
        "human_actor_required",
        "Die Zustellung enthält keine zuordenbare menschliche Freigabe.",
        _CHECK,
    ),
    "native label event timestamp is missing or malformed": (
        "delivery_timestamp_invalid",
        "Der Zeitpunkt der nativen Labeländerung fehlt oder ist ungültig.",
        _CHECK,
    ),
    "provider label timeline is unavailable": (
        "timeline_unavailable",
        "Die providerseitige Labeltimeline ist nicht verfügbar.",
        _CHECK,
    ),
    "provider label timeline lookup failed": (
        "timeline_lookup_failed",
        "Plan oder Labeltimeline konnten nicht gelesen werden.",
        _CHECK,
    ),
    "active plan evidence is unavailable": (
        "active_plan_unavailable",
        "Es ist kein gültiger aktiver Plan nachweisbar.",
        "Aktuellen Plan und gegebenenfalls einen ausdrücklichen Replan prüfen; keine alte Freigabe übernehmen.",
    ),
    "active plan timestamp is missing or malformed": (
        "plan_timestamp_invalid",
        "Der Veröffentlichungszeitpunkt des aktiven Plans ist nicht nachweisbar.",
        _CHECK,
    ),
    "native label event is not uniquely correlated to the provider timeline": (
        "timeline_ambiguous",
        "Die Zustellung lässt sich keinem einzelnen Timeline-Ereignis eindeutig zuordnen.",
        _RETRY,
    ),
    "provider timeline event is not the matching human approval addition": (
        "not_human_approval_addition",
        "Das zugeordnete Ereignis ist keine passende neue menschliche Planfreigabe.",
        _RETRY,
    ),
    "provider timeline approval predates the active plan": (
        "approval_predates_plan",
        "Die zugeordnete Freigabe stammt aus der Zeit vor dem aktiven Plan.",
        _RETRY,
    ),
    "approval evidence is not bound to the active plan": (
        "active_plan_binding_failed",
        "Die Freigabe-Evidence passt nicht zum aktuellen Plan und Contract.",
        _CHECK,
    ),
    "workflow_budget_admission_missing": (
        "workflow_budget_admission_missing",
        "Die gebundene Budgetzulassung für den Plan fehlt.",
        "Den Budgetblocker prüfen; ein Labelwechsel ersetzt die fehlende Zulassung nicht.",
    ),
    "plan_approval_authority_persist_failed": (
        "plan_approval_authority_persist_failed",
        "Die Planfreigabe konnte nicht dauerhaft als Authority gespeichert werden.",
        "State-/Speicherdiagnose prüfen und den Blocker beheben; keine Implementierung erzwingen.",
    ),
    "signed_webhook_authority_transport_required": (
        "signed_webhook_authority_transport_required",
        "Die gespeicherte Freigabe stammt nicht aus diesem signierten Webhookpfad.",
        _CHECK,
    ),
}


def delivery_diagnostic(reason: str) -> dict[str, str] | None:
    explanation = _REASONS.get(reason)
    if explanation is None:
        return None
    code, message, next_action = explanation
    return {"reason_code": code, "message": message, "next_action": next_action}


def _key(repository: str, issue: int, plan: int, contract_hash: str) -> str:
    subject = f"{repository}\n{issue}\n{plan}\n{contract_hash}"
    return SERIES + ":" + hashlib.sha256(subject.encode()).hexdigest()


def record_delivery(
    store: IRunProjectionStore,
    *,
    scm: IVersionControl,
    issue: int,
    diagnostic: dict[str, str],
    delivery_timestamp: str,
    expected_plan: tuple[int, str] | None = None,
) -> bool:
    """Keep the last ignored-delivery explanation bound to its observed plan."""
    try:
        active = latest_active_plan(scm.get_comments(issue))
        if active is None:
            return False
        plan, contract = active
        if expected_plan is not None and expected_plan != (plan.id, contract.contract_hash):
            return False
        if not scm_timestamp_at_or_after(delivery_timestamp, plan.created_at):
            return False
        now = datetime.now(timezone.utc)
        record = RunProjectionRecord(
            projection_key=_key(scm.repository_identity, issue, plan.id, contract.contract_hash),
            issue_number=issue,
            correlation_id="",
            series=SERIES,
            status="delivery_not_materialized",
            payload={
                "repository": scm.repository_identity,
                "issue": issue,
                "plan_comment_id": plan.id,
                "contract_hash": contract.contract_hash,
                "reason_code": diagnostic["reason_code"],
            },
            updated_at=now,
        )
        previous = store.get_projection(record.projection_key)
        if (
            previous is None
            or previous.status != record.status
            or previous.payload != record.payload
        ):
            store.upsert_projection(record)
        return True
    except Exception as exc:
        log.warning("Plan approval diagnostic unavailable: %s", type(exc).__name__)
        return False


def _post_feedback(
    store: IRunProjectionStore,
    *,
    scm: IVersionControl,
    issue: int,
    plan_id: int,
    contract_hash: str,
    code: str,
    message: str,
    next_action: str,
) -> str:
    """Claim one bounded notification; uncertain POSTs are never blindly repeated."""
    key = _key(scm.repository_identity, issue, plan_id, contract_hash) + ":notice:" + code
    marker = (
        "<!-- samuel-plan-approval-feedback:" + hashlib.sha256(key.encode()).hexdigest() + " -->"
    )
    try:
        comments = scm.get_comments(issue)
        active = latest_active_plan(comments)
        if active is None or (active[0].id, active[1].contract_hash) != (plan_id, contract_hash):
            return "not_applicable"
        previous = store.get_projection(key)
        record = RunProjectionRecord(
            projection_key=key,
            issue_number=issue,
            correlation_id="",
            series=SERIES,
            status="feedback_pending",
            payload={
                "repository": scm.repository_identity,
                "issue": issue,
                "plan_comment_id": plan_id,
                "contract_hash": contract_hash,
                "reason_code": code,
            },
        )
        if any(marker in c.body and c.user == active[0].user for c in comments):
            if previous is None:
                store.compare_and_swap_projection(replace(record, status="feedback_posted"), None)
            elif previous.status != "feedback_posted":
                store.compare_and_swap_projection(
                    replace(previous, status="feedback_posted"), previous
                )
            return "already_posted"
        if previous is not None:
            return "already_posted" if previous.status == "feedback_posted" else "unknown"
        if not store.compare_and_swap_projection(record, None):
            return "unknown"
        current = latest_active_plan(scm.get_comments(issue))
        if current is None or (current[0].id, current[1].contract_hash) != (plan_id, contract_hash):
            store.compare_and_swap_projection(replace(record, status="feedback_superseded"), record)
            return "not_applicable"
        body = "\n".join(
            [
                "## Rückmeldung zur Planfreigabe",
                "",
                message,
                "",
                f"Bezug: [Plan-Kommentar {plan_id}](#issuecomment-{plan_id}) · Contract: `{contract_hash}`",
                "",
                "**Nächster Schritt:** " + next_action,
                "",
                f"Diagnosegrund: `{code}`. Diese Rückmeldung erteilt und widerruft keine Freigabe.",
                marker,
            ]
        )
        try:
            comment = scm.post_comment(issue, body)
            if comment.id <= 0 or comment.body != body:
                raise ValueError("feedback postcondition not confirmed")
        except Exception as exc:
            store.compare_and_swap_projection(replace(record, status="feedback_unknown"), record)
            log.warning("Issue approval feedback unconfirmed (#%d, %s)", issue, type(exc).__name__)
            return "unknown"
        store.compare_and_swap_projection(replace(record, status="feedback_posted"), record)
        return "posted"
    except Exception as exc:
        log.warning("Issue approval feedback unavailable (#%d, %s)", issue, type(exc).__name__)
        return "unavailable"


def issue_feedback(
    store: IRunProjectionStore | None,
    *,
    scm: IVersionControl,
    authority: IAuthorityStateStore | None,
    issue: int,
    diagnostic: dict[str, str] | None,
    delivery_timestamp: str,
    accepted: bool = False,
    expected_plan: tuple[int, str] | None = None,
) -> str:
    """Explain a current signed delivery without changing approval authority."""
    if store is None:
        log.warning("Issue approval feedback unavailable (#%d, projection_store_missing)", issue)
        return "unavailable"
    try:
        comments = scm.get_comments(issue)
        active = latest_active_plan(comments)
        if active is None:
            return "not_applicable"
        plan, contract = active
        subject = (plan.id, contract.contract_hash)
        if expected_plan is not None and expected_plan != subject:
            return "not_applicable"
        if not scm_timestamp_at_or_after(delivery_timestamp, plan.created_at):
            return "not_applicable"
        can_retry = False
        if not accepted:
            if authority is not None:
                try:
                    resolve_plan_approval(
                        authority,
                        scm=scm,
                        repository=scm.repository_identity,
                        issue_number=issue,
                        plan_comment=plan,
                        contract=contract,
                        comments=comments,
                    )
                except PlanApprovalAuthorityError as exc:
                    can_retry = exc.code == "plan_approval_authority_missing"
                except Exception as exc:
                    log.warning(
                        "Issue approval authority check unavailable (#%d, %s)",
                        issue,
                        type(exc).__name__,
                    )
                    can_retry = False
                else:
                    accepted = True
        if accepted:
            previous = store.get_projection(_key(scm.repository_identity, issue, *subject))
            if previous is not None and previous.status == "delivery_not_materialized":
                store.upsert_projection(
                    replace(previous, status="resolved", updated_at=datetime.now(timezone.utc))
                )
            code = "durable_approval_valid"
            message = "Die menschliche Planfreigabe wurde für diesen Plan angenommen."
            action = "Keine erneute Freigabe nötig. Den Workflowfortschritt und gegebenenfalls dessen eigenen Blocker prüfen."
        elif diagnostic is not None:
            code = diagnostic["reason_code"]
            message = (
                "Die Labelzustellung wurde nicht als neue Planfreigabe übernommen. "
                + diagnostic["message"]
            )
            action = diagnostic["next_action"] if can_retry else _CHECK
        else:
            return "not_applicable"
        return _post_feedback(
            store,
            scm=scm,
            issue=issue,
            plan_id=plan.id,
            contract_hash=contract.contract_hash,
            code=code,
            message=message,
            next_action=action,
        )
    except Exception as exc:
        log.warning("Issue approval feedback unavailable (#%d, %s)", issue, type(exc).__name__)
        return "unavailable"


def log_entries(store: IRunProjectionStore | None) -> list[dict[str, Any]]:
    """One compact diagnostic per plan, separate from the workflow/audit event stream."""
    if store is None:
        return []
    try:
        rows = store.list_projections(series=SERIES)
    except Exception as exc:
        log.warning("Approval log projection unavailable: %s", type(exc).__name__)
        return []
    entries: list[dict[str, Any]] = []
    by_key = {row.projection_key: row for row in rows}
    for row in rows:
        if row.status not in {"delivery_not_materialized", "resolved"}:
            continue
        code = row.payload.get("reason_code")
        explanation = next((v for v in _REASONS.values() if v[0] == code), None)
        if explanation is None:
            continue
        resolved = row.status == "resolved"
        notice = by_key.get(row.projection_key + ":notice:" + str(code))
        entries.append(
            {
                "timestamp": row.updated_at.isoformat(),
                "level": "info" if resolved else "warn",
                "category": "workflow",
                "event": "Planfreigabe-Hinweis",
                "message": (
                    "Früherer Freigabehinweis erledigt: Freigabe angenommen."
                    if resolved
                    else "Labelzustellung nicht übernommen: " + explanation[1]
                ),
                "issue": row.issue_number,
                "correlation_id": "",
                "owasp": "",
                "meta": {
                    "source": SERIES,
                    "plan_comment_id": row.payload.get("plan_comment_id"),
                    "contract_hash": row.payload.get("contract_hash"),
                    "reason_code": code,
                    "status": "resolved" if resolved else "delivery_not_materialized",
                    "issue_feedback": notice.status.removeprefix("feedback_")
                    if notice
                    else "unavailable",
                    "next_steps": "Keine erneute Freigabe nötig." if resolved else explanation[2],
                },
            }
        )
        if resolved:
            entries[-1]["resolved_at"] = row.updated_at.isoformat()
        elif notice is not None and notice.status in {"feedback_pending", "feedback_unknown"}:
            entries[-1]["message"] += " Issue-Rückmeldung nicht bestätigt."
    return entries


def snapshot(
    *,
    scm: IVersionControl | None,
    authority: IAuthorityStateStore | None,
    projections: IRunProjectionStore | None,
    issue: int,
) -> dict[str, Any]:
    """Revalidate existing authority; never infer acceptance from labels/diagnostics."""
    result: dict[str, Any] = {
        "status": "unknown",
        "message": "Planfreigabe derzeit nicht prüfbar.",
        "reason_code": "approval_evidence_unavailable",
        "next_action": _CHECK,
        "label_is_authority": False,
    }
    if scm is None or authority is None:
        return result
    try:
        comments = scm.get_comments(issue)
        active = latest_active_plan(comments)
        if active is None:
            return {
                **result,
                "status": "no_active_plan",
                "reason_code": "active_plan_unavailable",
                "message": "Kein gültiger aktiver Plan nachweisbar.",
                "next_action": "Aktuellen Plan beziehungsweise ausdrücklichen Replan prüfen. Alte Freigaben gelten nicht für einen Ersatzplan.",
            }
        plan, contract = active
        result.update(plan_comment_id=plan.id, contract_hash=contract.contract_hash)
        try:
            resolve_plan_approval(
                authority,
                scm=scm,
                repository=scm.repository_identity,
                issue_number=issue,
                plan_comment=plan,
                contract=contract,
                comments=comments,
            )
        except PlanApprovalAuthorityError as exc:
            if exc.code != "plan_approval_authority_missing":
                return {
                    **result,
                    "reason_code": exc.code,
                    "message": "Die gespeicherte Planfreigabe ist nicht als aktuell gültig nachweisbar.",
                    "next_action": (
                        "Plan-, Issue- und Basisrevision mit der gespeicherten Bindung vergleichen. "
                        "Bei abgeschlossenem Lauf die historischen Freigabe-/Mergenachweise lesen; "
                        "für einen neuen Auftrag den vorgesehenen Plan-/Replanpfad verwenden. "
                        "Keine Labels auf Verdacht ändern und keine Freigabe übertragen."
                        if exc.code == "plan_approval_source_revision_mismatch"
                        else _CHECK
                    ),
                }
        else:
            return {
                **result,
                "status": "accepted",
                "reason_code": "durable_approval_valid",
                "message": "Planfreigabe angenommen: Die dauerhafte Bindung an den aktuellen Plan ist geprüft.",
                "next_action": "Keine erneute Freigabe nötig. Den Workflowfortschritt und gegebenenfalls dessen eigenen Blocker prüfen.",
            }
        labels = {label.name for label in scm.get_issue(issue).labels}
        result.update(
            status="not_materialized" if "status:approved" in labels else "not_recorded",
            reason_code="plan_approval_authority_missing",
            message=(
                "status:approved ist sichtbar, aber für diesen Plan liegt keine dauerhafte Freigabe vor."
                if "status:approved" in labels
                else "Für diesen Plan liegt keine dauerhafte menschliche Freigabe vor."
            ),
            next_action=(
                _RETRY
                if "status:approved" in labels
                else "Freigabeweg des aktiven Workflows prüfen. Nur wenn menschliche Freigabe vorgesehen ist: "
                + _RETRY
            ),
        )
        if projections is not None:
            row = projections.get_projection(
                _key(scm.repository_identity, issue, plan.id, contract.contract_hash)
            )
            if (
                row is not None
                and row.series == SERIES
                and row.status == "delivery_not_materialized"
                and row.payload
                == {
                    "repository": scm.repository_identity,
                    "issue": issue,
                    "plan_comment_id": plan.id,
                    "contract_hash": contract.contract_hash,
                    "reason_code": row.payload.get("reason_code"),
                }
            ):
                explanation = next(
                    (
                        value
                        for value in _REASONS.values()
                        if value[0] == row.payload["reason_code"]
                    ),
                    None,
                )
                if explanation is not None:
                    code, message, action = explanation
                    result["last_delivery"] = {
                        "observed_at": row.updated_at.isoformat(),
                        "reason_code": code,
                        "message": message,
                    }
                    result["next_action"] = action
    except Exception as exc:
        log.warning("Plan approval readback unavailable: %s", type(exc).__name__)
        # A diagnostic read failure must not turn missing evidence into success.
        return {**result, "diagnostic_unavailable": True}
    return result
