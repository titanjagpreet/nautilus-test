"""Phase 2 measurements: wall time and peak RSS of NautilusTrader runs, each in a fresh process.

    uv run python benchmarks/nautilus_phase2.py

Scenarios (all real BTC data, hand-written EMA/ATR strategy, premium fees, 1-tick slippage, funding on):
* empty node — Python + nautilus_trader imported + engine with venue and instrument, no data
* 1 year of 1m bars, strategy on 1m (venue executes on the same 1m bars)
* 5 years of 15m bars, strategy on 15m (venue executes on 15m bars)
* 2 years: strategy on 15m, venue executes on 1m bars (the Phase 2 reference run)

Each scenario runs twice: with NautilusTrader's stock PortfolioAnalyzer and with our patch for its quadratic
per-trade ``pd.concat`` (strategy_lab/engines/nautilus/patches.py). Results are identical; only time differs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).parent / "results" / "nautilus_phase2.json"

EMPTY_NODE = """
import json, resource, time
t0 = time.perf_counter()
import nautilus_trader
base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
from strategy_lab.engines.nautilus.venue import VenueSettings, add_lighter_venue, new_engine
engine = new_engine()
add_lighter_venue(engine, "BTC-PERP", VenueSettings(), None)
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(json.dumps({"wall_s": round(time.perf_counter() - t0, 2), "import_only_rss_mb": round(base, 1),
                  "peak_rss_mb": round(peak, 1)}))
"""

SCENARIOS = {
    "1y_1m_strategy_1m": [
        "--start",
        "2025-07-01",
        "--end",
        "2026-07-01",
        "--timeframe",
        "1m",
        "--exec-timeframe",
        "1m",
    ],
    "5y_15m_strategy_15m": [
        "--start",
        "2021-07-01",
        "--end",
        "2026-07-01",
        "--timeframe",
        "15m",
        "--exec-timeframe",
        "15m",
    ],
    "2y_15m_strategy_1m_exec": [
        "--start",
        "2024-07-01",
        "--end",
        "2026-07-01",
        "--timeframe",
        "15m",
        "--exec-timeframe",
        "1m",
    ],
}


def run(cmd: list[str]) -> dict[str, object]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")][-1]
    result: dict[str, object] = json.loads(line)
    return result


def main() -> None:
    results = {"empty_node": run([sys.executable, "-c", EMPTY_NODE])}
    print("empty_node", results["empty_node"], flush=True)
    for name, args in SCENARIOS.items():
        for variant, extra in (("stock", ["--stock-analyzer"]), ("patched", [])):
            key = f"{name}/{variant}"
            cmd = [sys.executable, "-m", "strategy_lab.engines.nautilus.handwritten", "--measure", *args, *extra]
            results[key] = run(cmd)
            keep = {k: results[key][k] for k in ("wall_s", "peak_rss_mb", "data_points", "positions", "net_pnl")}
            print(key, keep, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
