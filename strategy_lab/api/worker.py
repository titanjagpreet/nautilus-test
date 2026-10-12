"""Background jobs, executed in a separate worker process: backtests on either engine, and lab runs.

The worker writes progress, results and errors to the store; the API process only enqueues and polls. Heavy
imports (NautilusTrader, the lab) happen here, never in the web process.
"""

from __future__ import annotations

import json
import math
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd

from strategy_lab.api.store import Store, now
from strategy_lab.data.resample import resample_bars
from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.inputs import MarketData, load_market
from strategy_lab.engines.results import BacktestResult
from strategy_lab.lab.metrics import compute
from strategy_lab.spec.schema import StrategySpec

MAX_POINTS = 4000  # equity/benchmark points sent to the browser
MAX_CANDLES = 3000
DISPLAY_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")


def to_json(data: Any) -> str:
    """JSON with NumPy scalars as Python numbers and non-finite floats as null (browsers reject NaN)."""
    return json.dumps(_clean(data))


def _clean(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _clean(v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [_clean(v) for v in data]
    if hasattr(data, "item") and not isinstance(data, str | bytes):
        data = data.item()  # NumPy scalar
    if isinstance(data, float) and not math.isfinite(data):
        return None
    return data


def engine_version(engine: str) -> str:
    if engine == "nautilus":
        return f"nautilus_trader {version('nautilus_trader')}"
    return f"strategy_lab fast engine {version('strategy-lab')} (numba {version('numba')})"


def _epoch(ts: pd.Timestamp) -> int:
    return int(ts.timestamp())


def _thin(series: pd.Series) -> list[list[float]]:
    if series.empty:
        return []
    step = max(1, math.ceil(len(series) / MAX_POINTS))
    sampled = series.iloc[::step]
    if sampled.index[-1] != series.index[-1]:
        sampled = pd.concat([sampled, series.iloc[-1:]])
    return [[_epoch(ts), round(float(v), 4)] for ts, v in zip(sampled.index, sampled.to_numpy(), strict=True)]


def candles(market: MarketData, base_timeframe: str, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
    """OHLC for the price chart at the finest timeframe (≥ the strategy's) that fits in MAX_CANDLES."""
    bars = market.bars_1m[(market.bars_1m["ts"] >= start) & (market.bars_1m["ts"] < end)]
    options = DISPLAY_TIMEFRAMES[DISPLAY_TIMEFRAMES.index(base_timeframe) :]
    span_minutes = (end - start) / pd.Timedelta(minutes=1)
    minutes = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    timeframe = next((tf for tf in options if span_minutes / minutes[tf] <= MAX_CANDLES), "1d")
    frame = resample_bars(bars, timeframe)
    columns = (frame["ts"], frame["open"], frame["high"], frame["low"], frame["close"])
    rows = [[_epoch(t), o, h, low, c] for t, o, h, low, c in zip(*columns, strict=True)]
    return {"timeframe": timeframe, "bars": rows}


def serialize_backtest(result: BacktestResult, market: MarketData, spec: StrategySpec) -> dict[str, Any]:
    trades = result.trades
    records = [
        {
            "side": t["side"],
            "quantity": float(t["quantity"]),
            "entry_time": _epoch(t["entry_time"]),
            "entry_price": float(t["entry_price"]),
            "exit_time": _epoch(t["exit_time"]),
            "exit_price": float(t["exit_price"]),
            "exit_reason": t["exit_reason"],
            "fees": round(float(t["fees"]), 6),
            "funding": round(float(t["funding"]), 6),
            "pnl_net": round(float(t["pnl_net"]), 6),
        }
        for t in trades.to_dict("records")
    ]
    closes = result.closes
    benchmark = closes / closes.iloc[0] * result.starting_balance if len(closes) else closes
    return {
        "equity": _thin(result.equity),
        "buy_hold": _thin(benchmark),
        "price": candles(market, spec.market.timeframe, result.start, result.end),
        "trades": records,
        "starting_balance": result.starting_balance,
    }


def _market(spec: StrategySpec, start: pd.Timestamp, end: pd.Timestamp, source: str | None) -> MarketData:
    symbol = spec.market.symbol
    return load_market(symbol, start, end, contract_spec(symbol).price_decimals, source)


def run_backtest(store: Store, job_id: int, request: dict[str, Any]) -> int:
    spec = StrategySpec.model_validate(request["spec"])
    start, end = pd.Timestamp(request["start"], tz="UTC"), pd.Timestamp(request["end"], tz="UTC")
    engine = request.get("engine", "fast")
    store.update_job(job_id, stage="loading data", progress=0.05)
    market = _market(spec, start, end, request.get("source"))
    store.update_job(job_id, stage=f"running ({engine})", progress=0.2)
    if engine == "nautilus":
        from strategy_lab.engines.nautilus import spec_runner  # noqa: PLC0415 - keep the web process light

        result = spec_runner.run_spec(spec, start, end, market=market)
    else:
        from strategy_lab.engines.fast import runner  # noqa: PLC0415

        result = runner.run_spec(spec, start, end, market=market)
    store.update_job(job_id, stage="saving", progress=0.9)
    return store.save_backtest(
        {
            "job_id": job_id,
            "spec_name": spec.meta.name,
            "market": spec.market.symbol,
            "engine": engine,
            "engine_version": engine_version(engine),
            "source": result.bars_source,
            "funding_source": result.funding_source,
            "start_ts": start.isoformat(),
            "end_ts": end.isoformat(),
            "spec_json": spec.model_dump_json(),
            "metrics_json": to_json(compute(result).as_dict()),
            "result_json": to_json(serialize_backtest(result, market, spec)),
            "wall_s": result.wall_seconds,
        }
    )


def run_lab_job(store: Store, job_id: int, request: dict[str, Any]) -> int:
    from strategy_lab.lab.robustness import run_lab  # noqa: PLC0415

    spec = StrategySpec.model_validate(request["spec"])
    start, end = pd.Timestamp(request["start"], tz="UTC"), pd.Timestamp(request["end"], tz="UTC")
    last_stage, last_fraction = [""], [-1.0]

    def progress(stage: str, fraction: float) -> None:
        if stage != last_stage[0] or fraction - last_fraction[0] >= 0.01:  # throttle database writes
            store.update_job(job_id, stage=stage, progress=round(fraction, 3))
            last_stage[0], last_fraction[0] = stage, fraction

    report = run_lab(
        spec,
        start,
        end,
        parameters=request.get("parameters") or None,
        objective=request.get("objective", "sharpe"),
        optuna_trials=int(request.get("optuna_trials", 0)),
        grid_points=int(request.get("grid_points", 9)),
        source=request.get("source"),
        progress=progress,
    )
    data = report.as_dict()
    return store.save_lab_report(
        {
            "job_id": job_id,
            "spec_name": spec.meta.name,
            "market": spec.market.symbol,
            "engine_version": engine_version("fast"),
            "start_ts": start.isoformat(),
            "end_ts": end.isoformat(),
            "score": data["score"],
            "spec_json": spec.model_dump_json(),
            "report_json": to_json(data),
        }
    )


def run_job(job_id: int, db_path: str) -> None:
    """Entry point in the worker process."""
    store = Store(Path(db_path))
    job = store.job(job_id)
    if job is None:
        return
    store.update_job(job_id, status="running", started=now(), stage="starting", progress=0.0)
    try:
        if job["kind"] == "backtest":
            result_id = run_backtest(store, job_id, job["request"])
        elif job["kind"] == "lab":
            result_id = run_lab_job(store, job_id, job["request"])
        else:
            raise ValueError(f"unknown job kind {job['kind']!r}")
    except Exception as exc:  # every failure is reported on the job, never lost
        store.update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}", finished=now())
        return
    store.update_job(job_id, status="done", stage="done", progress=1.0, result_id=result_id, finished=now())
