"""Executable versions of the NautilusTrader 1.231 behaviours documented in LEARNINGS.md §2-§6, §9.

All bars are hand-made synthetic data built here (never results). Instrument: the BTC-PERP default spec
(tick 0.1). Each test pins one behaviour so a NautilusTrader upgrade that changes it fails loudly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FillModel, MakerTakerFeeModel
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from strategy_lab.engines.nautilus.data_loading import bar_type_for, read_catalog_bars, wrangle_bars, write_catalog
from strategy_lab.engines.nautilus.instruments import VENUE, make_instrument
from strategy_lab.engines.nautilus.venue import VenueSettings, add_lighter_venue, new_engine

MIN = 60_000_000_000
INSTRUMENT = make_instrument("BTC-PERP", maker_fee=0.0, taker_fee=0.0)
ONE_MIN = bar_type_for(INSTRUMENT, "1m")
QTY = Quantity.from_str("1.00000")


def bars(rows: list[tuple[float, float, float, float]], bar_type: BarType = ONE_MIN) -> list[Bar]:
    """Bar k covers minute k and is stamped at its close, (k + 1) minutes."""
    big = Quantity(1_000_000, 5)
    return [
        Bar(bar_type, Price(o, 1), Price(h, 1), Price(lo, 1), Price(c, 1), big, (k + 1) * MIN, (k + 1) * MIN)
        for k, (o, h, lo, c) in enumerate(rows)
    ]


class Scripted(Strategy):  # type: ignore[misc]
    """Runs ``actions[n](self)`` on the n-th bar (1-based) and records fills."""

    def __init__(self, actions: dict[int, Callable[[Strategy], None]], bar_type: BarType = ONE_MIN) -> None:
        super().__init__(StrategyConfig(strategy_id="S-001"))
        self.actions, self.bar_type, self.n = actions, bar_type, 0
        self.fills: list[tuple[str, float, int]] = []
        self.rejections: list[str] = []

    def on_start(self) -> None:
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        self.n += 1
        if self.n in self.actions:
            self.actions[self.n](self)

    def on_order_filled(self, event: Any) -> None:
        order = self.cache.order(event.client_order_id)
        self.fills.append((order.order_type.name, event.last_px.as_double(), event.ts_event))

    def on_order_rejected(self, event: Any) -> None:
        self.rejections.append(event.reason)


def run(strategy: Scripted, data: list[Bar], engine: BacktestEngine | None = None, **venue: Any) -> BacktestEngine:
    if engine is None:
        engine = new_engine()
        engine.add_venue(
            VENUE,
            OmsType.NETTING,
            AccountType.MARGIN,
            [Money(10_000, USDC)],
            base_currency=USDC,
            fee_model=MakerTakerFeeModel(),
            **venue,
        )
        engine.add_instrument(INSTRUMENT)
    engine.add_data(data)
    engine.add_strategy(strategy)
    engine.run()
    return engine


def buy(s: Strategy) -> None:
    s.submit_order(s.order_factory.market(INSTRUMENT.id, OrderSide.BUY, QTY))


def bracket(sl: float, tp: float) -> Callable[[Strategy], None]:
    def act(s: Strategy) -> None:
        s.submit_order_list(
            s.order_factory.bracket(
                INSTRUMENT.id, OrderSide.BUY, QTY, sl_trigger_price=Price(sl, 1), tp_price=Price(tp, 1)
            )
        )

    return act


ROWS = [
    (100.0, 101.0, 99.0, 100.5),
    (100.6, 102.0, 100.0, 101.0),
    (101.2, 103.0, 100.8, 102.5),
    (103.6, 106.0, 90.0, 104.0),  # wide bar: both 95 and 105 inside
    (104.1, 105.0, 103.0, 104.5),
]


def test_market_order_fills_at_the_signal_bars_close() -> None:
    s = Scripted({2: buy})
    run(s, bars(ROWS))
    assert s.fills == [("MARKET", 101.0, 2 * MIN)]


def test_fixed_bar_ordering_hits_take_profit_before_stop() -> None:
    """O-H-L-C: with SL 95 and TP 105 both inside bar 4 the take-profit wins (not conservative)."""
    s = Scripted({2: bracket(95.0, 105.0)})
    run(s, bars(ROWS))
    assert [f[:2] for f in s.fills] == [("MARKET", 101.0), ("LIMIT", 105.0)]


def test_stock_fill_model_slips_limit_orders_too() -> None:
    s = Scripted({2: bracket(95.0, 105.0)})
    run(s, bars(ROWS), fill_model=FillModel(prob_slippage=1.0, random_seed=1))
    assert [f[:2] for f in s.fills] == [("MARKET", 101.1), ("LIMIT", 104.9)]  # limit filled worse than its price


def test_our_fill_model_slips_market_and_stop_but_not_limit() -> None:
    engine = new_engine()
    add_lighter_venue(engine, "BTC-PERP", VenueSettings(slippage_ticks=1, adaptive_bar_ordering=False), None)
    s = Scripted({2: bracket(95.0, 105.0)})
    run(s, bars(ROWS), engine=engine)
    assert [f[:2] for f in s.fills] == [("MARKET", 101.1), ("LIMIT", 105.0)]
    stop_rows = [*ROWS[:3], (103.6, 103.8, 90.0, 92.0)]
    engine = new_engine()
    add_lighter_venue(engine, "BTC-PERP", VenueSettings(slippage_ticks=1, adaptive_bar_ordering=False), None)
    s = Scripted({2: bracket(95.0, 120.0)})
    run(s, bars(stop_rows), engine=engine)
    assert [f[:2] for f in s.fills] == [("MARKET", 101.1), ("STOP_MARKET", 94.9)]  # trigger price - 1 tick


@pytest.mark.parametrize(("reject", "expect_stop_fill"), [(True, False), (False, True)])
def test_reject_stop_orders_switch(reject: bool, expect_stop_fill: bool) -> None:
    """A stop placed when the market is already through it: rejected (position unprotected) or filled."""

    def entry_with_bad_stop(s: Strategy) -> None:
        buy(s)
        s.submit_order(
            s.order_factory.stop_market(INSTRUMENT.id, OrderSide.SELL, QTY, Price(150.0, 1), reduce_only=True)
        )

    s = Scripted({2: entry_with_bad_stop})
    run(s, bars(ROWS), reject_stop_orders=reject)
    assert any(f[0] == "STOP_MARKET" for f in s.fills) is expect_stop_fill
    assert bool(s.rejections) is reject


def test_finest_bar_type_drives_execution_and_ts_init_delta_orders_strategy_bars() -> None:
    """1m and 15m bars together: only 1m bars move the venue, and with ts_init_delta=1 the 15m bar reaches the
    strategy after the venue processed the last 1m bar of the same timestamp → the fill is at that 1m close."""
    one_min = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=30, freq="1min", tz="UTC"),
            "open": [100.0 + k for k in range(30)],
            "high": [100.5 + k for k in range(30)],
            "low": [99.5 + k for k in range(30)],
            "close": [100.2 + k for k in range(30)],
            "volume": 1_000.0,
        }
    )
    fifteen = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:15"], utc=True),
            "open": [100.0, 115.0],
            "high": [114.5, 129.5],
            "low": [99.5, 114.5],
            "close": [114.2, 129.2],
            "volume": 15.0,
        }
    )
    data = wrangle_bars(one_min, INSTRUMENT, "1m") + wrangle_bars(fifteen, INSTRUMENT, "15m", ts_init_delta=1)
    s = Scripted({1: buy}, bar_type=bar_type_for(INSTRUMENT, "15m"))
    run(s, data)
    at_0015 = pd.Timestamp("2024-01-01 00:15", tz="UTC").value
    # Filled at the close of the 1m bar 00:14-00:15, when the 15m bar is delivered (ts_init = close + 1 ns).
    assert s.fills == [("MARKET", 114.2, at_0015 + 1)]


def test_small_bar_volume_splits_market_orders() -> None:
    """Each bar price point only offers a quarter of the bar's volume; the rest fills one tick worse."""
    big, small = bars(ROWS), bars(ROWS)
    small = [Bar(b.bar_type, b.open, b.high, b.low, b.close, Quantity(1, 5), b.ts_event, b.ts_init) for b in small]
    s_big, s_small = Scripted({2: buy}), Scripted({2: buy})
    run(s_big, big)
    run(s_small, small)
    assert [f[1] for f in s_big.fills] == [101.0]
    assert [f[1] for f in s_small.fills] == [101.0, 101.1]  # 0.25 at the close, 0.75 one tick worse


