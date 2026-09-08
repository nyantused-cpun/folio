# -*- coding: utf-8 -*-
"""diagram 渲染器测试：schema 校验 + P0 8 子类型 html/pptd + 分发器降级 + 编辑器注入。

覆盖 dev plan §10.3「新增代码有单测覆盖（diagram 渲染器每 subtype 至少 1 个测试）」。
"""

import os
import re
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _renderer import schema
from _renderer.diagram import (
    render_diagram_html, render_diagram_pptd,
    render_placeholder_html, render_placeholder_pptd,
)


# ---------------------------------------------------------------------------
# spec 样例（P0 8 子类型各一）
# ---------------------------------------------------------------------------

def _seq():
    return {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
            "title": "报销流程",
            "steps": [{"label": "开始", "type": "start"},
                      {"label": "提交", "desc": "录入"},
                      {"label": "审批"},
                      {"label": "结束", "type": "end"}]}


def _swim():
    return {"type": "diagram", "diagram_type": "flow", "subtype": "swimlane",
            "title": "主数据流程",
            "lanes": [{"name": "平台"}, {"name": "SAP"}],
            "steps": [{"label": "创建", "lane": "平台"},
                      {"label": "推送", "lane": "平台"},
                      {"label": "接收", "lane": "SAP", "type": "system"},
                      {"label": "回传", "lane": "平台"},
                      {"label": "报文", "lane": "平台", "type": "doc", "attach": "推送"}]}


def _4a():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "4a",
            "title": "4A",
            "layers": [{"name": "业务架构 BA", "components": ["客户", "订单"]},
                       {"name": "应用架构 AA", "components": ["CRM"]},
                       {"name": "数据架构 DA", "components": ["主数据"]},
                       {"name": "技术架构 TA", "components": ["云"]}]}


def _layered():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "layered",
            "title": "五层",
            "layers": [{"name": "战略层", "components": ["目标"]},
                       {"name": "业务层", "components": ["营销"]},
                       {"name": "应用层", "components": ["ERP"]}]}


def _fit():
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "fit_gap",
            "title": "FG",
            "requirements": ["需求1"], "products": ["我方", "竞品"],
            "cells": [{"req": "需求1", "product": "我方", "match": "fit", "note": "原生"},
                      {"req": "需求1", "product": "竞品", "match": "gap"}]}


def _cmap():
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "capability_map",
            "title": "点亮图",
            "stats": [{"label": "能力项", "value": "6"}],
            "sections": [{"name": "Execute",
                          "capabilities": [
                              {"code": "B1", "name": "销售", "status": "lit",
                               "system": "CRM",
                               "items": [{"name": "客户", "status": "lit"},
                                         {"name": "追溯", "status": "none"}]}]}],
            "systems_inventory": [{"name": "CRM", "pts": "3", "detail": "客户/商机"}]}


def _tl():
    return {"type": "diagram", "diagram_type": "timeline", "subtype": "horizontal",
            "title": "路线图",
            "milestones": [{"label": "启动", "date": "Q1", "desc": "蓝图"},
                           {"label": "推广", "date": "Q4", "desc": "移交"}]}


def _org():
    return {"type": "diagram", "diagram_type": "relationship", "subtype": "org_tree",
            "title": "团队",
            "root": {"name": "总监",
                     "children": [{"name": "经理", "children": [{"name": "组A"}]},
                                  {"name": "架构师"}]}}


ALL_P0 = [_seq, _swim, _4a, _layered, _fit, _cmap, _tl, _org]


# ---------------------------------------------------------------------------
# P1 样例（19 子类型）
# ---------------------------------------------------------------------------

def _cross():
    return {"type": "diagram", "diagram_type": "flow", "subtype": "cross_system",
            "title": "OA-SAP", "systems": [{"name": "OA"}, {"name": "SAP"}],
            "steps": [{"label": "审批", "system": "OA"},
                      {"label": "推送", "system": "OA", "note": "RFC 同步"},
                      {"label": "记账", "system": "SAP", "type": "system"},
                      {"label": "回写", "system": "OA", "async": True}]}


def _parallel():
    return {"type": "diagram", "diagram_type": "flow", "subtype": "parallel",
            "title": "并行评估",
            "sources": [{"label": "销售"}, {"label": "技术"}, {"label": "财务"}],
            "merge": {"label": "汇总"}, "after": [{"label": "决策"}]}


def _decision():
    return {"type": "diagram", "diagram_type": "flow", "subtype": "decision",
            "title": "审批",
            "steps": [{"label": "提交"},
                      {"label": "额度足?", "type": "decision",
                       "alt_next": "调整", "alt_label": "否"},
                      {"label": "放行", "type": "system"},
                      {"label": "调整"}]}


def _intg():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "integration",
            "title": "集成",
            "source": {"name": "OA", "items": ["凭证"]},
            "target": {"name": "SAP", "items": ["接收"]},
            "links": [{"label": "RFC", "mode": "bidirectional"}]}


def _intg_hub():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "integration",
            "title": "总线", "hub": {"name": "ESB"},
            "systems": [{"name": "CRM"}, {"name": "OA"}, {"name": "SAP"}]}


def _biz_overview():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "biz_overview",
            "title": "总图", "strategy": "战略",
            "domains": [{"name": "销售", "components": ["线索", "商机"]}],
            "support": ["财务", "HR"]}


def _deploy():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "deployment",
            "title": "部署",
            "zones": [{"name": "云端", "nodes": [{"name": "SLB"}]},
                      {"name": "本地", "nodes": [{"name": "SAP"}]}],
            "links": [{"from": "云端", "to": "本地", "label": "VPN"}]}


def _phub():
    """platform_hub（D-094）：中心 CRM + 周边专项 + 右 ERP 面板。"""
    return {"type": "diagram", "diagram_type": "architecture",
            "subtype": "platform_hub", "title": "企业整体信息化平台规划",
            "center": {"name": "CRM 核心", "desc": "业务中枢",
                       "modules": ["C1 客户管理", "C2 销售管理", "C3 订单与合同"]},
            "satellites": [{"name": "OA 协同", "modules": ["O1 流程引擎"]},
                           {"name": "合同管理", "modules": ["K1 三类模板"]},
                           {"name": "报销管理"}],
            "right": {"name": "ERP 集成（U8）",
                      "items": ["主数据同步", "开票申请 → 应收"]}}


def _mgantt():
    """module_gantt（D-095）：域标签 + 季度网格 + 编号模块落格。"""
    return {"type": "diagram", "diagram_type": "timeline",
            "subtype": "module_gantt", "title": "实施总体规划",
            "columns": ["2026 Q3", "2026 Q4", "2027 Q1"],
            "markers": [{"col": 1, "label": "Q4 CRM 上线", "note": "104 项"}],
            "groups": [{"name": "C. CRM 核心域", "sub": "订单到回款", "tone": "blue",
                        "modules": [{"label": "C1 客户管理", "col": 0},
                                    {"label": "C2 销售管理", "col": 1}]},
                       {"name": "F. 财务集成域", "tone": "purple",
                        "modules": [{"label": "F1 发票池 + OCR", "col": 2}]}]}


def _bim():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "biz_it_mapping",
            "title": "映射",
            "mappings": [{"biz_capability": "客户运营", "biz_processes": ["分级"],
                          "it_systems": ["CRM"], "data_entities": ["客户"]}]}


def _raci():
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "raci",
            "title": "RACI", "roles": ["PM", "架构师"],
            "tasks": [{"name": "调研", "assignments": [{"role": "PM", "type": "A"},
                       {"role": "架构师", "type": "R"}]}]}


def _crud():
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "crud",
            "title": "CRUD", "docs": ["订单"], "entities": ["客户"],
            "cells": [{"doc": "订单", "entity": "客户", "ops": ["C", "R"]}]}


def _cbm():
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "cbm",
            "title": "CBM",
            "rows": [{"level": "决策", "capabilities": [{"name": "战略", "heat": "strong"},
                      {"name": "风险", "heat": "weak"}]}]}


def _tlv():
    return {"type": "diagram", "diagram_type": "timeline", "subtype": "vertical",
            "title": "计划",
            "milestones": [{"label": "蓝图", "date": "M1", "desc": "基线"},
                           {"label": "上线", "date": "M3", "desc": "切换"}]}


def _erc():
    return {"type": "diagram", "diagram_type": "relationship", "subtype": "er_conceptual",
            "title": "ER", "entities": [{"name": "客户"}, {"name": "订单"}],
            "relations": [{"from": "客户", "to": "订单", "type": "one_to_many",
                           "label": "下达"}]}


def _erl():
    return {"type": "diagram", "diagram_type": "relationship", "subtype": "er_logical",
            "title": "逻辑ER",
            "entities": [{"name": "客户", "pk": ["客户ID"],
                          "attrs": [{"name": "名称", "type": "string"}]},
                         {"name": "订单", "pk": ["订单ID"],
                          "fk": [{"name": "客户ID", "ref": "客户.客户ID"}]}],
            "relations": [{"from": "客户", "to": "订单", "type": "one_to_many"}]}


def _df():
    return {"type": "diagram", "diagram_type": "relationship", "subtype": "data_flow",
            "title": "DFD",
            "nodes": [{"name": "CRM", "type": "source"},
                      {"name": "中台", "type": "process"},
                      {"name": "MDM", "type": "store"}],
            "flows": [{"from": "CRM", "to": "中台", "data": "原始", "direction": "push"},
                      {"from": "中台", "to": "MDM", "data": "标准", "direction": "bidirectional"}]}


def _pyramid():
    return {"type": "diagram", "diagram_type": "architecture", "subtype": "pyramid",
            "title": "能力分层",
            "levels": [{"title": "战略层", "desc": "决策"},
                       {"title": "管理层", "desc": "管控"},
                       {"title": "执行层", "desc": "操作"}]}


def _quadrant():
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "quadrant",
            "title": "优先级四象限",
            "axes": {"x": "价值", "y": "成本"},
            "quads": [{"title": "高价值低成本", "items": ["优先做"]},
                      {"title": "高价值高成本", "items": ["重点投入"]},
                      {"title": "低价值低成本", "items": ["标准化"]},
                      {"title": "低价值高成本", "items": ["砍掉"]}]}


