# -*- coding: utf-8 -*-
"""间距体系收尾测试（docs/spacing_design_v1_2026-07-20 §六 4/5）：

- S4 表格行高 hug：fit_gap/raci/crud/biz_it_mapping/reconcile/automation_table
  六表 + cbm（排查 I-16/I-17）——行高 = 单元格最大行数 × 行距 + 2×INSET_Y，
  下限原写死值（短内容不变，长内容撑高）
- S5 subtype 容量阈值 warning（schema.validate_element_warnings，与 errors
  分离不阻断；阈值取排查实测越界数据 -1）
- product_intro_placeholder 页底防线（_pptd_gen，与 diagram 分支 I-16 同款）
"""

import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _renderer import schema
from _renderer.diagram import render_diagram_pptd
from _renderer.diagram import pptd_emit as pe

X, Y, W = 192, 130, 1048  # 与排查探针一致的真实内容区
L30 = "这是一段三十字左右的中文长句用于验证长文本排版是否溢出边界"
L60 = "这是一段接近六十字的超长中文描述文本，用来压测渲染器在极端长文本下的换行、溢出与裁切行为表现"


def _table_of(elems):
    return next(e for e in elems if e["elementType"] == "table")


def _by_id(elems, suffix):
    return next(e for e in elems if str(e["elementId"]).endswith(suffix))


# ---------------------------------------------------------------------------
# S4：table_hug_geometry 公式
# ---------------------------------------------------------------------------

class TestTableHugGeometry:
    def test_short_rows_keep_min_height(self):
        """短内容：各行 hug 高不超原写死高 -> 与原公式逐字节一致。"""
        # 8 行 fit_gap 口径：表头下限 8×40×0.14=44.8、数据行 39.3 均 > 1 行实高
        rows = [["客户需求", "产品甲"]] + [[f"需求{i}", "Fit"] for i in range(7)]
        table_h, fracs = pe.table_hug_geometry(rows, [0.34, 0.66], 1048, 40, 0.14)
        assert table_h == 320  # 8 × 40，与原写死输出一致
        assert fracs[0] == 0.14
        assert fracs[1] == pytest.approx(0.86 / 7)

    def test_header_floor_is_one_line(self):
        """表头原比例高放不下 1 行时，hug 顶到 1 行实高（修溢出方向）。"""
        one_line = 14 * 1.3 + 2 * 6  # 行距×1 + 2×INSET_Y = 30.2
        rows = [["表头"], ["短"]]
        table_h, fracs = pe.table_hug_geometry(rows, [1.0], 1000, 40, 0.14)
        assert table_h == pytest.approx(one_line + 68.8)  # 30.2 + 2×40×0.86
        assert fracs[0] == pytest.approx(one_line / table_h)

    def test_long_cell_grows_by_lines(self):
        """长文本按列宽折行：行高 = 行数 × 行距 + 2×INSET_Y。"""
        rows = [["表头"], ["一" * 300]]  # 300×14 / (1000-20) -> 5 行
        grew_h = 5 * 14 * 1.3 + 2 * 6  # 103
        table_h, fracs = pe.table_hug_geometry(rows, [1.0], 1000, 40, 0.14)
        assert table_h == pytest.approx(30.2 + grew_h)
        assert fracs[1] == pytest.approx(grew_h / table_h)

    def test_multi_paragraph_cell_counts_each_paragraph(self):
        """多段落单元格（fit_gap 的 label+note）按段折行累加。"""
        rows = [["h"], ["Fit\n" + "一" * 200]]  # 1 + ceil(2800/980)=3 -> 4 行
        table_h, _ = pe.table_hug_geometry(rows, [1.0], 1000, 40, 0.14)
        assert table_h == pytest.approx(30.2 + (4 * 14 * 1.3 + 12))


# ---------------------------------------------------------------------------
# S4：6 表 + cbm 渲染层 hug
# ---------------------------------------------------------------------------

