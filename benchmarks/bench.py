"""``make bench``: speed and memory of both engines on the same workload, written to REPORT.md.

Workload: the catalogue EMA crossover (1h bars, executed on 1-minute bars) over one year of real BTC data
(2024-01-01 → 2025-01-01, ~527k 1m bars). Scenarios, each on both engines, single core and all cores:

* one backtest;
* a 144-combination sweep (EMA fast 12 values × slow 12 values);
* a 1,600-combination sweep (40 × 40).

Peak memory = largest sum of RSS over this process and all its children, sampled every 0.25 s. Results are
checkpointed per scenario in ``benchmarks/results/bench.json`` (re-running skips finished scenarios; delete the
file to start over) and rendered into REPORT.md between the BENCH markers.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import psutil

from strategy_lab.engines.contracts import contract_spec
from strategy_lab.engines.fast import runner as fast
from strategy_lab.engines.inputs import MarketData, load_market
from strategy_lab.lab.sweep import grid, run_grid
from strategy_lab.spec.schema import StrategySpec

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "benchmarks" / "results" / "bench.json"
REPORT = ROOT / "REPORT.md"
SPEC = ROOT / "strategy_lab" / "spec" / "catalogue" / "01_ema_crossover.json"
START, END = pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")
CORES = os.cpu_count() or 1
SWEEPS = {
    "sweep_144": {"ema_fast.period": list(range(5, 65, 5)), "ema_slow.period": list(range(70, 310, 20))},
    "sweep_1600": {"ema_fast.period": list(range(5, 45)), "ema_slow.period": list(range(60, 260, 5))},
}


class PeakMemory:
    """Sample RSS of this process tree in a background thread."""

    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        me = psutil.Process()
        while not self._stop.is_set():
            total = 0
            for proc in [me, *me.children(recursive=True)]:
                with contextlib.suppress(psutil.Error):  # a worker may exit between listing and reading
                    total += proc.memory_info().rss
            self.peak = max(self.peak, total)
            time.sleep(0.25)

    def __enter__(self) -> PeakMemory:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()


def measure(fn: Callable[[], Any]) -> dict[str, float]:
    with PeakMemory() as mem:
        t0 = time.perf_counter()
        fn()
        wall = time.perf_counter() - t0
    return {"wall_s": round(wall, 2), "peak_rss_mb": round(mem.peak / 2**20, 1)}


def _nautilus_run(spec: StrategySpec, market: MarketData) -> Any:
    # Imported lazily: spawned sweep workers re-import this module, and the fast-engine workers must not pay
    # for NautilusTrader's ~300 MB of imports.
    from strategy_lab.engines.nautilus import spec_runner  # noqa: PLC0415

    return spec_runner.run_spec(spec, START, END, market=market)


def scenarios(spec: StrategySpec) -> dict[str, Callable[[], Any]]:
    market = load_market("BTC-PERP", START, END, contract_spec("BTC-PERP").price_decimals)
    out: dict[str, Callable[[], Any]] = {
        "single/fast/cold (incl. JIT compile)": lambda: fast.run_spec(spec, START, END, market=market),
        "single/fast/warm": lambda: fast.run_spec(spec, START, END, market=market),
        "single/nautilus": lambda: _nautilus_run(spec, market),
    }
    for name, axes in SWEEPS.items():
        points = grid(axes)
        for engine in ("fast", "nautilus"):
            for workers in (1, CORES):
                label = f"{name}/{engine}/{workers} core{'s' if workers > 1 else ''}"
                out[label] = functools.partial(
                    run_grid, spec, points, START, END, engine, workers, market=market if workers == 1 else None
                )
    return out


def render(results: dict[str, Any]) -> str:
    lines = [
        "| scenario | engine | cores | wall time | peak RSS | per backtest |",
        "|---|---|---|---|---|---|",
    ]
    for label, r in results.items():
        if label.startswith("_"):
            continue
        parts = label.split("/")
        kind, engine = parts[0], parts[1]
        cores = parts[2] if kind != "single" else "1"
        if kind == "single":
            engine_label = f"{engine} ({parts[2]})" if len(parts) > 2 else engine
            n = 1
        else:
            engine_label = engine
            n = int(kind.split("_")[1])
        per = r["wall_s"] / n
        lines.append(
            f"| {kind.replace('_', ' ')} | {engine_label} | {cores} | {r['wall_s']:,.1f} s | "
            f"{r['peak_rss_mb']:,.0f} MB | {per:.3f} s |"
        )
    meta = results.get("_meta", {})
    lines += [
        "",
        f"Machine: {meta.get('cpus')} vCPU, {meta.get('ram_gb')} GB RAM; workload: {meta.get('workload')}.",
    ]
    return "\n".join(lines)


def write_report(results: dict[str, Any]) -> None:
    begin, end = "<!-- BENCH:BEGIN -->", "<!-- BENCH:END -->"
    text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else f"# REPORT\n\n{begin}\n{end}\n"
    if begin not in text:
        text += f"\n{begin}\n{end}\n"
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    REPORT.write_text(f"{head}{begin}\n{render(results)}\n{end}{tail}", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="run only scenarios whose label contains this text")
    args = parser.parse_args()
    spec = StrategySpec.model_validate_json(SPEC.read_text(encoding="utf-8"))
    results: dict[str, Any] = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    results["_meta"] = {
        "cpus": CORES,
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "workload": f"{spec.meta.name}, BTC-PERP 1h on 1m execution, {START.date()} → {END.date()}",
    }
    for label, fn in scenarios(spec).items():
        if label in results or (args.only and args.only not in label):
            continue
        print(f"running {label} ...", flush=True)
        results[label] = measure(fn)
        print(f"  {results[label]}", flush=True)
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(results)
    print(render(results))


if __name__ == "__main__":
    main()
