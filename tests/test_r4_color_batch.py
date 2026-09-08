# -*- coding: utf-8 -*-
"""R-4 色彩批（发版 S6 B2.5）回归测试。

覆盖（任务验收清单）：
- syzygit 主题注册（VI 冻结值）+ LEGACY_STYLE_TO_THEME 映射 + schema 枚举放行
  （含未知主题仍报错）
- gov_red / consulting_kpmg / weaver_blue 关键槽位断言
- 图形共享盘绿/紫新值断言（DEFAULT_DIAGRAM_SLOTS + legacy 锚定跟随）
- DEFAULT_PPTD_SLOTS / PPTD_SLOT_NAMES / resolve_theme 含 shadow 阴影槽（R-3 发射）
- 封面渲染产物无 #FFFFFF / rgba(255,255,255,*) 字面量（S2 清尾，HTML + pptd 双侧）
- 可选槽发射（on_dark / brand_green / navy_deep）与 gov_red groups 键名归位
"""


from _renderer.theme import (
    DEFAULT_DIAGRAM_SLOTS,
    DEFAULT_PPTD_SLOTS,
    LEGACY_STYLE_TO_THEME,
    PPTD_SLOT_NAMES,
    THEMES,
    bridge_css,
    normalize_theme_name,
    pptd_theme,
    resolve_theme,
    theme_tokens_css,
)


# ---- syzygit 主题注册 + 映射 + schema 枚举 ----

def test_syzygit_theme_registered_vi_values():
    t = THEMES["syzygit"]
    assert t["primary"] == "#0078FF"
    assert t["primary_dark"] == "#0A238B"
    assert t["primary_mid"] == "#4DA6FF"
    # VI 无金/橙 accent 角色 → 海军蓝承担强调；禁橙红旧色
    assert t["accent"] == "#0A238B"
    banned = ("#BC450A", "#C00000")
    for v in (t["accent"], t["primary"], t["primary_dark"], t["primary_mid"]):
        assert v not in banned
    # text 三档 + 页脚灰/分隔灰经 roles 承载
    assert t["text"] == {"primary": "#1A1A1A", "secondary": "#3A3A3A",
                         "tertiary": "#595959"}
    assert t["roles"]["ext"] == "#727171"
    assert t["roles"]["sys"] == "#B5B5B6"
    # chip 底 / 浅蓝卡片底 / 分隔 / 内容页背景
    assert t["surface"]["bg_muted"] == "#E5F3FF"
    assert t["surface"]["bg_soft"] == "#F4F9FF"
    assert t["surface"]["border"] == "#B5B5B6"
    assert t["surface"]["card"] == "#FFFFFF"
    assert t["hero"] == {"from": "#0A1540", "to": "#0A238B", "angle": 135}
    # 图表色序（roles 五槽即 VI 色序）
    assert [t["roles"][r] for r in ("biz", "legal", "fin", "sys", "ext")] == [
        "#0078FF", "#0A238B", "#4DA6FF", "#B5B5B6", "#727171"]


def test_syzygit_legacy_mapping_and_resolve():
    assert LEGACY_STYLE_TO_THEME["syzygit"] == "syzygit"
    assert normalize_theme_name("syzygit") == "syzygit"
    t = resolve_theme("syzygit")
    assert t.style_name == "syzygit"
    assert t.base["primary"] == "#0078FF"
    assert t.html_colors["primary"] == "#0078FF"
    assert t.diagram_colors["blue"] == "#0078FF"


def test_schema_theme_enum_accepts_syzygit_rejects_unknown():
    from _renderer.schema import _validate_doc_theme
    assert _validate_doc_theme({"theme": "syzygit"}) == []
    errors = _validate_doc_theme({"theme": "swiss_ikb"})
    assert errors and "未知主题" in errors[0]
    # dict 覆盖形态与缺省不拦（历史行为不变）
    assert _validate_doc_theme({"theme": {"primary": "#123456"}}) == []
    assert _validate_doc_theme({}) == []


# ---- 既有主题关键槽位（R-4 新冻结值） ----

