"""Source parser tests and dataset selection. All inputs are tiny synthetic rows written here (labelled)."""

from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from strategy_lab.api import services
from strategy_lab.data import pipeline, storage
from strategy_lab.data.sources import binance, dukascopy, lighter
from strategy_lab.data.sources import github_datasets as gh
from strategy_lab.data.sources.http import SourceUnavailableError
from strategy_lab.data.validate import find_gaps
from strategy_lab.engines import inputs

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
    text.write_text(
        "symbol,fundingTime,fundingRate,markPrice\nBTCUSDT,2024-01-01 08:00:00.000,0.0001,\n", encoding="utf-8"
    )
    numeric = tmp_path / "numeric.csv"
    numeric.write_text(
        f"symbol,fundingTime,fundingRate,markPrice\nBTCUSDT,{T0_MS + 8 * 3_600_000},0.0001,\n", encoding="utf-8"
    )
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
        {
            "symbol": "BTC",
            "market_id": 1,
            "price_decimals": 1,
            "size_decimals": 5,
            "min_base_amount": "0.0002",
            "maker_fee": "0",
            "taker_fee": "0",
            "created_at": 1735689600,
        },
    ]
    spec = lighter.parse_market_spec(details, "BTC")
    assert (spec.market_id, spec.price_decimals, spec.size_decimals) == (1, 1, 5)
    assert spec.created_at_ms == 1_735_689_600_000
    with pytest.raises(KeyError):
        lighter.parse_market_spec(details, "XAU")


# --- which stored dataset backs a backtest window ------------------------------------------------------------


def _series(source: str, symbol: str, start: str, end: str, freq: str, **cols: float) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq=freq, tz="UTC")
    return pd.DataFrame({"ts": ts, **cols, "source": source, "symbol": symbol})


@pytest.fixture
def open_network_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC: what `make data` stores where every source works — a short Lighter history (from its listing)
    next to Binance's long one. Flat prices; only the date ranges matter here."""
    monkeypatch.setenv("STRATEGY_LAB_DATA_DIR", str(tmp_path))
    price = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0}
    storage.write_bars(_series("lighter", "BTC-PERP", "2026-01-01", "2026-02-28 23:59", "6h", **price))
    storage.write_bars(_series("binance_futures", "BTCUSDT", "2023-01-01", "2026-02-28 23:59", "6h", **price))
    storage.write_funding(
        _series("lighter", "BTC-PERP", "2026-01-01", "2026-02-28 23:00", "1h", rate=1e-5, period_hours=1.0)
    )
    storage.write_funding(
        _series("binance_futures", "BTCUSDT", "2023-01-01", "2025-12-31 16:00", "8h", rate=1e-4, period_hours=8.0)
    )


def ts(day: str) -> pd.Timestamp:
    return pd.Timestamp(day, tz="UTC")


@pytest.mark.usefixtures("open_network_store")
def test_the_preferred_source_is_used_only_where_it_covers_the_window() -> None:
    assert inputs.resolve_bar_source("BTC-PERP", ts("2026-01-05"), ts("2026-02-20")) == ("lighter", "BTC-PERP")
    assert inputs.resolve_bar_source("BTC-PERP", ts("2024-01-01"), ts("2025-01-01")) == (
        "binance_futures",
        "BTCUSDT",
    )
    with pytest.raises(
        ValueError,
        match=r"no stored BTC-PERP history covers 2022-01-01 → 2023-06-01; available: "
        r"lighter/BTC-PERP 2026-01-01 → 2026-02-28; binance_futures/BTCUSDT 2023-01-01 → 2026-02-28",
    ):
        inputs.resolve_bar_source("BTC-PERP", ts("2022-01-01"), ts("2023-06-01"))
    explicit = inputs.resolve_bar_source("BTC-PERP", ts("2024-01-01"), ts("2025-01-01"), "lighter/BTC-PERP")
    assert explicit == ("lighter", "BTC-PERP"), (
        "an explicit choice is honoured (and fails later if it has no bars)"
    )


