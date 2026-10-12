"""Tunable parameters of a spec: list them (for the overfitting warning, sweeps, Optuna) and set them."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from strategy_lab.spec.indicators import CATALOGUE, resolved_params
from strategy_lab.spec.schema import StrategySpec

PathPart = str | int


@dataclass(frozen=True)
class TunableParam:
    name: str  # human-readable, e.g. "ema_fast.period" or "stop_loss.multiple"
    path: tuple[PathPart, ...]  # location inside ``spec.model_dump()``
    value: float
    low: float
    high: float
    integer: bool


RISK_BOUNDS: dict[tuple[str, ...], tuple[float, float, bool]] = {
    ("stop_loss", "value"): (0.05, 50.0, False),
    ("stop_loss", "multiple"): (0.2, 20.0, False),
    ("stop_loss", "atr_period"): (2, 200, True),
    ("stop_loss", "lookback"): (2, 500, True),
    ("take_profit", "value"): (0.05, 500.0, False),
    ("take_profit", "multiple"): (0.2, 50.0, False),
    ("take_profit", "atr_period"): (2, 200, True),
    ("trailing_stop", "value"): (0.05, 50.0, False),
    ("trailing_stop", "multiple"): (0.2, 20.0, False),
    ("trailing_stop", "atr_period"): (2, 200, True),
    ("time_exit_bars",): (1, 10_000, True),
}


def _rule_constants(node: Any, path: tuple[PathPart, ...]) -> Iterator[tuple[tuple[PathPart, ...], float]]:
    if isinstance(node, dict):
        if set(node) == {"value"} and isinstance(node["value"], int | float):
            yield (*path, "value"), float(node["value"])  # path points at the number itself
            return
        for key, child in node.items():
            yield from _rule_constants(child, (*path, key))
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from _rule_constants(child, (*path, i))


def _path_name(rule: str, parts: tuple[PathPart, ...]) -> str:
    """('args', 0, 'right') -> 'entry_long.args[0].right'."""
    text = rule
    for part in parts:
        text += f"[{part}]" if isinstance(part, int) else f".{part}"
    return text


def tunable_parameters(spec: StrategySpec) -> list[TunableParam]:
    out: list[TunableParam] = []
    for i, ind in enumerate(spec.indicators):
        definition = CATALOGUE[ind.type]
        for name, value in resolved_params(ind.type, ind.params).items():
            p = definition.param_spec(name)
            assert p is not None
            out.append(
                TunableParam(
                    f"{ind.id}.{name}", ("indicators", i, "params", name), value, p.low, p.high, p.integer
                )
            )
    dumped = spec.model_dump()
    for (section, *field), (low, high, integer) in RISK_BOUNDS.items():
        node = dumped["risk"].get(section)
        if node is None:
            continue
        value = node.get(field[0]) if field else node
        if isinstance(value, int | float) and not isinstance(value, bool):
            path: tuple[PathPart, ...] = ("risk", section, *field)
            out.append(TunableParam(".".join([section, *field]), path, float(value), low, high, integer))
    for rule, cond in dumped["rules"].items():
        for path, value in _rule_constants(cond, ("rules", rule)):
            out.append(TunableParam(_path_name(rule, path[2:-1]), path, value, -1e12, 1e12, False))
    return out


def with_params(spec: StrategySpec, values: dict[str, float]) -> StrategySpec:
    """Return a copy of ``spec`` with tunable parameters (by ``TunableParam.name``) replaced."""
    by_name = {p.name: p for p in tunable_parameters(spec)}
    unknown = set(values) - set(by_name)
    if unknown:
        raise KeyError(f"unknown parameter(s) {sorted(unknown)}; available: {sorted(by_name)}")
    data = spec.model_dump()
    for name, value in values.items():
        param = by_name[name]
        node: Any = data
        for part in param.path[:-1]:
            node = node[part]
        node[param.path[-1]] = round(value) if param.integer else float(value)
    return StrategySpec.model_validate(data)
