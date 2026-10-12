# PROGRESS

Running log of what is done, measured numbers, problems and decisions. Updated at the end of every phase.

## Definition of done

- [x] Network check done; sources and fallbacks recorded.
- [x] BTC and XAU history downloaded, checksummed where possible, validated, resampled, documented in DATA.md.
- [x] The hand-written Nautilus strategy runs with fees, slippage and funding visible; speed and memory measured.
- [x] Spec schema, validator (look-ahead and higher-timeframe guards), plain-language renderer, 10 catalogue strategies.
- [x] SpecStrategy runs any valid spec in Nautilus.
- [x] The fast engine matches Nautilus on all 10 catalogue strategies within the stated tolerance, or every difference is documented.
- [ ] AI generate, edit, explain and from_pine work through the provider layer (DeepSeek default, Kimi alternative, Claude Haiku optional) with validation and repair, escalation, caching and cost logging.
- [ ] The eval has run on every provider with a key; the comparison and recommendation are in REPORT.md; total API spend is under budget.
- [ ] The lab works: out-of-sample, walk-forward, heat-map, Monte Carlo, score with its parts, warnings.
- [ ] UI pages work: Builder, Backtest, Lab, Compare, Costs.
- [ ] All tests pass; ruff and mypy are clean; `make demo` works from a clean checkout.
- [ ] LEARNINGS.md, ARCHITECTURE.md, DATA.md and REPORT.md are written with real measured numbers.
- [ ] No secrets in git; no live-trading code; no fabricated data.

---

## Phase 0 — environment and network check (2026-10-12)

**Environment.** Cloud sandbox: Linux x86_64, 4 vCPU, 15 GiB RAM, no swap. Python 3.13.16, uv 0.11.32,
Node 22.22.0. All outbound HTTPS goes through an egress proxy whose policy is a host allow-list.

**Done.**
- uv project (`pyproject.toml`, every dependency pinned with `==`, `uv.lock` committed).
- `Makefile` (`make help` lists targets), `.gitignore` (`.env`, `data/`, caches, SQLite), `.env.example`,
  pre-commit with ruff (check + format).
- `scripts/check_network.py` (`make network`).

**Network check result** (`make network`, 2026-10-12, from the sandbox):

| Host | Purpose | Reachable | HTTP | Note |
|---|---|---|---|---|
| data.binance.vision | Binance public data (BTC spot/futures klines, funding) | **NO** | – | proxy 403 (policy) |
| mainnet.zklighter.elliot.ai | Lighter REST API (BTC/XAU perp candles, funding) | **NO** | – | proxy 403 (policy) |
| datafeed.dukascopy.com | Dukascopy feed (XAUUSD bid/ask) | **NO** | – | proxy 403 (policy) |
| pypi.org | Python packages | yes | 200 | |
| registry.npmjs.org | npm packages | yes | 200 | |
| github.com | source code, fallback datasets | yes | 400 on `/` | TLS + HTTP OK; raw.githubusercontent.com, media.githubusercontent.com (LFS) and api.github.com also reachable |
| api.deepseek.com | DeepSeek LLM API | **NO** | – | proxy 403 (policy) |
| api.moonshot.ai | Moonshot / Kimi LLM API | **NO** | – | proxy 403 (policy) |
| api.anthropic.com | Claude API (optional provider) | yes | 404 on `/` | reachable |
| cdn.jsdelivr.net | CDN for chart/HTMX JS | **NO** | – | proxy 403 (policy) |

A wider probe also found these blocked: api.binance.com, fapi.binance.com, huggingface.co, kaggle.com,
stooq.com, query1.finance.yahoo.com, histdata.com, unpkg.com, cdnjs.cloudflare.com, docs.lighter.xyz,
api-docs.deepseek.com, platform.moonshot.ai, nautilustrader.io.

**Decisions taken from this.**
1. **Every primary source is still implemented in code** (Binance public data, Lighter REST, Dukascopy) so
   `make data` works on a normal machine. In this sandbox those downloads fail fast and are logged as
   "blocked", and the pipeline moves to the next fallback (rule 2: never fabricate).
