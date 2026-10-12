"""Request bodies and the actions shared by the JSON API and the HTML pages."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from strategy_lab.ai.builder import Builder
from strategy_lab.ai.config import llm_config
from strategy_lab.ai.ledger import BudgetExceededError
from strategy_lab.ai.providers import MissingKeyError
from strategy_lab.ai.providers.base import ProviderError
from strategy_lab.api import services
from strategy_lab.api.jobs import JobQueue
from strategy_lab.api.store import Store
from strategy_lab.spec.schema import StrategySpec


class State:
    store: Store
    queue: JobQueue


state = State()


# --- request bodies --------------------------------------------------------------------------------------

Engine = Literal["fast", "nautilus"]


class SpecBody(BaseModel):
    spec: dict[str, Any]


class BacktestRequest(BaseModel):
    spec: dict[str, Any]
    start: str
    end: str
    engine: Engine = "fast"
    source: str | None = None


class LabRequest(BaseModel):
    spec: dict[str, Any]
    start: str
    end: str
    parameters: list[str] = Field(default_factory=list, max_length=4)
    objective: Literal["sharpe", "net_return_pct", "calmar", "profit_factor"] = "sharpe"
    optuna_trials: int = Field(default=0, ge=0, le=300)
    grid_points: int = Field(default=9, ge=3, le=15)
    source: str | None = None


class GenerateRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=8000)
    answers: str | None = Field(default=None, max_length=4000)
    provider: str | None = None


class EditRequest(BaseModel):
    spec: dict[str, Any]
    request: str = Field(min_length=2, max_length=4000)
    provider: str | None = None


class ExplainRequest(BaseModel):
    spec: dict[str, Any]
    provider: str | None = None


class PineRequest(BaseModel):
    code: str = Field(min_length=10, max_length=30000)
    provider: str | None = None


# --- shared actions (also used by the HTML routes) -------------------------------------------------------


def valid_spec(data: dict[str, Any]) -> StrategySpec:
    checked = services.check(data)
    if not checked["ok"]:
        raise HTTPException(422, detail={"message": "the spec does not validate", "errors": checked["errors"]})
    return StrategySpec.model_validate(data)


def submit_backtest(request: BacktestRequest) -> int:
    valid_spec(request.spec)
    if request.start >= request.end:
        raise HTTPException(422, detail="start must be before end")
    return state.queue.submit("backtest", request.model_dump())


def submit_lab(request: LabRequest) -> int:
    spec = valid_spec(request.spec)
    known = set(services.tunables(spec.model_dump()))
    unknown = [p for p in request.parameters if p not in known]
    if unknown:
        raise HTTPException(422, detail=f"unknown parameter(s) {unknown}")
    if request.start >= request.end:
        raise HTTPException(422, detail="start must be before end")
    return state.queue.submit("lab", request.model_dump())


def run_ai(provider: str | None, task: str, **kwargs: Any) -> dict[str, Any]:
    if provider is not None and provider not in llm_config().providers:
        raise HTTPException(422, detail=f"unknown provider {provider!r}")
    try:
        builder = Builder.for_provider(provider)
        result = getattr(builder, task)(**kwargs)
    except MissingKeyError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except BudgetExceededError as exc:
        raise HTTPException(402, detail=f"spending limit: {exc}") from exc
    except ProviderError as exc:
        raise HTTPException(502, detail=str(exc)) from exc
    return services.build_result(result)
