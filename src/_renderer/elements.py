# -*- coding: utf-8 -*-
"""元素协议层：字段读取与能力声明的单点（重构 Phase 1，§6.1）。

依据 docs/refactor_plan_spec_pipeline_2026-07-20.md §六：
- 每种元素一个 normalize 函数，输入 spec element dict，输出标准化 dict；
  字段兼容逻辑（phases 三套写法等）只在本模块做，渲染器不再各自兼容。
- CAPABILITIES 声明每种元素在 HTML/DOCX/PPTD 三端的支持性；
  不支持端由 degrade_text 产出显式降级文本，绝不静默跳过。
- RenderReport 收集跳过/降级/警告（§6.3），供 CLI 摘要与 verify 消费。

本模块不做渲染；三端渲染器（下个任务接入）改为消费本模块。
"""

# 三端标识
END_HTML = "html"
END_DOCX = "docx"
END_PPTD = "pptd"
ENDS = (END_HTML, END_DOCX, END_PPTD)

# 能力取值
RENDER = "render"    # 该端原生渲染
DEGRADE = "degrade"  # 该端不支持，输出降级文本

# 能力矩阵（§6.1 目标矩阵）：每种元素 × 三端
CAPABILITIES = {
    "text":     {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "bullets":  {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "cards":    {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "table":    {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "phases":   {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    # pullquote 的 docx、heading 的 html/pptd 是本次补齐
    "pullquote": {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "heading":  {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    # 4A 架构图只有 docx 有原生渲染（layers 段落），html/pptd 降级
    "architecture_4a": {END_HTML: DEGRADE, END_DOCX: RENDER, END_PPTD: DEGRADE},
    # diagram 走专用渲染管线（_renderer.diagram），docx 无原生渲染，降级
    "diagram":  {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    # 产品介绍占位卡走专用渲染管线，docx 降级
    "product_intro_placeholder": {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    # ---- 视觉规范 v2.0 页面构件（dev_plan_visual_v2_2026-07-25 §5.2）----
    "hero":        {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "section_tag": {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "action_title": {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "stat_cards":  {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "kpi_cards":   {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "pain_cards":  {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "info_cards":  {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "legend_bar":  {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "qa_block":    {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    # topnav 仅 HTML 长文档导航；PPT/DOCX 降级页眉文本
    "topnav":      {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: DEGRADE},
    # page_header 页面级页眉横幅（D-092 第1层统一页面语言，双端渲染）
    "page_header": {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    # D-093 视角卡 + 底部 callout：4 列「痛点/优势」叙事页（麦肯锡式）
    "view_cards":   {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "callout_block": {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    # ---- 视觉规范 v3.0 版式构件（dev_plan_visual_v3_2026-08-11 §T5）----
    # P12 目录 / P14 双栏对比 / P15 优缺点 / P16 CTA：DOCX 降级
    "toc_cards":   {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "duo_compare": {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "pros_cons":   {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    "cta_block":   {END_HTML: RENDER, END_DOCX: DEGRADE, END_PPTD: RENDER},
    # ---- 批次 B 组件（B-3 证据台账，dev_plan_材料生成管线 v4）----
    "evidence_ledger": {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "risk_register":  {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "raci_matrix":    {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
    "decision_board": {END_HTML: RENDER, END_DOCX: RENDER, END_PPTD: RENDER},
}

# ---- v2 枚举合法值（协议层单点；schema 校验与渲染层共用，§5.3）----
HL_TONES = ("yellow", "red", "green")            # action_title segments.hl
STAT_TONES = ("blue", "lit", "part", "gap")      # stat_cards 左色条
PAIN_LEVELS = ("P0", "P1", "P2")                 # pain_cards 徽章
LEGEND_SWATCHES = (                              # legend_bar 色块（三态/keep/角色）
    "lit", "part", "gap", "keep",
    "role_biz", "role_legal", "role_fin", "role_sys", "role_ext",
)
RISK_LEVELS = ("高", "中", "低")                 # risk_register 等级（B-4）
RACI_ENUM = ("R", "A", "C", "I")                 # raci_matrix 单元格值（B-5）


def _first_str(elem, keys, default=""):
    """按优先级取第一个非空字段并转 str；全部缺失/为 None/空串时返回 default。"""
    for key in keys:
        value = elem.get(key)
        if value is not None and value != "":
            return str(value)
    return default


def _as_list(value):
    """非 list 一律归一到空列表（normalize 不抛异常）。"""
    return value if isinstance(value, list) else []


def _esc(text):
    """HTML 转义（用户文本进 HTML/pptd 富文本前必须转义防注入）。

    全项目唯一定义（§七 2.6）：diagram 包（theme.py/pptd_emit.py 经 import
    复用）、_renderer HTML 基础元素、_pptd_gen 用户文本统一消费本函数。
    """
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# _nl2br 占位符：保护「字面 \n」（双反斜杠+n 的转义写法）不被转成 <br>
_NL_LITERAL_PLACEHOLDER = "\x00"


def _nl2br(text):
    r"""多行文本转 HTML：先 _esc 转义，再把换行统一转 <br>（保持 §七 2.6 顺序）。

    - `\\n`（双反斜杠+n，作者想要字面 \n，如 Windows 路径写法）先换占位符，
      最后恢复为字面 \n，不参与换行转换；
    - 剩余字面 `\n`（单反斜杠+n，YAML 单引号写法的换行意图）与真实换行
      统一转 <br>；
    - \r 直接清除（Windows 粘贴的 \r\n 不再残留不可见字符）。
    """
    s = _esc(text)
    s = s.replace("\\\\n", _NL_LITERAL_PLACEHOLDER)
    s = s.replace("\\n", "\n")
    s = s.replace("\r", "")
    s = s.replace("\n", "<br>")
    return s.replace(_NL_LITERAL_PLACEHOLDER, "\\n")


def normalize_text(elem):
    """text 元素：兼容 content|text；role 原样带出（缺省 ""）。"""
    return {
        "content": _first_str(elem, ("content", "text")),
        "role": _first_str(elem, ("role",)),
    }


def normalize_bullets(elem):
    """bullets 元素：items 统一为 str 列表。"""
    return {"items": [str(item) for item in _as_list(elem.get("items"))]}


def normalize_cards(elem):
    """cards 元素：每张卡四键齐全（title/body/tag/highlight），缺省 ""。"""
    cards = []
    for card in _as_list(elem.get("cards")):
        if not isinstance(card, dict):
            card = {}
        cards.append({
            "title": _first_str(card, ("title",)),
            "body": _first_str(card, ("body",)),
            "tag": _first_str(card, ("tag",)),
            "highlight": _first_str(card, ("highlight",)),
        })
    return {"cards": cards}


def normalize_table(elem):
    """table 元素：headers 为 str 列表；rows 统一为 str 列表的列表。"""
    headers = [str(h) for h in _as_list(elem.get("headers"))]
    rows = []
    for row in _as_list(elem.get("rows")):
        if isinstance(row, (list, tuple)):
            rows.append([str(cell) for cell in row])
        else:
            rows.append([str(row)])
    return {"headers": headers, "rows": rows}


def normalize_phases(elem):
    """phases 元素：归一到 name/desc/actions，字段兼容只在这一处做。

    兼容现存三套写法（重构计划 §一/§二 B3）：
    - name ← name|label|phase|title（label 是 HTML/DOCX 旧写法，phase/title
      是 outline-to-spec 旧写法；真实 spec 的 milestones 也用 label）
    - desc ← desc|goal（goal 是 HTML/DOCX 旧写法）
    - actions ← actions|items（items 是 outline-to-spec 旧写法），缺省 []
    """
    phases = []
    for phase in _as_list(elem.get("phases")):
        if not isinstance(phase, dict):
            phase = {}
        actions = phase.get("actions")
        if not isinstance(actions, list):
            actions = phase.get("items")
        phases.append({
            "name": _first_str(phase, ("name", "label", "phase", "title")),
            "desc": _first_str(phase, ("desc", "goal")),
            "actions": [str(a) for a in _as_list(actions)],
        })
    return {"phases": phases}


def normalize_pullquote(elem):
    """pullquote 元素：content/cite，缺省 ""。"""
    return {
        "content": _first_str(elem, ("content",)),
        "cite": _first_str(elem, ("cite",)),
    }


def normalize_heading(elem):
    """heading 元素：兼容 text|title|content；level 缺省 2，钳到 1-7。"""
    try:
        level = int(elem.get("level", 2))
    except (TypeError, ValueError):
        level = 2
    return {
        "text": _first_str(elem, ("text", "title", "content")),
        "level": max(1, min(7, level)),
    }


# ---- 视觉规范 v2.0 页面构件 normalizers（§5.3：字段缺省 ""、列表归一）----


def _norm_dict_list(value, keys):
    """dict 列表归一：每项非 dict 置 {}，各键 _first_str 缺省 ""。"""
    out = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            item = {}
        out.append({k: _first_str(item, (k,)) for k in keys})
    return out


def normalize_hero(elem):
    """hero：封面横幅；meta 为 str 列表，stats 为 value/unit/label 三元组。"""
    return {
        "eyebrow": _first_str(elem, ("eyebrow",)),
        "title": _first_str(elem, ("title",)),
        "subtitle": _first_str(elem, ("subtitle",)),
        "meta": [str(m) for m in _as_list(elem.get("meta"))],
        "stats": _norm_dict_list(elem.get("stats"), ("value", "unit", "label")),
    }


def normalize_section_tag(elem):
    """section_tag：章节胶囊标签（index 如 SECTION 1 / EXHIBIT 1）。"""
    return {
        "index": _first_str(elem, ("index",)),
        "label": _first_str(elem, ("label",)),
    }


def normalize_action_title(elem):
    """action_title：结论式标题；segments 为 {t, hl} 行内强调唯一写法。

    hl 原样带出（非法值由 schema 报错），渲染层只认 HL_TONES。
    """
    segments = []
    for seg in _as_list(elem.get("segments")):
        if not isinstance(seg, dict):
            seg = {"t": seg}
        hl = seg.get("hl")
        segments.append({
            "t": _first_str(seg, ("t",)),
            "hl": "" if hl is None else str(hl),
        })
    return {
        "segments": segments,
        "sub": _first_str(elem, ("sub",)),
    }


def normalize_stat_cards(elem):
    """stat_cards：统计卡行；tone 原样带出（schema 校验 STAT_TONES）。"""
    return {"cards": _norm_dict_list(
        elem.get("cards"), ("value", "unit", "label", "tone"))}


def normalize_kpi_cards(elem):
    """kpi_cards：前后对比卡（label/from/to/note）。"""
    return {"cards": _norm_dict_list(
        elem.get("cards"), ("label", "from", "to", "note"))}


def normalize_pain_cards(elem):
    """pain_cards：痛点卡；level 原样带出（schema 校验 PAIN_LEVELS）。"""
    return {"cards": _norm_dict_list(
        elem.get("cards"), ("title", "level", "impact", "body"))}


def normalize_info_cards(elem):
    """info_cards：要点卡（title + items 列表）。"""
    cards = []
    for card in _as_list(elem.get("cards")):
        if not isinstance(card, dict):
            card = {}
        cards.append({
            "title": _first_str(card, ("title",)),
            "items": [str(i) for i in _as_list(card.get("items"))],
        })
    return {"cards": cards}


def normalize_legend_bar(elem):
    """legend_bar：图例条；swatch 原样带出（schema 校验 LEGEND_SWATCHES）。"""
    return {"items": _norm_dict_list(elem.get("items"), ("swatch", "label"))}


def normalize_qa_block(elem):
    """qa_block：问答块（q/a 对）。"""
    return {"items": _norm_dict_list(elem.get("items"), ("q", "a"))}


def normalize_topnav(elem):
    """topnav：长 HTML 导航；章节锚点由 pages 自动生成，无需手写。

    v3.0 扩展：logo / logo_position（spec 顶层 brand 合并注入，见 __init__）。
    """
    return {
        "brand": _first_str(elem, ("brand",)),
        "brand_sub": _first_str(elem, ("brand_sub",)),
        "logo": _first_str(elem, ("logo",)),
        "logo_position": _first_str(elem, ("logo_position",)),
    }


def normalize_page_header(elem):
    """page_header：页面级页眉横幅（D-092 第1层统一页面语言）。

    渐变横幅 + EX 编号徽章 + 标题 + 章节胶囊 + meta；index/tag/meta 均
    可选（缺省 ""/[]），title 必填（schema 校验）。
    """
    return {
        "index": _first_str(elem, ("index",)),
        "title": _first_str(elem, ("title",)),
        "tag": _first_str(elem, ("tag",)),
        "meta": [str(m) for m in _as_list(elem.get("meta"))],
    }


def normalize_view_cards(elem):
    """view_cards：4 列视角卡片（D-093 麦肯锡式说服叙事页）。

    顶端半圆顶居中标题 + 4 列并列卡片。每卡：char icon（占位符风格）
    + 视角名 + 关键数字 headline + 1-3 行正文。整组 3-4 卡（不可过少）。
    """
    return {
        "title": _first_str(elem, ("title",)),
        "cards": _norm_dict_list(
            elem.get("cards"),
            ("perspective", "icon", "headline", "detail", "tone")),
    }


def normalize_callout_block(elem):
    """callout_block：底部双编号说服区（D-093）。

    淡蓝底 + 圆角 + 双编号（01/02）说服句。每点：编号 + 标题（可含 hl
    关键数字） + 1-2 行 desc。整组 2-3 个点（视觉平衡）。
    """
    points = []
    for pt in _as_list(elem.get("points")):
        if not isinstance(pt, dict):
            pt = {}
        points.append({
            "num": _first_str(pt, ("num",)),
            "title": _first_str(pt, ("title",)),
            "highlight": _first_str(pt, ("highlight",)),
            "desc": _first_str(pt, ("desc",)),
        })
    return {"points": points}


def normalize_toc_cards(elem):
    """toc_cards：目录卡（P12，v3.0）。每卡：编号 + 标题 + 可选描述。"""
    cards = []
    for c in _as_list(elem.get("cards")):
        if not isinstance(c, dict):
            c = {}
        if not c.get("title"):
            continue
        cards.append({
            "num": _first_str(c, ("num",)),
            "title": _first_str(c, ("title",)),
            "desc": _first_str(c, ("desc",)),
        })
    return {"cards": cards}


def normalize_duo_compare(elem):
    """duo_compare：双栏对比（P14，v3.0）。左/右各标题 + 要点列表。"""
    def _side(s):
        s = s if isinstance(s, dict) else {}
        return {
            "title": _first_str(s, ("title",)),
            "points": [str(p) for p in _as_list(s.get("points"))],
        }
    return {"left": _side(elem.get("left")),
            "right": _side(elem.get("right"))}


def normalize_pros_cons(elem):
    """pros_cons：优缺点清单（P15，v3.0）。pros 绿 / cons 橙。"""
    return {
        "pros": [str(p) for p in _as_list(elem.get("pros"))],
        "cons": [str(c) for c in _as_list(elem.get("cons"))],
    }


def normalize_cta_block(elem):
    """cta_block：CTA 收尾（P16，v3.0）。标题 + 按钮 + 联系方式。"""
    return {
        "title": _first_str(elem, ("title",)),
        "button": _first_str(elem, ("button",)),
        "contact": _first_str(elem, ("contact",)),
    }


def normalize_evidence_ledger(elem):
    """evidence_ledger：证据台账（B-3）。每条结论挂证据编号 + 状态。

    结构：编号（num）+ 结论（conclusion）+ 证据（evidence）+ 状态（status）。
    """
    items = []
    for item in _as_list(elem.get("items")):
        if not isinstance(item, dict):
            item = {}
        items.append({
            "num": _first_str(item, ("num",)),
            "conclusion": _first_str(item, ("conclusion",)),
            "evidence": _first_str(item, ("evidence",)),
            "status": _first_str(item, ("status",)),
        })
    return {"title": _first_str(elem, ("title",)), "items": items}


def normalize_risk_register(elem):
    """risk_register：风险登记（B-4）。风险项 + 等级（高/中/低）+ 状态 + 应对。"""
    items = []
    for item in _as_list(elem.get("items")):
        if not isinstance(item, dict):
            item = {}
        items.append({
            "risk": _first_str(item, ("risk",)),
            "level": _first_str(item, ("level",)),
            "status": _first_str(item, ("status",)),
            "response": _first_str(item, ("response",)),
        })
    return {"title": _first_str(elem, ("title",)), "items": items}


def normalize_raci_matrix(elem):
    """raci_matrix：角色责任矩阵（B-5）。roles 列头 + tasks 行 + cells R/A/C/I。"""
    roles = [str(r) for r in _as_list(elem.get("roles"))]
    tasks = []
    for t in _as_list(elem.get("tasks")):
        if not isinstance(t, dict):
            t = {}
        raw_cells = t.get("cells") if isinstance(t.get("cells"), dict) else {}
        cells = {str(k): str(v) for k, v in raw_cells.items()}
        tasks.append({"task": _first_str(t, ("task",)), "cells": cells})
    return {"title": _first_str(elem, ("title",)), "roles": roles, "tasks": tasks}


def normalize_decision_board(elem):
    """decision_board：决策面板（B-6）。方案比较 + 推荐 + 下一步。"""
    options = []
    for opt in _as_list(elem.get("options")):
        if not isinstance(opt, dict):
            opt = {}
        options.append({
            "name": _first_str(opt, ("name",)),
            "pros": [str(p) for p in _as_list(opt.get("pros"))],
            "cons": [str(c) for c in _as_list(opt.get("cons"))],
        })
    return {
        "title": _first_str(elem, ("title",)),
        "options": options,
        "recommendation": _first_str(elem, ("recommendation",)),
        "next_step": _first_str(elem, ("next_step",)),
    }


# 有字段标准化需求的元素分派表
_NORMALIZERS = {
    "text": normalize_text,
    "bullets": normalize_bullets,
    "cards": normalize_cards,
    "table": normalize_table,
    "phases": normalize_phases,
    "pullquote": normalize_pullquote,
    "heading": normalize_heading,
    # v2 页面构件（§5.2/§5.3）
    "hero": normalize_hero,
    "section_tag": normalize_section_tag,
    "action_title": normalize_action_title,
    "stat_cards": normalize_stat_cards,
    "kpi_cards": normalize_kpi_cards,
    "pain_cards": normalize_pain_cards,
    "info_cards": normalize_info_cards,
    "legend_bar": normalize_legend_bar,
    "qa_block": normalize_qa_block,
    "topnav": normalize_topnav,
    "page_header": normalize_page_header,
    # D-093 视角卡 + 底部 callout（对齐麦肯锡式说服叙事页）
    "view_cards": normalize_view_cards,
    "callout_block": normalize_callout_block,
    # v3.0 版式构件（P12/P14/P15/P16）
    "toc_cards": normalize_toc_cards,
    "duo_compare": normalize_duo_compare,
    "pros_cons": normalize_pros_cons,
    "cta_block": normalize_cta_block,
    # 批次 B 组件（B-3 证据台账）
    "evidence_ledger": normalize_evidence_ledger,
    "risk_register": normalize_risk_register,
    "raci_matrix": normalize_raci_matrix,
    "decision_board": normalize_decision_board,
}


def normalize_element(elem):
    """总分派：返回 (elem_type, normalized dict)。

    diagram / product_intro_placeholder / architecture_4a 各有专用消费方
    （diagram 渲染管线、DOCX layers 段落），不需要字段标准化，直接返回原
    dict；未知 type 同样原样返回，由调用方走 degrade_text / report。
    """
    if not isinstance(elem, dict):
        return "", {}
    elem_type = elem.get("type", "")
    normalizer = _NORMALIZERS.get(elem_type)
    if normalizer is None:
        return elem_type, elem
    return elem_type, normalizer(elem)


def degrade_text(elem_type, normalized_or_elem, target_end):
    """产出目标端的降级文本（§6.1：不支持端显式降级并告知）。

    normalized_or_elem: normalize 后的 dict 或原始 element dict（本函数
    消费的 diagram/placeholder/architecture_4a 均不做字段标准化，两者同形）。
    """
    elem = normalized_or_elem if isinstance(normalized_or_elem, dict) else {}
    if elem_type == "architecture_4a":
        return "[4A 架构图] 本节内容请见 Word 版"
    if elem_type == "diagram":
        title = _first_str(elem, ("title",)) or "未命名"
        return f"[架构图：{title}] 请见 HTML/PPT 版"
    if elem_type == "product_intro_placeholder":
        return f"[产品介绍占位：{_first_str(elem, ('title',))}]"
    # v2 页面构件降级文案（§5.2 DEGRADE 端）
    _V2_DEGRADE = {
        "hero": "封面横幅",
        "stat_cards": "统计卡",
        "kpi_cards": "前后对比卡",
        "pain_cards": "痛点卡",
        "legend_bar": "图例条",
        "topnav": "页首导航",
        "page_header": "页眉横幅",
        "view_cards": "视角卡",
        "callout_block": "底部说服区",
        "toc_cards": "目录卡",
        "duo_compare": "双栏对比",
        "pros_cons": "优缺点清单",
        "cta_block": "CTA 收尾区",
    }
    if elem_type in _V2_DEGRADE:
        title = _first_str(elem, ("title", "brand"))
        suffix = f"：{title}" if title else ""
        return f"[{_V2_DEGRADE[elem_type]}{suffix}] 请见 HTML 版"
    return f"[不支持的元素类型：{elem_type}]"


class RenderReport:
    """渲染报告：收集跳过/降级/警告，消灭静默（§6.3）。

    skipped/degraded 条目为 dict，供 verify L1 检查与 CLI 摘要消费。
    """

    def __init__(self):
        self.skipped = []
        self.degraded = []
        self.warnings = []

    def skip(self, page_id, index, elem_type, reason):
        """记录一个被跳过的元素（未知 type、schema 非法等）。"""
        self.skipped.append({
            "page": page_id,
            "index": index,
            "type": elem_type,
            "reason": reason,
        })

    def degrade(self, page_id, index, elem_type, target_end, message):
        """记录一个被降级的元素（该端不支持，输出了降级文本）。"""
        self.degraded.append({
            "page": page_id,
            "index": index,
            "type": elem_type,
            "target": target_end,
            "message": message,
        })

    def warn(self, message):
        """记录一条警告（内容超限、字段可疑等）。"""
        self.warnings.append(str(message))

    def has_issues(self):
        """是否有任何跳过/降级/警告。"""
        return bool(self.skipped or self.degraded or self.warnings)

    def summary(self):
        """人类可读摘要：首行计数，随后逐条明细。"""
        lines = [
            f"跳过 {len(self.skipped)} 元素 / "
            f"降级 {len(self.degraded)} 元素 / "
            f"警告 {len(self.warnings)} 条"
        ]
        for item in self.skipped:
            lines.append(
                f"  [跳过] {item['page']} elements[{item['index']}] "
                f"{item['type']}: {item['reason']}"
            )
        for item in self.degraded:
            lines.append(
                f"  [降级] {item['page']} elements[{item['index']}] "
                f"{item['type']} -> {item['target']}: {item['message']}"
            )
        for message in self.warnings:
            lines.append(f"  [警告] {message}")
        return "\n".join(lines)


def empty_payload_reason(elem_type):
    """空载荷进 report.skipped 的理由；table 缺 headers/rows 给专属说明。"""
    if elem_type == "table":
        return "表格缺 headers 或 rows"
    return "内容为空（可能字段名错误或空元素）"


def is_empty_payload(elem_type, normalized):
    """基础元素 normalize 后内容是否为（可能字段名写错或空元素）。

    渲染器据此把"已知类型但无内容"计入 report.skipped 而非静默丢失
    （通用_schema验收样件的验收语义）。diagram/placeholder/architecture_4a
    各有专用校验与降级路径，不在此列。
    table 口径：headers 或 rows 任一为缺失/空即空载荷——rows-only/
    headers-only 的半边表格曾在 HTML 端静默丢弃（return "" 不进 report）。
    """
    if elem_type == "text":
        return not normalized.get("content")
    if elem_type == "bullets":
        return not normalized.get("items")
    if elem_type == "cards":
        return not normalized.get("cards")
    if elem_type == "table":
        return not normalized.get("headers") or not normalized.get("rows")
    if elem_type == "phases":
        return not normalized.get("phases")
    if elem_type == "pullquote":
        return not normalized.get("content")
    if elem_type == "heading":
        return not normalized.get("text")
    # v2 页面构件（§5.2）：空载荷判定与渲染层读取口径一致
    if elem_type == "hero":
        return not normalized.get("title")
    if elem_type == "section_tag":
        return not normalized.get("label")
    if elem_type == "action_title":
        return not any(seg.get("t") for seg in normalized.get("segments", []))
    if elem_type in ("stat_cards", "kpi_cards", "pain_cards", "info_cards"):
        return not normalized.get("cards")
    if elem_type in ("legend_bar", "qa_block"):
        return not normalized.get("items")
    if elem_type == "topnav":
        return not normalized.get("brand")
    return False
