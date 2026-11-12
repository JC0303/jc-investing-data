# Short-term v4 (attempt #3) result (rule frozen 2026-11-12, claude/12)
Run (UTC): 2026-11-12 13:43
Base signals: 5885; simulated trade-variants: 14848

In-sample grid (2022-2024), sorted by clustered t:
  Y   A    MA    T  H    n     mean        t   trimmed
0.3 0.2  True 0.10 60  914 0.016929 2.181176 -0.013525
0.2 0.2  True 0.10 60 1032 0.014468 2.040479 -0.015555
0.3 0.2  True 0.10 40  916 0.013318 2.000077 -0.016244
0.2 0.2  True 0.10 40 1034 0.010670 1.825050 -0.018161
0.3 0.1  True 0.10 60 1114 0.013482 1.787587 -0.016210
0.3 0.2  True 0.15 60  907 0.013388 1.767881 -0.022959
0.2 0.2  True 0.15 60 1025 0.012515 1.767110 -0.023811
0.2 0.1  True 0.10 60 1336 0.011672 1.720694 -0.016987
0.3 0.1  True 0.10 40 1117 0.010817 1.623036 -0.017652
0.3 0.2  True 0.15 40  914 0.008985 1.614272 -0.023107
0.2 0.2  True 0.15 40 1032 0.008547 1.595421 -0.023490
0.3 0.2 False 0.10 60 1215 0.009475 1.548597 -0.019669
0.2 0.2 False 0.10 60 1380 0.007861 1.511794 -0.020831
0.3 0.1  True 0.15 60 1106 0.011441 1.509697 -0.024783
0.2 0.1  True 0.10 40 1339 0.008677 1.481077 -0.018651
0.2 0.1  True 0.15 60 1328 0.009259 1.466308 -0.025762
0.3 0.2 False 0.10 40 1218 0.005726 1.329320 -0.022540
0.3 0.1  True 0.15 40 1115 0.006834 1.322857 -0.024560
0.2 0.1 False 0.10 60 1813 0.006818 1.295231 -0.021337
0.2 0.2 False 0.15 60 1368 0.006258 1.264447 -0.028415
0.2 0.1  True 0.15 40 1337 0.005656 1.258649 -0.024791
0.3 0.1 False 0.10 60 1498 0.007524 1.252629 -0.021428
0.3 0.2 False 0.15 60 1203 0.006571 1.181954 -0.028381
0.2 0.2 False 0.10 40 1383 0.003169 1.150701 -0.024325
0.2 0.1 False 0.15 60 1799 0.004530 1.073734 -0.029366
0.3 0.1 False 0.10 40 1502 0.004827 1.057253 -0.022753
0.3 0.1 False 0.15 60 1485 0.005686 1.035171 -0.029755
0.3 0.2 False 0.15 40 1212 0.002332 1.002119 -0.028737
0.2 0.1 False 0.10 40 1818 0.003309 0.980838 -0.022946
0.2 0.2 False 0.15 40 1377 0.001113 0.950862 -0.029507
0.3 0.1 False 0.15 40 1496 0.002003 0.827653 -0.028858
0.2 0.1 False 0.15 40 1811 0.000913 0.803768 -0.029021

Selected combo (in-sample): {'Y': 0.3, 'A': 0.2, 'MA': True, 'T': 0.1, 'H': 60}; IS trades 914, IS mean excess 1.6929%, IS t 2.18

Out-of-sample (2025-01 onward), selected combo only:
Trades 747; mean net 2.0306%; mean 0050 1.5944%; mean excess 0.4362%; clustered t 0.46
Median excess -4.1254%; win rate 36.3%; without top 5% -2.9200%
Average holding days 27.2; worst trade -23.28%
Top-3/month: trades 57, mean excess -0.4043%; worst rolling 3-month PnL TWD -7,842

By entry year:
      count      mean
yr                   
2025    153  0.019997
2026    594  0.000335

Checks:
- 1 OOS trades >= 60: PASS
- 2 OOS mean excess > 0 and clustered t >= 2.5: FAIL
- 3 OOS mean excess > 0 without top 5%: FAIL
- 4 OOS 2025 and 2026 mean excess both > 0: PASS
- 5 OOS top-3/month worst rolling 3-month PnL (TWD 16k) >= -18,000: PASS
- 6 selected combo in-sample mean excess > 0: PASS

OVERALL: FAIL
Caveats: 2025-26 data was partly seen in v2/v3 results (not a fully clean test); Yahoo lacks most delisted stocks.
