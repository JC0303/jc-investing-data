"""JC Investing: monthly snapshot of the Taiwan screen (rule v1.1) and forward evaluation (long-term upgrade #1).

Approved by JC 2026-11-21 (plan "A"). Purpose: the shadow log adds ~10 hand-researched names a month, far too few to
learn whether the screen itself has any value. This job freezes the WHOLE screen each month (every Taiwan common
stock, its rule v1.1 status and routes) and, 1 and 3 months later, measures each name's price return against 0050.
No Claude usage; runs in GitHub Actions.

Snapshot (mode "snapshot"): replicates the sheet tab 全市場 (formulas read 2026-11-21) from the repo's raw files:
- universe: codes 1000-9999 in the TWSE (BWIBBU) and TPEx valuation files
- status: no traded value -> DATA_GAP; value < 3,000,000 -> EXCLUDED; no P/E -> EXCLUDED; no monthly revenue ->
  DATA_GAP; >= 1 route -> FLAG if P/E < 5 or yield > 15% or cumulative YoY > 300% else ADVANCE; else REJECT_RULE
- route A: YoY >= 20, YoY <= 300, YoY - cumulative YoY >= 10, P/E > 0, P/E / YoY <= 1
- route B: 0 < P/E <= 12, P/B <= 1.5, yield >= 4, cumulative YoY >= -5, YoY >= cumulative YoY
- route C: ROE (= P/B / P/E x 100) >= 15, P/E <= 20, cumulative YoY >= 8
Writes data/snapshots/tw_rank_<data date>.csv (one per data date; never rewritten).

Evaluation (mode "evaluate"), pre-registered 2026-11-21 before any result:
- horizons: 1 month (first run >= 28 calendar days after the snapshot) and 3 months (first run >= 85 days after);
  each snapshot is evaluated once per horizon, appended to results/rank_ic_log.csv, never rewritten
- return = latest close / snapshot close - 1 (price only; dividends ignored on both sides); excess = return - 0050
  return over the same dates. Names without both prices are counted as missing, not dropped silently.
- per cross-section: mean excess of ADVANCE, REJECT_RULE and FLAG; spread = ADVANCE - REJECT_RULE; Spearman IC between
  route count (0-3) and excess over ADVANCE + REJECT_RULE names; same for route A score (YoY / P/E) among route-A names
- verdict rule (3-month horizon only): no conclusion before 12 monthly cross-sections. At >= 12: the screen "adds
  value" only if mean spread > 0 AND mean IC > 0 AND IC t-stat (mean / (sd / sqrt n)) >= 2. Otherwise "no evidence".
Known limits: survivorship within a horizon (delisted names become missing); price-only returns; one market regime.
"""
import csv
import datetime as dt
import glob
import io
import math
import os
import sys

import pandas as pd

D = "data/tw"
SNAP = "data/snapshots"
OUT = "results"


def num(x):
    try:
        x = str(x).replace(",", "").strip()
        return float(x) if x not in ("", "N/A", "--", "-") else None
    except ValueError:
        return None


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def rows(path):
    return list(csv.reader(io.StringIO(read_text(path))))


def is_code(c):
    c = c.strip()
    return c.isdigit() and 1000 <= int(c) <= 9999 and len(c) == 4


def prices():
    """code -> (close, traded value) for TWSE and TPEx, plus data date."""
    p = {}
    r = rows(f"{D}/stock_day_all.csv")
    date = None
    for x in r[1:]:
        if len(x) > 8:
            p[x[1].strip()] = (num(x[8]), num(x[4]))
            date = date or x[0].strip()
    for x in rows(f"{D}/tpex_close.csv"):
        if len(x) > 9 and x[0].strip() and x[0].strip() not in p:
            p[x[0].strip()] = (num(x[2]), num(x[9]))
    y, m, d = int(date[:3]) + 1911, int(date[3:5]), int(date[5:7])
    return p, dt.date(y, m, d)


def snapshot():
    p, ddate = prices()
    val = {}
    for x in rows(f"{D}/bwibbu_all.csv")[1:]:
        if len(x) >= 6 and is_code(x[1]):
            val[x[1].strip()] = ("上市", num(x[3]), num(x[4]), num(x[5]))
    for x in rows(f"{D}/tpex_pe.csv"):
        if len(x) >= 7 and is_code(x[0]):
            val[x[0].strip()] = ("上櫃", num(x[2]), num(x[5]), num(x[6]))
    rev = {}
    for f in ("mops_rev_L.csv", "mops_rev_O.csv"):
        for x in rows(f"{D}/{f}")[1:]:
            if len(x) >= 13 and is_code(x[2]):
                rev[x[2].strip()] = (x[1].strip(), num(x[9]), num(x[12]))
    out = []
    for c, (mkt, pe, yld, pb) in sorted(val.items()):
        close, value = p.get(c, (None, None))
        rm, yoy, cum = rev.get(c, ("", None, None))
        roe = pb / pe * 100 if pe and pe > 0 and pb is not None else None
        a = int(yoy is not None and cum is not None and pe is not None and 20 <= yoy <= 300 and yoy - cum >= 10
                and pe > 0 and pe / yoy <= 1)
        b = int(None not in (pe, yld, pb, yoy, cum) and 0 < pe <= 12 and pb <= 1.5 and yld >= 4 and cum >= -5
                and yoy >= cum)
        cc = int(roe is not None and cum is not None and roe >= 15 and pe <= 20 and cum >= 8)
        if value is None:
            st = "DATA_GAP"
        elif value < 3_000_000:
            st = "EXCLUDED"
        elif pe is None:
            st = "EXCLUDED"
        elif yoy is None:
            st = "DATA_GAP"
        elif a + b + cc > 0:
            st = "FLAG" if (pe < 5 or (yld is not None and yld > 15) or (cum is not None and cum > 300)) else "ADVANCE"
        else:
            st = "REJECT_RULE"
        out.append(dict(code=c, mkt=mkt, close=close, value=value, pe=pe, yld=yld, pb=pb, roe=roe, rev_month=rm,
                        yoy=yoy, cum=cum, A=a, B=b, C=cc, routes=a + b + cc, a_score=(yoy / pe if a else None),
                        status=st))
    df = pd.DataFrame(out)
    b0050 = p.get("0050", (None, None))[0]
    os.makedirs(SNAP, exist_ok=True)
    path = f"{SNAP}/tw_rank_{ddate.isoformat()}.csv"
    if os.path.exists(path):
        print("snapshot exists, not rewritten:", path)
        return
    df.insert(0, "bench_0050", b0050)
    df.insert(0, "snapshot_date", ddate.isoformat())
    df.to_csv(path, index=False)
    print(path, len(df), df.status.value_counts().to_dict(), "A/B/C", int(df.A.sum()), int(df.B.sum()), int(df.C.sum()))


