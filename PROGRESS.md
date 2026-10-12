# PROGRESS

Running log of what is done, measured numbers, problems and decisions. Updated at the end of every phase.

## Definition of done

- [x] Network check done; sources and fallbacks recorded.
- [x] BTC and XAU history downloaded, checksummed where possible, validated, resampled, documented in DATA.md.
- [ ] The hand-written Nautilus strategy runs with fees, slippage and funding visible; speed and memory measured.
- [ ] Spec schema, validator (look-ahead and higher-timeframe guards), plain-language renderer, 10 catalogue strategies.
- [ ] SpecStrategy runs any valid spec in Nautilus.
- [ ] The fast engine matches Nautilus on all 10 catalogue strategies within the stated tolerance, or every difference is documented.
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
