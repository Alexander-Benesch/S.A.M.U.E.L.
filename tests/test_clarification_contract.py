from __future__ import annotations

from samuel.core.acceptance import (
    ClarificationBasis,
    ClarificationRequest,
    assess_issue_readiness,
    comment_body_digest,
    comment_revision,
    parse_clarification_answer,
    render_clarification_request,
    verify_clarification_basis,
)
from samuel.core.types import Comment, Issue


def test_readiness_uses_only_explicit_gaps_and_limits_questions() -> None:
    clear = Issue(1, "Klar", "Implementiere den beschriebenen Endpunkt.", "open")
    assert assess_issue_readiness(clear).state == "ready"

    vague = Issue(
        2,
        "Offene Punkte",
        "TBD: Format\nOffen: Timeout\nTODO: Fehlercode\nUnklar: vierte Frage",
        "open",
    )
    decision = assess_issue_readiness(vague)
    assert decision.state == "needs_clarification"
    assert len(decision.questions) == 3


def test_readiness_detects_provable_grep_contradiction() -> None:
    issue = Issue(
        3,
        "Widerspruch",
        '- [ ] [GREP] "entry.score, entry.name.casefold()"\n'
        '- [ ] [GREP:NOT] "entry.score, entry.name.casefold()"',
        "open",
    )
    decision = assess_issue_readiness(issue)
    assert decision.state == "needs_clarification"
    assert decision.reasons == ("explicit_acceptance_contradiction",)


def test_answer_and_basis_are_bound_to_exact_comment_revision() -> None:
    request = ClarificationRequest(
        schema_version=1,
        series_key="clr-123",
        round_number=1,
        source_digest="sha256:" + "a" * 64,
        deadline_at="2026-09-20T10:00:00+00:00",
        questions=("Welches Timeout?",),
    )
    question = Comment(
        10,
        render_clarification_request(request),
        "samuel",
        "2026-09-19T10:00:00Z",
        "2026-09-19T10:00:00Z",
    )
    answer = Comment(
        11,
        "S.A.M.U.E.L.-Klärung: clr-123/R1\n1. 30 Sekunden",
        "alice",
        "2026-09-19T10:05:00Z",
        "2026-09-19T10:05:00Z",
    )
    assert parse_clarification_answer(answer, request) == ("30 Sekunden",)
    duplicate_number = Comment(
        12,
        "S.A.M.U.E.L.-Klärung: clr-123/R1\n1. 30 Sekunden\n1. 60 Sekunden",
        "alice",
        "2026-09-19T10:05:00Z",
        "2026-09-19T10:05:00Z",
    )
    assert parse_clarification_answer(duplicate_number, request) == ()
    basis = ClarificationBasis(
        schema_version=1,
        series_key="clr-123",
        source_digest=request.source_digest,
        rounds=(
            {
                "round_number": 1,
                "questions": ["Welches Timeout?"],
                "question_comment_id": question.id,
                "question_digest": comment_body_digest(question),
                "question_revision": comment_revision(question),
                "answers": ["30 Sekunden"],
                "answer_comment_id": answer.id,
                "answer_digest": comment_body_digest(answer),
                "answer_actor": answer.user,
                "answer_created_at": answer.created_at,
                "answer_revision": comment_revision(answer),
            },
        ),
    )
    assert verify_clarification_basis(basis, [question, answer]) == (True, "verified")
    edited = Comment(
        answer.id,
        answer.body + " geändert",
        answer.user,
        answer.created_at,
        "2026-09-19T10:06:00Z",
    )
    assert verify_clarification_basis(basis, [question, edited]) == (
        False,
        "clarification_answer_edited",
    )

    early = Comment(
        answer.id,
        answer.body,
        answer.user,
        "2026-09-19T09:59:00Z",
        "2026-09-19T09:59:00Z",
    )
    early_basis = ClarificationBasis(
        schema_version=1,
        series_key=basis.series_key,
        source_digest=basis.source_digest,
        rounds=(
            {
                **basis.rounds[0],
                "answer_digest": comment_body_digest(early),
                "answer_created_at": early.created_at,
                "answer_revision": comment_revision(early),
            },
        ),
    )
    assert verify_clarification_basis(early_basis, [question, early]) == (
        False,
        "clarification_answer_outside_bound_window",
    )
