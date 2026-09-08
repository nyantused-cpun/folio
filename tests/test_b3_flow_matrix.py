# -*- coding: utf-8 -*-
"""B3 批 A3 组回归测试：flow / matrix / view_cards 四缺陷（2026-09-06）。

- P1-10：flow parallel HTML 端旧守卫 `bi >= len(nodes)-1` 吞边——
  after=[]（schema 合法）时「源→网关」箭头全缺、merge→after 末段边恒被
  跳过；对齐 pptd 侧（render_pptd 对边集全量连线）语义
- P2：swimlane / cross_system 引用未声明 lane/system 的步骤双端静默丢弃
  → 丢弃行为不变，两端各补一条显式中文告警
- P1-11：matrix raci / crud 空 cell 字符串漏 f 前缀，字面 `{theme.`
  泄漏进交付 HTML（de-AI 红线区）
- P2：view_cards pptd 端 >4 卡不换行横向冲出版心；对齐 HTML 端
  .view-grid（repeat(4,1fr)）的 CSS grid 自动换行语义
"""

import os
import re
import sys

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer.diagram import flow, matrix, theme
from _renderer.diagram import pptd_emit as pe
from _renderer.spacing import snap

_ARROW = 'marker-end="url(#dgm-arr)"'


# ---- P1-10：parallel HTML 吞边 ----


def _parallel_elem(n_sources, after):
    return {"type": "diagram", "subtype": "parallel", "title": "汇聚",
            "sources": [{"label": f"源{i}"} for i in range(n_sources)],
            "merge": {"label": "汇总"}, "after": after}


def test_parallel_after_empty_keeps_gate_arrows():
    """after=[]（schema 合法）：每条「源→网关」箭头都不得被旧守卫吞掉。

    3 源 → 3 条源→网关曲线 + 1 条网关→merge（渲染层单独绘制）= 4；
    旧守卫下 merge（末节点）把 3 条源边全部吞掉，只剩 1。"""
    html = flow.render_html(_parallel_elem(3, []))
    assert html.count(_ARROW) == 4


def test_parallel_keeps_last_after_edge():
    """merge→after 链末段边（指向最后一个节点）不得被 bi>=len(nodes)-1 吞掉。

    2 源 + 2 after → 2 源→网关 + 1 网关→merge + merge→after[0]
    + after[0]→after[1] = 5；旧守卫把指向末节点的 x→after[1] 吞掉。"""
    html = flow.render_html(_parallel_elem(2, [{"label": "甲"}, {"label": "乙"}]))
    assert html.count(_ARROW) == 5


def test_parallel_double_end_edge_count_consistent():
    """双端一致：HTML 箭头数 = pptd 连线边数 + 1（网关→merge 单独绘制）。

    pptd 侧（flow.render_pptd）对 _layout_parallel 边集全量连线、无守卫，
    是本缺陷修复的正确基准。"""
    elem = _parallel_elem(3, [{"label": "后置"}])
    html = flow.render_html(elem)
    pptd_elems, _h = flow.render_pptd(elem, 0, 0, 1200)
    edge_ids = {m.group(0) for e in pptd_elems
                for m in [re.match(r"ar-\d+-\d+", e["elementId"])] if m}
    assert len(edge_ids) == 4  # 3 源→merge + merge→后置
    assert html.count(_ARROW) == len(edge_ids) + 1


# ---- P2：swimlane / cross_system 未声明 lane/system 显式告警 ----


def _swimlane_elem():
    return {"type": "diagram", "subtype": "swimlane", "title": "泳道",
            "lanes": [{"name": "研发"}, {"name": "交付"}],
            "steps": [
                {"label": "开发", "lane": "研发"},
                {"label": "联调", "lane": "研发部"},  # typo：未声明泳道
                {"label": "验收", "lane": "交付"},
            ]}


def test_swimlane_undeclared_lane_warns_and_drops(capsys):
    """引用未声明泳道的步骤：丢弃行为不变，但 HTML 端显式告警指名道姓。"""
    html = flow.render_html(_swimlane_elem())
    out = capsys.readouterr().out
    assert "联调" in out and "研发部" in out  # 指名步骤 + 未声明泳道
    assert "[diagram]" in out
    assert "联调" not in html  # 丢弃行为不变（历史口径）
    assert "开发" in html and "验收" in html  # 声明过的步骤照常渲染


