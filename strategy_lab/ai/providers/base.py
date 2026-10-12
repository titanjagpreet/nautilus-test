"""The provider interface: ``complete_json(system, user, schema) -> (data, usage)``.

Each provider lists the structured-output modes it supports, best first (``config/llm.json``):

* ``json_schema``  — the API constrains the reply to the schema (Claude ``output_config.format``, Kimi
  ``response_format=json_schema`` with ``strict``);
* ``strict_tools`` — a single strict function whose arguments are the reply (DeepSeek beta endpoint);
* ``json_object`` / ``json_prompt`` — JSON mode (or plain instructions) with the schema and an example in the
  system prompt.

If the API rejects a mode with HTTP 400 (e.g. a schema feature it does not support) the next mode is tried and
the working mode is remembered. Every call is logged with its token usage and cost; a call is refused up front
when its worst-case cost could cross a spending limit.
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

from strategy_lab.ai.config import Mode, ProviderConfig, llm_config
from strategy_lab.ai.ledger import Ledger, Usage

Turn = tuple[Literal["user", "assistant"], str]
CHARS_PER_TOKEN_LOW = 2.5  # conservative (over-)estimate of tokens from characters for budget checks


class ProviderError(RuntimeError):
    """The call failed for a reason other than the content of the reply (network, auth, bad request)."""


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


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a Markdown code fence or text around it."""
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise json.JSONDecodeError("the reply is JSON but not an object", stripped, 0)
    return value


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

    def estimate_cost(self, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> float:
        """Worst case for one call: every prompt token uncached, the full output allowance used."""
        chars = len(system) + sum(len(text) for _, text in turns) + len(json.dumps(schema))
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
            self.ledger.record(usage, scope=self.scope, feature=feature, ok=raw.stop == "ok", note=raw.detail)
            if raw.stop == "refusal":
                reason = raw.detail or "no reason given"
                raise RefusalError(f"the provider declined the request ({reason})", raw.text, usage)
            if raw.stop == "truncated":
                raise TruncatedError("the reply was cut off at the output-token limit", raw.text, usage)
            try:
                return parse_json_object(raw.text), usage
            except json.JSONDecodeError as exc:
                raise InvalidJSONError(f"the reply is not a valid JSON object: {exc}", raw.text, usage) from exc
        raise ProviderError(f"{self.ref}: every structured-output mode was rejected: {'; '.join(rejected)}")
