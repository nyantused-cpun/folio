# -*- coding: utf-8 -*-
"""样式单一源（Step 2）：THEMES v2 主题 tokens + 槽位派生 + spec 覆盖。三端共用。

HTML 渲染需要 9 个颜色槽（heading/primary/h2/subtitle/muted/
table_header_bg/border/card_bg/card_title），pptd 需要 12 槽
（PPTD_SLOT_NAMES，含阴影槽 shadow），diagram 需要 19 槽
（DIAGRAM_SLOT_NAMES）。
本模块以 THEMES 为唯一事实源，把主题 tokens -> 各端槽位的推导收敛为单点。
HTML 槽解析优先级（高 -> 低）：

1. spec_overrides（spec.theme.colors 逐槽覆盖，保持历史行为）
2. 派生函数 _derive_html_slots（从主题 tokens 的 5 基色推导）
3. DEFAULT_HTML_SLOTS（兜底）

pptd/diagram 槽不接 spec_overrides：全部走
_derive_pptd_slots / _derive_diagram_slots 派生；legacy_bluegreen 的
diagram 槽锚定 DEFAULT_DIAGRAM_SLOTS（基线零 diff 保证）。

quote 链路消费 base/fonts（见 _quote_html._load_quote_style）。
"""
from typing import Dict, NamedTuple

from _renderer.elements import _esc  # noqa: F401  渲染层经 .theme 复用

# HTML 端 9 个颜色槽（单一事实源，_get_html_styles 的 CSS 模板消费）
HTML_SLOT_NAMES = (
    "heading", "primary", "h2", "subtitle", "muted",
    "table_header_bg", "border", "card_bg", "card_title",
)

