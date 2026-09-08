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
import time
import yaml
from datetime import datetime

import _paths


# 去 AI 化禁用词（单一数据源在 _paths.py）
from _paths import BANNED_WORDS, BANNED_PHRASES

# F5-2：review 允许独立模型（默认与生成同 provider；显式 REVIEW_PROVIDER/REVIEW_MODEL 可分离）


def _parse_review_json(text):
    """容错解析 review LLM 返回：剥 ```json 围栏、截取首个 { 至末个 }。

    2026-09-03：minimax 实测返回带 markdown 围栏且尾部带散文，裸 json.loads 失败
    被判「解析失败」FAIL。截断（括号不闭合）仍会上抛，由调用方兜底。
    """
    import json
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    i, j = t.find("{"), t.rfind("}")
    if 0 <= i < j:
        t = t[i:j + 1]
    parsed = json.loads(t)
    # P3 fail-closed：LLM 返回顶层数组/标量时视为解析失败（曾放行到调用方
    # parsed.get() 抛 AttributeError，逃逸 except (JSONDecodeError, TypeError)
    # 且不写 review_log）。对齐本文件既有解析失败语义：走 FAIL 路径。
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("review 返回顶层不是 JSON 对象", t, 0)
    return parsed


def _review_llm_kwargs():
    """返回 review 专用 LLM 覆盖参数（仅设置非空值，默认不改变现有 fallback）。"""
    kwargs = {}
    provider = os.environ.get("REVIEW_PROVIDER", "")
    model = os.environ.get("REVIEW_MODEL", "")
    if provider:
        kwargs["provider"] = provider
    if model:
        kwargs["model"] = model
    return kwargs


# 产出文本截断上限（字符数），防止超长 prompt。
# 2026-09-03 实测订正：deck 纯文本其实很短（7 页 ≈1.9K 字符），此前的
# "缺页/图形占位"假阴性根因是 p07 缺 SECTION 标记 + dg-eyebrow 类型眉标被误读，
# 已通过图形渲染机检清单注入修复；盲目放大窗口会让 thinking provider 思考
# 链爆炸撞 max_tokens 上限（12000 仍 length）。12000 覆盖 15 页级 deck。
MAX_OUTPUT_CHARS = 12000

