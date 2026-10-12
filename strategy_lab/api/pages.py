"""Server-rendered pages (Jinja2) and the HTMX fragments they swap in: Builder, Backtest, Lab, Compare, Costs."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from strategy_lab.ai.config import llm_config
from strategy_lab.ai.ledger import Ledger
from strategy_lab.api import services
from strategy_lab.api.actions import (
    BacktestRequest,
    LabRequest,
    run_ai,
    state,
    submit_backtest,
    submit_lab,
    valid_spec,
)
from strategy_lab.ui import TEMPLATES_DIR, asset_url
from strategy_lab.ui.markdown import to_html

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["asset"] = asset_url
templates.env.filters["markdown"] = to_html


def _num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def _param(value: Any) -> str:
    """Parameter values: whole numbers without decimals, others with up to 6 significant digits."""
    return f"{value:g}" if isinstance(value, int | float) else str(value)


templates.env.filters["num"] = _num
templates.env.filters["param"] = _param

ShowId = Annotated[int | None, Query(alias="id")]  # ?id=N opens a stored result
PAGES = [
    ("/", "Builder"),
    ("/backtest", "Backtest"),
    ("/lab", "Lab"),
    ("/compare", "Compare"),
    ("/costs", "Costs"),
]


def page(request: Request, template: str, title: str, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, template, {"title": title, "pages": PAGES, **context})


def fragment(request: Request, template: str, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, template, context)


def _error(request: Request, exc: HTTPException) -> HTMLResponse:
    detail = exc.detail
    errors: list[dict[str, str]] = detail.get("errors", []) if isinstance(detail, dict) else []
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    return fragment(request, "_error.html", message=message, errors=errors)


# --- pages -----------------------------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def builder_page(request: Request) -> HTMLResponse:
    first = services.load_ref(state.store, "cat:01_ema_crossover") or {}
    providers = services.providers()
    available = [p["name"] for p in providers if p["available"]]
    default = next(p["name"] for p in providers if p["default"])
    writer = default if default in available else (available[0] if available else default)
    return page(
        request,
        "builder.html",
        "Builder",
        library=services.library(state.store),
        providers=providers,
        writer=writer,
        spec_text=json.dumps(first, indent=2),
    )


def _run_form_context(ref: str | None) -> dict[str, Any]:
    library = services.library(state.store)
    selected = ref or (library[0]["ref"] if library else None)
    spec = services.load_ref(state.store, selected) if selected else None
    market = spec["market"]["symbol"] if spec else "BTC-PERP"
    start, end = services.default_range(market)
    return {
        "library": library,
        "selected": selected,
        "start": start,
        "end": end,
        "parameters": services.tunables(spec) if spec else [],
    }


@router.get("/backtest", response_class=HTMLResponse)
def backtest_page(request: Request, ref: str | None = None, show: ShowId = None) -> HTMLResponse:
    return page(
        request,
        "backtest.html",
        "Backtest",
        **_run_form_context(ref),
        show_id=show,
        backtests=state.store.backtests(25),
    )


@router.get("/lab", response_class=HTMLResponse)
def lab_page(request: Request, ref: str | None = None, show: ShowId = None) -> HTMLResponse:
    return page(
        request, "lab.html", "Lab", **_run_form_context(ref), show_id=show, reports=state.store.lab_reports(25)
    )


@router.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request) -> HTMLResponse:
    return page(request, "compare.html", "Compare", backtests=state.store.backtests(100))


@router.get("/costs", response_class=HTMLResponse)
def costs_page(request: Request) -> HTMLResponse:
    ledger = Ledger()
    config = llm_config()
    return page(
        request,
        "costs.html",
        "Costs",
        budget=config.budget_usd,
        spent_total=ledger.spent(),
        spent_eval=ledger.spent("eval"),
        summary=ledger.summary(),
        recent=ledger.calls(30),
        providers=services.providers(),
        prices_checked=config.prices_checked,
        fees=services.fees(),
    )


# --- spec editor fragments -------------------------------------------------------------------------------


@router.post("/ui/spec/load", response_class=HTMLResponse)
def spec_load(request: Request, ref: Annotated[str, Form()]) -> HTMLResponse:
    data = services.load_ref(state.store, ref)
    if data is None:
        return _error(request, HTTPException(404, f"no spec {ref!r}"))
    return fragment(request, "_check.html", check=services.check(data), editor=json.dumps(data, indent=2))


@router.post("/ui/spec/check", response_class=HTMLResponse)
def spec_check(request: Request, spec: Annotated[str, Form()]) -> HTMLResponse:
    data, error = services.parse_spec(spec)
    if data is None:
        return _error(request, HTTPException(422, error))
    return fragment(request, "_check.html", check=services.check(data), editor=None)


@router.post("/ui/spec/save", response_class=HTMLResponse)
def spec_save(request: Request, spec: Annotated[str, Form()]) -> HTMLResponse:
    data, error = services.parse_spec(spec)
    if data is None:
        return _error(request, HTTPException(422, error))
    try:
        valid = valid_spec(data)
    except HTTPException as exc:
        return _error(request, exc)
    ref = f"saved:{state.store.save_spec(valid.model_dump(mode='json'))}"
    return fragment(request, "_saved.html", ref=ref, name=valid.meta.name)


@router.get("/ui/spec/params", response_class=HTMLResponse)
def spec_params(request: Request, ref: str) -> HTMLResponse:
    data = services.load_ref(state.store, ref)
    names = services.tunables(data) if data else []
    market = data["market"]["symbol"] if data else "BTC-PERP"
    start, end = services.default_range(market)
    return fragment(request, "_params.html", parameters=names, start=start, end=end, oob=True)


# --- AI fragments ----------------------------------------------------------------------------------------


def _ai(http: Request, provider: str | None, task: str, **kwargs: Any) -> HTMLResponse:
    try:
        result = run_ai(provider or None, task, **kwargs)
    except HTTPException as exc:
        return _error(http, exc)
    editor = json.dumps(result["spec"], indent=2) if result["spec"] else None
    return fragment(http, "_ai.html", r=result, editor=editor)


@router.post("/ui/ai/generate", response_class=HTMLResponse)
def ui_generate(
    request: Request,
    idea: Annotated[str, Form()],
    provider: Annotated[str, Form()] = "",
    answers: Annotated[str, Form()] = "",
) -> HTMLResponse:
    return _ai(request, provider, "generate", idea=idea, answers=answers or None)


@router.post("/ui/ai/edit", response_class=HTMLResponse)
def ui_edit(
    request: Request,
    spec: Annotated[str, Form()],
    change: Annotated[str, Form()],
    provider: Annotated[str, Form()] = "",
) -> HTMLResponse:
    data, error = services.parse_spec(spec)
    if data is None:
        return _error(request, HTTPException(422, error))
    try:
        return _ai(request, provider, "edit", spec=valid_spec(data), request=change)
    except HTTPException as exc:
        return _error(request, exc)


@router.post("/ui/ai/explain", response_class=HTMLResponse)
def ui_explain(
    request: Request, spec: Annotated[str, Form()], provider: Annotated[str, Form()] = ""
) -> HTMLResponse:
    data, error = services.parse_spec(spec)
    if data is None:
        return _error(request, HTTPException(422, error))
    try:
        return _ai(request, provider, "explain", spec=valid_spec(data))
    except HTTPException as exc:
        return _error(request, exc)


@router.post("/ui/ai/from_pine", response_class=HTMLResponse)
def ui_from_pine(
    request: Request, code: Annotated[str, Form()], provider: Annotated[str, Form()] = ""
) -> HTMLResponse:
    return _ai(request, provider, "from_pine", code=code)


# --- jobs, backtests, lab, compare -----------------------------------------------------------------------


@router.post("/ui/backtests", response_class=HTMLResponse)
def ui_backtest(
    request: Request,
    ref: Annotated[str, Form()],
    start: Annotated[str, Form()],
    end: Annotated[str, Form()],
    engine: Annotated[str, Form()] = "fast",
) -> HTMLResponse:
    data = services.load_ref(state.store, ref)
    if data is None:
        return _error(request, HTTPException(404, f"no spec {ref!r}"))
    try:
        job_id = submit_backtest(BacktestRequest(spec=data, start=start, end=end, engine=engine))  # type: ignore[arg-type]
    except (HTTPException, ValueError) as exc:
        return _error(request, exc if isinstance(exc, HTTPException) else HTTPException(422, str(exc)))
    return job_fragment(request, job_id)


@router.post("/ui/lab", response_class=HTMLResponse)
async def ui_lab(request: Request) -> HTMLResponse:
    form = await request.form()
    ref = str(form.get("ref", ""))
    data = services.load_ref(state.store, ref)
    if data is None:
        return _error(request, HTTPException(404, f"no spec {ref!r}"))
    try:
        body = LabRequest(
            spec=data,
            start=str(form.get("start")),
            end=str(form.get("end")),
            parameters=[str(p) for p in form.getlist("parameters")][:4],
            objective=str(form.get("objective", "sharpe")),  # type: ignore[arg-type]
            optuna_trials=int(str(form.get("optuna_trials") or 0)),
            grid_points=int(str(form.get("grid_points") or 9)),
        )
        job_id = submit_lab(body)
    except (HTTPException, ValueError) as exc:
        return _error(request, exc if isinstance(exc, HTTPException) else HTTPException(422, str(exc)))
    return job_fragment(request, job_id)


@router.get("/ui/jobs/{job_id}", response_class=HTMLResponse)
def job_fragment(request: Request, job_id: int) -> HTMLResponse:
    job = state.store.job(job_id)
    if job is None:
        return _error(request, HTTPException(404, f"no job {job_id}"))
    return fragment(request, "_job.html", job=job)


@router.get("/ui/backtests/{backtest_id}", response_class=HTMLResponse)
def backtest_fragment(request: Request, backtest_id: int) -> HTMLResponse:
    row = state.store.backtest(backtest_id)
    if row is None:
        return _error(request, HTTPException(404, f"no backtest {backtest_id}"))
    return fragment(request, "_backtest.html", b=row)


@router.get("/ui/lab/{report_id}", response_class=HTMLResponse)
def lab_fragment(request: Request, report_id: int) -> HTMLResponse:
    row = state.store.lab_report(report_id)
    if row is None:
        return _error(request, HTTPException(404, f"no lab report {report_id}"))
    return fragment(request, "_lab.html", row=row, r=row["report"])


@router.get("/ui/compare", response_class=HTMLResponse)
def compare_fragment(request: Request, ids: Annotated[list[int], Query()] = []) -> HTMLResponse:  # noqa: B006
    rows = [r for i in ids[:6] if (r := state.store.backtest(i)) is not None]
    curves = {r["id"]: r["result"]["equity"] for r in rows}
    return fragment(request, "_compare.html", rows=rows, curves=curves)
