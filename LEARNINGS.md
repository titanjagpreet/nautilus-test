# LEARNINGS — NautilusTrader, explained while building Strategy Lab

**Installed version: `nautilus_trader==1.231.0`** (PyPI, wheel `cp313-manylinux_2_35_x86_64`, uploaded 2026-08-02;
latest stable at the time of writing — `2.0.0rc1..rc6` exist and were deliberately not used). Python 3.13.16.

Every claim below was checked either by reading the installed source (the wheel ships the `.pyx` files under
`site-packages/nautilus_trader/`) or by running a probe. The official docs site (nautilustrader.io) is blocked
from the build sandbox, so **the installed source is the reference**. Probes live in `tests/nautilus_semantics/`
(added in Phase 2/3) so every statement here stays executable.

---

## 1. The mental model

| Concept | Plain words |
|---|---|
| `BacktestEngine` | The low-level API. You build it in code: add a venue, instruments, data, strategies, then `run()`. Everything in this project uses it. |
| `BacktestNode` | The high-level API: the same engine, but configured from `BacktestRunConfig` objects and fed from a `ParquetDataCatalog`. Good for batch runs from config files. |
| Venue / `SimulatedExchange` | A fake exchange. `add_venue(...)` creates it with an OMS type (NETTING = one position per instrument, HEDGING = many), account type (MARGIN for perps), balances, leverage, fee model, fill model, latency model and a set of switches. |
| `OrderMatchingEngine` | One per instrument inside the venue. It keeps an L1 "book" built from your market data and decides when resting orders fill. |
| Instrument | Contract specification: price/size precision and increment, currencies, margin, maker/taker fee. A perpetual is `CryptoPerpetual`. |
| Bar / `BarType` | OHLCV for a period. `BarType` string = `INSTRUMENT-STEP-AGGREGATION-PRICE_TYPE-SOURCE`, e.g. `BTC-PERP.LIGHTER-1-MINUTE-LAST-EXTERNAL`. `EXTERNAL` = you supply it; `INTERNAL` = Nautilus aggregates it. |
| `ts_event` / `ts_init` | Nanosecond UNIX timestamps. The engine orders data by `ts_init`. **A bar must be stamped at its close time**, otherwise a strategy can see it before it has finished (look-ahead). Exchange files are usually stamped at the *open* time — shift them. |
| Strategy | Your code. Callbacks: `on_start`, `on_bar`, `on_order_filled`, `on_position_closed`, ... |
| Actor / `SimulationModule` | An Actor is a strategy without trading. A `SimulationModule` is an Actor plugged *into the simulated venue* with hooks `pre_process(data)` and `process(ts_now)`; it can adjust the account (that is how FX rollover interest is implemented, and how we charge funding). |

## 2. What happens for every piece of data (the order matters)

Read from `BacktestEngine._run` (`backtest/engine.pyx`). For each data point, in this order:

1. Advance the clocks; fire timers that are due *before* this timestamp.
2. **The exchange sees the data first** (`exchange.process_bar(bar)`): the matching engine moves its book through
   the bar's prices and fills any *resting* orders.
3. **Then the strategy sees it** (`DataEngine.process` → `on_bar`). Orders it submits go into the venue's message
   queue.
4. `_process_and_settle_venues(ts)`: queued commands are executed **at the current book price**, then simulation
   modules run `process(ts_now)`.

**Consequence (verified by probe):** a market order sent from `on_bar` fills at **that same bar's close**, not
at the next bar's open. With 1-minute bars the close and the next open are usually within a tick for BTC, but
across a gold weekend gap they can differ by tens of dollars.

## 3. How bars are executed

`OrderMatchingEngine.process_bar` (verified in source and by probe):

- Bars only execute when `bar_execution=True` and the book type is L1.
- **Only the finest bar type per instrument is used for execution.** If you feed 1-minute and 15-minute bars,
  the 15-minute bars are ignored by the matching engine (it remembers the smallest `timedelta` it has seen).
  `INTERNAL` bars are never executed against.
- Each bar becomes up to four "trade ticks": **Open → High → Low → Close** (fixed), or with
  `bar_adaptive_high_low_ordering=True`: Open → whichever of High/Low is *closer to the open* → the other → Close.
- A stop-market order triggered while the market "moves through" high/low/close fills **at its trigger price**;
  if the bar *opens* beyond the trigger (a gap) it fills **at the open** (market).
