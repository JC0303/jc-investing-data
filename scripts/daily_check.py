"""Daily position check. Deterministic, free to run, places no orders.

Reads the holdings in data/positions.csv, the approved rules in
claude/rules.json, the measured highs in data/tw/highs.json and the TWSE daily
close already fetched into data/tw/stock_day_all.csv, then writes:

  results/daily_check.json  - machine readable, for the reporting agent
  results/daily_check.md    - the same thing in plain Chinese, for a human

Every approved rule is accounted for by name on every run: TRIGGERED, NEAR,
CLEAR or NO_DATA. A rule that could not be evaluated is never silently
omitted, and "nothing triggered" is only ever said when every rule was
actually evaluated. A data outage is itself something to report, because a
quiet failure is indistinguishable from a quiet market.

It decides nothing and places nothing.
"""
import csv, datetime as dt, json, os
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPE = dt.timezone(dt.timedelta(hours=8))
NEAR = Decimal('0.03')      # within 3% of a line is worth telling him about
STALE_DAYS = 4              # a close older than this means the feed is behind


def roc_to_iso(value):
    digits = ''.join(ch for ch in value if ch.isdigit())
    if len(digits) < 7:
        raise ValueError('unrecognised ROC date: ' + value)
    return f'{int(digits[:-4]) + 1911:04d}-{digits[-4:-2]}-{digits[-2:]}'


def upstream_problem():
    """The fetch run that triggered this check, when it did not succeed."""
    conclusion = os.environ.get('UPSTREAM_FETCH_CONCLUSION', '').strip()
    if conclusion and conclusion != 'success':
        return f'這次是抓價工作「{conclusion}」之後觸發的，資料可能是舊的或不完整'
    return None


def feed_expectation():
    """What the fetch job itself says the latest session should be.

    Reusing its record rather than recomputing the calendar here: it already
    distinguishes a market holiday (all four daily sources agreeing on one
    older date) from a pipeline failure, and a second implementation of that
    rule would drift from the first.
    """
    path = ROOT / 'data' / 'tw' / 'freshness.json'
    if not path.exists():
        return None, None, '找不到抓價的新鮮度紀錄，無法確認資料是不是最新的'
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None, None, '抓價的新鮮度紀錄讀不開'
    if not isinstance(record, dict):
        return None, None, '抓價的新鮮度紀錄格式不對'
    expected = record.get('expected_trading_day')
    verdict = record.get('verdict')
    checked = record.get('checked_taipei')
    # A record that exists but cannot be read is not a pass. Each missing or
    # unusable field below means "cannot confirm the session", which is treated
    # exactly like having no record at all.
    if not expected:
        return None, verdict, '抓價紀錄裡沒有預期交易日，無法確認資料是不是最新的'
    if not verdict:
        return expected, None, '抓價紀錄裡沒有狀態欄位，無法確認抓價是否正常'
    if not checked:
        return expected, verdict, '抓價紀錄裡沒有執行時間，無法確認抓價工作有沒有跑'
    try:
        stamp = dt.datetime.strptime(str(checked), '%Y-%m-%d %H:%M').replace(tzinfo=TPE)
    except (ValueError, TypeError):
        return expected, verdict, f'抓價紀錄的執行時間讀不懂（{checked}）'
    age = (dt.datetime.now(TPE) - stamp).total_seconds() / 3600
    if age < -1:
        return expected, verdict, f'抓價紀錄的執行時間在未來（{checked}），紀錄不可信'
    if age > 30:
        return expected, verdict, f'抓價工作已經 {age:.0f} 小時沒有執行（最後一次 {checked}）'
    if verdict != 'OK':
        note = record.get('note') or ''
        if verdict == 'HOLIDAY_SUSPECT':
            return expected, verdict, ('四個資料源都停在同一個較早的日期。可能是台股休市，'
                                       f'也可能是資料源同時延遲，無法從這裡分辨（{note}）')
        return expected, verdict, f'抓價回報的狀態是 {verdict}（{note}）'
    return expected, verdict, None


def tw_closes():
    """Return (closes, price_date, problem). problem is None when the feed is sound."""
    expected, verdict, feed_issue = feed_expectation()
    feed_issue = upstream_problem() or feed_issue
    path = ROOT / 'data' / 'tw' / 'stock_day_all.csv'
    if not path.exists():
        return {}, None, '台股收盤檔不存在，這次完全沒有行情可用'
    closes, day, conflicts = {}, None, set()
    with path.open(encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get('證券代號') or '').strip()
            close = (row.get('收盤價') or '').strip().replace(',', '')
            if not ticker or not close or close in ('--', '---'):
                continue
            try:
                value = Decimal(close)
            except Exception:
                continue
            if value <= 0:
                continue
            # Two different closes for one ticker is a disputed price, not a
            # price. Record the conflict and refuse to use either.
            if ticker in closes and closes[ticker] != value:
                conflicts.add(ticker)
            closes[ticker] = value
            if day is None:
                try:
                    day = roc_to_iso(row.get('日期', ''))
                except ValueError:
                    pass
    for ticker in conflicts:
        closes.pop(ticker, None)
    if conflicts:
        return closes, day, '收盤檔裡有同一檔股票的多個不同價格：' + '、'.join(sorted(conflicts))
    if not closes:
        return {}, day, '台股收盤檔存在但沒有任何可用的收盤價'
    if day is None:
        return closes, None, '台股收盤檔沒有可辨識的日期'
    if feed_issue:
        # Drop the prices: a rule must never be judged against a session that
        # is not the one it is supposed to be judging.
        return {}, day, feed_issue
    if expected and day != expected:
        return {}, day, f'台股收盤資料日期是 {day}，但預期交易日是 {expected}'
    age = (dt.date.today() - dt.date.fromisoformat(day)).days
    if age > STALE_DAYS:
        return {}, day, f'台股收盤資料停在 {day}，已經 {age} 天沒更新'
    return closes, day, None


