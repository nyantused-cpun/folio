# -*- coding: utf-8 -*-
"""diagram 渲染共享主题：CSS 变量、字体栈、pptd 色板。

设计依据 docs/diagram_visual_design_v1_2026-07-19.md §2 设计令牌 +
§2.1 字体规范（中文雅黑 / 西文 Helvetica 回落 Arial / 标题强调加粗）。
所有渲染器只引用这里的常量，不写字面量。

§七 2.2/2.3：19 色与 FONT_PPT 收敛到样式单一源（_renderer/theme.py 的
resolve_theme）。模块装载时按默认风格（enterprise）解析，与重构前常量
逐值相等（arms_v5 基线零 diff）；渲染链路经 use_style 切换风格
（P2-A2 风格透传，分发器 render_diagram_html/pptd 的 style 参数驱动，
渲染器全部以 theme.X 调用时取值，重绑定模块属性即全链路生效）。
"""

from ..theme import DEFAULT_FONT, DEFAULT_STYLE_NAME, resolve_theme
from ..elements import _esc  # noqa: F401  单一源（§七 2.6），本模块及 5 个渲染器经 .theme 复用


def _apply_theme(style_name=None):
    """按风格重解析模块级常量（19 色槽 + 分层循环色 + PPT 字体 + SVG 箭头色）。"""
    global _theme, _dg
    global BLUE, BLUE_MID, BLUE_LIGHT, GREEN, GREEN_LIGHT, TEAL, TEAL_LIGHT
    global PURPLE, PURPLE_LIGHT, GRAY, ORANGE, ORANGE_LIGHT, RED, RED_LIGHT
    global BG, CARD, TEXT, TEXT_SUB, BORDER, LAYER_COLORS, FONT_PPT, SVG_DEFS
    _theme = resolve_theme(style_name)
    _dg = _theme.diagram_colors

    # ---- 色板（HTML 侧 hex；pptd 侧直接复用，保持同源同色） ----
    BLUE = _dg["blue"]
    BLUE_MID = _dg["blue_mid"]
    BLUE_LIGHT = _dg["blue_light"]
    GREEN = _dg["green"]
    GREEN_LIGHT = _dg["green_light"]
    TEAL = _dg["teal"]
    TEAL_LIGHT = _dg["teal_light"]
    PURPLE = _dg["purple"]
    PURPLE_LIGHT = _dg["purple_light"]
    GRAY = _dg["gray"]
    ORANGE = _dg["orange"]
    ORANGE_LIGHT = _dg["orange_light"]
    RED = _dg["red"]
    RED_LIGHT = _dg["red_light"]
    BG = _dg["bg"]
    CARD = _dg["card"]
    TEXT = _dg["text"]
    TEXT_SUB = _dg["text_sub"]
    BORDER = _dg["border"]

    # 分层循环色（layered / 4a 层标签用）
    LAYER_COLORS = [BLUE, GREEN, TEAL, PURPLE, GRAY]

    # PPT 侧：Helvetica 在 Windows 不可用，用 Arial 兜底西文；中文取 styles.json
    # fonts.body（当前全风格 Microsoft YaHei，与重构前值相同，只换来源）
    FONT_PPT = _theme.fonts.get("body", DEFAULT_FONT)

    # 共享 SVG 箭头 marker 定义（蓝 / 绿 两种，取色板常量不写字面量）+ 节点阴影 filter
    SVG_DEFS = f"""<defs>
<filter id="dgm-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#0F172A" flood-opacity="0.12"/></filter>
<marker id="dgm-arr" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="{BLUE}"/></marker>
<marker id="dgm-arr-g" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="{GREEN}"/></marker>
</defs>"""


# 模块装载：默认风格 enterprise（与重构前常量逐值相等，基线零 diff 锚定）
_apply_theme()
_ACTIVE_STYLE = DEFAULT_STYLE_NAME


def use_style(style_name=None):
    """切换 diagram 主题风格（P2-A2 风格透传）。

    分发器在渲染前调用；风格键名与当前相同则零开销跳过。渲染方应在
    finally 里用 current_style_name() 恢复，避免污染同进程后续渲染。
    """
    global _ACTIVE_STYLE
    key = style_name or DEFAULT_STYLE_NAME
    if key == _ACTIVE_STYLE:
        return
    _apply_theme(key)
    _ACTIVE_STYLE = key


def current_style_name():
    """当前模块常量对应的风格键名（分发器切风格后恢复用）。"""
    return _ACTIVE_STYLE