# 重构前 _get_html_styles 的硬编码配色（enterprise 的 curated 值同源于此）
DEFAULT_HTML_SLOTS = {
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

DEFAULT_STYLE_NAME = "consulting_kpmg"
DEFAULT_FONT = "Microsoft YaHei"

# pptd 端 12 个颜色槽（_pptd_gen._build_theme 消费，顺序即主 pptd YAML 键序）
PPTD_SLOT_NAMES = (
    "primary", "navy", "ink", "body", "lead", "gray",
    "ltgray", "chip", "card", "veil", "hairline", "shadow",
)

# veil 默认色单点（封面遮罩）：HTML 封面（_renderer/__init__）、pptd 封面
# （_pptd_gen）与 pptd 槽位表三处兜底共用此值，禁再写 hex 字面量。
DEFAULT_VEIL = "#0A1540"

# qa_block 语义槽（C-E4 官方绿，2026-09-07）：字 #2D796A / 填充 #D6F0D7，
# 全主题默认同值；主题可用可选 "qa" 槽覆写（gov_red 登记金系对，遵守
# 「禁红配绿」裁决——枣红语境下官方绿为互补撞色）。发射面：
# theme_tokens_css（--t-qa-text/--t-qa-bg）+ pptd_theme（qa_text/qa_bg）。
DEFAULT_QA_SLOTS = {"text": "#2D796A", "bg": "#D6F0D7"}

# 重构前 _build_theme 对 enterprise 的产出：primary/navy 取 enterprise 基色，
# 其余 9 槽为 v3 工程实测硬编码值。enterprise 锚定此表（基线零 diff 保证）。
DEFAULT_PPTD_SLOTS = {
    "primary": "#2b6cb0",
    "navy": "#4299e1",
    "ink": "#1A1A1A",
    "body": "#3A3A3A",
    "lead": "#595959",
    "gray": "#727171",
    "ltgray": "#B5B5B6",
    "chip": "#E5F3FF",
    "card": "#F4F9FF",
    "veil": DEFAULT_VEIL,
    "hairline": "#D8E2EE",
    # 柔和阴影槽（R-3 发射端）：中性 slate 深灰，与 _pptd_convert 缺省阴影
    # 色同源同值；消费端 flowChart 节点阴影经 theme.colors.shadow 取色
    "shadow": "#0F172A",
}

# diagram 端 19 个颜色槽（_renderer/diagram/theme.py 消费，
# 键名 = 重构前常量名小写）
DIAGRAM_SLOT_NAMES = (
    "blue", "blue_mid", "blue_light", "green", "green_light",
    "teal", "teal_light", "purple", "purple_light", "gray",
    "orange", "orange_light", "red", "red_light",
    "bg", "card", "text", "text_sub", "border",
)

# 图形分组色共享盘（全主题固定）：绿/紫 2026-09-07 R-4 色彩批提饱和去灰
# （IBM Carbon green-60/purple-60，靠明度分层不只靠色相），浅底配套同步；
# legacy_bluegreen 的 diagram 19 槽锚定本表（旧 #2F7D5F/#7B68AE 仅其
# 页面构件 tri/roles 保留）。
DEFAULT_DIAGRAM_SLOTS = {
    "blue": "#1B5E8A",
    "blue_mid": "#4A7FA5",
    "blue_light": "#EDF2F7",
    "green": "#198038",
    "green_light": "#EAF6EF",
    "teal": "#2E8B8B",
    "teal_light": "#EDF6F6",
    "purple": "#8A3FFC",
    "purple_light": "#F2EDFF",
    "gray": "#A0AEC0",
    "orange": "#D69E2E",
    "orange_light": "#FEF5E7",
    "red": "#C53030",
    "red_light": "#FDEDEC",
    "bg": "#F7F8FA",
    "card": "#FFFFFF",
    "text": "#1A1A1A",
    "text_sub": "#718096",
    "border": "#E2E8F0",
}


class Theme(NamedTuple):
    """解析后的主题：HTML 9 槽 + pptd 11 槽 + diagram 19 槽 + 字体 + 5 基色 + 风格名。"""
    style_name: str
    html_colors: Dict[str, str]    # 9 槽，见 HTML_SLOT_NAMES
    fonts: Dict[str, str]          # {"heading": ..., "body": ...}
    base: Dict[str, str]           # 主题 tokens 的 5 基色（quote 链路消费）
    pptd_colors: Dict[str, str]    # 12 槽，见 PPTD_SLOT_NAMES
    diagram_colors: Dict[str, str]  # 19 槽，见 DIAGRAM_SLOT_NAMES


# 旧 style 语义 -> v2 theme 迁移映射（Step 2）
LEGACY_STYLE_TO_THEME = {
    "education": "consulting_kpmg",
    "enterprise": "corporate_navy",
    "tech": "product_charcoal",
    "gov": "gov_red",
    "syzygit": "syzygit",  # R-4：VI 主题包收编，修存量 style: syzygit 静默回退
}


def normalize_theme_name(name=None):
    """把主题名/旧 style 名归一为 THEMES 键；未知/空回退 consulting_kpmg。"""
    if not name:
        return DEFAULT_STYLE_NAME
    if name in THEMES:
        return name
    if name in LEGACY_STYLE_TO_THEME:
        return LEGACY_STYLE_TO_THEME[name]
    return DEFAULT_STYLE_NAME


def _single_font_from_stack(font_stack, default=DEFAULT_FONT):
    """从 CSS font stack 中取第一个常见中文字体名，作为 docx/pptd 单值字体。"""
    if not isinstance(font_stack, str):
        return default
    for token in font_stack.strip().split(","):
        name = token.strip().strip('"').strip("'")
        if name and name not in ("sans-serif", "serif", "Helvetica Neue",
                                 "Helvetica", "Arial"):
            return name
    return default


def _parse_hex(color):
    """#RRGGBB -> (r, g, b)；非法输入返回 None（调用方回退原值）。"""
    if not isinstance(color, str):
        return None
    h = color.lstrip("#")
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _to_hex(r, g, b):
    def clamp(v):
        return max(0, min(255, int(round(v))))
    return "#{:02x}{:02x}{:02x}".format(clamp(r), clamp(g), clamp(b))


def _lighten(color, ratio):
    """向白色混合 ratio（0=原色，1=纯白）。非法输入原样返回。"""
    rgb = _parse_hex(color)
    if rgb is None:
        return color
    return _to_hex(*(c + (255 - c) * ratio for c in rgb))


def _darken(color, ratio):
    """向黑色混合 ratio（0=原色，1=纯黑）。非法输入原样返回。"""
    rgb = _parse_hex(color)
    if rgb is None:
        return color
    return _to_hex(*(c * (1 - ratio) for c in rgb))


def _derive_html_slots(base):
    """从风格 5 基色推导 HTML 9 槽（风格无显式 "html" 块时使用）。

    推导规则：heading/h2/card_title 跟随 text；primary 用品牌主色；
    subtitle/muted 为 text 向白调亮两档（0.35/0.55，近似原硬编码里
    #2c5282->#718096->#a0aec0 的明度节奏）；table_header_bg/card_bg
    用 background；border 为 background 调深一档（0.10）。
    """
    text = base.get("text", DEFAULT_HTML_SLOTS["heading"])
    bg = base.get("background", DEFAULT_HTML_SLOTS["card_bg"])
    return {
        "heading": text,
        "primary": base.get("primary", DEFAULT_HTML_SLOTS["primary"]),
        "h2": text,
        "subtitle": _lighten(text, 0.35),
        "muted": _lighten(text, 0.55),
        "table_header_bg": bg,
        "border": _darken(bg, 0.10),
        "card_bg": bg,
        "card_title": text,
    }


def _derive_pptd_slots(base):
    """从风格 5 基色推导 pptd 12 槽（非 enterprise 风格使用）。

    推导规则：primary/navy 跟随品牌主/辅色；文字阶梯 ink->body->lead
    ->gray->ltgray 为 base.text 向白调亮五档（0/0.14/0.275/0.38/0.68，
    节奏对齐原硬编码 #1A1A1A->#3A3A3A->#595959->#727171->#B5B5B6）；
    card 用 base.background，chip/hairline 为其调深两档（0.06/0.12）；
    veil 为 background 调深 0.93 的暗场色（封面遮罩用）；shadow 为共享
    中性阴影槽，直接锚定 DEFAULT_PPTD_SLOTS（不随主题派生）。
    """
    text = base.get("text", DEFAULT_PPTD_SLOTS["ink"])
    bg = base.get("background", DEFAULT_PPTD_SLOTS["card"])
    return {
        "primary": base.get("primary", DEFAULT_PPTD_SLOTS["primary"]),
        "navy": base.get("secondary", DEFAULT_PPTD_SLOTS["navy"]),
        "ink": text,
        "body": _lighten(text, 0.14),
        "lead": _lighten(text, 0.275),
        "gray": _lighten(text, 0.38),
        "ltgray": _lighten(text, 0.68),
        "chip": _darken(bg, 0.06),
        "card": bg,
        "veil": _darken(bg, 0.93),
        "hairline": _darken(bg, 0.12),
        "shadow": DEFAULT_PPTD_SLOTS["shadow"],
    }


def _derive_diagram_slots(base):
    """从风格 5 基色推导 diagram 19 槽（非 enterprise 风格使用）。

    只重映射品牌锚点色：blue 族跟随 base.primary（blue_mid/blue_light
    为调亮 0.20/0.93 两档）。green/teal/purple/orange/red 及其浅色是
    语义/分类色，与中性色（bg/card/text/text_sub/border/gray）一起
    保持默认；LAYER_COLORS 分层循环色的其余成员后续可按风格 curate。
    """
    slots = dict(DEFAULT_DIAGRAM_SLOTS)
    primary = base.get("primary")
    if primary:
        slots["blue"] = primary
        slots["blue_mid"] = _lighten(primary, 0.20)
        slots["blue_light"] = _lighten(primary, 0.93)
    return slots


def resolve_theme(style_name=None, spec_overrides=None):
    """解析主题：唯一事实源为 THEMES v2 tokens（Step 2）。

    style_name 为空/未知时回退 consulting_kpmg；旧 style 名自动映射到
    v2 theme（education→consulting_kpmg 等）。spec_overrides 即
    spec.theme.colors 逐槽覆盖，只作用于 HTML 9 槽。
    """
    name = normalize_theme_name(style_name)
    t = THEMES.get(name, THEMES[DEFAULT_STYLE_NAME])
    base = {
        "primary": t["primary"],
        "secondary": t.get("primary_mid", t["primary"]),
        "accent": t.get("accent", t["primary"]),
        "background": t["surface"]["card"],
        "text": t["text"]["primary"],
    }

    overrides = dict(spec_overrides or {})
    derived = _derive_html_slots(base)
    slots = {}
    for slot in HTML_SLOT_NAMES:
        if slot == "card_title":
            continue
        slots[slot] = (
            overrides.get(slot)
            or derived.get(slot)
            or DEFAULT_HTML_SLOTS[slot]
        )
    slots["card_title"] = overrides.get("card_title") or slots["h2"]

    pptd_slots = _derive_pptd_slots(base)
    diagram_slots = _derive_diagram_slots(base)
    if name == "legacy_bluegreen":
        # F9：legacy 的 diagram 19 槽锚定重构前常量，保证零 diff
        diagram_slots = dict(DEFAULT_DIAGRAM_SLOTS)
    # 主题级图形盘覆盖（增补）：gov_red 等主题可登记 diagram_overrides，
    # 只覆盖本主题 disk 槽（共享盘常量不动，其余主题不受影响）
    ov = t.get("diagram_overrides")
    if ov:
        diagram_slots.update(ov)

    font_face = _single_font_from_stack(t.get("font_stack", DEFAULT_FONT))
    fonts = {"heading": font_face, "body": font_face}
    return Theme(style_name=name, html_colors=slots, fonts=fonts, base=base,
                 pptd_colors=pptd_slots, diagram_colors=diagram_slots)


def style_name_for_entry(entry):
    """兼容入口：老调用方传入的是 THEMES 条目/主题名；返回主题名。"""
    if isinstance(entry, str):
        return normalize_theme_name(entry)
    if isinstance(entry, dict):
        for name, candidate in THEMES.items():
            if candidate == entry:
                return name
    return DEFAULT_STYLE_NAME

def mix(hex_a, hex_b, t):
    """两色线性混合（t=0 → hex_a，t=1 → hex_b）。

    层色 tint（mix(层色, WHITE, 0.9)）、深态文字（mix(彩色, TEXT, 0.45)）
    等派生色的唯一入口——渲染器禁写 hex 字面量，派生一律走这里。
    """
    a, b = hex_a.lstrip("#"), hex_b.lstrip("#")
    ra, ga, ba = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    rb, gb, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return "#{:02X}{:02X}{:02X}".format(
        round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


# 中性结构色（风格无关，v1 硬编码灰阶收敛；slate 蓝灰系，去脏灰）
# 须在 _apply_theme() 首次调用前定义（LAYER_COLORS 第 5 层派生依赖 TEXT_STRONG）
WHITE = "#FFFFFF"            # 白色文字/填充
BLACK = "#000000"            # 深色派生端点（mix 调深用，如 primary_dark 档）
BORDER_STRONG = "#94A3B8"   # 泳道/容器边框（slate-400，带蓝的灰，去脏灰）
TEXT_STRONG = "#334155"     # 结构标签文字（slate-700，深蓝灰，去脏灰）


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

    # 分层循环色（layered / 4a 层标签、泳道道头用）
    # 第 5 层用 slate 深灰代替浅 GRAY：白字在 #A0AEC0 上对比度仅 2.3:1（verify 美学观察）
    LAYER_COLORS = [BLUE, GREEN, TEAL, PURPLE, mix(GRAY, TEXT_STRONG, 0.55)]

    # PPT 侧：Helvetica 在 Windows 不可用，用 Arial 兜底西文；中文取主题
    # font_stack 的 CJK 字面（gov_red 为 SimSun/仿宋）
    FONT_PPT = _theme.fonts.get("body", DEFAULT_FONT)

    # 共享 SVG 箭头 marker 定义（蓝 / 绿 两种，取色板常量不写字面量）+ 节点阴影 filter
    # v1.4 箭头加大：marker 10→13、线宽 2→2.4（原箭头在小图上缩成小尖角，读感弱）
    SVG_DEFS = f"""<defs>
<filter id="dgm-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#0F172A" flood-opacity="0.10"/></filter>
<marker id="dgm-arr" markerWidth="13" markerHeight="13" refX="11" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L0,8 L12,4 z" fill="{BLUE}"/></marker>
<marker id="dgm-arr-g" markerWidth="13" markerHeight="13" refX="11" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L0,8 L12,4 z" fill="{GREEN}"/></marker>
</defs>"""


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

# ======================================================================
# 视觉规范 v2.0 主题包（dev_plan_visual_v2_2026-07-25 §9，F2/F5/F9 冻结）
#
# 主题包：THEMES 管 v2 新增维度（页面构件/flow_rows/三态芯片/角色色板），
# 也是 resolve_theme 的唯一事实源。legacy_bluegreen = v1.2 冻结蓝绿原样
# 收编（F9：老 spec 显式 theme: legacy_bluegreen 视觉不变）；
# consulting_kpmg = 缺省主题（§9.2 tokens 基准，三态 2026-08-13 提饱和
# 去灰：lit/part 提饱和、gap 灰改红，旧 #D69E2E/#A0AEC0 仅 legacy 保留）。
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
        # §9.2 tokens 基准值（2026-07-25 定稿）；三态 2026-08-13 提饱和去灰；
        # R-4 色彩批（2026-09-07）：primary_mid 改 KPMG Medium Blue，accent 纯黄
        # 降饱和为金——金仅深底/描边用（白底 2.2:1 不可正文），并补深底变体槽
        "primary": "#00338D",
        "primary_dark": "#051C2C",
        "primary_mid": "#005EB8",
        "accent": "#F3C13A",  # 仅深底/描边用（白底 2.2:1 不可正文）
        # 深底变体（黑/深色底版，R-4 新增可选槽）：文字/强调/次级
        "on_dark": {"text": "#FFFFFF", "accent": "#1192E8", "muted": "#A8C0DC"},
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
    },
    "syzygit": {
        # 蓝海 SYZYGIT VI 规范（visual-craft-guide references/syzygit.md，
        # 2026-09-06 冻结，R-4 收编）：品牌蓝单色族 + 灰阶，白=内容页背景。
        # accent 不设金/橙（VI 无此角色，禁用橙红旧色 #BC450A/#C00000），
        # 由海军蓝承担强调；roles 五槽即 VI 图表色序
        #（品牌蓝→海军蓝→亮蓝→浅灰→深灰，禁 Office 默认色）
        "primary": "#0078FF",        # 品牌蓝：标题关键词/主按钮/图表主系列
        "primary_dark": "#0A238B",   # 深海军蓝：表头/次强调/深色罩层基调
        "primary_mid": "#4DA6FF",    # 亮蓝：七层架构 L7
        "accent": "#0A238B",         # VI 无 accent 角色 → 海军蓝承担强调
        "roles": {
            "biz": "#0078FF", "legal": "#0A238B", "fin": "#4DA6FF",
            "sys": "#B5B5B6", "ext": "#727171",
        },
        # VI 无三态专色：单色族内分层（蓝=有/进展，深灰=部分，浅灰=无）
        "tri": {
            "lit":  {"border": "#0078FF", "bg": "#E5F3FF", "text": "#0A238B"},
            "part": {"border": "#727171", "bg": "#F4F9FF", "text": "#3A3A3A"},
            "gap":  {"border": "#B5B5B6", "bg": "#F7F8FA", "text": "#727171"},
        },
        # 近黑/正文灰/导语灰；页脚深灰 #727171（roles.ext）/分隔浅灰 #B5B5B6
        "text": {"primary": "#1A1A1A", "secondary": "#3A3A3A",
                 "tertiary": "#595959"},
        # VI 衍生色：浅蓝卡片底 #F4F9FF / chip 底 #E5F3FF / 分隔 #B5B5B6
        "surface": {"bg_soft": "#F4F9FF", "bg_muted": "#E5F3FF",
                    "border": "#B5B5B6", "card": "#FFFFFF"},
        # 深色罩层 #0A1540（= DEFAULT_VEIL）→ 深海军蓝
        "hero": {"from": "#0A1540", "to": "#0A238B", "angle": 135},
        "groups": {"blue": "#E5F3FF", "teal": "#F4F9FF"},
        # 派生浅色：syzygit 无紫/红角色，给单色族浅灰对（bridge 桥接用）
        "purple_light": "#F2F2F2", "red_light": "#F5F6FA",
        "font_stack": FONT_STACK,
    },
    "weaver_blue": {
        # R-4 色彩批（2026-09-07，官网 DOM 提色 + logo 像素分析）：
        # 主蓝 #337AB7 / logo 蓝 #0050A0 / 官网深蓝 #22457F（hero 端点/表头）；
        # brand_green #00A040 图形/大元素用（白字 3.44:1 仅大元素），
        # 文本绿落 roles.fin=#007A31；金 accent 保留
        "primary": "#337AB7",
        "primary_dark": "#0050A0",
        "primary_mid": "#3D8AC8",
        "accent": "#E8A33D",
        "brand_green": "#00A040",  # logo 绿：图形/大元素用（可选槽）
        "navy_deep": "#22457F",    # 官网深蓝：hero 渐变端点/表头（可选槽）
        "roles": {
            "biz": "#337AB7", "legal": "#C00000", "fin": "#007A31",
            "sys": "#5B6B7E", "ext": "#8A6D3B",
        },
        "tri": {
            "lit":  {"border": "#059669", "bg": "#ECFDF5", "text": "#047857"},
            "part": {"border": "#EA580C", "bg": "#FFF7ED", "text": "#C2410C"},
            "gap":  {"border": "#C00000", "bg": "#FEF2F2", "text": "#991B1B"},
        },
        "text": {"primary": "#17222E", "secondary": "#455366",
                 "tertiary": "#6B7686"},
        "surface": {"bg_soft": "#F7F9FB", "bg_muted": "#EFF3F7",
                    "border": "#C9D4E0", "card": "#FFFFFF"},
        "hero": {"from": "#22457F", "to": "#337AB7", "angle": 135},
        "groups": {"blue": "#E7F2FB", "teal": "#EAF5F5"},
        "purple_light": "#F1EDFB", "red_light": "#FDEDED",
        "font_stack": FONT_STACK,
    },
    "gov_red": {
        # R-4 降饱和（2026-09-07）：全饱和 #C00000（S100% 刺眼）→ 枣红
        # #A63428（S~78%，政务大面积用色规范区间）；hero 渐变两端同步降饱和
        #（primary_dark = #A63428 向黑混合 0.3）；roles/tri 小面积点缀保留原红
        # R-4 增补（2026-09-07 用户裁决）：禁红配绿——roles.fin 青绿/三态
        # lit 翠绿在枣红语境撞色（红绿为互补色，边界色振不适），辅助色系
        # 整体换政务惯例色：金/赭石/藏蓝/暖米（来源见
        # docs/发版色彩批_预期diff_2026-09-07.md 增补节）。主色/hero 不动。
        "primary": "#A63428",
        "primary_dark": "#74241C",
        "primary_mid": "#D64545",
        "accent": "#B08D3E",
        "roles": {
            "biz": "#C00000", "legal": "#C00000", "fin": "#2F4B7C",
            "sys": "#5B6B7E", "ext": "#8A6D3B",
        },
        "tri": {
            "lit":  {"border": "#B08D3E", "bg": "#FBF5E7", "text": "#7A5A14"},
            "part": {"border": "#EA580C", "bg": "#FFF7ED", "text": "#C2410C"},
            "gap":  {"border": "#C00000", "bg": "#FEF2F2", "text": "#991B1B"},
        },
        "text": {"primary": "#1A1A1A", "secondary": "#4A4A4A",
                 "tertiary": "#727171"},
        "surface": {"bg_soft": "#FDF9F6", "bg_muted": "#F7F0EC",
                    "border": "#E3D5CE", "card": "#FFFFFF"},
        "hero": {"from": "#74241C", "to": "#A63428", "angle": 135},
        # 键名归位（R-4）：原 blue/teal 槽错填暖粉/暖灰，键名改与实际色相符；
        # 消费端（tokens CSS/pptd/flow_rows）已泛化为按 groups 键名分发。
        # 增补：gray 值由冷灰 #F0F5F5（泛青）改暖米灰，与暖面/金赭系一致
        "groups": {"red": "#F7EFEF", "gray": "#F5F0EA"},
        "purple_light": "#F2EDE6", "red_light": "#FDEDED",
        # 主题级图形盘覆盖（增补，可选槽 .get 发射）：共享盘绿/青族在枣红
        # 语境必现（timeline 末段绿条/LAYER_COLORS 分层），绿族→深赭金
        # #8A6116、青族→藏蓝 #2F4B7C（同 roles.fin）；其余主题共享盘不动
        "diagram_overrides": {"green": "#8A6116", "green_light": "#F7F0DC",
                              "teal": "#2F4B7C", "teal_light": "#EDF1F7"},
        # qa_block 语义槽覆写（C-E4）：官方绿默认值在枣红语境撞红绿互补
        # （同上文禁红配绿裁决），改用本主题赭金对（tri.lit 同族）
        "qa": {"text": "#7A5A14", "bg": "#FBF5E7"},
        "font_stack": '"SimSun", "仿宋", "Microsoft YaHei", serif',
    },
}

