# -*- coding: utf-8 -*-
"""会话反思：AI 自动提取"学习时刻"，生成决策提案。

与 _insight.py 的区别：
  - insight：元认知反思（目标/进度/偏离度），存档到 logs，不写决策
  - reflect：学习时刻提取（纠正/选择/原则/模式/溯源），生成决策提案，
    供 AI 弹确认框后经 save_decision() 写入 decisions.md

五类学习时刻：
  纠正型：用户说"不对/不是/应该是X因为Y"
  选择型：用户从多个选项中明确选了一个
  原则型：用户说"以后都/记住/永远不要"
  模式型：同一类修改出现 3 次以上
  溯源型：用户解释"上次为什么不行"

纯函数模块：不写文件（写文件由调用方负责）；LLM 不可用时返回空列表并报原因。
"""
import json
import os
import re

from _paths import CLIENTS_DIR, TASK_HISTORY

# 五类学习时刻标签
LEARNING_TYPES = ("纠正", "选择", "原则", "模式", "溯源", "版本偏好", "模式沉淀")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _get_latest_task_history(client_name):
    """从 task_history 读取该客户最近一次会话记录（dict 或 None）。"""
    content = _read(TASK_HISTORY)
    if not content:
        return None
    try:
        history = json.loads(content)
    except Exception:
        return None
    if isinstance(history, dict):
        history = history.get("tasks", [])
    if not isinstance(history, list):
        return None
    project_key = f"client:{client_name}"
    for entry in reversed(history):
        if entry.get("project") == project_key:
            return entry
    return None


def _get_latest_context_block(client_name):
    """从 context.md 读取最近一次会话块（dict 含 input/decisions/outputs/pending 或 None）。"""
    ctx_path = os.path.join(CLIENTS_DIR, client_name, "context.md")
    content = _read(ctx_path)
    if not content:
        return None
    sessions = re.findall(r'#{2,3} \[\d{4}-\d{2}-\d{2}\]\s*第 \d+ 次会话.*?(?=#{2,3} \[|\Z)', content, re.DOTALL)
    if not sessions:
        return None
    last = sessions[-1]
    result = {}

    def _extract_field(name, text):
        m = re.search(r'####\s*' + re.escape(name) + r'\s*\n(.*?)(?=####|\Z)', text, re.DOTALL)
        if not m:
            return ""
        val = m.group(1).strip()
        return "" if val == "(未记录)" else val

    result["input"] = _extract_field("本次输入", last)
    result["decisions"] = _extract_field("关键决策", last)
    result["outputs"] = _extract_field("产出文件", last)
    result["pending"] = _extract_field("待办 / 下次要做的", last)
    # 也读 outputs_index.json 获取版本链
    outputs_idx = _read(os.path.join(CLIENTS_DIR, client_name, "outputs_index.json"))
    if outputs_idx:
        try:
            idx = json.loads(outputs_idx)
            out_list = idx.get("outputs") or idx.get("files") or []
            if isinstance(out_list, list) and out_list:
                # 提取最近 5 个产出的版本链
                recent = [o for o in reversed(out_list[-5:]) if isinstance(o, dict)]
                if recent:
                    version_lines = []
                    for o in recent:
                        fn = o.get("file", o.get("path", "?"))
                        st = o.get("status", "?")
                        dt = o.get("date", "")
                        version_lines.append(f"{fn} (状态={st}, 日期={dt})")
                    result["version_chain"] = "\n".join(version_lines)
        except Exception:
            pass
    return result


