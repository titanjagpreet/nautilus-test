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
            {
                "source": f"{s}/{y}",
                "first": table[(s, y)][0].isoformat(),
                "last": table[(s, y)][1].isoformat(),
                "rows": table[(s, y)][2],
                "used": i == 0,
            }
            for i, (s, y) in enumerate([o for o in options if o in table])
        ]

    markets = {
        m: {"bars": describe(bars, BAR_SOURCES[m]), "funding": describe(funding, FUNDING_SOURCES[m])}
        for m in BAR_SOURCES
    }
    return {"markets": markets}


def default_range(market: str) -> tuple[str, str]:
    """A sensible backtest window: the last three whole years of the market's primary source, ending where its
    funding history ends too (so every month carries funding costs)."""
    info = coverage().get("markets", {}).get(market, {})
    bars, funding = info.get("bars", []), info.get("funding", [])
    if not bars:
        return "2024-01-01", "2025-01-01"
    last = min(dt.date.fromisoformat(src[0]["last"][:10]) for src in (bars, funding) if src)
    end = dt.date(last.year, last.month, 1)
    first = dt.date.fromisoformat(bars[0]["first"][:10])
    start = max(dt.date(end.year - 3, end.month, 1), dt.date(first.year, first.month, 1))
    return start.isoformat(), end.isoformat()


def library(store: Store) -> list[dict[str, Any]]:
    """Catalogue templates and saved specs, as select options (``ref`` = "cat:<stem>" or "saved:<id>")."""
    out = []
    for path in sorted(CATALOGUE_DIR.glob("*.json")):
        data = json.loads(path.read_text())
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
        return json.loads(path.read_text()) if path.parent == CATALOGUE_DIR and path.exists() else None
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
