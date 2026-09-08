# -*- coding: utf-8 -*-
"""S8-A 2×3 合规矩阵机械执行测试（crafted 定制页轨，crafted-track.md）。

覆盖：
- weaver×crafted：默认禁止（阻断 error）；spec 顶层
  crafted_special_approval: true 特批放行；特批值非严格 true 不放行
- syzygit / generic（含 legacy style / 缺省主题）× crafted：不阻断
- 非 crafted 的 weaver spec：零影响（存量兼容）
- 每 deck crafted 页数：3 页 warning、2 页无 warning
- crafted 计数双源：叙事单 page_map（expression_mode）与 raw_html 硬信号
- 挂载点：Renderer.__init__ 前置阻断/告警 + verify_spec_layout_data 同门汇聚
"""
import os
import sys

import pytest
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer import RenderBlockedError
from _renderer.narrative_schema import (
    APPROVAL_FIELD, CRAFTED_MAX_PAGES, check_compliance_matrix,
    collect_crafted_pages, resolve_spec_theme_key,
)
from _verify import verify_spec_layout_data


def _raw_html(content="<div class=\"hero\">主视觉</div>"):
    return {"type": "raw_html", "content": content}


def _page(pid, elements=None):
    return {"id": pid, "elements": elements if elements is not None
            else [_raw_html()]}


def _spec(theme=None, pages=None, **kw):
    spec = {"confirmed": True,
            "pages": pages if pages is not None else [_page("p1")]}
    if theme is not None:
        spec["theme"] = theme
    spec.update(kw)
    return spec


def _narrative_page(pid):
    return {"page": pid, "beat": "蓝图", "讲法": "data_narrative",
            "layout": "P04", "expression_mode": "crafted",
            "primary_expression": "主视觉", "static_equivalent": "架构图",
            "density": "low"}


def _narrative_doc(pids):
    return {"audience": "客户高层", "reading": "scroll", "page_budget": 12,
            "arc": "现状→蓝图", "page_map": [_narrative_page(p) for p in pids]}


def _write_yaml(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(obj, allow_unicode=True), encoding="utf-8")
    return str(p)


# ---------- 主题归一 ----------

def test_theme_key_resolution():
    assert resolve_spec_theme_key(_spec("weaver_blue")) == "weaver_blue"
    assert resolve_spec_theme_key({"style": "syzygit"}) == "syzygit"
    assert resolve_spec_theme_key({}) == "consulting_kpmg"  # generic 兜底
    # theme 优先于旧 style 字段
    assert resolve_spec_theme_key(
        _spec("weaver_blue", style="enterprise")) == "weaver_blue"


# ---------- 机械点 A：weaver×crafted 默认禁止 + 特批 ----------

def test_weaver_crafted_blocked_without_approval():
    errors, warnings = check_compliance_matrix(_spec("weaver_blue"))
    assert len(errors) == 1
    assert APPROVAL_FIELD in errors[0]
    assert "decisions.md" in errors[0]
    assert warnings == []


@pytest.mark.parametrize("approval", [None, False, "true", 1])
def test_weaver_crafted_approval_must_be_strict_true(approval):
    errors, _w = check_compliance_matrix(_spec("weaver_blue", **{
        APPROVAL_FIELD: approval}))
    assert len(errors) == 1


def test_weaver_crafted_special_approval_passes():
    out = check_compliance_matrix(_spec("weaver_blue", **{
        APPROVAL_FIELD: True}))
    assert out == ([], [])


def test_syzygit_crafted_allowed():
    assert check_compliance_matrix(_spec("syzygit")) == ([], [])


def test_generic_crafted_allowed():
    assert check_compliance_matrix(_spec()) == ([], [])


def test_legacy_style_crafted_allowed():
    # legacy 旧 style 映射后非 weaver（education -> consulting_kpmg）
    assert check_compliance_matrix(_spec(None, style="education")) == ([], [])


def test_weaver_without_crafted_zero_impact():
    spec = _spec("weaver_blue", pages=[
        {"id": "p1", "elements": [{"type": "bullets", "items": ["a"]}]}])
    assert check_compliance_matrix(spec) == ([], [])


# ---------- 机械点 B：每 deck crafted ≤2 页（观察级） ----------

