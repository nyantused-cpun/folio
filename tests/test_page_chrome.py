# -*- coding: utf-8 -*-
"""视觉规范 v2.0 页面构件测试（dev_plan_visual_v2_2026-07-25 §7，T3）。

覆盖：10 构件 HTML 结构、data-editable 标注、防注入转义、hl 枚举、
chrome_css 零 hex 硬编码（§9.3 机械防线）、端到端主题注入。
"""
import os
import re

import pytest

from _renderer import page_chrome as pc
from _renderer import elements as proto


def _norm(elem):
    return proto.normalize_element(elem)[1]


# ---- 构件 HTML 结构 ----

def test_hero_full():
    html = pc.render_hero(_norm({
        "type": "hero", "eyebrow": "SECTION 0 · 方案总览", "title": "大标题",
        "subtitle": "副标题", "meta": ["版本 v3", "日期 2026-07-25"],
        "stats": [{"value": "202", "unit": "功能点", "label": "全量替换"}]}))
    assert 'class="hero"' in html and 'class="hero-eyebrow"' in html
    assert 'class="hero-title"' in html and "大标题" in html
    assert 'class="hero-subtitle"' in html and 'class="hero-meta"' in html
    assert "版本 v3" in html
    assert 'class="hero-stats stats-bar"' in html and "202" in html
    assert html.count('data-editable="true"') >= 5


def test_hero_minimal():
    html = pc.render_hero(_norm({"type": "hero", "title": "只有标题"}))
    assert "hero-eyebrow" not in html and "hero-subtitle" not in html
    assert "hero-meta" not in html and "hero-stats" not in html
    assert "只有标题" in html


def test_section_tag():
    html = pc.render_section_tag(_norm(
        {"type": "section_tag", "index": "SECTION 1", "label": "业务背景"}))
    assert 'class="section-tag"' in html and "SECTION 1 · 业务背景" in html
    html = pc.render_section_tag(_norm({"type": "section_tag", "label": "无编号"}))
    assert "无编号" in html and "·" not in html


def test_action_title_segments_and_hl():
    html = pc.render_action_title(_norm({"type": "action_title", "segments": [
        {"t": "点亮 "}, {"t": "74%", "hl": "yellow"},
        {"t": "，缺口 "}, {"t": "15 项", "hl": "red"},
        {"t": " / "}, {"t": "8 域", "hl": "green"}], "sub": "口径说明"}))
    assert 'class="action-title"' in html
    assert '<span class="hl-yellow">74%</span>' in html
    assert '<span class="hl-red">15 项</span>' in html
    assert '<span class="hl-green">8 域</span>' in html
    assert 'class="section-sub"' in html and "口径说明" in html


def test_action_title_injection_safe():
    """防注入铁律（§7）：segments.t 的 HTML 标签必须转义；非法 hl 不产出 span。"""
    html = pc.render_action_title(_norm({"type": "action_title", "segments": [
        {"t": "<script>alert(1)</script>"},
        {"t": "x", "hl": "blink"}]}))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "hl-blink" not in html


def test_stat_cards_tone():
    html = pc.render_stat_cards(_norm({"type": "stat_cards", "cards": [
        {"value": "149", "unit": "74%", "label": "已点亮", "tone": "lit"},
        {"value": "15", "label": "缺口", "tone": "gap"},
        {"value": "12", "label": "系统"},  # tone 缺省 → 主色无修饰类
    ]}))
    assert 'class="stat-card s-lit"' in html
    assert 'class="stat-card s-gap"' in html
    assert html.count("stat-card") >= 3
    assert "<small>74%</small>" in html


def test_kpi_cards():
    html = pc.render_kpi_cards(_norm({"type": "kpi_cards", "cards": [
        {"label": "预算拦截率", "from": "0%", "to": "100%", "note": "事前强控"}]}))
    assert 'class="kpi-card"' in html
    assert 'class="kpi-from num"' in html and "0%" in html
    assert 'class="kpi-to num"' in html and "100%" in html
    assert "→" in html and "事前强控" in html


