# -*- coding: utf-8 -*-
"""flow 类渲染器：sequence / swimlane / cross_system / parallel / decision（5 种全部实现）。

HTML：内联 SVG（viewBox 1200 宽），沿用既有 figures 节点语言
（左色条 + 步骤序号圆点 + 实线同步/虚线异步 + doc 便签节点）。
pptd：同一套坐标经 PptdScaler 换算，连接器走原生 connector（§4.1 契约）。

spec 字段（dev plan §4.2）：
  steps: [{label, desc, type(start|task|system|decision|end|doc), lane(swimlane 必填),
           next(可选), async(cross_system 用), attach(doc 挂接目标 label)}]
  lanes: [{name}]（swimlane）
  direction: horizontal | vertical（本期实现 horizontal）
"""

from . import theme
from .theme import _esc
from . import pptd_emit as pe
from ..spacing import GAP_SM, INSET_X

NODE_W, NODE_H = 180, 72
MARGIN_X = 40
LANE_H, LANE_GAP = 132, 16  # 泳道紧凑化：4 道总高 <=640px，保证 PPTD 单页（可用高 ~560pt）不溢出
TOP_PAD = 20


def _hug_h(nd):
    """任务类节点的堆叠实高（容器盒模型 §3.2 hug，I-1）：NODE_H 与内容实高取大。

    布局一律用 nd["h"] 推进 y 游标，内容超高时节点长高而不是溢出互压。
    start/end/decision/doc 是固定造型节点，不 hug。
    """
    if nd["type"] in ("start", "end", "decision", "doc"):
        return NODE_H
    return max(NODE_H, pe.node_stack(nd.get("w", NODE_W), nd["label"],
                                     nd["desc"], has_num=True)[3])


# ---------------------------------------------------------------------------
# 布局
# ---------------------------------------------------------------------------

def _layout_sequence(elem):
    """单链横排。返回 (nodes, edges, vb_w, vb_h)。
    节点过多时先压 gap 再压节点宽，保证总宽不溢出 viewBox。"""
    steps = elem.get("steps", []) or []
    n = len(steps)
    vb_w = 1200
    node_w = NODE_W
    if n > 1:
        gap = (vb_w - 2 * MARGIN_X - n * node_w) / (n - 1)
        if gap < 24:
            gap = 24
            node_w = (vb_w - 2 * MARGIN_X - gap * (n - 1)) / n
    else:
        gap = 60
    y = TOP_PAD + 44
    nodes = []
    for i, st in enumerate(steps):
        nd = {
            "label": st.get("label", ""), "desc": st.get("desc", ""),
            "type": st.get("type", "task"),
            "x": MARGIN_X + i * (node_w + gap), "y": y, "num": i + 1,
            "w": node_w,
        }
        nd["h"] = _hug_h(nd)
        nodes.append(nd)
    edges = _build_edges(steps, nodes)
    vb_h = y + max((nd["h"] for nd in nodes), default=NODE_H) + 70
    return nodes, edges, vb_w, vb_h


def _layout_swimlane(elem):
    """泳道分带。lanes 自上而下，带内节点按 steps 顺序横排。"""
    steps = elem.get("steps", []) or []
    lanes = [lane.get("name", "") for lane in elem.get("lanes", []) or []]
    if not lanes:
        lanes = sorted({s.get("lane", "") for s in steps if s.get("lane")})
    # 带内分组保持 steps 顺序
    per_lane = {name: [] for name in lanes}
    for i, st in enumerate(steps):
        ln = st.get("lane", lanes[0])
        per_lane.setdefault(ln, []).append((i, st))
    nodes = []
    node_map = {}
    lane_rects = []
    ly = TOP_PAD  # 泳道 y 游标：按带内节点堆叠实高推进（hug）
    for name in lanes:
        band = per_lane.get(name, [])
        cnt = len(band)
        node_w = NODE_W
        if cnt > 1:
            gap = (1200 - 2 * MARGIN_X - cnt * node_w) / (cnt - 1)
            if gap < 60:
                # gap 至少 60px：给边上 note（关联键标注）留出显示位，避免被节点遮挡
                gap = 60
                node_w = (1200 - 2 * MARGIN_X - gap * (cnt - 1)) / cnt
        else:
            gap = 60
        band_max_h = NODE_H
        for k, (i, st) in enumerate(band):
            nd = {
                "label": st.get("label", ""), "desc": st.get("desc", ""),
                "type": st.get("type", "task"), "lane": name,
                "x": MARGIN_X + k * (node_w + gap),
                "y": ly + 44, "num": i + 1, "w": node_w,
            }
            nd["h"] = _hug_h(nd)
            band_max_h = max(band_max_h, nd["h"])
            nodes.append(nd)
            node_map[i] = nd
        lane_h = max(LANE_H, 44 + band_max_h + 16)
        lane_rects.append((name, MARGIN_X - 10, ly,
                           1200 - 2 * MARGIN_X + 20, lane_h))
        ly += lane_h + LANE_GAP
    edges = _build_edges(steps, nodes, node_map=node_map)
    vb_h = ly + 20
    return nodes, edges, 1200, vb_h, lane_rects