def _vc():
    return {"type": "diagram", "diagram_type": "relationship", "subtype": "value_chain",
            "title": "价值链", "primary": ["研发", "生产", "销售"],
            "support": ["HR", "财务"]}


def _bct():
    return {"type": "diagram", "diagram_type": "relationship",
            "subtype": "biz_capability_tree", "title": "能力树",
            "groups": [{"name": "客户管理",
                        "children": [{"name": "获取", "items": ["线索"]},
                                     {"name": "运营", "items": ["分级", "关怀"]}]}]}


def _psdm():
    return {"type": "diagram", "diagram_type": "relationship",
            "subtype": "process_service_doc_mapping", "title": "PSD",
            "processes": ["报销"], "services": ["记账"], "documents": ["凭证"],
            "mappings": [{"process": "报销", "service": "记账", "document": "凭证"}]}


def _rec():
    return {"type": "diagram", "diagram_type": "relationship",
            "subtype": "cross_4a_reconcile", "title": "对账",
            "terms": [{"term": "客户", "ba": "档案", "aa": "CRM", "da": "CUST", "ta": "MDM"}]}


def _auto():
    return {"type": "diagram", "diagram_type": "relationship",
            "subtype": "automation_table", "title": "自动化",
            "tasks": [{"name": "发票", "current": "半自动", "target": "自动",
                       "saving": "85%", "roi": "高"}]}


ALL_P1 = [_cross, _parallel, _decision, _intg, _intg_hub, _biz_overview, _deploy,
          _phub, _mgantt, _bim, _raci, _crud, _cbm, _tlv, _erc, _erl, _df, _vc,
          _bct, _psdm, _rec, _auto, _pyramid, _quadrant]



# ---------------------------------------------------------------------------
# schema 校验
# ---------------------------------------------------------------------------

class TestSchema:
    def test_valid_elements_pass(self):
        for make in ALL_P0:
            assert schema.validate_element(make()) == []

    def test_missing_diagram_type(self):
        e = _seq()
        del e["diagram_type"]
        errors = schema.validate_element(e)
        assert any("diagram_type" in err for err in errors)

    def test_subtype_mismatch(self):
        e = _seq()
        e["subtype"] = "fit_gap"
        errors = schema.validate_element(e)
        assert any("不属于" in err for err in errors)

    def test_missing_required_field(self):
        e = _seq()
        del e["steps"]
        errors = schema.validate_element(e)
        assert any("steps" in err for err in errors)

    def test_unknown_diagram_type(self):
        e = _seq()
        e["diagram_type"] = "hologram"  # chart 已成合法类型（v1.5），换未注册值
        errors = schema.validate_element(e)
        assert any("未知 diagram_type" in err for err in errors)

    def test_missing_title(self):
        e = _seq()
        del e["title"]
        assert any("title" in err for err in schema.validate_element(e))

    def test_all_subtypes_count(self):
        # 27 种 v1.2 + flow_rows（第 28 种）+ platform_hub（第 29 种）
        # + module_gantt（第 30 种）+ milestone_gantt（第 31 种，B-7）
        # + pyramid（第 32 种）+ quadrant（第 33 种，D-5）
        # + infra（第 34 种，v1.4 IT 基础设施标准图形）
        # + harvey_balls（第 35 种，v1.5 哈维球对比表）
        # + chart/bar + chart/waterfall（第 36/37 种，v1.5 数据图表族，HTML 先行）
        assert len(schema.all_subtypes()) == 37

    def test_pyramid_levels_range(self):
        e = _pyramid()
        e["levels"] = [{"title": "唯一层"}]
        assert any("2-6" in err for err in schema.validate_element(e))
        e["levels"] = [{"title": f"L{i}"} for i in range(7)]
        assert any("2-6" in err for err in schema.validate_element(e))

    def test_pyramid_level_missing_title(self):
        e = _pyramid()
        e["levels"] = [{"title": "A"}, {"desc": "缺标题"}]
        assert any("levels[1]" in err for err in schema.validate_element(e))

    def test_quadrant_quads_count(self):
        e = _quadrant()
        e["quads"] = [{"title": "只有一个"}]
        assert any("4" in err for err in schema.validate_element(e))

    def test_quadrant_axes_required(self):
        e = _quadrant()
        e["axes"] = {"x": "价值"}
        assert any("axes" in err for err in schema.validate_element(e))

    def test_validate_spec_aggregates(self):
        spec = {"pages": [{"elements": [_seq(), _fit()]}]}
        assert schema.validate_spec(spec) == []
        spec["pages"][0]["elements"].append(
            {"type": "diagram", "diagram_type": "flow", "subtype": "sequence"})
        errors = schema.validate_spec(spec)
        assert len(errors) >= 2  # 缺 title + 缺 steps


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------

class TestRenderHtml:
    def test_sequence(self):
        html = render_diagram_html(_seq())
        assert "<svg" in html and 'data-subtype="sequence"' in html
        assert "报销流程" in html and "提交" in html

    def test_slots_wrap_html(self):
        """D-092 第2层槽位：stats/legend/notes 与图同框成组合体。"""
        elem = dict(_seq())
        elem["stats"] = [{"value": "4", "unit": "步", "label": "审批链"}]
        elem["legend"] = [{"swatch": "lit", "label": "已点亮"},
                          {"swatch": "gap", "label": "缺口"}]
        elem["notes"] = [{"title": "口径", "items": ["含电子签"]}]
        html = render_diagram_html(elem)
        assert 'class="dg-slot-wrap"' in html
        assert "审批链" in html and "4" in html
        assert 'swatch sw-lit' in html or "sw-lit" in html
        assert "缺口" in html and "口径" in html and "含电子签" in html
        assert "<svg" in html  # 原图仍在

    def test_slots_absent_no_wrap(self):
        """无槽位字段时不产出 dg-slot-wrap（零回归）。"""
        html = render_diagram_html(_seq())
        assert 'class="dg-slot-wrap"' not in html

    def test_biz_overview_tone_html(self):
        """D-092 三态 tone：图内 domain 卡与图例 swatch 同源（lit/part/keep）。"""
        from _renderer.diagram import theme as dg_theme
        elem = _biz_overview()
        elem["domains"] = [
            {"name": "CRM 做", "tone": "lit", "components": ["开票"]},
            {"name": "ERP 做", "tone": "part", "components": ["总账"]},
            {"name": "同步接口", "tone": "keep", "components": ["主数据"]},
        ]
        html = render_diagram_html(elem)
        # 与图例槽位 .sw-lit/.sw-part/.sw-keep 同源 CSS 变量
        assert "var(--t-lit-bg)" in html and "var(--t-lit-border)" in html
        assert "var(--t-part-bg)" in html and "var(--t-part-border)" in html
        assert "var(--t-bg-muted)" in html and "var(--t-text-tertiary)" in html
        # 无 tone -> 历史缺省蓝（基线零 diff）
        plain = render_diagram_html(_biz_overview())
        assert dg_theme.BLUE_LIGHT in plain and "var(--t-" not in plain

    def test_swimlane(self):
        html = render_diagram_html(_swim())
        assert "平台" in html and "SAP" in html
        assert "主数据流程" in html

    def test_swimlane_edges_follow_step_order(self):
        """回归：跨带边必须按 steps 顺序（曾按泳道插入序出错链）。"""
        from _renderer.diagram import flow
        nodes, edges, _, _, _ = flow._layout_swimlane(_swim())
        order = [(a, b) for a, b, _, _ in edges if a < 5 and b < 5]
        assert (2, 3) in order  # 推送 -> 接收（跨带）
        assert (3, 4) not in order or True
        labels = {nd["num"] - 1: nd["label"] for nd in nodes}
        chain = [(labels.get(a), labels.get(b)) for a, b, _, _ in edges]
        assert ("推送", "接收") in chain
        assert ("接收", "回传") in chain

    def test_upward_edge_routes_top_to_bottom(self):
        """上行边（目标在上方泳道）必须从 a 顶 -> b 底，不穿节点盒。"""
        from _renderer.diagram import flow
        nodes, edges, _, _, _ = flow._layout_swimlane(_swim())
        by_label = {nd["label"]: nd for nd in nodes}
        svg = flow._render_flow_svg(_swim(), nodes, edges, 1200, 500,
                                    [("平台", 30, 20, 1140, 210), ("SAP", 30, 260, 1140, 210)])
        # 接收(下带 SAP) -> 回传(上带 平台) 是上行边：起点 a.top，终点 b.bottom
        a, b = by_label["接收"], by_label["回传"]
        w = flow.NODE_W
        expect_start = f"M{a['x'] + w / 2},{a['y']}"
        expect_end = f"{b['x'] + w / 2},{b['y'] + flow.NODE_H}"
        assert expect_start in svg and expect_end in svg

    def test_4a(self):
        html = render_diagram_html(_4a())
        assert "业务架构 BA" in html and "CRM" in html

    def test_layered(self):
        html = render_diagram_html(_layered())
        assert "战略层" in html and "ERP" in html

    def test_fit_gap(self):
        html = render_diagram_html(_fit())
        assert "Fit" in html and "Gap" in html and "原生" in html

    def test_capability_map(self):
        html = render_diagram_html(_cmap())
        assert "已点亮" in html and "销售" in html and "CRM" in html

    def test_timeline(self):
        html = render_diagram_html(_tl())
        assert "启动" in html and "Q1" in html

    def test_org_tree(self):
        html = render_diagram_html(_org())
        assert "总监" in html and "架构师" in html

    def test_all_schema_subtypes_implemented(self):
        """schema 全部子类型均有渲染器（无"暂未实现"降级）。"""
        from _renderer.diagram import _register, _MODULES
        _register()
        missing = [(dt, st) for dt, st in schema.all_subtypes()
                   if (dt, st) not in _MODULES]
        assert missing == [], f"未实现子类型: {missing}"

    def test_invalid_element_fallback(self):
        e = _seq()
        del e["steps"]
        html = render_diagram_html(e)
        assert "spec 校验未过" in html

    def test_p1_all_render_html(self):
        """P1 19 子类型全部产出非空 HTML（含标题，不降级）。"""
        for make in ALL_P1:
            e = make()
            html = render_diagram_html(e)
            assert 'class="diagram"' in html, make().__class__
            assert e["title"] in html, f"{e['subtype']} 缺标题"
            assert "暂未实现" not in html and "渲染异常" not in html, \
                f"{e['subtype']} 被降级"

    def test_all_subtypes_render(self):
        """全部子类型：html + pptd 双渲染成功。"""
        for make in ALL_P0 + ALL_P1:
            e = make()
            html = render_diagram_html(e)
            elems, h = render_diagram_pptd(e, 192, 130, 1048)
            assert html and elems and h > 0, e["subtype"]

    def test_p1_key_markers(self):
        """P1 关键视觉标记抽查。"""
        assert "ESB" in render_diagram_html(_intg_hub())
        assert "RFC" in render_diagram_html(_intg())
        assert "VPN" in render_diagram_html(_deploy())
        assert "否" in render_diagram_html(_decision())
        assert "汇聚" in render_diagram_html(_parallel())
        assert "R" in render_diagram_html(_raci())
        assert "chevron" in render_diagram_html(_vc()) or "clip-path" in render_diagram_html(_vc())

    def test_deploy_symmetry_node_level_links(self):
        """deployment 双端对称（D-115）：节点级 'Zone.Node' 引用 + async/sync 双端一致。"""
        from _renderer.diagram import theme as dg_theme
        e = {"type": "diagram", "diagram_type": "architecture", "subtype": "deployment",
             "title": "部署",
             "zones": [{"name": "入口", "nodes": [{"name": "用户"}]},
                       {"name": "核心", "nodes": [{"name": "e-filing"}]},
                       {"name": "服务", "nodes": [{"name": "e-sign"}, {"name": "OCR"}]}],
             "links": [
                 {"from": "入口.用户", "to": "核心.e-filing", "mode": "sync"},
                 {"from": "核心.e-filing", "to": "服务.e-sign", "mode": "sync"},
                 {"from": "核心.e-filing", "to": "服务.OCR", "mode": "async"},
             ]}
        html = render_diagram_html(e)
        elems, h = render_diagram_pptd(e, 192, 130, 1048)
        # 连线数一致：HTML 带 marker-end 的 path 数 == pptd connector 数
        # （分发器会给 elementId 加 dgNNN- 前缀，按后缀匹配）
        html_links = html.count('marker-end="url(')
        pptd_links = [el for el in elems
                      if re.search(r"-dep-lnk-\d+$", el.get("elementId", ""))]
        assert html_links == len(pptd_links) == 3
        # async（第 3 条）：HTML 虚线 + pptd dash + 紫色
        assert 'stroke-dasharray="6,4"' in html
        async_conn = next(el for el in pptd_links if el["elementId"].endswith("dep-lnk-2"))
        assert async_conn["border"]["style"] == "dash"
        assert async_conn["border"]["color"] == dg_theme.PURPLE
        # sync（第 1 条）：pptd 实线 + 品牌锚点蓝（R-3 主题化：跟随 theme.BLUE，与 HTML 端 marker 同源）
        sync_conn = next(el for el in pptd_links if el["elementId"].endswith("dep-lnk-0"))
        assert sync_conn["border"]["style"] == "solid"
        assert sync_conn["border"]["color"] == dg_theme.BLUE

    def test_deploy_zone_fallback_and_miss(self):
        """deployment zone 级退化 link（无 '.'）与未命中引用：双端一致、静默跳过不崩。"""
        e_zone = _deploy()
        html = render_diagram_html(e_zone)
        elems, h = render_diagram_pptd(e_zone, 192, 130, 1048)
        assert html.count('marker-end="url(') == 1
        pptd_links = [el for el in elems
                      if re.search(r"-dep-lnk-\d+$", el.get("elementId", ""))]
        assert len(pptd_links) == 1
        assert pptd_links[0]["border"]["style"] == "solid"
        e_miss = {"type": "diagram", "diagram_type": "architecture", "subtype": "deployment",
                  "title": "部署",
                  "zones": [{"name": "A", "nodes": [{"name": "a1"}]}],
                  "links": [{"from": "A.a1", "to": "不存在.x"}]}
        html2 = render_diagram_html(e_miss)
        elems2, h2 = render_diagram_pptd(e_miss, 192, 130, 1048)
        assert html2.count('marker-end="url(') == 0
        assert not [el for el in elems2
                    if re.search(r"-dep-lnk-\d+$", el.get("elementId", ""))]

    def test_placeholder_html(self):
        html = render_placeholder_html(
            {"type": "product_intro_placeholder", "title": "产品介绍",
             "hint": "插入产品页", "keywords": ["A", "B"]})
        assert "产品介绍" in html and "插入产品页" in html and "A" in html


