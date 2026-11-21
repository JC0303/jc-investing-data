# Short-term v2 backtest result (rule frozen 2026-11-12, claude/08)
Run (UTC): 2026-11-21 16:05
Admitted: 4118; settled: 4087; period price missing: 16; exit price missing: 15
Revenue input: repository snapshot data/tw_monthly_revenue.csv; revenue pages were not fetched during this replay.
Signals: 5174; trades: 4087; signals without price data (likely delisted/unavailable, survivorship bias): 0
Mean net return per trade: 0.9993%; mean 0050 same window: 0.7504%
Mean excess: 0.2490%; t-stat: 1.44; median excess: -1.3686%; win rate vs 0050: 43.4%
Stopped out: 18.6%; worst trade net: -24.76%
Mean excess without top 5%: -1.4953%
Top-3/month subset: admitted 174, settled 171, mean excess 1.2727%; worst rolling 3-month PnL TWD nan

By entry year:
            count      mean
entry_year                 
2022          569  0.003524
2023          522  0.017230
2024          918 -0.000561
2025          747  0.008952
2026         1331 -0.005256

Checks:
- 1 trades >= 200: PASS
- 2 mean excess > 0 and t >= 2: FAIL
- 3 >= 3 of 2022-2025 years positive: PASS
- 4 mean excess > 0 without top 5%: FAIL
- 5 worst rolling 3-month PnL (top-3/month, TWD 16k) >= -18,000: INCOMPLETE

OVERALL: INCOMPLETE
