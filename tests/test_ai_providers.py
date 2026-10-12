"""Providers through the real ``openai`` / ``anthropic`` SDKs against a mocked HTTP transport.

SYNTHETIC: every API response below is generated in code in the providers' documented wire format; no API is
called. The tests check the request each provider sends (structured-output mode, caching, thinking/effort,
token-limit parameter, no sampling parameters) and how usage is turned into cost.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest

from strategy_lab.ai.ledger import Ledger
from strategy_lab.ai.providers.anthropic_provider import AnthropicProvider
from strategy_lab.ai.providers.base import RefusalError, TruncatedError
from strategy_lab.ai.providers.openai_compat import TOOL_NAME, OpenAICompatProvider
from strategy_lab.ai.transport import reply_schema

SCHEMA = reply_schema()
REPLY = {
    "questions": ["Which market?"],
    "spec": None,
    "changes": [],
    "explanation": None,
    "unsupported": [],
    "assumptions": [],
    "refusal": None,
}
Handler = Callable[[httpx2.Request], httpx2.Response]


class Recorder:
    def __init__(self, *responses: httpx2.Response) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append((str(request.url), json.loads(request.content)))
        return self.responses.pop(0)

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self))


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite")


def anthropic_message(text: str, stop: str = "end_turn", **usage: int) -> httpx2.Response:
    body = {
        "id": "msg_synthetic",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 120,
            "output_tokens": 300,
            "cache_read_input_tokens": 5000,
            "cache_creation_input_tokens": 0,
        }
        | usage,
    }
    if stop == "refusal":
        body["stop_details"] = {"type": "refusal", "category": "cyber", "explanation": None}
    return httpx2.Response(200, json=body)


def chat_completion(
    content: str | None, tool_args: str | None = None, finish: str = "stop", **usage: Any
) -> httpx2.Response:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_args is not None:
        message["tool_calls"] = [
            {"id": "call_1", "type": "function", "function": {"name": TOOL_NAME, "arguments": tool_args}}
        ]
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-synthetic",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 5000, "completion_tokens": 400, "total_tokens": 5400} | usage,
        },
    )


def bad_request(message: str) -> httpx2.Response:
    return httpx2.Response(
        400, json={"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    )


def test_anthropic_request_shape_and_cost(ledger: Ledger) -> None:
    rec = Recorder(anthropic_message(json.dumps(REPLY)))
    provider = AnthropicProvider("anthropic", "claude-haiku-5-5", "test-key", ledger, http_client=rec.client())
    data, usage = provider.complete_json("SYSTEM PROMPT", "TASK: generate", SCHEMA, feature="generate")
    assert data == REPLY
    url, body = rec.requests[0]
    assert url.endswith("/v1/messages")
    assert body["model"] == "claude-haiku-5-5"
    assert body["system"] == [{"type": "text", "text": "SYSTEM PROMPT", "cache_control": {"type": "ephemeral"}}]
    assert body["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert body["messages"] == [{"role": "user", "content": "TASK: generate"}]
    assert not {"temperature", "top_p", "top_k", "thinking"} & body.keys()
    assert (usage.input_tokens, usage.cached_tokens, usage.output_tokens) == (120, 5000, 300)
    assert usage.cost_usd == pytest.approx((120 * 0.10 + 5000 * 0.01 + 300 * 0.50) / 1e6)


def test_anthropic_cache_write_is_billed_at_the_write_rate(ledger: Ledger) -> None:
    rec = Recorder(
        anthropic_message(json.dumps(REPLY), cache_read_input_tokens=0, cache_creation_input_tokens=5000)
    )
    provider = AnthropicProvider("anthropic", "claude-haiku-5-5", "k", ledger, http_client=rec.client())
    _, usage = provider.complete_json("S", "U", SCHEMA)
    assert usage.cost_usd == pytest.approx((120 * 0.10 + 5000 * 0.125 + 300 * 0.50) / 1e6)


def test_anthropic_falls_back_to_prompted_json_when_the_schema_is_rejected(ledger: Ledger) -> None:
    rec = Recorder(bad_request("schema too complex"), anthropic_message("```json\n" + json.dumps(REPLY) + "\n```"))
    provider = AnthropicProvider("anthropic", "claude-haiku-5-5", "k", ledger, http_client=rec.client())
    data, usage = provider.complete_json("S", "U", SCHEMA)
    assert data == REPLY
    assert usage.mode == "json_prompt"
    assert provider.mode == "json_prompt"
    second = rec.requests[1][1]
    assert "format" not in second["output_config"]
    assert second["system"][0]["text"].startswith("S\n\n# Reply format (json)")


def test_anthropic_refusal_and_truncation_are_not_parsed(ledger: Ledger) -> None:
    rec = Recorder(anthropic_message("", stop="refusal"), anthropic_message('{"questions": [', stop="max_tokens"))
    provider = AnthropicProvider("anthropic", "claude-haiku-5-5", "k", ledger, http_client=rec.client())
    with pytest.raises(RefusalError, match="cyber"):
        provider.complete_json("S", "U", SCHEMA)
    with pytest.raises(TruncatedError):
        provider.complete_json("S", "U", SCHEMA)
    assert len(ledger.calls()) == 2, "failed replies are still billed and logged"


def test_deepseek_strict_tools_then_json_mode(ledger: Ledger) -> None:
    rec = Recorder(
        chat_completion(
            None, tool_args=json.dumps(REPLY), prompt_cache_hit_tokens=4800, prompt_cache_miss_tokens=200
        ),
        bad_request("unsupported schema"),
        chat_completion(json.dumps(REPLY)),
    )
    provider = OpenAICompatProvider("deepseek", "deepseek-flash", "k", ledger, http_client=rec.client())
    schema = reply_schema("$def")
    data, usage = provider.complete_json("S", "U", schema)
    assert data == REPLY
    assert usage.mode == "strict_tools"
    url, body = rec.requests[0]
    assert url == "https://api.deepseek.com/beta/chat/completions"
    assert body["tools"][0]["function"]["strict"] is True
    assert body["tools"][0]["function"]["parameters"] == schema
    assert body["tool_choice"] == {"type": "function", "function": {"name": TOOL_NAME}}
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 8192
    assert "temperature" not in body
    assert (usage.input_tokens, usage.cached_tokens) == (200, 4800)
    peak = usage.peak
    rates = (0.30, 0.006, 1.20) if peak else (0.15, 0.003, 0.60)
    assert usage.cost_usd == pytest.approx((200 * rates[0] + 4800 * rates[1] + 400 * rates[2]) / 1e6)

    data, usage = provider.complete_json("S", "U", schema)  # strict tools rejected now → JSON mode
    assert usage.mode == "json_object"
    assert data == REPLY
    url, body = rec.requests[2]
    assert url == "https://api.deepseek.com/chat/completions"
    assert body["response_format"] == {"type": "json_object"}
    assert "json" in body["messages"][0]["content"]
    assert '"$def"' in body["messages"][0]["content"]


def test_kimi_json_schema_request_and_cached_tokens(ledger: Ledger) -> None:
    rec = Recorder(
        chat_completion("```json\n" + json.dumps(REPLY) + "\n```", prompt_tokens_details={"cached_tokens": 4096})
    )
    provider = OpenAICompatProvider("moonshot", "kimi-k2.6", "k", ledger, http_client=rec.client())
    data, usage = provider.complete_json("S", [("user", "U"), ("assistant", "A"), ("user", "fix")], SCHEMA)
    assert data == REPLY
    url, body = rec.requests[0]
    assert url == "https://api.moonshot.ai/v1/chat/completions"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["max_completion_tokens"] == 8192
    assert "max_tokens" not in body
    assert "temperature" not in body
    assert body["thinking"] == {"type": "disabled"}
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]
    assert usage.cached_tokens == 4096
    assert usage.input_tokens == 5000 - 4096
    assert usage.cost_usd == pytest.approx(((5000 - 4096) * 0.95 + 4096 * 0.16 + 400 * 4.00) / 1e6)


def test_kimi_k3_gets_no_thinking_switch(ledger: Ledger) -> None:
    rec = Recorder(chat_completion(json.dumps(REPLY)))
    provider = OpenAICompatProvider("moonshot", "kimi-k3", "k", ledger, http_client=rec.client())
    provider.complete_json("S", "U", SCHEMA)
    assert "thinking" not in rec.requests[0][1]


def test_length_finish_is_truncation(ledger: Ledger) -> None:
    rec = Recorder(chat_completion('{"questions": [', finish="length"))
    provider = OpenAICompatProvider("moonshot", "kimi-k2.6", "k", ledger, http_client=rec.client())
    with pytest.raises(TruncatedError):
        provider.complete_json("S", "U", SCHEMA)