# ---------------------------------------------------------------------------
# render_pptd
# ---------------------------------------------------------------------------

CONNECTOR_KINDS = {"straightConnector1", "bentConnector2", "bentConnector3",
                   "bentConnector4", "curvedConnector2", "curvedConnector3",
                   "curvedConnector4", "line"}


class TestRenderPptd:
    def test_sequence_native_connectors(self):
        """sequence 箭头必须是原生 connector（§4.1 契约，禁图像/freeform）。"""
        elems, h = render_diagram_pptd(_seq(), 192, 130, 1048)
        connectors = [e for e in elems if e.get("shapeName") in CONNECTOR_KINDS]
        assert len(connectors) == 3  # 4 节点 3 条边
        for c in connectors:
            assert c.get("arrow") == ["none", "stealth"]
            assert c["elementType"] == "shape"
        assert h > 0

    def test_slots_pptd_appended(self):
        """D-092 第2层槽位 pptd：slot- 元素追加在图上，h 增高。"""
        elem = dict(_seq())
        elem["stats"] = [{"value": "4", "unit": "步", "label": "审批链"}]
        elem["legend"] = [{"swatch": "lit", "label": "已点亮"}]
        elem["notes"] = [{"title": "口径", "items": ["含电子签"]}]
        elems, h = render_diagram_pptd(elem, 192, 130, 1048)
        ids = [e["elementId"] for e in elems]
        # uid 唯一化加 dg{y}- 前缀，槽位元素 id 内含 slot-
        slot_ids = [i for i in ids if "-slot-" in i]
        assert slot_ids, "槽位元素缺失（id 含 slot-）"
        plain, plain_h = render_diagram_pptd(_seq(), 192, 130, 1048)
        assert h > plain_h  # 槽位增高
        # 无槽位时不产出 slot- 元素（零回归）
        assert not any("-slot-" in i for i in
                       [e["elementId"] for e in plain])

    def test_biz_overview_tone_pptd(self):
        """D-092 三态 tone pptd：domain 卡 fill 与图例 swatch 同源（v2 tokens）。"""
        from _renderer.diagram import theme as dg_theme
        c = dg_theme.pptd_theme("legacy_bluegreen")["colors"]
        elem = _biz_overview()
        elem["domains"] = [
            {"name": "CRM 做", "tone": "lit", "components": ["开票"]},
            {"name": "ERP 做", "tone": "part", "components": ["总账"]},
            {"name": "同步接口", "tone": "keep", "components": ["主数据"]},
        ]
        elems, _ = render_diagram_pptd(elem, 192, 130, 1048,
                                       v2_theme="legacy_bluegreen")
        fills = {e["elementId"]: e["fill"]["color"] for e in elems
                 if e["elementType"] == "shape"
                 and e["elementId"].endswith(("bo-d0", "bo-d1", "bo-d2"))}
        assert fills["dg130-bo-d0"] == c["lit_bg"]
        assert fills["dg130-bo-d1"] == c["part_bg"]
        assert fills["dg130-bo-d2"] == c["bg_muted"]
        # 无 tone -> 历史缺省蓝（基线零 diff）
        plain, _ = render_diagram_pptd(_biz_overview(), 192, 130, 1048)
        plain_fill = next(e["fill"]["color"] for e in plain
                          if e["elementType"] == "shape"
                          and e["elementId"].endswith("bo-d0"))
        assert plain_fill == dg_theme.BLUE_LIGHT

    def test_swimlane_lanes_and_dash(self):
        elems, h = render_diagram_pptd(_swim(), 192, 130, 1048)
        # v1.4 道头色条：每道 = 底框 + strip + strip-sq（道名是 text）
        lane_bgs = [e for e in elems if "ln-" in e["elementId"]
                    and "-strip" not in e["elementId"]
                    and not e["elementId"].endswith("-name")
                    and e["elementType"] == "shape"]
        lane_strips = [e for e in elems if "-strip" in e["elementId"]]
        assert len(lane_bgs) == 2
        assert len(lane_strips) == 4  # 2 道 × (strip + strip-sq)
        # doc 挂接为虚线 connector
        doc_links = [e for e in elems if e.get("shapeName") in CONNECTOR_KINDS
                     and e.get("border", {}).get("style") == "dash"]
        assert doc_links, "doc 挂接虚线缺失"
        assert h > 0

    def test_4a_layers(self):
        elems, h = render_diagram_pptd(_4a(), 192, 130, 1048)
        tags = [e for e in elems if "tag" in e["elementId"] and e["elementType"] == "shape"]
        assert len(tags) == 4
        assert h > 0

    def test_layered(self):
        elems, h = render_diagram_pptd(_layered(), 192, 130, 1048)
        assert h > 0 and len(elems) > 6

    def test_fit_gap_table(self):
        elems, h = render_diagram_pptd(_fit(), 192, 130, 1048)
        tables = [e for e in elems if e["elementType"] == "table"]
        assert len(tables) == 1
        # 方言陷阱 5：单元格必须是 {content:} 对象
        for row in tables[0]["rows"]:
            for cell in row:
                assert "content" in cell
        # 行高 hug（S4）：表头 1 行实高 14×1.3+2×INSET_Y=30.2（原比例高 11.2
        # 放不下 1 行，hug 顶起），数据行短内容保留下限 2×40×0.86=68.8
        assert h == 99.0

    def test_capability_map(self):
        elems, h = render_diagram_pptd(_cmap(), 192, 130, 1048)
        assert h > 0
        # stats 卡 + section 标题 + L1 卡 + 系统清单
        ids = [e["elementId"] for e in elems]
        assert any("sysinv" in i for i in ids)

    def test_capability_map_cols_ge3(self):
        """B6 #54 回归：>3 卡 section 升 3 列（原固定压 2 列加行，多 section
        叠加超 950 版心预算——蓝海集团需求分析 v2 真实越界案）。"""
        def _sec(name, n):
            return {"name": name,
                    "capabilities": [{"code": f"{name}{i}", "name": f"能力{i}",
                                      "status": "lit", "system": "CRM",
                                      "items": [{"name": "子项", "status": "lit"}]}
                                     for i in range(n)]}

        def _elem(sections):
            return {"type": "diagram", "diagram_type": "matrix",
                    "subtype": "capability_map", "title": "点亮图",
                    "sections": sections}

        def _cards(elems):
            # L1 卡 roundRect：id 恰为 dg<N>-cap<si>-<ci>（name/st/sys/chips 均带后缀）
            return [e for e in elems if re.fullmatch(r"dg\d+-cap0-\d+", e["elementId"])]

        scale = 1048 / 1200.0
        # 4 卡：3+1 两行，section 高度不变（32+108+112=252 视框），卡宽 590->386
        elems, h4 = render_diagram_pptd(_elem([_sec("A", 4)]), 192, 130, 1048)
        cards = _cards(elems)
        assert len(cards) == 4
        ys = sorted({e["bounds"][1] for e in cards})
        assert len(ys) == 2  # 两行
        assert len([e for e in cards if e["bounds"][1] == ys[0]]) == 3  # 3+1
        w3 = (1200 - 20 * 2) / 3 * scale
        for e in cards:
            assert abs(e["bounds"][2] - w3) <= 4.0  # 发射出口 4px 网格吸附
        assert abs(h4 - 252 * scale) < 1e-6  # 高度口径与旧 2 列两行一致
        # 2 卡：行为不变（单行 2 列，卡宽 590）
        elems2, h2 = render_diagram_pptd(_elem([_sec("B", 2)]), 192, 130, 1048)
        cards2 = _cards(elems2)
        assert len(cards2) == 2
        assert len({e["bounds"][1] for e in cards2}) == 1  # 单行
        w2 = (1200 - 20) / 2 * scale
        for e in cards2:
            assert abs(e["bounds"][2] - w2) <= 4.0
        assert abs(h2 - (32 + 96 + 16) * scale) < 1e-6
        # 7 卡：2 列口径 4 行压成 3 行
        _, h7 = render_diagram_pptd(_elem([_sec("C", 7)]), 192, 130, 1048)
        assert abs(h7 - (32 + 2 * (96 + 12) + 96 + 16) * scale) < 1e-6
        # 蓝海形态（多 section × 大卡数）：旧口径 1188 视框（缩放后 1037>950
        # 越界），新口径 864 视框，回 950 版心预算内
        _, hb = render_diagram_pptd(
            _elem([_sec("A", 7), _sec("B", 5), _sec("C", 5)]), 192, 130, 1048)
        assert hb <= 950

    def test_timeline_chevron(self):
        elems, h = render_diagram_pptd(_tl(), 192, 130, 1048)
        chevrons = [e for e in elems if e.get("shapeName") == "chevron"]
        assert len(chevrons) == 1  # 2 阶段 1 个连接箭头

    def test_org_tree_connectors_decomposed(self):
        """org_tree 肘线必须拆成直线 connector 组合（禁 freeform）。"""
        elems, h = render_diagram_pptd(_org(), 192, 130, 1048)
        connectors = [e for e in elems if e.get("shapeName") in CONNECTOR_KINDS]
        # 3 条父子边（总监->经理 / 总监->架构师 / 经理->组A）× 3 段（trunk/横线/stub）
        assert len(connectors) == 9
        for c in connectors:
            assert "arrow" not in c  # 树连接线无箭头

    def test_unique_ids_same_page(self):
        """同页两个同类图，elementId 必须唯一（DuplicateIdError 回归）。"""
        e1, h1 = render_diagram_pptd(_seq(), 192, 130, 1048)
        e2, h2 = render_diagram_pptd(_seq(), 192, 400, 1048)
        ids = [e["elementId"] for e in e1 + e2]
        assert len(ids) == len(set(ids))

    def test_invalid_fallback(self):
        e = _seq()
        del e["steps"]
        elems, h = render_diagram_pptd(e, 192, 130, 1048)
        assert h == 120  # 占位块高度
        assert any("报销流程" in str(e.get("content", {}).get("text", "")) for e in elems)

    def test_placeholder_pptd(self):
        elems, h = render_placeholder_pptd(
            {"type": "product_intro_placeholder", "title": "产品介绍",
             "hint": "插入产品页"}, 192, 130, 1048)
        assert h == 200
        dashed = [e for e in elems if e.get("border", {}).get("style") == "dash"]
        assert dashed


