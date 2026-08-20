# -*- coding: utf-8 -*-
"""会话管理模块：save_session + parse_args + auto_for_input。

从原 _session.py 拆分（候选 4 · 模块化）。
拆出的模块：
  - _context.py: context.md schema、层级判定、客户目录管理
  - _graph.py: 世界书 client_graph.json + client_index.md
  - _recall.py: BM25 + Embedding 双路召回 + RRF 融合
  - _onboard.py: 一键接单 + BM25 索引重建

re-export 保持 `from _session import xxx` 向后兼容。
"""
import os
import json
import re
import sys
import time
from datetime import datetime

from _paths import SCRIPT_DIR, TASK_HISTORY, INBOX_DIR, KNOWLEDGE_DIR

# Re-export for backward compatibility（from _session import xxx 无需修改）
from _context import *
from _graph import *
from _recall import *
from _onboard import *


# 产出索引可识别的交付物扩展名（中间产物如截图/临时文件不入索引）
_OUTPUT_INDEX_EXTS = (".html", ".pptx", ".docx", ".xlsx", ".md")


def update_outputs_index(client_name):
    """扫描 output/{客户}/ 顶层交付物，合并写入 outputs_index.json。

    outputs_index.json 此前无程序写入方（只能手工维护），本函数补上写入路径：
    - 已有条目原样保留（status/version 等人工维护字段不动，包括字符串格式旧条目）；
    - 新文件按命名规范 `{客户}_{类型}_{版本}.{格式}` 解析补默认条目；
    - 不删除已消失的文件（保留历史）。
    返回新增条目数。
    """
    import _paths

    client_out_dir = os.path.join(_paths.OUTPUT_DIR, client_name)
    if not os.path.isdir(client_out_dir):
        return 0
    client_path = os.path.join(_paths.CLIENTS_DIR, client_name)
    os.makedirs(client_path, exist_ok=True)
    index_path = os.path.join(client_path, "outputs_index.json")

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
    except (OSError, ValueError):
        idx = None
    if not isinstance(idx, dict):
        idx = {"outputs": []}
    outputs = idx.get("outputs")
    if not isinstance(outputs, list):
        outputs = []
        idx["outputs"] = outputs

    known = set()
    for e in outputs:
        if isinstance(e, dict):
            known.add(e.get("file"))
        elif isinstance(e, str):
            known.add(e)

    added = 0
    for fname in sorted(os.listdir(client_out_dir)):
        fpath = os.path.join(client_out_dir, fname)
        if not os.path.isfile(fpath) or fname.startswith(("~$", ".")):
            continue
        if not fname.lower().endswith(_OUTPUT_INDEX_EXTS):
            continue
        rel = os.path.relpath(fpath, _paths.SCRIPT_DIR).replace(os.sep, "/")
        if rel in known:
            continue
        stem = os.path.splitext(fname)[0]
        parts = stem.split("_")
        version = parts[-1] if len(parts) > 1 and re.fullmatch(r"v\d+", parts[-1]) else ""
        out_type = parts[-2] if version and len(parts) > 2 else ""
        outputs.append({
            "version": version,
            "file": rel,
            "type": out_type,
            "status": "在用",
            "date": datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d"),
            "method": "auto-scan",
        })
        known.add(rel)
        added += 1

    idx["client"] = idx.get("client") or client_name
    idx["last_update"] = datetime.now().strftime("%Y-%m-%d")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    return added


def _sync_bm25_if_stale(log_dir, today):
    """save 内调用：BM25 落后检测 + 每自然日一次节流重建（D-117/P1-5）。

    触发条件：当天未重建过（marker 文件记录日期）+ corpus 存在比
    bm25_index.pkl 更新的文件。全量重建约 37s，节流避免每次 save 都跑。
    """
    from _bm25 import BM25_INDEX_PATH
    from _paths import CLIENTS_DIR
    marker_path = os.path.join(log_dir, "bm25_rebuild_date.txt")
    last_date = ""
    if os.path.exists(marker_path):
        with open(marker_path, encoding="utf-8") as f:
            last_date = f.read().strip()
    if last_date == today:
        return
    bm25_mtime = (os.path.getmtime(BM25_INDEX_PATH)
                  if os.path.exists(BM25_INDEX_PATH) else 0)
    newest = bm25_mtime
    _ext = (".md", ".txt", ".docx", ".pdf", ".pptx", ".xlsx")
    for root, _dirs, files in os.walk(CLIENTS_DIR):
        if ".cache" in root:
            continue
        for fn in files:
            if fn.lower().endswith(_ext):
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, fn)))
                except OSError:
                    pass
    if newest > bm25_mtime:
        print("[索引] BM25 落后于 corpus，自动重建（每自然日最多一次）...")
        from _onboard import rebuild_bm25_index_all
        r = rebuild_bm25_index_all()
        print(f"[索引] BM25 重建完成: {r.get('indexed_count', 0)} 块")
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write(today)


