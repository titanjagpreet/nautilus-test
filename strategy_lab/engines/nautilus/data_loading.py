"""Two ways to get bars into a NautilusTrader backtest (both explained in LEARNINGS.md §9).

1. **Directly**, with ``BarDataWrangler``: pandas frame → ``list[Bar]`` → ``engine.add_data``. Simple, all in
   memory, best for one-off runs and for tests.
2. **Through a ``ParquetDataCatalog``**: write the bars once into Nautilus's own Parquet layout, then query them
   back by bar type and time range (or stream them with ``BacktestNode``). Best when many runs reuse the same
   data, or the data does not fit in memory.

Our canonical bars are stamped at the bar **open**; Nautilus expects ``ts_event`` = bar **close**, so the index
is shifted by one bar width before wrangling. Prices are rounded to the instrument tick here, once, so both
engines see the same numbers (``engine_inputs.round_to_tick``).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler

from strategy_lab.data.schema import TIMEFRAMES
from strategy_lab.engines.inputs import round_to_tick

NAUTILUS_STEP = {
    "1m": "1-MINUTE",
    "5m": "5-MINUTE",
    "15m": "15-MINUTE",
    "1h": "1-HOUR",
    "4h": "4-HOUR",
    "1d": "1-DAY",
}


def bar_type_for(instrument: Instrument, timeframe: str) -> BarType:
    return BarType.from_str(f"{instrument.id}-{NAUTILUS_STEP[timeframe]}-LAST-EXTERNAL")


def wrangle_bars(bars: pd.DataFrame, instrument: Instrument, timeframe: str, ts_init_delta: int = 0) -> list[Bar]:
    """Canonical bars (open-time stamped) → Nautilus bars stamped at close time.

    ``ts_init_delta`` > 0 delays when the engine delivers the bar (``ts_init = ts_event + delta``). We use 1 ns
    for strategy-timeframe bars so that, at a shared timestamp, the venue first processes the last 1-minute
    execution bar and only then the strategy sees the higher-timeframe bar.
    """
    frame = round_to_tick(bars, instrument.price_precision)
    close_time = (frame["ts"] + TIMEFRAMES[timeframe]).dt.as_unit("ns")  # the wrangler reads raw ns from the index
    frame = frame.set_index(close_time)[["open", "high", "low", "close", "volume"]]
    wrangler = BarDataWrangler(bar_type=bar_type_for(instrument, timeframe), instrument=instrument)
    result: list[Bar] = wrangler.process(frame, ts_init_delta=ts_init_delta)
    return result


def write_catalog(path: Path, instrument: Instrument, bars: list[Bar]) -> ParquetDataCatalog:
    catalog = ParquetDataCatalog(str(path))
    catalog.write_data([instrument])
    catalog.write_data(bars)
    return catalog


def read_catalog_bars(path: Path, bar_type: BarType, start: pd.Timestamp, end: pd.Timestamp) -> list[Bar]:
    catalog = ParquetDataCatalog(str(path))
    bars: list[Bar] = catalog.bars(bar_types=[str(bar_type)], start=start, end=end)
    return bars