2. **I do not route around the block** (e.g. via the S3 origin bucket behind data.binance.vision): the proxy
   policy says denied hosts are to be reported, not bypassed. Fallbacks must be *different publishers* whose
   data is hosted on an allowed host (GitHub, PyPI, npm). Chosen in Phase 1.
3. **LLM providers:** DeepSeek and Moonshot cannot be called from this sandbox. Their code paths are built
   and tested with recorded responses; the live eval runs on whichever providers have a key *and* are
   reachable when `make eval` runs. Anthropic is reachable.
4. **UI assets:** templates load pinned versions from cdn.jsdelivr.net (as specified); `make setup`
   additionally vendors the same pinned files from registry.npmjs.org into a git-ignored folder used as an
   automatic fallback when the CDN is unreachable (it is, here).
5. **Lighter access:** plain HTTPS (httpx) instead of `lighter-sdk` 1.1.6, because the SDK pins
   `urllib3<2.1` and pulls in `eth-account` (transaction signing), which a backtest-only project must not
   need. Field names are taken from the SDK's own source/docs.
6. **NautilusTrader 1.231.0** installed (latest stable on PyPI; 2.0.0rc1–rc6 exist and are deliberately not
   used).

**How to unblock (for the owner):** in the cloud environment settings → Network access, add the denied
hosts to *Allowed domains* (docs: https://code.claude.com/docs/en/cloud-environments#network-access), or
simply run `make data` / `make eval` on your own machine.

## Phase 1 — historical data (2026-10-12) ✅

**Acceptance:** ≥ 3 years of BTC 1m ✅ (9.1 years) · ≥ 3 years of XAU 1m ✅ (5.4 years) · quality report ✅
(`data/quality_report.md`) · resampling tests ✅ (`tests/test_resample.py`, hand-made example).

**Obtained** (details, URLs, licences: DATA.md):

| dataset | rows (1m) | range (UTC) | completeness | notes |
|---|---|---|---|---|
| Binance spot BTCUSDT (GitHub republication) | 4,789,279 | 2017-08-17 → 2026-09-30 | 99.82% | 33 gaps (maintenance) |
| Bitstamp BTCUSD | 6,444,863 | 2012-01-01 → 2026-09-30 | 83.1% of minutes traded | 1.31 M filler rows dropped |
| HistData XAUUSD (bid) | 1,870,538 | 2021-01-03 → 2026-05-29 | 97.64% excl. closures | timezone verified from data |
| Binance BTCUSDT funding (8 h) | 7,457 | 2019-09-10 → 2026-06-30 | 100% | 0 mismatches vs 2 other exports |

**Blocked here (implemented, documented, would run on an open network):** Binance data.binance.vision (spot,
USD-M futures, fundingRate — with SHA-256 `.CHECKSUM` verification), Lighter REST (BTC/XAU perps, funding,
market specs), Dukascopy (bid+ask XAU via dukascopy-node), Kaggle (no token). No Lighter data at all ⇒ the
Binance-futures-vs-Lighter and Dukascopy-vs-Lighter cross-checks could not run; a Binance-vs-Bitstamp
cross-check ran instead (median |diff| 5.8 bps; worst minutes = 2018 Tether de-peg, 2019 Bitstamp flash crash).

**Problems hit and fixed.**
- HistData's documented timezone ("EST, no DST") is wrong for these files; the clock follows **EU** DST.
  Detected by scoring three hypotheses against the 17:00 New York gold break (DATA.md §3.7).
- Bitstamp's publisher fills outages with flat candles → dropped (never keep invented prices).
- US holiday early closes looked like XAU data gaps → classifier now uses a US exchange-holiday calendar.
- Provenance CSV was accidentally parsed as prices (file name filter) → files are now selected by role.

**Decisions.** Third-party GitHub copies on an allowed host are used and labelled; the blocked service's own
endpoints (e.g. its S3 origin) are not. Pinned commits + SHA-256 manifest for reproducibility. Data stays
git-ignored (`data/`), ~1.4 GB on disk (960 MB raw, 290 MB canonical, 124 MB resampled).

## Phase 2 — NautilusTrader fundamentals (2026-10-12) ✅

**Acceptance:** the hand-written strategy runs end to end on real data with fees, slippage and funding visible ✅;
speed and memory measured ✅.

**Built.** `strategy_lab/engines/nautilus/`: BTC-PERP / XAU-PERP `CryptoPerpetual`s on a simulated venue
`LIGHTER` (margin account, netting, leverage 3x default, 10,000 USDC); maker/taker fees with configurable
profiles (`config/fee_profiles.json`: `lighter_standard` 0/0 bps, `lighter_premium` 0.4/2.8 bps); an
order-type-aware fill model (1 tick against you on market and stop fills, never on limits); bar execution with
adaptive high/low ordering; a funding `SimulationModule`; bar loading via `BarDataWrangler` and via
`ParquetDataCatalog` (identical results); the EMA(12/48) + ATR(14) bracket strategy (stop 2×ATR, target 3×ATR,
20% of equity).

**Reference run** — BTC 15m strategy, venue executing on 1m bars, 2024-07-01 → 2026-07-01, Binance spot BTCUSDT
proxy, funding from Binance BTCUSDT (8h):

| fee profile | positions | net PnL | fees | funding paid (net) | funding events |
|---|---|---|---|---|---|
| lighter_premium | 1,760 | **−1,175.51 USDC (−11.8%)** | 1,614.05 | +0.14 | 729 |
| lighter_standard | 1,760 | **+422.91 USDC (+4.2%)** | 0.00 | +0.48 | 729 |

Nautilus portfolio statistics (premium): win rate 37.3%, profit factor 0.81, Sharpe (252 d) −1.14, Sortino
−1.45, avg winner +16.27, avg loser −10.73. Fills, positions, account and funding ledgers are written by
`python -m strategy_lab.engines.nautilus.handwritten --out runs/…`.

**Funding.** Nautilus 1.231 does not settle funding (`FundingRateUpdate` is data only; LEARNINGS §6) → our
`FundingModule` charges `size × price × rate` at each funding time via `exchange.adjust_account`, reported as a
separate line. Verified by a hand-made test and by reconciling ledgers to the account balance.

**Measurements** (LEARNINGS §12): empty node 370 MB; 1 y of 1m bars with a 1m strategy **575 s stock / 127 s
patched**, 1.3 GB; 5 y of 15m bars 68 s / 30 s, ~1.05 GB.

**Problems found and fixed.**
- Market orders fill at the signal bar's close; stock slippage also slips take-profit limits; neither bar
  ordering is "stop first" → order-type-aware fill model now; spec engine semantics handled in Phase 3.
- `reject_stop_orders=True` leaves a position unprotected when its stop is already through the market → False.
- pandas 3 µs timestamps silently broke funding (and nearly bar timestamps) → normalise to ns at storage.
- Quadratic `pd.concat` in Nautilus's `PortfolioAnalyzer` → tested patch (4.5× faster on 1m).

## Phase 3 — the strategy format (2026-10-12) ✅

**Acceptance:** all 10 catalogue strategies validate and backtest in Nautilus on real data ✅
(`tests/test_spec_nautilus.py`) · every indicator has a reference-calculation test ✅ (`tests/test_indicators.py`,
rtol 1e-9, warm-up boundaries included) · look-ahead and higher-timeframe guards proven by tests ✅
(`tests/test_validator.py`, 43 tests) · plain-language renderer ✅ (`spec/render.py`).

**Built** (`strategy_lab/spec/`): Pydantic v2 schema `spec_version 0.1` with exported JSON Schema
(`schema.json`, `python -m strategy_lab.spec`); indicator catalogue (18 types, bounds, outputs, Nautilus
mapping); validator returning every error at once with JSON paths; renderer; tunable-parameter listing/setting;
bar-by-bar evaluator; shared position-management decisions; 10 catalogue strategies with descriptions.
`engines/nautilus/`: generic `SpecStrategy` (no code generation, no eval), the execution feed, the spec runner,
and the engine-neutral `BacktestResult` (`engines/results.py`).

**Execution semantics** are written down in ARCHITECTURE.md and implemented in Nautilus with 1 ns latency, an
"open" bar per base bar and a direction-aware intrabar path fed through a streaming generator (LEARNINGS §7).
On every catalogue strategy, our trade + funding ledger reproduces Nautilus's own final account balance to
< 1e-6 USDC.

**Spec additions beyond the brief (and why).** `hour_utc` input (needed for the gold session breakout);
`funding_rate` input normalised to an 8-hour rate (Binance funds every 8 h, Lighter hourly); an `execution`
section whose only valid values are the safe ones — the unsafe ones exist so Pine-style look-ahead settings
(`process_orders_on_close`, `lookahead_on`) parse and are rejected with a clear look-ahead error.
`slippage_ticks` is limited to 0–1 because Nautilus's fill model cannot move a fill further (LEARNINGS §4).

**Decisions.** Nautilus's built-in indicators are used where they exist, with options chosen to match textbook
definitions where Nautilus's defaults differ (RSI → Wilder ×100, ATR → Wilder, WMA → linear weights,
Stochastics %D → SMA, ROC → n+1 window, VWAP → bar-open session); ADX, OBV and highest/lowest are ours.
No warm-up padding: indicators warm up inside the requested range in both engines.

