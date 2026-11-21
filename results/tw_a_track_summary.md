# Short-term simulation A-track: historical check (spec v1 frozen 2026-11-13; check approved 2026-11-21)
Run (UTC): 2026-11-21 16:05
Tickers with prices: 1855; candidate signals (no cap): 33396
Approximation: ADVANCE proxy = route A revenue part only (no historical P/E; routes B/C not reproduced).

MAIN (rule as live) (Admitted: 5065; settled: 5000; period price missing: 64; exit price missing: 1): trades 5000; signal days 1057; mean net 0.472%; mean 0050 net 0.739%; mean excess -0.267%; median excess -4.564%; clustered t -1.33; without top 5% -1.497%; stop 46% / target 28% / time 26%; mean days 11.0; mean entry gap vs signal close 0.81%

By signal year (count, mean excess):
      count      mean
yr                   
2022   1002 -0.000597
2023   1053  0.011763
2024   1065 -0.003414
2025    984 -0.012186
2026    896 -0.010642

Pass checks:
- 1 settled trades >= 100: PASS
- 2 mean net excess > 0: FAIL
- 3 mean net excess > 0 without top 5%: FAIL
- 4 signal-date clustered t >= 2: FAIL
- 5 mean net excess > 0 without best calendar month: FAIL

OVERALL: INCOMPLETE

Diagnostics (not adoptable as rules):
D1 executable exit (next-day close) (Admitted: 5038; settled: 4970; period price missing: 63; exit price missing: 5): trades 4970; signal days 1054; mean net 0.788%; mean 0050 net 0.913%; mean excess -0.125%; median excess -3.907%; clustered t -0.70; without top 5% -1.699%; stop 46% / target 28% / time 26%; mean days 11.9; mean entry gap vs signal close 0.81%
D2a signal-day return >= 9.5% (limit-up chase) (Admitted: 2486; settled: 2471; period price missing: 15; exit price missing: 0): trades 2471; signal days 865; mean net 0.654%; mean 0050 net 0.546%; mean excess 0.108%; median excess -5.193%; clustered t 0.30; without top 5% -1.132%; stop 51% / target 32% / time 18%; mean days 9.3; mean entry gap vs signal close 1.53%
D2b signal-day return < 9.5% (Admitted: 2579; settled: 2529; period price missing: 49; exit price missing: 1): trades 2529; signal days 827; mean net 0.294%; mean 0050 net 0.929%; mean excess -0.634%; median excess -4.254%; clustered t -2.38; without top 5% -1.855%; stop 42% / target 24% / time 34%; mean days 12.7; mean entry gap vs signal close 0.11%
D3 no daily cap (Admitted: 11141; settled: 11034; period price missing: 106; exit price missing: 1): trades 11034; signal days 1051; mean net 0.398%; mean 0050 net 0.522%; mean excess -0.124%; median excess -3.275%; clustered t -2.19; without top 5% -1.314%; stop 42% / target 25% / time 32%; mean days 12.2; mean entry gap vs signal close 0.29%

Known bias: Yahoo lacks most delisted stocks -> optimistic.
