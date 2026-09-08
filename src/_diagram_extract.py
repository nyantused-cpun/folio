# -*- coding: utf-8 -*-
"""大纲 role → diagram 的映射表、gold 示范注入与宽容校验器群（S1 拆分自 _outline_to_spec.py）。

职责：
  - role 表：ROLE_LAYOUT / ROLE_ELEMENT_KIND / ARCH_ROLES / ROLE_DIAGRAM_SPEC
    （+ 兼容别名 ROLE_DIAGRAM）/ ROLE_DIAGRAM_PROMPTS
  - gold 注入：GOLD_SPECS_DIR / GOLD_DEMO_MAX_TOKENS / load_gold_demo /
    _gold_demo_block（token 截断与注释剥除）
  - 宽容校验器群：_valid_*（LLM 结构化字段非法→None，调用方回退 text/cards）+
    _diagram_data_from_result 分发
纯数据与纯函数，无 CLI 编排；主流程与 LLM 提取缓存仍在 _outline_to_spec.py。
"""
import os

# SCRIPT_DIR 事实源：_paths（B4-G5 收拢，值语义不变）
from _paths import SCRIPT_DIR

# role → 页面版式（spec.yml 的 layout 字段，v3.0 P 系目录见 schema.PAGE_LAYOUTS）。
# §3-6（2026-09-03）：21 个旧版式值迁移 P01-P16；layout 只是页面版式字段，
# 元素构造改由 build_elements 按 role（ROLE_ELEMENT_KIND）决定，两者解耦；
# LEGACY_LAYOUTS 保留只读兼容。
# 批6（2026-09-05，C17）：requirement/scope/terms 三处旧值债清零（全部迁受控
# 版式，理由逐条见行内注释）；gap_analysis/roadmap/governance 补键（M3 欠账），
# gap_analysis 指向本批新增 P17 差距矩阵页（扩目录决策，decisions.md 在案）。
ROLE_LAYOUT = {
    "pain_points": "P04",        # 痛点矩阵页（原 cards_3 卡片）
    "goals": "P03",              # 结论摘要页：目标+关键指标（原 title_body）
    "blueprint": "P06",          # 架构图页：layered diagram（原 tree）
    "function_architecture": "P06",  # 同上（原 tree）
    "tech_architecture": "P06",      # 同上（原 tree）
    "implementation": "P09",     # 路线图页：timeline diagram（原 phases）
    "value": "P03",              # 结论摘要页：量化收益（原 title_body）
    "next_steps": "P11",         # 收尾页（原 summary）
    "requirement": "P03",        # 结论摘要页：背景+核心需求+范围边界（批6，原
                                 # title_body；摘要非清单——outline prompt 要求"每条
                                 # 一句话不展开"，故不取 P07 表格；缺 kpi 仅 warning）
    "solution_overview": "P08",  # 能力地图页：cbm diagram（原 title_body）
    "core_functions": "P05",     # 流程图页：cross_system diagram（原 table；
                                 # diagram 优先，回退 table 时缺图仅 warning）
    "service": "P11",            # 收尾页：服务保障（原 title_body）
    "overview": "P03",           # 结论摘要页：项目概况定性+量化（原 title_body）
    "progress": "P07",           # 对比表页：计划 vs 实际（原 table）
    "issues": "P10",             # 风险与待确认页（原 cards_3）
    "decisions": "P10",          # 风险与待确认页：待决策事项（原 cards_3）
    "scope": "P14",              # 双栏对比页：范围内/外（批6，原 title_body；
                                 # outline children 显式含"覆盖范围/不包含内容"）
    "pricing": "P07",            # 对比表页：报价表（原 table）
    "payment": "P07",            # 对比表页：付款计划表（原 title_body）
    "terms": "P07",              # 对比表页：商务条款=条款×内容表（批6，原
                                 # title_body；elements 仍 bullets 回退，缺 table
                                 # 仅 warning——同 core_functions 回退先例）
    "value_added": "P03",        # 结论摘要页：增值收益（原 cards_3）
    # M1（2026-09-04）扩映射配套版式：
    "integration": "P06",        # 架构图页：integration 集成图（M1 新增）
    "infrastructure": "P06",     # 架构图页：infra 基础设施拓扑（M1）
    "capabilities": "P08",       # 能力地图页：capability_map（M1）
    "data_ownership": "P07",     # 对比表页：crud 矩阵，回退 table（M1）
    "swimlane": "P05",           # 流程图页：泳道协同流程，回退 table（M1）
    "schedule": "P09",           # 路线图页：module_gantt，回退 phases（M1）
    "decision_flow": "P05",      # 流程图页：decision 分支流程，回退 table（M1）
    # 批6（2026-09-05，C17）补 M3 欠账三键：
    "gap_analysis": "P17",       # 差距矩阵页：fit_gap 差距二维矩阵（批6 新增版式）
    "roadmap": "P09",            # 路线图页：timeline/horizontal（同 implementation）
    "governance": "P07",         # 对比表页：raci 责任矩阵本质表格（同 M1
                                 # data_ownership crud→P07 先例）
    # data_flow 不设 layout 键：relationship 族无对应 P 码（P06 仅认 architecture），
    # 保持 P03 默认兜底——与 current_state 同类（current_state 本批未补键，
    # flow/cross_system→P05 候选，留后续批次评估）
}