DEFAULT_V2_THEME = "consulting_kpmg"  # Step 2：缺省主题改为 consulting_kpmg

# 模块装载：默认主题 consulting_kpmg
_apply_theme()
_ACTIVE_STYLE = DEFAULT_STYLE_NAME


def get_theme(name=None):
    """取 v2 主题包 tokens。None/空 → consulting_kpmg；非法名 raise。

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
    # 行级分组底色：键名即分组名（gov_red 归位为 red/gray），按主题实际键分发
    for gname, gcolor in groups.items():
        lines.append(f"  --t-group-{gname}:{gcolor};")
    # 派生浅色（旧 diagram 变量桥接用；THEMES 显式登记，禁 hex 硬编码）
    lines.append(f"  --t-purple-light:{t.get('purple_light', '#F3F0F9')};"
                 f" --t-red-light:{t.get('red_light', '#FDEDEC')};")
    # 可选槽（R-4）：深底变体（kpmg）/品牌绿与官网深蓝（weaver），
    # 经 .get 发射——未登记的主题零输出零影响
    on_dark = t.get("on_dark")
    if on_dark:
        lines.append(f"  --t-ondark-text:{on_dark['text']};"
                     f" --t-ondark-accent:{on_dark['accent']};"
                     f" --t-ondark-muted:{on_dark['muted']};")
    if t.get("brand_green"):
        lines.append(f"  --t-brand-green:{t['brand_green']};")
    if t.get("navy_deep"):
        lines.append(f"  --t-navy-deep:{t['navy_deep']};")
    # 派生透明度变量（hex8）：section-tag 底 8%、行标签边 15%、hl-yellow 荧光 55%
    lines.append(f"  --t-primary-a08:{t['primary']}14; --t-primary-a15:{t['primary']}26;"
                 f" --t-accent-a55:{t['accent']}8C;")
    # qa_block 语义槽（C-E4 官方绿；主题可选 "qa" 覆写，gov_red 金系）
    qa = t.get("qa") or DEFAULT_QA_SLOTS
    lines.append(f"  --t-qa-text:{qa['text']}; --t-qa-bg:{qa['bg']};")
    lines.append("}")
    return "\n".join(lines)


def bridge_css(name=None):
    """旧 diagram 变量桥接（统一色板，独立块保 --t- 命名空间隔离）。

    既有 diagram 渲染器引用 --blue/--green/--orange 等 19 槽变量
    （css_variables 注入），v2 主题场景下映射到 --t-* 变量，让 diagram 与
    页面构件共用同一主题色板（legacy 等值零视觉变化，consulting_kpmg
    全链路 KPMG 深蓝+黄）。独立函数：不污染 theme_tokens_css 的命名空间
    （测试断言 tokens 块零旧变量），由 render_html / 编辑器注入器拼接。

    name（R-4）：groups 键名归位后（gov_red = red/gray），浅底桥接变量
    回退指向该主题实际的分组键，保证旧 diagram 浅色填充不断链。
    """
    blue_grp, teal_grp = "blue", "teal"
    if name:
        gkeys = list(get_theme(name)["groups"])
        if "blue" not in gkeys and gkeys:
            blue_grp = gkeys[0]
        if "teal" not in gkeys and len(gkeys) > 1:
            teal_grp = gkeys[1]
    return f"""/* 旧 diagram 变量桥接 -> v2 主题（--t- 变量） */
