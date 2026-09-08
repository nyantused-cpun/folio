# -*- coding: utf-8 -*-
"""P3「材料/spec」组回归（全库审查 2026-09-06 §五，修复批次 B）。

覆盖五项（detect_format 一项在 tests/test_doc_extract.py）：
  - LLM 提取缓存：JSON 数组结果同键可命中（修复前入缓存永不命中，重跑白烧 token）
  - diagram_result_cacheable：非 dict 结果 fail-closed 不可缓存且不裸崩
  - build_elements table 分支：key_points 非 str 与 cards/phases 分支同口径 str 化
  - read_pptx：组合形状（含嵌套 GroupShape）递归下钻，组合内文本不再静默丢失
  - _valid_module_gantt：gantt col 浮点按四舍五入显式取整（1.0 → 第 1 列，不再归 0）
  - ROLE_ELEMENT_KIND：governance 补 table 回退形态（P07 页必需构件）
"""
import json

import pytest

import _diagram_extract as DX
import _outline_to_spec
import _pipeline
from _outline_to_spec import build_elements, extract_section_content

# ── 修2：LLM 提取缓存数组归一化 ────────────────────────────────────────────

_ARRAY_RESP = json.dumps(
    [{"title": "数组形态", "content": "正文", "key_points": ["要点"]}],
    ensure_ascii=False)


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    """隔离缓存文件到 tmp + 计数 fake chat（对齐 test_llm_extract_cache 约定）。"""
    monkeypatch.setattr(_outline_to_spec, "LLM_EXTRACT_CACHE_PATH",
                        str(tmp_path / "llm_extract_cache.json"))
    import _cloud_llm
    calls = {"n": 0}

    def _fake_chat(prompt, **kwargs):
        calls["n"] += 1
        return _ARRAY_RESP

    monkeypatch.setattr(_cloud_llm, "chat", _fake_chat)
    return calls


def test_array_result_hits_cache_on_rerun(cache_env, capsys):
    """LLM 返回 JSON 数组：入缓存且同键可命中，同章节重跑不再调 LLM。

    修复前读取门只认 dict，数组条目永不命中，每次重跑白烧一次 token。
    """
    sec = {"section": "项目目标", "role": "goals", "children": [], "prompt": ""}
    r1 = extract_section_content(sec, "材料文本" * 500, client_name="测试客户")
    assert isinstance(r1, list)
    r2 = extract_section_content(sec, "材料文本" * 500, client_name="测试客户")
    assert cache_env["n"] == 1  # 修复前：n == 2
    assert r1 == r2
    assert "命中 LLM 提取缓存" in capsys.readouterr().out


def test_dict_result_cache_path_unchanged(cache_env, monkeypatch):
    """既有命中路径不回归：dict 结果第二次仍命中（缓存归一化不得破坏现状）。"""
    import _cloud_llm

    def _dict_chat(prompt, **kwargs):
        cache_env["n"] += 1
        return '{"title": "t", "content": "c", "key_points": ["k"], "data": []}'

    monkeypatch.setattr(_cloud_llm, "chat", _dict_chat)
    sec = {"section": "项目概况", "role": "overview", "children": [], "prompt": ""}
    r1 = extract_section_content(sec, "材料文本" * 500, client_name="测试客户")
    r2 = extract_section_content(sec, "材料文本" * 500, client_name="测试客户")
    assert isinstance(r1, dict) and isinstance(r2, dict)
    assert cache_env["n"] == 1
    assert r1 == r2


def test_diagram_cache_gate_rejects_nondict_without_crash():
    """图形 role 的数组/None 结果 fail-closed 不可缓存。

    修复前 _valid_* 对非 dict 结果 .get 裸 AttributeError 从缓存写门户逃逸。
    """
    assert DX.diagram_result_cacheable({"role": "pain_points"}, [{"title": "x"}]) is False
    assert DX.diagram_result_cacheable({"role": "pain_points"}, None) is False
    # 非图形 role 恒 True 的既有语义不变（test_b3_parse_pipeline 同款断言）
    assert DX.diagram_result_cacheable({"role": "goals"}, None) is True


