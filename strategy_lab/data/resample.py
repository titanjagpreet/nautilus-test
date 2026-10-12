"""Resample canonical 1m bars to higher timeframes, anchored to UTC.

Rules: a bin ``[t, t + tf)`` is labelled with its open time ``t`` (same convention as the 1m data);
open = first, high = max, low = min, close = last, volume = sum. Bins with no 1m bars produce no row
(market closures stay closures). ``n_minutes`` counts the 1m bars inside each bin so incomplete bars
are visible. Daily bars run 00:00-24:00 UTC.
"""

from __future__ import annotations

import pandas as pd

from strategy_lab.data.schema import TIMEFRAMES, check_bars


def resample_bars(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate 1m bars (one source/symbol) into ``timeframe`` bars."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe {timeframe!r}; expected one of {list(TIMEFRAMES)}")
    check_bars(bars)
    if bars.empty:
        out = bars.iloc[0:0].copy()
        out["n_minutes"] = pd.Series([], dtype="int64")
        return out
    if bars["source"].nunique() != 1 or bars["symbol"].nunique() != 1:
        raise ValueError("resample one source/symbol at a time")

    width = TIMEFRAMES[timeframe]
    frame = bars.sort_values("ts")
    # Floor to the bin start; epoch-anchored floors are UTC-midnight aligned for every supported width.
    bin_start = frame["ts"].dt.floor(width)
    grouped = frame.groupby(bin_start, sort=True)
    out = pd.DataFrame(
        {
            "open": grouped["open"].first(),
            "high": grouped["high"].max(),
            "low": grouped["low"].min(),
            "close": grouped["close"].last(),
            "volume": grouped["volume"].sum(),
            "n_minutes": grouped["open"].size().astype("int64"),
        }
    )
    out.index.name = "ts"
    out = out.reset_index()
    extra = [c for c in frame.columns if c not in {"ts", "open", "high", "low", "close", "volume"}]
    for col in extra:
        if col in ("source", "symbol"):
            out[col] = frame[col].iloc[0]
        elif col == "spread":
            out[col] = grouped[col].last().to_numpy()
    return out
