# DATA — sources, coverage, verification, licences

`make data` (= `python -m strategy_lab.data`) downloads, normalises, validates and resamples everything below
and writes **`data/quality_report.md`** (full gap / outlier listings) plus machine-readable logs:
`data/source_log.json` (every source attempt), `data/datasets.json`, `data/crosscheck.json`,
`data/funding_verification.json`, `data/raw/github/manifest.json` (SHA-256 of every GitHub file).

Numbers below are from the run on **2026-10-12** in the build sandbox (last full month: 2026-09).

> **Licence warning.** Binance and Dukascopy (and HistData) market data are provided for personal / research
> use. They are used here **for personal learning only and must not ship in a commercial product** such as
> Mirrorlane. A commercial product needs licensed data (e.g. Lighter's own API data under Lighter's terms, or a
> paid vendor).

## 1. Storage layout

* Canonical 1m bars: `data/bars/source=<s>/symbol=<sym>/year=<y>/part-0.parquet` (zstd). Columns
  `ts` (UTC, **bar open time**), `open, high, low, close, volume` (float64); `source`, `symbol` and `year` are
  Hive partition keys. Optional extra column `spread` (Dukascopy only).
* Funding: `data/funding/source=<s>/symbol=<sym>/year=<y>/part-0.parquet` — `ts, rate (per period),
  period_hours`.
* Resampled bars: `data/resampled/tf=<5m|15m|1h|4h|1d>/source=…` (UTC-anchored, open-time labels,
  `n_minutes` = number of 1m bars in the bin).
* DuckDB: `strategy_lab.data.storage.duckdb_connection()` exposes views `bars_1m`, `funding`, `bars_5m` …
  `bars_1d` over the Parquet files.

## 2. Source attempts in this environment

The sandbox's egress proxy blocks the primary hosts (see PROGRESS.md Phase 0). The code for every primary source
is implemented from its documented format, with its parsers unit-tested on documented sample rows, but it has
**never run against the live hosts** — on an unrestricted machine it is tried first, and any failure is recorded
and falls back to the next source, as here. Nothing was synthesised.

| dataset | source tried (in order) | result here |
|---|---|---|
| BTC 1m long history | Binance USD-M futures (data.binance.vision) | blocked (proxy 403) |
| | Binance spot (data.binance.vision) | blocked (proxy 403) |
| | **Binance spot — GitHub republication** | **used** |
| BTC 1m (Kaggle Bitstamp) | Kaggle API | skipped — no Kaggle token configured (the same Bitstamp dataset was taken from its GitHub home) |
| BTC 1m second exchange | **Bitstamp BTC/USD — GitHub** | **used** (independent cross-check) |
| BTCUSDT funding | Binance fundingRate files (data.binance.vision) | blocked |
| | **Binance API export — GitHub** (verified against 2 other exports) | **used** |
| BTC-PERP / XAU-PERP 1m + hourly funding | Lighter REST (mainnet.zklighter.elliot.ai) | blocked — **no Lighter data in this environment** |
| XAU 1m long history | Dukascopy via dukascopy-node (jetta.dukascopy.com) | blocked |
| | **HistData XAUUSD bid — GitHub re-uploads** | **used** |

**Which dataset a backtest uses** (`engines/inputs.py`). Each market lists its sources in preference order —
Lighter first (the target exchange), then the closest proxies (BTC: Binance futures, Binance spot, its GitHub
republication, Bitstamp; XAU: Dukascopy, HistData). A backtest uses the most preferred dataset that **covers
its whole window** (4 days of slack for weekends and holidays), so Lighter's short history — it starts at the
market's listing — is used for recent windows and never silently truncates a longer one; when no dataset
covers the window the run stops with each dataset's date range. Funding follows the same rule; when no series
covers the window, the one overlapping it most is charged where it exists and labelled `(partial: …)`. The
default window (UI, `make demo`) is the last three whole years of the most preferred source that has them,
ending where a covering funding series ends (`api/services.default_window`).

## 3. Per-source details

### 3.1 Binance public data (primary; implemented, blocked here)

* URL patterns (`strategy_lab/data/sources/binance.py`):
  `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip`,
  `…/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip` (from 2019-09),
  `…/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-YYYY-MM.zip`, each with a `.CHECKSUM`.
* Downloads run in parallel with retries; **every zip is verified against the SHA-256 in its `.CHECKSUM`**
  before parsing; a mismatch aborts.
