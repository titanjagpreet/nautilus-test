"""Engine-neutral backtest results: both engines produce a ``BacktestResult`` the lab, API and UI consume.

Fill times are reported as the **open time of the 1-minute bar** in which the fill happened (Nautilus stamps
fills a few nanoseconds into the minute — see the execution feed — and the fast engine works per minute), so
parity can compare timestamps exactly.

The equity curve is computed here, from the trades, the funding ledger and base-bar closes, by the same code
for both engines: equity(t) = cash balance(t) + unrealised PnL of the open position at the bar close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

TRADE_COLUMNS = [
    "side",
    "quantity",
    "entry_time",
    "entry_price",
    "exit_time",
    "exit_price",
    "exit_reason",
    "entry_fee",
    "exit_fee",
    "fees",
    "funding",
    "pnl_gross",
    "pnl_net",
]
# pnl_gross = price PnL; fees = entry_fee + exit_fee; funding = paid while open (positive = cost);
# pnl_net = pnl_gross - fees - funding.


@dataclass
class BacktestResult:
    engine: str
    spec_name: str
    market: str
    bars_source: str
    funding_source: str | None
    start: pd.Timestamp
    end: pd.Timestamp
    starting_balance: float
    trades: pd.DataFrame  # TRADE_COLUMNS
    funding: pd.DataFrame  # ts, rate, position_size, price, amount (positive = paid)
    equity: pd.Series  # indexed by base-bar close time
    wall_seconds: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def fees_paid(self) -> float:
        return float(self.trades["fees"].sum()) if len(self.trades) else 0.0

    @property
    def funding_paid(self) -> float:
        return float(self.funding["amount"].sum()) if len(self.funding) else 0.0

    @property
    def net_pnl(self) -> float:
        """Final cash minus the starting balance: price PnL − fees − funding (all positions close at the end)."""
        gross = float(self.trades["pnl_gross"].sum()) if len(self.trades) else 0.0
        return gross - self.fees_paid - self.funding_paid

    def summary(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "spec": self.spec_name,
            "market": self.market,
            "bars_source": self.bars_source,
            "funding_source": self.funding_source,
            "start": str(self.start),
            "end": str(self.end),
            "trades": len(self.trades),
            "net_pnl": round(self.net_pnl, 6),
            "fees_paid": round(self.fees_paid, 6),
            "funding_paid": round(self.funding_paid, 6),
            "final_equity": round(self.starting_balance + self.net_pnl, 6),
            "wall_seconds": round(self.wall_seconds, 3),
        }


def trades_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=TRADE_COLUMNS)
    for col in ("entry_time", "exit_time"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    return frame


def _ns(values: pd.Series) -> npt.NDArray[np.int64]:
    out: npt.NDArray[np.int64] = values.dt.as_unit("ns").astype("int64").to_numpy(dtype=np.int64)
    return out


def _floats(frame: pd.DataFrame, column: str) -> npt.NDArray[np.float64]:
    return frame[column].to_numpy(dtype=np.float64)


def equity_curve(
    trades: pd.DataFrame,
    funding: pd.DataFrame,
    closes: pd.Series,
    starting_balance: float,
) -> pd.Series:
    """Mark-to-market equity at each base-bar close ``T`` (``closes`` indexed by close time).

    Cash moves when things happen: the entry fee at entry, ``pnl_gross - exit_fee`` at exit, each funding
    payment at its time. An event counts at ``T`` only if it happened strictly before ``T`` (a fill at the open
    that follows a bar close belongs to the next bar). The position is marked at ``T`` when entry < T ≤ exit.
    """
    t_ns = _ns(pd.Series(closes.index))
    close_values = closes.to_numpy(dtype=np.float64)
    cash_delta = np.zeros(len(t_ns) + 1, dtype=np.float64)  # delta applied from that bar index onwards
    unrealised = np.zeros(len(t_ns), dtype=np.float64)
    if len(trades):
        i_entry = np.searchsorted(t_ns, _ns(trades["entry_time"]), side="right")
        i_exit = np.searchsorted(t_ns, _ns(trades["exit_time"]), side="right")
        np.add.at(cash_delta, i_entry, -_floats(trades, "entry_fee"))
        np.add.at(cash_delta, i_exit, _floats(trades, "pnl_gross") - _floats(trades, "exit_fee"))
        signs = np.where(trades["side"].to_numpy() == "long", 1.0, -1.0)
        qty, entry_px = _floats(trades, "quantity"), _floats(trades, "entry_price")
        for k in range(len(trades)):
            a, b = int(i_entry[k]), int(i_exit[k])
            unrealised[a:b] += signs[k] * qty[k] * (close_values[a:b] - entry_px[k])
    if len(funding):
        i_pay = np.searchsorted(t_ns, _ns(funding["ts"]), side="right")
        np.add.at(cash_delta, i_pay, -_floats(funding, "amount"))
    cash = starting_balance + np.cumsum(cash_delta)[:-1]
    return pd.Series(cash + unrealised, index=closes.index, name="equity")
