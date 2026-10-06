"""#153: Tests fuer den QualityMetricsHandler (issue-Korrelation, Registry, Event)."""

from __future__ import annotations

from samuel.core.bus import Bus
from samuel.core.events import EvalCompleted, EvalFailed, LLMCallCompleted, ScoreObserved
from samuel.core.ports import IQualityMetricsRegistry
from samuel.slices.quality_metrics.handler import QualityMetricsHandler


class _FakeRegistry(IQualityMetricsRegistry):
    def __init__(self):
        self.records: list[tuple] = []

    def record(self, provider, model, task, score, passed, metadata=None):
        self.records.append((provider, model, task, score, passed, metadata))

    def score_for(self, provider, model, task):
        return None

    def aggregates(self):
        return []


def _wire():
    bus = Bus()
    reg = _FakeRegistry()
    h = QualityMetricsHandler(bus, reg)
    h.register()
    published: list = []
    bus.subscribe("QualityCheckCompleted", lambda e: published.append(e))
    return bus, reg, published


def _score_observed(issue: int, score: float = 0.9) -> ScoreObserved:
    return ScoreObserved(
        payload={
            "issue": issue,
            "score": score,
            "scoreability": "scoreable",
            "non_binding": True,
            "evidence_origin": "bound_acceptance_evidence",
            "observation_key": "sha256:" + "a" * 64,
            "score_key": "sha256:" + "c" * 64,
            "scoring_policy_version": "eval.v1",
            "scoring_policy_digest": "sha256:" + "b" * 64,
            "formula_version": "bound.v1",
            "categories": {"tests": {"score": score}},
        }
    )


def test_llm_then_bound_observation_records_and_publishes():
    bus, reg, published = _wire()
    bus.publish(
        LLMCallCompleted(
            payload={
                "provider": "deepseek",
                "model": "deepseek-chat",
                "task": "implementation",
                "issue": 153,
            }
        )
    )
    bus.publish(_score_observed(153))
    assert reg.records[0][:5] == (
        "deepseek",
        "deepseek-chat",
        "implementation",
        0.9,
        None,
    )
    assert len(published) == 1
    p = published[0].payload
    assert p["provider"] == "deepseek"
    assert p["task"] == "implementation"
    assert p["score"] == 0.9
    assert p["passed"] is None
    assert p["criteria"] == {"tests": {"score": 0.9}}
    assert p["issue"] == 153


def test_eval_without_prior_llm_is_ignored():
    bus, reg, published = _wire()
    bus.publish(_score_observed(999, 1.0))
    assert reg.records == []
    assert published == []


def test_historical_eval_events_are_not_consumed():
    bus, reg, published = _wire()
    bus.publish(
        LLMCallCompleted(
            payload={
                "provider": "p",
                "model": "m",
                "task": "impl",
                "issue": 1,
            }
        )
    )
    bus.publish(EvalCompleted(payload={"issue": 1, "score": 0.9}))
    bus.publish(EvalFailed(payload={"issue": 1, "score": 0.4}))
    assert reg.records == []
    assert published == []


def test_last_llm_call_per_issue_wins():
    bus, reg, published = _wire()
    bus.publish(
        LLMCallCompleted(
            payload={
                "provider": "p",
                "model": "m",
                "task": "planning",
                "issue": 7,
            }
        )
    )
    bus.publish(
        LLMCallCompleted(
            payload={
                "provider": "p",
                "model": "m",
                "task": "implementation",
                "issue": 7,
            }
        )
    )
    bus.publish(_score_observed(7, 1.0))
    # nur der letzte Call (implementation) wird grade-t
    assert reg.records[0][:5] == ("p", "m", "implementation", 1.0, None)


def test_eval_without_score_is_ignored():
    bus, reg, published = _wire()
    bus.publish(
        LLMCallCompleted(
            payload={
                "provider": "p",
                "model": "m",
                "task": "impl",
                "issue": 1,
            }
        )
    )
    invalid = _score_observed(1)
    invalid.payload.pop("score")
    bus.publish(invalid)
    assert reg.records == []


def test_consumes_only_provenance_labelled_score_observation():
    bus = Bus()
    reg = _FakeRegistry()
    handler = QualityMetricsHandler(bus, reg)
    handler.register()
    bus.publish(
        LLMCallCompleted(payload={"provider": "p", "model": "m", "task": "impl", "issue": 399})
    )
    bus.publish(EvalCompleted(payload={"issue": 399, "score": 1.0}))
    bus.publish(ScoreObserved(payload={"issue": 399, "score": 0.7}))
    assert reg.records == []

    bus.publish(_score_observed(399, 0.7))

    assert reg.records[0][:5] == ("p", "m", "impl", 0.7, None)
    assert reg.records[0][5]["non_binding"] is True
