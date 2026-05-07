from __future__ import annotations

from typing import Any

from samuel.core.bus import Bus
from samuel.core.commands import HealCommand
from samuel.core.events import Event
from samuel.core.ports import IConfig, ILLMProvider
from samuel.core.types import LLMResponse
from samuel.slices.healing.handler import HealingHandler


class MockLLM(ILLMProvider):
    def __init__(self, text: str = "fix suggestion") -> None:
        self._text = text

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self._text, input_tokens=100, output_tokens=50)

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 200_000


class MockConfig(IConfig):
    def __init__(self, flags: dict[str, bool] | None = None, values: dict[str, Any] | None = None):
        self._flags = flags or {}
        self._values = values or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def feature_flag(self, name: str) -> bool:
        return self._flags.get(name, False)

    def reload(self) -> None:
        pass


def _collect_events(bus: Bus) -> list[Event]:
    events: list[Event] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


class TestHealingHandler:
    def test_disabled_by_default(self):
        bus = Bus()
        handler = HealingHandler(bus, config=MockConfig())
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "disabled"

    def test_heals_when_enabled(self):
        bus = Bus()
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is True
        assert result["failure_type"] == "eval"
        assert "suggestion" in result

    def test_budget_exhausted_after_max_attempts(self):
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(
            flags={"healing": True},
            values={"healing.max_attempts": 2},
        )
        handler = HealingHandler(bus, llm=MockLLM(), config=config)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 3},
        ))
        assert result["healed"] is False
        assert result["reason"] == "budget_exhausted"
        assert any(e.name == "WorkflowBlocked" for e in events)

    def test_token_budget_exhausted(self):
        bus = Bus()
        _collect_events(bus)
        config = MockConfig(
            flags={"healing": True},
            values={"healing.max_tokens": 100},
        )
        handler = HealingHandler(bus, llm=MockLLM(), config=config)
        handler._token_budget_used[42] = 200
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "token_budget_exhausted"

    def test_no_llm_blocks(self):
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=None, config=config)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "no_llm"
        assert any(e.name == "WorkflowBlocked" for e in events)

    def test_token_tracking_accumulates(self):
        bus = Bus()
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        # #239: aufsteigende Scores damit no-improvement-Stop nicht greift —
        # sonst aborted Runde 2 ohne LLM-Call und Tokens akkumulieren nicht.
        handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1, "score": 0.5},
        ))
        handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 2, "score": 0.7},
        ))

        assert handler._token_budget_used[42] == 300

    def test_no_config_means_disabled(self):
        bus = Bus()
        handler = HealingHandler(bus, llm=MockLLM(), config=None)
        result = handler.handle(HealCommand(
            payload={"issue": 42, "failure_type": "eval", "attempt": 1},
        ))
        assert result["healed"] is False
        assert result["reason"] == "disabled"


