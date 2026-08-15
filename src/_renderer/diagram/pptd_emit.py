# -*- coding: utf-8 -*-
"""diagram 元素的 pptd 元素发射器（原生对象，禁图像/freeform）。

契约依据 docs/diagram_visual_design_v1_2026-07-19.md §4.1（箭头与连接线的
PPT 映射契约，源码审验 kimi_ppt_dsl renderer/pptx_builder.py）：
- 连接线一律 connector（straightConnector1 / bentConnector3 / curvedConnector3），
  arrow/border(dash)/flip 原生属性，PPT 内可拖锚点改样式
- 卡片/块一律 preset shape（roundRect / rect / chevron / diamond 等）
- 文字一律 text 元素，fontFamily 雅黑

坐标系：HTML 侧 SVG viewBox 宽 1200；pptd 侧按 scale 缩放到内容区。
所有工厂返回 dict（pptd 元素），由 _pptd_gen 汇总进 page elements。
"""

import math

from . import theme
from ..elements import _esc  # 单一源（§七 2.6），删除本地重复定义
from ..spacing import GAP_SM, GAP_XS, GRID, INSET_X, INSET_Y, snap


def _snap_bounds(x, y, w, h):
    """发射器出口 4px 网格吸附（间距体系 v1 §3.3）。

    集中在 shape/text/connector 三工厂出口做一次（不在各 subtype 散落）。
    四角各自 snap 后反推宽高：snap 单调，共享边与互不相交关系保持；
    宽高兜底 1（connector 近零厚度 bbox）。
    """
    x1, y1 = snap(float(x)), snap(float(y))
    x2, y2 = snap(float(x) + float(w)), snap(float(y) + float(h))
    return [x1, y1, max(x2 - x1, 1), max(y2 - y1, 1)]


class PptdScaler:
    """viewBox(1200×H) -> pptd 内容区 (x, y, w) 的坐标换算。"""

    def __init__(self, x, y, width, viewbox_w=1200.0):
        self.x = float(x)
        self.y = float(y)
        self.scale = float(width) / viewbox_w

    def px(self, vx):
        return self.x + vx * self.scale

    def py(self, vy):
        return self.y + vy * self.scale

    def len(self, v):
        return v * self.scale


def shape(eid, bounds, shape_name, fill=None, border=None, adjustments=None,
          flip=None):
    """preset shape 元素。border: {"style": solid|dash, "width": px, "color": hex}"""
    el = {
        "elementId": eid,
        "elementType": "shape",
        "bounds": _snap_bounds(*bounds),
        "shapeName": shape_name,
    }
    if adjustments:
        el["adjustments"] = adjustments
    if fill:
        el["fill"] = {"type": "solid", "color": fill}
    if border:
        el["border"] = border
    if flip:
        el["flip"] = list(flip)
    return el


def block_arrow(eid, bounds, shape_name="rightArrow", fill=None):
    """块箭头 preset（D-2 扩充）：实心方向指示，禁「线+框凑方向」。

    shape_name: rightArrow / leftRightArrow / upDownArrow / pentagon
    （转换层 _SHAPE_NAME_MAP 已登记，语义 preset 见 ppt-master 菜单）。
    规则：实心方向用块箭头 preset、细关系（接口/数据流连线）用 connector。
    """
    return shape(eid, bounds, shape_name, fill=fill)


def text(eid, bounds, content, font_size=13, color=None, bold=False,
         align=("center", "middle"), wrap=True, line_height=1.3):
    """text 元素（粗体只发行内 <strong>，方言陷阱 2）。

    color 缺省调用时取 theme.TEXT——默认参数在定义时冻结，风格透传
    （P2-A2）切换色板后必须延迟解析，其余默认色同理。

    文本内边距折算（间距体系 v1 一层）：pptd 方言 text content 无 insets
    字段（pyz yaml_format_checker.VALID_TEXT_CONTENT_KEYS 确认），故文本框
    宽减 2×INSET_X、x 加 INSET_X，文字不贴形状边；过窄的框（徽章数字等，
    inset 后不足一个字宽）不折。
    """
    if color is None:
        color = theme.TEXT
    bx, by, bw, bh = (float(v) for v in bounds)
    if bw > 2 * INSET_X + font_size:
        bx += INSET_X
        bw -= 2 * INSET_X
    # 换行 → 多段 <p>（字面 \n 与真实换行统一按行拆分；单行保持原格式兼容）
    esc = _esc(content)
    lines = esc.replace("\\n", "\n").split("\n")
    if len(lines) == 1:
        body = f"<p><strong>{esc}</strong></p>\n" if bold else f"{esc}\n"
    else:
        segs = [f"<p><strong>{ln}</strong></p>" if bold else f"<p>{ln}</p>"
                for ln in lines if ln]
        body = ("\n".join(segs) + "\n") if segs else f"{esc}\n"
    return {
        "elementId": eid,
        "elementType": "text",
        "bounds": _snap_bounds(bx, by, bw, bh),
        "content": {
            "fontSize": font_size,
            "color": color,
            "fontFamily": theme.FONT_PPT,
            "lineHeight": line_height,
            "align": list(align),
            "wrap": wrap,
            "text": body,
        },
    }


def connector(eid, x1, y1, x2, y2, kind="straightConnector1",
              arrow=("none", "arrow"), color=None, width=1.25,
              dash=False):
    """原生连接符元素（§4.1 契约）。

    bounds = 两端点包围盒；方向由 flip 推导（x2<x1 -> flipH，y2<y1 -> flipV）。
    kind: straightConnector1 | bentConnector2/3/4 | curvedConnector2/3/4
    arrow: (start, end)，取值 none|arrow|stealth|diamond|oval
    color 缺省调用时取 theme.BLUE（P2-A2 风格透传，见 text 注释）。
    """
    if color is None:
        color = theme.BLUE
    bx, by = min(x1, x2), min(y1, y2)
    bw, bh = abs(x2 - x1), abs(y2 - y1)
    flip_h, flip_v = x2 < x1, y2 < y1
    el = {
        "elementId": eid,
        "elementType": "shape",
        "bounds": _snap_bounds(bx, by, max(bw, 0.1), max(bh, 0.1)),
        "shapeName": kind,
        "border": {
            "style": "dash" if dash else "solid",
            "width": width,
            "color": color,
        },
        "flip": [flip_h, flip_v],
    }
    if arrow and (arrow[0] != "none" or arrow[1] != "none"):
        el["arrow"] = [arrow[0], arrow[1]]
    return el


def node(eid, sc, vx, vy, vw, vh, title, desc="", kind="task", num=None):
    """流程图任务节点（HTML 节点语言的 pptd 对应：白底蓝框圆角 + 左色条 + 序号）。

    kind: task(蓝) | system(绿) | trigger(橙) | start_end(蓝胶囊)
    返回元素列表（调用方 extend）。

    容器盒模型（间距体系 v1 §3.2，I-1 修复）：
    - 序号徽章骑缝 overlay(straddle=top-left)：圆心压节点左上角，
      badge 框一半在节点外，不再放节点内压标题
    - title/desc 沿轴 stack：标题区从 max(INSET_Y, badge_d/2 + GAP_XS) 起，
      desc 顶 = 标题底 + GAP_SM
    - 节点高 = 堆叠实高 + 上下 padding（hug）：max(vh, need_h)，不溢出互压
      （调用方布局按 node_stack 预算调高 vh 时，此处不再长高）
    """
    colors = {
        "task": (theme.CARD, theme.BLUE, theme.BLUE, theme.TEXT),
        "system": (theme.GREEN_LIGHT, theme.GREEN, theme.GREEN, theme.GREEN),
        "trigger": (theme.ORANGE_LIGHT, "#C05621", "#C05621", "#7B341E"),
        "start_end": (theme.BLUE, theme.BLUE, theme.BLUE, theme.WHITE),
    }
    fill_c, border_c, bar_c, title_c = colors.get(kind, colors["task"])
    x, y = sc.px(vx), sc.py(vy)
    w = sc.len(vw)
    elems = []
    if kind == "start_end":
        h = sc.len(vh)
        elems.append(shape(eid, [x, y, w, h], "flowChartTerminator",
                           fill=fill_c))
        elems.append(text(eid + "-t", [x, y, w, h], title,
                          font_size=max(11, sc.len(14)), color=theme.WHITE, bold=True))
        return elems
    title_fs = max(11, sc.len(13))
    desc_fs = max(9, sc.len(11))
    badge_d = sc.len(20)
    top_pad, title_h, desc_h, need_h = node_stack(
        w, title, desc, has_num=num is not None,
        title_fs=title_fs, desc_fs=desc_fs, badge_d=badge_d)
    h = max(sc.len(vh), need_h)
    children = []
    children.append(shape(eid + "-box", [x, y, w, h], "flowChartProcess", fill=fill_c,
                          border={"style": "solid", "width": 1.5, "color": border_c}))
    # 左侧 5px 色条
    bar = sc.len(5)
    children.append(shape(eid + "-bar", [x, y, bar, h], "rect", fill=bar_c))
    # 步骤序号圆点：骑缝（圆心压节点左上角）
    if num is not None:
        children.append(shape(eid + "-num",
                              [x - badge_d / 2, y - badge_d / 2, badge_d, badge_d],
                              "ellipse", fill=bar_c))
        children.append(text(eid + "-numt",
                             [x - badge_d / 2, y - badge_d / 2, badge_d, badge_d],
                             str(num), font_size=max(9, sc.len(10)),
                             color=theme.WHITE, bold=True))
    # 标题 + 描述：沿轴 stack（desc 顶 = 标题底 + GAP_SM）
    children.append(text(eid + "-title", [x, y + top_pad, w, title_h], title,
                         font_size=title_fs, color=title_c, bold=True))
    if desc:
        children.append(text(eid + "-desc",
                             [x, y + top_pad + title_h + GAP_SM, w, desc_h], desc,
                             font_size=desc_fs, color=theme.TEXT_SUB))
    # 组合：节点内部元素（框体/色条/角标/标题/描述）group 成整体（角标与框体关系固定）
    pad = badge_d / 2 if num is not None else 0
    return [{"elementId": eid, "elementType": "group",
             "bounds": [x - pad, y - pad, w + pad, h + pad],
             "children": children}]


