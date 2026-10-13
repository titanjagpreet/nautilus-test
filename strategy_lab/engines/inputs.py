"""Inputs shared by both engines, so they see byte-identical numbers.

* Which stored dataset backs each market (``BTC-PERP``, ``XAU-PERP``) and which funding series applies: the most
  preferred one that covers the backtest window, so a short, recent history (Lighter's starts at its listing)
  never silently truncates a longer backtest.
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


COVERAGE_SLACK = pd.Timedelta(days=4)  # a window may start or end on a market closure (weekend + holiday)
Ranges = dict[tuple[str, str], tuple[pd.Timestamp, pd.Timestamp]]


def _covers(span: tuple[pd.Timestamp, pd.Timestamp], start: pd.Timestamp, end: pd.Timestamp) -> bool:
    return span[0] <= start + COVERAGE_SLACK and span[1] >= end - COVERAGE_SLACK


def _describe(ranges: Ranges, options: list[tuple[str, str]]) -> str:
    return "; ".join(f"{s}/{y} {ranges[s, y][0]:%Y-%m-%d} → {ranges[s, y][1]:%Y-%m-%d}" for s, y in options)


def resolve_bar_source(
    market: str, start: pd.Timestamp, end: pd.Timestamp, source: str | None = None
) -> tuple[str, str]:
    """``source`` if given, else the most preferred stored dataset that covers [start, end)."""
    ranges = storage.time_ranges()
    stored = [option for option in BAR_SOURCES[market] if option in ranges]
    if not stored:
        raise FileNotFoundError(f"no stored bars for {market}; run `make data`")
    if source is not None:
        if tuple(source.split("/", 1)) not in stored:
            raise ValueError(
                f"source {source!r} not available for {market}; available: {_describe(ranges, stored)}"
            )
        src, sym = source.split("/", 1)
        return src, sym
    for option in stored:
        if _covers(ranges[option], start, end):
            return option
    window = f"{start:%Y-%m-%d} → {end:%Y-%m-%d}"
    raise ValueError(f"no stored {market} history covers {window}; available: {_describe(ranges, stored)}")


def resolve_funding_source(
    market: str, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[tuple[str, str], str] | None:
    """The most preferred funding series covering [start, end), else the one overlapping it most — then funding is
    charged only where it exists, and the label says so. ``None`` when no series overlaps the window."""
    ranges = storage.time_ranges(config.funding_dir())
    stored = [option for option in FUNDING_SOURCES[market] if option in ranges]
    for option in stored:
        if _covers(ranges[option], start, end):
            return option, f"{option[0]}/{option[1]}"
    overlap = {o: min(ranges[o][1], end) - max(ranges[o][0], start) for o in stored}
    best = max(stored, key=lambda o: overlap[o], default=None)
    if best is None or overlap[best] <= pd.Timedelta(0):
        return None
    lo, hi = ranges[best]
    return best, f"{best[0]}/{best[1]} (partial: {max(lo, start):%Y-%m-%d} → {min(hi, end):%Y-%m-%d})"


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
    history_from: pd.Timestamp | None = None,
) -> MarketData:
    """Bars and funding for [start, end). ``history_from``: also load the same datasets' earlier rows, as far as
    they go (indicator warm-up); the datasets are still chosen by [start, end) alone, so asking for warm-up never
    switches a backtest to a less preferred source."""
    src, sym = resolve_bar_source(market, start, end, source)
    first = min(start, history_from) if history_from is not None else start
    bars = round_to_tick(storage.read_bars(src, sym, first, end), price_decimals)
    if bars.empty:
        raise ValueError(f"no {src}/{sym} bars between {start} and {end}")
    empty = {"ts": pd.Series([], dtype="datetime64[ns, UTC]"), "rate": [], "period_hours": []}
    funding, funding_source = pd.DataFrame(empty), None
    if (chosen := resolve_funding_source(market, start, end)) is not None:
        (f_src, f_sym), funding_source = chosen
        funding = storage.read_funding(f_src, f_sym, first, end)[["ts", "rate", "period_hours"]]
    return MarketData(market, f"{src}/{sym}", bars.reset_index(drop=True), funding, funding_source)


def slice_market(market: MarketData, start: pd.Timestamp, end: pd.Timestamp) -> MarketData:
    """The bars (by open time) and funding events in [start, end)."""
    bars = market.bars_1m
    funding = market.funding
    return MarketData(
        market.market,
        market.source,
        bars[(bars["ts"] >= start) & (bars["ts"] < end)].reset_index(drop=True),
        funding[(funding["ts"] >= start) & (funding["ts"] < end)].reset_index(drop=True),
        market.funding_source,
    )


def funding_8h(funding: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Funding times (ns) and rates scaled to an 8-hour period (the spec's ``funding_rate`` input)."""
    if funding.empty:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)
    ts = funding["ts"].dt.as_unit("ns").astype("int64").to_numpy()
    rate = (funding["rate"] * 8.0 / funding["period_hours"]).to_numpy(dtype=np.float64)
    return ts, rate
