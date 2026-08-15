# -*- coding: utf-8 -*-
"""_renderer.theme（样式单一源）测试。

覆盖：resolve_theme 优先级（override > 显式 html 块 > 派生 > 默认）、
enterprise 显式槽 == 重构前硬编码 9 值、派生输出合法 hex、fonts 读取、
pptd 11 槽 / diagram 19 槽（enterprise 锚定 DEFAULT + 非 enterprise 派生）、
style_name_for_entry 反查、diagram/theme.py 常量导出镜像。
"""

import json
import re

import pytest

from _renderer import theme as theme_mod
from _renderer.theme import (
    DEFAULT_DIAGRAM_SLOTS,
    DEFAULT_HTML_SLOTS,
    DEFAULT_PPTD_SLOTS,
    DIAGRAM_SLOT_NAMES,
    HTML_SLOT_NAMES,
    PPTD_SLOT_NAMES,
    Theme,
    resolve_theme,
    style_name_for_entry,
)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class TestEnterpriseExplicitSlots:
    """enterprise 的显式 html 块必须等于重构前 HTML 端硬编码 9 值（零 diff 保证）。"""

    def test_explicit_block_equals_legacy_hardcoded(self):
        t = resolve_theme("enterprise")
        assert t.html_colors == DEFAULT_HTML_SLOTS
        assert t.html_colors == {
            "heading": "#1a365d",
            "primary": "#3182ce",
            "h2": "#2c5282",
            "subtitle": "#718096",
            "muted": "#a0aec0",
            "table_header_bg": "#ebf8ff",
            "border": "#e2e8f0",
            "card_bg": "#f7fafc",
            "card_title": "#2c5282",
        }

    def test_default_and_unknown_style_fall_back_to_enterprise(self):
        assert resolve_theme(None).html_colors == DEFAULT_HTML_SLOTS
        assert resolve_theme("nonexistent").style_name == "enterprise"
        assert resolve_theme("nonexistent").html_colors == DEFAULT_HTML_SLOTS


class TestPriority:
    """优先级：spec 覆盖 > 显式 html 块 > 派生 > 默认。"""

    def test_override_beats_explicit(self):
        t = resolve_theme("enterprise", {"primary": "#123456"})
        assert t.html_colors["primary"] == "#123456"
        # 未覆盖的槽仍取显式块
        assert t.html_colors["heading"] == "#1a365d"

    def test_explicit_beats_derived(self):
        # enterprise 有显式块：即使 5 基色不同，槽位也不走派生
        t = resolve_theme("enterprise")
        assert t.html_colors["primary"] == "#3182ce"  # 显式块值
        assert t.html_colors["primary"] != t.base["primary"]  # #2b6cb0

    def test_derived_when_no_explicit_block(self):
        # bookish 无显式 html 块 → 走派生
        t = resolve_theme("bookish")
        base = t.base
        assert t.html_colors["heading"] == base["text"]
        assert t.html_colors["primary"] == base["primary"]
        assert t.html_colors["h2"] == base["text"]
        assert t.html_colors["table_header_bg"] == base["background"]
        assert t.html_colors["card_bg"] == base["background"]
        assert t.html_colors["card_title"] == base["text"]

    def test_default_when_no_colors(self, tmp_path, monkeypatch):
        # 风格既无 html 块又无 colors → 槽位落 DEFAULT_HTML_SLOTS
        fake = {"minimal": {"name": "裸风格", "fonts": {"body": "SimSun"}}}
        p = tmp_path / "styles.json"
        p.write_text(json.dumps(fake), encoding="utf-8")
        monkeypatch.setattr(theme_mod, "STYLES_PATH", str(p))
        t = resolve_theme("minimal")
        assert t.html_colors == DEFAULT_HTML_SLOTS

    def test_missing_styles_file_falls_back_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(theme_mod, "STYLES_PATH", str(tmp_path / "nope.json"))
        t = resolve_theme("enterprise")
        assert t.html_colors == DEFAULT_HTML_SLOTS
        assert t.fonts["body"] == "Microsoft YaHei"


