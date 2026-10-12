"""What the API routes and pages share: data coverage, the spec library, validation, AI results, providers."""

from __future__ import annotations

import datetime as dt
import json
from functools import cache
from pathlib import Path
from typing import Any

from strategy_lab import config
from strategy_lab.ai.builder import DATA_CONTEXT, BuildResult
from strategy_lab.ai.config import api_key, llm_config
from strategy_lab.api.store import Store
from strategy_lab.costs import fee_profiles
from strategy_lab.data import storage
from strategy_lab.engines.inputs import BAR_SOURCES, FUNDING_SOURCES
from strategy_lab.spec.params import tunable_parameters
from strategy_lab.spec.render import render
from strategy_lab.spec.schema import StrategySpec
from strategy_lab.spec.validator import validate

CATALOGUE_DIR = Path(__file__).resolve().parent.parent / "spec" / "catalogue"


@cache
def coverage() -> dict[str, Any]:
    """Per market: every stored bar and funding source with its first/last timestamp and row count."""
    stored = storage.list_datasets()
    if not stored:
        return {"markets": {}, "note": "no data downloaded — run `make data`"}
    db = storage.duckdb_connection()
    bars = {
        (s, y): (lo, hi, n)
        for s, y, lo, hi, n in db.execute(
            "SELECT source, symbol, min(ts), max(ts), count(*) FROM bars_1m GROUP BY 1, 2"
        ).fetchall()
    }
    funding: dict[tuple[str, str], tuple[Any, Any, int]] = {}
    if storage.list_datasets(config.funding_dir()):  # the funding view exists only when funding is stored
        funding = {
            (s, y): (lo, hi, n)
            for s, y, lo, hi, n in db.execute(
                "SELECT source, symbol, min(ts), max(ts), count(*) FROM funding GROUP BY 1, 2"
            ).fetchall()
        }

    def describe(
        table: dict[tuple[str, str], tuple[Any, Any, int]], options: list[tuple[str, str]]
    ) -> list[dict[str, Any]]:
        return [
            {"source": f"{s}/{y}", "first": table[s, y][0], "last": table[s, y][1], "rows": table[s, y][2]}
            for s, y in options
            if (s, y) in table
        ]

    markets: dict[str, Any] = {}
    for m in BAR_SOURCES:
        info = {"bars": describe(bars, BAR_SOURCES[m]), "funding": describe(funding, FUNDING_SOURCES[m])}
        window = default_window(info["bars"], info["funding"])
        for kind in ("bars", "funding"):
            for src in info[kind]:
                src["used"] = window is not None and window[kind] == src["source"]
                src["first"], src["last"] = src["first"].isoformat(), src["last"].isoformat()
        markets[m] = info | {"default": window}
    return {"markets": markets}