- A resting limit order fills **at its limit price**, even when the bar gaps through it (probe: TP limit at
  105.0, bar opened at 110.0 → filled at 105.0). Conservative.
- **Neither ordering is "stop first".** If a long's stop-loss and take-profit are both inside one 1-minute bar,
  fixed ordering always hits the High (take-profit) first; adaptive ordering hits whichever is closer to the
  open. Our spec requires "stop first" (the conservative assumption), so the generic strategy uses a custom
  data feed (see §7).
- Bar volume matters: each of the four ticks carries a quarter of the bar volume as available liquidity.

## 4. Slippage: `FillModel`

- `FillModel(prob_fill_on_limit, prob_slippage, random_seed)`. With `prob_slippage=1.0` every fill moves
  **one price increment against you** (`apply_fills`: `if L1 and fill_model.is_slipped(): px ± price_increment`).
- **Pitfall:** this applies to *every* fill on an L1 book — including **limit (take-profit) fills** (probe: TP limit
  at 105.0 filled at 104.9). A limit order filling worse than its limit is not realistic.
- **Fix:** subclass `FillModel`. `get_orderbook_for_fill_simulation(instrument, order, best_bid, best_ask)` is
  called just before each fill with the order; we record whether it is a `MARKET`/`STOP_MARKET` order, return
  `None` (keep the standard fill logic, which is what gives stops their trigger-price fill) and answer
  `is_slipped()` from that record. Result: market and stop fills slip one tick, limits never slip.
