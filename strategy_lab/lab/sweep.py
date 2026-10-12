"""Parameter sweeps on either engine, in one process or across CPU cores.

Each worker loads the market data once (and, for the fast engine, prepares bars and caches indicator arrays
across runs), then evaluates grid points. ``workers=1`` runs inline — that is the "single core" measurement.
"""

from __future__ import annotations

import itertools
import multiprocessing as mp
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pandas as pd

from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.fast import runner as fast
from strategy_lab.engines.inputs import MarketData, load_market
from strategy_lab.engines.results import BacktestResult
from strategy_lab.lab.metrics import compute
from strategy_lab.spec.params import with_params
from strategy_lab.spec.schema import StrategySpec

Point = dict[str, float]


def grid(axes: Mapping[str, Sequence[float]]) -> list[Point]:
    names = list(axes)
    return [dict(zip(names, values, strict=True)) for values in itertools.product(*(axes[n] for n in names))]


def row(point: Point, result: BacktestResult) -> dict[str, Any]:
    return {**point, **compute(result).as_dict(), "wall_seconds": result.wall_seconds}


class _Worker:
    """Per-process state: market data (and the fast engine's prepared arrays) loaded once."""

    def __init__(self, spec_json: str, engine: str, start: pd.Timestamp, end: pd.Timestamp, source: str | None,
                 market: MarketData | None = None) -> None:  # fmt: skip
        self.spec = StrategySpec.model_validate_json(spec_json)
        self.engine, self.start, self.end = engine, start, end
        symbol = self.spec.market.symbol
        self.market = market or load_market(symbol, start, end, contract_spec(symbol).price_decimals, source)
        self.prepared = fast.prepare(self.spec, self.market) if engine == "fast" else None

    def run(self, point: Point) -> dict[str, Any]:
        spec = with_params(self.spec, point)
        if self.prepared is not None:
            result = fast.run_prepared(self.prepared, spec, start=self.start, end=self.end)
        else:
            from strategy_lab.engines.nautilus import spec_runner  # noqa: PLC0415 - keep fast workers light

            result = spec_runner.run_spec(spec, self.start, self.end, market=self.market)
        return row(point, result)


_WORKER: _Worker | None = None


def _init(spec_json: str, engine: str, start: pd.Timestamp, end: pd.Timestamp, source: str | None) -> None:
    global _WORKER  # noqa: PLW0603 - one worker object per process is the point of a process pool initializer
    _WORKER = _Worker(spec_json, engine, start, end, source)


def _run(point: Point) -> dict[str, Any]:
    assert _WORKER is not None
    return _WORKER.run(point)


def run_grid(
    spec: StrategySpec,
    points: list[Point],
    start: pd.Timestamp,
    end: pd.Timestamp,
    engine: str = "fast",
    workers: int = 1,
    source: str | None = None,
    market: MarketData | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Evaluate every point; returns one row of metrics per point (in input order)."""
    if engine not in ("fast", "nautilus"):
        raise ValueError(f"unknown engine {engine!r}")
    rows: list[dict[str, Any]] = []
    if workers <= 1:
        worker = _Worker(spec.model_dump_json(), engine, start, end, source, market)
        for i, point in enumerate(points):
            rows.append(worker.run(point))
            if progress:
                progress(i + 1, len(points))
        return pd.DataFrame(rows)
    ctx = mp.get_context("spawn")  # fresh interpreters: no inherited Nautilus/Numba state
    with ProcessPoolExecutor(workers, mp_context=ctx, initializer=_init,
                             initargs=(spec.model_dump_json(), engine, start, end, source)) as pool:  # fmt: skip
        for i, result in enumerate(pool.map(_run, points, chunksize=max(1, len(points) // (workers * 8)))):
            rows.append(result)
            if progress:
                progress(i + 1, len(points))
    return pd.DataFrame(rows)