@pytest.mark.usefixtures("open_network_store")
def test_funding_covers_the_window_or_is_labelled_partial() -> None:
    full = inputs.resolve_funding_source("BTC-PERP", ts("2024-01-01"), ts("2025-01-01"))
    assert full == (("binance_futures", "BTCUSDT"), "binance_futures/BTCUSDT")
    partial = inputs.resolve_funding_source("BTC-PERP", ts("2025-06-01"), ts("2026-02-15"))
    assert partial == (
        ("binance_futures", "BTCUSDT"),
        "binance_futures/BTCUSDT (partial: 2025-06-01 → 2025-12-31)",
    )
    assert inputs.resolve_funding_source("BTC-PERP", ts("2021-01-01"), ts("2022-01-01")) is None
    market = inputs.load_market("BTC-PERP", ts("2024-01-01"), ts("2025-01-01"), price_decimals=1)
    assert (market.source, market.funding_source) == ("binance_futures/BTCUSDT", "binance_futures/BTCUSDT")
    assert market.bars_1m["ts"].min() == ts("2024-01-01")
    assert len(market.funding) == 366 * 3


@pytest.mark.usefixtures("open_network_store")
def test_warm_up_history_never_switches_the_dataset() -> None:
    """Regression: the lab asked for its window minus the indicator warm-up, which reached before Lighter's (or
    Binance's) first bar, so the whole run silently moved to a less preferred dataset."""
    start, end = ts("2026-01-20"), ts("2026-02-20")
    market = inputs.load_market("BTC-PERP", start, end, price_decimals=1, history_from=ts("2025-06-01"))
    assert market.source == "lighter/BTC-PERP"
    assert market.bars_1m["ts"].min() == ts("2026-01-01"), "as much warm-up as the dataset has"
    assert market.funding["ts"].min() == ts("2026-01-01")


def utc(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=dt.UTC)


def source(name: str, first: str, last: str) -> dict[str, object]:
    return {"source": name, "first": utc(first), "last": utc(last)}


def test_default_window_takes_three_funded_years_from_the_preferred_source_that_has_them() -> None:
    bars = [
        source("lighter/BTC-PERP", "2026-01-01", "2026-09-30 23:59"),
        source("binance_futures/BTCUSDT", "2019-09-08 17:57", "2026-09-30 23:59"),
    ]
    funding = [
        source("lighter/BTC-PERP", "2026-01-01", "2026-10-12 09:00"),
        source("binance_futures/BTCUSDT", "2019-09-10 08:00", "2026-09-30 16:00"),
    ]
    assert services.default_window(bars, funding) == {
        "start": "2023-09-01",
        "end": "2026-09-01",
        "bars": "binance_futures/BTCUSDT",
        "funding": "binance_futures/BTCUSDT",
    }
    gold = [source("histdata/XAUUSD", "2021-01-03 23:00", "2026-05-29 20:58")]
    assert services.default_window(gold, []) == {
        "start": "2023-05-01",
        "end": "2026-05-01",
        "bars": "histdata/XAUUSD",
        "funding": None,
    }
    short = [source("lighter/BTC-PERP", "2025-03-15 12:00", "2026-09-30 23:59")]
    short_funding = [source("lighter/BTC-PERP", "2025-03-15 12:00", "2026-10-12 09:00")]
    assert services.default_window(short, short_funding) == {
        "start": "2025-04-01",
        "end": "2026-09-01",
        "bars": "lighter/BTC-PERP",
        "funding": "lighter/BTC-PERP",
    }, "without three years anywhere, the longest window"
    gold_with_lighter_funding = [source("lighter/XAU-PERP", "2026-02-01", "2026-10-12 09:00")]
    assert services.default_window(gold, gold_with_lighter_funding)["funding"] is None, (
        "three years beat full funding"
    )
    assert services.default_window([], []) is None


# --- an interrupted `make data` resumes cleanly ------------------------------------------------------------