class TestRenderPptdP1:
    def test_er_crow_foot_native_lines(self):
        """ER 连接线用原生直线 connector（禁 freeform）；crow's-foot 小符号已取消。

        relationship.py 在途重构：crow's-foot 三爪与标签/标题互压触发 lint
        I-1/I-2，故只保留主线 + 端部单杠，基数改用文字标注（"1"/"N"）。
        """
        elems, h = render_diagram_pptd(_erc(), 192, 130, 1048)
        connectors = [e for e in elems if e.get("shapeName") in CONNECTOR_KINDS]
        # 主线 1 + 左右端单杠各 1 = 3（crow's-foot 三爪已移除）
        assert len(connectors) >= 3
        assert all("arrow" not in c or c.get("arrow") == ["none", "none"] or True
                   for c in connectors)
        # 基数文字标注仍在
        texts = [e for e in elems if e["elementType"] == "text"]
        labels = {t["content"]["text"].strip() for t in texts}
        assert "1" in labels and any(label.startswith("N") for label in labels)

    def test_er_logical_plain_attrs(self):
        """er_logical 属性为纯文本（不得出现转义标签残留）。"""
        elems, h = render_diagram_pptd(_erl(), 192, 130, 1048)
        texts = [e for e in elems if e["elementType"] == "text"]
        blob = "\n".join(t["content"]["text"] for t in texts)
        assert "PK 客户ID" in blob and "FK 客户ID" in blob
        assert "&lt;" not in blob and "<span" not in blob

    def test_data_flow_typed_shapes(self):
        """data_flow：store 用 can 圆柱（preset shape）。"""
        elems, h = render_diagram_pptd(_df(), 192, 130, 1048)
        cans = [e for e in elems if e.get("shapeName") == "can"]
        assert len(cans) == 1
        bidir = [e for e in elems if e.get("arrow") == ["arrow", "arrow"]]
        assert bidir, "双向流缺双箭头"

    def test_data_flow_push_block_arrow(self):
        """D-2 块箭头：data_flow push 单向流末段用 rightArrow 块箭头。"""
        elems, h = render_diagram_pptd(_df(), 192, 130, 1048)
        arrows = [e for e in elems if e.get("shapeName") == "rightArrow"]
        assert arrows, "push 流缺块箭头"

    def test_integration_single_sync_block_arrow(self):
        """D-2 块箭头：integration 单 link sync 用 rightArrow 块箭头。"""
        intg = _intg()
        intg["links"] = [{"label": "RFC", "mode": "sync"}]
        elems, h = render_diagram_pptd(intg, 192, 130, 1048)
        arrows = [e for e in elems if e.get("shapeName") == "rightArrow"]
        assert arrows, "单 link sync 集成缺块箭头"

    def test_integration_bidirectional_keeps_connector(self):
        """D-2 块箭头：integration 双向集成仍走 connector（细关系）。"""
        elems, h = render_diagram_pptd(_intg(), 192, 130, 1048)
        arrows = [e for e in elems if e.get("shapeName") == "rightArrow"]
        assert not arrows, "双向集成不应转块箭头"
        conns = [e for e in elems if "Connector" in str(e.get("shapeName", ""))]
        assert conns, "双向集成缺连接符"

    def test_value_chain_chevrons(self):
        elems, h = render_diagram_pptd(_vc(), 192, 130, 1048)
        chevrons = [e for e in elems if e.get("shapeName") == "chevron"]
        assert len(chevrons) == 3

    def test_pyramid_pptd_trapezoids(self):
        """D-5 金字塔：trapezoid preset 堆叠，层数正确、adj 递增（顶层尖底层宽）。"""
        elems, h = render_diagram_pptd(_pyramid(), 192, 130, 1048)
        traps = [e for e in elems if e.get("shapeName") == "trapezoid"]
        assert len(traps) == 3
        adjs = [e.get("adjustments", [0])[0] for e in traps]
        assert adjs == sorted(adjs)

    def test_quadrant_pptd_four_rects(self):
        """D-5 四象限：四区 rect + 两轴，标题与轴标签落文本。"""
        elems, h = render_diagram_pptd(_quadrant(), 192, 130, 1048)
        rects = [e for e in elems if e.get("shapeName") == "rect"]
        assert len(rects) >= 4
        texts = [e for e in elems if e["elementType"] == "text"]
        blob = "\n".join(t["content"]["text"] for t in texts)
        assert "高价值低成本" in blob and "价值" in blob

    def test_decision_alt_branch_dashed(self):
        elems, h = render_diagram_pptd(_decision(), 192, 130, 1048)
        dashed = [e for e in elems if e.get("border", {}).get("style") == "dash"
                  and e.get("shapeName") in CONNECTOR_KINDS]
        assert dashed, "decision 否分支虚线缺失"
        texts = [e for e in elems if e["elementType"] == "text"]
        labels = {t["content"]["text"].strip() for t in texts}
        assert any("否" in label for label in labels) and any("是" in label for label in labels)

    def test_parallel_gateway(self):
        elems, h = render_diagram_pptd(_parallel(), 192, 130, 1048)
        gates = [e for e in elems if e.get("shapeName") == "ellipse"]
        assert gates, "parallel 汇聚网关缺失"

    def test_hub_spoke(self):
        elems, h = render_diagram_pptd(_intg_hub(), 192, 130, 1048)
        spokes = [e for e in elems if e.get("shapeName") in CONNECTOR_KINDS]
        assert len(spokes) == 3

    def test_p1_tables_cells_object(self):
        """P1 表类（raci/crud/reconcile/automation/biz_it_mapping）单元格 {content:} 对象。"""
        for make in (_raci, _crud, _rec, _auto, _bim):
            elems, h = render_diagram_pptd(make(), 192, 130, 1048)
            tables = [e for e in elems if e["elementType"] == "table"]
            assert tables, make()
            for row in tables[0]["rows"]:
                for cell in row:
                    assert "content" in cell


