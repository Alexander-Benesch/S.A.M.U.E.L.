from __future__ import annotations

from pathlib import Path

import pytest

from samuel.core.bus import Bus, DeadLetterQueue
from samuel.core.evaluation_observation import EvaluationObservationIdentity
from samuel.core.evaluation_subject import EvaluationSubject
from samuel.core.events import Event, GateEvaluationCompleted, GateEvaluationUnavailable
from samuel.core.ports import IObservationStore
from samuel.core.state import (
    EvaluationTerminalRecord,
    ObservationRecord,
    ScoreDerivationRecord,
    StateStoreError,
)
from samuel.slices.evaluation.handler import EvaluationHandler


class _MemoryObservationStore(IObservationStore):
    def __init__(self) -> None:
        self.observations: dict[str, ObservationRecord] = {}
        self.derivations: dict[str, ScoreDerivationRecord] = {}
        self.terminals: dict[str, EvaluationTerminalRecord] = {}

    def put_observation(self, record: ObservationRecord) -> bool:
        if record.observation_key in self.observations:
            return False
        self.observations[record.observation_key] = record
        return True

    def get_observation(self, observation_key: str) -> ObservationRecord | None:
        return self.observations.get(observation_key)

    def list_observations(self, issue_number: int | None = None) -> list[ObservationRecord]:
        return list(self.observations.values())

    def put_derivation(self, record: ScoreDerivationRecord) -> bool:
        if record.observation_key not in self.observations:
            raise ValueError("missing observation")
        if record.score_key in self.derivations:
            return False
        self.derivations[record.score_key] = record
        return True

    def get_derivation(self, score_key: str) -> ScoreDerivationRecord | None:
        return self.derivations.get(score_key)

    def list_derivations(self, issue_number: int | None = None) -> list[ScoreDerivationRecord]:
        return list(self.derivations.values())

    def put_terminal(self, record: EvaluationTerminalRecord) -> bool:
        if record.terminal_key in self.terminals:
            return False
        self.terminals[record.terminal_key] = record
        return True

    def get_terminal(self, terminal_key: str) -> EvaluationTerminalRecord | None:
        return self.terminals.get(terminal_key)

    def list_terminals(self, issue_number: int | None = None) -> list[EvaluationTerminalRecord]:
        return list(self.terminals.values())


def _handler(bus: Bus, tmp_path: Path) -> tuple[EvaluationHandler, _MemoryObservationStore]:
    store = _MemoryObservationStore()
    handler = EvaluationHandler(
        bus,
        config_dir="config",
        data_dir=tmp_path,
        observation_store=store,
    )
    handler.register_bound_observer()
    return handler, store


def _subject() -> EvaluationSubject:
    return EvaluationSubject(
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        contract_hash="sha256:" + "c" * 64,
        policy_version="gates.v1",
        policy_digest="sha256:" + "d" * 64,
    )


def _acceptance(results: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "evaluation_subject": _subject().as_dict(),
        "contract": {
            "schema_version": 2,
            "revision": "1",
            "contract_hash": _subject().contract_hash,
            "criteria": [],
            "scope": None,
            "approval": {"state": "unapproved"},
        },
        "results": results,
    }


def _event(results: list[dict], correlation_id: str = "run-1") -> GateEvaluationCompleted:
    acceptance = _acceptance(results)
    gate_passed = all(item["status"] == "passed" for item in results)
    gates = [
        {
            "gate": 11,
            "passed": gate_passed,
            "executed": True,
            "status": "passed" if gate_passed else "failed",
            "reason_code": "gate_11_passed" if gate_passed else "gate_11_failed",
            "reason": "",
            "owasp_risk": None,
            "authority": "required",
            "evaluation_subject": _subject().as_dict(),
        }
    ]
    identity = EvaluationObservationIdentity.build(
        subject=_subject(),
        gate_results=gates,
        acceptance_evidence=acceptance,
    )
    return GateEvaluationCompleted(
        payload={
            "issue": 399,
            "gate_results": gates,
            "acceptance_evidence": acceptance,
            "evaluation_subject": _subject().as_dict(),
            "gate_result_schema_version": 2,
            "observation_schema_version": identity.schema_version,
            "observation_key": identity.observation_key,
            "evidence_digest": identity.evidence_digest,
            "evidence_provenance": {
                "gate_results": "bound_evaluation_subject",
                "acceptance_evidence": "bound_acceptance_evidence",
            },
        },
        correlation_id=correlation_id,
    )


