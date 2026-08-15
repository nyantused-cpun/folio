# -*- coding: utf-8 -*-
"""主题守卫：防止 AI 在长对话中偏离客户铁律。

基于 LLM "lost in the middle" 问题，三层防护：
  数据层（persistence 分类）：decisions.md 中标记 permanent=铁律 / task=临时
  注入层（HEAD）：permanent 主题注入到 AI 上下文开头
  校验层（TAIL）：产出文件必须覆盖 permanent 主题关键词

persistence 三种取值：
  - permanent + client：永久客户约束（跨会话跨任务始终生效）
  - permanent + task：永久任务约束（本次任务全程不变）
  - task：临时任务约束（任务结束归档，默认值，向后兼容）

CLI 标准输出格式（PROJECT_DESIGN.md §4.3）：
  === 核心约束刷新 ===
  [PERMANENT-CLIENT] 7 系统一体化切换，不分阶段
    来源: decisions.md 2026-06-24
  [PERMANENT-TASK] 本次方案使用 KPMG v3 风格
    来源: decisions.md 2026-07-01
"""
import os
import re
from datetime import datetime

from _paths import CLIENTS_DIR

# 决策记录触发词（project_rules.md："记一下"=决策记录，区别于"总结一下"=洞察）
DECISION_TRIGGERS = ["记一下", "记下", "记录一下"]


# ============================================================
# 决策记录（写入 decisions.md，含 persistence 字段）
# ============================================================
def detect_decision_trigger(user_input):
    """检测用户是否要求记录决策（"记一下"）。

    返回 True 时触发决策记录（区别于洞察的"总结一下"）。
    """
    if not user_input:
        return False
    return any(kw in user_input for kw in DECISION_TRIGGERS)


def save_decision(client_name, topic, decision, reason="", alternatives_rejected="",
                  level="L4", persistence="task", scope="client", task_id=None):
    """记录关键决策到 decisions.md。

    记"为什么这么定、为什么不要那个"。
    level: L3/L4/L5，标记决策时的自动化层级
    persistence: permanent（永久）/ task（临时，默认）
    scope: client（客户级）/ task（任务级）
    task_id: scope=task 时必填，任务结束后自动归档
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    client_path = os.path.join(CLIENTS_DIR, client_name)
    if not os.path.exists(client_path):
        os.makedirs(client_path, exist_ok=True)

    decisions_path = os.path.join(client_path, "decisions.md")
    today = datetime.now().strftime("%Y-%m-%d")

    # 格式校验
    if persistence not in ("permanent", "task"):
        persistence = "task"
    if scope not in ("client", "task"):
        scope = "client"
    if scope == "task" and not task_id:
        task_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    entry = f"""