class TestTableSubtypeHug:
    def test_fit_gap_long_note_grows_row(self):
        elem = {"type": "diagram", "diagram_type": "matrix", "subtype": "fit_gap",
                "title": "FG", "requirements": ["需求1", "需求2"],
                "products": ["我方", "竞品"],
                "cells": [{"req": "需求1", "product": "我方", "match": "fit", "note": L60},
                          {"req": "需求2", "product": "竞品", "match": "gap", "note": "短"}]}
        elems, h = render_diagram_pptd(elem, X, Y, W)
        t = _table_of(elems)
        assert h > 3 * 40  # 长 note 行撑高，总高超原写死 120
        fracs = t["rowHeights"]
        assert fracs[1] > fracs[2]  # 长 note 行比短 note 行高
        assert t["bounds"][3] == h
        assert abs(sum(fracs) - 1.0) < 1e-6  # 方言：rowHeights 比例和为 1

    def test_fit_gap_short_content_unchanged(self):
        """短内容：数据行保持原写死高（2×40×0.86=68.8），仅表头取 1 行实高。"""
        elem = {"type": "diagram", "diagram_type": "matrix", "subtype": "fit_gap",
                "title": "FG", "requirements": ["需求1"], "products": ["我方"],
                "cells": [{"req": "需求1", "product": "我方", "match": "fit", "note": "短"}]}
        elems, h = render_diagram_pptd(elem, X, Y, W)
        assert h == pytest.approx(30.2 + 68.8)  # 99.0：无行被压缩

    @pytest.mark.parametrize("subtype,elem,const", [
        ("raci", {"roles": ["角色甲"],
                  "tasks": [{"name": L60, "assignments": [{"role": "角色甲", "type": "A"}]},
                            {"name": "短", "assignments": []}]}, 36),
        ("crud", {"docs": [L60, "短"], "entities": ["实体甲"],
                  "cells": [{"doc": L60, "entity": "实体甲", "ops": ["C"]}]}, 36),
        ("automation_table", {"tasks": [{"name": L60, "current": "人工", "target": "自动",
                                         "saving": "10%", "roi": "高"},
                                        {"name": "短", "current": "人工", "target": "自动",
                                         "saving": "5%", "roi": "中"}]}, 36),
    ])
    def test_matrix_and_relationship_tables_grow(self, subtype, elem, const):
        dt = "matrix" if subtype in ("raci", "crud") else "relationship"
        elem = {"type": "diagram", "diagram_type": dt, "subtype": subtype,
                "title": "T", **elem}
        elems, h = render_diagram_pptd(elem, X, Y, W)
        t = _table_of(elems)
        assert h > 3 * const  # 长文本行撑高超原写死
        fracs = t["rowHeights"]
        assert fracs[1] > fracs[2]

    def test_reconcile_long_term_grows(self):
        elem = {"type": "diagram", "diagram_type": "relationship",
                "subtype": "cross_4a_reconcile", "title": "REC",
                "terms": [{"term": L60, "ba": "业", "aa": "模", "da": "实", "ta": "组"},
                          {"term": "短", "ba": "业", "aa": "模", "da": "实", "ta": "组"}]}
        elems, h = render_diagram_pptd(elem, X, Y, W)
        assert h > 3 * 36
        assert _table_of(elems)["rowHeights"][1] > _table_of(elems)["rowHeights"][2]

    def test_biz_it_mapping_long_cell_grows(self):
        elem = {"type": "diagram", "diagram_type": "architecture",
                "subtype": "biz_it_mapping", "title": "BIM",
                "mappings": [{"biz_capability": L60, "biz_processes": [L30],
                              "it_systems": ["系"], "data_entities": ["实"]},
                             {"biz_capability": "短", "biz_processes": ["流"],
                              "it_systems": ["系"], "data_entities": ["实"]}]}
        elems, h = render_diagram_pptd(elem, X, Y, W)
        assert h > 3 * 44
        assert _table_of(elems)["rowHeights"][1] > _table_of(elems)["rowHeights"][2]

    def test_cbm_long_level_grows_row(self):
        """cbm（I-17）：30 字 level 名 5 行 -> 行高 stack_text_h(5,13)+2×INSET_Y（viewBox）。

        stack_text_h 现含防 lint 误判的 +GRID 余量（pptd_emit.py），
        期望值公式化而非写死，避免余量调整时测试反复跟进。
        """
        elem = {"type": "diagram", "diagram_type": "matrix", "subtype": "cbm",
                "title": "CBM",
                "rows": [{"level": L30, "capabilities": [{"name": "能力甲", "heat": "mid"}]},
                         {"level": "L2", "capabilities": [{"name": "能"}]}]}
        elems, h = render_diagram_pptd(elem, X, Y, W)
        sc = pe.PptdScaler(X, Y, W)
        from _renderer.spacing import INSET_Y
        expected = pe.stack_text_h(5, 13) + 2 * INSET_Y
        r0 = _by_id(elems, "-cbm-l0")["bounds"][3]
        r1 = _by_id(elems, "-cbm-l1")["bounds"][3]
        assert abs(r0 - sc.len(expected)) <= 2  # snap 容差
        assert abs(r1 - sc.len(52)) <= 2   # 短行保持原写死 52

    def test_long_table_deck_lint_clean(self):
        """长 note fit_gap 整页生成后 lint 零 error（hug 后无溢出）。"""
        from _layout_lint import lint_pptd_files
        spec = _minimal_spec([{
            "id": "p1", "title": "长文本表",
            "elements": [{
                "type": "diagram", "diagram_type": "matrix", "subtype": "fit_gap",
                "title": "FG", "requirements": ["需求1", "需求2"],
                "products": ["我方", "竞品"],
                "cells": [{"req": "需求1", "product": "我方", "match": "fit", "note": L60},
                          {"req": "需求2", "product": "竞品", "match": "gap", "note": "短"}]}],
        }])
        files, _report = _build(spec)
        errors = [i for i in lint_pptd_files(files) if i.severity == "error"]
        assert errors == []