def test_pain_cards_levels():
    html = pc.render_pain_cards(_norm({"type": "pain_cards", "cards": [
        {"title": "印章/电子签", "level": "P1", "impact": "4 部门强共性",
         "body": "正文"},
        {"title": "无徽章卡"}]}))
    assert 'class="pain-badge lv-P1">P1<' in html
    assert "4 部门强共性" in html and "正文" in html
    assert html.count("pain-badge") == 1  # 缺 level 不渲染徽章


def test_info_cards():
    html = pc.render_info_cards(_norm({"type": "info_cards", "cards": [
        {"title": "缺口 15 项集中在三处", "items": ["资产大件", "系统集成"]}]}))
    assert 'class="info-card"' in html
    assert "缺口 15 项集中在三处" in html
    assert "<li data-editable=\"true\">资产大件</li>" in html


def test_view_cards_html():
    """D-093 view_cards：4 列视角卡 + 顶部半圆顶居中标题。"""
    html = pc.render_view_cards(_norm({
        "type": "view_cards",
        "title": "原厂 3 大优势 + 1 落地",
        "cards": [
            {"perspective": "海外本地", "icon": "✈", "headline": "2 团队",
             "detail": "美国本地服务团队 + 出海咨询能力"},
            {"perspective": "团队池", "icon": "☉", "headline": "100+ 人",
             "detail": "咨询 / 实施 / 跨域专家"},
            {"perspective": "产研共建", "icon": "◈", "headline": "1 对 1",
             "detail": "组件迭代 + 持续降定制"},
            {"perspective": "全行业", "icon": "◉", "headline": "12+ 专项",
             "detail": "不只 CRM，覆盖合同/报销/档案"},
        ]}))
    assert 'class="view-cards"' in html
    assert 'class="view-cap-circle"' in html
    assert "原厂 3 大优势" in html
    assert html.count('class="view-card"') == 4
    assert "海外本地" in html and "100+ 人" in html
    assert "✈" in html


def test_callout_block_html():
    """D-093 callout_block：底部双编号说服区（含 highlight 数字）。"""
    html = pc.render_callout_block(_norm({
        "type": "callout_block",
        "points": [
            {"num": "01", "title": "试点上线可减少 30% 探索成本",
             "highlight": "30%", "desc": "原型修改 vs 定制开发"},
            {"num": "02", "title": "全面推广可降 60% 集成成本",
             "highlight": "60%", "desc": "集成平台 + 预集成包"},
        ]}))
    assert 'class="callout-block"' in html
    assert 'class="callout-num"' in html
    assert "01" in html and "02" in html
    assert "30%" in html
    assert 'class="callout-hl"' in html
    assert "试点上线" in html


def test_legend_bar_swatches():
    html = pc.render_legend_bar(_norm({"type": "legend_bar", "items": [
        {"swatch": "lit", "label": "已点亮"},
        {"swatch": "gap", "label": "缺口"},
        {"swatch": "role_biz", "label": "业务 / 采购"},
        {"swatch": "", "label": "缺省色块"},  # 空 swatch → keep
    ]}))
    assert 'class="legend-swatch sw-lit"' in html
    assert 'class="legend-swatch sw-gap"' in html
    assert 'class="legend-swatch sw-role-biz"' in html
    assert 'class="legend-swatch sw-keep"' in html


def test_qa_block():
    html = pc.render_qa_block(_norm({"type": "qa_block", "items": [
        {"q": "为什么选私有化？", "a": "数据不出域"}]}))
    assert 'class="qa-q"' in html and "为什么选私有化？" in html
    assert 'class="qa-a"' in html and "数据不出域" in html


