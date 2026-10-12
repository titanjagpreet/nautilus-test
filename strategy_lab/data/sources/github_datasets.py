"""Fallback datasets published on GitHub (reachable when the primary hosts are blocked).

Every file is fetched from ``raw.githubusercontent.com`` at a **pinned commit**, so a re-run downloads byte-
identical files; the SHA-256 of each file is recorded in ``data/raw/github/manifest.json``. These are
third-party republications or exports — DATA.md lists the publisher, licence and caveats of each.

Datasets:

* ``binance_spot_gh`` — Binance spot BTCUSDT 1m klines republished monthly by a GitHub Action from
  data.binance.vision (repo parshant231234-eng/BTCUSDT-Historical-Data). Same exchange data as the primary
  Binance source, but Binance's own ``.CHECKSUM`` files cannot be checked here (blocked host), so the data is
  cross-checked against Bitstamp instead.
* ``bitstamp`` — Bitstamp BTC/USD 1m since 2012 (ff137/bitstamp-btcusd-minute-data; CC BY-SA 4.0 bulk file,
  CC BY 4.0 updates). The publisher fills missing minutes with flat zero-volume candles; those carry no
  observed trade and are dropped (counted in the quality report).
* ``histdata`` — HistData.com XAUUSD 1m **bid** quotes, 2021-01..2026-05 (re-uploaded in Craig-Pang/QuantXAU
  and Paaktingc/forex_bot). Volume is always 0. Timestamps are exchange-local (see ``histdata_timezone``).
* ``binance_futures_funding_gh`` — Binance USD-M BTCUSDT 8-hourly funding exported from the Binance API
  (VivekWar/Crypto-Funding-Rate-Arbitrage), verified row-by-row against two independent exports.
"""

from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab import config
from strategy_lab.data.sources.binance import detect_epoch_unit
from strategy_lab.data.sources.http import Download, fetch_many, sha256_file

RAW = "https://raw.githubusercontent.com"

BINANCE_SPOT_REPO = (
    "parshant231234-eng/BTCUSDT-Historical-Data",
    "27c9be705ac9280248672c895082c057b979ebff",
)
BITSTAMP_REPO = ("ff137/bitstamp-btcusd-minute-data", "23a4a069c433ae5f5b95f1b64ed3dac72a5353aa")
QUANTXAU_REPO = ("Craig-Pang/QuantXAU", "9042cef49ae761e4c26126bfc011f7683d0d0854")
FOREX_BOT_REPO = ("Paaktingc/forex_bot", "a4f516cf9555b62ff1c708379fb151f1f77ba2dc")
FUNDING_REPOS = {
    "vivekwar": (
        "VivekWar/Crypto-Funding-Rate-Arbitrage",
        "dcbe60250451a8f7d5d230500a9176032e78b7c7",
        "notebooks/BTCUSDT_historical_funding.csv",
    ),
    "huiiisiii": (
        "huiiisiii/IS424-btc-prediction",
        "8410eb3168e97cf3ae9d52c8f0d33d16abeb3e7d",
        "data/binance_funding_BTCUSDT.csv",
    ),
    "kipopopo": (
        "kipopopo/autonomous-futures-bot",
        "e3092bacd54109cc95ceb947b47c343594d30f66",
        "research/data/BTCUSDT-funding.csv",
    ),
}


def raw_url(repo: tuple[str, str], path: str) -> str:
    name, commit = repo
    return f"{RAW}/{name}/{commit}/{path}"


def _local(path: str) -> Path:
    return config.raw_dir() / "github" / path


def _manifest_path() -> Path:
    return config.raw_dir() / "github" / "manifest.json"


def _record_manifest(entries: dict[str, Path]) -> None:
    path = _manifest_path()
    manifest: dict[str, dict[str, object]] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for url, local in entries.items():
        manifest[url] = {"file": str(local.relative_to(config.raw_dir())), "sha256": sha256_file(local),
                         "bytes": local.stat().st_size}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


@dataclass
class GithubFetch:
    files: dict[str, Path] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


def _fetch(urls_to_paths: dict[str, Path], workers: int = 8) -> GithubFetch:
    items = [Download(url, path) for url, path in urls_to_paths.items()]
    results = fetch_many(items, workers=workers)
    out = GithubFetch()
    for url, outcome in results.items():
        if isinstance(outcome, Exception):
            out.missing.append(f"{url}: {outcome}")
        else:
            out.files[url] = outcome
    _record_manifest(out.files)
    return out


# --- Binance spot BTCUSDT republication ------------------------------------------------------


def binance_spot_months(last: pd.Period) -> list[pd.Period]:
    return list(pd.period_range(pd.Period("2017-08", "M"), last, freq="M"))