# ---------------------------------------------------------------------------
# S5：subtype 容量阈值 warning
# ---------------------------------------------------------------------------

def _swimlane(n_lanes):
    return {"type": "diagram", "diagram_type": "flow", "subtype": "swimlane",
            "title": "S", "lanes": [{"name": f"道{i}"} for i in range(n_lanes)],
            "steps": [{"label": f"步{i}", "lane": f"道{i % n_lanes}"} for i in range(6)]}


def _cross_system(n_rows):
    return {"type": "diagram", "diagram_type": "flow", "subtype": "cross_system",
            "title": "C", "systems": [{"name": "S1"}],
            "steps": [{"label": f"步{i}", "system": "S1"} for i in range(n_rows)]}


def _decision(n_steps):
    return {"type": "diagram", "diagram_type": "flow", "subtype": "decision",
            "title": "D", "steps": [{"label": f"步{i}"} for i in range(n_steps)]}


def _timeline(st, n):
    return {"type": "diagram", "diagram_type": "timeline", "subtype": st,
            "title": "T", "milestones": [{"label": f"卡{i}", "date": "Q1"} for i in range(n)]}


def _cmap(n_sections):
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "capability_map",
            "title": "CM",
            "sections": [{"name": f"域{s}",
                          "capabilities": [{"code": "C1", "name": "能"}]}
                         for s in range(n_sections)]}


def _bct(n_groups, n_children):
    return {"type": "diagram", "diagram_type": "relationship",
            "subtype": "biz_capability_tree", "title": "BCT",
            "groups": [{"name": f"组{g}",
                        "children": [{"name": f"子{g}-{c}"} for c in range(n_children)]}
                       for g in range(n_groups)]}


