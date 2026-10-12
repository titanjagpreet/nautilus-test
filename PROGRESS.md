# PROGRESS

Running log of what is done, measured numbers, problems and decisions. Updated at the end of every phase.

## Definition of done

- [x] Network check done; sources and fallbacks recorded.
- [x] BTC and XAU history downloaded, checksummed where possible, validated, resampled, documented in DATA.md.
- [x] The hand-written Nautilus strategy runs with fees, slippage and funding visible; speed and memory measured.
- [x] Spec schema, validator (look-ahead and higher-timeframe guards), plain-language renderer, 10 catalogue strategies.
- [x] SpecStrategy runs any valid spec in Nautilus.
- [x] The fast engine matches Nautilus on all 10 catalogue strategies within the stated tolerance, or every difference is documented.
- [x] AI generate, edit, explain and from_pine work through the provider layer (DeepSeek default, Kimi alternative, Claude Haiku optional) with validation and repair, escalation, caching and cost logging. *(Live on DeepSeek via the eval — generate, edit, from_pine, repair, caching, cost logging; explain, escalation and the Kimi/Claude paths are covered by SDK-level tests only: no keys.)*
- [x] The eval has run on every provider with a key; the comparison and recommendation are in REPORT.md; total API spend is under budget. *(One key — DeepSeek; eval $0.047 of $1, total $0.053 of $3.)*
- [x] The lab works: out-of-sample, walk-forward, heat-map, Monte Carlo, score with its parts, warnings.
- [x] UI pages work: Builder, Backtest, Lab, Compare, Costs.
- [x] All tests pass; ruff and mypy are clean; `make demo` works from a clean checkout.
- [x] LEARNINGS.md, ARCHITECTURE.md, DATA.md and REPORT.md are written with real measured numbers.
- [x] No secrets in git; no live-trading code; no fabricated data.

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

## Phase 4 — the fast engine (2026-10-12) ✅

**Acceptance:** parity on all 10 catalogue strategies ✅ — same trades, same timestamps, net P&L within 0.5%
(`tests/test_parity.py`: 10 strategies × 2 fee profiles + 7 risk-feature variants + 3 strategies covering the
remaining indicator types, 2024-H1; `make parity`: the full year 2024). `make bench` table in REPORT.md ✅ (both engines; the NautilusTrader part ran ~6 h).

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
with the Numba on-disk cache; 3.4 s for the very first run in a new checkout, which compiles); 1,600-run sweep
48.5 s on 1 core, 15.2 s on 4 — NautilusTrader: 10,327 s (×213) and 2,522 s (×166, 3.4 GB peak).

**Problems found and fixed.**
- One take-profit one tick apart in 108 trades → `Price.as_double()` is one ulp off the decimal for large
  raw values; canonicalise prices on the tick grid (LEARNINGS §13). Parity is now exact.
- Trailing stop tightened into a gapped market: Nautilus rejects the modify and keeps the old stop
  (LEARNINGS §14) → the fast engine mirrors it; the spec strategy reads the live trigger price.
- (Found in Phase 8) WMA and HMA crashed the fast engine whenever its compiled code came from Numba's on-disk
  cache (a recursive jitted function) — no catalogue strategy used them, so parity never ran them → iterative
  pairwise sum, a direct exact-equality test for every indicator type, and three parity strategies covering
  the eight indicator types the catalogue does not use (LEARNINGS §16).
- Fast-engine sweep workers each imported Nautilus (≈870 MB per process) through a shared helper module →
  engine-neutral `contracts.py`, helpers moved to `engines/inputs.py` / `engines/results.py`, lazy Nautilus
  imports: ≈480–550 MB per worker.

## Phase 5 — AI strategy builder (2026-10-12) ✅ (eval run on DeepSeek, the one provider with a key)

**Acceptance so far:** provider layer, generate / edit / explain / from_pine, validation + repair + escalation,
caching-friendly prompts, cost ledger and spend limits ✅ (`tests/test_ai_*.py`: 48 tests through the real
`openai` / `anthropic` SDKs with synthetic, clearly labelled responses on a mock HTTP transport). No API key
exists in this sandbox, so the eval ran on the user's machine (DeepSeek, below). `make eval` runs it on every
provider with a key; results go to REPORT.md, `evals/results/latest.json` and `evals/recorded/` (replayed by the
tests).

