from datetime import datetime
from pathlib import Path
import runpy

import pytest

from scripts.audit_filing_sources import inspect_page

program = runpy.run_path(str(Path(__file__).resolve().parents[1] / "experiments/new-1.py"))


def test_report_generation_clock_cannot_supply_company_time():
    table = ("出表日期：113/03/05<!--19:38:22-->"
             "<table><tr><th>公司代號</th><th>當月營收</th><th>去年當月營收</th></tr>"
             "<tr><td>2330</td><td>1</td><td>1</td></tr></table>")
    assert inspect_page(table.encode("cp950")) == (1, "", "")
    revised = table.replace("公司代號", "公司代號</th><th>申報時間")
    assert inspect_page(revised.encode("cp950")) == (1, "申報時間", "")


def test_first_close_strictly_after_publication():
    parse = datetime.fromisoformat
    before = parse("2024-08-09T13:30:00+08:00")
    after = parse("2024-08-12T13:30:00+08:00")
    filing = parse("2024-08-09T15:01:33+08:00")
    assert program["first_execution"](filing, [after, before]) == after
    assert program["first_execution"](before, [before, after]) == after


def test_one_filing_one_day_and_no_conflicting_revisions():
    row = dict(market="sii", company="2330", period="2024-07-01",
               original_filed_at="2024-08-09T15:01:33+08:00", source="test record")
    assert len(program["evidence_dates"]([row, row, dict(row, company="1234")])) == 1
    with pytest.raises(ValueError):
        program["evidence_dates"]([row, dict(row, original_filed_at="2024-08-12T10:00:00+08:00")])
    for invalid in ["2024-08-09", "2024-08-09T15:01:33", "2025-12-01T10:00:00+08:00"]:
        with pytest.raises(ValueError):
            program["filing_time"](invalid)
