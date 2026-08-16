# -*- coding: utf-8 -*-
"""上下文管理模块：context.md schema、层级判定、客户目录管理。

从 _session.py 拆分（候选 4 · 模块化），无内部依赖（叶子模块）。
"""
import os
import json
import re
from datetime import datetime

from _paths import SCRIPT_DIR, CLIENTS_DIR, TASK_HISTORY


__all__ = [
    # 常量
    "CONTEXT_SCHEMA_H2", "WRITABLE_H2_SECTIONS", "CONTEXT_MAX_LINES",
    "LEVEL_KEYWORDS", "LEVEL_TO_MODE",
    # 函数
    "_validate_context_schema", "_snapshot_context",
    "detect_level", "load_context_by_level",
    "list_clients", "get_context_path", "ensure_client_dir",
    "load_context", "show_all_clients", "consolidate", "compact",
]


# ============================================================
# context.md schema（P1: 版本控制与文本约束）
# ============================================================
# H2 段白名单（save_session 只追加"会话历史"类的段，锁定段不在此列）
CONTEXT_SCHEMA_H2 = {
    "项目基础信息",      # 锁定段（只能初始化时写）
    "铁律与约束",        # 锁定段（通过 theme-guard --set-theme 更新）
    "关键材料",          # 锁定段（通过 classify 更新）
    "决策记录",          # 通过 theme-guard --set-decision 更新
    "会话历史",          # save_session 追加
    "待办与下一步",      # save_session 追加
    "历史会话摘要",      # compact 生成的压缩摘要段
    # --- 客户自定义扩展段（人工维护的锁定段，向后兼容） ---
    "项目关键背景（摘要）",   # 示例：招标基本信息+评标办法+合同条款+★号废标项+痛点+约束+业务模式
    "参考材料（refs/）",      # 示例：refs/ 目录索引（与 _knowledge/clients/{客户}/refs/ 对应）
    "独立报告（reports/）",   # 示例：reports/ 目录索引
    "关键决策（高亮）",       # 示例：高亮版关键决策（与 decisions.md 对应）
    "待澄清问题（高优先级 · 影响方案边界）",  # 示例：待客户澄清问题索引
    "业务双核心（D-006/D-007 · 2026-07-08 修正）",  # 示例：双核心业务模式说明
    "待办 / 下一步",          # 示例：待办事项（与"待办与下一步"语义一致，历史命名差异）
}

# H2 段中 save_session 可以写入的段（会话记录类）
WRITABLE_H2_SECTIONS = {"会话历史", "待办与下一步"}

# compact 生成的会话块 H2 段正则前缀（## [日期] 第N次会话 / ## 历史会话摘要 ...）
_COMPACT_H2_PATTERN = re.compile(r"^## (?:\[\d{4}-\d{2}-\d{2}\]|历史会话摘要)", re.MULTILINE)

# context.md 行数上限（超过触发 compact）
CONTEXT_MAX_LINES = 200


