"""Every catalogue strategy backtests in NautilusTrader on real data (skipped without `make data`)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from strategy_lab.data import storage
from strategy_lab.engines.nautilus.spec_runner import run_spec
from strategy_lab.spec.schema import StrategySpec

pytestmark = pytest.mark.realdata
CATALOGUE = sorted((Path(__file__).parent.parent / "strategy_lab" / "spec" / "catalogue").glob("*.json"))
REASONS = {"rule", "stop", "target", "time", "reverse", "end"}


@pytest.mark.parametrize("path", CATALOGUE, ids=lambda p: p.stem)
def test_catalogue_strategy_runs_in_nautilus(path: Path) -> None:
    if not storage.list_datasets():
        pytest.skip("no data downloaded (run `make data`)")
    spec = StrategySpec.model_validate(json.loads(path.read_text()))
    result = run_spec(spec, pd.Timestamp("2025-02-01", tz="UTC"), pd.Timestamp("2025-03-15", tz="UTC"))
    trades = result.trades
    assert set(trades["exit_reason"]) <= REASONS
    assert (trades["exit_time"] >= trades["entry_time"]).all()
    assert (trades["quantity"] > 0).all()
    # Our trade ledger + funding ledger reproduce Nautilus's own account balance.
    expected_balance = result.starting_balance + result.net_pnl
    assert result.meta["nautilus_final_balance"] == pytest.approx(expected_balance, abs=1e-6)
    if spec.market.direction == "long":
        assert set(trades["side"]) <= {"long"}
    assert (trades["fees"] >= 0).all()
    assert trades["funding"].sum() == pytest.approx(result.funding_paid)  # every payment belongs to a trade
