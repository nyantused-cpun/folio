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
import hashlib
import os
import re
from datetime import datetime

import _memory_guard
from _graph import DECISION_HEADING_SPLIT_RE, _split_decision_blocks as _graph_split_decision_blocks
from _memory_guard import _extract_theme_title, _CONFLICT_PENDING_HTML
from _paths import CLIENTS_DIR, SCRIPT_DIR

# I-3 A2：keynote_change 决策条目类型（ADR-009 案 2' 事件流；登记见 _memory_guard._VALID_ENTRY_TYPES）
KEYNOTE_ENTRY_TYPE = "keynote_change"

# keynote_change 条目标题唯一拼装点：写入侧（append_keynote_change）与引用侧
# （_session.save_session 的 context.md「见 decisions.md：<标题>」行）必须同源，
# 否则两处字面量各自漂移会让引用悬空（P3 2026-09-06）。
KEYNOTE_TOPIC_PREFIX = "keynote_change 基调变更"


def keynote_change_topic(version):
    """keynote_change 决策条目标题（写入与引用两侧唯一来源）。"""
    return f"{KEYNOTE_TOPIC_PREFIX} {version or 'v?'}"


def _client_dir(client_name):
    """按名解析客户目录：顶层优先，_internal/ 内部账本位回退（#48/D2）。

    经 _paths.client_dir 收口；读模块级 CLIENTS_DIR（单测可 monkeypatch 注入 tmp）。
    """
    from _paths import client_dir as _resolve
    return _resolve(client_name, clients_dir=CLIENTS_DIR)

# 已废弃状态行（resolve_conflict 写入后，load_active_themes 据此跳过，防矛盾铁律双加载）
_DEPRECATED_RE = re.compile(r'[-*]\s*\*{0,2}状态\*{0,2}\s*[：:]\s*已废弃')

# 决策标题形态判定（P3 2026-09-06）：与统一决策解析器 _graph.DECISION_HEADING_SPLIT_RE
# 的三种格式同口径——含无括号日期（## YYYY-MM-DD：标题，早期客户遗留格式）。
# 此前文件头判定用字面量元组（"## 决策"/"### D-"/"## ["）漏掉无括号形态，
# 首块若是该形态的真决策会被误当文件头丢弃。_graph 的切分正则是唯一事实源，
# 本处只做镜像匹配（_graph 不可从 match 视角复用 lookahead 正则）。
_DECISION_HEAD_RE = re.compile(r'^(?:## 决策 \d+|### D-\d+|## \[?\d{4}-\d{2}-\d{2}\]?)')

# W1-3 防灌水：块内「复发」行（_merge_same_day_decision 写入 / 历史合并脚本同格式）。
# 只计「第 N 次」逐次行——历史合并脚本写入的汇总行（「共 N 次（首末时间）」）不算数，
# 否则脚本清偿后的同日复发会被少计。
_RECURRENCE_LINE_RE = re.compile(r'(?m)^- \*\*复发\*\*[：:] 第 \d+ 次')

# 复发行「最新 issues」截断长度（首条一行，防长 issues 撑爆条目）
_RECURRENCE_ISSUE_MAX = 80

# 未决冲突双形态（resolve-conflict 泛化）：①HTML pending 标记（现版 save_decision
# 经 _append_conflict_flag 写入）；②「⚠️ 冲突」行（现版新块尾携带，旧版写入产物
# 常只剩此行、无 HTML 标记——如示例集团 decisions.md 存量块）。任一命中即未决。
# 判定真源在 _memory_guard._block_has_pending_conflict（#61：本模块模块级依赖
# _memory_guard，反向不可 import，双形态判定下沉下层后各消费方永不再漂移）；
# 标记常量 _CONFLICT_PENDING_HTML 随顶部 from-import 导入，供 _append_conflict_flag
# 插入 / _neutralize_conflict_markers 清理引用。
# 改写用整行形态（判定宽松、改写锚定行首，避免误伤正文中巧合出现的子串）
_CONFLICT_WARN_LINE_RE = re.compile(r'(?m)^- \*\*⚠️ 冲突\*\*[：:].*$')
# HTML 标记按整行移除（插入时独占一行），不留空行
_CONFLICT_HTML_LINE_RE = re.compile(r'(?m)^[ \t]*<!-- conflict: pending -->[ \t]*\n?')


