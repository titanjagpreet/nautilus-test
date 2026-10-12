"""Dukascopy XAUUSD 1m bid + ask via the ``dukascopy-node`` CLI (npm, MIT), run through ``npx``.

Command per year and price side (flags from the dukascopy-node 1.50.0 CLI help)::

    npx --yes dukascopy-node@1.50.0 -i xauusd -from 2015-01-01 -to 2016-01-01 -t m1 -p bid \
        -f csv -v -vu units -dir data/raw/dukascopy -fn xauusd-m1-bid-2015

Output CSV header ``timestamp,open,high,low,close,volume``; timestamp = bar open in Unix ms (UTC); the date
range is ``[from, to)``. Flat zero-volume minutes are dropped by the tool by default, so closures stay gaps.
Since dukascopy-node 1.49 the data comes from ``jetta.dukascopy.com`` (older versions used
``datafeed.dukascopy.com`` .bi5 files); both hosts belong to Dukascopy.

Mid bars: ``(bid + ask) / 2`` for each of open/high/low/close (the usual approximation — bid and ask extremes
may occur at different moments), plus ``spread = ask_close - bid_close`` as an extra column.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pandas as pd

from strategy_lab import config
from strategy_lab.data.sources.http import SourceUnavailableError

PACKAGE = "dukascopy-node@1.50.0"
FIRST_YEAR = 2015


def _raw_dir() -> Path:
    return config.raw_dir() / "dukascopy"


def _run_cli(side: str, start: pd.Timestamp, end: pd.Timestamp, name: str) -> Path:
    if shutil.which("npx") is None:
        raise SourceUnavailableError("npx (Node.js) is not installed")
    out_dir = _raw_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.csv"
    if target.exists() and target.stat().st_size > 0:
        return target
    cmd = [
        "npx", "--yes", PACKAGE,
        "-i", "xauusd", "-from", f"{start:%Y-%m-%d}", "-to", f"{end:%Y-%m-%d}",
        "-t", "m1", "-p", side, "-f", "csv", "-v", "-vu", "units",
        "-dir", str(out_dir), "-fn", name, "-r", "3", "-bs", "10", "-bp", "1000",
    ]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)
    if proc.returncode != 0 or not target.exists():
        tail = (proc.stderr or proc.stdout)[-400:]
        raise SourceUnavailableError(f"dukascopy-node failed for {name}: {tail}")
    return target


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["ts"] = pd.to_datetime(frame["timestamp"].astype("int64"), unit="ms", utc=True)
    return frame.drop(columns=["timestamp"])


def fetch_xau(last_full_month: pd.Period) -> pd.DataFrame:
    """Download bid and ask year by year (resumable) and build mid bars with a spread column."""
    end_all = last_full_month.to_timestamp(how="end").normalize().tz_localize("UTC") + pd.Timedelta(days=1)
    mids = []
    for year in range(FIRST_YEAR, end_all.year + 1):
        start = pd.Timestamp(f"{year}-01-01", tz="UTC")
        end = min(pd.Timestamp(f"{year + 1}-01-01", tz="UTC"), end_all)
        if start >= end:
            break
        bid = _read(_run_cli("bid", start, end, f"xauusd-m1-bid-{year}"))
        ask = _read(_run_cli("ask", start, end, f"xauusd-m1-ask-{year}"))
        both = bid.merge(ask, on="ts", suffixes=("_bid", "_ask"), how="inner")
        mid = pd.DataFrame({"ts": both["ts"]})
        for col in ("open", "high", "low", "close"):
            mid[col] = (both[f"{col}_bid"] + both[f"{col}_ask"]) / 2.0
        mid["volume"] = both["volume_bid"].astype("float64")
        mid["spread"] = both["close_ask"] - both["close_bid"]
        mids.append(mid)
    out = pd.concat(mids, ignore_index=True)
    out["source"] = "dukascopy"
    out["symbol"] = "XAUUSD"
    return out
