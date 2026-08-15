# -*- coding: utf-8 -*-
"""matrix 类渲染器：fit_gap / raci / crud / cbm / capability_map（5 种全部实现）。

fit_gap：三色徽章表格（绿 Fit / 橙 Partial / 红 Gap）。
capability_map：业务能力点亮图（stats 条 + 图例 + CBM 分区 + L1 卡 + chip 三态
+ 系统清单），chip 级三态 + 覆盖率条（v1.1 定稿，较首版的两点改进）。

spec：
  fit_gap: {requirements: [], products: [], cells: [{req, product, match, note}]}
  capability_map: {stats: [{label, value}], sections: [{name, capabilities: [{
      code, name, status(lit|partial|none), coverage(0-100), system,
      items: [{name, status}]}]}], systems_inventory: [{name, pts, detail}]}
"""

from . import theme
from .theme import _esc
from . import pptd_emit as pe
from ..spacing import INSET_X, INSET_Y

# fit/status 配色表：调用时取 theme（P2-A2 风格透传，模块级快照会在
# use_style 切换后滞留旧色板）
def _match_styles():
    return {"fit": ("Fit", theme.GREEN_LIGHT, theme.GREEN),
            "partial": ("Partial", theme.ORANGE_LIGHT, theme.ORANGE),
            "gap": ("Gap", theme.RED_LIGHT, theme.RED)}


def _status_styles():
    return {"lit": ("已点亮", theme.GREEN_LIGHT, theme.GREEN, theme.GREEN),
            "partial": ("部分覆盖", theme.ORANGE_LIGHT, theme.ORANGE, theme.ORANGE),
            "none": ("未点亮", theme.BLUE_LIGHT, theme.TEXT_SUB, theme.BORDER)}


# ---------------------------------------------------------------------------
# fit_gap
# ---------------------------------------------------------------------------

def _fit_rows(elem):
    reqs = elem.get("requirements", []) or []
    prods = elem.get("products", []) or []
    cell_map = {(c.get("req"), c.get("product")): c for c in elem.get("cells", []) or []}
    return reqs, prods, cell_map


def _fit_html(elem):
    reqs, prods, cell_map = _fit_rows(elem)
    head = "".join(f'<th style="padding:6px 10px;text-align:left;">{_esc(p)}</th>' for p in prods)
    rows_html = []
    for r in reqs:
        tds = [f'<td style="font-weight:600;" data-editable="true">{_esc(r)}</td>']
        for p in prods:
            cell = cell_map.get((r, p), {})
            match = cell.get("match", "")
            if match in _match_styles():
                label, bg, fg = _match_styles()[match]
                note = cell.get("note", "")
                badge = (f'<span style="display:inline-block;border-radius:11px;padding:2px 8px;'
                         f'font-size:12px;font-weight:700;background:{bg};color:{fg};" data-editable="true">{label}</span>')
                if note:
                    badge += f' <span style="font-size:12px;color:{theme.TEXT_SUB};" data-editable="true">{_esc(note)}</span>'
                tds.append(f"<td>{badge}</td>")
            else:
                tds.append(f'<td style="color:{theme.GRAY};">—</td>')
        rows_html.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            f'<thead><tr style="background:{theme.BLUE};color:{theme.WHITE};">'
            f'<th style="padding:6px 10px;text-align:left;width:34%;">客户需求</th>{head}</tr></thead>'
            f"<tbody>{''.join(rows_html)}</tbody></table>"
            f'<style>section.diagram[data-subtype="fit_gap"] td{{padding:6px 10px;border-bottom:1px solid {theme.BORDER};}}'
            f'section.diagram[data-subtype="fit_gap"] tr:hover td{{background:{theme.BLUE_LIGHT};}}</style>')


