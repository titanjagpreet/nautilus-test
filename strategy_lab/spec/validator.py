"""Spec validator: every problem at once, each with a JSON path and a plain message.

Errors make a spec unrunnable; warnings are advice (overfitting risk, missing data). Checks:

* structure and types (Pydantic), unknown fields, unknown indicator types/params/outputs;
* parameter bounds (e.g. RSI period 2-100), leverage ≤ 10, sizing within the leverage cap, a stop-loss present;
* references to undefined indicator ids;
* **look-ahead**: negative ``bars_ago`` (future bars), ``execution.fill_on = same_bar_close`` combined with
  current-bar values, ``execution.htf_bars = forming``;
* **higher-timeframe misuse**: indicator timeframe below the base timeframe, crosses on HTF series;
* **contradictory rules** that can never be true (impossible constant comparisons, empty intervals, oscillators
  outside their range, ``close > donchian.upper`` on the same bar, x crossing itself, ...);
* overfitting warning when more than 6 parameters are tunable.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from strategy_lab.costs import MAX_SLIPPAGE_TICKS, fee_profiles
from strategy_lab.spec.indicators import CATALOGUE, resolved_source, warmup_bars
from strategy_lab.spec.params import tunable_parameters
from strategy_lab.spec.schema import (
    AllOf,
    AnyOf,
    AtrStop,
    AtrTarget,
    AtrTrail,
    Between,
    Compare,
    Condition,
    ConstOperand,
    Cross,
    FixedUsd,
    IndicatorOperand,
    InputOperand,
    Not,
    Operand,
    PercentEquity,
    PercentStop,
    PercentTarget,
    PercentTrail,
    RiskRewardTarget,
    StrategySpec,
    StructureStop,
)

TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
MAX_LEVERAGE = 10.0
MAX_BARS_AGO = 500
MAX_TUNABLE = 6


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message} [{self.code}]"


@dataclass(frozen=True)
class ValidationContext:
    """What the data behind a run can supply. ``None`` = unknown (only warn)."""

    has_volume: bool | None = None
    has_funding: bool | None = None


@dataclass
class ValidationResult:
    spec: StrategySpec | None
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.spec is not None


def _pydantic_path(loc: tuple[int | str, ...]) -> str:
    path = "$"
    for part in loc:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _clean_loc(loc: tuple[int | str, ...]) -> tuple[int | str, ...]:
    """Drop Pydantic's union-branch tags (e.g. 'Compare', 'function-after[...]') from error locations."""
    return tuple(p for p in loc if isinstance(p, int) or (p[:1].islower() and "[" not in p) or p in {"op"})


def parse(data: dict[str, Any] | str) -> ValidationResult:
    try:
        spec = (
            StrategySpec.model_validate_json(data) if isinstance(data, str) else StrategySpec.model_validate(data)
        )
    except ValidationError as exc:
        seen: set[tuple[str, str]] = set()
        issues = []
        for err in exc.errors(include_url=False):
            path = _pydantic_path(_clean_loc(tuple(err["loc"])))
            key = (path, err["msg"])
            if key not in seen:
                seen.add(key)
                issues.append(Issue("SCHEMA", path, err["msg"]))
        return ValidationResult(None, issues)
    return ValidationResult(spec)


def validate(
    data: dict[str, Any] | str | StrategySpec, context: ValidationContext | None = None
) -> ValidationResult:
    result = ValidationResult(data) if isinstance(data, StrategySpec) else parse(data)
    if result.spec is None:
        return result
    checker = _Checker(result.spec, context or ValidationContext())
    checker.run()
    result.errors, result.warnings = checker.errors, checker.warnings
    return result


# --- condition traversal ------------------------------------------------------------------------------


def walk_conditions(cond: Condition, path: str) -> Iterator[tuple[Condition, str]]:
    yield cond, path
    if isinstance(cond, AllOf | AnyOf):
        for i, arg in enumerate(cond.args):
            yield from walk_conditions(arg, f"{path}.args[{i}]")
    elif isinstance(cond, Not):
        yield from walk_conditions(cond.arg, f"{path}.arg")


