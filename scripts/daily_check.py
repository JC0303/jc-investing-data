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
    # Every problem is collected before anything is returned. Returning on the
    # first one let a later, more serious one go unchecked: a conflicting price
    # used to return early and skip the feed check entirely, so a stale session
    # plus one disputed ticker still produced priced verdicts.
    problems = []
    if conflicts:
        problems.append('收盤檔裡有同一檔股票的多個不同價格：' + '、'.join(sorted(conflicts)))
    if not closes:
        problems.append('台股收盤檔存在但沒有任何可用的收盤價')
    if day is None:
        # A price with no date cannot be checked against the expected session,
        # so it cannot be known to be today's price.
        problems.append('台股收盤檔沒有可辨識的日期')
    if feed_issue:
        problems.append(feed_issue)
    if day is not None:
        if expected and day != expected:
            problems.append(f'台股收盤資料日期是 {day}，但預期交易日是 {expected}')
        age = (dt.date.today() - dt.date.fromisoformat(day)).days
        if age > STALE_DAYS:
            problems.append(f'台股收盤資料停在 {day}，已經 {age} 天沒更新')
    if problems:
        # Drop the prices: a rule must never be judged against a session that
        # is not the one it is supposed to be judging.
        return {}, day, '；'.join(problems)
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
    # The field each rule's loop iterates is as load-bearing as the rule block
    # itself: an empty or missing list silently produced zero checks and a
    # smaller rules_total, with nothing saying a rule had stopped being checked.
    for key, field in (('relative_review', 'applies_to'),
                       ('zero_fifty_ladder', 'steps_pct_below_one_year_high')):
        block = rules.get(key)
        if not isinstance(block, dict) or not block:
            rule_problems.append(f'規則檔裡找不到或讀不懂「{key}」這條規則')
            continue
        items = block.get(field)
        if not isinstance(items, list) or not items:
            rule_problems.append(f'「{key}」這條規則的「{field}」是空的或不見了，'
                                 f'這條規則這次完全沒有被檢查')
    # Approved rules this script does not evaluate are still stated, so the
    # report never implies the rulebook is only what it happened to check.
    not_evaluated = []
    dca = rules.get('monthly_dca')
    if isinstance(dca, dict) and dca:
        not_evaluated.append(
            f"每月定期定額（{dca.get('ticker')} 每月 {dca.get('day_of_month')} 日 "
            f"{dca.get('amount_twd')} 元）：這是固定扣款，不需要每日判斷，所以這個檢查不看它")
    elif 'monthly_dca' in rules:
        rule_problems.append('規則檔裡的「monthly_dca」讀不懂')
    never = rules.get('never')
    if not isinstance(never, list) or not never:
        rule_problems.append('規則檔裡的「never」禁止清單是空的或不見了，'
                             '這是不下單、不換匯、不改券商設定的那一條')
    else:
        not_evaluated.append('禁止清單（不下單、不換匯、不改券商設定）：'
                             f'{len(never)} 條，程式本身永遠不做這些事')
    for key in rules:
        if key.startswith('_') or key in ('version', 'updated', 'relative_review',
                                          'zero_fifty_ladder', 'monthly_dca', 'never',
                                          'positions_held_without_addition'):
            continue
        rule_problems.append(f'規則檔裡有這個程式不認得的規則「{key}」，它不會被檢查')

    rel = rules.get('relative_review', {})
    lookback = int(rel.get('lookback_trading_days') or 0)
    lag_limit = Decimal(str(rel.get('lag_pct', 0)))
    bench_ticker = rel.get('benchmark') or '0050'
    template = rel.get('history_from') or 'data/tw/history_{ticker}.csv'

    def change_over(ticker):
        """Return (pct_change, first_date, last_date) or (None, reason, None)."""
        path = ROOT / template.format(ticker=ticker)
        if not path.exists():
            return None, f'找不到 {ticker} 的歷史價格檔', None
        rows = []
        with path.open(encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                close = (row.get('close') or '').strip()
                date = (row.get('date') or '').strip()
                if not close or not date:
                    continue
                try:
                    value = Decimal(close)
                except Exception:
                    continue
                if value > 0:
                    rows.append((date, value))
        rows.sort()
        if len(rows) < lookback + 1:
            return None, (f'{ticker} 的歷史價格只有 {len(rows)} 天，'
                          f'不到比較需要的 {lookback + 1} 天'), None
        start_date, start_price = rows[-(lookback + 1)]
        end_date, end_price = rows[-1]
        return (end_price - start_price) / start_price, start_date, end_date

    bench_change, bench_from, bench_to = change_over(bench_ticker)
    # This rule reads its own history files, not today's feed, so without this
    # check it would go on answering confidently on a day the pipeline failed —
    # the exact failure this project keeps finding.
    history_problem = None
    if feed_problem:
        history_problem = f'今天的行情本身有問題，這個比較也不可信（{feed_problem}）'
    elif bench_to:
        try:
            age = (dt.date.today() - dt.date.fromisoformat(bench_to)).days
            if age > STALE_DAYS:
                history_problem = (f'歷史價格停在 {bench_to}，已經 {age} 天沒更新，'
                                   f'不能用來判斷現在的相對表現')
        except ValueError:
            history_problem = f'歷史價格的日期讀不懂（{bench_to}）'
    for ticker in rel.get('applies_to', []):
        row = next((r for r in positions if r['ticker'] == ticker), None)
        base = dict(rule='relative_review', ticker=ticker,
                    instrument=row['instrument'] if row else None,
                    benchmark=bench_ticker, lookback_trading_days=lookback,
                    price_date=price_date)
        if row is None:
            checks.append(dict(base, status='NO_DATA', reason='持股清單裡沒有這一檔'))
            continue
        if history_problem:
            checks.append(dict(base, status='NO_DATA', reason=history_problem))
            continue
        if bench_change is None:
            checks.append(dict(base, status='NO_DATA',
                               reason=f'沒有可比較的 {bench_ticker} 基準：{bench_from}'))
            continue
        change, since, until = change_over(ticker)
        if change is None:
            checks.append(dict(base, status='NO_DATA', reason=since))
            continue
        if until != bench_to:
            # Comparing two different end dates is not a comparison.
            checks.append(dict(base, status='NO_DATA',
                               reason=f'{ticker} 的資料到 {until}，{bench_ticker} 到 {bench_to}，'
                                      f'日期對不上，不能比較'))
            continue
        lag = change - bench_change
        entry = dict(base, since=since, until=until,
                     change_pct=str((change * 100).quantize(Decimal('0.01'))),
                     benchmark_change_pct=str((bench_change * 100).quantize(Decimal('0.01'))),
                     lag_pct=str((lag * 100).quantize(Decimal('0.01'))),
                     limit_pct=str((lag_limit * 100).quantize(Decimal('0.01'))))
        if lag <= -lag_limit:
            entry['status'] = 'TRIGGERED'
        elif lag <= -lag_limit + NEAR:
            entry['status'] = 'NEAR'
        else:
            entry['status'] = 'CLEAR'
        checks.append(entry)

    # A holding the rule names but cannot reach is stated, never left silent.
    for ticker, reason in (rel.get('unavailable') or {}).items():
        row = next((r for r in positions if r['ticker'] == ticker), None)
        checks.append(dict(rule='relative_review', ticker=ticker,
                           instrument=row['instrument'] if row else None,
                           benchmark=bench_ticker, price_date=price_date,
                           status='NO_DATA', reason=reason))

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
        try:
            high = Decimal(str(entry_high['one_year_high']))
        except (KeyError, TypeError, ArithmeticError, ValueError):
            # A high record present but unreadable is the same as not having
            # one. It used to raise here, which aborted the whole run after
            # the earlier rules had already been evaluated.
            checks.append(dict(base, status='NO_DATA',
                               reason='一年高點紀錄裡沒有可用的數字'))
            continue
        if high <= 0:
            checks.append(dict(base, status='NO_DATA', reason='一年高點不是正數'))
            continue
        as_of = measured.get('as_of')
        stale_high = as_of is None or (dt.date.today() - dt.date.fromisoformat(as_of)).days > 45
        price = closes[ticker]
        level = (high * (1 - Decimal(str(step)))).quantize(Decimal('0.01'))
        gap = (price - level) / level
        amount = ladder.get('amount_twd_per_step')
        entry = dict(base, price=str(price), level=str(level), one_year_high=str(high),
                     amount_twd_per_step=amount,
                     shares_at_level=(int(Decimal(str(amount)) / level) if amount else None),
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
        # These count rule instances (one ticker, one ladder step), not rule
        # blocks: the old name "rules_total" read as the size of the rulebook.
        rule_instances=len(checks), rule_instances_evaluated=len(checks) - len(no_data),
        rules_not_evaluated_here=not_evaluated,
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
        if entry['rule'] == 'relative_review':
            lines.append(f"**觸發｜{entry['ticker']} {entry['instrument']}**："
                         f"過去 {entry['lookback_trading_days']} 個交易日漲跌 {entry['change_pct']}%，"
                         f"同期間 0050 是 {entry['benchmark_change_pct']}%，"
                         f"落後 {entry['lag_pct']}%，超過 {entry['limit_pct']}% 的門檻。"
                         f"這是提醒你重新看一次，不是賣出指示。")
        else:
            note = '（這一階你還沒核准執行）' if not entry['approved_for_execution'] else ''
            buy = (f"照你設定的每階 {entry['amount_twd_per_step']} 元，這個價位約可買 "
                   f"{entry['shares_at_level']} 股。這是照規則算出來的數字，不是建議你買。"
                   if entry.get('shares_at_level') else '')
            lines.append(f"**觸發｜0050 第 {entry['step_pct']} 階**：收盤 {entry['price']}，"
                         f"已到 {entry['level']}，距一年高點 {entry['drawdown_pct']}%。{note}{buy}")
    for entry in near:
        if entry['rule'] == 'relative_review':
            lines.append(f"接近｜{entry['ticker']} {entry['instrument']}："
                         f"落後 0050 {entry['lag_pct']}%，門檻是 {entry['limit_pct']}%。")
        else:
            buy = (f"照每階 {entry['amount_twd_per_step']} 元，到價時約可買 "
                   f"{entry['shares_at_level']} 股。"
                   if entry.get('shares_at_level') else '')
            lines.append(f"接近｜0050 第 {entry['step_pct']} 階：收盤 {entry['price']}，"
                         f"距 {entry['level']} 還有一小段，目前距一年高點 "
                         f"{entry['drawdown_pct']}%。{buy}")
    if no_data:
        lines += ['', '**這次無法判定的規則：**']
        for entry in no_data:
            name = f"{entry['ticker']} 相對 0050 檢視" if entry['rule'] == 'relative_review' \
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
            rule_instances=0, rule_instances_evaluated=0, rules_not_evaluated_here=[],
            rules_total=0, rules_evaluated=0, checks=[], triggered=[], near=[], no_data=[],
            unpriced_positions=[], positions_as_of=None, crashed=True,
            something_to_report=True), indent=2, ensure_ascii=False) + '\n')
        (out / 'daily_check.md').write_text(f'# 每日部位檢查\n\n**{message}**\n\n'
                                            '這次完全沒有判斷任何規則。\n')
        print(message)
        raise


if __name__ == '__main__':
    run()
