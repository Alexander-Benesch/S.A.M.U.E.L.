from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from samuel.adapters.llm.retry import RetryLLMAdapter
from samuel.adapters.llm.workflow_budget import (
    LogicalCallLLMAdapter,
    WorkflowTokenBudgetLLMAdapter,
)
from samuel.adapters.state.sqlite import SQLiteStateStore
from samuel.core.bus import Bus
from samuel.core.errors import ProviderUnavailable
from samuel.core.issue_context import issue_scope
from samuel.core.ports import ILLMProvider
from samuel.core.state import StateStoreError, WorkflowBudgetAdmissionRecord
from samuel.core.types import LLMResponse


class SequenceProvider(ILLMProvider):
    def __init__(self, outcomes: Iterable[LLMResponse | Exception]) -> None:
        self._outcomes = iter(outcomes)
        self.calls = 0

    def complete(self, messages: list[dict], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        outcome = next(self._outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def estimate_tokens(self, text: str) -> int:
        return len(text)

    @property
    def context_window(self) -> int:
        return 100_000


def _store(tmp_path: Path, *, token_limit: int = 10_000) -> tuple[SQLiteStateStore, str]:
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        f"36 25 0:32 / {tmp_path} rw,relatime - ext4 device rw\n",
        encoding="utf-8",
    )
    store = SQLiteStateStore(tmp_path / "state", mountinfo_path=mountinfo)
    key = "budget-test"
    store.authority.put_budget_admission(
        WorkflowBudgetAdmissionRecord(
            admission_key=key,
            repository="owner/repo",
            issue_number=549,
            invocation_digest="sha256:invocation",
            source_digest="sha256:source",
            policy_digest="sha256:policy",
            correlation_id="run-549",
            token_limit=token_limit,
        )
    )
    return store, key


def _adapter(
    raw: ILLMProvider, store: SQLiteStateStore, *, bus: Bus | None = None
) -> LogicalCallLLMAdapter:
    return LogicalCallLLMAdapter(
        WorkflowTokenBudgetLLMAdapter(
            raw,
            authority_store=store.authority,
            provider="test-provider",
            model="test-model",
            bus=bus,
        )
    )


def test_success_reserves_before_call_and_settles_reported_usage(tmp_path: Path) -> None:
    store, key = _store(tmp_path)
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("LLMBudgetAttemptReserved", events.append)
    bus.subscribe("LLMBudgetAttemptSettled", events.append)
    raw = SequenceProvider([LLMResponse("ok", 11, 7)])

    with issue_scope(549, "run-549", key):
        response = _adapter(raw, store, bus=bus).complete(
            [{"role": "user", "content": "hello"}],
            task="planning",
            max_tokens=100,
        )

    assert response.text == "ok"
    attempt = store.authority.list_budget_attempts(admission_key=key)[0]
    assert attempt.status == "settled"
    assert (attempt.actual_input_tokens, attempt.actual_output_tokens) == (11, 7)
    assert [event.name for event in events] == [
        "LLMBudgetAttemptReserved",
        "LLMBudgetAttemptSettled",
    ]
    assert {event.correlation_id for event in events} == {"run-549"}
    assert all(event.payload["authority_series"] == "authority.v2" for event in events)


def test_unreported_usage_keeps_complete_reservation(tmp_path: Path) -> None:
    store, key = _store(tmp_path)
    raw = SequenceProvider([LLMResponse("ok", 0, 0, usage_reported=False)])

    with issue_scope(549, "run-549", key):
        _adapter(raw, store).complete([{"role": "user", "content": "hello"}], max_tokens=100)

    attempt = store.authority.list_budget_attempts(admission_key=key)[0]
    assert attempt.status == "unknown"
    assert attempt.outcome_code == "usage_unreported"
    assert attempt.actual_input_tokens is None


def test_retry_reserves_each_physical_attempt_and_holds_unknown_usage(tmp_path: Path) -> None:
    store, key = _store(tmp_path)
    raw = SequenceProvider([TimeoutError("late"), LLMResponse("ok", 5, 3)])
    leaf = WorkflowTokenBudgetLLMAdapter(
        raw,
        authority_store=store.authority,
        provider="test-provider",
        model="test-model",
    )
    adapter = LogicalCallLLMAdapter(
        RetryLLMAdapter(leaf, max_attempts=2, base_delay_s=0, sleep_fn=lambda _: None)
    )

    with issue_scope(549, "run-549", key):
        assert adapter.complete([{"role": "user", "content": "hello"}], max_tokens=100).text == "ok"

    attempts = store.authority.list_budget_attempts(admission_key=key)
    assert [attempt.status for attempt in attempts] == ["unknown", "settled"]
    assert len({attempt.logical_call_id for attempt in attempts}) == 1
    assert raw.calls == 2


@pytest.mark.parametrize(
    ("scope_key", "kwargs", "code"),
    [
        (None, {"max_tokens": 100}, "workflow_budget_admission_missing"),
        ("budget-test", {}, "workflow_budget_output_bound_missing"),
    ],
)
def test_missing_authority_or_output_bound_blocks_before_provider(
    tmp_path: Path,
    scope_key: str | None,
    kwargs: dict[str, Any],
    code: str,
) -> None:
    store, _ = _store(tmp_path)
    raw = SequenceProvider([LLMResponse("should-not-run", 1, 1)])
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("LLMBudgetBlocked", events.append)

    with issue_scope(549, "run-549", scope_key), pytest.raises(ProviderUnavailable) as blocked:
        _adapter(raw, store, bus=bus).complete([{"role": "user", "content": "hello"}], **kwargs)

    assert blocked.value.category == "workflow_budget"
    assert blocked.value.code == code
    assert raw.calls == 0
    assert events[0].payload["owasp_risk"] == "tool_misuse"


def test_exhausted_budget_blocks_second_call_before_provider(tmp_path: Path) -> None:
    store, key = _store(tmp_path, token_limit=250)
    raw = SequenceProvider(
        [
            LLMResponse("first", 1, 1, usage_reported=False),
            LLMResponse("should-not-run", 1, 1),
        ]
    )
    adapter = _adapter(raw, store)

    with issue_scope(549, "run-549", key):
        adapter.complete([{"role": "user", "content": "hello"}], max_tokens=100)
        with pytest.raises(ProviderUnavailable) as blocked:
            adapter.complete([{"role": "user", "content": "hello"}], max_tokens=100)

    assert blocked.value.code == "workflow_token_budget_exhausted"
    assert raw.calls == 1


def test_authority_read_failure_is_audited_and_blocks_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, key = _store(tmp_path)
    raw = SequenceProvider([LLMResponse("should-not-run", 1, 1)])
    bus = Bus()
    events: list[Any] = []
    bus.subscribe("LLMBudgetBlocked", events.append)

    def fail_read(admission_key: str) -> None:
        assert admission_key == key
        raise StateStoreError("state_authority_unavailable", "unavailable")

    monkeypatch.setattr(store.authority, "get_budget_admission", fail_read)
    with issue_scope(549, "run-549", key), pytest.raises(ProviderUnavailable) as blocked:
        _adapter(raw, store, bus=bus).complete(
            [{"role": "user", "content": "hello"}], max_tokens=100
        )

    assert blocked.value.code == "state_authority_unavailable"
    assert raw.calls == 0
    assert events[0].payload["reason"] == "state_authority_unavailable"