def main():
    rules = json.loads((ROOT / 'claude' / 'rules.json').read_text(encoding='utf-8'))
    with (ROOT / 'data' / 'positions.csv').open(encoding='utf-8') as handle:
        positions = list(csv.DictReader(handle))
    closes, price_date, feed_problem = tw_closes()

    checks = []       # one entry per approved rule instance, always
    rule_problems = []
    # The rules this script knows how to evaluate. A key that is absent, empty
    # or the wrong shape means the rulebook changed under us: that is a data
    # problem, never an empty all-clear.
    for key in ('review_line', 'zero_fifty_ladder'):
        block = rules.get(key)
        if not isinstance(block, dict) or not block:
            rule_problems.append(f'規則檔裡找不到或讀不懂「{key}」這條規則')
    for key in rules:
        if key.startswith('_') or key in ('version', 'updated', 'review_line',
                                          'zero_fifty_ladder', 'monthly_dca', 'never'):
            continue
        rule_problems.append(f'規則檔裡有這個程式不認得的規則「{key}」，它不會被檢查')

    review = rules.get('review_line', {})
    drop = Decimal(str(review.get('drop_pct', 0)))
    for ticker in review.get('applies_to', []):
        row = next((r for r in positions if r['ticker'] == ticker), None)
        base = dict(rule='review_line', ticker=ticker,
                    instrument=row['instrument'] if row else None, price_date=price_date)
        if row is None:
            checks.append(dict(base, status='NO_DATA', reason='持股清單裡沒有這一檔'))
            continue
        if ticker not in closes:
            checks.append(dict(base, status='NO_DATA', reason='沒有這一檔的收盤價'))
            continue
        cost = Decimal(row['avg_cost'])
        line = (cost * (1 - drop)).quantize(Decimal('0.01'))
        price = closes[ticker]
        gap = (price - line) / line
        entry = dict(base, price=str(price), line=str(line), avg_cost=str(cost),
                     gap_pct=str((gap * 100).quantize(Decimal('0.01'))))
        entry['status'] = 'TRIGGERED' if price <= line else 'NEAR' if gap <= NEAR else 'CLEAR'
        checks.append(entry)

    ladder = rules.get('zero_fifty_ladder', {})
    ticker = ladder.get('ticker')
    measured = {}
    highs_path = ROOT / (ladder.get('one_year_high_from') or 'data/tw/highs.json')
    if highs_path.exists():
        try:
            measured = json.loads(highs_path.read_text(encoding='utf-8'))
        except Exception:
            measured = {}
    entry_high = (measured.get('highs') or {}).get(ticker or '', {})
    for step in ladder.get('steps_pct_below_one_year_high', []):
        base = dict(rule='zero_fifty_ladder', ticker=ticker, step_pct=str(step),
                    approved_for_execution=ladder.get('approved_for_execution', False),
                    price_date=price_date)
        if ticker not in closes:
            checks.append(dict(base, status='NO_DATA', reason='沒有 0050 的收盤價'))
            continue
        if not entry_high:
            # Never fall back to an estimated high: this rule decides where
            # money would go, so without a measured high it is unchecked.
            checks.append(dict(base, status='NO_DATA', reason='還沒有實際量到的一年高點'))
            continue
        high = Decimal(str(entry_high['one_year_high']))
        as_of = measured.get('as_of')
        stale_high = as_of is None or (dt.date.today() - dt.date.fromisoformat(as_of)).days > 45
        price = closes[ticker]
        level = (high * (1 - Decimal(str(step)))).quantize(Decimal('0.01'))
        gap = (price - level) / level
        entry = dict(base, price=str(price), level=str(level), one_year_high=str(high),
                     high_date=entry_high.get('one_year_high_date'), high_as_of=as_of,
                     high_source=entry_high.get('source'), high_is_stale=stale_high,
                     drawdown_pct=str(((high - price) / high * 100).quantize(Decimal('0.01'))))
        if stale_high:
            # A high past its own staleness limit moves the ladder levels, and it
            # moves them in the direction that suppresses a trigger. Refuse it.
            entry['status'] = 'NO_DATA'
            entry['reason'] = f'一年高點資料已過期（最後更新 {as_of}），階梯價位不可信'
        else:
            entry['status'] = ('TRIGGERED' if price <= level
                               else 'NEAR' if gap <= NEAR else 'CLEAR')
        checks.append(entry)

    unpriced = [dict(ticker=r['ticker'], reason='這個檢查只用免費的台股收盤資料，沒有美股價格')
                for r in positions if r['market'] != 'TW' and r['ticker'] not in closes]

    triggered = [c for c in checks if c['status'] == 'TRIGGERED']
    near = [c for c in checks if c['status'] == 'NEAR']
    no_data = [c for c in checks if c['status'] == 'NO_DATA']
    if not checks:
        rule_problems.append('這次沒有任何規則被檢查，等於完全沒有判斷')
    data_problem = bool(feed_problem or no_data or rule_problems)

    report = dict(
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        price_date=price_date, feed_problem=feed_problem, rule_problems=rule_problems,
        data_problem=data_problem,
        rules_total=len(checks), rules_evaluated=len(checks) - len(no_data),
        checks=checks, triggered=triggered, near=near, no_data=no_data,
        unpriced_positions=unpriced,
        positions_as_of=positions[0]['as_of'] if positions else None,
        # A data outage is reportable in its own right: silence must not be
        # the same thing as a clear result.
        something_to_report=bool(triggered or near or data_problem))

    out = ROOT / 'results'
    out.mkdir(exist_ok=True)
    (out / 'daily_check.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')

    lines = [f"# 每日部位檢查（{price_date or '無價格日期'}）", '']
    if feed_problem:
        lines += [f'**資料異常：{feed_problem}。**', '']
    for entry in triggered:
        if entry['rule'] == 'review_line':
            lines.append(f"**觸發｜{entry['ticker']} {entry['instrument']}**：收盤 {entry['price']}，"
                         f"已跌破審查線 {entry['line']}（成本 {entry['avg_cost']}）。"
                         f"觸發的是一次重新檢視，不是賣出指示。")
        else:
            note = '（這一階你還沒核准執行）' if not entry['approved_for_execution'] else ''
            lines.append(f"**觸發｜0050 第 {entry['step_pct']} 階**：收盤 {entry['price']}，"
                         f"已到 {entry['level']}，距一年高點 {entry['drawdown_pct']}%。{note}")
    for entry in near:
        if entry['rule'] == 'review_line':
            lines.append(f"接近｜{entry['ticker']} {entry['instrument']}：收盤 {entry['price']}，"
                         f"距審查線 {entry['line']} 還有 {entry['gap_pct']}%。")
        else:
            lines.append(f"接近｜0050 第 {entry['step_pct']} 階：收盤 {entry['price']}，"
                         f"距 {entry['level']} 還有一小段，目前距一年高點 {entry['drawdown_pct']}%。")
    if no_data:
        lines += ['', '**這次無法判定的規則：**']
        for entry in no_data:
            name = f"{entry['ticker']} 審查線" if entry['rule'] == 'review_line' \
                else f"0050 第 {entry['step_pct']} 階加碼"
            lines.append(f"- {name}：{entry['reason']}")
    if rule_problems:
        lines += ['', '**規則本身有問題：**'] + [f'- {r}' for r in rule_problems]
    if checks and not triggered and not near and not no_data and not feed_problem \
            and not rule_problems:
        lines.append(f'{len(checks)} 條規則全部檢查過，沒有觸發，也沒有接近觸發的。')
    if any(e.get('high_is_stale') for e in checks):
        lines += ['', f"注意：0050 的一年高點資料已超過 45 天沒更新（最後更新 {measured.get('as_of')}），階梯價位需要重算。"]
    if unpriced:
        lines += ['', '沒有價格的部位：'] + [f"- {u['ticker']}：{u['reason']}" for u in unpriced]
    (out / 'daily_check.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


def run():
    """Never let a crash leave the previous run's file standing as today's answer.

    The reporting agent reads the file, not the exit code, and a red mark in a
    CI interface is not a channel that reaches anyone here.
    """
    try:
        main()
    except Exception as exc:
        out = ROOT / 'results'
        out.mkdir(exist_ok=True)
        message = f'每日檢查程式本身出錯了：{type(exc).__name__}: {exc}'
        (out / 'daily_check.json').write_text(json.dumps(dict(
            generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            price_date=None, feed_problem=message, rule_problems=[], data_problem=True,
            rules_total=0, rules_evaluated=0, checks=[], triggered=[], near=[], no_data=[],
            unpriced_positions=[], positions_as_of=None, crashed=True,
            something_to_report=True), indent=2, ensure_ascii=False) + '\n')
        (out / 'daily_check.md').write_text(f'# 每日部位檢查\n\n**{message}**\n\n'
                                            '這次完全沒有判斷任何規則。\n')
        print(message)
        raise


if __name__ == '__main__':
    run()
