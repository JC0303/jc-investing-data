# Short-term v2 backtest result (rule frozen 2026-11-12, claude/08)
Run (UTC): 2026-11-21 16:13
Admitted: 4118; complete windows: 4011; WINDOW_INCOMPLETE: 107; settled: 4011; period price missing: 0; exit price missing: 0
Revenue input: repository snapshot data/tw_monthly_revenue.csv; revenue pages were not fetched during this replay.
Signals: 5174; trades: 4011; signals without price data (likely delisted/unavailable, survivorship bias): 0
Mean net return per trade: 1.2895%; mean 0050 same window: 0.9536%
Mean excess: 0.3359%; t-stat: 1.92; median excess: -1.3027%; win rate vs 0050: 43.8%
Stopped out: 17.1%; worst trade net: -24.32%
Mean excess without top 5%: -1.4171%
Top-3/month subset: admitted 171, settled 171, mean excess 1.2727%; worst rolling 3-month PnL TWD -11,845

By entry year:
            count      mean
entry_year                 
2022          569  0.003524
2023          522  0.017230
2024          918 -0.000561
2025          747  0.008952
2026         1255 -0.002948

Checks:
- 1 trades >= 200: PASS
- 2 mean excess > 0 and t >= 2: FAIL
- 3 >= 3 of 2022-2025 years positive: PASS
- 4 mean excess > 0 without top 5%: FAIL
- 5 worst rolling 3-month PnL (top-3/month, TWD 16k) >= -18,000: PASS

OVERALL: FAIL
