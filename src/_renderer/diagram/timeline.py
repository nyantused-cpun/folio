# -*- coding: utf-8 -*-
"""timeline 类渲染器：horizontal / vertical（2 种全部实现）。

HTML：阶段卡横排 + chevron 箭头串联（卡顶 4px 色条）。
pptd：阶段卡 roundRect + chevron 原生形状连接。

spec：milestones: [{label, date, desc}]
"""

from . import theme
from .theme import _esc
from . import pptd_emit as pe


def _vertical_html(elem):
    ms = elem.get("milestones", []) or []
    parts = ['<div style="position:relative;padding-left:28px;">',
             f'<div style="position:absolute;left:8px;top:6px;bottom:6px;width:2px;background:{theme.BLUE_MID};"></div>']
    n = len(ms)
    for i, m in enumerate(ms):
        last = i == n - 1
        c = theme.GREEN if last else theme.BLUE
        parts.append(
            f'<div style="position:relative;margin-bottom:16px;">'
            f'<div style="position:absolute;left:-26px;top:6px;width:12px;height:12px;border-radius:50%;'
            f'background:{c};border:2px solid {theme.WHITE};box-shadow:0 0 0 2px {theme.BLUE_MID};"></div>'
            f'<div style="background:{theme.CARD};border:1px solid {theme.BORDER};border-left:4px solid {c};border-radius:8px;padding:12px 16px;">'
            f'<b style="color:{c};" data-editable="true">{_esc(m.get("label", ""))}</b>'
            f'<span style="font-size:12px;color:{theme.TEXT_SUB};" data-editable="true"> · {_esc(m.get("date", ""))}</span>'
            f'<div style="font-size:13px;margin-top:4px;" data-editable="true">{_esc(m.get("desc", ""))}</div>'
            f'</div></div>')
    parts.append('</div>')
    return "\n".join(parts)


def _mg_tones():
    """module_gantt 域色（左标签块与 chip 同源实底）。"""
    return {"blue": theme.BLUE, "green": theme.GREEN, "purple": theme.PURPLE,
            "teal": theme.TEAL, "orange": theme.ORANGE}


def _mg_geometry(elem):
    """module_gantt 布局几何（HTML/pptd 共用，viewBox 1200 宽坐标系）。

    结构：markers 行（红三角+上线点）→ 季度表头（深色条）→ 域行
    （左标签块 + 编号 chip 按列落格堆叠）。
    """
    cols = elem.get("columns", []) or []
    groups = elem.get("groups", []) or []
    markers = elem.get("markers", []) or []
    label_w = 190.0
    gx0, gx1 = 210.0, 1190.0
    n = max(1, len(cols))
    col_w = (gx1 - gx0) / n
    markers_h = 42.0 if markers else 0.0
    header_h = 32.0
    chip_h, chip_gap = 24.0, 6.0
    pad_t, pad_b, row_gap = 12.0, 10.0, 8.0
    y = markers_h + header_h
    rows = []
    for g in groups:
        stacks = {}
        for m in g.get("modules", []) or []:
            c = int(m.get("col", 0))
            if 0 <= c < n:
                stacks.setdefault(c, []).append(str(m.get("label", "")))
        max_stack = max((len(v) for v in stacks.values()), default=0)
        rh = pad_t + max(1, max_stack) * (chip_h + chip_gap) - chip_gap + pad_b
        rows.append({"spec": g, "stacks": stacks, "y": y, "h": rh})
        y += rh + row_gap
    H = y - row_gap + 4
    return {"W": 1200.0, "H": H, "columns": [str(c) for c in cols],
            "markers": markers, "label_w": label_w, "gx0": gx0, "col_w": col_w,
            "n": n, "markers_h": markers_h, "header_h": header_h,
            "chip_h": chip_h, "chip_gap": chip_gap, "pad_t": pad_t, "rows": rows}