def _month_ceil(ts: dt.datetime) -> dt.date:
    """The first whole month at or after ``ts``."""
    if (ts.day, ts.hour, ts.minute, ts.second) == (1, 0, 0, 0):
        return ts.date()
    return dt.date(ts.year + ts.month // 12, ts.month % 12 + 1, 1)


def default_window(bars: list[dict[str, Any]], funding: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last three whole years of the most preferred bar source that has them, ending where a funding series
    covering the whole window ends (so every month carries funding costs) — or, when no funding series reaches
    back three years (gold: only Lighter's, from its listing), three years without full funding: the engines then
    charge funding where it exists and label it partial. Without three years anywhere, the longest window.
    ``bars``/``funding``: sources in preference order with ``first``/``last`` timestamps. The engines pick the
    same bar source for that window (``engines.inputs``)."""
    best: dict[str, Any] | None = None
    for b in bars:
        for f in [*funding, None]:
            last = min(b["last"], f["last"]) if f else b["last"]
            end = dt.date(last.year, last.month, 1)
            full = dt.date(end.year - 3, end.month, 1)
            start = max(full, _month_ceil(b["first"]), *([_month_ceil(f["first"])] if f else []))
            if start >= end:
                continue
            window = {"start": start.isoformat(), "end": end.isoformat(), "bars": b["source"]}
            window["funding"] = f["source"] if f else None
            if start == full:
                return window
            if best is None or end - start > dt.date.fromisoformat(best["end"]) - dt.date.fromisoformat(
                best["start"]
            ):
                best = window
    return best


def default_range(market: str) -> tuple[str, str]:
    """The default backtest window for ``market`` (``default_window``); 2024 when no data is stored."""
    window = coverage().get("markets", {}).get(market, {}).get("default")
    return (window["start"], window["end"]) if window else ("2024-01-01", "2025-01-01")


def library(store: Store) -> list[dict[str, Any]]:
    """Catalogue templates and saved specs, as select options (``ref`` = "cat:<stem>" or "saved:<id>")."""
    out = []
    for path in sorted(CATALOGUE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(
            {
                "ref": f"cat:{path.stem}",
                "name": data["meta"]["name"],
                "market": data["market"]["symbol"],
                "group": "catalogue",
            }
        )
    for row in store.specs():
        out.append(
            {
                "ref": f"saved:{row['id']}",
                "name": f"#{row['id']} {row['name']}",
                "market": row["market"],
                "group": "saved",
            }
        )
    return out


def load_ref(store: Store, ref: str) -> dict[str, Any] | None:
    kind, _, key = ref.partition(":")
    if kind == "cat":
        path = CATALOGUE_DIR / f"{key}.json"
        return (
            json.loads(path.read_text(encoding="utf-8"))
            if path.parent == CATALOGUE_DIR and path.exists()
            else None
        )
    if kind == "saved" and key.isdigit():
        return store.spec(int(key))
    return None


def check(data: dict[str, Any]) -> dict[str, Any]:
    """Validation with the market's data context, the tunable parameters and the plain-language rendering."""
    symbol = data.get("market", {}).get("symbol") if isinstance(data.get("market"), dict) else None
    result = validate(data, DATA_CONTEXT.get(str(symbol)))
    out: dict[str, Any] = {
        "ok": result.ok,
        "errors": [{"code": i.code, "path": i.path, "message": i.message} for i in result.errors],
        "warnings": [{"code": i.code, "path": i.path, "message": i.message} for i in result.warnings],
        "parameters": [],
        "rendered": None,
    }
    if result.spec is not None:
        out["parameters"] = [
            {"name": p.name, "value": p.value, "low": p.low, "high": p.high, "integer": p.integer}
            for p in tunable_parameters(result.spec)
        ]
        out["rendered"] = render(result.spec)
    return out


def build_result(result: BuildResult) -> dict[str, Any]:
    return {
        "task": result.task,
        "status": result.status,
        "spec": result.spec.model_dump(mode="json") if result.spec else None,
        "rendered": render(result.spec) if result.spec else None,
        "questions": result.questions,
        "changes": result.changes,
        "diff": result.diff,
        "explanation": result.explanation,
        "unsupported": result.unsupported,
        "assumptions": result.assumptions,
        "refusal": result.refusal,
        "warnings": result.warnings,
        "errors": result.errors,
        "cost_usd": result.cost_usd,
        "latency_s": result.latency_s,
        "attempts": [
            {
                "kind": a.kind,
                "model": f"{a.provider}:{a.model}",
                "errors": a.errors,
                "cost_usd": a.usage.cost_usd if a.usage else 0.0,
                "cached_tokens": a.usage.cached_tokens if a.usage else 0,
                "latency_s": a.usage.latency_s if a.usage else 0.0,
            }
            for a in result.attempts
        ],
    }


def providers() -> list[dict[str, Any]]:
    config = llm_config()
    now = dt.datetime.now(dt.UTC)
    out = []
    for name, p in config.providers.items():
        out.append(
            {
                "name": name,
                "available": api_key(name) is not None,
                "key_env": p.key_env,
                "writer": p.writer,
                "escalation": p.escalation,
                "modes": list(p.modes),
                "data_location": p.data_location,
                "peak_now": p.is_peak(now) if p.peak_hours_utc else None,
                "next_off_peak": p.next_off_peak(now).isoformat(timespec="minutes") if p.is_peak(now) else None,
                "models": {m: price.model_dump(exclude_none=True) for m, price in p.models.items()},
                "default": name == config.default_writer,
            }
        )
    return out


def fees() -> list[dict[str, Any]]:
    return [
        {"name": f.name, "maker_bps": f.maker_bps, "taker_bps": f.taker_bps, "note": f.note}
        for f in fee_profiles().values()
    ]


def parse_spec(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """(spec dict, error) from editor text."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "the spec must be a JSON object"
    return data, None


def tunables(data: dict[str, Any]) -> list[str]:
    try:
        return [p.name for p in tunable_parameters(StrategySpec.model_validate(data))]
    except ValueError:
        return []
