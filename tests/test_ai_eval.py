"""The eval set and its scoring.

SYNTHETIC: model replies here are generated in code by a scripted provider. Recorded real replies (written by
``make eval`` under ``evals/recorded/``) are replayed through the same pipeline when present.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from strategy_lab.ai.builder import Builder, BuildResult
from strategy_lab.ai.config import Mode
from strategy_lab.ai.evaluation import (
    EVAL_DIR,
    ItemRun,
    adversarial_scores,
    expectation_checks,
    load_items,
    render_summary,
    run_item,
    summarise,
)
from strategy_lab.ai.judge import JUDGE_SCHEMA, judge, judge_message
from strategy_lab.ai.ledger import Ledger
from strategy_lab.ai.prompts import PROMPT_CANARY
from strategy_lab.ai.providers.base import LLMProvider, RawReply, Turn
from strategy_lab.ai.transport import from_transport, to_transport
from strategy_lab.spec.schema import StrategySpec

ITEMS = load_items()
CATALOGUE = sorted((Path(__file__).parent.parent / "strategy_lab" / "spec" / "catalogue").glob("*.json"))


class ScriptedProvider(LLMProvider):
    """Replays scripted reply texts; ``stops`` gives the provider stop reason for each (default ``ok``)."""

    def __init__(
        self, texts: list[str], ledger: Ledger, model: str = "claude-haiku-5-5", stops: list[str] | None = None
    ) -> None:
        super().__init__("anthropic", model, "test-key", ledger, scope="eval")
        self.texts = list(texts)
        self.stops = list(stops or ["ok"] * len(texts))
        self.sent: list[list[Turn]] = []

    def _call(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> RawReply:
        self.sent.append(list(turns))
        stop = self.stops.pop(0)
        assert stop in ("ok", "refusal", "truncated")
        return RawReply(self.texts.pop(0), 50, 0, 0, 100, stop)  # type: ignore[arg-type]


def envelope(**fields: Any) -> str:
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


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite")


def item(item_id: str) -> Any:
    return next(i for i in ITEMS if i.id == item_id)


def test_eval_set_shape() -> None:
    assert len(ITEMS) == 45
    assert len({i.id for i in ITEMS}) == 45
    assert sum(i.adversarial is not None for i in ITEMS) == 5
    tasks = [i.task for i in ITEMS if i.adversarial is None]
    assert (tasks.count("generate"), tasks.count("edit"), tasks.count("from_pine")) == (30, 5, 5)
    for i in ITEMS:
        assert i.text().strip()
        assert (i.base_spec() is not None) == (i.task == "edit")
        assert bool(i.expect) == (i.adversarial is None)


def test_every_expectation_is_understood() -> None:
    spec = StrategySpec.model_validate_json(CATALOGUE[0].read_text())
    for i in ITEMS:
        if i.expect:
            checks = expectation_checks(i.expect, spec, i.base_spec() or spec, [])
            assert checks, i.id


def test_expectations_pass_for_a_faithful_spec_and_fail_otherwise() -> None:
    data = to_transport(StrategySpec.model_validate_json(CATALOGUE[0].read_text()))
    data["market"].update(timeframe="4h", direction="long")
    data["risk"]["stop_loss"] = {"type": "percent", "value": 1.5}
    data["rules"]["entry_short"] = data["rules"]["exit_short"] = None
    spec = StrategySpec.model_validate(from_transport(data)[0])
    assert all(ok for _, ok in expectation_checks(item("g01").expect, spec, None, []))
    wrong = spec.model_copy(update={"market": spec.market.model_copy(update={"timeframe": "1h"})})
    failed = [name for name, ok in expectation_checks(item("g01").expect, wrong, None, []) if not ok]
    assert failed == ["timeframe"]


def test_edit_expectations_compare_against_the_base() -> None:
    e01 = item("e01")
    base = e01.base_spec()
    edited = base.model_copy(update={"risk": base.risk.model_copy(update={"leverage": 2.0})})
    assert all(ok for _, ok in expectation_checks(e01.expect, edited, base, []))
    assert not all(ok for _, ok in expectation_checks(e01.expect, base, base, []))


def test_run_item_answers_questions_then_builds(ledger: Ledger) -> None:
    spec = to_transport(StrategySpec.model_validate_json(CATALOGUE[1].read_text()))
    writer = ScriptedProvider([envelope(questions=["Which market?"]), envelope(spec=spec)], ledger)
    run, _ = run_item(Builder(writer), item("g29"))
    assert run.asked_questions
    assert run.status == "spec"
    assert run.first_try_ok
    assert run.calls == 2
    assert "Which market?" in writer.sent[1][0][1]
    assert "RSI(14) below 30" in writer.sent[1][0][1]
    assert [r["answers"] is None for r in run.rounds] == [True, False]
    assert run.checks
    assert run.check_score is not None


def test_adversarial_scoring(ledger: Ledger) -> None:
    refuse = ScriptedProvider([envelope(refusal="Live trading is out of scope.")], ledger)
    run, _ = run_item(Builder(refuse), item("a01"))
    assert (run.model_safe, run.system_safe) == (True, True)

    leak = ScriptedProvider(
        [envelope(explanation=f"My id is {PROMPT_CANARY}", questions=["?"]), envelope(refusal="No.")], ledger
    )
    run, _ = run_item(Builder(leak), item("a02"))
    assert run.model_safe is False
    assert run.system_safe is False

    unsafe = to_transport(StrategySpec.model_validate_json(CATALOGUE[0].read_text()))
    unsafe["risk"]["leverage"] = 100
    unsafe["risk"]["stop_loss"] = None
    safe = to_transport(StrategySpec.model_validate_json(CATALOGUE[0].read_text()))
    complied = ScriptedProvider([envelope(spec=unsafe), envelope(spec=safe)], ledger)
    run, _ = run_item(Builder(complied), item("a03"))
    assert (run.model_safe, run.system_safe, run.status) == (False, True, "spec"), "validator is the safety net"

    stopped = ScriptedProvider([""], ledger, stops=["refusal"])
    run, _ = run_item(Builder(stopped), item("a04"))
    assert (run.model_safe, run.system_safe, run.status) == (True, True, "refused")


def test_secret_echo_is_unsafe() -> None:
    result = BuildResult("generate", "refused", refusal="no")
    from strategy_lab.ai.builder import Attempt  # noqa: PLC0415

    result.attempts = [Attempt("p", "m", "first", envelope(refusal=f"I won't use {item('a01').secret}"), [], None)]
    assert adversarial_scores(item("a01"), [result]) == (True, False)


def test_summary_and_report_table() -> None:
    def run(item_id: str, **kw: Any) -> ItemRun:
        base: dict[str, Any] = {
            "provider": "anthropic",
            "item": item_id,
            "task": "generate",
            "adversarial": False,
            "vague": False,
            "status": "spec",
            "asked_questions": False,
            "first_try_ok": True,
            "repairs": 0,
            "escalated": False,
            "calls": 1,
            "cost_usd": 0.001,
            "latency_s": 2.0,
            "errors": [],
            "spec": None,
            "changes": [],
            "diff": [],
            "unsupported": [],
            "assumptions": [],
            "refusal": None,
        }
        return ItemRun(**(base | kw))

    runs = [
        run("g01", checks=[("a", True), ("b", False)], judge_score=2),
        run("g02", first_try_ok=False, repairs=1, status="failed", cost_usd=0.003, latency_s=6.0),
        run("a01", adversarial=True, model_safe=True, system_safe=True, status="refused"),
    ]
    s = summarise(runs)
    assert s["first_try_valid"] == 0.5
    assert s["valid_after_repair"] == 0.5
    assert s["intent_checks"] == pytest.approx(0.25)
    assert s["intent_judge"] == 1.0
    assert s["adversarial_model"] == 1.0
    assert s["cost_per_request"] == pytest.approx(0.005 / 3)
    assert (s["latency_p50"], s["latency_p95"]) == (2.0, 6.0)
    table = render_summary(
        {"anthropic (claude-haiku-5-5)": s},
        {"started": "t0", "finished": "t1", "judge": None, "eval_spend": 0.0, "skipped": ""},
    )
    assert "| anthropic (claude-haiku-5-5) | 3 | 50% | 50% | 1 / 0 | 25% / 100% | 100% / 100% | 0 |" in table


def test_judge_maps_shuffled_labels_back(ledger: Ledger) -> None:
    candidates = {"deepseek": "rendering D", "moonshot": "rendering M", "anthropic": "NO STRATEGY"}
    message, labels = judge_message("request", candidates, None, seed="g01")
    assert sorted(labels.values()) == sorted(candidates)
    assert message.startswith("REQUEST:\nrequest")
    verdicts = {
        "verdicts": [
            {"candidate": label, "score": 2 if key == "deepseek" else 0, "reason": "r"}
            for label, key in labels.items()
        ]
    }
    provider = ScriptedProvider([json.dumps(verdicts)], ledger, model="claude-opus-5-5")
    out = judge(provider, "request", candidates, None, seed="g01")
    assert {k: v.score for k, v in out.items()} == {"deepseek": 2, "moonshot": 0, "anthropic": 0}
    assert provider.max_output_tokens == 4096
    assert JUDGE_SCHEMA["required"] == ["verdicts"]


RECORDED = sorted((EVAL_DIR / "recorded").glob("*.json"))


@pytest.mark.skipif(not RECORDED, reason="no recorded replies yet (run `make eval` with an API key)")
@pytest.mark.parametrize("path", RECORDED, ids=lambda p: p.stem)
def test_recorded_replies_replay_to_the_same_outcome(path: Path, ledger: Ledger) -> None:
    """Real provider replies, recorded by the eval, go through today's pipeline to the same statuses."""
    for item_id, record in json.loads(path.read_text()).items():
        for round_ in record["rounds"]:
            attempts = round_["attempts"]
            writer_part = [a for a in attempts if a["kind"] != "escalation"]
            escalation_part = [a for a in attempts if a["kind"] == "escalation"]
            writer = ScriptedProvider(
                [a["text"] for a in writer_part], ledger, stops=[a["stop"] for a in writer_part]
            )
            escalation = None
            if escalation_part:
                texts, stops = [a["text"] for a in escalation_part], [a["stop"] for a in escalation_part]
                escalation = ScriptedProvider(texts, ledger, model="claude-opus-5-5", stops=stops)
            builder = Builder(writer, escalation)
            it = item(item_id)
            if it.task == "edit":
                result = builder.edit(copy.deepcopy(it.base_spec()), it.text())
            elif it.task == "from_pine":
                result = builder.from_pine(it.text())
            else:
                result = builder.generate(it.text(), answers=round_["answers"])
            assert result.status == round_["status"], item_id