def test_crafted_three_pages_warns():
    spec = _spec(pages=[_page("p1"), _page("p2"), _page("p3")])
    errors, warnings = check_compliance_matrix(spec)
    assert errors == []
    assert len(warnings) == 1
    assert "3 页" in warnings[0] and str(CRAFTED_MAX_PAGES) in warnings[0]
    assert "稀缺性" in warnings[0] and "拆页" in warnings[0]


def test_crafted_two_pages_no_warning():
    assert check_compliance_matrix(
        _spec(pages=[_page("p1"), _page("p2")])) == ([], [])


def test_crafted_count_dedup_raw_html_and_sheet(tmp_path):
    """同一页 raw_html 与叙事单 crafted 双源去重，不重复计数。"""
    doc_path = _write_yaml(tmp_path, "叙事设计_v1.yml", _narrative_doc(["p1"]))
    spec = _spec(pages=[_page("p1")], narrative_ref="叙事设计_v1.yml")
    assert collect_crafted_pages(spec, spec_path=doc_path) == ["p1"]


def test_crafted_count_via_narrative_sheet_without_raw_html(tmp_path):
    """叙事单标 crafted 而 spec 页尚无 raw_html：设计意图源生效。"""
    doc_path = _write_yaml(tmp_path, "叙事设计_v1.yml",
                           _narrative_doc(["p1", "p2", "p3"]))
    spec = _spec("weaver_blue",
                 pages=[_page(f"p{i}", [{"type": "bullets", "items": ["x"]}])
                        for i in (1, 2, 3)],
                 narrative_ref="叙事设计_v1.yml")
    errors, warnings = check_compliance_matrix(spec, spec_path=doc_path)
    assert len(errors) == 1  # 设计单为准 → weaver 照拦
    assert len(warnings) == 1  # 3 页 > 2 → 照告警


def test_unreadable_narrative_sheet_falls_back_to_raw_html(tmp_path):
    spec = _spec(pages=[_page("p1"), _page("p2")],
                 narrative_ref="不存在的叙事单.yml")
    assert collect_crafted_pages(spec, spec_path=str(tmp_path)) == ["p1", "p2"]


# ---------- 挂载点①：Renderer.__init__ 前置（html-build 前置即拦） ----------

def _write_spec(tmp_path, spec, name="spec.yml"):
    return _write_yaml(tmp_path, name, spec)


def test_renderer_blocks_weaver_crafted(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    from _renderer import Renderer
    spec_path = _write_spec(tmp_path, _spec("weaver_blue"))
    with pytest.raises(RenderBlockedError) as exc_info:
        Renderer(spec_path)
    assert APPROVAL_FIELD in str(exc_info.value)


def test_renderer_weaver_crafted_approval_constructs(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    from _renderer import Renderer
    spec_path = _write_spec(tmp_path, _spec("weaver_blue", **{
        APPROVAL_FIELD: True}))
    r = Renderer(spec_path)
    assert not any("合规矩阵" in w or "稀缺性" in w for w in r.report.warnings)


def test_renderer_crafted_over_limit_warns(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    from _renderer import Renderer
    spec = _spec(pages=[_page("p1"), _page("p2"), _page("p3")])
    r = Renderer(_write_spec(tmp_path, spec))
    assert any("稀缺性" in w and "拆页" in w for w in r.report.warnings)


def test_renderer_weaver_without_crafted_zero_impact(tmp_path, monkeypatch):
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    from _renderer import Renderer
    spec = _spec("weaver_blue", pages=[
        {"id": "p1", "elements": [{"type": "bullets", "items": ["a"]}]}])
    r = Renderer(_write_spec(tmp_path, spec))
    assert not any("稀缺性" in w or "合规矩阵" in w for w in r.report.warnings)


# ---------- 挂载点②：verify_spec_layout_data 同门汇聚 ----------

def test_verify_blocks_weaver_crafted():
    ok, errors, _warnings = verify_spec_layout_data(_spec("weaver_blue"))
    assert not ok
    assert any(APPROVAL_FIELD in e for e in errors)


def test_verify_weaver_crafted_approval_ok():
    ok, errors, _warnings = verify_spec_layout_data(_spec("weaver_blue", **{
        APPROVAL_FIELD: True}))
    assert ok and errors == []
