"""Daily position check. Deterministic, free to run, places no orders.

Reads the holdings in data/positions.csv, the approved rules in
claude/rules.json and the TWSE daily close already fetched into
data/tw/stock_day_all.csv, then writes two files:

  results/daily_check.json  - machine readable, for the reporting agent
  results/daily_check.md    - the same thing in plain Chinese, for a human

It decides nothing. It reports which rules JC has already approved are at or
near their trigger, so the decision reaches him instead of waiting to be asked
for. Anything it cannot price is reported as unchecked, never guessed.
"""
import csv, datetime as dt, json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEAR = Decimal('0.03')          # within 3% of a line is worth telling him about


def roc_to_iso(value):
    digits = ''.join(ch for ch in value if ch.isdigit())
    return f'{int(digits[:-4]) + 1911:04d}-{digits[-4:-2]}-{digits[-2:]}'


def tw_closes():
    path = ROOT / 'data' / 'tw' / 'stock_day_all.csv'
    if not path.exists():
        return {}, None
    closes, day = {}, None
    with path.open(encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get('證券代號') or '').strip()
            close = (row.get('收盤價') or '').strip().replace(',', '')
            if not ticker or not close or close in ('--', '---'):
                continue
            try:
                closes[ticker] = Decimal(close)
            except Exception:
                continue
            day = day or roc_to_iso(row.get('日期', ''))
    return closes, day


def main():
    rules = json.loads((ROOT / 'claude' / 'rules.json').read_text(encoding='utf-8'))
    with (ROOT / 'data' / 'positions.csv').open(encoding='utf-8') as handle:
        positions = list(csv.DictReader(handle))
    closes, price_date = tw_closes()

    alerts, unchecked, watch = [], [], []

    review = rules.get('review_line', {})
    for row in positions:
        ticker = row['ticker']
        if ticker not in review.get('applies_to', []):
            continue
        if ticker not in closes:
            unchecked.append(dict(ticker=ticker, reason='沒有今天的收盤價'))
            continue
        cost = Decimal(row['avg_cost'])
        line = (cost * (1 - Decimal(str(review['drop_pct'])))).quantize(Decimal('0.01'))
        price, gap = closes[ticker], (closes[ticker] - line) / line
        entry = dict(rule='review_line', ticker=ticker, instrument=row['instrument'],
                     price=str(price), line=str(line), avg_cost=str(cost),
                     gap_pct=str((gap * 100).quantize(Decimal('0.01'))), price_date=price_date)
        if price <= line:
            alerts.append(entry)
        elif gap <= NEAR:
            watch.append(entry)

    ladder = rules.get('zero_fifty_ladder', {})
    ticker = ladder.get('ticker')
    if ticker and ticker in closes and ladder.get('one_year_high_twd'):
        high = Decimal(str(ladder['one_year_high_twd']))
        as_of = dt.date.fromisoformat(ladder['one_year_high_as_of'])
        stale = (dt.date.today() - as_of).days > ladder.get('one_year_high_stale_after_days', 30)
        price = closes[ticker]
        drawdown = (high - price) / high
        for step in ladder.get('steps_pct_below_one_year_high', []):
            level = (high * (1 - Decimal(str(step)))).quantize(Decimal('0.01'))
            gap = (price - level) / level
            entry = dict(rule='zero_fifty_ladder', ticker=ticker, step_pct=str(step),
                         price=str(price), level=str(level),
                         drawdown_pct=str((drawdown * 100).quantize(Decimal('0.01'))),
                         one_year_high=str(high), high_as_of=str(as_of),
                         high_is_stale=stale, approved_for_execution=
                         ladder.get('approved_for_execution', False), price_date=price_date)
            if price <= level:
                alerts.append(entry)
            elif gap <= NEAR:
                watch.append(entry)

    for row in positions:
        if row['market'] != 'TW' and row['ticker'] not in closes:
            unchecked.append(dict(ticker=row['ticker'], reason='這個檢查只用免費的台股收盤資料，沒有美股價格'))

    report = dict(generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                  price_date=price_date, alerts=alerts, watch=watch, unchecked=unchecked,
                  positions_as_of=positions[0]['as_of'] if positions else None,
                  something_to_report=bool(alerts or watch))

    out = ROOT / 'results'
    out.mkdir(exist_ok=True)
    (out / 'daily_check.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')

    lines = [f"# 每日部位檢查（{price_date or '無價格'}）", '']
    if not report['something_to_report']:
        lines.append('沒有任何規則被觸發，也沒有接近觸發的。')
    for entry in alerts:
        if entry['rule'] == 'review_line':
            lines.append(f"**觸發｜{entry['ticker']} {entry['instrument']}**：收盤 {entry['price']}，"
                         f"已跌破審查線 {entry['line']}（成本 {entry['avg_cost']}）。觸發的是一次重新檢視，不是賣出指示。")
        else:
            note = '（這一階你還沒核准執行）' if not entry['approved_for_execution'] else ''
            lines.append(f"**觸發｜0050 第 {entry['step_pct']} 階**：收盤 {entry['price']}，"
                         f"已到 {entry['level']}，距一年高點 {entry['drawdown_pct']}%。{note}")
    for entry in watch:
        if entry['rule'] == 'review_line':
            lines.append(f"接近｜{entry['ticker']} {entry['instrument']}：收盤 {entry['price']}，"
                         f"距審查線 {entry['line']} 還有 {entry['gap_pct']}%。")
        else:
            lines.append(f"接近｜0050 第 {entry['step_pct']} 階：收盤 {entry['price']}，距 {entry['level']} 還有一小段。")
    if any(e.get('high_is_stale') for e in alerts + watch):
        lines += ['', f"注意：0050 的一年高點是 {ladder.get('one_year_high_as_of')} 推算的，已經過期，上面的階梯價位需要重算。"]
    if unchecked:
        lines += ['', '沒有檢查到的部位：'] + [f"- {u['ticker']}：{u['reason']}" for u in unchecked]
    (out / 'daily_check.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
