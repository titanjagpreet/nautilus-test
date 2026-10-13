"""The robustness lab: one call runs every test on a spec and scores it 0-100 from named, weighted parts.

Score parts (each 0..1, weight in points; every part and its inputs are shown to the user):

| part | weight | 1.0 means |
|---|---|---|
| out-of-sample retention | 25 | the tuned parameters keep their in-sample Sharpe on the unseen 30% |
| walk-forward consistency | 25 | every out-of-sample window profitable and walk-forward efficiency ≥ 1 |
| parameter stability | 20 | the best heat-map cell sits on a plateau (neighbours as good) |
| Monte Carlo | 15 | no resample of the trades ends with a loss |
| sample size | 10 | at least 100 trades (0 at 20 or fewer) |
| simplicity | 5 | at most 4 tunable parameters (0 above 6) |

The score describes robustness, not profitability: a robustly losing strategy can only score where losing does
not matter (stability, sample size, simplicity). Warnings flag the classic signs of overfitting.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.inputs import MarketData, load_market
from strategy_lab.lab.evaluator import Evaluator, Window, warmup_span
from strategy_lab.lab.metrics import compute
from strategy_lab.lab.optimize import MAX_OPTUNA_PARAMS, best_point, default_axes, optuna_search
from strategy_lab.lab.validation import (
    Heatmap,
    MonteCarlo,
    OutOfSample,
    WalkForward,
    heatmap,
    monte_carlo,
    out_of_sample,
    walk_forward,
)
from strategy_lab.spec.params import tunable_parameters
from strategy_lab.spec.schema import StrategySpec
from strategy_lab.spec.validator import MAX_TUNABLE

ProgressFn = Callable[[str, float], None]  # (stage, fraction of the whole lab done)


@dataclass(frozen=True)
class Part:
    name: str
    weight: float
    score: float  # 0..1
    detail: str

    @property
    def points(self) -> float:
        return self.weight * self.score


@dataclass(frozen=True)
class LabWarning:
    code: str
    message: str


def _clip(x: float) -> float:
    return 0.0 if not math.isfinite(x) else max(0.0, min(1.0, x))


def score_parts(
    full: dict[str, Any], oos: OutOfSample, wf: WalkForward, hm: Heatmap | None, mc: MonteCarlo, n_tunable: int
) -> list[Part]:
    trades = int(full["trades"])
    is_sharpe, oos_sharpe = oos.is_metrics["sharpe"] or 0.0, oos.oos_metrics["sharpe"] or 0.0
    simplicity = 1.0 if n_tunable <= 4 else 0.5 if n_tunable <= MAX_TUNABLE else 0.0
    return [
        Part(
            "out-of-sample retention",
            25,
            _clip(oos.retention),
            f"Sharpe in-sample {is_sharpe:.2f} → out-of-sample {oos_sharpe:.2f} (retention {oos.retention:.0%})",
        ),
        Part(
            "walk-forward consistency",
            25,
            0.5 * wf.profitable_share + 0.5 * _clip(wf.efficiency),
            f"{wf.profitable_share:.0%} of {len(wf.windows)} out-of-sample windows profitable; efficiency "
            f"{wf.efficiency:.2f}; chained out-of-sample return {wf.total_return_pct:+.1f}%",
        ),
        Part(
            "parameter stability",
            20,
            hm.stability if hm else 0.0,
            f"best cell's neighbours reach {hm.stability:.0%} of its objective"
            if hm
            else "no tunable parameters to map",
        ),
        Part(
            "Monte Carlo",
            15,
            _clip(1.0 - mc.prob_loss) if mc.final_return_pct else 0.0,
            f"{mc.prob_loss:.0%} of {mc.samples} trade resamples lose money; final return 5th / 95th "
            f"percentile {mc.final_return_pct['p5']:+.1f}% / {mc.final_return_pct['p95']:+.1f}%"
            if mc.final_return_pct
            else "fewer than 2 trades",
        ),
        Part("sample size", 10, _clip((trades - 20) / 80), f"{trades} trades over the whole period"),
        Part("simplicity", 5, simplicity, f"{n_tunable} tunable parameters"),
    ]


def warnings_for(
    full: dict[str, Any], oos: OutOfSample, wf: WalkForward, hm: Heatmap | None, mc: MonteCarlo, n_tunable: int
) -> list[LabWarning]:
    out = []
    if n_tunable > MAX_TUNABLE:
        out.append(
            LabWarning(
                "TOO_MANY_PARAMETERS",
                f"{n_tunable} tunable parameters (> {MAX_TUNABLE}): every "
                "extra knob makes a good backtest more likely to be luck",
            )
        )
    if full["trades"] < 30:
        out.append(LabWarning("FEW_TRADES", f"only {full['trades']} trades — too few to tell skill from luck"))
    is_sharpe, oos_sharpe = oos.is_metrics["sharpe"] or 0.0, oos.oos_metrics["sharpe"] or 0.0
    if is_sharpe > 0 and oos_sharpe < 0.5 * is_sharpe:
        out.append(
            LabWarning(
                "OUT_OF_SAMPLE_DECAY",
                f"Sharpe falls from {is_sharpe:.2f} in-sample to {oos_sharpe:.2f} on unseen data",
            )
        )
    if (oos.is_metrics["net_pnl"] or 0) > 0 and (oos.oos_metrics["net_pnl"] or 0) < 0:
        out.append(LabWarning("OUT_OF_SAMPLE_LOSS", "profitable when tuned, losing on the unseen 30%"))
    if hm is not None and hm.best is not None and hm.stability < 0.5:
        out.append(
            LabWarning(
                "ISOLATED_OPTIMUM",
                f"the best parameters are a spike: neighbours reach only {hm.stability:.0%} of the best objective",
            )
        )
    if hm is not None and hm.best is not None and _on_edge(hm):
        out.append(
            LabWarning(
                "OPTIMUM_ON_EDGE",
                "the best heat-map cell is on the edge of the grid: the real "
                "optimum may lie outside the tested range",
            )
        )
    if wf.windows and wf.profitable_share < 0.5:
        out.append(
            LabWarning(
                "WALK_FORWARD_INCONSISTENT",
                f"only {wf.profitable_share:.0%} of walk-forward windows are profitable",
            )
        )
    drift = {k: v for k, v in wf.param_drift().items() if v > 0.3}
    if drift:
        names = ", ".join(f"{k} (variation {v:.0%})" for k, v in drift.items())
        out.append(LabWarning("UNSTABLE_PARAMETERS", f"the best parameters change a lot between windows: {names}"))
    if mc.final_return_pct and mc.final_return_pct["p5"] < 0:
        out.append(
            LabWarning(
                "MONTE_CARLO_LOSS",
                f"{mc.prob_loss:.0%} of trade resamples end with a loss (5th "
                f"percentile {mc.final_return_pct['p5']:+.1f}%)",
            )
        )
    bh = full.get("buy_hold_return_pct")
    if bh is not None and full["net_return_pct"] < bh:
        out.append(
            LabWarning("BELOW_BUY_AND_HOLD", f"return {full['net_return_pct']:+.1f}% vs buy & hold {bh:+.1f}%")
        )
    return out


def _on_edge(hm: Heatmap) -> bool:
    assert hm.best is not None
    row, col = hm.best
    rows, cols = len(hm.y_values), len(hm.x_values)
    return col in (0, cols - 1) or (rows > 1 and row in (0, rows - 1))


@dataclass
class LabReport:
    spec_name: str
    market: str
    source: str
    window: Window
    objective: str
    axes: dict[str, list[float]]
    full_metrics: dict[str, Any]
    full_equity: pd.Series
    closes: pd.Series
    heatmap: Heatmap | None
    oos: OutOfSample
    walk_forward: WalkForward
    monte_carlo: MonteCarlo
    optuna: dict[str, Any] | None
    parts: list[Part]
    warnings: list[LabWarning]
    runs: int
    wall_seconds: float
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def score(self) -> float:
        return round(sum(p.points for p in self.parts), 1)

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready; curves are reduced to one point per day."""
        return {
            "spec_name": self.spec_name,
            "market": self.market,
            "source": self.source,
            "window": [self.window.start.isoformat(), self.window.end.isoformat()],
            "objective": self.objective,
            "axes": self.axes,
            "score": self.score,
            "parts": [asdict(p) | {"points": round(p.points, 1)} for p in self.parts],
            "warnings": [asdict(w) for w in self.warnings],
            "full_metrics": self.full_metrics,
            "curves": {
                "equity": _daily(self.full_equity),
                "buy_hold": _daily(self.closes / self.closes.iloc[0] * self.full_equity.iloc[0])
                if len(self.closes) and len(self.full_equity)
                else [],
                "oos_equity": _daily(self.oos.equity),
                "walk_forward_equity": _daily(self.walk_forward.equity),
            },
            "heatmap": asdict(self.heatmap) | {"current_rank": self.heatmap.current_rank}
            if self.heatmap
            else None,
            "oos": {
                "in_sample": _window(self.oos.in_sample),
                "out_sample": _window(self.oos.out_sample),
                "params": self.oos.params,
                "original": self.oos.original,
                "tuned": self.oos.tuned,
                "is_metrics": self.oos.is_metrics,
                "oos_metrics": self.oos.oos_metrics,
                "oos_original_metrics": self.oos.oos_original_metrics,
                "retention": self.oos.retention,
            },
            "walk_forward": {
                "windows": [
                    {
                        "in_sample": _window(w.in_sample),
                        "out_sample": _window(w.out_sample),
                        "params": w.params,
                        "is_metrics": w.is_metrics,
                        "oos_metrics": w.oos_metrics,
                    }
                    for w in self.walk_forward.windows
                ],
                "profitable_share": self.walk_forward.profitable_share,
                "efficiency": self.walk_forward.efficiency,
                "total_return_pct": self.walk_forward.total_return_pct,
                "param_drift": self.walk_forward.param_drift(),
            },
            "monte_carlo": asdict(self.monte_carlo),
            "optuna": self.optuna,
            "runs": self.runs,
            "wall_seconds": round(self.wall_seconds, 2),
            "meta": self.meta,
        }


