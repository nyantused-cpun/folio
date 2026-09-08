# -*- coding: utf-8 -*-
"""spec 元素全量 schema 校验：8 种基础元素 + 10 种 v2 页面构件 + diagram 37 种子类型 + 占位卡。

依据 docs/dev_plan_diagram_elements_2026-07-19.md §4（schema 扩展）+
docs/diagram_visual_design_v1_2026-07-19.md（v1.2，capability_map 增补）+
docs/refactor_plan_spec_pipeline_2026-07-20.md §六 6.2（全量校验、未知
type 从静默改为报错）+
docs/dev_plan_visual_v2_2026-07-25.md §5/§6（v2.0：页面构件、flow_rows、
theme 主题名、页面版式目录、hex 防线）。

基础元素的"有效值"判断复用 _renderer.elements 的 normalize 规则（字段兼容
逻辑单点定义，两处使用，§6.2）；未知 type 报错并列出合法值。

校验策略：逐元素返回错误列表，不抛异常——渲染层对非法元素降级为占位卡
（dev plan §11.2），不阻断整篇生成。
"""


from _renderer import elements as _proto
from _renderer._spec_hex import _validate_spec_hex  # S8 拆小迁入（防循环：其内部惰性回调本模块）

# diagram_type -> {subtype: [必填专有字段]}
DIAGRAM_SCHEMA = {
    "flow": {
        "sequence": ["steps"],
        "cross_system": ["systems", "steps"],
        "swimlane": ["lanes", "steps"],
        "parallel": ["sources", "merge"],
        "decision": ["steps"],
        "flow_rows": ["rows"],  # v2.0 引入（§5.4，纯增量 F8）
    },
    "architecture": {
        "4a": ["layers"],
        "layered": ["layers"],
        "integration": [],
        "biz_overview": ["domains"],
        "platform_hub": ["center", "satellites"],  # 中心-环绕-右集成平台规划图（D-094）
        "deployment": ["zones"],
        "biz_it_mapping": ["mappings"],
        "pyramid": ["levels"],  # 第 32 种：层级金字塔（D-5，trapezoid 堆叠）
        "infra": ["zones"],  # 第 34 种：IT 基础设施标准图形（图标节点+分区+连线）
    },
    "matrix": {
        "fit_gap": ["requirements", "products", "cells"],
        "raci": ["roles", "tasks"],
        "crud": ["docs", "entities", "cells"],
        "cbm": ["rows"],
        "capability_map": ["sections"],
        "quadrant": ["axes", "quads"],  # 第 33 种：四象限（D-5，两轴+四区）
        "harvey_balls": ["rows", "columns", "cells"],  # 第 35 种：哈维球对比表（五档防假精度）
    },
    "timeline": {
        "horizontal": ["milestones"],
        "vertical": ["milestones"],
        "module_gantt": ["columns", "groups"],  # 第 30 种：域标签+季度网格+编号模块落格（D-095）
        "milestone_gantt": ["columns", "tasks"],  # 第 31 种：任务轨×里程碑×依赖，按周铺（B-7）
    },
    "relationship": {
        "er_conceptual": ["entities", "relations"],
        "er_logical": ["entities", "relations"],
        "data_flow": ["nodes", "flows"],
        "org_tree": ["root"],
        "value_chain": ["primary"],
        "biz_capability_tree": ["groups"],
        "process_service_doc_mapping": ["processes", "services", "documents", "mappings"],
        "cross_4a_reconcile": ["terms"],
        "automation_table": ["tasks"],
    },
    "chart": {  # v1.5 新增 diagram_type：数据图表族（审计报告 §3.1 硬缺口）
        "bar": ["categories", "series"],       # 第 36 种：分组柱状图
        "waterfall": ["steps"],                # 第 37 种：瀑布图/收益桥
    },
}

# 合法 element type 全集：从元素协议层 CAPABILITIES 派生（单一事实源，
# 协议层加新元素时这里自动跟上）。保持同名导出兼容既有 import。
KNOWN_ELEMENT_TYPES = set(_proto.CAPABILITIES)

# 容量预算 *_WARN 常量的单一事实源在 budget_consts（S4 棘轮处置，2026-09-07
# 自本模块成簇拆出；graphics.md §2 联动注记指向同源），此处 import 暴露同名，
# 既有引用面（schema.PAGE_ELEMENTS_WARN 等）不变。PYRAMID/QUADRANT 等结构
# 常量非 *_WARN 容量预算，仍留本模块。
from _renderer.budget_consts import (  # noqa: F401
    BCT_CHILDREN_WARN, CAPABILITY_MAP_SECTIONS_WARN, CROSS_SYSTEM_ROWS_WARN,
    CROSS_SYSTEM_SYSTEMS_WARN, DECISION_OPTIONS_WARN, DECISION_STEPS_WARN,
    ELEMENT_TEXT_WARN, EVIDENCE_LEDGER_ROWS_WARN, FLOW_ROWS_CARDS_WARN,
    FLOW_ROWS_TOTAL_WARN, HERO_STATS_WARN, INFRA_ZONE_NODES_WARN,
    INFRA_ZONES_WARN, INFO_CARDS_MAX_WARN, INFO_CARDS_MIN_WARN,
    KPI_CARDS_WARN, LOGO_WALL_CELLS_WARN, MSG_TASKS_WARN,
    P07_TABLE_ROWS_WARN, PAGE_ELEMENTS_WARN,
    PAIN_CARDS_WARN, RACI_TASKS_WARN, RISK_REGISTER_ROWS_WARN,
    SWIMLANE_LANES_WARN, TIMELINE_HORIZONTAL_CARDS_WARN,
    TIMELINE_VERTICAL_CARDS_WARN)

PYRAMID_LEVELS_MIN = 2          # D-5 金字塔层数下限
PYRAMID_LEVELS_MAX = 6          # D-5 金字塔层数上限
QUADRANT_QUADS = 4              # D-5 四象限固定象限数

# ---- 页面版式目录（v2.0 F10 §6 冻结首批；v3.0 扩至 P01-P16，无 P13；批6 扩 P17）----
# required 项三种形态：元素 type 字符串 / ("diagram", diagram_type) /
# ("any", [子项...]) 二选一。必需构件缺失 → error；相对顺序不符 → warning。
FLOW_ROLES = ("biz", "legal", "fin", "sys", "ext")  # flow_rows 角色色板（§5.4）

PAGE_LAYOUTS = {
    "P01": {"name": "封面", "required": ["hero"]},
    "P02": {"name": "章节页", "required": ["section_tag", "action_title"]},
    "P03": {"name": "结论摘要",
            "required": ["section_tag", "action_title", "kpi_cards"]},
    "P04": {"name": "痛点矩阵",
            "required": ["section_tag", "action_title", "pain_cards"]},
    "P05": {"name": "流程图页",
            "required": ["section_tag", "action_title",
                         ("diagram", "flow"), "legend_bar"], "single_diagram": True},
    "P06": {"name": "架构图页",
            "required": ["section_tag", "action_title",
                         ("diagram", "architecture")], "single_diagram": True},
    "P07": {"name": "对比表页",
            "required": ["section_tag", "action_title", "table"]},
    "P08": {"name": "能力地图页",
            "required": ["section_tag", "action_title",
                         ("diagram", "matrix"), "legend_bar"], "single_diagram": True},
    "P09": {"name": "路线图页",
            "required": ["section_tag", "action_title",
                         ("diagram", "timeline")], "single_diagram": True},
    "P10": {"name": "风险与待确认页",
            "required": ["section_tag", "action_title",
                         ("any", ["table", "info_cards"])]},
    "P11": {"name": "收尾页", "required": ["action_title", "info_cards"]},
    # v3.0（2026-08-11）：P12/P14/P15/P16 扩展（无 P13：与 P02 章节页重叠）
    "P12": {"name": "目录页",
            "required": ["section_tag", "action_title", "toc_cards"]},
    "P14": {"name": "双栏对比页",
            "required": ["section_tag", "action_title", "duo_compare"]},
    "P15": {"name": "优缺点清单页",
            "required": ["section_tag", "action_title", "pros_cons"]},
    "P16": {"name": "CTA 收尾页",
            "required": ["action_title", "cta_block"]},
    # 批6（2026-09-05，C17/B4b #6 扩目录决策，decisions.md 在案）：差距矩阵页——
    # 差距二维矩阵（matrix/fit_gap 等）；legend_bar 可选（三档图例，同 P06 先例）
    "P17": {"name": "差距矩阵页",
            "required": ["section_tag", "action_title",
                         ("diagram", "matrix")], "single_diagram": True},
}