# 字体栈（§2.1：西文 Helvetica 回落 Arial，中文雅黑；风格无关，不随 use_style 变）
FONT_STACK = ('"Helvetica Neue", Helvetica, Arial, '
              '"Microsoft YaHei", "微软雅黑", sans-serif')

# 中性结构色（风格无关，v1 硬编码灰阶收敛；slate 蓝灰系，去脏灰）
WHITE = "#FFFFFF"            # 白色文字/填充
BORDER_STRONG = "#94A3B8"   # 泳道/容器边框（slate-400，带蓝的灰，去脏灰）
TEXT_STRONG = "#334155"     # 结构标签文字（slate-700，深蓝灰，去脏灰）

# ======================================================================
# 视觉规范 v2.0 主题包（dev_plan_visual_v2_2026-07-25 §9，F2/F5/F9 冻结）
#
# 与上方 styles.json 风格体系（resolve_theme 19/11/9 槽派生）分工：
#   - 风格体系管"既有 27 种 diagram + 旧版 HTML/pptd"的槽位，行为不变；
#   - THEMES 管 v2 新增维度：页面构件（hero/卡片/图例）、flow_rows、
#     三态芯片、角色色板。token 数远超 5 基色派生模型，故全量显式登记。
# legacy_bluegreen = v1.2 冻结蓝绿原样收编（F9：老 spec 缺省主题，
# 视觉不变）；consulting_kpmg = v2 主力主题（§9.2 tokens 基准，
# 三态 2026-08-13 提饱和去灰：lit/part 提饱和、gap 灰改红，
# 旧 #D69E2E/#A0AEC0 三态仅 legacy 保留）。
# ======================================================================

