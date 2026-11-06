from __future__ import annotations

import threading

from samuel.core.bus import Bus
from samuel.core.events import Event, PRCreated, ScoreObserved
from samuel.core.types import Comment
from samuel.slices.evaluation.presentation import (
    ScorePresentationHandler,
    render_score_observation,
)


def _score() -> dict:
    return {
        "issue": 399,
        "score": 0.75,
        "status": "observed",
        "coverage": 0.5,
        "scoring_policy_version": "policy.v1",
        "formula_version": "formula.v1",
        "evidence_origin": "bound_acceptance_evidence",
        "observation_key": "sha256:abc",
        "evaluation_subject": {"head_sha": "a" * 40},
        "categories": {
            "test_pass_rate": {
                "applicable": True,
                "total": 2,
                "passed": 1,
                "score": 0.5,
            },
            "syntax_valid": {
                "applicable": False,
                "total": 0,
                "passed": 0,
                "score": None,
            },
        },
    }


def test_markdown_is_explicitly_non_binding() -> None:
    body = render_score_observation(_score())
    assert "Nicht bindende Qualitätsbeobachtung" in body
    assert "kein PASS/FAIL- oder Merge-Signal" in body
    assert "Required-Gate-Profil" in body
    assert "Baseline" not in body


class _SCM:
    def __init__(self) -> None:
        self.comments: list[tuple[int, str]] = []
        self.called = threading.Event()

    def post_comment(self, number: int, body: str) -> Comment:
        self.comments.append((number, body))
        self.called.set()
        return Comment(id=1, body=body, user="bot")


def test_score_subscriber_does_no_external_io_and_pr_queues_presentation() -> None:
    bus = Bus()
    scm = _SCM()
    handler = ScorePresentationHandler(bus, scm=scm)
    handler.register()

    cached = handler.on_score_observed(Event(name="ScoreObserved", payload=_score()))
    assert cached == {"cached": True, "external_io": False}
    assert scm.comments == []

    result = handler.on_pr_created(
        Event(
            name="PRCreated",
            payload={
                "issue": 399,
                "pr_number": 77,
                "evaluation_subject": {"head_sha": "a" * 40},
            },
        )
    )
    assert result == {"queued": True, "external_io": "background"}
    assert scm.called.wait(1.0)
    assert scm.comments[0][0] == 77


def test_bus_delivery_joins_observation_and_pr() -> None:
    bus = Bus()
    scm = _SCM()
    handler = ScorePresentationHandler(bus, scm=scm)
    handler.register()

    bus.publish(ScoreObserved(payload=_score()))
    bus.publish(
        PRCreated(
            payload={
                "issue": 399,
                "pr_number": 78,
                "evaluation_subject": {"head_sha": "a" * 40},
            }
        )
    )
    assert scm.called.wait(1.0)
    assert scm.comments[0][0] == 78


def test_blocked_gate_observation_is_not_retained_for_a_pr_that_cannot_exist() -> None:
    handler = ScorePresentationHandler(Bus(), scm=_SCM())
    payload = _score()
    payload["gate_blocked"] = True

    result = handler.on_score_observed(Event(name="ScoreObserved", payload=payload))

    assert result == {"cached": False, "reason": "no_pr_for_blocked_gate_run"}
    assert handler._scores == {}
