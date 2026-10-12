"""Fast-engine backtests of one spec on time windows of one market, for the lab.

Every window is evaluated with indicator warm-up on the data *before* the window (``trade_from`` in the fast
engine: earlier data is used for indicator values only, entries start at the window's start), so short
out-of-sample windows are not eaten by warm-up. Prepared arrays are cached per window and reused by every
parameter combination. The lab uses the fast engine only; its trades equal NautilusTrader's (REPORT.md,
parity).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from strategy_lab.engines.fast import runner as fast
from strategy_lab.engines.inputs import MarketData, slice_market
from strategy_lab.engines.results import BacktestResult
from strategy_lab.lab.metrics import Metrics, compute
from strategy_lab.spec.indicators import warmup_bars
from strategy_lab.spec.params import tunable_parameters, with_params
from strategy_lab.spec.schema import AtrStop, AtrTarget, AtrTrail, StrategySpec, StructureStop
from strategy_lab.spec.validator import TIMEFRAME_MINUTES

Point = dict[str, float]
OBJECTIVES = ("sharpe", "net_return_pct", "calmar", "profit_factor")
MIN_TRADES = 10  # fewer trades than this in a window: the objective is not trusted (scored -inf)
WARMUP_FACTOR = 3.0  # recursive indicators (EMA, RSI, ATR) need a few periods beyond their nominal warm-up


@dataclass(frozen=True)
class Window:
    start: pd.Timestamp
    end: pd.Timestamp

    def split(self, fraction: float) -> tuple[Window, Window]:
        cut = (self.start + (self.end - self.start) * fraction).floor("D")
        return Window(self.start, cut), Window(cut, self.end)

    def label(self) -> str:
        return f"{self.start:%Y-%m-%d} → {self.end:%Y-%m-%d}"


def warmup_span(spec: StrategySpec, axes: Mapping[str, Sequence[float]] | None = None) -> pd.Timedelta:
    """History needed before a window so that every indicator is warm at its start (largest tuned values)."""
    if axes:
        spec = with_params(spec, {name: max(values) for name, values in axes.items()})
    base = TIMEFRAME_MINUTES[spec.market.timeframe]
    minutes = [
        warmup_bars(i.type, i.params) * TIMEFRAME_MINUTES[i.timeframe or spec.market.timeframe]
        for i in spec.indicators
    ]
    risk = spec.risk
    for item in (risk.stop_loss, risk.take_profit, risk.trailing_stop):
        if isinstance(item, AtrStop | AtrTarget | AtrTrail):
            minutes.append(item.atr_period * base)
        elif isinstance(item, StructureStop):
            minutes.append(item.lookback * base)
    return pd.Timedelta(minutes=WARMUP_FACTOR * max(minutes, default=0)) + pd.Timedelta(days=1)


def objective_value(metrics: Metrics, objective: str, min_trades: int = MIN_TRADES) -> float:
    if metrics.trades < min_trades:
        return -math.inf
    value = float(getattr(metrics, objective))
    return value if math.isfinite(value) else -math.inf


class Evaluator:
    def __init__(
        self,
        spec: StrategySpec,
        market: MarketData,
        warmup: pd.Timedelta,
        objective: str = "sharpe",
        min_trades: int = MIN_TRADES,
        starting_balance: float = 10_000.0,
    ) -> None:
        if objective not in OBJECTIVES:
            raise ValueError(f"objective must be one of {OBJECTIVES}")
        self.spec = spec
        self.market = market
        self.warmup = warmup
        self.objective = objective
        self.min_trades = min_trades
        self.starting_balance = starting_balance
        self.data_start = market.bars_1m["ts"].iloc[0]
        self._prepared: dict[tuple[pd.Timestamp, pd.Timestamp], fast.Prepared] = {}
        self.runs = 0

    def run(self, window: Window, params: Point | None = None) -> BacktestResult:
        data_start = max(self.data_start, (window.start - self.warmup).floor("D"))
        key = (data_start, window.end)
        if key not in self._prepared:
            self._prepared[key] = fast.prepare(self.spec, slice_market(self.market, data_start, window.end))
        spec = with_params(self.spec, params) if params else self.spec
        self.runs += 1
        return fast.run_prepared(
            self._prepared[key], spec, self.starting_balance, window.start, window.end, trade_from=window.start
        )

    def evaluate(self, window: Window, params: Point | None = None) -> dict[str, Any]:
        """One row: the parameters, every metric and the objective."""
        metrics = compute(self.run(window, params))
        return {
            **(params or {}),
            **metrics.as_dict(),
            "objective": objective_value(metrics, self.objective, self.min_trades),
        }

    def current_params(self, names: Sequence[str]) -> Point:
        values = {p.name: p.value for p in tunable_parameters(self.spec)}
        return {name: values[name] for name in names}
