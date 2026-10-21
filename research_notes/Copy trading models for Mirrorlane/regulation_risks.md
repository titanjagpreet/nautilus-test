# Regulation of Copy Trading (incl. Crypto-Perp Copy Trading) and Documented Risks of Copy-Trading Products

Research date: 21 October 2026. Background for a business decision, not legal advice. Every source is dated where a date could be found. "Older rule" or "superseded" is flagged inline. Inferences are kept separate from verified findings. Several sources are secondary (law-firm alerts, trade press, vendor blogs) and are marked as such. Primary regulator texts were read directly where reachable: ESMA 2023 briefing, ESMA Q&A 2463, ESMA Feb-2026 perps statement, FCA copy-trading page, CFTC releases, eCFR, Lighter ToS, eToro US disclosure, and the CHI-2024 and Apesteguia et al. papers.

---

## 1. EU: how ESMA and NCAs classify copy trading (MiFID II, MiCA, crypto derivatives), and recent warnings or enforcement

### Takeaway
In the EU, automatic copy trading with no client action per trade is **portfolio management**. When the client confirms each trade, it is **investment advice and/or RTO (reception and transmission of orders) or execution**. This has been ESMA's position since 2012, restated in 2023 and extended "mutatis mutandis" to MiCA in April 2025. Crypto perpetuals are not MiCA crypto-assets: they are MiFID II derivatives. Since 24 Feb 2026 ESMA has said they are "likely" CFDs subject to the national CFD product-intervention measures (retail leverage caps, which commentators put at 2:1 for crypto, plus negative-balance protection, a ban on incentives, and so on). Custody is not part of the classification test. The test is who takes the trade decision.

