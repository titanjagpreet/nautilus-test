# Third-party copy-trading products on Hyperliquid (as of 21 October 2026)

Scope: third-party web apps, terminals, Telegram bots, wallet trackers and CEX products that let users follow or automatically copy Hyperliquid (HL) traders. HL protocol features (vaults, builder codes, agent wallets) are covered by another researcher. They appear here only where a product uses them.

Source-quality legend used below: **[primary]** = product's own docs or site; **[data]** = on-chain dashboard or API pull; **[media]** = crypto press, often re-reporting a dashboard or a press release; **[vendor/affiliate]** = a competing or affiliate site (these state their disclosures, but treat their claims with care); **[marketing]** = a product's own unaudited claim.

DefiLlama figures marked "DL, 21 Oct 2026" were pulled by me on 21 Oct 2026 from the DefiLlama API (`https://api.llama.fi/overview/fees/Hyperliquid%20L1?dataType=dailyRevenue` and `https://api.llama.fi/summary/fees/<slug>`). For builder-code interfaces, fees and revenue are effectively the same number: the builder fee the app collects.

---

## Q1. Which products exist, and which are largest by users, volume or builder-code revenue?

### Takeaway
Wallets and consumer apps (Phantom, Based, MetaMask, Trust Wallet, fomo), not copy-trading specialists, dominate HL builder revenue. The only copy-capable product with material current revenue is **Hyperdash**. pvp.trade, a Telegram bot, bought it in Nov 2025, and Hyperdash now earns about $409k per 30 days. Pure copy-trading apps (HyperX, Dexly, Katoshi, MirrorTrade) earn between a few hundred and about $23k a month. Several products are dormant or shut down: pvp.trade's own builder code, Hyperbot and goodcryptoX.

### Cited Findings

