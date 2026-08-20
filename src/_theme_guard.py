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

import _memory_guard
from _paths import CLIENTS_DIR

# 决策记录触发词（project_rules.md："记一下"=决策记录，区别于"总结一下"=洞察）
DECISION_TRIGGERS = ["记一下", "记下", "记录一下"]

# 最近一次 load_active_themes 跳过的未决冲突/已废弃条目数（count_skipped_conflicts 读取）
_LAST_SKIPPED_CONFLICTS = 0

# 已废弃状态行（resolve_conflict 写入后，load_active_themes 据此跳过，防矛盾铁律双加载）
_DEPRECATED_RE = re.compile(r'[-*]\s*\*{0,2}状态\*{0,2}\s*[：:]\s*已废弃')


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


def _append_conflict_flag(decisions_path, old_date, topic):
    """在旧条目块的块尾插入未决冲突标记 `<!-- conflict: pending -->`。

    精确块定位：`## [old_date] topic` 标题到下一个 `## ` 标题前（或文件尾）。
    只插标记、不改正文；幂等（块内已有标记则不重复）；找不到旧块则静默返回。
    """
    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return  # 文件不存在/读取失败 -> 无处可插
    wanted = str(topic).strip()
    wanted_date = str(old_date).strip()
    heading_re = re.compile(r'^## \[(\d{4}-\d{2}-\d{2})\]\s*(.*?)\s*$', re.MULTILINE)
    for m in heading_re.finditer(content):
        if m.group(1) != wanted_date:
            continue
        if m.group(2).strip() != wanted:
            continue
        tail = re.search(r'^## ', content[m.end():], re.MULTILINE)
        insert_at = m.end() + tail.start() if tail else len(content)
        block = content[m.start():insert_at]
        if "<!-- conflict: pending -->" in block:
            return  # 幂等：已有标记
        content = content[:insert_at] + "\n<!-- conflict: pending -->\n" + content[insert_at:]
        with open(decisions_path, "w", encoding="utf-8") as f:
            f.write(content)
        return  # 只处理第一个匹配的旧块


def _build_source_line(source, client_name, strict):
    """校验 source 引用串，返回来源行文本。

    strict 且存在验不过的引用 -> 抛 ValueError（写入前，什么都不落盘）。
    非 strict -> 照写，行尾追加「（证据待核：第一条失败原因）」。
    user: 引用天然免校验（verify_source_ref 语义）。
    """
    if not source:
        print("[决策] 未携带来源引用（source 参数可补）")
        return "(待补)"
    refs = _memory_guard.parse_source_refs(source)
    failed = []
    for ref in refs:
        ok, reason = _memory_guard.verify_source_ref(ref, client_name)
        if not ok:
            failed.append(reason)
    if failed:
        if strict:
            raise ValueError("证据待核，拒绝写入: " + "；".join(failed))
        return f"{source}（证据待核：{failed[0]}）"
    return source


def save_decision(client_name, topic, decision, reason="", alternatives_rejected="",
                  level="L4", persistence="task", scope="client", task_id=None,
                  source="", confidence=0.5, strict=False):
    """记录关键决策到 decisions.md（含溯源 + 冲突保留）。

    记"为什么这么定、为什么不要那个"。
    level: L3/L4/L5，标记决策时的自动化层级
    persistence: permanent（永久）/ task（临时，默认）
    scope: client（客户级）/ task（任务级）
    task_id: scope=task 时必填，任务结束后自动归档
    source: 证据引用串（分号分隔 kind:value，见 _memory_guard.parse_source_refs）
    confidence: 0.0-1.0 置信度（仅记录，不参与判定）
    strict: True 时来源引用验不过 -> 抛 ValueError，什么都不落盘
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

    # 写前冲突检测（读当前文件；同主题同内容 -> False，幂等重写）
    conf = _memory_guard.detect_conflict(topic, decision, decisions_path)
    conflict = bool(conf["conflict"])
    old_date = conf["old_date"]

    # 来源校验（必须在任何落盘之前；strict 失败抛异常 -> 文件保持原样）
    source_line = _build_source_line(source, client_name, strict)

    # 冲突：先给旧条目块尾插 pending 标记（不删不改旧正文）
    if conflict:
        _append_conflict_flag(decisions_path, old_date, topic)

    entry = f"""
