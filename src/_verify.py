# -*- coding: utf-8 -*-
import os
import re
import sys
import math

MIN_PPTX_SIZE = 5 * 1024
MIN_HTML_SIZE = 500
MIN_DOCX_SIZE = 5 * 1024
MIN_XLSX_SIZE = 1 * 1024
MIN_YAML_SIZE = 50

# L4: 去 AI 痕迹（单一数据源：_paths.py）
from _paths import BANNED_PHRASES, BANNED_WORDS, SCRIPT_DIR

# P4-S3 拆分（2026-09-05）：spec 观察/检查类函数群迁 _verify_checks。
# 此处 re-import 保持既有引用面可达（tests/test_narrative_consistency.py、
# tests/test_verify_step5_6.py、tests/test_diagram_opportunity.py 等
# 经 _verify 引用这些符号），verify_spec_layout_data 内消费面不变。
# 到期复审：tests monkeypatch 面迁移至真源后退役（复审点：下一大批次开工前）。——2026-09-07 复审：tests 仍经此面打桩（test_b3_cli_face/test_m1_f0/test_recall_eval/test_verify_render_report 等），保留；退役点顺延至 monkeypatch 面迁移完成。
# 退役计划（S6 2026-09-07 注记）：tests 全部改为直引 _verify_checks 真源后删除
# 本 re-import 块；跟踪锚点 docs/发版稳定版_S3S4_实施报告_2026-09-07.md 遗留项
# 「check_diagram_level 打印面接线等」（本块图级符号接线见下）。
from _verify_checks import (
    check_capability_map_system_name_as_chip, check_diagram_level,
    check_diagram_opportunity, check_graphic_balance,
    check_narrative_consistency, check_question_binding,
    check_shell_repetition, check_stage_density,
    check_type_role_consistency, verify_analysis_md,
)
# S0 棘轮处置（2026-09-07）：check_evidence_ledger 再拆 _verify_evidence，
# 同面 re-import，_verify 引用面不变。
from _verify_evidence import check_evidence_ledger


def verify_pptx(path):
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    if not path.lower().endswith(".pptx"):
        return False, f"不是 .pptx 文件: {path}"

    size = os.path.getsize(path)
    if size < MIN_PPTX_SIZE:
        return False, f"文件过小 ({size} bytes, 最少 {MIN_PPTX_SIZE} bytes): {path}"

    try:
        from pptx import Presentation
        prs = Presentation(path)
    except Exception as e:
        return False, f"无法打开 PPTX: {e}"

    slide_count = len(prs.slides)
    if slide_count < 1:
        return False, "PPTX 没有幻灯片"

    return True, f"OK ({slide_count} 页, {size} bytes)"