## [{today}] {topic}
- **决策**: {decision}
- **理由**: {reason or '(未记录)'}
- **被否方案**: {alternatives_rejected or '(无)'}
- **层级**: {level}
- **persistence: {persistence}**
- **scope: {scope}**""" + (f"\n- **task_id: {task_id}**" if scope == "task" else "")

    if not os.path.exists(decisions_path):
        with open(decisions_path, "w", encoding="utf-8") as f:
            f.write(f"# {client_name} 决策记录\n")

    with open(decisions_path, "a", encoding="utf-8") as f:
        f.write(entry)

    print(f"已记录决策: {client_name} / {topic} (persistence={persistence}, scope={scope})")
    return decisions_path


# ============================================================
# 主题加载（persistence 分类）
# ============================================================
def load_active_themes(client_name, task_id=None, only_permanent=True):
    """从 decisions.md 提取当前生效的主题。

    persistence 分类：
      - permanent + client → 始终加载（铁律）
      - permanent + task + task_id 匹配 → 加载（本次任务约束）
      - permanent + task + task_id 不匹配 → 不加载
      - task → 仅当 only_permanent=False 且 task_id 匹配时加载
      - **旧无字段（向后兼容）→ 默认 permanent + client**（写进 decisions.md 的本来就是铁律）

    only_permanent=True 时只返回 permanent 主题（用于 HEAD 注入）
    only_permanent=False 时返回所有 task_id 匹配的主题（含临时）

    向后兼容：旧决策无 persistence 字段时，默认按 permanent + client 处理
    （写进 decisions.md 的本来就是客户铁律，不应因字段缺失而失效）

    返回 [{id, theme, description, persistence, scope, task_id, priority, source_date}, ...]
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    decisions_path = os.path.join(CLIENTS_DIR, client_name, "decisions.md")
    if not os.path.exists(decisions_path):
        return []

    with open(decisions_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按 ## [日期] 标题 切块（兼容 ## 决策 N 和 ## [日期] 标题 两种格式）
    blocks = re.split(r'\n## (?:决策 \d+[：:]|\[\d{4}-\d{2}-\d{2}\])', content)
    if len(blocks) < 2:
        return []

    themes = []
    for block in blocks[1:]:
        # 标题：第一行
        title_match = re.match(r'^\s*([^\n]+?)(?:\n|$)', block)
        title = title_match.group(1).strip().rstrip(']') if title_match else ""
        # 处理 "标题]" 残留（被切掉 [日期] 的情况）
        title = title.split(']', 1)[-1].strip() if ']' in title else title
        if not title:
            title = title_match.group(1).strip() if title_match else ""

        # 提取日期（兼容 [YYYY-MM-DD] 标题前缀 和 **日期**：YYYY-MM-DD 内嵌两种格式）
        date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', block)
        if not date_match:
            date_match = re.search(r'[-*]\s*\*{0,2}日期\*{0,2}\s*[：:]\s*(\d{4}-\d{2}-\d{2})', block)
        source_date = date_match.group(1) if date_match else "未知日期"

        # 提取 persistence（缺失默认 permanent，向后兼容旧铁律）
        pers_match = re.search(r'[-*]\s*\*{0,2}persistence\*{0,2}\s*[：:]\s*(\w+)', block)
        persistence = pers_match.group(1).strip().lower() if pers_match else "permanent"

        # 提取 scope（缺失默认 client）
        scope_match = re.search(r'[-*]\s*\*{0,2}scope\*{0,2}\s*[：:]\s*(\w+)', block)
        scope = scope_match.group(1).strip().lower() if scope_match else "client"

        # 提取 task_id
        tid_match = re.search(r'[-*]\s*\*{0,2}task_id\*{0,2}\s*[：:]\s*(\S+)', block)
        block_task_id = tid_match.group(1).strip() if tid_match else None

        # 过滤逻辑
        if persistence == "permanent":
            if scope == "client":
                pass  # 永久客户约束（含旧无字段默认），始终加载
            elif scope == "task":
                if task_id and block_task_id != task_id:
                    continue  # 永久任务约束，task_id 不匹配则跳过
                if not task_id and block_task_id:
                    continue  # 调用方未指定 task_id，但决策有 task_id，跳过
        else:  # persistence=task（临时任务约束）
            if only_permanent:
                continue  # 只取 permanent，跳过临时
            if task_id and block_task_id != task_id:
                continue

        # 提取影响范围作为 description
        impact_match = re.search(r'[-*]\s*\*{0,2}(?:影响范围|impact)\*{0,2}[：:]\s*\n?(.*?)(?=\n\*\*|\n##|\Z)', block, re.DOTALL)
        impact = impact_match.group(1).strip()[:300] if impact_match else ""

        # 提取决策内容
        decision_match = re.search(r'[-*]\s*\*{0,2}决策\*{0,2}\s*[：:]\s*([^\n]+)', block)
        decision_text = decision_match.group(1).strip() if decision_match else ""

        # priority 判定
        priority = "high"
        full_text = title + " " + impact + " " + decision_text
        if re.search(r'(核心|必须|强制|不可|关键|铁律|不允许|禁止|一律)', full_text):
            priority = "critical"

        # 兼容旧字段
        if not impact and decision_text:
            impact = decision_text[:200]

        themes.append({
            "id": f"theme_{len(themes)+1:03d}",
            "theme": title[:80] if title else decision_text[:80],
            "description": impact[:200] if impact else (decision_text[:200] if decision_text else title[:200]),
            "persistence": persistence,
            "scope": scope,
            "task_id": block_task_id,
            "priority": priority,
            "source_date": source_date,
            "impact": impact,
        })

    return themes


def build_head_context(themes):
    """生成 HEAD 文本：核心主题摘要，注入到 AI 上下文开头。

    HEAD 区是注意力密度最高点——放"必须遵守的硬约束"。
    输出格式对齐 PROJECT_DESIGN.md §4.3：
      === 核心约束刷新 ===
      [PERMANENT-CLIENT] 主题
        来源: decisions.md 日期
    """
    if not themes:
        return ""

    lines = ["=== 核心约束刷新 ==="]
    for t in themes:
        if t["persistence"] != "permanent":
            continue
        tag = f"[PERMANENT-{t['scope'].upper()}]"
        lines.append(f"{tag} {t['theme']}")
        lines.append(f"  来源: decisions.md {t['source_date']}")
    lines.append("")
    return "\n".join(lines)


def build_tail_checklist(themes):
    """生成 TAIL 文本：产出前自检清单，注入到上下文末尾。

    TAIL 区是注意力第二高点——放"交付前最后确认的事项"。
    """
    critical = [t for t in themes if t["priority"] == "critical" and t["persistence"] == "permanent"]
    if not critical:
        return ""

    lines = ["## 产出前自检清单（TAIL — 交付前逐项确认）"]
    for i, t in enumerate(critical, 1):
        lines.append(f"- [ ] 第{i}项「{t['theme']}」—— 产出中是否已体现？")
    lines.append("")
    return "\n".join(lines)


def check_coverage(output_text, themes):
    """检查产出文本是否覆盖了所有 permanent 主题。

    v2.0 算法（关键词匹配，可解释且快速）：
    1. 提取每条 permanent 主题的关键词
    2. 检查关键词是否出现在产出文件内容中
    3. 命中 ≥1 个关键词即算覆盖
    4. 输出未覆盖的主题列表及来源
    """
    if not themes or not output_text:
        return {"covered": [], "missing": [], "warnings": []}

    # 只检查 permanent 主题（铁律）
    permanent = [t for t in themes if t["persistence"] == "permanent"]
    if not permanent:
        return {"covered": [], "missing": [], "warnings": []}

    covered = []
    missing = []

    for t in permanent:
        # 提取关键词（中文 2 字以上 / 英文 3 字以上）
        keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}', t["theme"])
        # 去除常见无意义词
        stop_words = {"系统", "方案", "管理", "本次", "本次方案"}
        # 逐字符检查 stop_words（解决贪婪正则导致整个词被作为一个 token 的问题）
        filtered = []
        for kw in keywords:
            if kw in stop_words:
                continue
            # 检查 kw 是否包含任何 stop_word（子串匹配），仅对短关键词剥离
            if any(sw in kw for sw in stop_words) and len(kw) <= 4:
                # 对包含 stop_word 的关键词，去掉 stop_word 部分后保留剩余
                remaining = kw
                for sw in stop_words:
                    remaining = remaining.replace(sw, "")
                if len(remaining) >= 2:
                    filtered.append(remaining)
                else:
                    filtered.append(kw)  # 去掉后太短，保留原词
            else:
                filtered.append(kw)
        keywords = filtered
        if not keywords:
            # 兜底：用主题原文前 4 字（但跳过纯 stop_words 的情况）
            fallback = t["theme"][:4]
            if fallback in stop_words:
                # 如果前 4 字仍是 stop_word，用完整 theme 名
                fallback = t["theme"]
            keywords = [fallback]

        hits = sum(1 for kw in keywords if len(kw) >= 2 and kw in output_text)
        if hits >= 1:
            covered.append(t)
        else:
            missing.append(t)

    warnings = []
    if missing:
        warning_lines = ["以下 permanent 主题在产出中未覆盖："]
        for m in missing:
            warning_lines.append(f"  - {m['theme']}")
            warning_lines.append(f"    来源: decisions.md {m['source_date']}")
            warning_lines.append(f"    诉求: {m['description'][:100]}")
        warnings = ["\n".join(warning_lines)]

    return {"covered": covered, "missing": missing, "warnings": warnings}