def condition_operands(cond: Condition, path: str) -> Iterator[tuple[Operand, str]]:
    if isinstance(cond, Compare | Cross):
        yield cond.left, f"{path}.left"
        yield cond.right, f"{path}.right"
    elif isinstance(cond, Between):
        yield cond.value, f"{path}.value"
        yield cond.low, f"{path}.low"
        yield cond.high, f"{path}.high"


RULE_NAMES = ("entry_long", "exit_long", "entry_short", "exit_short")


class _Checker:
    def __init__(self, spec: StrategySpec, context: ValidationContext) -> None:
        self.spec = spec
        self.context = context
        self.errors: list[Issue] = []
        self.warnings: list[Issue] = []
        self.indicators = {ind.id: ind for ind in spec.indicators}

    def error(self, code: str, path: str, message: str) -> None:
        self.errors.append(Issue(code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(Issue(code, path, message))

    def run(self) -> None:
        self._indicators()
        self._rules()
        self._risk()
        self._costs()
        self._execution()
        self._overfitting()

    # -- indicators ------------------------------------------------------------------------------------

    def _indicators(self) -> None:
        base = TIMEFRAME_MINUTES[self.spec.market.timeframe]
        seen: set[str] = set()
        for i, ind in enumerate(self.spec.indicators):
            path = f"$.indicators[{i}]"
            if ind.id in seen:
                self.error("DUPLICATE_ID", f"{path}.id", f"indicator id {ind.id!r} is used more than once")
            seen.add(ind.id)
            definition = CATALOGUE[ind.type]
            for name, value in ind.params.items():
                spec = definition.param_spec(name)
                if spec is None:
                    known = ", ".join(p.name for p in definition.params) or "none"
                    self.error(
                        "UNKNOWN_PARAM",
                        f"{path}.params.{name}",
                        f"{ind.type} has no parameter {name!r} (parameters: {known})",
                    )
                    continue
                if spec.integer and value != int(value):
                    self.error("PARAM_NOT_INTEGER", f"{path}.params.{name}", f"{name} must be a whole number")
                if not spec.low <= value <= spec.high:
                    self.error(
                        "PARAM_OUT_OF_RANGE",
                        f"{path}.params.{name}",
                        f"{ind.type} {name} must be between {spec.low:g} and {spec.high:g}, got {value:g}",
                    )
            if ind.type == "macd":
                fast = ind.params.get("fast", 12)
                slow = ind.params.get("slow", 26)
                if slow <= fast:
                    self.error("PARAM_CONFLICT", f"{path}.params.slow", "MACD slow period must exceed fast")
            if definition.default_source is None and ind.source is not None:
                self.error(
                    "SOURCE_NOT_ALLOWED",
                    f"{path}.source",
                    f"{ind.type} is computed from high/low/close; 'source' must be omitted",
                )
            if definition.uses_volume or resolved_source(ind.type, ind.source) == "volume":
                self._volume_check(f"{path}.type", ind.type)
            if ind.timeframe is not None:
                tf = TIMEFRAME_MINUTES[ind.timeframe]
                if tf < base:
                    self.error(
                        "HTF_BELOW_BASE",
                        f"{path}.timeframe",
                        f"indicator timeframe {ind.timeframe} is lower than the strategy timeframe "
                        f"{self.spec.market.timeframe}; signals are only evaluated on "
                        f"{self.spec.market.timeframe} closes",
                    )
                elif tf % base:
                    self.error(
                        "HTF_NOT_MULTIPLE",
                        f"{path}.timeframe",
                        f"{ind.timeframe} is not a multiple of {self.spec.market.timeframe}",
                    )
            if warmup_bars(ind.type, ind.params) > 1000:
                self.warn(
                    "LONG_WARMUP", path, f"{ind.id} needs {warmup_bars(ind.type, ind.params)} bars of history"
                )

    def _volume_check(self, path: str, what: str) -> None:
        if self.context.has_volume is False:
            self.error("NO_VOLUME_DATA", path, f"{what} needs volume, but this market's data has no volume")
        elif self.spec.market.symbol == "XAU-PERP" and self.context.has_volume is None:
            self.warn(
                "VOLUME_MAYBE_MISSING", path, f"{what} needs volume; the XAU history used here (HistData) has none"
            )

    # -- rules -----------------------------------------------------------------------------------------

    def _rules(self) -> None:
        rules = self.spec.rules
        direction = self.spec.market.direction
        needs = {"long": ["entry_long"], "short": ["entry_short"], "both": ["entry_long", "entry_short"]}[
            direction
        ]
        for name in needs:
            if getattr(rules, name) is None:
                self.error("MISSING_ENTRY", f"$.rules.{name}", f"direction is {direction!r} but {name} is empty")
        unused = {"long": ["entry_short", "exit_short"], "short": ["entry_long", "exit_long"], "both": []}[
            direction
        ]
        for name in unused:
            if getattr(rules, name) is not None:
                self.warn("UNUSED_RULE", f"$.rules.{name}", f"ignored because direction is {direction!r}")
        for name in RULE_NAMES:
            cond = getattr(rules, name)
            if cond is None:
                continue
            path = f"$.rules.{name}"
            for node, node_path in walk_conditions(cond, path):
                for operand, op_path in condition_operands(node, node_path):
                    self._operand(operand, op_path)
                if isinstance(node, Cross):
                    self._cross(node, node_path)
            if name.startswith("entry"):
                for reason, where in contradictions(cond, path, self.indicators):
                    self.error("CONTRADICTORY_RULE", where, f"{name} can never be true: {reason}")

    def _operand(self, operand: Operand, path: str) -> None:
        if isinstance(operand, ConstOperand):
            return
        if operand.bars_ago < 0:
            self.error(
                "LOOKAHEAD_FUTURE_BAR",
                f"{path}.bars_ago",
                "bars_ago must be ≥ 0; a negative value reads bars that have not happened yet",
            )
        elif operand.bars_ago > MAX_BARS_AGO:
            self.error("BARS_AGO_TOO_LARGE", f"{path}.bars_ago", f"bars_ago must be ≤ {MAX_BARS_AGO}")
        if isinstance(operand, InputOperand):
            if operand.input == "volume":
                self._volume_check(f"{path}.input", "the volume input")
            no_funding = self.context.has_funding is False or (
                self.context.has_funding is None and self.spec.market.symbol == "XAU-PERP"
            )
            if operand.input == "funding_rate" and no_funding:
                self.error("NO_FUNDING_DATA", f"{path}.input", "no funding-rate history for this market")
            return
        ind = self.indicators.get(operand.indicator)
        if ind is None:
            known = ", ".join(sorted(self.indicators)) or "none defined"
            self.error(
                "UNDEFINED_INDICATOR",
                f"{path}.indicator",
                f"unknown indicator id {operand.indicator!r} (defined: {known})",
            )
            return
        outputs = CATALOGUE[ind.type].outputs
        if operand.output is not None and operand.output not in outputs:
            self.error(
                "UNKNOWN_OUTPUT",
                f"{path}.output",
                f"{ind.type} has outputs {', '.join(outputs)}; got {operand.output!r}",
            )

    def _cross(self, node: Cross, path: str) -> None:
        for side, operand in (("left", node.left), ("right", node.right)):
            if isinstance(operand, IndicatorOperand):
                ind = self.indicators.get(operand.indicator)
                if ind is not None and ind.timeframe not in (None, self.spec.market.timeframe):
                    self.error(
                        "HTF_CROSS",
                        f"{path}.{side}",
                        f"{node.op} on the {ind.timeframe} series {ind.id!r} would stay true on every "
                        f"{self.spec.market.timeframe} bar until the next {ind.timeframe} bar; compare "
                        "levels instead (e.g. close > htf_ema)",
                    )

    # -- risk ------------------------------------------------------------------------------------------

    def _bound(self, value: float, low: float, high: float, path: str, what: str) -> None:
        if not low <= value <= high:
            self.error("OUT_OF_RANGE", path, f"{what} must be between {low:g} and {high:g}, got {value:g}")

    def _risk(self) -> None:
        risk = self.spec.risk
        if not 0 < risk.leverage <= MAX_LEVERAGE:
            self.error(
                "LEVERAGE",
                "$.risk.leverage",
                f"leverage must be > 0 and ≤ {MAX_LEVERAGE:g}x, got {risk.leverage:g}x",
            )
        sizing = risk.position_sizing
        if isinstance(sizing, PercentEquity):
            cap = 100.0 * min(risk.leverage, MAX_LEVERAGE)
            if not 0 < sizing.value <= cap:
                self.error(
                    "SIZING",
                    "$.risk.position_sizing.value",
                    f"percent of equity must be > 0 and ≤ {cap:g} (leverage cap {risk.leverage:g}x)",
                )
        elif isinstance(sizing, FixedUsd):
            self._bound(sizing.value, 10.0, 10_000_000.0, "$.risk.position_sizing.value", "fixed notional (USD)")
        stop = risk.stop_loss
        if stop is None:
            self.error("MISSING_STOP", "$.risk.stop_loss", "a stop-loss is required")
        elif isinstance(stop, PercentStop):
            self._bound(stop.value, 0.05, 50.0, "$.risk.stop_loss.value", "stop distance (%)")
        elif isinstance(stop, AtrStop):
            self._bound(stop.multiple, 0.2, 20.0, "$.risk.stop_loss.multiple", "ATR multiple")
            self._bound(stop.atr_period, 2, 200, "$.risk.stop_loss.atr_period", "ATR period")
        elif isinstance(stop, StructureStop):
            self._bound(stop.lookback, 2, 500, "$.risk.stop_loss.lookback", "structure lookback")
            self._bound(stop.buffer_pct, 0.0, 10.0, "$.risk.stop_loss.buffer_pct", "buffer (%)")
        target = risk.take_profit
        if isinstance(target, PercentTarget):
            self._bound(target.value, 0.05, 500.0, "$.risk.take_profit.value", "target distance (%)")
        elif isinstance(target, AtrTarget):
            self._bound(target.multiple, 0.2, 50.0, "$.risk.take_profit.multiple", "ATR multiple")
            self._bound(target.atr_period, 2, 200, "$.risk.take_profit.atr_period", "ATR period")
        elif isinstance(target, RiskRewardTarget):
            self._bound(target.multiple, 0.2, 20.0, "$.risk.take_profit.multiple", "reward-to-risk multiple")
        trail = risk.trailing_stop
        if isinstance(trail, PercentTrail):
            self._bound(trail.value, 0.05, 50.0, "$.risk.trailing_stop.value", "trailing distance (%)")
        elif isinstance(trail, AtrTrail):
            self._bound(trail.multiple, 0.2, 20.0, "$.risk.trailing_stop.multiple", "ATR multiple")
            self._bound(trail.atr_period, 2, 200, "$.risk.trailing_stop.atr_period", "ATR period")
        if risk.time_exit_bars is not None:
            self._bound(risk.time_exit_bars, 1, 10_000, "$.risk.time_exit_bars", "time exit (bars)")
        self._bound(risk.cooldown_bars, 0, 1_000, "$.risk.cooldown_bars", "cooldown (bars)")
        if risk.max_trades_per_day is not None:
            self._bound(risk.max_trades_per_day, 1, 100, "$.risk.max_trades_per_day", "max trades per day")

    def _costs(self) -> None:
        costs = self.spec.costs
        if costs.fee_profile not in fee_profiles():
            self.error(
                "UNKNOWN_FEE_PROFILE",
                "$.costs.fee_profile",
                f"unknown fee profile {costs.fee_profile!r}; known: {', '.join(sorted(fee_profiles()))}",
            )
        if not 0 <= costs.slippage_ticks <= MAX_SLIPPAGE_TICKS:
            self.error(
                "SLIPPAGE",
                "$.costs.slippage_ticks",
                f"slippage_ticks must be 0 or {MAX_SLIPPAGE_TICKS} (NautilusTrader's fill model moves a fill "
                "by at most one tick)",
            )
        if costs.funding and self.context.has_funding is False:
            self.warn(
                "NO_FUNDING_DATA", "$.costs.funding", "funding is on but no funding history exists; 0 is used"
            )

    def _execution(self) -> None:
        execution = self.spec.execution
        if execution.htf_bars == "forming":
            self.error(
                "LOOKAHEAD_FORMING_HTF",
                "$.execution.htf_bars",
                "higher-timeframe values must come from completed bars; a still-forming bar uses prices "
                "from the future",
            )
        if execution.fill_on == "same_bar_close":
            current = [
                p
                for name in RULE_NAMES
                if (c := getattr(self.spec.rules, name)) is not None
                for node, np_ in walk_conditions(c, f"$.rules.{name}")
                for o, p in condition_operands(node, np_)
                if not isinstance(o, ConstOperand) and o.bars_ago == 0
            ]
            if current:
                self.error(
                    "LOOKAHEAD_SAME_BAR",
                    "$.execution.fill_on",
                    f"rules read the current bar's values (e.g. {current[0]}) but would fill at that same "
                    "bar's close — a price that was already used to decide; fill on the next bar's open",
                )
            else:
                self.error(
                    "UNSUPPORTED_EXECUTION", "$.execution.fill_on", "only next_bar_open fills are supported"
                )

    def _overfitting(self) -> None:
        params = tunable_parameters(self.spec)
        if len(params) > MAX_TUNABLE:
            names = ", ".join(p.name for p in params)
            self.warn(
                "OVERFITTING_RISK",
                "$",
                f"{len(params)} tunable parameters (> {MAX_TUNABLE}): {names}. "
                "Every extra knob makes a good backtest more likely to be luck.",
            )


# --- contradiction analysis ----------------------------------------------------------------------------

_INF = float("inf")


def _key(operand: Operand) -> tuple[str, ...] | None:
    if isinstance(operand, IndicatorOperand):
        return ("ind", operand.indicator, operand.output or "", str(operand.bars_ago))
    if isinstance(operand, InputOperand):
        return ("in", operand.input, str(operand.bars_ago))
    return None


def _range(operand: Operand, indicators: dict[str, Any]) -> tuple[float, float]:
    if isinstance(operand, InputOperand) and operand.input == "hour_utc":
        return (0.0, 23.0)
    if isinstance(operand, IndicatorOperand) and operand.indicator in indicators:
        definition = CATALOGUE[indicators[operand.indicator].type]
        if definition.value_range:
            return definition.value_range
    return (-_INF, _INF)


def _dominated(left: Operand, right: Operand, op: str, indicators: dict[str, Any]) -> str | None:
    """Same-bar relationships that hold by construction (price ≤ channel upper, etc.)."""
    if not (isinstance(left, InputOperand) and isinstance(right, IndicatorOperand)):
        return None
    ind = indicators.get(right.indicator)
    if ind is None or ind.timeframe is not None or left.bars_ago != right.bars_ago:
        return None
    output = right.output or CATALOGUE[ind.type].main_output
    above = {"open", "high", "low", "close", "hl2", "hlc3", "ohlc4"}
    if (
        op in {">"}
        and left.input in above
        and (
            (ind.type == "donchian" and output == "upper")
            or (ind.type == "highest" and resolved_source("highest", ind.source) == "high")
        )
    ):
        return f"{left.input} can never exceed {ind.id}.{output}, which already includes this bar's high"
    if (
        op in {"<"}
        and left.input in above
        and (
            (ind.type == "donchian" and output == "lower")
            or (ind.type == "lowest" and resolved_source("lowest", ind.source) == "low")
        )
    ):
        return f"{left.input} can never go below {ind.id}.{output}, which already includes this bar's low"
    return None


def contradictions(cond: Condition, path: str, indicators: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (reason, path) for sub-conditions that can never be true, plus empty intervals inside ``all``."""
    found: list[tuple[str, str]] = []
    for node, node_path in walk_conditions(cond, path):
        if isinstance(node, Compare):
            reason = _compare_never(node, indicators)
            if reason:
                found.append((reason, node_path))
        elif isinstance(node, Cross) and _key(node.left) is not None and _key(node.left) == _key(node.right):
            found.append(("a series cannot cross itself", node_path))
        elif isinstance(node, Between):
            lo, hi = node.low, node.high
            if isinstance(lo, ConstOperand) and isinstance(hi, ConstOperand) and lo.value > hi.value:
                found.append((f"between needs low ≤ high, got {lo.value:g} > {hi.value:g}", node_path))
        elif isinstance(node, AllOf):
            reason = _empty_interval(node, indicators)
            if reason:
                found.append((reason, node_path))
    return found


def _compare_never(node: Compare, indicators: dict[str, Any]) -> str | None:
    left, right, op = node.left, node.right, node.op
    if isinstance(left, ConstOperand) and isinstance(right, ConstOperand):
        holds = {
            ">": left.value > right.value,
            "<": left.value < right.value,
            ">=": left.value >= right.value,
            "<=": left.value <= right.value,
        }[op]
        return None if holds else f"{left.value:g} {op} {right.value:g} is always false"
    if _key(left) is not None and _key(left) == _key(right) and op in {">", "<"}:
        return "a value is never strictly greater or smaller than itself"
    for value_side, const_side, flipped in ((left, right, False), (right, left, True)):
        if isinstance(const_side, ConstOperand) and not isinstance(value_side, ConstOperand):
            low, high = _range(value_side, indicators)
            c = const_side.value
            effective = {">": "<", "<": ">", ">=": "<=", "<=": ">="}[op] if flipped else op
            if (
                (effective == ">" and c >= high)
                or (effective == ">=" and c > high)
                or (effective == "<" and c <= low)
                or (effective == "<=" and c < low)
            ):
                return f"the value is bounded to [{low:g}, {high:g}] so '{effective} {c:g}' is impossible"
    return _dominated(left, right, op, indicators)


def _empty_interval(node: AllOf, indicators: dict[str, Any]) -> str | None:
    """Intersect constant bounds on the same operand inside one ``all``; strictness is tracked exactly."""
    bounds: dict[tuple[str, ...], list[Any]] = {}  # key -> [low, low_strict, high, high_strict]
    for arg in node.args:
        if not isinstance(arg, Compare):
            continue
        for value_side, const_side, flipped in ((arg.left, arg.right, False), (arg.right, arg.left, True)):
            key = _key(value_side)
            if key is None or not isinstance(const_side, ConstOperand):
                continue
            op = {">": "<", "<": ">", ">=": "<=", "<=": ">="}[arg.op] if flipped else arg.op
            low, high = _range(value_side, indicators)
            b = bounds.setdefault(key, [low, False, high, False])
            c = const_side.value
            if op in {">", ">="} and (c > b[0] or (c == b[0] and op == ">")):
                b[0], b[1] = c, op == ">"
            if op in {"<", "<="} and (c < b[2] or (c == b[2] and op == "<")):
                b[2], b[3] = c, op == "<"
            if b[0] > b[2] or (b[0] == b[2] and (b[1] or b[3])):
                return f"{'.'.join(k for k in key[1:3] if k)} cannot be both above and below the given limits"
    return None
