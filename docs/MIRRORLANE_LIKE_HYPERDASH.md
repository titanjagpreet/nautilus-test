# Mirrorlane, built like Hyperdash, on Lighter

Product and build plan, 21 October 2026. Every Hyperdash feature below comes from Hyperdash's own docs,
read on 21 Oct 2026 ([index](https://docs.hyperdash.com/llms.txt)). Every Lighter capability is marked:

- **Live**: I called Lighter's public mainnet API from this environment on 21 Oct 2026 with no credentials.
- **Docs**: stated in Lighter's API docs ([index](https://apidocs.lighter.xyz/llms.txt)), not tested.
- **Inference**: my reading of what follows from the two above. Verify before relying on it.

The business case and the evidence behind the pricing are in
[reports/Copy trading models for Mirrorlane.md](../reports/Copy%20trading%20models%20for%20Mirrorlane.md).
This document is the "what to build" that follows from it.

---

## 1. What "like Hyperdash" means

Hyperdash is not a copy-trading app. It is a **trading terminal with free, deep on-chain analytics**, and copy
trading is one feature inside it. That structure is why it is the only Hyperliquid copy product with real
revenue: about **$409K in the 30 days to 21 Oct 2026** (DefiLlama), against a few hundred to about $23K a month
for standalone copy apps. Its model has five parts:

| Part | Hyperdash | What it does for the business |
|---|---|---|
| Free analytics on every wallet | Explore, Leaderboard, trader profiles, Cohorts, Top Traders, Position Changes, liquidation heatmaps, Telegram "Flows" | The funnel: people come to look, then stay to trade |
| Terminal | Every order type (13, incl. TWAP, Chase, Iceberg, Swarm), custom layouts and widgets | The revenue base: 1.5 bps per perp fill, 3 bps spot |
| Copy trading | Mirror or counter up to 10 public wallets, from a dedicated wallet | The premium product: 5 bps per copied fill, no rebates |
| Easy onboarding | Google/Apple/email → embedded wallet (Turnkey), cards and bank transfer in 34 currencies | More users, fewer drop-offs |
| Give-back ladders | Cashback 5–25% by own volume; referrals 20–35% of referees' fees | Retention and distribution |

**Leaders are paid nothing.** Copied wallets are public and never opted in; Hyperdash keeps the whole fee.

Mirrorlane on Lighter can copy all five parts. Two things change because of Lighter, and one thing Mirrorlane can
do better:

1. **Fees need a paid tier.** Lighter's integrator fee (its builder-code equivalent) is only charged to users on
   Plus or Premium. Standard users trade at zero fees and pay Mirrorlane nothing per trade (§4).
2. **The analytics must come from an indexer, not a node.** Hyperdash reads Hyperliquid node data. Lighter has
   no public node, but its public trade feed carries enough to rebuild every account's positions (§3).
3. **Mirrorlane can prove copy results.** No copy product publishes what copiers actually earn. Mirrorlane's
   backtest lab can replay any leader's fills through the exact copy rules and fees (§6).

---

## 2. Feature map: Hyperdash → Mirrorlane on Lighter

Status: ✅ possible as-is · 🟡 possible with a workaround or an estimate · ❌ not possible from public data.

### 2.1 Analytics (the funnel)

| Hyperdash feature | Mirrorlane on Lighter | Data source | Status |
|---|---|---|---|
| **Leaderboard**: net realized PnL; 24H/7D/30D/YTD/All; market tabs; account value, volume, win rate, trades, top assets; style filter | Global ranking straight from Lighter; per-market tabs, win rate and style from the indexer | `pnlLeaderboard` (Live: 99,161 ranked addresses in the 30d window; windows 24h/7d/30d/all; sort by pnl, roi, volume, account value) + indexer | ✅ |
| **Trader profile**: equity/PnL chart, PnL calendar, positions, fills, trades, transfers, best trades, per-asset performance | Same | `account` (Live: positions with entry, liquidation price, funding paid, order counts), `pnl` (Docs + earlier live test: daily/hourly PnL with inflows and outflows), indexer for trade history | ✅ |
| **Performance stats**: drawdown, win rate, Sharpe; style tag (Scalp < 15 min, Intraday 15 min–6 h, Swing 6 h–2 wk, Position > 2 wk, Algo) | Same thresholds, computed from holding times | Indexer + `pnl` | ✅ |
| **Explore / Global filters**: period, account value, PnL, style, copy score | Same | Indexer | ✅ |
| **Tracking**: aliases, lists, shareable lists, live "Tracked" feed of fills and deposits/withdrawals | Fills live; deposits and withdrawals from balance changes and `pnl` inflows/outflows (hourly) | WS `account_all_trades/{id}` and `account_all/{id}` (Docs + earlier live test: no auth; 500 accounts per connection, 5,000 per IP), `pnl` | ✅ fills · 🟡 transfers |
| **Cohorts**: per market, long vs short notional, # traders long vs short, # in profit vs loss; PnL cohorts and size cohorts; cohort detail pages | Same | Indexer positions + `account` snapshots for account value | ✅ |
| **Top Traders**: largest positions with entry, liquidation price, notional, uPnL, funding paid, account value, copy score | Same | Indexer + `account` (Live: `liquidation_price`, `total_funding_paid_out` are public) | ✅ |
| **Position Changes**: 15m, 1h, 4h, 24h, 3d, 7d | Same | Indexer position history | ✅ |
| **Live trade and liquidation feeds** | Same | WS `trade/{market}` (Docs: trade `type` is `trade`, `liquidation`, `deleverage` or `market-settlement`) | ✅ |
| **Liquidation heatmap** (live, depth, historical) | Live/depth from snapshotted positions' liquidation prices; historical from liquidation trades | `account` snapshots + liquidation trades | 🟡 exact for snapshotted accounts, estimated for the rest |
| **Stop-loss heatmap** | Not possible: stop and take-profit orders sit outside the book; the public account snapshot shows only how many there are (`position_tied_order_count`, `pending_order_count`) | Live: counts only | ❌ |
| **Current TWAPs** (other traders' running TWAPs) | Not possible: parent TWAP orders are private and public trades don't say which order type produced them | — | ❌ (a "probable TWAP" detector from regular fills is possible later) |
| **Resting orders of known wallets** (Hyperdash has no such view) | New: who owns the walls in the book | `orderBookOrders` (Live: every resting order carries `owner_account_index`; up to 250 a side per call) | ✅ extra |
| **Telegram Flows**: liquidations ≥ $50K, OI surge, volume surge, funding surge, daily summary | Same rules | Trade feed, WS `market_stats`, `fundings`, `exchangeMetrics`, hourly OI files | ✅ (except "TWAP started": ❌) |
| **Alerts and inbox** | Same | Mirrorlane's own backend | ✅ |
| **Direct Sentry Peering** (institutions peer their node) | No equivalent: Lighter has no public node | — | ❌ (not needed) |

### 2.2 Copy trading

Hyperdash's settings, from its [Copy Trading docs](https://docs.hyperdash.com/copy-trade), all map onto Lighter:

| Hyperdash setting | Default there | Mirrorlane on Lighter | Status |
|---|---|---|---|
| Mode: Copytrade (mirror) or Countertrade (opposite side) | Copytrade | Same. Countertrade is the same engine with the sign flipped | ✅ |
| Up to 10 target traders per wallet, equal or custom weights | Equal | Same | ✅ |
| Max position leverage, 1x–40x | 20x | Same, capped further by each market's max | ✅ |
| Only copy newly opened positions | Off | **Default On** in Mirrorlane: buying into a stale position at a worse price is a known copier loss | ✅ |
| Max worse entry, 0–50% vs the trader's entry | 10% | Same, enforced as an IOC limit price | ✅ |
| Asset whitelist / blacklist | All | Same; thin markets excluded by default | ✅ |
| Stop closes all positions; Archive returns funds; Delete | — | Same | ✅ |
| Per-wallet logs including skipped trades with reasons | — | Same (every decision stored) | ✅ |
| "Removing a trader closes its positions on the next sync" | — | Same: a reconciler compares target and actual positions | ✅ |
| Projection of a trader's 30-day PnL onto a $1,000 allocation | — | Better: a replay through Mirrorlane's real copy rules, delays and fees (§6) | ✅ extra |
| Warning when copying an algorithmic trader | — | Same, plus an expected monthly fee-drag figure | ✅ extra |
| Shareable PnL card | — | Same | ✅ |
| Discovery: Top 100 copyable, sort by copy score, ROI, equity, recent activity; paste any address | — | Same; Lighter accounts are identified by account index or L1 address | ✅ |

How a leader's moves are seen (Docs + earlier live test): every public fill includes both account IDs, each
side's position size and entry before the fill, and a flag when the position flips. That is enough to classify
open, add, reduce, close and flip with no extra reads. Leaders' resting limit orders are visible through
`orderBookOrders` snapshots, but mirroring should stay fill-driven like Hyperdash's.

### 2.3 Terminal

| Hyperdash | Mirrorlane on Lighter | Status |
|---|---|---|
| Market, Limit, TP/SL, Conditional (stop) | Native on Lighter (Docs: order types `limit`, `market`, `stop-loss`, `stop-loss-limit`, `take-profit`, `take-profit-limit`, `twap`) | ✅ |
| TWAP | Native on Lighter (charges 1 bp on Standard accounts) | ✅ |
| Scale (ladder of limits) | Client builds the ladder and sends it with `sendTxBatch` | ✅ |
| Chase, Chase TWAP, VWAP, POV, Swarm, Iceberg, Trailing Stop, "stealth" triggers | Mirrorlane's execution service works the order with the user's API key, the same server-side setup as copy trading | 🟡 after the copy signer exists |
| Quick Trade, shortcuts | Frontend | ✅ |
| Layouts, widgets, six link groups, shareable layouts | Frontend | ✅ |
| Perps, spot, RWA perps, prediction markets | Lighter has perps, spot, RWA markets (gold is already in this lab's data) and Up/Down binary options with their own partner attribution (Docs) | ✅ |
| Perp RFQ (block trades, private beta) | Lighter accounts carry `can_rfq` flags (Live), but RFQ was not researched | ❓ |

### 2.4 Accounts, custody and onboarding

| Hyperdash | Mirrorlane on Lighter | Status |
|---|---|---|
| Google/Apple/email sign-in creating a non-custodial Turnkey wallet; multiple wallets | Same pattern; the vendor (Turnkey, Privy or others) was not compared | 🟡 vendor choice open |
| Connect any EVM wallet; "import" an existing account by approving an agent key and the builder fee | Lighter: create an account and register an app API key with one wallet signature (Docs); `ApproveIntegrator` sets the fee cap and expiry (Docs) | ✅ |
| Agent key cannot withdraw | **Different on Lighter**: an API key can trade, move funds between the same owner's accounts and request withdrawals back to the owner's own wallet; there is no trade-only scope (Docs) | 🟡 the signer must allowlist order transactions only |
| 2FA (passkey or TOTP) before withdrawals | Same | ✅ |
| Deposits from 11 chains and 7 exchanges; cards, bank transfer, Revolut, PIX, UPI and others in 34 currencies | Lighter deposits via its bridge and intent addresses (Docs: `deposit_networks`, `createIntentAddress`); fiat on-ramp vendor not researched | 🟡 vendor choice open |

---

## 3. The data platform: Mirrorlane's version of Hyperdash's node

Most of §2.1 depends on one component: an **indexer** that knows every Lighter account's position in every market
at every moment. This is the biggest piece of engineering and the main moat, as it is for Hyperdash.

**Why it is possible (Live, 21 Oct 2026).** A public trade from `recentTrades` / `trade/{market}` carries:
`ask_account_id`, `bid_account_id`, `is_maker_ask`, `type`, `size`, `price`, `usd_amount`, and for both taker and
maker the position size before the fill, the entry quote before the fill and the initial margin fraction
(leverage setting) before the fill, plus `taker_position_sign_changed`. Applying fills in order rebuilds every
position, and the "before" fields let the indexer check itself on every trade.

| Input | What it gives | Cost and limits |
|---|---|---|
| WS `trade/{market}` for every market (`?readonly=true` works from restricted regions) | Every fill, live, with both accounts | Free |
| Daily Parquet of all trades since mainnet genesis (17 Jan 2025) | Full backfill of every account's history | One-time in-app transfer of 100 LIT (≈ $339 at $3.39 on 21 Oct 2026), or AWS "requester pays" S3 (Docs) |
| Hourly open interest per market, Parquet | OI history for charts and Flows | AWS requester pays (Docs) |
| `account` snapshot | Collateral, account value, liquidation prices, order counts, sub-accounts | Weight 300 |
| `pnl` | Equity curve with inflows and outflows, so ROI is deposit-adjusted | Weight 300 |
| `pnlLeaderboard` | Lighter's own ranking, for seeding and cross-checks (by L1 address, so sub-accounts combined) | Weight 300 |
| `orderBookOrders` | Resting orders with owners | Weight 300; ≤ 250 a side (1,000 is rejected, Live) |
| WS `market_stats`, `fundings`, `exchangeMetrics` | Prices, funding, OI, volume | Weight 120–300 |

**Rate budget.** Standard REST is 60 requests a minute. A free Lighter **Builder account** (applied for through
Lighter's Discord) allows 240,000 weighted units a minute (Docs), about 800 `account` or `pnl` calls a minute:
enough to refresh the 10,000 largest accounts every 25 minutes and the top 1,000 every few minutes. Apply for
it first.

**How it fits together** (same Docker Compose on EC2 as the copy service):

```
trade/{market} WS ─┐                                  ┌─> Postgres: live positions, accounts, lists, alerts
daily trade files ─┼─> indexer (applies fills, checks ├─> Parquet + DuckDB: history, stats, cohorts
account/pnl polls ─┘    "before" fields, resyncs)     └─> Redis Streams: live feeds, copy signals
```

The strategy lab already has the pieces to reuse: the Lighter REST/WS client and atomic Parquet writes
(`strategy_lab/data/sources/lighter.py`, `strategy_lab/data/storage.py`), UTC-safe DuckDB, and the Lightweight
Charts UI.

**Acceptance test for the indexer.** For a random sample of accounts each hour, rebuilt positions must equal the
`account` snapshot; for the top 100 addresses, 30-day PnL must match `pnlLeaderboard` within a stated tolerance.
Any mismatch triggers a resync of that account and is logged.

---

## 4. How Mirrorlane earns money (the Hyperdash model, adapted)

| Revenue line | Hyperdash on Hyperliquid | Mirrorlane on Lighter (proposal) |
|---|---|---|
| Copy trading | 5 bps per copied fill; no rebates on copy volume | **5 bps per copied fill**, no rebates on copy volume |
| Manual perp trades | 1.5 bps | **1 bp** for users on Plus or Premium; **0 on Standard** (Lighter won't let integrators charge Standard users) |
| Spot | 3 bps | 3 bps on Plus/Premium (Lighter allows up to 100 bps on spot) |
| Prediction markets / binary options | 3 bps | To check: Lighter documents partner attribution for binary options |
| Subscription | None | Optional "Pro" for heavy analytics (more tracked wallets, alerts, API). Test later; Hyperdash proves free analytics work as a funnel |
| Cashback | 5–25% of own fees by 30-day volume | Start without; add once fee revenue exists |
| Referrals | 20–35% of referees' fees; referees get 10% off | **20%** of referees' fees, referees 10% off; widen later |
| Leader payouts | None | **None at launch.** Later: opt-in verified leaders paid from copy fees, only while their copiers are in profit |

**The Standard-tier problem, solved the Hyperdash way.** Lighter applies the account tier to the whole L1
address, sub-accounts included (Docs). So copy trading should run from a **new wallet** (Hyperdash's "Create
New"): Mirrorlane creates a fresh embedded wallet, opens its Lighter account on Plus, registers Mirrorlane's key
and integrator approval, and the user funds it from their main account. The user's main wallet stays on Standard
at zero fees. A user can instead connect an existing Plus/Premium wallet (Hyperdash's "Use Existing").
*Inference: a separate L1 address has its own tier. Confirm with the house-money gate before launch.*

What a copier pays per taker fill:

| Route | Venue fee | App fee | Per fill | Round trip |
|---|---|---|---|---|
| Mirrorlane copy on Lighter Plus | 0.5 bps | 5 bps | **5.5 bps** | 11 bps |
| Hyperdash copy on Hyperliquid | 4.5 bps | 5 bps | 9.5 bps | 19 bps |

So Mirrorlane earns the **same 5 bps as Hyperdash** while its copiers pay **about 40% less**. That is the pitch.

**Size of the prize.** Each $1M of copied volume earns $500. In the week to 21 Oct 2026, all 60 integrators on
Lighter together earned $142K on $478.5M of volume (Litscan): about $600K a month, or roughly 1.5 times
Hyperdash's revenue on its own. Matching Hyperdash would mean taking about two-thirds of every integrator fee
paid on Lighter today. Copy fees must stack with terminal fees, and Lighter's growth sets the ceiling.

---

## 5. Copy engine and safety (already designed)

The shared-services design from the earlier discussion stands. Its parts are listed in the research report's
final table: one watcher subscription per leader, Redis Streams, one writer per API key, target-position copying
with a reconciler, a signer that is also the policy engine, per-follower risk guards and a global kill switch,
Postgres, and Docker Compose on one EC2 host with nginx.

Four Lighter-specific rules matter most:

1. **The signer signs only orders.** It signs only order create, cancel, modify and leverage changes, and refuses
   withdrawals, transfers and key changes, because a Lighter key can do all of those.
2. **Host outside Lighter's restricted list.** From a US IP, Lighter refuses the trading WebSocket (live test).
3. **Exits follow the leader.** Close only when the leader is net flat, and mirror partial exits proportionally.
   Developer evidence says exits, not entry lag, decide copier results.
4. **Plan for Lighter going dark.** The kill switch must treat "venue unreachable" as a trigger. Lighter was down
   about 4.5 hours in the 10–11 Oct 2025 crash.

---

## 6. Where Mirrorlane beats Hyperdash

| Mirrorlane feature | Why Hyperdash can't match it today | Built from |
|---|---|---|
| **Copier-realised returns** next to each leader's own return | No copy product publishes what copiers actually earned | This repo's engines: the replay applies 300 ms delay, IOC slippage cap, minimum sizes and 5.5 bps fees |
| **Deposit-adjusted ROI** | Leaders can inflate ROI by timing deposits | Lighter's `pnl` reports inflows and outflows |
| **Expected fee drag** per leader (e.g. "copying this trader costs ~9% of equity a month") | Hyperdash shows a warning but no figure | Indexer turnover × fee |
| **"Trades against followers" flag** | — | Every public fill names both accounts, so a leader (or a sibling sub-account) taking the other side of copier flow is detectable |
| **Who owns the walls** in the order book | Hyperliquid's book is anonymous in Hyperdash's UI | `orderBookOrders` owners |
| **AI strategy builder + backtest lab** | Not offered | This repo; already working |

Keep the AI builder out of the copy launch, and never list house strategies as copyable leaders. Either would
make Mirrorlane the discretionary manager (see the report's regulation section).

---

## 7. Build order

Each phase ships something users can see. The first two hold no user keys and place no orders.

| Phase | Ships | Done when |
|---|---|---|
| **A. See everything** | Indexer; Leaderboard (global + per market); trader profiles; Explore with filters; tracking lists and the Tracked feed | Indexer acceptance test in §3 passes for 7 days straight |
| **B. Market intelligence** | Cohorts; Top Traders; Position Changes; liquidation feed and heatmap; book-owner view; Telegram Flows channel | Cohort totals reconcile to market open interest within tolerance |
| **C. Copy** | Copy engine in three gates (from the report): shadow mode on 25–50 leaders, then 3–5 house wallets with real money, then a closed beta | Pass marks fixed in advance: copier's captured share of leader edge net of fees; zero signer-policy violations; reconciliation drift bounded and self-healing |
| **D. Trade** | Terminal orders with integrator fees; embedded wallets and deposits; referrals | First paid fills recorded through `partnerStats` |
| **E. Pro tools** | Algo orders (Chase, VWAP, Iceberg, …); layouts and widgets; alerts inbox; mobile | — |
| **F. Leaders** | Opt-in verified leaders paid from fees | Only after C shows copiers can make money |

Phase A is not a detour from the live copy test. The copy engine needs leader discovery and the watcher, and
Phase A builds both.

---

## 8. Open questions and risks

1. **Legal.** EU and UK regulators treat automatic copying as portfolio management, and the US treats it as
   directing accounts. Geo-block the US, Canada, UK, EEA retail and Lighter's other excluded countries from day
   one, and take advice from counsel before a public copy launch. Hyperdash's own legal setup was not researched.
2. **Lighter could close the data.** Public per-account data and order owners could be gated later. Nothing in
   the docs says so, but the REST `trades` endpoint already answers in a way that conflicts with its docs.
3. **Builder account.** Lighter must approve the Builder account application. Without it, the indexer is limited
   to 60 requests a minute.
4. **Plus tier.** Does switching a new wallet to Plus have any minimum or cost? Does the integrator receive its
   whole fee? Neither is stated in the docs.
5. **Vendors.** The embedded-wallet vendor and the fiat on-ramp vendor have not been compared.
6. **Data cost.** 100 LIT for the history files (≈ $339 at the 21 Oct 2026 price), or S3 transfer costs.
7. **Scale.** Lighter's open interest is about a tenth of Hyperliquid's (≈ $0.79B vs $7.75B on 21 Oct 2026). The
   same product earns less on Lighter until Lighter grows.

## Sources

**Hyperdash docs** (read 21 Oct 2026):
[About](https://docs.hyperdash.com/about-hyperdash.md) ·
[Copy Trading](https://docs.hyperdash.com/copy-trade.md) ·
[Trader Explore](https://docs.hyperdash.com/wallet-explore.md) ·
[Leaderboard](https://docs.hyperdash.com/leaderboard.md) ·
[Cohorts, Top Traders, Position Changes](https://docs.hyperdash.com/cohorts-top-traders-position-changes.md) ·
[Trading Indicators](https://docs.hyperdash.com/trading-indicators.md) ·
[Portfolio and Analytics](https://docs.hyperdash.com/portfolio-analytics.md) ·
[Alerts](https://docs.hyperdash.com/alerts-inbox.md) ·
[Telegram Flows](https://docs.hyperdash.com/telegram-flows.md) ·
[Fees, Referrals & Rewards](https://docs.hyperdash.com/fees-referrals-rewards.md) ·
[Onboarding](https://docs.hyperdash.com/onboarding-deposits.md) ·
[Layouts](https://docs.hyperdash.com/layouts.md) ·
[Widgets](https://docs.hyperdash.com/widgets.md) ·
[Order Types](https://docs.hyperdash.com/orders/overview.md)

**Lighter API docs:**
[Historical Data](https://apidocs.lighter.xyz/docs/historical-data) ·
[WebSocket reference](https://apidocs.lighter.xyz/docs/websocket-reference) ·
[Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits) ·
[API keys](https://apidocs.lighter.xyz/docs/api-keys) ·
[Account Types](https://apidocs.lighter.xyz/docs/account-types) ·
[Partner Attribution](https://apidocs.lighter.xyz/docs/partner-integration) ·
[orderBookOrders](https://apidocs.lighter.xyz/reference/orderbookorders) ·
[pnlLeaderboard](https://apidocs.lighter.xyz/reference/pnlleaderboard)

**Live queries**, all against `https://mainnet.zklighter.elliot.ai/api/v1/`, 21 Oct 2026, no credentials:
- `orderBookOrders?market_id=1&limit=250`: 250 asks and 250 bids, 119 distinct owners.
- `pnlLeaderboard?time_window=30d&sort_by=pnl&sort_dir=desc&limit=3&offset=0`: total 99,161.
- `recentTrades?market_id=1&limit=2`: field list quoted in §3.
- `account?by=l1_address&value=<30d leader>`: positions with `liquidation_price`, `total_funding_paid_out` and
  order counts.

**Revenue and market figures:** DefiLlama, Litscan and Lighter docs, as cited in the research report.
