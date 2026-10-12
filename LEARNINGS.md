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