# role → 元素构造形态（§3-6 解耦：build_elements 按 role 构造元素，不再按
# layout 字符串分支；形态与迁移前旧 layout 分支一一对应，行为零变化）。
# 未列出的 role 走默认 text+bullets（原 title_body 分支）。
ROLE_ELEMENT_KIND = {
    "pain_points": "cards",      # 原 cards_3 分支
    "issues": "cards",
    "decisions": "cards",
    "value_added": "cards",
    "blueprint": "layered",      # 原 tree 分支（layers 走 diagram 优先路径）
    "function_architecture": "layered",
    "tech_architecture": "layered",
    "implementation": "phases",  # 原 phases 分支
    "core_functions": "table",   # 原 table 分支
    "progress": "table",
    "pricing": "table",
    "terms": "bullets",          # 原 bullets 分支
    # M1（2026-09-04）扩映射配套回退形态；capabilities/data_flow 不加→title_body
    # 回退（同 solution_overview 先例）：
    "integration": "layered",     # M1：集成图回退 text+cards（同架构类）
    "infrastructure": "layered",  # M1：同上
    "data_ownership": "table",    # M1：crud 回退表格（P07 配套，同 core_functions）
    "swimlane": "table",          # M1：泳道回退表格（P05 配套）
    "schedule": "phases",         # M1：排期回退阶段（P09 配套，同 implementation）
    "decision_flow": "table",     # M1：决策流回退表格（P05 配套）
    # 批6（2026-09-05，C17）补 M3 欠账：governance 版式映射 P07（raci 本质
    # 表格），diagram 校验不过时的回退页须有 P07 必需的 table 构件——
    # 原缺键走 title_body 默认（text+bullets），同 data_ownership crud→P07 先例
    "governance": "table",
}
# 架构类 role：LLM 提取时追加 layers 结构化要求，build_elements 产 diagram（§七 2.7）
ARCH_ROLES = {"blueprint", "function_architecture", "tech_architecture"}

# Gold spec 示范库（§8 v1.2 候选 4 三层示范库）：每种 diagram subtype 1 个
# 验收过的 spec 片段，由 _tools/extract_gold_specs.py 从已验收产出切片生成
GOLD_SPECS_DIR = os.path.join(SCRIPT_DIR, "_knowledge", "templates", "gold_specs")
# 每种示范注入截断到 ~500 tokens（3-5 种 ≈ 2k/单，替代 ~23k 目检）
GOLD_DEMO_MAX_TOKENS = 500

# role → 本章节将产出的 diagram（build_elements 的实际产出），gold 示范按此召回。
# 让“流程/架构/矩阵/时间线/责任”类内容不再默认退化成 text/table/cards。
ROLE_DIAGRAM_SPEC = {
    # 架构类：分层架构图（沿用原 ARCH_ROLES 行为）
    "blueprint": {
        "diagram_type": "architecture", "subtype": "layered",
        "gold": ("architecture", "layered"),
    },
    "function_architecture": {
        "diagram_type": "architecture", "subtype": "layered",
        "gold": ("architecture", "layered"),
    },
    "tech_architecture": {
        "diagram_type": "architecture", "subtype": "layered",
        "gold": ("architecture", "layered"),
    },
    # 规划类：差距二维矩阵
    "gap_analysis": {
        "diagram_type": "matrix", "subtype": "fit_gap",
        "gold": ("matrix", "fit_gap"),
    },
    # 实施/演进/进展：时间线
    "implementation": {
        "diagram_type": "timeline", "subtype": "horizontal",
        "gold": ("timeline", "horizontal"),
    },
    "roadmap": {
        "diagram_type": "timeline", "subtype": "horizontal",
        "gold": ("timeline", "horizontal"),
    },
    "progress": {
        "diagram_type": "timeline", "subtype": "horizontal",
        "gold": ("timeline", "horizontal"),
    },
    # 业务断点/现状/核心流程：跨系统流程图
    "current_state": {
        "diagram_type": "flow", "subtype": "cross_system",
        "gold": ("flow", "cross_system"),
    },
    "pain_points": {
        "diagram_type": "flow", "subtype": "cross_system",
        "gold": ("flow", "cross_system"),
    },
    "core_functions": {
        "diagram_type": "flow", "subtype": "cross_system",
        "gold": ("flow", "cross_system"),
    },
    # 治理/责任：RACI 矩阵
    # 排查结论（§3-4）：键名与 outline role 逐字符一致，无归一问题；raci 从未
    # 出场的根因是「整体信息化规划」大纲把 governance 段注释为可选（默认不出），
    # 唯一引用它的「架构图」场景走 architecture-diagram-builder 重轨。
    "governance": {
        "diagram_type": "matrix", "subtype": "raci",
        "gold": ("matrix", "raci"),
    },
    # 方案总览：CBM 能力组件地图（能力分层 × 建设热度；gold matrix__cbm.yml）
    "solution_overview": {
        "diagram_type": "matrix", "subtype": "cbm",
        "gold": ("matrix", "cbm"),
    },
    # 问题与风险：影响×紧急 四象限（gold matrix__quadrant.yml）
    "issues": {
        "diagram_type": "matrix", "subtype": "quadrant",
        "gold": ("matrix", "quadrant"),
    },
    # 价值与收益：价值链主链+支撑链（gold relationship__value_chain.yml）
    "value": {
        "diagram_type": "relationship", "subtype": "value_chain",
        "gold": ("relationship", "value_chain"),
    },
    # 服务保障：服务组织树（gold relationship__org_tree.yml）
    "service": {
        "diagram_type": "relationship", "subtype": "org_tree",
        "gold": ("relationship", "org_tree"),
    },
    # ── M1（2026-09-04）扩映射 +8：distinct subtype 9→17 ──
    # 系统集成/接口集成：总线或点对点集成图（gold architecture__integration.yml；M1）
    "integration": {
        "diagram_type": "architecture", "subtype": "integration",
        "gold": ("architecture", "integration"),
    },
    # IT 基础设施/部署拓扑：分区图标拓扑（gold architecture__infra.yml；M1）
    "infrastructure": {
        "diagram_type": "architecture", "subtype": "infra",
        "gold": ("architecture", "infra"),
    },
    # 业务能力盘点/能力地图：分层点亮（gold matrix__capability_map.yml；M1）
    "capabilities": {
        "diagram_type": "matrix", "subtype": "capability_map",
        "gold": ("matrix", "capability_map"),
    },
    # 数据与单据权责：单据×实体 CRUD 矩阵（gold matrix__crud.yml；M1）
    "data_ownership": {
        "diagram_type": "matrix", "subtype": "crud",
        "gold": ("matrix", "crud"),
    },
    # 跨角色/跨系统泳道协同流程（gold flow__swimlane.yml；M1）
    "swimlane": {
        "diagram_type": "flow", "subtype": "swimlane",
        "gold": ("flow", "swimlane"),
    },
    # 分模块排期：域×季度网格甘特（gold timeline__module_gantt.yml；M1）
    "schedule": {
        "diagram_type": "timeline", "subtype": "module_gantt",
        "gold": ("timeline", "module_gantt"),
    },
    # 数据流向/数据架构（gold relationship__data_flow.yml；M1）
    "data_flow": {
        "diagram_type": "relationship", "subtype": "data_flow",
        "gold": ("relationship", "data_flow"),
    },
    # 审批/决策分支流程（gold flow__decision.yml；M1）。
    # 注意区分：decisions=待决策清单（保持 P10/cards 不挂图），decision_flow=真流程
    "decision_flow": {
        "diagram_type": "flow", "subtype": "decision",
        "gold": ("flow", "decision"),
    },
}

