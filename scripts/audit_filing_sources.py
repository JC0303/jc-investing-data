"""Inventory only historical MOPS company rows, without opening price or outcome data."""
import csv
import hashlib
from html import unescape
import re
import sys
import time
from urllib.request import Request, urlopen

SOURCE = "https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc}_{month}_0.html"
CLOCK = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3])[:：][0-5]\d|\d{1,2}\s*[時點]\s*\d{1,2}\s*分")
COMPANY_ROW = re.compile(r"<tr\b[^>]*>\s*<td\b[^>]*>\s*([1-9]\d{3})\s*</td>(.*?)</tr>", re.I | re.S)


def inspect_page(raw):
    page = raw.decode("cp950", errors="replace")
    rows = COMPANY_ROW.findall(page)
    if not rows or "當月營收" not in page or "去年當月營收" not in page:
        raise ValueError("unrecognized monthly revenue response")
    # The archive emits the industry tables' column labels in TH elements.
    headers = re.findall(r"<th\b[^>]*>(.*?)</th>", page, re.I | re.S)
    headers = [unescape(re.sub(r"<[^>]+>", "", h)).strip() for h in headers]
    timing = sorted({h for h in headers if re.search("申報日|申報時|公告日|公告時|上傳|發布日|發布時", h)})
    # Keep issuer-level clock-like text (including notes) for separate review.
    clocks = sorted({code for code, body in rows if CLOCK.search(unescape(body))})
    return len(set(code for code, _ in rows)), ";".join(timing), ";".join(clocks)


def main():
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["period", "market", "issuer_count", "timing_columns", "issuer_clock_candidates",
                     "body_sha256", "source"])
    for year in range(2022, 2026):
        for month in range(1, 13 if year < 2025 else 11):
            for market in ["sii", "otc"]:
                url = SOURCE.format(market=market, roc=year-1911, month=month)
                for attempt in range(3):
                    try:
                        with urlopen(Request(url, headers={"User-Agent": "Historical revenue research"}), timeout=20) as response:
                            raw = response.read()
                        counts = inspect_page(raw)
                        break
                    except (OSError, ValueError):
                        if attempt == 2:
                            raise
                        time.sleep(2 ** attempt)
                writer.writerow([f"{year}-{month:02}", market, *counts, hashlib.sha256(raw).hexdigest(), url])
                sys.stdout.flush()
                time.sleep(.5)


if __name__ == "__main__":
    main()
