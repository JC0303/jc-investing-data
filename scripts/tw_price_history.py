"""Build a real price history for the holdings, so no rule rests on a guess.

The 0050 drawdown ladder was measured against a one-year high that had been
derived in conversation, not looked up. A number that decides where money is
spent should come from the exchange.

Fetches TWSE STOCK_DAY one month at a time for each ticker in
data/positions.csv, appends to data/tw/history_<ticker>.csv (idempotent: a
session already stored is never rewritten), and writes data/tw/highs.json with
the 52-week high and low for each ticker and the date each was set.

Run it monthly; it only needs the current month to stay current, and will
back-fill up to BACKFILL_MONTHS the first time.
"""
import csv, datetime as dt, json, pathlib, sys, time
import requests

TPE = dt.timezone(dt.timedelta(hours=8))
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'tw'
HDR = {"User-Agent": "Mozilla/5.0 (jc-investing-data research; contact via repo owner)"}
URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={ym}01&stockNo={code}"
BACKFILL_MONTHS = 14
PAUSE_SECONDS = 4          # TWSE throttles; stay well inside what it tolerates


def roc_to_iso(value):
    year, month, day = value.strip().split('/')
    return f'{int(year) + 1911:04d}-{int(month):02d}-{int(day):02d}'


def fetch_month(code, year, month):
    url = URL.format(ym=f'{year:04d}{month:02d}', code=code)
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HDR, timeout=60)
            if response.status_code == 200:
                payload = response.json()
                if payload.get('stat') == 'OK':
                    return payload, None
                return None, f"stat={payload.get('stat')}"
            error = f'HTTP {response.status_code}'
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        time.sleep(PAUSE_SECONDS * (attempt + 1))
    return None, error


def read_existing(path):
    if not path.exists():
        return {}
    with path.open(encoding='utf-8') as handle:
        return {row['date']: row for row in csv.DictReader(handle)}


def main():
    with (ROOT / 'data' / 'positions.csv').open(encoding='utf-8') as handle:
        tickers = sorted({r['ticker'] for r in csv.DictReader(handle) if r['market'] == 'TW'})
    today = dt.datetime.now(TPE).date()
    months, cursor = [], today.replace(day=1)
    for _ in range(BACKFILL_MONTHS):
        months.append((cursor.year, cursor.month))
        cursor = (cursor - dt.timedelta(days=1)).replace(day=1)

    highs, problems = {}, []
    for code in tickers:
        path = OUT / f'history_{code}.csv'
        rows = read_existing(path)
        for year, month in months:
            # A month already complete is never re-fetched or rewritten.
            if any(d.startswith(f'{year:04d}-{month:02d}') for d in rows) and \
               (year, month) != (today.year, today.month):
                continue
            payload, error = fetch_month(code, year, month)
            time.sleep(PAUSE_SECONDS)
            if not payload:
                problems.append(dict(ticker=code, month=f'{year:04d}-{month:02d}', error=error))
                continue
            for entry in payload.get('data') or []:
                try:
                    day = roc_to_iso(entry[0])
                    close = entry[6].replace(',', '')
                    high = entry[4].replace(',', '')
                    low = entry[5].replace(',', '')
                    if close in ('--', '---', ''):
                        continue
                    rows[day] = dict(date=day, close=close, high=high, low=low)
                except Exception:
                    problems.append(dict(ticker=code, month=f'{year:04d}-{month:02d}',
                                         error='unparsable row'))
        if not rows:
            problems.append(dict(ticker=code, month='-', error='no history at all'))
            continue
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['date', 'close', 'high', 'low'])
            writer.writeheader()
            for day in sorted(rows):
                writer.writerow(rows[day])

        cutoff = (today - dt.timedelta(days=365)).isoformat()
        window = [r for day, r in sorted(rows.items()) if day >= cutoff]
        if not window:
            problems.append(dict(ticker=code, month='-', error='no sessions in the last year'))
            continue
        top = max(window, key=lambda r: float(r['high']))
        bottom = min(window, key=lambda r: float(r['low']))
        highs[code] = dict(
            one_year_high=top['high'], one_year_high_date=top['date'],
            one_year_low=bottom['low'], one_year_low_date=bottom['date'],
            sessions_in_window=len(window), window_start=window[0]['date'],
            window_end=window[-1]['date'], source='TWSE STOCK_DAY')

    report = dict(generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                  as_of=today.isoformat(), highs=highs, problems=problems)
    (OUT / 'highs.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if not highs else 0


if __name__ == '__main__':
    sys.exit(main())
