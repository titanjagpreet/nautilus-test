"""Turn any valid spec into readable rules (plain English, markdown bullets)."""

from __future__ import annotations

from strategy_lab.spec.indicators import CATALOGUE, resolved_params, resolved_source
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
    Indicator,
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

COMPARE_WORDS = {">": "is above", "<": "is below", ">=": "is at or above", "<=": "is at or below"}
INPUT_WORDS = {
    "open": "the open",
    "high": "the high",
    "low": "the low",
    "close": "the close",
    "volume": "the volume",
    "hl2": "the (high+low)/2 price",
    "hlc3": "the typical price",
    "ohlc4": "the OHLC average",
    "funding_rate": "the latest funding rate (per 8 h)",
    "hour_utc": "the bar's UTC hour",
}
OUTPUT_WORDS = {
    "upper": "upper band",
    "lower": "lower band",
    "middle": "middle line",
    "width": "band width",
    "line": "MACD line",
    "signal": "signal line",
    "hist": "histogram",
    "k": "%K",
    "d": "%D",
    "adx": "ADX",
    "plus_di": "+DI",
    "minus_di": "-DI",
}


def _num(value: float) -> str:
    return f"{value:g}"


def describe_indicator(ind: Indicator, base_timeframe: str) -> str:
    definition = CATALOGUE[ind.type]
    params = resolved_params(ind.type, ind.params)
    args = ", ".join(_num(v) for v in params.values())
    source = resolved_source(ind.type, ind.source)
    text = f"`{ind.id}` = {definition.label}" + (f" ({args})" if args else "")
    if source and definition.default_source is not None:
        text += f" of {INPUT_WORDS[source].removeprefix('the ')}"
    text += f" on {ind.timeframe or base_timeframe} bars"
    if ind.timeframe and ind.timeframe != base_timeframe:
        text += " (higher-timeframe filter, completed bars only)"
    return text


def _ago(bars_ago: int, unit: str) -> str:
    if bars_ago == 0:
        return ""
    return f" {bars_ago} {unit}{'s' if bars_ago > 1 else ''} ago"


def describe_operand(op: Operand, spec: StrategySpec) -> str:
    if isinstance(op, ConstOperand):
        return _num(op.value)
    if isinstance(op, InputOperand):
        return f"{INPUT_WORDS[op.input]}{_ago(op.bars_ago, 'bar')}"
    ind = next((i for i in spec.indicators if i.id == op.indicator), None)
    unit = f"{ind.timeframe} bar" if ind is not None and ind.timeframe else "bar"
    if ind is None:
        return f"`{op.indicator}` (undefined)"
    definition = CATALOGUE[ind.type]
    output = op.output or definition.main_output
    name = (
        f"`{ind.id}`" if len(definition.outputs) == 1 else f"the {OUTPUT_WORDS.get(output, output)} of `{ind.id}`"
    )
    return f"{name}{_ago(op.bars_ago, unit)}"


def describe_condition(cond: Condition, spec: StrategySpec, depth: int = 0) -> str:
    pad = "  " * depth
    if isinstance(cond, AllOf | AnyOf):
        word = "ALL" if isinstance(cond, AllOf) else "ANY"
        items = "\n".join(f"{pad}  - {describe_condition(c, spec, depth + 1).lstrip()}" for c in cond.args)
        return f"{word} of:\n{items}"
    if isinstance(cond, Not):
        return f"NOT ({describe_condition(cond.arg, spec, depth).strip()})"
    if isinstance(cond, Compare):
        return f"{describe_operand(cond.left, spec)} {COMPARE_WORDS[cond.op]} {describe_operand(cond.right, spec)}"
    if isinstance(cond, Cross):
        verb = "crosses above" if cond.op == "crosses_above" else "crosses below"
        return f"{describe_operand(cond.left, spec)} {verb} {describe_operand(cond.right, spec)}"
    assert isinstance(cond, Between)
    return (
        f"{describe_operand(cond.value, spec)} is between {describe_operand(cond.low, spec)} and "
        f"{describe_operand(cond.high, spec)}"
    )


