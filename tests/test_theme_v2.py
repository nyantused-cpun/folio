# -*- coding: utf-8 -*-
"""视觉规范 v2.0 主题包测试（dev_plan_visual_v2_2026-07-25 §9，T1）。

锚定：
- consulting_kpmg tokens = §9.2 冻结值（2026-07-25 用户确认，逐值断言）
- legacy_bluegreen = v1.2 常量原样收编（F9 老 spec 视觉不变）
- get_theme 非法名 raise（schema 双保险）；缺省 legacy_bluegreen
- theme_tokens_css / pptd_theme 结构完备且两主题同构
"""
import pytest

from _renderer.diagram import theme as dg_theme


# ---- get_theme ----

def test_get_theme_default_is_consulting():
    assert dg_theme.get_theme() is dg_theme.THEMES["consulting_kpmg"]
    assert dg_theme.get_theme(None) is dg_theme.THEMES["consulting_kpmg"]
    assert dg_theme.get_theme("") is dg_theme.THEMES["consulting_kpmg"]


def test_get_theme_valid_names():
    assert set(dg_theme.THEMES) == {
        "legacy_bluegreen", "consulting_kpmg", "corporate_navy",
        "product_charcoal", "weaver_blue", "gov_red", "syzygit",
    }
    assert dg_theme.get_theme("consulting_kpmg")["primary"] == "#00338D"


def test_get_theme_invalid_raises():
    with pytest.raises(ValueError) as exc:
        dg_theme.get_theme("swiss_ikb")  # F5：候选暂不实现
    assert "consulting_kpmg" in str(exc.value)
    assert "legacy_bluegreen" in str(exc.value)


# ---- §9.2 冻结 tokens 逐值锚定 ----

def test_kpmg_tokens_frozen():
    t = dg_theme.THEMES["consulting_kpmg"]
    assert t["primary"] == "#00338D"
    assert t["primary_dark"] == "#051C2C"
    assert t["primary_mid"] == "#005EB8"   # R-4：KPMG Medium Blue
    assert t["accent"] == "#F3C13A"        # R-4：降饱和金（仅深底/描边用）
    assert t["on_dark"] == {"text": "#FFFFFF", "accent": "#1192E8",
                            "muted": "#A8C0DC"}  # R-4 深底变体
    assert t["roles"] == {"biz": "#00338D", "legal": "#E11D48", "fin": "#0D9488",
                          "sys": "#7C3AED", "ext": "#EA580C"}
    # 三态提饱和 + 缺口去灰改红（2026-08-13 配色升级）
    assert t["tri"]["lit"] == {"border": "#059669", "bg": "#ECFDF5", "text": "#047857"}
    assert t["tri"]["part"] == {"border": "#EA580C", "bg": "#FFF7ED", "text": "#C2410C"}
    assert t["tri"]["gap"] == {"border": "#DC2626", "bg": "#FEF2F2", "text": "#B91C1C"}
    assert t["text"] == {"primary": "#0F172A", "secondary": "#475569",
                         "tertiary": "#64748B"}
    assert t["surface"] == {"bg_soft": "#F8FAFC", "bg_muted": "#F1F5F9",
                            "border": "#CBD5E1", "card": "#FFFFFF"}
    assert t["hero"] == {"from": "#051C2C", "to": "#00338D", "angle": 135}
    assert t["font_stack"] == dg_theme.FONT_STACK


def test_legacy_tokens_match_v12_constants():
    """legacy_bluegreen 原样收编 v1.2 蓝绿（F9：老 spec 视觉不变）。"""
    t = dg_theme.THEMES["legacy_bluegreen"]
    assert t["primary"] == "#1B5E8A"
    assert t["primary_mid"] == "#4A7FA5"
    assert t["accent"] == "#D69E2E"          # 旧三态色保留（仅 legacy）
    assert t["tri"]["part"]["border"] == "#D69E2E"
    assert t["tri"]["gap"]["border"] == "#A0AEC0"
    assert t["tri"]["lit"]["border"] == "#2F7D5F"
    assert t["groups"] == {"blue": "#EDF2F7", "teal": "#EDF6F6"}
    assert t["surface"]["card"] == "#FFFFFF"
    assert t["surface"]["border"] == "#E2E8F0"
    assert t["text"]["primary"] == "#1A1A1A"
    assert t["text"]["tertiary"] == "#718096"


def test_corporate_navy_tokens_frozen():
    """汇报型主题（blue-professional 蓝本：暖纸底 + 单一深蓝 accent + 三灰阶）。"""
    t = dg_theme.THEMES["corporate_navy"]
    assert t["primary"] == "#1E3A8A"          # 泛微系深蓝（投影可读）
    assert t["primary_dark"] == "#101F4A"     # hero 渐变端点
    assert t["primary_mid"] == "#4A6BB8"
    assert t["accent"] == "#D97706"           # 琥珀金（数据/CTA 强调）
    assert t["roles"]["biz"] == "#1E3A8A"
    assert t["tri"]["lit"] == {"border": "#009E73", "bg": "#E2F3EC", "text": "#00795A"}
    assert t["tri"]["part"] == {"border": "#D55E00", "bg": "#FBE7D9", "text": "#B04900"}
    assert t["tri"]["gap"] == {"border": "#4A5568", "bg": "#EDF0F4", "text": "#4A5568"}
    assert t["surface"]["card"] == "#FFFFFF"
    assert t["surface"]["bg_soft"] == "#F8FAFC"


