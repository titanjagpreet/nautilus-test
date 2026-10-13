"""The PortfolioAnalyzer patch must not change any statistic (real BTC data; skipped without `make data`)."""

from __future__ import annotations

import pandas as pd
import pytest

from strategy_lab.engines.inputs import resolve_bar_source
from strategy_lab.engines.nautilus.handwritten import run_handwritten

pytestmark = pytest.mark.realdata


@pytest.fixture(scope="module")
def runs() -> dict[bool, object]:
    start, end = pd.Timestamp("2025-07-01", tz="UTC"), pd.Timestamp("2025-07-15", tz="UTC")
    try:
        resolve_bar_source("BTC-PERP", start, end)
    except (FileNotFoundError, ValueError):
        pytest.skip("no stored BTC history covers July 2025 (run `make data`)")
    return {
        patched: run_handwritten(start, end, "1m", "1m", analyzer_patch=patched)[0] for patched in (False, True)
    }


def test_patch_keeps_statistics_identical(runs: dict[bool, object]) -> None:
    stock, patched = runs[False], runs[True]
    assert stock.summary["positions"] > 300  # enough closed trades to exercise the analyzer
    assert patched.stats_pnls == stock.stats_pnls
    assert patched.stats_returns == stock.stats_returns
    assert patched.summary == stock.summary