# 兼容旧引用：ARCH_ROLES 仍保留为架构类子集；ROLE_DIAGRAM 保留兼容别名
ROLE_DIAGRAM = {role: (spec["diagram_type"], spec["subtype"])
                for role, spec in ROLE_DIAGRAM_SPEC.items()}

# 各 diagram role 的 LLM 结构化提取要求（追加在提取 prompt 后；max_tokens 同架构类）
ROLE_DIAGRAM_PROMPTS = {
    "gap_analysis": """
【图形化附加要求】本章节是差距分析。除上述字段外，JSON 需额外包含：
"requirements": ["建设目标/需求项1", "建设目标/需求项2"],
"products": ["当前 IT 水平/方案/产品名称"],
"cells": [
  {"req": "建设目标1", "product": "当前 IT 水平",
   "match": "fit|partial|gap", "note": "一句话说明"}
]""",
    "implementation": """
【图形化附加要求】本章节是实施/演进路径。除上述字段外，JSON 需额外包含：
"milestones": [
  {"label": "阶段名", "date": "周期/日期", "desc": "可签认交付物"}
]""",
    "roadmap": """
【图形化附加要求】本章节是演进路线。除上述字段外，JSON 需额外包含：
"milestones": [
  {"label": "阶段/项目名", "date": "周期/日期", "desc": "阶段门或可签认交付物"}
]""",
    "progress": """
【图形化附加要求】本章节是进展与里程碑。除上述字段外，JSON 需额外包含：
"milestones": [
  {"label": "里程碑名", "date": "计划/实际", "desc": "量化成果或偏差"}
]""",
    "current_state": """
【图形化附加要求】本章节是现状与断点。除上述字段外，JSON 需额外包含：
"systems": [{"name": "系统/角色名"}],
"steps": [
  {"label": "① 动作", "system": "系统/角色名", "note": "接口/单据", "async": false}
]""",
    "pain_points": """
【图形化附加要求】本章节是现状痛点与流程断点。除上述字段外，JSON 需额外包含：
"systems": [{"name": "系统/角色名"}],
"steps": [
  {"label": "① 动作", "system": "系统/角色名", "note": "断点说明", "async": false}
]""",
    "core_functions": """
【图形化附加要求】本章节是核心流程。除上述字段外，JSON 需额外包含：
"systems": [{"name": "系统/角色名"}],
"steps": [
  {"label": "① 动作", "system": "系统/角色名", "note": "交互/单据", "async": false}
]""",
    "governance": """
【图形化附加要求】本章节是治理/责任矩阵。除上述字段外，JSON 需额外包含：
"roles": ["甲方项目经理", "我方PM", "我方顾问"],
"tasks": [
  {"name": "任务名",
   "assignments": [
     {"role": "甲方项目经理", "type": "A"},
     {"role": "我方PM", "type": "R"},
     {"role": "我方顾问", "type": "C"}
   ]}
]""",
    "solution_overview": """
【图形化附加要求】本章节是方案总览（能力组件地图）。除上述字段外，JSON 需额外包含：
"rows": [{"level": "能力层级（决策战略/管理运营/执行支撑）",
  "capabilities": [{"name": "能力名", "heat": "strong|mid|weak"}]}]""",
    "issues": """
【图形化附加要求】本章节是问题与风险（四象限分级）。除上述字段外，JSON 需额外包含：
"axes": {"x": "横轴（如 紧急度）", "y": "纵轴（如 影响面）"},
"quads": [{"title": "象限名", "items": ["问题/风险1", "问题/风险2"]}]（固定 4 象限）""",
    "value": """
【图形化附加要求】本章节是价值与收益（价值链）。除上述字段外，JSON 需额外包含：
"primary": ["主价值链环节（收益落点）"],
"support": ["支撑链环节"]""",
    "service": """
【图形化附加要求】本章节是服务保障（服务组织树）。除上述字段外，JSON 需额外包含：
"root": {"name": "服务总协调", "desc": "职责",
  "children": [{"name": "服务组/岗位", "desc": "职责"}]}""",
    # ── M1（2026-09-04）扩映射配套提取要求 ──
    "integration": """
【图形化附加要求】本章节是系统集成/接口集成。除上述字段外，JSON 需额外包含（总线形态）：
"hub": {"name": "集成平台/ESB 名称", "desc": "平台能力一句话"},
"systems": [{"name": "系统名（接口/单据/协议）"}]
（材料只体现两系统点对点时可用："source": "源系统", "target": "目标系统"；不足返回 []）""",
    "infrastructure": """
【图形化附加要求】本章节是 IT 基础设施/部署拓扑。除上述字段外，JSON 需额外包含：
"zones": [{"name": "分区（用户接入/安全/应用/数据/运维）",
  "nodes": [{"name": "节点名", "desc": "配置/规格口径",
             "icon": "terminal|cloud|firewall|lb|container|db|monitor"}]}],
"links": [{"from": "分区.节点", "to": "分区.节点", "mode": "sync|async"}]""",
    "capabilities": """
【图形化附加要求】本章节是业务能力盘点/能力地图。除上述字段外，JSON 需额外包含：
"sections": [{"name": "能力层名",
  "capabilities": [{"name": "能力名", "status": "lit|partial|none",
    "system": "承载系统", "items": [{"name": "子能力", "status": "lit|partial|none"}]}]}]""",
    "data_ownership": """
【图形化附加要求】本章节是数据与单据权责。除上述字段外，JSON 需额外包含：
"docs": ["单据/业务对象"],
"entities": ["数据实体/主数据"],
"cells": [{"doc": "单据名", "entity": "实体名", "ops": ["C", "R", "U", "D"]}]""",
    "swimlane": """
【图形化附加要求】本章节是跨角色/跨系统泳道协同流程。除上述字段外，JSON 需额外包含：
"lanes": [{"name": "泳道（岗位/系统）"}],
"steps": [{"label": "步骤", "lane": "所属泳道", "desc": "说明", "type": "doc|system"}]""",
    "schedule": """
【图形化附加要求】本章节是分模块排期。除上述字段外，JSON 需额外包含：
"columns": ["Q1", "Q2", "Q3", "Q4"],
"groups": [{"name": "业务域", "sub": "域口径一句话", "tone": "blue|teal|purple",
  "modules": [{"label": "01 模块名", "col": 0}]}],
"markers": [{"col": 1, "label": "里程碑", "note": "说明"}]""",
    "data_flow": """
【图形化附加要求】本章节是数据流向/数据架构。除上述字段外，JSON 需额外包含：
"nodes": [{"name": "系统/节点", "type": "source|process|store"}],
"flows": [{"from": "源节点", "to": "目标节点", "data": "流动的数据内容",
  "direction": "push|pull|bidirectional"}]""",
    "decision_flow": """
【图形化附加要求】本章节是审批/决策分支流程。除上述字段外，JSON 需额外包含：
"steps": [
  {"label": "步骤", "type": "decision|system|end",
   "alt_next": "分支去向步骤名", "alt_label": "分支条件（否/超限）"}
]""",
}


