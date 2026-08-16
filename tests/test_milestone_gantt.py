# -*- coding: utf-8 -*-

import pytest

pytestmark = pytest.mark.internal
"""B-7 里程碑甘特（timeline/milestone_gantt）测试。"""

from _renderer import schema


def _elem(**kw):
    return {"type": "diagram", "diagram_type": "timeline",
            "subtype": "milestone_gantt", "title": "路线图",
            "columns": ["W1", "W2", "W3", "W4"],
            "tasks": [{"name": "调研", "start": 0, "span": 2}], **kw}


def _spec(**kw):
    return {"pages": [{"id": "p1", "title": "t", "elements": [
        {"type": "diagram", "diagram_type": "timeline",
         "subtype": "milestone_gantt", "title": "路线图", **kw}]}]}


def test_schema_valid():
    assert schema.validate_spec(_spec(
        columns=["W1", "W2"], tasks=[{"name": "调研", "start": 0, "span": 1}]
    )) == []


def test_schema_missing_columns():
    errs = schema.validate_spec(_spec(tasks=[{"name": "t"}]))
    assert any("缺必填字段 'columns'" in e for e in errs)


def test_schema_missing_tasks():
    errs = schema.validate_spec(_spec(columns=["W1"]))
    assert any("缺必填字段 'tasks'" in e for e in errs)


def test_capacity_warning():
    tasks = [{"name": f"t{i}", "start": 0, "span": 1} for i in range(11)]
    warnings = schema.validate_element_warnings(_elem(
        columns=["W1", "W2"], tasks=tasks))
    assert any("超过" in w for w in warnings)


def test_geometry_bar_span():
    from _renderer.diagram import timeline
    g = timeline._msg_geometry(_elem(
        columns=["W1", "W2", "W3", "W4"],
        tasks=[{"name": "调研", "start": 0, "span": 2}]))
    col_w = g["col_w"]
    assert abs(g["rows"][0]["bar_w"] - (2 * col_w - 8)) < 0.01


def test_html_render():
    from _renderer.diagram import timeline
    html = timeline.render_html(_elem(
        columns=["W1", "W2", "W3"],
        tasks=[{"name": "调研", "start": 0, "span": 2, "deps": [1]},
               {"name": "设计", "start": 1, "span": 2}]))
    assert "调研" in html
    assert "msg-arrow" in html  # 有依赖箭头


def test_pptd_render():
    from _renderer.diagram import timeline
    elems, h = timeline.render_pptd(_elem(
        columns=["W1", "W2", "W3"],
        tasks=[{"name": "调研", "start": 0, "span": 2, "deps": [1]},
               {"name": "设计", "start": 1, "span": 2}]), 0, 0, 1200)
    ids = [str(e.get("elementId", "")) for e in elems]
    assert any("msg-b" in i for i in ids)
    assert any("msg-dep" in i for i in ids)  # 依赖箭头 connector
    assert h > 0


def test_deps_by_name_html():
    """deps 用任务名引用（图鉴 spec 实测踩坑：int(dep) 对中文名抛 ValueError）。"""
    from _renderer.diagram import timeline
    html = timeline.render_html(_elem(
        columns=["W1", "W2", "W3", "W4"],
        tasks=[{"name": "需求调研", "start": 0, "span": 2},
               {"name": "蓝图设计", "start": 1, "span": 3, "deps": ["需求调研"]}]))
    assert "msg-arrow" in html  # 依赖箭头正常渲染，不抛异常


def test_deps_by_name_pptd():
    from _renderer.diagram import timeline
    elems, h = timeline.render_pptd(_elem(
        columns=["W1", "W2", "W3", "W4"],
        tasks=[{"name": "需求调研", "start": 0, "span": 2},
               {"name": "蓝图设计", "start": 1, "span": 3, "deps": ["需求调研"]}]), 0, 0, 1200)
    ids = [str(e.get("elementId", "")) for e in elems]
    assert any("msg-dep" in i for i in ids)  # 名字引用解析出依赖箭头


def test_deps_unknown_name_skipped():
    """deps 引用不存在的任务名 → 跳过该依赖，不抛异常。"""
    from _renderer.diagram import timeline
    elems, h = timeline.render_pptd(_elem(
        columns=["W1", "W2"],
        tasks=[{"name": "A", "start": 0, "span": 1, "deps": ["不存在"]}]), 0, 0, 1200)
    ids = [str(e.get("elementId", "")) for e in elems]
    assert not any("msg-dep" in i for i in ids)
