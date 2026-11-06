"""SCM projection of completed, bound executions; never a source of authority."""

from __future__ import annotations

import html
import logging
from typing import Any

from samuel.core.acceptance import latest_active_plan
from samuel.core.errors import describe_diagnostic
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import Event
from samuel.core.ports import IVersionControl
from samuel.core.security_policy import redact_secrets
from samuel.core.state import AuthorityRecord
from samuel.core.workflow_recovery import WorkflowRecovery, digest

log = logging.getLogger(__name__)
WORKFLOW_LABELS = frozenset(
    {
        "ready-for-agent",
        "in-progress",
        "status:plan",
        "status:approved",
        "status:wip",
        "needs-review",
        "status:done",
        "status:failed",
    }
)
PASSIVE_ENTRIES = {"SubmitCandidate", "RequestCandidateVerification", "Evaluate"}


class BoundLabelProjection:
    def __init__(self, recovery: WorkflowRecovery, scm: IVersionControl) -> None:
        self.recovery, self.scm, self.store = recovery, scm, recovery.store

    def _record(self, key: str, kind: str, **payload: Any) -> None:
        self.store.put_authority_record(
            AuthorityRecord(
                record_key=key,
                kind="workflow_label_projection." + kind,
                payload=payload,
            )
        )

    def _claim(self, key: str, **payload: Any) -> bool:
        # Called under the existing issue lock. A claim survives a process death
        # or an uncertain SCM response: observation may be retried, writes may not.
        if self.store.get_authority_record(key) is not None:
            return False
        self._record(key, "attempt", **payload)
        return True

    def finish(
        self, ended: AuthorityRecord, events: list[Event], drafts: list[str] | None = None
    ) -> None:
        payload = ended.payload
        if payload["stage"] in PASSIVE_ENTRIES or payload["status"] in {
            "rejected",
            "waiting",
            "evaluated",
        }:
            return
        issue = payload["issue"]
        key = "workflow-labels:" + digest(ended.record_key)
        try:
            if not self.recovery.projection_is_current(ended) or not self._bound(payload, events):
                log.warning("Label projection binding unconfirmed (#%d); no mutation", issue)
                return
            desired = self._desired(payload, events)
            if desired is None:
                return
            if (
                "status:failed" in {label.name for label in self.scm.get_issue(issue).labels}
                and "status:failed" not in desired
            ):
                names = {event.name for event in events}
                if not (
                    "PlanPosted" in names
                    or "PRMerged" in names
                    or {"PRCreated", "HealingAttemptStarted"} <= names
                ):
                    log.warning("Failure label has no bound resolution (#%d); no mutation", issue)
                    return
            if not self._claim(key, execution=payload["execution"], issue=issue):
                return
            if payload["status"] in {"blocked", "aborted"}:
                self._terminal_comment(payload, events, drafts or [])
            self._apply(key, issue, desired)
        except Exception as exc:
            # Neither provider messages nor user/model content belong in logs.
            log.warning("Bound label projection deferred (#%d, %s)", issue, type(exc).__name__)

    def _bound(self, payload: dict[str, Any], events: list[Event]) -> bool:
        issue, correlation = payload["issue"], payload["correlation"]
        active = latest_active_plan(self.scm.get_comments(issue))
        current = {"id": active[0].id, "contract_hash": active[1].contract_hash} if active else {}
        initial = payload.get("plan_binding")
        if initial is None or initial.get("unknown"):
            return False
        posted = [e for e in events if e.name == "PlanPosted"]
        if posted:
            if initial or any(
                current
                != {
                    "id": event.payload.get("plan_comment_id"),
                    "contract_hash": event.payload.get("acceptance_contract", {}).get(
                        "contract_hash"
                    ),
                }
                for event in posted
            ):
                return False
        elif initial != current:
            return False
        for event in events:
            p = event.payload
            if (
                event.correlation_id != correlation
                or p.get("issue", p.get("issue_number")) != issue
                or any(p[key] != issue for key in ("issue", "issue_number") if key in p)
                or p.get("repository", self.scm.repository_identity) != self.scm.repository_identity
                or p.get("mutation_authority") == "none"
            ):
                return False
            if p.get("plan_comment_id") is not None and p["plan_comment_id"] != current.get("id"):
                return False
            contract = p.get("acceptance_contract")
            if (
                isinstance(contract, dict)
                and contract.get("contract_hash")
                and contract["contract_hash"] != current.get("contract_hash")
            ):
                return False
            raw = p.get("evaluation_subject")
            if raw is not None:
                subject = EvaluationSubject.from_dict(raw)
                if (
                    subject.repository != self.scm.repository_identity
                    or subject.contract_hash != current.get("contract_hash")
                ):
                    return False
        # Validate the final delivery against native SCM and its durable intent.
        deliveries = [e for e in events if e.name in {"PRCreated", "PRMerged", "ReviewCompleted"}]
        if deliveries:
            final = next((e for e in reversed(deliveries) if e.name == "PRMerged"), deliveries[-1])
            if not self._delivery_bound(issue, final):
                return False
        elif payload["status"] in {"blocked", "aborted"}:
            candidate = next(
                (e for e in reversed(events) if e.payload.get("evaluation_subject")), None
            )
            if candidate is not None and not self._candidate_bound(issue, candidate, events):
                return False
        return True

    def _candidate_bound(self, issue: int, event: Event, events: list[Event]) -> bool:
        if event.payload.get("pr_number") or event.payload.get("pr"):
            return self._delivery_bound(issue, event)
        subject = EvaluationSubject.from_dict(event.payload["evaluation_subject"])
        branches = {e.payload["branch"] for e in events if e.payload.get("branch")}
        branches.update(
            c.branch
            for c in self.store.list_checkpoints()
            if c.issue_number == issue
            and c.repository == subject.repository
            and c.correlation_id == event.correlation_id
            and c.head_sha == subject.head_sha
            and c.base_sha == subject.base_sha
            and c.branch
        )
        return (
            len(branches) == 1
            and self.scm.resolve_ref_optional(next(iter(branches))) == subject.head_sha
        )

    def _delivery_bound(self, issue: int, event: Event, *, native_merge: bool = False) -> bool:
        p = event.payload
        number = p.get("pr_number", p.get("pr"))
        if (
            type(number) is not int
            or number <= 0
            or not isinstance(p.get("evaluation_subject"), dict)
        ):
            return False
        subject = EvaluationSubject.from_dict(p["evaluation_subject"])
        intents = [
            i
            for i in self.store.list_intents(status="applied")
            if (
                i.operation == "create_pr"
                and i.issue_number == issue
                and (not native_merge or i.correlation_id == event.correlation_id)
                and i.postcondition.get("pr_number") == number
                and i.payload.get("repository") == subject.repository
                and i.payload.get("evaluation_subject") == subject.as_dict()
                and i.payload.get("head_sha") == subject.head_sha
                and i.payload.get("base_sha") == subject.base_sha
                and i.postcondition.get("head_sha") == subject.head_sha
                and i.postcondition.get("base_sha") == subject.base_sha
            )
        ]
        if len(intents) != 1:
            return False
        pr, revision = self.scm.get_pr(number), self.scm.get_pr_revision(number)
        return bool(
            pr.number == number
            and revision.repository == subject.repository
            and revision.head_sha == subject.head_sha
            and (pr.merged if event.name == "PRMerged" else pr.state == "open" and not pr.merged)
            and (event.name == "PRMerged" or revision.base_sha == subject.base_sha)
        )

    def _desired(self, payload: dict[str, Any], events: list[Event]) -> set[str] | None:
        status, names = payload["status"], {e.name for e in events}
        if status in {"blocked", "aborted"}:
            return {"status:failed", "help wanted"}
        if status == "merged":
            return {"status:done"}
        if status == "reviewed":
            return {"status:wip"}
        if "PRCreated" in names:
            starts = {
                e.payload.get("observation_key")
                for e in events
                if e.name == "HealingAttemptStarted"
            }
            delivered = next(e for e in reversed(events) if e.name == "PRCreated")
            if starts and (
                len(starts) != 1
                or not all(isinstance(key, str) and key for key in starts)
                or delivered.payload.get("healing_origin_observation_key") not in starts
            ):
                return None
            return {"status:wip", "needs-review"}
        if status == "manual_pending" or "CodeGenerated" in names:
            return {"status:wip", "in-progress", "status:approved"}
        if "PlanApproved" in names:
            return {"status:wip", "status:approved"}
        if "PlanPosted" in names:
            return {"status:plan"}
        return None

    def _apply(self, key: str, issue: int, desired: set[str]) -> None:
        before = {label.name for label in self.scm.get_issue(issue).labels}
        # Approval is evidence owned by humans. Keep it when needed, never add it.
        desired = desired - ({"status:approved"} - before)
        errors: list[str] = []
        # First expose the result, then remove misleading workflow labels.
        for remove, add in [("", label) for label in sorted(desired - before)] + [
            (label, "") for label in sorted((before & WORKFLOW_LABELS) - desired)
        ]:
            try:
                self.scm.swap_label(issue, remove, add)
            except Exception as exc:
                errors.append(type(exc).__name__)
                log.warning("Label write unconfirmed (#%d, %s)", issue, type(exc).__name__)
        after = {label.name for label in self.scm.get_issue(issue).labels}
        expected = (before - WORKFLOW_LABELS) | desired
        self._record(
            key + ":observed",
            "observation",
            issue=issue,
            status="confirmed" if after == expected and not errors else "unconfirmed",
            desired=sorted(desired),
            observed=sorted(after),
            errors=errors,
        )
        if errors or after != expected:
            log.warning("Label projection unconfirmed (#%d); no automatic write retry", issue)

    def _terminal_comment(
        self, payload: dict[str, Any], events: list[Event], drafts: list[str]
    ) -> None:
        issue = payload["issue"]
        key = "workflow-terminal:" + digest(
            [self.scm.repository_identity, issue, payload["correlation"]]
        )
        marker = "<!-- " + key + " -->"
        if not self._claim(key, issue=issue):
            return
        try:
            if any(marker in comment.body for comment in self.scm.get_comments(issue)):
                self._record(key + ":observed", "comment", issue=issue, status="confirmed")
                return

            def safe(value: Any) -> str:
                return (
                    html.escape(redact_secrets(str(value or "UNKNOWN")))[:180]
                    .replace("`", "&#96;")
                    .replace("@", "&#64;")
                    .replace("\n", " ")
                )

            subject: dict[str, Any] = next(
                (
                    e.payload["evaluation_subject"]
                    for e in reversed(events)
                    if e.payload.get("evaluation_subject")
                ),
                {},
            )
            plan = payload.get("plan_binding") or {}
            posted = next((event for event in events if event.name == "PlanPosted"), None)
            if posted is not None:
                plan = {
                    "id": posted.payload.get("plan_comment_id"),
                    "contract_hash": posted.payload.get("acceptance_contract", {}).get(
                        "contract_hash"
                    ),
                }
            healing = (
                "beobachtet; Versuch beendet"
                if any(e.name == "HealingAttemptStarted" for e in events)
                else "nicht beobachtet"
            )
            phase = {
                "PlanBlocked": "Planung",
                "PRCreationFailed": "PR-Erstellung",
                "ReviewBlocked": "Review",
                "MergeOutcomeUnknown": "Merge",
            }.get(str(payload.get("event")), "UNKNOWN")
            diagnosis = describe_diagnostic(
                logger="",
                reason=str(payload.get("reason") or ""),
                category="llm" if payload.get("event") == "LLMUnavailable" else "workflow",
                event_name=str(payload.get("event") or ""),
            )
            guidance = [diagnosis["title"], diagnosis["cause"], *diagnosis["next_steps"]]
            # Reuse the existing bound comment and captured gate identifiers. Raw
            # gate reasons/model content are deliberately absent from this projection.
            seen_gates: set[str] = set()
            for event in events:
                if event.name != "GateFailed" or not event.payload.get("gate"):
                    continue
                gate = str(event.payload["gate"])
                if gate in seen_gates or len(seen_gates) >= 10:
                    continue
                seen_gates.add(gate)
                gate_diagnosis = describe_diagnostic(
                    logger="",
                    reason="",
                    category="gates",
                    event_name="GateFailed",
                    gate=gate,
                )
                guidance.extend(
                    [
                        "Weiterer Gatebefund im selben Lauf; Korrelation belegt keine Kausalität.",
                        gate_diagnosis["title"],
                        gate_diagnosis["cause"],
                        *gate_diagnosis["next_steps"],
                    ]
                )
            body = "\n".join(
                [
                    marker,
                    "## Workflow-Versuch beendet",
                    "",
                    f"- Ergebnis: `{safe(payload['status'])}`; Fehlerphase: `{phase}`.",
                    f"- Einstieg: `{safe(payload['stage'])}`; terminales Ereignis: `{safe(payload.get('event'))}`.",
                    f"- Grund: `{safe(payload.get('reason'))}`.",
                    f"- Versuch: `{safe(payload['correlation'])}`; Plan: `{safe(plan.get('id'))}`.",
                    f"- Vertrag: `{safe(plan.get('contract_hash'))}`; Kandidat: `{subject.get('head_sha', 'UNKNOWN')}`.",
                    f"- Healing: {healing}. Akteurrolle: Workflow-Automation.",
                    "",
                    *(safe(detail) for detail in payload.get("terminal_details", [])),
                    "",
                    # Guidance is generated from fixed copy, not model/provider text.
                    *(
                        "- " + html.escape(redact_secrets(step)).replace("@", "&#64;")
                        for step in dict.fromkeys(guidance)
                    ),
                    "",
                    "Verantwortlich: menschlicher Operator. "
                    "Eine neue menschliche Planfreigabe ist erforderlich. Kein automatischer Wiederanlauf.",
                ]
            )
            for draft in drafts:
                body += (
                    "\n\n## Nicht autoritativer Planentwurf\n\n**Status:** Nicht freigegeben; keine Acceptance-Authority.\n\n<pre>"
                    + html.escape(draft).replace("@", "&#64;")
                    + "</pre>"
                )
            self.scm.post_comment(issue, body)
            confirmed = any(marker in c.body for c in self.scm.get_comments(issue))
            self._record(
                key + ":observed",
                "comment",
                issue=issue,
                status="confirmed" if confirmed else "unconfirmed",
            )
        except Exception as exc:
            log.warning(
                "Terminal comment unconfirmed (#%d, %s); no automatic write retry",
                issue,
                type(exc).__name__,
            )

    def merge(self, event: Event) -> None:
        """Native human merge arrives outside a root command; prove its binding."""
        issue = event.payload.get("issue")
        if (
            type(issue) is not int
            or issue <= 0
            or event.payload.get("issue_number", issue) != issue
            or event.payload.get("repository", self.scm.repository_identity)
            != self.scm.repository_identity
        ):
            return
        try:
            with (
                self.recovery.session.admission("PRMerged"),
                self.store.workflow_lock(digest([self.scm.repository_identity, issue])),
            ):
                active = latest_active_plan(self.scm.get_comments(issue))
                if active is None:
                    return
                subject = EvaluationSubject.from_dict(event.payload.get("evaluation_subject", {}))
                if (
                    subject.repository != self.scm.repository_identity
                    or subject.contract_hash != active[1].contract_hash
                    or not self._delivery_bound(issue, event, native_merge=True)
                ):
                    return
                key = "workflow-merge-labels:" + digest(
                    [self.scm.repository_identity, issue, subject.as_dict()]
                )
                if self._claim(key, issue=issue):
                    self._apply(key, issue, {"status:done"})
        except Exception as exc:
            log.warning("Merge label projection deferred (#%d, %s)", issue, type(exc).__name__)
