# -*- coding: utf-8 -*-
"""spec 观察/检查类函数群（P4-S3 拆分自 _verify.py，2026-09-05）。

职责：spec.yml 版式维的检查类函数（除 capability_map 芯片禁令为 error 级外，
其余全部 [观察] 级，只报告不阻断）：
  - check_type_role_consistency（A-2 散值字号）/ check_shell_repetition（A-3 反同壳）
  - check_graphic_balance（图形化平衡）
  - check_narrative_consistency（叙事设计单一致性）/ check_stage_density（stage 密度）
  - check_diagram_opportunity（「可用而未用」）/ check_question_binding（question 绑定）
  - check_capability_map_system_name_as_chip（P1 芯片禁令，error 级）；check_analysis_structure / verify_analysis_md（I-3 批3 B4 三区表结构校验，观察级）升级条件: analysis md 全量覆盖后试升 error（盘点#11）
    - check_diagram_level（C-F1 图级校验聚合，2026-09-07）：全部 diagram 元素的
    schema error/warning 结构化摘要，供 deliver receipt 取 verify 摘要
    （S4 棘轮处置再拆 _verify_diagram，本模块 import 暴露同名）
  - 配套常量/私有助手：_VISUAL_KEYWORDS / _NON_DIAGRAM_TYPES / _AUTO_PAGE_ID_PREFIX /
    _DIAGRAM_SIGNAL_RULES / _OPP_SKIP_KEYS / _collect_page_text
（check_evidence_ledger（B-3 证据编号）S0 棘轮处置再拆 _verify_evidence，2026-09-07。）
主流程入口（auto_verify / verify_* / verify_spec_layout_data 聚合编排）仍在 _verify.py；
_verify.py 再导出本模块公开符号，既有引用面（tests、_cli_generate 等）不变。
"""
import os
import re

# S4 棘轮处置（2026-09-07）：check_diagram_level 再拆 _verify_diagram，
# 本模块 import 暴露同名，既有引用面（tests、_cli_generate 等）不变。
from _verify_diagram import check_diagram_level  # noqa: F401


def check_type_role_consistency(spec):
    """A-2 散值字号统计（观察模式）：扫描全 spec 元素的 fontSize 散值。升级条件: 误报率数据在案 → 升 warn（盘点#9）

    同一 spec 内同一散值字号出现 >2 次 → 提示收敛为 type_roles 角色。
    只报告不阻断（exit code 不变）。
    """
    from collections import Counter
    counts = Counter()
    for page in spec.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        for elem in page.get("elements", []) or []:
            if not isinstance(elem, dict):
                continue
            fs = elem.get("fontSize")
            if isinstance(fs, (int, float)) and not isinstance(fs, bool):
                counts[fs] += 1
    return [f"[观察] 散值字号 {fs} 出现 {n} 次，建议收敛为 type_roles 角色"
            for fs, n in sorted(counts.items()) if n > 2]


def check_shell_repetition(spec):
    """A-3 反同壳检查（观察模式）：相邻 ≥3 页 layout + 构件指纹相同 → [观察]。升级条件: 与 A-2 同批评审——误报率数据在案 → 升 warn（盘点#10）

    指纹 = layout + 构件类型序列 + diagram subtype 序列（文案内容不参与）。
    只报告不阻断（exit code 不变）。
    """
    pages = [p for p in spec.get("pages", []) or [] if isinstance(p, dict)]
    fingerprints = []
    series_list = []
    for p in pages:
        layout = p.get("layout", "")
        types, subtypes = [], []
        for e in p.get("elements", []) or []:
            if not isinstance(e, dict):
                continue
            types.append(e.get("type", ""))
            if e.get("type") == "diagram":
                subtypes.append(f"{e.get('diagram_type', '')}/{e.get('subtype', '')}")
        fingerprints.append((layout, tuple(types), tuple(subtypes)))
        series_list.append(str(p.get("series") or ""))

    msgs = []
    i, n = 0, len(fingerprints)
    while i < n:
        j = i
        while j < n and fingerprints[j] == fingerprints[i]:
            j += 1
        # Step 6：同 series 页面（步骤序列/前后对比系列）豁免反同壳
        series = series_list[i]
        if j - i >= 3 and series and all(s == series for s in series_list[i:j]):
            i = j
            continue
        if j - i >= 3:
            layout, types, subtypes = fingerprints[i]
            parts = [layout] if layout else ["无版式"]
            if types:
                parts.append("构件:" + "+".join(types))
            if subtypes:
                parts.append("图:" + "+".join(subtypes))
            msgs.append(f"[观察] 页面 {i + 1}-{j} 构图壳重复（{'；'.join(parts)}）")
        i = j
    return msgs