def fetch_binance_spot(last_month: pd.Period) -> GithubFetch:
    mapping = {}
    for m in binance_spot_months(last_month):
        rel = f"1m/{m.year}/{m.month:02d}/BTCUSDT_1m_{m.year}-{m.month:02d}.csv"
        mapping[raw_url(BINANCE_SPOT_REPO, rel)] = _local(f"binance_spot_gh/{rel}")
    return _fetch(mapping)


def parse_binance_spot_csv(path: Path) -> tuple[pd.DataFrame, str]:
    frame = pd.read_csv(path, usecols=["timestamp", "open", "high", "low", "close", "volume"])
    unit = detect_epoch_unit(frame["timestamp"])
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(frame["timestamp"].astype("int64"), unit=unit, utc=True),
            **{c: frame[c].astype("float64") for c in ("open", "high", "low", "close", "volume")},
        }
    )
    bars["source"] = "binance_spot_gh"
    bars["symbol"] = "BTCUSDT"
    return bars, unit


# --- Bitstamp BTC/USD -------------------------------------------------------------------------

BITSTAMP_FILES = {
    "historical": "data/historical/btcusd_bitstamp_1min_2012-2025.csv.gz",
    "updates": "data/updates/btcusd_bitstamp_1min_latest.csv",
    "provenance": "data/provenance/btcusd_bitstamp_1min.csv",
}


def fetch_bitstamp() -> GithubFetch:
    mapping = {
        raw_url(BITSTAMP_REPO, rel): _local(f"bitstamp/{Path(rel).name}") for rel in BITSTAMP_FILES.values()
    }
    return _fetch(mapping, workers=3)


def parse_bitstamp(paths: list[Path]) -> tuple[pd.DataFrame, int, str]:
    """Concatenate the bulk + update files. Returns (bars, filler rows dropped, timestamp unit)."""
    frames = []
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as fh:
            frames.append(pd.read_csv(io.BytesIO(fh.read())))
    frame = pd.concat(frames, ignore_index=True)
    unit = detect_epoch_unit(frame["timestamp"])
    flat = (
        (frame["volume"] == 0)
        & (frame["open"] == frame["high"])
        & (frame["high"] == frame["low"])
        & (frame["low"] == frame["close"])
    )
    kept = frame.loc[~flat]
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(kept["timestamp"].astype("int64"), unit=unit, utc=True),
            **{c: kept[c].astype("float64") for c in ("open", "high", "low", "close", "volume")},
        }
    )
    bars["source"] = "bitstamp"
    bars["symbol"] = "BTCUSD"
    return bars.reset_index(drop=True), int(flat.sum()), unit


# --- HistData XAUUSD (bid) ----------------------------------------------------------------------

HISTDATA_YEARS = range(2021, 2026)
HISTDATA_2026_MONTHS = range(1, 6)


def fetch_histdata_xau() -> GithubFetch:
    mapping = {}
    base = "XAUUSD/dataAnalysis/data/historical"
    for year in HISTDATA_YEARS:
        rel = f"{base}/HISTDATA_COM_ASCII_XAUUSD_M1{year}/DAT_ASCII_XAUUSD_M1_{year}.csv"
        mapping[raw_url(QUANTXAU_REPO, rel)] = _local(f"histdata/DAT_ASCII_XAUUSD_M1_{year}.csv")
    for month in HISTDATA_2026_MONTHS:
        ym = f"2026{month:02d}"
        rel = f"data/raw/HISTDATA_COM_MT_XAUUSD_M1{ym}/DAT_ASCII_XAUUSD_M1_{ym}.csv"
        mapping[raw_url(FOREX_BOT_REPO, rel)] = _local(f"histdata/DAT_ASCII_XAUUSD_M1_{ym}.csv")
    return _fetch(mapping)


def read_histdata_local(paths: list[Path]) -> pd.DataFrame:
    """Raw HistData rows with naive exchange-local timestamps (``local_ts``), before any tz conversion."""
    frames = [
        pd.read_csv(path, sep=";", header=None, names=["dt", "open", "high", "low", "close", "volume"])
        for path in sorted(paths)
    ]
    frame = pd.concat(frames, ignore_index=True)
    frame["local_ts"] = pd.to_datetime(frame["dt"], format="%Y%m%d %H%M%S")
    return frame.drop(columns=["dt"])


TIMEZONE_HYPOTHESES = ("EST", "America/New_York", "UTC-5+EU_DST")


