"""Source parser tests. All inputs are tiny synthetic rows written here in each source's documented format."""

from __future__ import annotations

import gzip
from pathlib import Path

import pandas as pd
import pytest

from strategy_lab.data.sources import binance, lighter
from strategy_lab.data.sources import github_datasets as gh
from strategy_lab.data.validate import find_gaps

T0_MS = 1_704_067_200_000  # 2024-01-01 00:00:00 UTC


def test_epoch_unit_detection() -> None:
    assert binance.detect_epoch_unit(pd.Series([1_704_067_200])) == "s"
    assert binance.detect_epoch_unit(pd.Series([T0_MS])) == "ms"
    assert binance.detect_epoch_unit(pd.Series([T0_MS * 1000])) == "us"
    with pytest.raises(ValueError, match="cannot infer"):
        binance.detect_epoch_unit(pd.Series([123456]))


def test_binance_kline_ms_without_header() -> None:
    raw = f"{T0_MS},100.0,101.0,99.0,100.5,12.5,{T0_MS + 59_999},1,2,3,4,0\n".encode()
    bars, unit = binance.parse_kline_csv(raw, "binance_spot", "BTCUSDT")
    assert unit == "ms"
    assert bars["ts"].iloc[0] == pd.Timestamp("2024-01-01", tz="UTC")
    assert bars[["open", "high", "low", "close", "volume"]].iloc[0].tolist() == [100.0, 101.0, 99.0, 100.5, 12.5]


def test_binance_kline_microseconds_with_header() -> None:
    """Spot files from 2025-01-01 use microseconds; some files carry a header row."""
    us = 1_735_689_600_000_000  # 2025-01-01 00:00 UTC in microseconds
    header = "open_time,open,high,low,close,volume,close_time,quote_volume,count,tbv,tbqv,ignore\n"
    raw = (header + f"{us},4.1507,4.1587,4.1506,4.1554,539.23,{us + 59_999_999},1,13,1,1,0\n").encode()
    bars, unit = binance.parse_kline_csv(raw, "binance_spot", "BTCUSDT")
    assert unit == "us"
    assert bars["ts"].iloc[0] == pd.Timestamp("2025-01-01", tz="UTC")


def test_binance_funding_csv() -> None:
    raw = f"calc_time,funding_interval_hours,last_funding_rate\n{T0_MS + 3},8,0.00010000\n".encode()
    funding = binance.parse_funding_csv(raw, "binance_futures", "BTCUSDT")
    assert funding["ts"].iloc[0] == pd.Timestamp("2024-01-01", tz="UTC")  # snapped from +3 ms
    assert funding["rate"].iloc[0] == pytest.approx(1e-4)
    assert funding["period_hours"].iloc[0] == 8.0


def test_github_funding_exports_both_timestamp_styles(tmp_path: Path) -> None:
    text = tmp_path / "text.csv"
    text.write_text("symbol,fundingTime,fundingRate,markPrice\nBTCUSDT,2024-01-01 08:00:00.000,0.0001,\n")
    numeric = tmp_path / "numeric.csv"
    numeric.write_text(f"symbol,fundingTime,fundingRate,markPrice\nBTCUSDT,{T0_MS + 8 * 3_600_000},0.0001,\n")
    a, b = gh.parse_funding_export(text), gh.parse_funding_export(numeric)
    assert a["ts"].iloc[0] == b["ts"].iloc[0] == pd.Timestamp("2024-01-01 08:00", tz="UTC")
    (check,) = gh.verify_funding(a, {"numeric": b})
    assert (check.overlap_rows, check.mismatches) == (1, 0)


def test_bitstamp_flat_zero_volume_rows_are_dropped(tmp_path: Path) -> None:
    path = tmp_path / "bitstamp.csv.gz"
    rows = "timestamp,open,high,low,close,volume\n1704067200,1,2,0.5,1.5,3\n1704067260,1.5,1.5,1.5,1.5,0\n"
    path.write_bytes(gzip.compress(rows.encode()))
    bars, dropped, unit = gh.parse_bitstamp([path])
    assert (len(bars), dropped, unit) == (1, 1, "s")


@pytest.mark.parametrize(
    ("local", "hypothesis", "utc"),
    [
        # 12 March 2024: US already on daylight time, EU not yet.
        ("2024-03-12 16:00", "UTC-5+EU_DST", "2024-03-12 21:00"),
        ("2024-03-12 16:00", "America/New_York", "2024-03-12 20:00"),
        ("2024-03-12 16:00", "EST", "2024-03-12 21:00"),
        # July: both on daylight time.
        ("2024-07-10 16:00", "UTC-5+EU_DST", "2024-07-10 20:00"),
        ("2024-07-10 16:00", "EST", "2024-07-10 21:00"),
    ],
)
def test_histdata_clock_hypotheses(local: str, hypothesis: str, utc: str) -> None:
    converted = gh.histdata_local_to_utc(pd.Series(pd.to_datetime([local])), hypothesis)
    assert converted.iloc[0] == pd.Timestamp(utc, tz="UTC")


def test_us_holiday_early_close_is_a_closure() -> None:
    # Martin Luther King Jr. Day 2024: CME metals close early (12:00-18:00 New York, i.e. 17:00-23:00 UTC).
    ts = pd.Series(pd.to_datetime(["2024-01-15 16:59", "2024-01-15 23:00"], utc=True))
    (gap,) = find_gaps(ts, market_closures=True)
    assert gap.kind == "holiday"


def test_lighter_candle_and_funding_pages() -> None:
    """Shapes from the lighter-python SDK docs (CandlestickApi.md)."""
    candles = lighter.parse_candles(
        [{"r": "1m", "c": [{"t": T0_MS, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 3.0, "V": 4.5, "i": 7}]}],
        "BTC-PERP",
    )
    assert candles["ts"].iloc[0] == pd.Timestamp("2024-01-01", tz="UTC")
    assert candles["close"].iloc[0] == 1.5
    fundings = lighter.parse_fundings(
        [{"fundings": [{"timestamp": 1704067200, "value": "1", "rate": "0.0001", "direction": "short"}]}],
        "BTC-PERP",
    )
    assert fundings["rate"].iloc[0] == pytest.approx(-1e-4)  # direction "short" = shorts pay
    assert fundings["period_hours"].iloc[0] == 1.0


def test_lighter_market_spec_lookup() -> None:
    details = [
        {"symbol": "ETH", "market_id": 0, "price_decimals": 2, "size_decimals": 4, "min_base_amount": "0.01"},
        {"symbol": "BTC", "market_id": 1, "price_decimals": 1, "size_decimals": 5, "min_base_amount": "0.0002",
         "maker_fee": "0", "taker_fee": "0", "created_at": 1735689600},
    ]  # fmt: skip
    spec = lighter.parse_market_spec(details, "BTC")
    assert (spec.market_id, spec.price_decimals, spec.size_decimals) == (1, 1, 5)
    assert spec.created_at_ms == 1_735_689_600_000
    with pytest.raises(KeyError):
        lighter.parse_market_spec(details, "XAU")
