# -*- coding: utf-8 -*-
"""B3 批渲染器核心缺陷回归测试（2026-09-06 审查快照 6 项）。

- P1-6：spec.brand.logo 判空合并后真实生效（元素级 topnav 声明优先）
- P1-7：image 元素 HTML 端渲染分支（文件缺失体面降级，不裸崩）
- P1-8：DOCX 端 DEGRADE 构件按能力矩阵泛化判定，绝不静默 skip
- P2：format YAML null / pages 非 dict / cover.veil 非法 hex 三处容错
"""

import os
import shutil
import sys

import pytest
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer import Renderer
from _renderer.elements import CAPABILITIES, DEGRADE, END_DOCX, degrade_text

WORK_DIR = os.path.join(SCRIPT_DIR, "output", "通用", "_test_b3_renderer_core")


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
    """HTML/DOCX 输出目录（_validate_output_path 白名单在 output/ 内）。"""
    os.makedirs(WORK_DIR, exist_ok=True)
    yield WORK_DIR
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


def _render_docx(tmp_path, work_dir, spec):
    r = Renderer(_write_spec(tmp_path, spec))
    out = os.path.join(work_dir, "out.docx")
    r.render_docx(out)
    from docx import Document
    doc = Document(out)
    return r, [p.text for p in doc.paragraphs]


# ---- P1-6：spec.brand.logo 判空合并（原 setdefault 恒 no-op）----


def test_brand_logo_takes_effect(tmp_path, work_dir):
    """spec.brand.logo（元素级 topnav 未声明 logo）必须真实渲染 <img>。"""
    _, html = _render_html(tmp_path, work_dir, {
        "brand": {"logo": "refs/acme.png"},
        "pages": [{"id": "p1", "title": "封面",
                   "elements": [{"type": "topnav", "brand": "ACME"}]}],
    })
    assert '<img class="brand-logo" src="refs/acme.png"' in html


def test_element_logo_overrides_brand(tmp_path, work_dir):
    """元素级 logo 声明优先于文档级 brand。"""
    _, html = _render_html(tmp_path, work_dir, {
        "brand": {"logo": "refs/acme.png"},
        "pages": [{"id": "p1", "title": "封面",
                   "elements": [{"type": "topnav", "brand": "ACME",
                                 "logo": "assets/element.png"}]}],
    })
    assert 'src="assets/element.png"' in html
    assert 'src="refs/acme.png"' not in html


def test_no_brand_keeps_placeholder(tmp_path, work_dir):
    """无任何 logo（文档级/元素级均无）时保持占位框，不出现 <img>。"""
    _, html = _render_html(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "封面",
                   "elements": [{"type": "topnav", "brand": "ACME"}]}],
    })
    assert "brand-logo-placeholder" in html
    assert 'class="brand-logo"' not in html


# ---- P1-7：image 元素 HTML 端渲染分支 ----


def test_image_renders_in_html(tmp_path, work_dir):
    """src 指向真实文件时渲染 <img> + 图题（此前 HTML 端静默丢失）。"""
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # HTML 端只做存在性判断
    _, html = _render_html(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "图页", "elements": [
            {"type": "image", "src": str(img), "caption": "架构<示意>"}]}],
    })
    assert f'<img src="{img}"' in html
    assert "架构&lt;示意&gt;" in html  # 图题/alt 统一 _esc（§七 2.6）


def test_image_missing_file_degrades(tmp_path, work_dir):
    """src 文件不存在时体面降级为占位文本并进 report，不裸崩。"""
    r, html = _render_html(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "图页", "elements": [
            {"type": "image", "src": "refs/不存在.png", "caption": "缺图"}]}],
    })
    assert '<p class="degraded">[图片：缺图]</p>' in html
    assert any("图片不存在" in w for w in r.report.warnings)


def test_image_no_src_degrades(tmp_path, work_dir):
    """未指定 src 同样降级（与 DOCX 端 [图片：{caption or src}] 语义对齐）。"""
    r, html = _render_html(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "图页", "elements": [
            {"type": "image", "caption": "只有图题"}]}],
    })
    assert "[图片：只有图题]" in html
    assert any("图片不存在" in w for w in r.report.warnings)


# ---- P1-8：DOCX 端 DEGRADE 构件按能力矩阵泛化判定 ----

# P12/P14-P16 七构件（原手维护元组漏掉，落 else 静默 skip）
_DEGRADE_SEVEN = [
    {"type": "page_header", "title": "页眉", "index": "EX 1"},
    {"type": "view_cards", "title": "视角",
     "cards": [{"perspective": "业务", "headline": "x", "detail": "y"}]},
    {"type": "callout_block", "points": [{"title": "点", "desc": "d"}]},
    {"type": "toc_cards", "cards": [{"num": "01", "title": "章节一"}]},
    {"type": "duo_compare", "left": {"title": "左", "points": ["a"]},
     "right": {"title": "右", "points": ["b"]}},
    {"type": "pros_cons", "pros": ["p"], "cons": ["c"]},
    {"type": "cta_block", "title": "开始", "button": "联系", "contact": "x"},
]


