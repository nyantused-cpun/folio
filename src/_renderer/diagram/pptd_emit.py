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

from .. import theme
from ..elements import _esc  # 单一源（§七 2.6），删除本地重复定义
from ..spacing import GAP_SM, GAP_XS, GRID, INSET_X, INSET_Y, snap, est_text_w


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
          flip=None, decor=None):
    """preset shape 元素。border: {"style": solid|dash, "width": px, "color": hex}

    decor: 预留装饰标记（ui_mock 公章/装饰条等），供 bbox 观察数据消费。
    """
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
    if decor:
        el["decor"] = True
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
        "trigger": (theme.ORANGE_LIGHT, theme.ORANGE, theme.ORANGE,
                    theme.mix(theme.ORANGE, theme.TEXT, 0.45)),
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
             font_size=max(10, sc.len(12)), color=theme.mix(theme.ORANGE, theme.TEXT, 0.45), bold=True),
    ]


def lane(eid, sc, vx, vy, vw, vh, name, tint="gray", strip=None):
    """泳道底框 + 道名。

    v1.4：strip=道头色条色（实色左条 + 竖排白字，CJK 窄框逐字折行），
    不传时保留旧版左上横排带名（cross_system 列容器仍走旧版）。
    tint: gray=BG 底 / white=白底（泳道交替底色）/ green=green_light。
    """
    fills = {"gray": (theme.BG, theme.BORDER_STRONG),
             "white": (theme.WHITE, theme.BORDER_STRONG),
             "green": (theme.GREEN_LIGHT, "#CFDED6")}
    fill_c, border_c = fills.get(tint, fills["gray"])
    x, y = sc.px(vx), sc.py(vy)
    w, h = sc.len(vw), sc.len(vh)
    name_fs = max(10, sc.len(13))
    if strip is not None:
        sw = sc.len(38)
        return [
            shape(eid, [x, y, w, h], "roundRect", fill=fill_c,
                  border={"style": "solid", "width": 1.0, "color": border_c},
                  adjustments=[4000]),
            shape(eid + "-strip", [x, y, sw, h], "roundRect", fill=strip,
                  adjustments=[12000]),
            # 右半补方角：条左圆右方，贴合道框左缘
            shape(eid + "-strip-sq", [x + sw / 2, y, sw / 2, h], "rect", fill=strip),
            text(eid + "-name", [x, y, sw, h],
                 name, font_size=name_fs, color=theme.WHITE, bold=True,
                 align=("center", "middle")),
        ]
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
               color=None, gap=8, pad=14, chip_h=24, border=None):
    """chip 流式排版（自动换行）。返回 (元素列表, 消耗高度)。

    每 chip = roundRect 底 + 居中文字，宽按文本估算。
    fill/color 缺省调用时取 theme.BLUE_LIGHT/theme.BLUE（P2-A2 风格透传）。

    宽度含 2×INSET_X 余量（间距体系 v1 一层配套）：text() 内边距折算会把
    文本框收窄 2×INSET_X，OOXML 另有默认 insets（约 19px）——不补这 20px，
    双重收窄后短 label 也必折行（蓝海集团 v7 前无折算，chip 文案均单行）。
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
                           "roundRect", fill=fill, adjustments=[50000],
                           border=border))
        elems.append(text(f"{prefix}-chipt-{i}", [cx, cy, w, chip_h], it,
                          font_size=font_size, color=color, bold=True))
        cx += w + gap
    return elems, (cy - y) + chip_h


def chips_height(items, max_w, font_size=12, gap=8, pad=14, chip_h=24):
    """chip 流高度预估（与 emit_chips 同参数同结果）：容器先定高再排 chip 时用。"""
    cx, lines = 0.0, 1
    for it in items:
        w = est_text_w(it, font_size) + pad * 2 + 2 * INSET_X
        if cx > 0 and cx + w > max_w:
            lines += 1
            cx = 0.0
        cx += w + gap
    return lines * chip_h + (lines - 1) * gap


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


# ---- S8-B 棘轮拆小（2026-09-07）：chrome 构件发射器族迁 pptd_emit_chrome
# （v2/v3 构件 + map/dispatch）与 pptd_emit_ext（批次 B/ui_mock/conclusion_band）。
# 动因：本文件 1826 行 > 基线 cap 1606（只许拆小不许加码；b722f01 _spec_hex 先例）。
# 本模块保留 _v2c/_line（flow_rows 仍消费）并经懒加载转发保持既有 import 面不变。


def emit_chrome_pptd(elem_type, normalized, x, y, w, theme_name=None):
    """chrome 构件 pptd 总分派（实现已迁 pptd_emit_chrome，此处懒加载转发）。"""
    from .pptd_emit_chrome import emit_chrome_pptd as _impl
    return _impl(elem_type, normalized, x, y, w, theme_name)


def emit_legend_bar_pptd(n, x, y, w, c):
    """legend_bar 发射器（已迁 pptd_emit_chrome，懒加载转发；flow_rows 裸名消费）。"""
    from .pptd_emit_chrome import emit_legend_bar_pptd as _impl
    return _impl(n, x, y, w, c)


# 模块属性懒加载转发（PEP 562）：pptd_emit.emit_xxx_pptd 等既有引用零改动
_CHROME_REEXPORT = (
    "emit_hero_pptd", "emit_section_tag_pptd", "emit_page_header_pptd",
    "emit_action_title_pptd", "emit_stat_cards_pptd", "emit_kpi_cards_pptd",
    "emit_pain_cards_pptd", "emit_info_cards_pptd", "emit_legend_bar_pptd",
    "emit_qa_block_pptd", "emit_view_cards_pptd", "emit_callout_block_pptd",
    "emit_toc_cards_pptd", "emit_duo_compare_pptd", "emit_pros_cons_pptd",
    "emit_cta_block_pptd", "emit_sla_block_pptd", "emit_profile_card_pptd",
    "emit_logo_wall_pptd", "emit_evidence_ledger_pptd", "emit_risk_register_pptd",
    "emit_raci_matrix_pptd", "emit_decision_board_pptd", "emit_ui_mock_pptd",
    "emit_conclusion_band_pptd", "_CHROME_PPTD_EMITTERS",
)


def __getattr__(name):
    if name in _CHROME_REEXPORT:
        from . import pptd_emit_chrome as _chrome
        return getattr(_chrome, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



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
        dashed_opt = row.get("style") == "dashed_opt"
        has_label = bool(row.get("label"))
        # 有标签无卡片的行：HTML 端保留（只渲染行标签），pptd 同步保留不整行丢弃
        if not cards and not has_label:
            continue
        left_w = label_w if has_label else (opt_w if dashed_opt else 0.0)
        # 行高 hug：行数估算复用 v1.2 单点 wrap_lines/stack_text_h，间距
        # 用 spacing 常量（GAP_SM/INSET_X）——与其他 diagram 同一几何语义；
        # badge 置卡内（不骑缝：骑缝 numt 必触发 pyz TextDrift，§10 检查 7）
        avail_cards_w = w - left_w - (len(cards) - 1) * (arrow_w + 2 * card_gap)
        cw = avail_cards_w / len(cards) if cards else 0.0
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
        row_h = max(max(card_hs), 44.0) if card_hs else 44.0

        # 底层：行级分组底色 / dashed_opt 虚线框（z-order 最底，先 emit）
        if dashed_opt:
            elems.append(shape(f"fr-optbg{ri}", [x, cur_y, w, row_h], "roundRect",
                               fill=c["part_bg"],
                               border={"style": "dash", "width": 1.5,
                                       "color": c["part_border"]},
                               adjustments=[6000]))
        elif row.get("group") in ("blue", "teal", "red", "gray") and \
                c.get(f"group_{row['group']}"):
            elems.append(shape(f"fr-bg{ri}", [x, cur_y, w, row_h], "roundRect",
                               fill=c[f"group_{row['group']}"],
                               adjustments=[6000]))
        # 行标签 / 可选项标签
        if has_label:
            sub = str(row.get("label_sub", "") or "")
            label_text = row["label"] + (f'\n{sub}' if sub else "")
            # label_sub 过长时窄栏换行溢出（示例项目 v4 实战暴露，§7.2-5）：
            # 估算折行超 3 行自动降字号 12→10→9
            lb_fs = 12
            if sub:
                while lb_fs > 9 and len(wrap_lines(label_text, lb_fs,
                                                   label_w - 10)) > 3:
                    lb_fs -= 1
                lb_fs = min(lb_fs, 10)
            elems.append(text(f"fr-lb{ri}", [x + 6, cur_y, label_w - 10, row_h],
                              label_text, font_size=lb_fs, color=c["primary"],
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
