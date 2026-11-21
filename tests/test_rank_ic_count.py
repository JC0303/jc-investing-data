import datetime as dt

import pandas as pd

from scripts import rank_snapshot as rank


def test_missing_ic_does_not_complete_twelve_monthly_observations(tmp_path, monkeypatch):
    rows = [dict(snapshot=f"2025-{i:02}-01", horizon="3m", days=90, n_eligible=20,
                 n_missing=0, mean_ex_advance=.03, mean_ex_reject=.01, spread=.02,
                 ic_routes=i / 20 if i < 12 else float("nan"), ic_a_score=.1, n_a=10)
            for i in range(1, 13)]
    pd.DataFrame(rows).to_csv(tmp_path / "rank_ic_log.csv", index=False)
    monkeypatch.setattr(rank, "OUT", str(tmp_path))
    monkeypatch.setattr(rank, "SNAP", str(tmp_path))
    monkeypatch.setattr(rank, "prices", lambda: ({}, dt.date(2026, 11, 20)))
    rank.evaluate()
    report = (tmp_path / "rank_ic_summary.md").read_text()
    assert "valid IC: 11" in report
    assert "IC t 6.00" in report
    assert "Verdict: INSUFFICIENT DATA" in report