def test_docx_degrade_seven_components(tmp_path, work_dir):
    """七构件 + 存量 hero/topnav：DOCX 必须出降级文本 + report.degraded。"""
    elements = _DEGRADE_SEVEN + [
        {"type": "hero", "title": "封面"}, {"type": "topnav", "brand": "ACME"}]
    r, texts = _render_docx(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "版式页", "elements": elements}]})
    prefixes = ("[页眉横幅", "[视角卡", "[底部说服区", "[目录卡",
                "[双栏对比", "[优缺点清单", "[CTA 收尾区", "[封面横幅",
                "[页首导航")
    for prefix in prefixes:
        assert any(t.startswith(prefix) for t in texts), prefix
    degraded_types = {d["type"] for d in r.report.degraded}
    assert degraded_types == {"page_header", "view_cards", "callout_block",
                              "toc_cards", "duo_compare", "pros_cons",
                              "cta_block", "hero", "topnav"}
    assert len(r.report.degraded) == 9
    assert all(d["target"] == "docx" for d in r.report.degraded)
    assert r.report.skipped == []


def test_docx_degrade_matrix_complete():
    """能力矩阵声明 DOCX=DEGRADE 的类型，degrade_text 必须有专属降级文案。"""
    for etype, caps in CAPABILITIES.items():
        if caps.get(END_DOCX) == DEGRADE:
            text = degrade_text(etype, {"title": "T", "brand": "B"}, "docx")
            assert not text.startswith("[不支持的元素类型"), etype


def test_docx_unknown_type_still_skipped(tmp_path, work_dir):
    """泛化判定不得误吞未知 type：仍走 report.skipped（DOCX 端不支持）。"""
    r, _texts = _render_docx(tmp_path, work_dir, {
        "pages": [{"id": "p1", "title": "页",
                   "elements": [{"type": "tree"}]}]})
    assert [s["type"] for s in r.report.skipped] == ["tree"]
    assert r.report.degraded == []


# ---- P2：format 为 YAML null / 非 dict 容错 ----


def test_format_null_renders_docx(tmp_path, work_dir):
    """format: null（YAML）时 docx-build 不再 AttributeError 崩溃。"""
    r, texts = _render_docx(tmp_path, work_dir, {
        "format": None,
        "pages": [{"id": "p1", "title": "页", "elements": [
            {"type": "text", "content": "正文"}]}]})
    assert "正文" in texts
    assert r.format_config == {}


def test_format_non_dict_treated_as_empty(tmp_path, work_dir):
    """format 为字符串等非 dict 值时同样归一为空 dict，不崩。"""
    r, _texts = _render_docx(tmp_path, work_dir, {
        "format": "仿宋",
        "pages": [{"id": "p1", "title": "页", "elements": [
            {"type": "text", "content": "正文"}]}]})
    assert r.format_config == {}


# ---- P2：pages 含非 dict 项渲染层守卫 ----


def test_pages_non_dict_item_skipped_gracefully(tmp_path, work_dir):
    """pages 混入字符串项：HTML/DOCX 均不裸崩，合法页照常渲染并告警。"""
    spec = {
        "pages": ["我是非法页", {"id": "p1", "title": "正常页", "elements": [
            {"type": "text", "content": "正文"}]}],
    }
    r, html = _render_html(tmp_path, work_dir, spec)
    assert "正文" in html
    assert any("pages[0] 不是 dict" in w for w in r.report.warnings)
    r2, texts = _render_docx(tmp_path, work_dir, spec)
    assert "正文" in texts
    assert any("pages[0] 不是 dict" in w for w in r2.report.warnings)


def test_pages_null_renders_empty(tmp_path, work_dir):
    """pages 为 null：按空文档渲染并告警，不裸崩。"""
    r, html = _render_html(tmp_path, work_dir, {"pages": None})
    assert "<body>" in html
    assert any("pages 不是列表" in w for w in r.report.warnings)


# ---- P2：cover.veil 非 6 位 hex 解析防护 ----


def _cover_spec(veil):
    return {
        "document": {"title": "暗色封面", "cover": {
            "template": "dark-photo", "veil": veil}},
        "pages": [{"id": "p1", "title": "页", "elements": []}],
    }


def test_cover_veil_invalid_falls_back_to_default(tmp_path, work_dir):
    """veil 非法（'red'/None）时回退默认遮罩 #0A1540 并告警，不裸崩。"""
    r, html = _render_html(tmp_path, work_dir, _cover_spec("red"))
    assert "background:#0A1540" in html
    assert "rgba(10,21,64,0.8)" in html
    assert any("veil 不是 6 位 hex" in w for w in r.report.warnings)

    r2, html2 = _render_html(tmp_path, work_dir, _cover_spec(None))
    assert "rgba(10,21,64,0.8)" in html2
    assert any("veil 不是 6 位 hex" in w for w in r2.report.warnings)


def test_cover_veil_valid_hex_unchanged(tmp_path, work_dir):
    """合法 6 位 hex veil 行为不变（含无 # 前缀写法）。"""
    _, html = _render_html(tmp_path, work_dir, _cover_spec("#123456"))
    assert "background:#123456" in html
    assert "rgba(18,52,86,0.8)" in html
    _, html2 = _render_html(tmp_path, work_dir, _cover_spec("ABCDEF"))
    assert "rgba(171,205,239,0.8)" in html2