def verify_html(path, density_gate="verify"):
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    if not (path.lower().endswith(".html") or path.lower().endswith(".htm")):
        return False, f"不是 HTML 文件: {path}"

    size = os.path.getsize(path)
    if size < MIN_HTML_SIZE:
        return False, f"文件过小 ({size} bytes, 最少 {MIN_HTML_SIZE} bytes): {path}"

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"无法读取 HTML: {e}"

    if "<!DOCTYPE html>" not in content and "<!doctype html>" not in content:
        return False, "缺少 <!DOCTYPE html> 声明"

    if "</html>" not in content:
        return False, "缺少 </html> 闭合标签"

    # 放宽检查：只要有 CSS 样式引用即可（Tailwind/内联/外部 CSS 均可）
    has_css = (
        "<style" in content or
        "tailwindcss" in content or
        'rel="stylesheet"' in content or
        ".css" in content
    )
    if not has_css:
        return False, "未检测到任何 CSS 样式引用"

    msg = f"OK ({size} bytes)"
    # Step 3：style 机械扫描 + 占位符残留（只报不阻断）
    try:
        from _style_guard import check as style_check
        style_issues = style_check(content)
        if style_issues:
            # C-C1：severity 贯通——warn（语境层）与 block（硬禁）分级标注
            msg += " | style: " + "; ".join(
                f"{i['name']}×{i['count']}"
                + ("(warn)" if i.get("severity") == "warn" else "")
                for i in style_issues[:5])
    except Exception as e:
        # P3：扫描降级需留痕——曾静默 pass，style 扫描停用无人知晓（漏检去 AI 化）
        print(f"[warn] style 机械扫描失败（降级跳过，不阻断）: {e}", file=sys.stderr)
    ph = check_placeholder_residual(content)
    if ph:
        msg += " | " + "; ".join(ph)
    # C-E5：截图脱敏提醒（warn 级，不阻断）
    sd = _warn_screenshot_desensitization(html_text=content)
    if sd:
        msg += " | " + "; ".join(sd)
    # 美学观察（D-120，观察模式不阻断）：渲染后几何美学检查 升级条件: 标准页待误报率数据在案后逐维升 warn（盘点#2）
    # （重叠/字号层级/溢出/大空白/对比度）；playwright 不可用时显式标注降级
    try:
        from _density import check_density_html
        findings = check_density_html(path, gate=density_gate) or []
        real = [f for f in findings
                if not f.startswith(("playwright", "密度检查执行失败"))]
        # #43：降级显式标注——曾静默过滤，输出面与「通过」无异（佯动误导）
        skipped = len(findings) - len(real)
        if skipped and not real:
            msg += " | 美学观察：playwright 不可用未执行（显式降级，非通过）"
        if real:
            msg += f" | 美学观察 {len(real)} 条: " + "; ".join(real[:3])
    except Exception:
        pass
    # I-7 S15 域禁令观察（机械子集，不阻断）：命中在 msg 标注供人工复核
    try:
        import re as _re
        from _domain_guard import check_domain_bans
        _body = _re.sub(r"<[^>]+>", " ", content)
        _body = _re.sub(r"\s+", " ", _body)
        bans = check_domain_bans(_body)
        if bans:
            msg += " | 域禁令 " + "; ".join(
                f"{b['id']}({b['source']})" for b in bans[:5])
    except Exception:
        pass
    return True, msg


def verify_docx(path, client_name=""):
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    if not path.lower().endswith(".docx"):
        return False, f"不是 .docx 文件: {path}"

    size = os.path.getsize(path)
    if size < MIN_DOCX_SIZE:
        return False, f"文件过小 ({size} bytes, 最少 {MIN_DOCX_SIZE} bytes): {path}"

    try:
        from docx import Document
        doc = Document(path)
    except Exception as e:
        return False, f"无法打开 DOCX: {e}"

    para_count = len(doc.paragraphs)
    if para_count < 1:
        return False, "DOCX 没有段落内容"

    non_empty = sum(1 for p in doc.paragraphs if p.text.strip())
    if non_empty == 0:
        return False, "DOCX 所有段落均为空"

    # L4: 去 AI 痕迹（不阻断，仅警告）
    l4_ok, l4_issues = check_ai_traces(path)
    l4_msg = ""
    if not l4_ok:
        l4_msg = " | L4警告: " + "; ".join(l4_issues[:3])

    # L5: 废标风险（不阻断，仅警告）
    l5_ok, l5_issues = check_bid_risks(path, client_name)
    l5_msg = ""
    if not l5_ok:
        l5_msg = " | L5风险: " + "; ".join(l5_issues[:3])

    return True, f"OK ({para_count} 段落, {non_empty} 非空, {size} bytes){l4_msg}{l5_msg}"


# ============================================================
# L4: 去 AI 痕迹检查
# ============================================================

