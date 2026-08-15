# -*- coding: utf-8 -*-
"""relationship 类渲染器：org_tree / er_conceptual / er_logical / data_flow / value_chain /
biz_capability_tree / process_service_doc_mapping / cross_4a_reconcile / automation_table（9 种全部实现）。

HTML：SVG 肘形连接线 + 节点卡（根深蓝 / L1 白底蓝框 / L2+ 浅蓝底）。
pptd：肘线拆解为直线连接符组合（trunk + 横线 + stub，§4.1 全原生），
节点 roundRect + text。

spec：
  root: {name, desc, children: [{name, desc, children: [...]}]}
"""

from . import theme
from .theme import _esc
from . import pptd_emit as pe

NODE_W, NODE_H = 190, 56
LEVEL_GAP = 110
SIB_GAP = 40
TOP = 40


def _measure(node):
    """子树宽度：叶=NODE_W，内部=max(NODE_W, 子树和 + 间距)。"""
    children = node.get("children", []) or []
    if not children:
        node["_w"] = NODE_W
    else:
        total = sum(_measure(c) for c in children) + SIB_GAP * (len(children) - 1)
        node["_w"] = max(NODE_W, total)
    return node["_w"]


def _place(node, cx, depth, out):
    """以子树中心 cx 放置节点，递归子节点。out: (nodes, edges) 累积。"""
    x = cx - NODE_W / 2
    y = TOP + depth * LEVEL_GAP
    out[0].append({"x": x, "y": y, "depth": depth,
                   "name": node.get("name", ""), "desc": node.get("desc", "")})
    children = node.get("children", []) or []
    if children:
        total = sum(c["_w"] for c in children) + SIB_GAP * (len(children) - 1)
        cur = cx - total / 2
        for c in children:
            ccx = cur + c["_w"] / 2
            out[1].append((cx, y + NODE_H, ccx, TOP + (depth + 1) * LEVEL_GAP))
            _place(c, ccx, depth + 1, out)
            cur += c["_w"] + SIB_GAP


def _layout(elem):
    import copy
    root = copy.deepcopy(elem.get("root", {}) or {})
    _measure(root)
    out = ([], [])
    _place(root, root["_w"] / 2 + 30, 0, out)
    nodes, edges = out
    max_x = max(n["x"] + NODE_W for n in nodes) + 30
    depth_max = max(n["depth"] for n in nodes)
    vb_w = max(600, int(max_x))
    vb_h = TOP + (depth_max + 1) * LEVEL_GAP + 20
    return nodes, edges, vb_w, vb_h


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _node_fill():
    """org_tree 节点按深度的配色（调用时取 theme：P2-A2 风格透传，
    模块级快照会在 use_style 切换后滞留旧色板）。"""
    return {0: (theme.BLUE, theme.WHITE, theme.WHITE, None),
            1: (theme.WHITE, theme.BLUE, theme.BLUE, theme.BLUE),
            2: (theme.BLUE_LIGHT, theme.BORDER_STRONG, theme.TEXT, None)}


# ---------------------------------------------------------------------------
# P1：er_conceptual / er_logical / data_flow
# ---------------------------------------------------------------------------