# 旧 layout 值白名单（F9 向后兼容）：现存真实 spec 实测 8 值，渲染层本就不
# 消费 layout（自由流），这些值继续有效、不触发版式合规校验。
LEGACY_LAYOUTS = frozenset({
    "title_body", "summary", "cards_3", "blueprint",
    "table", "tree", "phases", "timeline",
})

# Step 5 新元素容量/字段阈值
UI_MOCK_TITLE_MAX = 30       # ui_mock.title ≤30 字
UI_MOCK_SEAL_TEXT_MAX = 6    # ui_mock.seal.text ≤6 字
UI_MOCK_SEAL_COMPANY_MAX = 20  # ui_mock.seal.company ≤20 字
UI_MOCK_BARS_MAX = 8         # 每 section bars ≤8 条
UI_MOCK_BAR_MIN = 10         # bars 宽度百分比下限
UI_MOCK_BAR_MAX = 100        # bars 宽度百分比上限
CONCLUSION_TEXT_MAX = 80     # conclusion_band.text ≤80 字


def all_subtypes():
    """返回 [(diagram_type, subtype), ...] 全量 37 种。"""
    return [(dt, st) for dt, subs in DIAGRAM_SCHEMA.items() for st in subs]


def validate_element(elem, index=None):
    """校验单个 spec 元素，返回错误描述列表（空列表=合法）。

    index: 元素在 page.elements 中的序号（报错定位用）。
    """
    errors = []
    where = f"elements[{index}]" if index is not None else "element"
    if not isinstance(elem, dict):
        return [f"{where}: 元素必须是对象"]

    elem_type = elem.get("type", "")
    if elem_type not in KNOWN_ELEMENT_TYPES:
        # 未知 type（含缺 type 键得到 ""）历史行为是静默跳过，渲染不出来；
        # §6.2 起改为报错，合法值列表随协议层 CAPABILITIES 更新
        legal = "/".join(sorted(KNOWN_ELEMENT_TYPES))
        return [f"{where}: 未知元素类型 '{elem_type}'（合法值：{legal}）"]

    # font_role 已废弃：不再校验，仅在整体 deprecated 警告中提示忽略
    if elem_type == "product_intro_placeholder":
        if not elem.get("title"):
            errors.append(f"{where}: product_intro_placeholder 缺 title")
        return errors

    if elem_type == "architecture_4a":
        return _validate_architecture_4a(elem, where)

    if elem_type != "diagram":
        return _validate_base_element(elem_type, elem, where)

    # diagram 校验
    diagram_type = elem.get("diagram_type", "")
    subtype = elem.get("subtype", "")
    if not diagram_type:
        errors.append(f"{where}: diagram 缺 diagram_type")
        return errors
    if diagram_type not in DIAGRAM_SCHEMA:
        errors.append(f"{where}: 未知 diagram_type '{diagram_type}'"
                      f"（合法值：{'/'.join(sorted(DIAGRAM_SCHEMA))}）")
        return errors
    if not subtype:
        errors.append(f"{where}: diagram 缺 subtype")
        return errors
    subs = DIAGRAM_SCHEMA[diagram_type]
    if subtype not in subs:
        errors.append(f"{where}: subtype '{subtype}' 不属于 {diagram_type}"
                      f"（合法值：{'/'.join(sorted(subs))}）")
        return errors
    if not elem.get("title"):
        errors.append(f"{where}: diagram 缺 title")
    # exhibit 图框契约（#56，B6 Wave3）：溯源字符串只认 exhibit.source（str），
    # 顶层 source 保留给 integration 端点 mapping dict——语义撞车在 schema 封死
    ex = elem.get("exhibit")
    if ex is not None and not isinstance(ex, dict):
        errors.append(f"{where}: exhibit 必须是对象（num/title/source）")
    elif isinstance(ex, dict):
        for f in ("num", "title", "source"):
            if ex.get(f) is not None and not isinstance(ex.get(f), str):
                errors.append(f"{where}: exhibit.{f} 须为字符串，"
                              f"实际 {ex.get(f)!r}")
    # integration 三形态：点对点 mapping（source+target dict，渲染端唯一实现）/
    # 点对点简式（source+target 系统名字符串，outline_to_spec M1 生成器形态——
    # 渲染端 _intg_* 未实现简式，潜在缺口登记 B6 #58）/ 总线（hub+systems）
    if subtype == "integration":
        src = elem.get("source")
        if src is not None and not isinstance(src, (dict, str)):
            errors.append(f"{where}: integration source 须为端点 mapping 对象"
                          "或点对点系统名字符串（溯源字符串请放 exhibit.source）")
        p2p = src and elem.get("target")
        hub = elem.get("hub") and elem.get("systems")
        if not p2p and not hub:
            errors.append(f"{where}: integration 需 source+target（点对点）或 hub+systems（总线）")
        return errors
    if elem.get("source") is not None:
        errors.append(f"{where}: {diagram_type}/{subtype} 顶层 source 已迁移至 "
                      "exhibit.source（顶层 source 仅 integration 端点 mapping 使用）")
    for field in subs[subtype]:
        if not elem.get(field):
            errors.append(f"{where}: {diagram_type}/{subtype} 缺必填字段 '{field}'")
    if subtype == "flow_rows":
        errors.extend(_validate_flow_rows(elem, where))
    elif subtype == "pyramid":
        levels = elem.get("levels") or []
        if (not isinstance(levels, list)
                or not (PYRAMID_LEVELS_MIN <= len(levels) <= PYRAMID_LEVELS_MAX)):
            n = len(levels) if isinstance(levels, list) else "非列表"
            errors.append(f"{where}: pyramid levels 需 {PYRAMID_LEVELS_MIN}-"
                          f"{PYRAMID_LEVELS_MAX} 层（当前 {n}）")
        else:
            for li, lv in enumerate(levels):
                if not isinstance(lv, dict) or not lv.get("title"):
                    errors.append(f"{where}: pyramid levels[{li}] 缺 title")
    elif subtype == "quadrant":
        axes = elem.get("axes") or {}
        if not isinstance(axes, dict) or not axes.get("x") or not axes.get("y"):
            errors.append(f"{where}: quadrant axes 需 x/y 两轴标签")
        quads = elem.get("quads") or []
        if not isinstance(quads, list) or len(quads) != QUADRANT_QUADS:
            n = len(quads) if isinstance(quads, list) else "非列表"
            errors.append(f"{where}: quadrant quads 需恰好 {QUADRANT_QUADS} 个"
                          f"象限（当前 {n}）")
        else:
            for qi, q in enumerate(quads):
                if not isinstance(q, dict) or not q.get("title"):
                    errors.append(f"{where}: quadrant quads[{qi}] 缺 title")
    elif subtype == "harvey_balls":
        rows = elem.get("rows") or []
        cols = elem.get("columns") or []
        for ci, c in enumerate(elem.get("cells") or []):
            if not isinstance(c, dict):
                errors.append(f"{where}: harvey_balls cells[{ci}] 必须是对象")
                continue
            v = c.get("value")
            # isinstance(True, int) 为真：bool 须显式排除（与 bar/waterfall 范式对齐）
            if not isinstance(v, int) or isinstance(v, bool) or not (0 <= v <= 4):
                errors.append(f"{where}: harvey_balls cells[{ci}].value "
                              f"需 0-4 整数（五档：0/25/50/75/100%），实际 {v!r}")
            if str(c.get("row", "")) not in [str(r) for r in rows]:
                errors.append(f"{where}: harvey_balls cells[{ci}].row "
                              f"'{c.get('row')}' 不在 rows 内")
            if str(c.get("col", "")) not in [str(cc) for cc in cols]:
                errors.append(f"{where}: harvey_balls cells[{ci}].col "
                              f"'{c.get('col')}' 不在 columns 内")
    elif subtype == "bar":
        cats = elem.get("categories") or []
        series = elem.get("series") or []
        if len(series) > 5:
            errors.append(f"{where}: chart/bar 系列数 {len(series)} 超上限 5"
                          f"（咨询图表纪律：系列 ≤3-5）")
        for si, s in enumerate(series):
            if not isinstance(s, dict) or not s.get("name"):
                errors.append(f"{where}: chart/bar series[{si}] 缺 name")
                continue
            vals = s.get("values") or []
            if len(vals) != len(cats):
                errors.append(f"{where}: chart/bar series[{si}].values 长度 "
                              f"{len(vals)} ≠ categories 长度 {len(cats)}")
            for vi, v in enumerate(vals):
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    errors.append(f"{where}: chart/bar series[{si}].values[{vi}]"
                                  f" 需数字")
                elif v < 0:
                    errors.append(f"{where}: chart/bar series[{si}].values[{vi}]"
                                  f" 为负值（负值/增减叙事请用 chart/waterfall）")
    elif subtype == "waterfall":
        for si, s in enumerate(elem.get("steps") or []):
            if not isinstance(s, dict) or not s.get("label"):
                errors.append(f"{where}: chart/waterfall steps[{si}] 缺 label")
                continue
            if not isinstance(s.get("value"), (int, float)) \
                    or isinstance(s.get("value"), bool):
                errors.append(f"{where}: chart/waterfall steps[{si}].value 需数字")
            if s.get("kind", "delta") not in ("delta", "total"):
                errors.append(f"{where}: chart/waterfall steps[{si}].kind 非法"
                              f"（合法值：delta/total）")
    return errors


