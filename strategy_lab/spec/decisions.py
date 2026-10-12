"""Position-management rules shared by both engines (ARCHITECTURE.md "Execution semantics").

The generic NautilusTrader strategy calls these functions directly; the Numba engine mirrors them line by
line (``engines/fast/simulate.py``). Keep the two in sync — the parity suite fails otherwise.

At each base-bar close, in this order:

1. In a position: exit if its exit rule fires or ``time_exit_bars`` is reached; also exit (and reverse) if the
   *opposite* entry rule fires and a new entry is allowed.
2. Flat (or exiting): enter long/short if exactly one entry rule fires, the direction allows it, the cooldown
   has passed (``bars_since_exit >= cooldown_bars``) and fewer than ``max_trades_per_day`` entries were taken on
   the UTC date of this bar's close. Both entry rules at once → no entry.
3. Still in a position and not exiting: move the trailing stop (never loosened).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from strategy_lab.spec.schema import (
    AtrStop,
    AtrTarget,
    AtrTrail,
    FixedUsd,
    PercentEquity,
    PercentStop,
    PercentTarget,
    PercentTrail,
    RiskRewardTarget,
    StrategySpec,
    StructureStop,
)


def round_price(value: float, decimals: int) -> float:
    """Half away from zero, like ``engines.inputs.round_to_tick`` and Nautilus's fixed-point conversion."""
    scale = 10.0**decimals
    return math.copysign(math.floor(abs(value) * scale + 0.5), value) / scale


def floor_quantity(value: float, decimals: int) -> float:
    scale = 10.0**decimals
    return math.floor(value * scale + 1e-9) / scale


@dataclass(frozen=True)
class Signals:
    entry_long: bool
    exit_long: bool
    entry_short: bool
    exit_short: bool


@dataclass(frozen=True)
class Decision:
    exit: bool
    exit_reason: str | None
    enter: str | None  # "long" | "short"


@dataclass
class TradeState:
    side: str = "flat"  # flat | long | short
    bars_held: int = 0
    bars_since_exit: int | None = None  # None = never traded
    entries_by_day: dict[str, int] | None = None

    def entries_on(self, day: str) -> int:
        return (self.entries_by_day or {}).get(day, 0)


def decide(spec: StrategySpec, state: TradeState, signals: Signals, day: str) -> Decision:
    direction = spec.market.direction
    risk = spec.risk
    can_long = direction in ("long", "both") and signals.entry_long
    can_short = direction in ("short", "both") and signals.entry_short
    if can_long and can_short:
        can_long = can_short = False
    cooldown_ok = state.bars_since_exit is None or state.bars_since_exit >= risk.cooldown_bars
    day_ok = risk.max_trades_per_day is None or state.entries_on(day) < risk.max_trades_per_day

    exit_now, reason = False, None
    if state.side != "flat":
        if risk.time_exit_bars is not None and state.bars_held >= risk.time_exit_bars:
            exit_now, reason = True, "time"
        elif (state.side == "long" and signals.exit_long) or (state.side == "short" and signals.exit_short):
            exit_now, reason = True, "rule"
        opposite = can_short if state.side == "long" else can_long
        # Reversal: the exit happens at this bar, so the cooldown has 0 bars elapsed.
        if opposite and day_ok and risk.cooldown_bars == 0:
            if not exit_now:
                exit_now, reason = True, "reverse"
            return Decision(True, reason, "short" if state.side == "long" else "long")
        return Decision(exit_now, reason, None)

    if not (cooldown_ok and day_ok):
        return Decision(False, None, None)
    if can_long:
        return Decision(False, None, "long")
    if can_short:
        return Decision(False, None, "short")
    return Decision(False, None, None)


def entry_quantity(
    spec: StrategySpec, equity: float, ref_price: float, size_decimals: int, min_quantity: float
) -> float:
    """Base-asset quantity for a new position (0 = too small to trade)."""
    sizing = spec.risk.position_sizing
    if isinstance(sizing, PercentEquity):
        notional = equity * sizing.value / 100.0
    else:
        assert isinstance(sizing, FixedUsd)
        notional = sizing.value
    notional = min(notional, max(equity, 0.0) * spec.risk.leverage)
    qty = floor_quantity(notional / ref_price, size_decimals)
    return qty if qty >= min_quantity else 0.0


@dataclass(frozen=True)
class RiskInputs:
    """Values known at the signal bar's close, used to place exits once the entry has filled."""

    atr: dict[int, float]  # Wilder ATR by period, for ATR-based stops/targets/trails
    lowest_low: float  # over the structure lookback (NaN when not needed)
    highest_high: float
    close: float


def stop_price(spec: StrategySpec, side: str, fill: float, r: RiskInputs, decimals: int) -> float:
    stop = spec.risk.stop_loss
    sign = 1.0 if side == "long" else -1.0
    if isinstance(stop, PercentStop):
        raw = fill * (1.0 - sign * stop.value / 100.0)
    elif isinstance(stop, AtrStop):
        raw = fill - sign * stop.multiple * r.atr[stop.atr_period]
    else:
        assert isinstance(stop, StructureStop)
        level = r.lowest_low if side == "long" else r.highest_high
        raw = level * (1.0 - sign * stop.buffer_pct / 100.0)
    return round_price(raw, decimals)


def target_price(
    spec: StrategySpec, side: str, fill: float, stop: float, r: RiskInputs, decimals: int
) -> float | None:
    target = spec.risk.take_profit
    sign = 1.0 if side == "long" else -1.0
    if target is None:
        return None
    if isinstance(target, PercentTarget):
        raw = fill * (1.0 + sign * target.value / 100.0)
    elif isinstance(target, AtrTarget):
        raw = fill + sign * target.multiple * r.atr[target.atr_period]
    else:
        assert isinstance(target, RiskRewardTarget)
        raw = fill + sign * target.multiple * abs(fill - stop)
    return round_price(raw, decimals)


def trailing_candidate(spec: StrategySpec, side: str, r: RiskInputs, decimals: int) -> float | None:
    trail = spec.risk.trailing_stop
    sign = 1.0 if side == "long" else -1.0
    if trail is None:
        return None
    if isinstance(trail, PercentTrail):
        raw = r.close * (1.0 - sign * trail.value / 100.0)
    else:
        assert isinstance(trail, AtrTrail)
        raw = r.close - sign * trail.multiple * r.atr[trail.atr_period]
    return round_price(raw, decimals)


def tighter(side: str, current: float, candidate: float | None) -> float | None:
    """The candidate if it tightens the stop, else None (trailing stops never loosen)."""
    if candidate is None:
        return None
    if (side == "long" and candidate > current) or (side == "short" and candidate < current):
        return candidate
    return None


def risk_atr_periods(spec: StrategySpec) -> list[int]:
    periods = {
        x.atr_period
        for x in (spec.risk.stop_loss, spec.risk.take_profit, spec.risk.trailing_stop)
        if isinstance(x, AtrStop | AtrTarget | AtrTrail)
    }
    return sorted(periods)


def structure_lookback(spec: StrategySpec) -> int:
    stop = spec.risk.stop_loss
    return stop.lookback if isinstance(stop, StructureStop) else 0
