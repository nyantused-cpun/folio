# -*- coding: utf-8 -*-
"""B4 批回归测试（2026-09-06）：theme 转发层退役 + logo_position 摆位消费。

- 转发层退役（考古 M2）：_renderer/diagram/theme.py（sys.modules 别名转发）
  删除，全部引用直连真源 _renderer/theme.py；本文件同时钉死
  `from _renderer.diagram import theme` 经包属性解析到真源的行为
  （pptd_emit.py:17 与 5 个存量测试文件依赖该解析，删除转发模块后仍成立）。
- logo_position（B3 挂账 P1-6 收尾）：topnav 摆位消费——topnav_left（缺省）
  与 B4 前输出逐字节一致；topnav_right 槽位移导航右端；hero_corner 为封面
  场景声明值，topnav 按缺省左位落。
"""

import importlib
import os
import shutil
import sys

import pytest
import yaml

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPT_DIR)

from _renderer import Renderer
from _renderer import elements as proto
from _renderer import page_chrome as pc

WORK_DIR = os.path.join(SCRIPT_DIR, "output", "通用", "_test_b4_theme_retire")


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
    shutil.rmtree(WORK_DIR, ignore_errors=True)


def _norm(elem):
    return proto.normalize_element(elem)[1]


def _seq():
    """最小合法 sequence 图（同 tests/test_diagram.py 样例形状）。"""
    return {"type": "diagram", "diagram_type": "flow", "subtype": "sequence",
            "title": "报销流程",
            "steps": [{"label": "开始", "type": "start"},
                      {"label": "提交", "desc": "录入"},
                      {"label": "审批"},
                      {"label": "结束", "type": "end"}]}


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


# ---- 转发层退役 ----

def test_forwarding_module_removed():
    """_renderer/diagram/theme.py 已删除，子模块 import 不再可达。"""
    path = os.path.join(SCRIPT_DIR, "_renderer", "diagram", "theme.py")
    assert not os.path.exists(path)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("_renderer.diagram.theme")


def test_diagram_theme_attr_is_true_source():
    """from _renderer.diagram import theme 经包属性解析到真源 _renderer.theme。

    钉死该解析（非转发层遗物）：diagram/__init__ 的 `from .. import theme`
    绑定包属性；pptd_emit.py 与存量测试的旧写法依赖此行为，删除转发模块
    后必须仍然成立且指向同一模块对象。
    """
    import _renderer.theme as rt
    import _renderer.diagram as dg_pkg
    from _renderer.diagram import theme as dg_theme
    assert dg_pkg.theme is rt
    assert dg_theme is rt


def test_renderers_bind_true_source_esc():
    """diagram 渲染器的 _esc / theme 名字空间直连真源。"""
    import _renderer.theme as rt
    from _renderer.diagram import (architecture, chart, flow, matrix,
                                   relationship, timeline)
    for mod in (architecture, chart, flow, matrix, relationship, timeline):
        assert mod._esc is rt._esc, mod.__name__
        assert mod.theme is rt, mod.__name__


def test_diagram_html_and_pptd_render():
    """HTML/pptd 双端渲染冒烟：直连 import 链路 + theme 常量消费正常。"""
    from _renderer.diagram import render_diagram_html, render_diagram_pptd
    html = render_diagram_html(_seq())
    assert '<section class="diagram"' in html and "报销流程" in html
    elems, h = render_diagram_pptd(_seq(), 0.0, 0.0, 1200.0)
    assert elems and h > 0


def test_editor_injector_v2_themes_script():
    """html_editor_injector 直连 _renderer.theme：THEMES + tokens + bridge 全通。"""
    from _renderer.html_editor_injector import _v2_themes_script
    s = _v2_themes_script()
    assert "window.__V2_THEMES__" in s
    assert "--t-primary:#00338D" in s       # consulting_kpmg tokens
    assert "--blue: var(--t-primary)" in s  # bridge_css


# ---- logo_position 摆位（page_chrome 单元级） ----

def test_chrome_css_has_pos_right_rule():
    assert ".brand-logo.pos-right" in pc.chrome_css()
    assert ".brand-logo-placeholder.pos-right" in pc.chrome_css()