def _validate_flow_rows(elem, where):
    """flow_rows 专项校验（§5.4）：roles 声明、行结构、枚举值、role 引用。

    error 级：roles 键非法/缺 label、空行、group/style/arrow 非法值、
    card 缺 label、card.role 不在 roles 声明内。
    warning 级（见 validate_element_warnings）：行数/行卡超阈值、
    dashed_opt 行内 card 带 badge。
    """
    errors = []
    roles = elem.get("roles")
    declared = set()
    if roles is not None:
        if not isinstance(roles, dict):
            errors.append(f"{where}: flow_rows roles 必须是映射（角色键 -> {{label}}）")
            roles = {}
        for rk, rv in (roles or {}).items():
            if rk not in FLOW_ROLES:
                errors.append(f"{where}: flow_rows roles 未知角色 '{rk}'"
                              f"（合法值：{'/'.join(FLOW_ROLES)}）")
            elif not isinstance(rv, dict) or not rv.get("label"):
                errors.append(f"{where}: flow_rows roles.{rk} 缺 label")
            else:
                declared.add(rk)
    rows = elem.get("rows")
    if not isinstance(rows, list):
        return errors  # rows 缺失/非列表由通用必填循环报出
    for ri, row in enumerate(rows):
        rwhere = f"{where}: flow_rows rows[{ri}]"
        if not isinstance(row, dict):
            errors.append(f"{rwhere} 必须是对象（卡行或 arrow 行）")
            continue
        arrow = row.get("arrow")
        if arrow:
            if arrow not in ("down", "up"):
                errors.append(f"{rwhere} arrow 非法值 '{arrow}'（合法值：down/up）")
            if row.get("cards"):
                errors.append(f"{rwhere} 是 arrow 行，不应再有 cards")
            continue
        cards = row.get("cards")
        if not cards:
            errors.append(f"{rwhere} 既无 cards 也无 arrow（空行）")
            continue
        group = row.get("group")
        if group and group not in ("blue", "teal", "red", "gray", "none"):
            errors.append(f"{rwhere} group 非法值 '{group}'"
                          "（合法值：blue/teal/red/gray/none；R-4 起 red/gray"
                          " 供 groups 键名归位的暖色主题使用，如 gov_red）")
        style = row.get("style")
        if style and style != "dashed_opt":
            errors.append(f"{rwhere} style 非法值 '{style}'"
                          "（唯一合法值：dashed_opt；F6 虚线仅用于可选项行）")
        if not isinstance(cards, list):
            errors.append(f"{rwhere} cards 必须是列表")
            continue
        for ci, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"{rwhere}.cards[{ci}] 必须是对象")
                continue
            if not card.get("label"):
                errors.append(f"{rwhere}.cards[{ci}] 缺 label")
            role = card.get("role")
            if role and role not in declared:
                errors.append(f"{rwhere}.cards[{ci}] role '{role}' 不在 roles 声明内")
    return errors