def histdata_local_to_utc(local_ts: pd.Series, hypothesis: str) -> pd.Series:
    """Convert naive HistData clock times to UTC under one timezone hypothesis (NaT where undefined).

    * ``EST``: fixed UTC-5 (what HistData documents).
    * ``America/New_York``: New York wall clock with US daylight saving.
    * ``UTC-5+EU_DST``: UTC-5 that moves to UTC-4 on the **EU** daylight-saving dates, i.e. the wall clock
      of Europe/Berlin minus six hours (what the data actually shows, see ``histdata_timezone``).
    """
    if hypothesis == "EST":
        return (local_ts + pd.Timedelta(hours=5)).dt.tz_localize("UTC")
    if hypothesis == "America/New_York":
        return local_ts.dt.tz_localize(hypothesis, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    if hypothesis == "UTC-5+EU_DST":
        berlin = (local_ts + pd.Timedelta(hours=6)).dt.tz_localize(
            "Europe/Berlin", ambiguous="NaT", nonexistent="NaT"
        )
        return berlin.dt.tz_convert("UTC")
    raise ValueError(f"unknown timezone hypothesis {hypothesis!r}")


def histdata_timezone(local: pd.DataFrame) -> tuple[str, dict[str, float]]:
    """Pick the clock convention under which the daily gold break starts at 17:00 New York time.

    Spot gold pauses every weekday at 17:00 New York time (US daylight saving). For each hypothesis we convert
    the first missing minute of every 30-120 minute weekday gap to New York time and score the share that lands
    exactly on 17:00. Returns (best hypothesis, scores).
    """
    ts = local["local_ts"]
    step = ts.diff()
    is_break = (step > pd.Timedelta(minutes=30)) & (step < pd.Timedelta(minutes=120))
    break_start = (ts - step)[is_break] + pd.Timedelta(minutes=1)
    if len(break_start) < 50:
        raise ValueError("not enough daily breaks to infer the HistData timezone")
    scores = {}
    for hypothesis in TIMEZONE_HYPOTHESES:
        ny = histdata_local_to_utc(break_start, hypothesis).dt.tz_convert("America/New_York")
        scores[hypothesis] = round(float(((ny.dt.hour == 17) & (ny.dt.minute == 0)).mean()), 4)
    return max(scores, key=lambda h: scores[h]), scores


def histdata_to_bars(local: pd.DataFrame, hypothesis: str) -> tuple[pd.DataFrame, int]:
    """Convert to canonical UTC bars. Returns (bars, rows dropped because their local time is undefined)."""
    utc = histdata_local_to_utc(local["local_ts"], hypothesis)
    keep = utc.notna().to_numpy()
    bars = pd.DataFrame(
        {
            "ts": utc[keep].reset_index(drop=True),
            **{
                c: local.loc[keep, c].astype("float64").reset_index(drop=True)
                for c in ("open", "high", "low", "close")
            },
            "volume": np.zeros(int(keep.sum())),
        }
    )
    bars["source"] = "histdata"
    bars["symbol"] = "XAUUSD"
    return bars, int((~keep).sum())


# --- Binance USD-M funding exports ---------------------------------------------------------------


def fetch_funding_exports() -> GithubFetch:
    mapping = {
        raw_url((repo, commit), rel): _local(f"funding/{key}.csv")
        for key, (repo, commit, rel) in FUNDING_REPOS.items()
    }
    return _fetch(mapping, workers=3)


def parse_funding_export(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    raw_ts = frame["fundingTime"]
    if pd.api.types.is_numeric_dtype(raw_ts):
        ts = pd.to_datetime(raw_ts.astype("int64"), unit=detect_epoch_unit(raw_ts), utc=True)
    else:
        ts = pd.to_datetime(raw_ts, utc=True)
    out = pd.DataFrame(
        {
            "ts": ts.dt.round("1min"),
            "rate": frame["fundingRate"].astype("float64"),
            "period_hours": 8.0,
        }
    )
    out["source"] = "binance_futures_funding_gh"
    out["symbol"] = "BTCUSDT"
    return out.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


@dataclass(frozen=True)
class FundingVerification:
    reference: str
    overlap_rows: int
    mismatches: int
    max_abs_diff: float


def verify_funding(primary: pd.DataFrame, others: dict[str, pd.DataFrame]) -> list[FundingVerification]:
    """Compare the primary funding export with independent exports on their overlapping timestamps."""
    out = []
    for name, other in others.items():
        merged = primary.merge(other, on="ts", suffixes=("", "_ref"))
        diff = (merged["rate"] - merged["rate_ref"]).abs()
        out.append(
            FundingVerification(
                name,
                len(merged),
                int((diff > 1e-12).sum()),
                float(diff.max() if len(diff) else 0.0),
            )
        )
    return out