def spearman(x, y):
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 10 or d.x.nunique() < 2:
        return float("nan"), len(d)
    return d.x.rank().corr(d.y.rank()), len(d)


def evaluate():
    p, ddate = prices()
    b_now = p.get("0050", (None, None))[0]
    log_path = f"{OUT}/rank_ic_log.csv"
    log = pd.read_csv(log_path) if os.path.exists(log_path) else pd.DataFrame()
    done = set(zip(log.snapshot, log.horizon)) if len(log) else set()
    new = []
    for f in sorted(glob.glob(f"{SNAP}/tw_rank_*.csv")):
        s = pd.read_csv(f, dtype={"code": str})
        sd = dt.date.fromisoformat(s.snapshot_date.iloc[0])
        age = (ddate - sd).days
        for h, need in (("1m", 28), ("3m", 85)):
            if age < need or (sd.isoformat(), h) in done:
                continue
            s["now"] = s.code.map(lambda c: p.get(c, (None, None))[0])
            bret = b_now / s.bench_0050.iloc[0] - 1
            s["excess"] = s.now / s.close - 1 - bret
            core = s[s.status.isin(["ADVANCE", "REJECT_RULE"])]
            ic, n_ic = spearman(core.routes, core.excess)
            aic, n_a = spearman(s[s.A == 1].a_score, s[s.A == 1].excess)
            g = s.groupby("status").excess
            adv, rej = g.mean().get("ADVANCE", float("nan")), g.mean().get("REJECT_RULE", float("nan"))
            new.append(dict(snapshot=sd.isoformat(), horizon=h, eval_date=ddate.isoformat(), days=age,
                            bench_ret=bret, n_eligible=int(core.excess.notna().sum()),
                            n_missing=int(core.excess.isna().sum()),
                            n_advance=int(s[s.status == "ADVANCE"].excess.notna().sum()),
                            mean_ex_advance=adv, mean_ex_reject=rej,
                            mean_ex_flag=g.mean().get("FLAG", float("nan")), spread=adv - rej,
                            ic_routes=ic, n_ic=n_ic, ic_a_score=aic, n_a=n_a))
    if new:
        log = pd.concat([log, pd.DataFrame(new)], ignore_index=True)
        os.makedirs(OUT, exist_ok=True)
        log.to_csv(log_path, index=False)
    lines = ["# Taiwan screen (rule v1.1) forward evaluation - monthly snapshots (approved 2026-11-21)",
             f"Last evaluation run: data date {ddate.isoformat()}",
             f"Snapshots stored: {len(glob.glob(f'{SNAP}/tw_rank_*.csv'))}"]
    if len(log):
        lines += ["", "| snapshot | horizon | days | n | ADVANCE excess | REJECT excess | spread | IC routes | IC A-score |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in log.itertuples():
            lines.append(f"| {r.snapshot} | {r.horizon} | {r.days} | {r.n_eligible} (missing {r.n_missing}) | "
                         f"{r.mean_ex_advance:.2%} | {r.mean_ex_reject:.2%} | {r.spread:+.2%} | {r.ic_routes:+.3f} | "
                         f"{r.ic_a_score:+.3f} (n {r.n_a}) |")
        m3 = log[log.horizon == "3m"]
        n = len(m3)
        if n >= 2:
            t = m3.ic_routes.mean() / (m3.ic_routes.std(ddof=1) / math.sqrt(n)) if m3.ic_routes.std(ddof=1) > 0 else float("nan")
        else:
            t = float("nan")
        verdict = "INSUFFICIENT DATA (need 12 three-month cross-sections)" if n < 12 else (
            "screen adds value" if (m3.spread.mean() > 0 and m3.ic_routes.mean() > 0 and t >= 2) else "no evidence")
        lines += ["", f"3-month cross-sections: {n}; mean spread {m3.spread.mean() if n else float('nan'):+.2%}; "
                      f"mean IC {m3.ic_routes.mean() if n else float('nan'):+.3f}; IC t {t:.2f}", f"Verdict: {verdict}"]
    else:
        lines += ["", "No evaluation yet (first 1-month read about 28 days after the first snapshot).",
                  "Verdict: INSUFFICIENT DATA"]
    with open(f"{OUT}/rank_ic_summary.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("snapshot", "both"):
        snapshot()
    if mode in ("evaluate", "both"):
        evaluate()
