"""Strategy spec v0.1 — the versioned JSON format every part of the lab speaks.

A spec is *data*: it is parsed with Pydantic, checked by ``spec.validator`` and executed by one generic
strategy per engine. Nothing in a spec is ever evaluated as code.

Shape (see ``strategy_lab/spec/catalogue/*.json`` for complete examples)::

    {
      "spec_version": "0.1",
      "meta":   {"name", "description", "author": "ai|user|template", "tags": [...]},
      "market": {"symbol": "BTC-PERP|XAU-PERP", "timeframe": "5m|15m|1h|4h|1d", "direction": "long|short|both"},
      "indicators": [{"id", "type", "params", "source", "timeframe"}],
      "rules": {"entry_long", "exit_long", "entry_short", "exit_short"},   # condition trees or null
      "risk":  {"position_sizing", "leverage", "stop_loss", "take_profit", "trailing_stop",
                "time_exit_bars", "cooldown_bars", "max_trades_per_day"},
      "costs": {"fee_profile", "slippage_ticks", "funding"},
      "execution": {"fill_on": "next_bar_open", "htf_bars": "completed"}
    }

Conditions: ``{"op": "all"|"any", "args": [...]}``, ``{"op": "not", "arg": ...}``,
``{"op": ">"|"<"|">="|"<=", "left": operand, "right": operand}``,
``{"op": "crosses_above"|"crosses_below", "left", "right"}``, ``{"op": "between", "value", "low", "high"}``.
Operands: ``{"indicator": id, "output": name?, "bars_ago": n?}``, ``{"input": field, "bars_ago": n?}`` or
``{"value": number}``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SPEC_VERSION: Literal["0.1"] = "0.1"

Symbol = Literal["BTC-PERP", "XAU-PERP"]
Timeframe = Literal["5m", "15m", "1h", "4h", "1d"]
Direction = Literal["long", "short", "both"]
SourceField = Literal["open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"]
InputField = Literal[
    "open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4",
    "funding_rate",  # latest settled funding rate at the bar close, as an 8-hour-equivalent fraction
    "hour_utc",  # hour (0-23, UTC) of the bar's open time — for session logic
]  # fmt: skip
IndicatorType = Literal[
    "sma", "ema", "wma", "hma", "rsi", "macd", "bbands", "atr", "stoch", "adx",
    "donchian", "keltner", "vwap", "roc", "cci", "obv", "highest", "lowest",
]  # fmt: skip


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Meta(_Strict):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    author: Literal["ai", "user", "template"] = "user"
    tags: list[str] = Field(default_factory=list, max_length=12)


class Market(_Strict):
    symbol: Symbol
    timeframe: Timeframe
    direction: Direction = "both"


class Indicator(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$", description="unique name used by rules")
    type: IndicatorType
    params: dict[str, float] = Field(default_factory=dict)
    source: SourceField | None = Field(default=None, description="price field; default depends on type")
    timeframe: Timeframe | None = Field(default=None, description="higher timeframe filter; null = base")


# --- operands --------------------------------------------------------------------------------------------


class IndicatorOperand(_Strict):
    indicator: str
    output: str | None = Field(default=None, description="e.g. 'upper' for bbands; null = the main output")
    bars_ago: int = Field(default=0, description="0 = the bar just closed")


class InputOperand(_Strict):
    input: InputField
    bars_ago: int = 0


class ConstOperand(_Strict):
    value: float


Operand = IndicatorOperand | InputOperand | ConstOperand


# --- conditions ------------------------------------------------------------------------------------------


class Compare(_Strict):
    op: Literal[">", "<", ">=", "<="]
    left: Operand
    right: Operand


class Cross(_Strict):
    op: Literal["crosses_above", "crosses_below"]
    left: Operand
    right: Operand


class Between(_Strict):
    op: Literal["between"]
    value: Operand
    low: Operand
    high: Operand


class AllOf(_Strict):
    op: Literal["all"]
    args: list[Condition] = Field(min_length=1)


class AnyOf(_Strict):
    op: Literal["any"]
    args: list[Condition] = Field(min_length=1)


class Not(_Strict):
    op: Literal["not"]
    arg: Condition


Condition = Annotated[Compare | Cross | Between | AllOf | AnyOf | Not, Field(discriminator="op")]


class Rules(_Strict):
    entry_long: Condition | None = None
    exit_long: Condition | None = None
    entry_short: Condition | None = None
    exit_short: Condition | None = None


# --- risk ------------------------------------------------------------------------------------------------


class PercentEquity(_Strict):
    type: Literal["percent_equity"]
    value: float = Field(description="notional as % of account equity, e.g. 20")


class FixedUsd(_Strict):
    type: Literal["fixed_usd"]
    value: float = Field(description="notional in USD(C)")


Sizing = Annotated[PercentEquity | FixedUsd, Field(discriminator="type")]


class PercentStop(_Strict):
    type: Literal["percent"]
    value: float = Field(description="distance from entry in %, e.g. 1.5")


class AtrStop(_Strict):
    type: Literal["atr"]
    multiple: float
    atr_period: int = 14


class StructureStop(_Strict):
    type: Literal["structure"]
    lookback: int = Field(description="long: lowest low of the last N bars; short: highest high")
    buffer_pct: float = 0.0


StopLoss = Annotated[PercentStop | AtrStop | StructureStop, Field(discriminator="type")]


class PercentTarget(_Strict):
    type: Literal["percent"]
    value: float


class AtrTarget(_Strict):
    type: Literal["atr"]
    multiple: float
    atr_period: int = 14


class RiskRewardTarget(_Strict):
    type: Literal["risk_reward"]
    multiple: float = Field(description="target distance = multiple × stop distance")


TakeProfit = Annotated[PercentTarget | AtrTarget | RiskRewardTarget, Field(discriminator="type")]


class PercentTrail(_Strict):
    type: Literal["percent"]
    value: float


class AtrTrail(_Strict):
    type: Literal["atr"]
    multiple: float
    atr_period: int = 14


TrailingStop = Annotated[PercentTrail | AtrTrail, Field(discriminator="type")]


class Risk(_Strict):
    position_sizing: Sizing
    leverage: float = 3.0
    stop_loss: StopLoss | None = Field(description="required; null is rejected by the validator")
    take_profit: TakeProfit | None = None
    trailing_stop: TrailingStop | None = Field(default=None, description="updated at bar close only")
    time_exit_bars: int | None = None
    cooldown_bars: int = 0
    max_trades_per_day: int | None = None


class Costs(_Strict):
    fee_profile: str = "lighter_standard"
    slippage_ticks: int = 1
    funding: bool = True


class Execution(_Strict):
    """When decisions are made and filled. Only the defaults are valid; the other values exist so that specs
    translated from other tools (e.g. Pine's ``process_orders_on_close=true`` or ``request.security(...,
    lookahead=barmerge.lookahead_on)``) parse and are then rejected by the validator's look-ahead guards."""

    fill_on: Literal["next_bar_open", "same_bar_close"] = "next_bar_open"
    htf_bars: Literal["completed", "forming"] = "completed"


class StrategySpec(_Strict):
    spec_version: Literal["0.1"] = SPEC_VERSION
    meta: Meta
    market: Market
    indicators: list[Indicator] = Field(default_factory=list, max_length=20)
    rules: Rules
    risk: Risk
    costs: Costs = Field(default_factory=Costs)
    execution: Execution = Field(default_factory=Execution)


def json_schema() -> dict[str, object]:
    """JSON Schema of the spec (Draft 2020-12, as generated by Pydantic)."""
    schema: dict[str, object] = StrategySpec.model_json_schema()
    return schema
