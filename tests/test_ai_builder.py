"""AI builder pipeline: validation, repair, escalation, clean failure, questions, refusals, budget, costs.

SYNTHETIC: the "model replies" below are generated in code by a scripted provider; no API is called.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from strategy_lab.ai.builder import Builder
from strategy_lab.ai.config import Mode, llm_config
from strategy_lab.ai.ledger import BudgetExceededError, Ledger
from strategy_lab.ai.providers.base import LLMProvider, ModeRejectedError, RawReply, Turn
from strategy_lab.ai.transport import to_transport
from strategy_lab.spec.schema import StrategySpec

CATALOGUE = sorted((Path(__file__).parent.parent / "strategy_lab" / "spec" / "catalogue").glob("*.json"))
EMA = StrategySpec.model_validate_json(CATALOGUE[0].read_text(encoding="utf-8"))


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


def good_spec() -> dict[str, Any]:
    return to_transport(EMA)


def no_stop_spec() -> dict[str, Any]:
    spec = good_spec()
    spec["risk"]["stop_loss"] = None
    return spec


class ScriptedProvider(LLMProvider):
    """Replays scripted replies (text, or an exception to raise) and records what it was sent."""

    def __init__(self, script: list[str | Exception], ledger: Ledger, model: str = "claude-haiku-5-5") -> None:
        super().__init__("anthropic", model, "test-key", ledger, scope="test")
        self.script = list(script)
        self.calls: list[tuple[Mode, str, list[Turn]]] = []

    def _call(self, mode: Mode, system: str, turns: Sequence[Turn], schema: dict[str, Any]) -> RawReply:
        self.calls.append((mode, system, copy.deepcopy(list(turns))))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        stop = "refusal" if item == "<refusal>" else "ok"
        return RawReply(
            item, input_tokens=100, cached_tokens=4000, cache_write_tokens=0, output_tokens=500, stop=stop
        )


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite")


def test_valid_first_reply(ledger: Ledger) -> None:
    writer = ScriptedProvider([reply(spec=good_spec(), assumptions=["1h bars"])], ledger)
    result = Builder(writer).generate("EMA cross on BTC")
    assert result.status == "spec"
    assert result.first_try_ok
    assert result.repairs == 0
    assert result.spec is not None
    assert result.spec.meta.author == "ai"
    assert result.assumptions == ["1h bars"]
    # Haiku 5.5: 100 uncached x $0.10 + 4000 cached x $0.01 + 500 output x $0.50 per million tokens
    assert result.cost_usd == pytest.approx((100 * 0.10 + 4000 * 0.01 + 500 * 0.50) / 1e6)
    assert ledger.spent() == pytest.approx(result.cost_usd)
    assert ledger.summary()[0]["feature"] == "generate"


def test_repair_quotes_the_exact_validator_errors(ledger: Ledger) -> None:
    writer = ScriptedProvider([reply(spec=no_stop_spec()), reply(spec=good_spec())], ledger)
    result = Builder(writer).generate("EMA cross without a stop")
    assert result.status == "spec"
    assert not result.first_try_ok
    assert result.repairs == 1
    turns = writer.calls[1][2]
    assert [role for role, _ in turns] == ["user", "assistant", "user"]
    assert "$.risk.stop_loss: a stop-loss is required [MISSING_STOP]" in turns[2][1]
    assert writer.calls[0][1] == writer.calls[1][1], "the system prompt (cached prefix) never changes"


def test_escalation_after_two_failed_repairs(ledger: Ledger) -> None:
    writer = ScriptedProvider([reply(spec=no_stop_spec())] * 3, ledger)
    stronger = ScriptedProvider([reply(spec=good_spec())], ledger, model="claude-opus-5-5")
    result = Builder(writer, stronger).generate("idea")
    assert result.status == "spec"
    assert result.escalated
    assert [a.kind for a in result.attempts] == ["first", "repair", "repair", "escalation"]
    ((role, message),) = stronger.calls[0][2]
    assert role == "user"
    assert "MISSING_STOP" in message
    assert "TASK: generate" in message


def test_fails_cleanly_with_all_errors(ledger: Ledger) -> None:
    bad = no_stop_spec()
    bad["risk"]["leverage"] = 50
    writer = ScriptedProvider([reply(spec=bad)] * 3, ledger)
    stronger = ScriptedProvider(["not json at all"], ledger, model="claude-opus-5-5")
    result = Builder(writer, stronger).generate("idea")
    assert result.status == "failed"
    assert result.spec is None
    assert not result.ok
    assert len(result.attempts) == 4
    assert any("not a valid JSON object" in e for e in result.errors)
    assert any("LEVERAGE" in e for e in result.attempts[0].errors)
    assert any("MISSING_STOP" in e for e in result.attempts[0].errors)


def test_questions_only_when_allowed(ledger: Ledger) -> None:
    writer = ScriptedProvider([reply(questions=["Which market?", "Long only?"])], ledger)
    assert Builder(writer).generate("buy dips").status == "questions"
    too_many = ScriptedProvider([reply(questions=["a?", "b?", "c?"]), reply(spec=good_spec())], ledger)
    assert Builder(too_many).generate("buy dips").repairs == 1
    answered = ScriptedProvider([reply(questions=["a?"]), reply(spec=good_spec())], ledger)
    result = Builder(answered).generate("buy dips", answers="BTC, long only")
    assert result.status == "spec"
    assert result.repairs == 1
    assert "QUESTIONS ALLOWED: no" in answered.calls[0][2][0][1]


def test_refusals(ledger: Ledger) -> None:
    writer = ScriptedProvider([reply(refusal="Live trading is out of scope.")], ledger)
    result = Builder(writer).generate("place a market order on my account")
    assert result.status == "refused"
    assert result.spec is None
    assert result.ok
    safety_stop = ScriptedProvider(["<refusal>"], ledger)
    assert Builder(safety_stop).generate("...").status == "refused"


def test_edit_returns_a_computed_diff(ledger: Ledger) -> None:
    edited = good_spec()
    edited["risk"]["leverage"] = 2.0
    writer = ScriptedProvider([reply(spec=edited, changes=["leverage 3 → 2"])], ledger)
    result = Builder(writer).edit(EMA, "use 2x leverage")
    assert result.status == "spec"
    assert result.first_try_ok
    assert result.diff == ["$.risk.leverage: 3 → 2"]
    assert result.changes == ["leverage 3 → 2"]


def test_edit_that_needs_no_change_is_accepted_with_a_warning(ledger: Ledger) -> None:
    """e.g. "make it long only" on a long-only spec: never force a meaningless edit through repairs."""
    writer = ScriptedProvider([reply(spec=good_spec(), changes=["already uses 3x leverage"])], ledger)
    result = Builder(writer).edit(EMA, "use 3x leverage")
    assert result.status == "spec"
    assert result.repairs == 0
    assert result.diff == []
    assert any(w.startswith("UNCHANGED") for w in result.warnings)


def test_explain_and_from_pine(ledger: Ledger) -> None:
    writer = ScriptedProvider(
        [reply(explanation="Trend following."), reply(spec=good_spec(), unsupported=["pyramiding"])], ledger
    )
    builder = Builder(writer)
    assert builder.explain(EMA).explanation == "Trend following."
    result = builder.from_pine("//@version=5\nstrategy('x', pyramiding=2)")
    assert result.status == "spec"
    assert result.unsupported == ["pyramiding"]


def test_market_data_context_is_applied(ledger: Ledger) -> None:
    spec = good_spec()
    spec["market"]["symbol"] = "XAU-PERP"
    spec["indicators"].append({"id": "v", "type": "vwap", "params": [], "source": None, "timeframe": None})
    spec["rules"]["entry_long"] = {
        "op": ">",
        "left": {"input": "close", "bars_ago": 0},
        "right": {"indicator": "v", "output": None, "bars_ago": 0},
    }
    writer = ScriptedProvider([reply(spec=spec), reply(spec=good_spec())], ledger)
    result = Builder(writer).generate("gold above VWAP")
    assert any("NO_VOLUME_DATA" in e for e in result.attempts[0].errors)


def test_mode_fallback_is_remembered(ledger: Ledger) -> None:
    writer = ScriptedProvider(
        [ModeRejectedError("schema too complex"), reply(spec=good_spec()), reply(spec=good_spec())], ledger
    )
    builder = Builder(writer)
    builder.generate("a")
    builder.generate("b")
    assert [mode for mode, _, _ in writer.calls] == ["json_schema", "json_prompt", "json_prompt"]


def test_budget_guard_stops_before_sending(ledger: Ledger, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = ScriptedProvider([reply(spec=good_spec())], ledger)
    monkeypatch.setattr(writer, "estimate_cost", lambda *_: llm_config().budget_usd.total + 0.01)
    with pytest.raises(BudgetExceededError):
        Builder(writer).generate("a")
    assert writer.calls == []


def test_eval_scope_has_its_own_limit(ledger: Ledger) -> None:
    budget = llm_config().budget_usd
    ledger.ensure_budget("eval", budget.eval - 0.01)
    ledger.ensure_budget("app", budget.eval + 0.01)
    with pytest.raises(BudgetExceededError):
        ledger.ensure_budget("eval", budget.eval + 0.01)


def test_deepseek_peak_and_off_peak_prices() -> None:
    deepseek = llm_config().providers["deepseek"]
    monday_peak = dt.datetime(2026, 10, 12, 2, 30, tzinfo=dt.UTC)
    monday_off = dt.datetime(2026, 10, 12, 4, 0, tzinfo=dt.UTC)
    saturday = dt.datetime(2026, 10, 17, 2, 30, tzinfo=dt.UTC)
    assert deepseek.is_peak(monday_peak)
    assert not deepseek.is_peak(monday_off)
    assert not deepseek.is_peak(saturday)
    assert deepseek.rates("deepseek-flash", monday_peak, 1000).input == 0.30
    assert deepseek.rates("deepseek-flash", saturday, 1000).input == 0.15
    assert deepseek.next_off_peak(monday_peak) == monday_off


def test_haiku_long_context_rate_card() -> None:
    anthropic = llm_config().providers["anthropic"]
    now = dt.datetime(2026, 10, 12, tzinfo=dt.UTC)
    assert anthropic.rates("claude-haiku-5-5", now, 100_000).input == 0.10
    assert anthropic.rates("claude-haiku-5-5", now, 100_001).output == 2.50
