"""Parity of the Numba engine against NautilusTrader on all catalogue strategies, written to REPORT.md.

    uv run python benchmarks/parity_report.py

One year (2024-01-01 → 2025-01-01, real data) per strategy and fee profile. Compares the number of trades,
entry/exit timestamps and exit reasons (must be identical) and net P&L, fees and funding (relative difference).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.fast import runner as fast
from strategy_lab.engines.inputs import MarketData, load_market
from strategy_lab.engines.nautilus import spec_runner as nautilus
from strategy_lab.spec.schema import StrategySpec

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "benchmarks" / "results" / "parity.json"
REPORT = ROOT / "REPORT.md"
START, END = pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), 1e-12) if a != b else 0.0


def compare(spec: StrategySpec, market: MarketData) -> dict[str, Any]:
    a = nautilus.run_spec(spec, START, END, market=market)
    b = fast.run_spec(spec, START, END, market=market)
    same = len(a.trades) == len(b.trades) and all(
        list(a.trades[c]) == list(b.trades[c]) for c in ("entry_time", "exit_time", "exit_reason", "side")
    )
    return {
        "strategy": spec.meta.name,
        "fee_profile": spec.costs.fee_profile,
        "trades": [len(a.trades), len(b.trades)],
        "identical_trades": same,
        "net_pnl": [round(a.net_pnl, 4), round(b.net_pnl, 4)],
        "net_pnl_rel_diff": rel(a.net_pnl, b.net_pnl),
        "fees_rel_diff": rel(a.fees_paid, b.fees_paid),
        "funding_rel_diff": rel(a.funding_paid, b.funding_paid),
        "wall_s": [round(a.wall_seconds, 2), round(b.wall_seconds, 3)],
    }


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| strategy | fees | trades (N / fast) | identical entries, exits, reasons | net P&L Nautilus "
        "| net P&L fast | rel. diff P&L / fees / funding | time Nautilus / fast |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['strategy']} | {r['fee_profile'].removeprefix('lighter_')} | "
            f"{r['trades'][0]} / {r['trades'][1]} | "
            f"{'yes' if r['identical_trades'] else '**NO**'} | {r['net_pnl'][0]:,.2f} | {r['net_pnl'][1]:,.2f} | "
            f"{r['net_pnl_rel_diff']:.0e} / {r['fees_rel_diff']:.0e} / {r['funding_rel_diff']:.0e} | "
            f"{r['wall_s'][0]:.1f} s / {r['wall_s'][1]:.2f} s |"
        )
    return "\n".join(lines)


def main() -> None:
    markets: dict[str, MarketData] = {}
    rows = []
    for path in sorted((ROOT / "strategy_lab" / "spec" / "catalogue").glob("*.json")):
        for profile in ("lighter_standard", "lighter_premium"):
            data = json.loads(path.read_text())
            data["costs"]["fee_profile"] = profile
            spec = StrategySpec.model_validate(data)
            symbol = spec.market.symbol
            if symbol not in markets:
                markets[symbol] = load_market(symbol, START, END, contract_spec(symbol).price_decimals)
            rows.append(compare(spec, markets[symbol]))
            print(rows[-1], flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2))
    begin, end = "<!-- PARITY:BEGIN -->", "<!-- PARITY:END -->"
    text = REPORT.read_text() if REPORT.exists() else "# REPORT\n"
    if begin not in text:
        text += f"\n{begin}\n{end}\n"
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    REPORT.write_text(f"{head}{begin}\n{render(rows)}\n{end}{tail}")


if __name__ == "__main__":
    main()
