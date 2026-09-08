# -*- coding: utf-8 -*-
"""v2/v3 页面构件 pptd 发射器（S8-B 棘轮拆小：自 pptd_emit.py 迁出）。

动因：pptd_emit 1826 行 > 基线 cap 1606（只许拆小不许加码；b722f01
_spec_hex 先例）。本模块承载 hero→logo_wall（含 C-E2 三件套/C-E3 duo
语义）的原生形状映射；批次 B/ui_mock/conclusion_band 在 pptd_emit_ext；
diagram 族发射器仍留 pptd_emit。
import 面不变：pptd_emit 经模块 __getattr__ 懒加载转发本模块全部名字，
`from _renderer.diagram.pptd_emit import emit_chrome_pptd` 等既有消费零改动。
"""
import math
import os

from .. import theme
from ..spacing import GAP_SM, INSET_X, est_text_w
from .pptd_emit import (
    _line, _snap_bounds, _v2c, shape, stack_text_h, text, wrap_lines,
)



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
    if not n["cards"]:
        return [], 0  # 空守卫：否则 n_cards=0 均分宽除零（对齐 toc_cards 早退）
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
    if not n["cards"]:
        return [], 0  # 空守卫：否则 n_cards=0 均分宽除零（对齐 toc_cards 早退）
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
    if not cards:
        return [], 0  # 空守卫：否则 n_cols=0 均分宽除零 + range 步长 0（对齐 toc_cards）
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
    """qa_block：左竖条 + Q 粗体 + A 段落（C-E4 官方绿语义槽取色）。"""
    elems = []
    cur_y = float(y)
    for i, it in enumerate(n["items"]):
        q_h = stack_text_h(len(wrap_lines(it["q"], 13, w - 2 * INSET_X - 20)), 13)
        a_h = stack_text_h(len(wrap_lines(it["a"], 12, w - 2 * INSET_X - 20)),
                           12) if it["a"] else 0
        item_h = 10 + q_h + (4 + a_h if it["a"] else 0) + 10
        elems.append(shape(f"qa-bg{i}", [x, cur_y, w, item_h], "roundRect",
                           fill=c["qa_bg"], adjustments=[6000]))
        elems.append(shape(f"qa-bar{i}", [x, cur_y, 3, item_h], "rect",
                           fill=c["qa_text"]))
        elems.append(text(f"qa-q{i}", [x + 10, cur_y + 8, w - 20, q_h],
                          it["q"], font_size=13, color=c["qa_text"],
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
    >4 卡时对齐 HTML 端 .view-grid（repeat(4,1fr)）每行 4 张折行，卡宽仍按 4 列栅格计。
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
    # 4 列卡片：y 从 cap_h 下方留 12px 间隙放；>4 卡按每行 4 张折行
    # （对齐 HTML 端 .view-grid 换行语义），行距复用列距 gap，总高按行数累计
    card_top = y + cap_h + 12
    card_h = 132.0
    n_rows = max(1, math.ceil(len(cards) / 4))
    for i, card in enumerate(cards):
        row, col = divmod(i, 4)
        cx = x + col * (cw + gap)
        top = card_top + row * (card_h + gap)
        # 卡底
        elems.append(shape(f"vc-{i}", [cx, top, cw, card_h], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        # icon 圆（48x48 居中）
        ic = str(card.get("icon", "◆")) or "◆"
        elems.append(shape(f"vc-{i}-icon", [cx + (cw - 36) / 2, top + 12,
                                            36, 36], "ellipse",
                           fill=c["bg_soft"]))
        elems.append(_line(f"vc-{i}-it", [cx + (cw - 36) / 2, top + 12,
                                          36, 36], ic, font_size=16,
                          color=c["primary"], bold=True,
                          align=("center", "middle")))
        # 视角名
        elems.append(_line(f"vc-{i}-p", [cx + 8, top + 52, cw - 16, 18],
                          card["perspective"], font_size=14,
                          color=c["text_primary"], bold=True,
                          align=("center", "middle")))
        # 关键数字 headline
        hl = card.get("headline", "")
        if hl:
            elems.append(_line(f"vc-{i}-hl", [cx + 8, top + 70, cw - 16, 18],
                              hl, font_size=16, color=c["accent"],
                              bold=True, align=("center", "middle")))
        # detail 说明（卡高 132 后底部留 40px 两行区，对齐 HTML 端信息密度；
        # 多行必须 text(wrap=True)，_line 单行会横向溢出邻卡）
        detail = card.get("detail", "")
        if detail:
            elems.append(text(f"vc-{i}-d", [cx + 12, top + 92, cw - 24, 34],
                              detail, font_size=10,
                              color=c["text_secondary"],
                              align=("center", "top")))
    total_h = cap_h + 12 + n_rows * card_h + (n_rows - 1) * gap
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
    """duo_compare：左右双面板 + 1px 中隔线，P14。

    C-E3 语义强化（向后兼容）：side.tone=before 灰/after 主色（after 侧
    加 3px 主色竖条）；metrics 量化对比行随双栏下方出对照表（after 列主色）。
    """
    gap = 16.0
    pw = (w - gap * 2) / 2
    elems = []
    # tone 取色：before 灰 / after 主色 / 无 tone 走原中性
    title_color, body_color = {}, {}
    for key in ("left", "right"):
        tone = n[key].get("tone") or ""
        if tone == "before":
            title_color[key] = c["text_tertiary"]
            body_color[key] = c["text_tertiary"]
        elif tone == "after":
            title_color[key] = c["primary"]
            body_color[key] = c["text_primary"]
        else:
            title_color[key] = c["text_primary"]
            body_color[key] = c["text_secondary"]
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
        if n[key].get("tone") == "after":
            elems.append(shape(f"duo-bar{pi}", [px, y, 3, max_h], "rect",
                               fill=c["primary"]))
            px += 9
        elems.append(_line(f"duo-t{pi}", [px, y, pw, 22], side["title"],
                           font_size=14, color=title_color[key], bold=True,
                           align=("left", "top")))
        if side["points"]:
            body = "\n".join("• " + p for p in side["points"])
            elems.append(text(f"duo-b{pi}", [px, y + 26, pw, max(max_h - 30, 12)],
                              body, font_size=12, color=body_color[key],
                              align=("left", "top")))
    elems.append(shape("duo-vr", [x + pw + gap, y, 1.5, max_h], "rect",
                       fill=c["border"]))
    total_h = max_h
    # C-E3 量化对比行：表头（空 | 左标题 | 右标题）+ 指标行（after 列主色）
    metrics = n.get("metrics") or []
    if metrics:
        col_label = w * 0.34
        col_val = (w - col_label) / 2
        ty = y + total_h + 12
        head_h = 22.0
        row_h = 22.0
        elems.append(_line("duo-m-hl", [x, ty, col_label, head_h], "",
                           font_size=11, color=c["text_secondary"]))
        elems.append(_line("duo-m-hleft", [x + col_label, ty, col_val, head_h],
                           n["left"]["title"], font_size=12,
                           color=c["text_secondary"]))
        elems.append(_line("duo-m-hright",
                           [x + col_label + col_val, ty, col_val, head_h],
                           n["right"]["title"], font_size=12,
                           color=c["primary"], bold=True))
        elems.append(shape("duo-m-hr", [x, ty + head_h, w, 1.2], "rect",
                           fill=c["border"]))
        for mi, m in enumerate(metrics):
            ry = ty + head_h + 2 + mi * row_h
            if mi % 2 == 0:
                elems.append(shape(f"duo-m-bg{mi}", [x, ry, w, row_h], "rect",
                                   fill=c["bg_soft"]))
            elems.append(_line(f"duo-m-l{mi}", [x, ry, col_label, row_h],
                               m["label"], font_size=11,
                               color=c["text_primary"], bold=True,
                               align=("left", "middle")))
            elems.append(_line(f"duo-m-vl{mi}",
                               [x + col_label, ry, col_val, row_h],
                               m["left"], font_size=12,
                               color=c["text_secondary"],
                               align=("left", "middle")))
            elems.append(_line(f"duo-m-vr{mi}",
                               [x + col_label + col_val, ry, col_val, row_h],
                               m["right"], font_size=12,
                               color=c["primary"], bold=True,
                               align=("left", "middle")))
        total_h += 12 + head_h + 2 + len(metrics) * row_h
    return elems, total_h


def _image_el(eid, bounds, src):
    """chrome 构件内嵌图片（logo/头像）：fit contain，调用方保证 src 存在。"""
    return {
        "elementId": eid,
        "elementType": "image",
        "bounds": _snap_bounds(*bounds),
        "src": src,
        "fit": {"mode": "contain"},
    }


def emit_sla_block_pptd(n, x, y, w, c):
    """sla_block：SLA 承诺卡网格（C-E2）：指标名 + 承诺值大字主色 + 说明。

    ≤4 张一行，>4 折行（同 view_cards 每行 4 列语义）；顶条 3px 主色。
    """
    items = n["items"]
    elems = []
    cur_y = float(y)
    title = n.get("title")
    if title:
        elems.append(_line("sla-t", [x, cur_y, w, 22], title, font_size=14,
                           color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        cur_y += 28
    gap = 12.0
    n_cols = max(1, min(len(items), 4))
    for i, it in enumerate(items):
        row, col = divmod(i, 4)
        cols_this_row = min(n_cols, max(1, len(items) - row * 4))
        cw_row = (w - gap * (cols_this_row - 1)) / cols_this_row
        cx = x + col * (cw_row + gap)
        top = cur_y + row * (86.0 + gap)
        elems.append(shape(f"sla-{i}", [cx, top, cw_row, 86.0], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        elems.append(shape(f"sla-{i}-bar", [cx, top, cw_row, 3.0], "rect",
                           fill=c["primary"]))
        elems.append(_line(f"sla-{i}-n", [cx + 10, top + 10, cw_row - 20, 16],
                           it["name"], font_size=11,
                           color=c["text_secondary"],
                           align=("left", "middle")))
        elems.append(_line(f"sla-{i}-v", [cx + 10, top + 28, cw_row - 20, 26],
                           it["value"], font_size=19, color=c["primary"],
                           bold=True, align=("left", "middle")))
        if it["desc"]:
            elems.append(text(f"sla-{i}-d",
                              [cx + 10, top + 56, cw_row - 20, 26],
                              it["desc"], font_size=9,
                              color=c["text_tertiary"],
                              align=("left", "top")))
    n_rows = max(1, math.ceil(len(items) / 4))
    total_h = (28 if title else 0) + n_rows * 86.0 + (n_rows - 1) * gap
    return elems, total_h


def emit_profile_card_pptd(n, x, y, w, c):
    """profile_card：人员卡（C-E2）：左照片/首字圆头像 + 右姓名职务经历。

    每人一行通栏卡，卡高按经历文本 hug（11pt 折行）；photo 已由调用方
    （_pptd_gen）预解析为绝对路径，空则首字圆头像兜底。
    """
    elems = []
    cur_y = float(y)
    title = n.get("title")
    if title:
        elems.append(_line("pfc-t", [x, cur_y, w, 22], title, font_size=14,
                           color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        cur_y += 28
    for i, p in enumerate(n["profiles"]):
        desc_lines = (wrap_lines(p["desc"], 11, w - 2 * INSET_X - 76)
                      if p["desc"] else [])
        desc_h = stack_text_h(len(desc_lines), 11)
        contact_h = 14.0 if p["contact"] else 0.0
        card_h = max(76.0, 12 + 20 + desc_h + contact_h + 12)
        elems.append(shape(f"pfc-{i}", [x, cur_y, w, card_h], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        photo = p.get("photo") or ""
        if photo and os.path.exists(str(photo)):
            elems.append(_image_el(f"pfc-{i}-ph",
                                   [x + 12, cur_y + 12, 56, card_h - 24],
                                   str(photo)))
        else:
            elems.append(shape(f"pfc-{i}-av",
                               [x + 12, cur_y + (card_h - 44) / 2, 44, 44],
                               "ellipse", fill=c["bg_soft"]))
            elems.append(_line(f"pfc-{i}-avt",
                               [x + 12, cur_y + (card_h - 44) / 2, 44, 44],
                               (p["name"] or "◆")[:1], font_size=17,
                               color=c["primary"], bold=True,
                               align=("center", "middle")))
        tx = x + 80
        tw = w - 92
        elems.append(_line(f"pfc-{i}-n", [tx, cur_y + 10, tw - 90, 20],
                           p["name"], font_size=13, color=c["text_primary"],
                           bold=True, align=("left", "middle")))
        if p["role"]:
            elems.append(_line(f"pfc-{i}-r", [tx + tw - 220, cur_y + 10, 220, 20],
                               p["role"], font_size=11, color=c["primary"],
                               bold=True, align=("right", "middle")))
        if p["desc"]:
            elems.append(text(f"pfc-{i}-d", [tx, cur_y + 32, tw, desc_h + 2],
                              p["desc"], font_size=11,
                              color=c["text_secondary"],
                              align=("left", "top")))
        if p["contact"]:
            elems.append(_line(f"pfc-{i}-c",
                               [tx, cur_y + card_h - 12 - contact_h, tw,
                                contact_h], p["contact"], font_size=10,
                               color=c["text_tertiary"],
                               align=("left", "middle")))
        cur_y += card_h + 10
    total_h = (cur_y - y - 10) if n["profiles"] else (28 if title else 0)
    return elems, total_h


def emit_logo_wall_pptd(n, x, y, w, c):
    """logo_wall：logo 网格（C-E2，收尾标配）：4 列、格高 64、≤8 两行。

    src 空/缺失用客户名文字牌兜底；图格 padding 6px，fit contain。
    """
    logos = n["logos"]
    elems = []
    cur_y = float(y)
    title = n.get("title")
    if title:
        elems.append(_line("lgw-t", [x, cur_y, w, 22], title, font_size=14,
                           color=c["text_primary"], bold=True,
                           align=("left", "middle")))
        cur_y += 28
    gap = 12.0
    cell_h = 64.0
    for i, lg in enumerate(logos):
        row, col = divmod(i, 4)
        cx = x + col * ((w - gap * 3) / 4 + gap)
        top = cur_y + row * (cell_h + gap)
        elems.append(shape(f"lgw-{i}", [cx, top, (w - gap * 3) / 4, cell_h],
                           "roundRect", fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]}, adjustments=[8000]))
        cw_cell = (w - gap * 3) / 4
        src = lg.get("src") or ""
        if src and os.path.exists(str(src)):
            elems.append(_image_el(f"lgw-{i}-img",
                                   [cx + 6, top + 6, cw_cell - 12,
                                    cell_h - 12], str(src)))
        else:
            elems.append(_line(f"lgw-{i}-n",
                               [cx + 6, top, cw_cell - 12, cell_h],
                               lg["name"], font_size=12,
                               color=c["text_tertiary"],
                               align=("center", "middle")))
    n_rows = max(1, math.ceil(len(logos) / 4))
    total_h = (28 if title else 0) + n_rows * cell_h + (n_rows - 1) * gap
    return elems, total_h


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




from .pptd_emit_ext import (
    emit_conclusion_band_pptd, emit_decision_board_pptd,
    emit_evidence_ledger_pptd, emit_raci_matrix_pptd,
    emit_risk_register_pptd, emit_ui_mock_pptd,
)


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
    # Step 5 新增元素
    "ui_mock": emit_ui_mock_pptd,
    "conclusion_band": emit_conclusion_band_pptd,
    # S8 Wave B（C-E2 三件套）
    "sla_block": emit_sla_block_pptd,
    "profile_card": emit_profile_card_pptd,
    "logo_wall": emit_logo_wall_pptd,
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
