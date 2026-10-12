"""Data-quality checks for canonical 1m bars and the markdown quality report.

Nothing here modifies prices. ``normalise_bars`` only sorts and drops exact-timestamp duplicates (counted);
every other finding (gaps, OHLC inconsistencies, outlier spikes) is reported, never silently "fixed".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

import numpy as np
import pandas as pd
from pandas.tseries.holiday import GoodFriday, USFederalHolidayCalendar

from strategy_lab.data.schema import check_bars

GAP_THRESHOLD = pd.Timedelta(minutes=5)
OUTLIER_SIGMAS = 10.0
OUTLIER_WINDOW = 1440  # trailing 1-day window of 1m log returns for the sigma estimate


@dataclass(frozen=True)
class Gap:
    start: pd.Timestamp  # first missing minute
    end: pd.Timestamp  # first minute present again
    minutes: int
    kind: str  # "data_gap", or for markets with closures: "weekend", "daily_break", "holiday"


@dataclass
class QualityReport:
    dataset: str
    rows: int
    first: pd.Timestamp | None
    last: pd.Timestamp | None
    duplicates_removed: int
    completeness_pct: float
    gaps: list[Gap]
    ohlc_violations: dict[str, int]
    outliers: pd.DataFrame
    timestamp_units: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def data_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.kind == "data_gap"]

    @property
    def closure_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.kind != "data_gap"]


def normalise_bars(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Sort by time and drop duplicate timestamps (keeping the first). Returns (frame, duplicates)."""
    ordered = df.sort_values("ts", kind="stable")
    dup_mask = ordered["ts"].duplicated(keep="first")
    return ordered.loc[~dup_mask].reset_index(drop=True), int(dup_mask.sum())


@cache
def us_market_holidays(first_year: int, last_year: int) -> frozenset[pd.Timestamp]:
    """New York dates on which CME metals close or close early.

    US federal holidays except Columbus Day and Veterans Day (metals trade normally then), plus Good Friday,
    the day after Thanksgiving, Christmas Eve and New Year's Eve.
    """
    start, end = f"{first_year}-01-01", f"{last_year}-12-31"
    federal = USFederalHolidayCalendar()
    rules = [r for r in federal.rules if r.name not in {"Columbus Day", "Veterans Day"}]
    days = {d.normalize() for r in rules for d in r.dates(start, end)}
    days |= {d.normalize() for d in GoodFriday.dates(start, end)}
    thanksgiving = [r for r in federal.rules if r.name == "Thanksgiving Day"][0]
    days |= {(d + pd.Timedelta(days=1)).normalize() for d in thanksgiving.dates(start, end)}
    for year in range(first_year, last_year + 1):
        days |= {pd.Timestamp(f"{year}-12-24"), pd.Timestamp(f"{year}-12-31")}
    return frozenset(days)