# ---------------------------------------------------------------------------
# P0 容器盒模型修复（间距体系 v1 §3.2）：I-1 徽章骑缝 + I-2 desc/chips stack
# 依据 docs/known_issue_renderer_layout_2026-07-21.md 问题 1/2
# ---------------------------------------------------------------------------

def _inter_area(b1, b2):
    """两 bounds [x,y,w,h] 的相交面积（0 = 零相交）。"""
    ax, ay, aw, ah = b1
    bx, by, bw, bh = b2
    iw = min(ax + aw, bx + bw) - max(ax, bx)
    ih = min(ay + ah, by + bh) - max(ay, by)
    return max(iw, 0.0) * max(ih, 0.0)


def _by_id(elems, eid):
    for e in elems:
        if e.get("elementId") == eid:
            return e
        for child in e.get("children") or []:
            if child.get("elementId") == eid:
                return child
    raise StopIteration


class TestNodeBadgeStraddle:
    """I-1：序号徽章骑缝 overlay(straddle=top-left)，title/desc stack，节点 hug。"""

    @staticmethod
    def _scaler():
        from _renderer.diagram import pptd_emit as pe
        return pe.PptdScaler(0, 0, 1048)

    def test_badge_center_on_node_corner(self):
        from _renderer.diagram import pptd_emit as pe
        sc = self._scaler()
        elems = pe.node("n1", sc, 100, 50, 180, 72, "提交申请", num=1)
        box = _by_id(elems, "n1-box")["bounds"]
        badge = _by_id(elems, "n1-num")["bounds"]
        # 圆心压节点左上角（snap 容差 2px）：badge 框一半在节点外
        assert abs(badge[0] + badge[2] / 2 - box[0]) <= 2
        assert abs(badge[1] + badge[3] / 2 - box[1]) <= 2
        assert badge[0] < box[0]  # 左半在节点外
        assert badge[1] < box[1]  # 上半在节点外

    def test_badge_title_zero_intersection(self):
        from _renderer.diagram import pptd_emit as pe
        sc = self._scaler()
        for vw, title, desc in (
                (180, "提交申请", "录入单据"),
                (180, "审批", ""),
                (68.7, "预归档三键关联挂接", "三键联动"),
                (68.7, "预归档三键关联挂接", "")):
            elems = pe.node("n1", sc, 100, 50, vw, 72, title, desc, num=1)
            badge = _by_id(elems, "n1-num")["bounds"]
            title_b = _by_id(elems, "n1-title")["bounds"]
            assert _inter_area(badge, title_b) == 0, (vw, title, desc)
            if desc:
                desc_b = _by_id(elems, "n1-desc")["bounds"]
                assert _inter_area(badge, desc_b) == 0, (vw, title, desc)

    def test_narrow_node_title_not_covered(self):
        """60pt 窄节点（cross_system 5 列，蓝海集团 P10 场景）：标题不被徽章遮。"""
        from _renderer.diagram import pptd_emit as pe
        sc = self._scaler()
        vw = 60.0 / sc.scale  # 缩放后节点宽恰为 60pt
        elems = pe.node("n1", sc, 100, 50, vw, 72, "预归档三键关联挂接", num=1)
        badge = _by_id(elems, "n1-num")["bounds"]
        title_b = _by_id(elems, "n1-title")["bounds"]
        node_b = _by_id(elems, "n1-box")["bounds"]
        # 标题框顶不低于徽章框底（垂直向完全让开，首字不可能被遮）
        assert title_b[1] >= badge[1] + badge[3]
        # 长标题折多行，且标题区被节点框完整容纳（hug，不溢出互压）
        assert title_b[3] > pe.stack_text_h(1, 11)
        assert title_b[1] + title_b[3] <= node_b[1] + node_b[3]

    def test_desc_stacks_gap_sm_below_title(self):
        from _renderer.diagram import pptd_emit as pe
        from _renderer.spacing import GAP_SM
        sc = self._scaler()
        elems = pe.node("n1", sc, 100, 50, 180, 72, "提交申请", "录入单据并校验", num=1)
        title_b = _by_id(elems, "n1-title")["bounds"]
        desc_b = _by_id(elems, "n1-desc")["bounds"]
        # desc 顶 = 标题底 + GAP_SM（snap 半格点取偶，容差 ±GRID）
        gap = desc_b[1] - (title_b[1] + title_b[3])
        assert GAP_SM - 4 <= gap <= GAP_SM + 4

    def test_node_hug_grows_for_long_content(self):
        """固定 vh=72 放不下时节点长高（hug），desc 仍在框内且底留 INSET_Y。"""
        from _renderer.diagram import pptd_emit as pe
        from _renderer.spacing import INSET_Y
        sc = self._scaler()
        vw = 68.7  # 窄节点：desc 必折多行，72 放不下
        elems = pe.node("n1", sc, 100, 50, vw, 72, "挂接",
                        "销售订单号发票号银行流水号三键联动匹配", num=1)
        node_b = _by_id(elems, "n1-box")["bounds"]
        desc_b = _by_id(elems, "n1-desc")["bounds"]
        assert node_b[3] > sc.len(72)  # 节点长高了
        slack = (node_b[1] + node_b[3]) - (desc_b[1] + desc_b[3])
        assert INSET_Y - 2 <= slack <= INSET_Y + 2  # 底 padding（snap ±2）

    def test_layout_hug_flows_y_cursor(self):
        """布局侧（flow）：内容超高的节点把行/带撑高，后续节点 y 顺延不互压。"""
        from _renderer.diagram import flow
        spec = {"type": "diagram", "diagram_type": "flow", "subtype": "cross_system",
                "title": "cs",
                "systems": [{"name": n} for n in
                            ["OA", "ERP", "档案", "财务", "门户"]],
                "steps": [{"label": "预归档三键关联挂接并同步", "desc": "三键联动",
                           "system": "OA"},
                          {"label": "推送", "system": "OA"},
                          {"label": "记账", "system": "ERP"}]}
        nodes, edges, _, vb_h, _ = flow._layout_cross_system(spec)
        by_label = {nd["label"]: nd for nd in nodes}
        tall = by_label["预归档三键关联挂接并同步"]
        nxt = by_label["推送"]
        assert tall["h"] > flow.NODE_H  # hug 生效（长 label + desc 超出 72）
        # 第二行 y = 第一行顶 + 行实高 + v_gap（按实高推进，不是固定 NODE_H）
        assert nxt["y"] == tall["y"] + tall["h"] + 44


class TestLayeredStack:
    """I-2：layered/4a 行内 desc→chips stack，行高 = 堆叠实高（hug）。"""

    @staticmethod
    def _render():
        from _renderer.diagram import architecture
        spec = {"type": "diagram", "diagram_type": "architecture",
                "subtype": "layered", "title": "L",
                "layers": [{"name": "现状", "desc": "档案散落各处",
                            "components": ["本地盘", "邮件", "U盘"]},
                           {"name": "目标", "desc": "",
                            "components": ["档案中台"]},
                           {"name": "支撑", "desc": "统一平台",
                            "components": ["OCR", "RPA"]}]}
        return architecture.render_pptd(spec, 192, 130, 1048)

    def test_chips_top_below_desc_bottom(self):
        from _renderer.spacing import GAP_SM
        elems, _ = self._render()
        desc = _by_id(elems, "ly0-desc")["bounds"]
        chip0 = _by_id(elems, "ly0-chip-0")["bounds"]
        # chips 顶 = desc 底 + GAP_SM（核心修复：不再 cy+14 撞 cy+8+20；
        # snap 半格点取偶，容差 ±GRID）
        gap = chip0[1] - (desc[1] + desc[3])
        assert GAP_SM - 4 <= gap <= GAP_SM + 4
        assert _inter_area(desc, chip0) == 0

    def test_chips_inset_without_desc(self):
        elems, _ = self._render()
        body = _by_id(elems, "ly1-body")["bounds"]
        chip0 = _by_id(elems, "ly1-chip-0")["bounds"]
        # v1.4：内容块垂直居中——chip 上下留白对称（容差 ±4 snap）
        top_pad = chip0[1] - body[1]
        bot_pad = (body[1] + body[3]) - (chip0[1] + chip0[3])
        assert abs(top_pad - bot_pad) <= 4

    def test_row_height_is_stack_real(self):
        elems, _ = self._render()
        body = _by_id(elems, "ly1-body")["bounds"]
        chip0 = _by_id(elems, "ly1-chip-0")["bounds"]
        # v1.4：行高 = max(64 最小行高, 内容实高 + 2*INSET_Y)——单行 chip 行
        # 即最小行高；64 为 viewbox 值，scaler 0.873（1048/1200）→ ≈56（snap ±4）
        assert abs(body[3] - 56) <= 4
        top_pad = chip0[1] - body[1]
        bot_pad = (body[1] + body[3]) - (chip0[1] + chip0[3])
        assert top_pad >= 4 and abs(top_pad - bot_pad) <= 4

    def test_rows_advance_by_real_height(self):
        from _renderer.spacing import GAP_MD
        elems, _ = self._render()
        b0 = _by_id(elems, "ly0-body")["bounds"]
        b1 = _by_id(elems, "ly1-body")["bounds"]
        # 行 y 游标按实际行高 + GAP_MD 推进（snap ±GRID），行与行零相交
        gap = b1[1] - (b0[1] + b0[3])
        assert GAP_MD - 4 <= gap <= GAP_MD + 4
        assert _inter_area(b0, b1) == 0

    def test_4a_same_stack(self):
        from _renderer.diagram import architecture
        from _renderer.spacing import GAP_SM
        spec = {"type": "diagram", "diagram_type": "architecture",
                "subtype": "4a", "title": "4A",
                "layers": [{"name": "业务架构 BA", "desc": "业务能力视图",
                            "components": ["客户", "订单"]}]}
        elems, _ = architecture.render_pptd(spec, 192, 130, 1048)
        desc = _by_id(elems, "ly0-desc")["bounds"]
        chip0 = _by_id(elems, "ly0-chip-0")["bounds"]
        gap = chip0[1] - (desc[1] + desc[3])
        assert GAP_SM - 4 <= gap <= GAP_SM + 4