- **Limit found:** the hook can only move a fill by exactly *one* price increment. Returning a custom simulated
  book could move it further, but that path bypasses the trigger-price logic for stops (they would fill at the
  bar's extreme instead of the stop price). So Nautilus-side slippage is **0 or 1 tick per fill**; the spec
  limits `slippage_ticks` to that range.

## 5. Venue switches we rely on

| Switch | Default | We use | Why |
|---|---|---|---|
| `oms_type` | – | `NETTING` | one position per instrument, like a perp exchange account |
| `account_type` | – | `MARGIN` | perpetuals |
| `default_leverage` | – | 3 | from strategy/venue config |
| `bar_adaptive_high_low_ordering` | `False` | `True` for the hand-written strategy | more realistic than fixed O-H-L-C |
| `reject_stop_orders` | `True` | **`False`** | with `True`, a stop placed when price is already through it is *rejected* and the position is left **unprotected** (probe). With `False` it fills immediately at market. |
| `latency_model` | none | `LatencyModel(base_latency_nanos=1)` for the spec engine | makes orders reach the venue after the next data point (see §7) |
| `use_reduce_only` | `True` | `True` | exits can never flip the position by accident; a stale reduce-only order is rejected with "would have increased position" |

## 6. Funding is not simulated (1.231)

`FundingRateUpdate` exists as a **data type** (`model/data.pyx`: `instrument_id, rate, interval, next_funding_ns`)
used by live adapters and the cache, but nothing in `backtest/engine.pyx`, the matching engine, `accounting/` or
`portfolio/` reads it — `grep -i funding` finds nothing there. **The simulated exchange never charges or pays
funding.** We therefore charge funding with a small `SimulationModule` (modelled on the built-in
`FXRolloverInterestModule`): at each funding timestamp it computes `position size × last price × rate` and calls
`exchange.adjust_account(...)`, keeping its own ledger so funding appears as a separate line in results.

## 7. Making Nautilus follow our execution semantics exactly

The spec (ARCHITECTURE.md) says: signals at bar close; market orders fill at the **next bar's open** plus slippage;
stops/take-profits are checked inside each 1-minute bar and **the stop wins** if both could fill in the same bar.
Native bar execution does neither (§2, §3). What works, using only public extension points (all verified by probe):

1. **`LatencyModel(base_latency_nanos=1)`** — commands sent at the strategy bar's close time `T` arrive at `T+1ns`.
2. **An "open" bar at `T+1ns`** (O=H=L=C=next 1-minute open). The venue processes it first (resting stops get
   their gap check at the open), then drains the 1ns-delayed queue → **market orders fill at the next open**
   (+1 tick slippage).
3. **Direction-aware intrabar path.** The rest of the minute is fed as small bars whose price path visits the
   *adverse* extreme first: for a long, `(O,O,L,L)` then `(L,H,L,C)`; for a short or flat, `(O,H,L,C)` (fixed
   ordering already visits High first). Probe: long with SL 95 / TP 105 inside a bar with H=106, L=90 → stop filled
   at 94.9 (95 − 1 tick), take-profit cancelled.
4. The direction is only known at run time, so bars come from a **generator** registered with
   `engine.add_data_iterator(name, generator)`. Verified in `BacktestDataIterator.next()`: the generator is asked
   for the next chunk **at the moment the last item of the current chunk is handed out** (before it is processed).
   So each chunk ends with the next minute's "open" bar — which does not depend on direction — and the following
   chunk is built after the strategy has handled its bar and recorded its intended direction.
5. Stop-loss/take-profit are placed in `on_order_filled` relative to the **actual fill price**; they reach the venue
   at `T+2ns`, so a second "open" bar at `T+2ns` gives the queue a chance to drain before the intrabar path starts.

Cost: more data points per minute than native bar execution (measured in Phase 2/4 numbers below).

## 8. Indicator semantics (read from `indicators/*.pyx`) — several differ from textbook definitions

| Nautilus class | What it really computes | Pitfall / what we do |
|---|---|---|
| `SimpleMovingAverage(n)` | mean of last n inputs; `initialized` after n inputs | – |
| `ExponentialMovingAverage(n)` | α = 2/(n+1), **seeded with the first value** (not an SMA of the first n) | fast engine replicates the seed |
| `WeightedMovingAverage(n)` | **with no `weights` argument this is a simple average** (`np.average` without weights) | always pass linear weights `1..n` |
| `HullMovingAverage(n)` | WMA(2·WMA(n/2) − WMA(n), √n) with linear weights; early values use partial weights | replicated |
| `WilderMovingAverage(n)` | α = 1/n, seeded with first value | used for ATR, RSI, ADX |
| `RelativeStrengthIndex(n)` | **scaled 0–1, not 0–100**; default smoothing is **EMA (α=2/(n+1)), not Wilder**; the first bar feeds a 0 gain/loss | we use `ma_type=WILDER` and multiply by 100 |
| `RateOfChange(n)` | compares with the price **n−1 bars ago** (deque of length n), as a fraction | we create `RateOfChange(n+1)` and ×100 → textbook ROC(n) % |
| `MovingAverageConvergenceDivergence` | MACD line only | signal = EMA(signal) of the line, updated once the line is initialized; histogram = line − signal |
| `BollingerBands(n, k)` | bands around the SMA of the **typical price (H+L+C)/3**, population std | we feed `(v, v, v)` so the band is on the chosen source (close by default) |
| `AverageTrueRange(n)` | default smoothing **SIMPLE**, not Wilder | we use `ma_type=WILDER` |
| `Stochastics(k, d)` | default %D is `100·Σ(C−LL)/Σ(HH−LL)` ("ratio"), not SMA(%K); if HH = LL the update is **skipped** (values stay stale) | we use `d_method="moving_average"` with SIMPLE; fast engine replicates the skip |
| `DirectionalMovement(n)` | only smoothed +DM / −DM (EMA), **no ADX** | ADX implemented ourselves (Wilder) |
| `DonchianChannel(n)` | max high / min low **including the current bar** | `close > upper` with offset 0 can never be true → the validator flags it |
| `KeltnerChannel(n, k)` | EMA of typical price ± k·ATR (ATR default SIMPLE) | we pass `ma_type_atr=WILDER` |
| `VolumeWeightedAveragePrice` | resets when `ts_init.day` changes — with close-time stamps the **23:45–00:00 bar starts the next day's session** | we call `update_raw` with the bar's *open* time |
| `OnBalanceVolume` | signs volume by **close vs the same bar's open**, not vs the previous close | textbook OBV implemented ourselves |
| `CommodityChannelIndex(n)` | textbook: (TP − SMA(TP)) / (0.015 · mean abs deviation) | – |

`MovingAverage.initialized` flips once `count >= period`. The generic strategy never reads an indicator before it is
initialized, and the fast engine uses exactly the same warm-up lengths.

## 9. Loading bars: wrangler vs catalog

Both paths are implemented in `strategy_lab/engines/nautilus/data_loading.py` and give **identical results**
(verified on a month of real BTC data: 66 positions, same PnL, fees and funding to the cent; and by
`test_wrangler_and_catalog_produce_identical_bars`).

| | `BarDataWrangler` (direct) | `ParquetDataCatalog` |
|---|---|---|
| What it is | turns a pandas frame indexed by timestamp into `list[Bar]` you pass to `engine.add_data` | Nautilus's own Parquet store; `catalog.write_data(bars)` once, `catalog.bars(bar_types=…, start=…, end=…)` to read |
| Good for | one-off runs, tests, data you already have in pandas | many runs over the same data, data larger than memory (stream it with `BacktestNode`), sharing data between processes |
| Cost here | 2.3 s / 582 MB for one month | 3.3 s / 621 MB (writes and reads back) |

Pitfalls hit:
* **Timestamps must be the bar close.** The wrangler takes the frame's index as `ts_event` *as is*
  (`prepare_event_and_init_timestamps` → `index.view(np.uint64)`). Our data is open-time stamped, so we shift by
  one bar width first.
* **pandas 3 returns `datetime64[us]` from Parquet.** `index.view(np.uint64)` then yields *microseconds* and
  every bar lands in January 1970. It only worked by accident until we noticed funding (same root cause) was
  never charged. Fix: normalise every timestamp to nanoseconds at the storage boundary (`dt.as_unit("ns")`).
* **`ts_init_delta`** delays delivery. With 1m execution bars and 15m strategy bars sharing a timestamp, give the
  15m bars `ts_init_delta=1` so the venue processes the last 1m bar *before* the strategy decides
  (`test_finest_bar_type_drives_execution_and_ts_init_delta_orders_strategy_bars`).
* The wrangler expects exactly the columns `open, high, low, close, volume` (it uses `data.values` positionally).

## 10. Performance: a quadratic slowdown in the portfolio analyzer

Running the hand-written EMA strategy on **1-minute** bars, one month took 9.4 s but two months 22.3 s (2.4×).
`cProfile` showed pandas, not the matching engine: `PortfolioAnalyzer._append_pnl_record` runs
`pd.concat([existing, new])` **every time a position closes** (called from `Portfolio.update_position` via
`record_trade`). That is O(n²) in the number of trades, and pandas 3's Arrow-backed string index makes each concat
slow. A strategy with ~14,000 trades a year spends most of its time there.

Workaround: `strategy_lab/engines/nautilus/patches.py` buffers the records in lists and builds the same Series
right before the only method that reads them (`realized_pnls`). `tests/test_nautilus_patches.py` proves every
Nautilus statistic is identical; two months of 1m trading drop from 21.6 s to 11.0 s. The patch is applied by
the generic spec runner; the Phase 2 benchmark reports stock and patched timings side by side. (Worth reporting
upstream: append to a list and concat once.)

## 11. Smaller pitfalls

* `OrderFactory.bracket(...)` creates the take-profit with **`tp_post_only=True`** by default (maker-only).
* Bar **volume is liquidity**: each bar offers a quarter of its volume per price point; a larger market order is
  split and the rest fills one tick worse (`test_small_bar_volume_splits_market_orders`). Zero-volume data
  (our HistData gold) would starve fills, so the spec engine's execution bars carry a large volume (we model no
  market impact).
