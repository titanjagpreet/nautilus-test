"""Parameter search on a window: exhaustive grids (heat-maps, out-of-sample and walk-forward tuning) and Optuna
(TPE) over up to four parameters. Higher objective is better; runs with too few trades score -inf."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
import optuna
import pandas as pd

from strategy_lab.lab.evaluator import Evaluator, Point, Window
from strategy_lab.lab.sweep import grid
from strategy_lab.spec.params import TunableParam, tunable_parameters

Progress = Callable[[int, int], None]
MAX_OPTUNA_PARAMS = 4


def axis_values(param: TunableParam, n: int = 9, spread: float = 0.5) -> list[float]:
    """``n`` values from (1 - spread) to (1 + spread) times the current value, within the parameter's bounds."""
    centre = param.value
    if centre == 0:
        low, high = -1.0, 1.0
    else:
        low, high = sorted((centre * (1 - spread), centre * (1 + spread)))
    low, high = max(low, param.low), min(high, param.high)
    values = np.linspace(low, high, n)
    if param.integer:
        unique = sorted({round(float(v)) for v in values})
        return [float(v) for v in unique]
    return [float(round(v, 6)) for v in values]


def default_axes(spec: Any, names: Sequence[str] | None = None, n: int = 9) -> dict[str, list[float]]:
    """Grid axes for the named parameters (default: the first two indicator parameters, else the first two)."""
    params = {p.name: p for p in tunable_parameters(spec)}
    if names is None:
        indicator_params = [p.name for p in params.values() if p.path[0] == "indicators"]
        names = (indicator_params or list(params))[:2]
    unknown = [n_ for n_ in names if n_ not in params]
    if unknown:
        raise KeyError(f"unknown parameter(s) {unknown}; available: {sorted(params)}")
    return {name: axis_values(params[name], n) for name in names}


def grid_search(
    evaluator: Evaluator, window: Window, axes: Mapping[str, Sequence[float]], progress: Progress | None = None
) -> pd.DataFrame:
    points = grid(axes)
    rows = []
    for i, point in enumerate(points):
        rows.append(evaluator.evaluate(window, point))
        if progress:
            progress(i + 1, len(points))
    return pd.DataFrame(rows)


def best_point(rows: pd.DataFrame, names: Sequence[str]) -> Point | None:
    """Parameters of the row with the highest objective; None when no row is usable."""
    if rows.empty or not np.isfinite(rows["objective"].to_numpy(dtype=float)).any():
        return None
    row = rows.iloc[int(np.argmax(rows["objective"].to_numpy(dtype=float)))]
    return {name: float(row[name]) for name in names}


def optuna_search(
    evaluator: Evaluator,
    window: Window,
    axes: Mapping[str, Sequence[float]],
    n_trials: int = 60,
    seed: int = 7,
    progress: Progress | None = None,
) -> pd.DataFrame:
    """TPE search inside each axis' [min, max] (integers stay integers). Same rows as ``grid_search``."""
    if not 1 <= len(axes) <= MAX_OPTUNA_PARAMS:
        raise ValueError(f"Optuna searches 1 to {MAX_OPTUNA_PARAMS} parameters")
    integer = {p.name: p.integer for p in tunable_parameters(evaluator.spec)}
    rows: list[dict[str, Any]] = []

    def objective(trial: optuna.Trial) -> float:
        point: Point = {}
        for name, values in axes.items():
            low, high = min(values), max(values)
            if integer[name]:
                point[name] = float(trial.suggest_int(name, int(low), int(high)))
            else:
                point[name] = trial.suggest_float(name, low, high)
        row = evaluator.evaluate(window, point)
        rows.append(row)
        if progress:
            progress(len(rows), n_trials)
        value = float(row["objective"])
        return value if math.isfinite(value) else -1e9

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials)
    return pd.DataFrame(rows)