# 结构完整度及格线（A-4 第 5 维，来源 presentation-content-design
# references/quality-gate.md；新组件上线时必须同步，维护约定见 B-3~B-7 任务卡）
STRUCTURE_CHECKLIST = {
    "叙事组件": "判断 + 解释 + 例证，三件套齐",
    "指标组件": "单位 + 周期 + 语境 + 变化原因，可追溯",
    "流程时序": "参与方 + 动作 + 状态 + 输入输出 + 异常支路",
    "架构图": "真实实体 + 边界 + 接口 + 流向",
    "数据图表": "口径 + 单位 + 刻度 + 标签 + 业务解释",
    "图形化表达": "关键关系页应有 diagram/table/结构化组件，而非纯文字/卡片堆砌",
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
            elif etype == "diagram":
                elem_summaries.append(
                    f"  图形: {el.get('diagram_type')}/{el.get('subtype')} · {el.get('title','')}")
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
        # 先剔除 style/script 块内容（CSS/JS 规则不是可见正文；否则 CSS 会占满
        # MAX_OUTPUT_CHARS 截断窗口，review LLM 只见样式不见内容 → 假阴性 FAIL）
        raw = re.sub(r"<(style|script)\b[^>]*>.*?</\1\s*>", " ", raw, flags=re.S | re.I)
        # 再剔除 head 整体（meta/link/title 等非正文）
        raw = re.sub(r"<head\b[^>]*>.*?</head\s*>", " ", raw, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:MAX_OUTPUT_CHARS]
    else:
        return raw[:MAX_OUTPUT_CHARS]


# W1-4（#41，2026-09-06 B6 Wave1）：review_log 并发写保护。原实现无锁整文件
# 重写，双会话并发写触发 Windows sharing violation（实测 15:56 后写入全拒）。
# 复用项目现有 _save_lock 原子创建语义（O_CREAT|O_EXCL，fd 持有即活性证据），
# 锁文件 .review_log.lock 与日志同目录；读-合并-写全程持锁。锁获取失败重试
# 1 次（间隔 1s），最终失败 print 明确警告但维持「不阻断」语义——审查结论
# 不因日志写入失败而中断（由 audit 报计数兜底）。
REVIEW_LOG_LOCK_NAME = ".review_log.lock"
REVIEW_LOG_LOCK_TIMEOUT = 5.0      # 首次获取超时（秒）
REVIEW_LOG_LOCK_RETRY_TIMEOUT = 10.0  # 重试一次的超时（秒）


def write_review_log(result, output_path, client_name):
    """把 review 结果追加到 review_log.json（独立日志，不写 task_history）。

    见 spec 5.1.1 + 破坏点 3：review 在 generate 内部自动调用，
    generate 不调 save_session 不写 task_history，故用独立日志。
    W1-4：读-合并-写全程持有 .review_log.lock，消双会话并发 sharing violation。
    """
    log_path = _paths.REVIEW_LOG
    logs_dir = os.path.dirname(log_path)
    from _save_lock import acquire_save_lock, release_save_lock
    lock_fd = acquire_save_lock(logs_dir, timeout=REVIEW_LOG_LOCK_TIMEOUT,
                                lock_name=REVIEW_LOG_LOCK_NAME)
    if lock_fd is None:
        # 锁获取失败重试 1 次（间隔 1s）
        time.sleep(1.0)
        lock_fd = acquire_save_lock(logs_dir, timeout=REVIEW_LOG_LOCK_RETRY_TIMEOUT,
                                    lock_name=REVIEW_LOG_LOCK_NAME)
    if lock_fd is None:
        print(f"[review] review_log 写入失败（不阻断）: {REVIEW_LOG_LOCK_NAME} "
              f"获取失败（双会话并发冲突），本条审查结果未落 review_log")
        return
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
            # S9-2a：模式与截图审视轮次（screenshot_adversarial 轮次计数持久化源）
            "mode": result.get("mode", ""),
            # WP-A5：审查注入面（full=全文 / incremental=变更页全文+未变更页轻摘要）
            "review_mode": result.get("review_mode"),
            "screenshot_review_rounds": result.get("screenshot_review_rounds"),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        os.makedirs(logs_dir, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[review] review_log 写入失败（不阻断）: {e}")
    finally:
        release_save_lock(logs_dir, lock_fd, lock_name=REVIEW_LOG_LOCK_NAME)


def _extract_diagram_inventory(output_path):
    """从 HTML 提取 diagram 渲染清单（机检事实，注入 review prompt）。

    纯文本抽取后图形页只剩类型眉标+单元格文字，reviewer 易误判"占位/未渲染"
    （2026-09-03 实测两轮假阴性 FAIL）。用 data-* 属性给 reviewer 地面真值。
    """
    import re
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return ""
    if not output_path.lower().endswith((".html", ".htm")):
        return ""
    items = []
    for m in re.finditer(
            r'data-diagram-type="([^"]+)"\s+data-subtype="([^"]+)"', raw):
        tail = raw[m.end():m.end() + 600]
        t = re.search(r'class="dg-title"[^>]*>(.*?)</div>', tail, re.S)
        title = re.sub(r"<[^>]+>", "", t.group(1)).strip() if t else "未命名"
        items.append(f"- {m.group(1)}/{m.group(2)}「{title}」（已渲染图形区块）")
    if not items:
        return ""
    return ("【图形渲染机检清单】以下 diagram 已在 HTML 中实际渲染（提取自 "
            "data-diagram-type 属性，可信，勿判「占位/未渲染」）：\n"
            + "\n".join(items) + "\n\n")


def _prepare_context(output_path, client_name, spec_path):
    """读产出 + 本地禁用词检查 + 客户铁律 + spec 摘要。

    review / review_parallel / review_adversarial 三函数共用的前置步骤。
    返回 dict（output_text/banned/themes_text/spec_summary）；产出不可读时返回 None。
    """
    output_text = _read_output_text(output_path)
    if output_text is None:
        return None
    output_text = _extract_diagram_inventory(output_path) + output_text
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
            written = save_decision(
                client_name=client_name,
                topic=f"review FAIL: {os.path.basename(output_path)}",
                decision=f"产出 {output_path} 审查未通过",
                reason=issues_text[:500],
            )
            if written is None:
                print("[review] save_decision 未写入（保存锁获取失败，不阻断审查结论）")
        except Exception as e:
            print(f"[review] save_decision 失败（不阻断）: {e}")

    if not quiet or result["verdict"] != "PASS":
        _print_review(result, output_path)


# ============================================================================
# W1-2 审查预算熔断（2026-09-06 B6 Wave1）
# 现状：审查 ERROR（LLM 不可得）后无熔断，连续重试白烧 token（实测一次
# ERROR 四连烧 40.5K）。熔断语义：同客户同日连续 ≥3 次 ERROR → 不再发起
# LLM 调用直接返回 ERROR。ERROR≠FAIL：内容未必有问题，是审查服务不可得。
# 状态落盘 .folio/logs/review_budget.json（{client: {date, consecutive_errors}}），
# PASS/FAIL 归零；跨日（date 变化）自动重置。路径做成独立函数便于测试注入。
# ============================================================================

REVIEW_BUDGET_MAX_ERRORS = 3

# S6（2026-09-07）：预算状态读-合并-写持锁。复用 review_log 锁先例
# （W1-4）：同一 _save_lock 机制、独立锁文件、获取失败重试 1 次后降级
# 「不阻断」——熔断计数丢失不中断审查结论（由 audit 报计数兜底）。
REVIEW_BUDGET_LOCK_NAME = ".review_budget.lock"
REVIEW_BUDGET_LOCK_TIMEOUT = 5.0
REVIEW_BUDGET_LOCK_RETRY_TIMEOUT = 10.0


def _review_budget_path():
    """审查预算状态文件路径（独立函数：测试 monkeypatch 到 tmp 隔离）。"""
    return os.path.join(_paths.LOGS_DIR, "review_budget.json")


def _budget_date():
    return datetime.now().strftime("%Y-%m-%d")


def _read_budget(client_name):
    """读该客户当日预算状态；文件缺失/损坏/跨日一律按归零处理。"""
    try:
        with open(_review_budget_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get(client_name or "")
        if not isinstance(entry, dict):
            return {"date": _budget_date(), "consecutive_errors": 0}
        if entry.get("date") != _budget_date():
            return {"date": _budget_date(), "consecutive_errors": 0}  # 跨日重置
        errors = entry.get("consecutive_errors", 0)
        if not isinstance(errors, int) or errors < 0:
            errors = 0
        return {"date": entry.get("date"), "consecutive_errors": errors}
    except Exception:
        return {"date": _budget_date(), "consecutive_errors": 0}


def _write_budget(client_name, entry):
    """按客户键写预算状态（保留其他客户条目）；失败只告警不阻断。

    S6：读-合并-写全程持 .review_budget.lock（双会话并发不再丢熔断计数）。
    """
    path = _review_budget_path()
    logs_dir = os.path.dirname(path)
    from _save_lock import acquire_save_lock, release_save_lock
    lock_fd = acquire_save_lock(logs_dir, timeout=REVIEW_BUDGET_LOCK_TIMEOUT,
                                lock_name=REVIEW_BUDGET_LOCK_NAME)
    if lock_fd is None:
        # 锁获取失败重试 1 次（间隔 1s）
        time.sleep(1.0)
        lock_fd = acquire_save_lock(logs_dir,
                                    timeout=REVIEW_BUDGET_LOCK_RETRY_TIMEOUT,
                                    lock_name=REVIEW_BUDGET_LOCK_NAME)
    if lock_fd is None:
        print(f"[review] 预算状态写入失败（不阻断）: {REVIEW_BUDGET_LOCK_NAME} "
              f"获取失败（双会话并发冲突），本条熔断计数未落盘")
        return
    try:
        data = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        data[client_name or ""] = entry
        os.makedirs(logs_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[review] 预算状态写入失败（不阻断）: {e}")
    finally:
        release_save_lock(logs_dir, lock_fd, lock_name=REVIEW_BUDGET_LOCK_NAME)


def _budget_fused_result(client_name):
    """同日连续 ERROR 达阈值 → 返回熔断 ERROR result（调用方不得再发起 LLM 调用）；否则 None。"""
    errors = _read_budget(client_name).get("consecutive_errors", 0)
    if errors < REVIEW_BUDGET_MAX_ERRORS:
        return None
    return {
        "verdict": "ERROR",
        "issues": [],
        "summary": (f"审查预算熔断：连续 {errors} 次审查不可得——ERROR≠FAIL"
                    "（内容未必有问题，是审查服务不可得），请稍后重试或人工审查"),
    }


def _budget_record(client_name, verdict):
    """review 出结果后记账：ERROR 累加；PASS/FAIL/SKIP 归零（仅有残留计数时写盘）。"""
    errors = _read_budget(client_name).get("consecutive_errors", 0)
    if verdict == "ERROR":
        _write_budget(client_name, {"date": _budget_date(),
                                    "consecutive_errors": errors + 1})
    elif errors:
        _write_budget(client_name, {"date": _budget_date(),
                                    "consecutive_errors": 0})


def review(output_path, client_name=None, spec_path=None, quiet=False, output_text=None):
    """独立审查产出物。

    Args:
        output_path: 产出文件路径
        client_name: 客户名（用于加载铁律）
        spec_path: spec.yml 路径（用于内容一致性检查）
        quiet: True 时只在有问题时打印
        output_text: LLM 注入文本覆盖（WP-A5 增量审查专用；None=读文件全文，
            现行为不变）。只覆盖 prompt 注入面——机械禁用词检查（_prepare_context
            内对全文跑）不受影响，符合「机检全量、LLM 增量」设计约束。

    Returns:
        dict: {"verdict": "PASS"|"FAIL"|"SKIP"|"ERROR", "issues": [...], "summary": str}
    """
    result = {"verdict": "SKIP", "issues": [], "summary": ""}

    # W1-2：进入即查预算熔断——同日连续 ≥3 次 ERROR 不再发起 LLM 调用，
    # 直接返回 ERROR（仍走收尾写日志，保持 review_log 闭环）
    fused = _budget_fused_result(client_name)
    if fused is not None:
        _finalize_review(fused, output_path, client_name, quiet)
        return fused

    # --- 1-3. 读产出 + 本地禁用词 + 铁律 + spec 摘要（三函数共用 helper） ---
    ctx = _prepare_context(output_path, client_name, spec_path)
    if ctx is None:
        result["verdict"] = "ERROR"
        result["summary"] = f"无法读取文件: {output_path}"
        return result

    if output_text is not None:
        ctx["output_text"] = output_text
    result["review_mode"] = "incremental" if output_text is not None else "full"

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
5. **防 monitor evasion（反逃避）**：如果产出中出现的“修复”是删除/削弱验证、收窄测试范围、
   降低阈值、移除断言等行为，必须判定为 gaming（规避审查/监控），不算真正的修复，verdict 应为 FAIL。
   真正修复应保留或增强验证物，而不是降低验证强度。

## 五维度打分（每维度 1-5 分，总分 25 分）
- **设计质量**：是否感觉像一个连贯整体，结构清晰、层次分明
- **原创性**：是否有定制决策证据，而非模板默认
- **工艺**：技术执行--字体层次、间距一致性、色彩协调
- **功能性**：用户能否理解内容、找到关键信息、达到目的
- **结构完整度**：按组件类型检查信息要素是否齐全（及格线见下），缺要素扣分

## 结构完整度及格线
{checklist}

## 输出格式（严格 JSON）
issues 每条一句话（≤60 字），最多 10 条；summary ≤80 字；不要复述原文。
{{"verdict": "PASS" 或 "FAIL", "scores": {{"设计": N, "原创": N, "工艺": N, "功能": N, "结构": N, "总分": N}}, "issues": ["问题1", "问题2"], "theme_coverage": {{"覆盖数": N, "未覆盖": ["铁律1"]}}, "summary": "一句话总结"}}"""

    system = "你是方案审查员。严格按审查要求逐项检查，不放过任何问题。只返回 JSON，不要解释。"

    llm_result = chat(
        prompt=prompt,
        system=system,
        temperature=0.1,
        # P0-1（2026-07-21）：chat() 对 thinking provider 自动加 reasoning 余量
        #（×3，下限 4000）+ finish_reason=length 加倍重试，无需在此逐 task 调参
        # 2026-09-03：1000→2000，30K 输入窗口下审查输出变长，4000 余量不够
        # 2026-09-06 W1-1（#37）：2000→3000（effective 9000，拉开与 12000 重试线
        # 的距离减少首撞）；reasoning 强度降档由 _cloud_llm.TASK_THINKING_OVERRIDE 承接
        max_tokens=3000,
        json_mode=True,
        task="post_generate_review",
        **_review_llm_kwargs(),
    )

    if llm_result:
        try:
            parsed = _parse_review_json(llm_result)
            parsed_issues = parsed.get("issues", [])
            # P1 双向判分：LLM JSON 缺 verdict 字段不得缺省 PASS 放行（fail-open → fail-closed）
            result["verdict"] = parsed.get("verdict", "FAIL")
            # 用 extend 而非赋值：保留本地 _check_banned 的命中结果（避免 LLM 返回空 issues 覆盖本地禁用词检查）
            if isinstance(parsed_issues, list):
                result["issues"].extend(parsed_issues)
            else:
                result["issues"].append(str(parsed_issues))
            result["summary"] = parsed.get("summary", "")
            result["theme_coverage"] = parsed.get("theme_coverage", {})
            result["scores"] = parsed.get("scores", {})
            # 低分自动 FAIL（总分低于 15/25）；scores 缺失或非数值时不做比较
            #（曾 .get("总分", 0)——缺 scores 误报"总分 0 低于阈值"）
            total = result["scores"].get("总分")
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

    # W1-2：出结果后记账（ERROR 累加 / PASS-FAIL 重置）。只记走到 LLM 之后的
    # 结果——上文「无法读取文件」的 ERROR 早退不经过此处（不烧 token 不计熔断）
    _budget_record(client_name, result["verdict"])

    # --- 5-6. 写 review_log + FAIL 记 decision + 输出（串行/并行共用） ---
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
        # P5：长文本创作循环——stdout 只打印前 10 条，完整清单在 review_log.json，
        # 避免 DSH tool-result-pruner（8192 字符）把中间问题截掉
        shown = issues[:10]
        for i, iss in enumerate(shown, 1):
            _safe_print(f"     {i}. {iss}")
        if len(issues) > 10:
            _safe_print(f"     … 完整 {len(issues)} 条见 {_paths.REVIEW_LOG}")

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
        **_review_llm_kwargs(),
    )

    if llm_result:
        try:
            parsed = _parse_review_json(llm_result)
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
        # P5：长文本创作循环——stdout 只打印前 10 条，完整清单在 review_log.json
        shown = issues[:10]
        for i, iss in enumerate(shown, 1):
            _safe_print(f"     {i}. {iss}")
        if len(issues) > 10:
            _safe_print(f"     … 完整 {len(issues)} 条见 {_paths.REVIEW_LOG}")
    else:
        _safe_print("   未发现问题")

    _safe_print(f"{'='*50}\n")


# ============================================================================
# S9-2a（发版稳定版，2026-09-07）截图对抗审视共享层：轮次上限 + review_log 读侧。
# 重实现（playwright 截图渲染 + VLM 提示词/解析）在 _review_screenshot.py，
# 本模块只放单一事实源常量与可复用判定函数（创作子代理派发循环 2c 与
# crafted-track.md 文档引用此处，不复制逻辑）。
# ============================================================================

# 修正循环上限：对齐创作子代理「派发-重派 ≤3 轮」（crafted-track stage 2c）。
SCREENSHOT_MAX_ROUNDS = 3


def screenshot_round_decision(prior_rounds):
    """按已完成截图审视轮数判定「允许重派/熔断」（纯函数，2c 派发循环可复用）。

    prior_rounds < SCREENSHOT_MAX_ROUNDS → {"action": "allow", "rounds_left": N}；
    ≥ SCREENSHOT_MAX_ROUNDS → {"action": "fuse", "reason": ...}。
    诚实上限：VLM 会漏细节、不承诺收敛——到顶熔断是流程护栏，不是质量承诺。
    """
    prior = prior_rounds if isinstance(prior_rounds, int) and prior_rounds >= 0 else 0
    if prior < SCREENSHOT_MAX_ROUNDS:
        return {"action": "allow", "rounds_done": prior,
                "rounds_left": SCREENSHOT_MAX_ROUNDS - prior}
    return {"action": "fuse", "rounds_done": prior, "rounds_left": 0,
            "reason": (f"截图审视修正已达 {SCREENSHOT_MAX_ROUNDS} 轮上限（重派熔断）；"
                       "VLM 会漏细节、不承诺收敛，余下问题转人工目检")}


def read_review_log():
    """读 review_log.json 全量条目（write_review_log 的读侧对偶）。

    文件缺失/损坏/顶层非列表一律返回 []（读侧容错，语义同 _read_budget）；
    路径每次调用时取 _paths.REVIEW_LOG——测试 monkeypatch 该属性即可隔离。
    """
    try:
        with open(_paths.REVIEW_LOG, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception:
        return []
    return entries if isinstance(entries, list) else []


# ============================================================================
# WP-A5 拆小（2026-09-08，剩余修复计划 R1）：并行两族（维度并行/并行对抗）
# 搬至 _review_parallel.py。此处 re-export 保持既有 import 面——tests 直接
# 引用 _review.review_parallel / _PARALLEL_DIMENSIONS 等；测试 mock 打在
# _cloud_llm.chat 与本模块 write_review_log 上，搬出侧全部函数内 import，
# patch 语义不变。 folio 侧 R2 同步批带出。
# ============================================================================
from _review_parallel import (  # noqa: E402,F401
    _ADVERSARIAL_DIMENSIONS,
    _PARALLEL_DIMENSIONS,
    _adversarial_dimension,
    _build_adversarial_prompt,
    _build_dimension_prompt,
    _merge_adversarial_results,
    _merge_parallel_results,
    _review_dimension,
    review_adversarial_parallel,
    review_parallel,
)


def resolve_review_fn(args):
    """review 命令分派（自 _cli_generate.cmd_review 外移，WP-A5 拆小 R1）。

    返回 (审查函数, 模式提示)；提示为 None 时调用方不打模式行。
    --incremental 与其余模式互斥（增量=同文件迭代复审的 opt-in 优化，
    不与并行/对抗/截图组合），命中即优先返回并提示。
    """
    if getattr(args, "incremental", False):
        from _review_incremental import review_incremental
        return (review_incremental,
                "[review] 增量审查模式（未变更页轻摘要+变更页全文，每 3 轮强制全量；首审无基线自动全量）")
    if getattr(args, "screenshot", False):
        from _review_screenshot import review_screenshot_adversarial
        return review_screenshot_adversarial, None
    adversarial = getattr(args, "adversarial", False)
    parallel = getattr(args, "parallel", False)
    if adversarial and parallel:
        return (review_adversarial_parallel,
                "[review] 并行对抗审查模式（5 路独立挑刺者各查一个角度，单路失败不阻断）")
    if adversarial:
        return (review_adversarial,
                "[review] 对抗性审查模式（挑刺者角色，借鉴 Claude Dynamic Workflows adversarial verification）")
    if parallel:
        return (review_parallel,
                "[review] 并行审查模式（5 路独立会话，维度隔离防锚定，单路失败不阻断）")
    return review, None