def _preflight_blocked_event() -> GateEvaluationCompleted:
    subject = _subject()
    gates = [
        {
            "gate": "7b",
            "passed": False,
            "executed": True,
            "status": "failed",
            "reason_code": "gate_7b_failed",
            "reason": "scope violation",
            "authority": "required",
            "evaluation_subject": subject.as_dict(),
        },
        {
            "gate": 11,
            "passed": None,
            "executed": False,
            "status": "skipped_precondition",
            "reason_code": "gate_11_skipped_precondition",
            "reason": "preflight failed",
            "authority": "required",
            "evaluation_subject": subject.as_dict(),
        },
    ]
    identity = EvaluationObservationIdentity.build(
        subject=subject,
        gate_results=gates,
        acceptance_evidence=None,
    )
    return GateEvaluationCompleted(
        payload={
            "issue": 620,
            "blocked": True,
            "gate_results": gates,
            "acceptance_evidence": None,
            "evaluation_subject": subject.as_dict(),
            "gate_result_schema_version": 2,
            "observation_schema_version": identity.schema_version,
            "observation_key": identity.observation_key,
            "evidence_digest": identity.evidence_digest,
            "evidence_provenance": {
                "gate_results": "bound_evaluation_subject",
                "acceptance_evidence": "missing_evidence",
            },
        },
        correlation_id="preflight-blocked",
    )


def test_bound_observer_scores_each_tag_once_and_keeps_empty_families_na(
    tmp_path: Path,
) -> None:
    bus = Bus()
    observed: list[Event] = []
    bus.subscribe("ScoreObserved", observed.append)
    _handler(bus, tmp_path)

    bus.publish(
        _event(
            [
                {
                    "criterion_id": "AC-diff",
                    "status": "passed",
                    "reason": "ok",
                    "tag": "DIFF",
                    "evidence": {"changed": True},
                },
                {
                    "criterion_id": "AC-test",
                    "status": "failed",
                    "reason": "failed",
                    "tag": "TEST",
                    "evidence": {"exit_code": 1},
                },
            ]
        )
    )

    assert len(observed) == 1
    payload = observed[0].payload
    assert payload["non_binding"] is True
    assert payload["scoreability"] == "scoreable"
    assert payload["score"] == 0.5
    assert payload["categories"]["hallucination_free"]["score"] == 1.0
    assert payload["categories"]["test_pass_rate"]["score"] == 0.0
    assert payload["categories"]["syntax_valid"]["score"] is None
    assert payload["categories"]["scope_compliant"]["score"] is None
    assert [item["category"] for item in payload["criteria"]] == [
        "hallucination_free",
        "test_pass_rate",
    ]


def test_bound_observer_is_idempotent_but_tracks_replayed_correlation(tmp_path: Path) -> None:
    bus = Bus()
    observed: list[Event] = []
    bus.subscribe("ScoreObserved", observed.append)
    _, store = _handler(bus, tmp_path)
    first = _event(
        [
            {
                "criterion_id": "AC-test",
                "status": "passed",
                "reason": "ok",
                "tag": "TEST",
                "evidence": {"exit_code": 0},
            }
        ],
        correlation_id="run-1",
    )
    replay = _event(first.payload["acceptance_evidence"]["results"], correlation_id="run-2")

    bus.publish(first)
    bus.publish(replay)

    assert len(observed) == 1
    assert len(store.observations) == 1
    assert len(store.derivations) == 1


