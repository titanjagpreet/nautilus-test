"""``make data``: download → normalise → store → validate → resample → cross-check.

Each dataset has an ordered list of sources. A source whose host is unreachable is recorded as ``blocked``
and the next one is tried; nothing is ever synthesised to fill a hole. Every attempt is written to
``data/source_log.json`` and summarised at the top of ``data/quality_report.md``.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab import config
from strategy_lab.data import storage
from strategy_lab.data.resample import resample_bars
from strategy_lab.data.schema import TIMEFRAMES
from strategy_lab.data.sources import binance, dukascopy, lighter
from strategy_lab.data.sources import github_datasets as gh
from strategy_lab.data.sources.http import SourceUnavailableError, probe
from strategy_lab.data.validate import QualityReport, build_report, normalise_bars, render_report

log = logging.getLogger(__name__)

# Datasets with market closures (gaps classified as weekend / daily break / holiday, not errors).
CLOSURE_MARKETS = {"XAUUSD", "XAU-PERP"}


@dataclass
class Attempt:
    dataset: str
    source: str
    status: str  # ok | blocked | failed | skipped
    detail: str


@dataclass
class StoredDataset:
    source: str
    symbol: str
    label: str
    duplicates_removed: int
    timestamp_units: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class PipelineState:
    attempts: list[Attempt] = field(default_factory=list)
    stored: list[StoredDataset] = field(default_factory=list)


def _period_end(last_full_month: pd.Period) -> pd.Timestamp:
    """Exclusive end of the last full month, in UTC."""
    return (last_full_month + 1).to_timestamp().tz_localize("UTC")


def _store_bars(
    state: PipelineState,
    frames: list[pd.DataFrame],
    label: str,
    end: pd.Timestamp,
    units: dict[str, int],
    notes: list[str],
) -> None:
    raw = pd.concat(frames, ignore_index=True)
    raw = raw[raw["ts"] < end]
    bars, dups = normalise_bars(raw)
    storage.write_bars(bars)
    source, symbol = str(bars["source"].iloc[0]), str(bars["symbol"].iloc[0])
    state.stored.append(StoredDataset(source, symbol, label, dups, units, notes))


def _store_funding(frame: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    frame = frame[frame["ts"] < end].sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    storage.write_funding(frame)
    return frame


def _try(state: PipelineState, dataset: str, source: str, fn: Callable[[], str]) -> bool:
    try:
        detail = fn()
    except SourceUnavailableError as exc:
        state.attempts.append(Attempt(dataset, source, "blocked", str(exc)[:300]))
        log.warning("%s via %s: blocked (%s)", dataset, source, exc)
        return False
    except Exception as exc:  # a broken source must not stop the other datasets
        state.attempts.append(Attempt(dataset, source, "failed", f"{type(exc).__name__}: {exc}"[:300]))
        log.exception("%s via %s failed", dataset, source)
        return False
    state.attempts.append(Attempt(dataset, source, "ok", detail))
    return True


def _require_host(url: str) -> None:
    reason = probe(url)
    if reason is not None:
        raise SourceUnavailableError(f"{url}: {reason}")


# --- individual dataset jobs ----------------------------------------------------------------------


def _binance_klines(state: PipelineState, source: str, end: pd.Timestamp) -> str:
    _require_host(binance.BASE_URL)
    result = binance.fetch_klines(source)
    label = "BTCUSDT 1m — Binance " + ("USD-M futures" if "futures" in source else "spot")
    notes = [f"{result.checksum_verified} monthly zips verified against Binance .CHECKSUM (SHA-256)"]
    if result.files_missing:
        notes.append(f"{len(result.files_missing)} monthly files not published (404)")
    _store_bars(state, result.frames, label, end, result.units, notes)
    return f"{result.files_ok} files, checksums verified: {result.checksum_verified}"


def _binance_funding(end: pd.Timestamp) -> str:
    _require_host(binance.BASE_URL)
    result = binance.fetch_funding()
    frame = _store_funding(pd.concat(result.frames, ignore_index=True), end)
    return f"{len(frame)} funding rows, {result.checksum_verified} zips checksum-verified"


def _github_binance_spot(state: PipelineState, last: pd.Period, end: pd.Timestamp) -> str:
    fetched = gh.fetch_binance_spot(last)
    if fetched.missing:
        raise RuntimeError(f"missing files: {fetched.missing[:3]}")
    frames, units = [], {}
    for path in sorted(fetched.files.values()):
        bars, unit = gh.parse_binance_spot_csv(path)
        frames.append(bars)
        units[unit] = units.get(unit, 0) + 1
    notes = [
        f"Third-party GitHub republication of data.binance.vision, pinned commit {gh.BINANCE_SPOT_REPO[1][:12]}; "
        "Binance .CHECKSUM files are on the blocked host, so integrity is checked by the Bitstamp cross-check",
        "Zero-volume flat minutes are Binance's own convention (published by Binance) and are kept",
    ]
    _store_bars(state, frames, "BTCUSDT 1m — Binance spot (GitHub republication)", end, units, notes)
    return f"{len(fetched.files)} monthly files (SHA-256 recorded in data/raw/github/manifest.json)"


def _github_funding(end: pd.Timestamp) -> str:
    fetched = gh.fetch_funding_exports()
    by_name = {
        key: gh.parse_funding_export(fetched.files[gh.raw_url((repo, commit), rel)])
        for key, (repo, commit, rel) in gh.FUNDING_REPOS.items()
    }
    primary = _store_funding(by_name.pop("vivekwar"), end)
    checks = gh.verify_funding(primary, by_name)
    _write_json("funding_verification.json", [asdict(c) for c in checks])
    summary = "; ".join(f"vs {c.reference}: {c.overlap_rows} rows, {c.mismatches} mismatches" for c in checks)
    if any(c.mismatches for c in checks):
        raise RuntimeError(f"funding exports disagree: {summary}")
    return f"{len(primary)} rows ({primary['ts'].min():%Y-%m-%d} → {primary['ts'].max():%Y-%m-%d}); {summary}"


def _bitstamp(state: PipelineState, end: pd.Timestamp) -> str:
    fetched = gh.fetch_bitstamp()
    price_files = (gh.BITSTAMP_FILES["historical"], gh.BITSTAMP_FILES["updates"])
    paths = [fetched.files[gh.raw_url(gh.BITSTAMP_REPO, rel)] for rel in price_files]
    bars, dropped, unit = gh.parse_bitstamp(sorted(paths))
    notes = [
        f"{dropped:,} flat zero-volume minutes dropped: the publisher fills missing minutes with flat candles "
        "and they carry no observed trade (genuine no-trade minutes are indistinguishable, so all are dropped)",
        f"pinned commit {gh.BITSTAMP_REPO[1][:12]}",
    ]
    _store_bars(state, [bars], "BTCUSD 1m — Bitstamp (GitHub)", end, {unit: len(paths)}, notes)
    return f"{len(paths)} files; {dropped:,} filler minutes dropped"


def _histdata(state: PipelineState) -> str:
    fetched = gh.fetch_histdata_xau()
    if fetched.missing:
        raise RuntimeError(f"missing files: {fetched.missing[:3]}")
    local = gh.read_histdata_local(list(fetched.files.values()))
    hypothesis, scores = gh.histdata_timezone(local)
    bars, dropped = gh.histdata_to_bars(local, hypothesis)
    notes = [
        f"BID quotes only (no ask, no volume — volume column is 0). Clock convention detected: {hypothesis} "
        f"(share of daily breaks landing on 17:00 New York per hypothesis: {scores})",
        f"{dropped} rows dropped because their local time does not exist in the detected timezone",
    ]
    end = bars["ts"].max() + pd.Timedelta(minutes=1)
    _store_bars(state, [bars], "XAUUSD 1m — HistData bid (GitHub)", end, {"local clock": len(fetched.files)}, notes)
    return f"{len(fetched.files)} files, timezone {hypothesis}"


def _dukascopy(state: PipelineState, last: pd.Period, end: pd.Timestamp) -> str:
    _require_host("https://jetta.dukascopy.com/")
    bars = dukascopy.fetch_xau(last)
    notes = ["mid = (bid + ask) / 2 per OHLC; spread = ask_close − bid_close"]
    _store_bars(state, [bars], "XAUUSD 1m — Dukascopy mid", end, {"ms": 2}, notes)
    return f"{len(bars):,} mid bars"


def _lighter(state: PipelineState, base: str, end: pd.Timestamp) -> str:
    _require_host(lighter.BASE_URL)
    spec = lighter.parse_market_spec(lighter.order_book_details(), base)
    bars = lighter.fetch_candles(spec, end)
    funding = lighter.fetch_fundings(spec, end)
    notes = [f"market_id {spec.market_id}; listing-limited history"]
    if base == "XAU":
        notes.append("Lighter XAU perp is priced from an oracle of spot gold; history starts at listing")
    _store_bars(state, [bars], f"{base}-PERP 1m — Lighter", end, {"ms": 1}, notes)
    _store_funding(funding, end)
    return f"{len(bars):,} candles, {len(funding):,} hourly funding rows"


def _kaggle() -> str:
    has_token = Path.home().joinpath(".kaggle", "kaggle.json").exists() or (
        os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")
    )
    if not has_token:
        raise SourceUnavailableError("no Kaggle API token configured — skipped (Bitstamp data comes from GitHub)")
    raise SourceUnavailableError("kaggle.com is not reachable from this environment")


# --- validation, resampling, cross-checks -------------------------------------------------------


def _write_json(name: str, payload: object) -> None:
    path = config.data_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def validate_all(state: PipelineState) -> list[QualityReport]:
    reports = []
    for ds in state.stored:
        bars = storage.read_bars(ds.source, ds.symbol)
        reports.append(
            build_report(
                f"{ds.label} (`source={ds.source}`, `symbol={ds.symbol}`)",
                bars,
                ds.duplicates_removed,
                market_closures=ds.symbol in CLOSURE_MARKETS,
                timestamp_units=ds.timestamp_units,
                notes=ds.notes,
            )
        )
    return reports


def resample_all(state: PipelineState) -> dict[str, int]:
    counts = {}
    for ds in state.stored:
        bars = storage.read_bars(ds.source, ds.symbol)
        for tf in TIMEFRAMES:
            if tf == "1m":
                continue
            out = resample_bars(bars, tf)
            storage.write_resampled(out, tf)
            counts[f"{ds.source}/{ds.symbol}/{tf}"] = len(out)
    return counts


@dataclass(frozen=True)
class CrossCheck:
    left: str
    right: str
    overlap_minutes: int
    first: str
    last: str
    close_correlation: float
    return_correlation: float
    median_abs_diff_bps: float
    p99_abs_diff_bps: float
    median_diff_bps_by_year: dict[str, float]
    worst_minutes: list[dict[str, object]]


def cross_check(left: tuple[str, str], right: tuple[str, str]) -> CrossCheck:
    """Compare 1m closes of two datasets on their common minutes."""
    a = storage.read_bars(*left)[["ts", "close"]]
    b = storage.read_bars(*right)[["ts", "close"]]
    m = a.merge(b, on="ts", suffixes=("_l", "_r")).sort_values("ts").reset_index(drop=True)
    diff_bps = (m["close_l"] / m["close_r"] - 1.0) * 1e4
    consecutive = m["ts"].diff() == pd.Timedelta(minutes=1)
    ret_l = np.log(m["close_l"]).diff()[consecutive]
    ret_r = np.log(m["close_r"]).diff()[consecutive]
    worst = m.assign(diff_bps=diff_bps).reindex(diff_bps.abs().sort_values(ascending=False).index[:10])
    by_year = diff_bps.groupby(m["ts"].dt.year).median().round(2)
    return CrossCheck(
        left=f"{left[0]}/{left[1]}",
        right=f"{right[0]}/{right[1]}",
        overlap_minutes=len(m),
        first=f"{m['ts'].iloc[0]:%Y-%m-%d %H:%M}",
        last=f"{m['ts'].iloc[-1]:%Y-%m-%d %H:%M}",
        close_correlation=round(float(m["close_l"].corr(m["close_r"])), 6),
        return_correlation=round(float(ret_l.corr(ret_r)), 4),
        median_abs_diff_bps=round(float(diff_bps.abs().median()), 3),
        p99_abs_diff_bps=round(float(diff_bps.abs().quantile(0.99)), 3),
        median_diff_bps_by_year={str(k): float(v) for k, v in by_year.items()},
        worst_minutes=[
            {"ts": f"{r.ts:%Y-%m-%d %H:%M}", "left": r.close_l, "right": r.close_r, "diff_bps": round(r.diff_bps, 1)}
            for r in worst.itertuples()
        ],
    )


CROSS_CHECK_PAIRS = [
    # (left, right): requested pairs first; they only run when both datasets exist.
    (("binance_futures", "BTCUSDT"), ("lighter", "BTC-PERP")),
    (("dukascopy", "XAUUSD"), ("lighter", "XAU-PERP")),
    (("binance_spot", "BTCUSDT"), ("bitstamp", "BTCUSD")),
    (("binance_spot_gh", "BTCUSDT"), ("bitstamp", "BTCUSD")),
    (("binance_futures", "BTCUSDT"), ("binance_spot", "BTCUSDT")),
]


def cross_check_all() -> tuple[list[CrossCheck], list[str]]:
    available = set(storage.list_datasets())
    done, skipped = [], []
    for left, right in CROSS_CHECK_PAIRS:
        if left in available and right in available:
            done.append(cross_check(left, right))
        else:
            missing = [f"{s}/{y}" for s, y in (left, right) if (s, y) not in available]
            skipped.append(f"{left[0]}/{left[1]} vs {right[0]}/{right[1]}: not run, missing {', '.join(missing)}")
    return done, skipped


def render_cross_checks(checks: list[CrossCheck], skipped: list[str]) -> str:
    lines = ["## Cross-source checks", ""]
    for c in checks:
        lines += [
            f"### {c.left} vs {c.right}",
            "",
            f"- Overlap: {c.overlap_minutes:,} common minutes, {c.first} → {c.last} UTC",
            f"- Correlation of closes: {c.close_correlation}; of 1m log returns: {c.return_correlation}",
            f"- |close difference|: median {c.median_abs_diff_bps} bps, 99th percentile {c.p99_abs_diff_bps} bps",
            "- Median signed difference by year (bps, left vs right): "
            + ", ".join(f"{y}: {v:+.2f}" for y, v in c.median_diff_bps_by_year.items()),
            "",
            "| worst minute (UTC) | left close | right close | diff bps |",
            "|---|---|---|---|",
        ]
        lines += [f"| {w['ts']} | {w['left']:,.2f} | {w['right']:,.2f} | {w['diff_bps']:+.1f} |" for w in c.worst_minutes]
        lines.append("")
    lines += [f"- {s}" for s in skipped]
    return "\n".join(lines) + "\n"


def render_attempts(attempts: list[Attempt]) -> str:
    lines = ["## Source attempts (in fallback order)", "", "| dataset | source | status | detail |", "|---|---|---|---|"]
    for a in attempts:
        lines.append(f"| {a.dataset} | {a.source} | **{a.status}** | {a.detail.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def run(today: pd.Timestamp | None = None) -> str:
    """Run the whole pipeline; returns the markdown quality report (also written to data/quality_report.md)."""
    now = today or pd.Timestamp.now(tz="UTC")
    last = binance.last_full_month(now)
    end = _period_end(last)
    state = PipelineState()

    btc = "BTC 1m (long history)"
    _try(state, btc, "binance_futures (data.binance.vision)", lambda: _binance_klines(state, "binance_futures", end))
    if not _try(state, btc, "binance_spot (data.binance.vision)", lambda: _binance_klines(state, "binance_spot", end)):
        _try(state, btc, "binance_spot_gh (GitHub republication)", lambda: _github_binance_spot(state, last, end))
    _try(state, "BTC 1m (Kaggle Bitstamp)", "kaggle", _kaggle)
    _try(state, "BTC 1m (second exchange)", "bitstamp (GitHub)", lambda: _bitstamp(state, end))

    fund = "BTCUSDT funding (8h)"
    if not _try(state, fund, "binance_futures fundingRate (data.binance.vision)", lambda: _binance_funding(end)):
        _try(state, fund, "binance_futures_funding_gh (GitHub API export)", lambda: _github_funding(end))

    for base in ("BTC", "XAU"):
        _try(state, f"{base}-PERP 1m + hourly funding", "lighter (mainnet REST)", lambda b=base: _lighter(state, b, end))

    xau = "XAU 1m (long history)"
    if not _try(state, xau, "dukascopy (dukascopy-node)", lambda: _dukascopy(state, last, end)):
        _try(state, xau, "histdata (GitHub re-uploads)", lambda: _histdata(state))

    _write_json("source_log.json", [asdict(a) for a in state.attempts])
    _write_json("datasets.json", [asdict(d) for d in state.stored])

    reports = validate_all(state)
    resampled = resample_all(state)
    _write_json("resampled_counts.json", resampled)
    checks, skipped = cross_check_all()
    _write_json("crosscheck.json", [asdict(c) for c in checks])

    report = "\n".join(
        [
            "# Data quality report",
            "",
            f"Generated {now:%Y-%m-%d %H:%M} UTC by `make data`. Last full month: {last}.",
            "",
            render_attempts(state.attempts),
            *[render_report(r) for r in reports],
            render_cross_checks(checks, skipped),
        ]
    )
    (config.reports_dir() / "quality_report.md").write_text(report)
    return report