## Phase 4 — the fast engine (2026-10-12)

**Acceptance:** parity on all 10 catalogue strategies ✅ — same trades, same timestamps, net P&L within 0.5%
(`tests/test_parity.py`: 10 strategies × 2 fee profiles + 7 risk-feature variants, 2024-H1; `make parity`:
the full year 2024). `make bench` table in REPORT.md: fast engine ✅, Nautilus ⏳ (running, ~6 h).

**Built** (`strategy_lab/engines/fast/`): Numba ports of all 18 indicators, bit-identical to Nautilus's
(NumPy's pairwise summation ported for the SMA family, sequential sums where Nautilus uses them, the same EMA
seeding); a vectorised compiler that turns a spec's condition tree into boolean arrays with the same
availability rules as the streaming evaluator; one jitted loop over 1-minute bars that implements the
execution semantics of ARCHITECTURE.md (gap check at the open, stop before target, trailing update at bar
close, funding, cooldown, daily cap, end-of-data close). `engines/contracts.py` holds the engine-neutral
contract specs so that fast-engine processes never import Nautilus. `lab/metrics.py` (all metrics from the
engine-neutral result) and `lab/sweep.py` (grid sweeps on either engine, 1 process or a spawn-based pool).

**Parity, one year (2024, real data), both fee profiles — 20 runs:** trades identical in all 20 (count, entry
and exit times, side, exit reason); largest relative difference in net P&L 1.3e-10, fees 1.4e-10, funding 0.
The residue is float64 accumulation order (the fast engine sums in float64, Nautilus books fixed-point
`Money`); in USDC it is below 1e-7. Nautilus 223 s for the 20 runs, the fast engine 2.9 s (×78).

**Fast-engine speed** (REPORT.md): one year of 1-minute execution 0.10 s warm (0.29 s from a cold process
with the Numba on-disk cache); 1,600-run sweep 48.5 s on 1 core, 15.2 s on 4.

**Problems found and fixed.**
- One take-profit one tick apart in 108 trades → `Price.as_double()` is one ulp off the decimal for large
  raw values; canonicalise prices on the tick grid (LEARNINGS §13). Parity is now exact.
- Trailing stop tightened into a gapped market: Nautilus rejects the modify and keeps the old stop
  (LEARNINGS §14) → the fast engine mirrors it; the spec strategy reads the live trigger price.
- Fast-engine sweep workers each imported Nautilus (≈870 MB per process) through a shared helper module →
  engine-neutral `contracts.py`, helpers moved to `engines/inputs.py` / `engines/results.py`, lazy Nautilus
  imports: ≈480–550 MB per worker.
