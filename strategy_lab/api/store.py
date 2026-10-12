"""SQLite persistence for the API: saved specs, background jobs, backtest results and lab reports.

Every result row keeps the spec it ran, the data range and source, and the engine with its version, so a
result can always be traced back and re-run. The file is shared with the LLM spend ledger
(``config.state_db_path()``); the job worker process writes to it too (SQLite handles the locking).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from strategy_lab.config import state_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS specs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, name TEXT NOT NULL, author TEXT NOT NULL,
    market TEXT NOT NULL, spec_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT '', progress REAL NOT NULL DEFAULT 0, request_json TEXT NOT NULL,
    result_id INTEGER, error TEXT, started TEXT, finished TEXT
);
CREATE TABLE IF NOT EXISTS backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, job_id INTEGER, spec_name TEXT NOT NULL,
    market TEXT NOT NULL, engine TEXT NOT NULL, engine_version TEXT NOT NULL, source TEXT NOT NULL,
    funding_source TEXT, start_ts TEXT NOT NULL, end_ts TEXT NOT NULL, spec_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL, result_json TEXT NOT NULL, wall_s REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, job_id INTEGER, spec_name TEXT NOT NULL,
    market TEXT NOT NULL, engine_version TEXT NOT NULL, start_ts TEXT NOT NULL, end_ts TEXT NOT NULL,
    score REAL NOT NULL, spec_json TEXT NOT NULL, report_json TEXT NOT NULL
);
"""


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or state_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def _insert(self, table: str, row: dict[str, Any]) -> int:
        columns = ", ".join(row)
        marks = ", ".join("?" * len(row))
        with self._db() as db:
            cursor = db.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(row.values()))
            assert cursor.lastrowid is not None
            return cursor.lastrowid

    def _one(self, query: str, *args: Any) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(query, args).fetchone()
        return dict(row) if row else None

    def _all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        with self._db() as db:
            return [dict(r) for r in db.execute(query, args).fetchall()]

    # -- specs -----------------------------------------------------------------------------------------

    def save_spec(self, spec: dict[str, Any]) -> int:
        row = {
            "created": now(),
            "name": spec["meta"]["name"],
            "author": spec["meta"].get("author", "user"),
            "market": spec["market"]["symbol"],
            "spec_json": json.dumps(spec),
        }
        return self._insert("specs", row)

    def spec(self, spec_id: int) -> dict[str, Any] | None:
        row = self._one("SELECT spec_json FROM specs WHERE id = ?", spec_id)
        return json.loads(row["spec_json"]) if row else None

    def specs(self) -> list[dict[str, Any]]:
        return self._all("SELECT id, created, name, author, market FROM specs ORDER BY id DESC")

    # -- jobs ------------------------------------------------------------------------------------------

    def create_job(self, kind: str, request: dict[str, Any]) -> int:
        row = {"created": now(), "kind": kind, "status": "queued", "request_json": json.dumps(request)}
        return self._insert("jobs", row)

    def job(self, job_id: int) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM jobs WHERE id = ?", job_id)
        if row:
            row["request"] = json.loads(row.pop("request_json"))
        return row

    def jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._all(
            "SELECT id, created, kind, status, stage, progress, result_id, error FROM jobs ORDER BY id DESC "
            "LIMIT ?",
            limit,
        )

    def update_job(self, job_id: int, **fields: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._db() as db:
            db.execute(f"UPDATE jobs SET {sets} WHERE id = ?", [*fields.values(), job_id])

    def fail_interrupted_jobs(self) -> int:
        """Jobs left queued or running by a previous server process can never finish."""
        with self._db() as db:
            cursor = db.execute(
                "UPDATE jobs SET status = 'failed', error = 'interrupted: the server was restarted', finished = ? "
                "WHERE status IN ('queued', 'running')",
                (now(),),
            )
            return cursor.rowcount

    # -- results ---------------------------------------------------------------------------------------

    def save_backtest(self, row: dict[str, Any]) -> int:
        return self._insert("backtests", {"created": now(), **row})

    def backtest(self, backtest_id: int) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM backtests WHERE id = ?", backtest_id)
        if row:
            for key in ("spec_json", "metrics_json", "result_json"):
                row[key.removesuffix("_json")] = json.loads(row.pop(key))
        return row

    def backtests(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT id, created, spec_name, market, engine, engine_version, source, start_ts, end_ts, "
            "metrics_json, wall_s FROM backtests ORDER BY id DESC LIMIT ?",
            limit,
        )
        for row in rows:
            row["metrics"] = json.loads(row.pop("metrics_json"))
        return rows

    def save_lab_report(self, row: dict[str, Any]) -> int:
        return self._insert("lab_reports", {"created": now(), **row})

    def lab_report(self, report_id: int) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM lab_reports WHERE id = ?", report_id)
        if row:
            row["spec"] = json.loads(row.pop("spec_json"))
            row["report"] = json.loads(row.pop("report_json"))
        return row

    def lab_reports(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._all(
            "SELECT id, created, spec_name, market, engine_version, start_ts, end_ts, score FROM lab_reports "
            "ORDER BY id DESC LIMIT ?",
            limit,
        )