def test_swimlane_warning_on_pptd_end_too(capsys):
    """pptd 端同样告警（共用 _layout_swimlane，两端各一次、口径一致）。"""
    nodes = flow.render_pptd(_swimlane_elem(), 0, 0, 1200)[0]
    out = capsys.readouterr().out
    assert "联调" in out and "研发部" in out
    node_ids = [e["elementId"] for e in nodes
                if re.fullmatch(r"nd-\d+", e["elementId"])]
    assert len(node_ids) == 2  # 仅 2 个声明过的步骤成节点


def test_cross_system_undeclared_system_warns_and_drops(capsys):
    """cross_system 同口径：未声明 system 的步骤丢弃 + 显式告警。"""
    elem = {"type": "diagram", "subtype": "cross_system", "title": "跨系统",
            "systems": [{"name": "计费"}, {"name": "开通"}],
            "steps": [
                {"label": "出账", "system": "计费"},
                {"label": "工单", "system": "计费系统"},  # typo：未声明系统
                {"label": "开通", "system": "开通"},
            ]}
    html = flow.render_html(elem)
    out = capsys.readouterr().out
    assert "工单" in out and "计费系统" in out
    assert "工单" not in html
    assert "出账" in html and "开通" in html


def test_declared_lanes_stay_silent(capsys):
    """负向对照：全部 lane 均已声明时不产生任何告警。"""
    elem = _swimlane_elem()
    elem["steps"][1]["lane"] = "研发"  # 修正 typo
    flow.render_html(elem)
    flow.render_pptd(elem, 0, 0, 1200)
    assert "[diagram]" not in capsys.readouterr().out


# ---- P1-11：raci / crud 空 cell 漏 f 前缀 ----


def test_raci_empty_cell_no_literal_theme_leak():
    """raci 空 cell 走 else 分支：不泄漏字面 {theme.，且解析出真实边框色。"""
    elem = {"type": "diagram", "subtype": "raci", "title": "RACI",
            "roles": ["业务方", "IT"],
            "tasks": [{"name": "需求确认",
                       "assignments": [{"role": "业务方", "type": "A"}]}]}
    html = matrix.render_html(elem)
    assert "{theme." not in html
    assert f"color:{theme.BORDER_STRONG}" in html


def test_crud_empty_cell_no_literal_theme_leak():
    """crud 空 cell（财务列无 ops）同样不泄漏字面 {theme.。"""
    elem = {"type": "diagram", "subtype": "crud", "title": "CRUD",
            "docs": ["订单"], "entities": ["库存", "财务"],
            "cells": [{"doc": "订单", "entity": "库存", "ops": ["C"]}]}
    html = matrix.render_html(elem)
    assert "{theme." not in html
    assert f"color:{theme.BORDER_STRONG}" in html


# ---- P2：view_cards pptd >4 卡折行 ----


def _view_cards(n_cards):
    return {"title": "四种视角",
            "cards": [{"icon": "◆", "perspective": f"视角{i}",
                       "headline": "30%", "detail": "说明"} for i in range(n_cards)]}


def _vc_card_bounds(elems):
    return [e["bounds"] for e in elems if re.fullmatch(r"vc-\d+", e["elementId"])]


def test_view_cards_pptd_wraps_beyond_four_cards():
    """>4 卡按 HTML 端 .view-grid 语义每行 4 张折行，不横向冲出版心。"""
    elems, total_h = pe.emit_chrome_pptd("view_cards", _view_cards(6), 0, 0, 1200)
    bounds = _vc_card_bounds(elems)
    assert len(bounds) == 6
    for b in bounds:
        assert b[0] + b[2] <= 1200  # 全部卡右缘不出版心（旧实现冲到 ~1808）
    tops = sorted({b[1] for b in bounds})
    assert len(tops) == 2  # 两行
    # 第二行 y = 首行 + 卡高 132 + 行距 14（行距复用列距，过 4px 网格吸附）
    assert tops[1] == snap(tops[0] + 132.0 + 14.0)
    assert [b[1] for b in bounds].count(tops[0]) == 4  # 首行 4 张
    assert total_h == pytest.approx(28.0 + 12.0 + 2 * 132.0 + 14.0)


def test_view_cards_pptd_within_four_cards_unchanged():
    """≤4 卡保持原单行布局与总高，不因折行逻辑回归。"""
    elems, total_h = pe.emit_chrome_pptd("view_cards", _view_cards(4), 0, 0, 1200)
    bounds = _vc_card_bounds(elems)
    assert len(bounds) == 4
    assert all(b[1] == snap(28.0 + 12.0) for b in bounds)  # 单行同一起点
    assert total_h == pytest.approx(172.0)
