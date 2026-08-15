# -*- coding: utf-8 -*-
"""独立审查：generate 完成后自动调用独立 LLM 会话审查产出质量。

与 verify（格式检查）和 theme-verify（关键词覆盖）不同，
review 用独立 LLM 会话做内容质量审查，不带对话历史。

设计原则（D-013）：
  - 独立会话：每次 review 是一次全新的 _cloud_llm.chat() 调用，不带任何对话历史
  - 输入最小化：只传 spec 摘要 + 产出文本 + 铁律清单
  - 结构化输出：PASS/FAIL + 逐条审查结果
  - 不阻断生成：review 失败只打印警告，不阻断后续流程（v1 保守策略）

审查维度：
  1. 铁律覆盖：permanent 主题是否全部在产出中有体现
  2. 内容一致性：产出内容是否与 spec 一致，有无 AI 自作主张
  3. 去 AI 化：是否含禁用词/禁用句式
  4. 事实可追溯：关键论断是否有依据（引用 spec 或 evidence）
"""
import os
import sys
import json
import yaml
from datetime import datetime

import _paths


# 去 AI 化禁用词（单一数据源在 _paths.py）
from _paths import BANNED_WORDS, BANNED_PHRASES

# 产出文本截断上限（字符数），防止超长 prompt
MAX_OUTPUT_CHARS = 8000

# 结构完整度及格线（A-4 第 5 维，来源 presentation-content-design reference.md
# #quality-gate；新组件上线时必须同步，维护约定见 B-3~B-7 任务卡）
STRUCTURE_CHECKLIST = {
    "叙事组件": "判断 + 解释 + 例证，三件套齐",
    "指标组件": "单位 + 周期 + 语境 + 变化原因，可追溯",
    "流程时序": "参与方 + 动作 + 状态 + 输入输出 + 异常支路",
    "架构图": "真实实体 + 边界 + 接口 + 流向",
    "数据图表": "口径 + 单位 + 刻度 + 标签 + 业务解释",
    "证据台账": "结论 + 证据编号 + 状态，可追溯",
    "风险登记": "风险项 + 等级 + 状态 + 应对，可跟踪",
    "责任矩阵": "每行任务恰一个 A（问责）+ R/C/I 分工清晰",
    "决策面板": "方案比较 + 推荐 + 下一步，缺一不可",
    "层级金字塔": "层级分明 + 每层有实质内容 + 层级递进逻辑",
    "四象限": "两轴标签清晰 + 四象限定位有业务含义 + 每象限有关键项",
}


def _format_themes(themes):
    """将 themes 列表格式化为审查用的文本。"""
    if not themes:
        return "(无铁律)"
    lines = []
    for t in themes:
        priority = t.get("priority", "high")
        tag = "[!]" if priority == "critical" else "[*]"
        lines.append(f"{tag} [{t.get('persistence','permanent').upper()}-{t.get('scope','client').upper()}] {t.get('theme','')}")
        if t.get("description"):
            lines.append(f"   说明: {t['description'][:150]}")
    return "\n".join(lines)


def _format_spec_summary(spec):
    """从 spec.yml 提取摘要（页面标题 + 关键元素）。"""
    pages = spec.get("pages", [])
    if not pages:
        return "(spec 无页面)"
    lines = []
    for i, p in enumerate(pages, 1):
        title = p.get("title", f"第{i}页")
        elements = p.get("elements", [])
        elem_summaries = []
        for el in elements[:5]:  # 每页最多 5 个元素
            etype = el.get("type", "text")
            if etype == "text":
                content = el.get("content", "")[:80]
                if content:
                    elem_summaries.append(f"  文本: {content}")
            elif etype == "bullets":
                items = el.get("items", [])[:3]
                for item in items:
                    elem_summaries.append(f"  - {str(item)[:60]}")
            elif etype == "cards":
                for c in el.get("cards", [])[:2]:
                    elem_summaries.append(f"  卡片: {c.get('title','')}")
            elif etype == "table":
                rows = el.get("rows", [])
                elem_summaries.append(f"  表格: {len(rows)} 行")
        lines.append(f"第{i}页 [{title}]")
        lines.extend(elem_summaries[:4])
    return "\n".join(lines)


def _check_banned(text):
    """本地检查禁用词/禁用句式（不走 LLM，快速）。"""
    found = []
    for w in BANNED_WORDS:
        if w in text:
            found.append(f"禁用词: {w}")
    for p in BANNED_PHRASES:
        if p in text:
            found.append(f"禁用句式: {p}")
    return found


