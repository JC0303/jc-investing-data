"""Every bug fixed in daily_check.py leaves a test here.

The thing this file is really guarding is one sentence: the report may only say
"nothing to report" when every approved rule was actually evaluated against a
price that is known to be the right session's. Each test below reproduces a way
that promise was broken, and fails if it breaks again.
"""
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / 'scripts' / 'daily_check.py'


def load(root):
    spec = importlib.util.spec_from_file_location('daily_check_under_test', SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.ROOT = root
    return module


RULES = {
    'version': 1,
    'monthly_dca': {'ticker': '0050', 'amount_twd': 20000, 'day_of_month': 16},
    'relative_review': {'benchmark': '0050', 'lookback_trading_days': 3, 'lag_pct': 0.15,
                        'applies_to': ['3036'], 'history_from': 'data/tw/history_{ticker}.csv',
                        'unavailable': {'AVGO': '沒有美股價格'}},
    'zero_fifty_ladder': {'ticker': '0050', 'approved_for_execution': False,
                          'steps_pct_below_one_year_high': [0.3],
                          'amount_twd_per_step': 20000,
                          'one_year_high_from': 'data/tw/highs.json'},
    'never': ['place, modify or cancel any order'],
}


@pytest.fixture
def repo(tmp_path):
    """A repo whose every input is sound, so a test changes exactly one thing."""
    today = dt.date.today()
    (tmp_path / 'claude').mkdir()
    (tmp_path / 'data' / 'tw').mkdir(parents=True)
    (tmp_path / 'claude' / 'rules.json').write_text(json.dumps(RULES), encoding='utf-8')
    (tmp_path / 'data' / 'positions.csv').write_text(
        'as_of,market,ticker,instrument,shares,avg_cost\n'
        f'{today},TW,0050,元大台灣50,1774,93.59\n'
        f'{today},TW,3036,文曄,50,188.26\n'
        f'{today},US,AVGO,Broadcom,1,350\n', encoding='utf-8')
    # Four sessions each: a three-session lookback needs four rows.
    for ticker, closes in (('0050', [100, 100, 100, 100]), ('3036', [100, 100, 100, 100])):
        (tmp_path / 'data' / 'tw' / f'history_{ticker}.csv').write_text(
            'date,close\n' + ''.join(f'2026-11-{17 + i:02d},{c:.2f}\n'
                                      for i, c in enumerate(closes)), encoding='utf-8')
    roc = f'{today.year - 1911}{today.month:02d}{today.day:02d}'
    (tmp_path / 'data' / 'tw' / 'stock_day_all.csv').write_text(
        '日期,證券代號,收盤價\n'
        f'{roc},0050,100.00\n{roc},3036,200.00\n', encoding='utf-8')
    (tmp_path / 'data' / 'tw' / 'freshness.json').write_text(json.dumps({
        'expected_trading_day': today.isoformat(), 'verdict': 'OK',
        'checked_taipei': dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
                            .strftime('%Y-%m-%d %H:%M')}), encoding='utf-8')
    (tmp_path / 'data' / 'tw' / 'highs.json').write_text(json.dumps({
        'as_of': today.isoformat(),
        'highs': {'0050': {'one_year_high': 116.60, 'one_year_high_date': '2026-10-06',
                           'source': 'TWSE STOCK_DAY'}}}), encoding='utf-8')
    return tmp_path


def report(repo, env=None, monkeypatch=None):
    module = load(repo)
    if env and monkeypatch:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
    module.run()
    return json.loads((repo / 'results' / 'daily_check.json').read_text())


def test_sound_inputs_give_a_real_all_clear(repo):
    out = report(repo)
    assert out['rule_problems'] == []
    assert out['feed_problem'] is None
    # 3036 relative, AVGO unavailable, one ladder step.
    assert out['rule_instances'] == 3
    # AVGO can never be evaluated here, so that is the honest steady state.
    assert any(c['ticker'] == 'AVGO' and c['status'] == 'NO_DATA' for c in out['checks'])


def test_the_dca_rule_is_stated_even_though_it_is_not_evaluated(repo):
    # It is an approved rule. Leaving it out of the output made the report
    # read as if the rulebook were only the two rules this script checks.
    out = report(repo)
    assert any('定期定額' in line for line in out['rules_not_evaluated_here'])
    assert any('禁止清單' in line for line in out['rules_not_evaluated_here'])


def test_a_holding_that_lags_the_benchmark_is_reported(repo):
    # 3036 falls 20% while 0050 falls nothing: a 20-point lag, past the 15 limit.
    (repo / 'data' / 'tw' / 'history_3036.csv').write_text(
        'date,close\n' + ''.join(f'2026-11-{17 + i:02d},{c:.2f}\n'
                                  for i, c in enumerate([100, 95, 90, 80])), encoding='utf-8')
    out = report(repo)
    hit = [c for c in out['triggered'] if c['ticker'] == '3036']
    assert hit and hit[0]['rule'] == 'relative_review'
    assert out['something_to_report'] is True


def test_a_holding_that_falls_with_the_benchmark_is_not_reported(repo):
    # The point of the rule: being down is not by itself a reason to look.
    # Under the old cost-anchored line this case raised an alarm.
    (repo / 'data' / 'tw' / 'history_0050.csv').write_text(
        'date,close\n' + ''.join(f'2026-11-{17 + i:02d},{c:.2f}\n'
                                  for i, c in enumerate([100, 90, 85, 80])), encoding='utf-8')
    (repo / 'data' / 'tw' / 'history_3036.csv').write_text(
        'date,close\n' + ''.join(f'2026-11-{17 + i:02d},{c:.2f}\n'
                                  for i, c in enumerate([100, 90, 85, 80])), encoding='utf-8')
    out = report(repo)
    rel = [c for c in out['checks'] if c['rule'] == 'relative_review'
           and c['ticker'] == '3036']
    assert rel and rel[0]['status'] == 'CLEAR'


def test_a_holding_down_more_than_its_cost_but_beating_the_benchmark_is_clear(repo):
    (repo / 'data' / 'tw' / 'history_0050.csv').write_text(
        'date,close\n' + ''.join(f'2026-11-{17 + i:02d},{c:.2f}\n'
                                  for i, c in enumerate([100, 80, 70, 60])), encoding='utf-8')
    (repo / 'data' / 'tw' / 'history_3036.csv').write_text(
        'date,close\n' + ''.join(f'2026-11-{17 + i:02d},{c:.2f}\n'
                                  for i, c in enumerate([100, 95, 90, 85])), encoding='utf-8')
    out = report(repo)
    rel = [c for c in out['checks'] if c['rule'] == 'relative_review'
           and c['ticker'] == '3036']
    assert rel and rel[0]['status'] == 'CLEAR'


def test_too_little_history_is_no_data_not_a_pass(repo):
    (repo / 'data' / 'tw' / 'history_3036.csv').write_text(
        'date,close\n' + ''.join(f'2026-11-{17 + i:02d},{c:.2f}\n'
                                  for i, c in enumerate([100, 100])), encoding='utf-8')
    out = report(repo)
    rel = [c for c in out['checks'] if c['rule'] == 'relative_review'
           and c['ticker'] == '3036']
    assert rel and rel[0]['status'] == 'NO_DATA'
    assert out['something_to_report'] is True


def test_mismatched_end_dates_are_refused(repo):
    # Comparing a holding's Tuesday with the benchmark's Friday is not a
    # comparison, however close the numbers look.
    (repo / 'data' / 'tw' / 'history_3036.csv').write_text(
        'date,close\n2026-11-14,100\n2026-11-15,100\n2026-11-16,100\n2026-11-17,100\n',
        encoding='utf-8')
    out = report(repo)
    rel = [c for c in out['checks'] if c['rule'] == 'relative_review'
           and c['ticker'] == '3036']
    assert rel and rel[0]['status'] == 'NO_DATA' and '對不上' in rel[0]['reason']


def test_a_holding_with_no_price_source_is_stated_not_omitted(repo):
    out = report(repo)
    avgo = [c for c in out['checks'] if c['ticker'] == 'AVGO']
    assert avgo and avgo[0]['status'] == 'NO_DATA'
    assert out['something_to_report'] is True


def test_the_ladder_says_what_the_configured_amount_would_buy(repo):
    today = dt.date.today()
    roc = f'{today.year - 1911}{today.month:02d}{today.day:02d}'
    (repo / 'data' / 'tw' / 'stock_day_all.csv').write_text(
        '日期,證券代號,收盤價\n'
        f'{roc},0050,80.00\n{roc},3036,100.00\n', encoding='utf-8')
    out = report(repo)
    step = [c for c in out['checks'] if c['rule'] == 'zero_fifty_ladder'][0]
    assert step['status'] == 'TRIGGERED'
    assert step['shares_at_level'] == int(20000 / float(step['level']))
    assert step['approved_for_execution'] is False


def test_an_empty_applies_to_list_is_not_an_all_clear(repo):
    rules = json.loads(json.dumps(RULES))
    rules['relative_review']['applies_to'] = []
    (repo / 'claude' / 'rules.json').write_text(json.dumps(rules), encoding='utf-8')
    out = report(repo)
    assert any('applies_to' in p for p in out['rule_problems'])
    assert out['something_to_report'] is True


def test_a_missing_ladder_step_list_is_not_an_all_clear(repo):
    rules = json.loads(json.dumps(RULES))
    del rules['zero_fifty_ladder']['steps_pct_below_one_year_high']
    (repo / 'claude' / 'rules.json').write_text(json.dumps(rules), encoding='utf-8')
    out = report(repo)
    assert any('steps_pct_below_one_year_high' in p for p in out['rule_problems'])
    assert out['something_to_report'] is True


def test_a_deleted_rule_block_is_not_an_all_clear(repo):
    rules = json.loads(json.dumps(RULES))
    del rules['relative_review']
    (repo / 'claude' / 'rules.json').write_text(json.dumps(rules), encoding='utf-8')
    out = report(repo)
    assert any('relative_review' in p for p in out['rule_problems'])


def test_an_emptied_never_list_is_reported(repo):
    rules = json.loads(json.dumps(RULES))
    rules['never'] = []
    (repo / 'claude' / 'rules.json').write_text(json.dumps(rules), encoding='utf-8')
    out = report(repo)
    assert any('never' in p for p in out['rule_problems'])


def test_an_unknown_rule_is_reported_rather_than_ignored(repo):
    rules = json.loads(json.dumps(RULES))
    rules['trailing_stop'] = {'pct': 0.2}
    (repo / 'claude' / 'rules.json').write_text(json.dumps(rules), encoding='utf-8')
    out = report(repo)
    assert any('trailing_stop' in p for p in out['rule_problems'])


def test_prices_without_a_recognisable_date_are_not_used(repo):
    # A price that cannot be dated cannot be checked against the expected
    # session, so it cannot be known to be the right day's price. It used to
    # be handed to the rules anyway, which could report a trigger and a data
    # problem in the same report.
    (repo / 'data' / 'tw' / 'stock_day_all.csv').write_text(
        '日期,證券代號,收盤價\n,0050,10.00\n,3036,10.00\n', encoding='utf-8')
    out = report(repo)
    assert '日期' in out['feed_problem']
    assert out['triggered'] == [] and out['near'] == []
    assert len(out['no_data']) == out['rule_instances']


def test_a_price_conflict_does_not_skip_the_feed_check(repo):
    # The conflict branch used to return before the feed was checked, so one
    # disputed ticker was enough to get a stale session priced anyway.
    today = dt.date.today()
    roc = f'{today.year - 1911}{today.month:02d}{today.day:02d}'
    (repo / 'data' / 'tw' / 'stock_day_all.csv').write_text(
        '日期,證券代號,收盤價\n'
        f'{roc},0050,100.00\n{roc},0050,900.00\n{roc},3036,200.00\n', encoding='utf-8')
    (repo / 'data' / 'tw' / 'freshness.json').write_text(json.dumps({
        'expected_trading_day': today.isoformat(), 'verdict': 'FAIL',
        'checked_taipei': dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
                            .strftime('%Y-%m-%d %H:%M'), 'note': 'source down'}),
        encoding='utf-8')
    out = report(repo)
    assert '0050' in out['feed_problem'] and 'FAIL' in out['feed_problem']
    assert out['triggered'] == [] and out['near'] == []


def test_an_empty_freshness_record_is_not_a_pass(repo):
    (repo / 'data' / 'tw' / 'freshness.json').write_text('{}', encoding='utf-8')
    out = report(repo)
    assert out['feed_problem'] and out['something_to_report'] is True


def test_a_freshness_record_that_is_a_list_does_not_crash(repo):
    (repo / 'data' / 'tw' / 'freshness.json').write_text('[]', encoding='utf-8')
    out = report(repo)
    assert out.get('crashed') is not True
    assert out['feed_problem'] and out['something_to_report'] is True


def test_a_high_record_missing_its_number_is_no_data_not_a_crash(repo):
    (repo / 'data' / 'tw' / 'highs.json').write_text(json.dumps({
        'as_of': dt.date.today().isoformat(),
        'highs': {'0050': {'one_year_high_date': '2026-10-06'}}}), encoding='utf-8')
    out = report(repo)
    assert out.get('crashed') is not True
    # The review line still got evaluated: one bad rule must not abort the rest.
    assert any(c['rule'] == 'relative_review' and c['ticker'] == '3036'
               and c['status'] != 'NO_DATA' for c in out['checks'])
    assert any(c['rule'] == 'zero_fifty_ladder' and c['status'] == 'NO_DATA'
               for c in out['checks'])


def test_a_stale_high_does_not_produce_a_clear(repo):
    old = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    (repo / 'data' / 'tw' / 'highs.json').write_text(json.dumps({
        'as_of': old, 'highs': {'0050': {'one_year_high': 116.60}}}), encoding='utf-8')
    out = report(repo)
    ladder = [c for c in out['checks'] if c['rule'] == 'zero_fifty_ladder']
    assert ladder and all(c['status'] == 'NO_DATA' for c in ladder)
    assert out['something_to_report'] is True


def test_a_failed_upstream_fetch_is_reported(repo, monkeypatch):
    out = report(repo, {'UPSTREAM_FETCH_CONCLUSION': 'failure'}, monkeypatch)
    assert '抓價' in out['feed_problem']
    assert out['triggered'] == [] and out['near'] == []


def test_a_broken_feed_also_stops_the_relative_comparison(repo, monkeypatch):
    # The comparison reads history files, not today's feed, so it would
    # otherwise keep answering on a day the pipeline failed.
    out = report(repo, {'UPSTREAM_FETCH_CONCLUSION': 'failure'}, monkeypatch)
    rel = [c for c in out['checks'] if c['rule'] == 'relative_review'
           and c['ticker'] == '3036']
    assert rel and rel[0]['status'] == 'NO_DATA'


def test_stale_history_stops_the_relative_comparison(repo):
    old = dt.date.today() - dt.timedelta(days=40)
    for ticker in ('0050', '3036'):
        (repo / 'data' / 'tw' / f'history_{ticker}.csv').write_text(
            'date,close\n' + ''.join(f'{old + dt.timedelta(days=i)},100.00\n'
                                     for i in range(4)), encoding='utf-8')
    out = report(repo)
    rel = [c for c in out['checks'] if c['rule'] == 'relative_review'
           and c['ticker'] == '3036']
    assert rel and rel[0]['status'] == 'NO_DATA' and '沒更新' in rel[0]['reason']


def test_a_crash_does_not_leave_yesterdays_report_standing(repo):
    good = report(repo)
    assert good.get('crashed') is not True
    (repo / 'claude' / 'rules.json').write_text('{ this is not json', encoding='utf-8')
    with pytest.raises(Exception):
        load(repo).run()
    out = json.loads((repo / 'results' / 'daily_check.json').read_text())
    assert out['crashed'] is True and out['something_to_report'] is True


def test_the_report_still_runs_with_an_unusual_price_set(repo):
    today = dt.date.today()
    roc = f'{today.year - 1911}{today.month:02d}{today.day:02d}'
    (repo / 'data' / 'tw' / 'stock_day_all.csv').write_text(
        '日期,證券代號,收盤價\n'
        f'{roc},0050,100.00\n{roc},3036,120.00\n', encoding='utf-8')
    out = report(repo)
    assert any(c['rule'] == 'zero_fifty_ladder' for c in out['checks'])
    assert out['something_to_report'] is True
