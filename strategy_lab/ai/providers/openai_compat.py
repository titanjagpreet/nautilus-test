"""DeepSeek and Kimi (Moonshot) through the official ``openai`` SDK with their OpenAI-compatible base URLs.

Provider facts (checked 2026-10-12, docs/notes/llm_provider_facts.md):

* DeepSeek has no ``json_schema`` response format; strict function calling is a beta on ``/beta`` (every
  property required, ``additionalProperties: false``, ``$ref`` via ``$def``). JSON mode needs the word "json"
  and an example in the prompt and may return empty content. Prompt caching is automatic; usage reports
  ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens``. Thinking is on by default and is turned off.
* Kimi supports ``response_format={"type": "json_schema", ..., "strict": true}`` and JSON mode; cached tokens
  are in ``usage.prompt_tokens_details.cached_tokens``; ``max_completion_tokens``; no ``temperature``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import httpx2
import openai
from openai.types.chat import ChatCompletion

from strategy_lab.ai.config import Mode
from strategy_lab.ai.ledger import Ledger
from strategy_lab.ai.providers.base import (
    LLMProvider,
    ModeRejectedError,
    ProviderError,
    RawReply,
    Turn,
    schema_instructions,
)

TOOL_NAME = "submit_reply"


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        provider: str,
        model: str,
        key: str,
        ledger: Ledger | None = None,
        scope: str = "app",
        http_client: httpx2.Client | None = None,
    ) -> None:
        super().__init__(provider, model, key, ledger, scope)
        self._http_client = http_client
        self._clients: dict[str, openai.OpenAI] = {}

    def _client(self, mode: Mode) -> openai.OpenAI:
        base_url = self.config.beta_base_url if mode == "strict_tools" else self.config.base_url
        assert base_url is not None
        if base_url not in self._clients:
            self._clients[base_url] = openai.OpenAI(
                api_key=self.key, base_url=base_url, timeout=180.0, max_retries=2, http_client=self._http_client
            )
        return self._clients[base_url]

    def _request(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> dict[str, Any]:
        if mode in ("json_object", "json_prompt"):
            system += schema_instructions(schema)
        messages = [{"role": "system", "content": system}, *({"role": r, "content": t} for r, t in turns)]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            self.config.max_tokens_param: self.max_output_tokens,
        }
        if mode == "json_schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "strategy_lab_reply", "strict": True, "schema": schema},
            }
        elif mode == "strict_tools":
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": TOOL_NAME,
                        "description": "Submit the reply object.",
                        "strict": True,
                        "parameters": schema,
                    },
                }
            ]
            kwargs["tool_choice"] = {"type": "function", "function": {"name": TOOL_NAME}}
        elif mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        if extras := self.config.body_extras(self.model):
            kwargs["extra_body"] = extras
        return kwargs

    def _call(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> RawReply:
        try:
            response = self._client(mode).chat.completions.create(**self._request(mode, system, turns, schema))
        except openai.BadRequestError as exc:
            if mode in ("json_schema", "strict_tools"):
                raise ModeRejectedError(_message(exc)) from exc
            raise ProviderError(f"{self.ref}: request rejected: {_message(exc)}") from exc
        except openai.APIStatusError as exc:
            raise ProviderError(f"{self.ref}: HTTP {exc.status_code}: {_message(exc)}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(f"{self.ref}: cannot reach the API ({exc.__class__.__name__})") from exc
        return _raw_reply(response, mode)


def _message(exc: openai.APIStatusError) -> str:
    body = exc.body
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return str(error["message"])[:500]
    return str(exc)[:500]


def _raw_reply(response: ChatCompletion, mode: Mode) -> RawReply:
    choice = response.choices[0]
    message = choice.message
    if mode == "strict_tools" and message.tool_calls:
        call = message.tool_calls[0]
        text = call.function.arguments if call.type == "function" else ""
    else:
        text = message.content or ""
    usage = response.usage
    prompt = usage.prompt_tokens if usage else 0
    extra = (usage.model_extra or {}) if usage else {}
    cached = extra.get("prompt_cache_hit_tokens")  # DeepSeek
    if cached is None and usage is not None and usage.prompt_tokens_details is not None:
        cached = usage.prompt_tokens_details.cached_tokens  # Kimi / OpenAI convention
    cached = int(cached or 0)
    stop: Literal["ok", "truncated", "refusal"] = "ok"
    if choice.finish_reason == "length":
        stop = "truncated"
    elif choice.finish_reason == "content_filter":
        stop = "refusal"
    return RawReply(
        text=text,
        input_tokens=prompt - cached,
        cached_tokens=cached,
        cache_write_tokens=0,
        output_tokens=usage.completion_tokens if usage else 0,
        stop=stop,
        detail="" if stop == "ok" else str(choice.finish_reason),
    )