def check_ai_traces(path):
    """检查 docx 中的 AI 痕迹。

    三项检查：
    1. burstiness（句子长度方差，AI 文本方差低）
    2. 禁用词（BANNED_WORDS 硬 5 词，单一数据源在 _paths.py）
    3. 模板句式（综上所述/总而言之...）

    返回 (pass: bool, issues: list[str])
    """
    from docx import Document
    doc = Document(path)
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if not full_text:
        return True, []

    issues = []

    # 1. burstiness 检查
    sentences = re.split(r"[。！？.!?]", full_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    if len(sentences) >= 10:
        lengths = [len(s) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((length - mean_len) ** 2 for length in lengths) / len(lengths)
        std_dev = math.sqrt(variance)
        burstiness = std_dev / mean_len if mean_len > 0 else 0
        # burstiness < 0.3 说明句子长度太均匀，疑似 AI 生成
        if burstiness < 0.3:
            issues.append(f"burstiness={burstiness:.2f}（偏低，句子长度过于均匀，疑似AI生成）")

    # 2. 禁用词检查
    for word in BANNED_WORDS:
        count = full_text.count(word)
        if count > 0:
            issues.append(f"禁用词「{word}」出现 {count} 次")

    # 3. 模板句式检查
    for phrase in BANNED_PHRASES:
        count = full_text.count(phrase)
        if count > 0:
            issues.append(f"模板句式「{phrase}」出现 {count} 次")

    return len(issues) == 0, issues


# ============================================================
# L5: 废标风险检查
# ============================================================

def check_bid_risks(path, client_name=""):
    """检查标书废标风险。

    三项检查：
    1. 评分覆盖率：每项评分是否都有对应章节
    2. 资质提及：must_mention 中的资质是否出现
    3. 格式合规：检查页边距/字体/暗标等

    返回 (pass: bool, issues: list[str])
    """
    import json

    issues = []

    # 加载 bid_criteria.json
    criteria_path = None
    if client_name:
        criteria_path = os.path.join(SCRIPT_DIR, "output", client_name, "bid_criteria.json")
    if not criteria_path or not os.path.exists(criteria_path):
        return True, []  # 无招标标准，跳过

    with open(criteria_path, "r", encoding="utf-8") as f:
        try:
            criteria = json.load(f)
        except json.JSONDecodeError as e:
            return False, [f"bid_criteria.json 解析失败: {e}"]

    from docx import Document
    doc = Document(path)
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # 1. 评分覆盖率
    scoring = criteria.get("scoring", [])
    uncovered = []
    for item in scoring:
        item_name = item.get("item", "")
        if item_name and item_name not in full_text:
            # 检查子项
            sub_items = item.get("sub_items", [])
            if sub_items:
                sub_covered = any(
                    sub.get("name", "") in full_text for sub in sub_items
                )
                if not sub_covered:
                    uncovered.append(item_name)
            else:
                uncovered.append(item_name)
    if uncovered:
        issues.append(f"评分项未覆盖: {', '.join(uncovered)}")

    # 2. 资质提及
    quals = criteria.get("qualifications", {})
    must_mention = quals.get("must_mention", [])
    missing_quals = [q for q in must_mention if q not in full_text]
    if missing_quals:
        issues.append(f"资质未提及: {', '.join(missing_quals)}")

    # 3. 格式合规（简单检查）
    fmt = criteria.get("format_requirements", {})
    if fmt.get("dark_bid"):
        # 暗标：检查是否含公司名/作者信息
        # 这里简单检查，实际应更严格
        author_fields = ["作者", "撰写人", "编制人", "公司名"]
        for field in author_fields:
            if field in full_text:
                issues.append(f"暗标模式但含「{field}」信息")
                break

    return len(issues) == 0, issues


def verify_xlsx(path):
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    if not path.lower().endswith(".xlsx"):
        return False, f"不是 .xlsx 文件: {path}"

    size = os.path.getsize(path)
    if size < MIN_XLSX_SIZE:
        return False, f"文件过小 ({size} bytes, 最少 {MIN_XLSX_SIZE} bytes): {path}"

    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
    except Exception as e:
        return False, f"无法打开 XLSX: {e}"

    sheet_count = len(wb.sheetnames)
    if sheet_count < 1:
        return False, "XLSX 没有工作表"

    return True, f"OK ({sheet_count} 工作表, {size} bytes)"


def verify_yaml(path):
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    if not (path.lower().endswith(".yml") or path.lower().endswith(".yaml")):
        return False, f"不是 YAML 文件: {path}"

    size = os.path.getsize(path)
    if size < MIN_YAML_SIZE:
        return False, f"文件过小 ({size} bytes, 最少 {MIN_YAML_SIZE} bytes): {path}"

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return False, f"无法解析 YAML: {e}"

    if data is None:
        return False, "YAML 文件内容为空或仅含注释"

    # v2.0 版式维（§10）：spec 文件（含 pages）追加 6 条版式检查
    if isinstance(data, dict) and isinstance(data.get("pages"), list):
        lay_ok, lay_errors, lay_warnings = verify_spec_layout_data(
            data, spec_path=path)
        msg = f"OK ({type(data).__name__}, {size} bytes)"
        # S6（2026-09-07）：图级 verify 摘要上打印面（C-F1 遗留接线）。与
        # deliver receipt 同口径（_verify_diagram.check_diagram_level 聚合，
        # 规则单点在 schema）；errors/warnings 与版式维同规则集，此处只做
        # 计数摘要展示，不重复阻断/不重复展开明细。
        dl = check_diagram_level(data)
        if dl["diagrams"]:
            msg += (f" | 图级校验 {dl['diagrams']} 图"
                    f"（错误 {len(dl['errors'])} / 警告 {len(dl['warnings'])}）")
        if lay_warnings:
            msg += f" | 版式警告 {len(lay_warnings)} 条: " + "; ".join(lay_warnings[:3])
        if lay_errors:
            return False, (f"{msg} | 版式校验 {len(lay_errors)} 条错误: "
                           + "; ".join(lay_errors[:3]))
        return True, msg

    return True, f"OK ({type(data).__name__}, {size} bytes)"


# ============================================================
# v2.0 版式维（dev_plan_visual_v2_2026-07-25 §10，6 条检查）
# ============================================================

# 结论式标题量化词（§10 检查 3：含数字或量化词）
_QUANT_WORDS = ("%", "翻倍", "倍", "降至", "提升", "提高", "降低", "减少",
                "增长", "覆盖", "节约", "缩短", "万", "亿")


_PLACEHOLDER_RE = re.compile(
    r"Services (One|Two|Three)|lorem ipsum|Nullam|Lorem|占位|"
    r"\bTODO(?:示例文字)?\b|待补充|待定",  # C-A4：词边界，独立 TODO/TODO:xxx 均命中、todoxxx 不误报
    re.IGNORECASE,
)

# C-E5 脱敏提醒外迁 _verify_desens（S8-B 棘轮拆小）；re-export 保持引用面
from _verify_desens import _warn_screenshot_desensitization  # noqa: F401


def check_placeholder_residual(text):
    """占位符残留扫描（Step 3 质检收口）：命中即 [warn]。"""
    hits = sorted({m.group(0) for m in _PLACEHOLDER_RE.finditer(text)})
    return [f"占位符残留：{', '.join(hits)}"] if hits else []


def verify_style_scan(path):
    """verify --only style 作用域：纯 style 机械扫描 + 占位符残留，不跑 Playwright。"""
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"无法读取文件: {e}"
    parts = []
    try:
        from _style_guard import check as style_check
        issues = style_check(content)
        if issues:
            # C-C1：severity 贯通——warn（语境层）与 block（硬禁）分级标注
            parts.append("style: " + "; ".join(
                f"{i['name']}×{i['count']}"
                + ("(warn)" if i.get("severity") == "warn" else "")
                for i in issues[:5]))
    except Exception as e:
        parts.append(f"style 扫描失败: {e}")
    ph = check_placeholder_residual(content)
    if ph:
        parts.extend(ph)
    return True, (f"OK（style+占位符扫描，{len(parts)} 条警告）"
                  + (" | " + "; ".join(parts) if parts else ""))


def verify_spec_layout_data(spec, spec_path=None):
    """spec 版式维 6 条检查（§10）。返回 (ok, errors, warnings)。

    1 版式合法（error）：layout ∈ P01-P16（无 P13）∪ 旧值白名单 + 必需构件齐全
      ——schema.validate_layout_errors 复核（单点在 schema，此处不重复实现）
    2 主题合法（error）：theme ∈ THEMES + v2 spec 无 hex 字面量
      ——schema._validate_doc_theme / _validate_spec_hex 复核
    3 结论式标题（warning）：action_title 全文 ≥12 字且含数字或量化词
    4 图例完备（error）：capability_map（三态语义色 >2）同页无 legend_bar；
      flow_rows roles>2 走 §8.1 自动 legend，豁免
    5 虚线纪律（warning）：dashed_opt 行内 badge 等——schema 容量/纪律
      warnings 复核（单点在 schema.validate_element_warnings）
    6 容量阈值（warning）：flow_rows 行/卡、P04 pain、P07 table 行数等
      ——schema.validate_element_warnings / validate_layout_warnings 复核
    """
    from _renderer import schema as _schema
    errors, warnings = [], []

    # C-E5：截图脱敏提醒（warn 级，不阻断）
    warnings.extend(_warn_screenshot_desensitization(spec=spec))

    # 检查 1 + 2（schema 复核：版式/theme/hex 的 error 全集）
    errors.extend(_schema.validate_spec(spec))
    # P1：capability_map 系统名不能当芯片
    errors.extend(check_capability_map_system_name_as_chip(spec))

    for pi, page in enumerate(spec.get("pages", []) or []):
        if not isinstance(page, dict):
            continue
        elements = [e for e in (page.get("elements", []) or [])
                    if isinstance(e, dict)]
        where = f"pages[{pi}]"
        # 检查 6（版式容量）+ 顺序
        warnings.extend(_schema.validate_layout_warnings(page, page_index=pi))
        # 检查 3：结论式标题
        for ei, elem in enumerate(elements):
            if elem.get("type") != "action_title":
                continue
            _, normalized = _schema._proto.normalize_element(elem)
            full = "".join(seg.get("t", "") for seg in normalized["segments"])
            has_num = any(ch.isdigit() for ch in full)
            has_quant = any(w in full for w in _QUANT_WORDS)
            if len(full) < 12 or not (has_num or has_quant):
                warnings.append(
                    f"{where}.elements[{ei}]: action_title 不满足结论式标题"
                    f"（需 ≥12 字且含数字或量化词），实际 {len(full)} 字")
        # 检查 4：图例完备
        has_legend = any(e.get("type") == "legend_bar" for e in elements)
        for ei, elem in enumerate(elements):
            if elem.get("type") != "diagram":
                continue
            # 检查 5 + 6（元素级容量/纪律）
            warnings.extend(_schema.validate_element_warnings(elem, index=ei))
            if elem.get("subtype") == "capability_map" and not has_legend:
                errors.append(
                    f"{where}.elements[{ei}]: capability_map 三态语义色 >2 "
                    "但同页无 legend_bar（图例完备，§10）")

        # 检查 9a：AI 配色纪律（v2 新增，Kimi 方法论：单页语义色 ≤4；
        # 禁红/紫/黄/绿高饱和四色同页——AI 经典配色）
        semantic = set()
        for elem in elements:
            etype = elem.get("type")
            if etype == "stat_cards":
                for c in elem.get("cards", []) or []:
                    if isinstance(c, dict) and c.get("tone") in ("lit", "part", "gap"):
                        semantic.add(c["tone"])
            elif etype == "legend_bar":
                for it in elem.get("items", []) or []:
                    if isinstance(it, dict) and it.get("swatch"):
                        semantic.add(str(it["swatch"]))
            elif etype == "pain_cards":
                for c in elem.get("cards", []) or []:
                    if isinstance(c, dict) and c.get("level") in ("P0", "P1", "P2"):
                        semantic.add(c["level"])
            elif etype == "action_title":
                for seg in elem.get("segments", []) or []:
                    if isinstance(seg, dict) and seg.get("hl") in ("yellow", "red", "green"):
                        semantic.add(f'hl_{seg["hl"]}')
            elif etype == "diagram" and elem.get("subtype") == "flow_rows":
                roles = elem.get("roles") or {}
                if isinstance(roles, dict):
                    semantic.update(f"role_{k}" for k in roles)
        if len(semantic) > 4:
            warnings.append(f"{where}: 单页语义色 {len(semantic)} 种 >4"
                            "（AI 配色纪律，§10 检查 9）")
        families = set()
        for s in semantic:
            if s in ("role_legal", "P0", "hl_red"):
                families.add("red")
            elif s == "role_sys":
                families.add("purple")
            elif s == "hl_yellow":
                families.add("yellow")
            elif s in ("role_fin", "lit", "hl_green"):
                families.add("green")
        if families == {"red", "purple", "yellow", "green"}:
            warnings.append(f"{where}: 红/紫/黄/绿高饱和四色同页"
                            "（Kimi 禁 AI 经典配色，§10 检查 9）")

    # A-2 散值字号观察 + A-3 反同壳观察 + B-3 证据编号重复观察
    # + D-122 讲法观察 + 图形平衡观察（观察模式）升级条件: review 第 5 维与机检 proxy 对账一次（S11 后）再定转正/维持（盘点#7）
    warnings.extend(check_type_role_consistency(spec))
    warnings.extend(check_shell_repetition(spec))
    warnings.extend(check_evidence_ledger(spec))
    warnings.extend(check_question_binding(spec))
    warnings.extend(check_graphic_balance(spec))
    # 条目 2-4 叙事一致性（0c：页面集合/页数预算升 error，其余只报不判）
    # + 条目 2-7 stage 密度（D-a=A，只报不判）
    _narr = check_narrative_consistency(spec, spec_path=spec_path)
    if isinstance(_narr, tuple) and len(_narr) == 2:
        errors.extend(_narr[0])
        warnings.extend(_narr[1])
    else:
        warnings.extend(_narr)
    # S8-A 2×3 合规矩阵（crafted 定制页轨）：weaver×crafted 特批门（error）
    # + 每 deck ≤2 页（观察），与叙事一致性同门汇聚（单点 narrative_schema）
    try:
        from _renderer.narrative_schema import check_compliance_matrix
        _mx_errors, _mx_warnings = check_compliance_matrix(
            spec, spec_path=spec_path)
    except Exception:
        _mx_errors, _mx_warnings = [], ["[观察] 合规矩阵检查异常，跳过"]
    errors.extend(_mx_errors)
    warnings.extend(_mx_warnings)
    warnings.extend(check_stage_density(spec))
    # 条目 3-5「可用而未用」观察（观察级，永不阻断）TTL(2026-12-31): 季度评审——持续为空的检查面销号（盘点#8）
    warnings.extend(check_diagram_opportunity(spec))

    return len(errors) == 0, errors, warnings


def verify_all(paths_dict):
    results = {}
    all_ok = True

    verifiers = {
        "pptx": (verify_pptx, ".pptx"),
        "html": (verify_html, ".html"),
        "docx": (verify_docx, ".docx"),
        "xlsx": (verify_xlsx, ".xlsx"),
        "yaml": (verify_yaml, ".yml"),
    }

    for key, (fn, _ext) in verifiers.items():
        path = paths_dict.get(key)
        if not path:
            continue
        ok, msg = fn(path)
        results[key] = {"ok": ok, "msg": msg, "path": path}
        if not ok:
            all_ok = False

    return all_ok, results


def auto_verify(path, client_name="", density_gate="verify"):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pptx":
        return verify_pptx(path)
    elif ext in (".html", ".htm"):
        ok, msg = verify_html(path, density_gate=density_gate)
        if client_name:  # I-3 A5：keynote 线集合核对（不阻断）
            try:
                import re as _re
                with open(path, "r", encoding="utf-8") as _f:
                    _body = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", _f.read()))
                from _domain_guard import keynote_observe_for_text
                msg += keynote_observe_for_text(_body, client_name=client_name)
            except Exception:
                pass
        return ok, msg
    elif ext == ".docx":
        return verify_docx(path, client_name)
    elif ext == ".xlsx":
        return verify_xlsx(path)
    elif ext == ".pptd":
        # pptd 主文件（yaml 内容）：格式检查 + 版式维复检（§10 检查 7/8/9b）
        if not os.path.exists(path):
            return False, f"文件不存在: {path}"
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                deck = yaml.safe_load(f)
        except Exception as e:
            return False, f"无法解析 pptd（yaml）: {e}"
        if not isinstance(deck, dict) or "pages" not in deck:
            return False, "pptd 缺 pages 结构"
        ok, msg = True, f"OK (pptd, {os.path.getsize(path)} bytes)"
        lay_ok, lay_errors, lay_warnings = verify_pptd_deck(
            os.path.dirname(os.path.abspath(path)) or ".")
        if lay_warnings:
            msg += f" | 版式警告 {len(lay_warnings)} 条: " + "; ".join(lay_warnings[:3])
        if lay_errors:
            return False, (f"{msg} | pptd 版式维 {len(lay_errors)} 条错误: "
                           + "; ".join(lay_errors[:3]))
        return ok, msg
    elif ext in (".yml", ".yaml"):
        ok, msg = verify_yaml(path)
        if ok and client_name:  # I-3 A5：spec 线集合核对（不阻断）
            try:
                with open(path, "r", encoding="utf-8") as _f:
                    _text = _f.read()
                from _domain_guard import keynote_observe_for_text
                msg += keynote_observe_for_text(_text, client_name=client_name)
            except Exception:
                pass
        return ok, msg
    elif ext == ".md":  # I-3 批3 B4：三区表结构校验（观察级，不阻断）升级条件: analysis md 全量覆盖后试升 error（盘点#11）
        res = verify_analysis_md(path)
        if res is not None:
            return res
        return False, f"不支持的文件类型: {ext}"
    else:
        return False, f"不支持的文件类型: {ext}"


# ============================================================
# v2.0 pptd 版式维复检（§10 检查 7/8/9b，v2 修订新增）
# ============================================================

# 检查 7 五类 Warning 类型：单点定义在 _pptd.py（checker 封装层）
# （局部 import 见 verify_pptd_deck，避免模块级依赖）

# 检查 9b 卡类 elementId（去唯一化前缀 v2{y}-/dg{y}- 后匹配）
_CARD_ID_RE = re.compile(
    r"^(?:(?:v2\d+|dg\d+)-)?(?:(?:stc|kpi|pain|info)-\d+|fr-c\d+-\d+|hero-sc\d+)$")


def _bounds_intersect(a, b, shrink=0.0):
    """矩形相交判定；shrink 为 a 的四边内缩容差（穿字检查防边缘误报）。"""
    ax1, ay1 = a[0] + shrink, a[1] + shrink
    ax2, ay2 = a[0] + a[2] - shrink, a[1] + a[3] - shrink
    return not (ax2 <= b[0] or b[0] + b[2] <= ax1
                or ay2 <= b[1] or b[1] + b[3] <= ay1)


def _bounds_contains(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[0] + outer[2] >= inner[0] + inner[2]
            and outer[1] + outer[3] >= inner[1] + inner[3])


def verify_pptd_deck(deck_dir):
    """pptd 工程版式维复检（§10 检查 7/8/9b）。返回 (ok, errors, warnings)。

    - 检查 7（error）：check_report.json（pptd-build 时 _pptd.py 写入）中
      五类 Warning 计数 >0；无报告文件时跳过（老工程兼容）
    - 检查 8（warning）：连接线（*Connector）bounds 与任何 text 元素
      bounds 相交（Kimi 制图纪律：连接线止于节点边缘、绝不穿越文字）
    - 检查 9b（warning）：卡片嵌套 >1 层（卡类 shape 完全包含另一卡类）
    """
    import json
    import yaml
    from _pptd import PPTD_WARN_TYPES  # 单点定义（checker 封装层）
    errors, warnings = [], []

    # ---- 检查 7：checker 五类 warning 复检 ----
    report_path = os.path.join(deck_dir, "check_report.json")
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                check_report = json.load(f)
        except (OSError, ValueError) as e:
            warnings.append(f"check_report.json 解析失败: {e}")
            check_report = {}
        warn_counts = check_report.get("warnings", {})
        bad = {t: n for t, n in warn_counts.items()
               if t in PPTD_WARN_TYPES and n > 0}
        if bad:
            detail = ", ".join(f"{t}×{n}" for t, n in sorted(bad.items()))
            errors.append(f"pptd checker 五类 Warning 未处理：{detail}（§10 检查 7）")

    # ---- 检查 8/9b：pages/*.page 几何扫描 ----
    pages_dir = os.path.join(deck_dir, "pages")
    page_files = []
    if os.path.isdir(pages_dir):
        page_files = [os.path.join(pages_dir, fn) for fn in os.listdir(pages_dir)
                      if fn.endswith(".page")]
    elif os.path.exists(report_path) or any(
            fn.endswith(".pptd") for fn in (os.listdir(deck_dir)
                                            if os.path.isdir(deck_dir) else [])):
        pass  # 有工程但无 pages 目录（空 deck），不报错
    for pf in sorted(page_files):
        try:
            with open(pf, "r", encoding="utf-8") as f:
                page = yaml.safe_load(f)
        except (OSError, ValueError):
            continue
        elements = (page or {}).get("elements", []) or []
        pname = os.path.basename(pf)
        # D-2 图形白名单（只报不阻断）：shape preset / connector kind / diagram 无图像化
        warnings.extend(_diagram_shape_whitelist_warnings(elements, pname))
        connectors = [e for e in elements
                      if e.get("elementType") == "shape"
                      and "Connector" in str(e.get("shapeName", ""))]
        texts = [e for e in elements if e.get("elementType") == "text"]
        for conn in connectors:
            cb = conn.get("bounds")
            if not cb or len(cb) != 4:
                continue
            for t in texts:
                tb = t.get("bounds")
                if not tb or len(tb) != 4:
                    continue
                if _bounds_intersect(cb, tb, shrink=2.0):
                    warnings.append(
                        f"{pname}: 连接线 {conn.get('elementId')} 穿过文本 "
                        f"{t.get('elementId')}（连接线止于节点边缘，§10 检查 8）")
        # 卡片嵌套：卡类完全包含另一卡类（装饰件/容器底不在卡类正则内）
        cards = [e for e in elements
                 if e.get("elementType") == "shape"
                 and _CARD_ID_RE.match(str(e.get("elementId", "")))
                 and e.get("bounds") and len(e["bounds"]) == 4]
        for outer in cards:
            for inner in cards:
                if outer is inner:
                    continue
                if _bounds_contains(outer["bounds"], inner["bounds"]):
                    warnings.append(
                        f"{pname}: 卡片嵌套 {outer.get('elementId')} ⊃ "
                        f"{inner.get('elementId')}（同页卡片不嵌套，§10 检查 9）")

    return len(errors) == 0, errors, warnings


def _diagram_shape_whitelist_warnings(elements, pname):
    """D-2 图形白名单（观察模式）：shape 名在注册 preset/connector 表内、TTL(2026-12-31): 季度评审转正/销号（盘点表未登记，随下轮盘点补录）
    diagram 区域无图像化。只报告不阻断。

    白名单单点来源 = _pptd_convert 的 _SHAPE_NAME_MAP / _CONNECTOR_MAP
    （转换器支持什么就允许什么，方言层与转换层不分叉）。
    """
    from _pptd_convert import _SHAPE_NAME_MAP, _CONNECTOR_MAP
    allowed = set(_SHAPE_NAME_MAP) | set(_CONNECTOR_MAP)
    msgs = []
    for e in elements:
        et = e.get("elementType")
        if et == "shape":
            sn = str(e.get("shapeName", ""))
            if not sn:
                continue
            if "Connector" in sn:
                if sn not in _CONNECTOR_MAP:
                    msgs.append(f"{pname}: 连接线 kind 未注册 {e.get('elementId')} "
                                f"shapeName={sn}（合法: {sorted(_CONNECTOR_MAP)}）")
            elif sn not in allowed:
                msgs.append(f"{pname}: shape 预设名不在白名单 {e.get('elementId')} "
                            f"shapeName={sn}")
        elif et == "image":
            eid = str(e.get("elementId", ""))
            if eid.startswith("dg"):
                msgs.append(f"{pname}: diagram 图形区域出现图片元素 {eid}"
                            "（图像化违规，图应走原生 shape/connector）")
    return [f"[观察] {m}" for m in msgs]



