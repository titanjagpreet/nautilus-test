"""LLM judge for the eval: does each candidate spec implement what the user asked for?

The judge never sees the model-written description — only the deterministic plain-English rendering of each
candidate's rules, risk and costs (``spec/render.py``) — so a persuasive description cannot earn points. All
providers' candidates for one prompt are graded in a single call, under anonymous labels in a shuffled order.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

from strategy_lab.ai.providers.base import LLMProvider
from strategy_lab.spec.render import render
from strategy_lab.spec.schema import StrategySpec

JUDGE_MAX_OUTPUT_TOKENS = 4096

JUDGE_SYSTEM = """You grade how faithfully candidate trading strategies implement a user's request. You are \
the judge in an evaluation of AI strategy writers for Strategy Lab, a backtesting tool for the BTC-PERP and \
XAU-PERP perpetual futures. Each candidate is shown as a mechanical plain-English rendering of its spec: \
market, indicators, entry and exit rules (checked at bar close, filled at the next bar's open), risk settings \
and costs.

Score every candidate:
- 2 = implements every element the user stated (market, timeframe, direction, indicators and their \
parameters, entry and exit logic, stop, target, sizing, other risk and cost settings). Sensible choices for \
anything the user left open are fine.
- 1 = the core idea is right, but at least one element the user stated is missing, different or only \
approximated.
- 0 = the core logic is wrong or missing, or there is no strategy ("NO STRATEGY").

Rules for grading:
- Judge only against the request (for an edit: the original strategy plus the requested change; anything \
else that changed counts against it). For a Pine Script translation, the request is the script's logic.
- The spec format cannot express arithmetic between values (e.g. "1% above VWAP"); a close, clearly \
equivalent approximation can still score 2 if it preserves the intent, otherwise 1.
- Ignore names, wording and formatting. Do not reward extra features nobody asked for.
- Give one short reason per candidate naming what is missing or wrong (or "matches").

Reply with a JSON object: {"verdicts": [{"candidate": "<label>", "score": 0 | 1 | 2, "reason": "..."}]} with \
one verdict per candidate, in the order given."""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "string"},
                    "score": {"type": "integer", "enum": [0, 1, 2]},
                    "reason": {"type": "string"},
                },
                "required": ["candidate", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Verdict:
    score: int
    reason: str


def rendering(spec: StrategySpec | None) -> str:
    if spec is None:
        return "NO STRATEGY"
    return render(spec.model_copy(update={"meta": spec.meta.model_copy(update={"description": ""})}))


def judge_message(
    request: str, candidates: dict[str, str], base: StrategySpec | None, seed: str
) -> tuple[str, dict[str, str]]:
    """The user message and the label → candidate-key mapping (labels are shuffled per item, reproducibly)."""
    keys = sorted(candidates)
    random.Random(seed).shuffle(keys)
    labels = {chr(ord("A") + i): key for i, key in enumerate(keys)}
    parts = []
    if base is not None:
        parts.append(f"ORIGINAL STRATEGY:\n{rendering(base)}\n\nREQUESTED CHANGE:\n{request}")
    else:
        parts.append(f"REQUEST:\n{request}")
    for label, key in labels.items():
        parts.append(f"CANDIDATE {label}:\n{candidates[key]}")
    return "\n\n---\n\n".join(parts), labels


@dataclass(frozen=True)
class Judgement:
    verdicts: dict[str, Verdict]  # by candidate key
    labels: dict[str, str]  # anonymous label → candidate key, as shown to the judge
    reply: dict[str, Any]  # the judge's raw reply, kept for the record


def _label(text: object) -> str:
    """'A', 'Candidate A', 'CANDIDATE A:' → 'A'."""
    letters = re.findall(r"\b([A-Z])\b", str(text).upper())
    return letters[-1] if letters else ""


def judge(
    provider: LLMProvider, request: str, candidates: dict[str, str], base: StrategySpec | None, seed: str
) -> Judgement:
    message, labels = judge_message(request, candidates, base, seed)
    provider.max_output_tokens = JUDGE_MAX_OUTPUT_TOKENS
    data, _ = provider.complete_json(JUDGE_SYSTEM, message, JUDGE_SCHEMA, feature="judge")
    verdicts: dict[str, Verdict] = {}
    for verdict in data.get("verdicts", []):
        key = labels.get(_label(verdict.get("candidate", "")))
        if key is not None and verdict.get("score") in (0, 1, 2):
            verdicts[key] = Verdict(int(verdict["score"]), str(verdict.get("reason", "")))
    return Judgement(verdicts, labels, data)