def _build_prompt(client_name, task_entry, ctx_block):
    parts = [f"【客户/项目】{client_name}"]
    if task_entry:
        parts.append(f"【最近会话日期】{task_entry.get('date', '未知')}")
        parts.append(f"【会话输入摘要】{task_entry.get('input_desc', '') or '(未记录)'}")
        parts.append(f"【会话关键决策】{task_entry.get('decisions', '') or '(未记录)'}")
        parts.append(f"【会话产出】{task_entry.get('outputs', '') or '(未记录)'}")
        parts.append(f"【会话待办】{task_entry.get('pending', '') or '(未记录)'}")
    if ctx_block:
        parts.append("【context.md 最近会话块】")
        parts.append(f"输入: {ctx_block.get('input', '') or '(未记录)'}")
        parts.append(f"决策: {ctx_block.get('decisions', '') or '(未记录)'}")
        parts.append(f"产出: {ctx_block.get('outputs', '') or '(未记录)'}")
        parts.append(f"待办: {ctx_block.get('pending', '') or '(未记录)'}")
        if ctx_block.get("version_chain"):
            parts.append("【outputs_index.json 版本链】")
            parts.append(ctx_block["version_chain"])
    parts.append("""
请从上述会话记录中提取"学习时刻"——用户在对话中教给 AI 的、值得记住的东西。

只提取以下七类（不要硬凑，没有就输出空数组）：
1. 纠正型：用户否定了某个产出并说明原因（"不对/应该是/改成X因为Y"）
2. 选择型：用户从多个选项中明确选了某个（"不用A，用B"）
3. 原则型：用户给出跨任务规则（"以后都/记住/永远不要"）
4. 模式型：同一类修改出现多次，形成可总结的模式
5. 溯源型：用户解释了某次失败或改动的根本原因
6. 版本偏好型：同一产出迭代了≥2版，用户明确表达了满意/不满意及原因
   （识别信号：产出文件名含 v1/v2/v3 或 0.1/0.2/0.3 等版本号，且会话中有"按...改/重建/重写/不对"等反馈）
   提取：终版是哪一版 → 被否版本 + 被否原因 → 满意在哪里
7. 模式沉淀型：本次会话产出了现有模板/图形目录中没有的新结构（新图形类型/新模板/新组件）
   （识别信号：产出了现有30种diagram subtype之外的新图形；或产出了一种新格式的模板）
   提取：新结构是什么 → 参考了什么材料 → 建议沉淀为哪种可复用资产

对每个学习时刻输出一个 JSON 对象，字段：
- topic: 简短话题（≤30字，如"资产卡片数量模糊化"）
- decision: 一句话决策（实际决定是什么，不是"讨论了X"）
- reason: 理由（为什么这么定）
- type: 七类之一（纠正/选择/原则/模式/溯源/版本偏好/模式沉淀）
- source: "user: 用户明示（日期）" 或 "AI 推断（需用户确认）"
- confidence: 0-1 置信度（AI 推断给 0.5-0.7，用户明示给 0.9+）

严格输出 JSON 数组，不要任何其他文字。没有学习时刻输出 []。
""")
    return "\n".join(parts)


