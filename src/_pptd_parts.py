# -*- coding: utf-8 -*-
"""_pptd_gen 部件/资源子模块（T9 拆分自 _pptd_gen.py，2026-09-01）。
承载：页面构件发射（fill/emit/scale/snap）、资源解析、设计指南、文本估算、_deck_font。"""
import os
import re


from _renderer.elements import _esc
# 内容区下限单源在 _renderer.spacing.CONTENT_Y_MAX；此处保留私有别名
# _CONTENT_Y_MAX——_pptd_gen 经本模块 re-import，lint 侧直引 spacing，三方同值
# （S6 2026-09-07 从本文件上移到 spacing，切断 lint→_pptd_gen 私有 import 链）。
from _renderer.spacing import (CONTENT_Y_MAX as _CONTENT_Y_MAX,
                               GAP_LG, INSET_X, snap)
from _renderer.theme import DEFAULT_FONT

def _deck_font(theme):
    """甲板统一字体：textStyles.bodytext 的 fontFamily（theme dict 单一源）。"""
    return theme["textStyles"]["bodytext"].get("fontFamily", DEFAULT_FONT)



_CONTENT_X = 80
_CONTENT_W = 1120

# cards/phases/pullquote 左侧强调竖条宽（px，照 v3）。竖条是容器 inset 区内
# 的装饰，条内文本框 x 偏移直接取 INSET_X（间距体系 v1：替代原 +22/+18 魔法数）
_BAR_W = 5

# 内容区下限单源在 _renderer.spacing.CONTENT_Y_MAX（见文件头部 import，
# 私有别名 _CONTENT_Y_MAX 为 _pptd_gen re-import 面保留）。

# 第二级 自动适配触发线（§七 2.5）：y 游标过线后正文类元素缩排。
# 取值 560 ≈ 内容区（130-674 共 544px）八成，给 shrink 档留出一排卡片的
# 收缩余量；基线 9 个溢出页实测见 docs/ 重构记录
_CONTENT_Y_SHRINK = 560

# shrink 档（单档，抄 Beautiful.ai Smart Slides 思路：先缩字号/压行距自适应，
# 仍超高才截断）：正文类 fontSize 14 -> 12，bullets 行距 1.65 -> 1.4
_SHRINK_BODY_SIZE = 12
_SHRINK_BODY_LINE_HEIGHT = 1.4

# pullquote 引文 shrink 档（§七 2.8 底边感知同款：缩字号 2px，18 -> 16；
# 署名 12pt 已到 small 档不再压）
_PULLQUOTE_QUOTE_SIZE = 18
_SHRINK_QUOTE_SIZE = 16

# cards/phases 整组 skip 阈值（§七 2.8 d）：可用高度不足一行卡正文
#（cardbody/desc 13pt × 1.55 行距 ≈ 20.2px）时不发压碎碎片，整组 skip
_CARD_LINE_H = 13 * 1.55

# 页级填充（版式改进：内容自适应填充可用区域）。可用区 = y 130（内容区顶，
# 即 y 游标起点）到页脚 y=690，共 560px
_FILL_Y_ANCHOR = 130.0
_FILL_AVAILABLE = 560.0
# 目标填充率：内容底边达到 130 + 0.88×560 ≈ 623；触发阈值：当前填充 < 75%
# （底边 < 550）。只向上填充、不向下压缩——内容超高仍走 shrink/裁剪防线
_FILL_TARGET_RATIO = 0.88
_FILL_TRIGGER_RATIO = 0.75
# 纵向拉伸倍率上限（视觉抽查口径：4 倍以上卡片过高过空显假）。目标 88%
# 达不到时停在 2 倍，接受留白
_FILL_MAX_SCALE = 2.0
# diagram 组均匀放大倍率上限（防卡通化：形状随盒子变大但字号不变，倍率过
# 大显空）
_FILL_DG_MAX_SCALE = 1.6
# 三件套不参与填充（页眉 logo / 页标题 / 页脚）
_FILL_EXCLUDE_IDS = frozenset({"header-logo", "title", "footer-left", "footer-right"})
# diagram 组 elementId 前缀（render_diagram_pptd 唯一化为 dg{int(y)}-*，同页
# 多图按此前缀分组）
_DG_GROUP_ID_RE = re.compile(r"^(dg\d+)-")