def _validate_base_element(elem_type, elem, where):
    """7 种基础元素（text/bullets/cards/table/phases/pullquote/heading）校验。

    "有效值存在"按 _renderer.elements 的 normalize 结果判断（normalize 已做
    字段兼容：text 兼容 content|text、heading 兼容 text|title|content、
    phases 兼容 name|label|phase|title 等），与渲染层读到的一致。
    """
    errors = []
    _, normalized = _proto.normalize_element(elem)

    if elem_type == "text":
        if not normalized["content"]:
            errors.append(f"{where}: text 缺 content（或兼容字段 text）")
    elif elem_type == "bullets":
        if not normalized["items"]:
            errors.append(f"{where}: bullets 缺 items 或 items 为空列表")
    elif elem_type == "cards":
        cards = normalized["cards"]
        if not cards:
            errors.append(f"{where}: cards 缺 cards 或 cards 为空列表")
        for ci, card in enumerate(cards):
            if not card["title"]:
                errors.append(f"{where}: cards[{ci}] 缺 title")
    elif elem_type == "table":
        headers = normalized["headers"]
        if not headers:
            errors.append(f"{where}: table 缺 headers 或 headers 为空列表")
        else:
            for ri, row in enumerate(normalized["rows"]):
                if len(row) != len(headers):
                    errors.append(f"{where}: table rows[{ri}] 列数 {len(row)}"
                                  f" 与 headers 列数 {len(headers)} 不齐")
    elif elem_type == "phases":
        phases = normalized["phases"]
        if not phases:
            errors.append(f"{where}: phases 缺 phases 或 phases 为空列表")
        for qi, phase in enumerate(phases):
            if not phase["name"]:
                errors.append(f"{where}: phases[{qi}] 缺 name"
                              "（name|label|phase|title 均取不到）")
    elif elem_type == "pullquote":
        if not normalized["content"]:
            errors.append(f"{where}: pullquote 缺 content")
    elif elem_type == "heading":
        if not normalized["text"]:
            errors.append(f"{where}: heading 缺 text（或兼容字段 title|content）")
        # level 存在时须 1-7 整数（normalize 会静默钳/回退，这里显式报出）
        if "level" in elem and elem["level"] is not None:
            try:
                level = int(elem["level"])
            except (TypeError, ValueError):
                level = None
            if level is None or not 1 <= level <= 7:
                errors.append(f"{where}: heading level 须为 1-7 整数，"
                              f"实际为 {elem['level']!r}")
    # ---- v2 页面构件（§5.3）----
    elif elem_type == "hero":
        if not normalized["title"]:
            errors.append(f"{where}: hero 缺 title")
        for si, stat in enumerate(normalized["stats"]):
            if not stat["value"]:
                errors.append(f"{where}: hero.stats[{si}] 缺 value")
    elif elem_type == "section_tag":
        if not normalized["label"]:
            errors.append(f"{where}: section_tag 缺 label")
    elif elem_type == "action_title":
        if not normalized["segments"]:
            errors.append(f"{where}: action_title 缺 segments")
        for si, seg in enumerate(normalized["segments"]):
            if not seg["t"]:
                errors.append(f"{where}: action_title segments[{si}] 缺 t")
            if seg["hl"] and seg["hl"] not in _proto.HL_TONES:
                errors.append(f"{where}: action_title segments[{si}] hl 非法值"
                              f" '{seg['hl']}'（合法值：{'/'.join(_proto.HL_TONES)}）")
    elif elem_type == "stat_cards":
        if not normalized["cards"]:
            errors.append(f"{where}: stat_cards 缺 cards 或 cards 为空列表")
        for ci, card in enumerate(normalized["cards"]):
            if not card["value"]:
                errors.append(f"{where}: stat_cards.cards[{ci}] 缺 value")
            if card["tone"] and card["tone"] not in _proto.STAT_TONES:
                errors.append(f"{where}: stat_cards.cards[{ci}] tone 非法值"
                              f" '{card['tone']}'（合法值：{'/'.join(_proto.STAT_TONES)}）")
    elif elem_type == "kpi_cards":
        if not normalized["cards"]:
            errors.append(f"{where}: kpi_cards 缺 cards 或 cards 为空列表")
        for ci, card in enumerate(normalized["cards"]):
            if not card["label"]:
                errors.append(f"{where}: kpi_cards.cards[{ci}] 缺 label")
    elif elem_type == "pain_cards":
        if not normalized["cards"]:
            errors.append(f"{where}: pain_cards 缺 cards 或 cards 为空列表")
        for ci, card in enumerate(normalized["cards"]):
            if not card["title"]:
                errors.append(f"{where}: pain_cards.cards[{ci}] 缺 title")
            if card["level"] and card["level"] not in _proto.PAIN_LEVELS:
                errors.append(f"{where}: pain_cards.cards[{ci}] level 非法值"
                              f" '{card['level']}'（合法值：{'/'.join(_proto.PAIN_LEVELS)}）")
    elif elem_type == "info_cards":
        if not normalized["cards"]:
            errors.append(f"{where}: info_cards 缺 cards 或 cards 为空列表")
        for ci, card in enumerate(normalized["cards"]):
            if not card["title"]:
                errors.append(f"{where}: info_cards.cards[{ci}] 缺 title")
    elif elem_type == "legend_bar":
        if not normalized["items"]:
            errors.append(f"{where}: legend_bar 缺 items 或 items 为空列表")
        for ii, item in enumerate(normalized["items"]):
            if not item["label"]:
                errors.append(f"{where}: legend_bar.items[{ii}] 缺 label")
            if item["swatch"] and item["swatch"] not in _proto.LEGEND_SWATCHES:
                errors.append(f"{where}: legend_bar.items[{ii}] swatch 非法值"
                              f" '{item['swatch']}'"
                              f"（合法值：{'/'.join(_proto.LEGEND_SWATCHES)}）")
    elif elem_type == "qa_block":
        if not normalized["items"]:
            errors.append(f"{where}: qa_block 缺 items 或 items 为空列表")
        for ii, item in enumerate(normalized["items"]):
            if not item["q"]:
                errors.append(f"{where}: qa_block.items[{ii}] 缺 q")
    elif elem_type == "topnav":
        if not normalized["brand"]:
            errors.append(f"{where}: topnav 缺 brand")
    elif elem_type == "page_header":
        if not normalized["title"]:
            errors.append(f"{where}: page_header 缺 title")
    elif elem_type == "view_cards":
        if not normalized["cards"]:
            errors.append(f"{where}: view_cards 缺 cards 或 cards 为空列表")
        for ci, card in enumerate(normalized["cards"]):
            if not card["perspective"]:
                errors.append(f"{where}: view_cards.cards[{ci}] 缺 perspective")
    elif elem_type == "callout_block":
        if not normalized["points"]:
            errors.append(f"{where}: callout_block 缺 points 或 points 为空列表")
        for pi, pt in enumerate(normalized["points"]):
            if not pt["num"]:
                errors.append(f"{where}: callout_block.points[{pi}] 缺 num")
    # ---- v3.0 版式构件（P12/P14/P15/P16）----
    elif elem_type == "toc_cards":
        if not normalized["cards"]:
            errors.append(f"{where}: toc_cards 缺 cards 或 cards 为空列表")
        for ci, card in enumerate(normalized["cards"]):
            if not card["title"]:
                errors.append(f"{where}: toc_cards.cards[{ci}] 缺 title")
    elif elem_type == "duo_compare":
        if not normalized["left"]["points"] and not normalized["right"]["points"]:
            errors.append(f"{where}: duo_compare 左右至少一侧有 points")
        for side_key in ("left", "right"):
            tone = normalized[side_key]["tone"]
            if tone and tone not in _proto.DUO_TONES:
                errors.append(
                    f"{where}: duo_compare.{side_key}.tone 非法值 '{tone}'"
                    f"（合法值：{'/'.join(_proto.DUO_TONES)}）")
        for mi, m in enumerate(normalized["metrics"]):
            if not m["label"]:
                errors.append(f"{where}: duo_compare.metrics[{mi}] 缺 label")
    elif elem_type == "pros_cons":
        if not normalized["pros"] and not normalized["cons"]:
            errors.append(f"{where}: pros_cons pros/cons 至少一侧非空")
    elif elem_type == "cta_block":
        if not normalized["title"]:
            errors.append(f"{where}: cta_block 缺 title")
    elif elem_type == "evidence_ledger":
        items = normalized["items"]
        if not items:
            errors.append(f"{where}: evidence_ledger 缺 items 或 items 为空列表")
        for ii, item in enumerate(items):
            if not item["conclusion"]:
                errors.append(f"{where}: evidence_ledger.items[{ii}] 缺 conclusion")
            if not item["evidence"]:
                errors.append(f"{where}: evidence_ledger.items[{ii}] 缺 evidence")
    elif elem_type == "risk_register":
        items = normalized["items"]
        if not items:
            errors.append(f"{where}: risk_register 缺 items 或 items 为空列表")
        for ii, item in enumerate(items):
            if not item["risk"]:
                errors.append(f"{where}: risk_register.items[{ii}] 缺 risk")
            if item["level"] and item["level"] not in _proto.RISK_LEVELS:
                errors.append(f"{where}: risk_register.items[{ii}] level 非法值 "
                              f"'{item['level']}'（合法值：高/中/低）")
            if not item["response"]:
                errors.append(f"{where}: risk_register.items[{ii}] 缺 response")
    elif elem_type == "raci_matrix":
        if not normalized["roles"]:
            errors.append(f"{where}: raci_matrix 缺 roles 或 roles 为空列表")
        tasks = normalized["tasks"]
        if not tasks:
            errors.append(f"{where}: raci_matrix 缺 tasks 或 tasks 为空列表")
        for ti, t in enumerate(tasks):
            if not t["task"]:
                errors.append(f"{where}: raci_matrix.tasks[{ti}] 缺 task")
            for role, val in t["cells"].items():
                if val not in _proto.RACI_ENUM:
                    errors.append(f"{where}: raci_matrix.tasks[{ti}].cells[{role}] "
                                  f"非法值 '{val}'（合法值：R/A/C/I）")
                if role not in normalized["roles"]:
                    errors.append(f"{where}: raci_matrix.tasks[{ti}].cells[{role}] "
                                  f"角色不在 roles 声明内")
    elif elem_type == "decision_board":
        options = normalized["options"]
        if len(options) < 2:
            errors.append(f"{where}: decision_board 需 ≥2 个 options（方案比较）")
        for oi, opt in enumerate(options):
            if not opt["name"]:
                errors.append(f"{where}: decision_board.options[{oi}] 缺 name")
        if not normalized["recommendation"]:
            errors.append(f"{where}: decision_board 缺 recommendation")
    # ---- Step 5 新增元素 ----
    elif elem_type == "ui_mock":
        if normalized["variant"] not in _proto.UI_MOCK_VARIANTS:
            errors.append(f"{where}: ui_mock.variant 必填，合法值 "
                          f"{'/'.join(_proto.UI_MOCK_VARIANTS)}")
        if normalized["frame"] not in _proto.UI_MOCK_FRAMES:
            errors.append(f"{where}: ui_mock.frame 非法值 '{normalized['frame']}'"
                          f"（合法值：{'/'.join(_proto.UI_MOCK_FRAMES)}）")
        if not normalized["title"]:
            errors.append(f"{where}: ui_mock 缺 title")
        elif len(normalized["title"]) > UI_MOCK_TITLE_MAX:
            errors.append(f"{where}: ui_mock.title 长度 {len(normalized['title'])}"
                          f" 超过上限 {UI_MOCK_TITLE_MAX} 字")
        if not normalized["sections"]:
            errors.append(f"{where}: ui_mock 缺 sections 或 sections 为空列表")
        for si, sec in enumerate(normalized["sections"]):
            bars = sec.get("bars") or []
            if not bars:
                errors.append(f"{where}: ui_mock.sections[{si}] 缺 bars")
                continue
            if len(bars) > UI_MOCK_BARS_MAX:
                errors.append(f"{where}: ui_mock.sections[{si}] bars {len(bars)} 条"
                              f" 超过上限 {UI_MOCK_BARS_MAX}")
            for bi, b in enumerate(bars):
                if not (UI_MOCK_BAR_MIN <= int(b) <= UI_MOCK_BAR_MAX):
                    errors.append(
                        f"{where}: ui_mock.sections[{si}].bars[{bi}] 数值 {b}"
                        f" 不在 {UI_MOCK_BAR_MIN}-{UI_MOCK_BAR_MAX}")
        seal = normalized.get("seal") or {}
        if seal and normalized["variant"] != "document":
            errors.append(f"{where}: ui_mock.seal 仅 document 型可用")
        if seal:
            if seal.get("text") and len(seal["text"]) > UI_MOCK_SEAL_TEXT_MAX:
                errors.append(f"{where}: ui_mock.seal.text 长度 {len(seal['text'])}"
                              f" 超过上限 {UI_MOCK_SEAL_TEXT_MAX} 字")
            if seal.get("company") and len(seal["company"]) > UI_MOCK_SEAL_COMPANY_MAX:
                errors.append(
                    f"{where}: ui_mock.seal.company 长度 {len(seal['company'])}"
                    f" 超过上限 {UI_MOCK_SEAL_COMPANY_MAX} 字")
    elif elem_type == "conclusion_band":
        if not normalized["text"]:
            errors.append(f"{where}: conclusion_band 缺 text")
        elif len(normalized["text"]) > CONCLUSION_TEXT_MAX:
            errors.append(f"{where}: conclusion_band.text 长度 {len(normalized['text'])}"
                          f" 超过上限 {CONCLUSION_TEXT_MAX} 字")
        if normalized["tone"] not in _proto.CONCLUSION_TONES:
            errors.append(f"{where}: conclusion_band.tone 非法值 "
                          f"'{normalized['tone']}'"
                          f"（合法值：{'/'.join(_proto.CONCLUSION_TONES)}）")
    # ---- S8 Wave A 新元素 ----
    elif elem_type == "screenshot":
        if not normalized["src"]:
            errors.append(f"{where}: screenshot 缺 src")
        if normalized["alignment"] not in ("", "center", "left"):
            errors.append(f"{where}: screenshot.alignment 非法值"
                          f" '{normalized['alignment']}'（合法值：center/left）")
        for ai, ann in enumerate(normalized["annotations"]):
            if not ann["text"]:
                errors.append(f"{where}: screenshot.annotations[{ai}] 缺 text")
    elif elem_type == "raw_html":
        if not normalized["content"]:
            errors.append(f"{where}: raw_html 缺 content")
    # ---- S8 Wave B 新元素（C-E2 三件套）----
    elif elem_type == "sla_block":
        if not normalized["items"]:
            errors.append(f"{where}: sla_block 缺 items 或 items 为空列表")
        for ii, item in enumerate(normalized["items"]):
            if not item["name"]:
                errors.append(f"{where}: sla_block.items[{ii}] 缺 name")
            if not item["value"]:
                errors.append(f"{where}: sla_block.items[{ii}] 缺 value")
    elif elem_type == "profile_card":
        if not normalized["profiles"]:
            errors.append(f"{where}: profile_card 缺 profiles 或 profiles 为空列表")
        for pi, p in enumerate(normalized["profiles"]):
            if not p["name"]:
                errors.append(f"{where}: profile_card.profiles[{pi}] 缺 name")
    elif elem_type == "logo_wall":
        if not normalized["logos"]:
            errors.append(f"{where}: logo_wall 缺 logos 或 logos 为空列表")
        for li, lg in enumerate(normalized["logos"]):
            if not lg["name"]:
                errors.append(f"{where}: logo_wall.logos[{li}] 缺 name")
    return errors


