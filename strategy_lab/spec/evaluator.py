"""Bar-by-bar evaluation of spec rules (used by the generic NautilusTrader strategy).

Semantics, shared with the fast engine's vectorised evaluator (``engines/fast/compile.py``):

* An operand value is *available* when its indicator is initialized at that bar (or the input exists).
* A rule fires only if **every** operand it references is available — at ``bars_ago`` and, for crosses, at
  ``bars_ago + 1``. Otherwise the rule is false (so ``not`` never turns "no data" into a signal).
* ``crosses_above(a, b)``: a > b now and a ≤ b one bar earlier. ``crosses_below`` mirrors it.
* ``between(v, lo, hi)``: lo ≤ v ≤ hi.
* Higher-timeframe operands index completed HTF bars: ``bars_ago`` counts HTF bars.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterator

from strategy_lab.spec.indicators import CATALOGUE
from strategy_lab.spec.schema import (
    AllOf,
    AnyOf,
    Between,
    Compare,
    Condition,
    ConstOperand,
    Cross,
    IndicatorOperand,
    InputOperand,
    Not,
    Operand,
    StrategySpec,
)
from strategy_lab.spec.streaming import BarValues, Runtime, make_runtime

Series = deque[float]  # most recent value last; NaN = not available


def _operands(cond: Condition) -> Iterator[tuple[Operand, int]]:
    """(operand, extra bars of history needed): crosses need one extra bar."""
    if isinstance(cond, Compare):
        yield cond.left, 0
        yield cond.right, 0
    elif isinstance(cond, Cross):
        yield cond.left, 1
        yield cond.right, 1
    elif isinstance(cond, Between):
        yield cond.value, 0
        yield cond.low, 0
        yield cond.high, 0
    elif isinstance(cond, AllOf | AnyOf):
        for arg in cond.args:
            yield from _operands(arg)
    elif isinstance(cond, Not):
        yield from _operands(cond.arg)


def rule_operands(spec: StrategySpec) -> list[tuple[Operand, int]]:
    out: list[tuple[Operand, int]] = []
    for name in ("entry_long", "exit_long", "entry_short", "exit_short"):
        cond = getattr(spec.rules, name)
        if cond is not None:
            out.extend(_operands(cond))
    return out


class SpecState:
    """Indicator runtimes plus the value history every rule needs, for base and higher timeframes."""

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = spec
        self.base = spec.market.timeframe
        self.runtimes: dict[str, Runtime] = {ind.id: make_runtime(ind) for ind in spec.indicators}
        self.type_of = {ind.id: ind.type for ind in spec.indicators}
        self.timeframe_of = {ind.id: ind.timeframe or self.base for ind in spec.indicators}
        depth: dict[tuple[str, str], int] = {}
        for operand, extra in rule_operands(spec):
            if isinstance(operand, IndicatorOperand):
                key = (operand.indicator, operand.output or CATALOGUE[self.type_of[operand.indicator]].main_output)
            elif isinstance(operand, InputOperand):
                key = ("$input", operand.input)
            else:
                continue
            depth[key] = max(depth.get(key, 0), operand.bars_ago + extra + 1)
        self.history: dict[tuple[str, str], Series] = {k: deque(maxlen=n) for k, n in depth.items()}

    def _push(self, key: tuple[str, str], value: float) -> None:
        series = self.history.get(key)
        if series is not None:
            series.append(value)

    def update(self, timeframe: str, bar: BarValues, funding_rate_8h: float | None = None) -> None:
        """Feed one completed bar of ``timeframe`` (base bars also update the raw-input histories)."""
        for ind_id, runtime in self.runtimes.items():
            if self.timeframe_of[ind_id] != timeframe:
                continue
            runtime.update(bar)
            values = runtime.outputs() if runtime.initialized else {}
            for output in CATALOGUE[self.type_of[ind_id]].outputs:
                self._push((ind_id, output), values.get(output, math.nan))
        if timeframe != self.base:
            return
        for field in ("open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"):
            self._push(("$input", field), bar.field(field))
        self._push(("$input", "hour_utc"), float(bar.open_time.hour))
        self._push(("$input", "funding_rate"), math.nan if funding_rate_8h is None else funding_rate_8h)

    def value(self, operand: Operand, extra: int = 0) -> float:
        if isinstance(operand, ConstOperand):
            return operand.value
        key: tuple[str, str]
        if isinstance(operand, InputOperand):
            key = ("$input", operand.input)
        else:
            key = (operand.indicator, operand.output or CATALOGUE[self.type_of[operand.indicator]].main_output)
        series = self.history[key]
        ago = operand.bars_ago + extra
        return series[-1 - ago] if ago < len(series) else math.nan

    def evaluate(self, cond: Condition | None) -> bool:
        if cond is None:
            return False
        if any(math.isnan(self.value(op, e)) for op, extra in _operands(cond) for e in range(extra + 1)):
            return False
        return self._eval(cond)

    def _eval(self, cond: Condition) -> bool:
        if isinstance(cond, Compare):
            a, b = self.value(cond.left), self.value(cond.right)
            return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[cond.op]
        if isinstance(cond, Cross):
            a0, b0 = self.value(cond.left), self.value(cond.right)
            a1, b1 = self.value(cond.left, 1), self.value(cond.right, 1)
            return (a0 > b0 and a1 <= b1) if cond.op == "crosses_above" else (a0 < b0 and a1 >= b1)
        if isinstance(cond, Between):
            v, lo, hi = self.value(cond.value), self.value(cond.low), self.value(cond.high)
            return lo <= v <= hi
        if isinstance(cond, AllOf):
            return all(self._eval(c) for c in cond.args)
        if isinstance(cond, AnyOf):
            return any(self._eval(c) for c in cond.args)
        assert isinstance(cond, Not)
        return not self._eval(cond.arg)