# ── 修3：table 分支 key_points str 化 ──────────────────────────────────────

def test_build_elements_table_strifies_key_points():
    """progress（table 形态）key_points 混入数字：rows 单元格统一为 str。

    修复前裸 int/float 直落 rows，下游 verify/渲染端类型漂移。
    """
    result = {"content": "正文", "key_points": [1, 2.5, "文字要点"], "data": []}
    els = build_elements(result, {"section": "项目进度", "role": "progress"})
    assert els[0]["type"] == "table"
    rows = els[0]["rows"]
    assert [r[0] for r in rows] == ["1", "2.5", "文字要点"]
    assert all(isinstance(r[0], str) for r in rows)


# ── 修4：read_pptx 组合形状下钻 ────────────────────────────────────────────

def test_read_pptx_digs_into_group_shapes(tmp_path):
    """组合形状（含嵌套 GroupShape）内文本必须读出。

    修复前只扫顶层 shapes，组合内文本/表格静默丢读。
    """
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    tb.text_frame.text = "外层文本"
    grp = slide.shapes.add_group_shape()
    sub = grp.shapes.add_textbox(Inches(2), Inches(2), Inches(3), Inches(1))
    sub.text_frame.text = "组合内文本"
    nested = grp.shapes.add_group_shape()
    t2 = nested.shapes.add_textbox(Inches(3), Inches(3), Inches(2), Inches(1))
    t2.text_frame.text = "嵌套内文本"
    p = tmp_path / "group_shapes.pptx"
    prs.save(str(p))

    text = _pipeline.read_pptx(str(p))
    assert "外层文本" in text
    assert "组合内文本" in text
    assert "嵌套内文本" in text


# ── 修5：gantt col 浮点显式取整 ────────────────────────────────────────────

def test_module_gantt_col_float_rounds_instead_of_zeroing():
    """gantt col 浮点按四舍五入取整：1.0 → 第 1 列（修复前静默归第 0 列）。"""
    norm = DX._valid_module_gantt({
        "columns": ["调研", "设计", "开发"],
        "groups": [{"name": "一期", "modules": [
            {"label": "需求确认", "col": 1.0},
            {"label": "方案设计", "col": 2.0},
        ]}],
        "markers": [{"col": 2.0, "label": "验收", "note": "里程碑"}],
    })
    assert norm is not None
    assert [m["col"] for m in norm["groups"][0]["modules"]] == [1, 2]
    assert norm["markers"][0]["col"] == 2


def test_module_gantt_col_edge_semantics_preserved():
    """越界收敛、bool 排除、非法类型归 0 的既有语义不变。"""
    norm = DX._valid_module_gantt({
        "columns": ["甲", "乙"],
        "groups": [{"name": "g", "modules": [
            {"label": "a", "col": 9.6},   # 四舍五入 10 → 越界收敛末列 1
            {"label": "b", "col": True},  # bool 是 int 子类，须排除不当作 1
            {"label": "c", "col": "x"},   # 非法类型仍归 0
        ]}],
    })
    assert [m["col"] for m in norm["groups"][0]["modules"]] == [1, 0, 0]


# ── 修6：ROLE_ELEMENT_KIND 补 governance ──────────────────────────────────

def test_governance_fallback_produces_p07_table():
    """governance 补 table 形态：raci 校验不过时回退页有 P07 必需的 table 构件。

    修复前缺键走 title_body 默认（text+bullets），P07 对比表页缺表格构件。
    """
    assert DX.ROLE_LAYOUT["governance"] == "P07"  # 前提：版式映射在案
    result = {"content": "治理正文", "key_points": ["职责矩阵", "例会机制"],
              "data": []}
    els = build_elements(result, {"section": "治理保障", "role": "governance"})
    assert els[0]["type"] == "table"