def test_product_charcoal_tokens_frozen():
    """产品介绍型主题（signal 蓝本：深编辑蓝 + 暖纸双表面 + 古董金 accent）。"""
    t = dg_theme.THEMES["product_charcoal"]
    assert t["primary"] == "#1C2644"          # 深编辑蓝（navy）
    assert t["primary_dark"] == "#0F1526"
    assert t["primary_mid"] == "#232F55"      # navy-alt
    assert t["accent"] == "#C8A870"           # 古董金（signal 唯一 accent）
    assert t["surface"]["card"] == "#FFFFFF"
    assert t["surface"]["bg_soft"] == "#F7F6F2"  # 暖纸 cream


# R-4 可选槽（仅个别主题登记，.get 发射，缺省零影响）与分组键名
#（gov_red 归位 red/gray）：同构校验对这两类豁免，其余键严格同构
# 增补：diagram_overrides（gov_red 主题级图形盘覆盖，resolve_theme .get 应用）
# 增补（S8-B C-E4）：qa 语义槽（默认官方绿，gov_red 金系覆写，.get 发射）
OPTIONAL_TOP_KEYS = {"on_dark", "brand_green", "navy_deep", "diagram_overrides",
                     "qa"}


def _theme_shape(d, prefix=""):
    keys = set()
    for k, v in d.items():
        if not prefix and k in OPTIONAL_TOP_KEYS:
            continue
        if prefix == "groups.":
            keys.add("groups.*")  # 分组键名随主题语义归位，只校验槽位数
            continue
        keys.add(f"{prefix}{k}")
        if isinstance(v, dict):
            keys |= _theme_shape(v, f"{prefix}{k}.")
    return keys


def test_all_themes_structurally_isomorphic():
    """全部主题核心键结构同构（_meta/可选槽/分组键名豁免）。"""
    ref = _theme_shape(dg_theme.THEMES["legacy_bluegreen"])
    for name in ("consulting_kpmg", "corporate_navy", "product_charcoal",
                 "syzygit", "weaver_blue", "gov_red"):
        assert _theme_shape(dg_theme.THEMES[name]) == ref, f"{name} 与 legacy 键结构不同构"


def test_themes_meta_removed():
    """_meta 死注册已删除（Step 1：登记但渲染不消费）。"""
    for name in ("corporate_navy", "product_charcoal"):
        assert "_meta" not in dg_theme.THEMES[name], f"{name} 仍含 _meta 死注册"


def test_themes_structurally_isomorphic():
    """全部主题键结构同构（渲染层按键取色，缺键即炸——同构是硬约束）。

    豁免两类（R-4）：可选槽（on_dark/brand_green/navy_deep，.get 发射）
    与 groups 键名（gov_red 归位 red/gray——消费端已泛化为按键名分发）。
    """
    ref = _theme_shape(dg_theme.THEMES["legacy_bluegreen"])
    for name in ("consulting_kpmg", "corporate_navy", "product_charcoal",
                 "syzygit", "weaver_blue", "gov_red"):
        assert _theme_shape(dg_theme.THEMES[name]) == ref, name
    # 分组槽位数的硬性不变量：每主题恰好 2 个分组底色，且均为合法 hex
    import re
    hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
    for name, t in dg_theme.THEMES.items():
        groups = t["groups"]
        assert len(groups) == 2, f"{name} groups 槽位数 != 2"
        for gcolor in groups.values():
            assert hex_re.match(gcolor), f"{name} groups 值非法: {gcolor}"


# ---- theme_tokens_css ----

def test_tokens_css_root_block():
    css = dg_theme.theme_tokens_css("consulting_kpmg")
    assert css.startswith(":root {")
    assert css.rstrip().endswith("}")
    for var in ("--t-primary:#00338D", "--t-accent:#F3C13A",
                "--t-role-legal:#E11D48", "--t-lit-border:#059669",
                "--t-part-bg:#FFF7ED", "--t-gap-text:#B91C1C",
                "--t-text-primary:#0F172A", "--t-bg-soft:#F8FAFC",
                "--t-hero-from:#051C2C", "--t-hero-to:#00338D",
                "--t-group-blue:", "--t-group-teal:",
                "--t-ondark-text:#FFFFFF", "--t-ondark-accent:#1192E8",
                "--t-ondark-muted:#A8C0DC"):
        assert var in css


def test_tokens_css_default_consulting_namespace_isolated():
    css = dg_theme.theme_tokens_css()  # 缺省 consulting_kpmg
    assert "--t-primary:#00338D" in css
    # 与既有 19 槽变量命名空间隔离（--blue 等不出现在 tokens 块）
    for line in css.splitlines():
        assert "--blue:" not in line and "--green:" not in line


# ---- pptd_theme ----

def test_pptd_theme_structure():
    p = dg_theme.pptd_theme("consulting_kpmg")
    assert p["font"] == dg_theme.FONT_STACK
    assert p["font_ppt"] == dg_theme.FONT_PPT
    c = p["colors"]
    for key in ("primary", "primary_dark", "primary_mid", "accent",
                "hero_from", "hero_to", "group_blue", "group_teal",
                "role_biz", "role_legal", "role_fin", "role_sys", "role_ext",
                "lit_border", "lit_bg", "lit_text",
                "part_border", "part_bg", "part_text",
                "gap_border", "gap_bg", "gap_text",
                "text_primary", "text_secondary", "text_tertiary",
                "bg_soft", "bg_muted", "border", "card"):
        assert key in c, f"pptd colors 缺键 {key}"
        assert c[key].startswith("#")
    assert c["role_sys"] == "#7C3AED"
