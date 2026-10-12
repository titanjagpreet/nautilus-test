"""Run the robustness lab on a spec file and print the score; the full report is written as JSON.

    uv run python -m strategy_lab.lab strategy_lab/spec/catalogue/01_ema_crossover.json \\
        --start 2023-07-01 --end 2026-07-01 [--params ema_fast.period,ema_slow.period] [--optuna 50] \\
        [--out runs/lab/ema.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from strategy_lab.lab.evaluator import OBJECTIVES
from strategy_lab.lab.robustness import run_lab
from strategy_lab.spec.schema import StrategySpec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--start", default="2023-07-01")
    parser.add_argument("--end", default="2026-07-01")
    parser.add_argument("--params", help="1-2 tunable parameters for the heat-map and tuning (comma-separated)")
    parser.add_argument("--objective", default="sharpe", choices=OBJECTIVES)
    parser.add_argument("--optuna", type=int, default=0, help="Optuna trials (0 = off)")
    parser.add_argument("--out", type=Path, help="write the full report as JSON")
    args = parser.parse_args()

    spec = StrategySpec.model_validate_json(args.spec.read_text(encoding="utf-8"))
    report = run_lab(
        spec,
        pd.Timestamp(args.start, tz="UTC"),
        pd.Timestamp(args.end, tz="UTC"),
        parameters=args.params.split(",") if args.params else None,
        objective=args.objective,
        optuna_trials=args.optuna,
        progress=lambda stage, fraction: print(f"\r{fraction:4.0%} {stage:<16}", end="", flush=True),
    )
    print(
        f"\n{report.spec_name}: robustness score {report.score:.0f}/100 "
        f"({report.runs} backtests in {report.wall_seconds:.0f} s)"
    )
    for part in report.parts:
        print(f"  {part.name:<26} {part.points:5.1f} / {part.weight:g}   {part.detail}")
    for warning in report.warnings:
        print(f"  ! {warning.code}: {warning.message}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report.as_dict(), indent=1), encoding="utf-8")
        print(f"report: {args.out}")


if __name__ == "__main__":
    main()
