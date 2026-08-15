# -*- coding: utf-8 -*-
"""B-3 证据台账（evidence_ledger）测试。"""

from _renderer import elements
from _renderer import schema


def _spec(items):
    return {"pages": [{"id": "p1", "title": "t",
                       "elements": [{"type": "evidence_ledger", "items": items}]}]}


def test_normalize():
    _, n = elements.normalize_element({
        "type": "evidence_ledger",
        "title": "台账",
        "items": [{"num": "E-01", "conclusion": "结论",
                   "evidence": "证据", "status": "已覆盖"}],
    })
    assert n["title"] == "台账"
    assert n["items"][0]["num"] == "E-01"
    assert n["items"][0]["conclusion"] == "结论"


def test_schema_valid():
    assert schema.validate_spec(_spec(
        [{"num": "E-01", "conclusion": "结论", "evidence": "证据"}]
    )) == []


def test_schema_missing_conclusion():
    errs = schema.validate_spec(_spec([{"num": "E-01", "evidence": "证据"}]))
    assert any("缺 conclusion" in e for e in errs)


def test_schema_missing_evidence():
    errs = schema.validate_spec(_spec([{"num": "E-01", "conclusion": "结论"}]))
    assert any("缺 evidence" in e for e in errs)


def test_schema_empty_items():
    errs = schema.validate_spec(_spec([]))
    assert any("evidence_ledger 缺 items" in e for e in errs)


def test_capacity_warning():
    items = [{"num": f"E-{i}", "conclusion": "c", "evidence": "e"}
             for i in range(13)]
    warnings = schema.validate_element_warnings(
        {"type": "evidence_ledger", "items": items})
    assert any("超过上限" in w for w in warnings)


def test_render_html():
    from _renderer.page_chrome import render_evidence_ledger
    _, n = elements.normalize_element({
        "type": "evidence_ledger",
        "items": [{"num": "E-01", "conclusion": "结论",
                   "evidence": "证据", "status": "已覆盖"}],
    })
    html = render_evidence_ledger(n)
    assert "evidence-table" in html
    assert "E-01" in html
    assert "结论" in html


def test_verify_duplicate_num():
    from _verify import check_evidence_ledger
    spec = {"pages": [{"id": "p1", "title": "t", "elements": [
        {"type": "evidence_ledger", "items": [
            {"num": "E-01", "conclusion": "a", "evidence": "b"},
            {"num": "E-01", "conclusion": "c", "evidence": "d"},
        ]},
    ]}]}
    msgs = check_evidence_ledger(spec)
    assert any("编号重复" in m and "E-01" in m for m in msgs)

