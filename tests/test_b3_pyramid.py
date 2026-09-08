# -*- coding: utf-8 -*-
"""B3-A2 回归：pyramid trapezoid adj 语义（P0-2）+ 双端高度统一（P3）。

P0-2：OOXML trapezoid preset 的 adj 语义是「顶边左右各内缩 ss×adj/100000
（ss=min(w,h)）」，此前发射端误用 上边宽/下边宽 比值、convert 端 ÷100000
回写，任何合法 spec（schema 强制 2-6 层）转 PPT 全量错版。修复后公式：
adj = (bot_w - top_w) / 2 / min(bot_w, layer_h) × 100000，钳位
[0, 50000×bot_w/ss]（preset gdLst：maxAdj=50000×w/ss，a=pin 0 adj maxAdj）。

P3：HTML viewBox 高 400 与 pptd 消耗高度 360 不一致，统一为单一常量
_PYRAMID_VB_H=400（以 HTML polygon 为正确基准，设计文档 §D-5 同为
viewBox 1200×400）。

外部参考合规铁律：OOXML trapezoid 几何语义引自 ECMA-376
presetShapeDefinitions.xml 标准文档事实（底边=全宽、顶边内缩 ss×adj/100000、
maxAdj 钳位公式），仅引用标准语义，未复制任何外部项目代码/标识符/数据结构。
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _renderer.diagram.architecture import (
    _PYRAMID_VB_H, _pyramid_html, _pyramid_pptd, _pyramid_trap_adj,
)

TOL_SNAP = 12.0  # 发射出口 4px 网格吸附的复合噪声上界（bw/bh 各 ±4 叠加）


def _pyramid_spec(n):
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "pyramid",
            "title": "能力分层",
            "levels": [{"title": f"L{i}", "desc": ""} for i in range(n)]}


def _traps(elems):
    return [e for e in elems if e.get("shapeName") == "trapezoid"]


# ---------------------------------------------------------------------------
# P0-2：adj 语义公式
# ---------------------------------------------------------------------------

def test_adj_matches_ooxml_inset_semantics():
    """给定具体几何，adj 必须等于内缩语义公式值，且由 adj 反推顶边宽闭合。"""
    cases = [
        # (top_w, bot_w, layer_h)——覆盖 ss 取 h / 取 w 两种分支
        (200, 600, 200),   # 宽扁层：inset=200, ss=200 → 100000
        (300, 700, 100),   # 极扁层：inset=200, ss=100 → 200000
        (100, 200, 500),   # 窄高层：ss=bot_w=200 → inset=50 → 25000
        (500, 800, 150),   # inset=150, ss=150 → 100000
    ]
    for top_w, bot_w, layer_h in cases:
        ss = min(bot_w, layer_h)
        expected = int(round((bot_w - top_w) / 2 / ss * 100000))
        got = _pyramid_trap_adj(top_w, bot_w, layer_h)
        assert got == expected, (top_w, bot_w, layer_h)
        # OOXML 语义闭环：adj 反推顶边宽 == top_w
        implied_top = bot_w - 2 * ss * got / 100000
        assert abs(implied_top - top_w) < 1e-6, (top_w, bot_w, layer_h)


def test_adj_zero_for_rectangular_layer():
    """矩形层（top_w==bot_w）内缩为 0 → adj==0（旧公式会误发 100000 比值）。"""
    assert _pyramid_trap_adj(400, 400, 120) == 0
    assert _pyramid_trap_adj(1000, 1000, 66.7) == 0


def test_adj_clamped_to_legal_range():
    """钳位边界：越 maxAdj 上界钳到 maxAdj，负内缩钳 0，退化几何不炸。"""
    # 内缩推过 maxAdj=50000×w/ss（非法负顶宽构造）：钳到上界且不越界
    got = _pyramid_trap_adj(-200, 1000, 10)
    max_adj = 50000.0 * 1000 / 10
    assert got == int(round(max_adj))
    # top_w > bot_w（负内缩）→ 钳 0
    assert _pyramid_trap_adj(800, 600, 100) == 0
    # 退化几何（零宽/零高）→ 0
    assert _pyramid_trap_adj(200, 0, 100) == 0
    assert _pyramid_trap_adj(200, 1000, 0) == 0


def test_adj_within_legal_range_all_layer_counts():
    """schema 合法层数 2-6 全扫：发射 adj 均在 OOXML 合法域内且几何可还原。"""
    for n in range(2, 7):
        elems, _ = _pyramid_pptd(_pyramid_spec(n), 0.0, 0.0, 1200.0)
        traps = _traps(elems)
        assert len(traps) == n
        for e in traps:
            bx, by, bw, bh = e["bounds"]
            adj = e["adjustments"][0]
            assert isinstance(adj, int)
            ss = min(bw, bh)
            max_adj = 50000.0 * bw / ss
            assert 0 <= adj <= max_adj, (n, adj, max_adj)
            # 反推顶边宽必须为正（每层是合法梯形，不塌成越界几何）
            assert bw - 2 * ss * adj / 100000 > 0


# ---------------------------------------------------------------------------
# P0-2：双端几何对齐（HTML polygon 基准 ↔ pptd adj 反推）
# ---------------------------------------------------------------------------

def _parse_polygons(html):
    polys = re.findall(r'<polygon points="([^"]+)"', html)
    return [[tuple(float(v) for v in p.split(",")) for p in poly.split()]
            for poly in polys]


def test_double_end_alignment_snap_exact_counts():
    """n=2/4（layer_h 恰为 4px 网格倍数，吸附零漂移）：pptd adj 反推几何
    与 HTML polygon 逐层精确一致（底边=全宽 bbox、顶边=adj 反推宽）。"""
    for n in (2, 4):
        elem = _pyramid_spec(n)
        polys = _parse_polygons(_pyramid_html(elem))
        assert len(polys) == n
        elems, _ = _pyramid_pptd(elem, 0.0, 0.0, 1200.0)  # scale=1 → 直读 viewBox 单位
        traps = _traps(elems)
        assert len(traps) == n
        # polygon 顶点序：左上(x1,y1) 右上(x2,·) 右下(x4,yb) 左下(x3,·)
        for poly, e in zip(polys, traps, strict=True):
            (x1, y1), (x2, _), (x4, yb), (x3, _) = poly
            bx, by, bw, bh = e["bounds"]
            adj = e["adjustments"][0]
            # 底边 = preset 全宽 → bbox 宽/位置与 HTML 底边一致
            assert abs(bw - (x4 - x3)) < 0.51
            assert abs(bx - x3) < 0.51
            assert abs(by - y1) < 0.51
            assert abs(by + bh - yb) < 0.51
            # adj 反推顶边宽 == HTML 顶边宽（P0-2 修复核心闭环）
            ss = min(bw, bh)
            implied_top = bw - 2 * ss * adj / 100000
            assert abs(implied_top - (x2 - x1)) < 0.51


def test_double_end_alignment_within_snap_noise():
    """n=3/6（layer_h 非网格倍数）：双端几何差在 4px 吸附复合噪声内。"""
    for n in (3, 6):
        elem = _pyramid_spec(n)
        polys = _parse_polygons(_pyramid_html(elem))
        elems, _ = _pyramid_pptd(elem, 0.0, 0.0, 1200.0)
        traps = _traps(elems)
        assert len(traps) == n
        for poly, e in zip(polys, traps, strict=True):
            (x1, y1), (x2, _), (x4, yb), (x3, _) = poly
            bx, by, bw, bh = e["bounds"]
            adj = e["adjustments"][0]
            assert abs(bw - (x4 - x3)) < TOL_SNAP
            assert abs(bx - x3) < TOL_SNAP
            assert abs(by - y1) < TOL_SNAP
            assert abs(by + bh - yb) < TOL_SNAP
            ss = min(bw, bh)
            implied_top = bw - 2 * ss * adj / 100000
            assert abs(implied_top - (x2 - x1)) < TOL_SNAP


# ---------------------------------------------------------------------------
# P3：双端高度统一（单一常量 _PYRAMID_VB_H，以 HTML=400 为基准）
# ---------------------------------------------------------------------------

def test_height_unified_double_end():
    """HTML viewBox 高与 pptd 消耗高度同源同值（原 400 vs 360 不一致）。"""
    assert _PYRAMID_VB_H == 400  # 设计文档 §D-5 基准：viewBox 1200×400
    elem = _pyramid_spec(3)
    html = _pyramid_html(elem)
    m = re.search(r'viewBox="0 0 1200 ([\d.]+)"', html)
    assert m, "HTML pyramid 缺 viewBox"
    vb_h = float(m.group(1))
    consumed = _pyramid_pptd(elem, 0.0, 0.0, 1200.0)[1]
    assert vb_h == float(_PYRAMID_VB_H)
    assert consumed == vb_h  # 双端各取一次相等
    # 等比换算：任意内容区宽下消耗高 = vb_h × (w/1200)
    consumed_half = _pyramid_pptd(elem, 10.0, 20.0, 600.0)[1]
    assert abs(consumed_half - vb_h / 2) < 0.51


# ---------------------------------------------------------------------------
# convert 端闭环（emit 原始 val → convert ÷100000 → python-pptx 回写 XML）
# ---------------------------------------------------------------------------

def test_pptx_adjustment_roundtrip_closes_loop():
    """convert 端无需改动：emit 写 OOXML 原始 val（0~100000），convert 按
    ÷100000 写 python-pptx effective value，python-pptx 回写 XML 时 ×100000
    还原——整数原始值无损闭环（TRAPEZOID 恰暴露 1 个 adjustment 槽位）。"""
    pytest.importorskip("pptx")
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn
    from pptx.util import Emu

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    shape = slide.shapes.add_shape(MSO_SHAPE.TRAPEZOID, Emu(0), Emu(0),
                                   Emu(914400), Emu(914400))
    assert len(shape.adjustments) == 1
    for raw in (0, 25000, 100000, 200000):
        shape.adjustments[0] = raw / 100000.0  # _pptd_convert._render_shape 回写公式
        av_lst = shape._element.spPr.find(qn("a:prstGeom")).find(qn("a:avLst"))
        val = int(av_lst.find(qn("a:gd")).get("fmla").split()[-1])
        assert val == raw, raw
