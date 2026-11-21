"""Pre-registered evidence screen. Input is attested, eligible original filings only."""
import csv
from datetime import date, datetime
from pathlib import Path

CUTOFF = date(2025, 11, 29)
TARGET = 387


def filing_time(value):
    ts = datetime.fromisoformat(value)
    if ts.utcoffset() is None or ts.utcoffset().total_seconds() != 8 * 3600:
        raise ValueError("need actual Asia/Taipei timestamp")
    if "T" not in value or len(value.split("+")[0]) < 19:
        raise ValueError("need date and time to seconds")
    if ts.date() >= CUTOFF:
        raise ValueError("outside development period")
    return ts


def first_execution(released, executable):
    """Preserve the close execution convention. Caller supplies actual tradable closes."""
    return next((ts for ts in sorted(executable)
                 if ts > released and ts.date() < CUTOFF), None)


def evidence_dates(rows):
    filings = {}
    for row in rows:
        key = (row["market"], row["company"], date.fromisoformat(row["period"]))
        stamp = filing_time(row["original_filed_at"])
        if not row["source"].strip() or key[2].day != 1 or key[2] >= stamp.date():
            raise ValueError("invalid evidence")
        if key in filings and filings[key] != stamp:
            raise ValueError("conflicting original filing")
        filings[key] = stamp
    return {ts.date() for ts in filings.values()}


if __name__ == "__main__":
    with Path("verified_eligible_originals.csv").open(encoding="utf-8") as stream:
        days = evidence_dates(csv.DictReader(stream))
    print(f"{len(days)} verified eligible announcement dates; target {TARGET}")
