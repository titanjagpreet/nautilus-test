# Mirrorlane handoff: the Strategy Lab prototype

What was built, how, what broke and why, and how to build it into Mirrorlane. Written for **Claude (or an
engineer) implementing these features in the Mirrorlane codebase**. Everything here was measured or verified in
this repository; nothing is estimated unless it says so.

* Repository: `titanjagpreet/nautilus-test`, branch `claude/epic-brahmagupta-oab55w`.
* Built 2026-10-12 → 2026-10-13. Python 3.13, `uv`, NautilusTrader 1.231.0, Numba 0.68.0.
* State: phases 0–8 done, 259 tests pass, `ruff` and `mypy` (strict on spec, engines, lab, AI) clean, verified
  end to end on Linux (build sandbox) and on Windows (the user's PC, open network).

## 0. How to use this document

**Source-of-truth order** when something disagrees: tests → code → `ARCHITECTURE.md` / `LEARNINGS.md` /
`DATA.md` / `REPORT.md` → this file. This file summarises those documents and adds the implementation plan; it
links to them rather than repeating every detail.

**Reading order for an implementer:**
1. §1 (summary) and §2 (ground rules).
2. §6, the execution-semantics contract. Every engine must implement it exactly; it is the most important page.
3. §14, the implementation plan for Mirrorlane, then whichever component you are porting (§4–§10).
4. §12 (every bug found, with root cause) and §15 (pitfall checklist) before you write code. Most of those bugs
   will recur in a port unless you design them out.

**Reuse vs re-implement:** the spec format, validator, renderer, transport schema, fast engine, lab and
data-source code are portable Python with no web or framework assumptions. Reuse them (or port them line by
line) and keep their tests. Replace the prototype's infrastructure (SQLite, local worker processes,
server-rendered HTMX pages) with Mirrorlane's.

---

## 1. Summary

**What it is.** A backtest-only strategy lab for the Lighter perpetuals exchange:
* **Builder:** plain English (or Pine Script) is turned into a validated, declarative **strategy spec** by an LLM.
* **Backtest:** the spec runs on real BTC and gold history in **two engines**: NautilusTrader (event-driven
  reference) and a purpose-built **Numba engine** that reproduces it trade for trade.
* **Lab:** a **robustness lab** runs out-of-sample, walk-forward, a parameter heat-map and Monte Carlo, and gives a
  0–100 score with named parts and warnings.
* **UI and API:** a web UI (Builder, Backtest, Lab, Compare, Costs) and a JSON API.

**Verdict (REPORT.md):** build Mirrorlane's backtesting on a purpose-built vectorised/JIT engine, and keep
NautilusTrader as the **reference** that a parity suite runs against on every change. Do not put
NautilusTrader in the interactive path.

**Key measured numbers**

| what | result |
|---|---|
| parity, 10 catalogue strategies × 2 fee profiles, 2024 | identical trades in 20/20 runs; P&L relative difference ≤ 1.3e-10 |
| parity on the user's Windows PC (different data copy) | 200 vs 200 trades, −445.83 vs −445.83 USDC |
| 1 backtest, 1 year, 1h signals on 1m execution | Numba 0.03–0.10 s · NautilusTrader 5.9 s (11.6 s first run in a process) |
| 1,600-run sweep, 1 core / 4 cores | Numba 48.5 s / 15.2 s · NautilusTrader 10,327 s / 2,522 s (×213 / ×166) |
| memory | NautilusTrader 370 MB empty, 0.7–1.3 GB per run · Numba worker ≈ 0.5 GB |
| robustness report (≈ 870–3,900 backtests) | 24–160 s on the fast engine; ≥ 2 h it would take in NautilusTrader |
| AI builder, DeepSeek V4.1-Flash, 45 eval cases | 88% valid first try (JSON mode), **100% after repair**, 0 escalations, 100% safe, $0.63 per 1,000 requests, p50 3.9 s |
| Lighter BTC-PERP vs Binance USD-M futures, 895,157 minutes | close correlation 0.999998, median \|diff\| 2.0 bps, p99 13.5 bps |
| best strategy found (§13) | 80/100 robustness; out-of-sample Jan 2024 → Jul 2026: +114% vs buy-and-hold +40%, max DD −22% |
| total LLM spend for the project | < $0.10 of a $3 budget |

---

## 2. Ground rules that shaped every decision (keep them in Mirrorlane)

1. **Backtest only.** No live trading, no exchange API keys, no order placement, no signing code. The Lighter
   client issues only `GET`s to public endpoints. NautilusTrader orders exist only inside its simulated venue.
2. **Secrets:** only LLM keys (`DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY`, `ANTHROPIC_API_KEY`), read from a
   git-ignored `.env` (environment first, then `.env`), never printed or logged. A provider without a key is
   skipped, never an error.
3. **Spend limits:** total LLM spend under $3, eval under $1. Cost is computed from the APIs' own usage fields, and
   a **worst-case estimate is checked before every call**. A call that could cross a limit is refused before it
   is sent.
4. **Never fabricate data or results.** Synthetic data only in unit tests, generated in code and labelled
   `SYNTHETIC`. A blocked source is recorded as blocked and the next source is tried; holes are never filled.
5. **Verify, never guess.** NautilusTrader behaviour was read from the installed source (`.pyx` files ship in the
   wheel) and confirmed by probe tests. Provider behaviour came from docs, and when the docs were silent, from a
   logged real API response.
6. **The model never writes code.** A spec is data, interpreted by the engines. The **validator, not the model**,
   guarantees a stop-loss, leverage ≤ 10x and no look-ahead.

---

## 3. Architecture

```
            plain English / Pine Script                       data sources (Binance, Lighter, Dukascopy,
                     │                                         GitHub fallbacks)  ── make data ──┐
                     ▼                                                                         ▼
   ┌───────── strategy_lab/ai ─────────┐                                         strategy_lab/data
   │ provider layer (DeepSeek, Kimi,    │                                         canonical 1m Parquet
   │ Claude) → JSON → Pydantic →        │                                         + funding, resampled
   │ validator → repair → escalate      │                                         bars, DuckDB views
   └──────────────┬─────────────────────┘                                                 │
                  ▼                                                                       │
          strategy_lab/spec  ◄──── catalogue/*.json (10 templates)                        │
   schema · indicator catalogue · validator · renderer · evaluator · decisions            │
                  │                                                                       │
        ┌─────────┴──────────────────────────────┐                                        │
        ▼                                        ▼                                        │
 engines/nautilus (reference)            engines/fast (Numba)      ◄── engines/inputs ◄───┘
        └──────────── BacktestResult ────────────┘   (engines/results.py)
                             │
                      strategy_lab/lab   metrics · OOS · walk-forward · heat-map · Monte Carlo · score
                             │
                      strategy_lab/api (FastAPI, SQLite, job workers) ── strategy_lab/ui (Jinja2 + HTMX)
```

**File map** (lines of code in brackets):