* `account.balance_total()` on a margin account **excludes unrealised PnL** — use it for "cash", not equity.
* `engine.get_result().elapsed_time` is the **simulated** time span in seconds, not wall time.
* Nautilus 1.231 calls `pd.Timestamp.utcnow()` internally, which pandas 3 deprecates (harmless warning, filtered
  in pytest config).
* A Python subclass of a Cython class (`FillModel`, `SimulationModule`, `Strategy`) can override `cpdef`
  methods and Nautilus will call the override — that is what makes the fill model and funding module possible.

## 12. Measured speed and memory (Phase 2, hand-written strategy, real BTC data)

4 vCPU sandbox, Python 3.13, NautilusTrader 1.231.0, each scenario in a fresh process
(`benchmarks/nautilus_phase2.py` → `benchmarks/results/nautilus_phase2.json`). "Stock" = NautilusTrader as
shipped; "patched" = with the `PortfolioAnalyzer` fix from §10 (identical results).

| scenario | data points | positions | stock wall | stock peak RSS | patched wall | patched peak RSS |
|---|---|---|---|---|---|---|
| empty node (import + engine + venue + instrument, no data) | 0 | 0 | 0.9 s | 370 MB (imports alone 77 MB) | – | – |
| 1 year of 1m bars, strategy on 1m | 525,600 | 14,038 | **575 s** | 1,303 MB | **127 s** | 1,265 MB |
| 5 years of 15m bars, strategy on 15m | 175,265 | 4,634 | 68 s | 1,068 MB | 30 s | 1,050 MB |
| 2 years: 15m strategy, venue on 1m bars | 1,121,280 | 1,760 | 50 s | 1,031 MB | 41 s | 1,139 MB |