def diamond(eid, sc, cx_v, cy_v, vw, vh, title):
    """decision 菱形节点（浅橙底橙框）。"""
    x, y = sc.px(cx_v - vw / 2), sc.py(cy_v - vh / 2)
    w, h = sc.len(vw), sc.len(vh)
    return [
        shape(eid, [x, y, w, h], "flowChartDecision", fill=theme.ORANGE_LIGHT,
              border={"style": "solid", "width": 1.5, "color": theme.ORANGE}),
        text(eid + "-t", [x + w * 0.15, y + h * 0.25, w * 0.7, h * 0.5], title,
             font_size=max(10, sc.len(12)), color="#7B341E", bold=True),
    ]


def lane(eid, sc, vx, vy, vw, vh, name, tint="gray"):
    """泳道底框 + 左上带名。"""
    fills = {"gray": (theme.BG, theme.BORDER_STRONG), "green": (theme.GREEN_LIGHT, "#CFDED6")}
    fill_c, border_c = fills.get(tint, fills["gray"])
    x, y = sc.px(vx), sc.py(vy)
    w, h = sc.len(vw), sc.len(vh)
    name_fs = max(10, sc.len(13))
    # 泳道名框宽按文字实际宽度估算（原固定 320px 覆盖跨泳道连接线垂段，
    # 触发 text_stack_overlap/badge_overlap）
    name_w = min(vw - 24, est_text_w(name, name_fs) + 2 * INSET_X + 8)
    return [
        shape(eid, [x, y, w, h], "roundRect", fill=fill_c,
              border={"style": "solid", "width": 1.0, "color": border_c},
              adjustments=[4000]),
        text(eid + "-name", [x + sc.len(12), y + sc.len(8), sc.len(name_w), stack_text_h(1, name_fs)],
             name, font_size=name_fs, color=theme.TEXT_STRONG, bold=True,
             align=("left", "middle")),
    ]


def est_text_w(s, font_size):
    """估算文本宽度（px）：全角≈font_size，半角≈0.55*font_size。"""
    w = 0.0
    for ch in str(s):
        w += font_size if ord(ch) > 0x2E7F else font_size * 0.55
    return w


# 文本行高系数：与 text() 默认 line_height、_layout_lint.LINE_HEIGHT 同值（1.3）
TEXT_LINE_H = 1.3


def stack_text_h(n_lines, font_size):
    """stack 文本块框高：行数 × 字号 × TEXT_LINE_H，向上取整到 GRID 倍数。

    取整使 _snap_bounds 后框高精确（高度是 4 的倍数时四角吸附不缩框），
    给 lint text_overflow 的 1.15 余量留出吸附余量（否则精确贴合的框
    可能被 snap 缩 2~4px 而误判溢出）。
    """
    raw = n_lines * font_size * TEXT_LINE_H
    # 额外 +GRID：snap 四角各自取整最多内缩 ~4px（如 16→12），
    # 单靠向上取整在 raw 略超网格倍数时仍会被 lint text_overflow 误判。
    return math.ceil(raw / GRID) * GRID + GRID


def wrap_lines(s, font_size, avail_w):
    """按 est_text_w 贪心折行（容器盒模型 §3.2 的文本分行唯一估算）。

    CJK 逐字断行；avail_w 不足一个字宽时按每行一字兜底。
    返回行列表（空串返回 [""]，占 1 行）。HTML（SVG 逐行 <text>）与
    pptd（行数 × 行高算框高）共用，保证两端 stack 几何一致。
    """
    s = str(s)
    if not s:
        return [""]
    avail_w = max(float(avail_w), float(font_size))
    lines, cur, cur_w = [], "", 0.0
    for ch in s:
        cw = font_size if ord(ch) > 0x2E7F else font_size * 0.55
        if cur and cur_w + cw > avail_w:
            lines.append(cur)
            cur, cur_w = ch, cw
        else:
            cur += ch
            cur_w += cw
    lines.append(cur)
    return lines


def node_stack(vw, title, desc="", has_num=False,
               title_fs=13.0, desc_fs=11.0, badge_d=20.0):
    """任务节点内容堆叠预算（容器盒模型 §3.2，I-1/I-2 的通用 stack 语义）。

    参数与返回值同一单位制（HTML 侧 = viewBox 单位；pptd 侧 = 缩放 px，
    字号/直径经 sc.len 换算）。返回 (top_pad, title_h, desc_h, total_h)：
    - top_pad：标题区顶距节点顶 = max(INSET_Y, badge_d/2 + GAP_XS)
      （徽章骑缝时下摆伸入节点 badge_d/2，标题区从其下 GAP_XS 起）；
      无徽章时 = INSET_Y
    - title_h/desc_h：wrap_lines 行数 × 字号 × TEXT_LINE_H，向上取整到
      GRID 倍数（stack_text_h；吸附后框高精确，lint 溢出余量不被 snap 吃掉）
    - total_h = top_pad + title_h + (GAP_SM + desc_h) + INSET_Y（hug 总高）
    """
    avail_w = max(vw - 2 * INSET_X, title_fs)
    top_pad = max(INSET_Y, badge_d / 2 + GAP_XS) if has_num else INSET_Y
    title_h = stack_text_h(len(wrap_lines(title, title_fs, avail_w)), title_fs)
    desc_h = (stack_text_h(len(wrap_lines(desc, desc_fs, avail_w)), desc_fs)
              if desc else 0.0)
    total_h = top_pad + title_h + (GAP_SM + desc_h if desc else 0.0) + INSET_Y
    return top_pad, title_h, desc_h, total_h


def table_hug_geometry(rows_plain, col_fracs, total_w, const_h, header_frac,
                       font_size=14.0):
    """表格行高 hug 几何（间距体系 v1 §五 "行高写死"项，排查 I-16/I-17）。

    行高 = 行内单元格最大行数 × 行距 + 2×INSET_Y（单元格文本经 est_text_w
    按列宽 - 2×INSET_X 估行数，多段落按段折行累加），下限保留原写死行高
    （短内容行高不变，长内容自动撑高）。撑高后表格总高超可用空间时不在此
    截断，走 _pptd_gen 页底防线（I-16 均匀缩放/裁剪）。

    rows_plain: [[str, ...]] 每行各列纯文本（多段落用 \\n 分隔，按段折行）。
    col_fracs: 列宽比例（与元素 columnWidths 同序同单位）。
    const_h / header_frac: 原写死公式的行高常量与表头比例（各 subtype 原值，
      下限 = 原公式下该行实高，保证短内容输出与 hug 前逐字节一致）。
    返回 (table_h, row_fracs)：无行撑高时与原公式完全一致
    （n×const_h + [header_frac, (1-header_frac)/(n-1)…]），有行撑高时返回
    （Σ hug 行高， 各行高占比）。
    """
    n = len(rows_plain)
    if n == 0:
        return 0.0, []
    rest_frac = (1.0 - header_frac) / max(1, n - 1)
    old_fracs = [header_frac] + [rest_frac] * (n - 1) if n > 1 else [1.0]
    line_h = font_size * TEXT_LINE_H
    hug, grew = [], False
    for ri, row in enumerate(rows_plain):
        min_h = n * const_h * old_fracs[ri]
        max_lines = 1
        for ci, cell in enumerate(row):
            frac = col_fracs[ci] if ci < len(col_fracs) else (col_fracs[-1] if col_fracs else 1.0)
            avail = max(frac * float(total_w) - 2 * INSET_X, font_size)
            lines = 0
            for para in str(cell).split("\n"):
                para = para.strip()
                if para:
                    lines += max(1, math.ceil(est_text_w(para, font_size) / avail))
            max_lines = max(max_lines, lines)
        row_h = max(min_h, max_lines * line_h + 2 * INSET_Y)
        grew = grew or row_h > min_h + 1e-9
        hug.append(row_h)
    if not grew:
        return n * const_h, old_fracs
    table_h = sum(hug)
    return table_h, [h / table_h for h in hug]