def test_kpmg_r4_key_slots():
    t = THEMES["consulting_kpmg"]
    assert t["primary_mid"] == "#005EB8"
    assert t["accent"] == "#F3C13A"  # 仅深底/描边用（白底 2.2:1 不可正文）
    assert t["on_dark"] == {"text": "#FFFFFF", "accent": "#1192E8",
                            "muted": "#A8C0DC"}
    assert t["roles"]["sys"] == "#7C3AED"  # 紫保留


def test_weaver_r4_key_slots():
    t = THEMES["weaver_blue"]
    assert t["primary"] == "#337AB7"
    assert t["primary_dark"] == "#0050A0"
    assert t["brand_green"] == "#00A040"   # 图形/大元素用
    assert t["roles"]["fin"] == "#007A31"  # 文本用深绿
    assert t["navy_deep"] == "#22457F"
    assert t["hero"] == {"from": "#22457F", "to": "#337AB7", "angle": 135}
    assert t["accent"] == "#E8A33D"        # 金保留


def test_gov_red_desaturated_key_slots():
    t = THEMES["gov_red"]
    assert t["primary"] == "#A63428"
    assert t["hero"] == {"from": "#74241C", "to": "#A63428", "angle": 135}
    # 增补（用户裁决禁红配绿）：辅助色系换金/赭石/藏蓝/暖米
    assert t["roles"]["fin"] == "#2F4B7C"      # 青绿 → 藏蓝
    assert t["tri"]["lit"] == {"border": "#B08D3E", "bg": "#FBF5E7",
                               "text": "#7A5A14"}  # 翠绿 → 金赭
    assert t["groups"] == {"red": "#F7EFEF", "gray": "#F5F0EA"}
    # 主题级图形盘覆盖：共享盘绿/青族在枣红语境不现（timeline 绿条根因）
    assert t["diagram_overrides"] == {
        "green": "#8A6116", "green_light": "#F7F0DC",
        "teal": "#2F4B7C", "teal_light": "#EDF1F7"}
    assert resolve_theme("gov_red").diagram_colors["green"] == "#8A6116"
    # 共享盘与其他主题不受影响
    assert DEFAULT_DIAGRAM_SLOTS["green"] == "#198038"
    assert resolve_theme("corporate_navy").diagram_colors["green"] == "#198038"


# ---- 图形共享盘（全主题共享固定分组色） ----

def test_shared_diagram_disk_green_purple():
    assert DEFAULT_DIAGRAM_SLOTS["green"] == "#198038"
    assert DEFAULT_DIAGRAM_SLOTS["green_light"] == "#EAF6EF"
    assert DEFAULT_DIAGRAM_SLOTS["purple"] == "#8A3FFC"
    assert DEFAULT_DIAGRAM_SLOTS["purple_light"] == "#F2EDFF"
    # legacy 锚定跟随共享盘（F9 锚定语义不变：恒等于 DEFAULT_DIAGRAM_SLOTS）
    t = resolve_theme("legacy_bluegreen")
    assert t.diagram_colors["green"] == "#198038"
    assert t.diagram_colors["purple"] == "#8A3FFC"
    # 非 legacy 主题同盘受益
    assert resolve_theme("corporate_navy").diagram_colors["green"] == "#198038"


# ---- R-3 阴影槽发射 ----

def test_shadow_slot_end_to_end():
    assert "shadow" in PPTD_SLOT_NAMES
    assert DEFAULT_PPTD_SLOTS["shadow"] == "#0F172A"  # 中性灰，同 _pptd_convert 缺省
    for name in THEMES:
        assert resolve_theme(name).pptd_colors["shadow"] == "#0F172A", name
    # pptd deck 主题带 shadow 键（消费端 _pptd_convert 已就位）
    from _pptd_gen import _build_theme
    assert _build_theme("consulting_kpmg")["colors"]["shadow"] == "#0F172A"


# ---- 可选槽发射（tokens CSS / pptd_theme 双出口） ----

