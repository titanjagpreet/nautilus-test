"""Phase 2 runner: the hand-written EMA/ATR bracket strategy on real data.

    python -m strategy_lab.engines.nautilus.handwritten --start 2024-07-01 --end 2026-07-01 --timeframe 15m

``--loader wrangler`` (default) builds bars in memory; ``--loader catalog`` writes them to a
ParquetDataCatalog first and reads them back (both paths are explained in LEARNINGS.md §9).
``--measure`` prints wall time and peak RSS as JSON (used by the Phase 2 measurements).
"""

from __future__ import annotations

import argparse
import json
import resource
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd

from strategy_lab import config
from strategy_lab.data.resample import resample_bars
from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.inputs import load_market
from strategy_lab.engines.nautilus import patches
from strategy_lab.engines.nautilus.data_loading import (
    bar_type_for,
    read_catalog_bars,
    wrangle_bars,
    write_catalog,
)
from strategy_lab.engines.nautilus.ema_strategy import EmaCrossBracket, EmaCrossBracketConfig
from strategy_lab.engines.nautilus.reports import NautilusRunReport, collect
from strategy_lab.engines.nautilus.venue import VenueSettings, add_lighter_venue, new_engine


def run_handwritten(
    start: pd.Timestamp,
    end: pd.Timestamp,
    strategy_timeframe: str = "15m",
    execution_timeframe: str = "1m",
    settings: VenueSettings | None = None,
    loader: str = "wrangler",
    funding_on: bool = True,
    source: str | None = None,
    analyzer_patch: bool = True,
) -> tuple[NautilusRunReport, dict[str, Any]]:
    settings = settings or VenueSettings()
    (patches.install if analyzer_patch else patches.uninstall)()
    spec = contract_spec("BTC-PERP")
    market = load_market("BTC-PERP", start, end, spec.price_decimals, source)
    exec_frame = (
        market.bars_1m if execution_timeframe == "1m" else resample_bars(market.bars_1m, execution_timeframe)
    )

    engine = new_engine()
    funding = market.funding if funding_on else None
    instrument, module = add_lighter_venue(engine, "BTC-PERP", settings, funding)

    data = wrangle_bars(exec_frame, instrument, execution_timeframe)
    if strategy_timeframe != execution_timeframe:
        strategy_frame = resample_bars(market.bars_1m, strategy_timeframe)
        data += wrangle_bars(strategy_frame, instrument, strategy_timeframe, ts_init_delta=1)
    if loader == "catalog":
        with tempfile.TemporaryDirectory(dir=config.data_dir()) as tmp:
            write_catalog(Path(tmp), instrument, data)
            data = []
            for tf in dict.fromkeys([execution_timeframe, strategy_timeframe]):
                data += read_catalog_bars(
                    Path(tmp), bar_type_for(instrument, tf), start, end + pd.Timedelta(days=1)
                )
    engine.add_data(data)

    strategy = EmaCrossBracket(
        EmaCrossBracketConfig(instrument_id=instrument.id, bar_type=bar_type_for(instrument, strategy_timeframe))
    )
    engine.add_strategy(strategy)
    engine.run()
    report = collect(engine, settings.starting_balance, module)
    meta = {
        "market": "BTC-PERP",
        "bars_source": market.source,
        "funding_source": market.funding_source if funding_on else None,
        "contract_spec": spec.origin,
        "strategy_timeframe": strategy_timeframe,
        "execution_timeframe": execution_timeframe,
        "start": str(start),
        "end": str(end),
        "data_points": len(data),
        "signals": strategy.signals,
        "analyzer_patch": analyzer_patch,
        "settings": settings.__dict__,
    }
    engine.dispose()
    return report, meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-07-01")
    parser.add_argument("--end", default="2026-07-01")
    parser.add_argument("--timeframe", default="15m", help="strategy timeframe")
    parser.add_argument("--exec-timeframe", default="1m", help="bars the venue executes against")
    parser.add_argument("--loader", choices=["wrangler", "catalog"], default="wrangler")
    parser.add_argument("--fee-profile", default="lighter_premium")
    parser.add_argument("--no-funding", action="store_true")
    parser.add_argument("--measure", action="store_true", help="print timing + peak memory JSON only")
    parser.add_argument("--stock-analyzer", action="store_true", help="run without the PortfolioAnalyzer patch")
    parser.add_argument("--out", help="write fills/positions/account/funding CSVs here")
    args = parser.parse_args()

    t0 = time.perf_counter()
    report, meta = run_handwritten(
        pd.Timestamp(args.start, tz="UTC"),
        pd.Timestamp(args.end, tz="UTC"),
        args.timeframe,
        args.exec_timeframe,
        VenueSettings(fee_profile=args.fee_profile),
        args.loader,
        not args.no_funding,
        analyzer_patch=not args.stock_analyzer,
    )
    wall = time.perf_counter() - t0
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    if args.measure:
        print(json.dumps({"wall_s": round(wall, 2), "peak_rss_mb": round(peak_mb, 1), **meta, **report.summary}))
        return
    print(json.dumps({"meta": meta, "summary": report.summary}, indent=2, default=str))
    print("\nNautilus PnL statistics (USDC):")
    for key, value in report.stats_pnls.items():
        print(f"  {key:<28} {value:,.4f}")
    print("Nautilus returns statistics:")
    for key, value in report.stats_returns.items():
        print(f"  {key:<28} {value:,.4f}")
    print(f"\nwall time {wall:.1f}s, peak RSS {peak_mb:.0f} MB")
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        report.fills.to_csv(out / "fills.csv")
        report.positions.to_csv(out / "positions.csv")
        report.account.to_csv(out / "account.csv")
        report.funding_payments.to_csv(out / "funding.csv", index=False)
        (out / "summary.json").write_text(
            json.dumps(
                {
                    "meta": meta,
                    "summary": report.summary,
                    "stats_pnls": report.stats_pnls,
                    "stats_returns": report.stats_returns,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