## [{today}] {topic}
- **决策**: {decision}
- **理由**: {reason or '(未记录)'}
- **被否方案**: {alternatives_rejected or '(无)'}
- **层级**: {level}
- **persistence: {persistence}**
- **scope: {scope}**"""
    if scope == "task":
        entry += f"\n- **task_id: {task_id}**"
    entry += f"\n- **来源**: {source_line}"
    entry += f"\n- **confidence**: {confidence}"
    if conflict:
        entry += f"\n- **⚠️ 冲突**: 与 [{old_date}] 同主题条目矛盾，待人工裁决（resolve-conflict）"

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
    global _LAST_SKIPPED_CONFLICTS
    _LAST_SKIPPED_CONFLICTS = 0
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
        # 跳过未决冲突 / 已废弃块（防矛盾铁律双加载）
        if "<!-- conflict: pending -->" in block or _DEPRECATED_RE.search(block):
            _LAST_SKIPPED_CONFLICTS += 1
            continue
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


def count_skipped_conflicts():
    """返回最近一次 load_active_themes 跳过的未决冲突/已废弃条目数。"""
    return _LAST_SKIPPED_CONFLICTS


def _split_decision_blocks(content):
    """把 decisions.md 内容切成程序化块 [{date, topic, start, end, text}]（`## [日期] topic` 格式）。

    块边界：`## [日期] topic` 标题到下一个 `## ` 标题前（或文件尾）。
    遗留手写 `## 决策 N：` 块不匹配（无日期前缀），自然被忽略——冲突只发生在程序化块之间。
    """
    result = []
    heading_re = re.compile(r'^## \[(\d{4}-\d{2}-\d{2})\]\s*(.*?)\s*$', re.MULTILINE)
    for m in heading_re.finditer(content):
        start = m.start()
        tail = re.search(r'^## ', content[m.end():], re.MULTILINE)
        end = m.end() + tail.start() if tail else len(content)
        result.append({
            "date": m.group(1),
            "topic": m.group(2).strip(),
            "start": start,
            "end": end,
            "text": content[start:end],
        })
    return result


def resolve_conflict(client_name, topic, keep):
    """人工裁决未决冲突。keep: "old"|"new"。返回 {"resolved": bool, "detail": str}。

    keep=old：旧条目（较早日期）保留，新条目（较晚日期）标「已废弃」，旧块清 pending；
    keep=new：新条目生效，旧条目标「已废弃」并清 pending，新条目标「冲突已裁决」。
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    if keep not in ("old", "new"):
        return {"resolved": False, "detail": f"keep 参数非法: {keep}（应为 old|new）"}

    decisions_path = os.path.join(CLIENTS_DIR, client_name, "decisions.md")
    if not os.path.exists(decisions_path):
        return {"resolved": False, "detail": "无未决冲突"}

    with open(decisions_path, "r", encoding="utf-8") as f:
        content = f.read()

    wanted = str(topic).strip()
    topic_blocks = [b for b in _split_decision_blocks(content) if b["topic"] == wanted]
    if len(topic_blocks) > 2:
        return {"resolved": False, "detail": f"条目数异常（{len(topic_blocks)} 条），请手工处理"}
    if len(topic_blocks) < 2:
        return {"resolved": False, "detail": "无未决冲突"}

    pending = [b for b in topic_blocks if "<!-- conflict: pending -->" in b["text"]]
    if not pending:
        return {"resolved": False, "detail": "无未决冲突"}

    old = pending[0]
    new = [b for b in topic_blocks if b is not old][0]
    # 注：pending 标记恒在「旧」块（save_decision 把标记插到 detect_conflict 命中的首个块，即最早块），
    # 故以标记为准判 old/new，不按日期 swap（swap 会把标记块错当成 new，导致标记不被清除）。

    edits = []
    if keep == "old":
        # 旧条目保留：清其 pending；新条目去掉过期的「待人工裁决」措辞后标已废弃
        # （裁决后 ⚠️ 行仍说「待人工裁决」会误导后续读者——标记语义必须跟随状态走）
        edits.append((old["start"], old["end"], old["text"].replace("<!-- conflict: pending -->", "")))
        new_text = new["text"].replace("，待人工裁决（resolve-conflict）", "，已裁决") \
            .rstrip("\n") + f"\n- **状态**: 已废弃（{old['date']} 条目保留）\n"
        edits.append((new["start"], new["end"], new_text))
    else:
        # 新条目生效：旧条目清 pending + 标已废弃；新条目清过期裁决措辞并标已生效
        old_text = old["text"].replace("<!-- conflict: pending -->", "").rstrip("\n") \
            + f"\n- **状态**: 已废弃（{new['date']} 条目取代）\n"
        edits.append((old["start"], old["end"], old_text))
        new_text = new["text"].replace("，待人工裁决（resolve-conflict）", "，已裁决") \
            .rstrip("\n") + f"\n- **状态**: 冲突已裁决（本条生效，{old['date']} 已废弃）\n"
        edits.append((new["start"], new["end"], new_text))

    # 从后往前应用编辑，保持位置有效
    for start, end, text in sorted(edits, key=lambda e: e[0], reverse=True):
        content = content[:start] + text + content[end:]

    with open(decisions_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"resolved": True, "detail": f"已裁决：保留{'旧' if keep == 'old' else '新'}条目"}


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