def _est_tokens(text):
    """粗估 token 数（偏保守上界）：CJK 1 字 ≈ 1 token，ASCII ~4 字符 ≈ 1 token。"""
    cjk = sum(1 for ch in text if ord(ch) >= 0x2E80)
    return cjk + (len(text) - cjk) // 4 + 1


def _truncate_to_tokens(text, max_tokens):
    """按行截断到 token 预算内（不切断行），超预算时追加截断标注。"""
    if _est_tokens(text) <= max_tokens:
        return text
    kept, budget = [], 0
    for line in text.splitlines():
        t = _est_tokens(line)
        if budget + t > max_tokens:
            break
        kept.append(line)
        budget += t
    return "\n".join(kept) + "\n# …（超出示范 token 预算，余下截断）"


def load_gold_demo(diagram_type, subtype, max_tokens=GOLD_DEMO_MAX_TOKENS):
    """读 gold spec 示范片段并截断到 token 预算；无对应 gold 返回 None（不注入）。

    先剥 `#` 注释行：gold 文件头注释含验收来源（内部路径/客户名），
    不能泄进其他客户的 prompt，且省 token。
    """
    path = os.path.join(GOLD_SPECS_DIR, f"{diagram_type}__{subtype}.yml")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return _truncate_to_tokens(_strip_comment_lines(f.read()), max_tokens)


