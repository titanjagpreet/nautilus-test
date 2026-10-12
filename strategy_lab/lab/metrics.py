"""Performance metrics from an engine-neutral ``BacktestResult``.

Conventions:
* Returns come from the **daily** mark-to-market equity (last value of each UTC day). Sharpe/Sortino are
  annualised with 365 days for crypto (trades every day) and 252 for gold; risk-free rate 0.
* Drawdown is measured on the base-bar equity curve, in % of the running peak; its duration is the longest
  time from a peak until equity regained it (or until the end if it never did).
* Profit factor and win rate use each trade's net P&L (after fees and its share of funding).
* Buy & hold: the market's own return from the first open to the last close of the test, and its drawdown.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategy_lab.engines.results import BacktestResult

DAYS_PER_YEAR = {"BTC-PERP": 365.0, "XAU-PERP": 252.0}


@dataclass(frozen=True)
class Metrics:
    trades: int
    net_pnl: float
    net_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    max_drawdown_days: float
    sharpe: float
    sortino: float
    calmar: float
    win_rate_pct: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    exposure_pct: float
    fees_paid: float
    funding_paid: float
    buy_hold_return_pct: float
    buy_hold_max_drawdown_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in asdict(self).items()}


def drawdown(equity: pd.Series) -> tuple[float, float]:
    """(max drawdown in % of peak — negative or 0, longest underwater period in days)."""
    if equity.empty:
        return 0.0, 0.0
    values = equity.to_numpy(dtype=np.float64)
    peak = np.maximum.accumulate(values)
    dd = values / peak - 1.0
    times = equity.index
    longest = pd.Timedelta(0)
    start = None
    for i in range(len(values)):
        if values[i] < peak[i]:
            if start is None:
                start = times[i - 1] if i > 0 else times[i]
        elif start is not None:
            longest = max(longest, times[i] - start)
            start = None
    if start is not None:
        longest = max(longest, times[-1] - start)
    return float(dd.min() * 100.0), longest / pd.Timedelta(days=1)


def daily_returns(equity: pd.Series) -> pd.Series:
    daily = equity.resample("1D").last().dropna()
    return daily.pct_change().dropna()


def compute(result: BacktestResult) -> Metrics:
    equity = result.equity
    trades = result.trades
    start_balance = result.starting_balance
    net = result.net_pnl
    years = (
        max((equity.index[-1] - equity.index[0]) / pd.Timedelta(days=365.25), 1e-9) if len(equity) > 1 else 1e-9
    )
    final = start_balance + net
    cagr = ((final / start_balance) ** (1.0 / years) - 1.0) * 100.0 if final > 0 else -100.0
    max_dd, dd_days = drawdown(equity)
    rets = daily_returns(equity)
    periods = DAYS_PER_YEAR.get(result.market, 365.0)
    std = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    downside = rets[rets < 0]
    down_std = float(np.sqrt((downside**2).sum() / len(rets))) if len(rets) else 0.0
    sharpe = float(rets.mean() / std * math.sqrt(periods)) if std > 0 else 0.0
    sortino = float(rets.mean() / down_std * math.sqrt(periods)) if down_std > 0 else 0.0
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    pnl = trades["pnl_net"].to_numpy(dtype=np.float64) if len(trades) else np.empty(0)
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)

    span_s = float((equity.index[-1] - equity.index[0]).total_seconds()) if len(equity) > 1 else 0.0
    held_s = float((trades["exit_time"] - trades["entry_time"]).dt.total_seconds().sum()) if len(trades) else 0.0
    exposure = held_s / span_s * 100.0 if span_s > 0 else 0.0

    bh_return = bh_dd = math.nan
    closes = result.closes
    if len(closes) > 1:
        bh_return = float((closes.iloc[-1] / closes.iloc[0] - 1.0) * 100.0)
        bh_dd, _ = drawdown(closes)
    return Metrics(
        trades=len(trades),
        net_pnl=round(net, 6),
        net_return_pct=net / start_balance * 100.0,
        cagr_pct=cagr,
        max_drawdown_pct=max_dd,
        max_drawdown_days=dd_days,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        win_rate_pct=float(len(wins) / len(pnl) * 100.0) if len(pnl) else 0.0,
        profit_factor=profit_factor,
        expectancy=float(pnl.mean()) if len(pnl) else 0.0,
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(losses.mean()) if len(losses) else 0.0,
        exposure_pct=exposure,
        fees_paid=result.fees_paid,
        funding_paid=result.funding_paid,
        buy_hold_return_pct=bh_return,
        buy_hold_max_drawdown_pct=bh_dd,
    )
