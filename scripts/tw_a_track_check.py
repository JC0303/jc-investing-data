"""JC Investing: historical check of the LIVE short-term simulation A-track (短線模擬規格 v1, frozen 2026-11-13).

Purpose (JC approved 2026-11-21, plan "A"): the A-track has been running in the simulation sheet without ever being
backtested; 14/14 settled trades hit the stop. This script tests the SAME rule on 2022-2026 history. It does not
change any parameter and is not a new attempt (#4); it is a check of the rule already in use.

Rule as tested (spec v1 points 4, 6, 7, 8) with one disclosed approximation:
- ADVANCE proxy = rule v1.1 route A, revenue part only: latest published single-month revenue YoY >= 20% and <= 300%;
  acceleration (single-month YoY minus year-to-date cumulative YoY) >= 10 pp; FLAG: cumulative YoY > 300% excluded.
  NOT reproduced (no point-in-time history in the repo): route A's P/E / YoY <= 1 test, routes B and C (P/E, P/B,
  yield). So the proxy universe is wider than the live rule. Revenue month M counts as known from the first trading
  day on/after the 10th of M+1 (legal deadline; conservative).
- Signal day D: daily return (adjusted close) >= +2%; traded value (close x volume) on D >= TWD 30,000,000.
- Cap: max 5 entries per day, ranked by D's return, highest first; a stock already held is skipped (DUP).
- Entry: close of the first trading day after D.
- Exit ("波段"): first close <= entry x 0.92 (stop) or >= entry x 1.15 (target), exit at THAT close; else close of
  day 20 after entry.
- Cost: stock round trip 0.585%; benchmark 0050 adjusted close on the same dates minus its own round trip 0.385%
  (0.1425% x 2 + 0.1% ETF tax), as spec point 8 says.

Pass criteria, written before any run (spec point 9 a-c, e; Taiwan only):
 1 settled trades >= 100
 2 mean net excess > 0
 3 mean net excess > 0 after removing the best 5% of trades
 4 signal-date clustered t >= 2
 5 mean net excess > 0 after removing the best calendar month (does not depend on a single month)
All five -> PASS. Otherwise FAIL.

Diagnostics (reported only; NOT eligible to be adopted as a rule - any new rule is attempt #4 and needs JC):
 D1 executable exit: exit at the close of the day AFTER the trigger (a real order cannot sell at the close that
    reveals the trigger)
 D2 split by signal-day return >= 9.5% (limit-up chase) vs < 9.5%
 D3 no 5-per-day cap (every qualifying signal)
Known bias: Yahoo lacks most delisted stocks -> results optimistic. Industry split not available.
"""
import datetime as dt
import math
import os
import time

import numpy as np
import pandas as pd

OUT = "results"
COST_STOCK = 0.00585
COST_BENCH = 0.00385
STOP, TARGET, HOLD = 0.92, 1.15, 20
MIN_VALUE = 30_000_000
MIN_RET = 0.02
CAP = 5
START, SIG_END = pd.Timestamp("2022-01-01"), pd.Timestamp("2026-10-31")


def monthly_flags(rev):
    rev = rev.sort_values(["code", "year", "month"]).drop_duplicates(["code", "year", "month"]).copy()
    rev = rev[(rev.rev_ly > 0) & (rev.rev >= 0)]
    rev["yoy"] = rev.rev / rev.rev_ly - 1
    g = rev.groupby(["code", "year"])
    rev["cum"] = g.rev.cumsum() / g.rev_ly.cumsum() - 1
    # cumulative needs every month from January of that year
    rev["nmon"] = g.cumcount() + 1
    rev = rev[rev.nmon == rev.month]
    rev["accel"] = rev.yoy - rev.cum
    rev["ok"] = (rev.yoy >= 0.20) & (rev.yoy <= 3.0) & (rev.accel >= 0.10) & (rev.cum <= 3.0)
    return rev