def _strip_comment_lines(text):
    """剥掉 `#` 注释行（行首/缩进后以 # 开头的 yaml 注释），保留内容行。"""
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def _gold_demo_block(section, gold_override=None):
    """本章节将产 diagram 时返回写法示范注入块，否则返回 ""。

    §3 前缀稳定性：注入块拼在静态 system 段之后、【本章节任务】之前
    （与 evidence 同区），静态前缀逐字节不变。

    gold_override（"族/subtype"，叙事设计单 page_map 项的 graphic 意图）
    优先于 role → gold 的默认映射：设计单显式指定了该页的图形形态时，
    按指定 族/subtype 注入对应 gold 示范（条目 2-2）。
    """
    if gold_override:
        parts = str(gold_override).split("/", 1)
        target = (parts[0], parts[1]) if len(parts) == 2 else None
    else:
        spec = ROLE_DIAGRAM_SPEC.get(section.get("role", ""))
        target = spec.get("gold") if spec else None
    if not target:
        return ""
    demo = load_gold_demo(*target)
    if not demo:
        return ""
    return ("\n【写法示范】以下为验收过的 gold spec 片段，模仿其字段结构和信息密度，"
            "不要抄内容：\n" + demo + "\n")


def _valid_layers(result):
    """宽容校验 LLM 返回的 layers 字段。

    合法（list、每项有 name 和 components list、组件非空）→ 返回规范化列表；
    缺失或结构不对 → 返回 None（调用方回退 text+cards，不报错）。
    """
    layers = result.get("layers")
    if not isinstance(layers, list) or not layers:
        return None
    cleaned = []
    for item in layers:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        components = item.get("components")
        if not name or not isinstance(components, list) or not components:
            return None
        cleaned.append({
            "name": str(name),
            "desc": str(item.get("desc") or ""),
            "components": [str(c) for c in components],
        })
    return cleaned


def _valid_fit_gap(result):
    """宽容校验 fit_gap 结构化字段；非法返回 None（调用方回退 text+cards）。"""
    requirements = result.get("requirements")
    products = result.get("products")
    cells = result.get("cells")
    if (not isinstance(requirements, list) or not requirements
            or not isinstance(products, list) or not products
            or not isinstance(cells, list) or not cells):
        return None
    reqs = [str(r) for r in requirements if str(r).strip()]
    prods = [str(p) for p in products if str(p).strip()]
    if not reqs or not prods:
        return None
    norm_cells = []
    for c in cells:
        if not isinstance(c, dict):
            return None
        if not c.get("req") or not c.get("product"):
            return None
        match = c.get("match")
        if match not in ("fit", "partial", "gap"):
            return None
        norm_cells.append({
            "req": str(c["req"]),
            "product": str(c["product"]),
            "match": match,
            "note": str(c.get("note") or ""),
        })
    return {"requirements": reqs, "products": prods, "cells": norm_cells}


def _valid_milestones(result):
    """宽容校验 timeline/horizontal 的 milestones 字段。"""
    milestones = result.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        return None
    norm = []
    for m in milestones:
        if not isinstance(m, dict) or not m.get("label"):
            return None
        norm.append({
            "label": str(m["label"]),
            "date": str(m.get("date") or ""),
            "desc": str(m.get("desc") or ""),
        })
    return {"milestones": norm}


def _valid_cross_system(result):
    """宽容校验 flow/cross_system 的 systems + steps 字段。"""
    systems = result.get("systems")
    steps = result.get("steps")
    if (not isinstance(systems, list) or not systems
            or not isinstance(steps, list) or not steps):
        return None
    norm_systems = []
    for s in systems:
        if isinstance(s, str):
            norm_systems.append({"name": s})
        elif isinstance(s, dict) and s.get("name"):
            norm_systems.append({"name": str(s["name"])})
        else:
            return None
    if not norm_systems:
        return None
    norm_steps = []
    for st in steps:
        if not isinstance(st, dict) or not st.get("label"):
            return None
        norm_steps.append({
            "label": str(st["label"]),
            "system": str(st.get("system") or ""),
            "note": str(st.get("note") or ""),
            "async": bool(st.get("async", False)),
        })
    return {"systems": norm_systems, "steps": norm_steps}


def _valid_raci(result):
    """宽容校验 matrix/raci 的 roles + tasks（assignments）字段。"""
    roles = result.get("roles")
    tasks = result.get("tasks")
    if (not isinstance(roles, list) or not roles
            or not isinstance(tasks, list) or not tasks):
        return None
    norm_roles = [str(r) for r in roles if str(r).strip()]
    if not norm_roles:
        return None
    norm_tasks = []
    for t in tasks:
        if not isinstance(t, dict) or not t.get("name"):
            return None
        assignments = t.get("assignments")
        if not isinstance(assignments, list) or not assignments:
            return None
        norm_assignments = []
        for a in assignments:
            if not isinstance(a, dict) or not a.get("role"):
                return None
            atype = a.get("type")
            if atype not in ("R", "A", "C", "I"):
                return None
            norm_assignments.append({
                "role": str(a["role"]),
                "type": atype,
            })
        if not norm_assignments:
            return None
        norm_tasks.append({
            "name": str(t["name"]),
            "assignments": norm_assignments,
        })
    return {"roles": norm_roles, "tasks": norm_tasks}


