"""Daily snapshot of Taiwan market files for the "Claude invest" Google Sheet (DATA-03, claude/09).

Google Sheets IMPORTDATA was refused by TWSE/TPEx on 2026-11-12 ("Could not fetch url").
This job downloads the same files from GitHub Actions and commits them to data/tw/,
so the sheet can read them from raw.githubusercontent.com instead.

DATA-05 fix (2026-11-15): every file's own data date is now parsed out of its contents and
written to data/tw/status.csv and data/tw/freshness.csv. The job exits non-zero when a source
failed or when the data is older than the expected trading day, so a stale feed can no longer
produce a green run. A failed source still keeps its previous file, but that file is marked
stale_kept=yes and never counted as fresh.

Holiday discrimination: when every daily source agrees on the same older date, the market was
probably closed (holiday), which is recorded as holiday_suspect and does not fail the run.
When the dates disagree, that is a real pipeline problem and the run fails.
"""
import csv
import datetime as dt
import io
import json
import pathlib
import re
import sys
import time

import requests

TPE = dt.timezone(dt.timedelta(hours=8))
OUT = pathlib.Path("data/tw")
OUT.mkdir(parents=True, exist_ok=True)
HDR = {"User-Agent": "Mozilla/5.0 (jc-investing-data research; contact via repo owner)"}


def tpex_close_urls():
    d = dt.datetime.now(TPE).date()
    for back in range(0, 7):
        day = d - dt.timedelta(days=back)
        if day.weekday() >= 5:
            continue
        roc = f"{day.year - 1911}/{day:%m/%d}"
        yield ("https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/"
               f"stk_quote_result.php?l=zh-tw&o=csv&d={roc}&s=0,asc,0")


SOURCES = {
    "bwibbu_all": ["https://www.twse.com.tw/exchangeReport/BWIBBU_ALL?response=open_data"],
    "stock_day_all": ["https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=open_data"],
    "tpex_pe": ["https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php?l=zh-tw&o=csv"],
    "tpex_close": list(tpex_close_urls()),
    "mops_rev_L": ["https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv"],
    "mops_rev_O": ["https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv"],
}
MIN_BYTES = 20_000  # every real file is far larger; small replies are error pages

# Daily sources must carry the latest trading day. The two MOPS files are monthly revenue.
DAILY = ("bwibbu_all", "stock_day_all", "tpex_pe", "tpex_close")
MONTHLY = ("mops_rev_L", "mops_rev_O")


def fetch(urls):
    err = "no url"
    for url in urls:
        for attempt in range(3):
            try:
                r = requests.get(url, headers=HDR, timeout=60)
                if r.status_code != 200:
                    err = f"HTTP {r.status_code} {url}"
                elif len(r.content) < MIN_BYTES:
                    err = f"too small ({len(r.content)} bytes) {url}"
                else:
                    return r.content, url, None
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e} {url}"
            time.sleep(10 * (attempt + 1))
    return None, None, err


def roc_to_date(s):
    """'1151113' or '115/11/13' -> date(2026, 11, 13). None if unparseable."""
    if not s:
        return None
    digits = re.sub(r"\D", "", str(s))
    if len(digits) != 7:
        return None
    try:
        return dt.date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7]))
    except ValueError:
        return None


def parse_data_date(name, body):
    """Read the data date out of the file itself. Returns (date|None, raw_string)."""
    try:
        if name in ("bwibbu_all", "stock_day_all"):
            # UTF-8, header 日期,..., first data row's first column is the ROC date
            text = body.decode("utf-8-sig", errors="replace")
            rows = list(csv.reader(io.StringIO(text)))
            for row in rows[1:]:
                if row and roc_to_date(row[0]):
                    return roc_to_date(row[0]), row[0].strip('"')
            return None, ""
        if name in ("tpex_close", "tpex_pe"):
            # Big5, line 2 looks like 資料日期:115/11/13
            text = body.decode("big5", errors="replace")
            m = re.search(r"(\d{3})/(\d{2})/(\d{2})", text[:4000])
            if m:
                raw = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
                return roc_to_date(raw), raw
            return None, ""
        if name in MONTHLY:
            # UTF-8, column 資料年月 like 11510 (ROC year 115, month 10)
            text = body.decode("utf-8-sig", errors="replace")
            rows = list(csv.reader(io.StringIO(text)))
            if len(rows) > 1 and len(rows[1]) > 1:
                raw = re.sub(r"\D", "", rows[1][1])
                if len(raw) == 5:
                    # represent the revenue month as the 1st of that month
                    return dt.date(int(raw[:3]) + 1911, int(raw[3:]), 1), raw
            return None, ""
    except Exception as e:  # noqa: BLE001
        print(f"  date-parse error {name}: {type(e).__name__}: {e}", flush=True)
    return None, ""