def test_a_dataset_is_swapped_in_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC rows. A rewrite never leaves half a dataset; leftovers of an interrupted one stay invisible."""
    monkeypatch.setenv("STRATEGY_LAB_DATA_DIR", str(tmp_path))
    price = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0}
    storage.write_bars(_series("binance_futures", "BTCUSDT", "2024-06-01", "2025-06-01", "1D", **price))
    leftover = tmp_path / "bars" / ".staging" / "source=binance_futures" / "symbol=BTCUSDT" / "year=2019"
    leftover.mkdir(parents=True)  # what an interrupted write leaves behind
    (leftover / "part-0.parquet").write_bytes(b"truncated")
    storage.write_bars(_series("binance_futures", "BTCUSDT", "2025-01-01", "2025-03-01", "1D", **price))
    assert storage.list_datasets() == [("binance_futures", "BTCUSDT")]
    assert storage.time_ranges() == {("binance_futures", "BTCUSDT"): (ts("2025-01-01"), ts("2025-03-01"))}
    assert not (tmp_path / "bars" / ".staging").exists(), "nothing is left behind"


def test_a_corrupt_cached_lighter_page_is_fetched_again(tmp_path: Path) -> None:
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text('{"candlesticks": []}', encoding="utf-8")
    bad.write_text('{"candlesticks": [{"t": 1', encoding="utf-8")  # cut off mid-write
    assert lighter._cached(good) == {"candlesticks": []}
    assert lighter._cached(bad) is None
    assert lighter._cached(tmp_path / "missing.json") is None


def test_dukascopy_keeps_only_files_the_cli_finished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRATEGY_LAB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dukascopy.shutil, "which", lambda name: "C:/nodejs/npx.cmd")
    calls: list[list[str]] = []

    def cli(ok: bool) -> Callable[..., subprocess.CompletedProcess[str]]:
        def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            out = Path(cmd[cmd.index("-dir") + 1]) / (cmd[cmd.index("-fn") + 1] + ".csv")
            out.write_text("timestamp,open\n1,2\n" if ok else "timestamp,op", encoding="utf-8")
            banner = "-----\nInstrument: Gold vs US Dollar\n-----\n\nSomething went wrong:\n > network error\n"
            return subprocess.CompletedProcess(cmd, 0 if ok else 1, "", "" if ok else banner)

        return run

    start, end = ts("2020-01-01"), ts("2021-01-01")
    monkeypatch.setattr(dukascopy.subprocess, "run", cli(ok=False))
    with pytest.raises(SourceUnavailableError, match=r"2020: Something went wrong: > network error$"):
        dukascopy._run_cli("bid", start, end, "xauusd-m1-bid-2020")
    folder = tmp_path / "raw" / "dukascopy"
    assert not (folder / "xauusd-m1-bid-2020.csv").exists(), "a failed or interrupted run leaves no final file"
    monkeypatch.setattr(dukascopy.subprocess, "run", cli(ok=True))
    path = dukascopy._run_cli("bid", start, end, "xauusd-m1-bid-2020")
    assert path == folder / "xauusd-m1-bid-2020.csv"
    assert path.read_text(encoding="utf-8") == "timestamp,open\n1,2\n"
    assert sorted(p.name for p in folder.iterdir()) == ["xauusd-m1-bid-2020.csv"]
    assert calls[-1][0] == "C:/nodejs/npx.cmd", "npx is launched by its full path (npx.cmd on Windows)"
    assert dukascopy._run_cli("bid", start, end, "xauusd-m1-bid-2020") == path
    assert len(calls) == 2, "a finished file is reused, not downloaded again"


def test_a_multi_line_source_error_stays_one_table_row() -> None:
    attempt = pipeline.Attempt("XAU 1m", "dukascopy", "blocked", "failed:\n---\nInstrument: Gold | x\n")
    table = pipeline.render_attempts([attempt])
    assert table.splitlines()[-1] == "| XAU 1m | dukascopy | **blocked** | failed: --- Instrument: Gold / x |"


@pytest.mark.skipif(sys.platform == "win32", reason="the TZ variable sets the local time zone on POSIX only")
@pytest.mark.usefixtures("open_network_store")
def test_coverage_is_in_utc_whatever_the_machines_time_zone() -> None:
    """Regression: on a UTC+6 machine the coverage showed 2026-10-01 for data ending 2026-09-30 23:59 UTC."""
    script = (
        "import json; from strategy_lab.api import services; from strategy_lab.data import storage; "
        "first = services.coverage()['markets']['BTC-PERP']['bars'][0]; "
        "last = storage.time_ranges()[('lighter', 'BTC-PERP')][1]; "
        "print(json.dumps([first['first'], first['last'], str(last)]))"
    )
    for zone in ("Asia/Dhaka", "America/New_York"):
        out = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            env=os.environ | {"TZ": zone},
        )
        assert json.loads(out.stdout) == [
            "2026-01-01T00:00:00+00:00",
            "2026-02-28T18:00:00+00:00",
            "2026-02-28 18:00:00+00:00",
        ], zone