def _module_gantt_html(elem):
    """module_gantt HTML：绝对定位容器（dg-body 允许横向滚动）。"""
    g = _mg_geometry(elem)
    tones = _mg_tones()
    W, H = g["W"], g["H"]
    gx0, col_w, n = g["gx0"], g["col_w"], g["n"]
    parts = [f'<div style="position:relative;width:{W:.0f}px;height:{H:.0f}px;font-family:{theme.FONT_STACK};">']
    # markers：红三角 + 上线点标签
    for _i, m in enumerate(g["markers"]):
        c = int(m.get("col", 0))
        if not (0 <= c < n):
            continue
        mx = gx0 + c * col_w + 4
        parts.append(
            f'<div style="position:absolute;left:{mx:.0f}px;top:2px;color:{theme.RED};font-size:12px;line-height:1;">▼</div>'
            f'<div style="position:absolute;left:{mx + 16:.0f}px;top:0;font-size:11px;font-weight:700;color:{theme.TEXT};" data-editable="true">{_esc(m.get("label", ""))}</div>')
        if m.get("note"):
            parts.append(f'<div style="position:absolute;left:{mx + 16:.0f}px;top:16px;font-size:10px;color:{theme.TEXT_SUB};" data-editable="true">{_esc(m["note"])}</div>')
    # 季度表头：深色条
    hy = g["markers_h"]
    for c, name in enumerate(g["columns"]):
        hx = gx0 + c * col_w + 2
        parts.append(
            f'<div style="position:absolute;left:{hx:.0f}px;top:{hy:.0f}px;width:{col_w - 4:.0f}px;height:{g["header_h"]:.0f}px;'
            f'background:{theme.TEXT_SUB};color:{theme.WHITE};font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;" data-editable="true">{_esc(name)}</div>')
    # 域行：左标签块 + 编号 chip 落格
    for r in g["rows"]:
        gspec, ry, rh = r["spec"], r["y"], r["h"]
        tone = tones.get(gspec.get("tone", "blue"), theme.BLUE)
        name_html = f'<div style="font-size:13px;font-weight:700;line-height:1.35;" data-editable="true">{_esc(gspec.get("name", ""))}</div>'
        if gspec.get("sub"):
            name_html += f'<div style="font-size:10px;opacity:0.85;margin-top:4px;line-height:1.4;" data-editable="true">{_esc(gspec["sub"])}</div>'
        parts.append(
            f'<div style="position:absolute;left:0;top:{ry:.0f}px;width:{g["label_w"]:.0f}px;height:{rh:.0f}px;'
            f'background:{tone};color:{theme.WHITE};border-radius:10px;padding:12px;box-sizing:border-box;">{name_html}</div>')
        for c, labels in r["stacks"].items():
            for k, label in enumerate(labels):
                cxp = gx0 + c * col_w + 8
                cyp = ry + g["pad_t"] + k * (g["chip_h"] + g["chip_gap"])
                parts.append(
                    f'<div style="position:absolute;left:{cxp:.0f}px;top:{cyp:.0f}px;width:{col_w - 16:.0f}px;height:{g["chip_h"]:.0f}px;'
                    f'background:{tone};color:{theme.WHITE};border-radius:6px;font-size:11px;font-weight:600;line-height:{g["chip_h"]:.0f}px;'
                    f'padding:0 10px;box-sizing:border-box;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" data-editable="true">{_esc(label)}</div>')
    parts.append('</div>')
    return "\n".join(parts)


