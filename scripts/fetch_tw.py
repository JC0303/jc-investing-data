"""Daily snapshot of Taiwan market files for the "Claude invest" Google Sheet (DATA-03, claude/09).

Google Sheets IMPORTDATA was refused by TWSE/TPEx on 2026-11-12 ("Could not fetch url").
This job downloads the same files from GitHub Actions and commits them to data/tw/,
so the sheet can read them from raw.githubusercontent.com instead.
A failed source keeps its previous file; data/tw/status.csv records every attempt.
"""
import datetime as dt
import pathlib
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


def main():
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines, ok_count = [], 0
    for name, urls in SOURCES.items():
        body, used, err = fetch(urls)
        if body is not None:
            (OUT / f"{name}.csv").write_bytes(body)
            ok_count += 1
            lines.append(f"{name},ok,{now},{len(body)},{used},")
        else:
            lines.append(f"{name},FAIL,{now},,,{err.replace(',', ';')}")
        print(lines[-1], flush=True)
    (OUT / "status.csv").write_text("source,result,checked_utc,bytes,url,error\n" + "\n".join(lines) + "\n",
                                    encoding="utf-8")
    return 0 if ok_count else 1


if __name__ == "__main__":
    sys.exit(main())
