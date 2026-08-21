# -*- coding: utf-8 -*-
"""记忆溯源守门（P0 · T1）：证据引用解析与校验的纯函数层。

设计原则（源自 MyContext 调研）：
  1. 静默失效是最高优先级 bug —— 每个校验失败都返回可见的原因，绝不吞掉。
  2. 引用映射不上 -> 整条待核 —— 坏引用不"忽略继续留结论"，而是标"（证据待核：原因）"。
  3. 「没做/读不到」≠「0 条」—— 待补 / 待核 / 不可读 单独表达，不和正常数混报。
  4. 冲突保留不覆盖 —— 同主题矛盾条目并存标记，交人工裁决。
  5. user 来源免校验且优先级最高 —— 用户口述是最高优先级证据，不质疑不覆盖。

本模块是纯函数层：不写文件、不联网、不 print；异常一律消化进返回值（元组/字典），不抛出。
路径默认值基于 _paths，但测试可注入 tmp 路径（context_path / decisions_path / base_dir / client_dir）。
"""

import os
import re

from _paths import CLIENTS_DIR, SCRIPT_DIR

_VALID_KINDS = ("file", "session", "decision", "user")


def parse_source_refs(text):
    """解析分号分隔的证据引用串为条目列表。

    每条 `kind:value`，kind ∈ {file, session, decision, user}：
      - file：value 反斜杠归一为正斜杠并剥离 `#锚点`（anchor 仅记录，不校验）；
      - session / decision：value 为整数字符串（整数性由 verify_source_ref 校验）；
      - user：任意描述，免校验。
    未知 kind / 无冒号 / value 为空 -> {"kind": "invalid", ...}；空串 / None -> []。
    """
    if not text:
        return []
    refs = []
    for token in text.split(";"):
        raw = token.strip()
        if not raw:
            continue  # 空段（如尾分号）不产生条目
        if ":" not in raw:
            refs.append({"kind": "invalid", "value": "", "anchor": "", "raw": raw})
            continue
        kind, _, value = raw.partition(":")
        kind = kind.strip()
        if kind not in _VALID_KINDS:
            refs.append({"kind": "invalid", "value": value, "anchor": "", "raw": raw})
            continue
        if kind == "file":
            path, _, anchor = value.partition("#")
            path = path.replace("\\", "/")
            if not path.strip():
                refs.append({"kind": "invalid", "value": "", "anchor": "", "raw": raw})
            else:
                refs.append({
                    "kind": "file",
                    "value": path.strip(),
                    "anchor": anchor.strip(),
                    "raw": raw,
                })
        else:
            v = value.strip()
            if not v:
                refs.append({"kind": "invalid", "value": "", "anchor": "", "raw": raw})
            else:
                if kind in ("session", "decision") and v.isdigit():
                    # 去前导零（"012"->"12"）：规约要求整数归一；全零保留 "0" 让校验自然失败
                    v = v.lstrip("0") or "0"
                refs.append({"kind": kind, "value": v, "anchor": "", "raw": raw})
    return refs


