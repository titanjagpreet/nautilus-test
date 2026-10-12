"""Robustness lab: windows, warm-up, search, heat-map stability, Monte Carlo, score and warnings.

SYNTHETIC: most tests run on random-walk 1-minute bars generated in code (``synthetic_market``); they check the
mechanics, not trading results. ``test_trade_from_*`` uses the real BTC history when it is downloaded.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy_lab.data import storage
from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.fast import runner as fast
from strategy_lab.engines.inputs import MarketData, load_market, slice_market
from strategy_lab.engines.results import TRADE_COLUMNS, BacktestResult
from strategy_lab.lab.evaluator import Evaluator, Window, warmup_span
from strategy_lab.lab.optimize import axis_values, best_point, default_axes, grid_search, optuna_search
from strategy_lab.lab.robustness import run_lab
from strategy_lab.lab.validation import monte_carlo, stability_at, trade_returns, walk_forward_windows
from strategy_lab.spec.params import tunable_parameters
from strategy_lab.spec.schema import StrategySpec

CATALOGUE = sorted((Path(__file__).parent.parent / "strategy_lab" / "spec" / "catalogue").glob("*.json"))
EMA = StrategySpec.model_validate_json(CATALOGUE[0].read_text())
T = pd.Timestamp


def synthetic_market(start: str, months: int, seed: int = 1) -> MarketData:
    """SYNTHETIC random-walk 1m BTC-like bars (no funding) — mechanics tests only."""
    ts = pd.date_range(start, T(start) + pd.DateOffset(months=months), freq="1min", inclusive="left", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 30_000 * np.exp(np.cumsum(rng.normal(0, 0.0008, len(ts))))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.0004, len(ts))) * close
    bars = pd.DataFrame(
        {
            "ts": ts,
            "open": open_.round(1),
            "close": close.round(1),
            "high": (np.maximum(open_, close) + spread).round(1),
            "low": (np.minimum(open_, close) - spread).round(1),
            "volume": 1.0,
            "source": "synthetic",
            "symbol": "BTC",
        }
    )
    funding = pd.DataFrame({"ts": pd.Series([], dtype="datetime64[ns, UTC]"), "rate": [], "period_hours": []})
    return MarketData("BTC-PERP", "synthetic/BTC", bars, funding, None)


@pytest.fixture(scope="module")
def market() -> MarketData:
    return synthetic_market("2024-01-01", 12)


def test_walk_forward_windows() -> None:
    pairs = walk_forward_windows(Window(T("2023-01-01", tz="UTC"), T("2024-01-01", tz="UTC")))
    assert len(pairs) == 3  # 6 months in, 2 out, rolled by 2: Jan-Jul|Jul-Sep, Mar-Sep|Sep-Nov, May-Nov|Nov-Jan
    assert pairs[0][0] == Window(T("2023-01-01", tz="UTC"), T("2023-07-01", tz="UTC"))
    assert pairs[-1][1] == Window(T("2023-11-01", tz="UTC"), T("2024-01-01", tz="UTC"))
    assert all(a.end == b.start for a, b in pairs)


def test_window_split_is_70_30_on_a_day_boundary() -> None:
    a, b = Window(T("2024-01-01", tz="UTC"), T("2025-01-01", tz="UTC")).split(0.7)
    assert a.end == b.start == T("2024-09-13", tz="UTC")  # day 256.2 of the leap year 2024


def test_axis_values_respect_bounds_and_integers() -> None:
    params = {p.name: p for p in tunable_parameters(EMA)}
    fast_values = axis_values(params["ema_fast.period"], 9)
    assert fast_values == sorted(set(fast_values))
    assert all(v == int(v) and 2 <= v <= 500 for v in fast_values)
    assert min(fast_values) == 6.0
    assert max(fast_values) == 18.0
    stop = axis_values(params["stop_loss.multiple"], 5)
    assert stop == [1.0, 1.5, 2.0, 2.5, 3.0]


def test_warmup_span_uses_the_largest_tuned_values() -> None:
    small = warmup_span(EMA)
    large = warmup_span(EMA, {"ema_slow.period": [48, 200]})
    assert large > small
    assert large == pd.Timedelta(minutes=3 * 200 * 60) + pd.Timedelta(days=1)


def test_trade_from_blocks_entries_and_starts_the_curve(market: MarketData) -> None:
    prep = fast.prepare(EMA, market)
    cut = T("2024-06-01", tz="UTC")
    result = fast.run_prepared(prep, trade_from=cut)
    assert len(result.trades)
    assert (result.trades["entry_time"] > cut).all()
    assert result.equity.index[0] >= cut
    assert result.equity.iloc[0] == 10_000.0
    assert result.start == cut


def test_grid_and_optuna_search(market: MarketData) -> None:
    window = Window(T("2024-03-01", tz="UTC"), T("2024-07-01", tz="UTC"))
    evaluator = Evaluator(EMA, market, warmup_span(EMA), min_trades=1)
    axes = {"ema_fast.period": [8.0, 12.0], "ema_slow.period": [30.0, 48.0]}
    rows = grid_search(evaluator, window, axes)
    assert len(rows) == 4
    assert {"objective", "sharpe", "trades", "ema_fast.period"} <= set(rows.columns)
    best = best_point(rows, list(axes))
    assert best is not None
    assert rows.loc[rows["objective"].idxmax(), "ema_fast.period"] == best["ema_fast.period"]
    trials = optuna_search(evaluator, window, axes, n_trials=5, seed=3)
    assert len(trials) == 5
    assert trials["ema_fast.period"].between(8, 12).all()


def test_stability_plateau_vs_spike() -> None:
    plateau = np.full((3, 3), 1.0)
    plateau[1, 1] = 1.1
    assert stability_at(plateau, 1, 1) == pytest.approx(1.0 / 1.1)
    spike = np.zeros((3, 3))
    spike[1, 1] = 2.0
    assert stability_at(spike, 1, 1) == 0.0
    corner = np.array([[1.0, -math.inf], [0.5, 0.5]])
    assert stability_at(corner, 0, 0) == pytest.approx((0 + 0.5 + 0.5) / 3)
    assert stability_at(-plateau, 1, 1) == 0.0


def result_with_trades(pnl: list[float]) -> BacktestResult:
    trades = pd.DataFrame({c: [0.0] * len(pnl) for c in TRADE_COLUMNS})
    trades["pnl_net"] = pnl
    empty = pd.Series(dtype=float)
    return BacktestResult(
        "fast",
        "x",
        "BTC-PERP",
        "synthetic",
        None,
        T("2024-01-01", tz="UTC"),
        T("2025-01-01", tz="UTC"),
        1000.0,
        trades,
        pd.DataFrame(),
        empty,
        empty,
    )


def test_monte_carlo() -> None:
    result = result_with_trades([100.0, -55.0, 20.0])
    assert trade_returns(result) == pytest.approx([0.1, -0.05, 20.0 / 1045.0])
    winning = monte_carlo(result_with_trades([10.0] * 20), samples=200)
    assert winning.prob_loss == 0.0
    assert winning.max_drawdown_pct["p5"] == 0.0
    mixed = monte_carlo(result_with_trades([30.0, -25.0] * 30), samples=1000, seed=1)
    assert mixed.final_return_pct["p5"] < mixed.final_return_pct["p50"] < mixed.final_return_pct["p95"]
    assert len(mixed.final_returns) == 1000
    assert 0 < mixed.prob_loss < 1
    assert monte_carlo(result_with_trades([5.0])).final_return_pct == {}


def test_run_lab_end_to_end(market: MarketData) -> None:
    calls: list[tuple[str, float]] = []
    report = run_lab(
        EMA,
        T("2024-02-01", tz="UTC"),
        T("2025-01-01", tz="UTC"),
        grid_points=3,
        optuna_trials=4,
        mc_samples=200,
        market=market,
        progress=lambda s, f: calls.append((s, f)),
    )
    data = report.as_dict()
    json.dumps(data)  # JSON-ready for the API
    assert sum(p["weight"] for p in data["parts"]) == 100
    assert 0 <= data["score"] <= 100
    assert data["score"] == pytest.approx(sum(p["points"] for p in data["parts"]), abs=0.11)
    assert len(data["walk_forward"]["windows"]) == 2
    assert data["heatmap"]["x"] == "ema_fast.period"
    assert len(data["heatmap"]["objective"]) == 3
    assert data["optuna"]["trials"] == 4
    assert data["curves"]["equity"][0][0] == "2024-02-01"
    assert [f for _, f in calls] == sorted(f for _, f in calls)
    assert calls[-1] == ("done", 1.0)
    codes = {w["code"] for w in data["warnings"]}
    assert codes <= {
        "TOO_MANY_PARAMETERS",
        "FEW_TRADES",
        "OUT_OF_SAMPLE_DECAY",
        "OUT_OF_SAMPLE_LOSS",
        "ISOLATED_OPTIMUM",
        "OPTIMUM_ON_EDGE",
        "WALK_FORWARD_INCONSISTENT",
        "UNSTABLE_PARAMETERS",
        "MONTE_CARLO_LOSS",
        "BELOW_BUY_AND_HOLD",
    }


def test_default_axes() -> None:
    assert list(default_axes(EMA)) == ["ema_fast.period", "ema_slow.period"]
    with pytest.raises(KeyError):
        default_axes(EMA, ["nope"])


@pytest.mark.realdata
def test_trade_from_matches_a_full_run_after_a_flat_point() -> None:
    """With enough warm-up, a window run reproduces the full run's trades that start after the window start."""
    if not storage.list_datasets():
        pytest.skip("no data downloaded (run `make data`)")
    spec = StrategySpec.model_validate_json(CATALOGUE[2].read_text())  # Donchian: exact windowed indicators
    start, end = T("2024-01-01", tz="UTC"), T("2024-07-01", tz="UTC")
    market = load_market(spec.market.symbol, start, end, contract_spec(spec.market.symbol).price_decimals)
    full = fast.run_prepared(fast.prepare(spec, market))
    trades = full.trades
    gap = next(
        i
        for i in range(1, len(trades))
        if trades["entry_time"].iloc[i] - trades["exit_time"].iloc[i - 1] > pd.Timedelta(days=2)
    )
    cut = (trades["exit_time"].iloc[gap - 1] + pd.Timedelta(days=1)).floor("D")
    window = fast.run_prepared(
        fast.prepare(spec, slice_market(market, cut - pd.Timedelta(days=30), end)), trade_from=cut
    )
    expected = trades[trades["entry_time"] > cut].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        window.trades[["entry_time", "exit_time", "side", "exit_reason"]],
        expected[["entry_time", "exit_time", "side", "exit_reason"]],
    )
