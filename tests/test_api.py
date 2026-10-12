"""API and pages: every page renders, specs validate/save, AI routes (scripted provider), background jobs.

SYNTHETIC: the AI replies come from a scripted provider generated in code; no LLM API is called. Backtest and
lab jobs run for real (worker processes, real BTC history) when the data is downloaded.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from strategy_lab.ai.builder import Builder
from strategy_lab.ai.config import Mode
from strategy_lab.ai.ledger import Ledger
from strategy_lab.ai.providers.base import LLMProvider, RawReply, Turn
from strategy_lab.ai.transport import to_transport
from strategy_lab.data import storage
from strategy_lab.spec.schema import StrategySpec
from strategy_lab.ui.markdown import to_html

CATALOGUE = sorted((Path(__file__).parent.parent / "strategy_lab" / "spec" / "catalogue").glob("*.json"))
EMA = json.loads(CATALOGUE[0].read_text())
needs_data = pytest.mark.skipif(not storage.list_datasets(), reason="no data downloaded (run `make data`)")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("STRATEGY_LAB_DB", str(tmp_path / "state.sqlite"))
    from strategy_lab.api.app import app  # noqa: PLC0415 - import after the environment is set

    with TestClient(app) as test_client:
        yield test_client


def wait_for(client: TestClient, job_id: int, timeout: float = 240.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.5)
    raise TimeoutError(f"job {job_id} did not finish")


@pytest.mark.parametrize("path", ["/", "/backtest", "/lab", "/compare", "/costs"])
def test_pages_render(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "backtest only" in response.text
    assert "<nav>" in response.text


def test_specs_library_validate_render_save(client: TestClient) -> None:
    library = client.get("/api/specs").json()
    assert sum(s["group"] == "catalogue" for s in library) == 10
    assert client.get("/api/specs/cat:01_ema_crossover").json()["meta"]["name"] == EMA["meta"]["name"]
    assert client.get("/api/specs/cat:../../etc").status_code == 404

    bad = json.loads(json.dumps(EMA))
    bad["risk"]["stop_loss"] = None
    checked = client.post("/api/specs/validate", json={"spec": bad}).json()
    assert not checked["ok"]
    assert [e["code"] for e in checked["errors"]] == ["MISSING_STOP"]
    good = client.post("/api/specs/validate", json={"spec": EMA}).json()
    assert good["ok"]
    assert len(good["parameters"]) == 6
    assert good["rendered"].startswith("### EMA crossover")

    assert client.post("/api/specs", json={"spec": bad}).status_code == 422
    ref = client.post("/api/specs", json={"spec": EMA}).json()["ref"]
    assert ref == "saved:1"
    assert any(s["ref"] == ref for s in client.get("/api/specs").json())


def test_spec_fragments(client: TestClient) -> None:
    loaded = client.post("/ui/spec/load", data={"ref": "cat:05_macd_htf_filter"}).text
    assert 'hx-swap-oob="true"' in loaded
    assert "Valid spec" in loaded
    broken = client.post("/ui/spec/check", data={"spec": "{not json"}).text
    assert "not valid JSON" in broken
    saved = client.post("/ui/spec/save", data={"spec": json.dumps(EMA)}).text
    assert "/backtest?ref=saved:1" in saved
    params = client.get("/ui/spec/params", params={"ref": "cat:01_ema_crossover"}).text
    assert 'value="ema_fast.period" checked' in params


class ScriptedProvider(LLMProvider):
    def __init__(self, texts: list[str]) -> None:
        super().__init__("anthropic", "claude-haiku-5-5", "test-key", Ledger(), scope="app")
        self.texts = texts

    def _call(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> RawReply:
        return RawReply(self.texts.pop(0), 100, 4000, 0, 300, "ok")


def reply(**fields: Any) -> str:
    base: dict[str, Any] = {
        "questions": [],
        "spec": None,
        "changes": [],
        "explanation": None,
        "unsupported": [],
        "assumptions": [],
        "refusal": None,
    }
    return json.dumps(base | fields)


def test_ai_routes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("strategy_lab.ai.providers.api_key", lambda name: None)
    response = client.post("/api/ai/generate", json={"idea": "EMA cross on BTC"})
    assert response.status_code == 400
    assert "is not set" in response.json()["detail"]
    assert "is not set" in client.post("/ui/ai/generate", data={"idea": "EMA cross"}).text

    spec = to_transport(StrategySpec.model_validate(EMA))
    scripted = ScriptedProvider([reply(spec=spec, assumptions=["1h bars"]), reply(explanation="Trend following.")])
    monkeypatch.setattr(Builder, "for_provider", classmethod(lambda cls, provider=None: cls(scripted)))
    result = client.post("/api/ai/generate", json={"idea": "EMA cross on BTC"}).json()
    assert result["status"] == "spec"
    assert result["spec"]["meta"]["author"] == "ai"
    assert result["cost_usd"] > 0
    fragment = client.post("/ui/ai/explain", data={"spec": json.dumps(EMA)}).text
    assert "Trend following." in fragment
    costs = client.get("/api/costs").json()
    assert costs["spent"]["total"] == pytest.approx(result["cost_usd"] * 2)
    assert costs["budget"] == {"total": 3.0, "eval": 1.0}


def test_job_requests_are_validated(client: TestClient) -> None:
    body = {"spec": EMA, "start": "2024-02-01", "end": "2024-01-01"}
    assert client.post("/api/backtests", json=body).status_code == 422
    assert client.post("/api/lab", json=body | {"end": "2025-01-01", "parameters": ["nope"]}).status_code == 422
    assert client.get("/api/jobs/999").status_code == 404


@needs_data
def test_backtest_jobs_on_both_engines_agree(client: TestClient) -> None:
    body = {"spec": EMA, "start": "2024-03-01", "end": "2024-05-01"}
    ids = [client.post("/api/backtests", json=body | {"engine": e}).json()["job_id"] for e in ("fast", "nautilus")]
    jobs = [wait_for(client, i) for i in ids]
    assert [j["status"] for j in jobs] == ["done", "done"]
    fast, nautilus = (client.get(f"/api/backtests/{j['result_id']}").json() for j in jobs)
    assert fast["engine_version"].startswith("strategy_lab fast engine")
    assert nautilus["engine_version"] == "nautilus_trader 1.231.0"
    assert fast["metrics"]["trades"] == nautilus["metrics"]["trades"] > 0
    assert fast["metrics"]["net_pnl"] == pytest.approx(nautilus["metrics"]["net_pnl"], rel=1e-9)
    assert fast["result"]["price"]["bars"]
    page = client.get(f"/ui/backtests/{fast['id']}").text
    assert "StrategyLab.backtest" in page
    compare = client.get("/ui/compare", params={"ids": [fast["id"], nautilus["id"]]}).text
    assert "compare-data" in compare


@needs_data
def test_lab_job(client: TestClient) -> None:
    body = {"spec": EMA, "start": "2024-01-01", "end": "2024-11-01", "grid_points": 3, "optuna_trials": 3}
    job = wait_for(client, client.post("/api/lab", json=body).json()["job_id"])
    assert job["status"] == "done", job["error"]
    report = client.get(f"/api/lab/{job['result_id']}").json()
    assert 0 <= report["score"] <= 100
    assert len(report["report"]["walk_forward"]["windows"]) == 2
    assert "StrategyLab.lab" in client.get(f"/ui/lab/{job['result_id']}").text


def test_markdown_subset() -> None:
    html = to_html("### T <x>\n**Rules**\n- a `b`\n  - nested\n- c")
    assert html == (
        "<h3>T &lt;x&gt;</h3>\n<p><strong>Rules</strong></p>\n<ul>\n<li>a <code>b</code></li>\n<ul>\n"
        "<li>nested</li>\n</ul>\n<li>c</li>\n</ul>"
    )
