"""Resampling tests on a hand-made example (synthetic data generated here, never results)."""

from __future__ import annotations

import pandas as pd
import pytest

from strategy_lab.data.resample import resample_bars


def _bars(rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["source"] = "synthetic_test"
    df["symbol"] = "TEST"
    return df


HAND_MADE = _bars(
    [
        # ts (bar open, UTC)       open   high   low    close  volume
        ("2024-01-01 00:00", 100.0, 101.0, 99.0, 100.5, 1.0),
        ("2024-01-01 00:01", 100.5, 103.0, 100.0, 102.0, 2.0),
        ("2024-01-01 00:02", 102.0, 102.5, 98.0, 99.0, 3.0),
        ("2024-01-01 00:03", 99.0, 99.5, 97.5, 98.0, 4.0),
        ("2024-01-01 00:04", 98.0, 100.0, 97.9, 99.9, 5.0),
        # 00:05-00:09 bin: only two minutes present (a gap) -> still one bar, n_minutes = 2
        ("2024-01-01 00:06", 99.9, 100.1, 99.8, 100.0, 6.0),
        ("2024-01-01 00:09", 100.0, 104.0, 100.0, 103.5, 7.0),
        # next UTC day
        ("2024-01-02 00:00", 103.5, 104.0, 103.0, 103.2, 8.0),
    ]
)


def test_5m_aggregation_matches_hand_computation() -> None:
    out = resample_bars(HAND_MADE, "5m")
    expected = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:05", "2024-01-02 00:00"], utc=True),
            "open": [100.0, 99.9, 103.5],
            "high": [103.0, 104.0, 104.0],
            "low": [97.5, 99.8, 103.0],
            "close": [99.9, 103.5, 103.2],
            "volume": [15.0, 13.0, 8.0],
            "n_minutes": [5, 2, 1],
        }
    )
    pd.testing.assert_frame_equal(out[expected.columns], expected, check_dtype=False)
    assert set(out["source"]) == {"synthetic_test"}


def test_daily_bars_are_anchored_to_utc_midnight() -> None:
    out = resample_bars(HAND_MADE, "1d")
    assert list(out["ts"]) == list(pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True))
    assert out["open"].tolist() == [100.0, 103.5]
    assert out["close"].tolist() == [103.5, 103.2]
    assert out["high"].tolist() == [104.0, 104.0]
    assert out["low"].tolist() == [97.5, 103.0]
    assert out["volume"].tolist() == [28.0, 8.0]


def test_4h_bins_start_at_utc_multiples_of_four_hours() -> None:
    late = _bars(
        [
            ("2024-03-05 03:59", 1.0, 1.0, 1.0, 1.0, 1.0),
            ("2024-03-05 04:00", 2.0, 2.0, 2.0, 2.0, 1.0),
        ]
    )
    out = resample_bars(late, "4h")
    assert list(out["ts"].dt.hour) == [0, 4]


def test_empty_bins_produce_no_rows() -> None:
    out = resample_bars(HAND_MADE, "1h")
    # 2024-01-01 00:00 and 2024-01-02 00:00 only; the 23 empty hours in between are not invented.
    assert len(out) == 2


def test_unknown_timeframe_rejected() -> None:
    with pytest.raises(ValueError, match="unknown timeframe"):
        resample_bars(HAND_MADE, "7m")