def _build_edges(steps, nodes, node_map=None):
    """边：优先 steps[].next（按 label 找），否则顺序相连。
    返回 [(from_idx, to_idx, dashed, note)]。doc 节点不进主链（走 attach 虚线）。"""
    node_map = node_map or {i: nodes[i] for i in range(len(nodes))}
    label2idx = {nd["label"]: i for i, nd in node_map.items()}
    edges = []
    # 主链按 steps 原始顺序（node_map 键即 step 序号；泳道按带插入会乱序，必须排序）
    main = sorted(i for i, nd in node_map.items() if nd["type"] != "doc")
    has_next = any(st.get("next") for st in steps)
    if has_next:
        for i, st in enumerate(steps):
            nxt = st.get("next")
            if nxt and nxt in label2idx and i in node_map:
                edges.append((i, label2idx[nxt],
                              bool(st.get("async")), st.get("note", "")))
    else:
        for a, b in zip(main, main[1:], strict=False):
            st = steps[b] if b < len(steps) else {}
            edges.append((a, b, bool(st.get("async")), st.get("note", "")))
    # doc 挂接虚线
    for i, nd in node_map.items():
        if nd["type"] == "doc":
            target = (steps[i].get("attach") if i < len(steps) else None) or ""
            tidx = label2idx.get(target)
            if tidx is None and main:
                tidx = main[-1]
            if tidx is not None:
                edges.append((tidx, i, True, ""))
    return edges


# ---------------------------------------------------------------------------
# P1 布局：cross_system / parallel / decision
# ---------------------------------------------------------------------------

def _layout_cross_system(elem):
    """跨系统流程：每系统一列，步骤按序落列，跨列箭头标接口。"""
    systems = [s.get("name", "") for s in elem.get("systems", []) or []]
    steps = elem.get("steps", []) or []
    if not systems:
        systems = sorted({s.get("system", "") for s in steps if s.get("system")})
    sys_idx = {name: i for i, name in enumerate(systems)}
    n_sys = max(1, len(systems))
    # 列间距按列数自适应：3 列宽松（120），4 列 60，5 列起 40——保证节点宽 >=120px 能放 8 字 label
    col_gap = 120 if n_sys <= 3 else (60 if n_sys == 4 else 40)
    col_w = (1200 - 2 * MARGIN_X - col_gap * (n_sys - 1)) / n_sys
    node_w = min(NODE_W + 40, col_w - 40)
    per_sys = {name: [] for name in systems}
    for i, st in enumerate(steps):
        per_sys.setdefault(st.get("system", systems[0]), []).append((i, st))
    nodes = []
    node_map = {}
    v_gap = 44
    # 先算各节点堆叠实高 -> 各行实高（行高 = 行内最高节点，hug）
    placed = []  # (i, k, nd)
    row_h = {}
    for name in systems:
        band = per_sys.get(name, [])
        cx = MARGIN_X + sys_idx[name] * (col_w + col_gap)
        for k, (i, st) in enumerate(band):
            nd = {
                "label": st.get("label", ""), "desc": st.get("desc", ""),
                "type": st.get("type", "task"), "system": name,
                "x": cx + (col_w - node_w) / 2,
                "y": 0.0, "num": i + 1, "w": node_w,
            }
            nd["h"] = _hug_h(nd)
            row_h[k] = max(row_h.get(k, NODE_H), nd["h"])
            placed.append((i, k, nd))
    # 行 y 游标：按行实高堆叠，不溢出互压
    row_y = {}
    yy = TOP_PAD + 70
    for k in sorted(row_h):
        row_y[k] = yy
        yy += row_h[k] + v_gap
    for i, k, nd in placed:
        nd["y"] = row_y[k]
        nodes.append(nd)
        node_map[i] = nd
    edges = _build_edges(steps, nodes, node_map=node_map)
    vb_h = yy + 30
    col_rects = [(name, MARGIN_X + sys_idx[name] * (col_w + col_gap) - 14, TOP_PAD,
                  col_w + 28, vb_h - TOP_PAD - 20,
                  "green" if sys_idx[name] % 2 else "gray") for name in systems]
    return nodes, edges, 1200, vb_h, col_rects


def _layout_parallel(elem):
    """汇聚型并行：sources 左侧纵排 -> 网关圆点 -> merge -> after 链。"""
    sources = elem.get("sources", []) or []
    merge = elem.get("merge", {}) or {}
    if isinstance(merge, str):
        merge = {"label": merge}
    after = elem.get("after", []) or []
    n = len(sources)
    src_gap = 34
    nodes = []
    yy = TOP_PAD + 30  # 源纵排 y 游标：按各源堆叠实高推进（hug）
    for i, st in enumerate(sources):
        nd = {
            "label": st.get("label", ""), "desc": st.get("desc", ""),
            "type": "task",
            "x": MARGIN_X, "y": yy,
            "num": i + 1, "w": NODE_W + 40,
        }
        nd["h"] = _hug_h(nd)
        nodes.append(nd)
        yy += nd["h"] + src_gap
    total_h = yy - src_gap
    gy = TOP_PAD + 30 + (total_h - TOP_PAD - 30) / 2  # 网关中心 y
    gate_x = MARGIN_X + NODE_W + 40 + 190
    merge_nd = {
        "label": merge.get("label", "汇总"), "desc": merge.get("desc", ""),
        "type": "task", "x": gate_x + 100, "y": 0.0,
        "num": n + 1, "w": NODE_W + 40,
    }
    merge_nd["h"] = _hug_h(merge_nd)
    merge_nd["y"] = gy - merge_nd["h"] / 2
    nodes.append(merge_nd)
    edges = [(i, n, False, "") for i in range(n)]
    prev_idx = n
    tail_max_h = merge_nd["h"]
    for j, st in enumerate(after):
        nd = {
            "label": st.get("label", ""), "desc": st.get("desc", ""),
            "type": st.get("type", "task"),
            "x": merge_nd["x"] + NODE_W + 40 + 100 + j * (NODE_W + 60),
            "y": 0.0, "num": n + 2 + j, "w": NODE_W,
        }
        nd["h"] = _hug_h(nd)
        nd["y"] = gy - nd["h"] / 2
        tail_max_h = max(tail_max_h, nd["h"])
        nodes.append(nd)
        edges.append((prev_idx, n + 1 + j, False, ""))
        prev_idx = n + 1 + j
    vb_h = max(total_h + 60, gy + tail_max_h / 2 + 80)
    vb_w = max(1200, (nodes[-1]["x"] + nodes[-1]["w"] + MARGIN_X) if nodes else 1200)
    gate = (gate_x, gy)
    return nodes, edges, vb_w, vb_h, gate