**Builder-code market size and leaderboards**
- The CoinGecko ranking of cumulative builder revenue (data to roughly 25 May 2026, reported 28 May 2026) puts **Phantom** first: $20.63M revenue, 137,496 users, about $150 revenue per user, 0.05% fee, $39.4B volume. **Based** is second: $15.05M on $44B volume at a 0.025% fee. Together the two make up about 55% of top-10 revenue. **MetaMask** is fourth with $6.51M at a 0.1% fee, 43,761 users and $7.46B volume. **Insilico** has $3.30M from only 2,962 users. **Axiom** has $2.27M on $22.1B volume at 0.01% (about $68 per user) — [CryptoPotato, 28 May 2026](https://cryptopotato.com/hyperliquid-builder-program-becomes-major-revenue-engine-for-wallets-and-bots-coingecko/) [media re-reporting CoinGecko; the original at coingecko.com/research/publications/top-hyperliquid-builders was bot-blocked for me]
- Same ranking: **PVP (pvp.trade) is third with $7.95M** and has the longest operating history in the top 10. The full top 10 is Phantom, BasedOneX, PVP, MetaMask, Insilico, Infinex, Axiom, Tread.fi, Dreamcash, Mass. The top 10 earned more than $63.5M combined. Mass has only 1,033 users but the highest average revenue per user — [CryptoAdventure, 5 Jun 2026](https://cryptoadventure.com/phantom-tops-hyperliquid-builders-as-hype-ecosystem-revenue-expands/) [media]
- Ecosystem total: "$80M in revenue has gone to over 300 of these apps in exchange for 12.4M users and $253B in volume", and "nearly 40% of the people trading on Hyperliquid never open its app". pvp.trade is shown at $7.99M revenue and $17B volume (sourced to CoinMarketMan HyperTracker) — [The Learning Pill Substack, 23 Jun 2026](https://thelearningpill.substack.com/p/hyperliquid-builder-codes-part-3) [media/analysis]
- HL HUB update (8 Oct 2026): Phantom leads all-time builder revenue, with $52.6B volume and 188K users — [KuCoin repost of HL HUB, 8 Oct 2026](https://www.kucoin.com/news/insight/META/6ac7584a38a2640007932413) [media; the post is truncated, so the full top-5 revenue numbers were not visible]
- HL HUB (15 Sep 2026): builder codes generated **$10.17M in 30-day revenue on $24.08B volume**. Trust Wallet was #2 by 30-day revenue — [KuCoin repost, 15 Sep 2026](https://www.kucoin.com/news/insight/META/6aa947a57d10fa0007cdaa20) [media; truncated]
- "The Builder Code @BasedOneX just surpassed $16M in revenue, making it the 2nd largest after Phantom" — [Hyperliquid News via KuCoin, 15 Oct 2026](https://www.kucoin.com/news/insight/SOL/6ad0d379fa4b9e000754ab7b) [media]

**Current 30-day builder revenue, DL, 21 Oct 2026 (interfaces relevant to copy/social trading; [data])** — [DefiLlama API overview](https://api.llama.fi/overview/fees/Hyperliquid%20L1?dataType=dailyRevenue)
| Product (DL name) | 30d revenue | 7d | All-time | Copy relevance |
|---|---|---|---|---|
| Trust Wallet Perps | $1,558,437 | – | $3.58M | wallet, no copy |
| fomo Perps | $1,385,960 | – | $2.77M | social feed, **no auto-copy** |
| Phantom Perps | $1,354,638 | $436,729 | $26.91M | wallet, no copy |
| MetaMask Perps | $1,307,419 | – | $12.06M | wallet, no copy |
| **HyperDash Perps** | **$409,297** | **$173,046** | **$1.14M** (1y: $1.02M) | **auto copy/countertrade** |
| Rabby Perps | $389,038 | – | $2.34M | wallet |
| Liquid Perps | $268,969 | $63,570 | $2.06M | one-tap "copy a trade" (manual confirm) |
| Insilico Terminal | $155,886 | $21,877 | $4.11M | pro terminal; no copy feature found |
| BasedApp Perps | $41,438 | $9,432 | $15.34M | app + TG bot; no copy |
| Dexly Trade Perps | $22,610 | $4,306 | $134,563 | auto copy |
| WunderTrading Perps | $14,906 | $3,277 | $240,338 | signal/grid bots |
| **pvp.trade Perps** | **$8,100** | $2,838 | **$8.01M** (1y: $435,753) | TG copy/countertrade |
| HyperX Perps | $6,211 | $1,257 | $171,540 | auto copy |
| Katoshi Perps | $298 | $54 | $14,793 | algo automation and strategy marketplace |
| Okto Wallet Perps | $188 | $10 | $886,315 | wallet, now near dormant |
- HyperDash's 24h revenue on 21 Oct 2026 was $41,828 (fees endpoint). Its 7d figure ($173k) is about 42% of its 30d figure, so revenue is accelerating — [DefiLlama HyperDash](https://defillama.com/protocol/hyperdash) [data]
- Insilico's DefiLlama methodology: "builder code revenue from Hyperliquid Perps Trades **and Lighter Partner Fees**". Insilico monetises on both HL and Lighter — [DefiLlama Insilico Terminal](https://defillama.com/protocol/insilico-terminal) [data]

**Product roster and status**
- **pvp.trade** (Telegram bot, `@pvptrade_bot`): group-chat perps trading, clans, leaderboards, `/track` wallet tracking, copy and countertrade of opted-in PVP users — [pvp.trade docs: Getting Started](https://docs.pvp.trade/en-quickstart); [Copytrading](https://docs.pvp.trade/en-copytrading) [primary]
- **pvp.trade acquired Hyperdash** (terms undisclosed) and launched Hyperdash V2 — [Phemex News, 19 Nov 2025](https://phemex.com/news/article/pvptrade-acquires-hyperdash-unveils-enhanced-v2-version-37252) [media]. The relaunched Hyperdash desktop terminal went fully live on 5 Jan 2026 ("after months of rebuilding following its acquisition by PVP Trade"). It is the exclusive terminal for Kinetiq's "Markets" HIP-3 marketplace — [Bankless, 7 Jan 2026](https://www.bankless.com/read/getting-started-with-hyperdashs-revamped-trading-terminal) [media]
- pvp.trade spent about $8.68M of builder income buying 421,000 HYPE (average $20.6), then worth about $24.34M. It unstaked 400,000 HYPE (about $22.8M) — [BlockBeats via Bitget News, 28 May 2026](https://www.bitget.com/news/detail/12560605432527) [media, citing on-chain analyst Yu Jin]
- pvp.trade was the leading builder when total builder-code revenue passed $10M — [Odaily via Bitget News, 10 Jul 2025](https://www.bitget.com/news/detail/12560604858009) [media, citing Messari]
- **Hyperdash** (hyperdash.com) is now a full terminal: perps, spot, HIP-3 RWA perps, prediction markets, Perp RFQ (private beta), and analytics (Explore, Cohorts, Leaderboard, liquidation heatmaps). Its copy trading "mirrors or counters up to 10 traders" — [Hyperdash docs: About](https://docs.hyperdash.com/about-hyperdash.md) [primary]
- **HyperX** (hyperx.trade): smart-money tracking, wallet leaderboard, one-click copy trading, AI-agent trading API, data API, iframe embeds. Claims "500,000+ Tracked Wallets, $200M+ Trading Volume, 5,000+ Users, 1 Year+ Stable Uptime" — [HyperX homepage, accessed 21 Oct 2026](https://hyperx.trade/) [marketing]
- **Dexly** (dexly.trade): HL terminal (crypto, tokenized stocks, commodities, prediction markets) with a Copy Trading tab and iOS/Android apps. Claims "+1,214 people joined onchain trading today!" — [Dexly homepage, accessed 21 Oct 2026](https://dexly.trade/) [marketing]
- **Katoshi**: "Trading Automation Engine for Hyperliquid": TradingView/webhook triggers, scripting, multi-account, MCP and AI agents, plus a **Strategy Marketplace**: "copy proven strategies from other traders — or publish your own algorithms and earn fees from every trade". "New app in beta… the current app will be phased out soon" — [Katoshi homepage, accessed 21 Oct 2026](https://katoshi.ai/) [primary/marketing]
- **Liquid** (liquid.trade): multi-venue consumer app. Its feed has a "copy a trade in one tap" button, and it "has processed over $5B in trades" — [Liquid docs](https://docs.liquid.trade/) [primary]. Liquid also routes to Ostium and Lighter — [Learning Pill Substack, 23 Jun 2026](https://thelearningpill.substack.com/p/hyperliquid-builder-codes-part-3)
- **fomo**: social trading app on HL perps. Per a third-party review of its help centre, it has public trade feeds, follow alerts and a leaderboard, but "fomo does not have a copy trading feature" — [Cipher Intelligence, updated 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- **Based**: native iOS/Android HL front-end at a 0.025% perps builder fee, with a Telegram bot. Its docs list no copy-trading feature — [Cipher Intelligence, 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- **Insilico Terminal**: free pro terminal. Users connect by browser wallet and sign a **1 bps builder fee**, or paste an API key. Offers TWAP, limit chase, scale orders, CLI/hotkeys, multi-wallet — [QuickNode Builders Guide listing](https://www.quicknode.com/builders-guide/tools/insilico-terminal-by-insilico-trading) [media/listing; content seen via search snippet]. I found no copy-trading feature.
- **HyperTracker (CoinMarketMan)**: wallet and whale tracker. Claims to track over 1.6M wallets, with alerts and an API, and runs a public builder-code dashboard — [HyperTracker](https://hypertracker.io/); [CMM builders dashboard](https://app.coinmarketman.com/hypertracker/builders) [primary; the dashboard is JS-rendered and I could not read it directly]. I found no copy execution.
- **BitMEX "Hyperliquid Copy Trading"** (CEX): launched 5 Feb 2026. A leaderboard of top HL traders ranked by PnL, drawdown, win ratio and AUM. Users "copy or reverse copy". Positions open on BitMEX, not HL. Up to 5 HL traders at once, with TP/SL. 100,000 USDT launch prize pool — [BitMEX press release via AAP/GlobeNewswire, 5 Feb 2026](https://www.aap.com.au/aapreleases/globenewswire1001163188/) [primary press release]. A follow-up "Copy and Conquer" campaign had a 50,000 USDT pool, 14 May – 14 Jun 2026 — [Macau Business/GlobeNewswire](https://macaubusiness.com/bitmex-launches-the-copy-and-conquer-campaign-featuring-a-50000-usdt-prize-pool/) [primary press release]
- **Hyperbot** (AI terminal: whale tracking plus copy trading, on HL and Aster). **Discontinued / winding down.** HypeChain records a provider announcement of a trading and copy-trading end date of 1 Oct 2026, with a user exit deadline of 30 Sep 2026, and notes the shutdown is "not independently confirmed" — [HypeChain bot directory, evaluated 13 Oct 2026](https://hypechain.app/best-hyperliquid-trading-bots/) [vendor/aggregator]
- **goodcryptoX**: announced it would stop operating on 9 Oct 2026 — [Turbine, 6 Oct 2026](https://www.turbinefi.com/blog/best-hyperliquid-trading-bots); [HypeChain](https://hypechain.app/best-hyperliquid-trading-bots/) [vendor]. **Discontinued.**
- **CopyLiquid**: "still pre-launch and selling a token presale" as of Sep 2026 — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]. Treat it as unproven or a red flag.
- **Hypurr Fun (HFUN)**: a Telegram memecoin launch, sniper and TWAP bot ("PumpFun of Hyperliquid"). I found no copy-trading feature — [BeInCrypto](https://beincrypto.com/learn/hypurr-fun-guide/) [media]
- **Perpex**: Android app listed as "Copy trade, grid bots & perps on Hyperliquid", with no settings described — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- **MirrorTrade**: a small copy service hosted on a raw-IP sslip.io domain. It claims a 1 bp fee per copied order, no deposit to the service, and execution through an agent key — [MirrorTrade FAQ](https://45-32-38-235.sslip.io/faq) [marketing; unverified operator]
- **Nansen API**: offers a documented DIY "find & copytrade wallets on Hyperliquid" workflow using perp-leaderboard, perp-positions and perp-trades endpoints, with smart-money labels — [Nansen docs](https://docs.nansen.ai/guides/templates/complex-use-cases/use-case-2-find-and-copytrade-wallets-on-hyperliquid) [primary]
- Open-source copy bots are common: e.g. Hyperliquid_Copy_Trader (WebSocket monitoring, proportional sizing, blocked-asset list) — [Chainstack, 12 May 2026](https://chainstack.com/hyperliquid-trading-bots-2026/) [vendor]
- **Finestel** "Trade Copier" (multi-venue including HL) replicates a master account across copier accounts, "with profit-sharing and performance-fee configuration built in" and a white-label option — [Chainstack, 12 May 2026](https://chainstack.com/hyperliquid-trading-bots-2026/) [vendor]

### Inferences
- The flow from pvp.trade's builder code appears to have moved to Hyperdash. pvp.trade's revenue over the last year was about $436k against an $8.0M lifetime total, and it is now about $8k a month. Hyperdash went from near zero to about $1.0M in its first year, and about $409k in the latest 30 days. This fits the Nov 2025 acquisition and the Jan 2026 relaunch. It is an inference; I found no statement from pvp.trade on migrating users.
- Commercially, the winning model on HL has been **distribution plus a terminal or wallet**, with copy trading as one feature. Standalone copy apps have not scaled: HyperX, Dexly and Katoshi together make about $29k a month, against Hyperdash's $409k and fomo's $1.39M. The biggest "social" earner, fomo, does not auto-copy at all.
- Based's figures conflict. DefiLlama shows only $41k in 30-day perps revenue, while "surpassed $16M" on 15 Oct 2026 implies it was still growing. Based may use several builder addresses, or DefiLlama may be mis-attributing them. Neither DefiLlama number should be used for Based without checking.

### Gaps
- No product publishes the number of active copiers, copied AUM or copy-specific volume. Hyperdash's revenue mixes 1.5 bps terminal trades with 5 bps copy trades.
- CoinMarketMan's builder dashboard reportedly shows Hyperdash at 944 users over 30 days with about $386 ARPU. That comes from a garbled search snippet only and is unverified.
- pvp.trade user counts: a Telegram directory figure of 30,114 MAU (undated) and about 11k MAU (late 2024) appear only in search summaries. I found no 2026 figure.
- I found no evidence that Okto, BloFin or other CEXs offer HL-leader copy trading, apart from BitMEX. Okto's builder revenue is near zero ($188 per 30 days).
- I could not read the CoinGecko original, Hypurrscan builder stats or ASXN dashboards (bot-blocked or JS-only). All rankings above are reproduced from secondary reports or the DefiLlama API.

---

## Q2. How leaders are picked, copy settings, how leader activity is detected, execution path and latency

### Takeaway
Leader discovery is built on HL's fully public account data: leaderboards ranked by realized PnL, ROI, equity, win rate and proprietary "copy scores", with style tags. Copy engines mirror position changes, not orders. They size by a ratio or a fixed allocation, and apply caps on leverage, worse entry and assets. Hyperdash, HyperX and Dexly execute from the user's own HL account through a no-withdraw agent key. pvp.trade and Hyperdash "Create New" use app-managed Turnkey wallets. Detection is via WebSocket `userFills` or position diffs, plus periodic reconciliation. No product publishes audited latency figures. The practical lesson from developers is that exits, not entry latency, decide copier performance.

### Cited Findings

**Hyperdash (most complete public spec)** — [Hyperdash docs: Copy Trading](https://docs.hyperdash.com/copy-trade) [primary]
- Discovery: the Explore "Copytraders" section ranks the **Top 100 copyable traders**, with curated tabs ("Equities Focused", top BTC/HYPE/CL traders). Sort by copy score, ROI, equity or recent activity. Cards show ROI, equity, volume and last trade time. Users can also paste any address.
- For a single trader, a chart projects their 30-day PnL onto a $1,000 allocation, inverted for countertrading.
- Modes: **Copytrade** (mirror) or **Countertrade** (opposite side). Up to **10 target traders per wallet**, weighted equally or custom.
- Settings: max position leverage **1x–40x**. "Only copy newly opened positions", which skips positions already open at start. **Max worse entry 0%–50%** versus the trader's entry. Option to include spot and staked HYPE in copy sizing. Asset whitelist or blacklist.
- What is copied: "When a target trader opens or closes a perp position, your wallet mirrors it (or counters it), sized to your allocation". Only perp positions are copied; this is not an alert feed. "Removing a trader closes its copied positions on the next sync."
- Operations: per-wallet logs show every action, including skipped trades with reasons. The trader warning says copying an algorithmic trader "may not replicate their results due to execution speed differences". **Stop always closes the wallet's open positions.** Archive returns funds from a Hyperdash-created wallet. Users can share a PnL card.
- Leaderboard: ranked by **net realized PnL**, so unrealized PnL does not move rank. Tabs: Overall, Equities, Commodities, Majors, Alts. Timeframes 24H/7D/30D/YTD/All. Columns: account value, net PnL ($ or %), volume, win rate, trades, top assets. Filters: account value, win rate, style tag (Algo, Scalp, Intraday, Swing) — [Hyperdash docs: Leaderboard](https://docs.hyperdash.com/leaderboard.md) [primary]
- Global trader filters: period, account value, PnL, style (including Position), **copy score 0–100**. Results show PnL, equity, trades, win rate, **Sharpe ratio, max drawdown, leverage, margin utilization** and assets traded. Tracked wallets stream into a "Tracked" feed — [Hyperdash docs: Trader Explore](https://docs.hyperdash.com/wallet-explore.md) [primary]
- Bankless (Jan 2026) says copy trading "includes built-in risk controls for position sizing, stop-losses, and take-profits" — [Bankless, 7 Jan 2026](https://www.bankless.com/read/getting-started-with-hyperdashs-revamped-trading-terminal) [media]. The current docs list no copy-specific SL/TP, so this has either changed or the reviewer was describing the general terminal.
- Institutions can peer their own HL node with Hyperdash's sentry infrastructure ("Direct Sentry Peering"). This is a latency and data-infrastructure feature, not copy-specific — [Hyperdash llms.txt index](https://docs.hyperdash.com/llms.txt) [primary]

**pvp.trade (Telegram)** — [pvp.trade docs: Copytrading](https://docs.pvp.trade/en-copytrading) [primary]
- Only PVP users who opt in ("🤝 Allow others to copy me") can be copied. A leader can have only **one** copyable account. Followers can run multiple copy/counter accounts and pick a leader **by username**.
- Each copy account is funded from the user's primary PVP account. Stopping converts it to a regular account. The docs describe no sizing or risk settings.
- General bot commands include `/leaderboards`, `/track` (wallet tracking), `/stoploss`, `/takeprofit`, and group-chat trade broadcasts — [pvp.trade docs: Getting Started](https://docs.pvp.trade/en-quickstart) [primary]

**HyperX** — [HyperX homepage demo "copy engine" panel, accessed 21 Oct 2026](https://hyperx.trade/) [marketing]
- Example config: Mode = **Position Ratio** (ratio 10%). Leverage = "Follow ≤ 5x" (capped). **Margin limit $200–$5,000.** **TP +30% / SL −10%**. Follow = "Open + Close".
- Engine log: "Subscribed to trader … positions", then "Watching position changes", then a signal that the trader opened an ETH long with $5,000 margin at 20x. It computes 10% → $500 margin, caps to 5x → $2,500 size, sends a market buy, and on the trader's close triggers `follow_decrease`. This describes a **position-diff** detection model.
- A third-party summary lists HyperX settings as "Ratio, leverage limit, margin range, TP/SL per copy" on Web, Android and iOS TestFlight — [Cipher Intelligence, 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]

**Dexly**: "Mirrors leaderboard wallets; drawdown pause, max position size"; agent-wallet authorisation, with funds staying in the user's wallet; iOS and Android apps — [Cipher Intelligence, 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]

**Liquid (semi-manual social copy)**: "Copy Trade opens that market's order form with their trade for you to check and place yourself; on iOS, Copy Close closes your copy when the trader exits" — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]. Liquid's own docs say "Follow traders to fill a live feed with their entries and exits, filter it by asset, and copy a trade in one tap" — [Liquid docs](https://docs.liquid.trade/) [primary]

**BitMEX (cross-venue copy)**: leaders are ranked by PnL, drawdown, win ratio and AUM. Up to 5 HL leaders, copy or reverse copy, per-leader TP/SL — [BitMEX press release, 5 Feb 2026](https://www.aap.com.au/aapreleases/globenewswire1001163188/) [primary]. A BitMEX spokesperson told The Defiant the company used HL L1's open-source code to track leader positions — [The Defiant](https://thedefiant.io/news/cefi/bitmex-launches-hyperliquid-copy-trading) [media; seen via search snippet only, page was Cloudflare-blocked]

**Detection and execution architecture (DIY reference)** — [Cipher Intelligence, 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate, cites HL docs]
- Signal: subscribe to WebSocket **`userFills`** for the leader's address, with **`userFillsByTime`** as REST fallback. Per-IP limits are 1,200 REST weight per minute, 10 WebSocket connections, 1,000 subscriptions, and **at most 10 unique users across user-specific subscriptions**.
- Sizing: read the leader's **`clearinghouseState`** account value and multiply each fill by the ratio of the follower's equity to the leader's. Cap by per-market notional, round to size decimals, and **drop orders under HL's $10 minimum**, logging them.
- Execution: sign with an API (agent) wallet. Use **IOC limit orders a few ticks through the book** rather than pure market orders, so a stale signal cannot fill at any price.
- Safety: a reconciliation task "compares your positions with the leader's every few seconds and flattens anything they no longer hold". Use a net-flat exit rule and a hard account-drawdown stop. HL's address-based limit is 1 request per 1 USDC traded, with a 10,000-request starting buffer.
- Chainstack: "A bot using HTTP polling misses fills, accumulates stale position data, and risks double-submitting orders. Every production bot in this list uses WebSockets" — [Chainstack, 12 May 2026](https://chainstack.com/hyperliquid-trading-bots-2026/) [vendor]
- The Nansen DIY template instead **polls** leaderboard, positions and trades endpoints, and periodically checks whether tracked wallets closed positions so it can close and rebalance — [Nansen docs](https://docs.nansen.ai/guides/templates/complex-use-cases/use-case-2-find-and-copytrade-wallets-on-hyperliquid) [primary]

**Latency claims (all unverified)**
- MirrorTrade claims about 0.7s copy latency — [MirrorTrade FAQ/landing](https://45-32-38-235.sslip.io/faq) [marketing; latency figure from search summary of the site]
- Katoshi: "Execute trades in milliseconds. Our optimized architecture outperforms the official SDK" — [Katoshi](https://katoshi.ai/) [marketing]
- Hyperdash: "every trade is copied automatically, in real time" — [Hyperdash docs](https://docs.hyperdash.com/copy-trade) [marketing]
- In general: "Seconds; you fill after the leader, usually as a taker" — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]

**Exit logic is the main driver of copier results (developer evidence)**
- From an r/algotrading thread by a developer who ran a self-built HL copy bot for months, as summarised by Cipher: "Entry lag of under a minute barely changed results; the edge leaked on how positions were closed." Rules: close only when the source is **net flat**; mirror partial exits proportionally; use a wide **catastrophe stop** rather than tight stops; reconcile on a schedule; skip "minute-flippers". Copies earned "about half of the source wallet's edge, mostly lost on exits" — [Cipher Intelligence, 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [secondary summary of Reddit; I could not access the original thread]

### Inferences
- Every serious product copies **position changes** (open, increase, decrease, close) rather than resting orders. None says it copies a leader's open limit orders or TP/SL orders. Followers therefore always enter as takers after the leader. I found no product that copies a leader's limit orders as makers.
- Hyperdash's "next sync" wording and per-wallet skip logs point to a hybrid design: event-driven mirroring plus a periodic reconciliation loop. Its "max worse entry" setting is effectively a slippage guard. "Only copy newly opened positions" stops followers buying into stale positions.
- The 10-unique-users-per-IP limit on user-specific WebSocket subscriptions forces any multi-leader copy service to shard across IPs, run its own non-validating node, or use a data vendor. Hyperdash's sentry/node peering offering suggests it runs its own node infrastructure.
- Countertrading (Hyperdash, pvp.trade, BitMEX "reverse copy") is a standard feature and cheap to build once copy exists.

### Gaps
- No product publishes measured signal-to-fill latency, copy slippage statistics, or fill-quality reports.
- Dexly's and pvp.trade's sizing algorithms (fixed vs proportional) are not documented publicly.
- Whether BitMEX's engine uses `userFills` or polls positions is unknown beyond "open-source code".

---

## Q3. Custody and security model; incidents and failures

### Takeaway
There are two custody models. (1) The **user's own HL account plus a no-withdraw agent (API) key**: Hyperdash "Use Existing", Dexly, HyperX, MirrorTrade, Insilico, Katoshi. (2) An **app-created embedded wallet secured by Turnkey enclaves**: pvp.trade, Hyperdash "Create New" and Google/Apple sign-in, fomo. BitMEX is fully custodial (CEX). I found **no** reported drain or key leak at any HL copy-trading product to Oct 2026. Reported HL user losses are private-key compromise or phishing outside the protocol, plus two copy-platform wind-downs (Hyperbot, goodcryptoX).

### Cited Findings
- Hyperdash agent model: "Hyperdash generates a fresh keypair in your browser, and your wallet signs an approval registering it as your trading agent. The agent key is valid for 180 days and is **encrypted in your browser before it is stored**." A second signature approves the builder fee. "The agent key signs trading actions only… Withdrawals and asset transfers are signed by your own wallet." The encrypted agent key "is what powers features like Copytrading". 2FA (passkey or TOTP) is required before withdrawals. Agent Manager offers refresh/revoke — [Hyperdash docs: API Wallets and Security](https://docs.hyperdash.com/agent-wallets-security.md) [primary]
- Hyperdash sign-in by Google, Apple or email creates "a non-custodial wallet for you, secured by **Turnkey**". Users can create multiple Turnkey wallets. Fiat on-ramps are available (cards, bank transfer, Revolut Pay, PIX and others) — [Hyperdash docs: Onboarding](https://docs.hyperdash.com/onboarding-deposits.md) [primary]
- Hyperdash copy wallets: "Create New: Hyperdash creates a dedicated wallet and funds it with USDC from your primary wallet. Use Existing: connect your own wallet holding at least $100 USDC, create an API key (valid 180 days), approve the 0.05% builder fee, and enable unified account mode" — [Hyperdash docs: Copy Trading](https://docs.hyperdash.com/copy-trade) [primary]
- pvp.trade: "Private keys are stored and encrypted by **Turnkey**… Only you have access to your private key as it is stored with Turnkey's verifiably secure enclaves". Users can set up 2FA with biometric passkeys and **export the private key** in `/settings`. Existing HL accounts can be attached with an API key — [pvp.trade FAQ](https://docs.pvp.trade/en-faq) [primary]
- fomo has no wallet connection (Apple, Google or email only) and creates its own wallet and HL account for the user — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- Liquid: "non-custodial… every trade and transfer is signed from that wallet"; sign-in by email, Google, Apple or wallet — [Liquid docs](https://docs.liquid.trade/) [primary]
- Katoshi: "non-custodial architecture — your API keys never leave your device" — [Katoshi](https://katoshi.ai/) [marketing]
- MirrorTrade: "We cannot withdraw your funds. We place orders in your account through an agent key, which Hyperliquid does not allow to withdraw or transfer." Its fee "is added to each copied order by Hyperliquid and paid out to us" — [MirrorTrade FAQ](https://45-32-38-235.sslip.io/faq) [marketing]
- Residual key risk: "an app's API wallet can open any position in the account it is approved for until it expires or you revoke it". Use a separate account for copying and set an expiry (at most 180 days). Hyperdash's **Stop closes every open position in that wallet, including your own trades** — [Cipher Intelligence, 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- Scams around the category: fake "Hyperliquid vault" sites, "token presales for copy-trading platforms that do not exist yet", and requests for seed phrases. "A real copy tool never needs your private key or a withdrawal permission" — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- Incidents: "As of August 2026 there is no verified case of an attacker breaching Hyperliquid's contracts, bridge or consensus". User losses have been off-protocol: fake airdrops, malicious approvals, Google-ads phishing (about $550K in Aug 2026), and a whale key compromise of about $21M — [HyperAcademy, updated Aug 2026](https://hyperacademy.io/en/articles/hyperliquid-security-and-hack-risk) [media/analysis]
- The roughly $21M theft (Oct 2025) was a private-key compromise of one trader's wallet and "not Hyperliquid itself". It has not been linked to any bot — [CoinDesk, 10 Oct 2025](https://www.coindesk.com/business/2025/10/10/usd21m-crypto-theft-on-hyperliquid-tied-to-private-key-leak-peckshield) [media]
- Product failures and wind-downs: Hyperbot announced the end of trading and copy-trading on 1 Oct 2026, with a user exit deadline of 30 Sep 2026. goodcryptoX announced shutdown on 9 Oct 2026 — [HypeChain, 13 Oct 2026](https://hypechain.app/best-hyperliquid-trading-bots/) [vendor/aggregator]

### Inferences
- Copy trading needs an always-on server that holds a key able to sign the user's orders. Hyperdash solves this by storing a browser-encrypted agent key. pvp.trade solves it by holding the full wallet key in Turnkey enclaves. Either way the server becomes a high-value target. An attacker cannot withdraw with an agent key, but could still grief accounts by trading them into losses or against attacker liquidity. This is the main residual risk; no incident of this type was found.
- Running copy accounts as separate sub-wallets (Hyperdash "a wallet dedicated to that strategy", pvp.trade's per-copy accounts) is a design pattern that limits blast radius and makes "Stop closes all positions" safe.
- Embedded wallets (Turnkey or Privy-style) with social login are now table stakes for consumer HL apps: Hyperdash, pvp.trade, fomo, Liquid. Card and fiat on-ramps are bundled.

### Gaps
- I found no audits or penetration-test reports published by any HL copy-trading app.
- No product discloses how agent keys are encrypted at rest server-side (KMS or HSM) or who can decrypt them.
- I found no reported incident specific to Hyperdash, pvp.trade, HyperX or Dexly. This is absence of evidence from searches, not proof.

---

## Q4. Business model and fees: builder fees, subscriptions, profit share, referrals, tokens and points, revenue

### Takeaway
The dominant model is a **per-fill builder fee**, often with a **copy surcharge**: Hyperdash charges 5 bps on copy trades against 1.5 bps on normal trades, and excludes copy volume from rebates. It is combined with cashback and referral rev-share ladders. Profit share to leaders is rare among wallet-mirroring apps (leaders are unaware public wallets). It exists only where leaders opt in: pvp.trade gives 10% to leaders, BitMEX charges a 15% profit share, Katoshi's marketplace pays per-trade fees to strategy publishers. Subscriptions are marginal (HyperX Pro, reportedly $199/yr). pvp.trade ran a points program and recycled about $8.7M of builder revenue into HYPE.

### Cited Findings
- **Hyperdash fees**: builder fee **1.5 bps (0.015%) on perps** and 3 bps on spot and prediction markets. Referral sign-ups pay 10% less. Cashback tiers by own 30-day volume run from **5% (Wood, $0) to 22.5% (Obsidian, $500M)**, and 25% for VIP. Referral rev share runs **20%–35%** of referees' fees by referred volume, direct referrals only, and the level never drops. Claim minimum is $10; an affiliate program is offered — [Hyperdash docs: Fees, Referrals & Rewards](https://docs.hyperdash.com/fees-referrals-rewards.md) [primary]
- **Hyperdash copy fee**: "Trading through Hyperdash uses a **0.05% builder fee**… **Volume generated by copy trading is not eligible for fee rebates.**" — [Hyperdash docs: Copy Trading](https://docs.hyperdash.com/copy-trade) [primary]. Worked example: a $10,000 copied taker fill costs 0.045% HL taker + 0.05% Hyperdash = 0.095%, or $9.50 — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- **pvp.trade fees** (fee-tiers page): at level 1 the base fee is **0.025%–0.040%**, falling to 0.010%–0.025% at level 98. A 30-day volume discount gives up to −1.5 bps (≥$1B). A **per-trade "effective leverage" discount** grows linearly to −4 bps at 40x leverage. Spot sell fee is 2x the perp fee — [pvp.trade docs: Fee Tiers](https://docs.pvp.trade/en-fee-tiers) [primary]. **Conflict:** the FAQ still says "0.05% on futures trades, and a 0.5% fee on spot trades (only sells)" — [pvp.trade FAQ](https://docs.pvp.trade/en-faq) [primary, likely stale]
- **pvp.trade leader profit share**: "Copytrading leaders earn **10% of the profits of their followers on closing a position**, there is no profit sharing from users that countertrade your positions. The profits are sent to your leader account." — [pvp.trade docs: Copytrading](https://docs.pvp.trade/en-copytrading) [primary]
- **pvp.trade growth loops**: rakeback by XP level runs from 5% to 30% (levels 95+). XP is earned from trades and quests, and levels unlock cards, fee tiers, a PVP T-shirt and a ring. Referrals pay **three tiers, L1 10% / L2 3% / L3 1%**, "forever" — [pvp.trade docs: Referrals](https://docs.pvp.trade/en-referrals); [Levels](https://docs.pvp.trade/en-levels) [primary]
- **pvp.trade points**: the program began 27 Jul 2024 with a fixed supply of 1,000,000 points, distributed weekly. "As of February 15, 2025, all points have been distributed." Only PVP-created wallets (not API-connected) were eligible, and top-10 clans got bonus points — [pvp.trade docs: Points](https://docs.pvp.trade/en-points) [primary]. A $PVP ticker was reportedly secured in an HL auction — [X post via search, undated](https://x.com/hyper_updates/status/1876266539151700004) [promotional; unverified]
- **pvp.trade treasury**: about $8.68M of builder income was used to buy 421k HYPE — [Bitget/BlockBeats, 28 May 2026](https://www.bitget.com/news/detail/12560605432527) [media]
- **HyperX pricing**: free tier 10 wallets at a 0.055% copy fee; **Pro $199/year**, 20 wallets, 0.035% fee, 1-on-1 support — [QuickNode Builders Guide listing](https://www.quicknode.com/builders-guide/tools/hyperx-by-hyperx) [listing; seen only via search snippet, undated]. Contradicted by Cipher on 21 Oct 2026: "Builder fee required; rate not published" — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/)
- **Dexly**: its copy page says "no platform fees", but enabling copy asked for a builder-fee approval in Sep 2026, rate not published — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate]
- **Liquid**: adds 0.05% per crypto perp fill — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/). Referral: friends get a 10% benefit on fees; the referrer earns 10% by default, up to 50% — [Liquid docs](https://docs.liquid.trade/) [primary]
- **Based**: 0.025% perps builder fee — [CryptoPotato/CoinGecko](https://cryptopotato.com/hyperliquid-builder-program-becomes-major-revenue-engine-for-wallets-and-bots-coingecko/). **Insilico**: 1 bp — [QuickNode listing](https://www.quicknode.com/builders-guide/tools/insilico-terminal-by-insilico-trading). **Axiom**: 0.01%; **MetaMask**: 0.1% (cap) — [CryptoPotato](https://cryptopotato.com/hyperliquid-builder-program-becomes-major-revenue-engine-for-wallets-and-bots-coingecko/)
- **WunderTrading**: 0.035% builder fee instead of a subscription — [Turbine, 6 Oct 2026](https://www.turbinefi.com/blog/best-hyperliquid-trading-bots) [vendor]. **Gainium** offers a hybrid: a free mode with builder fees (0.045% on both futures sides) or paid plans ($15–$109/month) with no builder fee — [Turbine](https://www.turbinefi.com/blog/best-hyperliquid-trading-bots) [vendor]
- **Katoshi**: strategy marketplace where publishers "earn fees from every trade" — [Katoshi](https://katoshi.ai/) [marketing]. A third-party table says a subscription is required (unverified) — [coinlaunch.space listicle via search](https://coinlaunch.space/de/blog/best-hyperliquid-bots/) [affiliate]
- **MirrorTrade**: 1 bp per copied order, no subscription. It says it cannot raise its fee because builder-fee approval must be signed by the user's main wallet — [MirrorTrade](https://45-32-38-235.sslip.io/faq) [marketing]
- **BitMEX**: standard BitMEX trading fees plus "a profit share of **15% for all Hyperliquid Leaders**", charged only on net profit — [BitMEX support article](https://support.bitmex.com/hc/en-gb/articles/33677673599005-What-are-the-fees-to-copy-trade-Hyperliquid-Leaders) [primary; content seen via search snippet only, page was blocked to direct fetch]
- **Revenue comparisons** (see Q1 table): Hyperdash about $409k per 30d and $1.14M all-time; pvp.trade $8.01M all-time but about $8k per 30d now; HyperX $171.5k all-time; Dexly $134.6k; Katoshi $14.8k (all DL, 21 Oct 2026) — [DefiLlama API](https://api.llama.fi/overview/fees/Hyperliquid%20L1?dataType=dailyRevenue) [data]. Hyperdash's own article (undated, about Jan 2026) says "Phantom alone earns over $100,000 per day", and that PVP.trade earned $7.2M lifetime and "Neither launched a token. Neither charges subscription fees." — [Hyperdash Learn](https://hyperdash.com/learn/hyperliquid-builder-codes-explained-how-third-party-apps-earn-fees-on-chain) [primary/marketing]
- Becoming a builder requires holding 100 USDC in an HL perps account, with "no application process" — [Hyperdash Learn](https://hyperdash.com/learn/hyperliquid-builder-codes-explained-how-third-party-apps-earn-fees-on-chain) [primary]

### Inferences
- Copy trading is monetised as a **premium execution product**: Hyperdash charges copiers about 3.3x its normal builder fee and withholds rebates. Users accept this because the fee is small relative to the perceived edge, and it is approved once.
- Paying leaders works only with opt-in leaders: pvp.trade's username-based leaders, Katoshi's publishers, BitMEX's profit share. On HL, most "leaders" are unaware public wallets, so apps keep 100% of fees. A venue where leader accounts are less visible would push a product towards an opt-in leader marketplace with profit share.
- Lifetime value is concentrated in a few high-volume users: Insilico has about $1,100 revenue per user, Mass has the highest ARPU, Hyperdash reportedly about $386 per 30 days. Meanwhile, retail cohorts churn fast (see Q5). Fee ladders that reward volume (cashback, leverage discounts) are the main retention lever used.
- pvp.trade's "effective leverage discount" (up to −4 bps at 40x) rewards high leverage. It raises fee revenue per user but works against follower survival. This is a design to avoid if follower outcomes matter.

### Gaps
- Exact current builder-fee rates for HyperX, Dexly and Katoshi are unconfirmed; sources conflict.
- No product reports how much of its revenue comes from copy trading versus normal trading.
- Who receives BitMEX's 15% "leader" profit share is not stated, since HL leaders are not BitMEX users. I infer BitMEX keeps it, but this is unconfirmed.

---

## Q5. Known problems for followers and data on how followers perform

### Takeaway
No HL copy product publishes follower performance. The available evidence points to copier underperformance. A developer reports copies captured about half of the leader's edge, mostly lost on exits. A cross-exchange study found 97% of leaders profitable but only about 44% made money for copiers. Hyperdash's own research shows that fees, not trading, drove more than half of recent losses in retail HL app cohorts. The structural problems are taker-after-leader slippage, leader/follower bankroll mismatch, leaderboard survivorship bias, leaders who know they are watched, and fragile thin markets.

### Cited Findings
- **Fee drag on retail app users (Hyperdash research)**: about 400,000 wallets trading through Phantom, MetaMask, Rabby, Trust Wallet, Invo and fomo lost **$280M** cumulatively. Of **$126M lost since 10 Nov 2025, fees were "slightly more than half"**. All-in cost is 6.5–14.5 cents per $100 notional. Typical deposits are **$30–$60** on five of the six apps. **About 1 in 7 new traders is still active after three months.** Monthly active traders tripled from Nov 2025 to Sep 2026, and about half of each month's actives are new. Invo users deposited $12.4M but traded $5.8B. On BTC, fees exceeded realized gains. Rabby users had larger accounts and higher odds of profit — [KuCoin blog summarising research by Hyperdash co-founder Hanson Birringer, 20 Oct 2026](https://www.kucoin.com/blog/hyperliquid-retail-traders-280-million-losses) [media summarising primary research; not copy-trading-specific]
- **Copier vs leader outcomes**: "In a 90-day study across three exchanges covering more than 100,000 copier outcomes, 97% of the copy-trade leaders were profitable on their own books — but only about 44% of them produced positive PnL for the people copying them" (YieldFund). Leaders with a win rate above 57% could still hand copiers losses — [Bitsgap blog](https://bitsgap.com/blog/why-copying-on-chain-whale-trades-usually-backfires) [vendor, a competitor selling grid/DCA bots; secondhand study; not HL-specific]
- **Anecdote**: a copier mirrored a wallet with a 73% win rate and a six-month record and "was down 18% in three weeks on positions the original was still holding comfortably", because of an earlier entry and a larger bankroll — [Bitsgap, citing 0xIcaruss on Medium](https://bitsgap.com/blog/why-copying-on-chain-whale-trades-usually-backfires) [vendor; anecdote]
- **Copies earn about half the edge; exits matter more than entry lag**: [Cipher Intelligence summarising an r/algotrading thread, 21 Oct 2026](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [secondary]
- **Bankroll mismatch**: "a whale doing 20x with 0.5% of their book looks the same as you doing 20x with 30% of yours but it's not even close to the same trade" — [r/algotrading snapshot comment, 9 Apr 2026](https://reddit.sentinel-team.org/posts/1semsc5/snapshots/2026-04-09T18%3A02%3A40.74888Z) [user comment]
- **Leaders watch the copiers**: "Copied wallets are public; some large leaders know they are followed and trade around it". Followers fill "after the leader, usually as a taker at a worse price… On a leader who scalps for 0.1%, that gap is the whole edge" — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate; claim, no data]
- **Exit liquidity / whale behaviour**: in the March 2025 ETH whale episode that left HLP with about a $4M loss, "copy traders assumed that the whale must have had insider knowledge". Claims that the whale acted deliberately are unproven — [WisdomTree Prime](https://www.wisdomtreeprime.com/blog/the-great-whale-slap-how-a-whale-offloaded-4m-in-losses-to-hyperliquids-hlp-vault/) [media; seen via search snippet, page fetch failed]
- **Survivorship and wash/holder noise in leaderboards**: on 21 Oct 2026, "1 of the top 10 accounts by 30-day PnL (and 5 of the top 50) had traded nothing in 30 days", i.e. holders whose token balance rose. Failed vaults "disappear from the list" — [Cipher Intelligence](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/) [vendor/affiliate, own check]. Leaderboards "show the wallets that survived, not the ones that blew up trying the same thing" — [Bitsgap](https://bitsgap.com/blog/why-copying-on-chain-whale-trades-usually-backfires) [vendor]
- **Market-structure fragility**: on 28 May 2026 the HL SPACEX-USDH (HIP-3) perp fell about 45% in about 30 minutes because of an oracle error after a stock split. 405 traders were liquidated across 1,393 positions, about $1.51M — [Bitsgap](https://bitsgap.com/blog/why-copying-on-chain-whale-trades-usually-backfires) [vendor, citing KuCoin, Sandmark and Ventuals]
- **Famous wallets blow up**: "Crypto Trader Machi Fully Liquidated Again, Erasing Year-Long Hyperliquid Profits" — [Phemex News headline, 18 Oct 2026](https://phemex.com/news/article/pvptrade-acquires-hyperdash-unveils-enhanced-v2-version-37252) [media headline only, listed on that page]
- **Product-side mitigations seen**: Hyperdash warns when copying traders tagged "algorithmic", offers max worse entry, new-positions-only, leverage caps, and logs skipped trades — [Hyperdash docs](https://docs.hyperdash.com/copy-trade). Dexly offers a drawdown pause — [Cipher](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/). HL's $10 minimum order means small copy accounts skip the leader's small trades and "your book drifts from the leader's" — [Cipher](https://cipher-intelligence.io/blog/hyperliquid-copy-trading/)

### Inferences
- On HL, copy trading suffers from the same fee-plus-churn economics Hyperdash measured in retail app cohorts. With a 5 bps copy fee plus a 4.5 bps taker fee on each side (about 19 bps per round trip), any leader with a short holding period or small average gain per trade is uncopyable. Products that filter or flag high-turnover leaders, and rank by realized PnL net of copy costs, would improve follower outcomes.
- Countertrade features and "copy scores" are partly a response to evidence that following top-PnL wallets does not transfer profits. A leaderboard ranked by **copier-realized** PnL, rather than leader PnL, would be a differentiator. No HL product appears to offer this.
- I found no quantitative evidence of systematic front-running of copiers on HL, only claims and anecdotes. Because all HL account data is public, front-running copy flow is plausible: a leader, or a bot watching a leader with known heavy followers, could trade ahead of the copy wave. It is undocumented.

### Gaps
- I found no published dataset of realized copier PnL for any HL copy product (Hyperdash, pvp.trade, HyperX, Dexly, BitMEX).
- I found no study of wash-traded leader statistics on HL leaderboards specifically. HL's leaderboard ROI definition (PnL divided by the larger of $100 and starting value plus max net deposits) reduces deposit inflation, but I found no wash-trading analysis.
- The YieldFund study's methodology and venues are unknown; it is reported secondhand by a competitor.