THEMES = {
    "legacy_bluegreen": {
        "primary": "#1B5E8A",        # = v1.2 BLUE
        "primary_dark": "#14486A",   # BLUE 调深一档（hero 渐变端点）
        "primary_mid": "#4A7FA5",    # = v1.2 BLUE_MID
        "accent": "#D69E2E",         # = v1.2 ORANGE
        "roles": {
            "biz": "#1B5E8A", "legal": "#C53030", "fin": "#2E8B8B",
            "sys": "#7B68AE", "ext": "#D69E2E",
        },
        "tri": {
            "lit":  {"border": "#2F7D5F", "bg": "#F0FAF5", "text": "#2F7D5F"},
            "part": {"border": "#D69E2E", "bg": "#FEF5E7", "text": "#B7791F"},
            "gap":  {"border": "#A0AEC0", "bg": "#F7F8FA", "text": "#718096"},
        },
        "text": {"primary": "#1A1A1A", "secondary": "#4A5568",
                 "tertiary": "#718096"},
        "surface": {"bg_soft": "#F7F8FA", "bg_muted": "#EDF2F7",
                    "border": "#E2E8F0", "card": "#FFFFFF"},
        "hero": {"from": "#14486A", "to": "#1B5E8A", "angle": 135},
        "groups": {"blue": "#EDF2F7", "teal": "#EDF6F6"},  # = v1.2 *_LIGHT
        # 派生浅色（旧 diagram 变量桥接用，v1.2 *_LIGHT 原值）
        "purple_light": "#F3F0F9", "red_light": "#FDEDEC",
        "font_stack": FONT_STACK,
    },
    "consulting_kpmg": {
        # §9.2 tokens 基准值（2026-07-25 定稿）；三态 2026-08-13 提饱和去灰
        "primary": "#00338D",
        "primary_dark": "#051C2C",
        "primary_mid": "#3D6AA8",
        "accent": "#FFE600",
        "roles": {
            "biz": "#00338D", "legal": "#E11D48", "fin": "#0D9488",
            "sys": "#7C3AED", "ext": "#EA580C",
        },
        "tri": {
            "lit":  {"border": "#059669", "bg": "#ECFDF5", "text": "#047857"},
            "part": {"border": "#EA580C", "bg": "#FFF7ED", "text": "#C2410C"},
            "gap":  {"border": "#DC2626", "bg": "#FEF2F2", "text": "#B91C1C"},
        },
        "text": {"primary": "#0F172A", "secondary": "#475569",
                 "tertiary": "#64748B"},
        "surface": {"bg_soft": "#F8FAFC", "bg_muted": "#F1F5F9",
                    "border": "#CBD5E1", "card": "#FFFFFF"},
        "hero": {"from": "#051C2C", "to": "#00338D", "angle": 135},
        # 行级底色分组：primary/fin 向白混合 0.93（与 _derive 同手法预算，
        # 避免运行时跨模块私有调用；值冻结于此）
        "groups": {"blue": "#EDF1F7", "teal": "#F3F6F5"},
        # 派生浅色（旧 diagram 变量桥接用，主色/系统紫 向白混合）
        "purple_light": "#F1EDFB", "red_light": "#FDEDED",
        "font_stack": FONT_STACK,
    },
    "corporate_navy": {
        # 汇报型（blue-professional 蓝本，2026-08-11 用户确认）：
        # 暖纸底 + 单一深蓝 accent + 三灰阶 + 投影安全三态（沿用 Okabe-Ito）
        "primary": "#1E3A8A",
        "primary_dark": "#101F4A",
        "primary_mid": "#4A6BB8",
        "accent": "#D97706",
        "roles": {
            "biz": "#1E3A8A", "legal": "#DC2626", "fin": "#059669",
            "sys": "#7C3AED", "ext": "#D97706",
        },
        "tri": {
            "lit":  {"border": "#009E73", "bg": "#E2F3EC", "text": "#00795A"},
            "part": {"border": "#D55E00", "bg": "#FBE7D9", "text": "#B04900"},
            "gap":  {"border": "#4A5568", "bg": "#EDF0F4", "text": "#4A5568"},
        },
        "text": {"primary": "#111111", "secondary": "#525252",
                 "tertiary": "#8A8A8A"},
        "surface": {"bg_soft": "#F8FAFC", "bg_muted": "#EEF1F6",
                    "border": "#D8DEE9", "card": "#FFFFFF"},
        "hero": {"from": "#101F4A", "to": "#1E3A8A", "angle": 135},
        "groups": {"blue": "#EEF1F7", "teal": "#F0F5F5"},
        "purple_light": "#F1EDFB", "red_light": "#FDEDED",
        "font_stack": FONT_STACK,
        "_meta": {
            "typography": {  # blue-professional 字号阶梯（vw 换算为文档 px 体系）
                "h1": 30, "h2": 24, "h3": 18, "body": 14,
                "caption": 12, "stat_value": 26, "stat_label": 12,
            },
            "spacing": {  # 8px 基距 token
                "sp-3": 8, "sp-4": 12, "sp-5": 16, "sp-6": 24,
                "sp-7": 32, "sp-8": 40, "sp-9": 48, "sp-10": 64,
            },
            "radii": {"card": 10, "pill": 100, "bar": 6},
            "components": {
                "card": "tint",       # 4% 主色 tint + 1.5px 半透明边框
                "shadow": "none",
                "bullet": "em-dash",  # mono 破折号项目符号
            },
        },
    },
    "product_charcoal": {
        # 产品介绍型（signal 蓝本，2026-08-11 用户确认）：
        # 深编辑蓝 navy + 暖纸 cream 双表面 + 古董金单一 accent
        "primary": "#1C2644",
        "primary_dark": "#0F1526",
        "primary_mid": "#232F55",
        "accent": "#C8A870",
        "roles": {
            "biz": "#1C2644", "legal": "#B03A48", "fin": "#2E5E4E",
            "sys": "#5B4A8A", "ext": "#C8A870",
        },
        "tri": {
            "lit":  {"border": "#009E73", "bg": "#E2F3EC", "text": "#00795A"},
            "part": {"border": "#D55E00", "bg": "#FBE7D9", "text": "#B04900"},
            "gap":  {"border": "#4A5568", "bg": "#EDF0F4", "text": "#4A5568"},
        },
        "text": {"primary": "#1A2030", "secondary": "#5A6270",
                 "tertiary": "#9AA0A8"},
        "surface": {"bg_soft": "#F7F6F2", "bg_muted": "#ECE9E0",
                    "border": "#CAC4B4", "card": "#FFFFFF"},
        "hero": {"from": "#0F1526", "to": "#1C2644", "angle": 135},
        "groups": {"blue": "#EAEDF3", "teal": "#EDF3F0"},
        "purple_light": "#F1EDFB", "red_light": "#FDEDED",
        "font_stack": FONT_STACK,
        "_meta": {
            "typography": {  # signal 字号阶梯（编辑风格，衬线/无衬线/等宽分工）
                "h1": 34, "h2": 26, "h3": 20, "body": 14,
                "caption": 12, "stat_value": 28, "stat_label": 12,
            },
            "spacing": {
                "sp-3": 8, "sp-4": 12, "sp-5": 16, "sp-6": 24,
                "sp-7": 32, "sp-8": 40, "sp-9": 48, "sp-10": 64,
            },
            "radii": {"card": 0, "pill": 100, "bar": 0},  # 直角发丝线（signal）
            "components": {
                "card": "flat",       # 无 tint，靠发丝线分隔
                "shadow": "none",
                "bullet": "em-dash",
            },
        },
    },
}