def _layout_decision(elem):
    """决策流程：主线 sequence + decision 菱形；alt_next 为否分支（虚线）。"""
    nodes, edges, vb_w, vb_h = _layout_sequence(elem)
    steps = elem.get("steps", []) or []
    label2idx = {nd["label"]: i for i, nd in enumerate(nodes)}
    alt_edges = []
    for i, st in enumerate(steps):
        alt = st.get("alt_next")
        if st.get("type") == "decision" and alt and alt in label2idx:
            alt_edges.append((i, label2idx[alt], st.get("alt_label", "否")))
    vb_h += 90 if alt_edges else 0
    return nodes, edges, alt_edges, vb_w, vb_h


# ---------------------------------------------------------------------------
# HTML（SVG）
# ---------------------------------------------------------------------------

def _node_style():
    """节点配色表（调用时取 theme：风格透传 P2-A2，模块级快照会在
    use_style 切换后滞留旧色板，故改为函数）。"""
    return {
        "task": (theme.WHITE, theme.BLUE, theme.BLUE, theme.TEXT),
        "system": (theme.GREEN_LIGHT, theme.GREEN, theme.GREEN, theme.GREEN),
        "trigger": ("#FFFAF0", "#C05621", "#C05621", "#C05621"),
    }


def _svg_node(nd):
    t = nd["type"]
    x, y = nd["x"], nd["y"]
    nw = nd.get("w", NODE_W)
    nh = nd.get("h", NODE_H)
    cx = x + nw / 2
    parts = []
    if t in ("start", "end"):
        fill = theme.BLUE if t == "start" else theme.GREEN
        parts.append(f'<rect x="{x}" y="{y}" width="{nw}" height="{nh}" rx="36" fill="{fill}"/>')
        parts.append(f'<text x="{cx}" y="{y + nh / 2 + 5}" font-size="14" font-weight="700" fill="{theme.WHITE}" text-anchor="middle">{_esc(nd["label"])}</text>')
        return "\n".join(parts)
    if t == "decision":
        # 菱形（decision 主链节点；分支标注归 P1 decision 子类型）
        dw, dh = 200, 110
        dx, dy = cx, y + nh / 2
        parts.append(f'<polygon points="{dx},{dy - dh / 2} {dx + dw / 2},{dy} {dx},{dy + dh / 2} {dx - dw / 2},{dy}" fill="{theme.ORANGE_LIGHT}" stroke="{theme.ORANGE}" stroke-width="1.5"/>')
        parts.append(f'<text x="{dx}" y="{dy + 4}" font-size="12" font-weight="700" fill="#7B341E" text-anchor="middle">{_esc(nd["label"])}</text>')
        return "\n".join(parts)
    if t == "doc":
        # 单据便签（青色折角，BPMN data object）
        dw, dh, fold = 130, 60, 12
        parts.append(f'<path d="M{x},{y} L{x + dw - fold},{y} L{x + dw},{y + fold} L{x + dw},{y + dh} L{x},{y + dh} Z" fill="{theme.TEAL_LIGHT}" stroke="{theme.TEAL}" stroke-width="1.5"/>')
        parts.append(f'<path d="M{x + dw - fold},{y} L{x + dw - fold},{y + fold} L{x + dw},{y + fold}" fill="none" stroke="{theme.TEAL}" stroke-width="1.5"/>')
        parts.append(f'<text x="{x + dw / 2}" y="{y + 26}" font-size="11" font-weight="600" fill="{theme.TEAL}" text-anchor="middle">{_esc(nd["label"])}</text>')
        if nd["desc"]:
            parts.append(f'<text x="{x + dw / 2}" y="{y + 44}" font-size="10" fill="{theme.TEXT_SUB}" text-anchor="middle">{_esc(nd["desc"])}</text>')
        return "\n".join(parts)
    fill, border, bar, title_c = _node_style().get(t, _node_style()["task"])
    parts.append(f'<rect x="{x}" y="{y}" width="{nw}" height="{nh}" rx="8" fill="{fill}" stroke="{border}" stroke-width="1.5" filter="url(#dgm-shadow)"/>')
    parts.append(f'<rect x="{x}" y="{y}" width="5" height="{nh}" rx="2" fill="{bar}"/>')
    # 序号徽章骑缝（§3.2 overlay(straddle=top-left)，I-1）：圆心压节点左上角，
    # 一半在节点外，不再放节点内压标题
    parts.append(f'<circle cx="{x}" cy="{y}" r="10" fill="{bar}"/>')
    parts.append(f'<text x="{x}" y="{round(y + 3.5, 1)}" font-size="10" font-weight="700" fill="{theme.WHITE}" text-anchor="middle">{nd["num"]}</text>')
    # title/desc 沿轴 stack：标题区从徽章预留（top_pad）之后起，desc 顶 = 标题底 + GAP_SM；
    # 逐行 <text> 与 pptd 侧 wrap_lines 同一分行估算，两端几何一致
    top_pad, title_h, _desc_h, _ = pe.node_stack(nw, nd["label"], nd["desc"],
                                                 has_num=True)
    avail_w = max(nw - 2 * INSET_X, 13.0)
    ty = y + top_pad
    for ln in pe.wrap_lines(nd["label"], 13, avail_w):
        parts.append(f'<text x="{cx}" y="{round(ty + 10.4, 1)}" font-size="13" font-weight="600" fill="{title_c}" text-anchor="middle">{_esc(ln)}</text>')
        ty += 13 * 1.3
    if nd["desc"]:
        dy = y + top_pad + title_h + GAP_SM
        for ln in pe.wrap_lines(nd["desc"], 11, avail_w):
            parts.append(f'<text x="{cx}" y="{round(dy + 8.8, 1)}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle">{_esc(ln)}</text>')
            dy += 11 * 1.3
    return "\n".join(parts)


