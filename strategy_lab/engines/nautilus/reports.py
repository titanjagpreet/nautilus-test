"""Collect NautilusTrader's own reports plus our funding ledger into one result object."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.currencies import USDC

from strategy_lab.engines.nautilus.funding import FundingModule
from strategy_lab.engines.nautilus.instruments import VENUE


@dataclass
class NautilusRunReport:
    fills: pd.DataFrame
    positions: pd.DataFrame
    account: pd.DataFrame
    stats_pnls: dict[str, float]
    stats_returns: dict[str, float]
    funding_payments: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)


def _money(value: object) -> float:
    """Report cells hold Money objects or strings like '1.23 USDC'."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    if hasattr(value, "as_double"):
        return float(value.as_double())
    return float(str(value).split()[0])


def collect(engine: BacktestEngine, starting_balance: float, funding: FundingModule | None) -> NautilusRunReport:
    trader = engine.trader
    fills = trader.generate_order_fills_report()
    positions = trader.generate_positions_report()
    account = trader.generate_account_report(VENUE)
    result = engine.get_result()
    stats_pnls = {k: float(v) for k, v in result.stats_pnls.get(USDC.code, {}).items()}
    stats_returns = {k: float(v) for k, v in result.stats_returns.items()}

    fees = float(sum(_money(c) for c in fills["commissions"].explode())) if "commissions" in fills else 0.0
    realized = float(sum(_money(p) for p in positions["realized_pnl"])) if len(positions) else 0.0
    final_balance = float(engine.portfolio.account(VENUE).balance_total(USDC).as_double())
    payments = pd.DataFrame([p.__dict__ for p in funding.payments]) if funding is not None else pd.DataFrame()
    funding_paid = funding.total_paid if funding is not None else 0.0
    summary = {
        "starting_balance": starting_balance,
        "final_balance": round(final_balance, 6),
        "net_pnl": round(final_balance - starting_balance, 6),
        # Nautilus position realized PnL already has commissions subtracted.
        "realized_pnl_after_fees": round(realized, 6),
        "fees_paid": round(fees, 6),
        "funding_paid": round(funding_paid, 6),
        "funding_events_charged": len(payments),
        "positions": len(positions),
        "orders_filled": len(fills),
        "iterations": result.iterations,
    }
    return NautilusRunReport(fills, positions, account, stats_pnls, stats_returns, payments, summary)