class TestHealingLoop:
    """#239: EvalFailed-Retry-Loop mit max 3 Runden + No-Improvement-Stop."""

    def test_healing_loop_score_improves(self):
        """Round 1: Score 0.5; Round 2: Score 0.7 -> HealingSuggested fliegt
        und Workflow-Engine triggert via Step die naechste Implement-Runde."""
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        # Runde 1: prev_score=None
        handler.handle(HealCommand(payload={
            "issue": 42, "failure_type": "eval", "attempt": 1, "score": 0.5,
        }))
        # Runde 2: current 0.7 > prev 0.5
        handler.handle(HealCommand(payload={
            "issue": 42, "failure_type": "eval", "attempt": 2, "score": 0.7,
        }))

        names = [e.name for e in events]
        assert names.count("HealingSuggested") == 2
        assert names.count("HealingAttemptStarted") == 2
        assert names.count("HealingAttemptCompleted") == 2
        # Score-Delta korrekt im zweiten Completed-Event
        completed_2 = [e for e in events if e.name == "HealingAttemptCompleted"][1]
        assert completed_2.payload["status"] == "improved"
        assert abs(completed_2.payload["score_delta"] - 0.2) < 1e-9

    def test_healing_loop_no_improvement_aborts(self):
        """Round 1: 0.5; Round 2: 0.5 -> HealingAborted reason
        'no improvement after heal' + WorkflowBlocked."""
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        handler.handle(HealCommand(payload={
            "issue": 42, "failure_type": "eval", "attempt": 1, "score": 0.5,
        }))
        result = handler.handle(HealCommand(payload={
            "issue": 42, "failure_type": "eval", "attempt": 2, "score": 0.5,
        }))

        assert result["healed"] is False
        assert result["reason"] == "no_improvement"
        names = [e.name for e in events]
        assert "HealingAborted" in names
        # WorkflowBlocked mit korrekter Reason
        wb = next(e for e in events if e.name == "WorkflowBlocked")
        assert "no improvement after heal" in wb.payload["reason"]
        # HealingAttemptCompleted mit status no_improvement
        nc = [e for e in events if e.name == "HealingAttemptCompleted"]
        assert nc[-1].payload["status"] == "no_improvement"
        # Keine HealingSuggested in Round 2
        suggested = [e for e in events if e.name == "HealingSuggested"]
        assert len(suggested) == 1  # nur Round 1

    def test_healing_loop_budget_exhausted(self):
        """max_attempts=2, attempt=3 -> HealingAborted reason
        'budget_exhausted'."""
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(
            flags={"healing": True}, values={"healing.max_attempts": 2},
        )
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        result = handler.handle(HealCommand(payload={
            "issue": 42, "failure_type": "eval", "attempt": 3, "score": 0.5,
        }))

        assert result["healed"] is False
        assert result["reason"] == "budget_exhausted"
        names = [e.name for e in events]
        assert "HealingAborted" in names
        ab = next(e for e in events if e.name == "HealingAborted")
        assert "budget exhausted" in ab.payload["reason"]

    def test_healing_loop_three_rounds_max(self):
        """4 EvalFailed-Events: 1-3 produzieren HealingSuggested, der 4. wird
        durch budget_exhausted abgebrochen."""
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        # Aufsteigende Scores damit no_improvement nicht zwischendurch greift
        for i, sc in enumerate([0.4, 0.5, 0.6, 0.7], start=1):
            handler.handle(HealCommand(payload={
                "issue": 42, "failure_type": "eval", "attempt": i, "score": sc,
            }))

        suggested = [e for e in events if e.name == "HealingSuggested"]
        aborted = [e for e in events if e.name == "HealingAborted"]
        assert len(suggested) == 3, f"erwartet 3 Suggested, gesehen {len(suggested)}"
        assert len(aborted) == 1
        assert "budget" in aborted[0].payload["reason"]


class TestHealingCharterCompliance:
    """§1.1 Sprachagnostik + §1.2 Bus-Resilience pro Phase-1-Charter."""

    def test_healing_disabled_feature_flag_graceful(self):
        """§1.2: healing=false -> handle returnt healed=False, kein Crash,
        keine Events publisht."""
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(flags={"healing": False})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        result = handler.handle(HealCommand(payload={
            "issue": 42, "failure_type": "eval", "attempt": 1, "score": 0.5,
        }))

        assert result["healed"] is False
        assert result["reason"] == "disabled"
        # Keine Healing-Events bei deaktiviertem Flag
        names = [e.name for e in events]
        assert "HealingAttemptStarted" not in names
        assert "HealingSuggested" not in names

    def test_healing_handles_non_python_failure_context(self):
        """§1.1: failure_context mit go-Datei-Pfad — sprachneutraler Pfad."""
        bus = Bus()
        events = _collect_events(bus)
        config = MockConfig(flags={"healing": True})
        handler = HealingHandler(bus, llm=MockLLM(), config=config)

        result = handler.handle(HealCommand(payload={
            "issue": 42,
            "failure_type": "eval",
            "attempt": 1,
            "score": 0.5,
            "context": {
                "file": "cmd/server/main.go",
                "language": "go",
                "test": "TestServer_HealthEndpoint",
            },
        }))

        assert result["healed"] is True
        assert "HealingSuggested" in [e.name for e in events]