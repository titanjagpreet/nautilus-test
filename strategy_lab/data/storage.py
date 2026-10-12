"""Parquet storage partitioned by source/symbol/year, with DuckDB views on top.

Layout (Hive-style, so DuckDB and pyarrow read the partition columns back automatically)::

    data/bars/source=binance_futures/symbol=BTCUSDT/year=2024/part-0.parquet
    data/funding/source=binance_futures/symbol=BTCUSDT/year=2024/part-0.parquet
    data/resampled/tf=15m/source=.../symbol=.../year=.../part-0.parquet
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from strategy_lab import config
from strategy_lab.data.schema import check_bars, check_funding


def _partition_dir(root: Path, source: str, symbol: str) -> Path:
    return root / f"source={source}" / f"symbol={symbol}"


def _write_partitioned(df: pd.DataFrame, root: Path, source: str, symbol: str) -> list[Path]:
    """Replace every year partition of (source, symbol) with ``df``; returns written files."""
    target = _partition_dir(root, source, symbol)
    if target.exists():
        shutil.rmtree(target)
    written: list[Path] = []
    body = df.drop(columns=["source", "symbol"]).sort_values("ts")
    for year, part in body.groupby(body["ts"].dt.year, sort=True):
        path = target / f"year={year}" / "part-0.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(part.reset_index(drop=True), preserve_index=False)
        pq.write_table(table, path, compression="zstd")
        written.append(path)
    return written


def write_bars(df: pd.DataFrame, root: Path | None = None) -> list[Path]:
    check_bars(df)
    (source,), (symbol,) = df["source"].unique(), df["symbol"].unique()
    return _write_partitioned(df, root or config.bars_dir(), str(source), str(symbol))


def write_funding(df: pd.DataFrame) -> list[Path]:
    check_funding(df)
    (source,), (symbol,) = df["source"].unique(), df["symbol"].unique()
    return _write_partitioned(df, config.funding_dir(), str(source), str(symbol))


def write_resampled(df: pd.DataFrame, timeframe: str) -> list[Path]:
    (source,), (symbol,) = df["source"].unique(), df["symbol"].unique()
    root = config.resampled_dir() / f"tf={timeframe}"
    return _write_partitioned(df, root, str(source), str(symbol))


def _read(
    root: Path, source: str, symbol: str, start: pd.Timestamp | None, end: pd.Timestamp | None
) -> pd.DataFrame:
    target = _partition_dir(root, source, symbol)
    if not target.exists():
        raise FileNotFoundError(f"no stored data for source={source} symbol={symbol} under {root}")
    files = sorted(target.glob("year=*/part-0.parquet"))
    if start is not None:
        files = [f for f in files if int(f.parent.name.split("=")[1]) >= start.year]
    if end is not None:
        files = [f for f in files if int(f.parent.name.split("=")[1]) <= end.year]
    frames = [pq.read_table(f).to_pandas() for f in files]
    if not frames:
        raise FileNotFoundError(f"no partitions in range for source={source} symbol={symbol}")
    df = pd.concat(frames, ignore_index=True)
    if start is not None:
        df = df[df["ts"] >= start]
    if end is not None:
        df = df[df["ts"] < end]
    df = df.reset_index(drop=True)
    df["source"] = source
    df["symbol"] = symbol
    return df


def read_bars(
    source: str,
    symbol: str,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    timeframe: str = "1m",
) -> pd.DataFrame:
    """Read canonical bars ``[start, end)`` (bar open times) for one source/symbol."""
    root = config.bars_dir() if timeframe == "1m" else config.resampled_dir() / f"tf={timeframe}"
    return _read(root, source, symbol, start, end)


def read_funding(
    source: str, symbol: str, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None
) -> pd.DataFrame:
    return _read(config.funding_dir(), source, symbol, start, end)


def list_datasets(root: Path | None = None) -> list[tuple[str, str]]:
    """(source, symbol) pairs stored under ``root`` (default: 1m bars)."""
    base = root or config.bars_dir()
    if not base.exists():
        return []
    pairs = []
    for src in sorted(base.glob("source=*")):
        for sym in sorted(src.glob("symbol=*")):
            pairs.append((src.name.split("=", 1)[1], sym.name.split("=", 1)[1]))
    return pairs


def duckdb_connection() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with views ``bars_1m``, ``funding`` and ``bars_<tf>`` over the Parquet store."""
    con = duckdb.connect()
    views = {"bars_1m": config.bars_dir(), "funding": config.funding_dir()}
    resampled = config.resampled_dir()
    if resampled.exists():
        for tf_dir in sorted(resampled.glob("tf=*")):
            views[f"bars_{tf_dir.name.split('=', 1)[1]}"] = tf_dir
    for name, root in views.items():
        if any(root.glob("source=*/symbol=*/year=*/*.parquet")):
            pattern = (root / "source=*" / "symbol=*" / "year=*" / "*.parquet").as_posix()
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{pattern}', hive_partitioning = true)")
    return con
