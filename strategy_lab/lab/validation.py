"""Out-of-sample test, walk-forward analysis, parameter heat-map and Monte Carlo resampling.

* **Out-of-sample:** tune on the first 70% of the period (grid search), then run the tuned parameters on the
  last 30% — data the tuning never saw.
* **Walk-forward:** 6 months in-sample / 2 months out-of-sample, rolled forward by 2 months; each window is
  tuned on its in-sample part and traded on its out-of-sample part. The out-of-sample pieces are chained into
  one equity curve (each piece compounds from where the previous one ended).
* **Heat-map:** the objective over a 2-parameter grid on the whole period; *stability* of the best cell is the
  mean of its (up to 8) neighbours relative to it — a plateau scores near 1, an isolated spike near 0.
* **Monte Carlo:** 1,000 bootstrap resamples of the trades' returns (with replacement, compounded); 5th / 50th /
  95th percentiles of the final return and of the maximum drawdown.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from strategy_lab.engines.results import BacktestResult
from strategy_lab.lab.evaluator import Evaluator, Point, Window
from strategy_lab.lab.metrics import compute
from strategy_lab.lab.optimize import best_point, grid_search

Progress = Callable[[int, int], None]
IS_FRACTION = 0.7
WF_IN_MONTHS, WF_OUT_MONTHS = 6, 2


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


# --- out-of-sample ---------------------------------------------------------------------------------------


@dataclass
class OutOfSample:
    in_sample: Window
    out_sample: Window
    params: Point  # tuned on the in-sample part
    original: Point
    is_metrics: dict[str, Any]  # tuned parameters, in-sample
    oos_metrics: dict[str, Any]  # tuned parameters, out-of-sample
    oos_original_metrics: dict[str, Any]  # the spec's own parameters, out-of-sample
    equity: pd.Series  # out-of-sample, tuned parameters
    tuned: bool  # False when no in-sample run had enough trades (the spec's own parameters are used)

    @property
    def retention(self) -> float:
        """Out-of-sample Sharpe as a share of the in-sample Sharpe (≤ 0 when it does not carry over)."""
        is_sharpe = self.is_metrics.get("sharpe") or 0.0
        return (self.oos_metrics.get("sharpe") or 0.0) / is_sharpe if is_sharpe > 0 else 0.0


def out_of_sample(
    evaluator: Evaluator, window: Window, axes: Mapping[str, Sequence[float]], progress: Progress | None = None
) -> OutOfSample:
    in_sample, out_sample = window.split(IS_FRACTION)
    original = evaluator.current_params(list(axes))
    rows = grid_search(evaluator, in_sample, axes, progress) if axes else pd.DataFrame()
    best = best_point(rows, list(axes)) if axes else None
    params = best if best is not None else original
    result = evaluator.run(out_sample, params)
    return OutOfSample(
        in_sample=in_sample,
        out_sample=out_sample,
        params=params,
        original=original,
        is_metrics=compute(evaluator.run(in_sample, params)).as_dict(),
        oos_metrics=compute(result).as_dict(),
        oos_original_metrics=compute(evaluator.run(out_sample, original)).as_dict(),
        equity=result.equity,
        tuned=best is not None,
    )


# --- walk-forward ----------------------------------------------------------------------------------------


@dataclass
class WalkForwardWindow:
    in_sample: Window
    out_sample: Window
    params: Point
    is_metrics: dict[str, Any]
    oos_metrics: dict[str, Any]


@dataclass
class WalkForward:
    windows: list[WalkForwardWindow]
    equity: pd.Series  # chained out-of-sample equity

    @property
    def profitable_share(self) -> float:
        if not self.windows:
            return 0.0
        profitable = sum(float(w.oos_metrics["net_pnl"] or 0.0) > 0 for w in self.windows)
        return profitable / len(self.windows)

    @property
    def efficiency(self) -> float:
        """Mean out-of-sample Sharpe / mean in-sample Sharpe of the tuned parameters (0 if in-sample ≤ 0)."""
        if not self.windows:
            return 0.0
        is_mean = float(np.mean([w.is_metrics["sharpe"] or 0.0 for w in self.windows]))
        oos_mean = float(np.mean([w.oos_metrics["sharpe"] or 0.0 for w in self.windows]))
        return oos_mean / is_mean if is_mean > 0 else 0.0

    @property
    def total_return_pct(self) -> float:
        return float((self.equity.iloc[-1] / self.equity.iloc[0] - 1) * 100) if len(self.equity) else 0.0

    def param_drift(self) -> dict[str, float]:
        """Coefficient of variation of each tuned parameter across windows (0 = always the same value)."""
        if not self.windows:
            return {}
        out = {}
        for name in self.windows[0].params:
            values = np.array([w.params[name] for w in self.windows])
            mean = float(np.mean(np.abs(values)))
            out[name] = float(np.std(values) / mean) if mean > 0 else 0.0
        return out


def walk_forward_windows(window: Window) -> list[tuple[Window, Window]]:
    out: list[tuple[Window, Window]] = []
    start = window.start
    while True:
        cut = start + pd.DateOffset(months=WF_IN_MONTHS)
        stop = cut + pd.DateOffset(months=WF_OUT_MONTHS)
        if stop > window.end:
            return out
        out.append((Window(start, cut), Window(cut, stop)))
        start += pd.DateOffset(months=WF_OUT_MONTHS)


def walk_forward(
    evaluator: Evaluator, window: Window, axes: Mapping[str, Sequence[float]], progress: Progress | None = None
) -> WalkForward:
    pairs = walk_forward_windows(window)
    original = evaluator.current_params(list(axes))
    windows: list[WalkForwardWindow] = []
    pieces: list[pd.Series] = []
    level = evaluator.starting_balance
    for k, (in_sample, out_sample) in enumerate(pairs):
        rows = grid_search(evaluator, in_sample, axes) if axes else pd.DataFrame()
        params = (best_point(rows, list(axes)) if axes else None) or original
        is_result = evaluator.run(in_sample, params)
        oos_result = evaluator.run(out_sample, params)
        windows.append(
            WalkForwardWindow(
                in_sample, out_sample, params, compute(is_result).as_dict(), compute(oos_result).as_dict()
            )
        )
        equity = oos_result.equity
        if len(equity):
            piece = equity / equity.iloc[0] * level
            pieces.append(piece if not pieces else piece.iloc[1:])
            level = float(piece.iloc[-1])
        if progress:
            progress(k + 1, len(pairs))
    chained = pd.concat(pieces) if pieces else pd.Series(dtype=float)
    return WalkForward(windows, chained)


# --- heat-map --------------------------------------------------------------------------------------------


@dataclass
class Heatmap:
    x: str
    y: str | None
    x_values: list[float]
    y_values: list[float]
    objective: list[list[float | None]]  # [row = y index][column = x index]; None = too few trades
    net_return_pct: list[list[float | None]]
    trades: list[list[int]]
    best: tuple[int, int] | None  # (row, column)
    current: tuple[int, int]
    stability: float  # neighbours of the best cell relative to it, 0..1

    @property
    def current_rank(self) -> float:
        """Share of usable cells whose objective is below the current parameters' cell (0..1)."""
        values = [v for row in self.objective for v in row if v is not None]
        mine = self.objective[self.current[0]][self.current[1]]
        if mine is None or not values:
            return 0.0
        return sum(v < mine for v in values) / len(values)


