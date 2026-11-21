from datetime import date, timedelta

import pytest

from scripts.research_evidence import HOLDOUT, opportunities, required_dates
from scripts.research_partition import budget, decision, include_trade, registration, claim_run, docker_command


def test_required_dates_preserves_direction_and_uses_groups():
    assert required_dates(57, 0.767766352243219) == 387
    assert required_dates(57, -0.77) is None
    assert required_dates(57, 0) is None


def test_calendar_counts_releases_once_across_weekends():
    days = [date(2022, 4, d) for d in [8, 11, 12, 14, 15]]
    slots = opportunities(days)
    assert slots["v2"] == [date(2022, 4, 11)]
    assert slots["v3"] == [days[0], days[-1]]
    assert slots["A-track"] == days


def test_registry_rejects_unregistered_or_changed_code():
    digest = "f" * 64
    row = f"| next | 2026-11-22 | positive excess | p < .001 | REGISTERED | {digest} |"
    assert registration(row, "next", digest)
    for bad in [row + "\n" + row, row.replace("next", "other"),
                row.replace(digest, "0" * 64), row.replace("REGISTERED", "FAIL"),
                row.replace("positive excess", "")]:
        with pytest.raises(ValueError):
            registration(bad, "next", digest)


def test_multiple_looks_do_not_keep_the_first_threshold():
    table = "| new-1 | date | hypothesis | gates | FAIL | hash |\n| new-2 | date | hypothesis | gates | REGISTERED | hash |"
    p = {"p": .01, "gates_passed": True}
    assert decision(p, budget(table, "new-1")) == "PASS"
    assert decision(p, budget(table, "new-2")) == "FAIL"
    with pytest.raises(ValueError):
        budget(table.replace("new-1", "new-2"), "new-2")
    assert decision({"p": None, "gates_passed": False}, .01) == "INSUFFICIENT_DATA"


def test_purge_whole_window_even_if_stopped_early():
    dates = [HOLDOUT + timedelta(days=i) for i in range(-30, 21)]
    idx = {d: i for i, d in enumerate(dates)}
    def record(i):
        return {"signal": dates[i].isoformat(), "entry": dates[i+1].isoformat(),
                "exit": dates[i+2].isoformat()}
    assert include_trade(record(18), "v2", dates, idx, False)
    assert not include_trade(record(19), "v2", dates, idx, False)
    assert not include_trade(record(29), "v2", dates, idx, True)
    assert include_trade(record(30), "v2", dates, idx, True)


def test_final_claim_failure_stops_run(monkeypatch):
    def duplicate(*args, **kwargs):
        raise RuntimeError("reference already exists")
    monkeypatch.setattr("scripts.research_partition.urlopen", duplicate)
    with pytest.raises(RuntimeError):
        claim_run("refs/tags/test", "a" * 40, "test-token")


def test_development_container_only_mounts_filtered_bundle(tmp_path):
    cmd = docker_command(tmp_path)
    assert "--network=none" in cmd and "--read-only" in cmd
    assert cmd.count("--mount") == 1 and "readonly" in cmd[cmd.index("--mount")+1]
    assert "--env" not in cmd and "GITHUB_TOKEN" not in cmd