def load_prices(tickers):
    import yfinance as yf
    tickers = sorted(set(tickers)) + ["0050.TW"]
    adj, close, vol = {}, {}, {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i + 100]
        d = None
        for _ in range(3):
            try:
                d = yf.download(batch, start="2021-11-01", end=dt.date.today().isoformat(), auto_adjust=False,
                                group_by="ticker", progress=False, threads=True)
                break
            except Exception as e:  # noqa: BLE001
                print("retry", e, flush=True)
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
    return pd.DataFrame(adj), pd.DataFrame(close), pd.DataFrame(vol)


def applicable_month(day):
    """The revenue month a trading day is allowed to know about.

    Taiwan monthly revenue for month M is published by the 10th of M+1, so a
    trading day before the 10th may only use M-2, and from the 10th onward
    M-1. This is a lookup, never a carry-forward.
    """
    y, m = day.year, day.month
    back = 2 if day.day < 10 else 1
    m -= back
    while m < 1:
        m += 12
        y -= 1
    return y, m


def qualified_matrix(flags, cal, tickers):
    """Eligibility per (day, ticker), from that day's applicable month only.

    This used to place each flag at the first session on or after the 10th of
    the following month and then ffill(). The forward fill was the bug: when a
    later month had no computable revenue, the previous month's verdict stayed
    in force indefinitely, so a day could be qualified on revenue that was by
    then many months old. A month with no usable data is now simply not
    eligible, which excludes the name from that day's candidates rather than
    guessing at it.
    """
    known = {}
    for r in flags.itertuples():
        known[(r.ticker, int(r.year), int(r.month))] = bool(r.ok)
    months = [applicable_month(d) for d in cal]
    q = pd.DataFrame(False, index=cal, columns=tickers)
    for t in tickers:
        q[t] = [known.get((t, y, m), False) for y, m in months]
    return q


def exit_index(a, E, executable):
    ent = a[E]
    last = len(a) - 1
    for d in range(1, HOLD + 1):
        if E + d > last or not a[E + d] > 0:
            return None, None
        px = a[E + d]
        if px <= ent * STOP or px >= ent * TARGET:
            reason = "stop" if px <= ent * STOP else "target"
            x = E + d + (1 if executable else 0)
            return (x, reason) if x <= last and a[x] > 0 else (None, None)
    return E + HOLD, "time"


def simulate(cands, adj, b, cal, cap, executable):
    held_until = {}
    rows = []
    for D, day in cands.groupby("D", sort=True):
        di = cal.get_loc(D)
        day = day.sort_values("r1", ascending=False)
        taken = 0
        for c in day.itertuples():
            if cap and taken >= cap:
                break
            if held_until.get(c.ticker, -1) >= di:
                continue  # DUP
            E = di + 1
            if E >= len(cal):
                continue
            a = adj[c.ticker].values
            if not a[E] > 0:
                continue
            x, why = exit_index(a, E, executable)
            if x is None:
                continue
            held_until[c.ticker] = x
            taken += 1
            ret = a[x] / a[E] - 1 - COST_STOCK
            bret = b.iloc[x] / b.iloc[E] - 1 - COST_BENCH
            rows.append(dict(ticker=c.ticker, signal=D, r1=c.r1, gap=a[E] / a[di] - 1, entry=cal[E], exit=cal[x],
                             days=x - E, reason=why, ret_net=ret, bench_net=bret, excess=ret - bret))
    return pd.DataFrame(rows)


def tstat(df):
    g = df.groupby("signal").excess.mean()
    return g.mean() / (g.std(ddof=1) / math.sqrt(len(g))) if len(g) > 2 and g.std(ddof=1) > 0 else float("nan")


def trimmed(x):
    return x[x < x.quantile(0.95)].mean() if len(x) else float("nan")


def drop_best_month(df):
    if df.empty:
        return float("nan")
    m = df.signal.dt.to_period("M")
    best = df.groupby(m).excess.sum().idxmax()
    return df[m != best].excess.mean()