def _valid_org_tree(result):
    """宽容校验 relationship/org_tree 的 root 递归树（节点 name 必填）。"""
    def _node(n):
        if not isinstance(n, dict) or not n.get("name"):
            return None
        node = {"name": str(n["name"]), "desc": str(n.get("desc") or "")}
        children = n.get("children")
        if isinstance(children, list) and children:
            kids = [_node(c) for c in children]
            if any(k is None for k in kids):
                return None
            node["children"] = kids
        return node
    root = _node(result.get("root"))
    return {"root": root} if root else None


def _valid_value_chain(result):
    """宽容校验 relationship/value_chain 的 primary/support 环节列表。"""
    primary = result.get("primary")
    if not isinstance(primary, list):
        return None
    primary = [str(p) for p in primary if str(p).strip()]
    if not primary:
        return None
    support = result.get("support")
    support = ([str(s) for s in support if str(s).strip()]
               if isinstance(support, list) else [])
    return {"primary": primary, "support": support}


def _valid_cbm(result):
    """宽容校验 matrix/cbm 的 rows（level + capabilities；heat 限 strong/mid/weak）。"""
    rows = result.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    norm = []
    for r in rows:
        # isinstance 参与控制流（P1-13）：LLM 混入字符串/null 时拒绝而非裸崩
        if not isinstance(r, dict) or not r.get("level"):
            return None
        caps = r.get("capabilities")
        if not isinstance(caps, list) or not caps:
            return None
        norm_caps = []
        for c in caps:
            if isinstance(c, str) and c.strip():
                norm_caps.append({"name": c})
            elif isinstance(c, dict) and c.get("name"):
                heat = c.get("heat")
                norm_caps.append({"name": str(c["name"]), "heat": heat
                                  if heat in ("strong", "mid", "weak") else ""})
            else:
                return None
        norm.append({"level": str(r["level"]), "capabilities": norm_caps})
    return {"rows": norm}


def _valid_quadrant(result):
    """宽容校验 matrix/quadrant 的 axes + quads（恰好 4 象限，对齐 schema
    QUADRANT_QUADS=4 硬校验——1-3/5+ 象限放行会 verify FAIL 阻断交付）。"""
    axes = result.get("axes")
    quads = result.get("quads")
    if (not isinstance(axes, dict) or not isinstance(quads, list)
            or len(quads) != 4):
        return None
    norm = []
    for q in quads:
        if not isinstance(q, dict) or not q.get("title"):
            return None
        items = q.get("items")
        norm.append({"title": str(q["title"]),
                     "items": [str(i) for i in items] if isinstance(items, list) else []})
    return {"axes": {"x": str(axes.get("x") or ""), "y": str(axes.get("y") or "")},
            "quads": norm}


def _diagram_data_from_result(diagram_spec, result):
    """按角色期望的 subtype 从 LLM 结果提取合法 diagram 数据；不合法返回 None。"""
    subtype = diagram_spec["subtype"]
    if subtype == "layered":
        layers = _valid_layers(result)
        return {"layers": layers} if layers is not None else None
    if subtype == "fit_gap":
        return _valid_fit_gap(result)
    if subtype == "horizontal":
        return _valid_milestones(result)
    if subtype == "cross_system":
        return _valid_cross_system(result)
    if subtype == "raci":
        return _valid_raci(result)
    if subtype == "org_tree":
        return _valid_org_tree(result)
    if subtype == "value_chain":
        return _valid_value_chain(result)
    if subtype == "cbm":
        return _valid_cbm(result)
    if subtype == "quadrant":
        return _valid_quadrant(result)
    # ── M1（2026-09-04）扩映射分发分支 ──
    if subtype == "integration":
        return _valid_integration(result)
    if subtype == "infra":
        return _valid_infra(result)
    if subtype == "capability_map":
        return _valid_capability_map(result)
    if subtype == "crud":
        return _valid_crud(result)
    if subtype == "swimlane":
        return _valid_swimlane(result)
    if subtype == "module_gantt":
        return _valid_module_gantt(result)
    if subtype == "data_flow":
        return _valid_data_flow(result)
    if subtype == "decision":
        return _valid_decision(result)
    return None