def _validate_architecture_4a(elem, where):
    """architecture_4a：按 DOCX 渲染实际读取的字段校验（layers[].name）。"""
    layers = elem.get("layers")
    if not isinstance(layers, list) or not layers:
        return [f"{where}: architecture_4a 缺 layers 或 layers 为空列表"]
    errors = []
    for li, layer in enumerate(layers):
        if not isinstance(layer, dict) or not layer.get("name"):
            errors.append(f"{where}: architecture_4a layers[{li}] 缺 name")
    return errors


# 文档级容器（A-1：叙事容器，默认 scroll）
CONTAINERS = ("scroll", "chapters", "stage", "report")

# 已废弃字段：只出聚合警告，不做任何校验（Step 1 收敛）
DEPRECATED_SPEC_FIELDS = ("type_roles", "simulation")
DEPRECATED_ELEMENT_FIELD = "font_role"

# 页面级构图母板（D-122：ZSW 十二种讲法，presentation-content-design
# references/composition.md 全量枚举；多值 = 组合体写法）
COMPOSITIONS = (
    "full_claim",          # 全幅主张：单一核心主张，整页一个判断
    "editorial_columns",   # 编辑式分栏：杂志式图文穿插，叙事带证据
    "architecture_board",  # 架构板：系统分层 + 底座 + 治理栏（与 4A skill 联动）
    "evidence_ledger",     # 证据台账：结论-证据-状态逐条明细
    "flow_spine",          # 流程脊柱：阶段逐级交接，阶段门评审
    "scenario_sequence",   # 场景序列：多场景按序展开（痛点→试点→推广）
    "data_narrative",      # 数据叙事：拐点标注 + 来源 + 结论
    "product_simulation",  # 仿真产品：页面拟真为主体，讲产品
    "timeline_gantt",      # 时间线甘特：任务轨 × 里程碑 × 依赖
    "comparison_matrix",   # 对比矩阵：多方案多维度打分比较
    "decision_board",      # 决策板：方案比较 + 推荐 + 建议下一步
    "capability_graph",    # 能力图谱：核心 + 能力项的关系图谱
)


