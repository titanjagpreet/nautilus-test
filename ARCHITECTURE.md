# ARCHITECTURE

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
   schema (Pydantic, JSON Schema) · indicator catalogue · validator · renderer ·          │
   evaluator (bar-by-bar) · decisions (position rules shared by both engines)             │
                  │                                                                       │
        ┌─────────┴──────────────────────────────┐                                        │
        ▼                                        ▼                                        │
 engines/nautilus (reference)            engines/fast (Numba)      ◄── engines/inputs ◄───┘
 SpecStrategy + execution feed           vectorised indicators +      (same tick-rounded bars
 + funding module + fill model           one jitted 1m loop            and funding for both)
        │                                        │
        └──────────── BacktestResult ────────────┘   (engines/results.py: trades, funding, equity)
                             │
                      strategy_lab/lab   metrics · OOS · walk-forward · sweeps/heat-map · Monte Carlo · score
                             │
                      strategy_lab/api (FastAPI, SQLite results + job queue) ── strategy_lab/ui (Jinja2 + HTMX)
```

## Packages

| package | role |
|---|---|
| `strategy_lab/data` | sources (`sources/`), normalisation + validation (`validate.py`), Parquet storage + DuckDB (`storage.py`), resampling (`resample.py`), the `make data` pipeline (`pipeline.py`) |
| `strategy_lab/spec` | spec schema v0.1, indicator catalogue, validator, renderer, parameters, bar-by-bar evaluator, shared position-management decisions, catalogue JSON |
| `strategy_lab/engines/nautilus` | instruments, venue, fill model, funding module, hand-written Phase 2 strategy, generic `SpecStrategy`, execution feed, runners, reports, analyzer patch |
| `strategy_lab/engines/fast` | Numba engine (Phase 4) |
| `strategy_lab/engines/inputs.py`, `results.py` | what both engines read (tick-rounded bars, funding) and write (`BacktestResult`) |
| `strategy_lab/lab` | robustness lab (Phase 6) |
| `strategy_lab/ai` | LLM layer and eval (Phase 5) |
| `strategy_lab/api`, `strategy_lab/ui` | FastAPI app and web UI (Phase 7) |

## Execution semantics (identical in both engines)

These are the contract. The Numba engine implements them directly; NautilusTrader is made to follow them with
the mechanisms in LEARNINGS.md §7. The parity suite checks they agree.

**Data.** Strategy ("base") bars and higher-timeframe bars are built from the same 1-minute bars
(UTC-anchored bins, open-time labels). Prices are rounded to the instrument tick once, before either engine sees
them. A base bar closes at `bin start + timeframe`; a bin with no 1-minute bars produces no bar.

**Signals** are evaluated when a base bar closes, using values up to and including that bar. Higher-timeframe
indicators only use **completed** HTF bars: an HTF bar ending at `T` is usable from the base bar that closes
at `T`. A rule fires only when every operand it references is available (indicator warmed up; for crosses also
one bar earlier); otherwise it is false. See `spec/evaluator.py` for operator definitions.

**Decisions at a base-bar close** (`spec/decisions.py`, in this order):
1. In a position: exit if the exit rule fires or `time_exit_bars` base bars have closed since entry. If the
   opposite entry rule fires and a new entry is allowed (cooldown 0, daily cap not reached), exit and reverse.
2. Flat: enter if exactly one allowed entry rule fires, `bars since exit ≥ cooldown_bars`, and fewer than
   `max_trades_per_day` entries were taken on the UTC date of this bar's close. Both entry rules at once → none.
3. Still in a position: move the trailing stop (computed from this close; never loosened).
4. Size: notional = `percent_equity` × cash balance (or `fixed_usd`), capped at `leverage × balance`; quantity =
   notional / this close, rounded **down** to the lot size; below the minimum quantity → no trade.

**Fills.**
* **Market orders** (entries, exits, reversals) fill at the **open of the next 1-minute bar** after the signal
  (for XAU that can be after a weekend), ± `slippage_ticks` × tick against you, taker fee.
* After an entry fills at price `P`, the **stop-loss** (stop-market) and **take-profit** (limit) are placed,
  priced from `P` and the ATR / structure values of the signal bar. A stop that is already through the market
  fills immediately at the current price ± slippage.
* Each following 1-minute bar is checked in this order: **open** (gap) — a stop beyond the open fills at the
  open ± slippage, a take-profit beyond the open fills at its limit price; then the **adverse extreme** (low for
  longs, high for shorts) — stop fills at its trigger ± slippage; then the **favourable extreme** — take-profit
  fills at its limit price, maker fee. **If both could fill in the same minute, the stop wins.**
* A trailing-stop change decided at a bar close takes effect after the next bar's open has been checked against
  the old stop.
* Positions still open when the data ends are closed at the last close ± slippage (exit reason `end`).

**Funding** is charged at each funding timestamp `F` on the position held after every fill stamped `≤ F`, at the
last traded price at or before `F`: payment = signed size × price × rate (positive rate: longs pay). The
`funding_rate` rule input is the latest settled rate at the bar close, scaled to an 8-hour period.

**One position at a time** per strategy; fees are `fee_profile` maker/taker rates on notional.

**Not modelled:** market impact or partial fills (fills are assumed to be small relative to liquidity),
liquidation (margin is only checked for sizing), order rejections other than those above, latency beyond
"next bar open", mark vs last price differences.

## Results and reproducibility

Both engines return `engines/results.BacktestResult`: trades (minute-stamped fills, fees, funding, PnL), the
funding ledger and an equity curve computed by one shared function. Results stored by the API carry the spec,
data source and range, and the engine name and version, so any result can be re-run.
