"""Bounded clarification orchestration inside the existing planning authority."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from samuel.core.acceptance import (
    MAX_CLARIFICATION_ROUNDS,
    ClarificationBasis,
    ClarificationRequest,
    PlanningSourceSnapshot,
    assess_issue_readiness,
    comment_body_digest,
    comment_revision,
    parse_clarification_answer,
    parse_clarification_request,
    render_clarification_request,
    verify_clarification_basis,
)
from samuel.core.events import (
    ClarificationAccepted,
    ClarificationRequested,
    ClarificationWaiting,
    PlanBlocked,
    WorkflowAborted,
)
from samuel.core.ports import IAuthorityStateStore, IVersionControl
from samuel.core.state import ClarificationStatus, PlanningClarificationRecord, StateStoreError
from samuel.core.types import Comment, Issue


def _series_key(repository: str, issue_number: int, source_digest: str, admission_key: str) -> str:
    value = f"{repository}\0{issue_number}\0{source_digest}\0{admission_key}".encode()
    return f"clr-{hashlib.sha256(value).hexdigest()[:24]}"


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


class ClarificationCoordinator:
    def __init__(
        self,
        *,
        bus: Any,
        scm: IVersionControl,
        store: IAuthorityStateStore,
        wait_seconds: int | None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._bus = bus
        self._scm = scm
        self._store = store
        self._wait_seconds = wait_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _publish_terminal(
        self,
        issue_number: int,
        correlation_id: str,
        reason: str,
        *,
        series_key: str = "",
    ) -> None:
        payload = {
            "issue": issue_number,
            "reason": reason,
            "cat": "plan",
            "evt": "clarification_terminal",
            "series_key": series_key,
        }
        with suppress(Exception):
            self._scm.post_comment(
                issue_number,
                "## Planung blockiert\n\n"
                f"**Grund:** `{reason}`\n\n"
                "Es wurde kein teilweiser Acceptance Contract freigegeben.",
            )
        self._bus.publish(PlanBlocked(payload=payload, correlation_id=correlation_id))
        self._bus.publish(WorkflowAborted(payload=payload, correlation_id=correlation_id))

    def _write(
        self,
        record: PlanningClarificationRecord,
        *,
        expected_version: int | None,
    ) -> PlanningClarificationRecord:
        self._store.put_planning_clarification(record, expected_version=expected_version)
        return record

    def _publish_requested(
        self,
        record: PlanningClarificationRecord,
        *,
        comment_id: int,
        question_count: int,
    ) -> None:
        self._bus.publish(
            ClarificationRequested(
                payload={
                    "issue": record.issue_number,
                    "cat": "plan",
                    "evt": "clarification_requested",
                    "series_key": record.series_key,
                    "round": record.round_number,
                    "question_count": question_count,
                    "deadline_at": record.deadline_at.isoformat(),
                    "question_comment_id": comment_id,
                },
                correlation_id=record.correlation_id,
            )
        )

    def _finish_record(
        self,
        record: PlanningClarificationRecord,
        *,
        status: ClarificationStatus = "exhausted",
    ) -> PlanningClarificationRecord:
        terminal = replace(
            record,
            status=status,
            version=record.version + 1,
            updated_at=self._now(),
        )
        return self._write(terminal, expected_version=record.version)

    def _question_round(
        self,
        record: PlanningClarificationRecord,
        questions: tuple[str, ...],
    ) -> PlanningClarificationRecord:
        deadline = self._now() + timedelta(seconds=int(self._wait_seconds or 0))
        round_data: dict[str, Any] = {
            "round_number": record.round_number,
            "questions": list(questions),
            "question_comment_id": 0,
            "question_digest": "",
            "question_revision": "",
        }
        rounds = (*record.rounds[:-1], round_data) if record.rounds else (round_data,)
        staged = replace(
            record,
            status="waiting",
            deadline_at=deadline,
            rounds=rounds,
            version=record.version + 1,
            updated_at=self._now(),
        )
        self._write(staged, expected_version=record.version)
        request = ClarificationRequest(
            schema_version=1,
            series_key=staged.series_key,
            round_number=staged.round_number,
            source_digest=staged.source_digest,
            deadline_at=deadline.isoformat(),
            questions=questions,
        )
        comment = self._scm.post_comment(staged.issue_number, render_clarification_request(request))
        round_data.update(
            {
                "question_comment_id": comment.id,
                "question_digest": comment_body_digest(comment),
                "question_revision": comment_revision(comment),
            }
        )
        complete = replace(
            staged,
            rounds=(*staged.rounds[:-1], round_data),
            version=staged.version + 1,
            updated_at=self._now(),
        )
        self._write(complete, expected_version=staged.version)
        self._publish_requested(
            complete,
            comment_id=comment.id,
            question_count=len(questions),
        )
        return complete

    def _ensure_question_comment(
        self, record: PlanningClarificationRecord, comments: list[Comment]
    ) -> PlanningClarificationRecord:
        current = record.rounds[-1]
        if int(current.get("question_comment_id", 0)) > 0:
            return record
        questions = tuple(str(item) for item in current.get("questions", ()))
        if not 1 <= len(questions) <= 3 or any(not question.strip() for question in questions):
            raise StateStoreError(
                "clarification_request_invalid",
                "Persisted clarification questions are missing or invalid",
            )
        expected_request = ClarificationRequest(
            schema_version=1,
            series_key=record.series_key,
            round_number=record.round_number,
            source_digest=record.source_digest,
            deadline_at=record.deadline_at.isoformat(),
            questions=questions,
        )
        matches: list[Comment] = []
        for comment in comments:
            request = parse_clarification_request(comment.body)
            if request == expected_request:
                matches.append(comment)
        if len(matches) > 1:
            raise StateStoreError(
                "clarification_request_duplicate",
                "More than one SCM request exists for one clarification round",
            )
        if matches:
            comment = matches[0]
            data = dict(current)
            data.update(
                {
                    "question_comment_id": comment.id,
                    "question_digest": comment_body_digest(comment),
                    "question_revision": comment_revision(comment),
                }
            )
            updated = replace(
                record,
                rounds=(*record.rounds[:-1], data),
                version=record.version + 1,
                updated_at=self._now(),
            )
            written = self._write(updated, expected_version=record.version)
            self._publish_requested(
                written,
                comment_id=comment.id,
                question_count=len(questions),
            )
            return written
        # Recover a staged state without duplicating a request marker.
        comment = self._scm.post_comment(
            record.issue_number, render_clarification_request(expected_request)
        )
        data = dict(current)
        data.update(
            {
                "question_comment_id": comment.id,
                "question_digest": comment_body_digest(comment),
                "question_revision": comment_revision(comment),
            }
        )
        updated = replace(
            record,
            rounds=(*record.rounds[:-1], data),
            version=record.version + 1,
            updated_at=self._now(),
        )
        written = self._write(updated, expected_version=record.version)
        self._publish_requested(
            written,
            comment_id=comment.id,
            question_count=len(questions),
        )
        return written

    def _basis(self, record: PlanningClarificationRecord) -> ClarificationBasis:
        return ClarificationBasis(
            schema_version=1,
            series_key=record.series_key,
            source_digest=record.source_digest,
            rounds=record.rounds,
        )

    def mark_planned(self, series_key: str) -> None:
        record = self._store.get_planning_clarification(series_key)
        if record is None or record.status != "answered":
            raise StateStoreError(
                "planning_clarification_missing",
                "The accepted clarification series is not available",
            )
        updated = replace(
            record,
            status="planned",
            version=record.version + 1,
            updated_at=self._now(),
        )
        self._write(updated, expected_version=record.version)

    def process(
        self,
        *,
        issue: Issue,
        source_snapshot: PlanningSourceSnapshot,
        admission_key: str,
        correlation_id: str,
    ) -> tuple[bool, ClarificationBasis | None]:
        """Return ``(proceed_to_planner, bound_basis)``."""

        decision = assess_issue_readiness(issue)
        if decision.state == "blocked":
            self._publish_terminal(issue.number, correlation_id, decision.reasons[0])
            return False, None
        active = self._store.find_active_planning_clarification(
            repository=source_snapshot.repository,
            issue_number=issue.number,
        )
        if active is None and decision.state == "ready":
            return True, None
        if (
            self._wait_seconds is None
            or isinstance(self._wait_seconds, bool)
            or not (1 <= self._wait_seconds <= 2_592_000)
        ):
            self._publish_terminal(
                issue.number, correlation_id, "clarification_wait_not_explicitly_configured"
            )
            return False, None

        if active is None:
            now = self._now()
            deadline = now + timedelta(seconds=self._wait_seconds)
            seed = PlanningClarificationRecord(
                series_key=_series_key(
                    source_snapshot.repository, issue.number, source_snapshot.digest, admission_key
                ),
                repository=source_snapshot.repository,
                issue_number=issue.number,
                source_digest=source_snapshot.digest,
                admission_key=admission_key,
                correlation_id=correlation_id,
                status="waiting",
                round_number=1,
                deadline_at=deadline,
                rounds=(
                    {
                        "round_number": 1,
                        "questions": list(decision.questions),
                        "question_comment_id": 0,
                        "question_digest": "",
                        "question_revision": "",
                    },
                ),
                created_at=now,
                updated_at=now,
            )
            self._store.put_planning_clarification(seed)
            try:
                active = self._question_round(seed, decision.questions)
            except StateStoreError as exc:
                self._publish_terminal(
                    issue.number, correlation_id, exc.code, series_key=seed.series_key
                )
            except Exception:  # noqa: BLE001 - SCM adapter failures remain retryable
                self._bus.publish(
                    ClarificationWaiting(
                        payload={
                            "issue": issue.number,
                            "cat": "plan",
                            "evt": "clarification_waiting",
                            "series_key": seed.series_key,
                            "round": seed.round_number,
                            "deadline_at": seed.deadline_at.isoformat(),
                            "reason": "clarification_request_delivery_pending",
                        },
                        correlation_id=correlation_id,
                    )
                )
            return False, None

        comments = self._scm.get_comments(issue.number)
        if active.status == "answered":
            basis = self._basis(active)
            valid, reason = verify_clarification_basis(
                basis, comments, source_digest=source_snapshot.digest
            )
            if not valid:
                self._finish_record(active)
                self._publish_terminal(
                    issue.number, correlation_id, reason, series_key=active.series_key
                )
                return False, None
            return True, basis

        try:
            active = self._ensure_question_comment(active, comments)
        except Exception as exc:  # noqa: BLE001 - distinguish state from SCM adapters below
            if isinstance(exc, StateStoreError):
                self._finish_record(active)
                self._publish_terminal(
                    issue.number, correlation_id, exc.code, series_key=active.series_key
                )
                return False, None
            self._bus.publish(
                ClarificationWaiting(
                    payload={
                        "issue": issue.number,
                        "cat": "plan",
                        "evt": "clarification_waiting",
                        "series_key": active.series_key,
                        "round": active.round_number,
                        "deadline_at": active.deadline_at.isoformat(),
                        "reason": "clarification_request_delivery_pending",
                    },
                    correlation_id=correlation_id,
                )
            )
            return False, None
        comments = self._scm.get_comments(issue.number)
        current = active.rounds[-1]
        question = next(
            (item for item in comments if item.id == int(current["question_comment_id"])), None
        )
        if question is None:
            self._finish_record(active)
            self._publish_terminal(
                issue.number,
                correlation_id,
                "clarification_question_missing",
                series_key=active.series_key,
            )
            return False, None
        if (
            comment_body_digest(question) != current["question_digest"]
            or comment_revision(question) != current["question_revision"]
        ):
            self._finish_record(active)
            self._publish_terminal(
                issue.number,
                correlation_id,
                "clarification_question_edited",
                series_key=active.series_key,
            )
            return False, None
        request = parse_clarification_request(question.body)
        if request is None:
            self._finish_record(active)
            self._publish_terminal(
                issue.number,
                correlation_id,
                "clarification_request_invalid",
                series_key=active.series_key,
            )
            return False, None
        candidates: list[tuple[Comment, tuple[str, ...]]] = []
        for comment in comments:
            parsed = parse_clarification_answer(comment, request)
            if parsed is not None:
                candidates.append((comment, parsed))
        if len(candidates) > 1:
            self._finish_record(active)
            self._publish_terminal(
                issue.number,
                correlation_id,
                "clarification_answer_duplicate",
                series_key=active.series_key,
            )
            return False, None
        if not candidates:
            if self._now() > active.deadline_at:
                terminal = replace(
                    active,
                    status="timed_out",
                    version=active.version + 1,
                    updated_at=self._now(),
                )
                self._write(terminal, expected_version=active.version)
                self._publish_terminal(
                    issue.number,
                    correlation_id,
                    "clarification_timeout",
                    series_key=active.series_key,
                )
            else:
                self._bus.publish(
                    ClarificationWaiting(
                        payload={
                            "issue": issue.number,
                            "cat": "plan",
                            "evt": "clarification_waiting",
                            "series_key": active.series_key,
                            "round": active.round_number,
                            "deadline_at": active.deadline_at.isoformat(),
                        },
                        correlation_id=correlation_id,
                    )
                )
            return False, None

        answer, answers = candidates[0]
        answer_time = _parse_time(answer.created_at)
        revision = comment_revision(answer)
        revision_time = _parse_time(revision)
        question_revision_time = _parse_time(comment_revision(question))
        if (
            answer_time is None
            or revision_time is None
            or answer_time > active.deadline_at
            or revision_time > active.deadline_at
        ):
            terminal = replace(
                active,
                status="timed_out",
                version=active.version + 1,
                updated_at=self._now(),
            )
            self._write(terminal, expected_version=active.version)
            self._publish_terminal(
                issue.number,
                correlation_id,
                "clarification_answer_late_or_unversioned",
                series_key=active.series_key,
            )
            return False, None
        if (
            not answer.user
            or question_revision_time is None
            or answer_time < question_revision_time
            or revision_time < answer_time
        ):
            self._finish_record(active)
            self._publish_terminal(
                issue.number,
                correlation_id,
                "clarification_answer_outside_bound_window",
                series_key=active.series_key,
            )
            return False, None

        answered_round = dict(current)
        answered_round.update(
            {
                "answers": list(answers),
                "answer_comment_id": answer.id,
                "answer_digest": comment_body_digest(answer),
                "answer_actor": answer.user,
                "answer_created_at": answer.created_at,
                "answer_revision": revision,
            }
        )
        unresolved_indexes = {
            index
            for index, value in enumerate(answers)
            if assess_issue_readiness(
                Issue(number=issue.number, title=issue.title, body=value, state=issue.state)
            ).state
            != "ready"
        }
        if not answers:
            unresolved_indexes = set(range(len(request.questions)))
        unresolved = bool(unresolved_indexes)
        recorded = replace(
            active,
            rounds=(*active.rounds[:-1], answered_round),
            version=active.version + 1,
            updated_at=self._now(),
        )
        self._write(recorded, expected_version=active.version)
        if unresolved:
            if active.round_number >= MAX_CLARIFICATION_ROUNDS:
                terminal = replace(
                    recorded,
                    status="exhausted",
                    version=recorded.version + 1,
                    updated_at=self._now(),
                )
                self._write(terminal, expected_version=recorded.version)
                self._publish_terminal(
                    issue.number,
                    correlation_id,
                    "clarification_rounds_exhausted",
                    series_key=active.series_key,
                )
                return False, None
            followups = tuple(
                f"Bitte beantworte die noch offene Frage abschließend: {question}"
                for index, question in enumerate(request.questions)
                if index in unresolved_indexes
            )
            next_deadline = self._now() + timedelta(seconds=int(self._wait_seconds or 0))
            next_seed = replace(
                recorded,
                round_number=recorded.round_number + 1,
                deadline_at=next_deadline,
                rounds=(
                    *recorded.rounds,
                    {
                        "round_number": recorded.round_number + 1,
                        "questions": list(followups[:3]),
                        "question_comment_id": 0,
                        "question_digest": "",
                        "question_revision": "",
                    },
                ),
                version=recorded.version + 1,
                updated_at=self._now(),
            )
            self._write(next_seed, expected_version=recorded.version)
            try:
                self._question_round(next_seed, followups[:3])
            except StateStoreError as exc:
                self._finish_record(next_seed)
                self._publish_terminal(
                    issue.number,
                    correlation_id,
                    exc.code,
                    series_key=next_seed.series_key,
                )
            except Exception:  # noqa: BLE001 - SCM adapter failures remain retryable
                self._bus.publish(
                    ClarificationWaiting(
                        payload={
                            "issue": issue.number,
                            "cat": "plan",
                            "evt": "clarification_waiting",
                            "series_key": next_seed.series_key,
                            "round": next_seed.round_number,
                            "deadline_at": next_seed.deadline_at.isoformat(),
                            "reason": "clarification_request_delivery_pending",
                        },
                        correlation_id=correlation_id,
                    )
                )
            return False, None

        accepted = replace(
            recorded,
            status="answered",
            version=recorded.version + 1,
            updated_at=self._now(),
        )
        self._write(accepted, expected_version=recorded.version)
        basis = self._basis(accepted)
        self._bus.publish(
            ClarificationAccepted(
                payload={
                    "issue": issue.number,
                    "cat": "plan",
                    "evt": "clarification_accepted",
                    "series_key": accepted.series_key,
                    "rounds": accepted.round_number,
                    "basis_digest": basis.digest,
                },
                correlation_id=correlation_id,
            )
        )
        return True, basis
