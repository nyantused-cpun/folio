# -*- coding: utf-8 -*-
"""叙事设计单一致性 + stage 密度观察测试（条目 2-4 / 2-7，决策 D-c=A / D-a=A）。

四类检查各覆盖：命中 + 豁免；stage 密度正反例；设计单缺失/坏 YAML 降级。
_renderer.narrative_schema 由并发子代理新建，此处按钉死契约
（load_and_validate(path) -> (doc | None, [错误...])）打桩，
本文件只测 _verify 侧的检查逻辑。
"""
import os
import sys
import types

import pytest
import yaml

from _verify import (
    check_narrative_consistency,
    check_stage_density,
    verify_spec_layout_data,
)

SPEC_NAME = "测试客户_方案_spec_v0.yml"
DOC_NAME = "测试客户_叙事设计_v1.yml"


def _check(spec, spec_path=None):
    """0c：check_narrative_consistency 返回 (errors, warnings)，
    合并为单一列表兼容本文件断言风格（页面集合/页数预算已升 error）。"""
    out = check_narrative_consistency(spec, spec_path=spec_path)
    if isinstance(out, tuple) and len(out) == 2:
        return list(out[0]) + list(out[1])
    return out




@pytest.fixture
def narrative_stub(monkeypatch):
    """按钉死契约打桩 _renderer.narrative_schema.load_and_validate。"""
    mod = types.ModuleType("_renderer.narrative_schema")

    def load_and_validate(path):
        if not os.path.exists(path):
            return None, ["文件不存在"]
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return None, [f"坏 YAML: {e}"]
        if not isinstance(data, dict) or not isinstance(
                data.get("page_map"), list):
            return None, ["顶层结构不符"]
        return data, []

    mod.load_and_validate = load_and_validate
    monkeypatch.setitem(sys.modules, "_renderer.narrative_schema", mod)
    return mod


def _write(tmp_path, name, obj):
    p = tmp_path / name
    if isinstance(obj, str):
        p.write_text(obj, encoding="utf-8")
    else:
        p.write_text(yaml.safe_dump(obj, allow_unicode=True),
                     encoding="utf-8")
    return str(p)


def _spec(pages, **kw):
    base = {"confirmed": True, "narrative_ref": DOC_NAME, "pages": pages}
    base.update(kw)
    return base


def _doc(page_map, **kw):
    base = {"audience": "CIO", "reading": "scroll", "page_budget": 10,
            "page_map": page_map}
    base.update(kw)
    return base


def _page(pid, elements=None):
    return {"id": pid, "elements": elements or []}


def _diagram(fam, sub):
    return {"type": "diagram", "diagram_type": fam, "subtype": sub}


# ---------- 豁免：无 narrative_ref ----------

def test_no_narrative_ref_returns_empty(tmp_path, narrative_stub):
    spec_path = _write(tmp_path, SPEC_NAME,
                       {"confirmed": True, "pages": [_page("p1")]})
    assert _check(
        {"confirmed": True, "pages": [_page("p1")]}, spec_path=spec_path) == []


# ---------- 检查①：页面集合一致 ----------