def _fit_pptd(elem, x, y, w):
    """fit_gap -> 原生 table 元素（单元格 {content:}，方言陷阱 5/6）。

    行高 hug（间距体系 v1 §五，排查 I-16）：行高 = 单元格最大行数 × 行距 +
    2×INSET_Y，下限原写死值（短内容不变，长文本 note 撑高所在行）。
    """
    reqs, prods, cell_map = _fit_rows(elem)
    n_cols = len(prods) + 1
    header = [{"content": {"text": "客户需求"}}] + [
        {"content": {"text": str(p)}} for p in prods]
    emit_rows = [header]
    plain_rows = [["客户需求"] + [str(p) for p in prods]]
    for r in reqs:
        row = [{"content": {"color": "$navy", "text": f"<p><strong>{_esc(r)}</strong></p>\n"}}]
        prow = [str(r)]
        for p in prods:
            cell = cell_map.get((r, p), {})
            match = cell.get("match", "")
            if match in _match_styles():
                label, _, fg = _match_styles()[match]
                note = cell.get("note", "")
                txt = f"<p><strong>{label}</strong></p>\n" + (f"<p>{_esc(note)}</p>\n" if note else "")
                row.append({"content": {"color": fg, "text": txt}})
                prow.append(label + ("\n" + str(note) if note else ""))
            else:
                row.append({"content": {"text": "—"}})
                prow.append("—")
        emit_rows.append(row)
        plain_rows.append(prow)
    col_w = [0.34] + [(0.66 / max(1, n_cols - 1))] * (n_cols - 1)
    table_h, row_fracs = pe.table_hug_geometry(plain_rows, col_w, w, 40, 0.14)
    elems = [{
        "elementId": f"fitgap-{y}", "elementType": "table",
        "bounds": [x, y, w, table_h],
        "columnWidths": col_w,
        "rowHeights": row_fracs,
        "style": "$default",
        "rows": emit_rows,
    }]
    return elems, table_h


# ---------------------------------------------------------------------------
# capability_map
# ---------------------------------------------------------------------------

