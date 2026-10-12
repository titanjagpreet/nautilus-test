"""The data stream that makes NautilusTrader follow the spec's execution semantics (LEARNINGS.md §7).

Per base bar (e.g. 15m) the generator yields one chunk, built *after* the strategy has handled the previous
base bar (``BacktestDataIterator`` asks a generator for its next chunk when it hands out the last item of the
current one, and every chunk ends with the next minute's "open" bar, which does not depend on direction):

====================  ===============================================================================
timestamp             item
====================  ===============================================================================
t₀ + 1 ns             "open" bar O=H=L=C=open of the first minute (gap check; 1 ns-latency orders sent at
                      the previous base close fill here → **next-bar-open fills**)          [previous chunk]
t₀ + 2 ns             second "open" bar (lets stop/target orders placed on the entry fill reach the venue)
t + 3 ns, t + 4 ns    each minute's path: long → (O,O,L,L) then (L,H,L,C) = **adverse extreme first**;
                      short → (O,H,L,C) (fixed ordering already visits the high first)
T (base close)        completed higher-timeframe bars, then the base bar (strategy decides here)
t₀' + 1 ns            "open" bar of the next base bar's first minute
====================  ===============================================================================

When the strategy is flat with nothing pending, no order can rest during the bar, so the minute path is
skipped — Nautilus then only processes ~2 items per base bar while flat.

Execution bars use the 1-MINUTE bar type (the finest type is what the venue executes against); base and HTF
bars use coarser EXTERNAL types, which the venue ignores. Their volume is set very large: we model no market
impact, and bar-volume-limited fills would otherwise split orders (``test_small_bar_volume_splits_market_orders``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from strategy_lab.data.schema import TIMEFRAMES

NS_PER_MIN = 60_000_000_000
EXEC_VOLUME = 1_000_000_000.0


@dataclass(frozen=True)
class BarArrays:
    open_ns: np.ndarray  # int64 bar open times
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> BarArrays:
        return cls(
            frame["ts"].dt.as_unit("ns").astype("int64").to_numpy(),
            *(frame[c].to_numpy(dtype=np.float64) for c in ("open", "high", "low", "close", "volume")),
        )


def execution_stream(
    minutes: BarArrays,
    base: BarArrays,
    base_timeframe: str,
    htf: dict[str, BarArrays],
    exec_type: BarType,
    base_type: BarType,
    htf_types: dict[str, BarType],
    price_decimals: int,
    size_decimals: int,
    direction: Callable[[], str],
) -> Iterator[list[Bar]]:
    """Yield chunks of bars; ``direction()`` returns the strategy's expected side ("long"/"short"/"flat")."""
    big = Quantity(EXEC_VOLUME, size_decimals)

    def price(x: float) -> Price:
        return Price(float(x), price_decimals)

    def flat_bar(px: float, ts: int) -> Bar:
        p = price(px)
        return Bar(exec_type, p, p, p, p, big, ts, ts)

    def bar(bar_type: BarType, arrays: BarArrays, i: int, ts: int, volume: Quantity) -> Bar:
        return Bar(
            bar_type,
            price(arrays.open[i]),
            price(arrays.high[i]),
            price(arrays.low[i]),
            price(arrays.close[i]),
            volume,
            ts,
            ts,
        )

    base_width = int(TIMEFRAMES[base_timeframe].value)
    base_close = base.open_ns + base_width
    starts = np.searchsorted(minutes.open_ns, base.open_ns, side="left")
    ends = np.searchsorted(minutes.open_ns, base_close, side="left")
    htf_close = {tf: arr.open_ns + int(TIMEFRAMES[tf].value) for tf, arr in htf.items()}
    htf_next = dict.fromkeys(htf, 0)

    yield [flat_bar(minutes.open[starts[0]], int(minutes.open_ns[starts[0]]) + 1)]
    for b in range(len(base.open_ns)):
        side = direction()
        chunk: list[Bar] = []
        if side != "flat":
            for m in range(starts[b], ends[b]):
                t = int(minutes.open_ns[m])
                o, h, lo, c = minutes.open[m], minutes.high[m], minutes.low[m], minutes.close[m]
                if m == starts[b]:
                    chunk.append(flat_bar(o, t + 2))
                if side == "long":
                    pa, pb, pc = price(o), price(lo), price(h)
                    chunk.append(Bar(exec_type, pa, pa, pb, pb, big, t + 3, t + 3))
                    chunk.append(Bar(exec_type, pb, pc, pb, price(c), big, t + 4, t + 4))
                else:
                    chunk.append(Bar(exec_type, price(o), price(h), price(lo), price(c), big, t + 4, t + 4))
        close_ns = int(base_close[b])
        for tf, arr in htf.items():
            i = htf_next[tf]
            while i < len(arr.open_ns) and htf_close[tf][i] <= close_ns:
                chunk.append(bar(htf_types[tf], arr, i, close_ns, Quantity(arr.volume[i], size_decimals)))
                i += 1
            htf_next[tf] = i
        chunk.append(bar(base_type, base, b, close_ns, Quantity(base.volume[b], size_decimals)))
        if b + 1 < len(base.open_ns):
            first = starts[b + 1]
            chunk.append(flat_bar(minutes.open[first], int(minutes.open_ns[first]) + 1))
        else:
            last = ends[b] - 1  # close-out point for positions still open at the end of the data
            chunk.append(flat_bar(minutes.close[last], close_ns + 1))
        yield chunk