def _fill_content_area(elements):
    """页级填充 pass：内容底边不足可用区 75% 时，纵向放大到底边 ~88%。

    所有内容元素 emit 完成后、页脚追加前调用，就地改写内容元素 bounds
    （排除三件套）：
    - 非 diagram 元素：以 y=130 为锚纵向拉伸（y' = 130+(y-130)×s，h' = h×s），
      x/w 不变，s 上限 _FILL_MAX_SCALE（目标 88% 达不到就停在限速，接受
      留白）。加高盒子/卡片/形状无失真；fontSize 不变（安全阀）——文字
      顶锚不变，文本框变高只是底部留白，无溢出风险。同组元素（cards 一组、
      phases 一组、table、pullquote）相对位置保持：所有元素同锚同倍率，
      组内间距同比放大。
    - diagram 组（dg\\d+- 前缀）：纵向拉伸会压扁圆形/菱形等比例形状
      （ellipse 变椭圆），改做均匀缩放（x/y/w/h 同乘 s_dg，宽高比不变），
      s_dg = min(s, _CONTENT_W/组宽, 1.6)；组顶 y 随 s 重排（保持与上文
      元素的纵向顺序/间距同比），缩放后水平居中于内容区。全宽 diagram
      放大受宽度约束，可能达不到 88% 目标——接受的折中（不压扁形状优先）。
    只向上填充（内容不足才触发）；饱满页（填充 ≥75%）零改动。
    非幂等：限速（_FILL_MAX_SCALE / _FILL_DG_MAX_SCALE）下目标 88% 达不到时
    停在限速，多次调用会在限速内继续逼近目标——当前链路保证每页只调一次
    （_build_content_page 内、页脚追加前），幂等性不影响产出。
    """
    content = [e for e in elements
               if str(e.get("elementId")) not in _FILL_EXCLUDE_IDS
               and not str(e.get("elementId", "")).startswith("ph-")
               and isinstance(e.get("bounds"), list) and len(e["bounds"]) == 4]
    if not content:
        return
    bottom = max(float(e["bounds"][1]) + float(e["bounds"][3]) for e in content)
    content_h = bottom - _FILL_Y_ANCHOR
    if content_h <= 0 or content_h >= _FILL_TRIGGER_RATIO * _FILL_AVAILABLE:
        return
    s = min(_FILL_TARGET_RATIO * _FILL_AVAILABLE / content_h, _FILL_MAX_SCALE)

    dg_groups = {}
    for e in content:
        m = _DG_GROUP_ID_RE.match(str(e.get("elementId", "")))
        if m:
            dg_groups.setdefault(m.group(1), []).append(e)
        else:
            # 纵向拉伸：x/w 原样保留，只改写 y/h
            b = e["bounds"]
            b[1] = _fill_num(_FILL_Y_ANCHOR + (float(b[1]) - _FILL_Y_ANCHOR) * s)
            b[3] = _fill_num(float(b[3]) * s)

    for group in dg_groups.values():
        _fill_diagram_group(group, s)


def _fill_diagram_group(group, page_s):
    """diagram 组填充：组顶 y 随 page_s 同比下移，组内按 s_dg 均匀缩放并水平居中。

    s_dg 受宽度约束（组宽 × s_dg ≤ _CONTENT_W）与 _FILL_DG_MAX_SCALE 上限；
    只放大不缩小（s_dg ≥ 1）。全宽 diagram 独占页时 s_dg=1 且位置不变——
    零改动返回。
    """
    gx0 = min(float(e["bounds"][0]) for e in group)
    gw = max(float(e["bounds"][0]) + float(e["bounds"][2]) for e in group) - gx0
    gy0 = min(float(e["bounds"][1]) for e in group)
    width_cap = (_CONTENT_W / gw) if gw > 0 else page_s
    s = max(1.0, min(page_s, _FILL_DG_MAX_SCALE, width_cap))
    new_gx0 = _CONTENT_X + (_CONTENT_W - gw * s) / 2
    new_gy0 = _FILL_Y_ANCHOR + (gy0 - _FILL_Y_ANCHOR) * page_s
    if s == 1.0 and abs(new_gx0 - gx0) < 0.01 and abs(new_gy0 - gy0) < 0.01:
        return
    _scale_group_bounds(group, s, new_gx0, new_gy0)


def _shrink_diagram_to_fit(dg_elems, dg_h, x, y, total_w, report, page_id, index):
    """I-16：超高 diagram 组均匀缩小压回 _CONTENT_Y_MAX 界内。

    返回 (elems, 新高度)；缩到 0.5 仍超可用高度则整图 skip 进 report
    （复用拆页口径），返回 (None, 0)，调用方不 emit、不推进 y 游标。
    字号随盒子同比缩小（下限 8px）：缩盒不缩字会触发 lint text_overflow。
    缩放后底边恰贴 _CONTENT_Y_MAX（lint 对该线元素豁免 text_overflow，§七 2.8 a）。
    """
    s = (_CONTENT_Y_MAX - y) / dg_h if dg_h > 0 else 1.0
    if s < 0.5:
        report.skip(page_id, index, "diagram",
                    "可用空间不足，diagram 缩至 0.5 仍超高，内容超量请拆页")
        return None, 0
    report.warn(f"{page_id} dg{int(y)}: diagram 均匀缩小 {s:.2f} 防溢出")
    gx0 = min(float(e["bounds"][0]) for e in dg_elems)
    gw = max(float(e["bounds"][0]) + float(e["bounds"][2]) for e in dg_elems) - gx0
    new_gx0 = x + max(0.0, (total_w - gw * s) / 2)  # 缩小后水平居中
    _scale_group_bounds(dg_elems, s, new_gx0, float(y), scale_font=True)
    return dg_elems, dg_h * s