class TestDerivedSlotsValid:
    """派生函数输出必须是合法 hex，且 subtitle/muted/border 的调亮调深方向正确。"""

    @pytest.mark.parametrize("name", ["bookish", "education", "tech", "gov", "syzygit"])
    def test_derived_slots_are_valid_hex(self, name):
        t = resolve_theme(name)
        assert isinstance(t, Theme)
        assert set(t.html_colors) == set(HTML_SLOT_NAMES)
        for slot, value in t.html_colors.items():
            assert HEX_RE.match(value), f"{name}.{slot} 非法: {value}"

    def test_lighten_darken_direction(self):
        t = resolve_theme("bookish")
        text_rgb = int(t.base["text"][1:3], 16)
        subtitle_rgb = int(t.html_colors["subtitle"][1:3], 16)
        muted_rgb = int(t.html_colors["muted"][1:3], 16)
        # 调亮两档：muted 比 subtitle 更亮，两者都比 text 亮
        assert text_rgb < subtitle_rgb < muted_rgb
        # border 比 background 深
        bg_r = int(t.base["background"][1:3], 16)
        border_r = int(t.html_colors["border"][1:3], 16)
        assert border_r < bg_r

    def test_override_beats_derived(self):
        t = resolve_theme("bookish", {"card_bg": "#abcdef"})
        assert t.html_colors["card_bg"] == "#abcdef"


class TestCardTitleFollowsH2:
    """历史行为：card_title 未被覆盖时跟随 h2（兼容 spec 只覆盖 h2 的写法）。"""

    def test_card_title_follows_h2_override(self):
        t = resolve_theme("bookish", {"h2": "#112233"})
        assert t.html_colors["h2"] == "#112233"
        assert t.html_colors["card_title"] == "#112233"

    def test_card_title_explicit_override_wins(self):
        t = resolve_theme("bookish", {"h2": "#112233", "card_title": "#445566"})
        assert t.html_colors["card_title"] == "#445566"


class TestFonts:
    """fonts 从 styles.json 读取（heading/body），缺省 Microsoft YaHei。"""

    def test_bookish_fonts(self):
        t = resolve_theme("bookish")
        assert t.fonts["heading"] == "Times New Roman"
        assert t.fonts["body"] == "Microsoft YaHei"

    def test_dict_form_font_compat(self, tmp_path, monkeypatch):
        fake = {"x": {"colors": {"primary": "#111111"},
                      "fonts": {"body": {"name": "KaiTi"}}}}
        p = tmp_path / "styles.json"
        p.write_text(json.dumps(fake), encoding="utf-8")
        monkeypatch.setattr(theme_mod, "STYLES_PATH", str(p))
        t = resolve_theme("x")
        assert t.fonts["body"] == "KaiTi"
        assert t.fonts["heading"] == "Microsoft YaHei"


class TestPptdSlots:
    """pptd 11 槽：enterprise 锚定 DEFAULT（= 重构前 _build_theme 产出，
    基线零 diff 保证），其余风格从 5 基色派生；不接 spec_overrides
    （保持重构前无覆盖路径的行为）。"""

    def test_enterprise_equals_legacy_build_theme_output(self):
        t = resolve_theme("enterprise")
        assert t.pptd_colors == DEFAULT_PPTD_SLOTS
        assert t.pptd_colors == {
            "primary": "#2b6cb0",
            "navy": "#4299e1",
            "ink": "#1A1A1A",
            "body": "#3A3A3A",
            "lead": "#595959",
            "gray": "#727171",
            "ltgray": "#B5B5B6",
            "chip": "#E5F3FF",
            "card": "#F4F9FF",
            "veil": "#0A1540",
            "hairline": "#D8E2EE",
        }

    def test_default_and_unknown_style_fall_back_to_enterprise(self):
        assert resolve_theme(None).pptd_colors == DEFAULT_PPTD_SLOTS
        assert resolve_theme("nonexistent").pptd_colors == DEFAULT_PPTD_SLOTS

    @pytest.mark.parametrize("name", ["bookish", "education", "tech", "gov", "syzygit"])
    def test_derived_slots_are_valid_hex(self, name):
        t = resolve_theme(name)
        assert set(t.pptd_colors) == set(PPTD_SLOT_NAMES)
        # 键序即主 pptd YAML 键序（yaml.safe_dump sort_keys=False 消费）
        assert list(t.pptd_colors) == list(PPTD_SLOT_NAMES)
        for slot, value in t.pptd_colors.items():
            assert HEX_RE.match(value), f"{name}.{slot} 非法: {value}"

    def test_derived_anchors_follow_base(self):
        t = resolve_theme("syzygit")
        assert t.pptd_colors["primary"] == t.base["primary"]    # #0078FF
        assert t.pptd_colors["navy"] == t.base["secondary"]     # #0A238B
        assert t.pptd_colors["ink"] == t.base["text"]           # #1A1A1A
        assert t.pptd_colors["card"] == t.base["background"]    # #F4F9FF

    def test_spec_overrides_do_not_leak_into_pptd(self):
        # 保持重构前行为：spec.theme.colors 只覆盖 HTML 槽，不碰 pptd 槽
        t = resolve_theme("bookish", {"primary": "#123456"})
        assert t.html_colors["primary"] == "#123456"
        assert t.pptd_colors["primary"] == t.base["primary"]


