"""Offline trade-weighted inference. Run with Python, numpy, pandas and scipy."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student

ROOT = Path(__file__).resolve().parents[1]
FILES = {"v2": "tw_rev_momentum_v2", "A-track": "tw_a_track", "v3": "tw_reversal_v3"}
COMMISSION = .001425
SLIPPAGE = .001


def clustered(returns, groups):
    x = pd.Series(np.asarray(returns, dtype=float))
    dates = np.asarray(groups)
    if not np.isfinite(x).all() or pd.isna(dates).any() or len(x) != len(dates):
        raise ValueError("Incomplete settled observation")
    mean = float(x.mean()) if len(x) else None
    scores = (x - mean).groupby(dates).sum() if len(x) else x
    g = len(scores)
    result = dict(n=len(x), groups=g, mean=mean, se=None, t=None, ci95=None, p=None)
    if g < 2 or x.nunique() < 2:
        return result
    se = float(np.sqrt(g / (g - 1) * scores.pow(2).sum()) / len(x))
    if se == 0:
        return result
    t = mean / se
    half = student.ppf(.975, g-1) * se
    return dict(result, se=se, t=t, ci95=[mean-half, mean+half], p=2*student.sf(abs(t), g-1))


def net_return(gross, tax, slip):
    # Both legs have commission and slippage. Sell-side tax uses sale proceeds.
    return (1 + gross) * (1 - slip) * (1 - COMMISSION - tax) / ((1 + slip) * (1 + COMMISSION)) - 1


def decide(t, mean, late_mean, late_t, net_edge, beat_passive):
    gates = [None if t is None else t > 2,
             None if late_t is None or mean is None or late_mean is None
             else mean * late_mean > 0 and late_t > 1.5,
             None if net_edge is None else net_edge > 0, beat_passive]
    if False in gates:
        return "不通過"
    return "樣本不足" if None in gates else "通過"


def analyze(name, frame, quotes):
    d = frame.loc[frame.status == "SETTLED"].copy()
    if d.empty:
        return {"verdict": "樣本不足"}
    bench = d.bench_net + .00385 if name == "A-track" else d.bench
    stock = d.ret_net + .00585
    if not np.isfinite(stock).all() or not np.isfinite(bench).all():
        raise ValueError("Missing settled return")
    day = pd.to_datetime(d.signal, errors="raise")
    midpoint = day.min() + (day.max()-day.min()) / 2
    samples = {"all": d, "early": d[day <= midpoint], "late": d[day > midpoint]}
    tests = {key: clustered(sample.excess, sample.signal) for key, sample in samples.items()}
    costs = {}
    for key, slip in [("fees_tax", 0.), ("fees_tax_slippage", SLIPPAGE)]:
        s, b = net_return(stock, .003, slip), net_return(bench, .001, slip)
        costs[key] = dict(stock=s.mean(), etf=b.mean(), edge=(s-b).mean())
    costs["gross"] = dict(stock=stock.mean(), etf=bench.mean(), edge=(stock-bench).mean())
    first, last = d.entry.min(), d.exit.max()
    hold = None
    if first in quotes.index and last in quotes.index:
        hold = net_return(quotes.at[last] / quotes.at[first] - 1, .001, SLIPPAGE)
    return dict(midpoint=midpoint.isoformat(), tests=tests, costs=costs, start=first, end=last,
                buy_hold_net=hold, portfolio_beats_buy_hold=None,
                verdict=decide(tests["all"]["t"], tests["all"]["mean"], tests["late"]["mean"],
                               tests["late"]["t"], costs["fees_tax_slippage"]["edge"], None))


if __name__ == "__main__":
    folder = ROOT / "results"
    quotes = pd.read_csv(folder / "clustered_0050_endpoints.csv").set_index("date").adjusted_close
    result = {name: analyze(name, pd.read_csv(folder / f"{stem}_trades.csv"), quotes)
              for name, stem in FILES.items()}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