def _extract_case_cards(client_name, max_age_days=30):
    """save 钩子：从 output/{客户}/ 的 spec 自动提取案例卡（D-123，业务启动包）。

    机械提取（不调 LLM）：标题/页面指纹（layout+composition+元素类型）/组件清单/
    构图母板清单/版本。写入 _knowledge/cases/，同 key 内容相同则跳过（幂等）。
    """
    import yaml as _yaml
    from _paths import OUTPUT_DIR, SCRIPT_DIR

    cases_dir = os.path.join(SCRIPT_DIR, "_knowledge", "cases")
    out_dir = os.path.join(OUTPUT_DIR, client_name)
    if not os.path.isdir(out_dir):
        return 0
    cutoff = time.time() - max_age_days * 86400
    written = 0
    try:
        entries = os.listdir(out_dir)
    except OSError:
        return 0
    for fn in sorted(entries):
        if not (fn.endswith(".yml") and "spec" in fn):
            continue
        spath = os.path.join(out_dir, fn)
        try:
            if os.path.getmtime(spath) < cutoff:
                continue
            with open(spath, "r", encoding="utf-8") as f:
                spec = _yaml.safe_load(f) or {}
        except Exception:
            continue
        if not isinstance(spec, dict) or not spec.get("pages"):
            continue
        # 版本：三种已知形态 {类型}_v{N}.spec.yml / {类型}_v{N}_spec.yml /
        # {类型}_spec_v{N}.yml
        m = re.search(r"(?:[_]v|_spec_v)(\d+(?:\.\d+)?)(?:\.spec|_spec)?\.yml$", fn)
        ver = m.group(1) if m else "0"
        title = (spec.get("document") or {}).get("title", "") or ""
        pages = []
        comps = set()
        comp_types = set()
        for p in spec.get("pages", []) or []:
            if not isinstance(p, dict):
                continue
            comp = p.get("composition") or []
            if isinstance(comp, str):
                comp = [comp]
            comps.update(comp)
            ptypes = []
            for e in p.get("elements", []) or []:
                if isinstance(e, dict) and e.get("type"):
                    comp_types.add(e["type"])
                    ptypes.append(e["type"])
            pages.append(f"{p.get('layout', '')}|{'+'.join(ptypes)}")
        if not pages:
            continue
        # 案例卡内容（结构指纹 = 页面序列，机械可比对复用）
        card = []
        card.append(f"# 案例卡：{client_name} · {title or fn}")
        card.append("")
        card.append(f"- 来源: `{os.path.join('output', client_name, fn)}`")
        card.append(f"- 版本: v{ver}")
        card.append(f"- 生成日期: {datetime.now().strftime('%Y-%m-%d')}")
        card.append(f"- 组件清单: {', '.join(sorted(comp_types))}")
        if comps:
            card.append(f"- 构图母板: {', '.join(sorted(comps))}")
        card.append("")
        card.append("## 页面结构指纹")
        card.append("")
        card.append("```")
        card.append("\n".join(pages))
        card.append("```")
        content = "\n".join(card) + "\n"
        os.makedirs(cases_dir, exist_ok=True)
        case_fn = f"{client_name}_{title or '方案'}_案例卡_v{ver}.md".replace(
            "/", "_").replace("\\", "_").replace(":", "_")
        cpath = os.path.join(cases_dir, case_fn)
        if os.path.exists(cpath):
            with open(cpath, "r", encoding="utf-8") as f:
                if f.read() == content:
                    continue  # 幂等：内容相同跳过
        with open(cpath, "w", encoding="utf-8") as f:
            f.write(content)
        written += 1
    return written


def _render_decisions_with_marker(decisions, marker):
    """决策正文拼接证据标记（P0 记忆溯源 T2）。

    decisions 非空且 marker 非空时追加 marker，否则原样返回（含 None / 空串）。
    纯函数，供测试直接覆盖三态拼接。
    """
    return (decisions + marker) if (decisions and marker) else decisions


