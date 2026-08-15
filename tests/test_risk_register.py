# -*- coding: utf-8 -*-
"""B-4 风险登记（risk_register）测试。"""

from _renderer import elements
from _renderer import schema


def _spec(items):
    return {"pages": [{"id": "p1", "title": "t",
                       "elements": [{"type": "risk_register", "items": items}]}]}


def test_normalize():
    _, n = elements.normalize_element({
        "type": "risk_register",
        "title": "风险",
        "items": [{"risk": "数据迁移失败", "level": "高",
                   "status": "未解决", "response": "备份"}],
    })
    assert n["title"] == "风险"
    assert n["items"][0]["risk"] == "数据迁移失败"
    assert n["items"][0]["level"] == "高"


def test_schema_valid():
    assert schema.validate_spec(_spec(
        [{"risk": "迁移失败", "level": "高", "response": "备份"}]
    )) == []


def test_schema_missing_risk():
    errs = schema.validate_spec(_spec([{"level": "高", "response": "备份"}]))
    assert any("缺 risk" in e for e in errs)


def test_schema_missing_response():
    errs = schema.validate_spec(_spec([{"risk": "迁移失败", "level": "高"}]))
    assert any("缺 response" in e for e in errs)


def test_schema_illegal_level():
    errs = schema.validate_spec(_spec(
        [{"risk": "迁移失败", "level": "极高", "response": "备份"}]))
    assert any("level 非法值" in e for e in errs)


def test_capacity_warning():
    items = [{"risk": "r", "level": "高", "response": "x"} for _ in range(13)]
    warnings = schema.validate_element_warnings(
        {"type": "risk_register", "items": items})
    assert any("超过上限" in w for w in warnings)


def test_render_html():
    from _renderer.page_chrome import render_risk_register
    _, n = elements.normalize_element({
        "type": "risk_register",
        "items": [{"risk": "迁移失败", "level": "高",
                   "status": "未解决", "response": "备份"}],
    })
    html = render_risk_register(n)
    assert "risk-table" in html
    assert "迁移失败" in html
    assert "lv-high" in html
