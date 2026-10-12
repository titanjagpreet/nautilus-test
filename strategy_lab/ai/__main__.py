"""Command line for the AI builder.

    uv run python -m strategy_lab.ai generate "Long BTC 1h when the 20 EMA crosses above the 50 EMA"
    uv run python -m strategy_lab.ai edit spec.json "use 2x leverage"
    uv run python -m strategy_lab.ai explain spec.json
    uv run python -m strategy_lab.ai from_pine script.pine
    uv run python -m strategy_lab.ai spend

``--provider deepseek|moonshot|anthropic`` picks the writer (default: ``default_writer`` in config/llm.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from strategy_lab.ai.builder import Builder, BuildResult
from strategy_lab.ai.config import llm_config
from strategy_lab.ai.ledger import Ledger
from strategy_lab.ai.providers import MissingKeyError
from strategy_lab.spec.render import render
from strategy_lab.spec.schema import StrategySpec


def show(result: BuildResult) -> None:
    for attempt in result.attempts:
        cost = attempt.usage.cost_usd if attempt.usage else 0.0
        verdict = f"{len(attempt.errors)} error(s)" if attempt.errors else "accepted"
        print(f"[{attempt.kind}] {attempt.provider}:{attempt.model} ${cost:.5f} — {verdict}", file=sys.stderr)
        for error in attempt.errors:
            print(f"    {error}", file=sys.stderr)
    print(
        f"status: {result.status}   cost: ${result.cost_usd:.5f}   time: {result.latency_s:.1f} s", file=sys.stderr
    )
    if result.questions:
        print("Questions:\n" + "\n".join(f"- {q}" for q in result.questions))
    if result.refusal:
        print(f"Refused: {result.refusal}")
    if result.explanation:
        print(result.explanation)
    if result.spec is not None:
        print(render(result.spec), file=sys.stderr)
        sections = {
            "Changes": result.diff,
            "Assumptions": result.assumptions,
            "Not translated": result.unsupported,
            "Warnings": result.warnings,
        }
        for title, lines in sections.items():
            if lines:
                print(f"\n{title}:\n" + "\n".join(f"- {line}" for line in lines), file=sys.stderr)
        print(result.spec.model_dump_json(indent=2, exclude_none=True))
    if result.errors:
        print("Failed:\n" + "\n".join(f"- {e}" for e in result.errors))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=sorted(llm_config().providers))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate").add_argument("idea")
    edit = sub.add_parser("edit")
    edit.add_argument("spec", type=Path)
    edit.add_argument("request")
    sub.add_parser("explain").add_argument("spec", type=Path)
    sub.add_parser("from_pine").add_argument("script", type=Path)
    sub.add_parser("spend")
    args = parser.parse_args()

    if args.command == "spend":
        ledger = Ledger()
        spend = {
            "total": ledger.spent(),
            "eval": ledger.spent("eval"),
            "by": ledger.summary(),
            "mode_rejections": ledger.mode_rejections(),
            "notes": ledger.notes(),
        }
        print(json.dumps(spend, indent=2))
        return
    try:
        builder = Builder.for_provider(args.provider)
    except MissingKeyError as exc:
        sys.exit(str(exc))
    if args.command == "generate":
        show(builder.generate(args.idea))
    elif args.command == "edit":
        show(builder.edit(StrategySpec.model_validate_json(args.spec.read_text(encoding="utf-8")), args.request))
    elif args.command == "explain":
        show(builder.explain(StrategySpec.model_validate_json(args.spec.read_text(encoding="utf-8"))))
    else:
        show(builder.from_pine(args.script.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
