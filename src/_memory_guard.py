# -*- coding: utf-8 -*-
"""记忆溯源守门（P0 · T1）：证据引用解析与校验的纯函数层。

设计原则（源自 MyContext 调研，docs/MyContext与兰亭记忆系统对照_2026-08-18.md）：
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

# 统一决策解析器（P0）：决策标题切分与标题提取的共享纯函数。
# 三种格式：## 决策 N：标题 / ### D-NNN · 标题 / ## [YYYY-MM-DD] 标题（可带方括号）
from _graph import _split_decision_blocks

_VALID_KINDS = ("file", "session", "decision", "user")

# I-3 A2：已登记的决策条目类型（新增类型须先登记；gate_entry 对未知类型给可见 warn，
# 三道闸语义不变——条目类型不是新写入通道）
_VALID_ENTRY_TYPES = ("keynote_change",)


def _extract_theme_title(first_line):
    """从三种决策标题格式提取主题标题（纯函数，统一决策解析器）。

    - 格式1：## 决策 N：标题
    - 格式2：### D-NNN · 标题
    - 格式3：## [YYYY-MM-DD] 标题 / ## YYYY-MM-DD：标题
    解析不出 -> 原样返回首行。
    """
    s = first_line.strip()
    if not s:
        return ""
    # 格式2：### D-NNN · 标题（兼容 ·•.: ： 全半角分隔符）
    m = re.match(r'^#{1,3}\s*D-\d+\s*[·•.:：]?\s*(.+)$', s)
    if m:
        return m.group(1).strip()
    # 格式1：## 决策 N：标题
    m = re.match(r'^##\s*决策\s*\d+\s*[：:]\s*(.+)$', s)
    if m:
        return m.group(1).strip()
    # 格式3：## [YYYY-MM-DD] 标题 / ## YYYY-MM-DD：标题（可带方括号/冒号/点/短横）
    m = re.match(r'^##\s*\[?\d{4}-\d{2}-\d{2}\]?\s*[：:．.\-]?\s*(.*)$', s)
    if m:
        return m.group(1).strip()
    return s


def parse_source_refs(text):
    """解析分号分隔的证据引用串为条目列表。

    每条 `kind:value`，kind ∈ {file, session, decision, user}：
      - file：value 反斜杠归一为正斜杠并剥离 `#锚点`（anchor 仅记录，不校验）；
      - session：value 为整数字符串（整数性由 verify_source_ref 校验）；
      - decision：value 可为整数（## 决策 N / ### D-NNN）或非数值（task_id /
        主题标题，P0 单轨化后按 task_id 或标题定位，校验在 verify_source_ref）；
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
    # #48/D2：按名解析支持 _internal/ 内部账本目录回退（证据校验读账本记忆）
    from _paths import client_dir as _resolve_client_dir
    if context_path is None:
        context_path = os.path.join(
            _resolve_client_dir(client_name, clients_dir=CLIENTS_DIR), "context.md")
    if decisions_path is None:
        decisions_path = os.path.join(
            _resolve_client_dir(client_name, clients_dir=CLIENTS_DIR), "decisions.md")

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
        value_s = str(value)
        # 数值引用：兼容格式1（## 决策 N）与格式2（### D-NNN）
        if value_s.isdigit():
            if re.search(r'## 决策\s*' + re.escape(value_s) + r'\s*[：:]', content):
                return (True, f"决策 {value_s} 存在")
            if re.search(r'^#{1,3}\s*D-' + re.escape(value_s.zfill(3)) + r'\b',
                         content, re.MULTILINE):
                return (True, f"决策 D-{value_s.zfill(3)} 存在")
            if re.search(r'^#{1,3}\s*D-' + re.escape(value_s) + r'\b',
                         content, re.MULTILINE):
                return (True, f"决策 D-{value_s} 存在")
            return (False, f"决策 {value_s} 不存在")
        # 非数值引用：新 task 决策按 task_id 或主题标题定位（P0 单轨化）
        if re.search(r'[-*]\s*\*{0,2}task_id\*{0,2}\s*[：:]\s*'
                     + re.escape(value_s) + r'\b', content):
            return (True, f"决策 {value_s} 存在（task_id）")
        blocks = _split_decision_blocks(content)
        for block in blocks[1:]:
            fm = re.match(r'^\s*([^\n]+?)(?:\n|$)', block)
            first_line = fm.group(1) if fm else ""
            if _extract_theme_title(first_line) == value_s:
                return (True, f"决策「{value_s}」存在")
        return (False, f"决策「{value_s}」不存在")

    if kind == "user":
        return (True, "用户口述（免校验）")

    return (False, f"格式非法: {raw}")


