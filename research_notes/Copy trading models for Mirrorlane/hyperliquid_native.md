# Hyperliquid native mechanisms for copy trading and third-party front-ends

Research date: 2026-10-21. "Live API" means I queried Hyperliquid's public endpoints myself on 2026-10-21 at about 14:10 UTC: `POST https://api.hyperliquid.xyz/info` and `https://stats-data.hyperliquid.xyz/Mainnet/...`, with no API key. Docs were pulled on the same date from hyperliquid.gitbook.io as markdown.

Older figures carry their own date. Search-engine summaries are used only where I could not open the page, and each one is marked "(page not opened; search summary)". Treat those as lower confidence.

## 1. User vaults: how they work, their economics, and the current landscape

### Takeaway
Hyperliquid's native "copy trading" is pooled custody, not mirroring. Depositors send USDC into a vault account, the leader trades that account, and each depositor owns a pro-rata share of its equity. The protocol fixes the leader's cut at 10% of profits and requires the leader to keep at least 5% of the vault. As of October 2026 these HyperCore vaults are officially labelled "legacy". Creating one now costs a 10,000 USDC fee. New vault creation has almost stopped since about April 2026, while 3,081 open vaults hold about $95M of user-vault TVL, separate from HLP.

### Cited Findings
**Rules (official docs, current as of 2026-10-21)**
- The docs now describe vaults as something builders create on HyperEVM via CoreWriter and precompiles. Such vaults can follow ERC-4626, trade on HyperCore, "delegate any number of authorized agents", and access spot and HIP-3. The docs call this "a strict improvement over the 'legacy' HyperCore vaults, which were introduced in 2023 and do not support HIP-3 or spot trading" — [HL docs: Vaults](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults)
- Who can create a vault: anyone. The steps are to choose a name and description (both permanent) and deposit at least 100 USDC. "Creating a vault requires a 10k USDC gas fee, which is distributed to the protocol in the same manner as trading fees" — [HL docs: For vault leaders (legacy)](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-leaders)
- Leader economics: the leader receives a 10% profit share. To keep skin in the game, the leader "must maintain ≥5% of the vault at all times" and cannot withdraw if that would push their share below 5% — [HL docs: For vault leaders](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-leaders)
- "Vault owners receive 10% of the total profits. Note that protocol vaults do not have any fees or profit share." Vaults can be run by an individual trader or automated by a market maker — [HL docs: HyperCore vaults (legacy)](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/hypercore-vaults-legacy)
- Tradable assets: legacy vaults "can trade validator-operated perps. They cannot trade spot or HIP-3 perps" — [HL docs: For vault leaders](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-leaders)
- Managing a vault in the UI: the leader picks the vault in the address dropdown on the Trade page, and every trade then applies to the vault. Through the API, "Subaccounts and vaults do not have private keys". The master account (or its API wallet) signs, and sets `vaultAddress` to the vault — [HL docs: For vault leaders](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-leaders); [HL docs: Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)
- Closing a vault: all positions must be closed first, and then all depositors receive their share — [HL docs: For vault leaders](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-leaders)
- What happens on a depositor withdrawal, in order:
  - If the vault has enough margin, open positions are unaffected.
  - If not, orders that use margin are cancelled, smallest margin first.
  - If margin is still short, "20% of positions are automatically closed", repeated until enough is freed.
  - Leaders can instead set the vault to "always proportionally close positions on withdrawals".
  - Source: [HL docs: For vault leaders](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-leaders)