def _scale_group_bounds(group, s, new_gx0, new_gy0, scale_font=False):
    """dg 组均匀缩放：组 bbox 左上对齐到 (new_gx0, new_gy0)，x/y/w/h 同乘 s。

    scale_font=True 时 content.fontSize 同乘 s（下限 8px）——仅 I-16 缩盒
    防溢出用；填充 pass 不动字号（安全阀：文字顶锚不变，只撑盒子）。
    group 元素（elementType=group）的子元素 children 同步缩放，保持
    角标/框体/标题相对关系不变。
    """
    gx0 = min(float(e["bounds"][0]) for e in group)
    gy0 = min(float(e["bounds"][1]) for e in group)
    for e in group:
        _scale_element_bounds(e, s, gx0, gy0, new_gx0, new_gy0, scale_font)


def _scale_element_bounds(e, s, gx0, gy0, new_gx0, new_gy0, scale_font):
    """单元素 bounds 等比缩放，并递归处理 group 的 children。"""
    ex, ey, ew, eh = (float(v) for v in e["bounds"])
    e["bounds"] = [_fill_num(new_gx0 + (ex - gx0) * s),
                   _fill_num(new_gy0 + (ey - gy0) * s),
                   _fill_num(ew * s), _fill_num(eh * s)]
    if scale_font:
        content = e.get("content")
        if isinstance(content, dict) and content.get("fontSize") is not None:
            try:
                content["fontSize"] = max(8, round(float(content["fontSize"]) * s, 1))
            except (TypeError, ValueError):
                pass
    for child in e.get("children") or []:
        _scale_element_bounds(child, s, gx0, gy0, new_gx0, new_gy0, scale_font)


def _fill_num(v):
    """bounds 数值紧凑化：保留 2 位小数，整数值写回 int（yaml 输出整洁）。"""
    r = round(v, 2)
    return int(r) if r == int(r) else r


def _snap_page_elements(elements):
    """页出口坐标吸附（间距体系 v1 §3.3）：整页元素 bounds 统一过 spacing.snap。

    集中在页构建出口做一次（不在各 emit 点散落）。四角吸附（x1/y1/x2/y2 各自
    snap 后反推 w/h）：snap 单调，组内共享边与互不相交关系保持，宽高兜底 1
    （connector 近零厚度 bbox）。吸附前底边恰贴 _CONTENT_Y_MAX 的元素保边不
    吸附——那是溢出防线裁剪产物，lint 对该线豁免 text_overflow（§七 2.8 a），
    防线语义不被网格破坏。
    """
    for e in elements:
        _snap_element(e)


def _snap_element(e):
    """单元素四角吸附 + 递归处理 group 的 children。"""
    b = e.get("bounds")
    if isinstance(b, list) and len(b) == 4:
        try:
            x, y, w, h = (float(v) for v in b)
        except (TypeError, ValueError):
            x = y = w = h = 0.0
        x1, y1 = snap(x), snap(y)
        x2 = snap(x + w)
        if abs(y + h - _CONTENT_Y_MAX) <= 0.01:
            y2 = _CONTENT_Y_MAX  # 防线裁剪线保边（见 docstring）
        else:
            y2 = snap(y + h)
        e["bounds"] = [x1, y1, max(x2 - x1, 1), max(y2 - y1, 1)]
    for child in e.get("children") or []:
        _snap_element(child)


def _clamp_bottom(page_id, element_id, y, h, report, font_size=14):
    """底边兜底（§七 2.8 裁决 a+d 组合）：y+h 超 _CONTENT_Y_MAX 时分三档。

    - 未超线：原样返回 h
    - 可用高度不足一行（< fontSize × 1.3，fontSize 取元素实际生效字号）：
      返回 None——一行都显示不出的裁剪碎片无意义，调用方整元素
      report.skip("可用空间不足一行，内容超量请拆页")。注意 P1-D 语义
      skipped→verify FAIL：页面真实超量时逼用户拆页，是预期不是 bug
    - 其余：裁剪到可用空间 + report.warn（不丢内容，PPT 文本框自然截断；
      lint 对底边贴线元素豁免 text_overflow，见 _layout_lint）
    只有元素起点超线的才整元素 skip（_build_content_page 第三级硬防线）。
    """
    if y + h <= _CONTENT_Y_MAX:
        return h
    available = _CONTENT_Y_MAX - y
    if available < font_size * 1.3:
        return None
    report.warn(f"{page_id} {element_id}: 高度裁切防溢出")
    return max(0.0, available)