# 应使用 diagram 的内容信号关键词（用于“疑似纯文字页”观察）
_VISUAL_KEYWORDS = (
    "流程", "架构", "蓝图", "差距", "矩阵", "路线", "路线图", "能力",
    "拓扑", "部署", "集成", "对比", "甘特", "里程碑", "RACI", "责任矩阵",
    "演进", "数据流", "关系",
)

# 纯文字/卡片元素类型（页面只有这些且内容信号命中时，提示改用图；不含
# evidence_ledger / risk_register / raci_matrix / decision_board 等结构化组件，
# 避免把“已有结构化组件”误报成纯文字）
_NON_DIAGRAM_TYPES = {
    "text", "heading", "bullets", "cards", "table", "phases", "pullquote",
    "info_cards", "stat_cards", "kpi_cards", "pain_cards", "view_cards",
    "toc_cards", "hero", "section_tag", "action_title", "legend_bar",
    "topnav", "page_header", "conclusion_band",
}


def check_graphic_balance(spec):
    """图形化平衡观察（2026-09 新增）：捕捉“全是字/卡片墙”回归。

    只报告不阻断。不依赖 composition 字段，因此 AI 无法通过
    不声明 composition 绕过。检查三类：
      1. P05/P06/P08/P09 缺 diagram；
      2. 标题含流程/架构/差距等信号、页面却只有 text/cards/table 等；
      3. 整稿 diagram 占比过低/为零。
    """
    msgs = []
    pages = [p for p in spec.get("pages", []) or [] if isinstance(p, dict)]
    diagram_count = 0
    for pi, page in enumerate(pages):
        elements = [e for e in (page.get("elements", []) or [])
                    if isinstance(e, dict)]
        has_diagram = any(e.get("type") == "diagram" for e in elements)
        if has_diagram:
            diagram_count += 1
            continue

        layout = page.get("layout", "")
        if layout in ("P05", "P06", "P08", "P09"):
            msgs.append(
                f"[观察] pages[{pi}] 版式 {layout} 缺对应 diagram，"
                "版式要求图形页建议改用 diagram 而非纯文字/卡片")

        # 内容信号：标题/action_title/section_tag 命中视觉关键词
        title_parts = [str(page.get("title") or "")]
        for e in elements:
            if e.get("type") == "action_title":
                for seg in e.get("segments", []) or []:
                    if isinstance(seg, dict):
                        title_parts.append(str(seg.get("t") or ""))
            elif e.get("type") == "section_tag":
                title_parts.append(str(e.get("label") or ""))
        title_text = " ".join(title_parts)
        hits = [kw for kw in _VISUAL_KEYWORDS if kw in title_text]
        types = [e.get("type") for e in elements if isinstance(e, dict)]
        if hits and types and all(t in _NON_DIAGRAM_TYPES for t in types):
            msgs.append(
                f"[观察] pages[{pi}] 疑似纯文字/卡片页：标题含"
                f"“{'/'.join(sorted(set(hits)))}”信号，但只有"
                f"{'+'.join(sorted(set(types)))}，建议改用 diagram")

    total = len(pages)
    if total >= 5 and diagram_count == 0:
        msgs.append(
            f"[观察] 全篇 {total} 页无 diagram，疑似纯文字稿，"
            "请检查关键页是否应使用流程/架构/矩阵/时间线等图形")
    elif total >= 8 and diagram_count / total < 0.2:
        msgs.append(
            f"[观察] 图形占比偏低：{diagram_count}/{total} 页含 diagram"
            "（<20%），建议关键页结构化图形化")
    return msgs