def _classify_gold_gap(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Spot gold trades Sun 18:00 to Fri 17:00 New York time with a one-hour daily break at 17:00 New York."""
    duration = end - start
    # Weekend: the gap contains Saturday noon UTC.
    saturday_noon = start.normalize() + pd.Timedelta(days=(5 - start.weekday()) % 7, hours=12)
    if start <= saturday_noon < end:
        return "weekend"
    if duration <= pd.Timedelta(minutes=75) and start.hour in (20, 21, 22):
        return "daily_break"
    ny_start = start.tz_convert("America/New_York").tz_localize(None).normalize()
    ny_end = end.tz_convert("America/New_York").tz_localize(None).normalize()
    holidays = us_market_holidays(ny_start.year, ny_end.year)
    days = pd.date_range(ny_start, ny_end, freq="D")
    if duration <= pd.Timedelta(days=4) and any(d in holidays for d in days):
        return "holiday"
    return "data_gap"


def find_gaps(ts: pd.Series, market_closures: bool) -> list[Gap]:
    diffs = ts.diff()
    idx = np.flatnonzero((diffs > GAP_THRESHOLD).to_numpy())
    gaps = []
    for i in idx:
        start = ts.iloc[i - 1] + pd.Timedelta(minutes=1)
        end = ts.iloc[i]
        minutes = int((end - start) / pd.Timedelta(minutes=1))
        kind = _classify_gold_gap(start, end) if market_closures else "data_gap"
        gaps.append(Gap(start, end, minutes, kind))
    return gaps


def ohlc_violations(df: pd.DataFrame) -> dict[str, int]:
    o, h, lo, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    return {
        "high_below_open_or_close": int(np.sum(h < np.maximum(o, c))),
        "low_above_open_or_close": int(np.sum(lo > np.minimum(o, c))),
        "high_below_low": int(np.sum(h < lo)),
        "non_positive_price": int(np.sum((o <= 0) | (h <= 0) | (lo <= 0) | (c <= 0))),
        "negative_volume": int(np.sum(df["volume"].to_numpy() < 0)),
        "nan_values": int(df[["open", "high", "low", "close", "volume"]].isna().to_numpy().sum()),
    }


def find_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """1m close-to-close log returns beyond ``OUTLIER_SIGMAS`` trailing-day standard deviations."""
    close = df["close"].astype("float64")
    valid = close > 0
    logret = pd.Series(np.where(valid, np.log(close.where(valid)), np.nan)).diff()
    sigma = logret.rolling(OUTLIER_WINDOW, min_periods=60).std().shift(1)
    z = logret / sigma
    mask = (z.abs() > OUTLIER_SIGMAS).to_numpy()
    out = pd.DataFrame(
        {
            "ts": df["ts"].to_numpy()[mask],
            "close": close.to_numpy()[mask],
            "prev_close": close.shift(1).to_numpy()[mask],
            "log_return": logret.to_numpy()[mask],
            "sigmas": z.to_numpy()[mask],
        }
    )
    return out.sort_values("sigmas", key=np.abs, ascending=False).reset_index(drop=True)


def build_report(
    dataset: str,
    df: pd.DataFrame,
    duplicates_removed: int,
    market_closures: bool,
    timestamp_units: dict[str, int] | None = None,
    notes: list[str] | None = None,
) -> QualityReport:
    check_bars(df)
    if df.empty:
        return QualityReport(dataset, 0, None, None, duplicates_removed, 0.0, [], {}, find_outliers(df))
    first, last = df["ts"].iloc[0], df["ts"].iloc[-1]
    gaps = find_gaps(df["ts"], market_closures)
    expected = int((last - first) / pd.Timedelta(minutes=1)) + 1
    closed = sum(g.minutes for g in gaps if g.kind != "data_gap")
    completeness = 100.0 * len(df) / max(expected - closed, 1)
    return QualityReport(
        dataset=dataset,
        rows=len(df),
        first=first,
        last=last,
        duplicates_removed=duplicates_removed,
        completeness_pct=round(min(completeness, 100.0), 3),
        gaps=gaps,
        ohlc_violations=ohlc_violations(df),
        outliers=find_outliers(df),
        timestamp_units=timestamp_units or {},
        notes=notes or [],
    )


def render_report(report: QualityReport, max_rows: int = 15) -> str:
    r = report
    lines = [f"## {r.dataset}", ""]
    if r.rows == 0:
        lines += ["No rows stored.", ""]
        lines += [f"- {n}" for n in r.notes]
        return "\n".join(lines)
    lines += [
        f"- Rows: **{r.rows:,}** 1m bars, {r.first:%Y-%m-%d %H:%M} → {r.last:%Y-%m-%d %H:%M} UTC",
        f"- Completeness (excluding market closures): {r.completeness_pct:.3f}%",
        f"- Duplicate timestamps removed: {r.duplicates_removed:,}",
        f"- Timestamp units detected per source file: "
        + (", ".join(f"{u}: {n} files" for u, n in sorted(r.timestamp_units.items())) or "n/a"),
        f"- Data gaps > 5 min: **{len(r.data_gaps)}** ({sum(g.minutes for g in r.data_gaps):,} missing minutes)",
    ]
    if r.closure_gaps:
        kinds: dict[str, int] = {}
        for g in r.closure_gaps:
            kinds[g.kind] = kinds.get(g.kind, 0) + 1
        lines.append(
            "- Market-closure gaps (not errors): " + ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items()))
        )
    lines.append("- OHLC sanity: " + ", ".join(f"{k}={v}" for k, v in r.ohlc_violations.items()))
    lines.append(
        f"- Outlier spikes (|1m log return| > {OUTLIER_SIGMAS:g}σ of trailing day, flagged, kept): "
        f"**{len(r.outliers)}**"
    )
    lines += [f"- Note: {n}" for n in r.notes]
    if r.data_gaps:
        lines += [
            "",
            f"Largest data gaps (top {max_rows}):",
            "",
            "| start (UTC) | end (UTC) | missing minutes |",
            "|---|---|---|",
        ]
        for g in sorted(r.data_gaps, key=lambda g: g.minutes, reverse=True)[:max_rows]:
            lines.append(f"| {g.start:%Y-%m-%d %H:%M} | {g.end:%Y-%m-%d %H:%M} | {g.minutes:,} |")
    if not r.outliers.empty:
        lines += [
            "",
            f"Largest outlier spikes (top {max_rows}):",
            "",
            "| ts (UTC) | prev close | close | log return | σ |",
            "|---|---|---|---|---|",
        ]
        for row in r.outliers.head(max_rows).itertuples():
            lines.append(
                f"| {row.ts:%Y-%m-%d %H:%M} | {row.prev_close:,.2f} | {row.close:,.2f} | "
                f"{row.log_return:+.4f} | {row.sigmas:+.1f} |"
            )
    lines.append("")
    return "\n".join(lines)