**Built** (`strategy_lab/ai/`): `config/llm.json` (models, prices checked 2026-10-12 with sources, budgets $3 /
$1, DeepSeek peak windows); `providers/` — DeepSeek and Kimi through `openai` (base URLs), Claude Haiku 5.5
through `anthropic` (claude-api skill read first); structured-output ladder per provider (Claude: JSON schema
→ prompted JSON; Kimi: JSON schema → JSON mode; DeepSeek: strict tools on `/beta` → JSON mode with "json" and an
example), falling back on HTTP 400 and remembering the working mode; `transport.py` — strict-mode-safe view of
the spec (LEARNINGS §15); `prompts.py` — one static ~5K-token system prompt (byte-identical for caching) built
from the indicator catalogue; `builder.py` — up to 2 repairs quoting the exact validator errors, then one
escalation (DeepSeek → v4-pro, Kimi → k3), then a clean failure; `ledger.py` — SQLite spend log from usage
fields with both limits checked *before* every call; `judge.py` + `evaluation.py` — 40 prompts + 5 adversarial
(`evals/ai_eval.json`), objective intent checks, blind batched LLM judge, model-level vs system-level safety.

**Network facts:** api.anthropic.com is reachable from this sandbox; api.deepseek.com and api.moonshot.ai are
refused by the egress proxy (403), so here only Claude can be evaluated; elsewhere all three run.

**Eval result (DeepSeek, run by the user on Windows, 2026-10-12, $0.047):** 45 cases; first-try valid 88%, valid
after repair 100% (9 repairs, 0 escalations); intent: objective checks 100%, judge 91% (39 judged; manual check
of 11 verdicts agrees on 9 — `evals/judge_check.md`); adversarial safety 100% model / 100% system (re-scored
from the recordings, see below); $0.00063 per request (~$0.63 per 1,000); latency p50 3.9 s, p95 8.8 s. Kimi and
Claude were not evaluated (no keys). Details and the default-writer recommendation: REPORT.md §5.