def _vertical_pptd(elem, x, y, w):
    ms = elem.get("milestones", []) or []
    sc = pe.PptdScaler(x, y, w)
    n = len(ms)
    card_h, gap = 74.0, 14.0
    elems = []
    # 竖轴
    axis_x = sc.px(8)
    total = n * (card_h + gap) - gap
    elems.append(pe.shape("tlv-axis", [axis_x, y + sc.len(6), sc.len(2), sc.len(total)],
                          "rect", fill=theme.BLUE_MID))
    for i, m in enumerate(ms):
        last = i == n - 1
        c = theme.GREEN if last else theme.BLUE
        cy = i * (card_h + gap)
        d = 12
        elems.append(pe.shape(f"tlv-dot{i}", [sc.px(8) - sc.len(d / 2) + sc.len(1), y + sc.len(cy + 8),
                              sc.len(d), sc.len(d)], "ellipse", fill=c))
        cx = sc.px(28)
        elems.append(pe.shape(f"tlv{i}", [cx, y + sc.len(cy), w - sc.len(28), sc.len(card_h)],
                              "roundRect", fill=theme.CARD, adjustments=[8000],
                              border={"style": "solid", "width": 1, "color": theme.BORDER}))
        elems.append(pe.shape(f"tlv{i}-bar", [cx, y + sc.len(cy), sc.len(4), sc.len(card_h)],
                              "rect", fill=c))
        elems.append(pe.text(f"tlv{i}-h", [cx + sc.len(16), y + sc.len(cy + 8), w - sc.len(60), sc.len(22)],
                             f'{m.get("label", "")} · {m.get("date", "")}',
                             font_size=max(10, sc.len(13)), color=c, bold=True,
                             align=("left", "middle")))
        elems.append(pe.text(f"tlv{i}-d", [cx + sc.len(16), y + sc.len(cy + 32), w - sc.len(60), sc.len(34)],
                             m.get("desc", ""), font_size=max(9, sc.len(12)),
                             color=theme.TEXT, align=("left", "top")))
    return elems, sc.len(total)


def _module_gantt_pptd(elem, x, y, w):
    """module_gantt pptd：与 HTML 同几何（viewBox 1200 宽 -> 内容区）。
    红三角用原生 triangle 形状 flipV，chip/标签块实底同色，全原生零图像。"""
    sc = pe.PptdScaler(x, y, w)
    g = _mg_geometry(elem)
    tones = _mg_tones()
    gx0, col_w, n = g["gx0"], g["col_w"], g["n"]
    elems = []
    # markers：红三角（flipV 向下）+ 上线点标签
    for i, m in enumerate(g["markers"]):
        c = int(m.get("col", 0))
        if not (0 <= c < n):
            continue
        mx = sc.px(gx0 + c * col_w + 4)
        elems.append(pe.shape(f"mg-m{i}", [mx, sc.py(2), sc.len(12), sc.len(10)],
                              "triangle", fill=theme.RED, flip=[False, True]))
        elems.append(pe.text(f"mg-m{i}-t", [sc.px(gx0 + c * col_w + 20), sc.py(0),
                                            sc.len(col_w - 24), sc.len(16)],
                             m.get("label", ""), font_size=max(8, sc.len(11)),
                             color=theme.TEXT, bold=True, align=("left", "middle"),
                             wrap=False))
        if m.get("note"):
            elems.append(pe.text(f"mg-m{i}-n", [sc.px(gx0 + c * col_w + 20), sc.py(16),
                                                sc.len(col_w - 24), sc.len(14)],
                                 m["note"], font_size=max(7, sc.len(10)),
                                 color=theme.TEXT_SUB, align=("left", "middle"),
                                 wrap=False))
    # 季度表头：深色条
    hy = sc.py(g["markers_h"])
    for c, name in enumerate(g["columns"]):
        hx = sc.px(gx0 + c * col_w + 2)
        elems.append(pe.shape(f"mg-h{c}", [hx, hy, sc.len(col_w - 4), sc.len(g["header_h"])],
                              "rect", fill=theme.TEXT_SUB))
        elems.append(pe.text(f"mg-h{c}-t", [hx, hy, sc.len(col_w - 4), sc.len(g["header_h"])],
                             name, font_size=max(9, sc.len(12)), color=theme.WHITE,
                             bold=True, wrap=False))
    # 域行：左标签块 + 编号 chip 落格
    for ri, r in enumerate(g["rows"]):
        gspec, ry, rh = r["spec"], r["y"], r["h"]
        tone = tones.get(gspec.get("tone", "blue"), theme.BLUE)
        elems.append(pe.shape(f"mg-g{ri}", [sc.px(0), sc.py(ry), sc.len(g["label_w"]), sc.len(rh)],
                              "roundRect", fill=tone, adjustments=[8000]))
        name_text = gspec.get("name", "") + (f'\n{gspec["sub"]}' if gspec.get("sub") else "")
        elems.append(pe.text(f"mg-g{ri}-t", [sc.px(10), sc.py(ry + 8),
                                             sc.len(g["label_w"] - 20), sc.len(rh - 16)],
                             name_text, font_size=max(9, sc.len(13)), color=theme.WHITE,
                             bold=True, align=("left", "top"), line_height=1.35))
        for c, labels in r["stacks"].items():
            for k, label in enumerate(labels):
                cxp = sc.px(gx0 + c * col_w + 8)
                cyp = sc.py(ry + g["pad_t"] + k * (g["chip_h"] + g["chip_gap"]))
                elems.append(pe.shape(f"mg-g{ri}-c{c}-{k}", [cxp, cyp, sc.len(col_w - 16), sc.len(g["chip_h"])],
                                      "roundRect", fill=tone, adjustments=[24000]))
                elems.append(pe.text(f"mg-g{ri}-ct{c}-{k}", [cxp, cyp, sc.len(col_w - 16), sc.len(g["chip_h"])],
                                     label, font_size=max(8, sc.len(11)), color=theme.WHITE,
                                     bold=True, align=("left", "middle"), wrap=False))
    return elems, sc.len(g["H"])


