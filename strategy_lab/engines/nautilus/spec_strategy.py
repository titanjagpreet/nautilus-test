"""SpecStrategy: one generic NautilusTrader strategy that runs any valid spec. No code generation, no eval.

Rules are evaluated by ``spec.evaluator.SpecState``; position management comes from ``spec.decisions`` (shared
with the fast engine). The strategy publishes ``expected_side`` so the execution feed can order each minute's
prices adverse-extreme-first (``exec_feed``).

Order flow (with the venue's 1 ns latency):
* base-bar close: exits (cancel stop/target, reduce-only market) and entries (market) → fill at the next open;
* entry fill: stop-market + limit take-profit, both reduce-only, priced from the actual fill;
* bar close in a position: the trailing stop is modified (effective after the next open's gap check);
* final base bar: anything open is closed at the last close (exit reason "end").
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from strategy_lab.data.schema import TIMEFRAMES
from strategy_lab.spec.decisions import (
    RiskInputs,
    Signals,
    TradeState,
    decide,
    entry_quantity,
    risk_atr_periods,
    round_price,
    stop_price,
    structure_lookback,
    target_price,
    tighter,
    trailing_candidate,
)
from strategy_lab.spec.evaluator import SpecState
from strategy_lab.spec.schema import Indicator, StrategySpec
from strategy_lab.spec.streaming import BarValues, make_runtime


class SpecStrategy(Strategy):  # type: ignore[misc]
    def __init__(
        self,
        spec: StrategySpec,
        instrument: Instrument,
        base_type: BarType,
        htf_types: dict[str, BarType],
        funding_ns: np.ndarray,
        funding_rate_8h: np.ndarray,
        final_close_ns: int,
        min_quantity: float,
    ) -> None:
        super().__init__(StrategyConfig(strategy_id="SPEC-001"))
        self.spec = spec
        self.instrument = instrument
        self.base_type = base_type
        self.htf_by_type = {bt: tf for tf, bt in htf_types.items()}
        self.funding_ns = funding_ns
        self.funding_rate_8h = funding_rate_8h
        self.final_close_ns = final_close_ns
        self.min_quantity = min_quantity
        self.price_decimals = instrument.price_precision
        self.size_decimals = instrument.size_precision
        self.base_width_ns = int(TIMEFRAMES[spec.market.timeframe].value)

        self.rules = SpecState(spec)
        self.risk_atr = {
            p: make_runtime(Indicator(id=f"risk_atr_{p}", type="atr", params={"period": p}))
            for p in risk_atr_periods(spec)
        }
        lookback = max(structure_lookback(spec), 1)
        self.highs: deque[float] = deque(maxlen=lookback)
        self.lows: deque[float] = deque(maxlen=lookback)

        self.trade = TradeState(entries_by_day={})
        self.expected_side = "flat"
        self.entry_ids: set[ClientOrderId] = set()
        self.pending: tuple[str, RiskInputs] | None = None
        self.stop_id: ClientOrderId | None = None
        self.target_id: ClientOrderId | None = None
        self.exit_reason: str | None = None
        self.closed: list[dict[str, Any]] = []
        self._open: dict[str, Any] | None = None

    # -- data ------------------------------------------------------------------------------------------

    def on_start(self) -> None:
        self.subscribe_bars(self.base_type)
        for bar_type in self.htf_by_type:
            self.subscribe_bars(bar_type)

    def _values(self, bar: Bar, width_ns: int) -> BarValues:
        open_time = datetime.fromtimestamp((bar.ts_event - width_ns) / 1e9, tz=UTC)
        return BarValues(
            open_time,
            bar.open.as_double(),
            bar.high.as_double(),
            bar.low.as_double(),
            bar.close.as_double(),
            bar.volume.as_double(),
        )

    def _funding_8h(self, close_ns: int) -> float | None:
        i = int(np.searchsorted(self.funding_ns, close_ns, side="right")) - 1
        return float(self.funding_rate_8h[i]) if i >= 0 else None

    def on_bar(self, bar: Bar) -> None:
        if bar.bar_type != self.base_type:
            tf = self.htf_by_type[bar.bar_type]
            self.rules.update(tf, self._values(bar, int(TIMEFRAMES[tf].value)))
            return
        values = self._values(bar, self.base_width_ns)
        self.rules.update(self.spec.market.timeframe, values, self._funding_8h(bar.ts_event))
        for runtime in self.risk_atr.values():
            runtime.update(values)
        self.highs.append(values.high)
        self.lows.append(values.low)
        if self.trade.side != "flat":
            self.trade.bars_held += 1
        if self.trade.bars_since_exit is not None:
            self.trade.bars_since_exit += 1
        if bar.ts_event >= self.final_close_ns:
            if self.trade.side != "flat":
                self._exit("end")
            self.expected_side = "flat"
            return
        if any(not r.initialized for r in self.risk_atr.values()):
            return  # no ATR yet: an ATR-based exit could not be placed
        self._decide(values, bar.ts_event)

    # -- decisions -------------------------------------------------------------------------------------

    def _decide(self, values: BarValues, close_ns: int) -> None:
        rules = self.spec.rules
        signals = Signals(
            self.rules.evaluate(rules.entry_long),
            self.rules.evaluate(rules.exit_long),
            self.rules.evaluate(rules.entry_short),
            self.rules.evaluate(rules.exit_short),
        )
        day = pd.Timestamp(close_ns, tz="UTC").strftime("%Y-%m-%d")
        decision = decide(self.spec, self.trade, signals, day)
        inputs = RiskInputs(
            atr={p: r.outputs()["value"] for p, r in self.risk_atr.items()},
            lowest_low=min(self.lows),
            highest_high=max(self.highs),
            close=values.close,
        )
        if decision.exit:
            self._exit(decision.exit_reason or "rule")
        if decision.enter is not None:
            equity = self.portfolio.account(self.instrument.id.venue).balance_total(USDC).as_double()
            qty = entry_quantity(self.spec, equity, values.close, self.size_decimals, self.min_quantity)
            if qty > 0.0:
                side = OrderSide.BUY if decision.enter == "long" else OrderSide.SELL
                order = self.order_factory.market(self.instrument.id, side, Quantity(qty, self.size_decimals))
                self.entry_ids.add(order.client_order_id)
                self.pending = (decision.enter, inputs)
                entries = self.trade.entries_by_day
                assert entries is not None
                entries[day] = entries.get(day, 0) + 1
                self.submit_order(order)
                self.expected_side = decision.enter
                return
        if decision.exit:
            self.expected_side = "flat"
        elif self.trade.side != "flat" and self.stop_id is not None:
            order = self.cache.order(self.stop_id)
            if order is None or not order.is_open:
                return
            # Compare with the venue's live trigger: a modify that was already in the market got rejected.
            current = order.trigger_price.as_double()
            candidate = trailing_candidate(self.spec, self.trade.side, inputs, self.price_decimals)
            new_stop = tighter(self.trade.side, current, candidate)
            if new_stop is not None:
                self.modify_order(order, trigger_price=Price(new_stop, self.price_decimals))

    def _exit(self, reason: str) -> None:
        self.exit_reason = reason
        for order_id in (self.stop_id, self.target_id):
            order = self.cache.order(order_id) if order_id is not None else None
            if order is not None and order.is_open:
                self.cancel_order(order)
        position = self._position()
        if position is not None:
            self.submit_order(
                self.order_factory.market(
                    self.instrument.id, position.closing_order_side(), position.quantity, reduce_only=True
                )
            )

    def _px(self, price: Price) -> float:
        """Nautilus prices are 128-bit fixed point; ``as_double()`` can be one ulp off the decimal value (e.g.
        65031.299999999996). Use the nearest double of the decimal so both engines compute stops and targets
        from the same number (LEARNINGS.md §13)."""
        return round_price(price.as_double(), self.price_decimals)

    def _position(self) -> Any:
        positions = self.cache.positions_open(instrument_id=self.instrument.id, strategy_id=self.id)
        return positions[0] if positions else None

    # -- events ----------------------------------------------------------------------------------------

    def on_order_filled(self, event: Any) -> None:
        if event.client_order_id in self.entry_ids and self.pending is not None:
            side, inputs = self.pending
            self.pending = None
            fill = self._px(event.last_px)
            self.trade.side = side
            self.trade.bars_held = 0
            stop = stop_price(self.spec, side, fill, inputs, self.price_decimals)
            target = target_price(self.spec, side, fill, stop, inputs, self.price_decimals)
            qty = event.last_qty
            exit_side = OrderSide.SELL if side == "long" else OrderSide.BUY
            stop_order = self.order_factory.stop_market(
                self.instrument.id, exit_side, qty, Price(stop, self.price_decimals), reduce_only=True
            )
            self.stop_id = stop_order.client_order_id
            self.submit_order(stop_order)
            if target is not None:
                tp = self.order_factory.limit(
                    self.instrument.id,
                    exit_side,
                    qty,
                    Price(target, self.price_decimals),
                    time_in_force=TimeInForce.GTC,
                    reduce_only=True,
                )
                self.target_id = tp.client_order_id
                self.submit_order(tp)
            else:
                self.target_id = None
            self._open = {
                "side": side,
                "quantity": qty.as_double(),
                "entry_ns": event.ts_event,
                "entry_price": fill,
                "entry_fee": event.commission.as_double(),
            }
        elif self._open is not None:
            if event.client_order_id == self.stop_id:
                self.exit_reason = "stop"
            elif event.client_order_id == self.target_id:
                self.exit_reason = "target"
            self._open["exit_fee"] = self._open.get("exit_fee", 0.0) + event.commission.as_double()
            self._open["exit_ns"] = event.ts_event
            self._open["exit_price"] = self._px(event.last_px)

    def on_position_closed(self, event: Any) -> None:
        self.trade.side = "flat"
        self.trade.bars_since_exit = 0
        if self.expected_side != "flat" and not self.entry_ids_pending():
            self.expected_side = "flat"
        for order_id in (self.stop_id, self.target_id):
            order = self.cache.order(order_id) if order_id is not None else None
            if order is not None and order.is_open:
                self.cancel_order(order)
        self.stop_id = self.target_id = None
        if self._open is not None:
            self._open["exit_reason"] = self.exit_reason or "rule"
            self.closed.append(self._open)
            self._open = None
        self.exit_reason = None

    def entry_ids_pending(self) -> bool:
        """An entry submitted at this bar close but not filled yet (reversals: exit fills first)."""
        return self.pending is not None