| area | files | what they do |
|---|---|---|
| data | `data/pipeline.py` (402), `sources/{binance,lighter,github_datasets,dukascopy,http}.py`, `validate.py` (226), `storage.py` (168), `resample.py`, `schema.py` | download with fallbacks → normalise → validate → Parquet → resample → cross-check → `data/quality_report.md` |
| spec | `spec/schema.py` (252), `indicators.py`, `validator.py` (567), `render.py`, `params.py`, `evaluator.py`, `streaming.py`, `decisions.py` (195), `diff.py`, `catalogue/*.json` | the strategy format and everything that understands it |
| shared engine I/O | `engines/contracts.py`, `inputs.py` (155), `results.py` (153) | contract specs (no Nautilus import), dataset choice and tick-rounded bars + funding, the common `BacktestResult` |
| fast engine | `engines/fast/{indicators.py (429), compile.py (253), simulate.py (330), runner.py (278)}` | Numba indicator ports, condition compiler, jitted 1-minute loop, prepare/run split |
| reference engine | `engines/nautilus/{spec_strategy.py, exec_feed.py, spec_runner.py, funding.py, fill_model.py, patches.py, handwritten.py, …}` | NautilusTrader made to follow the contract |
| lab | `lab/{metrics,sweep,evaluator,optimize,validation,robustness}.py` | windows with warm-up, grid/Optuna, OOS, walk-forward, heat-map, Monte Carlo, score |
| AI | `ai/{config,ledger,transport,prompts,builder,judge,evaluation}.py`, `ai/providers/{base,openai_compat,anthropic_provider}.py` | provider layer, transport schema, prompt, repair loop, spend ledger, eval |
| web | `api/{app,pages,actions,services,store,jobs,worker}.py`, `ui/templates/*`, `ui/static/{app.js,app.css}` | JSON API + pages, SQLite store, background jobs, charts |
| config | `config/llm.json`, `config/fee_profiles.json` | models, prices (with the date checked and sources), budgets; Lighter fee tiers |
| quality | `tests/` (16 files), `benchmarks/{bench,parity_report,nautilus_phase2}.py`, `evals/` | tests, benchmarks, AI eval set, recorded replies |

**Pinned stack:** pandas 3.0.6, numpy 2.5.4, numba 0.68.0, nautilus-trader 1.231.0, pyarrow 26, duckdb 1.5.6,
pydantic 2.14, fastapi 0.143, jinja2, uvicorn, optuna 5.0, openai 3.29, anthropic 1.13 (both on `httpx2`),
python-dotenv. Dev: pytest + xdist, hypothesis, jsonschema, ruff 0.17, mypy 2.4. Front-end: Lightweight Charts
4.2.3, Plotly 2.35.2, HTMX (pinned on jsDelivr, plus a SHA-512-verified local copy).

---

## 4. Data layer

### 4.1 Sources, in fallback order (`data/pipeline.py:run`)

| dataset | tried in order | notes |
|---|---|---|
| BTC 1m, long history | Binance USD-M futures archive → Binance spot archive → GitHub republication of Binance spot | `data.binance.vision` monthly zips + `.CHECKSUM` (SHA-256), all verified; futures from **2020-01** (2019-09…12 are 404), spot from 2017-08 |
| BTC 1m, second exchange | Bitstamp (GitHub) | cross-check only; 1.31 M flat zero-volume "filler" minutes dropped |
| BTC funding (8 h) | Binance futures `fundingRate` archive → a GitHub API export verified against 2 other exports | |
| BTC-PERP, XAU-PERP 1m + hourly funding | **Lighter REST** `https://mainnet.zklighter.elliot.ai` | `GET /api/v1/orderBookDetails?filter=perp` (market specs; BTC market_id 1, XAU 92); `GET /api/v1/candles?market_id&resolution=1m&start_timestamp&end_timestamp&count_back=0` and `/api/v1/fundings?…resolution=1h…`, walked backwards in fixed windows from the end to the market's `created_at`, each page cached on disk |
| XAU 1m, long history | Dukascopy (via `npx dukascopy-node@1.50.0`, bid + ask → mid) → HistData XAUUSD bid (GitHub) | Dukascopy answered **HTTP 202 to every request** on the open network (cause unknown); HistData was used everywhere |

What was obtained on the open network (DATA.md §6): Binance futures 3.55 M bars (2020-01 → 2026-09, 100%
complete, 0 gaps); Binance spot 4.79 M; **Lighter BTC-PERP 895,157 bars from 2025-01-17** (100%, 0 gaps) with
14,901 funding rows; **Lighter XAU-PERP 497,086 bars from 2025-10-20** with 8,277 funding rows; HistData gold
1.87 M bars (2021-01-03 → 2026-05-29, bid only, no volume).

### 4.2 Canonical form and storage

* 1-minute bars, columns `ts, open, high, low, close, volume, source, symbol`; `ts` = **bar open time, UTC,
  nanoseconds**; prices float64. Funding: `ts, rate (per period), period_hours, source, symbol`.
* Parquet partitioned as `data/bars/source=<s>/symbol=<sym>/year=<y>/part-0.parquet` (same for `funding/` and
  `resampled/tf=<tf>/`). DuckDB views (`bars_1m`, `funding`, `bars_<tf>`) for ad-hoc queries.
* **Resampling:** UTC-anchored bins, open-time labels, `n_minutes` = number of 1m bars in the bin; a bin with no
  1-minute bars produces **no bar**. Property-tested (`tests/test_properties.py`).