class TestDiagramSlots:
    """diagram 19 槽：enterprise == 重构前 diagram/theme.py 19 常量原值
    （arms_v5 基线零 diff 锚定）；非 enterprise 只重映射 blue 族锚点色，
    语义/分类/中性色保持默认。"""

    def test_enterprise_equals_legacy_constants(self):
        t = resolve_theme("enterprise")
        assert t.diagram_colors == DEFAULT_DIAGRAM_SLOTS
        assert t.diagram_colors == {
            "blue": "#1B5E8A", "blue_mid": "#4A7FA5", "blue_light": "#EDF2F7",
            "green": "#2F7D5F", "green_light": "#F0FAF5",
            "teal": "#2E8B8B", "teal_light": "#EDF6F6",
            "purple": "#7B68AE", "purple_light": "#F3F0F9",
            "gray": "#A0AEC0",
            "orange": "#D69E2E", "orange_light": "#FEF5E7",
            "red": "#C53030", "red_light": "#FDEDEC",
            "bg": "#F7F8FA", "card": "#FFFFFF",
            "text": "#1A1A1A", "text_sub": "#718096", "border": "#E2E8F0",
        }

    def test_default_and_unknown_style_fall_back_to_enterprise(self):
        assert resolve_theme(None).diagram_colors == DEFAULT_DIAGRAM_SLOTS
        assert resolve_theme("nonexistent").diagram_colors == DEFAULT_DIAGRAM_SLOTS

    @pytest.mark.parametrize("name", ["bookish", "education", "tech", "gov", "syzygit"])
    def test_derived_slots_are_valid_hex(self, name):
        t = resolve_theme(name)
        assert set(t.diagram_colors) == set(DIAGRAM_SLOT_NAMES)
        for slot, value in t.diagram_colors.items():
            assert HEX_RE.match(value), f"{name}.{slot} 非法: {value}"

    def test_anchor_remap_only_blue_family(self):
        t = resolve_theme("bookish")
        assert t.diagram_colors["blue"] == t.base["primary"]  # #2b1810
        # mid/light 为 primary 调亮档：合法 hex 且不等于默认
        assert HEX_RE.match(t.diagram_colors["blue_mid"])
        assert HEX_RE.match(t.diagram_colors["blue_light"])
        assert t.diagram_colors["blue_mid"] != DEFAULT_DIAGRAM_SLOTS["blue_mid"]
        # 非锚点（语义/分类/中性色）保持默认
        for slot in DIAGRAM_SLOT_NAMES:
            if slot in ("blue", "blue_mid", "blue_light"):
                continue
            assert t.diagram_colors[slot] == DEFAULT_DIAGRAM_SLOTS[slot], slot


class TestStyleNameForEntry:
    """style_name_for_entry：_resolve_style 返回的 entry dict 反查风格键名。"""

    def test_match_registered_styles(self):
        styles = theme_mod._load_styles()
        for name in ("enterprise", "bookish", "syzygit"):
            assert style_name_for_entry(styles[name]) == name

    def test_unknown_entry_falls_back_to_enterprise(self):
        assert style_name_for_entry({}) == "enterprise"
        assert style_name_for_entry(None) == "enterprise"
        assert style_name_for_entry({"colors": {"primary": "#000000"}}) == "enterprise"


class TestDiagramThemeModule:
    """_renderer/diagram/theme.py 常量导出必须镜像 DEFAULT_DIAGRAM_SLOTS
    （flow/matrix 等模块 `from . import theme` 后读 theme.XXX，引用不破）。"""

    def test_constants_mirror_default_slots(self):
        from _renderer.diagram import theme as dg_theme
        for slot in DIAGRAM_SLOT_NAMES:
            assert getattr(dg_theme, slot.upper()) == DEFAULT_DIAGRAM_SLOTS[slot], slot

    def test_font_ppt_reads_fonts_body(self):
        from _renderer.diagram import theme as dg_theme
        assert dg_theme.FONT_PPT == resolve_theme().fonts["body"] == "Microsoft YaHei"

    def test_layer_colors_follow_palette(self):
        from _renderer.diagram import theme as dg_theme
        assert dg_theme.LAYER_COLORS == [
            dg_theme.BLUE, dg_theme.GREEN, dg_theme.TEAL,
            dg_theme.PURPLE, dg_theme.GRAY]

    def test_svg_defs_use_palette_constants(self):
        from _renderer.diagram import theme as dg_theme
        assert f'fill="{dg_theme.BLUE}"' in dg_theme.SVG_DEFS
        assert f'fill="{dg_theme.GREEN}"' in dg_theme.SVG_DEFS