def _build_session_entry(today, session_num, input_desc, decisions_rendered, outputs,
                         pending, evidence_lines, dsh_session):
    """构造会话块文本（T8a）。

    dsh_session 非空时在标题行下一行写 HTML 注释标记 `<!-- dsh:session:ID -->`；
    dsh_session 为空时输出与旧版 f-string 逐字节一致（P0 回归零感知）。
    纯函数，供测试直接覆盖两种输出。
    """
    entry = f"""
### [{today}] 第 {session_num} 次会话
#### 本次输入
{input_desc or '(未记录)'}
#### 关键决策
{decisions_rendered or '(未记录)'}
#### 产出文件
{outputs or '(未记录)'}
#### 待办 / 下次要做的
{pending or '(未记录)'}
"""
    if dsh_session:
        entry = entry.replace(
            f"### [{today}] 第 {session_num} 次会话\n",
            f"### [{today}] 第 {session_num} 次会话\n<!-- dsh:session:{dsh_session} -->\n",
            1,
        )
    if evidence_lines:
        entry += "#### 证据\n" + "\n".join(evidence_lines) + "\n"
    return entry


def _upsert_session_block(content, entry, dsh_session):
    """T8a：context.md 会话级 upsert —— 定位「最后一块」并整块替换。

    扫描 content 中最后一块会话块（`#{2,3} [日期]` 开头，兼容 `### ` 新格式与
    `## ` compact 格式）：若该块内带 `<!-- dsh:session:ID -->` 标记且 ID 与
    dsh_session 相同，则用 entry 的正文（保留旧标题行：日期与会话号不变）
    整块替换；否则原样返回 content（调用方走现有 append）。

    合并语义（监工修复 2026-08-19）：新 entry 某字段为空（含 "(未记录)"）时
    保留旧块对应字段；新 entry 无证据段但旧块有则保留。否则 light/dispose 的
    空参数 save 会把先前更丰富的内容覆盖掉。

    返回 (new_content, replaced, old_head)：
      - replaced=True 时 old_head = (旧日期, 旧会话号)，无法解析则为 None。
    """
    matches = list(re.finditer(r'(?m)^#{2,3} \[\d{4}-\d{2}-\d{2}\]', content))
    if not matches:
        return content, False, None
    start = matches[-1].start()
    last_block = content[start:]
    m = re.search(r'<!--\s*dsh:session:([^\s>]+)\s*-->', last_block)
    if not m or m.group(1) != dsh_session:
        return content, False, None
    head_line = last_block.split("\n", 1)[0]
    old_head = None
    hm = re.search(r'\[(\d{4}-\d{2}-\d{2})\] 第 (\d+) 次会话', head_line)
    if hm:
        old_head = (hm.group(1), int(hm.group(2)))
    merged_entry = _merge_session_entry(entry, _parse_session_sections(last_block))
    body = merged_entry[1:] if merged_entry.startswith("\n") else merged_entry  # 去掉前导换行
    nl = body.find("\n")
    new_block = (head_line + body[nl:]) if nl >= 0 else (head_line + body)
    return content[:start] + new_block, True, old_head


_SESSION_SECTION_RE = re.compile(
    r'(?ms)^#### (本次输入|关键决策|产出文件|待办 / 下次要做的|证据)\n(.*?)(?=^#### |\Z)')


def _parse_session_sections(block_text):
    """T8a 合并用：解析会话块的五个字段（含可选 证据 段）。纯函数。"""
    sections = {}
    for m in _SESSION_SECTION_RE.finditer(block_text):
        sections[m.group(1)] = m.group(2).rstrip("\n")
    return sections


def _merge_session_entry(entry, old_sections):
    """T8a 合并语义（监工修复 2026-08-19）：新 entry 字段为空或 "(未记录)" 时
    保留旧块同名字段；新 entry 无证据段但旧块有则保留旧证据段。

    纯函数：无字段可合并时返回原 entry（逐字节不变）。
    """
    if not old_sections:
        return entry
    changed = False

    def _repl(m):
        nonlocal changed
        key, body = m.group(1), m.group(2)
        had_nl = body.endswith("\n")
        body = body.rstrip("\n")
        if not body.strip() or body.strip() == "(未记录)":
            old = old_sections.get(key)
            if old is not None and old.strip():
                changed = True
                # 保留原段尾换行（组 2 惰性匹配会吞掉它，必须补回，
                # 否则下一段标题与正文挤同一行）
                return f"#### {key}\n{old}" + ("\n" if had_nl else "")
        return m.group(0)

    out = _SESSION_SECTION_RE.sub(_repl, entry)
    if "#### 证据" not in out:
        old_ev = old_sections.get("证据")
        if old_ev is not None and old_ev.strip():
            changed = True
            out = out.rstrip("\n") + "\n#### 证据\n" + old_ev.rstrip("\n") + "\n"
    return out if changed else entry


def _find_task_history_entry(history, client_name, dsh_session):
    """T8a：task_history 按 (project, dsh_session) 查重，返回条目下标或 None。"""
    project = f"client:{client_name}"
    for i, e in enumerate(history):
        if isinstance(e, dict) and e.get("project") == project \
                and e.get("dsh_session") == dsh_session:
            return i
    return None


