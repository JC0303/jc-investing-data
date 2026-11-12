"""Backtest of JC Investing short-term rule v2 (claude/08, frozen 2026-11-12).

Rule (do NOT tune after seeing results; any change = new version + rerun):
- Universe: TWSE + TPEx common stocks (codes 1000-9999) that published monthly revenue.
- Signal for revenue month M: YoY >= 20% and <= 300%; YoY - mean(YoY of M-1..M-3) >= 15pp;
  revenue is the highest of the last 12 months (incl. M).
- Liquidity: 20-trading-day average traded value (close*volume) before entry >= TWD 3,000,000;
  close on the deadline day >= 10.
- Deadline day D = first trading day on/after the 10th of month M+1. Entry = close of the next trading day after D.
- Exit: close of the 10th trading day after entry; if any close on days 1..9 is <= entry*0.92,
  exit at the next day's close (day 10 trigger exits at day 10 close).
- Cost: 0.585% round trip. Benchmark: 0050 adjusted (total-return) close, same dates, no cost.
- Returns use adjusted close (dividends included).
Pass criteria (all): n>=200; mean excess>0 and t>=2; >=3 of 2022-2025 years mean excess>0;
mean excess>0 after dropping top 5%; worst rolling 3-month PnL of top-3-per-month at TWD 16,000
per trade >= -18,000.
"""
import io, time, sys, math, datetime as dt
import pandas as pd, numpy as np, requests

OUT_DIR = "results"
START_ROC_YEAR, START_MONTH = 109, 12   # 2020-12 (needed for 12-month window)
END_YEAR, END_MONTH = 2026, 10
COST = 0.00585
HOLD = 10
STOP = 0.92
MIN_VALUE = 3_000_000
POS = 16_000

HOSTS = ["https://mopsov.twse.com.tw"]
HDR = {"User-Agent": "Mozilla/5.0"}


def months():
    y, m = START_ROC_YEAR + 1911, START_MONTH
    while (y, m) <= (END_YEAR, END_MONTH):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_month(y, m, mkt):
    roc = y - 1911
    last_err = None
    for host in HOSTS:
        url = f"{host}/nas/t21/{mkt}/t21sc03_{roc}_{m}_0.html"
        for attempt in range(8):
            try:
                r = requests.get(url, headers=HDR, timeout=60)
                if r.status_code != 200:
                    last_err = f"{url} HTTP {r.status_code}"
                    time.sleep(3)
                    continue
                html = r.content.decode("big5", errors="ignore")
                tables = pd.read_html(io.StringIO(html), header=None)
                rows = []
                for t in tables:
                    if t.shape[1] < 5:
                        continue
                    sub = t.iloc[:, [0, 2, 4]].copy()
                    sub.columns = ["code", "rev", "rev_ly"]
                    sub["code"] = sub["code"].astype(str).str.strip()
                    sub = sub[sub["code"].str.fullmatch(r"\d{4}")]
                    if len(sub):
                        rows.append(sub)
                if not rows:
                    last_err = f"{url} no table"
                    break
                df = pd.concat(rows)
                df["code"] = df["code"].astype(str).str.strip()
                df = df[df["code"].str.fullmatch(r"\d{4}")]
                df["code_i"] = df["code"].astype(int)
                df = df[(df.code_i >= 1000) & (df.code_i <= 9999)].drop(columns="code_i")
                for c in ["rev", "rev_ly"]:
                    df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
                df["year"], df["month"], df["mkt"] = y, m, mkt
                time.sleep(1.5)
                return df.dropna(subset=["rev"]), None
            except Exception as e:  # noqa
                last_err = f"{url} {type(e).__name__}: {e}"
                time.sleep(10 * (attempt + 1))
    return None, last_err


def load_revenue():
    frames, errors = [], []
    for y, m in months():
        for mkt in ("sii", "otc"):
            df, err = fetch_month(y, m, mkt)
            if df is None:
                errors.append(err)
                print("FAIL", err, flush=True)
                if not frames and len(errors) >= 2:
                    sys.exit("First revenue pages failed; stopping early: " + "; ".join(errors))
            else:
                frames.append(df)
                print("ok", y, m, mkt, len(df), flush=True)
    rev = pd.concat(frames).drop_duplicates(["code", "year", "month"])
    rev.to_csv("data/tw_monthly_revenue.csv", index=False)
    return rev, errors


def signals(rev):
    rev = rev.sort_values(["code", "year", "month"]).copy()
    rev["ym"] = rev.year * 12 + rev.month - 1
    out = []
    for code, g in rev.groupby("code"):
        g = g.set_index("ym")
        for ym, row in g.iterrows():
            y, m = divmod(ym, 12)
            m += 1
            if (y, m) < (2022, 1):
                continue
            if not (row.rev_ly and row.rev_ly > 0):
                continue
            yoy = row.rev / row.rev_ly - 1
            if yoy < 0.20 or yoy > 3.0:
                continue
            prev = [ym - k for k in (1, 2, 3)]
            if not all(p in g.index for p in prev):
                continue
            pyoy = []
            for p in prev:
                r = g.loc[p]
                if not (r.rev_ly and r.rev_ly > 0):
                    break
                pyoy.append(r.rev / r.rev_ly - 1)
            if len(pyoy) < 3:
                continue
            accel = yoy - float(np.mean(pyoy))
            if accel < 0.15:
                continue
            window = [ym - k for k in range(0, 12)]
            if not all(p in g.index for p in window):
                continue
            if row.rev < max(g.loc[p].rev for p in window):
                continue
            out.append(dict(code=code, mkt=row.mkt, year=y, month=m, yoy=yoy, accel=accel))
    return pd.DataFrame(out)


