"""Size the existing signal-day experiment under constant cluster-score variance."""
import csv
import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
START = date(2022, 1, 1)
END = date(2026, 11, 20)
SIGNAL_END = date(2026, 10, 31)
HOLDOUT = START + timedelta(days=((END - START).days + 1) * 4 // 5)
HORIZON = {"v2": 10, "A-track": 20, "v3": 5}


def required_dates(groups, t, target=2):
    if groups < 2 or not math.isfinite(t) or target <= 0:
        raise ValueError("invalid clustered estimate")
    return max(2, math.ceil(groups * (target / t) ** 2)) if t > 0 else None


def sessions():
    with (RESULTS / "research_sessions.csv").open() as f:
        days = [date.fromisoformat(r["session"]) for r in csv.DictReader(f)]
    if sorted(set(days)) != days or days[-1] != END:
        raise ValueError("invalid frozen benchmark calendar")
    digest = hashlib.sha256(("\n".join(map(str, days)) + "\n").encode()).hexdigest()
    if digest != "cc4f51ad8568ea1f424f34430e7e58a50b4f82ef0009b83c2927c088ef07a306":
        raise ValueError("frozen 0050 sessions changed")
    return days


def opportunities(days):
    weeks = {}
    months = {}
    for d in days:
        weeks[d.isocalendar()[:2]] = d
        if d.day >= 10:
            months.setdefault((d.year, d.month), d)
    return {
        "v2": [d for d in months.values() if date(2022, 2, 1) <= d <= END],
        "A-track": [d for d in days if START <= d <= SIGNAL_END],
        "v3": [d for d in weeks.values() if START <= d <= SIGNAL_END],
    }


def census():
    days = sessions()
    estimates = json.loads((RESULTS / "clustered_performance.json").read_text(encoding="utf-8"))
    for name, dates in opportunities(days).items():
        fit = estimates[name]["tests"]["all"]
        mature = [d for d in dates if days.index(d) + 1 + HORIZON[name] < len(days)]
        print(name, fit["groups"], fit["t"], required_dates(fit["groups"], fit["t"]),
              required_dates(fit["groups"], abs(fit["t"])), len(dates), len(mature))
    print("HOLDOUT", HOLDOUT, END)


if __name__ == "__main__":
    census()
