# REPORT

<!-- BENCH:BEGIN -->
| scenario | engine | cores | wall time | peak RSS | per backtest |
|---|---|---|---|---|---|
| single | fast (cold (incl. JIT compile)) | 1 | 0.3 s | 482 MB | 0.290 s |
| single | fast (warm) | 1 | 0.1 s | 483 MB | 0.100 s |
| sweep 144 | fast | 1 core | 4.9 s | 491 MB | 0.034 s |
| sweep 144 | fast | 4 cores | 3.9 s | 2,224 MB | 0.027 s |
| sweep 1600 | fast | 1 core | 48.5 s | 425 MB | 0.030 s |
| sweep 1600 | fast | 4 cores | 15.2 s | 2,278 MB | 0.009 s |

Machine: 4 vCPU, 15.7 GB RAM; workload: EMA crossover, BTC-PERP 1h on 1m execution, 2024-01-01 → 2025-01-01.
<!-- BENCH:END -->

<!-- PARITY:BEGIN -->
| strategy | fees | trades (N / fast) | identical entries, exits, reasons | net P&L Nautilus | net P&L fast | rel. diff P&L / fees / funding | time Nautilus / fast |
|---|---|---|---|---|---|---|---|
| EMA crossover | standard | 198 / 198 | yes | -440.43 | -440.43 | 0e+00 / 0e+00 / 0e+00 | 11.3 s / 0.25 s |
| EMA crossover | premium | 198 / 198 | yes | -619.62 | -619.62 | 2e-11 / 6e-11 / 0e+00 | 11.6 s / 0.08 s |
| RSI mean reversion with trend filter | standard | 34 / 34 | yes | 11.93 | 11.93 | 0e+00 / 0e+00 / 0e+00 | 6.3 s / 0.11 s |
| RSI mean reversion with trend filter | premium | 34 / 34 | yes | -26.09 | -26.09 | 0e+00 / 0e+00 / 0e+00 | 6.1 s / 0.12 s |
| Donchian breakout | standard | 58 / 58 | yes | 1,518.98 | 1,518.98 | 0e+00 / 0e+00 / 0e+00 | 16.7 s / 0.08 s |
| Donchian breakout | premium | 58 / 58 | yes | 1,444.19 | 1,444.19 | 7e-12 / 1e-10 / 0e+00 | 16.5 s / 0.08 s |
| Bollinger squeeze breakout | standard | 211 / 211 | yes | 132.05 | 132.05 | 0e+00 / 0e+00 / 0e+00 | 8.3 s / 0.12 s |
| Bollinger squeeze breakout | premium | 211 / 211 | yes | -75.73 | -75.73 | 1e-10 / 5e-11 / 0e+00 | 7.4 s / 0.09 s |
| MACD with higher-timeframe EMA filter | standard | 1430 / 1430 | yes | 4.67 | 4.67 | 0e+00 / 0e+00 / 0e+00 | 21.6 s / 0.28 s |
| MACD with higher-timeframe EMA filter | premium | 1430 / 1430 | yes | -1,374.95 | -1,374.95 | 2e-11 / 2e-11 / 0e+00 | 20.8 s / 0.26 s |
| Keltner pullback | standard | 377 / 377 | yes | 1,512.74 | 1,512.74 | 0e+00 / 0e+00 / 0e+00 | 15.1 s / 0.08 s |
| Keltner pullback | premium | 377 / 377 | yes | 1,080.03 | 1,080.03 | 2e-11 / 5e-11 / 0e+00 | 15.3 s / 0.08 s |
| Stochastic oversold with ADX filter | standard | 73 / 73 | yes | -125.70 | -125.70 | 0e+00 / 0e+00 / 0e+00 | 7.5 s / 0.17 s |
| Stochastic oversold with ADX filter | premium | 73 / 73 | yes | -203.70 | -203.70 | 0e+00 / 0e+00 / 0e+00 | 7.0 s / 0.10 s |
| Funding-rate fade | standard | 18 / 18 | yes | 232.13 | 232.13 | 0e+00 / 0e+00 / 0e+00 | 2.7 s / 0.40 s |
| Funding-rate fade | premium | 18 / 18 | yes | 215.25 | 215.25 | 0e+00 / 0e+00 / 0e+00 | 2.5 s / 0.07 s |
| VWAP reversion | standard | 1075 / 1075 | yes | -510.29 | -510.29 | 0e+00 / 0e+00 / 0e+00 | 16.2 s / 0.20 s |
| VWAP reversion | premium | 1075 / 1075 | yes | -1,586.62 | -1,586.62 | 3e-11 / 5e-11 / 0e+00 | 17.5 s / 0.12 s |
| Gold session breakout (XAU) | standard | 213 / 213 | yes | 39.00 | 39.00 | 0e+00 / 0e+00 / 0e+00 | 6.5 s / 0.08 s |
| Gold session breakout (XAU) | premium | 213 / 213 | yes | -161.74 | -161.74 | 0e+00 / 0e+00 / 0e+00 | 6.1 s / 0.09 s |
<!-- PARITY:END -->
