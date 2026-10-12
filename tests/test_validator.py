"""Validator tests: every guard catches the bad spec it exists for, and good specs pass."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from strategy_lab.spec.render import render
from strategy_lab.spec.schema import StrategySpec, json_schema
from strategy_lab.spec.validator import ValidationContext, validate

CATALOGUE_DIR = Path(__file__).parent.parent / "strategy_lab" / "spec" / "catalogue"
CATALOGUE_FILES = sorted(CATALOGUE_DIR.glob("*.json"))


def ema_cross() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((CATALOGUE_DIR / "01_ema_crossover.json").read_text())
    return data


def codes(data: dict[str, Any], context: ValidationContext | None = None) -> list[str]:
    return [e.code for e in validate(data, context).errors]


def cmp(left: dict[str, Any], op: str, right: dict[str, Any]) -> dict[str, Any]:
    return {"op": op, "left": left, "right": right}


@pytest.mark.parametrize("path", CATALOGUE_FILES, ids=lambda p: p.stem)
def test_catalogue_specs_validate_and_render(path: Path) -> None:
    result = validate(json.loads(path.read_text()))
    assert result.ok, result.errors
    text = render(result.spec)  # type: ignore[arg-type]
    assert result.spec is not None and result.spec.meta.name in text
    assert "Stop-loss:" in text and "MISSING" not in text


def test_catalogue_has_ten_strategies_with_descriptions() -> None:
    assert len(CATALOGUE_FILES) == 10
    for path in CATALOGUE_FILES:
        assert len(json.loads(path.read_text())["meta"]["description"]) > 150


def test_all_errors_are_reported_at_once_with_json_paths() -> None:
    data = ema_cross()
    data["risk"]["stop_loss"] = None
    data["risk"]["leverage"] = 25
    data["indicators"][0]["params"]["period"] = 1
    data["rules"]["entry_long"]["left"]["indicator"] = "nope"
    result = validate(data)
    found = {(e.code, e.path) for e in result.errors}
    assert ("MISSING_STOP", "$.risk.stop_loss") in found
    assert ("LEVERAGE", "$.risk.leverage") in found
    assert ("PARAM_OUT_OF_RANGE", "$.indicators[0].params.period") in found
    assert ("UNDEFINED_INDICATOR", "$.rules.entry_long.left.indicator") in found


def test_schema_errors_have_paths() -> None:
    data = ema_cross()
    data["market"]["symbol"] = "DOGE-PERP"
    data["indicators"][0]["type"] = "magic"
    data["surprise"] = 1
    paths = {e.path for e in validate(data).errors}
    assert {"$.market.symbol", "$.indicators[0].type", "$.surprise"} <= paths


@pytest.mark.parametrize(("period", "ok"), [(1, False), (2, True), (100, True), (101, False)])
def test_rsi_period_bounds(period: int, ok: bool) -> None:
    data = ema_cross()
    data["indicators"].append({"id": "rsi", "type": "rsi", "params": {"period": period}})
    assert ("PARAM_OUT_OF_RANGE" not in codes(data)) is ok


def test_unknown_param_and_source_rules() -> None:
    data = ema_cross()
    data["indicators"][0]["params"]["length"] = 5
    data["indicators"].append({"id": "atr", "type": "atr", "params": {"period": 14}, "source": "close"})
    assert {"UNKNOWN_PARAM", "SOURCE_NOT_ALLOWED"} <= set(codes(data))


# --- look-ahead guards ---------------------------------------------------------------------------------


def test_lookahead_negative_bars_ago() -> None:
    data = ema_cross()
    data["rules"]["entry_long"]["left"]["bars_ago"] = -1
    assert "LOOKAHEAD_FUTURE_BAR" in codes(data)


def test_lookahead_same_bar_close_fill_with_current_values() -> None:
    data = ema_cross()
    data["execution"] = {"fill_on": "same_bar_close"}
    assert "LOOKAHEAD_SAME_BAR" in codes(data)


def test_same_bar_fill_without_current_values_is_still_unsupported() -> None:
    data = ema_cross()
    for rule in ("entry_long", "exit_long", "entry_short", "exit_short"):
        for side in ("left", "right"):
            data["rules"][rule][side]["bars_ago"] = 1
    data["execution"] = {"fill_on": "same_bar_close"}
    assert codes(data) == ["UNSUPPORTED_EXECUTION"]


def test_lookahead_forming_higher_timeframe_bar() -> None:
    data = json.loads((CATALOGUE_DIR / "05_macd_htf_filter.json").read_text())
    data["execution"] = {"htf_bars": "forming"}
    assert "LOOKAHEAD_FORMING_HTF" in codes(data)


# --- higher-timeframe misuse -------------------------------------------------------------------------


def test_indicator_timeframe_below_base_is_rejected() -> None:
    data = json.loads((CATALOGUE_DIR / "05_macd_htf_filter.json").read_text())
    data["market"]["timeframe"] = "1d"  # the 4h filter is now *lower* than the base timeframe
    assert "HTF_BELOW_BASE" in codes(data)


def test_crosses_on_higher_timeframe_series_are_rejected() -> None:
    data = json.loads((CATALOGUE_DIR / "05_macd_htf_filter.json").read_text())
    data["rules"]["entry_long"]["args"][1] = {
        "op": "crosses_above", "left": {"input": "close"}, "right": {"indicator": "htf_ema"},
    }  # fmt: skip
    assert "HTF_CROSS" in codes(data)


# --- contradictions -------------------------------------------------------------------------------------


def contradiction(entry: dict[str, Any], extra_indicators: list[dict[str, Any]] | None = None) -> list[str]:
    data = ema_cross()
    data["indicators"] += extra_indicators or []
    data["rules"]["entry_long"] = entry
    return codes(data)


RSI = [{"id": "rsi", "type": "rsi", "params": {"period": 14}}]
DC = [{"id": "dc", "type": "donchian", "params": {"period": 20}}]


@pytest.mark.parametrize(
    ("entry", "indicators"),
    [
        ({"op": "all", "args": [cmp({"indicator": "rsi"}, ">", {"value": 70}),
                                cmp({"indicator": "rsi"}, "<", {"value": 30})]}, RSI),
        ({"op": "all", "args": [cmp({"indicator": "rsi"}, ">", {"value": 50}),
                                cmp({"indicator": "rsi"}, "<=", {"value": 50})]}, RSI),
        (cmp({"indicator": "rsi"}, ">", {"value": 100}), RSI),
        (cmp({"value": 5}, ">", {"value": 10}), []),
        (cmp({"input": "close"}, ">", {"indicator": "dc", "output": "upper"}), DC),
        (cmp({"input": "low"}, "<", {"indicator": "dc", "output": "lower"}), DC),
        ({"op": "crosses_above", "left": {"indicator": "ema_fast"}, "right": {"indicator": "ema_fast"}}, []),
        ({"op": "between", "value": {"input": "close"}, "low": {"value": 10}, "high": {"value": 5}}, []),
        (cmp({"input": "hour_utc"}, ">", {"value": 23}), []),
    ],
    ids=["rsi_band", "strictness", "rsi_over_100", "const", "close_above_donchian", "low_below_donchian",
         "self_cross", "between", "hour_24"],
)  # fmt: skip
def test_contradictory_entries_are_rejected(entry: dict[str, Any], indicators: list[dict[str, Any]]) -> None:
    assert "CONTRADICTORY_RULE" in contradiction(entry, indicators)


@pytest.mark.parametrize(
    ("entry", "indicators"),
    [
        ({"op": "all", "args": [cmp({"indicator": "rsi"}, ">=", {"value": 50}),
                                cmp({"indicator": "rsi"}, "<=", {"value": 50})]}, RSI),
        (cmp({"input": "close"}, ">", {"indicator": "dc", "output": "upper", "bars_ago": 1}), DC),
        (cmp({"indicator": "rsi"}, ">=", {"value": 100}), RSI),
    ],
    ids=["rsi_equal_bounds", "donchian_previous_bar", "rsi_at_100"],
)  # fmt: skip
def test_possible_entries_are_not_flagged(entry: dict[str, Any], indicators: list[dict[str, Any]]) -> None:
    assert "CONTRADICTORY_RULE" not in contradiction(entry, indicators)


# --- risk, data availability, warnings ----------------------------------------------------------------


def test_sizing_cannot_exceed_leverage_cap() -> None:
    data = ema_cross()
    data["risk"]["position_sizing"]["value"] = 400  # 4x notional with a 3x cap
    assert "SIZING" in codes(data)


def test_slippage_limited_to_what_nautilus_can_model() -> None:
    data = ema_cross()
    data["costs"]["slippage_ticks"] = 2
    assert "SLIPPAGE" in codes(data)


def test_volume_and_funding_need_data() -> None:
    data = json.loads((CATALOGUE_DIR / "10_gold_session_breakout.json").read_text())
    data["indicators"].append({"id": "obv", "type": "obv"})
    data["rules"]["entry_long"]["args"].append(cmp({"input": "funding_rate"}, ">", {"value": 0}))
    result = validate(data)
    assert "NO_FUNDING_DATA" in [e.code for e in result.errors]
    assert "VOLUME_MAYBE_MISSING" in [w.code for w in result.warnings]
    assert "NO_VOLUME_DATA" in codes(data, ValidationContext(has_volume=False, has_funding=False))


def test_direction_needs_matching_entry_rules() -> None:
    data = ema_cross()
    data["rules"]["entry_short"] = None
    assert "MISSING_ENTRY" in codes(data)
    data = ema_cross()
    data["market"]["direction"] = "long"
    result = validate(data)
    assert result.ok and {w.code for w in result.warnings} == {"UNUSED_RULE"}


def test_overfitting_warning_counts_tunable_parameters() -> None:
    data = ema_cross()
    data["indicators"].append({"id": "rsi", "type": "rsi", "params": {"period": 14}})
    result = validate(data)
    assert result.ok
    assert any(w.code == "OVERFITTING_RISK" for w in result.warnings)


def test_exported_json_schema_is_current() -> None:
    exported = json.loads((CATALOGUE_DIR.parent / "schema.json").read_text())
    assert exported == json_schema(), "run `python -m strategy_lab.spec` to regenerate schema.json"


def test_spec_round_trips_through_json() -> None:
    spec = StrategySpec.model_validate(ema_cross())
    again = StrategySpec.model_validate_json(spec.model_dump_json())
    assert again == spec
    assert copy.deepcopy(spec) == spec
