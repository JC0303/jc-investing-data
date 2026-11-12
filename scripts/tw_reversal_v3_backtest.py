"""Backtest of JC Investing short-term rule v3 = attempt #2 (claude/11, frozen 2026-11-12 before any run).

Hypothesis (different from v2): liquid Taiwan large caps that fall sharply vs 0050 in one week
tend to rebound over the next week (short-term reversal / overreaction).

Rule (do NOT tune after seeing results; any change = attempt #3 under claude/11 rules):
- Universe: every code that appears in data/tw_monthly_revenue.csv (TWSE sii / TPEx otc common stocks,
  codes 1000-9999, revenue months 2020-12..2026-10) and has Yahoo price data.
- Signal day s = last trading day of each calendar week (0050 trading calendar), s from 2022-01-01 to 2026-10-31.
- Conditions on s: 20-day average traded value (close x volume, days s-19..s) >= TWD 200,000,000;
  close[s] >= 20; volume > 0 on each of days s-4..s; 5-day adjusted return r5 = adj[s]/adj[s-5]-1 <= -8%;
  relative return rel = r5 - (0050 adj 5-day return) <= -10 pp.
- Entry E = adjusted close of day s+1. Exit = close of day E+5; if any close on E+1..E+4 <= entry*0.92,
  exit at the next day's close.
- Cost 0.585% round trip. Benchmark 0050 adjusted close, same entry/exit days.
Pass criteria (all must hold):
 1 trades >= 200
 2 mean excess > 0 and week-clustered t >= 2 (t over per-week average excess)
 3 >= 3 of 2022-2025 entry years with mean excess > 0
 4 mean excess > 0 after dropping the top 5% of trades
 5 top-1-per-week subset (most negative rel): worst rolling 13-week PnL at TWD 16,000/trade >= -18,000
 6 holdout: trades entered 2025-01-01..2026-10-31 have mean excess > 0
"""
import datetime as dt
import math
import os
import time

import numpy as np
import pandas as pd

OUT_DIR = "results"
COST = 0.00585
HOLD = 5
STOP = 0.92
MIN_VALUE = 200_000_000
MIN_PX = 20
R5_MAX = -0.08
REL_MAX = -0.10
POS = 16_000
START, END = pd.Timestamp("2022-01-01"), pd.Timestamp("2026-10-31")


def load_prices():
    import yfinance as yf
    rev = pd.read_csv("data/tw_monthly_revenue.csv", dtype={"code": str})
    uni = rev.drop_duplicates("code")[["code", "mkt"]]
    tick = {c: c + (".TW" if m == "sii" else ".TWO") for c, m in uni.values}
    tickers = sorted(set(tick.values())) + ["0050.TW"]
    adj, close, vol = {}, {}, {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i + 100]
        for attempt in range(3):
            try:
                d = yf.download(batch, start="2021-10-01", end=dt.date.today().isoformat(), auto_adjust=False,
                                group_by="ticker", progress=False, threads=True)
                break
            except Exception as e:  # noqa: BLE001
                print("retry", i, e, flush=True)
                time.sleep(10)
        for t in batch:
            try:
                sub = d[t] if len(batch) > 1 else d
                if sub["Close"].dropna().empty:
                    continue
                adj[t], close[t], vol[t] = sub["Adj Close"], sub["Close"], sub["Volume"]
            except Exception:  # noqa: BLE001
                continue
        print("prices", i + len(batch), "/", len(tickers), flush=True)
        time.sleep(2)
    return len(tickers) - 1, pd.DataFrame(adj), pd.DataFrame(close), pd.DataFrame(vol)