def _read_output_text(output_path):
    """读取产出文件文本内容。HTML 取纯文本，其他取全文。"""
    if not os.path.exists(output_path):
        return None
    ext = os.path.splitext(output_path)[1].lower()
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None

    if ext in (".html", ".htm"):
        # 粗略去 HTML 标签，取纯文本
        import re
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:MAX_OUTPUT_CHARS]
    else:
        return raw[:MAX_OUTPUT_CHARS]


def write_review_log(result, output_path, client_name):
    """把 review 结果追加到 review_log.json（独立日志，不写 task_history）。

    见 spec 5.1.1 + 破坏点 3：review 在 generate 内部自动调用，
    generate 不调 save_session 不写 task_history，故用独立日志。
    """
    log_path = _paths.REVIEW_LOG
    try:
        entries = []
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
        if not isinstance(entries, list):
            entries = []
        entries.append({
            "verdict": result.get("verdict", "SKIP"),
            "scores": result.get("scores", {}),
            "file": output_path,
            "client": client_name or "",
            "issues": result.get("issues", []),
            "summary": result.get("summary", ""),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[review] review_log 写入失败（不阻断）: {e}")


def _prepare_context(output_path, client_name, spec_path):
    """读产出 + 本地禁用词检查 + 客户铁律 + spec 摘要。

    review / review_parallel / review_adversarial 三函数共用的前置步骤。
    返回 dict（output_text/banned/themes_text/spec_summary）；产出不可读时返回 None。
    """
    output_text = _read_output_text(output_path)
    if output_text is None:
        return None
    ctx = {
        "output_text": output_text,
        "banned": _check_banned(output_text),
        "themes_text": "(无客户铁律)",
        "spec_summary": "(无 spec)",
    }
    if client_name:
        try:
            from _theme_guard import load_active_themes
            themes = load_active_themes(client_name, only_permanent=True)
            ctx["themes_text"] = _format_themes(themes)
        except Exception:
            pass
    if spec_path and os.path.exists(spec_path):
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = yaml.safe_load(f)
            ctx["spec_summary"] = _format_spec_summary(spec)
        except Exception:
            pass
    return ctx


def _finalize_review(result, output_path, client_name, quiet):
    """review 收尾（串行/并行共用）：写 review_log + FAIL 记 decision + 打印。"""
    write_review_log(result, output_path, client_name)

    if result["verdict"] == "FAIL" and client_name:
        try:
            from _theme_guard import save_decision
            issues_text = "; ".join(result.get("issues", []))
            save_decision(
                client_name=client_name,
                topic=f"review FAIL: {os.path.basename(output_path)}",
                decision=f"产出 {output_path} 审查未通过",
                reason=issues_text[:500],
            )
        except Exception as e:
            print(f"[review] save_decision 失败（不阻断）: {e}")

    if not quiet or result["verdict"] != "PASS":
        _print_review(result, output_path)


def review(output_path, client_name=None, spec_path=None, quiet=False):
    """独立审查产出物。

    Args:
        output_path: 产出文件路径
        client_name: 客户名（用于加载铁律）
        spec_path: spec.yml 路径（用于内容一致性检查）
        quiet: True 时只在有问题时打印

    Returns:
        dict: {"verdict": "PASS"|"FAIL"|"SKIP"|"ERROR", "issues": [...], "summary": str}
    """
    result = {"verdict": "SKIP", "issues": [], "summary": ""}

    # --- 1-3. 读产出 + 本地禁用词 + 铁律 + spec 摘要（三函数共用 helper） ---
    ctx = _prepare_context(output_path, client_name, spec_path)
    if ctx is None:
        result["verdict"] = "ERROR"
        result["summary"] = f"无法读取文件: {output_path}"
        return result

    output_text = ctx["output_text"]
    banned = ctx["banned"]
    themes_text = ctx["themes_text"]
    spec_summary = ctx["spec_summary"]
    if banned:
        result["issues"].extend(banned)

    # --- 4. 独立 LLM 审查 ---
    from _cloud_llm import chat, LLM_MODE

    checklist = "\n".join(f"- {k}: {v}" for k, v in STRUCTURE_CHECKLIST.items())

    prompt = f"""你是独立审查员。请审查以下产出文件，逐项检查并打分。

## 客户铁律
{themes_text}

## spec 摘要
{spec_summary}

## 产出文件内容（前 {MAX_OUTPUT_CHARS} 字）
{output_text}

## 审查要求
1. **铁律覆盖**：上面的铁律是否全部在产出中有体现？逐条标注 ✓ 或 ✗
2. **内容一致性**：产出内容是否与 spec 一致？有无 AI 自作主张添加的内容？
3. **去 AI 化**：是否含禁用词（{"、".join(BANNED_WORDS)}）或禁用句式（{"、".join(BANNED_PHRASES)}）？
4. **事实可追溯**：关键论断是否有依据？

## 五维度打分（每维度 1-5 分，总分 25 分）
- **设计质量**：是否感觉像一个连贯整体，结构清晰、层次分明
- **原创性**：是否有定制决策证据，而非模板默认
- **工艺**：技术执行--字体层次、间距一致性、色彩协调
- **功能性**：用户能否理解内容、找到关键信息、达到目的
- **结构完整度**：按组件类型检查信息要素是否齐全（及格线见下），缺要素扣分

## 结构完整度及格线
{checklist}

## 输出格式（严格 JSON）
{{"verdict": "PASS" 或 "FAIL", "scores": {{"设计": N, "原创": N, "工艺": N, "功能": N, "结构": N, "总分": N}}, "issues": ["问题1", "问题2"], "theme_coverage": {{"覆盖数": N, "未覆盖": ["铁律1"]}}, "summary": "一句话总结"}}"""

    system = "你是方案审查员。严格按审查要求逐项检查，不放过任何问题。只返回 JSON，不要解释。"

    llm_result = chat(
        prompt=prompt,
        system=system,
        temperature=0.1,
        # P0-1（2026-07-21）：1000 是基础值；chat() 对 thinking provider 自动
        # 加 reasoning 余量（×3，下限 4000）+ finish_reason=length 加倍重试，
        # 无需在此逐 task 调参
        max_tokens=1000,
        json_mode=True,
        task="post_generate_review",
    )

    if llm_result:
        try:
            import json
            parsed = json.loads(llm_result)
            parsed_issues = parsed.get("issues", [])
            result["verdict"] = parsed.get("verdict", "PASS")
            # 用 extend 而非赋值：保留本地 _check_banned 的命中结果（避免 LLM 返回空 issues 覆盖本地禁用词检查）
            if isinstance(parsed_issues, list):
                result["issues"].extend(parsed_issues)
            else:
                result["issues"].append(str(parsed_issues))
            result["summary"] = parsed.get("summary", "")
            result["theme_coverage"] = parsed.get("theme_coverage", {})
            result["scores"] = parsed.get("scores", {})
            # 低分自动 FAIL（总分低于 15/25）
            total = result["scores"].get("总分", 0)
            if isinstance(total, (int, float)) and total < 15 and result["verdict"] == "PASS":
                result["verdict"] = "FAIL"
                result["issues"].append(f"总分 {total}/25 低于阈值 15，自动降级为 FAIL")
        except (json.JSONDecodeError, TypeError):
            # JSON 解析失败，把原始文本当 summary
            result["verdict"] = "FAIL"
            result["summary"] = f"LLM 返回非 JSON: {llm_result[:200]}"
            result["issues"].append("审查结果解析失败")
    else:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        result["verdict"] = "ERROR"
        result["summary"] = "LLM 调用失败（无可用 provider）"

    # 合并本地检查结果
    if banned:
        result["verdict"] = "FAIL"

    # --- 5-6. 写 review_log + FAIL 记 decision + 输出（串行/并行共用） ---
    _finalize_review(result, output_path, client_name, quiet)

    return result


# ============================================================================
# 并行审查模式（维度级并行，2026-08 起）
# 与串行 review()（一次调用查全部维度）不同，并行模式把 5 个维度拆成
# 5 路独立 LLM 会话并发执行：
#   - 维度隔离：每路独立角色、独立 prompt 只查自己维度，防注意力稀释
#     与维度间锚定（一路 PASS 暗示其他路 PASS 的自证偏差）
#   - 单路失败不阻断：某一路 provider 失败只记该路 ERROR，其余维度照常汇总
#   - 平台无关：用 _cloud_llm 独立会话 + 线程池内建，不依赖宿主子代理
#     （Kimi 禁用子代理、Trae 形态不同，宿主子代理只适合会话级人工拉起）
# 触发：python _cli.py review <文件> --parallel
# ============================================================================

# 5 路维度定义：(维度名, 角色, 唯一任务描述, 汇总时取用的 extra 键)
_PARALLEL_DIMENSIONS = (
    ("铁律覆盖", "铁律覆盖检查员", "逐条核对客户铁律是否在产出中有体现，逐条标注 ✓ 或 ✗，输出未覆盖清单", "theme_coverage"),
    ("内容一致性", "内容一致性检查员", "对照 spec 摘要检查产出内容是否一致，找出偏差与 AI 自作主张添加的内容", "spec_deviations"),
    ("去AI化", "文风检查员", "检查禁用词、禁用句式与模板化 AI 痕迹", "ai_traces"),
    ("事实可追溯", "事实核查员", "检查关键论断是否有事实/数据依据支撑", "unsupported_claims"),
    ("五维打分", "质量评审员", "设计/原创/工艺/功能/结构五维打分 + 结构完整度要素核查", "scores"),
)


def _build_dimension_prompt(dim_name, role, focus, ctx):
    """构造单维度审查 prompt：只含本维度任务，上下文块三函数共用（provider 前缀缓存友好）。"""
    checklist = "\n".join(f"- {k}: {v}" for k, v in STRUCTURE_CHECKLIST.items())
    scoring = ""
    extra_schema = ""
    if dim_name == "五维打分":
        scoring = f"""## 五维度打分（每维度 1-5 分，总分 25 分）
- **设计质量**：是否感觉像一个连贯整体，结构清晰、层次分明
- **原创性**：是否有定制决策证据，而非模板默认
- **工艺**：技术执行--字体层次、间距一致性、色彩协调
- **功能性**：用户能否理解内容、找到关键信息、达到目的
- **结构完整度**：按组件类型检查信息要素是否齐全（及格线见下），缺要素扣分

## 结构完整度及格线
{checklist}

"""
        extra_schema = ', "scores": {{"设计": N, "原创": N, "工艺": N, "功能": N, "结构": N, "总分": N}}'
    elif dim_name == "铁律覆盖":
        extra_schema = ', "theme_coverage": {{"覆盖数": N, "未覆盖": ["铁律1"]}}'
    return f"""你是{role}。只审查下面这一项，其他维度与你无关。

## 客户铁律
{ctx["themes_text"]}

## spec 摘要
{ctx["spec_summary"]}

## 产出文件内容（前 {MAX_OUTPUT_CHARS} 字）
{ctx["output_text"]}

## 你的唯一任务：{focus}
{scoring}## 输出格式（严格 JSON，不要解释）
{{"verdict": "PASS" 或 "FAIL", "issues": ["问题1", "问题2"], "summary": "一句话总结"{extra_schema}}}"""


def _review_dimension(dim, ctx):
    """单维度独立审查（review_parallel 线程池调用）。绝不抛异常，失败返回 error 标记。"""
    from _cloud_llm import chat, LLM_MODE

    dim_name, role, focus, extra_key = dim
    prompt = _build_dimension_prompt(dim_name, role, focus, ctx)
    system = f"你是{role}。严格只查指定维度，只返回 JSON，不要解释。"
    max_tokens = 1200 if dim_name == "五维打分" else 600
    try:
        llm_result = chat(
            prompt=prompt,
            system=system,
            temperature=0.1,
            max_tokens=max_tokens,
            json_mode=True,
            task="post_generate_review",
        )
    except Exception as e:
        return {"dim": dim_name, "error": f"chat 调用异常: {e}"}
    if not llm_result:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        return {"dim": dim_name, "error": "LLM 调用失败（无可用 provider）"}
    try:
        parsed = json.loads(llm_result)
    except (json.JSONDecodeError, TypeError):
        return {"dim": dim_name, "error": f"返回非 JSON: {llm_result[:120]}"}
    issues = parsed.get("issues", [])
    if not isinstance(issues, list):
        issues = [str(issues)]
    out = {
        "dim": dim_name,
        "verdict": parsed.get("verdict", "PASS"),
        "issues": issues,
        "summary": parsed.get("summary", ""),
    }
    extra = parsed.get(extra_key)
    if extra:
        out["extra_key"] = extra_key
        out["extra"] = extra
    return out


def _merge_parallel_results(dim_results, banned):
    """汇总 5 路并行结果：合并 issues（去重保序）、scores、theme_coverage、verdict。"""
    result = {"verdict": "PASS", "issues": list(banned), "summary": "", "mode": "parallel"}
    summaries = []
    errors = 0
    for dim_name, _, _, _ in _PARALLEL_DIMENSIONS:
        r = dim_results.get(dim_name)
        if r is None:
            errors += 1
            result["issues"].append(f"维度[{dim_name}] 审查未返回结果")
            continue
        if "error" in r:
            errors += 1
            result["issues"].append(f"维度[{dim_name}] 审查失败: {r['error']}")
            continue
        if r.get("verdict") == "FAIL":
            result["verdict"] = "FAIL"
        result["issues"].extend(r.get("issues", []))
        if r.get("summary"):
            summaries.append(f"{dim_name}: {r['summary']}")
        if r.get("extra_key") == "theme_coverage":
            result["theme_coverage"] = r["extra"]
        elif r.get("extra_key") == "scores":
            result["scores"] = r["extra"]

    # issues 去重（保序）
    seen = set()
    deduped = []
    for iss in result["issues"]:
        key = str(iss)
        if key not in seen:
            seen.add(key)
            deduped.append(iss)
    result["issues"] = deduped

    if summaries:
        result["summary"] = "；".join(summaries)[:300]

    # 低分自动 FAIL（总分 < 15/25，与串行 review 同阈值）。
    # scores 缺失（五维打分路失败/未返回）时跳过，避免 0 分误判。
    scores = result.get("scores") or {}
    total = scores.get("总分", 0)
    if scores and isinstance(total, (int, float)) and total < 15 and result["verdict"] == "PASS":
        result["verdict"] = "FAIL"
        result["issues"].append(f"总分 {total}/25 低于阈值 15，自动降级为 FAIL")

    # 全部维度失败 → ERROR
    if errors >= len(_PARALLEL_DIMENSIONS):
        result["verdict"] = "ERROR"
        result["summary"] = "全部审查维度失败（LLM 不可用）"
    return result


def review_parallel(output_path, client_name=None, spec_path=None, quiet=False, max_workers=5):
    """并行独立审查：5 路独立 LLM 会话各查一个维度，汇总去重。

    Returns:
        dict: {"verdict": "PASS"|"FAIL"|"SKIP"|"ERROR", "issues": [...],
               "scores": {...}, "theme_coverage": {...}, "summary": str,
               "mode": "parallel"}
    """
    result = {"verdict": "SKIP", "issues": [], "summary": "", "mode": "parallel"}

    # --- 1-3. 读产出 + 本地禁用词 + 铁律 + spec 摘要（三函数共用 helper） ---
    ctx = _prepare_context(output_path, client_name, spec_path)
    if ctx is None:
        result["verdict"] = "ERROR"
        result["summary"] = f"无法读取文件: {output_path}"
        return result

    # --- 4. 5 路独立会话并行审查 ---
    from concurrent.futures import ThreadPoolExecutor, as_completed

    dim_results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_dim = {
            pool.submit(_review_dimension, dim, ctx): dim[0]
            for dim in _PARALLEL_DIMENSIONS
        }
        for future in as_completed(future_to_dim):
            dim_name = future_to_dim[future]
            try:
                dim_results[dim_name] = future.result()
            except Exception as e:  # 防御：_review_dimension 不应抛，兜底
                dim_results[dim_name] = {"dim": dim_name, "error": str(e)}

    result.update(_merge_parallel_results(dim_results, ctx["banned"]))

    # --- 5-6. 写 review_log + FAIL 记 decision + 输出（与串行共用） ---
    _finalize_review(result, output_path, client_name, quiet)

    return result


def _safe_print(text):
    """安全打印：处理 Windows 控制台 GBK 编码问题。"""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")
        sys.stdout.flush()


def _print_review(result, output_path):
    """格式化打印审查结果。"""
    verdict = result.get("verdict", "SKIP")
    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "ERROR": "[ERR]"}.get(verdict, "?")

    _safe_print(f"\n{'='*50}")
    _safe_print(f"{icon} 独立审查: {verdict}")
    _safe_print(f"   文件: {os.path.basename(output_path)}")
    if result.get("mode") == "parallel":
        _safe_print("   模式: 并行 5 路独立会话（维度隔离，防锚定）")

    # 五维度打分
    scores = result.get("scores", {})
    if scores:
        total = scores.get("总分", 0)
        _safe_print(f"   打分: 设计 {scores.get('设计', '?')} | 原创 {scores.get('原创', '?')} | 工艺 {scores.get('工艺', '?')} | 功能 {scores.get('功能', '?')} | 结构 {scores.get('结构', '?')} | 总分 {total}/25")

    summary = result.get("summary", "")
    if summary:
        _safe_print(f"   总结: {summary}")

    issues = result.get("issues", [])
    if issues:
        _safe_print(f"   问题 ({len(issues)}):")
        for i, iss in enumerate(issues, 1):
            _safe_print(f"     {i}. {iss}")

    coverage = result.get("theme_coverage", {})
    if coverage:
        covered = coverage.get("覆盖数", "?")
        uncovered = coverage.get("未覆盖") or []
        _safe_print(f"   铁律覆盖: {covered}/{covered + len(uncovered) if isinstance(covered, int) else '?'}")
        if uncovered:
            for u in uncovered:
                _safe_print(f"     [x] {u}")

    _safe_print(f"{'='*50}\n")


# ============================================================================
# 对抗性 review 模式（P0-1，借鉴 Claude Dynamic Workflows adversarial verification）
# 与常规 review（平衡打分）不同，对抗性 review 是"专门挑刺"--独立角色聚焦找问题，
# 解决 AI 自证偏差（self-preferential bias）。触发：python _cli.py review <文件> --adversarial
# ============================================================================


def review_adversarial(output_path, client_name=None, spec_path=None, quiet=False):
    """对抗性审查：独立挑刺者角色，只找问题不打分。

    与常规 review() 的区别：
    - 常规 review：4 维度平衡打分，PASS/FAIL 阈值 12/20
    - 对抗性 review：不打分，只列可被反驳的论断/不一致/AI 痕迹/无依据论断

    借鉴 Claude Dynamic Workflows 的 adversarial verification layer--
    worker agent 产出后，独立 refutation agent 专门挑刺，解决自证偏差。

    Returns:
        dict: {"verdict": "PASS"|"FAIL"|"ERROR", "issues": [...], "summary": str}
    """
    result = {"verdict": "PASS", "issues": [], "summary": ""}

    # --- 1-3. 读产出 + 本地禁用词 + 铁律 + spec 摘要（三函数共用 helper） ---
    ctx = _prepare_context(output_path, client_name, spec_path)
    if ctx is None:
        result["verdict"] = "ERROR"
        result["summary"] = f"无法读取文件: {output_path}"
        return result

    output_text = ctx["output_text"]
    banned = ctx["banned"]
    themes_text = ctx["themes_text"]
    spec_summary = ctx["spec_summary"]
    if banned:
        result["issues"].extend(banned)

    # --- 4. 独立 LLM 对抗性审查（挑刺者角色） ---
    from _cloud_llm import chat, LLM_MODE

    checklist = "\n".join(f"- {k}: {v}" for k, v in STRUCTURE_CHECKLIST.items())

    prompt = f"""你是严格的挑刺者。目标只有一个：找出这份产出中可能被质疑的问题。

## 客户铁律
{themes_text}

## spec 摘要
{spec_summary}

## 产出文件内容（前 {MAX_OUTPUT_CHARS} 字）
{output_text}

## 审查要求（只找问题，不打分）
1. **可被反驳的论断**：列出可能被客户/评委质疑的论断，附反驳理由
2. **与 spec 不一致**：产出内容与 spec 摘要有哪些偏差？AI 自作主张了什么？
3. **AI 痕迹**：禁用词（{"、".join(BANNED_WORDS)}）或模板化句式
4. **无依据的关键论断**：哪些关键论断缺乏事实/数据支撑？
5. **结构完整度缺失**：按组件及格线检查，哪些组件缺信息要素？

## 结构完整度及格线
{checklist}

## 输出格式（严格 JSON）
{{"verdict": "PASS" 或 "FAIL", "refutable_claims": ["论断1 - 反驳理由", "论断2 - 反驳理由"], "spec_deviations": ["偏差1", "偏差2"], "ai_traces": ["痕迹1"], "unsupported_claims": ["无依据论断1"], "summary": "一句话总结挑刺结果"}}

注意：
- verdict=PASS 仅当确实找不到任何问题时；找到任何问题即 FAIL
- 禁止说"整体不错""总体可以"等平衡评价--你是挑刺者，不是打分员
- 若无问题，summary 明确写"未发现问题"
"""

    system = "你是对抗性审查员（挑刺者）。只负责找问题，不做平衡评价。只返回 JSON，不要解释。"

    llm_result = chat(
        prompt=prompt,
        system=system,
        temperature=0.1,
        max_tokens=1500,
        json_mode=True,
        task="adversarial_review",
    )

    if llm_result:
        try:
            parsed = json.loads(llm_result)
            result["verdict"] = parsed.get("verdict", "PASS")
            # 汇总所有问题到 issues
            for key in ("refutable_claims", "spec_deviations", "ai_traces", "unsupported_claims"):
                items = parsed.get(key, [])
                if isinstance(items, list):
                    for item in items:
                        result["issues"].append(f"[{key}] {item}")
                elif items:
                    result["issues"].append(f"[{key}] {items}")
            result["summary"] = parsed.get("summary", "")
            result["adversarial_details"] = parsed
        except (json.JSONDecodeError, TypeError):
            result["verdict"] = "FAIL"
            result["summary"] = f"LLM 返回非 JSON: {llm_result[:200]}"
            result["issues"].append("对抗性审查结果解析失败")
    else:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        result["verdict"] = "ERROR"
        result["summary"] = "LLM 调用失败（无可用 provider）"

    # 本地禁用词命中强制 FAIL
    if banned:
        result["verdict"] = "FAIL"

    # --- 5. 写 review_log ---
    write_review_log(result, output_path, client_name)

    # --- 6. 输出 ---
    if not quiet or result["verdict"] != "PASS":
        _print_adversarial_review(result, output_path)

    return result


# ============================================================================
# 并行对抗审查（P1：对抗 review 多角色并行）
# 串行 review_adversarial() 是单个挑刺者一次查 5 个角度；并行版拆成 5 路
# 独立挑刺者（各管一个角度）并发执行：
#   - 角度隔离：每路独立角色只挑自己的角度，互不锚定（同常规并行同理）
#   - 单路失败不阻断；findings 合并去重后以 [角度] 前缀展开
# 触发：python _cli.py review <文件> --adversarial --parallel
# ============================================================================

# 5 路挑刺角度：(角度名, 角色, 唯一挑刺角度, 输出 findings 键)
_ADVERSARIAL_DIMENSIONS = (
    ("可反驳论断", "论断挑刺者", "找出可能被客户/评委质疑的论断，附反驳理由", "refutable_claims"),
    ("spec偏差", "一致性挑刺者", "找出产出内容与 spec 摘要的偏差、AI 自作主张的内容", "spec_deviations"),
    ("AI痕迹", "文风挑刺者", "找出禁用词、模板化句式等 AI 痕迹", "ai_traces"),
    ("无依据论断", "事实挑刺者", "找出缺乏事实/数据支撑的关键论断", "unsupported_claims"),
    ("结构完整度", "结构挑刺者", "按组件及格线检查哪些组件缺信息要素", "structure_gaps"),
)


def _build_adversarial_prompt(dim_name, role, focus, ctx):
    """构造单角度挑刺 prompt：只含本角度任务，上下文块共用（provider 前缀缓存友好）。"""
    checklist = "\n".join(f"- {k}: {v}" for k, v in STRUCTURE_CHECKLIST.items())
    extra = ""
    if dim_name == "结构完整度":
        extra = f"\n\n## 结构完整度及格线\n{checklist}"
    return f"""你是{role}。目标只有一个：只从你的角度挑出这份产出中可能被质疑的问题，其他角度与你无关。

## 客户铁律
{ctx["themes_text"]}

## spec 摘要
{ctx["spec_summary"]}

## 产出文件内容（前 {MAX_OUTPUT_CHARS} 字）
{ctx["output_text"]}

## 你的唯一挑刺角度：{focus}{extra}

## 输出格式（严格 JSON，不要解释）
{{"verdict": "PASS" 或 "FAIL", "findings": ["问题1 - 理由", "问题2 - 理由"], "summary": "一句话总结挑刺结果"}}

注意：
- verdict=PASS 仅当从你的角度确实找不到任何问题时；找到任何问题即 FAIL
- 禁止说"整体不错""总体可以"等平衡评价--你是挑刺者，不是打分员
- 若无问题，summary 明确写"未发现问题"
"""


def _adversarial_dimension(dim, ctx):
    """单角度对抗审查（review_adversarial_parallel 线程池调用）。绝不抛异常。"""
    from _cloud_llm import chat, LLM_MODE

    dim_name, role, focus, _key = dim
    prompt = _build_adversarial_prompt(dim_name, role, focus, ctx)
    system = f"你是对抗性审查员（{role}）。只从你的角度挑刺，只返回 JSON，不要解释。"
    max_tokens = 1000 if dim_name == "结构完整度" else 800
    try:
        llm_result = chat(
            prompt=prompt,
            system=system,
            temperature=0.1,
            max_tokens=max_tokens,
            json_mode=True,
            task="adversarial_review",
        )
    except Exception as e:
        return {"dim": dim_name, "error": f"chat 调用异常: {e}"}
    if not llm_result:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        return {"dim": dim_name, "error": "LLM 调用失败（无可用 provider）"}
    try:
        parsed = json.loads(llm_result)
    except (json.JSONDecodeError, TypeError):
        return {"dim": dim_name, "error": f"返回非 JSON: {llm_result[:120]}"}
    findings = parsed.get("findings", [])
    if not isinstance(findings, list):
        findings = [str(findings)]
    return {
        "dim": dim_name,
        "verdict": parsed.get("verdict", "PASS"),
        "findings": findings,
        "summary": parsed.get("summary", ""),
    }


def _merge_adversarial_results(dim_results, banned):
    """汇总多路挑刺结果：findings 合并去重（[角度] 前缀）、verdict、summary。"""
    result = {"verdict": "PASS", "issues": list(banned), "summary": "",
              "mode": "parallel_adversarial"}
    summaries = []
    errors = 0
    for dim_name, _, _, _ in _ADVERSARIAL_DIMENSIONS:
        r = dim_results.get(dim_name)
        if r is None:
            errors += 1
            result["issues"].append(f"维度[{dim_name}] 审查未返回结果")
            continue
        if "error" in r:
            errors += 1
            result["issues"].append(f"维度[{dim_name}] 审查失败: {r['error']}")
            continue
        if r.get("verdict") == "FAIL":
            result["verdict"] = "FAIL"
        for item in r.get("findings", []):
            result["issues"].append(f"[{dim_name}] {item}")
        if r.get("summary"):
            summaries.append(f"{dim_name}: {r['summary']}")

    # issues 去重（保序）
    seen = set()
    deduped = []
    for iss in result["issues"]:
        key = str(iss)
        if key not in seen:
            seen.add(key)
            deduped.append(iss)
    result["issues"] = deduped

    if summaries:
        result["summary"] = "；".join(summaries)[:300]

    # 本地禁用词命中强制 FAIL
    if banned:
        result["verdict"] = "FAIL"

    # 全部维度失败 → ERROR
    if errors >= len(_ADVERSARIAL_DIMENSIONS):
        result["verdict"] = "ERROR"
        result["summary"] = "全部对抗审查维度失败（LLM 不可用）"
    return result


def review_adversarial_parallel(output_path, client_name=None, spec_path=None,
                                quiet=False, max_workers=5):
    """并行对抗审查：多角色挑刺者各查一个角度，并发执行后汇总去重。

    与串行 review_adversarial() 的区别：
    - 串行：单个挑刺者一次查全部角度
    - 并行：每路独立角色独立会话只挑一个角度，互不锚定；单路失败不阻断

    Returns:
        dict: {"verdict": "PASS"|"FAIL"|"ERROR", "issues": [...], "summary": str,
               "mode": "parallel_adversarial"}
    """
    result = {"verdict": "PASS", "issues": [], "summary": "", "mode": "parallel_adversarial"}

    # --- 1-3. 读产出 + 本地禁用词 + 铁律 + spec 摘要（三函数共用 helper） ---
    ctx = _prepare_context(output_path, client_name, spec_path)
    if ctx is None:
        result["verdict"] = "ERROR"
        result["summary"] = f"无法读取文件: {output_path}"
        return result

    # --- 4. 5 路独立挑刺者并行 ---
    from concurrent.futures import ThreadPoolExecutor, as_completed

    dim_results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_dim = {
            pool.submit(_adversarial_dimension, dim, ctx): dim[0]
            for dim in _ADVERSARIAL_DIMENSIONS
        }
        for future in as_completed(future_to_dim):
            dim_name = future_to_dim[future]
            try:
                dim_results[dim_name] = future.result()
            except Exception as e:  # 防御：_adversarial_dimension 不应抛，兜底
                dim_results[dim_name] = {"dim": dim_name, "error": str(e)}

    result.update(_merge_adversarial_results(dim_results, ctx["banned"]))

    # --- 5-6. 写 review_log + 输出（与串行对抗同，不记 decision） ---
    write_review_log(result, output_path, client_name)

    if not quiet or result["verdict"] != "PASS":
        _print_adversarial_review(result, output_path)

    return result


def _print_adversarial_review(result, output_path):
    """格式化打印对抗性审查结果。"""
    verdict = result.get("verdict", "SKIP")
    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "ERROR": "[ERR]"}.get(verdict, "?")

    _safe_print(f"\n{'='*50}")
    _safe_print(f"{icon} 对抗性审查（挑刺者模式）: {verdict}")
    _safe_print(f"   文件: {os.path.basename(output_path)}")
    if result.get("mode") == "parallel_adversarial":
        _safe_print("   模式: 并行多角色挑刺者（角度隔离，防锚定）")

    summary = result.get("summary", "")
    if summary:
        _safe_print(f"   总结: {summary}")

    issues = result.get("issues", [])
    if issues:
        _safe_print(f"   发现问题 ({len(issues)}):")
        for i, iss in enumerate(issues, 1):
            _safe_print(f"     {i}. {iss}")
    else:
        _safe_print("   未发现问题")

    _safe_print(f"{'='*50}\n")
