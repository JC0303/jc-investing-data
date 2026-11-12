# Short-term v2 backtest result (rule frozen 2026-11-12, claude/08)
Run (UTC): 2026-11-12 12:10
Revenue pages failed: 5 — https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_113_12_0.html ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')); https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_114_1_0.html ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')); https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_114_9_0.html ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')); https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_114_9_0.html ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')); https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_115_10_0.html ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
Signals: 2893; trades: 2184; signals without price data (likely delisted/unavailable, survivorship bias): 0
Mean net return per trade: 1.1361%; mean 0050 same window: 0.5652%
Mean excess: 0.5709%; t-stat: 2.66; median excess: -0.9640%; win rate vs 0050: 45.0%
Stopped out: 15.0%; worst trade net: -23.88%
Mean excess without top 5%: -1.0068%
Top-3/month subset: trades 111, mean excess 1.2663%; worst rolling 3-month PnL TWD -5,006

By entry year:
            count      mean
entry_year                 
2022          569  0.003524
2023          522  0.017230
2024          918 -0.000561
2025           64  0.005891
2026          111  0.014468

Checks:
- 1 trades >= 200: PASS
- 2 mean excess > 0 and t >= 2: PASS
- 3 >= 3 of 2022-2025 years positive: PASS
- 4 mean excess > 0 without top 5%: FAIL
- 5 worst rolling 3-month PnL (top-3/month, TWD 16k) >= -18,000: PASS

OVERALL: FAIL
