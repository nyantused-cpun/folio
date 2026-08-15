# -*- coding: utf-8 -*-
"""diagram 渲染分发器：subtype -> 具体渲染器（render_html / render_pptd）。

- 27 种子类型已全部实现（flow 5 / architecture 6 / matrix 5 / timeline 2 /
  relationship 9），见 schema.DIAGRAM_SCHEMA 与 dev plan 2026-07-19。
- 未注册 subtype 或任何异常降级为占位卡（dev plan §11.2：不阻断整篇生成，保留标题+desc）。
- product_intro_placeholder 也在这里渲染（HTML 占位卡 / pptd 占位块）。
"""

from . import theme
from .theme import _esc
from . import pptd_emit as pe
from .. import schema
from ..spacing import INSET_X

_MODULES = {}


def _register():
    """惰性装载 P0 渲染器（避免循环 import）。"""
    if _MODULES:
        return
    from . import flow, architecture, matrix, timeline, relationship
    # flow_rows：v2.0 第 28 种子类型（T2 注册分发，T4 落渲染实现；
    # flow.py 入口未加分支前，渲染走异常降级占位卡——显式降级不静默）
    for st in ("sequence", "swimlane", "cross_system", "parallel", "decision",
               "flow_rows"):
        _MODULES[("flow", st)] = flow
    for st in ("4a", "layered", "integration", "biz_overview", "deployment",
               "biz_it_mapping", "platform_hub", "pyramid"):
        _MODULES[("architecture", st)] = architecture
    for st in ("fit_gap", "capability_map", "raci", "crud", "cbm", "quadrant"):
        _MODULES[("matrix", st)] = matrix
    for st in ("horizontal", "vertical", "module_gantt", "milestone_gantt"):
        _MODULES[("timeline", st)] = timeline
    for st in ("org_tree", "er_conceptual", "er_logical", "data_flow",
               "value_chain", "biz_capability_tree",
               "process_service_doc_mapping", "cross_4a_reconcile",
               "automation_table"):
        _MODULES[("relationship", st)] = relationship


def _fallback_html(elem, reason=""):
    """降级占位卡：标题 + desc + 原因，不阻断生成。"""
    title = _esc(elem.get("title", "（未命名图）"))
    desc = _esc(elem.get("desc", ""))
    note = reason or "该图类型暂未实现，待后续版本"
    return (
        f'<section class="diagram" data-diagram-type="{_esc(elem.get("diagram_type", ""))}" '
        f'data-subtype="{_esc(elem.get("subtype", ""))}">'
        f'  <div class="dg-title" data-editable="true">{title}</div>'
        + (f'  <div class="dg-desc" data-editable="true">{desc}</div>' if desc else "")
        + f'  <div style="border:2px dashed {theme.BORDER};border-radius:10px;padding:36px 24px;'
          f'text-align:center;color:{theme.TEXT_SUB};background:{theme.BG};">{_esc(note)}</div>'
          f'</section>')


def _fallback_pptd(elem, x, y, w, reason=""):
    note = reason or "该图类型暂未实现，待后续版本"
    elems = [
        pe.shape("dg-fallback", [x, y, w, 120], "roundRect", fill=theme.BG,
                 border={"style": "dash", "width": 1.5, "color": theme.BORDER},
                 adjustments=[8000]),
        pe.text("dg-fallback-t", [x, y + 16, w, 26], elem.get("title", "（未命名图）"),
                font_size=15, color=theme.TEXT, bold=True),
        pe.text("dg-fallback-d", [x, y + 48, w, 60],
                (elem.get("desc", "") + "\n" if elem.get("desc") else "") + note,
                font_size=12, color=theme.TEXT_SUB),
    ]
    return elems, 120


def _wrap_exhibit(elem, html):
    """exhibit 图框包装（v2.0 §5.5）：编号 + 标题 + 来源行，全 diagram 可用。

    无 exhibit/source 字段时原样返回（零开销）。CSS 在 page_chrome。
    """
    ex = elem.get("exhibit")
    if not isinstance(ex, dict):
        ex = {}
    source = elem.get("source", "")
    if not ex and not source:
        return html
    num = _esc(ex.get("num", ""))
    title = _esc(ex.get("title", ""))
    header = ""
    if num or title:
        header = ('  <div class="exhibit-header">'
                  + (f'<span class="exhibit-num">{num}</span>' if num else "")
                  + (f'<span class="exhibit-title" data-editable="true">{title}</span>'
                     if title else "")
                  + '</div>\n')
    src = ""
    if source:
        src = (f'  <div class="exhibit-source" data-editable="true">'
               f'{_esc(source)}</div>\n')
    return ('<div class="exhibit">\n' + header
            + '  <div class="exhibit-body">\n' + html + '\n  </div>\n'
            + src + '</div>')


