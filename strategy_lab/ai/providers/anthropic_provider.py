"""Claude (optional) through the official ``anthropic`` SDK.

* Structured outputs: ``output_config={"format": {"type": "json_schema", "schema": ...}}``. Supported schema
  subset: ``$ref``/``$defs``, ``anyOf``, ``enum``; every object ``additionalProperties: false``; no recursion,
  no numeric or length bounds — the transport schema (``ai/transport.py``) is built to fit.
* Prompt caching: an explicit ``cache_control`` breakpoint on the static system prompt (minimum cacheable prefix
  512 tokens on Claude Haiku 5.5; default 5-minute TTL refreshed by each hit). Usage reports
  ``input_tokens`` (uncached), ``cache_read_input_tokens`` and ``cache_creation_input_tokens``.
* Cost control: ``output_config.effort`` (Haiku 5.5 defaults to ``medium``; we use ``low``). Thinking is left
  adaptive, as recommended for Haiku 5.5 — at low effort it is often skipped; its tokens bill as output.
* No ``temperature`` (non-default sampling values return 400 on Haiku 5.5) and no assistant prefill.
* ``stop_reason == "refusal"`` (safety classifiers) and ``"max_tokens"`` are surfaced, never parsed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

import anthropic
import httpx2

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


class AnthropicProvider(LLMProvider):
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
        self.client = anthropic.Anthropic(api_key=key, timeout=180.0, max_retries=2, http_client=http_client)

    def _request(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> dict[str, Any]:
        if mode == "json_prompt":
            system += schema_instructions(schema)
        output_config: dict[str, Any] = {}
        if self.config.effort:
            output_config["effort"] = self.config.effort
        if mode == "json_schema":
            output_config["format"] = {"type": "json_schema", "schema": schema}
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": role, "content": text} for role, text in turns],
        }
        if output_config:
            kwargs["output_config"] = output_config
        return kwargs

    def _call(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> RawReply:
        try:
            message = self.client.messages.create(**self._request(mode, system, turns, schema))
        except anthropic.BadRequestError as exc:
            if mode == "json_schema":
                raise ModeRejectedError(exc.message[:500]) from exc
            raise ProviderError(f"{self.ref}: request rejected: {exc.message[:500]}") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"{self.ref}: HTTP {exc.status_code}: {exc.message[:500]}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"{self.ref}: cannot reach the API ({exc.__class__.__name__})") from exc
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = message.usage
        stop: Literal["ok", "truncated", "refusal"] = "ok"
        detail = ""
        if message.stop_reason == "refusal":
            stop = "refusal"
            category = message.stop_details.category if message.stop_details else None
            detail = f"refusal category: {category or 'unspecified'}"
        elif message.stop_reason == "max_tokens":
            stop, detail = "truncated", "max_tokens"
        return RawReply(
            text=text,
            input_tokens=usage.input_tokens,
            cached_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            output_tokens=usage.output_tokens,
            stop=stop,
            detail=detail,
        )