DEFAULT_V2_THEME = "legacy_bluegreen"  # F9：spec 不声明 theme 时的缺省


def get_theme(name=None):
    """取 v2 主题包 tokens。None/空 → legacy_bluegreen（F9）；非法名 raise。

    schema 层已拦非法值（§5.1），此处双保险（§9.1）。
    返回值为 THEMES 条目本体（只读使用，调用方禁改）。
    """
    key = name or DEFAULT_V2_THEME
    if key not in THEMES:
        raise ValueError(
            f"未知主题 {key!r}，合法值: {', '.join(sorted(THEMES))}")
    return THEMES[key]


def theme_tokens_css(name=None):
    """v2 主题 tokens 的 :root CSS 变量块（页面构件/flow_rows/三态消费）。

    变量统一 --t- 前缀，与既有 19 槽变量（--blue 等）命名空间隔离。
    """
    t = get_theme(name)
    tri, roles = t["tri"], t["roles"]
    text, surface, hero, groups = t["text"], t["surface"], t["hero"], t["groups"]
    lines = [":root {"]
    lines.append(f"  --t-primary:{t['primary']}; --t-primary-dark:{t['primary_dark']};"
                 f" --t-primary-mid:{t['primary_mid']}; --t-accent:{t['accent']};")
    for role, color in roles.items():
        lines.append(f"  --t-role-{role}:{color};")
    for state, trio in tri.items():
        lines.append(f"  --t-{state}-border:{trio['border']}; --t-{state}-bg:{trio['bg']};"
                     f" --t-{state}-text:{trio['text']};")
    lines.append(f"  --t-text-primary:{text['primary']}; --t-text-secondary:{text['secondary']};"
                 f" --t-text-tertiary:{text['tertiary']};")
    lines.append(f"  --t-bg-soft:{surface['bg_soft']}; --t-bg-muted:{surface['bg_muted']};"
                 f" --t-border:{surface['border']}; --t-card:{surface['card']};")
    lines.append(f"  --t-hero-from:{hero['from']}; --t-hero-to:{hero['to']};")
    lines.append(f"  --t-group-blue:{groups['blue']}; --t-group-teal:{groups['teal']};")
    # 派生浅色（旧 diagram 变量桥接用；THEMES 显式登记，禁 hex 硬编码）
    lines.append(f"  --t-purple-light:{t.get('purple_light', '#F3F0F9')};"
                 f" --t-red-light:{t.get('red_light', '#FDEDEC')};")
    # 派生透明度变量（hex8）：section-tag 底 8%、行标签边 15%、hl-yellow 荧光 55%
    lines.append(f"  --t-primary-a08:{t['primary']}14; --t-primary-a15:{t['primary']}26;"
                 f" --t-accent-a55:{t['accent']}8C;")
    lines.append("}")
    return "\n".join(lines)


def bridge_css(name=None):
    """旧 diagram 变量桥接（统一色板，独立块保 --t- 命名空间隔离）。

    既有 27 种 diagram 渲染器引用 --blue/--green/--orange 等 19 槽变量
    （css_variables 注入），v2 主题场景下映射到 --t-* 变量，让 diagram 与
    页面构件共用同一主题色板（legacy 等值零视觉变化，consulting_kpmg
    全链路 KPMG 深蓝+黄）。独立函数：不污染 theme_tokens_css 的命名空间
    （测试断言 tokens 块零旧变量），由 render_html / 编辑器注入器拼接。
    """
    return """/* 旧 diagram 变量桥接 -> v2 主题（--t- 变量） */
:root {
  --blue: var(--t-primary); --blue-mid: var(--t-primary-mid); --blue-light: var(--t-group-blue);
  --green: var(--t-lit-border); --green-light: var(--t-lit-bg);
  --teal: var(--t-role-fin); --teal-light: var(--t-group-teal);
  --purple: var(--t-role-sys); --purple-light: var(--t-purple-light);
  --gray: var(--t-gap-border);
  --orange: var(--t-accent); --orange-light: var(--t-part-bg);
  --red: var(--t-role-legal); --red-light: var(--t-red-light);
  --bg: var(--t-bg-soft); --card: var(--t-card);
  --text: var(--t-text-primary); --text-sub: var(--t-text-secondary);
  --border: var(--t-border);
}"""