def _emit_cards(elements, cards, x, y, total_w, max_h=None, report=None, page_id=None,
                index=None):
    """cards：每卡 roundRect + 5px 竖条 + 标题 + body，横排均分。

    版式照 v3（07_p06_l1.page card-1/card-2）：
    - roundRect adjustments [8000] fill $card
    - 左侧 5px rect fill $primary（y 偏移 +18，高度 -36）
    - 标题 $cardtitle + <strong>
    - body $cardbody
    n 卡横排均分 total_w，卡间距 GAP_LG(24，间距令牌 §3.1)。
    elementId 带 y 坐标前缀（card-{int(y)}-{i}，§七 2.4，同 diagram 的
    dg{y}- 方案），保证同页多组 cards 不撞 ID。
    max_h 非空时整组高度裁到 max_h + report.warn（底边防线 §七 2.8）；
    max_h 不足一行卡正文（_CARD_LINE_H）时不 emit 压碎碎片，整组
    report.skip 并返回 (0, 0)（§七 2.8 d，同 text 类口径）。
    返回 (总高度, 卡数)。高度估算：标题 24 + body 4 行 ≈ 96 + padding。
    """
    uid = int(y)
    n = len(cards)
    if n == 0:
        return 0, 0
    gap = GAP_LG
    card_w = (total_w - gap * (n - 1)) / n
    # 文本框内边距折算（间距体系 v1 一层：方言无 insets 字段，折算进 bounds）：
    # x = 卡边 + INSET_X，宽 = 卡宽 - 2×INSET_X（替代 +22/-40 魔法数；
    # 竖条是 inset 区内的装饰，不再计入偏移）
    text_x_off = INSET_X
    text_w = max(card_w - 2 * INSET_X, 1)
    # 估算高度：标题 + body 行数
    max_body_h = 0
    for c in cards:
        body = str(c.get("body", ""))
        bh = _estimate_text_height(body, font_size=13, line_height=1.55, width=text_w)
        max_body_h = max(max_body_h, bh)
    card_h = 24 + 12 + max_body_h + 16  # padding-top + 标题 + 间距 + body + padding-bottom
    card_h = max(card_h, 100)  # 最小高度
    if max_h is not None and card_h > max_h:
        if max_h < _CARD_LINE_H:
            # 可用空间不足一行：不 emit 压碎碎片，整组 skip（§七 2.8 d）
            if report is not None:
                report.skip(page_id, index, "cards", "可用空间不足一行，内容超量请拆页")
            return 0, 0
        card_h = max(max_h, 0.0)
        if report is not None:
            report.warn(f"{page_id} card-{uid}: 高度裁切防溢出")

    for i, card in enumerate(cards):
        cx = x + i * (card_w + gap)
        title = str(card.get("title", ""))
        body = str(card.get("body", ""))
        elements.append({
            "elementId": f"card-{uid}-{i + 1}",
            "elementType": "shape",
            "bounds": [cx, y, card_w, card_h],
            "shapeName": "roundRect",
            "adjustments": [8000],
            "fill": {"type": "solid", "color": "$card"},
        })
        # 左侧竖条（y 偏移 +18，高度 -36，照 v3）
        bar_y = y + 18
        bar_h = max(card_h - 36, 8)
        elements.append({
            "elementId": f"card-{uid}-{i + 1}-bar",
            "elementType": "shape",
            "bounds": [cx, bar_y, _BAR_W, bar_h],
            "shapeName": "rect",
            "fill": {"type": "solid", "color": "$primary"},
        })
        # 标题
        elements.append({
            "elementId": f"card-{uid}-{i + 1}-title",
            "elementType": "text",
            "bounds": [cx + text_x_off, y + 10, text_w, 24],
            "content": {
                "style": "$cardtitle",
                "align": ["left", "middle"],
                "wrap": False,
                "text": f"<p><strong>{_esc(title)}</strong></p>\n",
            },
        })
        # body
        body_h = max(card_h - 24 - 16, 8)
        elements.append({
            "elementId": f"card-{uid}-{i + 1}-body",
            "elementType": "text",
            "bounds": [cx + text_x_off, y + 38, text_w, body_h],
            "content": {
                "style": "$cardbody",
                "align": ["left", "top"],
                "text": _esc(body.rstrip("\n")) + "\n",
            },
        })
    return card_h, n


def _emit_table(elements, headers, rows, x, y, total_w):
    """table：整体 bounds + 均分 columnWidths/行高 hug rowHeights + {content:} + style "$default"。

    方言陷阱 5：单元格 {content: {text: ...}} 对象，禁裸字符串。
    方言陷阱 6：style "$default" 引用主题 tableStyles.default。
    首行表头：headerFill 由主题样式负责（headerBold/headerColor），单元格只写 text。
    其余行首列：加 <strong> + color $navy（照 v3 07_p06_l1.page dims-table）。
    行高走 table_hug_geometry（间距体系 v1 §五）：短内容与旧均分公式一致，
    长文本单元格撑高所在行。
    返回表总高度。
    """
    n_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    if n_cols == 0:
        return 0
    len(rows) + (1 if headers else 0)

    # 均分列宽比例（和为 1）
    col_w = 1.0 / n_cols
    column_widths = [col_w] * n_cols

    # 行高 hug（间距体系 v1 §五，与 6 个 diagram 表格 subtype 同口径）：
    # 行高 = 行内单元格最大行数 × 行距 + 2×INSET_Y，下限原写死公式
    #（n×36 + 表头 0.1/其余均分；短内容与原输出逐字节一致，长文本单元格
    # 撑高不再静默裁剪）。撑高超页不在此截断，走调用方页底防线
    #（_clamp_bottom 裁切 + warn / 不足一行 skip）。
    from _renderer.diagram.pptd_emit import table_hug_geometry
    plain_rows = []
    if headers:
        plain_rows.append([str(h) for h in headers])
    for row in rows:
        plain_rows.append([str(c) for c in row])
    table_h, row_heights = table_hug_geometry(plain_rows, column_widths, total_w, 36, 0.1)

    # 构造 rows（方言陷阱 5：{content: {text: ...}}）
    emit_rows = []
    if headers:
        header_row = [{"content": {"text": _esc(str(h))}} for h in headers]
        emit_rows.append(header_row)
    for row in rows:
        cells = []
        for j, cell in enumerate(row):
            text = str(cell)
            if j == 0 and headers:
                # 首列加粗变色（照 v3）
                cells.append({
                    "content": {
                        "color": "$navy",
                        "text": f"<p><strong>{_esc(text)}</strong></p>\n",
                    }
                })
            else:
                cells.append({
                    "content": {
                        "align": ["left", "middle"],
                        "text": _esc(text),
                    }
                })
        emit_rows.append(cells)

    elements.append({
        "elementId": f"table-{int(y)}",
        "elementType": "table",
        "bounds": [x, y, total_w, table_h],
        "columnWidths": column_widths,
        "rowHeights": row_heights,
        "style": "$default",
        "rows": emit_rows,
    })
    return table_h


