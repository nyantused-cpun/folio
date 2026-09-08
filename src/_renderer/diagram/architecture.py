# -*- coding: utf-8 -*-
"""architecture 类渲染器：4a / layered / integration / biz_overview / deployment / biz_it_mapping（6 种全部实现）。

HTML：div 层叠行（左层标签色块 + 右卡体 chip），inline style 自包含。
pptd：层标签 shape + 卡体 shape + chip 流（emit_chips），全原生对象。

spec：
  4a:      layers: [{name, desc, components: []}]（BA/AA/DA/TA 四层，固定配色）
  layered: layers: [{name, desc, components: []}]（层色循环 蓝→绿→青→紫→灰）
"""

from .. import theme
from ..theme import _esc
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

def _intg_p2p_names(elem):
    """点对点简式形态识别（#58）：source/target 为系统名字符串
    （outline_to_spec M1 生成器形态，schema 放行 str|dict 双合法）。

    简式返回 (源系统名, 目标系统名)；source 非 str（端点 mapping dict 或
    缺省）返回 None 走既有 mapping 分支。target 非 str 视同缺失（""），
    由调用方按降级惯例处理。
    """
    src = elem.get("source")
    if not isinstance(src, str):
        return None
    tgt = elem.get("target")
    return src, (tgt if isinstance(tgt, str) else "")


def _intg_card_html(color, name, items_html):
    """integration 端点卡（mapping/p2p 共用壳）：顶色条卡体 + 居中标题。"""
    return (f'<div style="background:{theme.CARD};border:1px solid {theme.BORDER};border-top:4px solid {color};border-radius:10px;padding:18px 20px;">'
            f'<div style="font-weight:700;font-size:15px;text-align:center;color:{color};padding-bottom:10px;margin-bottom:12px;border-bottom:2px solid {theme.BORDER};" data-editable="true">{_esc(name)}</div>{items_html}</div>')


def _intg_arrows_html(links):
    """integration 中间箭头列（mapping/p2p 共用）：label + 模式箭头 + 模式名。"""
    return "".join(
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;margin:6px 0;">'
        f'<div style="font-size:12px;font-weight:700;color:{theme.BLUE};" data-editable="true">{_esc(link.get("label", ""))}</div>'
        f'<div style="color:{theme.BLUE};font-size:22px;line-height:1;">{"⟷" if link.get("mode") == "bidirectional" else ("⇢" if link.get("mode") == "async" else "→")}</div>'
        f'<div style="font-size:11px;color:{theme.TEXT_SUB};">{ {"sync": "同步", "async": "异步", "bidirectional": "双向"}.get(link.get("mode", "sync"), "同步") }</div></div>'
        for link in links)


def _intg_p2p_html(elem, names):
    """integration 点对点简式 HTML（#58）：双端点卡 + 连接表达，复用 mapping
    形态的卡片/箭头原语（同一视觉语言，与 pptd 端语义同构）；
    缺 target 降级单卡（模块 warn 惯例），不崩。"""
    src_name, tgt_name = names
    links = elem.get("links", []) or [{"label": elem.get("interface", "API"), "mode": "sync"}]
    if not tgt_name:
        print(f"[diagram] integration 点对点简式缺 target，降级单卡渲染：source={src_name!r}")
        return f'<div style="display:flex;justify-content:center;">{_intg_card_html(theme.BLUE, src_name, "")}</div>'
    return (f'<div style="display:grid;grid-template-columns:1fr 150px 1fr;gap:18px;align-items:stretch;">'
            f'{_intg_card_html(theme.BLUE, src_name, "")}'
            f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;">{_intg_arrows_html(links)}</div>'
            f'{_intg_card_html(theme.GREEN, tgt_name, "")}'
            f'</div>')