def test_topnav_anchors_from_pages():
    pages = [{"id": "p1", "title": "业务背景"},
             {"id": "p2", "title": "合同流程"},
             {"title": "无 id 不出锚点"}]
    html = pc.render_topnav(_norm({"type": "topnav", "brand": "瓴寓国际",
                                   "brand_sub": "私有化 OA 平台"}), pages=pages)
    assert 'class="topnav"' in html and "瓴寓国际" in html
    assert "私有化 OA 平台" in html
    assert 'href="#p1"' in html and "业务背景" in html
    assert 'href="#p2"' in html
    assert "无 id 不出锚点" not in html


def test_topnav_logo_injected():
    n = _norm({"type": "topnav", "brand": "客户公司", "brand_sub": "",
               "logo": "refs/logo.png"})
    html = pc.render_topnav(n, pages=[])
    assert '<img' in html
    assert 'refs/logo.png' in html
    assert 'class="brand-logo"' in html


def test_topnav_logo_placeholder_when_missing():
    n = _norm({"type": "topnav", "brand": "客户公司", "brand_sub": ""})
    html = pc.render_topnav(n, pages=[])
    assert 'class="brand-logo-placeholder"' in html


def test_toc_cards_html():
    n = _norm({"type": "toc_cards",
               "cards": [{"num": "01", "title": "背景", "desc": "现状"},
                         {"num": "02", "title": "方案", "desc": ""}]})
    html = pc.render_toc_cards(n)
    assert 'class="toc-cards"' in html
    assert "01" in html and "背景" in html
    assert "现状" in html
    assert 'class="toc-title" data-editable="true"' in html


def test_duo_compare_html():
    n = _norm({"type": "duo_compare",
               "left": {"title": "方案A", "points": ["a1", "a2"]},
               "right": {"title": "方案B", "points": ["b1"]}})
    html = pc.render_duo_compare(n)
    assert 'class="duo-compare"' in html
    assert 'class="duo-vrule"' in html
    assert "方案A" in html and "方案B" in html
    assert "a1" in html and "b1" in html


def test_pros_cons_html():
    n = _norm({"type": "pros_cons", "pros": ["省时"], "cons": ["成本"]})
    html = pc.render_pros_cons(n)
    assert 'class="pros-cons"' in html
    assert "优势" in html and "风险/成本" in html
    assert "省时" in html and "成本" in html
    assert 'class="pc-item pc-pro"' in html
    assert 'class="pc-item pc-con"' in html


def test_cta_block_html():
    n = _norm({"type": "cta_block", "title": "联系我们",
               "button": "预约演示", "contact": "400-000-0000"})
    html = pc.render_cta_block(n)
    assert 'class="cta-block"' in html
    assert "预约演示" in html and "400-000-0000" in html


def test_chrome_css_cjk_break():
    """v3.0 中文断行（同事经验：防「80000多家」拆行）。"""
    css = pc.chrome_css()
    assert "word-break: normal" in css
    assert "overflow-wrap: normal" in css


def test_page_header_full():
    """D-092 第1层页眉横幅：EX 编号徽章 + 标题 + 章节胶囊 + meta 全渲染。"""
    html = pc.render_page_header(_norm({
        "type": "page_header", "index": "EX-03", "title": "端到端流程贯通",
        "tag": "数字化中台", "meta": ["一期范围", "2026-07"]}))
    assert 'class="page-header"' in html
    assert 'class="ph-index"' in html and "EX-03" in html
    assert 'class="ph-title"' in html and "端到端流程贯通" in html
    assert 'class="ph-tag"' in html and "数字化中台" in html
    assert 'class="ph-meta"' in html
    assert 'class="ph-meta-item"' in html and "一期范围" in html
    assert html.count('data-editable="true"') >= 4


def test_page_header_minimal():
    """只有 title 的降级形态：index/tag/meta 均不渲染。"""
    html = pc.render_page_header(_norm({"type": "page_header", "title": "仅标题"}))
    assert 'class="page-header"' in html and "仅标题" in html
    assert "ph-index" not in html and "ph-tag" not in html and "ph-meta" not in html


