from __future__ import annotations

from unittest.mock import MagicMock

from samuel.adapters.llm.sanitizer import MAX_RESPONSE_LENGTH, SanitizingLLMAdapter
from samuel.core.ports import ILLMProvider
from samuel.core.types import LLMResponse

MESSAGES = [{"role": "user", "content": "hi"}]


def _make_inner(text: str) -> MagicMock:
    inner = MagicMock(spec=ILLMProvider)
    inner.context_window = 200_000
    inner.capabilities = {"tool_use"}
    inner.estimate_tokens.return_value = 10
    inner.complete.return_value = LLMResponse(text=text, input_tokens=5, output_tokens=3)
    return inner


class TestSanitizingLLMAdapter:
    def test_local_curl_context_survives_provider_roundtrip(self):
        source = "curl --fail --silent http://127.0.0.1:8080/api/health"
        messages = [{"role": "user", "content": source + "\nRemote: 192.0.2.25"}]
        inner = _make_inner("")

        def edit(messages, **kwargs):
            return LLMResponse(
                text=messages[0]["content"]
                .splitlines()[0]
                .replace("--silent", "--silent --show-error"),
                input_tokens=5,
                output_tokens=3,
            )

        inner.complete.side_effect = edit
        adapter = SanitizingLLMAdapter(inner, pii_config={"enabled": True})
        response = adapter.complete(messages)
        assert response.text == source.replace("--silent", "--silent --show-error")
        sent = inner.complete.call_args.args[0][0]["content"]
        assert sent == source + "\nRemote: [REDACTED:ip_address]"
        assert messages[0]["content"] == source + "\nRemote: 192.0.2.25"

    def test_strips_html(self):
        san = SanitizingLLMAdapter(_make_inner("<b>Hello</b> world"))
        resp = san.complete(MESSAGES)
        assert resp.text == "Hello world"

    def test_truncates_excessive(self):
        long_text = "x" * (MAX_RESPONSE_LENGTH + 1000)
        san = SanitizingLLMAdapter(_make_inner(long_text))
        resp = san.complete(MESSAGES)
        assert len(resp.text) == MAX_RESPONSE_LENGTH

    def test_passthrough_clean_text(self):
        san = SanitizingLLMAdapter(_make_inner("clean text"))
        resp = san.complete(MESSAGES)
        assert resp.text == "clean text"

    def test_delegates_properties(self):
        san = SanitizingLLMAdapter(_make_inner("x"))
        assert san.context_window == 200_000
        assert san.capabilities == {"tool_use"}
        assert san.estimate_tokens("hi") == 10

    def test_uses_text_not_content(self):
        san = SanitizingLLMAdapter(_make_inner("<p>test</p>"))
        resp = san.complete(MESSAGES)
        assert hasattr(resp, "text")
        assert resp.text == "test"