def _risk_lines(spec: StrategySpec) -> list[str]:
    risk = spec.risk
    sizing = risk.position_sizing
    lines = []
    if isinstance(sizing, PercentEquity):
        lines.append(
            f"Position size: {_num(sizing.value)}% of account equity (notional), leverage cap "
            f"{_num(risk.leverage)}x."
        )
    elif isinstance(sizing, FixedUsd):
        lines.append(f"Position size: {_num(sizing.value)} USDC notional, leverage cap {_num(risk.leverage)}x.")
    stop = risk.stop_loss
    if isinstance(stop, PercentStop):
        lines.append(f"Stop-loss: {_num(stop.value)}% from the entry price.")
    elif isinstance(stop, AtrStop):
        lines.append(f"Stop-loss: {_num(stop.multiple)} × ATR({stop.atr_period}) from the entry price.")
    elif isinstance(stop, StructureStop):
        buffer = f", minus a {_num(stop.buffer_pct)}% buffer" if stop.buffer_pct else ""
        lines.append(
            f"Stop-loss: below the lowest low (longs) / above the highest high (shorts) of the last "
            f"{stop.lookback} bars{buffer}."
        )
    else:
        lines.append("Stop-loss: MISSING (required).")
    target = risk.take_profit
    if isinstance(target, PercentTarget):
        lines.append(f"Take-profit: {_num(target.value)}% from the entry price.")
    elif isinstance(target, AtrTarget):
        lines.append(f"Take-profit: {_num(target.multiple)} × ATR({target.atr_period}) from the entry price.")
    elif isinstance(target, RiskRewardTarget):
        lines.append(
            f"Take-profit: {_num(target.multiple)} × the stop distance (reward-to-risk {_num(target.multiple)}:1)."
        )
    else:
        lines.append("Take-profit: none (exits by rule, stop or time).")
    trail = risk.trailing_stop
    if isinstance(trail, PercentTrail):
        lines.append(f"Trailing stop: {_num(trail.value)}% behind the best close, moved only at bar close.")
    elif isinstance(trail, AtrTrail):
        lines.append(
            f"Trailing stop: {_num(trail.multiple)} × ATR({trail.atr_period}) behind the close, moved only at "
            "bar close and never loosened."
        )
    if risk.time_exit_bars:
        lines.append(f"Time exit: close the position after {risk.time_exit_bars} bars.")
    if risk.cooldown_bars:
        lines.append(f"Cooldown: wait {risk.cooldown_bars} bars after an exit before entering again.")
    if risk.max_trades_per_day:
        lines.append(f"At most {risk.max_trades_per_day} entries per UTC day.")
    return lines


def render(spec: StrategySpec) -> str:
    m = spec.market
    direction = {"long": "long only", "short": "short only", "both": "long and short"}[m.direction]
    out = [f"### {spec.meta.name}", "", f"**Market:** {m.symbol}, {m.timeframe} bars, {direction}."]
    if spec.meta.description:
        out += ["", spec.meta.description]
    if spec.indicators:
        out += ["", "**Indicators**", *[f"- {describe_indicator(i, m.timeframe)}" for i in spec.indicators]]
    out += ["", "**Rules** (checked when each bar closes; orders fill at the next bar's open)"]
    labels = {
        "entry_long": "Enter long when",
        "exit_long": "Exit long when",
        "entry_short": "Enter short when",
        "exit_short": "Exit short when",
    }
    for name, label in labels.items():
        cond = getattr(spec.rules, name)
        if cond is not None:
            out.append(f"- {label} {describe_condition(cond, spec)}")
    out += ["", "**Risk**", *[f"- {line}" for line in _risk_lines(spec)]]
    c = spec.costs
    out += [
        "",
        f"**Costs:** fee profile `{c.fee_profile}`, {c.slippage_ticks} tick slippage on market/stop fills, "
        f"funding {'charged' if c.funding else 'ignored'}.",
    ]
    return "\n".join(out)