def _window(w: Window) -> list[str]:
    return [w.start.isoformat(), w.end.isoformat()]


def _daily(series: pd.Series) -> list[list[Any]]:
    if series.empty:
        return []
    daily = series.resample("1D").last().dropna()
    return [[f"{ts:%Y-%m-%d}", round(float(v), 2)] for ts, v in zip(daily.index, daily.to_numpy(), strict=True)]


def run_lab(
    spec: StrategySpec,
    start: pd.Timestamp,
    end: pd.Timestamp,
    parameters: Sequence[str] | None = None,
    objective: str = "sharpe",
    optuna_trials: int = 0,
    mc_samples: int = 1000,
    grid_points: int = 9,
    source: str | None = None,
    market: MarketData | None = None,
    progress: ProgressFn | None = None,
) -> LabReport:
    """Every test on ``spec`` over [start, end). ``parameters``: 1-2 for the heat-map and tuning (default: the
    first two indicator parameters); Optuna (``optuna_trials`` > 0) searches up to 4 of them."""
    t0 = time.perf_counter()
    report = progress or (lambda stage, fraction: None)
    tunables = tunable_parameters(spec)
    axes = default_axes(spec, list(parameters)[:2] if parameters else None, grid_points) if tunables else {}
    warmup = warmup_span(spec, axes)
    report("loading data", 0.0)
    if market is None:
        symbol = spec.market.symbol
        decimals = contract_spec(symbol).price_decimals
        market = load_market(symbol, start, end, decimals, source, history_from=start - warmup)
    evaluator = Evaluator(spec, market, warmup, objective)
    window = Window(start, end)

    report("baseline", 0.02)
    baseline = evaluator.run(window)
    full = compute(baseline).as_dict()
    hm = heatmap(evaluator, window, axes, lambda i, n: report("heat-map", 0.05 + 0.25 * i / n)) if axes else None
    oos = out_of_sample(evaluator, window, axes, lambda i, n: report("out-of-sample", 0.30 + 0.15 * i / n))
    wf = walk_forward(evaluator, window, axes, lambda i, n: report("walk-forward", 0.45 + 0.40 * i / n))
    optuna_result = None
    if optuna_trials > 0 and tunables:
        names = list(parameters or axes)[:MAX_OPTUNA_PARAMS]
        o_axes = default_axes(spec, names, grid_points)
        rows = optuna_search(
            evaluator, window, o_axes, optuna_trials, progress=lambda i, n: report("optuna", 0.85 + 0.10 * i / n)
        )
        best = best_point(rows, names)
        optuna_result = {
            "parameters": names,
            "trials": len(rows),
            "best": best,
            "best_objective": float(rows["objective"].max()) if len(rows) else None,
            "note": "searched on the whole period: in-sample only",
        }
    report("Monte Carlo", 0.95)
    mc = monte_carlo(baseline, mc_samples)
    parts = score_parts(full, oos, wf, hm, mc, len(tunables))
    warnings = warnings_for(full, oos, wf, hm, mc, len(tunables))
    report("done", 1.0)
    return LabReport(
        spec_name=spec.meta.name,
        market=spec.market.symbol,
        source=market.source,
        window=window,
        objective=objective,
        axes=axes,
        full_metrics=full,
        full_equity=baseline.equity,
        closes=baseline.closes,
        heatmap=hm,
        oos=oos,
        walk_forward=wf,
        monte_carlo=mc,
        optuna=optuna_result,
        parts=parts,
        warnings=warnings,
        runs=evaluator.runs,
        wall_seconds=time.perf_counter() - t0,
        meta={
            "engine": "fast",
            "warmup_days": round(warmup / pd.Timedelta(days=1), 1),
            "funding_source": market.funding_source,
        },
    )
