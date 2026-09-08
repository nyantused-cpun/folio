# -*- coding: utf-8 -*-
"""chart 类渲染器（第 36-37 种，v1.5 新增 diagram_type=chart）：数据图表族。

补信息化咨询"价值/收益论证"叙事硬缺口（审计报告 §3.1）。设计纪律
（kimi-slides 图表去默认细则 + Deckary MBB 图表规范，审计报告 §5.2）：
- 删纵向网格线，至多留极浅横线；
- 数据标签直接贴图形旁（不另附图例表），多系列才给图例；
- 轴标签带单位（unit 字段），来源行（source 字段）落图正下方；
- 系列色走主题色板，≤5 个系列（Deckary 上限）；
- 无 3D、无渐变、无装饰（铁律）。

spec：
  bar: {categories: [], series: [{name, values: []}], unit?, source?}
       多系列 = 分组柱；values 需非负（负值叙事请用 waterfall）
  waterfall: {steps: [{label, value, kind?}], unit?, source?}
       kind: delta（缺省，增减量）| total（立柱，从 0 起）；delta 可正可负

unit 落在 y 轴顶端（轴标签带单位纪律）；source 不在图内自绘——复用分发器
exhibit 图框的来源行机制（_wrap_exhibit，全 diagram 同源），避免双重来源行。

PPT 端（批二已实施，F7 决策路线）：bar/waterfall 接 _pptd_convert 原生
graphicFrame chart（双击可改数据）；其余 subtype render_pptd 显式抛
NotImplementedError 走分发器降级占位。
"""

from .. import theme
from ..theme import _esc

# 系列色板：主系列 → 次系列顺序取色（主题同源，不写死字面量）
def _series_colors():
    return [theme.BLUE, theme.GREEN, theme.ORANGE, theme.PURPLE, theme.TEAL]


# 几何常量（viewBox 1200 系）
_VB_W = 1200.0
_ML, _MR, _MT, _MB = 70.0, 24.0, 30.0, 60.0   # 绘图区四边距
_PLOT_H = 340.0


def _nice_max(v):
    """刻度上限取整（1/2/5×10^n 步进），保证 4 档刻度值为整数或一位小数。"""
    if v <= 0:
        return 1.0
    import math
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= mag * m:
            return mag * m
    return mag * 10


def _fmt_num(v):
    """刻度/标签数字：整数去小数点，否则保留一位。"""
    return str(int(v)) if float(v) == int(v) else f"{v:.1f}"


def _y_axis(parts, maxv, minv, unit):
    """横向浅网格 + y 轴刻度（去默认：只留极浅横线，无纵网格无轴框）。

    刻度带覆盖 [minv, maxv]（bar 负值柱自基线向下延伸时网格同步下探）；
    minv=0 时网格位置/刻度值与历史 0 起点逐像素一致。
    """
    span = maxv - minv
    plot_bot = _MT + _PLOT_H
    for i in range(5):
        gy = plot_bot - _PLOT_H * i / 4
        val = minv + span * i / 4
        parts.append(
            f'<line x1="{_ML}" y1="{gy}" x2="{_VB_W - _MR}" y2="{gy}" '
            f'stroke="{theme.BORDER}" stroke-width="{1.2 if i == 0 else 0.6}"'
            + ('' if i == 0 else ' stroke-opacity="0.55"') + '/>')
        parts.append(
            f'<text x="{_ML - 8}" y="{gy + 4}" font-size="11" '
            f'fill="{theme.TEXT_SUB}" text-anchor="end">{_fmt_num(val)}</text>')
    if unit:
        parts.append(
            f'<text x="{_ML - 8}" y="{_MT - 12}" font-size="11" '
            f'fill="{theme.TEXT_SUB}" text-anchor="end" '
            f'data-editable="true">单位：{_esc(unit)}</text>')


