"""Background job queue: backtests and lab runs execute in worker processes, two at a time.

Separate processes keep NautilusTrader (its Rust runtime, ~1 GB per run) and the CPU-heavy lab out of the web
server. Jobs are rows in the store; the browser polls ``GET /api/jobs/{id}`` for stage and progress. A worker
crash marks its job failed instead of leaving it "running".
"""

from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import Future, ProcessPoolExecutor
from typing import Any

from strategy_lab.api.store import Store, now
from strategy_lab.api.worker import run_job

MAX_WORKERS = 2


class JobQueue:
    def __init__(self, store: Store, workers: int = MAX_WORKERS) -> None:
        self.store = store
        self.workers = workers
        self._pool: ProcessPoolExecutor | None = None

    def _executor(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(self.workers, mp_context=mp.get_context("spawn"))
        return self._pool

    def submit(self, kind: str, request: dict[str, Any]) -> int:
        job_id = self.store.create_job(kind, request)
        future = self._executor().submit(run_job, job_id, str(self.store.path))
        future.add_done_callback(lambda f: self._on_done(job_id, f))
        return job_id

    def _on_done(self, job_id: int, future: Future[None]) -> None:
        error = future.exception()
        if error is not None:
            self.store.update_job(job_id, status="failed", error=f"worker crashed: {error!r}", finished=now())
            self._pool = None  # a broken pool cannot take new work; the next submit starts a fresh one

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