def _svg_arrow(a, b, dashed=False, note="", idx=0):
    """两节点间贝塞尔箭头。a/b 为 node dict。"""
    doc_b = b["type"] == "doc"
    aw = a.get("w", NODE_W)
    bw = b.get("w", NODE_W)
    ah = a.get("h", NODE_H)
    bh = b.get("h", NODE_H)
    ax, ay = a["x"] + aw / 2, a["y"] + ah / 2
    bx, by = b["x"] + (65 if doc_b else bw / 2), b["y"] + (30 if doc_b else bh / 2)
    color = theme.TEAL if doc_b else (theme.GREEN if dashed else theme.BLUE)
    dash = ' stroke-dasharray="6,4"' if dashed else ""
    w = 1.5 if dashed else 2
    marker = "dgm-arr-g" if (dashed or doc_b) else "dgm-arr"
    same_row = abs(ay - by) < 40
    if same_row:
        x1, x2 = a["x"] + aw, b["x"]
        path = f"M{x1},{ay} C{x1 + 30},{ay} {x2 - 30},{by} {x2},{by}"
        lx, ly = (x1 + x2) / 2, ay - 10
    elif doc_b:
        path = f"M{ax},{a['y'] + ah} L{bx},{b['y']}"
        lx, ly = (ax + bx) / 2 + 8, (a["y"] + ah + b["y"]) / 2
        dash = ' stroke-dasharray="3,3"'
        w = 1.2
    else:
        # 跨行/跨带 S 曲线：下行出底入顶，上行出顶入底（不穿节点盒）
        downward = b["y"] > a["y"]
        if downward:
            x1, y1 = ax, a["y"] + ah
            x2, y2 = bx, b["y"]
        else:
            x1, y1 = ax, a["y"]
            x2, y2 = bx, b["y"] + bh
        ym = (y1 + y2) / 2
        path = f"M{x1},{y1} C{x1},{ym} {x2},{ym} {x2},{y2}"
        lx, ly = max(x1, x2) + 8, ym
    parts = [f'<path d="{path}" stroke="{color}" stroke-width="{w}" fill="none"{dash} marker-end="url(#{marker})"/>']
    if note:
        parts.append(f'<text x="{lx}" y="{ly}" font-size="11" fill="{color}" font-style="italic">{_esc(note)}</text>')
    return "\n".join(parts)


