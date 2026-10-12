"""Data-quality check tests on small synthetic frames generated here (never used as results)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategy_lab.data.validate import build_report, find_gaps, normalise_bars, render_report


def _frame(ts: pd.DatetimeIndex, close: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": ts,
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.ones(len(ts)),
            "source": "synthetic_test",
            "symbol": "TEST",
        }
    )


def test_duplicates_are_dropped_and_counted() -> None:
    ts = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:01", "2024-01-01 00:01"], utc=True)
    df, dups = normalise_bars(_frame(pd.DatetimeIndex(ts), np.array([1.0, 2.0, 3.0])))
    assert dups == 1
    assert df["close"].tolist() == [1.0, 2.0]


def test_gaps_over_five_minutes_are_listed() -> None:
    ts = pd.Series(pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:05", "2024-01-01 00:20"], utc=True))
    gaps = find_gaps(ts, market_closures=False)
    # 00:00 -> 00:05 is a 4-minute hole (not > 5 min); 00:05 -> 00:20 misses 14 minutes.
    assert [(g.start.minute, g.end.minute, g.minutes, g.kind) for g in gaps] == [(6, 20, 14, "data_gap")]


def test_gold_closures_are_classified() -> None:
    cases = {
        ("2024-03-01 20:59", "2024-03-03 22:00"): "weekend",  # Friday close -> Sunday reopen
        ("2024-03-04 20:59", "2024-03-04 22:00"): "daily_break",
        ("2024-03-05 10:00", "2024-03-05 11:30"): "data_gap",  # unexplained weekday hole
        ("2024-12-24 18:00", "2024-12-26 01:00"): "holiday",  # Christmas
    }
    for (last_bar, next_bar), expected in cases.items():
        ts = pd.Series(pd.to_datetime([last_bar, next_bar], utc=True))
        (gap,) = find_gaps(ts, market_closures=True)
        assert gap.kind == expected, (last_bar, next_bar)


def test_outlier_spike_is_flagged_not_removed() -> None:
    rng = np.random.default_rng(7)
    n = 3000
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.0005, n)))
    close[2500] *= 1.2  # a 20% one-minute spike
    ts = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    report = build_report("synthetic", _frame(ts, close), 0, market_closures=False)
    assert report.rows == n
    assert report.outliers["ts"].iloc[0] == ts[2500]
    assert "Outlier spikes" in render_report(report)


def test_ohlc_violations_are_counted() -> None:
    ts = pd.date_range("2024-01-01", periods=3, freq="1min", tz="UTC")
    df = _frame(ts, np.array([10.0, 11.0, 12.0]))
    df.loc[1, "high"] = 5.0  # below open/close and below low
    df.loc[2, "low"] = -1.0
    v = build_report("synthetic", df, 0, market_closures=False).ohlc_violations
    assert v["high_below_open_or_close"] == 1
    assert v["high_below_low"] == 1
    assert v["non_positive_price"] == 1