class TestCapacityWarnings:
    @pytest.mark.parametrize("elem,expect", [
        (_swimlane(5), "泳道 5 超过容量上限 4"),
        (_swimlane(4), None),
        (_cross_system(5), "单列行数 5 超过容量上限 4"),
        (_cross_system(4), None),
        (_decision(7), "步数 7 超过容量上限 6"),
        (_decision(6), None),
        (_timeline("vertical", 8), "里程碑卡 8 超过容量上限 7"),
        (_timeline("vertical", 7), None),
        (_timeline("horizontal", 9), "里程碑卡 9 超过容量上限 8"),
        (_timeline("horizontal", 8), None),
        (_cmap(4), "section 4 超过容量上限 3"),
        (_cmap(3), None),
        (_bct(3, 5), "子项总数（组×子） 15 超过容量上限 12"),
        (_bct(3, 4), None),
    ])
    def test_thresholds(self, elem, expect):
        warnings = schema.validate_element_warnings(elem, index=0)
        if expect is None:
            assert warnings == []
        else:
            assert len(warnings) == 1
            assert expect in warnings[0]
            assert "拆为两页/两图" in warnings[0]
            assert "elements[0]" in warnings[0]

    def test_non_diagram_and_other_subtypes_silent(self):
        assert schema.validate_element_warnings({"type": "text", "content": "x"}) == []
        assert schema.validate_element_warnings(_timeline("vertical", 3)) == []
        seq = {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
               "title": "S", "steps": [{"label": f"步{i}"} for i in range(20)]}
        assert schema.validate_element_warnings(seq) == []

    def test_warnings_not_in_validate_spec_errors(self):
        """超阈值只产 warning，不进 validate_spec 的 errors（不阻断）。"""
        spec = {"pages": [{"id": "p1", "elements": [_swimlane(5)]}]}
        assert schema.validate_spec(spec) == []

    def test_renderer_init_collects(self, tmp_path, monkeypatch):
        """Renderer init 经现有警告通道收集进 report.warnings。"""
        monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
        from _renderer import Renderer
        spec = {"confirmed": True, "document": {"title": "T"},
                "pages": [{"id": "p1", "title": "页", "elements": [_swimlane(5)]}]}
        spec_path = tmp_path / "spec.yml"
        spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        r = Renderer(str(spec_path))
        assert any("[spec校验] pages[0].elements[0]" in w and "泳道 5" in w
                   for w in r.report.warnings)

    def test_render_unchanged_only_warns(self):
        """渲染零变化：超阈值图照常完整渲染（不降级不跳过），只多一条 warning。"""
        from _renderer.elements import RenderReport
        over = _timeline("vertical", 8)
        spec = _minimal_spec([{"id": "p1", "title": "页", "elements": [over]}])
        report = RenderReport()
        files, _ = _build(spec, report=report)
        page = yaml.safe_load(files["pages/02_p1.page"])
        dg_elems = [e for e in page["elements"] if str(e["elementId"]).startswith("dg")]
        assert dg_elems, "超阈值 diagram 仍应完整渲染"
        assert not report.skipped and not report.degraded
        assert any("timeline/vertical 里程碑卡 8 超过容量上限 7" in w
                   for w in report.warnings)
        # 未超阈值同内容渲染无 warning
        report2 = RenderReport()
        _build(_minimal_spec([{"id": "p1", "title": "页",
                               "elements": [_timeline("vertical", 7)]}]), report=report2)
        assert not any("容量上限" in w for w in report2.warnings)


# ---------------------------------------------------------------------------
# 收尾：product_intro_placeholder 页底防线
# ---------------------------------------------------------------------------

def _minimal_spec(pages):
    return {"confirmed": True, "author": "测试", "document": {"title": "T"},
            "pages": pages}


def _build(spec, report=None):
    import _pptd_gen
    from _renderer import _resolve_style
    from _renderer.elements import RenderReport
    out_dir = os.path.join("output", "通用", "_baseline_work", "test_table_hug")
    return _pptd_gen.build_deck(spec, "spec.yml", _resolve_style("enterprise"),
                                "deck", out_dir, report=report or RenderReport())


def _tall_text(n_lines):
    """占 n_lines 行的 text 元素（每段 30 字 1 行，行高 14×1.65）。"""
    return {"type": "text", "content": "\n".join(f"第{i}段" + "字" * 27 for i in range(n_lines))}