def _msg_geometry(elem):
    """milestone_gantt 布局几何（HTML/pptd 共用，viewBox 1200 宽）。

    结构：markers 行 → 列表头 → 任务行（左标签 + bar 跨列 start~start+span）。
    """
    cols = elem.get("columns", []) or []
    tasks = [t for t in (elem.get("tasks", []) or []) if isinstance(t, dict)]
    markers = elem.get("markers", []) or []
    label_w = 190.0
    gx0, gx1 = 210.0, 1190.0
    n = max(1, len(cols))
    col_w = (gx1 - gx0) / n
    markers_h = 42.0 if markers else 0.0
    header_h = 32.0
    row_h, row_gap = 40.0, 8.0
    bar_h = 24.0
    y = markers_h + header_h
    rows = []
    for i, t in enumerate(tasks):
        start = int(t.get("start", 0))
        span = max(1, int(t.get("span", 1)))
        rows.append({"task": t, "index": i, "y": y,
                     "bar_x": gx0 + start * col_w + 4,
                     "bar_w": span * col_w - 8,
                     "tone": t.get("tone", "blue")})
        y += row_h + row_gap
    H = y - row_gap + 4
    return {"W": 1200.0, "H": H, "columns": [str(c) for c in cols],
            "markers": markers, "label_w": label_w, "gx0": gx0, "col_w": col_w,
            "n": n, "markers_h": markers_h, "header_h": header_h,
            "row_h": row_h, "bar_h": bar_h, "rows": rows}