def expected_trading_day(now_tpe):
    """Most recent weekday whose close should already be published.

    The job is scheduled for 18:05 Taipei, after the 13:30 close and the exchanges'
    end-of-day files. Before 17:00 the same day's files may not exist yet, so the
    expectation steps back one weekday. Taiwan holidays are not in a calendar here;
    they are handled by the holiday_suspect rule in main().
    """
    d = now_tpe.date()
    if d.weekday() < 5 and now_tpe.hour < 17:
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def expected_revenue_month(today):
    """Taiwan monthly revenue for month M is filed by the 10th of M+1."""
    first_this = today.replace(day=1)
    prev = first_this - dt.timedelta(days=1)          # last day of previous month
    if today.day >= 11:
        return prev.replace(day=1)                     # previous month must be filed
    two_back = prev.replace(day=1) - dt.timedelta(days=1)
    return two_back.replace(day=1)                     # before the 11th, only M-2 is certain


def main():
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_tpe = dt.datetime.now(TPE)
    stamp = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    exp_day = expected_trading_day(now_tpe)
    exp_month = expected_revenue_month(now_tpe.date())

    rows, failed, stale, unknown = [], [], [], []
    daily_dates = {}

    for name, urls in SOURCES.items():
        body, used, err = fetch(urls)
        expected = exp_day if name in DAILY else exp_month
        if body is None:
            failed.append(name)
            kept = (OUT / f"{name}.csv").exists()
            rows.append({
                "source": name, "result": "FAIL", "checked_utc": stamp, "bytes": "",
                "url": "", "error": err.replace(",", ";"), "data_date": "",
                "expected": expected.isoformat(), "fresh": "no", "stale_kept": "yes" if kept else "no",
            })
            print(f"{name},FAIL,{err}", flush=True)
            continue

        (OUT / f"{name}.csv").write_bytes(body)
        d, raw = parse_data_date(name, body)
        if d is None:
            unknown.append(name)
            fresh = "unknown"
        elif d >= expected:
            fresh = "yes"
        else:
            fresh = "no"
            stale.append(name)
        if name in DAILY and d is not None:
            daily_dates[name] = d
        rows.append({
            "source": name, "result": "ok", "checked_utc": stamp, "bytes": str(len(body)),
            "url": used, "error": "", "data_date": d.isoformat() if d else f"unparsed:{raw}",
            "expected": expected.isoformat(), "fresh": fresh, "stale_kept": "no",
        })
        print(f"{name},ok,{len(body)} bytes,data_date={d},expected={expected},fresh={fresh}", flush=True)

    # Holiday discrimination: all four daily sources present and agreeing on one older date
    # means the market was shut, not that the pipeline broke.
    holiday_suspect = (
        len(daily_dates) == len(DAILY)
        and len(set(daily_dates.values())) == 1
        and next(iter(daily_dates.values())) < exp_day
    )
    stale_daily = [s for s in stale if s in DAILY]
    if holiday_suspect:
        for r in rows:
            if r["source"] in DAILY and r["fresh"] == "no":
                r["fresh"] = "holiday_suspect"
        stale = [s for s in stale if s not in DAILY]
        stale_daily = []

    fields = ["source", "result", "checked_utc", "bytes", "url", "error",
              "data_date", "expected", "fresh", "stale_kept"]
    with (OUT / "status.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    if failed:
        verdict = "FAIL"
        note = "fetch failed: " + "/".join(failed) + (" (old file kept, do not use)" if any(
            r["stale_kept"] == "yes" for r in rows) else "")
    elif stale or stale_daily:
        verdict = "STALE"
        note = "data older than expected: " + "/".join(sorted(set(stale) | set(stale_daily)))
    elif holiday_suspect:
        verdict = "HOLIDAY_SUSPECT"
        note = (f"all daily sources dated {next(iter(daily_dates.values()))}, expected {exp_day}"
                " — market probably closed")
    elif unknown:
        verdict = "DATE_UNKNOWN"
        note = "data date could not be parsed: " + "/".join(unknown)
    else:
        verdict = "OK"
        note = "all sources fresh"

    freshness = {
        "checked_utc": stamp,
        "checked_taipei": now_tpe.strftime("%Y-%m-%d %H:%M"),
        "verdict": verdict,
        "note": note,
        "expected_trading_day": exp_day.isoformat(),
        "expected_revenue_month": exp_month.strftime("%Y-%m"),
        "failed": failed,
        "stale": sorted(set(stale) | set(stale_daily)),
        "date_unknown": unknown,
    }
    (OUT / "freshness.json").write_text(json.dumps(freshness, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "freshness.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["checked_utc", "checked_taipei", "verdict", "note",
                    "expected_trading_day", "expected_revenue_month"])
        w.writerow([stamp, freshness["checked_taipei"], verdict, note,
                    exp_day.isoformat(), freshness["expected_revenue_month"]])

    print(f"VERDICT {verdict}: {note}", flush=True)
    # Loud failure: anything other than OK or a market holiday fails the workflow.
    return 0 if verdict in ("OK", "HOLIDAY_SUSPECT") else 1


if __name__ == "__main__":
    sys.exit(main())