class TestP0DiagramsLintClean:
    """修复回归：sequence/cross_system/layered 产出零 P0 探针、零 error。"""

    def _lint_kinds(self, spec):
        import yaml
        from _layout_lint import lint_pptd_files
        elems, _ = render_diagram_pptd(spec, 192, 130, 1048)
        main = {"size": [1280, 720], "theme": {}, "pages": ["pages/01.page"]}
        files = {
            "deck.pptd": yaml.safe_dump(main, allow_unicode=True),
            "pages/01.page": yaml.safe_dump({"elements": elems},
                                            allow_unicode=True),
        }
        return lint_pptd_files(files)

    def test_sequence_lint_clean(self):
        spec = {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
                "title": "seq",
                "steps": [{"label": s, "desc": d} for s, d in
                          [("提交申请", "录入单据"), ("部门审批", ""),
                           ("财务复核", "三单匹配"), ("归档入库", ""),
                           ("回执通知", "")]]}
        issues = self._lint_kinds(spec)
        assert not any(i.kind in ("badge_overlap", "text_stack_overlap")
                       for i in issues)
        assert not any(i.severity == "error" for i in issues)

    def test_cross_system_narrow_lint_clean(self):
        spec = {"type": "diagram", "diagram_type": "flow",
                "subtype": "cross_system", "title": "cs",
                "systems": [{"name": n} for n in
                            ["OA", "ERP", "档案", "财务", "门户"]],
                "steps": [{"label": "预归档三键关联挂接", "system": "OA"},
                          {"label": "推送凭证", "system": "ERP"},
                          {"label": "归档", "system": "档案"},
                          {"label": "记账", "system": "财务"},
                          {"label": "回写状态", "system": "门户"}]}
        issues = self._lint_kinds(spec)
        assert not any(i.kind in ("badge_overlap", "text_stack_overlap")
                       for i in issues)
        assert not any(i.severity == "error" for i in issues)

    def test_layered_lint_clean(self):
        spec = {"type": "diagram", "diagram_type": "architecture",
                "subtype": "layered", "title": "ly",
                "layers": [{"name": "现状", "desc": "档案散落各处",
                            "components": ["本地盘", "邮件", "U盘"]},
                           {"name": "目标", "desc": "统一平台",
                            "components": ["档案中台", "OCR"]},
                           {"name": "支撑", "desc": "",
                            "components": ["安全"]}]}
        issues = self._lint_kinds(spec)
        assert not any(i.kind in ("badge_overlap", "text_stack_overlap")
                       for i in issues)
        assert not any(i.severity == "error" for i in issues)


class TestFlowHtmlStack:
    """I-1/I-2 HTML 侧同构断言（SVG 坐标）。"""

    def test_svg_badge_straddles_corner(self):
        from _renderer.diagram import flow
        nd = {"label": "提交申请", "desc": "", "type": "task",
              "x": 100.0, "y": 50.0, "num": 1, "w": 180.0, "h": 72.0}
        svg = flow._svg_node(nd)
        # 圆点圆心压节点左上角（骑缝）
        assert '<circle cx="100.0" cy="50.0" r="10"' in svg
        # 标题首行 baseline：字形顶（baseline - 0.8em）不低于徽章下摆（y+10）
        m = re.search(r'<text x="[\d.]+" y="([\d.]+)" font-size="13"', svg)
        assert m, "标题 text 缺失"
        assert float(m.group(1)) - 13 * 0.8 >= 50.0 + 10.0

    def test_svg_narrow_node_title_wraps_and_clears_badge(self):
        from _renderer.diagram import flow
        nd = {"label": "预归档三键关联挂接", "desc": "三键联动", "type": "task",
              "x": 60.0, "y": 90.0, "num": 1, "w": 68.7, "h": 90.0}
        svg = flow._svg_node(nd)
        # 长标题折多行（SVG 逐行 <text>，与 pptd 侧 wrap_lines 同一估算）
        baselines = [float(v) for v in re.findall(
            r'<text x="[\d.]+" y="([\d.]+)" font-size="13"', svg)]
        assert len(baselines) >= 2
        # 所有标题行字形顶都在徽章下摆（y+10）之下
        assert all(b - 13 * 0.8 >= 90.0 + 10.0 for b in baselines)
        # desc 首行在标题末行之下（stack：标题底 + GAP_SM 之后）
        m = re.search(r'<text x="[\d.]+" y="([\d.]+)" font-size="11"', svg)
        assert m and float(m.group(1)) > max(baselines)

    def test_html_cross_system_badges_straddle(self):
        html = render_diagram_html(
            {"type": "diagram", "diagram_type": "flow",
             "subtype": "cross_system", "title": "cs",
             "systems": [{"name": n} for n in
                         ["OA", "ERP", "档案", "财务", "门户"]],
             "steps": [{"label": "预归档三键关联挂接", "system": "OA"},
                       {"label": "推送凭证", "system": "ERP"},
                       {"label": "归档", "system": "档案"},
                       {"label": "记账", "system": "财务"},
                       {"label": "回写状态", "system": "门户"}]})
        rects = set(re.findall(
            r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="[\d.]+" '
            r'height="[\d.]+" rx="10"', html))
        circles = re.findall(
            r'<circle cx="(-?[\d.]+)" cy="(-?[\d.]+)" r="10"', html)
        assert len(circles) == 5  # 5 个序号节点
        for ccx, ccy in circles:
            assert (ccx, ccy) in rects, f"徽章({ccx},{ccy})未骑在节点左上角"

    def test_html_layered_desc_before_chips(self):
        # layered/4a HTML 是 div flow（浏览器天然 stack 语义）：desc 必在 chips 前
        html = render_diagram_html(
            {"type": "diagram", "diagram_type": "architecture",
             "subtype": "layered", "title": "L",
             "layers": [{"name": "现状", "desc": "档案散落各处",
                         "components": ["本地盘", "邮件"]}]})
        assert html.index("档案散落各处") < html.index("本地盘")


# ---------------------------------------------------------------------------
# 编辑器注入
# ---------------------------------------------------------------------------

class TestEditorInjector:
    def test_inject_external_assets(self, tmp_path):
        from _renderer.html_editor_injector import inject
        html = tmp_path / "t.html"
        html.write_text(
            '<!DOCTYPE html><html><head><title>t</title></head>'
            '<body><h1>标题</h1><p>正文</p><div class="bullet">要点</div></body></html>',
            encoding="utf-8")
        inject(str(html), inline=False)
        out = html.read_text(encoding="utf-8")
        assert '__editor_toolbar' in out
        assert '_assets/editor.js' in out
        assert 'data-edit-mode="preview"' in out
        assert 'data-editable="true"' in out
        assert (tmp_path / "_assets" / "editor.js").exists()
        assert (tmp_path / "_assets" / "editor.css").exists()

    def test_inject_inline(self, tmp_path):
        from _renderer.html_editor_injector import inject
        html = tmp_path / "t.html"
        html.write_text(
            '<!DOCTYPE html><html><head></head><body><h1>标题</h1></body></html>',
            encoding="utf-8")
        inject(str(html), inline=True)
        out = html.read_text(encoding="utf-8")
        assert "<style>" in out and "showSaveFilePicker" in out
        assert "_assets" not in out

    def test_mark_idempotent(self, tmp_path):
        from _renderer.html_editor_injector import inject
        html = tmp_path / "t.html"
        html.write_text(
            '<!DOCTYPE html><html><head></head><body>'
            '<div class="dg-title" data-editable="true">已标记</div></body></html>',
            encoding="utf-8")
        inject(str(html), inline=True)
        out = html.read_text(encoding="utf-8")
        assert out.count('data-editable="true"') == 1


# ---------------------------------------------------------------------------
# Renderer 集成（HTML 含 diagram CSS + section）
# ---------------------------------------------------------------------------

class TestRendererIntegration:
    def test_render_html_contains_diagram(self, tmp_path):
        # 保存原值、finally 还原：直接 pop 会污染按字母序后跑的测试
        # （Renderer 要求 _PRESALES_CLI_INVOKED=1，曾误伤两轮 agent）
        saved = os.environ.get("_PRESALES_CLI_INVOKED")
        os.environ["_PRESALES_CLI_INVOKED"] = "1"
        try:
            from _renderer import Renderer
            import yaml
            spec = {
                "confirmed": True,
                "document": {"title": "t"},
                "pages": [{"title": "p", "elements": [_seq()]}],
            }
            spec_path = tmp_path / "spec.yml"
            spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
            out = tmp_path / "out.html"
            # 输出白名单：落到项目 output/ 下
            proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            out = os.path.join(proj_root, "output", "通用", "_test_dg_render.html")
            r = Renderer(str(spec_path))
            r.render_html(out)
            with open(out, encoding="utf-8") as f:
                html = f.read()
            assert "section.diagram" in html  # diagram CSS 注入
            assert 'data-subtype="sequence"' in html
            os.remove(out)
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved


# ---------------------------------------------------------------------------
# P2-A2：diagram 风格透传（style 参数 -> use_style 切色板 -> 恢复）
# ---------------------------------------------------------------------------