def test_page_header_injection_safe():
    """防注入铁律（§7）：title/index/tag 的 HTML 标签必须转义。"""
    html = pc.render_page_header(_norm({
        "type": "page_header", "index": "<b>EX</b>", "title": "<script>x</script>",
        "tag": "<i>标签</i>"}))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&lt;b&gt;EX&lt;/b&gt;" in html and "&lt;i&gt;标签&lt;/i&gt;" in html


def test_render_chrome_html_dispatch():
    assert pc.render_chrome_html("foo", {}) is None
    html = pc.render_chrome_html("section_tag", {"index": "", "label": "x"})
    assert 'class="section-tag"' in html


# ---- CSS 纪律（§9.3：构件 CSS 零 hex 硬编码） ----

def test_chrome_css_no_hex_hardcode():
    css = pc.chrome_css()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), \
        "chrome_css 出现 hex 字面量（应全部走 var(--t-*)）"


def test_chrome_css_uses_theme_vars():
    css = pc.chrome_css()
    for var in ("--t-primary", "--t-accent", "--t-lit-border", "--t-part-bg",
                "--t-gap-border", "--t-role-legal", "--t-text-secondary",
                "--t-bg-soft", "--t-hero-from", "--t-group-blue"):
        assert f"var({var})" in css


# ---- 端到端：Renderer 注入主题 tokens + 构件渲染 ----

@pytest.fixture()
def renderer(tmp_path):
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        from _renderer import Renderer
        spec = tmp_path / "spec.yml"
        spec.write_text("""\
confirmed: true
theme: consulting_kpmg
pages:
  - id: p1
    title: 封面
    layout: P01
    elements:
      - type: hero
        eyebrow: "SECTION 0"
        title: "蓝海集团统建 7 大系统全量替换"
        meta: ["版本 v3"]
      - type: stat_cards
        cards:
          - {value: "149", unit: "74%", label: "已点亮", tone: lit}
  - id: p2
    title: 流程
    elements:
      - type: section_tag
        index: "EXHIBIT 2"
        label: "合同流程"
      - type: action_title
        segments:
          - {t: "电子签覆盖 "}
          - {t: "4 部门", hl: yellow}
""", encoding="utf-8")
        yield Renderer(str(spec))
    finally:
        os.environ.pop("_PRESALES_CLI_INVOKED", None)


def _render_to_output(renderer):
    """渲染到 output/ 白名单内临时目录，返回 HTML 文本后清理（照 test_renderer 模式）。"""
    import shutil
    out_dir = os.path.join("output", "通用", "page_chrome_test")
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    try:
        out = os.path.join(out_dir, "out.html")
        renderer.render_html(out)
        with open(out, encoding="utf-8") as f:
            return f.read()
    finally:
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)


def test_end_to_end_theme_injection(renderer):
    html = _render_to_output(renderer)
    # 主题 tokens :root 块注入（kpmg 冻结值）
    assert "--t-primary:#00338D" in html
    assert "--t-lit-border:#059669" in html
    # 构件 CSS 注入 + 构件渲染
    assert ".hero-eyebrow" in html
    assert 'class="hero"' in html and "蓝海集团统建 7 大系统全量替换" in html
    assert 'class="stat-card s-lit"' in html
    assert '<span class="hl-yellow">4 部门</span>' in html


def test_end_to_end_legacy_default(tmp_path):
    """老 spec（无 theme 字段）：v2 tokens 缺省 legacy_bluegreen（F9）。"""
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        from _renderer import Renderer
        spec = tmp_path / "legacy.yml"
        spec.write_text("""\
confirmed: true
pages:
  - id: p1
    title: 页
    elements:
      - type: section_tag
        label: "背景"
""", encoding="utf-8")
        r = Renderer(str(spec))
        html = _render_to_output(r)
        assert "--t-primary:#1B5E8A" in html  # legacy 蓝绿
        assert 'class="section-tag"' in html
    finally:
        os.environ.pop("_PRESALES_CLI_INVOKED", None)