- Depositor accounting example: you deposit 100 USDC into a 900 USDC vault and own 10%. The vault grows to 2,000, so your 10% is 200 USDC. You withdraw 200 minus a 10 USDC leader profit share, receiving 190 USDC. "There may be some slippage as you withdraw and open positions are closed" — [HL docs: For vault depositors (legacy)](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-depositors)
- Lock-ups: "HLP has a lock-up period of 4 days. User vaults have a lock-up period of 1 day." — [HL docs: For vault depositors](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-depositors)
- API actions:
  - Deposits and withdrawals use the `vaultTransfer` action with `{vaultAddress, isDeposit, usd}`.
  - `vaultDetails` returns each follower's `vaultEquity`, `pnl`, `allTimePnl`, `daysFollowing`, `vaultEntryTime` and `lockupUntil`, plus vault-level `leaderFraction`, `leaderCommission`, `maxDistributable`, `maxWithdrawable`, `allowDeposits`, `alwaysCloseOnWithdraw`, `apr` and portfolio history.
  - `userVaultEquities` lists a user's vault positions.
  - Sources: [HL docs: Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint); [HL docs: Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- Live API check of real vaults (2026-10-21):
  - Growi HF: `leaderCommission`=0.1, `leaderFraction`=0.0506, `allowDeposits`=false, which shows leaders can close a vault to new deposits.
  - BredoStrategy: `leaderCommission`=0.1, `leaderFraction`=0.0855, `alwaysCloseOnWithdraw`=true.
  - Both responses listed exactly 100 followers.
  - Source: [Live API vaultDetails](https://api.hyperliquid.xyz/info)
- Discovery in the UI: app.hyperliquid.xyz/vaults shows APY and TVL for each vault. A vault's own page shows PnL, max drawdown, volume, open positions, trade history, and how many people have deposited and for how long — [HL docs: For vault depositors](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-depositors)

**Landscape (live API, full vault list from `stats-data.hyperliquid.xyz/Mainnet/vaults`, 2026-10-21)** — [Live vault list](https://stats-data.hyperliquid.xyz/Mainnet/vaults)
- 9,478 vaults have ever been created (first on 2023-02-26). 6,397 are closed and 3,081 are open.
- Open vaults by TVL: 504 have at least $1k, 226 at least $10k, 78 at least $100k, 25 at least $1M, and 4 at least $10M. Of the 25 above $1M, 7 belong to the HLP family, which leaves 18 user vaults above $1M.
- Open user vaults (relationship "normal", which excludes HLP and its children) hold a combined TVL of about $94.9M. The top 10 hold 64.6% of it.
- Vaults created per year: 777 in 2023, 5,079 in 2024, 2,997 in 2025, and 625 in 2026 to date.
- Vaults created per month in 2025–26:
  - Jun 2025 to Mar 2026: between 117 and 255 a month (Mar 2026: 220).
  - Then: Apr 2026 83, May 10, Jun 5, Jul 3, Aug 4, Sep 6, Oct (to the 21st) 2.
- Largest open user vaults on 2026-10-21. APR is the API's `apr` field, whose definition is undocumented.

| Vault | TVL | APR | Created | All-time PnL | 30-day PnL |
|---|---|---|---|---|---|
| Growi HF | $13.7M | 16.8% | 2024-07 | +$3.09M | |
| [Systemic Strategies] L/S Grids | $9.96M | −12.8% | | +$1.10M | −$1.83M |
| drkmttr | $8.79M | −23.8% | | +$5.35M | −$5.05M |
| DOUBLETOP Vault | $7.10M | | 2026-06 | | |
| BredoStrategy | $6.70M | 100.3% | | +$3.87M | |
| [Systemic Strategies] HyperGrowth | $5.77M | | | +$5.60M | |

  Source: [Live vault list](https://stats-data.hyperliquid.xyz/Mainnet/vaults)
- Search results report that one secondary guide gives the same terms: 10,000 USDC creation fee, 100 USDC minimum, 10% profit share, 5% leader stake, 1-day lock-up — [hypermirror.io (third-party guide)](https://hypermirror.io/hyperliquid/hyperliquid-vaults-and-hlp)

### Inferences
- The creation fee appears to have risen from about 100 USDC to 10,000 USDC.
  - Earlier versions of the leader docs said 100 USDC; a search engine's cached summary of the official page still said "100 USDC as a gas fee". I could not open an archived copy to confirm.
  - Monthly vault creations fell about 90% between March and May 2026.
  - Together these strongly suggest the fee increase and the "legacy" label arrived around April 2026. The exact date is unverified.
- The 10% profit share appears to be charged on profit at withdrawal, per depositor, which works like a per-depositor high-water mark. This is inferred from the docs example and the per-follower `pnl` and `allTimePnl` fields; the docs do not spell out high-water-mark semantics.
- The protocol takes no cut of the leader's 10%. Its only take from vaults is the creation fee plus normal trading fees on vault volume, and vault volume earns its own separate fee tier (Section 7).
- The vault model gives Mirrorlane no native revenue hook beyond normal trading or builder fees. The leader's 10% is hard-coded and cannot be split with a front-end. The new HyperEVM path (custom ERC-4626 accounting plus CoreWriter agents) is where configurable fee splits would have to live.
- Vault TVL is highly concentrated: the top 10 user vaults hold about 65%. Many large vaults currently show negative 30-day PnL, so vault returns are volatile and leaderboard ranking by APR is noisy.

### Gaps
- No official changelog or date for the fee change (to 10k USDC) or the "legacy" designation. archive.org was unreachable from this environment.
- The calculation behind the `apr` field (trailing window, annualisation) is undocumented.
- Total unique vault depositors across all vaults is not available. The `vaultDetails` response appears capped at 100 followers.
- Whether a leader's vault orders can carry a builder code, so that a front-end earns on vault flow, is not documented.

## 2. HLP (Hyperliquidity Provider): size, returns, and incidents

### Takeaway
HLP is the protocol-owned, community-funded vault: a market maker, the liquidation backstop, and a recipient of a share of fees. It has no profit share and a 4-day lock-up. Its TVL peaked at about $604M in September 2025 and was about $178M on 2026-10-21, with about $139M of all-time PnL.

Each of the March 2025 ETH whale, March 2025 JELLY and November 2025 POPCAT incidents pushed losses from toxic flow onto HLP depositors. The protocol's responses were a validator-vote delisting and forced settlement (JELLY), leverage and margin rule changes (ETH), and halting withdrawals and the bridge (POPCAT).

### Cited Findings
- What HLP does: it "provides liquidity to Hyperliquid through multiple market making strategies, performs liquidations, supplies USDC in Earn, and accrues a portion of trading fees… HLP is fully community-owned." The deposit lock-up is 4 days from the most recent deposit — [HL docs: Protocol vaults](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/protocol-vaults)
- Protocol vaults "do not have any fees or profit share" — [HL docs: HyperCore vaults (legacy)](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/hypercore-vaults-legacy)
- Live HLP state on 2026-10-21 (vault 0xdfc24b…f303):
  - Account value about $177.8M; `apr` 3.46%; `leaderCommission` 0; `leaderFraction` 0.20%.
  - All-time PnL +$138.8M; 30-day PnL +$0.63M.
  - Seven child strategy vaults: HLP Strategy X ($100.6M), HLP Liquidator 2 ($30.0M), Strategy A ($3.15M), Strategy B ($2.98M, all-time −$4.41M), and Liquidators 3 and 4 ($1M each).
  - Source: [Live API vaultDetails (HLP)](https://api.hyperliquid.xyz/info); [Live vault list](https://stats-data.hyperliquid.xyz/Mainnet/vaults)
- HLP account value history (live API, roughly biweekly points):

| Date | Account value |
|---|---|
| 2025-03-05 | $509.5M |
| 2025-03-12 | $354.2M |
| 2025-03-26 | $195.1M |
| 2025-04-09 | $149.7M |
| 2025-09-03 (peak) | $603.9M |
| 2025-11-12 | $532.8M |
| 2026-01-07 | $301.0M |
| 2026-04-01 | $448.3M |
| 2026-07-08 | $258.4M |
| 2026-10-21 | $177.8M |

  Source: [Live API vaultDetails (HLP)](https://api.hyperliquid.xyz/info)
- HLP PnL by year, calculated from the live API pnlHistory:

| Year | PnL | Return on average account value |
|---|---|---|
| 2024 | +$48.8M | about 32% |
| 2025 | +$68.3M | about 17% |
| 2026 to Oct 21 | +$20.6M | about 7% (not annualised) |

  Source: [Live API vaultDetails (HLP)](https://api.hyperliquid.xyz/info)
- **ETH whale, 2025-03-12**
  - Wallet 0xf3F opened a 50x ETH long worth over $300M, then withdrew collateral instead of closing. That raised its liquidation price, and it was liquidated at $1,915, netting the trader about $1.86M.
  - The position passed to HLP, and slippage on the unwind cost HLP about $4M.
  - Hyperliquid cut maximum leverage to 40x on BTC and 25x on ETH.
  - HLP saw over $130M of withdrawals in a day.
  - Source: [Arkham Research](https://info.arkm.com/research/hyperliquid-whale-passes-4m-loss-to-hlp-vault)
- Decrypt reported that after the ETH incident Hyperliquid said it would reduce leverage on BTC and ETH and "increase maintenance margin requirements" — [Decrypt, 2025-03-26](https://decrypt.co/311713)
- **JELLY (JELLYJELLY), 2025-03-26**
  - A user opened a $6M, 20x short on JELLYJELLY, suspected of deliberately self-liquidating so HLP would inherit the position as the price was pumped.
  - "After evidence of suspicious market activity, the validator set convened and voted to delist JELLY perps." Hyperliquid said: "All users apart from flagged addresses will be made whole from the Hyper Foundation."
  - HLP's all-time profit temporarily dropped by about $11M. HYPE fell about 14%.
  - Arthur Hayes: "Let's stop pretending Hyperliquid is decentralized."
  - Source: [Decrypt, 2025-03-26](https://decrypt.co/311713)
- JELLY positions were reportedly settled at $0.0095, the short's entry price, and HLP ended about +$703k on the episode. Reports of HLP's peak unrealised loss range up to about $12–13.5M — [coin360](https://coin360.com/news/hyperliquid-delists-jelly-token-after-attack); [forklog](https://forklog.com/en/?p=22453) (pages not opened; search summary)
- **POPCAT, 2025-11-12**
  - An attacker moved about $3M USDC from OKX across 19 wallets and built more than $20M of POPCAT longs.
  - The attacker placed an approximately $20M buy wall at $0.21 and then pulled it. The resulting crash triggered liquidations, and HLP absorbed about $4.9M of bad debt.
  - Hyperliquid halted withdrawals and temporarily halted its Arbitrum bridge.
  - Halborn described it as exploiting pool design and thin liquidity, "rather than any specific vulnerability".
  - Source: [Halborn](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-november-2025)
- The Block reported that Hyperliquid paused deposits and withdrawals amid POPCAT manipulation speculation — [The Block](https://www.theblock.co/post/378606/hyperliquid-pauses-deposits-withdrawals-popcat-trading-scheme-speculation) (page not opened, 403; search summary)
- A search summary describes POPCAT as the third manipulation event against HLP in 2025, after JELLY in March and an incident in July — [Yahoo Finance](https://finance.yahoo.com/news/hyperliquid-hit-third-market-manipulation-113215395.html) (page not opened; search summary)

### Inferences
- HLP's returns have compressed sharply: about 32% in 2024, about 17% in 2025, and about 7% YTD in 2026 with a trailing APR around 3.5%. Its TVL has fallen about 70% from the September 2025 peak.
- Mirrorlane's lesson from HLP: a pooled "house" vault socialises toxic-flow losses across all depositors. Incidents caused fast bank-run withdrawals; the March 2025 snapshots show HLP falling from about $509M to about $150M in five weeks.
- The protocol's backstop (Foundation reimbursement, validator-vote delisting at a chosen price) is discretionary and centralised. This is a governance and reputational risk, not a coded guarantee.

### Gaps
- No official Hyperliquid post-mortem was opened. Incident figures (position sizes, peak HLP loss) vary across media.
- I did not find a reliable source on the October 10, 2025 market-wide liquidation and ADL event's effect on HLP.
- The live API reports HLP only at about two-week granularity, so the intra-incident drawdowns cannot be measured from it.

## 3. Builder codes: how front-ends earn on users' trades

### Takeaway
Builder codes let any front-end add its own fee on top of Hyperliquid's fees to every fill it routes. The fee is capped at 0.1% (10 bps) on perps and 1% on spot. The user approves a maximum rate once with their main wallet, and the fee is accounted entirely on-chain.

This mechanism has paid out tens of millions of dollars. Phantom alone has $27.5M of builder rewards on-chain as of 2026-10-21. Builder-code revenue across the ecosystem runs at about $10M a month, with wallets charging the maximum and pro terminals charging 1–1.5 bps.

### Cited Findings
- Mechanics: builders "receive a fee on fills that they send on behalf of a user", set per order. The user approves a maximum builder fee per builder with `ApproveBuilderFee`, which "must be signed by the user's main wallet, not an agent/API wallet", and can revoke at any time. Accounting happens "entirely onchain as part of the fee logic" — [HL docs: Builder codes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes)
- Builder requirements: the builder address needs at least 100 USDC of perps account value and must use the "standard" account abstraction mode — [HL docs: Builder codes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes)
- Caps and scope:
  - At most 0.1% on perps and 1% on spot.
  - Builder codes apply only to fees collected in the quote or collateral asset, so they "do not apply to the buying side of spot trades but apply to both sides of perp trades".
  - "Each user can have a maximum of 10 active builder code approvals at a time."
  - Source: [HL docs: Builder codes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes)
- Order format: an optional `builder: {"b": address, "f": number}` on order actions, where `f` is in tenths of a basis point (f=10 means 1 bp). The approval payload is `{"type":"approveBuilderFee","maxFeeRate":"0.001%","builder":...}` — [HL docs: Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)
- The SDK example rejects builder approval from anything but the main wallet ("Only the main wallet has permission to approve a builder fee") — [Python SDK basic_builder_fee.py](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_builder_fee.py)
- Claiming and transparency:
  - Fees are claimed "through the usual referral reward claim process".
  - `{"type":"maxBuilderFee","user","builder"}` returns a user's approval.
  - The builder's cumulative total is in `{"type":"referral","user":builder}`.
  - Every builder-coded fill is published daily at `https://stats-data.hyperliquid.xyz/Mainnet/builder_fills/{builder_address}/{YYYYMMDD}.csv.lz4` (address must be lowercase).
  - Source: [HL docs: Builder codes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes)
- Live check (2026-10-21) of Phantom's builder address 0xb84168cf…f80b:
  - `builderRewards` = $27,529,851.
  - Claimed $24,598,886 and unclaimed $5,364,677, a total of about $29.96M across builder and referral rewards.
  - Phantom also runs referral code "PURPS" with 198,279 referred users.
  - Its builder_fills file for 2026-10-19 downloaded publicly (835 KB).
  - Source: [Live API referral](https://api.hyperliquid.xyz/info); [builder_fills feed](https://stats-data.hyperliquid.xyz/Mainnet/builder_fills/0xb84168cf3be63c6b8dad05ff5d755e97432ff80b/20261019.csv.lz4)
- Cumulative builder revenue (HL HUB community post, 2026-10-08):

| Builder | All-time revenue |
|---|---|
| Phantom | $26.8M ($52.6B volume, 188K users) |
| Based | $15.46M |
| MetaMask | $11.89M |
| PVP | $8.07M |
| Insilico | $4.16M |

  Source: [KuCoin/HL HUB, 2026-10-08](https://www.kucoin.com/news/insight/META/6ac7584a38a2640007932413)
- 30-day builder revenue (HL HUB, 2026-09-15): builder codes generated $10.17M on $24.08B of volume. The top 10 by 30-day revenue were MetaMask, Trust Wallet, Phantom, fomo, Invo, 0x9c…0ad9 (unidentified), Rabby, Blockchain.com, Based and 0x7c…e781 (unidentified) — [KuCoin/HL HUB, 2026-09-15](https://www.kucoin.com/news/insight/META/6aa947a57d10fa0007cdaa20)
- TokenPost (2026-10-10, citing Castle Labs): Phantom has received more than $25M through Builder Codes and MetaMask more than $10.5M — [TokenPost](https://www.tokenpost.com/news/investing/29363)
- Daily builder fees by front-end (OpenChainBench, day ending 2026-10-21 00:00 UTC). 104 front-ends are tracked, using the official builder_fills feed. Native Hyperliquid UI orders carry no builder code and are excluded.

| Front-end | Builder fees | Volume | Users | Effective fee |
|---|---|---|---|---|
| MetaMask | $60.7K | $60.7M | 1,229 | 0.10% |
| Trust Wallet | $59.9K | $59.9M | 1,464 | 0.10% |
| FOMO | $53.1K | $125.3M | 2,391 | 0.042% |
| Phantom | $51.2K | $88.3M | 4,319 | 0.058% |
| Hyperdash | $42.9K | $284.3M | 270 | 0.015% |
| Rabby | $20.6K | $59.5M | | 0.035% |
| Liquid Perps | $14.3K | | | |
| Invo | $11.4K | | 6,239 | |
| Bitget Wallet | $6.2K | | | 0.05% |
| Insilico | $4.5K | $45.2M | | 0.010% |
| Tread.fi | $2.6K | $26.9M | | 0.0097% |
| Moonbot | $2.2K | | | 0.015% |
| based.app | $0.8K | $3.7M | | 0.022% |

  Source: [OpenChainBench](https://openchainbench.com/benchmarks/hyperliquid-frontends)
- OpenChainBench's text says the cap is "100 basis points on perps". That contradicts the official 0.1% (10 bps) perp cap — [OpenChainBench](https://openchainbench.com/benchmarks/hyperliquid-frontends) vs [HL docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes)
- Hyperdash (2026-01-20) gives an example of how a terminal prices its builder fee:
  - It charges 1.5 bps (f=15), with volume-based cashback of 5% to 22.5% of the builder fee (Obsidian tier at $500M+ of 30-day volume is about 1.16 bps).
  - It claims builder codes had paid over $40M to developers, that "roughly 40% of Hyperliquid's daily active users now trade through third-party frontends", that Phantom earns over $100k a day, and that PVP.trade earned $7.2M lifetime.
  - Source: [Hyperdash](https://hyperdash.com/learn/hyperliquid-builder-codes-explained-how-third-party-apps-earn-fees-on-chain)
- CoinGecko research reportedly put Phantom at $20.6M (31.8% of top-10 builder revenue) and Based at $15.06M, attributing the gap partly to Based charging 0.025% versus Phantom's 0.05% — [CoinGecko](https://www.coingecko.com/research/publications/top-hyperliquid-builders) (page not opened, 403; search summary; date unknown, older than Oct 2026)

### Inferences
- From the OpenChainBench table, the top 24 front-ends earned about $373K in builder fees on about $926M of routed volume on 2026-10-20. That is a volume-weighted average of about 4 bps, roughly $11M a month, which agrees with HL HUB's $10.17M for 30 days.
- Two pricing camps exist:
  - Retail wallets (MetaMask, Trust Wallet) charge the full 10 bps, more than double Hyperliquid's own 4.5 bps base taker fee.
  - Pro and active terminals (Hyperdash, Insilico, Tread.fi, Moonbot) charge 1–1.5 bps and win on volume; Hyperdash routed about $284M a day.
  - A copy-trading terminal sits between the two; FOMO is the closest analogue at about 4.2 bps.
- Builder-coded volume of about $926M a day compares with about $5.15B of 24-hour notional on validator perps (Section 7), implying very roughly 15–20% of volume flows through builder codes. This is a loose estimate because the windows and scopes differ (builder volume may include spot and HIP-3).
- For Mirrorlane, this is the key primitive to replicate or compare on Lighter. On Hyperliquid a front-end monetises every mirrored fill with no contract or permission from the exchange: one signature from the user, a per-order rate up to a cap, on-chain accrual, and a public audit trail.
- The 10-approval limit per user means a front-end competes for one of a user's 10 slots.

### Gaps
- No official, comprehensive ranking of builders by all-time revenue. Third-party rankings rely on address-to-name registries and differ in date and method.
- Not verified: how builder fees interact with referral rewards on the same order (see Section 5 for the conflict).
- Copy-trading-specific builder revenue (for example from dedicated copy apps) was not isolated. That falls to the third-party-apps researcher.

## 4. Agent wallets and API wallets

### Takeaway
An API wallet (agent wallet) is a separate key that the master account authorises to sign trading actions for the master and its sub-accounts or vaults. It cannot withdraw or transfer funds out. This is the standard non-custodial pattern for bots and copy-trading services: the service holds only the agent key, and the user's funds stay in the user's own account.

Each account can have 1 unnamed and 3 named agents, plus 2 named agents per sub-account. Agents expire after at most 180 days. Nonces are tracked per signer.

### Cited Findings
- Permissions: the agent "can place trades on behalf of the account. The agent does not have permission to transfer or withdraw funds." Agents cannot create other agents ("You should not create an agent using an agent") — [Python SDK basic_agent.py](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_agent.py)
- Scope: "A master account can approve API wallets to sign on behalf of the master account or any of the sub-accounts." API wallets "are only used to sign". To query data you must use the real account address, because querying the agent's address returns empty results — [HL docs: Nonces and API wallets](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets)
- The one agent-signable transfer is `agentSendAsset`, which "can be signed by an agent. Destination must match the source address". It only moves collateral between the user's own perp DEXs and spot. Builder-fee approval must come from the main wallet — [HL docs: Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint); [HL docs: Builder codes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes)
- Limits and expiry: `approveAgent` takes an optional `agentName`. "An account can have 1 unnamed approved wallet and up to 3 named ones. And additional 2 named agents are allowed per subaccount." A custom expiry can be set with `valid_until {timestamp}`, at most 180 days ahead — [HL docs: Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)
- Pruning:
  - An agent and its nonce state can be pruned when it is deregistered (a new unnamed agent replaces the old unnamed one, or a new agent reuses a name), when it expires, or when the registering account no longer has funds.
  - The docs "strongly" advise against reusing agent addresses because "previously signed actions can be replayed once the nonce set is pruned".
  - Source: [HL docs: Nonces and API wallets](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets)
- Nonces:
  - The 100 highest nonces are stored per signer. A new nonce must exceed the smallest stored nonce and must never have been used.
  - Nonces must fall within (T − 2 days, T + 1 day) of block time.
  - Recommended practice: one API wallet per trading process or sub-account, batching orders every 0.1s, and an atomic nonce counter.
  - "A single API wallet signing for a user, vault, or subaccount all share the same nonce set."
  - Source: [HL docs: Nonces and API wallets](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets)
- Execution safety features available to bots:
  - `expiresAfter` rejects stale actions, which consume 5x the rate limit if they expire.
  - `scheduleCancel` acts as a dead man's switch.
  - `noop` invalidates an in-flight nonce.
  - Source: [HL docs: Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)
- HyperEVM vaults can "delegate any number of authorized agents using CoreWriter" — [HL docs: Vaults](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults)
- Address-based action limits:
  - 1 request per 1 USDC of cumulative volume, plus an initial buffer of 10,000. When rate-limited, one request per 10 seconds.
  - Cancels get a higher allowance.
  - Additional actions can be bought at 0.0005 USDC per request with `reserveRequestWeight`, which can pay for another user.
  - Batches of n orders count as n for address limits but as 1 for IP limits.
  - Sources: [HL docs: Rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits); [HL docs: Exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)
- Open-order limits: 1,000 by default, plus 1 per $5M of volume, up to 5,000 — [HL docs: Rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

### Inferences
- The copy-trading flow on Hyperliquid looks like this:
  - The follower signs `approveAgent`, giving the service a key that can trade but not withdraw.
  - The follower signs `approveBuilderFee` once, which the service cannot do on their behalf.
  - The service then mirrors the leader's fills into the follower's account through the agent and attaches the builder code to each order.
  - The service never holds funds, and the follower can revoke at any time by replacing or expiring the agent.
- Agent limits are per account, not per service. A copy service takes one of the follower's 4 master-level agent slots, and the unnamed slot is overwritten whenever a new unnamed agent is approved, for example by the official UI. Services should therefore use a named agent.
- A new follower with little volume starts with a 10,000-action buffer and then 1 action per USDC traded. Mirroring many small orders could hit address limits, though `reserveRequestWeight` lets the service pay for headroom.

### Gaps
- Did not verify whether an agent can sign `vaultTransfer` (vault deposit or withdrawal) or `usdClassTransfer`. The docs list `agentSendAsset` as the agent-capable transfer.
- Did not verify which other agent-signable actions exist beyond the documented "(agent)" variants (HIP-3 DEX abstraction, user abstraction).

## 5. Referral program economics

### Takeaway
The referrer earns 10% of the referred user's fees, net of the referee's discount, on the referee's first $1B of volume. The referee gets a 4% fee discount on their first $25M. Builder codes, not referrals, are the main revenue channel for front-ends. A proposed staking-referral program that would let referrers keep up to 40–100% of fee differences has not been implemented and is "being re-evaluated".

### Cited Findings
- Referrer requirements and rewards:
  - A referral code can be created after $10,000 of volume.
  - The referrer receives "10% of referred users' fees, less any fee discount they receive". Rewards apply to a referee's first $1B of volume.
  - Rewards accrue in all quote assets, can be claimed once above $1, and land in the spot balance.
  - Source: [HL docs: Referrals](https://hyperliquid.gitbook.io/hyperliquid-docs/referrals)
- Referee: 4% fee discount on the first $25M of volume. "Referral discounts do not apply to vaults or sub-accounts because those are treated as independent accounts in the clearinghouse" — [HL docs: Referrals](https://hyperliquid.gitbook.io/hyperliquid-docs/referrals); [HL docs: Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- Referral codes are tied to a user permanently and apply however that user trades. "Builder codes override referral codes for that order, and referral codes are disabled after the user trades $1B cumulative volume" — [HL docs: Proposal: Staking referral program](https://hyperliquid.gitbook.io/hyperliquid-docs/referrals/staking-referral-program)
- Staking referral proposal (not live):
  - "At this time, there is no definitive implementation for the staking referral program ready for mainnet… it is being re-evaluated."
  - The proposal would let builders and referrers with staked HYPE keep the difference between their staking-tier discount and the user's, scaled from 100% at VIP 0 down to 40% at VIP 6, and share up to 50% of that back with the user.
  - Worked example from the docs: Alice gets a 30% discount and Bob a 10% discount, with Bob at VIP 1. Alice keeps (30% − 10%) × 90% = 18% of Bob's fees.
  - Source: [HL docs: Proposal: Staking referral program](https://hyperliquid.gitbook.io/hyperliquid-docs/referrals/staking-referral-program)
- Example scale: Phantom's referral code "PURPS" has 198,279 referred users (live API, 2026-10-21) — [Live API referral](https://api.hyperliquid.xyz/info)
- Conflicting source: Hyperdash says builder codes and referral codes "can stack… both systems apply independently". That contradicts the official "builder codes override referral codes for that order" — [Hyperdash](https://hyperdash.com/learn/hyperliquid-builder-codes-explained-how-third-party-apps-earn-fees-on-chain) vs [HL docs](https://hyperliquid.gitbook.io/hyperliquid-docs/referrals/staking-referral-program)

### Inferences
- At the base 4.5 bps taker rate, a 10% referral share is worth about 0.45 bps of referee volume. That is about 1/20th of a maximum 10 bps builder fee, which is why front-ends rely on builder codes.
- Phantom's total rewards ($29.96M) minus its builder rewards ($27.53M) suggests about $2.4M came from referrals. This is inferred from the API fields and is unverified.

### Gaps
- Exact precedence when a referred user trades through a builder-coded front-end is ambiguous: official docs say builder codes override, while one third party says the two stack.
- No published total of referral payouts across the protocol.

## 6. Public data access: reading any address's fills, orders, positions and funding

### Takeaway
Everything is public and keyless. Any address's positions (`clearinghouseState`), open orders, fills, funding, ledger, portfolio and vault data can be read over REST. It can also be streamed over WebSocket (`userFills`, `userEvents`, `orderUpdates`, `clearinghouseState`, `openOrders`, `userFundings`, `webData3`, and others) for arbitrary addresses.

The binding constraint for copy trading is the per-IP WebSocket limit of 10 unique users across user-specific subscriptions. On top of that, REST allows 1,200 weight per minute per IP, and fill history is capped (2,000 per response, 10,000 most recent). Large-scale monitoring of many leaders needs many IPs or one's own non-validating node.

### Cited Findings
- Info endpoints take any `user` address, including:
  - Open orders (`openOrders`, `frontendOpenOrders`), `userFills` and `userFillsByTime`, `historicalOrders`, `orderStatus`.
  - Positions and margin (`clearinghouseState`), `userFunding` and non-funding ledger updates.
  - `portfolio`, `userFees`, `referral`, `subAccounts`, `vaultDetails` and `userVaultEquities`.
  - `maxBuilderFee` and approved builders, plus `activeAssetData`.
  - Source: [HL docs: Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint); [HL docs: Info endpoint – Perpetuals](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- History caps: `userFills` "Returns at most 2000 most recent fills". `userFillsByTime` returns at most 2,000 per response, "and only the 10000 most recent fills are available". Time-range queries return 500 elements per page — [HL docs: Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- WebSocket user-specific subscriptions take an arbitrary `user`:
  - `notification`, `webData3`, `twapStates`, `clearinghouseState`, `openOrders`, `orderUpdates`.
  - `userEvents` (channel "user"), `userFills` (optional `aggregateByTime`), `userFundings`, `userNonFundingLedgerUpdates`.
  - `activeAssetData`, `userTwapSliceFills`, `userTwapHistory`, `spotState`, `allDexsClearinghouseState`.
  - Subscription acks include a snapshot (`isSnapshot: true`).
  - The current docs list `webData3`; `webData2` no longer appears in the subscription list.
  - Source: [HL docs: WebSocket subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
- IP rate limits:
  - REST: 1,200 weight per minute per IP. `clearinghouseState`, `l2Book`, `allMids` and `orderStatus` cost 2. Most other info requests cost 20. `userFills`, `userFillsByTime`, `historicalOrders`, `userFunding` and others add weight per 20 items returned.
  - WebSocket: at most 10 connections, 30 new connections per minute, 1,000 subscriptions, "10 unique users across user-specific websocket subscriptions", and 2,000 messages sent per minute.
  - Source: [HL docs: Rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)
- Live verification (2026-10-21), without credentials, of a third-party address (the Growi HF vault):
  - `clearinghouseState` returned account value $13.69M and open positions (for example BTC).
  - `userFills` returned 2,000 fills with price, size, direction, closedPnl and fee.
  - `openOrders` returned [].
  - Source: [Live API](https://api.hyperliquid.xyz/info)
- Bulk and discovery data:
  - The public leaderboard JSON returned 47,733 accounts, each with account value and day, week, month and all-time PnL, ROI and volume.
  - The full vault list returned 9,478 vaults with TVL, APR and PnL series.
  - Sources: [Live leaderboard](https://stats-data.hyperliquid.xyz/Mainnet/leaderboard); [Live vault list](https://stats-data.hyperliquid.xyz/Mainnet/vaults)
- Historical bulk data:
  - Fills are streamed from a non-validating node (`--write-fills`) to the `s3://hl-mainnet-node-data/node_fills_by_block` bucket, requester pays.
  - L2 snapshots and asset contexts are in `s3://hyperliquid-archive`, about monthly, with "no guarantee of timely updates".
  - Source: [HL docs: Historical data](https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data)

### Inferences
- Hyperliquid makes leader discovery and real-time mirroring trivially permissionless: any wallet's trades can be copied without that trader's consent. Copy services on Hyperliquid can therefore track arbitrary "smart money", not just opted-in leaders. This is a structural advantage that Mirrorlane must check against Lighter's data model.
- With 10 unique users per IP on WebSocket, a service tracking hundreds of leaders needs either a fleet of IPs or a self-hosted non-validating node that streams all fills. Serious copy-trading operators likely run their own node; this is inferred, not confirmed.
- Polling `clearinghouseState` at weight 2 allows about 600 position snapshots per minute per IP. That suits slower position-diff copying, not tick-level mirroring.

### Gaps
- No live test of WebSocket subscriptions to arbitrary users was run; the docs and REST behaviour indicate it works.
- Whether a self-hosted non-validating node streams every user's fills in real time with acceptable latency was not benchmarked.

## 7. Fee schedule and overall traction (context)

### Takeaway
Base perp fees are 4.5 bps taker and 1.5 bps maker, falling to 2.4 / 0 bps at the top volume tier. Staking HYPE cuts fees by 5–40%, and maker rebates go up to −0.3 bps. All fees go to the community (HLP, the HYPE-burning assistance fund, and deployers).

As of October 2026 Hyperliquid generated about $85M in fees over 30 days and about $907M over the past year, per DefiLlama. Open interest on validator perps was about $11.9B and 24-hour notional volume about $5.2B on 2026-10-21. Hyperliquid holds more than 56% of on-chain perp open interest.

### Cited Findings
- Perp fee tiers by 14-day weighted volume, where weighted volume = perps + 2 × spot:

| Tier | 14-day volume | Taker | Maker |
|---|---|---|---|
| 0 | — | 0.045% | 0.015% |
| 1 | >$5M | 0.040% | 0.012% |
| 2 | >$25M | 0.035% | 0.008% |
| 3 | >$100M | 0.030% | 0.004% |
| 4 | >$500M | 0.028% | 0% |
| 5 | >$2B | 0.026% | 0% |
| 6 | >$7B | 0.024% | 0% |

  Spot runs from 0.070% / 0.040% down to 0.025% / 0%. Source: [HL docs: Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- Staking discounts:

| Tier | HYPE staked | Fee discount |
|---|---|---|
| Wood | >10 | 5% |
| Bronze | >100 | 10% |
| Silver | >1,000 | 15% |
| Gold | >10,000 | 20% |
| Platinum | >100,000 | 30% |
| Diamond | >500,000 | 40% |

  Source: [HL docs: Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- Maker rebates: −0.001%, −0.002% and −0.003% for more than 0.5%, 1.5% and 3.0% of 14-day maker volume share, paid continuously — [HL docs: Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- Account aggregation: sub-account volume counts toward the master account's tier, while "Vault volume is treated separately from the master account" — [HL docs: Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- Fee destination: fees go "entirely… to the community (HLP, the assistance fund, and deployers)". The assistance fund converts fees to HYPE, which is burned — [HL docs: Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- HIP-3 growth mode cuts fees by 90% or more for markets disjoint from crypto — [HL docs: Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- DefiLlama fees as of 2026-10-21:

| Window | Fees | Revenue |
|---|---|---|
| 24 hours | $3.11M | $2.39M |
| 30 days | $85.4M | $68.5M |
| 1 year | $906.9M | $690.3M |
| All-time | $1.68B | $1.359B |

  Source: [DefiLlama API (fees/hyperliquid)](https://api.llama.fi/summary/fees/hyperliquid)
- TokenPost (2026-10-10): cumulative protocol revenue exceeds $1.4B, more than $1.26B has been used for HYPE buybacks, and Hyperliquid's share of on-chain perp OI exceeds 56% — [TokenPost](https://www.tokenpost.com/news/investing/29363)
- Live API (2026-10-21), validator-operated perps only (excluding HIP-3 DEXs): about $11.91B of open interest and about $5.15B of 24-hour notional volume across 234 listed assets — [Live API metaAndAssetCtxs](https://api.hyperliquid.xyz/info)
- The Block reported OI of about $14.3B on 2026-09-08 — [The Block](https://www.theblock.co/news/ecosystems/2026-09-08-hyperliquid-open-interest-climbs-14-3-billion-hype-hits-all-time-high-413855) (page not opened, 403; search summary)
- TokenPost reported a record 11.4% share of aggregate perp OI across centralized and decentralized venues in late September 2026 — [TokenPost](https://www.tokenpost.com/news/investing/24540) (page not opened; search summary)

### Inferences
- A copy-trading front-end on Hyperliquid stacks its builder fee on top of a 4.5 bps base taker fee. A follower paying a 10 bps maximum builder fee pays about 14.5 bps all-in per fill. That is a useful benchmark when Mirrorlane prices on Lighter, which advertises zero-fee retail trading; the other researcher should verify Lighter's fees.
- Fees in 2026 appear lower than at the 2025 peak: the 30-day figure ($85M) annualises to about $1.0B, close to the trailing one-year $907M. This suggests flat activity rather than growth. It is a rough inference.

### Gaps
- No full-month September or October 2026 perp volume total was found. DefiLlama's derivatives-volume endpoint now requires a paid plan.
- HIP-3 DEX OI and volume were not included in the live totals.