def emit_chips(prefix, items, x, y, max_w, font_size=12, fill=None,
               color=None, gap=8, pad=14, chip_h=24):
    """chip 流式排版（自动换行）。返回 (元素列表, 消耗高度)。

    每 chip = roundRect 底 + 居中文字，宽按文本估算。
    fill/color 缺省调用时取 theme.BLUE_LIGHT/theme.BLUE（P2-A2 风格透传）。

    宽度含 2×INSET_X 余量（间距体系 v1 一层配套）：text() 内边距折算会把
    文本框收窄 2×INSET_X，OOXML 另有默认 insets（约 19px）——不补这 20px，
    双重收窄后短 label 也必折行（v7 前无折算，chip 文案均单行）。
    """
    if fill is None:
        fill = theme.BLUE_LIGHT
    if color is None:
        color = theme.BLUE
    elems, cx, cy = [], x, y
    for i, it in enumerate(items):
        w = est_text_w(it, font_size) + pad * 2 + 2 * INSET_X
        if cx + w > x + max_w and cx > x:
            cx, cy = x, cy + chip_h + gap
        elems.append(shape(f"{prefix}-chip-{i}", [cx, cy, w, chip_h],
                           "roundRect", fill=fill, adjustments=[50000]))
        elems.append(text(f"{prefix}-chipt-{i}", [cx, cy, w, chip_h], it,
                          font_size=font_size, color=color, bold=True))
        cx += w + gap
    return elems, (cy - y) + chip_h


# ---------------------------------------------------------------------------
# 视觉规范 v2.0：页面构件 + flow_rows 的 pptd 映射（dev_plan_visual_v2 §7/§8.5）
#
# 取色单点 = theme.pptd_theme（--t- tokens 扁平键），禁写字面量；中性白字与
# 既有 node() 同款 "#FFFFFF"。全部原生形状/连接符，零图像化（同源铁律）。
# 高度语义：返回 (元素列表, 消耗高度)，调用方推进 y 游标并接入页底防线。
# 方言保守集：solid fill / text(<strong>) / straightConnector1，与既有
# node/lane/emit_chips 同集，不踩未验证方言（渐变/透明度/run 级颜色）。
# ---------------------------------------------------------------------------

def _v2c(theme_name=None):
    """v2 主题 pptd 色板（T1 theme.pptd_theme 的扁平 colors）。"""
    return theme.pptd_theme(theme_name)["colors"]


def _line(eid, bounds, content, **kw):
    """单行文本（§10 文字估算常量：标题/标签/数字/导航等单行文本
    pptd 侧必须显式 wrap: false）。"""
    kw["wrap"] = False
    return text(eid, bounds, content, **kw)


def emit_hero_pptd(n, x, y, w, c):
    """hero：实底矩形（hero_to）+ eyebrow 胶囊 + 大标题 + 副标题 + meta + 统计卡。"""
    elems = []
    pad = 24.0
    inner_x, inner_w = x + pad, w - 2 * pad
    blocks = []  # 先算高度
    if n["eyebrow"]:
        blocks.append(("eyebrow", 20.0))
    blocks.append(("title", 42.0))
    if n["subtitle"]:
        blocks.append(("subtitle", 24.0))
    if n["meta"]:
        blocks.append(("meta", 20.0))
    if n["stats"]:
        blocks.append(("stats", 64.0))
    total_h = pad + sum(hh for _, hh in blocks) + 8 * (len(blocks) - 1) + pad
    elems.append(shape("hero-bg", [x, y, w, total_h], "roundRect",
                       fill=c["hero_to"], adjustments=[6000]))
    cur = y + pad
    for kind, hh in blocks:
        if kind == "eyebrow":
            cap_w = est_text_w(n["eyebrow"], 11) + 48
            elems.append(shape("hero-eb", [inner_x, cur, cap_w, hh], "roundRect",
                               fill=c["accent"], adjustments=[30000]))
            elems.append(text("hero-ebt", [inner_x, cur, cap_w, hh], n["eyebrow"],
                              font_size=11, color=c["hero_from"], bold=True))
        elif kind == "title":
            elems.append(text("hero-t", [inner_x, cur, inner_w, hh], n["title"],
                              font_size=28, color=theme.WHITE, bold=True,
                              align=("left", "middle")))
        elif kind == "subtitle":
            elems.append(text("hero-st", [inner_x, cur, inner_w, hh], n["subtitle"],
                              font_size=14, color=theme.WHITE,
                              align=("left", "middle")))
        elif kind == "meta":
            elems.append(_line("hero-m", [inner_x, cur, inner_w, hh],
                              "  ·  ".join(n["meta"]), font_size=12,
                              color=theme.WHITE, align=("left", "middle")))
        elif kind == "stats":
            n_cards = len(n["stats"])
            gap = 12.0
            cw = (inner_w - gap * (n_cards - 1)) / n_cards
            for i, s in enumerate(n["stats"]):
                cx = inner_x + i * (cw + gap)
                elems.append(shape(f"hero-sc{i}", [cx, cur, cw, hh], "roundRect",
                                   border={"style": "solid", "width": 1.0,
                                           "color": theme.WHITE},
                                   adjustments=[8000]))
                val = s["value"] + (f' {s["unit"]}' if s["unit"] else "")
                elems.append(_line(f"hero-scv{i}", [cx, cur + 6, cw, 30], val,
                                  font_size=22, color=theme.WHITE, bold=True))
                elems.append(_line(f"hero-scl{i}", [cx, cur + 38, cw, 20],
                                  s["label"], font_size=11, color=theme.WHITE))
        cur += hh + 8
    return elems, total_h


def emit_section_tag_pptd(n, x, y, w, c):
    """section_tag：浅底胶囊 + 主色字 11px/700。"""
    label = f'{n["index"]} · {n["label"]}' if n["index"] else n["label"]
    cap_w = est_text_w(label, 11) + 52
    elems = [
        shape("stag-bg", [x, y, cap_w, 22], "roundRect", fill=c["bg_soft"],
              border={"style": "solid", "width": 1.0, "color": c["border"]},
              adjustments=[30000]),
        _line("stag-t", [x, y, cap_w, 22], label, font_size=11,
             color=c["primary"], bold=True),
    ]
    return elems, 22


def emit_action_title_pptd(n, x, y, w, c):
    """action_title：21px/800 结论标题 + 可选副标题。

    PPT 侧 hl 降格为整段加粗（荧光笔/行内 run 颜色无原生对应，进不了
    pptd 方言保守集）；强调语义由 HTML 端 hl-* 承载。
    """
    parts_t = []
    for seg in n["segments"]:
        t = seg["t"]
        if parts_t and not parts_t[-1].endswith(" "):
            t = " " + t
        parts_t.append(t)
    full = "".join(parts_t)
    lines = len(wrap_lines(full, 21, w - 2 * INSET_X))
    title_h = stack_text_h(lines, 21)
    elems = [text("at-t", [x, y, w, title_h], full, font_size=21,
                  color=c["text_primary"], bold=True, align=("left", "middle"))]
    h = title_h
    if n["sub"]:
        sub_h = stack_text_h(len(wrap_lines(n["sub"], 13, w - 2 * INSET_X)), 13)
        elems.append(text("at-sub", [x, y + h + 4, w, sub_h], n["sub"],
                          font_size=13, color=c["text_secondary"],
                          align=("left", "middle")))
        h += 4 + sub_h
    return elems, h


def _tone_color(tone, c):
    return {"lit": c["lit_border"], "part": c["part_border"],
            "gap": c["gap_border"]}.get(tone, c["primary"])