* Timestamp unit detected **per file** from the magnitude of `open_time` (spot switched from ms to µs on
  2025-01-01, per the official README). Header rows are detected and skipped.
* Terms: Binance data — personal/research use; not for redistribution in a product.

### 3.2 Binance spot BTCUSDT — GitHub republication (used)

* Publisher: `parshant231234-eng/BTCUSDT-Historical-Data`, a weekly GitHub Action that copies Binance's public
  kline files. **Pinned commit `27c9be705ac9`.**
* URL pattern: `https://raw.githubusercontent.com/parshant231234-eng/BTCUSDT-Historical-Data/<commit>/1m/YYYY/MM/BTCUSDT_1m_YYYY-MM.csv`
  — header `timestamp (ms), datetime_utc, open, high, low, close, volume, quote_volume, trade_count, …`.
* Obtained: **110 monthly files (735 MB), 2017-08 → 2026-09; 4,789,279 1m bars, 2017-08-17 04:00 →
  2026-09-30 23:59 UTC.** Timestamp unit: ms in all 110 files (the republisher normalised Binance's µs files).
* Checksums: Binance's `.CHECKSUM` files live on the blocked host, so they **could not be verified**. SHA-256
  of each downloaded file is recorded in the manifest, and the data is validated against an independent
  exchange instead (§4: median |diff| vs Bitstamp 5.8 bps; the largest differences are two known real events).
* Known gaps: 33 gaps > 5 min, 8,557 missing minutes (99.82% complete) — Binance maintenance windows, e.g.
  2018-02-08 00:29 → 2018-02-09 09:59 (2,010 min). Zero-volume flat minutes are Binance's own convention and
  are kept.
* Licence: no licence file in the repository; Binance's terms apply (personal learning only).
* Why this is not "routing around the block": it is a third party's copy on GitHub (an allowed host), not an
  endpoint of the blocked service (the S3 origin behind data.binance.vision was deliberately **not** used).

### 3.3 Bitstamp BTC/USD 1m (used; second exchange)

* Publisher: `ff137/bitstamp-btcusd-minute-data` (source of the well-known Kaggle dataset). **Pinned commit
  `23a4a069c433`.**
* Files: `data/historical/btcusd_bitstamp_1min_2012-2025.csv.gz` (93.8 MB, 2012-01-01 → 2025-01-07) and
  `data/updates/btcusd_bitstamp_1min_latest.csv` (51.7 MB, daily updates), columns
  `timestamp (Unix s), open, high, low, close, volume (BTC)`.
* **The publisher fills missing minutes with flat zero-volume candles.** They carry no observed trade (and
  genuine no-trade minutes look identical), so **all 1,312,416 such rows were dropped** — outages become visible
  gaps instead of invented flat prices.
* Obtained: **6,444,863 1m bars, 2012-01-01 → 2026-09-30.** 83.1% of minutes have a trade (thin early years);
  36,276 gaps > 5 min.
* Licence: bulk file CC BY-SA 4.0 (Kaggle dataset by Zielak), updates CC BY 4.0; code MIT.

### 3.4 Binance USD-M BTCUSDT funding — GitHub exports (used)

* Primary: `VivekWar/Crypto-Funding-Rate-Arbitrage` (commit `dcbe60250451`),
  `notebooks/BTCUSDT_historical_funding.csv` — an export of Binance's `/fapi/v1/fundingRate` API:
  `symbol, fundingTime (UTC string), fundingRate (per 8 h), markPrice`.
* **Verification:** compared row by row with two independent exports —
  `huiiisiii/IS424-btc-prediction` (6,570 common timestamps, **0 mismatches**) and
  `kipopopo/autonomous-futures-bot` (Unix-ms timestamps, 3,831 common timestamps, **0 mismatches**; this also
  confirms the primary's times are UTC). The pipeline fails if any mismatch appears.
* Obtained: **7,457 rows, 2019-09-10 08:00 → 2026-06-30 16:00 UTC, every 8 h, no gaps.** Mean rate 0.0107%
  per 8 h, range −0.30% … +0.30%. **Backtests after 2026-06-30 have no funding data** (results say so).
* Licence: no licence files; Binance data terms apply.

### 3.5 Lighter (primary for the target exchange; implemented, blocked here)

* REST base `https://mainnet.zklighter.elliot.ai`; endpoints and field names from the official SDK source
  (`elliottech/lighter-python` v1.1.6): `GET /api/v1/orderBookDetails?filter=perp` (market_id, price/size
  decimals, min_base_amount, fees, created_at), `GET /api/v1/candles` (≤ 500 per call, `t` in ms; paged
  backwards from now to the market's `created_at`), `GET /api/v1/fundings` (resolution `1h`, ≤ 750 per call).
* Requests are spaced ≥ 1.05 s (60 requests/min tier) and back off on HTTP 429; every raw JSON page is cached
  under `data/raw/lighter/` so a re-run resumes.
* **Unverified assumptions** (could not call the API): request timestamps in ms (as CCXT does), funding `rate`
  is a fraction per hour and `direction` names the paying side. Check against Lighter's UI on first real run.
* XAU-PERP on Lighter is priced from an oracle of spot gold and has a short history (from listing).
* **Instrument specs:** with no metadata, the simulated venue uses documented defaults —
  BTC-PERP tick 0.1 USDC, lot 0.00001 BTC, min 0.0002 BTC; XAU-PERP tick 0.01 USDC, lot 0.001 oz
  (`strategy_lab/engines/nautilus/instruments.py`). Results record which spec was used.

### 3.6 Dukascopy XAUUSD (primary for gold; implemented, blocked here)

* `npx --yes dukascopy-node@1.50.0 -i xauusd -from YYYY-01-01 -to YYYY+1-01-01 -t m1 -p bid|ask -f csv -v -vu units`
  per year and side (resumable). Output: Unix-ms bar-open timestamps in UTC; flat zero-volume minutes are
  dropped by the tool. Since 1.49 the tool reads `jetta.dukascopy.com` (older versions `datafeed.dukascopy.com`
  `.bi5` files).
* Mid bars = (bid + ask)/2 per OHLC; `spread` = ask close − bid close kept as an extra column.
* Terms: Dukascopy data — personal use; not for a commercial product.

### 3.7 HistData XAUUSD 1m — GitHub re-uploads (used)

* Files: `Craig-Pang/QuantXAU` (commit `9042cef49ae7`) yearly files 2021–2025 and `Paaktingc/forex_bot`
  (commit `a4f516cf9555`) monthly files 2026-01 … 2026-05, both re-uploads of HistData.com `DAT_ASCII_XAUUSD_M1`
  (`YYYYMMDD HHMMSS;open;high;low;close;0`). 10 files, 123.5 MB.
* **Bid quotes only** — no ask, so no spread; **volume is always 0** (volume-based indicators are rejected for
  XAU by the validator).
* **Timezone (verified from the data, not assumed).** HistData documents "EST without daylight saving". The
  data disagrees: the daily gold break (17:00 New York) appears at 17:00 on the file's clock in both January and
  July, and shifts to 16:00 exactly in the weeks when the US is on daylight time but the EU is not (e.g.
  2024-03-11…27, 2024-10-28…31). So the clock is **UTC−5 moved to UTC−4 on EU daylight-saving dates**
  (= Europe/Berlin wall time − 6 h). The pipeline scores three hypotheses by the share of daily breaks that land
  on 17:00 New York (EST 0.29, America/New_York 0.62, **UTC−5+EU DST 0.67**) and uses the best.
* Obtained: **1,870,538 1m bars, 2021-01-03 23:00 → 2026-05-29 20:58 UTC (5.4 years).** 300 duplicate
  timestamps removed: one repeated hour (identical values) on each EU daylight-saving end date — an artefact in
  the published files.
* Gaps: closures are classified, not counted as errors — 281 weekends, 1,024 daily breaks, 58 holiday closures
  (US exchange holidays incl. early closes, Good Friday, Christmas/New Year). Remaining **595 data gaps
  (44,720 missing minutes; 97.64% complete)**, concentrated in 2023 (the 2023 file is visibly thinner).
* Licence: no licence in either repository; HistData.com data is free for personal use.

## 4. Cross-source checks

| pair | overlap | close corr | 1m return corr | median \|diff\| | p99 \|diff\| |
|---|---|---|---|---|---|
| Binance spot BTCUSDT (GitHub) vs Bitstamp BTCUSD | 4,656,159 minutes, 2017-08-17 → 2026-09-30 | 0.999999 | 0.697 | 5.8 bps | 241.7 bps |

* The median signed difference by year is −25 bps (2017), then within ±6 bps (2018–2026): the USDT/USD basis.
* The worst minutes are **real events**, which supports both datasets being genuine: the
  **2018-10-15 Tether de-peg** (BTCUSDT up to +13% over BTCUSD) and the **2019-05-17 Bitstamp-only flash crash**
  to $6,250. 1m return correlation is only 0.70 because Bitstamp is much less liquid (stale prints).
* **Not run here (data unavailable):** Binance USD-M futures vs Lighter BTC-PERP, and Dukascopy XAU vs Lighter
  XAU-PERP. Both are implemented (`pipeline.CROSS_CHECK_PAIRS`) and run whenever the datasets are present — the
  first one did on the user's machine (§6).

## 6. First run on an open network (the user's Windows machine, 2026-10-13)

The first time the primary sources ran against the live hosts. Figures are from that run's
`data/quality_report.md` (pasted by the user; the data itself is not in this repository).

| dataset | result |
|---|---|
| Binance USD-M futures BTCUSDT 1m (data.binance.vision) | **ok** — 81 monthly zips, all SHA-256-verified; 3,549,600 bars, 2020-01-01 → 2026-09-30, 100% complete, 0 gaps (2019-09 … 2019-12 are not published: 404) |
| Binance spot BTCUSDT 1m (data.binance.vision) | **ok** — 110 zips verified; 4,789,279 bars, 2017-08-17 → 2026-09-30: the same row count, range and 33 gaps as the GitHub republication used here |
| Binance BTCUSDT funding (data.binance.vision) | **ok** — 81 zips verified, 7,395 eight-hourly rows |
| Lighter BTC-PERP 1m + hourly funding (REST) | **ok** — 895,157 bars, 2025-01-17 08:43 → 2026-09-30, 100% complete, 0 gaps; 14,901 funding rows |
| Lighter XAU-PERP 1m + hourly funding (REST) | **ok** — 497,086 bars, 2025-10-20 19:14 → 2026-09-30, 100% complete (it trades 24/7 on a spot-gold oracle: the largest flagged moves are the Sunday 22:00 UTC reopen of spot gold); 8,277 funding rows |
| Dukascopy XAUUSD (dukascopy-node 1.50.0) | **failed** — the server answered HTTP 202 to every request, including a plain HEAD; cause unknown (no matching report found). HistData was used, as here |
| Bitstamp, HistData (GitHub) | **ok** — identical to this environment's |

| cross-check | overlap | close corr | 1m return corr | median \|diff\| | p99 \|diff\| | worst minutes |
|---|---|---|---|---|---|---|
| Binance futures vs **Lighter BTC-PERP** | 895,157 min, 2025-01-17 → 2026-09-30 | 0.999998 | 0.952 | 2.0 bps | 13.5 bps | 2025-10-10 21:16–21:22 UTC (the liquidation crash): up to 300 bps |
| Binance futures vs Binance spot | 3,547,275 min, 2020 → 2026 | 1.0 | 0.985 | 4.6 bps | 17.1 bps | 2020-03-13 (COVID crash): up to 526 bps |

**What a backtest uses there** (§2 rule): BTC windows inside Lighter's history run on **Lighter** bars and
funding; longer ones on **Binance USD-M futures** with Binance funding (default window 2023-09-01 → 2026-09-01).
Gold 3-year windows run on HistData; Lighter's XAU funding covers only their last months, so it is charged
there and labelled `(partial: …)`. Numbers in REPORT.md were measured on this environment's data (Binance spot
via GitHub, no Lighter) and will differ slightly from runs on that machine.

## 5. Validation rules (all datasets)

* Duplicate timestamps: dropped (first kept) and counted.
* Gaps > 5 min listed; for gold, gaps are classified as weekend / daily break / US-holiday closures.
* OHLC sanity (high ≥ max(open, close), low ≤ min(open, close), high ≥ low, prices > 0, volume ≥ 0, no NaN):
  **0 violations in every dataset**.
* Outlier spikes: |1m log return| > 10 σ of the trailing day's 1m returns are **flagged, never deleted**
  (Binance 2,053; Bitstamp 2,172; XAU 591 — mostly news minutes such as CPI/FOMC releases at 12:30/13:30/18:00
  UTC, visible in the report's top-15 tables).
* Resampling 1m → 5m/15m/1h/4h/1d: UTC-anchored bins `[t, t+tf)`, open=first, high=max, low=min, close=last,
  volume=sum; empty bins produce no bar (tested against a hand-made example in `tests/test_resample.py`).
