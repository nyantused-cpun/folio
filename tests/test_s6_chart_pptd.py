# -*- coding: utf-8 -*-
"""S6 阶段 4-1 chart PPT 批二（waterfall 半项）测试。

bar 半项已随 0d 实施（tests/test_diagram_chart.py::test_render_pptd_bar_native_chart_elem），
本文件只锁 waterfall：spec → render_pptd 数据元素 → _pptd_convert 原生
graphicFrame（COLUMN_STACKED 四系列栈式 emulate，F7 拍板路线，断言风格
参照 bar 既有测试 + 解包 chart XML 验原生结构）。
"""
import os
import sys
import zipfile

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.diagram import chart

# 期初 10（total）→ +5 → −3 → 期末 12（total）
WF_STEPS = [
    {"label": "期初", "value": 10, "kind": "total"},
    {"label": "增加", "value": 5},
    {"label": "下降", "value": -3},
    {"label": "期末", "value": 12, "kind": "total"},
]


def _wf_elem():
    return {"subtype": "waterfall", "steps": WF_STEPS, "unit": "万元"}


def _chart_xml(tmp_path):
    """render_pptd 元素过 _pptd_convert._render_chart，解包 chart XML 返回。"""
    from pptx import Presentation
    import _pptd_convert

    elems, _h = chart.render_pptd(_wf_elem(), 100, 200, 400)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _pptd_convert._render_chart(slide, elems[0])
    out = tmp_path / "wf.pptx"
    prs.save(str(out))
    with zipfile.ZipFile(str(out)) as z:
        names = [n for n in z.namelist()
                 if n.startswith("ppt/charts/chart") and n.endswith(".xml")]
        assert len(names) == 1, "应恰好产出一个原生 chart part"
        return z.read(names[0]).decode("utf-8")


# ---- render_pptd 数据元素（与 _waterfall_html 累计预排同源） ----

def test_waterfall_pptd_elem_structure():
    elems, h = chart.render_pptd(_wf_elem(), 100, 200, 400)
    assert h == 320
    el = elems[0]
    assert el["elementType"] == "chart"
    assert el["chartKind"] == "waterfall"
    assert el["bounds"] == [100, 200, 400, 320]
    assert el["categories"] == ["期初", "增加", "下降", "期末"]
    assert el["unit"] == "万元"
    # 栈式 emulate 四系列：total 从 0 起；delta 底=min(running, running+v)
    wf = el["waterfall"]
    assert wf["base"] == [0.0, 10.0, 12.0, 0.0]
    assert wf["increase"] == [0.0, 5.0, 0.0, 0.0]
    assert wf["decrease"] == [0.0, 0.0, 3.0, 0.0]
    assert wf["total"] == [10.0, 0.0, 0.0, 12.0]
    # 着色与 HTML 端同源（绿增/红减/蓝立柱）
    assert el["colors"] == {"increase": chart.theme.GREEN,
                            "decrease": chart.theme.RED,
                            "total": chart.theme.BLUE}


def test_waterfall_pptd_empty_steps_no_crash():
    elems, h = chart.render_pptd({"subtype": "waterfall"}, 0, 0, 100)
    assert h == 320
    assert elems[0]["categories"] == []
    assert elems[0]["waterfall"] == {"base": [], "increase": [],
                                     "decrease": [], "total": []}


def test_waterfall_pptd_negative_total_supported():
    """负 total（亏损合计）不特殊处理：total 系列负值栈式渲染。"""
    elems, _ = chart.render_pptd(
        {"subtype": "waterfall",
         "steps": [{"label": "亏损", "value": -8, "kind": "total"}]}, 0, 0, 100)
    assert elems[0]["waterfall"]["total"] == [-8.0]
    assert elems[0]["waterfall"]["base"] == [0.0]


def test_render_pptd_unknown_subtype_still_raises():
    with pytest.raises(NotImplementedError):
        chart.render_pptd({"subtype": "pie"}, 0, 0, 100)


# ---- convert 端原生 chart XML 结构 ----

def test_waterfall_native_chart_xml_stacked_four_series(tmp_path):
    import re
    xml = _chart_xml(tmp_path)
    # 原生 graphicFrame chart：栈式柱（python-pptx 1.0.2 无 WATERFALL 枚举）
    assert "<c:barChart>" in xml
    assert 'grouping val="stacked"' in xml
    # 四系列按 base/increase/decrease/total 顺序入栈
    sers = xml.split("<c:ser>")[1:]
    assert len(sers) == 4
    names = [re.search(r"<c:v>([^<]+)</c:v>", s).group(1) for s in sers]
    assert names == ["base", "increase", "decrease", "total"]


def test_waterfall_native_chart_xml_base_invisible_and_colors(tmp_path):
    xml = _chart_xml(tmp_path)
    # base 系列隐形托底：noFill（值标签在 ser 级 dLbls 关闭）
    base_ser = xml.split("<c:ser>")[1]
    assert "<a:noFill/>" in base_ser
    assert "<c:showVal val=\"0\"/>" in base_ser
    # 增/减/总着色与主题色板同源（hex 去 #）
    for color in (chart.theme.GREEN, chart.theme.RED, chart.theme.BLUE):
        assert f'val="{color.lstrip("#").upper()}"' in xml
    # 零值占位段标签隐藏：空零段 number format
    assert 'formatCode="#,##0;-#,##0;"' in xml


def test_waterfall_native_chart_roundtrip(tmp_path):
    """落盘重开仍是原生 chart（graphicFrame，双击可改数据路线）。"""
    from pptx import Presentation
    from pptx.enum.chart import XL_CHART_TYPE
    import _pptd_convert

    elems, _h = chart.render_pptd(_wf_elem(), 0, 0, 400)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    gf = _pptd_convert._render_chart(slide, elems[0])
    assert gf.shape_type is not None  # GraphicFrame 有 shape
    out = tmp_path / "roundtrip.pptx"
    prs.save(str(out))
    prs2 = Presentation(str(out))
    ch = prs2.slides[0].shapes[0].chart
    assert ch.chart_type == XL_CHART_TYPE.COLUMN_STACKED
    assert len(ch.plots[0].categories) == 4


def test_bar_pptd_still_native_path(tmp_path):
    """bar 半项回归锁：批二改动不破坏 0d 已实施的 bar 原生路径。"""
    from pptx import Presentation
    from pptx.enum.chart import XL_CHART_TYPE
    import _pptd_convert

    elems, _h = chart.render_pptd(
        {"subtype": "bar", "categories": ["A"],
         "series": [{"name": "S", "values": [1]}]}, 0, 0, 400)
    assert elems[0]["chartKind"] == "bar"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _pptd_convert._render_chart(slide, elems[0])
    out = tmp_path / "bar.pptx"
    prs.save(str(out))
    ch = Presentation(str(out)).slides[0].shapes[0].chart
    assert ch.chart_type == XL_CHART_TYPE.COLUMN_CLUSTERED