def emit_stat_cards_pptd(n, x, y, w, c):
    """stat_cards：左 4px 色条 + 大数字 24px/800 + 标签（形状行）。"""
    n_cards = len(n["cards"])
    gap = 12.0
    cw = (w - gap * (n_cards - 1)) / n_cards
    card_h = 64.0
    elems = []
    for i, card in enumerate(n["cards"]):
        cx = x + i * (cw + gap)
        elems.append(shape(f"stc-{i}", [cx, y, cw, card_h], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        elems.append(shape(f"stc-bar{i}", [cx, y, 4, card_h], "rect",
                           fill=_tone_color(card["tone"], c)))
        val = card["value"] + (f' {card["unit"]}' if card["unit"] else "")
        elems.append(_line(f"stc-v{i}", [cx + 8, y + 8, cw - 8, 30], val,
                          font_size=24, color=c["text_primary"], bold=True,
                          align=("left", "middle")))
        elems.append(_line(f"stc-l{i}", [cx + 8, y + 40, cw - 8, 18],
                          card["label"], font_size=12,
                          color=c["text_secondary"], align=("left", "middle")))
    return elems, card_h


def emit_kpi_cards_pptd(n, x, y, w, c):
    """kpi_cards：from → to 大数字对比 + 指标名 + 注（形状组合）。"""
    n_cards = len(n["cards"])
    gap = 12.0
    cw = (w - gap * (n_cards - 1)) / n_cards
    card_h = 76.0
    elems = []
    for i, card in enumerate(n["cards"]):
        cx = x + i * (cw + gap)
        elems.append(shape(f"kpi-{i}", [cx, y, cw, card_h], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        elems.append(shape(f"kpi-bar{i}", [cx, y, 4, card_h], "rect",
                           fill=c["primary"]))
        elems.append(_line(f"kpi-l{i}", [cx + 8, y + 6, cw - 8, 18],
                          card["label"], font_size=12,
                          color=c["text_secondary"], align=("left", "middle")))
        # from（灰）→ to（主色大数字）三段文本框横排（数字行 y+24..y+56，
        # 与 note(y+58) 保持 2px 间隙，避免 TextDrift/Occlusion 误报）
        nx = cx + 8
        if card["from"]:
            from_w = est_text_w(card["from"], 16) + 16
            elems.append(_line(f"kpi-f{i}", [nx, y + 24, from_w, 32],
                              card["from"], font_size=16,
                              color=c["text_tertiary"], align=("left", "middle")))
            nx += from_w
            elems.append(_line(f"kpi-a{i}", [nx, y + 24, 24, 32], "→",
                              font_size=16, color=c["primary_mid"],
                              align=("center", "middle")))
            nx += 24
        elems.append(_line(f"kpi-t{i}", [nx, y + 24, cx + cw - nx - 8, 32],
                          card["to"], font_size=24, color=c["primary"],
                          bold=True, align=("left", "middle")))
        if card["note"]:
            elems.append(_line(f"kpi-n{i}", [cx + 8, y + 58, cw - 8, 14],
                              card["note"], font_size=10,
                              color=c["text_tertiary"], align=("left", "middle")))
    return elems, card_h


def emit_pain_cards_pptd(n, x, y, w, c):
    """pain_cards：标题 + level 徽章（P0 红/P1 朱橙/P2 灰）+ 量化影响。"""
    cards = n["cards"]
    n_cols = min(3, len(cards))
    gap = 12.0
    cw = (w - gap * (n_cols - 1)) / n_cols
    badge_fill = {"P0": c["role_legal"], "P1": c["part_border"],
                  "P2": c["text_tertiary"]}
    elems = []
    cur_y = float(y)
    for row_i in range(0, len(cards), n_cols):
        row = cards[row_i:row_i + n_cols]
        row_h = 0.0
        for card in row:
            body_lines = len(wrap_lines(card["body"], 12, cw - 2 * INSET_X - 16))
            hh = 14 + 20 + (18 if card["impact"] else 0) + \
                (stack_text_h(body_lines, 12) if card["body"] else 0) + 12
            row_h = max(row_h, hh)
        for ci, card in enumerate(row):
            cx = x + ci * (cw + gap)
            i = row_i + ci
            elems.append(shape(f"pain-{i}", [cx, cur_y, cw, row_h], "roundRect",
                               fill=c["card"],
                               border={"style": "solid", "width": 1.0,
                                       "color": c["border"]}, adjustments=[8000]))
            title_w = cw - 16
            if card["level"] in badge_fill:
                bw_ = 30.0
                elems.append(shape(f"pain-b{i}",
                                   [cx + cw - bw_ - 10, cur_y + 10, bw_, 18],
                                   "roundRect", fill=badge_fill[card["level"]],
                                   adjustments=[50000]))
                elems.append(_line(f"pain-b{i}t",
                                  [cx + cw - bw_ - 10, cur_y + 10, bw_, 18],
                                  card["level"], font_size=11,
                                  color=theme.WHITE, bold=True))
                title_w -= bw_ + 8
            elems.append(text(f"pain-t{i}", [cx + 8, cur_y + 10, title_w, 20],
                              card["title"], font_size=14,
                              color=c["text_primary"], bold=True,
                              align=("left", "middle")))
            cy = cur_y + 14 + 20
            if card["impact"]:
                elems.append(_line(f"pain-im{i}", [cx + 8, cy, cw - 16, 18],
                                  card["impact"], font_size=12,
                                  color=c["primary"], bold=True,
                                  align=("left", "middle")))
                cy += 18
            if card["body"]:
                elems.append(text(f"pain-bd{i}",
                                  [cx + 8, cy, cw - 16,
                                   cur_y + row_h - cy - 6],
                                  card["body"], font_size=12,
                                  color=c["text_secondary"],
                                  align=("left", "top")))
        cur_y += row_h + gap
    return elems, cur_y - y - gap


def emit_info_cards_pptd(n, x, y, w, c):
    """info_cards：菱形符标题 + items 文本行（卡片网格）。"""
    cards = n["cards"]
    n_cols = min(4, len(cards))
    gap = 12.0
    cw = (w - gap * (n_cols - 1)) / n_cols
    elems = []
    cur_y = float(y)
    for row_i in range(0, len(cards), n_cols):
        row = cards[row_i:row_i + n_cols]
        row_h = 0.0
        for card in row:
            n_lines = sum(len(wrap_lines(it, 12, cw - 2 * INSET_X - 24))
                          for it in card["items"])
            hh = 12 + 20 + (stack_text_h(n_lines, 12) if card["items"] else 0) + 10
            row_h = max(row_h, hh)
        for ci, card in enumerate(row):
            cx = x + ci * (cw + gap)
            i = row_i + ci
            elems.append(shape(f"info-{i}", [cx, cur_y, cw, row_h], "roundRect",
                               fill=c["card"],
                               border={"style": "solid", "width": 1.0,
                                       "color": c["border"]}, adjustments=[8000]))
            elems.append(shape(f"info-d{i}", [cx + 12, cur_y + 16, 9, 9],
                               "diamond", fill=c["primary"]))
            elems.append(_line(f"info-t{i}", [cx + 26, cur_y + 10, cw - 34, 20],
                              card["title"], font_size=13,
                              color=c["text_primary"], bold=True,
                              align=("left", "middle")))
            if card["items"]:
                body = "\n".join("• " + it for it in card["items"])
                elems.append(text(f"info-bd{i}",
                                  [cx + 12, cur_y + 36, cw - 20,
                                   row_h - 42],
                                  body, font_size=12,
                                  color=c["text_secondary"], align=("left", "top")))
        cur_y += row_h + gap
    return elems, cur_y - y - gap


def emit_legend_bar_pptd(n, x, y, w, c):
    """legend_bar：底条 + 小矩形色块 + label 文本行（流式横排）。"""
    bar_h = 30.0
    elems = [shape("lgb-bg", [x, y, w, bar_h], "roundRect", fill=c["bg_soft"],
                   border={"style": "solid", "width": 1.0, "color": c["border"]},
                   adjustments=[16000])]
    cx = x + 14
    cy = y + (bar_h - 14) / 2
    for i, it in enumerate(n["items"]):
        sw = it["swatch"] or "keep"
        if sw.startswith("role_"):
            fill = c.get(f"role_{sw[5:]}", c["text_tertiary"])
            border = None
        elif sw == "keep":
            fill = c["bg_muted"]
            border = {"style": "solid", "width": 1.5,
                      "color": c["text_tertiary"]}
        else:
            fill = c.get(f"{sw}_bg", c["bg_muted"])
            border = {"style": "dash" if sw == "gap" else "solid",
                      "width": 1.5,
                      "color": c.get(f"{sw}_border", c["text_tertiary"])}
        elems.append(shape(f"lgb-sw{i}", [cx, cy, 14, 14], "roundRect",
                           fill=fill, border=border, adjustments=[20000]))
        label_w = est_text_w(it["label"], 12) + 22
        elems.append(_line(f"lgb-t{i}", [cx + 18, y, label_w, bar_h], it["label"],
                          font_size=12, color=c["text_secondary"],
                          align=("left", "middle")))
        cx += 18 + label_w + 10
    return elems, bar_h


def emit_qa_block_pptd(n, x, y, w, c):
    """qa_block：左竖条 + Q 粗体 + A 段落。"""
    elems = []
    cur_y = float(y)
    for i, it in enumerate(n["items"]):
        q_h = stack_text_h(len(wrap_lines(it["q"], 13, w - 2 * INSET_X - 20)), 13)
        a_h = stack_text_h(len(wrap_lines(it["a"], 12, w - 2 * INSET_X - 20)),
                           12) if it["a"] else 0
        item_h = 10 + q_h + (4 + a_h if it["a"] else 0) + 10
        elems.append(shape(f"qa-bg{i}", [x, cur_y, w, item_h], "roundRect",
                           fill=c["bg_soft"], adjustments=[6000]))
        elems.append(shape(f"qa-bar{i}", [x, cur_y, 3, item_h], "rect",
                           fill=c["primary"]))
        elems.append(text(f"qa-q{i}", [x + 10, cur_y + 8, w - 20, q_h],
                          it["q"], font_size=13, color=c["text_primary"],
                          bold=True, align=("left", "middle")))
        if it["a"]:
            elems.append(text(f"qa-a{i}",
                              [x + 10, cur_y + 8 + q_h + 4, w - 20, a_h],
                              it["a"], font_size=12, color=c["text_secondary"],
                              align=("left", "top")))
        cur_y += item_h + 8
    return elems, cur_y - y - 8


def emit_view_cards_pptd(n, x, y, w, c):
    """view_cards：4 列视角卡 + 顶部半圆顶居中标题（D-093 麦肯锡式）。

    PPT 侧简化：半圆顶用 rect 顶部加半圆 chord 近似；4 列卡同 kpi_cards
    套路（卡片 + icon 圆 + 视角名 + 关键数字 headline + 单行 detail）。
    整体高度 = 顶条 28 + 卡体（约 96，行 hug）。
    """
    cards = n["cards"]
    n_cols = max(1, min(len(cards), 4))
    gap = 14.0
    cw = (w - gap * (n_cols - 1)) / n_cols
    cap_h = 28.0
    cap_w = min(360.0, w * 0.55)
    cx_cap = x + (w - cap_w) / 2
    elems = []
    # 顶部半圆顶：capsule 圆角矩形 + 蓝底白字（PPTD 原生 chord 半圆用
    # roundRect 100% adjustments 近似，4 列叙事 4 张图同款气质即可）
    elems.append(shape("vc-cap", [cx_cap, y, cap_w, cap_h], "roundRect",
                       fill=c["primary"], adjustments=[100000]))
    title = n.get("title", "")
    if title:
        elems.append(_line("vc-cap-t", [cx_cap, y, cap_w, cap_h], title,
                          font_size=14, color=theme.WHITE, bold=True,
                          align=("center", "middle")))
    # 4 列卡片：y 从 cap_h 下方留 12px 间隙放
    card_top = y + cap_h + 12
    card_h = 132.0
    for i, card in enumerate(cards):
        cx = x + i * (cw + gap)
        # 卡底
        elems.append(shape(f"vc-{i}", [cx, card_top, cw, card_h], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        # icon 圆（48x48 居中）
        ic = str(card.get("icon", "◆")) or "◆"
        elems.append(shape(f"vc-{i}-icon", [cx + (cw - 36) / 2, card_top + 12,
                                            36, 36], "ellipse",
                           fill=c["bg_soft"]))
        elems.append(_line(f"vc-{i}-it", [cx + (cw - 36) / 2, card_top + 12,
                                          36, 36], ic, font_size=16,
                          color=c["primary"], bold=True,
                          align=("center", "middle")))
        # 视角名
        elems.append(_line(f"vc-{i}-p", [cx + 8, card_top + 52, cw - 16, 18],
                          card["perspective"], font_size=14,
                          color=c["text_primary"], bold=True,
                          align=("center", "middle")))
        # 关键数字 headline
        hl = card.get("headline", "")
        if hl:
            elems.append(_line(f"vc-{i}-hl", [cx + 8, card_top + 70, cw - 16, 18],
                              hl, font_size=16, color=c["accent"],
                              bold=True, align=("center", "middle")))
        # detail 说明（卡高 132 后底部留 40px 两行区，对齐 HTML 端信息密度；
        # 多行必须 text(wrap=True)，_line 单行会横向溢出邻卡）
        detail = card.get("detail", "")
        if detail:
            elems.append(text(f"vc-{i}-d", [cx + 12, card_top + 92, cw - 24, 34],
                              detail, font_size=10,
                              color=c["text_secondary"],
                              align=("center", "top")))
    total_h = cap_h + 12 + card_h
    return elems, total_h


def emit_callout_block_pptd(n, x, y, w, c):
    """callout_block：底部双编号说服区（D-093）。

    淡蓝底 + 圆角容器 + 双编号（01/02）说服句。每点：编号 + 标题 + desc。
    """
    points = n["points"]
    # 单行最多 3 列（视觉平衡 2-3 个点）
    n_cols = max(1, min(len(points), 3))
    gap = 18.0
    cw = (w - gap * (n_cols - 1)) / n_cols
    cont_h = 80.0
    elems = [shape("cb-bg", [x, y, w, cont_h], "roundRect",
                   fill=c["bg_soft"],
                   border={"style": "solid", "width": 1.0,
                           "color": c["border"]}, adjustments=[8000])]
    for i, pt in enumerate(points):
        cx = x + i * (cw + gap)
        # 编号（Georgia serif 大字）
        elems.append(_line(f"cb-n{i}", [cx + 14, y + 10, 50, 32],
                          str(pt["num"]), font_size=22,
                          color=c["primary"], bold=True,
                          align=("left", "top")))
        # 标题（含 highlight 红色，可选附 16px 文本——PPTD 单段不支持
        # 行内变色，简化为标题全段 primary + highlight 单独追加）
        # 高度 20 单行收尾，与下方 hl（y+32）留出 2px 间隙——此前 h=28
        # 与 hl 纵向相交 6px 触发 text_stack_overlap（I-2）
        elems.append(_line(f"cb-t{i}", [cx + 64, y + 10, cw - 78, 20],
                          str(pt["title"]), font_size=13,
                          color=c["text_primary"], bold=True,
                          align=("left", "top")))
        hl = pt.get("highlight", "")
        if hl:
            # highlight 置标题下方左侧小字（红色强调）
            elems.append(_line(f"cb-hl{i}", [cx + 64, y + 32, cw - 78, 16],
                              hl, font_size=12, color=c["accent"],
                              bold=True, align=("left", "middle")))
        # desc
        desc = pt.get("desc", "")
        if desc:
            elems.append(_line(f"cb-d{i}", [cx + 64, y + 50, cw - 78, 24],
                              desc, font_size=11,
                              color=c["text_secondary"], align=("left", "top")))
    return elems, cont_h


def emit_page_header_pptd(n, x, y, w, c):
    """page_header 页眉横幅（D-092）：渐变矩形 + EX 编号徽章 + 标题 + 章节胶囊 + meta。"""
    elems = []
    h = 64.0
    elems.append(shape("ph-bg", [x, y, w, h], "roundRect",
                       fill=c["hero_to"], adjustments=[8000]))
    idx = n.get("index", "")
    ix = x + 16
    if idx:
        # 宽度余量：est_text_w 对粗体 Latin 混排低估约 15-20%（目检发现
        # "EXHIBIT 13" 在 PowerPoint 实际渲染折行），乘 1.2 安全系数 +
        # 26px padding；_line 强制单行兜底
        bw = 26 + est_text_w(idx, 12) * 1.2
        elems.append(shape("ph-idx", [ix, y + 20, bw, 24], "roundRect",
                           fill=c["accent"], adjustments=[50000]))
        elems.append(_line("ph-idxt", [ix, y + 20, bw, 24], idx,
                          font_size=12, color=c["hero_from"], bold=True))
        ix += bw + 12
    title = n.get("title", "")
    tag = n.get("tag", "")
    # 章节胶囊宽度按文本估算动态放（24 padding + 文本宽，上限 300）——固定
    # 130px 装不下「第三章 · 方案架构与能力」级长 tag，估算 2 行触发 overflow
    tag_w = min(24.0 + est_text_w(tag, 12) * 1.2, 320.0) if tag else 0.0
    right_w = tag_w + 24 if tag else 24.0
    metas = n.get("meta") or []
    # 有 meta 行时标题框压到上部 40px（y+2..y+42），与 meta（y+42 起）相邻
    # 不交——此前标题框占满 64px 与 meta 纵向相交 71% 触发 text_stack_overlap
    t_h = 40.0 if metas else h
    t_y = y + 2 if metas else y
    elems.append(text("ph-title", [ix, t_y, max(w - ix - right_w, 200), t_h], title,
                      font_size=20, color=theme.WHITE, bold=True,
                      align=("left", "middle")))
    if tag:
        tx = x + w - tag_w - 24
        elems.append(shape("ph-tag", [tx, y + 20, tag_w, 24], "roundRect",
                           fill=c["bg_soft"], adjustments=[50000]))
        elems.append(_line("ph-tagt", [tx, y + 20, tag_w, 24], tag,
                          font_size=12, color=c["hero_from"], bold=True))
    if metas:
        mtext = "  ·  ".join(str(m) for m in metas)
        # y+46（原 y+42）：与 idx/tag 胶囊行（y+20..44）留 2px 净距——此前
        # 纵向相交 2px 触发 TextOcclusion/TextDrift 连锁警告
        elems.append(_line("ph-meta", [x + 16, y + 46, w - 32, 16], mtext,
                           font_size=10, color=theme.WHITE,
                           align=("left", "middle")))
    return elems, h


def emit_toc_cards_pptd(n, x, y, w, c):
    """toc_cards：2 列目录卡（编号 + 标题 + 可选描述），P12。"""
    cards = n["cards"]
    if not cards:
        return [], 0
    n_cols = min(2, len(cards))  # 单卡占满宽度
    gap = 12.0
    cw = (w - gap * (n_cols - 1)) / n_cols
    elems = []
    cur_y = float(y)
    for row_i in range(0, len(cards), n_cols):
        row = cards[row_i:row_i + n_cols]
        row_h = 0.0
        for card in row:
            tl = len(wrap_lines(card["title"], 13, cw - 60 - 2 * INSET_X))
            dl = (len(wrap_lines(card["desc"], 11, cw - 60 - 2 * INSET_X))
                  if card["desc"] else 0)
            hh = 10 + stack_text_h(tl, 13) + (GAP_SM + stack_text_h(dl, 11)
                                              if dl else 0) + 8
            row_h = max(row_h, hh)
        for ci, card in enumerate(row):
            cx = x + ci * (cw + gap)
            i = row_i + ci
            elems.append(shape(f"toc-{i}", [cx, cur_y, cw, row_h], "roundRect",
                               fill=c["card"],
                               border={"style": "solid", "width": 1.0,
                                       "color": c["border"]},
                               adjustments=[8000]))
            elems.append(_line(f"toc-n{i}", [cx + 12, cur_y + 8, 40, 22],
                               card["num"], font_size=16, color=c["primary"],
                               bold=True, align=("left", "middle")))
            elems.append(_line(f"toc-t{i}", [cx + 56, cur_y + 8, cw - 68, 20],
                               card["title"], font_size=13,
                               color=c["text_primary"], bold=True,
                               align=("left", "middle")))
            if card["desc"]:
                elems.append(text(f"toc-d{i}",
                                  [cx + 56, cur_y + 30, cw - 68, row_h - 36],
                                  card["desc"], font_size=11,
                                  color=c["text_secondary"],
                                  align=("left", "top")))
        cur_y += row_h + gap
    return elems, cur_y - y - gap


def emit_duo_compare_pptd(n, x, y, w, c):
    """duo_compare：左右双面板 + 1px 中隔线，P14。"""
    gap = 16.0
    pw = (w - gap * 2) / 2
    elems = []
    max_h = 0.0
    for _, key in enumerate(("left", "right")):
        side = n[key]
        tl = len(wrap_lines(side["title"], 14, pw - 2 * INSET_X))
        bl = sum(len(wrap_lines(p, 12, pw - 2 * INSET_X - 16))
                 for p in side["points"])
        h = stack_text_h(tl, 14) + 8 + (stack_text_h(bl, 12) if bl else 0) + 8
        max_h = max(max_h, h)
    for pi, key in enumerate(("left", "right")):
        side = n[key]
        px = x if pi == 0 else x + pw + gap * 2
        elems.append(_line(f"duo-t{pi}", [px, y, pw, 22], side["title"],
                           font_size=14, color=c["text_primary"], bold=True,
                           align=("left", "top")))
        if side["points"]:
            body = "\n".join("• " + p for p in side["points"])
            elems.append(text(f"duo-b{pi}", [px, y + 26, pw, max(max_h - 30, 12)],
                              body, font_size=12, color=c["text_secondary"],
                              align=("left", "top")))
    elems.append(shape("duo-vr", [x + pw + gap, y, 1.5, max_h], "rect",
                       fill=c["border"]))
    return elems, max_h


def emit_pros_cons_pptd(n, x, y, w, c):
    """pros_cons：pros/cons 双列（绿/橙头），P15。"""
    gap = 16.0
    pw = (w - gap) / 2
    elems = []
    max_h = 0.0
    cols = [("pros", c["lit_text"], "优势"),
            ("cons", c["part_text"], "风险/成本")]
    # 先算高度（跳过空侧）
    non_empty = [(key, hc, head) for key, hc, head in cols if n[key]]
    if not non_empty:
        return [], 0
    for key, _, _ in non_empty:
        items = n[key]
        bl = sum(len(wrap_lines(p, 12, pw - 2 * INSET_X - 16)) for p in items)
        h = 12 + 20 + (stack_text_h(bl, 12) if items else 0) + 10
        max_h = max(max_h, h)
    # 渲染非空侧
    for pi, (key, hc, head) in enumerate(non_empty):
        items = n[key]
        px = x + pi * (pw + gap)
        elems.append(shape(f"pc-bg{pi}", [px, y, pw, max_h], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        elems.append(_line(f"pc-h{pi}", [px + 12, y + 8, pw - 24, 20], head,
                           font_size=13, color=hc, bold=True,
                           align=("left", "middle")))
        if items:
            body = "\n".join("• " + p for p in items)
            elems.append(text(f"pc-b{pi}", [px + 12, y + 32, pw - 24,
                                            max(max_h - 40, 12)],
                              body, font_size=12, color=c["text_secondary"],
                              align=("left", "top")))
    return elems, max_h


def emit_cta_block_pptd(n, x, y, w, c):
    """cta_block：深色横幅 + 白标题 + accent 按钮 + 联系方式，P16。"""
    h = 96.0
    elems = [shape("cta-bg", [x, y, w, h], "roundRect", fill=c["hero_to"],
                   adjustments=[6000])]
    elems.append(_line("cta-t", [x + 24, y + 12, w - 48, 28], n["title"],
                       font_size=18, color=c["card"], bold=True,
                       align=("center", "middle")))
    if n["button"]:
        bw = 160.0
        bx = x + (w - bw) / 2
        elems.append(shape("cta-btn", [bx, y + 46, bw, 26], "roundRect",
                           fill=c["accent"], adjustments=[50000]))
        elems.append(_line("cta-bt", [bx, y + 46, bw, 26], n["button"],
                           font_size=12, color=c["hero_from"], bold=True,
                           align=("center", "middle")))
    if n["contact"]:
        elems.append(_line("cta-c", [x + 24, y + 76, w - 48, 16],
                           n["contact"], font_size=10, color=c["card"],
                           align=("center", "middle")))
    return elems, h


def emit_evidence_ledger_pptd(n, x, y, w, c):
    """evidence_ledger 证据台账（B-3）：四列静态表格（编号/结论/证据/状态）。"""
    elems = []
    cur_y = float(y)
    if n.get("title"):
        elems.append(_line("ev-t", [x, cur_y, w, 22], n["title"],
                           font_size=14, color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        cur_y += 28
    col_w = [w * 0.12, w * 0.36, w * 0.40, w * 0.12]
    headers = ["编号", "结论", "证据", "状态"]
    row_h = 24.0
    hx = x
    for i, hd in enumerate(headers):
        elems.append(shape(f"ev-h{i}", [hx, cur_y, col_w[i], row_h], "rect",
                           fill=c["bg_muted"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}))
        elems.append(_line(f"ev-ht{i}", [hx + 6, cur_y + 4, col_w[i] - 12, 16],
                           hd, font_size=11, color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        hx += col_w[i]
    cur_y += row_h
    for ri, it in enumerate(n["items"]):
        vals = [it["num"] or "—", it["conclusion"],
                it["evidence"], it["status"] or "—"]
        hx = x
        for ci, v in enumerate(vals):
            elems.append(shape(f"ev-r{ri}-{ci}", [hx, cur_y, col_w[ci], row_h],
                               "rect", fill=c["card"],
                               border={"style": "solid", "width": 1.0,
                                       "color": c["border"]}))
            elems.append(_line(f"ev-rt{ri}-{ci}",
                               [hx + 6, cur_y + 4, col_w[ci] - 12, 16],
                               v, font_size=10, color=c["text_secondary"],
                               align=("left", "middle")))
            hx += col_w[ci]
        cur_y += row_h
    return elems, cur_y - y


def emit_risk_register_pptd(n, x, y, w, c):
    """risk_register 风险登记（B-4）：四列静态表格（风险/等级/状态/应对）。"""
    elems = []
    cur_y = float(y)
    if n.get("title"):
        elems.append(_line("rk-t", [x, cur_y, w, 22], n["title"],
                           font_size=14, color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        cur_y += 28
    col_w = [w * 0.30, w * 0.10, w * 0.18, w * 0.42]
    headers = ["风险", "等级", "状态", "应对"]
    row_h = 24.0
    hx = x
    for i, hd in enumerate(headers):
        elems.append(shape(f"rk-h{i}", [hx, cur_y, col_w[i], row_h], "rect",
                           fill=c["bg_muted"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}))
        elems.append(_line(f"rk-ht{i}", [hx + 6, cur_y + 4, col_w[i] - 12, 16],
                           hd, font_size=11, color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        hx += col_w[i]
    cur_y += row_h
    for ri, it in enumerate(n["items"]):
        vals = [it["risk"], it["level"] or "—",
                it["status"] or "—", it["response"]]
        hx = x
        for ci, v in enumerate(vals):
            elems.append(shape(f"rk-r{ri}-{ci}", [hx, cur_y, col_w[ci], row_h],
                               "rect", fill=c["card"],
                               border={"style": "solid", "width": 1.0,
                                       "color": c["border"]}))
            elems.append(_line(f"rk-rt{ri}-{ci}",
                               [hx + 6, cur_y + 4, col_w[ci] - 12, 16],
                               v, font_size=10, color=c["text_secondary"],
                               align=("left", "middle")))
            hx += col_w[ci]
        cur_y += row_h
    return elems, cur_y - y


def emit_raci_matrix_pptd(n, x, y, w, c):
    """raci_matrix 角色责任矩阵（B-5）：动态列矩阵（任务 + 角色列）。"""
    elems = []
    cur_y = float(y)
    if n.get("title"):
        elems.append(_line("rc-t", [x, cur_y, w, 22], n["title"],
                           font_size=14, color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        cur_y += 28
    roles = n["roles"]
    if not roles or not n["tasks"]:
        return elems, cur_y - y
    task_w = w * 0.24
    role_w = (w - task_w) / len(roles)
    row_h = 24.0
    hx = x
    elems.append(shape("rc-h0", [hx, cur_y, task_w, row_h], "rect",
                       fill=c["bg_muted"],
                       border={"style": "solid", "width": 1.0,
                               "color": c["border"]}))
    elems.append(_line("rc-ht0", [hx + 6, cur_y + 4, task_w - 12, 16],
                       "任务", font_size=11, color=c["text_primary"], bold=True,
                       align=("left", "middle")))
    hx += task_w
    for i, r in enumerate(roles):
        elems.append(shape(f"rc-h{i + 1}", [hx, cur_y, role_w, row_h], "rect",
                           fill=c["bg_muted"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}))
        elems.append(_line(f"rc-ht{i + 1}", [hx + 6, cur_y + 4, role_w - 12, 16],
                           r, font_size=11, color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        hx += role_w
    cur_y += row_h
    for ri, t in enumerate(n["tasks"]):
        hx = x
        elems.append(shape(f"rc-r{ri}-0", [hx, cur_y, task_w, row_h], "rect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}))
        elems.append(_line(f"rc-rt{ri}-0", [hx + 6, cur_y + 4, task_w - 12, 16],
                           t["task"], font_size=10, color=c["text_secondary"],
                           align=("left", "middle")))
        hx += task_w
        for ci, r in enumerate(roles):
            v = t["cells"].get(r, "")
            elems.append(shape(f"rc-r{ri}-{ci + 1}", [hx, cur_y, role_w, row_h],
                               "rect", fill=c["card"],
                               border={"style": "solid", "width": 1.0,
                                       "color": c["border"]}))
            elems.append(_line(f"rc-rt{ri}-{ci + 1}",
                               [hx + 6, cur_y + 4, role_w - 12, 16],
                               v, font_size=10, color=c["text_secondary"],
                               align=("left", "middle")))
            hx += role_w
        cur_y += row_h
    return elems, cur_y - y


def emit_decision_board_pptd(n, x, y, w, c):
    """decision_board 决策面板（B-6）：方案卡 + 推荐横幅 + 下一步。"""
    elems = []
    cur_y = float(y)
    if n.get("title"):
        elems.append(_line("db-t", [x, cur_y, w, 22], n["title"],
                           font_size=14, color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        cur_y += 28
    opts = n["options"]
    if opts:
        n_cols = min(3, len(opts))
        gap = 12.0
        cw = (w - gap * (n_cols - 1)) / n_cols
        card_h = 84.0
        for i, opt in enumerate(opts):
            cx = x + (i % n_cols) * (cw + gap)
            cy = cur_y + (i // n_cols) * (card_h + gap)
            body = "\n".join([f"+ {p}" for p in opt["pros"]] +
                             [f"- {c}" for c in opt["cons"]])
            elems.append(shape(f"db-c{i}", [cx, cy, cw, card_h], "roundRect",
                               fill=c["card"],
                               border={"style": "solid", "width": 1.0,
                                       "color": c["border"]}, adjustments=[8000]))
            elems.append(_line(f"db-ct{i}", [cx + 10, cy + 6, cw - 20, 18],
                               opt["name"], font_size=12, color=c["text_primary"],
                               bold=True, align=("left", "middle")))
            elems.append(text(f"db-cb{i}", [cx + 10, cy + 28, cw - 16, 52],
                              body, font_size=10, color=c["text_secondary"],
                              align=("left", "top")))
        cur_y += ((len(opts) + n_cols - 1) // n_cols) * (card_h + gap)
    if n.get("recommendation"):
        elems.append(shape("db-r", [x, cur_y, w, 32], "roundRect",
                           fill=c["primary_mid"], adjustments=[8000]))
        elems.append(_line("db-rt", [x + 12, cur_y + 6, w - 24, 20],
                           "推荐：" + n["recommendation"], font_size=12,
                           color=theme.WHITE, bold=True, align=("left", "middle")))
        cur_y += 40
    if n.get("next_step"):
        elems.append(_line("db-n", [x, cur_y, w, 18], n["next_step"],
                           font_size=11, color=c["text_secondary"],
                           align=("left", "middle")))
        cur_y += 22
    return elems, cur_y - y


_CHROME_PPTD_EMITTERS = {
    "hero": emit_hero_pptd,
    "section_tag": emit_section_tag_pptd,
    "page_header": emit_page_header_pptd,
    "action_title": emit_action_title_pptd,
    "stat_cards": emit_stat_cards_pptd,
    "kpi_cards": emit_kpi_cards_pptd,
    "pain_cards": emit_pain_cards_pptd,
    "info_cards": emit_info_cards_pptd,
    "legend_bar": emit_legend_bar_pptd,
    "qa_block": emit_qa_block_pptd,
    # D-093 view_cards（4 列视角卡 + 顶半圆顶）+ callout_block（底部说服区）
    "view_cards": emit_view_cards_pptd,
    "callout_block": emit_callout_block_pptd,
    # v3.0 版式构件（P12/P14/P15/P16）
    "toc_cards": emit_toc_cards_pptd,
    "duo_compare": emit_duo_compare_pptd,
    "pros_cons": emit_pros_cons_pptd,
    "cta_block": emit_cta_block_pptd,
    # 批次 B 组件（B-3 证据台账）
    "evidence_ledger": emit_evidence_ledger_pptd,
    "risk_register": emit_risk_register_pptd,
    "raci_matrix": emit_raci_matrix_pptd,
    "decision_board": emit_decision_board_pptd,
}


def emit_chrome_pptd(elem_type, normalized, x, y, w, theme_name=None):
    """v2 页面构件 pptd 总分派。返回 (元素列表, 消耗高度)。

    topnav 不在此（§5.2 PPTD 端 DEGRADE，由 _pptd_gen 走 degrade_text）。
    未知 type 返回 ([], 0)（调用方保证只传已声明 RENDER 的构件）。
    """
    emitter = _CHROME_PPTD_EMITTERS.get(elem_type)
    if emitter is None:
        return [], 0
    return emitter(normalized, x, y, w, _v2c(theme_name))


# ---------------------------------------------------------------------------
# flow_rows pptd 映射（§8.5：全原生形状 + straightConnector1，零图像化）
# ---------------------------------------------------------------------------

def render_flow_rows_pptd(elem, x, y, w, theme_name=None):
    """flow_rows -> (pptd 元素列表, 消耗高度)。

    映射契约（§8.5）：卡=roundRect+顶条 3px 矩形色条；badge=oval+白字；
    行内 →/行间 ↓=straightConnector1+arrow；dashed_opt 行=roundRect 边框
    dash+part 浅底；行级底色=底层矩形（先 emit 垫底）；legend=小矩形+文本行。
    布局：单行 cards 等宽，行高按行内卡文本 hug，行间箭头 20px。
    """
    c = _v2c(theme_name)
    from ..schema import FLOW_ROLES
    rows = [r for r in (elem.get("rows", []) or []) if isinstance(r, dict)]
    elems = []
    cur_y = float(y)
    label_w = 86.0
    opt_w = 56.0   # 无行标签的可选项行：「可选项」文本宽
    arrow_w = 22.0
    card_gap = 6.0

    for ri, row in enumerate(rows):
        arrow = row.get("arrow")
        if arrow:
            # 行间箭头：垂直 straightConnector1（up 由端点反向推导 flipV）
            cx_mid = x + w / 2
            if arrow == "down":
                elems.append(connector(f"fr-v{ri}", cx_mid, cur_y + 2,
                                       cx_mid, cur_y + 12,
                                       color=c["primary_mid"], width=1.25))
            else:
                elems.append(connector(f"fr-v{ri}", cx_mid, cur_y + 12,
                                       cx_mid, cur_y + 2,
                                       color=c["primary_mid"], width=1.25))
            cur_y += 14
            continue
        cards = [cd for cd in (row.get("cards", []) or []) if isinstance(cd, dict)]
        if not cards:
            continue
        dashed_opt = row.get("style") == "dashed_opt"
        has_label = bool(row.get("label"))
        left_w = label_w if has_label else (opt_w if dashed_opt else 0.0)
        # 行高 hug：行数估算复用 v1.2 单点 wrap_lines/stack_text_h，间距
        # 用 spacing 常量（GAP_SM/INSET_X）——与 27 种图同一几何语义；
        # badge 置卡内（不骑缝：骑缝 numt 必触发 pyz TextDrift，§10 检查 7）
        avail_cards_w = w - left_w - (len(cards) - 1) * (arrow_w + 2 * card_gap)
        cw = avail_cards_w / len(cards)
        card_hs = []
        card_metrics = []  # (title_h, desc_h, has_badge)
        for cd in cards:
            has_badge = bool(cd.get("badge")) and not dashed_opt
            # badge 在左占 30px（8 偏移 + 18 圆点 + 4 间距）
            label_avail = cw - (34 if has_badge else 12) - 2 * INSET_X
            lh_ = len(wrap_lines(cd.get("label", ""), 13, label_avail))
            dh_ = len(wrap_lines(cd.get("desc", ""), 11,
                                 cw - 12 - 2 * INSET_X)) if cd.get("desc") else 0
            title_h = stack_text_h(lh_, 13)
            desc_h = stack_text_h(dh_, 11) if dh_ else 0
            card_metrics.append((title_h, desc_h, has_badge))
            card_hs.append(10 + title_h + (GAP_SM + desc_h if dh_ else 0) + 8)
        row_h = max(max(card_hs), 44.0)

        # 底层：行级分组底色 / dashed_opt 虚线框（z-order 最底，先 emit）
        if dashed_opt:
            elems.append(shape(f"fr-optbg{ri}", [x, cur_y, w, row_h], "roundRect",
                               fill=c["part_bg"],
                               border={"style": "dash", "width": 1.5,
                                       "color": c["part_border"]},
                               adjustments=[6000]))
        elif row.get("group") in ("blue", "teal"):
            elems.append(shape(f"fr-bg{ri}", [x, cur_y, w, row_h], "roundRect",
                               fill=c[f"group_{row['group']}"],
                               adjustments=[6000]))
        # 行标签 / 可选项标签
        if has_label:
            label_text = row["label"] + (f'\n{row["label_sub"]}'
                                         if row.get("label_sub") else "")
            elems.append(text(f"fr-lb{ri}", [x + 6, cur_y, label_w - 10, row_h],
                              label_text, font_size=12, color=c["primary"],
                              bold=True, align=("left", "middle")))
            elems.append(shape(f"fr-lbd{ri}",
                               [x + label_w - 4, cur_y + 8, 2, row_h - 16],
                               "rect", fill=c["primary_mid"]))
        elif dashed_opt:
            elems.append(_line(f"fr-opt-tag{ri}",
                              [x + 4, cur_y, opt_w - 6, row_h], "可选项",
                              font_size=11, color=c["part_border"], bold=True,
                              align=("left", "middle")))
        # 卡片 + 行内箭头
        cx = x + left_w
        for ci, cd in enumerate(cards):
            if ci > 0:
                elems.append(connector(
                    f"fr-a{ri}-{ci}", cx + card_gap, cur_y + row_h / 2,
                    cx + arrow_w + card_gap, cur_y + row_h / 2,
                    color=(c["part_border"] if dashed_opt else c["primary_mid"]),
                    width=1.25, dash=dashed_opt))
                cx += arrow_w + 2 * card_gap
            role = cd.get("role") if cd.get("role") in FLOW_ROLES else None
            top_c = c[f"role_{role}"] if role else c["primary"]
            text_c = c["part_border"] if dashed_opt else c["text_primary"]
            if cd.get("dim"):
                text_c = c["text_tertiary"]
            elems.append(shape(f"fr-c{ri}-{ci}", [cx, cur_y + 4, cw, row_h - 8],
                               "roundRect", fill=c["card"],
                               border={"style": "solid", "width": 1.5,
                                       "color": c["border"]},
                               adjustments=[8000]))
            elems.append(shape(f"fr-c{ri}-{ci}-top", [cx, cur_y + 4, cw, 3],
                               "rect", fill=top_c))
            has_badge = bool(cd.get("badge")) and not dashed_opt
            title_h, desc_h, _ = card_metrics[ci]
            # 卡内 stack：badge 在左（卡内顶条之下）、label 同排在右，
            # desc 顶 = label 底 + GAP_SM（v1.2 间距常量）
            # 顶部 padding 用 10 与卡高预算（10+title+(GAP_SM+desc)+8）对齐，
            # 避免 desc 底比卡底低（TextDrift，§10 检查 7）
            ty = cur_y + 4 + 10
            if has_badge:
                elems.append(shape(f"fr-c{ri}-{ci}-num",
                                   [cx + 8, ty, 18, 18], "ellipse",
                                   fill=c["primary_dark"]))
                elems.append(_line(f"fr-c{ri}-{ci}-numt",
                                  [cx + 8, ty, 18, 18], str(cd["badge"]),
                                  font_size=10, color=theme.WHITE, bold=True))
            label_x = cx + 30 if has_badge else cx + 8
            label_w_ = cw - 34 if has_badge else cw - 12
            elems.append(text(f"fr-c{ri}-{ci}-label",
                              [label_x, ty, label_w_, title_h],
                              cd.get("label", ""), font_size=13, color=text_c,
                              bold=True, align=("left", "middle")))
            if cd.get("desc"):
                elems.append(text(f"fr-c{ri}-{ci}-desc",
                                  [cx + 8, ty + title_h + GAP_SM,
                                   cw - 12, desc_h],
                                  cd["desc"], font_size=11,
                                  color=c["text_secondary"],
                                  align=("left", "top")))
            cx += cw
        cur_y += row_h + 6

    # roles → legend 自动生成（§8.1：>2 色；与 HTML 侧同语义）
    roles = elem.get("roles")
    if isinstance(roles, dict) and len(roles) > 2:
        legend_items = [{"swatch": f"role_{k}", "label": v.get("label", k)}
                        for k, v in roles.items()
                        if k in FLOW_ROLES and isinstance(v, dict)]
        lg_elems, lg_h = emit_legend_bar_pptd(
            {"items": legend_items}, x, cur_y + 4, w, c)
        elems.extend(lg_elems)
        cur_y += 4 + lg_h

    return elems, cur_y - y