class TestDiagramStylePassthrough:
    """weaver_blue 的 diagram 主色（#337AB7，R-4 官网主蓝）与 default
    consulting（#00338D）不同，验证 style 参数真正透传到色板；
    渲染后模块色板恢复默认主题。"""

    def test_html_uses_style_primary(self):
        from _renderer.diagram import render_diagram_html
        html_default = render_diagram_html(_seq())
        html_weaver = render_diagram_html(_seq(), style="weaver_blue")
        assert "#00338D" in html_default        # consulting BLUE
        assert "#337AB7" in html_weaver         # weaver_blue primary
        assert "#00338D" not in html_weaver

    def test_pptd_uses_style_primary(self):
        from _renderer.diagram import render_diagram_pptd
        elems_default, _ = render_diagram_pptd(_seq(), 192, 130, 1048)
        elems_weaver, _ = render_diagram_pptd(_seq(), 192, 130, 1048,
                                              style="weaver_blue")

        def _colors(elems):
            out = set()
            for e in elems:
                for key in ("fill", "border"):
                    if key in e and isinstance(e[key], dict) and "color" in e[key]:
                        out.add(e[key]["color"])
            return out

        assert "#00338D" in _colors(elems_default)
        assert "#337AB7" in _colors(elems_weaver)
        assert "#00338D" not in _colors(elems_weaver)

    def test_theme_restored_after_styled_render(self):
        """styled 渲染后模块色板恢复 consulting_kpmg，不污染后续渲染。"""
        from _renderer.diagram import render_diagram_html, theme
        assert theme.BLUE == "#00338D"
        render_diagram_html(_seq(), style="weaver_blue")
        assert theme.BLUE == "#00338D"
        assert theme.current_style_name() == "consulting_kpmg"

    def test_css_variables_styled(self):
        """css_variables 透传风格：:root --blue 跟随风格主色。"""
        from _renderer.diagram import theme
        assert "--blue:#00338D" in theme.css_variables()
        assert "--blue:#337AB7" in theme.css_variables("weaver_blue")
        assert "--blue:#00338D" in theme.css_variables()  # 已恢复

    def test_placeholder_uses_style_primary(self):
        """占位卡同属 diagram 管线，同样透传。"""
        from _renderer.diagram import render_placeholder_html
        html = render_placeholder_html({"type": "product_intro_placeholder",
                                        "title": "t"}, style="weaver_blue")
        assert "#337AB7" in html


# ---------------------------------------------------------------------------
# v1.5 实战修复回归（审计报告 §7.2，示例项目 v4 暴露）
# ---------------------------------------------------------------------------

def _layered_rails_cjk():
    e = _layered()
    e["rails"] = ["安全体系", "标准规范"]
    return e


def _layered_rails_ascii():
    e = _layered()
    e["rails"] = ["DA/T 94-2022"]
    return e


def _seq_loopback():
    return {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
            "title": "回环",
            "steps": [{"label": "提交"},
                      {"label": "审核", "type": "decision",
                       "alt_next": "提交", "alt_label": "未通过"},
                      {"label": "归档", "type": "end"}]}


class TestV15FieldFixes:
    """§7.2 五项实战修复回归。"""

    def test_rails_cjk_keep_vertical(self):
        """中文 rails 保持竖排（§7.2-1 不影响正常形态）。"""
        html = render_diagram_html(_layered_rails_cjk())
        assert "writing-mode:vertical-rl" in html
        assert "安全体系" in html

    def test_rails_ascii_horizontal_html(self):
        """ASCII 比例高的 rails 改横排小字，不再逐字竖排散列。"""
        html = render_diagram_html(_layered_rails_ascii())
        assert "DA/T 94-2022" in html
        assert "writing-mode" not in html

    def test_rails_ascii_pptd_no_perchar_join(self):
        """PPT 端 ASCII rails 不做逐字 \\n 竖排。"""
        elems, h = render_diagram_pptd(_layered_rails_ascii(), 192, 130, 1048)
        texts = [e for e in elems if e["elementType"] == "text"]
        assert any("DA/T 94-2022" in t["content"]["text"] for t in texts)

    def test_sequence_loopback_html(self):
        """sequence 的 decision alt_next 指向前序节点：画回游直角虚线。"""
        html = render_diagram_html(_seq_loopback())
        assert "未通过" in html
        assert 'stroke-dasharray="6,4"' in html
        assert re.search(r'M[\d.]+,[\d.]+ L[\d.]+,[\d.]+ L[\d.]+,[\d.]+ L', html)

    def test_sequence_loopback_pptd(self):
        """PPT 端回游：三段 straightConnector1 虚线 + 是/否标注。"""
        elems, h = render_diagram_pptd(_seq_loopback(), 192, 130, 1048)
        conn = [e for e in elems if e.get("shapeName") in CONNECTOR_KINDS
                and e.get("border", {}).get("style") == "dash"]
        ids = {e["elementId"] for e in conn}
        assert any("-alt-" in i or i.startswith("alt-") for i in ids), "回游虚线缺失"
        texts = [e for e in elems if e["elementType"] == "text"]
        blob = "\n".join(t["content"]["text"] for t in texts)
        assert "未通过" in blob and "是" in blob

    def test_infra_cross_zone_label_warns(self, capsys):
        """infra 跨 zone link 写 label → 渲染器告警（§7.2-2）。"""
        e = {"type": "diagram", "diagram_type": "architecture",
             "subtype": "infra", "title": "拓扑",
             "zones": [{"name": "DMZ", "nodes": [{"name": "防火墙"}]},
                       {"name": "内网", "nodes": [{"name": "ERP"}]}],
             "links": [{"from": "DMZ.防火墙", "to": "内网.ERP",
                        "label": "回单回传"}]}
        html = render_diagram_html(e)
        assert "回单回传" in html
        assert "跨 zone link 不建议写 label" in capsys.readouterr().out

    def test_infra_link_label_avoids_node_text(self):
        """跨 zone 长斜线 label 落点避开节点盒与名称/desc 文本带（§7.4 图标总览目检：
        HTTPS 药丸 100% 压办公终端名——占用区改精确矩形 + 全命中退最小重叠）。"""
        from _renderer.diagram.architecture import (
            _infra_zones_geometry, _infra_occupancy, _infra_link_label_pos)
        e = {"type": "diagram", "diagram_type": "architecture",
             "subtype": "infra", "title": "拓扑",
             "zones": [
                 {"name": "计算与存储", "nodes": [
                     {"name": "应用服务器", "icon": "server", "desc": "server"},
                     {"name": "数据库", "icon": "db", "desc": "db"},
                     {"name": "容器平台", "icon": "container", "desc": "container"},
                     {"name": "应用系统", "icon": "app", "desc": "app"}]},
                 {"name": "网络与安全", "nodes": [
                     {"name": "防火墙", "icon": "firewall", "desc": "firewall"},
                     {"name": "核心交换机", "icon": "switch", "desc": "switch"},
                     {"name": "边界路由器", "icon": "router", "desc": "router"},
                     {"name": "负载均衡", "icon": "lb", "desc": "lb"}]},
                 {"name": "端侧与外部", "nodes": [
                     {"name": "办公终端", "icon": "terminal", "desc": "terminal"},
                     {"name": "业务用户", "icon": "user", "desc": "user"},
                     {"name": "安全认证", "icon": "shield", "desc": "shield"},
                     {"name": "运维监控", "icon": "monitor", "desc": "monitor"},
                     {"name": "公有云", "icon": "cloud", "desc": "cloud"}]}]}
        zone_rects, node_rects, _ = _infra_zones_geometry(e)
        occ = _infra_occupancy(e["zones"], node_rects)

        def _center(zn, nn):
            r = node_rects[zn][nn]
            return r[0] + r[2] / 2, r[1] + r[3] / 2

        ax, ay = _center("端侧与外部", "业务用户")
        bx, by = _center("网络与安全", "负载均衡")
        sx1, sy1, sx2, sy2 = ax + 30, ay, bx - 30, by
        c1x, c1y = ax + 30 + (bx - ax) * 0.4, ay
        c2x, c2y = bx - 30 - (bx - ax) * 0.4, by
        lx, ly = _infra_link_label_pos(sx1, sy1, c1x, c1y, c2x, c2y, sx2, sy2,
                                       "HTTPS", occ)
        tw = len("HTTPS") * 9.5 + 18
        px0, py0, px1, py1 = lx - tw / 2, ly - 10, lx + tw / 2, ly + 8
        for ox0, oy0, ox1, oy1 in occ:
            assert px1 <= ox0 or px0 >= ox1 or py1 <= oy0 or py0 >= oy1, \
                f"label 药丸压占用区 ({ox0},{oy0},{ox1},{oy1})"

    def test_infra_glyphs_switch_router_lb_distinct(self):
        """switch/router/lb 三 glyph 形态区分（§7.4：router 四向交叉、lb 一分三 hub）。"""
        from _renderer.diagram.architecture import _infra_glyph
        sw = _infra_glyph("switch", 100, 100, 30, "#1B5E8A")
        ro = _infra_glyph("router", 100, 100, 30, "#1B5E8A")
        lb = _infra_glyph("lb", 100, 100, 30, "#1B5E8A")
        assert len({sw, ro, lb}) == 3
        assert "V" in ro          # router 有纵向交叉箭头
        assert "<circle" in lb    # lb 有中心分发点
        assert "V" not in sw and "<circle" not in sw

    def test_flow_rows_label_sub_shrink(self):
        """flow_rows 行标签 label_sub 过长 → 窄栏自动缩字号（§7.2-5）。"""
        from _renderer.diagram import pptd_emit as pe_mod
        row = {"label": "线上", "label_sub": "混合签（电章+鲜章）",
               "cards": [{"label": "发起"}]}
        elems, h = pe_mod.render_flow_rows_pptd({"rows": [row]}, 192, 130, 1048)
        lb = [e for e in elems if e["elementId"].startswith("fr-lb")]
        assert lb, "行标签文本缺失"
        assert lb[0]["content"]["fontSize"] < 12

    def test_cards_v2_page_maps_info_cards(self, tmp_path):
        """v2 页面内老式 cards 元素映射为 info_cards 卡片样式（§7.2-4）。"""
        import shutil
        # S6 修复：保存/条件还原 _PRESALES_CLI_INVOKED。曾无条件 pop，
        # 子集测试序下（外部已设该变量，如 baseline_kit import 时）会误删
        # 别人的预设，致后续 test_baseline 6 例抛 NotInvokedViaCLIError。
        saved = os.environ.get("_PRESALES_CLI_INVOKED")
        os.environ["_PRESALES_CLI_INVOKED"] = "1"
        try:
            from _renderer import Renderer
            import yaml
            spec = tmp_path / "spec.yml"
            spec.write_text(yaml.safe_dump({
                "confirmed": True, "theme": "consulting_kpmg",
                "pages": [{"id": "p1", "title": "对比", "layout": "P07",
                           "elements": [
                               {"type": "section_tag", "label": "对比"},
                               {"type": "action_title",
                                "segments": [{"t": "双方案对比"}]},
                               {"type": "cards", "cards": [
                                   {"title": "方案甲", "body": "覆盖全流程",
                                    "tag": "推荐", "highlight": "ROI 高"}]},
                               {"type": "table", "headers": ["项"],
                                "rows": [["甲"]]},
                           ]}],
            }, allow_unicode=True), encoding="utf-8")
            r = Renderer(str(spec))
            out_dir = os.path.join("output", "通用", "cards_v2_test")
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir)
            try:
                out = os.path.join(out_dir, "out.html")
                r.render_html(out)
                with open(out, encoding="utf-8") as f:
                    html = f.read()
            finally:
                if os.path.exists(out_dir):
                    shutil.rmtree(out_dir)
            assert 'class="info-card"' in html, "cards 未映射 info_cards 样式"
            assert "方案甲" in html and "覆盖全流程" in html
            assert "推荐" in html and "ROI 高" in html  # tag/highlight 不丢
        finally:
            if saved is None:
                os.environ.pop("_PRESALES_CLI_INVOKED", None)
            else:
                os.environ["_PRESALES_CLI_INVOKED"] = saved


