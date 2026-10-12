"""The provider interface: ``complete_json(system, user, schema) -> (data, usage)``.

Each provider lists the structured-output modes it supports, best first (``config/llm.json``):

* ``json_schema``  — the API constrains the reply to the schema (Claude ``output_config.format``, Kimi
  ``response_format=json_schema`` with ``strict``);
* ``strict_tools`` — a single strict function whose arguments are the reply (DeepSeek beta endpoint);
* ``json_object`` / ``json_prompt`` — JSON mode (or plain instructions) with the schema and an example in the
  system prompt.

If the API rejects a mode with HTTP 400 (e.g. a schema feature it does not support) the next mode is tried, the
working mode is remembered and the rejection is logged with the API's reason. Every call is logged with its
token usage and cost; a call is refused up front when its worst-case cost could cross a spending limit.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from strategy_lab.ai import transport
from strategy_lab.ai.config import Mode, ProviderConfig, llm_config
from strategy_lab.ai.ledger import MODE_REJECTED, Ledger, Usage

Turn = tuple[Literal["user", "assistant"], str]
CHARS_PER_TOKEN_LOW = 2.5  # conservative (over-)estimate of tokens from characters for budget checks


class ProviderError(RuntimeError):
    """The call failed for a reason other than the content of the reply (network, auth, bad request)."""


IGNORED_AFTER_JSON = "ignored after the JSON object: "  # ledger note when a reply had text or brackets after it


class ModeRejectedError(ProviderError):
    """HTTP 400 for a structured-output mode; the next mode may work."""


class ReplyError(RuntimeError):
    """The model answered, but the answer is unusable (not JSON, truncated, refused). Carries the usage."""

    def __init__(self, message: str, text: str, usage: Usage) -> None:
        super().__init__(message)
        self.text = text
        self.usage = usage


class InvalidJSONError(ReplyError):
    pass


class TruncatedError(ReplyError):
    pass


class RefusalError(ReplyError):
    """The provider's own safety system declined the request."""


@dataclass(frozen=True)
class RawReply:
    text: str
    input_tokens: int  # uncached prompt tokens
    cached_tokens: int
    cache_write_tokens: int
    output_tokens: int
    stop: Literal["ok", "truncated", "refusal"]
    detail: str = ""


def split_json_object(text: str) -> tuple[dict[str, Any], str]:
    """The reply's JSON object and whatever follows it.

    Tolerated: a Markdown code fence, text before the object and, after it, text or surplus closing brackets.
    DeepSeek V4.1-Flash sometimes closes one brace too many at the end of a long reply — a complete object and
    then a stray ``}``, recorded in JSON mode and in strict tools; reading "from the first ``{`` to the last
    ``}``" pulls that brace in and fails. A second JSON object is an error: which one is meant is ambiguous.
    """
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1)
    start = stripped.find("{")
    if start < 0:
        raise json.JSONDecodeError("no JSON object in the reply", stripped, 0)
    value: dict[str, Any]
    value, end = json.JSONDecoder().raw_decode(stripped, start)
    rest = stripped[end:].strip()
    if "{" in rest:
        raise json.JSONDecodeError("a second JSON object follows the first", stripped, stripped.index("{", end))
    return value, rest


def parse_json_object(text: str) -> dict[str, Any]:
    return split_json_object(text)[0]


def _invalid_json(exc: json.JSONDecodeError) -> str:
    """The parser's message with the text around the failing position, for the user and the repair prompt."""
    before, after = exc.doc[max(0, exc.pos - 60) : exc.pos], exc.doc[exc.pos : exc.pos + 40]
    return f"the reply is not a valid JSON object: {exc} — near: {before}<<HERE>>{after}"


def schema_instructions(schema: dict[str, Any]) -> str:
    """Appended to the system prompt in the JSON-mode fallbacks, where the API does not enforce the schema."""
    return (
        "\n\n# Reply format (json)\nReply with exactly one JSON object and nothing else - no Markdown, no code "
        "fence. It must validate against this JSON Schema:\n" + json.dumps(schema, separators=(",", ":"))
    )


