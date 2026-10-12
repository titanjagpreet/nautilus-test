"""Spend ledger: every LLM call with its token usage and cost, in SQLite; budget checks before each call.

Costs are computed from the API's own usage fields (uncached, cached and cache-write prompt tokens, output
tokens) and the prices in ``config/llm.json`` at the time of the call (DeepSeek: peak or off-peak). Two limits
apply (``budget_usd``): the whole project's total and the AI eval's share (scope ``"eval"``). A structured-output
mode the API rejects (HTTP 400, unbilled) is logged too, at zero cost, with the API's reason.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from strategy_lab.ai.config import llm_config
from strategy_lab.config import state_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    scope TEXT NOT NULL,
    feature TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    mode TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_s REAL NOT NULL,
    peak INTEGER NOT NULL,
    ok INTEGER NOT NULL,
    note TEXT NOT NULL
)
"""
MODE_REJECTED = "structured-output mode rejected: "  # note prefix of a logged HTTP 400 fallback


class BudgetExceededError(RuntimeError):
    """The next call could push spending past a limit; nothing was sent."""


@dataclass(frozen=True)
class Usage:
    provider: str
    model: str
    mode: str
    input_tokens: int  # uncached prompt tokens
    cached_tokens: int  # prompt tokens read from the provider's cache
    cache_write_tokens: int  # prompt tokens written to the cache (billed extra by Anthropic)
    output_tokens: int  # includes any reasoning tokens
    cost_usd: float
    latency_s: float
    peak: bool  # DeepSeek peak-hour pricing applied

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cached_tokens + self.cache_write_tokens


class Ledger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or state_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def record(self, usage: Usage, scope: str, feature: str, ok: bool, note: str = "") -> None:
        row = asdict(usage) | {
            "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "scope": scope,
            "feature": feature,
            "ok": int(ok),
            "note": note,
            "peak": int(usage.peak),
        }
        columns = ", ".join(row)
        with self._connect() as db:
            db.execute(
                f"INSERT INTO llm_calls ({columns}) VALUES ({', '.join('?' * len(row))})", list(row.values())
            )

    def spent(self, scope: str | None = None) -> float:
        query = "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls"
        args: tuple[str, ...] = ()
        if scope is not None:
            query += " WHERE scope = ?"
            args = (scope,)
        with self._connect() as db:
            return float(db.execute(query, args).fetchone()[0])

    def ensure_budget(self, scope: str, projected: float) -> None:
        budget = llm_config().budget_usd
        total = self.spent()
        if total + projected > budget.total:
            raise BudgetExceededError(
                f"total LLM spend ${total:.4f} + this call's worst case ${projected:.4f} would exceed the project "
                f"limit ${budget.total:.2f}"
            )
        if scope == "eval":
            spent = self.spent("eval")
            if spent + projected > budget.eval:
                raise BudgetExceededError(
                    f"eval spend ${spent:.4f} + this call's worst case ${projected:.4f} would exceed the eval "
                    f"limit ${budget.eval:.2f}"
                )

    def calls(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM llm_calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def mode_rejections(self) -> list[dict[str, Any]]:
        """Structured-output modes an API rejected (the provider fell back to its next mode), with the reason."""
        with self._connect() as db:
            rows = db.execute(
                """SELECT provider, model, mode, note AS reason, COUNT(*) AS times, MAX(ts) AS last
                   FROM llm_calls WHERE note LIKE ? GROUP BY provider, model, mode, note ORDER BY last DESC""",
                (MODE_REJECTED + "%",),
            ).fetchall()
        return [dict(r) | {"reason": r["reason"].removeprefix(MODE_REJECTED)} for r in rows]

    def summary(self) -> list[dict[str, Any]]:
        """Spend per scope, provider, model, feature and structured-output mode."""
        with self._connect() as db:
            rows = db.execute(
                """SELECT scope, provider, model, feature, mode, COUNT(*) AS calls,
                          SUM(input_tokens) AS input_tokens, SUM(cached_tokens) AS cached_tokens,
                          SUM(cache_write_tokens) AS cache_write_tokens, SUM(output_tokens) AS output_tokens,
                          SUM(cost_usd) AS cost_usd, AVG(latency_s) AS mean_latency_s
                   FROM llm_calls GROUP BY scope, provider, model, feature, mode ORDER BY cost_usd DESC"""
            ).fetchall()
        return [dict(r) for r in rows]
