"""Structural difference between two specs, one line per change (``$.risk.leverage: 3 → 2``).

Indicators are matched by id, so adding one reads as one added line rather than a changed list.
"""

from __future__ import annotations

import json
from typing import Any

from strategy_lab.spec.schema import StrategySpec


def _show(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return json.dumps(value, ensure_ascii=False)


def _kind(node: dict[str, Any]) -> Any:
    return node.get("op", node.get("type"))


def _by_id(items: list[Any]) -> dict[str, Any] | None:
    if all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in items):
        return {x["id"]: x for x in items}
    return None


def _walk(a: Any, b: Any, path: str, out: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict) and _kind(a) == _kind(b):
        for key in [*a, *(k for k in b if k not in a)]:
            _walk(a.get(key), b.get(key), f"{path}.{key}", out)
    elif isinstance(a, list) and isinstance(b, list):
        old, new = _by_id(a), _by_id(b)
        if old is not None and new is not None:
            for key in [k for k in old if k not in new]:
                out.append(f"{path}[{key}]: removed")
            for key in [k for k in new if k not in old]:
                out.append(f"{path}[{key}]: added {_show(new[key])}")
            for key in [k for k in old if k in new]:
                _walk(old[key], new[key], f"{path}[{key}]", out)
        elif len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b, strict=True)):
                _walk(x, y, f"{path}[{i}]", out)
        else:
            out.append(f"{path}: {_show(a)} → {_show(b)}")
    elif a != b:
        out.append(f"{path}: {_show(a)} → {_show(b)}")


def spec_diff(old: StrategySpec, new: StrategySpec) -> list[str]:
    out: list[str] = []
    _walk(old.model_dump(mode="json"), new.model_dump(mode="json"), "$", out)
    return out
