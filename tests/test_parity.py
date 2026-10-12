"""Parity suite: the Numba engine must match NautilusTrader trade for trade (real data; skipped without data).

Requirement: same number of trades, identical entry and exit timestamps, net P&L within 0.5%. In practice the
engines agree exactly (see REPORT.md); exit reasons are compared too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from strategy_lab.data import storage
from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.fast import runner as fast
from strategy_lab.engines.inputs import MarketData, load_market
from strategy_lab.engines.nautilus import spec_runner as nautilus
from strategy_lab.spec.schema import StrategySpec

pytestmark = pytest.mark.realdata
CATALOGUE = sorted((Path(__file__).parent.parent / "strategy_lab" / "spec" / "catalogue").glob("*.json"))
START, END = pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2024-07-01", tz="UTC")  # includes extreme funding
_markets: dict[str, MarketData] = {}


def catalogue(prefix: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        next(p for p in CATALOGUE if p.stem.startswith(prefix)).read_text(encoding="utf-8")
    )
    return data


def market(symbol: str) -> MarketData:
    if symbol not in _markets:
        _markets[symbol] = load_market(symbol, START, END, contract_spec(symbol).price_decimals)  # type: ignore[arg-type]
    return _markets[symbol]


def assert_parity(data: dict[str, Any]) -> None:
    if not storage.list_datasets():
        pytest.skip("no data downloaded (run `make data`)")
    spec = StrategySpec.model_validate(data)
    md = market(spec.market.symbol)
    a = nautilus.run_spec(spec, START, END, market=md)
    b = fast.run_spec(spec, START, END, market=md)
    assert len(a.trades) == len(b.trades)
    for column in ("entry_time", "exit_time", "side", "exit_reason"):
        assert list(a.trades[column]) == list(b.trades[column]), column
    assert b.net_pnl == pytest.approx(a.net_pnl, rel=0.005, abs=1e-6)
    assert b.fees_paid == pytest.approx(a.fees_paid, rel=0.005, abs=1e-6)
    assert b.funding_paid == pytest.approx(a.funding_paid, rel=0.005, abs=1e-6)


@pytest.mark.parametrize("fee_profile", ["lighter_standard", "lighter_premium"])
@pytest.mark.parametrize("path", CATALOGUE, ids=lambda p: p.stem)
def test_catalogue_parity(path: Path, fee_profile: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["costs"]["fee_profile"] = fee_profile
    assert_parity(data)


def _variant(prefix: str, market_changes: dict[str, Any], risk_changes: dict[str, Any],
             cost_changes: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    data = catalogue(prefix)
    data["market"].update(market_changes)
    data["risk"].update(risk_changes)
    data["costs"].update(cost_changes or {})
    return data


VARIANTS = {
    "cooldown_and_daily_cap": _variant("09", {}, {"cooldown_bars": 5, "max_trades_per_day": 2}),
    "structure_stop_percent_trail_fixed_size": _variant("01", {}, {
        "stop_loss": {"type": "structure", "lookback": 20, "buffer_pct": 0.1},
        "trailing_stop": {"type": "percent", "value": 1.5},
        "position_sizing": {"type": "fixed_usd", "value": 3000}}),
    "short_only_time_exit_percent_target": _variant("01", {"direction": "short"}, {
        "time_exit_bars": 12, "take_profit": {"type": "percent", "value": 2}}),
    "gold_atr_trail": _variant("10", {}, {"trailing_stop": {"type": "atr", "multiple": 2, "atr_period": 20}}),
    "htf_long_only_daily_cap_rr_target": _variant("05", {"direction": "long"}, {
        "max_trades_per_day": 1, "take_profit": {"type": "risk_reward", "multiple": 1.5}}),
    "tight_trail_rejected_modifies_leverage_5": _variant("03", {"timeframe": "1h"}, {
        "trailing_stop": {"type": "percent", "value": 0.4}, "leverage": 5,
        "position_sizing": {"type": "percent_equity", "value": 450}}),
    "no_slippage_cooldown": _variant("06", {}, {"cooldown_bars": 2}, {"slippage_ticks": 0}),
}  # fmt: skip


@pytest.mark.parametrize("name", VARIANTS)
def test_risk_feature_parity(name: str) -> None:
    assert_parity(VARIANTS[name])


def _ind(id_: str, type_: str, source: str | None = None, **params: float) -> dict[str, Any]:
    return {"id": id_, "type": type_, "params": params, "source": source}


def _op(indicator: str, output: str | None = None, bars_ago: int = 0) -> dict[str, Any]:
    return {"indicator": indicator, "output": output, "bars_ago": bars_ago}


CLOSE = {"input": "close"}


def _strategy(
    name: str, timeframe: str, indicators: list[dict[str, Any]], rules: dict[str, Any]
) -> dict[str, Any]:
    data = catalogue("01")
    data["meta"]["name"] = name
    data["market"]["timeframe"] = timeframe
    data["indicators"] = indicators
    data["rules"] = rules
    return data


# The indicator types no catalogue strategy uses (wma, hma, roc, cci, obv, atr, highest, lowest), end to end.
INDICATOR_SPECS = {
    "hma_wma_roc": _strategy("HMA/WMA with ROC", "1h",
        [_ind("hma", "hma", period=21), _ind("wma", "wma", period=50), _ind("roc", "roc", period=10)],
        {"entry_long": {"op": "all", "args": [{"op": "crosses_above", "left": _op("hma"), "right": _op("wma")},
                                              {"op": ">", "left": _op("roc"), "right": {"value": 0}}]},
         "exit_long": {"op": "crosses_below", "left": _op("hma"), "right": _op("wma")},
         "entry_short": {"op": "all", "args": [{"op": "crosses_below", "left": _op("hma"), "right": _op("wma")},
                                               {"op": "<", "left": _op("roc"), "right": {"value": 0}}]},
         "exit_short": {"op": "crosses_above", "left": _op("hma"), "right": _op("wma")}}),
    "cci_obv_atr": _strategy("CCI with OBV and ATR filters", "4h",
        [_ind("cci", "cci", period=20), _ind("obv", "obv"), _ind("atr", "atr", period=14)],
        {"entry_long": {"op": "all", "args": [
            {"op": "crosses_above", "left": _op("cci"), "right": {"value": -100}},
            {"op": ">", "left": _op("obv"), "right": _op("obv", bars_ago=20)},
            {"op": ">", "left": _op("atr"), "right": _op("atr", bars_ago=5)}]},
         "exit_long": {"op": ">", "left": _op("cci"), "right": {"value": 100}},
         "entry_short": {"op": "all", "args": [
            {"op": "crosses_below", "left": _op("cci"), "right": {"value": 100}},
            {"op": "<", "left": _op("obv"), "right": _op("obv", bars_ago=20)}]},
         "exit_short": {"op": "<", "left": _op("cci"), "right": {"value": -100}}}),
    "highest_lowest_channel": _strategy("Highest/lowest channel", "15m",
        [_ind("hi", "highest", period=40), _ind("lo", "lowest", period=40),
         _ind("hi_exit", "highest", "close", period=10), _ind("lo_exit", "lowest", "close", period=10)],
        {"entry_long": {"op": ">", "left": CLOSE, "right": _op("hi", bars_ago=1)},
         "exit_long": {"op": "<", "left": CLOSE, "right": _op("lo_exit", bars_ago=1)},
         "entry_short": {"op": "<", "left": CLOSE, "right": _op("lo", bars_ago=1)},
         "exit_short": {"op": ">", "left": CLOSE, "right": _op("hi_exit", bars_ago=1)}}),
}  # fmt: skip


@pytest.mark.parametrize("name", INDICATOR_SPECS)
def test_indicator_coverage_parity(name: str) -> None:
    assert_parity(INDICATOR_SPECS[name])