def gate_entry(decisions_text, evidence_text, client_name, strict=False,
               context_path=None, decisions_path=None, base_dir=None,
               entry_type=None):
    """gate_entry 包装层（I-3 A2）：识别条目类型，证据校验委托 _gate_entry_impl。

    entry_type: None=普通会话决策；"keynote_change"=基调变更事件（复用同一套
    证据语法与三道闸语义）。未知类型 -> 证据照常校验，但结果降级为可见 warn
    （verdict=ok 时改 warn + marker；blocked/warn 时追加 reason），绝不静默。
    """
    result = _gate_entry_impl(decisions_text, evidence_text, client_name,
                              strict=strict, context_path=context_path,
                              decisions_path=decisions_path, base_dir=base_dir)
    result["entry_type"] = entry_type
    if entry_type is not None and entry_type not in _VALID_ENTRY_TYPES:
        result["reasons"] = result.get("reasons", []) + [f"未知条目类型: {entry_type}"]
        unk = f"（条目类型未知: {entry_type}）"
        if result["verdict"] == "ok":
            result["verdict"] = "warn"
            result["marker"] = unk
        elif result["verdict"] == "warn" and unk not in result.get("marker", ""):
            result["marker"] = result["marker"] + unk
    return result


def _gate_entry_impl(decisions_text, evidence_text, client_name, strict=False,
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
    """检测同主题矛盾决策（兼容三种标题格式）。

    返回 {"conflict": bool, "old_date": str|None, "old_heading": str|None}。
    decisions.md 已有同主题条目（三种标题格式之一：## 决策 N / ### D-NNN /
    ## [日期]）且其 `- **决策**:` 行与 decision_text（均去首尾空白）不同 ->
    conflict=True + old_date。
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
    blocks = _split_decision_blocks(content)
    for block in blocks[1:]:  # 跳过文件头
        fm = re.match(r'^\s*([^\n]+?)(?:\n|$)', block)
        first_line = fm.group(1) if fm else ""
        if _extract_theme_title(first_line) != wanted:
            continue
        dm = re.search(r'^- \*\*决策\*\*:\s*(.*)$', block, re.MULTILINE)
        if dm is None:
            continue  # 同主题块缺「决策」行，无法比对，不判冲突
        if dm.group(1).strip() != str(decision_text).strip():
            result["conflict"] = True
            # old_date：与 _theme_guard 标记插入同口径（B3 P2 统一）——标题行
            # [日期] 优先、退回无括号日期；不扫整块（正文他处日期曾致两模块
            # 锚定到不同块，pending 标记插不进、矛盾铁律双载 HEAD）
            date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', first_line)
            if not date_match:
                date_match = re.search(r'^##\s*\[?(\d{4}-\d{2}-\d{2})\]?',
                                       first_line)
            result["old_date"] = date_match.group(1) if date_match else None
            result["old_heading"] = first_line.strip()
            break
    return result


# 未决冲突双形态（resolve-conflict 泛化，#61 单一事实源）：①HTML pending 标记
# （现版 save_decision 经 _append_conflict_flag 写入）；②「⚠️ 冲突」行（现版新块尾
# 携带，旧版写入产物常只剩此行、无 HTML 标记——如示例集团 decisions.md 存量块）。
# 任一命中即未决。本模块是 _theme_guard 的下层依赖（_theme_guard 模块级 import
# 本模块，反向不可 import），故判定真源放在此处，_theme_guard._block_is_pending
# 薄委托至此，两边永不再漂移。
_CONFLICT_PENDING_HTML = "<!-- conflict: pending -->"
_CONFLICT_WARN_RE = re.compile(r'\*\*⚠️ 冲突\*\*')


def _block_has_pending_conflict(block_text):
    """块级未决判定（双形态）：HTML pending 标记或「⚠️ 冲突」行，任一命中即未决。"""
    return _CONFLICT_PENDING_HTML in block_text or bool(_CONFLICT_WARN_RE.search(block_text))


def _count_pending_conflict_blocks(content):
    """按决策块计数未决冲突块（一块同时带双形态标记只算 1 条）。

    口径 = 未决「块」数：现版一块至多一个 HTML 标记（_append_conflict_flag 幂等），
    旧版存量一块至多一条 ⚠️ 行，按块计数与标记出现次数在实际文件上等价，
    且天然覆盖「只有 ⚠️ 行、无 HTML 标记」的孤儿块（改前计 0，健康线失真）。
    """
    return sum(1 for block in _split_decision_blocks(content or "")
               if _block_has_pending_conflict(block))


def count_pending_conflicts(decisions_md_path):
    """统计 decisions.md 中未决冲突块数（双形态：HTML pending 标记或「⚠️ 冲突」行）。"""
    try:
        with open(decisions_md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return 0
    return _count_pending_conflict_blocks(content)


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
    ctx_pending = ctx.count("（待补证据）") if ctx else 0
    ctx_unverified = ctx.count("（证据待核") if ctx else 0
    if ctx is not None:
        result["context_exists"] = True
        result["sessions"] = len(re.findall(r'#{2,3} \[\d{4}-\d{2}-\d{2}\] 第 \d+ 次会话', ctx))
        result["evidence_sections"] = len(re.findall(r'#### 证据', ctx))
    dec = _read(decisions_path)
    if dec is not None:
        result["decisions_exists"] = True
        # 统一决策解析器：三种标题格式都计入（## 决策 N / ### D-NNN / ## [日期]）
        result["decision_entries"] = max(0, len(_split_decision_blocks(dec)) - 1)
        # 冲突未决计数走双形态单一事实源（#61）：只有 ⚠️ 行、无 HTML 标记的
        # 旧版存量块同样计入，否则健康线「冲突未决 N 条」漏报（示例集团实弹 2 组）
        result["conflicts_pending"] = _count_pending_conflict_blocks(dec)
        # P0 单轨化：task 决策把证据标记写在 decisions.md（reason 字段），
        # 待补/待核证据计数必须两个文件都统计，否则 health 报告漏报。
        result["pending_evidence"] = ctx_pending + dec.count("（待补证据）")
        result["unverified_evidence"] = ctx_unverified + dec.count("（证据待核")
    else:
        result["pending_evidence"] = ctx_pending
        result["unverified_evidence"] = ctx_unverified
    return result


def format_report(h):
    """把 scan_memory_health 的 dict 格式化为「记忆证据健康」报告文本（P3 统一口径）。

    cmd_memory_health 与 audit --mode memory（_audit_memory）共用同一函数，
    保证同源同口径（决策真源一份、健康报告一份）。
    """
    lines = []
    ctx_note = (f"存在（会话 {h['sessions']} 次 / 证据段 {h['evidence_sections']}）"
                if h["context_exists"] else "不存在")
    dec_note = (f"存在（决策 {h['decision_entries']} 条 / 冲突未决 {h['conflicts_pending']} 条）"
                if h["decisions_exists"] else "不存在")
    lines.append(f"context.md:   {ctx_note}")
    lines.append(f"decisions.md: {dec_note}")
    if h["pending_evidence"] or h["unverified_evidence"]:
        lines.append(f"证据状态: ⚠ 待补 {h['pending_evidence']} / 待核 {h['unverified_evidence']}"
                     "（新 save 带 --evidence= 可消除；已落盘条目需手工补证据）")
    else:
        lines.append("证据状态: 无待补/待核")
    if h["conflicts_pending"]:
        lines.append(f"⚠ 冲突未决 {h['conflicts_pending']} 条（resolve-conflict 裁决）")
    return "\n".join(lines)
