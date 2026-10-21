# Binance Copy Trading (Futures and Spot), with a benchmark against Bitget, Bybit and OKX: mechanics, architecture and business model

Research date: 2026-10-21. Method note: Binance support pages are rendered by JavaScript and blocked for plain fetches, so the page text and the "last updated" timestamps below were read from Binance's public CMS endpoint (`/bapi/composite/v1/public/cms/article/detail/query?articleCode=...`). That endpoint returns the same article body as the linked support URL. Every Binance FAQ citation is tagged with its first-publish date and its last-update date, both in UTC. Any figure from before 2026 is marked as older.

---

## 1. Binance Futures and Spot copy trading mechanics (lead requirements, portfolio types, caps, copy modes, copier settings, order replication, lifecycle)

### Takeaway
Binance runs copy trading as a set of isolated "portfolio" accounts. A lead portfolio is a separate lead-trading account, described as a "separate sub-account". Each copier gets an isolated copy portfolio per leader. The engine mirrors each lead order into every copy portfolio. A lead taker order is mirrored right away as an IOC limit order capped by the copier's slippage setting. A lead maker order is mirrored only once it is fully filled. All closes are mirrored as market orders. Sizing uses a fixed ratio or a fixed amount, with depth, notional and leverage caps on top. The hard limits are numerous and specific: lead stake of 500 USDT or more, 200 to 1,000 copy slots, copy amounts from 10 to 300,000 USDT, and a fixed-leverage option capped at 10x for copiers.

### Cited Findings

