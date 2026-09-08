# -*- coding: utf-8 -*-
"""Step 2 主题快照测试：6 套主题的关键计算样式 + legacy 零 diff 锚定。

断言 theme_tokens_css 的最终 CSS 变量值（primary/accent/三态三色/hero 渐变/
字体）与 THEMES tokens 一致；legacy_bluegreen 的 diagram 槽与基线常量零 diff。
"""

import pytest

from _renderer.diagram import theme as dg_theme
from _renderer.theme import (
    DEFAULT_DIAGRAM_SLOTS,
    THEMES,
    resolve_theme,
)

THEME_NAMES = ("legacy_bluegreen", "consulting_kpmg", "corporate_navy",
               "product_charcoal", "syzygit", "weaver_blue", "gov_red")


@pytest.mark.parametrize("name", THEME_NAMES)
def test_theme_tokens_css_snapshot(name):
    css = dg_theme.theme_tokens_css(name)
    t = THEMES[name]
    assert f"--t-primary:{t['primary']}" in css
    assert f"--t-accent:{t['accent']}" in css
    for state in ("lit", "part", "gap"):
        trio = t["tri"][state]
        assert f"--t-{state}-border:{trio['border']}" in css
        assert f"--t-{state}-bg:{trio['bg']}" in css
        assert f"--t-{state}-text:{trio['text']}" in css
    assert f"--t-hero-from:{t['hero']['from']}" in css
    assert f"--t-hero-to:{t['hero']['to']}" in css


def test_theme_qa_slot_snapshot():
    """S8 Wave B（C-E4）qa 语义槽预期 diff：全主题发射 --t-qa-*；
    默认官方绿 #2D796A/#D6F0D7，gov_red 金系覆写（禁红配绿裁决）。"""
    for name in THEME_NAMES:
        css = dg_theme.theme_tokens_css(name)
        assert "--t-qa-text:" in css and "--t-qa-bg:" in css, name
    assert "--t-qa-text:#2D796A" in dg_theme.theme_tokens_css("consulting_kpmg")
    assert "--t-qa-bg:#D6F0D7" in dg_theme.theme_tokens_css("consulting_kpmg")
    gov_css = dg_theme.theme_tokens_css("gov_red")
    assert "--t-qa-text:#7A5A14" in gov_css
    assert "--t-qa-bg:#FBF5E7" in gov_css


@pytest.mark.parametrize("name", THEME_NAMES)
def test_resolve_theme_derives_all_slots(name):
    t = resolve_theme(name)
    assert t.html_colors["primary"] == THEMES[name]["primary"]
    assert t.pptd_colors["primary"] == THEMES[name]["primary"]
    assert t.diagram_colors["blue"] == THEMES[name]["primary"]


def test_legacy_zero_diff_anchor():
    """legacy_bluegreen：diagram 19 槽与基线常量零 diff（F9）。"""
    t = resolve_theme("legacy_bluegreen")
    assert t.diagram_colors == DEFAULT_DIAGRAM_SLOTS
    css = dg_theme.theme_tokens_css("legacy_bluegreen")
    assert "--t-primary:#1B5E8A" in css


def test_weaver_and_gov_key_slots():
    """R-4 色彩批后的 weaver/gov_red 关键槽位锚定（新冻结值）。"""
    w = THEMES["weaver_blue"]
    assert w["primary"] == "#337AB7"
    assert w["primary_dark"] == "#0050A0"
    assert w["brand_green"] == "#00A040"
    assert w["navy_deep"] == "#22457F"
    assert w["roles"]["fin"] == "#007A31"
    assert w["surface"]["bg_soft"] == "#F7F9FB"
    g = THEMES["gov_red"]
    assert g["primary"] == "#A63428"
    assert g["hero"] == {"from": "#74241C", "to": "#A63428", "angle": 135}
    assert g["groups"] == {"red": "#F7EFEF", "gray": "#F5F0EA"}
    assert g["surface"]["bg_soft"] == "#FDF9F6"
    # 增补（用户裁决禁红配绿）：辅助色系换金/赭石/藏蓝
    assert g["roles"]["fin"] == "#2F4B7C"
    assert g["tri"]["lit"] == {"border": "#B08D3E", "bg": "#FBF5E7",
                               "text": "#7A5A14"}
    assert g["diagram_overrides"]["green"] == "#8A6116"
    assert "SimSun" in g["font_stack"]