def pre_check(client_name, task_id=None):
    """IDE 钩子：一键加载主题 + 生成头尾上下文。

    供 AI 在会话开始时调用，也供 _style_guard.pre_check() 集成。
    生成产出物时 CLI 命令（html-build/ppt-build/docx-build）内部强制调本函数。

    返回 schema:
    {
        "client_name": str,
        "task_id": str | None,
        "themes": list,              # 完整 permanent 主题列表
        "permanent_client": list,    # 永久客户约束
        "permanent_task": list,      # 永久任务约束（仅 task_id 匹配的）
        "head_context": str,         # HEAD 文本（注入上下文开头）
        "tail_checklist": str,       # TAIL 文本（注入上下文末尾）
        "critical_count": int,       # critical 主题数
        "warnings": list,
    }
    """
    warnings = []
    try:
        themes = load_active_themes(client_name, task_id, only_permanent=True)
    except Exception as e:
        warnings.append(f"load_active_themes 失败: {e}")
        themes = []

    permanent_client = [t for t in themes if t["scope"] == "client"]
    permanent_task = [t for t in themes if t["scope"] == "task"]

    head_ctx = build_head_context(themes)
    tail_cl = build_tail_checklist(themes)
    critical_count = sum(1 for t in themes if t["priority"] == "critical")

    return {
        "client_name": client_name,
        "task_id": task_id,
        "themes": themes,
        "permanent_client": permanent_client,
        "permanent_task": permanent_task,
        "head_context": head_ctx,
        "tail_checklist": tail_cl,
        "critical_count": critical_count,
        "warnings": warnings,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("主题守卫 CLI：")
        print("  python _theme_guard.py <客户名> [task_id]    输出当前生效 permanent 主题")
        print("  python _theme_guard.py check <客户名> <文件>  检查产出覆盖")
        print("AI 调用推荐：python _cli.py theme-guard <客户> [--task-id <ID>]")
        sys.exit(0)

    action = sys.argv[1]

    if action == "check":
        # 兼容旧调用：python _theme_guard.py check <客户> <文件>
        client = sys.argv[2] if len(sys.argv) >= 3 else None
        file_path = sys.argv[3] if len(sys.argv) >= 4 else None
        if not client or not file_path:
            print("用法: python _theme_guard.py check <客户> <文件路径>")
            sys.exit(1)
        themes = load_active_themes(client)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"读取文件失败: {e}")
            sys.exit(1)
        result = check_coverage(text, themes)
        print(f"=== 主题覆盖检查：{file_path} ===")
        print(f"已覆盖 {len(result['covered'])} 条，缺失 {len(result['missing'])} 条\n")
        if result["covered"]:
            print("[OK] 已覆盖:")
            for t in result["covered"]:
                print(f"  - {t['theme']}")
        if result["missing"]:
            print("\n[FAIL] 缺失:")
            for t in result["missing"]:
                print(f"  - {t['theme']}")
                print(f"    来源: decisions.md {t['source_date']}")
                print(f"    {t['description'][:100]}")
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"\n{w}")
    else:
        # 默认：python _theme_guard.py <客户> [task_id]
        client = action
        task_id = sys.argv[2] if len(sys.argv) >= 3 else None
        if not client:
            print("请提供客户名")
            sys.exit(1)
        result = pre_check(client, task_id)
        if result["head_context"]:
            print(result["head_context"])
        else:
            print(f"=== {client} 无 permanent 主题 ===")
        if result["tail_checklist"]:
            print()
            print(result["tail_checklist"])
        if result["warnings"]:
            print("[warn] 警告:")
            for w in result["warnings"]:
                print(f"  - {w}")