def run():
    os.makedirs(OUT_DIR, exist_ok=True)
    n_uni, adj, close, vol = load_prices()
    b = adj["0050.TW"].dropna()
    cal = b.index
    adj, close, vol = adj.reindex(cal), close.reindex(cal), vol.reindex(cal)
    wk = pd.Series(cal, index=cal).groupby([cal.isocalendar().year.values, cal.isocalendar().week.values]).max()
    sig_days = [pd.Timestamp(d) for d in wk.values if START <= pd.Timestamp(d) <= END]
    names = [c for c in adj.columns if c != "0050.TW"]
    tv20 = (close[names] * vol[names]).rolling(20).mean()
    r5_all = adj[names] / adj[names].shift(5) - 1
    b5 = b / b.shift(5) - 1
    volok = (vol[names] > 0).rolling(5).min() == 1
    trades = []
    for s in sig_days:
        i = cal.get_loc(s)
        if i + 1 + HOLD >= len(cal):
            continue
        rel = r5_all.loc[s] - b5.loc[s]
        ok = (tv20.loc[s] >= MIN_VALUE) & (close.loc[s, names] >= MIN_PX) & volok.loc[s] \
            & (r5_all.loc[s] <= R5_MAX) & (rel <= REL_MAX)
        for t in ok[ok].index:
            E = i + 1
            ent = adj[t].iloc[E]
            if not ent > 0:
                continue
            exit_i = E + HOLD
            for d in range(1, HOLD):
                if adj[t].iloc[E + d] <= ent * STOP:
                    exit_i = E + d + 1
                    break
            ex = adj[t].iloc[exit_i]
            if not ex > 0:
                continue
            ret = ex / ent - 1 - COST
            bret = b.iloc[exit_i] / b.iloc[E] - 1
            trades.append(dict(ticker=t, signal=s.date(), entry=cal[E].date(), exit=cal[exit_i].date(),
                               r5=round(r5_all.loc[s, t], 4), rel=round(rel[t], 4),
                               ret_net=ret, bench=bret, excess=ret - bret, stopped=exit_i < E + HOLD))
    tr = pd.DataFrame(trades)
    tr.to_csv(f"{OUT_DIR}/tw_reversal_v3_trades.csv", index=False)
    n = len(tr)
    lines = ["# Short-term v3 (attempt #2) backtest result (rule frozen 2026-11-12, claude/11)",
             f"Run (UTC): {dt.datetime.utcnow():%Y-%m-%d %H:%M}",
             f"Universe tickers: {n_uni}; with price data: {adj.shape[1] - 1}; signal weeks: {len(sig_days)}; trades: {n}"]
    if n == 0:
        lines += ["No trades.", "OVERALL: FAIL"]
    else:
        mean = tr.excess.mean()
        wkmean = tr.groupby("signal").excess.mean()
        tcl = wkmean.mean() / (wkmean.std(ddof=1) / math.sqrt(len(wkmean))) if len(wkmean) > 1 else float("nan")
        tr["entry_year"] = pd.to_datetime(tr.entry).dt.year
        by_year = tr.groupby("entry_year").excess.agg(["count", "mean"])
        yrs_pos = sum(by_year.loc[y, "mean"] > 0 for y in (2022, 2023, 2024, 2025) if y in by_year.index)
        trimmed = tr[tr.excess < tr.excess.quantile(0.95)].excess.mean()
        top1 = tr.sort_values("rel").groupby("signal").head(1).sort_values("signal")
        wk_pnl = top1.set_index(pd.to_datetime(top1.signal)).ret_net * POS
        wk_pnl = wk_pnl.reindex(pd.to_datetime(pd.Series(sig_days)), fill_value=0)
        worst13 = wk_pnl.rolling(13).sum().min()
        hold = tr[pd.to_datetime(tr.entry) >= "2025-01-01"].excess
        checks = {
            "1 trades >= 200": n >= 200,
            "2 mean excess > 0 and week-clustered t >= 2": bool(mean > 0 and tcl >= 2),
            "3 >= 3 of 2022-2025 years positive": yrs_pos >= 3,
            "4 mean excess > 0 without top 5%": bool(trimmed > 0),
            "5 top-1/week worst rolling 13-week PnL (TWD 16k) >= -18,000": bool(worst13 >= -18000),
            "6 holdout 2025-01..2026-10 mean excess > 0": bool(len(hold) > 0 and hold.mean() > 0),
        }
        lines += [
            f"Mean net return per trade: {tr.ret_net.mean():.4%}; mean 0050 same window: {tr.bench.mean():.4%}",
            f"Mean excess: {mean:.4%}; week-clustered t: {tcl:.2f} ({len(wkmean)} weeks); median excess: {tr.excess.median():.4%}; win rate vs 0050: {(tr.excess > 0).mean():.1%}",
            f"Stopped out: {tr.stopped.mean():.1%}; worst trade net: {tr.ret_net.min():.2%}",
            f"Mean excess without top 5%: {trimmed:.4%}",
            f"Top-1/week: trades {len(top1)}, mean excess {top1.excess.mean():.4%}, median {top1.excess.median():.4%}; worst rolling 13-week PnL TWD {worst13:,.0f}",
            f"Holdout 2025-01..2026-10: trades {len(hold)}, mean excess {hold.mean() if len(hold) else float('nan'):.4%}",
            "", "By entry year:", by_year.to_string(), "", "Checks:",
        ] + [f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in checks.items()] + [
            "", f"OVERALL: {'PASS' if all(checks.values()) else 'FAIL'}",
            "Known bias: Yahoo lacks most delisted stocks (survivorship), which likely flatters a buy-the-drop rule."]
    open(f"{OUT_DIR}/tw_reversal_v3_summary.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    run()