def test_page_set_mismatch_both_directions(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME,
           _doc([{"page": "p1", "beat": "现状"},
                 {"page": "p2", "beat": "蓝图"}]))
    spec = _spec([_page("p1"), _page("p3")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    hit = [m for m in msgs if "页面集合不一致" in m]
    assert len(hit) == 1
    assert "p3" in hit[0] and "p2" in hit[0]  # 双向差集都列出


def test_page_set_match_no_hint(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME,
           _doc([{"page": "p1", "beat": "现状"}, {"page": "p2", "beat": "蓝图"}]))
    spec = _spec([_page("p1"), _page("p2")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert not any("页面集合不一致" in m for m in msgs)


def test_auto_page_ids_exempted(tmp_path, narrative_stub):
    """生成侧 chapters 容器自动补的 P02/P12 页（id 前缀 auto_）豁免集合比对。"""
    _write(tmp_path, DOC_NAME, _doc([{"page": "p1", "beat": "现状"}]))
    spec = _spec([_page("p1"), _page("auto_toc"), _page("auto_section_1")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert not any("页面集合不一致" in m for m in msgs)


# ---------- 检查②：页数预算 ----------

def test_page_budget_exceeded(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME,
           _doc([{"page": "p1", "beat": "a"}, {"page": "p2", "beat": "b"},
                 {"page": "p3", "beat": "c"}], page_budget=2))
    spec = _spec([_page("p1"), _page("p2"), _page("p3")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert any("page_budget=2" in m and "超 1 页" in m for m in msgs)


def test_page_budget_ok_no_hint(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME,
           _doc([{"page": "p1", "beat": "a"}, {"page": "p2", "beat": "b"}],
                page_budget=2))
    spec = _spec([_page("p1"), _page("p2")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert not any("page_budget" in m for m in msgs)


# ---------- 检查③：八环节覆盖（scene 命中规划类） ----------

def _plan_doc(beats):
    return _doc([{"page": f"p{i + 1}", "beat": b}
                 for i, b in enumerate(beats)],
                scene="信息化规划")


def test_eight_steps_missing_after_blueprint(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME, _plan_doc(["现状", "蓝图", "治理"]))
    spec = _spec([_page("p1"), _page("p2"), _page("p3")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert any("缺「差距」" in m for m in msgs)
    assert any("缺「演进」" in m for m in msgs)
    assert not any("缺「治理」" in m for m in msgs)


def test_eight_steps_order_inverted(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME,
           _plan_doc(["差距", "蓝图", "演进", "治理"]))
    spec = _spec([_page("p1"), _page("p2"), _page("p3"), _page("p4")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert any("「差距」出现在「蓝图」之前" in m and "顺序倒置" in m
               for m in msgs)
    assert not any("「演进」出现在" in m for m in msgs)


def test_eight_steps_full_sequence_no_hint(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME,
           _plan_doc(["现状", "蓝图", "差距", "演进", "治理", "交付"]))
    spec = _spec([_page(f"p{i}") for i in range(1, 7)])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert not any("八环节" in m for m in msgs)


def test_eight_steps_exempt_non_planning_scene(tmp_path, narrative_stub):
    """scene 非规划类（不含「规划」/「顶层设计」）→ 不检查八环节。"""
    _write(tmp_path, DOC_NAME,
           _doc([{"page": "p1", "beat": "现状"}], scene="产品汇报"))
    spec = _spec([_page("p1")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert not any("八环节" in m for m in msgs)


# ---------- 检查④：图形意图落地 ----------

def _graphic_doc(graphic, pid="p1"):
    return _doc([{"page": pid, "beat": "蓝图", "graphic": graphic}])


def test_graphic_intent_no_diagram(tmp_path, narrative_stub):
    """意图图形化、落地纯文字。"""
    _write(tmp_path, DOC_NAME, _graphic_doc("flow/flow_rows"))
    spec = _spec([_page("p1", [{"type": "bullets", "items": ["a"]}])])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert any("意图图形化" in m and "落地纯文字" in m for m in msgs)


def test_graphic_intent_family_mismatch(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME, _graphic_doc("flow/flow_rows"))
    spec = _spec([_page("p1", [_diagram("matrix", "raci_matrix")])])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert any("图形族不符" in m for m in msgs)


def test_graphic_intent_subtype_mismatch_light_hint(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME, _graphic_doc("flow/flow_rows"))
    spec = _spec([_page("p1", [_diagram("flow", "milestone_gantt")])])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert any("subtype 轻提示" in m for m in msgs)


def test_graphic_intent_exact_match_no_hint(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME, _graphic_doc("flow/flow_rows"))
    spec = _spec([_page("p1", [_diagram("flow", "flow_rows")])])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert msgs == []


def test_graphic_null_no_hint(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME, _graphic_doc(None))
    spec = _spec([_page("p1")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert msgs == []


# ---------- 降级：设计单不可读 ----------

def test_missing_doc_file_degrades(tmp_path, narrative_stub):
    spec = _spec([_page("p1")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)  # 设计单文件不写
    msgs = _check(spec, spec_path=spec_path)
    assert len(msgs) == 1
    assert "设计单不可读，跳过叙事一致性检查" in msgs[0]
    assert msgs[0].startswith("[观察]")


def test_bad_yaml_doc_degrades(tmp_path, narrative_stub):
    _write(tmp_path, DOC_NAME, ":\n  - [unclosed")
    spec = _spec([_page("p1")])
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    msgs = _check(spec, spec_path=spec_path)
    assert len(msgs) == 1
    assert "设计单不可读，跳过叙事一致性检查" in msgs[0]


def test_no_spec_path_degrades():
    msgs = _check(_spec([_page("p1")]), spec_path=None)
    assert len(msgs) == 1
    assert "设计单不可读，跳过叙事一致性检查" in msgs[0]


# ---------- D2：stage 容器单页密度 ----------

def _many_elements(n):
    return [{"type": "text", "content": f"x{i}"} for i in range(n)]


def test_stage_density_over_5_warns():
    spec = {"container": "stage",
            "pages": [_page("p1", _many_elements(6))]}
    msgs = check_stage_density(spec)
    assert msgs == ["[观察] stage 为翻页演讲容器，单页元素建议 ≤5"
                    "（第 1 页 6 个）"]


def test_stage_density_at_5_no_hint():
    spec = {"container": "stage",
            "pages": [_page("p1", _many_elements(5))]}
    assert check_stage_density(spec) == []


def test_stage_density_non_stage_container_no_hint():
    spec = {"container": "scroll",
            "pages": [_page("p1", _many_elements(8))]}
    assert check_stage_density(spec) == []


# ---------- 挂载点：verify_spec_layout_data 汇聚 + 永不阻断 ----------

def test_mounted_in_verify_spec_layout_data(tmp_path, narrative_stub):
    """verify_spec_layout_data(spec, spec_path=) 汇聚两类观察且不影响 ok。"""
    _write(tmp_path, DOC_NAME, _graphic_doc("flow/flow_rows"))
    spec = _spec([_page("p1", _many_elements(6))], container="stage")
    spec_path = _write(tmp_path, SPEC_NAME, spec)
    ok, errors, warnings = verify_spec_layout_data(spec, spec_path=spec_path)
    assert ok and errors == []
    assert any("落地纯文字" in w for w in warnings)
    assert any("stage 为翻页演讲容器" in w for w in warnings)
