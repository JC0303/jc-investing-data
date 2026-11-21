from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import tw_a_track_check as atrack
from scripts import tw_rev_momentum_backtest as v2
from scripts import tw_reversal_v3_backtest as v3


def quotes(ticker):
    # Extracts from the real Yahoo replay. Tests only mask observations.
    path = Path(__file__).parent / "fixtures/tw_session_quotes.csv"
    q = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    q = q[q.ticker == ticker]
    adj = pd.DataFrame({ticker: q.adjusted, "0050.TW": q.benchmark})
    return adj, q.close.to_frame(ticker), q.volume.to_frame(ticker)


def test_unsettled_atrack_candidate_keeps_slot_and_blocks_duplicate():
    adj, _, _ = quotes("1560.TW")
    cal = adj.index
    d = cal.get_loc("2022-01-07")
    candidates = pd.DataFrame({"D": [cal[d], cal[d], cal[d+2]],
                               "ticker": ["1560.TW", "0050.TW", "1560.TW"], "r1": [.08, .07, .06]})
    adj.loc[cal[d+2], "1560.TW"] = np.nan
    rows = atrack.simulate(candidates, adj, adj["0050.TW"], cal, 1, False)
    assert rows.ticker.tolist() == ["1560.TW"]
    assert rows.iloc[0].status == "PERIOD_PRICE_MISSING"
    assert pd.isna(rows.iloc[0].excess)


def run_v2(monkeypatch, tmp_path, adj, close, volume):
    signal = dict(code="1101", mkt="sii", year=2024, month=5, yoy=.44, accel=.41)
    monkeypatch.setattr(v2, "load_revenue", lambda: (None, []))
    monkeypatch.setattr(v2, "signals", lambda _: pd.DataFrame([signal]))
    monkeypatch.setattr(v2, "load_prices", lambda _: ({"1101": "1101.TW"}, adj, close, volume))
    monkeypatch.setattr(v2, "OUT_DIR", str(tmp_path))
    v2.run()
    return pd.read_csv(tmp_path / "tw_rev_momentum_v2_trades.csv").iloc[0]


@pytest.mark.parametrize("day,status", [("2024-06-13", "PERIOD_PRICE_MISSING"),
                                        ("2024-06-26", "EXIT_PRICE_MISSING")])
def test_v2_keeps_missing_stop_or_exit(monkeypatch, tmp_path, day, status):
    adj, close, volume = quotes("1101.TW")
    adj.loc[day, "1101.TW"] = np.nan
    row = run_v2(monkeypatch, tmp_path, adj, close, volume)
    assert row.status == status
    assert pd.isna(row.excess)


def test_v3_keeps_unobservable_stop_check(monkeypatch, tmp_path):
    adj, close, volume = quotes("1560.TW")
    adj.loc["2022-01-11", "1560.TW"] = np.nan
    monkeypatch.setattr(v3, "load_prices", lambda: (1, adj, close, volume))
    monkeypatch.setattr(v3, "OUT_DIR", str(tmp_path))
    v3.run()
    rows = pd.read_csv(tmp_path / "tw_reversal_v3_trades.csv")
    row = rows[rows.signal == "2022-01-07"].iloc[0]
    assert row.status == "PERIOD_PRICE_MISSING"
    assert pd.isna(row.excess)


def test_v2_benchmark_uses_exact_entry_and_exit(monkeypatch, tmp_path):
    adj, close, volume = quotes("1101.TW")
    adj.loc["2024-05-06", "0050.TW"] = np.nan
    row = run_v2(monkeypatch, tmp_path, adj, close, volume)
    expected = adj.at[pd.Timestamp(row.exit), "0050.TW"] / adj.at[pd.Timestamp(row.entry), "0050.TW"] - 1
    assert row.bench == pytest.approx(expected)
