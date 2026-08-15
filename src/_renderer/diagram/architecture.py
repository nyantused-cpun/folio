# -*- coding: utf-8 -*-
"""architecture 类渲染器：4a / layered / integration / biz_overview / deployment / biz_it_mapping（6 种全部实现）。

HTML：div 层叠行（左层标签色块 + 右卡体 chip），inline style 自包含。
pptd：层标签 shape + 卡体 shape + chip 流（emit_chips），全原生对象。

spec：
  4a:      layers: [{name, desc, components: []}]（BA/AA/DA/TA 四层，固定配色）
  layered: layers: [{name, desc, components: []}]（层色循环 蓝→绿→青→紫→灰）
"""

from . import theme
from .theme import _esc
from . import pptd_emit as pe
from ..spacing import GAP_MD, GAP_SM, INSET_X, INSET_Y

# 4a 固定层色（按层名关键字匹配，缺省循环）；调用时取 theme（P2-A2 风格透传，
# 模块级快照会在 use_style 切换后滞留旧色板）
def _4a_colors():
    return {"BA": theme.BLUE, "业务": theme.BLUE,
            "AA": theme.GREEN, "应用": theme.GREEN,
            "DA": theme.PURPLE, "数据": theme.PURPLE,
            "TA": theme.TEAL, "技术": theme.TEAL}


def _layer_color(index, name, fixed_4a):
    if fixed_4a:
        for key, c in _4a_colors().items():
            if key in name:
                return c
    return theme.LAYER_COLORS[index % len(theme.LAYER_COLORS)]


def _chip_css(color_key):
    return {"b": (theme.BLUE_LIGHT, theme.BLUE), "g": (theme.GREEN_LIGHT, theme.GREEN),
            "t": (theme.TEAL_LIGHT, theme.TEAL), "p": (theme.PURPLE_LIGHT, theme.PURPLE),
            "w": (theme.WHITE, theme.TEXT_SUB)}[color_key]


def _layer_rows(elem):
    rows = []
    fixed = elem.get("subtype") == "4a"
    for i, ly in enumerate(elem.get("layers", []) or []):
        name = ly.get("name", "")
        rows.append({
            "name": name,
            "desc": ly.get("desc", ""),
            "components": [str(c) for c in ly.get("components", []) or []],
            "color": _layer_color(i, name, fixed),
        })
    return rows


# ---------------------------------------------------------------------------
# P1：integration / biz_overview / deployment / biz_it_mapping
# ---------------------------------------------------------------------------

def _intg_html(elem):
    """integration：点对点双卡 + 箭头列；hub 形态走总线放射。"""
    if elem.get("hub"):
        return _intg_hub_html(elem)
    src = elem.get("source", {}) or {}
    tgt = elem.get("target", {}) or {}
    links = elem.get("links", []) or [{"label": elem.get("interface", "API"), "mode": "sync"}]
    def _item_text(i):
        return i.get("name", "") if isinstance(i, dict) else str(i)
    src_items = "".join(f'<div style="background:{theme.BG};border-left:3px solid {theme.BLUE};border-radius:6px;'
                        f'padding:9px 12px;font-size:13px;margin-bottom:8px;" data-editable="true">{_esc(_item_text(i))}</div>'
                        for i in src.get("items", []) or [])
    tgt_items = "".join(f'<div style="background:{theme.BG};border-left:3px solid {theme.GREEN};border-radius:6px;'
                        f'padding:9px 12px;font-size:13px;margin-bottom:8px;" data-editable="true">{_esc(_item_text(i))}</div>'
                        for i in tgt.get("items", []) or [])
    arrows = "".join(
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;margin:6px 0;">'
        f'<div style="font-size:12px;font-weight:700;color:{theme.BLUE};" data-editable="true">{_esc(link.get("label", ""))}</div>'
        f'<div style="color:{theme.BLUE};font-size:22px;line-height:1;">{"⟷" if link.get("mode") == "bidirectional" else ("⇢" if link.get("mode") == "async" else "→")}</div>'
        f'<div style="font-size:11px;color:{theme.TEXT_SUB};">{ {"sync": "同步", "async": "异步", "bidirectional": "双向"}.get(link.get("mode", "sync"), "同步") }</div></div>'
        for link in links)
    return (f'<div style="display:grid;grid-template-columns:1fr 150px 1fr;gap:18px;align-items:stretch;">'
            f'<div style="background:{theme.CARD};border:1px solid {theme.BORDER};border-top:4px solid {theme.BLUE};border-radius:10px;padding:18px 20px;">'
            f'<div style="font-weight:700;font-size:15px;text-align:center;color:{theme.BLUE};padding-bottom:10px;margin-bottom:12px;border-bottom:2px solid {theme.BORDER};" data-editable="true">{_esc(src.get("name", "源系统"))}</div>{src_items}</div>'
            f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;">{arrows}</div>'
            f'<div style="background:{theme.CARD};border:1px solid {theme.BORDER};border-top:4px solid {theme.GREEN};border-radius:10px;padding:18px 20px;">'
            f'<div style="font-weight:700;font-size:15px;text-align:center;color:{theme.GREEN};padding-bottom:10px;margin-bottom:12px;border-bottom:2px solid {theme.BORDER};" data-editable="true">{_esc(tgt.get("name", "目标系统"))}</div>{tgt_items}</div>'
            f'</div>')


def _intg_hub_edge(cx, cy, sx, sy, hw=85, hh=26):
    """integration 总线：hub 中心到系统框（半宽 hw、半高 hh）边缘的交点。

    连接线止于系统框边缘，不穿框内文字（§10 检查 8）。
    """
    import math
    dx, dy = sx - cx, sy - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return sx, sy
    ux, uy = dx / dist, dy / dist
    tx = hw / abs(ux) if abs(ux) > 1e-9 else float("inf")
    ty = hh / abs(uy) if abs(uy) > 1e-9 else float("inf")
    t = min(tx, ty)
    return sx - ux * t, sy - uy * t