def validate_spec(spec):
    """校验整份 spec，返回错误列表（空=全部合法）。

    范围：全部元素 + 文档级 theme（v2 主题名/旧 colors 覆盖双形态）+
    style/scenario 迁移错误 + brand（v3.0 logo 槽位）+ narrative_ref
    （叙事设计单溯源指针）+ v2 spec 的 hex 防线
    + P 系版式的未知版式错误（必需构件缺失/顺序见 warning 接口）。
    """
    errors = []
    errors.extend(_validate_doc_theme(spec))
    errors.extend(_validate_doc_style_migration(spec))
    errors.extend(_validate_doc_container(spec))
    errors.extend(_validate_doc_brand(spec))
    errors.extend(_validate_doc_narrative_ref(spec))
    errors.extend(_validate_spec_hex(spec))
    for pi, page in enumerate(spec.get("pages", []) or []):
        errors.extend(validate_layout_errors(page, page_index=pi))
        errors.extend(_validate_page_questions(page, page_index=pi))
        errors.extend(_validate_page_series(page, page_index=pi))
        for ei, elem in enumerate(page.get("elements", []) or []):
            for err in validate_element(elem, index=ei):
                errors.append(f"pages[{pi}].{err}")
    return errors


def _validate_page_questions(page, page_index=None):
    """question_driven（Step 3）：页面级可选 questions 列表 [{id, text}]。"""
    qs = page.get("questions")
    if qs is None:
        return []
    where = f"pages[{page_index}]" if page_index is not None else "page"
    if not isinstance(qs, list):
        return [f"{where}: questions 必须是列表（[{'{id, text}'}, ...]）"]
    errors = []
    for qi, q in enumerate(qs):
        if not isinstance(q, dict):
            errors.append(f"{where}.questions[{qi}]: 必须是对象 {{id, text}}")
            continue
        if not isinstance(q.get("id"), str) or not q["id"]:
            errors.append(f"{where}.questions[{qi}]: id 必填字符串")
        if not isinstance(q.get("text"), str) or not q["text"]:
            errors.append(f"{where}.questions[{qi}]: text 必填字符串")
    return errors


def _validate_page_series(page, page_index=None):
    """series（Step 6）：页面级可选系列标识，须为字符串（用于同壳豁免）。"""
    series = page.get("series")
    if series is None:
        return []
    where = f"pages[{page_index}]" if page_index is not None else "page"
    if not isinstance(series, str) or not series.strip():
        return [f"{where}: series 必须是字符串（同系列页面可声明同一 id）"]
    return []


def _validate_page_composition(page, page_index=None):
    """页面级 composition 字段（D-122）：十二种构图母板枚举，多值=组合体。"""
    comp = page.get("composition")
    if comp is None:
        return []
    where = f"pages[{page_index}]" if page_index is not None else "page"
    if isinstance(comp, str):
        comp = [comp]
    if not isinstance(comp, list) or not comp:
        return [f"{where}: composition 必须是非空字符串或字符串列表"]
    errors = []
    for c in comp:
        if c not in COMPOSITIONS:
            errors.append(
                f"{where}: composition 未知母板 '{c}'（合法值：{'/'.join(COMPOSITIONS)}）")
    return errors


def _validate_doc_style_migration(spec):
    """Step 2：style / scenario 已废弃，存量 spec 报迁移错误（fail-loud）。"""
    errors = []
    style = spec.get("style")
    if style is not None:
        from _renderer.theme import LEGACY_STYLE_TO_THEME, THEMES
        mapped = LEGACY_STYLE_TO_THEME.get(str(style))
        if mapped:
            errors.append(
                f"style: {style} 已废弃，请改为 theme: {mapped}")
        else:
            legal = "/".join(sorted(THEMES))
            errors.append(
                f"style: {style} 已废弃，请改用 theme 主题名"
                f"（合法值：{legal}）")
    scenario = spec.get("scenario")
    if scenario is not None:
        errors.append(
            f"scenario: {scenario} 已废弃，请从 spec 删除；"
            "版式默认映射见 presentation-content-design")
    return errors


def _validate_doc_container(spec):
    """文档级 container 字段（A-1）：scroll（缺省）| chapters | stage | report。"""
    container = spec.get("container")
    if container is None:
        return []
    if container not in CONTAINERS:
        return [f"container: 未知容器 '{container}'（合法值：{'/'.join(CONTAINERS)}）"]
    return []


def _validate_doc_narrative_ref(spec):
    """文档级 narrative_ref（阶段 2-3，视觉生产线重构计划 §2.1）：溯源指针，
    指向 output/{客户}/ 下的叙事设计单文件名，渲染层不消费。spec 顶层字段
    无白名单（未知字段宽松放行），此处只做"若出现则须为非空字符串"的类型校验。"""
    ref = spec.get("narrative_ref")
    if ref is None:
        return []
    if not isinstance(ref, str) or not ref.strip():
        return [f"narrative_ref: 必须是叙事设计单文件名字符串，实际 {ref!r}"]
    return []


def _contains_key(obj, key):
    """递归判断 dict/list 中是否存在指定键（用于 font_role 元素级废弃字段）。"""
    if isinstance(obj, dict):
        if key in obj:
            return True
        return any(_contains_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_key(v, key) for v in obj)
    return False


def _contains_element_type(obj, elem_type):
    """递归判断 spec 中是否出现指定元素类型（第一周期 deprecated 预警）。"""
    if isinstance(obj, dict):
        if obj.get("type") == elem_type:
            return True
        return any(_contains_element_type(v, elem_type) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_element_type(v, elem_type) for v in obj)
    return False


def validate_deprecated_field_warnings(spec):
    """已废弃字段的聚合警告：type_roles / simulation / font_role。

    这些字段不再做 schema 校验，也不再参与渲染；只为存量 spec 提供一次
    warn 提示（“字段 X/Y/Z 已废弃，将被忽略”），exit code 不受影响。
    """
    present = [f for f in DEPRECATED_SPEC_FIELDS if f in (spec or {})]
    if _contains_key(spec, DEPRECATED_ELEMENT_FIELD):
        present.append(DEPRECATED_ELEMENT_FIELD)
    warnings = []
    if present:
        warnings.append(f"字段 {'/'.join(present)} 已废弃，将被忽略")
    if _contains_element_type(spec, "architecture_4a"):
        warnings.append(
            "architecture_4a 已标记 deprecated：仍按现有 DOCX 原生/HTML/PPTD 降级"
            "能力渲染，第二周期将移除元素类型；新 spec 建议改用 diagram")
    legacy = sorted({
        p.get("layout") for p in (spec or {}).get("pages", []) or []
        if isinstance(p, dict) and p.get("layout") in LEGACY_LAYOUTS
    })
    if legacy:
        warnings.append(
            f"旧 layout 值 {'/'.join(legacy)} 已废弃，将被忽略"
            "（按自由流渲染）")
    return warnings


def _validate_doc_brand(spec):
    """文档级 brand（v3.0 logo 槽位）：logo 路径禁外链，position 白名单。"""
    brand = spec.get("brand")
    if brand is None:
        return []
    if not isinstance(brand, dict):
        return ["brand: 必须是对象（logo/logo_position）"]
    errors = []
    logo = brand.get("logo")
    if logo:
        logo = str(logo)
        if logo.startswith(("http://", "https://")):
            errors.append(f"brand.logo: 禁外链（{logo}），"
                          "只允许本地资产（refs/ 或 _assets/）")
        elif not logo.startswith(("refs/", "_assets/", "assets/")):
            errors.append(f"brand.logo: 只允许本地资产路径"
                          f"（refs/ 或 _assets/），实际 {logo}")
    pos = brand.get("logo_position")
    if pos and pos not in ("topnav_left", "topnav_right", "hero_corner"):
        errors.append(f"brand.logo_position: 非法值 '{pos}'"
                      "（合法值：topnav_left/topnav_right/hero_corner）")
    return errors