def test_topnav_default_placement_unchanged():
    """缺省/显式 topnav_left/hero_corner 三者输出一致，logo 槽在 brand 左。"""
    base = _norm({"type": "topnav", "brand": "客户公司", "logo": "refs/l.png"})
    html_default = pc.render_topnav(base, pages=[])
    assert pc.render_topnav(_norm({"type": "topnav", "brand": "客户公司",
                                   "logo": "refs/l.png",
                                   "logo_position": "topnav_left"}),
                            pages=[]) == html_default
    assert pc.render_topnav(_norm({"type": "topnav", "brand": "客户公司",
                                   "logo": "refs/l.png",
                                   "logo_position": "hero_corner"}),
                            pages=[]) == html_default
    assert "pos-right" not in html_default
    assert html_default.index('class="brand-logo"') \
        < html_default.index('class="brand"')


def test_topnav_topnav_right_placement():
    """topnav_right：pos-right 类 + logo 槽排到 nav-links 之后（导航右端）。"""
    html = pc.render_topnav(_norm({"type": "topnav", "brand": "客户公司",
                                   "logo": "refs/l.png",
                                   "logo_position": "topnav_right"}), pages=[])
    assert 'class="brand-logo pos-right"' in html
    assert html.index('class="nav-links"') \
        < html.index('class="brand-logo pos-right"')


def test_topnav_right_placeholder():
    """topnav_right 无 logo：占位框同样落右位（编辑替换入口跟随摆位）。"""
    html = pc.render_topnav(_norm({"type": "topnav", "brand": "客户公司",
                                   "logo_position": "topnav_right"}), pages=[])
    assert 'class="brand-logo-placeholder pos-right"' in html


def test_topnav_unknown_position_falls_back_left():
    """未知摆位值（元素级无 schema 白名单）回退缺省左位。"""
    base = _norm({"type": "topnav", "brand": "客户公司", "logo": "refs/l.png"})
    html_default = pc.render_topnav(base, pages=[])
    bogus = dict(base, logo_position="somewhere_else")
    assert pc.render_topnav(bogus, pages=[]) == html_default


# ---- logo_position 摆位（Renderer 端到端：brand 合并 + 渲染链路） ----

def test_brand_position_right_end_to_end(tmp_path, work_dir):
    """brand.logo_position=topnav_right 端到端生效；同 spec 冒烟渲染链路
    （schema 主题校验 + diagram 直连 + v2 tokens 注入）。"""
    _, html = _render_html(tmp_path, work_dir, {
        "title": "B4 摆位测试",
        "theme": "consulting_kpmg",
        "brand": {"logo": "refs/acme.png", "logo_position": "topnav_right"},
        "pages": [{"id": "p1", "title": "首页", "elements": [
            {"type": "topnav", "brand": "ACME"},
            _seq()]},
        ]})
    assert 'class="brand-logo pos-right" src="refs/acme.png"' in html
    # 渲染链路冒烟：diagram 直连渲染 + 主题 tokens（schema/__init__ 直连 import）
    assert '<section class="diagram"' in html
    assert "--t-primary:#00338D" in html


def test_brand_default_position_unchanged_end_to_end(tmp_path, work_dir):
    """brand 只给 logo 不给位置：缺省左位，输出与 B4 前结构一致。"""
    _, html = _render_html(tmp_path, work_dir, {
        "title": "B4 缺省测试",
        "brand": {"logo": "refs/acme.png"},
        "pages": [{"id": "p1", "title": "首页", "elements": [
            {"type": "topnav", "brand": "ACME"}]},
        ]})
    assert 'class="brand-logo" src="refs/acme.png"' in html
    assert 'class="brand-logo pos-right"' not in html
    assert 'class="brand-logo-placeholder pos-right"' not in html


def test_element_position_overrides_brand(tmp_path, work_dir):
    """元素级 logo_position 优先于文档级 brand（与 logo 同一优先级语义）。"""
    _, html = _render_html(tmp_path, work_dir, {
        "title": "B4 覆盖测试",
        "brand": {"logo": "refs/b.png", "logo_position": "topnav_right"},
        "pages": [{"id": "p1", "title": "首页", "elements": [
            {"type": "topnav", "brand": "ACME", "logo": "assets/e.png",
             "logo_position": "topnav_left"}]},
        ]})
    assert 'class="brand-logo" src="assets/e.png"' in html
    assert 'class="brand-logo pos-right"' not in html
    assert 'class="brand-logo-placeholder pos-right"' not in html
