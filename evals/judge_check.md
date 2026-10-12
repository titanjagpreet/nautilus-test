# Manual check of the LLM judge (DeepSeek run, 2026-10-12)

The eval's intent score comes from an LLM judge (`deepseek-v4-pro` in this run, the strongest model with a
key). The brief asks for a sample of its verdicts to be checked by a person; this is that check, done by
reading each request, the deterministic rendering of the produced spec (what the judge saw) and the judge's
reason. Sample: all five cases the judge scored below 2, plus six cases it scored 2.

| case | judge | my score | agree | notes |
|---|---|---|---|---|
| p02 Pine RSI reversal | 0 | 1 | no | Entries and exits match the script exactly. The stop/target conversion from "300/600 ticks" to 1.5%/3% is wrong (300 BTC ticks are far less than 1.5%), so one stated element is wrong — that is a 1 by the rubric, not 0. |
| p05 Pine Supertrend | 0 | 0 | yes | Supertrend is not in the indicator catalogue; the model substituted a close-crosses-EMA(10) signal (listed as unsupported). The core logic is different. |
| g11 VWAP stretch | 1 | 1 | yes | The rule enters on *any* close above VWAP; the "more than 1% above" condition is dropped (the format has no arithmetic between operands). **The model's notes claim the 1% threshold is implemented — they misdescribe the spec.** |
| g29 vague "buys the dip" | 1 | 2 | no | Eval bug, now fixed: the judge saw only the vague prompt, not the user's answers to the model's clarifying questions; the spec matches those answers exactly. |
| p04 Pine pyramiding | 1 | 1 | yes | Pyramiding and the half-position exit cannot be expressed (listed as unsupported); a full 5% target replaces the half exit. |
| g09 gold London breakout | 2 | 2 | yes | All stated elements present (15m, 07–10 UTC window, 16-bar high, 1/day, 32-bar time exit, 0.5% stop). |
| g17 short scalper | 2 | 2 | yes | Every stated element present. |
| g21 midnight entry with daily SMA | 2 | 2 | yes | Enters on the 23:00 bar's close so the fill is at 00:00 — correct under next-bar-open fills; daily SMA on completed bars. |
| e04 trend filter → daily 100 EMA | 2 | 2 | yes | Only the filter changed. |
| p03 Pine BB + 4h EMA (lookahead) | 2 | 2 | yes | Lookahead and process-on-close were not copied; completed 4h bars used. |
| g24 structure stop, 3R | 2 | 2 | yes | Every stated element present. |

**Agreement: 9 of 11.** One disagreement is the judge being too harsh (p02), the other an eval bug (g29: the
judge must see the clarifications — fixed in `evaluation.judge_request`). One case (e02) got no verdict; the
judge's raw reply was not recorded in this run (it is now, in `evals/recorded/judge.json`), so the cause
cannot be confirmed — the label parsing was made tolerant of answers like "Candidate A".

What the sample shows about the judge: it reads specs carefully (it caught the missing VWAP threshold that the
objective checks — 5/5 for g11 — did not), but it scores "missing core feature" and "wrong parameter" alike
sometimes; treat its numbers as ±1 on individual cases and look at the reasons.