def _cmap_html(elem):
    parts = []
    stats = elem.get("stats", []) or []
    if stats:
        cards = "".join(
            f'<div style="background:{theme.CARD};border:1px solid {theme.BORDER};border-top:3px solid {theme.BLUE};'
            f'border-radius:10px;padding:12px 26px;text-align:center;">'
            f'<div style="font-size:28px;font-weight:700;color:{theme.BLUE};" data-editable="true">{_esc(s.get("value", ""))}</div>'
            f'<div style="font-size:12px;color:{theme.TEXT_SUB};">{_esc(s.get("label", ""))}</div></div>'
            for s in stats)
        parts.append(f'<div style="display:flex;justify-content:center;gap:24px;flex-wrap:wrap;margin-bottom:16px;">{cards}</div>')
    # 图例
    parts.append(
        f'<div style="display:flex;gap:18px;justify-content:center;flex-wrap:wrap;background:{theme.CARD};'
        f'border:1px solid {theme.BORDER};border-radius:8px;padding:10px 18px;font-size:12px;margin-bottom:18px;">'
        f'<span><i style="display:inline-block;width:13px;height:13px;border-radius:3px;background:{theme.GREEN};"></i> 已点亮（有系统支撑）</span>'
        f'<span><i style="display:inline-block;width:13px;height:13px;border-radius:3px;background:{theme.ORANGE};"></i> 部分覆盖</span>'
        f'<span><i style="display:inline-block;width:13px;height:13px;border-radius:3px;background:{theme.WHITE};border:1px dashed {theme.BORDER};"></i> 未点亮（缺口）</span></div>')
    for sec in elem.get("sections", []) or []:
        parts.append(f'<div style="font-size:15px;font-weight:700;color:{theme.BLUE};border-left:4px solid {theme.BLUE};'
                     f'padding-left:10px;margin:20px 0 12px;" data-editable="true">{_esc(sec.get("name", ""))}</div>')
        parts.append('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;">')
        for cap in sec.get("capabilities", []) or []:
            parts.append(_cmap_card_html(cap))
        parts.append('</div>')
    inv = elem.get("systems_inventory", []) or []
    if inv:
        parts.append(f'<div style="font-size:15px;font-weight:700;color:{theme.BLUE};border-left:4px solid {theme.BLUE};'
                     f'padding-left:10px;margin:20px 0 12px;" data-editable="true">涉及系统清单</div>')
        cards = "".join(
            f'<div style="background:{theme.CARD};border:1px solid {theme.BORDER};border-top:3px solid {theme.GREEN};'
            f'border-radius:8px;padding:10px 14px;">'
            f'<div style="font-size:13px;font-weight:700;" data-editable="true">{_esc(s.get("name", ""))}</div>'
            f'<div style="font-size:20px;font-weight:700;color:{theme.GREEN};" data-editable="true">{_esc(s.get("pts", ""))}</div>'
            f'<div style="font-size:11px;color:{theme.TEXT_SUB};" data-editable="true">{_esc(s.get("detail", ""))}</div></div>'
            for s in inv)
        parts.append(f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:4px;">{cards}</div>')
    return "\n".join(parts)


def _cmap_card_html(cap):
    status = cap.get("status", "none")
    label, st_bg, st_fg, bar_c = _status_styles().get(status, _status_styles()["none"])
    cov = cap.get("coverage")
    if cov is None:
        cov = {"lit": 100, "partial": 50, "none": 0}[status]
    chip_html = []
    for it in cap.get("items", []) or []:
        ist = it.get("status", "none") if isinstance(it, dict) else "lit"
        name = it.get("name", "") if isinstance(it, dict) else str(it)
        if ist == "lit":
            style = f"background:{theme.GREEN_LIGHT};color:{theme.GREEN};border:1px solid rgba(47,125,95,0.3);"
        elif ist == "partial":
            style = f"background:{theme.ORANGE_LIGHT};color:{theme.ORANGE};border:1px solid rgba(214,158,46,0.35);"
        else:
            style = f"background:{theme.WHITE};color:{theme.TEXT_SUB};border:1px dashed {theme.BORDER};"
        chip_html.append(f'<span style="display:inline-flex;align-items:center;border-radius:4px;padding:3px 8px;'
                         f'font-size:11px;font-weight:600;{style}" data-editable="true">{_esc(name)}</span>')
    system = cap.get("system", "")
    sys_line = (f'<div style="font-size:12px;font-weight:700;color:{theme.BLUE_MID};border-left:2px solid {theme.BLUE_MID};'
                f'padding-left:6px;margin:8px 0 5px;" data-editable="true">{_esc(system)}</div>') if system else ""
    return (
        f'<div style="background:{theme.CARD};border:1px solid {theme.BORDER};border-left:4px solid {bar_c};'
        f'border-radius:10px;padding:14px 16px;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;">'
        f'<span style="background:{theme.BLUE};color:{theme.WHITE};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">{_esc(cap.get("code", ""))}</span>'
        f'<span style="font-size:14px;font-weight:700;flex:1;min-width:120px;" data-editable="true">{_esc(cap.get("name", ""))}</span>'
        f'<span style="font-size:11px;font-weight:600;border-radius:4px;padding:2px 8px;background:{st_bg};color:{st_fg};">{label}</span></div>'
        f'<div style="height:5px;background:{theme.BLUE_LIGHT};border-radius:3px;overflow:hidden;margin-bottom:10px;">'
        f'<i style="display:block;height:100%;width:{cov}%;background:{bar_c};border-radius:3px;"></i></div>'
        f'{sys_line}'
        f'<div style="display:flex;flex-wrap:wrap;gap:5px;">{"".join(chip_html)}</div></div>')


def _cmap_pptd(elem, x, y, w):
    """点亮图 pptd 简化版：stats 行 + 每 section 标题 + L1 卡（chip 文本行）。"""
    sc = pe.PptdScaler(x, y, w)
    elems = []
    cy = 0.0
    stats = elem.get("stats", []) or []
    if stats:
        n = len(stats)
        gap = 16.0
        cw = (1200 - gap * (n - 1)) / n
        for i, s in enumerate(stats):
            sx = sc.px(i * (cw + gap))
            elems.append(pe.shape(f"st{i}", [sx, y, sc.len(cw), sc.len(64)], "roundRect",
                                  fill=theme.CARD, adjustments=[8000],
                                  border={"style": "solid", "width": 1, "color": theme.BORDER}))
            elems.append(pe.shape(f"st{i}-top", [sx, y, sc.len(cw), sc.len(3)], "rect", fill=theme.BLUE))
            elems.append(pe.text(f"st{i}-n", [sx, y + sc.len(8), sc.len(cw), sc.len(30)],
                                 str(s.get("value", "")), font_size=max(14, sc.len(24)),
                                 color=theme.BLUE, bold=True))
            elems.append(pe.text(f"st{i}-l", [sx, y + sc.len(40), sc.len(cw), sc.len(18)],
                                 s.get("label", ""), font_size=max(8, sc.len(11)),
                                 color=theme.TEXT_SUB))
        cy += 64 + 18
    for si, sec in enumerate(elem.get("sections", []) or []):
        elems.append(pe.text(f"sec{si}", [x, y + sc.len(cy), sc.len(600), sc.len(24)],
                             sec.get("name", ""), font_size=max(11, sc.len(15)),
                             color=theme.BLUE, bold=True, align=("left", "middle")))
        cy += 24 + 8
        caps = sec.get("capabilities", []) or []
        # 列数自适应（v2.1 紧凑化，防 9 卡 2 列超 PPT 页面空间）：
        # 3 卡 -> 3 列整行（9 卡 3 行）；2 卡 -> 2 列；1 卡 -> 1 列
        n_caps = len(caps)
        cols = 3 if n_caps == 3 else (2 if n_caps > 1 else 1)
        card_w = (1200 - 20 * (cols - 1)) / cols
        row_h = 0.0
        for ci, cap in enumerate(caps):
            col = ci % cols
            if ci and col == 0:
                cy += row_h + 12
                row_h = 0.0
            cx = sc.px(col * (card_w + 20))
            status = cap.get("status", "none")
            label, st_bg, st_fg, bar_c = _status_styles().get(status, _status_styles()["none"])
            # 紧凑卡：无 items 子项时卡高 96 -> 64（name+system 两行即可），
            # 带 items 保留 96（chips 行）；9 卡全保留时可压进单页
            has_items = bool(cap.get("items"))
            body_h = 96.0 if has_items else 64.0
            chip_line = "  ".join(("● " if (it.get("status", "lit") if isinstance(it, dict) else "lit") == "lit"
                                   else "◐ " if (it.get("status", "") if isinstance(it, dict) else "") == "partial"
                                   else "○ ") + (it.get("name", "") if isinstance(it, dict) else str(it))
                                   for it in cap.get("items", []) or [])
            elems.append(pe.shape(f"cap{si}-{ci}", [cx, y + sc.len(cy), sc.len(card_w), sc.len(body_h)],
                                  "roundRect", fill=theme.CARD, adjustments=[6000],
                                  border={"style": "solid", "width": 1, "color": theme.BORDER}))
            elems.append(pe.shape(f"cap{si}-{ci}-bar", [cx, y + sc.len(cy), sc.len(5), sc.len(body_h)],
                                  "rect", fill=bar_c))
            elems.append(pe.text(f"cap{si}-{ci}-name", [cx + sc.len(16), y + sc.len(cy + 8), sc.len(card_w - 130), sc.len(22)],
                                 f'{cap.get("code", "")} {cap.get("name", "")}',
                                 font_size=max(10, sc.len(13)), color=theme.TEXT, bold=True,
                                 align=("left", "middle")))
            elems.append(pe.text(f"cap{si}-{ci}-st", [cx + sc.len(card_w - 100), y + sc.len(cy + 10), sc.len(84), sc.len(18)],
                                 label, font_size=max(8, sc.len(10)), color=st_fg, bold=True,
                                 align=("right", "middle")))
            if cap.get("system"):
                elems.append(pe.text(f"cap{si}-{ci}-sys", [cx + sc.len(16), y + sc.len(cy + 34), sc.len(card_w - 32), sc.len(18)],
                                     cap["system"], font_size=max(8, sc.len(10)),
                                     color=theme.BLUE_MID, align=("left", "middle")))
            if chip_line:
                elems.append(pe.text(f"cap{si}-{ci}-chips", [cx + sc.len(16), y + sc.len(cy + 54), sc.len(card_w - 32), sc.len(36)],
                                     chip_line, font_size=max(8, sc.len(10)), color=theme.TEXT_SUB,
                                     align=("left", "top")))
            row_h = max(row_h, body_h)
        cy += row_h + 16
    # 系统清单卡
    inv = elem.get("systems_inventory", []) or []
    if inv:
        elems.append(pe.text("sysinv", [x, y + sc.len(cy), sc.len(600), sc.len(24)],
                             "涉及系统清单", font_size=max(11, sc.len(15)),
                             color=theme.BLUE, bold=True, align=("left", "middle")))
        cy += 24 + 8
        n = len(inv)
        gap = 16.0
        cw = (1200 - gap * (n - 1)) / n
        for i, s in enumerate(inv):
            sx = sc.px(i * (cw + gap))
            elems.append(pe.shape(f"sys{i}", [sx, y + sc.len(cy), sc.len(cw), sc.len(72)], "roundRect",
                                  fill=theme.CARD, adjustments=[8000],
                                  border={"style": "solid", "width": 1, "color": theme.BORDER}))
            elems.append(pe.shape(f"sys{i}-top", [sx, y + sc.len(cy), sc.len(cw), sc.len(3)], "rect", fill=theme.GREEN))
            elems.append(pe.text(f"sys{i}-n", [sx + sc.len(12), y + sc.len(cy + 8), sc.len(cw - 24), sc.len(18)],
                                 s.get("name", ""), font_size=max(9, sc.len(12)),
                                 color=theme.TEXT, bold=True, align=("left", "middle")))
            detail = "  ".join(filter(None, [str(s.get("pts", "")), s.get("detail", "")]))
            elems.append(pe.text(f"sys{i}-d", [sx + sc.len(12), y + sc.len(cy + 30), sc.len(cw - 24), sc.len(34)],
                                 detail, font_size=max(8, sc.len(10)), color=theme.TEXT_SUB,
                                 align=("left", "top")))
        cy += 72
    return elems, sc.len(cy)


# ---------------------------------------------------------------------------
# P1：raci / crud / cbm
# ---------------------------------------------------------------------------

def _raci_html(elem):
    roles = elem.get("roles", []) or []
    tasks = elem.get("tasks", []) or []
    badge = {
        "A": f"background:{theme.BLUE};color:{theme.WHITE};",
        "R": f"background:{theme.GREEN};color:{theme.WHITE};",
        "C": f"background:{theme.WHITE};color:{theme.BLUE};border:1.5px solid {theme.BLUE};",
        "I": f"background:{theme.WHITE};color:{theme.GRAY};border:1.5px solid {theme.BORDER};",
    }
    head = "".join(f'<th style="padding:6px 10px;">{_esc(r)}</th>' for r in roles)
    rows = []
    for t in tasks:
        amap = {a.get("role"): a.get("type") for a in t.get("assignments", []) or []}
        tds = [f'<td style="text-align:left;font-weight:600;" data-editable="true">{_esc(t.get("name", ""))}</td>']
        for r in roles:
            ty = amap.get(r)
            if ty in badge:
                tds.append(f'<td><span style="display:inline-block;width:24px;height:24px;line-height:20px;border-radius:50%;'
                           f'text-align:center;font-size:12px;font-weight:700;{badge[ty]}">{ty}</span></td>')
            else:
                tds.append('<td style="color:{theme.BORDER_STRONG};">—</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<table style="width:100%;border-collapse:collapse;font-size:13px;text-align:center;">'
            f'<thead><tr style="background:{theme.BLUE};color:{theme.WHITE};"><th style="text-align:left;width:28%;padding:6px 10px;">任务</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            f'<style>section.diagram[data-subtype="raci"] td{{padding:6px 10px;border-bottom:1px solid {theme.BORDER};}}'
            f'section.diagram[data-subtype="raci"] tr:hover td{{background:{theme.BLUE_LIGHT};}}</style>')


def _crud_html(elem):
    docs = elem.get("docs", []) or []
    entities = elem.get("entities", []) or []
    cell_map = {(c.get("doc"), c.get("entity")): c.get("ops", []) for c in elem.get("cells", []) or []}
    def chip(op):
        return (f'<span style="display:inline-block;min-width:22px;text-align:center;border-radius:11px;'
                           f'padding:2px 8px;font-size:12px;font-weight:700;border:1.5px solid {theme.BLUE};'
                           f'color:{theme.BLUE};background:{theme.WHITE};margin:0 2px;">{op}</span>')
    head = "".join(f'<th style="padding:6px 10px;">{_esc(e)}</th>' for e in entities)
    rows = []
    for d in docs:
        tds = [f'<td style="text-align:left;font-weight:600;" data-editable="true">{_esc(d)}</td>']
        for e in entities:
            ops = cell_map.get((d, e), [])
            tds.append("<td>" + ("".join(chip(o) for o in ops) if ops else '<span style="color:{theme.BORDER_STRONG};">—</span>') + "</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<table style="width:100%;border-collapse:collapse;font-size:13px;text-align:center;">'
            f'<thead><tr style="background:{theme.BLUE};color:{theme.WHITE};"><th style="text-align:left;width:24%;padding:6px 10px;">业务单据</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            f'<style>section.diagram[data-subtype="crud"] td{{padding:6px 10px;border-bottom:1px solid {theme.BORDER};}}'
            f'section.diagram[data-subtype="crud"] tr:hover td{{background:{theme.BLUE_LIGHT};}}</style>')


def _cbm_level_colors():
    """cbm 层级循环色（调用时取 theme，P2-A2 风格透传）。"""
    return [theme.BLUE, theme.GREEN, theme.TEAL]


def _cbm_heat():
    """cbm 热力色（调用时取 theme，P2-A2 风格透传）。"""
    return {"strong": theme.GREEN, "mid": theme.ORANGE, "weak": theme.RED}


def _cbm_html(elem):
    rows = elem.get("rows", []) or []
    max_cols = max((len(r.get("capabilities", []) or []) for r in rows), default=1)
    parts = [f'<div style="display:grid;grid-template-columns:110px repeat({max_cols},1fr);gap:8px;align-items:stretch;">']
    for li, r in enumerate(rows):
        color = _cbm_level_colors()[li % 3]
        parts.append(f'<div style="background:{color};color:{theme.WHITE};border-radius:8px;display:flex;align-items:center;'
                     f'justify-content:center;font-weight:700;padding:12px 6px;text-align:center;" data-editable="true">{_esc(r.get("level", ""))}</div>')
        for c in r.get("capabilities", []) or []:
            if isinstance(c, dict):
                name, heat = c.get("name", ""), c.get("heat", "")
            else:
                name, heat = str(c), ""
            top = f'border-top:3px solid {_cbm_heat()[heat]};' if heat in _cbm_heat() else ""
            parts.append(f'<div style="background:{theme.WHITE};border:1px solid {theme.BORDER};{top}border-radius:8px;'
                         f'padding:10px;text-align:center;font-size:13px;font-weight:600;" data-editable="true">{_esc(name)}</div>')
    parts.append('</div>')
    if any((c.get("heat") if isinstance(c, dict) else None) for r in rows for c in r.get("capabilities", []) or []):
        parts.append(f'<div style="margin-top:10px;font-size:12px;color:{theme.TEXT_SUB};">热力图例：'
                     f'<span style="color:{theme.GREEN};font-weight:700;">■</span> 强 '
                     f'<span style="color:{theme.ORANGE};font-weight:700;">■</span> 中 '
                     f'<span style="color:{theme.RED};font-weight:700;">■</span> 缺（能力格顶部色条）</div>')
    return "\n".join(parts)


def _raci_pptd(elem, x, y, w):
    roles = elem.get("roles", []) or []
    tasks = elem.get("tasks", []) or []
    colors = {"A": theme.BLUE, "R": theme.GREEN, "C": theme.BLUE_MID, "I": theme.GRAY}
    headers = ["任务"] + roles
    emit_rows = [[{"content": {"text": h}} for h in headers]]
    plain_rows = [[str(h) for h in headers]]
    for t in tasks:
        amap = {a.get("role"): a.get("type") for a in t.get("assignments", []) or []}
        row = [{"content": {"color": "$navy", "text": f"<p><strong>{pe._esc(t.get('name', ''))}</strong></p>\n"}}]
        prow = [str(t.get("name", ""))]
        for r in roles:
            ty = amap.get(r)
            if ty in colors:
                row.append({"content": {"color": colors[ty], "align": ["center", "middle"],
                                        "text": f"<p><strong>{ty}</strong></p>\n"}})
                prow.append(str(ty))
            else:
                row.append({"content": {"align": ["center", "middle"], "text": "—"}})
                prow.append("—")
        emit_rows.append(row)
        plain_rows.append(prow)
    n_cols = len(headers)
    col_w = [0.28] + [0.72 / max(1, n_cols - 1)] * (n_cols - 1)
    # 行高 hug（间距体系 v1 §五，排查 I-16）：下限原写死 36
    table_h, row_fracs = pe.table_hug_geometry(plain_rows, col_w, w, 36, 0.16)
    elems = [{
        "elementId": f"raci-{y}", "elementType": "table",
        "bounds": [x, y, w, table_h],
        "columnWidths": col_w,
        "rowHeights": row_fracs,
        "style": "$default",
        "rows": emit_rows,
    }]
    return elems, table_h


def _crud_pptd(elem, x, y, w):
    docs = elem.get("docs", []) or []
    entities = elem.get("entities", []) or []
    cell_map = {(c.get("doc"), c.get("entity")): c.get("ops", []) for c in elem.get("cells", []) or []}
    headers = ["业务单据"] + entities
    emit_rows = [[{"content": {"text": pe._esc(h)}} for h in headers]]
    plain_rows = [[str(h) for h in headers]]
    for d in docs:
        row = [{"content": {"color": "$navy", "text": f"<p><strong>{pe._esc(d)}</strong></p>\n"}}]
        prow = [str(d)]
        for e in entities:
            ops = cell_map.get((d, e), [])
            row.append({"content": {"color": theme.BLUE, "align": ["center", "middle"],
                                    "text": " ".join(pe._esc(o) for o in ops) if ops else "—"}})
            prow.append(" ".join(ops) if ops else "—")
        emit_rows.append(row)
        plain_rows.append(prow)
    n_cols = len(headers)
    col_w = [0.24] + [0.76 / max(1, n_cols - 1)] * (n_cols - 1)
    # 行高 hug（间距体系 v1 §五，排查 I-16）：下限原写死 36
    table_h, row_fracs = pe.table_hug_geometry(plain_rows, col_w, w, 36, 0.16)
    elems = [{
        "elementId": f"crud-{y}", "elementType": "table",
        "bounds": [x, y, w, table_h],
        "columnWidths": col_w,
        "rowHeights": row_fracs,
        "style": "$default",
        "rows": emit_rows,
    }]
    return elems, table_h


def _cbm_pptd(elem, x, y, w):
    rows = elem.get("rows", []) or []
    sc = pe.PptdScaler(x, y, w)
    max_cols = max((len(r.get("capabilities", []) or []) for r in rows), default=1)
    label_w, gap = 110.0, 8.0
    cell_w = (1200 - label_w - gap * max_cols) / max_cols
    cell_h = 52.0
    elems = []
    cy = 0.0
    for li, r in enumerate(rows):
        color = _cbm_level_colors()[li % 3]
        # 行高 hug（间距体系 v1 §五，排查 I-17）：行高 = 行内最大行数 × 行距
        # + 2×INSET_Y，下限原写死 52（短内容不变，长 level/能力名撑高整行）
        max_lines = len(pe.wrap_lines(r.get("level", ""), 13.0, label_w - 2 * INSET_X))
        for c in r.get("capabilities", []) or []:
            name = c.get("name", "") if isinstance(c, dict) else str(c)
            max_lines = max(max_lines, len(pe.wrap_lines(name, 12.0, cell_w - 2 * INSET_X)))
        row_h = max(cell_h, pe.stack_text_h(max_lines, 13.0) + 2 * INSET_Y)
        elems.append(pe.shape(f"cbm-l{li}", [x, y + sc.len(cy), sc.len(label_w), sc.len(row_h)],
                              "roundRect", fill=color, adjustments=[8000]))
        elems.append(pe.text(f"cbm-l{li}-t", [x, y + sc.len(cy), sc.len(label_w), sc.len(row_h)],
                             r.get("level", ""), font_size=max(10, sc.len(13)),
                             color=theme.WHITE, bold=True))
        for ci, c in enumerate(r.get("capabilities", []) or []):
            if isinstance(c, dict):
                name, heat = c.get("name", ""), c.get("heat", "")
            else:
                name, heat = str(c), ""
            cx = sc.px(label_w + gap + ci * (cell_w + gap))
            elems.append(pe.shape(f"cbm-{li}-{ci}", [cx, y + sc.len(cy), sc.len(cell_w), sc.len(row_h)],
                                  "roundRect", fill=theme.CARD, adjustments=[6000],
                                  border={"style": "solid", "width": 1, "color": theme.BORDER}))
            if heat in _cbm_heat():
                elems.append(pe.shape(f"cbm-{li}-{ci}-heat", [cx, y + sc.len(cy), sc.len(cell_w), sc.len(3)],
                                      "rect", fill=_cbm_heat()[heat]))
            elems.append(pe.text(f"cbm-{li}-{ci}-t", [cx, y + sc.len(cy), sc.len(cell_w), sc.len(row_h)],
                                 name, font_size=max(9, sc.len(12)), color=theme.TEXT, bold=True))
        cy += row_h + gap
    return elems, sc.len(cy)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# D-5：quadrant 四象限（两轴 + 四区 rect，无需布尔，禁 freeform path）
# ---------------------------------------------------------------------------

def _quadrant_html(elem):
    axes = elem.get("axes", {}) or {}
    quads = elem.get("quads", []) or []
    vb_w, vb_h = 1200, 460
    cx, cy = 600.0, 230.0
    half_w, half_h = 470.0, 185.0
    light = [theme.BLUE_LIGHT, theme.GREEN_LIGHT,
             theme.ORANGE_LIGHT, theme.PURPLE_LIGHT]
    parts = [f'<svg class="dg" viewBox="0 0 {vb_w} {vb_h}" '
             f'xmlns="http://www.w3.org/2000/svg">']
    # 两轴（y 轴垂直 + x 轴水平）
    parts.append(f'<line x1="{cx}" y1="{cy - half_h}" x2="{cx}" y2="{cy + half_h}" '
                 f'stroke="{theme.BLUE_MID}" stroke-width="2"/>')
    parts.append(f'<line x1="{cx - half_w}" y1="{cy}" x2="{cx + half_w}" y2="{cy}" '
                 f'stroke="{theme.BLUE_MID}" stroke-width="2"/>')
    # 轴标签
    parts.append(f'<text x="{cx}" y="{cy - half_h - 10}" font-size="13" '
                 f'font-weight="700" fill="{theme.BLUE}" text-anchor="middle" '
                 f'data-editable="true">{_esc(axes.get("y", ""))}</text>')
    parts.append(f'<text x="{cx + half_w + 14}" y="{cy + 5}" font-size="13" '
                 f'font-weight="700" fill="{theme.BLUE}" text-anchor="middle" '
                 f'data-editable="true">{_esc(axes.get("x", ""))}</text>')
    # 四区（tl, tr, bl, br）
    pos = [(cx - half_w, cy - half_h), (cx, cy - half_h),
           (cx - half_w, cy), (cx, cy)]
    for i, q in enumerate(quads):
        qx, qy = pos[i]
        parts.append(f'<rect x="{qx}" y="{qy}" width="{half_w}" height="{half_h}" '
                     f'fill="{light[i % len(light)]}" stroke="{theme.BORDER}" '
                     f'stroke-width="1"/>')
        items = q.get("items", []) or []
        title_h, item_h, gap = 32.0, 26.0, 10.0
        content_h = title_h + (gap + len(items) * item_h if items else 0)
        start_y = qy + (half_h - content_h) / 2
        parts.append(f'<text x="{qx + half_w / 2}" y="{start_y + 22}" font-size="19" '
                     f'font-weight="700" fill="{theme.TEXT}" text-anchor="middle" '
                     f'data-editable="true">{_esc(q.get("title", ""))}</text>')
        for j, it in enumerate(items):
            parts.append(f'<text x="{qx + half_w / 2}" '
                         f'y="{start_y + title_h + gap + j * item_h}" '
                         f'font-size="15" fill="{theme.TEXT_SUB}" text-anchor="middle" '
                         f'data-editable="true">• {_esc(str(it))}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _quadrant_pptd(elem, x, y, w):
    axes = elem.get("axes", {}) or {}
    quads = elem.get("quads", []) or []
    sc = pe.PptdScaler(x, y, w)
    elems = []
    vb_h = 460.0
    cx, cy = 600.0, 230.0
    half_w, half_h = 470.0, 185.0
    light = [theme.BLUE_LIGHT, theme.GREEN_LIGHT,
             theme.ORANGE_LIGHT, theme.PURPLE_LIGHT]
    pos = [(cx - half_w, cy - half_h), (cx, cy - half_h),
           (cx - half_w, cy), (cx, cy)]
    # 四区 rect（先画底，轴最后画在最上）
    for i, q in enumerate(quads):
        qx, qy = pos[i]
        elems.append(pe.shape(f"qd{i}", [sc.px(qx), sc.py(qy),
                                         sc.len(half_w), sc.len(half_h)],
                              "rect", fill=light[i % len(light)],
                              border={"style": "solid", "width": 1,
                                      "color": theme.BORDER}))
        items = q.get("items", []) or []
        title_h, item_h, gap = 32.0, 26.0, 10.0
        content_h = title_h + (gap + len(items) * item_h if items else 0)
        start_y = qy + (half_h - content_h) / 2
        elems.append(pe.text(f"qd{i}-t", [sc.px(qx), sc.py(start_y),
                                           sc.len(half_w), sc.len(title_h)],
                             q.get("title", ""), font_size=max(16, sc.len(18)),
                             color=theme.TEXT, bold=True))
        if items:
            body = "\n".join("• " + str(it) for it in items)
            elems.append(pe.text(f"qd{i}-b", [sc.px(qx + 20),
                                               sc.py(start_y + title_h + gap),
                                               sc.len(half_w - 40),
                                               sc.len(len(items) * item_h)],
                                 body, font_size=max(12, sc.len(14)),
                                 color=theme.TEXT_SUB, align=("center", "top")))
    # 两轴（细 rect 表示，画在最上）
    elems.append(pe.shape("qd-vaxis", [sc.px(cx), sc.py(cy - half_h), 1.5,
                                       sc.len(2 * half_h)], "rect",
                          fill=theme.BLUE_MID))
    elems.append(pe.shape("qd-haxis", [sc.px(cx - half_w), sc.py(cy),
                                       sc.len(2 * half_w), 1.5], "rect",
                          fill=theme.BLUE_MID))
    # 轴标签
    elems.append(pe.text("qd-yl", [sc.px(cx - 60), sc.py(cy - half_h - 26),
                                   sc.len(120), sc.len(18)],
                         axes.get("y", ""), font_size=max(9, sc.len(12)),
                         color=theme.BLUE, bold=True))
    elems.append(pe.text("qd-xl", [sc.px(cx + half_w - 20), sc.py(cy + 8),
                                   sc.len(120), sc.len(18)],
                         axes.get("x", ""), font_size=max(9, sc.len(12)),
                         color=theme.BLUE, bold=True))
    return elems, sc.len(vb_h)


def render_html(elem):
    st = elem.get("subtype", "")
    body = {"fit_gap": _fit_html, "capability_map": _cmap_html,
            "raci": _raci_html, "crud": _crud_html, "cbm": _cbm_html,
            "quadrant": _quadrant_html}.get(st)
    if not body:
        raise NotImplementedError(f"matrix/{st} 未实现")
    return theme.section_open(elem) + "\n" + body(elem) + "\n" + theme.SECTION_CLOSE


def render_pptd(elem, x, y, w):
    st = elem.get("subtype", "")
    fn = {"fit_gap": _fit_pptd, "capability_map": _cmap_pptd,
          "raci": _raci_pptd, "crud": _crud_pptd, "cbm": _cbm_pptd,
          "quadrant": _quadrant_pptd}.get(st)
    if not fn:
        raise NotImplementedError(f"matrix/{st} 未实现")
    return fn(elem, x, y, w)
