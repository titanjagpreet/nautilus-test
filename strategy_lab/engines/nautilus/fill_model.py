"""Order-type-aware slippage for NautilusTrader's simulated venue.

The stock ``FillModel(prob_slippage=1.0)`` slips *every* L1 fill by one tick — take-profit limit orders included,
which is unrealistic (a limit never fills worse than its price). This subclass slips only MARKET and
STOP_MARKET fills. It works through two public override points (verified in backtest/engine.pyx, 1.231.0):

1. ``get_orderbook_for_fill_simulation(instrument, order, best_bid, best_ask)`` is called right before every
   market/limit fill with the order. We note the order type and return ``None`` so the matching engine keeps
   its standard fill logic (which is what gives stop orders their trigger-price fill).
2. ``is_slipped()`` is then asked inside ``apply_fills``; we answer from the note.
"""

from __future__ import annotations

from typing import Any

from nautilus_trader.backtest.models import FillModel
from nautilus_trader.model.enums import OrderType

SLIPPED_ORDER_TYPES = frozenset({OrderType.MARKET, OrderType.STOP_MARKET})


class MarketAndStopSlippageFillModel(FillModel):  # type: ignore[misc]
    def __init__(self, slippage_ticks: int) -> None:
        if slippage_ticks not in (0, 1):
            raise ValueError("NautilusTrader's fill model supports 0 or 1 tick of slippage per fill")
        super().__init__(prob_fill_on_limit=1.0, prob_slippage=0.0, random_seed=None)
        self._enabled = slippage_ticks == 1
        self._slip_next = False

    def get_orderbook_for_fill_simulation(self, instrument: Any, order: Any, best_bid: Any, best_ask: Any) -> None:
        self._slip_next = self._enabled and order.order_type in SLIPPED_ORDER_TYPES

    def is_slipped(self) -> bool:
        return self._slip_next