def pptd_theme(name=None):
    """pptd 侧主题映射（§9.1）：页面构件/flow_rows 的 pptd 形状取色单点。

    返回 {"font": PPT 字体, "colors": {扁平键 -> hex}}，键与 CSS 变量同名
    （去 --t- 前缀），pptd_emit 侧禁写字面量。
    """
    t = get_theme(name)
    colors = {
        "primary": t["primary"], "primary_dark": t["primary_dark"],
        "primary_mid": t["primary_mid"], "accent": t["accent"],
        "hero_from": t["hero"]["from"], "hero_to": t["hero"]["to"],
        "group_blue": t["groups"]["blue"], "group_teal": t["groups"]["teal"],
    }
    for role, color in t["roles"].items():
        colors[f"role_{role}"] = color
    for state, trio in t["tri"].items():
        colors[f"{state}_border"] = trio["border"]
        colors[f"{state}_bg"] = trio["bg"]
        colors[f"{state}_text"] = trio["text"]
    colors.update({
        "text_primary": t["text"]["primary"],
        "text_secondary": t["text"]["secondary"],
        "text_tertiary": t["text"]["tertiary"],
        "bg_soft": t["surface"]["bg_soft"], "bg_muted": t["surface"]["bg_muted"],
        "border": t["surface"]["border"], "card": t["surface"]["card"],
    })
    return {"font": t["font_stack"], "font_ppt": FONT_PPT, "colors": colors}

# ---- CSS 片段 ----

def css_variables(style_name=None):
    """:root 变量块 + 字体栈（注入到 HTML <style>）。

    style_name（P2-A2 风格透传）：切到该风格取色后恢复原风格；None/当前
    风格直接取模块常量（enterprise 与重构前逐值相等，基线零 diff）。
    """
    if style_name is not None and style_name != _ACTIVE_STYLE:
        prev = _ACTIVE_STYLE
        use_style(style_name)
        try:
            return css_variables()
        finally:
            use_style(prev)
    return f"""
:root {{
  --blue:{BLUE};  --blue-mid:{BLUE_MID};  --blue-light:{BLUE_LIGHT};
  --green:{GREEN}; --green-light:{GREEN_LIGHT};
  --teal:{TEAL};  --teal-light:{TEAL_LIGHT};
  --purple:{PURPLE}; --purple-light:{PURPLE_LIGHT};
  --gray:{GRAY};
  --orange:{ORANGE}; --orange-light:{ORANGE_LIGHT};
  --red:{RED};   --red-light:{RED_LIGHT};
  --bg:{BG};     --card:{CARD};      --text:{TEXT};
  --text-sub:{TEXT_SUB}; --border:{BORDER};
}}
section.diagram, section.diagram svg text {{
  font-family: {FONT_STACK};
}}
section.diagram {{
  background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px 28px 28px; margin: 20px 0;
  box-shadow: 0 1px 4px rgba(27,94,138,0.05);
}}
section.diagram .dg-eyebrow {{
  font-size: 12px; font-weight: 700; letter-spacing: 2px;
  color: var(--text-sub); text-transform: uppercase;
}}
section.diagram .dg-title {{ font-size: 18px; font-weight: 700; color: var(--blue); margin: 4px 0 2px; }}
section.diagram .dg-desc {{ font-size: 13px; color: var(--text-sub); margin-bottom: 14px; }}
section.diagram .dg-body {{ overflow-x: auto; }}
section.diagram svg.dg {{ display: block; width: 100%; height: auto; background: #fff; }}
"""


def section_open(elem, eyebrow=None):
    """diagram section 头部（容器 + eyebrow + 标题 + 可选说明）。"""
    dt = elem.get("diagram_type", "")
    st = elem.get("subtype", "")
    title = _esc(elem.get("title", ""))
    desc = elem.get("desc", "")
    eyebrow = eyebrow or f"{dt} / {st}"
    parts = [
        f'<section class="diagram" data-diagram-type="{dt}" data-subtype="{st}">',
        f'  <div class="dg-eyebrow">{_esc(eyebrow)}</div>',
        f'  <div class="dg-title" data-editable="true">{title}</div>',
    ]
    if desc:
        parts.append(f'  <div class="dg-desc" data-editable="true">{_esc(desc)}</div>')
    parts.append('  <div class="dg-body">')
    return "\n".join(parts)


SECTION_CLOSE = "  </div>\n</section>"
