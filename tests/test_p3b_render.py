# -*- coding: utf-8 -*-
"""P3 渲染器组回归测试（2026-09-06 审查报告 §五 渲染器 5 项）。

- P3-1：page_chrome.render_topnav 页标题为 YAML 数字时不崩，渲染前归一字符串
- P3-2：html_editor_injector.inject 幂等，重复执行不产出双份工具条
- P3-3：schema.harvey_balls value 校验排除 bool（对齐 bar/waterfall 范式）
- P3-4：纯占位页也注入 diagram CSS 外壳（含 diagram/纯文本页判定零 diff）
- P3-5：docx 编号风格命名统一归一（别名单点事实源），chapter 不再退化平铺
"""

import os
import sys

import pytest
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer import Renderer
from _renderer.docx_com_postprocess import (
    _manual_numbering, com_postprocess, normalize_numbering_style)
from _renderer.elements import normalize_element
from _renderer.html_editor_injector import inject
from _renderer.page_chrome import render_chrome_html
from _renderer.schema import validate_element

WORK_DIR = os.path.join(SCRIPT_DIR, "output", "通用", "_test_p3b_render")


@pytest.fixture(autouse=True)
def _cli_env():
    """Renderer 要求 _PRESALES_CLI_INVOKED=1；保存/还原避免污染其他测试。"""
    saved = os.environ.pop("_PRESALES_CLI_INVOKED", None)
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("_PRESALES_CLI_INVOKED", None)
        else:
            os.environ["_PRESALES_CLI_INVOKED"] = saved


@pytest.fixture
def work_dir():
    """HTML 输出目录（_validate_output_path 白名单在 output/ 内）。"""
    os.makedirs(WORK_DIR, exist_ok=True)
    yield WORK_DIR
    import shutil
    shutil.rmtree(WORK_DIR, ignore_errors=True)


def _write_spec(tmp_path, spec):
    spec = {"confirmed": True, **spec}
    spec_path = os.path.join(str(tmp_path), "spec.yml")
    with open(spec_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, allow_unicode=True)
    return spec_path


def _render_html(tmp_path, work_dir, spec):
    r = Renderer(_write_spec(tmp_path, spec))
    out = os.path.join(work_dir, "out.html")
    r.render_html(out)
    with open(out, encoding="utf-8") as f:
        return r, f.read()


# ---- P3-1：页标题为 YAML 数字时 topnav 崩 ----


def _topnav_html(pages):
    _type, normalized = normalize_element({"type": "topnav", "brand": "ACME"})
    return render_chrome_html("topnav", normalized, pages=pages)


def test_topnav_numeric_page_title_no_crash():
    """页标题为 int/float（YAML 数字）时不再 TypeError，标签归一为字符串。"""
    html = _topnav_html([
        {"id": "p1", "title": 2024},
        {"id": "p2", "title": 3.5},
        {"id": "p3", "title": "常规：标题"},
    ])
    assert '<a class="nav-link" href="#p1" title="2024">2024</a>' in html
    assert '<a class="nav-link" href="#p2" title="3.5">3.5</a>' in html
    # 字符串标题路径零 diff：冒号截断等 _nav_label 语义不变
    assert '<a class="nav-link" href="#p3" title="常规：标题">常规</a>' in html


def test_topnav_none_title_still_skipped():
    """title: null（YAML 空值）保持跳过（str(None) 不允许渲染成 'None'）。"""
    html = _topnav_html([{"id": "p1", "title": None}, {"id": "p2", "title": "章节"}])
    assert 'href="#p1"' not in html
    assert 'href="#p2"' in html


# ---- P3-2：inject 非幂等，重复执行双份工具条 ----


def test_editor_inject_idempotent(tmp_path):
    """重复 inject 不叠加：工具条/编辑态/脚本引用各恰好一份，两次结果逐字节一致。"""
    path = tmp_path / "doc.html"
    path.write_text(
        "<!DOCTYPE html><html><head><title>t</title></head>"
        "<body><p>正文</p></body></html>", encoding="utf-8")

    inject(str(path))
    first = path.read_text(encoding="utf-8")
    inject(str(path))
    second = path.read_text(encoding="utf-8")

    assert first == second
    assert first.count('id="__editor_toolbar"') == 1
    assert first.count('data-edit-mode="preview"') == 1
    assert first.count("_assets/editor.js") == 1


# ---- P3-3：harvey_balls value 未排除 bool ----


def _harvey_elem(value):
    return {"type": "diagram", "diagram_type": "matrix", "subtype": "harvey_balls",
            "title": "对比", "rows": ["A"], "columns": ["X"],
            "cells": [{"row": "A", "col": "X", "value": value}]}


def test_harvey_balls_bool_value_rejected():
    """value: true/false 是合法 int 的子类，必须显式拒绝（bar/waterfall 同范式）。"""
    for v in (True, False):
        errors = validate_element(_harvey_elem(v))
        assert any(".value" in e for e in errors), v


def test_harvey_balls_int_value_still_valid():
    """0-4 整数合法值行为不变。"""
    assert validate_element(_harvey_elem(2)) == []
    for v in (-1, 5, "2", 2.0):
        assert any(".value" in e for e in validate_element(_harvey_elem(v))), v