def _read_text(path):
    """读文本文件；FileNotFoundError 返回 None（表示"不存在"），其余异常上抛由调用方折进返回值。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def verify_source_ref(ref, client_name, context_path=None, decisions_path=None, base_dir=None):
    """校验单条来源引用，返回 (ok, reason)。

    - file：base_dir（默认 SCRIPT_DIR）下存在 -> ok，否则 "文件不存在: {路径}"；
    - session：context.md 中第 N 次会话存在 -> ok，否则 "会话 N 不存在（共 M 次）"；
    - decision：decisions.md 中 `## 决策 N[：:]` 存在 -> ok，否则 "决策 N 不存在"；
    - user：恒 (True, "用户口述（免校验）")；
    - invalid：("格式非法: {raw}")。
    文件缺失报 "context.md 不存在" / "decisions.md 不存在"；读取异常折成 (False, "读取失败: ...")，不抛。
    """
    if not isinstance(ref, dict):
        return (False, f"格式非法: {ref}")
    kind = ref.get("kind", "invalid")
    value = ref.get("value", "")
    raw = ref.get("raw", "")

    if base_dir is None:
        base_dir = SCRIPT_DIR
    if context_path is None:
        context_path = os.path.join(CLIENTS_DIR, client_name, "context.md")
    if decisions_path is None:
        decisions_path = os.path.join(CLIENTS_DIR, client_name, "decisions.md")

    if kind == "file":
        if os.path.exists(os.path.join(base_dir, value)):
            return (True, "文件存在")
        return (False, f"文件不存在: {value}")

    if kind == "session":
        try:
            content = _read_text(context_path)
        except Exception as e:
            return (False, f"读取失败: {e}")
        if content is None:
            return (False, "context.md 不存在")
        nums = re.findall(r'#{2,3} \[\d{4}-\d{2}-\d{2}\] 第 (\d+) 次会话', content)
        max_session = max((int(x) for x in nums), default=0)
        try:
            n = int(value)
        except (ValueError, TypeError):
            return (False, f"会话 {value} 不存在（共 {max_session} 次）")
        if 1 <= n <= max_session:
            return (True, f"会话 {n} 存在")
        return (False, f"会话 {n} 不存在（共 {max_session} 次）")

    if kind == "decision":
        try:
            content = _read_text(decisions_path)
        except Exception as e:
            return (False, f"读取失败: {e}")
        if content is None:
            return (False, "decisions.md 不存在")
        if re.search(r'## 决策\s*' + re.escape(str(value)) + r'\s*[：:]', content):
            return (True, f"决策 {value} 存在")
        return (False, f"决策 {value} 不存在")

    if kind == "user":
        return (True, "用户口述（免校验）")

    return (False, f"格式非法: {raw}")


def gate_entry(decisions_text, evidence_text, client_name, strict=False,
               context_path=None, decisions_path=None, base_dir=None):
    """对"决策 + 证据引用"做写入前守门。

    返回 {"verdict", "marker", "evidence_lines", "counts", "reasons"}：
      - 决策空 -> ok（marker=""，无事可守）；
      - 决策非空 + 无引用 -> warn，marker="（待补证据）"；
      - 引用全过 -> ok；
      - 有失败引用 -> 非 strict: warn 且 marker="（证据待核：{第一条失败原因}）"；
                     strict: blocked，reasons 列全部失败原因。
    evidence_lines 形如 "[✓] file:xxx" / "[✗] file:yyy（文件不存在: ...）"。
    """
    counts = {"total_refs": 0, "passed": 0, "failed": 0}
    has_decisions = decisions_text is not None and str(decisions_text).strip()
    has_evidence = evidence_text is not None and str(evidence_text).strip()
    # 监工修复（2026-08-19 真客户实测）：仅"决策与证据都为空"才无事可守。
    # 原逻辑：决策为空直接 return ok -> 传了 --evidence= 与 --strict-evidence=1
    # 但没传 --decisions= 时，坏引用被静默放行（exit 0 写入）——静默失效。
    # 有证据串就必须校验：失败引用 + strict 一律 blocked，与决策是否为空无关。
    if not has_decisions and not has_evidence:
        return {"verdict": "ok", "marker": "", "evidence_lines": [], "counts": counts, "reasons": []}

    refs = parse_source_refs(evidence_text)
    if not refs:
        if has_decisions:
            return {"verdict": "warn", "marker": "（待补证据）", "evidence_lines": [], "counts": counts, "reasons": []}
        # 有证据串但解析不出引用（且无决策）：显式可见的警告，绝不静默
        return {"verdict": "warn", "marker": "（证据待核：无法解析引用）",
                "evidence_lines": [], "counts": counts,
                "reasons": [f"无法从证据串解析出引用: {str(evidence_text)[:80]}"]}

    counts["total_refs"] = len(refs)
    evidence_lines = []
    reasons = []
    for ref in refs:
        ok, reason = verify_source_ref(
            ref, client_name,
            context_path=context_path, decisions_path=decisions_path, base_dir=base_dir,
        )
        if ok:
            counts["passed"] += 1
            evidence_lines.append(f"[✓] {ref.get('raw', '')}")
        else:
            counts["failed"] += 1
            evidence_lines.append(f"[✗] {ref.get('raw', '')}（{reason}）")
            reasons.append(reason)

    if counts["failed"] == 0:
        return {"verdict": "ok", "marker": "", "evidence_lines": evidence_lines, "counts": counts, "reasons": []}
    if strict:
        return {
            "verdict": "blocked",
            "marker": "",
            "evidence_lines": evidence_lines,
            "counts": counts,
            "reasons": reasons,
        }
    return {
        "verdict": "warn",
        "marker": f"（证据待核：{reasons[0]}）",
        "evidence_lines": evidence_lines,
        "counts": counts,
        "reasons": reasons,
    }


def normalize_status(text):
    """把自由文本归一为四态之一：已确认 / 未确认 / 不可读(原因) / 不存在。

    含「已确认/确认过」-> "已确认"；含「未确认/待确认/待核实」-> "未确认"；
    含「不可读」-> 原样保留整段（如 "不可读(PDF加密)"）；含「不存在/没有该」-> "不存在"；
    归不进返回原文；None / 空 -> "未确认"。
    """
    if text is None:
        return "未确认"
    s = text.strip()
    if not s:
        return "未确认"
    if "已确认" in s or "确认过" in s:
        return "已确认"
    if "未确认" in s or "待确认" in s or "待核实" in s:
        return "未确认"
    if "不可读" in s:
        return s
    if "不存在" in s or "没有该" in s:
        return "不存在"
    return s


def detect_conflict(topic, decision_text, decisions_md_path):
    """检测同主题矛盾决策（程序化格式 `## [日期] topic`）。

    返回 {"conflict": bool, "old_date": str|None, "old_heading": str|None}。
    decisions.md 已有 `## [YYYY-MM-DD] {topic}`（topic 全等，忽略首尾空白）且其
    `- **决策**:` 行与 decision_text（均去首尾空白）不同 -> conflict=True + old_date。
    同主题同内容 -> False（幂等重写）；无同主题 / 文件不存在 -> False。
    """
    result = {"conflict": False, "old_date": None, "old_heading": None}
    if topic is None or not str(topic).strip():
        return result
    try:
        with open(decisions_md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return result  # 文件不存在 / 读取失败 -> 无冲突可判

    wanted = str(topic).strip()
    heading_re = re.compile(r'^## \[(\d{4}-\d{2}-\d{2})\]\s*(.*?)\s*$', re.MULTILINE)
    for m in heading_re.finditer(content):
        if m.group(2).strip() != wanted:
            continue
        block_start = m.end()
        next_heading = re.search(r'^## ', content[block_start:], re.MULTILINE)
        block_end = block_start + next_heading.start() if next_heading else len(content)
        block = content[block_start:block_end]
        dm = re.search(r'^- \*\*决策\*\*:\s*(.*)$', block, re.MULTILINE)
        if dm is None:
            continue  # 同主题块缺「决策」行，无法比对，不判冲突
        if dm.group(1).strip() != str(decision_text).strip():
            result["conflict"] = True
            result["old_date"] = m.group(1)
            result["old_heading"] = m.group(0).strip()
            break
    return result


def count_pending_conflicts(decisions_md_path):
    """统计 decisions.md 中未决冲突标记 `<!-- conflict: pending -->` 的次数。"""
    try:
        with open(decisions_md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return 0
    return content.count("<!-- conflict: pending -->")


def scan_memory_health(client_name, client_dir=None):
    """汇总 context.md + decisions.md 的记忆证据健康计数。

    返回 {"client", "context_exists", "decisions_exists", "sessions", "evidence_sections",
          "pending_evidence", "unverified_evidence", "decision_entries", "conflicts_pending"}。
    文件缺失 -> exists=False、计数 0；异常不抛计 0。
    """
    base = client_dir if client_dir is not None else os.path.join(CLIENTS_DIR, client_name)
    context_path = os.path.join(base, "context.md")
    decisions_path = os.path.join(base, "decisions.md")

    def _read(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    result = {
        "client": client_name,
        "context_exists": False,
        "decisions_exists": False,
        "sessions": 0,
        "evidence_sections": 0,
        "pending_evidence": 0,
        "unverified_evidence": 0,
        "decision_entries": 0,
        "conflicts_pending": 0,
    }
    ctx = _read(context_path)
    if ctx is not None:
        result["context_exists"] = True
        result["sessions"] = len(re.findall(r'#{2,3} \[\d{4}-\d{2}-\d{2}\] 第 \d+ 次会话', ctx))
        result["evidence_sections"] = len(re.findall(r'#### 证据', ctx))
        result["pending_evidence"] = ctx.count("（待补证据）")
        result["unverified_evidence"] = ctx.count("（证据待核")
    dec = _read(decisions_path)
    if dec is not None:
        result["decisions_exists"] = True
        result["decision_entries"] = (
            len(re.findall(r'^## 决策 \d+[：:]', dec, re.MULTILINE))
            + len(re.findall(r'^## \[\d{4}-\d{2}-\d{2}\] ', dec, re.MULTILINE))
        )
        result["conflicts_pending"] = dec.count("<!-- conflict: pending -->")
    return result