# ---------------------------------------------------------------------------
# diagram 附件槽位（D-092 组合感：stats / legend / notes 内嵌 diagram）
# ---------------------------------------------------------------------------

# capability_map 的 stats 是图内统计条（matrix.py 自消费，arms_v5 历史字段），
# D-092 槽位排除该子类型的 stats，避免双重渲染（基线零 diff）
_SLOT_STATS_EXCLUDE = {("matrix", "capability_map")}


def _slot_stats_html(elem):
    """stats 槽位：顶部统计行（复用 stat-card 卡）。"""
    if (elem.get("diagram_type"), elem.get("subtype")) in _SLOT_STATS_EXCLUDE:
        return ""
    stats = elem.get("stats") or []
    if not stats:
        return ""
    cards = "".join(
        f'<div class="stat-card"><div class="stat-value num" data-editable="true">'
        f'{_esc(s.get("value", ""))}<small>{_esc(s.get("unit", ""))}</small></div>'
        f'<div class="stat-label" data-editable="true">{_esc(s.get("label", ""))}</div></div>'
        for s in stats)
    n = max(1, min(len(stats), 6))
    return (f'\n<div class="dg-slot-stats" style="grid-template-columns: repeat({n}, 1fr);">'
            f'{cards}</div>')


def _slot_legend_html(elem):
    """legend 槽位：图例条（复用 legend-bar 构件样式）。"""
    legend = elem.get("legend") or []
    if not legend:
        return ""
    items = "".join(
        f'<span class="legend-item"><i class="legend-swatch sw-{_esc(lt.get("swatch", "lit"))}"></i>'
        f'<span data-editable="true">{_esc(lt.get("label", ""))}</span></span>'
        for lt in legend)
    return f'\n<div class="legend-bar">{items}</div>'


def _slot_notes_html(elem):
    """notes 槽位：底部信息卡（复用 info-card 卡样式，底横排）。"""
    notes = elem.get("notes") or []
    if not notes:
        return ""
    cards = "".join(
        f'<div class="info-card"><div class="info-card-title" data-editable="true">'
        f'{_esc(nt.get("title", ""))}</div>'
        f'<ul class="info-card-list">'
        + "".join(f'<li data-editable="true">{_esc(it)}</li>' for it in nt.get("items", []) or [])
        + '</ul></div>'
        for nt in notes)
    return f'\n<div class="dg-slot-notes">{cards}</div>'


def _wrap_slots(elem, html):
    """diagram 附件槽位包装：stats（图上）+ legend/notes（图下），与图同框成组合体。

    无任何槽位字段时原样返回（零开销，基线零 diff）。槽位 div 与 section.diagram
    同处 .dg-slot-wrap 内，CSS 在 page_chrome。capability_map 的 stats 由图内
    渲染（matrix.py），不算槽位（_SLOT_STATS_EXCLUDE）。
    """
    if (elem.get("diagram_type"), elem.get("subtype")) in _SLOT_STATS_EXCLUDE:
        if not (elem.get("legend") or elem.get("notes")):
            return html
    elif not any(elem.get(k) for k in ("stats", "legend", "notes")):
        return html
    slots = (_slot_stats_html(elem) + _slot_legend_html(elem) + _slot_notes_html(elem))
    return f'<div class="dg-slot-wrap">\n{html}{slots}\n</div>'


def render_diagram_html(elem, style=None):
    """diagram 元素 -> HTML 片段（含校验与降级）。

    style（P2-A2 风格透传）：风格键名，切到该风格色板渲染后恢复原风格；
    None 用当前主题（默认 enterprise，基线零 diff）。
    """
    _register()
    prev = theme.current_style_name()
    if style is not None:
        theme.use_style(style)
    try:
        errors = schema.validate_element(elem)
        if errors:
            print(f"[diagram] 元素校验未过，降级占位: {'; '.join(errors)}")
            return _fallback_html(elem, "spec 校验未过：" + errors[0])
        mod = _MODULES.get((elem.get("diagram_type"), elem.get("subtype")))
        if not mod:
            return _fallback_html(elem)
        try:
            return _wrap_slots(elem, _wrap_exhibit(elem, mod.render_html(elem)))
        except Exception as e:
            print(f"[diagram] {elem.get('diagram_type')}/{elem.get('subtype')} HTML 渲染异常降级: {e}")
            return _fallback_html(elem, f"渲染异常：{e}")
    finally:
        if style is not None:
            theme.use_style(prev)


