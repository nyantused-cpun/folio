# -*- coding: utf-8 -*-
"""批次 B/ui_mock/conclusion_band 的 pptd 发射器（S8-B 棘轮拆小：自
pptd_emit.py 迁出，与 pptd_emit_chrome 同批；迁移动因见该模块头）。"""
from .. import theme
from ..spacing import INSET_X, est_text_w
from .pptd_emit import (
    _line, shape, stack_text_h, text, wrap_lines,
)



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


def emit_ui_mock_pptd(n, x, y, w, c):
    """ui_mock：全原生形状界面示意卡（roundRect/rect/ellipse/文本框，零 freeform）。

    DOCX 端降级；HTML/PPTD 原生。公章/装饰条等装饰形状打 decor: true 标记，
    为 bbox 观察数据预埋。
    """
    elems = []
    outer_x, outer_y, outer_w = float(x), float(y), float(w)
    top_h = 24.0 if n["frame"] == "browser" else 0.0
    pad = 14.0
    body_x = outer_x + pad
    body_w = outer_w - 2 * pad
    cur_y = outer_y + top_h + 10

    # 外框
    elems.append(shape("um-bg", [outer_x, outer_y, outer_w, 0], "roundRect",
                       fill=c["card"],
                       border={"style": "solid", "width": 1.0,
                               "color": c["border"]}, adjustments=[6000]))
    if n["frame"] == "browser":
        elems.append(shape("um-top", [outer_x, outer_y, outer_w, top_h], "rect",
                           fill=c["bg_muted"]))
        for i in range(3):
            elems.append(shape(f"um-dot{i}", [outer_x + 10 + i * 16,
                                               outer_y + 8, 8, 8], "ellipse",
                               fill=c["text_tertiary"], decor=True))
        elems.append(shape("um-addr", [outer_x + 70, outer_y + 5,
                                       outer_w - 90, 14], "roundRect",
                           fill=c["card"],
                           border={"style": "solid", "width": 1.0,
                                   "color": c["border"]},
                           adjustments=[50000]))
    # 标题
    title_h = 26.0
    elems.append(_line("um-title", [body_x, cur_y, body_w, title_h],
                       n["title"], font_size=16, color=c["primary"], bold=True,
                       align=("left", "middle")))
    cur_y += title_h + 6

    # tabs
    if n["tabs"]:
        tab_h = 24.0
        cur_x = body_x
        for i, tab in enumerate(n["tabs"]):
            tw = est_text_w(tab, 12) + 24
            elems.append(_line(f"um-tab{i}", [cur_x, cur_y, tw, tab_h], tab,
                               font_size=12,
                               color=c["primary"] if i == 0 else c["text_secondary"],
                               bold=(i == 0), align=("left", "middle")))
            if i == 0:
                elems.append(shape(f"um-tabline{i}", [cur_x, cur_y + tab_h - 2,
                                                      tw, 2], "rect", fill=c["primary"]))
            cur_x += tw + 14
        cur_y += tab_h + 8

    # sections / bars
    for si, sec in enumerate(n["sections"]):
        if sec.get("subtitle"):
            elems.append(_line(f"um-sub{si}", [body_x, cur_y, body_w, 18],
                               sec["subtitle"], font_size=12,
                               color=c["text_secondary"], bold=True,
                               align=("left", "middle")))
            cur_y += 20
        for bi, b in enumerate(sec.get("bars") or []):
            try:
                bw = body_w * max(10, min(100, int(b))) / 100.0
            except (TypeError, ValueError):
                bw = body_w * 0.5
            elems.append(shape(f"um-bar{si}-{bi}", [body_x, cur_y, bw, 10],
                               "rect", fill=c["border"], decor=True))
            cur_y += 14
        cur_y += 4

    # seal
    seal = n.get("seal") or {}
    if seal and n["variant"] == "document":
        seal_d = 72.0
        sx = body_x + body_w / 2 - seal_d / 2
        elems.append(shape("um-seal", [sx, cur_y + 4, seal_d, seal_d], "ellipse",
                           border={"style": "solid", "width": 2.0,
                                   "color": c["role_legal"]}, decor=True))
        if seal.get("text"):
            elems.append(_line("um-seal-t", [sx, cur_y + 12, seal_d, 22],
                               seal["text"], font_size=12,
                               color=c["role_legal"], bold=True,
                               align=("center", "middle")))
        if seal.get("company"):
            elems.append(_line("um-seal-c", [sx, cur_y + 36, seal_d, 30],
                               seal["company"], font_size=8,
                               color=c["role_legal"], align=("center", "middle")))
        cur_y += seal_d + 10

    total_h = cur_y - outer_y + 10
    # 更新外框高度
    elems[0]["bounds"][3] = total_h
    # caption
    if n.get("caption"):
        total_h += 20
        elems.append(_line("um-cap", [outer_x, cur_y, outer_w, 18],
                           n["caption"], font_size=11,
                           color=c["text_tertiary"], align=("center", "middle")))
    return elems, total_h


def emit_conclusion_band_pptd(n, x, y, w, c):
    """conclusion_band：通栏结论色带，主色加粗（单行文本不支持 run 级变色）。"""
    tone = n.get("tone") or "primary"
    if tone == "accent":
        fill = c["accent"]
        text_color = c["hero_from"]
    elif tone == "muted":
        fill = c["bg_muted"]
        text_color = c["text_secondary"]
    else:
        fill = c["primary"]
        text_color = theme.WHITE
    lines = len(wrap_lines(n["text"], 14, w - 2 * INSET_X - 20))
    h = max(36.0, 14 + stack_text_h(lines, 14) + 14)
    elems = [shape("cb-band", [x, y, w, h], "roundRect", fill=fill,
                   adjustments=[8000])]
    elems.append(text("cb-t", [x + 10, y, w - 20, h], n["text"], font_size=14,
                      color=text_color, bold=True, align=("left", "middle")))
    return elems, h