def _render_flow_svg(elem, nodes, edges, vb_w, vb_h, lane_rects=None):
    parts = [f'<svg class="dg" viewBox="0 0 {vb_w} {vb_h}" xmlns="http://www.w3.org/2000/svg">', theme.SVG_DEFS]
    for name, lx, ly, lw, lh in lane_rects or []:
        parts.append(f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="10" fill="{theme.BG}" stroke="{theme.BORDER_STRONG}" stroke-width="1.5"/>')
        parts.append(f'<text x="{lx + 18}" y="{ly + 28}" font-size="13" font-weight="700" fill="{theme.TEXT_STRONG}">{_esc(name)}</text>')
    node_map = {}
    for i, nd in enumerate(nodes):
        key = nd.get("num", i + 1) - 1
        node_map[key] = nd
    for ei, (ai, bi, dashed, note) in enumerate(edges):
        a, b = node_map.get(ai), node_map.get(bi)
        if a and b:
            parts.append(_svg_arrow(a, b, dashed, note, ei))
    for nd in nodes:
        parts.append(_svg_node(nd))
    parts.append("</svg>")
    return "\n".join(parts)


def _render_cross_svg(elem, nodes, edges, vb_w, vb_h, col_rects):
    """cross_system：列容器 + 节点 + 跨列箭头（实线同步/虚线异步）。"""
    parts = [f'<svg class="dg" viewBox="0 0 {vb_w} {vb_h}" xmlns="http://www.w3.org/2000/svg">', theme.SVG_DEFS]
    for name, rx, ry, rw, rh, tint in col_rects:
        fill = theme.GREEN_LIGHT if tint == "green" else theme.BG
        border = "#CFDED6" if tint == "green" else theme.BORDER_STRONG
        tcolor = theme.GREEN if tint == "green" else theme.BLUE
        parts.append(f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="10" fill="{fill}" stroke="{border}"/>')
        parts.append(f'<text x="{rx + rw / 2}" y="{ry + 30}" font-size="14" font-weight="700" fill="{tcolor}" text-anchor="middle">{_esc(name)}</text>')
    node_map = {nd.get("num", i + 1) - 1: nd for i, nd in enumerate(nodes)}
    for ai, bi, dashed, note in edges:
        a, b = node_map.get(ai), node_map.get(bi)
        if a and b:
            parts.append(_svg_arrow(a, b, dashed, note))
    for nd in nodes:
        parts.append(_svg_node(nd))
    if edges:
        parts.append(f'<text x="{vb_w / 2}" y="{vb_h - 8}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle" font-style="italic">图例：实线 = 同步接口 · 虚线 = 异步回传</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _render_parallel_svg(elem, nodes, edges, vb_w, vb_h, gate):
    """parallel：源纵排 -> 网关实心圆 -> merge -> after 链。"""
    parts = [f'<svg class="dg" viewBox="0 0 {vb_w} {vb_h}" xmlns="http://www.w3.org/2000/svg">', theme.SVG_DEFS]
    gx, gy = gate
    node_map = {nd.get("num", i + 1) - 1: nd for i, nd in enumerate(nodes)}
    for ai, bi, _dashed, _note in edges:
        a, b = node_map.get(ai), node_map.get(bi)
        if not a or not b:
            continue
        aw, _bw = a.get("w", NODE_W), b.get("w", NODE_W)
        if bi >= len(nodes) - 1 or ai == bi:
            continue
        if a.get("num", 0) <= len(elem.get("sources", []) or []):
            # 源 -> 网关
            x1, y1 = a["x"] + aw, a["y"] + a.get("h", NODE_H) / 2
            path = f"M{x1},{y1} C{x1 + 60},{y1} {gx - 60},{gy} {gx - 14},{gy}"
            parts.append(f'<path d="{path}" stroke="{theme.BLUE}" stroke-width="1.8" fill="none" marker-end="url(#dgm-arr)"/>')
        else:
            x1, y1 = a["x"] + aw, a["y"] + a.get("h", NODE_H) / 2
            x2, y2 = b["x"], b["y"] + b.get("h", NODE_H) / 2
            path = f"M{x1},{y1} C{x1 + 30},{y1} {x2 - 30},{y2} {x2},{y2}"
            parts.append(f'<path d="{path}" stroke="{theme.BLUE}" stroke-width="2" fill="none" marker-end="url(#dgm-arr)"/>')
    # 网关
    parts.append(f'<circle cx="{gx}" cy="{gy}" r="14" fill="{theme.BLUE}"/>')
    parts.append(f'<text x="{gx}" y="{gy + 30}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle">汇聚</text>')
    # 网关 -> merge
    merge_nd = nodes[len(elem.get("sources", []) or [])]
    parts.append(f'<path d="M{gx + 14},{gy} C{gx + 40},{gy} {merge_nd["x"] - 30},{gy} {merge_nd["x"]},{gy}" stroke="{theme.BLUE}" stroke-width="2" fill="none" marker-end="url(#dgm-arr)"/>')
    for nd in nodes:
        parts.append(_svg_node(nd))
    parts.append(f'<text x="{vb_w / 2}" y="{vb_h - 8}" font-size="11" fill="{theme.TEXT_SUB}" text-anchor="middle" font-style="italic">各源并行完成后方可在网关汇聚</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _render_decision_svg(elem, nodes, edges, alt_edges, vb_w, vb_h):
    """decision：主链 + 菱形决策 + 否分支虚线回流。"""
    parts = [f'<svg class="dg" viewBox="0 0 {vb_w} {vb_h}" xmlns="http://www.w3.org/2000/svg">', theme.SVG_DEFS]
    node_map = {nd.get("num", i + 1) - 1: nd for i, nd in enumerate(nodes)}
    for ai, bi, dashed, note in edges:
        a, b = node_map.get(ai), node_map.get(bi)
        if not a or not b:
            continue
        label = "是" if a["type"] == "decision" else ""
        parts.append(_svg_arrow(a, b, dashed, note or label))
    for ai, bi, blabel in alt_edges:
        a, b = node_map.get(ai), node_map.get(bi)
        if not a or not b:
            continue
        # 否分支：菱形底部 -> 下方虚线 -> 目标底部
        ax = a["x"] + a.get("w", NODE_W) / 2
        ay = a["y"] + a.get("h", NODE_H) / 2 + 55
        bx_t = b["x"] + b.get("w", NODE_W) / 2
        by_t = b["y"] + b.get("h", NODE_H) + 30
        path = f"M{ax},{ay} C{ax},{ay + 40} {bx_t},{by_t + 20} {bx_t},{by_t}"
        parts.append(f'<path d="{path}" stroke="{theme.ORANGE}" stroke-width="1.8" fill="none" stroke-dasharray="6,4" marker-end="url(#dgm-arr)"/>')
        parts.append(f'<text x="{(ax + bx_t) / 2}" y="{max(ay, by_t) + 20}" font-size="12" font-weight="700" fill="{theme.ORANGE}" text-anchor="middle">{_esc(blabel)}</text>')
    for nd in nodes:
        parts.append(_svg_node(nd))
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(elem):
    """flow -> HTML 片段。"""
    st = elem.get("subtype", "sequence")
    if st == "swimlane":
        nodes, edges, vb_w, vb_h, lane_rects = _layout_swimlane(elem)
        svg = _render_flow_svg(elem, nodes, edges, vb_w, vb_h, lane_rects)
    elif st == "cross_system":
        nodes, edges, vb_w, vb_h, col_rects = _layout_cross_system(elem)
        svg = _render_cross_svg(elem, nodes, edges, vb_w, vb_h, col_rects)
    elif st == "parallel":
        nodes, edges, vb_w, vb_h, gate = _layout_parallel(elem)
        svg = _render_parallel_svg(elem, nodes, edges, vb_w, vb_h, gate)
    elif st == "decision":
        nodes, edges, alt_edges, vb_w, vb_h = _layout_decision(elem)
        svg = _render_decision_svg(elem, nodes, edges, alt_edges, vb_w, vb_h)
    elif st == "sequence":
        nodes, edges, vb_w, vb_h = _layout_sequence(elem)
        svg = _render_flow_svg(elem, nodes, edges, vb_w, vb_h)
    elif st == "flow_rows":
        # 第 28 种子类型（v2.0 §8.1）：行式 HTML，不走 SVG 路径
        return render_flow_rows(elem)
    else:
        raise NotImplementedError(f"flow/{st} 未实现")
    return theme.section_open(elem) + "\n" + svg + "\n" + theme.SECTION_CLOSE


# ---------------------------------------------------------------------------
# flow_rows（v2.0 第 28 种子类型，§8.1/§8.2；F8 纯增量，不动既有 5 种 SVG）
# ---------------------------------------------------------------------------

def _flow_rows_legend(elem):
    """roles 色板 → legend_bar 自动生成（§8.1：角色色 >2 时，图框内底部）。"""
    from ..schema import FLOW_ROLES
    roles = elem.get("roles")
    if not isinstance(roles, dict) or len(roles) <= 2:
        return ""
    items = "".join(
        f'<span class="legend-item"><i class="legend-swatch sw-role-{_esc(k)}"></i>'
        f'<span data-editable="true">{_esc(v.get("label", k))}</span></span>'
        for k, v in roles.items()
        if k in FLOW_ROLES and isinstance(v, dict))
    return f'\n<div class="legend-bar">{items}</div>' if items else ""


def render_flow_rows(elem):
    """flow_rows 行式流程图 HTML（§8.1 结构与 mock EXHIBIT 2 一致）。

    行 = 业务阶段（group 底色分组）；卡 = 流程节点（role 顶部 3px 角色色条）；
    行内卡间 →；arrow 行 ↓/↑；dashed_opt 行 = 可选项（虚线框 + 竖排标签 +
    卡间 ⇢ + 抑制编号，F6 线型/框型语义表）。CSS 集中在 page_chrome。
    """
    from ..schema import FLOW_ROLES
    rows_html = []
    for row in elem.get("rows", []) or []:
        if not isinstance(row, dict):
            continue
        arrow = row.get("arrow")
        if arrow:
            rows_html.append(
                f'<div class="flow-down">{"↓" if arrow == "down" else "↑"}</div>')
            continue
        cards = [c for c in (row.get("cards", []) or []) if isinstance(c, dict)]
        dashed_opt = row.get("style") == "dashed_opt"
        classes = ["flow-row"]
        if row.get("group") in ("blue", "teal"):
            classes.append(f'g-{row["group"]}')
        if dashed_opt:
            classes.append("dashed-opt")
        label_html = ""
        if row.get("label"):
            sub = (f'<br><small>{_esc(row["label_sub"])}</small>'
                   if row.get("label_sub") else "")
            label_html = (f'<div class="flow-row-label" data-editable="true">'
                          f'{_esc(row["label"])}{sub}</div>')
        if dashed_opt:
            # F6：可选项行须配「可选项」标签（带行标签时追加在其后）
            label_html += '<span class="opt-tag">可选项</span>'
        cards_html = []
        for ci, card in enumerate(cards):
            if ci > 0:
                if dashed_opt:
                    cards_html.append('<div class="flow-arrow dashed">⇢</div>')
                else:
                    cards_html.append('<div class="flow-arrow">→</div>')
            cc = ["flow-card"]
            role = card.get("role")
            if role in FLOW_ROLES:
                cc.append(f"r-{_esc(role)}")
            if card.get("dim"):
                cc.append("dim")
            # F6：可选项不编号（schema 已 warning，渲染层同步抑制）
            badge = ""
            if card.get("badge") and not dashed_opt:
                badge = f'<div class="num-badge">{_esc(card["badge"])}</div>'
            desc = ""
            if card.get("desc"):
                desc = (f'<div class="fc-desc" data-editable="true">'
                        f'{_esc(card["desc"])}</div>')
            cards_html.append(
                f'<div class="{" ".join(cc)}">{badge}'
                f'<div class="fc-label" data-editable="true">'
                f'{_esc(card.get("label", ""))}</div>{desc}</div>')
        rows_html.append(
            f'<div class="{" ".join(classes)}">{label_html}'
            f'<div class="flow-cards">{"".join(cards_html)}</div></div>')
    canvas = f'<div class="flow-canvas">{"".join(rows_html)}</div>'
    return (theme.section_open(elem) + "\n" + canvas
            + _flow_rows_legend(elem) + "\n" + theme.SECTION_CLOSE)


# ---------------------------------------------------------------------------
# pptd
# ---------------------------------------------------------------------------

def render_pptd(elem, x, y, w, theme_name=None):
    """flow -> (pptd 元素列表, 消耗高度)。连接器全原生（§4.1）。

    theme_name（v2.0 §5.1）：仅 flow_rows 消费（v2 主题取色），
    既有 5 种 SVG 子类型忽略（v1.2 色板不变）。
    """
    st = elem.get("subtype", "sequence")
    if st == "flow_rows":
        return pe.render_flow_rows_pptd(elem, x, y, w, theme_name=theme_name)
    col_rects = None
    lane_rects = None
    gate = None
    alt_edges = []
    if st == "swimlane":
        nodes, edges, vb_w, vb_h, lane_rects = _layout_swimlane(elem)
    elif st == "cross_system":
        nodes, edges, vb_w, vb_h, col_rects = _layout_cross_system(elem)
    elif st == "parallel":
        nodes, edges, vb_w, vb_h, gate = _layout_parallel(elem)
    elif st == "decision":
        nodes, edges, alt_edges, vb_w, vb_h = _layout_decision(elem)
    elif st == "sequence":
        nodes, edges, vb_w, vb_h = _layout_sequence(elem)
    else:
        raise NotImplementedError(f"flow/{st} 未实现")
    sc = pe.PptdScaler(x, y, w, vb_w)
    elems = []
    for name, lx, ly, lw, lh in lane_rects or []:
        elems.extend(pe.lane(f"ln-{name}", sc, lx, ly, lw, lh, name))
    for name, rx, ry, rw, rh, tint in col_rects or []:
        elems.extend(pe.lane(f"col-{name}", sc, rx, ry, rw, rh, name,
                             tint="green" if tint == "green" else "gray"))
    node_map = {nd.get("num", i + 1) - 1: nd for i, nd in enumerate(nodes)}
    for ei, (ai, bi, dashed, note) in enumerate(edges):
        a, b = node_map.get(ai), node_map.get(bi)
        if not a or not b:
            continue
        if st == "decision" and a["type"] == "decision" and not note:
            note = "是"
        elems.extend(_pptd_arrow(sc, f"ar-{ai}-{bi}", a, b, dashed, note, slot=ei))
    for ai, bi, blabel in alt_edges:
        a, b = node_map.get(ai), node_map.get(bi)
        if not a or not b:
            continue
        aw = a.get("w", NODE_W)
        ax, ay = a["x"] + aw / 2, a["y"] + a.get("h", NODE_H) / 2 + 55
        bx_t = b["x"] + b.get("w", NODE_W) / 2
        by_t = b["y"] + b.get("h", NODE_H) + 30
        elems.append(pe.connector(f"alt-{ai}-{bi}", sc.px(ax), sc.py(ay),
                                  sc.px(bx_t), sc.py(by_t), kind="bentConnector3",
                                  color=theme.ORANGE, dash=True))
        elems.append(pe.text(f"alt-{ai}-{bi}-l",
                             [sc.px((ax + bx_t) / 2 - 30), sc.py(max(ay, by_t) + 6), sc.len(60), sc.len(18)],
                             blabel, font_size=max(9, sc.len(12)), color=theme.ORANGE,
                             bold=True))
    if gate:
        gx, gy = gate
        r = 14
        elems.append(pe.shape("gate", [sc.px(gx - r), sc.py(gy - r), sc.len(2 * r), sc.len(2 * r)],
                              "ellipse", fill=theme.BLUE))
        elems.append(pe.text("gate-l", [sc.px(gx - 30), sc.py(gy + r + 2), sc.len(60), sc.len(16)],
                             "汇聚", font_size=max(8, sc.len(11)), color=theme.TEXT_SUB))
    for i, nd in enumerate(nodes):
        elems.extend(_pptd_node(sc, f"nd-{i}", nd))
    return elems, sc.len(vb_h)


def _pptd_node(sc, eid, nd):
    t = nd["type"]
    nw = nd.get("w", NODE_W)
    nh = nd.get("h", NODE_H)
    if t in ("start", "end"):
        return pe.node(eid, sc, nd["x"], nd["y"], nw, nh,
                       nd["label"], kind="start_end")
    if t == "decision":
        return pe.diamond(eid, sc, nd["x"] + nw / 2, nd["y"] + nh / 2,
                          200, 110, nd["label"])
    if t == "doc":
        dw, dh = 130, 60
        x, y = sc.px(nd["x"]), sc.py(nd["y"])
        return [
            pe.shape(eid, [x, y, sc.len(dw), sc.len(dh)], "flowChartDocument",
                     fill=theme.TEAL_LIGHT,
                     border={"style": "solid", "width": 1.2, "color": theme.TEAL}),
            pe.text(eid + "-t", [x, y + sc.len(8), sc.len(dw), sc.len(22)],
                    nd["label"], font_size=max(9, sc.len(11)), color=theme.TEAL,
                    bold=True),
        ] + ([pe.text(eid + "-d", [x, y + sc.len(30), sc.len(dw), sc.len(18)],
                      nd["desc"], font_size=max(8, sc.len(10)),
                      color=theme.TEXT_SUB)] if nd["desc"] else [])
    kind = {"task": "task", "system": "system", "trigger": "trigger"}.get(t, "task")
    return pe.node(eid, sc, nd["x"], nd["y"], nw, nh,
                   nd["label"], nd["desc"], kind=kind, num=nd["num"])


def _pptd_arrow(sc, eid, a, b, dashed, note, slot=0):
    """连接符：同行直线，跨行肘形/直线；doc 挂接细虚线。

    slot（v1.3）：边序号，用于横向走廊错位——多条边共用两盒间缝隙时，
    走廊中线按 slot 错开 ±12px，避免水平段两两重叠成"一条粗线"。"""
    doc_b = b["type"] == "doc"
    aw = a.get("w", NODE_W)
    bw = b.get("w", NODE_W)
    ah = a.get("h", NODE_H)
    bh = b.get("h", NODE_H)
    ax, ay = a["x"] + aw / 2, a["y"] + ah / 2
    bx, by = b["x"] + (65 if doc_b else bw / 2), b["y"] + (30 if doc_b else bh / 2)
    same_row = abs(ay - by) < 40
    color = theme.TEAL if doc_b else (theme.GREEN if dashed else theme.BLUE)
    elems = []
    if doc_b:
        elems.append(pe.connector(eid, sc.px(ax), sc.py(a["y"] + ah),
                                  sc.px(bx), sc.py(b["y"]),
                                  arrow=("none", "none"), color=color, width=1.2,
                                  dash=True))
        return elems
    if same_row and b["x"] + bw >= a["x"]:
        # 前向（含少量重叠）：右缘中点 → 左缘中点，直线
        x1, x2 = a["x"] + aw, b["x"]
        elems.append(pe.connector(eid, sc.px(x1), sc.py(ay), sc.px(x2), sc.py(by),
                                  color=color, dash=dashed, width=1.25,
                                  arrow=("none", "stealth")))
        if note:
            note_fs = max(8, sc.len(11))
            note_w = sc.len(160)
            note_h = pe.stack_text_h(len(pe.wrap_lines(note, note_fs, note_w - 2 * INSET_X)), note_fs)
            mx = sc.px((x1 + x2) / 2) - note_w / 2
            my = sc.py(ay) - sc.len(22) - note_h
            elems.append(pe.text(eid + "-note", [mx, my, note_w, note_h],
                                 note, font_size=note_fs, color=color,
                                 align=("center", "middle")))
    elif same_row:
        # 同行回边（B 整体在 A 左侧）：绕下方三段直线，出底中点 → 横穿 → 入底中点。
        # 不用 bentConnector+角点：归一化几何 + flip 语义不可控，且角点贴盒边像脱锚
        acx, bcx = a["x"] + aw / 2, b["x"] + bw / 2
        # 出/入挂点都按 slot 横移 ±12px：同盒"一进一出"两条垂段不再重合
        off = ((slot % 3) - 1) * 12
        acx_out, bcx_in = acx + off, bcx + off
        gap_y = max(a["y"] + ah, b["y"] + bh) + 24 + ((slot % 3) - 1) * 10
        elems.append(pe.connector(f"{eid}-r0", sc.px(acx_out), sc.py(a["y"] + ah),
                                  sc.px(acx_out), sc.py(gap_y),
                                  arrow=("none", "none"), color=color,
                                  dash=dashed, width=1.25))
        elems.append(pe.connector(f"{eid}-r1", sc.px(acx_out), sc.py(gap_y),
                                  sc.px(bcx_in), sc.py(gap_y),
                                  arrow=("none", "none"), color=color,
                                  dash=dashed, width=1.25))
        elems.append(pe.connector(f"{eid}-r2", sc.px(bcx_in), sc.py(gap_y),
                                  sc.px(bcx_in), sc.py(b["y"] + bh),
                                  arrow=("none", "stealth"), color=color,
                                  dash=dashed, width=1.25))
        if note:
            note_fs = max(8, sc.len(11))
            note_w = sc.len(160)
            note_h = pe.stack_text_h(len(pe.wrap_lines(note, note_fs, note_w - 2 * INSET_X)), note_fs)
            elems.append(pe.text(eid + "-note",
                                 [sc.px((acx + bcx) / 2) - note_w / 2, sc.py(gap_y) + sc.len(4), note_w, note_h],
                                 note, font_size=note_fs, color=color,
                                 align=("center", "middle")))
    else:
        # 跨行：出/入都走"边缘中点"，中段横线走两行间缝隙中线。
        # 三段 straightConnector1（同 relationship.py 的 ER 折线先例），
        # 取代 bentConnector2 角点连接：端点贴盒角、flip 后折向不可控
        acx, bcx = a["x"] + aw / 2, b["x"] + bw / 2
        downward = b["y"] > a["y"]
        if downward:
            y_out, y_in = a["y"] + ah, b["y"]          # 出底 → 入顶
        else:
            y_out, y_in = a["y"], b["y"] + bh          # 出顶 → 入底
        if abs(acx - bcx) < 30:
            # 中轴对齐：一条直线
            elems.append(pe.connector(eid, sc.px(acx), sc.py(y_out),
                                      sc.px(bcx), sc.py(y_in),
                                      color=color, dash=dashed, width=1.25,
                                      arrow=("none", "stealth")))
        else:
            # 走廊错位：缝隙中线按 slot 错开 ±12px，多条边共用缝隙时水平段不重叠；
            # 入端挂点同步横移，同盒"一进一出"两条垂段不重合
            off = ((slot % 3) - 1) * 12
            acx_out, bcx_in = acx + off, bcx + off
            mid_y = (y_out + y_in) / 2 + off
            lo, hi = min(y_out, y_in) + 8, max(y_out, y_in) - 8
            mid_y = max(lo, min(hi, mid_y))
            elems.append(pe.connector(f"{eid}-r0", sc.px(acx_out), sc.py(y_out),
                                      sc.px(acx_out), sc.py(mid_y),
                                      arrow=("none", "none"), color=color,
                                      dash=dashed, width=1.25))
            elems.append(pe.connector(f"{eid}-r1", sc.px(acx_out), sc.py(mid_y),
                                      sc.px(bcx_in), sc.py(mid_y),
                                      arrow=("none", "none"), color=color,
                                      dash=dashed, width=1.25))
            elems.append(pe.connector(f"{eid}-r2", sc.px(bcx_in), sc.py(mid_y),
                                      sc.px(bcx_in), sc.py(y_in),
                                      arrow=("none", "stealth"), color=color,
                                      dash=dashed, width=1.25))
        if note:
            note_fs = max(8, sc.len(11))
            note_w = sc.len(160)
            note_h = pe.stack_text_h(len(pe.wrap_lines(note, note_fs, note_w - 2 * INSET_X)), note_fs)
            elems.append(pe.text(eid + "-note",
                                 [sc.px(max(acx, bcx)) + sc.len(8), sc.py((y_out + y_in) / 2) - note_h / 2, note_w, note_h],
                                 note, font_size=note_fs, color=color,
                                 align=("left", "middle")))
    return elems