def _normalize_topic_key(topic):
    """W1-3 幂等键的 topic 归一化：剥离全部空白字符（含全角空格）。

    「review FAIL:  a.html」与「review FAIL: a.html」视为同题，防同名异写绕过去重。
    """
    return "".join(str(topic).split())


def _merge_same_day_decision(decisions_path, today, topic, reason):
    """W1-3 防灌水：同日同题块已存在时不新增块，在原块尾追加一行「复发」记录。

    幂等键 = client + 当日 date + 归一化 topic（压空白，见 _normalize_topic_key）。
    命中 -> 原块尾追加 `- **复发**: 第 N 次（HH:MM），最新 issues: …` 并写回，
    返回 True（调用方跳过 append）；未命中 / 文件读不了 -> 返回 False（照旧追加）。
    N 的口径：原始块本身计第 1 次，复发行记录全局第 N 次发生
    = 块内已有复发行数 + 2（同日同题双调 -> 第 2 次）。
    含未决冲突标记或已废弃状态的块不归并（防污染冲突裁决语义）。
    """
    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeError):
        return False
    wanted = _normalize_topic_key(topic)
    if not wanted:
        return False
    matches = list(DECISION_HEADING_SPLIT_RE.finditer(content))
    for i, m in enumerate(matches):
        line_end = content.find("\n", m.start())
        first_line = content[m.start():line_end if line_end != -1 else None]
        # 日期：标题行 [YYYY-MM-DD] 优先，退回无括号形态（与 _programmatic_blocks 同口径）
        date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', first_line)
        if not date_match:
            date_match = re.search(r'^##\s*\[?(\d{4}-\d{2}-\d{2})\]?', first_line)
        if not date_match or date_match.group(1) != today:
            continue
        if _normalize_topic_key(_extract_theme_title(first_line)) != wanted:
            continue
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[m.start():block_end]
        if _block_is_pending(block) or _DEPRECATED_RE.search(block):
            continue  # 双形态未决判定（#61）：⚠️ 行存量块同样不归并，防污染裁决语义
        n = len(_RECURRENCE_LINE_RE.findall(block)) + 2
        reason_stripped = str(reason or "").strip()
        issue = reason_stripped.splitlines()[0] if reason_stripped else "(未记录)"
        issue = issue[:_RECURRENCE_ISSUE_MAX]
        hhmm = datetime.now().strftime("%H:%M")
        prefix = content[:block_end]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"  # 末块可能无结尾换行，补齐防串行
        content = (prefix
                   + f"- **复发**: 第 {n} 次（{hhmm}），最新 issues: {issue}\n"
                   + content[block_end:])
        with open(decisions_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False


# ============================================================
# 决策记录（写入 decisions.md，含 persistence 字段）
# ============================================================

def _append_conflict_flag(decisions_path, old_date, topic):
    """在旧条目块的块尾插入未决冲突标记 `<!-- conflict: pending -->`。

    统一决策解析器定位旧块（三种标题格式：## 决策 N / ### D-NNN / ## [日期]）。
    只插标记、不改正文；幂等（块内已有标记则不重复）；找不到旧块则静默返回。
    """
    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return  # 文件不存在/读取失败 -> 无处可插
    wanted = str(topic).strip()
    wanted_date = str(old_date).strip() if old_date is not None else ""
    matches = list(DECISION_HEADING_SPLIT_RE.finditer(content))
    for i, m in enumerate(matches):
        line_end = content.find("\n", m.start())
        first_line = content[m.start():line_end if line_end != -1 else None]
        if _extract_theme_title(first_line) != wanted:
            continue
        # 日期匹配（old_date 为空则不校验）
        if wanted_date and wanted_date != "None":
            date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]',
                                   content[m.start():line_end if line_end != -1 else None])
            if not date_match:
                date_match = re.search(r'^##\s*\[?(\d{4}-\d{2}-\d{2})\]?', first_line)
            if not date_match or date_match.group(1) != wanted_date:
                continue
        # 块边界：下一个决策标题起点或文件尾
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[m.start():block_end]
        if "<!-- conflict: pending -->" in block:
            return  # 幂等：已有标记
        content = content[:block_end] + "\n<!-- conflict: pending -->\n" + content[block_end:]
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
                  source="", confidence=0.5, strict=False, _skip_lock=False,
                  entry_type=None):
    """记录关键决策到 decisions.md（含溯源 + 冲突保留）。

    记"为什么这么定、为什么不要那个"。
    level: L3/L4/L5，标记决策时的自动化层级
    persistence: permanent（永久）/ task（临时，默认）
    scope: client（客户级）/ task（任务级）
    task_id: scope=task 时必填，任务结束后自动归档
    source: 证据引用串（分号分隔 kind:value，见 _memory_guard.parse_source_refs）
    confidence: 0.0-1.0 置信度（仅记录，不参与判定）
    strict: True 时来源引用验不过 -> 抛 ValueError，什么都不落盘
    entry_type: 条目类型（I-3 A2，如 keynote_change；None=普通决策），写入 **type** 字段

    F0-8：写 decisions.md 前获取客户级 .save_lock，与 save_session 同一把锁，
    避免并发 save + theme-guard 丢更新。
    返回 decisions_path；锁获取失败时返回 None（不假装成功写入）。
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    client_path = _client_dir(client_name)
    if not os.path.exists(client_path):
        os.makedirs(client_path, exist_ok=True)

    decisions_path = os.path.join(client_path, "decisions.md")
    today = datetime.now().strftime("%Y-%m-%d")

    from _save_lock import acquire_save_lock, release_save_lock
    lock_fd = None
    if not _skip_lock:
        lock_fd = acquire_save_lock(client_path)
        if lock_fd is None:
            print(f"[决策] 获取保存锁失败：{os.path.join(client_path, '.save_lock')} "
                  f"被其他进程持有，决策未写入")
            return None

    try:
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

        # W1-3 防灌水：同日同题块已存在 -> 原块尾归并为「复发」行，不新增块。
        # 置于 strict 来源校验之后（任何落盘前校验优先）；conflict 时走原冲突流
        # （新增 ⚠️ 块），不归并，防污染裁决语义。
        if (not conflict and os.path.exists(decisions_path)
                and _merge_same_day_decision(decisions_path, today, topic, reason)):
            print(f"[决策] 同日同题已存在，归并为复发记录: {client_name} / {topic}")
            return decisions_path

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
        if entry_type:
            entry += f"\n- **type: {entry_type}**"
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
    finally:
        if lock_fd is not None:
            release_save_lock(client_path, lock_fd)


def append_session_decision(client_name, topic, decision, evidence_marker="", session_ref="",
                            entry_type=None, source=None):
    """P0 决策单轨化 + I-6 写赢语义：把会话级决策（save --decisions）写入 decisions.md（task 条目）。

    包装 save_decision：固定 persistence=task、scope=task、task_id=<date>#<session>。
    I-6：同 (client, task_id) 已存在 -> **更新该块「决策」内容**（后写赢，与 task_history
    一致），decisions.md 保持单块不膨胀（不再跳过）。
    evidence_marker: gate_entry 返回的证据标记（如"（待补证据）"），记入 reason 字段保持可见。
    session_ref: 会话标识（DSH session id 或会话序号），用于 task_id 与幂等判定。
    entry_type: 条目类型（I-3 A2，如 keynote_change；None=普通会话决策），写入 **type** 字段。
    source: 证据引用串（None=默认 user:会话决策）。
    返回 decisions_path；写失败返回 None。
    """
    task_id = f"{datetime.now().strftime('%Y-%m-%d')}#{session_ref or 'session'}"
    decisions_path = os.path.join(_client_dir(client_name), "decisions.md")
    # I-6 upsert：同 task_id 已存在 -> 更新「决策」行，不重复 append
    if os.path.exists(decisions_path):
        try:
            with open(decisions_path, "r", encoding="utf-8") as f:
                existing = f.read()
            blocks = re.split(r'(?m)^(?=#{1,6} \[)', existing)
            for i, blk in enumerate(blocks):
                if re.search(r'task_id\s*[：:]\s*' + re.escape(task_id) + r'\b', blk):
                    # P1-14：替换串改函数形式——decision 含 \1/\n 等转义序列时
                    # 字符串形式会被 re.sub 当反向引用/转义解释（炸 re.error 或静默改写内容）
                    new_blk = re.sub(
                        r'(?m)^- \*\*决策\*\*[：:].*$',
                        lambda _m: f'- **决策**: {decision}',
                        blk, count=1)
                    if new_blk == blk:  # 块内无「决策」行（异常块）-> 追加一行
                        new_blk = blk.rstrip() + f'\n- **决策**: {decision}\n'
                    # P3（2026-09-06）：理由行同步以新值覆盖——否则首轮写入的
                    # 「（待补证据）」标记在补证据后的 upsert 里清不掉，残留旧
                    # reason 使健康计数（待补证据条数）永久虚高。空标记归位
                    # 「(未记录)」，与 save_decision 的渲染口径一致。
                    new_blk = re.sub(
                        r'(?m)^- \*\*理由\*\*[：:].*$',
                        lambda _m: f'- **理由**: {evidence_marker or "(未记录)"}',
                        new_blk, count=1)
                    with open(decisions_path, "w", encoding="utf-8") as f:
                        f.write("".join(blocks[:i] + [new_blk] + blocks[i + 1:]))
                    return decisions_path
        except (OSError, UnicodeError) as e:
            # P2-15：非 UTF-8 / 读取失败不阻断写入（与 detect_conflict 兜底口径一致）
            print(f"[决策] decisions.md 读取失败（{e}），跳过幂等检查照常追加")
    return save_decision(
        client_name, topic, decision,
        reason=evidence_marker or "",
        persistence="task", scope="task", task_id=task_id,
        source=source or "user:会话决策",
        entry_type=entry_type,
        _skip_lock=True,
    )


# ============================================================
# keynote 基调卡（ADR-009 案 2'：keynote.md 状态真源 + decisions 事件流）
# ============================================================
def load_keynote(client_name):
    """读取客户 keynote.md（I-3 A1 模板 parser 唯一实现）。缺失/读取失败 -> None。

    返回 {"path", "version", "effective_date", "approver", "lines", "structure", "sha256"}；
    lines = [{"name", "content", "weight", "order", "basis"}]（线清单表格行，
    首列前导序号已剥离）。parser 只认模板固定小节标题与线清单表格列序。
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    path = os.path.join(_client_dir(client_name), "keynote.md")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8")
    except Exception:
        return None
    version = re.search(r'版本[：:]\s*(v\d+)', text)
    effective = re.search(r'生效日期[：:]\s*(\d{4}-\d{2}-\d{2})', text)
    approver = re.search(r'批准人[：:]\s*([^｜\n]+)', text)
    lines = []
    in_table = False
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if s.startswith("## "):
            in_table = (s[3:].strip() == "线清单")
            continue
        if not in_table or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("线", "") or set(cells[0]) <= {"-", ":"}:
            continue  # 表头 / 分隔行 / 空行跳过
        lines.append({
            "name": re.sub(r'^\d+\s*', '', cells[0]).strip(),
            "content": cells[1], "weight": cells[2], "order": cells[3],
            "basis": cells[4],
        })
    structure = re.search(r'(?m)^## 呈现结构\s*\n+([^\n#]+)', text)
    return {
        "path": path,
        "version": version.group(1) if version else "",
        "effective_date": effective.group(1) if effective else "",
        "approver": approver.group(1).strip() if approver else "",
        "lines": lines,
        "structure": structure.group(1).strip() if structure else "",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def append_keynote_change(client_name, summary, approver="用户", conflict_note="",
                          session_ref=""):
    """A2：keynote_change 事件写入 decisions.md——只记事件，不复述内容（ADR-009 案 2'）。

    条目「决策」行 = 摘要一行 + 版本化指针（keynote.md@版本 + sha256）+ 批准人
    + 冲突并列说明（如有）。keynote.md 缺失 -> 拒绝写入返回 None（无状态真源则
    无事件可指）。证据复用现有语法：file:keynote.md + user:批准人。
    """
    kn = load_keynote(client_name)
    if kn is None:
        print(f"[决策] {client_name} 无 keynote.md，keynote_change 事件未写入")
        return None
    version = kn["version"] or "v?"
    decision = (f"{summary}｜指针: keynote.md@{version} sha256:{kn['sha256']}"
                f"｜批准人: {approver}")
    if conflict_note:
        decision += f"｜冲突并列: {conflict_note}"
    rel = os.path.relpath(kn["path"], SCRIPT_DIR).replace(os.sep, "/")
    return append_session_decision(
        client_name, keynote_change_topic(version), decision,
        session_ref=session_ref,
        source=f"file:{rel};user:{approver}", entry_type=KEYNOTE_ENTRY_TYPE)


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
    decisions_path = os.path.join(_client_dir(client_name), "decisions.md")
    if not os.path.exists(decisions_path):
        return []

    with open(decisions_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 统一决策解析器：按三种决策标题格式切块（## 决策 N / ### D-NNN / ## [日期]）
    blocks = _graph_split_decision_blocks(content)
    # 第一个块是文件头（# 客户 决策记录），不以决策标题开头 -> 丢弃。
    # P3（2026-09-06）：判定与统一解析器三种形态同口径（含无括号日期），
    # 防止首块为该形态的真决策时被误当文件头丢弃。
    if not blocks:
        return []
    if not _DECISION_HEAD_RE.match(blocks[0].lstrip()):
        blocks = blocks[1:]
    if not blocks:
        return []

    themes = []
    for block in blocks:
        # 跳过未决冲突 / 已废弃块（防矛盾铁律双加载）。
        # 未决判定走双形态单一事实源（#61）：只有「⚠️ 冲突」行、无 HTML 标记的
        # 旧版存量块同样跳过，不再被当 active 铁律加载。
        if _block_is_pending(block) or _DEPRECATED_RE.search(block):
            continue
        # 标题：第一行，按三种标题格式提取
        title_match = re.match(r'^\s*([^\n]+?)(?:\n|$)', block)
        first_line = title_match.group(1) if title_match else ""
        title = _extract_theme_title(first_line)

        # 提取日期（兼容 [YYYY-MM-DD] 标题前缀、## YYYY-MM-DD：标题前缀、
        # 和 **日期**：YYYY-MM-DD 内嵌三种格式）
        date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', block)
        if not date_match:
            date_match = re.search(r'[-*]\s*\*{0,2}日期\*{0,2}\s*[：:]\s*(\d{4}-\d{2}-\d{2})', block)
        if not date_match:
            date_match = re.search(r'^##\s*\[?(\d{4}-\d{2}-\d{2})\]?', block, re.MULTILINE)
        source_date = date_match.group(1) if date_match else "未知日期"

        # 提取 persistence（缺失默认 permanent，向后兼容旧铁律）
        pers_match = re.search(r'[-*]\s*\*{0,2}persistence\*{0,2}\s*[：:]\s*(\w+)', block)
        persistence = pers_match.group(1).strip().lower() if pers_match else "permanent"

        # 提取 scope（缺失默认 client）
        scope_match = re.search(r'[-*]\s*\*{0,2}scope\*{0,2}\s*[：:]\s*(\w+)', block)
        scope = scope_match.group(1).strip().lower() if scope_match else "client"

        # 提取 task_id
        tid_match = re.search(r'[-*]\s*\*{0,2}task_id\*{0,2}\s*[：:]\s*([^\s*]+)', block)
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
        # 边界：在下一个 `- **字段` 行、`**字段` 行、`##` 或文件尾停止（避免把追加的 persistence/scope 字段吃进描述）
        impact_match = re.search(r'[-*]\s*\*{0,2}(?:影响范围|impact)\*{0,2}[：:]\s*\n?(.*?)(?=\n- \*\*|\n\*\*|\n##|\Z)', block, re.DOTALL)
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


def load_recent_task_decisions(client_name, limit=3):
    """读取 decisions.md 尾部 limit 条 task 决策（persistence=task）摘要。

    P0 决策单轨化：L4 上下文注入最近 task 决策摘要（save --decisions 写入的条目）。
    跳过未决冲突 / 已废弃块。返回 [{title, decision, task_id}, ...]（按文件顺序尾部取）。
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    decisions_path = os.path.join(_client_dir(client_name), "decisions.md")
    if not os.path.exists(decisions_path):
        return []
    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []
    results = []
    for block in reversed(_graph_split_decision_blocks(content)[1:]):  # 跳过文件头，尾部往前
        if _block_is_pending(block) or _DEPRECATED_RE.search(block):  # 双形态判定（#61）
            continue
        pers = re.search(r'[-*]\s*\*{0,2}persistence\*{0,2}\s*[：:]\s*(\w+)', block)
        if not pers or pers.group(1).strip().lower() != "task":
            continue
        fm = re.match(r'^\s*([^\n]+?)(?:\n|$)', block)
        first_line = fm.group(1) if fm else ""
        title = _extract_theme_title(first_line)
        dm = re.search(r'[-*]\s*\*{0,2}决策\*{0,2}\s*[：:]\s*([^\n]+)', block)
        decision_text = dm.group(1).strip() if dm else ""
        tid = re.search(r'[-*]\s*\*{0,2}task_id\*{0,2}\s*[：:]\s*([^\s*]+)', block)
        results.append({
            "title": title or decision_text[:50],
            "decision": decision_text[:200],
            "task_id": tid.group(1).strip() if tid else "",
        })
        if len(results) >= limit:
            break
    return results


def _programmatic_blocks(content):
    """把 decisions.md 内容切成块 [{date, topic, start, end, text}]（统一解析器）。

    块边界：三种决策标题（## 决策 N / ### D-NNN / ## [日期]）到下一个决策标题前
    （或文件尾）。旧格式（### D-NNN 等）同样可定位——P0 统一解析器后覆盖旧格式。
    """
    result = []
    matches = list(DECISION_HEADING_SPLIT_RE.finditer(content))
    for i, m in enumerate(matches):
        start = m.start()
        line_end = content.find("\n", start)
        first_line = content[start:line_end if line_end != -1 else None]
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]',
                               content[start:line_end if line_end != -1 else None])
        if not date_match:
            date_match = re.search(r'^##\s*\[?(\d{4}-\d{2}-\d{2})\]?', first_line)
        result.append({
            "date": date_match.group(1) if date_match else "",
            "topic": _extract_theme_title(first_line),
            "start": start,
            "end": end,
            "text": content[start:end],
        })
    return result


def _block_is_pending(block_text):
    """块级未决判定（双形态）：HTML pending 标记或「⚠️ 冲突」行，任一命中即未决。

    #61 单一事实源：判定真源下沉 _memory_guard._block_has_pending_conflict
    （本模块模块级依赖 _memory_guard，反向不可 import），此处薄委托——
    count_pending_conflicts / load_active_themes / load_recent_task_decisions /
    resolve-conflict 全部同源同判，两形态永不漂移。
    """
    return _memory_guard._block_has_pending_conflict(block_text)


def _neutralize_conflict_markers(block_text):
    """清除块内全部未决冲突标记（裁决落盘时统一清理，双形态都覆盖）。

    - HTML pending 标记整行移除（独占一行写入，行级删除不留空行）；
    - 「⚠️ 冲突」行改写为「冲突裁决」，措辞沿既有「，待人工裁决（resolve-conflict）」
      ->「已裁决」替换思路，对无 HTML 标记只有 ⚠️ 行的旧版形态同样生效；
    - ⚠️ 标记若原样残留会被双形态判定再当未决（重复裁决/误列未决）——标记语义
      必须跟随状态走，裁决后块内不得残留「待人工裁决」字样。
    """
    def _rewrite_warn_line(m):
        line = m.group(0)
        line = line.replace("**⚠️ 冲突**", "**冲突裁决**")
        line = line.replace("，待人工裁决（resolve-conflict）", "，已裁决")
        return line.replace("待人工裁决", "已裁决")  # 兜底：旧版措辞变体

    text = _CONFLICT_HTML_LINE_RE.sub("", block_text)
    text = text.replace(_CONFLICT_PENDING_HTML, "")  # 非行首形态的兜底
    return _CONFLICT_WARN_LINE_RE.sub(_rewrite_warn_line, text)


def _match_topic_blocks(topic, blocks):
    """主题块匹配：先精确全串，未命中退「唯一子串」匹配（resolve-conflict 泛化）。

    主题标题常为 200+ 字长串，CLI 传全串几乎不可用。用户传短串命中恰好 1 个
    主题即用之；命中多个候选 -> 报错并列出候选（每条截 40 字）；0 命中 -> 无此主题。
    返回 (matched_blocks, "")；失败返回 ([], 错误详情)。
    """
    wanted = str(topic).strip() if topic is not None else ""
    if not wanted:
        return [], "缺少主题（--topic）"
    exact = [b for b in blocks if b["topic"] == wanted]
    if exact:
        return exact, ""
    hits = [b for b in blocks if wanted in (b["topic"] or "")]
    if not hits:
        return [], f"无此主题: {wanted[:40]}"
    candidates = sorted({b["topic"] for b in hits})
    if len(candidates) > 1:
        return [], ("主题子串命中多个候选，请用更长子串或完整主题: "
                    + "；".join(c[:40] for c in candidates))
    return hits, ""


def resolve_conflict(client_name, topic, keep):
    """人工裁决同主题未决冲突。keep: "old"|"new"。返回 {"resolved": bool, "detail": str}。

    泛化语义（P0）：
    - 未决判定双形态：HTML pending 标记或「⚠️ 冲突」行（覆盖旧版写入的存量块）；
    - 主题先精确全串、后唯一子串匹配（长标题 CLI 传参可用性）；
    - 同主题 >=2 块且至少 1 块未决即可裁决：keep=old 最早块胜 / keep=new 最晚块胜，
      其余全部块（含中间块）标「已废弃」；仅剩 1 块孤儿未决块（对侧已被清理的
      存量形态）同样可裁决——单胜者、无败方，只清标记；
    - 落盘统一清理双形态标记：胜方块标「冲突已裁决（本条保留/生效）」，任何块
      不残留「待人工裁决」措辞。
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    if keep not in ("old", "new"):
        return {"resolved": False, "detail": f"keep 参数非法: {keep}（应为 old|new）"}

    decisions_path = os.path.join(_client_dir(client_name), "decisions.md")
    if not os.path.exists(decisions_path):
        return {"resolved": False, "detail": "无未决冲突"}

    with open(decisions_path, "r", encoding="utf-8") as f:
        content = f.read()

    topic_blocks, match_err = _match_topic_blocks(topic, _programmatic_blocks(content))
    if match_err:
        return {"resolved": False, "detail": match_err}
    if not any(_block_is_pending(b["text"]) for b in topic_blocks):
        return {"resolved": False, "detail": "无未决冲突"}

    # keep=old 最早块胜 / keep=new 最晚块胜（文件序即追加序，等价时间序）
    winner = topic_blocks[0] if keep == "old" else topic_blocks[-1]
    win_word = "保留" if keep == "old" else "生效"
    n_losers = len(topic_blocks) - 1

    edits = []
    for b in topic_blocks:
        text = _neutralize_conflict_markers(b["text"]).rstrip("\n")
        if b is winner:
            extra = f"，其余 {n_losers} 条已废弃" if n_losers else ""
            text += f"\n- **状态**: 冲突已裁决（本条{win_word}{extra}）\n"
        else:
            text += f"\n- **状态**: 已废弃（{winner['date'] or '未知日期'} 条目{win_word}）\n"
        edits.append((b["start"], b["end"], text))

    # 从后往前应用编辑，保持位置有效
    for start, end, text in sorted(edits, key=lambda e: e[0], reverse=True):
        content = content[:start] + text + content[end:]

    with open(decisions_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"resolved": True,
            "detail": f"已裁决：保留{'旧' if keep == 'old' else '新'}条目"
                      f"（共 {len(topic_blocks)} 块，废弃 {n_losers} 块）"}


def list_conflicts(client_name):
    """扫描 decisions.md 全部 programmatic 块，按主题分组返回未决冲突组（只读）。

    返回 [{"topic", "dates", "pending_blocks"}]：topic 为全串（展示截断交 CLI 层），
    dates 为组内块日期（文件序去重），pending_blocks 为未决块数（双形态判定）。
    只列含未决块的主题组；不做任何写操作，供 resolve-conflict --list 枚举。
    """
    from _paths import _validate_client_name
    _validate_client_name(client_name)
    decisions_path = os.path.join(_client_dir(client_name), "decisions.md")
    if not os.path.exists(decisions_path):
        return []
    try:
        with open(decisions_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeError):
        return []
    groups = {}
    for b in _programmatic_blocks(content):
        if not b["topic"]:
            continue
        groups.setdefault(b["topic"], []).append(b)
    result = []
    for topic, blocks in groups.items():
        pending_n = sum(1 for b in blocks if _block_is_pending(b["text"]))
        if not pending_n:
            continue
        dates = []
        for b in blocks:
            if b["date"] and b["date"] not in dates:
                dates.append(b["date"])
        result.append({"topic": topic, "dates": dates, "pending_blocks": pending_n})
    return result


def build_keynote_head(keynote):
    """keynote HEAD 段（I-3 A3）：线清单摘要，注入 HEAD 最前段（先于普通铁律）。

    keynote 缺失/无线 -> ""。权重基准是注意力最高点最高优先级内容（ADR-009 §5-①）。
    """
    if not keynote or not keynote.get("lines"):
        return ""
    summary = "｜".join(
        f"{row['name']}({row['weight']}·{row['order']})" for row in keynote["lines"])
    return (f"=== 基调基准 keynote.md@{keynote['version'] or 'v?'}（权重仲裁先于普通铁律）===\n"
            f"[KEYNOTE] {summary}\n\n")


def build_head_context(themes, keynote=None):
    """生成 HEAD 文本：核心主题摘要，注入到 AI 上下文开头。

    HEAD 区是注意力密度最高点——放"必须遵守的硬约束"。
    P5 压缩（注意力机制外部证据）：HEAD 必须极短——前 4 条 + 计数，≤6 行。
    完整铁律留在 decisions.md，靠召回按需取；不再每条两行占满上下文。
    I-3 A3：keynote 为 permanent 特权源，其段置于最前（先于普通铁律）；
    keynote 缺失时行为与现状完全一致。

    输出格式对齐 PROJECT_DESIGN.md §4.3：
      === 核心约束刷新 ===
      [PERMANENT-CLIENT] 主题
      … 共 N 条永久铁律（前 4 条已列；完整见 decisions.md / recall）
    """
    kn_head = build_keynote_head(keynote)
    if not themes:
        return kn_head

    permanent = [t for t in themes if t["persistence"] == "permanent"]
    if not permanent:
        return kn_head

    lines = ["=== 核心约束刷新 ==="]
    for t in permanent[:4]:
        tag = f"[PERMANENT-{t['scope'].upper()}]"
        lines.append(f"{tag} {t['theme']}")
    if len(permanent) > 4:
        lines.append(f"… 共 {len(permanent)} 条永久铁律（前 4 条已列；完整见 decisions.md / recall）")
    lines.append("")
    return kn_head + "\n".join(lines)


def build_tail_checklist(themes, keynote=None):
    """生成 TAIL 文本：产出前自检清单，注入到上下文末尾。

    TAIL 区是注意力第二高点——放"交付前最后确认的事项"。
    I-3 A4：keynote 存在时追加「线间权重符合基调卡」自检项；
    keynote 缺失时行为与现状完全一致。
    """
    critical = [t for t in themes if t["priority"] == "critical" and t["persistence"] == "permanent"]
    items = [t["theme"] for t in critical]
    if keynote and keynote.get("lines"):
        items.append("线间权重符合基调卡（keynote.md）")
    if not items:
        return ""

    lines = ["## 产出前自检清单（TAIL — 交付前逐项确认）"]
    for i, theme in enumerate(items, 1):
        lines.append(f"- [ ] 第{i}项「{theme}」—— 产出中是否已体现？")
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
        "keynote": dict | None,      # I-3：keynote.md 解析结果（缺失为 None）
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

    # I-3 A3/A4：keynote 为 permanent 特权源（缺失 -> None，行为与现状一致）
    try:
        keynote = load_keynote(client_name)
    except Exception as e:
        warnings.append(f"load_keynote 失败: {e}")
        keynote = None

    permanent_client = [t for t in themes if t["scope"] == "client"]
    permanent_task = [t for t in themes if t["scope"] == "task"]

    head_ctx = build_head_context(themes, keynote=keynote)
    tail_cl = build_tail_checklist(themes, keynote=keynote)
    critical_count = sum(1 for t in themes if t["priority"] == "critical")

    return {
        "client_name": client_name,
        "task_id": task_id,
        "themes": themes,
        "permanent_client": permanent_client,
        "permanent_task": permanent_task,
        "keynote": keynote,
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
