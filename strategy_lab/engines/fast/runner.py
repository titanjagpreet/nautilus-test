"""Run a spec on the Numba engine; same inputs and same ``BacktestResult`` as the NautilusTrader runner."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from strategy_lab.costs import MAX_SLIPPAGE_TICKS, fee_profile
from strategy_lab.data.resample import resample_bars
from strategy_lab.data.schema import TIMEFRAMES
from strategy_lab.engines.contracts import ContractSpec, contract_spec
from strategy_lab.engines.fast import indicators as ind_fn
from strategy_lab.engines.fast.compile import BarFrame, Compiled
from strategy_lab.engines.fast.simulate import (
    ATR,
    BOTH,
    LONG_ONLY,
    NONE,
    PCT,
    REASONS,
    RR,
    SHORT_ONLY,
    SIZING_FIXED,
    SIZING_PCT,
    STRUCTURE,
    simulate,
)
from strategy_lab.engines.inputs import MarketData, funding_8h, load_market
from strategy_lab.engines.results import BacktestResult, attribute_funding, equity_curve, trades_frame
from strategy_lab.spec.schema import (
    AtrStop,
    AtrTarget,
    AtrTrail,
    PercentEquity,
    PercentStop,
    PercentTarget,
    PercentTrail,
    RiskRewardTarget,
    StrategySpec,
    StructureStop,
)

ENGINE_NAME = "fast"
F64 = npt.NDArray[np.float64]


def pack_params(spec: StrategySpec, contract: ContractSpec, starting_balance: float) -> F64:
    risk, costs = spec.risk, spec.costs
    fees = fee_profile(costs.fee_profile)
    direction = {"long": LONG_ONLY, "short": SHORT_ONLY, "both": BOTH}[spec.market.direction]
    sizing = risk.position_sizing
    stop = risk.stop_loss
    if isinstance(stop, PercentStop):
        stop_kind, stop_value = PCT, stop.value
    elif isinstance(stop, AtrStop):
        stop_kind, stop_value = ATR, stop.multiple
    else:
        assert isinstance(stop, StructureStop)
        stop_kind, stop_value = STRUCTURE, stop.buffer_pct
    tp = risk.take_profit
    tp_kind, tp_value = NONE, 0.0
    if isinstance(tp, PercentTarget):
        tp_kind, tp_value = PCT, tp.value
    elif isinstance(tp, AtrTarget):
        tp_kind, tp_value = ATR, tp.multiple
    elif isinstance(tp, RiskRewardTarget):
        tp_kind, tp_value = RR, tp.multiple
    trail = risk.trailing_stop
    trail_kind, trail_value = NONE, 0.0
    if isinstance(trail, PercentTrail):
        trail_kind, trail_value = PCT, trail.value
    elif isinstance(trail, AtrTrail):
        trail_kind, trail_value = ATR, trail.multiple
    slip = min(costs.slippage_ticks, MAX_SLIPPAGE_TICKS) * contract.tick_size
    return np.array(
        [
            direction,
            SIZING_PCT if isinstance(sizing, PercentEquity) else SIZING_FIXED,
            sizing.value,
            risk.leverage,
            stop_kind,
            stop_value,
            tp_kind,
            tp_value,
            trail_kind,
            trail_value,
            risk.time_exit_bars if risk.time_exit_bars is not None else -1,
            risk.cooldown_bars,
            risk.max_trades_per_day if risk.max_trades_per_day is not None else -1,
            slip,
            fees.taker_rate,
            fees.maker_rate,
            10.0**contract.price_decimals,
            10.0**contract.size_decimals,
            contract.min_quantity,
            starting_balance,
        ],
        dtype=np.float64,
    )


@dataclass(frozen=True)
class Prepared:
    """Everything that does not depend on tunable parameters except via the spec (reused by sweeps)."""

    spec: StrategySpec
    market: MarketData
    contract: ContractSpec
    minutes: BarFrame
    base: BarFrame
    m_base_close: npt.NDArray[np.int64]
    f_minute: npt.NDArray[np.int64]
    f_rate: F64
    f_ts: pd.Series
    indicator_cache: dict[tuple[object, ...], dict[str, F64]]  # shared by sweep runs on the same data
    htf_cache: dict[str, BarFrame]


def prepare(spec: StrategySpec, market: MarketData) -> Prepared:
    contract = contract_spec(spec.market.symbol)
    minutes = BarFrame.from_frame(market.bars_1m, "1m")
    base_frame = resample_bars(market.bars_1m, spec.market.timeframe)
    base = BarFrame.from_frame(base_frame, spec.market.timeframe)
    ends = np.searchsorted(minutes.open_ns, base.close_ns, side="left")
    m_base_close = np.full(len(minutes), -1, dtype=np.int64)
    m_base_close[ends - 1] = np.arange(len(base), dtype=np.int64)
    funding = market.funding
    if spec.costs.funding and not funding.empty:
        f_ns = funding["ts"].dt.as_unit("ns").astype("int64").to_numpy()
        keep = f_ns <= base.close_ns[-1]  # charged at the latest just before the final close-out
        f_minute = np.searchsorted(minutes.open_ns, f_ns[keep], side="left").astype(np.int64)
        f_rate = funding["rate"].to_numpy(dtype=np.float64)[keep]
        f_ts = funding["ts"][keep].reset_index(drop=True)
    else:
        f_minute, f_rate = np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)
        f_ts = pd.Series([], dtype="datetime64[ns, UTC]")
    return Prepared(spec, market, contract, minutes, base, m_base_close, f_minute, f_rate, f_ts, {}, {})


def run_prepared(
    prep: Prepared,
    spec: StrategySpec | None = None,
    starting_balance: float = 10_000.0,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> BacktestResult:
    """Simulate ``spec`` (default: the prepared one; it may differ only in tunable parameters)."""
    t0 = time.perf_counter()
    spec = spec or prep.spec
    base, minutes = prep.base, prep.minutes
    htf: dict[str, BarFrame] = {
        tf: _htf_frame(prep, tf)
        for tf in {i.timeframe for i in spec.indicators if i.timeframe not in (None, spec.market.timeframe)}
        if tf is not None
    }
    funding_ns, funding_rate = funding_8h(prep.market.funding)
    compiled = Compiled(spec, base, htf, funding_ns, funding_rate, prep.indicator_cache)
    rules = spec.rules
    entry_long, exit_long = compiled.evaluate(rules.entry_long), compiled.evaluate(rules.exit_long)
    entry_short, exit_short = compiled.evaluate(rules.entry_short), compiled.evaluate(rules.exit_short)

    nan = np.full(len(base), np.nan)
    atr_by_period = {p: ind_fn.atr(base.high, base.low, base.close, p) for p in _risk_periods(spec)}
    risk_ready = np.ones(len(base), dtype=np.bool_)
    for values in atr_by_period.values():
        risk_ready &= ~np.isnan(values)
    stop, tp, trail = spec.risk.stop_loss, spec.risk.take_profit, spec.risk.trailing_stop
    lookback = stop.lookback if isinstance(stop, StructureStop) else 1
    lows = pd.Series(base.low).rolling(lookback, min_periods=1).min().to_numpy()
    highs = pd.Series(base.high).rolling(lookback, min_periods=1).max().to_numpy()
    b_day = (base.close_ns // 86_400_000_000_000).astype(np.int64)

    trades_arr, funding_arr = simulate(
        minutes.open, minutes.high, minutes.low, minutes.close, prep.m_base_close,
        base.close, b_day, entry_long, exit_long, entry_short, exit_short, risk_ready,
        atr_by_period[stop.atr_period] if isinstance(stop, AtrStop) else nan,
        atr_by_period[tp.atr_period] if isinstance(tp, AtrTarget) else nan,
        atr_by_period[trail.atr_period] if isinstance(trail, AtrTrail) else nan,
        lows, highs, prep.f_minute, prep.f_rate,
        pack_params(spec, prep.contract, starting_balance),
    )  # fmt: skip
    minute_ns = np.r_[minutes.open_ns, base.close_ns[-1]]  # index n_min = the final base close (end exits)
    minute_ts = pd.DatetimeIndex(minute_ns.astype("datetime64[ns]")).tz_localize("UTC")
    rows = [
        {
            "side": "long" if t[0] > 0 else "short",
            "quantity": t[1],
            "entry_time": minute_ts[int(t[2])],
            "entry_price": t[3],
            "exit_time": minute_ts[int(t[4])],
            "exit_price": t[5],
            "exit_reason": REASONS[int(t[6])],
            "entry_fee": t[7],
            "exit_fee": t[8],
            "fees": t[7] + t[8],
            "funding": 0.0,
            "pnl_gross": t[0] * t[1] * (t[5] - t[3]),
            "pnl_net": 0.0,
        }
        for t in trades_arr
    ]
    trades = trades_frame(rows)
    funding = pd.DataFrame(
        {
            "ts": prep.f_ts.iloc[funding_arr[:, 0].astype(np.int64)].reset_index(drop=True),
            "rate": prep.f_rate[funding_arr[:, 0].astype(np.int64)],
            "position_size": funding_arr[:, 1],
            "price": funding_arr[:, 2],
            "amount": funding_arr[:, 3],
        }
    )
    trades["pnl_net"] = trades["pnl_gross"] - trades["fees"]
    attribute_funding(trades, funding)
    closes = pd.Series(base.close, index=pd.to_datetime(base.close_ns, utc=True))
    return BacktestResult(
        engine=ENGINE_NAME,
        spec_name=spec.meta.name,
        market=spec.market.symbol,
        bars_source=prep.market.source,
        funding_source=prep.market.funding_source if len(prep.f_rate) else None,
        start=start if start is not None else pd.Timestamp(minutes.open_ns[0], tz="UTC"),
        end=end if end is not None else pd.Timestamp(base.close_ns[-1], tz="UTC"),
        starting_balance=starting_balance,
        trades=trades,
        funding=funding,
        equity=equity_curve(trades, funding, closes, starting_balance),
        closes=closes,
        wall_seconds=time.perf_counter() - t0,
        meta={"contract_spec": prep.contract.origin, "minutes": len(minutes), "base_bars": len(base)},
    )


def _htf_frame(prep: Prepared, timeframe: str) -> BarFrame:
    if timeframe not in prep.htf_cache:
        prep.htf_cache[timeframe] = BarFrame.from_frame(resample_bars(prep.market.bars_1m, timeframe), timeframe)
    return prep.htf_cache[timeframe]


def _risk_periods(spec: StrategySpec) -> list[int]:
    risk = spec.risk
    return sorted({x.atr_period for x in (risk.stop_loss, risk.take_profit, risk.trailing_stop)
                   if isinstance(x, AtrStop | AtrTarget | AtrTrail)})  # fmt: skip


def run_spec(
    spec: StrategySpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
    source: str | None = None,
    starting_balance: float = 10_000.0,
    market: MarketData | None = None,
) -> BacktestResult:
    t0 = time.perf_counter()
    contract = contract_spec(spec.market.symbol)
    data = market or load_market(spec.market.symbol, start, end, contract.price_decimals, source)
    result = run_prepared(prepare(spec, data), spec, starting_balance, start, end)
    result.wall_seconds = time.perf_counter() - t0
    return result


__all__ = ["TIMEFRAMES", "Prepared", "pack_params", "prepare", "run_prepared", "run_spec"]
