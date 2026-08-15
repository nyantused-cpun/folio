# -*- coding: utf-8 -*-
"""样式单一源：styles.json 注册表 + 槽位派生 + spec 覆盖。三端共用。

设计见 docs/refactor_plan_spec_pipeline_2026-07-20.md §七 2.1/2.2/2.3。

HTML 渲染需要 9 个颜色槽（heading/primary/h2/subtitle/muted/
table_header_bg/border/card_bg/card_title），pptd 需要 11 槽
（PPTD_SLOT_NAMES），diagram 需要 19 槽（DIAGRAM_SLOT_NAMES）；
styles.json 每种风格只定义 5 基色（primary/secondary/accent/
background/text）+ fonts。本模块把"5 基色 -> 各端槽位"的推导收敛为单点。
HTML 槽解析优先级（高 -> 低）：

1. spec_overrides（spec.theme.colors 逐槽覆盖，保持历史行为）
2. styles.json 该风格的显式 "html" 槽位块（curated 覆盖）
3. 派生函数 _derive_html_slots（从 5 基色推导）
4. DEFAULT_HTML_SLOTS（重构前 HTML 端的硬编码 9 槽，兜底）

pptd/diagram 槽不接 spec_overrides（保持重构前无覆盖路径的行为）：
enterprise 锚定 DEFAULT_PPTD_SLOTS / DEFAULT_DIAGRAM_SLOTS（基线零 diff
保证），其余风格走 _derive_pptd_slots / _derive_diagram_slots 派生。

quote 链路消费 base/fonts（见 _quote_html._load_quote_style）。

注（§七 2.3 遗留）：DOCX 端字体由 spec.format.body_font 驱动（缺省
仿宋_GB2312，投标公文惯例，见 _renderer._apply_docx_format），与
styles.json fonts.body（Microsoft YaHei）是不同字符串来源。是否把 DOCX
字体也切到 fonts.body 留待用户决定；本模块暂不接管 DOCX 字体，
避免 document.xml 无意义 diff。
"""
import json
from typing import Dict, NamedTuple

from _paths import STYLES_PATH

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

DEFAULT_STYLE_NAME = "enterprise"
DEFAULT_FONT = "Microsoft YaHei"

# pptd 端 11 个颜色槽（_pptd_gen._build_theme 消费，顺序即主 pptd YAML 键序）
PPTD_SLOT_NAMES = (
    "primary", "navy", "ink", "body", "lead", "gray",
    "ltgray", "chip", "card", "veil", "hairline",
)

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
    "veil": "#0A1540",
    "hairline": "#D8E2EE",
}

# diagram 端 19 个颜色槽（_renderer/diagram/theme.py 消费，
# 键名 = 重构前常量名小写）
DIAGRAM_SLOT_NAMES = (
    "blue", "blue_mid", "blue_light", "green", "green_light",
    "teal", "teal_light", "purple", "purple_light", "gray",
    "orange", "orange_light", "red", "red_light",
    "bg", "card", "text", "text_sub", "border",
)