def diagram_result_cacheable(section, result):
    """提取缓存写入门（P1-13 fail-closed）：图形 role 的结构化字段校验不过
    → 不得入缓存（重跑可重试自愈）。畸形结果曾先入 llm_extract_cache、
    后在 build_elements 才校验，重跑命中同缓存导致修复后仍无法自愈。

    调用方接线（_outline_to_spec.extract_section_content 缓存写入处）：
        if diagram_result_cacheable(section, result):
            _cache_put(cache_key, section_name, result)
    非图形 role 恒 True（缓存语义不变）；本模块保持纯函数，不反向依赖
    _outline_to_spec。
    """
    role = section.get("role", "") if isinstance(section, dict) else ""
    diagram_spec = ROLE_DIAGRAM_SPEC.get(role)
    if not diagram_spec:
        return True
    # P3-2026-09-06：非 dict 结果（LLM 偶发返回 JSON 数组）fail-closed 不入缓存
    # （P1-13 同语义：畸形结果重跑可重试自愈），且防 _valid_* 对数组 .get 裸崩。
    # 注意须在 diagram_spec 短路之后——非图形 role 恒 True 的既有语义不变
    if not isinstance(result, dict):
        return False
    return _diagram_data_from_result(diagram_spec, result) is not None


def _valid_integration(result):
    """宽容校验 architecture/integration：总线（hub+systems）或点对点（source+target）。"""
    hub = result.get("hub")
    systems = result.get("systems")
    if isinstance(hub, dict) and hub.get("name"):
        if not isinstance(systems, list) or not systems:
            return None
        norm_systems = []
        for s in systems:
            if isinstance(s, str) and s.strip():
                norm_systems.append({"name": s})
            elif isinstance(s, dict) and s.get("name"):
                norm_systems.append({"name": str(s["name"])})
            else:
                return None
        return {"hub": {"name": str(hub["name"]),
                        "desc": str(hub.get("desc") or "")},
                "systems": norm_systems}
    source, target = result.get("source"), result.get("target")
    if source and target:
        return {"source": str(source), "target": str(target)}
    return None


def _valid_infra(result):
    """宽容校验 architecture/infra 的 zones（分区+节点必填）+ 可选 links。"""
    zones = result.get("zones")
    if not isinstance(zones, list) or not zones:
        return None
    norm_zones = []
    for z in zones:
        if not isinstance(z, dict) or not z.get("name"):
            return None
        nodes = z.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return None
        norm_nodes = []
        for n in nodes:
            if not isinstance(n, dict) or not n.get("name"):
                return None
            node = {"name": str(n["name"])}
            if n.get("desc"):
                node["desc"] = str(n["desc"])
            if n.get("icon"):
                node["icon"] = str(n["icon"])
            norm_nodes.append(node)
        norm_zones.append({"name": str(z["name"]), "nodes": norm_nodes})
    norm = {"zones": norm_zones}
    links = result.get("links")
    if isinstance(links, list):
        norm_links = []
        for ln in links:
            if not isinstance(ln, dict) or not ln.get("from") or not ln.get("to"):
                return None
            link = {"from": str(ln["from"]), "to": str(ln["to"])}
            if ln.get("mode") in ("sync", "async", "bidirectional"):
                link["mode"] = ln["mode"]
            norm_links.append(link)
        if norm_links:
            norm["links"] = norm_links
    return norm


def _valid_capability_map(result):
    """宽容校验 matrix/capability_map 的 sections；status 收敛 lit/partial/none
    （渲染器按该三值查表，未知值会 KeyError）。"""
    sections = result.get("sections")
    if not isinstance(sections, list) or not sections:
        return None
    norm = []
    for sec in sections:
        # isinstance 参与控制流（P1-13）：LLM 混入字符串/null 时拒绝而非裸崩
        if not isinstance(sec, dict) or not sec.get("name"):
            return None
        caps = sec.get("capabilities")
        if not isinstance(caps, list) or not caps:
            return None
        norm_caps = []
        for c in caps:
            if isinstance(c, str) and c.strip():
                norm_caps.append({"name": c})
            elif isinstance(c, dict) and c.get("name"):
                status = c.get("status")
                cap = {"name": str(c["name"]),
                       "status": status if status in ("lit", "partial", "none")
                                 else "none"}
                if c.get("system"):
                    cap["system"] = str(c["system"])
                if isinstance(c.get("items"), list):
                    cap["items"] = [
                        {"name": str(i["name"]),
                         "status": i.get("status")
                                   if isinstance(i, dict)
                                   and i.get("status") in ("lit", "partial", "none")
                                   else "none"}
                        for i in c["items"]
                        if isinstance(i, dict) and i.get("name")]
                norm_caps.append(cap)
            else:
                return None
        norm.append({"name": str(sec["name"]), "capabilities": norm_caps})
    return {"sections": norm}


def _valid_crud(result):
    """宽容校验 matrix/crud 的 docs×entities×cells（ops 限 C/R/U/D）。"""
    docs = result.get("docs")
    entities = result.get("entities")
    cells = result.get("cells")
    if (not isinstance(docs, list) or not docs
            or not isinstance(entities, list) or not entities
            or not isinstance(cells, list) or not cells):
        return None
    norm_docs = [str(d) for d in docs if str(d).strip()]
    norm_entities = [str(e) for e in entities if str(e).strip()]
    if not norm_docs or not norm_entities:
        return None
    norm_cells = []
    for c in cells:
        if not isinstance(c, dict) or not c.get("doc") or not c.get("entity"):
            return None
        ops = c.get("ops") if isinstance(c.get("ops"), list) else []
        norm_ops = [o for o in ops if o in ("C", "R", "U", "D")]
        if not norm_ops:
            return None
        norm_cells.append({"doc": str(c["doc"]), "entity": str(c["entity"]),
                           "ops": norm_ops})
    return {"docs": norm_docs, "entities": norm_entities, "cells": norm_cells}