:root {{
  --blue: var(--t-primary); --blue-mid: var(--t-primary-mid); --blue-light: var(--t-group-{blue_grp});
  --green: var(--t-lit-border); --green-light: var(--t-lit-bg);
  --teal: var(--t-role-fin); --teal-light: var(--t-group-{teal_grp});
  --purple: var(--t-role-sys); --purple-light: var(--t-purple-light);
  --gray: var(--t-gap-border);
  --orange: var(--t-accent); --orange-light: var(--t-part-bg);
  --red: var(--t-role-legal); --red-light: var(--t-red-light);
  --bg: var(--t-bg-soft); --card: var(--t-card);
  --text: var(--t-text-primary); --text-sub: var(--t-text-secondary);
  --border: var(--t-border);
}}"""


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
    }
    # 行级分组底色：键名即分组名（gov_red = red/gray），扁平化为 group_<名>
    for gname, gcolor in t["groups"].items():
        colors[f"group_{gname}"] = gcolor
    # 可选槽（R-4，.get 发射）：深底变体 / 品牌绿 / 官网深蓝
    on_dark = t.get("on_dark")
    if on_dark:
        colors["on_dark_text"] = on_dark["text"]
        colors["on_dark_accent"] = on_dark["accent"]
        colors["on_dark_muted"] = on_dark["muted"]
    if t.get("brand_green"):
        colors["brand_green"] = t["brand_green"]
    if t.get("navy_deep"):
        colors["navy_deep"] = t["navy_deep"]
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
    # qa_block 语义槽（C-E4 官方绿；主题可选 "qa" 覆写，与 CSS 同源同值）
    qa = t.get("qa") or DEFAULT_QA_SLOTS
    colors["qa_text"] = qa["text"]
    colors["qa_bg"] = qa["bg"]
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