# 重构前 diagram/theme.py 的 19 常量原值（arms_v5 基线零 diff 锚定）
DEFAULT_DIAGRAM_SLOTS = {
    "blue": "#1B5E8A",
    "blue_mid": "#4A7FA5",
    "blue_light": "#EDF2F7",
    "green": "#2F7D5F",
    "green_light": "#F0FAF5",
    "teal": "#2E8B8B",
    "teal_light": "#EDF6F6",
    "purple": "#7B68AE",
    "purple_light": "#F3F0F9",
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
    base: Dict[str, str]           # styles.json 的 5 基色（quote 链路消费）
    pptd_colors: Dict[str, str]    # 11 槽，见 PPTD_SLOT_NAMES
    diagram_colors: Dict[str, str]  # 19 槽，见 DIAGRAM_SLOT_NAMES


def _load_styles():
    """读取 styles.json 注册表；文件缺失/损坏时返回空 dict（走默认兜底）。"""
    try:
        with open(STYLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _normalize_font(value, default=DEFAULT_FONT):
    """fonts 值兼容纯字符串与历史 dict 形态（{"name": "..."}）。"""
    if isinstance(value, dict):
        return value.get("name", default)
    return value or default


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
    """从风格 5 基色推导 pptd 11 槽（非 enterprise 风格使用）。

    推导规则：primary/navy 跟随品牌主/辅色；文字阶梯 ink->body->lead
    ->gray->ltgray 为 base.text 向白调亮五档（0/0.14/0.275/0.38/0.68，
    节奏对齐原硬编码 #1A1A1A->#3A3A3A->#595959->#727171->#B5B5B6）；
    card 用 base.background，chip/hairline 为其调深两档（0.06/0.12）；
    veil 为 background 调深 0.93 的暗场色（封面遮罩用）。
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
    """解析主题。优先级：spec 覆盖 > 显式 html 块 > 派生 > 默认。

    style_name 为空或未知时回退 enterprise（与 _resolve_style 一致）。
    spec_overrides 即 spec.theme.colors（逐槽覆盖，可为 None），只作用于
    HTML 9 槽；pptd/diagram 槽保持重构前行为不接覆盖——enterprise 锚定
    DEFAULT 表，其余风格从 5 基色派生（§七 2.2）。
    """
    styles = _load_styles()
    name = style_name or DEFAULT_STYLE_NAME
    entry = styles.get(name) or styles.get(DEFAULT_STYLE_NAME) or {}
    if name not in styles and DEFAULT_STYLE_NAME in styles:
        name = DEFAULT_STYLE_NAME

    base = dict(entry.get("colors") or {})
    explicit = entry.get("html") or {}
    derived = _derive_html_slots(base) if base else {}
    overrides = dict(spec_overrides or {})

    slots = {}
    for slot in HTML_SLOT_NAMES:
        if slot == "card_title":
            continue  # 依赖已解析的 h2，在循环后单独处理
        slots[slot] = (
            overrides.get(slot)
            or explicit.get(slot)
            or derived.get(slot)
            or DEFAULT_HTML_SLOTS[slot]
        )
    # 历史行为：card_title 未被覆盖/显式定义时跟随 h2
    # （派生与默认规则下 card_title 与 h2 本就同色，行为等价）
    slots["card_title"] = (
        overrides.get("card_title")
        or explicit.get("card_title")
        or slots["h2"]
    )

    # pptd/diagram 槽：enterprise（含回退）锚定 DEFAULT 表保证基线零 diff，
    # 其余风格派生；base 缺失（如 styles.json 损坏）同样落 DEFAULT 兜底
    if name == DEFAULT_STYLE_NAME or not base:
        pptd_slots = dict(DEFAULT_PPTD_SLOTS)
        diagram_slots = dict(DEFAULT_DIAGRAM_SLOTS)
    else:
        pptd_slots = _derive_pptd_slots(base)
        diagram_slots = _derive_diagram_slots(base)

    fonts_raw = entry.get("fonts") or {}
    fonts = {
        "heading": _normalize_font(fonts_raw.get("heading")),
        "body": _normalize_font(fonts_raw.get("body")),
    }
    return Theme(style_name=name, html_colors=slots, fonts=fonts, base=base,
                 pptd_colors=pptd_slots, diagram_colors=diagram_slots)


def style_name_for_entry(entry):
    """反查 styles.json entry 的风格键名；未命中（如 styles.json 缺失时的
    {}）回退 enterprise。

    _renderer._resolve_style 只返回 entry dict 不返回键名，pptd 链路
    （_pptd_gen._build_theme）需要键名才能调 resolve_theme；按 entry
    全等匹配，注册表有重复 entry 时取先声明者。
    """
    styles = _load_styles()
    entry = entry or {}
    for name, candidate in styles.items():
        if candidate == entry:
            return name
    return DEFAULT_STYLE_NAME