# 生成侧（chapters 容器）自动补的 P02 目录 / P12 章节页 id 前缀，
# 页面集合一致性检查时豁免（条目 2-4 检查①；以生成侧实际上下发行为准）
_AUTO_PAGE_ID_PREFIX = "auto_"


def check_narrative_consistency(spec, spec_path=None):
    """叙事设计单一致性检查（条目 2-4，返回 (errors, warnings)）。

    2026-09-07 表达模式立项（0c）：①②「页面集合一致 / 页数预算」为可机检
    硬事实，已升阻断级；③④（八环节覆盖 / 图形意图落地）保持只报不判。

    四类检查：
      ① 页面集合一致：设计单 page_map 的 page id 集合 == spec pages 的 id 集合
        （生成侧自动补的 P02/P12 页 id 以 auto_ 开头，列入豁免）——error；
      ② 页数预算：spec 页数 ≤ 设计单 page_budget——error；
      ③ 八环节覆盖（scene 含「规划」或「顶层设计」时）：page_map beat 序列中
        「蓝图」之后必须出现「差距」「演进」「治理」——warning；
      ④ 图形意图落地：page_map graphic=族/subtype 的页，spec 对应页应有
        type: diagram 且 diagram_type == 族——warning。
    设计单不可读（spec_path 缺失 / 文件缺失 / 坏 YAML）→ 单条 warning 降级。
    """
    errors, warnings = [], []
    narrative_ref = spec.get("narrative_ref")
    if not narrative_ref:
        return errors, warnings

    def _unreadable():
        warnings.append(f"[观察] 设计单不可读，跳过叙事一致性检查"
                        f"（narrative_ref={narrative_ref}）")
        return errors, warnings

    if not spec_path:
        return _unreadable()
    doc_path = os.path.join(os.path.dirname(os.path.abspath(spec_path)),
                            str(narrative_ref))
    try:
        from _renderer.narrative_schema import load_and_validate
        doc, errs = load_and_validate(doc_path)
    except Exception:
        doc, errs = None, ["load_and_validate 异常"]
    if not isinstance(doc, dict) or errs:
        return _unreadable()

    pages = [p for p in spec.get("pages", []) or [] if isinstance(p, dict)]
    page_map = [m for m in (doc.get("page_map") or []) if isinstance(m, dict)]

    # ① 页面集合一致（error：硬事实）
    spec_ids = {str(p.get("id")) for p in pages if p.get("id")}
    spec_ids -= {i for i in spec_ids if i.startswith(_AUTO_PAGE_ID_PREFIX)}
    map_ids = {str(m.get("page")) for m in page_map if m.get("page")}
    only_spec = sorted(spec_ids - map_ids)
    only_map = sorted(map_ids - spec_ids)
    if only_spec or only_map:
        parts = []
        if only_spec:
            parts.append("spec 有而设计单缺: " + ", ".join(only_spec))
        if only_map:
            parts.append("设计单有而 spec 缺: " + ", ".join(only_map))
        errors.append("叙事设计单 page_map 与 spec 页面集合不一致（"
                      + "；".join(parts) + "）")

    # ② 页数预算（error：硬事实）
    budget = doc.get("page_budget")
    if (isinstance(budget, int) and not isinstance(budget, bool)
            and len(pages) > budget):
        errors.append(f"页数 {len(pages)} 超出设计单 page_budget={budget}"
                      f"（超 {len(pages) - budget} 页）")

    # ③ 八环节覆盖（仅规划类场景；环节定义见 规划方法.md §一 八环节主链）
    scene = str(doc.get("scene") or "")
    if "规划" in scene or "顶层设计" in scene:
        beats = [str(m.get("beat") or "") for m in page_map]

        def _beat_pos(kw):
            for i, b in enumerate(beats):
                if kw in b:
                    return i
            return None

        bp = _beat_pos("蓝图")
        if bp is None:
            warnings.append("[观察] 规划类场景八环节覆盖：page_map 缺「蓝图」环节"
                        "（环节定义见 规划方法.md §一）")
        else:
            for kw in ("差距", "演进", "治理"):
                pos = _beat_pos(kw)
                if pos is None:
                    warnings.append(f"[观察] 规划类场景八环节覆盖：「蓝图」之后缺"
                                f"「{kw}」环节（环节定义见 规划方法.md §一）")
                elif pos < bp:
                    warnings.append(f"[观察] 规划类场景八环节覆盖：「{kw}」出现在"
                                f"「蓝图」之前，顺序倒置（环节定义见"
                                " 规划方法.md §一）")

    # ④ 图形意图落地（graphic=族/subtype 的页应有 diagram 且 diagram_type==族）
    spec_by_id = {str(p.get("id")): p for p in pages if p.get("id")}
    for m in page_map:
        graphic = m.get("graphic")
        if not graphic or not isinstance(graphic, str) or "/" not in graphic:
            continue
        fam, sub = graphic.split("/", 1)
        pid = str(m.get("page") or "")
        page = spec_by_id.get(pid)
        if page is None:
            continue  # 页面缺失已由检查①报告
        diagrams = [e for e in (page.get("elements") or [])
                    if isinstance(e, dict) and e.get("type") == "diagram"]
        if not diagrams:
            warnings.append(f"[观察] 页 {pid} 意图图形化（{graphic}）、落地纯文字："
                        "spec 中无 diagram 元素")
            continue
        if not any(str(d.get("diagram_type") or "") == fam for d in diagrams):
            got = ", ".join(sorted({str(d.get("diagram_type") or "?")
                                    for d in diagrams}))
            warnings.append(f"[观察] 页 {pid} 图形族不符：设计意图 {graphic}，"
                        f"落地 diagram_type={got}")
        elif sub and not any(str(d.get("subtype") or "") == sub
                             for d in diagrams):
            warnings.append(f"[观察] 页 {pid} 图形 subtype 轻提示：设计意图"
                        f" {graphic}，落地同族但 subtype 不同")
    return errors, warnings