What this says:
* **An empty engine already costs ~370 MB**, and a few hundred thousand bars push it past 1 GB. Every run must be
  a separate process if you want to run several in parallel on a small server.
* Throughput is ~25–35k data points/s when the strategy only reacts occasionally, but **~4k bars/s when the
  strategy's Python `on_bar` runs on every bar and trades often** — per-event overhead (message bus, order
  events, portfolio updates) dominates, not the matching engine.
* Without the analyzer fix, cost grows **quadratically with the number of trades**: unusable for 1-minute
  strategies over long periods.
* Parameter sweeps of hundreds of combinations are therefore impractical in Nautilus (≈ 0.5–2 min per run);
  that is what the Numba engine (Phase 4) is for.

## 13. Prices are fixed-point integers — `as_double()` is not the decimal

`Price`, `Quantity` and `Money` hold a 128-bit integer with 16 implied decimals. `Price.as_double()` converts
`raw as f64 / 1e16`; for a large raw value that conversion can land **one ulp away from the decimal**:
`Price(65031.3, 1).as_double()` returns `65031.299999999996`. Comparisons inside the venue are exact (integer),
but strategy code that does arithmetic on `as_double()` values can round differently at a half-tick. Found by
the parity suite: a take-profit computed as `entry + 1.5 × risk` from a fill price landed one tick lower in
Nautilus than in the fast engine on one trade out of 108 (Δ 0.003 USDC). Fix: treat every price as a decimal on
the tick grid — `round_price(price.as_double(), precision)` gives the nearest double of the decimal — in the
spec strategy and the funding module. After that, P&L parity became exact.

Similarly, `Money` amounts are rounded to the currency precision (USDC: 8 decimals) when they are booked: our
funding ledger keeps the raw amount, the account receives the rounded one; the fast engine mirrors both.

## 14. Modifying a stop into the market is rejected (even with `reject_stop_orders=False`)

`reject_stop_orders=False` only applies to *new* stop orders (they then fill immediately). A **modify** whose new
trigger is already through the market is always rejected (`OrderModifyRejected: new stop px … was in the
market`; `OrderMatchingEngine._update_stop_market_order` checks `is_stop_triggered`: a SELL stop triggers when
`bid <= trigger`, a BUY stop when `ask >= trigger`, both inclusive). The old stop stays active. Consequences:
* a trailing stop that should have tightened above a gapped-down open keeps its old level — strategy code must
  read the live trigger price (`order.trigger_price`) rather than remember what it asked for;
* the fast engine reproduces the rejection (`engines/fast/simulate.py`, step 3c).

## 15. One spec format, three structured-output dialects

The spec's canonical JSON Schema (Pydantic) cannot be handed to the providers' strict modes as-is:

| feature in the canonical schema | Claude `json_schema` | DeepSeek strict tools (beta) | Kimi `json_schema` strict |
|---|---|---|---|
| recursive condition trees (`all`/`any`/`not`) | **not supported** | supported (`$ref`) | supported in principle; K2.6 noted unstable with `$ref` |
| `oneOf` + `discriminator` (Pydantic unions) | use `anyOf` | `anyOf` only | `anyOf` |
| optional fields (not in `required`) | allowed | **every property required** | every property required |
| `params` as an open map (`additionalProperties: {number}`) | **must be `false`** | must be `false` | must be `false` |
| `minimum`/`maximum`, `minLength`, `pattern`, `minItems` | not supported | partly | partly |
| `$defs` key | `$defs` | documented as `$def` | `$defs` |

So the models write a **transport form** (`strategy_lab/ai/transport.py`), generated from the Pydantic schema:
condition trees unrolled to 3 levels, params as `[{"name","value"}]` pairs, optional fields required-but-
nullable, no bounds, `anyOf` instead of `oneOf`. It converts back losslessly (tested on the whole catalogue), and
everything the transport schema cannot say (bounds, look-ahead, leverage, contradictions) is enforced by
Pydantic + the validator, whose exact errors drive the repair loop. Two consequences worth knowing:

