"""``make demo``: Strategy Lab end to end on the downloaded history (run ``make data`` first).

1. data coverage; 2. validate the 10 catalogue strategies; 3. one backtest on both engines (same trades);
4. the robustness lab on a catalogue strategy; 5. the AI builder (only if an LLM API key is set) generating a
strategy, which is validated and backtested. Results are stored like the UI's, so ``make ui`` shows them.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from strategy_lab.ai.builder import Builder
from strategy_lab.ai.config import providers_with_keys
from strategy_lab.ai.ledger import BudgetExceededError
from strategy_lab.ai.providers.base import ProviderError
from strategy_lab.api import services
from strategy_lab.api.store import Store
from strategy_lab.api.worker import run_job

CATALOGUE = services.CATALOGUE_DIR
IDEA = (
    "BTC on 1-hour bars: go long when RSI(14) crosses back above 30 while the close is above the 200 EMA; "
    "exit when RSI rises above 65. 2 ATR stop, 20% of equity at 2x leverage."
)


def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 70 - len(title)))


def job(store: Store, kind: str, request: dict[str, Any]) -> dict[str, Any]:
    job_id = store.create_job(kind, request)
    run_job(job_id, str(store.path))
    result = store.job(job_id)
    assert result is not None
    if result["status"] != "done":
        sys.exit(f"{kind} job failed: {result['error']}")
    return result


def backtest(store: Store, spec: dict[str, Any], start: str, end: str, engine: str) -> dict[str, Any]:
    done = job(store, "backtest", {"spec": spec, "start": start, "end": end, "engine": engine})
    row = store.backtest(done["result_id"])
    assert row is not None
    m = row["metrics"]
    print(
        f"  {engine:<9} #{row['id']}: {m['trades']} trades, net {m['net_pnl']:+,.2f} USDC "
        f"({m['net_return_pct']:+.1f}%), Sharpe {m['sharpe']:.2f}, max DD {m['max_drawdown_pct']:.1f}% "
        f"— {row['wall_s']:.2f} s ({row['engine_version']})"
    )
    return row


def main() -> None:
    t0 = time.perf_counter()
    store = Store()

    section("1. Data")
    coverage = services.coverage()
    if not coverage.get("markets"):
        sys.exit("No data downloaded. Run `make data` first.")
    for market, info in coverage["markets"].items():
        for kind in ("bars", "funding"):
            for src in info[kind]:
                flag = "used" if src["used"] else "fallback"
                print(
                    f"  {market} {kind:<7} {src['source']:<40} {src['first'][:10]} → {src['last'][:10]} "
                    f"{src['rows']:>10,} rows ({flag})"
                )

    section("2. Validate the catalogue")
    for path in sorted(CATALOGUE.glob("*.json")):
        checked = services.check(json.loads(path.read_text()))
        notes = ", ".join(w["code"] for w in checked["warnings"]) or "no warnings"
        print(
            f"  {'ok ' if checked['ok'] else 'ERR'} {path.stem:<32} {len(checked['parameters'])} tunable; {notes}"
        )

    section("3. One backtest, both engines (EMA crossover, BTC 2024)")
    ema = json.loads((CATALOGUE / "01_ema_crossover.json").read_text())
    fast = backtest(store, ema, "2024-01-01", "2025-01-01", "fast")
    nautilus = backtest(store, ema, "2024-01-01", "2025-01-01", "nautilus")
    same = [(t["entry_time"], t["exit_time"]) for t in fast["result"]["trades"]] == [
        (t["entry_time"], t["exit_time"]) for t in nautilus["result"]["trades"]
    ]
    diff = abs(fast["metrics"]["net_pnl"] - nautilus["metrics"]["net_pnl"])
    print(
        f"  identical trades: {same}; P&L difference {diff:.2e} USDC; "
        f"speed-up ×{nautilus['wall_s'] / fast['wall_s']:.0f}"
    )

    section("4. Robustness lab (Donchian breakout)")
    donchian = json.loads((CATALOGUE / "03_donchian_breakout.json").read_text())
    start, end = services.default_range("BTC-PERP")
    done = job(store, "lab", {"spec": donchian, "start": start, "end": end, "grid_points": 7})
    report = store.lab_report(done["result_id"])
    assert report is not None
    r = report["report"]
    print(f"  {start} → {end}: score {r['score']:.0f}/100 ({r['runs']} backtests in {r['wall_seconds']:.0f} s)")
    for part in r["parts"]:
        print(f"    {part['name']:<26} {part['points']:5.1f} / {part['weight']:g}  {part['detail']}")
    for warning in r["warnings"]:
        print(f"    ! {warning['code']}: {warning['message']}")

    section("5. AI builder")
    available = providers_with_keys()
    if not available:
        print("  skipped: no LLM API key in .env (DEEPSEEK_API_KEY / MOONSHOT_API_KEY / ANTHROPIC_API_KEY)")
    else:
        provider = available[0]
        print(f"  {provider}: {IDEA}")
        try:
            result = Builder.for_provider(provider).generate(IDEA, allow_questions=False)
        except (BudgetExceededError, ProviderError) as exc:
            print(f"  stopped: {exc}")
        else:
            print(
                f"  status {result.status}; {len(result.attempts)} call(s), ${result.cost_usd:.5f}, "
                f"{result.latency_s:.1f} s; repairs {result.repairs}, escalated {result.escalated}"
            )
            for line in result.assumptions:
                print(f"    assumption: {line}")
            if result.spec is not None:
                spec = result.spec.model_dump(mode="json")
                print(f"  saved as saved:{store.save_spec(spec)}")
                backtest(store, spec, "2024-01-01", "2025-01-01", "fast")
            for error in result.errors:
                print(f"    error: {error}")

    section("Done")
    print(f"  {time.perf_counter() - t0:.0f} s. Results are in {store.path}; `make ui` → http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