def render_slots_pptd(elem, x, y, w, theme_name=None):
    """diagram 附件槽位 pptd：stats 行 + legend 条 + notes 卡。

    返回 (元素列表, 消耗高度)。图渲染后调用，y 从图底开始推进；
    元素走调用方 uid 唯一化（render_diagram_pptd 内），id 前缀 slot-。
    """
    c = pe._v2c(theme_name)
    elems, cy = [], 0.0
    is_cmap = (elem.get("diagram_type"), elem.get("subtype")) in _SLOT_STATS_EXCLUDE
    stats = [] if is_cmap else (elem.get("stats") or [])
    if stats:
        gap = 14.0
        cw = (w - gap * (len(stats) - 1)) / len(stats)
        for i, s in enumerate(stats):
            sx = x + i * (cw + gap)
            elems.append(pe.shape(f"slot-st{i}", [sx, y + cy, cw, 52], "roundRect",
                                  fill=c["card"], adjustments=[8000],
                                  border={"style": "solid", "width": 1, "color": c["border"]}))
            # 左侧 4px 主色条（与 HTML stat-card border-left 视觉统一；顶部 3px
            # 条曾与数字文字吸附贴线触发 pyz TextDrift/TextContrast 误报）
            elems.append(pe.shape(f"slot-st{i}-bar", [sx, y + cy, 4, 52], "rect",
                                  fill=c["primary"]))
            elems.append(pe.text(f"slot-st{i}-n", [sx + 12, y + cy + 4, cw - 18, 26],
                                 str(s.get("value", "")), font_size=18,
                                 color=c["primary"], bold=True))
            elems.append(pe.text(f"slot-st{i}-l", [sx + 12, y + cy + 32, cw - 18, 16],
                                 s.get("label", ""), font_size=9,
                                 color=c["text_secondary"]))
        cy += 52 + 12
    legend = elem.get("legend") or []
    if legend:
        lh = 26
        sw = {"lit": c["lit_border"], "part": c["part_border"],
              "gap": c["gap_border"], "keep": c["text_tertiary"]}.get
        elems.append(pe.shape("slot-lg-bg", [x, y + cy, w, lh], "roundRect",
                              fill=c["bg_soft"], adjustments=[6000],
                              border={"style": "solid", "width": 1, "color": c["border"]}))
        ix = x + 14
        for i, lt in enumerate(legend):
            sw_c = sw(lt.get("swatch", "lit"), c["primary"])
            label = lt.get("label", "")
            # label 文本框宽按实际文本估算（固定 200 曾与下一色块相交，lint
            # badge_overlap 判定色块 100% 在文本框内，I-1 徽章压标题特征）；
            # 预留 text() 内边距折算（2×INSET_X）避免估算 2 行触发 text_overflow
            tw = pe.est_text_w(label, 10) + 2 * INSET_X + 4
            elems.append(pe.shape(f"slot-lg{i}", [ix, y + cy + 6, 14, 14], "rect",
                                  fill=sw_c))
            elems.append(pe.text(f"slot-lg{i}-t", [ix + 20, y + cy + 2, tw, 20],
                                 label, font_size=10,
                                 color=c["text_secondary"], align=("left", "middle")))
            ix += 20 + tw + 6
        cy += lh + 12
    notes = elem.get("notes") or []
    if notes:
        nw = (w - 12 * (len(notes) - 1)) / len(notes)
        for i, nt in enumerate(notes):
            nx = x + i * (nw + 12)
            items_txt = "\n".join(nt.get("items", []) or [])
            elems.append(pe.shape(f"slot-nt{i}", [nx, y + cy, nw, 68], "roundRect",
                                  fill=c["card"], adjustments=[8000],
                                  border={"style": "solid", "width": 1, "color": c["border"]}))
            elems.append(pe.text(f"slot-nt{i}-t", [nx + 10, y + cy + 5, nw - 20, 16],
                                 nt.get("title", ""), font_size=11,
                                 color=c["text_primary"], bold=True,
                                 align=("left", "middle")))
            elems.append(pe.text(f"slot-nt{i}-b", [nx + 10, y + cy + 23, nw - 20, 42],
                                 items_txt, font_size=9,
                                 color=c["text_secondary"], align=("left", "top")))
        cy += 68
    return elems, cy