def _bar_html(elem):
    """分组柱状图（bar）：类别 × 系列，值标签贴柱顶。

    负值翻转渲染（abs 高度 + 基线偏移，矩形自基线向下）：此前负高 SVG rect
    静默不渲染（审查 P3）；刻度带同步下探到最小负值，正路径几何逐像素不变。
    """
    cats = [str(c) for c in elem.get("categories", []) or []]
    series = [{"name": str(s.get("name", "")),
               "values": [float(v) for v in (s.get("values", []) or [])]}
              for s in (elem.get("series", []) or []) if isinstance(s, dict)]
    unit = str(elem.get("unit", "") or "")
    colors = _series_colors()
    vals = [v for s in series for v in s["values"]]
    maxv = _nice_max(max((abs(v) for v in vals), default=1.0))
    minv = min(0.0, min(vals, default=0.0))
    span = maxv - minv
    py1 = _MT + _PLOT_H * maxv / span        # 基线（值 0 的 y，负值区让出下半）
    plot_bot = _MT + _PLOT_H
    vb_h = plot_bot + _MB
    parts = [f'<svg class="dg" viewBox="0 0 {int(_VB_W)} {int(vb_h)}" '
             f'xmlns="http://www.w3.org/2000/svg">']
    _y_axis(parts, maxv, minv, unit)
    n_c, n_s = len(cats), len(series)
    group_w = (_VB_W - _ML - _MR) / max(1, n_c)
    bar_w = min(48.0, group_w * 0.62 / max(1, n_s))
    for ci, cat in enumerate(cats):
        gx = _ML + ci * group_w + group_w / 2
        for si, s in enumerate(series):
            v = s["values"][ci] if ci < len(s["values"]) else 0.0
            # 带符号柱高按 span 缩放（minv=0 时 span==maxv，正路径逐像素不变）
            bh = _PLOT_H * v / span
            bx = gx - bar_w * n_s / 2 + si * bar_w
            ry = py1 - bh if v >= 0 else py1
            parts.append(
                f'<rect x="{bx:.1f}" y="{ry:.1f}" width="{bar_w - 3:.1f}" '
                f'height="{abs(bh):.1f}" fill="{colors[si % len(colors)]}"/>')
            # 数据标签贴柱顶（负值贴柱底下方），关键点强调留给 spec 文案
            ly = (py1 - bh - 5) if v >= 0 else (py1 - bh + 16)
            parts.append(
                f'<text x="{bx + (bar_w - 3) / 2:.1f}" y="{ly:.1f}" '
                f'font-size="11" font-weight="600" text-anchor="middle" '
                f'fill="{colors[si % len(colors)]}">{_fmt_num(v)}</text>')
        parts.append(
            f'<text x="{gx:.1f}" y="{plot_bot + 20}" font-size="12" '
            f'fill="{theme.TEXT}" text-anchor="middle" '
            f'data-editable="true">{_esc(cat)}</text>')
    if n_s > 1:
        # 多系列图例（顺序与数据一致，右上）
        lx = _VB_W - _MR
        for si in range(n_s - 1, -1, -1):
            name = series[si]["name"]
            tw = len(name) * 12 + 20
            lx -= tw
            parts.append(
                f'<rect x="{lx}" y="{_MT - 18}" width="10" height="10" '
                f'fill="{colors[si % len(colors)]}"/>')
            parts.append(
                f'<text x="{lx + 14}" y="{_MT - 9}" font-size="11" '
                f'fill="{theme.TEXT_SUB}">{_esc(name)}</text>')
            lx -= 16
    parts.append("</svg>")
    return "\n".join(parts)


