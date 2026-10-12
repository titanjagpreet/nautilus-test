"""Phase 2: a hand-written NautilusTrader strategy, written the "native" Nautilus way.

EMA(12) / EMA(48) crossover, long and short. Each entry is a **bracket order**: a market entry plus a
stop-loss at 2×ATR(14) and a take-profit at 3×ATR(14) from the signal bar's close, as linked contingent orders
(the venue cancels the survivor when one fills). Position size: 20% of account equity in notional.

Native Nautilus execution semantics apply here (orders fill at the close of the bar that produced the signal,
intrabar order follows the venue's bar ordering) — the generic spec strategy in Phase 3 adds the spec's
"next open / stop first" semantics on top (LEARNINGS.md §7).
"""

from __future__ import annotations

from nautilus_trader.config import StrategyConfig
from nautilus_trader.indicators import AverageTrueRange, ExponentialMovingAverage, MovingAverageType
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy


class EmaCrossBracketConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    fast_period: int = 12
    slow_period: int = 48
    atr_period: int = 14
    sl_atr_multiple: float = 2.0
    tp_atr_multiple: float = 3.0
    equity_fraction: float = 0.20


class EmaCrossBracket(Strategy):  # type: ignore[misc]
    def __init__(self, config: EmaCrossBracketConfig) -> None:
        super().__init__(config)
        self.fast = ExponentialMovingAverage(config.fast_period)
        self.slow = ExponentialMovingAverage(config.slow_period)
        self.atr = AverageTrueRange(config.atr_period, MovingAverageType.WILDER)
        self.instrument: Instrument | None = None
        self._prev_diff: float | None = None
        self.signals = 0

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        # Registered indicators are updated by the framework *before* on_bar is called.
        for indicator in (self.fast, self.slow, self.atr):
            self.register_indicator_for_bars(self.config.bar_type, indicator)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if not (self.fast.initialized and self.slow.initialized and self.atr.initialized):
            return
        diff = self.fast.value - self.slow.value
        prev, self._prev_diff = self._prev_diff, diff
        if prev is None:
            return
        if prev <= 0.0 < diff:
            self._enter(OrderSide.BUY, bar)
        elif prev >= 0.0 > diff:
            self._enter(OrderSide.SELL, bar)

    def _enter(self, side: OrderSide, bar: Bar) -> None:
        assert self.instrument is not None
        instrument_id = self.config.instrument_id
        if (side == OrderSide.BUY and self.portfolio.is_net_long(instrument_id)) or (
            side == OrderSide.SELL and self.portfolio.is_net_short(instrument_id)
        ):
            return
        self.signals += 1
        # Flip: cancel the old bracket's resting orders and flatten before entering the other way.
        self.cancel_all_orders(instrument_id)
        self.close_all_positions(instrument_id)

        account = self.portfolio.account(instrument_id.venue)
        equity = account.balance_total(USDC).as_double()
        price = bar.close.as_double()
        quantity = self.instrument.make_qty(equity * self.config.equity_fraction / price)
        if quantity.as_double() <= 0.0:
            return
        distance_sl = self.config.sl_atr_multiple * self.atr.value
        distance_tp = self.config.tp_atr_multiple * self.atr.value
        sign = 1.0 if side == OrderSide.BUY else -1.0
        bracket = self.order_factory.bracket(
            instrument_id=instrument_id,
            order_side=side,
            quantity=quantity,
            sl_trigger_price=self.instrument.make_price(price - sign * distance_sl),
            tp_price=self.instrument.make_price(price + sign * distance_tp),
        )
        self.submit_order_list(bracket)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)
