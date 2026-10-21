# Lighter (zkLighter / lighter.xyz): Copy Trading, Public Pools, and the Builder Platform for Third-Party Terminals

Research date: 2026-10-21. Every number is dated. "Live query" means I called Lighter's public mainnet API (`https://mainnet.zklighter.elliot.ai`) or WebSocket (`wss://mainnet.zklighter.elliot.ai/stream?readonly=true`) from this environment on 2026-10-21 (about 14:00 to 14:30 UTC). Lighter doc pages were downloaded as Markdown (append `.md` to the URL). Each page has an `updatedAt` stamp, mostly between 2026-09-29 and 2026-10-21 unless noted. Items marked "(search excerpt)" come from search-engine summaries of pages I could not fetch. Treat them as lower confidence.

Environment note: WebFetch could not resolve several hosts (litscan.io, castlelabs.io, onchaintimes.com, lighterfluid.*). curl through the proxy worked for most of them. A normal WebSocket connection from this environment's US egress IP was refused with `{"code":20558,"message":"You are accessing Lighter from a restricted jurisdiction..."}`. The documented `?readonly=true` variant worked. Every WebSocket test below used read-only mode.

---

## 1. How do Lighter public pools work (creation, operator fee, minimum operator share, deposits and withdrawals, share valuation)? Which pools are large, and how have they performed? What is the LLP?

### Takeaway
Public pools are Lighter's native "follow a trader" product. A pool is a special sub-account of the operator. Depositors mint USDC-denominated shares, the operator trades the pool, and the operator takes a profit-share fee when a depositor withdraws. There is no lockup, only a 5-minute cooldown. As of 2026-10-21, the market is dominated by the protocol's own LLP at about $95.3M. All 341 user-run pools together hold only about $4.26M, and only 8 of them exceed $100k.