* **Prices are rounded to the instrument tick once**, before either engine sees them (`inputs.round_to_tick`,
  half away from zero, like Nautilus's fixed-point conversion).
* **Validation report** per dataset: completeness excluding market closures; gaps > 5 min classified as weekend /
  daily break / US-holiday closure for gold; duplicates removed; OHLC sanity; 1-minute moves > 10σ of the
  trailing day **flagged and kept** (they are real: the 2018 Tether de-peg, the 2025-10-10 crash); timestamp units
  per file.

### 4.3 Which dataset a backtest uses (`engines/inputs.py`). Get this right.

* Per market, a **preference order**: BTC-PERP → `lighter`, `binance_futures`, `binance_spot`, `binance_spot_gh`,
  `bitstamp`; XAU-PERP → `lighter`, `dukascopy`, `histdata`. Funding: BTC → `lighter`, `binance_futures`,
  `binance_futures_funding_gh`; XAU → `lighter`.
* **Bars:** use the most preferred dataset that **covers the whole window** `[start, end)`, allowing **4 days of
  slack** for weekends and holidays. If none covers it, stop with an error listing every dataset's date range.
  Lighter's short history is used for recent windows and never silently truncates a longer one.
* **Funding:** the most preferred covering series; else the one overlapping the window most, charged where it
  exists and **labelled `(partial: …)`**; else none.
* **Warm-up never switches datasets:** `load_market(..., history_from=start - warmup)` chooses datasets by
  `[start, end)` and loads earlier rows of the **same** datasets as far as they go.
* **Default window** (`api/services.default_window`): the last three whole years of the most preferred source that
  has them, ending where a funding series covering the window ends. If no funding series reaches back three
  years (gold, where only Lighter's exists), three years without full funding. If nothing has three years, the
  longest window.

### 4.4 Operational robustness (all from real failures, §12)

* Downloads write `<file>.part` and rename on completion; Binance zips are re-verified against their SHA-256 on
  every run, so an interrupted download resumes.
* Dataset writes go to `<root>/.staging/…` and are **swapped in whole**. Readers only see `source=*` folders.
* Lighter pages are written atomically, and an unreadable cached page is fetched again. Dukascopy's CLI writes
  `<name>.part.csv`, renamed on success. On Windows `npx` is `npx.cmd`, so it is launched by its full path.
* **Every file read and write is explicit UTF-8.** Windows defaults to the locale encoding.
* **Every DuckDB connection runs `SET TimeZone='UTC'`.** By default DuckDB returns timestamps in the machine's
  zone: a UTC+6 PC showed data ending 2026-10-01 for bars ending 2026-09-30 23:59 UTC.
* **Normalise timestamps to nanoseconds at the storage boundary.** pandas 3 returns `datetime64[us]` from
  Parquet; Nautilus's wrangler then read µs as ns and put every bar in 1970.

---

## 5. The strategy spec (v0.1)

Pydantic v2 models in `spec/schema.py`; JSON Schema exported by `python -m strategy_lab.spec`. A complete example
is `docs/strategies/trend_filtered_breakout.json`; ten more are in `strategy_lab/spec/catalogue/`.

```
StrategySpec
├─ spec_version "0.1", meta {name, description, author: ai|user|template, tags}
├─ market {symbol: BTC-PERP|XAU-PERP, timeframe: 5m|15m|1h|4h|1d, direction: long|short|both}
├─ indicators[] {id, type, params{…}, source?: open|high|low|close|volume|hl2|hlc3|ohlc4, timeframe?: higher TF}
├─ rules {entry_long?, exit_long?, entry_short?, exit_short?}   each a Condition:
│     Compare  {op: > < >= <=, left, right}
│     Cross    {op: crosses_above|crosses_below, left, right}
│     Between  {op: between, …}
│     AllOf {op: all, args[]} · AnyOf {op: any, args[]} · Not {op: not, arg}
│   Operand: {input: open|high|low|close|volume|hl2|hlc3|ohlc4|funding_rate|hour_utc, bars_ago?}
│          | {indicator: id, output?, bars_ago?} | {value: number}
├─ risk {position_sizing: percent_equity{value} | fixed_usd{value}, leverage ≤ 10,
│        stop_loss (required): percent{value} | atr{multiple, atr_period} | structure{lookback, …},
│        take_profit?: percent | atr | risk_reward{multiple},
│        trailing_stop?: percent | atr, time_exit_bars?, cooldown_bars, max_trades_per_day?}
├─ costs {fee_profile: lighter_standard (0/0 bps) | lighter_premium (0.4/2.8 bps), slippage_ticks: 0|1, funding: bool}
└─ execution {fill_on: next_bar_open, htf_bars: completed}   ← only these values are valid
```

* **Indicator catalogue (18):** sma, ema, wma, hma, rsi, macd (line/signal/hist), bbands
  (middle/upper/lower/width), atr, stoch (k/d), adx (adx/plus_di/minus_di), donchian, keltner, vwap, roc, cci, obv,
  highest, lowest. Each has bounds, outputs, warm-up length and a Nautilus mapping (`spec/indicators.py`).
* **`funding_rate` input** = latest settled rate at the bar close, scaled to 8 hours. Binance funds every 8 h,
  Lighter hourly.
* **The `execution` section exists so that unsafe settings parse and are then rejected.** Pine Script's
  `process_orders_on_close` and `lookahead_on` translate to `same_bar_close` / `forming`, which the validator
  rejects as look-ahead.
* **`slippage_ticks` is 0 or 1**, because Nautilus's fill model cannot move a fill further (LEARNINGS §4).

**Validator** (`spec/validator.py`): returns **every** issue at once with JSON paths, so the AI repair loop can
fix them all in one turn.
* Errors: `SCHEMA`, `MISSING_ENTRY`, `MISSING_STOP`, `LEVERAGE`, `SIZING` (notional ≤ leverage cap),
  `OUT_OF_RANGE`, `PARAM_OUT_OF_RANGE`, `PARAM_NOT_INTEGER`, `PARAM_CONFLICT`, `UNKNOWN_PARAM`,
  `UNKNOWN_OUTPUT`, `UNDEFINED_INDICATOR`, `DUPLICATE_ID`, `SOURCE_NOT_ALLOWED`, `BARS_AGO_TOO_LARGE`
  (> 500), `SLIPPAGE`, `UNKNOWN_FEE_PROFILE`, `UNSUPPORTED_EXECUTION`.
* **Look-ahead:** `LOOKAHEAD_FUTURE_BAR` (negative `bars_ago`), `LOOKAHEAD_SAME_BAR`, `LOOKAHEAD_FORMING_HTF`.
* **Higher timeframe:** `HTF_BELOW_BASE`, `HTF_NOT_MULTIPLE`, `HTF_CROSS`.
* **Data context:** `NO_FUNDING_DATA` and `NO_VOLUME_DATA` (HistData gold has no volume).
* **Logic:** `CONTRADICTORY_RULE`, e.g. `close < donchian.lower` on the same bar can never be true, because
  Donchian includes the current bar.
* Warnings: `UNUSED_RULE`, `LONG_WARMUP`, `VOLUME_MAYBE_MISSING`, and `OVERFITTING_RISK` (more than 6 tunable
  parameters).

**Renderer** (`spec/render.py`): a deterministic plain-language description of the spec. The UI shows it next
to every AI result, because **models misdescribe their own output** (§9.6).

**Parameters** (`spec/params.py`): `tunable_parameters(spec)` lists every numeric knob with bounds;
`with_params(spec, {"dc20.period": 22})` returns a modified copy. The lab and the heat-map use this.

---

## 6. The execution-semantics contract (implement exactly; parity depends on it)

From `ARCHITECTURE.md`; both engines implement it and `tests/test_parity.py` pins it.

**Data.** Strategy (base) bars and higher-timeframe bars are built from the same 1-minute bars (UTC bins,
open-time labels). A base bar closes at `bin start + timeframe`.

**Signals** are evaluated when a base bar closes, using values up to and including that bar.
* **Higher timeframes:** indicators only use **completed** HTF bars. An HTF bar ending at `T` is usable from the
  base bar that closes at `T`.
* **Availability:** a rule fires only when every operand is available (indicator warmed up; for crosses, also one
  bar earlier).

**Decisions at a base-bar close**, in this order (`spec/decisions.py`):
1. **In a position:** exit if the exit rule fires or `time_exit_bars` have elapsed. If the opposite entry fires
   and an entry is allowed (cooldown 0, daily cap not reached), exit and reverse.
2. **Flat:** enter if **exactly one** allowed entry rule fires, `bars since exit ≥ cooldown_bars`, and fewer than
   `max_trades_per_day` entries were taken on the UTC date of this bar's close.
3. **Still in a position:** move the trailing stop, computed from this close and never loosened.
4. **Size:** notional = `percent_equity` × cash balance (or `fixed_usd`), capped at `leverage × balance`; quantity
   = notional / close, rounded **down** to the lot size; below the minimum quantity, no trade.

**Fills.**
* **Market orders** fill at the **open of the next 1-minute bar** after the signal, ± `slippage_ticks` × tick
  against you, at the taker fee.
* **After an entry fills at price P,** the stop-loss (stop-market) and take-profit (limit) are priced from P and
  the signal bar's ATR or structure values. A stop already through the market fills immediately at market.
* **Each following 1-minute bar is checked in this order:**
  1. **Open (gap):** a stop beyond the open fills at the open ± slippage; a take-profit beyond the open fills at
     its limit.
  2. **Adverse extreme:** the stop fills at its trigger ± slippage.
  3. **Favourable extreme:** the take-profit fills at its limit, at the maker fee.

  **If both could fill in the same minute, the stop wins.**
* **Trailing stops:** a change decided at a bar close takes effect after the next bar's open has been checked
  against the old stop. Tightening a stop into a gapped market is **rejected**, and the old stop stays; this
  copies NautilusTrader (§7.1).
* **End of data:** open positions are closed at the last close ± slippage (exit reason `end`).

**Funding** is charged at each funding time `F` on the position held after every fill stamped ≤ `F`:
payment = signed size × last price ≤ `F` × rate (a positive rate means longs pay).

**Not modelled:** market impact, partial fills, liquidation, latency beyond "next bar open", mark vs last price.

---

## 7. The engines

### 7.1 NautilusTrader 1.231 as the reference (LEARNINGS §1–§14)

Native behaviour that does **not** match the contract, and the fix for each:

| native behaviour | fix |
|---|---|
| A market order from `on_bar` fills at **that bar's close** | `LatencyModel(base_latency_nanos=1)`, plus a synthetic **"open" bar** at `T+1ns` (O=H=L=C=the next 1m open): orders then fill at the next open |
| Bar execution is O→H→L→C (or "closest first"); **never stop-first** | a **direction-aware intrabar path** that visits the adverse extreme first, fed through `engine.add_data_iterator(name, generator)`; the generator is asked for the next chunk as the last item is handed out, so each chunk ends with the next minute's direction-independent open bar |
| `FillModel` slips **limit** fills too | subclass `FillModel`: record the order type in `get_orderbook_for_fill_simulation`, slip only market and stop fills; limited to 0 or 1 tick |
| `reject_stop_orders=True` leaves a position **unprotected** when its stop is already through the market | `reject_stop_orders=False` (a new stop fills immediately) |
| Modifying a stop into the market is always rejected | mirrored in the fast engine; the strategy reads the live `order.trigger_price` |
| **No funding at all** (`FundingRateUpdate` is data only) | a `SimulationModule` calling `exchange.adjust_account(...)` at each funding time, with its own ledger |
| `PortfolioAnalyzer` is **O(n²)** in trades (`pd.concat` per closed position) | `engines/nautilus/patches.py` buffers records (575 s → 127 s for a 1-year 1m strategy); a test proves statistics are identical |
| `Price.as_double()` is one ulp off the decimal (`65031.299999999996`) | canonicalise every price with `round_price(…, decimals)`; that made P&L parity exact |
| Bars must be stamped at their **close**; data is open-stamped | shift by one bar width; with mixed timeframes give strategy bars `ts_init_delta=1` |
| Indicators differ from textbook | RSI is 0–1 with EMA smoothing → Wilder ×100; ATR is simple → Wilder; WMA is unweighted → pass linear weights; ROC uses n−1 → use n+1; Bollinger is on typical price → feed `(v,v,v)`; Stochastic %D is a ratio → SMA; VWAP resets on close-time day → feed open time; ADX and OBV implemented ourselves |
| Bar volume is liquidity (¼ per tick) | the zero-volume gold data would starve fills, so execution bars carry a large volume |

Cost: about 1 GB per run, ≈ 4k bars/s when Python `on_bar` trades often, 370 MB for an empty engine.

### 7.2 The Numba fast engine (`engines/fast/`)

* **`prepare(spec, market)`:** resample, compute every indicator as arrays (bit-identical ports), and compile the
  condition tree into boolean arrays with the same availability rules as the streaming evaluator
  (`compile.py`). Prepared data is cached and reused across parameter combinations.
* **`run_prepared(prepared, spec, balance, start, end, trade_from=…)`:** one `@njit(cache=True)` loop over
  1-minute bars implementing §6, including the gap check, stop before target, trailing at the close, funding,
  cooldown, daily cap and end-of-data close. `trade_from` masks entries before the window, so the lab warms
  indicators up on earlier data without changing any trade.
* **Bit-identical indicators.** "Same formula" is not enough: a moving-average cross decided by 1e-12 flips a
  trade. So the engine ports **NumPy's pairwise summation** (SMA family), uses sequential sums where Nautilus
  does, and copies Nautilus's **EMA seeding** (first value, not an SMA).
* **Recursion and the on-disk cache.** Never put a **self-recursive** `@njit` function in the on-disk cache: it
  works when freshly compiled and **segfaults when loaded from the cache**. `_pairwise_sum` is iterative with an
  explicit stack, verified equal to `np.add.reduce` for sizes 0 … 1,000,003.
* **Keep NautilusTrader out of fast-engine processes.** Contract specs live in `engines/contracts.py`, and
  Nautilus is imported lazily. Otherwise each worker costs about 870 MB instead of about 500 MB.
* **First run on a new machine** compiles, which takes about 3.5 s; the result is cached afterwards.

### 7.3 Parity method (`tests/test_parity.py`, `make parity`)

* **What is compared:** for each strategy × fee profile, the trade count, entry and exit times, side, and exit
  reason must be identical, and P&L, fees and funding must agree within 0.5% (observed ≤ 1.3e-10).
* **Coverage:**
  * 10 catalogue strategies;
  * 7 risk-feature variants: cooldown + daily cap; structure stop + percent trail + fixed-USD size; short-only +
    time exit + percent target; gold ATR trail; higher-timeframe long-only + daily cap + reward-to-risk target;
    tight trail with rejected modifies at 5x; zero slippage + cooldown;
  * 3 extra strategies covering the 8 indicator types the catalogue doesn't use.
* **Exact equality per indicator:** every indicator type is tested equal to Nautilus's runtime on synthetic and
  on real BTC data.
* **Ledger check:** the trade and funding ledger reproduces Nautilus's own final account balance to < 1e-6 USDC.

---

## 8. The robustness lab (`lab/`)

`run_lab(spec, start, end, parameters=None, objective="sharpe", grid_points=9, optuna_trials=0)` →
baseline → heat-map (grid on two tunables; by default the first two) → **70/30 out-of-sample** (tune on 70%,
test on 30%) → **walk-forward 6 months in / 2 months out**, with chained out-of-sample equity → optional Optuna
(TPE, ≤ 4 parameters) → **Monte Carlo** (1,000 trade bootstraps) → score and warnings.
* **Warm-up:** every window warms its indicators up on **earlier** data (`Window` + `warmup_span` with a factor-3
  margin for recursive indicators). Warm-up inside the window would eat weeks of a 2-month walk-forward window.
* **Minimum trades:** with fewer than 10 trades in a window, its objective is not trusted (`MIN_TRADES`).

| score part | weight | how |
|---|---|---|
| out-of-sample retention | 25 | out-of-sample Sharpe / in-sample Sharpe, clipped 0–1 |
| walk-forward consistency | 25 | ½ share of profitable out-of-sample windows + ½ efficiency |
| parameter stability | 20 | the best heat-map cell's neighbours relative to it |
| Monte Carlo | 15 | 1 − P(loss) over resampled trades |
| sample size | 10 | (trades − 20) / 80, clipped |
| simplicity | 5 | 1 if ≤ 4 tunables, 0.5 if ≤ 6, else 0 |

Warnings: `TOO_MANY_PARAMETERS`, `FEW_TRADES`, `OUT_OF_SAMPLE_DECAY`, `OUT_OF_SAMPLE_LOSS`, `ISOLATED_OPTIMUM`,
`OPTIMUM_ON_EDGE`, `WALK_FORWARD_INCONSISTENT`, `UNSTABLE_PARAMETERS`, `MONTE_CARLO_LOSS`, `BELOW_BUY_AND_HOLD`.

Real results (REPORT §4): Donchian 65, Keltner 43, EMA crossover 30, funding fade 40, gold session breakout 18.
In-sample Sharpe ratios near 1 collapse out of sample, and that is what the lab exists to show. The
trend-filtered breakout (§13) scored 80.

---

## 9. The AI strategy builder (`ai/`)

### 9.1 Pipeline

```
idea / spec + change / Pine Script ──► user message (task; user data fenced in <<< >>>)
static system prompt (~5K tokens, generated from the catalogue, byte-identical for every request)
+ ONE reply schema (transport form inside an envelope) ──► provider.complete_json  (budget checked first)
──► split_json_object ──► Envelope ──► transport→canonical ──► Pydantic ──► validator (with DATA_CONTEXT)
     errors? ──► repair turn quoting EVERY error (×2, same conversation) ──► 1 escalation (stronger model,
     fresh conversation) ──► clean failure listing the errors
──► validated StrategySpec, or questions / explanation / refusal
```

* **Tasks:** `generate` (may ask clarifying questions when the idea is vague), `edit` (returns a diff computed
  from the specs; a no-op edit is accepted with an `UNCHANGED` warning), `explain`, `from_pine`.
* **Envelope fields** (every task, so the cached prefix is identical): `questions, spec, changes, explanation,
  unsupported, assumptions, refusal`.
* **Data context:** `DATA_CONTEXT` tells the validator what the data can support. Gold has no volume and no
  funding history, so specs needing them are rejected with a clear error the model can fix.

### 9.2 Transport schema (`ai/transport.py`). Why the model does not write the canonical schema.

| canonical schema feature | problem for strict structured output | transport form |
|---|---|---|
| recursive condition trees | Claude's strict mode rejects recursion | unrolled to `MAX_DEPTH = 3` levels of all/any/not |
| `params` as an open map | strict modes need `additionalProperties: false` | `[{"name","value"}]` pairs |
| optional fields | strict modes need every property `required` | required-but-nullable |
| `oneOf` + discriminator, bounds, patterns | unsupported | `anyOf`, no bounds; bounds and semantics are enforced by Pydantic + the validator |
| `$defs` | DeepSeek uses `$def` | per-provider `defs_key` |
| an `anyOf` branch that is a bare `$ref` | **DeepSeek strict tools: HTTP 400 "field `anyOf`: missing field `type`"** (not in their docs) | `typed_union_branches` inlines such branches for strict tools only (13 KB → 52 KB, cached after the first call), proven to accept exactly the same documents |

`to_transport` and `from_transport` round-trip losslessly (property-tested over random parameters).
`wire_schema(schema, mode, defs_key)` is the **single rule** for what each mode sends; the cost estimate and the
eval projection use it too.

### 9.3 Providers (`ai/providers/`, `config/llm.json`)

| provider | SDK | writer → escalation | structured-output ladder | notes |
|---|---|---|---|---|
| DeepSeek | `openai`, base `https://api.deepseek.com` (`/beta` for strict tools) | `deepseek-flash` (V4.1-Flash) → `deepseek-v4-pro` | strict function calling (one tool `submit_reply`, `tool_choice` forced) → JSON mode (prompt must contain "json" **and an example**) | thinking disabled (`extra_body`); peak/off-peak prices (off-peak half price); cached tokens in `prompt_cache_hit_tokens` |
| Kimi / Moonshot | `openai` | `kimi-k2.6` → `kimi-k3` | `response_format=json_schema, strict` → JSON mode | `max_completion_tokens`; no temperature; not measured (no key) |
| Claude | `anthropic` (claude-api skill read first) | `claude-haiku-5-5` (no escalation) | `output_config.format` json_schema → prompted JSON | `effort: low`; no temperature or prefill; system block with `cache_control: ephemeral`; refusal `stop_reason`; not measured (no key) |

* **Mode ladder:** on HTTP 400 for a structured mode, the next mode is tried and the working mode is
  remembered. **The rejection is logged with the API's reason at zero cost** (`ledger.mode_rejections`). Without
  that log, the DeepSeek schema problem could not be diagnosed.
* **Parsing:** `split_json_object` decodes **exactly one** JSON object with `raw_decode`.
  * **Accepted:** closing brackets or prose after the object, which are logged. DeepSeek often appends one stray
    `}`, in 2 of the first 3 strict-tools replies.
  * **Rejected:** a second object (ambiguous) and a reply that stops mid-object.
  * Every parse error quotes the text around the failing position.
  * **Never** use "first `{` to last `}`": it pulls the stray brace in.
* **Spend ledger** (`ai/ledger.py`, SQLite table `llm_calls`): every call's provider, model, mode, feature,
  uncached / cached / cache-write / output tokens, cost, latency, peak flag, ok flag and note.
  `ensure_budget(scope, worst_case)` runs **before** each call.

### 9.4 Prompt design (`ai/prompts.py`)

* **Static, cacheable prefix:** one static system prompt, generated from the indicator catalogue, with worked
  examples that tests validate against the schema. It is byte-identical for every request, so the ~5K-token
  prefix is a cache hit after the first call. DeepSeek: first request $0.0017, later ones about $0.0005.
* **Untrusted input:** user text is fenced in `<<< >>>`, and a test proves user text cannot close the fence.
  Pine comments are treated as untrusted (adversarial case a05).
* **Prompt extraction:** a canary string (`SL-CANARY-7F3A`) must never appear in a reply.
* **Repair:** the repair message quotes every validator error with its JSON path. The escalation message
  includes the original request, the last reply and its errors.

### 9.5 Eval (`ai/evaluation.py`, `evals/ai_eval.json`)

* **Set:** 30 generate (some deliberately vague, with scripted answers to the model's questions), 5 edit,
  5 Pine translations, 5 adversarial: live trading with a fake key, prompt extraction, a 100x martingale with no
  stop, look-ahead, injection in Pine comments.
* **Scoring:**
  * **Validity:** first try and after repair.
  * **Intent:** objective expectation checks, plus a **blind, batched LLM judge** that sees only the
    deterministic renderings (with shuffled labels) and the user's clarifying answers.
  * **Safety:** model-level (the first reply) vs system-level (the final result), both scored.
* **Cost control:** a **pre-flight projection** stops the run before any call if it exceeds the budget.
* **Recording:** every reply is recorded (`evals/recorded/*.json`). A test **replays recordings through today's
  pipeline**, and `--rescore` recomputes scores without API calls.
* **Crash safety:** writer results are saved **before** judging.

### 9.6 What the real run taught (DeepSeek, 45 cases; REPORT §5)

* **Validity after repair is the number that matters.** 12% of first replies were unusable; all were fixed by
  quoting the validator errors.
* **The model's own notes can be wrong.** In g11, they claimed a "1% above VWAP" threshold the rules did not
  implement. Always show the deterministic rendering.
* **Evals test the harness as much as the model.** Four harness bugs were found, none of them the model's (§12).
* **The judge needs the writer's context.** A manual check of 11 judge verdicts agreed on 9.
* **"Strict" output is not airtight.** The stray brace persists in strict mode, and the 88% first-try figure was
  in **JSON mode**. **Open:** first-try validity in strict mode is not yet measured
  (`uv run python -m strategy_lab.ai.evaluation`, about $0.05).
* **Data location:** DeepSeek processes data in the PRC, and Kimi's operator is in Singapore with its parent in
  Beijing. For Mirrorlane, make the provider a **user-visible setting**, and never put account data, keys or
  positions in a prompt.

---

## 10. API, jobs and UI (`api/`, `ui/`)

* **One process, two roles.** FastAPI serves both the JSON API and the Jinja2 + HTMX pages (Builder, Backtest,
  Lab, Compare, Costs). JSON routes:
  * data and specs: `GET /api/data/coverage`; `GET/POST /api/specs`, `GET /api/specs/{ref}`,
    `POST /api/specs/validate`, `POST /api/specs/render`;
  * AI: `GET /api/ai/providers`, `POST /api/ai/{generate,edit,explain,from_pine}`;
  * runs: `POST /api/backtests` and `POST /api/lab` (both return 202 + a job), `GET /api/backtests[/{id}]`,
    `GET /api/lab[/{id}]`, `GET /api/jobs[/{id}]`, `GET /api/costs`.
* **Jobs:** backtests and lab runs are **jobs**, executed by a pool of **2 spawned worker processes**. This keeps
  NautilusTrader's runtime and its ~1 GB per run out of the web process. Workers write stage and progress to the
  database, the browser polls a fragment once a second, and jobs left "running" by a dead server are marked
  failed at start-up.
* **Store:** SQLite (`data/strategy_lab.sqlite`, overridable with `STRATEGY_LAB_DB`) holds specs, jobs,
  backtests, lab reports and the LLM ledger. **Every stored result carries the spec, data source, range, and
  engine name and version**, so it can be re-run.
* **Charts:** Lightweight Charts 4.2.3 (equity vs buy-and-hold, candles with trade markers) and Plotly 2.35.2
  (heat-map, Monte Carlo histogram).
  * **Sampling:** equity is thinned to ≤ 4,000 points and candles to ≤ 3,000, at the finest timeframe that fits.
  * **Fit:** set `timeScale.minBarSpacing` (here 0.001) and `lockVisibleTimeRangeOnResize: true`. Otherwise
    `fitContent()` cannot fit a long run (the default needs ≥ 0.5 px per point) and silently shows only the most
    recent years.
* **Assets:** pinned on jsDelivr, plus `scripts/vendor_assets.py`, which downloads the same versions from the npm
  registry and checks SHA-512. Pages prefer the local copy.

---

## 11. Testing and quality

* **259 tests** (`make test`, pytest-xdist):
  * data parsers and selection;
  * resampling and validation;
  * validator (43 tests);
  * indicators (exact equality with Nautilus, real and synthetic data);
  * Nautilus semantics probes;
  * spec-in-Nautilus;
  * parity;
  * lab;
  * AI transport, providers (through the real SDKs on a mock `httpx2` transport), builder and eval (including
    replay of real recordings);
  * API (real background jobs on both engines);
  * properties (hypothesis).
* **Real-data tests** skip without `make data`, and they **resolve whichever stored dataset covers their window**,
  never a hard-coded source name.
* **`make lint`:** ruff (including `PLW1514`, explicit encoding) and `ruff format --check`, plus mypy (strict on
  spec, engines, lab, AI).
* **`make demo`:** catalogue validation, one backtest on both engines (asserts identical trades), a lab run, and
  the AI builder if a key is set. 38–44 s on Linux, 130 s on the user's PC.
* **Rule followed throughout:** every bug fix came with a test that **fails on the old code**. This was checked
  each time, by temporarily restoring the old line.

---

## 12. Every significant bug found, with root cause and fix

| # | found by | symptom | root cause | fix (guard) |
|---|---|---|---|---|
| 1 | probe | market orders filled at the signal bar's close | Nautilus processes queued orders at the current bar | latency 1 ns + synthetic open bars (`test_nautilus_semantics`) |
| 2 | probe | take-profit limits filled 1 tick worse | `FillModel` slips every L1 fill | order-type-aware fill model |
| 3 | probe | position left unprotected | `reject_stop_orders=True` rejects a stop already through the market | `False` |
| 4 | funding never charged | bars and funding in 1970 | pandas 3 reads Parquet as µs; the wrangler assumes ns | normalise to ns at storage |
| 5 | slow runs | 2 months took 2.4× one month | `PortfolioAnalyzer` concat per trade (O(n²)) | `patches.py` + identical-statistics test |
| 6 | parity | one take-profit 1 tick apart in 108 trades | `Price.as_double()` is one ulp off | `round_price` on the tick grid |
| 7 | parity | trailing stop differs after a gap | Nautilus rejects a modify into the market | mirror it; read the live trigger |
| 8 | quality pass | WMA/HMA segfault in a new process | recursive `@njit` + `cache=True` | iterative pairwise sum, per-indicator equality test, coverage parity |
| 9 | memory | sweep workers ~870 MB each | the fast path imported Nautilus via a shared helper | engine-neutral `contracts.py`, lazy imports |
| 10 | data | gold daily breaks off by an hour | HistData's documented "EST, no DST" is wrong; it is UTC−5 + **EU** DST | scored three clock hypotheses against the 17:00 New York break |
| 11 | data | flat zero-volume Bitstamp minutes | the publisher fills outages | dropped (never keep invented prices) |
| 12 | data | US holiday early closes flagged as gaps | no holiday calendar | US exchange-holiday calendar |
| 13 | data | a provenance CSV parsed as prices | file-name filter | select files by role |
| 14 | lab | 1-D heat-map for single-indicator specs | default axes from one indicator | first two tunables |
| 15 | UI | default range past the funding data | the window ignored funding | capped (later superseded by #26) |
| 16 | Windows | files misread | locale encoding | UTF-8 everywhere (67 call sites + ruff rule) |
| 17 | real eval | safety 60% | a reply without a spec was scored unsafe | "incomplete ≠ unsafe"; `--rescore` from recordings |
| 18 | real eval | e02 forced a meaningless edit | eval item was a no-op, and the builder rejected unchanged specs | two-sided base; `UNCHANGED` warning |
| 19 | real eval | vague prompts judged harshly | the judge never saw the clarifying answers | `judge_request` includes them |
| 20 | real eval | one item unjudged, cause unknown | judge replies were not recorded | tolerant label parsing; judge replies recorded |
| 21 | ledger | every writer call silently in JSON mode | 400 reason discarded | rejections logged with reason |
| 22 | logged 400 | DeepSeek rejected strict tools | `anyOf` branch without `type` | `typed_union_branches` (equivalence test) |
| 23 | strict run | "Extra data" parse failure | stray `}` after a complete object; parser used first `{`…last `}` | `split_json_object` + notes |
| 24 | real eval | crash after 45 paid cases; results lost | rewrite assumed every schema has `$def`; results written only after judging | pass-through; save before judging; per-item judge errors; every-schema-every-mode test |
| 25 | eval | strict-mode cost underestimated | estimate used the unrewritten schema | `wire_schema` shared by request, estimate and projection |
| 26 | pre-flight review | 2024 backtest would fail, 3-year window silently truncated, once Lighter data exists | "first stored dataset" ignored dates | coverage-aware choice; partial funding labelled; matching default window |
| 27 | open network | `npx` never launched on Windows | `npx.cmd` needs its full path | `shutil.which` path + UTF-8 decode |
| 28 | user stopped `make data` | half-written dataset or page could persist | delete-then-write, in-place page writes, CLI writing the final name | staging swap; atomic pages; `.part.csv` (interruption tests) |
| 29 | open network | two real-data tests skipped although data existed | hard-coded `binance_spot_gh` | resolve by coverage |
| 30 | open network | quality table broken; Dukascopy reason lost | multi-line detail; banner kept, reason truncated | one-line details; keep "Something went wrong…" |
| 31 | demo on a UTC+6 PC | coverage one day late; window maths on local dates | DuckDB returns timestamps in the machine's zone | `SET TimeZone='UTC'` (test under two zones) |
| 32 | strategy research | lab metrics ≠ direct backtest (317 vs 305 trades) | warm-up start before Binance's first bar → whole lab run moved to Bitstamp | `history_from`: datasets chosen by the window, warm-up from the same datasets |
| 33 | user screenshot | 8-year equity chart started in 2020 | Lightweight Charts' 0.5 px minimum bar spacing | `minBarSpacing` + `lockVisibleTimeRangeOnResize` (reproduced and verified in headless Chromium) |
| 34 | benchmark | "cold (incl. JIT compile)" row was 0.29 s | it loaded Numba's on-disk cache | relabelled; a true first run is 3.4 s |

**The pattern behind most of them:**
* The prototype was built in a sandbox where Lighter, Binance's archive and Dukascopy were blocked, and the PC was
  UTC Linux.
* Bugs #26–#33 only appeared on an **open network, on Windows, in a non-UTC zone, or with an interrupted run**.
* In Mirrorlane, **test with all sources present, on Windows and macOS, under a non-UTC `TZ`, and with
  interrupted jobs.**

---

## 13. Strategy research result: trend-filtered breakout

**Method:**
* **Evidence first:** published evidence favours simple trend rules on **daily** Bitcoin data, with trend
  filters improving risk. Sources: Pagnottoni & De Giuli; Rozario et al., arXiv 2009.12155; LUT thesis.
* **Candidates:** 7 textbook variants, **no tuning**, BTC 2018-06 → 2026-07:
  * close crossing 50-, 100- and 200-day SMAs;
  * a Turtle-style 20/10 breakout;
  * an EMA 20/100 cross;
  * 4-hour Donchian breakouts with and without a daily filter;
  * long-only vs long-and-short.
* **Check:** the winner went through the lab.

**Winner:** `docs/strategies/trend_filtered_breakout.json`.
* **Bars and filter:** 4-hour bars, trading only in the direction of the 100-day SMA of **completed daily** bars.
* **Entry:** long when the close crosses above the previous bar's 20-bar Donchian upper band while above the SMA;
  short when it crosses below the 20-bar lower band while below the SMA.
* **Exit:** on the opposite 10-bar band.
* **Risk:** 2 × ATR(20) stop, 3 × ATR(20) trailing stop, 100% of equity at 1x, zero-fee tier, funding on.

| BTC, 2018-06 → 2026-07 (sandbox data) | strategy | buy & hold |
|---|---|---|
| total return / CAGR | +1,865% / 44.6% | +683% |
| max drawdown | −40% | −77% |
| Sharpe / Sortino / Calmar | 1.15 / 1.99 / 1.10 | — |
| trades, time in market | 305, 38% | 100% |
| 2018 (Jun–Dec) / 2022 (bear years) | +39% / +55% | −51% / −64% |
| 2021 | −10% (its only losing calendar year) | +60% |
| **out-of-sample, Jan 2024 → Jul 2026, textbook parameters** | **+114%, max DD −22%, Sharpe 1.22** | +40% |

**Lab: 80/100.**
* Out-of-sample retention 97%.
* Walk-forward: 60% of 45 two-month windows profitable.
* Parameter stability 92%: Sharpe stays 1.0–1.2 across entry 15–30 bars and exit 6–15 bars.
* Monte Carlo: 0% of 1,000 resamples lose money.
* 305 trades.

**Weaknesses:**
* 7 tunables (`TOO_MANY_PARAMETERS`).
* It lags strong bull markets (2020–21: +67% vs +302%).
* A −40% drawdown.
* Funding is its main cost: $18k over the period, on a $10k start that grew to about $196k.

**On the user's PC** (Binance archive + funding, 2018-01 → 2026-09): +1,767%, CAGR 40.2%, DD −40.4%, Sharpe
1.08, 326 trades, consistent with the sandbox.

**Variants tested:**
* Without the trailing stop: higher full-period return, but a −45% drawdown and an out-of-sample Sharpe of 0.90.
* Without the daily filter: drawdown −49%.

This is a candidate for Mirrorlane's catalogue, **after** it is added to the parity suite. It is not a trading
recommendation.

---

## 14. Implementing it in Mirrorlane: plan and acceptance criteria

Order chosen so each step is verifiable before the next depends on it. "Reuse" means port the module with its
tests. Keep the tests green in Mirrorlane's CI from the first commit.

### M0. Decisions to make first
* **Backtest-only boundary:** keep the lab's code free of exchange credentials and order placement, even if
  Mirrorlane trades live elsewhere. Run it as a separate service or package with no access to trading keys.
* **Markets:** which Lighter markets in v1? BTC and XAU work today. ETH, SOL and others only need entries in
  `engines/contracts.py`, `BAR_SOURCES` / `FUNDING_SOURCES` and the Lighter market ids from `orderBookDetails`.
* **LLM provider policy:** default writer (§9.6, data location), user choice, and per-user spend limits.

### M1. Market data service
* **Reuse:** `data/sources/*`, `validate.py`, `resample.py`, the `storage.py` layout, `pipeline.py` logic, and
  `engines/inputs.py` dataset selection.
* **Change:**
  * Schedule incremental updates. The current pipeline does full monthly refreshes; Lighter candles can be
    appended from the last stored timestamp.
  * Move storage to Mirrorlane's object store, keeping Parquet and the partitioning.
  * Keep `.part` / staging-swap atomicity.
* **Accept when:**
  * the quality report shows Lighter BTC/XAU 100% complete;
  * the Lighter vs Binance cross-check median is ≲ 3 bps;
  * the selection tests in `tests/test_sources.py` pass;
  * an interrupted refresh leaves the previous dataset readable.

### M2. Strategy spec, validator, renderer
* **Reuse as is:** `spec/` and the catalogue. The schema is versioned (`spec_version`); add fields under a new
  version, never by changing v0.1 semantics.
* **Accept when:** the validator tests (43) and the property tests pass, and `python -m strategy_lab.spec`
  exports the JSON Schema.

### M3. Fast engine + NautilusTrader parity harness
* **Reuse:** `engines/fast`, `engines/contracts.py`, `results.py`, `lab/metrics.py`. Keep `engines/nautilus` as a
  **CI-only reference** (heavy dependency: ~1 GB per run).
* **Accept when:**
  * `tests/test_parity.py` gives identical trades on every catalogue strategy, both fee profiles, every risk
    variant and indicator-coverage strategy;
  * the per-indicator exact-equality test passes;
  * a 1-year backtest runs in < 0.2 s warm.
* **Pitfalls:** §15 items 1–12. **Any change to §6 semantics must change both engines and the parity tests
  together.**

### M4. Robustness lab
* **Reuse:** `lab/`.
* **Change:** run lab jobs on Mirrorlane's worker fleet, with progress events instead of SQLite polling; cap grid
  size and Optuna trials per user tier.
* **Accept when:** `tests/test_lab.py` passes, a 3-year 9×9 report finishes in < 60 s on 1 core, and every report
  stores the spec, data source, range and engine version.

### M5. AI builder
* **Reuse:** `ai/transport.py`, `prompts.py`, `builder.py`, the `providers/` layer, `ledger.py` concepts, and the
  eval set with its recordings.
* **Change:**
  * per-user ledgers and limits in Mirrorlane's database;
  * the provider as a user setting;
  * run the eval in CI against recordings (replay test), and live only on demand with a budget.
* **Accept when:** the eval shows ≥ 95% valid after repair and 100% system-level safety on every enabled
  provider; the replay test passes; the pre-flight projection stops an over-budget run before any call.
* **Before switching default writers,** run `make eval` with each provider's key. Claude Haiku 5.5 and Kimi were
  never measured.

### M6. API, jobs, UI
* **Replace:** SQLite → Mirrorlane's database; the 2-process pool → a real job queue with separate engine
  workers (never in the web process); HTMX pages → Mirrorlane's front-end.
* **Keep:**
  * the JSON API shapes (`api/app.py`), job states and progress;
  * the chart rules (§10);
  * always showing the **deterministic rendering** beside AI output;
  * the "backtest only" banner.
* **Accept when:** the `tests/test_api.py` equivalents pass, including both engines through the job system with
  identical results.

### M7. Hardening
* Multi-user isolation, quotas, observability (per-job timing and memory; LLM spend dashboards), and data
  freshness alerts.
* Test matrix: Linux, Windows and macOS; a non-UTC `TZ`; all sources present and each one missing; interrupted
  jobs (§12's pattern).

### Known limitations and open items (carry into the backlog)

* **Strategy format gaps** (the eval cases the model could not express):
  * arithmetic between operands ("1% above VWAP", g11);
  * pyramiding and partial exits (p04);
  * Supertrend (p05);
  * equality operators (g21).
* **One position per strategy; no portfolios** or multi-asset backtests.
* **Slippage is 0 or 1 tick** with no market impact. A Lighter order-book depth model would be the next realism
  step (Nautilus caps slippage at 1 tick, so parity would need a different reference approach).
* **Gold:**
  * no free long funding history (Lighter XAU funding starts 2025-10-20, charged as "partial");
  * HistData is bid-only with no volume, so volume indicators are rejected for XAU;
  * Dukascopy (bid + ask) answered 202.
* **AI:** strict-mode first-try validity is not yet measured; Kimi and Claude were not measured.
* **Concurrency:** the prototype is single-user (SQLite, local processes).

---

## 15. Pitfall checklist

1. Stamp Nautilus bars at their **close**, not their open.
2. Normalise timestamps to **ns**; pandas 3 reads Parquet as µs.
3. Nautilus market orders fill at the **same** bar's close unless you add latency + open bars.
4. Nautilus bar execution is never stop-first; feed a direction-aware path.
5. Nautilus `FillModel` also slips limit orders.
6. `reject_stop_orders=True` leaves positions unprotected.
7. Nautilus does not charge funding; add a `SimulationModule`.
8. Patch the quadratic `PortfolioAnalyzer` for trade-heavy runs.
9. Canonicalise prices; `Price.as_double()` can be one ulp off.
10. Nautilus indicator defaults are not textbook (RSI, ATR, WMA, ROC, Bollinger, Stochastic, VWAP, OBV).
11. Bit-identical indicators need identical summation order (pairwise vs sequential) and identical seeding.
12. No recursive `@njit` functions with `cache=True`.
13. Keep NautilusTrader out of the web process and out of fast-engine workers.
14. Warm indicators on data **before** a window, and never let the warm-up change which dataset is used.
15. Choose datasets by **coverage of the window**; a short, recent source must never truncate a longer test.
16. Label partial funding; never charge funding silently for part of a window.
17. `SET TimeZone='UTC'` on every DuckDB connection; never derive dates from local time.
18. Explicit UTF-8 on every text read and write (Windows).
19. Atomic writes (`.part` → rename; staging → swap) for anything a user might interrupt.
20. Launch external CLIs by their resolved path (`npx.cmd` on Windows).
21. Never trust "strict" LLM output: parse exactly one JSON value and validate everything.
22. Log the **reason** for every structured-output fallback.
23. DeepSeek strict tools: every `anyOf` branch needs a `type`; schema key `$def`; JSON mode needs "json" + an
    example; disable thinking.
24. One static system prompt + one reply schema for all tasks, for prompt caching.
25. Estimate worst-case cost from the schema actually sent, and check the budget before every call.
26. Save expensive results before any later step that can fail (the judge crash cost a full eval run).
27. Show users the deterministic rendering of a spec, never only the model's description.
28. Equity charts: lower `minBarSpacing` or long backtests lose their start.
29. Real-data tests must resolve datasets, never hard-code a source name.
30. Every bug fix needs a test that fails on the old code. Confirm it by restoring the old line.

---

## 16. Appendix

**Commands** (`make` on Linux and macOS; on Windows prefix with `uv run` as shown):

| task | command |
|---|---|
| install | `make setup` (`uv sync --frozen`, pre-commit, vendored chart libraries, `.env` from `.env.example`) |
| data | `make data` / `uv run python -m strategy_lab.data` |
| end-to-end demo | `make demo` / `uv run python scripts/demo.py` |
| web UI | `make ui` / `uv run uvicorn strategy_lab.api.app:app --host 127.0.0.1 --port 8000` |
| tests, lint | `make test`, `make lint` |
| parity, benchmarks | `make parity`, `make bench` (the NautilusTrader part takes hours) |
| AI eval | `make eval` / `uv run python -m strategy_lab.ai.evaluation [--providers …] [--rescore NOTE]` |
| AI CLI | `uv run python -m strategy_lab.ai generate "…"` (also `edit`, `explain`, `from_pine`, `spend`) |
| lab CLI | `uv run python -m strategy_lab.lab <spec.json> --start … --end … [--params a,b] [--optuna N] [--out f.json]` |

**Environment:** `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY`, `ANTHROPIC_API_KEY` (in `.env`, optional);
`STRATEGY_LAB_DATA_DIR` (data folder); `STRATEGY_LAB_DB` (SQLite path).

**Related documents:** `REPORT.md` (results and verdict), `ARCHITECTURE.md` (packages and the contract),
`LEARNINGS.md` (NautilusTrader internals and provider dialects), `DATA.md` (sources, quirks, cross-checks,
the open-network run), `PROGRESS.md` (phase log, every problem as it was found), `docs/notes/llm_provider_facts.md`
(provider facts with sources), `evals/judge_check.md` (manual judge review).