class TestPlaceholderClamp:
    def test_over_height_clamped_with_warn(self):
        """占位块底边超线：均匀缩进可用高度 + report.warn，底边贴 674 防线。"""
        from _renderer.elements import RenderReport
        report = RenderReport()
        # text 20 行 h=462 -> y_cursor=604；占位 200 高超 674，可用 70
        spec = _minimal_spec([{"id": "p1", "title": "页", "elements": [
            _tall_text(20),
            {"type": "product_intro_placeholder", "title": "产品介绍"}]}])
        files, _ = _build(spec, report=report)
        page = yaml.safe_load(files["pages/02_p1.page"])
        ph = [e for e in page["elements"] if str(e["elementId"]).startswith("pi")]
        assert ph, "占位块应仍存在（裁剪而非跳过）"
        bottom = max(float(e["bounds"][1]) + float(e["bounds"][3]) for e in ph)
        assert bottom <= 674 + 1e-6
        assert any("高度裁切防溢出" in w for w in report.warnings)
        assert not report.skipped

    def test_less_than_one_line_skips(self):
        """可用空间不足一行（< 20×1.3）：整元素 skip 进 report，不 emit 碎片。"""
        from _renderer.elements import RenderReport
        report = RenderReport()
        # text 23 行 h=531.3 -> y_cursor=673.3；可用 0.7 < 26 -> skip
        spec = _minimal_spec([{"id": "p1", "title": "页", "elements": [
            _tall_text(23),
            {"type": "product_intro_placeholder", "title": "产品介绍"}]}])
        files, _ = _build(spec, report=report)
        page = yaml.safe_load(files["pages/02_p1.page"])
        ph = [e for e in page["elements"] if str(e["elementId"]).startswith("pi")]
        assert ph == []
        assert any(s["type"] == "product_intro_placeholder" and "不足一行" in s["reason"]
                   for s in report.skipped)


# ---------------------------------------------------------------------------
# 原生 table 元素行高 hug（与 6 个 diagram 表格 subtype 同口径，间距体系 v1 §五）
# ---------------------------------------------------------------------------

class TestNativeTableHug:
    """_pptd_gen._emit_table 接 table_hug_geometry：长文本单元格撑高所在行，
    短内容与原均分公式逐字节一致；撑高超页走现有页底防线。"""

    def test_long_cell_grows_row(self):
        import _pptd_gen
        elements = []
        table_h = _pptd_gen._emit_table(
            elements, ["维度", "说明"], [["短", "短"], ["长", L60 * 4]], 80, 130, 1120)
        t = elements[0]
        assert table_h > 3 * 36, "长文本行撑高应超原写死 108"
        assert t["bounds"][3] == table_h
        fracs = t["rowHeights"]
        assert fracs[2] > fracs[1], "长文本行应比短行高"
        assert abs(sum(fracs) - 1.0) < 1e-6

    def test_short_content_unchanged(self):
        """短内容（各行下限 ≥ 一行实高）：与原均分公式逐字节一致。"""
        import _pptd_gen
        elements = []
        table_h = _pptd_gen._emit_table(
            elements, ["甲", "乙"], [[f"r{i}", "x"] for i in range(9)], 80, 130, 1120)
        t = elements[0]
        assert table_h == 360  # 10 行 × 36
        assert t["bounds"][3] == 360
        assert t["rowHeights"] == [0.1] * 10

    def test_over_tall_table_walks_existing_clamp(self):
        """hug 撑高超页走现有防线：_clamp_bottom 裁切 + warn（行高等比压缩）。"""
        from _renderer.elements import RenderReport
        report = RenderReport()
        # text 20 行推 y_cursor≈604；长单元格表 hug 后 ≈218 超 674，可用 ≈70
        spec = _minimal_spec([{"id": "p1", "title": "表", "elements": [
            _tall_text(20),
            {"type": "table", "headers": ["维度", "说明"],
             "rows": [["短", "短"], ["长", L60 * 4]]}]}])
        files, _ = _build(spec, report=report)
        page = yaml.safe_load(files["pages/02_p1.page"])
        t = next(e for e in page["elements"] if e["elementType"] == "table")
        y, h = t["bounds"][1], t["bounds"][3]
        assert y + h <= 674 + 1e-6, "裁剪后底边应在内容区内"
        assert h < 218, "hug 后原高应被裁小"
        assert report.skipped == []
        assert any("高度裁切防溢出" in w for w in report.warnings)