def _emit_phases(elements, phases, x, y, total_w, max_h=None, report=None, page_id=None,
                 index=None):
    """phases：每阶段 Shape + name(<strong>) + desc 横排（同 cards 布局）。

    spec 字段：phases[].name / phases[].desc（v3 实例确认，非 label/goal）。
    简化横排版（开发计划 §5 口径），v3 纵向时间轴是特殊页做法，归分页代理。
    elementId 带 y 坐标前缀（phase-{int(y)}-{i}，§七 2.4，同 cards）。
    高度自适应（§七 2.8，替代原固定 110——7 列窄卡时 desc 放不下，lint 实测
    溢出）：name 区 24 + desc 按文本框宽（卡宽 - 2×INSET_X，间距体系 v1
    内边距折算）用 est_text_w 估行数 × 行高（13px × 1.55，cardbody 样式）
    + padding，min 110。
    max_h 非空时整组高度裁到 max_h + report.warn（底边防线 §七 2.8）；
    max_h 不足一行 desc（_CARD_LINE_H）时不 emit 压碎碎片，整组
    report.skip 并返回 0（§七 2.8 d，同 text 类口径）。
    返回总高度。
    """
    n = len(phases)
    if n == 0:
        return 0
    uid = int(y)
    gap = GAP_LG
    phase_w = (total_w - gap * (n - 1)) / n
    from _renderer.diagram.pptd_emit import est_text_w  # 全角/半角区分，比全按全角准
    # 文本框内边距折算（同 cards）：x = 卡边 + INSET_X，宽 = 卡宽 - 2×INSET_X
    text_x_off = INSET_X
    desc_w = max(phase_w - 2 * INSET_X, 1)
    max_desc_h = 0.0
    for phase in phases:
        desc = str(phase.get("desc", ""))
        if not desc:
            continue
        lines = max(1, int(-(-est_text_w(desc, 13) // desc_w)))
        max_desc_h = max(max_desc_h, lines * 13 * 1.55)
    # padding-top + name + 间距 + desc + padding-bottom（公式同 cards），min 110
    phase_h = max(24 + 12 + max_desc_h + 16, 110)
    if max_h is not None and phase_h > max_h:
        if max_h < _CARD_LINE_H:
            # 可用空间不足一行：不 emit 压碎碎片，整组 skip（§七 2.8 d）
            if report is not None:
                report.skip(page_id, index, "phases", "可用空间不足一行，内容超量请拆页")
            return 0
        phase_h = max(max_h, 0.0)
        if report is not None:
            report.warn(f"{page_id} phase-{uid}: 高度裁切防溢出")

    for i, phase in enumerate(phases):
        px = x + i * (phase_w + gap)
        name = str(phase.get("name", ""))
        desc = str(phase.get("desc", ""))
        # 卡片底
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}",
            "elementType": "shape",
            "bounds": [px, y, phase_w, phase_h],
            "shapeName": "roundRect",
            "adjustments": [8000],
            "fill": {"type": "solid", "color": "$card"},
        })
        # 左侧竖条
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}-bar",
            "elementType": "shape",
            "bounds": [px, y + 18, _BAR_W, max(phase_h - 36, 8)],
            "shapeName": "rect",
            "fill": {"type": "solid", "color": "$primary"},
        })
        # name（accent 色 <strong>）
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}-name",
            "elementType": "text",
            "bounds": [px + text_x_off, y + 10, desc_w, 24],
            "content": {
                "style": "$cardtitle",
                "align": ["left", "middle"],
                "wrap": False,
                "text": f"<p><strong>{_esc(name)}</strong></p>\n",
            },
        })
        # desc
        desc_h = max(phase_h - 24 - 16, 8)
        elements.append({
            "elementId": f"phase-{uid}-{i + 1}-desc",
            "elementType": "text",
            "bounds": [px + text_x_off, y + 38, desc_w, desc_h],
            "content": {
                "style": "$cardbody",
                "align": ["left", "top"],
                "text": _esc(desc.rstrip("\n")) + "\n",
            },
        })
    return phase_h