def _intg_html(elem):
    """integration：点对点双卡 + 箭头列；hub 形态走总线放射。

    #58 双形态：source 为 dict 走端点 mapping（name + items 清单）；
    source 为 str 走点对点简式（系统名对系统名，M1 生成器形态）。
    """
    if elem.get("hub"):
        return _intg_hub_html(elem)
    p2p = _intg_p2p_names(elem)
    if p2p is not None:
        return _intg_p2p_html(elem, p2p)
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
    return (f'<div style="display:grid;grid-template-columns:1fr 150px 1fr;gap:18px;align-items:stretch;">'
            f'{_intg_card_html(theme.BLUE, src.get("name", "源系统"), src_items)}'
            f'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;">{_intg_arrows_html(links)}</div>'
            f'{_intg_card_html(theme.GREEN, tgt.get("name", "目标系统"), tgt_items)}'
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
        # 深底 hub 上的次级白字：rgba(255,255,255,α) 为 theme.WHITE 的中性
        # alpha 派生（WHITE 全主题恒定，无主题语义可跟随），hex8 字面量化会
        # 落到回归色板闭包外——语义冻结保留（R3-7 核验注记）。
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


def _icon_label(name):
    """拓扑图图标缩写：去括号后取更可识别的 1-2 字。

    策略：
    - 客户系统（Platinum / HRTPS / Mobile APP / Azure AD / IPSec VPN / P-filing
      / e-sign / OCR 等）保留英文/品牌缩写
    - 我方核心系统用「档案」「签章」「识别」等中文功能名
    - 客户描述（"内网 HR""SAAS HR"）直接忽略（括号内容已脱掉）
    """
    import re as _re
    # 显式映射：特定名称 -> 标识符（保证不撞名）
    explicit = {
        "Platinum（内网 HR）": "铂金",
        "HRTPS（SAAS HR）": "HRT",
        "Mobile APP（PMZ）": "手机",
        "HR 用户浏览器": "用户",
        "零信任接入（品牌未定）": "零信",
        "IPSec VPN 隧道": "VPN",
        "P-filing（e-filing）": "档案",
        "e-sign（契约锁）": "签章",
        "OCR": "OCR",
        "Azure AD SSO": "AD",
    }
    if name in explicit:
        return explicit[name]
    # 兜底：去括号后取前 2 个英文字首或前 2 个中文字
    main = _re.sub(r'[（(].*?[)）]', '', name).strip() or name
    words = _re.findall(r'[A-Za-z0-9]+', main)
    if words:
        abbr = ''.join(w[0].upper() for w in words[:2])
        return abbr or main[:2].upper()
    return main[:2]


def _deploy_html(elem):
    """deployment：传统网络拓扑图（小图标 + 下方系统名 + 泳道分区 + 端口连线）。"""
    zones = elem.get("zones", []) or []
    links = elem.get("links", []) or []
    n = len(zones)
    zone_w = (1200 - 80 - 40 * (n - 1)) / max(1, n)
    ICON_W, ICON_H = 44, 44
    STEP = 100
    TITLE_H = 44
    zone_rects = []
    icon_rects = {}
    for i, z in enumerate(zones):
        zname = z.get("name", "")
        zx = 40 + i * (zone_w + 40)
        nodes = z.get("nodes", []) or []
        zh = TITLE_H + max(1, len(nodes)) * STEP + 20
        zone_rects.append((zname, zx, 40, zone_w, zh))
        icon_rects[zname] = {}
        for k, nd in enumerate(nodes):
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            ix = zx + (zone_w - ICON_W) / 2
            iy = 40 + TITLE_H + 8 + k * STEP
            icon_rects[zname][nd_name] = (ix, iy, ICON_W, ICON_H)
    max_h = max((z[4] for z in zone_rects), default=140)
    parts = [f'<svg class="dg" viewBox="0 0 1200 {max_h + 40}" xmlns="http://www.w3.org/2000/svg">',
             f'<defs>'
             f'<marker id="dg-arr-sync" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="{theme.BLUE}"/></marker>'
             f'<marker id="dg-arr-async" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="{theme.PURPLE}"/></marker>'
             f'</defs>']

    def _icon_center(ref):
        if "." in ref:
            zn, nn = ref.split(".", 1)
            r = icon_rects.get(zn, {}).get(nn)
            if r:
                return r[0] + r[2] / 2, r[1] + r[3] / 2
        return None

    def _zone_center(ref):
        z = next((zz for zz in zone_rects if zz[0] == ref), None)
        if z:
            return z[1] + z[3] / 2, z[2] + z[4] / 2
        return None

    OUT, IN = 3, 2

    # 1) 先画网区之间虚线分隔线（在泳道 rect 之前，避免被遮）
    for i, (_name, zx, zy, zw, zh) in enumerate(zone_rects):
        if i < n - 1:
            lx = zx + zw + 20
            parts.append(f'<line x1="{lx}" y1="{zy + 40}" x2="{lx}" y2="{zy + zh}" stroke="{theme.BLUE}" stroke-width="1.5" stroke-dasharray="6,4" stroke-opacity="0.5"/>')

    # 2) 画泳道背景 + 标题
    for name, zx, zy, zw, zh in zone_rects:
        parts.append(f'<rect x="{zx}" y="{zy}" width="{zw}" height="{zh}" rx="12" fill="{theme.BG}" stroke="{theme.BORDER_STRONG}" stroke-width="1.2"/>')
        parts.append(f'<text x="{zx + zw / 2}" y="{zy + 26}" font-size="14" font-weight="700" fill="{theme.TEXT_STRONG}" text-anchor="middle" data-editable="true">{_esc(name)}</text>')

    # 3) 画连线（泳道之上、节点之下）
    for link in links:
        fr, to = link.get("from", ""), link.get("to", "")
        a = _icon_center(fr)
        b = _icon_center(to)
        mode = link.get("mode", "sync")
        stroke = theme.PURPLE if mode == "async" else theme.BLUE
        dash = ' stroke-dasharray="6,4"' if mode == "async" else ""
        marker = "url(#dg-arr-async)" if mode == "async" else "url(#dg-arr-sync)"
        if a and b:
            ax, ay = a
            bx, by = b
            if abs(ax - bx) < 1:
                sx1, sy1 = ax, ay + ICON_H / 2 + OUT
                sx2, sy2 = bx, by - ICON_H / 2 - IN
                c1x, c1y = ax, (sy1 + sy2) / 2
                c2x, c2y = bx, (sy1 + sy2) / 2
            else:
                sx1, sy1 = ax + ICON_W / 2 + OUT, ay
                sx2, sy2 = bx - ICON_W / 2 - IN, by
                c1x, c1y = ax + ICON_W / 2 + (bx - ax) * 0.4, ay
                c2x, c2y = bx - ICON_W / 2 - (bx - ax) * 0.4, by
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
            ly = (sy1 + sy2) / 2
            if abs(sx1 - sx2) < abs(sy1 - sy2):
                lx = sx1 + 18
            else:
                ly = min(sy1, sy2) - 12
            tw = len(str(link["label"])) * 9 + 16
            parts.append(f'<rect x="{lx - tw / 2}" y="{ly - 10}" width="{tw}" height="17" rx="4" fill="white" fill-opacity="0.95"/>')
            parts.append(f'<text x="{lx}" y="{ly + 4}" font-size="11" fill="{stroke}" text-anchor="middle" font-weight="600" font-family="Microsoft YaHei, sans-serif">{_esc(link["label"])}</text>')

    # 4) 画节点图标 + 名字 + desc
    for name, _zx, _zy, _zw, _zh in zone_rects:
        z = next(zz for zz in zones if zz.get("name", "") == name)
        for nd in z.get("nodes", []) or []:
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            r = icon_rects[name].get(nd_name)
            if not r:
                continue
            ix, iy, iw, ih = r
            cx = ix + iw / 2
            parts.append(f'<rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" rx="10" fill="{theme.BLUE}" stroke="{theme.mix(theme.BLUE, theme.BLACK, 0.465)}" stroke-width="1"/>')
            parts.append(f'<text x="{cx}" y="{iy + ih / 2 + 5}" font-size="13" font-weight="700" fill="white" text-anchor="middle" font-family="Microsoft YaHei, sans-serif">{_esc(_icon_label(nd_name))}</text>')
            parts.append(f'<text x="{cx}" y="{iy + ih + 15}" font-size="12" font-weight="600" fill="{theme.TEXT}" text-anchor="middle" data-editable="true" font-family="Microsoft YaHei, sans-serif">{_esc(nd_name)}</text>')
            if nd.get("desc"):
                parts.append(f'<text x="{cx}" y="{iy + ih + 31}" font-size="10" fill="{theme.mix(theme.TEXT, theme.WHITE, 0.245)}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif">{_esc(nd["desc"])}</text>')
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

def _intg_card_pptd(elems, side, sx, y, side_w, card_h, color, name, sc):
    """integration 端点卡壳（mapping/p2p 共用）：卡体 + 顶色条 + 居中标题。"""
    elems.append(pe.shape(f"intg-{side}", [sx, y, sc.len(side_w), sc.len(card_h)], "roundRect",
                          fill=theme.CARD, adjustments=[5000],
                          border={"style": "solid", "width": 1, "color": theme.BORDER}))
    elems.append(pe.shape(f"intg-{side}-top", [sx, y, sc.len(side_w), sc.len(4)], "rect", fill=color))
    elems.append(pe.text(f"intg-{side}-h", [sx, y + sc.len(12), sc.len(side_w), sc.len(24)],
                         name, font_size=max(11, sc.len(15)), color=color,
                         bold=True))


def _intg_arrows_pptd(elems, links, card_h, side_w, sc, y):
    """integration 中间箭头列（mapping/p2p 共用）：单 link sync 用块箭头 preset
    （D-2 块箭头扩充）；多 link / 双向 / 异步仍走 connector（细关系，需 dash/双箭头）。"""
    single_sync = len(links) == 1 and links[0].get("mode", "sync") == "sync"
    for k, link in enumerate(links):
        mode = link.get("mode", "sync")
        ay = y + sc.len(card_h / 2 - 20 + k * 40)
        ax1 = sc.px(40 + side_w + 12)
        ax2 = sc.px(40 + side_w + 150 - 12)
        both = mode == "bidirectional"
        if single_sync:
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


def _intg_p2p_pptd(elem, names, x, y, w):
    """integration 点对点简式 pptd（#58）：双端点卡 + 连接表达，几何与 mapping
    形态同源（同一卡片/箭头原语，与 HTML 端语义同构）；
    缺 target 降级单卡（模块 warn 惯例），不崩。"""
    sc = pe.PptdScaler(x, y, w)
    src_name, tgt_name = names
    links = elem.get("links", []) or [{"label": elem.get("interface", "API"), "mode": "sync"}]
    elems = []
    if not tgt_name:
        print(f"[diagram] integration 点对点简式缺 target，降级单卡渲染：source={src_name!r}")
        card_w, card_h = 420.0, 64.0
        _intg_card_pptd(elems, "src", sc.px((1200 - card_w) / 2), y, card_w, card_h,
                        theme.BLUE, src_name, sc)
        return elems, sc.len(card_h)
    card_h = 200  # mapping 形态无 items 时的同一下限
    side_w = (1200 - 150 - 2 * 40) / 2
    for side, name, color in (("src", src_name, theme.BLUE), ("tgt", tgt_name, theme.GREEN)):
        sx = sc.px(40 if side == "src" else 40 + side_w + 150)
        _intg_card_pptd(elems, side, sx, y, side_w, card_h, color, name, sc)
    _intg_arrows_pptd(elems, links, card_h, side_w, sc, y)
    return elems, sc.len(card_h)


def _intg_pptd(elem, x, y, w):
    """integration pptd：mapping/p2p 双形态（#58）；hub 形态走总线放射。"""
    if elem.get("hub"):
        return _intg_hub_pptd(elem, x, y, w)
    p2p = _intg_p2p_names(elem)
    if p2p is not None:
        return _intg_p2p_pptd(elem, p2p, x, y, w)
    sc = pe.PptdScaler(x, y, w)
    src = elem.get("source", {}) or {}
    tgt = elem.get("target", {}) or {}
    links = elem.get("links", []) or [{"label": elem.get("interface", "API"), "mode": "sync"}]
    elems = []
    card_h = max(200, 70 + max(len(src.get("items", []) or []), len(tgt.get("items", []) or [])) * 34)
    side_w = (1200 - 150 - 2 * 40) / 2
    for side, data, color in (("src", src, theme.BLUE), ("tgt", tgt, theme.GREEN)):
        sx = sc.px(40 if side == "src" else 40 + side_w + 150)
        _intg_card_pptd(elems, side, sx, y, side_w, card_h, color, data.get("name", ""), sc)
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
    _intg_arrows_pptd(elems, links, card_h, side_w, sc, y)
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
        pts.append((i, cx + r * 1.75 * math.cos(ang), cy + r * math.sin(ang),
                    s.get("name", "") if isinstance(s, dict) else str(s)))
    for i, sx, sy, _name in pts:
        ex, ey = _intg_hub_edge(cx, cy, sx, sy)
        # elementId 用索引不用用户文本（phub 同范式）：同名系统重复 ID 阻断 check
        elems.append(pe.connector(f"hub-l-{i}", sc.px(cx), sc.py(cy), sc.px(ex), sc.py(ey),
                                  arrow=("none", "none"), color=theme.BLUE_MID))
    elems.append(pe.shape("hub", [sc.px(cx - 140), sc.py(cy - 40), sc.len(280), sc.len(80)],
                          "roundRect", fill=theme.BLUE, adjustments=[10000]))
    elems.append(pe.text("hub-t", [sc.px(cx - 140), sc.py(cy - 24), sc.len(280), sc.len(26)],
                         hub.get("name", "ESB 总线"), font_size=max(12, sc.len(15)),
                         color=theme.WHITE, bold=True))
    if hub.get("desc"):
        elems.append(pe.text("hub-d", [sc.px(cx - 140), sc.py(cy + 2), sc.len(280), sc.len(36)],
                             hub["desc"], font_size=max(8, sc.len(10)), color=theme.WHITE))
    for i, sx, sy, name in pts:
        elems.append(pe.shape(f"hub-s-{i}", [sc.px(sx - 85), sc.py(sy - 26), sc.len(170), sc.len(52)],
                              "roundRect", fill=theme.CARD, adjustments=[8000],
                              border={"style": "solid", "width": 1.5, "color": theme.BLUE}))
        elems.append(pe.text(f"hub-st-{i}", [sc.px(sx - 85), sc.py(sy - 26), sc.len(170), sc.len(52)],
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
    """deployment：传统网络拓扑图（小图标 + 下方系统名 + 泳道分区 + 端口连线）。"""
    sc = pe.PptdScaler(x, y, w)
    zones = elem.get("zones", []) or []
    links = elem.get("links", []) or []
    n = len(zones)
    zone_w = (1200 - 80 - 40 * (n - 1)) / max(1, n)
    ICON_W, ICON_H = 44, 44
    STEP = 100
    TITLE_H = 44
    elems = []
    zone_rects = []
    icon_rects = {}
    for i, z in enumerate(zones):
        zname = z.get("name", "")
        zx = 40 + i * (zone_w + 40)
        nodes = z.get("nodes", []) or []
        zh = TITLE_H + max(1, len(nodes)) * STEP + 20
        zone_rects.append((zname, zx, 40, zone_w, zh))
        icon_rects[zname] = {}
        for k, nd in enumerate(nodes):
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            ix = zx + (zone_w - ICON_W) / 2
            iy = 40 + TITLE_H + 8 + k * STEP
            icon_rects[zname][nd_name] = (ix, iy, ICON_W, ICON_H)
    name2rect = {z[0]: z for z in zone_rects}

    def _icon_center(ref):
        if "." in ref:
            zn, nn = ref.split(".", 1)
            r = icon_rects.get(zn, {}).get(nn)
            if r:
                return r[0] + r[2] / 2, r[1] + r[3] / 2
        return None

    def _zone_center(ref):
        z = name2rect.get(ref)
        if z:
            return z[1] + z[3] / 2, z[2] + z[4] / 2
        return None

    OUT, IN = 3, 2

    # 1) 泳道背景 + 标题 + 网区之间虚线分隔线（ID 用索引不用区名：同名区重复 ID 阻断 check）
    for i, (name, zx, zy, zw, zh) in enumerate(zone_rects):
        elems.append(pe.shape(f"dep-z-{i}", [sc.px(zx), sc.py(zy), sc.len(zw), sc.len(zh)],
                              "roundRect", fill=theme.BG, adjustments=[6000],
                              border={"style": "solid", "width": 1, "color": theme.BORDER_STRONG}))
        elems.append(pe.text(f"dep-z-{i}-t", [sc.px(zx), sc.py(zy + 6), sc.len(zw), sc.len(24)],
                             name, font_size=max(10, sc.len(14)), color=theme.TEXT_STRONG,
                             bold=True, align=("center", "middle")))
        if i < n - 1:
            lx = zx + zw + 20
            elems.append(pe.connector(f"dep-z-{i}-sep", sc.px(lx), sc.py(zy + 40), sc.px(lx), sc.py(zy + zh),
                                      color=theme.BLUE, dash=True))

    # 2) 连线 + 端口标签（白底防穿线）
    for li, link in enumerate(links):
        fr, to = link.get("from", ""), link.get("to", "")
        a = _icon_center(fr)
        b = _icon_center(to)
        mode = link.get("mode", "sync")
        stroke = theme.PURPLE if mode == "async" else theme.BLUE
        dash = mode == "async"
        if a and b:
            ax, ay = a
            bx, by = b
            if abs(ax - bx) < 1:
                sx1, sy1 = ax, ay + ICON_H / 2 + OUT
                sx2, sy2 = bx, by - ICON_H / 2 - IN
            else:
                sx1, sy1 = ax + ICON_W / 2 + OUT, ay
                sx2, sy2 = bx - ICON_W / 2 - IN, by
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
            lx = (sx1 + sx2) / 2
            ly = (sy1 + sy2) / 2
            if abs(sx1 - sx2) < abs(sy1 - sy2):
                lx = sx1 + 18
            else:
                ly = min(sy1, sy2) - 14
            tw = len(str(link["label"])) * 9 + 24
            elems.append(pe.shape(f"dep-lnk-bg-{li}", [sc.px(lx - tw / 2), sc.py(ly - 10), sc.len(tw), sc.len(20)],
                                  "rect", fill=theme.WHITE))
            elems.append(pe.text(f"dep-lnk-l-{li}",
                                 [sc.px(lx - tw / 2), sc.py(ly - 10), sc.len(tw), sc.len(20)],
                                 link["label"], font_size=max(9, sc.len(10)),
                                 color=stroke, align=("center", "middle"), wrap=False))

    # 3) 节点图标 + 名字 + desc（ID 区名段同样走索引）
    for zi, (name, _zx, _zy, _zw, _zh) in enumerate(zone_rects):
        z = next(zz for zz in zones if zz.get("name", "") == name)
        for k, nd in enumerate(z.get("nodes", []) or []):
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            r = icon_rects[name].get(nd_name)
            if not r:
                continue
            ix, iy, iw, ih = r
            elems.append(pe.shape(f"dep-z-{zi}-n{k}", [sc.px(ix), sc.py(iy), sc.len(iw), sc.len(ih)],
                                  "roundRect", fill=theme.BLUE, adjustments=[10000],
                                  border={"style": "solid", "width": 1, "color": theme.mix(theme.BLUE, theme.BLACK, 0.465)}))
            elems.append(pe.text(f"dep-z-{zi}-n{k}-i", [sc.px(ix), sc.py(iy), sc.len(iw), sc.len(ih)],
                                 _icon_label(nd_name), font_size=max(9, sc.len(13)),
                                 color=theme.WHITE, bold=True))
            elems.append(pe.text(f"dep-z-{zi}-n{k}-t", [sc.px(ix - 55), sc.py(iy + ih + 2), sc.len(iw + 110), sc.len(20)],
                                 nd_name, font_size=max(9, sc.len(10)),
                                 color=theme.TEXT, bold=True, align=("center", "middle")))
            if nd.get("desc"):
                elems.append(pe.text(f"dep-z-{zi}-n{k}-d", [sc.px(ix - 65), sc.py(iy + ih + 22), sc.len(iw + 130), sc.len(20)],
                                     nd["desc"], font_size=max(8, sc.len(8)),
                                     color=theme.mix(theme.TEXT, theme.WHITE, 0.245), align=("center", "middle")))
    return elems, sc.len(max((z[4] for z in zone_rects), default=140) + 40)



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
        # 同 _intg hub 次级白字：theme.WHITE 的中性 alpha 派生，语义冻结保留
        # （R3-7 核验注记，理由见 integration 分支同款注释）。
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

_PYRAMID_VB_H = 400  # viewBox 高：HTML viewBox 与 pptd 消耗高度双端同一基准


def _pyramid_trap_adj(top_w, bot_w, layer_h):
    """trapezoid preset 的 OOXML adj：顶边左右各内缩 ss×adj/100000（ss=min(w,h)）。
    顶边宽=top_w、形状宽=bot_w → 单侧内缩=(bot_w-top_w)/2 反推；矩形层 adj=0。
    合法域 adj∈[0, maxAdj]（maxAdj=50000×w/ss，越界 pin）；PptdScaler x/y 等比，
    viewBox 单位计算与最终形状几何等价。
    """
    ss = min(bot_w, layer_h)
    if ss <= 0:
        return 0
    max_adj = 50000.0 * bot_w / ss
    adj = (bot_w - top_w) / 2.0 / ss * 100000.0
    return int(round(max(0.0, min(adj, max_adj))))


def _pyramid_html(elem):
    levels = elem.get("levels", []) or []
    n = max(1, len(levels))
    vb_h = _PYRAMID_VB_H
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
    total_h = float(_PYRAMID_VB_H)
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
        # trapezoid adj 按 OOXML 内缩语义反推（原始 val 0~100000，convert 端 ÷100000 闭环）
        adj = _pyramid_trap_adj(top_w, bot_w, layer_h)
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

def _rail_vertical(text):
    """rails 纵贯条排式判定：CJK 为主 → 竖排（逐字 upright）；
    ASCII 比例高（标准编号如 "DA/T 94-2022"）竖排会逐字散列，改横排小字
    （示例项目 v4 实战暴露，审计报告 §7.2-1）。"""
    if not text:
        return True
    ascii_cnt = sum(1 for ch in text if ord(ch) < 128 and not ch.isspace())
    return ascii_cnt * 2 < len(text)


def _layered_html(elem):
    """layered/4a 全宽层带（v1.4 重做）：左实色层签 + 同色系 tint 带 + 白芯 chip。

    旧版问题：层签小胶囊、组件淡药丸漂浮、短词折行（"CRM"→"CR M"）、
    层带近乎无底色。新版：整行带 1px 层色描边容器，带体为层色 9% tint，
    chip 白芯 + 层色描边，短词不折行（white-space:nowrap）。
    可选 rails: [str] 右侧纵向贯穿条（安全体系/标准规范等治理面）。
    """
    rows = _layer_rows(elem)
    rails = [str(r) for r in elem.get("rails", []) or []]
    rows_html = []
    for r in rows:
        c = r["color"]
        band = theme.mix(c, theme.WHITE, 0.91)
        border = theme.mix(c, theme.WHITE, 0.45)
        chips = "".join(
            f'<span data-editable="true" style="display:inline-block;background:{theme.WHITE};color:{c};'
            f'border:1px solid {border};border-radius:6px;padding:5px 14px;font-size:13px;'
            f'font-weight:600;margin:4px 8px 4px 0;white-space:nowrap;line-height:1.4;">{_esc(cp)}</span>'
            for cp in r["components"])
        desc = (f'<div style="font-size:12px;color:{theme.TEXT_SUB};margin-bottom:6px;" data-editable="true">{_esc(r["desc"])}</div>'
                if r["desc"] else "")
        rows_html.append(
            f'<div style="display:flex;align-items:stretch;margin-bottom:10px;border-radius:10px;'
            f'overflow:hidden;border:1px solid {border};min-height:64px;">'
            f'<div style="flex:0 0 132px;background:{c};color:{theme.WHITE};font-weight:700;'
            f'font-size:15px;display:flex;align-items:center;justify-content:center;text-align:center;'
            f'padding:14px 10px;line-height:1.35;" data-editable="true">{_esc(r["name"])}</div>'
            f'<div style="flex:1;background:{band};padding:10px 16px;display:flex;'
            f'flex-direction:column;justify-content:center;">{desc}'
            f'<div>{chips}</div></div></div>')
    rows_block = "".join(rows_html)
    if rails:
        rail_bg = theme.mix(theme.TEXT_STRONG, theme.WHITE, 0.88)

        def _rail_div(rl):
            if _rail_vertical(rl):
                layout_css = ('font-size:12px;writing-mode:vertical-rl;'
                              'text-orientation:upright;letter-spacing:2px;'
                              'padding:10px 0;')
            else:
                # ASCII 比例高：竖排逐字散列，改横排小字（允许折行）
                layout_css = ('font-size:10px;letter-spacing:0;'
                              'padding:6px 3px;line-height:1.4;')
            return (f'<div style="flex:0 0 32px;margin-left:10px;border-radius:8px;'
                    f'background:{rail_bg};border:1px solid {theme.BORDER};'
                    f'color:{theme.TEXT_STRONG};font-weight:700;{layout_css}'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'text-align:center;" data-editable="true">{_esc(rl)}</div>')

        rail_html = "".join(_rail_div(rl) for rl in rails)
        return (theme.section_open(elem)
                + f'\n<div style="display:flex;align-items:stretch;">'
                  f'<div style="flex:1;min-width:0;">{rows_block}</div>{rail_html}</div>\n'
                + theme.SECTION_CLOSE)
    return theme.section_open(elem) + "\n" + rows_block + "\n" + theme.SECTION_CLOSE


def _layered_pptd(elem, x, y, w):
    """layered/4a 全宽层带 pptd（v1.4，与 _layered_html 同源设计）。

    左实色层签 132 + 同色系 tint 带（层色 9%）+ 白芯层色描边 chip；
    内容垂直居中（旧版顶对齐，行一高就头重脚轻）；可选 rails 右侧纵贯条。
    """
    rows = _layer_rows(elem)
    rails = [str(r) for r in elem.get("rails", []) or []]
    sc = pe.PptdScaler(x, y, w)
    elems = []
    # —— viewbox 坐标（1200 宽）预排 ——
    rail_w, rail_gap = 32.0, 10.0
    rails_total = len(rails) * (rail_w + rail_gap) if rails else 0.0
    rows_right = 1200.0 - (rails_total + rail_gap if rails else 0.0)
    tag_w, gap = 132.0, 6.0
    body_x_v = tag_w + gap
    body_w_v = rows_right - body_x_v
    inner_x_v = body_x_v + 16
    inner_w_v = body_w_v - 32
    desc_fs = max(8, sc.len(11))
    chip_fs = max(9, sc.len(12))
    tag_fs = max(11, sc.len(14))
    cy = 0.0
    for i, r in enumerate(rows):
        c = r["color"]
        band = theme.mix(c, theme.WHITE, 0.91)
        border_c = theme.mix(c, theme.WHITE, 0.45)
        desc_h = 0.0
        if r["desc"]:
            desc_h = pe.stack_text_h(
                len(pe.wrap_lines(r["desc"], desc_fs,
                                  sc.len(inner_w_v) - 2 * INSET_X)), desc_fs)
        chip_h = sc.len(pe.chips_height(r["components"], sc.len(inner_w_v),
                                        font_size=chip_fs, chip_h=26))
        content_h = desc_h + (GAP_SM if r["desc"] else 0) + chip_h
        row_h = max(sc.len(64), content_h + 2 * INSET_Y)
        tag_lines = len(pe.wrap_lines(r["name"], tag_fs, sc.len(tag_w) - sc.len(12)))
        row_h = max(row_h, pe.stack_text_h(tag_lines, tag_fs) + 2 * INSET_Y)
        content_top = cy + (row_h - content_h) / 2  # 垂直居中
        elems.append(pe.shape(f"ly{i}-tag", [x, y + cy, sc.len(tag_w), row_h],
                              "roundRect", fill=c, adjustments=[12000]))
        elems.append(pe.text(f"ly{i}-tagt", [x, y + cy, sc.len(tag_w), row_h],
                             r["name"], font_size=tag_fs, color=theme.WHITE, bold=True))
        elems.append(pe.shape(f"ly{i}-body", [x + sc.len(body_x_v), y + cy,
                                              sc.len(body_w_v), row_h],
                              "roundRect", fill=band, adjustments=[6000],
                              border={"style": "solid", "width": 1,
                                      "color": border_c}))
        if r["desc"]:
            elems.append(pe.text(f"ly{i}-desc",
                                 [x + sc.len(inner_x_v), y + content_top,
                                  sc.len(inner_w_v), desc_h],
                                 r["desc"], font_size=desc_fs,
                                 color=theme.TEXT_SUB, align=("left", "middle")))
        chip_elems, _ = pe.emit_chips(
            f"ly{i}", r["components"], x + sc.len(inner_x_v),
            y + content_top + desc_h + (GAP_SM if r["desc"] else 0),
            sc.len(inner_w_v), font_size=chip_fs, chip_h=26,
            fill=theme.WHITE, color=c,
            border={"style": "solid", "width": 1, "color": border_c})
        elems.extend(chip_elems)
        cy += row_h + GAP_MD
    total_h = cy - GAP_MD if rows else 0.0
    for i, rl in enumerate(rails):
        rx_v = rows_right + rail_gap + i * (rail_w + rail_gap)
        rail_bg = theme.mix(theme.TEXT_STRONG, theme.WHITE, 0.88)
        elems.append(pe.shape(f"ly-rail{i}", [x + sc.px(rx_v), y, sc.len(rail_w), total_h],
                              "roundRect", fill=rail_bg, adjustments=[24000],
                              border={"style": "solid", "width": 1,
                                      "color": theme.BORDER}))
        # 窄文本框 + CJK 逐字换行 = 竖排效果（显式 \n 避免词中硬折）；
        # ASCII 比例高的文本（标准编号）逐字竖排会散列，改横排小字
        if _rail_vertical(rl):
            rail_text = "\n".join(rl) if len(rl) <= 8 else rl
            rail_fs = max(9, sc.len(12))
        else:
            rail_text = rl
            rail_fs = max(8, sc.len(10))
        elems.append(pe.text(f"ly-rail{i}-t",
                             [x + sc.px(rx_v), y, sc.len(rail_w), total_h],
                             rail_text, font_size=rail_fs,
                             color=theme.TEXT_STRONG, bold=True,
                             align=("center", "middle")))
    return elems, total_h


# ---------------------------------------------------------------------------
# infra（第 34 种）：IT 基础设施标准图形
#   zones: [{name, desc?, nodes: [{name, icon?, desc?}]}]   分区列（DMZ/内网/云…）
#   links: [{from: "区名.节点名", to: ..., label?, mode?}]  与 deployment 同约定
#   icon: server | db | storage | cloud | firewall | switch | router | lb |
#         terminal | user | shield | monitor | container | app（缺省=双字标签块）
# ---------------------------------------------------------------------------

_INFRA_ALIAS = {
    "数据库": "db", "存储": "db", "db2": "db", "mysql": "db", "oracle": "db",
    "服务器": "server", "主机": "server", "vm": "server", "虚拟机": "server",
    "云": "cloud", "互联网": "cloud", "internet": "cloud", "公网": "cloud",
    "防火墙": "firewall", "fw": "firewall",
    "交换机": "switch", "sw": "switch",
    "路由器": "router", "网关": "router",
    "负载均衡": "lb", "负载": "lb", "f5": "lb", "nginx": "lb",
    "终端": "terminal", "pc": "terminal", "电脑": "terminal", "客户端": "terminal",
    "用户": "user", "人员": "user",
    "安全": "shield", "盾": "shield", "waf": "shield", "零信任": "shield",
    "监控": "monitor", "大屏": "monitor", "运维": "monitor",
    "容器": "container", "k8s": "container", "docker": "container",
    "应用": "app", "系统": "app", "服务": "app",
}


def _infra_icon_key(nd):
    icon = (nd.get("icon", "") if isinstance(nd, dict) else "") or ""
    icon = icon.strip().lower()
    if icon:
        return _INFRA_ALIAS.get(icon, icon)
    name = (nd.get("name", "") if isinstance(nd, dict) else str(nd))
    for kw, key in _INFRA_ALIAS.items():
        if kw in name.lower() or kw in name:
            return key
    return "app"


def _infra_monogram(name):
    """infra PPTD 文本象形（OOXML 无描边 glyph 方言时的盒内标识）。

    返回 (文本, 建议字号)：拉丁 ≤4 字母全保留（WAF 不再截成 W）；
    CJK ≤4 字全保留（防火墙 不再截成 防火）；更长取前 2 字。
    """
    import re as _re
    main = _re.sub(r'[（(].*?[)）]', '', str(name)).strip() or str(name)
    latin = _re.findall(r'[A-Za-z0-9]+', main)
    if latin and len(''.join(latin)) <= 4 and not _re.search(r'[一-鿿]', main):
        return main.upper(), 11.0
    n = len(main)
    if n <= 2:
        return main, 13.0
    if n <= 4:
        return main, 10.0
    return main[:2], 12.0


def _infra_glyph(icon, cx, cy, s, color):
    """基础设施标准图标（描边式 SVG glyph，外接边长 s，中心 cx,cy）。

    全部 stroke 风格统一 2.2px 线宽、圆角线帽；fallback=app 网格块。
    """
    h = s / 2.0
    x0, y0 = cx - h, cy - h
    sw = 2.2
    lc = 'stroke-linecap="round" stroke-linejoin="round"'
    g = []
    if icon == "server":
        # 机架服务器：外壳 + 两道硬盘位分隔线 + 每列指示灯
        bw, bh = s * 0.86, s * 0.68
        bx, by = cx - bw / 2, cy - bh / 2
        g.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="4" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        for r_ in (1, 2):
            ly_ = by + bh * r_ / 3
            g.append(f'<line x1="{bx}" y1="{ly_}" x2="{bx + bw}" y2="{ly_}" stroke="{color}" stroke-width="{sw * 0.6}"/>')
        for r_ in range(3):
            dy_ = by + bh * (r_ + 0.5) / 3
            g.append(f'<circle cx="{bx + bw * 0.18}" cy="{dy_}" r="{s * 0.035}" fill="{color}"/>')
            g.append(f'<line x1="{bx + bw * 0.34}" y1="{dy_}" x2="{bx + bw * 0.80}" y2="{dy_}" stroke="{color}" stroke-width="{sw * 0.6}" {lc}/>')
    elif icon in ("db", "storage"):
        ry = s * 0.16
        g.append(f'<path d="M{x0},{cy - s * 0.26} v{s * 0.52} a{h},{ry} 0 0 0 {s},0 v{-s * 0.52}" fill="none" stroke="{color}" stroke-width="{sw}" {lc}/>')
        g.append(f'<ellipse cx="{cx}" cy="{cy - s * 0.26}" rx="{h}" ry="{ry}" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<path d="M{x0},{cy} a{h},{ry} 0 0 0 {s},0" fill="none" stroke="{color}" stroke-width="{sw * 0.55}" opacity="0.6"/>')
    elif icon == "cloud":
        # 标准云形：左鼓包→顶穹→右鼓包→右下收边，底边直线闭合；所有增量随 s 缩放
        g.append(f'<path d="M{cx - s * 0.34},{cy + s * 0.20} '
                 f'a{s * 0.15},{s * 0.15} 0 0 1 {-s * 0.02},{-s * 0.28} '
                 f'a{s * 0.24},{s * 0.24} 0 0 1 {s * 0.36},{-s * 0.18} '
                 f'a{s * 0.18},{s * 0.18} 0 0 1 {s * 0.32},{s * 0.16} '
                 f'a{s * 0.16},{s * 0.16} 0 0 1 {-s * 0.06},{s * 0.26} z" '
                 f'fill="none" stroke="{color}" stroke-width="{sw}" {lc}/>')
    elif icon == "firewall":
        bw, bh = s * 0.90, s * 0.64
        bx, by = cx - bw / 2, cy - bh / 2
        g.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="3" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<line x1="{bx}" y1="{cy}" x2="{bx + bw}" y2="{cy}" stroke="{color}" stroke-width="{sw * 0.6}"/>')
        g.append(f'<line x1="{cx}" y1="{by}" x2="{cx}" y2="{cy}" stroke="{color}" stroke-width="{sw * 0.6}"/>')
        g.append(f'<line x1="{bx + bw * 0.28}" y1="{cy}" x2="{bx + bw * 0.28}" y2="{by + bh}" stroke="{color}" stroke-width="{sw * 0.6}"/>')
        g.append(f'<line x1="{bx + bw * 0.72}" y1="{cy}" x2="{bx + bw * 0.72}" y2="{by + bh}" stroke="{color}" stroke-width="{sw * 0.6}"/>')
    elif icon == "switch":
        bw, bh = s * 0.88, s * 0.46
        bx, by = cx - bw / 2, cy - bh / 2
        g.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="5" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        ay1, ay2 = cy - bh * 0.18, cy + bh * 0.18
        g.append(f'<path d="M{bx + bw * 0.18},{ay1} H{bx + bw * 0.82} m{-5},-4 l5,4 l-5,4" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
        g.append(f'<path d="M{bx + bw * 0.82},{ay2} H{bx + bw * 0.18} m5,-4 l-5,4 l5,4" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
    elif icon == "router":
        # 四向交叉箭头（与 switch 双行往返区分）
        bw, bh = s * 0.88, s * 0.46
        bx, by = cx - bw / 2, cy - bh / 2
        g.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="5" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<path d="M{bx + bw * 0.14},{cy} H{bx + bw * 0.86} m{-5},-4 l5,4 l-5,4" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
        g.append(f'<path d="M{bx + bw * 0.14},{cy} m5,-4 l-5,4 l5,4" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
        g.append(f'<path d="M{cx},{cy - bh * 0.30} V{cy + bh * 0.30} m-4,-5 l4,5 l4,-5" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
        g.append(f'<path d="M{cx},{cy - bh * 0.30} m-4,5 l4,-5 l4,5" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
    elif icon == "lb":
        # 中心点一分三分发（hub 语义）
        bw, bh = s * 0.88, s * 0.46
        bx, by = cx - bw / 2, cy - bh / 2
        g.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="5" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<circle cx="{cx}" cy="{cy}" r="{s * 0.045}" fill="{color}"/>')
        g.append(f'<line x1="{bx + bw * 0.14}" y1="{cy}" x2="{cx}" y2="{cy}" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
        g.append(f'<line x1="{cx}" y1="{cy}" x2="{bx + bw * 0.86}" y2="{cy - bh * 0.28}" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
        g.append(f'<line x1="{cx}" y1="{cy}" x2="{bx + bw * 0.86}" y2="{cy + bh * 0.28}" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
    elif icon == "terminal":
        mw, mh = s * 0.84, s * 0.52
        g.append(f'<rect x="{cx - mw / 2}" y="{cy - mh / 2 - s * 0.06}" width="{mw}" height="{mh}" rx="4" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<line x1="{cx}" y1="{cy + mh / 2 - s * 0.06}" x2="{cx}" y2="{cy + s * 0.30}" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<line x1="{cx - s * 0.20}" y1="{cy + s * 0.34}" x2="{cx + s * 0.20}" y2="{cy + s * 0.34}" stroke="{color}" stroke-width="{sw}" {lc}/>')
    elif icon == "user":
        g.append(f'<circle cx="{cx}" cy="{cy - s * 0.16}" r="{s * 0.18}" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<path d="M{cx - s * 0.32},{cy + s * 0.36} a{s * 0.32},{s * 0.30} 0 0 1 {s * 0.64},0" fill="none" stroke="{color}" stroke-width="{sw}" {lc}/>')
    elif icon == "shield":
        g.append(f'<path d="M{cx},{y0 + s * 0.04} L{x0 + s * 0.88},{y0 + s * 0.20} v{s * 0.34} '
                 f'c0,{s * 0.26} -{s * 0.16},{s * 0.42} -{s * 0.38},{s * 0.50} '
                 f'c-{s * 0.22},-s * 0.08 -{s * 0.38},-s * 0.24 -{s * 0.38},-s * 0.50 '
                 f'v{-s * 0.34} z" fill="none" stroke="{color}" stroke-width="{sw}" {lc}/>')
        g.append(f'<path d="M{cx - s * 0.16},{cy} l{s * 0.11},{s * 0.12} l{s * 0.21},-{s * 0.24}" fill="none" stroke="{color}" stroke-width="{sw}" {lc}/>')
    elif icon == "monitor":
        mw, mh = s * 0.86, s * 0.60
        bx, by = cx - mw / 2, cy - mh / 2
        g.append(f'<rect x="{bx}" y="{by}" width="{mw}" height="{mh}" rx="4" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<polyline points="{bx + mw * 0.14},{by + mh * 0.72} {bx + mw * 0.38},{by + mh * 0.44} {bx + mw * 0.58},{by + mh * 0.58} {bx + mw * 0.86},{by + mh * 0.24}" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
    elif icon == "container":
        fw = s * 0.52
        g.append(f'<rect x="{cx - fw / 2 - s * 0.06}" y="{cy - fw / 2 + s * 0.08}" width="{fw}" height="{fw}" fill="none" stroke="{color}" stroke-width="{sw}"/>')
        g.append(f'<path d="M{cx - fw / 2 - s * 0.06},{cy - fw / 2 + s * 0.08} l{s * 0.14},-{s * 0.14} h{fw} l{s * 0.14},{s * 0.14} m0,0 v{fw} l-{s * 0.14},{s * 0.14}" fill="none" stroke="{color}" stroke-width="{sw * 0.7}" {lc}/>')
    else:  # app：四宫格圆角块
        aw, cell, gp = s * 0.80, s * 0.30, s * 0.10
        ax, ay = cx - aw / 2, cy - aw / 2
        for r in range(2):
            for c_ in range(2):
                g.append(f'<rect x="{ax + c_ * (cell + gp)}" y="{ay + r * (cell + gp)}" width="{cell}" height="{cell}" rx="3" fill="none" stroke="{color}" stroke-width="{sw * 0.8}"/>')
    return "".join(g)


def _infra_zones_geometry(elem):
    """infra 分区几何（HTML/PPTD 共用）：返回 (zone_rects, node_rects, max_h)。

    zone_rects: [(name, zx, zy, zw, zh)]；node_rects: {区名: {节点名: (nx, ny, nw, nh)}}。
    节点为 52px 图标盒，每区最多两列排布（节点 >3 时双列），比 deployment 单纵列紧凑。
    """
    zones = elem.get("zones", []) or []
    n = len(zones)
    zone_w = (1200 - 80 - 40 * (n - 1)) / max(1, n)
    ICON = 52.0
    TITLE_H = 40
    ROW_STEP = 108.0
    zone_rects, node_rects = [], {}
    for i, z in enumerate(zones):
        zname = z.get("name", "")
        zx = 40 + i * (zone_w + 40)
        nodes = z.get("nodes", []) or []
        cols = 2 if len(nodes) > 3 and zone_w >= 250 else 1
        rows = (len(nodes) + cols - 1) // cols
        zh = TITLE_H + max(1, rows) * ROW_STEP + 16
        zone_rects.append((zname, zx, 40, zone_w, zh))
        node_rects[zname] = {}
        for k, nd in enumerate(nodes):
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            col, row = k % cols, k // cols
            col_w = zone_w / cols
            nx = zx + col * col_w + (col_w - ICON) / 2
            ny = 40 + TITLE_H + 4 + row * ROW_STEP
            node_rects[zname][nd_name] = (nx, ny, ICON, ICON)
    max_h = max((z[4] for z in zone_rects), default=140)
    return zone_rects, node_rects, max_h


def _infra_text_width(s, font):
    """估算文本像素宽：CJK≈font，ASCII≈font*0.55。"""
    w = 0.0
    for ch in s:
        w += font if ord(ch) > 0x2E7F else font * 0.55
    return w


def _infra_occupancy(zones, node_rects):
    """节点占用区（HTML/PPTD 共用）：图标盒精确矩形 + 下方名称/desc 文本带（按实际文本估宽）。

    旧版用「盒横向 ±40、纵向 +34」单膨胀矩形过保守：同排节点间隙被余量吞掉，
    长跨区线全候选命中退 t=0.5 反压节点名（图标总览 v2 目检：HTTPS 100% 压
    办公终端名，§7.4）。改为盒/文本带两条精确矩形，文本带按 name/desc 估宽。
    """
    occ = []
    for z in zones:
        zmap = node_rects.get(z.get("name", ""), {})
        for nd in z.get("nodes", []) or []:
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            r = zmap.get(nd_name)
            if not r:
                continue
            nx, ny, nw, nh = r
            occ.append((nx, ny, nx + nw, ny + nh))
            desc = nd.get("desc", "") if isinstance(nd, dict) else ""
            bw = max(_infra_text_width(nd_name, 12.5), _infra_text_width(desc, 10.5)) + 12
            cx = nx + nw / 2
            occ.append((cx - bw / 2, ny + nh + 2, cx + bw / 2, ny + nh + 34))
    return occ


def _infra_link_label_pos(sx1, sy1, c1x, c1y, c2x, c2y, sx2, sy2, ltext, occupancy):
    """连线标签落点（HTML/PPTD 共用）：贝塞尔上取 t，白底药丸避让节点占用区。

    候选 t 依次试 (0.62, 0.5, 0.38, 0.75, 0.25)，取首个药丸矩形与所有占用区
    （图标盒 + 名称/desc 文本带，精确矩形）不相交者；全命中退重叠面积最小者。
    示例项目 v4 + 图标总览目检暴露：固定 t=0.62 会压目标侧节点文字（§7.4 闭环）。
    """
    tw = len(ltext) * 9.5 + 18

    def _pill(t):
        mt = 1 - t
        lx = mt**3 * sx1 + 3 * mt**2 * t * c1x + 3 * mt * t**2 * c2x + t**3 * sx2
        ly = mt**3 * sy1 + 3 * mt**2 * t * c1y + 3 * mt * t**2 * c2y + t**3 * sy2 - 16
        return lx, ly, (lx - tw / 2, ly - 10, lx + tw / 2, ly + 8)

    def _overlap(rect):
        px0, py0, px1, py1 = rect
        area = 0.0
        for ox0, oy0, ox1, oy1 in occupancy:
            ix = min(px1, ox1) - max(px0, ox0)
            iy = min(py1, oy1) - max(py0, oy0)
            if ix > 0 and iy > 0:
                area += ix * iy
        return area

    best, best_area = None, None
    for t in (0.62, 0.5, 0.38, 0.75, 0.25):
        lx, ly, rect = _pill(t)
        area = _overlap(rect)
        if area <= 0:
            return lx, ly
        if best_area is None or area < best_area:
            best, best_area = (lx, ly), area
    return best


def _infra_html(elem):
    """infra：分区容器 + 标准图标节点 + 跨区连线（SVG，双列紧凑布局）。"""
    zones = elem.get("zones", []) or []
    links = elem.get("links", []) or []
    zone_rects, node_rects, max_h = _infra_zones_geometry(elem)
    icon_fill = theme.mix(theme.BLUE, theme.WHITE, 0.93)
    icon_border = theme.mix(theme.BLUE, theme.WHITE, 0.55)
    parts = [f'<svg class="dg" viewBox="0 0 1200 {max_h + 40}" xmlns="http://www.w3.org/2000/svg">',
             f'<defs><marker id="dg-inf-arr" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L0,8 L11,4 z" fill="{theme.BLUE}"/></marker>'
             f'<marker id="dg-inf-arr-a" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L0,8 L11,4 z" fill="{theme.PURPLE}"/></marker></defs>']

    def _node_center(ref):
        if "." in ref:
            zn, nn = ref.split(".", 1)
            r = node_rects.get(zn, {}).get(nn)
            if r:
                return r[0] + r[2] / 2, r[1] + r[3] / 2
        return None

    def _zone_center(ref):
        z = next((zz for zz in zone_rects if zz[0] == ref), None)
        return (z[1] + z[3] / 2, z[2] + z[4] / 2) if z else None

    # 1) 分区容器 + 区间分隔虚线
    n = len(zone_rects)
    for i, (name, zx, zy, zw, zh) in enumerate(zone_rects):
        parts.append(f'<rect x="{zx}" y="{zy}" width="{zw}" height="{zh}" rx="12" fill="{theme.BG}" stroke="{theme.BORDER_STRONG}" stroke-width="1.2"/>')
        parts.append(f'<text x="{zx + zw / 2}" y="{zy + 26}" font-size="14" font-weight="700" fill="{theme.TEXT_STRONG}" text-anchor="middle" data-editable="true">{_esc(name)}</text>')
        if i < n - 1:
            lx = zx + zw + 20
            parts.append(f'<line x1="{lx}" y1="{zy + 40}" x2="{lx}" y2="{zy + zh}" stroke="{theme.BORDER_STRONG}" stroke-width="1.5" stroke-dasharray="6,4" stroke-opacity="0.6"/>')

    # 2) 连线（容器之上、节点之下；标签最后画，避免被节点盒遮挡）
    link_labels = []
    occupancy = _infra_occupancy(zones, node_rects)
    for link in links:
        a = _node_center(link.get("from", ""))
        b = _node_center(link.get("to", ""))
        if not a:
            a = _zone_center(link.get("from", ""))
        if not b:
            b = _zone_center(link.get("to", ""))
        if not a or not b:
            continue
        mode = link.get("mode", "sync")
        stroke = theme.PURPLE if mode == "async" else theme.BLUE
        dash = ' stroke-dasharray="6,4"' if mode == "async" else ""
        marker = "url(#dg-inf-arr-a)" if mode == "async" else "url(#dg-inf-arr)"
        ax, ay = a
        bx, by = b
        if abs(ax - bx) < 1:
            sx1, sy1 = ax, ay + 28
            sx2, sy2 = bx, by - 28
            c1x, c1y, c2x, c2y = ax, (sy1 + sy2) / 2, bx, (sy1 + sy2) / 2
        else:
            sx1, sy1 = ax + 30, ay
            sx2, sy2 = bx - 30, by
            c1x, c1y = ax + 30 + (bx - ax) * 0.4, ay
            c2x, c2y = bx - 30 - (bx - ax) * 0.4, by
        parts.append(f'<path d="M{sx1},{sy1} C{c1x},{c1y} {c2x},{c2y} {sx2},{sy2}" stroke="{stroke}" stroke-width="2" fill="none"{dash} marker-end="{marker}"/>')
        if link.get("label"):
            # 跨 zone link 写 label 会压中间节点文字（示例项目 v4 实战暴露，§7.2-2）：
            # 容量预算纪律是「跨 zone link 不写 label」，渲染器告警兜底
            def _ref_zone(ref):
                ref = str(ref)
                return ref.split(".", 1)[0] if "." in ref else ref
            if _ref_zone(link.get("from", "")) != _ref_zone(link.get("to", "")):
                print(f"[diagram] infra 跨 zone link 不建议写 label（压节点文字风险）："
                      f"{link.get('from')}→{link.get('to')} label={link['label']!r}，"
                      f"建议把说明并入节点 desc")
            # 标签避让节点占用区（候选 t 依次试，全命中退最小重叠）；统一在节点之后绘制
            lx, ly = _infra_link_label_pos(sx1, sy1, c1x, c1y, c2x, c2y, sx2, sy2,
                                           str(link["label"]), occupancy)
            link_labels.append((lx, ly, str(link["label"]), stroke))

    # 3) 图标节点
    for name, _zx, _zy, _zw, _zh in zone_rects:
        z = next(zz for zz in zones if zz.get("name", "") == name)
        for nd in z.get("nodes", []) or []:
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            r = node_rects[name].get(nd_name)
            if not r:
                continue
            nx, ny, nw, nh = r
            cx = nx + nw / 2
            parts.append(f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" rx="12" fill="{icon_fill}" stroke="{icon_border}" stroke-width="1.5"/>')
            parts.append(_infra_glyph(_infra_icon_key(nd), cx, ny + nh / 2, 30, theme.BLUE))
            parts.append(f'<text x="{cx}" y="{ny + nh + 15}" font-size="12" font-weight="600" fill="{theme.TEXT}" text-anchor="middle" data-editable="true">{_esc(nd_name)}</text>')
            if isinstance(nd, dict) and nd.get("desc"):
                parts.append(f'<text x="{cx}" y="{ny + nh + 30}" font-size="10" fill="{theme.TEXT_SUB}" text-anchor="middle" data-editable="true">{_esc(nd["desc"])}</text>')
    # 4) 连线标签（最上层，白底药丸保证可读）
    for lx, ly, ltext, lstroke in link_labels:
        tw = len(ltext) * 9.5 + 18
        parts.append(f'<rect x="{lx - tw / 2}" y="{ly - 10}" width="{tw}" height="18" rx="4" fill="white" fill-opacity="0.95"/>')
        parts.append(f'<text x="{lx}" y="{ly + 4}" font-size="11" fill="{lstroke}" text-anchor="middle" font-weight="600">{_esc(ltext)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _infra_pptd(elem, x, y, w):
    """infra pptd：与 HTML 同几何；图标盒 + 原生 preset 象形（can/cloud），
    其余双字标签（OOXML 无描边 glyph 方言，§图形铁律 原生 preset 优先）。"""
    zones = elem.get("zones", []) or []
    links = elem.get("links", []) or []
    zone_rects, node_rects, max_h = _infra_zones_geometry(elem)
    sc = pe.PptdScaler(x, y, w)
    icon_fill = theme.mix(theme.BLUE, theme.WHITE, 0.93)
    icon_border = theme.mix(theme.BLUE, theme.WHITE, 0.55)
    elems = []

    def _node_center(ref):
        if "." in ref:
            zn, nn = ref.split(".", 1)
            r = node_rects.get(zn, {}).get(nn)
            if r:
                return r[0] + r[2] / 2, r[1] + r[3] / 2
        return None

    def _zone_center(ref):
        z = next((zz for zz in zone_rects if zz[0] == ref), None)
        return (z[1] + z[3] / 2, z[2] + z[4] / 2) if z else None

    n = len(zone_rects)
    for i, (name, zx, zy, zw, zh) in enumerate(zone_rects):
        elems.append(pe.shape(f"inf-z-{i}", [sc.px(zx), sc.py(zy), sc.len(zw), sc.len(zh)],
                              "roundRect", fill=theme.BG, adjustments=[6000],
                              border={"style": "solid", "width": 1, "color": theme.BORDER_STRONG}))
        elems.append(pe.text(f"inf-z-{i}-t", [sc.px(zx), sc.py(zy + 6), sc.len(zw), sc.len(24)],
                             name, font_size=max(10, sc.len(14)), color=theme.TEXT_STRONG,
                             bold=True, align=("center", "middle")))
        if i < n - 1:
            lx = zx + zw + 20
            elems.append(pe.connector(f"inf-z-{i}-sep", sc.px(lx), sc.py(zy + 40),
                                      sc.px(lx), sc.py(zy + zh),
                                      color=theme.BORDER_STRONG, dash=True))

    link_labels = []
    occupancy = _infra_occupancy(zones, node_rects)
    for li, link in enumerate(links):
        a = _node_center(link.get("from", "")) or _zone_center(link.get("from", ""))
        b = _node_center(link.get("to", "")) or _zone_center(link.get("to", ""))
        if not a or not b:
            continue
        mode = link.get("mode", "sync")
        stroke = theme.PURPLE if mode == "async" else theme.BLUE
        ax, ay = a
        bx, by = b
        if abs(ax - bx) < 1:
            sx1, sy1, sx2, sy2 = ax, ay + 28, bx, by - 28
            c1x, c1y, c2x, c2y = ax, (sy1 + sy2) / 2, bx, (sy1 + sy2) / 2
        else:
            sx1, sy1, sx2, sy2 = ax + 30, ay, bx - 30, by
            c1x, c1y = ax + 30 + (bx - ax) * 0.4, ay
            c2x, c2y = bx - 30 - (bx - ax) * 0.4, by
        elems.append(pe.connector(f"inf-lnk-{li}", sc.px(sx1), sc.py(sy1),
                                  sc.px(sx2), sc.py(sy2), color=stroke,
                                  dash=mode == "async", arrow=("none", "stealth")))
        if link.get("label"):
            lx, ly = _infra_link_label_pos(sx1, sy1, c1x, c1y, c2x, c2y, sx2, sy2,
                                           str(link["label"]), occupancy)
            link_labels.append((li, lx, ly, str(link["label"]), stroke))

    for i, (name, _zx, _zy, _zw, _zh) in enumerate(zone_rects):
        z = next(zz for zz in zones if zz.get("name", "") == name)
        for k, nd in enumerate(z.get("nodes", []) or []):
            nd_name = nd.get("name", "") if isinstance(nd, dict) else str(nd)
            r = node_rects[name].get(nd_name)
            if not r:
                continue
            nx, ny, nw, nh = r
            key = _infra_icon_key(nd)
            elems.append(pe.shape(f"inf-n{i}-{k}", [sc.px(nx), sc.py(ny), sc.len(nw), sc.len(nh)],
                                  "roundRect", fill=icon_fill, adjustments=[12000],
                                  border={"style": "solid", "width": 1.5, "color": icon_border}))
            # 原生象形：db→can，cloud→cloud；其余双字标签
            if key in ("db", "storage"):
                gw, gh = 24.0, 22.0
                elems.append(pe.shape(f"inf-n{i}-{k}-g",
                                      [sc.px(nx + (nw - gw) / 2), sc.py(ny + (nh - gh) / 2),
                                       sc.len(gw), sc.len(gh)],
                                      "can", fill=theme.WHITE,
                                      border={"style": "solid", "width": 1.5, "color": theme.BLUE}))
            elif key == "cloud":
                gw, gh = 30.0, 20.0
                elems.append(pe.shape(f"inf-n{i}-{k}-g",
                                      [sc.px(nx + (nw - gw) / 2), sc.py(ny + (nh - gh) / 2),
                                       sc.len(gw), sc.len(gh)],
                                      "cloud", fill=theme.WHITE,
                                      border={"style": "solid", "width": 1.5, "color": theme.BLUE}))
            else:
                mono, mono_size = _infra_monogram(nd_name)
                elems.append(pe.text(f"inf-n{i}-{k}-g", [sc.px(nx), sc.py(ny), sc.len(nw), sc.len(nh)],
                                     mono, font_size=max(8, sc.len(mono_size)),
                                     color=theme.BLUE, bold=True, align=("center", "middle"), wrap=False))
            elems.append(pe.text(f"inf-n{i}-{k}-t", [sc.px(nx - 40), sc.py(ny + nh + 2), sc.len(nw + 80), sc.len(18)],
                                 nd_name, font_size=max(9, sc.len(10)),
                                 color=theme.TEXT, bold=True, align=("center", "middle")))
            if isinstance(nd, dict) and nd.get("desc"):
                elems.append(pe.text(f"inf-n{i}-{k}-d", [sc.px(nx - 50), sc.py(ny + nh + 20), sc.len(nw + 100), sc.len(16)],
                                     nd["desc"], font_size=max(8, sc.len(8)),
                                     color=theme.TEXT_SUB, align=("center", "middle")))
    # 连线标签（节点之后，白底药丸）
    for li, lx, ly, ltext, lstroke in link_labels:
        tw = len(ltext) * 9.5 + 18
        elems.append(pe.shape(f"inf-lnk-bg-{li}", [sc.px(lx - tw / 2), sc.py(ly - 9), sc.len(tw), sc.len(18)],
                              "roundRect", fill=theme.WHITE, adjustments=[22000],
                              border={"style": "solid", "width": 0.75, "color": theme.BORDER_STRONG}))
        elems.append(pe.text(f"inf-lnk-l-{li}", [sc.px(lx - tw / 2), sc.py(ly - 9), sc.len(tw), sc.len(18)],
                             ltext, font_size=max(8, sc.len(10)),
                             color=lstroke, align=("center", "middle"), wrap=False))
    return elems, sc.len(max_h + 40)


def render_html(elem):
    st = elem.get("subtype", "")
    if st in ("4a", "layered"):
        return _layered_html(elem)
    body = {"integration": _intg_html, "biz_overview": _biz_overview_html,
            "deployment": _deploy_html, "biz_it_mapping": _mapping_html,
            "platform_hub": _phub_html, "pyramid": _pyramid_html,
            "infra": _infra_html}.get(st)
    if not body:
        raise NotImplementedError(f"architecture/{st} 未实现")
    return theme.section_open(elem) + "\n" + body(elem) + "\n" + theme.SECTION_CLOSE


def render_pptd(elem, x, y, w, theme_name=None):
    """层叠行 pptd。返回 (元素列表, 消耗高度)。theme_name：v2 主题包名，
    biz_overview 三态 tone 取色用（D-092，与图例槽位 swatch 同源）。"""
    st = elem.get("subtype", "")
    if st in ("4a", "layered"):
        return _layered_pptd(elem, x, y, w)
    fn = {"integration": _intg_pptd, "biz_overview": _biz_overview_pptd,
          "deployment": _deploy_pptd, "biz_it_mapping": _mapping_pptd,
          "platform_hub": _phub_pptd, "pyramid": _pyramid_pptd,
          "infra": _infra_pptd}.get(st)
    if not fn:
        raise NotImplementedError(f"architecture/{st} 未实现")
    if st == "biz_overview":
        return _biz_overview_pptd(elem, x, y, w, theme_name)
    return fn(elem, x, y, w)
