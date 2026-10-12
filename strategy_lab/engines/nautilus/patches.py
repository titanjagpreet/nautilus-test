"""Workaround for a quadratic slowdown in NautilusTrader 1.231's ``PortfolioAnalyzer``.

Found by profiling (LEARNINGS.md §10): every time a position closes, ``Portfolio`` calls
``PortfolioAnalyzer.record_trade`` → ``_append_pnl_record``, which does ``pd.concat([existing, new])`` on a
growing Series. That is O(n²) in the number of closed positions, and slow per call under pandas 3 (Arrow-backed
string index). A 1-minute strategy with ~20k trades a year spends most of its time there.

The fix keeps the records in plain lists and turns them into the same Series, in the same order, right before
the only method that reads them (``realized_pnls``) runs. Statistics are identical
(``tests/test_nautilus_patches.py``). ``install()`` is idempotent and explicit; the measured numbers in REPORT.md
show both the stock and the patched timings.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nautilus_trader.analysis.analyzer import PortfolioAnalyzer

_PENDING = "_strategy_lab_pending_pnl_records"
_ORIGINAL_APPEND = PortfolioAnalyzer._append_pnl_record
_ORIGINAL_REALIZED_PNLS = PortfolioAnalyzer.realized_pnls
_ORIGINAL_RESET = PortfolioAnalyzer.reset


def _append_pnl_record(
    self: PortfolioAnalyzer,
    pnls: dict[Any, pd.Series],
    timestamps: dict[Any, pd.Series],
    position_id: Any,
    realized_pnl: Any,
    ts_event: int | None,
) -> None:
    pending: dict[tuple[int, Any], tuple[dict[Any, pd.Series], dict[Any, pd.Series], list[tuple[str, float, Any]]]]
    pending = self.__dict__.setdefault(_PENDING, {})
    key = (id(pnls), realized_pnl.currency)
    entry = pending.setdefault(key, (pnls, timestamps, []))
    entry[2].append((position_id.value, realized_pnl.as_double(), int(ts_event) if ts_event is not None else None))


def _flush(self: PortfolioAnalyzer) -> None:
    for (_, currency), (pnls, timestamps, rows) in self.__dict__.get(_PENDING, {}).items():
        if not rows:
            continue
        index = [r[0] for r in rows]
        new_pnls = pd.Series([r[1] for r in rows], index=index, dtype="float64")
        new_ts = pd.Series([r[2] for r in rows], index=index, dtype=object)
        pnls[currency] = new_pnls if currency not in pnls else pd.concat([pnls[currency], new_pnls])
        timestamps[currency] = new_ts if currency not in timestamps else pd.concat([timestamps[currency], new_ts])
        rows.clear()


def _realized_pnls(self: PortfolioAnalyzer, currency: Any = None) -> Any:
    _flush(self)
    return _ORIGINAL_REALIZED_PNLS(self, currency)


def _reset(self: PortfolioAnalyzer) -> None:
    self.__dict__.pop(_PENDING, None)
    _ORIGINAL_RESET(self)


def install() -> None:
    if PortfolioAnalyzer._append_pnl_record is _append_pnl_record:
        return  # already installed
    PortfolioAnalyzer._append_pnl_record = _append_pnl_record  # type: ignore[method-assign]
    PortfolioAnalyzer.realized_pnls = _realized_pnls  # type: ignore[method-assign]
    PortfolioAnalyzer.reset = _reset  # type: ignore[method-assign]


def uninstall() -> None:
    """Restore the stock methods (used by tests and the 'stock' benchmark)."""
    PortfolioAnalyzer._append_pnl_record = _ORIGINAL_APPEND  # type: ignore[method-assign]
    PortfolioAnalyzer.realized_pnls = _ORIGINAL_REALIZED_PNLS  # type: ignore[method-assign]
    PortfolioAnalyzer.reset = _ORIGINAL_RESET  # type: ignore[method-assign]
