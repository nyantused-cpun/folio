# -*- coding: utf-8 -*-
"""并行审查两族（维度并行 + 并行对抗）——自 _review.py 拆出（WP-A5，2026-09-08 R1）。

拆分动因：_review.py 触及 1200 行体量闸门（_project_map WARN_LINES），WP-A5
增量审查还需新增模块面；并行两族与串行主链只共用前置/收尾 helper，无反向
依赖，是自包含的搬出单元。

依赖纪律：对 _review 的共用件（_prepare_context/_finalize_review/
write_review_log/_print_adversarial_review/_parse_review_json/
_review_llm_kwargs/常量）一律**函数内 import**——_review.py 尾部会 re-export
本模块符号以保持既有 import 面（tests 直接引用 _review.review_parallel 等），
顶层 import 会在「外部先加载本模块」时撞上半成品 _review；函数内 import
同时保持测试 monkeypatch（_cloud_llm.chat / _review.write_review_log）语义。

触发：
- python _cli.py review <文件> --parallel                 → review_parallel
- python _cli.py review <文件> --adversarial --parallel   → review_adversarial_parallel
"""
import json


# ============================================================================
# 并行审查模式（维度级并行，2026-08 起）
# 与串行 review()（一次调用查全部维度）不同，并行模式把 5 个维度拆成
# 5 路独立 LLM 会话并发执行：
#   - 维度隔离：每路独立角色、独立 prompt 只查自己维度，防注意力稀释
#     与维度间锚定（一路 PASS 暗示其他路 PASS 的自证偏差）
#   - 单路失败不阻断：某一路 provider 失败只记该路 ERROR，其余维度照常汇总
#   - 平台无关：用 _cloud_llm 独立会话 + 线程池内建，不依赖宿主子代理
#     （Kimi 禁用子代理、Trae 形态不同，宿主子代理只适合会话级人工拉起）
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
    from _review import MAX_OUTPUT_CHARS, STRUCTURE_CHECKLIST
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
    from _review import _parse_review_json, _review_llm_kwargs

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
            **_review_llm_kwargs(),
        )
    except Exception as e:
        return {"dim": dim_name, "error": f"chat 调用异常: {e}"}
    if not llm_result:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        return {"dim": dim_name, "error": "LLM 调用失败（无可用 provider）"}
    try:
        parsed = _parse_review_json(llm_result)
    except (json.JSONDecodeError, TypeError):
        return {"dim": dim_name, "error": f"返回非 JSON: {llm_result[:120]}"}
    issues = parsed.get("issues", [])
    if not isinstance(issues, list):
        issues = [str(issues)]
    out = {
        "dim": dim_name,
        # P1 双向判分：维度返回缺 verdict 字段不得当 PASS（与串行统一）
        "verdict": parsed.get("verdict", "FAIL"),
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
    # scores 缺失（五维打分路失败/未返回）或缺"总分"时不做比较，避免 0 分误判。
    scores = result.get("scores") or {}
    total = scores.get("总分")
    if isinstance(total, (int, float)) and total < 15 and result["verdict"] == "PASS":
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
    from _review import _finalize_review, _prepare_context

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


# ============================================================================
# 并行对抗审查（P1：对抗 review 多角色并行）
# 串行 review_adversarial() 是单个挑刺者一次查 5 个角度；并行版拆成 5 路
# 独立挑刺者（各管一个角度）并发执行：
#   - 角度隔离：每路独立角色只挑自己的角度，互不锚定（同常规并行同理）
#   - 单路失败不阻断；findings 合并去重后以 [角度] 前缀展开
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
    from _review import MAX_OUTPUT_CHARS, STRUCTURE_CHECKLIST
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
    from _review import _parse_review_json, _review_llm_kwargs

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
            **_review_llm_kwargs(),
        )
    except Exception as e:
        return {"dim": dim_name, "error": f"chat 调用异常: {e}"}
    if not llm_result:
        if LLM_MODE == "host":
            print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
        return {"dim": dim_name, "error": "LLM 调用失败（无可用 provider）"}
    try:
        parsed = _parse_review_json(llm_result)
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
    from _review import (_print_adversarial_review, _prepare_context,
                         write_review_log)

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