### Cited Findings
**Mechanics (operators)**
- A public pool lets participants "combine funds under a designated operator who trades on their behalf". Profits are distributed to participants after the operator's fee is deducted. Trading happens through a sub-account in the operator's account. Public pools do not support isolated positions. — [Lighter Docs: Public Pools](https://docs.lighter.xyz/trading/public-pools)
- Who can create a pool: the user docs say operators are "currently, whitelisted by the protocol" — [Public Pools](https://docs.lighter.xyz/trading/public-pools). The API docs (updatedAt 2026-09-29) say creation is "gated to having traded $10M or more in paid volume (checked hourly)", with up to 6 public pools per L1 address — [Manage Public Pools](https://apidocs.lighter.xyz/docs/manage-public-pools-shares). The two docs conflict. The API doc is more specific and more recently maintained.
- Operator fee is defined as "the percentage of profits allocated to the operator upon participant withdrawals". The minimum operator share is the minimum ownership the operator must keep. Example: with a 10% minimum, an operator who deposits 10,000 USDC caps outside deposits at 90,000 USDC. — [Public Pools](https://docs.lighter.xyz/trading/public-pools)
- In the SDK, a pool is created with `create_public_pool(operator_fee, initial_total_shares, min_operator_share_rate)`. The example uses `operator_fee=100000` (10%), `initial_total_shares=1_000_000` (described as "1000 USDC") and `min_operator_share_rate=100` (1%). `update_public_pool` can set status (0 = active, 1 = frozen), operator fee and minimum share. The example notes "operator_fee can only decrease". — [lighter-python public_pool_create_modify.py](https://github.com/elliottech/lighter-python/blob/main/examples/public-pool/public_pool_create_modify.py)
- Transaction types: `L2CreatePublicPool` (10), `L2UpdatePublicPool` (11), `L2MintShares` (18, deposit), `L2BurnShares` (19, withdraw). Rate limits are 2 `L2CreatePublicPool` per minute and 1 `L2MintShares` per 15 seconds. — [Manage Public Pools](https://apidocs.lighter.xyz/docs/manage-public-pools-shares); [Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits)
- Error codes show further rules: "withdrawal from public pool is not allowed" (21127, so the operator cannot withdraw directly from the pool account); "public pool is frozen, only burning is allowed" (21203); "only master account can update public pool" (21215); "too many invested public pools" (21206, so there is a per-depositor cap); "pools are not allowed to trade in spot markets" (21744); "public pools are not allowed to trade in isolated only markets" (21747); pools cannot trade binary options (21752); "liquidity pool cooldown period has not passed yet" (21234). — [Data Structures, Constants and Errors](https://apidocs.lighter.xyz/docs/data-structures-constants-and-errors)

**Mechanics (depositors and valuation)**
- Depositors get pool shares, which they redeem on withdrawal. "Public Pools do not impose lockup periods, and funds can be withdrawn at any time." — [Public Pools](https://docs.lighter.xyz/trading/public-pools)
- Share price = `total_asset_value / total_shares`, read from `publicPoolsMetadata`. A depositor's `entry_usdc` field records the USDC they paid for their shares (their cost basis). — [Manage Public Pools](https://apidocs.lighter.xyz/docs/manage-public-pools-shares)
- Live `systemConfig` (2026-10-21) returns `liquidity_pool_cooldown_period: 300000` (5 minutes) and `staking_pool_lockup_period: 259200000` (3 days). — [live systemConfig](https://mainnet.zklighter.elliot.ai/api/v1/systemConfig). TradingStrategy.ai describes "a 5-minute withdrawal cooldown period" for Lighter pools and says operators set performance fees "0-100%", deducted from PnL. — [TradingStrategy.ai Lighter vaults](https://tradingstrategy.ai/vaults/protocols/lighter)
- Pool data is fully public over WebSocket without auth (live test, 2026-10-21). `pool_info/{pool}` returns `operator_fee`, `min_operator_share_rate`, `total_shares`, `operator_shares`, APY, Sharpe, `daily_returns[]`, `share_prices[]` and `strategies[]`. `pool_data/{pool}` streams the pool's trades, open orders, positions, shares and funding. — [WebSocket reference](https://apidocs.lighter.xyz/docs/websocket-reference); live test
- REST `transfer/history` is public for pools ("unless it's a public pool"). A live query on pool 281474976688087 returned `L2MintSharesInflow` and `L2BurnSharesOutflow` events with depositor L1 addresses. — [transfer_history reference](https://apidocs.lighter.xyz/reference/transfer_history); live query

**Size and performance snapshot (live `publicPoolsMetadata`, paginated, 2026-10-21)**
- There are 343 pools: 2 protocol pools (LLP and XLP) and 341 user pools, of which 191 are active (status 0). Total TVL across all pools is about $99.6M. LLP holds $95.30M of that, and the 341 user pools hold $4.26M combined. Only 8 user pools have more than $100k, 13 have more than $10k, and 314 have less than $1k. — [live publicPoolsMetadata](https://mainnet.zklighter.elliot.ai/api/v1/publicPoolsMetadata?index=281474976710655&limit=100&filter=all)
- Operator fee distribution across user pools: 198 pools at 0%, 28 at 10%, 50 at 20%, 15 at 25%, 30 at 30%, and a few between 1% and 17%. Among the larger fee-charging pools, the norm is 10–30%. — same live query
- Largest user pools (TVL / fee / API APY / min operator share / actual operator ownership, 2026-10-21):
  - "Edge & Hedge (L/S Factors)": $1.71M, 20% fee, APY 20.7%, Sharpe 1.0, min share 5%, operator owns 6.0%. Created 2025-09-18. TradingStrategy lists its peak TVL as $5.93M.
  - "NYP- Not YOUR pool": $0.81M, 10% fee, min share 17%, operator owns 19.9%. Peak $1.89M.
  - "[Systemic Strategies] Peter Schiff's vault": $0.47M, 10% fee, APY −268%.
  - "BTC vs ALTS and NEWS/DIPS": $0.41M, 20% fee, operator owns 99.3%.
  - "Insertive Capital (@onchainquant)": $0.15M, 25% fee, APY −97%.
  - "Candle Effect v2": $0.12M, 30% fee, Sharpe 7.3.

  — [live publicPoolsMetadata](https://mainnet.zklighter.elliot.ai/api/v1/publicPoolsMetadata?index=281474976710655&limit=100&filter=all); live `pool_info` WebSocket; [TradingStrategy.ai](https://tradingstrategy.ai/vaults/protocols/lighter)
- TradingStrategy.ai lists $106.3M TVL in 25 Lighter vaults, with a TVL-weighted 30-day annualised APY of 31.1% (page fetched 2026-10-21). A search excerpt of the same page dated 19 Oct 2026 said $102.5M across 26 vaults at 34.0%. — [TradingStrategy.ai](https://tradingstrategy.ai/vaults/protocols/lighter)

**LLP (Lighter Liquidity Provider, the protocol's own pool)**
- LLP is account 281474976710654 (2^48−2), the protocol market-making and insurance-fund vault, with a 0% operator fee. — [Core concepts](https://apidocs.lighter.xyz/docs/core-concepts); live query
- LLP funds sit in a single account that is the counterparty to all LLP trading and liquidations. ADL events are "fully backstopped by LLP". Collateral is split into strategy buckets (crypto perps, FX, equities/RWAs), and each bucket's losses are isolated to its own collateral. — [LLP Strategies](https://docs.lighter.xyz/trading/liquidations-and-llp-insurance-fund/llp-strategies). Live `pool_info` shows 8 strategy buckets, the largest holding $63.8M of collateral.
- The liquidation engine takes up to a 1% liquidation fee on partial liquidations, paid to LLP. LLP takes over positions on full liquidation. — [Liquidations & LLP](https://docs.lighter.xyz/trading/liquidations-and-llp-insurance-fund)
- Access is gated. "The Lighter Liquidity Pool (LLP) is now exclusively accessible to LIT stakers. For every 1 LIT staked, participants may deposit up to 10 USDC." Unstaking LIT has a 3-day lockup. — [LIT Utility](https://docs.lighter.xyz/about-lighter/lit-utility)
- LLP TVL over time:
  - About $20M in May 2025, and "nearly $500m" on 13 Nov 2025, when LLP had 34% APY on 3-month and 2-week windows and a 122% cumulative return since inception. Its maker market share had fallen from 80% to about 7%. — [On Chain Times, 13 Nov 2025](https://www.onchaintimes.com/a-look-into-lighters-llp-recent-performance/)
  - Peak TVL of $700.30M. — [TradingStrategy.ai](https://tradingstrategy.ai/vaults/protocols/lighter)
  - $693.55M with APY 30.7% in an undated example response in Lighter's API docs. — [Manage Public Pools](https://apidocs.lighter.xyz/docs/manage-public-pools-shares)
  - **$95.30M on 2026-10-21**, with API APY 14.41% and Sharpe 3.81. — live query. A search excerpt of app.lighter.xyz/public-pools showed $95.65M and 14.80% APR. — [Lighter app Public Pools](https://app.lighter.xyz/public-pools)
- LLP share price from live `pool_info.share_prices` (2026-10-21):
  - 0.001 on 2025-01-16, 0.003340 on 2025-10-01, 0.003329 on 2026-01-01, 0.003609 on 2026-10-01 and 0.003634 on 2026-10-20.
  - That is +263% since inception, +8.0% from 2025-10-01 to 2026-10-01, and +9.2% from 2026-01-01 to 2026-10-20.
  - Worst days were −6.73% (2025-03-03), −6.26% (2025-02-26) and −5.35% (2025-10-11, the crash and outage day).

  — live WebSocket `pool_info/281474976710654`
- XLP ("Experimental Liquidity Provider") is a second protocol pool for volatile markets. It is capped at under $1M — [On Chain Times](https://www.onchaintimes.com/a-look-into-lighters-llp-recent-performance/) — and held $40.4K on 2026-10-21 (live query). A separate "Lighter Robinhood LLP" holds $2.21M in USDG on Robinhood Chain. — [TradingStrategy.ai](https://tradingstrategy.ai/vaults/protocols/lighter)

### Inferences
- Lighter's native pools cover the "invest in a trader" form of copy trading, but not "mirror a trader into my own account". User pools are small: $4.26M across 341 pools, against $95M in LLP. This suggests demand for depositing with third-party operators on Lighter is thin. It also suggests a market gap, or a warning, for a Mirrorlane-style product.
- The fee is charged "upon participant withdrawals". Whether there is a per-depositor high-water mark is not documented (see Gaps).
- The LLP TVL collapse from about $700M to $95M coincides with the LIT-staking gate (1 LIT per 10 USDC). This is an inference from timing and the documented gate. I found no source that states the cause.
- All pool data, including open orders, trades and depositor flows, is public. A third party can build pool analytics and leaderboards with no permissions.

### Gaps
- Exact profit-share accounting: high-water mark or not, whether it is computed on each depositor's own gain since entry, and whether it is crystallised at operator withdrawals. Not documented.
- The maximum number of pools one depositor can join (error 21206 exists, but no number is given).
- Whether pool creation still requires whitelisting or only the $10M paid-volume gate. The docs conflict.
- How the API's `annual_percentage_yield` is computed (window and method). Not documented.

---

## 2. Which third-party copy-trading apps, bots, terminals or Telegram bots exist on Lighter? How do they detect leader activity and execute, and what do they charge?

### Takeaway
At least one live product explicitly does wallet copy trading onto Lighter: Dextrabot, which copies Hyperliquid and Lighter wallets for a 0.055% fee per copied trade. LighterFluid marketed free copy trading of Lighter and Hyperliquid wallets, but appears inactive in October 2026. Most integrator volume on Lighter comes from AI agents and wallets (Minara AI, Telegram Wallet) and pro terminals, not from copy-trading apps. Over 7 days the integrator channel was about $478M in volume, which is a small share of exchange volume.

### Cited Findings
- **Lighter's own docs name copy trading as a supported pattern.** "B. Server-side on behalf of users" is described as end user owns the account, "your backend, with an API key the user approved" signs trades, typical product "Copy trading, managed strategies, agents". The user registers the key with a one-time L1 signature, and Lighter warns that "an API key can trade and can request secure withdrawals (which only go back to the user's own L1 address)". — [Choose your integration](https://apidocs.lighter.xyz/docs/choose-your-integration) (updatedAt 2026-10-16)
- **Dextrabot** (dextrabot.com, fetched 2026-10-21):
  - "Find and copy trade top wallets on Hyperliquid and Lighter". It "monitors Hyperliquid and Lighter wallet activity and automatically executes the same perpetual positions in your account based on your risk settings".
  - Fee: "0.055% on trade size for copy trade transactions", with a 4% discount through a referral code. Referrers earn "up to 65%" of the fees from users they refer.
  - Features: SL/TP, position size limits, margin controls, copying several wallets at once, and Telegram alerts.

  — [Dextrabot](https://dextrabot.com/). An earlier Dextrabot X post dated 2025-11-14 (date decoded from the post ID) said "We don't charge for Lighter Copy Trading … you can Copy Trade a Hyperliquid Wallet on Lighter". — [dextrabot on X](https://x.com/dextrabot/status/1989409860698657039). Pricing seems to have changed since then (the post is older; the site is current).
- Dextrabot's traction: DefiLlama shows about $3.7K in 30-day fees, and another tracker shows about $23K. The figures are inconsistent. (search excerpt) — [DefiLlama dextrabot](https://defillama.com/protocol/dextrabot); [AlphaGrowth](https://alphagrowth.io/dextrabot). Dextrabot is **not** among the 45 integrators on Litscan's integrator page (2026-10-21). This suggests it does not use Lighter's partner attribution, or uses it under another name. — [Litscan integrators](https://litscan.io/integrators)
- **LighterFluid**: a search excerpt describes it as a "trading terminal and copy trading platform" that "monitors elite traders on both Lighter and Hyperliquid" and mirrors their trades onto the user's Lighter account across 130+ markets, "within milliseconds", sized proportionally to equity, and "free to use". (search excerpt) — [LighterFluid](https://www.lighterfluid.xyz/). On 2026-10-21, `lighterfluid.xyz` redirected to www, which returned `404 "Application not found"`. Litscan lists LighterFluid as a "partner" with $0 volume and 0 accounts in the last 7 days. — [Litscan](https://litscan.io/integrators)
- **Integrator league table (Litscan, 7 days to 2026-10-21 14:00 UTC)**:
  - Totals: 60 integrators, $478.5M volume, $142.0K integrator fees, 3,960 attributed accounts, $35.0K in Lighter fees generated. Integrator share of venue volume ran about 2–5% per hour.
  - Minara AI (AI agent): $193.6M volume, 3,569 accounts, about 2.5 bps.
  - Telegram Wallet: $80.7M, 920 accounts, 9.0 bps taker.
  - TrueNorth: $75.3M, 38 accounts, about 1 bp.
  - Insilico Terminal: $60.7M, 14 accounts, 1.0 bp.
  - ArbWeb: $13.8M, 0 bps.
  - PerpPilot (bot): $9.5M, 93 accounts, 1.3 bps.
  - Bots and terminals with small volume: MyLiquidBot ($1.5M, 43 accounts), GUBOTS ($0.42M, 124 accounts, 6.5 bps), Botlyz (10 bps), CCXT (10 bps).
  - Listed with zero 7-day volume: Tealstreet.io, Metascalp and others.

  — [Litscan integrator analytics](https://litscan.io/integrators) (data embedded in the page HTML, parsed 2026-10-21)
- **Telegram Wallet** launched custodial perps "via Lighter" on 2 Apr 2026: up to 50x leverage, 50+ assets, US and UK users excluded. — [Cointelegraph, 2 Apr 2026](https://cointelegraph.com/news/wallet-in-telegram-perpetual-future-lighter-dex)
- **Minara AI** routes perps to Lighter or Hyperliquid, with most recent perp volume going to Lighter. Its "Minara Harness" agent, announced 8 Sep 2026, lists Lighter as a perps venue for automated "Autopilot" strategies. (search excerpt, secondary) — [ourcryptotalk Minara review](https://ourcryptotalk.com/crypto-review/minara-ai-review-2026); [aiwiki Minara Harness](https://aiwiki.ai/wiki/minara_harness/raw)
- A 2026 comparison claimed Lighter has "no copy trading features" natively (it predates or ignores public pools). (search excerpt) — [ARX blog](https://arx.trade/blog/perp-dex-wars-hyperliquid-lighter-aster/)
- **Leader discovery data:** Lighter exposes a public `pnlLeaderboard` endpoint, filterable by window (24h/7d/30d/all) and sortable by pnl, roi, volume or account_value. It returns L1 address, PnL, ROI, volume, streaks, net position, biggest position and long/short %. A live query worked with no auth. The 30-day #1 on 2026-10-21 had a $23.2M account and +$3.33M PnL. — [pnlLeaderboard reference](https://apidocs.lighter.xyz/reference/pnlleaderboard); [live query](https://mainnet.zklighter.elliot.ai/api/v1/pnlLeaderboard?time_window=30d&sort_by=pnl&sort_dir=desc&limit=10&offset=0)

### Inferences
- Copy-trading engines on Lighter most likely detect leader activity through the public `account_all_trades/{idx}` and `account_all_positions/{idx}` WebSocket channels, or REST `trades` and `account` (see Q3). They execute with a user-approved API key (Pattern B), ideally scoped to a dedicated sub-account. Dextrabot's and LighterFluid's exact detection and execution methods are not documented publicly; this is inferred from what Lighter's API allows.
- Cross-venue copying (a Hyperliquid leader mirrored on Lighter) is an established pitch (Dextrabot, LighterFluid). It is attractive because Lighter's Standard accounts pay 0% exchange fees.
- Copy trading on Lighter looks early and fragmented. No copy-trading app appears among Litscan's top integrators. The integrator channel as a whole is roughly 2–5% of venue volume, which equals about $478M/week against roughly $13–21B/week of venue volume (based on Q6 daily figures).

### Gaps
- Dextrabot's Lighter-specific mechanics (key handling, sub-accounts, latency) and its real Lighter volume.
- Whether LighterFluid is permanently shut down.
- No public numbers on copy-trading users or AUM on Lighter.
- I did not find Lighter-native Telegram copy-trade bots beyond Dextrabot's Telegram alerts.

---

## 3. Can an app read another account's trades, positions and orders in real time without that account's credentials (REST and WebSocket)?

### Takeaway
Yes for fills, positions, balances, funding and margin stats. No for open or resting orders and transaction status. I verified this live on 2026-10-21 against a large third-party master account (index 714710). A copier can therefore mirror positions and fills in real time with no permission from the leader, but cannot see the leader's resting limit, TP/SL or TWAP orders unless the leader shares a read-only token. Public pools are the exception: their open orders are public too.

### Cited Findings
**WebSocket** (`wss://mainnet.zklighter.elliot.ai/stream`; docs at [WebSocket reference](https://apidocs.lighter.xyz/docs/websocket-reference)). Each channel was subscribed to without `auth` on 2026-10-21:

| Channel | Live result without auth | Content |
|---|---|---|
| `account_all/{idx}` | **Works** | assets/balances, positions, funding_histories, pool shares, trade counts and volumes. The docs say it carries "Positions, trades, funding across all markets". |
| `account_all_trades/{idx}` | **Works** | snapshot of trades by market plus daily/weekly/monthly/total volume, then live trade updates |
| `account_all_positions/{idx}` | **Works** | positions per market, pool shares, funding rounds |
| `user_stats/{idx}` | **Works** | collateral, portfolio value, leverage, margin usage, available balance |
| `pool_info/{pool}` and `pool_data/{pool}` | **Works** (pools) | pool_data includes the pool's **orders**, trades, positions, shares and funding |
| `account_all_orders/{idx}` | Error 20001 "auth field is required" | all open orders |
| `account_orders/{mkt}/{idx}` | auth required | |
| `account_market/{mkt}/{idx}` | auth required | |
| `account_tx/{idx}` | auth required | |
| `notification/{idx}` | auth required | |
| `account_all_assets/{idx}` | auth required | |

- The Trade JSON includes `ask_account_id`, `bid_account_id`, `is_maker_ask`, size, price, `usd_amount`, `taker_position_size_before`/`maker_position_size_before`, `*_position_sign_changed` and timestamps. A copier can therefore tell opens from closes and flips directly from fills. — [WebSocket reference: Trade JSON](https://apidocs.lighter.xyz/docs/websocket-reference)
- The public trade channel `trade/{market}` streams every trade with both account IDs. The order book channel batches updates every 50 ms. — [WebSocket reference](https://apidocs.lighter.xyz/docs/websocket-reference)

**REST** (`https://mainnet.zklighter.elliot.ai/api/v1/`), called on 2026-10-21 without auth for master account 714710:
- `account?by=index&value=…` is **public**: collateral, available balance, every position (size, entry, margin) and sub-accounts. The docs call it a "Public account snapshot". — [Account data & positions](https://apidocs.lighter.xyz/docs/account-data); live query
- `accountsByL1Address?l1_address=…` is public (it maps an L1 address to its master and sub-account indexes). — [Core concepts](https://apidocs.lighter.xyz/docs/core-concepts); live query
- `pnl?by=index&value=…` (daily/hourly PnL, inflows and outflows) returned 200 without auth. — live query; [pnl reference](https://apidocs.lighter.xyz/reference/pnl)
- `trades?account_index=…`: the docs say "`auth` is required for master accounts and sub accounts" (public pools excepted) — [trades reference](https://apidocs.lighter.xyz/reference/trades). **However, the live unauthenticated call for master account 714710 returned 200 with that account's trades on 2026-10-21.** The docs and live behaviour disagree, and Lighter could enforce the documented rule at any time.
- `positionFunding` returned "auth required for main accounts". `accountActiveOrders`, `accountInactiveOrders`, `accountMetadata`, `liquidations` and `deposit/history` all returned "auth … empty". `transfer/history` for a non-pool account returned an error; it is public only for pools. — live queries; [transfer_history](https://apidocs.lighter.xyz/reference/transfer_history)
- The explorer API `https://explorer.elliot.ai/api/accounts/{L1|index}/positions` and `/logs` are listed as public reference endpoints, limited to 90 weighted requests per minute. — [positions reference](https://apidocs.lighter.xyz/reference/get_accounts-param-positions); [Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits)

**Auth options for private data**
- Auth token, signed by an API key: format `{expiry_unix}:{account_index}:{api_key_index}:{random_hex}`, maximum 8-hour expiry. — [API keys](https://apidocs.lighter.xyz/docs/api-keys)
- Read-only token: format `ro:{account_index}:{single|all}:{expiry_unix}:{random_hex}`. Expiry is between 1 day and 10 years. It cannot trade or withdraw. `all` covers the master account and its sub-accounts. It is created through `tokens/create` (weight 23,000) or the front end at app.lighter.xyz/read-only-tokens. — [API keys](https://apidocs.lighter.xyz/docs/api-keys); [Account data](https://apidocs.lighter.xyz/docs/account-data)

**Rate limits relevant to monitoring many leaders**
- WebSocket, per IP: 255 connections, 500 subscriptions and **500 unique accounts per connection**, 5,000 subscriptions and **5,000 unique accounts per IP**, 200 client messages per minute. Keepalive at least every 2 minutes. — [Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits); [WebSocket reference](https://apidocs.lighter.xyz/docs/websocket-reference)
- REST, per rolling minute: Standard 60 requests; Plus and Premium 24,000 weighted; **Builder accounts 240,000 weighted** for read-only endpoints. Builder accounts are free and applied for through Discord. Weights: `account` and other endpoints 300, `trades` 200, active/inactive orders 100. Authenticated requests count against the L1 address instead of the IP. — [Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits)
- Restricted regions: the docs say to connect with `?readonly=true` "if you're connecting from a restricted region" to still get read-only data. — [WebSocket reference](https://apidocs.lighter.xyz/docs/websocket-reference). Verified live from a US IP.

### Inferences
- A Mirrorlane-style service can watch up to about 5,000 leader accounts per IP in real time for free, using `account_all_trades` and `account_all_positions`, with no cooperation from leaders. Market and IOC fills are visible immediately. Resting limit orders only become visible once they fill.
- Leaders who opt in (for example, a "verified leader" programme) could hand over a long-lived `ro:` token. That would let a copier see and pre-place their resting and TP/SL orders, and get `account_tx` confirmations.
- Lighter's public account transparency is close to Hyperliquid's for positions and fills, but stricter for open orders.
- The undocumented public REST `trades` access for master accounts should not be relied on in production. WebSocket `account_all_trades` is documented without auth.

### Gaps
- Whether Lighter plans to gate `account_all*` or REST `trades` for master accounts. Nothing in the docs says so, but REST `trades` already conflicts with them.
- End-to-end latency from a leader fill to the WebSocket message was not measured.

---

## 4. Can a Lighter API key withdraw or transfer funds, or only trade? What permission scopes exist?

### Takeaway
There is no granular scope system. A normal API key is bound to one account index and can trade, manage the account, transfer between accounts owned by the same L1 address, and request secure withdrawals, which can only go to the owner's own L1 address. Anything that sends value to another owner (cross-owner transfers, fast withdrawals) or approves an integrator with fees also needs the wallet's L1 signature. The only restricted variants are read-only tokens and Premium-only maker-only keys.

### Cited Findings
- API key permissions table:
  - Scope: one account index (master, sub-account or pool).
  - Indexes 0–254, of which 0–3 are reserved for Lighter's apps, leaving 251 usable.
  - Registered through `ChangePubKey`, which needs the L1 wallet signature.
  - **Can do:** "Trade, cancel, modify, leverage/margin, sub-accounts, secure withdrawals, same-owner transfers, auth-gated REST and WebSocket reads".
  - **Cannot do alone:** "Transfers to another L1 owner, fast withdrawals, approving an integrator with fees (these also need the L1 signature)".

  — [API keys](https://apidocs.lighter.xyz/docs/api-keys) (updatedAt 2026-10-16)
- "Secure withdrawals only need the API key because they can only go back to the L1 address that created the account." — [API keys](https://apidocs.lighter.xyz/docs/api-keys)
- Withdrawal types: **secure withdrawal** goes only to the owner's L1 address, needs only the API key, accepts any asset, has a minimum of 1 USDC equivalent and settles via Ethereum. **Fast withdrawal** can go to any Ethereum address, needs the API key plus an L1 signature, is USDC only, costs 4 USDC and goes through Lighter's fast-withdraw pool. — [Deposits, Transfers and Withdrawals](https://apidocs.lighter.xyz/docs/deposits-transfers-and-withdrawals)
- `L2Withdraw` is rate-limited to 2 per minute and 3 per 2 hours per L1 address; fast withdrawals to 10 per hour. — [Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits)
- Maker-only keys (Premium/Advanced accounts only) can be restricted to post-only orders, modifying post-only orders, and cancels. There is a 1-hour cooldown between changes. — [API keys](https://apidocs.lighter.xyz/docs/api-keys)
- Read-only tokens cannot sign transactions ("won't allow placing trades nor request withdrawals"). Lighter recommends them for dashboards, tax tools and AI agents. — [API keys](https://apidocs.lighter.xyz/docs/api-keys)
- Lighter's integration guide for server-side or copy-trading products: "Treat these keys as highly sensitive: an API key can trade and can request secure withdrawals." — [Choose your integration](https://apidocs.lighter.xyz/docs/choose-your-integration)
- Transactions are queued per API key, with a separate nonce stream for each. Lighter recommends a dedicated key per workload. — [Core concepts](https://apidocs.lighter.xyz/docs/core-concepts)
- Account setup can be done with one wallet signature: "Create a Lighter account for a user and register an API key for your app, with a single wallet signature." — [Create accounts programmatically](https://apidocs.lighter.xyz/docs/create-accounts-programmatically)
- Sub-account limits: Standard 4, Plus 16, Premium 64. Sub-accounts cannot be deleted. — [Account Types](https://apidocs.lighter.xyz/docs/account-types); [Trading Fees](https://docs.lighter.xyz/trading/trading-fees)

### Inferences
- A copy-trading server holding a user's API key cannot send the user's funds to a third party without the user's wallet signature. That is a meaningful custody protection. It can still trade the account to zero, and can trigger withdrawals back to the user's own wallet.
- Best practice for a terminal: have the user create a dedicated sub-account for copying and register an app key on that sub-account only. The key is bound to one account index, so the user's other balances stay out of reach.
- There is no "trade-only, no-withdraw" scope. A Mirrorlane security pitch would rest on Lighter's withdraw-to-self-only design, not on a scope flag.

### Gaps
- Whether a sub-account key can initiate same-owner transfers out of the sub-account. "Same-owner transfers" implies it can, so a sub-account key may be able to move funds within the owner's accounts.
- No documented way for a user to revoke a single key other than replacing it via `ChangePubKey`.

---

## 5. Does Lighter offer fee sharing, builder codes or referrals for front-ends and integrators? What are the economics?

### Takeaway
Yes, through two programmes that cannot be stacked on the same trade. (1) **Partner Attribution / integrator fees**: a permissionless builder-code equivalent with up to 10 bps on perps and 100 bps on spot, credited in USDC to the integrator's account. The catch is that users must be on a paid (Plus or Premium) tier for non-zero fees. (2) **Referral kickbacks**: 10% to 20% of the Lighter fees paid by referred users on paid tiers, paid weekly. Neither earns anything on zero-fee Standard flow, apart from Standard TWAP and advanced-order fees in the referral case.

### Cited Findings
**Partner Attribution (integrator fees)**
- "The program is permissionless, allowing any account index to be used to collect fees, including subaccounts." — [Partner Attribution (API)](https://apidocs.lighter.xyz/docs/partner-integration) (updatedAt 2026-10-18)
- Global caps: perps up to 10 bps (0.1%), spot up to 100 bps (1%), minimum increment 0.01 bps. On Robinhood Chain Lighter the caps are perps up to 1% and spot up to 2%. — [Partner Attribution (docs)](https://docs.lighter.xyz/integrations/partner-attribution). Live `systemConfig` (2026-10-21) confirms `max_integrator_perps_taker_fee: 1000`, `max_integrator_perps_maker_fee: 1000` (that is, 10 bps at 1e6 scale) and spot 10000 (100 bps). — [live systemConfig](https://mainnet.zklighter.elliot.ai/api/v1/systemConfig)
- **Requirement:** "Trades containing partner attribution attributes with non-zero integrator fees will require the client submitting them to be on a Plus or Premium/Advanced account type." Zero-fee tracking-only attribution works on Standard. — [Partner Attribution](https://apidocs.lighter.xyz/docs/partner-integration)
- **User approval:** the user signs an `ApproveIntegrator` transaction setting maximum perps and spot maker/taker fees and an expiry in milliseconds. If the integrator's account belongs to a different L1 address and fees are non-zero, this needs an L1 signature plus L2 confirmation. It can be revoked by re-approving with zero fees, which needs only an L2 signature. A client can have at most 4 approved partners at once. — [Partner Attribution](https://apidocs.lighter.xyz/docs/partner-integration); [docs](https://docs.lighter.xyz/integrations/partner-attribution)
- Each order carries `IntegratorAccountIndex`, `IntegratorMakerFee` and `IntegratorTakerFee`, which may not exceed the approved maximums. Perps fees are credited in USDC; spot fees are credited in the asset received. Non-zero partner fees cannot be combined with custom self-trade-prevention modes (error 21159). — [Partner Attribution](https://apidocs.lighter.xyz/docs/partner-integration)
- Tracking: the `partnerStats` endpoint gives volume and fees, and Litscan has per-integrator pages. — [partnerStats](https://apidocs.lighter.xyz/reference/partnerstats); [Third-Party Resources](https://apidocs.lighter.xyz/docs/third-party)
- Real-world integrator fee levels (Litscan, 7 days to 2026-10-21): Telegram Wallet 9.0 bps, Minara AI about 2.5 bps, Insilico Terminal 1.0 bp, Jumper Perps 5 bps, GUBOTS 6.5 bps, Botlyz and CCXT 10 bps. All integrators together earned $142.0K on $478.5M (about 3.0 bps blended). — [Litscan](https://litscan.io/integrators)

**Referral programme (new version from 28 Jul 2026)**
- Referrers earn a share of the **gross fees** paid by referred users who use paid account types: Bronze 10% for everyone, Silver 20% for referrers with 15+ unique referrals each active on 5+ days. Upgrades are manual, weekly and discretionary.
- Referees get a 10% fee discount and their first week of Premium/Advanced fees rebated.
- Payouts are weekly L2 transfers, $1 minimum. Attribution is permanent, and referral codes cannot be changed after sign-up.
- "Trades executed through the partner attribution program, with non-zero integrator fees, are not considered for kickbacks and rebates."
- Applies across perps, spot and binary options. All rewards are discretionary.

  — [Referral Program](https://docs.lighter.xyz/referral-program)
- API endpoints: `referral/create`, `referral/use`, `referral/kickback/update` (set the kickback % shared back to referees, once per day), `userReferrals`, `referral_stats`. — [API llms.txt index](https://apidocs.lighter.xyz/llms.txt); [referral_kickback_update](https://apidocs.lighter.xyz/reference/referral_kickback_update)

**Other builder support**
- Builder Account: free, applied for through Discord, with 240,000 weighted REST requests per minute on read endpoints. — [Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits)
- "Accelerate" builders programme (run by Lit Hub, a third party): direct line to the Lighter core team, partner credits, visibility and a builders chat. — [Third-Party Resources](https://apidocs.lighter.xyz/docs/third-party)
- A "Builder API key for bridge.lighter.xyz deposits" is listed as optional for front ends. — [Choose your integration](https://apidocs.lighter.xyz/docs/choose-your-integration)
- Points: Season 2 retail points were 200,000 per week (Volume, OI, Funding, Liquidations, PnL). Market-maker Season 2 ended 26 Dec 2025. — [Points Program](https://docs.lighter.xyz/points-program); [Retail](https://docs.lighter.xyz/points-program/retail); [docs index](https://docs.lighter.xyz/llms.txt). I found no integrator-specific points programme.

### Inferences
- Economics for a copy-trading terminal: charging the maximum 10 bps integrator fee forces followers off the zero-fee Standard tier. On Plus they would pay 0.5 bps maker/taker to Lighter plus up to 10 bps to the terminal. On Premium, 0.4/2.8 bps. On $1M of copied notional per month, the maximum is $1,000 per month in integrator fees.
- The alternative, referrals, earns only 10–20% of Lighter's own fees. On Plus that is 0.05–0.1 bps, which is negligible, and nothing on Standard trades apart from Standard TWAP and advanced-order fees. Integrator fees are therefore the only meaningful on-chain revenue line, and the two cannot be stacked on the same trade.
- Standard accounts also carry the 300 ms taker speed bump (see Q6). A paid tier slightly improves copy latency (Premium 140 ms), which partly offsets the fee in a sales pitch.
- Each order carries its own integrator fee value, up to the approved maximum. A terminal could therefore charge copy trades and manual trades differently, or charge 0 bps on Standard users for tracking only.

### Gaps
- Whether Lighter takes any cut of integrator fees. The docs imply the full integrator fee goes to the integrator, but this is not stated explicitly.
- No published integrator revenue-share or "partner tier" beyond these caps. Telegram Wallet and Minara are labelled "partner" on Litscan, but any bespoke terms are not public.

---

## 6. Lighter's fee schedule (Standard / Plus / Premium), traction (volume, OI, TVL), business model and token, and incidents

### Takeaway
Lighter's model is zero fees for retail Standard accounts, which come with speed bumps. Revenue comes from Plus and Premium fees paid by pro and HFT flow, liquidation fees to LLP, LIT fee-credit leases and data access, with LIT buybacks funded from fee revenue. As of 2026-10-21 it is a top-4 perp DEX by open interest, at about $0.79B (behind Hyperliquid at $7.75B). Daily volume is about $1.9–3.0B depending on source, TVL is about $0.82B (DefiLlama), and LIT trades at $3.39 with an $849M market cap. All metrics are well below the Nov–Dec 2025 points-era peak. The main incident was a roughly 4.5-hour outage during the Oct 10–11, 2025 crash, which cost LLP 5.35% in a day.

### Cited Findings
**Fee schedule and latency (docs current 2026-10)**
- **Standard (default):** 0 maker / 0 taker. Taker latency 300 ms, cancel/modify 300 ms, maker 0 ms. 4 sub-accounts. "For standard accounts only, TWAP orders charge a 1bps fee." REST limit 60 requests per minute. — [Account Types](https://apidocs.lighter.xyz/docs/account-types); [Trading Fees](https://docs.lighter.xyz/trading/trading-fees). Also: "Fees paid to access advanced order types via a Standard account" exist. — [Referral Program](https://docs.lighter.xyz/referral-program)
- **Plus (opt-in):** 0.5 bps maker and taker. 300 ms taker, 300 ms cancel/modify, 0 ms maker. 4,000 sendTx per minute, 24,000 weighted reads per minute, 16 sub-accounts. — [Account Types](https://apidocs.lighter.xyz/docs/account-types)
- **Premium/Advanced (opt-in):** 0.40 bps maker / 2.80 bps taker with no LIT staked, falling to 0.28 / 1.96 bps at 500,000 LIT staked (30% discount). Taker latency 140 ms; maker and cancel 0 ms. 4,000–72,000 sendTx per minute depending on stake. 64 sub-accounts. Staking tiers are aggregated per L1 address. — [Account Types](https://apidocs.lighter.xyz/docs/account-types); [Trading Fees](https://docs.lighter.xyz/trading/trading-fees)
- Volume Quota (Plus and Premium only): +1 transaction allowance per $2 of volume, starting at 1,000 and capped at 15M, plus one free SendTx every 15 seconds. — [Volume Quota](https://apidocs.lighter.xyz/docs/volume-quota-program)
- Tier changes go through `changeAccountTier`; you can downgrade at most once per 24 hours, and upgrades have no cooldown. Sub-accounts share the L1 address's tier. — [Account Types](https://apidocs.lighter.xyz/docs/account-types)
- Order limits: Standard allows 250 active orders per account and 30 per market; Premium allows 1,500 and 1,000. — [Rate Limits](https://apidocs.lighter.xyz/docs/rate-limits)

**Business model and LIT**
- LIT utility:
  - Staking with a fixed 6% APR.
  - LLP access at 1 LIT per 10 USDC.
  - Fee discounts on Premium.
  - **Buybacks**: "LIT is bought back by the protocol using trading fee revenue … via daily 24-hour TWAPs."

  — [LIT Utility](https://docs.lighter.xyz/about-lighter/lit-utility)
- LIT Fee Credits: Premium users can lease credits toward a staking tier instead of staking. "All proceeds … are distributed to LIT stakers." — [LIT Fee Credits](https://docs.lighter.xyz/trading/trading-fees/lit-fee-credits)
- Data monetisation: global historical-trades export requires a one-time 100 LIT L2 transfer. — [export_historicalTrades](https://apidocs.lighter.xyz/reference/export_historicaltrades)
- Liquidity Partner Program: weekly LIT rewards to Premium market makers, based on randomised order-book snapshots. — [Liquidity Partner Program](https://docs.lighter.xyz/liquidity-partner-program)
- LIT launched 30 Dec 2025. Allocation: 25% airdrop to Season 1–2 points holders, team 26%, investors 24%, both with a 1-year lock and 3-year vest. 250M LIT moved for the airdrop, which implies a 1B supply. (search excerpts; The Block returned 403 to curl) — [The Block](https://www.theblock.co/post/383940/lighter-native-token-lit); [KuCoin News](https://www.kucoin.com/news/flash/lighter-token-airdrop-begins-after-250m-lit-transfers-on-chain); [Whale Alert](https://whale-alert.io/stories/c2736d8500c1/Lighter-launches-LIT-token-as-native-asset-for-its-zk-rollup-DEX-25-of-supply-airdropped-50-reserved-for-team-investors-with-1year-lock-and-3year-vesting)
- **LIT on 2026-10-21:** $3.39, market cap $848.6M, 24h volume $77.0M. CoinGecko rank 85. — [CoinGecko API (live)](https://api.coingecko.com/api/v3/simple/price?ids=lighter&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true)
- Funding: $68M at a $1.5B fully diluted valuation, announced 11 Nov 2025. Led by Founders Fund and Ribbit Capital, with Haun Ventures and Robinhood participating. Founder: Vladimir Novakovski. (search excerpts) — [Wilson Sonsini](https://ecvc.wsgr.com/news/wilson-sonsini-advises-lighter-on-dollar68-million-financing); [Axios Pro](https://www.axios.com/pro/all-deals/2025/11/13/pro-rata-premium-first-look-coinbase-blackstone-niall-horan); [Bankless](https://www.bankless.com/de/read/news/ethereum-perps-dex-lighter-raises-68m-at-1-5b-valuation)

**Traction (dated)**
- **Live exchangeStats (2026-10-21, about 14:10 UTC):** rolling 24h volume $1.896B across 440 markets, 2.12M trades. BTC $736M, ETH $506M, SOL $69M, US100 $47M. — [live exchangeStats](https://mainnet.zklighter.elliot.ai/api/v1/exchangeStats)
- **Castle Labs (updated 21 Oct 2026):**
  - Open interest: Lighter (including Robinhood Perps) is **#4 at $786.8M** (5.7% share), behind Hyperliquid $7.75B, Aster $1.36B and Variational $1.02B.
  - 24h perp volume: Lighter **#3 at $3.04B** (13% of tracked DEX volume), versus Hyperliquid $9.56B.
  - A further table lists Lighter at $1.80B average daily volume, 2.87x turnover and 0.8 bps fees.

  — [Castle Labs Perp DEX Rankings](https://castlelabs.io/research/perp-dex-rankings). The $3.04B and the live $1.896B differ, probably because of different windows or sources (CoinGecko versus native).
- **DefiLlama (API, 2026-10-21):**
  - TVL $819.6M, against a peak of $1,459.9M on 2025-12-18. TVL on 2026-04-01 was $512.4M.
  - OI $786.4M.
  - Fees: 30-day $6.03M, 1-year $81.6M. Revenue: 30-day $5.00M, 1-year $63.9M.
  - Monthly fees peaked at $18.1M in Nov 2025, bottomed around $2.8M in Apr–Jul 2026, and recovered to $5.3M in Sep 2026.

  — [DefiLlama Lighter](https://defillama.com/protocol/lighter) (via api.llama.fi; perp volume is paywalled on the API)
- Older figures, for context: on 13 Nov 2025, more than $1.1B TVL, $1.6B OI and "more than $10b in trading volume most days" — [On Chain Times](https://www.onchaintimes.com/a-look-into-lighters-llp-recent-performance/). March 2026 perp volume was $59B, "down nearly 80% from its peak of $292 billion in November" (2025) (search excerpt citing DefiLlama, about April 2026) — [Cointelegraph](https://cointelegraph.com/news/wallet-in-telegram-perpetual-future-lighter-dex)

**Incidents**
- Oct 10–11, 2025: Lighter went offline for about 4.5 hours during the roughly $19B market-wide liquidation event. LLP returned −5.35% over 24 hours. Lighter announced compensation, including 250,000 points to affected traders, and LLP holders were reportedly unimpressed. Beosin cited single-sequencer dependence and ZK proof-generation bottlenecks, and the CEO cited a delayed database upgrade. (search excerpts) — [Phemex, 12 Oct 2025](https://phemex.com/news/article/lighter-to-compensate-llp-holders-after-535-loss-25866); [Phemex outage](https://phemex.com/news/article/lighter-exchange-outage-amid-19b-crypto-liquidation-28446); [Cryptaper](https://cryptaper.com/lighter-distributes-points-to-users-affected-by-platform-outage/). Lighter's own LLP daily-return series confirms −5.348% on 2025-10-11 (live `pool_info`). Some outlets reported about 10% (unverified).
- After the incident, LLP was split into segregated strategy buckets. A February 2026 event reportedly capped LLP's loss at $75K while a trader lost about $8.2M. (search excerpt, secondary) — [Datawallet](https://www.datawallet.com/crypto/lighter-explained); [LLP Strategies](https://docs.lighter.xyz/trading/liquidations-and-llp-insurance-fund/llp-strategies)

**Jurisdiction**
- The Terms exclude anyone "located in, a resident of, or organized in the United States, Canada, the UK, China, North Korea, Russia, Ukraine, Cuba, Iran, Venezuela, Syria". Lighter may suspend access for "Unauthorized access to the API" or "Impersonation of the frontend interface". — [Lighter Terms](https://lighter.xyz/terms). The API enforces this by IP (error 20558, observed live from a US IP), while `?readonly=true` market and account data stays accessible.

### Inferences
- Lighter makes money from paid tiers and HFT, not retail. This puts it structurally in tension with a copy-trading front end that wants to monetise retail Standard users: the terminal can only charge once users opt into a paid tier.
- Traction has normalised after the points programme and TGE. Fees are about 30% of the Nov 2025 peak and TVL about 56%. Lighter remains a top-4 venue, and its high turnover (2.9–4.7x OI per day) suggests much of the volume is HFT or market-maker flow rather than retail directional flow that would be worth copying.
- Geo-restrictions (US, UK, Canada) limit Mirrorlane's addressable market and its legal exposure on Lighter. A server in a restricted region cannot submit transactions, but can read data in read-only mode.

### Gaps
- Lighter's own official volume and OI dashboards were not consulted. The figures are from the native API, Castle Labs and DefiLlama, which disagree on volume.
- Exact LIT circulating supply, buyback totals to date, and current staking APR history.
- No official Lighter post-mortem for October 2025 was retrieved (only secondary coverage).
- Robinhood Chain Lighter (a separate deployment with higher integrator fee caps of 1% perps and 2% spot) was not researched in depth. — see [Lighter on Robinhood Chain](https://apidocs.lighter.xyz/docs/lighter-rh)