def reflect_session(client_name, provider=None, apply=False):
    """扫描最近一次会话，返回学习时刻提案列表。

    apply=False（默认）：只返回提案，不落盘（供 AI 弹确认框）。
    apply=True（P3）：把提案经 _theme_guard.save_decision 写入 decisions.md——
      persistence=task（临时，确认后再升 permanent）、source="AI 推断（待确认）"、
      reason 标「待确认」。冲突自动走 save_decision 的 detect_conflict + pending 标记。

    返回 ([proposal, ...], warning_str)：
      proposal = {"topic", "decision", "reason", "type", "source",
                  "confidence", "conflict", "old_date"}
      warning_str = "" 或降级原因（LLM 不可用等）
    """
    warnings = []
    task_entry = _get_latest_task_history(client_name)
    ctx_block = _get_latest_context_block(client_name)

    if not task_entry and not ctx_block:
        return [], "无会话记录（task_history 与 context.md 均为空）"

    # 两处都无实质内容时，仍尝试机械提取（session_notes 可能有内容）
    has_content = False
    if task_entry:
        has_content = any(str(task_entry.get(k, "")).strip() and str(task_entry.get(k, "")).strip() != "(未记录)"
                          for k in ("input_desc", "decisions", "outputs", "pending"))
    if ctx_block:
        has_content = has_content or any(str(v).strip() for v in ctx_block.values())
    if not has_content:
        warnings.append("会话槽位无实质内容（save 链路可能未填写摘要），提案可能为空")

    prompt = _build_prompt(client_name, task_entry, ctx_block)

    try:
        from _cloud_llm import chat, LLM_MODE
        resp = chat(prompt, system="你是咨询工作助手，做会话反思。只输出 JSON 数组，不编造未提及的信息。",
                    provider=provider, temperature=0.2, max_tokens=1500,
                    task="reflect", mode="collaborative")
        if resp is None and LLM_MODE == "host":
            warnings.append("host 模式：LLM 不可用，请人工反思")
            return [], "; ".join(warnings)
    except Exception as e:
        warnings.append(f"LLM 调用失败: {e}")
        return [], "; ".join(warnings)

    if not resp:
        warnings.append("LLM 返回空")
        return [], "; ".join(warnings)

    # 解析 JSON 数组
    proposals = []
    try:
        # 容错：剥离可能的 markdown 围栏
        text = str(resp).strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        # 取第一个 [ 到最后一个 ]
        start, end = text.find('['), text.rfind(']')
        if start >= 0 and end > start:
            text = text[start:end + 1]
        parsed = json.loads(text)
        if isinstance(parsed, list):
            proposals = parsed
    except Exception as e:
        warnings.append(f"LLM 输出解析失败: {e}（原始: {str(resp)[:120]}）")
        return [], "; ".join(warnings)

    # 冲突检测 + 字段规范化
    decisions_path = os.path.join(CLIENTS_DIR, client_name, "decisions.md")
    for p in proposals:
        if not isinstance(p, dict):
            continue
        topic = str(p.get("topic", "")).strip()
        decision = str(p.get("decision", "")).strip()
        p["topic"] = topic
        p["decision"] = decision
        p["reason"] = str(p.get("reason", "")).strip()
        p["type"] = str(p.get("type", "")).strip() or "选择"
        p["source"] = str(p.get("source", "")).strip() or "AI 推断（需用户确认）"
        try:
            p["confidence"] = float(p.get("confidence", 0.6))
        except (TypeError, ValueError):
            p["confidence"] = 0.6
        # 冲突检测（同主题不同决策内容 -> conflict=True）
        p["conflict"] = False
        p["old_date"] = None
        if topic and decision:
            try:
                from _memory_guard import detect_conflict
                conf = detect_conflict(topic, decision, decisions_path)
                p["conflict"] = bool(conf.get("conflict"))
                p["old_date"] = conf.get("old_date")
            except Exception:
                pass

    # 过滤空提案
    proposals = [p for p in proposals if isinstance(p, dict) and p.get("topic") and p.get("decision")]
    if not proposals and not warnings:
        warnings.append("未识别到学习时刻")

    # P3：--apply 落盘（persistence=task，AI 推断待确认；冲突由 save_decision 处理）
    if apply and proposals:
        from _theme_guard import save_decision
        applied = 0
        for p in proposals:
            topic = str(p.get("topic", "")).strip()
            decision = str(p.get("decision", "")).strip()
            if not topic or not decision:
                continue
            try:
                written = save_decision(
                    client_name, topic, decision,
                    reason=f"（待确认）{p.get('reason', '')}".strip(),
                    persistence="task", scope="client",
                    source="user:AI 推断（待确认）",  # P2-12：user: 免校验，避免误标「证据待核」
                    confidence=float(p.get("confidence", 0.6)),
                )
                if written:
                    applied += 1
                else:
                    warnings.append(f"写入提案失败: {topic}（保存锁获取失败，未落盘）")
            except Exception as e:
                warnings.append(f"写入提案失败: {topic}: {e}")
        if applied:
            warnings.append(f"已落盘 {applied} 条 AI 推断提案（persistence=task，待确认）")
        # P6-5：--apply 写 decisions.md 后触发一次索引增量（复用 save 的索引联动），
        # 否则新决策搜不到（BM25/embed 增量失败不阻断，与 save 同一容错口径）
        if applied:
            try:
                from _embed_index import build_embedding_index
                build_embedding_index(batch_size=50, force=False)
            except Exception as e:
                warnings.append(f"索引增量跳过: {e}")

    return proposals, "; ".join(warnings)


def format_proposals_text(proposals):
    """把提案列表格式化为可读文本（供 CLI 非 JSON 输出）。"""
    lines = []
    for i, p in enumerate(proposals, 1):
        lines.append(f"\n--- 提案 {i} ---")
        lines.append(f"话题: {p.get('topic', '')}")
        lines.append(f"决策: {p.get('decision', '')}")
        lines.append(f"理由: {p.get('reason', '')}")
        lines.append(f"类型: {p.get('type', '')} | 置信度: {p.get('confidence', 0)}")
        lines.append(f"来源: {p.get('source', '')}")
        if p.get("conflict"):
            lines.append(f"⚠ 冲突: 与 [{p.get('old_date', '?')}] 同主题条目矛盾，写入后将标记待人工裁决")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python _reflect.py <客户名>")
        sys.exit(1)
    client = sys.argv[1]
    proposals, warning = reflect_session(client)
    if warning:
        print(f"[warn] {warning}")
    if not proposals:
        print("（无提案）")
    else:
        print(format_proposals_text(proposals))
