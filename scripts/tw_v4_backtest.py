"""JC Investing short-term v4 = attempt #3 (claude/12, frozen 2026-11-12 before any run).

Built from lessons of v2/v3: keep the revenue-momentum signal (v2 caught big winners), let winners run with a
trailing stop instead of a fixed 10-day exit, trade less often, and only buy stocks already in an uptrend (v3 showed
short-term losers keep losing).

Design: tune on 2022-2024 only (in-sample), pick ONE combo automatically, test it ONCE on 2025-01..2026 (out-of-sample).
Out-of-sample numbers are computed only for the selected combo.

Fixed parts:
- Universe: codes in data/tw_monthly_revenue.csv (TWSE sii / TPEx otc, 1000-9999) with Yahoo prices.
- Signal for revenue month M (M >= 2022-01): YoY <= 300%; revenue = highest of the last 12 months (incl. M).
- Deadline D = first trading day on/after the 10th of M+1; entry E = close of the next trading day.
- Filters at D: 20-day average traded value >= TWD 10,000,000; close >= 10.
- Initial stop: close <= entry*0.92 -> exit next day's close. Trailing stop: close <= peak close since entry*(1-T)
  -> exit next day's close. Time exit: close of day E+H.
- Cost 0.585% round trip; benchmark 0050 adjusted close, same dates.
Tuning grid (32 combos): YoY >= {20%, 30%}; acceleration (YoY minus mean YoY of M-1..M-3) >= {10, 20} pp;
  uptrend filter close[D] >= 60-day average close {off, on}; trailing T {10%, 15%}; max hold H {40, 60} days.
Selection: in-sample = entry < 2025-01-01 and exit <= 2024-12-31; need >= 150 trades; maximise entry-date-clustered
  t of mean excess; tie -> higher mean excess without top 5%.
Out-of-sample pass criteria (all): 1 trades >= 60; 2 mean excess > 0 and clustered t >= 2.5; 3 mean excess > 0
  without top 5%; 4 entry-year 2025 mean excess > 0 AND 2026 mean excess > 0; 5 top-3-per-month by acceleration at
  TWD 16,000/trade: worst rolling 3-month PnL >= -18,000; 6 selected combo in-sample mean excess > 0.
"""
import datetime as dt
import itertools
import math
import os
import time

import numpy as np
import pandas as pd

OUT = "results"
COST = 0.00585
STOP = 0.92
MIN_VALUE = 10_000_000
MIN_PX = 10
POS = 16_000
IS_END = pd.Timestamp("2025-01-01")
GRID = dict(Y=[0.20, 0.30], A=[0.10, 0.20], MA=[False, True], T=[0.10, 0.15], H=[40, 60])


def base_signals(rev):
    rev = rev.sort_values(["code", "year", "month"]).copy()
    rev["ym"] = rev.year * 12 + rev.month - 1
    out = []
    for code, g in rev.groupby("code"):
        g = g.drop_duplicates("ym").set_index("ym")
        for ym, row in g.iterrows():
            y, m = divmod(ym, 12)
            m += 1
            if (y, m) < (2022, 1) or not (row.rev_ly and row.rev_ly > 0):
                continue
            yoy = row.rev / row.rev_ly - 1
            if yoy < min(GRID["Y"]) or yoy > 3.0:
                continue
            prev = [ym - k for k in (1, 2, 3)]
            if not all(p in g.index and g.loc[p].rev_ly and g.loc[p].rev_ly > 0 for p in prev):
                continue
            accel = yoy - float(np.mean([g.loc[p].rev / g.loc[p].rev_ly - 1 for p in prev]))
            if accel < min(GRID["A"]):
                continue
            window = [ym - k for k in range(12)]
            if not all(p in g.index for p in window) or row.rev < max(g.loc[p].rev for p in window):
                continue
            out.append(dict(code=code, mkt=row.mkt, year=y, month=m, yoy=yoy, accel=accel))
    return pd.DataFrame(out)