def stability_at(matrix: np.ndarray, row: int, col: int) -> float:
    best = matrix[row, col]
    if not (math.isfinite(best) and best > 0):
        return 0.0
    rows, cols = matrix.shape
    neighbours = [
        matrix[r, c]
        for r in range(row - 1, row + 2)
        for c in range(col - 1, col + 2)
        if (r, c) != (row, col) and 0 <= r < rows and 0 <= c < cols
    ]
    if not neighbours:
        return 0.0
    values = [max(v, 0.0) if math.isfinite(v) else 0.0 for v in neighbours]
    return float(min(1.0, sum(values) / len(values) / best))


def heatmap(
    evaluator: Evaluator, window: Window, axes: Mapping[str, Sequence[float]], progress: Progress | None = None
) -> Heatmap:
    names = list(axes)
    if not 1 <= len(names) <= 2:
        raise ValueError("a heat-map needs one or two parameters")
    x, y = names[0], (names[1] if len(names) == 2 else None)
    x_values = list(axes[x])
    y_values = list(axes[y]) if y else [0.0]
    rows = grid_search(evaluator, window, axes, progress)
    shape = (len(y_values), len(x_values))
    objective = np.full(shape, -math.inf)
    net = np.full(shape, math.nan)
    trades = np.zeros(shape, dtype=int)
    for _, row in rows.iterrows():
        i = y_values.index(float(row[y])) if y else 0
        j = x_values.index(float(row[x]))
        objective[i, j] = float(row["objective"])
        net[i, j] = float(row["net_return_pct"])
        trades[i, j] = int(row["trades"])
    current_point = evaluator.current_params(names)
    current = (
        int(np.argmin(np.abs(np.array(y_values) - current_point[y]))) if y else 0,
        int(np.argmin(np.abs(np.array(x_values) - current_point[x]))),
    )
    best = None
    stability = 0.0
    if np.isfinite(objective).any():
        r, c = np.unravel_index(int(np.argmax(objective)), shape)
        best = (int(r), int(c))
        stability = stability_at(objective, *best)
    return Heatmap(
        x=x,
        y=y,
        x_values=x_values,
        y_values=y_values,
        objective=[[_finite(v) for v in row] for row in objective],
        net_return_pct=[[_finite(v) for v in row] for row in net],
        trades=trades.tolist(),
        best=best,
        current=current,
        stability=stability,
    )


