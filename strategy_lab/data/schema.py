"""Canonical bar and funding schemas.

Bars: one row per minute, ``ts`` is the **bar open time** in UTC. Engines convert to close-time stamps
themselves (Nautilus requires ``ts_event`` = close; see LEARNINGS.md §1).
"""

from __future__ import annotations

from typing import Final

import pandas as pd

BAR_COLUMNS: Final = ["ts", "open", "high", "low", "close", "volume", "source", "symbol"]
FUNDING_COLUMNS: Final = ["ts", "rate", "period_hours", "source", "symbol"]
PRICE_COLUMNS: Final = ["open", "high", "low", "close"]

TIMEFRAMES: Final[dict[str, pd.Timedelta]] = {
    "1m": pd.Timedelta(minutes=1),
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}


class SchemaError(ValueError):
    """A frame does not follow the canonical schema."""


def _check_columns(df: pd.DataFrame, required: list[str], kind: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(f"{kind} frame is missing columns {missing}")
    ts = df["ts"]
    if not isinstance(ts.dtype, pd.DatetimeTZDtype) or str(ts.dt.tz) != "UTC":
        raise SchemaError(f"{kind} 'ts' must be tz-aware UTC, got {ts.dtype}")


def check_bars(df: pd.DataFrame) -> None:
    _check_columns(df, BAR_COLUMNS, "bar")
    for col in [*PRICE_COLUMNS, "volume"]:
        if df[col].dtype != "float64":
            raise SchemaError(f"bar column {col!r} must be float64, got {df[col].dtype}")


def check_funding(df: pd.DataFrame) -> None:
    _check_columns(df, FUNDING_COLUMNS, "funding")
    if df["rate"].dtype != "float64":
        raise SchemaError(f"funding 'rate' must be float64, got {df['rate'].dtype}")


def empty_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.Series([], dtype="datetime64[ns, UTC]"),
            **{c: pd.Series([], dtype="float64") for c in [*PRICE_COLUMNS, "volume"]},
            "source": pd.Series([], dtype="string"),
            "symbol": pd.Series([], dtype="string"),
        }
    )