class LLMProvider(ABC):
    """One model of one provider. Not thread-safe (remembers the working mode)."""

    def __init__(
        self, provider: str, model: str, key: str, ledger: Ledger | None = None, scope: str = "app"
    ) -> None:
        self.provider = provider
        self.model = model
        self.config: ProviderConfig = llm_config().providers[provider]
        self.key = key
        self.ledger = ledger or Ledger()
        self.scope = scope
        self.max_output_tokens = self.config.max_output_tokens
        self._modes: list[Mode] = list(self.config.modes)

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def mode(self) -> Mode:
        return self._modes[0]

    @abstractmethod
    def _call(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> RawReply: ...

    def wire_schema(self, mode: Mode, schema: dict[str, Any]) -> dict[str, Any]:
        return transport.wire_schema(schema, mode, self.config.defs_key)

    def estimate_cost(self, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> float:
        """Worst case for one call: every prompt token uncached, the full output allowance used."""
        sent = self.wire_schema(self.mode, schema)
        chars = len(system) + sum(len(text) for _, text in turns) + len(json.dumps(sent))
        prompt_tokens = int(chars / CHARS_PER_TOKEN_LOW)
        rates = self.config.rates(self.model, dt.datetime.now(dt.UTC), prompt_tokens)
        write = rates.cache_write if rates.cache_write is not None else rates.input
        return (prompt_tokens * max(rates.input, write) + self.max_output_tokens * rates.output) / 1e6

    def cost(self, raw: RawReply, when: dt.datetime) -> float:
        prompt = raw.input_tokens + raw.cached_tokens + raw.cache_write_tokens
        rates = self.config.rates(self.model, when, prompt)
        write = rates.cache_write if rates.cache_write is not None else rates.input
        return (
            raw.input_tokens * rates.input
            + raw.cached_tokens * rates.cached_input
            + raw.cache_write_tokens * write
            + raw.output_tokens * rates.output
        ) / 1e6

    def complete_json(
        self, system: str, user: str | Sequence[Turn], schema: dict[str, Any], feature: str = ""
    ) -> tuple[dict[str, Any], Usage]:
        turns: list[Turn] = [("user", user)] if isinstance(user, str) else list(user)
        self.ledger.ensure_budget(self.scope, self.estimate_cost(system, turns, schema))
        rejected: list[str] = []
        while self._modes:
            mode = self._modes[0]
            when = dt.datetime.now(dt.UTC)
            started = time.perf_counter()
            try:
                raw = self._call(mode, system, turns, schema)
            except ModeRejectedError as exc:
                rejected.append(f"{mode}: {exc}")
                self._modes.pop(0)
                unbilled = Usage(
                    provider=self.provider,
                    model=self.model,
                    mode=mode,
                    input_tokens=0,
                    cached_tokens=0,
                    cache_write_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_s=time.perf_counter() - started,
                    peak=self.config.is_peak(when),
                )
                self.ledger.record(
                    unbilled, scope=self.scope, feature=feature, ok=False, note=f"{MODE_REJECTED}{exc}"
                )
                continue
            usage = Usage(
                provider=self.provider,
                model=self.model,
                mode=mode,
                input_tokens=raw.input_tokens,
                cached_tokens=raw.cached_tokens,
                cache_write_tokens=raw.cache_write_tokens,
                output_tokens=raw.output_tokens,
                cost_usd=self.cost(raw, when),
                latency_s=time.perf_counter() - started,
                peak=self.config.is_peak(when),
            )
            data: dict[str, Any] | None = None
            note = raw.detail
            if raw.stop == "ok":
                try:
                    data, rest = split_json_object(raw.text)
                    note = f"{IGNORED_AFTER_JSON}{rest[:200]}" if rest else ""
                except json.JSONDecodeError as exc:
                    note = _invalid_json(exc)
            self.ledger.record(usage, scope=self.scope, feature=feature, ok=data is not None, note=note)
            if raw.stop == "refusal":
                reason = raw.detail or "no reason given"
                raise RefusalError(f"the provider declined the request ({reason})", raw.text, usage)
            if raw.stop == "truncated":
                raise TruncatedError("the reply was cut off at the output-token limit", raw.text, usage)
            if data is None:
                raise InvalidJSONError(note, raw.text, usage)
            return data, usage
        raise ProviderError(f"{self.ref}: every structured-output mode was rejected: {'; '.join(rejected)}")