def save_session(client_name, input_desc="", decisions="", outputs="", pending="", insight="",
                 evidence="", strict_evidence=False, dsh_session=None, light=False):
    """追加一条会话记录到客户 context.md 和 task_history.json

    insight: 本次会话的洞察摘要（如有，由 _insight.py 生成）
    evidence: 分号分隔的来源引用串（file:/session:/decision:/user:），写入前经
              _memory_guard.gate_entry 校验；空串 = 不携带证据（老调用零感知）。
    strict_evidence: True 时证据校验失败即阻断（返回 False，不写任何文件），
                     否则仅警告并照写。
    dsh_session: DSH 会话 ID（T8a）。非空时启用会话级 upsert：context.md 会话块
                 标题下一行写 `<!-- dsh:session:ID -->`，最后一块带同 ID 标记则整块
                 替换（会话号不变）；task_history 条目追加 dsh_session 键，同
                 (project, dsh_session) 已存在则原地更新。为空 = 现状 append。
    light: True 时只做证据守门 + context.md upsert + task_history upsert，
           跳过 embedding/graph/bm25/case_cards/session_notes（终点全量 save 补齐索引）。
    """
    # 客户名纠错：避免把别名当新客户创建空目录
    try:
        from _aliases import resolve_client_name
        resolved, candidates, matched_by = resolve_client_name(client_name)
        if matched_by == 'alias':
            print(f"[save] 客户名 '{client_name}' 已解析为 '{resolved}'（别名匹配）")
            client_name = resolved
        elif matched_by == 'substring':
            print(f"[save] ⚠️ 客户 '{client_name}' 不存在，近似候选: {', '.join(candidates)}")
            print(f"[save] 继续使用 '{client_name}'，请确认是否需要切换")
    except Exception as e:
        print(f"[warn] 客户名解析失败: {e}")

    # P0 记忆溯源（T2）：写入前守门。放在别名解析之后、ensure_client_dir/快照/
    # 任何写入之前 —— strict 阻断路径零副作用（不建目录、不写快照、不写历史）。
    from _memory_guard import gate_entry
    gate = gate_entry(decisions, evidence, client_name, strict=strict_evidence)
    if gate["verdict"] == "blocked":
        for r in gate["reasons"]:
            print(f"[证据] 阻断：{r}")
        print("[证据] --strict-evidence 生效，会话未保存")
        return False

    client_path = ensure_client_dir(client_name)
    context_path = os.path.join(client_path, "context.md")

    # P1 健壮性（T7）：按客户文件锁。放在别名解析与证据守门之后、任何写入之前；
    # 获取失败（默认 30s 超时）大声失败：print 明确中文原因并返回 False（不抛异常），
    # cmd_save 据此 exit 2 —— 绝不静默跳过、绝不绕锁写入。
    from _save_lock import acquire_save_lock, release_save_lock
    lock_fd = acquire_save_lock(client_path)
    if lock_fd is None:
        print(f"[锁] 获取保存锁失败：{os.path.join(client_path, '.save_lock')} "
              f"被其他进程持有且 30s 内未释放，会话未保存（避免并发写坏 context.md/task_history）")
        return False

    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # P1: 写前快照（用于回溯）
        snapshot_path = _snapshot_context(context_path)
        if snapshot_path:
            print(f"[快照] context.md 快照已保存: {os.path.basename(snapshot_path)}")

        with open(context_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 统计现有会话数（兼容旧 ## 格式和新 ### 格式）
        sessions = re.findall(r'#{2,3} \[(\d{4}-\d{2}-\d{2})\]', content)
        session_num = len(sessions) + 1

        decisions_rendered = _render_decisions_with_marker(decisions, gate["marker"])
        entry = _build_session_entry(today, session_num, input_desc, decisions_rendered,
                                     outputs, pending, gate["evidence_lines"], dsh_session)

        # T8a：会话级 upsert。dsh_session 非空时检查 context.md 最后一块是否带同 ID
        # 标记——是则整块替换（保留旧标题行：日期与会话号不变），否则走现有 append。
        replaced = False
        old_date = old_num = None
        if dsh_session:
            content, replaced, old_head = _upsert_session_block(content, entry, dsh_session)
            if replaced:
                if old_head:
                    old_date, old_num = old_head
                with open(context_path, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                with open(context_path, "a", encoding="utf-8") as f:
                    f.write(entry)
        else:
            with open(context_path, "a", encoding="utf-8") as f:
                f.write(entry)

        # 会话号口径：upsert 替换时沿用旧块编号，其余情况用新计算值
        reported_num = old_num if replaced else session_num

        # P1: 写后 schema 校验
        schema_ok, schema_issues = _validate_context_schema(context_path)
        if not schema_ok:
            print("[warn] context.md schema 问题：")
            for issue in schema_issues:
                print(f"  - {issue}")

        # 同时写入 task_history
        if os.path.exists(TASK_HISTORY):
            with open(TASK_HISTORY, "r", encoding="utf-8") as f:
                raw = f.read()
            try:
                history = json.loads(raw)
                if not isinstance(history, list):
                    # dict 格式（旧版兼容）：抽取 tasks 字段
                    if isinstance(history, dict) and isinstance(history.get("tasks"), list):
                        history = history["tasks"]
                    else:
                        history = []
            except Exception as e:
                # JSON 解析失败：备份原文件再重置，避免历史记录全丢
                backup = TASK_HISTORY + f".corrupt.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                try:
                    with open(backup, "w", encoding="utf-8") as f:
                        f.write(raw)
                    print(f"[警告] task_history.json 解析失败({e})，已备份到 {backup}")
                except Exception:
                    print(f"[警告] task_history.json 解析失败({e})，备份失败")
                history = []
        else:
            os.makedirs(os.path.dirname(TASK_HISTORY), exist_ok=True)
            history = []

        entry_task = {
            "date": today,
            "project": f"client:{client_name}",
            "session": reported_num,
            "decisions": decisions,
            "outputs": outputs,
            "pending": pending,
            "insight": insight,
            "evidence": evidence,
        }
        if dsh_session:
            entry_task["dsh_session"] = dsh_session
            # T8a：按 (project, dsh_session) 查重，已存在 -> 原地更新（date/session 等标识保持）
            idx = _find_task_history_entry(history, client_name, dsh_session)
            if idx is not None:
                old = history[idx]
                # 监工修复（2026-08-19）：合并语义——新值非空才覆盖，
                # 空参 upsert 不抹掉先前内容（与 context.md 合并一致）
                for _k, _v in (("decisions", decisions), ("outputs", outputs),
                               ("pending", pending), ("insight", insight),
                               ("evidence", evidence)):
                    if _v:
                        old[_k] = _v
            else:
                if replaced:
                    # 罕见情形：context.md 命中整块替换但 task_history 无同 ID 条目
                    # （如历史被重置/清理）——用旧块的日期与会话号对齐，避免编号错位
                    entry_task["date"] = old_date or today
                    entry_task["session"] = old_num or reported_num
                history.append(entry_task)
        else:
            history.append(entry_task)

        with open(TASK_HISTORY, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        # P0 记忆溯源（T2）：证据引用汇总。静默失效是最高优先级 bug，计数必须可见。
        if gate["counts"]["total_refs"] > 0:
            print(f"[证据] 引用 {gate['counts']['total_refs']}：通过 {gate['counts']['passed']} / 待核 {gate['counts']['failed']}{gate['marker']}")
        elif decisions and str(decisions).strip():
            print("[证据] 决策未携带证据（--evidence= 可补）")

        print(f"会话已保存: {client_name} 第 {reported_num} 次")

        # T8a：light 模式只做证据守门 + context.md upsert + task_history upsert，
        # 跳过 embedding/graph/bm25/case_cards/session_notes（终点全量 save 补齐索引）。
        if light:
            print("[light-save] 跳过索引/图谱/笔记")
        else:
            # 自动增量更新 Embedding 索引（失败不影响主流程）
            try:
                from _embed_index import build_embedding_index
                print("[索引] 自动增量更新 Embedding...")
                result = build_embedding_index(batch_size=50, force=False)
                if result and isinstance(result, dict):
                    total = len(result.get("vectors", {}))
                    print(f"[索引] 完成: 总计 {total} 个向量")
            except Exception as e:
                print(f"[索引] 增量更新跳过: {e}")

            # 自动同步 BM25 索引（D-117/P1-5 修复：此前 save 只更 Embedding，
            # BM25 长期滞后导致 RRF 双路不对称；节流逻辑见 _sync_bm25_if_stale）
            try:
                _sync_bm25_if_stale(os.path.dirname(TASK_HISTORY), today)
            except Exception as e:
                print(f"[索引] BM25 同步跳过: {e}")

        # 自动更新 outputs_index.json（graph 读取它，必须先于 graph 更新；失败不影响主流程）
        try:
            n_added = update_outputs_index(client_name)
            if n_added:
                print(f"[索引] outputs_index 新增 {n_added} 条产出记录")
        except Exception as e:
            print(f"[索引] outputs_index 更新跳过: {e}")

        # 自动提取案例卡（D-123，业务启动包；失败不影响主流程）
        if not light:
            try:
                n_cards = _extract_case_cards(client_name)
                if n_cards:
                    print(f"[案例] 新增/更新 {n_cards} 张案例卡")
            except Exception as e:
                print(f"[案例] 案例卡提取跳过: {e}")

        # 自动更新世界书 client_graph.json + client_index.md（失败不影响主流程）
        if not light:
            try:
                print("[graph] 自动更新 client_graph...")
                build_client_graph(client_name)
            except Exception as e:
                print(f"[graph] 更新跳过: {e}")

        # 三项强制检查（project_rules.md 会话结束 MANDATORY）
        import glob
        warnings = []
        # 检查 1：inbox/ 残留 .py/.log/.tmp/.pyc/.bak
        for ext in (".py", ".log", ".tmp", ".pyc", ".bak"):
            junk = glob.glob(os.path.join(INBOX_DIR, f"*{ext}"))
            if junk:
                warnings.append(f"inbox/ 有残留: {[os.path.basename(f) for f in junk]}")
        # 检查 2：产出路径合规（outputs 字段提到的文件应落在 output/{客户}/ 下）
        if outputs and isinstance(outputs, str):
            for line in outputs.splitlines():
                line = line.strip()
                if line and (line.endswith(".html") or line.endswith(".pptx") or line.endswith(".docx") or line.endswith(".xlsx")):
                    # 检查是否在 output/{客户}/ 路径下
                    expected_prefix = os.path.join(SCRIPT_DIR, "output", client_name)
                    if not os.path.isabs(line):
                        line_abs = os.path.join(SCRIPT_DIR, line)
                    else:
                        line_abs = line
                    if not os.path.abspath(line_abs).startswith(os.path.abspath(expected_prefix)):
                        warnings.append(f"产出路径不合规（应在 output/{client_name}/）: {line}")
        # 检查 3：_uncategorized/ 堆积
        uncat = os.path.join(KNOWLEDGE_DIR, "clients", "_uncategorized")
        if os.path.isdir(uncat):
            n = len(os.listdir(uncat))
            if n > 0:
                warnings.append(f"_uncategorized/ 堆积 {n} 个文件")

        if warnings:
            print("[warn] 会话结束检查警告：")
            for w in warnings:
                print(f"  - {w}")

        # 生成 session_notes 独立笔记（v2.9.7 · 结构化笔记持久化；light 模式跳过）
        if not light:
            try:
                notes_path = os.path.join(client_path, f"session_notes_{today}.md")
                notes_lines = [
                    f"# 会话笔记 · {client_name} · {today}（第 {reported_num} 次）",
                    "",
                    "## 本次目标",
                    input_desc[:200] if input_desc else "(未记录)",
                    "",
                    "## 完成项",
                    outputs[:500] if outputs else "(未记录)",
                    "",
                    "## 待办",
                    pending[:500] if pending else "(无待办)",
                    "",
                    "## 关键决策",
                    decisions[:500] if decisions else "(未记录)",
                    "",
                ]
                with open(notes_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(notes_lines))
                print(f"[笔记] session_notes 已生成: {os.path.basename(notes_path)}")
            except Exception as e:
                print(f"[笔记] session_notes 生成失败（不阻断）: {e}")

        return True  # 正常完成（旧版返回 warnings 且调用方均忽略；T2 起改 bool 供 _cli 判阻断）
    finally:
        # P1 健壮性（T7）：任何路径（含异常传播）都释放锁；自己持有的锁 remove 必成功
        release_save_lock(client_path, lock_fd)


def parse_args(args):
    """解析 save 子命令的会话内容键（原样传入，见 _cli.py p_save 的 extra 参数）。

    返回 dict：
      - input_desc / decisions / outputs / pending：原有四键，行为不变；
      - evidence：分号分隔的来源引用串（file:/session:/decision:/user:），原样存；
      - strict_evidence："1"/"true"/"yes"（大小写不敏感）为 True，其余 False，缺省 False；
      - dsh_session：`--dsh-session=ID` 的 DSH 会话 ID（T8a），缺省 None；
      - light：`--light` 或 `--light=1` 为 True（T8a），缺省 False。
    """
    result = {"input_desc": "", "decisions": "", "outputs": "", "pending": "",
              "evidence": "", "strict_evidence": False,
              "dsh_session": None, "light": False}
    for arg in args:
        if arg.startswith("--input="):
            result["input_desc"] = arg[8:]
        elif arg.startswith("--decisions="):
            result["decisions"] = arg[12:]
        elif arg.startswith("--outputs="):
            result["outputs"] = arg[10:]
        elif arg.startswith("--pending="):
            result["pending"] = arg[10:]
        elif arg.startswith("--evidence="):
            result["evidence"] = arg[len("--evidence="):]
        elif arg.startswith("--strict-evidence="):
            result["strict_evidence"] = arg[len("--strict-evidence="):].strip().lower() in ("1", "true", "yes")
        elif arg.startswith("--dsh-session="):
            result["dsh_session"] = arg[len("--dsh-session="):] or None
        elif arg == "--light":
            result["light"] = True
        elif arg.startswith("--light="):
            result["light"] = arg[len("--light="):].strip().lower() in ("1", "true", "yes")
    return result


# ============================================================
# IDE 模式钩子（auto_for_input）
# ============================================================
def auto_for_input(user_input, client_name=None):
    """IDE 模式：AI 收到用户输入时自动调用。

    组合 detect_level + load_context_by_level + recall，返回结构化上下文。
    失败时返回降级结果（含 warnings），不抛异常。

    返回 schema:
    {
        "level": "L3"|"L4"|"L5",
        "mode": "directed"|"collaborative"|"autonomous",
        "context_summary": str,          # ≤500 字
        "loaded_context": dict,          # load_context_by_level 的返回
        "recall": list,                 # ≤5 条召回结果
        "warnings": list                 # 钩子失败时的降级警告
    }
    """
    warnings = []

    # 1. 判层级
    try:
        level, mode = detect_level(user_input)
    except Exception as e:
        level, mode = "L4", "collaborative"
        warnings.append(f"detect_level 失败，默认 L4: {e}")

    # 2. 按层级加载上下文
    loaded = {}
    if client_name:
        try:
            loaded = load_context_by_level(client_name, level) or {}
        except Exception as e:
            warnings.append(f"load_context_by_level 失败: {e}")

    # 3. 语义召回（≤5 条，token 预算控制）
    recall_results = []
    try:
        recall_results = recall(
            user_input, client_name=client_name,
            use_embedding=True, return_results=True
        ) or []
        recall_results = recall_results[:5]
    except Exception as e:
        warnings.append(f"recall 失败: {e}")

    # 4. 生成摘要（≤500 字）
    summary_parts = []
    if loaded.get("client_index"):
        summary_parts.append(f"客户索引: {loaded['client_index'][:500]}")
    elif loaded.get("decisions"):
        summary_parts.append(f"上次决策: {loaded['decisions'][:500]}")
    if recall_results:
        summary_parts.append(f"相关召回 {len(recall_results)} 条")
    context_summary = " | ".join(summary_parts)[:500] if summary_parts else "无历史上下文"

    return {
        "level": level,
        "mode": mode,
        "context_summary": context_summary,
        "loaded_context": loaded,
        "recall": recall_results,
        "warnings": warnings,
    }


def generate_handoff_packet(client_name):
    """生成会话交接包 handoff_packet.md（≤50 行）。

    提取当前客户的关键状态：目标/已完成/待办/铁律/指针。
    用于上下文重置：用户新开对话时，session-start 自动检测并注入。

    返回：(content_str, filepath_str)
    """
    from _context import ensure_client_dir

    client_path = ensure_client_dir(client_name)
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. 从 task_history.json 提取最近任务
    recent_task = ""
    try:
        with open(TASK_HISTORY, "r", encoding="utf-8") as f:
            history = json.load(f)
        if isinstance(history, list):
            for entry in reversed(history):
                if entry.get("client") == client_name:
                    recent_task = entry.get("input_desc", "") or entry.get("task", "")
                    break
    except Exception:
        pass

    # 2. 从 context.md 提取最近会话的待办
    pending_items = []
    completed_items = []
    context_path = os.path.join(client_path, "context.md")
    try:
        with open(context_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 找最后一次会话的待办
        sessions = re.findall(r'## \[\d{4}-\d{2}-\d{2}\]\s*第 \d+ 次会话.*?(?=## \[|\Z)', content, re.DOTALL)
        if sessions:
            last_session = sessions[-1]
            # 提取待办
            pending_match = re.search(r'### 待办.*?\n(.*?)(?=###|\Z)', last_session, re.DOTALL)
            if pending_match:
                for line in pending_match.group(1).strip().split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line and line != "(未记录)":
                        pending_items.append(line)
            # 提取产出
            output_match = re.search(r'### 产出文件.*?\n(.*?)(?=###|\Z)', last_session, re.DOTALL)
            if output_match:
                for line in output_match.group(1).strip().split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line and line != "(未记录)":
                        completed_items.append(line)
    except Exception:
        pass

    # 3. 从 decisions.md 提取铁律（permanent + client）
    themes = []
    decisions_path = os.path.join(client_path, "decisions.md")
    try:
        from _theme_guard import load_active_themes
        themes = load_active_themes(client_name, only_permanent=True)
    except Exception:
        pass

    # 4. 找最近产出文件
    recent_output = ""
    try:
        outputs_index = os.path.join(client_path, "outputs_index.json")
        if os.path.exists(outputs_index):
            with open(outputs_index, "r", encoding="utf-8") as f:
                idx = json.load(f)
            if isinstance(idx, dict) and idx.get("files"):
                files = idx["files"]
                if isinstance(files, list) and files:
                    recent_output = files[-1].get("path", "")
            elif isinstance(idx, list) and idx:
                recent_output = idx[-1].get("path", "")
    except Exception:
        pass

    # 5. 组装交接包（≤50 行）
    lines = [
        f"# 会话交接包 · {client_name} · {today}",
        "",
        "## 当前目标",
        recent_task[:200] if recent_task else "(从 task_history 提取)",
        "",
        "## 已完成",
    ]
    if completed_items:
        for item in completed_items[:5]:
            lines.append(f"- {item[:100]}")
    else:
        lines.append("- (无记录)")

    lines.append("")
    lines.append("## 待办")
    if pending_items:
        for item in pending_items[:5]:
            lines.append(f"- {item[:100]}")
    else:
        lines.append("- (无待办)")

    lines.append("")
    lines.append("## 铁律刷新")
    if themes:
        for t in themes[:8]:
            persistence = t.get("persistence", "permanent").upper()
            scope = t.get("scope", "client").upper()
            lines.append(f"[{persistence}-{scope}] {t.get('theme', '')[:100]}")
    else:
        lines.append("(无铁律)")

    lines.append("")
    lines.append("## 上下文指针")
    lines.append(f"- context.md: {context_path}")
    lines.append(f"- decisions.md: {decisions_path}")
    if recent_output:
        lines.append(f"- 最近产出: {recent_output}")
    client_index = os.path.join(client_path, "client_index.md")
    lines.append(f"- 世界书: {client_index}")

    content = "\n".join(lines)

    # 写入文件
    handoff_path = os.path.join(client_path, "handoff_packet.md")
    with open(handoff_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content, handoff_path


def check_handoff_packet(client_name):
    """检测并读取 handoff_packet.md。存在则返回内容并删除文件（一次性使用）。

    返回：(content_str or None, found_bool)

    注意：不调用 ensure_client_dir，避免读文件时误建空客户目录。
    """
    from _paths import CLIENTS_DIR, _validate_client_name
    _validate_client_name(client_name)

    handoff_path = os.path.join(CLIENTS_DIR, client_name, "handoff_packet.md")

    if not os.path.exists(handoff_path):
        return None, False

    try:
        with open(handoff_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 删除文件（一次性使用）
        os.remove(handoff_path)
        return content, True
    except Exception:
        return None, False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python _session.py list                                    列出所有客户")
        print("  python _session.py status                                  所有客户状态一览")
        print("  python _session.py load <客户名>                           加载客户上下文")
        print("  python _session.py save <客户名> [参数...]                 保存会话")
        print("       --input=\"描述\" --decisions=\"决策\" --outputs=\"文件\" --pending=\"待办\"")
        print("  python _session.py recall <关键词>                         召回相关项目")
        print("  python _session.py consolidate <客户名> [阈值]             自动固化模式到规则")
        print("  python _session.py compact <客户名> [保留最近N次]          压缩历史上下文")
        sys.exit(0)

    action = sys.argv[1]

    if action == "list":
        print("客户项目:", list_clients())

    elif action == "status":
        show_all_clients()

    elif action == "load" and len(sys.argv) >= 3:
        load_context(sys.argv[2])

    elif action == "save" and len(sys.argv) >= 3:
        client = sys.argv[2]
        kwargs = parse_args(sys.argv[3:])
        if not any(kwargs.values()):
            print(f"保存 {client} 的会话记录：")
            kwargs["input_desc"] = input(" 本次输入（简述）: ").strip()
            kwargs["decisions"] = input(" 关键决策: ").strip()
            kwargs["outputs"] = input(" 产出文件: ").strip()
            kwargs["pending"] = input(" 待办事项: ").strip()
        save_session(client, **kwargs)

    elif action == "recall" and len(sys.argv) >= 3:
        recall(" ".join(sys.argv[2:]))

    elif action == "consolidate" and len(sys.argv) >= 3:
        client = sys.argv[2]
        threshold = int(sys.argv[3]) if len(sys.argv) >= 4 else 2
        consolidate(client, threshold)

    elif action == "compact" and len(sys.argv) >= 3:
        client = sys.argv[2]
        keep_last = int(sys.argv[3]) if len(sys.argv) >= 4 else 1
        compact(client, keep_last)

    else:
        print("无效命令")
