# Short-term simulation A-track: historical check (spec v1 frozen 2026-11-13; check approved 2026-11-21)
Run (UTC): 2026-11-21 09:48
Tickers with prices: 1855; candidate signals (no cap): 33527
Approximation: ADVANCE proxy = route A revenue part only (no historical P/E; routes B/C not reproduced).

MAIN (rule as live): trades 5015; signal days 1059; mean net 0.494%; mean 0050 net 0.746%; mean excess -0.252%; median excess -4.568%; clustered t -1.40; without top 5% -1.483%; stop 46% / target 28% / time 26%; mean days 11.0; mean entry gap vs signal close 0.81%

By signal year (count, mean excess):
      count      mean
yr                   
2022   1002 -0.000527
2023   1055  0.011580
2024   1065 -0.003382
2025    997 -0.011161
2026    896 -0.010722

Pass checks:
- 1 settled trades >= 100: PASS
- 2 mean net excess > 0: FAIL
- 3 mean net excess > 0 without top 5%: FAIL
- 4 signal-date clustered t >= 2: FAIL
- 5 mean net excess > 0 without best calendar month: FAIL

OVERALL: FAIL

Diagnostics (not adoptable as rules):
D1 executable exit (next-day close): trades 4987; signal days 1056; mean net 0.804%; mean 0050 net 0.924%; mean excess -0.120%; median excess -3.930%; clustered t -0.77; without top 5% -1.693%; stop 46% / target 28% / time 26%; mean days 11.9; mean entry gap vs signal close 0.81%
D2a signal-day return >= 9.5% (limit-up chase): trades 2479; signal days 868; mean net 0.682%; mean 0050 net 0.553%; mean excess 0.129%; median excess -5.185%; clustered t 0.38; without top 5% -1.107%; stop 50% / target 32% / time 18%; mean days 9.4; mean entry gap vs signal close 1.53%
D2b signal-day return < 9.5%: trades 2536; signal days 833; mean net 0.310%; mean 0050 net 0.935%; mean excess -0.625%; median excess -4.308%; clustered t -2.34; without top 5% -1.843%; stop 42% / target 24% / time 34%; mean days 12.6; mean entry gap vs signal close 0.10%
D3 no daily cap: trades 11118; signal days 1052; mean net 0.435%; mean 0050 net 0.524%; mean excess -0.089%; median excess -3.219%; clustered t -2.23; without top 5% -1.277%; stop 42% / target 25% / time 32%; mean days 12.2; mean entry gap vs signal close 0.29%

Known bias: Yahoo lacks most delisted stocks -> optimistic.
