"""Run any valid spec in NautilusTrader and return an engine-neutral ``BacktestResult``."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from strategy_lab.costs import MAX_SLIPPAGE_TICKS
from strategy_lab.data.resample import resample_bars
from strategy_lab.data.schema import TIMEFRAMES
from strategy_lab.engines.inputs import MarketData, load_market
from strategy_lab.engines.nautilus import patches
from strategy_lab.engines.nautilus.data_loading import bar_type_for
from strategy_lab.engines.nautilus.exec_feed import BarArrays, execution_stream
from strategy_lab.engines.nautilus.instruments import contract_spec
from strategy_lab.engines.nautilus.spec_strategy import SpecStrategy
from strategy_lab.engines.nautilus.venue import VenueSettings, add_lighter_venue, new_engine
from strategy_lab.engines.results import BacktestResult, equity_curve, trades_frame
from strategy_lab.spec.schema import StrategySpec

ENGINE_NAME = "nautilus"


def funding_8h(funding: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Funding times (ns) and rates scaled to an 8-hour period (the spec's ``funding_rate`` input)."""
    if funding.empty:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)
    ts = funding["ts"].dt.as_unit("ns").astype("int64").to_numpy()
    rate = (funding["rate"] * 8.0 / funding["period_hours"]).to_numpy(dtype=np.float64)
    return ts, rate


def run_spec(
    spec: StrategySpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
    source: str | None = None,
    starting_balance: float = 10_000.0,
    market: MarketData | None = None,
) -> BacktestResult:
    """Backtest ``spec`` on [start, end). ``market`` may be passed in to reuse already-loaded data."""
    t0 = time.perf_counter()
    patches.install()
    symbol = spec.market.symbol
    contract = contract_spec(symbol)
    data = market or load_market(symbol, start, end, contract.price_decimals, source)
    minutes = data.bars_1m
    base = resample_bars(minutes, spec.market.timeframe)
    htf_frames: dict[str, pd.DataFrame] = {
        ind.timeframe: resample_bars(minutes, ind.timeframe)
        for ind in spec.indicators
        if ind.timeframe is not None and ind.timeframe != spec.market.timeframe
    }

    settings = VenueSettings(
        leverage=spec.risk.leverage,
        starting_balance=starting_balance,
        fee_profile=spec.costs.fee_profile,
        slippage_ticks=min(spec.costs.slippage_ticks, MAX_SLIPPAGE_TICKS),
        adaptive_bar_ordering=False,  # the feed orders each minute's prices itself
        latency_ns=1,
    )
    engine = new_engine()
    charge_funding = spec.costs.funding and not data.funding.empty
    instrument, module = add_lighter_venue(engine, symbol, settings, data.funding if charge_funding else None)

    exec_type = bar_type_for(instrument, "1m")
    base_type = bar_type_for(instrument, spec.market.timeframe)
    htf_types = {tf: bar_type_for(instrument, tf) for tf in htf_frames}
    funding_ns, funding_rate = funding_8h(data.funding)
    base_arrays = BarArrays.from_frame(base)
    base_width = TIMEFRAMES[spec.market.timeframe]
    final_close_ns = int(base_arrays.open_ns[-1] + base_width.value)
    strategy = SpecStrategy(
        spec, instrument, base_type, htf_types, funding_ns, funding_rate, final_close_ns, contract.min_quantity
    )
    engine.add_strategy(strategy)
    engine.add_data_iterator(
        "execution",
        execution_stream(
            BarArrays.from_frame(minutes),
            base_arrays,
            spec.market.timeframe,
            {tf: BarArrays.from_frame(f) for tf, f in htf_frames.items()},
            exec_type,
            base_type,
            htf_types,
            instrument.price_precision,
            instrument.size_precision,
            lambda: strategy.expected_side,
        ),
    )
    engine.run()

    rows = []
    for t in strategy.closed:
        sign = 1.0 if t["side"] == "long" else -1.0
        gross = sign * t["quantity"] * (t["exit_price"] - t["entry_price"])
        rows.append(
            {
                "side": t["side"],
                "quantity": t["quantity"],
                "entry_time": pd.Timestamp(t["entry_ns"], tz="UTC").floor("1min"),
                "entry_price": t["entry_price"],
                "exit_time": pd.Timestamp(t["exit_ns"], tz="UTC").floor("1min"),
                "exit_price": t["exit_price"],
                "exit_reason": t["exit_reason"],
                "entry_fee": t["entry_fee"],
                "exit_fee": t["exit_fee"],
                "fees": t["entry_fee"] + t["exit_fee"],
                "funding": 0.0,
                "pnl_gross": gross,
                "pnl_net": gross - t["entry_fee"] - t["exit_fee"],
            }
        )
    trades = trades_frame(rows)
    funding = (
        pd.DataFrame([p.__dict__ for p in module.payments])
        if module is not None
        else pd.DataFrame(
            {
                "ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                "rate": [],
                "position_size": [],
                "price": [],
                "amount": [],
            }
        )
    )
    attribute_funding(trades, funding)
    closes = pd.Series(base["close"].to_numpy(), index=pd.DatetimeIndex(base["ts"] + base_width))
    account_balance = engine.portfolio.account(instrument.id.venue).balance_total().as_double()
    engine.dispose()
    return BacktestResult(
        engine=ENGINE_NAME,
        spec_name=spec.meta.name,
        market=symbol,
        bars_source=data.source,
        funding_source=data.funding_source if charge_funding else None,
        start=start,
        end=end,
        starting_balance=starting_balance,
        trades=trades,
        funding=funding,
        equity=equity_curve(trades, funding, closes, starting_balance),
        wall_seconds=time.perf_counter() - t0,
        meta={
            "contract_spec": contract.origin,
            "nautilus_final_balance": account_balance,
            "minutes": len(minutes),
            "base_bars": len(base),
        },
    )


def attribute_funding(trades: pd.DataFrame, funding: pd.DataFrame) -> None:
    """Add each funding payment to the trade that held the position when it was charged (in place).

    Fill times are minute-open times; a trade covers funding time F when entry < F ≤ exit (a position entered
    at F's minute opened after F, one exiting in F's minute was still held at F).
    """
    if trades.empty or funding.empty:
        return
    totals = np.zeros(len(trades))
    entry = trades["entry_time"].dt.as_unit("ns").astype("int64").to_numpy()
    exit_ = trades["exit_time"].dt.as_unit("ns").astype("int64").to_numpy()
    for ts, amount in zip(funding["ts"].dt.as_unit("ns").astype("int64"), funding["amount"], strict=True):
        hit = np.flatnonzero((entry < ts) & (ts <= exit_))
        if len(hit):
            totals[hit[0]] += amount
    trades["funding"] = totals
    trades["pnl_net"] = trades["pnl_gross"] - trades["fees"] - trades["funding"]