def load_prices(sig):
    import yfinance as yf
    tick = {c: (c + (".TW" if mk == "sii" else ".TWO")) for c, mk in sig[["code", "mkt"]].drop_duplicates().values}
    tickers = sorted(set(tick.values())) + ["0050.TW"]
    adj, close, vol = {}, {}, {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i + 100]
        d = yf.download(batch, start="2021-11-01", end=dt.date.today().isoformat(), auto_adjust=False,
                        group_by="ticker", progress=False, threads=True)
        for t in batch:
            try:
                sub = d[t] if len(batch) > 1 else d
                if sub["Close"].dropna().empty:
                    continue
                adj[t], close[t], vol[t] = sub["Adj Close"], sub["Close"], sub["Volume"]
            except Exception:
                continue
        time.sleep(2)
    return tick, pd.DataFrame(adj), pd.DataFrame(close), pd.DataFrame(vol)


def run():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    rev, errors = load_revenue()
    sig = signals(rev)
    tick, adj, close, vol = load_prices(sig)
    cal = adj["0050.TW"].dropna().index
    trades, missing = [], 0
    for s in sig.itertuples():
        ny, nm = (s.year + (s.month == 12), s.month % 12 + 1)
        tenth = pd.Timestamp(ny, nm, 10)
        idx = cal.searchsorted(tenth)
        if idx + 1 + HOLD >= len(cal):
            continue
        D, E = cal[idx], idx + 1
        t = tick[s.code]
        if t not in adj:
            missing += 1
            continue
        a = adj[t].reindex(cal)
        c = close[t].reindex(cal)
        v = vol[t].reindex(cal)
        tv = (c * v).iloc[max(0, E - 20):E].mean()
        if not (tv >= MIN_VALUE) or not (c.iloc[idx] >= 10):
            continue
        ent = a.iloc[E]
        if not (ent > 0):
            missing += 1
            continue
        exit_i = E + HOLD
        for d in range(1, HOLD):
            px = a.iloc[E + d]
            if px <= ent * STOP:
                exit_i = E + d + 1
                break
        ex = a.iloc[exit_i]
        if not (ex > 0):
            missing += 1
            continue
        b = adj["0050.TW"]
        ret = ex / ent - 1 - COST
        bret = b.iloc[exit_i] / b.iloc[E] - 1
        trades.append(dict(code=s.code, mkt=s.mkt, rev_month=f"{s.year}-{s.month:02d}", entry=cal[E].date(),
                           exit=cal[exit_i].date(), yoy=round(s.yoy, 4), accel=round(s.accel, 4),
                           ret_net=ret, bench=bret, excess=ret - bret, stopped=exit_i < E + HOLD))
    tr = pd.DataFrame(trades)
    tr.to_csv(f"{OUT_DIR}/tw_rev_momentum_v2_trades.csv", index=False)

    n = len(tr)
    mean, sd = tr.excess.mean(), tr.excess.std(ddof=1)
    tstat = mean / (sd / math.sqrt(n)) if n > 1 else float("nan")
    tr["entry_year"] = pd.to_datetime(tr.entry).dt.year
    by_year = tr.groupby("entry_year").excess.agg(["count", "mean"])
    yrs_pos = sum(by_year.loc[y, "mean"] > 0 for y in (2022, 2023, 2024, 2025) if y in by_year.index)
    cut = tr.excess.quantile(0.95)
    trimmed = tr[tr.excess < cut].excess.mean()
    top3 = tr.sort_values("accel", ascending=False).groupby("rev_month").head(3)
    monthly = top3.groupby("rev_month").ret_net.sum() * POS
    worst3 = monthly.sort_index().rolling(3).sum().min()
    checks = {
        "1 trades >= 200": n >= 200,
        "2 mean excess > 0 and t >= 2": bool(mean > 0 and tstat >= 2),
        "3 >= 3 of 2022-2025 years positive": yrs_pos >= 3,
        "4 mean excess > 0 without top 5%": bool(trimmed > 0),
        "5 worst rolling 3-month PnL (top-3/month, TWD 16k) >= -18,000": bool(worst3 >= -18000),
    }
    passed = all(checks.values())
    lines = [
        "# Short-term v2 backtest result (rule frozen 2026-11-12, claude/08)",
        f"Run (UTC): {dt.datetime.utcnow():%Y-%m-%d %H:%M}",
        f"Revenue pages failed: {len(errors)}" + (" — " + "; ".join(errors[:5]) if errors else ""),
        f"Signals: {len(sig)}; trades: {n}; signals without price data (likely delisted/unavailable, survivorship bias): {missing}",
        f"Mean net return per trade: {tr.ret_net.mean():.4%}; mean 0050 same window: {tr.bench.mean():.4%}",
        f"Mean excess: {mean:.4%}; t-stat: {tstat:.2f}; median excess: {tr.excess.median():.4%}; win rate vs 0050: {(tr.excess > 0).mean():.1%}",
        f"Stopped out: {tr.stopped.mean():.1%}; worst trade net: {tr.ret_net.min():.2%}",
        f"Mean excess without top 5%: {trimmed:.4%}",
        f"Top-3/month subset: trades {len(top3)}, mean excess {top3.excess.mean():.4%}; worst rolling 3-month PnL TWD {worst3:,.0f}",
        "", "By entry year:", by_year.to_string(), "", "Checks:",
    ] + [f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in checks.items()] + [
        "", f"OVERALL: {'PASS' if passed else 'FAIL'}",
    ]
    open(f"{OUT_DIR}/tw_rev_momentum_v2_summary.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    run()
