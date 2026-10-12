"""Binance public data (https://data.binance.vision) — spot / USD-M futures 1m klines and funding rates.

URL patterns (from github.com/binance/binance-public-data README and its ``python/utility.py``)::

    data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2017-08.zip           (+ .zip.CHECKSUM)
    data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2019-09.zip
    data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2020-01.zip

Kline columns: open_time, open, high, low, close, volume, close_time, quote_volume, trades,
taker_buy_base, taker_buy_quote, ignore. Some files start with a header row. **Spot timestamps switched from
milliseconds to microseconds on 2025-01-01**, so the unit is detected per file from the magnitude, never assumed.

Every zip is verified against the SHA-256 in its ``.CHECKSUM`` file before it is parsed.
"""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pandas as pd

from strategy_lab import config
from strategy_lab.data.sources.http import (
    Download,
    NotFoundError,
    client,
    fetch_many,
    request_with_retries,
)

BASE_URL = "https://data.binance.vision/"
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]

MARKETS = {
    # source name -> (path prefix, first month with data)
    "binance_spot": ("data/spot/monthly/klines", "2017-08"),
    "binance_futures": ("data/futures/um/monthly/klines", "2019-09"),
}
FUNDING_PREFIX = "data/futures/um/monthly/fundingRate"
FUNDING_FIRST_MONTH = "2019-09"


def detect_epoch_unit(values: pd.Series) -> str:
    """Return 's', 'ms', 'us' or 'ns' from the magnitude of epoch integers (dates 2001..2286)."""
    sample = int(pd.to_numeric(values, errors="raise").abs().max())
    digits = len(str(sample))
    units = {10: "s", 13: "ms", 16: "us", 19: "ns"}
    if digits not in units:
        raise ValueError(f"cannot infer epoch unit from value {sample} ({digits} digits)")
    return units[digits]


def _has_header(first_line: str) -> bool:
    head = first_line.split(",", 1)[0].strip()
    return not head.lstrip("-").isdigit()


def parse_kline_csv(raw: bytes, source: str, symbol: str) -> tuple[pd.DataFrame, str]:
    """Parse one monthly kline CSV. Returns (canonical bars, detected timestamp unit)."""
    text = raw.decode("utf-8")
    first_line = text.split("\n", 1)[0]
    frame = pd.read_csv(
        io.StringIO(text),
        header=None,
        names=KLINE_COLUMNS,
        skiprows=1 if _has_header(first_line) else 0,
        usecols=range(6),
    )
    unit = detect_epoch_unit(frame["open_time"])
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(frame["open_time"].astype("int64"), unit=unit, utc=True),
            **{c: frame[c].astype("float64") for c in ("open", "high", "low", "close", "volume")},
        }
    )
    bars["source"] = source
    bars["symbol"] = symbol
    return bars, unit


def parse_funding_csv(raw: bytes, source: str, symbol: str) -> pd.DataFrame:
    """Parse a monthly fundingRate CSV (header: calc_time, funding_interval_hours, last_funding_rate)."""
    frame = pd.read_csv(io.BytesIO(raw))
    cols = {c.lower(): c for c in frame.columns}
    ts_col = cols.get("calc_time") or cols.get("fundingtime") or frame.columns[0]
    rate_col = cols.get("last_funding_rate") or cols.get("fundingrate") or frame.columns[-1]
    period_col = cols.get("funding_interval_hours")
    unit = detect_epoch_unit(frame[ts_col])
    out = pd.DataFrame(
        {
            # Binance stamps the settlement a few ms after the hour; snap to the funding time.
            "ts": pd.to_datetime(frame[ts_col].astype("int64"), unit=unit, utc=True).dt.round("1min"),
            "rate": frame[rate_col].astype("float64"),
            "period_hours": frame[period_col].astype("float64") if period_col else 8.0,
        }
    )
    out["source"] = source
    out["symbol"] = symbol
    return out


def _months(first: str, last: pd.Period) -> list[pd.Period]:
    return list(pd.period_range(pd.Period(first, "M"), last, freq="M"))


def last_full_month(today: pd.Timestamp | None = None) -> pd.Period:
    now = today or pd.Timestamp.now(tz="UTC")
    return pd.Period(now.tz_localize(None), "M") - 1


@dataclass
class FetchResult:
    files_ok: int = 0
    files_missing: list[str] = field(default_factory=list)
    checksum_verified: int = 0
    units: dict[str, int] = field(default_factory=dict)
    frames: list[pd.DataFrame] = field(default_factory=list)


def _raw_path(source: str, rel_url: str) -> Path:
    return config.raw_dir() / source / rel_url


def _fetch_checksums(rel_urls: list[str], workers: int) -> tuple[dict[str, str], list[str]]:
    """SHA-256 from each ``.CHECKSUM`` file ("<hex>  <name>"). Missing months come back in the second list."""

    def one(http: httpx.Client, rel: str) -> str | None:
        try:
            text = request_with_retries(http, BASE_URL + rel + ".CHECKSUM").text
        except NotFoundError:
            return None
        return text.split()[0].strip().lower()

    checksums: dict[str, str] = {}
    missing: list[str] = []
    with client() as http, ThreadPoolExecutor(max_workers=workers) as pool:
        for rel, digest in zip(rel_urls, pool.map(lambda r: one(http, r), rel_urls), strict=True):
            if digest is None:
                missing.append(rel)
            else:
                checksums[rel] = digest
    return checksums, missing


def _download_verified(rel_urls: list[str], source: str, workers: int) -> tuple[dict[str, Path], list[str]]:
    """Fetch checksums, then the zips (each verified). Raises if any present file fails verification."""
    checksums, missing = _fetch_checksums(rel_urls, workers)
    items = [Download(BASE_URL + rel, _raw_path(source, rel), checksums[rel]) for rel in checksums]
    results = fetch_many(items, workers=workers)
    paths: dict[str, Path] = {}
    for rel in checksums:
        outcome = results[BASE_URL + rel]
        if isinstance(outcome, Exception):
            raise outcome
        paths[rel] = outcome
    return paths, missing


def _read_zip_member(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        (name,) = archive.namelist()
        return archive.read(name)


def fetch_klines(source: str, symbol: str = "BTCUSDT", workers: int = 8) -> FetchResult:
    """Download, verify and parse every monthly 1m kline file from the first month to the last full month."""
    prefix, first = MARKETS[source]
    rels = [f"{prefix}/{symbol}/1m/{symbol}-1m-{m}.zip" for m in _months(first, last_full_month())]
    paths, missing = _download_verified(rels, source, workers)
    result = FetchResult(files_missing=missing)
    for rel in sorted(paths):
        bars, unit = parse_kline_csv(_read_zip_member(paths[rel]), source, symbol)
        result.frames.append(bars)
        result.units[unit] = result.units.get(unit, 0) + 1
        result.files_ok += 1
        result.checksum_verified += 1
    return result


def fetch_funding(symbol: str = "BTCUSDT", workers: int = 8) -> FetchResult:
    rels = [
        f"{FUNDING_PREFIX}/{symbol}/{symbol}-fundingRate-{m}.zip"
        for m in _months(FUNDING_FIRST_MONTH, last_full_month())
    ]
    paths, missing = _download_verified(rels, "binance_futures_funding", workers)
    result = FetchResult(files_missing=missing)
    for rel in sorted(paths):
        result.frames.append(parse_funding_csv(_read_zip_member(paths[rel]), "binance_futures", symbol))
        result.files_ok += 1
        result.checksum_verified += 1
    return result