def _milestone_gantt_html(elem):
    """milestone_gantt HTML：markers + 列表头 + 任务标签 + bar 跨列 + 依赖箭头。"""
    g = _msg_geometry(elem)
    tones = _mg_tones()
    W, H = g["W"], g["H"]
    gx0, col_w, n = g["gx0"], g["col_w"], g["n"]
    parts = [f'<div style="position:relative;width:{W:.0f}px;height:{H:.0f}px;'
             f'font-family:{theme.FONT_STACK};">']
    for m in g["markers"]:
        c = int(m.get("col", 0))
        if not (0 <= c < n):
            continue
        mx = gx0 + c * col_w + 4
        parts.append(
            f'<div style="position:absolute;left:{mx:.0f}px;top:2px;color:{theme.RED};'
            f'font-size:12px;">◆</div>'
            f'<div style="position:absolute;left:{mx + 16:.0f}px;top:0;font-size:11px;'
            f'font-weight:700;color:{theme.TEXT};" data-editable="true">{_esc(m.get("label", ""))}</div>')
    hy = g["markers_h"]
    for c, name in enumerate(g["columns"]):
        hx = gx0 + c * col_w + 2
        parts.append(
            f'<div style="position:absolute;left:{hx:.0f}px;top:{hy:.0f}px;'
            f'width:{col_w - 4:.0f}px;height:{g["header_h"]:.0f}px;'
            f'background:{theme.TEXT_SUB};color:{theme.WHITE};font-size:12px;font-weight:700;'
            f'display:flex;align-items:center;justify-content:center;" data-editable="true">{_esc(name)}</div>')
    for r in g["rows"]:
        t, ry = r["task"], r["y"]
        tone = tones.get(r["tone"], theme.BLUE)
        parts.append(
            f'<div style="position:absolute;left:0;top:{ry:.0f}px;width:{g["label_w"]:.0f}px;'
            f'height:{g["row_h"]:.0f}px;background:{tone};color:{theme.WHITE};border-radius:10px;'
            f'padding:8px 12px;box-sizing:border-box;font-size:13px;font-weight:700;" data-editable="true">{_esc(t.get("name", ""))}</div>')
        by = ry + (g["row_h"] - g["bar_h"]) / 2
        parts.append(
            f'<div style="position:absolute;left:{r["bar_x"]:.0f}px;top:{by:.0f}px;'
            f'width:{r["bar_w"]:.0f}px;height:{g["bar_h"]:.0f}px;background:{tone};'
            f'color:{theme.WHITE};border-radius:6px;font-size:11px;font-weight:600;'
            f'line-height:{g["bar_h"]:.0f}px;padding:0 10px;box-sizing:border-box;'
            f'white-space:nowrap;overflow:hidden;" data-editable="true">{t.get("span", 1)}W</div>')
    deps = []
    for r in g["rows"]:
        for dep in (r["task"].get("deps", []) or []):
            dep = int(dep)
            if 0 <= dep < len(g["rows"]) and dep != r["index"]:
                drow = g["rows"][dep]
                deps.append((drow["bar_x"] + drow["bar_w"], drow["y"] + g["row_h"] / 2,
                             r["bar_x"], r["y"] + g["row_h"] / 2))
    if deps:
        lines = "".join(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="{theme.TEXT_SUB}" stroke-width="1.5" marker-end="url(#msg-arrow)"/>'
            for x1, y1, x2, y2 in deps)
        parts.append(
            f'<svg style="position:absolute;left:0;top:0;width:{W:.0f}px;height:{H:.0f}px;" '
            f'viewBox="0 0 {W:.0f} {H:.0f}">'
            f'<defs><marker id="msg-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">'
            f'<path d="M0,0 L6,3 L0,6 Z" fill="{theme.TEXT_SUB}"/></marker></defs>{lines}</svg>')
    parts.append('</div>')
    return "\n".join(parts)


