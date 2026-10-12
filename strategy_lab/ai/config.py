"""LLM provider settings (``config/llm.json``): models, prices, budgets, structured-output modes, API keys.

Keys come from the environment or a git-ignored ``.env`` file in the project root and are never printed or
logged. A provider whose key is missing is simply not available.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from functools import cache
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field

from strategy_lab.config import PROJECT_ROOT

Mode = Literal["json_schema", "strict_tools", "json_object", "json_prompt"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rates(_Frozen):
    """USD per million tokens."""

    input: float
    cached_input: float
    output: float
    cache_write: float | None = None  # Anthropic: writing a prompt-cache entry (5-minute TTL)


class ModelPrice(Rates):
    off_peak: Rates | None = None  # DeepSeek: discounted outside peak hours
    long_context_tokens: int | None = None  # Anthropic Haiku 5.5: second rate card above this prompt size
    long_context: Rates | None = None


class ProviderConfig(_Frozen):
    sdk: Literal["openai", "anthropic"]
    key_env: str
    base_url: str | None = None
    beta_base_url: str | None = None
    modes: tuple[Mode, ...]
    defs_key: Literal["$defs", "$def"] = "$defs"
    writer: str
    escalation: str | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)
    model_extra_body: dict[str, dict[str, Any]] = Field(default_factory=dict)
    effort: Literal["low", "medium", "high"] | None = None
    max_output_tokens: int
    max_tokens_param: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    data_location: str
    peak_hours_utc: tuple[tuple[int, int], ...] = ()
    peak_weekdays: tuple[int, ...] = ()
    models: dict[str, ModelPrice]

    def body_extras(self, model: str) -> dict[str, Any]:
        return {**self.extra_body, **self.model_extra_body.get(model, {})}

    def is_peak(self, when: dt.datetime) -> bool:
        if not self.peak_hours_utc:
            return False
        utc = when.astimezone(dt.UTC)
        return utc.weekday() in self.peak_weekdays and any(lo <= utc.hour < hi for lo, hi in self.peak_hours_utc)

    def next_off_peak(self, when: dt.datetime) -> dt.datetime:
        """The first full hour at or after ``when`` that is off-peak."""
        t = when.astimezone(dt.UTC)
        if not self.is_peak(t):
            return t
        t = t.replace(minute=0, second=0, microsecond=0)
        while self.is_peak(t):
            t += dt.timedelta(hours=1)
        return t

    def rates(self, model: str, when: dt.datetime, prompt_tokens: int) -> Rates:
        price = self.models[model]
        long_context = price.long_context_tokens is not None and prompt_tokens > price.long_context_tokens
        if long_context and price.long_context is not None:
            return price.long_context
        if price.off_peak is not None and not self.is_peak(when):
            return price.off_peak
        return price


class Budget(_Frozen):
    total: float
    eval: float


class LLMConfig(_Frozen):
    prices_checked: dt.date
    price_sources: dict[str, str]
    budget_usd: Budget
    default_writer: str
    judge_preference: tuple[str, ...]
    providers: dict[str, ProviderConfig]


CONFIG_PATH = PROJECT_ROOT / "config" / "llm.json"


@cache
def llm_config() -> LLMConfig:
    return LLMConfig.model_validate(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))


def api_key(provider: str) -> str | None:
    """The provider's API key from the environment, else from ``.env``; None when unset or empty."""
    name = llm_config().providers[provider].key_env
    value = os.environ.get(name) or dotenv_values(PROJECT_ROOT / ".env").get(name)
    return value or None


def providers_with_keys() -> list[str]:
    return [name for name in llm_config().providers if api_key(name)]


def split_ref(ref: str) -> tuple[str, str]:
    """``"provider:model"`` → (provider, model)."""
    provider, _, model = ref.partition(":")
    return provider, model