def _validate_doc_theme(spec):
    """文档级 theme 字段（§5.1）：str = v2 主题包名（校验合法值）；
    dict = 旧 theme.colors 逐槽覆盖机制（不校验，行为不变）。"""
    theme = spec.get("theme")
    if theme is None or isinstance(theme, dict):
        return []
    if isinstance(theme, str):
        from _renderer.theme import THEMES  # 局部 import 防循环
        if theme not in THEMES:
            legal = "/".join(sorted(THEMES))
            return [f"theme: 未知主题 '{theme}'（合法值：{legal}）"]
        return []
    return [f"theme: 类型非法（应为主题名字符串或 colors 覆盖字典），"
            f"实际为 {type(theme).__name__}"]


def _elem_matches(elem, req):
    """版式必需构件匹配：type 字符串 / ("diagram", diagram_type) /
    ("any", [子项...]) 三种形态。"""
    if not isinstance(elem, dict):
        return False
    if isinstance(req, str):
        return elem.get("type") == req
    if req[0] == "diagram":
        return (elem.get("type") == "diagram"
                and elem.get("diagram_type") == req[1])
    if req[0] == "any":
        return any(_elem_matches(elem, sub) for sub in req[1])
    return False


def _req_label(req):
    if isinstance(req, str):
        return req
    if req[0] == "diagram":
        return f"diagram({req[1]} 系)"
    if req[0] == "any":
        return "|".join(req[1])
    return str(req)


def validate_layout_errors(page, page_index=None):
    """P 系版式错误校验：layout 合法值（error 级）。

    无 layout / layout 非 P 系 → 自由流，不校验（F9 向后兼容）。
    必需构件缺失已降为 warning，见 validate_layout_warnings。
    """
    errors = []
    if not isinstance(page, dict):
        return errors
    layout = page.get("layout")
    if not layout:
        return errors
    where = f"pages[{page_index}]" if page_index is not None else "page"
    if layout not in PAGE_LAYOUTS:
        if layout in LEGACY_LAYOUTS:
            return []  # 旧值：自由流渲染，不校验（F9）
        legal = "/".join(sorted(PAGE_LAYOUTS))
        legacy = "/".join(sorted(LEGACY_LAYOUTS))
        return [f"{where}: 未知版式 '{layout}'"
                f"（受控值：{legal}；旧值 {legacy} 继续有效按自由流渲染；"
                "不声明 layout 同为自由流）"]
    # 必需构件缺失已从 error 降为 warning（见 validate_layout_warnings），
    # 与“P01-P16 目录制 + 自由流兜底”口径一致：目录是选型指南不是硬阻断。
    return errors


def validate_layout_warnings(page, page_index=None):
    """P 系版式 warning：必需构件缺失/相对顺序 + 版式容量上限（§6/§10 检查 6）。"""
    warnings = []
    if not isinstance(page, dict):
        return warnings
    layout = page.get("layout")
    if layout not in PAGE_LAYOUTS:
        return warnings
    where = f"pages[{page_index}]" if page_index is not None else "page"
    spec = PAGE_LAYOUTS[layout]
    elements = [e for e in (page.get("elements", []) or []) if isinstance(e, dict)]

    # 必需构件缺失（warning 级）：目录制为选型指南，存量缺件自由流兜底
    for req in spec["required"]:
        if not any(_elem_matches(elem, req) for elem in elements):
            warnings.append(f"{where}: 版式 {layout}"
                            f"（{spec['name']}）缺必需构件"
                            f" {_req_label(req)}（已降级为提示）")

    # 必需构件相对顺序（§6"必需构件（顺序）"）：各构件取首次出现位置，
    # 位置序列非递增即乱序；有构件缺失时不查顺序（warning 已列出）。
    pos = []
    for req in spec["required"]:
        hit = next((i for i, e in enumerate(elements)
                    if _elem_matches(e, req)), None)
        if hit is None:
            pos = None
            break
        pos.append(hit)
    if pos is not None and pos != sorted(pos):
        warnings.append(f"{where}: 版式 {layout}（{spec['name']}）必需构件顺序"
                        "与目录约定不符（§6），请按目录表顺序排布")

    # 容量上限（warning 级）
    if spec.get("single_diagram"):
        n = sum(1 for e in elements if e.get("type") == "diagram")
        if n > 1:
            warnings.append(f"{where}: 版式 {layout}（{spec['name']}）容量上限"
                            f"为单图，实际 {n} 个 diagram，建议拆页")
    if layout == "P07":
        for ei, e in enumerate(elements):
            if e.get("type") == "table":
                rows = len(e.get("rows", []) or [])
                if rows > P07_TABLE_ROWS_WARN:
                    warnings.append(f"{where}.elements[{ei}]: P07 表格 {rows} 行"
                                    f" 超过上限 {P07_TABLE_ROWS_WARN}，建议拆分")
    if layout == "P02":
        n = sum(1 for e in elements if e.get("type") == "info_cards")
        if n > 1:
            warnings.append(f"{where}: 版式 P02（章节页）info_cards 上限 1 组，"
                            f"实际 {n} 组，建议拆页")
    return warnings


def _element_text_total(elem):
    """元素内全部字符串值的递归总长（容量检查的文本量口径）。"""
    if isinstance(elem, str):
        return len(elem)
    if isinstance(elem, dict):
        return sum(_element_text_total(v) for v in elem.values())
    if isinstance(elem, list):
        return sum(_element_text_total(v) for v in elem)
    return 0


def validate_page_warnings(page, page_index=None):
    """页面级容量检查（§七 2.5 第一级 源头限量）。

    返回警告列表（warning 级别，不进 errors 不阻断；Renderer init 收集进
    report.warnings）。触发条件：
    - 单页 elements 数 > PAGE_ELEMENTS_WARN（10，基线实测最大 9 + 余量）
    - 单元素文本总长 > ELEMENT_TEXT_WARN（1300，基线实测最大 1091 + 余量）
    """
    warnings = []
    if not isinstance(page, dict):
        return warnings
    where = f"pages[{page_index}]" if page_index is not None else "page"
    pid = page.get("id")
    label = f"{where}(id={pid})" if pid else where
    elements = page.get("elements", []) or []
    if len(elements) > PAGE_ELEMENTS_WARN:
        warnings.append(f"{label}: 单页 {len(elements)} 个元素超过上限 "
                        f"{PAGE_ELEMENTS_WARN}，建议拆页")
    for ei, elem in enumerate(elements):
        total = _element_text_total(elem)
        if total > ELEMENT_TEXT_WARN:
            warnings.append(f"{label}.elements[{ei}]: 单元素文本 {total} 字"
                            f" 超过上限 {ELEMENT_TEXT_WARN}，建议精简或拆分")

    # composition 已退出契约层（error->warning）：母板是选型知识非硬校验
    comp = page.get("composition")
    if comp is not None:
        if isinstance(comp, str):
            comp = [comp]
        if not isinstance(comp, list) or not comp:
            warnings.append(f"{label}: composition 必须是非空字符串"
                            "或字符串列表（已降级为提示）")
        else:
            for c in comp:
                if c not in COMPOSITIONS:
                    warnings.append(f"{label}: composition 未知母板 '{c}'"
                                    f"（合法值：{'/'.join(COMPOSITIONS)}；"
                                    "已降级为提示）")
    return warnings