def describe(df, name):
    if df.empty:
        return [f"{name}: no trades"]
    st = df.reason.value_counts(normalize=True)
    return [f"{name}: trades {len(df)}; signal days {df.signal.nunique()}; mean net {df.ret_net.mean():.3%}; "
            f"mean 0050 net {df.bench_net.mean():.3%}; mean excess {df.excess.mean():.3%}; median excess "
            f"{df.excess.median():.3%}; clustered t {tstat(df):.2f}; without top 5% {trimmed(df.excess):.3%}; "
            f"stop {st.get('stop', 0):.0%} / target {st.get('target', 0):.0%} / time {st.get('time', 0):.0%}; "
            f"mean days {df.days.mean():.1f}; mean entry gap vs signal close {df.gap.mean():.2%}"]


def run(prices=None):
    os.makedirs(OUT, exist_ok=True)
    rev = pd.read_csv("data/tw_monthly_revenue.csv", dtype={"code": str})
    rev = rev[rev.code.str.fullmatch(r"[1-9]\d{3}")]
    flags = monthly_flags(rev)
    flags["ticker"] = flags.code + np.where(flags.mkt == "sii", ".TW", ".TWO")
    adj, close, vol = prices if prices is not None else load_prices(flags.ticker.unique().tolist())
    b = adj["0050.TW"].dropna()
    cal = b.index
    adj, close, vol = adj.reindex(cal), close.reindex(cal), vol.reindex(cal)
    tick = [t for t in adj.columns if t != "0050.TW"]
    q = qualified_matrix(flags, cal, tick)
    r1 = adj[tick] / adj[tick].shift(1) - 1
    tv = close[tick] * vol[tick]
    m = q & (r1 >= MIN_RET) & (tv >= MIN_VALUE)
    m = m[(m.index >= START) & (m.index <= SIG_END)]
    st = m.stack()
    st = st[st]
    cands = pd.DataFrame({"D": st.index.get_level_values(0), "ticker": st.index.get_level_values(1)})
    cands["r1"] = [r1.at[d, t] for d, t in zip(cands.D, cands.ticker)]

    main = simulate(cands, adj, b, cal, CAP, executable=False)
    main.to_csv(f"{OUT}/tw_a_track_trades.csv", index=False)
    d1 = simulate(cands, adj, b, cal, CAP, executable=True)
    d3 = simulate(cands, adj, b, cal, 0, executable=False)

    tt = tstat(main)
    checks = {
        "1 settled trades >= 100": len(main) >= 100,
        "2 mean net excess > 0": bool(main.excess.mean() > 0),
        "3 mean net excess > 0 without top 5%": bool(trimmed(main.excess) > 0),
        "4 signal-date clustered t >= 2": bool(tt >= 2),
        "5 mean net excess > 0 without best calendar month": bool(drop_best_month(main) > 0),
    }
    main["yr"] = main.signal.dt.year
    lines = ["# Short-term simulation A-track: historical check (spec v1 frozen 2026-11-13; check approved 2026-11-21)",
             f"Run (UTC): {dt.datetime.utcnow():%Y-%m-%d %H:%M}",
             f"Tickers with prices: {len(tick)}; candidate signals (no cap): {len(cands)}",
             "Approximation: ADVANCE proxy = route A revenue part only (no historical P/E; routes B/C not reproduced).",
             "", *describe(main, "MAIN (rule as live)"),
             "", "By signal year (count, mean excess):", main.groupby("yr").excess.agg(["count", "mean"]).to_string(),
             "", "Pass checks:"] + [f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in checks.items()]
    lines += ["", f"OVERALL: {'PASS' if all(checks.values()) else 'FAIL'}",
              "", "Diagnostics (not adoptable as rules):", *describe(d1, "D1 executable exit (next-day close)"),
              *describe(main[main.r1 >= 0.095], "D2a signal-day return >= 9.5% (limit-up chase)"),
              *describe(main[main.r1 < 0.095], "D2b signal-day return < 9.5%"),
              *describe(d3, "D3 no daily cap"),
              "", "Known bias: Yahoo lacks most delisted stocks -> optimistic."]
    with open(f"{OUT}/tw_a_track_summary.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    run()
