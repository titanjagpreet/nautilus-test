"""Provider factory: one ``LLMProvider`` per (provider, model); providers without an API key are skipped."""

from __future__ import annotations

from strategy_lab.ai.config import api_key, llm_config, split_ref
from strategy_lab.ai.ledger import Ledger
from strategy_lab.ai.providers.base import LLMProvider


class MissingKeyError(LookupError):
    pass


def make_provider(ref: str, ledger: Ledger | None = None, scope: str = "app") -> LLMProvider:
    """``ref`` is ``"provider"`` (its writer model) or ``"provider:model"``."""
    name, model = split_ref(ref)
    config = llm_config().providers[name]
    model = model or config.writer
    if model not in config.models:
        raise ValueError(f"no price configured for {name}:{model}; add it to config/llm.json")
    key = api_key(name)
    if key is None:
        raise MissingKeyError(f"{config.key_env} is not set; provider {name!r} is skipped")
    if config.sdk == "anthropic":
        from strategy_lab.ai.providers.anthropic_provider import AnthropicProvider  # noqa: PLC0415

        return AnthropicProvider(name, model, key, ledger, scope)
    from strategy_lab.ai.providers.openai_compat import OpenAICompatProvider  # noqa: PLC0415

    return OpenAICompatProvider(name, model, key, ledger, scope)