def _estimate_pullquote_height(quote, cite, quote_size, text_w):
    """pullquote 总高估算（与 _emit_pullquote 版式公式同口径）：
    引文 quote_size pt × 1.4 行距 × 行数 + 署名 20 + padding 16。"""
    quote_h = _estimate_text_height(quote, font_size=quote_size, line_height=1.4,
                                    width=text_w)
    return quote_h + (20 if cite else 0) + 16


def _emit_pullquote(elements, quote, cite, x, y, total_w, font=DEFAULT_FONT,
                    quote_size=_PULLQUOTE_QUOTE_SIZE, max_h=None, report=None,
                    page_id=None):
    """pullquote：左侧 5px $primary 竖条 + 引文 18pt $navy + 署名 12pt $gray。

    版式照 v3 DESIGN_GUIDE「内嵌版」。font 默认 DEFAULT_FONT（调用方传
    甲板统一字体 _deck_font）。文本框 x = 左缘 + INSET_X、宽 = 总宽 - 2×INSET_X
    （间距体系 v1 内边距折算，替代 +18/-30 魔法数；竖条是 inset 区内装饰）。
    elementId 带 y 坐标前缀（pullquote-{int(y)}-*，同 cards 口径）。
    quote_size：引文字号（shrink 档 16，§七 2.8 底边感知升档）。max_h 非空且
    总高超限时整组裁到 max_h + report.warn：引文框吸收裁切量（PPT 文本框
    自然截断不丢内容）、署名沉底保持界内；署名连一行引文都放不下时只发
    引文（框撑满整组）。裁切后竖条底边贴防线裁剪线，lint 对组内文本框
    豁免 text_overflow（同组容器贴线，§七 2.8 a）。
    返回总高度。
    """
    uid = int(y)
    text_x = x + INSET_X
    text_w = total_w - 2 * INSET_X
    # 引文高度估算：quote_size pt × 行数
    quote_h = _estimate_text_height(quote, font_size=quote_size, line_height=1.4,
                                    width=text_w)
    cite_h = 20 if cite else 0
    total_h = quote_h + cite_h + 16
    if max_h is not None and total_h > max_h:
        # 底边防线（§七 2.8）：整组裁到 max_h；裁切 warn 由调用方
        # _clamp_bottom 记录（直调本函数时才在此 warn）
        total_h = max(max_h, 0.0)
        if cite_h and total_h - cite_h - 16 < quote_size * 1.4:
            cite_h = 0  # 署名随裁切舍弃，整组空间留给引文（至少保住一行）
            quote_h = total_h
        else:
            quote_h = total_h - cite_h - 16
        if report is not None:
            report.warn(f"{page_id} pullquote-{uid}: 高度裁切防溢出")

    # 左侧竖条
    elements.append({
        "elementId": f"pullquote-{uid}-bar",
        "elementType": "shape",
        "bounds": [x, y, _BAR_W, total_h],
        "shapeName": "rect",
        "fill": {"type": "solid", "color": "$primary"},
    })
    # 引文
    elements.append({
        "elementId": f"pullquote-{uid}-text",
        "elementType": "text",
        "bounds": [text_x, y, text_w, quote_h],
        "content": {
            "fontSize": quote_size,
            "color": "$navy",
            "fontFamily": font,
            "lineHeight": 1.4,
            "align": ["left", "top"],
            "text": _esc(quote.rstrip("\n")) + "\n",
        },
    })
    # 署名
    if cite_h:
        elements.append({
            "elementId": f"pullquote-{uid}-cite",
            "elementType": "text",
            "bounds": [text_x, y + quote_h + 8, text_w, cite_h],
            "content": {
                "fontSize": 12,
                "color": "$gray",
                "fontFamily": font,
                "align": ["left", "middle"],
                "wrap": False,
                "text": _esc(cite) + "\n",
            },
        })
    return total_h

def _resolve_logo(spec, spec_dir, logo_path, client_name=None):
    """logo 解析顺序（PRD Q6）：
    1. --logo 显式
    2. spec.document.cover.logo_image
    3. _knowledge/clients/{client}/refs/ 文件名含 logo 的图片
    4. output/{client}/*/media/ 文件名含 logo 的图片
    5. 跳过（返回 (None, None)，DESIGN_GUIDE 注明待补）

    返回 (源绝对路径, media 内文件名)。
    """
    # 1. 显式 --logo
    if logo_path and os.path.exists(logo_path):
        return os.path.abspath(logo_path), os.path.basename(logo_path)
    # 2. spec.document.cover.logo_image
    cover_logo = spec.get("document", {}).get("cover", {}).get("logo_image")
    if cover_logo:
        resolved = _resolve_relative_or_abs(cover_logo, spec_dir)
        if resolved and os.path.exists(resolved):
            return resolved, os.path.basename(resolved)
    # 3. refs/ 探测
    if client_name:
        found = _probe_logo_in_dir(os.path.join("_knowledge", "clients", client_name, "refs"))
        if found:
            return found
        # 4. output media/ 探测
        found = _probe_logo_in_output_media(client_name)
        if found:
            return found
    return None, None