# ---- P3-4：纯占位页缺 diagram CSS 外壳 ----


def test_placeholder_only_page_gets_diagram_css(tmp_path, work_dir):
    """只有 product_intro_placeholder 的页面也输出 section.diagram CSS 外壳。"""
    _, html = _render_html(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "占位页", "elements": [
            {"type": "product_intro_placeholder", "title": "产品介绍"}]}]})
    assert 'class="diagram product-intro-placeholder"' in html
    assert "section.diagram {" in html  # 外壳卡底色/圆角/边距规则
    assert "--blue:" in html            # css_variables :root 变量块


def test_diagram_css_judgement_zero_diff(tmp_path, work_dir):
    """判定扩展不得误伤：纯文本页仍不注入、diagram 页照常注入（零 diff）。

    标记用 --blue:（css_variables/bridge_css 专属，chrome_css 的
    section.diagram 选择器常驻，不能作判别）。
    """
    _, text_only = _render_html(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "页", "elements": [
            {"type": "text", "content": "正文"}]}]})
    assert "--blue:" not in text_only

    _, with_diagram = _render_html(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "流程页", "elements": [
            {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
             "title": "流程", "steps": [{"label": "a"}, {"label": "b"}]}]}]})
    assert "--blue:" in with_diagram


# ---- P3-5：两套编号风格命名体系互不认，chapter 静默退化平铺 ----


def _headings(doc):
    return [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]


def _make_doc():
    from docx import Document
    doc = Document()
    doc.add_heading("总体方案", level=1)
    doc.add_heading("项目背景", level=2)
    doc.add_heading("建设目标", level=2)
    doc.add_heading("实施计划", level=1)
    doc.add_heading("阶段安排", level=2)
    return doc


class TestNumberingStyleUnified:
    def test_normalize_numbering_style(self):
        """别名/大小写归一到 canonical；未知回退 chinese_multi 并报 known=False。"""
        assert normalize_numbering_style("chinese_multi_level") == ("chinese_multi", True)
        assert normalize_numbering_style("CHAPTER") == ("chapter", True)
        assert normalize_numbering_style(" legal ") == ("legal", True)
        assert normalize_numbering_style("chinese_multi") == ("chinese_multi", True)
        assert normalize_numbering_style("nonsense") == ("chinese_multi", False)
        assert normalize_numbering_style(None) == ("chinese_multi", False)

    def test_chapter_style_not_flat(self):
        """numbering_style: chapter 在手动编号路径出章节层级，不再平铺 n.。"""
        texts = _headings(_apply("chapter"))
        assert texts[0].startswith("第一章 ")
        assert texts[1].startswith("1.1 ")
        assert texts[2].startswith("1.2 ")
        assert texts[3].startswith("第二章 ")
        assert texts[4].startswith("2.1 ")

    def test_legal_and_simple_styles(self):
        """legal / simple 同样经归一生效（原均被当未知风格平铺）。"""
        texts = _headings(_apply("legal"))
        assert texts[0].startswith("第1条 ")
        assert texts[1].startswith("1.1 ")
        texts = _headings(_apply("simple"))
        assert texts[0].startswith("1 ")
        assert texts[1].startswith("1.1 ")

    def test_alias_matches_legacy_default_output(self):
        """chinese_multi_level（历史缺省名）与显式 chinese_multi 输出逐字一致。"""
        d1 = _make_doc()
        _manual_numbering(d1)
        d2 = _make_doc()
        _manual_numbering(d2, "chinese_multi_level")
        d3 = _make_doc()
        _manual_numbering(d3, "chinese_multi")
        t1, t2, t3 = _headings(d1), _headings(d2), _headings(d3)
        assert t1 == t2 == t3
        # 二级半角括号历史输出保持（基线测试在案）
        assert t1[1].startswith("(一)")

    def test_renumber_headings_uses_shared_normalizer(self, monkeypatch, capsys):
        """COM 重排走同一归一层：别名不再误报未知风格（不起真 Word）。"""
        import _renderer.docx_com_postprocess as m

        def _boom():
            raise RuntimeError("测试环境不启动 Word")

        monkeypatch.setattr(m, "_open_word", _boom)
        assert m.renumber_headings("whatever.docx", style="chinese_multi_level") is False
        assert "未知风格" not in capsys.readouterr().out
        assert m.renumber_headings("whatever.docx", style="bogus") is False
        assert "未知风格 'bogus'" in capsys.readouterr().out

    def test_com_postprocess_chapter_style_fallback(self, tmp_path, monkeypatch):
        """无 pywin32 降级路径：numbering_style: chapter 编号真实写入。"""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("win32com"):
                raise ImportError("no pywin32")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        doc = _make_doc()
        path = tmp_path / "t.docx"
        doc.save(str(path))

        com_postprocess(str(path), {"numbering": True, "numbering_style": "chapter"})
        from docx import Document
        texts = _headings(Document(str(path)))
        assert texts[0].startswith("第一章 ")
        assert texts[3].startswith("第二章 ")


def _apply(style):
    doc = _make_doc()
    _manual_numbering(doc, style)
    return doc