def validate_element_warnings(elem, index=None):
    """单个 spec 元素的容量警告（warning 级别，与 errors 分离不阻断）。

    覆盖排查实测越界的数量型 subtype（阈值 = 实测越界值 -1，常量见上）：
    超阈值产出具体建议（拆为两页/两图），渲染行为不变——图照常渲染。
    cross_system 的"行数"= 单列最大步骤数（与 flow._layout_cross_system
    的行定义一致）；bct 的"组×子"= 各组 children 总数。
    graphics.md §2 预算口径（cross_system 系统列数、infra zone/节点数）
    同函数覆盖，阈值常量单一事实源在 budget_consts（经本模块 re-export）。
    """
    warnings = []
    if not isinstance(elem, dict):
        return warnings
    where = f"elements[{index}]" if index is not None else "element"

    # ---- v2 元素容量（§5.3/§6，warning 级）----
    etype = elem.get("type")
    if etype == "hero":
        n = len(elem.get("stats", []) or [])
        if n > HERO_STATS_WARN:
            warnings.append(f"{where}: hero.stats {n} 项超过上限 "
                            f"{HERO_STATS_WARN}，建议精简")
    elif etype == "kpi_cards":
        n = len(elem.get("cards", []) or [])
        if n > KPI_CARDS_WARN:
            warnings.append(f"{where}: kpi_cards {n} 卡超过上限 "
                            f"{KPI_CARDS_WARN}，建议精简")
    elif etype == "info_cards":
        n = len(elem.get("cards", []) or [])
        if n > INFO_CARDS_MAX_WARN or (n and n < INFO_CARDS_MIN_WARN):
            warnings.append(f"{where}: info_cards {n} 联不在 "
                            f"{INFO_CARDS_MIN_WARN}-{INFO_CARDS_MAX_WARN} 联区间"
                            "，建议调整")
    elif etype == "evidence_ledger":
        n = len(elem.get("items", []) or [])
        if n > EVIDENCE_LEDGER_ROWS_WARN:
            warnings.append(f"{where}: evidence_ledger {n} 条超过上限 "
                            f"{EVIDENCE_LEDGER_ROWS_WARN}，建议拆分")
    elif etype == "risk_register":
        n = len(elem.get("items", []) or [])
        if n > RISK_REGISTER_ROWS_WARN:
            warnings.append(f"{where}: risk_register {n} 条超过上限 "
                            f"{RISK_REGISTER_ROWS_WARN}，建议拆分")
    elif etype == "raci_matrix":
        n = len(elem.get("tasks", []) or [])
        if n > RACI_TASKS_WARN:
            warnings.append(f"{where}: raci_matrix {n} 行任务超过上限 "
                            f"{RACI_TASKS_WARN}，建议拆分")
    elif etype == "decision_board":
        n = len(elem.get("options", []) or [])
        if n > DECISION_OPTIONS_WARN:
            warnings.append(f"{where}: decision_board {n} 个方案超过上限 "
                            f"{DECISION_OPTIONS_WARN}，建议精简")
    elif etype == "logo_wall":
        n = len(elem.get("logos", []) or [])
        if n > LOGO_WALL_CELLS_WARN:
            warnings.append(f"{where}: logo_wall {n} 格超过上限 "
                            f"{LOGO_WALL_CELLS_WARN}，建议精简")
    elif etype == "pain_cards":
        n = len(elem.get("cards", []) or [])
        if n > PAIN_CARDS_WARN:
            warnings.append(f"{where}: pain_cards {n} 卡超过上限 "
                            f"{PAIN_CARDS_WARN}，建议拆页")

    if elem.get("type") != "diagram":
        return warnings
    dt = elem.get("diagram_type", "")
    st = elem.get("subtype", "")

    # flow_rows（§5.4）：行数/行卡阈值 + dashed_opt 行内 badge（F6 可选项不编号）
    if st == "flow_rows":
        rows = elem.get("rows", []) or []
        if len(rows) > FLOW_ROWS_TOTAL_WARN:
            warnings.append(f"{where}: flow/flow_rows 行数 {len(rows)} 超过容量上限"
                            f" {FLOW_ROWS_TOTAL_WARN}，单页排版会越界，建议拆为两图")
        for ri, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            cards = row.get("cards", []) or []
            if len(cards) > FLOW_ROWS_CARDS_WARN:
                warnings.append(f"{where}: flow/flow_rows rows[{ri}] 卡数 "
                                f"{len(cards)} 超过上限 {FLOW_ROWS_CARDS_WARN}，建议拆行")
            if row.get("style") == "dashed_opt":
                for ci, card in enumerate(cards):
                    if isinstance(card, dict) and card.get("badge"):
                        warnings.append(f"{where}: flow/flow_rows rows[{ri}].cards[{ci}]"
                                        " 在 dashed_opt 可选项行内带 badge"
                                        "（F6：可选项不编号）")

    def _over(what, n, limit):
        warnings.append(f"{where}: {dt}/{st} {what} {n} 超过容量上限 {limit}"
                        f"，单页排版会越界/互压，建议拆为两页/两图")

    if st == "swimlane":
        lanes = elem.get("lanes") or []
        if not lanes:  # 渲染层会从 steps 派生泳道（flow._layout_swimlane）
            lanes = sorted({s.get("lane", "") for s in elem.get("steps", []) or []
                            if s.get("lane")})
        if len(lanes) > SWIMLANE_LANES_WARN:
            _over("泳道", len(lanes), SWIMLANE_LANES_WARN)
    elif st == "cross_system":
        systems = [s.get("name", "") for s in elem.get("systems", []) or []]
        steps = elem.get("steps", []) or []
        if not systems:
            systems = sorted({s.get("system", "") for s in steps if s.get("system")})
        if len(systems) > CROSS_SYSTEM_SYSTEMS_WARN:
            _over("系统列", len(systems), CROSS_SYSTEM_SYSTEMS_WARN)
        rows = 0
        for name in systems:
            rows = max(rows, sum(1 for s in steps
                                 if s.get("system", systems[0] if systems else "") == name))
        if rows > CROSS_SYSTEM_ROWS_WARN:
            _over("单列行数", rows, CROSS_SYSTEM_ROWS_WARN)
    elif st == "infra":
        zones = [z for z in (elem.get("zones") or []) if isinstance(z, dict)]
        if len(zones) > INFRA_ZONES_WARN:
            _over("zone", len(zones), INFRA_ZONES_WARN)
        for zi, zone in enumerate(zones):
            nodes = zone.get("nodes") or []
            if len(nodes) > INFRA_ZONE_NODES_WARN:
                _over(f"zones[{zi}] 节点", len(nodes), INFRA_ZONE_NODES_WARN)
    elif st == "decision":
        n = len(elem.get("steps", []) or [])
        if n > DECISION_STEPS_WARN:
            _over("步数", n, DECISION_STEPS_WARN)
    elif dt == "timeline" and st == "vertical":
        n = len(elem.get("milestones", []) or [])
        if n > TIMELINE_VERTICAL_CARDS_WARN:
            _over("里程碑卡", n, TIMELINE_VERTICAL_CARDS_WARN)
    elif dt == "timeline" and st == "horizontal":
        n = len(elem.get("milestones", []) or [])
        if n > TIMELINE_HORIZONTAL_CARDS_WARN:
            _over("里程碑卡", n, TIMELINE_HORIZONTAL_CARDS_WARN)
    elif dt == "timeline" and st == "milestone_gantt":
        n = len(elem.get("tasks", []) or [])
        if n > MSG_TASKS_WARN:
            _over("任务", n, MSG_TASKS_WARN)
    elif st == "capability_map":
        n = len(elem.get("sections", []) or [])
        if n > CAPABILITY_MAP_SECTIONS_WARN:
            _over("section", n, CAPABILITY_MAP_SECTIONS_WARN)
    elif st == "biz_capability_tree":
        n = sum(len(g.get("children", []) or []) for g in elem.get("groups", []) or [])
        if n > BCT_CHILDREN_WARN:
            _over("子项总数（组×子）", n, BCT_CHILDREN_WARN)
    return warnings
