"""Inputs shared by both engines, so they see byte-identical numbers.

* Which stored dataset backs each market (``BTC-PERP``, ``XAU-PERP``) and which funding series applies.
* Prices rounded to the venue tick, once (Nautilus would round inside ``Price(...)``; doing it here keeps the
  fast engine on exactly the same prices).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy_lab import config
from strategy_lab.data import storage

# Preference order: the target exchange first, then the closest proxy.
BAR_SOURCES: dict[str, list[tuple[str, str]]] = {
    "BTC-PERP": [
        ("lighter", "BTC-PERP"),
        ("binance_futures", "BTCUSDT"),
        ("binance_spot", "BTCUSDT"),
        ("binance_spot_gh", "BTCUSDT"),
        ("bitstamp", "BTCUSD"),
    ],
    "XAU-PERP": [("lighter", "XAU-PERP"), ("dukascopy", "XAUUSD"), ("histdata", "XAUUSD")],
}
FUNDING_SOURCES: dict[str, list[tuple[str, str]]] = {
    "BTC-PERP": [
        ("lighter", "BTC-PERP"),
        ("binance_futures", "BTCUSDT"),
        ("binance_futures_funding_gh", "BTCUSDT"),
    ],
    "XAU-PERP": [("lighter", "XAU-PERP")],
}


def available_bar_sources(market: str) -> list[str]:
    stored = set(storage.list_datasets())
    return [f"{s}/{y}" for s, y in BAR_SOURCES[market] if (s, y) in stored]


def resolve_bar_source(market: str, source: str | None = None) -> tuple[str, str]:
    options = available_bar_sources(market)
    if not options:
        raise FileNotFoundError(f"no stored bars for {market}; run `make data`")
    chosen = source or options[0]
    if chosen not in options:
        raise ValueError(f"source {chosen!r} not available for {market}; available: {options}")
    src, sym = chosen.split("/", 1)
    return src, sym


def round_to_tick(bars: pd.DataFrame, price_decimals: int) -> pd.DataFrame:
    """Round OHLC to ``price_decimals`` (half away from zero, like Nautilus's fixed-point conversion)."""
    out = bars.copy()
    scale = 10.0**price_decimals
    for col in ("open", "high", "low", "close"):
        values = out[col].to_numpy(dtype=np.float64) * scale
        out[col] = np.sign(values) * np.floor(np.abs(values) + 0.5) / scale
    return out


@dataclass(frozen=True)
class MarketData:
    market: str
    source: str  # "source/symbol" of the bars
    bars_1m: pd.DataFrame  # canonical, open-time stamped, tick-rounded
    funding: pd.DataFrame  # ts, rate (per period), period_hours; empty when the market has no funding data
    funding_source: str | None


def load_market(
    market: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    price_decimals: int,
    source: str | None = None,
) -> MarketData:
    src, sym = resolve_bar_source(market, source)
    bars = round_to_tick(storage.read_bars(src, sym, start, end), price_decimals)
    if bars.empty:
        raise ValueError(f"no {src}/{sym} bars between {start} and {end}")
    empty = {"ts": pd.Series([], dtype="datetime64[ns, UTC]"), "rate": [], "period_hours": []}
    funding, funding_source = pd.DataFrame(empty), None
    stored = set(storage.list_datasets(config.funding_dir()))
    for f_src, f_sym in FUNDING_SOURCES[market]:
        if (f_src, f_sym) in stored:
            funding = storage.read_funding(f_src, f_sym, start, end)[["ts", "rate", "period_hours"]]
            funding_source = f"{f_src}/{f_sym}"
            break
    return MarketData(market, f"{src}/{sym}", bars.reset_index(drop=True), funding, funding_source)