def check_stage_density(spec):
    """stage 容器单页密度观察（条目 2-7 后半，决策 D-a=A）。

    stage 为翻页演讲容器，单页元素建议 ≤5；超出只提示不阻断。
    """
    if str(spec.get("container") or "") != "stage":
        return []
    msgs = []
    for pi, page in enumerate(spec.get("pages", []) or []):
        if not isinstance(page, dict):
            continue
        n = len(page.get("elements") or [])
        if n > 5:
            msgs.append(f"[观察] stage 为翻页演讲容器，单页元素建议 ≤5"
                        f"（第 {pi + 1} 页 {n} 个）")
    return msgs


# 「可用而未用」观察（条目 3-5）：信号词 → 建议 diagram 族/subtype。
# 事实源：graphics.md §1「关系→图形决策树」，每行取首个/最贴切的 subtype；
# 元组顺序即优先级（具体词在前、泛词在后），同页多信号只报最匹配一条。
# 故意不收「架构/流程/能力/对比」等泛词（已由 check_graphic_balance 粗粒度
# 覆盖），本表只收能落到具体 subtype 的信号。
_DIAGRAM_SIGNAL_RULES = (
    (("RACI", "责任矩阵"), "matrix", "raci"),
    (("分工", "职责", "责任"), "matrix", "raci"),
    (("权限", "CRUD"), "matrix", "crud"),
    (("价值链",), "relationship", "value_chain"),
    (("象限", "优先级", "两轴"), "matrix", "quadrant"),
    (("能力地图",), "matrix", "cbm"),
    (("能力盘点",), "matrix", "capability_map"),
    (("能力树",), "relationship", "biz_capability_tree"),
    (("组织", "汇报线"), "relationship", "org_tree"),
    (("成熟度",), "matrix", "harvey_balls"),
    (("差距",), "matrix", "fit_gap"),
    (("泳道", "跨系统", "多角色", "多系统交互"), "flow", "swimlane"),
    (("并行", "汇聚"), "flow", "parallel"),
    (("分支",), "flow", "decision"),
    (("主流程", "调用链", "数据流"), "flow", "sequence"),
    (("故障域", "网络分区", "部署"), "architecture", "deployment"),
    (("系统集成",), "architecture", "integration"),
    (("平台中心", "生态"), "architecture", "platform_hub"),
    (("分层", "业务总览"), "architecture", "layered"),
    (("金字塔",), "architecture", "pyramid"),
    (("里程碑", "排期", "甘特", "阶段计划", "演进路线"),
     "timeline", "horizontal"),
    (("ER", "数据关系"), "relationship", "er_conceptual"),
    (("柱状图",), "chart", "bar"),
    (("收益桥", "瀑布图"), "chart", "waterfall"),
)

