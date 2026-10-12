"""Phase 0 network check: HTTPS reachability of every host the project depends on.

Prints a table and, with ``--json PATH``, writes the raw results so later phases
(and PROGRESS.md) can pick data sources and fallbacks from facts, not guesses.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass

import httpx

HOSTS: dict[str, str] = {
    "data.binance.vision": "Binance public data (BTC spot/futures klines, funding)",
    "mainnet.zklighter.elliot.ai": "Lighter REST API (BTC/XAU perp candles, funding)",
    "datafeed.dukascopy.com": "Dukascopy tick/candle feed (XAUUSD bid/ask), dukascopy-node <= 1.46",
    "jetta.dukascopy.com": "Dukascopy candle API used by dukascopy-node >= 1.49",
    "pypi.org": "Python packages",
    "registry.npmjs.org": "npm packages (dukascopy-node, JS assets)",
    "github.com": "Source code, fallback datasets",
    "raw.githubusercontent.com": "Fallback datasets (pinned raw files)",
    "api.deepseek.com": "DeepSeek LLM API",
    "api.moonshot.ai": "Moonshot / Kimi LLM API",
    "api.anthropic.com": "Anthropic Claude API (optional provider)",
    "cdn.jsdelivr.net": "CDN for Lightweight Charts / Plotly / HTMX",
}


@dataclass(frozen=True)
class HostResult:
    host: str
    purpose: str
    reachable: bool
    status: int | None
    latency_ms: float | None
    error: str | None


def check_host(client: httpx.Client, host: str, purpose: str) -> HostResult:
    """A host counts as reachable if a TLS connection completes and any HTTP status comes back."""
    start = time.perf_counter()
    try:
        response = client.get(f"https://{host}/")
    except httpx.HTTPError as exc:
        return HostResult(host, purpose, False, None, None, f"{type(exc).__name__}: {exc}"[:120])
    latency = (time.perf_counter() - start) * 1000
    return HostResult(host, purpose, True, response.status_code, round(latency, 1), None)


def run_checks(timeout_s: float = 15.0) -> list[HostResult]:
    with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
        return [check_host(client, host, purpose) for host, purpose in HOSTS.items()]


def render_table(results: list[HostResult]) -> str:
    lines = [
        "| Host | Purpose | Reachable | HTTP | Latency ms | Error |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.host} | {r.purpose} | {'yes' if r.reachable else 'NO'} | "
            f"{r.status or ''} | {r.latency_ms or ''} | {r.error or ''} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="Also write raw results to this path")
    args = parser.parse_args()
    results = run_checks()
    print(render_table(results))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([asdict(r) for r in results], fh, indent=2)


if __name__ == "__main__":
    main()