def _milestone_gantt_pptd(elem, x, y, w):
    """milestone_gantt pptd：markers + 列表头 + 任务标签 + bar 跨列 + 依赖箭头。"""
    sc = pe.PptdScaler(x, y, w)
    g = _msg_geometry(elem)
    tones = _mg_tones()
    gx0, col_w, n = g["gx0"], g["col_w"], g["n"]
    elems = []
    for i, m in enumerate(g["markers"]):
        c = int(m.get("col", 0))
        if not (0 <= c < n):
            continue
        mx = sc.px(gx0 + c * col_w + 4)
        elems.append(pe.shape(f"msg-m{i}", [mx, sc.py(2), sc.len(12), sc.len(12)],
                              "diamond", fill=theme.RED))
        elems.append(pe.text(f"msg-m{i}-t", [sc.px(gx0 + c * col_w + 20), sc.py(0),
                                            sc.len(col_w - 24), sc.len(16)],
                             m.get("label", ""), font_size=max(8, sc.len(11)),
                             color=theme.TEXT, bold=True, align=("left", "middle"), wrap=False))
    hy = sc.py(g["markers_h"])
    for c, name in enumerate(g["columns"]):
        hx = sc.px(gx0 + c * col_w + 2)
        elems.append(pe.shape(f"msg-h{c}", [hx, hy, sc.len(col_w - 4), sc.len(g["header_h"])],
                              "rect", fill=theme.TEXT_SUB))
        elems.append(pe.text(f"msg-h{c}-t", [hx, hy, sc.len(col_w - 4), sc.len(g["header_h"])],
                             name, font_size=max(9, sc.len(12)), color=theme.WHITE,
                             bold=True, wrap=False))
    for r in g["rows"]:
        t, ry = r["task"], r["y"]
        tone = tones.get(r["tone"], theme.BLUE)
        elems.append(pe.shape(f"msg-t{r['index']}", [sc.px(0), sc.py(ry),
                                                      sc.len(g["label_w"]), sc.len(g["row_h"])],
                              "roundRect", fill=tone, adjustments=[8000]))
        elems.append(pe.text(f"msg-t{r['index']}-l", [sc.px(10), sc.py(ry + 6),
                                                      sc.len(g["label_w"] - 20), sc.len(g["row_h"] - 12)],
                             t.get("name", ""), font_size=max(9, sc.len(13)), color=theme.WHITE,
                             bold=True, align=("left", "middle"), wrap=False))
        by = ry + (g["row_h"] - g["bar_h"]) / 2
        elems.append(pe.shape(f"msg-b{r['index']}", [sc.px(r["bar_x"]), sc.py(by),
                                                      sc.len(r["bar_w"]), sc.len(g["bar_h"])],
                              "roundRect", fill=tone, adjustments=[24000]))
        elems.append(pe.text(f"msg-b{r['index']}-t", [sc.px(r["bar_x"]), sc.py(by),
                                                      sc.len(r["bar_w"]), sc.len(g["bar_h"])],
                             f'{t.get("span", 1)}W', font_size=max(8, sc.len(11)),
                             color=theme.WHITE, bold=True, align=("left", "middle"), wrap=False))
    for r in g["rows"]:
        for dep in (r["task"].get("deps", []) or []):
            dep = int(dep)
            if 0 <= dep < len(g["rows"]) and dep != r["index"]:
                drow = g["rows"][dep]
                x1 = sc.px(drow["bar_x"] + drow["bar_w"])
                y1 = sc.py(drow["y"] + g["row_h"] / 2)
                x2 = sc.px(r["bar_x"])
                y2 = sc.py(r["y"] + g["row_h"] / 2)
                elems.append(pe.connector(f"msg-dep{dep}-{r['index']}", x1, y1, x2, y2,
                                          color=theme.TEXT_SUB, width=1.25))
    return elems, sc.len(g["H"])


