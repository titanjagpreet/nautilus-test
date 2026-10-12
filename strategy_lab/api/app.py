"""FastAPI app: JSON API under ``/api``, server-rendered pages (Jinja2 + HTMX) at ``/``.

    make ui        # = uv run uvicorn strategy_lab.api.app:app --port 8000

Backtests and lab runs are background jobs (worker processes); the AI routes call the LLM synchronously.
Backtest only: nothing here can place an order or talk to an exchange.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from strategy_lab.ai.config import llm_config
from strategy_lab.ai.ledger import Ledger
from strategy_lab.api import pages, services
from strategy_lab.api.actions import (
    BacktestRequest,
    EditRequest,
    ExplainRequest,
    GenerateRequest,
    LabRequest,
    PineRequest,
    SpecBody,
    run_ai,
    state,
    submit_backtest,
    submit_lab,
    valid_spec,
)
from strategy_lab.api.jobs import JobQueue
from strategy_lab.api.store import Store
from strategy_lab.ui import STATIC_DIR


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    state.store = Store()
    state.store.fail_interrupted_jobs()
    state.queue = JobQueue(state.store)
    yield
    state.queue.shutdown()


# --- the app ---------------------------------------------------------------------------------------------

app = FastAPI(title="Strategy Lab", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/data/coverage")
def data_coverage() -> dict[str, Any]:
    return services.coverage()


@app.get("/api/specs")
def list_specs() -> list[dict[str, Any]]:
    return services.library(state.store)


@app.get("/api/specs/{ref}")
def get_spec(ref: str) -> dict[str, Any]:
    data = services.load_ref(state.store, ref)
    if data is None:
        raise HTTPException(404, detail=f"no spec {ref!r}")
    return data


@app.post("/api/specs")
def save_spec(body: SpecBody) -> dict[str, Any]:
    spec = valid_spec(body.spec)
    return {"ref": f"saved:{state.store.save_spec(spec.model_dump(mode='json'))}"}


@app.post("/api/specs/validate")
def validate_spec(body: SpecBody) -> dict[str, Any]:
    return services.check(body.spec)


@app.post("/api/specs/render")
def render_spec(body: SpecBody) -> dict[str, Any]:
    return {"text": services.check(body.spec)["rendered"]}


@app.get("/api/ai/providers")
def ai_providers() -> list[dict[str, Any]]:
    return services.providers()


@app.post("/api/ai/generate")
def ai_generate(body: GenerateRequest) -> dict[str, Any]:
    return run_ai(body.provider, "generate", idea=body.idea, answers=body.answers)


@app.post("/api/ai/edit")
def ai_edit(body: EditRequest) -> dict[str, Any]:
    return run_ai(body.provider, "edit", spec=valid_spec(body.spec), request=body.request)


@app.post("/api/ai/explain")
def ai_explain(body: ExplainRequest) -> dict[str, Any]:
    return run_ai(body.provider, "explain", spec=valid_spec(body.spec))


@app.post("/api/ai/from_pine")
def ai_from_pine(body: PineRequest) -> dict[str, Any]:
    return run_ai(body.provider, "from_pine", code=body.code)


@app.post("/api/backtests", status_code=202)
def create_backtest(body: BacktestRequest) -> dict[str, int]:
    return {"job_id": submit_backtest(body)}


@app.get("/api/backtests")
def list_backtests() -> list[dict[str, Any]]:
    return state.store.backtests()


@app.get("/api/backtests/{backtest_id}")
def get_backtest(backtest_id: int) -> dict[str, Any]:
    row = state.store.backtest(backtest_id)
    if row is None:
        raise HTTPException(404, detail=f"no backtest {backtest_id}")
    return row


@app.post("/api/lab", status_code=202)
def create_lab(body: LabRequest) -> dict[str, int]:
    return {"job_id": submit_lab(body)}


@app.get("/api/lab")
def list_lab_reports() -> list[dict[str, Any]]:
    return state.store.lab_reports()


@app.get("/api/lab/{report_id}")
def get_lab_report(report_id: int) -> dict[str, Any]:
    row = state.store.lab_report(report_id)
    if row is None:
        raise HTTPException(404, detail=f"no lab report {report_id}")
    return row


@app.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    return state.store.jobs()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int) -> dict[str, Any]:
    job = state.store.job(job_id)
    if job is None:
        raise HTTPException(404, detail=f"no job {job_id}")
    return job


@app.get("/api/costs")
def costs() -> dict[str, Any]:
    ledger = Ledger()
    budget = llm_config().budget_usd
    return {
        "budget": {"total": budget.total, "eval": budget.eval},
        "spent": {"total": ledger.spent(), "eval": ledger.spent("eval")},
        "by": ledger.summary(),
        "recent": ledger.calls(50),
        "prices_checked": llm_config().prices_checked.isoformat(),
        "providers": services.providers(),
        "fee_profiles": services.fees(),
    }


app.include_router(pages.router)
