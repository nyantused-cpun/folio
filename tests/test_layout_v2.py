# -*- coding: utf-8 -*-
"""页级版式渲染 P01-P11 测试（dev_plan_visual_v2 §6，T6）。

覆盖：P 系页 section 骨架 + 锚点 + 省略 h2；自由流页（无 layout/旧值）
保持现状零 diff（F9）；混合 spec；topnav 锚点可达。
"""
import os
import shutil

import pytest
import yaml


@pytest.fixture()
def render(tmp_path):
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    out_dir = os.path.join("output", "通用", "layout_v2_test")

    def _render(spec):
        from _renderer import Renderer
        spec.setdefault("confirmed", True)
        spec_path = tmp_path / "spec.yml"
        spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True),
                             encoding="utf-8")
        r = Renderer(str(spec_path))
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        try:
            out = os.path.join(out_dir, "out.html")
            r.render_html(out)
            with open(out, encoding="utf-8") as f:
                return f.read()
        finally:
            if os.path.exists(out_dir):
                shutil.rmtree(out_dir)

    yield _render
    os.environ.pop("_PRESALES_CLI_INVOKED", None)


def test_v2_page_skeleton(render):
    html = render({
        "pages": [{"id": "p1", "title": "封面", "layout": "P01",
                   "elements": [{"type": "hero", "title": "大标题"}]}],
    })
    assert '<section class="v2-page" id="p1">' in html
    assert 'class="hero"' in html
    # P 系页省略 h2 页标题（标题语义由 hero 承载）
    assert "<h2>封面</h2>" not in html
    assert ".v2-page" in html  # 骨架 CSS 注入


def test_free_flow_page_unchanged(render):
    """自由流页（无 layout / 旧值）：h2 页标题 + 无 wrapper（F9 零 diff）。"""
    for layout in (None, "title_body", "blueprint"):
        page = {"id": "p1", "title": "旧页面",
                "elements": [{"type": "text", "content": "正文"}]}
        if layout:
            page["layout"] = layout
        html = render({"pages": [page]})
        assert "<h2>旧页面</h2>" in html
        assert 'class="v2-page"' not in html


def test_mixed_spec(render):
    html = render({
        "pages": [
            {"id": "p1", "title": "封面", "layout": "P01",
             "elements": [{"type": "hero", "title": "大标题"}]},
            {"id": "p2", "title": "旧页",
             "elements": [{"type": "text", "content": "正文"}]},
        ],
    })
    assert '<section class="v2-page" id="p1">' in html
    assert "<h2>旧页</h2>" in html


def test_topnav_anchor_reachable(render):
    """topnav 锚点与 P 系页 id 对应（§5.3 锚点自动生成）。"""
    html = render({
        "pages": [
            {"id": "cover", "title": "封面", "layout": "P01",
             "elements": [{"type": "hero", "title": "大标题"}]},
            {"id": "flow", "title": "合同流程", "layout": "P05",
             "elements": [
                 {"type": "section_tag", "label": "流程"},
                 {"type": "action_title", "segments": [{"t": "闭环 8 步"}]},
                 {"type": "diagram", "diagram_type": "flow",
                  "subtype": "flow_rows", "title": "主流程",
                  "rows": [{"cards": [{"label": "准入"}]}]},
                 {"type": "legend_bar", "items": [{"swatch": "lit",
                                                   "label": "已点亮"}]},
             ]},
            {"id": "nav", "title": "导航", "layout": "P11",
             "elements": [
                 {"type": "action_title", "segments": [{"t": "谢谢"}]},
                 {"type": "info_cards", "cards": [{"title": "联系人",
                                                   "items": ["张"]}]},
                 {"type": "topnav", "brand": "瓴寓国际"},
             ]},
        ],
    })
    assert 'href="#cover"' in html and 'id="cover"' in html
    assert 'href="#flow"' in html and 'id="flow"' in html


def test_layout_warnings_in_report(render, tmp_path):
    """P 系必需构件缺失/乱序进 report.warnings（T2 schema 经 Renderer 收集）。"""
    os.environ["_PRESALES_CLI_INVOKED"] = "1"
    try:
        from _renderer import Renderer
        spec_path = tmp_path / "bad.yml"
        spec_path.write_text(yaml.safe_dump({
            "confirmed": True,
            "pages": [{"id": "p1", "title": "流程", "layout": "P05",
                       "elements": [
                           {"type": "action_title",
                            "segments": [{"t": "缺 legend"}]},
                           {"type": "diagram", "diagram_type": "flow",
                            "subtype": "flow_rows", "title": "x",
                            "rows": [{"cards": [{"label": "a"}]}]},
                       ]}],
        }, allow_unicode=True), encoding="utf-8")
        r = Renderer(str(spec_path))
        text = "\n".join(r.report.warnings)
        assert "legend_bar" in text  # 必需构件缺失（error 经 report 收集）
    finally:
        os.environ.pop("_PRESALES_CLI_INVOKED", None)
