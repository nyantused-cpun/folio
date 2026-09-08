# -*- coding: utf-8 -*-
"""全库审查报告 §五 P3「PPT 生产线」组修复回归（2026-09-06）。

覆盖：timeline vertical 空守卫、stat/kpi/pain_cards 空列表除零、ER 稀疏标签
双重呈现与绕行走廊越顶、waterfall 负 total 桥接 / bar 负值渲染、bct 脏数据
守卫、flow_rows 标签行 pptd 保留、intg/deploy elementId 索引范式。
最小 elem dict 直调 render/pptd 函数断言，不渲染真 PPT。
"""
import re

from _renderer.diagram import architecture, chart, flow, relationship, timeline
from _renderer.diagram import pptd_emit as pe

X, Y, W = 80, 130, 1120


def _ids(elems):
    return [e["elementId"] for e in elems]


def _bounds(elems):
    return [e["bounds"] for e in elems]


# ---- P3-1 timeline vertical 空 milestones ----

def test_vertical_timeline_empty_milestones_pptd():
    """空 milestones 早退 ([], 0)：否则竖轴 total=-gap 算出负高形状。"""
    elems, h = timeline.render_pptd({"subtype": "vertical", "milestones": []},
                                    X, Y, W)
    assert elems == []
    assert h == 0
    # 对照：非空路径竖轴照常渲染、高度为正（horizontal 空守卫既有行为不回归）
    elems2, h2 = timeline.render_pptd(
        {"subtype": "vertical", "milestones": [{"label": "M1", "date": "1月"}]},
        X, Y, W)
    assert h2 > 0
    assert "tlv-axis" in _ids(elems2)
    assert all(b[3] > 0 for b in _bounds(elems2))


# ---- P3-2 stat/kpi/pain_cards 空列表除零 ----

def test_stat_kpi_pain_empty_cards_pptd():
    """空 cards 早退 ([], 0)，不再均分宽除零。"""
    for fn in (pe.emit_stat_cards_pptd, pe.emit_kpi_cards_pptd,
               pe.emit_pain_cards_pptd):
        elems, h = fn({"cards": []}, X, Y, W, {})
        assert elems == []
        assert h == 0


# ---- P3-3 ER 稀疏模式标签双重呈现 ----

def test_er_sparse_label_single_presentation():
    """稀疏（≤4 条）模式逐边标签已呈现，不再重复收底部图例带。"""
    elem = {"subtype": "er_conceptual",
            "entities": [{"name": "客户"}, {"name": "订单"}],
            "relations": [{"from": "客户", "to": "订单",
                           "type": "one_to_many", "label": "下单"}]}
    elems, h = relationship._er_pptd(elem, X, Y, W)
    assert "er-legend" not in _ids(elems)
    lt = [e for e in elems if e["elementId"] == "er0-lt"]
    assert len(lt) == 1
    assert "下单" in lt[0]["content"]["text"]


def test_er_dense_legend_kept():
    """稠密（>4 条）图例模式照常收底部图例带（逐边标签本来就不画）。"""
    ents = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    pairs = [("A", "B"), ("B", "C"), ("A", "C"), ("B", "A"), ("C", "B")]
    elem = {"subtype": "er_conceptual", "entities": ents,
            "relations": [{"from": a, "to": b, "label": f"r{i}"}
                          for i, (a, b) in enumerate(pairs)]}
    elems, h = relationship._er_pptd(elem, X, Y, W)
    assert "er-legend" in _ids(elems)


# ---- P3-4 ER 绕行走廊越顶 ----

def test_er_detour_corridor_clamped_in_canvas():
    """首行框 × ri%4=3 走廊钳回画布内：全部元素 top 不高于图区起点。

    修复前第 4 条稀疏绕行的标签胶囊中心对齐走廊（viewBox y=0），上探
    17*scale 冲出画布（bounds y < 图顶 y）。
    """
    ents = [{"name": "A"}, {"name": "B"}]
    rels = [{"from": "A", "to": "B", "type": "one_to_many", "label": f"r{i}"}
            for i in range(4)]
    elems, h = relationship._er_pptd(
        {"subtype": "er_conceptual", "entities": ents, "relations": rels},
        X, Y, W)
    assert min(b[1] for b in _bounds(elems)) >= Y


# ---- P3-5 waterfall 负 total 桥接 / bar 负值渲染 ----

def _rects(html):
    return [(float(m[0]), float(m[1]), float(m[2]), float(m[3]))
            for m in re.findall(
                r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" '
                r'height="([\d.]+)"', html)]


def _bridge_ys(html):
    """桥接虚线的 y1（按出现顺序）。"""
    return [float(m) for m in re.findall(
        r'<line [^>]*?y1="([\d.]+)"[^>]*?stroke-dasharray="3,3"', html)]


def test_waterfall_negative_total_bridge_at_actual_level():
    """负 total 的桥接线画在实际结束水位（=柱底），不再错画在 0。"""
    html = chart.render_html({
        "subtype": "waterfall", "unit": "万元",
        "steps": [{"label": "期初", "value": -40, "kind": "total"},
                  {"label": "增量", "value": 60},
                  {"label": "期末", "value": 20, "kind": "total"}]})
    bars = _rects(html)
    bridges = _bridge_ys(html)
    assert len(bars) == 3 and len(bridges) == 2
    # 桥 1 跟住负 total 柱的底缘（柱跨 [value,0]，底缘即实际水位）
    assert abs(bridges[0] - (bars[0][1] + bars[0][3])) < 0.15
    # 桥 2 在正 delta 柱顶（既有正确行为不回归）
    assert abs(bridges[1] - bars[1][1]) < 0.15


