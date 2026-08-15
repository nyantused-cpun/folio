# -*- coding: utf-8 -*-
"""B-6 决策面板（decision_board）测试。"""

from _renderer import elements
from _renderer import schema


def _spec(options, recommendation="推荐A"):
    return {"pages": [{"id": "p1", "title": "t", "elements": [
        {"type": "decision_board", "options": options,
         "recommendation": recommendation}]}]}


def test_normalize():
    _, n = elements.normalize_element({
        "type": "decision_board",
        "options": [{"name": "A", "pros": ["优1"], "cons": ["劣1"]}],
        "recommendation": "推荐A",
        "next_step": "下一步",
    })
    assert n["options"][0]["name"] == "A"
    assert n["options"][0]["pros"] == ["优1"]
    assert n["recommendation"] == "推荐A"


def test_schema_valid():
    assert schema.validate_spec(_spec(
        [{"name": "A", "pros": ["优1"]}, {"name": "B", "cons": ["劣1"]}]
    )) == []


def test_schema_need_two_options():
    errs = schema.validate_spec(_spec([{"name": "A"}]))
    assert any("≥2" in e for e in errs)


def test_schema_missing_name():
    errs = schema.validate_spec(_spec([{"name": "A"}, {"pros": ["优"]}]))
    assert any("缺 name" in e for e in errs)


def test_schema_missing_recommendation():
    errs = schema.validate_spec(_spec(
        [{"name": "A"}, {"name": "B"}], recommendation=""))
    assert any("缺 recommendation" in e for e in errs)


def test_render_html():
    from _renderer.page_chrome import render_decision_board
    _, n = elements.normalize_element({
        "type": "decision_board",
        "options": [{"name": "A", "pros": ["优1"]},
                    {"name": "B", "cons": ["劣1"]}],
        "recommendation": "推荐A",
    })
    html = render_decision_board(n)
    assert "decision-board" in html
    assert "推荐A" in html