def load_prices(codes):
    import yfinance as yf
    tickers = sorted(set(codes)) + ["0050.TW"]
    adj, close, vol = {}, {}, {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i + 100]
        d = None
        for _ in range(3):
            try:
                d = yf.download(batch, start="2021-09-01", end=dt.date.today().isoformat(), auto_adjust=False,
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


def simulate(a, E, T, H):
    ent, peak = a[E], a[E]
    last = len(a) - 1
    for d in range(1, H + 1):
        if E + d > last:
            return None
        px = a[E + d]
        if not px > 0:
            return None
        if d < H and (px <= ent * STOP or px <= peak * (1 - T)):
            return E + d + 1 if E + d + 1 <= last else None
        peak = max(peak, px)
    return E + H


def tstat(df):
    g = df.groupby("entry").excess.mean()
    return g.mean() / (g.std(ddof=1) / math.sqrt(len(g))) if len(g) > 2 and g.std(ddof=1) > 0 else float("nan")


def trimmed(x):
    return x[x < x.quantile(0.95)].mean() if len(x) else float("nan")


def run(prices=None):
    os.makedirs(OUT, exist_ok=True)
    rev = pd.read_csv("data/tw_monthly_revenue.csv", dtype={"code": str})
    sig = base_signals(rev)
    sig["ticker"] = sig.code + np.where(sig.mkt == "sii", ".TW", ".TWO")
    adj, close, vol = prices if prices is not None else load_prices(sig.ticker.tolist())
    b = adj["0050.TW"].dropna()
    cal = b.index
    adj, close, vol = adj.reindex(cal), close.reindex(cal), vol.reindex(cal)
    tv20 = (close * vol).rolling(20).mean()
    ma60 = close.rolling(60).mean()
    rows = []
    for s in sig.itertuples():
        if s.ticker not in adj:
            continue
        ny, nm = (s.year + (s.month == 12), s.month % 12 + 1)
        idx = cal.searchsorted(pd.Timestamp(ny, nm, 10))
        E = idx + 1
        if E >= len(cal):
            continue
        D = cal[idx]
        if not (tv20.at[D, s.ticker] >= MIN_VALUE and close.at[D, s.ticker] >= MIN_PX):
            continue
        a = adj[s.ticker].values
        if not a[E] > 0:
            continue
        up = bool(close.at[D, s.ticker] >= ma60.at[D, s.ticker])
        for T, H in itertools.product(GRID["T"], GRID["H"]):
            x = simulate(a, E, T, H)
            if x is None or not a[x] > 0:
                continue
            ret = a[x] / a[E] - 1 - COST
            bret = b.iloc[x] / b.iloc[E] - 1
            rows.append(dict(ticker=s.ticker, rev_month=f"{s.year}-{s.month:02d}", yoy=s.yoy, accel=s.accel, up=up,
                             T=T, H=H, entry=cal[E], exit=cal[x], ret_net=ret, bench=bret, excess=ret - bret))
    allt = pd.DataFrame(rows)
    ins = allt[(allt.entry < IS_END) & (allt.exit < IS_END)]
    oos_all = allt[allt.entry >= IS_END]
    grid_rows = []
    for Y, A, MA, T, H in itertools.product(*GRID.values()):
        f = ins[(ins.yoy >= Y) & (ins.accel >= A) & (ins["T"] == T) & (ins.H == H) & (ins.up | (not MA))]
        grid_rows.append(dict(Y=Y, A=A, MA=MA, T=T, H=H, n=len(f), mean=f.excess.mean(), t=tstat(f),
                              trimmed=trimmed(f.excess)))
    grid = pd.DataFrame(grid_rows)
    grid.to_csv(f"{OUT}/tw_v4_insample_grid.csv", index=False)
    elig = grid[grid.n >= 150].sort_values(["t", "trimmed"], ascending=False)
    lines = ["# Short-term v4 (attempt #3) result (rule frozen 2026-11-12, claude/12)",
             f"Run (UTC): {dt.datetime.utcnow():%Y-%m-%d %H:%M}",
             f"Base signals: {len(sig)}; simulated trade-variants: {len(allt)}",
             "", "In-sample grid (2022-2024), sorted by clustered t:", elig.head(32).to_string(index=False)]
    if elig.empty:
        lines += ["", "No combo with >= 150 in-sample trades.", "OVERALL: FAIL"]
    else:
        c = elig.iloc[0]
        sel = dict(Y=float(c["Y"]), A=float(c["A"]), MA=bool(c["MA"]), T=float(c["T"]), H=int(c["H"]))
        o = oos_all[(oos_all.yoy >= sel["Y"]) & (oos_all.accel >= sel["A"]) & (oos_all["T"] == sel["T"])
                    & (oos_all.H == sel["H"]) & (oos_all.up | (not sel["MA"]))].copy()
        o.to_csv(f"{OUT}/tw_v4_oos_trades.csv", index=False)
        o["yr"] = o.entry.dt.year
        by_year = o.groupby("yr").excess.agg(["count", "mean"])
        y25 = by_year["mean"].get(2025, float("nan"))
        y26 = by_year["mean"].get(2026, float("nan"))
        top3 = o.sort_values("accel", ascending=False).groupby("rev_month").head(3)
        monthly = (top3.groupby("rev_month").ret_net.sum() * POS).sort_index()
        worst3 = monthly.rolling(3, min_periods=1).sum().min() if len(monthly) else float("nan")
        tt = tstat(o)
        checks = {
            "1 OOS trades >= 60": len(o) >= 60,
            "2 OOS mean excess > 0 and clustered t >= 2.5": bool(o.excess.mean() > 0 and tt >= 2.5),
            "3 OOS mean excess > 0 without top 5%": bool(trimmed(o.excess) > 0),
            "4 OOS 2025 and 2026 mean excess both > 0": bool(y25 > 0 and y26 > 0),
            "5 OOS top-3/month worst rolling 3-month PnL (TWD 16k) >= -18,000": bool(worst3 >= -18000),
            "6 selected combo in-sample mean excess > 0": bool(c["mean"] > 0),
        }
        lines += ["", f"Selected combo (in-sample): {sel}; IS trades {int(c['n'])}, IS mean excess {c['mean']:.4%}, IS t {c['t']:.2f}",
                  "", "Out-of-sample (2025-01 onward), selected combo only:",
                  f"Trades {len(o)}; mean net {o.ret_net.mean():.4%}; mean 0050 {o.bench.mean():.4%}; mean excess {o.excess.mean():.4%}; clustered t {tt:.2f}",
                  f"Median excess {o.excess.median():.4%}; win rate {(o.excess > 0).mean():.1%}; without top 5% {trimmed(o.excess):.4%}",
                  f"Average holding days {((o.exit - o.entry).dt.days).mean():.1f}; worst trade {o.ret_net.min():.2%}",
                  f"Top-3/month: trades {len(top3)}, mean excess {top3.excess.mean():.4%}; worst rolling 3-month PnL TWD {worst3:,.0f}",
                  "", "By entry year:", by_year.to_string(), "", "Checks:"]
        lines += [f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in checks.items()]
        lines += ["", f"OVERALL: {'PASS' if all(checks.values()) else 'FAIL'}",
                  "Caveats: 2025-26 data was partly seen in v2/v3 results (not a fully clean test); Yahoo lacks most delisted stocks."]
    open(f"{OUT}/tw_v4_summary.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    run()