def _er_layout(elem):
    """ER 实体网格布局：每行最多 per_row 个（行内 gap>=50），超行自动换行。
    跨行关系走行间肘形通道（Barker 纪律：无对角线）。"""
    entities = elem.get("entities", []) or []
    logical = elem.get("subtype") == "er_logical"
    ew = 220 if logical else 180
    per_row = max(1, (1200 - 2 * 40 + 50) // (ew + 50))
    row_gap = 110  # 行间距（跨行关系肘形通道）
    boxes = []
    y = 90
    i = 0
    while i < len(entities):
        row_ents = entities[i:i + per_row]
        rn = len(row_ents)
        gap = (1200 - 2 * 40 - rn * ew) / max(1, rn - 1) if rn > 1 else 0
        row_h = 0
        for j, e in enumerate(row_ents):
            attrs_h = 0
            if logical:
                n_attrs = len(e.get("attrs", []) or []) + len(e.get("pk", []) or []) + len(e.get("fk", []) or [])
                attrs_h = n_attrs * 28 + 12
            h = 60 + attrs_h
            row_h = max(row_h, h)
            boxes.append({
                "name": e.get("name", ""), "x": 40 + j * (ew + gap), "y": y,
                "w": ew, "h": h, "e": e, "row": i // per_row,
            })
        y += row_h + row_gap
        i += rn
    vb_h = y - row_gap + 80
    return boxes, 1200, vb_h


def _crow_foot_svg(x, y, direction, card):
    """基数符号：one=单杠，many=三爪。direction: 'left'（符号在线右端）或 'right'。"""
    sign = -1 if direction == "left" else 1
    parts = []
    if card == "one":
        bx = x + sign * 16
        parts.append(f'<line x1="{bx}" y1="{y - 9}" x2="{bx}" y2="{y + 9}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
    else:  # many
        bx = x + sign * 42
        parts.append(f'<line x1="{x}" y1="{y}" x2="{bx}" y2="{y}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
        parts.append(f'<line x1="{bx}" y1="{y}" x2="{bx + sign * 16}" y2="{y - 14}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
        parts.append(f'<line x1="{bx}" y1="{y}" x2="{bx + sign * 16}" y2="{y + 14}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
    return "\n".join(parts)


def _er_html(elem):
    boxes, vb_w, vb_h = _er_layout(elem)
    logical = elem.get("subtype") == "er_logical"
    relations = elem.get("relations", []) or []
    name2box = {b["name"]: b for b in boxes}
    parts = [f'<svg class="dg" viewBox="0 0 {vb_w} {vb_h}" xmlns="http://www.w3.org/2000/svg">']
    for ri, rel in enumerate(relations):
        a = name2box.get(rel.get("from", ""))
        b = name2box.get(rel.get("to", ""))
        if not a or not b:
            continue
        rtype = rel.get("type", "one_to_many")
        if a.get("row", 0) != b.get("row", 0):
            # 跨行肘形：上行框底中点 → 行间通道 → 下行框顶中点
            top_b, bot_b = (a, b) if a["y"] < b["y"] else (b, a)
            sx = top_b["x"] + top_b["w"] / 2
            sy = top_b["y"] + top_b["h"]
            tx = bot_b["x"] + bot_b["w"] / 2
            ty = bot_b["y"]
            mid_y = sy + (ty - sy) / 2
            parts.append(f'<path d="M {sx} {sy} L {sx} {mid_y} L {tx} {mid_y} L {tx} {ty}" fill="none" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
            ft = "M" if rtype == "many_to_many" else "1"
            tt = {"one_to_one": "1", "one_to_many": "N", "many_to_many": "M"}.get(rtype, "N")
            parts.append(f'<text x="{sx + 10}" y="{sy + 20}" font-size="12" fill="{theme.TEXT_STRONG}">{ft}</text>')
            parts.append(f'<text x="{tx - 20}" y="{ty - 8}" font-size="12" fill="{theme.TEXT_STRONG}">{tt}</text>')
            if rel.get("label"):
                lw = max(68, len(rel["label"]) * 13 + 16)
                lx = (sx + tx) / 2
                parts.append(f'<rect x="{lx - lw / 2}" y="{mid_y - 13}" width="{lw}" height="26" rx="13" fill="{theme.BLUE_LIGHT}"/>')
                parts.append(f'<text x="{lx}" y="{mid_y + 4}" font-size="12" font-weight="600" fill="{theme.BLUE}" text-anchor="middle">{_esc(rel["label"])}</text>')
            continue
        left, right = (a, b) if a["x"] < b["x"] else (b, a)
        between = [bb for bb in boxes
                   if bb.get("row") == left.get("row") and bb is not left and bb is not right
                   and left["x"] + left["w"] <= bb["x"] and bb["x"] + bb["w"] <= right["x"]]
        if between:
            # 中间隔框：顶部绕线（按关系索引错层，多线不重叠），避免横穿中间实体框
            sx = a["x"] + a["w"] / 2
            tx = b["x"] + b["w"] / 2
            ty = a["y"]
            wy = ty - 24 - (ri % 3) * 18
            parts.append(f'<path d="M {sx} {ty} L {sx} {wy} L {tx} {wy} L {tx} {ty}" fill="none" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
            ft = "M" if rtype == "many_to_many" else "1"
            tt = {"one_to_one": "1", "one_to_many": "N", "many_to_many": "M"}.get(rtype, "N")
            parts.append(f'<text x="{sx + 10}" y="{ty - 4}" font-size="12" fill="{theme.TEXT_STRONG}">{ft}</text>')
            parts.append(f'<text x="{tx - 20}" y="{ty - 4}" font-size="12" fill="{theme.TEXT_STRONG}">{tt}</text>')
            if rel.get("label"):
                lw = max(68, len(rel["label"]) * 13 + 16)
                lx = (sx + tx) / 2
                parts.append(f'<rect x="{lx - lw / 2}" y="{wy - 13}" width="{lw}" height="26" rx="13" fill="{theme.BLUE_LIGHT}"/>')
                parts.append(f'<text x="{lx}" y="{wy + 4}" font-size="12" font-weight="600" fill="{theme.BLUE}" text-anchor="middle">{_esc(rel["label"])}</text>')
            continue
        x1 = left["x"] + left["w"]
        x2 = right["x"]
        y1 = left["y"] + 30
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y1}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
        left_card = "one"
        right_card = {"one_to_one": "one", "one_to_many": "many", "many_to_many": "many"}.get(rtype, "many")
        if rtype == "many_to_many":
            left_card = "many"
        parts.append(_crow_foot_svg(x1, y1, "right", left_card))
        parts.append(_crow_foot_svg(x2, y1, "left", right_card))
        lt = "1" if left_card == "one" else "N"
        rt = "1" if right_card == "one" else ("M" if rtype == "many_to_many" else "N")
        parts.append(f'<text x="{x1 + 16}" y="{y1 - 8}" font-size="12" fill="{theme.TEXT_STRONG}">{lt}</text>')
        parts.append(f'<text x="{x2 - 24}" y="{y1 - 8}" font-size="12" fill="{theme.TEXT_STRONG}">{rt}</text>')
        if rel.get("label"):
            lw = max(68, len(rel["label"]) * 13 + 16)
            lx = (x1 + x2) / 2
            parts.append(f'<rect x="{lx - lw / 2}" y="{y1 - 13}" width="{lw}" height="26" rx="13" fill="{theme.BLUE_LIGHT}"/>')
            parts.append(f'<text x="{lx}" y="{y1 + 4}" font-size="12" font-weight="600" fill="{theme.BLUE}" text-anchor="middle">{_esc(rel["label"])}</text>')
    for b in boxes:
        e = b["e"]
        if not logical:
            parts.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" rx="10" fill="{theme.WHITE}" stroke="{theme.BLUE}" stroke-width="1.8"/>')
            parts.append(f'<text x="{b["x"] + b["w"] / 2}" y="{b["y"] + b["h"] / 2 + 5}" font-size="15" font-weight="700" fill="{theme.BLUE}" text-anchor="middle" data-editable="true">{_esc(b["name"])}</text>')
        else:
            parts.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" rx="8" fill="{theme.WHITE}" stroke="{theme.BLUE}" stroke-width="1.8"/>')
            parts.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="36" rx="8" fill="{theme.BLUE}"/>')
            parts.append(f'<text x="{b["x"] + b["w"] / 2}" y="{b["y"] + 24}" font-size="14" font-weight="700" fill="{theme.WHITE}" text-anchor="middle" data-editable="true">{_esc(b["name"])}</text>')
            ay = b["y"] + 36
            for pk in e.get("pk", []) or []:
                ay += 26
                parts.append(f'<text x="{b["x"] + 14}" y="{ay}" font-size="12" font-weight="700" fill="{theme.TEXT}">🔑 {_esc(pk)}</text>')
            for fk in e.get("fk", []) or []:
                ay += 26
                ref = fk.get("ref", "") if isinstance(fk, dict) else ""
                fname = fk.get("name", "") if isinstance(fk, dict) else str(fk)
                parts.append(f'<text x="{b["x"] + 14}" y="{ay}" font-size="12" font-style="italic" fill="{theme.BLUE}">{_esc(fname)} <tspan fill="{theme.TEXT_SUB}">FK → {_esc(ref)}</tspan></text>')
            for at in e.get("attrs", []) or []:
                ay += 26
                if isinstance(at, dict):
                    parts.append(f'<text x="{b["x"] + 14}" y="{ay}" font-size="12" fill="{theme.TEXT}">{_esc(at.get("name", ""))} <tspan fill="{theme.TEXT_SUB}">{_esc(at.get("type", ""))}</tspan></text>')
                else:
                    parts.append(f'<text x="{b["x"] + 14}" y="{ay}" font-size="12" fill="{theme.TEXT}">{_esc(at)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _er_pptd(elem, x, y, w):
    boxes, vb_w, vb_h = _er_layout(elem)
    logical = elem.get("subtype") == "er_logical"
    relations = elem.get("relations", []) or []
    name2box = {b["name"]: b for b in boxes}
    sc = pe.PptdScaler(x, y, w, vb_w)
    elems = []
    # 稠密关系网（>4 条）走图例模式：连接线只画走向，键名标注收底部图例带——
    # pptd 全图元素同组（dg{y}- 前缀），逐边标签在扇入场景必互压（lint I-1/I-2）。
    rich = len(relations) <= 4
    legend_items = []
    cn_seen = set()  # (端点框, 基数文字) 去重：同一框的同值基数只标一次（扇入去重）
    for ri, rel in enumerate(relations):
        a = name2box.get(rel.get("from", ""))
        b = name2box.get(rel.get("to", ""))
        if not a or not b:
            continue
        rtype = rel.get("type", "one_to_many")
        if rel.get("label"):
            legend_items.append(f"{rel.get('from', '')} → {rel.get('to', '')}：{rel['label']}")
        if a.get("row", 0) != b.get("row", 0):
            # 跨行肘形：上行框底中点 → 行间通道 → 下行框顶中点（三段原生连接符）
            top_b, bot_b = (a, b) if a["y"] < b["y"] else (b, a)
            sx = sc.px(top_b["x"] + top_b["w"] / 2)
            sy = sc.py(top_b["y"] + top_b["h"])
            tx = sc.px(bot_b["x"] + bot_b["w"] / 2)
            ty = sc.py(bot_b["y"])
            mid_y = (sy + ty) / 2
            if abs(sx - tx) < 2:
                # 同列跨行：中横段退化为点（bounds ≤30×30 会被 lint 当徽章），
                # 且可能压到中间带标题——直接一根竖线到底。
                elems.append(pe.connector(f"er{ri}-x0", sx, sy, tx, ty,
                                          arrow=("none", "arrow"), color=theme.TEXT_STRONG, width=1.5))
            else:
                elems.append(pe.connector(f"er{ri}-x0", sx, sy, sx, mid_y,
                                          arrow=("none", "none"), color=theme.TEXT_STRONG, width=1.5))
                elems.append(pe.connector(f"er{ri}-x1", sx, mid_y, tx, mid_y,
                                          arrow=("none", "none"), color=theme.TEXT_STRONG, width=1.5))
                elems.append(pe.connector(f"er{ri}-x2", tx, mid_y, tx, ty,
                                          arrow=("none", "arrow"), color=theme.TEXT_STRONG, width=1.5))
            if not rich:
                continue
            ft = "M" if rtype == "many_to_many" else "1"
            tt = {"one_to_one": "1", "one_to_many": "N", "many_to_many": "M"}.get(rtype, "N")
            if (top_b["name"], ft) not in cn_seen:
                cn_seen.add((top_b["name"], ft))
                elems.append(pe.text(f"er{ri}-cn-l", [sx + sc.len(8), sy + sc.len(6) + (ri % 3) * sc.len(12), sc.len(24), sc.len(16)],
                                     ft, font_size=max(8, sc.len(10)), color=theme.TEXT_STRONG))
            if (bot_b["name"], tt) not in cn_seen:
                cn_seen.add((bot_b["name"], tt))
                elems.append(pe.text(f"er{ri}-cn-r", [tx - sc.len(30), ty - sc.len(22) - (ri % 4) * sc.len(10), sc.len(24), sc.len(16)],
                                     tt, font_size=max(8, sc.len(10)), color=theme.TEXT_STRONG))
            if rel.get("label"):
                lw = max(68, len(rel["label"]) * 13 + 16)
                lx = (sx + tx) / 2
                elems.append(pe.shape(f"er{ri}-lb", [lx - sc.len(lw / 2), mid_y - sc.len(17), sc.len(lw), sc.len(34)],
                                      "roundRect", fill=theme.BLUE_LIGHT, adjustments=[50000]))
                elems.append(pe.text(f"er{ri}-lt", [lx - sc.len(lw / 2), mid_y - sc.len(17), sc.len(lw), sc.len(34)],
                                     rel["label"], font_size=max(9, sc.len(11)), color=theme.BLUE, bold=True))
            continue
        left, right = (a, b) if a["x"] < b["x"] else (b, a)
        if not rich:
            # 图例模式：简单水平直连（左框右缘 → 右框左缘，按索引错层），
            # 基数/标签全部收进底部图例带，避免 bounds 相交触发 lint。
            x1 = sc.px(left["x"] + left["w"])
            x2 = sc.px(right["x"])
            y1 = sc.py(left["y"] + left["h"] / 2) + (ri % 4) * sc.len(9) - sc.len(13)
            elems.append(pe.connector(f"er{ri}", x1, y1, x2, y1,
                                      arrow=("none", "arrow"), color=theme.TEXT_STRONG, width=1.5))
            continue
        # 同行关系统一走顶部绕线（按关系索引错层）：避免关系线横穿中间实体框，
        # 同时取消 crow's-foot 小符号（与标签/标题互压触发 lint I-1/I-2），
        # 基数语义由 1/N/M 文字标注保留。
        sx = sc.px(a["x"] + a["w"] / 2)
        tx = sc.px(b["x"] + b["w"] / 2)
        ty = sc.py(a["y"])
        wy = ty - sc.len(24) - (ri % 4) * sc.len(22)
        elems.append(pe.connector(f"er{ri}-w0", sx, ty, sx, wy,
                                  arrow=("none", "none"), color=theme.TEXT_STRONG, width=1.5))
        elems.append(pe.connector(f"er{ri}-w1", sx, wy, tx, wy,
                                  arrow=("none", "none"), color=theme.TEXT_STRONG, width=1.5))
        elems.append(pe.connector(f"er{ri}-w2", tx, wy, tx, ty,
                                  arrow=("none", "arrow"), color=theme.TEXT_STRONG, width=1.5))
        ft = "M" if rtype == "many_to_many" else "1"
        tt = {"one_to_one": "1", "one_to_many": "N", "many_to_many": "M"}.get(rtype, "N")
        cn_dy = sc.len(20) + (ri % 4) * sc.len(10)
        if (a["name"], ft) not in cn_seen:
            cn_seen.add((a["name"], ft))
            elems.append(pe.text(f"er{ri}-cn-l", [sx + sc.len(8), ty - cn_dy, sc.len(24), sc.len(16)],
                                 ft, font_size=max(8, sc.len(10)), color=theme.TEXT_STRONG))
        if (b["name"], tt) not in cn_seen:
            cn_seen.add((b["name"], tt))
            elems.append(pe.text(f"er{ri}-cn-r", [tx - sc.len(30), ty - cn_dy, sc.len(24), sc.len(16)],
                                 tt, font_size=max(8, sc.len(10)), color=theme.TEXT_STRONG))
        if rel.get("label"):
            lw = max(68, len(rel["label"]) * 13 + 16)
            lx = (sx + tx) / 2
            elems.append(pe.shape(f"er{ri}-lb", [lx - sc.len(lw / 2), wy - sc.len(17), sc.len(lw), sc.len(34)],
                                  "roundRect", fill=theme.BLUE_LIGHT, adjustments=[50000]))
            elems.append(pe.text(f"er{ri}-lt", [lx - sc.len(lw / 2), wy - sc.len(17), sc.len(lw), sc.len(34)],
                                 rel["label"], font_size=max(9, sc.len(11)), color=theme.BLUE, bold=True))
        continue
    for bi, b in enumerate(boxes):
        bx, by = sc.px(b["x"]), sc.py(b["y"])
        bw, bh = sc.len(b["w"]), sc.len(b["h"])
        if not logical:
            elems.append(pe.shape(f"erb{bi}", [bx, by, bw, bh], "roundRect", fill=theme.CARD,
                                  adjustments=[12000],
                                  border={"style": "solid", "width": 1.8, "color": theme.BLUE}))
            # 标题文本收窄为居中横带：全框 bounds 会与顶部绕线/基数标注
            # 几何相交（视觉不压字，但 lint 按 bounds 判 I-1/I-2）
            elems.append(pe.text(f"erb{bi}-t", [bx, by + bh / 2 - sc.len(12), bw, sc.len(24)],
                                 b["name"],
                                 font_size=max(11, sc.len(15)), color=theme.BLUE, bold=True))
        else:
            e = b["e"]
            elems.append(pe.shape(f"erb{bi}", [bx, by, bw, bh], "roundRect", fill=theme.CARD,
                                  adjustments=[6000],
                                  border={"style": "solid", "width": 1.8, "color": theme.BLUE}))
            elems.append(pe.shape(f"erb{bi}-h", [bx, by, bw, sc.len(36)], "rect", fill=theme.BLUE))
            elems.append(pe.text(f"erb{bi}-t", [bx, by, bw, sc.len(36)], b["name"],
                                 font_size=max(11, sc.len(14)), color=theme.WHITE, bold=True))
            lines = []
            for pk in e.get("pk", []) or []:
                lines.append(f"PK {pk}")
            for fk in e.get("fk", []) or []:
                if isinstance(fk, dict):
                    lines.append(f"FK {fk.get('name', '')} → {fk.get('ref', '')}")
                else:
                    lines.append(f"FK {fk}")
            for at in e.get("attrs", []) or []:
                if isinstance(at, dict):
                    lines.append(f"{at.get('name', '')} {at.get('type', '')}".rstrip())
                else:
                    lines.append(str(at))
            elems.append(pe.text(f"erb{bi}-a", [bx + sc.len(12), by + sc.len(40), bw - sc.len(20), bh - sc.len(44)],
                                 "\n".join(lines) + "\n", font_size=max(8, sc.len(11)),
                                 color=theme.TEXT, align=("left", "top")))
    total_h = sc.len(vb_h)
    if legend_items:
        # 图例带：稠密关系网的边语义收底部单段小字（避免逐边标签互压）
        lg_size = max(8, sc.len(10))
        lg_text = "关系：" + " ｜ ".join(legend_items)
        lg_lines = pe.wrap_lines(lg_text, lg_size, w)
        lg_h = pe.stack_text_h(len(lg_lines), lg_size)
        elems.append(pe.text("er-legend", [x, y + total_h + sc.len(6), w, lg_h],
                             lg_text, font_size=lg_size, color=theme.TEXT_SUB,
                             align=("left", "top")))
        total_h += sc.len(6) + lg_h
    return elems, total_h


def _df_layout(nodes):
    """data_flow 分列布局：source | process | store | sink 四列，列内纵排。"""
    col_x = {"source": 40, "process": 340, "store": 640, "sink": 940}
    groups = {c: [] for c in col_x}
    for nd in nodes:
        t = nd.get("type", "source")
        groups[t if t in groups else "source"].append(nd)
    nw, nh, vgap = 220, 52, 8
    pos = {}
    max_rows = 1
    for c, gx in col_x.items():
        g = groups[c]
        max_rows = max(max_rows, len(g))
        for k, nd in enumerate(g):
            pos[nd.get("name", "")] = (gx, 30 + k * (nh + vgap))
    vb_h = 30 + max_rows * (nh + vgap) + 24
    return pos, nw, nh, vb_h


def _df_html(elem):
    """data_flow：四列分层（source|process|store|sink），肘形连线。
    source/sink 直角矩形、process 圆角、store 三线开口框。"""
    nodes = elem.get("nodes", []) or []
    flows = elem.get("flows", []) or []
    pos, nw, nh, vb_h = _df_layout(nodes)
    parts = [f'<svg class="dg" viewBox="0 0 1200 {vb_h}" xmlns="http://www.w3.org/2000/svg">', theme.SVG_DEFS]
    for f in flows:
        a = pos.get(f.get("from", ""))
        b = pos.get(f.get("to", ""))
        if not a or not b:
            continue
        direction = f.get("direction", "push")
        ax, ay = a[0] + nw, a[1] + nh / 2
        bx, by = b[0], b[1] + nh / 2
        mid_x = ax + max(40, (bx - ax) / 2)
        dash = ' stroke-dasharray="6,4"' if direction == "pull" else ""
        marker_start = ' marker-start="url(#dgm-arr)"' if direction == "bidirectional" else ""
        parts.append(f'<path d="M {ax} {ay} L {mid_x} {ay} L {mid_x} {by} L {bx} {by}" fill="none" stroke="{theme.BLUE}" stroke-width="2"{dash}{marker_start} marker-end="url(#dgm-arr)"/>')
        label = f'{f.get("data", "")} · { {"push": "push", "pull": "pull", "bidirectional": "双向"}.get(direction, "push") }'
        parts.append(f'<text x="{(ax + mid_x) / 2}" y="{ay - 10}" font-size="11" fill="{theme.BLUE}" text-anchor="middle" data-editable="true">{_esc(label)}</text>')
    for nd in nodes:
        nx, ny = pos[nd.get("name", "")]
        t = nd.get("type", "source")
        name = nd.get("name", "")
        if t == "store":
            parts.append(f'<line x1="{nx}" y1="{ny}" x2="{nx}" y2="{ny + nh}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
            parts.append(f'<line x1="{nx + nw}" y1="{ny}" x2="{nx + nw}" y2="{ny + nh}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
            parts.append(f'<line x1="{nx}" y1="{ny + nh}" x2="{nx + nw}" y2="{ny + nh}" stroke="{theme.TEXT_STRONG}" stroke-width="1.8"/>')
            parts.append(f'<text x="{nx + nw / 2}" y="{ny + 22}" font-size="13" font-weight="700" fill="{theme.TEXT_STRONG}" text-anchor="middle" data-editable="true">{_esc(name)}</text>')
            parts.append(f'<text x="{nx + nw / 2}" y="{ny + 40}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle">store</text>')
        elif t == "process":
            parts.append(f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" rx="12" fill="{theme.GREEN_LIGHT}" stroke="{theme.GREEN}" stroke-width="1.8"/>')
            parts.append(f'<text x="{nx + nw / 2}" y="{ny + 22}" font-size="13" font-weight="700" fill="{theme.GREEN}" text-anchor="middle" data-editable="true">{_esc(name)}</text>')
            parts.append(f'<text x="{nx + nw / 2}" y="{ny + 40}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle">process</text>')
        else:
            parts.append(f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" rx="4" fill="{theme.WHITE}" stroke="{theme.BLUE}" stroke-width="1.8"/>')
            parts.append(f'<text x="{nx + nw / 2}" y="{ny + 22}" font-size="13" font-weight="700" fill="{theme.BLUE}" text-anchor="middle" data-editable="true">{_esc(name)}</text>')
            parts.append(f'<text x="{nx + nw / 2}" y="{ny + 40}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle">{t}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _df_pptd(elem, x, y, w):
    nodes = elem.get("nodes", []) or []
    flows = elem.get("flows", []) or []
    sc = pe.PptdScaler(x, y, w)
    pos, nw, nh, vb_h = _df_layout(nodes)
    elems = []
    for fi, f in enumerate(flows):
        a = pos.get(f.get("from", ""))
        b = pos.get(f.get("to", ""))
        if not a or not b:
            continue
        direction = f.get("direction", "push")
        both = direction == "bidirectional"
        ax = sc.px(a[0] + nw)
        ay = sc.py(a[1] + nh / 2)
        bx = sc.px(b[0])
        by = sc.py(b[1] + nh / 2)
        mid_x = ax + max(sc.len(40), (bx - ax) / 2)
        elems.append(pe.connector(f"df{fi}-x0", ax, ay, mid_x, ay,
                                  arrow=("none", "none"), color=theme.BLUE,
                                  dash=(direction == "pull")))
        elems.append(pe.connector(f"df{fi}-x1", mid_x, ay, mid_x, by,
                                  arrow=("none", "none"), color=theme.BLUE,
                                  dash=(direction == "pull")))
        if direction == "push":
            # 实心方向：单向数据流末段箭头用块箭头 preset（D-2 块箭头扩充）；
            # pull（虚线）/bidirectional（双箭头）仍走 connector（细关系）
            arrow_w = sc.len(28)
            elems.append(pe.connector(f"df{fi}-x2", mid_x, by, bx - arrow_w, by,
                                      arrow=("none", "none"), color=theme.BLUE))
            elems.append(pe.block_arrow(f"df{fi}-a", [bx - arrow_w, by - sc.len(12),
                                                       arrow_w, sc.len(24)],
                                        "rightArrow", fill=theme.BLUE))
        else:
            elems.append(pe.connector(f"df{fi}-x2", mid_x, by, bx, by,
                                      arrow=("arrow" if both else "none", "arrow"),
                                      color=theme.BLUE, dash=(direction == "pull")))
        label = f'{f.get("data", "")} · { {"push": "push", "pull": "pull", "bidirectional": "双向"}.get(direction, "push") }'
        label_x = (ax + mid_x) / 2
        elems.append(pe.text(f"df{fi}-l", [label_x - sc.len(100), sc.py(a[1] + nh / 2 - 24), sc.len(200), sc.len(16)],
                             label, font_size=max(8, sc.len(11)), color=theme.BLUE))
    for ni, nd in enumerate(nodes):
        nx, ny = pos[nd.get("name", "")]
        t = nd.get("type", "source")
        name = nd.get("name", "")
        if t == "store":
            elems.append(pe.shape(f"dfn{ni}", [sc.px(nx), sc.py(ny), sc.len(nw), sc.len(nh)], "can",
                                  fill=theme.CARD,
                                  border={"style": "solid", "width": 1.8, "color": theme.TEXT_STRONG}))
            elems.append(pe.text(f"dfn{ni}-t", [sc.px(nx), sc.py(ny) + sc.len(12), sc.len(nw), sc.len(22)],
                                 name, font_size=max(10, sc.len(13)), color=theme.TEXT_STRONG, bold=True))
            elems.append(pe.text(f"dfn{ni}-s", [sc.px(nx), sc.py(ny) + sc.len(36), sc.len(nw), sc.len(16)],
                                 "store", font_size=max(8, sc.len(11)), color=theme.TEXT_SUB))
        elif t == "process":
            elems.append(pe.shape(f"dfn{ni}", [sc.px(nx), sc.py(ny), sc.len(nw), sc.len(nh)], "roundRect",
                                  fill=theme.GREEN_LIGHT, adjustments=[15000],
                                  border={"style": "solid", "width": 1.8, "color": theme.GREEN}))
            elems.append(pe.text(f"dfn{ni}-t", [sc.px(nx), sc.py(ny) + sc.len(12), sc.len(nw), sc.len(22)],
                                 name, font_size=max(10, sc.len(13)), color=theme.GREEN, bold=True))
            elems.append(pe.text(f"dfn{ni}-s", [sc.px(nx), sc.py(ny) + sc.len(36), sc.len(nw), sc.len(16)],
                                 "process", font_size=max(8, sc.len(11)), color=theme.TEXT_SUB))
        else:
            elems.append(pe.shape(f"dfn{ni}", [sc.px(nx), sc.py(ny), sc.len(nw), sc.len(nh)], "rect",
                                  fill=theme.CARD,
                                  border={"style": "solid", "width": 1.8, "color": theme.BLUE}))
            elems.append(pe.text(f"dfn{ni}-t", [sc.px(nx), sc.py(ny) + sc.len(12), sc.len(nw), sc.len(22)],
                                 name, font_size=max(10, sc.len(13)), color=theme.BLUE, bold=True))
            elems.append(pe.text(f"dfn{ni}-s", [sc.px(nx), sc.py(ny) + sc.len(36), sc.len(nw), sc.len(16)],
                                 t, font_size=max(8, sc.len(11)), color=theme.TEXT_SUB))
    return elems, sc.len(vb_h)


# ---------------------------------------------------------------------------
# P1：value_chain / biz_capability_tree / process_service_doc_mapping /
#     cross_4a_reconcile / automation_table
# ---------------------------------------------------------------------------

def _vc_html(elem):
    primary = elem.get("primary", []) or []
    support = elem.get("support", []) or []
    blues = ["#14496B", "#1B5E8A", "#2A6E9C", "#4A7FA5", "#2F7D5F", "#3D9070"]
    parts = []
    if support:
        sup = "".join(f'<div style="flex:1;background:{theme.GREEN_LIGHT};color:{theme.GREEN};font-weight:700;'
                      f'font-size:13px;text-align:center;border-radius:6px;padding:9px 6px;" data-editable="true">{_esc(s)}</div>'
                      for s in support)
        parts.append(f'<div style="display:flex;gap:8px;margin-bottom:8px;">{sup}</div>')
    pv = []
    for i, p in enumerate(primary):
        c = blues[i % len(blues)]
        clip = "polygon(0 0, calc(100% - 20px) 0, 100% 50%, calc(100% - 20px) 100%, 0 100%);" if i == 0 else \
               "polygon(0 0, calc(100% - 20px) 0, 100% 50%, calc(100% - 20px) 100%, 0 100%, 20px 50%);"
        pv.append(f'<div style="flex:1;color:{theme.WHITE};font-weight:700;font-size:14px;text-align:center;'
                  f'padding:16px 10px 16px 26px;margin-right:4px;background:{c};clip-path:{clip}" data-editable="true">{_esc(p)}</div>')
    parts.append(f'<div style="display:flex;margin-top:14px;">{"".join(pv)}</div>')
    parts.append(f'<div style="text-align:right;font-size:12px;color:{theme.TEXT_SUB};margin-top:6px;font-style:italic;" data-editable="true">▲ 边际利润 = 价值创造 − 活动成本（chevron 颜色向绿过渡示意价值增值方向）</div>')
    return "\n".join(parts)


def _vc_pptd(elem, x, y, w):
    primary = elem.get("primary", []) or []
    support = elem.get("support", []) or []
    blues = ["#14496B", "#1B5E8A", "#2A6E9C", "#4A7FA5", "#2F7D5F", "#3D9070"]
    sc = pe.PptdScaler(x, y, w)
    elems = []
    cy = 0.0
    if support:
        n = len(support)
        sw = (1200 - 8 * (n - 1)) / n
        for i, s in enumerate(support):
            sx = sc.px(i * (sw + 8))
            elems.append(pe.shape(f"vc-s{i}", [sx, y, sc.len(sw), sc.len(40)], "roundRect",
                                  fill=theme.GREEN_LIGHT, adjustments=[10000]))
            elems.append(pe.text(f"vc-s{i}-t", [sx, y, sc.len(sw), sc.len(40)], s,
                                 font_size=max(9, sc.len(13)), color=theme.GREEN, bold=True))
        cy += 40 + 14
    n = len(primary)
    pw = (1200 - 4 * (n - 1)) / max(1, n)
    for i, p in enumerate(primary):
        c = blues[i % len(blues)]
        px = sc.px(i * (pw + 4))
        elems.append(pe.shape(f"vc-p{i}", [px, y + sc.len(cy), sc.len(pw), sc.len(56)], "chevron",
                              fill=c))
        elems.append(pe.text(f"vc-p{i}-t", [px + sc.len(14), y + sc.len(cy), sc.len(pw - 20), sc.len(56)],
                             p, font_size=max(9, sc.len(13)), color=theme.WHITE, bold=True))
    cy += 56
    return elems, sc.len(cy)


def _bct_html(elem):
    """biz_capability_tree：行式树（grid 行绑定对齐，禁手写 margin）。"""
    groups = elem.get("groups", []) or []
    def chip(t):
        return (f'<span style="display:inline-block;background:{theme.GREEN_LIGHT};color:{theme.GREEN};'
                          f'border-radius:4px;padding:4px 10px;font-size:12px;font-weight:600;margin:2px 5px 2px 0;" data-editable="true">{_esc(t)}</span>')
    parts = []
    for g in groups:
        rows = []
        for c in g.get("children", []) or []:
            items = c.get("items", []) or []
            rows.append(
                f'<div style="display:grid;grid-template-columns:190px 1fr;gap:0 28px;align-items:center;margin-bottom:8px;">'
                f'<div style="background:{theme.GREEN};color:{theme.WHITE};border-radius:6px;padding:8px 14px;font-weight:600;'
                f'font-size:13px;position:relative;" data-editable="true">{_esc(c.get("name", ""))}'
                f'<span style="position:absolute;right:-28px;top:50%;width:28px;border-top:2px solid {theme.BORDER_STRONG};"></span></div>'
                f'<div style="display:flex;flex-wrap:wrap;">{"".join(chip(i) for i in items)}</div></div>')
        parts.append(
            f'<div style="display:grid;grid-template-columns:170px 1fr;gap:0 28px;margin-bottom:18px;align-items:stretch;">'
            f'<div style="background:{theme.BLUE};color:{theme.WHITE};border-radius:8px;padding:12px 16px;font-weight:700;'
            f'display:flex;align-items:center;position:relative;" data-editable="true">{_esc(g.get("name", ""))}'
            f'<span style="position:absolute;right:-28px;top:50%;width:28px;border-top:2px solid {theme.BORDER_STRONG};"></span></div>'
            f'<div>{"".join(rows)}</div></div>')
    return "\n".join(parts)


def _bct_pptd(elem, x, y, w):
    groups = elem.get("groups", []) or []
    sc = pe.PptdScaler(x, y, w)
    elems = []
    cy = 0.0
    for gi, g in enumerate(groups):
        children = g.get("children", []) or []
        row_h = 44.0
        group_h = len(children) * (row_h + 8) - 8
        elems.append(pe.shape(f"bct-g{gi}", [x, y + sc.len(cy), sc.len(170), sc.len(group_h)],
                              "roundRect", fill=theme.BLUE, adjustments=[8000]))
        elems.append(pe.text(f"bct-g{gi}-t", [x, y + sc.len(cy), sc.len(170), sc.len(group_h)],
                             g.get("name", ""), font_size=max(10, sc.len(14)),
                             color=theme.WHITE, bold=True))
        elems.append(pe.connector(f"bct-g{gi}-lnk", sc.px(170), sc.py(cy + group_h / 2),
                                  sc.px(198), sc.py(cy + group_h / 2),
                                  arrow=("none", "none"), color=theme.BORDER_STRONG))
        for ci, c in enumerate(children):
            ry = cy + ci * (row_h + 8)
            elems.append(pe.shape(f"bct-g{gi}-c{ci}", [sc.px(198), y + sc.len(ry), sc.len(190), sc.len(row_h)],
                                  "roundRect", fill=theme.GREEN, adjustments=[8000]))
            elems.append(pe.text(f"bct-g{gi}-c{ci}-t", [sc.px(198), y + sc.len(ry), sc.len(190), sc.len(row_h)],
                                 c.get("name", ""), font_size=max(9, sc.len(13)),
                                 color=theme.WHITE, bold=True, align=("left", "middle")))
            elems.append(pe.connector(f"bct-g{gi}-c{ci}-lnk", sc.px(388), sc.py(ry + row_h / 2),
                                      sc.px(416), sc.py(ry + row_h / 2),
                                      arrow=("none", "none"), color=theme.BORDER_STRONG))
            items = "  ".join(c.get("items", []) or [])
            elems.append(pe.text(f"bct-g{gi}-c{ci}-i", [sc.px(424), y + sc.len(ry), w - sc.len(424), sc.len(row_h)],
                                 items, font_size=max(8, sc.len(11)), color=theme.GREEN,
                                 align=("left", "middle")))
        cy += group_h + 18
    return elems, sc.len(cy)


def _psdm_html(elem):
    mappings = elem.get("mappings", []) or []
    hdr = (f'<div style="display:grid;grid-template-columns:1fr 40px 1fr 40px 1fr;align-items:center;">'
           f'<div style="background:{theme.BLUE};color:{theme.WHITE};font-weight:700;text-align:center;border-radius:8px;padding:10px;">业务流程（BA）</div><div></div>'
           f'<div style="background:{theme.GREEN};color:{theme.WHITE};font-weight:700;text-align:center;border-radius:8px;padding:10px;">应用服务（AA）</div><div></div>'
           f'<div style="background:{theme.TEAL};color:{theme.WHITE};font-weight:700;text-align:center;border-radius:8px;padding:10px;">数据单据（DA）</div>')
    rows = []
    for m in mappings:
        rows.append(
            f'<div style="background:{theme.BLUE_LIGHT};color:{theme.BLUE};border-radius:6px;padding:9px 12px;font-size:13px;font-weight:600;margin-top:10px;" data-editable="true">{_esc(m.get("process", ""))}</div>'
            f'<div style="text-align:center;color:{theme.BLUE_MID};font-size:18px;margin-top:10px;">→</div>'
            f'<div style="background:{theme.GREEN_LIGHT};color:{theme.GREEN};border-radius:6px;padding:9px 12px;font-size:13px;font-weight:600;margin-top:10px;" data-editable="true">{_esc(m.get("service", ""))}</div>'
            f'<div style="text-align:center;color:{theme.BLUE_MID};font-size:18px;margin-top:10px;">→</div>'
            f'<div style="background:{theme.TEAL_LIGHT};color:{theme.TEAL};border-radius:6px;padding:9px 12px;font-size:13px;font-weight:600;margin-top:10px;" data-editable="true">{_esc(m.get("document", ""))}</div>')
    return hdr + "".join(rows) + "</div>"


def _psdm_pptd(elem, x, y, w):
    mappings = elem.get("mappings", []) or []
    sc = pe.PptdScaler(x, y, w)
    elems = []
    cols = [(0, "业务流程（BA）", theme.BLUE), (440, "应用服务（AA）", theme.GREEN),
            (880, "数据单据（DA）", theme.TEAL)]
    col_w = 400
    for ci, (cx, name, color) in enumerate(cols):
        elems.append(pe.shape(f"psdm-h{ci}", [sc.px(cx), y, sc.len(col_w - 80), sc.len(40)],
                              "roundRect", fill=color, adjustments=[10000]))
        elems.append(pe.text(f"psdm-h{ci}-t", [sc.px(cx), y, sc.len(col_w - 80), sc.len(40)],
                             name, font_size=max(9, sc.len(13)), color=theme.WHITE, bold=True))
    cy = 40 + 10
    for mi, m in enumerate(mappings):
        for ci, (cx, _, color) in enumerate(cols):
            key = ("process", "service", "document")[ci]
            light = {theme.BLUE: theme.BLUE_LIGHT, theme.GREEN: theme.GREEN_LIGHT,
                     theme.TEAL: theme.TEAL_LIGHT}[color]
            elems.append(pe.shape(f"psdm-{mi}-{ci}", [sc.px(cx), y + sc.len(cy), sc.len(col_w - 80), sc.len(38)],
                                  "roundRect", fill=light, adjustments=[12000]))
            elems.append(pe.text(f"psdm-{mi}-{ci}-t", [sc.px(cx + 10), y + sc.len(cy), sc.len(col_w - 100), sc.len(38)],
                                 m.get(key, ""), font_size=max(8, sc.len(12)), color=color,
                                 bold=True, align=("left", "middle")))
            if ci < 2:
                elems.append(pe.shape(f"psdm-{mi}-a{ci}", [sc.px(cx + col_w - 70), y + sc.len(cy + 8), sc.len(48), sc.len(22)],
                                      "rightArrow", fill=theme.BLUE_MID))
        cy += 38 + 10
    return elems, sc.len(cy)


def _reconcile_html(elem):
    terms = elem.get("terms", []) or []
    hdrs = [("术语", theme.TEXT), ("BA 业务对象", theme.BLUE), ("AA 应用模块", theme.GREEN),
            ("DA 数据实体", theme.PURPLE), ("TA 技术组件", theme.TEAL)]
    head = "".join(f'<th style="background:{c};color:{theme.WHITE};padding:6px 10px;text-align:left;">{t}</th>' for t, c in hdrs)
    rows = []
    for t in terms:
        rows.append(
            f'<tr><td style="font-weight:700;" data-editable="true">{_esc(t.get("term", ""))}</td>'
            f'<td data-editable="true">{_esc(t.get("ba", ""))}</td>'
            f'<td data-editable="true">{_esc(t.get("aa", ""))}</td>'
            f'<td data-editable="true">{_esc(t.get("da", ""))}</td>'
            f'<td data-editable="true">{_esc(t.get("ta", ""))}</td></tr>')
    return (f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'<style>section.diagram[data-subtype="cross_4a_reconcile"] td{{padding:6px 10px;border-bottom:1px solid {theme.BORDER};}}'
            f'section.diagram[data-subtype="cross_4a_reconcile"] tr:hover td{{background:{theme.BLUE_LIGHT};}}</style>')


def _reconcile_pptd(elem, x, y, w):
    terms = elem.get("terms", []) or []
    headers = ["术语", "BA 业务对象", "AA 应用模块", "DA 数据实体", "TA 技术组件"]
    emit_rows = [[{"content": {"text": h}} for h in headers]]
    plain_rows = [[str(h) for h in headers]]
    for t in terms:
        emit_rows.append([
            {"content": {"color": "$navy", "text": f"<p><strong>{pe._esc(t.get('term', ''))}</strong></p>\n"}},
            {"content": {"text": pe._esc(t.get("ba", ""))}},
            {"content": {"text": pe._esc(t.get("aa", ""))}},
            {"content": {"text": pe._esc(t.get("da", ""))}},
            {"content": {"text": pe._esc(t.get("ta", ""))}},
        ])
        plain_rows.append([str(t.get(k, "")) for k in ("term", "ba", "aa", "da", "ta")])
    col_w = [0.14, 0.22, 0.22, 0.22, 0.20]
    # 行高 hug（间距体系 v1 §五，排查 I-16）：下限原写死 36
    table_h, row_fracs = pe.table_hug_geometry(plain_rows, col_w, w, 36, 0.16)
    elems = [{
        "elementId": f"rec-{y}", "elementType": "table",
        "bounds": [x, y, w, table_h],
        "columnWidths": col_w,
        "rowHeights": row_fracs,
        "style": "$default",
        "rows": emit_rows,
    }]
    return elems, table_h


def _auto_html(elem):
    tasks = elem.get("tasks", []) or []
    badge = {"人工": f"background:{theme.BLUE_LIGHT};color:{theme.TEXT_SUB};",
             "半自动": f"background:{theme.ORANGE_LIGHT};color:{theme.ORANGE};",
             "自动": f"background:{theme.GREEN_LIGHT};color:{theme.GREEN};",
             "高": f"background:{theme.GREEN_LIGHT};color:{theme.GREEN};",
             "中": f"background:{theme.ORANGE_LIGHT};color:{theme.ORANGE};",
             "低": f"background:{theme.BLUE_LIGHT};color:{theme.TEXT_SUB};"}

    def _b(text):
        style = badge.get(text, badge["人工"])
        return f'<span style="display:inline-block;border-radius:11px;padding:2px 8px;font-size:12px;font-weight:700;{style}" data-editable="true">{_esc(text)}</span>'

    rows = []
    for t in tasks:
        rows.append(
            f'<tr><td data-editable="true">{_esc(t.get("name", ""))}</td>'
            f'<td>{_b(t.get("current", "人工"))}</td>'
            f'<td>{_b(t.get("target", "自动"))}</td>'
            f'<td><b data-editable="true">{_esc(t.get("saving", ""))}</b></td>'
            f'<td>{_b(t.get("roi", "中"))}</td></tr>')
    return (f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            f'<thead><tr style="background:{theme.BLUE};color:{theme.WHITE};">'
            f'<th style="padding:6px 10px;text-align:left;width:26%;">任务</th>'
            f'<th style="padding:6px 10px;text-align:left;">现状</th>'
            f'<th style="padding:6px 10px;text-align:left;">目标</th>'
            f'<th style="padding:6px 10px;text-align:left;">预计节省</th>'
            f'<th style="padding:6px 10px;text-align:left;">ROI</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            f'<style>section.diagram[data-subtype="automation_table"] td{{padding:6px 10px;border-bottom:1px solid {theme.BORDER};}}'
            f'section.diagram[data-subtype="automation_table"] tr:hover td{{background:{theme.BLUE_LIGHT};}}</style>')


def _auto_pptd(elem, x, y, w):
    tasks = elem.get("tasks", []) or []
    colors = {"人工": theme.TEXT_SUB, "半自动": theme.ORANGE, "自动": theme.GREEN,
              "高": theme.GREEN, "中": theme.ORANGE, "低": theme.TEXT_SUB}
    headers = ["任务", "现状", "目标", "预计节省", "ROI"]
    emit_rows = [[{"content": {"text": h}} for h in headers]]
    plain_rows = [[str(h) for h in headers]]
    for t in tasks:
        emit_rows.append([
            {"content": {"text": pe._esc(t.get("name", ""))}},
            {"content": {"color": colors.get(t.get("current", ""), theme.TEXT_SUB),
                         "text": t.get("current", "")}},
            {"content": {"color": colors.get(t.get("target", ""), theme.GREEN),
                         "text": t.get("target", "")}},
            {"content": {"text": f"<p><strong>{pe._esc(t.get('saving', ''))}</strong></p>\n"}},
            {"content": {"color": colors.get(t.get("roi", ""), theme.ORANGE),
                         "text": t.get("roi", "")}},
        ])
        plain_rows.append([str(t.get(k, "")) for k in ("name", "current", "target", "saving", "roi")])
    col_w = [0.26, 0.16, 0.20, 0.22, 0.16]
    # 行高 hug（间距体系 v1 §五，排查 I-16）：下限原写死 36
    table_h, row_fracs = pe.table_hug_geometry(plain_rows, col_w, w, 36, 0.16)
    elems = [{
        "elementId": f"auto-{y}", "elementType": "table",
        "bounds": [x, y, w, table_h],
        "columnWidths": col_w,
        "rowHeights": row_fracs,
        "style": "$default",
        "rows": emit_rows,
    }]
    return elems, table_h


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def render_html(elem):
    st = elem.get("subtype", "")
    if st == "org_tree":
        nodes, edges, vb_w, vb_h = _layout(elem)
        parts = [theme.section_open(elem)]
        # 缩放封顶：viewBox 不足 1200 宽时按原始占比渲染并居中（防止小树上浮放大）
        pct = min(100.0, vb_w / 1200 * 100)
        parts.append(f'<svg class="dg" viewBox="0 0 {vb_w} {vb_h}" style="width:{pct:.1f}%;margin:0 auto;" xmlns="http://www.w3.org/2000/svg">')
        for px, py1, cx, cy1 in edges:
            ym = (py1 + cy1) / 2
            parts.append(f'<path d="M{px},{py1} L{px},{ym} L{cx},{ym} L{cx},{cy1}" stroke="{theme.GRAY}" stroke-width="1.5" fill="none"/>')
        for _i, nd in enumerate(nodes):
            fill, border, title_c, _ = _node_fill().get(min(nd["depth"], 2), _node_fill()[2])
            bw = 0 if nd["depth"] == 0 else 1.8
            stroke = f' stroke="{border}" stroke-width="{bw}"' if bw else ""
            title_c = theme.WHITE if nd["depth"] == 0 else title_c
            sub_c = "rgba(255,255,255,0.8)" if nd["depth"] == 0 else theme.TEXT_SUB
            parts.append(f'<rect x="{nd["x"]}" y="{nd["y"]}" width="{NODE_W}" height="{NODE_H}" rx="8" fill="{fill}"{stroke}/>')
            parts.append(f'<text x="{nd["x"] + NODE_W / 2}" y="{nd["y"] + 24}" font-size="13" font-weight="700" fill="{title_c}" text-anchor="middle" data-editable="true">{_esc(nd["name"])}</text>')
            if nd["desc"]:
                parts.append(f'<text x="{nd["x"] + NODE_W / 2}" y="{nd["y"] + 43}" font-size="11" fill="{sub_c}" text-anchor="middle">{_esc(nd["desc"])}</text>')
        parts.append("</svg>")
        parts.append(theme.SECTION_CLOSE)
        return "\n".join(parts)
    body = {"er_conceptual": _er_html, "er_logical": _er_html,
            "data_flow": _df_html, "value_chain": _vc_html,
            "biz_capability_tree": _bct_html,
            "process_service_doc_mapping": _psdm_html,
            "cross_4a_reconcile": _reconcile_html,
            "automation_table": _auto_html}.get(st)
    if not body:
        raise NotImplementedError(f"relationship/{st} 未实现")
    return theme.section_open(elem) + "\n" + body(elem) + "\n" + theme.SECTION_CLOSE


def render_pptd(elem, x, y, w):
    st = elem.get("subtype", "")
    if st == "org_tree":
        return _org_pptd(elem, x, y, w)
    fn = {"er_conceptual": _er_pptd, "er_logical": _er_pptd,
          "data_flow": _df_pptd, "value_chain": _vc_pptd,
          "biz_capability_tree": _bct_pptd,
          "process_service_doc_mapping": _psdm_pptd,
          "cross_4a_reconcile": _reconcile_pptd,
          "automation_table": _auto_pptd}.get(st)
    if not fn:
        raise NotImplementedError(f"relationship/{st} 未实现")
    return fn(elem, x, y, w)


def _org_pptd(elem, x, y, w):
    """org_tree pptd：肘线拆直线连接符组合，缩放封顶 + 居中。"""
    nodes, edges, vb_w, vb_h = _layout(elem)
    # 缩放封顶：树宽不足 1200 时按 1200 基准缩放并水平居中（防止上浮放大）
    scale = w / 1200.0
    x_off = max(0.0, (w - vb_w * scale) / 2)
    sc = pe.PptdScaler(x + x_off, y, w - 2 * x_off, max(vb_w, 1))
    elems = []
    # 肘线拆解：竖 trunk + 横线 + 竖 stub（全 straightConnector1 无箭头）
    for i, (px, py1, cx, cy1) in enumerate(edges):
        ym = (py1 + cy1) / 2
        elems.append(pe.connector(f"og{i}-v1", sc.px(px), sc.py(py1), sc.px(px), sc.py(ym),
                                  arrow=("none", "none"), color=theme.GRAY, width=1.5))
        elems.append(pe.connector(f"og{i}-h", sc.px(px), sc.py(ym), sc.px(cx), sc.py(ym),
                                  arrow=("none", "none"), color=theme.GRAY, width=1.5))
        elems.append(pe.connector(f"og{i}-v2", sc.px(cx), sc.py(ym), sc.px(cx), sc.py(cy1),
                                  arrow=("none", "none"), color=theme.GRAY, width=1.5))
    for i, nd in enumerate(nodes):
        nx, ny = sc.px(nd["x"]), sc.py(nd["y"])
        nw, nh = sc.len(NODE_W), sc.len(NODE_H)
        if nd["depth"] == 0:
            elems.append(pe.shape(f"ogn{i}", [nx, ny, nw, nh], "roundRect",
                                  fill=theme.BLUE, adjustments=[10000]))
            elems.append(pe.text(f"ogn{i}-t", [nx, ny + sc.len(6), nw, sc.len(24)],
                                 nd["name"], font_size=max(11, sc.len(13)),
                                 color=theme.WHITE, bold=True))
            if nd["desc"]:
                elems.append(pe.text(f"ogn{i}-d", [nx, ny + sc.len(30), nw, sc.len(18)],
                                     nd["desc"], font_size=max(8, sc.len(11)),
                                     color=theme.WHITE))
        else:
            fill = theme.WHITE if nd["depth"] == 1 else theme.BLUE_LIGHT
            border_c = theme.BLUE if nd["depth"] == 1 else theme.BORDER_STRONG
            elems.append(pe.shape(f"ogn{i}", [nx, ny, nw, nh], "roundRect", fill=fill,
                                  adjustments=[10000],
                                  border={"style": "solid", "width": 1.5, "color": border_c}))
            elems.append(pe.text(f"ogn{i}-t", [nx, ny + sc.len(6), nw, sc.len(24)],
                                 nd["name"], font_size=max(11, sc.len(13)),
                                 color=theme.BLUE if nd["depth"] == 1 else theme.TEXT,
                                 bold=True))
            if nd["desc"]:
                elems.append(pe.text(f"ogn{i}-d", [nx, ny + sc.len(30), nw, sc.len(18)],
                                     nd["desc"], font_size=max(8, sc.len(11)),
                                     color=theme.TEXT_SUB))
    return elems, sc.len(vb_h)