def _probe_logo_in_dir(dir_path):
    """在目录下找文件名含 logo 的图片（png/jpg/jpeg/svg），返回 (abs_path, basename) 或 None。"""
    if not os.path.isdir(dir_path):
        return None
    logo_exts = (".png", ".jpg", ".jpeg", ".svg")
    for root, _, files in os.walk(dir_path):
        for fname in files:
            low = fname.lower()
            if "logo" in low and low.endswith(logo_exts):
                abs_p = os.path.abspath(os.path.join(root, fname))
                return abs_p, fname
    return None


def _probe_logo_in_output_media(client_name):
    """在 output/{client}/*/media/ 下找文件名含 logo 的图片。"""
    client_output = os.path.join("output", client_name)
    if not os.path.isdir(client_output):
        return None
    for entry in os.listdir(client_output):
        media_dir = os.path.join(client_output, entry, "media")
        found = _probe_logo_in_dir(media_dir)
        if found:
            return found
    return None


def _resolve_background_image(spec, spec_dir):
    """cover 背景图：spec.document.cover.background_image。没有返回 (None, None)。"""
    bg = spec.get("document", {}).get("cover", {}).get("background_image")
    if bg:
        resolved = _resolve_relative_or_abs(bg, spec_dir)
        if resolved and os.path.exists(resolved):
            return resolved, os.path.basename(resolved)
    return None, None


def _resolve_screenshot_path(src, spec_dir, client_name=None):
    """screenshot src 解析：refs/ → client refs/；_assets/ → 项目根；其余相对 spec_dir。

    返回存在的绝对路径或 None（调用方降级）。
    """
    if not src:
        return None
    src = str(src)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
    if src.startswith("refs/"):
        base = os.path.join(script_dir, "_knowledge", "clients",
                            client_name or "", "refs")
        candidate = os.path.join(base, src[5:])
    elif src.startswith("_assets/"):
        candidate = os.path.join(script_dir, src)
    elif src.startswith("assets/"):
        candidate = os.path.join(script_dir, "_" + src)
    elif os.path.isabs(src):
        candidate = src
    else:
        candidate = os.path.join(spec_dir, src)
    candidate = os.path.abspath(candidate)
    return candidate if os.path.exists(candidate) else None


def _emit_degrade_text(elements, x, y, total_w, text, report, page_id, index,
                       target_end, shrink=False, deck_font=None):
    """通用降级文本发射：按能力矩阵声明不支持时输出显式文本框并进 report.degraded。

    返回使用的总高度；空间不足时返回 0 并 skip。
    """
    from _renderer.spacing import estimate_text_height
    body_size = _SHRINK_BODY_SIZE if shrink else 14
    h = estimate_text_height(text, font_size=body_size, line_height=1.65,
                             width=total_w)
    eid = f"elem-{int(y)}"
    h = _clamp_bottom(page_id, eid, y, h, report, font_size=body_size)
    if h is None:
        report.skip(page_id, index, "degrade_text",
                    "可用空间不足一行，内容超量请拆页")
        return 0
    content = {"style": "$bodytext", "align": ["left", "top"],
               "text": text + "\n"}
    if shrink:
        content["fontSize"] = body_size
    if deck_font:
        content["fontFamily"] = deck_font
    elements.append({
        "elementId": eid,
        "elementType": "text",
        "bounds": [x, y, total_w, h],
        "content": content,
    })
    report.degrade(page_id, index, "degrade_text", target_end, text)
    return h


def _resolve_relative_or_abs(path, base_dir):
    """路径可能是绝对、相对 spec_dir、或相对 cwd；统一返回绝对路径。"""
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(base_dir, path))


def _media_abs_path(out_dir, media_name):
    """工程内 media 文件未来落盘后的绝对路径（方言陷阱 4）。"""
    return os.path.abspath(os.path.join(out_dir, "media", media_name))


# ---------------------------------------------------------------------------
# DESIGN_GUIDE.md 模板（P3）
# ---------------------------------------------------------------------------

