# -*- coding: utf-8 -*-
"""_renderer.theme（Step 2 后唯一主题模块）测试。

覆盖：default=consulting_kpmg、旧 style 映射、THEMES 六主题可解析、
legacy 等值、spec_overrides 仅 HTML、font 单值、style_name_for_entry 兼容、
diagram 模块常量镜像。
"""

import re

import pytest

from _renderer.theme import (
    DEFAULT_DIAGRAM_SLOTS,
    DIAGRAM_SLOT_NAMES,
    HTML_SLOT_NAMES,
    PPTD_SLOT_NAMES,
    THEMES,
    Theme,
    normalize_theme_name,
    resolve_theme,
    style_name_for_entry,
)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
THEME_NAMES = ("legacy_bluegreen", "consulting_kpmg", "corporate_navy",
               "product_charcoal", "weaver_blue", "gov_red")


def test_default_and_unknown_fall_back_to_consulting():
    assert resolve_theme(None).style_name == "consulting_kpmg"
    assert resolve_theme("nonexistent").style_name == "consulting_kpmg"
    assert normalize_theme_name(None) == "consulting_kpmg"
    assert normalize_theme_name("nope") == "consulting_kpmg"


def test_legacy_style_mapping():
    assert normalize_theme_name("education") == "consulting_kpmg"
    assert normalize_theme_name("enterprise") == "corporate_navy"
    assert normalize_theme_name("tech") == "product_charcoal"
    assert normalize_theme_name("gov") == "gov_red"
    assert resolve_theme("enterprise").style_name == "corporate_navy"


@pytest.mark.parametrize("name", THEME_NAMES)
def test_each_theme_resolves_all_slots(name):
    t = resolve_theme(name)
    assert isinstance(t, Theme)
    assert t.style_name == name
    assert set(t.html_colors) == set(HTML_SLOT_NAMES)
    assert set(t.pptd_colors) == set(PPTD_SLOT_NAMES)
    assert list(t.pptd_colors) == list(PPTD_SLOT_NAMES)
    assert set(t.diagram_colors) == set(DIAGRAM_SLOT_NAMES)
    for v in list(t.html_colors.values()) + list(t.pptd_colors.values()) + list(t.diagram_colors.values()):
        assert HEX_RE.match(v), f"{name} 出现非法 hex: {v}"


def test_legacy_bluegreen_matches_default_diagram_slots():
    t = resolve_theme("legacy_bluegreen")
    assert t.diagram_colors == DEFAULT_DIAGRAM_SLOTS
    assert t.html_colors["primary"] == "#1B5E8A"


def test_spec_overrides_only_html():
    t = resolve_theme("weaver_blue", {"primary": "#123456"})
    assert t.html_colors["primary"] == "#123456"
    assert t.pptd_colors["primary"] == "#337AB7"
    assert t.diagram_colors["blue"] == "#337AB7"


def test_weaver_tokens_frozen():
    t = resolve_theme("weaver_blue")
    assert t.base["primary"] == "#337AB7"
    assert t.pptd_colors["primary"] == "#337AB7"
    assert t.diagram_colors["blue"] == "#337AB7"
    assert t.fonts["body"] == "Microsoft YaHei"


def test_gov_red_font_chosen_from_cjk_stack():
    t = resolve_theme("gov_red")
    assert t.base["primary"] == "#A63428"
    assert t.pptd_colors["primary"] == "#A63428"
    assert t.fonts["body"] in ("SimSun", "Microsoft YaHei")


def test_style_name_for_entry_compat():
    assert style_name_for_entry("enterprise") == "corporate_navy"
    assert style_name_for_entry("consulting_kpmg") == "consulting_kpmg"
    assert style_name_for_entry({}) == "consulting_kpmg"
    assert style_name_for_entry(None) == "consulting_kpmg"
    assert style_name_for_entry(THEMES["weaver_blue"]) == "weaver_blue"


def test_diagram_module_constants_mirror_current_resolution():
    from _renderer.diagram import theme as dg_theme
    t = resolve_theme()
    for slot in DIAGRAM_SLOT_NAMES:
        assert getattr(dg_theme, slot.upper()) == t.diagram_colors[slot], slot
    assert dg_theme.FONT_PPT == t.fonts["body"]
    assert f'fill="{dg_theme.BLUE}"' in dg_theme.SVG_DEFS
    assert f'fill="{dg_theme.GREEN}"' in dg_theme.SVG_DEFS
