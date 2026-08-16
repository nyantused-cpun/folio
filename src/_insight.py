# -*- coding: utf-8 -*-
"""洞察机制：AI 元认知反思。

触发时机（project_rules.md）：
  1. 每 10 轮对话自动触发
  2. 用户说"总结一下"/"回顾一下"
  3. 上下文将压缩前（由调用方判断，传 force=True）

触发词区分（project_rules.md）：
  - "总结一下"/"回顾一下" → 洞察（本模块）
  - "记一下" → 决策记录（_session.py，非本模块）

输出结构（六部分）：
  目标回顾 → 进度 → 偏离度 → 关键洞察 → 建议 → 目标差距

存档：.trae/logs/insights/{客户}_{日期}.md
"""
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
INSIGHTS_DIR = os.path.join(SCRIPT_DIR, ".trae", "logs", "insights")

# 洞察触发关键词
INSIGHT_TRIGGERS = ["总结一下", "回顾一下", "总结下", "回顾下"]
# 决策记录关键词（不触发洞察，触发决策记录）
DECISION_TRIGGERS = ["记一下", "记下", "记录一下"]

# 自动触发间隔（轮次）
AUTO_INTERVAL = 10


def extract_summary(filepath):
    """从 insight 文件提取摘要（关键洞察 + 建议 + 偏离度）。

    供 load_context_by_level L4 层级加载，避免读全文。
    返回摘要字符串，文件不存在或格式不规范时返回空字符串。
    """
    if not filepath or not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""

    parts = []
    # 提取各段（## N. 标题 到下一个 ## 或文件尾）
    import re
    sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
    for sec in sections:
        for key in ("关键洞察", "建议", "偏离度"):
            if key in sec[:30]:
                # 去掉标题行，取内容
                lines = sec.strip().split("\n")
                body = "\n".join(lines[1:]).strip()
                if body:
                    parts.append(f"[{key}] {body[:200]}")
                break
    return "\n".join(parts)


def detect_trigger(user_input, turn_count, force=False):
    """检测是否触发洞察。

    user_input: 用户当前输入
    turn_count: 当前对话轮次（从 1 开始）
    force: True 时强制触发（上下文压缩前由调用方传入）

    返回 (triggered, reason) 元组。
    triggered: True 时触发洞察
    reason: "keyword" / "interval" / "force" / "decision" / ""
    """
    # 强制触发（上下文压缩前）
    if force:
        return True, "force"

    if not user_input:
        # 无输入时只检查轮次
        if turn_count > 0 and turn_count % AUTO_INTERVAL == 0:
            return True, "interval"
        return False, ""

    # 优先检测决策记录关键词（不触发洞察）
    for kw in DECISION_TRIGGERS:
        if kw in user_input:
            return False, "decision"

    # 检测洞察触发关键词
    for kw in INSIGHT_TRIGGERS:
        if kw in user_input:
            return True, "keyword"

    # 10 轮自动触发
    if turn_count > 0 and turn_count % AUTO_INTERVAL == 0:
        return True, "interval"

    return False, ""


def generate_insight(client_name, context_summary, turn_count, provider=None):
    """调 LLM 生成洞察报告（六部分结构）。

    context_summary: 对话上下文摘要（目标/已完成/待办等）
    返回洞察文本或 None。
    """
    from _cloud_llm import chat, LLM_MODE

    prompt = f"""请对以下咨询工作对话做元认知反思，输出洞察报告。

【客户/项目】{client_name}
【对话轮次】{turn_count}
【上下文摘要】
{context_summary}

请严格按以下六部分输出（每部分 2-3 句，基于上下文客观分析，不编造未提及的信息）：

## 1. 目标回顾
本次工作的核心目标是什么？

## 2. 进度
已完成哪些？进行到哪一步？

## 3. 偏离度
当前方向是否偏离原定目标？偏离多少？

## 4. 关键洞察
发现了什么非显而易见的模式/问题/机会？

## 5. 建议
下一步最该做什么？有什么风险要规避？

## 6. 目标差距
离目标达成还差什么？
"""

    system = "你是咨询工作助手，做元认知反思。基于上下文客观分析，不编造未提及的信息。"
    resp = chat(prompt, system=system, provider=provider, temperature=0.3,
                max_tokens=1500, task="insight", mode="collaborative")
    if resp is None and LLM_MODE == "host":
        print("[host-mode] 机械部分已完成；请按上方 prompt 完成推理并继续流程")
    return resp


def save_insight(client_name, insight_text):
    """洞察报告存档到 .trae/logs/insights/{客户}_{日期}.md。

    同日多次洞察追加（不覆盖）。
    返回存档路径或 None。
    """
    if not insight_text:
        return None

    os.makedirs(INSIGHTS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{client_name}_{today}.md"
    filepath = os.path.join(INSIGHTS_DIR, filename)

    # 同日多次洞察追加
    header = f"\n\n---\n# 洞察 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(header + insight_text)

    return filepath


def run_insight(client_name, context_summary, turn_count, user_input="", provider=None, force=False):
    """完整洞察流程：检测触发 → 生成 → 存档 → Skill 提示（M8）。

    返回 (insight_text, filepath, reason) 或 (None, None, reason)。
    user_input 用于检测关键词触发（"总结一下"等），不传则只靠 turn_count/force。
    """
    triggered, reason = detect_trigger(user_input, turn_count, force=force)
    if not triggered:
        return None, None, reason

    insight = generate_insight(client_name, context_summary, turn_count, provider)
    if not insight:
        return None, None, reason

    filepath = save_insight(client_name, insight)

    # M8: Skill 与洞察联动——发现可复用工作流时提示保存为 Skill
    try:
        from _skill import suggest_skill_from_insight
        hint = suggest_skill_from_insight(insight)
        if hint:
            print(f"\n[Skill 提示] {hint}")
    except Exception:
        pass

    return insight, filepath, reason


if __name__ == "__main__":
    # 自测触发检测
    print("=== 触发检测自测 ===")
    tests = [
        ("总结一下进度", 5, False),
        ("记一下这个决策", 5, False),
        ("继续", 10, False),
        ("继续", 5, False),
        ("", 10, False),
        ("继续", 5, True),  # force
    ]
    for text, turn, force in tests:
        triggered, reason = detect_trigger(text, turn, force=force)
        print(f"  input={repr(text)}, turn={turn}, force={force} -> triggered={triggered}, reason={reason}")