**Problems the real run exposed, all fixed** (none was the model's fault):
- Safety scoring counted a first reply *without* a spec as unsafe (a03, a04: 60% model-level). A reply that
  contains nothing unsafe is incomplete, not unsafe → `adversarial_scores` fixed; re-scored from the recorded
  replies with `--rescore` (no API calls) → 100%.
- e02 asked to "make it long only" a strategy that already was; the model said so, but the builder rejected
  unchanged specs and forced a meaningless edit → the eval item now uses a two-sided base, and an unchanged edit
  is accepted with an `UNCHANGED` warning (the prompt says to return the spec unchanged when nothing is needed).
- The judge saw only the vague prompt for g29/g30, not the user's clarifying answers → now included. One case
  (e02) got no verdict; label parsing is now tolerant ("Candidate A") and judge replies are recorded.
- Windows: text files were read with the locale encoding → UTF-8 everywhere; recordings now also store the
  structured-output mode, tokens and cost of every attempt and the item definition they answer.
- Every writer call ran in JSON mode: DeepSeek's strict tools were rejected with a 400 whose message was thrown
  away. Rejections are now logged with the reason; one call named it ("field `anyOf`: missing field `type`"), and
  strict tools now get a schema with every `anyOf` branch typed (`transport.typed_union_branches`, proven to
  accept the same documents); DeepSeek accepts it.
- The first strict-tools reply (and g21's in JSON mode) was a complete object plus one stray `}`; the parser's
  "first `{` to last `}`" fallback pulled it in and failed. It now reads exactly one JSON object
  (`split_json_object`), logs what follows it, rejects a second object, and quotes the text around any parse
  error. Confirmed on the user's machine: the next strict-tools reply was accepted first time, with the ledger
  note `ignored after the JSON object: }` (2 of the first 3 strict replies had text after the object). **Open:** re-run the DeepSeek eval to measure first-try validity under strict tools (projected ~$0.14
  of the $0.95 eval budget left).

## Phase 6 — the lab (2026-10-12) ✅

**Acceptance:** out-of-sample, walk-forward, heat-map, Monte Carlo, score with its parts, warnings ✅
(`tests/test_lab.py`; real-data runs below).

**Built** (`strategy_lab/lab/`): `evaluator.py` (window runs with indicator warm-up on earlier data — new
`trade_from` in the fast engine, proven equal to a full run's trades by a real-data test), `optimize.py` (grid,
Optuna TPE ≤ 4 parameters), `validation.py` (70/30 OOS, 6m/2m walk-forward with chained OOS equity, heat-map
neighbour stability, 1,000-sample trade bootstrap), `robustness.py` (score from six weighted parts, ten warning
types, JSON report), CLI `python -m strategy_lab.lab`.

**Real runs** (BTC, 2023-07-01 → 2026-07-01, grid 9×9, fast engine, ~1,400 backtests in 37–51 s each):

| strategy | score | OOS Sharpe (in → out) | WF windows profitable | MC P(loss) | return vs buy & hold |
|---|---|---|---|---|---|
| Donchian breakout | 65 | 1.08 → 0.49 | 60% of 15 | 10% | +18.3% vs +92.4% |
| Keltner pullback | 43 | 1.22 → −0.02 | 40% of 15 | 39% | +2.8% vs +92.4% |
| EMA crossover | 30 | 0.95 → −0.50 | 47% of 15 | 89% | −9.0% vs +92.4% |
| Funding-rate fade (BTC, 2023-06 → 2026-06) | 40 | 1.68 → 0.00 | 20% of 15 | 7% | +5.1% vs +170.8% (22 trades) |
| Gold session breakout (XAU, 2023-05 → 2026-05) | 18 | 0.36 → −2.32 | 33% of 15 | 77% | −1.1% vs +132.9% |

The lab does what it is for: tuned in-sample Sharpe ratios near 1 collapse out of sample for two of three
templates, and none beats holding BTC over the period.

## Phase 7 — API and UI (2026-10-12) ✅

**Acceptance:** all five pages work against real data ✅ (`tests/test_api.py`, 12 tests incl. real background
jobs on both engines; screenshots in `docs/screenshots/`).

**Built:** FastAPI JSON API (`strategy_lab/api/app.py`) + Jinja2/HTMX pages (`pages.py`), SQLite store
(`store.py`: specs, jobs, backtests and lab reports with spec, data range, source and engine version), background
jobs in spawned worker processes (`jobs.py`, `worker.py`), dark theme, Lightweight Charts 4.2.3 + Plotly 2.35.2
pinned on jsDelivr with an offline copy fetched from the npm registry and SHA-512-verified
(`scripts/vendor_assets.py`; jsDelivr is blocked here, the npm registry is not). Through the API the Donchian
breakout over 2024 gives identical results on both engines (58 trades, +1,518.98 USDC; 0.33 s vs 17.2 s).

## Phase 8 — quality, demo, report (2026-10-12)

**Checks:** `make lint` clean (ruff + mypy, strict on spec, engines, lab and AI); **236 tests pass**, including
the replay of the recorded DeepSeek replies. From a **clean clone** (before the eval):
`make setup` → `make lint` → `make demo` (44 s) → `make test` (225 passed, the replay skipped) — with `STRATEGY_LAB_DATA_DIR`
pointing at the already downloaded history instead of re-running `make data`, which was verified in Phase 1.

**Found by the quality pass:** a direct exact-equality test of every indicator exposed that WMA/HMA crashed the
fast engine when loaded from Numba's cache (fixed; Phase 4 problems, LEARNINGS §16) and mypy caught two
keyword collisions in the HTML routes before they shipped.

**Safety review:** no `.env`, database or key in git (the only key-like string is the invented one in
adversarial eval prompt a01); no order placement, exchange account or signing code anywhere — NautilusTrader's
orders exist only inside its simulated venue; the Lighter data client only issues GET requests to public
endpoints; synthetic data only in tests, labelled.

**Written:** README (setup in 6 steps, every make command, a screenshot of each page), REPORT (verdict, data,
NautilusTrader measurements, parity and speed tables, lab results, AI design and data-location note),
ARCHITECTURE (AI, lab, API/jobs sections), LEARNINGS §15–17, `make demo`.

**Benchmark complete:** NautilusTrader's 1,600-run sweep took 10,327 s on 1 core and 2,522 s on 4 (3.4 GB
peak), vs 48.5 s / 15.2 s for the fast engine; the REPORT verdict quotes them. The fast engine's "cold" row
was relabelled: it loads compiled code from Numba's cache (0.29 s); a first run that compiles takes 3.4 s.