def test_waterfall_positive_total_bridge_unchanged():
    """正 total 桥接仍在柱顶（正常输入路径零 diff）。"""
    html = chart.render_html({
        "subtype": "waterfall",
        "steps": [{"label": "A", "value": 100, "kind": "total"},
                  {"label": "B", "value": -30}]})
    bars = _rects(html)
    bridges = _bridge_ys(html)
    assert abs(bridges[0] - bars[0][1]) < 0.15


def test_bar_negative_value_rendered_below_baseline():
    """bar 负值翻转渲染（abs 高度 + 基线偏移），不再负高静默不渲染。"""
    html = chart.render_html({
        "subtype": "bar", "categories": ["营收", "利润"], "unit": "万元",
        "series": [{"name": "2025", "values": [100, -40]}]})
    bars = _rects(html)
    assert len(bars) == 2
    assert all(h_ > 0 for _, _, _, h_ in bars)  # 修复前负高 rect 不渲染
    # 正值柱顶仍在绘图区顶（正常路径零 diff），负值柱自基线向下、底缘≤绘图区底
    assert abs(bars[0][1] - 30.0) < 0.1
    assert bars[1][1] > bars[0][1] + bars[0][3] - 0.1   # 负柱顶在基线（低于正柱底）
    assert bars[1][1] + bars[1][3] <= 370.0 + 0.15      # 不冲出绘图区底
    assert "-40" in html                                 # 负值数据标签可见


# ---- P3-6 bct 非字符串 items / 空 children 碎条 ----

def test_bct_pptd_type_guards_and_empty_children():
    """非 dict 组/子项跳过、非字符串 items str() 化不崩；空组不产 1px 碎条。"""
    elem = {"subtype": "biz_capability_tree",
            "groups": [
                {"name": "G1", "children": [
                    {"name": "C1", "items": ["a", 2, {"k": 1}]},
                    "bad-str-child"]},
                "bad-str-group",
                {"name": "G2", "children": []}]}
    elems, h = relationship._bct_pptd(elem, X, Y, W)  # 不抛异常即过第一关
    # 无 1×1 碎条（修复前空组 group_h=-8 被 snap 兜成 1×1）
    assert not any(b[2] == 1 and b[3] == 1 for b in _bounds(elems))
    # 脏 items str() 化后正常拼文本（与 HTML 端 _esc 行为对齐；pptd text 惯例带尾 \n）
    items = [e for e in elems if e["elementId"] == "bct-g0-c0-i"][0]
    assert items["content"]["text"].rstrip("\n") == "a  2  {'k': 1}"
    # 空组钳到单行高，组名仍渲染（与 HTML 端空组渲染组名块对齐）
    g2 = [e for e in elems if e["elementId"] == "bct-g2"][0]
    assert g2["bounds"][3] > 10


# ---- P3-7 flow_rows 有标签无卡片行 ----

def test_flow_rows_label_only_row_kept_in_pptd():
    """有标签无卡片的行 pptd 保留（与 HTML 对齐），不再整行丢弃。"""
    elems, h = flow.render_pptd(
        {"subtype": "flow_rows",
         "rows": [{"label": "阶段一", "label_sub": "S1"},
                  {"cards": [{"label": "卡A", "badge": "1"}]}]},
        X, Y, W)
    ids = _ids(elems)
    assert "fr-lb0" in ids and "fr-lbd0" in ids       # 标签行保留
    assert "fr-c1-0" in ids                            # 卡片行不受影响
    lb = [e for e in elems if e["elementId"] == "fr-lb0"][0]
    assert "阶段一" in lb["content"]["text"]
    assert h >= 100                                    # 标签行(50) + 卡片行


# ---- P3-8 intg/deploy elementId 索引范式 ----

def test_intg_hub_duplicate_system_names_unique_ids():
    """hub 连线/系统卡 ID 用索引（phub 同范式）：同名系统不再重复 ID。"""
    elems, h = architecture.render_pptd(
        {"subtype": "integration", "hub": {"name": "ESB 总线"},
         "systems": [{"name": "ERP"}, {"name": "ERP"}, {"name": "CRM"}]},
        X, Y, W)
    ids = _ids(elems)
    assert len(ids) == len(set(ids))
    assert "hub-l-0" in ids and "hub-s-1" in ids and "hub-st-2" in ids


def test_deploy_duplicate_zone_names_unique_ids():
    """deployment 区/节点 ID 区名段改索引：同名区不再重复 ID。"""
    elems, h = architecture.render_pptd(
        {"subtype": "deployment",
         "zones": [{"name": "DMZ", "nodes": [{"name": "Web"}]},
                   {"name": "DMZ", "nodes": [{"name": "Web"}]}],
         "links": []},
        X, Y, W)
    ids = _ids(elems)
    assert len(ids) == len(set(ids))
    assert "dep-z-0" in ids and "dep-z-1" in ids