def _validate_context_schema(context_path):
    """校验 context.md 的 schema 合法性。

    返回 (ok, issues)。issues 是问题列表（空=无问题）。
    """
    if not os.path.exists(context_path):
        return True, []

    try:
        with open(context_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return True, []

    issues = []

    # 检查 H2 段白名单（含 compact 生成的日期会话块 ## [日期] 第N次会话）
    h2_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    found_sections = h2_pattern.findall(content)

    for section in found_sections:
        section = section.strip()
        # compact 生成的会话块：## [日期] 第N次会话 / ## 历史会话摘要 (日期范围)
        if section.startswith("[") or section.startswith("历史会话摘要"):
            continue
        if section not in CONTEXT_SCHEMA_H2:
            issues.append(f"非法 H2 段: ## {section}")

    # 检查行数
    line_count = content.count("\n") + 1
    if line_count > CONTEXT_MAX_LINES:
        issues.append(f"context.md 超长 ({line_count} 行 > {CONTEXT_MAX_LINES})，请跑 compact")

    return len(issues) == 0, issues


def _snapshot_context(context_path):
    """写 context.md 快照（.snapshot.{timestamp}）。

    save_session 追加前调用，保留追加前的状态用于回溯。
    保留最近 5 个快照，超出删除最旧的。
    """
    if not os.path.exists(context_path):
        return None

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    snapshot_path = f"{context_path}.snapshot.{timestamp}"

    try:
        with open(context_path, "r", encoding="utf-8") as src:
            content = src.read()
        with open(snapshot_path, "w", encoding="utf-8") as dst:
            dst.write(content)
    except OSError:
        return None

    # 清理旧快照（保留最近 5 个）
    base = os.path.dirname(context_path)
    fname = os.path.basename(context_path)
    snapshots = []
    for f in os.listdir(base):
        if f.startswith(f"{fname}.snapshot."):
            snapshots.append(os.path.join(base, f))
    if len(snapshots) > 5:
        snapshots.sort(key=lambda x: os.path.getmtime(x))
        for old in snapshots[:-5]:
            try:
                os.remove(old)
            except OSError:
                pass

    return snapshot_path


# ============================================================
# 能力边界动态策略（L3/L4/L5 层级判定 + 按层级加载上下文）
# ============================================================
# SAE J3016 映射：L3 directed 人给框架AI填充 / L4 collaborative AI主导人确认 / L5 autonomous 全自动可重跑
LEVEL_KEYWORDS = {
    "L5": ["整理", "提取", "重命名", "分类", "归档", "批量", "清洗", "去重", "索引"],
    "L4": ["计划", "大纲", "检索", "分析", "评估", "审查", "对比", "建议", "总结"],
    "L3": ["写", "生成", "制作", "创建", "设计", "渲染", "输出", "导出", "排版"],
    "creative": ["灵感", "创意", "头脑风暴", "发散", "脑洞", "点子", "想法", "思路"],
}

LEVEL_TO_MODE = {
    "L3": "directed",
    "L4": "collaborative",
    "L5": "autonomous",
    "creative": "creative",
}


def detect_level(user_input):
    """从用户输入判定工作层级。

    creative: 灵感/创意/头脑风暴（高温发散）
    L5 autonomous: 整理/提取/重命名（AI 全自动可重跑）
    L4 collaborative: 计划/大纲/检索（AI 主导人确认）
    L3 directed: 写/生成/制作（人给框架 AI 填充）
    模糊默认 L4（collaborative）

    返回 (level, mode) 元组，如 ("L5", "autonomous")
    """
    if not user_input:
        return "L4", "collaborative"

    counts = {level: sum(1 for kw in keywords if kw in user_input)
              for level, keywords in LEVEL_KEYWORDS.items()}

    max_count = max(counts.values())
    if max_count == 0:
        return "L4", "collaborative"  # 模糊默认 L4

    # creative 优先：只要命中即选 creative（用户显式要求创意时不应被 L3/L4/L5 覆盖）
    if counts.get("creative", 0) > 0:
        return "creative", "creative"

    # 命中数最多的层级，平局时 L5 > L4 > L3
    for level in ["L5", "L4", "L3"]:
        if counts[level] == max_count:
            return level, LEVEL_TO_MODE[level]

    return "L4", "collaborative"


def load_context_by_level(client_name, level):
    """按层级加载客户上下文（SAE J3016 映射）。

    L5 autonomous: 不提取历史（AI 全自动，无需历史关联）
    L4 collaborative: 读 decisions.md + profile.md（决策记忆 + 个人画像）
    L3 directed: 读 outputs_index.json + preferences.md + profile.md（产出索引 + 偏好 + 画像）

    返回 dict，含 level/profile/decisions/outputs_index/preferences 等键（按层级加载）。
    """
    loaded = {"level": level, "mode": LEVEL_TO_MODE.get(level, "collaborative")}

    if level == "L5":
        return loaded  # L5 不提取历史

    if level == "creative":
        return loaded  # creative 不提取历史（创意发散不需要受既有决策约束）

    client_path = os.path.join(CLIENTS_DIR, client_name)

    # L4 + L3 都加载 profile.md（个人画像，去 AI 化基准）
    profile_path = os.path.join(SCRIPT_DIR, "_knowledge", "me", "profile.md")
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                loaded["profile"] = f.read()
        except Exception as e:
            # P1-3：文件存在但读取失败时打印警告（原静默 pass 会让用户误以为已加载）
            print(f"[warn] profile.md 读取失败: {e}")

    if level == "L4":
        # L4 优先加载 client_index.md（世界书索引 ≤80 行），不再塞 decisions.md 全文
        # 改动6（grilling 确认）：client_index.md 含全景计数，需要细节时用 chunk-read
        from _paths import client_index_path
        ci_path = client_index_path(client_name)
        if os.path.exists(ci_path):
            try:
                with open(ci_path, "r", encoding="utf-8") as f:
                    loaded["client_index"] = f.read()
            except Exception as e:
                print(f"[warn] {client_name}/client_index.md 读取失败: {e}")
        else:
            # client_index.md 不存在时降级读 decisions.md
            decisions_path = os.path.join(client_path, "decisions.md")
            if os.path.exists(decisions_path):
                try:
                    with open(decisions_path, "r", encoding="utf-8") as f:
                        loaded["decisions"] = f.read()
                except Exception as e:
                    print(f"[warn] {client_name}/decisions.md 读取失败: {e}")

        # 加载最近 1 次 insight 摘要（spec 5.1.2）
        try:
            from _insight import extract_summary, INSIGHTS_DIR
            if os.path.isdir(INSIGHTS_DIR):
                insight_files = sorted(
                    [f for f in os.listdir(INSIGHTS_DIR)
                     if f.startswith(f"{client_name}_") and f.endswith(".md")],
                    reverse=True,
                )
                if insight_files:
                    latest_path = os.path.join(INSIGHTS_DIR, insight_files[0])
                    summary = extract_summary(latest_path)
                    if summary:
                        loaded["insight_summary"] = summary
                        if "偏离" in summary:
                            loaded.setdefault("warnings", []).append(
                                "上次 insight 标记偏离度较高，请检查方向"
                            )
        except Exception as e:
            print(f"[warn] insight 摘要加载失败: {e}")
    elif level == "L3":
        # L3 加载 outputs_index.json（产出索引）+ preferences.md（客户偏好）
        outputs_index_path = os.path.join(client_path, "outputs_index.json")
        if os.path.exists(outputs_index_path):
            try:
                with open(outputs_index_path, "r", encoding="utf-8") as f:
                    loaded["outputs_index"] = json.load(f)
            except Exception as e:
                print(f"[warn] {client_name}/outputs_index.json 解析失败: {e}")
        preferences_path = os.path.join(client_path, "preferences.md")
        if os.path.exists(preferences_path):
            try:
                with open(preferences_path, "r", encoding="utf-8") as f:
                    loaded["preferences"] = f.read()
            except Exception as e:
                print(f"[warn] {client_name}/preferences.md 读取失败: {e}")

    return loaded


def list_clients():
    """列出所有客户项目"""
    if not os.path.isdir(CLIENTS_DIR):
        print("没有客户项目目录")
        return []
    clients = [d for d in os.listdir(CLIENTS_DIR)
               if os.path.isdir(os.path.join(CLIENTS_DIR, d)) and not d.startswith("_")]
    return clients


def get_context_path(client_name):
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    return os.path.join(CLIENTS_DIR, client_name, "context.md")


def ensure_client_dir(client_name):
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    template = os.path.join(CLIENTS_DIR, "_template")
    client_path = os.path.join(CLIENTS_DIR, client_name)
    if not os.path.exists(client_path):
        os.makedirs(os.path.join(client_path, "refs"), exist_ok=True)
        os.makedirs(os.path.join(client_path, "outputs"), exist_ok=True)
        context_path = os.path.join(client_path, "context.md")
        if os.path.exists(os.path.join(template, "context.md")):
            with open(os.path.join(template, "context.md"), "r", encoding="utf-8") as src:
                with open(context_path, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
        else:
            with open(context_path, "w", encoding="utf-8") as f:
                f.write("# 项目上下文记录\n\n")
        print(f"创建新客户项目: {client_name}")
    return client_path


def load_context(client_name):
    """加载客户上下文，输出最近一次会话摘要"""
    context_path = get_context_path(client_name)
    if not os.path.exists(context_path):
        print(f"错误: 客户 '{client_name}' 不存在")
        print(f"可用客户: {list_clients()}")
        return

    with open(context_path, "r", encoding="utf-8") as f:
        content = f.read()

    sessions = re.findall(r'## \[(\d{4}-\d{2}-\d{2})\]\s*(.*?)(?=## \[|\Z)', content, re.DOTALL)

    print(f"=== {client_name} 项目上下文 ===")
    print(f"总会话次数: {len(sessions)}")

    if sessions:
        last = sessions[-1]
        print(f"\n最近一次会话: {last[0]} - {last[1].strip()[:100]}")
    else:
        print("\n还没有任何会话记录。项目刚开始。")

    # 别名异议提醒（P1a）
    try:
        from _aliases import print_alias_reminder
        prev_client = None
        if os.path.exists(TASK_HISTORY):
            with open(TASK_HISTORY, "r", encoding="utf-8") as f:
                try:
                    history = json.load(f)
                except Exception:
                    history = []
            if isinstance(history, list):
                for entry in reversed(history):
                    p = entry.get("project", "")
                    if p.startswith("client:"):
                        p = p[7:]
                    if p and p != client_name and not p.startswith("_"):
                        prev_client = p
                        break
            elif isinstance(history, dict):
                for entry in reversed(history.get("tasks", [])):
                    p = entry.get("project", "")
                    if p.startswith("client:"):
                        p = p[7:]
                    if p and p != client_name and not p.startswith("_"):
                        prev_client = p
                        break
        print_alias_reminder(client_name, prev_client)
    except Exception as e:
        print(f"[别名提醒跳过: {e}]")


def show_all_clients(json_output=False):
    """展示所有客户项目的最近状态"""
    clients = list_clients()
    if not clients:
        if json_output:
            print("[]")
        else:
            print("暂无客户项目")
        return

    if json_output:
        import json as _json
        data = []
        for c in clients:
            ctx_path = get_context_path(c)
            entry = {"client": c, "last_session": "无记录", "session_count": 0, "pending": ""}
            if os.path.exists(ctx_path):
                with open(ctx_path, "r", encoding="utf-8") as f:
                    content = f.read()
                sessions = re.findall(r'## \[(\d{4}-\d{2}-\d{2})\]\s*(.*?)(?=## \[|\Z)', content, re.DOTALL)
                if sessions:
                    entry["last_session"] = sessions[-1][0]
                    entry["session_count"] = len(sessions)
                pending_match = re.findall(r'### 待办[^\n]*\n(.*?)(?=\n##|\n###|\Z)', content, re.DOTALL)
                if pending_match:
                    entry["pending"] = pending_match[-1].strip()[:200]
            data.append(entry)
        print(_json.dumps(data, ensure_ascii=False, indent=2))
        return

    print(f"{'客户':<20} {'最近会话':<14} {'会话数':<8} {'待办'}")
    print("-" * 70)
    for c in clients:
        ctx_path = get_context_path(c)
        if os.path.exists(ctx_path):
            with open(ctx_path, "r", encoding="utf-8") as f:
                content = f.read()
            sessions = re.findall(r'## \[(\d{4}-\d{2}-\d{2})\]\s*(.*?)(?=## \[|\Z)', content, re.DOTALL)
            last_date = sessions[-1][0] if sessions else "无记录"
            session_count = len(sessions)
            pending_match = re.findall(r'### 待办[^\n]*\n(.*?)(?=\n##|\n###|\Z)', content, re.DOTALL)
            last_pending = pending_match[-1].strip()[:30] if pending_match else "无"
            print(f"{c:<20} {last_date:<14} {session_count:<8} {last_pending}")
        else:
            print(f"{c:<20} {'无记录':<14} {0:<8}")


def consolidate(client_name, threshold=3):
    """自动固化：检测反复出现的模式，升级到 .folio/rules/"""
    context_path = get_context_path(client_name)
    if not os.path.exists(context_path):
        print(f"客户 '{client_name}' 不存在")
        return

    with open(context_path, "r", encoding="utf-8") as f:
        content = f.read()

    rules_dir = os.path.join(CLIENTS_DIR, client_name, ".folio", "rules")
    if not os.path.isdir(rules_dir):
        rules_dir = os.path.join(SCRIPT_DIR, ".folio", "rules")

    patterns = {
        "主题色": r"#([0-9a-fA-F]{6})",
        "页数结构": r"(\d+)[页Pp][结]*构",
        "字体": r"(Microsoft YaHei|SimSun|SimHei|KaiTi|FangSong|Arial|Segoe UI|Noto Sans)",
        "输出类型": r"\.(pptx|html|docx|pdf)",
        "数据来源": r"([\u4e00-\u9fff]+规划|[\u4e00-\u9fff]+报告|[\u4e00-\u9fff]+文档)",
        "优先Skill": r"(slides|frontend-design|web-artifacts-builder)",
    }

    found_rules = []
    for label, pattern in patterns.items():
        matches = re.findall(pattern, content)
        if not matches:
            continue
        freq = {}
        for m in matches:
            freq[m] = freq.get(m, 0) + 1
        for val, count in freq.items():
            if count >= threshold:
                found_rules.append(f"{label}: {val} (出现 {count} 次)")

    if not found_rules:
        print(f"未发现可固化的模式（阈值: {threshold} 次）")
        return

    print(f"\n检测到 {len(found_rules)} 个可固化模式:\n")
    for r in found_rules:
        print(f"  ✓ {r}")

    # 不再自动写入，输出建议让用户确认
    new_rules_text = "\n".join(f"- **{r}**" for r in found_rules)
    print(f"\n[consolidate] 检测到客户 '{client_name}' 的以下模式（出现 {threshold}+ 次），建议升级为规则：")
    print(new_rules_text)
    print("如需确认，请说'记一下'或手动添加到 AGENTS.md")


def compact(client_name, keep_last=1):
    """上下文压缩：将前 N-1 次会话压缩为摘要，仅保留最近 keep_last 次完整记录"""
    context_path = get_context_path(client_name)
    if not os.path.exists(context_path):
        print(f"客户 '{client_name}' 不存在")
        return

    with open(context_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 捕获完整会话块（含日期和正文），返回 (date, full_block) 元组列表
    sessions = re.findall(r'(## \[(\d{4}-\d{2}-\d{2})\][^\n]*\n.*?)(?=## \[\d{4}-\d{2}-\d{2}\]|\Z)', content, re.DOTALL)

    if len(sessions) <= keep_last:
        print(f"只有 {len(sessions)} 次会话，无需压缩")
        return

    header_end = content.find("## [")
    if header_end == -1:
        # P1-1：--- 不存在时 find 返回 -1，+3 后是 2，导致 header 只取前 2 字符
        sep_pos = content.find("---")
        header_end = sep_pos + 3 if sep_pos != -1 else 0
    header = content[:header_end].strip()

    old_sessions = sessions[:-keep_last]
    recent_sessions = sessions[-keep_last:]

    # sessions 元素是 (full_block, date)
    " ".join(s[0] for s in old_sessions)
    date_range = f"{old_sessions[0][1]} ~ {old_sessions[-1][1]}"

    # 提取会话序号
    def _extract_session_num(block):
        m = re.search(r'第 (\d+) 次', block)
        return m.group(1) if m else "?"

    first_num = _extract_session_num(old_sessions[0][0])
    last_num = _extract_session_num(old_sessions[-1][0])

    # 提取关键信息
    all_decisions = set()
    all_outputs = set()
    all_pending = set()
    for s in old_sessions:
        body = s[0]
        dec = re.findall(r'### 关键决策\n(.*?)(?=\n###|\Z)', body, re.DOTALL)
        out = re.findall(r'### 产出文件\n(.*?)(?=\n###|\Z)', body, re.DOTALL)
        pen = re.findall(r'### 待办[^\n]*\n(.*?)(?=\n###|\Z)', body, re.DOTALL)
        for d in dec:
            all_decisions.add(d.strip())
        for o in out:
            all_outputs.add(o.strip())
        for p in pen:
            if p.strip() and p.strip() != "(未记录)":
                all_pending.add(p.strip())

    summary = f"""
## 历史会话摘要 ({date_range})

本摘要覆盖第 {first_num} ~ {last_num} 次会话，共 {len(old_sessions)} 次。

### 历史关键决策
{chr(10).join('- ' + d for d in sorted(all_decisions)[:10]) or '无记录'}

### 历史产出文件
{chr(10).join('- ' + o for o in sorted(all_outputs)[:10]) or '无记录'}

### 已解决的待办
{chr(10).join('- ' + p for p in sorted(all_pending)[:10]) or '无记录'}

---
"""

    # recent_sessions 元素是 (full_block, date)，直接拼接 full_block
    recent_text = "".join(s[0] for s in recent_sessions)

    new_content = header + "\n" + summary + "\n" + recent_text

    bak_path = context_path + ".bak"
    with open(bak_path, "w", encoding="utf-8") as f:
        f.write(content)

    with open(context_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    original_kb = len(content) // 1024
    new_kb = len(new_content) // 1024
    saved = original_kb - new_kb

    print(f"压缩完成: {original_kb} KB -> {new_kb} KB (节省 {saved} KB, {int(saved/max(original_kb,1)*100)}%)")
    print(f"原 {len(sessions)} 次会话 -> {len(old_sessions)} 次压缩为摘要 + 保留最近 {keep_last} 次")
    print(f"备份已保存到: {bak_path}")
