# Short-term v2 backtest result (rule frozen 2026-11-12, claude/08)
Run (UTC): 2026-11-12 12:39
Revenue pages failed: 0
Signals: 5174; trades: 4011; signals without price data (likely delisted/unavailable, survivorship bias): 0
Mean net return per trade: 1.2894%; mean 0050 same window: 0.9541%
Mean excess: 0.3352%; t-stat: 1.92; median excess: -1.3027%; win rate vs 0050: 43.8%
Stopped out: 15.2%; worst trade net: -24.32%
Mean excess without top 5%: -1.4177%
Top-3/month subset: trades 171, mean excess 1.2727%; worst rolling 3-month PnL TWD -11,845

By entry year:
            count      mean
entry_year                 
2022          569  0.003524
2023          522  0.017230
2024          918 -0.000588
2025          747  0.008952
2026         1255 -0.002948

Checks:
- 1 trades >= 200: PASS
- 2 mean excess > 0 and t >= 2: FAIL
- 3 >= 3 of 2022-2025 years positive: PASS
- 4 mean excess > 0 without top 5%: FAIL
- 5 worst rolling 3-month PnL (top-3/month, TWD 16k) >= -18,000: PASS

OVERALL: FAIL
