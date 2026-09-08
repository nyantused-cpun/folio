# -*- coding: utf-8 -*-
"""chart.py 参数化直测（T-2 补，2026-09-07，原 T-2 的 chart 部分从 V-B 挪回本批）。

风格参照 tests/test_pptd_parts.py：纯函数/渲染函数直接调用，参数化覆盖
空 spec / 负值 / 单元素 / 边界。口径 = T-2 原案：空输入、None、单元素、
负值/零尺寸。chart.py 的负值渲染与 waterfall 桥接线已有 test_p3b_diagram
行为级回归，本文件锁参数化边界不重复其行为断言。
"""
import os
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.diagram import chart


# ---- _nice_max / _fmt_num 纯函数边界 ----

@pytest.mark.parametrize("v,expect", [
    (0, 1.0),          # 零/负值兜底 1.0（空图刻度不塌）
    (-5, 1.0),
    (0.4, 0.4),        # 1/2/5 系步进：恰落档位取该档
    (0.06, 0.06),
    (5, 5.0),
    (7, 8.0),
    (12, 12.0),
    (99, 100.0),
])
def test_nice_max(v, expect):
    assert chart._nice_max(v) == expect


@pytest.mark.parametrize("v,expect", [
    (3, "3"),
    (3.0, "3"),        # 整数去小数点
    (3.25, "3.2"),     # 非整数保留一位
    (-2.5, "-2.5"),
])
def test_fmt_num(v, expect):
    assert chart._fmt_num(v) == expect


# ---- _bar_html 参数化边界 ----

def test_bar_empty_spec_renders_frame_only():
    """空 spec：只有网格/轴的骨架 SVG，零数据柱、不抛异常。"""
    html = chart._bar_html({})
    assert '<svg class="dg"' in html
    assert html.count("<rect") == 0


def test_bar_single_category_single_series():
    elem = {"categories": ["A"], "series": [{"name": "S", "values": [5]}]}
    html = chart._bar_html(elem)
    rects = [ln for ln in html.splitlines() if "<rect" in ln]
    assert len(rects) == 1          # 单系列不给图例（图例 rect 不会出现）
    assert ">5<" in html
    assert ">A<" in html


def test_bar_negative_value_renders_below_baseline():
    """负值柱自基线向下（rect y=基线、height=abs），刻度带下探（P3 修复口径）。"""
    elem = {"categories": ["A"], "series": [{"name": "S", "values": [-5]}]}
    html = chart._bar_html(elem)
    # maxv=_nice_max(5)=5，minv=-5，span=10，基线 py1=30+340*5/10=200
    assert 'y="200.0"' in html
    assert 'height="170.0"' in html
    assert ">-5<" in html


def test_bar_values_shorter_than_categories_no_crash():
    """series.values 短于 categories：缺位按 0 兜底，不 IndexError。"""
    elem = {"categories": ["A", "B"],
            "series": [{"name": "S", "values": [1]}]}
    html = chart._bar_html(elem)
    assert ">A<" in html and ">B<" in html


def test_bar_unit_label_and_multi_series_legend():
    elem = {"categories": ["A"],
            "series": [{"name": "S1", "values": [1]},
                       {"name": "S2", "values": [2]}],
            "unit": "万元"}
    html = chart._bar_html(elem)
    assert "单位：万元" in html
    assert ">S1<" in html and ">S2<" in html


# ---- _waterfall_html 参数化边界 ----

def test_waterfall_empty_steps_renders_frame_only():
    html = chart._waterfall_html({})
    assert '<svg class="dg"' in html
    assert html.count("<rect") == 0


def test_waterfall_single_total_step():
    elem = {"steps": [{"label": "合计", "value": 10, "kind": "total"}]}
    html = chart._waterfall_html(elem)
    rects = [ln for ln in html.splitlines() if "<rect" in ln]
    assert len(rects) == 1
    assert ">10<" in html and ">合计<" in html


def test_waterfall_negative_delta_red():
    elem = {"steps": [{"label": "下降", "value": -3}]}
    html = chart._waterfall_html(elem)
    assert f'fill="{chart.theme.RED}"' in html
    assert ">-3<" in html


def test_waterfall_mixed_delta_total_bridge():
    elem = {"steps": [{"label": "期初", "value": 10, "kind": "total"},
                      {"label": "增加", "value": 5},
                      {"label": "期末", "value": 15, "kind": "total"}]}
    html = chart._waterfall_html(elem)
    # 桥接虚线只在柱间出现（3 柱 → 2 条 dasharray 线）
    assert html.count('stroke-dasharray="3,3"') == 2


# ---- 分发层 ----

def test_render_html_unknown_subtype_raises():
    with pytest.raises(NotImplementedError):
        chart.render_html({"subtype": "pie"})


def test_render_pptd_bar_native_chart_elem():
    elem = {"subtype": "bar", "categories": ["A"],
            "series": [{"name": "S", "values": [1]}], "unit": "万元"}
    elems, h = chart.render_pptd(elem, 100, 200, 400)
    assert h == 320
    assert elems[0]["elementType"] == "chart"
    assert elems[0]["chartKind"] == "bar"
    assert elems[0]["categories"] == ["A"]
    assert elems[0]["bounds"] == [100, 200, 400, 320]


def test_render_pptd_waterfall_native_chart_elem():
    """waterfall 批二已接原生 chart（F7）：返回 chartKind=waterfall 数据元素。"""
    elem = {"subtype": "waterfall",
            "steps": [{"label": "a", "value": 1, "kind": "total"}]}
    elems, h = chart.render_pptd(elem, 0, 0, 100)
    assert h == 320
    assert elems[0]["elementType"] == "chart"
    assert elems[0]["chartKind"] == "waterfall"
    assert elems[0]["waterfall"]["total"] == [1.0]
    assert elems[0]["waterfall"]["increase"] == [0.0]
