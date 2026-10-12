"""Turn a spec into arrays: indicator outputs per bar and boolean signal arrays per base bar.

Mirrors ``spec/evaluator.py`` exactly: a rule is true at a bar only if every operand it references is
available there (at ``bars_ago`` and, for crosses, ``bars_ago + 1``). Higher-timeframe operands read the latest
*completed* HTF bar at each base bar, and their ``bars_ago`` counts HTF bars.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from strategy_lab.data.schema import TIMEFRAMES
from strategy_lab.engines.fast import indicators as ind_fn
from strategy_lab.spec.indicators import CATALOGUE, resolved_params, resolved_source
from strategy_lab.spec.schema import (
    AllOf,
    AnyOf,
    Between,
    Compare,
    Condition,
    ConstOperand,
    Cross,
    Indicator,
    IndicatorOperand,
    InputOperand,
    Not,
    Operand,
    StrategySpec,
)

F64 = npt.NDArray[np.float64]
BoolArr = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class BarFrame:
    """One timeframe's bars as arrays (open-time stamped, tick-rounded prices)."""

    open_ns: npt.NDArray[np.int64]
    close_ns: npt.NDArray[np.int64]
    open: F64
    high: F64
    low: F64
    close: F64
    volume: F64

    @classmethod
    def from_frame(cls, frame: pd.DataFrame, timeframe: str) -> BarFrame:
        open_ns = frame["ts"].dt.as_unit("ns").astype("int64").to_numpy()
        return cls(
            open_ns,
            open_ns + int(TIMEFRAMES[timeframe].value),
            *(frame[c].to_numpy(dtype=np.float64) for c in ("open", "high", "low", "close", "volume")),
        )

    def __len__(self) -> int:
        return len(self.close)

    def field(self, name: str) -> F64:
        match name:
            case "hl2":
                return (self.high + self.low) / 2.0
            case "hlc3":
                return (self.high + self.low + self.close) / 3.0
            case "ohlc4":
                return (self.open + self.high + self.low + self.close) / 4.0
            case _:
                values: F64 = getattr(self, name)
                return values

    def day_of_month(self) -> npt.NDArray[np.int64]:
        return pd.to_datetime(self.open_ns, utc=True).day.to_numpy(dtype=np.int64)

    def hour_utc(self) -> F64:
        return pd.to_datetime(self.open_ns, utc=True).hour.to_numpy(dtype=np.float64)


def compute_indicator(ind: Indicator, bars: BarFrame) -> dict[str, F64]:
    p = resolved_params(ind.type, ind.params)
    x = bars.field(resolved_source(ind.type, ind.source) or "close")
    h, lo, c, v = bars.high, bars.low, bars.close, bars.volume
    n = int(p.get("period", 0))
    match ind.type:
        case "sma":
            return {"value": ind_fn.sma(x, n)}
        case "ema":
            return {"value": ind_fn.ema(x, n)}
        case "wma":
            return {"value": ind_fn.wma(x, n)}
        case "hma":
            return {"value": ind_fn.hma(x, n)}
        case "rsi":
            return {"value": ind_fn.rsi(x, n)}
        case "roc":
            return {"value": ind_fn.roc(x, n)}
        case "macd":
            line, sig, hist = ind_fn.macd(x, int(p["fast"]), int(p["slow"]), int(p["signal"]))
            return {"line": line, "signal": sig, "hist": hist}
        case "bbands":
            middle, upper, lower, width = ind_fn.bbands(x, n, p["std"])
            return {"middle": middle, "upper": upper, "lower": lower, "width": width}
        case "atr":
            return {"value": ind_fn.atr(h, lo, c, n)}
        case "cci":
            return {"value": ind_fn.cci(h, lo, c, n)}
        case "keltner":
            middle, upper, lower = ind_fn.keltner(h, lo, c, n, p["multiplier"])
            return {"middle": middle, "upper": upper, "lower": lower}
        case "stoch":
            k, d = ind_fn.stoch(h, lo, c, int(p["k_period"]), int(p["d_period"]), int(p["smooth"]))
            return {"k": k, "d": d}
        case "adx":
            a, plus_di, minus_di = ind_fn.adx(h, lo, c, n)
            return {"adx": a, "plus_di": plus_di, "minus_di": minus_di}
        case "donchian":
            middle, upper, lower = ind_fn.donchian(h, lo, n)
            return {"middle": middle, "upper": upper, "lower": lower}
        case "vwap":
            return {"value": ind_fn.vwap(h, lo, c, v, bars.day_of_month())}
        case "obv":
            return {"value": ind_fn.obv(c, v)}
        case "highest":
            return {"value": ind_fn.highest(x, n)}
        case "lowest":
            return {"value": ind_fn.lowest(x, n)}
    raise ValueError(f"no fast implementation for {ind.type!r}")


