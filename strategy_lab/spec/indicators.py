"""Indicator catalogue: parameters (with bounds), outputs, sources and how each maps to NautilusTrader.

This table is the single source of truth for the validator, the plain-language renderer, both engines and
the AI prompt. Formulas follow NautilusTrader 1.231 where it has the indicator (LEARNINGS.md §8 lists where
that differs from textbook definitions and which options we pick); "own" indicators are implemented in
``strategy_lab/spec/streaming.py`` (Nautilus side) and ``strategy_lab/engines/fast/indicators.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParamSpec:
    name: str
    default: float
    low: float
    high: float
    integer: bool = True
    description: str = ""


@dataclass(frozen=True)
class IndicatorDef:
    type: str
    label: str
    params: tuple[ParamSpec, ...]
    outputs: tuple[str, ...]  # first entry = main output (used when an operand gives no "output")
    default_source: str | None  # None: computed from high/low/close (+volume) — "source" must not be set
    nautilus: str  # NautilusTrader class used by the generic strategy, or "own"
    uses_volume: bool = False
    value_range: tuple[float, float] | None = None  # bounded oscillators, for contradiction checks
    description: str = ""

    @property
    def main_output(self) -> str:
        return self.outputs[0]

    def param_spec(self, name: str) -> ParamSpec | None:
        return next((p for p in self.params if p.name == name), None)


def _period(default: float, low: float, high: float) -> tuple[ParamSpec, ...]:
    return (ParamSpec("period", default, low, high, description="lookback in bars"),)


CATALOGUE: dict[str, IndicatorDef] = {
    d.type: d
    for d in [
        IndicatorDef("sma", "simple moving average", _period(20, 2, 500), ("value",), "close",
                     "SimpleMovingAverage"),
        IndicatorDef("ema", "exponential moving average", _period(20, 2, 500), ("value",), "close",
                     "ExponentialMovingAverage", description="alpha = 2/(period+1), seeded with the first value"),
        IndicatorDef("wma", "linearly weighted moving average", _period(20, 2, 500), ("value",), "close",
                     "WeightedMovingAverage(weights=1..n)"),
        IndicatorDef("hma", "Hull moving average", _period(21, 4, 500), ("value",), "close", "HullMovingAverage"),
        IndicatorDef("rsi", "relative strength index (Wilder)", _period(14, 2, 100), ("value",), "close",
                     "RelativeStrengthIndex(WILDER) x 100", value_range=(0.0, 100.0)),
        IndicatorDef(
            "macd", "MACD",
            (ParamSpec("fast", 12, 2, 100), ParamSpec("slow", 26, 3, 300), ParamSpec("signal", 9, 2, 100)),
            ("line", "signal", "hist"), "close", "MovingAverageConvergenceDivergence + EMA signal",
        ),
        IndicatorDef(
            "bbands", "Bollinger Bands",
            (ParamSpec("period", 20, 5, 200), ParamSpec("std", 2.0, 0.5, 5.0, integer=False)),
            ("middle", "upper", "lower", "width"), "close", "BollingerBands (fed with the source value)",
            description="SMA ± std × population standard deviation; width = (upper - lower) / middle",
        ),
        IndicatorDef("atr", "average true range (Wilder)", _period(14, 2, 200), ("value",), None,
                     "AverageTrueRange(WILDER)"),
        IndicatorDef(
            "stoch", "stochastic oscillator",
            (ParamSpec("k_period", 14, 3, 100), ParamSpec("d_period", 3, 1, 20), ParamSpec("smooth", 3, 1, 20)),
            ("k", "d"), None, "Stochastics(d_method=moving_average, SIMPLE)", value_range=(0.0, 100.0),
        ),
        IndicatorDef("adx", "average directional index (Wilder)", _period(14, 3, 100),
                     ("adx", "plus_di", "minus_di"), None, "own", value_range=(0.0, 100.0)),
        IndicatorDef("donchian", "Donchian channel", _period(20, 2, 500), ("middle", "upper", "lower"), None,
                     "DonchianChannel", description="highest high / lowest low including the current bar"),
        IndicatorDef(
            "keltner", "Keltner channel",
            (ParamSpec("period", 20, 5, 200), ParamSpec("multiplier", 2.0, 0.5, 5.0, integer=False)),
            ("middle", "upper", "lower"), None, "KeltnerChannel(EMA, ATR WILDER)",
            description="EMA of typical price ± multiplier × ATR",
        ),
        IndicatorDef("vwap", "session VWAP (UTC day)", (), ("value",), None, "VolumeWeightedAveragePrice",
                     uses_volume=True, description="resets at 00:00 UTC; typical price weighted by volume"),
        IndicatorDef("roc", "rate of change (%)", _period(10, 1, 500), ("value",), "close",
                     "RateOfChange(period + 1) x 100"),
        IndicatorDef("cci", "commodity channel index", _period(20, 5, 200), ("value",), None,
                     "CommodityChannelIndex"),
        IndicatorDef("obv", "on-balance volume", (), ("value",), None, "own", uses_volume=True,
                     description="cumulative volume signed by close vs previous close"),
        IndicatorDef("highest", "highest value over N bars", _period(20, 2, 500), ("value",), "high", "own",
                     description="includes the current bar"),
        IndicatorDef("lowest", "lowest value over N bars", _period(20, 2, 500), ("value",), "low", "own",
                     description="includes the current bar"),
    ]
}  # fmt: skip


def resolved_params(indicator_type: str, params: dict[str, float]) -> dict[str, float]:
    """Defaults filled in; integer parameters coerced to int-valued floats."""
    definition = CATALOGUE[indicator_type]
    out = {}
    for p in definition.params:
        value = params.get(p.name, p.default)
        out[p.name] = float(int(value)) if p.integer else float(value)
    return out


def resolved_source(indicator_type: str, source: str | None) -> str | None:
    return source if source is not None else CATALOGUE[indicator_type].default_source


def warmup_bars(indicator_type: str, params: dict[str, float]) -> int:
    """Bars needed before the first valid value (used for messages and data-range padding)."""
    p = resolved_params(indicator_type, params)
    match indicator_type:
        case "macd":
            return int(p["slow"] + p["signal"] - 1)
        case "stoch":
            return int(p["k_period"] + p["smooth"] + p["d_period"])
        case "adx":
            return int(2 * p["period"] + 1)
        case "roc":
            return int(p["period"] + 1)
        case "vwap" | "obv":
            return 1
        case _:
            return int(p["period"])
