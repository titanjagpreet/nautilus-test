"""Perpetual funding for NautilusTrader backtests.

NautilusTrader 1.231 does not settle funding in the simulated exchange (``FundingRateUpdate`` is a data type
only; LEARNINGS.md §6), so this ``SimulationModule`` does it, modelled on the built-in
``FXRolloverInterestModule``.

Rule (identical in the fast engine): a funding event at time ``F`` applies to the position held after every
fill stamped ``<= F``, priced at the last traded price at or before ``F``. Payment = signed size × price ×
rate; a positive rate means longs pay shorts. It is applied in ``pre_process`` — i.e. *before* the venue
handles the first piece of data stamped after ``F`` — and booked with ``exchange.adjust_account``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from nautilus_trader.backtest.config import SimulationModuleConfig
from nautilus_trader.backtest.modules import SimulationModule
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money


@dataclass(frozen=True)
class FundingPayment:
    ts: pd.Timestamp
    rate: float
    position_size: float  # signed base units
    price: float
    amount: float  # paid by us (positive = cost)


class FundingModule(SimulationModule):  # type: ignore[misc]
    def __init__(self, instrument_id: InstrumentId, funding: pd.DataFrame) -> None:
        super().__init__(SimulationModuleConfig())
        frame = funding.sort_values("ts")
        self._instrument_id = instrument_id
        self._times = frame["ts"].dt.as_unit("ns").astype("int64").to_numpy(dtype=np.int64)
        self._rates = frame["rate"].to_numpy(dtype=np.float64)
        self._next = 0
        self.payments: list[FundingPayment] = []

    def pre_process(self, data: Any) -> None:
        ts = data.ts_init
        while self._next < len(self._times) and self._times[self._next] < ts:
            self._settle(int(self._times[self._next]), float(self._rates[self._next]))
            self._next += 1

    def process(self, ts_now: int) -> None:
        """Nothing to do after commands are processed; settlement happens in ``pre_process``."""

    def _settle(self, ts_ns: int, rate: float) -> None:
        positions = self.exchange.cache.positions_open(instrument_id=self._instrument_id)
        size = sum(p.signed_qty for p in positions)
        if size == 0.0:
            return
        book = self.exchange.get_book(self._instrument_id)
        bid, ask = book.best_bid_price(), book.best_ask_price()
        if bid is None or ask is None:
            return  # no price yet: nothing has traded, so no position can exist either
        price = (bid.as_double() + ask.as_double()) / 2.0
        amount = size * price * rate
        self.exchange.adjust_account(Money(-amount, USDC))
        self.payments.append(FundingPayment(pd.Timestamp(ts_ns, tz="UTC"), rate, size, price, amount))

    def log_diagnostics(self, logger: Any) -> None:
        logger.info(f"Funding paid (total): {self.total_paid:.6f} USDC over {len(self.payments)} events")

    def reset(self) -> None:
        self._next = 0
        self.payments = []

    @property
    def total_paid(self) -> float:
        return float(sum(p.amount for p in self.payments))
