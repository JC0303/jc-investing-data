"""Fetch latest-quarter revenue and net income for all SEC filers (XBRL frames API).

Output: data/sec_revenue.csv  (one row per ticker)
Requires env SEC_UA = "Name email" (SEC fair-access policy).
"""
import csv, datetime as dt, json, os, sys, time, urllib.request, urllib.error

UA = os.environ.get("SEC_UA", "").strip()
if "@" not in UA:
    sys.exit("SEC_UA secret missing (format: 'Name email')")

REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
       "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]
NI = "NetIncomeLoss"


def get(url):
    for attempt in range(1, 4):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(0.2)  # stay far below SEC's 10 requests/second
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f"HTTP {e.code} {url} (attempt {attempt})", file=sys.stderr)
            time.sleep(2 * attempt)
    raise SystemExit(f"failed: {url}")


def frame(concept, period):
    j = get(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/{period}.json")
    return {d["cik"]: d["val"] for d in (j or {}).get("data", [])}


def candidate_quarters(today):
    y, q = today.year, (today.month - 1) // 3  # previous quarter
    out = []
    for _ in range(4):
        if q <= 0:
            y, q = y - 1, 4
        if q != 4:  # Q4 is rarely filed as a standalone quarter
            out.append((y, q))
        q -= 1
    return out


def main():
    today = dt.datetime.utcnow()
    tick = get("https://www.sec.gov/files/company_tickers.json")
    chosen = None
    for y, q in candidate_quarters(today):
        p, pp = f"CY{y}Q{q}", f"CY{y-1}Q{q}"
        cur, prev = {}, {}
        for con in REV:
            a, b = frame(con, p), frame(con, pp)
            for cik, v in a.items():
                if cik not in cur and cik in b:
                    cur[cik] = (v, con)
                    prev[cik] = b[cik]
        base = len(frame(REV[0], pp)) or 1
        print(f"{p}: {len(cur)} companies with current+prior revenue (baseline {base})")
        if len(cur) >= 0.6 * base:
            chosen = p
            ni_cur, ni_prev = frame(NI, p), frame(NI, pp)
            break
    if not chosen:
        raise SystemExit("no sufficiently complete quarter")

    stamp = today.strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    for e in tick.values():
        cik, t = e["cik_str"], e["ticker"].upper()
        if cik not in cur:
            continue
        v, con = cur[cik]
        pv = prev[cik]
        yoy = round((v / pv - 1) * 100, 2) if pv else ""
        rows.append([t, cik, e["title"], chosen, v, pv, yoy, con,
                     ni_cur.get(cik, ""), ni_prev.get(cik, ""), stamp])
    rows.sort()
    os.makedirs("data", exist_ok=True)
    with open("data/sec_revenue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "cik", "name", "quarter", "revenue", "revenue_prior_year",
                    "revenue_yoy_pct", "revenue_concept", "net_income", "net_income_prior_year", "updated"])
        w.writerows(rows)
    print(f"wrote {len(rows)} rows for {chosen}")


if __name__ == "__main__":
    main()