def _valid_swimlane(result):
    """宽容校验 flow/swimlane 的 steps（label+lane 必填）；lanes 缺失时从
    steps 派生（渲染层 _layout_swimlane 同规则），保证 schema 必填 lanes 恒有值。"""
    steps = result.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    norm_steps = []
    for st in steps:
        if not isinstance(st, dict) or not st.get("label") or not st.get("lane"):
            return None
        norm_steps.append({
            "label": str(st["label"]),
            "lane": str(st["lane"]),
            "desc": str(st.get("desc") or ""),
        })
    norm_lanes, seen = [], set()
    lanes = result.get("lanes")
    if isinstance(lanes, list):
        for ln in lanes:
            name = ln if isinstance(ln, str) else (
                ln.get("name") if isinstance(ln, dict) else None)
            if not name or not str(name).strip():
                return None
            name = str(name)
            if name not in seen:
                seen.add(name)
                norm_lanes.append({"name": name})
    for st in norm_steps:
        if st["lane"] not in seen:
            seen.add(st["lane"])
            norm_lanes.append({"name": st["lane"]})
    return {"lanes": norm_lanes, "steps": norm_steps}


def _valid_module_gantt(result):
    """宽容校验 timeline/module_gantt 的 columns+groups；col 越界收敛到末列
    （渲染器按列号落格），tone 透传（渲染层 tones.get(tone, blue) 兜底）。"""
    columns = result.get("columns")
    groups = result.get("groups")
    if (not isinstance(columns, list) or not columns
            or not isinstance(groups, list) or not groups):
        return None
    norm_columns = [str(c) for c in columns if str(c).strip()]
    if not norm_columns:
        return None
    last = len(norm_columns) - 1

    def _col(value):
        # P3-2026-09-06：LLM 常把整数写成浮点（"col": 1.0），原实现
        # isinstance(int) 不过直接归 0，模块静默落到第 0 列——浮点按四舍五入
        # 显式取整，不再静默截断；bool 是 int 子类须排除，字符串/null 仍归 0
        if isinstance(value, bool):
            col = 0
        elif isinstance(value, int):
            col = value
        elif isinstance(value, float):
            col = int(round(value))
        else:
            col = 0
        return min(max(col, 0), last)

    norm_groups = []
    for g in groups:
        # isinstance 参与控制流（P1-13）：LLM 混入字符串/null 时拒绝而非裸崩
        if not isinstance(g, dict) or not g.get("name"):
            return None
        modules = g.get("modules")
        if not isinstance(modules, list) or not modules:
            return None
        norm_modules = []
        for m in modules:
            if not isinstance(m, dict) or not m.get("label"):
                return None
            norm_modules.append({"label": str(m["label"]),
                                 "col": _col(m.get("col", 0))})
        group = {"name": str(g["name"]), "modules": norm_modules}
        if g.get("sub"):
            group["sub"] = str(g["sub"])
        if g.get("tone"):
            group["tone"] = str(g["tone"])
        norm_groups.append(group)
    norm = {"columns": norm_columns, "groups": norm_groups}
    markers = result.get("markers")
    if isinstance(markers, list):
        norm_markers = []
        for mk in markers:
            if not isinstance(mk, dict) or not mk.get("label"):
                return None
            norm_markers.append({"col": _col(mk.get("col", 0)),
                                 "label": str(mk["label"]),
                                 "note": str(mk.get("note") or "")})
        if norm_markers:
            norm["markers"] = norm_markers
    return norm


def _valid_data_flow(result):
    """宽容校验 relationship/data_flow 的 nodes+flows；type/direction 收敛
    到渲染器枚举（source/process/store；push/pull/bidirectional）。"""
    nodes = result.get("nodes")
    flows = result.get("flows")
    if (not isinstance(nodes, list) or not nodes
            or not isinstance(flows, list) or not flows):
        return None
    norm_nodes = []
    for n in nodes:
        if not isinstance(n, dict) or not n.get("name"):
            return None
        ntype = n.get("type")
        norm_nodes.append({"name": str(n["name"]),
                           "type": ntype if ntype in ("source", "process", "store")
                                   else "process"})
    norm_flows = []
    for f in flows:
        if not isinstance(f, dict) or not f.get("from") or not f.get("to"):
            return None
        direction = f.get("direction")
        norm_flows.append({
            "from": str(f["from"]), "to": str(f["to"]),
            "data": str(f.get("data") or ""),
            "direction": direction if direction in ("push", "pull", "bidirectional")
                         else "push",
        })
    return {"nodes": norm_nodes, "flows": norm_flows}


def _valid_decision(result):
    """宽容校验 flow/decision 的 steps（decision 步用 alt_next/alt_label 标分支）。"""
    steps = result.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    norm = []
    for st in steps:
        if not isinstance(st, dict) or not st.get("label"):
            return None
        step = {"label": str(st["label"])}
        if st.get("type") in ("decision", "system", "end"):
            step["type"] = st["type"]
        if st.get("alt_next"):
            step["alt_next"] = str(st["alt_next"])
        if st.get("alt_label"):
            step["alt_label"] = str(st["alt_label"])
        norm.append(step)
    return {"steps": norm}