def test_optional_slots_emission():
    css = theme_tokens_css("consulting_kpmg")
    assert "--t-ondark-text:#FFFFFF" in css
    assert "--t-ondark-accent:#1192E8" in css
    assert "--t-ondark-muted:#A8C0DC" in css
    wcss = theme_tokens_css("weaver_blue")
    assert "--t-brand-green:#00A040" in wcss
    assert "--t-navy-deep:#22457F" in wcss
    # 未登记主题零输出
    scss = theme_tokens_css("syzygit")
    assert "ondark" not in scss and "brand-green" not in scss
    # gov_red groups 键名归位后的变量分发
    gcss = theme_tokens_css("gov_red")
    assert "--t-group-red:#F7EFEF" in gcss
    assert "--t-group-gray:#F5F0EA" in gcss
    assert "--t-group-blue:" not in gcss
    # gov_red tokens 增补：青绿系槽位已换藏蓝/金赭（禁红配绿）
    assert "--t-role-fin:#2F4B7C" in gcss
    assert "--t-lit-border:#B08D3E" in gcss
    assert "--t-lit-bg:#FBF5E7" in gcss
    # bridge 浅底变量回退指向实际分组键（旧 diagram 浅色填充不断链）
    assert "--blue-light: var(--t-group-red);" in bridge_css("gov_red")
    assert "--blue-light: var(--t-group-blue);" in bridge_css("corporate_navy")
    # pptd 侧扁平键
    wc = pptd_theme("weaver_blue")["colors"]
    assert wc["brand_green"] == "#00A040" and wc["navy_deep"] == "#22457F"
    assert pptd_theme("gov_red")["colors"]["group_red"] == "#F7EFEF"


# ---- 封面无白字硬编码（S2 清尾） ----

def _cover_doc():
    return {"title": "样张标题", "subtitle": "样张副标题", "author": "作者",
            "cover": {"template": "dark-photo", "confidential": "机密",
                      "show_author": True, "show_date": True},
            "date": "2026-09-07"}


def test_cover_html_no_white_literal(tmp_path, monkeypatch):
    """S2 清尾：封面「源码层」无白字硬编码（渲染值 WHITE=#FFFFFF 本身合法）。

    静态断言 _render_cover_html 源码体无 #FFFFFF / rgba(255,255,255,*) 字面量；
    动态断言渲染产物白字确实走 theme.WHITE 常量注入。
    """
    import inspect
    import yaml
    from _renderer import Renderer
    from _renderer.theme import WHITE
    src = inspect.getsource(Renderer._render_cover_html)
    assert "#FFFFFF" not in src
    assert "255,255,255" not in src
    monkeypatch.setenv("_PRESALES_CLI_INVOKED", "1")
    spec_file = tmp_path / "cover_spec.yml"
    spec_file.write_text(yaml.safe_dump(
        {"confirmed": True, "document": _cover_doc()}, allow_unicode=True),
        encoding="utf-8")
    r = Renderer(str(spec_file))
    html = r._render_cover_html(r.spec["document"])
    assert f"color:{WHITE}" in html
    assert "opacity:0.92" in html  # 原 rgba(255,255,255,0.92) 的语义化形态


def test_pptd_content_page_bg_no_white_literal():
    from _pptd_gen import _build_content_page, _build_theme
    import yaml as _yaml
    theme = _build_theme("corporate_navy")
    assert "shadow" in theme["colors"]  # R-3 发射端随主题到位
    page = _yaml.safe_load(_build_content_page(
        {"layout": "P01", "elements": []}, theme, None, 2))
    assert page["background"]["color"] == "#FFFFFF"  # 值仍白（card 槽）
    # 走主题槽位后，改主题 card 即改页面底色：替换 card 槽验证不再硬编码
    theme2 = _build_theme("corporate_navy")
    theme2["colors"]["card"] = "#F4F9FF"
    page2 = _yaml.safe_load(_build_content_page(
        {"layout": "P01", "elements": []}, theme2, None, 2))
    assert page2["background"]["color"] == "#F4F9FF"


# ---- syzygit 全链路渲染冒烟（HTML tokens 注入 + pptd 主题） ----

def test_syzygit_full_chain_smoke():
    css = theme_tokens_css("syzygit")
    for var in ("--t-primary:#0078FF", "--t-hero-from:#0A1540",
                "--t-hero-to:#0A238B", "--t-group-blue:#E5F3FF",
                "--t-role-ext:#727171"):
        assert var in css, var
    c = pptd_theme("syzygit")["colors"]
    assert c["primary"] == "#0078FF" and c["primary_dark"] == "#0A238B"
    assert c["primary_mid"] == "#4DA6FF"
    assert c["hero_from"] == "#0A1540" and c["hero_to"] == "#0A238B"