# 文本采集时跳过的结构性字段（值是枚举/编号不是文案，避免误命中信号词）
_OPP_SKIP_KEYS = {
    "id", "type", "subtype", "diagram_type", "layout", "index", "hl",
    "tone", "level", "swatch", "variant", "frame", "icon", "num", "date",
    "unit", "source",
}


def _collect_page_text(node, out):
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k not in _OPP_SKIP_KEYS:
                _collect_page_text(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_page_text(v, out)


def check_diagram_opportunity(spec):
    """「可用而未用」观察（条目 3-5）：信号命中但页面无 diagram 时提示。

    逐页扫描 title/action_title/正文等全部文案字段，命中决策树信号词且
    页面元素只有 table/cards/text 一类（无 diagram、无 evidence_ledger 等
    结构化组件，判定复用 _NON_DIAGRAM_TYPES）时，产出一条 [观察] 提示对应
    族/subtype；同页多信号按 _DIAGRAM_SIGNAL_RULES 顺序只报最匹配一条。
    只报不判，永不阻断（TTL(2026-12-31): 季度评审——持续为空的检查面销号，盘点#8）。
    """
    msgs = []
    for pi, page in enumerate(spec.get("pages", []) or []):
        if not isinstance(page, dict):
            continue
        elements = [e for e in (page.get("elements", []) or [])
                    if isinstance(e, dict)]
        if any(e.get("type") == "diagram" for e in elements):
            continue
        types = [e.get("type") for e in elements]
        if not types or not all(t in _NON_DIAGRAM_TYPES for t in types):
            continue
        parts = []
        _collect_page_text(page, parts)
        text = " ".join(parts)
        for keywords, fam, sub in _DIAGRAM_SIGNAL_RULES:
            hit = next((kw for kw in keywords if kw in text), None)
            if hit:
                pid = str(page.get("id") or f"pages[{pi}]")
                msgs.append(f"[观察] 页 {pid} 命中「{hit}」信号但只有"
                            f"文字/卡片，可考虑 {fam}/{sub}")
                break
    return msgs


def check_question_binding(spec):
    """question_driven 最简机械检查：questions.id 出现在 ≥1 后续页面的
    section_tag 或 title 中，缺失 → [观察]。不做叙事分析。"""
    msgs = []
    pages = [p for p in spec.get("pages", []) or [] if isinstance(p, dict)]
    for pi, page in enumerate(pages):
        qs = page.get("questions") or []
        if not isinstance(qs, list):
            continue
        for qi, q in enumerate(qs):
            if not isinstance(q, dict) or not q.get("id"):
                continue
            qid = str(q["id"])
            # P3：Q 编号边界精确匹配——裸子串匹配会让「Q12」顶替 Q1 的绑定
            # （title 含 Q12 即判 Q1 已引用）。边界：编号两侧不得邻接字母数字。
            qid_re = re.compile(
                rf"(?<![0-9A-Za-z]){re.escape(qid)}(?![0-9A-Za-z])")
            found = False
            for later in pages[pi + 1:]:
                if not isinstance(later, dict):
                    continue
                if qid_re.search(str(later.get("title", ""))):
                    found = True
                    break
                for e in later.get("elements", []) or []:
                    if (isinstance(e, dict) and e.get("type") == "section_tag"
                            and qid_re.search(str(e.get("label", "")))):
                        found = True
                        break
                if found:
                    break
            if not found:
                msgs.append(
                    f"[观察] pages[{pi}].questions[{qi}]: 问题编号 {qid} "
                    "未在后续页面 section_tag 或 title 中引用")
    return msgs


def check_capability_map_system_name_as_chip(spec):
    """P1：capability_map 的 items.name 禁止等于 systems_inventory.name。

    系统名出现在芯片位 = 把“系统”当“能力点”使用，直接报错（verify FAIL）。
    """
    errors = []
    for pi, page in enumerate(spec.get("pages", []) or []):
        if not isinstance(page, dict):
            continue
        for ei, elem in enumerate(page.get("elements", []) or []):
            if not isinstance(elem, dict) or elem.get("type") != "diagram":
                continue
            if elem.get("subtype") != "capability_map":
                continue
            inv_names = {
                str(s.get("name", "")).strip()
                for s in (elem.get("systems_inventory") or [])
                if isinstance(s, dict) and s.get("name")
            }
            if not inv_names:
                continue
            for si, sec in enumerate(elem.get("sections") or []):
                if not isinstance(sec, dict):
                    continue
                for ci, cap in enumerate(sec.get("capabilities") or []):
                    if not isinstance(cap, dict):
                        continue
                    for ii, it in enumerate(cap.get("items") or []):
                        if not isinstance(it, dict):
                            continue
                        name = str(it.get("name", "")).strip()
                        if name and name in inv_names:
                            errors.append(
                                f"pages[{pi}].elements[{ei}]: capability_map "
                                f"sections[{si}].capabilities[{ci}].items[{ii}].name "
                                f"'{name}' 等于 systems_inventory.name"
                                "（系统名不能当芯片，请改为能力项）")
    return errors


# I-3 批3 B4：三区表结构校验（总方案 §9.2 三规则，观察级不阻断）升级条件: analysis md 全量覆盖后试升 error（盘点#11）。解析复用 _embed_index 批2
# 解析器（已核实其模块级仅 stdlib+numpy、无 _verify* 反向引用，无循环 import）
_ANALYSIS_BASIS_RE = re.compile(r"依据类型[：:]\s*(材料原文|召回片段|推断)")
_ANALYSIS_TOP_LIMIT = 5


def check_analysis_structure(content, label="三区表"):
    """三规则检查（只报不判）：①确认区每条挂依据类型+有效证据锚点（_memory_guard 语法）②confirmed ≤5
    （Top 纪律）③推断不得 confirmed（Claim 零条进确认区）。缺固定小节 → []（非三区表，跳过）。"""
    from _embed_index import _ANALYSIS_ENTRY_RE, _split_analysis_sections
    from _memory_guard import parse_source_refs
    sections = _split_analysis_sections(content)
    if "确认事实" not in sections:
        return []
    warnings, confirmed_n = [], 0
    for i, line in enumerate(sections["确认事实"], 1):
        if not re.match(r"^[-*]\s", line):
            continue
        m = _ANALYSIS_ENTRY_RE.match(line)
        if not m:
            warnings.append(f"[观察] {label} 确认区第{i}行缺 [confirmed|draft] 机械标记")
            continue
        basis = _ANALYSIS_BASIS_RE.search(m.group(2))
        if not basis:
            warnings.append(f"[观察] {label} 确认区第{i}行未挂依据类型（材料原文/召回片段/推断）")
        em = re.search(r"证据[：:]\s*(.+)$", m.group(2))
        refs = parse_source_refs(em.group(1).strip()) if em else []
        if not refs or any(r["kind"] == "invalid" for r in refs):
            warnings.append(f"[观察] {label} 确认区第{i}行缺有效证据锚点（file:/session: 语法）")
        confirmed_n += m.group(1) == "confirmed"
        if m.group(1) == "confirmed" and basis and basis.group(1) == "推断":
            warnings.append(f"[观察] {label} 确认区第{i}行推断类 confirmed（Claim 零条进确认区）")
    if confirmed_n > _ANALYSIS_TOP_LIMIT:
        warnings.append(f"[观察] {label} 确认区 confirmed {confirmed_n} 条 >{_ANALYSIS_TOP_LIMIT}（Top 纪律）")
    return warnings


def verify_analysis_md(path):
    """auto_verify 的 .md 分支：analysis/ 下含「## 确认事实」的三区表 → (True, msg)（只报不判，永不 FAIL）；否则 None。"""
    if "/analysis/" not in path.replace("\\", "/") or not path.endswith(".md"):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return False, f"无法读取: {e}"
    if "## 确认事实" not in content:
        return None
    warnings = check_analysis_structure(content, label=os.path.basename(path))
    return True, (f"OK (三区表结构校验, {os.path.getsize(path)} bytes)"
                  + (f" | {'; '.join(warnings[:5])}" if warnings else ""))
