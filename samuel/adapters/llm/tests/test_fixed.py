"""#368 Task 8: deterministischer FixedResponseAdapter."""

from __future__ import annotations

from samuel.adapters.llm.fixed import FixedResponseAdapter
from samuel.core.types import LLMResponse


def test_single_string_response_repeats():
    a = FixedResponseAdapter("hello")
    assert a.complete([{"role": "user", "content": "x"}]).text == "hello"
    assert a.complete([{"role": "user", "content": "y"}]).text == "hello"


def test_sequence_in_order():
    a = FixedResponseAdapter(["one", "two"])
    assert a.complete([{"content": "a"}]).text == "one"
    assert a.complete([{"content": "b"}]).text == "two"
    assert a.complete([{"content": "c"}]).text == "two"  # letzte wiederholt


def test_deterministic_same_input_same_output():
    a1 = FixedResponseAdapter(["r1"])
    a2 = FixedResponseAdapter(["r1"])
    msg = [{"role": "user", "content": "identisch"}]
    assert a1.complete(msg).text == a2.complete(msg).text


def test_passthrough_llmresponse():
    resp = LLMResponse(text="t", input_tokens=1, output_tokens=2, structured={"k": 1})
    a = FixedResponseAdapter([resp])
    out = a.complete([{"content": "x"}])
    assert out.structured == {"k": 1}


def test_records_calls():
    a = FixedResponseAdapter(["r"])
    a.complete([{"content": "first"}])
    assert a.calls[0][0]["content"] == "first"


def test_context_window():
    assert FixedResponseAdapter("x", context_window=42).context_window == 42