**Product scope and dates**
- Futures copy trading FAQ first published 2023-08-22. The Spot copy trading FAQs were first published 2024-04-19, and the official "Binance Launches Spot Copy Trading" announcement is dated 2024-05-15 (older info). — [Binance announcement, 2024-05-15](https://www.binance.com/en/support/announcement/binance-launches-spot-copy-trading-cf333f9ad25a4a55be0fdcdb748852bd)
- Futures copy trading supports "400+ USDⓈ-M Futures contracts". Only USDT contracts are supported, so all fees are in USDT. Multi-Assets mode is not supported. The FAQ also mentions a "TradFi" tag for leaders who traded TradFi contracts in the past 7 days. — [Binance Futures Copy Trading FAQ, updated 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d); [Binance Copy Trading Rules, updated 2026-09-10](https://www.binance.com/en/support/faq/binance-copy-trading-rules-30f1e3a2835345e0b8ffc87f261a8256)
- Spot copy trading supports "more than 100 pairs". — [Binance Spot Copy Trading FAQ, updated 2026-09-03](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-spot-copy-trading-1826c3b426a149949851554bdde227d3)
- A third model, "Smart Money Signal Copy Trading", was launched in 2026 (FAQ published 2026-07-08). Here the leader does not create a separate portfolio. The system watches the leader's master Futures account and broadcasts all USDT-M perpetual trades to copiers. Phase 1 is open to invited top traders only and requires 500 USDT or more in the master Futures account. COIN-M contracts are not copied. Portfolio Margin and Multi-Assets modes are excluded. — [Binance Smart Money Signal Copy Trading FAQ, published 2026-07-08, updated 2026-07-14](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)

**Account architecture**
- "Traditional Copy Trading: The lead trader needs to create a lead portfolio as a separate sub-account." — [Binance Smart Money Signal FAQ, 2026-07-14](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)
- The Copy Trading Account is independent from the Binance Futures Account. Copy trading is not supported for user sub-accounts, which can neither copy nor lead. — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d)
- On Spot, lead assets are moved to a Spot Copy Trading Account "to prevent the assets from being withdrawn, transferred out, or used for other trading operations". Assets cannot be withdrawn from it directly. Spot and Futures copy assets are not shared. — [Spot Lead Trader Guide, updated 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa); [Spot FAQ, 2026-09-03](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-spot-copy-trading-1826c3b426a149949851554bdde227d3)
- When a Spot copier stops, the system sells all tokens to USDT and returns them to the Spot Account. Balances under 10 USDT are returned in the original token. Low-liquidity tokens can delay withdrawal. — [Spot FAQ, 2026-09-03](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-spot-copy-trading-1826c3b426a149949851554bdde227d3)

**Lead trader requirements and portfolio types**
- Futures: the user applies via [Futures] - [Copy Trading] - [Apply Now] and picks a Public portfolio (anyone can copy) or a Private portfolio (copy by invite code or link only). The minimum lead trading amount is 500 USDT. Funds move from the Spot Account to the Lead Trading Account. The maximum transferable amount is the available balance minus 500 USDT. A user must agree to a service agreement. No track record is required to open a "Regular" portfolio; track-record thresholds only gate badges (see the Growth Plan in section 2). — [How to Lead Trade on Binance Futures, updated 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- Conflict: a search-engine snippet of the same "How to Lead Trade" page showed "minimum 1,000 USDT". The current text (updated 2026-10-01) says 500 USDT, which suggests the threshold was lowered at some point. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- A user can run 1 public lead portfolio, 1 private lead portfolio and up to 20 copy portfolios at the same time (Futures). — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d)
- Spot: a "verified Binance Account" is required, and the lead portfolio must hold between 500 and 1,000,000 USDT. The guide allows 1 public lead account, 1 private lead account and 10 copy accounts, while the Spot FAQ says "one Lead Trading Portfolio and up to 10 Copy Trading Portfolios". Spot copy trading is "only available to users who have completed identity verification with proof of address and are from eligible regions". — [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa); [Spot FAQ, 2026-09-03](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-spot-copy-trading-1826c3b426a149949851554bdde227d3)
- At the April 2024 launch (older info), a Binance spokesperson told The Block the Spot lead portfolio range was about 500 to 250,000 USDT. The maximum is now 1,000,000 USDT. — [The Block, 2024-04-23 (search snippet)](https://www.theblock.co/post/290345/binance-spot-copy-trading)

**Copy slots (maximum copiers per portfolio)**
- Futures public portfolios start with 200 slots and gain 100 more each time the portfolio is full, up to 800. More than 800 needs manual approval; the Legend badge range is 800 to 1,000. Private portfolios can be set up to 1,000 slots "without limitation". — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c); [Lead Trader Growth Plan, updated 2026-10-01](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)
- Smart Money Signal portfolios have 500 slots by default, and leaders can apply via a survey to raise that. — [Signal FAQ, 2026-07-14](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)
- Spot portfolios start at 300 copiers. The Spot Elite tiers are set by copier count: Cadet 300, Champion 500, Master 800, Legend 1,000 to 2,000. — [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa); [Spot Elite Trader Program Guide, updated 2026-08-18](https://www.binance.com/en/support/faq/binance-spot-copy-trading-elite-trader-program-guide-2fc0125418c94bfcbefc8f9b4fe5aa72)

**Copy modes and copier settings (Futures)**
- Fixed Amount uses a fixed margin cost per trade, adjustable from 10 to 50,000 USDT. Fixed Ratio has the copier set a total investment, and the system sizes each copy in proportion to the leader's order. The total copy amount ranges from 10 to 300,000 USDT. The default minimum copy amount is 10 USDT; leaders with badges can raise it, and private portfolios can raise it up to 50,000 USDT. — [How to Use Copy Trading on Binance Futures, updated 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206); [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- Copier settings include:
  - existing-position mode: copy all at market, "copy better entries" only, or new positions only
  - Auto-Invest top-ups (daily, 7, 14 or 30 days)
  - a symbol whitelist (low-liquidity symbols are removed by default when portfolio AUM is above 250,000 USDT)
  - margin mode: follow the leader, or fixed Cross/Isolated
  - leverage: follow the leader, or fixed 1x to 10x
  - maximum entry slippage from 0.1% to 3%, defaulting to 0.5% for BTCUSDT and ETHUSDT and 1.5% for other pairs; it applies to opens only, not closes
  - per-position TP/SL, with trigger = entry × (1 + ROI/leverage), applied to new positions only
  - maximum cost per order
  - a portfolio-level stop loss in USDT or %
  - "Close All Positions on Stop", or a "Self Managing" mode that keeps positions open and ends the leader relationship

  — [How to Use Copy Trading on Binance Futures, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206)
- Leaders can enable "Forced Sync", which pushes the leader's copy settings to all followers. The total stop loss is never synced. Sync can be changed up to 2 times a day, new orders are blocked for 30 seconds after each change, and followers are emailed. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- Copiers can Pause, which stops new copies while existing positions keep following the leader's closes. Pause is not supported for Signal Copy Phase 1. — [How to Use Copy Trading, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206); [Signal FAQ, 2026-07-14](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)

**Order replication (execution engine)**
- Futures opens: a lead taker order (Market or Stop Market) is copied immediately as an IOC limit order with the limit at the slippage cap or floor. A lead maker order (Limit or Stop Limit) is copied only once fully filled, also as an IOC limit order. Closes: taker closes are copied immediately as Market orders, and maker closes are copied once fully filled, as Market orders. The leader cannot trade for 5 seconds after changing margin mode. — [Copy Trading Rules, 2026-09-10](https://www.binance.com/en/support/faq/binance-copy-trading-rules-30f1e3a2835345e0b8ffc87f261a8256)
- Fixed Ratio sizing works as follows. Copy order cost = min(amount ratio × copier margin balance, discount coefficient × copier available balance). Amount ratio = min(Lead Order Cost / Lead Margin Balance, 1), also capped by a max position rate. Discount coefficient = {(1−S)/(1−S+L·S)} × 0.98, where S is the max entry slippage and L is the leverage; for example, it equals 0.813 at 1% slippage and 20x. Partial closes are mirrored proportionally: a leader closing 20% closes 20% for every copier. — [Copy Trading Rules, 2026-09-10](https://www.binance.com/en/support/faq/binance-copy-trading-rules-30f1e3a2835345e0b8ffc87f261a8256)
- Size adjustments and caps:
  - If a computed open is below the minimum trade amount, the Futures engine opens at the minimum trade amount, so the copy can be larger than intended.
  - If it exceeds the maximum for the chosen leverage, it opens at that maximum.
  - Once the copy ratio reaches 80% of margin, a 0.97 coefficient is applied.
  - The copy amount is capped at 80% of the contract's market depth.
  - IOC partial fills shrink the position.

  Spot works differently: below-minimum buys are not placed at all. — [Copy Trading Rules, 2026-09-10](https://www.binance.com/en/support/faq/binance-copy-trading-rules-30f1e3a2835345e0b8ffc87f261a8256); [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa)
- The listed copy failure reasons are:
  - insufficient margin
  - a lead limit order not fully filled
  - slippage beyond the cap
  - notional below the symbol minimum
  - leverage mismatch when the copier follows the leader's leverage
  - the combined leader-plus-copier position hitting the Max Position Limit or the dynamic symbol limit

  — [Copy Trading Rules, 2026-09-10](https://www.binance.com/en/support/faq/binance-copy-trading-rules-30f1e3a2835345e0b8ffc87f261a8256); [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d)
- Capacity limits on leaders: the portfolio notional cap = min(max notional 1 from the trading-rules table, (0.8/leverage) × depth). Leverage on low-liquidity symbols is capped at 5x. Once leader plus copiers reach the Max Position Limit for a contract, the leader cannot add to it. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- Spot replication uses the same taker/maker trigger logic. Buys go out as IOC limit orders with default slippage caps of 0.3% for BTC/USDT and ETH/USDT and 0.5% for other pairs (customisable up to 3%), and sells go out as market orders. If too many copiers would breach the dynamic maximum size for a symbol, the system reallocates the copy amounts across all copiers. — [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa); [Spot Copier Guide, updated 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-copy-trader-abc27f5949cf46d9801d31b5e33d0b38)

**Lifecycle: what happens when the leader closes or stops**
- A Futures leader cannot close a portfolio that has open positions. When the leader closes it, followers automatically stop copying and profit share is settled. A 72-hour cooling-off period applies if the portfolio is closed within 7 days with a negative total PnL. If that is triggered twice, the leader cannot open a new portfolio until next month. Leaders can remove a copier only when the copier has no open positions. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- Signal Copy: if the leader turns signals off, all copier positions are closed at market immediately, profit share is settled and the copy portfolios are closed. A 24-hour cooldown follows, with at most 2 activations per month. Reopening creates a new portfolio with recalculated data, so the track record resets. — [Signal FAQ, 2026-07-14](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)
- The system closes a lead portfolio 2 days after liquidation if its balance stays at 0. A copy portfolio is auto-closed if its margin falls below the minimum copy amount and it fails 5 consecutive copies; Futures checks this daily and Spot checks it every Friday. — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d); [Spot Copier Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-copy-trader-abc27f5949cf46d9801d31b5e33d0b38)
- Lock-up: once a public portfolio fills 200 slots, the leader can set a 7D, 14D or 30D lock-up. Copiers must then set a portfolio stop loss and cannot stop copying, change the stop loss or transfer out during the lock-up. Each user has one "unlock option", which renews 30 days after use. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c); [How to Use Copy Trading, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206)
- The copier dashboard tracks Net Copy Amount (initial + transfers in − transfers out − profit shared), Margin Balance, Realized PnL (net of trading, funding and insurance-clearance fees), Unrealized PnL, Profit Shared and Net Profit. — [How to Use Copy Trading, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206)

### Inferences
- Binance's architecture amounts to a per-relationship isolated account (one copy portfolio per copier per leader), and each mirrored order is a real separate order on the central limit order book, not an internal allocation. The evidence is the per-copier IOC orders, the per-copier failure reasons and the "reallocate across copiers" logic. A copy product built on a DEX order book that places one order per follower account would face the same fan-out, slippage and depth-capacity problems. Binance's specific mitigations are worth copying: an IOC with a slippage cap on entries, unprotected market exits, a combined leader-plus-copier notional cap tied to depth, and auto-closing persistently failing copy portfolios.
- Copying a maker order only once it is fully filled means copiers always enter after the leader at a taker price. This is a structural source of the leader-versus-copier PnL gap (see section 5).
- Signal Copy, which copies the master account with no separate stake, shows Binance moving toward lower-friction leader onboarding. Leaders keep their own account, which matters for terminal-style products where leaders do not want to move funds into a dedicated vault or sub-account.

### Gaps
- No published copy latency (milliseconds between a lead fill and copier order placement) and no description of order sequencing across hundreds of copiers (for example, whether copier orders are randomised or batched).
- The official Binance list of supported or restricted countries for copy trading could not be retrieved; the "Service List" FAQ code returned no content.
- The "Smart Filter" ranking algorithm is described only as identifying "top traders with superior trading skills, high profits, and low drawdowns", and its formula is not published.

---

## 2. Money flows: profit share, settlement, what Binance earns, lead rebates, referral programs

### Takeaway
On Binance Futures, the leader takes a profit share of 0 to 30%. Public portfolios default to 10% and unlock 15%, 20% and 30% through performance or AUM badges; private portfolios can be set up to 30%. Settlement is weekly on Mondays, computed on cumulative total PnL (realized plus unrealized since 2024-09-23) against what has already been paid, which works like a cumulative high-water mark. Leaders also get 10% of their copiers' trading fees, capped at 0.3% of copier margin per week. Binance keeps the trading fees net of that rebate and of referral or affiliate payouts. No platform cut of profit share is documented. Spot pays 10% profit share (up to 30% for Elite tiers based on copier count), settled on realized profit only.

### Cited Findings

**Profit share: rates and controls**
- Futures leaders "can receive up to 30% profit share from their copy traders. The remaining profit goes to their copy traders", plus a 10% commission on copiers' trading fees. — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d); [Lead Trader Benefits, updated 2026-09-22](https://www.binance.com/en/support/faq/lead-trader-benefits-in-binance-futures-copy-trading-ea9bacf82b9e4ddfae50ebc98565241b)
- Public portfolios default to 10% and can be adjusted within a range set by badge. Private portfolios can be set up to 30%. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- The Futures Lead Trader Growth Plan (first published 2023-11-07, updated 2026-10-01) sets the following badge criteria and benefits. Badges are evaluated daily, move up or down one tier at a time, must be held 7 days before the next change, and apply to public and signal portfolios but not private ones. The profit share ratio can be changed at most twice a week. — [Growth Plan, 2026-10-01](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)

| Badge | Margin balance (USDT) | 7D copier PnL (USDT) | Copiers | Run time | 30D avg AUM (USDT) | 30D trading days | 7D MDD max | Slots | Min copy amount range (USDT) | Profit share |
|---|---|---|---|---|---|---|---|---|---|---|
| Regular | ≥500 | - | - | - | - | - | - | 200 | 10-200 | 0-10% |
| Cadet | ≥1,000 | ≥50 | ≥200 | ≥15d | ≥10,000 | ≥5 | 50% | 200-400 | 10-1,000 | 0-15% |
| Champion | ≥5,000 | ≥1,000 | ≥400 | ≥30d | ≥100,000 | ≥5 | 35% | 400-600 | 10-5,000 | 0-20% |
| Master | ≥10,000 | ≥2,000 | ≥600 | ≥30d | ≥500,000 | ≥10 | 35% | 600-800 | 10-10,000 | 0-30% |
| Legend | ≥20,000 | ≥10,000 | ≥800 | ≥30d | ≥3,000,000 | ≥10 | 35% | 800-1,000 | 10-20,000 | 0-30% |

- Smart Money Signal leaders get the same terms: "up to 30% profit share and 10% commission rebate", with profit sharing "consistent with traditional copy trading". — [Signal FAQ, 2026-07-14](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)
- Spot: the standard rate is 10% profit share (90% to the copier) plus a 10% fee commission. These were the launch terms (2024-05-15, older) and are still current in the Spot FAQ (2026-09-03). Spot Elite tiers unlock up to 12% (Cadet, 300+ copiers), 15% (Champion, 500+), 20% (Master, 800+) and 30% (Legend, 1,000 to 2,000), with weekly reviews. Spot private portfolios also allow a custom profit share. — [Spot FAQ, 2026-09-03](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-spot-copy-trading-1826c3b426a149949851554bdde227d3); [Spot Elite Trader Program Guide, 2026-08-18](https://www.binance.com/en/support/faq/binance-spot-copy-trading-elite-trader-program-guide-2fc0125418c94bfcbefc8f9b4fe5aa72); [Spot launch announcement, 2024-05-15](https://www.binance.com/en/support/announcement/binance-launches-spot-copy-trading-cf333f9ad25a4a55be0fdcdb748852bd)

**Profit share: settlement mechanics (high-water-mark style)**
- Futures: "The weekly profit share mechanism has been updated since 2024-09-23, it will be settled based on portfolio Total PNL instead of realized PNL." Snapshots of each copy portfolio's Total PnL are taken every Monday from 00:00 UTC, and profits are paid to the leader's Spot Account on Mondays. — [Lead Trader Benefits, 2026-09-22](https://www.binance.com/en/support/faq/lead-trader-benefits-in-binance-futures-copy-trading-ea9bacf82b9e4ddfae50ebc98565241b)
- Futures formula: Profit to be settled = max[(total realized profit + unrealized PnL of the copy portfolio) × profit share % − shared profit, 0]. Total PnL is after all fees.
  - Binance's worked example at 10%: Week 1 at +200 pays 20. Week 2 at a cumulative +50 pays 0. Week 3 at a cumulative +150 pays 0. Week 4 at a cumulative +300 pays 10.
  - Losses therefore have to be recovered before new profit share is due. There are no clawbacks: shared profit is never refunded.

  — [Lead Trader Benefits, 2026-09-22](https://www.binance.com/en/support/faq/lead-trader-benefits-in-binance-futures-copy-trading-ea9bacf82b9e4ddfae50ebc98565241b)
- Settlement is also triggered off-cycle when a copier stops copying, the leader closes the portfolio, or a copier withdraws profits. Switching to "Self Managing" also settles at that moment. A newly copied portfolio "may pay a profit share on Mondays if copied before the profit share calculation period". — [Lead Trader Benefits, 2026-09-22](https://www.binance.com/en/support/faq/lead-trader-benefits-in-binance-futures-copy-trading-ea9bacf82b9e4ddfae50ebc98565241b); [How to Use Copy Trading, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206)
- The copier's withdrawable amount excludes the accrued profit share: the maximum transferable is available balance − minimum copy amount − profit share amount. — [How to Use Copy Trading, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206)
- Spot settles on realized profit only, with the same cumulative "minus shared profit" logic. The cycle runs Monday 00:00 UTC to Sunday 23:59:59 UTC, and settlement happens only "when there are no open orders in the copying portfolios". — [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa)

**Trading-fee commission to leaders (Binance-funded rebate)**
- Leaders receive a "10% weekly commission from their active copy portfolios on Mondays". It is capped at min[total trading fee × 10%, copy portfolio margin balance × 3% × 10%], with margin snapshots at 00:00 UTC Mondays. The payout appears in Transaction History as "Distribution" with a note referencing the "Copy Trading Referral Program". — [Lead Trader Benefits, 2026-09-22](https://www.binance.com/en/support/faq/lead-trader-benefits-in-binance-futures-copy-trading-ea9bacf82b9e4ddfae50ebc98565241b); [Growth Plan, 2026-10-01](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)

**What Binance earns**
- Copier and leader trades pay the standard fee rate for the account's VIP level. Futures leaders can pay fees in BNB for a discount. On Spot copy trading, "BNB cannot be used for trading fee deduction" and "trading fee rebate vouchers are not supported", while referral fees are supported. — [Copy Trading Rules, 2026-09-10](https://www.binance.com/en/support/faq/binance-copy-trading-rules-30f1e3a2835345e0b8ffc87f261a8256); [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa)
- Copy and lead trading volume counts toward the Binance VIP program, and lead trading volume counts as the leader's USDⓈ-M Futures volume. — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d); [Growth Plan, 2026-10-01](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)

**Referral and affiliate overlay**
- A user's inviter earns the normal referral commission on that user's lead or copy trading fees. Spot states that the 10% profit share and 10% commission "will not affect the original referral fee structure". — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d); [Spot FAQ, 2026-09-03](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-spot-copy-trading-1826c3b426a149949851554bdde227d3)
- Binance Affiliates get "Up to 50% commission generated on referees' copy trading volume", and this is listed as a standard lead trader benefit. — [Growth Plan, 2026-10-01](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)
- Spot leaders can "unlock extra rewards from ongoing campaigns". — [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa)

### Inferences
- There is no evidence that Binance takes a cut of the profit share. Every document describes the profit share as a split between copier and leader ("the remaining profit goes to their copy traders"). Binance's revenue is therefore the trading fees on copier volume (opens, closes, and fee-heavy taker exits through market orders) minus the 10% leader rebate, minus referral or affiliate commission. Copy trading is a volume-acquisition channel, not a direct revenue line.
- The rebate cap of 3% × 10% of copier margin per week equals at most 0.3% of copier margin per week (about 15.6% a year). It stops leaders from earning large rebates by churning small copier balances, which ties leader income to AUM rather than turnover. Binance's own example uses 10%.
- The Growth Plan is the main incentive lever: higher profit share (10% to 30%), more slots and larger minimum copy amounts are unlocked only with copier PnL, AUM, run time and drawdown limits. This simultaneously rewards leaders who make copiers money, filters out small-balance ROI spikes (margin and AUM floors, MDD caps), and gives Binance a discretionary dial ("sole and absolute discretion").
- The 2024-09-23 switch from realized to total PnL (including unrealized) closed a gaming vector. Under realized PnL, a leader could take profit share on realized winners while leaving losers open; total PnL removes that.
- For Mirrorlane, the Binance template is: default 10%, a tiered unlock to 30%, a cumulative high-water mark, weekly settlement plus settlement on exit, and the platform funding a capped fee rebate to leaders out of trading fees. If Mirrorlane's own fee take on Lighter is thin, the fee-rebate lever may not be fundable. A platform cut of profit share, which Binance does not take, may then be the more natural revenue line.

### Gaps
- No published total of profit share or fee commission paid to leaders, and no breakdown of Binance's copy-trading revenue.
- Whether Binance's "Max Position Limit" or copy slots are ever monetized (for example, paid slots) is not documented; there is no evidence they are.
- The full referral percentages for copy trading volume outside the affiliate program ("up to 50%") were not retrieved.

---

## 3. Lead Trader API / copy-trading API for programmatic leaders

### Takeaway
Binance supports programmatic lead trading, but only through standard USDⓈ-M Futures endpoints called with a dedicated per-portfolio API key: up to 2 keys per lead portfolio, IP whitelist, USDT only, 20 orders per 10 seconds. The separate "Copy Trading API" namespace has just two read endpoints, lead trader status and the symbol whitelist. There is no documented API for copiers (no programmatic follow, unfollow or allocation) and no public leaderboard API.

### Cited Findings
- Lead traders can create up to two API keys per Futures lead portfolio from [My Lead] - [API], with "Restrict access to trusted IPs only" and "Enable Futures". The key works only for Futures trading, supports USDT only, cannot be used with Multi-Assets Mode, and is deleted automatically when the lead portfolio closes. "The Lead Trader API order rate limit is 20 requests per 10 seconds." Portfolios trading via API show an "API" tag. — [How to Create an API Key for a Futures Lead Trading Portfolio, first published 2023-11-14, updated 2026-02-27](https://www.binance.com/en/support/faq/2bec848b904b422197ce121d0925f20b); [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d)
- The copy-trading API changelog lists two endpoints added 2024-06-06: `GET /sapi/v1/copyTrading/futures/userStatus` (Futures lead trader status) and `GET /sapi/v1/copyTrading/futures/leadSymbol` (lead trading symbol whitelist). — [Binance Copy Trading API change log (search snippet)](https://developers.binance.com/en/docs/products/copy-trading/change-log)
- Binance's official auto-generated JS SDK `@binance/copy-trading` exposes only `getFuturesLeadTraderStatus` (weight(IP) 1, TRADE) and `getFuturesLeadTradingSymbolWhitelist` (weight(IP) 1, USER_DATA). The SDK describes its purpose as "Automate lead trading via the Copy Trading API". The latest version is 4.0.7 (2026-10-19), and the changelog since 2026 shows only dependency updates. A Python SDK `binance-sdk-copy-trading` covers `/sapi/v1/copyTrading/*`. — [binance-connector-js copy-trading rest-api.ts](https://github.com/binance/binance-connector-js/blob/master/clients/copy-trading/src/rest-api/rest-api.ts); [CHANGELOG](https://github.com/binance/binance-connector-js/blob/master/clients/copy-trading/CHANGELOG.md); [binance-connector-python copy_trading README](https://github.com/binance/binance-connector-python/blob/master/clients/copy_trading/README.md)
- Spot Elite tiers list "API Rate Limit: Modify the number of orders supported per second" as a benefit, so higher tiers get higher Spot API throughput. — [Spot Elite Trader Program Guide, 2026-08-18](https://www.binance.com/en/support/faq/binance-spot-copy-trading-elite-trader-program-guide-2fc0125418c94bfcbefc8f9b4fe5aa72)
- Copiers can filter portfolios to show or hide "API" portfolios. — [How to Use Copy Trading, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206)

### Inferences
- Binance treats API-driven leaders, that is bots and quant strategies, as first-class leaders but flags them, so copiers can choose to avoid them. The 20 per 10 seconds order limit is far below normal Futures limits, which keeps leader order rates compatible with fan-out to hundreds of copiers.
- The absence of a copier-side API or a leaderboard API means third parties cannot build on Binance's copy graph. This is an opening for a DEX terminal, where on-chain account histories make leader performance independently verifiable.

### Gaps
- The full parameter and response schema of the two `/sapi/v1/copyTrading/futures/*` endpoints could not be read, because developers.binance.com was blocked by a bot challenge. Only the names and weights were confirmed via the SDK.
- No documentation was found of a Spot lead-trading API key product equivalent to the Futures one.

---

## 4. Traction: lead portfolios, copiers, AUM or volume

### Takeaway
Binance publishes no official copy-trading traction figures. Its 2025 Year in Review (300M+ users) does not mention copy trading at all, but it does cite 1.2M Smart Money subscribers. Copier and leader counts circulating in reviews are unsourced and inconsistent, so treat them as marketing-grade at best. Indirect scale signals come from Binance's own rules: 400+ copyable contracts, Legend-tier thresholds of 3M USDT 30-day AUM per portfolio, and default slot ceilings of 800 to 1,000.

### Cited Findings
- Binance's "State of the Blockchain: 2025 Year in Review" cites 300 million users and says "More than 1.2 million users subscribed to Smart Money in 2025". A text search of the report found no mention of copy trading, lead traders or copiers. — [Binance 2025 EOY Report (PDF)](https://public.bnbstatic.com/reports/2025_EOY_Report.pdf)
- Scale indicators in the rules: Futures copy trading covers 400+ USDⓈ-M contracts (FAQ updated 2026-07-16). The Legend badge requires 30-day average AUM of at least 3,000,000 USDT and 800 or more copiers. Private portfolios can hold 1,000 slots, and Spot Legend 1,000 to 2,000 copiers. — [Futures FAQ](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d); [Growth Plan](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb); [Spot Elite Guide](https://www.binance.com/en/support/faq/binance-spot-copy-trading-elite-trader-program-guide-2fc0125418c94bfcbefc8f9b4fe5aa72)
- Third-party sample (vendor study, published November 2025, data from October 2025): across Binance, Bybit and MEXC, YieldFund analyzed 100,236 copier outcomes. Aggregate Binance follower PnL in the sample was +572,979.94 USDT, against +346,106.01 USDT for Bybit and −210,040.51 USDT for MEXC. This is a sample, not platform totals. — [YieldFund, "Is Copy Trading Profitable? A 90-Day, Multi-Exchange Study"](https://www.yieldfund.com/news/is-copy-trading-profitable-a-90-day-multi-exchange-study)
- A 2026 Coin Bureau review notes, as of 2026-10-14, that Binance offers separate spot and futures copy portfolios with their own rules (search snippet; no traction figures given). — [Coin Bureau, Binance Copy Trading Review](https://coinbureau.com/review/binance-copy-trading-review)

### Inferences
- Binance's silence on copy-trading KPIs, while it promotes Smart Money (1.2M) and Demo Trading (300k), suggests copy trading is not a headline growth metric for Binance, unlike Bitget, which brands itself around copy trading.
- For Mirrorlane's positioning, copiers per leader matter more than total users. Binance's tier thresholds imply that a top public portfolio holds on the order of hundreds to about 1,000 copiers and single-digit millions of USDT AUM.

### Gaps
- No verified count of Binance lead portfolios, copiers, copy AUM or copy volume. Search surfaced third-party claims of roughly "200,000 lead traders / 2 million copiers" and "2,300+ spot traders to copy" (June 2026), but the originating pages and Binance sources could not be confirmed, so they are excluded as unverified.
- No Kaiko, CoinGecko or The Block research quantifying CEX copy-trading market size was found in this pass.

---

## 5. Risk controls and failures: manipulation, copier losses, policy changes, delisting, regional availability

### Takeaway
Binance's anti-gaming controls are rule-based. They include badge thresholds with copier-PnL, AUM, run-time and MDD floors; leverage and notional caps tied to depth; cooling-off periods after closing a losing new portfolio; hiding imitators and leaders who steer copiers off-platform or promise returns; revoking benefits for "malicious behaviour"; settlement on total PnL rather than realized PnL; and time-weighted ROI. Independent evidence still shows a large leader-versus-copier gap: in a 2025 vendor sample, 97% of leaders were profitable on their own PnL but only 44% made their followers money. Binance has blocked copy trading in the EEA since June 2024 and says availability varies by country, with Spot requiring proof of address.

### Cited Findings

**Anti-gaming and quality controls (Binance)**
- Public portfolios cannot imitate the nickname, description or strategy of portfolios with 200 or more copiers; imitators are hidden. Portfolios may be "taken offline, put into cooling-off and restricted to advanced benefits" for abnormal behaviour. Examples are directing traffic to outside platforms and "any form of guarantee or promise regarding risk free copy trading". Private portfolios may not show invite codes in their nickname or description. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- "If any malicious behaviour is detected, all benefits will be revoked. This includes, but is not limited to historical closed portfolios, fund transfer frequency, carrying order, etc." Binance measures all metrics "at its sole and absolute discretion" and may amend or cancel the program "without prior notice". — [Growth Plan, 2026-10-01](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)
- A 72-hour cooling-off period applies after closing a portfolio within 7 days with negative PnL. A second trigger blocks new portfolios until the next month. This counters the "spin up a new portfolio until one gets lucky" pattern. — [How to Lead Trade, 2026-10-01](https://www.binance.com/en/support/faq/how-to-lead-trade-on-binance-futures-6acfb4c1f50c4db1b9e915181ff31a4c)
- Risk tags: "high leverage" (max leverage at or above 20x in the past 7 days), "10x-20x leverage", "API" and "TradFi". — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d)
- Low-liquidity symbols are defined two ways:
  - The FAQ: notional at 3% order-book depth stays below 500,000 USDT over the past 14 days, based on hourly snapshots.
  - The leader guide and Rules: market cap ≤ 50,000,000 and 5% depth ≤ 250,000. Leverage on these symbols is capped at 5x.

  The two definitions are inconsistent across Binance pages. — [Futures FAQ, 2026-07-16](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-futures-copy-trading-6ed0995daf0b42d5816beaf1e31ca09d); [Copy Trading Rules, 2026-09-10](https://www.binance.com/en/support/faq/binance-copy-trading-rules-30f1e3a2835345e0b8ffc87f261a8256)
- Spot ROI uses a NAV (unit-value) method so deposits and withdrawals do not distort ROI. In the example, a −100 loss on 500 followed by a 1,000 deposit and +150 gives an ROI of −11.4%, not a positive figure. — [Spot Lead Trader Guide, 2026-08-25](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa)
- Copier-side safeguards: the slippage cap applies to entries only (exits are unprotected market orders). There is a portfolio stop loss, which Binance warns may still end in liquidation and the loss of all margin in extreme markets. Lock-ups force a stop loss. The copier is told "the lead trader may add margin to their positions, which could expose your positions to higher risks". — [How to Use Copy Trading, 2026-10-21](https://www.binance.com/en/support/faq/how-to-use-copy-trading-on-binance-futures-0b3a91eea664402f812fe41358c8a206)
- Policy change history (Binance):
  - 2024-09-23: profit share moved from realized to total PnL. — [Lead Trader Benefits](https://www.binance.com/en/support/faq/lead-trader-benefits-in-binance-futures-copy-trading-ea9bacf82b9e4ddfae50ebc98565241b)
  - The Growth Plan was "upgraded" (first published 2023-11-07). — [Growth Plan](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)
  - The Spot portfolio maximum rose from about 250,000 USDT at launch (2024) to 1,000,000 USDT. — [The Block 2024 (snippet)](https://www.theblock.co/post/290345/binance-spot-copy-trading); [Spot Lead Guide 2026](https://www.binance.com/en/support/faq/binance-spot-copy-trading-guide-lead-traders-b9e5e3b2141149be826685d2c88536fa)
  - Signal Copy Trading launched July 2026. — [Signal FAQ](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)

**Copier outcomes and manipulation evidence (independent and academic)**
- YieldFund's 90-day study covered Binance, Bybit and MEXC, with data from October 2025, published November 2025, and the authors are a vendor:
  - Only 48.48% of 100,236 copier outcomes were profitable.
  - 97.04% of leaders were green on their own PnL, but only 43.61% produced positive follower PnL.
  - On Binance, 72.45% of leaders delivered positive follower PnL and the copier event win rate was 66.50%. On Bybit, 40.34% of leaders did and the win rate was 43.65%.
  - The authors attribute the gap partly to followers entering later at worse prices, and to fees, funding and slippage, which they did not decompose. They state that their methodology does not establish causality.

  — [YieldFund study](https://www.yieldfund.com/news/is-copy-trading-profitable-a-90-day-multi-exchange-study)
- The peer-reviewed CHI '24 paper "Stranger Danger?" studied TraderWagon, not Binance directly. Per its abstract as surfaced in search, leaders may aim for leaderboard rank over portfolio performance and "do not have to bear large financial risks to climb up the rankings, even briefly". Copiers rely on (at most) the first couple of leaderboard pages, and copying top-ranked leaders did not lead to substantial profits. — [ACM CHI '24 (search snippet; full text 403)](https://dl.acm.org/doi/10.1145/3613904.3642715)
- Academic work on meme-coin copy trading (on-chain, not CEX) describes key opinion leaders using coordinated wallets to accumulate early, inflate prices, wash trade and then dump into copier demand. This is relevant to pump-scheme risk in any copy product listing illiquid assets. — [arXiv 2601.08641 (search snippet)](https://arxiv.org/html/2601.08641v2)

**Regional availability and stated compliance basis (platform statements only)**
- Binance blocked copy trading for EEA users ahead of MiCA's stablecoin rules (June 2024; older info). The service showed "unavailable" in the EEA, and lead and copy traders were told to close positions and move funds back to Spot "before 2024-06-27 23:59 (UTC +3)". — [Finance Magnates, June 2024](https://www.financemagnates.com/cryptocurrency/mica-is-already-here-binance-restricts-eu-users-from-copy-trading-and-many-stablecoins/)
- "Futures and Spot Copy Trading is available in different countries/regions based on respective country-specific legislation and regulatory constraints." Spot copy trading requires "identity verification with proof of address" and an "eligible region". Binance's disclaimer states: "Copy trading is restricted in certain countries and to certain users." All current copy-trading FAQs carry a MiCA disclaimer about unauthorized stablecoins for EEA users. — [Spot FAQ, 2026-09-03](https://www.binance.com/en/support/faq/frequently-asked-questions-on-binance-spot-copy-trading-1826c3b426a149949851554bdde227d3); [Growth Plan, 2026-10-01](https://www.binance.com/en/support/faq/binance-futures-copy-trading-lead-trader-growth-plan-3160c961b2734d1cbb5342d1e86c6cdb)
- The 2026 Signal Copy FAQ refers to legal terms in Binance's Terms of Use, the "Exchange Rules ... and the Clearing Rules ... which come into effect on 5 January 2026", and "Copy Trading Services Terms (as applicable to Futures Copy Trading Services)". This means Futures copy trading now sits under a dedicated services-terms document. — [Signal FAQ, 2026-07-14](https://www.binance.com/en/support/faq/detail/75592719ba1d471ea9558325c6e8e788)
- When Binance launched Futures copy trading in 2023 (older info), a spokesperson said copy trading "is only available in selected markets" without listing them. — [The Block (search snippet)](https://www.theblock.co/post/255396/binance-introduces-copy-trading-feature-for-futures-markets)

### Inferences
- Binance's controls target presentation gaming (imitation, off-platform funnels, guarantees, invite-code spam) and capacity risk (depth-based notional caps, low-liquidity leverage caps). They do little about the structural lag between leader and copier fills, beyond slippage caps and "copy better entries". The leader-versus-copier PnL gap documented by YieldFund is consistent with that.
- Tying profit-share unlocks to copier PnL (the 7D copier PnL threshold) is the strongest alignment mechanism in Binance's design. A DEX terminal can implement it verifiably on-chain.
- The phrase "carrying order" (likely a translation of 带单, meaning "order-leading" or signal-calling) as a malicious behaviour is ambiguous. It may refer to leaders soliciting off-platform signal groups.

### Gaps
- No public record was found of Binance delisting or banning specific lead traders, publishing enforcement statistics, or compensating copiers.
- No Binance-specific, sourced reporting on small-balance ROI inflation or pump schemes by lead traders was found. The evidence is general and academic, or from vendor studies.
- The full list of countries where Binance Futures or Spot copy trading is unavailable was not retrievable (Binance's restricted-region service list page returned no content).

---

## 6. Benchmark (brief): Bitget, Bybit, OKX

### Takeaway
All three exchanges use the same core model as Binance: the leader takes a percentage of the copier's net profit, settled against prior payouts (high-water-mark or netting), and the exchange earns trading fees. They differ on rate caps and settlement cadence:
- Bitget: futures 0–10% with daily settlement (private mode and CFD up to 99% and 30%).
- Bybit: 10–15% by rank, weekly (TradFi 15–30%).
- OKX: up to 30% by level, weekly.
- Binance: 10% default, up to 30%, weekly, on total PnL.

Bitget positions itself as the copy-trading leader, but its last hard numbers I could verify are older marketing figures.

### Cited Findings

**Bitget**
- The new Futures Copy Trading Elite Trader guide (dated 2026-01-09) says:
  - KYC is required, and trades placed in a dedicated "Futures Elite Trading Zone" are mirrored while personal trades are unaffected.
  - Profit share ratio "Range: 0%–10%". The ratio can vary by copier tier.
  - Settlement is "daily at 00:00 (UTC+8)", only if all positions are fully closed, with immediate settlement when a copier stops or is removed or when the project closes.
  - "Profit sharing only occurs on new profits since the last settlement", which is a high-water mark.
  - ROI is time-weighted, and open positions are visible to non-copiers with a 1-hour delay.

  — [Bitget Futures Copy Trading Elite Traders Guide, 2026-01-09](https://www.bitget.com/support/articles/12560603847588)
- On 2026-09-14, Bitget announced a phased mandatory migration of classic futures elite traders to a UTA "elite portfolio" model, staged by copier count (0, 1–49, 50–99, 100–499, 500+). Elite status is revoked for accounts that fail KYC, and bios are AI-reviewed. — [Bitget announcement, 2026-09-14](https://www.bitget.com/news/detail/12560605824231)
- Elite Trader Private Mode (Nov 2023, older info) offers invite-only followers and a customisable profit share "ranging from 0% to 99%", without needing to lock BGB. — [PR Newswire, 2023-11-15](https://www.prnewswire.com/news-releases/bitget-launches-elite-trader-private-mode-elevating-copy-trading-to-new-heights-301988691.html)
- CFD Copy Trading launched 2026-04-14 on MT5 infrastructure. Copying starts from 50 USDT. It uses a "High-Water Mark profit-sharing model", daily settlement and "up to 30%" profit share, with VIP restricted-access portfolios. Bitget's marketing claims are "world's largest Universal Exchange" and "over 125 million users". — [Bitget/GlobeNewswire via AAP, 2026-04-14](https://www.aap.com.au/aapreleases/globenewswire1001175484/)
- Unverified third-party figures (search snippets): 130,000 to 190,000+ elite traders, 800,000+ copiers, and "100 million copy trades". — [Coin Bureau Bitget review](https://coinbureau.com/review/bitget-copy-trading-review); [Datawallet](https://www.datawallet.com/crypto/best-crypto-copy-trading-platforms)

**Bybit**
- Profit share by Master Trader rank: Cadet 10%, Bronze 10%, Silver 12%, Gold 15% (page last updated 2026-02-25).
  - Net PnL is calculated daily, and the profit share on daily profits is pre-deducted and refunded if the cycle nets a loss.
  - The cycle runs Saturday 00:00 UTC to Friday 23:59:59 UTC, with payout at 03:00 UTC Monday.
  - The share is paid only once all USDT perpetual trades opened on the same day are closed.
  - Net profit = position PnL − open fee − close fee.

  — [Bybit Help Center, Copy Trading: Profit Sharing Explained, 2026-02-25](https://www.bybit.com/en/help-center/article/Copy-Trading-Profit-Sharing-Explained)
- TradFi Master Traders have higher ratios of 15%, 20%, 25% and 30% (Cadet to Gold) under a high-water-mark principle, per a page last updated May 2026 (search snippet). — [Bybit TradFi Copy Trading Profit Sharing](https://www.bybit.com/en/help-center/article/TradFi-Copy-Trading-Profit-Sharing-Explained)
- Copy Trading Pro, a vetted "Pro Masters" tier, launched in June 2024, announced alongside Bybit's 30M-user milestone (older). Bot Copy Trading launched in December 2023 (older), letting followers copy master traders' bots run in sub-accounts. — [Finance Magnates, June 2024 (snippet)](https://www.financemagnates.com/cryptocurrency/bybit-marks-30-million-users-as-new-copy-trading-platform-debuts/); [The Paypers (snippet)](https://thepaypers.com/crypto-web3-and-cbdc/news/bybit-launches-bot-copy-trading-system)
- Leader acquisition runs through prize competitions: a Master Trader Arena with a 300,000 USDT pool (Nov 2025), and a "TradFi vs. Crypto" challenge with 300,000 USDT (Feb 2026) requiring at least 20 unique active followers to qualify. — [AAP/Cision, 2025-11-17 (snippet)](https://www.aap.com.au/aapreleases/cision20251117ae25988); [AAP/Cision, 2026-02-09 (snippet)](https://www.aap.com.au/aapreleases/cision20260209ae83704)

**OKX**
- "Copy traders share up to 30% of profits ... based on lead trader levels." Settlement is weekly, Monday 00:00 to Sunday 23:59:59 (UTC+8), effective 10 Sep 2023. Profit share is withheld daily on profitable trades and the excess is refunded at settlement. Futures profit is shared only when copier and leader have no linked open positions; on Spot, only when all crypto bought that week has been sold. Leaders can edit the ratio up to 3 times a month. The worked example uses an L2 leader at 10%. Page published 2023-09-04, updated 2026-08-19. — [OKX Help, Lead traders: Trader profit sharing rules](https://www.okx.com/help/lead-traders-trader-profit-sharing-rules)
- In 2023 (older), OKX introduced AUM-based profit-sharing levels. ForkLog reported an 8–13% range by AUM at the time, which conflicts with the current "up to 30%" figure and has likely been superseded. — [Fintech Futures (OKX press release)](https://www.fintechfutures.com/press-releases/flash-news-okx-announces-profit-sharing-feature-updates-on-its-copy-trading-product); [ForkLog (snippet)](https://forklog.com/en/?p=86570)

### Inferences
- Comparison:

| | Binance Futures | Bitget Futures | Bybit (crypto) | OKX |
|---|---|---|---|---|
| Profit share | 10% default, 0–30% by badge; private up to 30% | 0–10% (private up to 99%; CFD up to 30%) | 10/10/12/15% by rank (TradFi 15–30%) | up to 30% by level |
| Settlement | Weekly (Mon 00:00 UTC), total PnL incl. unrealized, cumulative HWM | Daily 00:00 UTC+8, HWM, only when flat | Weekly (Sat–Fri, paid Mon 03:00 UTC), daily pre-deduction with refund | Weekly (Mon 00:00 UTC+8), withholding with refund, only when no linked positions |
| Extra leader income | 10% of copier fees (capped at 0.3% of margin/week), affiliate up to 50% | not retrieved | not retrieved | not retrieved |

- Sources: the cited Binance, Bitget, Bybit and OKX pages above.
- The industry-standard anchor is about 10% default profit share, with 30% reserved for top-tier or private leaders. Settlement netting against prior payouts or a high-water mark is universal. Binance is the only one of the four that settles on unrealized PnL, which avoids the "settle only when flat" delays used by Bitget, Bybit and OKX but means leaders can be paid on paper gains.
- None of the four documents a platform cut of profit share. All monetize through trading fees, and Binance explicitly kicks back 10% of copier fees to leaders.

### Gaps
- Bitget, Bybit and OKX do not publish verified current totals for copiers, leaders or copy AUM. Bitget's frequently cited "120,000 elite traders / 600,000 followers / US$4B cumulative profit" comes from a September 2023 press release (older) that I could not retrieve directly.
- Fee rebates or commissions to leaders on Bitget, Bybit and OKX were not verified in this pass.
- Bybit's Copy Trading Pro profit share terms were not found.
