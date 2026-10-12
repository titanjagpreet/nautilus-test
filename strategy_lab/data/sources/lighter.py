"""Lighter (zkLighter) public REST API — perp 1m candles, hourly funding, market specs. Read-only.

Plain HTTPS (httpx) instead of ``lighter-sdk``: the SDK pins ``urllib3<2.1`` and pulls in transaction-signing
libraries this backtest-only project must not need. Endpoint and field names are taken from the SDK source
(elliottech/lighter-python v1.1.6, docs/CandlestickApi.md, docs/OrderApi.md):

* ``GET /api/v1/orderBookDetails?filter=perp`` → ``order_book_details[]`` with ``symbol, market_id,
  size_decimals, price_decimals, min_base_amount, maker_fee, taker_fee, created_at, ...`` (strings for decimals).
* ``GET /api/v1/candles?market_id&resolution=1m&start_timestamp&end_timestamp&count_back`` →
  ``{"r": "1m", "c": [{"t", "o", "h", "l", "c", "v", "V", "i"}]}``, at most 500 candles per call, ``t`` in ms.
  CCXT's Lighter integration sends start/end in **milliseconds** with ``count_back=0``; we do the same.
* ``GET /api/v1/fundings?market_id&resolution=1h&start_timestamp&end_timestamp&count_back`` →
  ``{"fundings": [{"timestamp", "value", "rate", "direction"}]}``, at most 750 per call.

**Unverified here** (the host is blocked from the build sandbox): funding ``rate`` is assumed to be a
fraction per hourly period and ``direction`` the side that pays. Raw JSON pages are kept under
``data/raw/lighter/`` so these assumptions can be checked against Lighter's UI.

Rate limit: the standard tier is reported as 60 requests/minute, so calls are spaced ≥ 1.05 s apart and
HTTP 429 backs off (``http.request_with_retries``).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from strategy_lab import config
from strategy_lab.data.sources.http import client, request_with_retries

BASE_URL = "https://mainnet.zklighter.elliot.ai"
CANDLES_PER_CALL = 500
FUNDINGS_PER_CALL = 750
MIN_SECONDS_BETWEEN_CALLS = 1.05


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    market_id: int
    price_decimals: int
    size_decimals: int
    min_base_amount: float
    maker_fee: float
    taker_fee: float
    created_at_ms: int | None


def _raw_dir() -> Path:
    return config.raw_dir() / "lighter"


class _Throttle:
    def __init__(self) -> None:
        self._last = 0.0

    def wait(self) -> None:
        delay = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


def order_book_details() -> list[dict[str, Any]]:
    """Fetch perp market metadata and keep the raw JSON (used by instrument specs in the engines)."""
    with client() as http:
        payload = request_with_retries(http, f"{BASE_URL}/api/v1/orderBookDetails", {"filter": "perp"}).json()
    path = _raw_dir() / "order_book_details.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return list(payload.get("order_book_details", []))


def parse_market_spec(details: list[dict[str, Any]], symbol: str) -> MarketSpec:
    for row in details:
        if str(row.get("symbol", "")).upper() == symbol.upper():
            return MarketSpec(
                symbol=symbol,
                market_id=int(row["market_id"]),
                price_decimals=int(row["price_decimals"]),
                size_decimals=int(row["size_decimals"]),
                min_base_amount=float(row["min_base_amount"]),
                maker_fee=float(row.get("maker_fee", 0) or 0),
                taker_fee=float(row.get("taker_fee", 0) or 0),
                created_at_ms=_epoch_ms(row.get("created_at")),
            )
    raise KeyError(f"symbol {symbol!r} not found in Lighter orderBookDetails")


def _epoch_ms(value: object) -> int | None:
    """``created_at`` may be epoch seconds, epoch ms or an ISO string; the unit is not documented."""
    if value in (None, ""):
        return None
    text = str(value)
    if text.isdigit():
        number = int(text)
        return number * 1000 if number < 10**11 else number
    return int(pd.Timestamp(text).value // 1_000_000)


def parse_candles(pages: list[dict[str, Any]], symbol: str) -> pd.DataFrame:
    rows = [c for page in pages for c in page.get("c", [])]
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "source", "symbol"])
    frame = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "ts": pd.to_datetime(frame["t"].astype("int64"), unit="ms", utc=True),
            "open": frame["o"].astype("float64"),
            "high": frame["h"].astype("float64"),
            "low": frame["l"].astype("float64"),
            "close": frame["c"].astype("float64"),
            "volume": frame["v"].astype("float64"),
        }
    )
    out["source"] = "lighter"
    out["symbol"] = symbol
    return out


def parse_fundings(pages: list[dict[str, Any]], symbol: str) -> pd.DataFrame:
    rows = [f for page in pages for f in page.get("fundings", [])]
    frame = pd.DataFrame(rows, columns=["timestamp", "value", "rate", "direction"])
    raw_ts = frame["timestamp"].astype("int64")
    unit = "ms" if len(raw_ts) and raw_ts.max() > 10**11 else "s"
    sign = frame["direction"].astype(str).str.lower().map({"long": 1.0, "short": -1.0}).fillna(1.0)
    out = pd.DataFrame(
        {
            "ts": pd.to_datetime(raw_ts, unit=unit, utc=True),
            "rate": frame["rate"].astype("float64") * sign,
            "period_hours": 1.0,
        }
    )
    out["source"] = "lighter"
    out["symbol"] = symbol
    return out


def _paged(
    endpoint: str,
    market_id: int,
    resolution: str,
    step_ms: int,
    floor_ms: int,
    end_ms: int,
    key: str,
) -> list[dict[str, Any]]:
    """Walk backwards from ``end_ms`` in ``step_ms`` windows; each raw page is cached on disk."""
    cache = _raw_dir() / endpoint / f"market={market_id}"
    cache.mkdir(parents=True, exist_ok=True)
    throttle = _Throttle()
    pages: list[dict[str, Any]] = []
    window_end = end_ms
    with client() as http:
        while window_end > floor_ms:
            window_start = max(window_end - step_ms, floor_ms)
            page_path = cache / f"{window_start}_{window_end}.json"
            if page_path.exists():
                page = json.loads(page_path.read_text())
            else:
                throttle.wait()
                params = {
                    "market_id": market_id,
                    "resolution": resolution,
                    "start_timestamp": window_start,
                    "end_timestamp": window_end,
                    "count_back": 0,
                }
                page = request_with_retries(http, f"{BASE_URL}/api/v1/{endpoint}", params).json()
                page_path.write_text(json.dumps(page))
            pages.append(page)
            window_end = window_start
    return [p for p in pages if p.get(key)]


def fetch_candles(spec: MarketSpec, end: pd.Timestamp) -> pd.DataFrame:
    floor = spec.created_at_ms or int(pd.Timestamp("2024-01-01", tz="UTC").value // 1_000_000)
    pages = _paged(
        "candles", spec.market_id, "1m", CANDLES_PER_CALL * 60_000, floor, int(end.value // 1_000_000), "c"
    )
    return parse_candles(pages, f"{spec.symbol}-PERP")


def fetch_fundings(spec: MarketSpec, end: pd.Timestamp) -> pd.DataFrame:
    floor = spec.created_at_ms or int(pd.Timestamp("2024-01-01", tz="UTC").value // 1_000_000)
    pages = _paged(
        "fundings",
        spec.market_id,
        "1h",
        FUNDINGS_PER_CALL * 3_600_000,
        floor,
        int(end.value // 1_000_000),
        "fundings",
    )
    return parse_fundings(pages, f"{spec.symbol}-PERP")