def render_diagram_pptd(elem, x, y, w, style=None, v2_theme=None):
    """diagram 元素 -> (pptd 元素列表, 消耗高度)。

    style（P2-A2 风格透传）：同 render_diagram_html。
    v2_theme（v2.0 §5.1）：v2 主题包名，flow_rows 取色用；None → legacy。
    """
    _register()
    prev = theme.current_style_name()
    if style is not None:
        theme.use_style(style)
    try:
        errors = schema.validate_element(elem)
        if errors:
            print(f"[diagram-pptd] 元素校验未过，降级占位: {'; '.join(errors)}")
            return _fallback_pptd(elem, x, y, w, "spec 校验未过：" + errors[0])
        mod = _MODULES.get((elem.get("diagram_type"), elem.get("subtype")))
        if not mod:
            return _fallback_pptd(elem, x, y, w)
        try:
            if (elem.get("diagram_type"), elem.get("subtype")) in (
                    ("flow", "flow_rows"), ("architecture", "biz_overview")):
                # flow_rows：v2 主题角色色板；biz_overview：D-092 三态
                # tone 映射（lit/part/keep 与图例槽位 swatch 同源）
                elems, h = mod.render_pptd(elem, x, y, w, theme_name=v2_theme)
            else:
                elems, h = mod.render_pptd(elem, x, y, w)
        except Exception as e:
            print(f"[diagram-pptd] {elem.get('diagram_type')}/{elem.get('subtype')} 渲染异常降级: {e}")
            return _fallback_pptd(elem, x, y, w, f"渲染异常：{e}")
        # D-092 附件槽位：stats/legend/notes 追加在图后，与图同组（同 uid 前缀）
        slot_elems, slot_h = render_slots_pptd(elem, x, y + h, w, theme_name=v2_theme)
        if slot_elems:
            elems.extend(slot_elems)
            h += slot_h
        # 同页多图时 elementId 唯一化（pptd check DuplicateIdError，y 游标必不同）
        uid = f"dg{int(y)}"
        for el in elems:
            el["elementId"] = f"{uid}-{el['elementId']}"
        return elems, h
    finally:
        if style is not None:
            theme.use_style(prev)


# ---------------------------------------------------------------------------
# product_intro_placeholder（D-089）
# ---------------------------------------------------------------------------

def render_placeholder_html(elem, style=None):
    """产品介绍占位卡（HTML）。style：P2-A2 风格透传，同 render_diagram_html。"""
    prev = theme.current_style_name()
    if style is not None:
        theme.use_style(style)
    try:
        title = _esc(elem.get("title", "产品介绍"))
        hint = _esc(elem.get("hint", "在此处插入客户产品介绍页"))
        kws = elem.get("keywords", []) or []
        chips = "".join(
            f'<span style="display:inline-block;background:{theme.BLUE_LIGHT};color:{theme.BLUE};'
            f'border-radius:4px;padding:3px 10px;font-size:12px;font-weight:600;margin:0 6px 4px 0;">{_esc(k)}</span>'
            for k in kws)
        return (
            f'<section class="diagram product-intro-placeholder" data-subtype="product_intro">'
            f'  <div style="border:2px dashed {theme.BLUE_MID};border-radius:12px;padding:44px 28px;'
            f'text-align:center;background:{theme.BLUE_LIGHT};">'
            f'  <div style="font-size:20px;font-weight:700;color:{theme.BLUE};" data-editable="true">{title}</div>'
            f'  <div style="font-size:13px;color:{theme.TEXT_SUB};margin-top:10px;" data-editable="true">{hint}</div>'
            + (f'  <div style="margin-top:16px;">{chips}</div>' if chips else "")
            + '</div></section>')
    finally:
        if style is not None:
            theme.use_style(prev)


def render_placeholder_pptd(elem, x, y, w, style=None):
    """产品介绍占位块（pptd）：虚线框 + 标题 + 提示。style：P2-A2 风格透传。"""
    prev = theme.current_style_name()
    if style is not None:
        theme.use_style(style)
    try:
        elems = [
            pe.shape("p-intro", [x, y, w, 200], "roundRect", fill=theme.BLUE_LIGHT,
                     border={"style": "dash", "width": 1.5, "color": theme.BLUE_MID},
                     adjustments=[8000]),
            pe.text("p-intro-t", [x, y + 60, w, 34], elem.get("title", "产品介绍"),
                    font_size=20, color=theme.BLUE, bold=True),
            pe.text("p-intro-h", [x, y + 104, w, 22], elem.get("hint", "在此处插入客户产品介绍页"),
                    font_size=13, color=theme.TEXT_SUB),
        ]
        kws = " / ".join(str(k) for k in elem.get("keywords", []) or [])
        if kws:
            elems.append(pe.text("p-intro-k", [x, y + 136, w, 20], kws,
                                 font_size=11, color=theme.BLUE_MID))
        # 同页多个占位块时 elementId 唯一化
        uid = f"pi{int(y)}"
        for el in elems:
            el["elementId"] = f"{uid}-{el['elementId']}"
        return elems, 200
    finally:
        if style is not None:
            theme.use_style(prev)
