# Short-term simulation A-track: historical check (spec v1 frozen 2026-11-13; check approved 2026-11-21)
Run (UTC): 2026-11-21 16:13
Tickers with prices: 1855; candidate signals (no cap): 33396
Approximation: ADVANCE proxy = route A revenue part only (no historical P/E; routes B/C not reproduced).

MAIN (rule as live) (Admitted: 5065; complete windows: 5040; WINDOW_INCOMPLETE: 25; settled: 4975; period price missing: 64; exit price missing: 1): trades 4975; signal days 1052; mean net 0.510%; mean 0050 net 0.771%; mean excess -0.260%; median excess -4.558%; clustered t -1.30; without top 5% -1.491%; stop 46% / target 28% / time 26%; mean days 11.1; mean entry gap vs signal close 0.82%

By signal year (count, mean excess):
      count      mean
yr                   
2022   1002 -0.000597
2023   1053  0.011763
2024   1065 -0.003414
2025    984 -0.012186
2026    871 -0.010468

Pass checks:
- 1 settled trades >= 100: PASS
- 2 mean net excess > 0: FAIL
- 3 mean net excess > 0 without top 5%: FAIL
- 4 signal-date clustered t >= 2: FAIL
- 5 mean net excess > 0 without best calendar month: FAIL

OVERALL: INCOMPLETE

Diagnostics (not adoptable as rules):
D1 executable exit (next-day close) (Admitted: 5038; complete windows: 5008; WINDOW_INCOMPLETE: 30; settled: 4940; period price missing: 63; exit price missing: 5): trades 4940; signal days 1048; mean net 0.828%; mean 0050 net 0.957%; mean excess -0.129%; median excess -3.924%; clustered t -0.71; without top 5% -1.696%; stop 45% / target 28% / time 27%; mean days 11.9; mean entry gap vs signal close 0.82%
D2a signal-day return >= 9.5% (limit-up chase) (Admitted: 2486; complete windows: 2469; WINDOW_INCOMPLETE: 17; settled: 2454; period price missing: 15; exit price missing: 0): trades 2454; signal days 860; mean net 0.690%; mean 0050 net 0.583%; mean excess 0.107%; median excess -5.191%; clustered t 0.30; without top 5% -1.130%; stop 50% / target 32% / time 18%; mean days 9.4; mean entry gap vs signal close 1.55%
D2b signal-day return < 9.5% (Admitted: 2579; complete windows: 2571; WINDOW_INCOMPLETE: 8; settled: 2521; period price missing: 49; exit price missing: 1): trades 2521; signal days 824; mean net 0.336%; mean 0050 net 0.954%; mean excess -0.618%; median excess -4.242%; clustered t -2.30; without top 5% -1.842%; stop 42% / target 24% / time 34%; mean days 12.7; mean entry gap vs signal close 0.12%
D3 no daily cap (Admitted: 11141; complete windows: 11058; WINDOW_INCOMPLETE: 83; settled: 10953; period price missing: 104; exit price missing: 1): trades 10953; signal days 1046; mean net 0.465%; mean 0050 net 0.577%; mean excess -0.111%; median excess -3.269%; clustered t -2.23; without top 5% -1.298%; stop 42% / target 26% / time 32%; mean days 12.2; mean entry gap vs signal close 0.31%

Known bias: Yahoo lacks most delisted stocks -> optimistic.