### Cited Findings
**Classification (MiFID II)**
- **ESMA Q&A 9 (June 2012; still relevant, references updated to MiFID II):** automatic execution of orders based on third-party trade signals is portfolio management where "the order execution is automatic and does not require any further action from the client". Where client action is required per trade, other services may apply instead (advice, RTO). ESMA says the 2012 Q&A "remains relevant for copy trading business models since the majority of copy trading service providers provide for automatic execution". — [ESMA Supervisory Briefing on copy trading, ESMA35-42-1428, 30 Mar 2023](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf)
- **The 2023 briefing covers:** service qualification; information and marketing; costs and charges; product governance; suitability and appropriateness; remuneration and inducements; and copied-trader qualifications. It is non-binding and not "comply or explain". — [ESMA briefing, 30 Mar 2023](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf); [ESMA press release](https://www.esma.europa.eu/press-news/esma-news/esma-provides-guidance-supervision-copy-trading-services)
- **Points that close off common "it's just a tool" arguments (ESMA 2023 briefing, paras 22–33 and fn 22):**
  - "auto-copy" or "auto-follow" buttons are themselves the discretionary "mandate".
  - A time window in which the client can approve, modify or cancel, after which the trade executes anyway, is still portfolio management.
  - Letting clients set leverage limits, stop-losses or close positions does not stop it being portfolio management.
  - "An ex-ante bulk approval (a blank check) or stop loss limit orders are not considered interventions on a transaction basis".
  - "If… one single firm is involved… and the firm has a (direct) link to the copied traders, then it seems highly unlikely that this firm is only providing execution services." — [ESMA briefing](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf)
- **Where a client copies trades seen on social media and places orders themselves:** the broker is likely only executing, but "the trades that are being shared on social media could still qualify as investment advice provided by the copied trader". — [ESMA briefing, para 30](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf)
- **Copied traders as "experts":** copied traders who present themselves as having expertise may be "experts" under the MAR Delegated Regulation Art. 1(a), with conflict-of-interest disclosure duties (Art. 6 MAR DR). Firms must ensure copied traders "meet requirements concerning their minimum skill, trading experience or knowledge". — [ESMA briefing, paras 72–74](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf)
- **Remuneration conflicts:** ESMA flags variable pay for copied traders based on "number and value of trades copied", "number of followers" or AUM. Payments to copied traders may be "inducements" under Art. 24(9) MiFID II, and the copying client must be informed. — [ESMA briefing, section 2.6](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf)
- **Marketing of leader performance:** past performance must not be the most prominent element. It must cover 5 years, or the available complete 12-month periods. Simulated past performance must not be used for future-performance claims. Gross figures must disclose fee effects. — [ESMA briefing, section 2.3](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf)

**MiCA**
- **ESMA Q&A 2463 (answer 7 Apr 2025):** the MiFID II copy-trading guidance (Q&A 9 and briefing §§2.1–2.2) "applies, mutatis mutandis, to copy trading services under MiCA but regarding only the qualification of what type of crypto-asset service(s) are provided". The MiCA services in question are "providing portfolio management of crypto-assets", advice, and RTO. CASPs must assess "case-by-case". — [ESMA_QA_2463 (copy)](https://www.dirittobancario.it/wp-content/uploads/2025/04/ESMAQA2463.pdf)
- **MiCA transitional period:** it ended at the latest on 1 July 2026 (Art. 143(3)); some Member States ended it earlier. A secondary source says ESMA stated in April 2026 that from 1 July 2026 anyone serving EU clients without a MiCA licence is in breach and must stop. — [Zyphe (secondary), 2026](http://zyphe.com/resources/news/mica-transitional-period-ends-july-2026). Primary ESMA text not retrieved.
- **DeFi carve-out:** MiCA Recital 22 excludes services provided "in a fully decentralised manner without any intermediary". Commentators stress that a recital is not an exemption, and that authorities look for an identifiable controller such as a "front-end operation, fee capture, admin keys, governance control, order matching". — [Legal Bison (secondary, undated, 2025–26)](https://legalbison.com/blog/defi-protocols-under-mica/)

**Crypto perpetual futures are MiFID derivatives, likely CFDs**
- **ESMA Public Statement ESMA35-243228190-8024 (24 Feb 2026):** derivatives "often marketed as perpetual futures or perpetual contracts" giving leveraged exposure to crypto-assets "are likely to fall within the scope" of the national CFD product-intervention measures, which mirror ESMA Decision 2018/796. These measures include "leverage limits, a mandatory risk warning, a margin close-out and negative balance protection, and the prohibition of monetary and non-monetary benefits". The statement also says:
  - "the commercial name… is irrelevant".
  - Being traded on a venue, having a funding-rate mechanism, or voluntary negative-balance protection or "insurance funds" are "not relevant to this assessment".
  - Firms should expect a "narrow target market". Mass marketing and "get started now" pop-ups are inconsistent with that.
  - Appropriateness tests are required for non-advised services, and PRIIPs KIDs are required ("packaged investment products").
  - "participating in circumvention activities… is prohibited". — [ESMA statement (copy)](https://www.dirittobancario.it/wp-content/uploads/2026/02/Dichiarazione-ESMA-24-febbraio-2026-ESMA35-243228190-8024.pdf); NCA relay: [MFSA circular, Mar 2026](https://www.mfsa.mt/wp-content/uploads/2026/03/Circular-on-ESMA-Public-Statement-Identifying-Derivatives-within-the-Scope-of-CFDs-National-Product-Intervention-Measures.pdf)
- **Leverage cap:** commentators read the statement as implying the 2:1 retail leverage cap for crypto CFDs from the 2018 measures. — [Finance Magnates, Feb 2026](https://www.financemagnates.com/forex/regulation/esma-tells-firms-perpetual-futures-fall-under-eu-cfd-rules/). The 2:1 figure is not in the statement text itself; it comes from the 2018 ESMA decision.
- **Trade-press view on DEXs:** trade press argues the ESMA logic makes DEX perps such as Hyperliquid's "look increasingly like CFDs in DeFi clothing". — [FinTelegram, 2026](https://fintelegram.com/esma-draws-the-line-why-hyperliquids-crypto-perpetuals-look-increasingly-like-cfds-in-defi-clothing/) (commentary)

**How large CEXs handle the EU**
- **Bybit:** Bybit EU GmbH holds an Austrian FMA MiCA CASP licence. Sources conflict on whether Bybit EU offers derivatives or copy trading. Bybit has said it is seeking a MiFID licence for EU derivatives. — [CASP Tracker (secondary, 2026)](https://casptracker.eu/exchange/bybit/); [Finance Magnates, ~2025](https://www.financemagnates.com/cryptocurrency/bybit-pursues-mifid-license-for-eu-derivatives-phases-out-mt5-for-in-house-trafi/)
- **Bitget:** as of an ESMA register check on 7–16 Oct 2026, Bitget had no MiCA authorisation (it applied in Austria in July 2026). Its terms list Austria, France and Germany as prohibited. — [CASP Tracker (secondary), Oct 2026](https://casptracker.eu/exchange/bitget/)

**International baseline (IOSCO)**
- **IOSCO Final Report FR/06/2025, "Online Imitative Trading Practices: Copy Trading, Mirror Trading and Social Trading" (May 2025), published alongside reports on finfluencers and digital engagement:**
  - Copy traders may imitate strategies unsuited to them.
  - Leveraged losses and fees erode returns.
  - Lead-trader remuneration creates conflicts.
  - Imitative trading overlaps with finfluencers.
  - Cross-border provision makes enforcement difficult.
  - Its non-binding Good Practices cover monitoring lead traders and outcomes, disclosure, marketing standards, and assessing whether activity amounts to advice. — [IOSCO FR/06/2025](https://www.iosco.org/library/pubdocs/pdf/IOSCOPD793.pdf); summaries: [Cadwalader](https://www.cadwalader.com/fin-news/index.php?eid=932&nid=128), [Investment Executive](https://www.investmentexecutive.com/news/from-the-regulators/iosco-tackles-retail-harm-from-online-innovation/). The full PDF was Cloudflare-blocked, so content is via secondary summaries. Consultation version: [CR/10/2024](https://www.iosco.org/library/pubdocs/pdf/IOSCOPD776.pdf).

### Inferences
- A Mirrorlane feature that auto-mirrors a leader's Lighter perp trades into EU retail users' accounts would most likely be treated in the EU as **MiFID II portfolio management in CFDs**. That requires MiFID authorisation, suitability assessment, periodic reporting, 2:1 retail leverage, a ban on incentives, a narrow target market, and PRIIPs KIDs. This is commercially incompatible with a typical perps-DEX copy product. The MiCA route does not help, because perps are financial instruments rather than MiCA crypto-assets.
- Non-custody (agent keys, the user's own wallet) does **not** change the characterisation under ESMA's test, which focuses on who takes the decision and whether the client acts per trade. Non-custody mainly avoids additional custody and safekeeping regimes.
- "Fully decentralised" arguments are weak for an identifiable company that runs a branded front-end, charges fees, curates a leader list, or pays leaders.
- The lowest-risk EU posture is one of: (a) geo-excluding EU retail from any auto-copy feature; (b) limiting EU users to self-directed tools where each order is user-initiated and user-signed, with no curated or ranked leaders and no leader compensation; or (c) partnering with or becoming an authorised firm. Even per-trade-confirm signal display can be "advice" or RTO. Leader posts can be "advice" by the leader.

### Gaps
- No ESMA or NCA enforcement case specifically against a DeFi copy-trading front-end was found.
- No NCA-specific copy-trading circulars (CySEC, BaFin, AMF, CONSOB) were retrieved. CySEC and BaFin positions are reported only by secondary or broker sources and are not verified.
- The IOSCO final-report text could not be read directly (Cloudflare 403). No 2025–26 ESMA finfluencer-specific statement was retrieved.
- Whether ESMA's perps statement reaches unauthorised offshore or DeFi front-ends (as opposed to authorised "firms") is not addressed in the statement. Enforcement against those would run through national unauthorised-activity rules (inference).

---

## 2. UK: FCA position on copy trading and crypto derivatives, and enforcement

### Takeaway
The FCA treats automatic copy and mirror trading as **portfolio or investment management** requiring authorisation. Client-set parameters (amount, max loss) do not change this. Only per-trade client action, or signals "fully determined by the client", fall outside. Retail sale of crypto derivatives has been **banned since 6 Jan 2021** and the ban remains in place (the crypto ETN ban was lifted in 2025). Lighter's own ToS excludes the UK. Finfluencer enforcement for unauthorised CFD and forex promotions is active, with criminal convictions in 2026.

### Cited Findings
- **FCA "Copy trading" page (first published 12 May 2015; last updated 27 Jul 2026):** "We classify copy trading as portfolio or investment management where no manual input is clear from the account holder." The FCA "support[s]" ESMA's Q&A 9. "Where the client sets trading parameters, such as the sum they wish to invest or are prepared to lose, this will not affect the characterisation of the service as portfolio management."
  - **Exceptions:** (i) client must confirm each recommendation before execution, which may still be advice or RTO; (ii) "The trade signals are fully determined by the client, who must set the detailed limits for each signal/order/transaction, such as the precise market conditions that will trigger a particular signal."
  - **Older wording:** the page still cites old MiFID Art. 4(1)(9) numbering. — [FCA, Copy trading](https://www.fca.org.uk/firms/copy-trading)
- **Retail crypto-derivatives ban:** PS20/10 prohibits the sale, marketing and distribution to retail clients of crypto-asset derivatives and ETNs (COBS 22.6), effective January 2021. — [FCA PS20/10](https://www.fca.org.uk/publications/policy-statements/ps20-10-prohibiting-sale-retail-clients-investment-products-reference-cryptoassets); [FCA Handbook COBS 22.6](https://handbook.fca.org.uk/handbook/cobs22/cobs22s6)
- **The derivatives ban stays:** when lifting the crypto-ETN ban (2025), the FCA said the ban on retail access to crypto derivatives "will remain in place". — [FCA press release, 2025](https://www.fca.org.uk/news/press-releases/fca-lift-ban-crypto-exchange-traded-notes)
- **New UK crypto regime:** per the FCA, crypto will be regulated from October 2027, with authorisation applications opening September 2026. — [FCA press release (2026)](https://www.fca.org.uk/news/press-releases/fca-consults-guidance-uk-future-crypto-regime). The copy-trading treatment within the new regime was not found.
- **Finfluencer enforcement:**
  - In June 2025 the FCA led an international action with 9 regulators across 6 countries: arrests, cease-and-desist letters, and over 650 takedown requests.
  - Three finfluencers (Hunter, Kalipha, Desmaris) were charged over promoting CFD forex trading. They pleaded not guilty, with a hearing on 8 Oct 2025. — [FCA press release, Sept 2025](https://www.fca.org.uk/news/press-releases/first-court-appearance-three-finfluencers-charged-fca-led-global-crackdown-illegal-promotions)
  - In Feb 2026, seven influencers were sentenced at Southwark Crown Court after pleading guilty to issuing unauthorised financial promotions for a CFD forex scheme. Fines were small (largest £3,750). — [Insurance Edge, 23 Feb 2026](https://insurance-edge.net/2026/02/23/finfluencers-fined-for-foreign-exchange-scheme/); [MPA, 2026](https://www.mpamag.com/uk/news/general/social-media-influencers-fined-over-unauthorised-financial-promotions/566284)
- **Lighter excludes the UK:** Lighter's ToS (last updated 29 Dec 2025) state the services are "not available to persons or entities who reside in, are located in… the United Kingdom" (among others). — [Lighter Terms of Service](https://lighter.xyz/terms)

### Inferences
- Serving UK users with an auto-copy feature on crypto perps would combine three problems: (i) an unauthorised portfolio-management activity; (ii) promotion or distribution of a product the FCA bans for retail; and (iii) breach of Lighter's own terms. The UK should be geo-excluded for any trading functionality. Even marketing to UK users (including via paid influencers or leaders) risks s.21 FSMA financial-promotion offences.
- The FCA's "signals fully determined by the client" exception supports a narrow safe space: user-authored rule-based automation (for example "sell if price < X") is not portfolio management. Following a third party's signals is not covered by that exception.

### Gaps
- No FCA enforcement action specifically against a copy-trading platform was found. The page states the position; enforcement examples are for finfluencers and CFD promotions.
- How copy trading of crypto (spot) will be treated under the October 2027 UK crypto regime (CP25/40-series) was not retrieved.

---

## 3. US: CFTC/NFA (CTA, CPO), SEC (vaults, front-ends), offshore perps access, and DEX geo-blocking

### Takeaway
Under CFTC rules, a person who **"directs"** client commodity-interest accounts (causes trades without the client's specific authorisation) is a commodity trading advisor (CTA). Directing accounts disqualifies the standard exemption for non-tailored advice (Rule 4.14(a)(9)). Pooled vaults trading perps are classic commodity-pool and CPO territory.

The CFTC's 2023 DeFi cases treated perps as swaps or leveraged retail commodity transactions. It held a **front-end operator** (0x/Matcha) liable for third-party leveraged products and found **IP-blocking insufficient** (Opyn).

2026 brought a pro-onshoring shift:
- The first US-listed perp (May 29, 2026).
- An FCM route for US customers to reach offshore perps.
- A CFTC no-action letter for a self-custodial wallet front-end (DCM-only).
- An SEC staff statement for non-custodial interfaces, which expressly excludes discretion, custody and order routing.

None of these blesses an unregistered front-end auto-copying offshore DEX perps for US persons. The CLARITY Act stalled in Sept 2026. Lighter's terms exclude US persons.

### Cited Findings
**CTA, CPO and directing accounts**
- **Definitions:** 17 CFR 4.10(f): "Direct… refers to agreements whereby a person is authorized to cause transactions to be effected for a client's commodity interest account without the client's specific authorization." 4.10(g): a "trading program" includes directing accounts or guiding trading "by means of a systematic program that recommends specific transactions." — [eCFR §4.10](https://www.ecfr.gov/current/title-17/chapter-I/part-4/subpart-A/section-4.10)
- **The 4.14(a)(9) exemption:** CTA registration is not required for a person who "does not engage in… (i) Directing client accounts; or (ii) Providing commodity trading advice based on, or tailored to… particular clients". Separately, 4.14(a)(10) covers advice to ≤15 persons with no holding out to the public. — [eCFR §4.14](https://www.ecfr.gov/current/title-17/chapter-I/part-4/subpart-A/section-4.14)
- **CPO framework:** the CFTC reads "commodity pool" broadly. Dodd-Frank extended it to vehicles trading swaps. CPOs must register unless exempt. — [Mayer Brown, "US Commodity Pool and CPO Regulation", Mar 2026](https://www.mayerbrown.com/-/media/files/perspectives-events/events/2026/03/commodity-pool-and-cpo-regulation.pdf?rev=f2748ed99b8645bd8990b69e8d112812)

**DeFi and front-end enforcement (2022–2023; older, but not withdrawn as far as found)**
- **Opyn, ZeroEx (0x) and Deridex, settled 7 Sep 2023** (penalties $250k / $200k / $100k):
  - Deridex's "perpetual contracts" were swaps and leveraged retail commodity transactions. It operated as an unregistered SEF, acted as an unregistered FCM, and had no CIP.
  - Opyn blocked US IPs, but "those steps were not sufficient to actually block U.S. users".
  - ZeroEx (Matcha front-end) was charged with illegally offering leveraged retail commodity transactions, via third-party tokens accessible through its interface.
  - Enforcement Director: "DeFi operators got the idea that unlawful transactions become lawful when facilitated by smart contracts. They do not."
  - Commissioner Mersinger dissented. — [CFTC Release 8774-23](https://www.cftc.gov/PressRoom/PressReleases/8774-23); [McDermott, 2023](https://www.mcdermottlaw.com/insights/cftc-crackdown-three-defi-platforms-face-enforcement-actions/)
- **Ooki DAO:** default judgment of 8–9 Jun 2023. It imposed a $643,542 penalty, permanent trading and registration bans, and a website takedown reaching hosting and domain providers. — [CFTC Release 8715-23](https://www.cftc.gov/PressRoom/PressReleases/8715-23)
- **Polymarket:** CFTC order of 3 Jan 2022. It imposed a $1.4M penalty and required wind-down of non-compliant markets. Polymarket subsequently geo-blocked US users. — [The Block, Jan 2022](https://www.theblock.co/post/129047/crypto-prediction-market-platform-polymarket-settles-with-cftc-for-1-4-million)

**Copy-trading fraud precedent**
- **Mirror Trading International (MTI), an automated "mirror trading" forex/BTC scheme:**
  - CFTC complaint 30 Jun 2022.
  - Default judgment against CEO Steynberg, 24 Apr 2023: $1,733,838,372 restitution plus an equal civil penalty, the highest in CFTC history. At least 29,421 BTC was collected and mostly misappropriated.
  - Consent order against MTI, Sep 2023: >$1.7B restitution. — [CFTC Release 8696-23](https://www.cftc.gov/PressRoom/PressReleases/8696-23); [CFTC Release 8772-23](https://www.cftc.gov/PressRoom/PressReleases/8772-23)

**2026 shift (current)**
- **CFTC actions of 29 May 2026:**
  - It approved Kalshi's BTC perpetual contract as a **futures** contract under Reg. 40.3, the first US-listed "true" perp. Classification is case-by-case and limited to digital commodities with "deep, active, and continuous spot market trading".
  - A Policy Statement asks exchanges to seek prior approval rather than self-certify.
  - A staff letter to Coinbase Financial Markets (an FCM) lets certain perps on its affiliated foreign board of trade be treated as "foreign futures" (Reg. 30.1), with no-action relief on crypto/stablecoin margin.
  - A 24/7 trading advisory was issued.
  - Before this, perps were "largely understood" to be swaps. — [Dechert, 9 Jun 2026](https://www.dechert.com/knowledge/onpoint/2026/6/cftc-takes-historic-steps-to-bring-digital-asset-perpetual-contr.html); [CoinDesk, 3 Mar 2026](https://www.coindesk.com/policy/2026/03/03/cftc-chief-selig-to-clear-path-for-u-s-perpetual-futures-in-coming-weeks)
- **CFTC No-Action Letter 26-09 (17 Mar 2026, Phantom):** no-action on introducing-broker registration for a self-custodial wallet front-end, but only for trading on CFTC-regulated DCMs, with roughly 10 conditions. The software may not take custody, "generat[e] buy or sell signals", or exercise "discretion over the routing or execution of individual transactions". It does not address DeFi protocols. — [Manatt, 2026](https://www.manatt.com/insights/newsletters/client-alert/the-cftc-just-drew-a-line-between-wallets-and-brokers-here-s-what-it-actually-says); [JD Supra, 2026](https://www.jdsupra.com/legalnews/cftc-no-action-letter-for-self-7918636/). Letter text not read directly.
- **SEC Trading & Markets staff statement on "Covered User Interfaces" (13 Apr 2026; deemed withdrawn 14 Apr 2031 absent SEC action):**
  - It applies only to crypto asset **securities** traded via self-custodial wallets.
  - Compensation must be fixed and product/venue-agnostic, with no PFOF.
  - Prohibited: soliciting specific transactions, making recommendations, "Exercising any control or discretion over… securities transactions", holding or accessing user funds, executing or settling, and "Taking or routing orders".
  - No relief for custodial wallets or for the venues themselves.
  - Possible state-law exposure remains. — [Dechert, Apr 2026](https://www.dechert.com/knowledge/onpoint/2026/4/sec-staff-provides-relief-for-crypto-wallet-interfaces.html); [Sidley, 21 Apr 2026](https://datamatters.sidley.com/2026/04/21/u-s-sec-clears-path-for-decentralized-crypto-asset-security-trading-with-broker-registration-exception-for-user-interfaces/); [McDermott, 2026](https://www.mcdermottlaw.com/insights/secstatement-broker-dealer-registration-crypto-user-interfaces/)
- **CLARITY Act:** Senate cloture failed 49–50 on 15 Sep 2026. The bill is stalled and likely to slip into 2027. The treatment of DeFi front-ends is among the open disputes. — [DLA Piper, Sep 2026](https://www.dlapiper.com/en/insights/publications/2026/09/senate-fails-to-advance-the-clarity-act); [Orrick, Oct 2026](https://www.orrick.com/en/Insights/2026/10/The-CLARITY-Act-Stalls-in-the-Senate-Whats-Next-for-Digital-Asset-Regulation)
- **Hyperliquid and US regulators:**
  - Hyperliquid Labs told the CFTC (comment letter, 21 May 2025) that its front-end ToU prohibit US persons. — [CFTC comment file](https://comments.cftc.gov/Handlers/PdfHandler.ashx?id=35634)
  - CME and ICE urged US regulators to scrutinise Hyperliquid over manipulation and sanctions risk (May 2026). — [CoinDesk, 15 May 2026](https://www.coindesk.com/markets/2026/05/15/cme-ice-push-u-s-regulators-to-scrutinize-hyperliquid-over-manipulation-risks-bloomberg)
  - Reports (Aug 2026) that the CFTC is "working to onshore" Hyperliquid. — [The Defiant, 2026](https://thedefiant.io/news/regulation/trump-says-cftc-working-to-onshore-hyperliquid)
  - Hyperliquid and dYdX geo-block US IPs at the front-end. — [OneKey (secondary)](https://onekey.so/blog/ecosystem/geo-block-hyperliquid-dydx-us/)
- **Lighter:** the ToS (29 Dec 2025, operator "Elliot Technologies, Inc.") exclude persons residing or located in, or incorporated in, the US, Canada, UK, China, North Korea, Russia, Ukraine, Cuba, Iran, Venezuela, Syria. One version of the list on the same page also includes Sudan, Belarus and Myanmar. — [Lighter ToS](https://lighter.xyz/terms). Lighter's Robinhood-Chain perps also restrict the US. — [Lighter docs](https://docs.lighter.xyz/points-program/lighter-on-robinhood-chain-points)
- **eToro US positioning (an onshore, SEC/FINRA BD model):** eToro US frames CopyTrader as a "self-directed tool", "not an investment advice tool", with "no discretionary authority". Popular Investors are "not paid by eToro in the USA". There are no CopyTrader-specific fees. Products are spot stocks/ETFs (via a BD) and spot crypto (via an MSB), not derivatives. eToro still states that "no pre-approval request or notice is sent to you before those trades are executed". — [eToro "Let's Talk About CopyTrader", Oct 2025](https://www.etoro.com/wp-content/uploads/2025/10/Lets-Talk-About-CopyTrader-disclosure-October-2025.pdf)

### Inferences
- **For US persons:**
  - Auto-copy of perps = "directing" accounts = CTA, with no 4.14(a)(9) exemption. A profit-sharing leader looks like an unregistered CTA, and the platform may be an IB, CTA or FCM-like actor.
  - A vault or pool = commodity pool, so the operator is a CPO. Securities "investment contract" risk sits on top where profits come from a manager's efforts. That is not tested here; no source found.
  - Offshore DEX perps for US retail remain off-exchange swaps or leveraged retail commodity transactions. The 2026 relief runs through DCMs and FCMs only.
- **Exclude US persons from all trading features.** This matches Lighter's own ToS. The Opyn finding means IP-blocking alone may be judged insufficient. Wallet attestations, VPN/IP heuristics, and sanctions screening strengthen the record.
- Both 2026 front-end reliefs (SEC statement, CFTC NAL 26-09) draw the line at discretion, signal generation, routing, and custody. A copy-trading engine sits on the wrong side of each line. They offer a template for a pure self-directed terminal, not for copy trading.
- **The eToro US model shows what "tool" positioning requires in practice:** no leader compensation, no recommendations or curation, no extra fee, and an onshore registered BD/MSB doing execution. That is very different from a DEX front-end paying leaders a profit share.

### Gaps
- No US enforcement action specifically against a crypto copy-trading front-end or a DEX vault leader was found. No SEC statement on Hyperliquid-style vaults as investment contracts was found. No law-firm analysis of vault leaders as CPOs was found.
- Full NAL 26-09 conditions and the SEC statement text were not read directly; the summaries above are from law firms.
- State-level (money transmission, state securities) exposure was not researched.

---

## 4. Other jurisdictions: Singapore (MAS), UAE/Dubai (VARA), Hong Kong (SFC), Australia (ASIC)

### Takeaway
Asia-Pacific and Gulf hubs restrict retail crypto leverage heavily and license any intermediary that executes or manages client crypto trades:
- **Singapore:** bans leveraged DPT trading and derivatives for retail. Since 30 Jun 2025 it effectively bars Singapore-based firms from serving only overseas users without a licence.
- **Hong Kong:** allows perps only for professional investors on licensed platforms (2026).
- **Dubai:** treats order-transmitting copy platforms as Broker-Dealers (with Management & Investment licences for discretion) and caps retail leverage.
- **Australia:** sued eToro over CFD target markets.

No regulator-specific copy-trading guidance was found for MAS, SFC or VARA.

### Cited Findings
- **Singapore, retail restrictions:** MAS Guidelines PS-G03 (revised Sep 2024) prohibit DPT service providers from offering retail customers credit or leveraged transactions, "including margin trading, DPT futures, options and other derivative transactions", or facilitating leveraged trades with third parties. Trading and referral incentives are banned. — [Rahmat Lim & Partners, 2024](https://rahmatlim.com/publication/articles/29214/mas-issues-revised-guidelines-on-provision-of-consumer-protection-safeguards-by-digital-payment-token-service-providers); [Linklaters, 2023](https://techinsights.linklaters.com/post/102ituh/securing-the-future-mas-unveils-final-consumer-access-and-other-regulatory-measu)
- **Singapore, DTSP regime:** Part 9 of the FSM Act came into force 30 Jun 2025. Singapore entities providing digital-token services only outside Singapore must be licensed or cease, with no transition. Licences are granted only in "extremely limited circumstances". Penalties reportedly run up to S$250k and 3 years' imprisonment. — [Lexology, 2025](https://www.lexology.com/library/detail.aspx?g=ab240df8-90b0-4ca3-93d2-569db8534ff9); [Blockhead, 2 Jun 2025](https://www.blockhead.co/2025/06/02/mas-sets-hard-june-30-deadline-for-unlicensed-crypto-firms-serving-overseas-clients/)
- **Hong Kong:**
  - In Feb 2026 the SFC published a framework letting licensed VA trading platforms offer perpetual contracts to **professional investors only**, with derivative-knowledge assessments, and permitting affiliated market makers. — [Davis Polk, 2026](https://www.davispolk.com/insights/client-update/hong-kong-permit-va-exchanges-offer-perpetual-contracts-and-engage); [Charltons, 2026](https://www.charltonslaw.com/sfc-virtual-asset-update-new-guidance-on-va-margin-financing-perpetual-contracts-and-affiliated-market-makers/)
  - Older SFC warning (c. 2019): no one is licensed to offer VA futures in HK, and platforms doing so "may potentially be operating illegally". — [SFC warning](https://www.sfc.hk/en/News-and-announcements/Policy-statements-and-announcements/SFC-issues-warnings-on-virtual-asset-futures-contracts) (older; partly superseded by the 2026 framework for licensed platforms)
- **Dubai (VARA):**
  - Law-firm guidance places "copy-trading platforms where the operator transmits client orders" in Broker-Dealer Services, and discretionary portfolio management in VA Management & Investment Services. Fees are roughly AED 100k application and AED 200k per activity per year. — [NeoLegal (secondary, 2026)](https://neolegal.ae/insights/do-i-need-a-vara-licence)
  - The VARA rulebook update (May 2025) tightened margin-trading controls. — [CoinDesk, 19 May 2025](https://www.coindesk.com/policy/2025/05/19/vara-fortifies-controls-on-crypto-margin-trading-in-dubai-refreshes-rulebook)
  - March 2026 rules impose margin, governance and disclosure requirements on crypto trading and derivatives. Reports cite a retail leverage cap of about 5x. — [The Block, 31 Mar 2026](https://www.theblock.co/news/regulation/2026-03-31-dubais-vara-imposes-margin-governance-and-disclosure-rules-on-crypto-trading-and-derivatives-395873)
- **Australia (ASIC):** in Aug 2023 ASIC sued eToro (its first design-and-distribution action), alleging the CFD target market was "far too broad" and the screening test weak. — [ASIC 23-204MR, Aug 2023](https://asic.gov.au/about-asic/news-centre/find-a-media-release/2023-releases/23-204mr-asic-sues-etoro-in-its-first-design-and-distribution-action-to-protect-consumers-from-high-risk-cfd-products/)

### Inferences
- None of these hubs offers an easy home for a retail-facing auto-copy product on offshore perps. Singapore incorporation would be especially risky because of the DTSP "overseas-only" rule. Dubai is possible but means a VARA Broker-Dealer and/or Management licence with leverage caps. Hong Kong is professional-investor only.

### Gaps
- No MAS, SFC or VARA document specifically on copy or social trading was found.
- The outcome of ASIC v eToro (judgment or settlement) was not found.
- Japan, Korea, Canada (which Lighter excludes), Brazil and Turkey were not researched.
- DIFC (DFSA) and ADGM (FSRA) treatment was not researched.

---

## 5. How existing products manage this: geo-blocking, leader KYC, "software tool" ToS positioning, non-custodial agent wallets vs custodial API keys, vaults

### Takeaway
The industry pattern has five parts:
- Exclude the US (and often the UK and Canada) via ToS and IP blocks.
- Run regulated entities per region where copy trading is offered (eToro's BD/MSB in the US; Bybit's MiCA entity in the EU).
- Describe copy features as "self-directed tools" with no discretion or advice.
- Vet or limit leaders ("Popular Investor" criteria, risk-score thresholds, follower caps).
- Increasingly fix gameable leaderboard maths.

Regulators look through labels to who decides trades. Custodial API-key models carry demonstrated catastrophic security risk (3Commas, 2022). Pooled vaults are the highest-risk legal structure.

### Cited Findings
- **Geo-blocking:**
  - Lighter ToS exclude US, CA, UK, CN and sanctioned states. They warn that "third parties may provide other means of accessing the Protocol to which these Terms do not apply". Lighter may suspend for "Impersonation of the frontend interface", "Unauthorized access to the API" and "Price manipulation or market interference". — [Lighter ToS, 29 Dec 2025](https://lighter.xyz/terms)
  - Hyperliquid and dYdX block US IPs at the front-end. — [OneKey (secondary)](https://onekey.so/blog/ecosystem/geo-block-hyperliquid-dydx-us/)
  - The CFTC found IP-blocking insufficient (Opyn 2023). — [CFTC 8774-23](https://www.cftc.gov/PressRoom/PressReleases/8774-23)
- **"Tool" positioning:** eToro US says CopyTrader is "an educational and operational tool", not advice, with "no discretion". It does "not recommend Popular Investors or other users". Users may not be copied if their "risk score… hits a certain threshold or if they have a certain amount of copiers or assets already". Popular Investors may not themselves copy others. — [eToro disclosure, Oct 2025](https://www.etoro.com/wp-content/uploads/2025/10/Lets-Talk-About-CopyTrader-disclosure-October-2025.pdf)
- **Regulators look through labels:** ESMA says "auto-copy" buttons are a mandate, and bulk approvals or stop-losses are not per-trade intervention. — [ESMA 2023 briefing](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf). The FCA disregards client-set parameters. — [FCA](https://www.fca.org.uk/firms/copy-trading). ESMA on perps: "the commercial name… is irrelevant". — [ESMA Feb 2026](https://www.dirittobancario.it/wp-content/uploads/2026/02/Dichiarazione-ESMA-24-febbraio-2026-ESMA35-243228190-8024.pdf)
- **Systemic or operational risk disclosed by eToro:** where "a large number of individuals copy the trading undertaken by a single 'Popular Investor'", this "creates a risk that there may be a large number of trades which fail to settle". — [eToro SEC filing, 2025](https://www.sec.gov/Archives/edgar/data/1493318/000101376225001589/ea0223534-08.htm)
- **Custodial API-key failure (3Commas, 2022):**
  - Users reported unauthorised trades from leaked exchange API keys. ZachXBT tallied 44 users losing $14.8M.
  - 3Commas first called the claims "fake". On 28 Dec 2022 its CEO confirmed the leaked data "is true", after a hacker published about 10,000 keys (about 100,000 reportedly taken). 3Commas asked exchanges to revoke all connected keys. Complaints dated from Oct 2022. — [CryptoSlate, Dec 2022](https://cryptoslate.com/3commas-denies-accusations-of-leaking-api-data-resulting-in-14-8m-in-unauthorized-trades/); [Decrypt, Dec 2022](https://decrypt.co/118094/after-repeated-denials-3commas-admits-it-was-source-for-earlier-hacks); [ForkLog/HAPI analysis](https://forklog.com/en/api-key-leaks-and-exchange-inaction-a-hapi-analysis-of-the-3commas-incident/)
- **Vault structure (Hyperliquid):**
  - Depositors share losses pro rata. The leader takes 10% of profits and must keep at least 5% of the vault.
  - The protocol vault HLP passes 100% of PnL to depositors. HLP cumulative profit was about $137M at 30 Jun 2026, against a peak TVL of $603.9M (Sep 2025). — [OneKey (secondary)](https://onekey.so/blog/ecosystem/hyperliquid-vault-deposit-guide/); [Datawallet (secondary), 2026](https://www.datawallet.com/crypto/hyperliquid-hlp-explained)
  - Several leader vaults show negative APRs on the official page. — [Hyperliquid vaults page (snapshot)](https://app.hyperliquid.xyz/vaults)
- **Leaderboard-maths fixes:** Bitget (12 Jun 2026) changed its ROI formula after "a small number of elite traders" inflated ROI. They opened small positions, transferred in large sums, traded, and withdrew quickly, exploiting a formula that used only "initial assets" as the denominator. The new hourly ROI is net PnL ÷ maximum available capital. — [Bitget announcement, 12 Jun 2026](https://www.bitget.com/news/detail/12560605456280)
- **Leader incentive structures:**
  - TraderWagon (Binance-linked; Oct 2022–Aug 2023 data) paid leaders 10% of copier profits plus a share of copier fees. Leaders could run up to six portfolios and close losers at will. — [Kawai et al., CHI 2024](https://www.andrew.cmu.edu/user/nicolasc/publications/Kawai-CHI24.pdf)
  - eToro's Popular Investor programme historically paid up to 2% of copied equity plus spread rebates (c. 2018). — [Apesteguia, Oechssler & Weidenholzer, working paper Sep 2019](https://repository.essex.ac.uk/25396/1/copy%20trading%20experiment_32ms%20final.pdf)

### Inferences
- **Custody and keys:** a non-custodial "agent key" model (a user-revocable, trade-only key with no withdrawal rights, held by Mirrorlane's engine) reduces custody-regime exposure and theft blast-radius compared with 3Commas-style custodial exchange API keys. It does **not** change the portfolio-management, CTA "directing" or advice characterisation if Mirrorlane's engine places trades from a third party's signals without per-trade user action. If Mirrorlane holds any user's signing key server-side, it also becomes a high-value hacking target. The 3Commas incident is the reference case for liability and reputational exposure.
- **Lighter-specific operational risk:** Lighter's ToS reserve the right to suspend accounts for "unauthorized access to the API" and "impersonation of the frontend". Mirrorlane should confirm its API usage is permitted (an integrator or partner agreement if available) and use distinct branding.
- **Vault-style pooling has the most legal risk.** It means pooled funds, manager discretion and a profit share: an AIF/CIS in EU/UK terms, a commodity pool in the US, and possibly an investment contract. It is also the most exposed to manipulation transferring losses to depositors (see section 6).
- **Lower-risk design ingredients** that the evidence supports:
  1. Trading features restricted for excluded jurisdictions (at minimum Lighter's list).
  2. No leader compensation from Mirrorlane, or full inducement-style disclosure if any.
  3. No "top trader" curation or ROI-ranked default lists. Neutral, multi-metric, risk-adjusted displays, with drawdown and full-history including closed or abandoned strategies.
  4. Per-trade user signing (signals, not auto-execution) for any regulated-market users.
  5. Leader eligibility rules (minimum history, own-capital at risk, no self-dealing).
  6. Follower caps per leader and size limits relative to market liquidity.
  7. Prominent loss-rate disclosures.

### Gaps
- Lighter's specific key and permission model (whether sub-keys can be trade-only, withdrawal-restricted, or time-limited) and whether Lighter has native pools or vaults were not verified here. This is likely covered by another researcher.
- No source gave the actual KYC practices for lead traders at Binance, Bybit, OKX or Hyperliquid.
- No court outcome for any 3Commas class action was found.

---

## 6. Evidence on outcomes and abuses: follower performance, survivorship bias, exit liquidity, inflated stats, scandals and enforcement

### Takeaway
The evidence is consistent: copy trading **raises risk-taking**, followers concentrate on a few top-ranked leaders, rankings are **gameable and weakly predictive**, and leaders' own PnL overstates what followers earn. On perps venues, large "whale" positions can be used to make copiers and pooled vaults absorb losses. Rigorous independent outcome data for crypto copy-trading followers is scarce. The largest-scale numbers come from a vendor with a commercial interest.

### Cited Findings
**Academic and experimental**
- **Apesteguia, Oechssler & Weidenholzer, "Copy trading" (working paper dated 17 Sep 2019; reportedly published later in *Management Science*, venue not verified here).** In the lab, "providing information on the success of others leads to a significant increase in risk taking… This increase in risk taking is even larger when subjects are provided with the option to directly copy others. We conclude that copy trading leads to excessive risk taking."
  - In the COPY treatment, 35% copied someone. 88% of copiers picked a top-5 earner (71% the top earner), and 88% picked a trader who chose the riskiest asset.
  - **Platform data (May 2018):** only 1.13–8.71% of ranked traders are copied at all. "The top 5% of leaders accounts for 61.1% (ZuluTrade) to 92.8% (eToro) of copier relationships."
  - **Literature cited in the paper:** copied trades on eToro have a higher probability of positive returns, but smaller wins and larger losses (Liu et al. 2014). Copied investors show more disposition effect (Pelster & Hofmann 2018). About 85% of eToro transactions were forex (2018). — [Apesteguia et al. (Essex repository)](https://repository.essex.ac.uk/25396/1/copy%20trading%20experiment_32ms%20final.pdf)
- **Kawai, Soska, Routledge, Zetlin-Jones & Christin, "Stranger Danger? Investor Behavior and Incentives on Cryptocurrency Copy-Trading Platforms" (ACM CHI 2024).** The study used data on TraderWagon (Binance Futures-linked) and Bybit perps copy trading, Oct 2022–Aug 2023. Typical copier stakes were USD 500–2,000+. Findings:
  - "the platform UI significantly influences copiers' decisions".
  - Rankings "are often easily gameable by unscrupulous leaders who prey on novice copiers".
  - On Bybit, rankings reflect popularity more than performance and are "poorly correlated with future returns". On TraderWagon they "over-emphasize recent past performance".
  - "leaders do not have to bear large financial risks to climb up the rankings".
  - Platforms are incentivised to maximise copy volume.
  - A documented leader tried multiple portfolios at once and kept only winners. A leader can show a +12% open portfolio while having just closed one at −92%. — [Kawai et al. (author PDF)](https://www.andrew.cmu.edu/user/nicolasc/publications/Kawai-CHI24.pdf); [ACM DL](https://dl.acm.org/doi/10.1145/3613904.3642715)

**Crypto CEX outcome data (vendor, use with caution)**
- **YieldFund "Is Copy Trading Profitable? A 90-Day, Multi-Exchange Study" (24 Nov 2025).** The study scraped public leaderboard data (Dubai market view) from Binance, Bybit and MEXC: 1,486 leaders and 100,236 copier outcomes.
  - "only 48.48%" of copier outcomes were profitable.
  - "97.04% of leaders were green on their own PnL, only 43.61% of leaders produced positive follower PnL".
  - Aggregate follower PnL was +709,045 USDT.
  - Copier win rates by platform: Binance 66.5%, MEXC 57.79%, Bybit 43.65%.
  - **Limits:** event-weighted; fees, funding and slippage not decomposed; leaderboard-visible leaders only. Leaderboard samples are survivorship-biased, which is an inference. The author sells a managed crypto product, which is a conflict of interest. — [YieldFund, Nov 2025](https://yieldfund.com/is-copy-trading-profitable-a-90-day-multi-exchange-study)
- **Inflated leader statistics confirmed by an exchange:** Bitget's June 2026 ROI-formula fix, for deposit-timing manipulation by "elite traders". — [Bitget, 12 Jun 2026](https://www.bitget.com/news/detail/12560605456280)

**Perp-DEX "whale" abuse and loss transfer to pooled vaults (Hyperliquid)**
- **March 2025 ETH whale:** a trader opened a large leveraged ETH long, withdrew collateral, and let the remainder be liquidated. Hyperliquid's HLP vault lost about $4M. Commentators argue the whale "was betting that others would follow" (copy traders assuming insider knowledge), creating exit conditions. Hyperliquid denied an exploit, then cut leverage limits and required a 20% margin ratio to withdraw collateral from open positions. — [WisdomTree Prime, 2025](https://www.wisdomtree.com/onchain/insights/blog/the-great-whale-slap-how-a-whale-offloaded-4m-in-losses-to-hyperliquids-hlp-vault). The copy-trader-bait motive is commentary, not proven.
- **JELLY (March 2025):** coordinated positions forced HLP into a short squeeze, with exposure around $12M. Hyperliquid delisted JELLY perps and settled positions at an adjusted price, raising decentralisation concerns. — [NFTEvening, 2025](https://nftevening.com/recap-price-manipulation-hyperliquid/)
- **Later events:** HLP also absorbed losses from a POPCAT manipulation (2025). Some traders deliberately engineer self-liquidations in thin markets to push losses onto HLP. — [EarnPark review, Oct 2026 (secondary)](https://earnpark.com/en/posts/hyperliquid-vaults-hlp-review/); [Datawallet, 2026](https://www.datawallet.com/crypto/hyperliquid-hlp-explained)
- **Vault rankings mislead:** a vault showing a 547% 90-day return "is as likely to be a martingale that hasn't blown up yet". Drawdown matters more than APR. — [VaultVision, 2026 (vendor commentary)](https://vaultvision.tech/blog/hyperliquid-yield-guide)

**Scandals, enforcement and lawsuits**
- **Mirror Trading International (2019–2021 scheme):** the largest CFTC BTC fraud case. About $1.73B (29,421 BTC) was taken under an automated "mirror trading" forex pitch. Judgments were entered in 2023 (see section 3). — [CFTC 8696-23](https://www.cftc.gov/PressRoom/PressReleases/8696-23)
- **3Commas API-key leak (2022):** see section 5.
- **ASIC v eToro (filed Aug 2023):** CFD design-and-distribution case (see section 4).
- **FCA finfluencer convictions (Feb 2026) and the June 2025 multi-regulator sweep:** see section 2.
- **ESMA:** the 2023 briefing and IOSCO's 2025 report both identify leader remuneration (per follower or AUM) and misleading performance presentation as core harms. — [ESMA 2023](https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf); [IOSCO FR/06/2025](https://www.iosco.org/library/pubdocs/pdf/IOSCOPD793.pdf)

### Inferences
- **Product risks Mirrorlane would inherit:**
  1. **Ranking-driven herding** into a few high-variance leaders, which raises liquidation cascades and slippage for late followers, especially in thin Lighter markets.
  2. **Front-running or exit-liquidity risk**, where a leader trades ahead of, or exits into, follower order flow. This is mechanically easier when followers execute after the leader on the same order book.
  3. **Gaming of displayed stats** through multiple accounts or strategies, closing losers, deposit timing, and margin-based ROI.
  4. **Profit-share incentives** that reward variance (option-like payoff for the leader, with no loss-sharing).
- **Defensible mitigations follow from the evidence:**
  - Rank by risk-adjusted, capital-weighted, full-history metrics, including closed strategies.
  - Show follower-realised (not leader) PnL and the percentage of followers profitable.
  - Cap followers and copy size relative to market depth.
  - Delay or randomise follower execution, or forbid leaders from trading against follower flow.
  - Require leaders to keep meaningful own-capital at risk.
  - Avoid pooled vaults.
- **Marketing claims:** given that the best available crypto data (vendor) shows fewer than half of copier outcomes profitable, and leaders' own PnL far exceeds follower PnL, any "copy the winners" claim would be hard to defend under ESMA's or IOSCO's marketing standards.

### Gaps
- No independent, peer-reviewed study of **Hyperliquid vault depositor** returns or of **Lighter** follower outcomes was found.
- No academic estimate of the share of crypto copy-trading followers who lose money was found. Exchange-published loss-rate disclosures for copy trading (analogous to CFD "x% of retail accounts lose money") were not found.
- No documented enforcement case specifically for a crypto copy-trading leader front-running followers was found. Searches for Binance or Bybit lead-trader suspensions for manipulation returned nothing verifiable.
- eToro copier-level outcome statistics (current) were not found. The academic eToro evidence mostly predates 2020.