def test_wrangler_and_catalog_produce_identical_bars(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=5, freq="1min", tz="UTC"),
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 3.0,
        }
    )
    direct = wrangle_bars(frame, INSTRUMENT, "1m")
    assert direct[0].ts_event == pd.Timestamp("2024-01-01 00:01", tz="UTC").value  # stamped at the close
    write_catalog(tmp_path, INSTRUMENT, direct)
    back = read_catalog_bars(
        tmp_path, ONE_MIN, pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2024-01-02", tz="UTC")
    )
    assert back == direct


def test_funding_module_charges_position_at_funding_time() -> None:
    """Long 1 BTC from 00:02; funding at 00:03 (+0.1%) is charged at the 00:03 price; at 00:00 (pre-entry) not."""
    funding = pd.DataFrame(
        {"ts": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:03"], utc=True), "rate": [0.01, 0.001]}
    )
    engine = new_engine()
    _, module = add_lighter_venue(engine, "BTC-PERP", VenueSettings(slippage_ticks=0), funding)
    rows = [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 101.0, 100.0, 101.0),
        (101.0, 102.0, 101.0, 102.0),
        (102.0, 103.0, 102.0, 103.0),
        (103.0, 104.0, 103.0, 104.0),
    ]
    start = pd.Timestamp("2024-01-01", tz="UTC").value
    data = [
        Bar(ONE_MIN, b.open, b.high, b.low, b.close, b.volume, b.ts_event + start, b.ts_init + start)
        for b in bars(rows)
    ]
    s = Scripted({2: buy})
    run(s, data, engine=engine)
    assert module is not None
    assert [(p.ts.minute, p.position_size, p.price, round(p.amount, 6)) for p in module.payments] == [
        (3, 1.0, 102.0, 0.102)
    ]
    balance = engine.portfolio.account(VENUE).balance_total(USDC).as_double()
    assert balance == pytest.approx(10_000 - 0.102)  # the open position's unrealized PnL is not in the balance
