"""The A-track revenue-eligibility month, and why it is not carried forward.

Monthly revenue for month M is published by the 10th of M+1. A backtest that
forward-fills eligibility can hold a position qualified on revenue that is
months stale, which is knowledge the strategy would not have had and which
flatters the result. These tests pin the month arithmetic and the refusal to
carry a verdict forward.
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

SRC = Path(__file__).resolve().parent.parent / 'scripts' / 'tw_a_track_check.py'


@pytest.fixture(scope='module')
def mod():
    spec = importlib.util.spec_from_file_location('a_track_under_test', SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('day,expected', [
    ('2026-03-09', (2026, 1)),    # before the 10th: January is the latest published
    ('2026-03-10', (2026, 2)),    # from the 10th: February has been published
    ('2026-03-31', (2026, 2)),
    ('2026-01-09', (2025, 11)),   # across the year boundary, both directions
    ('2026-01-10', (2025, 12)),
    ('2026-02-09', (2025, 12)),
])
def test_the_applicable_month_follows_the_publication_date(mod, day, expected):
    assert mod.applicable_month(pd.Timestamp(day)) == expected


def test_a_month_with_no_revenue_is_not_eligible(mod):
    # The regression: 2026-01 qualifies, 2026-02 has no row at all. A day in
    # March that may only use February must not inherit January's verdict.
    flags = pd.DataFrame([{'ticker': '1234', 'year': 2026, 'month': 1, 'ok': True}])
    cal = pd.DatetimeIndex(['2026-02-12', '2026-03-12'])
    q = mod.qualified_matrix(flags, cal, ['1234'])
    assert bool(q.loc[pd.Timestamp('2026-02-12'), '1234']) is True
    assert bool(q.loc[pd.Timestamp('2026-03-12'), '1234']) is False


def test_a_failing_month_is_not_rescued_by_an_earlier_pass(mod):
    flags = pd.DataFrame([
        {'ticker': '1234', 'year': 2026, 'month': 1, 'ok': True},
        {'ticker': '1234', 'year': 2026, 'month': 2, 'ok': False}])
    cal = pd.DatetimeIndex(['2026-02-12', '2026-03-12'])
    q = mod.qualified_matrix(flags, cal, ['1234'])
    assert bool(q.loc[pd.Timestamp('2026-03-12'), '1234']) is False


def test_a_ticker_with_no_revenue_at_all_is_never_eligible(mod):
    flags = pd.DataFrame([{'ticker': '1234', 'year': 2026, 'month': 1, 'ok': True}])
    cal = pd.DatetimeIndex(['2026-02-12', '2026-03-12'])
    q = mod.qualified_matrix(flags, cal, ['1234', '9999'])
    assert not q['9999'].any()


def test_eligibility_is_not_granted_before_publication(mod):
    # A flag for February must not be in force on 2026-03-09, only from the 10th.
    flags = pd.DataFrame([{'ticker': '1234', 'year': 2026, 'month': 2, 'ok': True}])
    cal = pd.DatetimeIndex(['2026-03-09', '2026-03-10'])
    q = mod.qualified_matrix(flags, cal, ['1234'])
    assert bool(q.loc[pd.Timestamp('2026-03-09'), '1234']) is False
    assert bool(q.loc[pd.Timestamp('2026-03-10'), '1234']) is True