# --- operands on the base timeline ------------------------------------------------------------------------


@dataclass
class OperandSource:
    """Values of one series and the base-bar → series index mapping (identity for base series)."""

    values: F64
    index_at_base: npt.NDArray[np.int64]


class Compiled:
    """Indicator outputs and inputs for one spec, addressable as operands at each base bar."""

    def __init__(
        self,
        spec: StrategySpec,
        base: BarFrame,
        htf: dict[str, BarFrame],
        funding_ns: npt.NDArray[np.int64],
        funding_rate_8h: F64,
    ) -> None:
        self.spec = spec
        self.n = len(base)
        identity = np.arange(self.n, dtype=np.int64)
        self.series: dict[tuple[str, str], OperandSource] = {}
        for ind in spec.indicators:
            tf = ind.timeframe or spec.market.timeframe
            if tf == spec.market.timeframe:
                frame, index = base, identity
            else:
                frame = htf[tf]
                # latest HTF bar whose close is at or before the base bar's close
                index = np.searchsorted(frame.close_ns, base.close_ns, side="right").astype(np.int64) - 1
            for output, values in compute_indicator(ind, frame).items():
                self.series[(ind.id, output)] = OperandSource(values, index)
        for field in ("open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"):
            self.series[("$input", field)] = OperandSource(base.field(field), identity)
        self.series[("$input", "hour_utc")] = OperandSource(base.hour_utc(), identity)
        last_funding = np.searchsorted(funding_ns, base.close_ns, side="right").astype(np.int64) - 1
        rates = np.r_[funding_rate_8h, np.nan]  # index -1 → NaN (no funding settled yet)
        self.series[("$input", "funding_rate")] = OperandSource(rates[np.where(last_funding >= 0, last_funding, -1)],
                                                                identity)  # fmt: skip
        self.type_of = {i.id: i.type for i in spec.indicators}

    def value(self, operand: Operand, extra: int = 0) -> F64:
        """Operand value at every base bar (NaN where unavailable)."""
        if isinstance(operand, ConstOperand):
            return np.full(self.n, operand.value)
        if isinstance(operand, InputOperand):
            key = ("$input", operand.input)
        else:
            assert isinstance(operand, IndicatorOperand)
            key = (operand.indicator, operand.output or CATALOGUE[self.type_of[operand.indicator]].main_output)
        src = self.series[key]
        idx = src.index_at_base - (operand.bars_ago + extra)
        out = np.full(self.n, np.nan)
        ok = idx >= 0
        out[ok] = src.values[idx[ok]]
        return out

    def evaluate(self, cond: Condition | None) -> BoolArr:
        if cond is None:
            return np.zeros(self.n, dtype=np.bool_)
        available = np.ones(self.n, dtype=np.bool_)
        for operand, extra in _operands(cond):
            for e in range(extra + 1):
                available &= ~np.isnan(self.value(operand, e))
        result: BoolArr = self._eval(cond) & available
        return result

    def _eval(self, cond: Condition) -> BoolArr:
        with np.errstate(invalid="ignore"):
            if isinstance(cond, Compare):
                a, b = self.value(cond.left), self.value(cond.right)
                ops = {">": np.greater, "<": np.less, ">=": np.greater_equal, "<=": np.less_equal}
                out: BoolArr = ops[cond.op](a, b)
                return out
            if isinstance(cond, Cross):
                a0, b0 = self.value(cond.left), self.value(cond.right)
                a1, b1 = self.value(cond.left, 1), self.value(cond.right, 1)
                if cond.op == "crosses_above":
                    return (a0 > b0) & (a1 <= b1)
                return (a0 < b0) & (a1 >= b1)
            if isinstance(cond, Between):
                v, lo, hi = self.value(cond.value), self.value(cond.low), self.value(cond.high)
                return (lo <= v) & (v <= hi)
        if isinstance(cond, AllOf):
            out = np.ones(self.n, dtype=np.bool_)
            for arg in cond.args:
                out &= self._eval(arg)
            return out
        if isinstance(cond, AnyOf):
            out = np.zeros(self.n, dtype=np.bool_)
            for arg in cond.args:
                out |= self._eval(arg)
            return out
        assert isinstance(cond, Not)
        return ~self._eval(cond.arg)


def _operands(cond: Condition) -> list[tuple[Operand, int]]:
    if isinstance(cond, Compare):
        return [(cond.left, 0), (cond.right, 0)]
    if isinstance(cond, Cross):
        return [(cond.left, 1), (cond.right, 1)]
    if isinstance(cond, Between):
        return [(cond.value, 0), (cond.low, 0), (cond.high, 0)]
    if isinstance(cond, AllOf | AnyOf):
        return [o for arg in cond.args for o in _operands(arg)]
    assert isinstance(cond, Not)
    return _operands(cond.arg)