# --- Monte Carlo -----------------------------------------------------------------------------------------


@dataclass
class MonteCarlo:
    samples: int
    trades: int
    final_return_pct: dict[str, float] = field(default_factory=dict)  # p5 / p50 / p95
    max_drawdown_pct: dict[str, float] = field(default_factory=dict)
    prob_loss: float = math.nan
    final_returns: list[float] = field(default_factory=list)  # every sample, for the histogram


def trade_returns(result: BacktestResult) -> np.ndarray:
    """Each trade's net P&L as a fraction of the equity before it (trades in order)."""
    pnl = result.trades["pnl_net"].to_numpy(dtype=np.float64) if len(result.trades) else np.empty(0)
    before = result.starting_balance + np.r_[0.0, np.cumsum(pnl)[:-1]]
    return np.asarray(pnl / before, dtype=np.float64)


def monte_carlo(result: BacktestResult, samples: int = 1000, seed: int = 7) -> MonteCarlo:
    returns = trade_returns(result)
    if len(returns) < 2:
        return MonteCarlo(samples, len(returns))
    rng = np.random.default_rng(seed)
    drawn = rng.choice(returns, size=(samples, len(returns)), replace=True)
    paths = np.cumprod(1.0 + drawn, axis=1)
    paths = np.hstack([np.ones((samples, 1)), paths])
    final = (paths[:, -1] - 1.0) * 100.0
    drawdown = ((paths / np.maximum.accumulate(paths, axis=1)) - 1.0).min(axis=1) * 100.0

    def pct(values: np.ndarray) -> dict[str, float]:
        return {f"p{q}": float(np.percentile(values, q)) for q in (5, 50, 95)}

    return MonteCarlo(
        samples, len(returns), pct(final), pct(drawdown), float((final < 0).mean()), [float(v) for v in final]
    )