def _intg_hub_html(elem):
    """integration 总线型：中央 hub + 四周系统放射（SVG）。"""
    hub = elem.get("hub", {}) or {}
    systems = elem.get("systems", []) or []
    n = len(systems)
    # 圆周布局：hub 中心 600,210；系统框 180×56
    import math
    cx, cy, r = 600, 210, 175
    parts = ['<svg class="dg" viewBox="0 0 1200 420" xmlns="http://www.w3.org/2000/svg">']
    pts = []
    for i, s in enumerate(systems):
        ang = -math.pi / 2 + 2 * math.pi * i / max(1, n)
        sx = cx + r * 1.75 * math.cos(ang)
        sy = cy + r * math.sin(ang)
        pts.append((sx, sy, s))
    for sx, sy, _s in pts:
        ex, ey = _intg_hub_edge(cx, cy, sx, sy)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{theme.BLUE_MID}" stroke-width="1.8"/>')
    parts.append(f'<rect x="{cx - 140}" y="{cy - 40}" width="280" height="80" rx="10" fill="{theme.BLUE}"/>')
    parts.append(f'<text x="{cx}" y="{cy - 4}" font-size="15" font-weight="700" fill="{theme.WHITE}" text-anchor="middle" data-editable="true">{_esc(hub.get("name", "ESB 总线"))}</text>')
    if hub.get("desc"):
        parts.append(f'<text x="{cx}" y="{cy + 20}" font-size="11" fill="rgba(255,255,255,0.75)" text-anchor="middle">{_esc(hub["desc"])}</text>')
    for sx, sy, s in pts:
        name = s.get("name", "") if isinstance(s, dict) else str(s)
        parts.append(f'<rect x="{sx - 85}" y="{sy - 26}" width="170" height="52" rx="8" fill="{theme.WHITE}" stroke="{theme.BLUE}" stroke-width="1.5"/>')
        parts.append(f'<text x="{sx}" y="{sy + 4}" font-size="13" font-weight="600" fill="{theme.TEXT}" text-anchor="middle" data-editable="true">{_esc(name)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _biz_overview_html(elem):
    """biz_overview：战略横带 + 业务域容器 + 支撑带。"""
    strategy = elem.get("strategy", "")
    band = ""
    if strategy:
        band = (f'<div style="background:{theme.BLUE};border-radius:10px;color:{theme.WHITE};text-align:center;'
                f'padding:14px;font-weight:700;font-size:15px;margin-bottom:14px;" data-editable="true">{_esc(strategy)}</div>')
    def _tone_pair(d):
        """biz_overview domain 三态 -> (bg, fg) CSS 变量对。

        D-092 组合感：与图例槽位 swatch 同源（.sw-lit/.sw-part/.sw-keep 定义
        即 --t-lit-bg 等），图内卡与图例色码一一对应。无 tone/未知 -> 历史
        缺省蓝（基线零 diff）。
        """
        return {
            "lit": ("var(--t-lit-bg)", "var(--t-lit-border)"),
            "part": ("var(--t-part-bg)", "var(--t-part-border)"),
            "keep": ("var(--t-bg-muted)", "var(--t-text-tertiary)"),
        }.get(d.get("tone", ""), (theme.BLUE_LIGHT, theme.BLUE))

    domains = elem.get("domains", []) or []
    cols = max(1, len(domains))
    dom_html = "".join(
        f'<div style="background:{_tone_pair(d)[0]};border-radius:10px;padding:16px;">'
        f'<div style="font-weight:700;color:{_tone_pair(d)[1]};margin-bottom:8px;text-align:center;" data-editable="true">{_esc(d.get("name", ""))}</div>'
        + "".join(f'<span style="display:inline-block;background:{theme.WHITE};color:{_tone_pair(d)[1]};border-radius:4px;'
                  f'padding:4px 10px;font-size:12px;font-weight:600;margin:3px 4px 3px 0;" data-editable="true">{_esc(c)}</span>'
                  for c in d.get("components", []) or [])
        + '</div>'
        for d in domains)
    support = elem.get("support", []) or []
    sup_html = ""
    if support:
        sup_html = (f'<div style="background:{theme.GREEN_LIGHT};border-radius:10px;padding:12px 16px;margin-top:14px;">'
                    f'<span style="font-weight:700;color:{theme.GREEN};margin-right:12px;">管理支撑</span>'
                    + "".join(f'<span style="display:inline-block;background:{theme.WHITE};color:{theme.GREEN};border-radius:4px;'
                              f'padding:4px 10px;font-size:12px;font-weight:600;margin:3px 4px 3px 0;" data-editable="true">{_esc(s)}</span>'
                              for s in support) + '</div>')
    return band + f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:14px;">{dom_html}</div>' + sup_html


def _deploy_html(elem):
    """deployment：分区嵌套容器 + 节点级跨区连线（SVG）。"""
    zones = elem.get("zones", []) or []
    links = elem.get("links", []) or []
    n = len(zones)
    zone_w = (1200 - 80 - 40 * (n - 1)) / max(1, n)
    zone_rects = []
    zone_node_rects = {}  # zone_name -> node_name -> (x, y, w, h)
    for i, z in enumerate(zones):
        zname = z.get("name", "")
        zx = 40 + i * (zone_w + 40)
        nodes = z.get("nodes", []) or []
        zh = 60 + max(1, len(nodes)) * 84 + 20
        zone_rects.append((zname, zx, 40, zone_w, zh))
        zone_node_rects[zname] = {}
        for k, nd in enumerate(nodes):
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            ny = 40 + 50 + k * 84
            zone_node_rects[zname][nd_name] = (zx + 24, ny, zone_w - 48, 64)
    max_h = max((z[4] for z in zone_rects), default=140)
    parts = [f'<svg class="dg" viewBox="0 0 1200 {max_h + 100}" xmlns="http://www.w3.org/2000/svg">',
             f'<defs>'
             f'<marker id="dg-arr" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="{theme.BLUE_MID}"/></marker>'
             f'<marker id="dg-arr-async" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="{theme.PURPLE}"/></marker>'
             f'<marker id="dg-arr-sync" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#1E3A8A"/></marker>'
             f'</defs>']

    def _node_rect(ref):
        """'Zone.Node' -> (x, y, w, h)；'Zone' 或未命中返回 None。"""
        if "." in ref:
            zone_name, node_name = ref.split(".", 1)
            return zone_node_rects.get(zone_name, {}).get(node_name)
        return None

    def _zone_center(ref):
        z = next((zz for zz in zone_rects if zz[0] == ref), None)
        if z:
            return z[1] + z[3] / 2, z[2] + z[4] / 2
        return None

    OUT = 3    # 出口线头外移（露出框外）
    IN = 8     # 入口箭头外移（marker 宽 10，让箭头主体全露出）

    # 1) 画 zone 容器背景（最底层，fill 不透明会盖住更早画的元素）
    for name, zx, zy, zw, zh in zone_rects:
        parts.append(f'<rect x="{zx}" y="{zy}" width="{zw}" height="{zh}" rx="12" fill="{theme.BG}" stroke="{theme.BORDER_STRONG}" stroke-width="1.5"/>')
        parts.append(f'<text x="{zx + 20}" y="{zy + 28}" font-size="14" font-weight="700" fill="{theme.TEXT_STRONG}" data-editable="true">{_esc(name)}</text>')

    # 2) 画连线（在 zone 背景之上、节点框之下）
    for link in links:
        fr, to = link.get("from", ""), link.get("to", "")
        ra, rb = _node_rect(fr), _node_rect(to)
        mode = link.get("mode", "sync")
        stroke = theme.PURPLE if mode == "async" else "#1E3A8A"
        dash = ' stroke-dasharray="6,4"' if mode == "async" else ""
        marker = "url(#dg-arr-async)" if mode == "async" else "url(#dg-arr-sync)"

        if ra and rb:
            ax1, ay1, aw1, ah1 = ra
            bx1, by1, bw1, bh1 = rb
            if ax1 == bx1:
                # 同列（同 zone）：from 底边出 -> to 顶边进，垂直连线
                sx1, sy1 = ax1 + aw1 / 2, ay1 + ah1 + OUT
                sx2, sy2 = bx1 + bw1 / 2, by1 - IN
                c1x, c1y = ax1 + aw1 / 2, (sy1 + sy2) / 2
                c2x, c2y = bx1 + bw1 / 2, (sy1 + sy2) / 2
            else:
                # 不同列：from 右缘出 -> to 左缘进，横向贝塞尔
                sx1, sy1 = ax1 + aw1 + OUT, ay1 + ah1 / 2
                sx2, sy2 = bx1 - IN, by1 + bh1 / 2
                c1x, c1y = ax1 + aw1 + OUT + (sx2 - sx1) * 0.4, ay1 + ah1 / 2
                c2x, c2y = sx2 - (sx2 - sx1) * 0.4, by1 + bh1 / 2
        else:
            a = _zone_center(fr)
            b = _zone_center(to)
            if not a or not b:
                continue
            sx1, sy1 = a
            sx2, sy2 = b
            c1x, c1y = sx1 + (sx2 - sx1) * 0.4, sy1
            c2x, c2y = sx2 - (sx2 - sx1) * 0.4, sy2
        parts.append(f'<path d="M{sx1},{sy1} C{c1x},{c1y} {c2x},{c2y} {sx2},{sy2}" stroke="{stroke}" stroke-width="1.8" fill="none"{dash} marker-end="{marker}"/>')
        if link.get("label"):
            lx = (sx1 + sx2) / 2
            ly = (sy1 + sy2) / 2 - 8
            parts.append(f'<text x="{lx}" y="{ly}" font-size="10" fill="{stroke}" text-anchor="middle" font-weight="600">{_esc(link["label"])}</text>')

    # 3) 画节点（最顶层，盖住连线穿过节点的部分；端点已外移，线头/箭头露在框外）
    for name, zx, zy, zw, _zh in zone_rects:
        z = next(zz for zz in zones if zz.get("name", "") == name)
        for k, nd in enumerate(z.get("nodes", []) or []):
            ny = zy + 50 + k * 84
            parts.append(f'<rect x="{zx + 24}" y="{ny}" width="{zw - 48}" height="64" rx="8" fill="{theme.WHITE}" stroke="{theme.BLUE}" stroke-width="1.5"/>')
            parts.append(f'<rect x="{zx + 24}" y="{ny}" width="5" height="64" rx="2" fill="{theme.BLUE}"/>')
            parts.append(f'<text x="{zx + zw / 2}" y="{ny + 28}" font-size="13" font-weight="600" text-anchor="middle" data-editable="true">{_esc(nd.get("name", ""))}</text>')
            if nd.get("desc"):
                parts.append(f'<text x="{zx + zw / 2}" y="{ny + 48}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle">{_esc(nd["desc"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _mapping_html(elem):
    """biz_it_mapping：4 列映射表（能力｜流程｜系统｜数据）。"""
    rows = []
    for m in elem.get("mappings", []) or []:
        def chips(items, bg, fg):
            return "".join(f'<span style="display:inline-block;background:{bg};color:{fg};border-radius:4px;'
                           f'padding:3px 9px;font-size:12px;font-weight:600;margin:2px 4px 2px 0;" data-editable="true">{_esc(i)}</span>'
                           for i in items or [])
        rows.append(
            f'<tr><td style="background:{theme.BLUE};color:{theme.WHITE};font-weight:700;" data-editable="true">{_esc(m.get("biz_capability", ""))}</td>'
            f'<td>{chips(m.get("biz_processes"), theme.BLUE_LIGHT, theme.BLUE)}</td>'
            f'<td>{chips(m.get("it_systems"), theme.GREEN_LIGHT, theme.GREEN)}</td>'
            f'<td>{chips(m.get("data_entities"), theme.PURPLE_LIGHT, theme.PURPLE)}</td></tr>')
    return (f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            f'<thead><tr style="background:{theme.BLUE};color:{theme.WHITE};">'
            f'<th style="padding:6px 10px;text-align:left;width:18%;">业务能力</th>'
            f'<th style="padding:6px 10px;text-align:left;width:30%;">业务流程</th>'
            f'<th style="padding:6px 10px;text-align:left;width:26%;">IT 系统</th>'
            f'<th style="padding:6px 10px;text-align:left;width:26%;">数据实体</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            f'<style>section.diagram[data-subtype="biz_it_mapping"] td{{padding:6px 10px;border-bottom:1px solid {theme.BORDER};vertical-align:top;}}'
            f'section.diagram[data-subtype="biz_it_mapping"] tr:hover td{{background:{theme.BLUE_LIGHT};}}'
            f'section.diagram[data-subtype="biz_it_mapping"] tr:hover td:first-child{{background:{theme.BLUE};}}</style>')


# ---------------------------------------------------------------------------
# P1 pptd
# ---------------------------------------------------------------------------

def _intg_pptd(elem, x, y, w):
    if elem.get("hub"):
        return _intg_hub_pptd(elem, x, y, w)
    sc = pe.PptdScaler(x, y, w)
    src = elem.get("source", {}) or {}
    tgt = elem.get("target", {}) or {}
    links = elem.get("links", []) or [{"label": elem.get("interface", "API"), "mode": "sync"}]
    elems = []
    card_h = max(200, 70 + max(len(src.get("items", []) or []), len(tgt.get("items", []) or [])) * 34)
    side_w = (1200 - 150 - 2 * 40) / 2
    for side, data, color in (("src", src, theme.BLUE), ("tgt", tgt, theme.GREEN)):
        sx = sc.px(40 if side == "src" else 40 + side_w + 150)
        elems.append(pe.shape(f"intg-{side}", [sx, y, sc.len(side_w), sc.len(card_h)], "roundRect",
                              fill=theme.CARD, adjustments=[5000],
                              border={"style": "solid", "width": 1, "color": theme.BORDER}))
        elems.append(pe.shape(f"intg-{side}-top", [sx, y, sc.len(side_w), sc.len(4)], "rect", fill=color))
        elems.append(pe.text(f"intg-{side}-h", [sx, y + sc.len(12), sc.len(side_w), sc.len(24)],
                             data.get("name", ""), font_size=max(11, sc.len(15)), color=color,
                             bold=True))
        for k, item in enumerate(data.get("items", []) or []):
            item_text = item.get("name", "") if isinstance(item, dict) else str(item)
            iy = y + sc.len(50 + k * 34)
            elems.append(pe.shape(f"intg-{side}-i{k}", [sx + sc.len(16), iy, sc.len(side_w - 32), sc.len(26)],
                                  "roundRect", fill=theme.BG, adjustments=[12000]))
            elems.append(pe.shape(f"intg-{side}-i{k}-bar", [sx + sc.len(16), iy, sc.len(3), sc.len(26)],
                                  "rect", fill=color))
            elems.append(pe.text(f"intg-{side}-i{k}-t", [sx + sc.len(26), iy, sc.len(side_w - 46), sc.len(26)],
                                 item_text, font_size=max(9, sc.len(12)), color=theme.TEXT,
                                 align=("left", "middle")))
    # 中间箭头列
    single_sync = len(links) == 1 and links[0].get("mode", "sync") == "sync"
    for k, link in enumerate(links):
        mode = link.get("mode", "sync")
        ay = y + sc.len(card_h / 2 - 20 + k * 40)
        ax1 = sc.px(40 + side_w + 12)
        ax2 = sc.px(40 + side_w + 150 - 12)
        both = mode == "bidirectional"
        if single_sync:
            # 实心方向：单向主集成用块箭头 preset（D-2 块箭头扩充）；
            # 多 link / 双向 / 异步仍走 connector（细关系，需 dash/双箭头）
            elems.append(pe.block_arrow(f"intg-arr{k}",
                                        [ax1, ay - sc.len(12), ax2 - ax1, sc.len(24)],
                                        "rightArrow", fill=theme.BLUE))
        else:
            elems.append(pe.connector(f"intg-arr{k}", ax1, ay, ax2, ay,
                                      arrow=("arrow" if both else "none", "arrow"),
                                      color=theme.BLUE, dash=(mode == "async")))
        elems.append(pe.text(f"intg-arr{k}-l", [ax1 - sc.len(20), ay - sc.len(26), ax2 - ax1 + sc.len(40), sc.len(20)],
                             link.get("label", ""), font_size=max(8, sc.len(11)), color=theme.BLUE,
                             bold=True))
    return elems, sc.len(card_h)


def _intg_hub_pptd(elem, x, y, w):
    import math
    sc = pe.PptdScaler(x, y, w)
    hub = elem.get("hub", {}) or {}
    systems = elem.get("systems", []) or []
    n = len(systems)
    cx, cy, r = 600, 210, 175
    elems = []
    pts = []
    for i, s in enumerate(systems):
        ang = -math.pi / 2 + 2 * math.pi * i / max(1, n)
        pts.append((cx + r * 1.75 * math.cos(ang), cy + r * math.sin(ang),
                    s.get("name", "") if isinstance(s, dict) else str(s)))
    for sx, sy, name in pts:
        ex, ey = _intg_hub_edge(cx, cy, sx, sy)
        elems.append(pe.connector(f"hub-l-{name}", sc.px(cx), sc.py(cy), sc.px(ex), sc.py(ey),
                                  arrow=("none", "none"), color=theme.BLUE_MID))
    elems.append(pe.shape("hub", [sc.px(cx - 140), sc.py(cy - 40), sc.len(280), sc.len(80)],
                          "roundRect", fill=theme.BLUE, adjustments=[10000]))
    elems.append(pe.text("hub-t", [sc.px(cx - 140), sc.py(cy - 24), sc.len(280), sc.len(26)],
                         hub.get("name", "ESB 总线"), font_size=max(12, sc.len(15)),
                         color=theme.WHITE, bold=True))
    if hub.get("desc"):
        elems.append(pe.text("hub-d", [sc.px(cx - 140), sc.py(cy + 2), sc.len(280), sc.len(36)],
                             hub["desc"], font_size=max(8, sc.len(10)), color=theme.WHITE))
    for sx, sy, name in pts:
        elems.append(pe.shape(f"hub-s-{name}", [sc.px(sx - 85), sc.py(sy - 26), sc.len(170), sc.len(52)],
                              "roundRect", fill=theme.CARD, adjustments=[8000],
                              border={"style": "solid", "width": 1.5, "color": theme.BLUE}))
        elems.append(pe.text(f"hub-st-{name}", [sc.px(sx - 85), sc.py(sy - 26), sc.len(170), sc.len(52)],
                             name, font_size=max(10, sc.len(13)), color=theme.TEXT, bold=True))
    return elems, sc.len(420)


def _biz_overview_pptd(elem, x, y, w, theme_name=None):
    sc = pe.PptdScaler(x, y, w)
    elems = []
    c = pe._v2c(theme_name)
    cy = 0.0
    if elem.get("strategy"):
        elems.append(pe.shape("bo-str", [x, y, w, sc.len(56)], "roundRect", fill=theme.BLUE,
                              adjustments=[10000]))
        elems.append(pe.text("bo-str-t", [x, y, w, sc.len(56)], elem["strategy"],
                             font_size=max(11, sc.len(15)), color=theme.WHITE, bold=True))
        cy += 56 + 14
    domains = elem.get("domains", []) or []
    cols = max(1, len(domains))
    dom_w = (1200 - 14 * (cols - 1)) / cols
    dom_h_px = 0.0
    for i, d in enumerate(domains):
        dx = sc.px(i * (dom_w + 14))
        comps = d.get("components", []) or []
        # D-092 三态：lit=绿（CRM 主做）/ part=橙（对侧系统做）/ keep=灰
        # （同步桥梁），取 v2 主题 tokens 与图例槽位 swatch 同源；无 tone/
        # 未知 -> 历史缺省蓝（基线零 diff）。chips 白底 fg 色与 HTML 同款。
        tone = d.get("tone", "")
        if tone == "lit":
            bg, fg = c["lit_bg"], c["lit_border"]
        elif tone == "part":
            bg, fg = c["part_bg"], c["part_border"]
        elif tone == "keep":
            bg, fg = c["bg_muted"], c["text_tertiary"]
        else:
            bg, fg = theme.BLUE_LIGHT, theme.BLUE
        # 先排 chips 拿实际消耗高度，再定域框高：估算行数（len/3）会低估
        # 宽度换行，导致支撑带/后续元素压 chip（lint I-2）
        chip_elems, used = pe.emit_chips(f"bo-d{i}", comps, dx + sc.len(12),
                                         y + sc.len(cy + 38), sc.len(dom_w - 24),
                                         font_size=max(8, sc.len(11)),
                                         fill=None if not tone else c["card"],
                                         color=fg)
        dh_px = sc.len(38) + used + sc.len(12)
        dom_h_px = max(dom_h_px, dh_px)
        elems.append(pe.shape(f"bo-d{i}", [dx, y + sc.len(cy), sc.len(dom_w), dh_px],
                              "roundRect", fill=bg, adjustments=[8000]))
        elems.append(pe.text(f"bo-d{i}-t", [dx, y + sc.len(cy + 10), sc.len(dom_w), sc.len(22)],
                             d.get("name", ""), font_size=max(10, sc.len(14)), color=fg,
                             bold=True))
        elems.extend(chip_elems)
    cy += dom_h_px / sc.scale + 14
    support = elem.get("support", []) or []
    if support:
        chip_elems, sup_used = pe.emit_chips("bo-sup", support, x + sc.len(130),
                                             y + sc.len(cy + 12), w - sc.len(140),
                                             font_size=max(8, sc.len(11)),
                                             fill=theme.WHITE, color=theme.GREEN)
        band_h = max(sc.len(48), sup_used + sc.len(24))
        elems.append(pe.shape("bo-sup", [x, y + sc.len(cy), w, band_h], "roundRect",
                              fill=theme.GREEN_LIGHT, adjustments=[10000]))
        elems.append(pe.text("bo-sup-t", [x + sc.len(14), y + sc.len(cy), sc.len(110), band_h],
                             "管理支撑", font_size=max(9, sc.len(13)), color=theme.GREEN,
                             bold=True, align=("left", "middle")))
        elems.extend(chip_elems)
        cy += band_h / sc.scale
    return elems, sc.len(cy)


def _deploy_pptd(elem, x, y, w):
    """deployment：与 _deploy_html 同源的节点级跨区连线（双端对称，D-115）。

    连线几何与 HTML 端共用同一套 1200 坐标系规则：
    - from/to 支持 'Zone.Node' 节点级引用（含 '.' 拆分）与纯 'Zone' 退化（zone 中心）；
    - 同列节点：底边出 -> 顶边进（垂直）；不同列：右缘出 -> 左缘进（横向）；
    - mode: async=紫色虚线 / sync=深蓝实线（与 HTML 端 marker/描边同义）。
    """
    sc = pe.PptdScaler(x, y, w)
    zones = elem.get("zones", []) or []
    links = elem.get("links", []) or []
    n = len(zones)
    zone_w = (1200 - 80 - 40 * (n - 1)) / max(1, n)
    elems = []
    zone_rects = []
    zone_node_rects = {}  # zone_name -> node_name -> (x, y, w, h)，1200 坐标系
    for i, z in enumerate(zones):
        zname = z.get("name", "")
        zx = 40 + i * (zone_w + 40)
        nodes = z.get("nodes", []) or []
        zh = 60 + max(1, len(nodes)) * 84 + 20
        zone_rects.append((zname, zx, 40, zone_w, zh))
        zone_node_rects[zname] = {}
        for k, nd in enumerate(nodes):
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            ny = 40 + 50 + k * 84
            zone_node_rects[zname][nd_name] = (zx + 24, ny, zone_w - 48, 64)
    name2rect = {z[0]: z for z in zone_rects}

    def _node_rect(ref):
        if "." in ref:
            zone_name, node_name = ref.split(".", 1)
            return zone_node_rects.get(zone_name, {}).get(node_name)
        return None

    def _zone_center(ref):
        z = name2rect.get(ref)
        if z:
            return z[1] + z[3] / 2, z[2] + z[4] / 2
        return None

    OUT = 3    # 出口线头外移
    IN = 8     # 入口箭头外移（与 HTML 端同值，箭头主体露出节点框）

    for li, link in enumerate(links):
        fr, to = link.get("from", ""), link.get("to", "")
        ra, rb = _node_rect(fr), _node_rect(to)
        mode = link.get("mode", "sync")
        stroke = theme.PURPLE if mode == "async" else "#1E3A8A"
        dash = mode == "async"
        if ra and rb:
            ax1, ay1, aw1, ah1 = ra
            bx1, by1, bw1, bh1 = rb
            if ax1 == bx1:
                sx1, sy1 = ax1 + aw1 / 2, ay1 + ah1 + OUT
                sx2, sy2 = bx1 + bw1 / 2, by1 - IN
            else:
                sx1, sy1 = ax1 + aw1 + OUT, ay1 + ah1 / 2
                sx2, sy2 = bx1 - IN, by1 + bh1 / 2
        else:
            a = _zone_center(fr)
            b = _zone_center(to)
            if not a or not b:
                continue
            sx1, sy1 = a
            sx2, sy2 = b
        elems.append(pe.connector(f"dep-lnk-{li}", sc.px(sx1), sc.py(sy1), sc.px(sx2), sc.py(sy2),
                                  color=stroke, dash=dash))
        if link.get("label"):
            elems.append(pe.text(f"dep-lnk-l-{li}",
                                 [sc.px(min(sx1, sx2) + abs(sx2 - sx1) * 0.5 - 80), sc.py(min(sy1, sy2) - 22),
                                  sc.len(160), sc.len(18)],
                                 link["label"], font_size=max(8, sc.len(11)), color=stroke))
    max_h = 0
    for name, zx, zy, zw, zh in zone_rects:
        max_h = max(max_h, zh)
        elems.append(pe.shape(f"dep-z-{name}", [sc.px(zx), sc.py(zy), sc.len(zw), sc.len(zh)],
                              "roundRect", fill=theme.BG, adjustments=[6000],
                              border={"style": "solid", "width": 1, "color": theme.BORDER_STRONG}))
        elems.append(pe.text(f"dep-z-{name}-t", [sc.px(zx + 16), sc.py(zy + 10), sc.len(zw - 32), sc.len(22)],
                             name, font_size=max(10, sc.len(14)), color=theme.TEXT_STRONG,
                             bold=True, align=("left", "middle")))
        z = next(zz for zz in zones if zz.get("name", "") == name)
        for k, nd in enumerate(z.get("nodes", []) or []):
            ny = zy + 50 + k * 84
            elems.append(pe.shape(f"dep-z-{name}-n{k}", [sc.px(zx + 24), sc.py(ny), sc.len(zw - 48), sc.len(64)],
                                  "roundRect", fill=theme.CARD, adjustments=[8000],
                                  border={"style": "solid", "width": 1.5, "color": theme.BLUE}))
            elems.append(pe.shape(f"dep-z-{name}-n{k}-bar", [sc.px(zx + 24), sc.py(ny), sc.len(5), sc.len(64)],
                                  "rect", fill=theme.BLUE))
            elems.append(pe.text(f"dep-z-{name}-n{k}-t", [sc.px(zx + 24), sc.py(ny + 10), sc.len(zw - 48), sc.len(22)],
                                 nd.get("name", ""), font_size=max(10, sc.len(13)),
                                 color=theme.TEXT, bold=True))
            if nd.get("desc"):
                elems.append(pe.text(f"dep-z-{name}-n{k}-d", [sc.px(zx + 24), sc.py(ny + 34), sc.len(zw - 48), sc.len(18)],
                                     nd["desc"], font_size=max(8, sc.len(11)),
                                     color=theme.TEXT_SUB))
    return elems, sc.len(max_h + 100)


# ---------------------------------------------------------------------------
# platform_hub（第 29 种，D-094）：中心-环绕-右集成平台规划图
#   center:     {name, desc?, modules: []}   中心大卡（CRM 核心 + 模块 chip）
#   satellites: [{name, modules: []}]        周边系统卡环绕（≤6 六边形槽位）
#   right:      {name, items: []}            右侧竖条集成面板（ERP，可选）
# ---------------------------------------------------------------------------

def _phub_chip_flow(items, max_w, font=11, chip_h=22, gap=6, pad=8):
    """chip 流布局几何（HTML SVG / pptd 共用）：返回 (boxes, 总高)。
    boxes = [(dx, dy, w, text)]，相对芯片区左上角；宽度估算与
    pptd_emit.est_text_w 同源（全角≈font，半角≈0.55*font）。"""
    boxes, cx, cy = [], 0.0, 0.0
    for m in items:
        w = pe.est_text_w(m, font) + pad * 2
        if cx + w > max_w and cx > 0:
            cx, cy = 0.0, cy + chip_h + gap
        boxes.append((cx, cy, w, m))
        cx += w + gap
    return boxes, cy + (chip_h if boxes else 0)


def _phub_border_point(cx, cy, hw, hh, tx, ty):
    """矩形中心 -> 目标点的射线与矩形边的交点（连线止于卡缘，不穿卡）。"""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    t = min(hw / abs(dx) if dx else float("inf"),
            hh / abs(dy) if dy else float("inf"))
    return cx + dx * t, cy + dy * t


def _phub_geometry(elem):
    """platform_hub 布局几何（HTML/pptd 共用，viewBox 1200×440 坐标系）。"""
    center = elem.get("center", {}) or {}
    sats = elem.get("satellites", []) or []
    right = elem.get("right", {}) or {}
    W, H = 1200.0, 440.0
    main_w = 880.0 if right else 1200.0
    ccx, ccy = main_w / 2, H / 2
    # 中心卡：标题 + 可选 desc + 模块 chip 流
    cw = 340.0
    c_mods = [str(m) for m in center.get("modules", []) or []]
    c_boxes, c_chips_h = _phub_chip_flow(c_mods, cw - 36, font=11, chip_h=24, gap=8, pad=10)
    c_title_h = 24.0
    c_desc_h = 16.0 if center.get("desc") else 0.0
    ch = 14 + c_title_h + c_desc_h + (6 + c_chips_h if c_mods else 0) + 14
    cx0, cy0 = ccx - cw / 2, ccy - ch / 2
    # 卫星卡：≤6 走六边形槽位；>6 退化为圆环均布
    sw = 200.0
    slots = [(0.16, 0.16), (0.84, 0.16), (0.12, 0.50), (0.88, 0.50),
             (0.16, 0.84), (0.84, 0.84)]
    import math
    sat_cards = []
    n = len(sats)
    for i, s in enumerate(sats):
        if n <= 6:
            fx, fy = slots[i]
        else:
            ang = -math.pi / 2 + 2 * math.pi * i / n
            fx, fy = 0.5 + 0.40 * math.cos(ang), 0.5 + 0.38 * math.sin(ang)
        sx, sy = main_w * fx, H * fy
        mods = [str(m) for m in (s.get("modules", []) if isinstance(s, dict) else []) or []]
        boxes, chips_h = _phub_chip_flow(mods, sw - 24, font=11, chip_h=22, gap=6, pad=8)
        sh = 10 + 22 + (4 + chips_h if mods else 0) + 10
        scx, scy = sx, sy
        # 连线两端各退到卡缘（lint：连接线止于节点边缘，不穿越卡片/chip）
        lx1, ly1 = _phub_border_point(ccx, ccy, cw / 2, ch / 2, scx, scy)
        lx2, ly2 = _phub_border_point(scx, scy, sw / 2, sh / 2, ccx, ccy)
        sat_cards.append({"spec": s, "x": sx - sw / 2, "y": sy - sh / 2,
                          "w": sw, "h": sh, "boxes": boxes,
                          "line": (lx1, ly1, lx2, ly2)})
    geo = {"W": W, "H": H, "main_w": main_w, "ccx": ccx, "ccy": ccy,
           "center": center, "cx0": cx0, "cy0": cy0, "cw": cw, "ch": ch,
           "c_boxes": c_boxes, "c_title_h": c_title_h, "c_desc_h": c_desc_h,
           "satellites": sat_cards, "right": right}
    if right:
        geo["rx"], geo["rw"] = main_w + 16, W - (main_w + 16) - 16
        geo["ry"], geo["rh"] = 16.0, H - 32
        # ERP 连线走中心卡下缘肘形绕行（避开右中卫星卡）：下缘 -> 下探 -> 横进面板
        elbow_y = max(cy0 + ch + 20, 322.0)
        geo["right_link"] = [(ccx, cy0 + ch), (ccx, elbow_y), (geo["rx"] - 8, elbow_y)]
        # 标签锚在横段左 1/5 处、线之上（lint：避开卫星连线 phub-l-4/5 的 x 区间）
        geo["right_label"] = (ccx + (geo["rx"] - 8 - ccx) * 0.18, elbow_y - 12)
    return geo


def _phub_html(elem):
    """platform_hub HTML：SVG 单图画布（连线压卡下，卡体圆角 + chip）。"""
    g = _phub_geometry(elem)
    center, right = g["center"], g["right"]
    ccx = g["ccx"]
    parts = [f'<svg class="dg" viewBox="0 0 {g["W"]:.0f} {g["H"]:.0f}" xmlns="http://www.w3.org/2000/svg">',
             theme.SVG_DEFS]
    # 连线（先画，压在卡下；两端止于卡缘，不穿卡）
    for sc_ in g["satellites"]:
        lx1, ly1, lx2, ly2 = sc_["line"]
        parts.append(f'<line x1="{lx1:.0f}" y1="{ly1:.0f}" x2="{lx2:.0f}" y2="{ly2:.0f}" stroke="{theme.BLUE_MID}" stroke-width="1.6"/>')
    if right:
        (px1, py1), (px2, py2), (px3, py3) = g["right_link"]
        parts.append(f'<path d="M{px1:.0f},{py1:.0f} L{px2:.0f},{py2:.0f} L{px3:.0f},{py3:.0f}" stroke="{theme.GREEN}" stroke-width="2" fill="none" marker-end="url(#dgm-arr-g)"/>')
        lx, ly = g["right_label"]
        parts.append(f'<text x="{lx:.0f}" y="{ly:.0f}" font-size="11" font-weight="600" fill="{theme.GREEN}" text-anchor="middle" data-editable="true">集成接口</text>')
    # 卫星卡
    for sc_ in g["satellites"]:
        s = sc_["spec"]
        name = s.get("name", "") if isinstance(s, dict) else str(s)
        sx0, sy0, sw, sh = sc_["x"], sc_["y"], sc_["w"], sc_["h"]
        parts.append(f'<rect x="{sx0:.0f}" y="{sy0:.0f}" width="{sw:.0f}" height="{sh:.0f}" rx="10" fill="{theme.WHITE}" stroke="{theme.BLUE}" stroke-width="1.5"/>')
        parts.append(f'<text x="{sx0 + sw / 2:.0f}" y="{sy0 + 25:.0f}" font-size="13" font-weight="700" fill="{theme.BLUE}" text-anchor="middle" data-editable="true">{_esc(name)}</text>')
        for dx, dy, w, m in sc_["boxes"]:
            parts.append(f'<rect x="{sx0 + 12 + dx:.0f}" y="{sy0 + 36 + dy:.0f}" width="{w:.0f}" height="22" rx="5" fill="{theme.BLUE_LIGHT}"/>')
            parts.append(f'<text x="{sx0 + 12 + dx + w / 2:.0f}" y="{sy0 + 36 + dy + 15:.0f}" font-size="11" font-weight="600" fill="{theme.BLUE}" text-anchor="middle" data-editable="true">{_esc(m)}</text>')
    # 中心卡（最后画，压连线）
    cx0, cy0, cw, ch = g["cx0"], g["cy0"], g["cw"], g["ch"]
    parts.append(f'<rect x="{cx0:.0f}" y="{cy0:.0f}" width="{cw:.0f}" height="{ch:.0f}" rx="14" fill="{theme.BLUE}"/>')
    parts.append(f'<text x="{ccx:.0f}" y="{cy0 + 30:.0f}" font-size="16" font-weight="700" fill="{theme.WHITE}" text-anchor="middle" data-editable="true">{_esc(center.get("name", "CRM 核心"))}</text>')
    if center.get("desc"):
        parts.append(f'<text x="{ccx:.0f}" y="{cy0 + 48:.0f}" font-size="11" fill="rgba(255,255,255,0.8)" text-anchor="middle" data-editable="true">{_esc(center["desc"])}</text>')
    chip_y = cy0 + 14 + g["c_title_h"] + g["c_desc_h"] + 6
    for dx, dy, w, m in g["c_boxes"]:
        parts.append(f'<rect x="{cx0 + 18 + dx:.0f}" y="{chip_y + dy:.0f}" width="{w:.0f}" height="24" rx="6" fill="{theme.WHITE}"/>')
        parts.append(f'<text x="{cx0 + 18 + dx + w / 2:.0f}" y="{chip_y + dy + 16:.0f}" font-size="11" font-weight="700" fill="{theme.BLUE}" text-anchor="middle" data-editable="true">{_esc(m)}</text>')
    # 右侧集成面板（ERP）
    if right:
        rx, rw, ry, rh = g["rx"], g["rw"], g["ry"], g["rh"]
        parts.append(f'<rect x="{rx:.0f}" y="{ry:.0f}" width="{rw:.0f}" height="{rh:.0f}" rx="12" fill="{theme.BG}" stroke="{theme.BORDER}" stroke-width="1.5"/>')
        parts.append(f'<rect x="{rx:.0f}" y="{ry:.0f}" width="{rw:.0f}" height="44" rx="12" fill="{theme.GREEN}"/>')
        parts.append(f'<rect x="{rx:.0f}" y="{ry + 24:.0f}" width="{rw:.0f}" height="20" fill="{theme.GREEN}"/>')
        parts.append(f'<text x="{rx + rw / 2:.0f}" y="{ry + 29:.0f}" font-size="13" font-weight="700" fill="{theme.WHITE}" text-anchor="middle" data-editable="true">{_esc(right.get("name", "ERP 集成"))}</text>')
        iy = ry + 60
        for it in right.get("items", []) or []:
            lines = pe.wrap_lines(str(it), 11, rw - 52)
            ih = len(lines) * 16 + 12
            parts.append(f'<rect x="{rx + 14:.0f}" y="{iy:.0f}" width="3" height="{ih - 10}" fill="{theme.GREEN}"/>')
            for li, ln in enumerate(lines):
                parts.append(f'<text x="{rx + 26:.0f}" y="{iy + 12 + li * 16:.0f}" font-size="11" fill="{theme.TEXT}" data-editable="true">{_esc(ln)}</text>')
            iy += ih
    parts.append("</svg>")
    return "\n".join(parts)


def _mapping_pptd(elem, x, y, w):
    mappings = elem.get("mappings", []) or []
    headers = ["业务能力", "业务流程", "IT 系统", "数据实体"]
    emit_rows = [[{"content": {"text": h}} for h in headers]]
    plain_rows = [[str(h) for h in headers]]
    for m in mappings:
        emit_rows.append([
            {"content": {"color": "$navy", "text": f"<p><strong>{pe._esc(m.get('biz_capability', ''))}</strong></p>\n"}},
            {"content": {"text": "  ".join(pe._esc(x) for x in (m.get("biz_processes", []) or []))}},
            {"content": {"text": "  ".join(pe._esc(x) for x in (m.get("it_systems", []) or []))}},
            {"content": {"text": "  ".join(pe._esc(x) for x in (m.get("data_entities", []) or []))}},
        ])
        plain_rows.append([str(m.get("biz_capability", "")),
                           "  ".join(m.get("biz_processes", []) or []),
                           "  ".join(m.get("it_systems", []) or []),
                           "  ".join(m.get("data_entities", []) or [])])
    col_w = [0.18, 0.30, 0.26, 0.26]
    # 行高 hug（间距体系 v1 §五，排查 I-16）：下限原写死 44
    table_h, row_fracs = pe.table_hug_geometry(plain_rows, col_w, w, 44, 0.14)
    elems = [{
        "elementId": f"bim-{y}", "elementType": "table",
        "bounds": [x, y, w, table_h],
        "columnWidths": col_w,
        "rowHeights": row_fracs,
        "style": "$default",
        "rows": emit_rows,
    }]
    return elems, table_h


def _phub_pptd(elem, x, y, w):
    """platform_hub pptd：与 HTML 同几何（viewBox 1200×440 -> 内容区）。
    全原生形状/连接符，零图像化（同源铁律）。"""
    sc = pe.PptdScaler(x, y, w)
    g = _phub_geometry(elem)
    center, right = g["center"], g["right"]
    elems = []
    # 连线（压卡下；两端止于卡缘，不穿卡）
    for i, sc_ in enumerate(g["satellites"]):
        lx1, ly1, lx2, ly2 = sc_["line"]
        elems.append(pe.connector(f"phub-l-{i}", sc.px(lx1), sc.py(ly1),
                                  sc.px(lx2), sc.py(ly2),
                                  arrow=("none", "none"), color=theme.BLUE_MID, width=1.6))
    if right:
        (px1, py1), (px2, py2), (px3, py3) = g["right_link"]
        elems.append(pe.connector("phub-l-right-v", sc.px(px1), sc.py(py1),
                                  sc.px(px2), sc.py(py2),
                                  arrow=("none", "none"), color=theme.GREEN, width=1.5))
        elems.append(pe.connector("phub-l-right-h", sc.px(px2), sc.py(py2),
                                  sc.px(px3), sc.py(py3),
                                  arrow=("none", "arrow"), color=theme.GREEN, width=1.5))
        lx, ly = g["right_label"]
        elems.append(pe.text("phub-l-right-t", [sc.px(lx) - sc.len(60), sc.py(ly) - sc.len(10),
                                                sc.len(120), sc.len(18)],
                             "集成接口", font_size=max(8, sc.len(11)), color=theme.GREEN,
                             bold=True, wrap=False))
    # 卫星卡
    for i, sc_ in enumerate(g["satellites"]):
        s = sc_["spec"]
        name = s.get("name", "") if isinstance(s, dict) else str(s)
        sx0, sy0 = sc.px(sc_["x"]), sc.py(sc_["y"])
        sw, sh = sc.len(sc_["w"]), sc.len(sc_["h"])
        elems.append(pe.shape(f"phub-s-{i}", [sx0, sy0, sw, sh], "roundRect",
                              fill=theme.CARD, adjustments=[10000],
                              border={"style": "solid", "width": 1.5, "color": theme.BLUE}))
        elems.append(pe.text(f"phub-s-{i}-t", [sx0, sy0 + sc.len(8), sw, sc.len(22)],
                             name, font_size=max(10, sc.len(13)), color=theme.BLUE,
                             bold=True, wrap=False))
        for k, (dx, dy, cwp, m) in enumerate(sc_["boxes"]):
            bx = sc.px(sc_["x"] + 12 + dx)
            by = sc.py(sc_["y"] + 36 + dy)
            bw = sc.len(cwp)
            elems.append(pe.shape(f"phub-s-{i}-c{k}", [bx, by, bw, sc.len(22)],
                                  "roundRect", fill=theme.BLUE_LIGHT, adjustments=[50000]))
            elems.append(pe.text(f"phub-s-{i}-ct{k}", [bx, by, bw, sc.len(22)], m,
                                 font_size=max(8, sc.len(11)), color=theme.BLUE,
                                 bold=True, wrap=False))
    # 中心卡（压连线）
    cx0, cy0 = sc.px(g["cx0"]), sc.py(g["cy0"])
    cw, ch = sc.len(g["cw"]), sc.len(g["ch"])
    elems.append(pe.shape("phub-c", [cx0, cy0, cw, ch], "roundRect",
                          fill=theme.BLUE, adjustments=[10000]))
    elems.append(pe.text("phub-c-t", [cx0, cy0 + sc.len(12), cw, sc.len(24)],
                         center.get("name", "CRM 核心"), font_size=max(12, sc.len(16)),
                         color=theme.WHITE, bold=True, wrap=False))
    if center.get("desc"):
        elems.append(pe.text("phub-c-d", [cx0, cy0 + sc.len(38), cw, sc.len(16)],
                             center["desc"], font_size=max(8, sc.len(11)),
                             color=theme.WHITE, wrap=False))
    chip_base_y = sc.py(g["cy0"] + 14 + g["c_title_h"] + g["c_desc_h"] + 6)
    for k, (dx, dy, cwp, m) in enumerate(g["c_boxes"]):
        bx = sc.px(g["cx0"] + 18 + dx)
        by = chip_base_y + sc.len(dy)
        bw = sc.len(cwp)
        elems.append(pe.shape(f"phub-c-c{k}", [bx, by, bw, sc.len(24)],
                              "roundRect", fill=theme.WHITE, adjustments=[50000]))
        elems.append(pe.text(f"phub-c-ct{k}", [bx, by, bw, sc.len(24)], m,
                             font_size=max(8, sc.len(11)), color=theme.BLUE,
                             bold=True, wrap=False))
    # 右侧集成面板（ERP）
    if right:
        rx, rw = sc.px(g["rx"]), sc.len(g["rw"])
        ry, rh = sc.py(g["ry"]), sc.len(g["rh"])
        elems.append(pe.shape("phub-r", [rx, ry, rw, rh], "roundRect",
                              fill=theme.BG, adjustments=[8000],
                              border={"style": "solid", "width": 1.5, "color": theme.BORDER}))
        # 标题条：单个 pill（双矩形拼合会让标题文本跨形状边界，lint TextDrift）
        elems.append(pe.shape("phub-r-bar", [rx, ry, rw, sc.len(44)], "roundRect",
                              fill=theme.GREEN, adjustments=[22000]))
        elems.append(pe.text("phub-r-t", [rx, ry, rw, sc.len(44)],
                             right.get("name", "ERP 集成"), font_size=max(10, sc.len(13)),
                             color=theme.WHITE, bold=True, wrap=False))
        iy = g["ry"] + 60
        for j, it in enumerate(right.get("items", []) or []):
            lines = pe.wrap_lines(str(it), 11, g["rw"] - 52)
            ih = len(lines) * 16 + 12
            elems.append(pe.shape(f"phub-r-i{j}-bar", [sc.px(g["rx"] + 14), sc.py(iy),
                                                       sc.len(3), sc.len(ih - 10)],
                                  "rect", fill=theme.GREEN))
            elems.append(pe.text(f"phub-r-i{j}", [sc.px(g["rx"] + 24), sc.py(iy),
                                                  sc.len(g["rw"] - 44), sc.len(ih)],
                                 "\n".join(lines), font_size=max(8, sc.len(11)),
                                 color=theme.TEXT, align=("left", "top"),
                                 line_height=1.45))
            iy += ih
    return elems, sc.len(g["H"])


# ---------------------------------------------------------------------------
# D-5：pyramid 层级金字塔（trapezoid 堆叠，顶层窄底层宽，禁 freeform path）
# ---------------------------------------------------------------------------

def _pyramid_html(elem):
    levels = elem.get("levels", []) or []
    n = max(1, len(levels))
    vb_h = 400
    min_w, max_w = 200, 1000
    step = (max_w - min_w) / n
    cx = 600.0
    layer_h = vb_h / n
    colors = theme.LAYER_COLORS
    parts = [f'<svg class="dg" viewBox="0 0 1200 {vb_h}" '
             f'xmlns="http://www.w3.org/2000/svg">']
    for i, lv in enumerate(levels):
        top_w = min_w + i * step
        bot_w = min_w + (i + 1) * step
        y = i * layer_h
        x1, x2 = cx - top_w / 2, cx + top_w / 2
        x3, x4 = cx - bot_w / 2, cx + bot_w / 2
        c = colors[i % len(colors)]
        parts.append(
            f'<polygon points="{x1:.1f},{y:.1f} {x2:.1f},{y:.1f} '
            f'{x4:.1f},{y + layer_h:.1f} {x3:.1f},{y + layer_h:.1f}" '
            f'fill="{c}" stroke="{theme.WHITE}" stroke-width="2"/>')
        ty = y + layer_h / 2
        parts.append(f'<text x="{cx}" y="{ty}" font-size="14" font-weight="700" '
                     f'fill="{theme.WHITE}" text-anchor="middle" data-editable="true">'
                     f'{_esc(lv.get("title", ""))}</text>')
        desc = lv.get("desc", "")
        if desc:
            parts.append(f'<text x="{cx}" y="{ty + 18}" font-size="11" fill="{theme.WHITE}" '
                         f'text-anchor="middle" data-editable="true">{_esc(desc)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _pyramid_pptd(elem, x, y, w):
    levels = elem.get("levels", []) or []
    n = max(1, len(levels))
    sc = pe.PptdScaler(x, y, w)
    elems = []
    total_h = 360.0
    layer_h = total_h / n
    min_w, max_w = 200.0, 1000.0
    step = (max_w - min_w) / n
    cx = 600.0
    colors = theme.LAYER_COLORS
    for i, lv in enumerate(levels):
        top_w = min_w + i * step
        bot_w = min_w + (i + 1) * step
        bx = sc.px(cx - bot_w / 2)
        bw = sc.len(bot_w)
        by = y + sc.len(i * layer_h)
        bh = sc.len(layer_h)
        # trapezoid 上窄下宽：adj = 上边宽/下边宽（v1 方言 0~100000 归一化）
        adj = int(top_w / bot_w * 100000)
        elems.append(pe.shape(f"pyr{i}", [bx, by, bw, bh], "trapezoid",
                              fill=colors[i % len(colors)], adjustments=[adj]))
        # 标题 + desc 放层内上部（框宽按层顶边宽预算，防溢出梯形）
        tw = sc.len(top_w) - 2 * INSET_X
        tx = sc.px(cx - top_w / 2 + INSET_X)
        ty = by + bh * 0.3
        title_fs = max(10, sc.len(14))
        elems.append(pe.text(f"pyr{i}-t", [tx, ty, tw, sc.len(20)],
                             lv.get("title", ""), font_size=title_fs,
                             color=theme.WHITE, bold=True))
        desc = lv.get("desc", "")
        if desc:
            elems.append(pe.text(f"pyr{i}-d", [tx, ty + sc.len(20), tw, sc.len(16)],
                                 desc, font_size=max(8, sc.len(11)),
                                 color=theme.WHITE, align=("center", "middle")))
    return elems, sc.len(total_h)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def render_html(elem):
    st = elem.get("subtype", "")
    if st in ("4a", "layered"):
        rows = _layer_rows(elem)
        parts = [theme.section_open(elem)]
        for r in rows:
            chip_bg, chip_c = _chip_css({theme.BLUE: "b", theme.GREEN: "g",
                                         theme.TEAL: "t", theme.PURPLE: "p"}.get(r["color"], "w"))
            chips = "".join(
                f'<span data-editable="true" style="display:inline-block;background:{chip_bg};color:{chip_c};'
                f'border-radius:4px;padding:4px 10px;font-size:12px;font-weight:600;margin:3px 6px 3px 0;">{_esc(c)}</span>'
                for c in r["components"])
            desc = (f'<div style="font-size:12px;color:{theme.TEXT_SUB};margin-bottom:8px;" data-editable="true">{_esc(r["desc"])}</div>'
                    if r["desc"] else "")
            parts.append(
                f'<div style="display:flex;gap:14px;align-items:stretch;margin-bottom:12px;">'
                f'<div style="flex:0 0 108px;border-radius:8px;background:{r["color"]};color:{theme.WHITE};font-weight:700;'
                f'font-size:14px;display:flex;align-items:center;justify-content:center;text-align:center;padding:12px 8px;" data-editable="true">{_esc(r["name"])}</div>'
                f'<div style="flex:1;background:{theme.BG};border-radius:8px;padding:14px 18px;">{desc}{chips}</div>'
                f'</div>')
        parts.append(theme.SECTION_CLOSE)
        return "\n".join(parts)
    body = {"integration": _intg_html, "biz_overview": _biz_overview_html,
            "deployment": _deploy_html, "biz_it_mapping": _mapping_html,
            "platform_hub": _phub_html, "pyramid": _pyramid_html}.get(st)
    if not body:
        raise NotImplementedError(f"architecture/{st} 未实现")
    return theme.section_open(elem) + "\n" + body(elem) + "\n" + theme.SECTION_CLOSE


def render_pptd(elem, x, y, w, theme_name=None):
    """层叠行 pptd。返回 (元素列表, 消耗高度)。theme_name：v2 主题包名，
    biz_overview 三态 tone 取色用（D-092，与图例槽位 swatch 同源）。"""
    st = elem.get("subtype", "")
    if st in ("4a", "layered"):
        rows = _layer_rows(elem)
        sc = pe.PptdScaler(x, y, w)
        elems = []
        cy = 0.0  # pptd px 行 y 游标：按行堆叠实高推进（hug）
        tag_w, gap = 108.0, 14.0
        body_x = x + sc.len(tag_w + gap)
        body_w = w - sc.len(tag_w + gap)
        inner_x = body_x + sc.len(16)
        inner_w = body_w - sc.len(32)
        desc_fs = max(8, sc.len(11))
        for i, r in enumerate(rows):
            # 行内容器 stack（间距体系 v1 §3.2，I-2 修复）：
            # desc 顶 = 行顶 + INSET_Y；chips 顶 = desc 底 + GAP_SM
            # （无 desc 时 = 行顶 + INSET_Y）；行高 = 堆叠总高 + 上下 padding
            desc_h = 0.0
            if r["desc"]:
                n_lines = len(pe.wrap_lines(r["desc"], desc_fs,
                                            inner_w - 2 * INSET_X))
                desc_h = pe.stack_text_h(n_lines, desc_fs)
            stack_top = INSET_Y + desc_h + GAP_SM if r["desc"] else INSET_Y
            chip_elems, chip_h = pe.emit_chips(
                f"ly{i}", r["components"], inner_x, y + cy + stack_top,
                inner_w, font_size=max(9, sc.len(12)))
            body_h = stack_top + chip_h + INSET_Y
            # 标签名按 tag 宽折行预算，行高不够时撑高整行（防 ly{i}-tagt 溢出）
            tag_fs = max(11, sc.len(14))
            tag_lines = len(pe.wrap_lines(r["name"], tag_fs, sc.len(tag_w) - sc.len(12)))
            body_h = max(body_h, pe.stack_text_h(tag_lines, tag_fs) + 2 * INSET_Y)
            elems.append(pe.shape(f"ly{i}-tag", [x, y + cy, sc.len(tag_w), body_h],
                                  "roundRect", fill=r["color"], adjustments=[8000]))
            elems.append(pe.text(f"ly{i}-tagt", [x, y + cy, sc.len(tag_w), body_h],
                                 r["name"], font_size=tag_fs, color=theme.WHITE, bold=True))
            elems.append(pe.shape(f"ly{i}-body", [body_x, y + cy, body_w, body_h],
                                  "roundRect", fill=theme.BG, adjustments=[6000]))
            if r["desc"]:
                elems.append(pe.text(f"ly{i}-desc",
                                     [inner_x, y + cy + INSET_Y, inner_w, desc_h],
                                     r["desc"], font_size=desc_fs,
                                     color=theme.TEXT_SUB, align=("left", "middle")))
            elems.extend(chip_elems)
            cy += body_h + GAP_MD
        return elems, cy
    fn = {"integration": _intg_pptd, "biz_overview": _biz_overview_pptd,
          "deployment": _deploy_pptd, "biz_it_mapping": _mapping_pptd,
          "platform_hub": _phub_pptd, "pyramid": _pyramid_pptd}.get(st)
    if not fn:
        raise NotImplementedError(f"architecture/{st} 未实现")
    if st == "biz_overview":
        return _biz_overview_pptd(elem, x, y, w, theme_name)
    return fn(elem, x, y, w)