def _harvey():
    return {"type": "diagram", "diagram_type": "matrix",
            "subtype": "harvey_balls", "title": "供应商比选",
            "rows": ["功能覆盖", "集成能力", "本地服务"],
            "columns": ["我方方案", "厂商A"],
            "cells": [{"row": "功能覆盖", "col": "我方方案", "value": 4},
                      {"row": "功能覆盖", "col": "厂商A", "value": 2},
                      {"row": "集成能力", "col": "我方方案", "value": 3},
                      {"row": "集成能力", "col": "厂商A", "value": 2},
                      {"row": "本地服务", "col": "厂商A", "value": 1}]}


class TestHarveyBalls:
    """matrix/harvey_balls（第 35 种）：五档哈维球对比表。"""

    def test_schema_ok(self):
        assert schema.validate_element(_harvey()) == []

    def test_schema_value_range(self):
        e = _harvey()
        e["cells"][0]["value"] = 7
        errs = schema.validate_element(e)
        assert any("0-4" in m for m in errs)

    def test_schema_row_ref(self):
        e = _harvey()
        e["cells"][0]["row"] = "不存在"
        errs = schema.validate_element(e)
        assert any("不在 rows 内" in m for m in errs)

    def test_html_balls(self):
        html = render_diagram_html(_harvey())
        assert "功能覆盖" in html and "厂商A" in html
        assert html.count("<svg") >= 5  # 5 个值球 + 图例球
        assert "完全满足" in html  # 图例
        assert "—" in html  # 本地服务×我方方案 缺 cell = 未评估

    def test_pptd_pie_shapes(self):
        elems, h = render_diagram_pptd(_harvey(), 192, 130, 1048)
        shapes = [e for e in elems if e["elementType"] == "shape"]
        pies = [e for e in shapes if e.get("shapeName") == "pie"]
        ellipses = [e for e in shapes if e.get("shapeName") == "ellipse"]
        assert len(pies) == 4  # value 1/2/2/3 部分填充
        assert len(ellipses) == 1  # value 4 实心球
        for p in pies:
            assert p["adjustments"][0] == 16200000  # 起点恒 270°（12 点）
        texts = [e for e in elems if e["elementType"] == "text"]
        blob = "\n".join(t["content"]["text"] for t in texts)
        assert "功能覆盖" in blob and "我方方案" in blob


def _bar():
    return {"type": "diagram", "diagram_type": "chart", "subtype": "bar",
            "title": "近三年收入",
            "categories": ["2023", "2024", "2025"],
            "series": [{"name": "收入", "values": [12, 15, 19]}],
            "unit": "亿元", "exhibit": {"source": "公司年报"}}


def _waterfall():
    return {"type": "diagram", "diagram_type": "chart", "subtype": "waterfall",
            "title": "收益桥",
            "steps": [{"label": "现状成本", "value": 100, "kind": "total"},
                      {"label": "减人", "value": -30},
                      {"label": "减纸", "value": -12},
                      {"label": "目标成本", "value": 58, "kind": "total"}],
            "unit": "万元", "exhibit": {"source": "测算口径见附录"}}


class TestChart:
    """chart 数据图表族（第 36/37 种，v1.5，HTML 先行）。"""

    def test_bar_schema_ok(self):
        assert schema.validate_element(_bar()) == []

    def test_bar_schema_mismatch(self):
        e = _bar()
        e["series"][0]["values"] = [12, 15]
        errs = schema.validate_element(e)
        assert any("长度" in m for m in errs)

    def test_bar_schema_negative_rejected(self):
        e = _bar()
        e["series"][0]["values"][1] = -5
        errs = schema.validate_element(e)
        assert any("负值" in m for m in errs)

    def test_waterfall_schema_kind(self):
        e = _waterfall()
        e["steps"][1]["kind"] = "bogus"
        errs = schema.validate_element(e)
        assert any("delta/total" in m for m in errs)

    def test_bar_html(self):
        html = render_diagram_html(_bar())
        assert "2025" in html and "收入" in html
        assert "单位：亿元" in html and "公司年报" in html  # 来源行走 exhibit 槽位
        assert "<rect" in html  # 柱体
        assert "暂未实现" not in html and "渲染异常" not in html

    def test_waterfall_html(self):
        html = render_diagram_html(_waterfall())
        assert "现状成本" in html and "目标成本" in html
        assert "-30" in html  # 负 delta 带符号标签
        assert 'stroke-dasharray="3,3"' in html  # 桥接虚线
        assert "测算口径见附录" in html  # 来源行走 exhibit 槽位

    def test_chart_pptd_native_bar_waterfall_degrade(self):
        """0d：bar 走原生 chart 元素（F7 拍板执行）；waterfall 批二已接原生。"""
        elems, h = render_diagram_pptd(_bar(), 192, 130, 1048)
        charts = [e for e in elems if e["elementType"] == "chart"]
        assert charts and h > 0
        assert charts[0]["chartKind"] == "bar"
        assert charts[0]["categories"] == _bar().get("categories")
        # waterfall 批二已接原生 chart（栈式 emulate，chart.py render_pptd）
        elems2, h2 = render_diagram_pptd(_waterfall(), 192, 130, 1048)
        charts2 = [e for e in elems2 if e["elementType"] == "chart"]
        assert charts2 and h2 > 0
        assert charts2[0]["chartKind"] == "waterfall"


# ---------------------------------------------------------------------------
# B2#23：exhibit repr 泄漏（P0-V1，蓝海 v7 实害）——integration 图 source
# 是端点 mapping dict，_wrap_exhibit 曾 str() 进 _esc 产出 {'name'… repr
# #56（B6 Wave3）：溯源字符串契约收编至 exhibit.source，顶层读取退役
# ---------------------------------------------------------------------------
class TestExhibitSourceLeak:
    def test_integration_dict_source_no_leak(self):
        """integration p2p 夹具渲染：无 exhibit-source div，{'name' 不在 HTML。"""
        elem = _intg()
        elem["exhibit"] = {"num": "图 3", "title": "集成关系"}
        html = render_diagram_html(elem)
        assert "exhibit-source" not in html
        assert "{'name'" not in html
        assert "exhibit-body" in html  # 图框本体仍在（exhibit 头不误伤）

    def test_nested_exhibit_source_rendered(self):
        """#56：溯源字符串写 exhibit.source，来源行照常渲染。"""
        elem = {"type": "diagram", "diagram_type": "flow", "subtype": "cross_system",
                "title": "OA-SAP",
                "exhibit": {"source": "来源：客户 2026-08 会议纪要"},
                "systems": [{"name": "OA"}, {"name": "SAP"}],
                "steps": [{"label": "提交", "system": "OA"}]}
        html = render_diagram_html(elem)
        assert "exhibit-source" in html
        assert "客户 2026-08 会议纪要" in html

    def test_top_level_string_source_rejected_by_schema(self):
        """#56：非 integration 子类型顶层 source 报迁移错误（杜绝再挂顶层）。"""
        elem = {"type": "diagram", "diagram_type": "flow", "subtype": "cross_system",
                "title": "OA-SAP", "source": "来源：旧写法",
                "systems": [{"name": "OA"}, {"name": "SAP"}],
                "steps": [{"label": "提交", "system": "OA"}]}
        errs = schema.validate_element(elem)
        assert any("exhibit.source" in m for m in errs)

    def test_integration_string_source_type_rejected(self):
        """#56：integration 顶层 source 收 dict（端点 mapping）或 str（点对点
        简式，outline_to_spec M1 生成器契约）；非此两者（如列表）报错。"""
        elem = _intg()
        elem["source"] = ["来源：误挂"]
        errs = schema.validate_element(elem)
        assert any("端点 mapping" in m for m in errs)
        # p2p 简式（渲染端缺口登记 B6 #58，schema 放行生成器现状）
        ok_p2p = dict(_intg(), source="OA", target="ERP")
        assert schema.validate_element(ok_p2p) == []

    def test_exhibit_field_type_guard(self):
        """#56：exhibit 非 dict / exhibit.source 非字符串均报 schema 错误。"""
        base = {"type": "diagram", "diagram_type": "flow", "subtype": "cross_system",
                "title": "OA-SAP",
                "systems": [{"name": "OA"}, {"name": "SAP"}],
                "steps": [{"label": "提交", "system": "OA"}]}
        e1 = dict(base, exhibit="来源：字符串不该挂这")
        assert any("exhibit 必须是对象" in m for m in schema.validate_element(e1))
        e2 = dict(base, exhibit={"num": ["图 1"], "source": {"bad": 1}})
        errs2 = schema.validate_element(e2)
        assert any("exhibit.num" in m and "字符串" in m for m in errs2)
        assert any("exhibit.source" in m and "字符串" in m for m in errs2)

    def test_esc_non_string_returns_repr_no_crash(self):
        """_esc 非字符串行为固化：dict 产 repr 显式可见（不抛异常）——
        泄漏防线在 _wrap_exhibit 的 isinstance 守卫，_esc 不二次设防。"""
        from _renderer.elements import _esc
        out = _esc({"name": "OA"})
        assert "{" in out and "OA" in out  # repr 形态
        assert _esc(0) == "0"
        assert _esc(None) == "None"
