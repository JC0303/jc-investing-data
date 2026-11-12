# Short-term v3 (attempt #2) backtest result (rule frozen 2026-11-12, claude/11)
Run (UTC): 2026-11-12 13:31
Universe tickers: 1864; with price data: 1864; signal weeks: 248; trades: 2942
Mean net return per trade: 0.5054%; mean 0050 same window: 0.8562%
Mean excess: -0.3508%; week-clustered t: -2.82 (229 weeks); median excess: -1.3876%; win rate vs 0050: 41.7%
Stopped out: 9.6%; worst trade net: -25.59%
Mean excess without top 5%: -1.5954%
Top-1/week: trades 229, mean excess -1.9337%, median -2.0480%; worst rolling 13-week PnL TWD -13,197
Holdout 2025-01..2026-10: trades 1649, mean excess 0.0267%

By entry year:
            count      mean
entry_year                 
2022          368 -0.014848
2023          289 -0.013789
2024          636 -0.002062
2025          520 -0.017630
2026         1129  0.008510

Checks:
- 1 trades >= 200: PASS
- 2 mean excess > 0 and week-clustered t >= 2: FAIL
- 3 >= 3 of 2022-2025 years positive: FAIL
- 4 mean excess > 0 without top 5%: FAIL
- 5 top-1/week worst rolling 13-week PnL (TWD 16k) >= -18,000: PASS
- 6 holdout 2025-01..2026-10 mean excess > 0: PASS

OVERALL: FAIL
Known bias: Yahoo lacks most delisted stocks (survivorship), which likely flatters a buy-the-drop rule.