def _build_design_guide(spec, theme, logo_abs, bg_abs, client_name, name, out_dir):
    """参数化 DESIGN_GUIDE.md（母版照 v3，参数换为客户/主题/logo/bg）。

    方言权威 pptd.md 路径失效，改为"方言规则见主 pptd + 本 GUIDE 六陷阱"。
    无 logo 时注明"待补 logo"。
    """
    colors = theme["colors"]
    primary = colors["primary"]
    navy = colors["navy"]
    deck_font = _deck_font(theme)
    doc = spec.get("document", {})
    title = doc.get("title", "")
    author = spec.get("author", client_name or "（待填客户名）")
    logo_note = logo_abs if logo_abs else "（待补 logo，页眉/封面 logo 元素未生成）"
    bg_note = bg_abs if bg_abs else "（待补封面背景图，cover 用纯色底）"

    return f"""# {title} - PPT 设计规范（子代理必读 · 执行口径）

> 由 pptd-gen 自动生成（{name}.pptd 配套）。母版照蓝海 v3 参数化。
> 写页面之前先读：
> 1. 方言六陷阱（见下，源 v3 实战 + 主 pptd 主题）
> 2. 内容源 spec.yml（L3 铁律：文案逐字取自 spec，只可视觉重排）
> 3. 示范页：pages/01_cover.page（封面）、pages/02_p01_*.page（标准内容页）
> 项目根：{out_dir}

## 方言六陷阱（踩过坑，务必遵守）

1. **主 pptd 顶层无 version 字段**。
2. **粗体只用行内 `<strong>`**；textStyles 无 bold 属性，写了不生效。
3. **斜体用 `<em>`**；中文斜体观感差，优先用粗细和颜色对比。
4. **图片 src 只认绝对路径**。media/ 素材引用写 `os.path.abspath`。
5. **表格单元格是 `{{content: {{...}}}}` 对象**，不是裸字符串。
6. **表格样式走 `headerFill` 系列 + `style: "$default"` 引用**。

另：**禁用 Icon 元素**（FA 图标 convert 时退化，v3 踩坑）。需要图形一律 Shape + Text。

## 主题与色板（来自主 pptd）

- 主色 primary：`{primary}`
- 深海军蓝 navy：`{navy}`
- 文字阶梯：ink `{colors["ink"]}` -> body `{colors["body"]}` -> lead `{colors["lead"]}` -> gray `{colors["gray"]}`
- 卡片底 card `{colors["card"]}`、浅蓝 chip `{colors["chip"]}`、分隔线 hairline `{colors["hairline"]}`
- 字体统一 {deck_font}（pagetitle 32 / lead 16 / bodytext 14 / small 12 / footer 11）
- 表格样式：headerFill `$navy` + headerColor 白 + headerBold true

## 画布与公共版式（1280×720）

- 内容页固定三件套（pptd-gen 已生成，仅改页码与标题；bounds 已按 4px 网格吸附）：
  - 页眉 logo：`bounds: [24, 28, 48, 40]`，`fit: {{mode: contain}}`
  - 页标题：`bounds: [80, 56, 1120, 44]`，`style: "$pagetitle"`，`wrap: false`，整体 `<strong>` 包裹
  - 页脚左：`bounds: [80, 688, 400, 16]`，`style: "$footer"`，`© 2026 – {author}`
  - 页脚右：`bounds: [1056, 688, 144, 16]`，`style: "$footer"`，`Page - N`
- 正文区：x 80–1200（宽 1120，左右各 80 对称边距），y 130–674
- 卡片：roundRect `adjustments: [8000]` fill `$card` + 左侧 5px `$primary` 竖条 + `$cardtitle`+`<strong>` + `$cardbody`
- pullquote：左侧 5px `$primary` 竖条 + 引文 18pt `$navy` + 署名 12pt `$gray`

## 媒体清单

- logo：{logo_note}
- 封面背景：{bg_note}

## 自检流程

1. 改完负责的 .page 文件后，复制主 pptd 为 `_check_批次.pptd`，pages 列表改成你的批次。
2. 跑 `python _cli.py pptd-build _check_批次.pptd --check-only --client {client_name or "客户名"}`。
3. 修到 0 errors, 0 warnings（TextOverflow/TextUnderfill/TextOcclusion 全修）。
4. 不要跑 convert（统一由 pptd-build 主流程做）。
5. 汇报：每页一行版式说明 + check 最终 Summary。
"""


# ---------------------------------------------------------------------------
# y 游标估算
# ---------------------------------------------------------------------------

def _estimate_text_height(text, font_size=14, line_height=1.65, width=_CONTENT_W):
    """估算文本块高度（px）——薄委托，统一入口在
    _renderer.spacing.estimate_text_height（S6 2026-09-07 单源，lint/生成器
    同源；行距显式参数，此处默认 1.65 为正文口径）。
    """
    from _renderer.spacing import estimate_text_height
    return estimate_text_height(text, font_size, line_height, width)


def _estimate_bullets_height(items, font_size=14, line_height=1.65, width=_CONTENT_W):
    """bullets 高度：每条按 text 估算 + 条间距。"""
    if not items:
        return font_size * line_height
    total = 0
    for it in items:
        total += _estimate_text_height(str(it), font_size, line_height, width)
        total += font_size * 0.5  # 段间距
    return total


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _opacity_to_hex(opacity):
    """不透明度 0.0-1.0 -> 两位十六进制（00-FF）。0.8 -> 'CC'。"""
    v = max(0, min(1, float(opacity)))
    return f"{int(round(v * 255)):02X}"


def _page_slug(page_spec, idx):
    """从 page.id 推 slug；没 id 用 p{NN}。连字符转下划线。"""
    pid = page_spec.get("id") or f"p{idx + 1:02d}"
    return pid.replace("-", "_")


def _slugify_name(name):
    """项目名清洗：保留中文/字母/数字/下划线，其余转下划线。"""
    if not name:
        return "deck"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name, flags=re.UNICODE)
    cleaned = cleaned.strip("_")
    return cleaned or "deck"