def _waterfall_html(elem):
    """瀑布图/收益桥（waterfall）：total 立柱从 0 起，delta 浮动增减，
    正=绿 负=红 立柱=蓝；柱间水平虚线桥接（麦肯锡"解释差异"默认图）。"""
    steps = [{"label": str(s.get("label", "")),
              "value": float(s.get("value", 0) or 0),
              "kind": str(s.get("kind", "delta"))}
             for s in (elem.get("steps", []) or []) if isinstance(s, dict)]
    unit = str(elem.get("unit", "") or "")
    # 预排：累计值与每根柱的 (底, 顶)
    bars = []
    running = 0.0
    for s in steps:
        if s["kind"] == "total":
            lo, hi = 0.0, s["value"]
            running = s["value"]
        else:
            lo, hi = running, running + s["value"]
            running = hi
        bars.append((s, min(lo, hi), max(lo, hi)))
    maxv = _nice_max(max((b[2] for b in bars), default=1.0))
    minv = min(0.0, min((b[1] for b in bars), default=0.0))
    span = maxv - minv
    plot_top = _MT
    vb_h = _MT + _PLOT_H + _MB

    def _y(val):
        return plot_top + _PLOT_H * (maxv - val) / span

    parts = [f'<svg class="dg" viewBox="0 0 {int(_VB_W)} {int(vb_h)}" '
             f'xmlns="http://www.w3.org/2000/svg">']
    # 横网格（相对 minv 起 4 档）
    for i in range(5):
        val = minv + span * i / 4
        gy = _y(val)
        parts.append(
            f'<line x1="{_ML}" y1="{gy:.1f}" x2="{_VB_W - _MR}" y2="{gy:.1f}" '
            f'stroke="{theme.BORDER}" stroke-width="0.6" stroke-opacity="0.55"/>')
        parts.append(
            f'<text x="{_ML - 8}" y="{gy + 4:.1f}" font-size="11" '
            f'fill="{theme.TEXT_SUB}" text-anchor="end">{_fmt_num(val)}</text>')
    if unit:
        parts.append(
            f'<text x="{_ML - 8}" y="{_MT - 12}" font-size="11" '
            f'fill="{theme.TEXT_SUB}" text-anchor="end" '
            f'data-editable="true">单位：{_esc(unit)}</text>')
    n = len(bars)
    slot_w = (_VB_W - _ML - _MR) / max(1, n)
    bar_w = min(72.0, slot_w * 0.62)
    for i, (s, lo, hi) in enumerate(bars):
        cx = _ML + i * slot_w + slot_w / 2
        color = (theme.BLUE if s["kind"] == "total"
                 else (theme.GREEN if s["value"] >= 0 else theme.RED))
        parts.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{_y(hi):.1f}" width="{bar_w:.1f}" '
            f'height="{max(_y(lo) - _y(hi), 1.5):.1f}" fill="{color}"/>')
        # 值标签：delta 带正负号贴柱顶/底，total 贴柱顶
        if s["kind"] == "total":
            lbl, ly = _fmt_num(s["value"]), _y(hi) - 6
        else:
            lbl = f'{"+" if s["value"] >= 0 else ""}{_fmt_num(s["value"])}'
            ly = (_y(hi) - 6) if s["value"] >= 0 else (_y(lo) + 16)
        parts.append(
            f'<text x="{cx:.1f}" y="{ly:.1f}" font-size="12" font-weight="700" '
            f'fill="{color}" text-anchor="middle">{_esc(lbl)}</text>')
        # 桥接虚线：本柱结束水位 → 下一柱
        if i < n - 1:
            # 本柱结束水位：total 取原始值（第二循环解包的 lo/hi 已按 min/max
            # 排序，负 total 的 hi=0 会把桥接线错画在 0 而非实际水位，审查 P3）；
            # delta 正=柱顶、负=柱底
            end_level = (s["value"] if s["kind"] == "total"
                         else (hi if s["value"] >= 0 else lo))
            nx = _ML + (i + 1) * slot_w + slot_w / 2
            parts.append(
                f'<line x1="{cx + bar_w / 2:.1f}" y1="{_y(end_level):.1f}" '
                f'x2="{nx - bar_w / 2:.1f}" y2="{_y(end_level):.1f}" '
                f'stroke="{theme.TEXT_SUB}" stroke-width="1" '
                f'stroke-dasharray="3,3" stroke-opacity="0.7"/>')
        parts.append(
            f'<text x="{cx:.1f}" y="{_MT + _PLOT_H + 20}" font-size="12" '
            f'fill="{theme.TEXT}" text-anchor="middle" '
            f'data-editable="true">{_esc(s["label"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(elem):
    st = elem.get("subtype", "")
    body = {"bar": _bar_html, "waterfall": _waterfall_html}.get(st)
    if not body:
        raise NotImplementedError(f"chart/{st} 未实现")
    return theme.section_open(elem) + "\n" + body(elem) + "\n" + theme.SECTION_CLOSE


def render_pptd(elem, x, y, w):
    """chart 族 PPT 端（批二，F7 拍板执行）：返回 (elements, h)，
    elements 含 chart 数据元素，convert 端 `_render_chart` 接原生
    graphicFrame（双击可改数据）。bar=分组柱（COLUMN_CLUSTERED）；
    waterfall=栈式 emulate（base 隐形 + 增/减/total 四系列，
    convert 端 COLUMN_STACKED，见 _waterfall_chart_elem）。"""
    st = elem.get("subtype")
    if st == "bar":
        chart_el = _bar_chart_elem(elem, x, y, w)
        return [chart_el], chart_el["bounds"][3]
    if st == "waterfall":
        chart_el = _waterfall_chart_elem(elem, x, y, w)
        return [chart_el], chart_el["bounds"][3]
    raise NotImplementedError(
        f"chart/{st} PPT 端未实现（F7 原生 chart 路线），"
        f"本次降级为占位块")


def _bar_chart_elem(elem, x, y, w):
    """bar → {elementType: chart, chartKind: bar} 数据元素。

    categories/series 契约与 _bar_html 同源（类别 × 系列 + 可选 unit）。"""
    cats = [str(c) for c in elem.get("categories", []) or []]
    series = [{"name": str(s.get("name", "")),
               "values": [float(v) for v in (s.get("values", []) or [])]}
              for s in (elem.get("series", []) or []) if isinstance(s, dict)]
    return {
        "elementId": elem.get("id") or "chart-bar",
        "elementType": "chart",
        "bounds": [int(x), int(y), int(w), 320],
        "chartKind": "bar",
        "categories": cats,
        "series": series,
        "unit": str(elem.get("unit", "") or ""),
    }


def _waterfall_chart_elem(elem, x, y, w):
    """waterfall → {elementType: chart, chartKind: waterfall} 数据元素。

    python-pptx 1.0.2 无 WATERFALL 枚举（Office 2016+ 类型未收录），
    按瀑布图惯例栈式 emulate：四系列——base（隐形托底）+ increase
    （增，绿）+ decrease（减，红）+ total（立柱，蓝），convert 端
    COLUMN_STACKED 渲染。累计预排与 _waterfall_html 逐柱同源
    （total 从 0 起、delta 浮动增减、桥接水位=min/max 语义一致）。
    """
    steps = [{"label": str(s.get("label", "")),
              "value": float(s.get("value", 0) or 0),
              "kind": str(s.get("kind", "delta"))}
             for s in (elem.get("steps", []) or []) if isinstance(s, dict)]
    base, increase, decrease, total = [], [], [], []
    running = 0.0
    for s in steps:
        if s["kind"] == "total":
            base.append(0.0)
            increase.append(0.0)
            decrease.append(0.0)
            total.append(s["value"])
            running = s["value"]
        else:
            base.append(min(running, running + s["value"]))
            if s["value"] >= 0:
                increase.append(s["value"])
                decrease.append(0.0)
            else:
                increase.append(0.0)
                decrease.append(-s["value"])
            total.append(0.0)
            running += s["value"]
    return {
        "elementId": elem.get("id") or "chart-waterfall",
        "elementType": "chart",
        "bounds": [int(x), int(y), int(w), 320],
        "chartKind": "waterfall",
        "categories": [s["label"] for s in steps],
        "waterfall": {"base": base, "increase": increase,
                      "decrease": decrease, "total": total},
        "colors": {"increase": theme.GREEN, "decrease": theme.RED,
                   "total": theme.BLUE},
        "unit": str(elem.get("unit", "") or ""),
    }