def render_html(elem):
    st = elem.get("subtype", "horizontal")
    parts = [theme.section_open(elem)]
    if st == "module_gantt":
        parts.append(_module_gantt_html(elem))
        parts.append(theme.SECTION_CLOSE)
        return "\n".join(parts)
    if st == "milestone_gantt":
        parts.append(_milestone_gantt_html(elem))
        parts.append(theme.SECTION_CLOSE)
        return "\n".join(parts)
    if st == "vertical":
        parts.append(_vertical_html(elem))
        parts.append(theme.SECTION_CLOSE)
        return "\n".join(parts)
    ms = elem.get("milestones", []) or []
    n = len(ms)
    parts.append('<div style="display:flex;align-items:stretch;">')
    for i, m in enumerate(ms):
        last = i == n - 1
        bar_c = theme.GREEN if last else theme.BLUE
        arrow = ""
        if not last:
            arrow = (f'<div style="flex:0 0 34px;display:flex;align-items:center;justify-content:center;">'
                     f'<div style="border-left:16px solid {theme.BLUE_MID};border-top:9px solid transparent;'
                     f'border-bottom:9px solid transparent;"></div></div>')
        parts.append(
            f'<div style="flex:1;background:{theme.CARD};border:1px solid {theme.BORDER};border-top:4px solid {bar_c};'
            f'border-radius:8px;padding:16px 18px;">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:1px;color:{bar_c};" data-editable="true">{_esc(m.get("date", ""))}</div>'
            f'<div style="font-size:16px;font-weight:700;margin:4px 0 2px;" data-editable="true">{_esc(m.get("label", ""))}</div>'
            f'<div style="background:{theme.GREEN_LIGHT if last else theme.BLUE_LIGHT};color:{bar_c};border-radius:6px;'
            f'font-size:12px;font-weight:600;padding:8px 10px;margin-top:10px;" data-editable="true">{_esc(m.get("desc", ""))}</div>'
            f'</div>')
        if arrow:
            parts.append(arrow)
    parts.append('</div>')
    parts.append(theme.SECTION_CLOSE)
    return "\n".join(parts)


def render_pptd(elem, x, y, w):
    if elem.get("subtype") == "module_gantt":
        return _module_gantt_pptd(elem, x, y, w)
    if elem.get("subtype") == "milestone_gantt":
        return _milestone_gantt_pptd(elem, x, y, w)
    if elem.get("subtype") == "vertical":
        return _vertical_pptd(elem, x, y, w)
    ms = elem.get("milestones", []) or []
    n = len(ms)
    if not n:
        return [], 0
    sc = pe.PptdScaler(x, y, w)
    arrow_w = 34.0
    card_w = (1200 - arrow_w * (n - 1)) / n
    card_h = 150.0
    elems = []
    for i, m in enumerate(ms):
        last = i == n - 1
        bar_c = theme.GREEN if last else theme.BLUE
        cx = sc.px(i * (card_w + arrow_w))
        elems.append(pe.shape(f"tl{i}", [cx, y, sc.len(card_w), sc.len(card_h)], "roundRect",
                              fill=theme.CARD, adjustments=[6000],
                              border={"style": "solid", "width": 1, "color": theme.BORDER}))
        elems.append(pe.shape(f"tl{i}-top", [cx, y, sc.len(card_w), sc.len(4)], "rect", fill=bar_c))
        elems.append(pe.text(f"tl{i}-date", [cx + sc.len(16), y + sc.len(14), sc.len(card_w - 32), sc.len(18)],
                             m.get("date", ""), font_size=max(9, sc.len(11)), color=bar_c,
                             bold=True, align=("left", "middle")))
        elems.append(pe.text(f"tl{i}-label", [cx + sc.len(16), y + sc.len(34), sc.len(card_w - 32), sc.len(26)],
                             m.get("label", ""), font_size=max(11, sc.len(16)), color=theme.TEXT,
                             bold=True, align=("left", "middle")))
        if m.get("desc"):
            elems.append(pe.shape(f"tl{i}-dv", [cx + sc.len(14), y + sc.len(70), sc.len(card_w - 28), sc.len(card_h - 86)],
                                  "roundRect", fill=theme.GREEN_LIGHT if last else theme.BLUE_LIGHT,
                                  adjustments=[10000]))
            elems.append(pe.text(f"tl{i}-desc", [cx + sc.len(24), y + sc.len(70), sc.len(card_w - 48), sc.len(card_h - 86)],
                                 m["desc"], font_size=max(8, sc.len(11)), color=bar_c,
                                 align=("left", "middle")))
        if not last:
            ax = sc.px(i * (card_w + arrow_w) + card_w + 4)
            elems.append(pe.shape(f"tl-arr{i}", [ax, y + sc.len(card_h / 2 - 12), sc.len(arrow_w - 8), sc.len(24)],
                                  "chevron", fill=theme.BLUE_MID))
    return elems, sc.len(card_h)