* **Schema-constrained output does not mean valid output.** A strict schema guarantees shape, not meaning: a
  model can still emit `leverage: 100`, `stop_loss: null` or an undefined indicator id. The validator is the
  safety net, and the eval measures the model-level and the system-level safety separately.
* **One reply envelope for every task** (generate / edit / explain / from_pine) keeps the tools/response-format
  block byte-identical across requests, so — together with a static system prompt — every provider's prompt
  cache can hit on the whole ~5K-token prefix; only the user message varies.

Fallback ladder: if an API rejects a structured-output mode with HTTP 400 (e.g. "schema too complex"), the
provider drops to the next mode (strict tools → JSON mode with the schema and examples in the prompt, which
DeepSeek requires to contain the word "json") and remembers it.

## 16. A second engine that matches NautilusTrader exactly

What it took for the Numba engine to give *identical* trades (`tests/test_parity.py`, REPORT §3):

* **Bit-identical indicators.** "Same formula" is not enough at crossing points: a moving-average cross decided
  by 1e-12 flips a trade. NumPy's `mean` uses pairwise summation, Nautilus's SMA keeps a running sum, and EMA
  seeding differs between libraries; each was ported in the exact operation order (`engines/fast/indicators.py`,
  `_pairwise_sum`), and every indicator type is tested for exact equality with the runtimes the Nautilus
  strategy uses, on synthetic and on real BTC data.
* **One shared definition of "a decision".** Position rules (exits before entries, time exit, reversal only
  without cooldown, daily cap by the signal's UTC date, trailing update after the next open's gap check) live
  in one module (`spec/decisions.py`) used by Nautilus's strategy and mirrored by the jitted loop.
* **Copy the reference's quirks deliberately.** Nautilus rejects a stop modified into the market and books
  `Money` rounded to the currency precision; the fast engine does the same, documented, instead of being
  "more correct".
* **Price canonicalisation.** Prices go through `round_price(..., decimals)` in both engines (§13).
* **Process memory, not CPU, limits parallel sweeps.** A spawned worker that (indirectly) imported Nautilus cost
  ~870 MB; after moving contract specs and shared helpers to engine-neutral modules and importing Nautilus lazily,
  a fast-engine worker costs ~480–550 MB (mostly Numba/LLVM and the data).
* **Numba's on-disk cache** (`cache=True`) makes a cold process start in ~0.3 s instead of several seconds of JIT
  compilation — **but a self-recursive jitted function does not survive it.** The pairwise-summation port was
  recursive like NumPy's; it worked when freshly compiled and **segfaulted when loaded from the cache** in the
  next process. No catalogue strategy used WMA or HMA, so the parity suite never ran it; a direct
  exact-equality test of every indicator (`tests/test_indicators.py::test_fast_engine_indicators_are_bit_identical`)
  exposed it. Fix: the same additions in the same order with an explicit stack (verified equal to
  `np.add.reduce` for sizes 0 … 1,000,003), plus parity strategies that use the eight indicator types the
  catalogue does not (`tests/test_parity.py::test_indicator_coverage_parity`). Lesson: parity on a catalogue
  only covers what the catalogue uses — test every building block directly too.

## 17. The lab and the UI

* **Out-of-sample windows need warm-up from *earlier* data.** With warm-up inside the window, a 2-month
  walk-forward window loses weeks to a 200-bar EMA on 4-hour bars. The fast engine got `trade_from`: indicators
  run on the preceding data, entries start at the window. Warming up on the past is not look-ahead; a real-data
  test shows the window run reproduces the full run's trades exactly.
* **Grid edges and spikes matter more than the best value.** The heat-map score is the best cell's neighbours
  relative to it; an optimum on the edge of the grid gets its own warning. For the EMA crossover, the best cell
  sat in the grid corner and the walk-forward optimum moved by 40–50% between windows.
* **Keep NautilusTrader out of the web process.** Backtest and lab jobs run in spawned worker processes that
  write progress to SQLite; the browser polls. A crash marks the job failed instead of leaving it "running".
* **`anthropic` 1.x and `openai` 3.x are built on `httpx2`,** not `httpx`: test transports and custom clients
  must come from `httpx2` (the type checker caught a mismatch).
* **Pinned CDN plus a verified local copy.** jsDelivr is blocked in the build sandbox but the npm registry is
  not: `scripts/vendor_assets.py` downloads the same pinned versions from the registry, checks the SHA-512
  integrity value, and the pages prefer the local copy.