def test_manual_only_observation_is_explicitly_not_scoreable(tmp_path: Path) -> None:
    bus = Bus()
    observed: list[Event] = []
    bus.subscribe("ScoreObserved", observed.append)
    _handler(bus, tmp_path)

    bus.publish(
        _event(
            [
                {
                    "criterion_id": "AC-manual",
                    "status": "manual_pending",
                    "reason": "receipt required",
                    "tag": "MANUAL",
                    "evidence": None,
                }
            ]
        )
    )

    assert observed[0].payload["score"] is None
    assert observed[0].payload["scoreability"] == "not_scoreable"
    assert observed[0].payload["not_scoreable_reason"] == ("no_automatic_applicable_criteria")


def test_preflight_block_is_persisted_as_v2_not_scoreable_observation(tmp_path: Path) -> None:
    bus = Bus()
    observed: list[Event] = []
    bus.subscribe("ScoreObserved", observed.append)
    _, store = _handler(bus, tmp_path)

    bus.publish(_preflight_blocked_event())

    assert len(observed) == 1
    assert observed[0].payload["score"] is None
    assert observed[0].payload["scoreability"] == "not_scoreable"
    assert observed[0].payload["not_scoreable_reason"] == "missing_acceptance_evidence"
    observation = next(iter(store.observations.values()))
    assert observation.observation_schema == "bound.v2"
    assert observation.payload["acceptance_evidence"] is None
    assert observation.payload["gate_results"][1]["status"] == "skipped_precondition"


def test_missing_evidence_reduces_coverage_without_becoming_a_failed_score(
    tmp_path: Path,
) -> None:
    bus = Bus()
    observed: list[Event] = []
    bus.subscribe("ScoreObserved", observed.append)
    _handler(bus, tmp_path)

    bus.publish(
        _event(
            [
                {
                    "criterion_id": "AC-test",
                    "status": "missing_evidence",
                    "reason": "coverage artifact absent",
                    "tag": "TEST",
                    "evidence": None,
                }
            ]
        )
    )

    payload = observed[0].payload
    assert payload["score"] is None
    assert payload["scoreability"] == "not_scoreable"
    assert payload["coverage"] == {
        "automatic_total": 1,
        "automatic_evaluated": 0,
        "ratio": 0.0,
    }
    assert payload["categories"]["test_pass_rate"]["criteria_total"] == 1
    assert payload["categories"]["test_pass_rate"]["criteria_evaluated"] == 0


def test_invalid_bound_payload_isolated_in_dlq(tmp_path: Path) -> None:
    bus = Bus()
    bus.dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    _handler(bus, tmp_path)
    event = _event([])
    event.payload["observation_key"] = "sha256:" + "0" * 64

    bus.publish(event)

    entries = bus.dlq.list()
    assert len(entries) == 1
    assert entries[0]["event_name"] == "GateEvaluationCompleted"
    assert "observation_key" in entries[0]["error"]


def test_unavailable_evaluation_is_persisted_without_score(tmp_path: Path) -> None:
    bus = Bus()
    observed: list[Event] = []
    bus.subscribe("ScoreObserved", observed.append)
    _, store = _handler(bus, tmp_path)

    bus.publish(
        GateEvaluationUnavailable(
            payload={
                "issue": 627,
                "terminal_key": "sha256:" + "1" * 64,
                "status": "not_evaluated",
                "reason": "subject unavailable",
            },
            correlation_id="run-unavailable",
        )
    )

    terminal = next(iter(store.terminals.values()))
    assert terminal.status == "unavailable"
    assert terminal.payload["correlation_id"] == "run-unavailable"
    assert observed == []
    assert store.observations == {}
    assert store.derivations == {}


def test_observation_store_failure_is_redacted_dlq_evidence_not_gate_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = Bus()
    bus.dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    observed: list[Event] = []
    bus.subscribe("ScoreObserved", observed.append)
    _, store = _handler(bus, tmp_path)

    def fail(_record: ObservationRecord) -> bool:
        raise StateStoreError("state_locked", "Runtime-state database is locked or busy")

    monkeypatch.setattr(store, "put_observation", fail)
    bus.publish(_event([]))

    entries = bus.dlq.list()
    assert len(entries) == 1
    assert entries[0]["event_name"] == "GateEvaluationCompleted"
    assert entries[0]["error"].endswith("Runtime-state database is locked or busy")
    assert observed == []
